"""
curve_analysis.py  (v1 — August 2026)
─────────────────────────────────────
The full Treasury curve — shape, spreads, inversions, and the steepening
TYPE that a single spread cannot tell you.

WHY A SINGLE SPREAD IS NOT ENOUGH
─────────────────────────────────
This framework has tracked 2s10s and nothing else. That is one slice of a
shape with several distinct, differently-meaningful segments, and it misses
the single most predictive spread on the curve.

    3M-2Y    Policy-pivot expectations. The 3-month bill tracks the CURRENT
             policy rate almost exactly; the 2-year embeds expected cuts.
             This segment inverts when the market prices a pivot.

    3M-10Y   THE RECESSION SIGNAL. The New York Fed's own recession
             probability model is built on this spread, and Estrella &
             Mishkin's research found it outperformed alternatives. The
             mechanism: because the 3-month tracks current policy while the
             10-year embeds growth and inflation expectations, this measures
             "is policy tight relative to where the economy is heading."
             2s10s mutes exactly this signal, because the 2-year has already
             priced the cuts -- the muting is worst precisely when it
             matters most.

    2Y-10Y   The classic, and the one this framework already had.

    10Y-30Y  PURE TERM PREMIUM. No policy-expectation content -- the Fed
             does not credibly influence the 20-year-forward rate. This is
             the cleanest read on fiscal/supply/credibility risk, which is
             exactly the story when the 30-year sits at a 19-year high while
             the dollar FALLS (normally higher yields support the currency;
             when they do not, buyers are demanding compensation to hold US
             paper at all).

WHY THE SHAPE BEATS ANY NUMBER
──────────────────────────────
A 2s10s reading of +48bp means OPPOSITE things depending on which end
moved:

    BULL steepening   short end falls faster -> market pricing CUTS ->
                      historically the most violent regime-shift signal, and
                      the one this framework's own checklist flags as
                      demanding immediate review
    BEAR steepening   long end rises faster -> term premium / inflation /
                      supply -> duration is the enemy, not the hedge

The spread is identical. The implication is inverted. Only decomposing the
move into its two ends distinguishes them, which is what classify_steepening()
below does.

THE HONEST CAVEAT
─────────────────
Inversions have preceded every modern US recession, but the lead time is
long, variable, and the false-positive rate is not zero: the 2019 inversion
preceded a recession that arrived via a pandemic, and the 2022-24 inversion
was the longest on record without a recession following on the historical
schedule. This belongs in the same category as CAPE in this framework --
structurally informative, NOT a timing tool. It is presented here as
context, and deliberately does NOT feed the regime classifier's branch
logic.
"""

from __future__ import annotations

from typing import Callable, Optional

# Full curve, short to long. All from FRED, daily, constant-maturity.
CURVE_SERIES = {
    "3M": "DGS3MO",
    "6M": "DGS6MO",
    "1Y": "DGS1",
    "2Y": "DGS2",
    "5Y": "DGS5",
    "7Y": "DGS7",
    "10Y": "DGS10",
    "20Y": "DGS20",
    "30Y": "DGS30",
}

# Ordered for plotting — years to maturity, so the x-axis is economically
# spaced rather than evenly spaced by label.
TENOR_YEARS = {"3M": 0.25, "6M": 0.5, "1Y": 1, "2Y": 2, "5Y": 5,
               "7Y": 7, "10Y": 10, "20Y": 20, "30Y": 30}

# The four segments that carry distinct information.
SPREADS = {
    "3M-2Y": ("3M", "2Y",
              "Policy-pivot expectations. Inverts when the market prices "
              "cuts before the Fed delivers them."),
    "3M-10Y": ("3M", "10Y",
               "THE recession signal — the spread the NY Fed's own model "
               "uses. Measures policy tightness against the growth and "
               "inflation outlook."),
    "2Y-10Y": ("2Y", "10Y",
               "The classic spread. Widely watched, but the 2-year already "
               "embeds expected cuts, which mutes the signal."),
    "10Y-30Y": ("10Y", "30Y",
                "PURE term premium — no meaningful policy-expectation "
                "content. The cleanest read on fiscal, supply and "
                "credibility risk."),
}

# Steepening types
BULL_STEEPEN = "BULL STEEPENING"
BEAR_STEEPEN = "BEAR STEEPENING"
BULL_FLATTEN = "BULL FLATTENING"
BEAR_FLATTEN = "BEAR FLATTENING"
PARALLEL_UP = "PARALLEL SHIFT UP"
PARALLEL_DOWN = "PARALLEL SHIFT DOWN"
UNCHANGED = "LITTLE CHANGED"

