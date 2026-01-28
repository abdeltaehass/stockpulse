import sqlite3
from contextlib import contextmanager
from datetime import datetime

DATABASE_PATH = 'stockpulse.db'

@contextmanager
def get_db_connection():
    """Context manager for database connections"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def init_db():
    """Initialize database schema"""
    with get_db_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS portfolio_holdings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker VARCHAR(10) NOT NULL,
                quantity REAL NOT NULL,
                purchase_price REAL NOT NULL,
                purchase_date TEXT NOT NULL,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                CHECK (quantity > 0),
                CHECK (purchase_price > 0)
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS price_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker VARCHAR(10) NOT NULL,
                alert_type VARCHAR(20) NOT NULL,
                target_value REAL NOT NULL,
                baseline_price REAL,
                is_active INTEGER DEFAULT 1,
                notify_email INTEGER DEFAULT 0,
                notify_telegram INTEGER DEFAULT 0,
                notify_discord INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                triggered_at TEXT,
                notes TEXT,
                CHECK (alert_type IN ('above', 'below', 'percentage'))
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS alert_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id INTEGER NOT NULL,
                ticker VARCHAR(10) NOT NULL,
                alert_type VARCHAR(20) NOT NULL,
                target_value REAL NOT NULL,
                trigger_price REAL NOT NULL,
                triggered_at TEXT DEFAULT CURRENT_TIMESTAMP,
                email_sent INTEGER DEFAULT 0,
                telegram_sent INTEGER DEFAULT 0,
                discord_sent INTEGER DEFAULT 0,
                email_error TEXT,
                telegram_error TEXT,
                discord_error TEXT,
                FOREIGN KEY (alert_id) REFERENCES price_alerts(id) ON DELETE CASCADE
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS notification_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                email_enabled INTEGER DEFAULT 0,
                email_address TEXT,
                telegram_enabled INTEGER DEFAULT 0,
                telegram_chat_id TEXT,
                telegram_bot_token TEXT,
                discord_enabled INTEGER DEFAULT 0,
                discord_webhook_url TEXT,
                daily_report_enabled INTEGER DEFAULT 0,
                daily_report_time TEXT DEFAULT '08:00',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Add daily report columns if they don't exist (migration for existing databases)
        try:
            conn.execute('ALTER TABLE notification_settings ADD COLUMN daily_report_enabled INTEGER DEFAULT 0')
        except:
            pass
        try:
            conn.execute("ALTER TABLE notification_settings ADD COLUMN daily_report_time TEXT DEFAULT '08:00'")
        except:
            pass
