from flask import jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
import uuid
from app.models import Review, Order, Buyer, Farmer, User, EscrowRecord, db
from app.services.mpesa_service import MpesaService
from . import reviews_bp
@reviews_bp.route("/", methods=["GET"])
@jwt_required()
def get_my_reviews():
    """
    Get all reviews for the current authenticated farmer.
    Returns reviews received by the farmer.
    """
    current_user_id_str = get_jwt_identity()

    try:
        current_user_id = uuid.UUID(current_user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    farmer = Farmer.query.filter_by(user_id=current_user_id).first()
    if not farmer:
        return jsonify({"message": "No farmer profile found for this user"}), 404
     reviews = (
        Review.query
        .filter_by(target_id=current_user_id)
        .order_by(Review.created_at.desc())
        .all()
    )

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
    Create a review and automatically release escrow funds if rating is >= 4.
    """
    current_user_id_str = get_jwt_identity()

    try:
        current_user_id = uuid.UUID(current_user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400
     data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    order_id = data.get("orderId") or data.get("order_id")
    rating = data.get("rating")
    comment = data.get("feedback") or data.get("comment")
    tags = data.get("tags", [])

    if not order_id:
        return jsonify({"error": "Order ID is required"}), 400
    # Convert order_id to UUID
    try:
        order_uuid = uuid.UUID(order_id)
    except ValueError:
        return jsonify({"error": "Invalid order ID format"}), 400

    if not rating or not isinstance(rating, int) or rating < 1 or rating > 5:
        return jsonify({"error": "Rating must be an integer between 1 and 5"}), 400
     buyer = Buyer.query.filter_by(user_id=current_user_id).first()
    if not buyer:
        return jsonify({"message": "No buyer profile found for this user"}), 404

    order = Order.query.filter_by(id=order_uuid, buyer_id=buyer.id).first()
    if not order:
        return jsonify({"message": "Order not found or access denied"}), 404

    if order.status not in ["delivered", "completed"]:
        return jsonify({
            "message": f"Order must be 'delivered' or 'completed' to leave a review. Current status: {order.status}"
        }), 400




