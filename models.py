from datetime import datetime
import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin
from sqlalchemy.types import Text, TypeDecorator
from werkzeug.security import check_password_hash

from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
ENCRYPTED_PREFIX = "enc$"


def _derive_fernet_key(seed):
    raw_seed = (seed or '').encode('utf-8')
    digest = hashlib.sha256(raw_seed).digest()
    return base64.urlsafe_b64encode(digest)


@lru_cache(maxsize=1)
def _field_fernet():
    seed = Config.FIELD_ENCRYPTION_KEY or Config.SECRET_KEY
    if not seed:
        return None
    return Fernet(_derive_fernet_key(seed))


def encrypt_sensitive_value(value):
    """Encrypt a scalar value for storage using the shared app key."""
    if value is None:
        return None

    fernet = _field_fernet()
    if not fernet:
        return str(value)

    plaintext = str(value)
    if plaintext.startswith(ENCRYPTED_PREFIX):
        return plaintext

    token = fernet.encrypt(plaintext.encode('utf-8')).decode('utf-8')
    return f"{ENCRYPTED_PREFIX}{token}"


def decrypt_sensitive_value(value):
    """Decrypt a stored value if it is encrypted; otherwise return it as-is."""
    if value is None:
        return None

    fernet = _field_fernet()
    if not fernet:
        return value

    text_value = str(value)
    if not text_value.startswith(ENCRYPTED_PREFIX):
        return value

    try:
        token = text_value[len(ENCRYPTED_PREFIX):]
        return fernet.decrypt(token.encode('utf-8')).decode('utf-8')
    except (InvalidToken, ValueError, AttributeError):
        return value


