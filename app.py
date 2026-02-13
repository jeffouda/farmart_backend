import os
from flask import send_from_directory
from flask_cors import CORS
from app import create_app

# 1. Initialize the app using the factory pattern
app = create_app()

# 2. Get origins from config. 
# It's best to ensure this is a list. If your .env has a comma-separated string, 
# you might need: app.config.get('ALLOWED_ORIGINS', "").split(",")
origins = app.config.get('ALLOWED_ORIGINS', [
    "http://localhost:5173",          # Vite Default
    "http://127.0.0.1:5173",         # Vite Alternative
    "http://localhost:3000",
    "https://farmart-com.onrender.com",
    "https://aglisten-armida-confarreate.ngrok-free.dev" # Your Ngrok Tunnel
])

# 3. Configure CORS
# Safaricom STK/B2C callbacks are server-to-server, so they aren't restricted by CORS,
# but your React/Frontend needs this to talk to your API.
CORS(
    app,
    supports_credentials=True,
    resources={r"/api/*": {"origins": origins}}
)

# 4. Serve static files for uploaded images
# Using absolute paths ensures it works regardless of where the script is started
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
static_uploads = os.path.join(BASE_DIR, "app", "static", "uploads")

if not os.path.exists(static_uploads):
    os.makedirs(static_uploads, exist_ok=True)

@app.route("/static/uploads/<path:filename>")
def serve_upload(filename):
    """Serve uploaded image files."""
    return send_from_directory(static_uploads, filename)

if __name__ == "__main__":
    # In development, you'll run this and then start ngrok: ngrok http 5000
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))