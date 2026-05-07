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
    if refresh or cache_key not in st.session_state or \
       (now - st.session_state.get(cache_ts, 0)) > TTL:
        with st.spinner("Fetching live data from FRED & Yahoo Finance…"):
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
    tab1, tab2, tab3, tab4 = st.tabs(
        ["📋 Indicator Scorecard", "📈 Historical Charts", "⏱ Catalyst Timeline", "👁 Daily Watchlist"]
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
                        # KRE price chart — compute -30% alert from 52-week high
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
