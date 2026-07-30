"""
credit_history.py  (v1 — July 2026)
===================================
Credit-spread history with an explicit COVERAGE contract.

THE PROBLEM
-----------
FRED restricted every ICE BofA index series to a rolling three-year window in
April 2026. The full BAMLH0A0HYM2 history back to December 1996 is no longer
distributed through the FRED API.

Nothing in the existing code notices. rep_app.py requests the series from
"2019-01-01" and slices .tail(1260). The request SUCCEEDS. The chart renders.
The y-axis autoscales. A panel labelled as five years of credit history now
shows three — and the three it shows contain no credit stress whatsoever.

WHY THAT CHANGES A DECISION
---------------------------
The whole purpose of a spread reading is percentile context. HY OAS at 2.77%
(23 July 2026):

  Against the 3-year FRED window
      range low  2.59% (January 2025)
      range high 4.61% (April 2025)
      -> roughly the 9th percentile of a 202bp range. Reads as "tight-ish".
         Unremarkable. Nothing to see.

  Against the full 1996-2026 history
      range low  ~2.41% (June 2007)
      range high 21.82% (15 December 2008)
      -> roughly the 2nd percentile. Reads as "at the tightest level in the
         entire modern history of the index, matched only by June 2007".

June 2007 is not trivia. It is THE analogue for spreads this tight, and what
followed it is the single most instructive fact a credit-spread panel can
convey. Without pre-2023 data you cannot see it — and if HY OAS is the
load-bearing input for whether an equity drawdown is a positioning unwind or
the front edge of a credit event, the 3-year window will tell you the wrong
thing at exactly the moment it matters.

VERDICT: the history is worth keeping. It is one CSV, committed once, with no
ongoing maintenance, and it is the difference between "tight-ish" and "ties the
2007 record".

HOW TO GET THE CSV
------------------
1. Download the full series while any archived copy is reachable:
     - FRED's series page still offers a full-history CSV download in the
       browser even though the API is windowed
     - or ICE/BofA via a data vendor, or an existing local copy
2. Save as: data/hy_oas_history.csv with columns  date,value
     value in PERCENT (2.77 means 277bp) to match the FRED convention already
     used throughout this codebase
3. Commit it. It is ~7,600 rows, well under a megabyte.

The module works WITHOUT the CSV — it just reports coverage="windowed" and
refuses to emit a full-history percentile, which is the honest failure mode.
"""

from __future__ import annotations

import io
import os
import sys
from typing import Callable, Optional

import pandas as pd

STATIC_FILE = "hy_oas_history.csv"
IG_STATIC_FILE = "ig_oas_history.csv"

# Coverage classes
COVERAGE_FULL = "full"          # pre-2010 data present
COVERAGE_PARTIAL = "partial"    # more than the window, less than full
COVERAGE_WINDOWED = "windowed"  # FRED's 3-year window only
COVERAGE_NONE = "none"

# The minimum span, in years, we require before calling a percentile
# "full-history". 15 years gets you at least one genuine credit cycle.
FULL_HISTORY_MIN_YEARS = 15

# Documented reference points, used for context when the static CSV is absent.
# These are NOT computed from data at runtime — they are published extremes,
# recorded here so a windowed deployment still shows the reader what the
# window is hiding.
REFERENCE_ANCHORS = {
    "record_wide": {"value": 21.82, "when": "2008-12-15",
                    "note": "GFC peak — the widest print in the modern series."},
    "gfc_onset": {"value": 5.00, "when": "2007-2008",
                  "note": "The 500bp line the liquidity_crisis branch uses as "
                          "its trigger."},
    "record_tight": {"value": 2.41, "when": "June 2007",
                     "note": "Tightest print in the modern series. The only "
                             "period comparable to today, and the last one "
                             "before spreads went to 2,182bp in 18 months."},
    "complacency_line": {"value": 3.50, "when": "—",
                         "note": "Below 350bp is the framework's late-cycle "
                                 "complacency threshold and the +1 point in "
                                 "the repression score."},
    "window_low": {"value": 2.59, "when": "January 2025",
                   "note": "Low of FRED's surviving 3-year window."},
    "window_high": {"value": 4.61, "when": "April 2025",
                    "note": "High of FRED's surviving 3-year window."},
}


