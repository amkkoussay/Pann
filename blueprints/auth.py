"""
Bakery ERP System - Authentication Blueprint
Handles login, signup, and logout functionality
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash, generate_password_hash
from database import get_db_connection
from config import ROLES

auth_bp = Blueprint('auth', __name__, template_folder='templates/auth')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        # Validation
        if not username or not password:
            flash('Please enter both username and password.', 'danger')
            return render_template('auth/login.html')
        
        # Check user in database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, username, email, password_hash, role, is_active 
            FROM users 
            WHERE username = ?
        ''', (username,))
        user = cursor.fetchone()
        conn.close()
        
        if user is None:
            flash('Invalid username or password.', 'danger')
            return render_template('auth/login.html')
        
        if not user['is_active']:
            flash('Your account has been deactivated. Please contact admin.', 'danger')
            return render_template('auth/login.html')
        
        if check_password_hash(user['password_hash'], password):
            # Login successful
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['email'] = user['email']
            session['role'] = user['role']
            
            flash(f'Welcome back, {user["username"]}!', 'success')
            
            # Redirect based on role
            if user['role'] == 'customer':
                return redirect(url_for('customer.browse_products'))

            else:
                return redirect(url_for('dashboard.home'))
        else:
            flash('Invalid username or password.', 'danger')
    
    return render_template('auth/login.html')

@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    """Handle user registration"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        
        # Validation
        errors = []
        
        if not username:
            errors.append('Username is required.')
        elif len(username) < 3:
            errors.append('Username must be at least 3 characters.')
        elif not username.isalnum():
            errors.append('Username can only contain letters and numbers.')
        
        if not email:
            errors.append('Email is required.')
        elif '@' not in email or '.' not in email:
            errors.append('Please enter a valid email address.')
        
        if not password:
            errors.append('Password is required.')
        elif len(password) < 6:
            errors.append('Password must be at least 6 characters.')
        
        if password != confirm_password:
            errors.append('Passwords do not match.')
        
        if not full_name:
            errors.append('Full name is required.')
        
        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('auth/signup.html')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if username exists
        cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
        if cursor.fetchone():
            conn.close()
            flash('Username already exists. Please choose another.', 'danger')
            return render_template('auth/signup.html')
        
        # Check if email exists
        cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
        if cursor.fetchone():
            conn.close()
            flash('Email already registered. Please use another email or login.', 'danger')
            return render_template('auth/signup.html')
        
        # Create new user
        password_hash = generate_password_hash(password)
        try:
            cursor.execute('''
                INSERT INTO users (username, email, password_hash, role)
                VALUES (?, ?, ?, ?)
            ''', (username, email, password_hash, 'customer'))
            
            user_id = cursor.lastrowid
            
            # Create customer record
            cursor.execute('''
                INSERT INTO customers (user_id, name, email, phone, address, credit_limit)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, full_name, email, phone, address, 500))
            
            conn.commit()
            
            flash('Account created successfully! Please login.', 'success')
            return redirect(url_for('auth.login'))
            
        except Exception as e:
            conn.rollback()
            flash('An error occurred. Please try again.', 'danger')
            print(f"Signup error: {e}")
        finally:
            conn.close()
    
    return render_template('auth/signup.html')

@auth_bp.route('/logout')
def logout():
    """Handle user logout"""
    # Clear session
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('index'))

@auth_bp.route('/profile')
def profile():
    """User profile page"""
    if 'user_id' not in session:
        flash('Please login to view your profile.', 'warning')
        return redirect(url_for('auth.login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.*, c.name, c.phone, c.address, c.credit_limit, c.balance
        FROM users u
        LEFT JOIN customers c ON u.id = c.user_id
        WHERE u.id = ?
    ''', (session['user_id'],))
    user = cursor.fetchone()
    conn.close()
    
    if user is None:
        flash('User not found.', 'danger')
        return redirect(url_for('index'))
    
    return render_template('auth/profile.html', user=user)

@auth_bp.route('/change-password', methods=['POST'])
def change_password():
    """Change user password"""
    if 'user_id' not in session:
        flash('Please login to change your password.', 'warning')
        return redirect(url_for('auth.login'))
    
    current_password = request.form.get('current_password', '').strip()
    new_password = request.form.get('new_password', '').strip()
    confirm_password = request.form.get('confirm_password', '').strip()
    
    if not current_password or not new_password or not confirm_password:
        flash('All fields are required.', 'danger')
        return redirect(url_for('auth.profile'))
    
    if new_password != confirm_password:
        flash('New passwords do not match.', 'danger')
        return redirect(url_for('auth.profile'))
    
    if len(new_password) < 6:
        flash('New password must be at least 6 characters.', 'danger')
        return redirect(url_for('auth.profile'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Verify current password
    cursor.execute('SELECT password_hash FROM users WHERE id = ?', (session['user_id'],))
    user = cursor.fetchone()
    
    if not user or not check_password_hash(user['password_hash'], current_password):
        conn.close()
        flash('Current password is incorrect.', 'danger')
        return redirect(url_for('auth.profile'))
    
    # Update password
    new_hash = generate_password_hash(new_password)
    cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?', 
                   (new_hash, session['user_id']))
    conn.commit()
    conn.close()
    
    flash('Password changed successfully!', 'success')
    return redirect(url_for('auth.profile'))
