from flask import Flask, render_template, jsonify
from stock_data import StockData
from datetime import datetime

app = Flask(__name__)

WATCHLIST = ['AAPL', 'MSFT', 'MA', 'LLY', 'AMZN', 'GOOGL', 'SPY', 'TSM', 'NVDA']

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

if __name__ == '__main__':
    app.run(debug=True, port=8080, host='127.0.0.1')
