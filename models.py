"""
Bakery ERP System - SQLAlchemy ORM Models
Provides typed models, relationships, and migration-ready schema for the
bakery ERP system. The legacy `database.py` keeps working side-by-side for
backward compatibility with the existing blueprints, while new code can use
the `db.session` API and the `models` layer.
"""
from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import (
    Column, Integer, String, Text, Float, Date, DateTime, Boolean,
    ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship, backref
from werkzeug.security import generate_password_hash, check_password_hash

# Single shared SQLAlchemy instance. The Flask app factory binds it via
# `db.init_app(app)`; tests can also call `db.create_all()` against a
# throwaway in-memory or file-based DB.
db = SQLAlchemy()


# ---------------------------------------------------------------------------
# Users & customers
# ---------------------------------------------------------------------------
class User(db.Model):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(80), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default='customer')
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Integer, default=1, nullable=False)

    # Relationships
    customer = relationship('Customer', uselist=False, back_populates='user')
    sales = relationship('Sale', back_populates='user')

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    @property
    def is_staff(self) -> bool:
        return self.role in ('admin', 'manager', 'cashier')

    def __repr__(self) -> str:
        return f'<User {self.username} ({self.role})>'


class Customer(db.Model):
    __tablename__ = 'customers'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    name = Column(String(120), nullable=False)
    email = Column(String(120), unique=True)
    phone = Column(String(40))
    address = Column(Text)
    credit_limit = Column(Float, default=0, nullable=False)
    balance = Column(Float, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship('User', back_populates='customer')
    sales = relationship('Sale', back_populates='customer')
    payments = relationship('Payment', back_populates='customer')

    def __repr__(self) -> str:
        return f'<Customer {self.name}>'


class Supplier(db.Model):
    __tablename__ = 'suppliers'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False, index=True)
    contact_person = Column(String(120))
    email = Column(String(120))
    phone = Column(String(40))
    address = Column(Text)
    # Lead time in DAYS (used by the smart reorder predictor).
    lead_time_days = Column(Integer, default=3, nullable=False)
    balance = Column(Float, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    purchase_orders = relationship('PurchaseOrder', back_populates='supplier')
    supplier_payments = relationship('SupplierPayment', back_populates='supplier')

    def __repr__(self) -> str:
        return f'<Supplier {self.name}>'


# ---------------------------------------------------------------------------
# Inventory, recipes, production
# ---------------------------------------------------------------------------
class InventoryItem(db.Model):
    __tablename__ = 'inventory_items'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False, index=True)
    type = Column(String(40), nullable=False)  # raw_material / packaging / ...
    unit = Column(String(20), nullable=False)
    quantity = Column(Float, default=0, nullable=False)
    min_stock = Column(Float, default=0, nullable=False)
    cost = Column(Float, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    movements = relationship('StockMovement', back_populates='item',
                             cascade='all, delete-orphan')
    recipe_uses = relationship('Recipe', back_populates='item')
    purchase_items = relationship('PurchaseItem', back_populates='item')

    @property
    def is_low_stock(self) -> bool:
        return self.quantity <= self.min_stock

    def __repr__(self) -> str:
        return f'<InventoryItem {self.name} qty={self.quantity} {self.unit}>'


class Product(db.Model):
    __tablename__ = 'products'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False, index=True)
    category = Column(String(40), nullable=False, index=True)
    description = Column(Text)
    price = Column(Float, nullable=False)
    cost = Column(Float, default=0, nullable=False)
    image_path = Column(String(200))
    is_active = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    recipes = relationship('Recipe', back_populates='product',
                           cascade='all, delete-orphan')
    sales_items = relationship('SaleItem', back_populates='product')
    production_orders = relationship('ProductionOrder', back_populates='product')

    @property
    def computed_cost(self) -> float:
        """Sum of (recipe ingredient qty * ingredient cost) for this product."""
        return sum((r.quantity_required or 0) * (r.item.cost or 0)
                   for r in self.recipes)

    @property
    def margin(self) -> float:
        return float(self.price or 0) - float(self.computed_cost or 0)

    @property
    def margin_pct(self) -> float:
        cost = self.computed_cost or 0
        if cost <= 0:
            return 0.0
        return (self.margin / self.price) * 100 if self.price else 0.0

    def __repr__(self) -> str:
        return f'<Product {self.name} ${self.price}>'


