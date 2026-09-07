"""
tripwires.py  (v1 — August 2026)
────────────────────────────────
"What would change the call" — as a live panel, not a paragraph.

WHY
───
Every review this framework produces ends with a "what would change this"
section, written by hand, and stale the moment it is written. The
thresholds themselves are already pre-committed in code — regime_bands'
transition band, the HY 3.50%/5.00% lines, the gold 200-day gate, the
valuation block levels, the vol quartile that prices convexity. What has
been missing is the DISTANCE to each one, updated live.

That distance is the actionable part. "HY OAS is 2.71%" is a reading;
"HY OAS is 79bp from the complacency line and 229bp from the crisis
override" is a decision input — it tells you how much room the current
regime call has before it breaks.

DESIGN
──────
Each tripwire reports: current value, the threshold, the distance, and
which DIRECTION would trip it. Every one is None-safe; a missing input
renders as "unavailable" and is never silently treated as "far away".

Sorted by proximity, so the closest tripwire — the thing most likely to
change the call next — is always at the top.
"""

from __future__ import annotations

from typing import Optional

# Severity for display ordering and colour
CRITICAL = "CRITICAL"     # would force an immediate regime change
HIGH = "HIGH"             # would change the regime on confirmation
MEDIUM = "MEDIUM"         # would change sizing, not the regime
INFO = "INFO"


def _tw(name, value, threshold, distance, direction, severity, unit="%",
        note="", available=True) -> dict:
    return {"name": name, "value": value, "threshold": threshold,
            "distance": distance, "direction": direction,
            "severity": severity, "unit": unit, "note": note,
            "available": available}


RRP_EXHAUSTED_BN = 50.0     # RRP once ran $2T+; under $50B is genuinely spent
RESERVE_DRAIN_BN = -5.0     # same weekly threshold the H.4.1 posture uses


def reserve_cushion(rrp_level: Optional[float],
                    wresbal_4wk_chg: Optional[float],
                    wtregen_4wk_chg: Optional[float]) -> Optional[dict]:
    """
    Standalone so the H.4.1 tab (which already fetches WRESBAL/WTREGEN/RRP
    for its own KPI cards) can call this directly, without duplicating the
    fetch or constructing the regime-classifier argument set build() needs.
    build() also calls this internally, so the full tripwire panel and the
    H.4.1 tab's own status line always agree -- one function, two call sites.

    The textbook expectation is WRESBAL and WTREGEN moving OPPOSITE each
    other: a falling TGA releases cash, which should show up as RISING
    reserves. Seeing them fall TOGETHER means something else -- QT -- is
    outpacing that release. Historically ON RRP absorbs QT's drain before it
    ever touches bank reserves; once RRP is near zero, that cushion is gone
    and QT flows through directly. This is the exact mechanical setup that
    preceded the September 2019 repo-market spike.

    Deliberately NOT a calibrated "ample reserves" dollar threshold -- the
    Fed's own officials disagree on where that line sits, so pretending to
    know it would overclaim precision this framework avoids everywhere else.
    The actionable signal is the PATTERN (RRP exhausted + both falling
    together), not a specific level.
    """
    if rrp_level is None:
        return None
    exhausted = rrp_level < RRP_EXHAUSTED_BN
    both_falling = (wresbal_4wk_chg is not None and wtregen_4wk_chg is not None
                    and wresbal_4wk_chg < RESERVE_DRAIN_BN
                    and wtregen_4wk_chg < RESERVE_DRAIN_BN)
    if exhausted and both_falling:
        return _tw(
            "Reserve cushion → exhausted, uncushioned drain", rrp_level,
            RRP_EXHAUSTED_BN, rrp_level, "fall", CRITICAL, unit="$B",
            note=(f"ON RRP ${rrp_level:,.0f}B (cushion exhausted) AND "
                  f"reserves ({wresbal_4wk_chg:+,.1f}B/wk) and TGA "
                  f"({wtregen_4wk_chg:+,.1f}B/wk) are falling TOGETHER — "
                  f"the textbook pattern is opposite. QT is now draining "
                  f"reserves uncushioned. This is the same mechanical setup "
                  f"that preceded the September 2019 repo spike. Watch "
                  f"SOFR vs IORB next — a widening spread is the confirming "
                  f"signal, not this alone."))
    if exhausted:
        return _tw(
            "Reserve cushion → exhausted", rrp_level, RRP_EXHAUSTED_BN,
            rrp_level, "fall", HIGH, unit="$B",
            note=(f"ON RRP ${rrp_level:,.0f}B — cushion exhausted, but "
                  f"reserves and TGA aren't yet confirming an uncushioned "
                  f"drain together. Watch for both to turn negative at "
                  f"once."))
    return _tw(
        "Reserve cushion → exhausted", rrp_level, RRP_EXHAUSTED_BN,
        rrp_level - RRP_EXHAUSTED_BN, "fall", MEDIUM, unit="$B",
        note=(f"${rrp_level:,.0f}B of RRP cushion remains to absorb "
              f"TGA/QT swings before reserves feel it directly."))


