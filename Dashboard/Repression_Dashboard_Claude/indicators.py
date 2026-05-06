"""
indicators.py
==============
Scoring logic: takes raw data from data_fetcher and produces
a structured scorecard dict with status, bar_pct, reading, notes.

Also holds the static WATCHLIST and CATALYSTS data.
"""

from __future__ import annotations
from typing import Any


# ─── Status thresholds ────────────────────────────────────────────────────────

def _clamp(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, val))


def score_debt_gdp(pct: float | None) -> dict:
    if pct is None:
        return _unknown("Debt-to-GDP ratio")
    status = "red" if pct >= 105 else "amber" if pct >= 90 else "green"
    bar    = _clamp((pct / 130) * 100)
    return {
        "name":      "Debt-to-GDP ratio",
        "sub":       "Repression becomes systemic above 100% · Historical alarm: 106% (1946 WWII peak)",
        "reading":   f"{pct:.1f}% {'⚠' if status == 'red' else ''}",
        "status":    status,
        "bar_pct":   bar,
        "bar_left":  f"Current: {pct:.1f}%",
        "bar_right": "Threshold: 100%",
        "note": (
            f"Latest reading: {pct:.1f}% of GDP. IMF projects this exceeds 140% by 2031. "
            "Already above the 1946 WWII peak of 106%. Once past 100%, banks absorb "
            "~100% of incremental government debt — the core mechanism of repression. "
            f"{'Full repression threshold: BREACHED.' if pct >= 100 else 'Approaching threshold.'}"
        ),
        "weight": 2,
        "score_contrib": 2 if pct >= 100 else 1 if pct >= 90 else 0,
    }


def score_deficit(pct: float | None) -> dict:
    if pct is None:
        return _unknown("Fiscal deficit (% of GDP)")
    status = "red" if pct >= 5.0 else "amber" if pct >= 3.5 else "green"
    bar    = _clamp((pct / 7.0) * 100)
    return {
        "name":      "Fiscal deficit (% of GDP)",
        "sub":       "Repression likely above 5% · 50-year average: 3.8% · Fiscal austerity politically impossible",
        "reading":   f"{pct:.1f}% GDP {'⚠' if status == 'red' else ''}",
        "status":    status,
        "bar_pct":   bar,
        "bar_left":  f"Current: {pct:.1f}%",
        "bar_right": "Threshold: 5%",
        "note": (
            f"FY2025 deficit: {pct:.1f}% of GDP. CBO projects 5.8% in 2026, rising to 6.7% by 2036. "
            "50-year historical average: 3.8%. Structural, not cyclical — no revenue path closes this "
            "without austerity (politically impossible) or monetization (repression). "
            f"{'Full repression threshold: essentially breached.' if pct >= 5 else 'Elevated but below critical threshold.'}"
        ),
        "weight": 2,
        "score_contrib": 2 if pct >= 5 else 1 if pct >= 3.5 else 0,
    }


def score_interest_gdp(pct: float | None) -> dict:
    if pct is None:
        return _unknown("Net interest expense (% of GDP)")
    status = "red" if pct >= 3.2 else "amber" if pct >= 2.5 else "green"
    bar    = _clamp((pct / 4.0) * 100)
    return {
        "name":      "Net interest expense (% of GDP)",
        "sub":       "Previous post-WWII high: 3.2% (1991) · Historical avg: 2.1%",
        "reading":   f"{pct:.1f}% GDP {'⚠' if status == 'red' else ''}",
        "status":    status,
        "bar_pct":   bar,
        "bar_left":  f"Current: {pct:.1f}%",
        "bar_right": "Prior record: 3.2%",
        "note": (
            f"Net interest: {pct:.1f}% of GDP (~$1 trillion in 2026). "
            "Now the 2nd-largest spending category — above defense. "
            "Consumes ~18.6% of all federal revenues. "
            "Projected to double to $2.1T by 2036. "
            f"{'All-time post-WWII record.' if pct >= 3.2 else 'Elevated and rising rapidly.'}"
        ),
        "weight": 1,
        "score_contrib": 1 if pct >= 3.2 else 0,
    }


