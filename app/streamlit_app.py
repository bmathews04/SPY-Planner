import sys
from pathlib import Path

# Ensure src/ is importable when running in Streamlit Cloud
ROOT = Path(__file__).resolve().parents[1]   # repo root
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

# Dynamic defaults
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

    # Core values
    entry = float(plan.entry_price)
    stop = float(plan.stop_price)
    t1 = float(plan.target1_price)
    t2 = float(plan.target2_price)

    risk_per_share = float(plan.risk_per_share) if plan.risk_per_share is not None else max(entry - stop, 0.0)
    atr14 = float(plan.atr14) if plan.atr14 is not None else None

    reward_t1 = t1 - entry
    reward_t2 = t2 - entry

    r1 = float(plan.r_to_t1) if plan.r_to_t1 is not None else (reward_t1 / risk_per_share if risk_per_share > 0 else None)
    r2 = float(plan.r_to_t2) if plan.r_to_t2 is not None else (reward_t2 / risk_per_share if risk_per_share > 0 else None)

    risk_atr = (risk_per_share / atr14) if (atr14 and atr14 > 0) else None

    # Simple trade quality heuristic (edit thresholds if you want)
    def rr_label(r: float | None) -> str:
        if r is None:
            return "n/a"
        if r >= 2.0:
            return "Strong"
        if r >= 1.5:
            return "Good"
        if r >= 1.2:
            return "Borderline"
        return "Not Great"

    quality_t1 = rr_label(r1)

    # Quick bullets (easy scan)
    st.write(f"- **Entry ({plan.entry_type.title()}):** {entry:.2f}")
    st.write(f"- **Stop Loss:** {stop:.2f}")
    st.write(f"- **Target 1:** {t1:.2f}")
    st.write(f"- **Target 2:** {t2:.2f}")

    with st.expander("Risk/Reward Table (Is This Worth Attempting?)", expanded=True):
        rows = [
            {
                "Level": "Entry",
                "Price": f"{entry:.2f}",
                "Δ vs Entry ($/sh)": "—",
                "Risk/Reward (R)": "—",
                "Notes": "Planned entry price",
            },
            {
                "Level": "Stop Loss",
                "Price": f"{stop:.2f}",
                "Δ vs Entry ($/sh)": f"-{risk_per_share:.2f}",
                "Risk/Reward (R)": "1.00R",
                "Notes": f"Risk = {risk_per_share:.2f}/sh"
                         + (f" ({risk_atr:.2f} ATR)" if risk_atr is not None else ""),
            },
            {
                "Level": "Target 1",
                "Price": f"{t1:.2f}",
                "Δ vs Entry ($/sh)": f"+{reward_t1:.2f}",
                "Risk/Reward (R)": f"{r1:.2f}R" if r1 is not None else "n/a",
                "Notes": f"Quality: {quality_t1}",
            },
            {
                "Level": "Target 2",
                "Price": f"{t2:.2f}",
                "Δ vs Entry ($/sh)": f"+{reward_t2:.2f}",
                "Risk/Reward (R)": f"{r2:.2f}R" if r2 is not None else "n/a",
                "Notes": "Stretch/runner target",
            },
        ]
        tbl = pd.DataFrame(rows)
        st.dataframe(tbl, use_container_width=True, hide_index=True)

        if r1 is not None:
            if r1 < 1.2:
                st.warning("Target 1 offers a low R multiple. Consider skipping or waiting for a better entry (price comes to you).")
            elif r1 < 1.5:
                st.info("Target 1 is borderline. This can work, but discipline matters (don’t chase).")
            else:
                st.success("Risk/Reward looks favorable for Target 1. If price comes to your entry, it’s a reasonable attempt.")

        if atr14 is not None and atr14 > 0:
            st.caption(
                f"ATR(14) is **{atr14:.2f}**. Planned risk is **{risk_per_share:.2f}/share**"
                + (f" (**{risk_atr:.2f} ATR**)." if risk_atr is not None else ".")
            )

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

    # --- Notes & Guidance ---
    st.subheader("Notes & Guidance")

    # Existing engine notes
    if plan.notes:
        for n in plan.notes:
            st.warning(n)

    # --- R & ATR Sanity Check ---
    st.markdown("### Risk & Volatility Sanity Check")
    st.caption("Use this quick checklist to decide if the plan is reasonable before placing orders.")

    # ATR explanation
    if atr14 is not None and atr14 > 0:
        st.write(
            f"- **ATR (14): {atr14:.2f}** — this ticker typically moves about **${atr14:.2f} per day**. "
            "Higher ATR means wider normal swings; stops and targets should be wider too."
        )
    else:
        st.write("- **ATR (14):** n/a")

    # Risk vs ATR
    if risk_atr is not None:
        if risk_atr < 0.7:
            st.warning(
                f"- **Planned Risk:** **{risk_atr:.2f} ATR** — very tight relative to daily movement; could be stopped by normal noise."
            )
        elif risk_atr <= 1.3:
            st.success(
                f"- **Planned Risk:** **{risk_atr:.2f} ATR** — well-calibrated for a daily plan; allows room for typical volatility."
            )
        elif risk_atr <= 1.8:
            st.info(
                f"- **Planned Risk:** **{risk_atr:.2f} ATR** — reasonable for volatile/trending tickers; consider sizing appropriately."
            )
        else:
            st.warning(
                f"- **Planned Risk:** **{risk_atr:.2f} ATR** — wide stop; ensure position size reflects the risk."
            )
    else:
        st.write("- **Planned Risk (in ATR):** n/a")

    # R multiple interpretation
    if r1 is not None:
        if r1 < 1.2:
            st.warning(
                f"- **Target 1 Reward:** **{r1:.2f}R** — reward may not sufficiently compensate for risk; consider waiting for a better entry."
            )
        elif r1 < 1.5:
            st.info(
                f"- **Target 1 Reward:** **{r1:.2f}R** — borderline; execution discipline matters (avoid chasing)."
            )
        else:
            st.success(
                f"- **Target 1 Reward:** **{r1:.2f}R** — favorable; if price comes to your entry, this is a reasonable attempt."
            )
    else:
        st.write("- **Target 1 Reward (R):** n/a")

    # Final summary
    if (risk_atr is not None) and (r1 is not None):
        if (risk_atr <= 1.8) and (r1 >= 1.5):
            st.success(
                "✅ **Overall Assessment:** Risk is reasonable relative to volatility and reward is sufficient. "
                "The key is patience — wait for price to come to your level."
            )
        else:
            st.info(
                "ℹ️ **Overall Assessment:** The plan is structurally valid, but either risk or reward is less favorable. "
                "Waiting for a better entry may improve the setup."
            )

    with st.expander("Raw Plan JSON (Advanced)"):
        st.json(plan.to_dict())

