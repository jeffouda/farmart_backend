from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from functools import wraps
from app import db
import uuid
from app.models import User, Dispute, Order, Farmer, Buyer, create_notification

disputes_bp = Blueprint("disputes", __name__, url_prefix="/api/disputes")


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
        
        user = User.query.filter_by(id=str(user_uuid)).first()
        
        # Ensure role is compared as lowercase string
        user_role = user.role.value if hasattr(user.role, 'value') else str(user.role)
        user_role = user_role.lower() if user_role else user_role
        
        if not user or user_role != "admin":
            return jsonify({"error": "Admin access required"}), 403
        
        return f(*args, **kwargs)
    return decorated_function


def generate_ticket_id():
    """Generate a unique ticket ID."""
    return f"DSP-{uuid.uuid4().hex[:8].upper()}"


@disputes_bp.route("", methods=["POST"])
@jwt_required()
def create_dispute():
    """Create a new dispute"""
    try:
        current_user_id_str = get_jwt_identity()
        user_uuid = get_uuid(current_user_id_str)
        if not user_uuid:
            return jsonify({"error": "Invalid user ID format"}), 400
        
        # Get user
        user = User.query.filter_by(id=str(user_uuid)).first()
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        # Get user role - ensure it's compared as lowercase string
        user_role = user.role.value if hasattr(user.role, 'value') else str(user.role)
        user_role = user_role.lower() if user_role else user_role
        
        data = request.form.to_dict()
        
        # Generate ticket ID
        ticket_id = generate_ticket_id()
        
        # Get order if provided
        order_id_str = data.get("order_id")
        order_id = get_uuid(order_id_str) if order_id_str else None
        
        # Get target ID (user being reported)
        target_id_str = data.get("target_id")
        target_id = get_uuid(target_id_str) if target_id_str else None
        
        # If order is provided, auto-detect target from order
        if order_id and not target_id:
            order = Order.query.get(order_id)
            if order:
                if user_role == "farmer":
                    # Farmer filing dispute → target is buyer
                    buyer = Buyer.query.get(order.buyer_id)
                    if buyer:
                        target_id = buyer.user_id
                        current_app.logger.info(f"Auto-detected buyer target_id: {target_id} for farmer dispute on order {order_id}")
                elif user_role == "buyer":
                    # Buyer filing dispute → target is farmer
                    farmer = Farmer.query.get(order.farmer_id)
                    if farmer:
                        target_id = farmer.user_id
                        current_app.logger.info(f"Auto-detected farmer target_id: {target_id} for buyer dispute on order {order_id}")
        
        dispute = Dispute(
            ticket_id=ticket_id,
            order_id=order_id,
            filer_id=user_uuid,
            target_id=target_id,
            dispute_type=data.get("dispute_type", "order"),
            reason=data.get("reason"),
            description=data.get("description"),
            resolution=data.get("resolution"),
            status="open",
        )
        
        db.session.add(dispute)
        db.session.commit()
        
        # Create notifications
        try:
            # Notify target of the dispute
            if target_id:
                create_notification(
                    user_id=target_id,
                    type='new_dispute',
                    title='New Dispute Filed',
                    message=f'A new dispute has been filed. Reason: {data.get("reason", "General")}',
                    related_id=str(dispute.id),
                    related_type='dispute'
                )
            # Notify filer (confirmation)
            create_notification(
                user_id=user_uuid,
                type='dispute_filed',
                title='Dispute Filed Successfully',
                message=f'Your dispute has been submitted. Ticket ID: {ticket_id}',
                related_id=str(dispute.id),
                related_type='dispute'
            )
        except Exception as notify_error:
            current_app.logger.error(f"Error creating notification: {notify_error}")
        
        return jsonify({
            "message": "Dispute created successfully",
            "ticket_id": ticket_id,
            "dispute_id": str(dispute.id),
            "target_id": str(target_id) if target_id else None,
        }), 201
        
    except Exception as e:
        current_app.logger.error(f"Error creating dispute: {str(e)}")
        return jsonify({"error": str(e)}), 500