STEEPENING_MEANING = {
    BULL_STEEPEN: ("Short end falling faster than the long end — the market "
                   "is pricing CUTS. Historically the most violent "
                   "regime-shift signal on the curve, and the one that "
                   "warrants immediate review rather than waiting for the "
                   "weekly cycle. Often marks the transition from 'inflation "
                   "problem' to 'growth problem'."),
    BEAR_STEEPEN: ("Long end rising faster than the short end — term "
                   "premium, inflation risk, or supply. Duration is the "
                   "enemy here, not the hedge. This is the signature of a "
                   "fiscal/credibility repricing rather than a growth story."),
    BULL_FLATTEN: ("Long end falling faster — the market is buying duration, "
                   "typically a growth-scare or flight-to-quality bid. "
                   "Duration works in this one."),
    BEAR_FLATTEN: ("Short end rising faster — the Fed is hiking, or expected "
                   "to. Classic mid-tightening-cycle shape."),
    PARALLEL_UP: ("The whole curve shifted up together — a level move, not a "
                  "shape change. Usually an inflation-expectations or "
                  "global-rates story rather than a Fed-path story."),
    PARALLEL_DOWN: ("The whole curve shifted down together — broad easing of "
                    "financial conditions."),
    UNCHANGED: "No material change in level or shape.",
}


def _last(series) -> Optional[float]:
    try:
        s = series.dropna()
        return float(s.iloc[-1]) if len(s) else None
    except Exception:
        return None


def _asof(series, days_back: int) -> Optional[float]:
    """Value approximately N calendar days ago. None if history is short."""
    try:
        s = series.dropna()
        if len(s) < 2:
            return None
        target = s.index[-1] - __import__("pandas").Timedelta(days=days_back)
        prior = s[s.index <= target]
        return float(prior.iloc[-1]) if len(prior) else None
    except Exception:
        return None


def fetch_curve(fetch_fred: Callable, api_key: str = "",
                start: str = "2018-01-01") -> dict:
    """
    Fetch every tenor. Returns raw series plus point-in-time snapshots.

    Never raises. A tenor that fails is named in `missing` and simply
    absent from the curve — never interpolated, because a fabricated point
    on a yield curve is indistinguishable from a real one downstream.
    """
    out = {"series": {}, "today": {}, "m3": {}, "y1": {}, "missing": [],
           "asof": None}

    for label, sid in CURVE_SERIES.items():
        try:
            s = fetch_fred(sid, api_key, start)
            if s is None or len(s.dropna()) == 0:
                out["missing"].append(f"{label} ({sid})")
                continue
            s = s.dropna()
            out["series"][label] = s
            out["today"][label] = _last(s)
            out["m3"][label] = _asof(s, 91)
            out["y1"][label] = _asof(s, 365)
            if out["asof"] is None:
                out["asof"] = s.index[-1]
        except Exception as e:
            out["missing"].append(f"{label} ({type(e).__name__})")
    return out


def compute_spreads(curve_today: dict) -> list[dict]:
    """All four spreads with inversion status."""
    rows = []
    for name, (short_t, long_t, why) in SPREADS.items():
        s_val = curve_today.get(short_t)
        l_val = curve_today.get(long_t)
        if s_val is None or l_val is None:
            rows.append({"name": name, "value": None, "inverted": None,
                        "short": short_t, "long": long_t, "why": why,
                        "available": False,
                        "detail": f"{short_t} or {long_t} unavailable."})
            continue
        spread = (l_val - s_val) * 100  # basis points
        inverted = spread < 0
        rows.append({
            "name": name, "value": spread, "inverted": inverted,
            "short": short_t, "long": long_t, "why": why, "available": True,
            "short_val": s_val, "long_val": l_val,
            "detail": (f"{long_t} {l_val:.2f}% − {short_t} {s_val:.2f}% = "
                      f"{spread:+.0f}bp"
                      + (" — INVERTED" if inverted else "")),
        })
    return rows


def inversion_duration(series_short, series_long,
                       max_lookback: int = 750) -> Optional[dict]:
    """
    How long the current inversion (if any) has persisted.

    Duration matters: a one-day dip below zero and a six-month inversion are
    different states, and only the second has historically carried signal.
    """
    try:
        import pandas as pd
        s = pd.concat([series_short.dropna(), series_long.dropna()],
                     axis=1, join="inner").tail(max_lookback)
        if s.empty:
            return None
        spread = (s.iloc[:, 1] - s.iloc[:, 0]) * 100
        if spread.iloc[-1] >= 0:
            # Not inverted now — report days since the last inversion ended.
            inv = spread < 0
            if not inv.any():
                return {"inverted_now": False, "days": 0,
                        "detail": "No inversion in the lookback window."}
            last_inv = inv[inv].index[-1]
            days = (spread.index[-1] - last_inv).days
            return {"inverted_now": False, "days": days,
                    "detail": f"Not inverted. Last inversion ended ~{days} "
                             f"days ago."}
        # Currently inverted — walk back to find when it started.
        streak = 0
        for v in reversed(spread.values):
            if v < 0:
                streak += 1
            else:
                break
        start_date = spread.index[-streak]
        return {"inverted_now": True, "days": streak,
                "since": start_date,
                "detail": (f"INVERTED for {streak} consecutive observations "
                          f"(since {start_date:%Y-%m-%d}). Duration matters — "
                          f"a brief dip and a sustained inversion are "
                          f"different states.")}
    except Exception:
        return None


