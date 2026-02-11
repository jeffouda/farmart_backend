from flask import Blueprint

livestock_bp = Blueprint("livestock", __name__)

from . import routes
