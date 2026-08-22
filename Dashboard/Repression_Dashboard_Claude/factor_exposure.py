"""
factor_exposure.py  (v1 — August 2026)
──────────────────────────────────────
What is this portfolio ACTUALLY exposed to?

WHY
───
This was flagged as a gap in the framework's own gap analysis months ago
and has remained open since. The question it answers is not academic:

    A portfolio can hold fifteen sleeves and be ONE factor.

Fifteen tickers with an average pairwise correlation of 0.8 is roughly 1.7
independent bets wearing a costume. The book LOOKS diversified in a pie
chart and behaves like a single position in a drawdown. You cannot manage
what you do not measure, and right now this framework does not measure it.

METHOD
──────
Regress sleeve returns against factor proxies. Deliberately using liquid
ETF proxies rather than academic factor series (Fama-French, AQR), because:
  * they are fetchable with the same infrastructure already in place
  * they are what you could actually TRADE to adjust an exposure
  * academic series lag by weeks and are not point-in-time

    MARKET      SPY        broad beta
    GROWTH      IWF/VUG    growth tilt
    VALUE       IWD/VTV    value tilt
    SIZE        IWM        small-cap
    MOMENTUM    MTUM       cross-sectional momentum
    QUALITY     QUAL       profitability/stability
    DURATION    IEF        rate sensitivity
    INFLATION   PDBC/DBC   commodity/inflation beta
    DOLLAR      UUP        currency

Multivariate OLS, so exposures are conditional on each other — a univariate
regression against GROWTH alone would double-count what MARKET already
explains.

THE HONEST LIMITATION
─────────────────────
Factor proxies are correlated with each other (GROWTH and MOMENTUM
especially), which inflates standard errors and makes individual
coefficients unstable. R-squared is reliable; individual betas should be
read as directional, not precise. This is a diagnostic for "am I secretly
one bet", not a risk model. It is not Barra, and it does not pretend to be.
"""

from __future__ import annotations

from typing import Callable, Optional

import numpy as np
import pandas as pd

FACTOR_PROXIES = {
    "MARKET": "SPY",
    "GROWTH": "VUG",
    "VALUE": "VTV",
    "SIZE": "IWM",
    "MOMENTUM": "MTUM",
    "QUALITY": "QUAL",
    "DURATION": "IEF",
    "INFLATION": "PDBC",
    "DOLLAR": "UUP",
}

MIN_OBS = 120          # ~6 months of daily data
LOOKBACK_DEFAULT = 252


def _returns(prices: pd.Series) -> pd.Series:
    return pd.Series(prices).astype(float).dropna().pct_change().dropna()


def build_factor_matrix(fetch_prices: Callable,
                        lookback: int = LOOKBACK_DEFAULT) -> dict:
    """Fetch and align all factor proxy returns."""
    out = {"returns": None, "missing": [], "detail": ""}
    cols = {}
    for name, tk in FACTOR_PROXIES.items():
        try:
            px = fetch_prices(tk, "2y")
            px = pd.Series(px.squeeze() if hasattr(px, "squeeze") else px)
            r = _returns(px)
            if len(r) < MIN_OBS:
                out["missing"].append(f"{name} ({tk}: {len(r)} obs)")
                continue
            cols[name] = r
        except Exception as e:
            out["missing"].append(f"{name} ({tk}: {type(e).__name__})")

    if not cols:
        out["detail"] = "No factor proxies available — decomposition is dark."
        return out

    df = pd.DataFrame(cols).dropna().tail(lookback)
    out["returns"] = df
    out["detail"] = (f"{len(df)} overlapping observations across "
                     f"{len(df.columns)} factors.")
    if out["missing"]:
        out["detail"] += f" Missing: {', '.join(out['missing'])}."
    return out


