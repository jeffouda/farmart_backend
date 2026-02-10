from flask import jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
import uuid
from app.models import Order, Buyer, User, Farmer, BargainSession, Animal, EscrowRecord
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
        return jsonify({"message": "No buyer profile found for this user"}), 404

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
        return jsonify({"message": "No farmer profile found for this user"}), 404

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
        return jsonify({"message": "No buyer profile found for this user"}), 404

    data = request.get_json()
    phone = data.get("phone_number") or data.get("phone")
    
    if not data or "items" not in data or "total_amount" not in data or not phone:
        return jsonify({"message": "Missing required fields"}), 400

    items = data["items"]
    farmer_id = None
    if items and len(items) > 0:
        animal = Animal.query.get(items[0].get("animal_id"))
        if animal:
            farmer_id = animal.farmer_id

    if not farmer_id:
        return jsonify({"message": "Could not determine farmer"}), 400

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

    try:
        stk_response = MpesaService.stk_push(
            phone, 
            int(float(data["total_amount"])), 
            str(order.id)
        )

        if stk_response.get('ResponseCode') == '0':
            order.checkout_id = stk_response.get('CheckoutRequestID')
            db.session.commit() 
            current_app.logger.info(f"STK Push initiated for Order {order.id}")
        else:
            current_app.logger.error(f"Mpesa Rejected: {stk_response}")

    except Exception as e:
        db.session.rollback()
        return jsonify({"message": "M-Pesa trigger failed", "error": str(e), "order_id": order.id}), 201

    return jsonify({
        "message": "Payment initiated",
        "order_id": order.id,
        "mpesa_response": stk_response
    }), 201


@orders_bp.route("/<uuid:order_id>/status", methods=["GET"])
@jwt_required()
def get_order_status(order_id):
    """Check if status changed to 'paid'."""
    order = Order.query.get_or_404(order_id)
    return jsonify({
        "order_id": order.id,
        "status": order.status, 
        "is_paid": order.status not in ["payment_pending", "payment_failed"]
    }), 200

@orders_bp.route("/<uuid:order_id>/confirm-receipt", methods=["POST"])
@jwt_required()
def confirm_receipt(order_id):
    """
    Buyer confirms delivery:
    1. Update Order status to 'completed'
    2. Move funds to Farmer wallet
    3. Update Escrow record to 'released'
    """
    order = Order.query.get_or_404(order_id)
    
    if order.status != "paid":
        return jsonify({"message": "Only paid orders can be confirmed for delivery"}), 400

    try:
        # 1. Update Order State
        order.status = "completed"
        order.payment_status = "released"
        
        # 2. Update Farmer Wallet
        farmer = Farmer.query.get(order.farmer_id)
        if farmer:
            farmer.wallet_balance = (farmer.wallet_balance or 0) + order.total_amount
            current_app.logger.info(f"Wallet updated for Farmer {farmer.id}")

        # 3. Update Escrow Record
        escrow = EscrowRecord.query.filter_by(order_id=order.id).first()
        if escrow:
            escrow.status = "released"
            current_app.logger.info(f"Escrow released for Order {order.id}")

        db.session.commit()
        return jsonify({"message": "Delivery confirmed and funds released.", "order": order.to_dict()}), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error releasing funds: {str(e)}")
        return jsonify({"error": "Internal server error during fund release"}), 500


@orders_bp.route("/<uuid:order_id>", methods=["GET"])
@jwt_required()
def get_order(order_id):
    order = Order.query.get_or_404(order_id)
    return jsonify(order.to_dict()), 200


@orders_bp.route("/stats", methods=["GET"])
@jwt_required()
def get_order_stats():
    current_user_id_str = get_jwt_identity()
    buyer = Buyer.query.filter_by(user_id=uuid.UUID(current_user_id_str)).first()
    if not buyer:
        return jsonify({"total_orders": 0, "total_spent": 0}), 200

    orders = Order.query.filter(Order.buyer_id == buyer.id, Order.status != "payment_pending").all()
    return jsonify({
        "total_orders": len(orders),
        "total_spent": round(sum(float(o.total_amount) for o in orders), 2),
    }), 200


@orders_bp.route("/create_from_bargain", methods=["POST"])
@jwt_required()
def create_order_from_bargain():
    current_user_id_str = get_jwt_identity()
    data = request.get_json()
    phone = data.get("phone_number") or data.get("phone")
    
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

    try:
        stk_response = MpesaService.stk_push(phone, int(float(agreed_price)), str(order.id))
        if stk_response.get('ResponseCode') == '0':
            order.checkout_id = stk_response.get('CheckoutRequestID')
            db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Bargain Mpesa Error: {str(e)}")

    return jsonify({"message": "Bargain payment initiated", "order_id": order.id}), 201