from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import User, Farmer, Animal
from . import livestock_bp
import uuid


@livestock_bp.route("/seed_test", methods=["POST"])
@jwt_required()
def seed_test_animal():
    """
    Create a test animal for testing the negotiation chat.
    Only accessible by farmers.
    """
    user_id_str = get_jwt_identity()

    try:
        user_id_uuid = uuid.UUID(user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    user = User.query.get(user_id_uuid)
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Only farmers can create test animals
    if user.role.value != "farmer":
        return jsonify({"error": "Only farmers can create test animals"}), 403

    farmer = Farmer.query.filter_by(user_id=user_id_uuid).first()
    if not farmer:
        return jsonify({"error": "Farmer profile not found"}), 404

    # Create test animal with dummy image
    animal = Animal(
        farmer_id=farmer.id,
        species="Test Fresian Cow",
        breed="Fresian",
        age=36,  # 3 years
        weight=450,  # kg
        price=50000,  # KES
        status="available",
        image_url="https://placehold.co/600x400?text=Test+Cow",
    )

    db.session.add(animal)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Test cow created successfully",
        "livestock_id": animal.id,
        "animal": animal.to_dict(),
    }), 201


@livestock_bp.route("/list", methods=["GET"])
@jwt_required()
def list_animals():
    """
    List all available animals for the authenticated user (farmer's own animals).
    """
    user_id_str = get_jwt_identity()

    try:
        user_id_uuid = uuid.UUID(user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    user = User.query.get(user_id_uuid)
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Only farmers can list their own animals
    if user.role.value != "farmer":
        return jsonify({"error": "Only farmers can list their animals"}), 403

    farmer = Farmer.query.filter_by(user_id=user_id_uuid).first()
    if not farmer:
        return jsonify({"error": "Farmer profile not found"}), 404

    # Get farmer's animals with case-insensitive status filter
    animals = (
        Animal.query
        .filter(Animal.farmer_id == farmer.id, Animal.status.ilike("available"))
        .order_by(Animal.created_at.desc())
        .all()
    )

    return jsonify({
        "animals": [a.to_dict() for a in animals],
        "count": len(animals),
    }), 200


@livestock_bp.route("/all", methods=["GET"])
def get_all_livestock():
    """
    Get all available livestock for the marketplace (public endpoint).
    - Case-insensitive filter for status='available'
    - Returns items even without images
    - Sorts by created_at descending (newest first)
    """
    animals = (
        Animal.query
        .filter(Animal.status.ilike("available"))
        .order_by(Animal.created_at.desc())
        .all()
    )

    return jsonify({
        "animals": [a.to_dict() for a in animals],
        "count": len(animals),
    }), 200
