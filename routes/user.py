"""User routes - Dashboard and logout"""
import os
from datetime import datetime, timedelta
import math
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, logout_user, current_user
from sqlalchemy import func

from . import user_bp
from forms import ProfileForm
from models import db, User, GlucoseEntry, MealEntry, ActivityEntry, SleepEntry
from email_service import send_report_email


def _clamp(value, lower, upper):
    return max(lower, min(upper, value))


def _safe_round(value, ndigits=0):
    """Round numbers safely and return numeric values for display."""
    if value is None:
        return None
    try:
        rounded = round(float(value), ndigits)
        if ndigits == 0 and isinstance(rounded, float) and rounded.is_integer():
            return int(rounded)
        return rounded
    except (TypeError, ValueError):
        return value


def _pearson_correlation(x_vals, y_vals):
    if len(x_vals) < 2 or len(y_vals) < 2 or len(x_vals) != len(y_vals):
        return None

    mean_x = sum(x_vals) / len(x_vals)
    mean_y = sum(y_vals) / len(y_vals)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_vals, y_vals))
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in x_vals))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in y_vals))
    den = den_x * den_y
    if den == 0:
        return None
    return num / den


def _correlation_strength(corr):
    abs_corr = abs(corr)
    if abs_corr >= 0.7:
        return 'strong'
    if abs_corr >= 0.4:
        return 'moderate'
    if abs_corr >= 0.2:
        return 'weak'
    return 'very weak'


def _impact_label(impact):
    if impact >= 70:
        return 'High influence'
    if impact >= 35:
        return 'Moderate influence'
    return 'Low influence'


def _correlation_takeaway(label, corr):
    subject = label.split(' vs ')[0].lower()
    if corr > 0:
        return f"When {subject} goes up, glucose tends to go up too."
    return f"When {subject} goes up, glucose tends to go down."


def _risk_pressure(value, low, high, reverse=False):
    if value is None:
        return 0

    if reverse:
        if value >= high:
            return 0
        if value <= low:
            return 100
        return int(((high - value) / (high - low)) * 100)

    if value <= low:
        return 0
    if value >= high:
        return 100
    return int(((value - low) / (high - low)) * 100)


def _build_explainability(profile, weekly_metrics, recent_entries):
    factors = []

    glucose_pressure = _risk_pressure(weekly_metrics['avg_glucose'], 95, 180)
    factors.append({
        'factor': 'Recent glucose trend',
        'value': f"{_safe_round(weekly_metrics['avg_glucose'], 1)} mg/dL",
        'impact': glucose_pressure,
        'impact_label': _impact_label(glucose_pressure),
        'why': 'Higher rolling glucose raises projected diabetes risk and next-glucose estimate.'
    })

    hba1c_pressure = _risk_pressure(profile.hba1c, 5.7, 9.0)
    factors.append({
        'factor': 'HbA1c profile marker',
        'value': f"{_safe_round(profile.hba1c, 1)}%" if profile.hba1c is not None else 'Not provided',
        'impact': hba1c_pressure,
        'impact_label': _impact_label(hba1c_pressure),
        'why': 'HbA1c summarizes long-term glucose control and strongly affects baseline risk.'
    })

    activity_pressure = _risk_pressure(weekly_metrics['total_activity_minutes'], 60, 210, reverse=True)
    factors.append({
        'factor': 'Weekly activity level',
        'value': f"{int(weekly_metrics['total_activity_minutes'])} minutes",
        'impact': activity_pressure,
        'impact_label': _impact_label(activity_pressure),
        'why': 'More movement usually improves insulin sensitivity and lowers risk pressure.'
    })

    sleep_value = weekly_metrics['avg_sleep_hours']
    sleep_pressure = 0
    if sleep_value:
        sleep_pressure = int(_clamp(abs(sleep_value - 7.5) / 2.5, 0, 1) * 100)
    factors.append({
        'factor': 'Sleep regularity',
        'value': f"{_safe_round(sleep_value, 1)} hours" if sleep_value else 'Not enough data',
        'impact': sleep_pressure,
        'impact_label': _impact_label(sleep_pressure),
        'why': 'Very short or long sleep can destabilize glucose regulation.'
    })

    diet_value = weekly_metrics['avg_diet_score']
    diet_pressure = _risk_pressure(diet_value, 4, 8, reverse=True) if diet_value else 0
    factors.append({
        'factor': 'Diet quality score',
        'value': f"{_safe_round(diet_value, 1)} / 10" if diet_value else 'Not enough data',
        'impact': diet_pressure,
        'impact_label': _impact_label(diet_pressure),
        'why': 'Higher meal quality generally supports steadier post-meal glucose response.'
    })

    family_flag = 100 if profile.family_history_diabetes == 'Yes' else 0
    factors.append({
        'factor': 'Family history',
        'value': profile.family_history_diabetes or 'Not provided',
        'impact': family_flag,
        'impact_label': _impact_label(family_flag),
        'why': 'Family history raises baseline susceptibility even with good habits.'
    })

    ranked_factors = sorted(factors, key=lambda item: item['impact'], reverse=True)

    return {
        'factors': ranked_factors,
        'top_factors': ranked_factors[:4],
        'data_quality': {
            'glucose_entries': len(recent_entries['glucose']),
            'meal_entries': len(recent_entries['meals']),
            'activity_entries': len(recent_entries['activity']),
            'sleep_entries': len(recent_entries['sleep']),
        }
    }


