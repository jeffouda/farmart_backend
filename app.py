# app.py
from app import create_app, db
from flask_cors import CORS
import os

# 1. Create the app instance
app = create_app()

# --- DATABASE INITIALIZATION BLOCK ---
with app.app_context():
    try:
        # IMPORTANT: Import models here so SQLAlchemy registers them
        from app.models import User, Animal, Farmer, Buyer, Order, Review  # Add all your models
        
        print("Starting database table creation...")
        db.create_all()
        print("✅ Database tables initialized successfully!")
    except Exception as e:
        print(f"❌ Database initialization error: {e}")
# --------------------------------------

# 2. Configure CORS
# Using .get() prevents crashes if the environment variable is missing
allowed_origins = app.config.get('ALLOWED_ORIGINS', "https://farmart-com.onrender.com")

CORS(
    app,
    supports_credentials=True,
    resources={
        r"/api/*": {
            "origins": [allowed_origins, "http://localhost:5173"],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
            "allow_headers": ["Content-Type", "Authorization", "Accept", "Origin"],
            "supports_credentials": True
        }
    }
)

# 3. Static File Handling
static_uploads = os.path.join(os.path.dirname(__file__), "app", "static", "uploads")
if not os.path.exists(static_uploads):
    os.makedirs(static_uploads, exist_ok=True)

@app.route("/static/uploads/<path:filename>")
def serve_upload(filename):
    """Serve uploaded image files."""
    from flask import send_from_directory
    return send_from_directory(static_uploads, filename)

if __name__ == "__main__":
    # Render uses the PORT environment variable
    port = int(os.environ.get("PORT", 5555))
    app.run(host="0.0.0.0", port=port)