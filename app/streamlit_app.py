import sys
from pathlib import Path

# Ensure src/ is importable when running in Streamlit Cloud
ROOT = Path(__file__).resolve().parents[1]   # repo root
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import os
from dotenv import load_dotenv

import streamlit as st

from spyplanner.data.service import MarketDataService
from spyplanner.engine.plan import build_plan
from spyplanner.charts.plotly_chart import plot_plan_chart
from spyplanner.storage.db import DB

# NEW: dynamic defaults
from spyplanner.features.indicators import add_indicators
from spyplanner.engine.recommend import recommend_trade_params


load_dotenv()

st.set_page_config(page_title="Planner (Daily)", layout="wide")

# --- Header ---
st.title("Daily Plan Generator (Plan-Only)")
st.caption(
    "This app generates a daily trading plan (entry, stop, targets) based on trend, volatility, and key support/resistance zones. "
    "It does not place trades."
)

# ---- Sidebar (Phase 1: Ticker & Data Source) ----
with st.sidebar:
    st.header("Inputs")

    symbol = st.text_input("Ticker Symbol", value="SPY").strip().upper()
    data_source = st.selectbox("Data Source", ["yfinance", "alpaca"], index=0)

    st.subheader("Data & Cache")
    force_refresh = st.checkbox("Force Refresh Market Data", value=False)

# ---- Services ----
cache_dir = os.getenv("CACHE_DIR", ".cache")
ttl = int(os.getenv("CACHE_TTL_SECONDS", "3600"))
db_path = os.getenv("DB_PATH", ".data/spyplanner.sqlite")

md = MarketDataService(cache_dir=cache_dir, ttl_seconds=ttl)
db = DB(db_path)
db.ensure_schema()

# ---- Data ----
with st.spinner("Loading Market Data..."):
    df = md.get_daily_bars(symbol=symbol, source=data_source, force_refresh=force_refresh)

if df is None or df.empty or len(df) < 300:
    st.error("Not enough market data returned. Try Yahoo Finance, verify the ticker, or disable Force Refresh.")
    st.stop()

# ---- Dynamic Recommendations (Stop/Targets/Lookahead) ----
# Add indicators so ATR exists for recommendation logic
df_feat = add_indicators(df, ema_fast=20, ema_mid=50, ema_slow=200, atr_n=14).dropna()
rec = recommend_trade_params(df_feat)

# ---- Sidebar (Phase 2: Plan Settings — Dynamic Defaults) ----
with st.sidebar:
    st.subheader("Plan Settings (Daily)")
    st.caption(
        f"Recommended for **{symbol}** · "
        f"Stop **{rec.stop_atr:.1f} ATR**, "
        f"Target **{rec.target1_atr:.1f} ATR**"
    )

    with st.expander("Why These Defaults?"):
        st.write(rec.reason)
        st.write(
            "Defaults are based on the ticker’s historical daily volatility (ATR%) and gap behavior. "
            "Higher volatility typically requires wider stops and larger targets."
        )

    lookahead = st.selectbox(
        "Probability Lookahead (Trading Days)",
        [10, 20, 40],
        index=[10, 20, 40].index(rec.lookahead_days) if rec.lookahead_days in [10, 20, 40] else 1,
        key=f"lookahead_{symbol}",
    )

    stop_atr = st.slider(
        "Stop Distance (ATR)",
        0.7, 3.5,
        float(rec.stop_atr), 0.1,
        key=f"stop_atr_{symbol}",
    )

    target_atr = st.slider(
        "Target 1 Distance (ATR)",
        0.8, 6.0,
        float(rec.target1_atr), 0.1,
        key=f"target1_atr_{symbol}",
    )

    target2_mult = st.slider(
        "Target 2 Multiplier (x Target 1)",
        1.2, 2.5,
        float(rec.target2_mult), 0.1,
        key=f"target2_mult_{symbol}",
    )

    st.subheader("Optional Position Sizing")
    max_risk_dollars = st.number_input(
        "Max Risk ($) per Trade",
        min_value=0.0,
        value=0.0,
        step=25.0,
        key=f"max_risk_{symbol}",
    )
    st.caption("If set above $0, the app will estimate share size from entry-to-stop risk.")

