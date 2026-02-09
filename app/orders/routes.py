from flask import jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import uuid
from app.models import Order, Buyer, User, Farmer, BargainSession, Animal
from app import db
from . import orders_bp
from app.services.mpesa_service import MpesaService

@orders_bp.route("/", methods=["GET"])
@jwt_required()
def get_my_orders():
    """Get all orders for the current authenticated user (as buyer)."""
    current_user_id_str = get_jwt_identity()
    try:
        current_user_id = uuid.UUID(current_user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    buyer = Buyer.query.filter_by(user_id=current_user_id).first()
    if not buyer:
        return jsonify({"message": "No buyer profile found"}), 404

    # We only show orders that are 'paid' or further in the process
    orders = Order.query.filter(
        Order.buyer_id == buyer.id,
        Order.status != "payment_pending"
    ).all()

    return jsonify([order.to_dict() for order in orders]), 200


@orders_bp.route("/my-sales", methods=["GET"])
@jwt_required()
def get_my_sales():
    """Get all sales for the current farmer."""
    current_user_id_str = get_jwt_identity()
    try:
        current_user_id = uuid.UUID(current_user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    farmer = Farmer.query.filter_by(user_id=current_user_id).first()
    if not farmer:
        return jsonify({"message": "No farmer profile found"}), 404

    # Farmers only see orders that have actually been paid
    orders = Order.query.filter(
        Order.farmer_id == farmer.id,
        Order.status != "payment_pending"
    ).all()

    return jsonify([order.to_dict() for order in orders]), 200


@orders_bp.route("/", methods=["POST"])
@jwt_required()
def create_order():
    """Initiates payment and saves order with 'payment_pending' status."""
    current_user_id_str = get_jwt_identity()
    try:
        current_user_id = uuid.UUID(current_user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    buyer = Buyer.query.filter_by(user_id=current_user_id).first()
    if not buyer:
        return jsonify({"message": "No buyer profile found"}), 404

    data = request.get_json()
    if not data or "items" not in data or "total_amount" not in data or "phone_number" not in data:
        return jsonify({"message": "Missing required fields"}), 400

    # Determine farmer from first item
    items = data["items"]
    farmer_id = None
    if items and len(items) > 0:
        animal = Animal.query.get(items[0].get("animal_id"))
        if animal:
            farmer_id = animal.farmer_id

    if not farmer_id:
        return jsonify({"message": "Could not determine farmer"}), 400

    # 1. Save order as 'payment_pending'
    # This ensures we have the data, but it isn't "live" yet.
    order = Order(
        buyer_id=buyer.id,
        farmer_id=farmer_id,
        items=items,
        total_amount=data["total_amount"],
        status="payment_pending", 
        payment_method="mpesa",
    )

    db.session.add(order)
    db.session.commit()

    # 2. Trigger M-Pesa STK Push
    # Use the order.id as AccountReference so the callback can find this order.
    stk_response = MpesaService.stk_push(
        phone_number=data["phone_number"],
        amount=int(float(data["total_amount"])),
        order_id=str(order.id)
    )

    return jsonify({
        "message": "Payment initiated. Please enter your M-Pesa PIN.",
        "order_id": order.id,
        "mpesa_response": stk_response
    }), 201


@orders_bp.route("/<uuid:order_id>/status", methods=["GET"])
@jwt_required()
def get_order_status(order_id):
    """Polling endpoint for frontend to check if status changed to 'paid'."""
    order = Order.query.get_or_404(order_id)
    return jsonify({
        "order_id": order.id,
        "status": order.status, # Will change to 'paid' via callback
        "is_paid": order.status != "payment_pending"
    }), 200


@orders_bp.route("/<uuid:order_id>", methods=["GET"])
@jwt_required()
def get_order(order_id):
    """Get specific order details."""
    order = Order.query.get_or_404(order_id)
    return jsonify(order.to_dict()), 200


@orders_bp.route("/stats", methods=["GET"])
@jwt_required()
def get_order_stats():
    """Get stats, excluding unpaid orders."""
    current_user_id_str = get_jwt_identity()
    try:
        current_user_id = uuid.UUID(current_user_id_str)
    except:
        return jsonify({"error": "Invalid ID"}), 400

    buyer = Buyer.query.filter_by(user_id=current_user_id).first()
    if not buyer:
        return jsonify({"total_orders": 0, "total_spent": 0}), 200

    orders = Order.query.filter(
        Order.buyer_id == buyer.id, 
        Order.status != "payment_pending"
    ).all()

    return jsonify({
        "total_orders": len(orders),
        "total_spent": round(sum(float(o.total_amount) for o in orders), 2),
    }), 200


@orders_bp.route("/create_from_bargain", methods=["POST"])
@jwt_required()
def create_order_from_bargain():
    """Create order from bargain session with 'payment_pending' status."""
    current_user_id_str = get_jwt_identity()
    data = request.get_json()
    
    buyer = Buyer.query.filter_by(user_id=uuid.UUID(current_user_id_str)).first()
    bargain = BargainSession.query.get_or_404(data["bargain_id"])
    animal = Animal.query.get(bargain.animal_id)
    agreed_price = bargain.final_price or bargain.initial_offer

    order = Order(
        buyer_id=buyer.id,
        farmer_id=animal.farmer_id,
        bargain_id=bargain.id,
        items=[{"animal_id": animal.id, "name": animal.species, "price": float(agreed_price)}],
        total_amount=agreed_price,
        status="payment_pending",
        payment_method="mpesa"
    )

    db.session.add(order)
    db.session.commit()

    MpesaService.stk_push(data["phone_number"], int(float(agreed_price)), str(order.id))

    return jsonify({"message": "Bargain payment initiated", "order_id": order.id}), 201


@orders_bp.route("/confirm-receipt/<uuid:order_id>", methods=["POST"])
@jwt_required()
def confirm_receipt(order_id):
    """Buyer confirms delivery, releasing funds from escrow to farmer."""
    order = Order.query.get_or_404(order_id)
    
    if order.status != "paid":
        return jsonify({"message": "Only paid orders can be confirmed"}), 400

    order.status = "delivered"
    order.payment_status = "released"
    
    farmer = Farmer.query.get(order.farmer_id)
    farmer.wallet_balance = (farmer.wallet_balance or 0) + order.total_amount

    db.session.commit()
    return jsonify({"message": "Delivery confirmed, funds released.", "order": order.to_dict()}), 200