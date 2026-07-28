"""
Bakery ERP System - Production Blueprint
Handles production orders, recipes, and waste recording
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from database import get_db_connection
from datetime import datetime
from functools import wraps

production_bp = Blueprint('production', __name__, template_folder='templates/dashboard')

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

@production_bp.route('/')
@staff_required
def view_production():
    """View all production orders"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get filter parameters
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    status = request.args.get('status', '')
    
    query = '''
        SELECT po.*, p.name as product_name, p.category
        FROM production_orders po
        JOIN products p ON po.product_id = p.id
        WHERE 1=1
    '''
    params = []
    
    if date_from:
        query += ' AND po.date >= ?'
        params.append(date_from)
    if date_to:
        query += ' AND po.date <= ?'
        params.append(date_to)
    if status:
        query += ' AND po.status = ?'
        params.append(status)
    
    query += ' ORDER BY po.id DESC'
    
    cursor.execute(query, params)
    orders = cursor.fetchall()
    
    conn.close()
    
    return render_template('dashboard/production.html',
                         orders=orders,
                         filters={
                             'date_from': date_from,
                             'date_to': date_to,
                             'status': status
                         })

@production_bp.route('/recipes')
@staff_required
def view_recipes():
    """View all recipes (BOM)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT p.id, p.name as product_name, p.category, p.price,
               COUNT(r.id) as ingredient_count,
               SUM(r.quantity_required * i.cost) as total_cost
        FROM products p
        LEFT JOIN recipes r ON p.id = r.product_id
        LEFT JOIN inventory_items i ON r.inventory_item_id = i.id
        WHERE p.is_active = 1
        GROUP BY p.id
        ORDER BY p.name
    ''')
    recipes = cursor.fetchall()
    
    conn.close()
    
    return render_template('dashboard/recipes.html', recipes=recipes)

@production_bp.route('/recipes/<int:product_id>')
@staff_required
def recipe_detail(product_id):
    """View recipe details"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM products WHERE id = ?', (product_id,))
    product = cursor.fetchone()
    
    if not product:
        conn.close()
        flash('Product not found.', 'danger')
        return redirect(url_for('production.view_recipes'))
    
    cursor.execute('''
        SELECT r.*, i.name as item_name, i.unit, i.cost,
               (r.quantity_required * i.cost) as item_cost
        FROM recipes r
        JOIN inventory_items i ON r.inventory_item_id = i.id
        WHERE r.product_id = ?
    ''', (product_id,))
    ingredients = cursor.fetchall()
    
    cursor.execute('SELECT id, name, unit FROM inventory_items ORDER BY name')
    inventory_items = cursor.fetchall()
    
    conn.close()
    
    # Calculate total cost
    total_cost = sum(i['item_cost'] for i in ingredients) if ingredients else 0
    
    return render_template('dashboard/recipe_detail.html',
                         product=product,
                         ingredients=ingredients,
                         inventory_items=inventory_items,
                         total_cost=total_cost)

@production_bp.route('/recipes/<int:product_id>/add-ingredient', methods=['POST'])
@staff_required
def add_ingredient(product_id):
    """Add ingredient to recipe"""
    item_id = request.form.get('item_id', '')
    quantity = float(request.form.get('quantity', 0))
    
    if not item_id or quantity <= 0:
        flash('Please select an item and enter a valid quantity.', 'danger')
        return redirect(url_for('production.recipe_detail', product_id=product_id))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if ingredient already exists
    cursor.execute('''
        SELECT id FROM recipes WHERE product_id = ? AND inventory_item_id = ?
    ''', (product_id, item_id))
    
    if cursor.fetchone():
        # Update existing
        cursor.execute('''
            UPDATE recipes SET quantity_required = ? 
            WHERE product_id = ? AND inventory_item_id = ?
        ''', (quantity, product_id, item_id))
    else:
        # Add new
        cursor.execute('''
            INSERT INTO recipes (product_id, inventory_item_id, quantity_required)
            VALUES (?, ?, ?)
        ''', (product_id, item_id, quantity))
    
    conn.commit()
    conn.close()
    
    flash('Ingredient added to recipe!', 'success')
    return redirect(url_for('production.recipe_detail', product_id=product_id))

