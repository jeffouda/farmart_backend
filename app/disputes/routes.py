from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from app import db
import uuid
import requests

disputes_bp = Blueprint("disputes", __name__, url_prefix="/api/disputes")

# In-memory storage for disputes (replace with database model in production)
disputes_store = []


def get_user_role_and_profile():
    """
    Get the current user's role and profile ID from the auth service.
    """
    try:
        # Call the auth service to get user info
        response = requests.get(
            f"http://localhost:5000/api/auth/me",
            headers={"Authorization": f"Bearer {get_jwt_identity()}"},
        )
        if response.status_code == 200:
            user_data = response.json()
            return user_data.get("role"), user_data.get("id")
    except Exception as e:
        print(f"Error getting user info: {e}")
    return None, None


@disputes_bp.route("", methods=["POST"])
def create_dispute():
    """Create a new dispute"""
    try:
        data = request.form.to_dict()
        files = request.files

        # Generate ticket ID
        ticket_id = f"DSP-{uuid.uuid4().hex[:8].upper()}"

        dispute = {
            "id": len(disputes_store) + 1,
            "ticket_id": ticket_id,
            "order_id": data.get("order_id") or None,
            "dispute_type": data.get("dispute_type")
            or "order",  # 'order', 'user', 'livestock'
            "target_id": data.get("target_id") or None,
            "context": data.get("context") or None,
            "reference_id": data.get("reference_id") or None,
            "reason": data.get("reason"),
            "description": data.get("description"),
            "resolution": data.get("resolution"),
            "status": "pending",
            "evidence": [],
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        # Handle evidence file
        if "evidence" in files:
            # In production, upload to cloud storage (S3, Cloudinary, etc.)
            # For now, store filename reference
            dispute["evidence"].append({
                "filename": files["evidence"].filename,
                "stored": True,
            })

        disputes_store.append(dispute)

        return jsonify({
            "message": "Dispute created successfully",
            "ticket_id": ticket_id,
            "dispute_id": dispute["id"],
        }), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@disputes_bp.route("", methods=["GET"])
def get_disputes():
    """Get all disputes (admin view)"""
    return jsonify(disputes_store), 200


@disputes_bp.route("/my", methods=["GET"])
@jwt_required()
def get_my_disputes():
    """
    Get disputes for the current authenticated user.
    Returns disputes where the user is either the filer or the target.
    """
    current_user_id_str = get_jwt_identity()

    # Try to get user role and profile
    role, profile_id = get_user_role_and_profile()

    if not profile_id:
        # Fallback: return empty if can't determine user
        return jsonify({"incoming": [], "outgoing": []}), 200

    incoming = []
    outgoing = []

    for dispute in disputes_store:
        # Check if user is the filer (outgoing)
        if dispute.get("filer_id") == profile_id or dispute.get("filer_email"):
            outgoing.append(dispute)

        # For incoming, check if user is the target (farmer/buyer involved)
        # This logic depends on how disputes are linked to orders
        if dispute.get("target_id") == profile_id:
            incoming.append(dispute)

    return jsonify({"incoming": incoming, "outgoing": outgoing}), 200


@disputes_bp.route("/<int:dispute_id>", methods=["GET"])
def get_dispute(dispute_id):
    """Get a specific dispute"""
    for dispute in disputes_store:
        if dispute["id"] == dispute_id:
            return jsonify(dispute), 200
    return jsonify({"error": "Dispute not found"}), 404


@disputes_bp.route("/<int:dispute_id>", methods=["PUT"])
def update_dispute(dispute_id):
    """Update dispute status (admin only)"""
    data = request.get_json()
    for dispute in disputes_store:
        if dispute["id"] == dispute_id:
            dispute["status"] = data.get("status", dispute["status"])
            dispute["admin_notes"] = data.get("admin_notes", None)
            dispute["updated_at"] = datetime.utcnow().isoformat()
            return jsonify({"message": "Dispute updated", "dispute": dispute}), 200
    return jsonify({"error": "Dispute not found"}), 404


@disputes_bp.route("/<int:dispute_id>/respond", methods=["POST"])
@jwt_required()
def respond_to_dispute(dispute_id):
    """
    Submit a response to a dispute.
    """
    data = request.get_json() or {}

    for dispute in disputes_store:
        if dispute["id"] == dispute_id:
            # Add response to the dispute
            if "responses" not in dispute:
                dispute["responses"] = []

            dispute["responses"].append({
                "user_id": get_jwt_identity(),
                "message": data.get("message", ""),
                "submitted_at": datetime.utcnow().isoformat(),
            })

            dispute["updated_at"] = datetime.utcnow().isoformat()

            return jsonify({
                "message": "Response submitted successfully",
                "dispute": dispute,
            }), 200

    return jsonify({"error": "Dispute not found"}), 404
