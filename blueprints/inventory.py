"""
Bakery ERP System - Inventory Blueprint
Handles inventory management and stock movements
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from database import get_db_connection
from datetime import datetime
from functools import wraps

inventory_bp = Blueprint('inventory', __name__, template_folder='templates/dashboard')

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

@inventory_bp.route('/')
@staff_required
def view_inventory():
    """View all inventory items"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get filter parameters
    item_type = request.args.get('type', '')
    low_stock = request.args.get('low_stock', '')
    search = request.args.get('search', '')
    
    query = 'SELECT * FROM inventory_items WHERE 1=1'
    params = []
    
    if item_type:
        query += ' AND type = ?'
        params.append(item_type)
    if low_stock:
        query += ' AND quantity <= min_stock'
    if search:
        query += ' AND name LIKE ?'
        params.append(f'%{search}%')
    
    query += ' ORDER BY name'
    
    cursor.execute(query, params)
    items = cursor.fetchall()
    
    # Get inventory value
    cursor.execute('SELECT SUM(quantity * cost) as total_value FROM inventory_items')
    total_value = cursor.fetchone()['total_value'] or 0
    
    # Get low stock count
    cursor.execute('SELECT COUNT(*) as count FROM inventory_items WHERE quantity <= min_stock')
    low_stock_count = cursor.fetchone()['count']
    
    conn.close()
    
    return render_template('dashboard/inventory.html',
                         items=items,
                         total_value=total_value,
                         low_stock_count=low_stock_count,
                         filters={
                             'type': item_type,
                             'low_stock': low_stock,
                             'search': search
                         })

