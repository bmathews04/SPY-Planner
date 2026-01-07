import sys
from pathlib import Path

# Ensure src/ is importable when running in Streamlit Cloud
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import os
from dotenv import load_dotenv
import pandas as pd
import streamlit as st

from spyplanner.data.service import MarketDataService
from spyplanner.engine.plan import build_plan
from spyplanner.charts.plotly_chart import plot_plan_chart
from spyplanner.storage.db import DB
from spyplanner.features.indicators import add_indicators
from spyplanner.engine.recommend import recommend_trade_params

load_dotenv()

st.set_page_config(page_title="Planner (Daily)", layout="wide")

# ─────────────────────────────
# Header
# ─────────────────────────────
st.title("Daily Plan Generator (Plan-Only)")
st.caption(
    "Generates a daily trading plan (entry, stop, targets) using volatility-aware logic. "
    "This tool does **not** place trades."
)

# ─────────────────────────────
# Sidebar – Inputs
# ─────────────────────────────
with st.sidebar:
    st.header("Inputs")
    symbol = st.text_input("Ticker Symbol", value="SPY").strip().upper()
    data_source = st.selectbox("Data Source", ["yfinance", "alpaca"])
    st.subheader("Data & Cache")
    force_refresh = st.checkbox("Force Refresh Market Data", value=False)

# ─────────────────────────────
# Services
# ─────────────────────────────
cache_dir = os.getenv("CACHE_DIR", ".cache")
ttl = int(os.getenv("CACHE_TTL_SECONDS", "3600"))
db_path = os.getenv("DB_PATH", ".data/spyplanner.sqlite")

md = MarketDataService(cache_dir=cache_dir, ttl_seconds=ttl)
db = DB(db_path)
db.ensure_schema()

# ─────────────────────────────
# Load Data
# ─────────────────────────────
with st.spinner("Loading Market Data…"):
    df = md.get_daily_bars(symbol=symbol, source=data_source, force_refresh=force_refresh)

if df is None or df.empty or len(df) < 300:
    st.error("Not enough market data returned.")
    st.stop()

df_feat = add_indicators(df).dropna()
rec = recommend_trade_params(df_feat)

# ─────────────────────────────
# Sidebar – Dynamic Plan Settings
# ─────────────────────────────
with st.sidebar:
    st.subheader("Plan Settings (Daily)")
    st.caption(
        f"Recommended for **{symbol}** · "
        f"Stop {rec.stop_atr:.1f} ATR · Target {rec.target1_atr:.1f} ATR"
    )

    lookahead = st.selectbox(
        "Probability Lookahead (Days)",
        [10, 20, 40],
        index=[10, 20, 40].index(rec.lookahead_days)
        if rec.lookahead_days in [10, 20, 40] else 1
    )

    stop_atr = st.slider("Stop Distance (ATR)", 0.7, 3.5, float(rec.stop_atr), 0.1)
    target_atr = st.slider("Target 1 Distance (ATR)", 0.8, 6.0, float(rec.target1_atr), 0.1)
    target2_mult = st.slider("Target 2 Multiplier", 1.2, 2.5, float(rec.target2_mult), 0.1)

    max_risk_dollars = st.number_input(
        "Max Risk ($ per trade)",
        min_value=0.0,
        value=0.0,
        step=25.0
    )

# ─────────────────────────────
# Build Plan
# ─────────────────────────────
with st.spinner("Building Plan…"):
    plan = build_plan(
        symbol=symbol,
        df=df,
        lookahead_bars=int(lookahead),
        stop_atr=float(stop_atr),
        target1_atr=float(target_atr),
        target2_mult=float(target2_mult),
        max_risk_dollars=float(max_risk_dollars),
        db=db
    )

# ─────────────────────────────
# Layout
# ─────────────────────────────
col1, col2 = st.columns([2.2, 1])

with col1:
    st.subheader("Chart")
    st.plotly_chart(plot_plan_chart(df.tail(450), plan), use_container_width=True)

