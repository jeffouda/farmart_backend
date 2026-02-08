from flask import jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import uuid
from app.models import Order, Buyer, User, Farmer, BargainSession, Animal
from app import db
from . import orders_bp


@orders_bp.route("/", methods=["GET"])
@jwt_required()
def get_my_orders():
    """
    Get all orders for the current authenticated user (as buyer).
    Returns only orders belonging to the current user as a buyer.
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


@orders_bp.route("/my-sales", methods=["GET"])
@jwt_required()
def get_my_sales():
    """
    Get all orders for the current authenticated user (as farmer/seller).
    Returns only orders where the current user is the farmer.
    """
    current_user_id_str = get_jwt_identity()

    # Convert string UUID to UUID object for database query
    try:
        current_user_id = uuid.UUID(current_user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    # Find the farmer record for this user
    farmer = Farmer.query.filter_by(user_id=current_user_id).first()

    if not farmer:
        return jsonify({"message": "No farmer profile found for this user"}), 404

    # Filter orders by farmer_id - DATA ISOLATION
    orders = Order.query.filter_by(farmer_id=farmer.id).all()

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

    # Get the farmer_id from the first animal item
    items = data["items"]
    farmer_id = None
    if items and len(items) > 0:
        first_animal_id = items[0].get("animal_id")
        if first_animal_id:
            animal = Animal.query.get(first_animal_id)
            if animal:
                farmer_id = animal.farmer_id

    if not farmer_id:
        return jsonify({"message": "Could not determine farmer for the order"}), 400

    # Create new order
    order = Order(
        buyer_id=buyer.id,
        farmer_id=farmer_id,
        items=items,
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


@orders_bp.route("/<order_id>", methods=["PUT"])
@jwt_required()
def update_order(order_id):
    """
    Update an existing order.
    Only allows updating status and payment_method.
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

    data = request.get_json()

    # Only allow updating status and payment_method
    if "status" in data:
        order.status = data["status"]

    if "payment_method" in data:
        order.payment_method = data["payment_method"]

    db.session.commit()

    return jsonify({
        "message": "Order updated successfully",
        "order": order.to_dict(),
    }), 200


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


@orders_bp.route("/create_from_bargain", methods=["POST"])
@jwt_required()
def create_order_from_bargain():
    """
    Create a new order from an accepted bargain session.
    Input: bargain_id
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

    # Validate required field
    if not data or "bargain_id" not in data:
        return jsonify({"message": "Missing required field: bargain_id"}), 400

    bargain_id = data["bargain_id"]

    # Fetch the bargain session
    bargain_session = BargainSession.query.get(bargain_id)
    if not bargain_session:
        return jsonify({"message": "Bargain session not found"}), 404

    # Verify the bargain session belongs to this buyer
    if bargain_session.buyer_id != buyer.id:
        return jsonify({"error": "Access denied"}), 403

    # Verify status is accepted
    if bargain_session.status != "accepted":
        return jsonify({
            "message": "Bargain session must be accepted before creating an order"
        }), 400

    # Get the animal details
    animal = Animal.query.get(bargain_session.animal_id)
    if not animal:
        return jsonify({"message": "Animal not found"}), 404

    # Use the agreed price (final_price if set, otherwise initial_offer)
    agreed_price = (
        bargain_session.final_price
        if bargain_session.final_price
        else bargain_session.initial_offer
    )

    # Create order items structure
    items = [
        {
            "animal_id": animal.id,
            "name": f"{animal.species} - {animal.breed}",
            "price": float(agreed_price),
            "quantity": 1,
        }
    ]

    # Create new order
    order = Order(
        buyer_id=buyer.id,
        bargain_id=bargain_session.id,  # Link to bargain session
        items=items,
        total_amount=agreed_price,
        status="pending",
        payment_method=data.get("payment_method", "mpesa"),
    )

    db.session.add(order)
    db.session.commit()

    return jsonify({
        "message": "Order created successfully from bargain",
        "order_id": order.id,
        "order": order.to_dict(),
    }), 201


@orders_bp.route("/<int:order_id>/confirm-receipt", methods=["POST"])
@jwt_required()
def confirm_receipt(order_id):
    """
    Confirm that the buyer has received the order.
    Updates order status to 'delivered' and releases payment to farmer.
    """
    current_user_id_str = get_jwt_identity()

    # Convert string UUID to UUID object
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

    # Validate order status - allow paid, shipped, or in_transit for testing
    if order.status not in ["paid", "shipped", "in_transit"]:
        return jsonify({
            "message": f"Cannot confirm receipt. Order status is '{order.status}'. Expected 'paid', 'shipped', or 'in_transit'."
        }), 400

    # Update order status
    order.status = "delivered"
    order.payment_status = "released"

    # Add funds to farmer's wallet
    farmer = Farmer.query.get(order.farmer_id)
    if farmer:
        farmer.wallet_balance = (farmer.wallet_balance or 0) + order.total_amount

    db.session.commit()

    return jsonify({
        "message": "Order confirmed, funds released to farmer.",
        "order": order.to_dict(),
        "farmer_received": float(order.total_amount),
    }), 200
