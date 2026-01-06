# SPY Planner (Daily)

A daily-first plan generator for a single ticker (default: SPY). Produces:
- Regime classification (trend / range / high-vol)
- Floor/ceiling zones from swing highs/lows
- Setup-driven plan (trend pullback or mean reversion)
- Stops/targets and R-multiples
- Probability stats from historical labeled outcomes (target hit before stop)
- Streamlit UI with chart overlays + plan card + backtest + stats

## Quickstart

### 1) Create venv & install
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