def score_real_policy_rate(rate: float | None, fed_funds: float | None, cpi: float | None) -> dict:
    if rate is None:
        return _unknown("Real interest rate (Fed funds − CPI)")
    status = "red" if rate <= 0 else "amber" if rate <= 1.5 else "green"
    # bar = how close to zero (repression threshold)
    bar = _clamp(((2.0 - rate) / 4.0) * 100) if rate <= 2.0 else 10
    ffr_str = f"{fed_funds:.2f}%" if fed_funds else "N/A"
    cpi_str = f"{cpi:.1f}%" if cpi else "N/A"
    return {
        "name":      "Real interest rate (Fed funds − CPI)",
        "sub":       f"Fed funds: {ffr_str} · CPI YoY: {cpi_str} · Repression = negative real rate",
        "reading":   f"~{rate:+.2f}% {'⚠' if status == 'red' else ''}",
        "status":    status,
        "bar_pct":   bar,
        "bar_left":  f"Current: {rate:+.2f}%",
        "bar_right": "Trigger: 0%",
        "note": (
            f"Real policy rate = {ffr_str} (Fed funds) minus {cpi_str} (CPI YoY) = {rate:+.2f}%. "
            f"{'REPRESSION ACTIVE: real rates are negative — savers are being taxed by inflation.' if rate <= 0 else ''}"
            f"{'Marginally positive — approaching repression zone. New Fed chair (May 2026) expected to cut aggressively, which could flip this negative within 12–18 months.' if 0 < rate <= 1.5 else ''}"
            f"{'Real rates positive and comfortable — repression not yet active via rate channel.' if rate > 1.5 else ''}"
        ),
        "weight": 2,
        "score_contrib": 2 if rate <= 0 else 1 if rate <= 1.5 else 0,
    }


def score_tips_real_yield(yld: float | None) -> dict:
    if yld is None:
        return _unknown("10-yr TIPS real yield")
    status = "red" if yld <= 0 else "amber" if yld <= 1.0 else "green"
    bar    = _clamp(((2.5 - yld) / 4.0) * 100) if yld <= 2.5 else 5
    return {
        "name":      "10-yr TIPS real yield (DFII10)",
        "sub":       "Repression active when negative · Peak repression: −1.6% (2021) · Source: FRED DFII10",
        "reading":   f"{yld:.2f}% {'⚠' if status == 'red' else ''}",
        "status":    status,
        "bar_pct":   bar,
        "bar_left":  f"Current: {yld:.2f}%",
        "bar_right": "Trigger: 0%",
        "note": (
            f"10-yr TIPS real yield: {yld:.2f}%. "
            f"{'CRITICAL: Real yields negative — markets are actively pricing in repression. Savers face guaranteed purchasing-power destruction.' if yld <= 0 else ''}"
            f"{'Approaching repression zone. Watch for further decline below 1%.' if 0 < yld <= 1.0 else ''}"
            f"{'Positive and historically elevated — markets not yet pricing repression. This is the last window to lock in positive real yields cheaply.' if yld > 1.0 else ''}"
            " This is the single best leading indicator: when it trends toward zero, repression is activating."
        ),
        "weight": 2,
        "score_contrib": 2 if yld <= 0 else 1 if yld <= 1.0 else 0,
    }


def score_fed_independence() -> dict:
    """Static scoring — Fed chair succession is event-based."""
    return {
        "name":      "Fed independence (chair succession)",
        "sub":       "Powell term ends May 2026 · Trump nominee expected to be dovish · 'Litmus test' for rate cuts",
        "reading":   "High risk ⚠",
        "status":    "red",
        "bar_pct":   90,
        "bar_left":  "Risk level: High",
        "bar_right": "Trigger: Chair confirmed",
        "note": (
            "Powell's term as Fed chair ends May 2026. Trump has stated immediate rate cuts are a "
            "'litmus test' for his nominee. Markets are already pricing more dovish policy in H2 2026. "
            "A new chair pushing the terminal rate below 3% would flip real rates negative and "
            "activate repression. This is the most important near-term event to monitor. "
            "Watch: confirmation hearing language on 'neutral rate' and 'r-star'."
        ),
        "weight": 2,
        "score_contrib": 1,  # partial — event hasn't occurred yet
    }


