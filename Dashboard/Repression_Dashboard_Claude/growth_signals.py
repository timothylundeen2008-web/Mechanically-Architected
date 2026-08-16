"""
growth_signals.py  (v1 — August 2026)
─────────────────────────────────────
The GROWTH axis — the input this framework has never had.

WHY THIS EXISTS
───────────────
Every branch in classify_regime() keys off the SHORT REAL RATE's sign,
plus credit, curve shape and long real yields. There is no growth input
anywhere. The consequence surfaced concretely on 2026-08-14: payrolls at
-23,000, retail sales down the most in over a year, and consumer sentiment
at 51.0 — an unambiguous growth scare — while the classifier could not
name it, because the `stagflation` branch requires a DECISIVELY NEGATIVE
short real rate and the rate was +0.27%.

That is a coverage gap by construction, not a bug: the classifier was built
around the financial-repression thesis, where the real-rate sign IS the
question. A macro-markets framework needs growth as a first-class axis.

WHAT IT MEASURES
────────────────
Four series, each casting a vote. No single one can dominate:

    PAYEMS    Nonfarm payrolls        — the labour market's level trend
    ICSA      Initial jobless claims  — the fastest-moving labour signal
    RSAFS     Retail sales            — the consumer, in dollars
    UMCSENT   Consumer sentiment      — the consumer, in expectations

Two labour + two consumer is deliberate. Labour turns first in most
cycles; the consumer confirms whether it is feeding through to spending.
Requiring agreement across both pairs is what separates a genuine growth
scare from one noisy print.

DESIGN RULES
────────────
1. VOTES, NOT A BLACK BOX. Each series maps to an integer vote via
   published thresholds, and every vote is reported with its reasoning.
   A composite that cannot be decomposed cannot be argued with.
2. NEVER FABRICATE. A series that fails to fetch casts NO vote and is
   named in `missing`. It is not silently scored zero — a missing input
   and a neutral input are different states.
3. DEGRADED CONFIDENCE. With fewer than 3 of 4 series live, the state is
   reported but flagged low-confidence, and the classifier's growth guard
   is written to require a CONFIRMED reading before it will act.
"""

from __future__ import annotations

from typing import Callable, Optional

FRED_GROWTH_SERIES = {
    "payrolls": "PAYEMS",       # thousands, monthly, SA
    "claims": "ICSA",           # weekly initial claims, SA
    "retail_sales": "RSAFS",    # millions $, monthly, SA
    "sentiment": "UMCSENT",     # index, monthly
}

# ── State constants ─────────────────────────────────────────────────────────
CONTRACTING = "CONTRACTING"
DETERIORATING = "DETERIORATING"
NEUTRAL = "NEUTRAL"
EXPANDING = "EXPANDING"
UNKNOWN = "UNKNOWN"

# ── Thresholds. Each is a pre-commitment, reviewable when calm. ─────────────
# Payrolls: 3-month average monthly change, thousands.
PAYROLLS_CONTRACT = 0.0        # 3mo avg negative
PAYROLLS_WEAK = 50.0           # below trend replacement
PAYROLLS_STRONG = 150.0

# Initial claims: 4-week MA, percent change vs one year ago.
CLAIMS_RISING_HARD = 15.0      # +15% YoY — historically recessionary
CLAIMS_FALLING = -10.0

# Retail sales: 3-month percent change (nominal).
RETAIL_WEAK = -0.5
RETAIL_STRONG = 1.5

# Sentiment: level, and 3-month percent change.
SENTIMENT_DEPRESSED = 60.0
SENTIMENT_COLLAPSE_3M = -12.0


def _vote(name: str, vote: int, reading: str, detail: str) -> dict:
    return {"name": name, "vote": vote, "reading": reading, "detail": detail}


def _pct_change(series, periods: int) -> Optional[float]:
    try:
        s = series.dropna()
        if len(s) <= periods:
            return None
        return float(s.iloc[-1] / s.iloc[-1 - periods] - 1) * 100
    except Exception:
        return None


def _last(series) -> Optional[float]:
    try:
        s = series.dropna()
        return float(s.iloc[-1]) if len(s) else None
    except Exception:
        return None


