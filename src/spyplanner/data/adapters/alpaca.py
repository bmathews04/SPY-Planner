import os
import pandas as pd
from spyplanner.data.normalize import normalize_ohlcv

def fetch_daily(symbol: str, limit: int = 5000) -> pd.DataFrame:
    """
    Optional Alpaca adapter.
    If alpaca-py isn't installed or keys aren't set, returns empty df.
    """
    api_key = os.getenv("ALPACA_API_KEY", "")
    secret = os.getenv("ALPACA_SECRET_KEY", "")
    if not api_key or not secret:
        return pd.DataFrame()

    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame
    except Exception:
        return pd.DataFrame()

    client = StockHistoricalDataClient(api_key, secret)
    req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Day, limit=limit)
    bars = client.get_stock_bars(req).df
    if bars is None or bars.empty:
        return pd.DataFrame()

    if isinstance(bars.index, pd.MultiIndex):
        bars = bars.reset_index().set_index("timestamp")

    bars.index = pd.to_datetime(bars.index)
    bars = bars.rename(columns={
        "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"
    })
    df = normalize_ohlcv(bars)
    return df
