"""Main Flask Application"""
from flask import Flask, make_response, send_from_directory, request, redirect
from flask_migrate import Migrate
from werkzeug.middleware.proxy_fix import ProxyFix

import logging

from config import Config
from models import db, init_login_manager
from utils import initialize_database
from routes import register_blueprints
from scheduler import init_scheduler

logger = logging.getLogger(__name__)


def create_app():
    """Application factory"""
    app = Flask(__name__)
    app.config.from_object(Config)

    if Config.TRUST_PROXY_HEADERS:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    engine_options = {
        'pool_pre_ping': True,
        'pool_recycle': 280
    }

    if Config.DB_REQUIRE_SSL:
        ssl_options = {}
        if Config.DB_SSL_CA:
            ssl_options['ca'] = Config.DB_SSL_CA
        if Config.DB_SSL_CERT:
            ssl_options['cert'] = Config.DB_SSL_CERT
        if Config.DB_SSL_KEY:
            ssl_options['key'] = Config.DB_SSL_KEY
        engine_options['connect_args'] = {'ssl': ssl_options} if ssl_options else {'ssl': {}}

    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        **app.config.get('SQLALCHEMY_ENGINE_OPTIONS', {}),
        **engine_options
    }
    
    # Initialize extensions
    db.init_app(app)
    migrate = Migrate(app, db)
    init_login_manager(app)

    # Register blueprints
    register_blueprints(app)

    @app.before_request
    def enforce_https_transport():
        if not Config.ENFORCE_HTTPS:
            return None

        if app.debug:
            return None

        if request.is_secure:
            return None

        forwarded_proto = request.headers.get('X-Forwarded-Proto', '').lower()
        if forwarded_proto == 'https':
            return None

        if request.host.startswith('127.0.0.1') or request.host.startswith('localhost'):
            return None

        secure_url = request.url.replace('http://', 'https://', 1)
        return redirect(secure_url, code=301)

    @app.after_request
    def add_security_headers(response):
        if Config.ENFORCE_HTTPS:
            response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        response.headers.setdefault('Permissions-Policy', 'geolocation=(), microphone=(), camera=()')

        origin = request.headers.get('Origin')
        allowed_origins = [origin.strip() for origin in Config.CORS_ALLOWED_ORIGINS.split(',')] if Config.CORS_ALLOWED_ORIGINS else []
        if origin and (Config.CORS_ALLOWED_ORIGINS == '*' or origin in allowed_origins):
            response.headers['Access-Control-Allow-Origin'] = origin if Config.CORS_ALLOWED_ORIGINS != '*' else '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            response.headers['Vary'] = 'Origin'

        return response

    @app.get('/manifest.webmanifest')
    def manifest():
        response = make_response(send_from_directory(
            app.static_folder,
            'manifest.webmanifest',
            mimetype='application/manifest+json'
        ))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response

    @app.route('/service-worker.js')
    def sw():
        response = make_response(
            send_from_directory(app.root_path, 'service-worker.js', mimetype='application/javascript')
        )
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response

    # Initialize database
    try:
        initialize_database(app)
    except Exception as exc:
        logger.error('[App] Database initialization failed: %s', exc, exc_info=True)

    # Initialize scheduler
    with app.app_context():
        logger.info('[App] Initializing APScheduler for push notifications...')
    init_scheduler(app)
    logger.info('[App] APScheduler initialized successfully. Scheduled jobs: daily_log_reminder (19:00), weekly_summary (Sun 18:00), profile_refresh_reminder (1st day 09:00)')
    
    return app

# Create app instance
app = create_app()


if __name__ == '__main__':
    app.run(debug=True)