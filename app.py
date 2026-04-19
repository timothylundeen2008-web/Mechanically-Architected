import math
from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple

import pandas as pd
import requests
import streamlit as st

# Optional dependency for KRE live price/history
try:
    import yfinance as yf
except Exception:
    yf = None

st.set_page_config(
    page_title="Macro Stress Monitor",
    page_icon="📉",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------- Styling ----------
st.markdown(
    """
    <style>
    :root {
        --bg: #111111;
        --panel: #1b1b1b;
        --panel-2: #222222;
        --text: #f4f4ef;
        --muted: #b8b8b0;
        --line: #78be20;
        --line-soft: rgba(120,190,32,0.55);
        --pill: #e9efd7;
        --pill-text: #527d1a;
        --danger: #ff6b6b;
    }

    .stApp {
        background: var(--bg);
        color: var(--text);
    }

    [data-testid="stHeader"] {
        background: transparent;
    }

    div[data-baseweb="tab-list"] {
        gap: 0.65rem;
    }

    button[data-baseweb="tab"] {
        background: transparent;
        border: 1px solid #4a4a4a;
        border-radius: 14px;
        color: var(--text);
        padding: 0.45rem 0.95rem;
    }

    button[data-baseweb="tab"][aria-selected="true"] {
        border-color: var(--line);
        box-shadow: inset 0 0 0 1px var(--line-soft);
    }

    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 3rem;
        max-width: 1200px;
    }

    .title-wrap {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 1rem;
        margin-bottom: 0.75rem;
    }

    .app-title {
        font-size: 2rem;
        font-weight: 700;
        line-height: 1.1;
        margin-bottom: 0.15rem;
        color: var(--text);
    }

    .app-updated {
        color: var(--muted);
        font-size: 1rem;
    }

    .signal-card {
        background: linear-gradient(180deg, #262626 0%, #232323 100%);
        border: 1.5px solid var(--line);
        border-radius: 18px;
        padding: 1.25rem 1.35rem 1.2rem 1.35rem;
        min-height: 360px;
        box-shadow: 0 0 0 1px rgba(120,190,32,0.08);
        display: flex;
        flex-direction: column;
        justify-content: flex-start;
        overflow: hidden;
    }

    .signal-eyebrow {
        color: #9d9d95;
        font-size: 0.92rem;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        margin-bottom: 0.2rem;
        font-weight: 600;
    }

    .signal-name {
        color: var(--text);
        font-size: 1.85rem;
        font-weight: 600;
        margin-bottom: 0.65rem;
    }

    .signal-value {
        color: var(--text);
        font-size: 3.4rem;
        line-height: 1;
        font-weight: 700;
        margin-bottom: 0.25rem;
    }

    .signal-sub {
        color: var(--muted);
        font-size: 0.98rem;
        margin-bottom: 1rem;
        min-height: 2.2rem;
    }

    .progress-label-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        color: var(--muted);
        font-size: 0.95rem;
        margin-bottom: 0.35rem;
    }

    .threshold-right {
        color: var(--text);
        font-weight: 600;
    }

    .bar-shell {
        width: 100%;
        height: 10px;
        background: #161616;
        border-radius: 999px;
        overflow: hidden;
        margin-bottom: 0.85rem;
    }

    .bar-fill {
        height: 100%;
        background: var(--line);
        border-radius: 999px;
    }

    .pill {
        display: inline-block;
        background: var(--pill);
        color: var(--pill-text);
        border-radius: 12px;
        padding: 0.35rem 0.7rem;
        font-size: 0.95rem;
        font-weight: 700;
        margin-top: 0.75rem;
        width: fit-content;
    }

    .pill-danger {
        background: #341616;
        color: #ffb4b4;
    }

    .streak-row {
        display: flex;
        gap: 0.38rem;
        margin-top: 0.4rem;
        margin-bottom: 0.6rem;
    }

    .streak-box {
        width: 28px;
        height: 28px;
        border-radius: 6px;
        background: #1a1a1a;
        border: 1px solid #2c2c2c;
        color: #d8d8d2;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 0.95rem;
        font-weight: 700;
    }

    .streak-box.on {
        background: rgba(120,190,32,0.16);
        border-color: var(--line);
        color: #eaf5d3;
    }

    .status-panel {
        background: linear-gradient(180deg, #202020 0%, #1b1b1b 100%);
        border-radius: 18px;
        padding: 1.25rem 1.5rem;
        margin-top: 1rem;
        margin-bottom: 1rem;
    }

    .status-title {
        color: var(--text);
        font-size: 1.2rem;
        margin-bottom: 0.95rem;
        font-weight: 600;
    }

    .status-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 1rem;
        text-align: center;
    }

    .status-value {
        font-size: 2.2rem;
        font-weight: 700;
        line-height: 1.1;
    }

    .status-label {
        color: var(--muted);
        font-size: 0.95rem;
    }

    .ask-bar {
        border: 1px solid #3d3d3d;
        border-radius: 14px;
        padding: 0.9rem 1rem;
        color: var(--text);
        text-align: center;
        font-size: 1rem;
        margin-bottom: 1.5rem;
    }

    .small-muted {
        color: var(--muted);
        font-size: 0.9rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- Constants ----------
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
YIELD_SERIES = "DGS10"
HY_SERIES = "BAMLH0A0HYM2"
IG_SERIES = "BAMLC0A0CM"
KRE_BASELINE_DEFAULT = 52.0
TREASURY_THRESHOLD = 5.0
TREASURY_STREAK_TRIGGER = 3
CREDIT_THRESHOLD = 6.0
KRE_ALERT_DECLINE = -30.0
DEFAULT_TIMEOUT = 30

# ---------- Helpers ----------

def fmt_dt(dt: datetime | None) -> str:
    if not dt:
        return "—"
    return dt.astimezone().strftime("%I:%M %p").lstrip("0")


def fmt_day(dt: datetime | None) -> str:
    if not dt:
        return "—"
    return dt.astimezone().strftime("%b %d")


def latest_business_days_streak(values: pd.Series, threshold: float) -> int:
    streak = 0
    ordered = values.dropna().sort_index(ascending=False)
    for val in ordered:
        if float(val) > threshold:
            streak += 1
        else:
            break
    return streak


def progress_pct(value: float, threshold: float) -> float:
    if threshold <= 0:
        return 0.0
    return max(0.0, min(100.0, (value / threshold) * 100.0))


def signed_pct_text(v: float) -> str:
    sign = "-" if v < 0 else ""
    return f"{sign}{abs(v):.1f}%"


def stress_level(triggered: int) -> str:
    return {0: "LOW", 1: "ELEVATED", 2: "HIGH", 3: "CRITICAL"}.get(triggered, "LOW")


def fred_observations(series_id: str, api_key: str | None = None, days: int = 60) -> pd.DataFrame:
    params = {
        "series_id": series_id,
        "file_type": "json",
        "sort_order": "asc",
        "observation_start": (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d"),
    }
    if api_key:
        params["api_key"] = api_key

    r = requests.get(FRED_BASE, params=params, timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()
    payload = r.json()
    obs = payload.get("observations", [])
    df = pd.DataFrame(obs)
    if df.empty:
        raise ValueError(f"No FRED data returned for {series_id}")
    df = df[["date", "value"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"].replace(".", pd.NA), errors="coerce")
    return df.dropna(subset=["value"]).reset_index(drop=True)


def fetch_kre_history() -> pd.DataFrame:
    if yf is None:
        raise ImportError("yfinance is not installed. Add it to requirements.txt.")

    ticker = yf.Ticker("KRE")
    hist = ticker.history(period="6mo", interval="1d", auto_adjust=False)
    if hist.empty:
        raise ValueError("No KRE history returned.")

    hist = hist.reset_index()
    date_col = "Date" if "Date" in hist.columns else hist.columns[0]
    hist[date_col] = pd.to_datetime(hist[date_col]).dt.tz_localize(None)

    close_col = "Close"
    if close_col not in hist.columns:
        raise ValueError("KRE close price not found in history output.")

    out = hist[[date_col, close_col]].rename(columns={date_col: "date", close_col: "close"}).copy()
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    return out.dropna(subset=["close"]).reset_index(drop=True)


@st.cache_data(ttl="1d", show_spinner=False)
def load_market_snapshot(api_key: str | None, manual_refresh_nonce: int) -> Dict:
    # manual_refresh_nonce is intentionally unused except to break cache when requested.
    _ = manual_refresh_nonce

    dgs10 = fred_observations(YIELD_SERIES, api_key=api_key, days=90)
    hy = fred_observations(HY_SERIES, api_key=api_key, days=90)
    ig = fred_observations(IG_SERIES, api_key=api_key, days=90)
    kre = fetch_kre_history()

    merged_credit = hy.merge(ig, on="date", how="inner", suffixes=("_hy", "_ig"))
    merged_credit["spread"] = merged_credit["value_hy"] - merged_credit["value_ig"]

    latest_yield = float(dgs10.iloc[-1]["value"])
    latest_credit = float(merged_credit.iloc[-1]["spread"])
    latest_kre = float(kre.iloc[-1]["close"])

    streak = latest_business_days_streak(dgs10.set_index("date")["value"], TREASURY_THRESHOLD)

    fetched_at = datetime.now(timezone.utc)
    market_date = max(dgs10.iloc[-1]["date"], merged_credit.iloc[-1]["date"], kre.iloc[-1]["date"])

    return {
        "yield_value": latest_yield,
        "yield_date": pd.Timestamp(dgs10.iloc[-1]["date"]).to_pydatetime().replace(tzinfo=timezone.utc),
        "yield_streak": streak,
        "credit_value": latest_credit,
        "credit_date": pd.Timestamp(merged_credit.iloc[-1]["date"]).to_pydatetime().replace(tzinfo=timezone.utc),
        "hy_value": float(merged_credit.iloc[-1]["value_hy"]),
        "ig_value": float(merged_credit.iloc[-1]["value_ig"]),
        "kre_value": latest_kre,
        "kre_date": pd.Timestamp(kre.iloc[-1]["date"]).to_pydatetime().replace(tzinfo=timezone.utc),
        "market_date": pd.Timestamp(market_date).to_pydatetime().replace(tzinfo=timezone.utc),
        "fetched_at": fetched_at,
        "yield_history": dgs10,
        "credit_history": merged_credit[["date", "spread"]].copy(),
        "kre_history": kre,
    }


def progress_html(current_pct: float) -> str:
    current_pct = max(0.0, min(100.0, current_pct))
    return f"""
    <div class="bar-shell">
        <div class="bar-fill" style="width:{current_pct:.1f}%"></div>
    </div>
    """


def streak_boxes_html(streak: int, target: int) -> str:
    boxes = []
    for idx in range(target):
        on = idx < streak
        content = "✓" if on else "•"
        boxes.append(f'<span class="streak-box {"on" if on else ""}">{content}</span>')
    return f'<div class="streak-row">{"".join(boxes)}</div>'


def signal_card_1_html(yield_value: float, streak: int, triggered: bool) -> str:
    pill = "Treasury signal triggered" if triggered else "Below threshold"
    pill_cls = "pill pill-danger" if triggered else "pill"

    return f"""
    <div class="signal-card">
        <div class="signal-eyebrow">Signal 1 — Treasury</div>
        <div class="signal-name">10-year yield</div>
        <div class="signal-value">{yield_value:.2f}%</div>
        <div class="signal-sub">Current yield vs threshold</div>

        <div class="progress-label-row">
            <span>Alert threshold</span>
            <span class="threshold-right">{TREASURY_THRESHOLD:.2f}%</span>
        </div>
        {progress_html(progress_pct(yield_value, TREASURY_THRESHOLD))}

        <div class="progress-label-row">
            <span>Days above 5% (need {TREASURY_STREAK_TRIGGER} to trigger)</span>
            <span class="threshold-right">{streak}/{TREASURY_STREAK_TRIGGER}</span>
        </div>
        {streak_boxes_html(streak, TREASURY_STREAK_TRIGGER)}

        <span class="{pill_cls}">{pill}</span>
    </div>
    """


def signal_card_2_html(kre_value: float, baseline: float, triggered: bool) -> str:
    decline_pct = ((kre_value / baseline) - 1.0) * 100.0
    alert_level_price = baseline * (1.0 + KRE_ALERT_DECLINE / 100.0)
    progress = max(0.0, min(100.0, abs(decline_pct) / abs(KRE_ALERT_DECLINE) * 100.0))

    badge_text = (
        f"{abs(decline_pct):.1f}% from baseline"
        if decline_pct <= 0
        else f"{decline_pct:.1f}% above baseline"
    )
    pill_cls = "pill pill-danger" if triggered else "pill"

    return f"""
    <div class="signal-card">
        <div class="signal-eyebrow">Signal 2 — Regional Banks</div>
        <div class="signal-name">KRE ETF</div>
        <div class="signal-value">${kre_value:,.2f}</div>
        <div class="signal-sub">{signed_pct_text(decline_pct)} from baseline (${baseline:,.2f})</div>

        <div class="progress-label-row">
            <span>Alert level (-30%)</span>
            <span class="threshold-right">${alert_level_price:,.2f}</span>
        </div>
        {progress_html(progress)}

        <span class="{pill_cls}">{badge_text}</span>
    </div>
    """


def signal_card_3_html(credit_value: float, hy_value: float, ig_value: float, triggered: bool) -> str:
    label = f"{credit_value:.2f}% spread — {'alert' if triggered else 'normal'}"
    pill_cls = "pill pill-danger" if triggered else "pill"

    return f"""
    <div class="signal-card">
        <div class="signal-eyebrow">Signal 3 — Credit</div>
        <div class="signal-name">HY − IG spread</div>
        <div class="signal-value">{credit_value:.2f}%</div>
        <div class="signal-sub">HY: {hy_value:.2f}% &nbsp;&nbsp; IG: {ig_value:.2f}%</div>

        <div class="progress-label-row">
            <span>Alert threshold</span>
            <span class="threshold-right">{CREDIT_THRESHOLD:.2f}%</span>
        </div>
        {progress_html(progress_pct(credit_value, CREDIT_THRESHOLD))}

        <span class="{pill_cls}">{label}</span>
    </div>
    """


# ---------- Header ----------
if "manual_refresh_nonce" not in st.session_state:
    st.session_state.manual_refresh_nonce = 0
if "kre_baseline" not in st.session_state:
    st.session_state.kre_baseline = KRE_BASELINE_DEFAULT

left, right = st.columns([5, 1.4])
with left:
    st.markdown('<div class="app-title">Macro stress monitor</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="app-updated">Live data refreshes automatically every day; last fetch shown below.</div>',
        unsafe_allow_html=True,
    )
with right:
    if st.button("Recalculate", use_container_width=True):
        st.session_state.manual_refresh_nonce += 1
        st.cache_data.clear()
        st.rerun()

# ---------- Secrets / API key ----------
fred_api_key = None
try:
    fred_api_key = st.secrets.get("FRED_API_KEY")
except Exception:
    fred_api_key = None

if not fred_api_key:
    st.info(
        "Optional: add `FRED_API_KEY` to your Streamlit secrets for higher-rate, more reliable FRED access. "
        "The app can still work without it for lighter usage."
    )

# ---------- Data load ----------
error = None
snapshot = None
try:
    snapshot = load_market_snapshot(fred_api_key, st.session_state.manual_refresh_nonce)
except Exception as exc:
    error = str(exc)

if error:
    st.error(f"Data update failed: {error}")
    st.stop()

# ---------- Derived metrics ----------
yield_triggered = (
    snapshot["yield_value"] > TREASURY_THRESHOLD
    and snapshot["yield_streak"] >= TREASURY_STREAK_TRIGGER
)

kre_baseline = float(st.session_state.kre_baseline)
kre_decline_pct = ((snapshot["kre_value"] / kre_baseline) - 1.0) * 100.0
kre_triggered = kre_decline_pct <= KRE_ALERT_DECLINE
credit_triggered = snapshot["credit_value"] >= CREDIT_THRESHOLD
signals_triggered = int(yield_triggered) + int(kre_triggered) + int(credit_triggered)
overall = stress_level(signals_triggered)

# ---------- Tabs ----------
dashboard_tab, enter_tab, guide_tab = st.tabs(["Dashboard", "Enter data", "Signal guide"])

with dashboard_tab:
    st.markdown(
        f'<div class="small-muted">Updated {fmt_dt(snapshot["fetched_at"])} · market date {fmt_day(snapshot["market_date"])} </div>',
        unsafe_allow_html=True,
    )
    st.write("")

    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(
            signal_card_1_html(
                snapshot["yield_value"],
                snapshot["yield_streak"],
                yield_triggered,
            ),
            unsafe_allow_html=True,
        )

    with c2:
        st.markdown(
            signal_card_2_html(
                snapshot["kre_value"],
                kre_baseline,
                kre_triggered,
            ),
            unsafe_allow_html=True,
        )

    with c3:
        st.markdown(
            signal_card_3_html(
                snapshot["credit_value"],
                snapshot["hy_value"],
                snapshot["ig_value"],
                credit_triggered,
            ),
            unsafe_allow_html=True,
        )

    level_color = "#78be20" if signals_triggered == 0 else ("#c6d930" if signals_triggered == 1 else ("#f5a524" if signals_triggered == 2 else "#ff6b6b"))
    st.markdown(
        f"""
        <div class="status-panel">
            <div class="status-title">Overall stress status</div>
            <div class="status-grid">
                <div>
                    <div class="status-value">{signals_triggered}/3</div>
                    <div class="status-label">Signals triggered</div>
                </div>
                <div>
                    <div class="status-value" style="color:{level_color};">{overall}</div>
                    <div class="status-label">Stress level</div>
                </div>
                <div>
                    <div class="status-value">{fmt_day(snapshot['market_date'])}</div>
                    <div class="status-label">Last updated</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="ask-bar">If all 3 signals fire: review liquidity, counterparty risk, and de-risking options.</div>', unsafe_allow_html=True)

    st.markdown(
        """
        ### How this works
        **Automatic update:** the app caches market/API pulls for one day, then refreshes on the next run automatically.  
        **Manual update:** click **Recalculate** at the top right anytime to clear the cache and fetch fresh values immediately.
        """
    )

with enter_tab:
    st.subheader("Settings")
    baseline = st.number_input(
        "KRE baseline",
        min_value=1.0,
        value=float(st.session_state.kre_baseline),
        step=0.5,
        help="Set a fixed KRE reference level. The dashboard tracks decline from this level.",
    )
    st.session_state.kre_baseline = baseline

    st.markdown("### Current live inputs")
    live_df = pd.DataFrame(
        [
            {"Metric": "10-year Treasury yield", "Value": f"{snapshot['yield_value']:.2f}%", "Market date": fmt_day(snapshot["yield_date"])},
            {"Metric": "KRE ETF", "Value": f"${snapshot['kre_value']:.2f}", "Market date": fmt_day(snapshot["kre_date"])},
            {"Metric": "HY spread", "Value": f"{snapshot['hy_value']:.2f}%", "Market date": fmt_day(snapshot["credit_date"])},
            {"Metric": "IG spread", "Value": f"{snapshot['ig_value']:.2f}%", "Market date": fmt_day(snapshot["credit_date"])},
            {"Metric": "HY − IG spread", "Value": f"{snapshot['credit_value']:.2f}%", "Market date": fmt_day(snapshot["credit_date"])},
            {"Metric": "Days above 5%", "Value": snapshot["yield_streak"], "Market date": fmt_day(snapshot["yield_date"])},
        ]
    )
    st.dataframe(live_df, use_container_width=True, hide_index=True)

    st.caption("Tip: the Treasury streak is fully automatic. The app computes consecutive business days above 5% directly from recent FRED history.")

with guide_tab:
    st.subheader("Signal guide")
    st.markdown(
        f"""
        **Signal 1 — Treasury**  
        Trigger when the **10-year Treasury yield is above {TREASURY_THRESHOLD:.0f}% for {TREASURY_STREAK_TRIGGER} consecutive trading days**.

        **Signal 2 — Regional banks**  
        Trigger when **KRE is down 30% or more from the chosen baseline**.

        **Signal 3 — Credit**  
        Trigger when the **high-yield minus investment-grade spread reaches {CREDIT_THRESHOLD:.0f}% or higher**.
        """
    )

    st.markdown("### Data sources")
    sources_df = pd.DataFrame(
        [
            {"Source": "FRED", "Series / endpoint": YIELD_SERIES, "Use": "10-year Treasury yield"},
            {"Source": "FRED", "Series / endpoint": HY_SERIES, "Use": "High-yield corporate spread"},
            {"Source": "FRED", "Series / endpoint": IG_SERIES, "Use": "Investment-grade corporate spread"},
            {"Source": "Yahoo Finance via yfinance", "Series / endpoint": "KRE", "Use": "Regional bank ETF price"},
        ]
    )
    st.dataframe(sources_df, use_container_width=True, hide_index=True)

    st.markdown("### Streamlit deployment notes")
    st.markdown(
        """
        1. Put this file in your repo as `app.py`.
        2. Add the packages from `requirements.txt`.
        3. In Streamlit Community Cloud, add `FRED_API_KEY` in **App settings → Secrets**.
        4. Deploy.
        """
    )