def classify_steepening(today: dict, prior: dict,
                        short_t: str = "2Y", long_t: str = "10Y",
                        threshold_bp: float = 10.0) -> dict:
    """
    Decompose a curve move into bull/bear × steepening/flattening.

    THIS IS THE POINT OF THE MODULE. A 2s10s of +48bp means opposite things
    depending on which end moved to get there, and no single spread reading
    can distinguish them.
    """
    s_now, l_now = today.get(short_t), today.get(long_t)
    s_old, l_old = prior.get(short_t), prior.get(long_t)
    if None in (s_now, l_now, s_old, l_old):
        return {"type": None, "available": False,
                "detail": f"Need both {short_t} and {long_t} at two dates."}

    d_short = (s_now - s_old) * 100
    d_long = (l_now - l_old) * 100
    d_spread = d_long - d_short

    if abs(d_short) < threshold_bp and abs(d_long) < threshold_bp:
        t = UNCHANGED
    elif abs(d_spread) < threshold_bp:
        t = PARALLEL_UP if d_long > 0 else PARALLEL_DOWN
    elif d_spread > 0:                      # steepening
        t = BEAR_STEEPEN if d_long > abs(d_short) or d_short >= 0 else BULL_STEEPEN
    else:                                    # flattening
        t = BEAR_FLATTEN if d_short > 0 else BULL_FLATTEN

    return {
        "type": t, "available": True,
        "d_short_bp": round(d_short, 1), "d_long_bp": round(d_long, 1),
        "d_spread_bp": round(d_spread, 1),
        "short_t": short_t, "long_t": long_t,
        "meaning": STEEPENING_MEANING.get(t, ""),
        "detail": (f"{short_t} {d_short:+.0f}bp, {long_t} {d_long:+.0f}bp → "
                  f"spread {d_spread:+.0f}bp"),
    }


def assess(fetch_fred: Callable, api_key: str = "") -> dict:
    """One-call: fetch, compute spreads, classify the 3-month move."""
    curve = fetch_curve(fetch_fred, api_key)
    spreads = compute_spreads(curve["today"])
    steep_2s10s = classify_steepening(curve["today"], curve["m3"], "2Y", "10Y")
    steep_10s30s = classify_steepening(curve["today"], curve["m3"], "10Y", "30Y")

    inverted = [r["name"] for r in spreads if r.get("inverted")]
    dur = None
    if "3M" in curve["series"] and "10Y" in curve["series"]:
        dur = inversion_duration(curve["series"]["3M"], curve["series"]["10Y"])

    return {"curve": curve, "spreads": spreads,
            "steepening_2s10s": steep_2s10s,
            "steepening_10s30s": steep_10s30s,
            "inverted_spreads": inverted,
            "recession_spread_duration": dur,
            "headline": (f"{len(inverted)} of {len(spreads)} spreads inverted"
                        + (f": {', '.join(inverted)}" if inverted else "")),
            "missing": curve["missing"]}


