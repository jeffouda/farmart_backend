from app import create_app
from flask_cors import CORS  # Import CORS
import os

# Create the app instance using the factory
app = create_app()

# Enable CORS correctly
# 1. origins: must match your frontend URL exactly
# 2. supports_credentials: must be True for login/sessions to work
# 3. allow_headers: must include the ngrok header you're sending in Axios
CORS(app, 
     origins=["http://localhost:5173"], 
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization", "ngrok-skip-browser-warning"])

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
    # Ensure this port matches the one you use in your ngrok command
    # e.g., ngrok http --url=aglisten-armida-confarreate.ngrok-free.dev 5000
    app.run(debug=True, port=5000)