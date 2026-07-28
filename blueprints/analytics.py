"""
Bakery ERP System - Analytics Blueprint
Smart dashboards: predictive reorder + profitability + exports.
Mounted under /analytics/ and uses the new SQLAlchemy models.
"""
from flask import Blueprint, render_template, request, redirect, url_for, \
    flash, session, send_file, abort, jsonify
from functools import wraps

from database import get_db_connection  # legacy for some lookups
from models import db, Customer, Product
from services import (
    SmartInventoryService, ProfitabilityService, InventoryService,
    InsufficientStockError,
)
from exports import (
    customer_statement_pdf, production_order_invoice_pdf,
    profitability_xlsx, reorder_suggestions_xlsx,
)

analytics_bp = Blueprint('analytics', __name__, template_folder='templates/dashboard')


def staff_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if session.get('role') not in ('admin', 'manager'):
            flash('Manager or admin access required.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Smart reorder page
# ---------------------------------------------------------------------------
@analytics_bp.route('/reorder')
@staff_required
def smart_reorder():
    """Predictive reorder dashboard."""
    svc = SmartInventoryService(
        window_days=int(request.args.get('window', 30))
    )
    suggestions = svc.analyze_all()
    # Sort by urgency then days_until_stockout (None last)
    urgency_rank = {'critical': 0, 'soon': 1, 'monitor': 2, 'ok': 3}
    suggestions.sort(key=lambda s: (
        urgency_rank.get(s.urgency, 9),
        s.days_until_stockout if s.days_until_stockout is not None else 1e9,
    ))
    summary = {
        'critical': sum(1 for s in suggestions if s.urgency == 'critical'),
        'soon': sum(1 for s in suggestions if s.urgency == 'soon'),
        'monitor': sum(1 for s in suggestions if s.urgency == 'monitor'),
        'total': len(suggestions),
    }
    return render_template(
        'dashboard/smart_reorder.html',
        suggestions=suggestions,
        summary=summary,
        window=svc.window_days,
    )


@analytics_bp.route('/reorder/export.xlsx')
@staff_required
def smart_reorder_xlsx():
    svc = SmartInventoryService()
    buf = reorder_suggestions_xlsx(svc.analyze_all())
    return send_file(
        buf, as_attachment=True,
        download_name='reorder_suggestions.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@analytics_bp.route('/api/reorder.json')
@staff_required
def smart_reorder_json():
    """JSON endpoint for the dashboard widgets / external integrations."""
    svc = SmartInventoryService()
    return jsonify([s.to_dict() for s in svc.analyze_all()])


# ---------------------------------------------------------------------------
# Profitability page
# ---------------------------------------------------------------------------
@analytics_bp.route('/profitability')
@staff_required
def profitability():
    days = request.args.get('days')
    days = int(days) if days and days.isdigit() else None
    svc = ProfitabilityService(waste_window_days=days)
    summaries = svc.analyze_all()
    losers = [s for s in summaries if s.margin < 0]
    total_waste_cost = svc.total_waste_cost()
    totals = {
        'revenue': sum(s.revenue for s in summaries),
        'net_profit': sum(s.net_profit for s in summaries),
        'units_sold': sum(s.units_sold for s in summaries),
        'waste_cost': total_waste_cost,
    }
    return render_template(
        'dashboard/profitability.html',
        summaries=summaries,
        losers=losers,
        totals=totals,
        days=days,
    )


@analytics_bp.route('/profitability/export.xlsx')
@staff_required
def profitability_xlsx_export():
    days = request.args.get('days')
    days = int(days) if days and days.isdigit() else None
    svc = ProfitabilityService(waste_window_days=days)
    buf = profitability_xlsx(svc.analyze_all())
    return send_file(
        buf, as_attachment=True,
        download_name='profitability.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


# ---------------------------------------------------------------------------
# PDF exports
# ---------------------------------------------------------------------------
@analytics_bp.route('/statement/<int:customer_id>.pdf')
@staff_required
def customer_statement_pdf_export(customer_id):
    try:
        buf = customer_statement_pdf(customer_id)
    except ValueError:
        abort(404)
    customer = db.session.get(Customer, customer_id)
    fname = f"statement_{customer.name.replace(' ', '_')}.pdf" \
        if customer else f"statement_{customer_id}.pdf"
    return send_file(buf, as_attachment=True, download_name=fname,
                     mimetype='application/pdf')


@analytics_bp.route('/production/<int:order_id>.pdf')
@staff_required
def production_invoice_pdf_export(order_id):
    try:
        buf = production_order_invoice_pdf(order_id)
    except ValueError:
        abort(404)
    return send_file(buf, as_attachment=True,
                     download_name=f'production_{order_id}.pdf',
                     mimetype='application/pdf')
