"""
macro_quadrant.py  (v1 — September 2026)
────────────────────────────────────────
THE FOUR-QUADRANT MAP: growth × inflation. The canonical macro framework,
and specifically the intellectual foundation of the All-Weather portfolio —
Dalio's "four boxes" exist because every asset class has one environment it
is built for and one it cannot survive.

WHY THIS SITS ABOVE THE 9-REGIME CLASSIFIER, NOT INSTEAD OF IT
──────────────────────────────────────────────────────────────
They answer different questions and both are needed:

    QUADRANT  "What macro environment is this?"       universal, 4 states,
                                                       every allocator knows it
    REGIME    "What specifically is happening now?"   this framework's own
                                                       taxonomy, 9 states,
                                                       built around repression

A quadrant tells you which asset classes STRUCTURALLY belong. A regime tells
you what is happening inside that quadrant right now and how to tilt. You can
be in the Reflation quadrant via ordinary inflationary boom OR via
term_premium_repricing — same box, very different instructions.

WHY THE GROWTH AXIS IS NOT RAW GDP
──────────────────────────────────
GDP growth IS the definition of this axis. It is not usable as the INPUT:

    frequency   quarterly -- the quadrant would update 4x/year
    lag         advance estimate ~1 month after quarter-end, so Q3 (Jul-Sep)
                arrives in late October; you would allocate on data up to
                4 months stale
    revisions   advance -> second -> third -> annual, routinely 0.5-1.0pp+.
                (The Jul-2026 payroll revision moved 44k in one print; GDP
                revisions are worse.)
    direction   backward-looking by construction -- it measures what already
                happened, not what is happening

So the composite (PAYEMS, ICSA, RSAFS, UMCSENT) is a NOWCAST: a real-time
proxy for what GDP will eventually print. Same logic as the Atlanta Fed's
GDPNow and the NY Fed Staff Nowcast -- monthly and weekly indicators standing
in for a quarterly number nobody can wait for.

BUT A PROXY MUST BE CHECKED AGAINST WHAT IT PROXIES. gdp_anchor() below
fetches actual realised GDP growth and, when available, GDPNow, and reports
whether the composite AGREES with them. A nowcast that has drifted away from
the thing it is nowcasting is a nowcast that has stopped working -- and that
disagreement is more informative than either number alone.

BOTH AXES ARE ALREADY LIVE — THIS MODULE FETCHES NOTHING
  growth    <- growth_signals.assess()   PAYEMS, ICSA, RSAFS, UMCSENT composite
  inflation <- SignalSet.cpi_yoy (NSA trailing), cpi_3m_saar (SA leading),
               breakeven_10y (market-implied forward)
This is pure synthesis of data the dashboard already computes.

THE DIRECTION-NOT-LEVEL RULE
  Quadrants are about the DIRECTION OF CHANGE, not the level. 3% inflation
  FALLING from 5% is the disinflation quadrant; 3% inflation RISING from 1%
  is the reflation quadrant. Same level, opposite boxes, opposite asset
  instructions. This is the single most common way the four-quadrant
  framework gets misapplied.
"""

from __future__ import annotations

from typing import Optional

# ── The four boxes ──────────────────────────────────────────────────────────
REFLATION = "reflation"          # growth ↑  inflation ↑
GOLDILOCKS_Q = "goldilocks"      # growth ↑  inflation ↓
STAGFLATION_Q = "stagflation"    # growth ↓  inflation ↑
DEFLATION = "deflation"          # growth ↓  inflation ↓