def _entry_date_value(entry):
    value = entry.get('date') if isinstance(entry, dict) else getattr(entry, 'date', None)
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return datetime.strptime(value, '%Y-%m-%d').date()
    if hasattr(value, 'date') and callable(value.date):
        return value.date()
    return value


def _entry_time_value(entry):
    value = entry.get('time') if isinstance(entry, dict) else getattr(entry, 'time', None)
    if value is None:
        return datetime.min.time()
    if isinstance(value, str):
        try:
            return datetime.strptime(value, '%H:%M').time()
        except ValueError:
            try:
                return datetime.fromisoformat(value).time()
            except ValueError:
                return datetime.min.time()
    if hasattr(value, 'hour') and hasattr(value, 'minute'):
        return value
    return datetime.min.time()


def _entry_sort_value(entry):
    created_at = entry.get('created_at') if isinstance(entry, dict) else getattr(entry, 'created_at', None)
    return (
        _entry_date_value(entry) or datetime.min.date(),
        _entry_time_value(entry),
        created_at or datetime.min,
    )


def _entry_number(entry, field_name, default=0):
    value = entry.get(field_name) if isinstance(entry, dict) else getattr(entry, field_name, None)
    return default if value is None else value


def _build_model_context(user_id):
    """Build prediction and summary data for model result pages."""

    today = datetime.utcnow().date()
    seven_days_ago = today - timedelta(days=7)
    thirty_days_ago = today - timedelta(days=29)

    from .prediction_service import predict_diabetes_metrics

    raw_prediction = predict_diabetes_metrics(user_id)
    prediction_error = None
    predictions = None

    if raw_prediction and raw_prediction.get('status') == 'success':
        predictions = raw_prediction
    elif raw_prediction:
        prediction_error = raw_prediction.get('message', 'Unable to generate prediction right now.')

    weekly_metrics = {
        'avg_glucose': (
            db.session.query(func.avg(GlucoseEntry.glucose_level))
            .filter(GlucoseEntry.user_id == user_id, GlucoseEntry.date >= seven_days_ago)
            .scalar() or 0
        ),
        'total_activity_minutes': (
            db.session.query(func.sum(ActivityEntry.duration_minutes))
            .filter(ActivityEntry.user_id == user_id, ActivityEntry.date >= seven_days_ago)
            .scalar() or 0
        ),
        'avg_sleep_hours': (
            db.session.query(func.avg(SleepEntry.sleep_duration))
            .filter(SleepEntry.user_id == user_id, SleepEntry.date >= seven_days_ago)
            .scalar() or 0
        ),
        'avg_diet_score': (
            db.session.query(func.avg(MealEntry.diet_score))
            .filter(MealEntry.user_id == user_id, MealEntry.date >= seven_days_ago)
            .scalar() or 0
        )
    }

    previous_week_start = today - timedelta(days=14)
    previous_week_end = today - timedelta(days=8)
    previous_week_avg_glucose = (
        db.session.query(func.avg(GlucoseEntry.glucose_level))
        .filter(
            GlucoseEntry.user_id == user_id,
            GlucoseEntry.date >= previous_week_start,
            GlucoseEntry.date <= previous_week_end
        )
        .scalar() or 0
    )

    recent_entries = {
        'glucose': (
            GlucoseEntry.query.filter_by(user_id=user_id)
            .order_by(GlucoseEntry.date.desc(), GlucoseEntry.time.desc())
            .limit(120).all()
        ),
        'meals': (
            MealEntry.query.filter_by(user_id=user_id)
            .order_by(MealEntry.date.desc(), MealEntry.time.desc())
            .limit(120).all()
        ),
        'activity': (
            ActivityEntry.query.filter_by(user_id=user_id)
            .order_by(ActivityEntry.date.desc())
            .limit(120).all()
        ),
        'sleep': (
            SleepEntry.query.filter_by(user_id=user_id)
            .order_by(SleepEntry.date.desc())
            .limit(120).all()
        ),
    }

    glucose_30 = GlucoseEntry.query.filter(
        GlucoseEntry.user_id == user_id,
        GlucoseEntry.date >= thirty_days_ago
    ).order_by(GlucoseEntry.date.asc(), GlucoseEntry.time.asc()).all()
    meals_30 = MealEntry.query.filter(
        MealEntry.user_id == user_id,
        MealEntry.date >= thirty_days_ago
    ).order_by(MealEntry.date.asc(), MealEntry.time.asc()).all()
    activity_30 = ActivityEntry.query.filter(
        ActivityEntry.user_id == user_id,
        ActivityEntry.date >= thirty_days_ago
    ).order_by(ActivityEntry.date.asc()).all()
    sleep_30 = SleepEntry.query.filter(
        SleepEntry.user_id == user_id,
        SleepEntry.date >= thirty_days_ago
    ).order_by(SleepEntry.date.asc()).all()

    day_keys = [(thirty_days_ago + timedelta(days=offset)).isoformat() for offset in range(30)]
    daily_rollup = {
        key: {
            'glucose': [],
            'activity': 0,
            'sleep': [],
            'diet': []
        } for key in day_keys
    }

    for entry in glucose_30:
        daily_rollup[entry.date.isoformat()]['glucose'].append(float(entry.glucose_level))
    for entry in activity_30:
        daily_rollup[entry.date.isoformat()]['activity'] += int(entry.duration_minutes)
    for entry in sleep_30:
        daily_rollup[entry.date.isoformat()]['sleep'].append(float(entry.sleep_duration))
    for entry in meals_30:
        if entry.diet_score is not None:
            daily_rollup[entry.date.isoformat()]['diet'].append(float(entry.diet_score))

    chart_labels = [datetime.fromisoformat(key).strftime('%b %d') for key in day_keys]
    glucose_series = []
    sleep_series = []
    activity_series = []
    diet_series = []

    corr_glucose = []
    corr_activity = []
    corr_sleep = []
    corr_diet = []

    for key in day_keys:
        day = daily_rollup[key]
        avg_glucose = sum(day['glucose']) / len(day['glucose']) if day['glucose'] else None
        avg_sleep = sum(day['sleep']) / len(day['sleep']) if day['sleep'] else None
        avg_diet = sum(day['diet']) / len(day['diet']) if day['diet'] else None

        glucose_series.append(_safe_round(avg_glucose, 1) if avg_glucose is not None else None)
        sleep_series.append(_safe_round(avg_sleep, 1) if avg_sleep is not None else None)
        activity_series.append(day['activity'])
        diet_series.append(_safe_round(avg_diet, 1) if avg_diet is not None else None)

        if avg_glucose is not None:
            corr_glucose.append(avg_glucose)
            corr_activity.append(day['activity'])
            corr_sleep.append(avg_sleep if avg_sleep is not None else 0)
            corr_diet.append(avg_diet if avg_diet is not None else 0)

    corr_activity_value = _pearson_correlation(corr_glucose, corr_activity)
    corr_sleep_value = _pearson_correlation(corr_glucose, corr_sleep)
    corr_diet_value = _pearson_correlation(corr_glucose, corr_diet)

    correlation_insights = []
    correlations = [
        ('Activity vs Glucose', corr_activity_value),
        ('Sleep vs Glucose', corr_sleep_value),
        ('Diet Score vs Glucose', corr_diet_value)
    ]
    for label, corr in correlations:
        if corr is None:
            correlation_insights.append({
                'label': label,
                'coefficient': None,
                'insight': 'Not enough aligned data points yet.',
                'plain_text': 'Add more days with both habits and glucose logs to make this pattern easier to read.'
            })
            continue

        direction = 'positive' if corr > 0 else 'negative'
        strength = _correlation_strength(corr)
        correlation_insights.append({
            'label': label,
            'coefficient': _safe_round(corr, 2),
            'insight': f"{strength.title()} {direction} relationship in the last 30 days.",
            'plain_text': _correlation_takeaway(label, corr)
        })

    user = db.session.get(User, user_id)
    profile = user.patient_profile if user else None
    explainability = _build_explainability(profile, weekly_metrics, recent_entries)

    predicted_base = predictions['predicted_next_glucose'] if predictions else (glucose_series[-1] if glucose_series[-1] is not None else 0)
    last_valid_glucose = [value for value in glucose_series if value is not None]
    slope = 0
    if len(last_valid_glucose) >= 2:
        slope = _clamp((last_valid_glucose[-1] - last_valid_glucose[0]) / (len(last_valid_glucose) - 1), -12, 12)

    trend_labels = [(today + timedelta(days=offset)).strftime('%b %d') for offset in range(1, 8)]
    predicted_trend = [_safe_round(predicted_base + slope * step, 1) for step in range(7)]

    month_start = today.replace(day=1)
    monthly_counts = {
        'glucose': GlucoseEntry.query.filter(GlucoseEntry.user_id == user_id, GlucoseEntry.date >= month_start).count(),
        'meals': MealEntry.query.filter(MealEntry.user_id == user_id, MealEntry.date >= month_start).count(),
        'activity': ActivityEntry.query.filter(ActivityEntry.user_id == user_id, ActivityEntry.date >= month_start).count(),
        'sleep': SleepEntry.query.filter(SleepEntry.user_id == user_id, SleepEntry.date >= month_start).count(),
    }

    active_days = len({entry.date.isoformat() for entry in glucose_30} | {entry.date.isoformat() for entry in meals_30} |
                      {entry.date.isoformat() for entry in activity_30} | {entry.date.isoformat() for entry in sleep_30})

    weekly_summary = {
        'avg_glucose': _safe_round(weekly_metrics['avg_glucose'], 1),
        'glucose_change_vs_last_week': _safe_round(weekly_metrics['avg_glucose'] - previous_week_avg_glucose, 1),
        'activity_minutes': int(weekly_metrics['total_activity_minutes']),
        'avg_sleep_hours': _safe_round(weekly_metrics['avg_sleep_hours'], 1),
        'avg_diet_score': _safe_round(weekly_metrics['avg_diet_score'], 1),
    }

    monthly_summary = {
        'month_label': today.strftime('%B %Y'),
        'entry_counts': monthly_counts,
        'active_days': active_days,
        'avg_glucose_30d': _safe_round(sum(last_valid_glucose) / len(last_valid_glucose), 1) if last_valid_glucose else 0,
        'avg_activity_30d': _safe_round(sum(activity_series) / len(activity_series), 1) if activity_series else 0,
        'avg_sleep_30d': _safe_round(sum(v for v in sleep_series if v is not None) / len([v for v in sleep_series if v is not None]), 1) if any(v is not None for v in sleep_series) else 0,
    }

    model_guide = {
        'how_it_predicts': [
            'Builds a feature vector from profile biomarkers and recent logs (glucose, meals, activity, sleep).',
            'Applies the same saved scalers used during training to keep feature scale consistent.',
            'Runs a classification model for risk score and a regression model for next glucose estimate.'
        ],
        'how_to_improve_accuracy': [
            'Log fasting glucose consistently for at least 7 to 14 days.',
            'Avoid skipping meal, activity, and sleep entries in the same week.',
            'Update profile biomarkers when new lab results are available.',
            'Prefer realistic values over estimated guesses for all tracked fields.'
        ],
        'app_instructions': [
            'Complete Profile first so model inputs are unlocked.',
            'Use Track daily and submit glucose, meal, activity, and sleep entries.',
            'Review Dashboard for quick model status and top factors.',
            'Use Analytics for trends, summaries, and relationship insights.'
        ]
    }

    logging_days = set()
    for entry_date, in db.session.query(GlucoseEntry.date).filter(GlucoseEntry.user_id == user_id):
        logging_days.add(entry_date)
    for entry_date, in db.session.query(MealEntry.date).filter(MealEntry.user_id == user_id):
        logging_days.add(entry_date)
    for entry_date, in db.session.query(ActivityEntry.date).filter(ActivityEntry.user_id == user_id):
        logging_days.add(entry_date)
    for entry_date, in db.session.query(SleepEntry.date).filter(SleepEntry.user_id == user_id):
        logging_days.add(entry_date)

    current_streak = 0
    probe_date = today
    while probe_date in logging_days:
        current_streak += 1
        probe_date -= timedelta(days=1)

    best_streak = 0
    streak_run = 0
    previous_date = None
    for log_date in sorted(logging_days):
        if previous_date and log_date == previous_date + timedelta(days=1):
            streak_run += 1
        else:
            streak_run = 1
        best_streak = max(best_streak, streak_run)
        previous_date = log_date

    active_days_total = len(logging_days)
    if current_streak <= 0:
        tier_slug = 'died'
        tier_label = 'Streak reset'
        tier_color = 'gray'
    elif current_streak >= 90:
        tier_slug = 'three-month'
        tier_label = '3-Month Fire'
        tier_color = 'gold'
    elif current_streak >= 30:
        tier_slug = 'one-month'
        tier_label = '1-Month Flame'
        tier_color = 'rose'
    else:
        tier_slug = 'starter'
        tier_label = 'Starter Ember'
        tier_color = 'orange'

    if current_streak <= 0:
        next_milestone = 1
    elif current_streak < 30:
        next_milestone = 30
    elif current_streak < 90:
        next_milestone = 90
    else:
        next_milestone = 180

    gamification = {
        'current_streak': current_streak,
        'best_streak': best_streak if best_streak else current_streak,
        'total_active_days': active_days_total,
        'next_milestone': next_milestone,
        'tier_slug': tier_slug,
        'tier_label': tier_label,
        'tier_color': tier_color,
    }

    return {
        'predictions': predictions,
        'prediction_error': prediction_error,
        'weekly_metrics': weekly_metrics,
        'recent_entries': recent_entries,
        'explainability': explainability,
        'chart_data': {
            'labels_30d': chart_labels,
            'glucose_30d': glucose_series,
            'activity_30d': activity_series,
            'sleep_30d': sleep_series,
            'diet_30d': diet_series,
            'predicted_labels_7d': trend_labels,
            'predicted_glucose_7d': predicted_trend,
        },
        'correlation_insights': correlation_insights,
        'weekly_summary': weekly_summary,
        'monthly_summary': monthly_summary,
        'model_guide': model_guide,
        'gamification': gamification,
        'generated_at': datetime.utcnow(),
    }


