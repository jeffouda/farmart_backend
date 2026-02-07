from flask import Blueprint

wishlist_bp = Blueprint("wishlist", __name__, url_prefix="/api/wishlist")

from . import routes
