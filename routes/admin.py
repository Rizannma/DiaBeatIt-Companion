"""Admin routes - Admin dashboard"""
print('IMPORTING: admin.py', flush=True)
from datetime import datetime
import math
import os

from flask import render_template, abort, request
from flask_login import login_required, current_user
from sqlalchemy import func, text

from models import db, User, PatientProfile, GlucoseEntry, MealEntry, ActivityEntry, SleepEntry, LoginAudit
from config import Config

from . import admin_bp


def _paginate_items(items, page, per_page):
    total_items = len(items)
    total_pages = max(1, math.ceil(total_items / per_page))
    current_page = max(1, min(page, total_pages))
    start_index = (current_page - 1) * per_page
    end_index = start_index + per_page
    page_items = items[start_index:end_index]

    return page_items, {
        'page': current_page,
        'per_page': per_page,
        'total_items': total_items,
        'total_pages': total_pages,
        'start_item': start_index + 1 if total_items else 0,
        'end_item': min(end_index, total_items),
        'has_prev': current_page > 1,
        'has_next': current_page < total_pages,
        'prev_page': current_page - 1,
        'next_page': current_page + 1,
    }


def _build_user_inventory(now):
    all_users = User.query.filter_by(role='user').order_by(User.id.desc()).all()
    all_users_data = []
    successful_predictions = 0
    predictable_users = 0
    high_risk_users = 0
    low_risk_users = 0

    for user in all_users:
        risk_label = 'Unavailable'
        risk_score = None
        risk_filter = 'unavailable'
        prediction_note = 'Profile incomplete'

        if user.profile_complete:
            predictable_users += 1
            from .prediction_service import predict_diabetes_metrics
            prediction = predict_diabetes_metrics(user.id)
            if prediction and prediction.get('status') == 'success':
                successful_predictions += 1
                risk_score = prediction.get('risk_score')
                risk_label = prediction.get('risk_label', 'Unavailable')
                prediction_note = 'Prediction generated'
                if risk_label == 'High Risk':
                    risk_filter = 'high'
                    high_risk_users += 1
                elif risk_label == 'Low Risk':
                    risk_filter = 'low'
                    low_risk_users += 1
            else:
                prediction_note = 'Prediction unavailable'

        all_users_data.append({
            'id': user.id,
            'name': user.subject_name,
            'email': user.email,
            'account_for': user.account_for.title() if user.account_for else 'User',
            'age': user.subject_age,
            'verification_status': 'Verified' if user.is_confirmed else 'Pending',
            'profile_status': 'Complete' if user.profile_complete else 'Incomplete',
            'lockout_active': bool(user.lockout_until and user.lockout_until > now),
            'risk_label': risk_label,
            'risk_score': risk_score,
            'risk_filter': risk_filter,
            'prediction_note': prediction_note,
            'login_attempts': user.login_attempts or 0,
            'lockout_until': user.lockout_until,
            'otp_sent_at': user.otp_sent_at,
            'confirmed_at': user.confirmed_at,
        })

    return {
        'all_users': all_users_data,
        'successful_predictions': successful_predictions,
        'predictable_users': predictable_users,
        'high_risk_users': high_risk_users,
        'low_risk_users': low_risk_users,
    }


def _build_system_health():
    database_status = {'status': 'Offline', 'detail': 'Database health check failed.'}
    try:
        db.session.execute(text('SELECT 1'))
        database_status = {'status': 'Online', 'detail': 'Database connection is healthy.'}
    except Exception as exc:
        database_status = {'status': 'Offline', 'detail': f'Database check error: {exc}'}

    required_artifacts = ['risk_model.pkl', 'glucose_model.pkl', 'scaler_class.pkl', 'scaler_reg.pkl']
    missing_artifacts = [path for path in required_artifacts if not os.path.exists(path)]
    model_runtime_status = {
        'status': 'Online' if not missing_artifacts else 'Degraded',
        'detail': 'All model artifacts are available.' if not missing_artifacts else f"Missing artifacts: {', '.join(missing_artifacts)}",
    }

    api_status = {
        'status': 'Online' if Config.BREVO_API_KEY else 'Degraded',
        'detail': 'Brevo API key configured.' if Config.BREVO_API_KEY else 'BREVO_API_KEY missing in environment.',
    }

    return [
        {'service': 'Database', **database_status},
        {'service': 'Email API', **api_status},
        {'service': 'Model Runtime', **model_runtime_status},
    ]


