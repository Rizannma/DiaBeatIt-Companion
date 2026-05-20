"""OTP Verification routes"""
from flask import render_template, redirect, url_for, flash, session, current_app
from flask_login import login_user, current_user
from datetime import datetime, timedelta, date
from werkzeug.security import generate_password_hash

from . import verification_bp
from models import db, User
from forms import ConfirmForm, ResetPasswordForm
from utils import generate_otp, log_login_audit, column_exists
from email_service import send_otp_email
from push_service import send_notification_to_user, build_notification_payload
from config import Config


@verification_bp.route('/verify_account_otp', methods=['GET', 'POST'])
def verify_account_otp():
    """Verify account via OTP"""
    
    email = session.get('verify_email')
    if not email:
        flash('Session expired. Please log in again.', 'danger')
        return redirect(url_for('auth.login'))

    user = User.query.filter_by(email=email).first()
    if not user or not user.otp:
        flash('Invalid request.', 'danger')
        log_login_audit('verify_account_invalid', status='warning', email=email, detail='Account OTP verification requested with invalid session/state.')
        return redirect(url_for('auth.login'))
    
    otp_message = ''
    otp_message_type = ''
    expired = False
    
    if user.otp_sent_at and datetime.utcnow() - user.otp_sent_at > timedelta(seconds=Config.OTP_EXPIRY_SECONDS):
        user.otp = None
        user.otp_sent_at = None
        db.session.commit()
        log_login_audit('verify_account_expired', status='warning', user=user, detail='Account verification OTP expired.')
        otp_message = 'OTP expired. Please request a new one.'
        otp_message_type = 'danger'
        expired = True

    remaining_seconds = 0
    if user.otp_sent_at:
        remaining_seconds = max(0, Config.OTP_EXPIRY_SECONDS - (datetime.utcnow() - user.otp_sent_at).seconds)

    form = ConfirmForm()
    if form.validate_on_submit() and not expired:
        if user.otp == form.otp.data:
            user.is_confirmed = True
            user.confirmed_at = datetime.utcnow()
            user.otp = None
            user.otp_sent_at = None
            db.session.commit()
            login_user(user)
            log_login_audit('verify_account_success', status='success', user=user, detail='Account verification OTP accepted.')
            flash('Account verified and logged in successfully!', 'success')
            return redirect(url_for('admin.dashboard' if user.is_admin else 'user.dashboard'))
        else:
            log_login_audit('verify_account_failed', status='warning', user=user, detail='Invalid account verification OTP entered.')
            otp_message = 'Invalid OTP code.'
            otp_message_type = 'danger'

    return render_template('confirm_account_otp.html', form=form, remaining_seconds=remaining_seconds, 
                         otp_message=otp_message, otp_message_type=otp_message_type, expired=expired)


@verification_bp.route('/resend_confirmation_otp')
def resend_confirmation_otp():
    """Resend account verification OTP"""
    email = session.get('verify_email')
    if not email:
        flash('Session expired. Please log in again.', 'danger')
        return redirect(url_for('auth.login'))

    user = User.query.filter_by(email=email).first()
    if not user or not user.otp_sent_at:
        flash('Invalid request.', 'danger')
        log_login_audit('verify_account_resend_invalid', status='warning', email=email, detail='Resend confirmation OTP requested with invalid state.')
        return redirect(url_for('auth.login'))
    
    # Check if 30 seconds have passed
    if datetime.utcnow() - user.otp_sent_at < timedelta(seconds=Config.OTP_EXPIRY_SECONDS):
        remaining = Config.OTP_EXPIRY_SECONDS - (datetime.utcnow() - user.otp_sent_at).seconds
        flash(f'Please wait {remaining} seconds before resending.', 'warning')
        log_login_audit('verify_account_resend_rate_limited', status='info', user=user, detail=f'Resend confirmation OTP rate-limited ({remaining}s left).')
        return redirect(url_for('verification.verify_account_otp'))
    
    # Resend OTP
    otp = generate_otp()
    user.otp = otp
    user.otp_sent_at = datetime.utcnow()
    db.session.commit()
    if send_otp_email(user.email, otp, "Confirm Your Diabeatit Account"):
        log_login_audit('verify_account_resend_sent', status='info', user=user, detail='Confirmation OTP resent successfully.')
        flash('OTP resent to your email.', 'success')
    else:
        log_login_audit('verify_account_resend_failed', status='error', user=user, detail='Failed to resend confirmation OTP.')
        flash('Failed to resend OTP.', 'danger')
    return redirect(url_for('verification.verify_account_otp'))


