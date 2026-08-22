"""
position_sizing.py  (v1 — August 2026)
──────────────────────────────────────
Conviction scaling and — deliberately bounded within it — leverage.

WHY THESE TWO LIVE IN ONE MODULE
────────────────────────────────
Both answer "how much". Separating them would let leverage float free of
the conviction framework that is supposed to constrain it, which is exactly
how leverage goes wrong: applied uniformly rather than only where the
evidence is strongest, and with no mechanism to reduce it when the evidence
degrades. Here, leverage cannot exceed what conviction justifies.

PART 1 — CONVICTION SCALING
───────────────────────────
Currently every sleeve is capped at base weight × regime overlay. There is
no mechanism to concentrate when evidence is strong. Diversification is a
VARIANCE-reduction tool: it mathematically caps returns toward the average
of holdings. A framework that can never concentrate can never materially
outperform its own average sleeve.

Conviction is scored from evidence the system ALREADY produces:
    regime confirmation   is the regime confirmed or guard-blocked?
    RS quartile           relative_strength.py
    trend state           trend_filter.py
    valuation             cheap/expensive vs own history, where available

3-of-3 confluence earns a genuine overweight. 1-of-3 earns nothing.

PART 2 — LEVERAGE (DEFAULT OFF)
───────────────────────────────
⚠ Leverage is the fastest way to convert a good framework into a blown-up
account, and every safeguard below exists because of a specific documented
failure mode:

  HARD CAP 1.30x        Risk-parity funds lever LOW-VOLATILITY diversified
                        books. This is categorically different from 3x
                        single-sector ETFs, whose daily reset produces
                        volatility decay that compounds against the holder.
                        1.3x on a diversified book is a different animal;
                        the cap makes sure it stays that way.

  CORRELATION GATE      2022 is the case study: risk parity broke because
                        stocks and bonds fell TOGETHER, so the leverage that
                        was justified by low correlation amplified a loss
                        that diversification was supposed to damp. If
                        average pairwise correlation is elevated, leverage
                        is refused outright regardless of everything else.

  REGIME GATE           No leverage in liquidity_crisis, growth_scare, or
                        any transition/guard-blocked state. Leverage is only
                        available when the regime is CONFIRMED benign.

  VOL GATE              No leverage when realised vol exceeds target — the
                        book is already carrying more risk than intended.

  DRAWDOWN MATH SHOWN   Every output states what leverage does to LOSSES,
                        not just gains, because that asymmetry is what
                        people underestimate.

Default is OFF. It must be explicitly enabled, and any single gate failing
returns 1.00x.
"""

from __future__ import annotations

from typing import Optional

# ── Conviction ──────────────────────────────────────────────────────────────
CONVICTION_MULT = {3: 1.40, 2: 1.15, 1: 1.00, 0: 0.85}

# No single sleeve may exceed this after conviction scaling. Concentration
# is the point; unbounded concentration is not.
MAX_SLEEVE_PCT = 28.0

# ── Leverage safeguards ─────────────────────────────────────────────────────
LEVERAGE_ENABLED_DEFAULT = False
LEVERAGE_HARD_CAP = 1.30
LEVERAGE_CORRELATION_MAX = 0.55      # avg pairwise; above this -> refused
LEVERAGE_VOL_TARGET = 12.0           # annualised %; above this -> refused

LEVERAGE_ALLOWED_REGIMES = {"goldilocks", "hard_repression"}
LEVERAGE_BLOCKED_REGIMES = {
    "liquidity_crisis", "growth_scare", "transition_ambiguous",
    "stagflation", "neutral", "inflationary_repression",
}


