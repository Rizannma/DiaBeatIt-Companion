import os
import pickle
import numpy as np
import logging
from datetime import datetime, timedelta
from flask import has_request_context, session
from sqlalchemy import func
from huggingface_hub import hf_hub_download
from models import db, User, PatientProfile, GlucoseEntry, ActivityEntry, SleepEntry, MealEntry
from push_service import send_high_glucose_alert

logger = logging.getLogger(__name__)
HF_HUB_REPO = os.environ.get('HF_HUB_REPO', 'YOUR_HF_USERNAME/YOUR_MODEL_REPO')

risk_model = None
glucose_model = None
scaler_class = None
scaler_reg = None


def _download_and_load_model(filename):
    repo_id = HF_HUB_REPO
    if not repo_id:
        raise RuntimeError('HF_HUB_REPO environment variable is not set')

    model_path = hf_hub_download(repo_id=repo_id, filename=filename)
    with open(model_path, 'rb') as f:
        return pickle.load(f)


# Load models and scalers once at startup
try:
    risk_model = _download_and_load_model('risk_model.pkl')
    glucose_model = _download_and_load_model('glucose_model.pkl')
    scaler_class = _download_and_load_model('scaler_class.pkl')
    scaler_reg = _download_and_load_model('scaler_reg.pkl')
    logger.info('Model artifacts loaded from Hugging Face Hub successfully.')
except Exception as e:
    logger.warning('Warning: Failed to load model artifacts from Hugging Face Hub. %s', e, exc_info=True)



def _align_feature_count(features, expected_count):
    """Pad or trim features to match the trained scaler/model input size."""
    if expected_count is None:
        return features

    if len(features) < expected_count:
        return features + [0.0] * (expected_count - len(features))

    return features[:expected_count]

def get_user_features(user_id):
    """Fetch and calculate 17/20 features for a specific user"""
    user = User.query.get(user_id)
    profile = user.patient_profile

    if not user or not profile:
        raise ValueError('User profile data is incomplete.')
    
    # 1. Categorical Encoding (Binary 0/1)
    gender_encoded = 1 if profile.gender == 'Male' else 0
    fam_hist = 1 if profile.family_history_diabetes == 'Yes' else 0
    cardio_hist = 1 if profile.cardiovascular_history == 'Yes' else 0
    hyper_hist = 1 if profile.hypertension_history == 'Yes' else 0
    
    # 2. BMI Calculation
    # Using stored BMI or calculating on the fly for robustness
    bmi = profile.bmi
    if not bmi and profile.height_cm and profile.weight_kg:
        height_m = profile.height_cm / 100
        bmi = profile.weight_kg / (height_m ** 2)

    # 3. Time Series Lags (3 most recent Fasting readings)
    lags = (
        GlucoseEntry.query.filter(
            GlucoseEntry.user_id == user_id,
            func.lower(GlucoseEntry.reading_type) == 'fasting'
        )
        .order_by(GlucoseEntry.date.desc(), GlucoseEntry.time.desc())
        .limit(3)
        .all()
    )

    fasting_lag1 = lags[0].glucose_level if len(lags) > 0 else 0
    fasting_lag2 = lags[1].glucose_level if len(lags) > 1 else 0
    fasting_lag3 = lags[2].glucose_level if len(lags) > 2 else 0

    # 4. 7-Day Rolling Averages
    seven_days_ago = datetime.utcnow().date() - timedelta(days=7)

    # Glucose Rolling Avg
    avg_glucose = (
        db.session.query(func.avg(GlucoseEntry.glucose_level))
        .filter(GlucoseEntry.user_id == user_id, GlucoseEntry.date >= seven_days_ago)
        .scalar() or 0
    )

    # Activity Sum (Minutes per week)
    sum_activity = (
        db.session.query(func.sum(ActivityEntry.duration_minutes))
        .filter(ActivityEntry.user_id == user_id, ActivityEntry.date >= seven_days_ago)
        .scalar() or 0
    )

    # Sleep Rolling Avg
    avg_sleep = (
        db.session.query(func.avg(SleepEntry.sleep_duration))
        .filter(SleepEntry.user_id == user_id, SleepEntry.date >= seven_days_ago)
        .scalar() or 0
    )

    # Meal Diet Score Rolling Avg
    avg_diet_score = (
        db.session.query(func.avg(MealEntry.diet_score))
        .filter(MealEntry.user_id == user_id, MealEntry.date >= seven_days_ago)
        .scalar() or 0
    )

    # 5. Vector Construction (Risk: 17 features)
    base_features = [
        user.age, gender_encoded, bmi or 0, profile.hba1c or 0, 
        profile.cholesterol_total or 0, profile.triglyceride or 0,
        profile.hip_circumference or 0, fam_hist, cardio_hist, hyper_hist,
        fasting_lag1, fasting_lag2, fasting_lag3,
        avg_glucose, sum_activity, avg_sleep, avg_diet_score
    ]
    
    # Match the scaler feature count used during training (e.g., 18 in some runs).
    risk_expected = getattr(scaler_class, 'n_features_in_', len(base_features))
    risk_features = _align_feature_count(base_features, risk_expected)
    
    # Construct Glucose Vector (20 features)
    # Adding recent meal data as extra context for the regression model
    recent_meal = MealEntry.query.filter_by(user_id=user_id).order_by(MealEntry.created_at.desc()).first()
    meal_context = [
        recent_meal.carbohydrates or 0 if recent_meal else 0,
        recent_meal.calories or 0 if recent_meal else 0,
        recent_meal.diet_score or 0 if recent_meal else 0
    ]
    glucose_features = base_features + meal_context
    glucose_expected = getattr(scaler_reg, 'n_features_in_', len(glucose_features))
    glucose_features = _align_feature_count(glucose_features, glucose_expected)
    
    return np.array(risk_features, dtype=float).reshape(1, -1), np.array(glucose_features, dtype=float).reshape(1, -1)