def render(st, data: dict):
    """Render the Curve tab."""
    import pandas as pd

    st.markdown("### Yield Curve")
    st.caption(
        "The full curve, not one spread. Different segments answer different "
        "questions, and the SHAPE of a move carries information no single "
        "number can."
    )

    curve = data["curve"]
    if not curve["today"]:
        st.error("No curve data available.")
        return
    if curve["missing"]:
        st.caption(f"⚠ Missing tenors: {', '.join(curve['missing'])} — these "
                  f"are omitted, never interpolated.")

    # ── The curve itself, three dates ───────────────────────────────────────
    rows = []
    for label in CURVE_SERIES:
        for when, key in (("Today", "today"), ("3 months ago", "m3"),
                          ("1 year ago", "y1")):
            v = curve[key].get(label)
            if v is not None:
                rows.append({"Tenor": label, "Years": TENOR_YEARS[label],
                            "Yield": v, "When": when})
    if rows:
        df = pd.DataFrame(rows)
        try:
            import plotly.express as px
            fig = px.line(df.sort_values("Years"), x="Tenor", y="Yield",
                         color="When", markers=True,
                         category_orders={"Tenor": list(CURVE_SERIES)})
            fig.update_layout(height=380, margin=dict(l=10, r=10, t=30, b=10),
                             paper_bgcolor="rgba(0,0,0,0)",
                             plot_bgcolor="rgba(0,0,0,0)",
                             yaxis_title="Yield (%)", xaxis_title="")
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            st.dataframe(df.pivot(index="Tenor", columns="When",
                                 values="Yield"), use_container_width=True)
        st.caption("The MOVEMENT between these three lines is the signal — a "
                  "parallel shift, a steepening and a twist are different "
                  "events with different implications.")

    # ── Spreads ─────────────────────────────────────────────────────────────
    st.markdown("#### The four segments")
    for r in data["spreads"]:
        if not r["available"]:
            st.markdown(f"○ **{r['name']}** — unavailable")
            st.caption(r["detail"])
            continue
        colour = "#dc2626" if r["inverted"] else "#16a34a"
        st.markdown(
            f"<span style='color:{colour};'>●</span> <b>{r['name']}</b> &nbsp; "
            f"<span style='font-family:monospace;font-size:1.1rem;'>"
            f"{r['value']:+.0f}bp</span>"
            + ("<span style='color:#dc2626;font-weight:700;'> INVERTED</span>"
               if r["inverted"] else ""),
            unsafe_allow_html=True)
        st.caption(f"{r['detail']} — {r['why']}")

    # ── Inversion duration on the recession spread ──────────────────────────
    dur = data.get("recession_spread_duration")
    if dur:
        (st.error if dur["inverted_now"] else st.success)(
            f"**3M–10Y (the recession spread):** {dur['detail']}")

    # ── Steepening type ─────────────────────────────────────────────────────
    st.markdown("#### How the curve moved (last 3 months)")
    for key, title in (("steepening_2s10s", "2s10s"),
                       ("steepening_10s30s", "10s30s — term premium")):
        sd = data.get(key, {})
        if not sd.get("available"):
            st.caption(f"{title}: {sd.get('detail', 'unavailable')}")
            continue
        st.markdown(f"**{title}: {sd['type']}**")
        st.caption(f"{sd['detail']} — {sd['meaning']}")

    with st.expander("Why inversions are context, not a timing tool"):
        st.markdown(
            "Inversions have preceded every modern US recession, but the lead "
            "time is long, variable, and the false-positive rate is not "
            "zero:\n\n"
            "- The **2019** inversion preceded a recession that arrived via a "
            "pandemic — the signal was 'right' for reasons unrelated to it.\n"
            "- The **2022–24** inversion was the longest on record without a "
            "recession following on the historical schedule.\n\n"
            "This sits in the same category as CAPE in this framework: "
            "structurally informative, **not** a timing tool. It is "
            "deliberately NOT wired into the regime classifier's branch "
            "logic — it informs the read, it does not name the regime.")


def selftest() -> dict:
    """Verify the steepening classifier against constructed moves."""
    failures = []

    cases = [
        # (today, prior, expected)
        ({"2Y": 3.50, "10Y": 4.50}, {"2Y": 4.50, "10Y": 4.60}, BULL_STEEPEN),
        ({"2Y": 4.20, "10Y": 4.90}, {"2Y": 4.15, "10Y": 4.40}, BEAR_STEEPEN),
        ({"2Y": 3.80, "10Y": 4.00}, {"2Y": 3.85, "10Y": 4.50}, BULL_FLATTEN),
        ({"2Y": 4.80, "10Y": 4.50}, {"2Y": 4.00, "10Y": 4.40}, BEAR_FLATTEN),
        ({"2Y": 4.50, "10Y": 4.90}, {"2Y": 4.20, "10Y": 4.60}, PARALLEL_UP),
        ({"2Y": 4.00, "10Y": 4.40}, {"2Y": 4.30, "10Y": 4.70}, PARALLEL_DOWN),
        ({"2Y": 4.00, "10Y": 4.40}, {"2Y": 4.02, "10Y": 4.42}, UNCHANGED),
    ]
    for today, prior, expected in cases:
        got = classify_steepening(today, prior)["type"]
        if got != expected:
            failures.append(f"{today} vs {prior}: got {got}, expected {expected}")

    # Inversion detection
    sp = compute_spreads({"3M": 5.40, "2Y": 4.20, "10Y": 4.70, "30Y": 5.30})
    inv = [r["name"] for r in sp if r.get("inverted")]
    if "3M-2Y" not in inv or "3M-10Y" not in inv:
        failures.append(f"inversion detection wrong: {inv}")
    if "2Y-10Y" in inv or "10Y-30Y" in inv:
        failures.append(f"false inversion flagged: {inv}")

    # Missing tenor must not fabricate
    sp2 = compute_spreads({"3M": 5.40})
    if any(r["available"] for r in sp2 if r["name"] != "3M-3M"):
        pass
    if sp2[0]["available"]:
        failures.append("spread computed with a missing leg")

    return {"ok": not failures, "failures": failures,
            "cases_run": len(cases)}


if __name__ == "__main__":
    import json
    print(json.dumps(selftest(), indent=2, default=str))
