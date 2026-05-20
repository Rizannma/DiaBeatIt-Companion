"""Utility functions for the application"""
import ipaddress
import random
import string
from datetime import datetime
from sqlalchemy import text
from werkzeug.security import generate_password_hash
from models import db, User, PatientProfile, Admin, LoginAudit, encrypt_sensitive_value, ENCRYPTED_PREFIX
from config import Config


def generate_otp():
    """Generate a 6-digit OTP"""
    return ''.join(random.choices(string.digits, k=6))


def get_client_ip(request):
    """Return the first valid client IP from forwarded headers or remote address."""
    candidates = []
    forwarded_for = request.headers.get('X-Forwarded-For', '')
    if forwarded_for:
        candidates.extend([part.strip() for part in forwarded_for.split(',') if part.strip()])

    access_route = getattr(request, 'access_route', None) or []
    candidates.extend([part.strip() for part in access_route if part and part.strip()])

    if request.remote_addr:
        candidates.append(request.remote_addr.strip())

    for candidate in candidates:
        try:
            ipaddress.ip_address(candidate)
            return candidate
        except ValueError:
            continue

    return request.remote_addr or 'unknown'


def log_login_audit(event_type, status='info', user=None, email=None, detail=None, ip_address=None):
    """Write a login/authentication audit event without breaking user flows."""
    try:
        audit = LoginAudit(
            user_id=user.id if user and getattr(user, 'id', None) else None,
            email=email or (getattr(user, 'email', None) if user else None),
            event_type=event_type,
            status=status,
            detail=detail,
            ip_address=ip_address,
        )
        db.session.add(audit)
        db.session.commit()
    except Exception:
        db.session.rollback()


def ensure_role_column():
    """Add role column if it doesn't exist"""
    try:
        with db.engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'user'"))
    except Exception as e:
        print(f"Error adding role column: {e}")


def ensure_lockout_columns():
    """Add login lockout columns if they don't exist"""
    try:
        with db.engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS login_attempts INT NOT NULL DEFAULT 0"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS lockout_until DATETIME NULL"))
    except Exception as e:
        print(f"Error adding lockout columns: {e}")


def ensure_otp_columns():
    """Add OTP verification columns if they don't exist"""
    try:
        with db.engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS otp VARCHAR(6) NULL"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_confirmed BOOLEAN NOT NULL DEFAULT FALSE"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS confirmed_at DATETIME NULL"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS otp_sent_at DATETIME NULL"))
    except Exception as e:
        print(f"Error adding OTP columns: {e}")


def ensure_profile_columns():
    """Add user profile columns if they don't exist"""
    try:
        with db.engine.begin() as conn:
            # Add new columns to patient_profiles table
            conn.execute(text("ALTER TABLE patient_profiles ADD COLUMN IF NOT EXISTS bmi FLOAT NULL"))
            conn.execute(text("ALTER TABLE patient_profiles ADD COLUMN IF NOT EXISTS hip_circumference FLOAT NULL"))
            conn.execute(text("ALTER TABLE patient_profiles ADD COLUMN IF NOT EXISTS hba1c FLOAT NULL"))
            conn.execute(text("ALTER TABLE patient_profiles ADD COLUMN IF NOT EXISTS cholesterol_total FLOAT NULL"))
            conn.execute(text("ALTER TABLE patient_profiles ADD COLUMN IF NOT EXISTS triglyceride FLOAT NULL"))
    except Exception as e:
        print(f"Error adding new profile columns: {e}")


