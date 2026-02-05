from flask import request, jsonify
from flask_jwt_extended import create_access_token
from app import db
from app.models import (
    User,
    Farmer,
    Buyer,
    UserRole,
)
from . import auth_bp


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

    # Validate role
    if role not in ["farmer", "buyer"]:
        return jsonify({"error": "Invalid role. Must be 'farmer' or 'buyer'"}), 400

    # Check if user already exists
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already registered"}), 409

    # 2. Create the Base User
    new_user = User(email=email, role=role)
    new_user.set_password(password)

    db.session.add(new_user)
    db.session.flush()  # Generates the user_id for the next step

    # 3. Create Profile based on Role with proper validation
    if role == "farmer":
        # Farmer requires farm_name, location, and phone_number
        farmer_required_fields = ["farm_name", "location", "phone_number"]
        missing_fields = [f for f in farmer_required_fields if not data.get(f)]

        if missing_fields:
            db.session.rollback()
            return jsonify({
                "error": f"Missing required farmer fields: {', '.join(missing_fields)}"
            }), 400

        new_profile = Farmer(
            user_id=new_user.id,
            farm_name=data["farm_name"],
            location=data["location"],
            phone_number=data["phone_number"],
        )
        db.session.add(new_profile)

    elif role == "buyer":
        # Buyer doesn't require additional fields but can have optional ones
        delivery_address = data.get("delivery_address")
        preferred_contact = data.get("preferred_contact")

        new_profile = Buyer(
            user_id=new_user.id,
            delivery_address=delivery_address,
            preferred_contact=preferred_contact,
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
            "user": {"id": str(user.id), "email": user.email, "role": user.role},
        }), 200

    return jsonify({"error": "Invalid credentials"}), 401
