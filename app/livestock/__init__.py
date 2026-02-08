from flask import Blueprint

livestock_bp = Blueprint('livestock', __name__, url_prefix='/api/livestock')

from . import routes
