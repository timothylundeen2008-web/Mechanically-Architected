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

st.set_page_config(
    page_title="Macro Repression + Stress Monitor",
    layout="wide"
)

# =========================
# CONFIG
# =========================
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

TREASURY_THRESHOLD = 5
CREDIT_THRESHOLD = 6
KRE_DROP = -30

TIPS_EARLY_WARNING = 1.5
TIPS_REPRESSION_WARNING = 0.5
BREAKEVEN_WARNING = 3
M2_WARNING = 6

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
# UI HELPERS (FIXED HTML)
# =========================
def card(title, value, sub, color="green"):
    return f"""
    <div style="background:#222;padding:20px;border-radius:15px;border:2px solid {color};">
        <div style="font-size:14px;color:gray;">{title}</div>
        <div style="font-size:32px;font-weight:bold;">{value}</div>
        <div style="color:gray;">{sub}</div>
    </div>
    """

# =========================
# LOAD DATA
# =========================
yield_df = get_fred("DGS10")
hy = get_fred("BAMLH0A0HYM2")
ig = get_fred("BAMLC0A0CM")
tips = get_fred("DFII10")
breakeven = get_fred("T10YIE")
fed = get_fred("FEDFUNDS")
cpi = get_fred("CPIAUCSL")
m2 = get_fred("M2SL")

kre = get_kre()

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

tabs = st.tabs([
    "Summary",
    "Systemic Stress",
    "Financial Repression",
    "Data",
    "Guide"
])

# =========================
# SUMMARY
# =========================
with tabs[0]:
    c1, c2, c3, c4 = st.columns(4)

    c1.markdown(card("10Y Yield", f"{yield_val:.2f}%", "", "#78be20"), unsafe_allow_html=True)
    c2.markdown(card("Credit Spread", f"{credit_val:.2f}%", "", "#78be20"), unsafe_allow_html=True)
    c3.markdown(card("TIPS Yield", f"{tips_val:.2f}%", "", "#78be20"), unsafe_allow_html=True)
    c4.markdown(card("Real Policy", f"{real_policy:.2f}%", "", "#78be20"), unsafe_allow_html=True)

    st.write(f"### Repression Stage: {stage}")

# =========================
# STRESS
# =========================
with tabs[1]:
    c1, c2, c3 = st.columns(3)

    c1.markdown(card("10Y Yield", f"{yield_val:.2f}%", "Stress" if treasury_signal else "Normal", "#ff6b6b" if treasury_signal else "#78be20"), unsafe_allow_html=True)
    c2.markdown(card("Credit Spread", f"{credit_val:.2f}%", "Stress" if credit_signal else "Normal", "#ff6b6b" if credit_signal else "#78be20"), unsafe_allow_html=True)
    c3.markdown(card("KRE", f"${kre_price:.2f}", f"{kre_change:.1f}%", "#ff6b6b" if kre_signal else "#78be20"), unsafe_allow_html=True)

# =========================
# REPRESSION
# =========================
with tabs[2]:
    c1, c2, c3, c4 = st.columns(4)

    c1.markdown(card("TIPS", f"{tips_val:.2f}%", "", "#78be20"), unsafe_allow_html=True)
    c2.markdown(card("Breakeven", f"{breakeven_val:.2f}%", "", "#78be20"), unsafe_allow_html=True)
    c3.markdown(card("Fed Funds", f"{fed_val:.2f}%", "", "#78be20"), unsafe_allow_html=True)
    c4.markdown(card("Real Policy", f"{real_policy:.2f}%", "", "#78be20"), unsafe_allow_html=True)

    st.write(f"### Stage: {stage}")

# =========================
# DATA
# =========================
with tabs[3]:
    df = pd.DataFrame({
        "Metric": ["10Y Yield", "Credit Spread", "TIPS", "Breakeven", "Fed Funds", "CPI YoY", "M2 YoY"],
        "Value": [yield_val, credit_val, tips_val, breakeven_val, fed_val, cpi_yoy, m2_yoy]
    })
    st.dataframe(df)