def score_structural_tools() -> dict:
    """Static scoring — SLR reform / regulatory tools."""
    return {
        "name":      "Structural repression tools (SLR reform, QE framework)",
        "sub":       "Regulatory machinery being assembled to force bank Treasury purchases",
        "reading":   "In progress",
        "status":    "amber",
        "bar_pct":   60,
        "bar_left":  "Assembly: ~60%",
        "bar_right": "Trigger: SLR enacted",
        "note": (
            "SLR (Supplementary Leverage Ratio) exemption reforms under discussion would force banks "
            "to absorb Treasuries at below-market rates — the post-WWII Regulation Q equivalent. "
            "Stablecoin regulation directing crypto toward T-bills. Digital asset frameworks. "
            "All channel demand to government debt at suppressed yields. "
            "Watch: Federal Reserve regulatory announcements weekly."
        ),
        "weight": 1,
        "score_contrib": 1,
    }


def score_market_pricing(breakeven: float | None, hy_spread: float | None) -> dict:
    if breakeven is None and hy_spread is None:
        return _unknown("Market pricing of repression")

    be_str = f"{breakeven:.2f}%" if breakeven else "N/A"
    hy_str = f"{hy_spread:.2f}%" if hy_spread else "N/A"

    # Markets are alert if breakevens > 3% OR spreads < 2% (risk-on ignoring debt risk)
    status = "amber" if (breakeven and breakeven > 3.0) else "green"
    bar    = _clamp(((breakeven or 2.25) / 3.5) * 100 * 0.5)

    return {
        "name":      "Market pricing of repression (breakevens, credit spreads)",
        "sub":       f"10-yr breakeven: {be_str} · HY OAS: {hy_str} · Alert: breakeven > 3%, spreads widening",
        "reading":   f"Not priced {'⚠' if status == 'amber' else ''}",
        "status":    status,
        "bar_pct":   bar,
        "bar_left":  f"Breakeven: {be_str}",
        "bar_right": "Alert: 3%+",
        "note": (
            f"10-yr breakeven inflation: {be_str}. HY credit spread (OAS): {hy_str}. "
            "Markets are NOT yet fully pricing in repression — breakevens below 3% suggest "
            "modest inflation expectations. HY spreads calm = credit markets not stressed. "
            "This is either an opportunity or complacency — historically, markets misprice "
            "repression until it is already underway. Watch for breakevens to spike sharply "
            "as the new Fed chair signals policy direction."
        ),
        "weight": 1,
        "score_contrib": 0,
    }


def _unknown(name: str) -> dict:
    return {
        "name": name, "sub": "Data unavailable",
        "reading": "N/A", "status": "amber",
        "bar_pct": 0, "bar_left": "No data", "bar_right": "",
        "note": "Could not fetch data for this indicator. Check your internet connection or FRED API key.",
        "weight": 1, "score_contrib": 0,
    }


# ─── Master scorecard builder ──────────────────────────────────────────────────

def build_scorecard(raw: dict) -> dict:
    """
    Given raw data dict from fetch_all_indicators(), return a structured
    scorecard with per-indicator scores and an overall 0-10 score.
    """
    indicators = [
        score_debt_gdp(raw.get("debt_gdp_pct")),
        score_deficit(raw.get("deficit_gdp_pct")),
        score_interest_gdp(raw.get("interest_gdp_pct")),
        score_real_policy_rate(
            raw.get("real_policy_rate"),
            raw.get("fed_funds"),
            raw.get("cpi_yoy"),
        ),
        score_tips_real_yield(raw.get("tips_real_yield")),
        score_fed_independence(),
        score_structural_tools(),
        score_market_pricing(raw.get("breakeven"), raw.get("hy_spread")),
    ]

    total_contrib = sum(i["score_contrib"] for i in indicators)
    max_possible  = sum(i["weight"] for i in indicators)   # = 13
    # Scale to 0-10
    overall = round((total_contrib / max_possible) * 10)
    overall = max(0, min(10, overall))

    return {
        "indicators":    indicators,
        "overall_score": overall,
        "triggered":     sum(1 for i in indicators if i["status"] == "red"),
        "watching":      sum(1 for i in indicators if i["status"] == "amber"),
        "clear":         sum(1 for i in indicators if i["status"] == "green"),
    }


# ─── Static data: Catalysts ───────────────────────────────────────────────────

