import time
from datetime import datetime, timedelta, timezone
from typing import Dict

import pandas as pd
import requests
import streamlit as st

try:
    import yfinance as yf
except:
    yf = None

st.set_page_config(layout="wide")

# =========================
# CONFIG
# =========================
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

SERIES = {
    "DGS10": "10Y Yield",
    "BAMLH0A0HYM2": "HY",
    "BAMLC0A0CM": "IG",
    "DFII10": "TIPS",
    "T10YIE": "Breakeven",
    "FEDFUNDS": "Fed Funds",
    "CPIAUCSL": "CPI",
    "M2SL": "M2"
}

TREASURY_THRESHOLD = 5
CREDIT_THRESHOLD = 6
KRE_DROP = -30

# =========================
# HELPERS
# =========================
def get_fred(series):
    key = st.secrets.get("FRED_API_KEY", None)
    params = {
        "series_id": series,
        "file_type": "json",
        "sort_order": "asc",
        "observation_start": (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d"),
    }
    if key:
        params["api_key"] = key

    r = requests.get(FRED_BASE, params=params)
    r.raise_for_status()

    df = pd.DataFrame(r.json()["observations"])
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna()

def get_kre():
    if yf is None:
        return None
    return yf.Ticker("KRE").history(period="6mo")

def yoy(df):
    df["yoy"] = df["value"].pct_change(12) * 100
    return df.iloc[-1]["yoy"]

# =========================
# LOAD DATA
# =========================
try:
    yield_df = get_fred("DGS10")
    hy = get_fred("BAMLH0A0HYM2")
    ig = get_fred("BAMLC0A0CM")

    tips = get_fred("DFII10")
    breakeven = get_fred("T10YIE")
    fed = get_fred("FEDFUNDS")
    cpi = get_fred("CPIAUCSL")
    m2 = get_fred("M2SL")

    kre = get_kre()

except Exception as e:
    st.error(f"Data error: {e}")
    st.stop()

# =========================
# DERIVED
# =========================
yield_val = yield_df.iloc[-1]["value"]

credit = hy.merge(ig, on="date")
credit["spread"] = credit["value_x"] - credit["value_y"]
credit_val = credit.iloc[-1]["spread"]

tips_val = tips.iloc[-1]["value"]
breakeven_val = breakeven.iloc[-1]["value"]
fed_val = fed.iloc[-1]["value"]

cpi_yoy = yoy(cpi)
m2_yoy = yoy(m2)

real_policy = fed_val - cpi_yoy

kre_price = kre["Close"].iloc[-1] if kre is not None else 50
baseline = 52
kre_change = (kre_price / baseline - 1) * 100

# =========================
# SIGNALS
# =========================
treasury_signal = yield_val > TREASURY_THRESHOLD
credit_signal = credit_val > CREDIT_THRESHOLD
kre_signal = kre_change <= KRE_DROP

# =========================
# REPRESSION LOGIC
# =========================
if tips_val > 1.5:
    stage = "LOW"
elif tips_val < 1.5:
    stage = "EARLY"
if tips_val < 0.5 and breakeven_val > 3:
    stage = "LATE"
if real_policy < 0:
    stage = "ACTIVE"

# =========================
# UI
# =========================
st.title("Macro Repression + Systemic Stress Monitor")

tabs = st.tabs(["Summary", "Stress", "Repression"])

# =========================
# SUMMARY
# =========================
with tabs[0]:
    st.subheader("Macro Summary")

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("10Y Yield", f"{yield_val:.2f}%")
    c2.metric("Credit Spread", f"{credit_val:.2f}%")
    c3.metric("TIPS Real Yield", f"{tips_val:.2f}%")
    c4.metric("Real Policy", f"{real_policy:.2f}%")

    st.write(f"Repression Stage: **{stage}**")

# =========================
# STRESS
# =========================
with tabs[1]:
    st.subheader("Systemic Stress")

    c1, c2, c3 = st.columns(3)

    c1.metric("10Y Yield", f"{yield_val:.2f}%", "Stress" if treasury_signal else "Normal")
    c2.metric("Credit Spread", f"{credit_val:.2f}%", "Stress" if credit_signal else "Normal")
    c3.metric("KRE", f"${kre_price:.2f}", f"{kre_change:.1f}%")

    if treasury_signal:
        st.error("Treasury stress triggered")
    if credit_signal:
        st.error("Credit stress triggered")
    if kre_signal:
        st.error("Banking stress triggered")

# =========================
# REPRESSION
# =========================
with tabs[2]:
    st.subheader("Financial Repression Monitor")

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("TIPS", f"{tips_val:.2f}%")
    c2.metric("Breakeven", f"{breakeven_val:.2f}%")
    c3.metric("Fed Funds", f"{fed_val:.2f}%")
    c4.metric("Real Policy", f"{real_policy:.2f}%")

    st.write(f"Stage: **{stage}**")

    st.markdown("""
    ### Activation Sequence
    - Fed shift
    - Rate cuts
    - TIPS falls
    - Breakeven rises
    - Real rates go negative
    """)
