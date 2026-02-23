from flask import request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import User, Farmer, Buyer, Order, Animal, Dispute
from . import admin_bp
import uuid


def admin_required():
    """Check if user is admin"""
    user_id = uuid.UUID(get_jwt_identity())
    user = User.query.filter_by(id=str(user_id)).first()
    if not user or user.role != "admin":
        return None
    return user


@admin_bp.route("/stats", methods=["GET"])
@jwt_required()
def get_stats():
    """Get platform statistics"""
    user = admin_required()
    if not user:
        return jsonify({"error": "Admin access required"}), 403
    
    try:
        stats = {
            "total_users": User.query.count(),
            "total_farmers": Farmer.query.count(),
            "total_buyers": Buyer.query.count(),
            "total_livestock": Animal.query.count(),
            "available_livestock": Animal.query.filter_by(status="available").count(),
            "total_orders": Order.query.count(),
            "pending_orders": Order.query.filter_by(status="pending").count(),
            "completed_orders": Order.query.filter_by(status="completed").count(),
        }
        
        # Try to get disputes count, but don't fail if table doesn't exist
        try:
            stats["open_disputes"] = Dispute.query.filter_by(status="open").count()
        except:
            stats["open_disputes"] = 0
            
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/users", methods=["GET"])
@jwt_required()
def get_users():
    """Get all users"""
    user = admin_required()
    if not user:
        return jsonify({"error": "Admin access required"}), 403
    
    role = request.args.get("role")
    query = User.query
    if role:
        query = query.filter_by(role=role)
    
    users = query.all()
    return jsonify({
        "users": [{
            "id": str(u.id),
            "email": u.email,
            "role": u.role,
            "full_name": u.full_name,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None
        } for u in users]
    }), 200


