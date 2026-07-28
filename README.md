# Bakery ERP System

A complete bakery management system with ERP modules, customer portal,
login/signup, smart inventory predictions, real profitability analytics,
PDF/Excel exports, and a full SQLAlchemy ORM layer backed by an automated
pytest test suite (36 tests). Built with Flask and optimized for Termux
(Android) as well as standard Linux.

## What's new in v2.0

| Area | Before | After |
| --- | --- | --- |
| Inventory alerts | Static `WHERE quantity <= min_stock` | **Predictive** — avg daily consumption, days-until-stockout, urgency tiers, auto reorder qty based on fastest supplier lead time |
| Margin reporting | Stored `products.cost` (often stale) | **Real** — `SUM(recipe.qty * ingredient.cost)` per product + waste-cost attribution |
| Exports | None | **PDF** (customer statement, production invoice) + **Excel** (reorder, profitability) |
| Data layer | Raw `sqlite3` strings | **SQLAlchemy 2.x ORM** with typed models, relationships, and migration-ready schema |
| Testing | None | **36 pytest tests** covering inventory, BOM, smart reorder, profitability, exports |

## Features

### ERP modules
- **Sales Management** — invoices, payments, customer balances
- **Purchases Management** — purchase orders, supplier management, payments
- **Production Management** — production orders, recipes/BOM, waste recording
- **Inventory Management** — stock tracking, movements, low-stock alerts,
  **smart reorder predictions**

### Smart analytics (v2.0)
- **Smart Reorder** (`/analytics/reorder`) — predicts days-until-stockout
  per item from real `stock_movements` history, suggests a reorder
  quantity covering the supplier's lead time + a 7-day safety buffer,
  surfaces critical / soon / monitor buckets
- **Profitability** (`/analytics/profitability`) — for every product:
  recipe-driven cost, true margin, units sold, revenue, waste cost, and
  net profit. Surfaces loss-makers first and shows total waste cost for
  the selected window.
- **JSON API** for the analytics (`/analytics/api/reorder.json`) so the
  same predictions can power a dashboard widget, mobile app, or BI tool

### Exports (v2.0)
- `GET /analytics/statement/<customer_id>.pdf` — branded customer statement
- `GET /analytics/production/<order_id>.pdf` — production order invoice with
  BOM, totals, and waste breakdown
- `GET /analytics/reorder/export.xlsx` — full reorder workbook
- `GET /analytics/profitability/export.xlsx` — full profitability workbook

### Customer portal
- Product catalog, search & filter by category
- Shopping cart and checkout
- Order history
- Chat bot with predefined responses

### User management
- Secure password hashing (`werkzeug`)
- Role-based access (admin, manager, cashier, customer)
- Profile + change-password flows

## Tech stack

- **Backend** — Flask, Flask-SQLAlchemy 3, Flask-Migrate (Alembic)
- **ORM** — SQLAlchemy 2 with typed models in `models.py`
- **Database** — SQLite (file-based, single-file deploy)
- **PDF** — ReportLab
- **Excel** — OpenPyXL
- **Tests** — pytest (36 tests, in-memory SQLite per test)
- **Frontend** — HTML + CSS + Vanilla JS

## Project structure

```
pann/
├── app.py                      # Flask app factory + SQLAlchemy binding
├── config.py                   # Configuration settings
├── database.py                 # Legacy sqlite3 init + sample data
├── models.py                   # SQLAlchemy ORM (new)
├── services.py                 # Business logic (smart reorder, profit, inv)
├── exports.py                  # PDF + Excel generators (new)
├── requirements.txt
├── pytest.ini
├── database.db                 # SQLite file (created on first run)
├── blueprints/                 # Flask blueprints
│   ├── auth.py                 # Authentication
│   ├── dashboard.py            # Dashboard
│   ├── sales.py                # Sales
│   ├── purchases.py            # Purchases
│   ├── production.py           # Production
│   ├── inventory.py            # Inventory
│   ├── customer.py             # Customer portal
│   └── analytics.py            # NEW: smart reorder + profitability
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── dashboard/
│   │   ├── smart_reorder.html  # NEW
│   │   └── profitability.html  # NEW
│   ├── auth/
│   └── customer/
├── static/
│   ├── css/style.css
│   ├── js/
│   └── images/
└── tests/                      # NEW: pytest suite
    ├── conftest.py
    ├── test_inventory.py
    ├── test_bom.py
    ├── test_smart_reorder.py
    ├── test_profitability.py
    └── test_exports.py
```

## Installation

```bash
pip install -r requirements.txt
python app.py
```

Then open `http://localhost:5000`.

### Run the tests

```bash
python -m pytest tests/ -v
```

You should see `36 passed` in under 10 seconds.

## Default login credentials

| Role     | Username  | Password     |
|----------|-----------|--------------|
| Admin    | admin     | admin123     |
| Manager  | manager   | manager123   |
| Cashier  | cashier   | cashier123   |
| Customer | customer1 | customer123  |

The **Smart Reorder** and **Profitability** pages are visible to admin
and manager roles.

## Database schema (v2.0)

The schema is defined twice for compatibility:

- **Legacy** — raw `CREATE TABLE` in `database.py` (kept for the original
  raw-sqlite3 blueprints to keep working unchanged)
- **ORM** — typed SQLAlchemy models in `models.py`. They share the same
  database file; the new analytics blueprint uses the ORM exclusively.

New column in v2.0: `suppliers.lead_time_days` (used by the smart-reorder
predictor to choose the fastest supplier for each item).

## How the smart reorder works

`SmartInventoryService` (`services.py`) computes per item:

1. **avg_daily_consumption** = `SUM(out movements in last 30 days) / 30`
2. **days_until_stockout** = `current_quantity / avg_daily`
3. **preferred_supplier** = supplier with smallest `lead_time_days` among
   suppliers who actually supplied this item
4. **recommended_order_qty** = `avg_daily * (lead_time + 7-day safety)`
5. **urgency** = critical (≤ 3d) / soon (≤ 7d) / monitor (no history) / ok

## How profitability works

`ProfitabilityService` (`services.py`) computes per product:

1. **computed_cost** = `SUM(Recipe.qty * Ingredient.cost)` — the real
   cost-of-goods, not the stored `products.cost` field
2. **margin** = `price - computed_cost`
3. **units_sold** + **revenue** aggregated from `sales_items`
4. **waste_units** + **waste_cost** aggregated from `production_waste`
   joined to the product
5. **net_profit** = `margin * units_sold - waste_cost`

## Configuration

`config.py` controls the secret key, database path, product categories,
units, payment methods, and chatbot responses.

## License

MIT — feel free to use and modify.
