"""
Bakery ERP System - Customer Blueprint
Handles customer portal, product catalog, cart, and chatbot
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from database import get_db_connection
from datetime import datetime
from functools import wraps
import random
import os

customer_bp = Blueprint('customer', __name__, template_folder='templates/customer')

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def customer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if session.get('role') != 'customer':
            flash('This page is for customers only.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@customer_bp.route('/browse')
def browse_products():
    """Browse product catalog"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get filter parameters
    category = request.args.get('category', '')
    search = request.args.get('search', '')
    
    query = 'SELECT * FROM products WHERE is_active = 1'
    params = []
    
    if category:
        query += ' AND category = ?'
        params.append(category)
    if search:
        query += ' AND (name LIKE ? OR description LIKE ?)'
        params.extend([f'%{search}%', f'%{search}%'])
    
    query += ' ORDER BY category, name'
    
    cursor.execute(query, params)
    products = cursor.fetchall()
    
    # Get categories for filter
    cursor.execute('SELECT DISTINCT category FROM products WHERE is_active = 1 ORDER BY category')
    categories = [row['category'] for row in cursor.fetchall()]
    
    # Get cart count if logged in
    cart_count = 0
    if 'user_id' in session:
        cursor.execute('SELECT SUM(qty) as count FROM cart WHERE user_id = ?', (session['user_id'],))
        result = cursor.fetchone()
        cart_count = result['count'] or 0
    
    conn.close()
    
    # Add random stock quantities for display
    products_with_stock = []
    for product in products:
        product_dict = dict(product)
        # Random stock between 5 and 50
        product_dict['stock'] = random.randint(5, 50)
        # Random image if not set
        if not product_dict.get('image_path'):
            product_dict['image_path'] = f"{product_dict['category']}_default.jpg"
        products_with_stock.append(product_dict)
    
    return render_template('customer/browse.html',
                         products=products_with_stock,
                         categories=categories,
                         cart_count=cart_count,
                         filters={
                             'category': category,
                             'search': search
                         })

@customer_bp.route('/product/<int:product_id>')
def product_detail(product_id):
    """View product details"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM products WHERE id = ? AND is_active = 1', (product_id,))
    product = cursor.fetchone()
    
    if not product:
        conn.close()
        flash('Product not found.', 'danger')
        return redirect(url_for('customer.browse_products'))
    
    # Get related products
    cursor.execute('''
        SELECT * FROM products 
        WHERE category = ? AND id != ? AND is_active = 1
        ORDER BY RANDOM()
        LIMIT 4
    ''', (product['category'], product_id))
    related = cursor.fetchall()
    
    conn.close()
    
    product_dict = dict(product)
    product_dict['stock'] = random.randint(5, 50)
    
    return render_template('customer/product_detail.html',
                         product=product_dict,
                         related_products=related)

@customer_bp.route('/cart')
@login_required
def view_cart():
    """View shopping cart"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT c.*, p.name, p.price, p.image_path, p.description
        FROM cart c
        JOIN products p ON c.product_id = p.id
        WHERE c.user_id = ?
    ''', (session['user_id'],))
    cart_items = cursor.fetchall()
    
    # Calculate totals
    subtotal = sum(item['price'] * item['qty'] for item in cart_items)
    tax = subtotal * 0.08
    total = subtotal + tax
    
    conn.close()
    
    return render_template('customer/cart.html',
                         cart_items=cart_items,
                         subtotal=subtotal,
                         tax=tax,
                         total=total)

@customer_bp.route('/cart/add', methods=['POST'])
@login_required
def add_to_cart():
    """Add item to cart"""
    product_id = request.form.get('product_id', '')
    qty = int(request.form.get('qty', 1))
    
    if not product_id:
        return jsonify({'success': False, 'message': 'Product not specified'})
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if product exists
    cursor.execute('SELECT id FROM products WHERE id = ? AND is_active = 1', (product_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': 'Product not found'})
    
    # Check if already in cart
    cursor.execute('''
        SELECT id, qty FROM cart WHERE user_id = ? AND product_id = ?
    ''', (session['user_id'], product_id))
    existing = cursor.fetchone()
    
    if existing:
        # Update quantity
        new_qty = existing['qty'] + qty
        cursor.execute('''
            UPDATE cart SET qty = ? WHERE id = ?
        ''', (new_qty, existing['id']))
    else:
        # Add new item
        cursor.execute('''
            INSERT INTO cart (user_id, product_id, qty)
            VALUES (?, ?, ?)
        ''', (session['user_id'], product_id, qty))
    
    # Get updated cart count
    cursor.execute('SELECT SUM(qty) as count FROM cart WHERE user_id = ?', (session['user_id'],))
    cart_count = cursor.fetchone()['count'] or 0
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'message': 'Added to cart!',
        'cart_count': cart_count
    })

@customer_bp.route('/cart/update', methods=['POST'])
@login_required
def update_cart():
    """Update cart item quantity"""
    cart_id = request.form.get('cart_id', '')
    qty = int(request.form.get('qty', 1))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if qty <= 0:
        cursor.execute('DELETE FROM cart WHERE id = ? AND user_id = ?', 
                      (cart_id, session['user_id']))
    else:
        cursor.execute('''
            UPDATE cart SET qty = ? WHERE id = ? AND user_id = ?
        ''', (qty, cart_id, session['user_id']))
    
    conn.commit()
    conn.close()
    
    flash('Cart updated!', 'success')
    return redirect(url_for('customer.view_cart'))

@customer_bp.route('/cart/remove/<int:cart_id>', methods=['POST'])
@login_required
def remove_from_cart(cart_id):
    """Remove item from cart"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM cart WHERE id = ? AND user_id = ?', 
                  (cart_id, session['user_id']))
    
    conn.commit()
    conn.close()
    
    flash('Item removed from cart.', 'info')
    return redirect(url_for('customer.view_cart'))

@customer_bp.route('/checkout', methods=['POST'])
@login_required
def place_order():
    """Place order from cart"""
    payment_method = request.form.get('payment_method', 'cash')
    notes = request.form.get('notes', '')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get cart items
    cursor.execute('''
        SELECT c.*, p.name, p.price
        FROM cart c
        JOIN products p ON c.product_id = p.id
        WHERE c.user_id = ?
    ''', (session['user_id'],))
    cart_items = cursor.fetchall()
    
    if not cart_items:
        conn.close()
        flash('Your cart is empty.', 'warning')
        return redirect(url_for('customer.view_cart'))
    
    # Calculate totals
    subtotal = sum(item['price'] * item['qty'] for item in cart_items)
    tax = subtotal * 0.08
    grand_total = subtotal + tax
    
    # Get customer_id
    cursor.execute('SELECT id FROM customers WHERE user_id = ?', (session['user_id'],))
    customer = cursor.fetchone()
    customer_id = customer['id'] if customer else None
    
    # Create sale
    cursor.execute('''
        INSERT INTO sales (customer_id, user_id, date, total, tax, grand_total, payment_method, payment_status, notes)
        VALUES (?, ?, date('now'), ?, ?, ?, ?, 'pending', ?)
    ''', (customer_id, session['user_id'], subtotal, tax, grand_total, payment_method, notes))
    
    sale_id = cursor.lastrowid
    
    # Add sale items
    for item in cart_items:
        cursor.execute('''
            INSERT INTO sales_items (sale_id, product_id, qty, price, total)
            VALUES (?, ?, ?, ?, ?)
        ''', (sale_id, item['product_id'], item['qty'], item['price'], item['price'] * item['qty']))
    
    # Clear cart
    cursor.execute('DELETE FROM cart WHERE user_id = ?', (session['user_id'],))
    
    conn.commit()
    conn.close()
    
    flash(f'Order placed successfully! Order #{sale_id}', 'success')
    return redirect(url_for('customer.order_confirmation', order_id=sale_id))

@customer_bp.route('/order/<int:order_id>/confirmation')
@login_required
def order_confirmation(order_id):
    """Order confirmation page"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT s.*, c.name as customer_name
        FROM sales s
        LEFT JOIN customers c ON s.customer_id = c.id
        WHERE s.id = ? AND (s.customer_id IN (SELECT id FROM customers WHERE user_id = ?) OR ?)
    ''', (order_id, session['user_id'], session.get('role') in ['admin', 'manager']))
    order = cursor.fetchone()
    
    if not order:
        conn.close()
        flash('Order not found.', 'danger')
        return redirect(url_for('customer.browse_products'))
    
    cursor.execute('''
        SELECT si.*, p.name as product_name
        FROM sales_items si
        JOIN products p ON si.product_id = p.id
        WHERE si.sale_id = ?
    ''', (order_id,))
    items = cursor.fetchall()
    
    conn.close()
    
    return render_template('customer/order_confirmation.html',
                         order=order,
                         items=items)

