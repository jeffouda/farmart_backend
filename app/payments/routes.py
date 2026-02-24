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

    # If farmer_id not provided, extract from first animal
    if not farmer_id and items:
        first_item = items[0] if isinstance(items, list) else {}
        animal_id = first_item.get('animal_id')
        print(f"🔍 STK DEBUG: first_item={first_item}, animal_id={animal_id}")
        if animal_id:
            # Use filter_by instead of query.get for UUID
            animal = Animal.query.filter_by(id=str(animal_id)).first()
            print(f"🔍 STK DEBUG: animal found={animal is not None}")
            if animal:
                farmer_id = str(animal.farmer_id)
                print(f"🔍 STK DEBUG: farmer_id={farmer_id}")

    if not all([phone, amount, items]):
        return jsonify({"error": "Missing required payment fields"}), 400

    if not farmer_id:
        return jsonify({"error": "Could not determine farmer_id for this order"}), 400

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
    # Check if an order has been created with this checkout ID
    order = Order.query.filter_by(checkout_id=checkout_id).first()
    if order:
        return jsonify({
            "status": "paid",
            "order_id": order.id,
            "payment_status": "paid"
        }), 200
    
    # Check if the pending record marked it as failed
    pending = PendingCheckout.query.filter_by(checkout_id=checkout_id).first()
    if pending and pending.status == "failed":
        return jsonify({"status": "failed"}), 200
        
    return jsonify({"status": "pending"}), 200


@payment_bp.route('/confirm-receipt/<order_id>', methods=['POST'])
@jwt_required()
def confirm_and_release(order_id):
    """
    Triggers the Escrow release (B2C Payout to Farmer).
    Captures ConversationID to track the asynchronous response from Safaricom.
    """
    order = Order.query.get_or_404(order_id)
    
    # Ensure funds are currently held and not already being processed
    escrow = EscrowRecord.query.filter_by(order_id=order_id, status="held").first()

    if not escrow:
        return jsonify({"error": "No funds in escrow or already released/processing"}), 404

    # Execute M-Pesa B2C Payout
    response = MpesaService.initiate_b2c(escrow.seller_phone, escrow.amount, str(order.id))
    
    if response.get('ResponseCode') == '0':
        # IMPORTANT: Capture ConversationID so the callback can find this record
        escrow.b2c_conversation_id = response.get('ConversationID')
        escrow.status = "releasing" # Interim status while waiting for callback
        db.session.commit()
        
        current_app.logger.info(f"B2C Payout Initiated for Order {order_id}. CID: {escrow.b2c_conversation_id}")
        return jsonify({"message": "Payout initiated. Waiting for Safaricom confirmation."}), 200

    current_app.logger.error(f"B2C Payout Initiation Failed: {response}")
    return jsonify({"error": "Payout initiation failed", "details": response}), 400


# ==========================================
# 2. SAFARICOM CALLBACKS
# ==========================================

