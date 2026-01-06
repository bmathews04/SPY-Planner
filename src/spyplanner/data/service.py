import pandas as pd

from spyplanner.data.cache import DiskCache
from spyplanner.data.adapters.yfinance import fetch_daily as yf_fetch_daily
from spyplanner.data.adapters.alpaca import fetch_daily as alp_fetch_daily

class MarketDataService:
    def __init__(self, cache_dir: str, ttl_seconds: int):
        self.cache = DiskCache(cache_dir=cache_dir, ttl_seconds=ttl_seconds)

    def get_daily_bars(self, symbol: str, source: str, force_refresh: bool = False) -> pd.DataFrame:
        key = f"daily:{source}:{symbol}"
        if not force_refresh:
            cached = self.cache.get(key)
            if cached is not None and not cached.empty:
                cached.index = pd.to_datetime(cached.index)
                return cached

        if source == "alpaca":
            df = alp_fetch_daily(symbol)
            if df is None or df.empty:
                # fallback automatically to yfinance
                df = yf_fetch_daily(symbol)
        else:
            df = yf_fetch_daily(symbol)

        if df is None:
            return pd.DataFrame()

        self.cache.set(key, df)
        return df
