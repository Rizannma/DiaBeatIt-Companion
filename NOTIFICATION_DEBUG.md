# Push Notification System - Debugging Checklist

Use this checklist to verify all notification triggers are working correctly.

## Pre-Flight Checks

- [ ] **VAPID Keys Configured**
  ```bash
  # Check in app.log after startup
  grep "VAPID key loaded" app.log
  # Should see: [Push] VAPID key loaded
  ```
  - [ ] `PUSH_VAPID_PUBLIC_KEY` set in `.env`
  - [ ] `PUSH_VAPID_PRIVATE_KEY` set in `.env`
  - [ ] `PUSH_VAPID_CLAIMS_SUBJECT` set in `.env`

- [ ] **Scheduler Running**
  ```bash
  grep "APScheduler initialized" app.log
  # Should see: [Scheduler] APScheduler initialized with 3 jobs
  ```
  - [ ] `daily_log_reminder` job created
  - [ ] `weekly_summary` job created
  - [ ] `profile_refresh_reminder` job created

- [ ] **Database Migration Applied**
  - [ ] `last_login_notified_date` column exists in `users` table
  - [ ] `PushSubscription` model working
  - [ ] User has at least one active subscription

## Per-Notification Verification

### 1. Login Success Notification
**Expected:** Notification sent when user logs in (once per day)

**Steps:**
1. Enable push notifications in UI
2. Refresh page to ensure subscription is active
3. Log out and log back in
4. Should see notification

**Log Check:**
```bash
grep "login_success\|Login notification" app.log | tail -20
# Should see:
# [Auth] Login notification sent to user {user_id}
# [Push] Notification sent successfully to user {user_id}... (tag: login-success)
```

**If not working:**
- [ ] Check `/push/status` returns `enabled: true`
- [ ] Verify `last_login_notified_date` != today
- [ ] Check browser DevTools for subscription errors
- [ ] Check logs for `[Auth] Failed to send login notification`

---

### 2. High Glucose Alert Notification
**Expected:** Notification when predicted glucose > 180 mg/dL

**Steps:**
1. Log test data (glucose entries, meals, activity)
2. Go to dashboard - triggers prediction
3. Should see alert if predicted glucose > 180
4. Only once per day (refresh and try again - should not repeat)

**Log Check:**
```bash
grep "high-glucose-alert\|High glucose alert" app.log | tail -20
# Should see:
# [Prediction] High glucose alert sent to user {user_id}...
# [Push] Notification sent successfully to user {user_id}... (tag: high-glucose-alert)
```

**If not working:**
- [ ] Check prediction logic: `predict_diabetes_metrics()` being called?
- [ ] Check predicted value is > 180: Look for `predicted_next_glucose` in logs
- [ ] Check rate limiting: `alert_key` in session
- [ ] Check if user has active subscriptions

---

### 3. Daily Log Reminder Notification
**Expected:** Notification at 19:00 UTC to users who haven't logged today

**Scheduler:** Runs daily at 19:00 UTC

**Steps (Manual Testing):**
1. Modify scheduler trigger to run in 1 minute:
   ```python
   scheduler.add_job(..., trigger='cron', hour='X', minute='Y')  # Set to 1 min from now
   ```
2. Wait for job to execute
3. Check logs

**Log Check:**
```bash
grep "daily_log_reminder\|Daily log reminder" app.log | tail -30
# Should see:
# [Scheduler] Starting daily log reminder job for {date}
# [Scheduler] Found {N} users to remind about daily logging
# [Scheduler] Daily log reminder sent to user {user_id}...
```