def _build_recommendations(model_data):
    """Build simple personalized recommendations from current metrics."""
    if not model_data or model_data.get('prediction_error') or not model_data.get('predictions'):
        return []

    recs = []
    risk_score = model_data['predictions']['risk_score']
    weekly = model_data['weekly_summary']
    factors = model_data['explainability']['factors']
    top_factor = factors[0] if factors else None

    if risk_score >= 70:
        recs.append({
            'title': 'Risk reduction priority',
            'category': 'Glucose Control',
            'priority': 'High',
            'summary': 'Your current risk score is high. WHO guidance supports regular activity, healthier meals, and reducing free sugars to lower risk.',
            'actions': [
                'Aim for at least 150 minutes of moderate-intensity activity each week.',
                'Reduce high-sugar snacks and sweetened drinks.',
                'If fasting glucose stays at or above 126 mg/dL on repeat testing, discuss it with your clinician.'
            ]
        })
    elif risk_score >= 40:
        recs.append({
            'title': 'Moderate risk optimization',
            'category': 'Prevention',
            'priority': 'Medium',
            'summary': 'Your risk is moderate. WHO-aligned prevention guidance says small routine changes can help keep glucose steadier.',
            'actions': [
                'Keep glucose and meal logs complete this week.',
                'Target at least 150 activity minutes weekly.',
                'Maintain consistent sleep schedule.'
            ]
        })
    else:
        recs.append({
            'title': 'Maintain low risk trajectory',
            'category': 'Maintenance',
            'priority': 'Low',
            'summary': 'Your risk appears low. Continue the healthy routines that support stable glucose and routine screening.',
            'actions': [
                'Keep logging key habits to preserve model accuracy.',
                'Continue balanced meals and regular activity.',
                'Recheck profile labs when new results are available.'
            ]
        })

    if weekly['activity_minutes'] < 150:
        recs.append({
            'title': 'Increase activity volume',
            'category': 'Exercise',
            'priority': 'High' if weekly['activity_minutes'] < 90 else 'Medium',
            'summary': f"You logged {weekly['activity_minutes']} active minutes this week. WHO recommends at least 150 minutes of moderate-intensity activity weekly for adults.",
            'actions': [
                'Add a 20 to 30 minute brisk walk 5 days this week.',
                'Break long sitting periods every 60 minutes.',
                'Include 2 light resistance sessions weekly.'
            ]
        })

    if weekly['avg_sleep_hours'] < 6.5 or weekly['avg_sleep_hours'] > 8.5:
        recs.append({
            'title': 'Stabilize sleep window',
            'category': 'Sleep',
            'priority': 'Medium',
            'summary': f"Average sleep is {weekly['avg_sleep_hours']} hours; target 7 to 8 hours.",
            'actions': [
                'Use a fixed bedtime and wake time daily.',
                'Avoid heavy meals and caffeine late at night.',
                'Track sleep quality every morning in Track.'
            ]
        })

    if weekly['avg_diet_score'] and weekly['avg_diet_score'] < 6:
        recs.append({
            'title': 'Improve meal quality',
            'category': 'Diet',
            'priority': 'Medium',
            'summary': f"Average meal score is {weekly['avg_diet_score']}/10.",
            'actions': [
                'Prioritize high-fiber carbs and lean protein.',
                'Reduce refined carbs in evening meals.',
                'Log meals consistently to track food-impact patterns.'
            ]
        })

    if top_factor:
        recs.append({
            'title': 'Focus factor for this week',
            'category': 'Explainability Insight',
            'priority': 'Info',
            'summary': f"Top contributing factor: {top_factor['factor']} ({top_factor['impact']}% impact).",
            'actions': [
                top_factor['why'],
                'Prioritize actions that reduce this factor first for faster improvement.'
            ]
        })

    return recs[:6]