def regress(portfolio_returns: pd.Series, factors: pd.DataFrame) -> dict:
    """
    Multivariate OLS of portfolio returns on factor returns.

    Uses numpy lstsq rather than a stats package to avoid adding a
    dependency — this is a diagnostic, not an inference engine, so
    coefficients and R-squared are sufficient and p-values would imply more
    precision than correlated proxies can support.
    """
    out = {"available": False, "betas": {}, "r_squared": None,
           "alpha_annual": None, "detail": ""}
    try:
        df = pd.concat([portfolio_returns.rename("port"), factors],
                       axis=1, join="inner").dropna()
        if len(df) < MIN_OBS:
            out["detail"] = (f"Only {len(df)} overlapping observations; "
                            f"need {MIN_OBS}.")
            return out

        y = df["port"].values
        X = df.drop(columns=["port"]).values
        X = np.column_stack([np.ones(len(X)), X])       # intercept

        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        pred = X @ coef
        ss_res = float(((y - pred) ** 2).sum())
        ss_tot = float(((y - y.mean()) ** 2).sum())
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else None

        names = list(df.drop(columns=["port"]).columns)
        out.update(
            available=True,
            betas={n: round(float(b), 3) for n, b in zip(names, coef[1:])},
            r_squared=round(r2, 3) if r2 is not None else None,
            alpha_annual=round(float(coef[0]) * 252 * 100, 2),
        )
        out["detail"] = (f"R² {r2:.2f} — {r2*100:.0f}% of this portfolio's "
                        f"variance is explained by these factors. "
                        + ("The remainder is idiosyncratic."
                           if r2 < 0.9 else
                           "Almost nothing is idiosyncratic: this book IS "
                           "its factor exposures."))
        return out
    except Exception as e:
        out["detail"] = f"Regression failed: {e}"
        return out


def effective_bets(corr_matrix: pd.DataFrame) -> Optional[float]:
    """
    How many INDEPENDENT bets N correlated sleeves actually represent.

        N_eff = N / (1 + (N-1) * avg_rho)

    The single most clarifying number in this module. Fifteen sleeves at
    rho=0.8 is 1.7 effective bets.
    """
    try:
        a = corr_matrix.to_numpy(dtype=float)
        n = a.shape[0]
        if n < 2:
            return None
        mask = ~np.eye(n, dtype=bool)
        vals = a[mask]
        vals = vals[~np.isnan(vals)]
        rho = float(vals.mean())
        denom = 1 + (n - 1) * rho
        return round(n / denom, 2) if denom > 0 else float(n)
    except Exception:
        return None


def analyse(fetch_prices: Callable, weights: dict,
            lookback: int = LOOKBACK_DEFAULT) -> dict:
    """Full decomposition: sleeve correlations, effective bets, factor betas."""
    out = {"available": False, "detail": ""}

    sleeve_returns = {}
    missing = []
    for tk in weights:
        try:
            px = fetch_prices(tk, "2y")
            px = pd.Series(px.squeeze() if hasattr(px, "squeeze") else px)
            r = _returns(px)
            if len(r) >= MIN_OBS:
                sleeve_returns[tk] = r
            else:
                missing.append(tk)
        except Exception:
            missing.append(tk)

    if len(sleeve_returns) < 2:
        out["detail"] = "Too few sleeves with usable history."
        return out

    sdf = pd.DataFrame(sleeve_returns).dropna().tail(lookback)
    corr = sdf.corr()
    n_eff = effective_bets(corr)

    w = {tk: weights[tk] for tk in sdf.columns}
    total_w = sum(w.values())
    port = sum(sdf[tk] * (w[tk] / total_w) for tk in sdf.columns)

    fac = build_factor_matrix(fetch_prices, lookback)
    reg = regress(port, fac["returns"]) if fac["returns"] is not None else {}

    out.update(available=True, correlation=corr, n_sleeves=len(sdf.columns),
               effective_bets=n_eff, regression=reg,
               factor_detail=fac.get("detail", ""), missing=missing,
               portfolio_returns=port)
    out["detail"] = (
        f"{len(sdf.columns)} sleeves → ~{n_eff} effective bets. "
        + ("Diversification is largely COSMETIC — consolidate rather than "
           "adding more tickers." if n_eff and n_eff < len(sdf.columns) * 0.35
           else "Reasonable independence across sleeves."))
    return out


