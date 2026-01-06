import pandas as pd

def stats_summary_table(db, symbol: str) -> pd.DataFrame:
    """
    High-level summary: counts and win rates by setup/regime prefix.
    """
    return db.stats_summary(symbol=symbol)
