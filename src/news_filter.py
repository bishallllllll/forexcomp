"""
News Filter for Forex Trading
- Block trades during high-impact news events
- Configurable blackout windows
"""

import requests
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import json

logger = logging.getLogger(__name__)

class NewsFilter:
    """Filter trades during high-impact economic news."""
    
    # High-impact indicators (for major currencies)
    HIGH_IMPACT_INDICATORS = {
        "USD": ["NFP", "FOMC", "Fed Rate", "PCE", "CPI", "Initial Jobless", "Retail Sales"],
        "EUR": ["ECB Rate", "GDP", "Inflation", "ZEW Sentiment"],
        "GBP": ["BOE Rate", "GDP", "Inflation"],
        "JPY": ["BOJ Rate", "Inflation", "GDP"],
        "AUD": ["RBA Rate", "Employment", "GDP"],
        "CAD": ["BOC Rate", "Employment", "CPI"],
        "CHF": ["SNB Rate", "KOF Barometer"],
        "NZD": ["RBNZ Rate", "Employment"],
    }
    
    def __init__(self, blackout_before_min=10, blackout_after_min=5):
        self.blackout_before = timedelta(minutes=blackout_before_min)
        self.blackout_after = timedelta(minutes=blackout_after_min)
        self.news_cache = {}
        self.last_fetch = None
        
    def _extract_currencies(self, pair: str) -> tuple:
        """Extract base and quote currencies from pair (e.g., EURUSD -> EUR, USD)."""
        if len(pair) == 6:
            return pair[:3], pair[3:]
        return None, None
    
    def _is_high_impact(self, event_name: str) -> bool:
        """Check if event is high-impact."""
        for currency, indicators in self.HIGH_IMPACT_INDICATORS.items():
            for indicator in indicators:
                if indicator.lower() in event_name.lower():
                    return True
        return False
    
    def _fetch_forex_factory_news(self) -> Optional[List[Dict]]:
        """Fetch high-impact news from Forex Factory API (lightweight)."""
        try:
            # Using a free endpoint that doesn't require auth
            # For production, use an authenticated service like Trading Economics
            
            url = "https://nfs.nzjforex.com/economic_calendar"
            headers = {"User-Agent": "Mozilla/5.0"}
            
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code != 200:
                logger.warning(f"Forex Factory fetch failed: {response.status_code}")
                return None
            
            try:
                data = response.json()
            except ValueError:
                logger.warning("News fetch returned non-JSON payload")
                return None
            
            events = []
            if isinstance(data, dict):
                events = data.get("data") or data.get("events") or []
            elif isinstance(data, list):
                events = data
            
            news_cache: Dict[str, List[Dict]] = {}
            for item in events:
                if not isinstance(item, dict):
                    continue
                
                currency = item.get("currency") or item.get("ccy") or item.get("symbol")
                name = item.get("event") or item.get("name") or item.get("title")
                impact = item.get("impact") or item.get("importance")
                time_val = item.get("time") or item.get("datetime") or item.get("date")
                
                if not currency or not name or not time_val:
                    continue
                
                event_time = None
                if isinstance(time_val, (int, float)):
                    event_time = datetime.utcfromtimestamp(time_val)
                elif isinstance(time_val, str):
                    try:
                        event_time = datetime.fromisoformat(time_val.replace("Z", "+00:00")).replace(tzinfo=None)
                    except ValueError:
                        event_time = None
                
                if event_time is None:
                    continue
                
                news_cache.setdefault(currency, []).append({
                    "name": name,
                    "time": event_time,
                    "impact": impact,
                    "forecast": item.get("forecast"),
                    "previous": item.get("previous"),
                })
            
            self.news_cache = news_cache
            logger.debug("News cache refreshed")
            return events
        except Exception as e:
            logger.warning(f"News fetch error: {e}")
            return None
    
    def is_trade_allowed(self, pair: str, current_time: Optional[datetime] = None) -> bool:
        """
        Check if trading is allowed for a pair (not in blackout window).
        Returns: True if OK to trade, False if in blackout.
        """
        if current_time is None:
            current_time = datetime.utcnow()
        
        base, quote = self._extract_currencies(pair)
        if not base or not quote:
            logger.warning(f"Invalid pair format: {pair}")
            return True  # Fail open
        
        # Refresh news cache every 60 seconds
        if self.last_fetch is None or (current_time - self.last_fetch).total_seconds() > 60:
            self._fetch_forex_factory_news()
            self.last_fetch = current_time
        
        # Check if currencies have pending high-impact news within blackout windows
        for currency in [base, quote]:
            if currency in self.news_cache:
                for news_item in self.news_cache[currency]:
                    event_time = news_item.get("time")
                    if not event_time:
                        continue
                    
                    if self._is_high_impact(news_item.get("name", "")):
                        # Calculate blackout window
                        blackout_start = event_time - self.blackout_before
                        blackout_end = event_time + self.blackout_after
                        
                        if blackout_start <= current_time <= blackout_end:
                            logger.info(
                                f"Trade blocked for {pair}: "
                                f"{news_item['name']} at {event_time}"
                            )
                            return False
        
        return True
    
    def get_upcoming_events(self, pair: str, hours_ahead=24) -> List[Dict]:
        """Get upcoming high-impact events for a pair."""
        base, quote = self._extract_currencies(pair)
        if not base or not quote:
            return []
        
        upcoming = []
        current_time = datetime.utcnow()
        
        for currency in [base, quote]:
            if currency in self.news_cache:
                for event in self.news_cache[currency]:
                    event_time = event.get("time")
                    if event_time and self._is_high_impact(event.get("name", "")):
                        if 0 <= (event_time - current_time).total_seconds() <= (hours_ahead * 3600):
                            upcoming.append({
                                "currency": currency,
                                "event": event["name"],
                                "time": event_time,
                                "forecast": event.get("forecast"),
                                "previous": event.get("previous"),
                            })
        
        return sorted(upcoming, key=lambda x: x["time"])
