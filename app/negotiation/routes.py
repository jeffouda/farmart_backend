from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db

from app.models import User, Farmer, Animal, Message
from datetime import datetime
from . import negotiation_bp
import uuid


# Get all messages for a livestock (conversation view)
@negotiation_bp.route("/<string:livestock_id>", methods=["GET"])
@negotiation_bp.route("/<string:livestock_id>/", methods=["GET"])
@jwt_required()
def get_conversation(livestock_id):
    """
    Get all messages for a specific livestock.
    Users can only see messages they sent or received.
    """
    user_id_str = get_jwt_identity()

    user = User.query.filter_by(id=user_id_str).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Verify livestock exists
    animal = Animal.query.filter_by(id=livestock_id).first()
    if not animal:
        return jsonify({"error": "Livestock not found"}), 404

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
        },
        "farmer_name": farmer_name,
        "messages": [msg.to_dict() for msg in messages],
        "count": len(messages),
    }), 200


# Send a message about livestock
@negotiation_bp.route("/<string:livestock_id>", methods=["POST", "OPTIONS"])
@negotiation_bp.route("/<string:livestock_id>/", methods=["POST", "OPTIONS"])
@jwt_required(optional=True)
def send_message(livestock_id):
    """
    Send a message about a livestock item.
    Requires: receiver_id and content in request body.
    """
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200
    
    user_id_str = get_jwt_identity()

    user = User.query.filter_by(id=user_id_str).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json()

    # Validate required fields
    if not data.get("content"):
        return jsonify({"error": "Message content is required"}), 400

    receiver_id = data.get("receiver_id")
    if not receiver_id:
        return jsonify({"error": "Receiver ID is required"}), 400

    # Verify livestock exists
    animal = Animal.query.filter_by(id=livestock_id).first()
    if not animal:
        return jsonify({"error": "Livestock not found"}), 404

    # Verify receiver exists
    receiver = User.query.filter_by(id=receiver_id).first()
    if not receiver:
        return jsonify({"error": "Receiver not found"}), 404

    # Create message
    message = Message(
        sender_id=user_id_str,
        receiver_id=receiver_id,
        livestock_id=livestock_id,
        content=data["content"],
    )

    db.session.add(message)

    try:
        db.session.commit()
        return jsonify({
            "message": "Message sent successfully",
            "data": message.to_dict(),
        }), 201
    except Exception as e:
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
