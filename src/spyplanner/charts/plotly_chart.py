from __future__ import annotations
import plotly.graph_objects as go


def plot_plan_chart(df, plan) -> go.Figure:
    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
        name="Price"
    ))

    # EMAs
    if "EMA_FAST" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["EMA_FAST"], name="EMA20", mode="lines"))
    if "EMA_MID" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["EMA_MID"], name="EMA50", mode="lines"))
    if "EMA_SLOW" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["EMA_SLOW"], name="EMA200", mode="lines"))

    # Plan lines (brighter colors for dark theme)
    fig.add_hline(
        y=plan.entry_price,
        line_dash="dash",
        line_color="#00E5FF",  # cyan
        line_width=2,
        annotation_text="Entry",
        annotation_position="top left",
    )
    fig.add_hline(
        y=plan.stop_price,
        line_dash="dot",
        line_color="#FF5252",  # red
        line_width=2,
        annotation_text="Stop",
        annotation_position="bottom left",
    )
    fig.add_hline(
        y=plan.target1_price,
        line_dash="dot",
        line_color="#69F0AE",  # green
        line_width=2,
        annotation_text="T1",
        annotation_position="top left",
    )
    fig.add_hline(
        y=plan.target2_price,
        line_dash="dot",
        line_color="#B388FF",  # purple
        line_width=2,
        annotation_text="T2",
        annotation_position="top left",
    )

    # Zones (slightly higher opacity + distinct colors)
    if plan.floor_zone:
        y0, y1 = plan.floor_zone
        fig.add_hrect(
            y0=y0,
            y1=y1,
            opacity=0.25,
            line_width=0,
            fillcolor="#2E7D32",  # green
            annotation_text="Floor",
            annotation_position="bottom left",
        )
    if plan.ceiling_zone:
        y0, y1 = plan.ceiling_zone
        fig.add_hrect(
            y0=y0,
            y1=y1,
            opacity=0.25,
            line_width=0,
            fillcolor="#EF6C00",  # orange
            annotation_text="Ceiling",
            annotation_position="top left",
        )

    fig.update_layout(
        title=f"{plan.symbol} (1D) — {plan.regime} — {plan.setup_name}",
        xaxis_rangeslider_visible=False,
        height=650,
        margin=dict(l=10, r=10, t=50, b=10),
    )
    return fig
