"""
Financial Repression Monitor
=============================
Streamlit app that auto-pulls live data from FRED and Yahoo Finance
and scores each indicator against repression thresholds.

Run:
    streamlit run app.py

Required env var (optional but recommended for higher FRED rate limits):
    FRED_API_KEY=your_key_here   (free at https://fred.stlouisfed.org/docs/api/api_key.html)
"""

import os
import time
import datetime
import warnings
warnings.filterwarnings("ignore")

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from data_fetcher import fetch_all_indicators
from indicators   import build_scorecard, WATCHLIST, CATALYSTS

# ─── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Financial Repression Monitor",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS (dark theme matching original HTML) ─────────────────────────────
st.markdown("""
<style>
  /* Global */
  html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
  .stApp { background-color: #0d0f12; color: #e8eaf0; }

  /* Hide default Streamlit chrome */
  #MainMenu, footer, header { visibility: hidden; }
  .block-container { padding-top: 1.5rem; padding-bottom: 3rem; max-width: 1100px; }

  /* Section labels */
  .sec-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px; letter-spacing: .1em;
    text-transform: uppercase; color: #5c6475;
    border-bottom: 1px solid #242830;
    padding-bottom: 6px; margin-bottom: 4px;
  }

  /* Score ring card */
  .score-card {
    background: #13161b; border: 1px solid #242830;
    border-radius: 10px; padding: 1.2rem 1.4rem;
  }
  .score-verdict { font-size: 1.1rem; font-weight: 700; color: #d4913a; }
  .score-sub { font-size: .82rem; color: #9aa3b2; margin-top: 4px; line-height: 1.5; }

  /* Indicator cards */
  .ind-card {
    border-radius: 10px; padding: 1rem 1.1rem;
    margin-bottom: 10px;
    border-left-width: 4px; border-left-style: solid;
    background: #13161b; border-top: 1px solid #242830;
    border-right: 1px solid #242830; border-bottom: 1px solid #242830;
  }
  .ind-card.red    { border-left-color: #e05252; }
  .ind-card.amber  { border-left-color: #d4913a; }
  .ind-card.green  { border-left-color: #5a9e47; }

  .ind-name  { font-size: .95rem; font-weight: 600; color: #e8eaf0; }
  .ind-sub   { font-size: .72rem; font-family: monospace; color: #5c6475; margin-top: 1px; }
  .ind-note  { font-size: .78rem; color: #9aa3b2; line-height: 1.55;
               border-top: 1px solid #242830; margin-top: 8px; padding-top: 8px; }

  .badge {
    display: inline-block; font-size: .72rem; font-family: monospace;
    font-weight: 600; padding: 3px 10px; border-radius: 5px;
  }
  .badge-red   { background: #2a1818; color: #e05252; border: 1px solid #3d1f1f; }
  .badge-amber { background: #271d10; color: #d4913a; border: 1px solid #3a2810; }
  .badge-green { background: #152010; color: #5a9e47; border: 1px solid #1c2e14; }

  /* Timeline */
  .tl-item { display: flex; gap: 12px; padding-bottom: 16px; }
  .tl-dot-r { width:20px;height:20px;border-radius:50%;background:#2a1818;
               border:1.5px solid #e05252;color:#e05252;display:flex;
               align-items:center;justify-content:center;font-size:9px;
               font-weight:700;flex-shrink:0;margin-top:2px; }
  .tl-dot-a { width:20px;height:20px;border-radius:50%;background:#271d10;
               border:1.5px solid #d4913a;color:#d4913a;display:flex;
               align-items:center;justify-content:center;font-size:9px;
               font-weight:700;flex-shrink:0;margin-top:2px; }
  .tl-title { font-size:.88rem;font-weight:600;color:#e8eaf0;margin-bottom:3px; }
  .tl-desc  { font-size:.78rem;color:#9aa3b2;line-height:1.55; }

  /* Watch cards */
  .watch-card {
    background:#13161b;border:1px solid #242830;border-radius:10px;
    padding:.9rem 1rem;height:100%;
  }
  .watch-title { font-size:.88rem;font-weight:600;color:#e8eaf0;margin-bottom:2px; }
  .watch-freq  { font-size:.7rem;font-family:monospace;color:#5c6475;margin-bottom:6px; }
  .watch-desc  { font-size:.77rem;color:#9aa3b2;line-height:1.5;margin-bottom:8px; }

  /* Metric boxes */
  .metric-box {
    background:#13161b;border:1px solid #242830;border-radius:10px;
    padding:.9rem 1rem;text-align:center;
  }
  .metric-val  { font-size:1.6rem;font-weight:700;font-family:monospace; }
  .metric-label{ font-size:.72rem;color:#5c6475;text-transform:uppercase;
                 letter-spacing:.06em;margin-top:2px; }

  /* Plotly override */
  .js-plotly-plot .plotly { background: transparent !important; }
</style>
""", unsafe_allow_html=True)


# ─── Helpers ───────────────────────────────────────────────────────────────────

def color_hex(status: str) -> str:
    return {"red": "#e05252", "amber": "#d4913a", "green": "#5a9e47"}.get(status, "#9aa3b2")

def badge_html(text: str, status: str) -> str:
    return f'<span class="badge badge-{status}">{text}</span>'

def status_icon(status: str) -> str:
    return {"red": "🔴", "amber": "🟡", "green": "🟢"}.get(status, "⚪")


def make_gauge(score: int) -> go.Figure:
    """Plotly gauge for the overall repression score."""
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number={"font": {"size": 36, "color": "#d4913a", "family": "monospace"},
                "suffix": "/10"},
        gauge={
            "axis": {"range": [0, 10], "tickwidth": 1, "tickcolor": "#5c6475",
                     "tickfont": {"color": "#5c6475", "size": 10}},
            "bar":  {"color": "#d4913a", "thickness": 0.25},
            "bgcolor": "#13161b",
            "borderwidth": 0,
            "steps": [
                {"range": [0, 3],  "color": "#152010"},
                {"range": [3, 6],  "color": "#1e1c10"},
                {"range": [6, 8],  "color": "#271d10"},
                {"range": [8, 10], "color": "#2a1818"},
            ],
            "threshold": {
                "line": {"color": "#e05252", "width": 2},
                "thickness": 0.75, "value": 8,
            },
        },
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=20, b=10, l=20, r=20), height=200,
        font={"color": "#9aa3b2"},
    )
    return fig


def make_history_chart(series: pd.Series, title: str, threshold: float | None,
                       threshold_label: str, color: str = "#4a8fd4",
                       fill: bool = False) -> go.Figure:
    """
    Line chart with an optional horizontal threshold line.
    threshold=None skips the threshold line entirely (used for KRE price chart).
    fill=True adds a subtle area fill under the line — fills to min value, not zero,
    so price charts don't collapse the y-axis.
    """
    fig = go.Figure()

    vals = series.dropna().values
    idx  = series.dropna().index

    # Subtle fill under line — use "tonexty" against a transparent baseline
    # so the y-axis stays anchored to the data range, not to zero
    if fill:
        y_min = float(vals.min()) * 0.97   # baseline just below data
        fig.add_trace(go.Scatter(
            x=idx, y=[y_min] * len(idx),
            line=dict(width=0), showlegend=False,
            hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=idx, y=vals,
            fill="tonexty",
            fillcolor=f"rgba({_hex_to_rgb(color)},0.10)",
            line=dict(color=color, width=1.5),
            name=title, hovertemplate="%{y:.2f}<extra></extra>",
        ))
    else:
        fig.add_trace(go.Scatter(
            x=idx, y=vals,
            line=dict(color=color, width=1.5),
            name=title, hovertemplate="%{y:.2f}<extra></extra>",
        ))

    # Only add threshold line when a real value is provided
    if threshold is not None:
        fig.add_hline(
            y=threshold,
            line_dash="dot", line_color="#e05252", line_width=1.5,
            annotation_text=f"  {threshold_label}",
            annotation_font_color="#e05252", annotation_font_size=10,
        )

    # Lock y-axis range to data — prevents threshold line from distorting scale
    y_pad = (vals.max() - vals.min()) * 0.08 if len(vals) > 1 else 1
    y_range = [vals.min() - y_pad, vals.max() + y_pad]

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=10, b=30, l=40, r=20), height=220,
        showlegend=False,
        xaxis=dict(showgrid=False, tickfont=dict(color="#5c6475", size=10),
                   linecolor="#242830"),
        yaxis=dict(gridcolor="#1a1e25", tickfont=dict(color="#5c6475", size=10),
                   linecolor="#242830", range=y_range),
        hovermode="x unified",
    )
    return fig


def _hex_to_rgb(h: str) -> str:
    h = h.lstrip("#")
    return ",".join(str(int(h[i:i+2], 16)) for i in (0, 2, 4))


# ─── Main App ─────────────────────────────────────────────────────────────────

