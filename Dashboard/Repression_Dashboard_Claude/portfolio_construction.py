"""
portfolio_construction.py  (v1 — August 2026)
─────────────────────────────────────────────
Regime → portfolio, with the crash-diversification constraint made explicit.

THE STATED OBJECTIVE
────────────────────
"Architect a portfolio that takes advantage of the regime, but also
diversified to minimise losses during market crashes or rapid regime
changes."

Those two goals genuinely conflict, and this module's job is to show the
tension rather than hide it. A portfolio maximally tilted to the current
regime is, by construction, maximally exposed to being wrong about it — and
regime changes are exactly when tilts hurt most, because the tilt was sized
on the OLD regime right up until the moment it stopped being true.

So every allocation here is split into two explicitly-labelled parts:

    REGIME TILT      the overlay from regime_classifier.target_weights()
    ALL-WEATHER CORE what stays regardless, sized so a wrong regime call
                     is survivable rather than fatal

THE CRASH-TYPE PROBLEM
──────────────────────
There is no single "crash hedge", and pretending otherwise is the most
expensive mistake available here. Two historical crashes, opposite winners:

    2000-02 dot-com   REITs +45%, long Treasuries +25%, gold +13%
    2008 GFC          REITs -68%, long Treasuries +25%, gold ~flat

REITs were the best diversifier in one and the worst asset in the other.
Only TWO things worked in both: long Treasuries and trend-following. And
2022 breaks even that — an inflation-driven drawdown where long Treasuries
fell WITH equities, leaving trend as the sole survivor across all three.

That is the entire justification for the KMLM sleeve, and for why duration
is regime-gated rather than permanent.
"""

from __future__ import annotations

from typing import Optional

# ── The three-layer construction ────────────────────────────────────────────
LAYER_CORE = "All-weather core"
LAYER_TILT = "Regime tilt"
LAYER_CONVEX = "Convexity"

# Sleeves that stay regardless of regime — the survivability floor.
# These are NOT a view; they are what makes a wrong regime call recoverable.
CORE_SLEEVES = {
    "SCHD": "Quality dividend — cash-flow durability, works in most regimes",
    "SGOV": "T-bills — zero duration, the optionality to buy a crash",
    "USFR": "Floating rate — coupon RISES if the Fed hikes",
    "KMLM": "Managed futures — the ONLY sleeve positive in 2000-02, 2008 AND 2022",
    "GLD":  "Gold — debasement and negative-real-rate hedge (momentum-gated)",
}

# What each regime is BETTING ON, and what would make that bet wrong.
REGIME_THESIS = {
    "inflationary_repression": {
        "bet": "Negative front-end real rates with a rising long end — savers "
               "are being liquidated while duration bleeds.",
        "wrong_if": "The short real rate turns decisively positive, or the "
                    "long end rallies hard (which would signal deflation, not "
                    "repression).",
        "crash_exposure": "Real assets carry the book. A DEFLATIONARY bust "
                          "hurts most here — commodities and metals fall with "
                          "equities and the duration hedge is underweight.",
    },
    "hard_repression": {
        "bet": "Negative front-end real rates with a SUPPRESSED long end — "
               "yield-curve-control signature. Duration works again.",
        "wrong_if": "Long real yields resume rising, or credit cracks.",
        "crash_exposure": "Best-hedged of the repression states, because "
                          "duration is re-armed alongside real assets.",
    },
    "stagflation": {
        "bet": "Negative real rates plus a re-steepening curve — growth risk "
               "with inflation still above target.",
        "wrong_if": "Inflation rolls over fast enough for the Fed to ease "
                    "before growth breaks.",
        "crash_exposure": "The hardest regime to hedge: stocks AND bonds can "
                          "fall together. Trend and cash carry the load.",
    },
    "goldilocks": {
        "bet": "Positive real rates, tight credit, intact leadership, "
               "non-extreme valuation — genuine benign conditions.",
        "wrong_if": "Any one of the three guards trips: valuation, "
                    "leadership, or growth.",
        "crash_exposure": "MOST exposed by design. This is the only "
                          "growth-additive regime, so a wrong call here costs "
                          "the most — which is precisely why it carries three "
                          "independent guards.",
    },
    "growth_scare": {
        "bet": "Labour and consumer data contracting together, independent of "
               "the real-rate sign.",
        "wrong_if": "The growth data reverses within a quarter — payroll "
                    "revisions in particular are large and frequent.",
        "crash_exposure": "Defensively positioned, but duration is "
                          "deliberately NOT added: if the contraction is "
                          "stagflationary rather than deflationary, adding "
                          "duration would compound the loss.",
    },
    "liquidity_crisis": {
        "bet": "Credit is breaking. Nothing else matters until it stops.",
        "wrong_if": "Spreads retrace quickly — a false positive costs "
                    "participation in the recovery.",
        "crash_exposure": "This IS the crash. Duration re-armed, growth cut, "
                          "cash maximal.",
    },
    "transition_ambiguous": {
        "bet": "Deliberately none. The primary gauge is silent or a guard has "
               "blocked confirmation.",
        "wrong_if": "N/A — this state exists precisely to avoid betting.",
        "crash_exposure": "Near base weights. The most robust posture to a "
                          "RAPID regime change, at the cost of participation "
                          "if the current trend continues.",
    },
    "neutral": {
        "bet": "Signals disagree; no dominant driver.",
        "wrong_if": "N/A",
        "crash_exposure": "Base weights.",
    },
}


