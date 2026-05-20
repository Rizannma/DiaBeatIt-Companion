# Web Push Notification Implementation Guide

## Overview

This guide implements Web Push Notifications with VAPID keys for DiaBeatIt without using Firebase or third-party services.

## Features Implemented

✅ **Lazy Loading**: Models load only on first inference, cached in memory  
✅ **Subscription Management**: Enable/disable notifications via UI  
✅ **Subscription Syncing**: Automatically syncs on every page load  
✅ **Login Notifications**: "Welcome back" on first login of day  
✅ **Account Lock Notifications**: Sent when account is locked after 3 failed attempts  
✅ **Account Unlock Notifications**: Sent when account is restored  
✅ **Multiple Devices**: Supports multiple subscriptions per user  
✅ **Stale Subscription Cleanup**: Auto-removes expired/invalid subscriptions  

---

## Database Changes

### User Model (models.py)

Two new fields added:
```python
last_login_notified_date = db.Column(db.Date, nullable=True)
lock_until = db.Column(db.DateTime, nullable=True)
```

### PushSubscription Model

Already exists with:
- `endpoint`: Push endpoint URL
- `p256dh`, `auth`: Encryption keys
- `user_id`: Foreign key to user
- `active`: Boolean flag
- `created_at`, `updated_at`: Timestamps

### Migration

Run:
```bash
flask db migrate -m "Add notification tracking fields"
flask db upgrade
```

---

## Environment Setup

### 1. Generate VAPID Keys

```bash
npm install -g web-push
web-push generate-vapid-keys
```

### 2. Update .env

```env
VAPID_PUBLIC_KEY=your_public_key_here
VAPID_PRIVATE_KEY=your_private_key_here
PUSH_VAPID_CLAIMS_SUBJECT=mailto:your_email@example.com
```

### 3. Verify Config

In `config.py` (already configured):
```python
PUSH_VAPID_PUBLIC_KEY = os.environ.get('PUSH_VAPID_PUBLIC_KEY')
PUSH_VAPID_PRIVATE_KEY = os.environ.get('PUSH_VAPID_PRIVATE_KEY')
PUSH_VAPID_CLAIMS_SUBJECT = os.environ.get('PUSH_VAPID_CLAIMS_SUBJECT', 'mailto:your_email@example.com')
```

---

## Frontend Integration

### 1. Add to Dashboard HTML (templates/dashboard.html)

Add these imports to the `<head>`:
```html
<!-- Push notification styles -->
<link rel="stylesheet" href="{{ url_for('static', filename='css/notification-bell.css') }}">

<!-- Push notification scripts -->
<script src="{{ url_for('static', filename='js/push-subscription.js') }}"></script>
<script src="{{ url_for('static', filename='js/notification-bell.js') }}"></script>
```

### 2. Add Notification Bell to Navigation/Header

Insert this in your navbar/header (e.g., near user profile):
```html
<!-- Notification Bell Component -->
<div class="notification-bell-container">
  <button id="notification-bell" title="Notifications" aria-label="Notification bell">
    🔔
    <span id="notification-badge">0</span>
  </button>

  <!-- Notification Dropdown -->
  <div id="notification-dropdown" class="notification-dropdown">
    <div class="notification-dropdown-header">
      <span>Notifications</span>
      <button class="btn btn-sm btn-outline-secondary" onclick="document.getElementById('notification-dropdown').classList.remove('open')">×</button>
    </div>

    <div class="notification-dropdown-content">
      <!-- Notification items will appear here -->
      <div class="notification-empty">No notifications yet</div>
    </div>

    <div class="notification-dropdown-footer">
      <label class="notification-toggle-label">
        <span>Enable Notifications</span>
        <label class="notification-toggle">
          <input type="checkbox" id="notifications-toggle">
          <span class="notification-toggle-slider"></span>
        </label>
      </label>
    </div>
  </div>
</div>
```

### 3. Update base.html

Add to `<head>` if navigation is in base.html:
```html
<link rel="stylesheet" href="{{ url_for('static', filename='css/notification-bell.css') }}">
<script src="{{ url_for('static', filename='js/push-subscription.js') }}"></script>
<script src="{{ url_for('static', filename='js/notification-bell.js') }}"></script>
```

---

## API Endpoints

### GET `/api/push-config`
Returns VAPID public key for frontend.
```json
{
  "vapid_public_key": "BG...",
  "enabled": true
}
```

### GET `/push/config`
Alias for `/api/push-config`.

### GET `/push/status`
Get current notification status for user.
```json
{
  "enabled": true,
  "subscription_count": 2
}
```

### POST `/push/subscribe`
Save a new push subscription.
```json
{
  "endpoint": "https://...",
  "expirationTime": null,
  "keys": {
    "p256dh": "...",
    "auth": "..."
  }
}
```

### POST `/push/sync-subscription`
Sync existing subscription (called on page load).
```json
{
  "endpoint": "https://...",
  "expirationTime": null,
  "keys": {
    "p256dh": "...",
    "auth": "..."
  }
}
```

### POST `/push/unsubscribe`
Remove a subscription.
```json
{
  "endpoint": "https://..."
}
```

---

## Notification Types

### login-success
Sent on first login of the day.
- **Title**: "Welcome back"
- **Body**: "Your daily insights are ready."

### account-locked
Sent when account is locked after failed login attempts.
- **Title**: "Account Locked"
- **Body**: "Too many login attempts. Your account is locked for {N} minutes."

### account-unlocked
Sent when account is unlocked.
- **Title**: "Account Unlocked"
- **Body**: "You can now log in again."

