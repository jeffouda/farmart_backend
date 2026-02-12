# app.py
from app import create_app
from flask_cors import CORS
import os

# app instance using the factory
app = create_app()

# Configure CORS
CORS(
    app,
    supports_credentials=True,
    resources={r"/api/*": {"origins": "*"}}
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