@disputes_bp.route("", methods=["GET"])
@jwt_required()
@admin_required
def get_all_disputes_admin():
    """Get all disputes for admin dashboard"""
    try:
        disputes = Dispute.query.order_by(Dispute.created_at.desc()).all()
        
        disputes_data = []
        for dispute in disputes:
            dispute_dict = dispute.to_dict()
            
            # Get order details if exists
            if dispute.order_id:
                order = Order.query.get(dispute.order_id)
                if order:
                    dispute_dict["order_amount"] = float(order.total_amount)
                    dispute_dict["order_date"] = order.created_at.strftime("%Y-%m-%d") if order.created_at else None
                    # Safely get item name from items array
                    order_items = order.items if order.items else []
                    dispute_dict["item_details"] = order_items[0].get("name", order_items[0].get("species", "Unknown")) if order_items else "Unknown"
                    
                    # Get buyer info
                    if order.buyer_id:
                        buyer = Buyer.query.get(order.buyer_id)
                        if buyer:
                            buyer_user = User.query.filter_by(id=str(buyer.user_id)).first()
                            dispute_dict["buyer"] = {
                                "name": buyer_user.full_name if buyer_user else "Unknown",
                                "id": str(buyer_user.id) if buyer_user else None,
                            }
                    
                    # Get farmer info
                    if order.farmer_id:
                        farmer = Farmer.query.get(order.farmer_id)
                        if farmer:
                            farmer_user = User.query.filter_by(id=str(farmer.user_id)).first()
                            dispute_dict["farmer"] = {
                                "name": farmer_user.full_name if farmer_user else "Unknown",
                                "id": str(farmer_user.id) if farmer_user else None,
                            }
            
            # Get filer info
            if dispute.filer_id:
                filer = User.query.get(dispute.filer_id)
                dispute_dict["filer"] = {
                    "name": filer.full_name if filer else "Unknown",
                    "email": filer.email if filer else None,
                }
            
            disputes_data.append(dispute_dict)
        
        return jsonify(disputes_data), 200
        
    except Exception as e:
        current_app.logger.error(f"Error fetching disputes: {str(e)}")
        return jsonify({"error": str(e)}), 500


@disputes_bp.route("/my", methods=["GET"])
@jwt_required()
def get_my_disputes():
    """Get disputes for the current authenticated user"""
    try:
        current_user_id_str = get_jwt_identity()
        user_uuid = get_uuid(current_user_id_str)
        if not user_uuid:
            return jsonify({"error": "Invalid user ID format"}), 400

        # Get user's farmer/buyer profile
        farmer = Farmer.query.filter_by(user_id=user_uuid).first()
        buyer = Buyer.query.filter_by(user_id=user_uuid).first()
        
        # Get disputes where user is filer or target
        incoming = []
        outgoing = []
        
        # Outgoing: disputes filed by user
        outgoing_disputes = Dispute.query.filter_by(filer_id=user_uuid).all()
        for d in outgoing_disputes:
            dispute_dict = d.to_dict()
            # Get filer info
            filer = User.query.get(d.filer_id)
            dispute_dict["filer_name"] = filer.full_name if filer else "Unknown"
            # Get order details
            if d.order_id:
                order = Order.query.get(d.order_id)
                if order:
                    dispute_dict["order_amount"] = float(order.total_amount)
                    dispute_dict["item_details"] = order.items[0].get("name") if order.items else "Unknown"
            outgoing.append(dispute_dict)
        
        # Incoming: disputes against user's orders
        if farmer:
            farmer_orders = Order.query.filter_by(farmer_id=farmer.id).all()
            order_ids = [o.id for o in farmer_orders]
            incoming_disputes = Dispute.query.filter(Dispute.order_id.in_(order_ids)).all()
            for d in incoming_disputes:
                dispute_dict = d.to_dict()
                filer = User.query.get(d.filer_id)
                dispute_dict["filer_name"] = filer.full_name if filer else "Unknown"
                order = Order.query.get(d.order_id)
                if order:
                    dispute_dict["order_amount"] = float(order.total_amount)
                    dispute_dict["item_details"] = order.items[0].get("name") if order.items else "Unknown"
                incoming.append(dispute_dict)
        
        if buyer:
            buyer_orders = Order.query.filter_by(buyer_id=buyer.id).all()
            order_ids = [o.id for o in buyer_orders]
            for d in Dispute.query.filter(Dispute.order_id.in_(order_ids)).all():
                if d.filer_id != user_uuid:  # Don't duplicate
                    dispute_dict = d.to_dict()
                    filer = User.query.get(d.filer_id)
                    dispute_dict["filer_name"] = filer.full_name if filer else "Unknown"
                    order = Order.query.get(d.order_id)
                    if order:
                        dispute_dict["order_amount"] = float(order.total_amount)
                        dispute_dict["item_details"] = order.items[0].get("name") if order.items else "Unknown"
                    incoming.append(dispute_dict)
        
        return jsonify({"incoming": incoming, "outgoing": outgoing}), 200
        
    except Exception as e:
        current_app.logger.error(f"Error fetching user disputes: {str(e)}")
        return jsonify({"error": str(e)}), 500