@verification_bp.route('/verify_login_otp/<email>', methods=['GET', 'POST'])
def verify_login_otp(email):
    """Verify login via OTP"""
    user = User.query.filter_by(email=email).first()
    if not user or not user.otp or not user.is_confirmed:
        flash('Invalid request.', 'danger')
        log_login_audit('verify_login_invalid', status='warning', email=email, detail='Login OTP verification requested with invalid state.')
        return redirect(url_for('auth.login'))
    
    # Check if OTP expired
    if user.otp_sent_at and datetime.utcnow() - user.otp_sent_at > timedelta(seconds=Config.OTP_EXPIRY_SECONDS):
        user.otp = None
        user.otp_sent_at = None
        db.session.commit()
        log_login_audit('verify_login_expired', status='warning', user=user, detail='Login OTP expired before verification.')
        flash('OTP expired. Please log in again to receive a new one.', 'danger')
        return redirect(url_for('auth.login'))
    
    remaining_seconds = max(0, Config.OTP_EXPIRY_SECONDS - (datetime.utcnow() - user.otp_sent_at).seconds)
    
    form = ConfirmForm()
    if form.validate_on_submit():
        if user.otp == form.otp.data:
            user.otp = None
            user.otp_sent_at = None
            db.session.commit()
            login_user(user)
            
            # Send login success notification (if migration applied)
            if column_exists('users', 'last_login_notified_date'):
                today = date.today()
                if user.last_login_notified_date != today:
                    try:
                        payload = build_notification_payload('login-success')
                        send_notification_to_user(user.id, payload['title'], payload['body'], payload['tag'], payload['url'])
                        user.last_login_notified_date = today
                        db.session.commit()
                        current_app.logger.info('[Auth] Login notification sent to user %s via OTP verification', user.id)
                    except Exception as e:
                        current_app.logger.warning('[Auth] Failed to send login notification: %s', e)
            
            log_login_audit('verify_login_success', status='success', user=user, detail='Login OTP accepted and session established.')
            flash('Login successful!', 'success')
            return redirect(url_for('admin.dashboard' if user.is_admin else 'user.dashboard'))
        else:
            log_login_audit('verify_login_failed', status='warning', user=user, detail='Invalid login OTP entered.')
            flash('Invalid OTP code.', 'danger')
    
    return render_template('login_otp.html', form=form, email=email, remaining_seconds=remaining_seconds)


@verification_bp.route('/resend_login_otp/<email>')
def resend_login_otp(email):
    """Resend login OTP"""
    user = User.query.filter_by(email=email).first()
    if not user or not user.is_confirmed or not user.otp_sent_at:
        flash('Invalid request.', 'danger')
        log_login_audit('verify_login_resend_invalid', status='warning', email=email, detail='Resend login OTP requested with invalid state.')
        return redirect(url_for('auth.login'))
    
    # Check if 30 seconds have passed
    if datetime.utcnow() - user.otp_sent_at < timedelta(seconds=Config.OTP_EXPIRY_SECONDS):
        remaining = Config.OTP_EXPIRY_SECONDS - (datetime.utcnow() - user.otp_sent_at).seconds
        flash(f'Please wait {remaining} seconds before resending.', 'warning')
        log_login_audit('verify_login_resend_rate_limited', status='info', user=user, detail=f'Resend login OTP rate-limited ({remaining}s left).')
        return redirect(url_for('verification.verify_login_otp', email=email))
    
    # Resend OTP
    otp = generate_otp()
    user.otp = otp
    user.otp_sent_at = datetime.utcnow()
    db.session.commit()
    if send_otp_email(user.email, otp, "Login OTP for Diabeatit"):
        log_login_audit('verify_login_resend_sent', status='info', user=user, detail='Login OTP resent successfully.')
        flash('OTP resent to your email.', 'success')
    else:
        log_login_audit('verify_login_resend_failed', status='error', user=user, detail='Failed to resend login OTP.')
        flash('Failed to resend OTP.', 'danger')
    return redirect(url_for('verification.verify_login_otp', email=email))


