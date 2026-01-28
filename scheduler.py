from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from config import Config
from database import get_db_connection
import atexit
import logging

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()

def start_scheduler():
    """Initialize and start the background scheduler"""
    from alert_monitor import check_all_alerts

    logger.info("Starting background scheduler")

    # Schedule alert checking
    scheduler.add_job(
        func=check_all_alerts,
        trigger=IntervalTrigger(minutes=Config.ALERT_CHECK_INTERVAL),
        id='price_alert_checker',
        name='Check stock price alerts',
        replace_existing=True,
        max_instances=1
    )

    # Schedule daily report if enabled
    _schedule_daily_report()

    scheduler.start()
    logger.info(f"Scheduler started. Will check alerts every {Config.ALERT_CHECK_INTERVAL} minutes")

    atexit.register(lambda: scheduler.shutdown())


def _schedule_daily_report():
    """Add or update the daily report job based on database settings"""
    try:
        with get_db_connection() as conn:
            cursor = conn.execute(
                'SELECT daily_report_enabled, daily_report_time FROM notification_settings WHERE id = 1'
            )
            settings = cursor.fetchone()

        if settings and settings['daily_report_enabled']:
            report_time = settings['daily_report_time'] or Config.DAILY_REPORT_DEFAULT_TIME
        else:
            report_time = Config.DAILY_REPORT_DEFAULT_TIME

        hour, minute = report_time.split(':')

        scheduler.add_job(
            func=_run_daily_report_if_enabled,
            trigger=CronTrigger(hour=int(hour), minute=int(minute), day_of_week='mon-fri'),
            id='daily_watchlist_report',
            name='Daily watchlist analysis report',
            replace_existing=True,
            max_instances=1
        )

        logger.info(f"Daily report scheduled at {report_time} (Mon-Fri)")

    except Exception as e:
        logger.error(f"Failed to schedule daily report: {e}")
        # Fallback: schedule with default time
        scheduler.add_job(
            func=_run_daily_report_if_enabled,
            trigger=CronTrigger(hour=8, minute=0, day_of_week='mon-fri'),
            id='daily_watchlist_report',
            name='Daily watchlist analysis report',
            replace_existing=True,
            max_instances=1
        )


def _run_daily_report_if_enabled():
    """Wrapper that checks if daily report is enabled before running"""
    from daily_report import generate_daily_report

    try:
        with get_db_connection() as conn:
            cursor = conn.execute(
                'SELECT daily_report_enabled FROM notification_settings WHERE id = 1'
            )
            settings = cursor.fetchone()

        if settings and settings['daily_report_enabled']:
            logger.info("Daily report is enabled, generating report...")
            generate_daily_report()
        else:
            logger.debug("Daily report is disabled, skipping")

    except Exception as e:
        logger.error(f"Error checking daily report settings: {e}")


def reschedule_daily_report():
    """Called when the user updates daily report time in settings"""
    _schedule_daily_report()
    logger.info("Daily report rescheduled with updated settings")
