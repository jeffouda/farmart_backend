import logging
from flask import jsonify
from werkzeug.exceptions import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from jwt.exceptions import PyJWTError

logger = logging.getLogger(__name__)

def register_error_handlers(app):
    @app.errorhandler(400)
    def bad_request(e):
        logger.warning(f"Bad request: {str(e)}")
        return jsonify({"error": "Bad request", "message": str(e)}), 400

    @app.errorhandler(401)
    def unauthorized(e):
        return jsonify({"error": "Unauthorized", "message": "Authentication required"}), 401

    @app.errorhandler(403)
    def forbidden(e):
        return jsonify({"error": "Forbidden", "message": "Access denied"}), 403

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not found", "message": "Resource not found"}), 404

    @app.errorhandler(500)
    def internal_error(e):
        logger.error(f"Internal server error: {str(e)}", exc_info=True)
        return jsonify({"error": "Internal server error", "message": "An unexpected error occurred"}), 500

    @app.errorhandler(SQLAlchemyError)
    def handle_db_error(e):
        logger.error(f"Database error: {str(e)}", exc_info=True)
        return jsonify({"error": "Database error", "message": "A database error occurred"}), 500

    @app.errorhandler(PyJWTError)
    def handle_jwt_error(e):
        logger.warning(f"JWT error: {str(e)}")
        return jsonify({"error": "Authentication error", "message": "Invalid or expired token"}), 401

    @app.errorhandler(Exception)
    def handle_exception(e):
        if isinstance(e, HTTPException):
            return e
        logger.error(f"Unhandled exception: {str(e)}", exc_info=True)
        return jsonify({"error": "Internal server error", "message": "An unexpected error occurred"}), 500