def main():
    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown('<p class="sec-label">Macro research · Financial repression monitor</p>',
                unsafe_allow_html=True)

    col_title, col_refresh = st.columns([6, 1])
    with col_title:
        st.markdown("## Financial Repression Proximity Monitor")
        st.markdown(
            "<span style='color:#9aa3b2;font-size:.88rem;'>"
            "Live data from FRED &amp; Yahoo Finance · Scores each indicator against repression thresholds"
            "</span>", unsafe_allow_html=True
        )
    with col_refresh:
        st.markdown("<br>", unsafe_allow_html=True)
        refresh = st.button("🔄 Refresh data", use_container_width=True)

    st.markdown("---")

    # ── FRED API key notice ────────────────────────────────────────────────────
    fred_key = os.environ.get("FRED_API_KEY", "")
    if not fred_key:
        st.info(
            "💡 **Optional:** Set a `FRED_API_KEY` environment variable for higher rate limits. "
            "Get a free key at [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html). "
            "The app works without it using public FRED endpoints.",
            icon=None,
        )

    # ── Data fetch (cached 1 hour) ─────────────────────────────────────────────
    cache_key = "indicator_data"
    cache_ts   = "indicator_ts"
    TTL = 3600  # seconds

    now = time.time()

    # Invalidate cache if it's missing H.4.1 balance sheet keys
    # (happens when app was deployed before that fetch block was added)
    cached_raw = st.session_state.get(cache_key, {})
    bs_missing = "bs_total_assets_latest" not in cached_raw

    if refresh or cache_key not in st.session_state or bs_missing or \
       (now - st.session_state.get(cache_ts, 0)) > TTL:
        reason = ("missing H.4.1 keys" if bs_missing else
                  "manual refresh"     if refresh    else "TTL expired / first load")
        with st.spinner(f"Fetching live data from FRED & Yahoo Finance… ({reason})"):
            try:
                raw = fetch_all_indicators(fred_api_key=fred_key)
                st.session_state[cache_key] = raw
                st.session_state[cache_ts]  = now
            except Exception as e:
                st.error(f"Data fetch error: {e}")
                st.stop()

    raw = st.session_state[cache_key]

    # ── Build scorecard ────────────────────────────────────────────────────────
    scorecard = build_scorecard(raw)
    overall   = scorecard["overall_score"]
    indicators = scorecard["indicators"]

    # ── Top KPI row ────────────────────────────────────────────────────────────
    updated_str = datetime.datetime.fromtimestamp(
        st.session_state.get(cache_ts, now)
    ).strftime("%b %d, %Y  %I:%M %p")

    kpi_cols = st.columns([2, 2, 2, 2, 3])
    kpis = [
        ("Debt / GDP",          raw.get("debt_gdp_pct", "N/A"),     "%",  "#e05252"),
        ("10-yr TIPS Real Yld", raw.get("tips_real_yield", "N/A"),  "%",  "#d4913a"),
        ("Real Policy Rate",    raw.get("real_policy_rate", "N/A"), "%",  "#d4913a"),
        ("HY Credit Spread",    raw.get("hy_spread", "N/A"),        "%",  "#5a9e47"),
    ]
    for col, (label, val, unit, clr) in zip(kpi_cols[:4], kpis):
        with col:
            val_str = f"{val:.2f}{unit}" if isinstance(val, float) else str(val)
            st.markdown(
                f'<div class="metric-box">'
                f'<div class="metric-val" style="color:{clr};">{val_str}</div>'
                f'<div class="metric-label">{label}</div>'
                f'</div>', unsafe_allow_html=True
            )
    with kpi_cols[4]:
        st.markdown(
            f'<div class="metric-box">'
            f'<div style="font-size:.7rem;color:#5c6475;text-transform:uppercase;letter-spacing:.06em;">Last updated</div>'
            f'<div style="font-size:.95rem;font-weight:600;color:#e8eaf0;margin-top:4px;">{updated_str}</div>'
            f'<div style="font-size:.7rem;color:#5c6475;margin-top:2px;">Auto-refreshes every hour</div>'
            f'</div>', unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Score gauge + summary ──────────────────────────────────────────────────
    g_col, s_col = st.columns([1, 2])
    with g_col:
        st.plotly_chart(make_gauge(overall), use_container_width=True,
                        config={"displayModeBar": False})
    with s_col:
        triggered = sum(1 for ind in indicators if ind["status"] == "red")
        watching  = sum(1 for ind in indicators if ind["status"] == "amber")
        clear     = sum(1 for ind in indicators if ind["status"] == "green")

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(
            f'<div class="score-card">'
            f'<div class="score-verdict">{"STRUCTURALLY PRIMED — MECHANISTICALLY INCOMPLETE" if overall >= 6 else "ELEVATED" if overall >= 4 else "LOW RISK"}</div>'
            f'<div class="score-sub">'
            f'Every long-run structural precondition for financial repression is in place. '
            f'The operational trigger arrives May 2026 with the new Fed chair appointment — '
            f'the most important inflection point for repression risk in a generation.'
            f'</div>'
            f'<br>'
            f'<span style="margin-right:16px;">🔴 <b>{triggered}</b> breached</span>'
            f'<span style="margin-right:16px;">🟡 <b>{watching}</b> watching</span>'
            f'<span>🟢 <b>{clear}</b> clear</span>'
            f'</div>', unsafe_allow_html=True
        )

    st.markdown("---")

    # ── Tabs: Scorecard | Charts | Timeline | Watchlist ───────────────────────
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        ["📋 Indicator Scorecard", "📈 Historical Charts", "⏱ Catalyst Timeline", "👁 Daily Watchlist", "💰 Wealth-Building Assets", "🏦 Fed Balance Sheet (H.4.1)"]
    )

    # ── TAB 1: SCORECARD ──────────────────────────────────────────────────────
    with tab1:
        st.markdown('<p class="sec-label">Indicator-by-indicator scorecard</p>',
                    unsafe_allow_html=True)

        for ind in indicators:
            status  = ind["status"]
            bar_pct = min(ind["bar_pct"], 100)
            bar_clr = color_hex(status)

            st.markdown(
                f'<div class="ind-card {status}">'
                f'<div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;margin-bottom:10px;">'
                f'  <div>'
                f'    <div class="ind-name">{status_icon(status)} {ind["name"]}</div>'
                f'    <div class="ind-sub">{ind["sub"]}</div>'
                f'  </div>'
                f'  {badge_html(ind["reading"], status)}'
                f'</div>'
                # progress bar
                f'<div style="display:flex;justify-content:space-between;font-size:.7rem;color:#5c6475;font-family:monospace;margin-bottom:5px;">'
                f'  <span>{ind["bar_left"]}</span><span>{ind["bar_right"]}</span>'
                f'</div>'
                f'<div style="height:6px;background:#1a1e25;border-radius:3px;overflow:hidden;border:1px solid #242830;">'
                f'  <div style="height:100%;width:{bar_pct}%;background:linear-gradient(90deg,{bar_clr}88,{bar_clr});border-radius:3px;"></div>'
                f'</div>'
                f'<div class="ind-note">{ind["note"]}</div>'
                f'</div>',
                unsafe_allow_html=True
            )

    # ── TAB 2: HISTORICAL CHARTS ───────────────────────────────────────────────
    with tab2:
        st.markdown('<p class="sec-label">Historical data — last 5 years</p>',
                    unsafe_allow_html=True)

        # ── SPY vs Treasury Yield Overlay ──────────────────────────────────────
        st.markdown("### SPY vs 2, 10 & 30-Year Treasury Yields")
        st.markdown(
            "<span style='color:#9aa3b2;font-size:.82rem;'>"
            "Overlays SPY price (right axis) with 2-yr, 10-yr, and 30-yr Treasury yields (left axis). "
            "When Treasury yields rise above the SPY earnings yield (~"
            f"{raw.get('spy_earnings_yield', 0) or 0:.1f}% today"
            "), bonds compete with equities for capital — a key repression signal."
            "</span>",
            unsafe_allow_html=True
        )

        # Controls row
        ctrl1, ctrl2, ctrl3 = st.columns([2, 2, 3])
        with ctrl1:
            show_spy_price = st.toggle("Show SPY price", value=True, key="tog_spy")
        with ctrl2:
            show_earnings_yield = st.toggle("Show SPY earnings yield", value=True,
                                             key="tog_ey")
        with ctrl3:
            chart_period = st.select_slider(
                "Period", options=["1Y", "2Y", "3Y", "5Y"], value="5Y",
                key="chart_period"
            )

        period_days = {"1Y": 252, "2Y": 504, "3Y": 756, "5Y": 1260}[chart_period]

        # Build overlay figure
        fig_overlay = go.Figure()

        # ── Bond yield traces (left y-axis) ────────────────────────────────────
        bond_series = [
            ("treasury_2y_series",  "2-yr Treasury",  "#4a8fd4", "dash"),
            ("treasury_10y_series", "10-yr Treasury", "#d4913a", "solid"),
            ("treasury_30y_series", "30-yr Treasury", "#e05252", "dot"),
        ]
        for key_name, label, color, dash in bond_series:
            s = raw.get(key_name, pd.Series(dtype=float))
            if s is not None and len(s) > 0:
                s_trim = s.dropna().tail(period_days)
                fig_overlay.add_trace(go.Scatter(
                    x=s_trim.index, y=s_trim.values,
                    name=label,
                    line=dict(color=color, width=2, dash=dash),
                    yaxis="y1",
                    hovertemplate=f"{label}: %{{y:.2f}}%<extra></extra>",
                ))

        # ── SPY earnings yield (left y-axis, same scale as bond yields) ────────
        if show_earnings_yield:
            ey = raw.get("spy_earnings_yield_series", pd.Series(dtype=float))
            if ey is not None and len(ey) > 0:
                ey_trim = ey.dropna().tail(period_days)
                fig_overlay.add_trace(go.Scatter(
                    x=ey_trim.index, y=ey_trim.values,
                    name="SPY Earnings Yield (EPS/Price)",
                    line=dict(color="#5a9e47", width=1.8, dash="dashdot"),
                    yaxis="y1",
                    hovertemplate="SPY Earnings Yield: %{y:.2f}%<extra></extra>",
                ))

        # ── SPY price (right y-axis) ────────────────────────────────────────────
        if show_spy_price:
            spy_s = raw.get("spy_series", pd.Series(dtype=float))
            if spy_s is not None and len(spy_s) > 0:
                spy_trim = spy_s.dropna().tail(period_days)
                fig_overlay.add_trace(go.Scatter(
                    x=spy_trim.index, y=spy_trim.values,
                    name="SPY Price ($)",
                    line=dict(color="rgba(255,255,255,0.25)", width=1.5),
                    fill="tozeroy",
                    fillcolor="rgba(255,255,255,0.04)",
                    yaxis="y2",
                    hovertemplate="SPY: $%{y:.2f}<extra></extra>",
                ))

        # ── Layout with dual axes ───────────────────────────────────────────────
        # Compute y-ranges for both axes
        bond_vals = []
        for key_name, _, _, _ in bond_series:
            s = raw.get(key_name, pd.Series(dtype=float))
            if s is not None and len(s) > 0:
                bond_vals.extend(s.dropna().tail(period_days).values.tolist())
        if show_earnings_yield:
            ey = raw.get("spy_earnings_yield_series", pd.Series(dtype=float))
            if ey is not None and len(ey) > 0:
                bond_vals.extend(ey.dropna().tail(period_days).values.tolist())

        y1_min = max(0, min(bond_vals) - 0.3) if bond_vals else 0
        y1_max = max(bond_vals) + 0.5 if bond_vals else 10

        spy_vals = []
        if show_spy_price:
            spy_s = raw.get("spy_series", pd.Series(dtype=float))
            if spy_s is not None and len(spy_s) > 0:
                spy_vals = spy_s.dropna().tail(period_days).values.tolist()
        y2_min = min(spy_vals) * 0.92 if spy_vals else 0
        y2_max = max(spy_vals) * 1.05 if spy_vals else 600

        fig_overlay.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=420,
            margin=dict(t=10, b=50, l=55, r=65),
            hovermode="x unified",
            legend=dict(
                orientation="h", yanchor="bottom", y=1.01,
                xanchor="left", x=0,
                font=dict(color="#9aa3b2", size=11),
                bgcolor="rgba(0,0,0,0)",
            ),
            xaxis=dict(
                showgrid=False,
                tickfont=dict(color="#5c6475", size=10),
                linecolor="#242830",
            ),
            yaxis=dict(
                title="Yield (%)",
                title_font=dict(color="#9aa3b2", size=11),
                tickfont=dict(color="#9aa3b2", size=10),
                gridcolor="#1a1e25",
                linecolor="#242830",
                range=[y1_min, y1_max],
                ticksuffix="%",
                side="left",
            ),
            yaxis2=dict(
                title="SPY Price ($)",
                title_font=dict(color="#5c6475", size=11),
                tickfont=dict(color="#5c6475", size=10),
                gridcolor="rgba(0,0,0,0)",
                linecolor="#242830",
                range=[y2_min, y2_max],
                tickprefix="$",
                side="right",
                overlaying="y",
                showgrid=False,
            ),
        )

        st.plotly_chart(fig_overlay, use_container_width=True,
                        config={"displayModeBar": True,
                                "modeBarButtonsToRemove": ["lasso2d", "select2d"]})

        # ── Current spread callouts ─────────────────────────────────────────────
        t2  = raw.get("treasury_2y")
        t10 = raw.get("treasury_10y")
        t30 = raw.get("treasury_30y")
        ey  = raw.get("spy_earnings_yield")
        spy_px = raw.get("spy_latest")

        m1, m2, m3, m4, m5 = st.columns(5)
        for col, label, val, color, suffix in [
            (m1, "2-yr Yield",       t2,  "#4a8fd4", "%"),
            (m2, "10-yr Yield",      t10, "#d4913a", "%"),
            (m3, "30-yr Yield",      t30, "#e05252", "%"),
            (m4, "SPY Earn. Yield",  ey,  "#5a9e47", "%"),
            (m5, "SPY Price",        spy_px, "#9aa3b2", ""),
        ]:
            val_str = (f"${val:,.2f}" if suffix == "" and val
                       else f"{val:.2f}{suffix}" if val else "N/A")
            col.markdown(
                f'<div style="background:#13161b;border:1px solid #242830;'
                f'border-radius:8px;padding:.65rem .85rem;text-align:center;">'
                f'<div style="font-size:1.1rem;font-weight:700;font-family:monospace;'
                f'color:{color};">{val_str}</div>'
                f'<div style="font-size:.68rem;color:#5c6475;text-transform:uppercase;'
                f'letter-spacing:.05em;margin-top:2px;">{label}</div>'
                f'</div>',
                unsafe_allow_html=True
            )

        # Yield curve shape callout
        if t2 and t10:
            spread_2_10 = round(t10 - t2, 2)
            curve_color = "#5a9e47" if spread_2_10 > 0 else "#e05252"
            curve_label = "Normal (upward sloping)" if spread_2_10 > 0.3 else \
                          "Flat" if spread_2_10 >= 0 else "INVERTED ⚠"
            st.markdown(
                f'<div style="margin-top:10px;font-size:.8rem;color:#9aa3b2;">'
                f'2s10s spread: <b style="color:{curve_color};">'
                f'{spread_2_10:+.2f}%</b> — Yield curve: '
                f'<b style="color:{curve_color};">{curve_label}</b>'
                f'</div>',
                unsafe_allow_html=True
            )

        st.markdown("---")

        # ── Individual macro charts (existing) ─────────────────────────────────
        st.markdown("**Individual macro indicator charts**")

        series_map = {
            "10-yr TIPS Real Yield (%)":    ("tips_real_yield_series",   0.0,  "Repression threshold: 0%",  "#4a8fd4"),
            "10-yr Treasury Nominal Yield":  ("treasury_10y_series",      5.0,  "Stress threshold: 5%",      "#d4913a"),
            "10-yr Breakeven Inflation (%)": ("breakeven_series",         3.0,  "Alert: 3%",                 "#5a9e47"),
            "Real Policy Rate (%)":          ("real_policy_rate_series",  0.0,  "Repression threshold: 0%",  "#e05252"),
            "HY Credit Spread (OAS %)":      ("hy_spread_series",         6.0,  "Alert threshold: 6%",       "#c76bdb"),
            "KRE Regional Bank ETF ($)":     ("kre_series",               None, "",                          "#4a8fd4"),
        }

        chart_cols = st.columns(2)
        for i, (title, (key, threshold, t_label, clr)) in enumerate(series_map.items()):
            series = raw.get(key)
            with chart_cols[i % 2]:
                st.markdown(f"**{title}**")
                if series is not None and len(series) > 0:
                    if threshold is not None:
                        fig = make_history_chart(series, title, threshold, t_label, clr)
                    else:
                        kre_52w = raw.get("kre_52w_high")
                        kre_threshold = round(kre_52w * 0.70, 2) if kre_52w else None
                        kre_label = f"−30% alert (${kre_threshold:.2f})" if kre_threshold else ""
                        fig = make_history_chart(
                            series, title, kre_threshold, kre_label, clr, fill=True
                        )
                    st.plotly_chart(fig, use_container_width=True,
                                    config={"displayModeBar": False})
                else:
                    st.markdown(
                        '<div style="background:#13161b;border:1px solid #242830;border-radius:10px;'
                        'padding:2rem;text-align:center;color:#5c6475;font-size:.8rem;">'
                        'Data unavailable — check FRED connection</div>',
                        unsafe_allow_html=True
                    )

    # ── TAB 3: CATALYST TIMELINE ───────────────────────────────────────────────
    with tab3:
        st.markdown('<p class="sec-label">Key catalysts — what to watch and when</p>',
                    unsafe_allow_html=True)

        for cat in CATALYSTS:
            dot_class = "tl-dot-r" if cat["urgency"] == "high" else "tl-dot-a"
            symbol    = "!" if cat["urgency"] == "high" else "~"
            st.markdown(
                f'<div class="tl-item">'
                f'<div class="{dot_class}">{symbol}</div>'
                f'<div>'
                f'  <div class="tl-title">{cat["title"]}</div>'
                f'  <div class="tl-desc">{cat["desc"]}</div>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True
            )
            st.markdown(
                '<div style="height:1px;background:#242830;margin:0 0 0 34px;"></div>',
                unsafe_allow_html=True
            )

    # ── TAB 4: DAILY WATCHLIST ─────────────────────────────────────────────────
    with tab4:
        st.markdown('<p class="sec-label">Daily / weekly watchlist</p>',
                    unsafe_allow_html=True)

        w_cols = st.columns(3)
        for i, w in enumerate(WATCHLIST):
            status_clr = {"safe": "#5a9e47", "warn": "#d4913a", "alert": "#e05252"}[w["status_class"]]
            badge_cls  = {"safe": "badge-green", "warn": "badge-amber", "alert": "badge-red"}[w["status_class"]]
            with w_cols[i % 3]:
                st.markdown(
                    f'<div class="watch-card">'
                    f'<div class="watch-title">{w["title"]}</div>'
                    f'<div class="watch-freq">{w["freq"]}</div>'
                    f'<div class="watch-desc">{w["desc"]}</div>'
                    f'<span class="badge {badge_cls}">{w["status"]}</span>'
                    f'</div><br>',
                    unsafe_allow_html=True
                )

    # ── TAB 5: WEALTH-BUILDING ASSETS ─────────────────────────────────────────
    with tab5:
        wealth_assets_tab(raw)

    # ── TAB 6: FED BALANCE SHEET ───────────────────────────────────────────────
    with tab6:
        fed_balance_sheet_tab(raw)

    # ── Footer ────────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        "<div style='font-size:.72rem;color:#5c6475;line-height:1.6;'>"
        "<b>Sources:</b> IMF World Economic Outlook · CBO Budget &amp; Economic Outlook · "
        "FRED (Federal Reserve Bank of St. Louis) · Yahoo Finance · "
        "ICE BofA Bond Indices (via FRED) · NY Fed ACM Term Premium Model.<br>"
        "<b>Disclaimer:</b> Educational research only — not investment advice. "
        "Past performance does not guarantee future results."
        "</div>",
        unsafe_allow_html=True
    )


