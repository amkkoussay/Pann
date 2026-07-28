"""
Bakery ERP System - Main Application
Flask-based ERP for bakery management with smart inventory predictions,
profitability analytics, and PDF/Excel exports.
"""
import os
from functools import wraps
from flask import (
    Flask, render_template, redirect, url_for, flash, session, request
)

from config import (
    SECRET_KEY, DEBUG, HOST, PORT, UPLOAD_FOLDER, MAX_CONTENT_LENGTH,
    DATABASE_PATH,
)

# Legacy blueprints (raw sqlite3)
from blueprints.auth import auth_bp
from blueprints.dashboard import dashboard_bp
from blueprints.sales import sales_bp
from blueprints.purchases import purchases_bp
from blueprints.production import production_bp
from blueprints.inventory import inventory_bp
from blueprints.customer import customer_bp

# New analytics blueprint (SQLAlchemy-backed)
from blueprints.analytics import analytics_bp

# SQLAlchemy models
from models import db


def create_app():
    app = Flask(__name__)

    # --- Flask config ---
    app.secret_key = SECRET_KEY
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DATABASE_PATH}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # --- Bind SQLAlchemy ---
    db.init_app(app)

    # --- Register blueprints ---
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(dashboard_bp, url_prefix='/dashboard')
    app.register_blueprint(sales_bp, url_prefix='/sales')
    app.register_blueprint(purchases_bp, url_prefix='/purchases')
    app.register_blueprint(production_bp, url_prefix='/production')
    app.register_blueprint(inventory_bp, url_prefix='/inventory')
    app.register_blueprint(customer_bp, url_prefix='/customer')
    app.register_blueprint(analytics_bp, url_prefix='/analytics')

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    return app


# App instance (module-level so `flask run` and tests both work)
app = create_app()


# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


# Role required decorator
def role_required(roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please login to access this page.', 'warning')
                return redirect(url_for('auth.login'))
            if session.get('role') not in roles:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorator
    return decorator


# Home route
@app.route('/')
def index():
    if 'user_id' in session:
        if session.get('role') == 'customer':
            return redirect(url_for('customer.browse_products'))
        return redirect(url_for('dashboard.home'))
    return render_template('index.html')


# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    flash('Page not found.', 'danger')
    return redirect(url_for('index'))


@app.errorhandler(500)
def internal_error(error):
    flash('An internal error occurred.', 'danger')
    return redirect(url_for('index'))


# Template filters
@app.template_filter('format_currency')
def format_currency(value):
    if value is None:
        return '$0.00'
    return '${:,.2f}'.format(float(value))


@app.template_filter('format_date')
def format_date(value):
    if value is None:
        return ''
    return value


# Context processor
@app.context_processor
def inject_globals():
    return {
        'app_name': 'BakeryERP',
        'app_version': '2.0.0',
        'current_year': 2026,
    }


# Initialize database on first request
@app.before_request
def init_db_on_first_request():
    if not os.path.exists(DATABASE_PATH):
        from database import init_database
        init_database()


# Main entry point
if __name__ == '__main__':
    if not os.path.exists(DATABASE_PATH):
        from database import init_database
        init_database()

    print("=" * 50)
    print("Bakery ERP System v2.0")
    print("=" * 50)
    print(f"Running on http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop")
    print("=" * 50)
    app.run(host=HOST, port=PORT, debug=DEBUG)
