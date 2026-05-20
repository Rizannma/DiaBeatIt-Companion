# Push Notification System - Complete Flow Documentation

## Overview
The push notification system has been redesigned for reliability with comprehensive logging, error handling, and guaranteed delivery tracking.

## Notification Types & Triggers

### 1. **Login Success Notification**
**Type:** `login-success`  
**Message:** "Welcome back - Your daily insights are ready"

**Triggers:**
- Direct login: User enters email/password → `/auth/login` → password verified → `send_notification_to_user()` called
- OTP login: User enters OTP → `/verify_login_otp` → OTP verified → `send_notification_to_user()` called
- **Rate limiting:** Only once per day per user (tracked via `last_login_notified_date`)

**Code Location:** 
- `/routes/auth.py` - Lines ~75-90 (direct login)
- `/routes/verification.py` - Lines ~115-130 (OTP verification)

**Log Pattern:**
```
[Auth] Login notification sent to user {user_id}
[Push] Notification sent successfully to user {user_id} via subscription {endpoint_hash} (tag: login-success)
```

---

### 2. **High Glucose Alert Notification**
**Type:** `high-glucose-alert`  
**Condition:** Predicted glucose > 180 mg/dL  
**Message:** "Your predicted glucose is {value} mg/dL. Review your latest logs."

**Triggers:**
- User views dashboard with ML prediction
- Any route that calls `predict_diabetes_metrics(user_id)` and result exceeds 180
- **Rate limiting:** Only once per day per user (via session key)

**Code Location:**
- `/routes/prediction_service.py` - `predict_diabetes_metrics()` function
- `/routes/push.py` - Contains the handler

**Log Pattern:**
```
[Prediction] High glucose alert sent to user {user_id} (predicted: {value} mg/dL, subscriptions: {count})
[Push] Notification sent successfully to user {user_id} via subscription {endpoint_hash} (tag: high-glucose-alert)
```

---

### 3. **Daily Log Reminder Notification**
**Type:** `daily-log-reminder`  
**Message:** "Log today's glucose, meals, activity, and sleep."

**Scheduler:** APScheduler job - **Daily at 19:00 UTC**

**Triggers:**
- Runs every day at 7:00 PM UTC
- Identifies users who haven't logged today (no entries in GlucoseEntry, MealEntry, ActivityEntry, SleepEntry)
- Sends notification to all non-logging users

**Code Location:**
- `/scheduler.py` - `daily_log_reminder_job()` function
- Candidate selection: `push_service.py::get_daily_log_reminder_candidates()`

**Log Pattern:**
```
[Scheduler] Starting daily log reminder job for {date}
[Scheduler] Found {N} users to remind about daily logging
[Scheduler] Daily log reminder sent to user {user_id} ({count} subscriptions)
[Push] Notification sent successfully to user {user_id} via subscription {endpoint_hash} (tag: daily-log-reminder)
```

---

### 4. **Weekly Summary Notification**
**Type:** `weekly-summary`  
**Message:** "Weekly snapshot: avg glucose {X} mg/dL, {Y} activity minutes, {Z} sleep hours"

**Scheduler:** APScheduler job - **Sundays at 18:00 UTC**

**Triggers:**
- Runs every Sunday at 6:00 PM UTC
- Identifies users with activity in last 7 days
- Sends aggregated metrics (glucose average, activity sum, sleep average)

**Code Location:**
- `/scheduler.py` - `weekly_summary_job()` function
- Candidate selection: `push_service.py::get_weekly_summary_candidates()`
- Metrics calculation: `push_service.py::get_weekly_summary_metrics()`

**Log Pattern:**
```
[Scheduler] Starting weekly summary job for {date}
[Scheduler] Found {N} users with activity in last 7 days
[Scheduler] Weekly summary sent to user {user_id} ({count} subscriptions)
[Push] Notification sent successfully to user {user_id} via subscription {endpoint_hash} (tag: weekly-summary)
```

---

### 5. **Profile Refresh Reminder Notification**
**Type:** `profile-refresh-reminder`  
**Message:** "Update your profile and lab values so your insights stay accurate."