# ─────────────────────────────────────────────────────────────────────────────
#  FED BALANCE SHEET (H.4.1) TAB
# ─────────────────────────────────────────────────────────────────────────────

def fed_balance_sheet_tab(raw: dict):
    """
    Renders the Fed H.4.1 Balance Sheet weekly tracker tab.
    Data sourced from FRED — updated every Thursday at 4:30 PM ET.
    """
    from data_fetcher import fetch_fred, latest

    st.markdown("""
    <style>
      .bs-kpi {
        background: #13161b; border: 1px solid #242830; border-radius: 10px;
        padding: .9rem 1rem; text-align: center;
      }
      .bs-kpi-val   { font-size: 1.55rem; font-weight: 700; font-family: monospace; }
      .bs-kpi-label { font-size: .7rem; text-transform: uppercase; letter-spacing: .06em;
                      color: #5c6475; margin-top: 3px; }
      .bs-kpi-sub   { font-size: .72rem; color: #5c6475; margin-top: 2px; }

      .bs-card {
        background: #13161b; border: 1px solid #242830; border-radius: 10px;
        padding: 1rem 1.1rem; margin-bottom: 10px; border-left: 3px solid;
      }
      .bs-card-title { font-size: .92rem; font-weight: 600; color: #e8eaf0; margin-bottom: 3px; }
      .bs-card-val   { font-size: 1.3rem; font-weight: 700; font-family: monospace; margin-bottom: 4px; }
      .bs-card-sub   { font-size: .75rem; color: #9aa3b2; line-height: 1.5; margin-bottom: 6px; }
      .bs-card-why   { font-size: .78rem; color: #5c6475; line-height: 1.5; border-top: 1px solid #1a1e25;
                       padding-top: 7px; margin-top: 4px; }

      .timeline-entry {
        display: flex; gap: 12px; padding-bottom: 14px; position: relative;
      }
      .timeline-entry:not(:last-child)::before {
        content: ''; position: absolute; left: 10px; top: 22px; bottom: 0;
        width: 1px; background: #242830;
      }
      .tl-dot-bs {
        width: 21px; height: 21px; border-radius: 50%; flex-shrink: 0;
        display: flex; align-items: center; justify-content: center;
        font-size: 9px; font-weight: 700; margin-top: 1px;
      }
    </style>
    """, unsafe_allow_html=True)

    # ── Header ─────────────────────────────────────────────────────────────────
    st.markdown('<p class="sec-label">Federal Reserve H.4.1 · Balance Sheet Weekly Tracker</p>',
                unsafe_allow_html=True)

    import datetime as dt
    today      = dt.date.today()
    last_thurs = today - dt.timedelta(days=(today.weekday() - 3) % 7)
    next_thurs = last_thurs + dt.timedelta(days=7)

    st.markdown(
        f"<span style='color:#9aa3b2;font-size:.85rem;'>"
        f"Released every Thursday at 4:30 PM ET · "
        f"Last release: <b style='color:#e8eaf0;'>{last_thurs.strftime('%B %d, %Y')}</b> · "
        f"Next release: <b style='color:#e8eaf0;'>{next_thurs.strftime('%B %d, %Y')}</b>"
        f"</span>",
        unsafe_allow_html=True
    )
    st.markdown(
        "<span style='font-size:.78rem;color:#5c6475;'>"
        "Source: FRED — WALCL, TREAST, WSHOMCB, WTREGEN, WRESBAL, RRPONTSYD · "
        "<a href='https://www.federalreserve.gov/releases/h41/current/' "
        "style='color:#4a8fd4;'>View latest H.4.1 release →</a>"
        "</span>",
        unsafe_allow_html=True
    )
    st.markdown("<br>", unsafe_allow_html=True)

    # ── FRED fetch status ─────────────────────────────────────────────────────
    fetch_status = raw.get("bs_fetch_status", {})
    BS_SERIES = ["WALCL", "TREAST", "WSHOMCB", "WTREGEN", "WRESBAL", "RRPONTSYD"]

    loaded_bs  = [s for s in BS_SERIES if fetch_status.get(s, 0) > 0]
    missing_bs = [s for s in BS_SERIES if fetch_status.get(s, 0) == 0]

    # ── If no H.4.1 data at all, attempt inline fetch on the spot ─────────────
    if not fetch_status or len(loaded_bs) == 0:
        st.info("⏳ Fetching H.4.1 balance sheet data from FRED…")
        fred_key = os.environ.get("FRED_API_KEY", "")

        def _bs_inline(series_id, divisor):
            s = fetch_fred(series_id, fred_key, "2019-01-01")
            return (s / divisor) if len(s) > 0 else pd.Series(dtype=float)

        walcl_s   = _bs_inline("WALCL",     1e6)
        treast_s  = _bs_inline("TREAST",    1e6)
        mbs_s     = _bs_inline("WSHOMCB",   1e6)
        tga_s     = _bs_inline("WTREGEN",   1e3)
        resbal_s  = _bs_inline("WRESBAL",   1e3)
        rrp_s     = _bs_inline("RRPONTSYD", 1)

        # Patch into raw and session state so they persist for this session
        raw["bs_total_assets"]        = walcl_s
        raw["bs_total_assets_latest"] = latest(walcl_s)
        raw["bs_treasuries"]          = treast_s
        raw["bs_treasuries_latest"]   = latest(treast_s)
        raw["bs_mbs"]                 = mbs_s
        raw["bs_mbs_latest"]          = latest(mbs_s)
        raw["bs_tga"]                 = tga_s
        raw["bs_tga_latest"]          = latest(tga_s)
        raw["bs_reserves"]            = resbal_s
        raw["bs_reserves_latest"]     = latest(resbal_s)
        raw["bs_rrp"]                 = rrp_s
        raw["bs_rrp_latest"]          = latest(rrp_s)

        if len(walcl_s) >= 2:
            wc = walcl_s.dropna()
            raw["bs_wow_change_bn"] = round((wc.iloc[-1] - wc.iloc[-2]) * 1000, 1)
        bs_peak_t = 8.965
        walcl_lv = latest(walcl_s)
        raw["bs_drawdown_pct"] = (
            round((bs_peak_t - walcl_lv) / bs_peak_t * 100, 1)
            if walcl_lv else None
        )
        fetch_status = {
            "WALCL":     len(walcl_s),
            "TREAST":    len(treast_s),
            "WSHOMCB":   len(mbs_s),
            "WTREGEN":   len(tga_s),
            "WRESBAL":   len(resbal_s),
            "RRPONTSYD": len(rrp_s),
        }
        raw["bs_fetch_status"] = fetch_status
        if "indicator_data" in st.session_state:
            st.session_state["indicator_data"] = raw

        loaded_bs  = [s for s in BS_SERIES if fetch_status.get(s, 0) > 0]
        missing_bs = [s for s in BS_SERIES if fetch_status.get(s, 0) == 0]

        if loaded_bs:
            st.success(f"✅ Fetched {len(loaded_bs)}/6 H.4.1 series successfully.")
        else:
            st.error(
                "❌ Could not fetch H.4.1 data from FRED. "
                "FRED may be temporarily unavailable or rate-limited. "
                "Try clicking **🔄 Refresh data** in a minute."
            )
            if st.button("🔄 Retry now", type="primary", key="bs_force_refresh"):
                for k in ["indicator_data", "indicator_ts"]:
                    st.session_state.pop(k, None)
                st.rerun()
            return

    elif missing_bs:
        with st.expander(f"⚠️ {len(missing_bs)} series failed: {', '.join(missing_bs)}",
                         expanded=False):
            st.markdown(
                f"**Loaded ({len(loaded_bs)}):** {', '.join(loaded_bs)}\n\n"
                f"**Failed ({len(missing_bs)}):** {', '.join(missing_bs)}\n\n"
                "Possible causes: FRED rate limit (120 req/min), temporary network block. "
                f"Row counts: {fetch_status}"
            )
            if st.button("🔄 Retry FRED fetch", key="bs_retry"):
                st.session_state.pop("indicator_data", None)
                st.session_state.pop("indicator_ts", None)
                st.rerun()
    else:
        st.success(
            f"✅ All 6 H.4.1 series loaded — "
            f"{', '.join(f'{s}: {fetch_status[s]}' for s in BS_SERIES)} rows",
            icon=None,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Pull values ─────────────────────────────────────────────────────────────
    total_assets = raw.get("bs_total_assets_latest")   # trillions
    treasuries   = raw.get("bs_treasuries_latest")     # trillions
    mbs          = raw.get("bs_mbs_latest")            # trillions
    tga          = raw.get("bs_tga_latest")            # billions
    reserves     = raw.get("bs_reserves_latest")       # billions
    rrp          = raw.get("bs_rrp_latest")            # billions
    wow_change   = raw.get("bs_wow_change_bn")         # billions WoW change
    drawdown     = raw.get("bs_drawdown_pct")          # % from peak

    def fmt_T(v):
        return f"${v:.2f}T" if v is not None else "N/A"
    def fmt_B(v):
        return f"${v:,.0f}B" if v is not None else "N/A"
    def fmt_wow(v):
        if v is None: return "N/A"
        sign = "+" if v >= 0 else ""
        clr  = "#5a9e47" if v >= 0 else "#e05252"
        return sign, v, clr

    # QT vs QE signal
    if wow_change is not None:
        if wow_change >= 10:
            bs_signal, bs_signal_clr = "QE EXPANDING ⚠", "#e05252"
        elif wow_change >= 0:
            bs_signal, bs_signal_clr = "Flat / Slight Expansion", "#d4913a"
        else:
            bs_signal, bs_signal_clr = "QT SHRINKING ✓", "#5a9e47"
    else:
        bs_signal, bs_signal_clr = "N/A", "#5c6475"

    # ── Top KPI row ─────────────────────────────────────────────────────────────
    k1, k2, k3, k4, k5 = st.columns(5)

    with k1:
        wow_sign = "+" if (wow_change or 0) >= 0 else ""
        wow_clr  = "#5a9e47" if (wow_change or 0) <= 0 else "#e05252"
        wow_str  = f"{wow_sign}{wow_change:.1f}B WoW" if wow_change is not None else "N/A"
        st.markdown(
            f'<div class="bs-kpi">'
            f'<div class="bs-kpi-val" style="color:#4a8fd4;">{fmt_T(total_assets)}</div>'
            f'<div class="bs-kpi-label">Total Assets</div>'
            f'<div class="bs-kpi-sub" style="color:{wow_clr};">{wow_str}</div>'
            f'</div>', unsafe_allow_html=True
        )
    with k2:
        st.markdown(
            f'<div class="bs-kpi">'
            f'<div class="bs-kpi-val" style="color:#d4913a;">{fmt_T(treasuries)}</div>'
            f'<div class="bs-kpi-label">Treasuries Held</div>'
            f'<div class="bs-kpi-sub">TREAST</div>'
            f'</div>', unsafe_allow_html=True
        )
    with k3:
        st.markdown(
            f'<div class="bs-kpi">'
            f'<div class="bs-kpi-val" style="color:#c76bdb;">{fmt_T(mbs)}</div>'
            f'<div class="bs-kpi-label">MBS Held</div>'
            f'<div class="bs-kpi-sub">WSHOMCB</div>'
            f'</div>', unsafe_allow_html=True
        )
    with k4:
        st.markdown(
            f'<div class="bs-kpi">'
            f'<div class="bs-kpi-val" style="color:#5a9e47;">{fmt_B(reserves)}</div>'
            f'<div class="bs-kpi-label">Bank Reserves</div>'
            f'<div class="bs-kpi-sub">WRESBAL</div>'
            f'</div>', unsafe_allow_html=True
        )
    with k5:
        dd_clr = "#5a9e47" if (drawdown or 0) > 5 else "#d4913a"
        st.markdown(
            f'<div class="bs-kpi">'
            f'<div class="bs-kpi-val" style="color:{dd_clr};">−{drawdown:.1f}%</div>'
            f'<div class="bs-kpi-label">From Peak ($8.97T)</div>'
            f'<div class="bs-kpi-sub">QT progress</div>'
            f'</div>' if drawdown is not None else
            f'<div class="bs-kpi"><div class="bs-kpi-val">N/A</div>'
            f'<div class="bs-kpi-label">From Peak</div></div>',
            unsafe_allow_html=True
        )

    # ── QE/QT Signal banner ─────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        f'<div style="background:#13161b;border:1px solid #242830;'
        f'border-left:4px solid {bs_signal_clr};border-radius:10px;'
        f'padding:.85rem 1.25rem;margin-bottom:1rem;">'
        f'<span style="font-size:.88rem;font-weight:700;color:{bs_signal_clr};">'
        f'Current Fed posture: {bs_signal}</span>'
        f'<span style="font-size:.78rem;color:#9aa3b2;margin-left:16px;">'
        f'WoW change: {fmt_B(wow_change) if wow_change is not None else "N/A"} | '
        f'TGA: {fmt_B(tga)} | ON RRP: {fmt_B(rrp)}'
        f'</span></div>',
        unsafe_allow_html=True
    )

    # ── Charts: Total Assets + Components ──────────────────────────────────────
    st.markdown('<p class="sec-label">Balance sheet history — 5 years</p>',
                unsafe_allow_html=True)

    chart_tab1, chart_tab2, chart_tab3 = st.tabs(
        ["📊 Total Assets", "🏛️ Holdings Breakdown", "💧 Liquidity Indicators"]
    )

    with chart_tab1:
        walcl_s = raw.get("bs_total_assets")
        if walcl_s is not None and len(walcl_s) > 0:
            vals = walcl_s.dropna().values
            idx  = walcl_s.dropna().index
            y_pad = (vals.max() - vals.min()) * 0.05

            fig = go.Figure()
            # Filled area
            fig.add_trace(go.Scatter(
                x=idx, y=[vals.min() - y_pad] * len(idx),
                line=dict(width=0), showlegend=False, hoverinfo="skip",
            ))
            fig.add_trace(go.Scatter(
                x=idx, y=vals,
                fill="tonexty",
                fillcolor="rgba(74,143,212,0.10)",
                line=dict(color="#4a8fd4", width=2),
                name="Total Assets (T)",
                hovertemplate="$%{y:.3f}T<extra>Total Assets</extra>",
            ))
            # Peak annotation
            fig.add_hline(
                y=8.965, line_dash="dot", line_color="#e05252", line_width=1.2,
                annotation_text="  Peak $8.97T (Apr 2022)",
                annotation_font_color="#e05252", annotation_font_size=10,
            )
            # Pre-COVID baseline
            fig.add_hline(
                y=4.17, line_dash="dot", line_color="#5c6475", line_width=1,
                annotation_text="  Pre-COVID baseline ~$4.2T",
                annotation_font_color="#5c6475", annotation_font_size=9,
            )
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                height=320, showlegend=False,
                margin=dict(t=20, b=40, l=60, r=30),
                xaxis=dict(showgrid=False, tickfont=dict(color="#5c6475", size=10),
                           linecolor="#242830"),
                yaxis=dict(gridcolor="#1a1e25", tickfont=dict(color="#5c6475", size=10),
                           linecolor="#242830",
                           range=[vals.min() - y_pad, vals.max() + y_pad],
                           tickprefix="$", ticksuffix="T"),
                hovermode="x unified",
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

            # WoW change bar chart (last 52 weeks)
            if len(walcl_s) >= 2:
                wk_changes = walcl_s.diff().dropna().tail(52) * 1000  # trillions → billions
                colors_bar = ["#e05252" if v >= 0 else "#5a9e47" for v in wk_changes.values]
                fig2 = go.Figure(go.Bar(
                    x=wk_changes.index, y=wk_changes.values,
                    marker_color=colors_bar,
                    hovertemplate="%{y:+.1f}B WoW<extra></extra>",
                ))
                fig2.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    height=160, showlegend=False, title="Weekly Change ($B) — last 52 weeks",
                    title_font=dict(size=12, color="#9aa3b2"),
                    margin=dict(t=30, b=30, l=60, r=20),
                    xaxis=dict(showgrid=False, tickfont=dict(color="#5c6475", size=9),
                               linecolor="#242830"),
                    yaxis=dict(gridcolor="#1a1e25", tickfont=dict(color="#5c6475", size=9),
                               linecolor="#242830", ticksuffix="B"),
                    hovermode="x unified",
                )
                st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})
        else:
            st.warning("Total assets data unavailable — check FRED connection.")

    with chart_tab2:
        c1, c2 = st.columns(2)
        for col, key_name, label, color, unit in [
            (c1, "bs_treasuries", "Treasury Securities Held ($T)", "#d4913a", "T"),
            (c2, "bs_mbs",        "MBS Held ($T)",                 "#c76bdb", "T"),
        ]:
            with col:
                s = raw.get(key_name)
                st.markdown(f"**{label}**")
                if s is not None and len(s) > 0:
                    vals = s.dropna().values
                    idx  = s.dropna().index
                    y_pad = (vals.max() - vals.min()) * 0.05
                    fig = go.Figure(go.Scatter(
                        x=idx, y=vals, line=dict(color=color, width=1.8),
                        hovertemplate=f"$%{{y:.3f}}{unit}<extra></extra>",
                    ))
                    fig.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        height=220, showlegend=False,
                        margin=dict(t=5, b=30, l=50, r=15),
                        xaxis=dict(showgrid=False, tickfont=dict(color="#5c6475", size=9),
                                   linecolor="#242830"),
                        yaxis=dict(gridcolor="#1a1e25", tickfont=dict(color="#5c6475", size=9),
                                   linecolor="#242830",
                                   range=[vals.min() - y_pad, vals.max() + y_pad],
                                   tickprefix="$", ticksuffix=unit),
                        hovermode="x unified",
                    )
                    st.plotly_chart(fig, use_container_width=True,
                                    config={"displayModeBar": False})
                else:
                    st.info("Data unavailable")

    with chart_tab3:
        c1, c2, c3 = st.columns(3)
        liquidity_series = [
            (c1, "bs_reserves", "Bank Reserves ($B)",         "#5a9e47", "B"),
            (c2, "bs_tga",      "Treasury Gen. Account ($B)", "#d4913a", "B"),
            (c3, "bs_rrp",      "Overnight RRP ($B)",         "#4a8fd4", "B"),
        ]
        for col, key_name, label, color, unit in liquidity_series:
            with col:
                s = raw.get(key_name)
                st.markdown(f"**{label}**")
                if s is not None and len(s) > 0:
                    vals = s.dropna().values
                    idx  = s.dropna().index
                    y_pad = max((vals.max() - vals.min()) * 0.05, 10)
                    fig = go.Figure(go.Scatter(
                        x=idx, y=vals, line=dict(color=color, width=1.6),
                        hovertemplate=f"$%{{y:,.0f}}{unit}<extra></extra>",
                    ))
                    fig.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        height=210, showlegend=False,
                        margin=dict(t=5, b=25, l=50, r=10),
                        xaxis=dict(showgrid=False, tickfont=dict(color="#5c6475", size=9),
                                   linecolor="#242830"),
                        yaxis=dict(gridcolor="#1a1e25", tickfont=dict(color="#5c6475", size=9),
                                   linecolor="#242830",
                                   range=[max(0, vals.min() - y_pad), vals.max() + y_pad],
                                   tickprefix="$", ticksuffix=unit),
                        hovermode="x unified",
                    )
                    st.plotly_chart(fig, use_container_width=True,
                                    config={"displayModeBar": False})
                    # Latest value badge
                    lv = float(vals[-1])
                    chg = float(vals[-1] - vals[-2]) if len(vals) >= 2 else None
                    chg_str = (f"{'▲' if chg >= 0 else '▼'} {abs(chg):,.0f}B WoW"
                               if chg is not None else "")
                    chg_clr = "#5a9e47" if (chg or 0) <= 0 else "#e05252"
                    if key_name == "bs_reserves":
                        chg_clr = "#5a9e47" if (chg or 0) >= 0 else "#e05252"
                    st.markdown(
                        f'<div style="text-align:center;font-size:.75rem;margin-top:-8px;">'
                        f'<b style="color:#e8eaf0;">${lv:,.0f}B</b> '
                        f'<span style="color:{chg_clr};">{chg_str}</span></div>',
                        unsafe_allow_html=True
                    )
                else:
                    st.info("Data unavailable")

    # ── Component detail cards ──────────────────────────────────────────────────
    st.markdown("---")
    st.markdown('<p class="sec-label">What each component signals for financial repression</p>',
                unsafe_allow_html=True)

    COMPONENTS = [
        {
            "title":  "Total Assets (WALCL)",
            "value":  fmt_T(total_assets),
            "series": "WALCL",
            "color":  "#4a8fd4",
            "sub":    f"Peak: $8.97T (Apr 2022) · QT drawdown: {drawdown:.1f}%" if drawdown else "Weekly Wednesday level",
            "why": (
                "The headline balance sheet number. Expanding = QE/monetary stimulus being injected. "
                "Shrinking = QT (quantitative tightening) draining liquidity. "
                "During financial repression, the Fed typically resumes balance sheet expansion "
                "to suppress long-term yields — watch for the trough and any reversal. "
                "The pre-COVID baseline was $4.2T. Peak QE reached $8.97T in April 2022."
            ),
        },
        {
            "title":  "Treasury Securities Held (TREAST)",
            "value":  fmt_T(treasuries),
            "series": "TREAST",
            "color":  "#d4913a",
            "sub":    "Direct suppression of Treasury yields",
            "why": (
                "When the Fed buys Treasuries, it artificially suppresses yields below what "
                "the free market would demand — the operational definition of financial repression. "
                "A resumption of Treasury purchases after QT ends is the most direct repression signal. "
                "Watch for: QT pause announcement, then renewed Treasury buying. "
                "Each $1T in purchases suppresses 10-yr yields by roughly 15-20 bps (Fed research)."
            ),
        },
        {
            "title":  "Mortgage-Backed Securities (WSHOMCB)",
            "value":  fmt_T(mbs),
            "series": "WSHOMCB",
            "color":  "#c76bdb",
            "sub":    "Housing market yield suppression",
            "why": (
                "MBS holdings suppress mortgage rates below market-clearing levels, "
                "stimulating the housing market and supporting real estate prices. "
                "During repression, MBS buying keeps 30-yr mortgage rates artificially low, "
                "amplifying the real estate wealth effect. The Fed has been allowing MBS to "
                "roll off during QT — any resumption of MBS buying signals deep repression."
            ),
        },
        {
            "title":  "Bank Reserves (WRESBAL)",
            "value":  fmt_B(reserves),
            "series": "WRESBAL",
            "color":  "#5a9e47",
            "sub":    "System liquidity buffer — watch for shortage signals",
            "why": (
                "Bank reserves are the buffer that prevents a repo market seizure (like Sept 2019). "
                "When reserves fall too low (below ~$3T), money market rates spike and the Fed "
                "is forced to inject liquidity. Low reserves = stress approaching. "
                "High reserves = ample liquidity, suppressed short rates. "
                "Current reading vs. the ~$3T 'comfortable minimum' is a key stability signal."
            ),
        },
        {
            "title":  "Treasury General Account — TGA (WTREGEN)",
            "value":  fmt_B(tga),
            "series": "WTREGEN",
            "color":  "#d4913a",
            "sub":    "Treasury's checking account at the Fed",
            "why": (
                "The TGA is the US Treasury's operating account. When the TGA is drawn down "
                "(spent), that money flows into bank reserves, injecting liquidity into the system — "
                "functionally similar to QE. When the TGA is rebuilt (debt ceiling lifted), it "
                "drains reserves, tightening financial conditions. "
                "A TGA rebuild after a debt ceiling resolution can tighten conditions by $500B+."
            ),
        },
        {
            "title":  "Overnight Reverse Repo — ON RRP (RRPONTSYD)",
            "value":  fmt_B(rrp),
            "series": "RRPONTSYD",
            "color":  "#4a8fd4",
            "sub":    "Excess liquidity parked at the Fed",
            "why": (
                "The RRP facility is where money market funds park excess cash overnight. "
                "Peak RRP ($2.55T in Dec 2022) signaled extreme liquidity — too much money "
                "chasing too few safe assets. As RRP drains toward zero, that liquidity "
                "enters the banking system. RRP near zero = liquidity fully deployed, "
                "reserves under pressure. Watch for RRP exhaustion as a liquidity cliff signal."
            ),
        },
    ]

    comp_cols = st.columns(2)
    for i, comp in enumerate(COMPONENTS):
        with comp_cols[i % 2]:
            st.markdown(
                f'<div class="bs-card" style="border-left-color:{comp["color"]};">'
                f'<div style="display:flex;justify-content:space-between;align-items:baseline;'
                f'flex-wrap:wrap;gap:6px;margin-bottom:4px;">'
                f'  <div class="bs-card-title">{comp["title"]}</div>'
                f'  <div class="bs-card-val" style="color:{comp["color"]};">{comp["value"]}</div>'
                f'</div>'
                f'<div class="bs-card-sub">'
                f'  FRED: <code style="color:#5c6475;">{comp["series"]}</code> · {comp["sub"]}'
                f'</div>'
                f'<div class="bs-card-why">{comp["why"]}</div>'
                f'</div>',
                unsafe_allow_html=True
            )

    # ── Historical context timeline ─────────────────────────────────────────────
    st.markdown("---")
    st.markdown('<p class="sec-label">Historical QE/QT cycle context</p>',
                unsafe_allow_html=True)

    HISTORY = [
        ("#5c6475", "Pre-GFC baseline (2007)",
         "Balance sheet ~$900B. Normal monetary operations. No financial repression via balance sheet."),
        ("#d4913a", "QE1 → QE3 (2008–2014)",
         "Balance sheet expanded from $900B to $4.5T. First systematic balance sheet repression. "
         "10-yr yield suppressed from 4%+ to sub-2%. Savers received negative real returns for 6 years."),
        ("#5a9e47", "QT1 (2017–2019)",
         "Balance sheet reduced from $4.5T to $3.8T before a repo market seizure in Sept 2019 "
         "forced the Fed to restart liquidity injections. Revealed the ~$3T reserve floor."),
        ("#e05252", "COVID QE (2020–2022)",
         "Balance sheet doubled from $4.2T to $8.97T in 24 months. "
         "Largest monetary expansion in Fed history. 10-yr yield suppressed to 0.55%."),
        ("#d4913a", "QT2 (2022–present)",
         "Balance sheet shrinking from $8.97T peak. ~$2T+ removed via passive roll-off. "
         "Process expected to pause when reserves approach ~$3T floor."),
        ("#e05252", "QT Pause → QE3? (2026+, scenario)",
         "New Fed chair (May 2026) expected to pause QT and potentially restart Treasury purchases "
         "to suppress yields — the operational activation of financial repression. "
         "Watch WALCL for a trough followed by resumption of balance sheet expansion."),
    ]

    for dot_clr, title, desc in HISTORY:
        st.markdown(
            f'<div class="timeline-entry">'
            f'<div class="tl-dot-bs" style="background:{dot_clr}22;border:1.5px solid {dot_clr};'
            f'color:{dot_clr};">●</div>'
            f'<div>'
            f'<div style="font-size:.88rem;font-weight:600;color:#e8eaf0;margin-bottom:2px;">{title}</div>'
            f'<div style="font-size:.78rem;color:#9aa3b2;line-height:1.5;">{desc}</div>'
            f'</div></div>',
            unsafe_allow_html=True
        )

    # ── Repression signal thresholds ────────────────────────────────────────────
    st.markdown("---")
    st.markdown('<p class="sec-label">Repression signal thresholds — what to watch</p>',
                unsafe_allow_html=True)

    thresholds = [
        ("Total assets begin rising WoW for 3+ consecutive weeks",
         "QE restart — direct balance sheet repression activated",
         "#e05252"),
        ("Treasury holdings stop declining (QT pause)",
         "Precursor to QE — Fed has stopped allowing roll-off; yield suppression about to resume",
         "#d4913a"),
        ("Bank reserves fall below $3.0T",
         "System approaching liquidity floor — Fed will be forced to inject; likely precedes QE restart",
         "#d4913a"),
        ("ON RRP facility reaches zero",
         "All excess liquidity fully deployed — reserves now the only buffer; system fragility increasing",
         "#e05252"),
        ("TGA rebuilt above $800B after debt ceiling resolution",
         "Massive reserve drain incoming — equivalent to passive QT of $500B+; watch for market stress",
         "#d4913a"),
        ("MBS purchases restart after being zero for 12+ months",
         "Deep repression signal — Fed explicitly subsidizing housing and suppressing mortgage rates",
         "#e05252"),
    ]

    for trigger, meaning, clr in thresholds:
        st.markdown(
            f'<div style="background:#13161b;border:1px solid #242830;border-left:3px solid {clr};'
            f'border-radius:8px;padding:.65rem 1rem;margin-bottom:6px;display:flex;gap:12px;">'
            f'<div style="flex:1;">'
            f'  <div style="font-size:.8rem;font-weight:600;color:#e8eaf0;margin-bottom:2px;">'
            f'  {trigger}</div>'
            f'  <div style="font-size:.75rem;color:#9aa3b2;">{meaning}</div>'
            f'</div></div>',
            unsafe_allow_html=True
        )

    st.markdown(
        "<div style='font-size:.72rem;color:#5c6475;margin-top:12px;line-height:1.6;'>"
        "<b>Data sources:</b> All series from FRED (Federal Reserve Bank of St. Louis). "
        "WALCL updated weekly (Wednesday level, released Thursday 4:30 PM ET). "
        "TREAST, WSHOMCB, WRESBAL, WTREGEN, RRPONTSYD all from H.4.1 release. "
        "Balance sheet values in trillions (total assets, holdings) or billions (liquidity). "
        "</div>",
        unsafe_allow_html=True
    )


