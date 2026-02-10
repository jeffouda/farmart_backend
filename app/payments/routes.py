from flask import request, jsonify, current_app
from app.models import db, Order, EscrowRecord, Farmer, Buyer, Animal
from app.services.mpesa_service import MpesaService
import uuid
from . import payment_bp

# ==========================================
# 1. USER ROUTES (Initiation)
# ==========================================

@payment_bp.route('/stk-push', methods=['POST'])
def trigger_payment():
    """
    Starts the payment process. 
    Order details are passed here but NOT saved to the DB yet.
    """
    data = request.get_json()
    phone = data.get('phone_number')
    amount = data.get('total_amount')
    
    # We create a unique reference to track this specific payment attempt
    # We pass the order details in the 'AccountReference' or handle via cache
    temp_ref = f"FAR-{uuid.uuid4().hex[:6].upper()}"
    
    response = MpesaService.stk_push(phone, amount, temp_ref)
    
    if response.get('ResponseCode') == '0':
        # We return the CheckoutRequestID so the frontend can poll for the status
        return jsonify({
            "message": "STK Push initiated", 
            "checkout_id": response.get('CheckoutRequestID'),
            "temp_ref": temp_ref
        }), 200
    
    return jsonify({"error": "Failed to initiate payment", "details": response}), 400


@payment_bp.route('/release-escrow/<uuid:order_id>', methods=['POST'])
def release_funds(order_id):
    """Manual trigger to pay the Farmer via B2C payout after buyer confirms receipt."""
    order = Order.query.get_or_404(order_id)
    escrow = EscrowRecord.query.filter_by(order_id=order_id, status="held").first()

    if not escrow:
        return jsonify({"error": "No held funds found for this order"}), 404

    # Call the service to send money from Business to Farmer
    response = MpesaService.initiate_b2c(escrow.seller_phone, escrow.amount, order.id)
    
    if response.get('ResponseCode') == '0':
        escrow.b2c_conversation_id = response.get('ConversationID')
        escrow.status = "releasing"
        order.status = "completed"
        db.session.commit()
        return jsonify({"message": "Payout to farmer initiated"}), 200

    return jsonify({"error": "Payout failed to initiate", "details": response}), 400


# ==========================================
# 2. SAFARICOM CALLBACKS (The "Creation" Logic)
# ==========================================

@payment_bp.route('/callback/stk', methods=['POST'])
def mpesa_stk_callback():
    """
    Webhook: THIS IS WHERE THE ORDER IS ACTUALLY SAVED.
    Safaricom calls this after the user enters their PIN.
    """
    data = request.json.get('Body', {}).get('stkCallback', {})
    result_code = data.get('ResultCode')
    checkout_id = data.get('CheckoutRequestID')

    # ResultCode 0 means the user successfully entered their PIN
    if result_code == 0:
        # 1. Extract Metadata
        meta_items = data.get('CallbackMetadata', {}).get('Item', [])
        receipt = next((i.get('Value') for i in meta_items if i.get('Name') == 'MpesaReceiptNumber'), None)
        amount = next((i.get('Value') for i in meta_items if i.get('Name') == 'Amount'), 0)
        phone = next((i.get('Value') for i in meta_items if i.get('Name') == 'PhoneNumber'), None)

        # 2. DATA RECONCILIATION 
        # In a production app, you'd fetch the 'items' and 'buyer_id' from a Redis cache 
        # using the checkout_id. For now, we assume your frontend sent specific data 
        # or we reconstruct it.
        
        # Example logic to create the order now that money is confirmed:
        # Note: You'll need to pass buyer/farmer IDs to the STK push or cache them
        try:
            new_order = Order(
                checkout_id=checkout_id,
                mpesa_receipt=receipt,
                total_amount=amount,
                status="paid",  # Set to paid immediately
                payment_status="held", # Escrow state
                payment_method="mpesa"
                # items=... (fetched from cache)
            )
            db.session.add(new_order)
            
            # 3. Create the Escrow Record
            escrow = EscrowRecord(
                order_id=new_order.id,
                amount=amount,
                status="held",
                mpesa_receipt=receipt
            )
            db.session.add(escrow)
            db.session.commit()
            
            current_app.logger.info(f"ORDER CREATED: {new_order.id} for Receipt {receipt}")
        except Exception as e:
            current_app.logger.error(f"Error saving order after payment: {str(e)}")
            db.session.rollback()

    else:
        current_app.logger.warning(f"Payment Failed or Cancelled. Code: {result_code}")

    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200


@payment_bp.route('/callback/b2c', methods=['POST'])
def mpesa_b2c_callback():
    """Webhook: Confirms when the Farmer actually receives the payout."""
    data = request.json.get('Result', {})
    conversation_id = data.get('ConversationID')
    result_code = data.get('ResultCode')
    
    escrow = EscrowRecord.query.filter_by(b2c_conversation_id=conversation_id).first()
    
    if result_code == 0 and escrow:
        escrow.status = "completed"
        db.session.commit()
    
    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200

@payment_bp.route('/callback/timeout', methods=['POST'])
def mpesa_timeout_callback():
    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200