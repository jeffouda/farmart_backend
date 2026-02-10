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
        Order.status.notin_(["failed"])  # Include payment_pending orders (they're valid during processing)
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
        Order.status.notin_(["failed"])
    ).all()

    return jsonify([order.to_dict() for order in orders]), 200


@orders_bp.route("/", methods=["POST"])
@jwt_required()
def create_order():
    """
    Initiates M-Pesa STK Push payment first.
    Order is ONLY created in the database when payment callback confirms success.
    This prevents zombie orders on timeout/failure.
    """
    from app.models import PendingCheckout
    
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

    # Format phone number for M-Pesa
    formatted_phone = MpesaService.format_phone_number(phone)
    if not formatted_phone:
        return jsonify({"message": "Invalid phone number format. Use 07XXXXXXXX or +254XXXXXXXXX"}), 400

    items = data["items"]
    farmer_id = None
    if items and len(items) > 0:
        animal = Animal.query.get(items[0].get("animal_id"))
        if animal:
            farmer_id = animal.farmer_id

    if not farmer_id:
        return jsonify({"message": "Could not determine farmer"}), 400

    # Generate a temporary order reference for STK push
    temp_order_id = str(uuid.uuid4())

    try:
        # 1. First initiate STK Push
        stk_response = MpesaService.stk_push(
            formatted_phone, 
            int(float(data["total_amount"])), 
            temp_order_id  # Use temp_order_id as AccountReference
        )

        if stk_response.get('ResponseCode') != '0':
            current_app.logger.error(f"Mpesa STK Rejected: {stk_response}")
            return jsonify({
                "message": "M-Pesa STK Push failed", 
                "error": stk_response.get('error', 'Unknown error')
            }), 400

        checkout_request_id = stk_response.get('CheckoutRequestID')
        current_app.logger.info(f"STK Push initiated with CheckoutRequestID: {checkout_request_id}")

        # 2. Save checkout data to PendingCheckout (NOT to Order table yet)
        pending_checkout = PendingCheckout(
            id=temp_order_id,  # Use the same ID
            buyer_id=buyer.id,
            farmer_id=farmer_id,
            bargain_id=data.get("bargain_id"),
            items=items,
            total_amount=data["total_amount"],
            payment_method=data.get("payment_method", "mpesa"),
            checkout_id=checkout_request_id,
            status="pending"
        )
        db.session.add(pending_checkout)
        db.session.commit()
        current_app.logger.info(f"PendingCheckout created: {temp_order_id}")

        # 3. Return the checkout_id for polling
        # Order will be created in the callback when payment succeeds
        return jsonify({
            "message": "Payment initiated. Complete payment to create order.",
            "temp_order_id": temp_order_id,
            "checkout_id": checkout_request_id,
            "pending_amount": int(float(data["total_amount"]))
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"M-Pesa Error: {str(e)}")
        return jsonify({"message": "M-Pesa trigger failed", "error": str(e)}), 500


@orders_bp.route("/<uuid:order_id>/status", methods=["GET"])
@jwt_required()
def get_order_status(order_id):
    """Check if status changed to 'paid'."""
    from app.models import PendingCheckout
    
    # First check if it's an actual Order
    order = Order.query.get(order_id)
    if order:
        return jsonify({
            "order_id": str(order.id),
            "status": order.status, 
            "is_paid": order.status not in ["payment_pending", "payment_failed", "failed"]
        }), 200
    
    # Check if it's a PendingCheckout (not yet converted to Order)
    pending = PendingCheckout.query.get(order_id)
    if pending:
        return jsonify({
            "order_id": str(pending.id),
            "status": pending.status,
            "is_paid": pending.status == "paid",
            "message": "Payment is being processed"
        }), 200
    
    return jsonify({"error": "Not found"}), 404


@orders_bp.route("/poll-status/<checkout_id>", methods=["GET"])
@jwt_required()
def poll_checkout_status(checkout_id):
    """
    Poll this endpoint to check if payment has succeeded.
    Returns the created order_id when payment is confirmed.
    """
    from app.models import PendingCheckout
    
    pending = PendingCheckout.query.filter_by(checkout_id=checkout_id).first()
    
    if not pending:
        # Check if an order was already created
        order = Order.query.filter_by(checkout_id=checkout_id).first()
        if order:
            return jsonify({
                "status": "completed",
                "order_id": str(order.id),
                "message": "Order already created"
            }), 200
        return jsonify({"error": "Checkout not found"}), 404
    
    if pending.status == "paid":
        # Order should now exist - find it
        # The order was created with a new UUID, not the pending id
        order = Order.query.filter_by(checkout_id=checkout_id).first()
        if order:
            return jsonify({
                "status": "completed",
                "order_id": str(order.id),
                "message": "Payment confirmed"
            }), 200
        return jsonify({
            "status": "processing",
            "message": "Payment confirmed, order being created..."
        }), 200
    elif pending.status == "cancelled":
        return jsonify({
            "status": "failed",
            "message": "Payment was cancelled or failed"
        }), 400
    else:
        # Still pending
        return jsonify({
            "status": "pending",
            "message": "Waiting for payment..."
        }), 200

@orders_bp.route("/<uuid:order_id>/confirm-receipt", methods=["OPTIONS", "POST"])
@jwt_required()
def confirm_receipt(order_id):
    """
    Buyer confirms delivery:
    1. Update Order status to 'completed'
    2. Release funds to Farmer via M-Pesa B2C
    3. Update Escrow record to 'released'
    """
    from app.models import PendingCheckout
    
    # First check if it's an actual Order
    order = Order.query.get(order_id)
    
    # If not found, check if it's still pending (not yet converted)
    if not order:
        pending = PendingCheckout.query.get(order_id)
        if pending:
            return jsonify({
                "message": "Payment is still being processed. Please wait for payment confirmation.",
                "status": pending.status
            }), 400
        return jsonify({"error": "Order not found. It may have been created with an older system version."}), 404
    
    escrow = EscrowRecord.query.filter_by(order_id=order_id).first()
    
    if order.status != "paid":
        return jsonify({"message": f"Only paid orders can be confirmed. Current status: {order.status}"}), 400

    try:
        # Execute B2C Payout to release funds to farmer
        if escrow and escrow.status == "held":
            b2c_response = MpesaService.initiate_b2c(
                escrow.seller_phone, 
                float(escrow.amount), 
                str(order.id)
            )
            
            if b2c_response.get('ResponseCode') == '0':
                # B2C initiated successfully
                escrow.b2c_conversation_id = b2c_response.get('ConversationID')
                escrow.status = "releasing"
                current_app.logger.info(f"B2C initiated for Order {order.id}. ConversationID: {b2c_response.get('ConversationID')}")
            else:
                current_app.logger.error(f"B2C failed: {b2c_response}")
                # Continue anyway - the funds are in escrow, we'll update status
        
        # 1. Update Order State
        order.status = "completed"
        order.payment_status = "released"
        
        # 2. Update Farmer Wallet (as backup/fallback)
        farmer = Farmer.query.get(order.farmer_id)
        if farmer:
            farmer.wallet_balance = (farmer.wallet_balance or 0) + order.total_amount
            current_app.logger.info(f"Wallet updated for Farmer {farmer.id}")

        # 3. Update Escrow Record
        if escrow:
            if escrow.status == "held":
                escrow.status = "released"  # Mark as released (B2C will be confirmed in callback)
            current_app.logger.info(f"Escrow released for Order {order.id}")

        db.session.commit()
        return jsonify({
            "message": "Delivery confirmed and funds released to farmer.",
            "order": order.to_dict()
        }), 200

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

    orders = Order.query.filter(Order.buyer_id == buyer.id, Order.status.notin_(["failed", "payment_pending"])).all()
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
    
    # Format phone number
    formatted_phone = MpesaService.format_phone_number(phone)
    if not formatted_phone:
        return jsonify({"message": "Invalid phone number format"}), 400
    
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
        stk_response = MpesaService.stk_push(formatted_phone, int(float(agreed_price)), str(order.id))
        if stk_response.get('ResponseCode') == '0':
            order.checkout_id = stk_response.get('CheckoutRequestID')
            db.session.commit()
        else:
            current_app.logger.error(f"Bargain Mpesa Error: {stk_response}")
    except Exception as e:
        current_app.logger.error(f"Bargain Mpesa Error: {str(e)}")

    return jsonify({"message": "Bargain payment initiated", "order_id": order.id}), 201


# ==========================================
# DEBUG ENDPOINTS (For development only)
# ==========================================

@orders_bp.route("/debug/all", methods=["GET"])
def debug_all_orders():
    """Get all orders with payment_pending status - for debugging."""
    from datetime import datetime, timedelta
    
    # Get recent pending orders (last 24 hours)
    recent_orders = Order.query.filter(
        Order.status == "payment_pending",
        Order.created_at >= datetime.utcnow() - timedelta(hours=24)
    ).all()
    
    return jsonify({
        "count": len(recent_orders),
        "orders": [{
            "id": str(o.id),
            "status": o.status,
            "total_amount": float(o.total_amount),
            "checkout_id": o.checkout_id,
            "created_at": o.created_at.isoformat() if o.created_at else None
        } for o in recent_orders]
    }), 200


@orders_bp.route("/debug/checkout/<checkout_id>", methods=["GET"])
def debug_checkout_status(checkout_id):
    """Check order status by checkout_id - for debugging."""
    order = Order.query.filter_by(checkout_id=checkout_id).first()
    
    if not order:
        return jsonify({"error": "Order not found", "checkout_id": checkout_id}), 404
    
    return jsonify({
        "order_id": str(order.id),
        "status": order.status,
        "payment_status": order.payment_status,
        "checkout_id": order.checkout_id,
        "total_amount": float(order.total_amount),
        "created_at": order.created_at.isoformat() if order.created_at else None
    }), 200
