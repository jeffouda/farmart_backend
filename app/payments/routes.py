from flask import request, jsonify, current_app
from app.models import db, Order, EscrowRecord, Farmer
from app.services.mpesa_service import MpesaService
from . import payment_bp

# ==========================================
# 1. USER ROUTES (Mobile/Web App hits these)
# ==========================================

@payment_bp.route('/stk-push/<uuid:order_id>', methods=['POST'])
def trigger_payment(order_id):
    """Starts the Lipa na M-Pesa STK Push process for the Buyer."""
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


@payment_bp.route('/release-escrow/<uuid:order_id>', methods=['POST'])
def release_funds(order_id):
    """Manual trigger to pay the Farmer via B2C payout."""
    order = Order.query.get_or_404(order_id)
    escrow = EscrowRecord.query.filter_by(order_id=order_id, status="held").first()

    if not escrow:
        return jsonify({"error": "No held funds found for this order"}), 404

    # Call the service to send money from Business to Customer (Farmer)
    response = MpesaService.initiate_b2c(escrow.seller_phone, escrow.amount, order.id)
    
    if response.get('ResponseCode') == '0':
        escrow.b2c_conversation_id = response.get('ConversationID')
        escrow.status = "releasing"
        order.status = "completed"
        db.session.commit()
        return jsonify({"message": "Payout to farmer initiated"}), 200

    return jsonify({"error": "Payout failed to initiate", "details": response}), 400


# ==========================================
# 2. SAFARICOM CALLBACKS (Webhooks)
# ==========================================

@payment_bp.route('/callback/stk', methods=['POST'])
def mpesa_stk_callback():
    """Webhook: Handles the Buyer's payment result and extracts receipt metadata."""
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
        
        # 2. Extract M-Pesa Receipt Number from Metadata items list
        items = data.get('CallbackMetadata', {}).get('Item', [])
        receipt_number = next((i.get('Value') for i in items if i.get('Name') == 'MpesaReceiptNumber'), None)
        
        # 3. Create Escrow Record to hold funds for the Farmer
        farmer = Farmer.query.get(order.farmer_id)
        escrow = EscrowRecord(
            order_id=order.id,
            amount=order.total_amount,
            seller_phone=farmer.phone_number,
            status="held",
            mpesa_receipt=receipt_number
        )
        db.session.add(escrow)
        current_app.logger.info(f"Payment success for Order {order.id}. Receipt: {receipt_number}")
    else:
        order.payment_status = "failed"
        current_app.logger.warning(f"Payment failed for Order {order.id}. Code: {result_code}")

    db.session.commit()
    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200


@payment_bp.route('/callback/b2c', methods=['POST'])
def mpesa_b2c_callback():
    """Webhook: Confirms when the Farmer actually receives the payout."""
    data = request.json.get('Result', {})
    conversation_id = data.get('ConversationID')
    result_code = data.get('ResultCode')
    
    escrow = EscrowRecord.query.filter_by(b2c_conversation_id=conversation_id).first()
    
    if not escrow:
        # We return 200 to Safaricom even if we don't find the record to stop retries
        return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200

    if result_code == 0:
        escrow.status = "completed"
        current_app.logger.info(f"Escrow released successfully for Record {escrow.id}")
    else:
        escrow.status = "failed"
        current_app.logger.error(f"B2C Payout failed for Escrow {escrow.id}. Code: {result_code}")

    db.session.commit()
    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200


@payment_bp.route('/callback/timeout', methods=['POST'])
def mpesa_timeout_callback():
    """Webhook: Handles Safaricom gateway timeouts for B2C requests."""
    current_app.logger.error(f"M-Pesa B2C Timeout: {request.json}")
    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200