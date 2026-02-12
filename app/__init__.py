import os
import logging
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from .models import db
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from config import config
from .error_handlers import register_error_handlers
from .logging_config import setup_logging

migrate = Migrate()
jwt = JWTManager()
logger = logging.getLogger(__name__)


def create_app(config_name="default"):
    app = Flask(__name__)
    app.url_map.strict_slashes = False
    
    app_config = config.get(config_name, config["default"])
    app.config.from_object(app_config)
    
    # CORS configuration
    allowed_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
    base_url = os.environ.get("BASE_URL")
    if base_url:
        allowed_origins.append(base_url)
    frontend_url = os.environ.get("FRONTEND_URL")
    if frontend_url:
        allowed_origins.append(frontend_url)
    
    CORS(app, resources={r"/api/*": {
        "origins": allowed_origins,
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "ngrok-skip-browser-warning"],
        "supports_credentials": True
    }})
    
    setup_logging(app)
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    register_error_handlers(app)
    
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
    from app.notifications import notifications_bp
    
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(orders_bp, url_prefix="/api/orders")
    app.register_blueprint(wishlist_bp, url_prefix="/api/wishlist")
    app.register_blueprint(bargain_bp, url_prefix="/api/bargain")
    app.register_blueprint(livestock_bp, url_prefix="/api/livestock")
    app.register_blueprint(disputes_bp, url_prefix="/api/disputes")
    app.register_blueprint(reviews_bp, url_prefix="/api/reviews")
    app.register_blueprint(analytics_bp, url_prefix="/api/analytics")
    app.register_blueprint(negotiation_bp, url_prefix="/api/negotiation")
    app.register_blueprint(payment_bp, url_prefix="/api/payments")
    app.register_blueprint(notifications_bp, url_prefix="/api")
    
    uploads_dir = os.path.join(os.getcwd(), "uploads")
    if os.path.exists(uploads_dir):
        @app.route("/uploads/<path:filename>")
        def serve_upload(filename):
            return send_from_directory(uploads_dir, filename)
    
    static_uploads_dir = os.path.join(os.path.dirname(__file__), "static", "uploads")
    if os.path.exists(static_uploads_dir):
        @app.route("/static/uploads/<path:filename>")
        def serve_static_upload(filename):
            return send_from_directory(static_uploads_dir, filename)
    
    @app.route("/api/health", methods=["GET"])
    def health_check():
        try:
            db.session.execute(db.text('SELECT 1'))
            return jsonify({"status": "online", "message": "System is healthy"}), 200
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            return jsonify({"status": "unhealthy", "message": "Database connection failed"}), 503
    
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
                "payments": "/api/payments/",
            },
        }), 200
    
    return app