def upgrade_encrypted_text_columns():
    """Widen sensitive text columns so encrypted values fit safely."""
    try:
        with db.engine.begin() as conn:
            conn.execute(text("ALTER TABLE users MODIFY full_name TEXT NOT NULL"))
            conn.execute(text("ALTER TABLE users MODIFY patient_name TEXT NULL"))
            conn.execute(text("ALTER TABLE users MODIFY relationship TEXT NULL"))
            conn.execute(text("ALTER TABLE users MODIFY otp TEXT NULL"))

            conn.execute(text("ALTER TABLE patient_profiles MODIFY gender TEXT NULL"))
            conn.execute(text("ALTER TABLE patient_profiles MODIFY family_history_diabetes TEXT NULL"))
            conn.execute(text("ALTER TABLE patient_profiles MODIFY cardiovascular_history TEXT NULL"))
            conn.execute(text("ALTER TABLE patient_profiles MODIFY hypertension_history TEXT NULL"))

            conn.execute(text("ALTER TABLE glucose_entries MODIFY reading_type TEXT NOT NULL"))
            conn.execute(text("ALTER TABLE glucose_entries MODIFY notes TEXT NULL"))

            conn.execute(text("ALTER TABLE meal_entries MODIFY meal_type TEXT NOT NULL"))
            conn.execute(text("ALTER TABLE meal_entries MODIFY food_items TEXT NOT NULL"))
            conn.execute(text("ALTER TABLE meal_entries MODIFY notes TEXT NULL"))

            conn.execute(text("ALTER TABLE activity_entries MODIFY activity_type TEXT NOT NULL"))
            conn.execute(text("ALTER TABLE activity_entries MODIFY alcohol_consumption TEXT NULL"))
            conn.execute(text("ALTER TABLE activity_entries MODIFY notes TEXT NULL"))

            conn.execute(text("ALTER TABLE sleep_entries MODIFY sleep_quality TEXT NOT NULL"))
            conn.execute(text("ALTER TABLE sleep_entries MODIFY notes TEXT NULL"))

            conn.execute(text("ALTER TABLE admins MODIFY full_name TEXT NOT NULL"))
            conn.execute(text("ALTER TABLE admins MODIFY otp TEXT NULL"))

            conn.execute(text("ALTER TABLE login_audits MODIFY email TEXT NULL"))
            conn.execute(text("ALTER TABLE login_audits MODIFY detail TEXT NULL"))
            conn.execute(text("ALTER TABLE login_audits MODIFY ip_address TEXT NULL"))
    except Exception as e:
        print(f"Error upgrading encrypted text columns: {e}")


def backfill_encrypted_text_data():
    """Encrypt any legacy plaintext values in sensitive text columns."""
    try:
        with db.engine.begin() as conn:
            user_rows = conn.execute(text("SELECT id, full_name, patient_name, relationship, otp FROM users")).mappings().all()
            for row in user_rows:
                updates = {}
                for field in ('full_name', 'patient_name', 'relationship', 'otp'):
                    value = row[field]
                    if value and not str(value).startswith(ENCRYPTED_PREFIX):
                        updates[field] = encrypt_sensitive_value(value)
                if updates:
                    set_clause = ", ".join(f"{field} = :{field}" for field in updates)
                    conn.execute(text(f"UPDATE users SET {set_clause} WHERE id = :id"), {"id": row['id'], **updates})

            profile_rows = conn.execute(text("SELECT id, gender, family_history_diabetes, cardiovascular_history, hypertension_history FROM patient_profiles")).mappings().all()
            for row in profile_rows:
                updates = {}
                for field in ('gender', 'family_history_diabetes', 'cardiovascular_history', 'hypertension_history'):
                    value = row[field]
                    if value and not str(value).startswith(ENCRYPTED_PREFIX):
                        updates[field] = encrypt_sensitive_value(value)
                if updates:
                    set_clause = ", ".join(f"{field} = :{field}" for field in updates)
                    conn.execute(text(f"UPDATE patient_profiles SET {set_clause} WHERE id = :id"), {"id": row['id'], **updates})

            glucose_rows = conn.execute(text("SELECT id, reading_type, notes FROM glucose_entries")).mappings().all()
            for row in glucose_rows:
                updates = {}
                for field in ('reading_type', 'notes'):
                    value = row[field]
                    if value and not str(value).startswith(ENCRYPTED_PREFIX):
                        updates[field] = encrypt_sensitive_value(value)
                if updates:
                    set_clause = ", ".join(f"{field} = :{field}" for field in updates)
                    conn.execute(text(f"UPDATE glucose_entries SET {set_clause} WHERE id = :id"), {"id": row['id'], **updates})

            meal_rows = conn.execute(text("SELECT id, meal_type, food_items, notes FROM meal_entries")).mappings().all()
            for row in meal_rows:
                updates = {}
                for field in ('meal_type', 'food_items', 'notes'):
                    value = row[field]
                    if value and not str(value).startswith(ENCRYPTED_PREFIX):
                        updates[field] = encrypt_sensitive_value(value)
                if updates:
                    set_clause = ", ".join(f"{field} = :{field}" for field in updates)
                    conn.execute(text(f"UPDATE meal_entries SET {set_clause} WHERE id = :id"), {"id": row['id'], **updates})

            activity_rows = conn.execute(text("SELECT id, activity_type, alcohol_consumption, notes FROM activity_entries")).mappings().all()
            for row in activity_rows:
                updates = {}
                for field in ('activity_type', 'alcohol_consumption', 'notes'):
                    value = row[field]
                    if value and not str(value).startswith(ENCRYPTED_PREFIX):
                        updates[field] = encrypt_sensitive_value(value)
                if updates:
                    set_clause = ", ".join(f"{field} = :{field}" for field in updates)
                    conn.execute(text(f"UPDATE activity_entries SET {set_clause} WHERE id = :id"), {"id": row['id'], **updates})

            sleep_rows = conn.execute(text("SELECT id, sleep_quality, notes FROM sleep_entries")).mappings().all()
            for row in sleep_rows:
                updates = {}
                for field in ('sleep_quality', 'notes'):
                    value = row[field]
                    if value and not str(value).startswith(ENCRYPTED_PREFIX):
                        updates[field] = encrypt_sensitive_value(value)
                if updates:
                    set_clause = ", ".join(f"{field} = :{field}" for field in updates)
                    conn.execute(text(f"UPDATE sleep_entries SET {set_clause} WHERE id = :id"), {"id": row['id'], **updates})

            admin_rows = conn.execute(text("SELECT id, full_name, otp FROM admins")).mappings().all()
            for row in admin_rows:
                updates = {}
                for field in ('full_name', 'otp'):
                    value = row[field]
                    if value and not str(value).startswith(ENCRYPTED_PREFIX):
                        updates[field] = encrypt_sensitive_value(value)
                if updates:
                    set_clause = ", ".join(f"{field} = :{field}" for field in updates)
                    conn.execute(text(f"UPDATE admins SET {set_clause} WHERE id = :id"), {"id": row['id'], **updates})

            audit_rows = conn.execute(text("SELECT id, email, detail, ip_address FROM login_audits")).mappings().all()
            for row in audit_rows:
                updates = {}
                for field in ('email', 'detail', 'ip_address'):
                    value = row[field]
                    if value and not str(value).startswith(ENCRYPTED_PREFIX):
                        updates[field] = encrypt_sensitive_value(value)
                if updates:
                    set_clause = ", ".join(f"{field} = :{field}" for field in updates)
                    conn.execute(text(f"UPDATE login_audits SET {set_clause} WHERE id = :id"), {"id": row['id'], **updates})
    except Exception as e:
        print(f"Error backfilling encrypted text data: {e}")


