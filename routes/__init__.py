"""Routes blueprint initialization"""
from flask import Blueprint

# Create blueprints
auth_bp = Blueprint('auth', __name__, url_prefix='')
verification_bp = Blueprint('verification', __name__, url_prefix='')
user_bp = Blueprint('user', __name__, url_prefix='')
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')
push_bp = Blueprint('push', __name__, url_prefix='')

# Import routes to register them with blueprints AFTER blueprint creation
from . import auth, verification, user, admin, push

def register_blueprints(app):
    """Register all blueprints with the app"""
    app.register_blueprint(auth_bp)
    app.register_blueprint(verification_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(push_bp)
