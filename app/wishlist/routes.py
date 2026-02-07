from flask import jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.orm import joinedload
import traceback
import uuid
from app.models import Wishlist, Animal, User
from app import db
from . import wishlist_bp


@wishlist_bp.route("/", methods=["GET"])
@jwt_required()
def get_my_wishlist():
    """
    Get all wishlist items for the current authenticated user.
    Returns only items belonging to the current user with full animal details.
    """
    current_user_id_str = get_jwt_identity()

    # Convert string UUID to UUID object for database query
    try:
        current_user_id = uuid.UUID(current_user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    # Filter by user_id - DATA ISOLATION
    # Use joinedload to eagerly load animal relationship
    wishlist_items = (
        Wishlist.query
        .options(joinedload(Wishlist.animal))
        .filter_by(user_id=current_user_id)
        .all()
    )

    # Use the model's to_dict() which now includes animal details
    result = [item.to_dict() for item in wishlist_items]

    return jsonify(result), 200


@wishlist_bp.route("/", methods=["POST"])
@jwt_required()
def add_to_wishlist():
    """
    Add an item to the current user's wishlist.
    """
    current_user_id_str = get_jwt_identity()

    # Convert string UUID to UUID object for database query
    try:
        current_user_id = uuid.UUID(current_user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    data = request.get_json()

    # 📝 DEBUG: Log incoming request data
    print("Incoming Wishlist Data:", request.json)
    print("Current User ID:", current_user_id)

    # Input Validation: Check if animal_id is in request
    if not data or "animal_id" not in data:
        return jsonify({"message": "Missing required field: animal_id"}), 400

    animal_id = data["animal_id"]

    # Duplicate Check: Query the DB before adding
    existing = Wishlist.query.filter_by(
        user_id=current_user_id, animal_id=animal_id
    ).first()

    if existing:
        return jsonify({"message": "Item already in wishlist"}), 200

    # Create wishlist item
    wishlist_item = Wishlist(
        user_id=current_user_id,
        animal_id=animal_id,
    )

    # Exception Handling: Wrap DB commit in try-except
    try:
        db.session.add(wishlist_item)
        db.session.commit()
    except Exception as e:
        # 🔍 VERBOSE: Print full traceback to terminal
        traceback.print_exc()
        db.session.rollback()
        return jsonify({"error": "Backend Crash", "details": str(e)}), 500

    return jsonify({
        "message": "Added to wishlist",
        "item": wishlist_item.to_dict(),
    }), 201


@wishlist_bp.route("/<item_id>", methods=["DELETE"])
@jwt_required()
def remove_from_wishlist(item_id):
    """
    Remove an item from the current user's wishlist.
    Only removes if the item belongs to the current user.
    """
    current_user_id_str = get_jwt_identity()

    # Convert string UUID to UUID object for database query
    try:
        current_user_id = uuid.UUID(current_user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    # Find and delete only if owned by user - DATA ISOLATION
    item = Wishlist.query.filter_by(id=item_id, user_id=current_user_id).first()

    if not item:
        return jsonify({"message": "Wishlist item not found or access denied"}), 404

    db.session.delete(item)
    db.session.commit()

    return jsonify({"message": "Removed from wishlist"}), 200


@wishlist_bp.route("/check/<animal_id>", methods=["GET"])
@jwt_required()
def check_in_wishlist(animal_id):
    """
    Check if an animal is in the current user's wishlist.
    """
    current_user_id_str = get_jwt_identity()

    # Convert string UUID to UUID object for database query
    try:
        current_user_id = uuid.UUID(current_user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    item = Wishlist.query.filter_by(
        user_id=current_user_id, animal_id=animal_id
    ).first()

    return jsonify({"in_wishlist": item is not None}), 200


@wishlist_bp.route("/count", methods=["GET"])
@jwt_required()
def get_wishlist_count():
    """
    Get the count of wishlist items for the current user.
    """
    current_user_id_str = get_jwt_identity()

    # Convert string UUID to UUID object for database query
    try:
        current_user_id = uuid.UUID(current_user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    count = Wishlist.query.filter_by(user_id=current_user_id).count()

    return jsonify({"count": count}), 200
