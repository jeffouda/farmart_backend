from flask import Blueprint

bargain_bp = Blueprint("bargain", __name__)

from . import routes