QUADRANTS = {
    REFLATION: {
        "label": "Reflation — growth rising, inflation rising",
        "blurb": ("Nominal growth accelerating on both axes. Real assets and "
                  "cyclicals are built for this; long duration is not, because "
                  "rising inflation erodes fixed coupons."),
        "favours": ["commodities", "energy", "metals", "TIPS", "cyclical equity",
                    "value"],
        "punishes": ["long-duration Treasuries", "long-duration growth equity",
                     "cash (negative real)"],
        "aw_sleeves_up": ["PDBC", "XLE", "GLD", "SLV", "RING"],
        "aw_sleeves_down": ["TLT"],
    },
    GOLDILOCKS_Q: {
        "label": "Goldilocks — growth rising, inflation falling",
        "blurb": ("The rarest and most favourable box. Growth without price "
                  "pressure means multiple expansion AND falling discount "
                  "rates simultaneously. Equity — especially long-duration "
                  "growth — is built for exactly this."),
        "favours": ["growth equity", "tech", "small caps", "credit",
                    "long duration (falling rates)"],
        "punishes": ["commodities", "gold", "cash", "defensives"],
        "aw_sleeves_up": ["VGT", "QQQ", "SMH"],
        "aw_sleeves_down": ["GLD", "PDBC", "SGOV"],
    },
    STAGFLATION_Q: {
        "label": "Stagflation — growth falling, inflation rising",
        "blurb": ("The worst box for a conventional 60/40, because BOTH legs "
                   "fail at once: equity loses on growth, bonds lose on "
                   "inflation. Stock/bond correlation typically turns POSITIVE "
                   "here, which is the specific reason a trend/managed-futures "
                   "sleeve exists in this framework."),
        "favours": ["gold", "commodities", "energy", "managed futures / trend",
                    "floating rate", "TIPS"],
        "punishes": ["long duration", "growth equity", "credit", "60/40 itself"],
        "aw_sleeves_up": ["GLD", "KMLM", "PDBC", "XLE", "USFR"],
        "aw_sleeves_down": ["TLT", "VGT", "QQQ"],
    },
    DEFLATION: {
        "label": "Deflation / bust — growth falling, inflation falling",
        "blurb": ("Demand collapse. This is the ONE box where long duration is "
                  "the hero rather than the victim — falling growth AND falling "
                  "inflation both push yields down. A portfolio with TLT at zero "
                  "has no defence here; that trade-off must be named explicitly, "
                  "not buried."),
        "favours": ["long-duration Treasuries", "cash", "defensives",
                    "quality", "the dollar"],
        "punishes": ["commodities", "cyclicals", "credit", "small caps",
                     "energy"],
        "aw_sleeves_up": ["TLT", "SGOV", "XLV", "XLU"],
        "aw_sleeves_down": ["PDBC", "XLE", "RING", "SLV"],
    },
}

# ── How the 9 regimes map into the 4 boxes ─────────────────────────────────
# Several regimes are cross-cutting: they describe a MECHANISM that can occur
# in more than one box. Those are marked with their likely box plus a note,
# never forced into one.
REGIME_TO_QUADRANT = {
    "inflationary_repression":  (REFLATION, "Repression expresses itself as reflation: "
                                            "negative real rates WITH rising inflation."),
    "goldilocks":               (GOLDILOCKS_Q, "Direct match."),
    "stagflation":              (STAGFLATION_Q, "Direct match."),
    "liquidity_crisis":         (DEFLATION, "Credit event — demand and prices both collapse."),
    "growth_scare":             (DEFLATION, "Growth deteriorating; inflation usually follows down. "
                                            "If inflation is RISING, the box is stagflation instead."),
    "hard_repression":          (DEFLATION, "Suppressed long end with falling inflation — "
                                            "repression in a disinflationary setting."),
    "term_premium_repricing":   (REFLATION, "CROSS-CUTTING: the driver is fiscal/currency risk, "
                                            "not the growth-inflation mix. Lands in reflation when "
                                            "growth holds up, stagflation when it does not. Read the "
                                            "growth axis to decide."),
    "transition_ambiguous":     (None, "No dominant driver — the quadrant read stands on its own "
                                       "and is MORE informative than the regime here."),
    "neutral":                  (None, "Signals mixed."),
}

# Thresholds. Direction of change, not level — see the module docstring.
INFL_RISING_PP = 0.20       # 3M SAAR above trailing YoY by this much = accelerating
INFL_FALLING_PP = -0.20
GROWTH_UP_STATES = ("EXPANDING",)
GROWTH_DOWN_STATES = ("DETERIORATING", "CONTRACTING")

