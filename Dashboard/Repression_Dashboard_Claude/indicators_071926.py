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


def score_real_policy_rate(rate: float | None, fed_funds: float | None, cpi: float | None,
                           cpi_sa: float | None = None) -> dict:
    if rate is None:
        return _unknown("Real interest rate (Fed funds − CPI)")
    status = "red" if rate <= 0 else "amber" if rate <= 1.5 else "green"
    # bar = how close to zero (repression threshold)
    bar = _clamp(((2.0 - rate) / 4.0) * 100) if rate <= 2.0 else 10
    ffr_str = f"{fed_funds:.2f}%" if fed_funds else "N/A"
    cpi_str = f"{cpi:.1f}%" if cpi else "N/A"
    sa_str  = f"{cpi_sa:.1f}%" if cpi_sa else "N/A"
    return {
        "name":      "Real interest rate (Fed funds − CPI)",
        "sub":       f"Fed funds: {ffr_str} · CPI YoY (NSA): {cpi_str}  ·  SA (display only): {sa_str} · Repression = negative real rate",
        "reading":   f"~{rate:+.2f}% {'⚠' if status == 'red' else ''}",
        "status":    status,
        "bar_pct":   bar,
        "bar_left":  f"Current: {rate:+.2f}%",
        "bar_right": "Trigger: 0%",
        "note": (
            f"Real policy rate = {ffr_str} (Fed funds) minus {cpi_str} (CPI YoY, NSA — matches the "
            f"officially-quoted headline figure) = {rate:+.2f}%. Seasonally-adjusted CPI YoY is "
            f"{sa_str} for comparison; NOT used in this calculation, since CPIAUCSL's seasonal "
            f"factors are re-revised annually and can drift from the quoted headline. "
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


def score_dollar_divergence(dxy_20d_change_pct: float | None,
                            tips_real_yield: float | None,
                            treasury_10y: float | None,
                            treasury_10y_series=None) -> dict:
    """
    Flags the specific pattern that matters for repression: real yields (or
    nominal yields) RISING while the dollar FALLS. Normally higher US real
    yields pull in foreign capital and support DXY — when that link breaks,
    it means the term premium is being priced as a currency/debt-confidence
    risk rather than a growth/inflation signal. This is a leading indicator,
    not a lagging one, so it will sit quiet most of the time by design.
    """
    if dxy_20d_change_pct is None or tips_real_yield is None:
        return _unknown("Dollar / real-yield divergence")

    # 20-trading-day change in the 10-yr nominal yield, for context alongside
    # the DXY momentum figure (both roughly 1-month windows).
    yield_20d_chg = None
    if treasury_10y_series is not None and len(treasury_10y_series) >= 21:
        s = treasury_10y_series.dropna()
        if len(s) >= 21:
            yield_20d_chg = round(s.iloc[-1] - s.iloc[-21], 2)

    diverging = (yield_20d_chg is not None and yield_20d_chg > 0.10
                 and dxy_20d_change_pct < -1.0)

    status = "red" if diverging else "amber" if (dxy_20d_change_pct < -1.5) else "green"
    bar    = _clamp(50 - dxy_20d_change_pct * 10)

    yield_str = f"{yield_20d_chg:+.2f}pp" if yield_20d_chg is not None else "N/A"

    return {
        "name":      "Dollar / real-yield divergence",
        "sub":       f"DXY 20d: {dxy_20d_change_pct:+.1f}% · 10-yr yield 20d: {yield_str} "
                     "· Alert: yields rising while DXY falls",
        "reading":   f"DXY {dxy_20d_change_pct:+.1f}% (20d) {'⚠' if diverging else ''}",
        "status":    status,
        "bar_pct":   bar,
        "bar_left":  f"DXY 20d: {dxy_20d_change_pct:+.1f}%",
        "bar_right": "Watching for divergence",
        "note": (
            f"Dollar index (DXY) is {'up' if dxy_20d_change_pct >= 0 else 'down'} "
            f"{abs(dxy_20d_change_pct):.1f}% over the last 20 trading days; the 10-yr Treasury "
            f"yield has moved {yield_str} over the same window. "
            + (
                "DIVERGENCE FLAGGED: yields are rising while the dollar falls — the classic "
                "sign that bond buyers are pricing debt-sustainability risk into the term "
                "premium rather than growth or Fed-policy expectations, and that foreign "
                "capital is not following the higher yield the way it normally would. "
                "This is the pattern to watch for confirmation of a debt-driven, rather than "
                "policy-driven, dollar weakening."
                if diverging else
                "No divergence currently — yields and the dollar are moving in their normal "
                "relationship (both driven by the same Fed-policy/inflation expectations)."
            )
        ),
        "weight": 1,
        "score_contrib": 2 if diverging else 1 if dxy_20d_change_pct < -1.5 else 0,
    }


def score_gold_momentum_gate(gld_series=None,
                             tips_real_yield: float | None = None,
                             breakeven_series=None) -> dict:
    """
    Gold momentum gate: gold is treated as a repression-confirming signal
    only when BOTH conditions hold —
      1) the fundamental gate is open: real yields low/falling (< 1.5%) AND
         breakeven inflation expectations rising (10d slope > 0), matching
         the existing wealth-tab thesis text ("TIPS real yield < 1.5% AND
         breakeven inflation rising — gold accelerates"), and
      2) price is actually confirming: GLD's 50-day average is above its
         200-day average (trend-following momentum gate).
    Both gates open = repression thesis is being actively priced by the
    gold market, not just a macro precondition sitting there unconfirmed.
    """
    if gld_series is None or len(gld_series) < 200 or tips_real_yield is None:
        return _unknown("Gold momentum gate")

    gld = gld_series.dropna()
    ma50  = float(gld.tail(50).mean())
    ma200 = float(gld.tail(200).mean())
    price_confirmed = ma50 > ma200

    be_rising = None
    if breakeven_series is not None and len(breakeven_series.dropna()) >= 11:
        be = breakeven_series.dropna()
        be_rising = be.iloc[-1] > be.iloc[-11]

    fundamental_open = (tips_real_yield < 1.5) and bool(be_rising)
    both_open = fundamental_open and price_confirmed

    if both_open:
        status, label = "red", "GATE OPEN — confirmed"
    elif fundamental_open or price_confirmed:
        status, label = "amber", "partial — one gate open"
    else:
        status, label = "green", "gate closed"

    bar = 90 if both_open else 50 if (fundamental_open or price_confirmed) else 10

    be_str = ("rising" if be_rising else "flat/falling") if be_rising is not None else "N/A"

    return {
        "name":      "Gold momentum gate (fundamental + price confirmation)",
        "sub":       f"Real yield: {tips_real_yield:.2f}% · Breakevens: {be_str} · "
                     f"GLD 50d {'>' if price_confirmed else '<'} 200d MA",
        "reading":   label,
        "status":    status,
        "bar_pct":   bar,
        "bar_left":  "Fundamental gate",
        "bar_right": "Price gate",
        "note": (
            f"Fundamental gate ({'OPEN' if fundamental_open else 'closed'}): TIPS real yield "
            f"{tips_real_yield:.2f}% (needs < 1.5%) with breakevens {be_str} (needs rising). "
            f"Price gate ({'OPEN' if price_confirmed else 'closed'}): GLD 50-day MA "
            f"${ma50:.2f} vs. 200-day MA ${ma200:.2f}. "
            + (
                "BOTH GATES OPEN — the repression thesis is fundamentally supported AND the "
                "gold market is actively confirming it with price trend. This is the strongest "
                "form of the gold signal used elsewhere on this dashboard."
                if both_open else
                "Only one gate is open — either the macro precondition exists without price "
                "confirmation yet, or price is trending up without the real-yield/breakeven "
                "setup behind it (momentum without a repression driver)."
                if (fundamental_open or price_confirmed) else
                "Neither gate is open — no repression-driven gold signal at this time."
            )
        ),
        "weight": 1,
        "score_contrib": 2 if both_open else 1 if (fundamental_open or price_confirmed) else 0,
    }


def score_auction_demand(btc_latest: float | None, btc_avg4: float | None,
                         security_label: str = "10-yr note") -> dict:
    """
    Treasury auction bid-to-cover ratio — a leading indicator of debt-
    sustainability stress rather than a lagging confirmation. A bid-to-cover
    consistently below ~2.2 on the 10-yr signals weakening demand; below 2.0
    is a genuinely weak auction by modern standards.
    """
    if btc_latest is None:
        return _unknown(f"Treasury auction demand ({security_label})")

    status = "red" if btc_latest < 2.0 else "amber" if btc_latest < 2.3 else "green"
    bar    = _clamp(((2.6 - btc_latest) / 1.0) * 100)
    trend_str = f"{btc_avg4:.2f}" if btc_avg4 is not None else "N/A"

    return {
        "name":      f"Treasury auction demand ({security_label} bid-to-cover)",
        "sub":       f"Latest: {btc_latest:.2f} · Trailing 4-auction avg: {trend_str} "
                     "· Weak demand: < 2.2, stressed: < 2.0",
        "reading":   f"{btc_latest:.2f} {'⚠' if status == 'red' else ''}",
        "status":    status,
        "bar_pct":   bar,
        "bar_left":  f"Current: {btc_latest:.2f}",
        "bar_right": "Healthy: 2.3+",
        "note": (
            f"Most recent {security_label} auction bid-to-cover ratio: {btc_latest:.2f} "
            f"(trailing 4-auction average: {trend_str}). "
            f"{'STRESSED: this is a genuinely weak auction — investors are demanding higher yields to absorb supply, a leading sign of debt-sustainability concern.' if btc_latest < 2.0 else ''}"
            f"{'Softening demand — worth watching the next 2-3 auctions for confirmation.' if 2.0 <= btc_latest < 2.3 else ''}"
            f"{'Healthy demand — no auction-driven stress signal currently.' if btc_latest >= 2.3 else ''}"
            " Source: U.S. Treasury Fiscal Data API (auctions_query)."
        ),
        "weight": 1,
        "score_contrib": 2 if btc_latest < 2.0 else 1 if btc_latest < 2.3 else 0,
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
            raw.get("cpi_yoy_sa"),
        ),
        score_tips_real_yield(raw.get("tips_real_yield")),
        score_fed_independence(),
        score_structural_tools(),
        score_market_pricing(raw.get("breakeven"), raw.get("hy_spread")),
        score_dollar_divergence(
            raw.get("dxy_20d_change_pct"),
            raw.get("tips_real_yield"),
            raw.get("treasury_10y"),
            raw.get("treasury_10y_series"),
        ),
        score_gold_momentum_gate(
            raw.get("wealth_GLD_series"),
            raw.get("tips_real_yield"),
            raw.get("breakeven_series"),
        ),
        score_auction_demand(
            raw.get("auction_10y_btc_latest"),
            raw.get("auction_10y_btc_avg4"),
        ),
    ]

    total_contrib = sum(i["score_contrib"] for i in indicators)
    max_possible  = sum(i["weight"] for i in indicators)   # computed dynamically; was 13 before the dollar/gold/auction additions
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


# ─── Static data: Watchlist (fallback / reference only) ───────────────────────
# NOTE: app.py should call build_watchlist(raw) below for LIVE status.
# This static list is kept only as a fallback if raw data is unavailable.

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
        "freq":        "Monthly (CPI) · FRED: FEDFUNDS, CPIAUCNS",
        "desc":        "Real policy rate = Fed funds minus CPI (NSA — matches the officially-quoted headline figure). When this turns negative after the new chair takes over, active repression has begun.",
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
    {
        "title":       "Dollar (DXY) vs. real-yield divergence",
        "freq":        "Daily · Yahoo Finance DX-Y.NYB, FRED DGS10",
        "desc":        "Watch for yields rising while DXY falls — bond buyers pricing debt-confidence risk rather than growth/Fed-policy expectations into the term premium.",
        "status":      "Monitor daily",
        "status_class": "warn",
    },
    {
        "title":       "Gold momentum gate",
        "freq":        "Daily · Yahoo Finance GLD, FRED DFII10/T10YIE",
        "desc":        "Both the fundamental gate (real yield < 1.5% AND breakevens rising) and the price gate (GLD 50d MA > 200d MA) need to be open for gold to be a confirmed repression signal, not just a macro precondition.",
        "status":      "Monitor daily",
        "status_class": "warn",
    },
    {
        "title":       "Treasury auction bid-to-cover",
        "freq":        "Per auction (~monthly for 10-yr) · Treasury Fiscal Data API",
        "desc":        "A leading indicator of debt-sustainability stress. Below 2.2 = weak demand; below 2.0 = genuinely stressed auction.",
        "status":      "Monitor per auction",
        "status_class": "warn",
    },
]


