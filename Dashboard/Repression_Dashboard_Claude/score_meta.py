"""
score_meta.py  (v1 — July 2026)
===============================
Versioned denominators for the repression score, and the guard that stops
two incomparable readings from being plotted on the same axis.

THE PROBLEM THIS SOLVES
-----------------------
indicators.build_scorecard() computed:

    max_possible = sum(i["weight"] for i in indicators)
    overall      = round((total_contrib / max_possible) * 10)

The denominator floats with the indicator list. The in-code comment already
recorded that it had moved once ("was 13 before the dollar/gold/auction
additions"). The consequence is not cosmetic:

    Add ONE indicator of weight 1 that currently scores 0.
    Denominator 15 -> 16. Contribution unchanged at 7.
    Score 4.67 -> 4.38. Rounds 5 -> 4.
    Band flips "Moderate repression" -> "Tightening cycle".
    The dashboard now tells you to REDUCE your tilt.
    Nothing happened in the market.

That is the opposite of ground truth. The score exists to answer "HOW HARD to
tilt" — if its scale moves for non-market reasons, the tilt magnitude moves
for non-market reasons.

WHY NOT JUST FREEZE IT
----------------------
Because the flexibility is genuinely valuable: when you find a better
indicator you should be able to add it. Freezing the denominator forever means
never improving the composition.

THE ANSWER IS VERSIONING, NOT CHOOSING
--------------------------------------
Two properties are being conflated:

  COMPOSITION accuracy — are we measuring the right things?
      Improved by adding indicators. Keep the flexibility.
  LEVEL accuracy — does 5/10 mean the same thing this month as last?
      Destroyed by floating. Restored by versioning.

So: pin the denominator PER VERSION, stamp every logged reading with its
version, always display the raw fraction alongside the scaled score, and
refuse to compare across versions without an explicit opt-in.

You get both. Add indicators whenever you like — you just bump the version,
and the log knows which scale each row was measured on.

ADDING AN INDICATOR — the procedure
-----------------------------------
1. Add the score_* function to indicators.py and append it to the list.
2. Add a new entry to VERSIONS below with the new max_possible and the
   indicator names. Bump CURRENT_VERSION.
3. Redeploy. Old logged rows keep their old version stamp and are still
   readable; they are simply not plotted on the same line as the new ones
   unless you pass allow_cross_version=True.
4. Optionally backfill: re-derive history under the new version if you want a
   single comparable series.
"""

from __future__ import annotations

from typing import Iterable, Optional

# --------------------------------------------------------------------------- #
#  Version registry
# --------------------------------------------------------------------------- #
# Each version records the denominator that was in force and the indicator set
# that produced it. `indicators` is the audit trail — it is what lets you tell,
# a year from now, WHY v2 and v3 disagree by half a point.

VERSIONS = {
    "v1": {
        "max_possible": 13,
        "note": "Original 8-indicator set, before the dollar-divergence, "
                "gold-momentum-gate and auction-demand additions.",
        "indicators": [
            "debt_gdp", "deficit", "interest_gdp", "real_policy_rate",
            "tips_real_yield", "fed_independence", "structural_tools",
            "market_pricing",
        ],
        "static_indicators": ["fed_independence", "structural_tools"],
    },
    "v2": {
        "max_possible": 16,
        "note": "Added dollar_divergence, gold_momentum_gate, auction_demand. "
                "This is the denominator that was in force when the score was "
                "still being computed by summing weights at runtime.",
        "indicators": [
            "debt_gdp", "deficit", "interest_gdp", "real_policy_rate",
            "tips_real_yield", "fed_independence", "structural_tools",
            "market_pricing", "dollar_divergence", "gold_momentum_gate",
            "auction_demand",
        ],
        "static_indicators": ["fed_independence", "structural_tools"],
    },
    "v3": {
        "max_possible": 16,
        "note": "Denominator PINNED (no longer summed at runtime). Same "
                "indicator set as v2; the change is that the scale is now "
                "declared rather than derived, so readings are comparable "
                "across deployments. Static indicators are now tagged and "
                "reported separately.",
        "indicators": [
            "debt_gdp", "deficit", "interest_gdp", "real_policy_rate",
            "tips_real_yield", "fed_independence", "structural_tools",
            "market_pricing", "dollar_divergence", "gold_momentum_gate",
            "auction_demand",
        ],
        "static_indicators": ["fed_independence", "structural_tools"],
    },
}