# ─────────────────────────────────────────────────────────────────────────────
#  WEALTH-BUILDING ASSETS TAB
# ─────────────────────────────────────────────────────────────────────────────

# ── Asset definitions ─────────────────────────────────────────────────────────

ASSETS = [
    # ── BEFORE ────────────────────────────────────────────────────────────────
    {
        "phase": "before",
        "name": "TIPS — Treasury Inflation-Protected Securities",
        "tickers": ["SCHP", "VTIP", "TIP"],
        "primary_ticker": "SCHP",
        "category": "Inflation-Linked Bonds",
        "why": (
            "TIPS are the single best entry point while real yields are still positive (~2%). "
            "Principal adjusts with CPI every 6 months — the government literally cannot suppress "
            "your real return through inflation. Once repression activates and real yields go "
            "negative, this entry window closes. Lock in now."
        ),
        "allocation_before": 25,
        "allocation_during": 15,
        "allocation_after": 5,
        "expert": "Ray Dalio",
        "expert_quote": (
            "'The safest investment you can get right now is an inflation index bond. They offer "
            "a real return above inflation, providing a hedge against currency devaluation.' "
            "— Ray Dalio, Bridgewater Associates (2025)"
        ),
        "signal_enter": "TIPS real yield (DFII10) positive and above 1% — buy",
        "signal_exit":  "TIPS real yield goes deeply negative (< −1%) — reduce to short-duration only",
        "color": "#4a8fd4",
        "phase_color": "#185FA5",
    },
    {
        "phase": "before",
        "name": "Gold & Precious Metals",
        "tickers": ["GLD", "IAU", "GDX"],
        "primary_ticker": "GLD",
        "category": "Hard Money / Store of Value",
        "why": (
            "Gold has no yield to suppress — it is the asset governments cannot repress. "
            "In 2025, gold rose 48% as central banks globally accelerated de-dollarization. "
            "Dalio calls it 'the only asset that's not somebody else's liability.' "
            "Currently in a structural bull market driven by sovereign debt fears. "
            "GDX (gold miners) offers leveraged exposure with dividend income."
        ),
        "allocation_before": 15,
        "allocation_during": 20,
        "allocation_after": 5,
        "expert": "Ray Dalio / Paul Tudor Jones",
        "expert_quote": (
            "'Gold is a currency. It's the second-largest reserve currency. You're seeing "
            "changes in the monetary order. I would have 15% of my portfolio in gold.' "
            "— Ray Dalio, Greenwich Economic Forum (Oct 2025). "
            "Jeffrey Gundlach (DoubleLine): recommends up to 25% gold allocation."
        ),
        "signal_enter": "TIPS real yield < 1.5% AND breakeven inflation rising — gold accelerates",
        "signal_exit":  "Real rates normalize above 2% and fiscal consolidation confirmed",
        "color": "#d4913a",
        "phase_color": "#BA7517",
    },
    {
        "phase": "before",
        "name": "Dividend Growth Equities",
        "tickers": ["VYM", "DGRO", "BRK-B"],
        "primary_ticker": "VYM",
        "category": "Equity — Pricing Power",
        "why": (
            "Companies that raise dividends annually for 10+ years have proven pricing power — "
            "they pass inflation to consumers. When bonds are repressed to 0% real, a 3-5% "
            "dividend yield that grows 7-10% annually dominates. Buffett's Berkshire holds "
            "$370B+ in cash-rich businesses that thrive when others can't borrow cheaply."
        ),
        "allocation_before": 20,
        "allocation_during": 25,
        "allocation_after": 35,
        "expert": "Warren Buffett",
        "expert_quote": (
            "'Put 10% in short-term government bonds and 90% in a very low-cost S&P 500 index fund. "
            "I suggest Vanguard's. When companies sell things people need and can raise prices, "
            "they compound your returns regardless of inflation.' "
            "— Warren Buffett (instructions for estate trust, 2014, Berkshire shareholder letters)"
        ),
        "signal_enter": "Dividend yield of index > 10-yr TIPS real yield — equities dominate bonds",
        "signal_exit":  "Nominal bond yields rise above 5% — shift from dividend to total return",
        "color": "#5a9e47",
        "phase_color": "#3B6D11",
    },
    {
        "phase": "before",
        "name": "Real Estate Investment Trusts (REITs)",
        "tickers": ["VNQ", "O", "VICI"],
        "primary_ticker": "VNQ",
        "category": "Real Assets — Hard Property",
        "why": (
            "Real estate delivers two repression protections at once: rents reset with CPI, "
            "and fixed-rate mortgages erode in real terms. REITs legally distribute 90%+ of "
            "income as dividends. Industrial, self-storage, and apartment REITs are most "
            "inflation-sensitive. Hold in tax-advantaged accounts to avoid ordinary income tax."
        ),
        "allocation_before": 15,
        "allocation_during": 20,
        "allocation_after": 10,
        "expert": "Peter Lynch / John Templeton",
        "expert_quote": (
            "'Real estate has made more ordinary people wealthy than any other asset. "
            "Owning property during inflation is like holding a bond that reprices itself upward.' "
            "— Peter Lynch, Fidelity (Beating the Street). "
            "Lynch 29.2% avg annual return at Magellan Fund 1977-1990."
        ),
        "signal_enter": "CPI > 3% and Fed funds below CPI — real estate outperforms bonds decisively",
        "signal_exit":  "Real rates rise above 2% — cap rates must reset, trim REIT allocation",
        "color": "#c76bdb",
        "phase_color": "#7C3D9E",
    },

    # ── DURING ────────────────────────────────────────────────────────────────
    {
        "phase": "during",
        "name": "Energy & Natural Resources Equities",
        "tickers": ["XLE", "XOM", "PDBC"],
        "primary_ticker": "XLE",
        "category": "Commodities — Hard Assets",
        "why": (
            "Oil, gas, copper, and agriculture are the inputs to everything governments try to "
            "inflate away. Energy companies generate cash flows that scale directly with the "
            "prices being inflated. XME (metals & mining) gained 13% in 2022 while S&P fell 18%. "
            "During active repression, commodity producers are the best equity sector — "
            "they own the real thing governments can't print."
        ),
        "allocation_before": 10,
        "allocation_during": 15,
        "allocation_after": 0,
        "expert": "Stanley Druckenmiller",
        "expert_quote": (
            "'Never fight the Fed AND inflation at the same time — own what's real. "
            "Commodities and energy are the only assets that go up when everything else is being "
            "debased.' — Stanley Druckenmiller, Duquesne Capital. "
            "30%+ avg annual returns 1986-2010, never had a losing year."
        ),
        "signal_enter": "Fed cuts rates while CPI > 3% — commodity bull market confirmed",
        "signal_exit":  "CPI falls below 3% for 2+ consecutive months — reduce to zero",
        "color": "#d4913a",
        "phase_color": "#BA7517",
    },
    {
        "phase": "during",
        "name": "International Equity (Non-Repressed Economies)",
        "tickers": ["VEA", "EWG", "DODFX"],
        "primary_ticker": "VEA",
        "category": "International Diversification",
        "why": (
            "US financial repression weakens the dollar — which is a tailwind for foreign assets. "
            "European and EM stocks priced in stronger currencies deliver real USD gains even at "
            "flat local returns. German and Swiss equities often have positive real rates. "
            "European bank stocks currently offer ~7% real yield via dividends + buybacks "
            "(Algebris Investments, 2025). EM local currency bonds yield 5-10% real."
        ),
        "allocation_before": 10,
        "allocation_during": 15,
        "allocation_after": 15,
        "expert": "John Templeton",
        "expert_quote": (
            "'The four most dangerous words in investing are: this time it's different. "
            "Bull markets are born on pessimism, grown on skepticism. When the US debases, "
            "buy where they are not debasing — international diversification is not optional, "
            "it is essential.' — Sir John Templeton, founder of Templeton Growth Fund. "
            "15.8% avg annual return 1954-1992."
        ),
        "signal_enter": "USD index (DXY) breaks below 100 — dollar weakness confirms international thesis",
        "signal_exit":  "USD rallies above 105 AND US real rates normalize — rebalance back to domestic",
        "color": "#0F6E56",
        "phase_color": "#0F6E56",
    },
    {
        "phase": "during",
        "name": "Short-Duration Floating Rate / I-Bonds",
        "tickers": ["FLOT", "USFR", "Series I Bonds"],
        "primary_ticker": "FLOT",
        "category": "Cash Equivalent — Inflation-Indexed",
        "why": (
            "I Bonds (TreasuryDirect) adjust to CPI every 6 months with zero price volatility — "
            "you cannot lose principal, and the rate tracks actual inflation. Limited to $10K/yr. "
            "FLOT and USFR are floating-rate ETFs that reset with SOFR — they keep pace with "
            "a rising rate environment without duration risk. Best for the defensive cash portion "
            "of a portfolio during active repression."
        ),
        "allocation_before": 5,
        "allocation_during": 5,
        "allocation_after": 0,
        "expert": "Bill Gross",
        "expert_quote": (
            "'Duration is your enemy in a repressed rate environment heading toward normalization. "
            "Own the short end, own floaters — the long end will hurt you when the regime ends.' "
            "— Bill Gross, PIMCO. Built PIMCO into the world's largest bond fund. "
            "Managed Total Return Fund to 8.4% avg annual return over 27 years."
        ),
        "signal_enter": "Real policy rate negative AND CPI > 4% — floaters beat all fixed-rate instruments",
        "signal_exit":  "Fed begins hiking cycle in earnest — exit floaters, enter long nominal bonds",
        "color": "#4a8fd4",
        "phase_color": "#185FA5",
    },
    {
        "phase": "during",
        "name": "Bitcoin / Digital Scarcity Assets",
        "tickers": ["IBIT", "FBTC", "GBTC"],
        "primary_ticker": "IBIT",
        "category": "Alternative — Scarce Asset",
        "why": (
            "Fixed 21M supply cap means Bitcoin cannot be inflated away by central bank policy. "
            "Increasingly held by institutions as a 'digital gold' reserve. Dalio recommends "
            "a 'combination of gold and some bitcoin' as a fiat debasement hedge (2025). "
            "High volatility makes it speculative — appropriate at 2-5% of portfolio only. "
            "Spot Bitcoin ETFs (IBIT, FBTC) make access tax-efficient inside IRAs."
        ),
        "allocation_before": 3,
        "allocation_during": 5,
        "allocation_after": 3,
        "expert": "Paul Tudor Jones",
        "expert_quote": (
            "'Bitcoin reminds me of gold in the early 1970s. Every major central bank in the "
            "world is printing money... Bitcoin has everything to recommend it as a store of "
            "value at a time when fiat currencies are being debased.' "
            "— Paul Tudor Jones, Tudor Investment Corp. ~19% avg annual return since 1980."
        ),
        "signal_enter": "M2 money supply growth > 8% YoY AND real rates negative — debasement thesis active",
        "signal_exit":  "Regulatory crackdown OR real rates normalize above 2% — reduce to minimum",
        "color": "#e05252",
        "phase_color": "#A32D2D",
    },

    # ── AFTER ─────────────────────────────────────────────────────────────────
    {
        "phase": "after",
        "name": "Long-Duration Nominal Treasuries",
        "tickers": ["TLT", "VGLT", "EDV"],
        "primary_ticker": "TLT",
        "category": "Bonds — Lock-In High Nominal Yield",
        "why": (
            "When repression ends, nominal yields typically spike to a cycle peak before "
            "falling. Buying TLT at the yield peak locks in 5-6% coupons for 20-30 years. "
            "As rates fall from the cycle high, bond prices surge — the mirror image of the "
            "repression regime. This is the 1981 moment: buying 30-yr Treasuries at 15% "
            "generated extraordinary real returns through the next decade."
        ),
        "allocation_before": 0,
        "allocation_during": 0,
        "allocation_after": 25,
        "expert": "Bill Gross / Jeffrey Gundlach",
        "expert_quote": (
            "'The 30-year Treasury at a cycle peak yield is the greatest risk-adjusted "
            "opportunity in fixed income. Duration is your friend when the repression ends "
            "and rates begin to normalize downward from elevated levels.' "
            "— Jeffrey Gundlach, DoubleLine Capital. "
            "Known as 'Bond King' — DoubleLine Total Return +7.4% avg annual since 2009."
        ),
        "signal_enter": "10-yr yield near cycle high (> 5%) AND CPI falling for 6+ months — buy duration",
        "signal_exit":  "10-yr yield falls below 3% — fully harvested, rotate to equity",
        "color": "#4a8fd4",
        "phase_color": "#185FA5",
    },
    {
        "phase": "after",
        "name": "Growth & Technology Equities",
        "tickers": ["QQQ", "VGT", "MSFT"],
        "primary_ticker": "QQQ",
        "category": "Equity — Long Duration Growth",
        "why": (
            "High-growth technology equities are long-duration assets — their value depends on "
            "discounting future earnings at real rates. They suffer severely during repression "
            "(rising discount rates) but recover powerfully when real rates normalize and "
            "economic growth resumes. The post-repression growth boom is when growth stocks shine. "
            "Buffett's Berkshire entered Apple at scale in 2016 — an example of patient "
            "accumulation during distress and riding the normalization recovery."
        ),
        "allocation_before": 5,
        "allocation_during": 5,
        "allocation_after": 25,
        "expert": "Warren Buffett / Charlie Munger",
        "expert_quote": (
            "'It's far better to buy a wonderful company at a fair price than a fair company "
            "at a wonderful price. The best businesses compound at high rates — they are worth "
            "almost any price if the duration of the compounding is long enough.' "
            "— Charlie Munger, Berkshire Hathaway Vice Chairman. "
            "Berkshire Hathaway: 19.8% avg annual return 1965-2024 vs 10.2% for S&P 500."
        ),
        "signal_enter": "Real rates above 1.5% AND inflation below 3% for 6 months — growth rotation",
        "signal_exit":  "P/E > 35x on trailing earnings with inflation re-accelerating — reduce",
        "color": "#5a9e47",
        "phase_color": "#3B6D11",
    },
    {
        "phase": "after",
        "name": "Broad International Equity (Rebalanced)",
        "tickers": ["VT", "VXUS", "EFA"],
        "primary_ticker": "VT",
        "category": "Global Equity Diversification",
        "why": (
            "Post-repression, international equity remains attractive as dollar repatriation "
            "unwinds gradually. Dalio's All-Weather portfolio permanently holds international "
            "assets: 30% stocks (diversified globally). The Harvard endowment model allocates "
            "~40% to international equity and alternatives. Reducing home-country bias after "
            "a US repression cycle is a structural rebalancing, not a tactical trade."
        ),
        "allocation_before": 10,
        "allocation_during": 10,
        "allocation_after": 15,
        "expert": "Ray Dalio — All Weather",
        "expert_quote": (
            "'15 good uncorrelated return streams will lower risk by 80% while maintaining "
            "returns. No single country, no single asset. This is the Holy Grail of investing — "
            "true diversification across geographies and asset classes.' "
            "— Ray Dalio, Bridgewater Associates. "
            "All Weather Portfolio: ~9.7% avg annual return 1996-2023."
        ),
        "signal_enter": "Post-repression normalization confirmed — rebalance to permanent global allocation",
        "signal_exit":  "No exit — permanent strategic allocation for all-weather diversification",
        "color": "#0F6E56",
        "phase_color": "#0F6E56",
    },
]

