import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from database import get_db_connection
from config import Config
from predictor import StockPredictor
from stock_data import StockData
from datetime import datetime
import logging
import requests

logger = logging.getLogger(__name__)

WATCHLIST = ['AAPL', 'MSFT', 'MA', 'GLD', 'AMZN', 'GOOGL', 'SPY', 'TSM', 'NVDA']


def generate_daily_report():
    """Analyze all watchlist stocks and send daily report via all channels"""
    try:
        logger.info("Starting daily watchlist report generation")

        with get_db_connection() as conn:
            cursor = conn.execute(
                'SELECT email_enabled, telegram_enabled, discord_enabled FROM notification_settings WHERE id = 1'
            )
            settings = cursor.fetchone()

        if not settings:
            logger.info("No notification settings configured, skipping daily report")
            return

        if not any([settings['email_enabled'], settings['telegram_enabled'], settings['discord_enabled']]):
            logger.info("All notification channels disabled, skipping daily report")
            return

        analyses = []
        for ticker in WATCHLIST:
            try:
                predictor = StockPredictor(ticker)
                prediction = predictor.get_prediction()

                stock = StockData(ticker)
                info = stock.get_stock_info()
                current_price = info.get('current_price', 0) if info else 0
                change_pct = info.get('change_percent', 0) if info else 0

                analyses.append({
                    'ticker': ticker,
                    'name': info.get('name', ticker) if info else ticker,
                    'current_price': current_price,
                    'change_percent': change_pct or 0,
                    'recommendation': prediction.get('recommendation', 'Hold'),
                    'confidence': prediction.get('confidence', 0),
                    'combined_score': prediction.get('combined_score', 0),
                    'summary': prediction.get('summary', ''),
                    'rsi': prediction.get('technical_analysis', {}).get('rsi', {}).get('value', 'N/A'),
                    'rsi_interp': prediction.get('technical_analysis', {}).get('rsi', {}).get('interpretation', ''),
                    'ma_position': prediction.get('technical_analysis', {}).get('ma_trend', {}).get('position', ''),
                    'macd_interp': prediction.get('technical_analysis', {}).get('macd', {}).get('interpretation', ''),
                    'sentiment_pos': prediction.get('sentiment_analysis', {}).get('positive_count', 0),
                    'sentiment_neg': prediction.get('sentiment_analysis', {}).get('negative_count', 0),
                    'sentiment_neu': prediction.get('sentiment_analysis', {}).get('neutral_count', 0),
                    'weekly_direction': prediction.get('seasonal_analysis', {}).get('weekly_trend', {}).get('direction', 'flat'),
                })
                logger.info(f"Analyzed {ticker}: {prediction.get('recommendation', 'Hold')}")
            except Exception as e:
                logger.error(f"Failed to analyze {ticker}: {e}")
                analyses.append({
                    'ticker': ticker,
                    'name': ticker,
                    'current_price': 0,
                    'change_percent': 0,
                    'recommendation': 'N/A',
                    'confidence': 0,
                    'combined_score': 0,
                    'summary': 'Analysis unavailable',
                    'rsi': 'N/A',
                    'rsi_interp': '',
                    'ma_position': '',
                    'macd_interp': '',
                    'sentiment_pos': 0,
                    'sentiment_neg': 0,
                    'sentiment_neu': 0,
                    'weekly_direction': 'flat',
                })

        bullish = [a for a in analyses if a['recommendation'] == 'Buy']
        bearish = [a for a in analyses if a['recommendation'] == 'Sell']
        neutral = [a for a in analyses if a['recommendation'] == 'Hold']
        failed = [a for a in analyses if a['recommendation'] == 'N/A']

        if settings['email_enabled']:
            try:
                success, error = send_daily_email(analyses, bullish, bearish, neutral)
                if success:
                    logger.info("Daily report email sent")
                else:
                    logger.error(f"Daily report email failed: {error}")
            except Exception as e:
                logger.error(f"Daily report email exception: {e}")

        if settings['telegram_enabled']:
            try:
                success, error = send_daily_telegram(analyses, bullish, bearish, neutral)
                if success:
                    logger.info("Daily report Telegram sent")
                else:
                    logger.error(f"Daily report Telegram failed: {error}")
            except Exception as e:
                logger.error(f"Daily report Telegram exception: {e}")

        if settings['discord_enabled']:
            try:
                success, error = send_daily_discord(analyses, bullish, bearish, neutral)
                if success:
                    logger.info("Daily report Discord sent")
                else:
                    logger.error(f"Daily report Discord failed: {error}")
            except Exception as e:
                logger.error(f"Daily report Discord exception: {e}")

        logger.info("Daily watchlist report complete")

    except Exception as e:
        logger.critical(f"Daily report generation crashed: {e}", exc_info=True)