st.divider()

tab1, tab2, tab3, tab4 = st.tabs(["Quick Backtest", "Stats Summary", "Recent Logs", "Scanner"])

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
    st.dataframe(tbl, use_container_width=True, hide_index=True)

with tab3:
    st.caption("Recent plan snapshots saved locally (SQLite).")
    snaps = db.read_recent_snapshots(symbol=symbol, limit=25)
    st.dataframe(snaps, use_container_width=True, hide_index=True)

with tab4:
    st.subheader("Scanner")
    st.caption(
        "Scans a universe of tickers and ranks candidates using the same daily plan logic. "
        "Each ticker is evaluated using its own recommended stop/target defaults (per-ticker volatility-aware settings)."
    )

    # --- Universe Presets ---
    PRESETS = {
        "Recommended (Expanded S&P Core + ETFs)": [
            # Core index / style ETFs
            "SPY", "QQQ", "IWM", "DIA", "RSP", "SPYV", "SPYG", "SPLV",
            # Sector ETFs
            "XLK", "XLF", "XLE", "XLY", "XLP", "XLV", "XLI", "XLU", "XLB", "XLRE",
            # Subsector ETFs
            "SMH", "SOXX", "XBI", "IBB", "KRE", "KBE", "IGV", "SKYY", "ITA", "XAR", "OIH", "TAN", "ICLN",

            # S&P 500 heavy liquidity / high quality (curated)
            "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "AVGO", "CRM", "ADBE", "ORCL", "NOW",
            "CSCO", "INTC", "AMD", "QCOM", "TXN", "AMAT", "MU", "PANW", "CRWD", "NFLX",

            "BRK.B", "JPM", "BAC", "WFC", "C", "GS", "MS", "BLK", "SCHW", "AXP", "SPGI", "CME", "ICE",
            "PNC", "USB", "TFC",

            "UNH", "JNJ", "LLY", "PFE", "MRK", "ABBV", "TMO", "DHR", "ABT", "MDT", "BMY", "AMGN", "GILD",
            "ISRG", "VRTX", "CVS", "CI", "HUM",

            "TSLA", "HD", "LOW", "COST", "WMT", "TGT", "NKE", "SBUX", "MCD", "BKNG", "DIS", "CMCSA",

            "CAT", "DE", "HON", "GE", "LMT", "RTX", "BA", "UNP", "UPS", "FDX", "ADP", "WM", "ETN", "PH",

            "XOM", "CVX", "COP", "SLB", "EOG", "PSX", "MPC", "VLO",

            "LIN", "SHW", "FCX", "NEM", "APD", "ECL",

            "NEE", "DUK", "SO", "AEP", "EXC", "XEL",

            "AMT", "PLD", "EQIX", "DLR", "O",
        ],
        "ETFs Only (Indexes + Sectors + Subsectors)": [
            "SPY", "QQQ", "IWM", "DIA", "RSP", "SPYV", "SPYG", "SPLV",
            "XLK", "XLF", "XLE", "XLY", "XLP", "XLV", "XLI", "XLU", "XLB", "XLRE",
            "SMH", "SOXX", "XBI", "IBB", "KRE", "KBE", "IGV", "SKYY", "ITA", "XAR", "OIH", "TAN", "ICLN",
            "TLT", "IEF", "SHY", "GLD", "SLV", "UUP",
        ],
        "Leveraged Only (High Consequence)": [
            "SSO", "UPRO", "SPXL", "SDS", "SPXU", "SPXS",
            "QLD", "TQQQ", "SQQQ",
        ],
    }

    leveraged_set = {
        "SSO", "UPRO", "SPXL", "SDS", "SPXU", "SPXS",
        "QLD", "TQQQ", "SQQQ",
    }

    # --- Ranking ---
    def _score(sym: str, r1_: float | None, risk_atr_: float | None, entry_pct_: float | None) -> float | None:
        # Ranking uses ONLY normalized metrics; raw ATR should never be used in the score.
        if r1_ is None or risk_atr_ is None or entry_pct_ is None:
            return None

        is_lev = sym in leveraged_set

        # Coefficients (leveraged gets stricter penalties)
        if is_lev:
            w_r, w_risk, w_entry = 1.25, 1.20, 0.70
        else:
            w_r, w_risk, w_entry = 1.40, 0.90, 0.60

        # Soft caps to keep extreme values from dominating
        risk_atr_c = min(max(risk_atr_, 0.0), 3.0)
        entry_pct_c = min(max(entry_pct_, 0.0), 5.0)

        return (w_r * r1_) - (w_risk * risk_atr_c) - (w_entry * entry_pct_c)

    preset_name = st.selectbox("Universe Preset", list(PRESETS.keys()), index=0, key="scan_preset")
    preset_universe = PRESETS[preset_name]
    default_universe_text = "\n".join(preset_universe)

    universe_text = st.text_area(
        "Tickers to Scan (one per line)",
        value=default_universe_text,
        height=220,
        help="Tip: 50–150 tickers is fine with caching. Larger lists will run slower on Streamlit Cloud.",
        key="scan_universe_text",
    )
    universe = sorted({t.strip().upper() for t in universe_text.splitlines() if t.strip()})

    st.markdown("### Filters")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        min_r_to_t1 = st.slider("Min R to T1", 0.5, 4.0, 1.5, 0.1, key="scan_min_r1")
    with c2:
        max_risk_atr = st.slider("Max Risk (ATR)", 0.5, 3.0, 1.8, 0.1, key="scan_max_risk_atr")
    with c3:
        max_entry_away_pct = st.slider("Max Entry Away (%)", 0.0, 5.0, 1.0, 0.1, key="scan_max_entry_pct")
    with c4:
        min_bars = st.number_input("Min History (bars)", min_value=200, value=300, step=50, key="scan_min_bars")
    with c5:
        top_n = st.number_input("Show Top N", min_value=5, value=25, step=5, key="scan_top_n")

    show_all = st.checkbox("Show All (Including Fails)", value=False, key="scan_show_all")

    st.markdown("### Run Scan")

    @st.cache_data(show_spinner=False)
    def _get_daily(symbol_: str, source_: str, force_refresh_: bool):
        return md.get_daily_bars(symbol=symbol_, source=source_, force_refresh=force_refresh_)

    def _to_float(x):
        try:
            return float(x)
        except Exception:
            return None

    def _entry_away_pct(last_close: float | None, entry_: float | None) -> float | None:
        if last_close is None or entry_ is None or last_close == 0:
            return None
        return abs(entry_ - last_close) / last_close * 100.0

    def _risk_in_atr(risk_per_share_: float | None, atr14_: float | None) -> float | None:
        if risk_per_share_ is None or atr14_ is None or atr14_ <= 0:
            return None
        return risk_per_share_ / atr14_

    def _clamp_lookahead(x: int) -> int:
        # keep horizons aligned to the UI options
        return x if x in (10, 20, 40) else 20

    class _NoOpDB:
        """A no-op DB object to avoid writing scan runs to SQLite while keeping build_plan calls safe."""
        def __getattr__(self, _name):
            def _noop(*_args, **_kwargs):
                return None
            return _noop

    run = st.button("Scan Universe", type="primary", use_container_width=True, key="scan_run")

    if run:
        if not universe:
            st.warning("Universe is empty. Add tickers above and try again.")
            st.stop()

        results = []
        progress = st.progress(0)
        status = st.empty()

        for i, sym in enumerate(universe, start=1):
            status.write(f"Scanning **{sym}** ({i}/{len(universe)})…")

            try:
                dfi = _get_daily(sym, data_source, force_refresh)
                if dfi is None or dfi.empty or len(dfi) < int(min_bars):
                    progress.progress(i / len(universe))
                    continue

                # Per-ticker recommended parameters (the upgrade you asked for)
                dfi_feat = add_indicators(dfi, ema_fast=20, ema_mid=50, ema_slow=200, atr_n=14).dropna()
                if dfi_feat is None or dfi_feat.empty:
                    progress.progress(i / len(universe))
                    continue

                rec_i = recommend_trade_params(dfi_feat)
                lookahead_i = _clamp_lookahead(int(getattr(rec_i, "lookahead_days", 20)))
                stop_atr_i = float(getattr(rec_i, "stop_atr", 1.2))
                target1_atr_i = float(getattr(rec_i, "target1_atr", 2.0))
                target2_mult_i = float(getattr(rec_i, "target2_mult", 1.6))

                pl = build_plan(
                    symbol=sym,
                    df=dfi,
                    lookahead_bars=int(lookahead_i),
                    stop_atr=stop_atr_i,
                    target1_atr=target1_atr_i,
                    target2_mult=target2_mult_i,
                    max_risk_dollars=0.0,
                    db=_NoOpDB(),  # <- do not log scan runs
                )

                last_close = _to_float(getattr(pl, "last_close", None))
                entry_price = _to_float(getattr(pl, "entry_price", None))
                atr14_i = _to_float(getattr(pl, "atr14", None))
                risk_ps = _to_float(getattr(pl, "risk_per_share", None))
                r_to_t1 = _to_float(getattr(pl, "r_to_t1", None))
                r_to_t2 = _to_float(getattr(pl, "r_to_t2", None))

                entry_pct = _entry_away_pct(last_close, entry_price)
                risk_atr_i = _risk_in_atr(risk_ps, atr14_i)
                score = _score(sym, r_to_t1, risk_atr_i, entry_pct)

                # Filters (gatekeeper)
                passes = True
                if r_to_t1 is None or r_to_t1 < float(min_r_to_t1):
                    passes = False
                if risk_atr_i is None or risk_atr_i > float(max_risk_atr):
                    passes = False
                if entry_pct is None or entry_pct > float(max_entry_away_pct):
                    passes = False

                results.append({
                    "Ticker": sym,
                    "Type": "Leveraged" if sym in leveraged_set else "Standard",
                    "Regime": getattr(pl, "regime", ""),
                    "Setup": getattr(pl, "setup_name", ""),
                    "Last Close": last_close,
                    "Entry": entry_price,
                    "Stop": _to_float(getattr(pl, "stop_price", None)),
                    "Target 1": _to_float(getattr(pl, "target1_price", None)),
                    "Target 2": _to_float(getattr(pl, "target2_price", None)),
                    "ATR(14)": atr14_i,
                    "Risk (ATR)": risk_atr_i,
                    "R to T1": r_to_t1,
                    "R to T2": r_to_t2,
                    "Entry Away %": entry_pct,
                    "Rec Stop (ATR)": stop_atr_i,
                    "Rec Target (ATR)": target1_atr_i,
                    "Lookahead (Days)": lookahead_i,
                    "Score": score,
                    "Verdict": "✅ Pass" if passes else "—",
                })

            except Exception:
                # Keep scanning; do not fail the whole run
                pass

            progress.progress(i / len(universe))

        status.empty()

        if not results:
            st.warning("No results returned. Try fewer symbols, verify tickers, or disable Force Refresh.")
            st.stop()

        df_scan = pd.DataFrame(results)

        if not show_all:
            df_scan = df_scan[df_scan["Verdict"] == "✅ Pass"].copy()

        if df_scan.empty:
            st.warning("Nothing passed your filters. Try relaxing thresholds slightly or scanning a different universe preset.")
            st.stop()

        # Sort by Score (desc), then supporting fields
        df_scan = df_scan.sort_values(
            by=["Score", "R to T1", "Entry Away %", "Risk (ATR)"],
            ascending=[False, False, True, True],
            na_position="last",
        ).reset_index(drop=True)

        df_scan.insert(0, "Rank", df_scan.index + 1)

        st.markdown("### Ranked Results")
        st.dataframe(
            df_scan.head(int(top_n)),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Rank": st.column_config.NumberColumn(format="%d"),
                "Last Close": st.column_config.NumberColumn(format="%.2f"),
                "Entry": st.column_config.NumberColumn(format="%.2f"),
                "Stop": st.column_config.NumberColumn(format="%.2f"),
                "Target 1": st.column_config.NumberColumn(format="%.2f"),
                "Target 2": st.column_config.NumberColumn(format="%.2f"),
                "ATR(14)": st.column_config.NumberColumn(format="%.2f"),
                "Risk (ATR)": st.column_config.NumberColumn(format="%.2f"),
                "R to T1": st.column_config.NumberColumn(format="%.2f"),
                "R to T2": st.column_config.NumberColumn(format="%.2f"),
                "Entry Away %": st.column_config.NumberColumn(format="%.2f"),
                "Rec Stop (ATR)": st.column_config.NumberColumn(format="%.2f"),
                "Rec Target (ATR)": st.column_config.NumberColumn(format="%.2f"),
                "Lookahead (Days)": st.column_config.NumberColumn(format="%d"),
                "Score": st.column_config.NumberColumn(format="%.2f"),
            },
        )

        st.caption(
            "Ranking uses normalized metrics only: **R to T1**, **Risk in ATR**, and **Entry Away %**. "
            "Each ticker is evaluated using its own recommended stop/target defaults to stay fair across volatility profiles."
        )