class EncryptedText(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt_sensitive_value(value)

    def process_result_value(self, value, dialect):
        return decrypt_sensitive_value(value)

def init_login_manager(app):
    """Initialize Flask-Login"""
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'


@login_manager.user_loader
def load_user(user_id):
    """Load user or admin by ID"""
    if isinstance(user_id, str) and user_id.startswith('admin-'):
        try:
            admin_id = int(user_id.split('-', 1)[1])
        except ValueError:
            return None
        return Admin.query.get(admin_id)
    return User.query.get(int(user_id))


class User(UserMixin, db.Model):
    """User model for authentication and account management"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(EncryptedText(), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    age = db.Column(db.Integer, nullable=False)
    account_for = db.Column(db.String(20), nullable=False)

    # Account type specific fields (for caregivers)
    patient_name = db.Column(EncryptedText(), nullable=True)
    patient_age = db.Column(db.Integer, nullable=True)
    relationship = db.Column(EncryptedText(), nullable=True)

    # Security & authentication
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user')
    is_confirmed = db.Column(db.Boolean, default=False)
    confirmed_at = db.Column(db.DateTime, nullable=True)

    # Login security
    login_attempts = db.Column(db.Integer, nullable=False, default=0)
    lockout_until = db.Column(db.DateTime, nullable=True)

    # OTP verification
    otp = db.Column(EncryptedText(), nullable=True)
    otp_sent_at = db.Column(db.DateTime, nullable=True)

    # Notification tracking
    last_login_notified_date = db.Column(db.Date, nullable=True)  # Tracks if login notification sent today
    lock_until = db.Column(db.DateTime, nullable=True)  # Account lock expiry time (for display in unlock notification)

    # Relationship to patient profile
    patient_profile = db.relationship('PatientProfile', backref='user', uselist=False, cascade='all, delete-orphan')

    def check_password(self, password):
        """Check if password matches"""
        return check_password_hash(self.password, password)

    @property
    def is_admin(self):
        """Check if user is admin"""
        return self.role == 'admin'

    @property
    def subject_name(self):
        if self.account_for == 'other' and self.patient_name:
            return self.patient_name
        return self.full_name

    @property
    def subject_age(self):
        if self.account_for == 'other' and self.patient_age is not None:
            return self.patient_age
        return self.age

    @property
    def subject_diabetes_type(self):
        if self.patient_profile and self.patient_profile.diabetes_type:
            return self.patient_profile.diabetes_type
        return 'Not set'

    @property
    def profile_complete(self):
        """Check if patient profile is complete"""
        profile = PatientProfile.query.filter_by(user_id=self.id).first()
        if not profile:
            return False
        return profile.is_complete


class Admin(UserMixin, db.Model):
    """Admin model for admin authentication only"""
    __tablename__ = 'admins'

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(EncryptedText(), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='admin')
    is_confirmed = db.Column(db.Boolean, default=True)
    confirmed_at = db.Column(db.DateTime, nullable=True)
    login_attempts = db.Column(db.Integer, nullable=False, default=0)
    lockout_until = db.Column(db.DateTime, nullable=True)
    otp = db.Column(EncryptedText(), nullable=True)
    otp_sent_at = db.Column(db.DateTime, nullable=True)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    @property
    def is_admin(self):
        return True

    def get_id(self):
        return f"admin-{self.id}"


class PatientProfile(db.Model):
    """Patient profile model for medical and demographic data"""
    __tablename__ = 'patient_profiles'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Demographic information
    gender = db.Column(EncryptedText(), nullable=True)

    # Lifestyle & History
    family_history_diabetes = db.Column(EncryptedText(), nullable=True)
    cardiovascular_history = db.Column(EncryptedText(), nullable=True)
    hypertension_history = db.Column(EncryptedText(), nullable=True)

    # Physical measurements
    height_cm = db.Column(db.Float, nullable=True)  # Height in centimeters
    weight_kg = db.Column(db.Float, nullable=True)  # Weight in kilograms
    bmi = db.Column(db.Float, nullable=True) # Stored BMI value
    hip_circumference = db.Column(db.Float, nullable=True)  # Hip circumference in cm

    # Medical & Lab Results
    hba1c = db.Column(db.Float, nullable=True)  # HbA1c percentage
    cholesterol_total = db.Column(db.Float, nullable=True)  # Total cholesterol in mg/dL
    triglyceride = db.Column(db.Float, nullable=True)  # Triglyceride in mg/dL

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def bmi_category(self):
        """Get BMI category based on WHO classification"""
        if not self.bmi:
            return None

        if self.bmi < 18.5:
            return "Underweight"
        elif self.bmi < 25:
            return "Normal weight"
        elif self.bmi < 30:
            return "Overweight"
        elif self.bmi < 35:
            return "Obese Class I"
        elif self.bmi < 40:
            return "Obese Class II"
        else:
            return "Obese Class III"

    @property
    def is_complete(self):
        """Check if all required profile fields are filled"""
        required = [
            self.gender,
            self.family_history_diabetes,
            self.cardiovascular_history,
            self.hypertension_history,
            self.height_cm,
            self.weight_kg
        ]
        return all(required)


class GlucoseEntry(db.Model):
    __tablename__ = 'glucose_entries'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    glucose_level = db.Column(db.Float, nullable=False)
    reading_type = db.Column(EncryptedText(), nullable=False)
    hba1c = db.Column(db.Float, nullable=True)
    heart_rate = db.Column(db.Integer, nullable=True)
    notes = db.Column(EncryptedText(), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('glucose_entries', lazy='dynamic'))


class MealEntry(db.Model):
    __tablename__ = 'meal_entries'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    meal_type = db.Column(EncryptedText(), nullable=False)
    food_items = db.Column(EncryptedText(), nullable=False)
    diet_score = db.Column(db.Integer, nullable=True) # Numerical 1-10
    carbohydrates = db.Column(db.Float, nullable=True)
    calories = db.Column(db.Float, nullable=True)
    notes = db.Column(EncryptedText(), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('meal_entries', lazy='dynamic'))


class ActivityEntry(db.Model):
    __tablename__ = 'activity_entries'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    activity_type = db.Column(EncryptedText(), nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False)
    bp_systolic = db.Column(db.Integer, nullable=True)
    alcohol_consumption = db.Column(EncryptedText(), nullable=True)
    screen_time_minutes = db.Column(db.Integer, nullable=True)
    notes = db.Column(EncryptedText(), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('activity_entries', lazy='dynamic'))


class SleepEntry(db.Model):
    __tablename__ = 'sleep_entries'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    sleep_duration = db.Column(db.Float, nullable=False)
    sleep_quality = db.Column(EncryptedText(), nullable=False)
    notes = db.Column(EncryptedText(), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('sleep_entries', lazy='dynamic'))


class PushSubscription(db.Model):
    __tablename__ = 'push_subscriptions'

    endpoint_hash = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    endpoint = db.Column(db.Text, nullable=False)
    p256dh = db.Column(db.String(512), nullable=False)
    auth = db.Column(db.String(256), nullable=False)
    expiration_time = db.Column(db.DateTime, nullable=True)
    user_agent = db.Column(db.String(512), nullable=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('push_subscriptions', lazy='dynamic', cascade='all, delete-orphan'))


class LoginAudit(db.Model):
    __tablename__ = 'login_audits'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    email = db.Column(EncryptedText(), nullable=True)
    event_type = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='info')
    detail = db.Column(EncryptedText(), nullable=True)
    ip_address = db.Column(EncryptedText(), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('login_audits', lazy='dynamic'))
