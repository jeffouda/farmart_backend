from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db

from app.models import User, Farmer, Animal, Message, Notification
from datetime import datetime
from . import negotiation_bp
import uuid


# Get messages and send messages for a livestock
@negotiation_bp.route("/<string:livestock_id>", methods=["GET", "POST", "OPTIONS"])
@negotiation_bp.route("/<string:livestock_id>/", methods=["GET", "POST", "OPTIONS"])
def livestock_conversation(livestock_id):
    """
    GET: Get all messages for a specific livestock.
    POST: Send a message about a livestock item.
    """
    print(f"🔍 Negotiation route called: {request.method} /negotiation/{livestock_id}")
    
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200
    
    # Get JWT token
    from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
    try:
        verify_jwt_in_request(optional=True)
        user_id_str = get_jwt_identity()
    except Exception as e:
        print(f"❌ JWT Error: {e}")
        user_id_str = None
    
    if not user_id_str:
        return jsonify({"error": "Authentication required"}), 401

    user = User.query.filter_by(id=user_id_str).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Verify livestock exists
    animal = Animal.query.filter_by(id=livestock_id).first()
    if not animal:
        return jsonify({"error": "Livestock not found"}), 404

    if request.method == "GET":
        # Get messages where user is sender or receiver
        messages = (
            Message.query
            .filter(
                Message.livestock_id == livestock_id,
                (
                    (Message.sender_id == user_id_str)
                    | (Message.receiver_id == user_id_str)
                ),
            )
            .order_by(Message.created_at.asc())
            .all()
        )

        # Get farmer info for the livestock
        farmer = Farmer.query.get(animal.farmer_id)
        farmer_name = farmer.user.full_name if farmer and farmer.user else "Unknown Farmer"

        return jsonify({
            "livestock_id": str(livestock_id),
            "livestock": {
                "species": animal.species,
                "breed": animal.breed,
                "image_url": animal.image_url,
                "price": float(animal.price) if animal.price else 0,
            },
            "farmer_name": farmer_name,
            "messages": [msg.to_dict() for msg in messages],
            "count": len(messages),
        }), 200

    elif request.method == "POST":
        print(f"📨 POST request received for livestock {livestock_id}")
        data = request.get_json()
        print(f"📦 Request data: {data}")

        # Validate required fields
        if not data or not data.get("content"):
            print(f"❌ Missing content field")
            return jsonify({"error": "Message content is required"}), 400

        receiver_id = data.get("receiver_id")
        if not receiver_id:
            print(f"❌ Missing receiver_id field")
            return jsonify({"error": "Receiver ID is required"}), 400
        
        print(f"✅ Validated: sender={user_id_str}, receiver={receiver_id}, content={data['content'][:50]}")

        # Verify receiver exists - could be user_id or farmer_id
        receiver = User.query.filter_by(id=receiver_id).first()
        if not receiver:
            # Try as farmer_id
            farmer = Farmer.query.filter_by(id=receiver_id).first()
            if farmer:
                receiver_id = farmer.user_id
                receiver = farmer.user
                print(f"🔄 Converted farmer_id to user_id: {receiver_id}")
            else:
                print(f"❌ Receiver not found: {receiver_id}")
                return jsonify({"error": "Receiver not found"}), 404

        # Create message
        print(f"💾 Creating message in database...")
        message = Message(
            sender_id=user_id_str,
            receiver_id=receiver_id,
            livestock_id=livestock_id,
            content=data["content"],
        )

        db.session.add(message)

        # Create notification for receiver
        notification = Notification(
            user_id=receiver_id,
            type="new_negotiation",
            title="New Message",
            message=f"{user.full_name} sent you a message about {animal.species}",
            related_id=livestock_id,  # Store livestock_id for navigation
            is_read=False
        )
        db.session.add(notification)

        try:
            db.session.commit()
            print(f"✅ Message saved successfully: {message.id}")
            print(f"🔔 Notification created for user: {receiver_id}")
            return jsonify({
                "message": "Message sent successfully",
                "data": message.to_dict(),
            }), 201
        except Exception as e:
            print(f"❌ Database error: {e}")
            db.session.rollback()
            return jsonify({"error": str(e)}), 500