PHASE_META = {
    "before": {
        "label":    "Phase 1 — Before Repression",
        "subtitle": "Now through mid-2026 estimated · Real TIPS yield ~2% · Set up while window is open",
        "color":    "#185FA5",
        "bg":       "#0d1a2e",
        "icon":     "🔵",
        "desc": (
            "Structural conditions are fully met but real rates remain positive. "
            "This is the last window to lock in positive real yields and accumulate hard assets "
            "before the operational trigger (Fed chair succession, May 2026) activates the regime. "
            "Priority: TIPS, gold, dividend equities, REITs. Eliminate long nominal bonds entirely."
        ),
    },
    "during": {
        "label":    "Phase 2 — During Active Repression",
        "subtitle": "2026–2029 estimated · Real rates negative · Savers taxed invisibly",
        "color":    "#A32D2D",
        "bg":       "#2a1818",
        "icon":     "🔴",
        "desc": (
            "Fed cuts rates despite inflation. TIPS real yields approach zero or negative. "
            "Nominal bonds are wealth destruction. Real assets and inflation-sensitive equity dominate. "
            "This is the core repression regime — the stealth tax on savers is fully active. "
            "Overweight: energy, commodities, international, gold, floating rate. "
            "Eliminate: long nominal Treasuries, cash savings, aggregate bond funds."
        ),
    },
    "after": {
        "label":    "Phase 3 — After Repression Ends",
        "subtitle": "2029+ estimated · Real rates normalize · Growth resumes",
        "color":    "#3B6D11",
        "bg":       "#152010",
        "icon":     "🟢",
        "desc": (
            "Repression ends when inflation forces a Volcker-style response OR fiscal consolidation "
            "reduces debt needs. Real rates normalize. Nominal bonds become extremely attractive at "
            "cycle-peak yields. Growth equities recover as discount rates fall. "
            "Rotate back toward traditional diversification. This phase may be 5–15 years away."
        ),
    },
}