### daily-log-reminder
Sent by scheduler (unchanged).

### weekly-summary
Sent by scheduler (unchanged).

### high-glucose-alert
Sent when glucose prediction is high (unchanged).

---

## Scheduler Integration

Scheduler jobs are unchanged and automatically use new subscription system:

```python
@scheduler.add_job(id='daily_log_reminder', func=daily_log_reminder_job, trigger='cron', hour='19', minute='0')
@scheduler.add_job(id='weekly_summary', func=weekly_summary_job, trigger='cron', day_of_week='sun', hour='18', minute='0')
@scheduler.add_job(id='profile_refresh_reminder', func=profile_refresh_reminder_job, trigger='cron', day='1', hour='9', minute='0')
```

These call `send_notification_to_user()` which:
1. Fetches all active subscriptions for user
2. Sends to each device via `send_web_push_to_subscription()`
3. Removes invalid/expired subscriptions (410/404 status)

---

## User Flow

### Enable Notifications

1. User clicks bell icon → dropdown appears
2. User checks "Enable Notifications"
3. Browser requests `Notification.requestPermission()`
4. Frontend registers Service Worker
5. `pushManager.subscribe()` creates subscription
6. Subscription sent to `/push/subscribe`
7. Stored in database linked to user

### Page Load

1. Page loads, `PushSubscriptionManager.init()` runs
2. Fetches `/api/push-config` for VAPID key
3. Registers Service Worker
4. Gets current subscription via `pushManager.getSubscription()`
5. Syncs to backend via `/push/sync-subscription`
6. UI updates to reflect status

### Login

1. User successfully logs in
2. Backend checks `last_login_notified_date`
3. If not today, sends "Welcome back" notification
4. Sets `last_login_notified_date = today`

### Account Lockout

1. After 3 failed login attempts
2. `lockout_until` set to `utcnow() + timedelta(minutes={30|60|90})`
3. `lock_until` set for display in unlock notification
4. "Account Locked" notification sent
5. If account is later unlocked, "Account Unlocked" sent

---

## Testing

### Manual Test: Enable Notifications
```bash
curl -X POST http://localhost:5000/push/subscribe \
  -H "Content-Type: application/json" \
  -b "session_id=your_session" \
  -d '{
    "endpoint": "https://example.push.apple.com/endpoint",
    "keys": {
      "p256dh": "base64_encoded_key",
      "auth": "base64_encoded_auth"
    }
  }'
```

### Manual Test: Send Test Notification
```python
# In Flask shell
from models import User
from push_service import send_notification_to_user, build_notification_payload

user = User.query.get(1)
payload = build_notification_payload('login-success')
send_notification_to_user(user.id, payload['title'], payload['body'], payload['tag'], payload['url'])
```

### Browser Console Tests
```javascript
// Check if service worker registered
navigator.serviceWorker.getRegistrations()

// Get current subscription
navigator.serviceWorker.ready.then(reg => {
  reg.pushManager.getSubscription().then(sub => {
    console.log(sub);
  });
});

// Manually test permission
Notification.requestPermission().then(permission => {
  console.log('Permission:', permission);
});
```

---

## Troubleshooting

### "No VAPID public key in config"
- Check `.env` has `VAPID_PUBLIC_KEY`
- Restart Flask app
- Verify `Config.PUSH_VAPID_PUBLIC_KEY` is set

### "Service Worker registration failed"
- Check browser console for CORS errors
- Verify `/static/service-worker.js` exists and is accessible
- Check HTTPS is enabled (required for SW)

### "Notification permission denied"
- User clicked "Block" instead of "Allow"
- Clear site settings in browser
- Try incognito/private window

### Subscriptions not syncing
- Check `/push/status` returns `enabled: true`
- Check network tab in DevTools
- Verify subscription endpoint is valid
- Check browser `Application → Storage → IndexedDB`

### Old subscriptions not removed
- Backend will auto-remove on next push failure (410/404)
- Manual cleanup:
  ```python
  from models import PushSubscription
  PushSubscription.query.filter_by(active=False).delete()
  db.session.commit()
  ```

---

## Security Notes

✅ **Private key in environment only** - never exposed to frontend  
✅ **VAPID claims subject required** - configured in `.env`  
✅ **Subscriptions linked to user** - only user's own device can receive  
✅ **Stale subscriptions auto-removed** - handles expired endpoints  
✅ **HTTPS required** - Service Workers need secure context  

---

## Files Modified

- `models.py`: Added `last_login_notified_date`, `lock_until` to User
- `push_service.py`: Added 3 new notification types
- `routes/push.py`: Added `/api/push-config`, `/push/sync-subscription`
- `routes/auth.py`: Added login/lock/unlock notifications
- `static/js/push-subscription.js`: Subscription manager (new)
- `static/js/notification-bell.js`: UI handler (new)
- `static/css/notification-bell.css`: Styles (new)
- `static/service-worker.js`: Already has push handling

---

## Deployment to Render

1. Set VAPID environment variables in Render dashboard
2. Run migrations: `flask db upgrade`
3. Ensure HTTPS is enabled
4. Deploy normally: `git push`

The app will automatically:
- Detect VAPID keys are configured
- Enable Web Push in service worker
- Accept subscriptions from frontend
- Send notifications via pywebpush

---

## Next Steps

1. Generate VAPID keys: `web-push generate-vapid-keys`
2. Set `.env` variables
3. Run migrations: `flask db migrate && flask db upgrade`
4. Add HTML/CSS/JS imports to dashboard
5. Add notification bell HTML to navbar
6. Test enable/disable flow
7. Send test notification
8. Deploy!

