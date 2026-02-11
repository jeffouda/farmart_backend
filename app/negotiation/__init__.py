from flask import Blueprint

negotiation_bp = Blueprint("negotiation", __name__)

from . import routes