# GDP anchor series. Quarterly realised growth + the Atlanta Fed nowcast.
GDP_SERIES = {
    "real_gdp_qoq_saar": "A191RL1Q225SBEA",   # real GDP, % change, SAAR, quarterly
    "gdpnow": "GDPNOW",                        # Atlanta Fed nowcast, current quarter
}
GDP_WEAK_PCT = 1.0        # below trend-ish
GDP_CONTRACTING_PCT = 0.0


def gdp_anchor(fetch_fred=None, api_key: str = "", start: str = "2015-01-01",
               composite_direction: Optional[str] = None) -> dict:
    """
    Fetch REALISED GDP growth (and GDPNow when available) and check whether
    the composite nowcast agrees with it.

    This does not replace the composite as the axis input -- see the module
    docstring for why quarterly, lagged, heavily-revised data cannot drive a
    live allocation read. It exists because a proxy nobody checks is a proxy
    that can silently stop tracking.

    Returns realised GDP with its own as-of date, the nowcast, an implied
    direction, and an explicit agreement verdict. Never raises; a failed
    fetch is named, not defaulted.
    """
    out = {"realised": None, "realised_asof": None, "gdpnow": None,
           "gdp_direction": None, "agrees": None, "note": None, "missing": []}
    if fetch_fred is None:
        out["missing"].append("no fetch_fred supplied")
        return out

    def _last(series_id):
        try:
            s_ = fetch_fred(series_id, api_key, start)
            d = s_.dropna() if s_ is not None else None
            return (float(d.iloc[-1]), d.index[-1]) if d is not None and len(d) else (None, None)
        except Exception:
            return (None, None)

    val, asof = _last(GDP_SERIES["real_gdp_qoq_saar"])
    if val is None:
        out["missing"].append(GDP_SERIES["real_gdp_qoq_saar"])
    else:
        out["realised"] = round(val, 2)
        out["realised_asof"] = asof.strftime("%b %Y") if hasattr(asof, "strftime") else str(asof)

    nowc, nowc_asof = _last(GDP_SERIES["gdpnow"])
    if nowc is not None:
        out["gdpnow"] = round(nowc, 2)
        out["gdpnow_asof"] = (nowc_asof.strftime("%d %b %Y")
                              if hasattr(nowc_asof, "strftime") else str(nowc_asof))

    # Prefer the NOWCAST for direction when present -- it is the same kind of
    # real-time read the composite is, so it is the fairer comparison. Fall
    # back to realised only when the nowcast is unavailable.
    ref = out["gdpnow"] if out["gdpnow"] is not None else out["realised"]
    ref_src = "GDPNow" if out["gdpnow"] is not None else "realised GDP"
    if ref is not None:
        if ref <= GDP_CONTRACTING_PCT:
            out["gdp_direction"] = "falling"
        elif ref < GDP_WEAK_PCT:
            out["gdp_direction"] = "flat"
        else:
            out["gdp_direction"] = "rising"
        out["gdp_direction_source"] = ref_src

    if composite_direction and out["gdp_direction"]:
        out["agrees"] = (composite_direction == out["gdp_direction"])
        if out["agrees"]:
            out["note"] = (f"Composite nowcast ({composite_direction}) agrees with "
                           f"{ref_src} {ref:+.2f}% ({out['gdp_direction']}). The "
                           f"proxy is tracking what it proxies.")
        else:
            out["note"] = (f"⚠ DISAGREEMENT: the composite says growth is "
                           f"{composite_direction}, but {ref_src} is {ref:+.2f}% "
                           f"({out['gdp_direction']}). One of two things is true — "
                           f"the composite is picking up a turn GDP has not "
                           f"registered yet (its whole purpose, and the more likely "
                           f"case near an inflection), or the composite has drifted "
                           f"and stopped tracking. Check which before trusting the "
                           f"quadrant.")
    return out


