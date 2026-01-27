import yfinance as yf
import pandas as pd
from datetime import datetime

class StockData:
    def __init__(self, ticker):
        self.ticker = ticker.upper()
        self.stock = yf.Ticker(self.ticker)
    
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
            info = self.stock.info
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
    
    def get_historical_data(self, period='1mo'):
        try:
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

                article['sentiment'] = self._analyze_sentiment(article['title'])
                articles.append(article)

            return articles
        except Exception as e:
            print(f"Error fetching news for {self.ticker}: {e}")
            return []

    def _analyze_sentiment(self, text):
        text_lower = text.lower()

        positive_words = [
            'surge', 'jump', 'gain', 'rise', 'soar', 'rally', 'bull', 'boom',
            'growth', 'profit', 'beat', 'exceed', 'upgrade', 'buy', 'strong',
            'record', 'high', 'success', 'win', 'breakthrough', 'innovation',
            'positive', 'optimistic', 'confidence', 'recovery', 'outperform'
        ]

        negative_words = [
            'fall', 'drop', 'plunge', 'crash', 'decline', 'loss', 'bear',
            'miss', 'fail', 'downgrade', 'sell', 'weak', 'low', 'concern',
            'fear', 'risk', 'warning', 'cut', 'layoff', 'lawsuit', 'fraud',
            'investigation', 'negative', 'pessimistic', 'recession', 'crisis'
        ]

        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)

        if positive_count > negative_count:
            return 'positive'
        elif negative_count > positive_count:
            return 'negative'
        else:
            return 'neutral'