def score_conviction(regime_confirmed: bool, rs_quartile: Optional[int],
                     trend_state: Optional[str],
                     valuation_cheap: Optional[bool] = None) -> dict:
    """
    3-of-3 confluence scoring. Returns score, multiplier and the reasoning.

    Missing evidence does NOT count as passing — an unknown is not a yes.
    """
    legs, passed = [], 0

    if rs_quartile is None:
        legs.append("○ RS: unavailable (not counted as a pass)")
    elif rs_quartile <= 2:
        passed += 1
        legs.append(f"✓ RS: quartile {rs_quartile} (top half)")
    else:
        legs.append(f"✗ RS: quartile {rs_quartile} (bottom half)")

    if trend_state is None:
        legs.append("○ Trend: unavailable (not counted as a pass)")
    elif trend_state == "CONFIRMED UPTREND":
        passed += 1
        legs.append("✓ Trend: confirmed uptrend")
    elif trend_state == "EXEMPT":
        legs.append("○ Trend: exempt (cash-like)")
    else:
        legs.append(f"✗ Trend: {trend_state}")

    if valuation_cheap is None:
        legs.append("○ Valuation: unavailable (not counted as a pass)")
    elif valuation_cheap:
        passed += 1
        legs.append("✓ Valuation: cheap vs own history")
    else:
        legs.append("✗ Valuation: not cheap vs own history")

    # A guard-blocked or unconfirmed regime caps conviction regardless of the
    # other legs — the macro backdrop is a precondition, not one vote of three.
    if not regime_confirmed and passed == 3:
        passed = 2
        legs.append("⚠ Capped at 2/3: regime is not confirmed (guard active "
                    "or transition state). A Level-4 setup in an unconfirmed "
                    "Level-1 regime does not earn full size.")

    return {"score": passed, "multiplier": CONVICTION_MULT[passed],
            "legs": legs}


def apply_conviction(weights: dict, convictions: dict,
                     max_sleeve: float = MAX_SLEEVE_PCT) -> dict:
    """Apply conviction multipliers, cap any single sleeve, renormalise."""
    scaled = {tk: w * convictions.get(tk, {}).get("multiplier", 1.0)
              for tk, w in weights.items()}

    total = sum(scaled.values())
    if total <= 0:
        return dict(weights)
    scaled = {tk: w / total * 100 for tk, w in scaled.items()}

    # Cap, redistributing excess proportionally — ITERATIVELY. A single pass
    # is wrong: redistributing one sleeve's excess can push a previously
    # compliant sleeve ABOVE the cap, so the cap must be re-applied until it
    # converges. Caught by selftest, which found A capped at 28% while the
    # redistribution pushed B to 33% and C to 39%.
    for _ in range(20):
        excess = 0.0
        for tk, w in list(scaled.items()):
            if w > max_sleeve + 1e-9:
                excess += w - max_sleeve
                scaled[tk] = max_sleeve
        if excess <= 1e-9:
            break
        uncapped = {tk: w for tk, w in scaled.items()
                    if w < max_sleeve - 1e-9}
        pool = sum(uncapped.values())
        if pool <= 0:
            # Every sleeve is at the cap — the universe is too small for this
            # cap to be satisfiable. Distribute evenly and stop rather than
            # loop forever.
            n = len(scaled)
            scaled = {tk: 100.0 / n for tk in scaled}
            break
        for tk in uncapped:
            scaled[tk] += excess * (scaled[tk] / pool)

    return {tk: round(w, 2) for tk, w in scaled.items()}