@verification_bp.route('/verify_reset_password_otp', methods=['GET', 'POST'])
def verify_reset_password_otp():
    """Verify password reset OTP"""
    email = session.get('reset_email')
    if not email:
        flash('Session expired. Please start password recovery again.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash('Invalid request.', 'danger')
        log_login_audit('password_reset_verify_invalid', status='warning', email=email, detail='Password reset OTP verify requested for invalid account.')
        return redirect(url_for('auth.login'))
    
    otp_message = ''
    otp_message_type = ''
    expired = False
    
    if user.otp_sent_at and datetime.utcnow() - user.otp_sent_at > timedelta(seconds=Config.OTP_EXPIRY_SECONDS):
        user.otp = None
        user.otp_sent_at = None
        db.session.commit()
        log_login_audit('password_reset_verify_expired', status='warning', user=user, detail='Password reset OTP expired before verification.')
        expired = True

    remaining_seconds = max(0, Config.OTP_EXPIRY_SECONDS - (datetime.utcnow() - user.otp_sent_at).seconds) if user.otp_sent_at else 0
    
    form = ConfirmForm()
    if form.validate_on_submit() and not expired:
        if user.otp == form.otp.data:
            user.otp = None
            user.otp_sent_at = None
            db.session.commit()
            log_login_audit('password_reset_verify_success', status='success', user=user, detail='Password reset OTP verified successfully.')
            flash('OTP verified. Please enter your new password.', 'success')
            return redirect(url_for('verification.reset_password', email=email))
        else:
            log_login_audit('password_reset_verify_failed', status='warning', user=user, detail='Invalid password reset OTP entered.')
            otp_message = 'Invalid OTP code.'
            otp_message_type = 'danger'

    return render_template('reset_password_otp.html', form=form, remaining_seconds=remaining_seconds, 
                         otp_message=otp_message, otp_message_type=otp_message_type, expired=expired)


@verification_bp.route('/resend_reset_password_otp')
def resend_reset_password_otp():
    """Resend password reset OTP"""
    email = session.get('reset_email')
    if not email:
        flash('Session expired. Please start password recovery again.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash('Invalid request.', 'danger')
        log_login_audit('password_reset_resend_invalid', status='warning', email=email, detail='Resend reset OTP requested for invalid account.')
        return redirect(url_for('auth.forgot_password'))

    if user.otp_sent_at and datetime.utcnow() - user.otp_sent_at < timedelta(seconds=Config.OTP_EXPIRY_SECONDS):
        remaining = Config.OTP_EXPIRY_SECONDS - (datetime.utcnow() - user.otp_sent_at).seconds
        flash(f'Please wait {remaining} seconds before resending.', 'warning')
        log_login_audit('password_reset_resend_rate_limited', status='info', user=user, detail=f'Resend reset OTP rate-limited ({remaining}s left).')
        return redirect(url_for('verification.verify_reset_password_otp'))

    otp = generate_otp()
    user.otp = otp
    user.otp_sent_at = datetime.utcnow()
    db.session.commit()
    if send_otp_email(user.email, otp, "Reset Your Diabeatit Password"):
        log_login_audit('password_reset_resend_sent', status='info', user=user, detail='Password reset OTP resent successfully.')
        flash('Password reset OTP resent to your email.', 'success')
    else:
        log_login_audit('password_reset_resend_failed', status='error', user=user, detail='Failed to resend password reset OTP.')
        flash('Failed to resend OTP.', 'danger')
    return redirect(url_for('verification.verify_reset_password_otp'))


@verification_bp.route('/reset_password/<email>', methods=['GET', 'POST'])
def reset_password(email):
    """Reset user password"""
    user = User.query.filter_by(email=email).first()
    if not user:
        flash('Invalid request.', 'danger')
        log_login_audit('password_reset_invalid', status='warning', email=email, detail='Password reset requested for invalid account.')
        return redirect(url_for('auth.login'))
    
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.password = generate_password_hash(form.password.data)
        db.session.commit()
        log_login_audit('password_reset_success', status='success', user=user, detail='Password reset completed successfully.')
        flash('Password reset successfully! You can now log in.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('reset_password.html', form=form, email=email)
