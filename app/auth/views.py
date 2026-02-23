from flask import request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from app import db
from app.models import (
    User,
    Farmer,
    Buyer,
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

    # Basic validation for all users
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

    # Create the Base User with profile data
    new_user = User(
        email=email,
        role=role,  # Use string directly
        full_name=full_name,
        phone_number=phone_number,
        location=location,
    )
    new_user.set_password(password)

    db.session.add(new_user)
    db.session.flush()  # Generates the user_id for the next step

    # Create Profile based on Role
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

    # Commit everything
    try:
        db.session.commit()
        
        # Create JWT token for auto-login after registration
        access_token = create_access_token(
            identity=str(new_user.id), 
            additional_claims={"role": new_user.role}
        )
        
        return jsonify({
            "message": f"{role.capitalize()} registered successfully",
            "access_token": access_token,
            "user": {
                "id": str(new_user.id),
                "email": new_user.email,
                "role": new_user.role,
                "full_name": new_user.full_name,
                "phone_number": new_user.phone_number,
                "location": new_user.location,
            },
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# LOGIN ROUTE
@auth_bp.route("/login", methods=["POST"])
def login():
    import logging
    
    logger = logging.getLogger(__name__)
    
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")
    
    logger.info(f"🔐 Login attempt for email: {email}")

    # Find user
    user = User.query.filter_by(email=email).first()
    
    if not user:
        logger.warning(f"❌ User not found: {email}")
        return jsonify({"error": "Invalid credentials"}), 401
    
    logger.info(f"✅ User found: {user.email}, role: {user.role}")
    
    # Check password
    if user and user.check_password(password):
        # Ensure role is always a lowercase string
        user_role = user.role.value if hasattr(user.role, 'value') else str(user.role)
        user_role = user_role.lower() if user_role else user_role
        
        logger.info(f"🎫 Creating JWT with role: {user_role}")
        
        # Create JWT Token
        access_token = create_access_token(
            identity=str(user.id), additional_claims={"role": user_role}
        )
        
        logger.info(f"✅ Login successful for: {email}")

        return jsonify({
            "message": "Login successful",
            "access_token": access_token,
            "user": {
                "id": str(user.id),
                "email": user.email,
                "role": user_role,
                "full_name": user.full_name,
                "phone_number": user.phone_number,
                "location": user.location,
            },
        }), 200

    logger.warning(f"❌ Invalid credentials for: {email}")
    return jsonify({"error": "Invalid credentials"}), 401


# DEBUG ROUTE - Remove in production!
@auth_bp.route("/debug/login", methods=["POST"])
def debug_login():
    """Debug login that returns user info even if password fails (for testing only!)."""
    data = request.get_json()
    email = data.get("email")

    user = User.query.filter_by(email=email).first()

    if not user:
        return jsonify({
            "error": "User not found",
            "email": email,
            "registered_emails": [u.email for u in User.query.all()],
        }), 404

    # Check if password matches
    password = data.get("password")
    password_matches = user.check_password(password)

    return jsonify({
        "email": user.email,
        "role": user.role.value if hasattr(user.role, "value") else user.role,
        "password_hash": user.password_hash[:20] + "...",
        "password_matches": password_matches,
        "debug": "Password check result",
    }), 200


# GET CURRENT USER ROUTE
@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def get_current_user():
    # Get user ID from JWT token (returns string UUID)
    user_id_str = get_jwt_identity()

    # Find user in database (use string directly)
    user = User.query.filter_by(id=user_id_str).first()

    if not user:
        return jsonify({"error": "User not found"}), 404

    # Ensure role is always a lowercase string
    user_role = user.role.value if hasattr(user.role, 'value') else str(user.role)
    user_role = user_role.lower() if user_role else user_role

    # Build response with user data - role is now a string
    user_data = {
        "id": str(user.id),
        "email": user.email,
        "role": user_role,
        "full_name": user.full_name,
        "phone_number": user.phone_number,
        "location": user.location,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "average_rating": user.average_rating,
        "review_count": user.review_count,
    }

    # Add role-specific profile data
    if user_role == "farmer" and user.farmer:
        user_data["farm_name"] = user.farmer.farm_name
        user_data["farm_location"] = user.farmer.location
        user_data["farm_phone_number"] = user.farmer.phone_number
        user_data["is_verified"] = user.farmer.is_verified
        user_data["wallet_balance"] = float(user.farmer.wallet_balance) if user.farmer.wallet_balance else 0
    elif user_role == "buyer" and user.buyer:
        user_data["delivery_address"] = user.buyer.delivery_address
        user_data["preferred_contact"] = user.buyer.preferred_contact

    return jsonify(user_data), 200


# UPDATE PROFILE ROUTE
@auth_bp.route("/profile", methods=["PUT"])
@jwt_required()
def update_profile():
    """Update current user's profile"""
    user_id_str = get_jwt_identity()

    # Use string directly since database stores UUIDs as strings
    user = User.query.filter_by(id=user_id_str).first()

    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json()

    # Update basic user fields
    if "full_name" in data:
        user.full_name = data["full_name"]
    if "phone_number" in data:
        user.phone_number = data["phone_number"]
    if "location" in data:
        user.location = data["location"]

    # Update role-specific fields
    if user.role == "farmer" and user.farmer:
        if "farm_name" in data:
            user.farmer.farm_name = data["farm_name"]
        if "farm_location" in data:
            user.farmer.location = data["farm_location"]
        # Note: phone_number should be updated on user level, not farmer level for uniqueness reasons
    elif user.role == "buyer" and user.buyer:
        if "delivery_address" in data:
            user.buyer.delivery_address = data["delivery_address"]
        if "preferred_contact" in data:
            user.buyer.preferred_contact = data["preferred_contact"]

    try:
        db.session.commit()

        # Return updated user data
        return get_current_user()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