def predict_diabetes_metrics(user_id):
    """Execute the full flow: fetch -> calculate -> scale -> predict"""
    try:
        risk_raw, glucose_raw = get_user_features(user_id)
        
        # Scaling
        risk_scaled = scaler_class.transform(risk_raw)
        glucose_scaled = scaler_reg.transform(glucose_raw)
        
        # Prediction
        risk_prob = risk_model.predict_proba(risk_scaled)[0][1] # Probability of Class 1
        risk_label = "High Risk" if risk_prob > 0.5 else "Low Risk"
        
        future_glucose = glucose_model.predict(glucose_scaled)[0]

        result = {
            "risk_score": round(float(risk_prob * 100), 2),
            "risk_label": risk_label,
            "predicted_next_glucose": round(float(future_glucose), 2),
            "status": "success"
        }

        # Check for high glucose alert and send if threshold exceeded
        if result['predicted_next_glucose'] > 180:
            alert_key = f'high-glucose-alert:{user_id}:{datetime.utcnow().date().isoformat()}'
            should_send_alert = True
            
            # Only send alert once per day per user
            if has_request_context():
                should_send_alert = not session.get(alert_key)
            
            if should_send_alert:
                try:
                    send_count = send_high_glucose_alert(user_id, result['predicted_next_glucose'])
                    if send_count > 0:
                        logger.info('[Prediction] High glucose alert sent to user %s (predicted: %.1f mg/dL, subscriptions: %d)',
                                   user_id, result['predicted_next_glucose'], send_count)
                    else:
                        logger.warning('[Prediction] High glucose alert could not be sent to user %s - no active subscriptions', user_id)
                    
                    if has_request_context():
                        session[alert_key] = True
                except Exception as e:
                    logger.error('[Prediction] Error sending high glucose alert to user %s: %s', user_id, e, exc_info=True)
        
        return result
    except Exception as e:
        logger.error('[Prediction] Error in predict_diabetes_metrics for user %s: %s', user_id, e, exc_info=True)
        return {"status": "error", "message": str(e)}