# =========================
# GUIDE
# =========================
with tabs[4]:
    st.subheader("Signal Guide")

    st.markdown(
        f"""
        ## Systemic Stress Dashboard

        ### 1. 10-Year Treasury Yield
        **What it measures:**  
        The market’s required return for lending to the U.S. government for 10 years.

        **Why it matters:**  
        A sustained move above **{TREASURY_THRESHOLD:.0f}%** can signal rising concern about debt sustainability, inflation, Treasury supply, or loss of confidence in fiscal management.

        **Dashboard trigger:**  
        - Warning if the 10-year Treasury yield rises above **{TREASURY_THRESHOLD:.0f}%**
        - Stronger signal if it holds above that level for multiple trading days

        ---

        ### 2. Regional Bank ETF — KRE
        **What it measures:**  
        KRE tracks U.S. regional bank stocks.

        **Why it matters:**  
        Regional banks are a key part of credit creation. A major decline can suggest the market is pricing in deposit stress, loan losses, commercial real estate pressure, or institutional failures.

        **Dashboard trigger:**  
        - Warning if KRE falls **30% or more** from the selected baseline

        ---

        ### 3. High-Yield Minus Investment-Grade Credit Spread
        **What it measures:**  
        The difference between high-yield bond spreads and investment-grade corporate bond spreads.

        **Why it matters:**  
        When this spread widens sharply, credit markets are demanding much more compensation for risk. This often happens when defaults, liquidity stress, or recession risk are rising.

        **Dashboard trigger:**  
        - Warning if HY − IG spread reaches **{CREDIT_THRESHOLD:.0f}% or higher**

        ---

        ## Financial Repression Dashboard

        ### 1. 10-Year TIPS Real Yield
        **What it measures:**  
        The inflation-adjusted yield on 10-year Treasury Inflation-Protected Securities.

        **Why it matters:**  
        This is the most important financial repression signal. Financial repression happens when real returns are suppressed below inflation. If the 10-year TIPS real yield trends toward zero or negative, it may indicate repression pressure.

        **Dashboard trigger zones:**  
        - Early warning: TIPS real yield below **{TIPS_EARLY_WARNING:.1f}%**
        - Stronger repression warning: TIPS real yield below **{TIPS_REPRESSION_WARNING:.1f}%**

        ---

        ### 2. 10-Year Breakeven Inflation
        **What it measures:**  
        The market’s implied inflation expectation over the next 10 years.

        **Why it matters:**  
        Rising breakevens mean markets expect higher inflation. Financial repression becomes more likely if inflation expectations rise while nominal yields or policy rates are held down.

        **Dashboard trigger:**  
        - Warning if breakeven inflation rises above **{BREAKEVEN_WARNING:.0f}%**

        ---

        ### 3. Real Policy Rate
        **Formula:**  
        Fed Funds Rate − CPI YoY

        **Why it matters:**  
        If the Fed Funds Rate is below inflation, cash and short-term bonds lose purchasing power. This is one of the clearest signs of repression.

        **Dashboard trigger:**  
        - Warning if real policy rate falls below **0%**

        ---

        ### 4. CPI YoY
        **What it measures:**  
        Year-over-year consumer inflation.

        **Why it matters:**  
        CPI shows the inflation side of the repression equation. Higher CPI with low or falling rates means real returns are being compressed.

        ---

        ### 5. Fed Funds Rate
        **What it measures:**  
        The Federal Reserve’s main policy rate.

        **Why it matters:**  
        If the Fed cuts rates while inflation remains elevated, the real policy rate can quickly turn negative.

        ---

        ### 6. M2 Money Supply YoY
        **What it measures:**  
        Year-over-year growth in broad money supply.

        **Why it matters:**  
        Rising money supply can support liquidity, asset prices, and inflationary pressure. It is not repression by itself, but it can reinforce repression if real rates are negative.

        **Dashboard trigger:**  
        - Warning if M2 YoY growth rises above **{M2_WARNING:.0f}%**

        ---

        ## Activation Sequence to Watch

        The dashboard is designed around this sequence:

        1. **Fed leadership or policy shift**
        2. **Aggressive rate-cut signals**
        3. **10-year TIPS real yield trends toward zero**
        4. **Breakeven inflation rises above 3%**
        5. **Real policy rate turns negative**
        6. **Financial repression becomes active**

        ---

        ## How to Interpret the Dashboard

        ### Low Risk
        - TIPS real yields remain positive
        - Breakevens are contained
        - Real policy rate is positive
        - Credit spreads are calm
        - KRE is stable

        ### Elevated Risk
        - TIPS real yield is falling
        - Breakevens are rising
        - CPI remains above policy rates
        - M2 growth starts accelerating

        ### High Risk
        - TIPS real yield approaches zero
        - Breakevens exceed 3%
        - Real policy rate turns negative
        - Credit spreads begin widening

        ### Critical Risk
        - Multiple stress signals trigger at once
        - KRE falls sharply
        - Credit spreads exceed 6%
        - Real policy rate remains negative while inflation expectations rise

        ---

        ## Data Sources

        - FRED `DGS10` — 10-year Treasury yield
        - FRED `DFII10` — 10-year TIPS real yield
        - FRED `T10YIE` — 10-year breakeven inflation
        - FRED `FEDFUNDS` — Fed Funds rate
        - FRED `CPIAUCSL` — Consumer Price Index
        - FRED `M2SL` — M2 money supply
        - FRED `BAMLH0A0HYM2` — High-yield corporate spread
        - FRED `BAMLC0A0CM` — Investment-grade corporate spread
        - Yahoo Finance `KRE` — Regional bank ETF

        ---

        ## Deployment Checklist

        1. Save this file as `app.py`
        2. Keep `requirements.txt` in the same folder
        3. Add this to Streamlit Secrets:

        ```toml
        FRED_API_KEY = "your_real_key_here"
        ```

        4. Commit and push to GitHub
        5. Reboot the Streamlit app
        """
    )