def _build_admin_dashboard_context(include_users=False):
    now = datetime.utcnow()

    user_inventory = _build_user_inventory(now)
    all_users_data = user_inventory['all_users']

    total_users = User.query.filter_by(role='user').count()
    confirmed_users = User.query.filter_by(role='user', is_confirmed=True).count()
    pending_verifications = max(total_users - confirmed_users, 0)
    profiles_complete = db.session.query(func.count(User.id)).join(PatientProfile).filter(
        User.role == 'user',
        PatientProfile.gender.isnot(None),
        PatientProfile.family_history_diabetes.isnot(None),
        PatientProfile.cardiovascular_history.isnot(None),
        PatientProfile.hypertension_history.isnot(None),
        PatientProfile.height_cm.isnot(None),
        PatientProfile.weight_kg.isnot(None),
    ).scalar() or 0
    profiles_pending = max(total_users - profiles_complete, 0)
    active_lockouts = User.query.filter(
        User.role == 'user',
        User.lockout_until.isnot(None),
        User.lockout_until > now,
    ).count()

    total_glucose = GlucoseEntry.query.count()
    total_meals = MealEntry.query.count()
    total_activity = ActivityEntry.query.count()
    total_sleep = SleepEntry.query.count()
    total_entries = total_glucose + total_meals + total_activity + total_sleep

    successful_predictions = user_inventory['successful_predictions']
    predictable_users = user_inventory['predictable_users']
    high_risk_users = user_inventory['high_risk_users']
    low_risk_users = user_inventory['low_risk_users']

    recent_users = User.query.filter_by(role='user').order_by(User.id.desc()).limit(6).all()
    recent_users_data = []
    for user in recent_users:
        recent_users_data.append({
            'name': user.subject_name,
            'email': user.email,
            'account_for': user.account_for.title() if user.account_for else 'User',
            'profile_status': 'Complete' if user.profile_complete else 'Incomplete',
            'verification_status': 'Verified' if user.is_confirmed else 'Pending',
            'lockout_active': bool(user.lockout_until and user.lockout_until > now),
            'age': user.subject_age,
        })

    recent_feed = []
    for entry in GlucoseEntry.query.order_by(GlucoseEntry.created_at.desc()).limit(4).all():
        recent_feed.append({
            'kind': 'Glucose',
            'user': entry.user.subject_name,
            'detail': f"{entry.reading_type.replace('_', ' ').title()} - {entry.glucose_level} mg/dL",
            'created_at': entry.created_at,
        })
    for entry in MealEntry.query.order_by(MealEntry.created_at.desc()).limit(4).all():
        recent_feed.append({
            'kind': 'Meal',
            'user': entry.user.subject_name,
            'detail': f"{entry.meal_type.replace('_', ' ').title()} - {entry.diet_score if entry.diet_score is not None else 'No score'}",
            'created_at': entry.created_at,
        })
    for entry in ActivityEntry.query.order_by(ActivityEntry.created_at.desc()).limit(4).all():
        recent_feed.append({
            'kind': 'Activity',
            'user': entry.user.subject_name,
            'detail': f"{entry.activity_type.replace('_', ' ').title()} - {entry.duration_minutes} min",
            'created_at': entry.created_at,
        })
    for entry in SleepEntry.query.order_by(SleepEntry.created_at.desc()).limit(4).all():
        recent_feed.append({
            'kind': 'Sleep',
            'user': entry.user.subject_name,
            'detail': f"{entry.sleep_quality.replace('_', ' ').title()} - {entry.sleep_duration} hrs",
            'created_at': entry.created_at,
        })

    recent_feed.sort(key=lambda item: item['created_at'], reverse=True)
    recent_feed = recent_feed[:8]

    profile_completion_rate = round((profiles_complete / total_users) * 100, 1) if total_users else 0
    avg_entries_per_user = round(total_entries / total_users, 1) if total_users else 0
    inference_success_rate = round((successful_predictions / predictable_users) * 100, 1) if predictable_users else 0

    security_controls = [
        {'label': 'Password hashing', 'status': 'Enabled', 'detail': 'Passwords are stored as hashes and never in plain text.'},
        {'label': 'OTP verification', 'status': 'Enabled', 'detail': 'Account, login, and reset verification use short-lived codes.'},
        {'label': 'Login lockouts', 'status': 'Enabled', 'detail': 'Repeated failed logins trigger timed lockout windows.'},
        {'label': 'Field encryption', 'status': 'Enabled', 'detail': 'Sensitive profile and note fields are encrypted at rest.'},
        {'label': 'CSRF protection', 'status': 'Enabled', 'detail': 'Flask-WTF forms include built-in CSRF tokens.'},
        {'label': 'Admin-only access', 'status': 'Enabled', 'detail': 'The admin dashboard rejects non-admin users.'},
    ]

    model_overview = {
        'how_it_predicts': [
            'Builds features from profile biomarkers plus recent glucose, meal, activity, and sleep logs.',
            'Scales the inputs with the saved preprocessing objects used during training.',
            'Runs a classifier for risk and a regressor for the next glucose estimate.',
        ],
        'how_it_is_trained': [
            'Historical app data was transformed into structured tabular features.',
            'A classification model was trained to estimate risk probability.',
            'A regression model was trained to estimate the next glucose value.',
            'Both models were serialized with joblib and loaded at runtime.',
        ],
        'models_used': [
            'risk_model.pkl - classifier',
            'glucose_model.pkl - regressor',
            'scaler_class.pkl - classification scaler',
            'scaler_reg.pkl - regression scaler',
        ],
    }

    system_health = _build_system_health()

    context = {
        'generated_at': now,
        'summary_cards': [
            {'label': 'Total Users', 'value': total_users, 'hint': 'Registered patient accounts'},
            {'label': 'Profiles Complete', 'value': profiles_complete, 'hint': f'{profile_completion_rate}% of users are ready for prediction'},
            {'label': 'Active Lockouts', 'value': active_lockouts, 'hint': 'Accounts locked after failed logins'},
            {'label': 'Total Logged Entries', 'value': total_entries, 'hint': f'{avg_entries_per_user} entries per user on average'},
        ],
        'account_health': {
            'confirmed_users': confirmed_users,
            'pending_verifications': pending_verifications,
            'profiles_pending': profiles_pending,
            'profile_completion_rate': profile_completion_rate,
        },
        'data_inventory': [
            {'label': 'Glucose entries', 'count': total_glucose},
            {'label': 'Meal entries', 'count': total_meals},
            {'label': 'Activity entries', 'count': total_activity},
            {'label': 'Sleep entries', 'count': total_sleep},
        ],
        'recent_users': recent_users_data,
        'recent_feed': recent_feed,
        'security_controls': security_controls,
        'model_overview': model_overview,
        'inference_success_rate': inference_success_rate,
        'risk_distribution': {'high': high_risk_users, 'low': low_risk_users},
        'system_health': system_health,
    }

    if include_users:
        context['all_users'] = all_users_data

    return context


