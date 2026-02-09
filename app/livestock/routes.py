from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import User, Farmer, Animal
from . import livestock_bp
import uuid
import os
from werkzeug.utils import secure_filename
from datetime import datetime


@livestock_bp.route("/stats", methods=["GET"])
@jwt_required()
def get_inventory_stats():
    """
    Get inventory statistics for farmer dashboard.
    Returns count of animals by status.
    """
    user_id_str = get_jwt_identity()

    try:
        user_id_uuid = uuid.UUID(user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    user = User.query.get(user_id_uuid)
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Only farmers can view their inventory stats
    if user.role.value != "farmer":
        return jsonify({"error": "Only farmers can view inventory stats"}), 403

    farmer = Farmer.query.filter_by(user_id=user_id_uuid).first()
    if not farmer:
        return jsonify({"error": "Farmer profile not found"}), 404

    # Get counts by status
    available_count = Animal.query.filter_by(
        farmer_id=farmer.id, 
        status="available"
    ).count()

    pending_count = Animal.query.filter_by(
        farmer_id=farmer.id, 
        status="pending"
    ).count()

    sold_count = Animal.query.filter_by(
        farmer_id=farmer.id, 
        status="sold"
    ).count()

    total_count = Animal.query.filter_by(farmer_id=farmer.id).count()

    return jsonify({
        "total": total_count,
        "available": available_count,
        "pending": pending_count,
        "sold": sold_count,
    }), 200


@livestock_bp.route("/create", methods=["POST"])
@jwt_required()
def create_animal():
    """
    Create a new animal listing with optional image upload.
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

    # Only farmers can create animals
    if user.role.value != "farmer":
        return jsonify({"error": "Only farmers can create livestock listings"}), 403

    farmer = Farmer.query.filter_by(user_id=user_id_uuid).first()
    if not farmer:
        return jsonify({"error": "Farmer profile not found"}), 404

    # Get form data
    species = request.form.get("species")
    breed = request.form.get("breed")
    price = request.form.get("price")
    age = request.form.get("age")
    age_unit = request.form.get("ageUnit", "months")
    weight = request.form.get("weight")
    gender = request.form.get("gender", "male")
    description = request.form.get("description")
    health_history = request.form.get("health_history")

    # Validate required fields
    if not species or not breed or not price:
        return jsonify({"error": "Species, breed, and price are required"}), 400

    # Convert age to months if in years
    age_months = int(age) if age else None
    if age_unit == "years" and age:
        age_months = int(age) * 12

    # Handle image upload
    image_url = None
    if "image" in request.files:
        image_file = request.files["image"]
        if image_file and image_file.filename:
            # Create upload directory if it doesn't exist
            upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "uploads")
            os.makedirs(upload_dir, exist_ok=True)

            # Generate secure filename with timestamp
            filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{image_file.filename}")
            file_path = os.path.join(upload_dir, filename)
            image_file.save(file_path)

            # Store relative URL
            image_url = f"/static/uploads/{filename}"

    # Create new animal
    animal = Animal(
        farmer_id=farmer.id,
        species=species,
        breed=breed,
        age=age_months,
        weight=float(weight) if weight else None,
        price=float(price),
        status="available",
        gender=gender,
        health_history=health_history,
        image_url=image_url or "https://placehold.co/600x400?text=No+Image",
    )

    db.session.add(animal)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Livestock created successfully",
        "animal": animal.to_dict(),
    }), 201


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
