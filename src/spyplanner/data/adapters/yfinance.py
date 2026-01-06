import pandas as pd
import yfinance as yf

from spyplanner.data.normalize import normalize_ohlcv

def fetch_daily(symbol: str, years: int = 15) -> pd.DataFrame:
    period = f"{years}y"
    df = yf.download(symbol, period=period, interval="1d", auto_adjust=False, progress=False)
    df = normalize_ohlcv(df)
    return df