@payment_bp.route('/callback/stk', methods=['POST'])
def mpesa_stk_callback():
    """
    Webhook from Safaricom. Creates order ONLY on successful payment.
    Updates existing order if found, otherwise creates new one.
    """
    try:
        payload = request.get_json()
        data = payload.get('Body', {}).get('stkCallback', {})
        checkout_id = data.get('CheckoutRequestID')
        result_code = data.get('ResultCode')
        
        current_app.logger.info(f"STK CALLBACK DEBUG - CheckoutID: {checkout_id}, ResultCode: {result_code}")
        
        # 1. Check if there's an existing order with this checkout_id (from orders/routes.py)
        existing_order = Order.query.filter_by(checkout_id=checkout_id).first()
        current_app.logger.info(f"STK CALLBACK DEBUG - Found order by checkout_id: {existing_order is not None}")
        
        if existing_order:
            # Update existing order from orders/routes.py flow
            current_app.logger.info(f"STK CALLBACK DEBUG - Order {existing_order.id}: current status={existing_order.status}, payment_status={existing_order.payment_status}")
            
            if result_code == 0:
                # Extract receipt
                items_meta = data.get('CallbackMetadata', {}).get('Item', [])
                receipt = next((item.get('Value') for item in items_meta if item.get('Name') == 'MpesaReceiptNumber'), "N/A")
                
                existing_order.status = "paid"
                existing_order.payment_status = "paid"
                existing_order.checkout_id = checkout_id
                existing_order.mpesa_receipt = receipt
                
                # Mark animals as sold
                for item_data in (existing_order.items or []):
                    animal_id_str = item_data.get('animal_id')
                    try:
                        # Convert string UUID to UUID object for query
                        animal_uuid = uuid.UUID(animal_id_str) if isinstance(animal_id_str, str) else animal_id_str
                        animal = Animal.query.get(animal_uuid)
                        if animal:
                            animal.status = "sold"
                            animal.is_available = False
                    except (ValueError, AttributeError) as e:
                        current_app.logger.error(f"Error updating animal {animal_id_str}: {e}")
                
                # Create escrow record
                farmer = Farmer.query.get(existing_order.farmer_id)
                escrow = EscrowRecord(
                    order_id=existing_order.id,
                    amount=existing_order.total_amount,
                    status="held",
                    mpesa_receipt=receipt,
                    seller_phone=getattr(farmer, 'phone_number', 'N/A') if farmer else 'N/A'
                )
                db.session.add(escrow)
                
                current_app.logger.info(f"✅ Order {existing_order.id} updated to PAID. New status={existing_order.status}, payment_status={existing_order.payment_status}")
            else:
                existing_order.status = "failed"
                existing_order.payment_status = "failed"
                current_app.logger.info(f"❌ Order {existing_order.id} updated to FAILED (ResultCode={result_code})")
            
            db.session.commit()
            return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200
        
        # 2. Check for PendingCheckout (from payments/stk-push flow)
        pending = PendingCheckout.query.filter_by(checkout_id=checkout_id).first()
        
        if not pending:
            current_app.logger.error(f"❌ No Pending record or Order found for checkout_id: {checkout_id}")
            return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200

        # 3. If Payment Failed (ResultCode != 0)
        if result_code != 0:
            pending.status = "failed"
            db.session.commit()
            current_app.logger.warning(f"Payment failed for CheckoutID: {checkout_id}")
            return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200

        # 4. Payment SUCCESS - Extract Metadata
        items_meta = data.get('CallbackMetadata', {}).get('Item', [])
        receipt = next((item.get('Value') for item in items_meta if item.get('Name') == 'MpesaReceiptNumber'), "N/A")
        
        # 5. Create the Actual Order
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
        
        # 6. Mark Animal as Sold
        for item_data in (pending.items or []):
            animal_id_str = item_data.get('animal_id')
            try:
                # Convert string UUID to UUID object for query
                animal_uuid = uuid.UUID(animal_id_str) if isinstance(animal_id_str, str) else animal_id_str
                animal = Animal.query.get(animal_uuid)
                if animal:
                    animal.status = "sold"
                    animal.is_available = False
            except (ValueError, AttributeError) as e:
                current_app.logger.error(f"Error updating animal {animal_id_str}: {e}")

        # 7. Create Escrow Record
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
    """
    Final confirmation of the payout to the farmer.
    """
    payload = request.get_json()
    result = payload.get('Result', {})
    result_code = result.get('ResultCode')
    conversation_id = result.get('ConversationID')

    # Find the escrow record using the ConversationID captured during initiation
    escrow = EscrowRecord.query.filter_by(b2c_conversation_id=conversation_id).first()

    if not escrow:
        current_app.logger.error(f"B2C Callback received for unknown ConversationID: {conversation_id}")
        return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200

    if result_code == 0:
        current_app.logger.info(f"✅ B2C Payout Success for Escrow {escrow.id}")
        escrow.status = "released"
        # Update the associated order status to fully completed
        order = Order.query.get(escrow.order_id)
        if order:
            order.status = "completed"
    else:
        # Catch errors like 2040 (Insufficient funds in your shortcode)
        error_msg = result.get('ResultDesc')
        current_app.logger.error(f"❌ B2C Payout Failed for CID {conversation_id}: {error_msg}")
        escrow.status = "held" # Revert to 'held' so the admin/system can retry
    
    db.session.commit()
    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200