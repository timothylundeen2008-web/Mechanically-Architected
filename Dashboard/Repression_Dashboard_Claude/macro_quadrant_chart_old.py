"""
macro_quadrant_chart.py  (v1 — September 2026)
────────────────────────────────────────────────
The visual for macro_quadrant.py: four shaded boxes, crosshair axes, and a
dot plotted at the actual current reading. Kept in its own file specifically
so an SVG string full of markup characters never has to survive an inline
edit inside macro_quadrant.py's own body again.

AXES
  X = inflation delta, cpi_3m_saar - cpi_yoy, in percentage points, clamped
      to +-CHART_X_RANGE. Positive = accelerating (right), negative =
      decelerating (left).
  Y = the growth composite's own raw score (4 series voting -1/0/+1 each,
      so the natural range is -4 to +4). Positive = rising (top).

A SECOND, DASHED MARKER shows where GDPNow / realised GDP alone would place
the growth axis, at the same X position — so a reader can see, at a glance,
whether the composite nowcast agrees with its own anchor, not just read it
in the text note underneath.

MISSING DATA NEVER PLOTS A GUESSED DOT. If either axis lacks a value, the
chart says so directly instead of defaulting to the center.
"""

REFLATION, GOLDILOCKS_Q, STAGFLATION_Q, DEFLATION = (
    "reflation", "goldilocks", "stagflation", "deflation")

QCOLOR = {REFLATION: "#d4913a", GOLDILOCKS_Q: "#5a9e47",
         STAGFLATION_Q: "#e05252", DEFLATION: "#4a8fd4"}

CHART_X_RANGE = 4.0   # pp on the inflation delta -- a swing this large is already extreme
CHART_Y_RANGE = 4.0   # the growth composite's own min/max (4 series, +-1 each)


def _norm(v, span):
    """Clamp v to +-span and normalise to [-1, 1]. None passes through."""
    if v is None:
        return None
    return max(-1.0, min(1.0, v / span))


