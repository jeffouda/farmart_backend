from flask import jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from functools import wraps
import uuid
from app.models import Order, Buyer, User, Farmer, BargainSession, Animal, EscrowRecord
from app import db
from . import orders_bp
from app.services.mpesa_service import MpesaService
from app.models import create_notification


def get_uuid(val):
    """Helper to convert string to UUID."""
    if isinstance(val, uuid.UUID):
        return val
    try:
        return uuid.UUID(val)
    except ValueError:
        return None


def admin_required(f):
    """Decorator to require admin role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        current_user_id_str = get_jwt_identity()
        user_uuid = get_uuid(current_user_id_str)
        if not user_uuid:
            return jsonify({"error": "Invalid user ID format"}), 400
        
        user = User.query.get(user_uuid)
        if not user or user.role.value != "admin":
            return jsonify({"error": "Admin access required"}), 403
        
        return f(*args, **kwargs)
    return decorated_function


@orders_bp.route("/admin/all", methods=["GET"])
@jwt_required()
@admin_required
def get_all_orders_admin():
    """Get all orders for admin dashboard."""
    orders = Order.query.order_by(Order.created_at.desc()).all()
    
    # Build response with buyer and farmer info
    orders_data = []
    for order in orders:
        # Get buyer info
        buyer = Buyer.query.get(order.buyer_id)
        buyer_user = User.query.get(buyer.user_id) if buyer else None
        
        # Get farmer info
        farmer = Farmer.query.get(order.farmer_id)
        farmer_user = User.query.get(farmer.user_id) if farmer else None
        
        order_dict = order.to_dict()
        order_dict.update({
            "buyer_name": buyer_user.full_name if buyer_user else "Unknown",
            "buyer_email": buyer_user.email if buyer_user else "Unknown",
            "farmer_name": farmer.farm_name if farmer else "Unknown",
            "farmer_location": farmer.location if farmer else "Unknown",
        })
        orders_data.append(order_dict)
    
    return jsonify(orders_data), 200


# Admin User Management Endpoints
@orders_bp.route("/admin/farmers", methods=["GET"])
@jwt_required()
@admin_required
def get_all_farmers_admin():
    """Get all farmers for admin dashboard."""
    farmers = Farmer.query.all()
    
    farmers_data = []
    for farmer in farmers:
        user = User.query.get(farmer.user_id)
        # Count animals
        animal_count = Animal.query.filter_by(farmer_id=farmer.id).count()
        
        farmers_data.append({
            "id": str(farmer.id),
            "user_id": str(farmer.user_id),
            "name": user.full_name if user else farmer.farm_name,
            "email": user.email if user else None,
            "location": farmer.location,
            "phone_number": farmer.phone_number,
            "status": "pending" if not farmer.is_verified else "active",
            "rating": user.average_rating if user else 0,
            "joinDate": farmer.created_at.strftime("%Y-%m-%d") if farmer.created_at else None,
            "livestockCount": animal_count,
            "verified": farmer.is_verified,
            "is_active": user.is_active if user else True,
        })
    
    return jsonify(farmers_data), 200


@orders_bp.route("/admin/buyers", methods=["GET"])
@jwt_required()
@admin_required
def get_all_buyers_admin():
    """Get all buyers for admin dashboard."""
    buyers = Buyer.query.all()
    
    buyers_data = []
    for buyer in buyers:
        user = User.query.get(buyer.user_id)
        # Count orders
        order_count = Order.query.filter_by(buyer_id=buyer.id).count()
        
        buyers_data.append({
            "id": str(buyer.id),
            "user_id": str(buyer.user_id),
            "name": user.full_name if user else "Unknown",
            "email": user.email if user else None,
            "location": user.location or buyer.delivery_address or "Unknown",
            "status": "active" if user.is_active else "suspended",
            "totalOrders": order_count,
            "joinDate": buyer.created_at.strftime("%Y-%m-%d") if buyer.created_at else None,
            "is_active": user.is_active if user else True,
        })
    
    return jsonify(buyers_data), 200


@orders_bp.route("/admin/farmers/<string:farmer_user_id>/verify", methods=["POST"])
@jwt_required()
@admin_required
def verify_farmer_admin(farmer_user_id):
    """Verify a farmer (mark as verified)."""
    user_uuid = get_uuid(farmer_user_id)
    if not user_uuid:
        return jsonify({"error": "Invalid user ID format"}), 400
    
    # Find farmer by user_id
    farmer = Farmer.query.filter_by(user_id=user_uuid).first()
    if not farmer:
        return jsonify({"error": "Farmer not found"}), 404
    
    farmer.is_verified = True
    db.session.commit()
    
    return jsonify({"message": "Farmer verified successfully"}), 200


@orders_bp.route("/admin/users/<string:user_id>/suspend", methods=["POST"])
@jwt_required()
@admin_required
def suspend_user_admin(user_id):
    """Suspend a user (farmer or buyer)."""
    user_uuid = get_uuid(user_id)
    if not user_uuid:
        return jsonify({"error": "Invalid user ID format"}), 400
    
    user = User.query.get(user_uuid)
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    user.is_active = False
    db.session.commit()
    
    return jsonify({"message": "User suspended successfully"}), 200


@orders_bp.route("/admin/users/<string:user_id>/activate", methods=["POST"])
@jwt_required()
@admin_required
def activate_user_admin(user_id):
    """Activate a suspended user."""
    user_uuid = get_uuid(user_id)
    if not user_uuid:
        return jsonify({"error": "Invalid user ID format"}), 400
    
    user = User.query.get(user_uuid)
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    user.is_active = True
    db.session.commit()
    
    return jsonify({"message": "User activated successfully"}), 200


@orders_bp.route("/", methods=["GET"])
@jwt_required()
def get_my_orders():
    """Get all orders for the current authenticated user (as buyer)."""
    current_user_id_str = get_jwt_identity()
    user_uuid = get_uuid(current_user_id_str)
    if not user_uuid:
        return jsonify({"error": "Invalid user ID format"}), 400

    buyer = Buyer.query.filter_by(user_id=user_uuid).first()
    if not buyer:
        return jsonify({"message": "No buyer profile found for this user"}), 404

    orders = Order.query.filter(Order.buyer_id == buyer.id).all()

    return jsonify([order.to_dict() for order in orders]), 200


@orders_bp.route("/my-sales", methods=["GET"])
@jwt_required()
def get_my_sales():
    """Get all sales for the current farmer."""
    current_user_id_str = get_jwt_identity()
    user_uuid = get_uuid(current_user_id_str)
    if not user_uuid:
        return jsonify({"error": "Invalid user ID format"}), 400

    farmer = Farmer.query.filter_by(user_id=user_uuid).first()
    if not farmer:
        return jsonify({"message": "No farmer profile found for this user"}), 404

    orders = Order.query.filter(Order.farmer_id == farmer.id).all()
    
    # Enrich orders with buyer info and animal images
    orders_data = []
    for order in orders:
        order_dict = order.to_dict()
        
        # Get buyer info
        buyer = Buyer.query.get(order.buyer_id)
        buyer_user = User.query.get(buyer.user_id) if buyer else None
        order_dict["buyer"] = {
            "full_name": buyer_user.full_name if buyer_user else "Unknown",
            "phone_number": buyer_user.phone_number if buyer_user else None,
        }
        
        # Enrich items with animal images
        enriched_items = []
        for item in order.items:
            enriched_item = dict(item)
            if item.get("animal_id"):
                animal_uuid = get_uuid(item["animal_id"])
                if animal_uuid:
                    animal = Animal.query.get(animal_uuid)
                    if animal:
                        enriched_item["image_url"] = animal.image_url
                        enriched_item["species"] = animal.species
            enriched_items.append(enriched_item)
        order_dict["items"] = enriched_items
        
        orders_data.append(order_dict)

    return jsonify(orders_data), 200


@orders_bp.route("/", methods=["POST"])
@jwt_required()
def create_order():
    """Initiates payment and saves order with 'payment_pending' status."""
    current_user_id_str = get_jwt_identity()
    user_uuid = get_uuid(current_user_id_str)
    if not user_uuid:
        return jsonify({"error": "Invalid user ID format"}), 400

    buyer = Buyer.query.filter_by(user_id=user_uuid).first()
    if not buyer:
        return jsonify({"message": "No buyer profile found for this user"}), 404

    data = request.get_json()
    phone = data.get("phone_number") or data.get("phone")

    if not data or "items" not in data or "total_amount" not in data or not phone:
        return jsonify({"message": "Missing required fields"}), 400

    items = data["items"]
    farmer_id = None
    if items and len(items) > 0:
        animal_id_str = items[0].get("animal_id")
        if animal_id_str:
            animal_uuid = get_uuid(animal_id_str)
            if animal_uuid:
                animal = Animal.query.filter_by(id=animal_uuid).first()
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

    # Create notifications
    try:
        # Get farmer's user_id
        farmer = Farmer.query.get(farmer_id)
        if farmer:
            # Notify farmer
            create_notification(
                user_id=farmer.user_id,
                type='new_order',
                title='New Order Received!',
                message=f'You received a new order worth KES {float(data["total_amount"]):,.0f}',
                related_id=str(order.id),
                related_type='order'
            )
        # Notify buyer
        create_notification(
            user_id=user_uuid,
            type='order_placed',
            title='Order Placed Successfully',
            message=f'Your order has been placed successfully. Total: KES {float(data["total_amount"]):,.0f}',
            related_id=str(order.id),
            related_type='order'
        )
    except Exception as e:
        current_app.logger.error(f"Error creating notifications: {str(e)}")

    mpesa_response = None
    try:
        stk_response = MpesaService.stk_push(
            phone, int(float(data["total_amount"])), str(order.id)
        )

        if stk_response.get("ResponseCode") == "0":
            order.checkout_id = stk_response.get("CheckoutRequestID")
            db.session.commit()
            current_app.logger.info(f"STK Push initiated for Order {order.id}")
            mpesa_response = stk_response
        else:
            current_app.logger.error(f"Mpesa Rejected: {stk_response}")
            mpesa_response = stk_response

    except Exception as e:
        current_app.logger.error(f"M-Pesa Error: {str(e)}")
        # Order is still created, just M-Pesa failed
        mpesa_response = {"error": str(e)}

    return jsonify({
        "message": "Order created",
        "order_id": str(order.id),
        "mpesa_response": mpesa_response,
    }), 201


@orders_bp.route("/<string:order_id>/status", methods=["GET"])
@jwt_required()
def get_order_status(order_id):
    """Check if status changed to 'paid'."""
    order_uuid = get_uuid(order_id)
    if not order_uuid:
        return jsonify({"error": "Invalid order ID format"}), 400

    order = Order.query.filter_by(id=order_uuid).first()
    if not order:
        return jsonify({"error": "Order not found"}), 404

    return jsonify({
        "order_id": str(order.id),
        "status": order.status,
        "is_paid": order.status not in ["payment_pending", "payment_failed"],
    }), 200


@orders_bp.route("/<string:order_id>/status", methods=["PUT"])
@jwt_required()
def update_order_status(order_id):
    """Update order status (farmer marks as shipped)."""
    order_uuid = get_uuid(order_id)
    if not order_uuid:
        return jsonify({"error": "Invalid order ID format"}), 400
    
    order = Order.query.filter_by(id=order_uuid).first()
    if not order:
        return jsonify({"error": "Order not found"}), 404
    
    data = request.get_json()
    new_status = data.get("status")
    
    # Map frontend status values to backend status values
    status_map = {
        "shipped": "in_transit",
        "delivered": "completed",
    }
    actual_status = status_map.get(new_status, new_status)
    
    # Validate status transition
    valid_transitions = {
        "pending": ["in_transit"],
        "processing": ["in_transit"],
        "payment_pending": ["in_transit"],  # Allow shipping before payment completes
        "in_transit": ["completed"],  # Buyer confirms delivery
    }
    
    if new_status not in ["shipped", "in_transit"]:
        return jsonify({"error": "Invalid status update. Use 'shipped' or 'in_transit'"}), 400
    
    # Check if transition is valid
    if order.status not in valid_transitions:
        return jsonify({"error": f"Cannot update order from {order.status} to {new_status}"}), 400
    
    if new_status not in valid_transitions.get(order.status, []):
        return jsonify({"error": f"Cannot transition from {order.status} to {new_status}"}), 400
    
    # Map to actual status value
    actual_status = "in_transit"
    order.status = actual_status
    db.session.commit()
    
    return jsonify({
        "message": f"Order status updated to {actual_status}",
        "order": order.to_dict()
    }), 200


@orders_bp.route("/<string:order_id>/confirm-receipt", methods=["POST"])
@jwt_required()
def confirm_receipt(order_id):
    """
    Buyer confirms delivery:
    1. Update Order status to 'completed'
    2. Move funds to Farmer wallet
    3. Update Escrow record to 'released'
    """
    order_uuid = get_uuid(order_id)
    if not order_uuid:
        return jsonify({"error": "Invalid order ID format"}), 400

    order = Order.query.filter_by(id=order_uuid).first()
    if not order:
        return jsonify({"error": "Order not found"}), 404

    if order.status not in ["paid", "payment_pending", "in_transit"]:
        return jsonify({
            "message": "Only paid, pending payment, or shipped orders can be confirmed for delivery"
        }), 400

    try:
        # 1. Update Order State
        order.status = "completed"
        order.payment_status = "released"

        # 2. Update Farmer Wallet
        farmer = Farmer.query.filter_by(id=order.farmer_id).first()
        if farmer:
            farmer.wallet_balance = (farmer.wallet_balance or 0) + order.total_amount
            current_app.logger.info(f"Wallet updated for Farmer {farmer.id}")

        # 3. Update Escrow Record
        escrow = EscrowRecord.query.filter_by(order_id=order.id).first()
        if escrow:
            escrow.status = "released"
            current_app.logger.info(f"Escrow released for Order {order.id}")

        db.session.commit()
        return jsonify({
            "message": "Delivery confirmed and funds released.",
            "order": order.to_dict(),
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error releasing funds: {str(e)}")
        return jsonify({"error": "Internal server error during fund release"}), 500


@orders_bp.route("/<string:order_id>", methods=["GET"])
@jwt_required()
def get_order(order_id):
    """Get a single order by ID."""
    order_uuid = get_uuid(order_id)
    if not order_uuid:
        return jsonify({"error": "Invalid order ID format"}), 400

    order = Order.query.filter_by(id=order_uuid).first()
    if not order:
        return jsonify({"error": "Order not found"}), 404
    
    # Get farmer info
    farmer = Farmer.query.get(order.farmer_id)
    farmer_user = User.query.get(farmer.user_id) if farmer else None
    
    order_dict = order.to_dict()
    order_dict.update({
        "farmer_name": farmer_user.full_name if farmer_user else "Unknown Farmer",
        "farmer": farmer_user.full_name if farmer_user else "Unknown Farmer",
    })
    
    return jsonify(order_dict), 200


@orders_bp.route("/stats", methods=["GET"])
@jwt_required()
def get_order_stats():
    current_user_id_str = get_jwt_identity()
    user_uuid = get_uuid(current_user_id_str)
    if not user_uuid:
        return jsonify({"error": "Invalid user ID format"}), 400

    buyer = Buyer.query.filter_by(user_id=user_uuid).first()
    if not buyer:
        return jsonify({"total_orders": 0, "total_spent": 0}), 200

    orders = Order.query.filter(Order.buyer_id == buyer.id).all()
    return jsonify({
        "total_orders": len(orders),
        "total_spent": round(sum(float(o.total_amount) for o in orders), 2),
    }), 200


@orders_bp.route("/create_from_bargain", methods=["POST"])
@jwt_required()
def create_order_from_bargain():
    current_user_id_str = get_jwt_identity()
    user_uuid = get_uuid(current_user_id_str)
    if not user_uuid:
        return jsonify({"error": "Invalid user ID format"}), 400

    data = request.get_json()
    phone = data.get("phone_number") or data.get("phone")

    buyer = Buyer.query.filter_by(user_id=user_uuid).first()
    if not buyer:
        return jsonify({"message": "No buyer profile found"}), 404

    bargain_id_str = data.get("bargain_id")
    if bargain_id_str:
        try:
            bargain_id_int = int(bargain_id_str)
        except ValueError:
            return jsonify({"error": "Invalid bargain ID format"}), 400
    else:
        return jsonify({"error": "bargain_id is required"}), 400

    bargain = BargainSession.query.filter_by(id=bargain_id_int).first()
    if not bargain:
        return jsonify({"error": "Bargain not found"}), 404

    animal_uuid = get_uuid(bargain.animal_id)
    if not animal_uuid:
        return jsonify({"error": "Invalid animal ID"}), 400

    animal = Animal.query.filter_by(id=animal_uuid).first()
    if not animal:
        return jsonify({"error": "Animal not found"}), 404

    agreed_price = bargain.final_price or bargain.initial_offer

    order = Order(
        buyer_id=buyer.id,
        farmer_id=animal.farmer_id,
        bargain_id=bargain.id,
        items=[
            {
                "animal_id": str(animal.id),
                "name": animal.species,
                "price": float(agreed_price),
            }
        ],
        total_amount=agreed_price,
        status="payment_pending",
        payment_method="mpesa",
    )

    db.session.add(order)
    db.session.commit()

    mpesa_response = None
    try:
        stk_response = MpesaService.stk_push(
            phone, int(float(agreed_price)), str(order.id)
        )
        if stk_response.get("ResponseCode") == "0":
            order.checkout_id = stk_response.get("CheckoutRequestID")
            db.session.commit()
            mpesa_response = stk_response
        else:
            current_app.logger.error(f"Mpesa Rejected: {stk_response}")
            mpesa_response = stk_response
    except Exception as e:
        current_app.logger.error(f"Bargain Mpesa Error: {str(e)}")
        mpesa_response = {"error": str(e)}

    return jsonify({
        "message": "Bargain payment initiated",
        "order_id": str(order.id),
        "mpesa_response": mpesa_response,
    }), 201
