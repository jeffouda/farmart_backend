from flask import request, jsonify
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
    """Create order from cart items"""
    user_id = uuid.UUID(get_jwt_identity())
    user = User.query.get(user_id)

    if not user or user.role.value != "buyer":
        return jsonify({"error": "Only buyers can create orders"}), 403

    buyer = Buyer.query.filter_by(user_id=user_id).first()
    if not buyer:
        return jsonify({"error": "Buyer profile not found"}), 404

    data = request.get_json()
    items = data.get("items", [])

    if not items:
        return jsonify({"error": "No items in order"}), 400

    # Group items by farmer
    farmer_orders = {}
    for item in items:
        # Support both 'id' and 'animal_id' from frontend
        animal_id = item.get("animal_id") or item.get("id")
        if not animal_id:
            return jsonify({"error": "Missing animal ID in item"}), 400

        animal = Animal.query.get(uuid.UUID(animal_id))
        if not animal or animal.status != "available":
            return jsonify({"error": f"Animal {animal_id} not available"}), 400

        farmer_id = str(animal.farmer_id)
        if farmer_id not in farmer_orders:
            farmer_orders[farmer_id] = []
        farmer_orders[farmer_id].append({
            "animal_id": str(animal.id),
            "species": animal.species,
            "breed": animal.breed,
            "price": float(item.get("price", animal.price)),
            "quantity": item.get("quantity", 1),
        })

    # Create separate order per farmer
    created_orders = []
    for farmer_id, order_items in farmer_orders.items():
        total = sum(item["price"] * item["quantity"] for item in order_items)

        order = Order(
            buyer_id=buyer.id,
            farmer_id=uuid.UUID(farmer_id),
            items=order_items,
            total_amount=total,
            status="pending",
            payment_status="pending",
        )
        db.session.add(order)
        db.session.flush()

        # Mark animals as pending
        for item in order_items:
            animal = Animal.query.get(uuid.UUID(item["animal_id"]))
            animal.status = "pending"

        # Create escrow record
        farmer = Farmer.query.get(uuid.UUID(farmer_id))
        escrow = EscrowRecord(
            order_id=order.id,
            amount=total,
            seller_phone=farmer.phone_number,
            status="pending",
        )
        db.session.add(escrow)

        # Notify farmer
        create_notification(
            user_id=farmer.user_id,
            type="new_order",
            title="New Order Received",
            message=f"You have a new order worth KES {total}",
            related_id=order.id,
            related_type="order",
        )

        created_orders.append({"id": str(order.id), **order.to_dict()})

    db.session.commit()

    # Return first order ID for frontend compatibility
    return jsonify({
        "orders": created_orders,
        "order_id": str(created_orders[0]["id"]) if created_orders else None,
        "message": "Order created successfully",
    }), 201


@orders_bp.route("/", methods=["GET"])
@jwt_required()
def get_orders():
    """Get user orders"""
    user_id = uuid.UUID(get_jwt_identity())
    user = User.query.get(user_id)

    if user.role.value == "buyer":
        buyer = Buyer.query.filter_by(user_id=user_id).first()
        orders = (
            Order.query
            .filter_by(buyer_id=buyer.id)
            .order_by(Order.created_at.desc())
            .all()
        )
    elif user.role.value == "farmer":
        farmer = Farmer.query.filter_by(user_id=user_id).first()
        orders = (
            Order.query
            .filter_by(farmer_id=farmer.id)
            .order_by(Order.created_at.desc())
            .all()
        )
    else:
        orders = Order.query.order_by(Order.created_at.desc()).all()

    return jsonify({"orders": [o.to_dict() for o in orders]}), 200


@orders_bp.route("/stats", methods=["GET"])
@jwt_required()
def get_order_stats():
    """Get order statistics for a user"""
    user_id = uuid.UUID(get_jwt_identity())
    user = User.query.get(user_id)

    if user.role.value == "buyer":
        buyer = Buyer.query.filter_by(user_id=user_id).first()
        orders = Order.query.filter_by(buyer_id=buyer.id).all()
    elif user.role.value == "farmer":
        farmer = Farmer.query.filter_by(user_id=user_id).first()
        orders = Order.query.filter_by(farmer_id=farmer.id).all()
    else:
        orders = Order.query.all()

    total_orders = len(orders)
    total_spent = sum(
        o.total_amount for o in orders if o.status in ["paid", "completed", "delivered"]
    )

    return jsonify({
        "total_orders": total_orders,
        "total_spent": total_spent,
    }), 200


