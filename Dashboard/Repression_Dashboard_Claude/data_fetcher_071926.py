"""
data_fetcher.py
================
Fetches all financial repression indicator data.

Key improvements:
  - All FRED series fetched in PARALLEL via ThreadPoolExecutor (max 3 concurrent)
  - Per-request retry with exponential backoff (3 attempts, 30s timeout)
  - Browser-like User-Agent headers to reduce Streamlit Cloud IP blocks
  - Yahoo Finance primary for 2-yr (^IRX), 30-yr (^TYX), 10-yr (^TNX), SPY
  - FRED used for history/accuracy, Yahoo Finance as live fallback
"""

import warnings
warnings.filterwarnings("ignore")

import time as _time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import StringIO

import pandas as pd
import requests

try:
    import yfinance as yf
    YFINANCE_OK = True
except Exception:
    YFINANCE_OK = False


# ─────────────────────────────────────────────────────────────────────────────
#  YAHOO FINANCE
# ─────────────────────────────────────────────────────────────────────────────

def fetch_yf_series(ticker: str, period: str = "5y") -> pd.Series:
    if not YFINANCE_OK:
        return pd.Series(dtype=float)

    # Attempt 1: download with flat columns
    try:
        df = yf.download(ticker, period=period, auto_adjust=True,
                         progress=False, multi_level_index=False)
        print(f"[yfinance-A] {ticker} shape={df.shape}, cols={df.columns.tolist()}")
        if not df.empty and "Close" in df.columns:
            s = df["Close"]
            if isinstance(s, pd.DataFrame):
                s = s.iloc[:, 0]
            s = s.dropna().astype(float)
            if hasattr(s.index, "tz") and s.index.tz is not None:
                s.index = s.index.tz_localize(None)
            s = s.sort_index()
            if len(s) > 0:
                print(f"[yfinance-A] {ticker} OK: {len(s)} rows, latest={s.iloc[-1]:.4f}")
                return s
    except Exception as e:
        print(f"[yfinance-A] {ticker} failed: {e}")

    # Attempt 2: Ticker.history()
    try:
        hist = yf.Ticker(ticker).history(period=period, auto_adjust=True)
        if "Close" in hist.columns and not hist.empty:
            s = hist["Close"].dropna().astype(float)
            if hasattr(s.index, "tz") and s.index.tz is not None:
                s.index = s.index.tz_localize(None)
            s = s.sort_index()
            if len(s) > 0:
                print(f"[yfinance-B] {ticker} OK: {len(s)} rows, latest={s.iloc[-1]:.4f}")
                return s
    except Exception as e:
        print(f"[yfinance-B] {ticker} failed: {e}")

    print(f"[yfinance] All methods failed for {ticker}")
    return pd.Series(dtype=float)


def fetch_yf_latest(ticker: str) -> float | None:
    s = fetch_yf_series(ticker, period="5d")
    return float(s.iloc[-1]) if len(s) > 0 else None


# ─────────────────────────────────────────────────────────────────────────────
#  FRED — with retry, longer timeout, browser headers
# ─────────────────────────────────────────────────────────────────────────────

_FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
_FRED_API = "https://api.stlouisfed.org/fred/series/observations"
_HEADERS  = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _fred_csv(series_id: str, start: str = "2019-01-01",
              max_retries: int = 3) -> pd.Series:
    url = f"{_FRED_CSV}?id={series_id}"
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=30)
            resp.raise_for_status()
            df = pd.read_csv(StringIO(resp.text), parse_dates=["DATE"],
                             index_col="DATE")
            df.columns = ["value"]
            df["value"] = pd.to_numeric(df["value"], errors="coerce")
            s = df["value"].dropna()
            s = s[s.index >= start]
            if len(s) > 0:
                print(f"[FRED CSV] {series_id}: {len(s)} rows, "
                      f"latest={s.iloc[-1]:.3f} (attempt {attempt})")
                return s
        except requests.exceptions.ReadTimeout:
            wait = 2 ** attempt
            print(f"[FRED CSV] {series_id}: ReadTimeout attempt {attempt} — wait {wait}s")
            if attempt < max_retries:
                _time.sleep(wait)
        except Exception as e:
            print(f"[FRED CSV] {series_id}: error attempt {attempt}: {type(e).__name__}: {e}")
            if attempt < max_retries:
                _time.sleep(1)
    print(f"[FRED CSV] {series_id}: all {max_retries} attempts failed")
    return pd.Series(dtype=float)


