import os
from dotenv import load_dotenv

import streamlit as st

from spyplanner.config.defaults import default_params
from spyplanner.data.service import MarketDataService
from spyplanner.engine.plan import build_plan
from spyplanner.charts.plotly_chart import plot_plan_chart
from spyplanner.storage.db import DB


load_dotenv()

st.set_page_config(page_title="SPY Planner (Daily)", layout="wide")

st.title("SPY Planner — Daily Plan Generator (plan-only)")

# ---- Sidebar ----
with st.sidebar:
    symbol = st.text_input("Ticker", value="SPY").strip().upper()
    data_source = st.selectbox("Data source", ["yfinance", "alpaca"], index=0)

    st.markdown("### Plan settings (daily)")
    p = default_params()
    lookahead = st.selectbox("Probability horizon (bars)", [10, 20, 40], index=1)
    stop_atr = st.slider("Stop distance (ATR)", 0.7, 3.5, float(p.stop_atr), 0.1)
    target_atr = st.slider("Target 1 distance (ATR)", 0.8, 6.0, float(p.target1_atr), 0.1)
    target2_mult = st.slider("Target 2 multiplier (x Target 1)", 1.2, 2.5, float(p.target2_mult), 0.1)
    max_risk_dollars = st.number_input("Max $ risk (optional sizing)", min_value=0.0, value=0.0, step=25.0)

    st.markdown("### Cache")
    force_refresh = st.checkbox("Force refresh data", value=False)

# ---- Services ----
cache_dir = os.getenv("CACHE_DIR", ".cache")
ttl = int(os.getenv("CACHE_TTL_SECONDS", "3600"))
db_path = os.getenv("DB_PATH", ".data/spyplanner.sqlite")

md = MarketDataService(cache_dir=cache_dir, ttl_seconds=ttl)
db = DB(db_path)
db.ensure_schema()

# ---- Data ----
with st.spinner("Loading market data..."):
    df = md.get_daily_bars(symbol=symbol, source=data_source, force_refresh=force_refresh)

# Label any unlabeled occurrences so probabilities get smarter over time
# (safe to call every run; it only updates rows where label IS NULL)
_ = db.update_labels_for_symbol(symbol=symbol, df_daily=df)

if df is None or df.empty or len(df) < 300:
    st.error("Not enough data returned. Try yfinance, or check symbol.")
    st.stop()

# ---- Plan ----
with st.spinner("Computing plan..."):
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
    fig = plot_plan_chart(df=df.tail(450), plan=plan)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Plan")
    st.write(f"**As of:** {plan.as_of_date}")
    st.write(f"**Regime:** {plan.regime}")
    st.write(f"**Setup:** {plan.setup_name}")

    st.markdown("**Levels**")
    st.write(f"- Last close: **{plan.last_close:.2f}**")
    st.write(f"- ATR(14): **{plan.atr14:.2f}**")
    st.write(f"- Floor zone: `{plan.floor_zone}`" if plan.floor_zone else "- Floor zone: n/a")
    st.write(f"- Ceiling zone: `{plan.ceiling_zone}`" if plan.ceiling_zone else "- Ceiling zone: n/a")

    st.markdown("**Entry / Risk**")
    st.write(f"- Entry ({plan.entry_type}): **{plan.entry_price:.2f}**")
    st.write(f"- Stop: **{plan.stop_price:.2f}**  (risk: {plan.risk_per_share:.2f}/sh)")
    st.write(f"- Target 1: **{plan.target1_price:.2f}**  (R: {plan.r_to_t1:.2f})")
    st.write(f"- Target 2: **{plan.target2_price:.2f}**  (R: {plan.r_to_t2:.2f})")

    if plan.suggested_shares and plan.suggested_shares > 0:
        st.markdown("**Sizing (optional)**")
        st.write(f"- Suggested shares: **{plan.suggested_shares}**")
        st.write(f"- Approx $ risk: **{plan.suggested_shares * plan.risk_per_share:.2f}**")

    st.subheader("Probability (historical)")
    if plan.p_target1_before_stop is None:
        st.info("Not enough labeled samples yet for this state. Leave the app running; it logs occurrences.")
    else:
        st.write(f"- P(T1 before Stop, ≤ {plan.lookahead_bars} bars): **{plan.p_target1_before_stop:.0%}**")
        st.write(f"- Sample size: **{plan.prob_sample}**")
        st.write(f"- Expected value (R): **{plan.ev_r:.2f}R**")

    if plan.notes:
        st.subheader("Notes")
        for n in plan.notes:
            st.warning(n)

    st.subheader("Raw plan JSON")
    st.json(plan.to_dict())

st.divider()

tab1, tab2, tab3 = st.tabs(["Backtest (quick)", "Stats", "Logs"])

with tab1:
    st.caption("Quick backtest of the currently selected setup logic over full history (daily, simplified fills).")
    from spyplanner.backtest.runner import quick_backtest

    res = quick_backtest(df=df, setup_name=plan.setup_name, stop_atr=stop_atr, target1_atr=target_atr, target2_mult=target2_mult)
    st.write(res["summary"])
    st.dataframe(res["trades"].tail(25), use_container_width=True)

with tab2:
    from spyplanner.stats.reports import stats_summary_table
    tbl = stats_summary_table(db=db, symbol=symbol)
    st.dataframe(tbl, use_container_width=True)

with tab3:
    st.caption("Recent plan snapshots (sqlite).")
    snaps = db.read_recent_snapshots(symbol=symbol, limit=25)
    st.dataframe(snaps, use_container_width=True)