def _build_report_email_payload(user, model_data):
    """Generate subject and body for doctor-facing report email."""
    if not model_data or model_data.get('prediction_error') or not model_data.get('predictions'):
        return None, None

    subject = f"DiaBeatIt report for {user.subject_name} - {model_data['generated_at'].strftime('%Y-%m-%d')}"
    body = (
        f"Patient: {user.subject_name}\n"
        f"Generated: {model_data['generated_at'].strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"Risk Classification: {model_data['predictions']['risk_label']} ({model_data['predictions']['risk_score']}%)\n"
        f"Predicted Next Glucose: {model_data['predictions']['predicted_next_glucose']} mg/dL\n"
        f"7-Day Avg Glucose: {model_data['weekly_summary']['avg_glucose']} mg/dL\n"
        f"7-Day Activity: {model_data['weekly_summary']['activity_minutes']} minutes\n"
        f"7-Day Avg Sleep: {model_data['weekly_summary']['avg_sleep_hours']} hours\n"
        f"7-Day Avg Diet Score: {model_data['weekly_summary']['avg_diet_score']}/10\n"
    )
    return subject, body


@user_bp.route('/dashboard')
@login_required
def dashboard():
    """User dashboard"""
    if current_user.is_admin:
        return redirect(url_for('admin.dashboard'))

    profile_needed = not current_user.profile_complete

    model_data = _build_model_context(current_user.id) if not profile_needed else None
    notification_context = {}
    if model_data and model_data.get('predictions'):
        notification_context = {
            'risk_score': model_data['predictions'].get('risk_score'),
            'risk_label': model_data['predictions'].get('risk_label'),
            'top_factors': [factor['factor'] for factor in model_data['explainability']['top_factors'][:3]],
            'recommendation_count': len(_build_recommendations(model_data)),
        }

    return render_template(
        'dashboard.html',
        user=current_user,
        profile_needed=profile_needed,
        model_data=model_data,
        notification_context=notification_context,
    )