def _fred_api(series_id: str, api_key: str, start: str = "2019-01-01",
              max_retries: int = 3) -> pd.Series:
    params = {
        "series_id": series_id, "api_key": api_key,
        "file_type": "json", "observation_start": start, "sort_order": "asc",
    }
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(_FRED_API, params=params,
                             headers=_HEADERS, timeout=30)
            r.raise_for_status()
            obs  = r.json().get("observations", [])
            data = {pd.Timestamp(o["date"]): float(o["value"])
                    for o in obs if o.get("value", ".") != "."}
            s = pd.Series(data)
            if len(s) > 0:
                print(f"[FRED API] {series_id}: {len(s)} rows (attempt {attempt})")
                return s
        except requests.exceptions.ReadTimeout:
            wait = 2 ** attempt
            print(f"[FRED API] {series_id}: ReadTimeout attempt {attempt} — wait {wait}s")
            if attempt < max_retries:
                _time.sleep(wait)
        except Exception as e:
            print(f"[FRED API] {series_id}: error attempt {attempt}: {e}")
            if attempt < max_retries:
                _time.sleep(1)
    return pd.Series(dtype=float)


def fetch_fred(series_id: str, api_key: str = "",
               start: str = "2019-01-01") -> pd.Series:
    if api_key:
        s = _fred_api(series_id, api_key, start)
        if len(s) > 0:
            return s
    return _fred_csv(series_id, start)


def fetch_fred_batch(series_dict: dict, api_key: str = "",
                     start: str = "2019-01-01",
                     max_workers: int = 3) -> dict:
    """
    Fetch multiple FRED series in parallel.
    max_workers=3 avoids hammering FRED; each worker has its own retry logic.
    """
    results = {}

    def _one(output_key, series_id):
        _time.sleep(0.4)   # small stagger so threads don't all hit FRED at t=0
        return output_key, fetch_fred(series_id, api_key, start)

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_one, k, v): k for k, v in series_dict.items()}
        for future in as_completed(futures):
            try:
                out_key, series = future.result()
                results[out_key] = series
                n  = len(series)
                lv = f"{series.dropna().iloc[-1]:.3f}" if n > 0 else "EMPTY"
                print(f"[batch] {out_key:32s}: {n} rows, latest={lv}")
            except Exception as e:
                k = futures[future]
                print(f"[batch] {k}: exception {e}")
                results[k] = pd.Series(dtype=float)

    return results


def fetch_treasury_auctions(security_term_contains: str = "10-Year",
                             n: int = 16,
                             max_retries: int = 3) -> pd.DataFrame:
    """
    Live bid-to-cover ratio history from Treasury's public Fiscal Data API
    (no key required). Filters to a given security term (e.g. "10-Year" for
    notes, "30-Year" for bonds, "2-Year" for the short end) and returns the
    most recent `n` auctions, oldest first.

    Returns a DataFrame indexed by auction_date with columns:
      security_term, high_yield, bid_to_cover_ratio
    Empty DataFrame on failure — callers should treat that as "unavailable",
    same convention as fetch_fred returning an empty Series.
    """
    url = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query"
    params = {
        "fields": "auction_date,security_type,security_term,high_yield,bid_to_cover_ratio",
        "filter": "security_type:eq:Note,bid_to_cover_ratio:gt:0",
        "sort": "-auction_date",
        "page[size]": "200",
    }
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(url, params=params, headers=_HEADERS, timeout=30)
            r.raise_for_status()
            data = r.json().get("data", [])
            if not data:
                print(f"[auctions] empty response (attempt {attempt})")
                continue
            df = pd.DataFrame(data)
            df = df[df["security_term"].str.contains(security_term_contains, na=False)]
            df["auction_date"] = pd.to_datetime(df["auction_date"])
            df["bid_to_cover_ratio"] = pd.to_numeric(df["bid_to_cover_ratio"], errors="coerce")
            df["high_yield"] = pd.to_numeric(df["high_yield"], errors="coerce")
            df = df.dropna(subset=["bid_to_cover_ratio"]).sort_values("auction_date")
            df = df.set_index("auction_date").tail(n)
            if len(df) > 0:
                print(f"[auctions] {security_term_contains}: {len(df)} auctions, "
                      f"latest B/C={df['bid_to_cover_ratio'].iloc[-1]:.2f} (attempt {attempt})")
                return df[["security_term", "high_yield", "bid_to_cover_ratio"]]
        except requests.exceptions.ReadTimeout:
            wait = 2 ** attempt
            print(f"[auctions] ReadTimeout attempt {attempt} — wait {wait}s")
            if attempt < max_retries:
                _time.sleep(wait)
        except Exception as e:
            print(f"[auctions] error attempt {attempt}: {type(e).__name__}: {e}")
            if attempt < max_retries:
                _time.sleep(1)
    print(f"[auctions] all {max_retries} attempts failed for '{security_term_contains}'")
    return pd.DataFrame(columns=["security_term", "high_yield", "bid_to_cover_ratio"])


