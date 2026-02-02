import logging
import threading
from datetime import datetime
from functools import wraps

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from config import Config
from database import get_db_connection
from stock_data import StockData
from predictor import StockPredictor
from binance_trader import BinanceTrader

logger = logging.getLogger(__name__)

alpaca = None
binance = None

pending_trades = {}


def authorized_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = str(update.effective_chat.id)

        with get_db_connection() as conn:
            cursor = conn.execute(
                'SELECT telegram_chat_id FROM notification_settings WHERE id = 1'
            )
            settings = cursor.fetchone()

        if not settings or settings['telegram_chat_id'] != chat_id:
            await update.message.reply_text(
                f"Unauthorized. Your chat ID ({chat_id}) is not configured in StockPulse.\n"
                "Add this chat ID in Settings > Notifications to authorize."
            )
            logger.warning(f"Unauthorized access attempt from chat_id: {chat_id}")
            return

        return await func(update, context)
    return wrapper


@authorized_only
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "*StockPulse Trading Bot*\n\n"
        "*Trading Commands:*\n"
        "/buy <ticker> <qty\\_or\\_usd> \\- Buy stock or crypto\n"
        "/sell <ticker> <quantity> \\- Sell stock or crypto\n"
        "/cancel <order\\_id> \\- Cancel pending order\n\n"
        "*Info Commands:*\n"
        "/portfolio \\- Show current holdings\n"
        "/balance \\- Show account balances\n"
        "/price <ticker> \\- Quick price check\n"
        "/predict <ticker> \\- Get AI prediction\n"
        "/orders \\- Show recent orders\n"
        "/help \\- Show this message\n\n"
        "*Examples:*\n"
        "`/buy AAPL 10` \\- Buy 10 shares of Apple\n"
        "`/buy AAPL 500usd` \\- Buy $500 of Apple\n"
        "`/buy BTC 0.5` \\- Buy 0\\.5 BTC\n"
        "`/buy BTC 1000usd` \\- Spend $1000 on BTC\n"
        "`/sell TSLA 5` \\- Sell 5 shares of Tesla\n"
        "`/price ETH` \\- Check Ethereum price\n"
        "`/predict NVDA` \\- Get NVDA prediction"
    )
    await update.message.reply_text(help_text, parse_mode='MarkdownV2')


@authorized_only
async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /buy <ticker> <quantity_or_usd>\n"
            "Examples: /buy AAPL 10, /buy BTC 0.5, /buy AAPL 500usd"
        )
        return

    ticker = context.args[0].upper()
    amount_str = context.args[1].lower()

    is_usd = amount_str.endswith('usd') or amount_str.startswith('$')
    amount_str_clean = amount_str.replace('usd', '').replace('$', '')

    try:
        amount = float(amount_str_clean)
    except ValueError:
        await update.message.reply_text("Invalid amount. Use a number like 10, 0.5, or 500usd")
        return

    if amount <= 0:
        await update.message.reply_text("Amount must be positive.")
        return

    is_crypto = BinanceTrader.is_crypto_ticker(ticker)
    platform = 'Binance' if is_crypto else 'Alpaca'

    try:
        if is_crypto:
            current_price = binance.get_price(ticker)
            display_ticker = BinanceTrader.normalize_symbol(ticker)
        else:
            stock = StockData(ticker)
            current_price = stock.get_current_price()
            display_ticker = ticker

            if not is_crypto and alpaca:
                clock = alpaca.get_clock()
                if clock and not clock['is_open']:
                    await update.message.reply_text(
                        f"Note: US stock market is currently closed.\n"
                        f"Next open: {clock['next_open']}\n"
                        f"Order will be queued for market open."
                    )
    except Exception as e:
        await update.message.reply_text(f"Failed to get price for {ticker}: {e}")
        return

    if is_usd:
        est_qty = amount / current_price if current_price else 0
        confirm_text = (
            f"Confirm Buy Order\n\n"
            f"Platform: {platform}\n"
            f"Ticker: {display_ticker}\n"
            f"Amount: ${amount:,.2f}\n"
            f"Est. Quantity: {est_qty:.6f}\n"
            f"Current Price: ${current_price:,.2f}\n"
            f"Order Type: Market\n\n"
            f"Proceed?"
        )
    else:
        est_total = amount * current_price if current_price else 0
        confirm_text = (
            f"Confirm Buy Order\n\n"
            f"Platform: {platform}\n"
            f"Ticker: {display_ticker}\n"
            f"Quantity: {amount}\n"
            f"Est. Total: ${est_total:,.2f}\n"
            f"Current Price: ${current_price:,.2f}\n"
            f"Order Type: Market\n\n"
            f"Proceed?"
        )

    chat_id = update.effective_chat.id
    pending_trades[chat_id] = {
        'action': 'buy',
        'ticker': ticker,
        'is_crypto': is_crypto,
        'is_usd': is_usd,
        'amount': amount,
        'current_price': current_price,
        'timestamp': datetime.now()
    }

    keyboard = [[
        InlineKeyboardButton("Confirm", callback_data="confirm_trade"),
        InlineKeyboardButton("Cancel", callback_data="cancel_trade")
    ]]
    await update.message.reply_text(
        confirm_text, reply_markup=InlineKeyboardMarkup(keyboard)
    )


