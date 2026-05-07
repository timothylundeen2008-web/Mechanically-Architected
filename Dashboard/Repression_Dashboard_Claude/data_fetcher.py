"""
data_fetcher.py
================
Pulls all financial repression indicator data from FRED and Yahoo Finance.

yfinance strategy: Method A only — yf.download(multi_level_index=False)
Confirmed working on Python 3.14.4 / yfinance 1.3.0 / pandas 3.0.2

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
  ^TNX         — 10-yr Treasury yield (intraday supplement to FRED DGS10)
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
#  YAHOO FINANCE — Method A: download(multi_level_index=False)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_yf_series(ticker: str, period: str = "5y") -> pd.Series:
    """
    Fetch Yahoo Finance closing prices as a clean pd.Series.

    Uses Method A: yf.download(multi_level_index=False) which returns flat
    column names ('Close', 'High', ...) confirmed working on yfinance 1.3.0.

    Falls back to Ticker.history() if Method A returns empty.
    Returns empty Series on all failures — never raises.
    """
    if not YFINANCE_OK:
        print(f"[yfinance] Not installed — cannot fetch {ticker}")
        return pd.Series(dtype=float)

    # ── Method A: flat columns (primary) ─────────────────────────────────────
    try:
        df = yf.download(
            ticker,
            period=period,
            auto_adjust=True,
            progress=False,
            multi_level_index=False,
        )
        print(f"[yfinance-A] {ticker} raw shape={df.shape}, cols={df.columns.tolist()}")

        if df.empty:
            print(f"[yfinance-A] {ticker} returned empty DataFrame")
        elif "Close" not in df.columns:
            print(f"[yfinance-A] {ticker} missing Close column, got: {df.columns.tolist()}")
        else:
            s = df["Close"]
            # Ensure it is a Series, not a DataFrame
            if isinstance(s, pd.DataFrame):
                print(f"[yfinance-A] {ticker} Close is DataFrame — taking first column")
                s = s.iloc[:, 0]
            s = s.dropna().astype(float)
            # Strip timezone
            if hasattr(s.index, "tz") and s.index.tz is not None:
                s.index = s.index.tz_localize(None)
            s = s.sort_index()
            if len(s) > 0:
                print(f"[yfinance-A] {ticker} OK: {len(s)} rows, "
                      f"latest={s.iloc[-1]:.4f} ({s.index[-1].date()})")
                return s
            else:
                print(f"[yfinance-A] {ticker} Close Series empty after dropna")
    except Exception as e:
        print(f"[yfinance-A] {ticker} failed: {type(e).__name__}: {e}")

    # ── Method B: Ticker.history() (fallback) ─────────────────────────────────
    try:
        print(f"[yfinance-B] {ticker} trying Ticker.history(period={period})")
        hist = yf.Ticker(ticker).history(period=period, auto_adjust=True)
        print(f"[yfinance-B] {ticker} raw shape={hist.shape}, cols={hist.columns.tolist()}")

        if "Close" in hist.columns and not hist.empty:
            s = hist["Close"].dropna().astype(float)
            if hasattr(s.index, "tz") and s.index.tz is not None:
                s.index = s.index.tz_localize(None)
            s = s.sort_index()
            if len(s) > 0:
                print(f"[yfinance-B] {ticker} OK: {len(s)} rows, "
                      f"latest={s.iloc[-1]:.4f} ({s.index[-1].date()})")
                return s
    except Exception as e:
        print(f"[yfinance-B] {ticker} failed: {type(e).__name__}: {e}")

    print(f"[yfinance] All methods failed for {ticker} — returning empty Series")
    return pd.Series(dtype=float)


def fetch_yf_latest(ticker: str) -> float | None:
    """Most recent closing price only."""
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
        print(f"[FRED CSV] {series_id} failed: {e}")
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
        print(f"[FRED API] {series_id} failed: {e}")
        return pd.Series(dtype=float)


def fetch_fred(series_id: str, api_key: str = "",
               start: str = "2019-01-01") -> pd.Series:
    """Fetch FRED series — API key if provided, else public CSV."""
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
    Never raises — missing data returns None or empty Series.
    """
    START = "2019-01-01"
    key   = fred_api_key or ""
    out   = {}

    # ── 1. KRE — SPDR S&P Regional Banking ETF ────────────────────────────────
    print("\n[fetch] KRE ---")
    kre = fetch_yf_series("KRE", period="5y")
    out["kre_series"]  = kre
    out["kre_current"] = latest(kre)
    out["kre_52w_high"] = (
        float(kre.tail(252).max()) if len(kre) >= 252
        else float(kre.max())      if len(kre) > 0
        else None
    )
    if out["kre_current"] and out["kre_52w_high"]:
        out["kre_decline_pct"] = round(
            (out["kre_52w_high"] - out["kre_current"])
            / out["kre_52w_high"] * 100, 1
        )
    else:
        out["kre_decline_pct"] = None
    print(f"[fetch] KRE current={out['kre_current']}, "
          f"52w_high={out['kre_52w_high']}, "
          f"decline={out['kre_decline_pct']}%")

    # ── 2. 10-yr Treasury nominal yield ───────────────────────────────────────
    print("\n[fetch] Treasury 10yr ---")
    tsy = fetch_fred("DGS10", key, START)
    tnx = fetch_yf_series("^TNX", period="5y")
    if len(tnx) > 0:
        tsy = tsy.combine_first(tnx).sort_index()
    out["treasury_10y_series"] = tsy
    out["treasury_10y"]        = latest(tsy)

    # ── 3. 10-yr TIPS real yield ───────────────────────────────────────────────
    print("\n[fetch] TIPS real yield ---")
    tips = fetch_fred("DFII10", key, START)
    out["tips_real_yield_series"] = tips
    out["tips_real_yield"]        = latest(tips)

    # ── 4. 10-yr breakeven inflation ──────────────────────────────────────────
    print("\n[fetch] Breakeven ---")
    be = fetch_fred("T10YIE", key, START)
    out["breakeven_series"] = be
    out["breakeven"]        = latest(be)

    # ── 5. Effective Federal Funds Rate ───────────────────────────────────────
    print("\n[fetch] Fed funds ---")
    ffr = fetch_fred("FEDFUNDS", key, START)
    out["fed_funds_series"] = ffr
    out["fed_funds"]        = latest(ffr)

    # ── 6. CPI YoY ────────────────────────────────────────────────────────────
    print("\n[fetch] CPI ---")
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

    # ── 8. HY credit spread ────────────────────────────────────────────────────
    print("\n[fetch] HY spread ---")
    hy = fetch_fred("BAMLH0A0HYM2", key, START)
    out["hy_spread_series"] = hy
    out["hy_spread"]        = latest(hy)

    # ── 9. Debt-to-GDP ─────────────────────────────────────────────────────────
    print("\n[fetch] Debt/GDP ---")
    debt = fetch_fred("GFDEGDQ188S", key, "2015-01-01")
    out["debt_gdp_series"] = debt
    out["debt_gdp_pct"]    = latest(debt)

    # ── 10. Static CBO values ──────────────────────────────────────────────────
    out["deficit_gdp_pct"]  = 5.9
    out["interest_gdp_pct"] = 3.3

    # ── 11. Implied breakeven ──────────────────────────────────────────────────
    if out["treasury_10y"] is not None and out["tips_real_yield"] is not None:
        out["implied_breakeven"] = round(
            out["treasury_10y"] - out["tips_real_yield"], 2
        )
    else:
        out["implied_breakeven"] = out.get("breakeven")

    # ── 12. Wealth-building asset tickers (pre-fetched for Tab 5) ─────────────
    # One primary ticker per asset — stored as "wealth_{TICKER}_series"
    # Fetched here so the tab renders instantly without per-chart spinner delays.
    WEALTH_TICKERS = [
        # Before
        "SCHP",   # TIPS ETF
        "GLD",    # Gold
        "VYM",    # Dividend equity
        "VNQ",    # REITs
        # During
        "XLE",    # Energy
        "VEA",    # Intl developed equity
        "FLOT",   # Floating rate
        "IBIT",   # Bitcoin ETF
        # After
        "TLT",    # Long Treasuries
        "QQQ",    # Growth/Tech
        "VT",     # Global equity
    ]
    print("\n[fetch] Wealth asset tickers ---")
    for tkr in WEALTH_TICKERS:
        key_name = f"wealth_{tkr}_series"
        s = fetch_yf_series(tkr, period="2y")
        out[key_name] = s
        if len(s) > 0:
            print(f"  {tkr:6s}: {len(s)} rows, latest={s.iloc[-1]:.2f}")
        else:
            print(f"  {tkr:6s}: EMPTY")

    # ── Final summary ──────────────────────────────────────────────────────────
    print("\n=== fetch_all_indicators complete ===")
    for k in ["treasury_10y", "tips_real_yield", "breakeven", "fed_funds",
              "cpi_yoy", "real_policy_rate", "hy_spread", "debt_gdp_pct",
              "kre_current", "kre_52w_high", "kre_decline_pct"]:
        v = out.get(k)
        print(f"  {k:30s}: {f'{v:.4f}' if isinstance(v, float) else v}")

    return out
