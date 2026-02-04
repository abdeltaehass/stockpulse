from flask import Flask, render_template, jsonify, request
from stock_data import StockData
from portfolio import Portfolio
from predictor import StockPredictor
from database import init_db, get_db_connection
from scheduler import start_scheduler, reschedule_daily_report
from notifications import send_email_notification, send_telegram_notification, send_discord_notification
from config import Config
from datetime import datetime
import logging

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)

# Initialize database on startup
init_db()

# Reactivate all alerts on startup
def reactivate_all_alerts():
    with get_db_connection() as conn:
        conn.execute('UPDATE price_alerts SET is_active = 1')
    logging.info("All alerts reactivated on startup")

reactivate_all_alerts()

# Start background scheduler for price alerts
start_scheduler()

# Start Telegram trading bot
if Config.TELEGRAM_TRADING_ENABLED and Config.TELEGRAM_BOT_TOKEN:
    from telegram_bot import start_telegram_bot
    start_telegram_bot()

def get_watchlist():
    """Read watchlist tickers from the database"""
    with get_db_connection() as conn:
        cursor = conn.execute('SELECT ticker FROM watchlist ORDER BY added_at')
        return [row['ticker'] for row in cursor.fetchall()]

TOP_CRYPTO_TICKERS = [
    'BTC-USD', 'ETH-USD', 'BNB-USD', 'SOL-USD', 'XRP-USD',
    'ADA-USD', 'DOGE-USD', 'AVAX-USD', 'DOT-USD', 'MATIC-USD',
    'LINK-USD', 'SHIB-USD', 'LTC-USD', 'UNI-USD', 'ATOM-USD',
    'XLM-USD', 'ALGO-USD', 'NEAR-USD', 'FTM-USD', 'AAVE-USD'
]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/stocks')
def get_stocks():
    stocks_data = []

    for ticker in get_watchlist():
        stock = StockData(ticker)
        info = stock.get_stock_info()
        if info:
            info['weekly_change'] = stock.get_weekly_change()
            stocks_data.append(info)

    return jsonify({
        'stocks': stocks_data,
        'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/api/stocks/top-movers')
def get_top_movers():
    """Get top 10 gainers and losers for the day"""
    try:
        popular_tickers = [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'BRK-B', 'JPM', 'V',
            'JNJ', 'WMT', 'PG', 'MA', 'HD', 'CVX', 'MRK', 'ABBV', 'PFE', 'KO',
            'PEP', 'COST', 'TMO', 'AVGO', 'MCD', 'CSCO', 'ACN', 'ABT', 'DHR', 'NKE',
            'AMD', 'INTC', 'QCOM', 'TXN', 'ORCL', 'CRM', 'ADBE', 'NFLX', 'PYPL', 'DIS'
        ]

        stocks_data = []
        for ticker in popular_tickers:
            try:
                stock = StockData(ticker)
                info = stock.get_stock_info()
                if info and info.get('change_percent') is not None:
                    stocks_data.append(info)
            except:
                continue

        gainers = sorted([s for s in stocks_data if s.get('change_percent', 0) > 0],
                        key=lambda x: x.get('change_percent', 0), reverse=True)[:10]

        losers = sorted([s for s in stocks_data if s.get('change_percent', 0) < 0],
                       key=lambda x: x.get('change_percent', 0))[:10]

        return jsonify({
            'gainers': gainers,
            'losers': losers,
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stocks/search')
def search_stock():
    """Search for a stock by ticker or name"""
    try:
        query = request.args.get('q', '').strip().upper()
        if not query:
            return jsonify({'error': 'Search query required'}), 400

        stock = StockData(query)
        info = stock.get_stock_info()

        if info and info.get('current_price'):
            info['weekly_change'] = stock.get_weekly_change()
            return jsonify({
                'found': True,
                'stock': info,
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
        else:
            return jsonify({
                'found': False,
                'message': f'No stock found for "{query}"'
            })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stocks/<ticker>/prediction')
def get_stock_prediction(ticker):
    try:
        predictor = StockPredictor(ticker.upper())
        prediction = predictor.get_prediction()
        return jsonify({
            'prediction': prediction,
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stocks/<ticker>/history/<period>')
def get_stock_history(ticker, period):
    valid_periods = ['1d', '1wk', '1mo', '1y']
    if period not in valid_periods:
        return jsonify({'error': 'Invalid period'}), 400

    interval = request.args.get('interval', None)
    valid_intervals = ['5m', '15m', '30m', '1h', '3h']
    if period == '1d' and interval and interval not in valid_intervals:
        return jsonify({'error': f'Invalid interval. Use: {", ".join(valid_intervals)}'}), 400

    stock = StockData(ticker)
    historical_data = stock.get_historical_data(period=period, interval=interval)

    if historical_data is None or historical_data.empty:
        return jsonify({'error': 'No data available'}), 404

    # Convert historical data to lists for JSON response
    labels = historical_data.index.strftime('%Y-%m-%d %H:%M').tolist()
    close_prices = historical_data['Close'].round(2).tolist()
    open_prices = historical_data['Open'].round(2).tolist()
    high_prices = historical_data['High'].round(2).tolist()
    low_prices = historical_data['Low'].round(2).tolist()
    volumes = historical_data['Volume'].tolist()

    # Calculate period statistics
    high = float(historical_data['High'].max())
    low = float(historical_data['Low'].min())
    avg = float(historical_data['Close'].mean())
    period_change = ((close_prices[-1] - close_prices[0]) / close_prices[0]) * 100

    # Convert NaN values to null for JSON compatibility
    import math

    def nan_to_none(value):
        return None if (isinstance(value, float) and math.isnan(value)) else value

    ma_20_raw = historical_data['Close'].rolling(window=min(20, len(historical_data))).mean().round(2).tolist()
    ma_50_raw = historical_data['Close'].rolling(window=min(50, len(historical_data))).mean().round(2).tolist()
    ma_200_raw = historical_data['Close'].rolling(window=min(200, len(historical_data))).mean().round(2).tolist()

    ma_20 = [nan_to_none(v) for v in ma_20_raw]
    ma_50 = [nan_to_none(v) for v in ma_50_raw]
    ma_200 = [nan_to_none(v) for v in ma_200_raw]

    return jsonify({
        'ticker': ticker.upper(),
        'period': period,
        'data': {
            'labels': labels,
            'prices': close_prices,
            'open': open_prices,
            'high': high_prices,
            'low': low_prices,
            'volume': volumes,
            'ma_20': ma_20,
            'ma_50': ma_50,
            'ma_200': ma_200
        },
        'statistics': {
            'high': round(high, 2),
            'low': round(low, 2),
            'avg': round(avg, 2),
            'period_change': round(period_change, 2),
            'start_price': close_prices[0],
            'end_price': close_prices[-1]
        }
    })

@app.route('/api/news')
def get_news():
    """Get news for all watchlist stocks or a specific ticker"""
    try:
        ticker = request.args.get('ticker', None)
        limit = request.args.get('limit', 5, type=int)
        sentiment_filter = request.args.get('sentiment', None)

        all_news = []

        if ticker:
            tickers = [ticker.upper()]
        else:
            tickers = get_watchlist()

        for t in tickers:
            stock = StockData(t)
            news = stock.get_news(limit=limit)
            for article in news:
                article['ticker'] = t
            all_news.extend(news)

        all_news.sort(key=lambda x: x['published'], reverse=True)

        if sentiment_filter and sentiment_filter in ['positive', 'negative', 'neutral']:
            all_news = [n for n in all_news if n['sentiment'] == sentiment_filter]

        return jsonify({
            'news': all_news,
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/portfolio/holdings', methods=['GET'])
def get_portfolio_holdings():
    """Get all portfolio holdings with P&L"""
    try:
        holdings = Portfolio.get_holdings_with_pnl()
        summary = Portfolio.calculate_portfolio_summary()

        return jsonify({
            'holdings': holdings,
            'summary': summary,
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/portfolio/holdings', methods=['POST'])
def add_portfolio_holding():
    """Add a new portfolio holding"""
    try:
        data = request.get_json()

        # Validate required fields
        required_fields = ['ticker', 'quantity', 'purchase_price', 'purchase_date']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400

        # Validate data types and values
        quantity = float(data['quantity'])
        purchase_price = float(data['purchase_price'])

        if quantity <= 0:
            return jsonify({'error': 'Quantity must be positive'}), 400
        if purchase_price <= 0:
            return jsonify({'error': 'Purchase price must be positive'}), 400

        # Add holding
        Portfolio.add_holding(
            ticker=data['ticker'],
            quantity=quantity,
            purchase_price=purchase_price,
            purchase_date=data['purchase_date'],
            notes=data.get('notes', '')
        )

        return jsonify({'success': True, 'message': 'Holding added successfully'}), 201

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/portfolio/holdings/<int:holding_id>', methods=['PUT'])
def update_portfolio_holding(holding_id):
    """Update an existing portfolio holding"""
    try:
        data = request.get_json()

        # Validate required fields
        required_fields = ['quantity', 'purchase_price', 'purchase_date']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400

        quantity = float(data['quantity'])
        purchase_price = float(data['purchase_price'])

        if quantity <= 0:
            return jsonify({'error': 'Quantity must be positive'}), 400
        if purchase_price <= 0:
            return jsonify({'error': 'Purchase price must be positive'}), 400

        Portfolio.update_holding(
            holding_id=holding_id,
            quantity=quantity,
            purchase_price=purchase_price,
            purchase_date=data['purchase_date'],
            notes=data.get('notes', '')
        )

        return jsonify({'success': True, 'message': 'Holding updated successfully'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/portfolio/holdings/<int:holding_id>', methods=['DELETE'])
def delete_portfolio_holding(holding_id):
    """Delete a portfolio holding"""
    try:
        Portfolio.delete_holding(holding_id)
        return jsonify({'success': True, 'message': 'Holding deleted successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/portfolio/performance', methods=['GET'])
def get_portfolio_performance():
    """Get portfolio performance metrics"""
    try:
        metrics = Portfolio.get_performance_metrics()
        return jsonify({
            'metrics': metrics,
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============ PRICE ALERTS API ============

@app.route('/api/alerts', methods=['POST'])
def create_alert():
    """Create a new price alert"""
    try:
        data = request.get_json()

        # Validate required fields
        required_fields = ['ticker', 'alert_type', 'target_value']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400

        ticker = data['ticker'].upper()
        alert_type = data['alert_type']
        target_value = float(data['target_value'])

        # Validate alert type
        if alert_type not in ['above', 'below', 'percentage']:
            return jsonify({'error': 'Invalid alert type'}), 400

        # Validate ticker by getting current price
        stock = StockData(ticker)
        current_price = stock.get_current_price()
        if current_price is None:
            return jsonify({'error': f'Invalid ticker: {ticker}'}), 400

        # For percentage alerts, store baseline price
        baseline_price = current_price if alert_type == 'percentage' else None

        # Validate target value
        if alert_type in ['above', 'below'] and target_value <= 0:
            return jsonify({'error': 'Target price must be positive'}), 400

        # Insert alert into database
        with get_db_connection() as conn:
            cursor = conn.execute('''
                INSERT INTO price_alerts
                (ticker, alert_type, target_value, baseline_price,
                 notify_email, notify_telegram, notify_discord, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                ticker,
                alert_type,
                target_value,
                baseline_price,
                data.get('notify_email', 1),
                data.get('notify_telegram', 0),
                data.get('notify_discord', 0),
                data.get('notes', '')
            ))
            alert_id = cursor.lastrowid

        return jsonify({
            'success': True,
            'message': 'Alert created successfully',
            'alert_id': alert_id,
            'current_price': current_price
        }), 201

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    """Get all price alerts"""
    try:
        with get_db_connection() as conn:
            cursor = conn.execute('''
                SELECT id, ticker, alert_type, target_value, baseline_price,
                       is_active, notify_email, notify_telegram, notify_discord,
                       created_at, triggered_at, notes
                FROM price_alerts
                ORDER BY created_at DESC
            ''')
            alerts = [dict(row) for row in cursor.fetchall()]

        # Get current prices for active alerts
        for alert in alerts:
            if alert['is_active']:
                try:
                    stock = StockData(alert['ticker'])
                    alert['current_price'] = stock.get_current_price()
                except:
                    alert['current_price'] = None
            else:
                alert['current_price'] = None

        return jsonify({
            'alerts': alerts,
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/alerts/<int:alert_id>', methods=['PUT'])
def update_alert(alert_id):
    """Update an existing price alert"""
    try:
        data = request.get_json()

        # Build update query dynamically based on provided fields
        update_fields = []
        values = []

        if 'alert_type' in data:
            if data['alert_type'] not in ['above', 'below', 'percentage']:
                return jsonify({'error': 'Invalid alert type'}), 400
            update_fields.append('alert_type = ?')
            values.append(data['alert_type'])

            # If switching to percentage, recalculate baseline_price
            if data['alert_type'] == 'percentage':
                with get_db_connection() as conn:
                    cursor = conn.execute('SELECT ticker FROM price_alerts WHERE id = ?', (alert_id,))
                    alert_row = cursor.fetchone()
                if alert_row:
                    stock = StockData(alert_row['ticker'])
                    current_price = stock.get_current_price()
                    if current_price:
                        update_fields.append('baseline_price = ?')
                        values.append(current_price)

        if 'target_value' in data:
            update_fields.append('target_value = ?')
            values.append(float(data['target_value']))

        if 'is_active' in data:
            update_fields.append('is_active = ?')
            values.append(int(data['is_active']))

        if 'notify_email' in data:
            update_fields.append('notify_email = ?')
            values.append(int(data['notify_email']))

        if 'notify_telegram' in data:
            update_fields.append('notify_telegram = ?')
            values.append(int(data['notify_telegram']))

        if 'notify_discord' in data:
            update_fields.append('notify_discord = ?')
            values.append(int(data['notify_discord']))

        if 'notes' in data:
            update_fields.append('notes = ?')
            values.append(data['notes'])

        if not update_fields:
            return jsonify({'error': 'No fields to update'}), 400

        values.append(alert_id)

        with get_db_connection() as conn:
            conn.execute(f'''
                UPDATE price_alerts
                SET {', '.join(update_fields)}
                WHERE id = ?
            ''', values)

        return jsonify({'success': True, 'message': 'Alert updated successfully'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/alerts/<int:alert_id>', methods=['DELETE'])
def delete_alert(alert_id):
    """Delete a price alert"""
    try:
        with get_db_connection() as conn:
            conn.execute('DELETE FROM price_alerts WHERE id = ?', (alert_id,))

        return jsonify({'success': True, 'message': 'Alert deleted successfully'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/alerts/history', methods=['GET'])
def get_alert_history():
    """Get alert trigger history"""
    try:
        limit = request.args.get('limit', 100, type=int)

        with get_db_connection() as conn:
            cursor = conn.execute('''
                SELECT id, alert_id, ticker, alert_type, target_value,
                       trigger_price, triggered_at, email_sent, telegram_sent, discord_sent,
                       email_error, telegram_error, discord_error
                FROM alert_history
                ORDER BY triggered_at DESC
                LIMIT ?
            ''', (limit,))
            history = [dict(row) for row in cursor.fetchall()]

        return jsonify({
            'history': history,
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============ WATCHLIST API ============

@app.route('/api/watchlist', methods=['GET'])
def get_watchlist_api():
    """Get all watchlist tickers"""
    try:
        tickers = get_watchlist()
        return jsonify({'watchlist': tickers})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/watchlist', methods=['POST'])
def add_to_watchlist():
    """Add a stock to the watchlist"""
    try:
        data = request.get_json()
        ticker = data.get('ticker', '').strip().upper()

        if not ticker:
            return jsonify({'error': 'Ticker is required'}), 400

        # Check if already in watchlist
        with get_db_connection() as conn:
            cursor = conn.execute('SELECT id FROM watchlist WHERE ticker = ?', (ticker,))
            if cursor.fetchone():
                return jsonify({'error': f'{ticker} is already in your watchlist'}), 409

        # Validate ticker by fetching price
        stock = StockData(ticker)
        price = stock.get_current_price()
        if price is None:
            return jsonify({'error': f'Invalid ticker: {ticker}'}), 400

        with get_db_connection() as conn:
            conn.execute('INSERT INTO watchlist (ticker) VALUES (?)', (ticker,))

        return jsonify({'success': True, 'message': f'{ticker} added to watchlist'}), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/watchlist/<ticker>', methods=['DELETE'])
def remove_from_watchlist(ticker):
    """Remove a stock from the watchlist"""
    try:
        ticker = ticker.upper()

        with get_db_connection() as conn:
            cursor = conn.execute('SELECT id FROM watchlist WHERE ticker = ?', (ticker,))
            if not cursor.fetchone():
                return jsonify({'error': f'{ticker} is not in your watchlist'}), 404

            conn.execute('DELETE FROM watchlist WHERE ticker = ?', (ticker,))

        return jsonify({'success': True, 'message': f'{ticker} removed from watchlist'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============ CRYPTO API ============

@app.route('/api/crypto/market')
def get_crypto_market():
    """Get market data for top cryptocurrencies"""
    try:
        crypto_data = []
        for ticker in TOP_CRYPTO_TICKERS:
            try:
                stock = StockData(ticker)
                info = stock.get_crypto_info()
                if info and info.get('current_price'):
                    crypto_data.append(info)
            except:
                continue

        crypto_data.sort(
            key=lambda x: x.get('market_cap') or 0,
            reverse=True
        )

        return jsonify({
            'cryptos': crypto_data,
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/crypto/news')
def get_crypto_news():
    """Get news for top cryptocurrencies"""
    try:
        ticker = request.args.get('ticker', None)
        limit = request.args.get('limit', 5, type=int)
        sentiment_filter = request.args.get('sentiment', None)

        all_news = []

        if ticker:
            tickers = [ticker.upper()]
        else:
            tickers = TOP_CRYPTO_TICKERS[:5]

        for t in tickers:
            stock = StockData(t)
            news = stock.get_news(limit=limit)
            for article in news:
                article['ticker'] = t.replace('-USD', '')
            all_news.extend(news)

        all_news.sort(key=lambda x: x['published'], reverse=True)

        if sentiment_filter and sentiment_filter in ['positive', 'negative', 'neutral']:
            all_news = [n for n in all_news if n['sentiment'] == sentiment_filter]

        return jsonify({
            'news': all_news,
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/crypto/search')
def search_crypto():
    """Search for a cryptocurrency by ticker"""
    try:
        query = request.args.get('q', '').strip().upper()
        if not query:
            return jsonify({'error': 'Search query required'}), 400

        if not query.endswith('-USD'):
            ticker = query + '-USD'
        else:
            ticker = query

        stock = StockData(ticker)
        info = stock.get_crypto_info()

        if info and info.get('current_price'):
            return jsonify({
                'found': True,
                'crypto': info,
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
        else:
            return jsonify({
                'found': False,
                'message': f'No cryptocurrency found for "{query}"'
            })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/notifications/settings', methods=['GET'])
def get_notification_settings():
    """Get notification preferences"""
    try:
        with get_db_connection() as conn:
            cursor = conn.execute('''
                SELECT email_enabled, email_address, telegram_enabled,
                       telegram_chat_id, telegram_bot_token, discord_enabled, discord_webhook_url,
                       daily_report_enabled, daily_report_time,
                       crash_detection_enabled, crash_stock_threshold, crash_crypto_threshold
                FROM notification_settings
                WHERE id = 1
            ''')
            settings = cursor.fetchone()

            if settings:
                return jsonify(dict(settings))
            else:
                return jsonify({
                    'email_enabled': 0,
                    'email_address': '',
                    'telegram_enabled': 0,
                    'telegram_chat_id': '',
                    'telegram_bot_token': '',
                    'discord_enabled': 0,
                    'discord_webhook_url': '',
                    'daily_report_enabled': 0,
                    'daily_report_time': '08:00',
                    'crash_detection_enabled': 0,
                    'crash_stock_threshold': 3.0,
                    'crash_crypto_threshold': 5.0
                })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/notifications/settings', methods=['PUT'])
def update_notification_settings():
    """Update notification preferences"""
    try:
        data = request.get_json()

        with get_db_connection() as conn:
            # Check if settings exist
            cursor = conn.execute('SELECT id FROM notification_settings WHERE id = 1')
            exists = cursor.fetchone()

            if exists:
                conn.execute('''
                    UPDATE notification_settings
                    SET email_enabled = ?, email_address = ?,
                        telegram_enabled = ?, telegram_chat_id = ?, telegram_bot_token = ?,
                        discord_enabled = ?, discord_webhook_url = ?,
                        daily_report_enabled = ?, daily_report_time = ?,
                        crash_detection_enabled = ?, crash_stock_threshold = ?, crash_crypto_threshold = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                ''', (
                    data.get('email_enabled', 0),
                    data.get('email_address', ''),
                    data.get('telegram_enabled', 0),
                    data.get('telegram_chat_id', ''),
                    data.get('telegram_bot_token', ''),
                    data.get('discord_enabled', 0),
                    data.get('discord_webhook_url', ''),
                    data.get('daily_report_enabled', 0),
                    data.get('daily_report_time', '08:00'),
                    data.get('crash_detection_enabled', 0),
                    data.get('crash_stock_threshold', 3.0),
                    data.get('crash_crypto_threshold', 5.0)
                ))
            else:
                conn.execute('''
                    INSERT INTO notification_settings
                    (id, email_enabled, email_address, telegram_enabled, telegram_chat_id,
                     telegram_bot_token, discord_enabled, discord_webhook_url,
                     daily_report_enabled, daily_report_time,
                     crash_detection_enabled, crash_stock_threshold, crash_crypto_threshold)
                    VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    data.get('email_enabled', 0),
                    data.get('email_address', ''),
                    data.get('telegram_enabled', 0),
                    data.get('telegram_chat_id', ''),
                    data.get('telegram_bot_token', ''),
                    data.get('discord_enabled', 0),
                    data.get('discord_webhook_url', ''),
                    data.get('daily_report_enabled', 0),
                    data.get('daily_report_time', '08:00'),
                    data.get('crash_detection_enabled', 0),
                    data.get('crash_stock_threshold', 3.0),
                    data.get('crash_crypto_threshold', 5.0)
                ))

        try:
            reschedule_daily_report()
        except Exception:
            pass

        return jsonify({'success': True, 'message': 'Settings updated successfully'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/notifications/test', methods=['POST'])
def test_notification():
    """Send a test notification"""
    try:
        data = request.get_json()
        channel = data.get('channel', 'email')

        if channel not in ['email', 'telegram', 'discord']:
            return jsonify({'error': 'Invalid channel'}), 400

        # Test with dummy alert data
        test_ticker = 'AAPL'
        test_price = 150.00

        if channel == 'email':
            success, error = send_email_notification(
                test_ticker, 'above', 150.00, test_price
            )
            if success:
                return jsonify({'success': True, 'message': 'Test email sent successfully'})
            else:
                return jsonify({'success': False, 'error': error}), 500

        elif channel == 'telegram':
            success, error = send_telegram_notification(
                test_ticker, 'above', 150.00, test_price
            )
            if success:
                return jsonify({'success': True, 'message': 'Test Telegram message sent successfully'})
            else:
                return jsonify({'success': False, 'error': error}), 500

        elif channel == 'discord':
            success, error = send_discord_notification(
                test_ticker, 'above', 150.00, test_price
            )
            if success:
                return jsonify({'success': True, 'message': 'Test Discord message sent successfully'})
            else:
                return jsonify({'success': False, 'error': error}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/daily-report/trigger', methods=['POST'])
def trigger_daily_report():
    """Manually trigger the daily watchlist report"""
    try:
        from daily_report import generate_daily_report
        generate_daily_report()
        return jsonify({'success': True, 'message': 'Daily report sent successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============ STOCK COMPARISON API ============

@app.route('/api/stocks/compare', methods=['POST'])
def compare_stocks():
    """Compare 2-4 stocks side-by-side with metrics, technicals, predictions, and correlation"""
    try:
        import math

        data = request.get_json()
        tickers = data.get('tickers', [])
        period = data.get('period', '1mo')

        # Validate inputs
        tickers = [t.strip().upper() for t in tickers if t.strip()]
        tickers = list(dict.fromkeys(tickers))  # Remove duplicates preserving order

        if len(tickers) < 2:
            return jsonify({'error': 'At least 2 different tickers are required'}), 400
        if len(tickers) > 4:
            return jsonify({'error': 'Maximum 4 tickers allowed'}), 400

        valid_periods = ['1wk', '1mo', '3mo', '1y']
        if period not in valid_periods:
            return jsonify({'error': f'Invalid period. Use: {", ".join(valid_periods)}'}), 400

        metrics = []
        normalized_prices = {}
        returns_data = {}
        technicals = []
        predictions = []

        for ticker in tickers:
            stock = StockData(ticker)
            info = stock.get_stock_info()

            if not info or not info.get('current_price'):
                return jsonify({'error': f'Invalid or unavailable ticker: {ticker}'}), 400

            # Get extended info from yfinance
            yf_info = stock.stock.info
            weekly_change = stock.get_weekly_change()

            metric = {
                'ticker': ticker,
                'name': info.get('name', 'N/A'),
                'current_price': info.get('current_price'),
                'change': info.get('change', 0),
                'change_percent': info.get('change_percent', 0),
                'day_high': info.get('day_high', 'N/A'),
                'day_low': info.get('day_low', 'N/A'),
                'volume': info.get('volume', 'N/A'),
                'weekly_change': weekly_change,
                'market_cap': yf_info.get('marketCap', None),
                'pe_ratio': yf_info.get('trailingPE', None),
                'fifty_two_week_high': yf_info.get('fiftyTwoWeekHigh', None),
                'fifty_two_week_low': yf_info.get('fiftyTwoWeekLow', None),
                'sector': yf_info.get('sector', 'N/A'),
                'industry': yf_info.get('industry', 'N/A'),
            }
            metrics.append(metric)

            # Historical data for chart and correlation
            hist = stock.get_historical_data(period=period)
            if hist is not None and not hist.empty:
                closes = hist['Close']
                first_price = float(closes.iloc[0])
                if first_price > 0:
                    normalized = ((closes / first_price) - 1) * 100
                    normalized_prices[ticker] = {
                        'labels': hist.index.strftime('%Y-%m-%d').tolist(),
                        'values': [round(float(v), 2) for v in normalized.tolist()]
                    }
                    metric['period_return'] = round(float(normalized.iloc[-1]), 2)
                else:
                    metric['period_return'] = 0

                # Daily returns for correlation
                daily_returns = closes.pct_change().dropna()
                returns_data[ticker] = daily_returns
            else:
                metric['period_return'] = 0

            # Technical analysis
            predictor = StockPredictor(ticker)
            tech = predictor.analyze_technical()
            technicals.append({
                'ticker': ticker,
                'rsi_value': tech.get('rsi', {}).get('value', 'N/A'),
                'rsi_interpretation': tech.get('rsi', {}).get('interpretation', 'N/A'),
                'macd_interpretation': tech.get('macd', {}).get('interpretation', 'N/A'),
                'ma_position': tech.get('ma_trend', {}).get('position', 'N/A'),
                'ma20': tech.get('ma_trend', {}).get('ma20', 0),
                'ma50': tech.get('ma_trend', {}).get('ma50', 0),
                'ma200': tech.get('ma_trend', {}).get('ma200', 0),
            })

            # Prediction
            pred = predictor.get_prediction()
            predictions.append({
                'ticker': ticker,
                'recommendation': pred.get('recommendation', 'Hold'),
                'confidence': pred.get('confidence', 0),
                'combined_score': pred.get('combined_score', 0),
                'summary': pred.get('summary', ''),
            })

        # Build rankings
        daily_ranked = sorted(metrics, key=lambda x: x.get('change_percent', 0) or 0, reverse=True)
        weekly_ranked = sorted(metrics, key=lambda x: x.get('weekly_change', 0) or 0, reverse=True)
        period_ranked = sorted(metrics, key=lambda x: x.get('period_return', 0) or 0, reverse=True)

        rankings = {
            'daily': [{'ticker': m['ticker'], 'value': m.get('change_percent', 0)} for m in daily_ranked],
            'weekly': [{'ticker': m['ticker'], 'value': m.get('weekly_change', 0)} for m in weekly_ranked],
            'period': [{'ticker': m['ticker'], 'value': m.get('period_return', 0)} for m in period_ranked],
        }

        # Build correlation matrix
        correlation = {}
        if len(returns_data) >= 2:
            import pandas as pd
            returns_df = pd.DataFrame(returns_data)
            corr_matrix = returns_df.corr()

            for t1 in tickers:
                correlation[t1] = {}
                for t2 in tickers:
                    try:
                        val = float(corr_matrix.loc[t1, t2])
                        correlation[t1][t2] = round(val, 3) if not math.isnan(val) else 0
                    except (KeyError, ValueError):
                        correlation[t1][t2] = 0

        # Sector analysis
        sectors = {}
        for m in metrics:
            sector = m.get('sector', 'N/A')
            if sector not in sectors:
                sectors[sector] = []
            sectors[sector].append(m['ticker'])

        return jsonify({
            'tickers': tickers,
            'period': period,
            'metrics': metrics,
            'normalized_prices': normalized_prices,
            'rankings': rankings,
            'technicals': technicals,
            'predictions': predictions,
            'correlation': correlation,
            'sectors': sectors,
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/trades', methods=['GET'])
def get_trade_history():
    try:
        limit = request.args.get('limit', 50, type=int)
        platform = request.args.get('platform', None)

        query = 'SELECT * FROM trade_history'
        params = []

        if platform:
            query += ' WHERE platform = ?'
            params.append(platform)

        query += ' ORDER BY created_at DESC LIMIT ?'
        params.append(limit)

        with get_db_connection() as conn:
            cursor = conn.execute(query, params)
            trades = [dict(row) for row in cursor.fetchall()]

        return jsonify({
            'trades': trades,
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=8080, host='127.0.0.1')