@customer_bp.route('/orders')
@login_required
def my_orders():
    """View customer's order history"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM customers WHERE user_id = ?', (session['user_id'],))
    customer = cursor.fetchone()
    
    if not customer:
        conn.close()
        flash('Customer record not found.', 'danger')
        return redirect(url_for('customer.browse_products'))
    
    cursor.execute('''
        SELECT s.*, 
               (SELECT SUM(qty) FROM sales_items WHERE sale_id = s.id) as item_count
        FROM sales s
        WHERE s.customer_id = ?
        ORDER BY s.id DESC
    ''', (customer['id'],))
    orders = cursor.fetchall()
    
    conn.close()
    
    return render_template('customer/orders.html', orders=orders)

@customer_bp.route('/chat')
def chat_interface():
    """Chatbot interface"""
    return render_template('customer/chat.html')

@customer_bp.route('/api/chat', methods=['POST'])
def chat_api():
    """API endpoint for chatbot"""
    from config import CHATBOT_RESPONSES, CHATBOT_KEYWORDS
    
    data = request.get_json()
    message = data.get('message', '').lower().strip()
    
    if not message:
        return jsonify({'response': 'Please type a message.'})
    
    # Try to find a matching response
    response = None
    
    # Check direct matches
    if message in CHATBOT_RESPONSES:
        response = CHATBOT_RESPONSES[message]
    else:
        # Check keyword matches
        for key, keywords in CHATBOT_KEYWORDS.items():
            if any(kw in message for kw in keywords):
                response = CHATBOT_RESPONSES.get(key)
                break
    
    # Check partial matches
    if not response:
        for key in CHATBOT_RESPONSES:
            if key in message:
                response = CHATBOT_RESPONSES[key]
                break
    
    # Default response
    if not response:
        response = CHATBOT_RESPONSES['default']
    
    return jsonify({'response': response})

@customer_bp.route('/api/cart/count')
@login_required
def cart_count():
    """API: Get cart item count"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT SUM(qty) as count FROM cart WHERE user_id = ?', (session['user_id'],))
    result = cursor.fetchone()
    conn.close()
    
    count = result['count'] or 0
    return jsonify({'count': count})
