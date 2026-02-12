import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///farmart.db")
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 300, "pool_size": 10, "max_overflow": 20}
    
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-secret-key")
    JWT_ACCESS_TOKEN_EXPIRES = int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRES", 3600))
    FLASK_APP = os.environ.get("FLASK_APP", "app.py")
    FLASK_ENV = os.environ.get("FLASK_ENV", "development")
    
    MPESA_CONSUMER_KEY = os.environ.get('MPESA_CONSUMER_KEY')
    MPESA_CONSUMER_SECRET = os.environ.get('MPESA_CONSUMER_SECRET')
    MPESA_SHORTCODE = os.environ.get('MPESA_SHORTCODE')
    MPESA_PASSKEY = os.environ.get('MPESA_PASSKEY')
    MPESA_INITIATOR_NAME = os.environ.get('MPESA_INITIATOR_NAME')
    MPESA_SECURITY_CREDENTIAL = os.environ.get('MPESA_SECURITY_CREDENTIAL')
    BASE_URL = os.environ.get('BASE_URL')

class DevelopmentConfig(Config):
    FLASK_ENV = "development"
    DEBUG = True

class ProductionConfig(Config):
    FLASK_ENV = "production"
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 3600
    
    def __init__(self):
        super().__init__()
        if not os.environ.get("JWT_SECRET_KEY") or os.environ.get("JWT_SECRET_KEY") == "dev-secret-key":
            raise ValueError("JWT_SECRET_KEY must be set in production")
        if not os.environ.get("DATABASE_URL"):
            raise ValueError("DATABASE_URL must be set in production")
        if not os.environ.get("FRONTEND_URL"):
            raise ValueError("FRONTEND_URL must be set in production")

config = {"development": DevelopmentConfig, "production": ProductionConfig, "default": DevelopmentConfig}
