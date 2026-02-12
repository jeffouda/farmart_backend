import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logging(app):
    """Configure production-ready logging"""
    
    log_level = logging.INFO if app.config.get('FLASK_ENV') == 'production' else logging.DEBUG
    
    if not os.path.exists('logs'):
        os.mkdir('logs')
    
    file_handler = RotatingFileHandler('logs/farmart.log', maxBytes=10485760, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(log_level)
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(log_level)
    
    logging.basicConfig(level=log_level, handlers=[file_handler, console_handler])
    
    app.logger.info('FarmArt application startup')