with col2:
    st.subheader("Today’s Plan")
    st.write(f"**As Of:** {plan.as_of_date}")
    st.write(f"**Regime:** {plan.regime}")
    st.write(f"**Setup:** {plan.setup_name}")

    st.markdown("### Key Levels")
    st.write(f"- Last Close: {plan.last_close:.2f}")
    st.write(f"- ATR(14): {plan.atr14:.2f}")

    st.markdown("### Entry / Stop / Targets")
    st.write(f"- Entry: {plan.entry_price:.2f}")
    st.write(f"- Stop: {plan.stop_price:.2f}")
    st.write(f"- Target 1: {plan.target1_price:.2f} ({plan.r_to_t1:.2f}R)")
    st.write(f"- Target 2: {plan.target2_price:.2f} ({plan.r_to_t2:.2f}R)")

# ─────────────────────────────
# Tabs
# ─────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(
    ["Quick Backtest", "Stats", "Logs", "Scanner"]
)

# ─────────────────────────────
# Scanner Tab
# ─────────────────────────────
with tab4:
    st.subheader("Scanner")
    st.caption("Ranks tickers using normalized volatility-aware metrics.")

    PRESETS = {
        "Core + ETFs": ["SPY","QQQ","IWM","DIA","XLK","XLF","XLE","XLV","SMH","XBI"],
        "Leveraged ETFs": ["SSO","UPRO","SPXL","SDS","SPXU","SPXS","TQQQ","SQQQ"]
    }

    leveraged_set = set(PRESETS["Leveraged ETFs"])

    preset = st.selectbox("Universe", list(PRESETS.keys()))
    universe = PRESETS[preset]

    def adaptive_defaults(p):
        return (
            dict(min_r=1.8, max_risk=1.5, max_entry=0.6)
            if "Leveraged" in p
            else dict(min_r=1.5, max_risk=1.8, max_entry=1.0)
        )

    defaults = adaptive_defaults(preset)

    min_r = st.slider("Min R to T1", 0.5, 4.0, defaults["min_r"], 0.1)
    max_risk = st.slider("Max Risk (ATR)", 0.5, 3.0, defaults["max_risk"], 0.1)
    max_entry = st.slider("Max Entry Away (%)", 0.0, 5.0, defaults["max_entry"], 0.1)

    run_scan = st.button("Scan")

    if run_scan:
        results = []
        MIN_RISK_ATR = 0.5

        for sym in universe:
            try:
                dfi = md.get_daily_bars(sym, data_source)
                if dfi is None or len(dfi) < 300:
                    continue

                feat = add_indicators(dfi).dropna()
                rec_i = recommend_trade_params(feat)

                pl = build_plan(
                    sym,
                    dfi,
                    rec_i.lookahead_days,
                    rec_i.stop_atr,
                    rec_i.target1_atr,
                    rec_i.target2_mult,
                    0.0,
                    db=None
                )

                risk_atr = pl.risk_per_share / pl.atr14 if pl.atr14 else None
                entry_pct = abs(pl.entry_price - pl.last_close) / pl.last_close * 100

                if risk_atr is None or risk_atr < MIN_RISK_ATR:
                    continue
                if pl.r_to_t1 < min_r or risk_atr > max_risk or entry_pct > max_entry:
                    continue

                score = (
                    (1.25 if sym in leveraged_set else 1.4) * pl.r_to_t1
                    - (1.2 if sym in leveraged_set else 0.9) * risk_atr
                    - (0.7 if sym in leveraged_set else 0.6) * entry_pct
                )

                results.append({
                    "Ticker": sym,
                    "R to T1": pl.r_to_t1,
                    "Risk (ATR)": risk_atr,
                    "Entry Away %": entry_pct,
                    "Score": score
                })

            except Exception:
                continue

        if results:
            df_scan = pd.DataFrame(results).sort_values("Score", ascending=False)
            df_scan.insert(0, "Rank", range(1, len(df_scan) + 1))
            st.dataframe(df_scan, use_container_width=True)
        else:
            st.warning("No candidates passed filters.")