# Label any unlabeled occurrences so probabilities get smarter over time
# (safe to call every run; it only updates rows where label IS NULL)
_ = db.update_labels_for_symbol(symbol=symbol, df_daily=df)

# ---- Plan ----
with st.spinner("Building Your Plan..."):
    plan = build_plan(
        symbol=symbol,
        df=df,
        lookahead_bars=int(lookahead),
        stop_atr=float(stop_atr),
        target1_atr=float(target_atr),
        target2_mult=float(target2_mult),
        max_risk_dollars=float(max_risk_dollars),
        db=db,  # logs snapshots + occurrences
    )

# ---- UI ----
col1, col2 = st.columns([2.2, 1])

with col1:
    st.subheader("Chart")
    fig = plot_plan_chart(df=df.tail(450), plan=plan)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Today’s Plan")
    st.write(f"**As Of:** {plan.as_of_date}")
    st.write(f"**Market Regime:** {plan.regime}")
    st.write(f"**Plan Type:** {plan.setup_name}")

    st.markdown("### Key Levels")
    st.write(f"- **Last Close:** {plan.last_close:.2f}")
    st.write(f"- **ATR (14):** {plan.atr14:.2f}")
    st.write(f"- **Support Zone (Floor):** `{plan.floor_zone}`" if plan.floor_zone else "- **Support Zone (Floor):** n/a")
    st.write(f"- **Resistance Zone (Ceiling):** `{plan.ceiling_zone}`" if plan.ceiling_zone else "- **Resistance Zone (Ceiling):** n/a")

    st.markdown("### Entry, Stop, and Targets")
    st.write(f"- **Entry ({plan.entry_type.title()}):** {plan.entry_price:.2f}")
    st.write(f"- **Stop Loss:** {plan.stop_price:.2f}  *(Risk: {plan.risk_per_share:.2f} per share)*")
    st.write(f"- **Target 1:** {plan.target1_price:.2f}  *(R: {plan.r_to_t1:.2f})*")
    st.write(f"- **Target 2:** {plan.target2_price:.2f}  *(R: {plan.r_to_t2:.2f})*")

    if plan.suggested_shares and plan.suggested_shares > 0:
        st.markdown("### Position Size (Optional)")
        st.write(f"- **Suggested Shares:** {plan.suggested_shares}")
        st.write(f"- **Estimated $ Risk:** {plan.suggested_shares * plan.risk_per_share:.2f}")

    st.subheader("Historical Probability")
    if plan.p_target1_before_stop is None:
        st.info(
            "Not enough labeled history for this exact setup yet. "
            "This will populate automatically as the app logs and labels more occurrences."
        )
    else:
        st.write(f"- **P(Target 1 Before Stop)** *(≤ {plan.lookahead_bars} days)*: **{plan.p_target1_before_stop:.0%}**")
        st.write(f"- **Sample Size:** {plan.prob_sample}")
        st.write(f"- **Expected Value (R):** {plan.ev_r:.2f}R")

    if plan.notes:
        st.subheader("Notes & Guidance")
        for n in plan.notes:
            st.warning(n)

    with st.expander("Raw Plan JSON (Advanced)"):
        st.json(plan.to_dict())

st.divider()

tab1, tab2, tab3 = st.tabs(["Quick Backtest", "Stats Summary", "Recent Logs"])

with tab1:
    st.caption("A simplified historical check of the current plan type using daily bars (for sanity checking only).")
    from spyplanner.backtest.runner import quick_backtest

    res = quick_backtest(
        df=df,
        setup_name=plan.setup_name,
        stop_atr=stop_atr,
        target1_atr=target_atr,
        target2_mult=target2_mult,
    )
    st.write(res["summary"])
    st.dataframe(res["trades"].tail(25), use_container_width=True)

with tab2:
    from spyplanner.stats.reports import stats_summary_table

    tbl = stats_summary_table(db=db, symbol=symbol)
    st.dataframe(tbl, use_container_width=True)

with tab3:
    st.caption("Recent plan snapshots saved locally (SQLite).")
    snaps = db.read_recent_snapshots(symbol=symbol, limit=25)
    st.dataframe(snaps, use_container_width=True)