@user_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """User profile page for additional prediction data"""
    if current_user.is_admin:
        return redirect(url_for('admin.dashboard'))

    # Get or create patient profile
    if not current_user.patient_profile:
        from models import PatientProfile
        current_user.patient_profile = PatientProfile(user_id=current_user.id)

    form = ProfileForm(obj=current_user.patient_profile)

    if form.validate_on_submit():
        # Update profile
        current_user.patient_profile.gender = form.gender.data
        current_user.patient_profile.family_history_diabetes = form.family_history_diabetes.data
        current_user.patient_profile.cardiovascular_history = form.cardiovascular_history.data
        current_user.patient_profile.hypertension_history = form.hypertension_history.data
        current_user.patient_profile.height_cm = form.height_cm.data
        current_user.patient_profile.weight_kg = form.weight_kg.data
        current_user.patient_profile.hip_circumference = form.hip_circumference.data
        
        # Calculate and save BMI
        if form.height_cm.data and form.weight_kg.data:
            height_m = form.height_cm.data / 100
            current_user.patient_profile.bmi = round(form.weight_kg.data / (height_m ** 2), 2)

        current_user.patient_profile.hba1c = form.hba1c.data
        current_user.patient_profile.cholesterol_total = form.cholesterol_total.data
        current_user.patient_profile.triglyceride = form.triglyceride.data
        db.session.commit()
        
        # Check if it's an AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            # Return the updated form for AJAX requests (no redirect)
            return render_template('profile.html', user=current_user, form=form)
        else:
            # Traditional form submission - redirect to dashboard
            flash('User profile updated successfully.', 'success')
            return redirect(url_for('user.dashboard'))

    return render_template('profile.html', user=current_user, form=form)


