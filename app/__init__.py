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
                # This adds 'FARMER', 'BUYER', 'ADMIN' to the DB type if they don't exist
                # Using uppercase to match the UserRole enum in models.py
                for role in ['FARMER', 'BUYER', 'ADMIN']:
                    try:
                        connection.execute(text(f"ALTER TYPE userrole ADD VALUE '{role}';"))
                        connection.execute(text("COMMIT"))
                        print(f"✅ Production: Added {role} to userrole enum.")
                    except Exception:
                        connection.execute(text("COMMIT")) # Already exists
                
                # --- Fix Existing Data: Convert lowercase to uppercase ---
                # Update any existing lowercase enum values to uppercase
                try:
                    connection.execute(text("UPDATE users SET role = 'ADMIN' WHERE role = 'admin';"))
                    connection.execute(text("UPDATE users SET role = 'FARMER' WHERE role = 'farmer';"))
                    connection.execute(text("UPDATE users SET role = 'BUYER' WHERE role = 'buyer';"))
                    connection.execute(text("COMMIT"))
                    print("✅ Production: Fixed existing lowercase enum values.")
                except Exception as e:
                    print(f"⚠️ Data fix notice: {e}")
                    connection.execute(text("COMMIT"))
                
                # --- Fix Admin Role: Ensure admin@farmart.com has ADMIN role ---
                # This handles cases where the admin user was created with wrong role
                try:
                    connection.execute(text("""
                        UPDATE users SET role = 'ADMIN' 
                        WHERE email = 'admin@farmart.com' AND role != 'ADMIN';
                    """))
                    connection.execute(text("COMMIT"))
                    print("✅ Production: Fixed admin user role.")
                except Exception as e:
                    print(f"⚠️ Admin role fix notice: {e}")
                    connection.execute(text("COMMIT"))
                
                # --- Create admin1@farmart.com if doesn't exist ---
                try:
                    # First check if admin1@farmart.com exists
                    result = connection.execute(text("""
                        SELECT id FROM users WHERE email = 'admin1@farmart.com'
                    """))
                    existing = result.fetchone()
                    
                    if not existing:
                        # Generate UUID for the new admin
                        import uuid
                        admin1_id = str(uuid.uuid4())
                        from werkzeug.security import generate_password_hash
                        password_hash = generate_password_hash("admin1234")
                        
                        connection.execute(text("""
                            INSERT INTO users (id, email, password_hash, role, is_active, full_name, created_at, updated_at)
                            VALUES (:id, :email, :password_hash, 'ADMIN', true, 'Admin User', NOW(), NOW())
                        """), {"id": admin1_id, "email": "admin1@farmart.com", "password_hash": password_hash})
                        connection.execute(text("COMMIT"))
                        print("✅ Production: Created admin1@farmart.com user.")
                    else:
                        # Fix role if user exists but wrong role
                        connection.execute(text("""
                            UPDATE users SET role = 'ADMIN' 
                            WHERE email = 'admin1@farmart.com' AND role != 'ADMIN';
                        """))
                        connection.execute(text("COMMIT"))
                        print("✅ Production: Fixed admin1@farmart.com user role.")
                except Exception as e:
                    print(f"⚠️ Admin1 creation notice: {e}")
                    connection.execute(text("COMMIT"))
                
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
            admin = User.query.filter_by(email="admin1@farmart.com").first()
            
            if admin:
                logger.info(f"✅ Admin already exists: {admin.email}, role: {admin.role}")
                return jsonify({"message": "Admin already exists", "email": admin.email}), 200
            
            logger.info("🔧 Creating new admin user...")
            admin = User(
                email="admin1@farmart.com",
                role=UserRole.ADMIN,
                full_name="Admin User",
                is_active=True,
            )
            admin.set_password("admin1234")
            db.session.add(admin)
            db.session.commit()
            
            logger.info("✅ Admin created successfully!")
            
            return jsonify({
                "message": "Admin created successfully",
                "email": "admin1@farmart.com",
                "password": "admin1234"
            }), 201
        except Exception as e:
            db.session.rollback()
            logger.error(f"❌ Error creating admin: {str(e)}")
            return jsonify({"error": str(e)}), 500

    return app
