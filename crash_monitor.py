import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from database import get_db_connection
from config import Config
from stock_data import StockData
from datetime import datetime, date
import logging
import requests

logger = logging.getLogger(__name__)

STOCK_MONITORS = ['SPY', 'QQQ', 'DIA']
CRYPTO_MONITORS = ['BTC-USD', 'ETH-USD', 'SOL-USD']

intraday_highs = {}
last_crash_alert = {}
last_reset_date = None


def check_for_crashes():
    """Main crash detection function called by the scheduler"""
    global last_reset_date

    try:
        with get_db_connection() as conn:
            cursor = conn.execute(
                '''SELECT crash_detection_enabled, crash_stock_threshold, crash_crypto_threshold,
                          email_enabled, telegram_enabled, discord_enabled
                   FROM notification_settings WHERE id = 1'''
            )
            settings = cursor.fetchone()

        if not settings or not settings['crash_detection_enabled']:
            return

        stock_threshold = settings['crash_stock_threshold'] or Config.CRASH_STOCK_THRESHOLD
        crypto_threshold = settings['crash_crypto_threshold'] or Config.CRASH_CRYPTO_THRESHOLD

        today = date.today()
        if last_reset_date != today:
            intraday_highs.clear()
            last_reset_date = today
            logger.info("Intraday highs reset for new trading day")

        stock_crashes = []
        crypto_crashes = []

        for ticker in STOCK_MONITORS:
            result = _check_ticker(ticker, stock_threshold)
            if result:
                stock_crashes.append(result)

        for ticker in CRYPTO_MONITORS:
            result = _check_ticker(ticker, crypto_threshold)
            if result:
                crypto_crashes.append(result)

        now = datetime.now()

        if stock_crashes and _can_alert('stocks', now):
            logger.warning(f"Stock flash crash detected: {stock_crashes}")
            _send_crash_notifications(stock_crashes, 'Stock Market', settings)
            last_crash_alert['stocks'] = now

        if crypto_crashes and _can_alert('crypto', now):
            logger.warning(f"Crypto flash crash detected: {crypto_crashes}")
            _send_crash_notifications(crypto_crashes, 'Crypto Market', settings)
            last_crash_alert['crypto'] = now

    except Exception as e:
        logger.error(f"Error in crash detection: {e}")


def _check_ticker(ticker, threshold):
    """Check a single ticker for flash crash conditions"""
    try:
        stock = StockData(ticker)
        price = stock.get_current_price()
        if not price:
            return None

        if ticker in intraday_highs:
            if price > intraday_highs[ticker]:
                intraday_highs[ticker] = price
        else:
            intraday_highs[ticker] = price
            return None

        high = intraday_highs[ticker]
        if high <= 0:
            return None

        drop_pct = ((high - price) / high) * 100

        if drop_pct >= threshold:
            symbol = ticker.replace('-USD', '') if '-USD' in ticker else ticker
            return {
                'ticker': ticker,
                'symbol': symbol,
                'price': round(price, 2),
                'high': round(high, 2),
                'drop_pct': round(drop_pct, 2)
            }

        return None

    except Exception as e:
        logger.error(f"Error checking {ticker}: {e}")
        return None


def _can_alert(market_type, now):
    """Check if cooldown period has passed"""
    if market_type not in last_crash_alert:
        return True
    elapsed = (now - last_crash_alert[market_type]).total_seconds() / 60
    return elapsed >= Config.CRASH_COOLDOWN_MINUTES


def _send_crash_notifications(crashes, market_label, settings):
    """Send crash alerts via all enabled channels"""
    if settings['email_enabled']:
        try:
            _send_crash_email(crashes, market_label)
        except Exception as e:
            logger.error(f"Failed to send crash email: {e}")

    if settings['telegram_enabled']:
        try:
            _send_crash_telegram(crashes, market_label)
        except Exception as e:
            logger.error(f"Failed to send crash telegram: {e}")

    if settings['discord_enabled']:
        try:
            _send_crash_discord(crashes, market_label)
        except Exception as e:
            logger.error(f"Failed to send crash discord: {e}")