@user_bp.route('/track', methods=['GET', 'POST'])
@login_required
def track():
    """Track glucose, meal, activity, and sleep entries"""
    if current_user.is_admin:
        return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        entry_type = request.form.get('entry_type')

        if entry_type == 'glucose':
            glucose_date = request.form.get('glucose_date')
            glucose_time = request.form.get('glucose_time')
            glucose_level = request.form.get('glucose_level')
            reading_type = request.form.get('reading_type')

            if not all([glucose_date, glucose_time, glucose_level, reading_type]):
                flash('Please complete the required glucose fields.', 'danger')
                return render_template('track.html', user=current_user)

            entry = GlucoseEntry(
                user_id=current_user.id,
                date=datetime.strptime(glucose_date, '%Y-%m-%d').date(),
                time=datetime.strptime(glucose_time, '%H:%M').time(),
                glucose_level=float(glucose_level),
                reading_type=reading_type,
                notes=request.form.get('glucose_notes') or None
            )
            db.session.add(entry)

        elif entry_type == 'meal':
            meal_date = request.form.get('meal_date')
            meal_time = request.form.get('meal_time')
            meal_type = request.form.get('meal_type')
            diet_score = request.form.get('diet_score')
            food_items = request.form.get('food_items')

            if not all([meal_date, meal_time, meal_type, food_items]):
                flash('Please complete the required meal fields.', 'danger')
                return render_template('track.html', user=current_user)

            entry = MealEntry(
                user_id=current_user.id,
                date=datetime.strptime(meal_date, '%Y-%m-%d').date(),
                time=datetime.strptime(meal_time, '%H:%M').time(),
                meal_type=meal_type,
                food_items=food_items,
                diet_score=int(diet_score) if diet_score else None,
                carbohydrates=float(request.form.get('carbohydrates')) if request.form.get('carbohydrates') else None,
                calories=float(request.form.get('calories')) if request.form.get('calories') else None,
                notes=request.form.get('meal_notes') or None
            )
            db.session.add(entry)

        elif entry_type == 'activity':
            activity_date = request.form.get('activity_date')
            activity_type = request.form.get('activity_type')
            duration = request.form.get('duration')
            bp_systolic_raw = (request.form.get('bp_systolic') or '').strip()
            alcohol_consumption = (request.form.get('alcohol_consumption') or '').strip()
            screen_time_raw = (request.form.get('screen_time') or '').strip()

            if not all([activity_date, activity_type, duration, bp_systolic_raw, alcohol_consumption, screen_time_raw]):
                flash('Please complete the required activity fields.', 'danger')
                return render_template('track.html', user=current_user)

            try:
                duration_minutes = int(duration)
                bp_systolic = int(bp_systolic_raw)
                screen_time_minutes = int(screen_time_raw)
            except ValueError:
                flash('Please enter valid numeric values for duration, blood pressure, and screen time.', 'danger')
                return render_template('track.html', user=current_user)

            if duration_minutes <= 0 or bp_systolic < 50 or bp_systolic > 300 or screen_time_minutes < 0 or screen_time_minutes > 1440:
                flash('Please enter valid values for activity duration, blood pressure, and screen time.', 'danger')
                return render_template('track.html', user=current_user)

            entry = ActivityEntry(
                user_id=current_user.id,
                date=datetime.strptime(activity_date, '%Y-%m-%d').date(),
                activity_type=activity_type,
                duration_minutes=duration_minutes,
                bp_systolic=bp_systolic,
                alcohol_consumption=alcohol_consumption,
                screen_time_minutes=screen_time_minutes,
                notes=request.form.get('activity_notes') or None
            )
            db.session.add(entry)

        elif entry_type == 'sleep':
            sleep_date = request.form.get('sleep_date')
            sleep_duration = request.form.get('sleep_duration')
            sleep_quality = request.form.get('sleep_quality')

            if not all([sleep_date, sleep_duration, sleep_quality]):
                flash('Please complete the required sleep fields.', 'danger')
                return render_template('track.html', user=current_user)

            entry = SleepEntry(
                user_id=current_user.id,
                date=datetime.strptime(sleep_date, '%Y-%m-%d').date(),
                sleep_duration=float(sleep_duration),
                sleep_quality=sleep_quality,
                notes=request.form.get('sleep_notes') or None
            )
            db.session.add(entry)

        else:
            flash('Unsupported entry type. Please select a valid tab and try again.', 'danger')
            return render_template('track.html', user=current_user)

        db.session.commit()
        flash('Your tracking entry has been saved successfully.', 'success')
        return redirect(url_for('user.track'))

    return render_template('track.html', user=current_user)