# --------------------------------------------------------------------------- #
#  Loading
# --------------------------------------------------------------------------- #
def _read_static(filename: str, data_dir: str = "data") -> pd.Series:
    """Read the committed history file. Empty Series when absent — never raises.

    Tries storage_backend first (so a GitHub-backed deployment picks it up),
    then the local filesystem.
    """
    try:
        import storage_backend as sb
        txt = sb.read_text(filename)
        if txt:
            df = pd.read_csv(io.StringIO(txt))
            return _to_series(df)
    except Exception as e:
        print(f"[credit_history] storage_backend read failed: {e}", file=sys.stderr)

    path = os.path.join(data_dir, filename)
    try:
        if os.path.exists(path):
            return _to_series(pd.read_csv(path))
    except Exception as e:
        print(f"[credit_history] local read failed for {path}: {e}", file=sys.stderr)
    return pd.Series(dtype=float)


def _to_series(df: pd.DataFrame) -> pd.Series:
    """Normalize a two-column date,value frame to a float Series."""
    if df is None or df.empty:
        return pd.Series(dtype=float)
    cols = {c.lower().strip(): c for c in df.columns}
    dcol = cols.get("date") or list(df.columns)[0]
    vcol = cols.get("value") or cols.get("oas") or list(df.columns)[-1]
    out = pd.Series(
        pd.to_numeric(df[vcol], errors="coerce").values,
        index=pd.to_datetime(df[dcol], errors="coerce"),
        name="hy_oas",
    ).dropna()
    return out[~out.index.duplicated(keep="last")].sort_index()


def load_series(fetch_fred: Optional[Callable] = None,
                api_key: str = "",
                series_id: str = "BAMLH0A0HYM2",
                static_filename: str = STATIC_FILE,
                data_dir: str = "data") -> dict:
    """
    Build the longest available series and DECLARE its coverage.

    Static history and the live window are spliced: static provides depth,
    live provides the last three years including today. Where they overlap the
    LIVE value wins, because it reflects any revision.

    Returns a dict, always:
        series          pd.Series (may be empty)
        coverage        COVERAGE_* constant
        start / end     Timestamps or None
        span_years      float
        n_static / n_live
        detail          display string
        warning         display string, empty when coverage is full
    """
    static = _read_static(static_filename, data_dir)

    live = pd.Series(dtype=float)
    if fetch_fred is not None:
        try:
            live = fetch_fred(series_id, api_key, "1996-01-01")
            live = pd.Series(live.squeeze() if hasattr(live, "squeeze") else live)
            live = live.astype(float).dropna()
        except Exception as e:
            print(f"[credit_history] live fetch failed: {e}", file=sys.stderr)
            live = pd.Series(dtype=float)

    if len(static) and len(live):
        merged = pd.concat([static[~static.index.isin(live.index)], live])
        merged = merged.sort_index()
    elif len(live):
        merged = live
    else:
        merged = static

    out = {"series": merged, "n_static": len(static), "n_live": len(live),
           "start": None, "end": None, "span_years": 0.0,
           "coverage": COVERAGE_NONE, "detail": "", "warning": ""}

    if merged.empty:
        out["detail"] = ("No credit-spread history available from either the "
                         "committed CSV or FRED.")
        out["warning"] = ("HY OAS unavailable — the liquidity-crisis branch and "
                          "the credit leg of the repression score cannot be "
                          "evaluated. This degrades the regime read; it does "
                          "not make credit calm.")
        return out

    start, end = merged.index.min(), merged.index.max()
    span = (end - start).days / 365.25
    out.update(start=start, end=end, span_years=round(span, 1))

    if span >= FULL_HISTORY_MIN_YEARS and start.year <= 2010:
        out["coverage"] = COVERAGE_FULL
    elif span > 3.5:
        out["coverage"] = COVERAGE_PARTIAL
    else:
        out["coverage"] = COVERAGE_WINDOWED

    out["detail"] = (f"{len(merged):,} observations, "
                     f"{start:%Y-%m-%d} to {end:%Y-%m-%d} "
                     f"({span:.1f} years). "
                     f"static={len(static):,} live={len(live):,}")

    if out["coverage"] != COVERAGE_FULL:
        out["warning"] = (
            f"COVERAGE: {out['coverage'].upper()} — only {span:.1f} years. FRED "
            f"restricted ICE BofA series to a rolling 3-year window in April "
            f"2026, and that window contains no credit stress. Percentiles "
            f"computed against it are NOT comparable to the published "
            f"thresholds. Commit data/{static_filename} to restore full "
            f"context. Today's 2.77% reads as the ~9th percentile of the "
            f"window and the ~2nd percentile of the full history — the same "
            f"number, two different decisions."
        )
    return out


