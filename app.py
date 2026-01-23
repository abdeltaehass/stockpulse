from flask import Flask, render_template, jsonify, request
from stock_data import StockData
from portfolio import Portfolio
from database import init_db
from datetime import datetime

app = Flask(__name__)

# Initialize database on startup
init_db()

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

if __name__ == '__main__':
    app.run(debug=True, port=8080, host='127.0.0.1')
