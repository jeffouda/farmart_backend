from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import User, Farmer, Animal
from . import livestock_bp
import uuid
import os
import cloudinary
import cloudinary.uploader

# Configure Cloudinary at module level
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)


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
        farmer_id=farmer.id, status="available"
    ).count()

    pending_count = Animal.query.filter_by(
        farmer_id=farmer.id, status="pending"
    ).count()

    sold_count = Animal.query.filter_by(farmer_id=farmer.id, status="sold").count()

    total_count = Animal.query.filter_by(farmer_id=farmer.id).count()

    return jsonify({
        "total": total_count,
        "available": available_count,
        "pending": pending_count,
        "sold": sold_count,
    }), 200


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


@livestock_bp.route("/", methods=["GET"])
def get_all_livestock():
    """
    Get all available livestock for the marketplace (public endpoint).
    Supports filtering by species, location, price range, and sorting.

    Query Parameters:
    - species: Filter by animal species (comma-separated for multiple)
    - location: Filter by location
    - min_price: Minimum price filter
    - max_price: Maximum price filter
    - sort: Sort order - "newest", "price_asc", "price_desc"
    """
    # Start with base query - only available animals
    query = Animal.query.filter(Animal.status.ilike("available"))

    # Filter by species (comma-separated for multiple)
    species = request.args.get("species")
    if species:
        species_list = [s.strip().capitalize() for s in species.split(",")]
        if species_list:
            query = query.filter(Animal.species.in_(species_list))

    # Filter by location (case-insensitive)
    location = request.args.get("location")
    if location:
        query = query.filter(Animal.location.ilike(f"%{location}%"))

    # Filter by price range
    min_price = request.args.get("min_price")
    max_price = request.args.get("max_price")

    if min_price:
        try:
            query = query.filter(Animal.price >= float(min_price))
        except ValueError:
            pass

    if max_price:
        try:
            query = query.filter(Animal.price <= float(max_price))
        except ValueError:
            pass

    # Search filter (searches breed and description)
    search = request.args.get("search")
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Animal.breed.ilike(search_term))
            | (Animal.description.ilike(search_term))
            | (Animal.species.ilike(search_term))
        )

    # Sorting
    sort = request.args.get("sort", "newest")

    if sort == "price_asc":
        query = query.order_by(Animal.price.asc())
    elif sort == "price_desc":
        query = query.order_by(Animal.price.desc())
    else:  # "newest" or default
        query = query.order_by(Animal.created_at.desc())

    # Execute query
    animals = query.all()

    return jsonify({
        "animals": [a.to_dict() for a in animals],
        "count": len(animals),
        "filters_applied": {
            "species": species,
            "location": location,
            "min_price": min_price,
            "max_price": max_price,
            "search": search,
            "sort": sort,
        },
    }), 200


@livestock_bp.route("/all", methods=["GET"])
def get_all_livestock_legacy():
    """
    Legacy endpoint - redirects to main livestock endpoint.
    """
    return get_all_livestock()


@livestock_bp.route("/create", methods=["POST"])
@jwt_required()
def create_livestock():
    """
    Create a new livestock listing with Cloudinary image upload.
    Handles multipart/form-data with text fields and image file.
    """
    try:
        user_id_str = get_jwt_identity()

        try:
            user_id_uuid = uuid.UUID(user_id_str)
        except ValueError:
            return jsonify({"error": "Invalid user ID format"}), 400

        user = User.query.get(user_id_uuid)
        if not user or user.role.value != "farmer":
            return jsonify({"error": "Only farmers can create livestock listings"}), 403

        farmer = Farmer.query.filter_by(user_id=user_id_uuid).first()
        if not farmer:
            return jsonify({"error": "Farmer profile not found"}), 404

        # Get text fields from form
        species = request.form.get("species")
        breed = request.form.get("breed")
        age = request.form.get("age")
        age_unit = request.form.get("ageUnit", "years")
        weight = request.form.get("weight")
        price = request.form.get("price")
        description = request.form.get("description", "")
        gender = request.form.get("gender", "male")
        health_history = request.form.get("health_history", "")

        # Validate required fields
        if not species or not breed or not price:
            return jsonify({
                "error": "Missing required fields: species, breed, and price are required"
            }), 400

        # Handle image upload to Cloudinary
        image_file = request.files.get("image")
        image_url = None

        if image_file:
            try:
                # Check if Cloudinary is configured
                cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME")
                if not cloud_name:
                    raise Exception("CLOUDINARY_CLOUD_NAME not set in environment")

                # Upload to Cloudinary - need to pass file stream, not the FileStorage object directly
                upload_result = cloudinary.uploader.upload(
                    image_file.read(),
                    folder="farmart/livestock",
                    public_id=f"{farmer.id}_{uuid.uuid4().hex[:8]}",
                    resource_type="image",
                )
                image_url = upload_result.get("secure_url")
                print(f"✅ Image uploaded to Cloudinary: {image_url}")
            except Exception as e:
                print(f"❌ Cloudinary upload failed: {e}")
                # Fallback to placeholder on error
                image_url = "https://placehold.co/600x400?text=Upload+Failed"
        else:
            # Use placeholder image if no image uploaded
            image_url = "https://placehold.co/600x400?text=No+Image"

        # Create animal
        animal = Animal(
            farmer_id=farmer.id,
            species=species,
            breed=breed,
            age=int(age) if age else None,
            weight=float(weight) if weight else None,
            price=float(price),
            description=description,
            gender=gender,
            health_history=health_history,
            status="available",
            image_url=image_url,
        )

        db.session.add(animal)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Livestock listed successfully",
            "animal": animal.to_dict(),
        }), 201

    except Exception as e:
        print(f"❌ create_livestock error: {e}")
        return jsonify({"error": str(e)}), 500


@livestock_bp.route("/<uuid:animal_id>", methods=["GET"])
def get_animal(animal_id):
    """
    Get a single animal by ID.
    Returns animal details including farmer information.
    """
    animal = Animal.query.get_or_404(animal_id, description="Animal not found")

    # Get farmer details
    farmer = Farmer.query.get(animal.farmer_id)
    farmer_user = User.query.get(farmer.user_id) if farmer else None

    # Build response matching frontend expectations
    return jsonify({
        "id": str(animal.id),
        "breed": animal.breed,
        "species": animal.species,
        "price": float(animal.price),
        "description": animal.description,
        "health_records": animal.health_history,
        "age": animal.age,
        "weight": animal.weight,
        "location": farmer.location if farmer else None,
        "image_url": animal.image_url,
        "farmer_id": str(animal.farmer_id),
        "status": animal.status,
        "gender": animal.gender,
        # Additional farmer info
        "farmer_name": farmer_user.full_name if farmer_user else "Unknown",
        "farmer_verified": farmer.is_verified if farmer else False,
    }), 200


@livestock_bp.route("/<uuid:animal_id>", methods=["PUT"])
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


@livestock_bp.route("/<uuid:animal_id>", methods=["DELETE"])
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
