from flask import request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from app import db
from app.models import (
    User,
    Farmer,
    Buyer,
    UserRole,
)
from . import auth_bp
from datetime import datetime
import uuid


# HEALTH CHECK ROUTE
@auth_bp.route("/health", methods=["GET"])
def health_check():
    try:
        # Check DB Connection
        db.session.execute(db.text("SELECT 1"))
        return jsonify({
            "status": "online",
            "database": "connected",
            "backend_time": datetime.now().isoformat(),
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "database": str(e)}), 500


# REGISTRATION ROUTE
@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()

    # 1. Basic validation for all users
    required_fields = ["email", "password", "role"]
    if not all(k in data for k in required_fields):
        return jsonify({"error": "Missing email, password, or role"}), 400

    email = data.get("email")
    password = data.get("password")
    role = data.get("role").lower()

    # Get profile fields
    full_name = data.get("full_name")
    phone_number = data.get("phone_number")
    location = data.get("location")

    # Validate role
    if role not in ["farmer", "buyer"]:
        return jsonify({"error": "Invalid role. Must be 'farmer' or 'buyer'"}), 400

    # Check if user already exists
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already registered"}), 409

    # 2. Create the Base User with profile data
    new_user = User(
        email=email,
        role=role,
        full_name=full_name,
        phone_number=phone_number,
        location=location,
    )
    new_user.set_password(password)

    db.session.add(new_user)
    db.session.flush()  # Generates the user_id for the next step

    # 3. Create Profile based on Role
    if role == "farmer":
        # Farmers require farm_name, location, and phone_number
        if not all([
            data.get("farm_name"),
            data.get("location"),
            data.get("phone_number"),
        ]):
            db.session.rollback()
            return jsonify({
                "error": "Farmers require farm_name, location, and phone_number"
            }), 400

        # Check phone number uniqueness
        if Farmer.query.filter_by(phone_number=data["phone_number"]).first():
            db.session.rollback()
            return jsonify({"error": "Phone number already registered"}), 409

        new_profile = Farmer(
            user_id=new_user.id,
            farm_name=data["farm_name"],
            location=data["location"],
            phone_number=data["phone_number"],
        )
        db.session.add(new_profile)

    elif role == "buyer":
        # Buyers don't require additional fields but can have optional ones
        new_profile = Buyer(
            user_id=new_user.id,
            delivery_address=data.get("delivery_address"),
            preferred_contact=data.get("preferred_contact"),
        )
        db.session.add(new_profile)

    # 4. Commit everything
    try:
        db.session.commit()
        return jsonify({
            "message": f"{role.capitalize()} registered successfully",
            "user_id": str(new_user.id),
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# LOGIN ROUTE
@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()

    email = data.get("email")
    password = data.get("password")

    # Find user
    user = User.query.filter_by(email=email).first()

    # Check password
    if user and user.check_password(password):
        # Create JWT Token
        access_token = create_access_token(
            identity=str(user.id), additional_claims={"role": user.role}
        )

        return jsonify({
            "message": "Login successful",
            "access_token": access_token,
            "user": {
                "id": str(user.id),
                "email": user.email,
                "role": user.role,
                "full_name": user.full_name,
                "phone_number": user.phone_number,
                "location": user.location,
            },
        }), 200

    return jsonify({"error": "Invalid credentials"}), 401


# GET CURRENT USER ROUTE
@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def get_current_user():
    # Get user ID from JWT token (returns string UUID)
    user_id_str = get_jwt_identity()

    # Convert string UUID to UUID object for database query
    try:
        user_id_uuid = uuid.UUID(user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    # Find user in database
    user = User.query.get(user_id_uuid)

    if not user:
        return jsonify({"error": "User not found"}), 404

    # Return user data with profile info
    return jsonify({
        "id": str(user.id),
        "email": user.email,
        "role": user.role,
        "full_name": user.full_name,
        "phone_number": user.phone_number,
        "location": user.location,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }), 200
