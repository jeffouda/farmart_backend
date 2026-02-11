# wsgi.py
from app import create_app

# Create the Flask app instance
# for production ready
app = create_app()
