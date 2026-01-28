import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from stock_data import StockData


class StockPredictor:
    WEIGHTS = {
        'weekday':      0.10,
        'seasonal':     0.10,
        'weekly_trend': 0.10,
        'rsi':          0.20,
        'macd':         0.15,
        'ma_trend':     0.20,
        'sentiment':    0.15,
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

            weekday_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
            weekday_stats = {}

            for day in range(5):
                day_data = hist[hist['weekday'] == day]['daily_return']
                if len(day_data) > 0:
                    weekday_stats[day] = {
                        'name': weekday_names[day],
                        'avg_return': round(float(day_data.mean() * 100), 4),
                        'pct_positive': round(float((day_data > 0).mean() * 100), 1),
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

            month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                           'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

            monthly_stats = {}
            for m in range(1, 13):
                m_data = monthly_returns_df[monthly_returns_df['month'] == m]['return']
                if len(m_data) > 0:
                    monthly_stats[m] = {
                        'name': month_names[m - 1],
                        'avg_return': round(float(m_data.mean() * 100), 2),
                        'pct_positive': round(float((m_data > 0).mean() * 100), 1),
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

    def analyze_sentiment(self):
        try:
            articles = self.stock.get_news(limit=15)
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
                score = sentiment_map.get(sentiment, 0.0)
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

        signals = {
            'weekday': weekday.get('signal', 0.0),
            'seasonal': seasonal.get('signal', 0.0),
            'weekly_trend': 0.0,
            'rsi': technical.get('rsi', {}).get('signal', 0.0),
            'macd': technical.get('macd', {}).get('signal', 0.0),
            'ma_trend': technical.get('ma_trend', {}).get('signal', 0.0),
            'sentiment': sentiment.get('signal', 0.0),
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
        elif combined_score < 0:
            agreeing = sum(1 for s in signals.values() if s < 0)
        else:
            agreeing = sum(1 for s in signals.values() if abs(s) < 0.1)

        total_signals = len(signals)
        agreement_ratio = agreeing / total_signals
        raw_confidence = abs(combined_score) * agreement_ratio
        confidence = round(min(95.0, raw_confidence * 100 + 15), 1)

        signal_breakdown = {
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
            }
        }

        summary = self._generate_summary(
            recommendation, confidence, combined_score, signals, technical, seasonal, weekday
        )

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
            'weekday': 'day-of-week patterns',
            'seasonal': 'seasonal trends',
            'weekly_trend': 'weekly momentum',
            'rsi': 'RSI',
            'macd': 'MACD',
            'ma_trend': 'moving average trends',
            'sentiment': 'news sentiment'
        }
        strongest_name = name_map.get(strongest_key, strongest_key)

        rsi_val = technical.get('rsi', {}).get('value', 50)
        ma_position = technical.get('ma_trend', {}).get('position', 'Unknown')

        return (
            f"Based on analysis of 7 signals, the overall outlook is {direction} "
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
