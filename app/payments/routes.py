from flask import request, jsonify, current_app
from app.models import db, Order, EscrowRecord, Farmer
from app.services.mpesa_service import MpesaService
from . import payment_bp

@payment_bp.route('/stk-push/<uuid:order_id>', methods=['POST'])
def trigger_payment(order_id):
    """Starts the Lipa na M-Pesa STK Push process."""
    order = Order.query.get_or_404(order_id)
    phone = request.json.get('phone_number') # Expected format: 2547xxxxxxxx
    
    response = MpesaService.stk_push(phone, order.total_amount, order.id)
    
    if response.get('ResponseCode') == '0':
        order.checkout_id = response.get('CheckoutRequestID')
        db.session.commit()
        return jsonify({
            "message": "STK Push initiated", 
            "checkout_id": order.checkout_id
        }), 200
    
    return jsonify({"error": "Failed to initiate payment", "details": response}), 400


@payment_bp.route('/callback/stk', methods=['POST'])
def mpesa_stk_callback():
    """Webhook: Safaricom hits this after user enters PIN."""
    data = request.json.get('Body', {}).get('stkCallback', {})
    checkout_id = data.get('CheckoutRequestID')
    result_code = data.get('ResultCode')
    
    order = Order.query.filter_by(checkout_id=checkout_id).first()
    if not order:
        return jsonify({"message": "Order not found"}), 404

    if result_code == 0:
        # 1. Update Order Status
        order.payment_status = "paid"
        order.status = "held"
        
        # 2. Extract M-Pesa Receipt Number from Metadata
        items = data.get('CallbackMetadata', {}).get('Item', [])
        receipt_number = next((i.get('Value') for i in items if i.get('Name') == 'MpesaReceiptNumber'), None)
        
        # 3. Create Escrow Record
        farmer = Farmer.query.get(order.farmer_id)
        escrow = EscrowRecord(
            order_id=order.id,
            amount=order.total_amount,
            seller_phone=farmer.phone_number,
            status="held",
            mpesa_receipt=receipt_number
        )
        db.session.add(escrow)
        current_app.logger.info(f"Payment successful for Order {order.id}. Receipt: {receipt_number}")
    else:
        # User cancelled or insufficient funds
        order.payment_status = "failed"
        current_app.logger.warning(f"Payment failed for Order {order.id}. Code: {result_code}")

    db.session.commit()
    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200


@payment_bp.route('/release-escrow/<uuid:order_id>', methods=['POST'])
def release_funds(order_id):
    """Triggered when Buyer confirms receipt of livestock."""
    order = Order.query.get_or_404(order_id)
    escrow = EscrowRecord.query.filter_by(order_id=order_id, status="held").first()

    if not escrow:
        return jsonify({"error": "No held funds found for this order"}), 404

    # Trigger B2C payout to Farmer
    response = MpesaService.initiate_b2c(escrow.seller_phone, escrow.amount, order.id)
    
    if response.get('ResponseCode') == '0':
        escrow.b2c_conversation_id = response.get('ConversationID')
        escrow.status = "releasing"
        order.status = "completed"
        db.session.commit()
        return jsonify({"message": "Payout to farmer initiated"}), 200

    return jsonify({"error": "Payout failed to initiate", "details": response}), 400