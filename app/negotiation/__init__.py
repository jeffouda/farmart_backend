from flask import Blueprint

negotiation_bp = Blueprint("negotiation", __name__, url_prefix="/api/negotiation")

from . import routes