# Get all conversations for current user
@negotiation_bp.route("/conversations", methods=["GET"])
@negotiation_bp.route("/conversations/", methods=["GET"])
@jwt_required()
def get_conversations():
    """
    Get all conversations for the current user.
    Returns unique conversations grouped by livestock.
    """
    user_id_str = get_jwt_identity()

    user = User.query.filter_by(id=user_id_str).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Get unique livestock IDs from messages
    sent_livestock = (
        db.session
        .query(Message.livestock_id)
        .filter(Message.sender_id == user_id_str)
        .distinct()
        .all()
    )
    received_livestock = (
        db.session
        .query(Message.livestock_id)
        .filter(Message.receiver_id == user_id_str)
        .distinct()
        .all()
    )

    livestock_ids = set()
    for row in sent_livestock:
        livestock_ids.add(row[0])
    for row in received_livestock:
        livestock_ids.add(row[0])

    conversations = []
    for livestock_id in livestock_ids:
        # Get the latest message for this livestock
        latest_message = (
            Message.query
            .filter(Message.livestock_id == livestock_id)
            .order_by(Message.created_at.desc())
            .first()
        )

        if latest_message:
            animal = Animal.query.filter_by(id=livestock_id).first()
            farmer = Farmer.query.get(animal.farmer_id) if animal else None

            # Determine the other party
            if latest_message.sender_id == user_id_str:
                other_user = latest_message.receiver
                other_name = other_user.full_name if other_user else "Unknown"
            else:
                other_user = latest_message.sender
                other_name = other_user.full_name if other_user else "Unknown"

            # Count unread messages
            unread_count = Message.query.filter(
                Message.livestock_id == livestock_id,
                Message.receiver_id == user_id_str,
                Message.is_read == False,
            ).count()

            conversations.append({
                "livestock_id": str(livestock_id),
                "livestock": {
                    "species": animal.species if animal else None,
                    "breed": animal.breed if animal else None,
                    "image_url": animal.image_url if animal else None,
                },
                "other_party": other_name,
                "last_message": latest_message.content[:100] + "..."
                if len(latest_message.content) > 100
                else latest_message.content,
                "last_message_at": latest_message.created_at.isoformat()
                if latest_message.created_at
                else None,
                "unread_count": unread_count,
            })

    # Sort by latest message
    conversations.sort(key=lambda x: x.get("last_message_at", ""), reverse=True)

    return jsonify({
        "conversations": conversations,
        "count": len(conversations),
    }), 200


# Mark messages as read
@negotiation_bp.route("/<string:livestock_id>/read", methods=["POST"])
@negotiation_bp.route("/<string:livestock_id>/read/", methods=["POST"])
@jwt_required()
def mark_as_read(livestock_id):
    """
    Mark all messages for a livestock as read.
    """
    user_id_str = get_jwt_identity()

    # Update unread messages
    Message.query.filter(
        Message.livestock_id == livestock_id,
        Message.receiver_id == user_id_str,
        Message.is_read == False,
    ).update({"is_read": True})

    try:
        db.session.commit()
        return jsonify({"message": "Messages marked as read"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# Delete a message
@negotiation_bp.route("/message/<int:message_id>", methods=["DELETE"])
@jwt_required()
def delete_message(message_id):
    """
    Delete a message (only the sender can delete).
    """
    user_id_str = get_jwt_identity()

    message = Message.query.get(message_id)
    if not message:
        return jsonify({"error": "Message not found"}), 404

    # Only sender can delete
    if message.sender_id != user_id_str:
        return jsonify({"error": "You can only delete your own messages"}), 403

    try:
        db.session.delete(message)
        db.session.commit()
        return jsonify({"message": "Message deleted"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
