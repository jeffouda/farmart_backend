import requests
import base64
import re
import uuid
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
        
        if phone.startswith('+'):
            phone = phone[1:]
        
        if phone.startswith('0'):
            phone = '254' + phone[1:]
        elif phone.startswith('7') or phone.startswith('1'): # Support 07... and 01...
            phone = '254' + phone
        
        if re.match(r'^254[1-9]\d{8}$', phone):
            return phone
        else:
            current_app.logger.warning(f"Invalid phone format: {phone}")
            return None

    @staticmethod
    def get_access_token():
        """Fetches the OAuth2 token from Safaricom."""
        consumer_key = current_app.config.get('MPESA_CONSUMER_KEY')
        consumer_secret = current_app.config.get('MPESA_CONSUMER_SECRET')
        
        if not consumer_key or not consumer_secret:
            current_app.logger.error("Missing Mpesa Keys in Config")
            return None

        api_url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
        
        try:
            res = requests.get(api_url, auth=HTTPBasicAuth(consumer_key, consumer_secret), timeout=15)
            token_data = res.json()
            if res.status_code == 200:
                return token_data.get('access_token')
            else:
                current_app.logger.error(f"Mpesa Token Error Status {res.status_code}: {token_data}")
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
        
        data_to_encode = str(shortcode) + str(passkey) + timestamp
        online_password = base64.b64encode(data_to_encode.encode()).decode('utf-8')
        return online_password, timestamp

    @classmethod
    def stk_push(cls, phone, amount, order_id):
        """Initiates the STK Push on the buyer's phone."""
        token = cls.get_access_token()
        if not token:
            return {"error": "Failed to generate M-Pesa token. Check credentials."}

        password, timestamp = cls.generate_password()
        
        base_url = current_app.config.get('BASE_URL', '').strip().rstrip('/')
        callback_url = f"{base_url}/api/payments/callback/stk"
        
        formatted_phone = cls.format_phone_number(phone)
        if not formatted_phone:
            return {"error": "Invalid phone number format", "original_phone": phone}
        
        # FIX: Remove hyphens from UUID for AccountReference. Safaricom hates special chars here.
        clean_ref = str(order_id).replace('-', '')[:12].upper()
        
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
            "AccountReference": clean_ref, 
            "TransactionDesc": f"Pay {clean_ref}"
        }
        
        current_app.logger.info(f"🚀 Attempting STK Push for {formatted_phone} - Ref: {clean_ref}")
        
        try:
            res = requests.post(
                "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest",
                json=payload,
                headers=headers,
                timeout=30
            )
            response_data = res.json()
            
            if res.status_code != 200:
                current_app.logger.error(f"❌ Safaricom 400/500 Error: {response_data}")
            else:
                current_app.logger.info(f"✅ M-Pesa STK Success Response: {response_data}")
                
            return response_data
            
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"M-Pesa STK Request Failed: {e}")
            return {"error": str(e)}

    @classmethod
    def initiate_b2c(cls, phone, amount, order_id):
        """Initiates payout from Escrow to Farmer (Seller)."""
        token = cls.get_access_token()
        if not token:
            return {"error": "Failed to generate token"}

        base_url = current_app.config.get('BASE_URL', '').strip().rstrip('/')
        
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
            "Remarks": f"Escrow {str(order_id)[:10]}",
            "QueueTimeOutURL": f"{base_url}/api/payments/callback/timeout",
            "ResultURL": f"{base_url}/api/payments/callback/b2c",
            "Occassion": "FarmartPayout"
        }
        
        try:
            res = requests.post(
                "https://sandbox.safaricom.co.ke/mpesa/b2c/v1/paymentrequest",
                json=payload,
                headers=headers,
                timeout=30
            )
            return res.json()
        except Exception as e:
            return {"error": str(e)}