@admin_bp.route("/orders/all", methods=["GET"])
@jwt_required()
def get_all_orders_admin():
    """Get all orders for admin dashboard"""
    user = admin_required()
    if not user:
        return jsonify({"error": "Admin access required"}), 403
    
    try:
        orders = Order.query.order_by(Order.created_at.desc()).all()
        
        orders_data = []
        for order in orders:
            order_dict = order.to_dict()
            
            # Get buyer info
            buyer = Buyer.query.get(order.buyer_id)
            if buyer:
                buyer_user = User.query.filter_by(id=str(buyer.user_id)).first()
                order_dict["buyer_name"] = buyer_user.full_name if buyer_user else "Unknown"
                order_dict["buyer_email"] = buyer_user.email if buyer_user else None
            
            # Get farmer info
            farmer = Farmer.query.get(order.farmer_id)
            if farmer:
                farmer_user = User.query.filter_by(id=str(farmer.user_id)).first()
                order_dict["farmer_name"] = farmer_user.full_name if farmer_user else "Unknown"
                order_dict["farmer_location"] = farmer.location if farmer else None
            
            orders_data.append(order_dict)
        
        return jsonify(orders_data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/farmers", methods=["GET"])
@jwt_required()
def get_all_farmers():
    """Get all farmers for admin"""
    user = admin_required()
    if not user:
        return jsonify({"error": "Admin access required"}), 403
    
    try:
        farmers = Farmer.query.all()
        
        farmers_data = []
        for farmer in farmers:
            farmer_user = User.query.filter_by(id=str(farmer.user_id)).first()
            animals_count = Animal.query.filter_by(farmer_id=farmer.id).count()
            orders_count = Order.query.filter_by(farmer_id=farmer.id).count()
            
            farmers_data.append({
                "id": str(farmer.id),
                "user_id": str(farmer.user_id),
                "name": farmer_user.full_name if farmer_user else "Unknown",
                "email": farmer_user.email if farmer_user else None,
                "phone_number": farmer.phone_number,
                "location": farmer.location,
                "farm_name": farmer.farm_name,
                "status": "pending" if not farmer.is_verified else "active",
                "is_verified": farmer.is_verified,
                "rating": float(farmer_user.average_rating) if farmer_user and farmer_user.average_rating else 0,
                "livestockCount": animals_count,
                "totalOrders": orders_count,
                "joinDate": farmer.created_at.isoformat() if farmer.created_at else None
            })
        
        return jsonify(farmers_data), 200
    except Exception as e:
        current_app.logger.error(f"Error fetching farmers: {str(e)}")
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/buyers", methods=["GET"])
@jwt_required()
def get_all_buyers():
    """Get all buyers for admin"""
    user = admin_required()
    if not user:
        return jsonify({"error": "Admin access required"}), 403
    
    try:
        buyers = Buyer.query.all()
        
        buyers_data = []
        for buyer in buyers:
            buyer_user = User.query.filter_by(id=str(buyer.user_id)).first()
            orders_count = Order.query.filter_by(buyer_id=buyer.id).count()
            
            buyers_data.append({
                "id": str(buyer.id),
                "user_id": str(buyer.user_id),
                "name": buyer_user.full_name if buyer_user else "Unknown",
                "email": buyer_user.email if buyer_user else None,
                "location": buyer_user.location if buyer_user else None,
                "status": "active" if buyer_user.is_active else "suspended",
                "is_active": buyer_user.is_active,
                "totalOrders": orders_count,
                "joinDate": buyer.created_at.isoformat() if buyer.created_at else None
            })
        
        return jsonify(buyers_data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/farmers/<farmer_id>/verify", methods=["POST"])
@jwt_required()
def verify_farmer(farmer_id):
    """Verify a farmer"""
    admin = admin_required()
    if not admin:
        return jsonify({"error": "Admin access required"}), 403
    
    try:
        farmer = Farmer.query.get(uuid.UUID(farmer_id))
        if not farmer:
            return jsonify({"error": "Farmer not found"}), 404
        
        farmer.is_verified = True
        db.session.commit()
        
        return jsonify({"message": "Farmer verified successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/users/<user_id>/suspend", methods=["POST"])
@jwt_required()
def suspend_user(user_id):
    """Suspend a user"""
    admin = admin_required()
    if not admin:
        return jsonify({"error": "Admin access required"}), 403
    
    try:
        user = User.query.filter_by(id=str(user_id)).first()
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        user.is_active = False
        db.session.commit()
        
        return jsonify({"message": "User suspended successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/users/<user_id>/activate", methods=["POST"])
@jwt_required()
def activate_user(user_id):
    """Activate a user"""
    admin = admin_required()
    if not admin:
        return jsonify({"error": "Admin access required"}), 403
    
    try:
        user = User.query.filter_by(id=str(user_id)).first()
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        user.is_active = True
        db.session.commit()
        
        return jsonify({"message": "User activated successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/users/<user_id>/toggle-status", methods=["PUT"])
@jwt_required()
def toggle_user_status(user_id):
    """Activate/suspend user"""
    admin = admin_required()
    if not admin:
        return jsonify({"error": "Admin access required"}), 403
    
    user = User.query.filter_by(id=str(user_id)).first()
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    user.is_active = not user.is_active
    db.session.commit()
    
    return jsonify({
        "message": f"User {'activated' if user.is_active else 'suspended'}",
        "is_active": user.is_active
    }), 200


@admin_bp.route("/livestock", methods=["GET"])
@jwt_required()
def get_all_livestock():
    """Get all livestock for moderation"""
    user = admin_required()
    if not user:
        return jsonify({"error": "Admin access required"}), 403
    
    animals = Animal.query.order_by(Animal.created_at.desc()).all()
    return jsonify({"animals": [a.to_dict() for a in animals]}), 200


@admin_bp.route("/disputes", methods=["GET"])
@jwt_required()
def get_disputes():
    """Get all disputes"""
    user = admin_required()
    if not user:
        return jsonify({"error": "Admin access required"}), 403
    
    try:
        disputes = Dispute.query.order_by(Dispute.created_at.desc()).all()
        return jsonify({"disputes": [d.to_dict() for d in disputes]}), 200
    except Exception as e:
        # If disputes table doesn't exist, return empty list
        return jsonify({"disputes": [], "message": "Disputes feature not yet configured"}), 200


@admin_bp.route("/disputes/<dispute_id>/resolve", methods=["PUT"])
@jwt_required()
def resolve_dispute(dispute_id):
    """Resolve dispute"""
    admin = admin_required()
    if not admin:
        return jsonify({"error": "Admin access required"}), 403
    
    dispute = Dispute.query.get(uuid.UUID(dispute_id))
    if not dispute:
        return jsonify({"error": "Dispute not found"}), 404
    
    data = request.get_json()
    dispute.status = "resolved"
    dispute.admin_decision = data.get("decision")
    dispute.admin_notes = data.get("notes")
    
    db.session.commit()
    return jsonify({"message": "Dispute resolved"}), 200