@inventory_bp.route('/add', methods=['POST'])
@staff_required
def add_item():
    """Add new inventory item"""
    name = request.form.get('name', '').strip()
    item_type = request.form.get('type', '')
    unit = request.form.get('unit', '')
    quantity = float(request.form.get('quantity', 0))
    min_stock = float(request.form.get('min_stock', 0))
    cost = float(request.form.get('cost', 0))
    
    if not name or not item_type or not unit:
        flash('Please fill in all required fields.', 'danger')
        return redirect(url_for('inventory.view_inventory'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO inventory_items (name, type, unit, quantity, min_stock, cost)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (name, item_type, unit, quantity, min_stock, cost))
    
    item_id = cursor.lastrowid
    
    # Record initial stock movement if quantity > 0
    if quantity > 0:
        cursor.execute('''
            INSERT INTO stock_movements (inventory_item_id, type, quantity, reference_type, notes)
            VALUES (?, 'in', ?, 'initial', ?)
        ''', (item_id, quantity, 'Initial stock'))
    
    conn.commit()
    conn.close()
    
    flash('Inventory item added successfully!', 'success')
    return redirect(url_for('inventory.view_inventory'))

@inventory_bp.route('/<int:item_id>/edit', methods=['POST'])
@staff_required
def edit_item(item_id):
    """Edit inventory item"""
    name = request.form.get('name', '').strip()
    item_type = request.form.get('type', '')
    unit = request.form.get('unit', '')
    min_stock = float(request.form.get('min_stock', 0))
    cost = float(request.form.get('cost', 0))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE inventory_items 
        SET name = ?, type = ?, unit = ?, min_stock = ?, cost = ?
        WHERE id = ?
    ''', (name, item_type, unit, min_stock, cost, item_id))
    
    conn.commit()
    conn.close()
    
    flash('Inventory item updated successfully!', 'success')
    return redirect(url_for('inventory.view_inventory'))

@inventory_bp.route('/<int:item_id>')
@staff_required
def item_detail(item_id):
    """View inventory item details"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM inventory_items WHERE id = ?', (item_id,))
    item = cursor.fetchone()
    
    if not item:
        conn.close()
        flash('Item not found.', 'danger')
        return redirect(url_for('inventory.view_inventory'))
    
    # Get stock movements
    cursor.execute('''
        SELECT * FROM stock_movements 
        WHERE inventory_item_id = ?
        ORDER BY created_at DESC
        LIMIT 50
    ''', (item_id,))
    movements = cursor.fetchall()
    
    # Get products using this item
    cursor.execute('''
        SELECT p.id, p.name, r.quantity_required
        FROM recipes r
        JOIN products p ON r.product_id = p.id
        WHERE r.inventory_item_id = ?
    ''', (item_id,))
    used_in_products = cursor.fetchall()
    
    conn.close()
    
    return render_template('dashboard/inventory_detail.html',
                         item=item,
                         movements=movements,
                         used_in_products=used_in_products)

@inventory_bp.route('/movement', methods=['POST'])
@staff_required
def record_stock_movement():
    """Record stock movement (in/out)"""
    item_id = request.form.get('item_id', '')
    movement_type = request.form.get('type', '')
    quantity = float(request.form.get('quantity', 0))
    notes = request.form.get('notes', '')
    
    if not item_id or not movement_type or quantity <= 0:
        flash('Please fill in all required fields.', 'danger')
        return redirect(url_for('inventory.view_inventory'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT quantity FROM inventory_items WHERE id = ?', (item_id,))
    item = cursor.fetchone()
    
    if not item:
        conn.close()
        flash('Item not found.', 'danger')
        return redirect(url_for('inventory.view_inventory'))
    
    # Update inventory quantity
    if movement_type == 'in':
        new_qty = item['quantity'] + quantity
    else:  # out
        if item['quantity'] < quantity:
            conn.close()
            flash('Insufficient stock for this movement.', 'danger')
            return redirect(url_for('inventory.view_inventory'))
        new_qty = item['quantity'] - quantity
    
    cursor.execute('''
        UPDATE inventory_items SET quantity = ? WHERE id = ?
    ''', (new_qty, item_id))
    
    # Record movement
    cursor.execute('''
        INSERT INTO stock_movements (inventory_item_id, type, quantity, notes)
        VALUES (?, ?, ?, ?)
    ''', (item_id, movement_type, quantity, notes))
    
    conn.commit()
    conn.close()
    
    flash(f'Stock movement recorded successfully! New quantity: {new_qty}', 'success')
    return redirect(url_for('inventory.view_inventory'))

@inventory_bp.route('/adjust', methods=['POST'])
@staff_required
def adjust_stock():
    """Adjust stock quantity (inventory count)"""
    item_id = request.form.get('item_id', '')
    new_quantity = float(request.form.get('new_quantity', 0))
    reason = request.form.get('reason', '')
    
    if not item_id:
        flash('Item not specified.', 'danger')
        return redirect(url_for('inventory.view_inventory'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT quantity FROM inventory_items WHERE id = ?', (item_id,))
    item = cursor.fetchone()
    
    if not item:
        conn.close()
        flash('Item not found.', 'danger')
        return redirect(url_for('inventory.view_inventory'))
    
    old_quantity = item['quantity']
    difference = new_quantity - old_quantity
    
    cursor.execute('''
        UPDATE inventory_items SET quantity = ? WHERE id = ?
    ''', (new_quantity, item_id))
    
    # Record adjustment
    movement_type = 'in' if difference > 0 else 'out'
    cursor.execute('''
        INSERT INTO stock_movements (inventory_item_id, type, quantity, notes)
        VALUES (?, ?, ?, ?)
    ''', (item_id, movement_type, abs(difference), f'Inventory adjustment: {reason}'))
    
    conn.commit()
    conn.close()
    
    flash(f'Stock adjusted from {old_quantity} to {new_quantity}', 'success')
    return redirect(url_for('inventory.item_detail', item_id=item_id))

@inventory_bp.route('/report')
@staff_required
def inventory_report():
    """Inventory reports"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Summary by type
    cursor.execute('''
        SELECT type, COUNT(*) as count, SUM(quantity * cost) as value
        FROM inventory_items
        GROUP BY type
    ''')
    summary_by_type = cursor.fetchall()
    
    # Low stock items
    cursor.execute('''
        SELECT * FROM inventory_items
        WHERE quantity <= min_stock
        ORDER BY quantity ASC
    ''')
    low_stock_items = cursor.fetchall()
    
    # Recent movements
    cursor.execute('''
        SELECT sm.*, i.name as item_name
        FROM stock_movements sm
        JOIN inventory_items i ON sm.inventory_item_id = i.id
        ORDER BY sm.created_at DESC
        LIMIT 50
    ''')
    recent_movements = cursor.fetchall()
    
    # Total valuation
    cursor.execute('''
        SELECT SUM(quantity * cost) as total_value,
               COUNT(*) as total_items
        FROM inventory_items
    ''')
    valuation = cursor.fetchone()
    
    conn.close()
    
    return render_template('dashboard/inventory_report.html',
                         summary_by_type=summary_by_type,
                         low_stock_items=low_stock_items,
                         recent_movements=recent_movements,
                         valuation=valuation)

@inventory_bp.route('/api/items')
@staff_required
def api_items():
    """API: Get all inventory items"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, unit, quantity FROM inventory_items ORDER BY name')
    items = cursor.fetchall()
    conn.close()
    
    return jsonify([{
        'id': item['id'],
        'name': item['name'],
        'unit': item['unit'],
        'quantity': item['quantity']
    } for item in items])
