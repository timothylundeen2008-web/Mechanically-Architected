import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

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

# -----------------------------
# API KEY HANDLING
# -----------------------------
# Preferred deployment options:
# 1) Streamlit Cloud secrets: FRED_API_KEY="your_real_key"
# 2) Local env var: export FRED_API_KEY="your_real_key"
# 3) Local .streamlit/secrets.toml: FRED_API_KEY="your_real_key"
# Do not commit your real key to GitHub.

def get_fred_api_key() -> Optional[str]:
    try:
        key = st.secrets.get("FRED_API_KEY", None)
        if key:
            return str(key).strip()
    except Exception:
        pass
    key = os.getenv("FRED_API_KEY")
    return key.strip() if key else None

FRED_API_KEY = get_fred_api_key()
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
DEFAULT_TIMEOUT = 30

# -----------------------------
# SERIES CONSTANTS
# -----------------------------
YIELD_SERIES = "DGS10"          # 10-Year Treasury Constant Maturity Rate
HY_SERIES = "BAMLH0A0HYM2"      # ICE BofA US High Yield OAS
IG_SERIES = "BAMLC0A0CM"        # ICE BofA US Corporate OAS
CPI_SERIES = "CPIAUCSL"         # CPI Index
FEDFUNDS_SERIES = "FEDFUNDS"    # Effective Fed Funds Rate, monthly
BREAKEVEN_10Y_SERIES = "T10YIE" # 10-Year Breakeven Inflation Rate
REAL_10Y_SERIES = "DFII10"      # 10-Year TIPS real yield
M2_SERIES = "M2SL"              # M2 Money Supply

TREASURY_THRESHOLD = 5.0
TREASURY_STREAK_TRIGGER = 3
CREDIT_THRESHOLD = 6.0
KRE_ALERT_DECLINE = -30.0
KRE_BASELINE_DEFAULT = 52.0
NEGATIVE_REAL_RATE_TRIGGER = 0.0
CPI_OVER_FEDFUNDS_TRIGGER = 1.0
M2_GROWTH_TRIGGER = 6.0

# -----------------------------
# CSS
# -----------------------------
st.markdown("""
<style>
.stApp { background:#111111; color:#f4f4ef; }
.block-container { padding-top:1.5rem; padding-bottom:3rem; max-width:1250px; }
[data-testid="stHeader"] { background:transparent; }
.card { background:linear-gradient(180deg,#262626 0%,#202020 100%); border:1.5px solid #78be20; border-radius:18px; padding:1.15rem 1.25rem; min-height:245px; box-shadow:0 0 0 1px rgba(120,190,32,.08); }
.card-red { border-color:#ff6b6b; }
.eyebrow { color:#aaa; font-size:.82rem; letter-spacing:.05em; text-transform:uppercase; font-weight:700; }
.name { font-size:1.35rem; font-weight:700; margin:.1rem 0 .55rem 0; color:#f4f4ef; }
.value { font-size:2.65rem; font-weight:800; line-height:1; color:#f4f4ef; }
.sub { color:#b8b8b0; font-size:.94rem; min-height:2rem; margin-top:.45rem; }
.pill { display:inline-block; background:#e9efd7; color:#527d1a; border-radius:12px; padding:.34rem .65rem; font-size:.88rem; font-weight:800; margin-top:.7rem; }
.pill-red { background:#341616; color:#ffb4b4; }
.pill-yellow { background:#312914; color:#ffd37b; }
.status-panel { background:#1c1c1c; border-radius:18px; padding:1.2rem 1.4rem; margin:1rem 0; }
.small-muted { color:#b8b8b0; font-size:.9rem; }
hr { border-color:#333; }
</style>
""", unsafe_allow_html=True)

# -----------------------------
# HELPERS
# -----------------------------
def fmt_dt(dt) -> str:
    if not dt:
        return "—"
    return pd.Timestamp(dt).strftime("%b %d, %Y")


