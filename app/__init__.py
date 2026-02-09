import os
from flask import Flask, jsonify
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
    CORS(app)
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    # Register blueprints with proper URL prefixes
    # This solves the 404 errors by mapping prefixes like /api/orders
    from app.auth import auth_bp
    from app.orders import orders_bp
    from app.wishlist import wishlist_bp
    from app.bargain import bargain_bp
    from app.livestock import livestock_bp
    from app.disputes import disputes_bp
    from app.reviews import reviews_bp
    from app.analytics import analytics_bp
    # Import your payment blueprint here
    from app.payments import payment_bp 

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(orders_bp, url_prefix='/api/orders')
    app.register_blueprint(wishlist_bp, url_prefix='/api/wishlist')
    app.register_blueprint(bargain_bp, url_prefix='/api/bargain')
    app.register_blueprint(livestock_bp, url_prefix='/api/livestock')
    app.register_blueprint(disputes_bp, url_prefix='/api/disputes')
    app.register_blueprint(reviews_bp, url_prefix='/api/reviews')
    app.register_blueprint(analytics_bp, url_prefix='/api/analytics')
    app.register_blueprint(payment_bp, url_prefix='/api/payments')

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
                "auth": "/api/auth/login",
                "livestock": "/api/livestock/all",
                "orders": "/api/orders/",
                "payments": "/api/payments/"
            }
        }), 200

    return app