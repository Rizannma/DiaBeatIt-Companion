"""Authentication routes - Login, Signup"""
from flask import render_template, redirect, url_for, flash, session, request, current_app
from flask_login import current_user, login_user
from datetime import datetime, timedelta, date
from werkzeug.security import generate_password_hash

from . import auth_bp
from models import db, User, PatientProfile, Admin
from forms import SignupForm, LoginForm
from utils import generate_otp, log_login_audit, get_client_ip, column_exists
from email_service import send_otp_email
from push_service import send_notification_to_user, build_notification_payload
from config import Config


@auth_bp.route('/', methods=['GET', 'POST'])
def login():
    """User login route"""
    
    if current_user.is_authenticated:
        return redirect(url_for('admin.dashboard' if current_user.is_admin else 'user.dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        client_ip = get_client_ip(request)
        user = User.query.filter_by(email=form.email.data).first()
        if not user:
            user = Admin.query.filter_by(email=form.email.data).first()
        if user:
            if user.lockout_until and datetime.utcnow() < user.lockout_until:
                time_left = user.lockout_until - datetime.utcnow()
                flash(f"Account locked. Try again in {int(time_left.total_seconds() // 60)} mins.", 'danger')
                log_login_audit('login_locked', status='warning', user=user, detail='Login blocked due to active lockout.', ip_address=client_ip)
                return render_template('login.html', form=form)

            if user.check_password(form.password.data):
                was_locked = bool(user.lockout_until and datetime.utcnow() < user.lockout_until)
                user.login_attempts = 0
                user.lockout_until = None

                if was_locked:
                    # Send account unlocked notification
                    try:
                        payload = build_notification_payload('account-unlocked')
                        send_notification_to_user(user.id, payload['title'], payload['body'], payload['tag'], payload['url'])
                        current_app.logger.info('[Auth] Account unlock notification sent to user %s', user.id)
                    except Exception as e:
                        current_app.logger.warning('[Auth] Failed to send account unlock notification: %s', e)

                # Check if verification needed
                needs_verification = False
                if user.is_admin:
                    needs_verification = False
                elif not user.is_confirmed:
                    needs_verification = True
                elif not user.confirmed_at or (datetime.utcnow() - user.confirmed_at) > timedelta(days=15):
                    needs_verification = True

                if needs_verification:
                    otp = generate_otp()
                    user.otp = otp
                    user.otp_sent_at = datetime.utcnow()
                    db.session.commit()
                    session['verify_email'] = user.email
                    session['verification_reason'] = 'first login or periodic verification'
                    if send_otp_email(user.email, otp, "Verify Your Diabeatit Account"):
                        log_login_audit('verification_otp_sent', status='info', user=user, detail='Verification OTP sent after login.', ip_address=client_ip)
                        flash('A verification code has been sent to your email. Please enter it to continue.', 'info')
                        return redirect(url_for('verification.verify_account_otp'))
                    else:
                        log_login_audit('verification_otp_failed', status='error', user=user, detail='Failed to send verification OTP email.', ip_address=client_ip)
                        flash('Failed to send verification email. Please try again.', 'danger')
                        return render_template('login.html', form=form)

                # Successful login without verification needed
                login_user(user)
                
                # Send welcome-back notification on every successful login
                try:
                    send_notification_to_user(user.id, "Welcome back", "Your daily insights are ready.", "login-success", "/dashboard")
                    current_app.logger.info('[Auth] Welcome back notification sent to user %s', user.id)
                except Exception as e:
                    current_app.logger.warning('[Auth] Failed to send welcome back notification: %s', e)
                
                db.session.commit()
                log_login_audit('login_success', status='success', user=user, detail='Direct login successful.', ip_address=client_ip)
                flash('Login successful! Your account is up to date.', 'success')
                return redirect(url_for('admin.dashboard' if user.is_admin else 'user.dashboard'))
            else:
                user.login_attempts = (user.login_attempts or 0) + 1
                if user.login_attempts >= 3:
                    if user.login_attempts == 3:
                        minutes = 30
                    elif user.login_attempts == 4:
                        minutes = 60
                    else:
                        minutes = 90
                    user.lockout_until = datetime.utcnow() + timedelta(minutes=minutes)
                    
                    # Store lock_until for display in unlock notification (if column exists)
                    if column_exists('users', 'lock_until'):
                        user.lock_until = user.lockout_until
                    
                    # Send account locked notification (if column exists)
                    if column_exists('users', 'lock_until'):
                        try:
                            payload = build_notification_payload('account-locked', lockout_minutes=minutes)
                            send_notification_to_user(user.id, payload['title'], payload['body'], payload['tag'], payload['url'])
                            current_app.logger.info('[Auth] Account lock notification sent to user %s for %d minutes', user.id, minutes)
                        except Exception as e:
                            current_app.logger.warning('[Auth] Failed to send account lock notification: %s', e)
                    
                    flash(f"Too many attempts. Account locked for {minutes} minutes.", 'danger')
                    log_login_audit('login_failed_lockout', status='warning', user=user, detail=f'Failed login triggered {minutes}-minute lockout.', ip_address=client_ip)
                else:
                    flash(f"Login unsuccessful. Please check email and password. {3 - user.login_attempts} attempts remaining.", 'danger')
                    log_login_audit('login_failed', status='warning', user=user, detail=f'Incorrect password. Attempts: {user.login_attempts}.', ip_address=client_ip)
                db.session.commit()
        else:
            flash('Email not found.', 'danger')
            log_login_audit('login_failed_no_account', status='warning', email=form.email.data, detail='Login attempted with unknown email.', ip_address=client_ip)
    
    return render_template('login.html', form=form)


@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    """User signup route"""
    form = SignupForm()
    if form.validate_on_submit():
        # Validate account type specific fields
        if form.account_for.data == 'other':
            if not form.patient_name.data:
                flash('Please enter the patient\'s full name.', 'danger')
                return render_template('signup.html', form=form)
            if not form.patient_age.data or form.patient_age.data < 0:
                flash('Please enter the patient\'s valid age.', 'danger')
                return render_template('signup.html', form=form)
            if not form.relationship.data:
                flash('Please select your relationship to the patient.', 'danger')
                return render_template('signup.html', form=form)
            if not form.consent.data:
                flash('You must confirm legal authority for this patient.', 'danger')
                return render_template('signup.html', form=form)

        new_user = User(
            full_name=form.full_name.data,
            email=form.email.data,
            age=form.age.data,
            account_for=form.account_for.data,
            patient_name=form.patient_name.data if form.account_for.data == 'other' else None,
            patient_age=form.patient_age.data if form.account_for.data == 'other' else None,
            relationship=form.relationship.data if form.account_for.data == 'other' else None,
            password=generate_password_hash(form.password.data),
            role='user'
        )

        # Create an empty profile that will be completed after signup
        new_user.patient_profile = PatientProfile()

        try:
            db.session.add(new_user)
            db.session.commit()
            flash('Account created successfully! Please log in to confirm your account.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            print(f"Error creating account: {str(e)}")
            flash(f'Error: {str(e)}', 'danger')

    return render_template('signup.html', form=form)


@auth_bp.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    """Forgot password route - sends OTP"""
    from flask import request
    
    if request.method == 'POST':
        client_ip = get_client_ip(request)
        email = request.form.get('email')
        if not email:
            flash('Please enter your email.', 'danger')
            return render_template('forgot_password.html')
        
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('No account found with this email.', 'danger')
            log_login_audit('password_reset_no_account', status='warning', email=email, detail='Password reset requested for unknown account.', ip_address=client_ip)
            return render_template('forgot_password.html')
        
        # Send reset OTP
        otp = generate_otp()
        user.otp = otp
        user.otp_sent_at = datetime.utcnow()
        db.session.commit()
        session['reset_email'] = email
        
        if send_otp_email(user.email, otp, "Reset Your Diabeatit Password"):
            log_login_audit('password_reset_otp_sent', status='info', user=user, detail='Password reset OTP sent.', ip_address=client_ip)
            flash('Password reset OTP sent to your email.', 'success')
            return redirect(url_for('verification.verify_reset_password_otp'))
        else:
            log_login_audit('password_reset_otp_failed', status='error', user=user, detail='Failed to send password reset OTP.', ip_address=client_ip)
            flash('Failed to send reset email. Please try again.', 'danger')
    
    return render_template('forgot_password.html')
