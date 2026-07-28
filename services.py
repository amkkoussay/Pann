"""
Bakery ERP System - Business Services Layer

Encapsulates the "smart" business logic on top of the ORM models:
  * SmartInventoryService   - consumption forecasting + auto reorder
  * ProfitabilityService    - per-product margin + waste cost analytics
  * InventoryService        - transactional stock movements / production

Each service takes a SQLAlchemy `db.session` (or operates inside an
`app.app_context()`) so it can be reused from Flask routes, CLI, or tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, date, timedelta
from typing import Iterable, List, Optional

from sqlalchemy import func, and_

from models import (
    db,
    InventoryItem, StockMovement, Product, Recipe,
    ProductionOrder, ProductionWaste, Supplier, PurchaseOrder, PurchaseItem,
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class InsufficientStockError(Exception):
    """Raised when a stock movement would drive quantity below zero."""

    def __init__(self, item_name: str, available: float, requested: float):
        self.item_name = item_name
        self.available = available
        self.requested = requested
        super().__init__(
            f"Insufficient stock for '{item_name}': "
            f"requested {requested}, available {available}"
        )


class UnknownProductError(Exception):
    pass


# ---------------------------------------------------------------------------
# Result dataclasses (lightweight DTOs for views / JSON / templates)
# ---------------------------------------------------------------------------
@dataclass
class ReorderSuggestion:
    item_id: int
    name: str
    unit: str
    quantity: float
    min_stock: float
    avg_daily_consumption: float
    days_until_stockout: Optional[float]
    recommended_order_qty: float
    preferred_supplier: Optional[str]
    lead_time_days: int
    urgency: str  # 'critical' | 'soon' | 'monitor' | 'ok'

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProductProfitability:
    product_id: int
    name: str
    category: str
    price: float
    computed_cost: float
    margin: float
    margin_pct: float
    units_sold: int
    revenue: float
    waste_units: int
    waste_cost: float
    net_profit: float

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Smart Inventory Forecasting
# ---------------------------------------------------------------------------
class SmartInventoryService:
    """
    Turns raw `stock_movements` rows into actionable predictions:
      * average daily consumption over a configurable window
      * estimated days-until-stockout
      * recommended reorder quantity based on the fastest supplier lead time
    """

    DEFAULT_WINDOW_DAYS = 30
    SAFETY_STOCK_DAYS = 7  # extra buffer on top of lead time
    CRITICAL_DAYS = 3
    SOON_DAYS = 7

    def __init__(self, window_days: int = DEFAULT_WINDOW_DAYS):
        self.window_days = window_days

    # ---- core math --------------------------------------------------------
    def avg_daily_consumption(self, item_id: int) -> float:
        """Average outbound quantity per day over the window."""
        cutoff = datetime.utcnow() - timedelta(days=self.window_days)
        total_out = (
            db.session.query(func.coalesce(func.sum(StockMovement.quantity), 0.0))
            .filter(StockMovement.inventory_item_id == item_id)
            .filter(StockMovement.type == 'out')
            .filter(StockMovement.created_at >= cutoff)
            .scalar()
        ) or 0.0
        return float(total_out) / float(self.window_days)

    def days_until_stockout(self, item: InventoryItem,
                            avg_daily: Optional[float] = None) -> Optional[float]:
        if avg_daily is None:
            avg_daily = self.avg_daily_consumption(item.id)
        if avg_daily <= 0:
            return None
        return round(item.quantity / avg_daily, 1)

    def preferred_supplier_for(self, item: InventoryItem) -> Optional[Supplier]:
        """
        Choose the supplier with the smallest observed lead time among
        purchase_items for this inventory item. Falls back to None if no
        history exists.
        """
        # Average days between PO date and an arbitrary 'expected' in the
        # past. We approximate via the supplier's stored `lead_time_days`
        # filtered to suppliers who actually supplied this item.
        rows = (
            db.session.query(Supplier)
            .join(PurchaseOrder, PurchaseOrder.supplier_id == Supplier.id)
            .join(PurchaseItem, PurchaseItem.purchase_id == PurchaseOrder.id)
            .filter(PurchaseItem.inventory_item_id == item.id)
            .all()
        )
        if not rows:
            return None
        return min(rows, key=lambda s: (s.lead_time_days or 999))

    def recommended_reorder_qty(self, item: InventoryItem,
                                avg_daily: float,
                                lead_time_days: int) -> float:
        """
        Reorder enough to cover (lead time + safety stock) days of demand,
        but at least enough to reach 2x min_stock. Returns 0 if no demand.
        """
        if avg_daily <= 0:
            return 0.0
        horizon = max(lead_time_days + self.SAFETY_STOCK_DAYS, 1)
        target = avg_daily * horizon
        # Round up to a sensible "case" size: nearest integer for units like
        # `pc`, otherwise one decimal place.
        if item.unit in ('pc', 'box', 'bag', 'dozen'):
            return float(max(1, round(target)))
        return round(target, 2)

    def urgency_for(self, days_left: Optional[float]) -> str:
        if days_left is None:
            return 'monitor'
        if days_left <= self.CRITICAL_DAYS:
            return 'critical'
        if days_left <= self.SOON_DAYS:
            return 'soon'
        return 'ok'

    # ---- public API -------------------------------------------------------
    def analyze_item(self, item: InventoryItem) -> ReorderSuggestion:
        avg_daily = self.avg_daily_consumption(item.id)
        days_left = self.days_until_stockout(item, avg_daily)
        supplier = self.preferred_supplier_for(item)
        lead = (supplier.lead_time_days if supplier and supplier.lead_time_days
                else 3)
        rec_qty = self.recommended_reorder_qty(item, avg_daily, lead) \
            if item.is_low_stock or (days_left is not None and days_left <= lead) \
            else 0.0
        return ReorderSuggestion(
            item_id=item.id,
            name=item.name,
            unit=item.unit,
            quantity=item.quantity,
            min_stock=item.min_stock,
            avg_daily_consumption=round(avg_daily, 3),
            days_until_stockout=days_left,
            recommended_order_qty=rec_qty,
            preferred_supplier=supplier.name if supplier else None,
            lead_time_days=lead,
            urgency=self.urgency_for(days_left) if item.is_low_stock
                     or (days_left is not None and days_left <= lead)
                     else 'ok',
        )

    def analyze_all(self) -> List[ReorderSuggestion]:
        items: Iterable[InventoryItem] = (
            db.session.query(InventoryItem).order_by(InventoryItem.name).all()
        )
        return [self.analyze_item(it) for it in items]

    def low_stock_with_predictions(self) -> List[ReorderSuggestion]:
        """Only items at or below min_stock — used by the dashboard alert."""
        items = (
            db.session.query(InventoryItem)
            .filter(InventoryItem.quantity <= InventoryItem.min_stock)
            .order_by(InventoryItem.quantity.asc())
            .all()
        )
        return [self.analyze_item(it) for it in items]


# ---------------------------------------------------------------------------
# Profitability Analytics
# ---------------------------------------------------------------------------
class ProfitabilityService:
    """
    Real margin reporting. Joins recipes → ingredient cost to compute the
    TRUE cost-of-goods for each product, and folds in waste cost recorded
    against production orders.
    """

    def __init__(self, waste_window_days: Optional[int] = None):
        # waste_window_days None = all-time
        self.waste_window_days = waste_window_days

    def _recipe_cost(self, product_id: int) -> float:
        total = (
            db.session.query(
                func.coalesce(
                    func.sum(Recipe.quantity_required * InventoryItem.cost),
                    0.0)
            )
            .select_from(Recipe)
            .join(InventoryItem, InventoryItem.id == Recipe.inventory_item_id)
            .filter(Recipe.product_id == product_id)
            .scalar()
        )
        return float(total or 0.0)

    def _units_sold(self, product_id: int) -> int:
        from models import SaleItem, Sale
        total = (
            db.session.query(func.coalesce(func.sum(SaleItem.qty), 0))
            .join(Sale, Sale.id == SaleItem.sale_id)
            .filter(SaleItem.product_id == product_id)
            .scalar()
        )
        return int(total or 0)

    def _revenue(self, product_id: int) -> float:
        from models import SaleItem, Sale
        total = (
            db.session.query(func.coalesce(func.sum(SaleItem.total), 0.0))
            .join(Sale, Sale.id == SaleItem.sale_id)
            .filter(SaleItem.product_id == product_id)
            .scalar()
        )
        return float(total or 0.0)

    def _waste_units(self, product_id: int) -> int:
        q = (
            db.session.query(
                func.coalesce(func.sum(ProductionWaste.quantity), 0))
            .join(ProductionOrder,
                  ProductionOrder.id == ProductionWaste.production_order_id)
            .filter(ProductionOrder.product_id == product_id)
        )
        if self.waste_window_days:
            cutoff = date.today() - timedelta(days=self.waste_window_days)
            q = q.filter(ProductionWaste.recorded_at >= cutoff)
        return int(q.scalar() or 0)

    def analyze_product(self, product: Product) -> ProductProfitability:
        cost = self._recipe_cost(product.id)
        margin = float(product.price or 0) - cost
        margin_pct = (margin / float(product.price) * 100.0) \
            if product.price else 0.0
        units = self._units_sold(product.id)
        revenue = self._revenue(product.id)
        waste_units = self._waste_units(product.id)
        waste_cost = float(waste_units) * cost
        net_profit = margin * units - waste_cost
        return ProductProfitability(
            product_id=product.id,
            name=product.name,
            category=product.category,
            price=float(product.price or 0),
            computed_cost=round(cost, 4),
            margin=round(margin, 4),
            margin_pct=round(margin_pct, 2),
            units_sold=units,
            revenue=round(revenue, 2),
            waste_units=waste_units,
            waste_cost=round(waste_cost, 2),
            net_profit=round(net_profit, 2),
        )

    def analyze_all(self) -> List[ProductProfitability]:
        products = (
            db.session.query(Product)
            .filter(Product.is_active == 1)
            .order_by(Product.category, Product.name)
            .all()
        )
        results = [self.analyze_product(p) for p in products]
        # Sort worst-margin first so the dashboard surfaces loss-makers.
        results.sort(key=lambda r: r.margin)
        return results

    def total_waste_cost(self) -> float:
        """Sum of waste_cost across all products in the window."""
        return round(sum(r.waste_cost for r in self.analyze_all()), 2)


# ---------------------------------------------------------------------------
# Transactional inventory helpers
# ---------------------------------------------------------------------------
class InventoryService:
    """
    Thin transactional layer over stock movements + production. Anything
    that mutates `inventory_items.quantity` MUST go through here so the
    `stock_movements` ledger stays consistent.
    """

    @staticmethod
    def record_movement(item_id: int, movement_type: str, quantity: float,
                        reference_type: Optional[str] = None,
                        reference_id: Optional[int] = None,
                        notes: Optional[str] = None) -> StockMovement:
        if movement_type not in ('in', 'out'):
            raise ValueError("movement_type must be 'in' or 'out'")
        if quantity <= 0:
            raise ValueError("quantity must be positive")

        item: Optional[InventoryItem] = db.session.get(InventoryItem, item_id)
        if not item:
            raise ValueError(f"Inventory item {item_id} not found")

        if movement_type == 'out' and item.quantity < quantity:
            raise InsufficientStockError(item.name, item.quantity, quantity)

        if movement_type == 'in':
            item.quantity = (item.quantity or 0) + quantity
        else:
            item.quantity = (item.quantity or 0) - quantity

        mv = StockMovement(
            inventory_item_id=item.id,
            type=movement_type,
            quantity=quantity,
            reference_type=reference_type,
            reference_id=reference_id,
            notes=notes,
        )
        db.session.add(mv)
        return mv

    @classmethod
    def complete_production(cls, order: ProductionOrder,
                            actual_qty: int) -> ProductionOrder:
        """
        Atomically deduct recipe ingredients from inventory and stamp the
        production order as completed. Raises InsufficientStockError if any
        ingredient is short.
        """
        if order.status == 'completed':
            raise ValueError("Production order already completed")

        # Lock-in ingredients at order time.
        ingredients = (
            db.session.query(Recipe, InventoryItem)
            .join(InventoryItem, InventoryItem.id == Recipe.inventory_item_id)
            .filter(Recipe.product_id == order.product_id)
            .all()
        )
        scale = (actual_qty or order.planned_qty) / max(order.planned_qty, 1)
        for recipe, item in ingredients:
            needed = float(recipe.quantity_required) * order.planned_qty
            # pre-check
            if item.quantity < needed:
                raise InsufficientStockError(item.name, item.quantity, needed)
            cls.record_movement(
                item_id=item.id,
                movement_type='out',
                quantity=needed,
                reference_type='production',
                reference_id=order.id,
                notes=f"Production #{order.id} ({order.product.name})",
            )
        order.actual_qty = actual_qty
        order.status = 'completed'
        return order

    @classmethod
    def receive_purchase(cls, order: PurchaseOrder) -> PurchaseOrder:
        if order.status == 'completed':
            raise ValueError("Purchase order already received")
        for pi in order.items:
            cls.record_movement(
                item_id=pi.inventory_item_id,
                movement_type='in',
                quantity=pi.qty,
                reference_type='purchase',
                reference_id=order.id,
                notes=f"PO #{order.id} from {order.supplier.name}",
            )
        order.status = 'completed'
        return order