INVESTOR_PROFILES = [
    {
        "name": "Ray Dalio",
        "firm": "Bridgewater Associates",
        "track": "~15% avg annual return 1975–2020 · World's largest hedge fund at $150B+ AUM",
        "repression_view": (
            "Compares 2025-2026 to the early 1970s. Recommends 15% gold, TIPS, and "
            "real assets as the core repression hedge. All-Weather Portfolio: 30% stocks, "
            "40% long bonds, 15% intermediate bonds, 7.5% gold, 7.5% commodities. "
            "In repression: overweight real assets vs. nominal bonds."
        ),
        "key_assets": ["GLD / IAU (15%)", "SCHP / TIPS (20%)", "VT global equity (30%)", "Commodities PDBC (7.5%)"],
        "color": "#d4913a",
    },
    {
        "name": "Warren Buffett",
        "firm": "Berkshire Hathaway",
        "track": "19.8% avg annual return 1965–2024 · Beat S&P 500 by ~2x over 60 years",
        "repression_view": (
            "Focuses on businesses with durable pricing power — companies that raise prices "
            "with inflation and compound free cash flow. Avoids gold ('unproductive asset'). "
            "Estate trust instruction: 90% S&P 500 index, 10% short-term Treasuries. "
            "Berkshire holds $370B+ cash — ready to buy distressed assets at cycle lows."
        ),
        "key_assets": ["BRK-B (conglomerate)", "S&P 500 index (90%)", "Short T-bills (10%)", "Consumer staples, energy, banks"],
        "color": "#5a9e47",
    },
    {
        "name": "Stanley Druckenmiller",
        "firm": "Duquesne Capital",
        "track": "30%+ avg annual return 1986–2010 · Never had a losing year",
        "repression_view": (
            "Macro-focused — tracks money supply, real rates, and central bank policy. "
            "In repression: heavily long gold, commodities, and hard assets. "
            "Short long-duration nominal bonds. Uses macro signals (TIPS yield, DXY) to "
            "time rotations. Does not hold losers — concentrated in highest-conviction positions."
        ),
        "key_assets": ["GLD (large position)", "Energy equities XLE", "Commodities", "Short TLT during repression"],
        "color": "#e05252",
    },
    {
        "name": "Paul Tudor Jones",
        "firm": "Tudor Investment Corp",
        "track": "~19% avg annual return since 1980 · Never had a losing year in 45 years",
        "repression_view": (
            "Called Bitcoin 'like gold in the early 1970s.' Advocates 'never fighting the Fed AND "
            "inflation simultaneously.' Holds gold and Bitcoin as joint monetary debasement hedges. "
            "Watches M2 money supply growth as primary repression signal — when M2 grows >8% "
            "with negative real rates, commodity and hard asset positions are maximum size."
        ),
        "key_assets": ["Gold (large position)", "Bitcoin 1-5%", "Commodity equities", "Inflation-linked bonds"],
        "color": "#c76bdb",
    },
    {
        "name": "Jeffrey Gundlach",
        "firm": "DoubleLine Capital",
        "track": "DoubleLine Total Return +7.4% avg annual since 2009 · 'New Bond King'",
        "repression_view": (
            "Recommends up to 25% gold during current environment (2025). "
            "Warns long-duration nominal bonds are 'return-free risk' when real rates are "
            "negative. Focus on short-duration floating rate during repression, then rotate "
            "to long Treasuries at the cycle peak yield. EM local-currency bonds offer "
            "5-10% real yields when dollar weakens — strong post-repression play."
        ),
        "key_assets": ["Gold up to 25%", "Short-duration TIPS/floaters", "EM local bonds (post-repression)", "Long TLT at yield peak"],
        "color": "#4a8fd4",
    },
    {
        "name": "Peter Lynch",
        "firm": "Fidelity Magellan Fund",
        "track": "29.2% avg annual return 1977–1990 · Best mutual fund performance ever recorded",
        "repression_view": (
            "Focused on 'invest in what you know' — real, tangible businesses with clear "
            "pricing power. Real estate, consumer staples with brand moats, and dividend "
            "growers are Lynch's inflation plays. 'Owning property during inflation is like "
            "holding a bond that reprices itself upward.' Avoided macroeconomic timing — "
            "instead focused on business fundamentals with strong cash flow."
        ),
        "key_assets": ["REITs VNQ", "Consumer staples (KO, PG, WMT)", "Dividend growers VYM", "Real estate direct ownership"],
        "color": "#0F6E56",
    },
]


