"""
data_fetcher.py
================
Pulls all financial repression indicator data from FRED and Yahoo Finance.

Uses yfinance >= 0.2.x Ticker.history() API (not the deprecated yf.download()).
Falls back gracefully if any source is unavailable.

FRED series:
  DGS10        — 10-yr Treasury constant maturity yield
  DFII10       — 10-yr TIPS real yield
  T10YIE       — 10-yr breakeven inflation rate
  FEDFUNDS     — Effective federal funds rate
  CPIAUCSL     — CPI all urban consumers
  BAMLH0A0HYM2 — ICE BofA US High Yield OAS
  GFDEGDQ188S  — Federal debt as % of GDP (quarterly)

Yahoo Finance tickers (via Ticker.history):
  KRE          — SPDR S&P Regional Banking ETF
  ^TNX         — 10-yr Treasury yield (real-time supplement)
"""

import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import requests

# ── yfinance import guard ──────────────────────────────────────────────────────
try:
    import yfinance as yf
    YFINANCE_OK = True
except Exception:
    YFINANCE_OK = False


# ─────────────────────────────────────────────────────────────────────────────
#  YAHOO FINANCE  (Ticker.history — works in yfinance >= 0.2.x)
# ─────────────────────────────────────────────────────────────────────────────

def _yf_history(ticker_str: str, period: str = "5y") -> pd.Series:
    """
    Fetch closing prices using the modern yfinance Ticker.history() API.

    Returns a clean pd.Series (DatetimeIndex -> float), or empty Series on failure.

    Why Ticker.history() instead of yf.download():
      - yf.download() in >= 0.2.x returns MultiIndex columns when multiple
        tickers are implied, making ['Close'] fail silently or return a DataFrame.
      - Ticker.history() always returns a simple single-ticker DataFrame with
        plain column names: Open, High, Low, Close, Volume, Dividends, Stock Splits.
    """
    if not YFINANCE_OK:
        return pd.Series(dtype=float)

    try:
        t    = yf.Ticker(ticker_str)
        hist = t.history(period=period, auto_adjust=True)

        if hist is None or hist.empty:
            print(f"[yfinance] Empty result for {ticker_str}")
            return pd.Series(dtype=float)

        # Ticker.history() always has a plain 'Close' column (no MultiIndex)
        close = hist["Close"].copy()

        # Strip timezone so index is tz-naive (consistent with FRED)
        if hasattr(close.index, "tz") and close.index.tz is not None:
            close.index = close.index.tz_localize(None)

        close = close.dropna().sort_index()
        print(f"[yfinance] {ticker_str}: {len(close)} rows, "
              f"latest={close.iloc[-1]:.2f} ({close.index[-1].date()})")
        return close

    except Exception as e:
        print(f"[yfinance] Failed for {ticker_str}: {type(e).__name__}: {e}")
        return pd.Series(dtype=float)


def fetch_yf_series(ticker_str: str, period: str = "5y") -> pd.Series:
    """Public wrapper — fetch a Yahoo Finance ticker as a price Series."""
    return _yf_history(ticker_str, period=period)


def fetch_yf_latest(ticker_str: str) -> float | None:
    """Return only the most recent closing price."""
    s = _yf_history(ticker_str, period="5d")
    return float(s.iloc[-1]) if len(s) > 0 else None


# ─────────────────────────────────────────────────────────────────────────────
#  FRED
# ─────────────────────────────────────────────────────────────────────────────

_FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
_FRED_API = "https://api.stlouisfed.org/fred/series/observations"


def _fred_csv(series_id: str, start: str = "2019-01-01") -> pd.Series:
    """Public CSV endpoint — no API key required."""
    try:
        url = f"{_FRED_CSV}?id={series_id}"
        df  = pd.read_csv(url, parse_dates=["DATE"], index_col="DATE")
        df.columns = ["value"]
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        s = df["value"].dropna()
        s = s[s.index >= start]
        print(f"[FRED CSV] {series_id}: {len(s)} rows, latest={s.iloc[-1]:.3f}")
        return s
    except Exception as e:
        print(f"[FRED CSV] Failed for {series_id}: {e}")
        return pd.Series(dtype=float)


def _fred_api(series_id: str, api_key: str, start: str = "2019-01-01") -> pd.Series:
    """Official FRED API — requires key, higher rate limits."""
    try:
        r = requests.get(_FRED_API, params={
            "series_id": series_id, "api_key": api_key,
            "file_type": "json", "observation_start": start, "sort_order": "asc",
        }, timeout=12)
        r.raise_for_status()
        obs = r.json().get("observations", [])
        data = {pd.Timestamp(o["date"]): float(o["value"])
                for o in obs if o.get("value", ".") != "."}
        s = pd.Series(data)
        print(f"[FRED API] {series_id}: {len(s)} rows")
        return s
    except Exception as e:
        print(f"[FRED API] Failed for {series_id}: {e}")
        return pd.Series(dtype=float)


def fetch_fred(series_id: str, api_key: str = "",
               start: str = "2019-01-01") -> pd.Series:
    """Fetch a FRED series — API key path if available, else public CSV."""
    if api_key:
        s = _fred_api(series_id, api_key, start)
        if len(s) > 0:
            return s
    return _fred_csv(series_id, start)


def latest(series: pd.Series) -> float | None:
    """Most recent non-NaN value, or None."""
    if series is None or len(series) == 0:
        return None
    clean = series.dropna()
    return float(clean.iloc[-1]) if len(clean) > 0 else None