def render(st, res: dict):
    st.markdown("### Factor Exposure")
    st.caption(
        "A portfolio can hold fifteen sleeves and be ONE factor. This "
        "measures whether the diversification is real or cosmetic."
    )
    if not res.get("available"):
        st.error(res.get("detail", "Unavailable."))
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Sleeves held", res["n_sleeves"])
    c2.metric("Effective bets", res.get("effective_bets", "n/a"),
              help="N / (1 + (N-1)·avg_correlation). Fifteen sleeves at "
                   "rho=0.8 is ~1.7 independent bets.")
    reg = res.get("regression", {})
    c3.metric("R² vs factors",
              f"{reg.get('r_squared', 0):.2f}" if reg.get("r_squared") is not None
              else "n/a")
    st.caption(res["detail"])

    if reg.get("available"):
        st.markdown("#### Factor betas")
        st.caption(reg["detail"])
        rows = sorted(reg["betas"].items(), key=lambda kv: -abs(kv[1]))
        for name, b in rows:
            colour = "#16a34a" if b > 0 else "#dc2626"
            st.markdown(
                f"<b>{name}</b> <span style='font-family:monospace;"
                f"color:{colour};'>{b:+.2f}</span> "
                f"<span style='color:#9ca3af;'>({FACTOR_PROXIES.get(name,'')})"
                f"</span>", unsafe_allow_html=True)
        if reg.get("alpha_annual") is not None:
            st.caption(f"Annualised intercept: {reg['alpha_annual']:+.2f}%. "
                      f"Treat as noise unless it is large and stable — with "
                      f"correlated proxies the intercept absorbs a great deal.")

    if res.get("correlation") is not None:
        with st.expander("Sleeve correlation matrix"):
            st.dataframe(res["correlation"].round(2),
                        use_container_width=True)

    st.info(
        "**Read R² and effective-bets as reliable; read individual betas as "
        "directional only.** Factor proxies are correlated with each other "
        "(GROWTH and MOMENTUM especially), which makes individual "
        "coefficients unstable. This is a 'am I secretly one bet' diagnostic, "
        "not a Barra-grade risk model."
    )


def selftest() -> dict:
    failures = []
    rng = np.random.default_rng(11)
    n = 300
    idx = pd.bdate_range("2025-01-01", periods=n)

    # Three sleeves driven by ONE common factor -> effective bets must be
    # far below 3, which is the entire point of the metric.
    common = rng.normal(0, 0.01, n)
    same = pd.DataFrame({
        "A": common + rng.normal(0, 0.001, n),
        "B": common + rng.normal(0, 0.001, n),
        "C": common + rng.normal(0, 0.001, n),
    }, index=idx)
    n_eff = effective_bets(same.corr())
    if n_eff is None or n_eff > 1.5:
        failures.append(f"3 identical sleeves gave {n_eff} effective bets")

    # Three genuinely independent sleeves -> close to 3
    indep = pd.DataFrame({c: rng.normal(0, 0.01, n) for c in "ABC"}, index=idx)
    n_eff2 = effective_bets(indep.corr())
    if n_eff2 is None or n_eff2 < 2.5:
        failures.append(f"3 independent sleeves gave {n_eff2} effective bets")

    # Regression must recover a known beta
    f = pd.DataFrame({"MARKET": rng.normal(0, 0.01, n)}, index=idx)
    port = 1.5 * f["MARKET"] + rng.normal(0, 0.0005, n)
    r = regress(port, f)
    if not r["available"] or abs(r["betas"]["MARKET"] - 1.5) > 0.1:
        failures.append(f"beta recovery failed: {r.get('betas')}")
    if r["r_squared"] < 0.9:
        failures.append(f"R² too low on a near-deterministic case: "
                        f"{r['r_squared']}")

    # Insufficient data must refuse
    short = regress(port.head(50), f.head(50))
    if short["available"]:
        failures.append("regressed on insufficient data")

    return {"ok": not failures, "failures": failures,
            "identical_sleeves_eff_bets": n_eff,
            "independent_sleeves_eff_bets": n_eff2,
            "recovered_beta": r["betas"].get("MARKET")}


if __name__ == "__main__":
    import json
    print(json.dumps(selftest(), indent=2, default=str))
