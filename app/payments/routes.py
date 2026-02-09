from flask import request, jsonify, current_app
from app.models import db, Order, EscrowRecord, Farmer
from app.services.mpesa_service import MpesaService
from . import payment_bp


@payment_bp.route('/stk-push/<uuid:order_id>', methods=['POST'])
def trigger_payment(order_id):
    order = Order.query.get_or_404(order_id)
    phone = request.json.get('phone_number')
    
    response = MpesaService.stk_push(phone, order.total_amount, order.id)
    
    if response.get('ResponseCode') == '0':
        order.checkout_id = response.get('CheckoutRequestID')
        db.session.commit()
        return jsonify({"message": "STK Push initiated", "checkout_id": order.checkout_id}), 200
    
    return jsonify({"error": "Failed to initiate payment"}), 400