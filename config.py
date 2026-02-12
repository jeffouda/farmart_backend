import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Base configuration class."""

    # Database configuration
    DATABASE_URL = os.environ.get("DATABASE_URL")
    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace(
            "postgres://", "postgresql://", 1
        )
    # Ensure port 5432 for Render PostgreSQL
    if DATABASE_URL and "@" in DATABASE_URL and ":5432" not in DATABASE_URL:
        parts = DATABASE_URL.split("@")
        if len(parts) == 2:
            before_at, after_at = parts
            host_db = after_at.split("/")
            if len(host_db) == 2:
                host, db = host_db
                DATABASE_URL = f"{before_at}@{host}:5432/{db}"
    if not DATABASE_URL:
        # Use SQLite for development if DATABASE_URL is not set
        DATABASE_URL = "sqlite:///farmart.db"

    # JWT configuration
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-secret-key")
    JWT_ACCESS_TOKEN_EXPIRES = int(os.environ.get(
        "JWT_ACCESS_TOKEN_EXPIRES", 3600
    ))  # Ensure it's an integer

    # Flask configuration
    FLASK_APP = os.environ.get("FLASK_APP", "app.py")
    FLASK_ENV = os.environ.get("FLASK_ENV", "development")

    # SQLAlchemy configuration
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    # ==========================================
    # M-PESA CONFIGURATION (Daraja API)
    # ==========================================
    MPESA_CONSUMER_KEY = os.environ.get('MPESA_CONSUMER_KEY')
    MPESA_CONSUMER_SECRET = os.environ.get('MPESA_CONSUMER_SECRET')
    MPESA_SHORTCODE = os.environ.get('MPESA_SHORTCODE')
    MPESA_PASSKEY = os.environ.get('MPESA_PASSKEY')
    
    # B2C Credentials (for Farmer Payouts)
    MPESA_INITIATOR_NAME = os.environ.get('MPESA_INITIATOR_NAME')
    MPESA_SECURITY_CREDENTIAL = os.environ.get('MPESA_SECURITY_CREDENTIAL')
    
    # Base URL for Webhook Callbacks (Ngrok or Production Domain)
    BASE_URL = os.environ.get('BASE_URL')

    # CORS Allowed Origins
    ALLOWED_ORIGINS = os.environ.get(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:5173,https://farmart-com.onrender.com"
    ).split(",")


class DevelopmentConfig(Config):
    """Development configuration."""
    FLASK_ENV = "development"
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration."""
    FLASK_ENV = "production"
    DEBUG = False


# Configuration mapping
config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}