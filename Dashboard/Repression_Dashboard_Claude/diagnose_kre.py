"""
diagnose_kre.py
================
Run this FIRST before running the Streamlit app.
It will tell you exactly what yfinance returns on your machine
and which fetch method works.

Run:
    python diagnose_kre.py
"""

import sys
import pandas as pd

print("=" * 60)
print("DIAGNOSTIC: KRE data fetch")
print("=" * 60)

# ── 1. Python & pandas version ────────────────────────────────
print(f"\nPython  : {sys.version.split()[0]}")
print(f"Pandas  : {pd.__version__}")

# ── 2. yfinance version ───────────────────────────────────────
try:
    import yfinance as yf
    print(f"yfinance: {yf.__version__}")
except ImportError:
    print("yfinance: NOT INSTALLED — run: pip install yfinance")
    sys.exit(1)

# ── 3. Try every known method ─────────────────────────────────

TICKER = "KRE"
PERIOD = "5d"

print(f"\n{'─'*60}")
print(f"Testing ticker: {TICKER}  period: {PERIOD}")
print(f"{'─'*60}")

# ── Method A: download with multi_level_index=False ───────────
print("\n[A] yf.download(multi_level_index=False)")
try:
    import inspect
    params = list(inspect.signature(yf.download).parameters.keys())
    if "multi_level_index" not in params:
        print("    SKIP — multi_level_index param not available in this version")
    else:
        df = yf.download(TICKER, period=PERIOD, auto_adjust=True,
                         progress=False, multi_level_index=False)
        print(f"    Shape   : {df.shape}")
        print(f"    Columns : {df.columns.tolist()}")
        print(f"    Head    :\n{df.head(3)}")
        if "Close" in df.columns:
            s = df["Close"]
            print(f"    Close type : {type(s).__name__}")
            print(f"    Close dtype: {s.dtype}")
            if isinstance(s, pd.Series) and len(s) > 0:
                print(f"    ✅ SUCCESS — latest: {s.iloc[-1]:.2f}")
            else:
                print(f"    ❌ Close is not a usable Series")
        else:
            print("    ❌ No 'Close' column found")
except Exception as e:
    print(f"    ❌ Exception: {type(e).__name__}: {e}")

# ── Method B: Ticker.history() ────────────────────────────────
print("\n[B] yf.Ticker().history()")
try:
    t    = yf.Ticker(TICKER)
    hist = t.history(period=PERIOD, auto_adjust=True)
    print(f"    Shape   : {hist.shape}")
    print(f"    Columns : {hist.columns.tolist()}")
    print(f"    Index tz: {hist.index.tz}")
    if "Close" in hist.columns and len(hist) > 0:
        print(f"    ✅ SUCCESS — latest: {hist['Close'].iloc[-1]:.2f}")
    else:
        print("    ❌ No usable Close column")
        print(f"    Head:\n{hist.head(3)}")
except Exception as e:
    print(f"    ❌ Exception: {type(e).__name__}: {e}")

# ── Method C: download() default (MultiIndex) ─────────────────
print("\n[C] yf.download() default (MultiIndex expected)")
try:
    df = yf.download(TICKER, period=PERIOD, auto_adjust=True, progress=False)
    print(f"    Shape   : {df.shape}")
    print(f"    Columns : {df.columns.tolist()}")
    # Try tuple key
    for key in [("Close", TICKER), "Close"]:
        if key in df.columns:
            s = df[key]
            if isinstance(s, pd.Series) and len(s) > 0:
                print(f"    ✅ SUCCESS via key={key!r} — latest: {s.iloc[-1]:.2f}")
                break
    else:
        print("    ❌ Could not extract Close")
        print(f"    Head:\n{df.head(3)}")
except Exception as e:
    print(f"    ❌ Exception: {type(e).__name__}: {e}")

# ── Method D: fast_info (price only, no history) ──────────────
print("\n[D] yf.Ticker().fast_info['last_price']")
try:
    t = yf.Ticker(TICKER)
    price = t.fast_info["last_price"]
    print(f"    ✅ SUCCESS — last_price: {price:.2f}")
except Exception as e:
    print(f"    ❌ Exception: {type(e).__name__}: {e}")

# ── Method E: Ticker.history with explicit dates ──────────────
print("\n[E] yf.Ticker().history(start=..., end=...) with explicit dates")
try:
    import datetime
    end   = datetime.date.today()
    start = end - datetime.timedelta(days=10)
    t     = yf.Ticker(TICKER)
    hist  = t.history(start=str(start), end=str(end))
    print(f"    Shape   : {hist.shape}")
    if "Close" in hist.columns and len(hist) > 0:
        print(f"    ✅ SUCCESS — latest: {hist['Close'].iloc[-1]:.2f}")
    else:
        print(f"    ❌  Columns: {hist.columns.tolist()}")
except Exception as e:
    print(f"    ❌ Exception: {type(e).__name__}: {e}")

print(f"\n{'='*60}")
print("Copy and paste the output above and share it.")
print("It will show exactly which method works on your machine.")
print("="*60)
