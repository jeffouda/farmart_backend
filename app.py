# app.py
from app import create_app, db  # Import db here
from flask_cors import CORS
import os

# app instance using the factory
app = create_app()

# --- DATABASE INITIALIZATION BLOCK ---
# This ensures that all tables are created in PostgreSQL on startup.
# Once your app is live and working, you can remove this block.
with app.app_context():
    try:
        db.create_all()
        print("Database tables initialized successfully!")
    except Exception as e:
        print(f"Database initialization error: {e}")
# --------------------------------------

# Configure CORS
CORS(
    app,
    supports_credentials=True,
    resources={r"/api/*": {"origins": app.config['ALLOWED_ORIGINS']}}
)

# Serve static files for uploaded images
static_uploads = os.path.join(os.path.dirname(__file__), "app", "static", "uploads")
if not os.path.exists(static_uploads):
    os.makedirs(static_uploads, exist_ok=True)

@app.route("/static/uploads/<path:filename>")
def serve_upload(filename):
    """Serve uploaded image files."""
    from flask import send_from_directory
    return send_from_directory(static_uploads, filename)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5555)))