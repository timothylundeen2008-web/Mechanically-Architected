"""
data_fetcher.py
================
Pulls all financial repression indicator data from FRED and Yahoo Finance.

yfinance column-handling strategy (3-layer fallback):
  1. yf.download(..., multi_level_index=False)  -> flat 'Close' column  [preferred]
  2. yf.Ticker(...).history()                   -> plain DataFrame       [fallback]
  3. Manual MultiIndex flatten on ('Close', ticker) tuple               [last resort]

FRED series:
  DGS10        — 10-yr Treasury constant maturity yield
  DFII10       — 10-yr TIPS real yield
  T10YIE       — 10-yr breakeven inflation rate
  FEDFUNDS     — Effective federal funds rate
  CPIAUCSL     — CPI all urban consumers
  BAMLH0A0HYM2 — ICE BofA US High Yield OAS
  GFDEGDQ188S  — Federal debt as % of GDP (quarterly)

Yahoo Finance tickers:
  KRE          — SPDR S&P Regional Banking ETF
  ^TNX         — 10-yr Treasury yield (real-time supplement to FRED DGS10)
"""

import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import requests

try:
    import yfinance as yf
    YFINANCE_OK = True
except Exception:
    YFINANCE_OK = False


# ─────────────────────────────────────────────────────────────────────────────
#  YAHOO FINANCE — bulletproof Close extractor
# ─────────────────────────────────────────────────────────────────────────────

def _extract_close(df: pd.DataFrame, ticker: str) -> pd.Series:
    """
    Extract a clean Close price Series from a yfinance DataFrame,
    handling flat columns, MultiIndex tuples, and string MultiIndex.

    Layer 1: flat column named 'Close'          (multi_level_index=False)
    Layer 2: MultiIndex tuple ('Close', ticker)  (download() default >= 0.2.x)
    Layer 3: MultiIndex string level search       (edge cases)
    """
    if df is None or df.empty:
        return pd.Series(dtype=float)

    cols = df.columns

    # Layer 1 — flat string column
    if "Close" in cols:
        s = df["Close"]
        if isinstance(s, pd.Series):
            return s.dropna().astype(float)
        # Sometimes returns DataFrame if column name collision
        if isinstance(s, pd.DataFrame):
            return s.iloc[:, 0].dropna().astype(float)

    # Layer 2 — MultiIndex tuple e.g. ('Close', 'KRE')
    target_tuple = ("Close", ticker)
    if target_tuple in cols:
        return df[target_tuple].dropna().astype(float)

    # Layer 3 — MultiIndex, search by first level == 'Close'
    if isinstance(cols, pd.MultiIndex):
        close_cols = [(a, b) for (a, b) in cols if a == "Close"]
        if close_cols:
            return df[close_cols[0]].dropna().astype(float)

    # Layer 4 — 'Adj Close' fallback (some older data)
    for name in ["Adj Close", ("Adj Close", ticker)]:
        if name in cols:
            s = df[name]
            if isinstance(s, pd.Series):
                return s.dropna().astype(float)

    print(f"[yfinance] Could not find Close column for {ticker}. Columns: {cols.tolist()[:6]}")
    return pd.Series(dtype=float)


def _strip_tz(series: pd.Series) -> pd.Series:
    """Remove timezone from DatetimeIndex so it matches FRED (tz-naive)."""
    if hasattr(series.index, "tz") and series.index.tz is not None:
        series = series.copy()
        series.index = series.index.tz_localize(None)
    return series


def fetch_yf_series(ticker: str, period: str = "5y") -> pd.Series:
    """
    Fetch Yahoo Finance closing prices as a clean pd.Series.
    Tries multi_level_index=False first, then Ticker.history(), then raw download.
    Returns empty Series on all failures — never raises.
    """
    if not YFINANCE_OK:
        return pd.Series(dtype=float)

    # ── Attempt 1: download with flat columns ──────────────────────────────────
    try:
        df = yf.download(
            ticker,
            period=period,
            auto_adjust=True,
            progress=False,
            multi_level_index=False,   # forces flat 'Close' column
        )
        s = _extract_close(df, ticker)
        if len(s) > 0:
            s = _strip_tz(s).sort_index()
            print(f"[yfinance] {ticker} via download(flat): "
                  f"{len(s)} rows, latest={s.iloc[-1]:.2f} ({s.index[-1].date()})")
            return s
    except Exception as e:
        print(f"[yfinance] download(flat) failed for {ticker}: {e}")

    # ── Attempt 2: Ticker.history() ───────────────────────────────────────────
    try:
        hist = yf.Ticker(ticker).history(period=period, auto_adjust=True)
        s = _extract_close(hist, ticker)
        if len(s) > 0:
            s = _strip_tz(s).sort_index()
            print(f"[yfinance] {ticker} via Ticker.history(): "
                  f"{len(s)} rows, latest={s.iloc[-1]:.2f} ({s.index[-1].date()})")
            return s
    except Exception as e:
        print(f"[yfinance] Ticker.history() failed for {ticker}: {e}")

    # ── Attempt 3: download() with default MultiIndex, then flatten ────────────
    try:
        df = yf.download(ticker, period=period, auto_adjust=True, progress=False)
        s = _extract_close(df, ticker)
        if len(s) > 0:
            s = _strip_tz(s).sort_index()
            print(f"[yfinance] {ticker} via download(MultiIndex flatten): "
                  f"{len(s)} rows, latest={s.iloc[-1]:.2f}")
            return s
    except Exception as e:
        print(f"[yfinance] download(MultiIndex) failed for {ticker}: {e}")

    print(f"[yfinance] All methods failed for {ticker} — returning empty Series")
    return pd.Series(dtype=float)


