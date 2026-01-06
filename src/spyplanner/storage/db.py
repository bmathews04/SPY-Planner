from __future__ import annotations
import os
import sqlite3
from typing import Optional
import pandas as pd

from spyplanner.stats.labeling import label_target_vs_stop_first

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS plan_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT NOT NULL,
  as_of_date TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS occurrences (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT NOT NULL,
  as_of_date TEXT NOT NULL,
  regime TEXT NOT NULL,
  setup_name TEXT NOT NULL,
  entry_price REAL NOT NULL,
  stop_price REAL NOT NULL,
  target1_price REAL NOT NULL,
  lookahead_bars INTEGER NOT NULL,
  stop_atr REAL,
  target1_atr REAL,
  pb_bucket INTEGER,
  vol_bucket INTEGER,
  reg_prefix TEXT,
  label INTEGER,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_occ_symbol_setup ON occurrences(symbol, setup_name);
CREATE INDEX IF NOT EXISTS idx_occ_label ON occurrences(symbol, setup_name, label);
"""

class DB:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def connect(self):
        return sqlite3.connect(self.path)

    def ensure_schema(self):
        with self.connect() as con:
            con.executescript(SCHEMA_SQL)
            con.commit()

    def insert_snapshot(self, plan) -> None:
        import json
        payload = json.dumps(plan.to_dict(), separators=(",", ":"), ensure_ascii=False)
        with self.connect() as con:
            con.execute(
                "INSERT INTO plan_snapshots(symbol, as_of_date, payload_json) VALUES (?, ?, ?)",
                (plan.symbol, plan.as_of_date, payload),
            )
            con.commit()

    def read_recent_snapshots(self, symbol: str, limit: int = 25) -> pd.DataFrame:
        with self.connect() as con:
            rows = con.execute(
                "SELECT as_of_date, created_at, payload_json FROM plan_snapshots WHERE symbol=? ORDER BY id DESC LIMIT ?",
                (symbol, limit),
            ).fetchall()
        return pd.DataFrame(rows, columns=["as_of_date", "created_at", "payload_json"])

    def insert_occurrence(
        self,
        symbol: str,
        as_of_date: str,
        regime: str,
        setup_name: str,
        entry_price: float,
        stop_price: float,
        target1_price: float,
        lookahead_bars: int,
    ) -> None:
        # We fill bucketing fields later from query-time features; keep minimal here.
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO occurrences(symbol, as_of_date, regime, setup_name, entry_price, stop_price, target1_price, lookahead_bars)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (symbol, as_of_date, regime, setup_name, float(entry_price), float(stop_price), float(target1_price), int(lookahead_bars)),
            )
            con.commit()

    def update_labels_for_symbol(self, symbol: str, df_daily: pd.DataFrame) -> int:
        """
        Label unlabeled rows using daily high/low path for target vs stop first.
        """
        updated = 0
        with self.connect() as con:
            rows = con.execute(
                "SELECT id, as_of_date, entry_price, stop_price, target1_price, lookahead_bars FROM occurrences WHERE symbol=? AND label IS NULL",
                (symbol,),
            ).fetchall()

            for _id, as_of_date, entry, stop, target1, lookahead in rows:
                label = label_target_vs_stop_first(
                    df=df_daily,
                    as_of_date=as_of_date,
                    entry=float(entry),
                    stop=float(stop),
                    target=float(target1),
                    lookahead_bars=int(lookahead),
                )
                if label is None:
                    continue
                con.execute("UPDATE occurrences SET label=? WHERE id=?", (int(label), int(_id)))
                updated += 1

            con.commit()
        return updated

    def read_labeled_occurrences(
        self,
        symbol: str,
        setup_name: str,
        lookahead_bars: int,
        reg_prefix: str,
        pb_bucket: Optional[int],
        vol_bucket: Optional[int],
        stop_atr: float,
        target1_atr: float,
        limit: int = 2000,
    ) -> pd.DataFrame:
        """
        We approximate analog bucketing in-SQL by using stored reg_prefix/pb_bucket/vol_bucket if populated.
        For now, we store those fields lazily at query time by "patching" rows based on current plan features.
        If not present, this function falls back to regime prefix match only.
        """
        # For MVP: use label only + setup + symbol + lookahead.
        # (You can later populate pb_bucket/vol_bucket/reg_prefix/stop_atr/target1_atr columns for stronger filtering.)
        q = """
        SELECT label
        FROM occurrences
        WHERE symbol=? AND setup_name=? AND lookahead_bars=? AND label IS NOT NULL
        ORDER BY id DESC
        LIMIT ?
        """
        with self.connect() as con:
            rows = con.execute(q, (symbol, setup_name, int(lookahead_bars), int(limit))).fetchall()
        return pd.DataFrame(rows, columns=["label"])

    def stats_summary(self, symbol: str) -> pd.DataFrame:
        q = """
        SELECT setup_name,
               COUNT(*) AS n,
               SUM(CASE WHEN label=1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN label=0 THEN 1 ELSE 0 END) AS losses,
               ROUND(AVG(CASE WHEN label IS NULL THEN NULL ELSE label END), 4) AS win_rate
        FROM occurrences
        WHERE symbol=?
        GROUP BY setup_name
        ORDER BY n DESC
        """
        with self.connect() as con:
            rows = con.execute(q, (symbol,)).fetchall()
        return pd.DataFrame(rows, columns=["setup_name", "n", "wins", "losses", "win_rate"])
