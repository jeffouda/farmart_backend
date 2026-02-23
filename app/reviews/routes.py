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

    user = User.query.filter_by(id=str(current_user_id)).first()

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

    if order.has_review:
        # Check if user wants to update existing review
        existing_review = Review.query.filter_by(order_id=order.id, reviewer_id=current_user_id).first()
        if existing_review:
            # Update existing review
            existing_review.rating = rating
            existing_review.comment = comment
            existing_review.tags = tags if isinstance(tags, list) else []
            db.session.commit()
            return jsonify({
                "message": "Review updated successfully",
                "review": existing_review.to_dict(),
            }), 200
        return jsonify({"error": "Review already exists for this order"}), 403

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
        current_app.logger.info(
            f"Creating review for order {order.id}, rating={rating}"
        )

        db.session.add(review)
        order.has_review = True
        _update_farmer_rating(farmer.user_id)
        current_app.logger.info(f"Review added and farmer rating updated")

        # --- ESCROW AUTO-RELEASE LOGIC ---
        payout_triggered = False
        if rating >= 4:
            escrow = EscrowRecord.query.filter_by(
                order_id=order.id, status="held"
            ).first()
            current_app.logger.info(
                f"Checking escrow for order {order.id}: escrow={escrow}"
            )
            if escrow:
                current_app.logger.info(
                    f"Found held escrow for order {order.id}, triggering B2C payout"
                )
                try:
                    # Trigger M-Pesa B2C Payout
                    payout_res = MpesaService.initiate_b2c(
                        escrow.seller_phone, escrow.amount, order.id
                    )

                    if payout_res.get("ResponseCode") == "0":
                        escrow.status = "releasing"
                        escrow.b2c_conversation_id = payout_res.get("ConversationID")
                        order.status = "completed"
                        payout_triggered = True
                        current_app.logger.info(
                            f"Auto-payout triggered for Order {order.id} due to {rating}-star review."
                        )
                    else:
                        current_app.logger.warning(
                            f"M-Pesa B2C failed for Order {order.id}: {payout_res}"
                        )
                except Exception as mpesa_error:
                    current_app.logger.error(f"M-Pesa B2C error: {str(mpesa_error)}")
                    # Continue without failing the review
                    payout_triggered = False

        db.session.commit()

        return jsonify({
            "message": "Review created successfully",
            "payout_initiated": payout_triggered,
            "review": review.to_dict(),
            "farmer_new_average": float(farmer.user.average_rating)
            if farmer.user
            else 0,
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Review creation failed: {str(e)}")
        return jsonify({"error": f"Failed to process review: {str(e)}"}), 500


@reviews_bp.route("/farmer/<farmer_id>", methods=["GET"])
def get_farmer_reviews(farmer_id):
    """
    Get all reviews for a specific farmer.
    """
    try:
        farmer_uuid = uuid.UUID(farmer_id)
    except ValueError:
        return jsonify({"error": "Invalid farmer ID format"}), 400

    user = User.query.filter_by(id=farmer_uuid, role="farmer").first()
    if not user:
        return jsonify({"message": "Farmer not found"}), 404

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
    """
    user = User.query.filter_by(id=str(farmer_user_id)).first()
    if not user:
        return

    reviews = Review.query.filter_by(target_id=farmer_user_id).all()

    if not reviews:
        user.average_rating = 0.0
        user.review_count = 0
        return

    total_ratings = sum(r.rating for r in reviews)
    user.average_rating = total_ratings / len(reviews)
    user.review_count = len(reviews)