def _send_crash_email(crashes, market_label):
    """Send flash crash alert via email"""
    with get_db_connection() as conn:
        cursor = conn.execute('SELECT email_address FROM notification_settings WHERE id = 1')
        settings = cursor.fetchone()

    if not settings or not settings['email_address']:
        return

    rows = ''
    for c in crashes:
        rows += f'''
        <tr>
            <td style="padding: 10px; border-bottom: 1px solid #eee; font-weight: 700;">{c['symbol']}</td>
            <td style="padding: 10px; border-bottom: 1px solid #eee;">${c['high']:,.2f}</td>
            <td style="padding: 10px; border-bottom: 1px solid #eee;">${c['price']:,.2f}</td>
            <td style="padding: 10px; border-bottom: 1px solid #eee; color: #dc3545; font-weight: 700;">-{c['drop_pct']:.2f}%</td>
        </tr>'''

    html = f'''
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: linear-gradient(135deg, #dc3545 0%, #c0392b 100%); color: white; padding: 25px; border-radius: 10px 10px 0 0;">
            <h1 style="margin: 0; font-size: 22px;">&#9888; Flash Crash Alert</h1>
            <p style="margin: 8px 0 0; opacity: 0.9;">{market_label} — {datetime.now().strftime('%b %d, %Y %I:%M %p')}</p>
        </div>
        <div style="background: #fff; padding: 25px; border: 1px solid #eee; border-radius: 0 0 10px 10px;">
            <p style="color: #333; margin-top: 0;">Rapid price decline detected in the following assets:</p>
            <table style="width: 100%; border-collapse: collapse; margin: 15px 0;">
                <thead>
                    <tr style="background: #f8f9fa;">
                        <th style="padding: 10px; text-align: left;">Asset</th>
                        <th style="padding: 10px; text-align: left;">Day High</th>
                        <th style="padding: 10px; text-align: left;">Current</th>
                        <th style="padding: 10px; text-align: left;">Drop</th>
                    </tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>
            <p style="color: #666; font-size: 13px; margin-bottom: 0;">This is an automated alert from StockPulse flash crash detection.</p>
        </div>
    </div>'''

    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"&#9888; Flash Crash: {market_label} dropping rapidly"
    msg['From'] = Config.SMTP_FROM_EMAIL or Config.SMTP_USERNAME
    msg['To'] = settings['email_address']
    msg.attach(MIMEText(html, 'html'))

    with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT) as server:
        server.starttls()
        server.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)
        server.send_message(msg)

    logger.info("Crash alert email sent")


def _send_crash_telegram(crashes, market_label):
    """Send flash crash alert via Telegram"""
    with get_db_connection() as conn:
        cursor = conn.execute(
            'SELECT telegram_chat_id, telegram_bot_token FROM notification_settings WHERE id = 1'
        )
        settings = cursor.fetchone()

    if not settings or not settings['telegram_chat_id'] or not settings['telegram_bot_token']:
        return

    lines = [f"*{c['symbol']}*: ${c['price']:,.2f} (down {c['drop_pct']:.2f}% from ${c['high']:,.2f})" for c in crashes]
    details = '\n'.join(lines)

    message = (
        f"🚨 *FLASH CRASH ALERT*\n"
        f"_{market_label}_\n\n"
        f"{details}\n\n"
        f"_{datetime.now().strftime('%b %d, %Y %I:%M %p')}_"
    )

    url = f"https://api.telegram.org/bot{settings['telegram_bot_token']}/sendMessage"
    payload = {
        'chat_id': settings['telegram_chat_id'],
        'text': message,
        'parse_mode': 'Markdown'
    }

    response = requests.post(url, json=payload, timeout=10)
    response.raise_for_status()
    logger.info("Crash alert Telegram sent")


def _send_crash_discord(crashes, market_label):
    """Send flash crash alert via Discord webhook"""
    with get_db_connection() as conn:
        cursor = conn.execute('SELECT discord_webhook_url FROM notification_settings WHERE id = 1')
        settings = cursor.fetchone()

    if not settings or not settings['discord_webhook_url']:
        return

    fields = []
    for c in crashes:
        fields.append({
            'name': c['symbol'],
            'value': f"${c['price']:,.2f} (**-{c['drop_pct']:.2f}%** from ${c['high']:,.2f})",
            'inline': True
        })

    embed = {
        'title': f"🚨 Flash Crash Alert — {market_label}",
        'description': 'Rapid price decline detected across monitored assets.',
        'color': 0xdc3545,
        'fields': fields,
        'footer': {
            'text': f"StockPulse Flash Crash Detection • {datetime.now().strftime('%b %d, %Y %I:%M %p')}"
        }
    }

    payload = {'embeds': [embed]}
    response = requests.post(settings['discord_webhook_url'], json=payload, timeout=10)
    response.raise_for_status()
    logger.info("Crash alert Discord sent")
