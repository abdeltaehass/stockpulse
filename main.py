from stock_data import StockData
from datetime import datetime

def display_stock_info(ticker):
    print(f"\n{'='*50}")
    print(f"StockPulse - Market Monitor")
    print(f"{'='*50}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")
    
    stock = StockData(ticker)
    info = stock.get_stock_info()
    
    if info:
        print(f"Stock: {info['name']} ({info['ticker']})")
        print(f"Current Price: ${info['current_price']}")
        print(f"Previous Close: ${info['previous_close']}")
        print(f"Open: ${info['open']}")
        print(f"Day Range: ${info['day_low']} - ${info['day_high']}")
        print(f"Volume: {info['volume']:,}")
        
        if 'change' in info:
            change_symbol = '📈' if info['change'] >= 0 else '📉'
            print(f"\nChange: {change_symbol} ${info['change']} ({info['change_percent']}%)")
    else:
        print(f"Could not fetch data for {ticker}")
    
    print(f"\n{'='*50}\n")

def main():
    print("Welcome to StockPulse!")
    
    watchlist = ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'GLD']
    
    print(f"Monitoring {len(watchlist)} stocks...")
    
    for ticker in watchlist:
        display_stock_info(ticker)

if __name__ == "__main__":
    main()