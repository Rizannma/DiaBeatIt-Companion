"""Web Push notification helpers."""
from __future__ import annotations

import json
import hashlib
import logging
from datetime import datetime, timedelta

from sqlalchemy import func
from pywebpush import WebPushException, webpush

from config import Config
from models import db, User, GlucoseEntry, MealEntry, ActivityEntry, SleepEntry, PushSubscription

logger = logging.getLogger(__name__)


def _push_enabled():
    return bool(Config.PUSH_VAPID_PUBLIC_KEY and Config.PUSH_VAPID_PRIVATE_KEY)


def build_notification_payload(notification_type, **context):
    if notification_type == 'daily-log-reminder':
        return {
            'title': 'DiaBeatIt Daily Check-In',
            'body': "Log today's glucose, meals, activity, and sleep.",
            'tag': 'daily-log-reminder',
            'url': '/track',
        }

    if notification_type == 'weekly-summary':
        avg_glucose = context.get('avg_glucose')
        activity_minutes = context.get('activity_minutes')
        sleep_hours = context.get('sleep_hours')
        parts = []
        if avg_glucose is not None:
            parts.append(f'avg glucose {round(float(avg_glucose), 1)} mg/dL')
        if activity_minutes is not None:
            parts.append(f'{int(activity_minutes)} activity minutes')
        if sleep_hours is not None:
            parts.append(f'{round(float(sleep_hours), 1)} sleep hours')
        body = 'Weekly snapshot: ' + ', '.join(parts) if parts else 'Your weekly summary is ready.'
        return {
            'title': 'Weekly Summary',
            'body': body,
            'tag': 'weekly-summary',
            'url': '/analytics',
        }

    if notification_type == 'profile-refresh-reminder':
        return {
            'title': 'Profile Refresh Reminder',
            'body': 'Update your profile and lab values so your insights stay accurate.',
            'tag': 'profile-refresh-reminder',
            'url': '/profile',
        }

    if notification_type == 'high-glucose-alert':
        predicted_glucose = context.get('predicted_glucose')
        body = 'Your predicted glucose is above the target range.'
        if predicted_glucose is not None:
            body = f'Your predicted glucose is {round(float(predicted_glucose), 1)} mg/dL. Review your latest logs.'
        return {
            'title': 'High Glucose Alert',
            'body': body,
            'tag': 'high-glucose-alert',
            'url': '/dashboard',
        }

    if notification_type == 'login-success':
        return {
            'title': 'Welcome back',
            'body': 'Your daily insights are ready.',
            'tag': 'login-success',
            'url': '/dashboard',
        }

    if notification_type == 'account-locked':
        lockout_minutes = context.get('lockout_minutes', 30)
        return {
            'title': 'Account Locked',
            'body': f'Too many login attempts. Your account is locked for {lockout_minutes} minutes.',
            'tag': 'account-locked',
            'url': '/login',
        }

    if notification_type == 'account-unlocked':
        return {
            'title': 'Account Unlocked',
            'body': 'You can now log in again.',
            'tag': 'account-unlocked',
            'url': '/login',
        }

    raise ValueError(f'Unsupported notification type: {notification_type}')


def _iter_user_subscriptions(user_id):
    return PushSubscription.query.filter_by(user_id=user_id, active=True).all()


def _subscription_hash(endpoint):
    return hashlib.sha256(endpoint.encode('utf-8')).hexdigest()


def subscribe_user(subscription_data, user, user_agent=None):
    endpoint = subscription_data.get('endpoint')
    keys = subscription_data.get('keys') or {}
    p256dh = keys.get('p256dh')
    auth = keys.get('auth')

    if not endpoint or not p256dh or not auth:
        raise ValueError('A valid push subscription is required.')

    expiration_time = subscription_data.get('expirationTime')
    if expiration_time:
        try:
            expiration_time = datetime.utcfromtimestamp(float(expiration_time) / 1000.0)
        except (TypeError, ValueError, OSError):
            expiration_time = None

    existing = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if existing:
        existing.user_id = user.id
        existing.endpoint_hash = _subscription_hash(endpoint)
        existing.p256dh = p256dh
        existing.auth = auth
        existing.expiration_time = expiration_time
        existing.user_agent = user_agent
        existing.active = True
    else:
        db.session.add(PushSubscription(
            endpoint_hash=_subscription_hash(endpoint),
            user_id=user.id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            expiration_time=expiration_time,
            user_agent=user_agent,
            active=True,
        ))

    db.session.commit()


def unsubscribe_user(user, endpoint):
    if not endpoint:
        return False

    subscription = PushSubscription.query.filter_by(user_id=user.id, endpoint=endpoint, active=True).first()
    if not subscription:
        return False

    subscription.active = False
    db.session.commit()
    return True


