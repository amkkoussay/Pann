"""
Bakery ERP System - Sales Blueprint
Handles sales management, invoices, and payments
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from database import get_db_connection
from datetime import datetime
from functools import wraps

sales_bp = Blueprint('sales', __name__, template_folder='templates/dashboard')

def staff_required(f):
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

@sales_bp.route('/')
@staff_required
def view_sales():
    """View all sales/invoices"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get filter parameters
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    customer_id = request.args.get('customer_id', '')
    payment_status = request.args.get('payment_status', '')
    
    query = '''
        SELECT s.*, c.name as customer_name, c.phone as customer_phone
        FROM sales s
        LEFT JOIN customers c ON s.customer_id = c.id
        WHERE 1=1
    '''
    params = []
    
    if date_from:
        query += ' AND s.date >= ?'
        params.append(date_from)
    if date_to:
        query += ' AND s.date <= ?'
        params.append(date_to)
    if customer_id:
        query += ' AND s.customer_id = ?'
        params.append(customer_id)
    if payment_status:
        query += ' AND s.payment_status = ?'
        params.append(payment_status)
    
    query += ' ORDER BY s.id DESC'
    
    cursor.execute(query, params)
    sales = cursor.fetchall()
    
    # Get customers for filter
    cursor.execute('SELECT id, name FROM customers ORDER BY name')
    customers = cursor.fetchall()
    
    conn.close()
    
    return render_template('dashboard/sales.html', 
                         sales=sales, 
                         customers=customers,
                         filters={
                             'date_from': date_from,
                             'date_to': date_to,
                             'customer_id': customer_id,
                             'payment_status': payment_status
                         })