class Recipe(db.Model):
    """BOM line: one ingredient for one product."""
    __tablename__ = 'recipes'
    __table_args__ = (
        UniqueConstraint('product_id', 'inventory_item_id',
                         name='uq_recipes_product_item'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey('products.id'),
                        nullable=False, index=True)
    inventory_item_id = Column(Integer, ForeignKey('inventory_items.id'),
                               nullable=False, index=True)
    quantity_required = Column(Float, nullable=False)

    product = relationship('Product', back_populates='recipes')
    item = relationship('InventoryItem', back_populates='recipe_uses')


class ProductionOrder(db.Model):
    __tablename__ = 'production_orders'

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    planned_qty = Column(Integer, nullable=False)
    actual_qty = Column(Integer, default=0, nullable=False)
    status = Column(String(20), default='pending', nullable=False, index=True)
    date = Column(Date, default=date.today, nullable=False)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    product = relationship('Product', back_populates='production_orders')
    waste_records = relationship('ProductionWaste', back_populates='order',
                                 cascade='all, delete-orphan')

    @property
    def total_waste(self) -> int:
        return sum((w.quantity or 0) for w in self.waste_records)

    @property
    def waste_cost(self) -> float:
        """Cost of wasted units at the product's recipe cost per unit."""
        if not self.product:
            return 0.0
        return float(self.total_waste) * float(self.product.computed_cost or 0)


class ProductionWaste(db.Model):
    __tablename__ = 'production_waste'

    id = Column(Integer, primary_key=True, autoincrement=True)
    production_order_id = Column(Integer, ForeignKey('production_orders.id'),
                                 nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    reason = Column(Text)
    recorded_at = Column(DateTime, default=datetime.utcnow)

    order = relationship('ProductionOrder', back_populates='waste_records')


class StockMovement(db.Model):
    __tablename__ = 'stock_movements'

    id = Column(Integer, primary_key=True, autoincrement=True)
    inventory_item_id = Column(Integer, ForeignKey('inventory_items.id'),
                               nullable=False, index=True)
    type = Column(String(10), nullable=False)  # in / out
    quantity = Column(Float, nullable=False)
    reference_type = Column(String(40))
    reference_id = Column(Integer)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    item = relationship('InventoryItem', back_populates='movements')


# ---------------------------------------------------------------------------
# Sales, payments, purchases
# ---------------------------------------------------------------------------
class Sale(db.Model):
    __tablename__ = 'sales'

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey('customers.id'), index=True)
    user_id = Column(Integer, ForeignKey('users.id'), index=True)
    date = Column(Date, default=date.today, nullable=False, index=True)
    total = Column(Float, default=0, nullable=False)
    tax = Column(Float, default=0, nullable=False)
    discount = Column(Float, default=0, nullable=False)
    grand_total = Column(Float, default=0, nullable=False)
    payment_method = Column(String(40), default='cash')
    payment_status = Column(String(20), default='pending', index=True)
    status = Column(String(20), default='completed')
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    customer = relationship('Customer', back_populates='sales')
    user = relationship('User', back_populates='sales')
    items = relationship('SaleItem', back_populates='sale',
                          cascade='all, delete-orphan')
    payments = relationship('Payment', back_populates='sale')

    @property
    def total_paid(self) -> float:
        return float(sum((p.amount or 0) for p in self.payments))

    @property
    def balance_due(self) -> float:
        return float(self.grand_total or 0) - self.total_paid


class SaleItem(db.Model):
    __tablename__ = 'sales_items'

    id = Column(Integer, primary_key=True, autoincrement=True)
    sale_id = Column(Integer, ForeignKey('sales.id'), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    qty = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    total = Column(Float, nullable=False)

    sale = relationship('Sale', back_populates='items')
    product = relationship('Product', back_populates='sales_items')


class Payment(db.Model):
    __tablename__ = 'payments'

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey('customers.id'),
                         nullable=False, index=True)
    sale_id = Column(Integer, ForeignKey('sales.id'), index=True)
    amount = Column(Float, nullable=False)
    payment_method = Column(String(40), nullable=False)
    date = Column(Date, default=date.today, nullable=False)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    customer = relationship('Customer', back_populates='payments')
    sale = relationship('Sale', back_populates='payments')


class PurchaseOrder(db.Model):
    __tablename__ = 'purchase_orders'

    id = Column(Integer, primary_key=True, autoincrement=True)
    supplier_id = Column(Integer, ForeignKey('suppliers.id'),
                         nullable=False, index=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    date = Column(Date, default=date.today, nullable=False)
    expected_date = Column(Date)
    total = Column(Float, default=0, nullable=False)
    tax = Column(Float, default=0, nullable=False)
    grand_total = Column(Float, default=0, nullable=False)
    status = Column(String(20), default='pending', index=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    supplier = relationship('Supplier', back_populates='purchase_orders')
    items = relationship('PurchaseItem', back_populates='order',
                         cascade='all, delete-orphan')
    supplier_payments = relationship('SupplierPayment', back_populates='order')


class PurchaseItem(db.Model):
    __tablename__ = 'purchase_items'

    id = Column(Integer, primary_key=True, autoincrement=True)
    purchase_id = Column(Integer, ForeignKey('purchase_orders.id'),
                         nullable=False, index=True)
    inventory_item_id = Column(Integer, ForeignKey('inventory_items.id'),
                               nullable=False)
    qty = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    total = Column(Float, nullable=False)

    order = relationship('PurchaseOrder', back_populates='items')
    item = relationship('InventoryItem', back_populates='purchase_items')


class SupplierPayment(db.Model):
    __tablename__ = 'supplier_payments'

    id = Column(Integer, primary_key=True, autoincrement=True)
    supplier_id = Column(Integer, ForeignKey('suppliers.id'),
                         nullable=False, index=True)
    purchase_id = Column(Integer, ForeignKey('purchase_orders.id'), index=True)
    amount = Column(Float, nullable=False)
    payment_method = Column(String(40), nullable=False)
    date = Column(Date, default=date.today, nullable=False)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    supplier = relationship('Supplier', back_populates='supplier_payments')
    order = relationship('PurchaseOrder', back_populates='supplier_payments')


class CartItem(db.Model):
    __tablename__ = 'cart'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'),
                     nullable=False, index=True)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    qty = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Composite indexes for hot query paths (used by analytics services)
# ---------------------------------------------------------------------------
Index('ix_stock_movements_item_date', StockMovement.inventory_item_id,
      StockMovement.created_at)
Index('ix_sales_date_status', Sale.date, Sale.payment_status)
Index('ix_production_orders_date_status', ProductionOrder.date,
      ProductionOrder.status)
