from flask import Flask
from flask_cors import CORS
from .models import db
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from config import config

migrate = Migrate()
jwt = JWTManager()


def create_app(config_name="default"):
    app = Flask(__name__)

    # Load configuration from config.py
    app_config = config.get(config_name, config["default"])
    app.config.from_object(app_config)

    # Initialize extensions
    CORS(app)
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    # Register blueprints
    from app.auth import auth_bp

    app.register_blueprint(auth_bp)

    return app
