import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Flask settings
    DEBUG = os.getenv('FLASK_DEBUG', 'True') == 'True'
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

    # Database
    DATABASE_PATH = 'stockpulse.db'

    # Scheduler
    SCHEDULER_API_ENABLED = False

    # Email settings (SMTP)
    SMTP_HOST = os.getenv('SMTP_HOST', 'smtp.gmail.com')
    SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
    SMTP_USERNAME = os.getenv('SMTP_USERNAME')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
    SMTP_FROM_EMAIL = os.getenv('SMTP_FROM_EMAIL')

    # Telegram settings
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

    # Discord settings
    DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')

    # Alpaca Trading API
    ALPACA_API_KEY = os.getenv('ALPACA_API_KEY')
    ALPACA_SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')
    ALPACA_BASE_URL = os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')
    ALPACA_PAPER = os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets').startswith('https://paper')

    # Binance Trading API
    BINANCE_API_KEY = os.getenv('BINANCE_API_KEY')
    BINANCE_SECRET_KEY = os.getenv('BINANCE_SECRET_KEY')

    # Telegram Trading Bot
    TELEGRAM_TRADING_ENABLED = os.getenv('TELEGRAM_TRADING_ENABLED', 'True') == 'True'

    # Alert settings
    ALERT_CHECK_INTERVAL = int(os.getenv('ALERT_CHECK_INTERVAL', '5'))
    ALERT_COOLDOWN_HOURS = int(os.getenv('ALERT_COOLDOWN_HOURS', '1'))

    # Daily report settings
    DAILY_REPORT_DEFAULT_TIME = os.getenv('DAILY_REPORT_TIME', '08:00')

    # Flash crash detection settings
    CRASH_CHECK_INTERVAL = int(os.getenv('CRASH_CHECK_INTERVAL', '2'))
    CRASH_STOCK_THRESHOLD = float(os.getenv('CRASH_STOCK_THRESHOLD', '3.0'))
    CRASH_CRYPTO_THRESHOLD = float(os.getenv('CRASH_CRYPTO_THRESHOLD', '5.0'))
    CRASH_COOLDOWN_MINUTES = int(os.getenv('CRASH_COOLDOWN_MINUTES', '30'))
