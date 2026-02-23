# app.py
import os
from flask import send_from_directory
from flask_cors import CORS
from app import create_app, db

# 1. Initialize the app using the factory pattern
app = create_app()

# --- DATABASE INITIALIZATION BLOCK ---
with app.app_context():
    try:
        # IMPORTANT: You MUST import your models here. 
        # If SQLAlchemy doesn't see them, it won't create the tables.
        from app.models import User, Farmer, Buyer, Animal, Order, Review, Wishlist, BargainSession, Dispute, Notification, PendingCheckout, EscrowRecord
        
        print("Registering models and creating tables...")
        db.create_all()
        print("✅ Database tables initialized successfully!")
    except Exception as e:
        print(f"❌ Database initialization error: {e}")
# --------------------------------------

# 2. Configure CORS
# Get origins from config and ensure it's a list
origins = app.config.get('ALLOWED_ORIGINS', [
    "http://localhost:5173",          # Vite Default
    "http://127.0.0.1:5173",         # Vite Alternative
    "http://localhost:3000",
    "http://localhost:5555",
    "https://farmart-com.onrender.com",
    "https://aglisten-armida-confarreate.ngrok-free.dev" # Ngrok Tunnel
])

# Ensure origins is a list
if isinstance(origins, str):
    origins = [o.strip() for o in origins.split(",")]

# Safaricom STK/B2C callbacks are server-to-server, so they aren't restricted by CORS,
# but your React/Frontend needs this to talk to your API.
CORS(
    app,
    supports_credentials=True,
    resources={
        r"/api/*": {
            "origins": origins,
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
            "allow_headers": [
                "Content-Type", 
                "Authorization", 
                "Accept", 
                "Origin", 
                "ngrok-skip-browser-warning",
                "X-Requested-With"
            ],
            "expose_headers": ["Content-Type", "Authorization"],
            "max_age": 86400
        }
    }
)

# 3. Static File Handling
static_uploads = os.path.join(os.path.dirname(__file__), "app", "static", "uploads")
if not os.path.exists(static_uploads):
    os.makedirs(static_uploads, exist_ok=True)

if __name__ == "__main__":
    # Use PORT from environment (for Render) or default to 5000
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

