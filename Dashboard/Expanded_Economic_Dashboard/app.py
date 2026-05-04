import time
from datetime import datetime, timedelta, timezone
from typing import Dict

import pandas as pd
import requests
import streamlit as st

try:
    import yfinance as yf
except Exception:
    yf = None

st.set_page_config(
    page_title="Macro Repression + Stress Monitor",
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
        --text: #f4f4ef;
        --muted: #b8b8b0;
        --line: #78be20;
        --warning: #f5a524;
        --danger: #ff6b6b;
        --pill: #e9efd7;
        --pill-text: #527d1a;
    }

    .stApp { background: var(--bg); color: var(--text); }
    [data-testid="stHeader"] { background: transparent; }

    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 3rem;
        max-width: 1250px;
    }

    div[data-baseweb="tab-list"] { gap: 0.65rem; }

    button[data-baseweb="tab"] {
        background: transparent;
        border: 1px solid #4a4a4a;
        border-radius: 14px;
        color: var(--text);
        padding: 0.45rem 0.95rem;
    }

    button[data-baseweb="tab"][aria-selected="true"] {
        border-color: var(--line);
        box-shadow: inset 0 0 0 1px rgba(120,190,32,0.55);
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
        padding: 1.25rem 1.35rem;
        min-height: 335px;
        box-shadow: 0 0 0 1px rgba(120,190,32,0.08);
        overflow: hidden;
    }

    .signal-card.warning { border-color: var(--warning); }
    .signal-card.danger { border-color: var(--danger); }

    .signal-eyebrow {
        color: #9d9d95;
        font-size: 0.9rem;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        margin-bottom: 0.2rem;
        font-weight: 600;
    }

    .signal-name {
        color: var(--text);
        font-size: 1.65rem;
        font-weight: 600;
        margin-bottom: 0.65rem;
    }

    .signal-value {
        color: var(--text);
        font-size: 3rem;
        line-height: 1;
        font-weight: 700;
        margin-bottom: 0.3rem;
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

    .bar-fill.warning { background: var(--warning); }
    .bar-fill.danger { background: var(--danger); }

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

    .pill-warning {
        background: #3b2b08;
        color: #ffd98a;
    }

    .pill-danger {
        background: #341616;
        color: #ffb4b4;
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
        grid-template-columns: repeat(4, 1fr);
        gap: 1rem;
        text-align: center;
    }

    .status-value {
        font-size: 2.1rem;
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
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- Constants ----------
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

YIELD_SERIES = "DGS10"
HY_SERIES = "BAMLH0A0HYM2"
IG_SERIES = "BAMLC0A0CM"

TIPS_SERIES = "DFII10"
BREAKEVEN_SERIES = "T10YIE"
FED_FUNDS_SERIES = "FEDFUNDS"
CPI_SERIES = "CPIAUCSL"
M2_SERIES = "M2SL"

KRE_BASELINE_DEFAULT = 52.0

TREASURY_THRESHOLD = 5.0
TREASURY_STREAK_TRIGGER = 3
CREDIT_THRESHOLD = 6.0
KRE_ALERT_DECLINE = -30.0

TIPS_EARLY_WARNING = 1.5
TIPS_REPRESSION_WARNING = 0.5
BREAKEVEN_WARNING = 3.0
REAL_POLICY_WARNING = 0.0
M2_WARNING = 6.0

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


def fred_observations(series_id: str, api_key: str | None = None, days: int = 900) -> pd.DataFrame:
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

    hist = yf.Ticker("KRE").history(period="6mo", interval="1d", auto_adjust=False)

    if hist.empty:
        raise ValueError("No KRE history returned.")

    hist = hist.reset_index()
    date_col = "Date" if "Date" in hist.columns else hist.columns[0]
    hist[date_col] = pd.to_datetime(hist[date_col]).dt.tz_localize(None)

    out = hist[[date_col, "Close"]].rename(columns={date_col: "date", "Close": "close"}).copy()
    out["close"] = pd.to_numeric(out["close"], errors="coerce")

    return out.dropna(subset=["close"]).reset_index(drop=True)


def latest_business_days_streak(values: pd.Series, threshold: float) -> int:
    streak = 0
    ordered = values.dropna().sort_index(ascending=False)

    for val in ordered:
        if float(val) > threshold:
            streak += 1
        else:
            break

    return streak


def yoy_latest(df: pd.DataFrame, periods: int = 12) -> float:
    temp = df.copy()
    temp["yoy"] = temp["value"].pct_change(periods) * 100
    temp = temp.dropna(subset=["yoy"])
    if temp.empty:
        return float("nan")
    return float(temp.iloc[-1]["yoy"])


def progress_pct(value: float, threshold: float) -> float:
    if threshold <= 0:
        return 0.0
    return max(0.0, min(100.0, (value / threshold) * 100.0))


def inverse_progress_pct(value: float, start: float, danger: float) -> float:
    if start == danger:
        return 0.0
    pct = (start - value) / (start - danger) * 100
    return max(0.0, min(100.0, pct))


def signed_pct_text(v: float) -> str:
    sign = "-" if v < 0 else ""
    return f"{sign}{abs(v):.1f}%"


def stress_level(triggered: int) -> str:
    return {0: "LOW", 1: "ELEVATED", 2: "HIGH", 3: "CRITICAL"}.get(triggered, "LOW")


def repression_level(score: int) -> str:
    if score <= 1:
        return "LOW"
    if score == 2:
        return "ELEVATED"
    if score == 3:
        return "HIGH"
    return "CRITICAL"


def progress_html(current_pct: float, mode: str = "normal") -> str:
    current_pct = max(0.0, min(100.0, current_pct))
    cls = "bar-fill"
    if mode == "warning":
        cls += " warning"
    elif mode == "danger":
        cls += " danger"

    return f"""
    <div class="bar-shell">
        <div class="{cls}" style="width:{current_pct:.1f}%"></div>
    </div>
    """


def streak_boxes_html(streak: int, target: int) -> str:
    boxes = []
    for idx in range(target):
        on = idx < streak
        content = "✓" if on else "•"
        boxes.append(f'<span class="streak-box {"on" if on else ""}">{content}</span>')
    return f'<div class="streak-row">{"".join(boxes)}</div>'


def metric_card_html(
    eyebrow: str,
    name: str,
    value: str,
    sub: str,
    threshold_label: str,
    threshold_value: str,
    progress: float,
    pill: str,
    state: str = "normal",
) -> str:
    card_cls = "signal-card"
    pill_cls = "pill"

    if state == "warning":
        card_cls += " warning"
        pill_cls += " pill-warning"
    elif state == "danger":
        card_cls += " danger"
        pill_cls += " pill-danger"

    return f"""
    <div class="{card_cls}">
        <div class="signal-eyebrow">{eyebrow}</div>
        <div class="signal-name">{name}</div>
        <div class="signal-value">{value}</div>
        <div class="signal-sub">{sub}</div>

        <div class="progress-label-row">
            <span>{threshold_label}</span>
            <span class="threshold-right">{threshold_value}</span>
        </div>

        {progress_html(progress, state)}

        <span class="{pill_cls}">{pill}</span>
    </div>
    """


@st.cache_data(ttl="1d", show_spinner=False)
def load_market_snapshot(api_key: str | None, manual_refresh_nonce: int) -> Dict:
    _ = manual_refresh_nonce

    dgs10 = fred_observations(YIELD_SERIES, api_key=api_key, days=180)
    hy = fred_observations(HY_SERIES, api_key=api_key, days=180)
    ig = fred_observations(IG_SERIES, api_key=api_key, days=180)
    kre = fetch_kre_history()

    tips = fred_observations(TIPS_SERIES, api_key=api_key, days=900)
    breakeven = fred_observations(BREAKEVEN_SERIES, api_key=api_key, days=900)
    fed_funds = fred_observations(FED_FUNDS_SERIES, api_key=api_key, days=900)
    cpi = fred_observations(CPI_SERIES, api_key=api_key, days=900)
    m2 = fred_observations(M2_SERIES, api_key=api_key, days=900)

    merged_credit = hy.merge(ig, on="date", how="inner", suffixes=("_hy", "_ig"))
    merged_credit["spread"] = merged_credit["value_hy"] - merged_credit["value_ig"]

    latest_yield = float(dgs10.iloc[-1]["value"])
    latest_credit = float(merged_credit.iloc[-1]["spread"])
    latest_kre = float(kre.iloc[-1]["close"])

    latest_tips = float(tips.iloc[-1]["value"])
    latest_breakeven = float(breakeven.iloc[-1]["value"])
    latest_fed_funds = float(fed_funds.iloc[-1]["value"])
    latest_cpi_yoy = yoy_latest(cpi, periods=12)
    latest_m2_yoy = yoy_latest(m2, periods=12)
    latest_real_policy = latest_fed_funds - latest_cpi_yoy

    streak = latest_business_days_streak(
        dgs10.set_index("date")["value"],
        TREASURY_THRESHOLD,
    )

    fetched_at = datetime.now(timezone.utc)

    market_date = max(
        dgs10.iloc[-1]["date"],
        merged_credit.iloc[-1]["date"],
        kre.iloc[-1]["date"],
        tips.iloc[-1]["date"],
        breakeven.iloc[-1]["date"],
        fed_funds.iloc[-1]["date"],
        cpi.iloc[-1]["date"],
        m2.iloc[-1]["date"],
    )

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

        "tips_value": latest_tips,
        "tips_date": pd.Timestamp(tips.iloc[-1]["date"]).to_pydatetime().replace(tzinfo=timezone.utc),

        "breakeven_value": latest_breakeven,
        "breakeven_date": pd.Timestamp(breakeven.iloc[-1]["date"]).to_pydatetime().replace(tzinfo=timezone.utc),

        "fed_funds_value": latest_fed_funds,
        "fed_funds_date": pd.Timestamp(fed_funds.iloc[-1]["date"]).to_pydatetime().replace(tzinfo=timezone.utc),

        "cpi_yoy": latest_cpi_yoy,
        "cpi_date": pd.Timestamp(cpi.iloc[-1]["date"]).to_pydatetime().replace(tzinfo=timezone.utc),

        "real_policy_rate": latest_real_policy,

        "m2_yoy": latest_m2_yoy,
        "m2_date": pd.Timestamp(m2.iloc[-1]["date"]).to_pydatetime().replace(tzinfo=timezone.utc),

        "market_date": pd.Timestamp(market_date).to_pydatetime().replace(tzinfo=timezone.utc),
        "fetched_at": fetched_at,

        "yield_history": dgs10,
        "credit_history": merged_credit[["date", "spread"]].copy(),
        "kre_history": kre,
        "tips_history": tips,
        "breakeven_history": breakeven,
        "fed_funds_history": fed_funds,
        "cpi_history": cpi,
        "m2_history": m2,
    }


def signal_card_1_html(yield_value: float, streak: int, triggered: bool) -> str:
    pill = "Treasury signal triggered" if triggered else "Below threshold"
    state = "danger" if triggered else "normal"

    return f"""
    <div class="signal-card {'danger' if triggered else ''}">
        <div class="signal-eyebrow">Signal 1 — Treasury</div>
        <div class="signal-name">10-year yield</div>
        <div class="signal-value">{yield_value:.2f}%</div>
        <div class="signal-sub">Current yield vs threshold</div>

        <div class="progress-label-row">
            <span>Alert threshold</span>
            <span class="threshold-right">{TREASURY_THRESHOLD:.2f}%</span>
        </div>
        {progress_html(progress_pct(yield_value, TREASURY_THRESHOLD), state)}

        <div class="progress-label-row">
            <span>Days above 5% need {TREASURY_STREAK_TRIGGER}</span>
            <span class="threshold-right">{streak}/{TREASURY_STREAK_TRIGGER}</span>
        </div>
        {streak_boxes_html(streak, TREASURY_STREAK_TRIGGER)}

        <span class="pill {'pill-danger' if triggered else ''}">{pill}</span>
    </div>
    """


def signal_card_2_html(kre_value: float, baseline: float, triggered: bool) -> str:
    decline_pct = ((kre_value / baseline) - 1.0) * 100.0
    alert_level_price = baseline * (1.0 + KRE_ALERT_DECLINE / 100.0)
    progress = max(0.0, min(100.0, abs(decline_pct) / abs(KRE_ALERT_DECLINE) * 100.0))
    state = "danger" if triggered else "normal"

    badge_text = (
        f"{abs(decline_pct):.1f}% from baseline"
        if decline_pct <= 0
        else f"{decline_pct:.1f}% above baseline"
    )

    return f"""
    <div class="signal-card {'danger' if triggered else ''}">
        <div class="signal-eyebrow">Signal 2 — Regional Banks</div>
        <div class="signal-name">KRE ETF</div>
        <div class="signal-value">${kre_value:,.2f}</div>
        <div class="signal-sub">{signed_pct_text(decline_pct)} from baseline (${baseline:,.2f})</div>

        <div class="progress-label-row">
            <span>Alert level -30%</span>
            <span class="threshold-right">${alert_level_price:,.2f}</span>
        </div>

        {progress_html(progress, state)}

        <span class="pill {'pill-danger' if triggered else ''}">{badge_text}</span>
    </div>
    """


def signal_card_3_html(credit_value: float, hy_value: float, ig_value: float, triggered: bool) -> str:
    state = "danger" if triggered else "normal"
    label = f"{credit_value:.2f}% spread — {'alert' if triggered else 'normal'}"

    return f"""
    <div class="signal-card {'danger' if triggered else ''}">
        <div class="signal-eyebrow">Signal 3 — Credit</div>
        <div class="signal-name">HY − IG spread</div>
        <div class="signal-value">{credit_value:.2f}%</div>
        <div class="signal-sub">HY: {hy_value:.2f}% &nbsp;&nbsp; IG: {ig_value:.2f}%</div>

        <div class="progress-label-row">
            <span>Alert threshold</span>
            <span class="threshold-right">{CREDIT_THRESHOLD:.2f}%</span>
        </div>

        {progress_html(progress_pct(credit_value, CREDIT_THRESHOLD), state)}

        <span class="pill {'pill-danger' if triggered else ''}">{label}</span>
    </div>
    """


# ---------- Header ----------
if "manual_refresh_nonce" not in st.session_state:
    st.session_state.manual_refresh_nonce = 0

if "kre_baseline" not in st.session_state:
    st.session_state.kre_baseline = KRE_BASELINE_DEFAULT

left, right = st.columns([5, 1.4])

with left:
    st.markdown('<div class="app-title">Macro repression + systemic stress monitor</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="app-updated">One Streamlit dashboard for slow-burn financial repression signals and market-breakage stress signals.</div>',
        unsafe_allow_html=True,
    )

with right:
    if st.button("Recalculate", use_container_width=True):
        st.session_state.manual_refresh_nonce += 1
        st.cache_data.clear()
        st.rerun()

# ---------- API Key ----------
try:
    fred_api_key = st.secrets.get("FRED_API_KEY")
except Exception:
    fred_api_key = None

if not fred_api_key:
    st.warning("FRED_API_KEY was not found. Add it to Streamlit Secrets or your local environment for reliable API access.")

# ---------- Data Load ----------
try:
    snapshot = load_market_snapshot(fred_api_key, st.session_state.manual_refresh_nonce)
    st.session_state["last_good_snapshot"] = snapshot
except Exception as exc:
    snapshot = st.session_state.get("last_good_snapshot")
    if snapshot is None:
        st.error(f"Live data failed and no cached snapshot exists: {exc}")
        st.stop()
    else:
        st.warning(f"Live update failed. Showing last good cached data instead: {exc}")

# ---------- Derived Stress ----------
kre_baseline = float(st.session_state.kre_baseline)
kre_decline_pct = ((snapshot["kre_value"] / kre_baseline) - 1.0) * 100.0

yield_triggered = snapshot["yield_value"] > TREASURY_THRESHOLD and snapshot["yield_streak"] >= TREASURY_STREAK_TRIGGER
kre_triggered = kre_decline_pct <= KRE_ALERT_DECLINE
credit_triggered = snapshot["credit_value"] >= CREDIT_THRESHOLD

signals_triggered = int(yield_triggered) + int(kre_triggered) + int(credit_triggered)
overall_stress = stress_level(signals_triggered)

# ---------- Derived Repression ----------
tips_triggered = snapshot["tips_value"] <= TIPS_REPRESSION_WARNING
tips_warning = snapshot["tips_value"] <= TIPS_EARLY_WARNING

breakeven_triggered = snapshot["breakeven_value"] >= BREAKEVEN_WARNING
real_policy_triggered = snapshot["real_policy_rate"] < REAL_POLICY_WARNING
m2_triggered = snapshot["m2_yoy"] >= M2_WARNING

repression_score = int(tips_warning) + int(breakeven_triggered) + int(real_policy_triggered) + int(m2_triggered)
overall_repression = repression_level(repression_score)

if tips_triggered and breakeven_triggered and real_policy_triggered:
    activation_stage = "ACTIVE"
elif tips_warning and breakeven_triggered:
    activation_stage = "LATE WARNING"
elif tips_warning:
    activation_stage = "EARLY WARNING"
else:
    activation_stage = "NOT ACTIVE"

# ---------- Tabs ----------
summary_tab, stress_tab, repression_tab, data_tab, guide_tab = st.tabs(
    ["Summary", "Systemic Stress", "Financial Repression", "Enter Data", "Signal Guide"]
)

with summary_tab:
    st.markdown(
        f'<div class="small-muted">Updated {fmt_dt(snapshot["fetched_at"])} · market date {fmt_day(snapshot["market_date"])}</div>',
        unsafe_allow_html=True,
    )
    st.write("")

    stress_color = "#78be20" if signals_triggered == 0 else ("#f5a524" if signals_triggered <= 2 else "#ff6b6b")
    repression_color = "#78be20" if repression_score <= 1 else ("#f5a524" if repression_score <= 3 else "#ff6b6b")

    st.markdown(
        f"""
        <div class="status-panel">
            <div class="status-title">Macro dashboard summary</div>
            <div class="status-grid">
                <div>
                    <div class="status-value" style="color:{stress_color};">{overall_stress}</div>
                    <div class="status-label">Systemic stress</div>
                </div>
                <div>
                    <div class="status-value">{signals_triggered}/3</div>
                    <div class="status-label">Stress signals</div>
                </div>
                <div>
                    <div class="status-value" style="color:{repression_color};">{overall_repression}</div>
                    <div class="status-label">Repression risk</div>
                </div>
                <div>
                    <div class="status-value">{activation_stage}</div>
                    <div class="status-label">Activation sequence</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.markdown(
            metric_card_html(
                "Repression Core",
                "10Y TIPS real yield",
                f"{snapshot['tips_value']:.2f}%",
                "Most important repression signal",
                "Early warning",
                f"≤ {TIPS_EARLY_WARNING:.1f}%",
                inverse_progress_pct(snapshot["tips_value"], 2.5, 0.0),
                "Watch for trend toward zero",
                "danger" if tips_triggered else ("warning" if tips_warning else "normal"),
            ),
            unsafe_allow_html=True,
        )

    with c2:
        st.markdown(
            metric_card_html(
                "Inflation Expectations",
                "10Y breakeven",
                f"{snapshot['breakeven_value']:.2f}%",
                "Market-implied inflation expectation",
                "Alert threshold",
                f"≥ {BREAKEVEN_WARNING:.1f}%",
                progress_pct(snapshot["breakeven_value"], BREAKEVEN_WARNING),
                "Breakeven pressure building" if breakeven_triggered else "Below alert",
                "danger" if breakeven_triggered else "normal",
            ),
            unsafe_allow_html=True,
        )

    with c3:
        st.markdown(
            metric_card_html(
                "Policy Repression",
                "Real policy rate",
                f"{snapshot['real_policy_rate']:.2f}%",
                "Fed Funds minus CPI YoY",
                "Repression threshold",
                "< 0.0%",
                inverse_progress_pct(snapshot["real_policy_rate"], 3.0, 0.0),
                "Negative real policy rate" if real_policy_triggered else "Positive real policy rate",
                "danger" if real_policy_triggered else "normal",
            ),
            unsafe_allow_html=True,
        )

    with c4:
        st.markdown(
            metric_card_html(
                "Liquidity",
                "M2 YoY",
                f"{snapshot['m2_yoy']:.2f}%",
                "Money supply growth",
                "Liquidity warning",
                f"≥ {M2_WARNING:.1f}%",
                progress_pct(snapshot["m2_yoy"], M2_WARNING),
                "Liquidity expansion" if m2_triggered else "Below warning",
                "warning" if m2_triggered else "normal",
            ),
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div class="ask-bar">Sequence to watch: new Fed leadership → aggressive rate-cut signals → TIPS real yield trends toward zero → breakevens above 3% → real policy rate negative.</div>',
        unsafe_allow_html=True,
    )

with stress_tab:
    st.markdown(
        f'<div class="small-muted">Updated {fmt_dt(snapshot["fetched_at"])} · market date {fmt_day(snapshot["market_date"])}</div>',
        unsafe_allow_html=True,
    )
    st.write("")

    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(signal_card_1_html(snapshot["yield_value"], snapshot["yield_streak"], yield_triggered), unsafe_allow_html=True)

    with c2:
        st.markdown(signal_card_2_html(snapshot["kre_value"], kre_baseline, kre_triggered), unsafe_allow_html=True)

    with c3:
        st.markdown(signal_card_3_html(snapshot["credit_value"], snapshot["hy_value"], snapshot["ig_value"], credit_triggered), unsafe_allow_html=True)

    level_color = "#78be20" if signals_triggered == 0 else ("#c6d930" if signals_triggered == 1 else ("#f5a524" if signals_triggered == 2 else "#ff6b6b"))

    st.markdown(
        f"""
        <div class="status-panel">
            <div class="status-title">Overall systemic stress status</div>
            <div class="status-grid">
                <div>
                    <div class="status-value">{signals_triggered}/3</div>
                    <div class="status-label">Signals triggered</div>
                </div>
                <div>
                    <div class="status-value" style="color:{level_color};">{overall_stress}</div>
                    <div class="status-label">Stress level</div>
                </div>
                <div>
                    <div class="status-value">{fmt_day(snapshot['market_date'])}</div>
                    <div class="status-label">Last updated</div>
                </div>
                <div>
                    <div class="status-value">{snapshot['yield_streak']}/3</div>
                    <div class="status-label">10Y streak</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with repression_tab:
    st.markdown(
        f'<div class="small-muted">Updated {fmt_dt(snapshot["fetched_at"])} · market date {fmt_day(snapshot["market_date"])}</div>',
        unsafe_allow_html=True,
    )
    st.write("")

    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(
            metric_card_html(
                "Signal 1 — Real Yield",
                "10Y TIPS real yield",
                f"{snapshot['tips_value']:.2f}%",
                "Falls toward zero when real returns are suppressed",
                "Early / active",
                f"≤ {TIPS_EARLY_WARNING:.1f}% / ≤ {TIPS_REPRESSION_WARNING:.1f}%",
                inverse_progress_pct(snapshot["tips_value"], 2.5, 0.0),
                "Real yield suppression" if tips_triggered else ("Early warning" if tips_warning else "No suppression yet"),
                "danger" if tips_triggered else ("warning" if tips_warning else "normal"),
            ),
            unsafe_allow_html=True,
        )

    with c2:
        st.markdown(
            metric_card_html(
                "Signal 2 — Inflation Expectations",
                "10Y breakeven",
                f"{snapshot['breakeven_value']:.2f}%",
                "Breakevens rising above 3% show inflation pressure",
                "Alert threshold",
                f"≥ {BREAKEVEN_WARNING:.1f}%",
                progress_pct(snapshot["breakeven_value"], BREAKEVEN_WARNING),
                "Inflation expectations alert" if breakeven_triggered else "Below alert",
                "danger" if breakeven_triggered else "normal",
            ),
            unsafe_allow_html=True,
        )

    with c3:
        st.markdown(
            metric_card_html(
                "Signal 3 — Real Policy Rate",
                "Fed Funds − CPI",
                f"{snapshot['real_policy_rate']:.2f}%",
                f"Fed Funds {snapshot['fed_funds_value']:.2f}% minus CPI YoY {snapshot['cpi_yoy']:.2f}%",
                "Repression threshold",
                "< 0.0%",
                inverse_progress_pct(snapshot["real_policy_rate"], 3.0, 0.0),
                "Negative real policy rate" if real_policy_triggered else "Positive real policy rate",
                "danger" if real_policy_triggered else "normal",
            ),
            unsafe_allow_html=True,
        )

    c4, c5, c6 = st.columns(3)

    with c4:
        st.markdown(
            metric_card_html(
                "Signal 4 — CPI",
                "CPI YoY",
                f"{snapshot['cpi_yoy']:.2f}%",
                "Inflation pressure relative to policy rates",
                "Watch zone",
                "≥ Fed Funds",
                progress_pct(snapshot["cpi_yoy"], max(snapshot["fed_funds_value"], 0.1)),
                "CPI above Fed Funds" if snapshot["cpi_yoy"] > snapshot["fed_funds_value"] else "CPI below Fed Funds",
                "warning" if snapshot["cpi_yoy"] > snapshot["fed_funds_value"] else "normal",
            ),
            unsafe_allow_html=True,
        )

    with c5:
        st.markdown(
            metric_card_html(
                "Signal 5 — Fed Funds",
                "Fed Funds rate",
                f"{snapshot['fed_funds_value']:.2f}%",
                "Policy rate side of repression equation",
                "Compare against CPI",
                f"CPI {snapshot['cpi_yoy']:.2f}%",
                progress_pct(snapshot["fed_funds_value"], max(snapshot["cpi_yoy"], 0.1)),
                "Policy below inflation" if snapshot["fed_funds_value"] < snapshot["cpi_yoy"] else "Policy above inflation",
                "danger" if snapshot["fed_funds_value"] < snapshot["cpi_yoy"] else "normal",
            ),
            unsafe_allow_html=True,
        )

    with c6:
        st.markdown(
            metric_card_html(
                "Signal 6 — Money Supply",
                "M2 YoY",
                f"{snapshot['m2_yoy']:.2f}%",
                "Liquidity growth can support monetization/repression",
                "Warning threshold",
                f"≥ {M2_WARNING:.1f}%",
                progress_pct(snapshot["m2_yoy"], M2_WARNING),
                "Liquidity expansion warning" if m2_triggered else "Below warning",
                "warning" if m2_triggered else "normal",
            ),
            unsafe_allow_html=True,
        )

    rep_color = "#78be20" if repression_score <= 1 else ("#f5a524" if repression_score <= 3 else "#ff6b6b")

    st.markdown(
        f"""
        <div class="status-panel">
            <div class="status-title">Financial repression activation sequence</div>
            <div class="status-grid">
                <div>
                    <div class="status-value">{repression_score}/4</div>
                    <div class="status-label">Repression signals</div>
                </div>
                <div>
                    <div class="status-value" style="color:{rep_color};">{overall_repression}</div>
                    <div class="status-label">Repression risk</div>
                </div>
                <div>
                    <div class="status-value">{activation_stage}</div>
                    <div class="status-label">Activation stage</div>
                </div>
                <div>
                    <div class="status-value">{snapshot['tips_value']:.2f}%</div>
                    <div class="status-label">10Y TIPS real yield</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        ### What this tab is watching

        Financial repression is most visible when **real returns are being suppressed**. The strongest activation sequence is:

        **TIPS real yield trends toward zero → breakeven inflation rises above 3% → real policy rate turns negative.**
        """
    )

with data_tab:
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
            {"Metric": "10Y TIPS real yield", "Value": f"{snapshot['tips_value']:.2f}%", "Market date": fmt_day(snapshot["tips_date"])},
            {"Metric": "10Y breakeven inflation", "Value": f"{snapshot['breakeven_value']:.2f}%", "Market date": fmt_day(snapshot["breakeven_date"])},
            {"Metric": "Fed Funds", "Value": f"{snapshot['fed_funds_value']:.2f}%", "Market date": fmt_day(snapshot["fed_funds_date"])},
            {"Metric": "CPI YoY", "Value": f"{snapshot['cpi_yoy']:.2f}%", "Market date": fmt_day(snapshot["cpi_date"])},
            {"Metric": "Real policy rate", "Value": f"{snapshot['real_policy_rate']:.2f}%", "Market date": fmt_day(snapshot["cpi_date"])},
            {"Metric": "M2 YoY", "Value": f"{snapshot['m2_yoy']:.2f}%", "Market date": fmt_day(snapshot["m2_date"])},
        ]
    )

    st.dataframe(live_df, use_container_width=True, hide_index=True)