CURRENT_VERSION = "v3"


# --------------------------------------------------------------------------- #
#  Accessors
# --------------------------------------------------------------------------- #
def max_possible(version: str = CURRENT_VERSION) -> int:
    """The pinned denominator for a version. Raises on an unknown version —
    silently defaulting is how an unversioned row gets mixed into a series."""
    if version not in VERSIONS:
        raise KeyError(
            f"Unknown SCORE_VERSION '{version}'. Known: {sorted(VERSIONS)}. "
            f"If you added indicators, add a VERSIONS entry and bump "
            f"CURRENT_VERSION — do not let the denominator float."
        )
    return int(VERSIONS[version]["max_possible"])


def static_indicators(version: str = CURRENT_VERSION) -> list[str]:
    """Indicators that are editorial constants rather than live data.

    In v1-v3 these are fed_independence and structural_tools, which take no
    arguments. They contribute to BOTH numerator and denominator, so roughly
    18% of the score cannot move no matter what markets do. That is defensible
    — the structural tools genuinely are structural — but it has to be LABELED,
    or a reader assumes all eleven indicators are live feeds.
    """
    return list(VERSIONS[version].get("static_indicators", []))


def scale(total_contrib: float, version: str = CURRENT_VERSION) -> dict:
    """
    Scale a raw contribution to 0-10 against the PINNED denominator.

    Returns a dict rather than a float so the raw fraction travels with the
    scaled number. The dashboard should render both:

        "5.2 / 10   (v3: 8 of 16 pts)"

    because the scaled number alone hides a denominator change and the raw
    fraction alone is not comparable to the published band thresholds.
    """
    mx = max_possible(version)
    raw = float(total_contrib)
    scaled_exact = (raw / mx) * 10.0 if mx else 0.0
    scaled = max(0.0, min(10.0, scaled_exact))
    return {
        "version": version,
        "raw_contrib": raw,
        "max_possible": mx,
        "scaled_exact": round(scaled, 2),
        "scaled_int": int(round(scaled)),
        "display": f"{scaled:.1f} / 10  ({version}: {raw:g} of {mx} pts)",
        "static_share_pct": round(
            100.0 * len(static_indicators(version)) / mx, 1) if mx else 0.0,
    }


# --------------------------------------------------------------------------- #
#  Band thresholds — declared once, here, so they cannot drift from the scale
# --------------------------------------------------------------------------- #
# These are the bands from the written framework. They are defined on the
# 0-10 SCALED score, which is precisely why the denominator has to be pinned:
# a floating denominator silently re-calibrates every one of these.
BANDS = [
    (8.0, "Peak repression"),
    (5.0, "Moderate repression"),
    (2.0, "Tightening cycle"),
    (0.0, "Anti-repression"),
]


def band(scaled_score: float) -> str:
    for threshold, name in BANDS:
        if scaled_score >= threshold:
            return name
    return "Anti-repression"


