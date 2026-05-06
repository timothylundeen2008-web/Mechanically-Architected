"""
data_fetcher.py
================
Pulls all financial repression indicator data from FRED and Yahoo Finance.

FRED series used:
  DGS10        — 10-yr Treasury constant maturity yield
  DFII10       — 10-yr TIPS real yield (market-implied)
  T10YIE       — 10-yr breakeven inflation rate
  FEDFUNDS     — Effective federal funds rate
  CPIAUCSL     — CPI all urban consumers (for real rate calc)
  BAMLH0A0HYM2 — ICE BofA US High Yield OAS (credit spread)
  GFDEGDQ188S  — Federal debt as % of GDP (quarterly)

Yahoo Finance tickers:
  ^TNX         — 10-yr Treasury yield (real-time proxy)
  KRE          — SPDR S&P Regional Banking ETF
"""

import os
import datetime
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np

# FRED via requests (no key required for most series; key gives higher limits)
import requests

try:
    import yfinance as yf
    YFINANCE_OK = True
except ImportError:
    YFINANCE_OK = False


# ─── FRED helpers ──────────────────────────────────────────────────────────────

FRED_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FRED_API  = "https://api.stlouisfed.org/fred/series/observations"

def _fetch_fred_csv(series_id: str, start: str = "2019-01-01") -> pd.Series:
    """
    Pull a FRED series via the public CSV endpoint (no API key needed).
    Returns a pandas Series indexed by date, values as float.
    """
    url = f"{FRED_BASE}?id={series_id}"
    try:
        df = pd.read_csv(url, parse_dates=["DATE"], index_col="DATE")
        df.columns = ["value"]
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna()
        df = df[df.index >= start]
        return df["value"]
    except Exception as e:
        print(f"[FRED CSV] Failed for {series_id}: {e}")
        return pd.Series(dtype=float)


def _fetch_fred_api(series_id: str, api_key: str,
                    start: str = "2019-01-01") -> pd.Series:
    """
    Pull a FRED series via the official API (requires key, higher rate limits).
    """
    params = {
        "series_id":        series_id,
        "api_key":          api_key,
        "file_type":        "json",
        "observation_start": start,
        "sort_order":       "asc",
    }
    try:
        r = requests.get(FRED_API, params=params, timeout=10)
        r.raise_for_status()
        obs = r.json().get("observations", [])
        data = {
            pd.Timestamp(o["date"]): float(o["value"])
            for o in obs if o["value"] != "."
        }
        return pd.Series(data)
    except Exception as e:
        print(f"[FRED API] Failed for {series_id}: {e}")
        return pd.Series(dtype=float)


def fetch_fred(series_id: str, api_key: str = "",
               start: str = "2019-01-01") -> pd.Series:
    """Route to API (if key given) or public CSV."""
    if api_key:
        s = _fetch_fred_api(series_id, api_key, start)
        if len(s) > 0:
            return s
    return _fetch_fred_csv(series_id, start)


def latest(series: pd.Series) -> float | None:
    """Return most recent non-NaN value."""
    if series is None or len(series) == 0:
        return None
    return float(series.dropna().iloc[-1])


# ─── Yahoo Finance helpers ─────────────────────────────────────────────────────

