import logging
from datetime import datetime
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from alpaca.common.exceptions import APIError
from config import Config

logger = logging.getLogger(__name__)


class AlpacaTrader:
    def __init__(self):
        self.client = TradingClient(
            api_key=Config.ALPACA_API_KEY,
            secret_key=Config.ALPACA_SECRET_KEY,
            paper=Config.ALPACA_PAPER
        )

    def get_account(self):
        try:
            account = self.client.get_account()
            return {
                'equity': float(account.equity),
                'buying_power': float(account.buying_power),
                'cash': float(account.cash),
                'portfolio_value': float(account.portfolio_value),
                'status': str(account.status),
                'is_paper': Config.ALPACA_PAPER
            }
        except APIError as e:
            raise ValueError(f"Alpaca API error: {e}")

    def buy_stock(self, ticker, quantity=None, notional=None):
        if not quantity and not notional:
            raise ValueError("Provide either quantity or dollar amount")

        try:
            order_data = MarketOrderRequest(
                symbol=ticker.upper(),
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY
            )
            if notional:
                order_data.notional = round(notional, 2)
            else:
                order_data.qty = quantity

            order = self.client.submit_order(order_data)
            result = self._format_order(order)
            self._record_trade(result)
            return result
        except APIError as e:
            raise ValueError(f"Buy order failed: {e}")

    def sell_stock(self, ticker, quantity):
        try:
            order_data = MarketOrderRequest(
                symbol=ticker.upper(),
                qty=quantity,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY
            )
            order = self.client.submit_order(order_data)
            result = self._format_order(order)
            self._record_trade(result)
            return result
        except APIError as e:
            raise ValueError(f"Sell order failed: {e}")

    def get_positions(self):
        try:
            positions = self.client.get_all_positions()
            return [{
                'ticker': p.symbol,
                'qty': float(p.qty),
                'avg_entry_price': float(p.avg_entry_price),
                'current_price': float(p.current_price),
                'market_value': float(p.market_value),
                'unrealized_pl': float(p.unrealized_pl),
                'unrealized_plpc': float(p.unrealized_plpc) * 100
            } for p in positions]
        except APIError as e:
            raise ValueError(f"Failed to get positions: {e}")

    def get_orders(self, limit=10):
        try:
            request = GetOrdersRequest(
                status=QueryOrderStatus.ALL,
                limit=limit
            )
            orders = self.client.get_orders(filter=request)
            return [self._format_order(o) for o in orders]
        except APIError as e:
            raise ValueError(f"Failed to get orders: {e}")

    def cancel_order(self, order_id):
        try:
            self.client.cancel_order_by_id(order_id)
            return True
        except APIError as e:
            raise ValueError(f"Cancel failed: {e}")

    def get_position_for_ticker(self, ticker):
        try:
            position = self.client.get_open_position(ticker.upper())
            return {
                'ticker': position.symbol,
                'qty': float(position.qty),
                'avg_entry_price': float(position.avg_entry_price),
                'current_price': float(position.current_price),
                'market_value': float(position.market_value),
                'unrealized_pl': float(position.unrealized_pl),
                'unrealized_plpc': float(position.unrealized_plpc) * 100
            }
        except APIError:
            return None

    def get_clock(self):
        try:
            clock = self.client.get_clock()
            return {
                'is_open': clock.is_open,
                'next_open': str(clock.next_open),
                'next_close': str(clock.next_close)
            }
        except APIError:
            return None

    def _format_order(self, order):
        filled_qty = float(order.filled_qty) if order.filled_qty else 0
        filled_avg_price = float(order.filled_avg_price) if order.filled_avg_price else 0
        return {
            'order_id': str(order.id),
            'ticker': order.symbol,
            'side': str(order.side).split('.')[-1].lower(),
            'qty': float(order.qty) if order.qty else 0,
            'filled_qty': filled_qty,
            'filled_avg_price': filled_avg_price,
            'total_value': filled_qty * filled_avg_price,
            'status': str(order.status).split('.')[-1].lower(),
            'submitted_at': str(order.submitted_at) if order.submitted_at else '',
            'filled_at': str(order.filled_at) if order.filled_at else '',
            'type': str(order.type).split('.')[-1].lower()
        }

    def _record_trade(self, order_data):
        try:
            from database import get_db_connection
            with get_db_connection() as conn:
                conn.execute('''
                    INSERT INTO trade_history
                    (platform, ticker, side, quantity, price, total_value, order_id, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    'alpaca',
                    order_data['ticker'],
                    order_data['side'],
                    order_data['filled_qty'] or order_data['qty'],
                    order_data['filled_avg_price'],
                    order_data['total_value'],
                    order_data['order_id'],
                    order_data['status'],
                    datetime.now().isoformat()
                ))
        except Exception as e:
            logger.error(f"Failed to record trade: {e}")