def band_with_context(scaled: dict, top_weight_earned: int,
                      top_weight_total: int) -> dict:
    """
    The band label PLUS the honest caveat about where the points came from.

    A score of 5 built entirely from fiscal-and-plumbing components is not the
    same state as a score of 5 that includes both real-yield components, even
    though the band label is identical. On 2026-07-29 the score was 4-5 with
    0 of 4 top-weight points: short real rate was not negative and DFII10 was
    2.44%, not below 1%. The band read "Moderate repression" while both of the
    framework's heaviest gauges were off.

    This is the same design principle as the existing `missing[]` list — a
    degraded 5 and a true 5 are different states and the caller must be able
    to tell them apart.
    """
    label = band(scaled["scaled_exact"])
    hollow = top_weight_total > 0 and top_weight_earned == 0
    out = dict(scaled)
    out.update({
        "band": label,
        "top_weight_earned": top_weight_earned,
        "top_weight_total": top_weight_total,
        "top_weight_display": f"{top_weight_earned}/{top_weight_total}",
        "hollow": hollow,
    })
    if hollow:
        out["caveat"] = (
            f"HOLLOW {label}: 0 of {top_weight_total} top-weight points earned. "
            f"Every point in this score comes from second-tier components "
            f"(fiscal, liquidity, credit, CPI level). The framework's two "
            f"heaviest gauges — the sign of the short real policy rate and "
            f"DFII10 below 1% — are both OFF. Treat the band label as an "
            f"upper bound on the strength of the repression read."
        )
    elif top_weight_earned < top_weight_total:
        out["caveat"] = (
            f"PARTIAL {label}: {top_weight_earned} of {top_weight_total} "
            f"top-weight points earned. The read is directionally supported "
            f"but not fully confirmed by the primary gauges."
        )
    else:
        out["caveat"] = ""
    return out


# --------------------------------------------------------------------------- #
#  Comparability guard
# --------------------------------------------------------------------------- #
def assert_comparable(versions: Iterable[str],
                      allow_cross_version: bool = False) -> Optional[str]:
    """
    Call this before charting or averaging a logged score series.

    Returns None when the series is safe, or a warning string when it mixes
    versions. Raises only if allow_cross_version is False AND versions differ,
    because a chart that silently splices two scales is worse than no chart.
    """
    seen = sorted({v for v in versions if v})
    if len(seen) <= 1:
        return None
    denominators = {v: VERSIONS[v]["max_possible"] for v in seen if v in VERSIONS}
    msg = (f"Score series mixes versions {seen} with denominators "
           f"{denominators}. These readings are NOT on the same scale.")
    if not allow_cross_version:
        raise ValueError(
            msg + " Pass allow_cross_version=True to plot anyway, or backfill "
                  "the history under a single version."
        )
    return msg


def log_row(scaled: dict, extra: dict | None = None) -> dict:
    """
    The row shape to persist. Always carries the version and the denominator,
    so a row is self-describing even if VERSIONS is edited later.
    """
    row = {
        "score_version": scaled["version"],
        "max_possible": scaled["max_possible"],
        "raw_contrib": scaled["raw_contrib"],
        "score_scaled": scaled["scaled_exact"],
        "band": scaled.get("band", band(scaled["scaled_exact"])),
        "top_weight": scaled.get("top_weight_display", ""),
        "hollow": scaled.get("hollow", None),
    }
    if extra:
        row.update(extra)
    return row


def selftest() -> dict:
    """Verify the denominator-drift scenario is now caught."""
    failures = []

    # The exact scenario the floating denominator produced.
    v2 = scale(7, "v2")
    v3 = scale(7, "v3")
    if v2["max_possible"] != v3["max_possible"]:
        failures.append("v2/v3 denominators unexpectedly differ")

    # A v1 reading and a v3 reading of the same raw contribution must NOT be
    # treated as equal.
    a, b = scale(7, "v1"), scale(7, "v3")
    if abs(a["scaled_exact"] - b["scaled_exact"]) < 0.5:
        failures.append("v1 vs v3 scaling difference not detected")

    # The guard must refuse to mix them.
    try:
        assert_comparable(["v1", "v3"])
        failures.append("assert_comparable failed to raise on mixed versions")
    except ValueError:
        pass

    hollow = band_with_context(scale(5, "v3"), top_weight_earned=0,
                              top_weight_total=4)
    if not hollow["hollow"]:
        failures.append("hollow-score detection failed")

    return {"ok": not failures, "failures": failures,
            "current_version": CURRENT_VERSION,
            "current_max": max_possible(),
            "static_share_pct": scale(0)["static_share_pct"],
            "example_hollow_caveat": hollow["caveat"]}


if __name__ == "__main__":
    import json
    print(json.dumps(selftest(), indent=2, default=str))
