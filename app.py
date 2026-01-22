from flask import Flask, render_template, jsonify
from stock_data import StockData
from datetime import datetime

app = Flask(__name__)

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

    # Format for Chart.js with OHLCV data
    labels = historical_data.index.strftime('%Y-%m-%d %H:%M').tolist()
    close_prices = historical_data['Close'].round(2).tolist()
    open_prices = historical_data['Open'].round(2).tolist()
    high_prices = historical_data['High'].round(2).tolist()
    low_prices = historical_data['Low'].round(2).tolist()
    volumes = historical_data['Volume'].tolist()

    # Calculate statistics
    high = float(historical_data['High'].max())
    low = float(historical_data['Low'].min())
    avg = float(historical_data['Close'].mean())
    period_change = ((close_prices[-1] - close_prices[0]) / close_prices[0]) * 100

    # Calculate moving averages and replace NaN with None (null in JSON)
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

if __name__ == '__main__':
    app.run(debug=True, port=8080, host='127.0.0.1')
