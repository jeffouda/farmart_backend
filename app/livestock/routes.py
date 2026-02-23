from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import User, Farmer, Animal
from . import livestock_bp
import uuid
import os
import cloudinary
import cloudinary.uploader
from werkzeug.utils import secure_filename
from datetime import datetime


def save_local_image(image_file):
    """Save image to local storage and return URL."""
    # Create upload directory if it doesn't exist
    upload_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "static", "uploads"
    )
    os.makedirs(upload_dir, exist_ok=True)

    # Generate secure filename with timestamp
    filename = secure_filename(
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{image_file.filename}"
    )
    file_path = os.path.join(upload_dir, filename)
    image_file.save(file_path)

    # Store relative URL
    image_url = f"/static/uploads/{filename}"
    print(f"✅ Image saved locally: {image_url}")
    return image_url


# Configure Cloudinary at module level
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)


def get_animal_by_id(animal_id):
    """
    Helper function to find animal by ID (handles UUID and string IDs).
    """
    # Try to parse as UUID first
    try:
        uuid_id = uuid.UUID(animal_id)
        animal = Animal.query.filter_by(id=uuid_id).first()
        if animal:
            return animal
    except ValueError:
        pass

    # Try direct lookup as last resort
    return Animal.query.filter_by(id=animal_id).first()


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

    user = User.query.filter_by(id=str(user_id_uuid)).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Convert enum to string for comparison
    user_role = user.role.value if hasattr(user.role, 'value') else str(user.role)
    user_role_lower = user_role.lower() if user_role else user_role

    # Only farmers can view their inventory stats
    if user_role_lower != "farmer":
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

    user = User.query.filter_by(id=str(user_id_uuid)).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Convert enum to string for comparison
    user_role = user.role.value if hasattr(user.role, 'value') else str(user.role)
    user_role_lower = user_role.lower() if user_role else user_role

    # Only farmers can create animals
    if user_role_lower != "farmer":
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
            # Check if Cloudinary is configured
            cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME")
            api_key = os.getenv("CLOUDINARY_API_KEY")
            api_secret = os.getenv("CLOUDINARY_API_SECRET")

            print(
                f"🔍 Cloudinary config check: name={cloud_name}, key={api_key[:10] if api_key else 'None'}..."
            )

            if (
                cloud_name
                and api_key
                and api_secret
                and cloud_name != "your_cloud_name"
            ):
                # Upload to Cloudinary
                try:
                    upload_result = cloudinary.uploader.upload(
                        image_file, folder="farmart_livestock", resource_type="image"
                    )
                    image_url = upload_result.get("secure_url")
                    print(f"✅ Image uploaded to Cloudinary: {image_url}")
                except Exception as cloud_error:
                    print(f"❌ Cloudinary upload failed: {cloud_error}")
                    # Fallback to local storage
                    image_url = save_local_image(image_file)
            else:
                print("⚠️ Cloudinary not configured, using local storage")
                # Use local storage
                image_url = save_local_image(image_file)

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

    user = User.query.filter_by(id=str(user_id_uuid)).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Convert enum to string for comparison
    user_role = user.role.value if hasattr(user.role, 'value') else str(user.role)
    user_role_lower = user_role.lower() if user_role else user_role

    # Only farmers can create test animals
    if user_role_lower != "farmer":
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


@livestock_bp.route('/', methods=['GET', 'OPTIONS'])
@jwt_required(optional=True)
def list_animals():
    """
    Marketplace Endpoint: Lists all available animals for everyone.
    If a user is logged in as a farmer, we can optionally filter or tag their own.
    """
    # 1. Get query parameters from the React Marketplace
    search_query = request.args.get('search')
    species = request.args.get('species') # e.g., "Cattle,Goats"
    min_price = request.args.get('min_price')
    max_price = request.args.get('max_price')
    location = request.args.get('location')
    sort_by = request.args.get('sort', 'newest')

    # 2. Base Query: Only show 'available' animals to the public
    show_sold = request.args.get('show_sold', 'false').lower() == 'true'
    
    if show_sold:
        query = Animal.query  # Show all animals
    else:
        query = Animal.query.filter(Animal.status.ilike("available"))

    # 3. Apply Filters
    if search_query:
        query = query.filter(Animal.breed.ilike(f"%{search_query}%") | 
                             Animal.species.ilike(f"%{search_query}%"))
    
    if species:
        species_list = species.split(',')
        query = query.filter(Animal.species.in_(species_list))

    if min_price:
        query = query.filter(Animal.price >= float(min_price))
    
    if max_price:
        query = query.filter(Animal.price <= float(max_price))

    # 4. Sorting
    if sort_by == 'price_low':
        query = query.order_by(Animal.price.asc())
    elif sort_by == 'price_high':
        query = query.order_by(Animal.price.desc())
    else:
        query = query.order_by(Animal.created_at.desc())

    animals = query.all()

    return jsonify({
        "animals": [a.to_dict() for a in animals],
        "count": len(animals),
    }), 200

