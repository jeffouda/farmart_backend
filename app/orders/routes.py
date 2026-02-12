from flask import request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import (
    Order,
    User,
    Buyer,
    Farmer,
    Animal,
    EscrowRecord,
    create_notification,
)
from . import orders_bp
import uuid
from datetime import datetime

# Import your MPESA service (Create this file if it doesn't exist)
# from app.services.mpesa_service import trigger_stk_push

def get_uuid(val):
    """Helper to convert string to UUID."""
    if isinstance(val, uuid.UUID):
        return val
    try:
        return uuid.UUID(val)
    except (ValueError, AttributeError):
        return None

@orders_bp.route("/", methods=["POST"])
@jwt_required()
def create_order():
    """Create order and trigger M-Pesa STK Push"""
    user_id = uuid.UUID(get_jwt_identity())
    user = User.query.get(user_id)

    if not user or user.role.value != "buyer":
        return jsonify({"error": "Only buyers can create orders"}), 403

    buyer = Buyer.query.filter_by(user_id=user_id).first()
    if not buyer:
        return jsonify({"error": "Buyer profile not found"}), 404

    data = request.get_json()
    items = data.get("items", [])
    payment_method = data.get("payment_method", "mpesa")
    # Frontend passes phone as 'phone_number' or 'phone'
    phone_number = data.get("phone_number") or data.get("phone")

    if not items:
        return jsonify({"error": "No items in order"}), 400

    # Group items by farmer
    farmer_orders = {}
    for item in items:
        animal_id = item.get("animal_id") or item.get("id")
        animal = Animal.query.get(uuid.UUID(animal_id))
        
        if not animal or animal.status != "available":
            return jsonify({"error": f"Animal {animal_id} not available"}), 400

        farmer_id = str(animal.farmer_id)
        if farmer_id not in farmer_orders:
            farmer_orders[farmer_id] = []
        farmer_orders[farmer_id].append({
            "animal_id": str(animal.id),
            "price": float(item.get("price", animal.price)),
            "quantity": item.get("quantity", 1),
        })

    created_orders = []
    total_bill = 0

    # Create separate order per farmer (Escrow Logic)
    for farmer_id, order_items in farmer_orders.items():
        sub_total = sum(item["price"] * item["quantity"] for item in order_items)
        total_bill += sub_total

        order = Order(
            buyer_id=buyer.id,
            farmer_id=uuid.UUID(farmer_id),
            items=order_items,
            total_amount=sub_total,
            status="pending",
            payment_status="pending",
        )
        db.session.add(order)
        db.session.flush() # Get ID before commit

        # Mark animals as pending
        for item in order_items:
            animal = Animal.query.get(uuid.UUID(item["animal_id"]))
            animal.status = "pending"

        # Initialize Escrow
        farmer = Farmer.query.get(uuid.UUID(farmer_id))
        escrow = EscrowRecord(
            order_id=order.id,
            amount=sub_total,
            seller_phone=farmer.phone_number,
            status="pending",
        )
        db.session.add(escrow)
        created_orders.append(order)

    # --- TRIGGER MPESA STK PUSH ---
    if payment_method == "mpesa":
        if not phone_number:
            return jsonify({"error": "Phone number required for M-Pesa"}), 400
        
        # In a real app, you'd call your Daraja Service here:
        # success = trigger_stk_push(phone_number, total_bill, created_orders[0].id)
        # For now, we log it for your dev environment:
        print(f"DEBUG: Triggering STK Push to {phone_number} for KES {total_bill}")

    db.session.commit()

    return jsonify({
        "order_id": str(created_orders[0].id),
        "message": "Order placed! Check your phone for M-Pesa prompt.",
        "total": total_bill
    }), 201

@orders_bp.route("/poll-status/<order_id>", methods=["GET"])
@jwt_required()
def poll_order_status(order_id):
    """Poll for M-Pesa callback updates"""
    order_uuid = get_uuid(order_id)
    order = Order.query.get(order_uuid)
    
    if not order:
        return jsonify({"error": "Order not found"}), 404
    
    return jsonify({
        "order_id": str(order.id),
        "status": order.status,
        "payment_status": order.payment_status, # This changes when Safaricom hits your Callback URL
    }), 200

@orders_bp.route("/<order_id>/confirm-delivery", methods=["POST"])
@jwt_required()
def confirm_delivery(order_id):
    """Buyer confirms delivery -> Release Escrow to Farmer"""
    order_uuid = get_uuid(order_id)
    order = Order.query.get(order_uuid)
    
    if not order or order.payment_status != "paid":
        return jsonify({"error": "Order not paid or not found"}), 400

    order.status = "delivered"
    
    # Release Funds
    if order.escrow:
        order.escrow.status = "released"
        farmer = Farmer.query.get(order.farmer_id)
        farmer.wallet_balance += order.total_amount

    # Notification
    create_notification(
        user_id=order.farmer.user_id,
        type="payment_release",
        title="Funds Released",
        message=f"KES {order.total_amount} released to your wallet.",
        related_id=order.id,
        related_type="order"
    )

    db.session.commit()
    return jsonify({"message": "Funds released to farmer"}), 200

# ... (Keep get_orders, get_order, and stats as they were)