**Scheduler:** APScheduler job - **1st of each month at 09:00 UTC**

**Triggers:**
- Runs monthly on the 1st at 9:00 AM UTC
- Identifies users with outdated profile (no profile or updated >90 days ago)

**Code Location:**
- `/scheduler.py` - `profile_refresh_reminder_job()` function
- Candidate selection: `push_service.py::get_profile_refresh_candidates()`

**Log Pattern:**
```
[Scheduler] Starting profile refresh reminder job
[Scheduler] Found {N} users who need profile refresh reminder
[Scheduler] Profile refresh reminder sent to user {user_id} ({count} subscriptions)
[Push] Notification sent successfully to user {user_id} via subscription {endpoint_hash} (tag: profile-refresh-reminder)
```

---

### 6. **Account Locked Notification**
**Type:** `account-locked`  
**Condition:** 3+ failed login attempts  
**Message:** "Too many login attempts. Your account is locked for {X} minutes."

**Triggers:**
- User fails login 3+ times
- Account locked for 30/60/90 minutes depending on attempt count
- Notification sent when lock is activated

**Code Location:**
- `/routes/auth.py` - Lines ~113-123 (lock notification)

**Log Pattern:**
```
[Auth] Account lock notification sent to user {user_id} for {minutes} minutes
[Push] Notification sent successfully to user {user_id} via subscription {endpoint_hash} (tag: account-locked)
```

---

### 7. **Account Unlocked Notification**
**Type:** `account-unlocked`  
**Condition:** User logs in after lockout expires  
**Message:** "You can now log in again."

**Triggers:**
- User attempts login during/after lockout period
- Lockout has expired
- Account is re-enabled

**Code Location:**
- `/routes/auth.py` - Lines ~41-48 (unlock notification)

**Log Pattern:**
```
[Auth] Account unlock notification sent to user {user_id}
[Push] Notification sent successfully to user {user_id} via subscription {endpoint_hash} (tag: account-unlocked)
```

---

## End-to-End Notification Delivery Flow

### 1. Trigger Detection
```
User Action/Scheduled Time
    ↓
Condition Checked (password match, glucose > 180, etc.)
    ↓
Logging: "[Component] Starting action..."
```

### 2. Notification Building
```
build_notification_payload(notification_type, **context)
    ↓
Returns: {title, body, tag, url, icon, badge}
    ↓
Logging: "[Push] Built payload for tag: {tag}"
```

### 3. Database Query
```
PushSubscription.query.filter_by(user_id=user_id, active=True).all()
    ↓
Returns: List of active subscriptions for user
    ↓
Logging: "[Push] {N} active subscriptions found for user {user_id}"
```

### 4. Delivery Attempt
```
For each subscription:
    webpush(subscription_info, payload, vapid_keys)
    ↓
    Success: Logging: "[Push] Notification sent successfully..."
    ↓
    Failed (410/404): Mark subscription as inactive, cleanup
    ↓
    Failed (other): Log error with response code
```

### 5. Completion Report
```
send_notification_to_user() returns:
    - sent_count: Number of successful deliveries
    - Logging: "[Push] Notification delivery complete: {sent}/{total} subscriptions"
```

---

## Logging Guide for Troubleshooting

### Check if notification was triggered:
```bash
# Look for initial trigger log
grep "\[Auth\]\|\[Push\]\|\[Scheduler\]\|\[Prediction\]" app.log | grep "sent to user {user_id}"
```

### Check if subscription exists:
```bash
# Look for subscription status
grep "\[Push\] Status check for user {user_id}" app.log
# Should see: enabled=True, count=N
```

### Check delivery failures:
```bash
# Look for failed sends
grep "\[Push\] Failed to send\|\[Push\] WebPush error" app.log
```

### Check scheduler jobs:
```bash
# Look for scheduler initialization
grep "\[Scheduler\] APScheduler initialized" app.log
grep "\[Scheduler\] Starting.*job" app.log
```

### Full notification trace for a user:
```bash
grep "user_id" app.log | grep -E "\[Auth\]|\[Push\]|\[Scheduler\]|\[Prediction\]"
```

