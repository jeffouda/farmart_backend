# app.py
from app import create_app
import os

# app instance using the factory
app = create_app()

# Note: CORS is now configured in the create_app() factory in app/__init__.py
# Do not add additional CORS configuration here to avoid conflicts


# Serve static files for uploaded images
static_uploads = os.path.join(os.path.dirname(__file__), "app", "static", "uploads")
if not os.path.exists(static_uploads):
    os.makedirs(static_uploads, exist_ok=True)

@app.route("/static/uploads/<path:filename>")
def serve_upload(filename):
    """Serve uploaded image files."""
    from flask import send_from_directory
    return send_from_directory(static_uploads, filename)
