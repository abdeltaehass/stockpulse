import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from stock_data import StockData
from sklearn.ensemble import RandomForestClassifier


class StockPredictor:
    WEIGHTS = {
        'historical_pattern': 0.12,
        'ml_prediction':      0.10,
        'rsi':                0.12,
        'ma_trend':           0.12,
        'macd':               0.10,
        'sentiment':          0.10,
        'bollinger':          0.08,
        'weekly_trend':       0.07,
        'volume_trend':       0.06,
        'weekday':            0.05,
        'seasonal':           0.04,
        'atr_volatility':     0.04,
    }

    def __init__(self, ticker):
        self.ticker = ticker.upper()
        self.stock = StockData(self.ticker)
        self._hist_2y = None
        self._hist_5y = None

    def _get_history_2y(self):
        if self._hist_2y is None:
            self._hist_2y = self.stock.get_historical_data(period='2y')
        return self._hist_2y

    def _get_history_5y(self):
        if self._hist_5y is None:
            self._hist_5y = self.stock.get_historical_data(period='5y')
        return self._hist_5y

    def analyze_weekday(self):
        try:
            hist = self._get_history_2y()
            if hist is None or len(hist) < 30:
                return self._empty_weekday_result()

            hist = hist.copy()
            hist['daily_return'] = hist['Close'].pct_change()
            hist = hist.dropna(subset=['daily_return'])
            hist['weekday'] = hist.index.dayofweek

            six_months_ago = datetime.now() - timedelta(days=180)
            hist['recency_weight'] = np.where(hist.index >= six_months_ago, 2.0, 1.0)

            weekday_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
            weekday_stats = {}

            for day in range(5):
                day_data = hist[hist['weekday'] == day]
                if len(day_data) > 0:
                    weighted_return = np.average(
                        day_data['daily_return'], weights=day_data['recency_weight']
                    )
                    positive_mask = (day_data['daily_return'] > 0).astype(float)
                    weighted_pct_positive = np.average(
                        positive_mask, weights=day_data['recency_weight']
                    ) * 100
                    weekday_stats[day] = {
                        'name': weekday_names[day],
                        'avg_return': round(float(weighted_return * 100), 4),
                        'pct_positive': round(float(weighted_pct_positive), 1),
                        'count': int(len(day_data))
                    }

            today = datetime.now().weekday()
            if today > 4:
                today = 4

            today_stats = weekday_stats.get(today, {})
            pct_positive = today_stats.get('pct_positive', 50.0)

            signal = max(-1.0, min(1.0, (pct_positive - 50.0) / 25.0))

            return {
                'weekday_stats': weekday_stats,
                'today_weekday': today,
                'today_name': weekday_names[min(today, 4)],
                'today_avg_return': today_stats.get('avg_return', 0.0),
                'today_pct_positive': pct_positive,
                'signal': round(signal, 3)
            }
        except Exception:
            return self._empty_weekday_result()

    def analyze_seasonal(self):
        try:
            hist = self._get_history_5y()
            if hist is None or len(hist) < 252:
                return self._empty_seasonal_result()

            hist = hist.copy()

            monthly = hist['Close'].resample('ME').last()
            monthly_returns = monthly.pct_change().dropna()
            monthly_returns_df = pd.DataFrame({
                'return': monthly_returns,
                'month': monthly_returns.index.month
            })

            two_years_ago = datetime.now() - timedelta(days=730)
            monthly_returns_df['recency_weight'] = np.where(
                monthly_returns_df.index >= two_years_ago, 2.0, 1.0
            )

            month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                           'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

            monthly_stats = {}
            for m in range(1, 13):
                m_data = monthly_returns_df[monthly_returns_df['month'] == m]
                if len(m_data) > 0:
                    weighted_avg = np.average(m_data['return'], weights=m_data['recency_weight'])
                    positive_mask = (m_data['return'] > 0).astype(float)
                    weighted_pct = np.average(positive_mask, weights=m_data['recency_weight']) * 100
                    monthly_stats[m] = {
                        'name': month_names[m - 1],
                        'avg_return': round(float(weighted_avg * 100), 2),
                        'pct_positive': round(float(weighted_pct), 1),
                        'years': int(len(m_data))
                    }

            current_month = datetime.now().month
            current_month_stats = monthly_stats.get(current_month, {})

            now = datetime.now()
            ytd_return = 0.0
            last_ytd = 0.0
            try:
                current_year_data = hist.loc[str(now.year)]['Close']
                if len(current_year_data) > 1:
                    ytd_return = (float(current_year_data.iloc[-1]) / float(current_year_data.iloc[0]) - 1) * 100

                last_year = now.year - 1
                last_year_data = hist.loc[f'{last_year}-01':f'{last_year}-{now.month:02d}-{now.day:02d}']['Close']
                if len(last_year_data) > 1:
                    last_ytd = (float(last_year_data.iloc[-1]) / float(last_year_data.iloc[0]) - 1) * 100
            except (KeyError, IndexError):
                pass

            ytd_vs_last = round(ytd_return - last_ytd, 2)

            weekly = hist['Close'].resample('W').last().tail(5)
            weekly_returns = weekly.pct_change().dropna()
            up_weeks = 0
            down_weeks = 0
            direction = 'flat'
            avg_weekly_return = 0.0
            streak = 0

            if len(weekly_returns) >= 2:
                up_weeks = int((weekly_returns > 0).sum())
                down_weeks = int((weekly_returns < 0).sum())
                direction = 'up' if up_weeks > down_weeks else ('down' if down_weeks > up_weeks else 'flat')
                avg_weekly_return = round(float(weekly_returns.mean() * 100), 2)

                for ret in reversed(weekly_returns.values):
                    if (direction == 'up' and ret > 0) or (direction == 'down' and ret < 0):
                        streak += 1
                    else:
                        break

            weekly_trend = {
                'direction': direction,
                'streak': streak,
                'avg_weekly_return': avg_weekly_return,
                'up_weeks': up_weeks,
                'down_weeks': down_weeks
            }

            month_pct = current_month_stats.get('pct_positive', 50.0)
            month_signal = (month_pct - 50.0) / 25.0

            if direction == 'up':
                weekly_signal = 0.5 + (streak * 0.1)
            elif direction == 'down':
                weekly_signal = -0.5 - (streak * 0.1)
            else:
                weekly_signal = 0.0

            ytd_signal = max(-1.0, min(1.0, ytd_vs_last / 20.0))
            combined = month_signal * 0.4 + weekly_signal * 0.3 + ytd_signal * 0.3
            signal = round(max(-1.0, min(1.0, combined)), 3)

            return {
                'monthly_stats': monthly_stats,
                'current_month': current_month,
                'current_month_name': month_names[current_month - 1],
                'current_month_avg': current_month_stats.get('avg_return', 0.0),
                'current_month_pct_positive': month_pct,
                'ytd_return': round(ytd_return, 2),
                'last_year_ytd': round(last_ytd, 2),
                'ytd_vs_last_year': ytd_vs_last,
                'weekly_trend': weekly_trend,
                'signal': signal
            }
        except Exception:
            return self._empty_seasonal_result()

    def analyze_technical(self):
        try:
            hist = self._get_history_2y()
            if hist is None or len(hist) < 200:
                return self._empty_technical_result()

            close = hist['Close']
            current_price = float(close.iloc[-1])

            # RSI (14-day)
            delta = close.diff()
            gain = delta.where(delta > 0, 0.0)
            loss = (-delta).where(delta < 0, 0.0)
            avg_gain = gain.rolling(window=14).mean()
            avg_loss = loss.rolling(window=14).mean()
            rs = avg_gain / avg_loss
            rsi_series = 100 - (100 / (1 + rs))
            rsi_value = round(float(rsi_series.iloc[-1]), 1)

            if rsi_value < 30:
                rsi_interp = 'Oversold'
                rsi_signal = 0.5 + (30 - rsi_value) / 60
            elif rsi_value > 70:
                rsi_interp = 'Overbought'
                rsi_signal = -0.5 - (rsi_value - 70) / 60
            else:
                rsi_interp = 'Neutral'
                rsi_signal = (50 - rsi_value) / 40

            rsi_signal = round(max(-1.0, min(1.0, rsi_signal)), 3)

            # MACD (12, 26, 9)
            ema_12 = close.ewm(span=12, adjust=False).mean()
            ema_26 = close.ewm(span=26, adjust=False).mean()
            macd_line = ema_12 - ema_26
            signal_line = macd_line.ewm(span=9, adjust=False).mean()
            histogram = macd_line - signal_line

            macd_val = round(float(macd_line.iloc[-1]), 4)
            signal_val = round(float(signal_line.iloc[-1]), 4)
            hist_val = round(float(histogram.iloc[-1]), 4)

            hist_normalized = hist_val / current_price * 100 if current_price else 0
            if hist_val > 0:
                macd_interp = 'Bullish'
                macd_signal = min(1.0, hist_normalized * 10)
            elif hist_val < 0:
                macd_interp = 'Bearish'
                macd_signal = max(-1.0, hist_normalized * 10)
            else:
                macd_interp = 'Neutral'
                macd_signal = 0.0

            recent_hist = histogram.tail(3).values
            if len(recent_hist) >= 2:
                if recent_hist[-2] < 0 and recent_hist[-1] > 0:
                    macd_interp = 'Bullish Crossover'
                    macd_signal = min(1.0, macd_signal + 0.3)
                elif recent_hist[-2] > 0 and recent_hist[-1] < 0:
                    macd_interp = 'Bearish Crossover'
                    macd_signal = max(-1.0, macd_signal - 0.3)

            macd_signal = round(max(-1.0, min(1.0, macd_signal)), 3)

            # Moving Averages
            ma20 = round(float(close.rolling(20).mean().iloc[-1]), 2)
            ma50 = round(float(close.rolling(50).mean().iloc[-1]), 2)
            ma200 = round(float(close.rolling(200).mean().iloc[-1]), 2)

            above_ma20 = current_price > ma20
            above_ma50 = current_price > ma50
            above_ma200 = current_price > ma200
            above_count = sum([above_ma20, above_ma50, above_ma200])

            crossovers = []
            ma50_series = close.rolling(50).mean()
            ma200_series = close.rolling(200).mean()
            if len(ma50_series) >= 5 and len(ma200_series) >= 5:
                ma50_recent = ma50_series.tail(5).values
                ma200_recent = ma200_series.tail(5).values
                if ma50_recent[-2] < ma200_recent[-2] and ma50_recent[-1] > ma200_recent[-1]:
                    crossovers.append('Golden Cross (MA50 crossed above MA200)')
                elif ma50_recent[-2] > ma200_recent[-2] and ma50_recent[-1] < ma200_recent[-1]:
                    crossovers.append('Death Cross (MA50 crossed below MA200)')

            if above_count == 3:
                position = 'Strong Uptrend'
            elif above_count == 2:
                position = 'Moderate Uptrend'
            elif above_count == 1:
                position = 'Moderate Downtrend'
            else:
                position = 'Strong Downtrend'

            alignment_bonus = 0.0
            if ma20 > ma50 > ma200:
                alignment_bonus = 0.2
            elif ma20 < ma50 < ma200:
                alignment_bonus = -0.2

            ma_signal = (above_count - 1.5) / 1.5 + alignment_bonus
            ma_signal = round(max(-1.0, min(1.0, ma_signal)), 3)

            return {
                'rsi': {
                    'value': rsi_value,
                    'interpretation': rsi_interp,
                    'signal': rsi_signal
                },
                'macd': {
                    'macd_line': macd_val,
                    'signal_line': signal_val,
                    'histogram': hist_val,
                    'interpretation': macd_interp,
                    'signal': macd_signal
                },
                'ma_trend': {
                    'ma20': ma20,
                    'ma50': ma50,
                    'ma200': ma200,
                    'current_price': round(current_price, 2),
                    'above_ma20': above_ma20,
                    'above_ma50': above_ma50,
                    'above_ma200': above_ma200,
                    'position': position,
                    'crossovers': crossovers,
                    'signal': ma_signal
                }
            }
        except Exception:
            return self._empty_technical_result()

    def analyze_bollinger(self):
        try:
            hist = self._get_history_2y()
            if hist is None or len(hist) < 20:
                return {'signal': 0.0, 'upper': 0, 'lower': 0, 'middle': 0,
                        'bandwidth': 0, 'pct_b': 0.5, 'squeeze': False,
                        'interpretation': 'Insufficient Data'}

            close = hist['Close']
            current_price = float(close.iloc[-1])

            ma20 = close.rolling(20).mean()
            std20 = close.rolling(20).std()
            upper = ma20 + 2 * std20
            lower = ma20 - 2 * std20

            upper_val = float(upper.iloc[-1])
            lower_val = float(lower.iloc[-1])
            middle_val = float(ma20.iloc[-1])

            band_width = upper_val - lower_val
            pct_b = (current_price - lower_val) / band_width if band_width > 0 else 0.5

            bandwidth_ratio = band_width / middle_val if middle_val > 0 else 0
            bw_series = ((upper - lower) / ma20).dropna()
            avg_bw = float(bw_series.tail(120).mean()) if len(bw_series) >= 120 else float(bw_series.mean())
            squeeze = bandwidth_ratio < avg_bw * 0.75

            if pct_b < 0.2:
                signal = 0.5 + (0.2 - pct_b) * 2.5
                interpretation = 'Near Lower Band (Oversold)'
            elif pct_b > 0.8:
                signal = -0.5 - (pct_b - 0.8) * 2.5
                interpretation = 'Near Upper Band (Overbought)'
            else:
                signal = (0.5 - pct_b) * 1.0
                interpretation = 'Within Bands'

            if squeeze:
                interpretation += ' (Squeeze)'
                signal *= 0.5

            signal = round(max(-1.0, min(1.0, signal)), 3)

            return {
                'signal': signal,
                'upper': round(upper_val, 2),
                'lower': round(lower_val, 2),
                'middle': round(middle_val, 2),
                'bandwidth': round(bandwidth_ratio * 100, 2),
                'pct_b': round(pct_b, 3),
                'squeeze': squeeze,
                'interpretation': interpretation
            }
        except Exception:
            return {'signal': 0.0, 'upper': 0, 'lower': 0, 'middle': 0,
                    'bandwidth': 0, 'pct_b': 0.5, 'squeeze': False,
                    'interpretation': 'Error'}

    def analyze_volume_trend(self):
        try:
            hist = self._get_history_2y()
            if hist is None or len(hist) < 30:
                return {'signal': 0.0, 'volume_ratio': 1.0, 'trend': 'Normal',
                        'interpretation': 'Insufficient Data'}

            volume = hist['Volume']
            close = hist['Close']

            avg_vol_20 = float(volume.tail(20).mean())
            avg_vol_5 = float(volume.tail(5).mean())
            today_vol = float(volume.iloc[-1])

            volume_ratio = avg_vol_5 / avg_vol_20 if avg_vol_20 > 0 else 1.0

            price_change_5d = 0
            if len(close) >= 6:
                price_change_5d = (float(close.iloc[-1]) - float(close.iloc[-6])) / float(close.iloc[-6])

            if volume_ratio > 1.5:
                trend = 'High Volume'
                if price_change_5d > 0:
                    signal = min(1.0, (volume_ratio - 1.0) * 0.5)
                else:
                    signal = max(-1.0, -(volume_ratio - 1.0) * 0.5)
            elif volume_ratio < 0.6:
                trend = 'Low Volume'
                signal = 0.0
            else:
                trend = 'Normal Volume'
                if price_change_5d > 0.02:
                    signal = 0.2
                elif price_change_5d < -0.02:
                    signal = -0.2
                else:
                    signal = 0.0

            signal = round(max(-1.0, min(1.0, signal)), 3)

            return {
                'signal': signal,
                'volume_ratio': round(volume_ratio, 2),
                'avg_volume_20d': int(avg_vol_20),
                'avg_volume_5d': int(avg_vol_5),
                'today_volume': int(today_vol),
                'trend': trend,
                'interpretation': f'{trend} ({volume_ratio:.1f}x avg)'
            }
        except Exception:
            return {'signal': 0.0, 'volume_ratio': 1.0, 'trend': 'Normal',
                    'interpretation': 'Error'}

    def analyze_atr(self):
        try:
            hist = self._get_history_2y()
            if hist is None or len(hist) < 30:
                return {'signal': 0.0, 'atr': 0, 'atr_pct': 0,
                        'volatility': 'Unknown', 'interpretation': 'Insufficient Data'}

            high = hist['High']
            low = hist['Low']
            close = hist['Close']
            current_price = float(close.iloc[-1])

            tr1 = high - low
            tr2 = (high - close.shift(1)).abs()
            tr3 = (low - close.shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

            atr_14 = float(tr.rolling(14).mean().iloc[-1])
            atr_50 = float(tr.rolling(50).mean().iloc[-1]) if len(tr) >= 50 else atr_14

            atr_pct = (atr_14 / current_price) * 100 if current_price > 0 else 0
            atr_ratio = atr_14 / atr_50 if atr_50 > 0 else 1.0

            if atr_ratio > 1.5:
                volatility = 'Very High'
                signal = -0.4
            elif atr_ratio > 1.2:
                volatility = 'High'
                signal = -0.2
            elif atr_ratio < 0.7:
                volatility = 'Low'
                signal = 0.2
            elif atr_ratio < 0.85:
                volatility = 'Below Average'
                signal = 0.1
            else:
                volatility = 'Normal'
                signal = 0.0

            signal = round(max(-1.0, min(1.0, signal)), 3)

            return {
                'signal': signal,
                'atr': round(atr_14, 2),
                'atr_pct': round(atr_pct, 2),
                'atr_ratio': round(atr_ratio, 2),
                'volatility': volatility,
                'interpretation': f'{volatility} Volatility (ATR {atr_pct:.1f}% of price)'
            }
        except Exception:
            return {'signal': 0.0, 'atr': 0, 'atr_pct': 0,
                    'volatility': 'Unknown', 'interpretation': 'Error'}

    def analyze_historical_pattern(self):
        try:
            hist = self._get_history_2y()
            if hist is None or len(hist) < 252:
                return self._empty_historical_result()

            df = hist.copy()
            df['daily_return'] = df['Close'].pct_change()

            today_idx = len(df) - 1

            lookbacks = [
                {'name': '1 Week Ago',   'days': 5,   'weight': 0.30},
                {'name': '1 Month Ago',  'days': 21,  'weight': 0.25},
                {'name': '3 Months Ago', 'days': 63,  'weight': 0.20},
                {'name': '6 Months Ago', 'days': 126, 'weight': 0.15},
                {'name': '1 Year Ago',   'days': 252, 'weight': 0.10},
            ]

            pattern_details = []
            weighted_signal = 0.0
            total_weight = 0.0

            for lb in lookbacks:
                target_idx = today_idx - lb['days']
                if target_idx < 1 or target_idx >= len(df):
                    continue

                day_return = float(df['daily_return'].iloc[target_idx])

                context_start = max(1, target_idx - 1)
                context_end = min(len(df) - 1, target_idx + 1)
                context_returns = df['daily_return'].iloc[context_start:context_end + 1]
                context_return = float(context_returns.sum())

                combined_return = day_return * 0.6 + context_return * 0.4

                signal = max(-1.0, min(1.0, combined_return / 0.02))

                weighted_signal += signal * lb['weight']
                total_weight += lb['weight']

                pattern_details.append({
                    'period': lb['name'],
                    'day_return': round(day_return * 100, 3),
                    'context_return': round(context_return * 100, 3),
                    'signal': round(signal, 3),
                    'weight': lb['weight']
                })

            if total_weight > 0:
                final_signal = weighted_signal / total_weight
            else:
                final_signal = 0.0

            final_signal = round(max(-1.0, min(1.0, final_signal)), 3)

            return {
                'signal': final_signal,
                'lookbacks': pattern_details,
                'interpretation': self._historical_interpretation(final_signal),
            }
        except Exception:
            return self._empty_historical_result()

    @staticmethod
    def _historical_interpretation(signal):
        if signal > 0.3:
            return 'Historical dates were strongly positive'
        elif signal > 0.1:
            return 'Historical dates were moderately positive'
        elif signal > -0.1:
            return 'Historical dates were mixed'
        elif signal > -0.3:
            return 'Historical dates were moderately negative'
        else:
            return 'Historical dates were strongly negative'

    def _empty_historical_result(self):
        return {
            'signal': 0.0,
            'lookbacks': [],
            'interpretation': 'Insufficient historical data',
        }

    def analyze_ml(self):
        try:
            hist = self._get_history_2y()
            if hist is None or len(hist) < 300:
                return self._empty_ml_result()

            df = hist.copy()
            close = df['Close']
            high = df['High']
            low = df['Low']
            volume = df['Volume']

            df['return_1d'] = close.pct_change(1)
            df['return_5d'] = close.pct_change(5)
            df['return_20d'] = close.pct_change(20)

            delta = close.diff()
            gain = delta.where(delta > 0, 0.0)
            loss = (-delta).where(delta < 0, 0.0)
            avg_gain = gain.rolling(14).mean()
            avg_loss = loss.rolling(14).mean()
            rs = avg_gain / avg_loss
            df['rsi'] = 100 - (100 / (1 + rs))

            ema12 = close.ewm(span=12, adjust=False).mean()
            ema26 = close.ewm(span=26, adjust=False).mean()
            macd_line = ema12 - ema26
            signal_line = macd_line.ewm(span=9, adjust=False).mean()
            df['macd_hist_norm'] = (macd_line - signal_line) / close * 100

            ma20 = close.rolling(20).mean()
            std20 = close.rolling(20).std()
            upper_bb = ma20 + 2 * std20
            lower_bb = ma20 - 2 * std20
            bb_width = upper_bb - lower_bb
            df['bb_pct_b'] = (close - lower_bb) / bb_width.where(bb_width > 0, 1)

            vol_ma5 = volume.rolling(5).mean()
            vol_ma20 = volume.rolling(20).mean()
            df['volume_ratio'] = vol_ma5 / vol_ma20.where(vol_ma20 > 0, 1)

            df['price_ma20_ratio'] = close / ma20.where(ma20 > 0, 1)
            ma50 = close.rolling(50).mean()
            df['price_ma50_ratio'] = close / ma50.where(ma50 > 0, 1)
            ma200 = close.rolling(200).mean()
            df['price_ma200_ratio'] = close / ma200.where(ma200 > 0, 1)

            tr1 = high - low
            tr2 = (high - close.shift(1)).abs()
            tr3 = (low - close.shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr_14 = tr.rolling(14).mean()
            atr_50 = tr.rolling(50).mean()
            df['atr_ratio'] = atr_14 / atr_50.where(atr_50 > 0, 1)

            df['volatility_20d'] = df['return_1d'].rolling(20).std()

            df['dow'] = df.index.dayofweek
            for d in range(5):
                df[f'dow_{d}'] = (df['dow'] == d).astype(int)

            df['month'] = df.index.month
            for m in range(1, 13):
                df[f'month_{m}'] = (df['month'] == m).astype(int)

            df['target'] = (close.shift(-1) > close).astype(int)

            feature_cols = [
                'rsi', 'macd_hist_norm', 'bb_pct_b', 'volume_ratio',
                'price_ma20_ratio', 'price_ma50_ratio', 'price_ma200_ratio',
                'return_1d', 'return_5d', 'return_20d',
                'atr_ratio', 'volatility_20d',
            ] + [f'dow_{d}' for d in range(5)] + [f'month_{m}' for m in range(1, 13)]

            df_clean = df.dropna(subset=feature_cols + ['target'])

            if len(df_clean) < 200:
                return self._empty_ml_result()

            X = df_clean[feature_cols].values
            y = df_clean['target'].values

            split_idx = int(len(X) * 0.8)
            X_train, X_val = X[:split_idx], X[split_idx:]
            y_train, y_val = y[:split_idx], y[split_idx:]

            model = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                min_samples_leaf=5,
                random_state=42,
                n_jobs=-1
            )
            model.fit(X_train, y_train)

            accuracy = float(model.score(X_val, y_val))

            latest_features = df[feature_cols].iloc[-1:]
            if latest_features.isnull().any(axis=1).iloc[0]:
                return self._empty_ml_result()

            proba = model.predict_proba(latest_features.values)[0]
            prob_positive = float(proba[1]) if len(proba) > 1 else 0.5

            signal = (prob_positive - 0.5) * 2.0
            signal = round(max(-1.0, min(1.0, signal)), 3)

            accuracy_multiplier = max(0.0, min(1.0, (accuracy - 0.5) * 4.0))
            adjusted_signal = round(signal * max(0.3, accuracy_multiplier), 3)

            return {
                'signal': adjusted_signal,
                'raw_signal': signal,
                'probability_positive': round(prob_positive, 3),
                'model_accuracy': round(accuracy * 100, 1),
                'training_samples': len(X_train),
                'validation_samples': len(X_val),
                'interpretation': self._ml_interpretation(adjusted_signal, accuracy),
            }
        except Exception:
            return self._empty_ml_result()

    @staticmethod
    def _ml_interpretation(signal, accuracy):
        acc_pct = round(accuracy * 100, 1)
        if abs(signal) < 0.1:
            direction = 'neutral'
        elif signal > 0:
            direction = 'bullish'
        else:
            direction = 'bearish'
        return f'ML model ({acc_pct}% accurate) predicts {direction}'

    def _empty_ml_result(self):
        return {
            'signal': 0.0,
            'raw_signal': 0.0,
            'probability_positive': 0.5,
            'model_accuracy': 50.0,
            'training_samples': 0,
            'validation_samples': 0,
            'interpretation': 'Insufficient data for ML model',
        }

    def analyze_sentiment(self):
        try:
            articles = self.stock.get_news(limit=25)
            if not articles:
                return {
                    'articles_analyzed': 0,
                    'positive_count': 0,
                    'negative_count': 0,
                    'neutral_count': 0,
                    'weighted_score': 0.0,
                    'signal': 0.0,
                    'recent_headlines': []
                }

            now = datetime.now().timestamp()
            sentiment_map = {'positive': 1.0, 'neutral': 0.0, 'negative': -1.0}

            weighted_scores = []
            weights = []
            pos_count = 0
            neg_count = 0
            neu_count = 0
            headlines = []

            for article in articles:
                sentiment = article.get('sentiment', 'neutral')
                score = article.get('sentiment_score', sentiment_map.get(sentiment, 0.0))
                published = article.get('published', 0)

                if published > 0:
                    age_hours = (now - published) / 3600
                else:
                    age_hours = 168

                if age_hours <= 24:
                    weight = 1.0
                elif age_hours <= 72:
                    weight = 0.7
                elif age_hours <= 168:
                    weight = 0.4
                else:
                    weight = 0.2

                weighted_scores.append(score * weight)
                weights.append(weight)

                if sentiment == 'positive':
                    pos_count += 1
                elif sentiment == 'negative':
                    neg_count += 1
                else:
                    neu_count += 1

                headlines.append({
                    'title': article.get('title', ''),
                    'sentiment': sentiment,
                    'age_hours': round(age_hours, 1)
                })

            total_weight = sum(weights)
            weighted_avg = sum(weighted_scores) / total_weight if total_weight > 0 else 0.0
            signal = round(max(-1.0, min(1.0, weighted_avg)), 3)

            return {
                'articles_analyzed': len(articles),
                'positive_count': pos_count,
                'negative_count': neg_count,
                'neutral_count': neu_count,
                'weighted_score': round(weighted_avg, 3),
                'signal': signal,
                'recent_headlines': headlines[:5]
            }
        except Exception:
            return {
                'articles_analyzed': 0,
                'positive_count': 0,
                'negative_count': 0,
                'neutral_count': 0,
                'weighted_score': 0.0,
                'signal': 0.0,
                'recent_headlines': []
            }

    def get_prediction(self):
        weekday = self.analyze_weekday()
        seasonal = self.analyze_seasonal()
        technical = self.analyze_technical()
        sentiment = self.analyze_sentiment()
        bollinger = self.analyze_bollinger()
        volume_trend = self.analyze_volume_trend()
        atr = self.analyze_atr()
        historical_pattern = self.analyze_historical_pattern()
        ml_result = self.analyze_ml()

        signals = {
            'historical_pattern': historical_pattern.get('signal', 0.0),
            'ml_prediction': ml_result.get('signal', 0.0),
            'weekday': weekday.get('signal', 0.0),
            'seasonal': seasonal.get('signal', 0.0),
            'weekly_trend': 0.0,
            'rsi': technical.get('rsi', {}).get('signal', 0.0),
            'macd': technical.get('macd', {}).get('signal', 0.0),
            'ma_trend': technical.get('ma_trend', {}).get('signal', 0.0),
            'sentiment': sentiment.get('signal', 0.0),
            'bollinger': bollinger.get('signal', 0.0),
            'volume_trend': volume_trend.get('signal', 0.0),
            'atr_volatility': atr.get('signal', 0.0),
        }

        weekly = seasonal.get('weekly_trend', {})
        if weekly.get('direction') == 'up':
            signals['weekly_trend'] = min(1.0, 0.3 + weekly.get('streak', 0) * 0.15)
        elif weekly.get('direction') == 'down':
            signals['weekly_trend'] = max(-1.0, -0.3 - weekly.get('streak', 0) * 0.15)

        combined_score = sum(
            signals[key] * self.WEIGHTS[key]
            for key in self.WEIGHTS
        )
        combined_score = round(max(-1.0, min(1.0, combined_score)), 3)

        if combined_score > 0.25:
            recommendation = 'Buy'
        elif combined_score < -0.25:
            recommendation = 'Sell'
        else:
            recommendation = 'Hold'

        if combined_score > 0:
            agreeing = sum(1 for s in signals.values() if s > 0)
            strongly_opposing = sum(1 for s in signals.values() if s < -0.3)
        elif combined_score < 0:
            agreeing = sum(1 for s in signals.values() if s < 0)
            strongly_opposing = sum(1 for s in signals.values() if s > 0.3)
        else:
            agreeing = sum(1 for s in signals.values() if abs(s) < 0.1)
            strongly_opposing = sum(1 for s in signals.values() if abs(s) > 0.3)

        total_signals = len(signals)
        agreement_ratio = agreeing / total_signals
        disagreement_penalty = strongly_opposing * 0.08
        raw_confidence = abs(combined_score) * agreement_ratio
        confidence = round(min(95.0, max(15.0, raw_confidence * 100 + 15 - (disagreement_penalty * 100))), 1)

        signal_breakdown = {
            'historical_pattern': {
                'name': 'Historical Pattern',
                'signal': signals['historical_pattern'],
                'label': self._signal_label(signals['historical_pattern']),
                'weight': self.WEIGHTS['historical_pattern'],
                'detail': historical_pattern.get('interpretation', 'N/A')
            },
            'ml_prediction': {
                'name': 'ML Prediction',
                'signal': signals['ml_prediction'],
                'label': self._signal_label(signals['ml_prediction']),
                'weight': self.WEIGHTS['ml_prediction'],
                'detail': ml_result.get('interpretation', 'N/A')
            },
            'weekday': {
                'name': 'Day-of-Week Pattern',
                'signal': signals['weekday'],
                'label': self._signal_label(signals['weekday']),
                'weight': self.WEIGHTS['weekday'],
                'detail': f"{weekday.get('today_name', 'N/A')}: "
                          f"{weekday.get('today_pct_positive', 50)}% historically positive"
            },
            'seasonal': {
                'name': 'Seasonal Pattern',
                'signal': signals['seasonal'],
                'label': self._signal_label(signals['seasonal']),
                'weight': self.WEIGHTS['seasonal'],
                'detail': f"{seasonal.get('current_month_name', 'N/A')}: "
                          f"avg {seasonal.get('current_month_avg', 0)}% return"
            },
            'weekly_trend': {
                'name': 'Weekly Momentum',
                'signal': signals['weekly_trend'],
                'label': self._signal_label(signals['weekly_trend']),
                'weight': self.WEIGHTS['weekly_trend'],
                'detail': f"{weekly.get('direction', 'flat').title()} "
                          f"({weekly.get('streak', 0)} week streak)"
            },
            'rsi': {
                'name': 'RSI (14)',
                'signal': signals['rsi'],
                'label': self._signal_label(signals['rsi']),
                'weight': self.WEIGHTS['rsi'],
                'detail': f"RSI: {technical.get('rsi', {}).get('value', 'N/A')} "
                          f"({technical.get('rsi', {}).get('interpretation', 'N/A')})"
            },
            'macd': {
                'name': 'MACD',
                'signal': signals['macd'],
                'label': self._signal_label(signals['macd']),
                'weight': self.WEIGHTS['macd'],
                'detail': technical.get('macd', {}).get('interpretation', 'N/A')
            },
            'ma_trend': {
                'name': 'Moving Averages',
                'signal': signals['ma_trend'],
                'label': self._signal_label(signals['ma_trend']),
                'weight': self.WEIGHTS['ma_trend'],
                'detail': technical.get('ma_trend', {}).get('position', 'N/A')
            },
            'sentiment': {
                'name': 'News Sentiment',
                'signal': signals['sentiment'],
                'label': self._signal_label(signals['sentiment']),
                'weight': self.WEIGHTS['sentiment'],
                'detail': f"{sentiment.get('positive_count', 0)} positive, "
                          f"{sentiment.get('negative_count', 0)} negative, "
                          f"{sentiment.get('neutral_count', 0)} neutral"
            },
            'bollinger': {
                'name': 'Bollinger Bands',
                'signal': signals['bollinger'],
                'label': self._signal_label(signals['bollinger']),
                'weight': self.WEIGHTS['bollinger'],
                'detail': f"BB: {bollinger.get('interpretation', 'N/A')}, "
                          f"%B: {bollinger.get('pct_b', 'N/A')}"
            },
            'volume_trend': {
                'name': 'Volume Trend',
                'signal': signals['volume_trend'],
                'label': self._signal_label(signals['volume_trend']),
                'weight': self.WEIGHTS['volume_trend'],
                'detail': volume_trend.get('interpretation', 'N/A')
            },
            'atr_volatility': {
                'name': 'ATR Volatility',
                'signal': signals['atr_volatility'],
                'label': self._signal_label(signals['atr_volatility']),
                'weight': self.WEIGHTS['atr_volatility'],
                'detail': atr.get('interpretation', 'N/A')
            },
        }

        summary = self._generate_summary(
            recommendation, confidence, combined_score, signals, technical, seasonal, weekday
        )

        analyst_targets = self.get_analyst_targets()

        return {
            'ticker': self.ticker,
            'recommendation': recommendation,
            'confidence': confidence,
            'combined_score': combined_score,
            'signal_breakdown': signal_breakdown,
            'weekday_analysis': weekday,
            'seasonal_analysis': seasonal,
            'technical_analysis': technical,
            'sentiment_analysis': sentiment,
            'historical_analysis': historical_pattern,
            'ml_analysis': ml_result,
            'analyst_targets': analyst_targets,
            'summary': summary,
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'disclaimer': 'This is a statistical analysis for educational purposes only. '
                          'Not financial advice. Past performance does not guarantee future results.'
        }

    @staticmethod
    def _signal_label(signal):
        if signal > 0.5:
            return 'Strong Bullish'
        elif signal > 0.15:
            return 'Bullish'
        elif signal > -0.15:
            return 'Neutral'
        elif signal > -0.5:
            return 'Bearish'
        else:
            return 'Strong Bearish'

    @staticmethod
    def _generate_summary(recommendation, confidence, score, signals, technical, seasonal, weekday):
        direction = 'upward' if score > 0 else 'downward' if score < 0 else 'sideways'

        strongest_key = max(signals, key=lambda k: abs(signals[k]))
        name_map = {
            'historical_pattern': 'historical patterns',
            'ml_prediction': 'ML model prediction',
            'weekday': 'day-of-week patterns',
            'seasonal': 'seasonal trends',
            'weekly_trend': 'weekly momentum',
            'rsi': 'RSI',
            'macd': 'MACD',
            'ma_trend': 'moving average trends',
            'sentiment': 'news sentiment',
            'bollinger': 'Bollinger Bands',
            'volume_trend': 'volume trend',
            'atr_volatility': 'ATR volatility'
        }
        strongest_name = name_map.get(strongest_key, strongest_key)

        rsi_val = technical.get('rsi', {}).get('value', 50)
        ma_position = technical.get('ma_trend', {}).get('position', 'Unknown')

        return (
            f"Based on analysis of {len(signals)} signals, the overall outlook is {direction} "
            f"with a {recommendation} recommendation at {confidence}% confidence. "
            f"The strongest signal comes from {strongest_name}. "
            f"RSI is at {rsi_val} and the stock is in a {ma_position}."
        )

    def _empty_weekday_result(self):
        today = min(datetime.now().weekday(), 4)
        return {
            'weekday_stats': {},
            'today_weekday': today,
            'today_name': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'][today],
            'today_avg_return': 0.0,
            'today_pct_positive': 50.0,
            'signal': 0.0,
            'error': 'Insufficient historical data'
        }

    def _empty_seasonal_result(self):
        return {
            'monthly_stats': {},
            'current_month': datetime.now().month,
            'current_month_name': '',
            'current_month_avg': 0.0,
            'current_month_pct_positive': 50.0,
            'ytd_return': 0.0,
            'last_year_ytd': 0.0,
            'ytd_vs_last_year': 0.0,
            'weekly_trend': {'direction': 'flat', 'streak': 0, 'avg_weekly_return': 0.0, 'up_weeks': 0, 'down_weeks': 0},
            'signal': 0.0,
            'error': 'Insufficient historical data'
        }

    def _empty_technical_result(self):
        return {
            'rsi': {'value': 50, 'interpretation': 'Insufficient Data', 'signal': 0.0},
            'macd': {'macd_line': 0, 'signal_line': 0, 'histogram': 0, 'interpretation': 'Insufficient Data', 'signal': 0.0},
            'ma_trend': {'ma20': 0, 'ma50': 0, 'ma200': 0, 'current_price': 0,
                         'above_ma20': False, 'above_ma50': False, 'above_ma200': False,
                         'position': 'Unknown', 'crossovers': [], 'signal': 0.0}
        }

    def get_analyst_targets(self):
        targets = self.stock.get_analyst_targets()
        if not targets:
            return None

        current = targets['current_price']
        target_mean = targets['target_mean']
        target_low = targets['target_low']
        target_high = targets['target_high']

        annual_change = target_mean - current
        low_change = target_low - current
        high_change = target_high - current

        projections = []

        periods = [
            {'name': '1 Week', 'fraction': 1/52},
            {'name': '1 Month', 'fraction': 1/12},
            {'name': '6 Months', 'fraction': 0.5},
            {'name': '1 Year', 'fraction': 1.0},
            {'name': '2 Years', 'fraction': 2.0},
        ]

        for period in periods:
            frac = period['fraction']
            proj_low = round(current + low_change * frac, 2)
            proj_mean = round(current + annual_change * frac, 2)
            proj_high = round(current + high_change * frac, 2)

            projections.append({
                'period': period['name'],
                'low': proj_low,
                'mean': proj_mean,
                'high': proj_high,
                'upside_pct': round((proj_mean - current) / current * 100, 1)
            })

        return {
            'current_price': current,
            'target_low': target_low,
            'target_high': target_high,
            'target_mean': target_mean,
            'target_median': targets['target_median'],
            'num_analysts': targets['num_analysts'],
            'projections': projections,
            'upside_pct': round((target_mean - current) / current * 100, 1)
        }