@orders_bp.route("/<order_id>", methods=["GET"])
@jwt_required()
def get_order(order_id):
    """Get order details"""
    order_uuid = get_uuid(order_id)
    if not order_uuid:
        return jsonify({"error": "Invalid order ID format"}), 400

    order = Order.query.get(order_uuid)
    if not order:
        return jsonify({"error": "Order not found"}), 404

    return jsonify(order.to_dict()), 200


@orders_bp.route("/<order_id>/accept", methods=["PUT"])
@jwt_required()
def accept_order(order_id):
    """Farmer accepts order"""
    order_uuid = get_uuid(order_id)
    if not order_uuid:
        return jsonify({"error": "Invalid order ID format"}), 400

    user_id = uuid.UUID(get_jwt_identity())
    user = User.query.get(user_id)

    if user.role.value != "farmer":
        return jsonify({"error": "Only farmers can accept orders"}), 403

    order = Order.query.get(order_uuid)
    if not order:
        return jsonify({"error": "Order not found"}), 404

    farmer = Farmer.query.filter_by(user_id=user_id).first()
    if order.farmer_id != farmer.id:
        return jsonify({"error": "Not your order"}), 403

    order.status = "accepted"

    # Notify buyer
    create_notification(
        user_id=order.buyer.user_id,
        type="order_update",
        title="Order Accepted",
        message=f"Your order has been accepted by the farmer",
        related_id=order.id,
        related_type="order",
    )

    db.session.commit()
    return jsonify({"message": "Order accepted", "order": order.to_dict()}), 200


@orders_bp.route("/<order_id>/confirm-payment", methods=["POST"])
@jwt_required()
def confirm_payment(order_id):
    """Simulate payment confirmation (for demo without M-Pesa)"""
    order_uuid = get_uuid(order_id)
    if not order_uuid:
        return jsonify({"error": "Invalid order ID format"}), 400

    order = Order.query.get(order_uuid)
    if not order:
        return jsonify({"error": "Order not found"}), 404

    order.payment_status = "paid"
    order.status = "processing"

    # Update escrow
    if order.escrow:
        order.escrow.status = "held"

    # Mark animals as sold
    for item in order.items:
        animal = Animal.query.get(uuid.UUID(item["animal_id"]))
        if animal:
            animal.status = "sold"

    db.session.commit()
    return jsonify({"message": "Payment confirmed", "order": order.to_dict()}), 200


@orders_bp.route("/<order_id>/confirm-delivery", methods=["POST"])
@jwt_required()
def confirm_delivery(order_id):
    """Buyer confirms delivery - releases funds to farmer"""
    order_uuid = get_uuid(order_id)
    if not order_uuid:
        return jsonify({"error": "Invalid order ID format"}), 400

    user_id = uuid.UUID(get_jwt_identity())
    user = User.query.get(user_id)

    order = Order.query.get(order_uuid)
    if not order:
        return jsonify({"error": "Order not found"}), 404

    buyer = Buyer.query.filter_by(user_id=user_id).first()
    if order.buyer_id != buyer.id:
        return jsonify({"error": "Not your order"}), 403

    order.status = "completed"

    # Release escrow funds to farmer
    if order.escrow:
        order.escrow.status = "released"
        farmer = Farmer.query.get(order.farmer_id)
        farmer.wallet_balance += order.total_amount

    # Notify farmer
    create_notification(
        user_id=order.farmer.user_id,
        type="order_update",
        title="Payment Released",
        message=f"KES {order.total_amount} has been added to your wallet",
        related_id=order.id,
        related_type="order",
    )

    db.session.commit()
    return jsonify({"message": "Delivery confirmed, funds released"}), 200