def leverage_decision(enabled: bool = LEVERAGE_ENABLED_DEFAULT,
                      regime_key: str = "",
                      avg_correlation: Optional[float] = None,
                      realised_vol: Optional[float] = None,
                      conviction_avg: Optional[float] = None) -> dict:
    """
    Decide gross exposure. Returns 1.00x unless EVERY gate passes.

    Each refusal names the specific gate and why it exists.
    """
    out = {"leverage": 1.00, "enabled": enabled, "gates": [],
           "refused_by": None, "detail": ""}

    def refuse(gate, why):
        out["refused_by"] = gate
        out["detail"] = why
        out["gates"].append(f"✗ {gate}: {why}")
        return out

    if not enabled:
        return refuse("Master switch",
                      "Leverage is OFF by default and must be explicitly "
                      "enabled. This is deliberate: the same construction "
                      "that returns 25% levered in a good window returns "
                      "-60% in the wrong one.")

    if regime_key in LEVERAGE_BLOCKED_REGIMES:
        return refuse("Regime gate",
                      f"'{regime_key}' is a blocked regime. Leverage is "
                      f"available only in a CONFIRMED benign regime "
                      f"({', '.join(sorted(LEVERAGE_ALLOWED_REGIMES))}) — "
                      f"never in a crisis, growth scare, or any "
                      f"guard-blocked transition state.")
    out["gates"].append(f"✓ Regime gate: '{regime_key}' permitted")

    if avg_correlation is None:
        return refuse("Correlation gate",
                      "Average pairwise correlation unavailable. Leverage "
                      "REQUIRES proof that diversification is intact — "
                      "unknown is not permission.")
    if avg_correlation > LEVERAGE_CORRELATION_MAX:
        return refuse("Correlation gate",
                      f"Average pairwise correlation {avg_correlation:.2f} "
                      f"exceeds {LEVERAGE_CORRELATION_MAX:.2f}. This is the "
                      f"2022 failure mode: risk parity broke because stocks "
                      f"and bonds fell TOGETHER, so leverage justified by "
                      f"low correlation amplified a loss diversification was "
                      f"meant to damp.")
    out["gates"].append(f"✓ Correlation gate: {avg_correlation:.2f} ≤ "
                        f"{LEVERAGE_CORRELATION_MAX:.2f}")

    if realised_vol is None:
        return refuse("Vol gate", "Realised volatility unavailable — cannot "
                                  "confirm the book is inside its risk budget.")
    if realised_vol > LEVERAGE_VOL_TARGET:
        return refuse("Vol gate",
                      f"Realised vol {realised_vol:.1f}% exceeds the "
                      f"{LEVERAGE_VOL_TARGET:.1f}% target. The book already "
                      f"carries more risk than intended; levering it would "
                      f"compound that.")
    out["gates"].append(f"✓ Vol gate: {realised_vol:.1f}% ≤ "
                        f"{LEVERAGE_VOL_TARGET:.1f}%")

    # Scale leverage by BOTH remaining vol headroom and average conviction.
    vol_headroom = max(0.0, (LEVERAGE_VOL_TARGET - realised_vol)
                       / LEVERAGE_VOL_TARGET)
    conv = (conviction_avg or 1.0)
    raw = 1.0 + vol_headroom * 0.5 * min(conv / 1.2, 1.0)
    lev = min(raw, LEVERAGE_HARD_CAP)

    out["leverage"] = round(lev, 3)
    out["gates"].append(f"✓ All gates passed → {lev:.2f}x "
                        f"(capped at {LEVERAGE_HARD_CAP:.2f}x)")
    out["detail"] = (f"{lev:.2f}x gross exposure. At this leverage a -20% "
                     f"underlying move becomes {-20*lev:.1f}%, and recovering "
                     f"from that requires {(1/(1+(-20*lev/100))-1)*100:.1f}%. "
                     f"That asymmetry, not the upside, is what leverage "
                     f"actually changes.")
    return out


def drawdown_table(leverage: float) -> list[dict]:
    """What leverage does to losses — the part people underestimate."""
    rows = []
    for move in (-10, -20, -30, -40, -50):
        levered = move * leverage
        recovery = (1 / (1 + levered / 100) - 1) * 100
        rows.append({"underlying": move, "levered": round(levered, 1),
                     "recovery_needed": round(recovery, 1)})
    return rows


def render(st, convictions: dict, lev: dict, weights: dict = None):
    st.markdown("### Position Sizing")

    st.markdown("#### Conviction scaling")
    st.caption(
        "3-of-3 confluence earns a genuine overweight; 1-of-3 earns nothing. "
        "Diversification caps returns toward the average sleeve — a framework "
        "that can never concentrate can never materially outperform its own "
        "average."
    )
    for tk, c in sorted(convictions.items(), key=lambda kv: -kv[1]["score"]):
        st.markdown(f"**{tk}** — {c['score']}/3 → ×{c['multiplier']:.2f}")
        for leg in c["legs"]:
            st.caption(leg)

    st.markdown("#### Leverage")
    if lev["leverage"] <= 1.0:
        st.success(f"**Gross exposure 1.00x — no leverage.** "
                   f"Refused by: {lev.get('refused_by', 'n/a')}.")
        st.caption(lev.get("detail", ""))
    else:
        st.warning(f"**Gross exposure {lev['leverage']:.2f}x**")
        st.caption(lev.get("detail", ""))
    for g in lev.get("gates", []):
        st.caption(g)

    with st.expander("⚠ What leverage does to LOSSES"):
        import pandas as pd
        df = pd.DataFrame(drawdown_table(max(lev["leverage"], 1.30)))
        df.columns = ["Underlying move %", "Levered move %", "Recovery needed %"]
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.markdown(
            "At the 1.30x hard cap, a -40% underlying drawdown becomes -52%, "
            "requiring **+108%** to recover. Leverage does not scale gains and "
            "losses symmetrically — the recovery requirement grows faster than "
            "the loss. This is why the cap is 1.30x rather than 2x or 3x, and "
            "why every gate must pass rather than most of them.")


