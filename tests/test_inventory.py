"""
Unit tests for InventoryService — the heart of the transactional layer.

Covers the three contracts:
  1. Stock OUT deducts the right quantity and writes a movement row.
  2. Stock OUT refuses to go negative.
  3. Receiving a purchase order increments inventory correctly.
"""
import pytest
from datetime import datetime, timedelta

from models import db, InventoryItem, StockMovement, PurchaseOrder, PurchaseItem
from services import InventoryService, InsufficientStockError


def test_record_out_movement_deducts_quantity(db_session):
    flour = db_session.query(InventoryItem).filter_by(name='Flour').one()
    start_qty = flour.quantity
    consumed = 5.0

    mv = InventoryService.record_movement(
        item_id=flour.id, movement_type='out', quantity=consumed,
        reference_type='production', reference_id=1, notes='test',
    )
    db_session.commit()

    assert flour.quantity == start_qty - consumed
    assert mv.type == 'out'
    assert mv.quantity == consumed
    assert mv.inventory_item_id == flour.id


def test_record_in_movement_increments_quantity(db_session):
    sugar = db_session.query(InventoryItem).filter_by(name='Sugar').one()
    start_qty = sugar.quantity
    InventoryService.record_movement(
        item_id=sugar.id, movement_type='in', quantity=10,
        reference_type='purchase', notes='restock',
    )
    db_session.commit()
    assert sugar.quantity == start_qty + 10


def test_out_movement_below_zero_raises(db_session):
    flour = db_session.query(InventoryItem).filter_by(name='Flour').one()
    with pytest.raises(InsufficientStockError) as exc:
        InventoryService.record_movement(
            item_id=flour.id, movement_type='out',
            quantity=flour.quantity + 100,
        )
    assert exc.value.available == flour.quantity
    assert exc.value.requested == flour.quantity + 100
    # Confirm DB state untouched
    db_session.rollback()
    assert flour.quantity == 100


def test_invalid_movement_type_rejected(db_session):
    flour = db_session.query(InventoryItem).filter_by(name='Flour').one()
    with pytest.raises(ValueError):
        InventoryService.record_movement(
            item_id=flour.id, movement_type='sideways', quantity=1,
        )


def test_unknown_item_rejected(db_session):
    with pytest.raises(ValueError):
        InventoryService.record_movement(
            item_id=999_999, movement_type='in', quantity=1,
        )


def test_complete_production_deducts_recipe(db_session):
    from models import Product, ProductionOrder
    bread = db_session.query(Product).filter_by(name='Sourdough').one()
    flour = db_session.query(InventoryItem).filter_by(name='Flour').one()
    sugar = db_session.query(InventoryItem).filter_by(name='Sugar').one()

    order = ProductionOrder(product_id=bread.id, planned_qty=10,
                            actual_qty=10, status='pending')
    db_session.add(order)
    db_session.commit()

    flour_before = flour.quantity
    sugar_before = sugar.quantity

    InventoryService.complete_production(order, actual_qty=10)
    db_session.commit()

    # 10 loaves * 0.5 kg flour = 5 kg
    assert flour.quantity == pytest.approx(flour_before - 5.0)
    # 10 loaves * 0.05 kg sugar = 0.5 kg
    assert sugar.quantity == pytest.approx(sugar_before - 0.5)
    assert order.status == 'completed'

    # 2 stock_movements (out) must have been written
    out_count = (db_session.query(StockMovement)
                 .filter_by(type='out', reference_type='production',
                            reference_id=order.id).count())
    assert out_count == 2


def test_complete_production_insufficient_raises(db_session):
    from models import Product, ProductionOrder
    bread = db_session.query(Product).filter_by(name='Sourdough').one()
    order = ProductionOrder(product_id=bread.id, planned_qty=10_000,
                            status='pending')
    db_session.add(order)
    db_session.commit()
    with pytest.raises(InsufficientStockError):
        InventoryService.complete_production(order, actual_qty=10_000)
    db_session.rollback()
    assert order.status == 'pending'


def test_complete_production_twice_raises(db_session):
    from models import Product, ProductionOrder
    bread = db_session.query(Product).filter_by(name='Sourdough').one()
    order = ProductionOrder(product_id=bread.id, planned_qty=2,
                            actual_qty=2, status='completed')
    db_session.add(order)
    db_session.commit()
    with pytest.raises(ValueError):
        InventoryService.complete_production(order, actual_qty=2)


def test_receive_purchase_increments_inventory(db_session):
    from models import Supplier, PurchaseOrder, PurchaseItem
    sup = db_session.query(Supplier).first()
    flour = db_session.query(InventoryItem).filter_by(name='Flour').one()
    sugar = db_session.query(InventoryItem).filter_by(name='Sugar').one()
    po = PurchaseOrder(supplier_id=sup.id, status='pending',
                       date=datetime.utcnow().date())
    db_session.add(po)
    db_session.flush()
    db.session.add_all([
        PurchaseItem(purchase_id=po.id, inventory_item_id=flour.id,
                     qty=50, price=2.5, total=125),
        PurchaseItem(purchase_id=po.id, inventory_item_id=sugar.id,
                     qty=20, price=2.0, total=40),
    ])
    db_session.commit()

    flour_before = flour.quantity
    sugar_before = sugar.quantity
    InventoryService.receive_purchase(po)
    db_session.commit()

    assert flour.quantity == flour_before + 50
    assert sugar.quantity == sugar_before + 20
    assert po.status == 'completed'
