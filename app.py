# app.py
from app import create_app, db
from flask_cors import CORS
import os

# 1. Initialize the app
app = create_app()

# --- DATABASE INITIALIZATION BLOCK ---
with app.app_context():
    try:
        # IMPORTANT: You MUST import your models here. 
        # If SQLAlchemy doesn't see them, it won't create the tables.
        from app.models import User, Farmer, Buyer, Animal, Order # Add all your model names here
        
        print("Registering models and creating tables...")
        db.create_all()
        print("✅ Database tables initialized successfully!")
    except Exception as e:
        print(f"❌ Database initialization error: {e}")
# --------------------------------------

# 2. Configure CORS
# Pull from config or fallback to your frontend URL
allowed_origins = [
    "https://farmart-com.onrender.com",
    "https://farmart-backend-q9w6.onrender.com",
    "http://localhost:5173",
    "http://localhost:3000",
    "https://aglisten-armida-confarreate.ngrok-free.dev",
]

CORS(
    app,
    supports_credentials=True,
    resources={
        r"/api/*": {
            "origins": allowed_origins,
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
            "allow_headers": ["Content-Type", "Authorization", "Accept", "Origin", "ngrok-skip-browser-warning", "X-Requested-With"],
            "expose_headers": ["Content-Type", "Authorization"],
            "max_age": 86400
        }
    }
)

# 3. Static File Handling
static_uploads = os.path.join(os.path.dirname(__file__), "app", "static", "uploads")
if not os.path.exists(static_uploads):
    os.makedirs(static_uploads, exist_ok=True)

# server
@app.route("/static/uploads/<path:filename>")
def serve_upload(filename):
    from flask import send_from_directory
    return send_from_directory(static_uploads, filename)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5555))
    app.run(host="0.0.0.0", port=port)