def classify(growth: Optional[dict] = None,
             cpi_yoy: Optional[float] = None,
             cpi_3m_saar: Optional[float] = None,
             breakeven_10y: Optional[float] = None,
             regime_key: Optional[str] = None) -> dict:
    """
    Place the current environment in one of four boxes.

    growth      output of growth_signals.assess() — uses its `state`
    cpi_yoy     NSA trailing 12-month (the LEVEL / lagging read)
    cpi_3m_saar SA 3-month annualised (the DIRECTION / leading read)
    breakeven_10y  market-implied forward inflation — used as a tiebreak only

    Returns the quadrant, both axis reads with their evidence, a confidence
    level, and — when a regime key is supplied — how that regime sits inside
    the box. Missing inputs are NAMED and lower confidence; they never get
    silently defaulted to a direction.
    """
    out = {"quadrant": None, "label": None, "growth_axis": None,
           "inflation_axis": None, "confidence": "LOW", "missing": [],
           "evidence": [], "regime_fit": None}

    # ── Growth axis ─────────────────────────────────────────────────────────
    g_state = (growth or {}).get("state")
    g_confirmed = (growth or {}).get("confirmed")
    if g_state in GROWTH_UP_STATES:
        g_dir = "rising"
    elif g_state in GROWTH_DOWN_STATES:
        g_dir = "falling"
    elif g_state == "NEUTRAL":
        g_dir = "flat"
    else:
        g_dir = None
        out["missing"].append("growth composite")
    out["growth_axis"] = {"direction": g_dir, "state": g_state,
                          "confirmed": g_confirmed, "score": (growth or {}).get("score"),
                          "detail": (growth or {}).get("detail")}
    if g_state:
        out["evidence"].append(
            f"Growth composite {g_state}"
            + (" (confirmed)" if g_confirmed else " (unconfirmed)")
            + (f" — {(growth or {}).get('detail')}" if (growth or {}).get("detail") else ""))

    # ── Inflation axis — DIRECTION, not level ───────────────────────────────
    i_dir = None
    if cpi_3m_saar is not None and cpi_yoy is not None:
        delta = cpi_3m_saar - cpi_yoy
        if delta >= INFL_RISING_PP:
            i_dir = "rising"
        elif delta <= INFL_FALLING_PP:
            i_dir = "falling"
        else:
            i_dir = "flat"
        out["evidence"].append(
            f"Inflation {i_dir}: 3M SAAR {cpi_3m_saar:+.2f}% vs trailing YoY "
            f"{cpi_yoy:+.2f}% (gap {delta:+.2f}pp). Direction of change, not "
            f"level — 3% falling from 5% is disinflation; 3% rising from 1% "
            f"is reflation.")
    else:
        out["missing"].append("cpi_3m_saar and/or cpi_yoy")
        # Breakeven as a weak fallback — market-implied forward vs trailing
        if breakeven_10y is not None and cpi_yoy is not None:
            i_dir = "falling" if breakeven_10y < cpi_yoy - 0.5 else \
                    "rising" if breakeven_10y > cpi_yoy + 0.5 else "flat"
            out["evidence"].append(
                f"Inflation direction inferred from 10y breakeven "
                f"{breakeven_10y:.2f}% vs trailing CPI {cpi_yoy:.2f}% — "
                f"WEAKER evidence than the 3M SAAR comparison.")
    _delta = ((cpi_3m_saar - cpi_yoy) if (cpi_3m_saar is not None and cpi_yoy is not None)
              else None)
    out["inflation_axis"] = {"direction": i_dir, "cpi_yoy": cpi_yoy,
                             "cpi_3m_saar": cpi_3m_saar, "delta_pp": _delta,
                             "breakeven_10y": breakeven_10y}

    # ── Place in a box ──────────────────────────────────────────────────────
    # v2 FIX: "flat" must NEVER be bundled with a directional neighbour on
    # EITHER axis. It was previously grouped with "rising" for growth,
    # which let the label say e.g. Goldilocks while the dot -- drawn from
    # the raw continuous score, which gets no such bundling -- could still
    # plot in the OPPOSITE half whenever score was flat-but-slightly-
    # negative (NEUTRAL spans -1/0/+1). Caught directly: score=-1 (NEUTRAL,
    # so "flat") labelled Goldilocks while visually plotting below the
    # center line, in Deflation's half. A genuinely flat reading is
    # ambiguous about which half it belongs to; forcing it into the
    # "nicer" box overclaims precision the data doesn't have, and now
    # disagrees with where the dot is actually drawn. Symmetric ambiguity
    # on both axes keeps the label and the dot's position always
    # consistent -- if either is flat, the box is genuinely undetermined.
    if g_dir == "rising" and i_dir == "rising":
        q = REFLATION
    elif g_dir == "rising" and i_dir == "falling":
        q = GOLDILOCKS_Q
    elif g_dir == "falling" and i_dir == "rising":
        q = STAGFLATION_Q
    elif g_dir == "falling" and i_dir == "falling":
        q = DEFLATION
    elif g_dir == "flat" or i_dir == "flat":
        q = None
        out["evidence"].append(
            f"{'Growth' if g_dir=='flat' else 'Inflation'} is flat — "
            f"genuinely ambiguous which box this belongs to, not forced "
            f"into either neighbour. The dot's position reflects this "
            f"directly rather than the label overclaiming a side.")
    else:
        q = None

    if q:
        out["quadrant"] = q
        out["label"] = QUADRANTS[q]["label"]
        out.update({k: QUADRANTS[q][k] for k in
                    ("blurb", "favours", "punishes", "aw_sleeves_up", "aw_sleeves_down")})

    # ── Confidence ──────────────────────────────────────────────────────────
    if q and not out["missing"] and g_confirmed and g_dir != "flat" and i_dir != "flat":
        out["confidence"] = "HIGH"
    elif q and not out["missing"]:
        out["confidence"] = "MODERATE"
    elif q:
        out["confidence"] = "LOW"
    if out["missing"]:
        out["evidence"].append(
            f"Degraded inputs ({', '.join(out['missing'])}) — this lowers "
            f"confidence in everything downstream, including the regime read.")

    # ── How the 9-regime classifier sits inside the box ─────────────────────
    if regime_key:
        mapped, note = REGIME_TO_QUADRANT.get(regime_key, (None, "Unmapped regime."))
        agrees = (mapped == q) if (mapped and q) else None
        out["regime_fit"] = {
            "regime": regime_key, "expected_quadrant": mapped, "agrees": agrees,
            "note": note,
            "conflict": (None if agrees is not False else
                         f"The regime classifier says `{regime_key}` (normally "
                         f"{mapped}) while the growth×inflation axes place this in "
                         f"{q}. A disagreement between the universal map and the "
                         f"framework's own taxonomy is the single highest-value "
                         f"thing to investigate before acting — one of the two "
                         f"inputs is stale, or this is a genuine transition.")}
    return out