def ensure_meal_columns():
    """Add diet_score column to meal_entries if it doesn't exist"""
    try:
        with db.engine.begin() as conn:
            conn.execute(text("ALTER TABLE meal_entries ADD COLUMN IF NOT EXISTS diet_score INT NULL AFTER food_items"))
    except Exception as e:
        print(f"Error adding meal columns: {e}")


def migrate_user_profiles():
    """Migrate existing user profile data to the new PatientProfile table"""
    try:
        # Check if PatientProfile table exists and has data
        profile_count = PatientProfile.query.count()
        if profile_count > 0:
            print("✓ Patient profiles already migrated")
            return

        # Get all users with role='user' - only regular users get profiles
        users = User.query.filter_by(role='user').all()

        migrated_count = 0
        for user in users:
            # Check if user already has a patient profile
            if user.patient_profile:
                continue

            # Create patient profile for user
            # Note: We can't access the old columns directly since they were removed
            # This migration assumes the profile data was already moved or will be filled later
            patient_profile = PatientProfile(
                user_id=user.id,
            )
            db.session.add(patient_profile)
            migrated_count += 1

        if migrated_count > 0:
            db.session.commit()
            print(f"✓ Created {migrated_count} patient profiles")

            # Note: If there was existing profile data in the User table,
            # it would need to be manually migrated before removing the old columns
            print("Note: Existing profile data migration may be needed if User table had profile columns")

    except Exception as e:
        print(f"Error migrating user profiles: {e}")
        db.session.rollback()


def migrate_admin_users():
    """Migrate any users with role='admin' to the admins table"""
    try:
        # Check if new columns exist - if not, skip this migration (it will run after upgrade)
        if not column_exists('users', 'last_login_notified_date'):
            print("⏭  Skipping admin migration - database columns not yet created")
            return
        
        admin_users = User.query.filter_by(role='admin').all()
        if not admin_users:
            print("✓ No admin users to migrate")
            return

        migrated_count = 0
        for user in admin_users:
            # Check if admin already exists
            existing_admin = Admin.query.filter_by(email=user.email).first()
            if existing_admin:
                print(f"Admin {user.email} already exists, skipping")
                continue

            # Create admin in admins table
            admin = Admin(
                full_name=user.full_name,
                email=user.email,
                password=user.password,  # Password hash is the same
                role='admin',
                is_confirmed=user.is_confirmed,
                confirmed_at=user.confirmed_at,
                login_attempts=user.login_attempts,
                lockout_until=user.lockout_until,
                otp=user.otp,
                otp_sent_at=user.otp_sent_at
            )
            db.session.add(admin)
            migrated_count += 1

        if migrated_count > 0:
            db.session.commit()
            print(f"✓ Migrated {migrated_count} admin users to admins table")

            # Now delete the admin users from users table
            for user in admin_users:
                # Delete associated patient profile if exists
                if user.patient_profile:
                    db.session.delete(user.patient_profile)
                db.session.delete(user)
            db.session.commit()
            print(f"✓ Removed {len(admin_users)} admin users from users table")

    except Exception as e:
        print(f"Error migrating admin users: {e}")
        db.session.rollback()


