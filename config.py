"""
Bakery ERP System - Configuration
Optimized for Termux (Android) environment
"""
import os

# Base directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Database configuration
DATABASE_PATH = os.path.join(BASE_DIR, 'database.db')
SQLALCHEMY_DATABASE_URI = f'sqlite:///{DATABASE_PATH}'
SQLALCHEMY_TRACK_MODIFICATIONS = False

# Flask configuration
SECRET_KEY = 'bakery-erp-secret-key-change-in-production'
SESSION_TYPE = 'filesystem'
PERMANENT_SESSION_LIFETIME = 3600  # 1 hour

# Upload configuration
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'images')
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size

# App configuration
DEBUG = True
HOST = '0.0.0.0'
PORT = 5000

# User roles
ROLES = {
    'admin': 'Administrator',
    'manager': 'Manager',
    'cashier': 'Cashier',
    'customer': 'Customer'
}

# Product categories
PRODUCT_CATEGORIES = [
    'bread',
    'croissant',
    'cake',
    'pastry',
    'cookie',
    'muffin',
    'donut'
]

# Inventory item types
INVENTORY_TYPES = [
    'raw_material',
    'finished_good',
    'packaging',
    'supply'
]

# Units of measurement
UNITS = [
    'kg',
    'g',
    'l',
    'ml',
    'pc',
    'dozen',
    'box',
    'bag'
]

# Payment methods
PAYMENT_METHODS = [
    'cash',
    'credit_card',
    'debit_card',
    'bank_transfer',
    'credit'
]

# Order statuses
ORDER_STATUSES = [
    'pending',
    'in_progress',
    'completed',
    'cancelled'
]

# Chatbot predefined responses
CHATBOT_RESPONSES = {
    'hi': 'Hello! Welcome to our bakery 🥖 How can I help you today?',
    'hello': 'Hi there! Welcome to our bakery! What can I do for you?',
    'hey': 'Hey! Welcome to our bakery! How may I assist you?',
    'hours': 'We are open from 6 AM to 8 PM every day. 🕕',
    'open': 'We are open from 6 AM to 8 PM every day, including weekends!',
    'close': 'We close at 8 PM every day.',
    'products': 'We have a variety of fresh products: bread, croissants, cakes, pastries, cookies, muffins, and donuts! 🍞🥐🎂',
    'bread': 'We offer sourdough, whole wheat, white bread, baguette, and rye bread. All baked fresh daily! 🍞',
    'croissant': 'Our croissants are buttery and flaky! We have plain, chocolate, and almond croissants. 🥐',
    'cake': 'We have chocolate cake, vanilla cake, cheesecake, and custom birthday cakes! 🎂',
    'pastry': 'Our pastries include danishes, turnovers, and cream puffs. Perfect with coffee! 🥮',
    'cookie': 'We bake chocolate chip, oatmeal raisin, sugar cookies, and macarons daily! 🍪',
    'price': 'Our prices vary by product. Bread starts at $3, croissants at $2.50, cakes from $15. Check our catalog for details!',
    'order': 'You can place an order through our online catalog! Just browse products and add to cart. 🛒',
    'delivery': 'We offer delivery within 5 miles for orders over $25. Delivery fee is $5. 🚚',
    'payment': 'We accept cash, credit cards, debit cards, and bank transfers. 💳',
    'contact': 'You can reach us at (555) 123-4567 or email us at hello@bakeryerp.com 📞',
    'phone': 'Our phone number is (555) 123-4567. Call us for orders! 📞',
    'email': 'You can email us at hello@bakeryerp.com 📧',
    'location': 'We are located at 123 Bakery Street, Sweet Town, ST 12345 📍',
    'address': '123 Bakery Street, Sweet Town, ST 12345',
    'vegan': 'We have vegan options! Ask about our vegan bread and pastries. 🌱',
    'gluten': 'We offer gluten-free bread and cookies. Please ask for availability. 🌾',
    'allergy': 'Please inform us of any allergies. We handle nuts, dairy, and gluten in our kitchen. ⚠️',
    'custom': 'Yes, we do custom orders for birthdays, weddings, and special events! 🎉',
    'birthday': 'We make custom birthday cakes! Order at least 3 days in advance. 🎂🎈',
    'wedding': 'We create beautiful wedding cakes! Contact us for consultation and pricing. 💒',
    'discount': 'We offer 10% discount on orders over $50! Check our promotions page. 💰',
    'loyalty': 'Join our loyalty program! Earn points with every purchase. ⭐',
    'fresh': 'All our products are baked fresh every morning! 🌅',
    'organic': 'We use organic flour and ingredients whenever possible. 🌿',
    'help': 'I can help you with: products, prices, hours, orders, delivery, and more! Just ask. 😊',
    'bye': 'Thank you for visiting! Have a sweet day! 👋',
    'goodbye': 'Goodbye! Come back soon! 🥖👋',
    'thanks': 'You\'re welcome! Enjoy our delicious baked goods! 🙏',
    'thank you': 'You\'re very welcome! Is there anything else I can help with?',
    'default': 'I\'m sorry, I didn\'t understand that. Try asking about: products, hours, prices, or orders. 🤔'
}

# Chatbot keywords mapping (for fuzzy matching)
CHATBOT_KEYWORDS = {
    'hi': ['hi', 'hey', 'hello', 'greetings'],
    'hours': ['hours', 'open', 'close', 'time', 'when'],
    'products': ['products', 'menu', 'items', 'food', 'baked'],
    'bread': ['bread', 'loaf', 'sourdough', 'baguette'],
    'croissant': ['croissant', 'crossaint', 'crescent'],
    'cake': ['cake', 'cakes', 'birthday cake'],
    'pastry': ['pastry', 'pastries', 'danish'],
    'cookie': ['cookie', 'cookies', 'biscuit', 'macaron'],
    'price': ['price', 'cost', 'how much', 'expensive', 'cheap'],
    'order': ['order', 'buy', 'purchase', 'cart'],
    'delivery': ['delivery', 'deliver', 'shipping', 'send'],
    'payment': ['payment', 'pay', 'card', 'cash'],
    'contact': ['contact', 'reach', 'call', 'phone', 'email'],
    'location': ['location', 'address', 'where', 'find'],
    'vegan': ['vegan', 'plant-based', 'dairy-free'],
    'gluten': ['gluten', 'gluten-free', 'celiac'],
    'custom': ['custom', 'special', 'personalized'],
    'discount': ['discount', 'sale', 'promo', 'deal', 'offer'],
    'help': ['help', 'assist', 'support', 'question']
}