def send_web_push_to_subscription(subscription, payload):
    if not _push_enabled():
        logger.warning('[Push] Web Push is disabled - VAPID keys are missing. Unable to send notification.')
        return False

    subscription_info = {
        'endpoint': subscription.endpoint,
        'keys': {
            'p256dh': subscription.p256dh,
            'auth': subscription.auth,
        }
    }

    if subscription.expiration_time:
        subscription_info['expirationTime'] = int(subscription.expiration_time.timestamp() * 1000)

    try:
        webpush(
            subscription_info,
            data=json.dumps(payload),
            vapid_private_key=Config.PUSH_VAPID_PRIVATE_KEY,
            vapid_claims={'sub': Config.PUSH_VAPID_CLAIMS_SUBJECT},
        )
        return True
    except WebPushException as exc:
        response = getattr(exc, 'response', None)
        if response:
            logger.error('[Push] WebPush error (status %d): %s', response.status_code, exc)
        else:
            logger.error('[Push] WebPush error: %s', exc)
        raise


def send_notification_to_user(user_id, title, body, tag, url='/dashboard'):
    payload = {
        'title': title,
        'body': body,
        'tag': tag,
        'url': url,
        'icon': '/static/icons/icon-192.png',
        'badge': '/static/icons/icon-192.png',
    }

    subscriptions = _iter_user_subscriptions(user_id)
    if not subscriptions:
        logger.warning('[Push] No active subscriptions found for user %s - notification not sent. (tag: %s)', user_id, tag)
        return 0

    sent_count = 0
    for subscription in subscriptions:
        try:
            send_web_push_to_subscription(subscription, payload)
            sent_count += 1
            logger.info('[Push] Notification sent successfully to user %s via subscription %s (tag: %s)', 
                       user_id, subscription.endpoint_hash, tag)
        except WebPushException as exc:
            response = getattr(exc, 'response', None)
            if response and response.status_code in (404, 410):
                # Endpoint is gone - delete subscription immediately
                try:
                    logger.warning('[Push] Subscription endpoint expired for user %s (status %d). Deleting subscription.',
                                   user_id, response.status_code)
                    db.session.delete(subscription)
                    db.session.commit()
                except Exception as db_exc:
                    logger.error('[Push] Failed to delete stale subscription for user %s: %s', user_id, db_exc, exc_info=True)
            elif response and response.status_code in (400, 401):
                # Bad request / Unauthorized - mark subscription inactive to avoid further 400/401 errors
                try:
                    subscription.active = False
                    db.session.commit()
                    logger.warning('[Push] Subscription for user %s marked inactive due to status %d.', user_id, response.status_code)
                except Exception as db_exc:
                    logger.error('[Push] Failed to mark subscription inactive for user %s: %s', user_id, db_exc, exc_info=True)
            else:
                logger.error('[Push] WebPush exception for user %s: %s (status: %s)',
                             user_id, exc, response.status_code if response else 'unknown')
        except Exception as exc:
            logger.error('[Push] Unexpected error sending notification to user %s: %s', user_id, exc, exc_info=True)


    if sent_count > 0:
        logger.info('[Push] Notification delivery complete for user %s: %d/%d subscriptions (tag: %s)', 
                   user_id, sent_count, len(subscriptions), tag)
    else:
        logger.warning('[Push] Failed to send notification to user %s via any subscription (tag: %s)', user_id, tag)

    return sent_count


def send_high_glucose_alert(user_id, predicted_glucose):
    payload = build_notification_payload('high-glucose-alert', predicted_glucose=predicted_glucose)
    return send_notification_to_user(user_id, payload['title'], payload['body'], payload['tag'], payload['url'])


def get_daily_log_reminder_candidates(today):
    logged_users = set()
    for model in (GlucoseEntry, MealEntry, ActivityEntry, SleepEntry):
        for user_id, in db.session.query(model.user_id).filter(model.date == today).distinct():
            logged_users.add(user_id)
    return User.query.filter(User.id.notin_(logged_users)).all()


def get_weekly_summary_candidates(today):
    seven_days_ago = today - timedelta(days=7)
    logged_users = set()
    for model in (GlucoseEntry, MealEntry, ActivityEntry, SleepEntry):
        for user_id, in db.session.query(model.user_id).filter(model.date >= seven_days_ago).distinct():
            logged_users.add(user_id)
    return User.query.filter(User.id.in_(logged_users)).all() if logged_users else []


def get_weekly_summary_metrics(user_id, today):
    seven_days_ago = today - timedelta(days=7)
    return {
        'avg_glucose': db.session.query(func.avg(GlucoseEntry.glucose_level)).filter(
            GlucoseEntry.user_id == user_id,
            GlucoseEntry.date >= seven_days_ago,
        ).scalar(),
        'activity_minutes': db.session.query(func.sum(ActivityEntry.duration_minutes)).filter(
            ActivityEntry.user_id == user_id,
            ActivityEntry.date >= seven_days_ago,
        ).scalar(),
        'sleep_hours': db.session.query(func.avg(SleepEntry.sleep_duration)).filter(
            SleepEntry.user_id == user_id,
            SleepEntry.date >= seven_days_ago,
        ).scalar(),
    }


def get_profile_refresh_candidates(now):
    threshold = now - timedelta(days=90)
    candidates = []
    for user in User.query.all():
        profile = user.patient_profile
        if not profile:
            candidates.append(user)
            continue
        if profile.updated_at < threshold:
            candidates.append(user)
    return candidates