def drop_old_profile_columns():
    """Drop old profile columns from users table"""
    try:
        cols_users = ['gender', 'ethnicity', 'education_level', 'employment_status', 'family_history_diabetes', 'cardiovascular_history', 'hypertension_history']
        cols_profiles = ['ethnicity', 'education_level', 'employment_status', 'income_level', 'smoking_status', 'insulin_level', 'hdl_cholesterol', 'ldl_cholesterol', 'waist_circumference']
        cols_activity = ['intensity', 'bp_diastolic', 'bp_dialostic']
        profile_tables = ['patient_profiles', 'patient_profile']
        
        with db.engine.begin() as conn:
            for col in cols_users:
                conn.execute(text(f"ALTER TABLE users DROP COLUMN IF EXISTS {col}"))
            for table_name in profile_tables:
                try:
                    for col in cols_profiles:
                        conn.execute(text(f"ALTER TABLE {table_name} DROP COLUMN IF EXISTS {col}"))
                except Exception:
                    # Table may not exist in some environments.
                    pass
            for col in cols_activity:
                conn.execute(text(f"ALTER TABLE activity_entries DROP COLUMN IF EXISTS {col}"))
            print("✓ Dropped deprecated columns")
    except Exception as e:
        print(f"Error dropping old profile columns: {e}")


def column_exists(table_name, column_name):
    """
    Check if a column exists in a database table.
    Safe to call before migrations are applied.
    
    Args:
        table_name: Name of the table (e.g., 'users')
        column_name: Name of the column (e.g., 'last_login_notified_date')
    
    Returns:
        bool: True if column exists, False otherwise
    """
    try:
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        columns = [col["name"] for col in inspector.get_columns(table_name)]
        exists = column_name in columns
        return exists
    except Exception as e:
        # If we can't check, assume column doesn't exist to be safe
        print(f"Warning: Could not check for column {table_name}.{column_name}: {e}")
        return False


def cleanup_admin_profiles():
    """Remove patient profiles for admin users (shouldn't exist after migration)"""
    try:
        # This is a safety cleanup - admins shouldn't have profiles
        admin_profiles = PatientProfile.query.join(User).filter(User.role == 'admin').all()
        if admin_profiles:
            for profile in admin_profiles:
                db.session.delete(profile)
            db.session.commit()
            print(f"✓ Cleaned up {len(admin_profiles)} admin patient profiles")
        else:
            print("✓ No admin patient profiles to clean up")
    except Exception as e:
        print(f"Error cleaning up admin profiles: {e}")
        db.session.rollback()


def ensure_admin_user():
    """Create or update admin user"""
    if not Config.ADMIN_EMAIL or not Config.ADMIN_PASSWORD:
        print("Warning: Admin credentials not configured in environment variables. Skipping admin creation.")
        return
    
    admin = Admin.query.filter_by(email=Config.ADMIN_EMAIL).first()
    
    if admin:
        # Update existing admin
        if admin.role != Config.ADMIN_ROLE or not admin.check_password(Config.ADMIN_PASSWORD):
            admin.role = Config.ADMIN_ROLE
            admin.password = generate_password_hash(Config.ADMIN_PASSWORD)
            admin.full_name = 'Admin'
            db.session.commit()
    else:
        # Create new admin
        admin = Admin(
            full_name='Admin',
            email=Config.ADMIN_EMAIL,
            password=generate_password_hash(Config.ADMIN_PASSWORD),
            role=Config.ADMIN_ROLE,
            is_confirmed=True,
            confirmed_at=datetime.utcnow()
        )
        db.session.add(admin)
        db.session.commit()
    
    print("✓ Admin user ensured")


def initialize_database(app):
    """Initialize database tables and columns"""
    with app.app_context():
        db.create_all()
        ensure_role_column()
        ensure_lockout_columns()
        ensure_otp_columns()
        ensure_profile_columns()  # Add new profile columns
        ensure_meal_columns()     # Add diet_score column
        upgrade_encrypted_text_columns()
        backfill_encrypted_text_data()
        migrate_admin_users()  # Migrate admin users first
        migrate_user_profiles()  # Then migrate profiles for remaining users
        drop_old_profile_columns()  # Drop old columns after migration
        cleanup_admin_profiles()  # Clean up any remaining admin profiles
        ensure_admin_user()  # Ensure the default admin exists
        print("✓ Database initialized")
