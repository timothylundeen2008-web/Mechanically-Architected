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

    # ── 2. Treasury yields — all via Yahoo Finance for reliability ────────────
    # Yahoo Finance tickers:
    #   ^IRX = 13-week T-bill (best 2-yr proxy available intraday)
    #   ^FVX = 5-yr Treasury
    #   ^TNX = 10-yr Treasury
    #   ^TYX = 30-yr Treasury
    # FRED DGS series used as backup/history (may hit rate limits)
    print("\n[fetch] Treasury yields ---")

    # 10-yr: Yahoo Finance primary + FRED for longer history
    tnx = fetch_yf_series("^TNX", period="5y")
    tsy10_fred = fetch_fred("DGS10", key, START)
    if len(tnx) > 0 and len(tsy10_fred) > 0:
        tsy10 = tsy10_fred.combine_first(tnx).sort_index()
    elif len(tnx) > 0:
        tsy10 = tnx
    else:
        tsy10 = tsy10_fred
    out["treasury_10y_series"] = tsy10
    out["treasury_10y"]        = latest(tsy10)
    print(f"  10-yr: {len(tsy10)} rows, latest={out['treasury_10y']}")

    # 2-yr: Yahoo Finance ^IRX is 13-wk bill — use FRED DGS2 with yf fallback
    # Note: ^IRX reports as annualized discount rate; divide by 10 to get percent
    tsy2_fred = fetch_fred("DGS2", key, START)
    irx = fetch_yf_series("^IRX", period="5y")
    if len(irx) > 0:
        irx_pct = irx / 10.0  # ^IRX is in tenths of a percent
    else:
        irx_pct = pd.Series(dtype=float)

    if len(tsy2_fred) > 0:
        tsy2 = tsy2_fred  # FRED DGS2 is most accurate 2-yr
        if len(irx_pct) > 0:
            tsy2 = tsy2.combine_first(irx_pct).sort_index()
    else:
        tsy2 = irx_pct   # fallback to ^IRX if FRED fails
    out["treasury_2y_series"] = tsy2
    out["treasury_2y"]        = latest(tsy2)
    print(f"  2-yr:  {len(tsy2)} rows, latest={out['treasury_2y']}")

    # 30-yr: Yahoo Finance ^TYX primary (very reliable) + FRED backup
    tyx = fetch_yf_series("^TYX", period="5y")
    if len(tyx) > 0:
        # ^TYX is already in percent (e.g. 4.84 = 4.84%)
        tsy30 = tyx
        tsy30_fred = fetch_fred("DGS30", key, START)
        if len(tsy30_fred) > 0:
            tsy30 = tsy30_fred.combine_first(tyx).sort_index()
    else:
        tsy30 = fetch_fred("DGS30", key, START)
    out["treasury_30y_series"] = tsy30
    out["treasury_30y"]        = latest(tsy30)
    print(f"  30-yr: {len(tsy30)} rows, latest={out['treasury_30y']}")

    # SPY price — Yahoo Finance (fetch here so it's available for overlay chart)
    print("\n[fetch] SPY ---")
    spy = fetch_yf_series("SPY", period="5y")
    out["spy_series"] = spy
    out["spy_latest"] = latest(spy)
    print(f"  SPY: {len(spy)} rows, latest={out['spy_latest']}")

    # SPY earnings yield (trailing EPS / price * 100)
    # S&P 500 trailing 12-mo EPS ~$230 as of Q1 2026 (FactSet/Yardeni Research)
    SP500_TRAILING_EPS = 230.0
    if len(spy) > 0:
        spy_ey = (SP500_TRAILING_EPS / spy) * 100
        out["spy_earnings_yield_series"] = spy_ey
        out["spy_earnings_yield"]        = latest(spy_ey)
    else:
        out["spy_earnings_yield_series"] = pd.Series(dtype=float)
        out["spy_earnings_yield"]        = None

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

    # ── 13. Fed H.4.1 Balance Sheet series (weekly, Thursday release) ──────────
    # FRED units for H.4.1 series:
    #   WALCL, TREAST, WSHOMCB, WTREGEN, WRESBAL → all in MILLIONS of USD
    #   RRPONTSYD → already in BILLIONS of USD
    # Small delay between calls to avoid FRED free-tier rate limit (120 req/min)
    import time as _time
    print("\n[fetch] H.4.1 Balance Sheet ---")

    def _bs_fetch(series_id, divisor, label, delay=0.6):
        """Fetch a balance sheet series, apply unit divisor, with rate-limit pause."""
        _time.sleep(delay)   # avoid hitting FRED 120 req/min free-tier limit
        raw_s = fetch_fred(series_id, key, "2019-01-01")
        if len(raw_s) > 0:
            converted = raw_s / divisor
            lv = latest(converted)
            print(f"  {series_id:12s}: {len(raw_s)} rows, "
                  f"latest_raw={raw_s.dropna().iloc[-1]:,.0f} → {lv:.3f} {label}")
            return converted, lv
        else:
            print(f"  {series_id:12s}: EMPTY — fetch failed")
            return pd.Series(dtype=float), None

    # WALCL: millions → trillions  (/1e6)
    walcl_s,   walcl_lv   = _bs_fetch("WALCL",     1e6,  "T")
    # TREAST: millions → trillions (/1e6)
    treast_s,  treast_lv  = _bs_fetch("TREAST",    1e6,  "T")
    # WSHOMCB: millions → trillions (/1e6)
    mbs_s,     mbs_lv     = _bs_fetch("WSHOMCB",   1e6,  "T")
    # WTREGEN: millions → billions (/1e3)
    tga_s,     tga_lv     = _bs_fetch("WTREGEN",   1e3,  "B")
    # WRESBAL: millions → billions (/1e3)
    resbal_s,  resbal_lv  = _bs_fetch("WRESBAL",   1e3,  "B")
    # RRPONTSYD: already billions (/1)
    rrp_s,     rrp_lv     = _bs_fetch("RRPONTSYD", 1,    "B")

    out["bs_total_assets"]        = walcl_s
    out["bs_total_assets_latest"] = walcl_lv
    out["bs_treasuries"]          = treast_s
    out["bs_treasuries_latest"]   = treast_lv
    out["bs_mbs"]                 = mbs_s
    out["bs_mbs_latest"]          = mbs_lv
    out["bs_tga"]                 = tga_s
    out["bs_tga_latest"]          = tga_lv
    out["bs_reserves"]            = resbal_s
    out["bs_reserves_latest"]     = resbal_lv
    out["bs_rrp"]                 = rrp_s
    out["bs_rrp_latest"]          = rrp_lv

    # Week-over-week change in total assets (result in billions)
    if len(walcl_s) >= 2:
        wc = walcl_s.dropna()
        # walcl_s is in trillions; *1000 → billions
        out["bs_wow_change_bn"] = round((wc.iloc[-1] - wc.iloc[-2]) * 1000, 1)
    else:
        out["bs_wow_change_bn"] = None

    # QT drawdown from April 2022 peak ($8.965T)
    bs_peak_t = 8.965   # trillions
    out["bs_peak_bn"] = bs_peak_t * 1000
    if walcl_lv is not None:
        out["bs_drawdown_pct"] = round(
            (bs_peak_t - walcl_lv) / bs_peak_t * 100, 1
        )
    else:
        out["bs_drawdown_pct"] = None

    # Store raw fetch status so tab can show diagnostic
    out["bs_fetch_status"] = {
        "WALCL":     len(walcl_s),
        "TREAST":    len(treast_s),
        "WSHOMCB":   len(mbs_s),
        "WTREGEN":   len(tga_s),
        "WRESBAL":   len(resbal_s),
        "RRPONTSYD": len(rrp_s),
    }

    print(f"  WoW change: {out['bs_wow_change_bn']} B | "
          f"Drawdown: {out['bs_drawdown_pct']}%")

    # ── Final summary ──────────────────────────────────────────────────────────
    print("\n=== fetch_all_indicators complete ===")
    for k in ["treasury_10y", "tips_real_yield", "breakeven", "fed_funds",
              "cpi_yoy", "real_policy_rate", "hy_spread", "debt_gdp_pct",
              "kre_current", "kre_52w_high", "kre_decline_pct"]:
        v = out.get(k)
        print(f"  {k:30s}: {f'{v:.4f}' if isinstance(v, float) else v}")

    return out