import requests
import base64
from datetime import datetime
from flask import current_app
from requests.auth import HTTPBasicAuth

class MpesaService:
    @staticmethod
    def get_access_token():
        """Fetches the OAuth2 token from Safaricom."""
        consumer_key = current_app.config['MPESA_CONSUMER_KEY']
        consumer_secret = current_app.config['MPESA_CONSUMER_SECRET']
        api_url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
        
        try:
            res = requests.get(api_url, auth=HTTPBasicAuth(consumer_key, consumer_secret))
            return res.json().get('access_token')
        except Exception as e:
            current_app.logger.error(f"Mpesa Token Error: {e}")
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