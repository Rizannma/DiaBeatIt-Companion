import logging
from datetime import datetime
from flask_apscheduler import APScheduler

from push_service import (
    build_notification_payload,
    get_daily_log_reminder_candidates,
    get_profile_refresh_candidates,
    get_weekly_summary_candidates,
    get_weekly_summary_metrics,
    send_notification_to_user,
)

logger = logging.getLogger(__name__)
scheduler = APScheduler()

def daily_log_reminder_job():
    """Send a daily reminder to log today's health data."""
    try:
        with scheduler.app.app_context():
            today = datetime.utcnow().date()
            logger.info('[Scheduler] Starting daily log reminder job for %s', today)
            
            users_to_remind = get_daily_log_reminder_candidates(today)
            logger.info('[Scheduler] Found %d users to remind about daily logging', len(users_to_remind))

            for user in users_to_remind:
                try:
                    payload = build_notification_payload('daily-log-reminder')
                    send_count = send_notification_to_user(user.id, payload['title'], payload['body'], payload['tag'], payload['url'])
                    if send_count > 0:
                        logger.info('[Scheduler] Daily log reminder sent to user %s (%d subscriptions)', user.id, send_count)
                    else:
                        logger.warning('[Scheduler] Daily log reminder could not be sent to user %s (no active subscriptions)', user.id)
                except Exception as e:
                    logger.error('[Scheduler] Error sending daily log reminder to user %s: %s', user.id, e, exc_info=True)
            
            logger.info('[Scheduler] Daily log reminder job completed')
    except Exception as e:
        logger.error('[Scheduler] Fatal error in daily_log_reminder_job: %s', e, exc_info=True)

def weekly_summary_job():
    """Send a weekly summary to active users."""
    try:
        with scheduler.app.app_context():
            today = datetime.utcnow().date()
            logger.info('[Scheduler] Starting weekly summary job for %s', today)
            
            users_to_remind = get_weekly_summary_candidates(today)
            logger.info('[Scheduler] Found %d users with activity in last 7 days', len(users_to_remind))

            for user in users_to_remind:
                try:
                    metrics = get_weekly_summary_metrics(user.id, today)
                    payload = build_notification_payload('weekly-summary', **metrics)
                    send_count = send_notification_to_user(user.id, payload['title'], payload['body'], payload['tag'], payload['url'])
                    if send_count > 0:
                        logger.info('[Scheduler] Weekly summary sent to user %s (%d subscriptions)', user.id, send_count)
                    else:
                        logger.warning('[Scheduler] Weekly summary could not be sent to user %s (no active subscriptions)', user.id)
                except Exception as e:
                    logger.error('[Scheduler] Error sending weekly summary to user %s: %s', user.id, e, exc_info=True)
            
            logger.info('[Scheduler] Weekly summary job completed')
    except Exception as e:
        logger.error('[Scheduler] Fatal error in weekly_summary_job: %s', e, exc_info=True)

def profile_refresh_reminder_job():
    """Send a monthly reminder to refresh profile and labs."""
    try:
        with scheduler.app.app_context():
            logger.info('[Scheduler] Starting profile refresh reminder job')
            
            users_to_remind = get_profile_refresh_candidates(datetime.utcnow())
            logger.info('[Scheduler] Found %d users who need profile refresh reminder', len(users_to_remind))

            for user in users_to_remind:
                try:
                    payload = build_notification_payload('profile-refresh-reminder')
                    send_count = send_notification_to_user(user.id, payload['title'], payload['body'], payload['tag'], payload['url'])
                    if send_count > 0:
                        logger.info('[Scheduler] Profile refresh reminder sent to user %s (%d subscriptions)', user.id, send_count)
                    else:
                        logger.warning('[Scheduler] Profile refresh reminder could not be sent to user %s (no active subscriptions)', user.id)
                except Exception as e:
                    logger.error('[Scheduler] Error sending profile refresh reminder to user %s: %s', user.id, e, exc_info=True)
            
            logger.info('[Scheduler] Profile refresh reminder job completed')
    except Exception as e:
        logger.error('[Scheduler] Fatal error in profile_refresh_reminder_job: %s', e, exc_info=True)


def init_scheduler(app):
    """Initializes and starts the scheduler."""
    if getattr(scheduler, 'running', False):
        logger.info('[Scheduler] Scheduler already running; skipping initialization')
        return

    try:
        # Ensure scheduler configuration exists and doesn't crash startup
        app.config.setdefault('SCHEDULER_API_ENABLED', False)
        app.config.setdefault('SCHEDULER_TIMEZONE', 'UTC')

        scheduler.init_app(app)

        # Schedule jobs
        scheduler.add_job(id='daily_log_reminder', func=daily_log_reminder_job, trigger='cron', hour='19', minute='0')
        scheduler.add_job(id='weekly_summary', func=weekly_summary_job, trigger='cron', day_of_week='sun', hour='18', minute='0')
        scheduler.add_job(id='profile_refresh_reminder', func=profile_refresh_reminder_job, trigger='cron', day='1', hour='9', minute='0')

        scheduler.start()
        logger.info('[Scheduler] APScheduler initialized with 3 jobs: daily_log_reminder, weekly_summary, profile_refresh_reminder')
    except Exception as e:
        logger.error('[Scheduler] Failed to initialize APScheduler: %s', e, exc_info=True)