---

## Configuration Required

### 1. VAPID Keys (in .env or config)
```
PUSH_VAPID_PUBLIC_KEY=<your-public-key>
PUSH_VAPID_PRIVATE_KEY=<your-private-key>
PUSH_VAPID_CLAIMS_SUBJECT=mailto:your-email@example.com
```

### 2. Scheduler Configuration
APScheduler is initialized in `/app.py::create_app()`:
- Job 1: `daily_log_reminder` - Daily at 19:00 UTC
- Job 2: `weekly_summary` - Sundays at 18:00 UTC
- Job 3: `profile_refresh_reminder` - 1st of month at 09:00 UTC

### 3. Database Schema
Ensure migration `add_last_login_notified_date` has been applied:
```
users.last_login_notified_date (DATE, nullable, for login notification rate-limiting)
```

---

## Error Scenarios & Recovery

### Scenario: "No subscriptions found for user"
**Cause:** User hasn't enabled push notifications
**Recovery:** 
- Check notification bell UI - user must click and accept subscription
- Check `/push/status` endpoint returns `enabled=true`
- Frontend must have synced subscription successfully

### Scenario: "WebPush error (410 Gone)"
**Cause:** Subscription endpoint is stale/expired
**Recovery:**
- Notification will mark subscription as inactive
- On next visit, frontend re-syncs and creates new subscription
- User will receive notifications going forward

### Scenario: "VAPID keys missing"
**Cause:** Environment variables not set
**Recovery:**
- Generate VAPID keys using `web-push generate-vapid-keys`
- Set in `.env`: `PUSH_VAPID_PUBLIC_KEY` and `PUSH_VAPID_PRIVATE_KEY`
- Restart Flask app
- Check logs for: "[Push] VAPID key loaded"

### Scenario: "Scheduler job not running"
**Cause:** APScheduler not initialized or database not accessible
**Recovery:**
- Check app startup logs for: "[Scheduler] APScheduler initialized"
- Verify database connection is working
- Check that scheduler.start() was called in `app.py`
- Look for exceptions in logs during job execution window

---

## Testing Notifications Manually

### Test login notification:
1. Enable notifications via bell UI
2. Log out and log back in
3. Check browser notifications and `app.log` for delivery logs

### Test high glucose alert:
1. Log entries to create data
2. Visit dashboard (triggers prediction)
3. If predicted glucose > 180, notification should appear
4. Check logs for `[Prediction] High glucose alert sent`

### Test scheduler jobs:
1. Modify scheduler times to trigger within next minute
2. Watch logs for job execution: `[Scheduler] Starting.*_job`
3. Check delivery logs: `[Push] Notification sent successfully`

---

## Summary: What's Been Fixed

1. **Comprehensive Logging**
   - Every notification trigger, send attempt, and delivery is logged
   - Includes subscription count, endpoint hash, and tag for tracing

2. **Error Handling**
   - WebPush exceptions caught and categorized (410, 404 vs others)
   - Failed sends don't crash the app - errors logged and reported
   - Scheduler jobs wrapped in try/catch with full error context

3. **State Tracking**
   - Sent count returned to caller
   - Warning logged if no subscriptions found
   - Stale subscriptions cleaned up automatically

4. **Notification Triggers Verified**
   - Login success: Called after auth verification
   - High glucose: Called after ML prediction
   - Daily reminder: Runs via scheduler daily at 19:00 UTC
   - Weekly summary: Runs via scheduler Sundays at 18:00 UTC
   - Profile refresh: Runs via scheduler monthly

5. **Frontend-Backend Sync**
   - UI maintains subscription state with localStorage
   - Backend validates state on page load
   - Sync endpoint prevents duplicate subscriptions
   - Status endpoint always accurate

6. **Rate Limiting**
   - Login notifications: Once per day per user
   - High glucose alerts: Once per day per user (session-based)
   - Account lock/unlock: Triggered once per event

All notifications now have proper delivery tracking, failure recovery, and detailed logging for debugging.
