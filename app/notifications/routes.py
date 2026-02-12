from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, Notification, User, Order, Farmer, Buyer
from app.models import create_notification

notifications_bp = Blueprint('notifications', __name__)


@notifications_bp.route('/', methods=['GET'])
@jwt_required()
def get_notifications():
    """Get all notifications for the current user"""
    try:
        user_id = get_jwt_identity()
        
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        unread_only = request.args.get('unread_only', False, type=bool)
        
        # Build query
        query = Notification.query.filter_by(user_id=user_id)
        
        if unread_only:
            query = query.filter_by(is_read=False)
        
        # Get notifications with pagination
        pagination = query.order_by(Notification.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        return jsonify({
            'notifications': [n.to_dict() for n in pagination.items],
            'total': pagination.total,
            'page': pagination.page,
            'per_page': pagination.per_page,
            'has_next': pagination.has_next,
            'unread_count': Notification.query.filter_by(user_id=user_id, is_read=False).count()
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@notifications_bp.route('/unread-count', methods=['GET'])
@jwt_required()
def get_unread_count():
    """Get the count of unread notifications"""
    try:
        user_id = get_jwt_identity()
        count = Notification.query.filter_by(user_id=user_id, is_read=False).count()
        return jsonify({'unread_count': count}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@notifications_bp.route('/<int:notification_id>/read', methods=['PUT'])
@jwt_required()
def mark_notification_read(notification_id):
    """Mark a single notification as read"""
    try:
        user_id = get_jwt_identity()
        notification = Notification.query.filter_by(
            id=notification_id, 
            user_id=user_id
        ).first()
        
        if not notification:
            return jsonify({'error': 'Notification not found'}), 404
        
        notification.is_read = True
        notification.read_at = db.func.now()
        db.session.commit()
        
        return jsonify({'message': 'Notification marked as read', 'notification': notification.to_dict()}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@notifications_bp.route('/read-all', methods=['PUT'])
@jwt_required()
def mark_all_read():
    """Mark all notifications as read for the current user"""
    try:
        user_id = get_jwt_identity()
        Notification.query.filter_by(user_id=user_id, is_read=False).update({
            'is_read': True,
            'read_at': db.func.now()
        })
        db.session.commit()
        
        return jsonify({'message': 'All notifications marked as read'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@notifications_bp.route('/<int:notification_id>', methods=['DELETE'])
@jwt_required()
def delete_notification(notification_id):
    """Delete a notification"""
    try:
        user_id = get_jwt_identity()
        notification = Notification.query.filter_by(
            id=notification_id, 
            user_id=user_id
        ).first()
        
        if not notification:
            return jsonify({'error': 'Notification not found'}), 404
        
        db.session.delete(notification)
        db.session.commit()
        
        return jsonify({'message': 'Notification deleted'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Helper function to create notifications from other routes
def notify_new_order(order_id, buyer_id, farmer_id, total_amount):
    """Create notifications for new order - to farmer"""
    try:
        # Get farmer's user_id
        farmer = Farmer.query.get(farmer_id)
        if not farmer:
            return
        
        # Notify farmer
        create_notification(
            user_id=farmer.user_id,
            type='new_order',
            title='New Order Received!',
            message=f'You received a new order worth KES {float(total_amount):,.0f}',
            related_id=order_id,
            related_type='order'
        )
        
        # Notify buyer
        buyer = Buyer.query.get(buyer_id)
        if buyer:
            create_notification(
                user_id=buyer.user_id,
                type='order_placed',
                title='Order Placed Successfully',
                message=f'Your order has been placed successfully. Total: KES {float(total_amount):,.0f}',
                related_id=order_id,
                related_type='order'
            )
    except Exception as e:
        print(f"Error creating order notifications: {e}")


def notify_new_negotiation(session_id, buyer_id, farmer_id, animal_name):
    """Create notifications for new negotiation"""
    try:
        # Notify farmer
        farmer = Farmer.query.get(farmer_id)
        if farmer:
            create_notification(
                user_id=farmer.user_id,
                type='new_negotiation',
                title='New Negotiation Request',
                message=f'A buyer wants to negotiate for {animal_name}',
                related_id=session_id,
                related_type='negotiation'
            )
    except Exception as e:
        print(f"Error creating negotiation notifications: {e}")


def notify_negotiation_update(session_id, buyer_id, farmer_id, status, message):
    """Create notifications for negotiation status updates"""
    try:
        # Notify farmer if buyer updated
        if buyer_id:
            buyer = Buyer.query.get(buyer_id)
            if buyer:
                create_notification(
                    user_id=buyer.user_id,
                    type='negotiation_update',
                    title='Negotiation Update',
                    message=message,
                    related_id=session_id,
                    related_type='negotiation'
                )
        
        # Notify buyer if farmer updated
        if farmer_id:
            farmer = Farmer.query.get(farmer_id)
            if farmer:
                create_notification(
                    user_id=farmer.user_id,
                    type='negotiation_update',
                    title='Negotiation Update',
                    message=message,
                    related_id=session_id,
                    related_type='negotiation'
                )
    except Exception as e:
        print(f"Error creating negotiation update notifications: {e}")


def notify_new_dispute(dispute_id, filer_id, target_id, reason):
    """Create notifications for new dispute"""
    try:
        # Notify the target (farmer or buyer)
        if target_id:
            create_notification(
                user_id=target_id,
                type='new_dispute',
                title='New Dispute Filed',
                message=f'A new dispute has been filed: {reason}',
                related_id=dispute_id,
                related_type='dispute'
            )
        
        # Confirm to filer
        create_notification(
            user_id=filer_id,
            type='dispute_filed',
            title='Dispute Filed Successfully',
            message=f'Your dispute has been submitted. Ticket ID: {dispute_id}',
            related_id=dispute_id,
            related_type='dispute'
        )
    except Exception as e:
        print(f"Error creating dispute notifications: {e}")


def notify_order_status_update(order_id, user_id, status, message):
    """Create notifications for order status updates"""
    try:
        create_notification(
            user_id=user_id,
            type='order_update',
            title=f'Order Status: {status.title()}',
            message=message,
            related_id=order_id,
            related_type='order'
        )
    except Exception as e:
        print(f"Error creating order update notifications: {e}")
