import logging
from datetime import datetime
from binance.client import Client as BinanceClient
from binance.exceptions import BinanceAPIException
from config import Config

logger = logging.getLogger(__name__)

KNOWN_CRYPTO_BASES = [
    'BTC', 'ETH', 'BNB', 'SOL', 'XRP', 'ADA', 'DOGE', 'AVAX',
    'DOT', 'MATIC', 'LINK', 'SHIB', 'LTC', 'UNI', 'ATOM',
    'XLM', 'ALGO', 'NEAR', 'FTM', 'AAVE', 'PEPE', 'ARB', 'OP',
    'APT', 'SUI', 'SEI', 'TIA', 'INJ', 'FET', 'RENDER', 'WIF',
    'BONK', 'JUP', 'PYTH', 'TRX', 'TON', 'NOT', 'FLOKI'
]


class BinanceTrader:
    def __init__(self):
        self.client = BinanceClient(
            api_key=Config.BINANCE_API_KEY,
            api_secret=Config.BINANCE_SECRET_KEY
        )
        self._symbol_info_cache = {}

    @staticmethod
    def normalize_symbol(ticker):
        ticker = ticker.upper().strip()
        if ticker.endswith('-USD'):
            ticker = ticker.replace('-USD', '')
        if ticker.endswith('USDT'):
            return ticker
        return ticker + 'USDT'

    @staticmethod
    def is_crypto_ticker(ticker):
        ticker = ticker.upper().strip()
        if ticker.endswith('-USD'):
            return True
        if ticker.endswith('USDT'):
            return True
        base = ticker.replace('-USD', '').replace('USDT', '')
        if base in KNOWN_CRYPTO_BASES:
            return True
        return False

    def get_price(self, ticker):
        symbol = self.normalize_symbol(ticker)
        try:
            price = self.client.get_symbol_ticker(symbol=symbol)
            return float(price['price'])
        except BinanceAPIException as e:
            raise ValueError(f"Failed to get price for {symbol}: {e}")

    def _get_lot_size(self, symbol):
        if symbol in self._symbol_info_cache:
            return self._symbol_info_cache[symbol]

        try:
            info = self.client.get_symbol_info(symbol)
            if not info:
                return None

            lot_filter = None
            for f in info['filters']:
                if f['filterType'] == 'LOT_SIZE':
                    lot_filter = f
                    break

            if lot_filter:
                step_size = float(lot_filter['stepSize'])
                min_qty = float(lot_filter['minQty'])
                self._symbol_info_cache[symbol] = {
                    'step_size': step_size,
                    'min_qty': min_qty
                }
                return self._symbol_info_cache[symbol]
        except BinanceAPIException:
            pass
        return None

    def _truncate_qty(self, symbol, qty):
        lot_info = self._get_lot_size(symbol)
        if not lot_info:
            return qty

        step = lot_info['step_size']
        if step == 0:
            return qty

        precision = len(str(step).rstrip('0').split('.')[-1]) if '.' in str(step) else 0
        truncated = float(int(qty / step) * step)
        return round(truncated, precision)

    def buy_crypto(self, ticker, quantity=None, quote_amount=None):
        symbol = self.normalize_symbol(ticker)
        try:
            if quote_amount:
                order = self.client.order_market_buy(
                    symbol=symbol,
                    quoteOrderQty=round(quote_amount, 2)
                )
            elif quantity:
                qty = self._truncate_qty(symbol, quantity)
                order = self.client.order_market_buy(
                    symbol=symbol,
                    quantity=qty
                )
            else:
                raise ValueError("Provide either quantity or dollar amount")

            result = self._format_order(order, symbol)
            self._record_trade(result)
            return result
        except BinanceAPIException as e:
            raise ValueError(f"Buy order failed: {e}")

    def sell_crypto(self, ticker, quantity):
        symbol = self.normalize_symbol(ticker)
        try:
            qty = self._truncate_qty(symbol, quantity)
            order = self.client.order_market_sell(
                symbol=symbol,
                quantity=qty
            )
            result = self._format_order(order, symbol)
            self._record_trade(result)
            return result
        except BinanceAPIException as e:
            raise ValueError(f"Sell order failed: {e}")

    def get_balances(self):
        try:
            account = self.client.get_account()
            balances = []
            for b in account['balances']:
                free = float(b['free'])
                locked = float(b['locked'])
                total = free + locked
                if total > 0:
                    usd_value = 0
                    if b['asset'] == 'USDT':
                        usd_value = total
                    elif b['asset'] == 'BUSD':
                        usd_value = total
                    else:
                        try:
                            price = float(self.client.get_symbol_ticker(
                                symbol=b['asset'] + 'USDT'
                            )['price'])
                            usd_value = total * price
                        except:
                            pass
                    balances.append({
                        'asset': b['asset'],
                        'free': free,
                        'locked': locked,
                        'total': total,
                        'usd_value': round(usd_value, 2)
                    })
            balances.sort(key=lambda x: x['usd_value'], reverse=True)
            return balances
        except BinanceAPIException as e:
            raise ValueError(f"Failed to get balances: {e}")

    def get_orders(self, ticker=None, limit=10):
        try:
            if ticker:
                symbol = self.normalize_symbol(ticker)
                orders = self.client.get_all_orders(symbol=symbol, limit=limit)
                return [self._format_order(o, symbol) for o in reversed(orders)]
            else:
                all_orders = []
                for base in ['BTC', 'ETH', 'SOL', 'BNB', 'XRP']:
                    try:
                        symbol = base + 'USDT'
                        orders = self.client.get_all_orders(symbol=symbol, limit=3)
                        all_orders.extend([self._format_order(o, symbol) for o in orders])
                    except:
                        continue
                all_orders.sort(key=lambda x: x.get('submitted_at', ''), reverse=True)
                return all_orders[:limit]
        except BinanceAPIException as e:
            raise ValueError(f"Failed to get orders: {e}")

    def cancel_order(self, ticker, order_id):
        symbol = self.normalize_symbol(ticker)
        try:
            self.client.cancel_order(symbol=symbol, orderId=int(order_id))
            return True
        except BinanceAPIException as e:
            raise ValueError(f"Cancel failed: {e}")

    def _format_order(self, order, symbol):
        filled_qty = float(order.get('executedQty', 0))
        cum_quote = float(order.get('cummulativeQuoteQty', 0))
        avg_price = cum_quote / filled_qty if filled_qty > 0 else 0
        return {
            'order_id': str(order.get('orderId', '')),
            'ticker': symbol,
            'side': order.get('side', '').lower(),
            'qty': float(order.get('origQty', 0)),
            'filled_qty': filled_qty,
            'filled_avg_price': avg_price,
            'total_value': cum_quote,
            'status': order.get('status', '').lower(),
            'submitted_at': str(order.get('time', '')),
            'filled_at': str(order.get('updateTime', '')),
            'type': order.get('type', '').lower()
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
                    'binance',
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
