import os
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from .models import db
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from config import config

migrate = Migrate()
jwt = JWTManager()


def create_app(config_name="default"):
    app = Flask(__name__)

    # Disable strict slashes to prevent redirect issues with CORS
    app.url_map.strict_slashes = False

    # Load configuration from config.py
    app_config = config.get(config_name, config["default"])
    app.config.from_object(app_config)


    # Initialize extensions
    # Allow all origins for development (including ngrok)
    CORS(app, resources={
        r"/api/*": {
            "origins": ["http://localhost:5173", "http://127.0.0.1:5173", 
                       "*"]  # Allow all for development including ngrok
        }
    })

    # Initialize extensions with CORS configuration
    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": ["http://localhost:5173", "http://127.0.0.1:5173"],
                "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                "allow_headers": ["Content-Type", "Authorization"],
            }
        },
    )

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    # Register blueprints
    from app.auth import auth_bp
    from app.orders import orders_bp
    from app.wishlist import wishlist_bp
    from app.bargain import bargain_bp
    from app.livestock import livestock_bp
    from app.disputes import disputes_bp
    from app.reviews import reviews_bp
    from app.analytics import analytics_bp
    from app.negotiation import negotiation_bp
    from app.payments import payment_bp

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(orders_bp, url_prefix='/api/orders')
    app.register_blueprint(wishlist_bp, url_prefix='/api/wishlist')
    app.register_blueprint(bargain_bp, url_prefix='/api/bargain')
    app.register_blueprint(livestock_bp, url_prefix='/api/livestock')
    app.register_blueprint(disputes_bp, url_prefix='/api/disputes')
    app.register_blueprint(reviews_bp, url_prefix='/api/reviews')
    app.register_blueprint(analytics_bp, url_prefix='/api/analytics')
    app.register_blueprint(negotiation_bp, url_prefix='/api/negotiation')
    app.register_blueprint(payment_bp, url_prefix='/api/payments')

    # Serve uploaded images
    uploads_dir = os.path.join(os.getcwd(), "uploads")
    if os.path.exists(uploads_dir):

        @app.route("/uploads/<path:filename>")
        def serve_upload(filename):
            return send_from_directory(uploads_dir, filename)

    # Health check endpoint
    @app.route("/api/health", methods=["GET"])
    def health_check():
        return jsonify({"status": "online", "message": "System is healthy"}), 200

    # Root endpoint - API info
    @app.route("/", methods=["GET"])
    def root():
        return jsonify({
            "name": "FarmArt API",
            "version": "1.0",
            "status": "running",
            "endpoints": {
                "health": "/api/health",
                "auth": "/api/auth/login, /api/auth/register, /api/auth/me",
                "livestock": "/api/livestock/all, /api/livestock/<id>",
                "orders": "/api/orders/",
                "wishlist": "/api/wishlist/",
                "bargain": "/api/bargain/sessions",
                "reviews": "/api/reviews/",
                "disputes": "/api/disputes/",
                "analytics": "/api/analytics/farmer",
                "negotiation": "/api/negotiation/<livestock_id>",
                "payments": "/api/payments/"
            }
        }), 200

    return app