def latest(series: pd.Series) -> float | None:
    if series is None or len(series) == 0:
        return None
    clean = series.dropna()
    return float(clean.iloc[-1]) if len(clean) > 0 else None


# ─────────────────────────────────────────────────────────────────────────────
#  MASTER FETCH
# ─────────────────────────────────────────────────────────────────────────────

def fetch_all_indicators(fred_api_key: str = "") -> dict:
    """
    Fetch all indicator data.  Returns dict of scalars and pd.Series.
    Never raises — missing data → None or empty Series.
    """
    START = "2019-01-01"
    key   = fred_api_key or ""
    out   = {}

    # ── Step 1: Batch-fetch all FRED series in parallel ───────────────────────
    print("\n[fetch] FRED parallel batch (max 3 concurrent) ---")
    fred_batch = {
        "tips_real_yield_series": "DFII10",
        "treasury_10y_series":    "DGS10",
        "treasury_2y_series":     "DGS2",
        "treasury_30y_series":    "DGS30",
        "breakeven_series":       "T10YIE",
        "fed_funds_series":       "FEDFUNDS",
        "hy_spread_series":       "BAMLH0A0HYM2",
        # H.4.1 balance sheet (millions of USD except RRPONTSYD which is billions)
        "bs_walcl_raw":           "WALCL",
        "bs_treast_raw":          "TREAST",
        "bs_mbs_raw":             "WSHOMCB",
        "bs_tga_raw":             "WTREGEN",
        "bs_reserves_raw":        "WRESBAL",
        "bs_rrp_raw":             "RRPONTSYD",
    }
    batch = fetch_fred_batch(fred_batch, key, START, max_workers=3)
    out.update(batch)

    # CPI and debt need different start dates — fetch separately
    # NSA (CPIAUCNS) is the CALCULATION series: the publicly-quoted headline
    # YoY figure (e.g. "CPI rose 4.2%") is BLS's official number, computed
    # from the UNADJUSTED index. CPIAUCSL's seasonal factors are re-revised
    # annually (each Feb) and can visibly diverge from the quoted headline —
    # fetched separately below for DISPLAY only, never for calculation.
    out["cpi_raw_series"]     = fetch_fred("CPIAUCNS",     key, "2017-01-01")
    out["cpi_raw_sa_series"]  = fetch_fred("CPIAUCSL",     key, "2017-01-01")
    out["debt_gdp_series"]    = fetch_fred("GFDEGDQ188S",  key, "2015-01-01")

    # ── Step 2: Yahoo Finance tickers ─────────────────────────────────────────
    print("\n[fetch] Yahoo Finance ---")
    yf_tickers = {
        "kre":  ("KRE",     "5y", 1.0),
        "tnx":  ("^TNX",    "5y", 1.0),   # 10-yr live
        "tyx":  ("^TYX",    "5y", 1.0),   # 30-yr live
        "irx":  ("^IRX",    "5y", 10.0),  # 13-wk T-bill → divide by 10 for %
        "spy":  ("SPY",     "5y", 1.0),
        "dxy":  ("DX-Y.NYB","5y", 1.0),   # ICE US Dollar Index, live
    }
    yf_data = {}
    for label, (ticker, period, div) in yf_tickers.items():
        s = fetch_yf_series(ticker, period=period)
        yf_data[label] = (s / div) if (len(s) > 0 and div != 1.0) else s

    # ── Step 3: KRE ───────────────────────────────────────────────────────────
    kre = yf_data["kre"]
    out["kre_series"]  = kre
    out["kre_current"] = latest(kre)
    out["kre_52w_high"] = (
        float(kre.tail(252).max()) if len(kre) >= 252
        else float(kre.max())      if len(kre) > 0
        else None
    )
    out["kre_decline_pct"] = (
        round((out["kre_52w_high"] - out["kre_current"])
              / out["kre_52w_high"] * 100, 1)
        if out["kre_current"] and out["kre_52w_high"] else None
    )

    # ── Step 3b: DXY (US Dollar Index) — live via Yahoo, with fallback ticker ──
    dxy = yf_data["dxy"]
    if len(dxy) == 0:
        # DX-Y.NYB occasionally fails on Yahoo; ICE dollar index futures track
        # the same underlying basket and rarely both fail at once.
        print("[dxy] DX-Y.NYB empty, trying DX=F fallback")
        dxy = fetch_yf_series("DX=F", period="5y")
    out["dxy_series"]  = dxy
    out["dxy_current"] = latest(dxy)
    out["dxy_52w_high"] = (
        float(dxy.tail(252).max()) if len(dxy) >= 252
        else float(dxy.max())      if len(dxy) > 0
        else None
    )
    out["dxy_52w_low"] = (
        float(dxy.tail(252).min()) if len(dxy) >= 252
        else float(dxy.min())      if len(dxy) > 0
        else None
    )
    # 20-trading-day % change — short-term momentum used by the dollar-vs-real-yield
    # divergence check in indicators.py
    if len(dxy) >= 21:
        out["dxy_20d_change_pct"] = round(
            (dxy.iloc[-1] / dxy.iloc[-21] - 1) * 100, 2
        )
    else:
        out["dxy_20d_change_pct"] = None

    # ── Step 4: Treasury yields (merge FRED history + Yahoo live) ─────────────
    # 10-yr
    tsy10_f = out.get("treasury_10y_series", pd.Series(dtype=float))
    tnx     = yf_data["tnx"]
    tsy10   = tsy10_f.combine_first(tnx).sort_index() if len(tsy10_f) > 0 and len(tnx) > 0 \
              else tnx if len(tnx) > 0 else tsy10_f
    out["treasury_10y_series"] = tsy10
    out["treasury_10y"]        = latest(tsy10)

    # 2-yr
    tsy2_f = out.get("treasury_2y_series", pd.Series(dtype=float))
    irx    = yf_data["irx"]
    tsy2   = tsy2_f.combine_first(irx).sort_index() if len(tsy2_f) > 0 and len(irx) > 0 \
             else irx if len(irx) > 0 else tsy2_f
    out["treasury_2y_series"] = tsy2
    out["treasury_2y"]        = latest(tsy2)

    # 30-yr
    tsy30_f = out.get("treasury_30y_series", pd.Series(dtype=float))
    tyx     = yf_data["tyx"]
    tsy30   = tsy30_f.combine_first(tyx).sort_index() if len(tsy30_f) > 0 and len(tyx) > 0 \
              else tyx if len(tyx) > 0 else tsy30_f
    out["treasury_30y_series"] = tsy30
    out["treasury_30y"]        = latest(tsy30)

    # ── Step 5: SPY + earnings yield ──────────────────────────────────────────
    spy = yf_data["spy"]
    out["spy_series"] = spy
    out["spy_latest"] = latest(spy)
    if len(spy) > 0:
        spy_ey = (230.0 / spy) * 100   # trailing EPS ~$230 (FactSet Q1 2026)
        out["spy_earnings_yield_series"] = spy_ey
        out["spy_earnings_yield"]        = latest(spy_ey)
    else:
        out["spy_earnings_yield_series"] = pd.Series(dtype=float)
        out["spy_earnings_yield"]        = None

    # ── Step 6: Derived macro scalars ─────────────────────────────────────────
    out["tips_real_yield"] = latest(out.get("tips_real_yield_series", pd.Series(dtype=float)))
    out["breakeven"]       = latest(out.get("breakeven_series",       pd.Series(dtype=float)))
    out["fed_funds"]       = latest(out.get("fed_funds_series",       pd.Series(dtype=float)))
    out["hy_spread"]       = latest(out.get("hy_spread_series",       pd.Series(dtype=float)))
    out["debt_gdp_pct"]    = latest(out.get("debt_gdp_series",        pd.Series(dtype=float)))

    # CPI YoY — NSA drives every downstream calculation (real_policy_rate,
    # scorecard). SA computed alongside purely so the app can display both.
    cpi_raw = out.get("cpi_raw_series", pd.Series(dtype=float))
    if len(cpi_raw) >= 12:
        cpi_yoy = (cpi_raw.pct_change(12) * 100).dropna()
        cpi_yoy = cpi_yoy[cpi_yoy.index >= START]
    else:
        cpi_yoy = pd.Series(dtype=float)
    out["cpi_yoy_series"] = cpi_yoy
    out["cpi_yoy"]        = latest(cpi_yoy)

    cpi_raw_sa = out.get("cpi_raw_sa_series", pd.Series(dtype=float))
    if len(cpi_raw_sa) >= 12:
        cpi_yoy_sa = (cpi_raw_sa.pct_change(12) * 100).dropna()
        cpi_yoy_sa = cpi_yoy_sa[cpi_yoy_sa.index >= START]
    else:
        cpi_yoy_sa = pd.Series(dtype=float)
    out["cpi_yoy_sa_series"] = cpi_yoy_sa
    out["cpi_yoy_sa"]        = latest(cpi_yoy_sa)

    # Real policy rate
    ffr = out.get("fed_funds_series", pd.Series(dtype=float))
    if out["fed_funds"] is not None and out["cpi_yoy"] is not None:
        out["real_policy_rate"] = round(out["fed_funds"] - out["cpi_yoy"], 2)
    else:
        out["real_policy_rate"] = None
    if len(ffr) > 0 and len(cpi_yoy) > 0:
        out["real_policy_rate_series"] = (
            ffr.resample("ME").last() - cpi_yoy.resample("ME").last()
        ).dropna()
    else:
        out["real_policy_rate_series"] = pd.Series(dtype=float)

    # Implied breakeven
    if out["treasury_10y"] is not None and out["tips_real_yield"] is not None:
        out["implied_breakeven"] = round(out["treasury_10y"] - out["tips_real_yield"], 2)
    else:
        out["implied_breakeven"] = out.get("breakeven")

    # Static CBO values
    out["deficit_gdp_pct"]  = 5.9
    out["interest_gdp_pct"] = 3.3

    # ── Step 6b: Treasury auction demand (10-yr note bid-to-cover) ────────────
    print("\n[fetch] Treasury auction bid-to-cover ---")
    auctions_10y = fetch_treasury_auctions("10-Year", n=16)
    out["auction_10y_df"] = auctions_10y
    if len(auctions_10y) > 0:
        out["auction_10y_btc_series"] = auctions_10y["bid_to_cover_ratio"]
        out["auction_10y_btc_latest"] = float(auctions_10y["bid_to_cover_ratio"].iloc[-1])
        if len(auctions_10y) >= 4:
            out["auction_10y_btc_avg4"] = round(
                float(auctions_10y["bid_to_cover_ratio"].tail(4).mean()), 2
            )
        else:
            out["auction_10y_btc_avg4"] = None
    else:
        out["auction_10y_btc_series"] = pd.Series(dtype=float)
        out["auction_10y_btc_latest"] = None
        out["auction_10y_btc_avg4"]   = None

    # ── Step 7: H.4.1 Balance sheet unit conversions ──────────────────────────
    # WALCL, TREAST, WSHOMCB, WTREGEN, WRESBAL → millions → convert to T or B
    # RRPONTSYD → already in billions
    print("\n[fetch] H.4.1 unit conversions ---")

    def _bs(raw_key, divisor, out_key, scalar_key):
        s_raw = out.get(raw_key, pd.Series(dtype=float))
        s     = (s_raw / divisor) if len(s_raw) > 0 else pd.Series(dtype=float)
        out[out_key]    = s
        out[scalar_key] = latest(s)
        lv = f"{out[scalar_key]:.3f}" if out[scalar_key] else "N/A"
        print(f"  {raw_key:15s} → {out_key:25s}: latest={lv}")

    _bs("bs_walcl_raw",    1e6, "bs_total_assets",   "bs_total_assets_latest")  # M→T
    _bs("bs_treast_raw",   1e6, "bs_treasuries",     "bs_treasuries_latest")    # M→T
    _bs("bs_mbs_raw",      1e6, "bs_mbs",            "bs_mbs_latest")           # M→T
    _bs("bs_tga_raw",      1e3, "bs_tga",            "bs_tga_latest")           # M→B
    _bs("bs_reserves_raw", 1e3, "bs_reserves",       "bs_reserves_latest")      # M→B
    _bs("bs_rrp_raw",      1.0, "bs_rrp",            "bs_rrp_latest")           # already B

    walcl_clean = out.get("bs_total_assets", pd.Series(dtype=float)).dropna()
    out["bs_wow_change_bn"] = (
        round((walcl_clean.iloc[-1] - walcl_clean.iloc[-2]) * 1000, 1)
        if len(walcl_clean) >= 2 else None
    )
    bs_peak = 8965.8   # billions
    out["bs_peak_bn"] = bs_peak
    ta = out.get("bs_total_assets_latest")
    out["bs_drawdown_pct"] = (
        round((bs_peak - ta * 1000) / bs_peak * 100, 1) if ta else None
    )
    out["bs_fetch_status"] = {
        "WALCL":     len(out.get("bs_walcl_raw",    pd.Series(dtype=float))),
        "TREAST":    len(out.get("bs_treast_raw",   pd.Series(dtype=float))),
        "WSHOMCB":   len(out.get("bs_mbs_raw",      pd.Series(dtype=float))),
        "WTREGEN":   len(out.get("bs_tga_raw",      pd.Series(dtype=float))),
        "WRESBAL":   len(out.get("bs_reserves_raw", pd.Series(dtype=float))),
        "RRPONTSYD": len(out.get("bs_rrp_raw",      pd.Series(dtype=float))),
    }

    # ── Step 8: Wealth asset tickers ──────────────────────────────────────────
    WEALTH_TICKERS = ["SCHP","GLD","VYM","VNQ","XLE","VEA","FLOT","IBIT","TLT","QQQ","VT"]
    print("\n[fetch] Wealth asset tickers ---")
    for tkr in WEALTH_TICKERS:
        s = fetch_yf_series(tkr, period="2y")
        out[f"wealth_{tkr}_series"] = s
        lv = f"{s.iloc[-1]:.2f}" if len(s) > 0 else "EMPTY"
        print(f"  {tkr:6s}: {len(s)} rows, latest={lv}")

    # ── Final summary ──────────────────────────────────────────────────────────
    print("\n=== fetch_all_indicators complete ===")
    for k in ["treasury_10y", "treasury_2y", "treasury_30y",
              "tips_real_yield", "breakeven", "fed_funds", "cpi_yoy", "cpi_yoy_sa",
              "real_policy_rate", "hy_spread", "debt_gdp_pct",
              "kre_current", "spy_latest", "dxy_current", "dxy_20d_change_pct",
              "auction_10y_btc_latest", "auction_10y_btc_avg4",
              "bs_total_assets_latest", "bs_wow_change_bn"]:
        v = out.get(k)
        print(f"  {k:30s}: {f'{v:.4f}' if isinstance(v, float) else v}")

    return out