# ── Individual signal scoring ───────────────────────────────────────────────
def score_payrolls(series) -> Optional[dict]:
    """3-month average monthly change in nonfarm payrolls."""
    try:
        s = series.dropna()
        if len(s) < 4:
            return None
        recent = s.diff().dropna().iloc[-3:]
        avg = float(recent.mean())
    except Exception:
        return None

    if avg < PAYROLLS_CONTRACT:
        v, d = -2, (f"3-month average payroll change is NEGATIVE ({avg:+.0f}k/mo). "
                    f"The labour market is shedding jobs, not merely slowing.")
    elif avg < PAYROLLS_WEAK:
        v, d = -1, (f"3-month average {avg:+.0f}k/mo is below the ~{PAYROLLS_WEAK:.0f}k "
                    f"pace that absorbs labour-force growth.")
    elif avg > PAYROLLS_STRONG:
        v, d = 1, f"3-month average {avg:+.0f}k/mo is a firm expansion pace."
    else:
        v, d = 0, f"3-month average {avg:+.0f}k/mo — moderate, neither hot nor cold."
    return _vote("Payrolls (3mo avg)", v, f"{avg:+.0f}k/mo", d)


def score_claims(series) -> Optional[dict]:
    """4-week MA of initial claims vs one year ago."""
    try:
        s = series.dropna()
        if len(s) < 56:
            return None
        ma4 = s.rolling(4).mean().dropna()
        now = float(ma4.iloc[-1])
        yr_ago = float(ma4.iloc[-53]) if len(ma4) > 53 else None
        if yr_ago is None or yr_ago == 0:
            return None
        yoy = (now / yr_ago - 1) * 100
    except Exception:
        return None

    if yoy > CLAIMS_RISING_HARD:
        v, d = -2, (f"4-week average claims are {yoy:+.0f}% above a year ago — "
                    f"a rise of this size has historically accompanied recessions.")
    elif yoy > 5:
        v, d = -1, f"Claims {yoy:+.0f}% YoY — layoffs are picking up at the margin."
    elif yoy < CLAIMS_FALLING:
        v, d = 1, f"Claims {yoy:+.0f}% YoY — the labour market is tightening."
    else:
        v, d = 0, f"Claims {yoy:+.0f}% YoY — broadly stable."
    return _vote("Initial claims (4wk MA, YoY)", v, f"{now:,.0f} ({yoy:+.0f}% YoY)", d)


def score_retail(series) -> Optional[dict]:
    """3-month change in retail sales. Nominal — see the caveat below."""
    chg = _pct_change(series, 3)
    if chg is None:
        return None
    if chg < RETAIL_WEAK:
        v, d = -2, (f"Retail sales {chg:+.1f}% over 3 months. NOTE: this is "
                    f"NOMINAL — with CPI positive, a negative nominal figure "
                    f"means real consumption is falling faster still.")
    elif chg < 0.5:
        v, d = -1, (f"Retail sales {chg:+.1f}% over 3 months — barely positive "
                    f"nominally, likely negative in real terms.")
    elif chg > RETAIL_STRONG:
        v, d = 1, f"Retail sales {chg:+.1f}% over 3 months — real consumption growing."
    else:
        v, d = 0, f"Retail sales {chg:+.1f}% over 3 months — flat in real terms."
    return _vote("Retail sales (3mo)", v, f"{chg:+.1f}%", d)


def score_sentiment(series) -> Optional[dict]:
    """UMich consumer sentiment: level plus 3-month direction."""
    lvl = _last(series)
    chg = _pct_change(series, 3)
    if lvl is None:
        return None

    if lvl < SENTIMENT_DEPRESSED and (chg is not None and chg < SENTIMENT_COLLAPSE_3M):
        v, d = -2, (f"Sentiment at {lvl:.1f} AND falling {chg:+.0f}% over 3 months "
                    f"— depressed and deteriorating together.")
    elif lvl < SENTIMENT_DEPRESSED:
        v, d = -1, (f"Sentiment {lvl:.1f} is historically depressed (below "
                    f"{SENTIMENT_DEPRESSED:.0f}).")
    elif chg is not None and chg < SENTIMENT_COLLAPSE_3M:
        v, d = -1, f"Sentiment fell {chg:+.0f}% over 3 months — a sharp turn."
    elif lvl > 85:
        v, d = 1, f"Sentiment {lvl:.1f} — consumers are confident."
    else:
        v, d = 0, f"Sentiment {lvl:.1f} — middling."
    return _vote("Consumer sentiment (UMich)", v, f"{lvl:.1f}", d)


