from database import get_db_connection
from stock_data import StockData
from notifications import send_email_notification, send_telegram_notification, send_discord_notification
from config import Config
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

def check_all_alerts():
    """Main function called by scheduler to check all active alerts"""
    try:
        logger.info("Starting alert check cycle")

        with get_db_connection() as conn:
            cursor = conn.execute('''
                SELECT id, ticker, alert_type, target_value, baseline_price,
                       notify_email, notify_telegram, notify_discord, triggered_at
                FROM price_alerts
                WHERE is_active = 1
            ''')
            alerts = [dict(row) for row in cursor.fetchall()]

        if not alerts:
            logger.info("No active alerts to check")
            return

        logger.info(f"Checking {len(alerts)} active alerts")

        # Group by ticker for efficient price fetching
        tickers = list(set([alert['ticker'] for alert in alerts]))
        ticker_prices = {}

        for ticker in tickers:
            try:
                stock = StockData(ticker)
                price = stock.get_current_price()
                if price:
                    ticker_prices[ticker] = price
                    logger.debug(f"{ticker}: ${price}")
            except Exception as e:
                logger.error(f"Failed to fetch price for {ticker}: {e}")

        # Check each alert
        for alert in alerts:
            try:
                check_single_alert(alert, ticker_prices.get(alert['ticker']))
            except Exception as e:
                logger.error(f"Error checking alert {alert['id']}: {e}")

        logger.info("Alert check cycle completed")

    except Exception as e:
        logger.critical(f"Alert checker crashed: {e}", exc_info=True)


def check_single_alert(alert, current_price):
    """Evaluate if a single alert should trigger"""
    if current_price is None:
        return

    alert_id = alert['id']
    ticker = alert['ticker']
    alert_type = alert['alert_type']
    target_value = alert['target_value']
    baseline_price = alert['baseline_price']

    should_trigger = False

    # Evaluate condition based on alert type
    if alert_type == 'above':
        should_trigger = current_price > target_value
    elif alert_type == 'below':
        should_trigger = current_price < target_value
    elif alert_type == 'percentage':
        if baseline_price:
            change_percent = ((current_price - baseline_price) / baseline_price) * 100
            should_trigger = abs(change_percent) >= abs(target_value)

    if should_trigger:
        # Check cooldown period
        if alert['triggered_at']:
            try:
                last_trigger = datetime.fromisoformat(alert['triggered_at'])
                cooldown_hours = Config.ALERT_COOLDOWN_HOURS
                if datetime.now() - last_trigger < timedelta(hours=cooldown_hours):
                    logger.debug(f"Alert {alert_id} in cooldown period")
                    return
            except:
                pass

        logger.info(f"Alert {alert_id} triggered: {ticker} at ${current_price}")
        trigger_alert(alert_id, ticker, alert_type, target_value, current_price,
                     alert['notify_email'], alert['notify_telegram'], alert['notify_discord'])


def trigger_alert(alert_id, ticker, alert_type, target_value, current_price,
                  notify_email, notify_telegram, notify_discord):
    """Handle alert triggering: send notifications and update database"""
    email_sent, email_error = False, None
    telegram_sent, telegram_error = False, None
    discord_sent, discord_error = False, None

    # Send email notification
    if notify_email:
        try:
            email_sent, email_error = send_email_notification(
                ticker, alert_type, target_value, current_price
            )
            if email_sent:
                logger.info(f"Email sent for alert {alert_id}")
            else:
                logger.error(f"Email failed for alert {alert_id}: {email_error}")
        except Exception as e:
            email_error = str(e)
            logger.error(f"Email exception for alert {alert_id}: {e}")

    # Send Telegram notification
    if notify_telegram:
        try:
            telegram_sent, telegram_error = send_telegram_notification(
                ticker, alert_type, target_value, current_price
            )
            if telegram_sent:
                logger.info(f"Telegram sent for alert {alert_id}")
            else:
                logger.error(f"Telegram failed for alert {alert_id}: {telegram_error}")
        except Exception as e:
            telegram_error = str(e)
            logger.error(f"Telegram exception for alert {alert_id}: {e}")

    # Send Discord notification
    if notify_discord:
        try:
            discord_sent, discord_error = send_discord_notification(
                ticker, alert_type, target_value, current_price
            )
            if discord_sent:
                logger.info(f"Discord sent for alert {alert_id}")
            else:
                logger.error(f"Discord failed for alert {alert_id}: {discord_error}")
        except Exception as e:
            discord_error = str(e)
            logger.error(f"Discord exception for alert {alert_id}: {e}")

    # Record in history and deactivate alert
    with get_db_connection() as conn:
        # Log to alert history
        conn.execute('''
            INSERT INTO alert_history
            (alert_id, ticker, alert_type, target_value, trigger_price,
             triggered_at, email_sent, telegram_sent, discord_sent,
             email_error, telegram_error, discord_error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (alert_id, ticker, alert_type, target_value, current_price,
              datetime.now().isoformat(), email_sent, telegram_sent, discord_sent,
              email_error, telegram_error, discord_error))

        # Deactivate alert
        conn.execute('''
            UPDATE price_alerts
            SET is_active = 0, triggered_at = ?
            WHERE id = ?
        ''', (datetime.now().isoformat(), alert_id))

    logger.info(f"Alert {alert_id} deactivated and logged to history")