@production_bp.route('/recipes/<int:product_id>/remove-ingredient/<int:ingredient_id>', methods=['POST'])
@staff_required
def remove_ingredient(product_id, ingredient_id):
    """Remove ingredient from recipe"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM recipes WHERE id = ?', (ingredient_id,))
    conn.commit()
    conn.close()
    
    flash('Ingredient removed from recipe.', 'info')
    return redirect(url_for('production.recipe_detail', product_id=product_id))

@production_bp.route('/new', methods=['GET', 'POST'])
@staff_required
def new_production_order():
    """Create new production order"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        product_id = request.form.get('product_id', '')
        planned_qty = int(request.form.get('planned_qty', 0))
        notes = request.form.get('notes', '')
        
        if not product_id or planned_qty <= 0:
            flash('Please select a product and enter a valid quantity.', 'danger')
            cursor.execute('SELECT id, name FROM products WHERE is_active = 1 ORDER BY name')
            products = cursor.fetchall()
            conn.close()
            return render_template('dashboard/new_production.html', products=products)
        
        # Check if enough ingredients are available
        cursor.execute('''
            SELECT r.*, i.name as item_name, i.quantity as available_qty, i.unit
            FROM recipes r
            JOIN inventory_items i ON r.inventory_item_id = i.id
            WHERE r.product_id = ?
        ''', (product_id,))
        ingredients = cursor.fetchall()
        
        insufficient = []
        for ing in ingredients:
            required = ing['quantity_required'] * planned_qty
            if ing['available_qty'] < required:
                insufficient.append(f"{ing['item_name']} (need {required} {ing['unit']}, have {ing['available_qty']})")
        
        if insufficient:
            flash('Insufficient ingredients: ' + ', '.join(insufficient), 'danger')
            cursor.execute('SELECT id, name FROM products WHERE is_active = 1 ORDER BY name')
            products = cursor.fetchall()
            conn.close()
            return render_template('dashboard/new_production.html', products=products)
        
        # Create production order
        cursor.execute('''
            INSERT INTO production_orders (product_id, planned_qty, status, date, notes)
            VALUES (?, ?, 'pending', date('now'), ?)
        ''', (product_id, planned_qty, notes))
        
        conn.commit()
        flash('Production order created successfully!', 'success')
        conn.close()
        return redirect(url_for('production.view_production'))
    
    # GET request
    cursor.execute('SELECT id, name FROM products WHERE is_active = 1 ORDER BY name')
    products = cursor.fetchall()
    conn.close()
    
    return render_template('dashboard/new_production.html', products=products)

@production_bp.route('/<int:order_id>/complete', methods=['POST'])
@staff_required
def complete_production(order_id):
    """Complete production order and update inventory"""
    actual_qty = int(request.form.get('actual_qty', 0))
    
    if actual_qty < 0:
        flash('Actual quantity cannot be negative.', 'danger')
        return redirect(url_for('production.view_production'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT po.*, p.name as product_name
        FROM production_orders po
        JOIN products p ON po.product_id = p.id
        WHERE po.id = ?
    ''', (order_id,))
    order = cursor.fetchone()
    
    if not order:
        conn.close()
        flash('Production order not found.', 'danger')
        return redirect(url_for('production.view_production'))
    
    if order['status'] == 'completed':
        conn.close()
        flash('This order has already been completed.', 'warning')
        return redirect(url_for('production.view_production'))
    
    # Get recipe ingredients
    cursor.execute('''
        SELECT r.*, i.name as item_name
        FROM recipes r
        JOIN inventory_items i ON r.inventory_item_id = i.id
        WHERE r.product_id = ?
    ''', (order['product_id'],))
    ingredients = cursor.fetchall()
    
    # Deduct ingredients from inventory
    for ing in ingredients:
        qty_needed = ing['quantity_required'] * order['planned_qty']
        cursor.execute('''
            UPDATE inventory_items 
            SET quantity = quantity - ? 
            WHERE id = ?
        ''', (qty_needed, ing['inventory_item_id']))
        
        # Record stock movement
        cursor.execute('''
            INSERT INTO stock_movements (inventory_item_id, type, quantity, reference_type, reference_id, notes)
            VALUES (?, 'out', ?, 'production', ?, ?)
        ''', (ing['inventory_item_id'], qty_needed, order_id, 
              f'Used in production #{order_id}'))
    
    # Update production order
    cursor.execute('''
        UPDATE production_orders 
        SET status = 'completed', actual_qty = ?
        WHERE id = ?
    ''', (actual_qty, order_id))
    
    conn.commit()
    conn.close()
    
    flash('Production completed successfully!', 'success')
    return redirect(url_for('production.view_production'))

@production_bp.route('/<int:order_id>/waste', methods=['POST'])
@staff_required
def record_waste(order_id):
    """Record production waste"""
    quantity = int(request.form.get('quantity', 0))
    reason = request.form.get('reason', '')
    
    if quantity <= 0:
        flash('Waste quantity must be greater than 0.', 'danger')
        return redirect(url_for('production.view_production'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM production_orders WHERE id = ?', (order_id,))
    order = cursor.fetchone()
    
    if not order:
        conn.close()
        flash('Production order not found.', 'danger')
        return redirect(url_for('production.view_production'))
    
    # Record waste
    cursor.execute('''
        INSERT INTO production_waste (production_order_id, quantity, reason)
        VALUES (?, ?, ?)
    ''', (order_id, quantity, reason))
    
    conn.commit()
    conn.close()
    
    flash('Waste recorded successfully.', 'info')
    return redirect(url_for('production.view_production'))

@production_bp.route('/api/check-ingredients/<int:product_id>')
@staff_required
def check_ingredients(product_id):
    """API: Check available ingredients for a product"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT r.*, i.name as item_name, i.quantity as available_qty, i.unit
        FROM recipes r
        JOIN inventory_items i ON r.inventory_item_id = i.id
        WHERE r.product_id = ?
    ''', (product_id,))
    ingredients = cursor.fetchall()
    
    conn.close()
    
    result = []
    for ing in ingredients:
        result.append({
            'item_name': ing['item_name'],
            'required_per_unit': ing['quantity_required'],
            'available': ing['available_qty'],
            'unit': ing['unit']
        })
    
    return jsonify(result)