def render(st, q: dict, show_detail_link: bool = True, gdp: Optional[dict] = None):
    """The headline panel. Quadrant first, regime detail underneath."""
    colour = {REFLATION: "#d4913a", GOLDILOCKS_Q: "#5a9e47",
              STAGFLATION_Q: "#e05252", DEFLATION: "#4a8fd4"}.get(q.get("quadrant"), "#6b7280")
    conf_c = {"HIGH": "#5a9e47", "MODERATE": "#d4913a", "LOW": "#e05252"}.get(q["confidence"], "#6b7280")

    st.markdown(
        f'<div style="background:#13161b;border:1px solid #242830;'
        f'border-left:5px solid {colour};border-radius:10px;padding:1rem 1.25rem;margin:.5rem 0;">'
        f'<div style="font-size:.72rem;color:#6b7280;letter-spacing:.08em;">MACRO QUADRANT</div>'
        f'<div style="font-size:1.25rem;font-weight:700;color:{colour};margin:.2rem 0;">'
        f'{q.get("label") or "Between boxes — axes do not agree on a quadrant"}</div>'
        f'<div style="font-size:.78rem;color:{conf_c};">Confidence: {q["confidence"]}</div>'
        f'</div>', unsafe_allow_html=True)

    if q.get("blurb"):
        st.caption(q["blurb"])

    try:
        import macro_quadrant_chart as _chart
        _svg = _chart.build(
            quadrant=q.get("quadrant"),
            growth_score=q["growth_axis"].get("score"),
            inflation_delta_pp=q["inflation_axis"].get("delta_pp"),
            confidence=q["confidence"],
            gdp_direction=(gdp or {}).get("gdp_direction"))
        st.markdown(_svg, unsafe_allow_html=True)
        st.caption("Solid dot: current reading (size/opacity = confidence). "
                   "Dashed ring: where GDPNow/realised GDP alone would place "
                   "the growth axis, at the same inflation reading — a gap "
                   "between the two is the composite and its anchor "
                   "disagreeing, visibly.")
    except Exception as _e:
        st.caption(f"Chart unavailable: {_e}")

    c1, c2 = st.columns(2)
    ga, ia = q["growth_axis"], q["inflation_axis"]
    with c1:
        st.markdown(f"**Growth axis:** {ga['direction'] or 'unknown'}")
        st.caption(f"{ga['state'] or 'no composite'}"
                   + (" · confirmed" if ga.get("confirmed") else " · unconfirmed"))
    with c2:
        st.markdown(f"**Inflation axis:** {ia['direction'] or 'unknown'}")
        if ia.get("cpi_3m_saar") is not None and ia.get("cpi_yoy") is not None:
            st.caption(f"3M SAAR {ia['cpi_3m_saar']:+.2f}% vs YoY {ia['cpi_yoy']:+.2f}%")

    # ── GDP anchor: is the nowcast proxy still tracking what it proxies? ────
    if gdp and (gdp.get("realised") is not None or gdp.get("gdpnow") is not None):
        g1, g2 = st.columns(2)
        if gdp.get("realised") is not None:
            g1.metric("Realised GDP (QoQ SAAR)", f"{gdp['realised']:+.2f}%",
                      help=f"Actual reported growth as of {gdp.get('realised_asof','?')}. "
                           f"Quarterly and revised — the ANCHOR, not the axis input.")
        if gdp.get("gdpnow") is not None:
            g2.metric("GDPNow (Atlanta Fed)", f"{gdp['gdpnow']:+.2f}%",
                      help=f"Current-quarter nowcast as of {gdp.get('gdpnow_asof','?')} — "
                           f"updated through the quarter, the fair comparison for "
                           f"this dashboard's own composite nowcast.")
        if gdp.get("note"):
            (st.warning if gdp.get("agrees") is False else st.caption)(gdp["note"])
    elif gdp and gdp.get("missing"):
        st.caption(f"GDP anchor unavailable ({', '.join(gdp['missing'])}) — the "
                   f"composite nowcast is unchecked against realised growth this pass.")

    if q.get("favours"):
        st.markdown(f"**Structurally favours:** {', '.join(q['favours'])}")
        st.markdown(f"**Structurally punishes:** {', '.join(q['punishes'])}")
        st.caption(f"All-Weather sleeves this box argues UP: {', '.join(q['aw_sleeves_up'])} · "
                   f"DOWN: {', '.join(q['aw_sleeves_down'])}. This is the STRUCTURAL read — "
                   f"the regime classifier below sets the actual tilt.")

    rf = q.get("regime_fit")
    if rf:
        if rf.get("conflict"):
            st.error(f"⚠ **Quadrant/regime disagreement** — {rf['conflict']}")
        else:
            st.success(f"✅ Regime `{rf['regime']}` is consistent with this quadrant. {rf['note']}")

    with st.expander("Evidence and how this is built"):
        for e in q["evidence"]:
            st.caption(f"· {e}")
        st.caption(
            "**Quadrants are about the DIRECTION OF CHANGE, not the level.** 3% "
            "inflation FALLING from 5% is the disinflation box; 3% RISING from 1% "
            "is the reflation box. Same level, opposite boxes, opposite asset "
            "instructions — this is the most common way the four-quadrant "
            "framework gets misapplied.\\n\\n"
            "**Why both layers exist:** the quadrant is the universal map every "
            "allocator knows and answers *what environment is this*. The 9-regime "
            "classifier is this framework's own taxonomy and answers *what "
            "specifically is happening right now*. You can be in Reflation via an "
            "ordinary inflationary boom OR via term_premium_repricing — same box, "
            "very different instructions.\\n\\n"
            "**Why growth is not raw GDP.** GDP growth IS the definition of "
            "this axis, but it cannot be the input: it is quarterly, the advance "
            "estimate lands ~1 month after quarter-end (so Q3 arrives in late "
            "October), and it is revised repeatedly by 0.5-1.0pp+. You would be "
            "allocating on data up to four months stale and subject to material "
            "revision. The composite (PAYEMS, ICSA, RSAFS, UMCSENT) is a "
            "NOWCAST — a real-time proxy for what GDP will print, the same logic "
            "behind GDPNow and the NY Fed Staff Nowcast. Realised GDP and "
            "GDPNow are shown above as the ANCHOR: if the composite stops "
            "agreeing with them, either it is catching a turn GDP has not "
            "registered yet (its purpose) or it has drifted and stopped "
            "working — and knowing which matters more than either number."
        )


