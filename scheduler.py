from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from config import Config
import atexit
import logging

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()

def start_scheduler():
    """Initialize and start the background scheduler"""
    # Import here to avoid circular imports
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

    scheduler.start()
    logger.info(f"Scheduler started. Will check alerts every {Config.ALERT_CHECK_INTERVAL} minutes")

    # Graceful shutdown
    atexit.register(lambda: scheduler.shutdown())
