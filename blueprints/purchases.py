"""
Bakery ERP System - Purchases Blueprint
Handles purchase orders and supplier management
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from database import get_db_connection
from datetime import datetime
from functools import wraps

purchases_bp = Blueprint('purchases', __name__, template_folder='templates/dashboard')

def staff_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if session.get('role') not in ['admin', 'manager']:
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@purchases_bp.route('/')
@staff_required
def view_purchases():
    """View all purchase orders"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get filter parameters
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    supplier_id = request.args.get('supplier_id', '')
    status = request.args.get('status', '')
    
    query = '''
        SELECT po.*, s.name as supplier_name
        FROM purchase_orders po
        JOIN suppliers s ON po.supplier_id = s.id
        WHERE 1=1
    '''
    params = []
    
    if date_from:
        query += ' AND po.date >= ?'
        params.append(date_from)
    if date_to:
        query += ' AND po.date <= ?'
        params.append(date_to)
    if supplier_id:
        query += ' AND po.supplier_id = ?'
        params.append(supplier_id)
    if status:
        query += ' AND po.status = ?'
        params.append(status)
    
    query += ' ORDER BY po.id DESC'
    
    cursor.execute(query, params)
    purchases = cursor.fetchall()
    
    # Get suppliers for filter
    cursor.execute('SELECT id, name FROM suppliers ORDER BY name')
    suppliers = cursor.fetchall()
    
    conn.close()
    
    return render_template('dashboard/purchases.html',
                         purchases=purchases,
                         suppliers=suppliers,
                         filters={
                             'date_from': date_from,
                             'date_to': date_to,
                             'supplier_id': supplier_id,
                             'status': status
                         })