**If not working:**
- [ ] Check current time vs scheduled time (19:00 UTC)
- [ ] Check scheduler logs for job execution
- [ ] Check `get_daily_log_reminder_candidates()` query
- [ ] Check if any users match criteria (haven't logged today)

---

### 4. Weekly Summary Notification
**Expected:** Notification every Sunday at 18:00 UTC with metrics

**Scheduler:** Runs Sundays at 18:00 UTC

**Steps (Manual Testing):**
1. Ensure today is Sunday or modify scheduler to run today
2. Add test data with entries from last 7 days
3. Trigger job and check logs

**Log Check:**
```bash
grep "weekly_summary\|Weekly summary" app.log | tail -30
# Should see:
# [Scheduler] Starting weekly summary job for {date}
# [Scheduler] Found {N} users with activity in last 7 days
# [Scheduler] Weekly summary sent to user {user_id}...
```

**If not working:**
- [ ] Check if it's a Sunday or modify trigger
- [ ] Check `get_weekly_summary_candidates()` query
- [ ] Verify test users have entries in last 7 days
- [ ] Check metrics calculation in `get_weekly_summary_metrics()`

---

### 5. Profile Refresh Reminder Notification
**Expected:** Notification on 1st of month at 09:00 UTC

**Scheduler:** Runs 1st of each month at 09:00 UTC

**Steps (Manual Testing):**
1. Set today to 1st of month (or modify scheduler)
2. Create test users with no profile or profile > 90 days old
3. Trigger job and check logs

**Log Check:**
```bash
grep "profile_refresh\|Profile refresh" app.log | tail -30
# Should see:
# [Scheduler] Starting profile refresh reminder job
# [Scheduler] Found {N} users who need profile refresh reminder
# [Scheduler] Profile refresh reminder sent to user {user_id}...
```

**If not working:**
- [ ] Check `get_profile_refresh_candidates()` query
- [ ] Verify threshold is 90 days: `now - timedelta(days=90)`
- [ ] Check if test users qualify

---

## Subscription Management Verification

### Check Active Subscriptions
```bash
# Database query
SELECT user_id, COUNT(*) as sub_count FROM push_subscription WHERE active=TRUE GROUP BY user_id;

# API check
curl -b cookies.txt http://localhost:5000/push/status
# Should return: {"enabled": true, "subscription_count": N}
```

### Check Subscription Sync
```bash
grep "Status check\|Subscription sync\|sync-subscription" app.log | tail -20
# Should see successful syncs on page load:
# [Push] Status check for user {user_id}: enabled=True, count=1
```

### Check for Stale Subscriptions
```bash
# Database query
SELECT user_id, COUNT(*) as stale_count FROM push_subscription WHERE active=FALSE GROUP BY user_id;

# Should cleanup automatically on failed sends:
# [Push] Subscription endpoint expired for user {user_id}
```

---

## WebPush Errors - Common Issues

### Error: "VAPID keys are missing"
```bash
grep "VAPID keys are missing\|Web Push is disabled" app.log
```
**Fix:** Set environment variables and restart

### Error: "WebPush error (410 Gone)"
```bash
grep "status 410\|endpoint expired" app.log
```
**Expected:** Subscription auto-marked as inactive and user re-subscribes next visit

### Error: "WebPush error (401 Unauthorized)"
```bash
grep "status 401\|Unauthorized" app.log
```
**Fix:** Check VAPID keys are valid and match browser configuration

### Error: "No subscriptions found for user"
```bash
grep "No active subscriptions found" app.log
```
**Fix:** User must enable push notifications via UI bell icon

---

## Performance Checks

### Scheduler Job Execution Time
```bash
grep "Starting.*_job\|completed" app.log | grep -E "daily_log_reminder|weekly_summary|profile_refresh"
# Calculate: completed - started = execution time
# Should be < 30 seconds for typical user base
```

### Notification Delivery Rate
```bash
grep "Notification delivery complete\|Notification sent successfully" app.log | wc -l
# Count successful deliveries
# Should be high relative to trigger attempts
```

### Database Query Performance
```bash
# Monitor slow queries in logs if enabled:
grep "slow query\|query took" app.log
```

---

## End-to-End Test Scenario

**Step 1: Setup**
```bash
# Enable notifications
# Navigate to dashboard, click bell, approve subscription
# Check: /push/status returns enabled=true
```

**Step 2: Test Login Notification**
```bash
# Log out
# Log back in
# Check: Browser notification appears
# Check: app.log has [Auth] and [Push] entries
```

**Step 3: Test High Glucose Alert**
```bash
# Add test entries to generate glucose data
# Visit dashboard (triggers prediction)
# Check: Notification appears if > 180
# Check: app.log has [Prediction] entries
```

**Step 4: Test Scheduler**
```bash
# Modify scheduler to run in 1 minute
# Restart app
# Wait for job to execute
# Check: app.log has [Scheduler] entries
```

**Step 5: Verify All Logs**
```bash
# Collect all notifications in timeline:
grep -E "\[Auth\]|\[Push\]|\[Scheduler\]|\[Prediction\]" app.log | grep "notification\|sent\|completed"

# Should show: trigger → delivery → completion for each notification
```

---

## Log Levels Reference

**DEBUG:** Detailed subscription sync, status checks
**INFO:** Successful notification sends, scheduler job starts/completions
**WARNING:** No subscriptions found, sync failures, backend unsubscribe failures
**ERROR:** WebPush exceptions, VAPID key issues, database errors

---

## Quick Commands

```bash
# Watch logs in real-time
tail -f app.log | grep -E "\[Push\]|\[Auth\]|\[Scheduler\]"

# Count notifications sent today
grep "$(date +%Y-%m-%d)" app.log | grep "Notification sent successfully" | wc -l

# Find errors for a specific user
grep "user 123" app.log | grep -i error

# Check scheduler status
grep "APScheduler" app.log

# Find all notification triggers
grep "send_notification_to_user\|send_high_glucose_alert" app.log

# Export logs for analysis
grep -E "\[Push\]|\[Auth\]|\[Scheduler\]" app.log > notification_logs.txt
```

---

## Frequently Asked Questions

**Q: Notification doesn't appear but logs show "sent successfully"**
- A: Browser may be in focus. Service worker only shows notifications when app is not active. Check service worker registration in DevTools.

**Q: Same user getting multiple login notifications per day**
- A: Check if `last_login_notified_date` column exists and is being set. See migration check above.

**Q: Scheduler job not running at scheduled time**
- A: Check system timezone vs UTC in scheduler. Times are in UTC. Also check APScheduler logs for errors.

**Q: High glucose alert triggers even for user without subscriptions**
- A: Correct behavior - alert is triggered but returns 0 sent_count. Check logs for "No active subscriptions".

**Q: WebPush says "Unauthorized" but VAPID keys are set**
- A: VAPID keys must match the browser configuration. Regenerate keys and update both backend and frontend.