@user_bp.route('/analytics')
@login_required
def analytics():
    """Analytics page"""
    if current_user.is_admin:
        return redirect(url_for('admin.dashboard'))

    profile_needed = not current_user.profile_complete
    model_data = _build_model_context(current_user.id) if not profile_needed else None
    return render_template('analytics.html', user=current_user, profile_needed=profile_needed, model_data=model_data)


@user_bp.route('/recommendations')
@login_required
def recommendations():
    """Recommendations page"""
    if current_user.is_admin:
        return redirect(url_for('admin.dashboard'))

    profile_needed = not current_user.profile_complete
    model_data = _build_model_context(current_user.id) if not profile_needed else None
    recommendations_data = _build_recommendations(model_data) if model_data else []
    return render_template(
        'recommendations.html',
        user=current_user,
        profile_needed=profile_needed,
        model_data=model_data,
        recommendations_data=recommendations_data,
        recommendation_source_note='These are rule-based suggestions that combine WHO-aligned prevention guidance with your tracked habits. They are educational, not a diagnosis.'
    )


@user_bp.route('/reports')
@login_required
def reports():
    """Reports page"""
    if current_user.is_admin:
        return redirect(url_for('admin.dashboard'))

    profile_needed = not current_user.profile_complete
    model_data = _build_model_context(current_user.id) if not profile_needed else None
    return render_template('reports.html', user=current_user, profile_needed=profile_needed, model_data=model_data)


