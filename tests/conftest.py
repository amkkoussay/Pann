"""
Pytest fixtures: build a fresh in-memory SQLite database for every test
and provide a Flask test client + convenience helpers.
"""
import os
import sys
import tempfile
import pytest

# Make the project root importable so `import models` etc. work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from models import (
    db, User, Customer, Supplier, InventoryItem, Product, Recipe,
    ProductionOrder, ProductionWaste, StockMovement,
    Sale, SaleItem, Payment, PurchaseOrder, PurchaseItem,
)


@pytest.fixture
def app():
    """A Flask app bound to a throwaway SQLite file."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test'
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['WTF_CSRF_ENABLED'] = False

    db.init_app(app)
    with app.app_context():
        db.create_all()
        # Minimal seed data the tests rely on
        from werkzeug.security import generate_password_hash
        admin = User(username='admin', email='a@b.c', role='admin')
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.flush()
        c = Customer(user_id=admin.id, name='Test Customer',
                     email='c@b.c', credit_limit=500)
        sup = Supplier(name='Test Supplier', lead_time_days=2)
        flour = InventoryItem(name='Flour', type='raw_material',
                              unit='kg', quantity=100, min_stock=20, cost=2.5)
        sugar = InventoryItem(name='Sugar', type='raw_material',
                              unit='kg', quantity=50, min_stock=10, cost=2.0)
        db.session.add_all([c, sup, flour, sugar])
        db.session.flush()
        bread = Product(name='Sourdough', category='bread',
                        price=6.99, cost=0, is_active=1)
        db.session.add(bread)
        db.session.flush()
        db.session.add_all([
            Recipe(product_id=bread.id, inventory_item_id=flour.id,
                   quantity_required=0.5),
            Recipe(product_id=bread.id, inventory_item_id=sugar.id,
                   quantity_required=0.05),
        ])
        db.session.commit()

    yield app

    with app.app_context():
        db.session.remove()
        db.engine.dispose()
    os.unlink(path)


@pytest.fixture
def db_session(app):
    with app.app_context():
        yield db.session


@pytest.fixture
def client(app):
    return app.test_client()