@purchases_bp.route('/new', methods=['GET', 'POST'])
@staff_required
def new_purchase_order():
    """Create new purchase order"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        supplier_id = request.form.get('supplier_id', '')
        expected_date = request.form.get('expected_date', '')
        notes = request.form.get('notes', '')
        
        items = request.form.getlist('item_id[]')
        quantities = request.form.getlist('qty[]')
        prices = request.form.getlist('price[]')
        
        if not supplier_id:
            flash('Please select a supplier.', 'danger')
            cursor.execute('SELECT id, name FROM suppliers ORDER BY name')
            suppliers = cursor.fetchall()
            cursor.execute('SELECT id, name, unit FROM inventory_items ORDER BY name')
            inventory_items = cursor.fetchall()
            conn.close()
            return render_template('dashboard/new_purchase.html', 
                                suppliers=suppliers, 
                                inventory_items=inventory_items)
        
        if not items:
            flash('Please add at least one item.', 'danger')
            cursor.execute('SELECT id, name FROM suppliers ORDER BY name')
            suppliers = cursor.fetchall()
            cursor.execute('SELECT id, name, unit FROM inventory_items ORDER BY name')
            inventory_items = cursor.fetchall()
            conn.close()
            return render_template('dashboard/new_purchase.html', 
                                suppliers=suppliers, 
                                inventory_items=inventory_items)
        
        # Calculate totals
        subtotal = 0
        purchase_items = []
        
        for i in range(len(items)):
            item_id = items[i]
            qty = float(quantities[i])
            price = float(prices[i])
            total = qty * price
            subtotal += total
            purchase_items.append((item_id, qty, price, total))
        
        tax = subtotal * 0.08  # 8% tax
        grand_total = subtotal + tax
        
        # Create purchase order
        cursor.execute('''
            INSERT INTO purchase_orders (supplier_id, user_id, date, expected_date, total, tax, grand_total, status, notes)
            VALUES (?, ?, date('now'), ?, ?, ?, ?, 'pending', ?)
        ''', (supplier_id, session['user_id'], expected_date, subtotal, tax, grand_total, notes))
        
        purchase_id = cursor.lastrowid
        
        # Add purchase items
        for item in purchase_items:
            cursor.execute('''
                INSERT INTO purchase_items (purchase_id, inventory_item_id, qty, price, total)
                VALUES (?, ?, ?, ?, ?)
            ''', (purchase_id, item[0], item[1], item[2], item[3]))
        
        # Update supplier balance
        cursor.execute('UPDATE suppliers SET balance = balance + ? WHERE id = ?', 
                      (grand_total, supplier_id))
        
        conn.commit()
        flash('Purchase order created successfully!', 'success')
        conn.close()
        return redirect(url_for('purchases.view_purchases'))
    
    # GET request
    cursor.execute('SELECT id, name FROM suppliers ORDER BY name')
    suppliers = cursor.fetchall()
    cursor.execute('SELECT id, name, unit FROM inventory_items ORDER BY name')
    inventory_items = cursor.fetchall()
    conn.close()
    
    return render_template('dashboard/new_purchase.html', 
                         suppliers=suppliers, 
                         inventory_items=inventory_items)

@purchases_bp.route('/<int:purchase_id>')
@staff_required
def purchase_detail(purchase_id):
    """View purchase order details"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT po.*, s.name as supplier_name, s.contact_person, s.email, s.phone, s.address
        FROM purchase_orders po
        JOIN suppliers s ON po.supplier_id = s.id
        WHERE po.id = ?
    ''', (purchase_id,))
    purchase = cursor.fetchone()
    
    if not purchase:
        conn.close()
        flash('Purchase order not found.', 'danger')
        return redirect(url_for('purchases.view_purchases'))
    
    cursor.execute('''
        SELECT pi.*, i.name as item_name, i.unit
        FROM purchase_items pi
        JOIN inventory_items i ON pi.inventory_item_id = i.id
        WHERE pi.purchase_id = ?
    ''', (purchase_id,))
    items = cursor.fetchall()
    
    cursor.execute('''
        SELECT sp.* FROM supplier_payments sp WHERE sp.purchase_id = ?
    ''', (purchase_id,))
    payments = cursor.fetchall()
    
    conn.close()
    
    return render_template('dashboard/purchase_detail.html', 
                         purchase=purchase, 
                         items=items, 
                         payments=payments)

@purchases_bp.route('/<int:purchase_id>/receive', methods=['POST'])
@staff_required
def receive_purchase(purchase_id):
    """Receive purchase order and update inventory"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM purchase_orders WHERE id = ?', (purchase_id,))
    purchase = cursor.fetchone()
    
    if not purchase:
        conn.close()
        flash('Purchase order not found.', 'danger')
        return redirect(url_for('purchases.view_purchases'))
    
    if purchase['status'] == 'completed':
        conn.close()
        flash('This order has already been received.', 'warning')
        return redirect(url_for('purchases.purchase_detail', purchase_id=purchase_id))
    
    # Get purchase items
    cursor.execute('''
        SELECT pi.*, i.name as item_name
        FROM purchase_items pi
        JOIN inventory_items i ON pi.inventory_item_id = i.id
        WHERE pi.purchase_id = ?
    ''', (purchase_id,))
    items = cursor.fetchall()
    
    # Update inventory quantities
    for item in items:
        cursor.execute('''
            UPDATE inventory_items 
            SET quantity = quantity + ? 
            WHERE id = ?
        ''', (item['qty'], item['inventory_item_id']))
        
        # Record stock movement
        cursor.execute('''
            INSERT INTO stock_movements (inventory_item_id, type, quantity, reference_type, reference_id, notes)
            VALUES (?, 'in', ?, 'purchase', ?, ?)
        ''', (item['inventory_item_id'], item['qty'], purchase_id, 
              f'Received from PO #{purchase_id}'))
    
    # Update purchase order status
    cursor.execute('UPDATE purchase_orders SET status = ? WHERE id = ?', 
                  ('completed', purchase_id))
    
    conn.commit()
    conn.close()
    
    flash('Purchase order received and inventory updated!', 'success')
    return redirect(url_for('purchases.purchase_detail', purchase_id=purchase_id))

@purchases_bp.route('/<int:purchase_id>/payment', methods=['POST'])
@staff_required
def record_supplier_payment(purchase_id):
    """Record payment to supplier"""
    amount = float(request.form.get('amount', 0))
    payment_method = request.form.get('payment_method', 'bank_transfer')
    notes = request.form.get('notes', '')
    
    if amount <= 0:
        flash('Payment amount must be greater than 0.', 'danger')
        return redirect(url_for('purchases.purchase_detail', purchase_id=purchase_id))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM purchase_orders WHERE id = ?', (purchase_id,))
    purchase = cursor.fetchone()
    
    if not purchase:
        conn.close()
        flash('Purchase order not found.', 'danger')
        return redirect(url_for('purchases.view_purchases'))
    
    # Record payment
    cursor.execute('''
        INSERT INTO supplier_payments (supplier_id, purchase_id, amount, payment_method, notes)
        VALUES (?, ?, ?, ?, ?)
    ''', (purchase['supplier_id'], purchase_id, amount, payment_method, notes))
    
    # Update supplier balance
    cursor.execute('''
        UPDATE suppliers SET balance = balance - ? WHERE id = ?
    ''', (amount, purchase['supplier_id']))
    
    conn.commit()
    conn.close()
    
    flash('Payment recorded successfully!', 'success')
    return redirect(url_for('purchases.purchase_detail', purchase_id=purchase_id))

@purchases_bp.route('/suppliers')
@staff_required
def view_suppliers():
    """View all suppliers"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT s.*, 
               (SELECT COUNT(*) FROM purchase_orders WHERE supplier_id = s.id) as order_count,
               (SELECT COALESCE(SUM(grand_total), 0) FROM purchase_orders WHERE supplier_id = s.id) as total_purchases
        FROM suppliers s
        ORDER BY s.name
    ''')
    suppliers = cursor.fetchall()
    
    conn.close()
    
    return render_template('dashboard/suppliers.html', suppliers=suppliers)

@purchases_bp.route('/suppliers/new', methods=['POST'])
@staff_required
def add_supplier():
    """Add new supplier"""
    name = request.form.get('name', '').strip()
    contact_person = request.form.get('contact_person', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    address = request.form.get('address', '').strip()
    
    if not name:
        flash('Supplier name is required.', 'danger')
        return redirect(url_for('purchases.view_suppliers'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO suppliers (name, contact_person, email, phone, address)
        VALUES (?, ?, ?, ?, ?)
    ''', (name, contact_person, email, phone, address))
    
    conn.commit()
    conn.close()
    
    flash('Supplier added successfully!', 'success')
    return redirect(url_for('purchases.view_suppliers'))

@purchases_bp.route('/api/inventory/<int:item_id>')
@staff_required
def get_inventory_item(item_id):
    """API: Get inventory item details"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, unit, cost FROM inventory_items WHERE id = ?', (item_id,))
    item = cursor.fetchone()
    conn.close()
    
    if item:
        return jsonify({
            'id': item['id'],
            'name': item['name'],
            'unit': item['unit'],
            'cost': item['cost']
        })
    return jsonify({'error': 'Item not found'}), 404
