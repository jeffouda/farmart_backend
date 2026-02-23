import os
import logging
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
from .models import db
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from config import config
from sqlalchemy import text

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

migrate = Migrate()
jwt = JWTManager()

def create_app(config_name="default"):
    app = Flask(__name__)
    
    # Enable debug logging in production
    app.logger.setLevel(logging.INFO)

    # Disable strict slashes to prevent redirect issues with CORS
    app.url_map.strict_slashes = False

    # Load configuration from config.py
    app_config = config.get(config_name, config["default"])
    app.config.from_object(app_config)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    # --- DATABASE INITIALIZATION & MIGRATIONS ---
    with app.app_context():
        try:
            # 1. Import models
            from .models import User, Animal, Farmer, Buyer, Order, Review, PendingCheckout
            
            # 2. Basic table creation
            print("Creating database tables...")
            db.create_all()
            
            # 3. PostgreSQL Specific Fixes (Post-creation)
            # This handles the Enum mismatch and the missing order_id column
            if "postgresql" in app.config.get('SQLALCHEMY_DATABASE_URI', ''):
                connection = db.engine.connect()
                # Use a transaction-less execution for ALTER TYPE
                connection.execute(text("COMMIT"))
                
                # --- Fix Enum Case/Value Issues ---
                # This adds 'farmer' and 'buyer' to the DB type if they don't exist
                for role in ['farmer', 'buyer', 'admin']:
                    try:
                        connection.execute(text(f"ALTER TYPE userrole ADD VALUE '{role}';"))
                        connection.execute(text("COMMIT"))
                        print(f"✅ Production: Added {role} to userrole enum.")
                    except Exception:
                        connection.execute(text("COMMIT")) # Already exists
                
                # --- Fix Missing order_id Column ---
                try:
                    # PostgreSQL DO block to add column if missing
                    connection.execute(text("""
                        DO $$ 
                        BEGIN 
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                           WHERE table_name='pending_checkouts' AND column_name='order_id') THEN
                                ALTER TABLE pending_checkouts ADD COLUMN order_id UUID;
                            END IF;
                        END $$;
                    """))
                    connection.execute(text("COMMIT"))
                    print("✅ Production: order_id column verified.")
                except Exception as e:
                    print(f"⚠️ Column migration notice: {e}")
                    connection.execute(text("COMMIT"))

                connection.close()

            print("✅ Database initialization sequence completed!")
        except Exception as e:
            print(f"❌ Database initialization error: {e}")

    # --- UNIFIED CORS CONFIGURATION ---
    CORS(
        app,
        supports_credentials=True,
        resources={
            r"/api/*": {
                "origins": [
                    "http://localhost:5173",
                    "http://127.0.0.1:5173",
                    "http://localhost:3000",
                    "https://farmart-com.onrender.com",
                    "https://farmart-backend-q9w6.onrender.com",
                    "https://aglisten-armida-confarreate.ngrok-free.dev",
                ],
                "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
                "allow_headers": [
                    "Content-Type",
                    "Authorization",
                    "ngrok-skip-browser-warning",
                    "Accept",
                    "Origin",
                    "X-Requested-With",
                ],
                "expose_headers": ["Content-Type", "Authorization"],
                "max_age": 86400,
            }
        },
    )

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
    from app.notifications import notifications_bp
    from app.admin import admin_bp

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
    app.register_blueprint(notifications_bp, url_prefix="/api/notifications")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")

    # Serve uploads logic...
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
        return jsonify({"status": "online", "message": "System is healthy"}), 200

    @app.route("/", methods=["GET"])
    def root():
        return jsonify({
            "name": "FarmArt API",
            "version": "1.0",
            "status": "running",
            "endpoints": {
                "health": "/api/health",
                "auth": "/api/auth/login, /api/auth/register, /api/auth/me",
            },
        }), 200

    @app.route("/api/auth/setup-admin", methods=["POST"])
    def setup_admin():
        """One-time admin user creation endpoint"""
        logger.info("🔧 Setup admin endpoint called")
        
        data = request.get_json()
        secret = data.get("secret")
        
        logger.info(f"🔧 Secret provided: {secret[:10] if secret else 'None'}...")
        
        # Simple secret to prevent unauthorized admin creation
        if secret != "farmart-admin-setup-2024":
            logger.warning("⚠️ Invalid secret provided")
            return jsonify({"error": "Invalid secret"}), 403
        
        try:
            from app.models import User, UserRole
            
            logger.info("🔧 Checking for existing admin...")
            admin = User.query.filter_by(email="admin@farmart.com").first()
            
            if admin:
                logger.info(f"✅ Admin already exists: {admin.email}, role: {admin.role}")
                return jsonify({"message": "Admin already exists", "email": admin.email}), 200
            
            logger.info("🔧 Creating new admin user...")
            admin = User(
                email="admin@farmart.com",
                role=UserRole.ADMIN,
                full_name="Admin User",
                is_active=True,
            )
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
            
            logger.info("✅ Admin created successfully!")
            
            return jsonify({
                "message": "Admin created successfully",
                "email": "admin@farmart.com",
                "password": "admin123"
            }), 201
        except Exception as e:
            db.session.rollback()
            logger.error(f"❌ Error creating admin: {str(e)}")
            return jsonify({"error": str(e)}), 500

    return app
