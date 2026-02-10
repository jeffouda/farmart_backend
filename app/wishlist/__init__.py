from flask import Blueprint

wishlist_bp = Blueprint("wishlist", __name__)

from . import routes