@sales_bp.route('/new', methods=['GET', 'POST'])
@staff_required
def new_sale():
    """Create new sale/invoice"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        customer_id = request.form.get('customer_id', '')
        if not customer_id:
            customer_id = None
        
        items = request.form.getlist('product_id[]')
        quantities = request.form.getlist('qty[]')
        prices = request.form.getlist('price[]')
        
        if not items:
            flash('Please add at least one item.', 'danger')
            cursor.execute('SELECT id, name FROM customers ORDER BY name')
            customers = cursor.fetchall()
            cursor.execute('SELECT id, name, price FROM products WHERE is_active = 1 ORDER BY name')
            products = cursor.fetchall()
            conn.close()
            return render_template('dashboard/new_sale.html', customers=customers, products=products)
        
        # Calculate totals
        subtotal = 0
        sale_items = []
        
        for i in range(len(items)):
            product_id = items[i]
            qty = int(quantities[i])
            price = float(prices[i])
            total = qty * price
            subtotal += total
            sale_items.append((product_id, qty, price, total))
        
        tax_rate = 0.08  # 8% tax
        tax = subtotal * tax_rate
        grand_total = subtotal + tax
        
        # Create sale
        cursor.execute('''
            INSERT INTO sales (customer_id, user_id, date, total, tax, grand_total, payment_status)
            VALUES (?, ?, date('now'), ?, ?, ?, 'pending')
        ''', (customer_id, session['user_id'], subtotal, tax, grand_total))
        
        sale_id = cursor.lastrowid
        
        # Add sale items
        for item in sale_items:
            cursor.execute('''
                INSERT INTO sales_items (sale_id, product_id, qty, price, total)
                VALUES (?, ?, ?, ?, ?)
            ''', (sale_id, item[0], item[1], item[2], item[3]))
        
        conn.commit()
        flash('Sale created successfully!', 'success')
        conn.close()
        return redirect(url_for('sales.view_sales'))
    
    # GET request
    cursor.execute('SELECT id, name FROM customers ORDER BY name')
    customers = cursor.fetchall()
    cursor.execute('SELECT id, name, price FROM products WHERE is_active = 1 ORDER BY name')
    products = cursor.fetchall()
    conn.close()
    
    return render_template('dashboard/new_sale.html', customers=customers, products=products)

@sales_bp.route('/<int:sale_id>')
@staff_required
def sale_detail(sale_id):
    """View sale details"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT s.*, c.name as customer_name, c.email as customer_email, c.phone as customer_phone, c.address
        FROM sales s
        LEFT JOIN customers c ON s.customer_id = c.id
        WHERE s.id = ?
    ''', (sale_id,))
    sale = cursor.fetchone()
    
    if not sale:
        conn.close()
        flash('Sale not found.', 'danger')
        return redirect(url_for('sales.view_sales'))
    
    cursor.execute('''
        SELECT si.*, p.name as product_name
        FROM sales_items si
        JOIN products p ON si.product_id = p.id
        WHERE si.sale_id = ?
    ''', (sale_id,))
    items = cursor.fetchall()
    
    cursor.execute('''
        SELECT p.* FROM payments p WHERE p.sale_id = ?
    ''', (sale_id,))
    payments = cursor.fetchall()
    
    conn.close()
    
    return render_template('dashboard/sale_detail.html', sale=sale, items=items, payments=payments)

@sales_bp.route('/<int:sale_id>/payment', methods=['POST'])
@staff_required
def record_payment(sale_id):
    """Record payment for a sale"""
    amount = float(request.form.get('amount', 0))
    payment_method = request.form.get('payment_method', 'cash')
    notes = request.form.get('notes', '')
    
    if amount <= 0:
        flash('Payment amount must be greater than 0.', 'danger')
        return redirect(url_for('sales.sale_detail', sale_id=sale_id))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get sale details
    cursor.execute('SELECT * FROM sales WHERE id = ?', (sale_id,))
    sale = cursor.fetchone()
    
    if not sale:
        conn.close()
        flash('Sale not found.', 'danger')
        return redirect(url_for('sales.view_sales'))
    
    # Get total payments
    cursor.execute('SELECT COALESCE(SUM(amount), 0) as total FROM payments WHERE sale_id = ?', (sale_id,))
    total_paid = cursor.fetchone()['total'] or 0
    
    remaining = sale['grand_total'] - total_paid
    
    if amount > remaining:
        conn.close()
        flash(f'Payment amount exceeds remaining balance of ${remaining:.2f}.', 'danger')
        return redirect(url_for('sales.sale_detail', sale_id=sale_id))
    
    # Record payment
    cursor.execute('''
        INSERT INTO payments (customer_id, sale_id, amount, payment_method, notes)
        VALUES (?, ?, ?, ?, ?)
    ''', (sale['customer_id'], sale_id, amount, payment_method, notes))
    
    # Update sale payment status
    new_total_paid = total_paid + amount
    if new_total_paid >= sale['grand_total']:
        payment_status = 'paid'
    else:
        payment_status = 'partial'
    
    cursor.execute('UPDATE sales SET payment_status = ? WHERE id = ?', (payment_status, sale_id))
    
    # Update customer balance if exists
    if sale['customer_id']:
        cursor.execute('''
            UPDATE customers SET balance = balance - ? WHERE id = ?
        ''', (amount, sale['customer_id']))
    
    conn.commit()
    conn.close()
    
    flash('Payment recorded successfully!', 'success')
    return redirect(url_for('sales.sale_detail', sale_id=sale_id))

@sales_bp.route('/customers')
@staff_required
def customer_balance():
    """View customer balances"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT c.*, u.username, 
               COALESCE((SELECT SUM(grand_total) FROM sales WHERE customer_id = c.id AND payment_status != 'paid'), 0) as total_due
        FROM customers c
        LEFT JOIN users u ON c.user_id = u.id
        ORDER BY c.name
    ''')
    customers = cursor.fetchall()
    
    conn.close()
    
    return render_template('dashboard/customers.html', customers=customers)

@sales_bp.route('/customers/<int:customer_id>/statement')
@staff_required
def customer_statement(customer_id):
    """View customer statement"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM customers WHERE id = ?', (customer_id,))
    customer = cursor.fetchone()
    
    if not customer:
        conn.close()
        flash('Customer not found.', 'danger')
        return redirect(url_for('sales.customer_balance'))
    
    cursor.execute('''
        SELECT s.*, 
               (SELECT COALESCE(SUM(amount), 0) FROM payments WHERE sale_id = s.id) as paid_amount
        FROM sales s
        WHERE s.customer_id = ?
        ORDER BY s.date DESC
    ''', (customer_id,))
    sales = cursor.fetchall()
    
    cursor.execute('''
        SELECT p.*, s.id as sale_id
        FROM payments p
        LEFT JOIN sales s ON p.sale_id = s.id
        WHERE p.customer_id = ?
        ORDER BY p.date DESC
    ''', (customer_id,))
    payments = cursor.fetchall()
    
    conn.close()
    
    return render_template('dashboard/customer_statement.html', 
                         customer=customer, 
                         sales=sales, 
                         payments=payments)

@sales_bp.route('/api/products/<int:product_id>')
@staff_required
def get_product(product_id):
    """API: Get product details"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, price FROM products WHERE id = ?', (product_id,))
    product = cursor.fetchone()
    conn.close()
    
    if product:
        return jsonify({
            'id': product['id'],
            'name': product['name'],
            'price': product['price']
        })
    return jsonify({'error': 'Product not found'}), 404