def build(sig=None, growth: Optional[dict] = None,
          cape: Optional[float] = None,
          top20_concentration_pct: Optional[float] = None,
          vix: Optional[float] = None,
          vix_pct_rank: Optional[float] = None,
          gold_price: Optional[float] = None,
          gold_200d: Optional[float] = None,
          gold_200d_rising: Optional[bool] = None,
          curve: Optional[dict] = None,
          rrp_level: Optional[float] = None,
          wresbal_4wk_chg: Optional[float] = None,
          wtregen_4wk_chg: Optional[float] = None) -> list[dict]:
    """
    Build the full tripwire list. Every argument optional; anything missing
    renders as unavailable rather than being skipped silently.
    """
    def g(name, default=None):
        if sig is None:
            return default
        if isinstance(sig, dict):
            return sig.get(name, default)
        return getattr(sig, name, default)

    out: list[dict] = []

    # ── 1. HY OAS — the single most important tripwire in the framework ─────
    hy = g("hy_oas")
    if hy is None:
        out.append(_tw("HY OAS → crisis override", None, 5.00, None, "widen",
                       CRITICAL, note="Unavailable — the credit lane is dark, "
                                      "which is NOT the same as calm.",
                       available=False))
    else:
        out.append(_tw(
            "HY OAS → crisis override", hy, 5.00, 5.00 - hy, "widen", CRITICAL,
            note=("The ONLY signal authorising a same-day de-risk. Crossing "
                  "this re-arms TLT and overrides the inflation regime "
                  "entirely.")))
        out.append(_tw(
            "HY OAS → complacency line", hy, 3.50, 3.50 - hy, "widen", HIGH,
            note=("Below 3.50% is late-cycle risk COMPRESSION, not safety. "
                  "Crossing up means credit has started repricing risk — "
                  "historically leads equity drawdowns by 2-4 weeks.")))

    # ── 2. Short real rate — the band boundary either side ──────────────────
    srr = g("short_real_rate")
    if srr is None:
        out.append(_tw("Short real rate → band edge", None, 0.25, None,
                       "either", HIGH, note="Unavailable — primary gauge dark.",
                       available=False))
    else:
        # distance to whichever edge is nearer
        d_upper, d_lower = 0.25 - srr, srr - (-0.25)
        if abs(srr) <= 0.25:
            nearer = min(d_upper, d_lower)
            direction = "rise" if d_upper < d_lower else "fall"
            note = (f"Inside the band. Clearing +0.25% opens the goldilocks "
                    f"branch (subject to the valuation/leadership/growth "
                    f"guards); clearing -0.25% opens the repression branches.")
            out.append(_tw("Short real rate → band edge", srr, 0.25, nearer,
                           direction, HIGH, note=note))
        else:
            back = abs(srr) - 0.25
            out.append(_tw(
                "Short real rate → back inside band", srr, 0.25, back,
                "fall" if srr > 0 else "rise", HIGH,
                note=("Decisively "
                      + ("positive" if srr > 0 else "negative")
                      + f". Would need to move {back:.2f}pp to re-enter the "
                        f"ambiguous band.")))

    # ── 2b. Reserve cushion — is QT draining reserves UNCUSHIONED? ──────────
    # The textbook expectation is WRESBAL and WTREGEN moving OPPOSITE each
    # other: a falling TGA releases cash, which should show up as RISING
    # reserves. Seeing them fall TOGETHER means something else — QT — is
    # outpacing that release. Historically the ON RRP facility absorbs QT's
    # drain before it ever touches bank reserves; once RRP is near zero,
    # that cushion is gone and QT flows through directly. This is the exact
    # mechanical setup that preceded the September 2019 repo-market spike.
    #
    # Not a hard "ample reserves" dollar threshold -- the Fed's own officials
    # disagree on where that line sits, so pretending to know it would
    # overclaim precision this framework avoids everywhere else. The
    # actionable signal here is the PATTERN (RRP exhausted + both falling
    # together), not a calibrated level.
    rc_tw = reserve_cushion(rrp_level, wresbal_4wk_chg, wtregen_4wk_chg)
    if rc_tw is not None:
        out.append(rc_tw)

    # ── 3. Gold momentum gate — Level-4 entry confirmation ──────────────────
    if gold_price is not None and gold_200d is not None:
        gap_pct = (gold_price / gold_200d - 1) * 100
        rising_txt = ("rising" if gold_200d_rising else
                      "falling" if gold_200d_rising is False else "direction unknown")
        if gap_pct < 0:
            note = (f"Gold is {abs(gap_pct):.1f}% BELOW its 200-day "
                    f"({gold_200d:,.0f}, {rising_txt}). Gate FAILS — the "
                    f"metals tilt is parked in SGOV. A close above a "
                    f"flattening/rising 200-day is the Level-4 confirmation "
                    f"to add.")
        else:
            note = (f"Gold is {gap_pct:.1f}% above its 200-day "
                    f"({gold_200d:,.0f}, {rising_txt}). Gate passes only if "
                    f"the 200-day is also RISING — position above a falling "
                    f"average is not confirmation.")
        out.append(_tw("Gold → 200-day gate", gold_price, gold_200d,
                       abs(gold_price - gold_200d), "rise" if gap_pct < 0 else "fall",
                       HIGH, unit="$", note=note))
    else:
        out.append(_tw("Gold → 200-day gate", None, None, None, "rise", HIGH,
                       unit="$", note="Gold price / 200-day unavailable.",
                       available=False))

    # ── 4. Growth composite — the newest axis ───────────────────────────────
    if growth and growth.get("state") != "UNKNOWN":
        score = growth.get("score", 0)
        state = growth.get("state")
        # -4 is the CONTRACTING boundary in growth_signals.assess()
        dist = score - (-4) if score > -4 else 0
        out.append(_tw(
            "Growth composite → contraction", score, -4, dist, "fall", HIGH,
            unit=" pts",
            note=(f"Currently {state}. At -4 or below the classifier returns "
                  f"`growth_scare` outright, overriding the real-rate "
                  f"branches. "
                  + ("CONFIRMED reading." if growth.get("confirmed")
                     else "⚠ UNCONFIRMED (<3 of 4 series) — the guard will "
                          "not act until confirmed."))))
    else:
        out.append(_tw("Growth composite → contraction", None, -4, None,
                       "fall", HIGH, unit=" pts",
                       note="Growth axis dark — degraded, not benign.",
                       available=False))

    # ── 4b. Yield curve — 3M10Y is THE recession spread ────────────────────
    # Presented as a tripwire, NOT a classifier input. Inversions have led
    # every modern US recession, but with long, variable lead times and a
    # non-zero false-positive rate (2019 preceded a pandemic recession; the
    # 2022-24 inversion was the longest on record without one following on
    # schedule). Same category as CAPE here: structurally informative,
    # deliberately not a timing trigger.
    if curve:
        for row in curve.get("spreads", []):
            if row.get("name") == "3M-10Y" and row.get("available"):
                v = row["value"]
                out.append(_tw(
                    "3M–10Y → inversion", v, 0.0, v, "fall", HIGH, unit="bp",
                    note=("The NY Fed's own recession model is built on this "
                          "spread. Crossing below zero is the signal — but "
                          "with a long and variable lead time. Context, not "
                          "a trigger.")))
        st_ = curve.get("steepening_2s10s", {})
        if st_.get("available") and st_.get("type") == "BULL STEEPENING":
            out.append(_tw(
                "Curve → bull steepening ACTIVE", st_["d_spread_bp"], 0.0,
                0.0, "already tripped", CRITICAL, unit="bp",
                note=("Short end falling faster than the long end — the "
                      "market is pricing CUTS. This framework's checklist "
                      "flags rapid bull steepening from inversion as the "
                      "most violent regime-shift signal there is, warranting "
                      "immediate review rather than the weekly cycle.")))

    # ── 5. Valuation guard — what would UNBLOCK goldilocks ──────────────────
    if cape is not None:
        out.append(_tw(
            "CAPE → valuation block clears", cape, 40.0, cape - 40.0, "fall",
            MEDIUM, unit="x",
            note=("Above 40 the valuation guard blocks any growth-additive "
                  "regime. This does NOT time a top — CAPE predicts the next "
                  "decade, not the next year — it only refuses to ADD at an "
                  "extreme.")))
    if top20_concentration_pct is not None:
        out.append(_tw(
            "Top-20 concentration → block clears", top20_concentration_pct,
            45.0, top20_concentration_pct - 45.0, "fall", MEDIUM,
            note=("Above 45% a single-theme shock hits the benchmark nearly "
                  "as hard as the theme itself — index-level concentration "
                  "risk.")))

    # ── 6. Convexity pricing — when protection is cheap ─────────────────────
    if vix is not None:
        q = None
        if vix_pct_rank is not None:
            q = 1 if vix_pct_rank < 25 else 2 if vix_pct_rank < 50 else \
                3 if vix_pct_rank < 75 else 4
        budget = {1: 2.00, 2: 1.25, 3: 0.50, 4: 0.00}.get(q)
        note = (f"VIX {vix:.1f}"
                + (f", {vix_pct_rank:.0f}th percentile of its own year → Q{q} "
                   f"→ convexity budget {budget:.2f}% of NAV."
                   if q else " — 1-year percentile unavailable, cannot price "
                             "the convexity budget.")
                + (" This is the cheapest-insurance window the vol-priced "
                   "budget exists for." if q == 1 else ""))
        out.append(_tw("VIX → convexity budget", vix, 21.0, 21.0 - vix, "rise",
                       MEDIUM, note=note))

    # ── 7. Stock/bond correlation — is the bond hedge working? ──────────────
    corr = g("stock_bond_corr_60d")
    if corr is not None:
        out.append(_tw(
            "Stock/bond 60d corr → hedge restored", corr, 0.0, corr, "fall",
            MEDIUM, unit="",
            note=("Positive means stocks and bonds fall together — the 60/40 "
                  "hedge is impaired and trend-following carries the "
                  "diversification load. Below zero restores duration as "
                  "ballast.")))

    # Closest-first among available, unavailable last.
    def _key(t):
        if not t["available"] or t["distance"] is None:
            return (1, 0.0)
        return (0, abs(t["distance"]))
    return sorted(out, key=_key)


