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
    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["📋 Indicator Scorecard", "📈 Historical Charts", "⏱ Catalyst Timeline", "👁 Daily Watchlist", "💰 Wealth-Building Assets"]
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

    # ── TAB 5: WEALTH-BUILDING ASSETS ─────────────────────────────────────────
    with tab5:
        wealth_assets_tab(raw)

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
                    with st.spinner(f"Loading {ticker}…"):
                        try:
                            series = fetch_yf_series(ticker, period="2y")
                        except Exception:
                            series = pd.Series(dtype=float)

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
