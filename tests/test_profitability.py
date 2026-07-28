"""
Unit tests for ProfitabilityService — true margin reporting + waste cost.
"""
import pytest
from datetime import datetime, date, timedelta

from models import (
    db, Product, InventoryItem, Recipe, Sale, SaleItem, Payment,
    ProductionOrder, ProductionWaste,
)
from services import ProfitabilityService


def test_computed_cost_sums_recipe_ingredients(db_session):
    bread = db_session.query(Product).filter_by(name='Sourdough').one()
    # 0.5 kg flour @ 2.5 + 0.05 kg sugar @ 2.0 = 1.25 + 0.1 = 1.35
    expected = 0.5 * 2.5 + 0.05 * 2.0
    assert bread.computed_cost == pytest.approx(expected)


def test_margin_is_price_minus_recipe_cost(db_session):
    bread = db_session.query(Product).filter_by(name='Sourdough').one()
    expected = 6.99 - (0.5 * 2.5 + 0.05 * 2.0)
    assert bread.margin == pytest.approx(expected)
    assert bread.margin_pct > 0


def test_profitability_handles_no_sales(db_session):
    bread = db_session.query(Product).filter_by(name='Sourdough').one()
    svc = ProfitabilityService()
    r = svc.analyze_product(bread)
    assert r.units_sold == 0
    assert r.revenue == 0
    assert r.net_profit == 0  # margin * 0 - waste
    assert r.computed_cost > 0


def test_profitability_counts_units_and_revenue(db_session):
    from models import Customer
    bread = db_session.query(Product).filter_by(name='Sourdough').one()
    cust = db_session.query(Customer).first()
    sale = Sale(customer_id=cust.id, date=date.today(),
                total=20.97, tax=1.68, grand_total=22.65,
                payment_status='paid')
    db_session.add(sale); db_session.flush()
    db_session.add(SaleItem(sale_id=sale.id, product_id=bread.id,
                            qty=3, price=6.99, total=20.97))
    db_session.commit()
    svc = ProfitabilityService()
    r = svc.analyze_product(bread)
    assert r.units_sold == 3
    assert r.revenue == pytest.approx(20.97)


def test_profitability_includes_waste_cost(db_session):
    from models import Customer
    bread = db_session.query(Product).filter_by(name='Sourdough').one()
    cust = db_session.query(Customer).first()
    # 1 sold, 5 wasted
    sale = Sale(customer_id=cust.id, date=date.today(),
                total=6.99, grand_total=6.99, payment_status='paid')
    db_session.add(sale); db_session.flush()
    db_session.add(SaleItem(sale_id=sale.id, product_id=bread.id,
                            qty=1, price=6.99, total=6.99))
    order = ProductionOrder(product_id=bread.id, planned_qty=10,
                             actual_qty=10, status='completed',
                             date=date.today())
    db_session.add(order); db_session.flush()
    db_session.add(ProductionWaste(production_order_id=order.id,
                                    quantity=5, reason='overbake'))
    db_session.commit()

    svc = ProfitabilityService()
    r = svc.analyze_product(bread)
    cost = 0.5 * 2.5 + 0.05 * 2.0
    assert r.waste_units == 5
    assert r.waste_cost == pytest.approx(5 * cost)
    # net = margin * 1 - waste_cost
    expected_net = (6.99 - cost) * 1 - 5 * cost
    assert r.net_profit == pytest.approx(expected_net)


def test_waste_window_filters_old_records(db_session):
    bread = db_session.query(Product).filter_by(name='Sourdough').one()
    order = ProductionOrder(product_id=bread.id, planned_qty=1, actual_qty=1,
                            status='completed', date=date.today())
    db_session.add(order); db_session.flush()
    old = ProductionWaste(production_order_id=order.id, quantity=2,
                          reason='ancient',
                          recorded_at=datetime.utcnow() - timedelta(days=400))
    new = ProductionWaste(production_order_id=order.id, quantity=1,
                          reason='recent',
                          recorded_at=datetime.utcnow())
    db_session.add_all([old, new]); db_session.commit()
    svc = ProfitabilityService(waste_window_days=30)
    r = svc.analyze_product(bread)
    assert r.waste_units == 1  # old one filtered out


def test_analyze_all_sorted_worst_first(db_session):
    svc = ProfitabilityService()
    results = svc.analyze_all()
    # Sort order: ascending margin → worst margin first
    margins = [r.margin for r in results]
    assert margins == sorted(margins)