@admin_bp.route('/dashboard')
@login_required
def dashboard():
    """Admin dashboard"""
    if not current_user.is_admin:
        abort(403)
    admin_data = _build_admin_dashboard_context(include_users=False)
    return render_template('admin_dashboard.html', user=current_user, admin_data=admin_data)


@admin_bp.route('/users')
@login_required
def users():
    """Admin user management page."""
    if not current_user.is_admin:
        abort(403)
    admin_data = _build_admin_dashboard_context(include_users=True)
    page = request.args.get('page', 1, type=int)
    paged_users, pagination = _paginate_items(admin_data['all_users'], page, 8)
    admin_data['all_users'] = paged_users
    admin_data['users_pagination'] = pagination
    return render_template('admin_users.html', user=current_user, admin_data=admin_data)


@admin_bp.route('/login-audit')
@login_required
def login_audit():
    """Admin login audit page with full available history."""
    if not current_user.is_admin:
        abort(403)

    admin_data = _build_admin_dashboard_context(include_users=False)
    page = request.args.get('page', 1, type=int)
    audits = LoginAudit.query.order_by(LoginAudit.created_at.desc()).all()
    audit_rows = [
        {
            'name': audit.user.subject_name if audit.user else 'Unknown user',
            'email': audit.email,
            'event': audit.event_type,
            'status': audit.status,
            'detail': audit.detail,
            'ip_address': audit.ip_address,
            'event_time': audit.created_at,
        }
        for audit in audits
    ]

    paged_audits, pagination = _paginate_items(audit_rows, page, 10)

    return render_template(
        'admin_login_audit.html',
        user=current_user,
        admin_data=admin_data,
        audit_rows=paged_audits,
        audit_pagination=pagination,
    )