# --------------------------------------------------------------------------- #
#  Percentile with a coverage contract
# --------------------------------------------------------------------------- #
def percentile(value: Optional[float], loaded: dict,
               require_full: bool = True) -> dict:
    """
    Percentile rank of `value` within the loaded history.

    require_full=True (the default, and the right default) returns
    available=False when coverage is not FULL, rather than handing back a
    number computed against three quiet years. A refused percentile is
    recoverable; a wrong one propagates into sizing.
    """
    out = {"available": False, "value": value, "pct_rank": None,
           "range_position_pct": None, "coverage": loaded.get("coverage"),
           "n": 0, "detail": "", "context": ""}

    s = loaded.get("series", pd.Series(dtype=float))
    if value is None:
        out["detail"] = "No value supplied."
        return out
    if s is None or s.empty:
        # No history at all — but a level still means something against the
        # published extremes, so give the reader that rather than nothing.
        out["detail"] = ("No history loaded, so no percentile. Showing "
                         "published anchors only.")
        out["context"] = _anchor_context(value)
        return out

    out["n"] = len(s)

    if require_full and loaded.get("coverage") != COVERAGE_FULL:
        out["detail"] = (
            f"Percentile REFUSED: coverage is "
            f"'{loaded.get('coverage')}', not '{COVERAGE_FULL}'. A percentile "
            f"against a 3-year window with no stress in it would read as "
            f"reassuring regardless of the level. Showing raw level and "
            f"published anchors instead."
        )
        out["context"] = _anchor_context(value)
        return out

    lo, hi = float(s.min()), float(s.max())
    out.update(
        available=True,
        pct_rank=round(float((s <= value).mean()) * 100.0, 1),
        range_position_pct=round((value - lo) / (hi - lo) * 100.0, 1)
        if hi > lo else None,
    )
    out["detail"] = (f"{value:.2f}% is the {out['pct_rank']:.1f} percentile of "
                     f"{len(s):,} observations spanning "
                     f"{loaded['span_years']:.1f} years "
                     f"(range {lo:.2f}%-{hi:.2f}%).")
    out["context"] = _anchor_context(value)
    return out


def _anchor_context(value: float) -> str:
    """Place a level against published extremes. Works with zero history."""
    a = REFERENCE_ANCHORS
    bits = []
    if value <= a["record_tight"]["value"] + 0.40:
        bits.append(
            f"At {value:.2f}% this is within 40bp of the modern record tight "
            f"({a['record_tight']['value']:.2f}%, {a['record_tight']['when']}). "
            f"{a['record_tight']['note']}"
        )
    if value < a["complacency_line"]["value"]:
        bits.append(
            f"Below the {a['complacency_line']['value']:.2f}% complacency line "
            f"— earns the credit point in the repression score and signals "
            f"late-cycle risk compression, not safety."
        )
    if value >= a["gfc_onset"]["value"]:
        bits.append(
            f"At or beyond the {a['gfc_onset']['value']:.2f}% line that trips "
            f"the liquidity_crisis branch."
        )
    return " ".join(bits)


def read(value: Optional[float], fetch_fred: Optional[Callable] = None,
         api_key: str = "", **kw) -> dict:
    """One-call convenience: load, then percentile, then merge for the UI."""
    loaded = load_series(fetch_fred=fetch_fred, api_key=api_key, **kw)
    pct = percentile(value, loaded)
    return {
        "value": value,
        "coverage": loaded["coverage"],
        "coverage_detail": loaded["detail"],
        "coverage_warning": loaded["warning"],
        "span_years": loaded["span_years"],
        "percentile_available": pct["available"],
        "pct_rank": pct["pct_rank"],
        "percentile_detail": pct["detail"],
        "context": pct["context"],
        "series": loaded["series"],
    }


def selftest(fetch_fred: Optional[Callable] = None, api_key: str = "") -> dict:
    """Confirm the coverage guard actually refuses a windowed percentile."""
    loaded = load_series(fetch_fred=fetch_fred, api_key=api_key)
    pct = percentile(2.77, loaded)
    failures = []
    if loaded["coverage"] == COVERAGE_WINDOWED and pct["available"]:
        failures.append("Windowed coverage produced a percentile — guard failed")
    if loaded["coverage"] == COVERAGE_FULL and not pct["available"]:
        failures.append("Full coverage refused a percentile — guard too strict")
    return {"ok": not failures, "failures": failures,
            "coverage": loaded["coverage"], "span_years": loaded["span_years"],
            "detail": loaded["detail"], "warning": loaded["warning"],
            "percentile": pct}


if __name__ == "__main__":
    import json
    print(json.dumps(selftest(), indent=2, default=str))