@user_bp.route('/reports/share', methods=['POST'])
@login_required
def share_report_email():
    """Share report with a doctor by email."""
    if current_user.is_admin:
        return redirect(url_for('admin.dashboard'))

    if not current_user.profile_complete:
        flash('Complete your profile before sharing reports.', 'danger')
        return redirect(url_for('user.reports'))

    doctor_email = (request.form.get('doctor_email') or '').strip()
    custom_note = (request.form.get('doctor_note') or '').strip()
    if not doctor_email:
        flash('Doctor email is required.', 'danger')
        return redirect(url_for('user.reports'))

    model_data = _build_model_context(current_user.id)
    subject, body = _build_report_email_payload(current_user, model_data)
    if not subject:
        flash('Unable to prepare report email right now.', 'danger')
        return redirect(url_for('user.reports'))

    html_body = body.replace('\n', '<br>')
    if custom_note:
        html_body += f"<br><br><strong>Patient note:</strong><br>{custom_note}"

    sent = send_report_email(doctor_email, subject, html_body)
    if sent:
        flash('Report shared with doctor successfully.', 'success')
    else:
        flash('Failed to send report email. Please verify email settings and try again.', 'danger')

    return redirect(url_for('user.reports'))


@user_bp.route('/history')
@login_required
def history():
    """History page"""
    if current_user.is_admin:
        return redirect(url_for('admin.dashboard'))

    profile_needed = not current_user.profile_complete
    model_data = _build_model_context(current_user.id) if not profile_needed else None
    return render_template('history.html', user=current_user, profile_needed=profile_needed, model_data=model_data)


@user_bp.route('/logout')
@login_required
def logout():
    """Logout user"""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))
