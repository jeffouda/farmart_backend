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
    Safaricom calls this when the user enters their PIN.
    Updates order status, creates escrow, and marks animals as sold.
    """
    payload = request.get_json()
    current_app.logger.info(f"M-Pesa Callback Received: {payload}")

    data = payload.get('Body', {}).get('stkCallback', {})
    checkout_id = data.get('CheckoutRequestID')
    result_code = data.get('ResultCode')
    
    # 1. Find the order by CheckoutRequestID
    order = Order.query.filter_by(checkout_id=checkout_id).first()
    
    if not order:
        current_app.logger.error(f"Order not found for CheckoutRequestID: {checkout_id}")
        return jsonify({"ResultCode": 1, "ResultDesc": "Order not found"}), 200

    if result_code == 0:
        # 2. Extract Receipt Metadata
        items_meta = data.get('CallbackMetadata', {}).get('Item', [])
        receipt = next((i.get('Value') for i in items_meta if i.get('Name') == 'MpesaReceiptNumber'), None)
        
        # 3. Fetch Farmer Details for EscrowRecord
        farmer = Farmer.query.get(order.farmer_id)
        seller_phone = getattr(farmer, 'phone', None) or "N/A"
        
        # 4. Update Order Status
        order.status = "paid"
        order.payment_status = "held"
        order.mpesa_receipt = receipt
        
        # 5. MARK ANIMALS AS SOLD (Inventory Management)
        # This ensures the animals are removed from the marketplace
        if order.items:
            for item in order.items:
                animal_id = item.get('animal_id')
                if animal_id:
                    animal = Animal.query.get(animal_id)
                    if animal:
                        animal.status = "sold"
                        animal.is_available = False # Use whichever field controls marketplace visibility
                        current_app.logger.info(f"Animal {animal_id} marked as sold.")

        # 6. Create/Update Escrow Record
        try:
            escrow = EscrowRecord.query.filter_by(order_id=order.id).first()
            if not escrow:
                escrow = EscrowRecord(
                    order_id=order.id,
                    amount=order.total_amount,
                    status="held",
                    mpesa_receipt=receipt,
                    seller_phone=seller_phone
                )
                db.session.add(escrow)
            else:
                escrow.status = "held"
                escrow.mpesa_receipt = receipt
                escrow.seller_phone = seller_phone

            db.session.commit()
            current_app.logger.info(f"Payment Success & Inventory Updated: Order {order.id}")
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Database Error during callback: {str(e)}")
            return jsonify({"ResultCode": 1, "ResultDesc": "Internal Database Error"}), 200
    else:
        # Payment failed (user cancelled, timeout, etc.)
        order.status = "failed"
        db.session.commit()
        current_app.logger.warning(f"Payment failed for Order {order.id} with code {result_code}")

    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200
        

    
@payment_bp.route('/callback/timeout', methods=['POST'])
def mpesa_timeout_callback():
    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200