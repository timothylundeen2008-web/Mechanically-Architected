# ================================
# EXPANDED MACRO DASHBOARD
# ================================

import pandas as pd
import requests
import streamlit as st
from datetime import datetime, timedelta, timezone

try:
    import yfinance as yf
except:
    yf = None

st.set_page_config(layout="wide")

# ================================
# CONFIG
# ================================
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

SERIES = {
    "DGS10": "10Y Yield",
    "BAMLH0A0HYM2": "HY",
    "BAMLC0A0CM": "IG",
    "DFII10": "TIPS Real Yield",
    "T10YIE": "Breakeven Inflation",
    "FEDFUNDS": "Fed Funds",
    "CPIAUCSL": "CPI"
}

TREASURY_THRESHOLD = 5
CREDIT_THRESHOLD = 6
KRE_DROP = -30

# ================================
# HELPERS
# ================================

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

    data = r.json()["observations"]
    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna()

def get_kre():
    if yf is None:
        return None
    df = yf.Ticker("KRE").history(period="6mo")
    return df

# ================================
# LOAD DATA
# ================================
try:
    yield_df = get_fred("DGS10")
    hy = get_fred("BAMLH0A0HYM2")
    ig = get_fred("BAMLC0A0CM")

    tips = get_fred("DFII10")
    breakeven = get_fred("T10YIE")
    fed = get_fred("FEDFUNDS")
    cpi = get_fred("CPIAUCSL")

    kre = get_kre()

except Exception as e:
    st.error(f"Data error: {e}")
    st.stop()

# ================================
# DERIVED
# ================================

yield_val = yield_df.iloc[-1]["value"]

credit = hy.merge(ig, on="date")
credit["spread"] = credit["value_x"] - credit["value_y"]
credit_val = credit.iloc[-1]["spread"]

tips_val = tips.iloc[-1]["value"]
breakeven_val = breakeven.iloc[-1]["value"]
fed_val = fed.iloc[-1]["value"]

# CPI YoY
cpi["yoy"] = cpi["value"].pct_change(12) * 100
cpi_yoy = cpi.iloc[-1]["yoy"]

real_policy = fed_val - cpi_yoy

# KRE
if kre is not None:
    kre_price = kre["Close"].iloc[-1]
else:
    kre_price = 50

baseline = 52
kre_change = (kre_price / baseline - 1) * 100

# ================================
# SIGNALS
# ================================

treasury_signal = yield_val > TREASURY_THRESHOLD
credit_signal = credit_val > CREDIT_THRESHOLD
kre_signal = kre_change <= KRE_DROP

# ================================
# REPRESSION LOGIC
# ================================

if tips_val > 1.5:
    stage = 0
    label = "No repression"
elif tips_val < 1.5 and tips_val > 0.5:
    stage = 1
    label = "Early shift"
elif tips_val < 0.5 and breakeven_val > 3:
    stage = 2
    label = "Inflation building"
elif real_policy < 0:
    stage = 3
    label = "Repression active"
else:
    stage = 0
    label = "Neutral"

# ================================
# UI
# ================================

tabs = st.tabs(["Systemic Stress", "Financial Repression"])

# ================================
# TAB 1: STRESS
# ================================
with tabs[0]:

    st.header("Systemic Stress Monitor")

    c1, c2, c3 = st.columns(3)

    c1.metric("10Y Yield", f"{yield_val:.2f}%", "Above 5%" if treasury_signal else "Normal")
    c2.metric("Credit Spread", f"{credit_val:.2f}%", "Stress" if credit_signal else "Normal")
    c3.metric("KRE", f"${kre_price:.2f}", f"{kre_change:.1f}%")

    if treasury_signal:
        st.error("Treasury stress signal triggered")
    if credit_signal:
        st.error("Credit stress signal triggered")
    if kre_signal:
        st.error("Banking stress signal triggered")

# ================================
# TAB 2: REPRESSION
# ================================
with tabs[1]:

    st.header("Financial Repression Monitor")

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("TIPS Real Yield", f"{tips_val:.2f}%")
    c2.metric("Breakeven Inflation", f"{breakeven_val:.2f}%")
    c3.metric("Fed Funds", f"{fed_val:.2f}%")
    c4.metric("Real Policy Rate", f"{real_policy:.2f}%")

    st.subheader("Repression Stage")
    st.write(f"Stage {stage}: {label}")

    if stage == 3:
        st.error("⚠️ Financial repression ACTIVE")
    elif stage == 2:
        st.warning("⚠️ Inflation pressure building")
    elif stage == 1:
        st.info("Early policy shift underway")
    else:
        st.success("No repression detected")

    st.markdown("""
    ### Activation Sequence
    1. Fed leadership shift
    2. Rate cuts begin
    3. TIPS yield declines
    4. Breakeven inflation rises
    5. Real rates go negative
    """)
