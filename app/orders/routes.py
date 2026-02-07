from flask import jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import uuid
from app.models import Order, Buyer, User
from app import db
from . import orders_bp


@orders_bp.route("/", methods=["GET"])
@jwt_required()
def get_my_orders():
    """
    Get all orders for the current authenticated user.
    Returns only orders belonging to the current user.
    """
    current_user_id_str = get_jwt_identity()

    # Convert string UUID to UUID object for database query
    try:
        current_user_id = uuid.UUID(current_user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    # Find the buyer record for this user
    buyer = Buyer.query.filter_by(user_id=current_user_id).first()

    if not buyer:
        return jsonify({"message": "No buyer profile found for this user"}), 404

    # Filter orders by buyer_id - DATA ISOLATION
    orders = Order.query.filter_by(buyer_id=buyer.id).all()

    return jsonify([order.to_dict() for order in orders]), 200


@orders_bp.route("/", methods=["POST"])
@jwt_required()
def create_order():
    """
    Create a new order for the current authenticated user.
    """
    current_user_id_str = get_jwt_identity()

    # Convert string UUID to UUID object for database query
    try:
        current_user_id = uuid.UUID(current_user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    # Find the buyer record for this user
    buyer = Buyer.query.filter_by(user_id=current_user_id).first()

    if not buyer:
        return jsonify({"message": "No buyer profile found for this user"}), 404

    data = request.get_json()

    # Validate required fields
    if not data or "items" not in data or "total_amount" not in data:
        return jsonify({"message": "Missing required fields: items, total_amount"}), 400

    # Create new order
    order = Order(
        buyer_id=buyer.id,
        items=data["items"],
        total_amount=data["total_amount"],
        status=data.get("status", "paid"),
        payment_method=data.get("payment_method", "mpesa"),
    )

    db.session.add(order)
    db.session.commit()

    return jsonify({
        "message": "Order created successfully",
        "order": order.to_dict(),
    }), 201


@orders_bp.route("/<order_id>", methods=["GET"])
@jwt_required()
def get_order(order_id):
    """
    Get a specific order by ID.
    Only returns the order if it belongs to the current user.
    """
    current_user_id_str = get_jwt_identity()

    # Convert string UUID to UUID object for database query
    try:
        current_user_id = uuid.UUID(current_user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    # Find the buyer record for this user
    buyer = Buyer.query.filter_by(user_id=current_user_id).first()

    if not buyer:
        return jsonify({"message": "No buyer profile found for this user"}), 404

    # Find order and verify ownership
    order = Order.query.filter_by(id=order_id, buyer_id=buyer.id).first()

    if not order:
        return jsonify({"message": "Order not found or access denied"}), 404

    return jsonify(order.to_dict()), 200


@orders_bp.route("/stats", methods=["GET"])
@jwt_required()
def get_order_stats():
    """
    Get order statistics for the current user.
    Returns total orders and total spent.
    """
    current_user_id_str = get_jwt_identity()

    # Convert string UUID to UUID object for database query
    try:
        current_user_id = uuid.UUID(current_user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    buyer = Buyer.query.filter_by(user_id=current_user_id).first()

    if not buyer:
        return jsonify({"total_orders": 0, "total_spent": 0}), 200

    # Get count and sum filtered by user
    orders = Order.query.filter_by(buyer_id=buyer.id).all()

    total_orders = len(orders)
    total_spent = sum(float(o.total_amount) for o in orders)

    return jsonify({
        "total_orders": total_orders,
        "total_spent": round(total_spent, 2),
    }), 200