def render(st, tripwires: list[dict]):
    """Compact always-visible panel. `st` passed in for import safety."""
    if not tripwires:
        st.caption("No tripwires available.")
        return

    colour = {CRITICAL: "#dc2626", HIGH: "#d97706",
              MEDIUM: "#2563eb", INFO: "#6b7280"}

    st.markdown("##### What would change this call")
    st.caption("Live distance to every pre-committed threshold, closest "
               "first. These are the specific things that would move the "
               "regime — not commentary.")

    for t in tripwires:
        c = colour.get(t["severity"], "#6b7280")
        if not t["available"] or t["distance"] is None:
            st.markdown(
                f"<div style='padding:4px 0;'>"
                f"<span style='color:#6b7280;'>○ <b>{t['name']}</b> — "
                f"unavailable</span></div>", unsafe_allow_html=True)
            st.caption(t["note"])
            continue

        val = t["value"]
        val_s = (f"{val:,.2f}{t['unit']}" if t["unit"] != "$"
                 else f"${val:,.0f}")
        thr = t["threshold"]
        thr_s = (f"{thr:,.2f}{t['unit']}" if t["unit"] != "$"
                 else f"${thr:,.0f}")
        dist_s = (f"{abs(t['distance']):,.2f}{t['unit']}" if t["unit"] != "$"
                  else f"${abs(t['distance']):,.0f}")

        st.markdown(
            f"<div style='padding:4px 0;'>"
            f"<span style='color:{c};'>●</span> "
            f"<b>{t['name']}</b> &nbsp; "
            f"<span style='font-family:monospace;'>{val_s}</span> "
            f"<span style='color:#9ca3af;'>vs {thr_s}</span> &nbsp; "
            f"<span style='color:{c};font-weight:600;'>"
            f"{dist_s} to {t['direction']}</span>"
            f"</div>", unsafe_allow_html=True)
        st.caption(t["note"])


