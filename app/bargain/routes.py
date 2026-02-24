from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import (
    User,
    Farmer,
    Buyer,
    Animal,
    BargainSession,
    BargainMessage,
    create_notification,
)
from datetime import datetime, timedelta
from . import bargain_bp
import uuid


# Start a new bargain session (Buyer makes initial offer)
@bargain_bp.route("/sessions", methods=["POST", "OPTIONS"])
@jwt_required(optional=True)
def create_session():
    # Handle OPTIONS preflight
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200
    
    data = request.get_json()

    # Get current user from JWT
    user_id_str = get_jwt_identity()
    try:
        user_id_uuid = uuid.UUID(user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    user = User.query.filter_by(id=str(user_id_uuid)).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Validate buyer role - convert enum to proper string
    user_role = user.role.value if hasattr(user.role, 'value') else str(user.role)
    user_role = user_role.lower() if user_role else user_role
    
    if user_role != "buyer":
        return jsonify({"error": "Only buyers can start bargain sessions", "debug_role": user_role}), 403

    # Validate required fields
    required_fields = ["animal_id", "offer_amount", "message"]
    if not all(k in data for k in required_fields):
        return jsonify({"error": "Missing animal_id, offer_amount, or message"}), 400

    animal_id = data["animal_id"]
    offer_amount = data["offer_amount"]
    message = data["message"]

    # Get the animal
    animal = Animal.query.get(animal_id)
    if not animal:
        return jsonify({"error": "Animal not found"}), 404

    # Check if animal is available
    if animal.status != "available":
        return jsonify({"error": "Animal is not available for bargaining"}), 400

    # Get or create buyer profile
    buyer = Buyer.query.filter_by(user_id=user_id_uuid).first()
    if not buyer:
        return jsonify({"error": "Buyer profile not found"}), 404

    # Check for existing pending session
    existing_session = BargainSession.query.filter(
        BargainSession.animal_id == animal_id,
        BargainSession.buyer_id == buyer.id,
        BargainSession.status.in_(["pending", "counter"]),
    ).first()

    if existing_session:
        return jsonify({
            "error": "You already have an active bargain session for this animal",
            "session_id": str(existing_session.id),
        }), 400

    # Create new bargain session
    session = BargainSession(
        animal_id=animal_id,
        buyer_id=buyer.id,
        farmer_id=animal.farmer_id,
        initial_offer=offer_amount,
        status="pending",
        expires_at=datetime.utcnow() + timedelta(days=3),  # 3 day expiry
    )
    db.session.add(session)
    db.session.flush()  # Get session ID

    # Add initial message from buyer
    msg = BargainMessage(
        session_id=session.id,
        sender_id=user_id_uuid,
        sender_role="buyer",
        message=message,
        offered_price=offer_amount,
    )
    db.session.add(msg)

    try:
        db.session.commit()
        
        # Create notifications
        try:
            # Notify farmer of new negotiation
            farmer = Farmer.query.get(animal.farmer_id)
            if farmer:
                create_notification(
                    user_id=farmer.user_id,
                    type='new_negotiation',
                    title='New Negotiation Request',
                    message=f'A buyer wants to negotiate for {animal.species} ({animal.breed or "Unknown breed"})',
                    related_id=str(session.id),
                    related_type='negotiation'
                )
        except Exception as notify_error:
            print(f"Error creating notification: {notify_error}")
        
        return jsonify({
            "message": "Bargain session created successfully",
            "session": session.to_dict(),
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# Get all bargain sessions for current user
@bargain_bp.route("/sessions", methods=["GET", "OPTIONS"])
@jwt_required(optional=True)
def get_sessions():
    # Handle OPTIONS preflight
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200
    
    user_id_str = get_jwt_identity()
    try:
        user_id_uuid = uuid.UUID(user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    user = User.query.filter_by(id=str(user_id_uuid)).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    try:
        # Get sessions based on role - ensure role is compared as lowercase string
        user_role = user.role.value if hasattr(user.role, 'value') else str(user.role)
        user_role = user_role.lower() if user_role else user_role
        
        if user_role == "buyer":
            buyer = Buyer.query.filter_by(user_id=user_id_uuid).first()
            if buyer:
                sessions = (
                    BargainSession.query
                    .filter_by(buyer_id=buyer.id)
                    .order_by(BargainSession.created_at.desc())
                    .all()
                )
            else:
                sessions = []
        elif user_role == "farmer":
            farmer = Farmer.query.filter_by(user_id=user_id_uuid).first()
            if farmer:
                sessions = (
                    BargainSession.query
                    .filter_by(farmer_id=farmer.id)
                    .order_by(BargainSession.created_at.desc())
                    .all()
                )
            else:
                sessions = []
        else:
            return jsonify({"error": "Invalid role"}), 400

        # Serialize sessions safely
        sessions_data = []
        for session in sessions:
            try:
                sessions_data.append(session.to_dict())
            except Exception as e:
                print(f"[ERROR] Failed to serialize session {session.id}: {e}")
                # Return a minimal dict if serialization fails
                sessions_data.append({
                    "id": str(session.id),
                    "animal_id": str(session.animal_id),
                    "status": session.status,
                    "error": "Serialization failed",
                })

        return jsonify({
            "sessions": sessions_data,
            "count": len(sessions_data),
        }), 200

    except Exception as e:
        print(f"[ERROR] get_sessions route failed: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500


# Get specific session details
@bargain_bp.route("/sessions/<int:session_id>", methods=["GET"])
@jwt_required()
def get_session(session_id):
    user_id_str = get_jwt_identity()
    try:
        user_id_uuid = uuid.UUID(user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    session = BargainSession.query.get(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    user = User.query.filter_by(id=str(user_id_uuid)).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Check access rights
    buyer = Buyer.query.filter_by(user_id=user_id_uuid).first()
    farmer = Farmer.query.filter_by(user_id=user_id_uuid).first()

    # Ensure role is compared as lowercase string
    user_role = user.role.value if hasattr(user.role, 'value') else str(user.role)
    user_role = user_role.lower() if user_role else user_role
    
    has_access = (
        (buyer and session.buyer_id == buyer.id)
        or (farmer and session.farmer_id == farmer.id)
        or user_role == "admin"
    )

    if not has_access:
        return jsonify({"error": "Access denied"}), 403

    # Get messages
    messages = (
        BargainMessage.query
        .filter_by(session_id=session_id)
        .order_by(BargainMessage.created_at.asc())
        .all()
    )

    return jsonify({
        "session": session.to_dict(),
        "messages": [m.to_dict() for m in messages],
    }), 200


# Counter offer (Buyer counters farmer's offer)
@bargain_bp.route("/sessions/<int:session_id>/counter", methods=["POST"])
@jwt_required()
def counter_offer(session_id):
    data = request.get_json()

    user_id_str = get_jwt_identity()
    try:
        user_id_uuid = uuid.UUID(user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    user = User.query.filter_by(id=str(user_id_uuid)).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    session = BargainSession.query.get(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    # Check access rights
    buyer = Buyer.query.filter_by(user_id=user_id_uuid).first()
    farmer = Farmer.query.filter_by(user_id=user_id_uuid).first()

    has_access = (buyer and session.buyer_id == buyer.id) or (
        farmer and session.farmer_id == farmer.id
    )

    if not has_access:
        return jsonify({"error": "Access denied"}), 403

    if session.status not in ["pending", "counter"]:
        return jsonify({"error": "Session is not active"}), 400

    # Get the new price from request
    new_price = data.get("new_price")
    if not new_price:
        return jsonify({"error": "new_price is required"}), 400

    # Update session with new price
    session.initial_offer = float(new_price)
    session.status = "counter"

    # Determine sender role
    sender_role = "buyer" if buyer else "farmer"

    # Create system message for counter offer
    system_msg = BargainMessage(
        session_id=session.id,
        sender_id=user_id_uuid,
        sender_role=sender_role,
        message=f"Counter Offer: KSh {float(new_price):,.0f}",
        offered_price=float(new_price),
    )
    db.session.add(system_msg)

    try:
        db.session.commit()
        
        # Create notifications for counter offer
        try:
            animal = Animal.query.get(session.animal_id)
            # Notify the other party
            if buyer:
                # Farmer made counter offer - notify buyer
                farmer = Farmer.query.get(session.farmer_id)
                if farmer:
                    create_notification(
                        user_id=farmer.user_id,
                        type='negotiation_update',
                        title='Negotiation Update',
                        message=f'You sent a counter offer of KES {float(new_price):,.0f} for {animal.species if animal else "livestock"}',
                        related_id=str(session.id),
                        related_type='negotiation'
                    )
                    # Notify buyer
                    create_notification(
                        user_id=buyer.user_id,
                        type='negotiation_update',
                        title='Counter Offer Received',
                        message=f'Farmer sent a counter offer of KES {float(new_price):,.0f} for {animal.species if animal else "livestock"}',
                        related_id=str(session.id),
                        related_type='negotiation'
                    )
            else:
                # Buyer made counter offer - notify farmer
                farmer_user = User.query.filter_by(id=session.farmer_id).first() if session.farmer_id else None
                if farmer_user:
                    create_notification(
                        user_id=farmer_user.id,
                        type='negotiation_update',
                        title='Counter Offer Received',
                        message=f'Buyer sent a counter offer of KES {float(new_price):,.0f}',
                        related_id=str(session.id),
                        related_type='negotiation'
                    )
        except Exception as notify_error:
            print(f"Error creating notification: {notify_error}")
        
        return jsonify({
            "message": "Counter offer submitted successfully",
            "session": session.to_dict(),
            "message_data": system_msg.to_dict(),
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# Accept bargain offer
@bargain_bp.route("/sessions/<int:session_id>/accept", methods=["POST"])
@jwt_required()
def accept_offer(session_id):
    data = request.get_json()

    user_id_str = get_jwt_identity()
    try:
        user_id_uuid = uuid.UUID(user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    user = User.query.filter_by(id=str(user_id_uuid)).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    session = BargainSession.query.get(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    # Check access rights
    buyer = Buyer.query.filter_by(user_id=user_id_uuid).first()
    farmer = Farmer.query.filter_by(user_id=user_id_uuid).first()

    has_access = (buyer and session.buyer_id == buyer.id) or (
        farmer and session.farmer_id == farmer.id
    )

    if not has_access:
        return jsonify({"error": "Access denied"}), 403

    # Get confirmed price from request or use session's current offer
    confirmed_price = data.get("confirmed_price") if data else None
    if not confirmed_price:
        confirmed_price = session.initial_offer

    # Set final price and mark as accepted
    session.final_price = float(confirmed_price)
    session.status = "accepted"

    # Create system message with price confirmation
    system_msg = BargainMessage(
        session_id=session.id,
        sender_id=user_id_uuid,
        sender_role="buyer" if buyer else "farmer",
        message=f"✅ Offer Accepted! The agreed price is KSh {float(confirmed_price):,.0f}. Buyer can now proceed to payment.",
        offered_price=float(confirmed_price),
    )
    db.session.add(system_msg)

    try:
        db.session.commit()
        
        # Create notifications for accepted offer
        try:
            animal = Animal.query.get(session.animal_id)
            # Notify both parties
            if buyer:
                # Notify farmer that buyer accepted
                farmer = Farmer.query.get(session.farmer_id)
                if farmer:
                    create_notification(
                        user_id=farmer.user_id,
                        type='negotiation_update',
                        title='Offer Accepted!',
                        message=f'Buyer accepted the offer of KES {float(confirmed_price):,.0f} for {animal.species if animal else "livestock"}',
                        related_id=str(session.id),
                        related_type='negotiation'
                    )
            else:
                # Notify buyer that farmer accepted
                buyer_profile = Buyer.query.get(session.buyer_id)
                if buyer_profile:
                    create_notification(
                        user_id=buyer_profile.user_id,
                        type='negotiation_update',
                        title='Offer Accepted!',
                        message=f'Farmer accepted your offer of KES {float(confirmed_price):,.0f}. You can now proceed to payment.',
                        related_id=str(session.id),
                        related_type='negotiation'
                    )
        except Exception as notify_error:
            print(f"Error creating notification: {notify_error}")
        
        return jsonify({
            "message": "Offer accepted successfully",
            "status": "accepted",
            "final_price": float(confirmed_price),
            "session": session.to_dict(),
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# Reject bargain offer
@bargain_bp.route("/sessions/<int:session_id>/reject", methods=["POST"])
@jwt_required()
def reject_offer(session_id):
    user_id_str = get_jwt_identity()
    try:
        user_id_uuid = uuid.UUID(user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    user = User.query.filter_by(id=str(user_id_uuid)).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    session = BargainSession.query.get(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    # Check access rights
    buyer = Buyer.query.filter_by(user_id=user_id_uuid).first()
    farmer = Farmer.query.filter_by(user_id=user_id_uuid).first()

    has_access = (buyer and session.buyer_id == buyer.id) or (
        farmer and session.farmer_id == farmer.id
    )

    if not has_access:
        return jsonify({"error": "Access denied"}), 403

    # Mark as rejected
    session.status = "rejected"

    # Create system message
    system_msg = BargainMessage(
        session_id=session.id,
        sender_id=user_id_uuid,
        sender_role="buyer" if buyer else "farmer",
        message="Offer Rejected",
    )
    db.session.add(system_msg)

    try:
        db.session.commit()
        
        # Create notifications for rejected offer
        try:
            animal = Animal.query.get(session.animal_id)
            # Notify both parties
            if buyer:
                # Notify farmer that buyer rejected
                farmer = Farmer.query.get(session.farmer_id)
                if farmer:
                    create_notification(
                        user_id=farmer.user_id,
                        type='negotiation_update',
                        title='Offer Rejected',
                        message=f'Buyer rejected the offer for {animal.species if animal else "livestock"}',
                        related_id=str(session.id),
                        related_type='negotiation'
                    )
            else:
                # Notify buyer that farmer rejected
                buyer_profile = Buyer.query.get(session.buyer_id)
                if buyer_profile:
                    create_notification(
                        user_id=buyer_profile.user_id,
                        type='negotiation_update',
                        title='Offer Rejected',
                        message=f'Farmer rejected your offer for {animal.species if animal else "livestock"}',
                        related_id=str(session.id),
                        related_type='negotiation'
                    )
        except Exception as notify_error:
            print(f"Error creating notification: {notify_error}")
        
        return jsonify({"message": "Offer rejected", "session": session.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# Respond to a bargain (Farmer accepts/rejects/counters) - legacy route
@bargain_bp.route("/sessions/<int:session_id>/respond", methods=["POST"])
@jwt_required()
def respond_session(session_id):
    data = request.get_json()

    user_id_str = get_jwt_identity()
    try:
        user_id_uuid = uuid.UUID(user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    user = User.query.filter_by(id=str(user_id_uuid)).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Only farmers can respond
    user_role = user.role.value if hasattr(user.role, 'value') else str(user.role)
    user_role = user_role.lower() if user_role else user_role
    
    if user_role != "farmer":
        return jsonify({"error": "Only farmers can respond to bargain sessions"}), 403

    session = BargainSession.query.get(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    farmer = Farmer.query.filter_by(user_id=user_id_uuid).first()
    if not farmer or session.farmer_id != farmer.id:
        return jsonify({"error": "Access denied"}), 403

    if session.status not in ["pending", "counter"]:
        return jsonify({"error": "Session is not active"}), 400

    # Validate response
    response = data.get("response")  # accept, reject, counter
    if response not in ["accept", "reject", "counter"]:
        return jsonify({"error": "Invalid response type"}), 400

    counter_price = data.get("counter_price")

    if response == "accept":
        session.final_price = session.initial_offer
        session.status = "accepted"
        # Optionally update animal status
        animal = Animal.query.get(session.animal_id)
        if animal:
            animal.status = "reserved"

    elif response == "reject":
        session.status = "rejected"

    elif response == "counter":
        if not counter_price:
            return jsonify({"error": "Counter offer requires a price"}), 400
        session.initial_offer = counter_price
        session.status = "counter"
        session.expires_at = datetime.utcnow() + timedelta(days=2)

    # Add system message for counter offers
    if response == "counter":
        system_msg = BargainMessage(
            session_id=session.id,
            sender_id=user_id_uuid,
            sender_role="farmer",
            message=f"Counter Offer: KSh {counter_price:,.0f}",
            offered_price=counter_price,
        )
        db.session.add(system_msg)
    elif response == "accept":
        system_msg = BargainMessage(
            session_id=session.id,
            sender_id=user_id_uuid,
            sender_role="farmer",
            message="Offer Accepted!",
            offered_price=session.final_price,
        )
        db.session.add(system_msg)
    elif response == "reject":
        system_msg = BargainMessage(
            session_id=session.id,
            sender_id=user_id_uuid,
            sender_role="farmer",
            message="Offer Rejected",
        )
        db.session.add(system_msg)

    try:
        db.session.commit()
        return jsonify({
            "message": f"Offer {response}ed successfully",
            "session": session.to_dict(),
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# Add a message to a session (continuing negotiation)
@bargain_bp.route("/sessions/<int:session_id>/messages", methods=["POST"])
@jwt_required()
def add_message(session_id):
    data = request.get_json()

    user_id_str = get_jwt_identity()
    try:
        user_id_uuid = uuid.UUID(user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    user = User.query.filter_by(id=str(user_id_uuid)).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    session = BargainSession.query.get(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    # Check access rights
    buyer = Buyer.query.filter_by(user_id=user_id_uuid).first()
    farmer = Farmer.query.filter_by(user_id=user_id_uuid).first()

    has_access = (buyer and session.buyer_id == buyer.id) or (
        farmer and session.farmer_id == farmer.id
    )

    if not has_access:
        return jsonify({"error": "Access denied"}), 403

    if session.status not in ["pending", "counter"]:
        return jsonify({"error": "Session is not active"}), 400

    message_text = data.get("message", "")
    new_offer = data.get("offer_amount")

    sender_role = "buyer" if buyer else "farmer"

    msg = BargainMessage(
        session_id=session.id,
        sender_id=user_id_uuid,
        sender_role=sender_role,
        message=message_text,
        offered_price=new_offer,
    )

    # Update session offer if buyer makes new offer
    if new_offer and sender_role == "buyer":
        session.initial_offer = new_offer
        session.status = "counter"  # Reopen negotiation

    db.session.add(msg)

    try:
        db.session.commit()
        # Return the message object directly
        return jsonify(msg.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# Complete a bargain (proceed to checkout)
@bargain_bp.route("/sessions/<int:session_id>/complete", methods=["POST"])
@jwt_required()
def complete_session(session_id):
    user_id_str = get_jwt_identity()
    try:
        user_id_uuid = uuid.UUID(user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    user = User.query.filter_by(id=str(user_id_uuid)).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    session = BargainSession.query.get(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    # Only the buyer can complete the session
    buyer = Buyer.query.filter_by(user_id=user_id_uuid).first()
    if not buyer or session.buyer_id != buyer.id:
        return jsonify({"error": "Access denied"}), 403

    if session.status != "accepted":
        return jsonify({"error": "Bargain must be accepted before completing"}), 400

    session.status = "completed"
    session.completed_at = datetime.utcnow()

    # Mark animal as sold
    animal = Animal.query.get(session.animal_id)
    if animal:
        animal.status = "sold"

    try:
        db.session.commit()
        return jsonify({
            "message": "Bargain completed successfully",
            "session": session.to_dict(),
            "next_step": "Proceed to checkout with finalized price",
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# Delete a message
@bargain_bp.route("/messages/<int:message_id>", methods=["DELETE"])
@jwt_required()
def delete_message(message_id):
    user_id_str = get_jwt_identity()
    try:
        user_id_uuid = uuid.UUID(user_id_str)
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400

    user = User.query.filter_by(id=str(user_id_uuid)).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Find the message
    msg = BargainMessage.query.get(message_id)
    if not msg:
        return jsonify({"error": "Message not found"}), 404

    # Check if user is the sender
    if msg.sender_id != user_id_uuid:
        return jsonify({"error": "You can only delete your own messages"}), 403

    try:
        db.session.delete(msg)
        db.session.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
