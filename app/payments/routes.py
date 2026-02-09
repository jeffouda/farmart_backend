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


@payment_bp.route('/callback/stk', methods=['POST'])
def mpesa_stk_callback():
    data = request.json.get('Body', {}).get('stkCallback', {})
    checkout_id = data.get('CheckoutRequestID')
    result_code = data.get('ResultCode')
    
    order = Order.query.filter_by(checkout_id=checkout_id).first()
    if not order:
        return jsonify({"message": "Order not found"}), 404

    if result_code == 0:
        order.payment_status = "paid"
        order.status = "held"
        
        farmer = Farmer.query.get(order.farmer_id)
        escrow = EscrowRecord(
            order_id=order.id,
            amount=order.total_amount,
            seller_phone=farmer.phone_number,
            status="held"
        )
        db.session.add(escrow)
    else:
        order.payment_status = "failed"

    db.session.commit()
    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200