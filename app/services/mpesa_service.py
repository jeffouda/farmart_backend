import requests
import base64
import re
from datetime import datetime
from flask import current_app
from requests.auth import HTTPBasicAuth

class MpesaService:
    @staticmethod
    def format_phone_number(phone):
        """
        Format phone number to M-Pesa expected format (254XXXXXXXXX).
        Handles formats: 07XXXXXXXX, +254XXXXXXXXX, 254XXXXXXXXX
        """
        if not phone:
            return None
        
        # Remove any spaces and special characters
        phone = re.sub(r'[\s\-\(\)]', '', str(phone))
        
        # Handle different formats
        if phone.startswith('+'):
            phone = phone[1:]
        
        if phone.startswith('0'):
            # Convert 07XXXXXXXX to 254XXXXXXXXX
            phone = '254' + phone[1:]
        elif phone.startswith('7'):
            # Convert 7XXXXXXXX to 254XXXXXXXXX
            phone = '254' + phone
        
        # Validate the format
        if re.match(r'^254[1-9]\d{8}$', phone):
            return phone
        else:
            current_app.logger.warning(f"Invalid phone format: {phone}")
            return None

    @staticmethod
    def get_access_token():
        """Fetches the OAuth2 token from Safaricom."""
        consumer_key = current_app.config['MPESA_CONSUMER_KEY']
        consumer_secret = current_app.config['MPESA_CONSUMER_SECRET']
        api_url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
        
        try:
            res = requests.get(api_url, auth=HTTPBasicAuth(consumer_key, consumer_secret))
            token_data = res.json()
            if res.status_code == 200:
                return token_data.get('access_token')
            else:
                current_app.logger.error(f"Mpesa Token Error: {token_data}")
                return None
        except Exception as e:
            current_app.logger.error(f"Mpesa Token Exception: {e}")
            return None

    @staticmethod
    def generate_password():
        """Generates the STK Push password."""
        shortcode = current_app.config['MPESA_SHORTCODE']
        passkey = current_app.config['MPESA_PASSKEY']
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        
        data_to_encode = shortcode + passkey + timestamp
        online_password = base64.b64encode(data_to_encode.encode()).decode('utf-8')
        return online_password, timestamp

    @classmethod
    def stk_push(cls, phone, amount, order_id):
        """Initiates the STK Push on the buyer's phone."""
        token = cls.get_access_token()
        password, timestamp = cls.generate_password()
        
        # AUTOMATION FIX: Clean whitespace and trailing slashes from BASE_URL
        base_url = current_app.config['BASE_URL'].strip().rstrip('/')
        callback_url = f"{base_url}/api/payments/callback/stk"
        
        # Format phone number to M-Pesa expected format
        formatted_phone = cls.format_phone_number(phone)
        if not formatted_phone:
            return {"error": "Invalid phone number format", "original_phone": phone}
        
        # Log the full callback URL to verify automation bridge
        current_app.logger.info(f"STK Push Automation: Callback URL set to {callback_url}")
        current_app.logger.info(f"STK Push: Original phone={phone}, Formatted={formatted_phone}, OrderID={order_id}")
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "BusinessShortCode": current_app.config['MPESA_SHORTCODE'],
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(float(amount)), 
            "PartyA": formatted_phone, 
            "PartyB": current_app.config['MPESA_SHORTCODE'],
            "PhoneNumber": formatted_phone,
            "CallBackURL": callback_url,
            "AccountReference": str(order_id)[:12], # M-Pesa often caps this length
            "TransactionDesc": f"Order {order_id}"
        }
        
        try:
            res = requests.post(
                "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest",
                json=payload,
                headers=headers,
                timeout=30
            )
            response_data = res.json()
            current_app.logger.info(f"M-Pesa STK Response: {response_data}")
            return response_data
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"M-Pesa STK Request Failed: {e}")
            return {"error": str(e)}

    @classmethod
    def initiate_b2c(cls, phone, amount, order_id):
        """Initiates payout from Escrow to Farmer (Seller)."""
        token = cls.get_access_token()
        base_url = current_app.config['BASE_URL'].strip().rstrip('/')
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "InitiatorName": current_app.config['MPESA_INITIATOR_NAME'],
            "SecurityCredential": current_app.config['MPESA_SECURITY_CREDENTIAL'],
            "CommandID": "BusinessPayment",
            "Amount": int(float(amount)),
            "PartyA": current_app.config['MPESA_SHORTCODE'],
            "PartyB": cls.format_phone_number(phone),
            "Remarks": f"Escrow Release Order {order_id}",
            "QueueTimeOutURL": f"{base_url}/api/payments/callback/timeout",
            "ResultURL": f"{base_url}/api/payments/callback/b2c",
            "Occassion": "FarmartPayout"
        }
        
        res = requests.post(
            "https://sandbox.safaricom.co.ke/mpesa/b2c/v1/paymentrequest",
            json=payload,
            headers=headers
        )
        return res.json()