def fetch_yf_latest(ticker: str) -> float | None:
    """Most recent closing price, or None."""
    s = fetch_yf_series(ticker, period="5d")
    return float(s.iloc[-1]) if len(s) > 0 else None


# ─────────────────────────────────────────────────────────────────────────────
#  FRED
# ─────────────────────────────────────────────────────────────────────────────

_FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
_FRED_API = "https://api.stlouisfed.org/fred/series/observations"


def _fred_csv(series_id: str, start: str = "2019-01-01") -> pd.Series:
    """Public FRED CSV endpoint — no API key required."""
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
    """Official FRED API — requires free key, higher rate limits."""
    try:
        r = requests.get(_FRED_API, params={
            "series_id": series_id, "api_key": api_key,
            "file_type": "json", "observation_start": start, "sort_order": "asc",
        }, timeout=12)
        r.raise_for_status()
        obs  = r.json().get("observations", [])
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
    """Fetch FRED series — use API key if provided, else public CSV."""
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

    Returns dict of scalar values and historical pd.Series.
    All series: tz-naive DatetimeIndex, float values.
    Never raises — missing data returns None or empty Series.
    """
    START = "2019-01-01"
    key   = fred_api_key or ""
    out   = {}

    # ── 1. KRE — SPDR S&P Regional Banking ETF ────────────────────────────────
    kre = fetch_yf_series("KRE", period="5y")
    out["kre_series"]  = kre
    out["kre_current"] = latest(kre)
    out["kre_52w_high"] = (
        float(kre.tail(252).max()) if len(kre) >= 252
        else float(kre.max()) if len(kre) > 0
        else None
    )
    if out["kre_current"] and out["kre_52w_high"]:
        out["kre_decline_pct"] = round(
            (out["kre_52w_high"] - out["kre_current"]) / out["kre_52w_high"] * 100, 1
        )
    else:
        out["kre_decline_pct"] = None

    # ── 2. 10-yr Treasury nominal yield ───────────────────────────────────────
    tsy = fetch_fred("DGS10", key, START)
    tnx = fetch_yf_series("^TNX", period="5y")   # intraday supplement
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

    # ── 6. CPI YoY (computed from monthly CPIAUCSL) ───────────────────────────
    cpi_raw = fetch_fred("CPIAUCSL", key, "2017-01-01")
    if len(cpi_raw) >= 12:
        cpi_yoy = (cpi_raw.pct_change(12) * 100).dropna()
        cpi_yoy = cpi_yoy[cpi_yoy.index >= START]
    else:
        cpi_yoy = pd.Series(dtype=float)
    out["cpi_yoy_series"] = cpi_yoy
    out["cpi_yoy"]        = latest(cpi_yoy)

    # ── 7. Real policy rate ────────────────────────────────────────────────────
    if out["fed_funds"] is not None and out["cpi_yoy"] is not None:
        out["real_policy_rate"] = round(out["fed_funds"] - out["cpi_yoy"], 2)
    else:
        out["real_policy_rate"] = None

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

    # ── 10. Static CBO values ─────────────────────────────────────────────────
    out["deficit_gdp_pct"]  = 5.9   # FY2025 per CBO
    out["interest_gdp_pct"] = 3.3   # FY2026 est. per CBO

    # ── 11. Implied breakeven ─────────────────────────────────────────────────
    if out["treasury_10y"] is not None and out["tips_real_yield"] is not None:
        out["implied_breakeven"] = round(out["treasury_10y"] - out["tips_real_yield"], 2)
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
