import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def _build_database_uri():
    database_url = os.environ.get('DATABASE_URL')
    db_host = os.environ.get('DB_HOST')
    db_user = os.environ.get('DB_USER')
    db_password = os.environ.get('DB_PASSWORD')
    db_name = os.environ.get('DB_NAME')
    db_port = os.environ.get('DB_PORT', '5432')

    if database_url:
        if database_url.startswith('postgres://'):
            return database_url.replace('postgres://', 'postgresql+psycopg2://', 1)
        if database_url.startswith('postgresql://'):
            return database_url.replace('postgresql://', 'postgresql+psycopg2://', 1)
        return database_url

    if db_host and db_user and db_password and db_name:
        return f"postgresql+psycopg2://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

    raise RuntimeError(
        'Database configuration is incomplete. In production, set DATABASE_URL or '
        'DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, and DB_PORT environment variables.'
    )


class Config:
    """Application configuration"""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'fallback_secret_key')
    FIELD_ENCRYPTION_KEY = os.environ.get('FIELD_ENCRYPTION_KEY')
    BREVO_API_KEY = os.environ.get('BREVO_API_KEY')

    DB_HOST = os.environ.get('DB_HOST')
    DB_USER = os.environ.get('DB_USER')
    DB_PASSWORD = os.environ.get('DB_PASSWORD')
    DB_NAME = os.environ.get('DB_NAME')
    DB_PORT = os.environ.get('DB_PORT', '5432')
    DATABASE_URL = os.environ.get('DATABASE_URL')

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 280
    }

    # Transport security defaults
    ENFORCE_HTTPS = os.environ.get('ENFORCE_HTTPS', 'false').lower() == 'true'
    TRUST_PROXY_HEADERS = os.environ.get('TRUST_PROXY_HEADERS', 'false').lower() == 'true'
    PREFERRED_URL_SCHEME = 'https'

    # Secure cookie defaults
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = os.environ.get('REMEMBER_COOKIE_SAMESITE', 'Lax')
    REMEMBER_COOKIE_SECURE = os.environ.get('REMEMBER_COOKIE_SECURE', 'false').lower() == 'true'

    # Optional database TLS settings
    DB_REQUIRE_SSL = os.environ.get('DB_REQUIRE_SSL', 'false').lower() == 'true'
    DB_SSL_CA = os.environ.get('DB_SSL_CA')
    DB_SSL_CERT = os.environ.get('DB_SSL_CERT')
    DB_SSL_KEY = os.environ.get('DB_SSL_KEY')

    CORS_ALLOWED_ORIGINS = os.environ.get('CORS_ALLOWED_ORIGINS', '*')
    SQLALCHEMY_DATABASE_URI = _build_database_uri()
    
    # Admin credentials
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')
    ADMIN_ROLE = 'admin'
    
    # Email settings
    SENDER_EMAIL = "officialdiabeatit.admin@gmail.com"
    SENDER_NAME = "Diabeatit Admin"
    OTP_EXPIRY_SECONDS = 30

    # Web Push settings
    PUSH_VAPID_PUBLIC_KEY = os.environ.get('PUSH_VAPID_PUBLIC_KEY')
    PUSH_VAPID_PRIVATE_KEY = os.environ.get('PUSH_VAPID_PRIVATE_KEY')
    PUSH_VAPID_CLAIMS_SUBJECT = os.environ.get('PUSH_VAPID_CLAIMS_SUBJECT', 'mailto:officialdiabeatit.admin@gmail.com')
