"""
Unit tests for SmartInventoryService — forecasting + reorder logic.
"""
import pytest
from datetime import datetime, timedelta

from models import db, InventoryItem, StockMovement
from services import SmartInventoryService


def _backdate_movements(db_session, item_id, daily_out, days=30):
    """Helper: insert `days` worth of 'out' movements at daily_out each."""
    base = datetime.utcnow()
    for d in range(days):
        ts = base - timedelta(days=days - d, hours=12)
        mv = StockMovement(
            inventory_item_id=item_id, type='out', quantity=daily_out,
            reference_type='production', reference_id=None,
            notes=f'day {d}', created_at=ts,
        )
        db_session.add(mv)
    db_session.commit()


def test_avg_daily_consumption(db_session):
    flour = db_session.query(InventoryItem).filter_by(name='Flour').one()
    _backdate_movements(db_session, flour.id, daily_out=10, days=30)
    svc = SmartInventoryService(window_days=30)
    # 30 * 10 / 30 = 10 (allow tiny rounding from datetime truncation)
    assert svc.avg_daily_consumption(flour.id) == pytest.approx(10.0, abs=0.5)


def test_avg_daily_consumption_ignores_inbound(db_session):
    flour = db_session.query(InventoryItem).filter_by(name='Flour').one()
    _backdate_movements(db_session, flour.id, daily_out=4, days=20)
    db_session.add(StockMovement(
        inventory_item_id=flour.id, type='in', quantity=999,
        created_at=datetime.utcnow(),
    ))
    db_session.commit()
    svc = SmartInventoryService(window_days=30)
    assert svc.avg_daily_consumption(flour.id) == pytest.approx(
        (20 * 4) / 30.0
    )


def test_days_until_stockout(db_session):
    flour = db_session.query(InventoryItem).filter_by(name='Flour').one()
    flour.quantity = 50
    db_session.commit()
    _backdate_movements(db_session, flour.id, daily_out=10, days=20)
    svc = SmartInventoryService(window_days=30)
    # avg=~6.67, days = 50/6.67 ≈ 7.5
    assert svc.days_until_stockout(flour) == pytest.approx(7.5, abs=0.5)


def test_days_until_stockout_no_history(db_session):
    """No outbound movements → None (we don't know)."""
    flour = db_session.query(InventoryItem).filter_by(name='Flour').one()
    svc = SmartInventoryService()
    assert svc.days_until_stockout(flour) is None


def test_urgency_thresholds():
    svc = SmartInventoryService()
    assert svc.urgency_for(1) == 'critical'
    assert svc.urgency_for(3) == 'critical'
    assert svc.urgency_for(4) == 'soon'
    assert svc.urgency_for(7) == 'soon'
    assert svc.urgency_for(10) == 'ok'
    assert svc.urgency_for(None) == 'monitor'


def test_reorder_suggestion_for_low_stock_item(db_session):
    """An item below min_stock with active demand must suggest a reorder."""
    from models import Supplier, PurchaseOrder, PurchaseItem
    flour = db_session.query(InventoryItem).filter_by(name='Flour').one()
    sup = db_session.query(Supplier).first()
    flour.quantity = 10  # below min_stock=20
    db_session.commit()
    _backdate_movements(db_session, flour.id, daily_out=5, days=20)

    # Record a prior purchase so a supplier is associated
    po = PurchaseOrder(supplier_id=sup.id, date=datetime.utcnow().date(),
                       status='completed')
    db_session.add(po); db_session.flush()
    db_session.add(PurchaseItem(purchase_id=po.id,
                                 inventory_item_id=flour.id,
                                 qty=10, price=2.5, total=25))
    db_session.commit()

    svc = SmartInventoryService(window_days=30)
    s = svc.analyze_item(flour)
    assert s.urgency in ('critical', 'soon')
    assert s.recommended_order_qty > 0
    assert s.preferred_supplier == sup.name
    assert s.lead_time_days == sup.lead_time_days


def test_reorder_no_history_returns_zero_suggestion(db_session):
    sugar = db_session.query(InventoryItem).filter_by(name='Sugar').one()
    sugar.quantity = 5  # below min_stock
    db_session.commit()
    svc = SmartInventoryService()
    s = svc.analyze_item(sugar)
    assert s.avg_daily_consumption == 0
    assert s.recommended_order_qty == 0
    assert s.days_until_stockout is None
    # No movement history → urgency reflects "monitor" but since the
    # item IS low stock, the dispatcher flips it to one of the alert
    # categories.
    assert s.urgency == 'monitor'


def test_recommended_reorder_qty_scales_with_lead_time():
    from models import InventoryItem
    svc = SmartInventoryService()
    item = InventoryItem(name='X', unit='kg', min_stock=10)
    q_short_lead = svc.recommended_reorder_qty(item, avg_daily=5,
                                                lead_time_days=1)
    q_long_lead = svc.recommended_reorder_qty(item, avg_daily=5,
                                               lead_time_days=10)
    assert q_long_lead > q_short_lead
    # Safety buffer of 7 days always added
    assert q_short_lead >= 5 * (1 + 7)
