import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from database import get_db_connection
from config import Config
import logging
import requests

logger = logging.getLogger(__name__)

def send_email_notification(ticker, alert_type, target_value, current_price):
    """Send email alert notification"""
    try:
        # Get notification settings from database
        with get_db_connection() as conn:
            cursor = conn.execute(
                'SELECT email_enabled, email_address FROM notification_settings WHERE id = 1'
            )
            settings = cursor.fetchone()

            if not settings or not settings['email_enabled']:
                return False, "Email notifications disabled"

            if not settings['email_address']:
                return False, "Email address not configured"

        # Check SMTP configuration
        if not all([Config.SMTP_HOST, Config.SMTP_USERNAME, Config.SMTP_PASSWORD]):
            return False, "SMTP credentials not configured"

        # Format alert message
        subject = f"🚨 StockPulse Alert: {ticker}"

        if alert_type == 'above':
            message = f"{ticker} has reached ${current_price:.2f}, exceeding your target of ${target_value:.2f}"
        elif alert_type == 'below':
            message = f"{ticker} has dropped to ${current_price:.2f}, below your target of ${target_value:.2f}"
        else:  # percentage
            message = f"{ticker} has moved significantly to ${current_price:.2f} (threshold: {target_value}%)"

        # Create email
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = Config.SMTP_FROM_EMAIL or Config.SMTP_USERNAME
        msg['To'] = settings['email_address']

        # HTML body
        html_body = f"""
        <html>
          <body style="font-family: Arial, sans-serif;">
            <h2 style="color: #667eea;">StockPulse Alert</h2>
            <p style="font-size: 16px;">{message}</p>
            <p style="font-size: 24px; font-weight: bold; margin: 20px 0;">
              {ticker}: ${current_price:.2f}
            </p>
            <hr style="margin: 30px 0;">
            <p style="font-size: 12px; color: #6c757d;">
              This alert has been automatically deactivated.
              Visit StockPulse to manage your alerts.
            </p>
          </body>
        </html>
        """

        msg.attach(MIMEText(html_body, 'html'))

        # Send via SMTP
        with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT) as server:
            server.starttls()
            server.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)
            server.send_message(msg)

        logger.info(f"Email sent to {settings['email_address']}")
        return True, None

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Email send failed: {error_msg}")
        return False, error_msg


def send_telegram_notification(ticker, alert_type, target_value, current_price):
    """Send Telegram alert notification"""
    try:
        # Get notification settings from database
        with get_db_connection() as conn:
            cursor = conn.execute(
                'SELECT telegram_enabled, telegram_chat_id, telegram_bot_token FROM notification_settings WHERE id = 1'
            )
            settings = cursor.fetchone()

            if not settings or not settings['telegram_enabled']:
                return False, "Telegram notifications disabled"

            if not settings['telegram_chat_id'] or not settings['telegram_bot_token']:
                return False, "Telegram credentials not configured"

        # Format message
        if alert_type == 'above':
            message = f"🚨 *StockPulse Alert*\n\n{ticker} has reached ${current_price:.2f}, exceeding your target of ${target_value:.2f}"
        elif alert_type == 'below':
            message = f"🚨 *StockPulse Alert*\n\n{ticker} has dropped to ${current_price:.2f}, below your target of ${target_value:.2f}"
        else:  # percentage
            message = f"🚨 *StockPulse Alert*\n\n{ticker} has moved significantly to ${current_price:.2f} (threshold: {target_value}%)"

        message += f"\n\n📊 Current Price: *${current_price:.2f}*\n\n_This alert has been automatically deactivated._"

        # Send via Telegram Bot API
        url = f"https://api.telegram.org/bot{settings['telegram_bot_token']}/sendMessage"
        payload = {
            'chat_id': settings['telegram_chat_id'],
            'text': message,
            'parse_mode': 'Markdown'
        }

        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()

        logger.info(f"Telegram message sent to chat_id: {settings['telegram_chat_id']}")
        return True, None

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Telegram send failed: {error_msg}")
        return False, error_msg


def send_discord_notification(ticker, alert_type, target_value, current_price):
    """Send Discord alert notification via webhook"""
    try:
        # Get notification settings from database
        with get_db_connection() as conn:
            cursor = conn.execute(
                'SELECT discord_enabled, discord_webhook_url FROM notification_settings WHERE id = 1'
            )
            settings = cursor.fetchone()

            if not settings or not settings['discord_enabled']:
                return False, "Discord notifications disabled"

            if not settings['discord_webhook_url']:
                return False, "Discord webhook not configured"

        # Format message
        if alert_type == 'above':
            description = f"{ticker} has reached ${current_price:.2f}, exceeding your target of ${target_value:.2f}"
            color = 0x28a745  # Green
        elif alert_type == 'below':
            description = f"{ticker} has dropped to ${current_price:.2f}, below your target of ${target_value:.2f}"
            color = 0xdc3545  # Red
        else:  # percentage
            description = f"{ticker} has moved significantly to ${current_price:.2f} (threshold: {target_value}%)"
            color = 0x667eea  # Purple

        # Create Discord embed
        embed = {
            "title": f"🚨 StockPulse Alert: {ticker}",
            "description": description,
            "color": color,
            "fields": [
                {
                    "name": "Current Price",
                    "value": f"${current_price:.2f}",
                    "inline": True
                },
                {
                    "name": "Target",
                    "value": f"${target_value:.2f}" if alert_type != 'percentage' else f"{target_value}%",
                    "inline": True
                }
            ],
            "footer": {
                "text": "This alert has been automatically deactivated."
            }
        }

        payload = {
            "embeds": [embed]
        }

        # Send via Discord webhook
        response = requests.post(settings['discord_webhook_url'], json=payload, timeout=10)
        response.raise_for_status()

        logger.info(f"Discord webhook message sent")
        return True, None

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Discord send failed: {error_msg}")
        return False, error_msg