def selftest() -> dict:
    failures = []

    c3 = score_conviction(True, 1, "CONFIRMED UPTREND", True)
    if c3["score"] != 3 or c3["multiplier"] != 1.40:
        failures.append(f"3/3 scored {c3['score']}")

    c_unconf = score_conviction(False, 1, "CONFIRMED UPTREND", True)
    if c_unconf["score"] != 2:
        failures.append("unconfirmed regime did not cap conviction at 2")

    c_missing = score_conviction(True, None, None, None)
    if c_missing["score"] != 0:
        failures.append("missing evidence counted as passing")

    # Leverage must refuse by default
    if leverage_decision()["leverage"] != 1.00:
        failures.append("leverage not refused by default")

    # Blocked regime
    l = leverage_decision(enabled=True, regime_key="growth_scare",
                          avg_correlation=0.2, realised_vol=8)
    if l["leverage"] != 1.00 or l["refused_by"] != "Regime gate":
        failures.append("growth_scare did not block leverage")

    # 2022 correlation failure mode
    l = leverage_decision(enabled=True, regime_key="goldilocks",
                          avg_correlation=0.75, realised_vol=8)
    if l["leverage"] != 1.00 or l["refused_by"] != "Correlation gate":
        failures.append("high correlation did not block leverage")

    # Unknown correlation must refuse
    l = leverage_decision(enabled=True, regime_key="goldilocks",
                          avg_correlation=None, realised_vol=8)
    if l["leverage"] != 1.00:
        failures.append("unknown correlation did not refuse")

    # All gates pass
    l = leverage_decision(enabled=True, regime_key="goldilocks",
                          avg_correlation=0.25, realised_vol=8,
                          conviction_avg=1.2)
    if not (1.0 < l["leverage"] <= LEVERAGE_HARD_CAP):
        failures.append(f"clean case gave {l['leverage']}")

    # Cap enforcement
    l2 = leverage_decision(enabled=True, regime_key="goldilocks",
                           avg_correlation=0.05, realised_vol=0.1,
                           conviction_avg=5.0)
    if l2["leverage"] > LEVERAGE_HARD_CAP:
        failures.append(f"hard cap breached: {l2['leverage']}")

    # Conviction weights on a REALISTIC universe. The real book has 15
    # sleeves; a 28% cap needs >= 4 sleeves to be satisfiable at all, so
    # testing it against 3 was an invalid test, not a code failure.
    w = {"VGT": 20, "SMH": 4, "QQQ": 4, "GLD": 12, "SLV": 5, "RING": 5,
         "XLE": 5, "PDBC": 3, "SCHD": 13, "XLV": 4, "XLU": 3, "SGOV": 5,
         "USFR": 3, "TLT": 10, "KMLM": 4}
    cv = {"VGT": {"multiplier": 1.40}, "SMH": {"multiplier": 1.40},
          "TLT": {"multiplier": 0.85}, "SCHD": {"multiplier": 1.15}}
    out = apply_conviction(w, cv)
    if abs(sum(out.values()) - 100) > 0.5:
        failures.append(f"conviction weights sum to {sum(out.values())}")
    if any(v > MAX_SLEEVE_PCT + 0.01 for v in out.values()):
        failures.append(f"sleeve cap breached: {out}")
    if out["VGT"] <= w["VGT"]:
        failures.append("high-conviction sleeve not overweighted")
    if out["TLT"] >= w["TLT"]:
        failures.append("low-conviction sleeve not underweighted")

    # Unsatisfiable cap must equal-weight, not breach or hang
    tiny = apply_conviction({"A": 50, "B": 50}, {})
    if abs(sum(tiny.values()) - 100) > 0.5:
        failures.append("unsatisfiable cap broke the 100% total")

    return {"ok": not failures, "failures": failures,
            "clean_leverage": l["leverage"], "capped": l2["leverage"],
            "conviction_example": out}


if __name__ == "__main__":
    import json
    print(json.dumps(selftest(), indent=2, default=str))
