"""
Bakery ERP System - Database Module (Bridge)
SQLite database initialization and helper functions.

This module is preserved for backward compatibility with the original
blueprints that use raw sqlite3. The new analytics layer uses the
SQLAlchemy ORM (see `models.py`) which is initialized by the Flask app
factory and (for tests) by `tests/conftest.py`.
"""
import os
from datetime import datetime
from werkzeug.security import generate_password_hash
from config import DATABASE_PATH, PRODUCT_CATEGORIES, INVENTORY_TYPES, UNITS


def get_db_connection():
    """Get a legacy sqlite3 connection (row factory = sqlite3.Row)."""
    import sqlite3
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """
    Initialize the SQLite schema and seed sample data using the legacy
    schema. SQLAlchemy models (`models.py`) will discover these tables at
    runtime since they share the same file. We DO NOT use `db.create_all()`
    here so the seeded data and column names match the original blueprints.
    """
    if os.path.exists(DATABASE_PATH):
        os.remove(DATABASE_PATH)

    conn = get_db_connection()
    cursor = conn.cursor()

    # Create users table
    cursor.execute('''
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'customer',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
    ''')

    # Create customers table
    cursor.execute('''
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            phone TEXT,
            address TEXT,
            credit_limit REAL DEFAULT 0,
            balance REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Create suppliers table (now with lead_time_days for smart reorder)
    cursor.execute('''
        CREATE TABLE suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact_person TEXT,
            email TEXT,
            phone TEXT,
            address TEXT,
            lead_time_days INTEGER DEFAULT 3,
            balance REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create inventory_items table
    cursor.execute('''
        CREATE TABLE inventory_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            unit TEXT NOT NULL,
            quantity REAL DEFAULT 0,
            min_stock REAL DEFAULT 0,
            cost REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create products table
    cursor.execute('''
        CREATE TABLE products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            cost REAL DEFAULT 0,
            image_path TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create recipes/BOM table
    cursor.execute('''
        CREATE TABLE recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            inventory_item_id INTEGER NOT NULL,
            quantity_required REAL NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products (id),
            FOREIGN KEY (inventory_item_id) REFERENCES inventory_items (id)
        )
    ''')

    # Create production_orders table
    cursor.execute('''
        CREATE TABLE production_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            planned_qty INTEGER NOT NULL,
            actual_qty INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            date DATE DEFAULT CURRENT_DATE,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
    ''')

    # Create production_waste table
    cursor.execute('''
        CREATE TABLE production_waste (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            production_order_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            reason TEXT,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (production_order_id) REFERENCES production_orders (id)
        )
    ''')

    # Create sales table
    cursor.execute('''
        CREATE TABLE sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            user_id INTEGER,
            date DATE DEFAULT CURRENT_DATE,
            total REAL DEFAULT 0,
            tax REAL DEFAULT 0,
            discount REAL DEFAULT 0,
            grand_total REAL DEFAULT 0,
            payment_method TEXT DEFAULT 'cash',
            payment_status TEXT DEFAULT 'pending',
            status TEXT DEFAULT 'completed',
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Create sales_items table
    cursor.execute('''
        CREATE TABLE sales_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            qty INTEGER NOT NULL,
            price REAL NOT NULL,
            total REAL NOT NULL,
            FOREIGN KEY (sale_id) REFERENCES sales (id),
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
    ''')

    # Create payments table (for customer payments)
    cursor.execute('''
        CREATE TABLE payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            sale_id INTEGER,
            amount REAL NOT NULL,
            payment_method TEXT NOT NULL,
            date DATE DEFAULT CURRENT_DATE,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers (id),
            FOREIGN KEY (sale_id) REFERENCES sales (id)
        )
    ''')

    # Create purchase_orders table
    cursor.execute('''
        CREATE TABLE purchase_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER NOT NULL,
            user_id INTEGER,
            date DATE DEFAULT CURRENT_DATE,
            expected_date DATE,
            total REAL DEFAULT 0,
            tax REAL DEFAULT 0,
            grand_total REAL DEFAULT 0,
            status TEXT DEFAULT 'pending',
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (supplier_id) REFERENCES suppliers (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Create purchase_items table
    cursor.execute('''
        CREATE TABLE purchase_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            purchase_id INTEGER NOT NULL,
            inventory_item_id INTEGER NOT NULL,
            qty REAL NOT NULL,
            price REAL NOT NULL,
            total REAL NOT NULL,
            FOREIGN KEY (purchase_id) REFERENCES purchase_orders (id),
            FOREIGN KEY (inventory_item_id) REFERENCES inventory_items (id)
        )
    ''')

    # Create supplier_payments table
    cursor.execute('''
        CREATE TABLE supplier_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER NOT NULL,
            purchase_id INTEGER,
            amount REAL NOT NULL,
            payment_method TEXT NOT NULL,
            date DATE DEFAULT CURRENT_DATE,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (supplier_id) REFERENCES suppliers (id),
            FOREIGN KEY (purchase_id) REFERENCES purchase_orders (id)
        )
    ''')

    # Create stock_movements table
    cursor.execute('''
        CREATE TABLE stock_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inventory_item_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            quantity REAL NOT NULL,
            reference_type TEXT,
            reference_id INTEGER,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (inventory_item_id) REFERENCES inventory_items (id)
        )
    ''')

    # Create cart table
    cursor.execute('''
        CREATE TABLE cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            qty INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
    ''')

    # ---- Seed data ----
    admin_hash = generate_password_hash('admin123')
    cursor.execute('''
        INSERT INTO users (username, email, password_hash, role)
        VALUES (?, ?, ?, ?)
    ''', ('admin', 'admin@bakeryerp.com', admin_hash, 'admin'))

    sample_users = [
        ('manager', 'manager@bakeryerp.com',
         generate_password_hash('manager123'), 'manager'),
        ('cashier', 'cashier@bakeryerp.com',
         generate_password_hash('cashier123'), 'cashier'),
        ('customer1', 'customer1@email.com',
         generate_password_hash('customer123'), 'customer'),
    ]
    cursor.executemany('''
        INSERT INTO users (username, email, password_hash, role)
        VALUES (?, ?, ?, ?)
    ''', sample_users)

    cursor.execute('''
        INSERT INTO customers
            (user_id, name, email, phone, address, credit_limit)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (4, 'John Doe', 'customer1@email.com', '(555) 111-2222',
          '456 Customer Ave', 500))

    # suppliers now have lead_time_days (smart reorder uses this)
    suppliers = [
        ('Flour Mill Co.', 'John Smith', 'orders@flourmill.com',
         '(555) 222-3333', '789 Industrial Rd', 2, 0),
        ('Dairy Fresh Ltd.', 'Mary Johnson', 'sales@dairyfresh.com',
         '(555) 333-4444', '321 Farm Way', 1, 0),
        ('Sugar & Spices', 'Robert Brown', 'contact@sugarspices.com',
         '(555) 444-5555', '654 Spice Lane', 4, 0),
        ('Baking Supplies Inc.', 'Lisa Davis', 'info@bakingsupplies.com',
         '(555) 555-6666', '987 Supply St', 3, 0),
    ]
    cursor.executemany('''
        INSERT INTO suppliers
            (name, contact_person, email, phone, address,
             lead_time_days, balance)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', suppliers)

    inventory_items = [
        ('All-Purpose Flour', 'raw_material', 'kg', 500, 50, 2.5),
        ('Whole Wheat Flour', 'raw_material', 'kg', 200, 30, 3.0),
        ('Sugar', 'raw_material', 'kg', 150, 25, 2.0),
        ('Butter', 'raw_material', 'kg', 100, 20, 8.0),
        ('Eggs', 'raw_material', 'dozen', 50, 10, 4.5),
        ('Milk', 'raw_material', 'l', 80, 15, 3.5),
        ('Yeast', 'raw_material', 'g', 5000, 500, 0.05),
        ('Salt', 'raw_material', 'kg', 50, 10, 1.0),
        ('Chocolate', 'raw_material', 'kg', 30, 5, 15.0),
        ('Vanilla Extract', 'raw_material', 'ml', 500, 100, 0.5),
        ('Baking Powder', 'raw_material', 'g', 2000, 200, 0.03),
        ('Cinnamon', 'raw_material', 'g', 500, 100, 0.1),
        ('Bread Bags', 'packaging', 'pc', 1000, 200, 0.1),
        ('Cake Boxes', 'packaging', 'pc', 200, 50, 1.5),
        ('Paper Bags', 'packaging', 'pc', 500, 100, 0.2),
    ]
    cursor.executemany('''
        INSERT INTO inventory_items
            (name, type, unit, quantity, min_stock, cost)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', inventory_items)

    products = [
        ('Sourdough Bread', 'bread', 'Traditional sourdough bread', 6.99, 3.5),
        ('Whole Wheat Bread', 'bread', 'Healthy whole wheat bread', 5.99, 3.0),
        ('White Bread', 'bread', 'Classic white sandwich bread', 4.99, 2.5),
        ('French Baguette', 'bread', 'Authentic French baguette', 3.99, 2.0),
        ('Rye Bread', 'bread', 'Hearty rye bread', 5.49, 3.0),
        ('Plain Croissant', 'croissant', 'Buttery flaky croissant', 2.99, 1.5),
        ('Chocolate Croissant', 'croissant', 'Croissant w/ chocolate', 3.49, 1.8),
        ('Almond Croissant', 'croissant', 'Croissant w/ almond', 3.99, 2.0),
        ('Chocolate Cake', 'cake', 'Rich chocolate layer cake', 24.99, 15.0),
        ('Vanilla Cake', 'cake', 'Classic vanilla cake', 22.99, 14.0),
        ('Cheesecake', 'cake', 'NY-style cheesecake', 28.99, 18.0),
        ('Red Velvet Cake', 'cake', 'Red velvet w/ cream cheese', 26.99, 16.0),
        ('Apple Danish', 'pastry', 'Apple-filled Danish', 3.99, 2.0),
        ('Cream Puff', 'pastry', 'Vanilla cream puff', 2.49, 1.2),
        ('Fruit Tart', 'pastry', 'Fresh fruit tart', 4.99, 2.5),
        ('Chocolate Chip Cookie', 'cookie', 'Classic choc-chip', 1.99, 0.8),
        ('Oatmeal Raisin Cookie', 'cookie', 'Oatmeal raisin', 1.99, 0.8),
        ('Sugar Cookie', 'cookie', 'Decorated sugar', 2.49, 1.0),
        ('Macaron', 'cookie', 'French macaron', 2.99, 1.5),
        ('Blueberry Muffin', 'muffin', 'Blueberry muffin', 3.49, 1.8),
        ('Chocolate Muffin', 'muffin', 'Double chocolate', 3.49, 1.8),
        ('Banana Nut Muffin', 'muffin', 'Banana walnut', 3.49, 1.8),
        ('Glazed Donut', 'donut', 'Classic glazed', 1.99, 0.9),
        ('Chocolate Donut', 'donut', 'Chocolate frosted', 2.29, 1.0),
        ('Jelly Donut', 'donut', 'Jelly filled', 2.49, 1.2),
    ]
    cursor.executemany('''
        INSERT INTO products (name, category, description, price, cost)
        VALUES (?, ?, ?, ?, ?)
    ''', products)

    recipes = [
        # Sourdough (product 1)
        (1, 1, 0.5), (1, 6, 0.3), (1, 7, 10), (1, 8, 0.01),
        # Whole Wheat (2)
        (2, 2, 0.5), (2, 6, 0.3), (2, 7, 10), (2, 8, 0.01),
        # Plain Croissant (6)
        (6, 1, 0.3), (6, 4, 0.15), (6, 5, 0.5), (6, 7, 5),
        # Chocolate Cake (9)
        (9, 1, 0.4), (9, 3, 0.3), (9, 4, 0.2),
        (9, 5, 0.75), (9, 9, 0.15), (9, 10, 5),
    ]
    cursor.executemany('''
        INSERT INTO recipes (product_id, inventory_item_id, quantity_required)
        VALUES (?, ?, ?)
    ''', recipes)

    cursor.execute('''
        INSERT INTO sales (customer_id, user_id, date, total, tax,
                           grand_total, payment_method, payment_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (1, 3, datetime.now().strftime('%Y-%m-%d'),
          25.96, 2.08, 28.04, 'cash', 'paid'))

    sale_items = [
        (1, 1, 2, 6.99, 13.98),
        (1, 6, 4, 2.99, 11.96),
    ]
    cursor.executemany('''
        INSERT INTO sales_items (sale_id, product_id, qty, price, total)
        VALUES (?, ?, ?, ?, ?)
    ''', sale_items)

    cursor.execute('''
        INSERT INTO purchase_orders
            (supplier_id, user_id, date, total, grand_total, status)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (1, 1, datetime.now().strftime('%Y-%m-%d'),
          625.0, 625.0, 'completed'))

    purchase_items = [
        (1, 1, 100, 2.5, 250),
        (1, 2, 50, 3.0, 150),
        (1, 3, 50, 2.0, 100),
        (1, 4, 25, 8.0, 200),
    ]
    cursor.executemany('''
        INSERT INTO purchase_items
            (purchase_id, inventory_item_id, qty, price, total)
        VALUES (?, ?, ?, ?, ?)
    ''', purchase_items)

    cursor.execute('''
        INSERT INTO production_orders
            (product_id, planned_qty, actual_qty, status, date)
        VALUES (?, ?, ?, ?, ?)
    ''', (1, 50, 48, 'completed', datetime.now().strftime('%Y-%m-%d')))

    # A few more stock movements so the smart-reorder predictor has data
    # to work with. We backdate them across a 30-day window.
    base = datetime.utcnow()
    movements_data = []
    # 30 days of flour outflows averaging ~10 kg/day (for predictive demo)
    for d in range(30):
        ts = base - timedelta(days=29 - d, hours=12)
        movements_data.append((1, 'out', 10 + (d % 3), 'production', None,
                               f'Baked day {d+1}', ts.strftime('%Y-%m-%d %H:%M:%S')))
    # 30 days of sugar outflows averaging ~3 kg/day
    for d in range(30):
        ts = base - timedelta(days=29 - d, hours=10)
        movements_data.append((3, 'out', 3, 'production', None,
                               f'Baked day {d+1}', ts.strftime('%Y-%m-%d %H:%M:%S')))
    # Initial stock purchases (no backdate — these are "in" so net zero
    # for the day they're logged)
    movements_data.append((1, 'in', 500, 'initial', None,
                            'Initial flour stock',
                            base.strftime('%Y-%m-%d %H:%M:%S')))
    movements_data.append((3, 'in', 200, 'initial', None,
                            'Initial sugar stock',
                            base.strftime('%Y-%m-%d %H:%M:%S')))
    cursor.executemany('''
        INSERT INTO stock_movements
            (inventory_item_id, type, quantity, reference_type,
             reference_id, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', movements_data)

    # A small waste record so profitability has data to display
    cursor.execute('''
        INSERT INTO production_waste
            (production_order_id, quantity, reason)
        VALUES (?, ?, ?)
    ''', (1, 2, 'End-of-day leftovers'))

    conn.commit()
    conn.close()
    print("Database initialized successfully!")


# Tiny shim for backward compat (legacy code imported `timedelta` here)
from datetime import timedelta  # noqa: E402


def get_stats():
    """Get dashboard statistics (legacy helper)."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT COALESCE(SUM(grand_total), 0) as total
        FROM sales WHERE date = date('now')
    ''')
    today_sales = cursor.fetchone()['total']

    cursor.execute('''
        SELECT COALESCE(SUM(grand_total), 0) as total
        FROM sales WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
    ''')
    month_sales = cursor.fetchone()['total']

    cursor.execute('''
        SELECT COUNT(*) as count FROM inventory_items
        WHERE quantity <= min_stock
    ''')
    low_stock = cursor.fetchone()['count']

    cursor.execute('SELECT COUNT(*) as count FROM products WHERE is_active = 1')
    total_products = cursor.fetchone()['count']

    cursor.execute('''
        SELECT COUNT(*) as count FROM production_orders WHERE status = 'pending'
    ''')
    pending_orders = cursor.fetchone()['count']

    cursor.execute('SELECT COUNT(*) as count FROM customers')
    total_customers = cursor.fetchone()['count']

    cursor.execute('SELECT COALESCE(SUM(balance), 0) as total FROM customers')
    customer_balances = cursor.fetchone()['total']

    cursor.execute('SELECT COALESCE(SUM(balance), 0) as total FROM suppliers')
    supplier_balances = cursor.fetchone()['total']

    conn.close()

    return {
        'today_sales': today_sales,
        'month_sales': month_sales,
        'low_stock': low_stock,
        'total_products': total_products,
        'pending_orders': pending_orders,
        'total_customers': total_customers,
        'customer_balances': customer_balances,
        'supplier_balances': supplier_balances,
    }


if __name__ == '__main__':
    init_database()