def build_watchlist(raw: dict) -> list[dict]:
    """
    LIVE watchlist: same schema/order as the static WATCHLIST above, but the
    three data-backed rows (TIPS real yield, Fed funds/CPI spread, breakeven)
    pull their status from `raw` using the SAME thresholds as the scorecard
    functions, so the watchlist and scorecard can never silently disagree.

    Event-driven rows with no numeric source in `raw` (Fed chair nomination,
    term premium, SLR reform) are passed through unchanged from the static
    list — there is nothing to compute for them.

    If a value is missing from `raw` (fetch failed), falls back to the
    static entry's text so the card never shows a blank/broken status.
    """
    out = [dict(w) for w in WATCHLIST]  # shallow copy, preserve order/schema

    # ── Row 0: 10-yr TIPS real yield — thresholds match score_tips_real_yield
    tips = raw.get("tips_real_yield")
    if tips is not None:
        if tips <= 0:
            cls, label = "alert", "REPRESSION ACTIVE"
        elif tips <= 1.0:
            cls, label = "warn", "approaching"
        else:
            cls, label = "safe", "safe"
        out[0]["status"] = f"{tips:.2f}% — {label}"
        out[0]["status_class"] = cls

    # ── Row 1: Fed funds vs. CPI spread — thresholds match score_real_policy_rate
    rpr = raw.get("real_policy_rate")
    if rpr is not None:
        if rpr <= 0:
            cls, label = "alert", "REPRESSION ACTIVE"
        elif rpr <= 1.5:
            cls, label = "warn", "watching"
        else:
            cls, label = "safe", "safe"
        out[1]["status"] = f"{rpr:+.2f}% — {label}"
        out[1]["status_class"] = cls

    # Row 2 (Fed chair nomination): no numeric source — left static.

    # ── Row 3: 10-yr breakeven inflation — thresholds match score_market_pricing
    be = raw.get("breakeven")
    if be is not None:
        if be > 3.0:
            cls, label = "warn", "elevated"
        else:
            cls, label = "safe", "calm"
        out[3]["status"] = f"{be:.2f}% — {label}"
        out[3]["status_class"] = cls

    # Rows 4-5 (term premium, SLR reform): no numeric source in raw — static.

    # ── Row 6: DXY vs real-yield divergence — thresholds match score_dollar_divergence
    dxy_chg = raw.get("dxy_20d_change_pct")
    if dxy_chg is not None:
        t10_series = raw.get("treasury_10y_series")
        yield_20d_chg = None
        if t10_series is not None and len(t10_series.dropna()) >= 21:
            s = t10_series.dropna()
            yield_20d_chg = s.iloc[-1] - s.iloc[-21]
        diverging = (yield_20d_chg is not None and yield_20d_chg > 0.10 and dxy_chg < -1.0)
        if diverging:
            cls, label = "alert", "DIVERGENCE FLAGGED"
        elif dxy_chg < -1.5:
            cls, label = "warn", "watching"
        else:
            cls, label = "safe", "normal"
        out[6]["status"] = f"DXY {dxy_chg:+.1f}% (20d) — {label}"
        out[6]["status_class"] = cls

    # ── Row 7: Gold momentum gate — thresholds match score_gold_momentum_gate
    tips = raw.get("tips_real_yield")
    gld  = raw.get("wealth_GLD_series")
    if tips is not None and gld is not None and len(gld.dropna()) >= 200:
        g = gld.dropna()
        price_confirmed = float(g.tail(50).mean()) > float(g.tail(200).mean())
        be_series = raw.get("breakeven_series")
        be_rising = None
        if be_series is not None and len(be_series.dropna()) >= 11:
            be = be_series.dropna()
            be_rising = be.iloc[-1] > be.iloc[-11]
        fundamental_open = (tips < 1.5) and bool(be_rising)
        if fundamental_open and price_confirmed:
            cls, label = "alert", "GATE OPEN"
        elif fundamental_open or price_confirmed:
            cls, label = "warn", "partial"
        else:
            cls, label = "safe", "closed"
        out[7]["status"] = label
        out[7]["status_class"] = cls

    # ── Row 8: Treasury auction bid-to-cover — thresholds match score_auction_demand
    btc = raw.get("auction_10y_btc_latest")
    if btc is not None:
        if btc < 2.0:
            cls, label = "alert", "STRESSED"
        elif btc < 2.3:
            cls, label = "warn", "softening"
        else:
            cls, label = "safe", "healthy"
        out[8]["status"] = f"{btc:.2f} — {label}"
        out[8]["status_class"] = cls

    return out
