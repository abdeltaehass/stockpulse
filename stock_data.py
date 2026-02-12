import yfinance as yf
import pandas as pd
import time
from datetime import datetime

_info_cache = {}
_cache_ttl = 120

class StockData:
    def __init__(self, ticker):
        self.ticker = ticker.upper()
        self.stock = yf.Ticker(self.ticker)

    def _get_info_cached(self):
        now = time.time()
        if self.ticker in _info_cache:
            cached_time, cached_data = _info_cache[self.ticker]
            if now - cached_time < _cache_ttl:
                return cached_data
        data = self.stock.info
        _info_cache[self.ticker] = (now, data)
        return data
    
    def get_current_price(self):
        try:
            data = self.stock.history(period='1d')
            if not data.empty:
                current_price = data['Close'].iloc[-1]
                return round(current_price, 2)
            return None
        except Exception as e:
            print(f"Error fetching price for {self.ticker}: {e}")
            return None
    
    def get_stock_info(self):
        try:
            info = self._get_info_cached()
            current_price = self.get_current_price()
            
            stock_data = {
                'ticker': self.ticker,
                'name': info.get('longName', 'N/A'),
                'current_price': current_price,
                'previous_close': info.get('previousClose', 'N/A'),
                'open': info.get('open', 'N/A'),
                'day_high': info.get('dayHigh', 'N/A'),
                'day_low': info.get('dayLow', 'N/A'),
                'volume': info.get('volume', 'N/A'),
                'week52_high': info.get('fiftyTwoWeekHigh', None),
                'week52_low': info.get('fiftyTwoWeekLow', None),
            }
            
            if current_price and stock_data['previous_close'] != 'N/A':
                change = current_price - stock_data['previous_close']
                change_percent = (change / stock_data['previous_close']) * 100
                stock_data['change'] = round(change, 2)
                stock_data['change_percent'] = round(change_percent, 2)
            
            return stock_data
        except Exception as e:
            print(f"Error fetching info for {self.ticker}: {e}")
            return None
    
    def get_crypto_info(self):
        """Get crypto-specific info including market cap, volume, and supply"""
        try:
            info = self._get_info_cached()
            current_price = self.get_current_price()

            crypto_data = {
                'ticker': self.ticker,
                'name': info.get('name', info.get('longName', 'N/A')),
                'symbol': self.ticker.replace('-USD', ''),
                'current_price': current_price,
                'previous_close': info.get('previousClose', None),
                'open': info.get('open', None),
                'day_high': info.get('dayHigh', None),
                'day_low': info.get('dayLow', None),
                'volume': info.get('volume24Hr', info.get('volume', None)),
                'market_cap': info.get('marketCap', None),
                'circulating_supply': info.get('circulatingSupply', None),
                'total_supply': info.get('totalSupply', None),
                'volume_24h': info.get('volume24Hr', info.get('volume', None)),
            }

            if current_price and crypto_data['previous_close']:
                change = current_price - crypto_data['previous_close']
                change_percent = (change / crypto_data['previous_close']) * 100
                crypto_data['change'] = round(change, 2)
                crypto_data['change_percent'] = round(change_percent, 2)
            else:
                crypto_data['change'] = 0
                crypto_data['change_percent'] = 0

            return crypto_data
        except Exception as e:
            print(f"Error fetching crypto info for {self.ticker}: {e}")
            return None

    def get_historical_data(self, period='1mo', interval=None):
        try:
            if period == '1d':
                if interval is None:
                    interval = '15m'
                interval_map = {
                    '5m': '5m',
                    '15m': '15m',
                    '30m': '30m',
                    '1h': '60m',
                    '3h': '60m'
                }
                yf_interval = interval_map.get(interval, '15m')
                data = self.stock.history(period='1d', interval=yf_interval)
                if interval == '3h' and not data.empty:
                    data = data.resample('3h').agg({
                        'Open': 'first',
                        'High': 'max',
                        'Low': 'min',
                        'Close': 'last',
                        'Volume': 'sum'
                    }).dropna()
                return data
            else:
                data = self.stock.history(period=period)
                return data
        except Exception as e:
            print(f"Error fetching historical data for {self.ticker}: {e}")
            return None
    def get_weekly_change(self):
        try:
            data = self.stock.history(period='1wk')
            if len(data) >= 2:
                week_start = data['Close'].iloc[0]
                current = data['Close'].iloc[-1]
                weekly_change = ((current - week_start) / week_start) * 100
                return round(weekly_change, 2)
            return 0
        except Exception as e:
            print(f"Error fetching weekly data for {self.ticker}: {e}")
            return 0

    def get_news(self, limit=10):
        try:
            news = self.stock.news
            if not news:
                return []

            articles = []
            for item in news[:limit]:
                content = item.get('content', item)

                title = content.get('title', '')
                if not title:
                    continue

                publisher = 'Unknown'
                if content.get('provider'):
                    publisher = content['provider'].get('displayName', 'Unknown')

                link = ''
                if content.get('clickThroughUrl'):
                    link = content['clickThroughUrl'].get('url', '')
                elif content.get('canonicalUrl'):
                    link = content['canonicalUrl'].get('url', '')

                published = 0
                pub_date = content.get('pubDate', '')
                if pub_date:
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                        published = int(dt.timestamp())
                    except:
                        pass

                thumbnail = ''
                if content.get('thumbnail'):
                    resolutions = content['thumbnail'].get('resolutions', [])
                    if resolutions:
                        thumbnail = resolutions[0].get('url', '')
                    elif content['thumbnail'].get('originalUrl'):
                        thumbnail = content['thumbnail']['originalUrl']

                article = {
                    'title': title,
                    'publisher': publisher,
                    'link': link,
                    'published': published,
                    'type': content.get('contentType', 'STORY'),
                    'thumbnail': thumbnail,
                    'related_tickers': []
                }

                sentiment_result = self._analyze_sentiment(article['title'])
                article['sentiment'] = sentiment_result['label']
                article['sentiment_score'] = sentiment_result['score']
                articles.append(article)

            return articles
        except Exception as e:
            print(f"Error fetching news for {self.ticker}: {e}")
            return []

    def get_analyst_targets(self):
        try:
            info = self._get_info_cached()
            current = self.get_current_price()

            target_low = info.get('targetLowPrice')
            target_high = info.get('targetHighPrice')
            target_mean = info.get('targetMeanPrice')
            target_median = info.get('targetMedianPrice')
            num_analysts = info.get('numberOfAnalystOpinions', 0)

            if not target_mean or not current or num_analysts == 0:
                return None

            return {
                'current_price': current,
                'target_low': target_low,
                'target_high': target_high,
                'target_mean': target_mean,
                'target_median': target_median,
                'num_analysts': num_analysts
            }
        except Exception as e:
            print(f"Error fetching analyst targets for {self.ticker}: {e}")
            return None

    def _analyze_sentiment(self, text):
        text_lower = text.lower()

        positive_words = [
            'surge', 'jump', 'gain', 'rise', 'soar', 'rally', 'bull', 'boom',
            'growth', 'profit', 'beat', 'exceed', 'upgrade', 'buy', 'strong',
            'record', 'high', 'success', 'win', 'breakthrough', 'innovation',
            'positive', 'optimistic', 'confidence', 'recovery', 'outperform',
            'momentum', 'upside', 'bullish', 'dividend', 'breakout', 'expand',
            'accelerate', 'approval', 'acquisition', 'synergy', 'rebound',
            'upbeat', 'robust', 'exceeded', 'milestone', 'favorable',
            'catalyst', 'turnaround', 'top', 'leading', 'surpass'
        ]

        negative_words = [
            'fall', 'drop', 'plunge', 'crash', 'decline', 'loss', 'bear',
            'miss', 'fail', 'downgrade', 'sell', 'weak', 'low', 'concern',
            'fear', 'risk', 'warning', 'cut', 'layoff', 'lawsuit', 'fraud',
            'investigation', 'negative', 'pessimistic', 'recession', 'crisis',
            'bearish', 'downside', 'default', 'bankruptcy', 'slump', 'plummet',
            'downtrend', 'overvalued', 'headwind', 'deteriorate', 'underperform',
            'volatility', 'uncertainty', 'stagnant', 'dilution', 'deficit',
            'impairment', 'shortfall', 'suspension', 'penalty', 'recall'
        ]

        positive_phrases = [
            'beat expectations', 'exceeded estimates', 'raised guidance',
            'strong earnings', 'record revenue', 'all-time high',
            'buy rating', 'price target raised', 'dividend increase',
            'share buyback', 'strong demand', 'revenue growth',
            'above consensus', 'market outperform', 'positive outlook',
            'revenue beat', 'strong guidance', 'margin expansion'
        ]

        negative_phrases = [
            'missed earnings', 'missed expectations', 'lowered guidance',
            'price target cut', 'revenue miss', 'profit warning',
            'going concern', 'debt default', 'sec investigation',
            'class action', 'supply chain disruption', 'margin pressure',
            'below expectations', 'revenue decline', 'margin compression',
            'earnings miss', 'guidance cut', 'market underperform'
        ]

        negation_words = {'not', 'no', 'never', 'neither', 'hardly', 'barely',
                          "don't", "doesn't", "didn't", "won't", "can't",
                          "isn't", "wasn't", "wouldn't", 'nor'}

        positive_count = 0
        negative_count = 0

        for phrase in positive_phrases:
            if phrase in text_lower:
                positive_count += 3

        for phrase in negative_phrases:
            if phrase in text_lower:
                negative_count += 3

        words = text_lower.split()
        for i, word in enumerate(words):
            negated = (i > 0 and words[i - 1] in negation_words)
            if word in positive_words:
                if negated:
                    negative_count += 1
                else:
                    positive_count += 1
            elif word in negative_words:
                if negated:
                    positive_count += 1
                else:
                    negative_count += 1

        total = positive_count + negative_count
        if total == 0:
            score = 0.0
        else:
            score = (positive_count - negative_count) / total

        if score > 0.05:
            label = 'positive'
        elif score < -0.05:
            label = 'negative'
        else:
            label = 'neutral'

        return {'label': label, 'score': round(score, 3)}