# ─────────────────────────────────────────────────────────────────────────────
#  MASTER FETCH
# ─────────────────────────────────────────────────────────────────────────────

def fetch_all_indicators(fred_api_key: str = "") -> dict:
    """
    Fetch all indicator data from FRED and Yahoo Finance.

    Returns a dict containing:
      - Scalar current values  (e.g. 'tips_real_yield': 2.01)
      - Historical pd.Series   (e.g. 'tips_real_yield_series': pd.Series)

    All series have tz-naive DatetimeIndex and float values.
    Missing data returns None (scalars) or empty Series — never raises.
    """
    START = "2019-01-01"
    key   = fred_api_key or ""
    out   = {}

    # ── 1. KRE — Regional Banking ETF ─────────────────────────────────────────
    # Fetched first so yfinance issues surface early with a clear label.
    kre_series = fetch_yf_series("KRE", period="5y")
    out["kre_series"]  = kre_series
    out["kre_current"] = latest(kre_series)

    if len(kre_series) >= 252:
        out["kre_52w_high"] = float(kre_series.tail(252).max())
    elif len(kre_series) > 0:
        out["kre_52w_high"] = float(kre_series.max())
    else:
        out["kre_52w_high"] = None

    if out["kre_current"] and out["kre_52w_high"]:
        out["kre_decline_pct"] = round(
            (out["kre_52w_high"] - out["kre_current"]) / out["kre_52w_high"] * 100, 1
        )
    else:
        out["kre_decline_pct"] = None

    # ── 2. 10-yr Treasury nominal yield ───────────────────────────────────────
    tsy = fetch_fred("DGS10", key, START)
    # ^TNX fills intraday gaps (FRED lags ~1 business day)
    tnx = fetch_yf_series("^TNX", period="5y")
    if len(tnx) > 0:
        tsy = tsy.combine_first(tnx).sort_index()
    out["treasury_10y_series"] = tsy
    out["treasury_10y"]        = latest(tsy)

    # ── 3. 10-yr TIPS real yield ───────────────────────────────────────────────
    tips = fetch_fred("DFII10", key, START)
    out["tips_real_yield_series"] = tips
    out["tips_real_yield"]        = latest(tips)

    # ── 4. 10-yr breakeven inflation ──────────────────────────────────────────
    be = fetch_fred("T10YIE", key, START)
    out["breakeven_series"] = be
    out["breakeven"]        = latest(be)

    # ── 5. Effective Federal Funds Rate ───────────────────────────────────────
    ffr = fetch_fred("FEDFUNDS", key, START)
    out["fed_funds_series"] = ffr
    out["fed_funds"]        = latest(ffr)

    # ── 6. CPI YoY inflation ──────────────────────────────────────────────────
    # Fetch from 2017 so we have 12 months of lead time to compute YoY from 2019
    cpi_raw = fetch_fred("CPIAUCSL", key, "2017-01-01")
    if len(cpi_raw) >= 12:
        cpi_yoy = (cpi_raw.pct_change(12) * 100).dropna()
        cpi_yoy = cpi_yoy[cpi_yoy.index >= START]
    else:
        cpi_yoy = pd.Series(dtype=float)
    out["cpi_yoy_series"] = cpi_yoy
    out["cpi_yoy"]        = latest(cpi_yoy)

    # ── 7. Real policy rate = Fed funds - CPI YoY ─────────────────────────────
    if out["fed_funds"] is not None and out["cpi_yoy"] is not None:
        out["real_policy_rate"] = round(out["fed_funds"] - out["cpi_yoy"], 2)
    else:
        out["real_policy_rate"] = None

    # Historical real policy rate series (monthly alignment)
    if len(ffr) > 0 and len(cpi_yoy) > 0:
        ffr_m = ffr.resample("ME").last()
        cpi_m = cpi_yoy.resample("ME").last()
        out["real_policy_rate_series"] = (ffr_m - cpi_m).dropna()
    else:
        out["real_policy_rate_series"] = pd.Series(dtype=float)

    # ── 8. HY credit spread (OAS) ─────────────────────────────────────────────
    hy = fetch_fred("BAMLH0A0HYM2", key, START)
    out["hy_spread_series"] = hy
    out["hy_spread"]        = latest(hy)

    # ── 9. Debt-to-GDP (quarterly) ────────────────────────────────────────────
    debt = fetch_fred("GFDEGDQ188S", key, "2015-01-01")
    out["debt_gdp_series"] = debt
    out["debt_gdp_pct"]    = latest(debt)

    # ── 10. Static CBO/IMF values (no clean live FRED series) ─────────────────
    out["deficit_gdp_pct"]  = 5.9   # FY2025 outturn per CBO
    out["interest_gdp_pct"] = 3.3   # FY2026 estimate per CBO

    # ── 11. Derived: implied breakeven (nominal yield - TIPS yield) ────────────
    if out["treasury_10y"] is not None and out["tips_real_yield"] is not None:
        out["implied_breakeven"] = round(
            out["treasury_10y"] - out["tips_real_yield"], 2
        )
    else:
        out["implied_breakeven"] = out.get("breakeven")

    # ── Summary ────────────────────────────────────────────────────────────────
    print("\n=== fetch_all_indicators complete ===")
    for k in ["treasury_10y", "tips_real_yield", "breakeven", "fed_funds",
              "cpi_yoy", "real_policy_rate", "hy_spread", "debt_gdp_pct",
              "kre_current", "kre_52w_high", "kre_decline_pct"]:
        v = out.get(k)
        print(f"  {k:30s}: {f'{v:.2f}' if isinstance(v, float) else v}")

    return out
