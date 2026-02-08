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


@livestock_bp.route("/<int:animal_id>", methods=["GET"])
def get_animal(animal_id):
    """
    Get a single animal by ID.
    Returns animal details including farmer information.
    """
    animal = Animal.query.get(animal_id)

    if not animal:
        return jsonify({"error": "Animal not found"}), 404

    # Get farmer details
    farmer = Farmer.query.get(animal.farmer_id)
    farmer_data = None

    if farmer:
        user = User.query.get(farmer.user_id)
        farmer_data = {
            "id": farmer.id,
            "name": user.full_name if user else "Unknown Farmer",
            "rating": user.average_rating
            if user and hasattr(user, "average_rating")
            else 0,
            "verified": farmer.is_verified or False,
            "avatar": (user.full_name[:2] if user else "U").upper() if user else "U",
            "phone": farmer.phone_number or None,
        }

    # Build response matching frontend expectations
    response_data = animal.to_dict()
    response_data.update({
        "farmer_id": animal.farmer_id,
        "farmer_name": farmer_data["name"] if farmer_data else "Unknown",
        "farmer": farmer_data,
        # Ensure image is available
        "image": animal.image_url or animal.image or None,
        "images": [
            {
                "url": animal.image_url
                or animal.image
                or "https://placehold.co/600x400?text=No+Image",
                "alt": f"{animal.species} - {animal.breed}",
            }
        ],
    })

    return jsonify(response_data), 200


@livestock_bp.route("/<int:animal_id>", methods=["PUT"])
@jwt_required()
def update_animal(animal_id):
    """
    Update an animal's details.
    Only the owner farmer can update their animal.
    """
    user_id_str = get_jwt_identity()

    try:
        user_id_uuid = uuid.UUID(user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    user = User.query.get(user_id_uuid)
    if not user or user.role.value != "farmer":
        return jsonify({"error": "Only farmers can update animals"}), 403

    farmer = Farmer.query.filter_by(user_id=user_id_uuid).first()
    if not farmer:
        return jsonify({"error": "Farmer profile not found"}), 404

    animal = Animal.query.filter_by(id=animal_id, farmer_id=farmer.id).first()
    if not animal:
        return jsonify({"error": "Animal not found or access denied"}), 404

    data = request.get_json()

    # Update allowed fields
    if "price" in data:
        animal.price = data["price"]
    if "status" in data:
        animal.status = data["status"]
    if "image_url" in data:
        animal.image_url = data["image_url"]

    db.session.commit()

    return jsonify({
        "message": "Animal updated successfully",
        "animal": animal.to_dict(),
    }), 200


@livestock_bp.route("/<int:animal_id>", methods=["DELETE"])
@jwt_required()
def delete_animal(animal_id):
    """
    Delete an animal listing.
    Only the owner farmer can delete their animal.
    """
    user_id_str = get_jwt_identity()

    try:
        user_id_uuid = uuid.UUID(user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    user = User.query.get(user_id_uuid)
    if not user or user.role.value != "farmer":
        return jsonify({"error": "Only farmers can delete animals"}), 403

    farmer = Farmer.query.filter_by(user_id=user_id_uuid).first()
    if not farmer:
        return jsonify({"error": "Farmer profile not found"}), 404

    animal = Animal.query.filter_by(id=animal_id, farmer_id=farmer.id).first()
    if not animal:
        return jsonify({"error": "Animal not found or access denied"}), 404

    db.session.delete(animal)
    db.session.commit()

    return jsonify({
        "message": "Animal deleted successfully",
    }), 200