def build(quadrant, growth_score, inflation_delta_pp, confidence,
         gdp_direction=None, size=440):
    """
    quadrant            one of REFLATION/GOLDILOCKS_Q/STAGFLATION_Q/DEFLATION,
                        or None if the axes disagree on a box
    growth_score        the raw composite score (-4..+4), or None
    inflation_delta_pp  cpi_3m_saar - cpi_yoy, or None
    confidence          "HIGH" / "MODERATE" / "LOW"
    gdp_direction       "rising" / "flat" / "falling" / None -- the GDP
                        anchor's own read, plotted as a secondary marker
    """
    pad = 46
    cx = size // 2
    cy = size // 2
    plot = size - 2 * pad
    half = plot / 2.0

    x = _norm(inflation_delta_pp, CHART_X_RANGE)
    y = _norm(growth_score, CHART_Y_RANGE)

    def px(nx):
        return cx + nx * half

    def py(ny):
        return cy - ny * half  # SVG y grows downward

    conf_op = {"HIGH": 1.0, "MODERATE": 0.85, "LOW": 0.55}.get(confidence, 0.5)
    qcol = QCOLOR.get(quadrant, "#6b7280")

    parts = []
    parts.append(f'<svg viewBox="0 0 {size} {size}" width="100%" '
                 f'style="max-width:{size}px;">')
    parts.append(f'<rect x="0" y="0" width="{size}" height="{size}" '
                 f'fill="#0d0f12" rx="10"/>')

    # Four quadrant boxes
    parts.append(f'<rect x="{pad}" y="{pad}" width="{half}" height="{half}" '
                 f'fill="{QCOLOR[GOLDILOCKS_Q]}" opacity="0.10"/>')
    parts.append(f'<rect x="{cx}" y="{pad}" width="{half}" height="{half}" '
                 f'fill="{QCOLOR[REFLATION]}" opacity="0.10"/>')
    parts.append(f'<rect x="{pad}" y="{cy}" width="{half}" height="{half}" '
                 f'fill="{QCOLOR[DEFLATION]}" opacity="0.10"/>')
    parts.append(f'<rect x="{cx}" y="{cy}" width="{half}" height="{half}" '
                 f'fill="{QCOLOR[STAGFLATION_Q]}" opacity="0.10"/>')

    # Crosshair axes
    parts.append(f'<line x1="{pad}" y1="{cy}" x2="{size-pad}" y2="{cy}" '
                 f'stroke="#3a4048" stroke-width="1.5"/>')
    parts.append(f'<line x1="{cx}" y1="{pad}" x2="{cx}" y2="{size-pad}" '
                 f'stroke="#3a4048" stroke-width="1.5"/>')

    # Axis labels -- HTML numeric entities, never a literal unicode arrow
    parts.append(f'<text x="{size-pad}" y="{cy-8}" fill="#6b7280" '
                 f'font-size="10" text-anchor="end">INFLATION RISING &#8594;</text>')
    parts.append(f'<text x="{pad}" y="{cy-8}" fill="#6b7280" font-size="10" '
                 f'text-anchor="start">&#8592; FALLING</text>')
    parts.append(f'<text x="{cx+6}" y="{pad-8}" fill="#6b7280" '
                 f'font-size="10">&#8593; GROWTH RISING</text>')
    parts.append(f'<text x="{cx+6}" y="{size-pad+16}" fill="#6b7280" '
                 f'font-size="10">&#8595; FALLING</text>')

    # Quadrant name labels
    parts.append(f'<text x="{pad+8}" y="{pad+22}" fill="{QCOLOR[GOLDILOCKS_Q]}" '
                 f'font-size="12" font-weight="700">GOLDILOCKS</text>')
    parts.append(f'<text x="{cx+8}" y="{pad+22}" fill="{QCOLOR[REFLATION]}" '
                 f'font-size="12" font-weight="700">REFLATION</text>')
    parts.append(f'<text x="{pad+8}" y="{cy+half-10}" fill="{QCOLOR[DEFLATION]}" '
                 f'font-size="12" font-weight="700">DEFLATION</text>')
    parts.append(f'<text x="{cx+8}" y="{cy+half-10}" fill="{QCOLOR[STAGFLATION_Q]}" '
                 f'font-size="12" font-weight="700">STAGFLATION</text>')

    # Main dot -- or, if data is missing, say so ON the chart
    if x is not None and y is not None:
        dx, dy = px(x), py(y)
        parts.append(f'<circle cx="{dx:.1f}" cy="{dy:.1f}" r="13" fill="{qcol}" '
                     f'opacity="{conf_op*0.25:.2f}"/>')
        parts.append(f'<circle cx="{dx:.1f}" cy="{dy:.1f}" r="7" fill="{qcol}" '
                     f'opacity="{conf_op:.2f}" stroke="#0d0f12" stroke-width="2"/>')
    else:
        parts.append(f'<text x="{cx}" y="{cy}" fill="#6b7280" font-size="11" '
                     f'text-anchor="middle">missing data &#8212; no position plotted</text>')

    # GDP anchor -- dashed ring at the same X, using the anchor's OWN
    # implied Y. Shows composite-vs-GDP agreement visually.
    if gdp_direction and x is not None:
        gdy = {"rising": 1.0, "flat": 0.0, "falling": -1.0}.get(gdp_direction)
        if gdy is not None:
            gx, gy = px(x), py(gdy)
            parts.append(f'<circle cx="{gx:.1f}" cy="{gy:.1f}" r="5" fill="none" '
                         f'stroke="#e8e8e8" stroke-width="1.5" '
                         f'stroke-dasharray="2,2" opacity="0.7"/>')
            parts.append(f'<text x="{gx+9:.1f}" y="{gy+4:.1f}" fill="#9aa3b2" '
                         f'font-size="9">GDP</text>')

    parts.append('</svg>')
    return "".join(parts)


def selftest():
    f = []
    # A normal case: both axes present, must contain a solid dot
    svg = build(GOLDILOCKS_Q, growth_score=1, inflation_delta_pp=-3.22,
               confidence="MODERATE", gdp_direction="rising")
    if "missing data" in svg:
        f.append("valid inputs should not render the missing-data message")
    if "GDP" not in svg:
        f.append("gdp_direction supplied but no GDP marker rendered")
    if svg.count("<circle") < 3:
        f.append(f"expected >=3 circles (glow+dot+GDP ring), got {svg.count('<circle')}")

    # Missing growth score -> no dot, explicit message, no crash
    svg2 = build(None, growth_score=None, inflation_delta_pp=-3.22, confidence="LOW")
    if "missing data" not in svg2:
        f.append("missing growth score should render the missing-data message")
    if svg2.count("<circle") != 0:
        f.append("no dot should be plotted when growth_score is None")

    # Clamping: an extreme value must not blow past the plot bounds
    svg3 = build(REFLATION, growth_score=999, inflation_delta_pp=999, confidence="HIGH")
    import re
    xs = [float(m) for m in re.findall(r'cx="([\d.]+)"', svg3)]
    ys = [float(m) for m in re.findall(r'cy="([\d.]+)"', svg3)]
    if any(v < 0 or v > 440 for v in xs + ys):
        f.append(f"extreme input produced an out-of-bounds coordinate: x={xs} y={ys}")

    return {"ok": not f, "failures": f}


if __name__ == "__main__":
    import json
    print(json.dumps(selftest(), indent=2))
