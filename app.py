from flask import Flask, render_template, jsonify, request
from stock_data import StockData
from portfolio import Portfolio
from predictor import StockPredictor
from database import init_db, get_db_connection
from scheduler import start_scheduler
from notifications import send_email_notification, send_telegram_notification, send_discord_notification
from datetime import datetime

app = Flask(__name__)

# Initialize database on startup
init_db()

# Start background scheduler for price alerts
start_scheduler()

WATCHLIST = ['AAPL', 'MSFT', 'MA', 'GLD', 'AMZN', 'GOOGL', 'SPY', 'TSM', 'NVDA']

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/stocks')
def get_stocks():
    stocks_data = []

    for ticker in WATCHLIST:
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

    stock = StockData(ticker)
    historical_data = stock.get_historical_data(period=period)

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
            tickers = WATCHLIST

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

@app.route('/api/notifications/settings', methods=['GET'])
def get_notification_settings():
    """Get notification preferences"""
    try:
        with get_db_connection() as conn:
            cursor = conn.execute('''
                SELECT email_enabled, email_address, telegram_enabled,
                       telegram_chat_id, telegram_bot_token, discord_enabled, discord_webhook_url
                FROM notification_settings
                WHERE id = 1
            ''')
            settings = cursor.fetchone()

            if settings:
                return jsonify(dict(settings))
            else:
                # Return default settings if not configured yet
                return jsonify({
                    'email_enabled': 0,
                    'email_address': '',
                    'telegram_enabled': 0,
                    'telegram_chat_id': '',
                    'telegram_bot_token': '',
                    'discord_enabled': 0,
                    'discord_webhook_url': ''
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
                # Update existing settings
                conn.execute('''
                    UPDATE notification_settings
                    SET email_enabled = ?, email_address = ?,
                        telegram_enabled = ?, telegram_chat_id = ?, telegram_bot_token = ?,
                        discord_enabled = ?, discord_webhook_url = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                ''', (
                    data.get('email_enabled', 0),
                    data.get('email_address', ''),
                    data.get('telegram_enabled', 0),
                    data.get('telegram_chat_id', ''),
                    data.get('telegram_bot_token', ''),
                    data.get('discord_enabled', 0),
                    data.get('discord_webhook_url', '')
                ))
            else:
                # Insert new settings
                conn.execute('''
                    INSERT INTO notification_settings
                    (id, email_enabled, email_address, telegram_enabled, telegram_chat_id,
                     telegram_bot_token, discord_enabled, discord_webhook_url)
                    VALUES (1, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    data.get('email_enabled', 0),
                    data.get('email_address', ''),
                    data.get('telegram_enabled', 0),
                    data.get('telegram_chat_id', ''),
                    data.get('telegram_bot_token', ''),
                    data.get('discord_enabled', 0),
                    data.get('discord_webhook_url', '')
                ))

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

if __name__ == '__main__':
    app.run(debug=True, port=8080, host='127.0.0.1')
