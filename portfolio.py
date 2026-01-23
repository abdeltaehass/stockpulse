from database import get_db_connection
from stock_data import StockData
from datetime import datetime

class Portfolio:
    @staticmethod
    def add_holding(ticker, quantity, purchase_price, purchase_date, notes=''):
        """Add a new portfolio holding"""
        stock = StockData(ticker)
        if stock.get_current_price() is None:
            raise ValueError(f"Invalid ticker: {ticker}")

        with get_db_connection() as conn:
            conn.execute('''
                INSERT INTO portfolio_holdings
                (ticker, quantity, purchase_price, purchase_date, notes)
                VALUES (?, ?, ?, ?, ?)
            ''', (ticker.upper(), quantity, purchase_price, purchase_date, notes))

    @staticmethod
    def get_all_holdings():
        """Get all portfolio holdings"""
        with get_db_connection() as conn:
            cursor = conn.execute('''
                SELECT * FROM portfolio_holdings ORDER BY purchase_date DESC
            ''')
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def update_holding(holding_id, quantity, purchase_price, purchase_date, notes):
        """Update an existing holding"""
        with get_db_connection() as conn:
            conn.execute('''
                UPDATE portfolio_holdings
                SET quantity = ?, purchase_price = ?, purchase_date = ?,
                    notes = ?, updated_at = ?
                WHERE id = ?
            ''', (quantity, purchase_price, purchase_date, notes,
                  datetime.now().isoformat(), holding_id))

    @staticmethod
    def delete_holding(holding_id):
        """Delete a holding"""
        with get_db_connection() as conn:
            conn.execute('DELETE FROM portfolio_holdings WHERE id = ?', (holding_id,))

    @staticmethod
    def calculate_portfolio_summary():
        """Calculate comprehensive portfolio metrics"""
        holdings = Portfolio.get_all_holdings()

        if not holdings:
            return {
                'total_value': 0,
                'total_cost': 0,
                'total_gain_loss': 0,
                'total_gain_loss_percent': 0,
                'holdings_count': 0
            }

        total_value = 0
        total_cost = 0

        # Get current prices for all unique tickers
        tickers = list(set([h['ticker'] for h in holdings]))
        current_prices = {}

        for ticker in tickers:
            stock = StockData(ticker)
            price = stock.get_current_price()
            if price:
                current_prices[ticker] = price

        for holding in holdings:
            ticker = holding['ticker']
            quantity = holding['quantity']
            purchase_price = holding['purchase_price']

            cost = quantity * purchase_price
            total_cost += cost

            if ticker in current_prices:
                value = quantity * current_prices[ticker]
                total_value += value

        gain_loss = total_value - total_cost
        gain_loss_percent = (gain_loss / total_cost * 100) if total_cost > 0 else 0

        return {
            'total_value': round(total_value, 2),
            'total_cost': round(total_cost, 2),
            'total_gain_loss': round(gain_loss, 2),
            'total_gain_loss_percent': round(gain_loss_percent, 2),
            'holdings_count': len(holdings)
        }

    @staticmethod
    def get_holdings_with_pnl():
        """Get all holdings with current P&L calculations"""
        holdings = Portfolio.get_all_holdings()
        enriched_holdings = []

        for holding in holdings:
            ticker = holding['ticker']
            quantity = holding['quantity']
            purchase_price = holding['purchase_price']
            purchase_date = holding['purchase_date']

            # Get current price
            stock = StockData(ticker)
            current_price = stock.get_current_price()

            if current_price:
                cost = quantity * purchase_price
                current_value = quantity * current_price
                gain_loss = current_value - cost
                gain_loss_percent = (gain_loss / cost * 100) if cost > 0 else 0

                # Calculate holding period
                try:
                    purchase_dt = datetime.fromisoformat(purchase_date)
                    days_held = (datetime.now() - purchase_dt).days
                except:
                    days_held = 0

                enriched_holdings.append({
                    **holding,
                    'current_price': round(current_price, 2),
                    'current_value': round(current_value, 2),
                    'cost_basis': round(cost, 2),
                    'gain_loss': round(gain_loss, 2),
                    'gain_loss_percent': round(gain_loss_percent, 2),
                    'days_held': days_held
                })
            else:
                # If current price unavailable
                enriched_holdings.append({
                    **holding,
                    'current_price': None,
                    'current_value': None,
                    'cost_basis': round(quantity * purchase_price, 2),
                    'gain_loss': None,
                    'gain_loss_percent': None,
                    'days_held': None
                })

        return enriched_holdings

    @staticmethod
    def get_performance_metrics():
        """Calculate daily, weekly, and all-time performance"""
        holdings = Portfolio.get_all_holdings()

        if not holdings:
            return {
                'daily_change': 0,
                'daily_change_percent': 0,
                'weekly_change': 0,
                'weekly_change_percent': 0,
                'all_time_gain_loss': 0,
                'all_time_gain_loss_percent': 0,
                'total_current_value': 0,
                'total_cost': 0
            }

        # Group holdings by ticker
        ticker_positions = {}
        for holding in holdings:
            ticker = holding['ticker']
            if ticker not in ticker_positions:
                ticker_positions[ticker] = {
                    'total_quantity': 0,
                    'total_cost': 0
                }
            ticker_positions[ticker]['total_quantity'] += holding['quantity']
            ticker_positions[ticker]['total_cost'] += holding['quantity'] * holding['purchase_price']

        # Calculate metrics
        total_current_value = 0
        total_previous_close_value = 0
        total_week_ago_value = 0
        total_cost = 0

        for ticker, position in ticker_positions.items():
            stock = StockData(ticker)
            current_price = stock.get_current_price()

            if current_price:
                quantity = position['total_quantity']
                cost = position['total_cost']

                total_current_value += quantity * current_price
                total_cost += cost

                # Get previous close for daily change
                info = stock.get_stock_info()
                if info and info.get('previous_close') != 'N/A':
                    total_previous_close_value += quantity * info['previous_close']

                # Get week ago price
                hist_data = stock.get_historical_data(period='1wk')
                if hist_data is not None and len(hist_data) >= 2:
                    week_ago_price = hist_data['Close'].iloc[0]
                    total_week_ago_value += quantity * week_ago_price

        # Calculate changes
        daily_change = total_current_value - total_previous_close_value
        daily_change_percent = (daily_change / total_previous_close_value * 100) if total_previous_close_value > 0 else 0

        weekly_change = total_current_value - total_week_ago_value
        weekly_change_percent = (weekly_change / total_week_ago_value * 100) if total_week_ago_value > 0 else 0

        all_time_gain_loss = total_current_value - total_cost
        all_time_gain_loss_percent = (all_time_gain_loss / total_cost * 100) if total_cost > 0 else 0

        return {
            'daily_change': round(daily_change, 2),
            'daily_change_percent': round(daily_change_percent, 2),
            'weekly_change': round(weekly_change, 2),
            'weekly_change_percent': round(weekly_change_percent, 2),
            'all_time_gain_loss': round(all_time_gain_loss, 2),
            'all_time_gain_loss_percent': round(all_time_gain_loss_percent, 2),
            'total_current_value': round(total_current_value, 2),
            'total_cost': round(total_cost, 2)
        }
