from flask import jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import uuid
from app.models import Review, Order, Buyer, Farmer, User
from app import db
from . import reviews_bp


@reviews_bp.route("/", methods=["GET"])
@jwt_required()
def get_my_reviews():
    """
    Get all reviews for the current authenticated farmer.
    Returns reviews received by the farmer.
    """
    current_user_id_str = get_jwt_identity()

    # Convert string UUID to UUID object
    try:
        current_user_id = uuid.UUID(current_user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    # Verify user is a farmer
    farmer = Farmer.query.filter_by(user_id=current_user_id).first()

    if not farmer:
        return jsonify({"message": "No farmer profile found for this user"}), 404

    # Get all reviews for this farmer (target_id is the farmer's user_id)
    reviews = (
        Review.query
        .filter_by(target_id=current_user_id)
        .order_by(Review.created_at.desc())
        .all()
    )

    # Get user info for the farmer
    user = User.query.get(current_user_id)

    return jsonify({
        "farmer": {
            "id": str(user.id),
            "full_name": user.full_name,
            "average_rating": user.average_rating,
            "review_count": user.review_count,
        },
        "reviews": [review.to_dict() for review in reviews],
    }), 200


@reviews_bp.route("/", methods=["POST"])
@jwt_required()
def create_review():
    """
    Create a review for a completed order.
    Also updates the farmer's average rating.
    """
    current_user_id_str = get_jwt_identity()

    # Convert string UUID to UUID object
    try:
        current_user_id = uuid.UUID(current_user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    data = request.get_json()

    # Validate required fields
    if not data:
        return jsonify({"error": "No data provided"}), 400

    order_id = data.get("orderId") or data.get("order_id")
    rating = data.get("rating")
    comment = data.get("feedback") or data.get("comment")
    tags = data.get("tags", [])

    if not order_id:
        return jsonify({"error": "Order ID is required"}), 400

    if not rating or not isinstance(rating, int) or rating < 1 or rating > 5:
        return jsonify({"error": "Rating must be an integer between 1 and 5"}), 400

    # Find the buyer record for this user
    buyer = Buyer.query.filter_by(user_id=current_user_id).first()

    if not buyer:
        return jsonify({"message": "No buyer profile found for this user"}), 404

    # Find order and verify ownership
    order = Order.query.filter_by(id=order_id, buyer_id=buyer.id).first()

    if not order:
        return jsonify({"message": "Order not found or access denied"}), 404

    # Check if order is delivered
    if order.status != "delivered":
        return jsonify({
            "message": f"Cannot review order. Order status is '{order.status}'. Order must be 'delivered' to leave a review."
        }), 400

    # Check if review already exists (double-submit prevention)
    if order.has_review:
        return jsonify({
            "error": "Review already exists for this order. Duplicate reviews are not allowed."
        }), 403

    # Get the farmer's user_id for the target
    farmer = Farmer.query.get(order.farmer_id)
    if not farmer:
        return jsonify({"error": "Farmer not found for this order"}), 404

    # Create the review
    review = Review(
        order_id=order.id,
        reviewer_id=current_user_id,
        target_id=farmer.user_id,
        rating=rating,
        comment=comment,
        tags=tags if isinstance(tags, list) else [],
    )

    try:
        db.session.add(review)

        # Mark order as reviewed
        order.has_review = True

        # Update farmer's rating (atomic transaction)
        _update_farmer_rating(farmer.user_id)

        db.session.commit()

        return jsonify({
            "message": "Review created successfully",
            "review": review.to_dict(),
            "farmer_new_average": float(farmer.user.average_rating)
            if farmer.user
            else 0,
            "farmer_review_count": farmer.user.review_count if farmer.user else 1,
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to create review: {str(e)}"}), 500


@reviews_bp.route("/farmer/<farmer_id>", methods=["GET"])
def get_farmer_reviews(farmer_id):
    """
    Get all reviews for a specific farmer.
    """
    try:
        farmer_uuid = uuid.UUID(farmer_id)
    except ValueError:
        return jsonify({"error": "Invalid farmer ID format"}), 400

    # Find the farmer's user record
    user = User.query.filter_by(id=farmer_uuid, role="farmer").first()

    if not user:
        return jsonify({"message": "Farmer not found"}), 404

    # Get all reviews for this farmer
    reviews = (
        Review.query
        .filter_by(target_id=farmer_uuid)
        .order_by(Review.created_at.desc())
        .all()
    )

    return jsonify({
        "farmer": {
            "id": str(user.id),
            "full_name": user.full_name,
            "average_rating": user.average_rating,
            "review_count": user.review_count,
        },
        "reviews": [review.to_dict() for review in reviews],
    }), 200


def _update_farmer_rating(farmer_user_id):
    """
    Recalculate and update the farmer's average rating.
    Called atomically when a new review is created.
    """
    user = User.query.get(farmer_user_id)
    if not user:
        return

    # Get all reviews for this farmer
    reviews = Review.query.filter_by(target_id=farmer_user_id).all()

    if not reviews:
        user.average_rating = 0.0
        user.review_count = 0
        return

    # Calculate new average
    total_ratings = sum(r.rating for r in reviews)
    user.average_rating = total_ratings / len(reviews)
    user.review_count = len(reviews)