CATALYSTS = [
    {
        "urgency": "high",
        "title":   "May 2026 — New Fed chair takes office",
        "desc":    (
            "The single most important near-term event. If the nominee is dovish (Hassett or similar), "
            "expect the terminal rate pushed toward 2.5–3.0% regardless of inflation levels. "
            "This is the operational trigger that turns structural repression into active repression. "
            "Watch confirmation hearings closely for language on the 'neutral rate' and 'r-star'."
        ),
    },
    {
        "urgency": "high",
        "title":   "2026 — Fiscal expansion accelerates debt trajectory",
        "desc":    (
            "Tax cuts and spending expansion projected to push the deficit back above 6–7% of GDP. "
            "This accelerates the debt trajectory and makes maintaining positive real rates mathematically untenable. "
            "IMF projects debt exceeds 140% of GDP by 2031 — well above the 1946 WWII peak of 106%."
        ),
    },
    {
        "urgency": "medium",
        "title":   "2026–2027 — Tariff inflation meets rate cuts",
        "desc":    (
            "Tariffs are inflationary (goods prices rising), but the new Fed chair may cut rates anyway "
            "to support the economy and reduce debt service costs. If this happens, real rates go negative — "
            "the textbook definition of active financial repression. Watch: CPI vs. Fed funds rate spread monthly."
        ),
    },
    {
        "urgency": "medium",
        "title":   "2027–2028 — SLR reform and bank behavior shift",
        "desc":    (
            "If SLR exemptions are granted, banks will absorb Treasuries at suppressed yields — "
            "the post-WWII Regulation Q equivalent, forcing the financial system to fund the "
            "government at below-market rates. Watch: bank Treasury holdings as a share of assets (FDIC quarterly data)."
        ),
    },
    {
        "urgency": "medium",
        "title":   "2028+ — Interest expense becomes the dominant fiscal constraint",
        "desc":    (
            "CBO projects interest exceeds Medicare spending by 2028. At that point, the government "
            "faces a binary choice: suppress yields through repression, or watch the debt spiral accelerate. "
            "The political will to maintain positive real rates collapses. Full systematic repression becomes the base case."
        ),
    },
]


# ─── Static data: Watchlist ───────────────────────────────────────────────────

WATCHLIST = [
    {
        "title":       "10-yr TIPS real yield",
        "freq":        "Daily · FRED: DFII10",
        "desc":        "The single most important signal. Below 1.0% = repression approaching. Below 0% = arrived. Chart the trend, not just the level.",
        "status":      "~2.0% — safe",
        "status_class": "safe",
    },
    {
        "title":       "Fed funds vs. CPI spread",
        "freq":        "Monthly (CPI) · FRED: FEDFUNDS, CPIAUCSL",
        "desc":        "Real policy rate = Fed funds minus CPI. When this turns negative after the new chair takes over, active repression has begun.",
        "status":      "~+0.8% — watching",
        "status_class": "warn",
    },
    {
        "title":       "New Fed chair nomination / hearings",
        "freq":        "Event-driven · Expected May 2026",
        "desc":        "Watch hearings for language on 'neutral rate,' 'r-star,' and willingness to cut into inflation. Dovish language = repression signal.",
        "status":      "⚠ Most important event",
        "status_class": "alert",
    },
    {
        "title":       "10-yr breakeven inflation",
        "freq":        "Daily · FRED: T10YIE",
        "desc":        "If breakevens spike above 3.0%+ while the Fed is cutting, markets are pricing in repression. The canary — moves before TIPS yields do.",
        "status":      "~2.25% — calm",
        "status_class": "safe",
    },
    {
        "title":       "10-yr Treasury term premium",
        "freq":        "Daily · NY Fed ACM model",
        "desc":        "Negative term premium = markets believe Fed will suppress long rates. Rising = repression risk being priced in by bond bears.",
        "status":      "Monitor NY Fed daily",
        "status_class": "warn",
    },
    {
        "title":       "SLR reform progress",
        "freq":        "Weekly · Fed regulatory releases",
        "desc":        "Any announcement exempting Treasuries from the Supplementary Leverage Ratio is the regulatory machinery of repression being activated.",
        "status":      "Monitor Fed releases",
        "status_class": "warn",
    },
]
