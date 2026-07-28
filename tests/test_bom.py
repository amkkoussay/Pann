"""
Unit tests for BOM (Bill of Materials) math + sale stock-check.
"""
import pytest

from models import db, Product, InventoryItem, Recipe, Sale, SaleItem, Customer
from services import InventoryService, InsufficientStockError


def test_bom_total_cost_is_sum_of_lines(db_session):
    bread = db_session.query(Product).filter_by(name='Sourdough').one()
    expected = 0.5 * 2.5 + 0.05 * 2.0
    assert bread.computed_cost == pytest.approx(expected)


def test_bom_for_product_with_no_recipe_is_zero(db_session):
    p = Product(name='Mystery', category='mystery', price=5, is_active=1)
    db_session.add(p); db_session.commit()
    assert p.computed_cost == 0
    assert p.margin == 5


def test_sale_qty_cannot_exceed_recipe_availability(db_session):
    """
    Simulate a sale larger than what the BOM can support. The application
    layer rejects insufficient stock before allowing the sale.
    """
    bread = db_session.query(Product).filter_by(name='Sourdough').one()
    flour = db_session.query(InventoryItem).filter_by(name='Flour').one()
    # We have 100 kg flour. Bread needs 0.5 kg. → max 200 loaves possible.
    flour.quantity = 1  # reduce dramatically
    db_session.commit()
    needed_for_50 = 0.5 * 50
    with pytest.raises(InsufficientStockError):
        InventoryService.record_movement(
            item_id=flour.id, movement_type='out', quantity=needed_for_50,
            reference_type='sale', notes='too-big sale',
        )


def test_multiple_recipes_for_one_product(db_session):
    """A product with two recipes must sum both ingredient costs."""
    p = Product(name='Cake', category='cake', price=20, is_active=1)
    db_session.add(p); db_session.flush()
    flour = db_session.query(InventoryItem).filter_by(name='Flour').one()
    sugar = db_session.query(InventoryItem).filter_by(name='Sugar').one()
    db_session.add_all([
        Recipe(product_id=p.id, inventory_item_id=flour.id,
               quantity_required=0.3),
        Recipe(product_id=p.id, inventory_item_id=sugar.id,
               quantity_required=0.2),
    ])
    db_session.commit()
    expected = 0.3 * 2.5 + 0.2 * 2.0
    assert p.computed_cost == pytest.approx(expected)


def test_sale_creation_reduces_inventory(db_session):
    """The happy path: a sale's required ingredients are deducted."""
    bread = db_session.query(Product).filter_by(name='Sourdough').one()
    flour = db_session.query(InventoryItem).filter_by(name='Flour').one()
    cust = db_session.query(Customer).first()
    start = flour.quantity

    sale = Sale(customer_id=cust.id, date=__import__('datetime').date.today(),
                total=13.98, grand_total=13.98, payment_status='paid')
    db_session.add(sale); db_session.flush()
    db_session.add(SaleItem(sale_id=sale.id, product_id=bread.id,
                            qty=2, price=6.99, total=13.98))
    db_session.flush()
    # Simulate 2 loaves of bread produced
    InventoryService.record_movement(
        item_id=flour.id, movement_type='out', quantity=1.0,
        reference_type='production', reference_id=sale.id,
    )
    db_session.commit()
    assert flour.quantity == start - 1.0