# NEW ROUTE: Specific for Farmer's private dashboard
@livestock_bp.route('/my-inventory', methods=['GET'])
@jwt_required()
def get_my_inventory():
    user_id_str = get_jwt_identity()
    user_id_uuid = uuid.UUID(user_id_str)
    
    farmer = Farmer.query.filter_by(user_id=user_id_uuid).first()
    if not farmer:
        return jsonify({"error": "Farmer profile not found"}), 404

    animals = Animal.query.filter_by(farmer_id=farmer.id).all()
    return jsonify({"animals": [a.to_dict() for a in animals]}), 200


@livestock_bp.route("", methods=["GET"])
@livestock_bp.route("/all", methods=["GET"])
def get_all_livestock():
    """
    Get all available livestock for the marketplace (public endpoint).
    - Case-insensitive filter for status='available'
    - Returns items even without images
    - Sorts by created_at descending (newest first)
    - Handles both Cloudinary URLs and local image filenames
    """
    try:
        animals = (
            Animal.query
            .filter(Animal.status.ilike("available"))
            .order_by(Animal.created_at.desc())
            .all()
        )

        # Helper function to process image URL
        def process_image_url(image_url):
            """Handle both Cloudinary (full URLs) and local legacy filenames."""
            if not image_url:
                return "https://placehold.co/600x400?text=No+Image"
            if image_url.startswith("http"):
                # It's a Cloudinary or external URL, leave it as-is
                return image_url
            # It's a local legacy file, construct full path
            return f"{request.host_url}static/uploads/{image_url}"

        # Build response with robust image handling
        animals_list = []
        for animal in animals:
            animal_dict = {
                "id": str(animal.id),
                "species": animal.species,
                "breed": animal.breed,
                "age": animal.age,
                "weight": animal.weight,
                "price": float(animal.price) if animal.price else 0,
                "status": animal.status,
                "gender": animal.gender,
                "health_history": animal.health_history,
                "image_url": process_image_url(animal.image_url),
                "farmer_id": str(animal.farmer_id),
                "created_at": animal.created_at.isoformat()
                if animal.created_at
                else None,
            }
            # Get farmer info if available
            if animal.owner:
                animal_dict["farmer_name"] = animal.owner.farm_name
                animal_dict["location"] = animal.owner.location
            animals_list.append(animal_dict)

        return jsonify({
            "animals": animals_list,
            "count": len(animals_list),
        }), 200

    except Exception as e:
        print(f"❌ CRITICAL ERROR in GET /livestock/all: {str(e)}")
        return jsonify({"error": "Internal Server Error", "details": str(e)}), 500


@livestock_bp.route("/", methods=["GET"])
def get_livestock():
    """
    Get livestock with query parameter filtering.
    Supports: search, species, min_price, max_price, location, sort
    """
    try:
        # Get query parameters
        search = request.args.get("search", "")
        species = request.args.get("species", "")
        min_price = request.args.get("min_price")
        max_price = request.args.get("max_price")
        location = request.args.get("location", "")
        sort = request.args.get("sort", "newest")

        # Build query
        show_sold = request.args.get("show_sold", "false").lower() == "true"
        
        if show_sold:
            query = Animal.query  # Show all animals
        else:
            query = Animal.query.filter(Animal.status.ilike("available"))

        # Search filter
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                db.or_(
                    Animal.species.ilike(search_term),
                    Animal.breed.ilike(search_term),
                )
            )

        # Species filter (comma-separated)
        if species:
            species_list = [s.strip() for s in species.split(",")]
            query = query.filter(Animal.species.in_(species_list))

        # Price range filters
        if min_price:
            query = query.filter(Animal.price >= float(min_price))
        if max_price:
            query = query.filter(Animal.price <= float(max_price))

        # Location filter (requires join with Farmer)
        if location:
            # Use correlated subquery for location filter
            from sqlalchemy.sql import exists

            location_filter = exists().where(
                db.and_(
                    Farmer.id == Animal.farmer_id,
                    Farmer.location.ilike(f"%{location}%"),
                )
            )
            query = query.filter(location_filter)

        # Sorting
        if sort == "price_low":
            query = query.order_by(Animal.price.asc())
        elif sort == "price_high":
            query = query.order_by(Animal.price.desc())
        else:  # newest
            query = query.order_by(Animal.created_at.desc())

        animals = query.all()

        # Helper function to process image URL
        def process_image_url(image_url):
            """Handle both Cloudinary (full URLs) and local legacy filenames."""
            if not image_url:
                return "https://placehold.co/600x400?text=No+Image"
            if image_url.startswith("http"):
                # It's a Cloudinary or external URL, leave it as-is
                return image_url
            # It's a local legacy file, construct full path
            return f"{request.host_url}static/uploads/{image_url}"

        # Build response with robust image handling
        animals_list = []
        for animal in animals:
            animal_dict = {
                "id": str(animal.id),
                "species": animal.species,
                "breed": animal.breed,
                "age": animal.age,
                "weight": animal.weight,
                "price": float(animal.price) if animal.price else 0,
                "status": animal.status,
                "gender": animal.gender,
                "health_history": animal.health_history,
                "image_url": process_image_url(animal.image_url),
                "farmer_id": str(animal.farmer_id),
                "created_at": animal.created_at.isoformat()
                if animal.created_at
                else None,
            }
            # Get farmer info if available
            if animal.owner:
                animal_dict["farmer_name"] = animal.owner.farm_name
                animal_dict["location"] = animal.owner.location
            animals_list.append(animal_dict)

        return jsonify({
            "animals": animals_list,
            "count": len(animals_list),
        }), 200

    except Exception as e:
        print(f"❌ CRITICAL ERROR in GET /livestock: {str(e)}")
        return jsonify({"error": "Internal Server Error", "details": str(e)}), 500