@disputes_bp.route("/<string:dispute_id>", methods=["GET"])
@jwt_required()
def get_dispute(dispute_id):
    """Get a specific dispute"""
    dispute_uuid = get_uuid(dispute_id)
    if not dispute_uuid:
        return jsonify({"error": "Invalid dispute ID format"}), 400
    
    dispute = Dispute.query.get(dispute_uuid)
    if not dispute:
        return jsonify({"error": "Dispute not found"}), 404
    
    return jsonify(dispute.to_dict()), 200


@disputes_bp.route("/<string:dispute_id>/resolve", methods=["POST"])
@jwt_required()
@admin_required
def resolve_dispute(dispute_id):
    """Resolve a dispute (admin only)"""
    dispute_uuid = get_uuid(dispute_id)
    if not dispute_uuid:
        return jsonify({"error": "Invalid dispute ID format"}), 400
    
    dispute = Dispute.query.get(dispute_uuid)
    if not dispute:
        return jsonify({"error": "Dispute not found"}), 404
    
    data = request.get_json() or {}
    decision = data.get("decision")  # 'refund_buyer', 'release_farmer', 'dismiss'
    notes = data.get("notes", "")
    
    if decision not in ["refund_buyer", "release_farmer", "dismiss"]:
        return jsonify({"error": "Invalid decision"}), 400
    
    dispute.status = "resolved"
    dispute.admin_decision = decision
    dispute.admin_notes = notes
    
    db.session.commit()
    
    return jsonify({
        "message": "Dispute resolved successfully",
        "dispute": dispute.to_dict(),
    }), 200


@disputes_bp.route("/<string:dispute_id>", methods=["PUT"])
@jwt_required()
@admin_required
def update_dispute(dispute_id):
    """Update dispute status (admin only)"""
    dispute_uuid = get_uuid(dispute_id)
    if not dispute_uuid:
        return jsonify({"error": "Invalid dispute ID format"}), 400
    
    dispute = Dispute.query.get(dispute_uuid)
    if not dispute:
        return jsonify({"error": "Dispute not found"}), 404
    
    data = request.get_json()
    if "status" in data:
        dispute.status = data["status"]
    if "admin_notes" in data:
        dispute.admin_notes = data["admin_notes"]
    
    db.session.commit()
    
    return jsonify({
        "message": "Dispute updated",
        "dispute": dispute.to_dict(),
    }), 200


@disputes_bp.route("/<string:dispute_id>/respond", methods=["POST"])
@jwt_required()
def respond_to_dispute(dispute_id):
    """Respond to a dispute (for both farmers and buyers who are targets)"""
    try:
        current_user_id_str = get_jwt_identity()
        user_uuid = get_uuid(current_user_id_str)
        if not user_uuid:
            return jsonify({"error": "Invalid user ID format"}), 400
        
        dispute_uuid = get_uuid(dispute_id)
        if not dispute_uuid:
            return jsonify({"error": "Invalid dispute ID format"}), 400
        
        dispute = Dispute.query.get(dispute_uuid)
        if not dispute:
            return jsonify({"error": "Dispute not found"}), 404
        
        # Verify the current user is the target of the dispute
        if dispute.target_id != user_uuid:
            return jsonify({"error": "You are not authorized to respond to this dispute"}), 403
        
        # Determine if current user is farmer or buyer
        user = User.query.filter_by(id=str(user_uuid)).first()
        is_farmer = Farmer.query.filter_by(user_id=user_uuid).first() is not None
        is_buyer = Buyer.query.filter_by(user_id=user_uuid).first() is not None
        
        # Get response data
        data = request.form.to_dict()
        response_text = data.get("response", "").strip()
        
        if not response_text:
            return jsonify({"error": "Response is required"}), 400
        
        # Update dispute with response based on user role
        if is_farmer:
            dispute.farmer_response = response_text
            dispute.farmer_response_at = datetime.utcnow()
        elif is_buyer:
            dispute.buyer_response = response_text
            dispute.buyer_response_at = datetime.utcnow()
        
        dispute.status = "pending"  # Mark as pending for admin review
        
        # Handle evidence upload
        if "evidence" in request.files:
            evidence_file = request.files["evidence"]
            if evidence_file and evidence_file.filename:
                # Save evidence file
                import os
                upload_folder = current_app.config.get("UPLOAD_FOLDER", "app/static/uploads")
                os.makedirs(upload_folder, exist_ok=True)
                filename = f"dispute_{dispute.id}_{evidence_file.filename}"
                filepath = os.path.join(upload_folder, filename)
                evidence_file.save(filepath)
                dispute.farmer_evidence = filepath
        
        db.session.commit()
        
        return jsonify({
            "message": "Response submitted successfully",
            "dispute": dispute.to_dict(),
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Error responding to dispute: {str(e)}")
        return jsonify({"error": str(e)}), 500