def selftest() -> dict:
    f = []
    G = lambda s, c=True, score=None: {"state": s, "confirmed": c,
                                       "detail": "test", "score": score}

    # Four corners
    cases = [
        (G("EXPANDING"), 2.0, 3.0, REFLATION),        # growth up, infl accelerating
        (G("EXPANDING"), 3.0, 2.0, GOLDILOCKS_Q),     # growth up, infl decelerating
        (G("CONTRACTING"), 2.0, 3.0, STAGFLATION_Q),  # growth down, infl accelerating
        (G("CONTRACTING"), 3.0, 2.0, DEFLATION),      # growth down, infl decelerating
    ]
    for g, yoy, saar, expect in cases:
        r = classify(growth=g, cpi_yoy=yoy, cpi_3m_saar=saar)
        if r["quadrant"] != expect:
            f.append(f"{g['state']} + yoy{yoy}/saar{saar} -> {r['quadrant']}, expected {expect}")

    # Direction not level: SAME 3% level, opposite boxes
    hot = classify(growth=G("EXPANDING"), cpi_yoy=1.0, cpi_3m_saar=3.0)
    cool = classify(growth=G("EXPANDING"), cpi_yoy=5.0, cpi_3m_saar=3.0)
    if hot["quadrant"] != REFLATION or cool["quadrant"] != GOLDILOCKS_Q:
        f.append("3% SAAR must be reflation when rising from 1% and goldilocks when falling from 5%")

    # Missing growth must NOT silently default
    m = classify(growth=None, cpi_yoy=3.0, cpi_3m_saar=2.0)
    if "growth composite" not in m["missing"] or m["confidence"] != "LOW":
        f.append("missing growth must be named and lower confidence")

    # Conflict detection
    c = classify(growth=G("CONTRACTING"), cpi_yoy=3.0, cpi_3m_saar=2.0,
                 regime_key="goldilocks")
    if not (c["regime_fit"] and c["regime_fit"]["conflict"]):
        f.append("goldilocks regime in the deflation box must flag a conflict")

    # Agreement
    a = classify(growth=G("EXPANDING"), cpi_yoy=3.0, cpi_3m_saar=2.0,
                 regime_key="goldilocks")
    if a["regime_fit"]["agrees"] is not True:
        f.append("goldilocks regime in the goldilocks box must agree")

    # GDP anchor agreement logic
    ag = gdp_anchor(fetch_fred=lambda sid, k, s: None, composite_direction="rising")
    if ag["agrees"] is not None:
        f.append("no fetch -> agrees must stay None, not a guess")

    class _FakeSeries:
        def __init__(self, v): self.v = v
        def dropna(self): return self
        def __len__(self): return 1
        @property
        def iloc(self): return {-1: self.v}
        @property
        def index(self): return {-1: "2026-06-01"}

    def _mk(vals):
        def _f(sid, key, start):
            v = vals.get(sid)
            return _FakeSeries(v) if v is not None else None
        return _f

    # composite says rising, GDPNow +2.5 -> agree
    a1 = gdp_anchor(_mk({"GDPNOW": 2.5, "A191RL1Q225SBEA": 2.1}), composite_direction="rising")
    if a1["agrees"] is not True or a1["gdp_direction"] != "rising":
        f.append(f"expected agreement, got {a1['agrees']} dir={a1['gdp_direction']}")
    # composite says rising, GDPNow -0.5 -> DISAGREE and say so
    a2 = gdp_anchor(_mk({"GDPNOW": -0.5, "A191RL1Q225SBEA": 2.1}), composite_direction="rising")
    if a2["agrees"] is not False or "DISAGREEMENT" not in (a2["note"] or ""):
        f.append("expected a flagged disagreement")
    # nowcast preferred over realised for direction
    if a2.get("gdp_direction_source") != "GDPNow":
        f.append("nowcast must be preferred over realised for the direction read")

    # v2 FIX regression: "flat" must NEVER be bundled with a directional
    # neighbour, on EITHER axis -- this is the exact bug a live screenshot
    # caught (score=-1, NEUTRAL/"flat", labelled Goldilocks while the dot
    # plotted in Deflation's half because the raw score was negative).
    flat_growth_falling_infl = classify(growth=G("NEUTRAL", True, score=-1),
                                        cpi_yoy=3.40, cpi_3m_saar=0.18)
    if flat_growth_falling_infl["quadrant"] is not None:
        f.append(f"flat growth (even clearly-directional inflation) must be "
                f"ambiguous, got {flat_growth_falling_infl['quadrant']}")
    # And the reverse: clear growth, flat inflation -- also ambiguous
    flat_infl_rising_growth = classify(growth=G("EXPANDING", True),
                                       cpi_yoy=3.00, cpi_3m_saar=3.05)
    if flat_infl_rising_growth["quadrant"] is not None:
        f.append(f"flat inflation (even clearly-directional growth) must be "
                f"ambiguous, got {flat_infl_rising_growth['quadrant']}")
    # The label and the dot's half must NEVER disagree: whenever a quadrant
    # IS assigned, the sign of the score must match the box's own vertical
    # half (top boxes = rising = score>0; bottom = falling = score<0).
    for lbl, g_state, score in (("rising/rising", "EXPANDING", 3),
                                ("falling/falling", "CONTRACTING", -3)):
        r = classify(growth=G(g_state, True, score=score),
                     cpi_yoy=(1.0 if score > 0 else 3.0),
                     cpi_3m_saar=(3.0 if score > 0 else 1.0))
        top_boxes = {REFLATION, GOLDILOCKS_Q}
        if r["quadrant"] and ((score > 0) != (r["quadrant"] in top_boxes)):
            f.append(f"label/dot half mismatch for {lbl}: score={score} "
                    f"quadrant={r['quadrant']}")

    # Confidence ladder
    hi = classify(growth=G("EXPANDING", True), cpi_yoy=2.0, cpi_3m_saar=3.0)
    lo = classify(growth=G("EXPANDING", False), cpi_yoy=2.0, cpi_3m_saar=3.0)
    if hi["confidence"] != "HIGH" or lo["confidence"] != "MODERATE":
        f.append(f"confidence ladder wrong: confirmed={hi['confidence']} unconfirmed={lo['confidence']}")

    return {"ok": not f, "failures": f}


if __name__ == "__main__":
    import json
    print(json.dumps(selftest(), indent=2))