def fred_observations(series_id: str, days: int = 365 * 3) -> pd.DataFrame:
    params = {
        "series_id": series_id,
        "file_type": "json",
        "sort_order": "asc",
        "observation_start": (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d"),
    }
    if FRED_API_KEY:
        params["api_key"] = FRED_API_KEY

    r = requests.get(FRED_BASE, params=params, timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()
    obs = r.json().get("observations", [])
    df = pd.DataFrame(obs)
    if df.empty:
        raise ValueError(f"No FRED data returned for {series_id}")
    df = df[["date", "value"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"].replace(".", pd.NA), errors="coerce")
    return df.dropna(subset=["value"]).reset_index(drop=True)


def fetch_kre_history() -> pd.DataFrame:
    if yf is None:
        raise ImportError("yfinance is not installed. Add yfinance to requirements.txt.")
    hist = yf.Ticker("KRE").history(period="1y", interval="1d", auto_adjust=False)
    if hist.empty:
        raise ValueError("No KRE history returned.")
    hist = hist.reset_index()
    date_col = "Date" if "Date" in hist.columns else hist.columns[0]
    hist[date_col] = pd.to_datetime(hist[date_col]).dt.tz_localize(None)
    out = hist[[date_col, "Close"]].rename(columns={date_col: "date", "Close": "close"})
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    return out.dropna().reset_index(drop=True)


def latest_business_days_streak(values: pd.Series, threshold: float) -> int:
    streak = 0
    for val in values.dropna().sort_index(ascending=False):
        if float(val) > threshold:
            streak += 1
        else:
            break
    return streak


def yoy_change(df: pd.DataFrame) -> Optional[float]:
    if len(df) < 13:
        return None
    latest = float(df.iloc[-1]["value"])
    prior_date = df.iloc[-1]["date"] - pd.DateOffset(years=1)
    prior_rows = df[df["date"] <= prior_date]
    if prior_rows.empty:
        return None
    prior = float(prior_rows.iloc[-1]["value"])
    return ((latest / prior) - 1) * 100


def card(title: str, name: str, value: str, sub: str, status: str, triggered: bool = False, warn: bool = False):
    klass = "card card-red" if triggered else "card"
    pill = "pill-red" if triggered else ("pill-yellow" if warn else "")
    st.markdown(f"""
    <div class=\"{klass}\">
        <div class=\"eyebrow\">{title}</div>
        <div class=\"name\">{name}</div>
        <div class=\"value\">{value}</div>
        <div class=\"sub\">{sub}</div>
        <span class=\"pill {pill}\">{status}</span>
    </div>
    """, unsafe_allow_html=True)


def level_from_count(n: int, total: int) -> str:
    if n == 0:
        return "LOW"
    if n == 1:
        return "ELEVATED"
    if n < total:
        return "HIGH"
    return "CRITICAL"


@st.cache_data(ttl="1d", show_spinner=False)
def load_snapshot(refresh_nonce: int) -> Dict:
    _ = refresh_nonce
    dgs10 = fred_observations(YIELD_SERIES, 365)
    hy = fred_observations(HY_SERIES, 365)
    ig = fred_observations(IG_SERIES, 365)
    cpi = fred_observations(CPI_SERIES, 365 * 3)
    fed = fred_observations(FEDFUNDS_SERIES, 365 * 3)
    breakeven = fred_observations(BREAKEVEN_10Y_SERIES, 365)
    real10 = fred_observations(REAL_10Y_SERIES, 365)
    m2 = fred_observations(M2_SERIES, 365 * 3)
    kre = fetch_kre_history()

    credit = hy.merge(ig, on="date", how="inner", suffixes=("_hy", "_ig"))
    credit["spread"] = credit["value_hy"] - credit["value_ig"]

    cpi_yoy = yoy_change(cpi)
    m2_yoy = yoy_change(m2)
    fed_latest = float(fed.iloc[-1]["value"])
    real_rate_proxy = float(dgs10.iloc[-1]["value"]) - (cpi_yoy or 0)
    policy_gap = (cpi_yoy or 0) - fed_latest

    return {
        "fetched_at": datetime.now(timezone.utc),
        "dgs10": dgs10,
        "credit": credit,
        "kre": kre,
        "cpi": cpi,
        "fed": fed,
        "breakeven": breakeven,
        "real10": real10,
        "m2": m2,
        "yield_value": float(dgs10.iloc[-1]["value"]),
        "yield_date": dgs10.iloc[-1]["date"],
        "yield_streak": latest_business_days_streak(dgs10.set_index("date")["value"], TREASURY_THRESHOLD),
        "credit_value": float(credit.iloc[-1]["spread"]),
        "hy_value": float(credit.iloc[-1]["value_hy"]),
        "ig_value": float(credit.iloc[-1]["value_ig"]),
        "credit_date": credit.iloc[-1]["date"],
        "kre_value": float(kre.iloc[-1]["close"]),
        "kre_date": kre.iloc[-1]["date"],
        "cpi_yoy": cpi_yoy,
        "fedfunds": fed_latest,
        "policy_gap": policy_gap,
        "breakeven10": float(breakeven.iloc[-1]["value"]),
        "real10": float(real10.iloc[-1]["value"]),
        "real_rate_proxy": real_rate_proxy,
        "m2_yoy": m2_yoy,
        "market_date": max(dgs10.iloc[-1]["date"], credit.iloc[-1]["date"], kre.iloc[-1]["date"]),
    }

# -----------------------------
# APP STATE
# -----------------------------
if "manual_refresh_nonce" not in st.session_state:
    st.session_state.manual_refresh_nonce = 0
if "kre_baseline" not in st.session_state:
    st.session_state.kre_baseline = KRE_BASELINE_DEFAULT

# -----------------------------
# HEADER
# -----------------------------
left, right = st.columns([5, 1.3])
with left:
    st.markdown('<div style="font-size:2rem;font-weight:800;">Macro repression + systemic stress monitor</div>', unsafe_allow_html=True)
    st.markdown('<div class="small-muted">One Streamlit dashboard for slow-burn financial repression signals and market-breakage stress signals.</div>', unsafe_allow_html=True)
with right:
    if st.button("Recalculate", use_container_width=True):
        st.session_state.manual_refresh_nonce += 1
        st.cache_data.clear()
        st.rerun()

if not FRED_API_KEY:
    st.warning("FRED_API_KEY was not found. Add it to Streamlit Secrets or your local environment for reliable API access.")

try:
    snapshot = load_snapshot(st.session_state.manual_refresh_nonce)
    st.session_state["last_good_snapshot"] = snapshot
except Exception as exc:
    snapshot = st.session_state.get("last_good_snapshot")
    if snapshot is None:
        st.error(f"Live data failed and no cached snapshot exists: {exc}")
        st.stop()
    st.warning(f"Live data failed. Showing last good cached data instead: {exc}")

# -----------------------------
# DERIVED SIGNALS
# -----------------------------
kre_baseline = float(st.session_state.kre_baseline)
kre_decline_pct = ((snapshot["kre_value"] / kre_baseline) - 1.0) * 100.0

yield_triggered = snapshot["yield_value"] > TREASURY_THRESHOLD and snapshot["yield_streak"] >= TREASURY_STREAK_TRIGGER
kre_triggered = kre_decline_pct <= KRE_ALERT_DECLINE
credit_triggered = snapshot["credit_value"] >= CREDIT_THRESHOLD
stress_count = int(yield_triggered) + int(kre_triggered) + int(credit_triggered)

real_rate_triggered = snapshot["real_rate_proxy"] < NEGATIVE_REAL_RATE_TRIGGER
policy_gap_triggered = snapshot["policy_gap"] >= CPI_OVER_FEDFUNDS_TRIGGER
m2_triggered = snapshot["m2_yoy"] is not None and snapshot["m2_yoy"] >= M2_GROWTH_TRIGGER
repression_count = int(real_rate_triggered) + int(policy_gap_triggered) + int(m2_triggered)

# -----------------------------
# TABS
# -----------------------------
summary_tab, repression_tab, stress_tab, charts_tab, settings_tab, guide_tab = st.tabs([
    "Signal Summary", "Financial Repression", "Systemic Stress", "Charts", "Settings", "Guide"
])

with summary_tab:
    st.markdown(f'<div class="small-muted">Updated {fmt_dt(snapshot["fetched_at"])} · latest market date {fmt_dt(snapshot["market_date"])}</div>', unsafe_allow_html=True)
    st.write("")
    a, b, c = st.columns(3)
    with a:
        card("Combined", "Financial repression", f"{repression_count}/3", "Negative real rates, CPI above Fed Funds, and excess money growth.", level_from_count(repression_count, 3), triggered=repression_count >= 2, warn=repression_count == 1)
    with b:
        card("Combined", "Systemic stress", f"{stress_count}/3", "Treasury, regional bank, and credit spread breakage signals.", level_from_count(stress_count, 3), triggered=stress_count >= 2, warn=stress_count == 1)
    with c:
        total = repression_count + stress_count
        card("Overall", "Macro regime risk", f"{total}/6", "Best interpreted as a dashboard, not a trading signal by itself.", level_from_count(total, 6), triggered=total >= 4, warn=total in [2, 3])

    st.markdown("### Current readings")
    rows = [
        ["10Y Treasury", f'{snapshot["yield_value"]:.2f}%', f'>{TREASURY_THRESHOLD:.0f}% for {TREASURY_STREAK_TRIGGER} trading days', "TRIGGERED" if yield_triggered else "OK"],
        ["KRE decline", f'{kre_decline_pct:.1f}%', "-30% from baseline", "TRIGGERED" if kre_triggered else "OK"],
        ["HY minus IG spread", f'{snapshot["credit_value"]:.2f}%', f'>= {CREDIT_THRESHOLD:.0f}%', "TRIGGERED" if credit_triggered else "OK"],
        ["10Y minus CPI proxy", f'{snapshot["real_rate_proxy"]:.2f}%', "Below 0%", "TRIGGERED" if real_rate_triggered else "OK"],
        ["CPI minus Fed Funds", f'{snapshot["policy_gap"]:.2f}%', ">= 1%", "TRIGGERED" if policy_gap_triggered else "OK"],
        ["M2 YoY", "—" if snapshot["m2_yoy"] is None else f'{snapshot["m2_yoy"]:.2f}%', f'>= {M2_GROWTH_TRIGGER:.0f}%', "TRIGGERED" if m2_triggered else "OK"],
    ]
    st.dataframe(pd.DataFrame(rows, columns=["Metric", "Current", "Trigger", "Status"]), use_container_width=True, hide_index=True)

with repression_tab:
    st.subheader("Financial Repression Monitor")
    a, b, c = st.columns(3)
    with a:
        card("Repression 1", "Real rate proxy", f'{snapshot["real_rate_proxy"]:.2f}%', f'10Y Treasury minus CPI YoY. CPI YoY: {snapshot["cpi_yoy"]:.2f}%.' if snapshot["cpi_yoy"] is not None else "CPI YoY unavailable.", "Negative real rate" if real_rate_triggered else "Positive real rate", triggered=real_rate_triggered)
    with b:
        card("Repression 2", "CPI vs Fed Funds", f'{snapshot["policy_gap"]:.2f}%', f'CPI YoY minus Fed Funds. Fed Funds: {snapshot["fedfunds"]:.2f}%.' if snapshot["cpi_yoy"] is not None else "Policy gap unavailable.", "Inflation above policy" if policy_gap_triggered else "Policy restrictive/neutral", triggered=policy_gap_triggered)
    with c:
        m2_text = "—" if snapshot["m2_yoy"] is None else f'{snapshot["m2_yoy"]:.2f}%'
        card("Repression 3", "M2 money growth", m2_text, "Year-over-year M2 growth. High liquidity with controlled yields supports repression risk.", "Liquidity expansion" if m2_triggered else "Not triggered", triggered=m2_triggered)

    st.markdown("### Extra context")
    a, b = st.columns(2)
    with a:
        card("Market-implied", "10Y breakeven inflation", f'{snapshot["breakeven10"]:.2f}%', "Inflation expectations from Treasury/TIPS market.", "Context")
    with b:
        card("Market-implied", "10Y TIPS real yield", f'{snapshot["real10"]:.2f}%', "Direct market-based real yield from TIPS.", "Context", triggered=snapshot["real10"] < 0)

with stress_tab:
    st.subheader("Systemic Stress Monitor")
    a, b, c = st.columns(3)
    with a:
        card("Stress 1", "10Y Treasury yield", f'{snapshot["yield_value"]:.2f}%', f'{snapshot["yield_streak"]}/{TREASURY_STREAK_TRIGGER} consecutive trading days above {TREASURY_THRESHOLD:.0f}%.', "Treasury stress" if yield_triggered else "Below trigger", triggered=yield_triggered)
    with b:
        card("Stress 2", "KRE regional banks", f'${snapshot["kre_value"]:.2f}', f'{kre_decline_pct:.1f}% from baseline ${kre_baseline:.2f}. Trigger is -30%.', "Bank signal" if kre_triggered else "Below trigger", triggered=kre_triggered)
    with c:
        card("Stress 3", "HY − IG spread", f'{snapshot["credit_value"]:.2f}%', f'HY OAS {snapshot["hy_value"]:.2f}% minus IG OAS {snapshot["ig_value"]:.2f}%.', "Credit seizure risk" if credit_triggered else "Below trigger", triggered=credit_triggered)

with charts_tab:
    st.subheader("Historical charts")
    chart_choice = st.selectbox("Chart", ["10Y Treasury", "KRE", "HY minus IG spread", "CPI YoY", "M2 YoY", "10Y TIPS real yield"])
    if chart_choice == "10Y Treasury":
        st.line_chart(snapshot["dgs10"].set_index("date")[["value"]])
    elif chart_choice == "KRE":
        st.line_chart(snapshot["kre"].set_index("date")[["close"]])
    elif chart_choice == "HY minus IG spread":
        st.line_chart(snapshot["credit"].set_index("date")[["spread"]])
    elif chart_choice == "CPI YoY":
        cpi = snapshot["cpi"].copy()
        cpi["CPI YoY"] = cpi["value"].pct_change(12) * 100
        st.line_chart(cpi.set_index("date")[["CPI YoY"]].dropna())
    elif chart_choice == "M2 YoY":
        m2 = snapshot["m2"].copy()
        m2["M2 YoY"] = m2["value"].pct_change(12) * 100
        st.line_chart(m2.set_index("date")[["M2 YoY"]].dropna())
    else:
        st.line_chart(snapshot["real10"].set_index("date")[["value"]])

with settings_tab:
    st.subheader("Settings")
    st.session_state.kre_baseline = st.number_input(
        "KRE baseline price",
        min_value=1.0,
        value=float(st.session_state.kre_baseline),
        step=0.5,
        help="Set your reference level. A 30% decline from this level triggers the KRE stress signal.",
    )
    st.markdown("### API key status")
    st.write("FRED API key loaded:" if FRED_API_KEY else "FRED API key not loaded:", "✅" if FRED_API_KEY else "❌")
    st.code('FRED_API_KEY="your_real_fred_key_here"', language="toml")
    st.caption("For Streamlit Cloud: App → Settings → Secrets. For local: create .streamlit/secrets.toml or set an environment variable.")

with guide_tab:
    st.subheader("Signal guide")
    st.markdown(f"""
**Financial repression signals**

1. **Real rate proxy below 0%**: 10Y Treasury yield minus CPI YoY is negative. This means inflation is running above nominal long-term Treasury compensation.
2. **CPI above Fed Funds by 1% or more**: policy is still behind inflation.
3. **M2 growth above {M2_GROWTH_TRIGGER:.0f}% YoY**: liquidity growth may support inflation or asset-price distortion.

**Systemic stress signals**

1. **10Y Treasury yield above {TREASURY_THRESHOLD:.0f}% for {TREASURY_STREAK_TRIGGER} consecutive trading days**.
2. **KRE down 30% or more from your baseline**.
3. **High-yield OAS minus investment-grade OAS above {CREDIT_THRESHOLD:.0f}%**.

**Data sources**: FRED for Treasury yields, CPI, Fed Funds, breakevens, TIPS real yields, M2, and credit spreads. Yahoo Finance/yfinance for KRE.
""")