@authorized_only
async def cmd_sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /sell <ticker> <quantity>\n"
            "Examples: /sell AAPL 10, /sell BTC 0.5"
        )
        return

    ticker = context.args[0].upper()

    try:
        quantity = float(context.args[1])
    except ValueError:
        await update.message.reply_text("Invalid quantity. Use a number like 10 or 0.5")
        return

    if quantity <= 0:
        await update.message.reply_text("Quantity must be positive.")
        return

    is_crypto = BinanceTrader.is_crypto_ticker(ticker)
    platform = 'Binance' if is_crypto else 'Alpaca'

    try:
        if is_crypto:
            current_price = binance.get_price(ticker)
            display_ticker = BinanceTrader.normalize_symbol(ticker)
        else:
            stock = StockData(ticker)
            current_price = stock.get_current_price()
            display_ticker = ticker
    except Exception as e:
        await update.message.reply_text(f"Failed to get price for {ticker}: {e}")
        return

    est_total = quantity * current_price if current_price else 0
    confirm_text = (
        f"Confirm Sell Order\n\n"
        f"Platform: {platform}\n"
        f"Ticker: {display_ticker}\n"
        f"Quantity: {quantity}\n"
        f"Est. Total: ${est_total:,.2f}\n"
        f"Current Price: ${current_price:,.2f}\n"
        f"Order Type: Market\n\n"
        f"Proceed?"
    )

    chat_id = update.effective_chat.id
    pending_trades[chat_id] = {
        'action': 'sell',
        'ticker': ticker,
        'is_crypto': is_crypto,
        'is_usd': False,
        'amount': quantity,
        'current_price': current_price,
        'timestamp': datetime.now()
    }

    keyboard = [[
        InlineKeyboardButton("Confirm", callback_data="confirm_trade"),
        InlineKeyboardButton("Cancel", callback_data="cancel_trade")
    ]]
    await update.message.reply_text(
        confirm_text, reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_trade_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    trade = pending_trades.pop(chat_id, None)

    if not trade:
        await query.edit_message_text("Trade expired or already processed.")
        return

    if query.data == 'cancel_trade':
        await query.edit_message_text("Trade cancelled.")
        return

    await query.edit_message_text("Executing order...")

    try:
        if trade['is_crypto']:
            if trade['action'] == 'buy':
                if trade['is_usd']:
                    result = binance.buy_crypto(trade['ticker'], quote_amount=trade['amount'])
                else:
                    result = binance.buy_crypto(trade['ticker'], quantity=trade['amount'])
            else:
                result = binance.sell_crypto(trade['ticker'], quantity=trade['amount'])
        else:
            if trade['action'] == 'buy':
                if trade['is_usd']:
                    result = alpaca.buy_stock(trade['ticker'], notional=trade['amount'])
                else:
                    result = alpaca.buy_stock(trade['ticker'], quantity=trade['amount'])
            else:
                result = alpaca.sell_stock(trade['ticker'], quantity=trade['amount'])

        msg = (
            f"Order Executed\n\n"
            f"Order ID: {result['order_id']}\n"
            f"Ticker: {result['ticker']}\n"
            f"Side: {result['side'].upper()}\n"
            f"Quantity: {result['filled_qty']}\n"
            f"Avg Price: ${result['filled_avg_price']:,.2f}\n"
            f"Total: ${result['total_value']:,.2f}\n"
            f"Status: {result['status']}"
        )
        await query.edit_message_text(msg)

    except Exception as e:
        await query.edit_message_text(f"Order failed: {str(e)}")


@authorized_only
async def cmd_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_parts = ["*Portfolio Holdings*\n"]

    if alpaca:
        try:
            positions = alpaca.get_positions()
            if positions:
                msg_parts.append("*Stocks (Alpaca):*")
                for p in positions:
                    pl_emoji = "+" if p['unrealized_pl'] >= 0 else ""
                    msg_parts.append(
                        f"  {p['ticker']}: {p['qty']} @ ${p['avg_entry_price']:,.2f}\n"
                        f"    Now: ${p['current_price']:,.2f} | "
                        f"P/L: {pl_emoji}${p['unrealized_pl']:,.2f} ({pl_emoji}{p['unrealized_plpc']:.1f}%)"
                    )
            else:
                msg_parts.append("*Stocks (Alpaca):* No positions")
        except Exception as e:
            msg_parts.append(f"*Stocks:* Error - {e}")

    msg_parts.append("")

    if binance:
        try:
            balances = binance.get_balances()
            if balances:
                msg_parts.append("*Crypto (Binance):*")
                for b in balances:
                    if b['usd_value'] > 0.01:
                        msg_parts.append(
                            f"  {b['asset']}: {b['total']:.8g} (${b['usd_value']:,.2f})"
                        )
            else:
                msg_parts.append("*Crypto (Binance):* No holdings")
        except Exception as e:
            msg_parts.append(f"*Crypto:* Error - {e}")

    await update.message.reply_text('\n'.join(msg_parts), parse_mode='Markdown')


@authorized_only
async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_parts = ["*Account Balances*\n"]

    if alpaca:
        try:
            account = alpaca.get_account()
            mode = "Paper" if account['is_paper'] else "Live"
            msg_parts.append(
                f"*Alpaca ({mode}):*\n"
                f"  Equity: ${account['equity']:,.2f}\n"
                f"  Cash: ${account['cash']:,.2f}\n"
                f"  Buying Power: ${account['buying_power']:,.2f}\n"
                f"  Portfolio Value: ${account['portfolio_value']:,.2f}"
            )
        except Exception as e:
            msg_parts.append(f"*Alpaca:* Error - {e}")

    msg_parts.append("")

    if binance:
        try:
            balances = binance.get_balances()
            total_usd = sum(b['usd_value'] for b in balances)
            usdt_balance = next((b for b in balances if b['asset'] == 'USDT'), None)
            usdt_free = usdt_balance['free'] if usdt_balance else 0

            msg_parts.append(
                f"*Binance:*\n"
                f"  USDT Available: ${usdt_free:,.2f}\n"
                f"  Total Value: ${total_usd:,.2f}\n"
                f"  Assets: {len(balances)}"
            )
        except Exception as e:
            msg_parts.append(f"*Binance:* Error - {e}")

    await update.message.reply_text('\n'.join(msg_parts), parse_mode='Markdown')


@authorized_only
async def cmd_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /price <ticker>\nExamples: /price AAPL, /price BTC")
        return

    ticker = context.args[0].upper()
    is_crypto = BinanceTrader.is_crypto_ticker(ticker)

    try:
        if is_crypto:
            price = binance.get_price(ticker)
            symbol = BinanceTrader.normalize_symbol(ticker)
            msg = f"*{symbol}*\nPrice: ${price:,.2f}"
        else:
            stock = StockData(ticker)
            info = stock.get_stock_info()
            price = info.get('price', 0)
            change = info.get('change', 0)
            change_pct = info.get('change_pct', 0)
            change_emoji = "+" if change >= 0 else ""
            day_high = info.get('day_high', 0)
            day_low = info.get('day_low', 0)

            msg = (
                f"*{ticker}* - {info.get('name', ticker)}\n"
                f"Price: ${price:,.2f}\n"
                f"Change: {change_emoji}${change:,.2f} ({change_emoji}{change_pct:.2f}%)\n"
                f"Day Range: ${day_low:,.2f} - ${day_high:,.2f}"
            )

        await update.message.reply_text(msg, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"Error getting price for {ticker}: {e}")


@authorized_only
async def cmd_predict(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /predict <ticker>\nExample: /predict AAPL")
        return

    ticker = context.args[0].upper()
    await update.message.reply_text(f"Analyzing {ticker}... this may take a moment.")

    try:
        predictor = StockPredictor(ticker)
        prediction = predictor.get_prediction()

        rec = prediction.get('recommendation', 'N/A')
        confidence = prediction.get('confidence', 0)
        score = prediction.get('combined_score', 0)
        summary = prediction.get('summary', '')

        breakdown_text = ""
        for sig in prediction.get('signal_breakdown', []):
            label = sig.get('label', '')
            name = sig.get('name', '')
            breakdown_text += f"  {name}: {label}\n"

        msg = (
            f"*{ticker} Analysis*\n\n"
            f"Recommendation: *{rec}*\n"
            f"Confidence: {confidence}%\n"
            f"Score: {score}\n\n"
            f"*Signals:*\n{breakdown_text}\n"
            f"{summary}"
        )
        await update.message.reply_text(msg, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"Prediction failed for {ticker}: {e}")


@authorized_only
async def cmd_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_parts = ["*Recent Orders*\n"]

    if alpaca:
        try:
            orders = alpaca.get_orders(limit=5)
            if orders:
                msg_parts.append("*Stocks (Alpaca):*")
                for o in orders:
                    msg_parts.append(
                        f"  {o['side'].upper()} {o['ticker']} x{o['qty']} - {o['status']}\n"
                        f"    ID: {o['order_id'][:12]}..."
                    )
            else:
                msg_parts.append("*Stocks:* No recent orders")
        except Exception as e:
            msg_parts.append(f"*Stocks:* Error - {e}")

    msg_parts.append("")

    if binance:
        try:
            orders = binance.get_orders(limit=5)
            if orders:
                msg_parts.append("*Crypto (Binance):*")
                for o in orders:
                    msg_parts.append(
                        f"  {o['side'].upper()} {o['ticker']} x{o['qty']} - {o['status']}\n"
                        f"    ID: {o['order_id']}"
                    )
            else:
                msg_parts.append("*Crypto:* No recent orders")
        except Exception as e:
            msg_parts.append(f"*Crypto:* Error - {e}")

    await update.message.reply_text('\n'.join(msg_parts), parse_mode='Markdown')


@authorized_only
async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /cancel <order_id>")
        return

    order_id = context.args[0]

    if alpaca:
        try:
            alpaca.cancel_order(order_id)
            await update.message.reply_text(f"Alpaca order {order_id} cancelled.")
            return
        except:
            pass

    if binance and len(context.args) >= 2:
        ticker = context.args[0].upper()
        order_id = context.args[1]
        try:
            binance.cancel_order(ticker, order_id)
            await update.message.reply_text(f"Binance order {order_id} cancelled.")
            return
        except:
            pass

    await update.message.reply_text(
        "Could not cancel order. For Binance, use: /cancel <ticker> <order_id>"
    )


def start_telegram_bot():
    def _run_bot():
        try:
            global alpaca, binance

            try:
                from alpaca_trader import AlpacaTrader
                if Config.ALPACA_API_KEY and Config.ALPACA_API_KEY != 'your-alpaca-api-key':
                    alpaca = AlpacaTrader()
                    logger.info("Alpaca trader initialized")
                else:
                    logger.warning("Alpaca API keys not configured, stock trading disabled")
            except Exception as e:
                logger.error(f"Failed to initialize Alpaca: {e}")

            try:
                if Config.BINANCE_API_KEY and Config.BINANCE_API_KEY != 'your-binance-api-key':
                    binance = BinanceTrader()
                    logger.info("Binance trader initialized")
                else:
                    logger.warning("Binance API keys not configured, crypto trading disabled")
            except Exception as e:
                logger.error(f"Failed to initialize Binance: {e}")

            app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()

            app.add_handler(CommandHandler('help', cmd_help))
            app.add_handler(CommandHandler('start', cmd_help))
            app.add_handler(CommandHandler('buy', cmd_buy))
            app.add_handler(CommandHandler('sell', cmd_sell))
            app.add_handler(CommandHandler('portfolio', cmd_portfolio))
            app.add_handler(CommandHandler('balance', cmd_balance))
            app.add_handler(CommandHandler('price', cmd_price))
            app.add_handler(CommandHandler('predict', cmd_predict))
            app.add_handler(CommandHandler('orders', cmd_orders))
            app.add_handler(CommandHandler('cancel', cmd_cancel))
            app.add_handler(CallbackQueryHandler(handle_trade_callback))

            logger.info("Telegram trading bot started, polling for commands...")
            app.run_polling(drop_pending_updates=True)

        except Exception as e:
            logger.error(f"Telegram bot failed to start: {e}")

    bot_thread = threading.Thread(target=_run_bot, daemon=True)
    bot_thread.start()
    logger.info("Telegram bot thread launched")