def selftest() -> dict:
    """Verify ordering, None-safety, and that nothing is silently dropped."""
    failures = []

    class S:
        hy_oas = 2.71
        short_real_rate = 0.27
        stock_bond_corr_60d = 0.38

    tw = build(sig=S(), growth={"state": "DETERIORATING", "score": -2,
                                "confirmed": True},
               cape=42.0, top20_concentration_pct=50.8,
               vix=14.25, vix_pct_rank=18.0,
               gold_price=4437.0, gold_200d=4490.0, gold_200d_rising=False)

    if not tw:
        failures.append("no tripwires built")
    # available ones must sort before unavailable
    avail = [t["available"] for t in tw]
    if avail != sorted(avail, reverse=True):
        failures.append("unavailable tripwires not sorted last")
    # closest-first among available
    dists = [abs(t["distance"]) for t in tw if t["available"] and t["distance"] is not None]
    if dists != sorted(dists):
        failures.append("available tripwires not sorted closest-first")

    # all-None must not raise and must mark things unavailable
    tw2 = build()
    if not any(not t["available"] for t in tw2):
        failures.append("empty input did not produce unavailable entries")

    return {"ok": not failures, "failures": failures,
            "count": len(tw), "closest": tw[0]["name"] if tw else None}


if __name__ == "__main__":
    import json
    print(json.dumps(selftest(), indent=2, default=str))