@livestock_bp.route("/<string:animal_id>", methods=["GET"])
def get_animal(animal_id):
    """
    Get a single animal by ID (supports UUID and string IDs).
    Returns animal details including farmer information.
    """
    try:
        animal = get_animal_by_id(animal_id)

        if not animal:
            return jsonify({"error": "Animal not found"}), 404

        # Get farmer details
        farmer = Farmer.query.get(animal.farmer_id)
        farmer_data = None

        if farmer:
            user = User.query.filter_by(id=str(farmer.user_id)).first()
            farmer_data = {
                "id": farmer.id,
                "name": user.full_name if user else "Unknown Farmer",
                "rating": user.average_rating
                if user and hasattr(user, "average_rating")
                else 0,
                "verified": farmer.is_verified or False,
                "avatar": (user.full_name[:2] if user else "U").upper()
                if user
                else "U",
                "phone": farmer.phone_number or None,
            }

        # Build response matching frontend expectations
        response_data = animal.to_dict()
        response_data.update({
            "farmer_id": str(animal.farmer_id),
            "farmer_name": farmer_data["name"] if farmer_data else "Unknown",
            "farmer": farmer_data,
            # Ensure image is available
            "image": animal.image_url or None,
            "images": [
                {
                    "url": animal.image_url
                    or "https://placehold.co/600x400?text=No+Image",
                    "alt": f"{animal.species} - {animal.breed}",
                }
            ],
        })

        return jsonify(response_data), 200

    except Exception as e:
        print(f"❌ ERROR in get_animal: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


@livestock_bp.route("/<string:animal_id>", methods=["PUT"])
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

    user = User.query.filter_by(id=str(user_id_uuid)).first()
    
    # Convert enum to string for comparison
    user_role = user.role.value if hasattr(user.role, 'value') else str(user.role)
    user_role_lower = user_role.lower() if user_role else user_role
    
    if not user or user_role_lower != "farmer":
        return jsonify({"error": "Only farmers can update animals"}), 403

    farmer = Farmer.query.filter_by(user_id=user_id_uuid).first()
    if not farmer:
        return jsonify({"error": "Farmer profile not found"}), 404

    animal = get_animal_by_id(animal_id)
    if not animal:
        return jsonify({"error": "Animal not found or access denied"}), 404

    # Verify ownership
    if animal.farmer_id != farmer.id:
        return jsonify({"error": "Not authorized to update this animal"}), 403

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


@livestock_bp.route("/<string:animal_id>", methods=["DELETE"])
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

    user = User.query.filter_by(id=str(user_id_uuid)).first()
    
    # Convert enum to string for comparison
    user_role = user.role.value if hasattr(user.role, 'value') else str(user.role)
    user_role_lower = user_role.lower() if user_role else user_role
    
    if not user or user_role_lower != "farmer":
        return jsonify({"error": "Only farmers can delete animals"}), 403

    farmer = Farmer.query.filter_by(user_id=user_id_uuid).first()
    if not farmer:
        return jsonify({"error": "Farmer profile not found"}), 404

    animal = get_animal_by_id(animal_id)
    if not animal:
        return jsonify({"error": "Animal not found or access denied"}), 404

    # Verify ownership
    if animal.farmer_id != farmer.id:
        return jsonify({"error": "Not authorized to delete this animal"}), 403

    db.session.delete(animal)
    db.session.commit()

    return jsonify({
        "message": "Animal deleted successfully",
    }), 200
