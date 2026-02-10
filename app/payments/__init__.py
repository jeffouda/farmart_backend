from flask import Blueprint

payment_bp = Blueprint('payments', __name__)

from . import routes