with guide_tab:
    st.subheader("Signal guide")

    st.markdown(
        f"""
        ### Systemic stress dashboard

        **10-year Treasury yield**  
        Triggers when the 10-year Treasury yield is above **{TREASURY_THRESHOLD:.0f}%** for **{TREASURY_STREAK_TRIGGER} consecutive trading days**.

        **Regional banks**  
        Triggers when **KRE is down 30% or more** from your selected baseline.

        **Credit spreads**  
        Triggers when the **high-yield minus investment-grade spread reaches {CREDIT_THRESHOLD:.0f}% or higher**.

        ---

        ### Financial repression dashboard

        **10Y TIPS real yield**  
        This is the most important repression metric. Watch for movement toward zero.

        **10Y breakeven inflation**  
        A move above **{BREAKEVEN_WARNING:.0f}%** signals inflation expectations are rising.

        **Real policy rate**  
        Fed Funds minus CPI YoY. A negative reading means policy rates are below inflation.

        **M2 YoY**  
        A strong rise in money supply can indicate liquidity expansion.

        ---

        ### Data sources

        - FRED `{YIELD_SERIES}` — 10Y Treasury yield
        - FRED `{TIPS_SERIES}` — 10Y TIPS real yield
        - FRED `{BREAKEVEN_SERIES}` — 10Y breakeven inflation
        - FRED `{FED_FUNDS_SERIES}` — Fed Funds
        - FRED `{CPI_SERIES}` — CPI
        - FRED `{M2_SERIES}` — M2 money supply
        - FRED `{HY_SERIES}` — High-yield spread
        - FRED `{IG_SERIES}` — Investment-grade spread
        - Yahoo Finance `KRE` — Regional bank ETF
        """
    )

    st.markdown(
        """
        ### Streamlit deployment checklist

        1. Save this file as `app.py`.
        2. Keep `requirements.txt` in the same folder.
        3. Add this to Streamlit Secrets:

        ```toml
        FRED_API_KEY = "your_real_key_here"
        ```

        4. Reboot the Streamlit app.
        """
    )