def fetch_yf_series(ticker: str, period: str = "5y",
                    interval: str = "1d") -> pd.Series:
    """Download Yahoo Finance OHLCV and return Close as a Series."""
    if not YFINANCE_OK:
        return pd.Series(dtype=float)
    try:
        data = yf.download(ticker, period=period, interval=interval,
                           auto_adjust=True, progress=False)
        if data is None or data.empty:
            return pd.Series(dtype=float)
        close = data["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        close = close.dropna()
        close.index = pd.to_datetime(close.index).tz_localize(None)
        return close
    except Exception as e:
        print(f"[Yahoo Finance] Failed for {ticker}: {e}")
        return pd.Series(dtype=float)


def fetch_yf_latest(ticker: str) -> float | None:
    """Get the latest closing price from Yahoo Finance."""
    s = fetch_yf_series(ticker, period="5d", interval="1d")
    if len(s) == 0:
        return None
    return float(s.iloc[-1])


# ─── Master fetch ──────────────────────────────────────────────────────────────

def fetch_all_indicators(fred_api_key: str = "") -> dict:
    """
    Fetch all indicator data needed for the scorecard.
    Returns a dict with both scalar current values and historical Series.
    """
    START = "2019-01-01"
    key   = fred_api_key or ""

    result = {}

    # ── 1. 10-yr Treasury nominal yield ────────────────────────────────────────
    tsy_series = fetch_fred("DGS10", key, START)
    # Supplement / cross-check with Yahoo Finance ^TNX
    tnx_series = fetch_yf_series("^TNX", "5y")
    if len(tnx_series) > 0:
        # ^TNX is in percent (e.g. 4.26 means 4.26%)
        # Merge: prefer FRED but fill gaps with yfinance
        combined = tsy_series.combine_first(tnx_series)
        tsy_series = combined.sort_index()

    result["treasury_10y_series"] = tsy_series
    result["treasury_10y"]        = latest(tsy_series)

    # ── 2. 10-yr TIPS real yield (DFII10) ──────────────────────────────────────
    tips_series = fetch_fred("DFII10", key, START)
    result["tips_real_yield_series"] = tips_series
    result["tips_real_yield"]        = latest(tips_series)

    # ── 3. 10-yr breakeven inflation (T10YIE) ──────────────────────────────────
    be_series = fetch_fred("T10YIE", key, START)
    result["breakeven_series"] = be_series
    result["breakeven"]        = latest(be_series)

    # ── 4. Effective Federal Funds Rate ────────────────────────────────────────
    ffr_series = fetch_fred("FEDFUNDS", key, START)
    result["fed_funds_series"] = ffr_series
    result["fed_funds"]        = latest(ffr_series)

    # ── 5. CPI (CPIAUCSL) → year-over-year inflation ───────────────────────────
    cpi_series = fetch_fred("CPIAUCSL", key, "2017-01-01")
    if len(cpi_series) >= 12:
        cpi_yoy = cpi_series.pct_change(12) * 100
        cpi_yoy = cpi_yoy.dropna()
        cpi_yoy = cpi_yoy[cpi_yoy.index >= START]
    else:
        cpi_yoy = pd.Series(dtype=float)
    result["cpi_yoy_series"] = cpi_yoy
    result["cpi_yoy"]        = latest(cpi_yoy)

    # ── 6. Real policy rate = Fed funds − CPI YoY ──────────────────────────────
    if result["fed_funds"] is not None and result["cpi_yoy"] is not None:
        result["real_policy_rate"] = round(result["fed_funds"] - result["cpi_yoy"], 2)
    else:
        result["real_policy_rate"] = None

    # Build historical real policy rate series (align on monthly frequency)
    if len(ffr_series) > 0 and len(cpi_yoy) > 0:
        ffr_m = ffr_series.resample("ME").last()
        cpi_m = cpi_yoy.resample("ME").last()
        real_rate_series = (ffr_m - cpi_m).dropna()
        result["real_policy_rate_series"] = real_rate_series
    else:
        result["real_policy_rate_series"] = pd.Series(dtype=float)

    # ── 7. HY credit spread — ICE BofA US High Yield OAS (BAMLH0A0HYM2) ───────
    hy_series = fetch_fred("BAMLH0A0HYM2", key, START)
    result["hy_spread_series"] = hy_series
    result["hy_spread"]        = latest(hy_series)

    # ── 8. KRE — Regional Banking ETF (Yahoo Finance) ─────────────────────────
    kre_series = fetch_yf_series("KRE", "5y")
    result["kre_series"]  = kre_series
    result["kre_current"] = latest(kre_series)
    result["kre_52w_high"] = float(kre_series.tail(252).max()) if len(kre_series) >= 252 else latest(kre_series)

    # Compute KRE decline from 52-week high
    if result["kre_current"] and result["kre_52w_high"]:
        result["kre_decline_pct"] = round(
            (result["kre_52w_high"] - result["kre_current"]) / result["kre_52w_high"] * 100, 1
        )
    else:
        result["kre_decline_pct"] = None

    # ── 9. Debt-to-GDP (GFDEGDQ188S — quarterly) ──────────────────────────────
    debt_gdp = fetch_fred("GFDEGDQ188S", key, "2015-01-01")
    result["debt_gdp_series"] = debt_gdp
    result["debt_gdp_pct"]    = latest(debt_gdp)

    # ── 10. Fiscal deficit placeholder (structural — use IMF/CBO static) ───────
    # FRED does not have deficit-to-GDP as a clean live series; use latest CBO value
    result["deficit_gdp_pct"] = 5.9   # FY2025 outturn per CBO
    result["interest_gdp_pct"] = 3.3  # FY2026 est. per CBO

    # ── Derived: spread between 10-yr nominal and TIPS (= breakeven check) ─────
    if result["treasury_10y"] and result["tips_real_yield"] is not None:
        result["implied_breakeven"] = round(
            result["treasury_10y"] - result["tips_real_yield"], 2
        )
    else:
        result["implied_breakeven"] = result.get("breakeven")

    return result