def build(regime_key: str, weights: dict, base_weights: dict,
          growth: Optional[dict] = None,
          convexity_pct: Optional[float] = None) -> dict:
    """
    Decompose the target weights into core / tilt / convexity and attach the
    thesis and its invalidation.
    """
    tilt = {t: round(weights.get(t, 0) - base_weights.get(t, 0), 1)
            for t in base_weights}
    active_tilt = {t: v for t, v in tilt.items() if abs(v) >= 0.5}

    core_total = sum(weights.get(t, 0) for t in CORE_SLEEVES)
    tilt_gross = sum(abs(v) for v in active_tilt.values())

    thesis = REGIME_THESIS.get(regime_key, REGIME_THESIS["neutral"])

    return {
        "regime": regime_key,
        "weights": weights,
        "tilt": active_tilt,
        "core_total_pct": round(core_total, 1),
        "tilt_gross_pct": round(tilt_gross, 1),
        "thesis": thesis,
        "convexity_pct": convexity_pct,
        "growth_state": (growth or {}).get("state"),
    }


def render(st, plan: dict, base_weights: dict):
    """Render the construction view."""
    st.markdown("### Portfolio construction for this regime")

    t = plan["thesis"]
    st.markdown(f"**The bet:** {t['bet']}")
    st.markdown(f"**Wrong if:** {t['wrong_if']}")
    st.warning(f"**Crash exposure:** {t['crash_exposure']}")

    c1, c2, c3 = st.columns(3)
    c1.metric("All-weather core", f"{plan['core_total_pct']:.0f}%",
              help="Sleeves held regardless of regime. This is the "
                   "survivability floor — what makes a wrong regime call "
                   "recoverable rather than fatal.")
    c2.metric("Regime tilt (gross)", f"{plan['tilt_gross_pct']:.0f}%",
              help="Total absolute deviation from base weights. Higher = a "
                   "bigger bet on this regime being right.")
    c3.metric("Convexity",
              f"{plan['convexity_pct']:.2f}%" if plan.get("convexity_pct")
              is not None else "not sized",
              help="Far-OTM index puts, priced off where VIX sits in its own "
                   "1-year range. The only sleeve that GAINS in a crash "
                   "rather than merely falling less.")

    st.markdown("#### Active tilts vs base")
    if not plan["tilt"]:
        st.caption("No active tilts — holding base weights.")
    else:
        for tk, v in sorted(plan["tilt"].items(), key=lambda kv: -abs(kv[1])):
            arrow = "▲" if v > 0 else "▼"
            colour = "#16a34a" if v > 0 else "#dc2626"
            base = base_weights.get(tk, 0)
            st.markdown(
                f"<span style='color:{colour};'>{arrow}</span> "
                f"<b>{tk}</b> {base:.0f}% → {plan['weights'].get(tk, 0):.0f}% "
                f"<span style='color:{colour};'>({v:+.0f})</span>",
                unsafe_allow_html=True)

    with st.expander("Why these sleeves are the core — the crash-type problem"):
        st.markdown(
            "There is no single crash hedge, and assuming otherwise is the "
            "most expensive mistake available here:\n\n"
            "| Crash | REITs | Long Treasuries | Gold | Trend |\n"
            "|---|---|---|---|---|\n"
            "| 2000–02 dot-com | **+45%** | +25% | +13% | positive |\n"
            "| 2008 GFC | **−68%** | +25% | ~flat | **+14%** |\n"
            "| 2022 inflation | negative | **negative** | ~flat | positive |\n\n"
            "REITs were the best diversifier in one crash and the worst asset "
            "in another. Long Treasuries worked in two of three and failed "
            "badly in the inflationary one. **Only trend-following was "
            "positive in all three** — which is why KMLM is core rather than "
            "a tilt, and why duration is regime-gated rather than permanent.")
        for tk, why in CORE_SLEEVES.items():
            st.markdown(f"- **{tk}** — {why}")


def selftest() -> dict:
    base = {"VGT": 20, "SCHD": 13, "SGOV": 5, "USFR": 3, "KMLM": 4, "GLD": 12,
            "TLT": 10, "XLV": 4}
    wts = {"VGT": 16, "SCHD": 16, "SGOV": 7, "USFR": 4, "KMLM": 5, "GLD": 12,
           "TLT": 10, "XLV": 7}
    p = build("growth_scare", wts, base, convexity_pct=1.25)
    failures = []
    if p["core_total_pct"] != 44.0:
        failures.append(f"core total {p['core_total_pct']}, expected 44.0")
    if "TLT" in p["tilt"]:
        failures.append("TLT has no tilt but appeared in active tilts")
    if p["tilt"].get("VGT") != -4.0:
        failures.append(f"VGT tilt {p['tilt'].get('VGT')}, expected -4.0")
    return {"ok": not failures, "failures": failures,
            "core_pct": p["core_total_pct"], "tilt_gross": p["tilt_gross_pct"]}


if __name__ == "__main__":
    import json
    print(json.dumps(selftest(), indent=2, default=str))