def wealth_assets_tab(raw: dict):
    """Render the Wealth-Building Assets tab."""

    # ── CSS additions for this tab ─────────────────────────────────────────────
    st.markdown("""
    <style>
      .phase-header {
        border-radius: 10px; padding: 1rem 1.25rem; margin-bottom: 1.25rem;
        border-left: 4px solid;
      }
      .phase-title { font-size: 1rem; font-weight: 700; margin: 0 0 3px; }
      .phase-sub   { font-size: .78rem; margin: 0 0 8px; opacity: .75; }
      .phase-desc  { font-size: .82rem; line-height: 1.6; margin: 0; }

      .asset-card {
        background: #13161b; border: 1px solid #242830; border-radius: 10px;
        padding: 1rem 1.1rem; margin-bottom: 10px;
        border-left: 3px solid;
      }
      .asset-name   { font-size: .95rem; font-weight: 600; color: #e8eaf0; margin-bottom: 2px; }
      .asset-cat    { font-size: .7rem; font-family: monospace; letter-spacing: .06em;
                      text-transform: uppercase; color: #5c6475; margin-bottom: 10px; }
      .asset-why    { font-size: .8rem; color: #9aa3b2; line-height: 1.55; margin-bottom: 10px; }
      .asset-quote  { font-size: .78rem; color: #7a8299; line-height: 1.5;
                      border-left: 2px solid #2e343f; padding-left: 10px;
                      margin-bottom: 10px; font-style: italic; }
      .signal-row   { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 6px; }
      .signal-chip  { font-size: .7rem; padding: 3px 9px; border-radius: 5px;
                      font-family: monospace; }
      .sig-enter    { background: #152010; color: #5a9e47; border: 1px solid #1c2e14; }
      .sig-exit     { background: #2a1818; color: #e05252; border: 1px solid #3d1f1f; }

      .alloc-pill {
        display: inline-block; font-size: .75rem; font-weight: 600;
        padding: 4px 12px; border-radius: 20px; font-family: monospace;
        margin: 2px;
      }
      .pill-before { background: #0d1a2e; color: #4a8fd4; border: 1px solid #1a2e4a; }
      .pill-during { background: #2a1818; color: #e05252; border: 1px solid #3d1f1f; }
      .pill-after  { background: #152010; color: #5a9e47; border: 1px solid #1c2e14; }

      .investor-card {
        background: #13161b; border: 1px solid #242830; border-radius: 10px;
        padding: 1rem; margin-bottom: 10px;
      }
      .inv-name  { font-size: .95rem; font-weight: 700; color: #e8eaf0; margin-bottom: 1px; }
      .inv-firm  { font-size: .72rem; font-family: monospace; color: #5c6475; margin-bottom: 6px; }
      .inv-track { font-size: .75rem; font-weight: 600; margin-bottom: 8px; }
      .inv-view  { font-size: .8rem; color: #9aa3b2; line-height: 1.55; margin-bottom: 8px; }
      .inv-assets { font-size: .75rem; color: #5c6475; }
    </style>
    """, unsafe_allow_html=True)

    # ── Header ─────────────────────────────────────────────────────────────────
    st.markdown('<p class="sec-label">Wealth-building assets · Financial repression playbook</p>',
                unsafe_allow_html=True)
    st.markdown(
        "<span style='color:#9aa3b2;font-size:.85rem;'>"
        "Live prices tracked via Yahoo Finance · Guidance from the greatest investors "
        "of the last 50 years · Organized by repression phase"
        "</span>", unsafe_allow_html=True
    )

    # ── Data status ────────────────────────────────────────────────────────────
    WEALTH_TICKERS = ["SCHP","GLD","VYM","VNQ","XLE","VEA","FLOT","IBIT","TLT","QQQ","VT"]
    loaded  = [t for t in WEALTH_TICKERS if len(raw.get(f"wealth_{t}_series", pd.Series(dtype=float))) > 0]
    missing = [t for t in WEALTH_TICKERS if t not in loaded]

    if missing:
        with st.expander(f"⚠️ {len(missing)} ticker(s) not loaded: {', '.join(missing)} — click to see details"):
            st.markdown(
                f"**Loaded ({len(loaded)}):** {', '.join(loaded) if loaded else 'none'}\n\n"
                f"**Missing ({len(missing)}):** {', '.join(missing)}\n\n"
                "Missing tickers show 'Price unavailable' charts. "
                "Click **🔄 Refresh data** in the sidebar to retry, or check the 🔬 Diagnostics page."
            )
            for t in missing:
                s = raw.get(f"wealth_{t}_series", pd.Series(dtype=float))
                st.write(f"  `{t}`: Series length = {len(s)}")
    else:
        st.success(f"✅ All {len(WEALTH_TICKERS)} asset tickers loaded successfully", icon=None)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Current phase indicator ────────────────────────────────────────────────
    tips_yield = raw.get("tips_real_yield")
    real_rate  = raw.get("real_policy_rate")
    if tips_yield is not None and tips_yield <= 0 and real_rate is not None and real_rate <= 0:
        current_phase = "during"
    elif tips_yield is not None and tips_yield <= 1.0:
        current_phase = "transitioning"
    else:
        current_phase = "before"

    phase_msg = {
        "before":       ("🔵 PHASE 1 — BEFORE REPRESSION ACTIVE",
                         "Real TIPS yield still positive. Setup window is open — this is the time to position.",
                         "#185FA5"),
        "transitioning":("🟡 TRANSITIONING — REPRESSION APPROACHING",
                         "TIPS yield falling toward zero. New Fed chair incoming. Accelerate positioning now.",
                         "#854F0B"),
        "during":       ("🔴 PHASE 2 — ACTIVE REPRESSION",
                         "Real rates negative. Savers are being taxed. Hard assets and real equity are the play.",
                         "#A32D2D"),
    }
    msg, sub, clr = phase_msg[current_phase]
    st.markdown(
        f'<div style="background:#13161b;border:1px solid #242830;border-left:4px solid {clr};'
        f'border-radius:10px;padding:.85rem 1.1rem;margin-bottom:1.5rem;">'
        f'<div style="font-size:.88rem;font-weight:700;color:{clr};">{msg}</div>'
        f'<div style="font-size:.78rem;color:#9aa3b2;margin-top:3px;">{sub}</div>'
        f'</div>',
        unsafe_allow_html=True
    )

    # ── Phase tabs ─────────────────────────────────────────────────────────────
    ptab1, ptab2, ptab3, ptab4 = st.tabs([
        "🔵 Before Repression",
        "🔴 During Repression",
        "🟢 After Repression",
        "🧠 Investor Playbooks",
    ])

    for phase_key, ptab in [("before", ptab1), ("during", ptab2), ("after", ptab3)]:
        with ptab:
            meta = PHASE_META[phase_key]
            phase_assets = [a for a in ASSETS if a["phase"] == phase_key]

            # Phase header
            st.markdown(
                f'<div class="phase-header" style="background:{meta["bg"]}20;'
                f'border-color:{meta["color"]};color:{meta["color"]};">'
                f'<div class="phase-title">{meta["icon"]} {meta["label"]}</div>'
                f'<div class="phase-sub">{meta["subtitle"]}</div>'
                f'<div class="phase-desc" style="color:#9aa3b2;">{meta["desc"]}</div>'
                f'</div>',
                unsafe_allow_html=True
            )

            # Allocation summary bar
            alloc_key = f"allocation_{phase_key}"
            total_alloc = sum(a[alloc_key] for a in phase_assets)
            st.markdown(
                f'<div style="font-size:.75rem;color:#5c6475;margin-bottom:8px;">'
                f'Target allocation this phase: <b style="color:#e8eaf0;">{total_alloc}%</b> '
                f'(remaining {100-total_alloc}% in cash/equivalents or complementary assets)'
                f'</div>',
                unsafe_allow_html=True
            )

            # Assets
            for asset in phase_assets:
                alloc = asset[alloc_key]
                clr   = asset["color"]

                # Fetch live price for primary ticker
                ticker_prices = []
                for t in asset["tickers"][:2]:
                    safe_t = t.replace("-", "").replace(" ", "").replace(".", "-")
                    try:
                        price_series = raw.get(f"_wealth_{safe_t}")
                        if price_series is None:
                            pass  # fetched lazily below
                    except Exception:
                        pass

                st.markdown(
                    f'<div class="asset-card" style="border-left-color:{clr};">'
                    f'<div style="display:flex;justify-content:space-between;align-items:flex-start;'
                    f'flex-wrap:wrap;gap:6px;margin-bottom:6px;">'
                    f'  <div>'
                    f'    <div class="asset-name">{asset["name"]}</div>'
                    f'    <div class="asset-cat">{asset["category"]}</div>'
                    f'  </div>'
                    f'  <div style="text-align:right;">'
                    f'    <span class="alloc-pill pill-before">Before: {asset["allocation_before"]}%</span>'
                    f'    <span class="alloc-pill pill-during">During: {asset["allocation_during"]}%</span>'
                    f'    <span class="alloc-pill pill-after">After: {asset["allocation_after"]}%</span>'
                    f'  </div>'
                    f'</div>'

                    # Tickers row
                    f'<div style="margin-bottom:8px;">'
                    + "".join(
                        f'<span class="alloc-pill" style="background:#1a1e25;color:#9aa3b2;'
                        f'border:1px solid #2e343f;">{t}</span>'
                        for t in asset["tickers"]
                    )
                    + f'</div>'

                    # Why it works
                    f'<div class="asset-why">{asset["why"]}</div>'

                    # Expert quote
                    f'<div class="asset-quote">{asset["expert_quote"]}</div>'

                    # Entry / exit signals
                    f'<div class="signal-row">'
                    f'  <span class="signal-chip sig-enter">▶ ENTER: {asset["signal_enter"]}</span>'
                    f'</div>'
                    f'<div class="signal-row">'
                    f'  <span class="signal-chip sig-exit">◀ EXIT: {asset["signal_exit"]}</span>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

            # Live price chart for phase
            st.markdown("---")
            st.markdown(f"**Live price charts — {meta['label']}**")
            chart_tickers = [(a["primary_ticker"], a["name"].split(" —")[0], a["color"])
                             for a in phase_assets]
            ccols = st.columns(min(3, len(chart_tickers)))
            for idx, (ticker, name, color) in enumerate(chart_tickers):
                with ccols[idx % 3]:
                    # Read from pre-fetched raw dict — no spinner needed
                    series = raw.get(f"wealth_{ticker}_series", pd.Series(dtype=float))

                    st.markdown(f"**{ticker}** — {name[:30]}")
                    if series is not None and len(series) > 10:
                        vals = series.dropna().values
                        y_pad = (vals.max() - vals.min()) * 0.06
                        fig = go.Figure(go.Scatter(
                            x=series.dropna().index,
                            y=vals,
                            line=dict(color=color, width=1.5),
                            fill="tonexty" if False else None,
                            hovertemplate="%{y:.2f}<extra></extra>",
                        ))
                        fig.update_layout(
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(0,0,0,0)",
                            margin=dict(t=5, b=25, l=35, r=10),
                            height=160,
                            showlegend=False,
                            xaxis=dict(showgrid=False,
                                       tickfont=dict(color="#5c6475", size=9),
                                       linecolor="#242830"),
                            yaxis=dict(gridcolor="#1a1e25",
                                       tickfont=dict(color="#5c6475", size=9),
                                       linecolor="#242830",
                                       range=[vals.min() - y_pad, vals.max() + y_pad]),
                            hovermode="x unified",
                        )
                        # Latest price annotation
                        latest_price = float(vals[-1])
                        chg_1m = (
                            (latest_price / float(vals[-22]) - 1) * 100
                            if len(vals) >= 22 else None
                        )
                        chg_str = (
                            f"{'▲' if chg_1m >= 0 else '▼'} {abs(chg_1m):.1f}% (1mo)"
                            if chg_1m is not None else ""
                        )
                        chg_clr = "#5a9e47" if (chg_1m or 0) >= 0 else "#e05252"
                        st.plotly_chart(fig, use_container_width=True,
                                        config={"displayModeBar": False})
                        st.markdown(
                            f'<div style="font-size:.75rem;text-align:center;margin-top:-10px;">'
                            f'<b style="color:#e8eaf0;">${latest_price:.2f}</b> '
                            f'<span style="color:{chg_clr};">{chg_str}</span>'
                            f'</div>',
                            unsafe_allow_html=True
                        )
                    else:
                        st.markdown(
                            '<div style="height:160px;display:flex;align-items:center;'
                            'justify-content:center;background:#13161b;border-radius:8px;'
                            'border:1px solid #242830;font-size:.75rem;color:#5c6475;">'
                            'Price unavailable</div>',
                            unsafe_allow_html=True
                        )

    # ── TAB 4: INVESTOR PLAYBOOKS ──────────────────────────────────────────────
    with ptab4:
        st.markdown('<p class="sec-label">Master investor playbooks — 50 years of proven returns</p>',
                    unsafe_allow_html=True)
        st.markdown(
            "<span style='color:#9aa3b2;font-size:.82rem;'>"
            "How the greatest capital allocators of the last half-century approach "
            "financial repression and inflation cycles."
            "</span><br><br>",
            unsafe_allow_html=True
        )

        for inv in INVESTOR_PROFILES:
            st.markdown(
                f'<div class="investor-card" style="border-left:3px solid {inv["color"]};">'
                f'<div class="inv-name">{inv["name"]}</div>'
                f'<div class="inv-firm">{inv["firm"]}</div>'
                f'<div class="inv-track" style="color:{inv["color"]};">📈 {inv["track"]}</div>'
                f'<div class="inv-view">{inv["repression_view"]}</div>'
                f'<div class="inv-assets"><b style="color:#5c6475;">Key repression assets: </b>'
                + " · ".join(
                    f'<span style="color:#9aa3b2;">{a}</span>'
                    for a in inv["key_assets"]
                )
                + f'</div></div>',
                unsafe_allow_html=True
            )

        # Consensus table
        st.markdown("---")
        st.markdown("**Consensus allocation — composite of all 6 investor frameworks**")
        consensus = [
            ("Gold / Precious Metals",       "GLD, IAU, GDX",       "10–20%",  "5%",    "#d4913a"),
            ("TIPS / Inflation Bonds",        "SCHP, VTIP, TIP",     "15–25%",  "5%",    "#4a8fd4"),
            ("Real Estate / REITs",           "VNQ, O, VICI",        "10–20%",  "10%",   "#c76bdb"),
            ("Dividend / Value Equity",       "VYM, BRK-B, DGRO",    "15–25%",  "35–40%","#5a9e47"),
            ("Energy / Commodities",          "XLE, PDBC, XOM",      "10–15%",  "0%",    "#d4913a"),
            ("International Equity",          "VEA, VT, DODFX",      "10–15%",  "15–20%","#0F6E56"),
            ("Floaters / I-Bonds / Cash",     "FLOT, USFR, I-Bonds", "5–10%",   "0%",    "#9aa3b2"),
            ("Long Nominal Treasuries",       "TLT, VGLT, EDV",      "0%",      "20–25%","#4a8fd4"),
            ("Growth / Tech Equity",          "QQQ, VGT, MSFT",      "0–5%",    "20–25%","#5a9e47"),
            ("Bitcoin (speculative)",         "IBIT, FBTC",          "2–5%",    "0–3%",  "#e05252"),
        ]
        header_html = (
            '<div style="display:grid;grid-template-columns:2fr 1.5fr 1fr 1fr 1fr;'
            'gap:8px;padding:.5rem .75rem;background:#1a1e25;border-radius:8px 8px 0 0;'
            'font-size:.72rem;font-family:monospace;color:#5c6475;text-transform:uppercase;'
            'letter-spacing:.06em;margin-bottom:2px;">'
            '<span>Asset class</span><span>Tickers</span>'
            '<span>Before</span><span>During</span><span>After</span></div>'
        )
        st.markdown(header_html, unsafe_allow_html=True)
        for asset_name, tickers, before, after, clr in consensus:
            during = before  # during = highest allocation period
            st.markdown(
                f'<div style="display:grid;grid-template-columns:2fr 1.5fr 1fr 1fr 1fr;'
                f'gap:8px;padding:.55rem .75rem;background:#13161b;border:1px solid #1a1e25;'
                f'border-left:3px solid {clr};font-size:.78rem;margin-bottom:2px;">'
                f'<span style="color:#e8eaf0;font-weight:500;">{asset_name}</span>'
                f'<span style="color:#5c6475;font-family:monospace;">{tickers}</span>'
                f'<span style="color:#4a8fd4;">{before}</span>'
                f'<span style="color:#e05252;">{during}</span>'
                f'<span style="color:#5a9e47;">{after}</span>'
                f'</div>',
                unsafe_allow_html=True
            )

        st.markdown(
            "<div style='font-size:.7rem;color:#5c6475;margin-top:8px;line-height:1.5;'>"
            "Composite of Dalio All-Weather, Buffett estate trust, Druckenmiller macro framework, "
            "Tudor Jones hard money thesis, Gundlach fixed income rotation, and Lynch real asset principles. "
            "Not investment advice — allocations vary materially by age, timeline, and risk tolerance."
            "</div>",
            unsafe_allow_html=True
        )


# ─────────────────────────────────────────────────────────────────────────────
#  DIAGNOSE PAGE
# ─────────────────────────────────────────────────────────────────────────────

def diagnose_page():
    """
    Hidden debug page — shows exactly what yfinance returns on this server.
    Accessible via the sidebar selector.
    """
    import inspect
    import sys

    st.markdown("## 🔬 Data Fetch Diagnostics")
    st.markdown(
        "This page tests every known yfinance fetch method and shows raw output. "
        "Use it to identify which method works on this server."
    )

    # ── Environment info ───────────────────────────────────────────────────────
    st.markdown("### Environment")
    try:
        import yfinance as yf
        yf_ver = yf.__version__
    except ImportError:
        yf_ver = "NOT INSTALLED"

    col1, col2, col3 = st.columns(3)
    col1.metric("Python", sys.version.split()[0])
    col2.metric("yfinance", yf_ver)
    col3.metric("pandas", pd.__version__)

    st.markdown("---")

    # ── Pick ticker to test ────────────────────────────────────────────────────
    ticker = st.selectbox("Ticker to test", ["KRE", "^TNX", "SPY"], index=0)
    period = st.selectbox("Period", ["5d", "1mo", "3mo", "1y", "5y"], index=0)

    st.info("💡 **Tip:** Test with `5y` period too — the chart uses 5 years of history and the column structure sometimes differs from short periods.")

    if st.button("▶ Run all fetch methods", type="primary"):

        results = {}

        # ── Method A: download(multi_level_index=False) ────────────────────────
        with st.expander("Method A — yf.download(multi_level_index=False)", expanded=True):
            try:
                params = list(inspect.signature(yf.download).parameters.keys())
                if "multi_level_index" not in params:
                    st.warning("multi_level_index param not available in this yfinance version — skipping")
                    results["A"] = None
                else:
                    df = yf.download(ticker, period=period, auto_adjust=True,
                                     progress=False, multi_level_index=False)
                    st.write(f"**Shape:** {df.shape}")
                    st.write(f"**Columns:** `{df.columns.tolist()}`")
                    st.write(f"**dtypes:**")
                    st.dataframe(df.dtypes.to_frame("dtype"), use_container_width=False)
                    st.write("**Head (3 rows):**")
                    st.dataframe(df.head(3))

                    if "Close" in df.columns:
                        s = df["Close"]
                        st.write(f"**df['Close'] type:** `{type(s).__name__}`")
                        if isinstance(s, pd.Series) and len(s) > 0:
                            st.success(f"✅ SUCCESS — latest Close: **{s.iloc[-1]:.4f}**")
                            results["A"] = s
                        elif isinstance(s, pd.DataFrame):
                            st.error(f"❌ df['Close'] returned a DataFrame, not a Series — MultiIndex leak")
                            st.dataframe(s.head(3))
                            results["A"] = None
                        else:
                            st.error("❌ Empty or unusable Close column")
                            results["A"] = None
                    else:
                        st.error(f"❌ No 'Close' column. All columns: `{df.columns.tolist()}`")
                        results["A"] = None
            except Exception as e:
                st.error(f"❌ Exception: `{type(e).__name__}: {e}`")
                results["A"] = None

        # ── Method B: Ticker.history() ─────────────────────────────────────────
        with st.expander("Method B — yf.Ticker().history(period=...)", expanded=True):
            try:
                t    = yf.Ticker(ticker)
                hist = t.history(period=period, auto_adjust=True)
                st.write(f"**Shape:** {hist.shape}")
                st.write(f"**Columns:** `{hist.columns.tolist()}`")
                st.write(f"**Index tz:** `{hist.index.tz}`")
                st.write("**Head (3 rows):**")
                st.dataframe(hist.head(3))

                if "Close" in hist.columns and len(hist) > 0:
                    val = hist["Close"].iloc[-1]
                    st.success(f"✅ SUCCESS — latest Close: **{val:.4f}**")
                    results["B"] = hist["Close"]
                else:
                    st.error("❌ No usable Close column")
                    results["B"] = None
            except Exception as e:
                st.error(f"❌ Exception: `{type(e).__name__}: {e}`")
                results["B"] = None

        # ── Method C: Ticker.history(start=, end=) ────────────────────────────
        with st.expander("Method C — yf.Ticker().history(start=..., end=...)", expanded=True):
            try:
                import datetime as dt
                end_dt   = dt.date.today()
                start_dt = end_dt - dt.timedelta(days=10)
                t    = yf.Ticker(ticker)
                hist = t.history(start=str(start_dt), end=str(end_dt))
                st.write(f"**Shape:** {hist.shape}")
                st.write(f"**Columns:** `{hist.columns.tolist()}`")
                st.write("**Head (3 rows):**")
                st.dataframe(hist.head(3))

                if "Close" in hist.columns and len(hist) > 0:
                    val = hist["Close"].iloc[-1]
                    st.success(f"✅ SUCCESS — latest Close: **{val:.4f}**")
                    results["C"] = hist["Close"]
                else:
                    st.error("❌ No usable Close column")
                    results["C"] = None
            except Exception as e:
                st.error(f"❌ Exception: `{type(e).__name__}: {e}`")
                results["C"] = None

        # ── Method D: fast_info ────────────────────────────────────────────────
        with st.expander("Method D — yf.Ticker().fast_info['last_price']", expanded=True):
            try:
                t     = yf.Ticker(ticker)
                price = t.fast_info["last_price"]
                st.write(f"**fast_info keys:** `{list(t.fast_info.keys())[:8]}`")
                if price and price > 0:
                    st.success(f"✅ SUCCESS — last_price: **{price:.4f}**")
                    results["D"] = price
                else:
                    st.error(f"❌ Invalid price: {price}")
                    results["D"] = None
            except Exception as e:
                st.error(f"❌ Exception: `{type(e).__name__}: {e}`")
                results["D"] = None

        # ── Method E: download() default with MultiIndex flatten ───────────────
        with st.expander("Method E — yf.download() default + manual MultiIndex flatten", expanded=True):
            try:
                df = yf.download(ticker, period=period, auto_adjust=True, progress=False)
                st.write(f"**Shape:** {df.shape}")
                st.write(f"**Column type:** `{type(df.columns).__name__}`")
                st.write(f"**Columns:** `{df.columns.tolist()}`")
                st.write("**Head (3 rows):**")
                st.dataframe(df.head(3))

                # Try all key formats
                found = False
                for key in [("Close", ticker), ("Close", ticker.replace("^", "")), "Close"]:
                    if key in df.columns:
                        s = df[key]
                        if isinstance(s, pd.Series) and len(s) > 0:
                            st.success(f"✅ SUCCESS via key `{key!r}` — latest: **{s.iloc[-1]:.4f}**")
                            results["E"] = s
                            found = True
                            break

                if not found:
                    # Try MultiIndex level search
                    if isinstance(df.columns, pd.MultiIndex):
                        close_cols = [(a, b) for (a, b) in df.columns if a == "Close"]
                        st.write(f"**MultiIndex 'Close' columns found:** `{close_cols}`")
                        if close_cols:
                            s = df[close_cols[0]]
                            if isinstance(s, pd.Series) and len(s) > 0:
                                st.success(f"✅ SUCCESS via MultiIndex search `{close_cols[0]}` — latest: **{s.iloc[-1]:.4f}**")
                                results["E"] = s
                                found = True

                    if not found:
                        st.error("❌ Could not extract Close from any key")
                        results["E"] = None
            except Exception as e:
                st.error(f"❌ Exception: `{type(e).__name__}: {e}`")
                results["E"] = None

        # ── Summary ────────────────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("### Summary")
        working = [k for k, v in results.items() if v is not None]
        failing = [k for k, v in results.items() if v is None]

        if working:
            st.success(f"✅ Working methods: **{', '.join(working)}**")
            st.info(
                f"👉 Paste this output in chat. The fix will hardcode Method "
                f"**{working[0]}** as the primary fetch strategy in `data_fetcher.py`."
            )
        else:
            st.error(
                "❌ ALL methods failed. This likely means Yahoo Finance is being "
                "blocked by the server (common on Streamlit Cloud). "
                "Paste this output in chat — we'll switch KRE to an alternative source."
            )

        if failing:
            st.warning(f"Failing methods: {', '.join(failing)}")

    # ── 5Y period specific test ────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 5-year period test (used by the chart)")
    st.markdown("The chart requests `period='5y'` — test that specifically:")
    if st.button("▶ Test KRE with period='5y'"):
        try:
            df = yf.download(
                "KRE", period="5y", auto_adjust=True,
                progress=False, multi_level_index=False,
            )
            st.write(f"**Shape:** {df.shape}")
            st.write(f"**Columns:** `{df.columns.tolist()}`")
            st.write(f"**Column type:** `{type(df.columns).__name__}`")
            st.write("**Head (3 rows):**")
            st.dataframe(df.head(3))
            st.write("**Tail (3 rows):**")
            st.dataframe(df.tail(3))

            if "Close" in df.columns:
                s = df["Close"]
                st.write(f"**df['Close'] type:** `{type(s).__name__}`")
                st.write(f"**df['Close'] dtype:** `{s.dtype}`")
                if isinstance(s, pd.Series) and len(s) > 0:
                    st.success(f"✅ 5y fetch OK — {len(s)} rows, "
                               f"range: {s.min():.2f} – {s.max():.2f}, "
                               f"latest: {s.iloc[-1]:.2f}")
                    st.line_chart(s, use_container_width=True)
                elif isinstance(s, pd.DataFrame):
                    st.error("❌ Close returned a DataFrame not a Series — MultiIndex leak despite multi_level_index=False")
                    st.dataframe(s.head())
                else:
                    st.error("❌ Close empty or wrong type")
            else:
                st.error(f"❌ No 'Close' column. Got: `{df.columns.tolist()}`")
        except Exception as e:
            st.error(f"❌ Exception: `{type(e).__name__}: {e}`")

    # ── FRED quick test ────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### FRED connection test")
    if st.button("▶ Test FRED (DFII10 — TIPS real yield)"):
        try:
            import requests
            url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFII10"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                from io import StringIO
                df = pd.read_csv(StringIO(resp.text), parse_dates=["DATE"], index_col="DATE")
                df.columns = ["value"]
                df["value"] = pd.to_numeric(df["value"], errors="coerce")
                df = df.dropna()
                latest_val = df["value"].iloc[-1]
                latest_dt  = df.index[-1].date()
                st.success(f"✅ FRED OK — DFII10 latest: **{latest_val:.2f}%** as of {latest_dt}")
                st.line_chart(df.tail(252), use_container_width=True)
            else:
                st.error(f"❌ FRED returned HTTP {resp.status_code}")
        except Exception as e:
            st.error(f"❌ FRED connection failed: `{type(e).__name__}: {e}`")


# ─────────────────────────────────────────────────────────────────────────────
#  ROUTING
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    with st.sidebar:
        st.markdown("### Navigation")
        page = st.radio(
            label="",
            options=["📊 Dashboard", "🔬 Diagnostics"],
            index=0,
            label_visibility="collapsed",
        )
        st.markdown("---")
        st.markdown(
            "<div style='font-size:.72rem;color:#5c6475;line-height:1.6;'>"
            "Data: FRED · Yahoo Finance<br>"
            "Not investment advice."
            "</div>",
            unsafe_allow_html=True,
        )

    if page == "🔬 Diagnostics":
        diagnose_page()
    else:
        main()