def send_daily_email(analyses, bullish, bearish, neutral):
    """Send daily watchlist report via email"""
    try:
        with get_db_connection() as conn:
            cursor = conn.execute(
                'SELECT email_enabled, email_address FROM notification_settings WHERE id = 1'
            )
            settings = cursor.fetchone()

        if not settings or not settings['email_enabled'] or not settings['email_address']:
            return False, "Email not configured"

        if not all([Config.SMTP_HOST, Config.SMTP_USERNAME, Config.SMTP_PASSWORD]):
            return False, "SMTP credentials not configured"

        today = datetime.now().strftime('%B %d, %Y')
        subject = f"StockPulse Daily Report - {today}"

        # Build stock rows
        stock_rows = ""
        for a in analyses:
            if a['recommendation'] == 'Buy':
                rec_color = '#28a745'
                rec_bg = '#d4edda'
            elif a['recommendation'] == 'Sell':
                rec_color = '#dc3545'
                rec_bg = '#f8d7da'
            elif a['recommendation'] == 'N/A':
                rec_color = '#6c757d'
                rec_bg = '#e9ecef'
            else:
                rec_color = '#856404'
                rec_bg = '#fff3cd'

            change_color = '#28a745' if a['change_percent'] >= 0 else '#dc3545'
            change_sign = '+' if a['change_percent'] >= 0 else ''

            stock_rows += f"""
            <tr>
                <td style="padding: 12px; border-bottom: 1px solid #eee; font-weight: 600;">{a['ticker']}</td>
                <td style="padding: 12px; border-bottom: 1px solid #eee;">${a['current_price']:.2f}</td>
                <td style="padding: 12px; border-bottom: 1px solid #eee; color: {change_color};">{change_sign}{a['change_percent']:.2f}%</td>
                <td style="padding: 12px; border-bottom: 1px solid #eee;">
                    <span style="background: {rec_bg}; color: {rec_color}; padding: 4px 12px; border-radius: 12px; font-weight: 600; font-size: 13px;">
                        {a['recommendation']}
                    </span>
                </td>
                <td style="padding: 12px; border-bottom: 1px solid #eee;">{a['confidence']}%</td>
                <td style="padding: 12px; border-bottom: 1px solid #eee;">RSI: {a['rsi']} | {a['ma_position']}</td>
            </tr>
            """

        # Summary counts
        summary_text = f"{len(bullish)} Bullish, {len(bearish)} Bearish, {len(neutral)} Neutral"

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 700px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 12px 12px 0 0;">
                <h1 style="color: white; margin: 0;">StockPulse Daily Report</h1>
                <p style="color: rgba(255,255,255,0.8); margin: 8px 0 0 0;">{today}</p>
            </div>

            <div style="background: #f8f9fa; padding: 20px; border-left: 1px solid #eee; border-right: 1px solid #eee;">
                <h3 style="margin: 0 0 10px 0; color: #333;">Market Overview</h3>
                <p style="margin: 0; font-size: 16px; color: #555;">{summary_text}</p>
            </div>

            <div style="padding: 0; border: 1px solid #eee; border-top: none;">
                <table style="width: 100%; border-collapse: collapse;">
                    <thead>
                        <tr style="background: #f1f3f5;">
                            <th style="padding: 12px; text-align: left; color: #555; font-size: 13px;">TICKER</th>
                            <th style="padding: 12px; text-align: left; color: #555; font-size: 13px;">PRICE</th>
                            <th style="padding: 12px; text-align: left; color: #555; font-size: 13px;">CHANGE</th>
                            <th style="padding: 12px; text-align: left; color: #555; font-size: 13px;">SIGNAL</th>
                            <th style="padding: 12px; text-align: left; color: #555; font-size: 13px;">CONF.</th>
                            <th style="padding: 12px; text-align: left; color: #555; font-size: 13px;">DETAILS</th>
                        </tr>
                    </thead>
                    <tbody>
                        {stock_rows}
                    </tbody>
                </table>
            </div>

            <div style="padding: 20px; border: 1px solid #eee; border-top: none; border-radius: 0 0 12px 12px;">
                <p style="font-size: 12px; color: #999; margin: 0; text-align: center;">
                    This is a statistical analysis for educational purposes only.
                    Not financial advice. Past performance does not guarantee future results.
                </p>
            </div>
        </body>
        </html>
        """

        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = Config.SMTP_FROM_EMAIL or Config.SMTP_USERNAME
        msg['To'] = settings['email_address']
        msg.attach(MIMEText(html_body, 'html'))

        with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT) as server:
            server.starttls()
            server.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)
            server.send_message(msg)

        return True, None

    except Exception as e:
        return False, str(e)


def send_daily_telegram(analyses, bullish, bearish, neutral):
    """Send daily watchlist report via Telegram"""
    try:
        with get_db_connection() as conn:
            cursor = conn.execute(
                'SELECT telegram_enabled, telegram_chat_id, telegram_bot_token FROM notification_settings WHERE id = 1'
            )
            settings = cursor.fetchone()

        if not settings or not settings['telegram_enabled']:
            return False, "Telegram not configured"
        if not settings['telegram_chat_id'] or not settings['telegram_bot_token']:
            return False, "Telegram credentials missing"

        today = datetime.now().strftime('%B %d, %Y')

        msg = f"*StockPulse Daily Report*\n_{today}_\n\n"
        msg += f"*Summary:* {len(bullish)} Bullish | {len(bearish)} Bearish | {len(neutral)} Neutral\n"
        msg += "─────────────────\n\n"

        for a in analyses:
            if a['recommendation'] == 'Buy':
                icon = "🟢"
            elif a['recommendation'] == 'Sell':
                icon = "🔴"
            elif a['recommendation'] == 'N/A':
                icon = "⚪"
            else:
                icon = "🟡"

            change_sign = '+' if a['change_percent'] >= 0 else ''
            msg += f"{icon} *{a['ticker']}* — {a['recommendation']} ({a['confidence']}%)\n"
            msg += f"   ${a['current_price']:.2f} ({change_sign}{a['change_percent']:.2f}%)\n"
            msg += f"   RSI: {a['rsi']} | {a['ma_position']}\n"
            msg += f"   MACD: {a['macd_interp']} | Trend: {a['weekly_direction'].title()}\n\n"

        msg += "_Statistical analysis for educational purposes only. Not financial advice._"

        url = f"https://api.telegram.org/bot{settings['telegram_bot_token']}/sendMessage"
        payload = {
            'chat_id': settings['telegram_chat_id'],
            'text': msg,
            'parse_mode': 'Markdown'
        }

        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()

        return True, None

    except Exception as e:
        return False, str(e)


def send_daily_discord(analyses, bullish, bearish, neutral):
    """Send daily watchlist report via Discord webhook"""
    try:
        with get_db_connection() as conn:
            cursor = conn.execute(
                'SELECT discord_enabled, discord_webhook_url FROM notification_settings WHERE id = 1'
            )
            settings = cursor.fetchone()

        if not settings or not settings['discord_enabled']:
            return False, "Discord not configured"
        if not settings['discord_webhook_url']:
            return False, "Discord webhook missing"

        today = datetime.now().strftime('%B %d, %Y')

        # Build stock fields
        fields = []
        for a in analyses:
            if a['recommendation'] == 'Buy':
                icon = "🟢"
            elif a['recommendation'] == 'Sell':
                icon = "🔴"
            elif a['recommendation'] == 'N/A':
                icon = "⚪"
            else:
                icon = "🟡"

            change_sign = '+' if a['change_percent'] >= 0 else ''
            fields.append({
                "name": f"{icon} {a['ticker']} — {a['recommendation']}",
                "value": (
                    f"**${a['current_price']:.2f}** ({change_sign}{a['change_percent']:.2f}%)\n"
                    f"Confidence: {a['confidence']}% | RSI: {a['rsi']}\n"
                    f"{a['ma_position']} | MACD: {a['macd_interp']}"
                ),
                "inline": True
            })

        # Determine overall color
        if len(bullish) > len(bearish):
            color = 0x28a745
        elif len(bearish) > len(bullish):
            color = 0xdc3545
        else:
            color = 0xffc107

        embed = {
            "title": f"StockPulse Daily Report — {today}",
            "description": f"**{len(bullish)}** Bullish | **{len(bearish)}** Bearish | **{len(neutral)}** Neutral",
            "color": color,
            "fields": fields,
            "footer": {
                "text": "Statistical analysis for educational purposes only. Not financial advice."
            }
        }

        payload = {"embeds": [embed]}

        response = requests.post(settings['discord_webhook_url'], json=payload, timeout=30)
        response.raise_for_status()

        return True, None

    except Exception as e:
        return False, str(e)
