from flask import Blueprint

bargain_bp = Blueprint("bargain", __name__, url_prefix="/api/bargain")

from . import routes
