from flask import request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, Order, EscrowRecord, Farmer, Animal, PendingCheckout
from app.services.mpesa_service import MpesaService
import uuid
from . import payment_bp
from datetime import datetime, timedelta

# ==========================================
# 1. USER ROUTES (Initiation & Status)
# ==========================================

@payment_bp.route('/stk-push', methods=['POST'])
@jwt_required()
def trigger_payment():
    """
    Initiates STK Push and creates a PendingCheckout record.
    The actual Order is created only when the M-Pesa Callback confirms success.
    """
    data = request.get_json()
    buyer_id = get_jwt_identity()
    
    # Extract details
    phone = data.get('phone_number')
    amount = data.get('total_amount')
    items = data.get('items')
    farmer_id = data.get('farmer_id')

    if not all([phone, amount, items, farmer_id]):
        return jsonify({"error": "Missing required payment fields"}), 400

    try:
        # 1. Initiate STK Push
        temp_ref = f"FAR-{uuid.uuid4().hex[:6].upper()}"
        response = MpesaService.stk_push(phone, amount, temp_ref)
        
        if response.get('ResponseCode') == '0':
            checkout_id = response.get('CheckoutRequestID')
            
            # 2. Create PendingCheckout (The "Waiting Room" for the order)
            pending = PendingCheckout(
                id=str(uuid.uuid4()),
                buyer_id=buyer_id,
                farmer_id=farmer_id,
                total_amount=amount,
                items=items,
                status="pending",
                checkout_id=checkout_id 
            )
            
            db.session.add(pending)
            db.session.commit()
            
            current_app.logger.info(f"STK Push initiated: {checkout_id}. Pending record created.")
            
            return jsonify({
                "message": "STK Push initiated", 
                "checkout_id": checkout_id,
                "pending_id": pending.id
            }), 201
        
        return jsonify({"error": "M-Pesa rejected request", "details": response}), 400

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"STK Push Error: {str(e)}")
        return jsonify({"error": f"Internal Error: {str(e)}"}), 500


@payment_bp.route('/order-status/<checkout_id>', methods=['GET'])
def check_order_status(checkout_id):
    """
    Frontend polls this to see if the callback has created the Order yet.
    """
    order = Order.query.filter_by(checkout_id=checkout_id).first()
    if order:
        return jsonify({
            "status": order.status,
            "order_id": order.id,
            "payment_status": "paid"
        }), 200
    
    return jsonify({"status": "pending"}), 200


@payment_bp.route('/confirm-receipt/<order_id>', methods=['POST'])
@jwt_required()
def confirm_and_release(order_id):
    """
    UPDATED: Matches frontend call /api/payments/confirm-receipt/<id>
    This triggers the Escrow release (B2C Payout to Farmer).
    """
    order = Order.query.get_or_404(order_id)
    
    # Ensure funds are currently held
    escrow = EscrowRecord.query.filter_by(order_id=order_id, status="held").first()

    if not escrow:
        return jsonify({"error": "No funds in escrow or already released"}), 404

    # Execute M-Pesa B2C Payout
    response = MpesaService.initiate_b2c(escrow.seller_phone, escrow.amount, str(order.id))
    
    if response.get('ResponseCode') == '0':
        # Update records
        escrow.status = "completed"
        order.status = "completed"
        db.session.commit()
        return jsonify({"message": "Success! Funds released to farmer."}), 200

    current_app.logger.error(f"B2C Payout Failed: {response}")
    return jsonify({"error": "Payout initiation failed", "details": response}), 400


# ==========================================
# 2. SAFARICOM CALLBACKS
# ==========================================

@payment_bp.route('/callback/stk', methods=['POST'])
def mpesa_stk_callback():
    """
    Webhook from Safaricom. Creates order ONLY on successful payment.
    """
    try:
        payload = request.get_json()
        data = payload.get('Body', {}).get('stkCallback', {})
        checkout_id = data.get('CheckoutRequestID')
        result_code = data.get('ResultCode')
        
        current_app.logger.info(f"STK Callback - CheckoutID: {checkout_id}, ResultCode: {result_code}")
        
        # 1. Find the Pending Record
        pending = PendingCheckout.query.filter_by(checkout_id=checkout_id).first()
        
        if not pending:
            current_app.logger.error(f"No Pending record for {checkout_id}")
            return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200

        # 2. If Payment Failed
        if result_code != 0:
            pending.status = "failed"
            db.session.commit()
            return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200

        # 3. Payment SUCCESS - Extract Metadata
        items_meta = data.get('CallbackMetadata', {}).get('Item', [])
        receipt = next((item.get('Value') for item in items_meta if item.get('Name') == 'MpesaReceiptNumber'), "N/A")
        
        # 4. Create the Actual Order
        new_order = Order(
            id=str(uuid.uuid4()),
            buyer_id=pending.buyer_id,
            farmer_id=pending.farmer_id,
            total_amount=pending.total_amount,
            items=pending.items,
            status="paid",
            checkout_id=checkout_id,
            mpesa_receipt=receipt
        )
        db.session.add(new_order)
        
        # 5. Mark Animal as Sold
        for item_data in (pending.items or []):
            animal = Animal.query.get(item_data.get('animal_id'))
            if animal:
                animal.status = "sold"
                animal.is_available = False

        # 6. Create Escrow Record
        farmer = Farmer.query.get(pending.farmer_id)
        escrow = EscrowRecord(
            order_id=new_order.id,
            amount=pending.total_amount,
            status="held",
            mpesa_receipt=receipt,
            seller_phone=getattr(farmer, 'phone_number', 'N/A')
        )
        db.session.add(escrow)
        
        # Cleanup pending
        pending.status = "completed"
        db.session.commit()
        
        current_app.logger.info(f"✅ Order {new_order.id} verified and Escrowed.")
        return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200
        
    except Exception as e:
        current_app.logger.error(f"Callback Crash: {str(e)}")
        db.session.rollback()
        return jsonify({"ResultCode": 1, "ResultDesc": "Internal error"}), 200

@payment_bp.route('/callback/b2c', methods=['POST'])
def mpesa_b2c_callback():
    payload = request.get_json()
    result = payload.get('Result', {})
    result_code = result.get('ResultCode')
    conversation_id = result.get('ConversationID')

    # Find the record to update its status based on Safaricom's final word
    escrow = EscrowRecord.query.filter_by(b2c_conversation_id=conversation_id).first()

    if result_code == 0:
        current_app.logger.info("✅ B2C Payout Success.")
        if escrow:
            escrow.status = "released"
    else:
        # This is where your 2040 error will be caught
        error_msg = result.get('ResultDesc')
        current_app.logger.error(f"❌ B2C Payout Failed: {error_msg}")
        if escrow:
            escrow.status = "held" # Revert to held so you can try again
            # Optionally revert order status too
    
    db.session.commit()
    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200