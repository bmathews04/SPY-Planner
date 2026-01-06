import pandas as pd

REQUIRED_COLS = ["Open", "High", "Low", "Close", "Volume"]

def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    # yfinance sometimes returns multiindex columns
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # standardize column names
    df = df.rename(columns=str.title)

    keep = [c for c in REQUIRED_COLS if c in df.columns]
    df = df[keep].copy()

    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    df = df.dropna()

    # Ensure numeric
    for c in keep:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna()
    return df
