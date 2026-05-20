from flask import jsonify, request, current_app
from flask_login import current_user, login_required

from . import push_bp
from push_service import subscribe_user, unsubscribe_user
from models import db, PushSubscription
from config import Config


@push_bp.route('/push/config', methods=['GET'])
@login_required
def push_config():
    """Get push configuration (VAPID public key) for frontend."""
    return jsonify({
        'vapid_public_key': Config.PUSH_VAPID_PUBLIC_KEY,
        'enabled': bool(Config.PUSH_VAPID_PUBLIC_KEY and Config.PUSH_VAPID_PRIVATE_KEY)
    })


@push_bp.route('/api/push-config', methods=['GET'])
@login_required
def api_push_config():
    """API endpoint for push configuration (VAPID public key)."""
    return jsonify({
        'vapid_public_key': Config.PUSH_VAPID_PUBLIC_KEY,
        'enabled': bool(Config.PUSH_VAPID_PUBLIC_KEY and Config.PUSH_VAPID_PRIVATE_KEY)
    })


@push_bp.route('/push/subscribe', methods=['POST'])
@login_required
def subscribe():
    """Save or update push subscription."""
    try:
        payload = request.get_json(silent=True) or {}
        subscribe_user(payload, current_user, user_agent=request.headers.get('User-Agent'))
        current_app.logger.info('[Push] User %s subscribed to push notifications', current_user.id)
        return jsonify({'status': 'success'})
    except Exception as e:
        current_app.logger.error('[Push] Error subscribing user %s: %s', current_user.id, e, exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 400


@push_bp.route('/push/sync-subscription', methods=['POST'])
@login_required
def sync_subscription():
    """
    Sync current subscription with backend.
    Called on every page load to ensure subscription is up-to-date.
    If subscription changed, update it.
    """
    try:
        payload = request.get_json(silent=True) or {}
        endpoint = payload.get('endpoint')
        
        if not endpoint:
            return jsonify({'status': 'error', 'message': 'endpoint required'}), 400
        
        # Check if this subscription already exists for user
        existing = PushSubscription.query.filter_by(user_id=current_user.id, endpoint=endpoint).first()
        
        if existing and existing.active:
            # Subscription already synced
            current_app.logger.debug('[Push] Subscription sync for user %s - already active', current_user.id)
            return jsonify({'status': 'synced', 'message': 'subscription already active'})
        
        # New subscription or reactivating old one
        subscribe_user(payload, current_user, user_agent=request.headers.get('User-Agent'))
        current_app.logger.info('[Push] Subscription synced for user %s', current_user.id)
        return jsonify({'status': 'updated', 'message': 'subscription updated'})
    except Exception as e:
        current_app.logger.error('[Push] Error syncing subscription for user %s: %s', current_user.id, e, exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 400


@push_bp.route('/push/unsubscribe', methods=['POST'])
@login_required
def unsubscribe():
    """Remove push subscription."""
    try:
        payload = request.get_json(silent=True) or {}
        removed = unsubscribe_user(current_user, payload.get('endpoint'))
        if removed:
            current_app.logger.info('[Push] User %s unsubscribed from push notifications', current_user.id)
        else:
            current_app.logger.warning('[Push] Unsubscribe requested for user %s but no matching subscription found', current_user.id)
        return jsonify({'status': 'success', 'removed': removed})
    except Exception as e:
        current_app.logger.error('[Push] Error unsubscribing user %s: %s', current_user.id, e, exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 400


@push_bp.route('/push/status', methods=['GET'])
@login_required
def status():
    """Get push notification status for current user."""
    try:
        subscription_count = current_user.push_subscriptions.filter_by(active=True).count()
        has_subscriptions = subscription_count > 0
        
        current_app.logger.debug('[Push] Status check for user %s: enabled=%s, count=%d', 
                                 current_user.id, has_subscriptions, subscription_count)
        
        return jsonify({
            'enabled': has_subscriptions,
            'subscription_count': subscription_count
        })
    except Exception as e:
        current_app.logger.error('[Push] Error checking push status for user %s: %s', current_user.id, e, exc_info=True)
        return jsonify({'status': 'error', 'enabled': False, 'subscription_count': 0}), 500