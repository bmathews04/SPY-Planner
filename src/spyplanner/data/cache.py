import os
import time
import pandas as pd

class DiskCache:
    def __init__(self, cache_dir: str, ttl_seconds: int):
        self.cache_dir = cache_dir
        self.ttl_seconds = ttl_seconds
        os.makedirs(self.cache_dir, exist_ok=True)

    def _path(self, key: str) -> str:
        safe = key.replace("/", "_").replace(":", "_")
        return os.path.join(self.cache_dir, f"{safe}.parquet")

    def get(self, key: str) -> pd.DataFrame | None:
        path = self._path(key)
        if not os.path.exists(path):
            return None
        mtime = os.path.getmtime(path)
        if (time.time() - mtime) > self.ttl_seconds:
            return None
        try:
            return pd.read_parquet(path)
        except Exception:
            return None

    def set(self, key: str, df: pd.DataFrame) -> None:
        path = self._path(key)
        try:
            df.to_parquet(path, index=True)
        except Exception:
            # fallback
            df.to_csv(path.replace(".parquet", ".csv"), index=True)