# ── Composite ───────────────────────────────────────────────────────────────
def assess(fetch_fred: Callable, api_key: str = "",
           start: str = "2015-01-01") -> dict:
    """
    Fetch all four series and produce the composite growth state.

    Returns a dict, always. Never raises — a failed series is named in
    `missing` and casts no vote.
    """
    out = {"votes": [], "missing": [], "score": 0, "state": UNKNOWN,
           "confirmed": False, "detail": "", "headline": ""}

    scorers = [
        ("payrolls", score_payrolls),
        ("claims", score_claims),
        ("retail_sales", score_retail),
        ("sentiment", score_sentiment),
    ]

    for key, scorer in scorers:
        series_id = FRED_GROWTH_SERIES[key]
        try:
            s = fetch_fred(series_id, api_key, start)
            if s is None or len(s.dropna()) == 0:
                out["missing"].append(series_id)
                continue
            v = scorer(s)
            if v is None:
                out["missing"].append(f"{series_id} (insufficient history)")
            else:
                out["votes"].append(v)
        except Exception as e:
            out["missing"].append(f"{series_id} ({type(e).__name__})")

    n = len(out["votes"])
    if n == 0:
        out["detail"] = ("No growth series available — the growth axis is DARK. "
                        "This is a degraded read, not a benign one.")
        out["headline"] = "Growth: unavailable"
        return out

    score = sum(v["vote"] for v in out["votes"])
    out["score"] = score

    # CONFIRMED requires at least 3 of 4 live. The classifier's growth guard
    # acts only on a confirmed reading — a single surviving series should
    # never be able to move a regime on its own.
    out["confirmed"] = n >= 3

    if score <= -4:
        out["state"] = CONTRACTING
    elif score <= -2:
        out["state"] = DETERIORATING
    elif score >= 2:
        out["state"] = EXPANDING
    else:
        out["state"] = NEUTRAL

    neg = [v["name"] for v in out["votes"] if v["vote"] < 0]
    pos = [v["name"] for v in out["votes"] if v["vote"] > 0]

    out["detail"] = (
        f"Composite {score:+d} from {n} of 4 series"
        + (f" · negative: {', '.join(neg)}" if neg else "")
        + (f" · positive: {', '.join(pos)}" if pos else "")
        + ("" if out["confirmed"] else
           f" · ⚠ UNCONFIRMED — only {n} of 4 series live, so the classifier's "
           f"growth guard will not act on this.")
    )
    out["headline"] = f"Growth: {out['state']} ({score:+d})"
    if out["missing"]:
        out["headline"] += f" · missing: {', '.join(out['missing'])}"
    return out


def selftest() -> dict:
    """Verify the scoring thresholds against constructed series."""
    import pandas as pd
    import numpy as np
    failures = []

    idx = pd.date_range("2024-01-01", periods=40, freq="MS")

    # Payrolls shedding jobs -> must score -2
    shrinking = pd.Series(np.concatenate([
        np.linspace(150000, 158000, 37), [157950, 157900, 157850]]), index=idx)
    r = score_payrolls(shrinking)
    if not r or r["vote"] != -2:
        failures.append(f"payrolls contraction: got {r['vote'] if r else None}")

    # Strong payrolls -> +1
    strong = pd.Series(np.linspace(150000, 157200, 40), index=idx)
    r = score_payrolls(strong)
    if not r or r["vote"] != 1:
        failures.append(f"payrolls strong: got {r['vote'] if r else None}")

    # Depressed + collapsing sentiment -> -2
    sent = pd.Series(list(np.linspace(75, 70, 37)) + [62, 56, 51], index=idx)
    r = score_sentiment(sent)
    if not r or r["vote"] != -2:
        failures.append(f"sentiment collapse: got {r['vote'] if r else None}")

    # Retail sales falling -> -2
    retail = pd.Series(list(np.linspace(700000, 765000, 37))
                      + [764000, 762000, 759000], index=idx)
    r = score_retail(retail)
    if not r or r["vote"] != -2:
        failures.append(f"retail falling: got {r['vote'] if r else None}")

    # Missing series must not fabricate a vote
    fake = assess(lambda *a, **k: None)
    if fake["state"] != UNKNOWN or fake["confirmed"]:
        failures.append("all-missing case did not degrade correctly")

    return {"ok": not failures, "failures": failures}


if __name__ == "__main__":
    import json
    print(json.dumps(selftest(), indent=2, default=str))
