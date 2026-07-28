"""
Bakery ERP System - Dashboard Blueprint
Main dashboard with summary statistics
"""
from flask import Blueprint, render_template, session, redirect, url_for, flash
from database import get_db_connection, get_stats
from functools import wraps

dashboard_bp = Blueprint('dashboard', __name__, template_folder='templates/dashboard')

def staff_required(f):
    """Decorator to require staff role (admin, manager, cashier)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if session.get('role') not in ['admin', 'manager', 'cashier']:
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@dashboard_bp.route('/')
@staff_required
def home():
    """Dashboard home page with summary statistics"""
    stats = get_stats()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get recent sales
    cursor.execute('''
        SELECT s.id, s.date, s.grand_total, s.payment_status, c.name as customer_name
        FROM sales s
        LEFT JOIN customers c ON s.customer_id = c.id
        ORDER BY s.id DESC
        LIMIT 5
    ''')
    recent_sales = cursor.fetchall()
    
    # Get low stock items
    cursor.execute('''
        SELECT id, name, quantity, min_stock, unit
        FROM inventory_items
        WHERE quantity <= min_stock
        ORDER BY quantity ASC
        LIMIT 5
    ''')
    low_stock_items = cursor.fetchall()
    
    # Get pending production orders
    cursor.execute('''
        SELECT po.id, po.date, p.name as product_name, po.planned_qty, po.status
        FROM production_orders po
        JOIN products p ON po.product_id = p.id
        WHERE po.status = 'pending'
        ORDER BY po.date ASC
        LIMIT 5
    ''')
    pending_production = cursor.fetchall()
    
    # Get top selling products
    cursor.execute('''
        SELECT p.name, SUM(si.qty) as total_qty, SUM(si.total) as total_revenue
        FROM sales_items si
        JOIN products p ON si.product_id = p.id
        GROUP BY si.product_id
        ORDER BY total_qty DESC
        LIMIT 5
    ''')
    top_products = cursor.fetchall()
    
    # Get daily sales for chart (last 7 days)
    cursor.execute('''
        SELECT date, SUM(grand_total) as total
        FROM sales
        WHERE date >= date('now', '-7 days')
        GROUP BY date
        ORDER BY date ASC
    ''')
    daily_sales = cursor.fetchall()
    
    conn.close()
    
    return render_template('dashboard/index.html',
                         stats=stats,
                         recent_sales=recent_sales,
                         low_stock_items=low_stock_items,
                         pending_production=pending_production,
                         top_products=top_products,
                         daily_sales=daily_sales)

@dashboard_bp.route('/reports')
@staff_required
def reports():
    """Reports page"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Sales by month
    cursor.execute('''
        SELECT strftime('%Y-%m', date) as month, COUNT(*) as count, SUM(grand_total) as total
        FROM sales
        GROUP BY month
        ORDER BY month DESC
        LIMIT 12
    ''')
    monthly_sales = cursor.fetchall()
    
    # Sales by product category
    cursor.execute('''
        SELECT p.category, COUNT(*) as count, SUM(si.total) as total
        FROM sales_items si
        JOIN products p ON si.product_id = p.id
        GROUP BY p.category
        ORDER BY total DESC
    ''')
    sales_by_category = cursor.fetchall()
    
    # Inventory valuation
    cursor.execute('''
        SELECT SUM(quantity * cost) as total_value
        FROM inventory_items
    ''')
    inventory_value = cursor.fetchone()['total_value'] or 0
    
    conn.close()
    
    return render_template('dashboard/reports.html',
                         monthly_sales=monthly_sales,
                         sales_by_category=sales_by_category,
                         inventory_value=inventory_value)
