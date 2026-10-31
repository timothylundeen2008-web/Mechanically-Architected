"""
convexity_sleeve.py  (v1 — August 2026)
───────────────────────────────────────
The tail hedge: from a dollar budget to an executable, rule-based position.

WHAT WAS ALREADY BUILT vs WHAT THIS ADDS
────────────────────────────────────────
risk_budget.py already answers "HOW MUCH" — a percentage of NAV priced off
where VIX sits in its own one-year range (Q1 cheapest → 2.00%, Q4 most
expensive → 0.00%). That logic is sound and is reused here rather than
duplicated.

Everything downstream of the dollar figure was missing:

    WHICH instrument      SPX vs SPY, and why the choice matters
    WHICH strike/tenor    moneyness and days-to-expiry, with reasoning
    WHEN to roll          a fixed calendar, not a judgement call
    WHEN to HARVEST       the rule most tail-hedge programmes omit
    WHAT it costs to be wrong   honest expected outcome per quarter

THE MONETIZATION PROBLEM — the part most programmes get wrong
─────────────────────────────────────────────────────────────
A hedge you never sell is not a hedge, it is a permanent fee. The whole
economic value of convexity is captured at the moment of stress, when the
put is worth many multiples of its cost AND the assets you want to buy are
cheap. If you hold to expiry every time, you pay the premium in every calm
quarter and collect nothing in the one quarter that mattered, because a
crash that recovers before expiry leaves the option worthless again.

So this module makes harvesting mechanical: defined profit multiples trigger
partial sales, and the proceeds have a pre-assigned destination (buying the
drawdown), decided in advance rather than in the moment when nobody wants to
buy anything.

HONEST EXPECTED OUTCOME
───────────────────────
Most quarters this expires worthless. That is the design, not a failure —
the same way home insurance is "wasted" every year the house does not burn.
At 1.25% of NAV per quarter the sleeve costs roughly 5% of NAV annually if
every tranche expires at zero. It has to pay for several years of that in
the one event it is bought for. Anyone uncomfortable with that arithmetic
should size it at zero deliberately rather than drift into it.

⚠ OPTIONS CARRY TOTAL LOSS OF PREMIUM AS THE BASE CASE HERE. This module
sizes and schedules; it does not predict. Every premium estimate below is an
APPROXIMATION from implied vol — real fills require a live options chain,
and the estimates should never be treated as quotes.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Optional

# ── Structure defaults ──────────────────────────────────────────────────────
# Tenor: 3-6 months. Shorter decays too fast to survive a slow-developing
# drawdown; longer costs more per unit of protection and dulls the convexity
# (a 12-month put behaves more like a static short than a tail hedge).
TENOR_DAYS_MIN, TENOR_DAYS_TARGET, TENOR_DAYS_MAX = 90, 135, 180

# Moneyness: 5-10% out of the money. At-the-money is not convexity, it is
# expensive delta. Deeper than ~15% OTM is cheap per contract but needs an
# implausibly large move to pay, and the gamma arrives too late.
OTM_MIN_PCT, OTM_TARGET_PCT, OTM_MAX_PCT = 5.0, 8.0, 12.0

# ── Harvest ladder — the rule that makes this a hedge rather than a fee ─────
# Multiples of premium paid. Partial sales, so a deepening crash still has
# exposure left, but early gains are banked rather than round-tripped.
HARVEST_LADDER = [
    (3.0, 0.25, "Sell 25%. First real repricing — bank enough to cover the "
                "sleeve's annual cost."),
    (5.0, 0.25, "Sell another 25%. Half the position is now realised; the "
                "rest still carries full convexity."),
    (10.0, 0.30, "Sell another 30%. This is deep-crisis territory; the "
                 "proceeds are the dry powder the sleeve exists to create."),
]
HARVEST_TAIL_PCT = 0.20   # deliberately left to run or expire

# Roll trigger: roll when remaining tenor falls below this. Theta decay
# accelerates sharply in the final ~60 days, which is exactly the wrong time
# to be holding a hedge you intend to keep.
ROLL_AT_DAYS = 60

# Where harvested proceeds go, decided in advance.
PROCEEDS_DESTINATION = [
    ("Rebalance into the drawdown", 0.60,
     "Buy the sleeves the regime favours at crisis prices. This is the "
     "entire economic point — convexity converts a crash into buying power."),
    ("Restore the hedge", 0.25,
     "Re-establish protection at the NEW (higher) vol. Costlier per unit, "
     "but leaving the book naked after one leg pays is how a hedging "
     "programme dies after its first success."),
    ("Hold as cash", 0.15,
     "Optionality. A crash that keeps going needs unspent capital."),
]


def _bs_put_approx(spot: float, strike: float, iv: float, days: int,
                   r: float = 0.04) -> Optional[float]:
    """
    Black-Scholes put premium — an APPROXIMATION, never a quote.

    Real index puts trade with a pronounced volatility SKEW: downside strikes
    carry materially higher implied vol than at-the-money, which is precisely
    the strikes this sleeve buys. Flat-IV Black-Scholes therefore UNDERSTATES
    the true cost, often by a wide margin. The `skew_adj` below is a crude
    correction so the estimate errs toward being too expensive rather than
    too cheap — an estimate that flatters the trade is worse than no estimate.
    """
    try:
        if min(spot, strike, iv, days) <= 0:
            return None
        t = days / 365.0
        sigma = iv / 100.0
        # Crude skew adjustment: ~1 vol point per 1% OTM, capped.
        otm_pct = max(0.0, (spot - strike) / spot * 100)
        skew_adj = min(otm_pct * 1.0, 12.0) / 100.0
        sigma = sigma + skew_adj

        d1 = (math.log(spot / strike) + (r + sigma ** 2 / 2) * t) / (sigma * math.sqrt(t))
        d2 = d1 - sigma * math.sqrt(t)
        ncdf = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))
        return strike * math.exp(-r * t) * ncdf(-d2) - spot * ncdf(-d1)
    except Exception:
        return None


# For accounts where a single outright put consumes the whole budget, a put
# SPREAD (buy near-OTM, sell far-OTM) cuts the cost by roughly half. The
# trade-off is explicit: the payoff CAPS at the spread width, so it stops
# being unbounded convexity and becomes a defined-payoff hedge. That is a
# real downgrade — but a capped hedge you can actually afford beats an
# uncapped one you cannot.
SPREAD_SHORT_OTM_PCT = 20.0


def design(nav: float, budget_pct: float, spot: float,
           vix: Optional[float] = None,
           otm_pct: float = OTM_TARGET_PCT,
           tenor_days: int = TENOR_DAYS_TARGET,
           use_spx: bool = True,
           use_spread: bool = False) -> dict:
    """
    Turn a budget percentage into a concrete, executable structure.

    Returns a dict, always. Missing inputs produce a plan with `available`
    False and a named reason rather than a fabricated position.
    """
    out = {"available": False, "detail": "", "nav": nav,
           "budget_pct": budget_pct}

    if not nav or not spot or budget_pct is None:
        out["detail"] = "Need NAV, index spot and a budget percentage."
        return out
    if budget_pct <= 0:
        out["detail"] = ("Budget is 0% — vol is in its most expensive "
                        "quartile. Buying protection here is insuring the "
                        "house while it burns. Reduce exposure directly "
                        "instead; do NOT buy convexity at these prices.")
        return out

    dollar_budget = nav * budget_pct / 100.0
    strike = round(spot * (1 - otm_pct / 100.0))

    # Contract multiplier: SPX is 100x index, SPY is 100x (~1/10 of index).
    multiplier = 100
    underlying = "SPX" if use_spx else "SPY"
    ref_spot = spot if use_spx else spot / 10.0
    ref_strike = strike if use_spx else round(strike / 10.0)

    iv = vix if vix else 20.0
    prem_per_unit = _bs_put_approx(ref_spot, ref_strike, iv, tenor_days)
    if not prem_per_unit or prem_per_unit <= 0:
        out["detail"] = "Premium estimate failed — need a live options chain."
        return out

    short_strike = None
    if use_spread:
        short_strike = round(ref_spot * (1 - SPREAD_SHORT_OTM_PCT / 100.0))
        short_prem = _bs_put_approx(ref_spot, short_strike, iv, tenor_days)
        if short_prem and short_prem > 0:
            prem_per_unit = max(prem_per_unit - short_prem, 0.01)

    cost_per_contract = prem_per_unit * multiplier
    n_contracts = int(dollar_budget // cost_per_contract)
    actual_cost = n_contracts * cost_per_contract

    notional = n_contracts * ref_strike * multiplier
    notional_pct = (notional / nav * 100) if nav else 0

    expiry = date.today() + timedelta(days=tenor_days)

    out.update({
        "available": n_contracts > 0,
        "underlying": underlying,
        "spot": ref_spot,
        "strike": ref_strike,
        "otm_pct": otm_pct,
        "tenor_days": tenor_days,
        "expiry_approx": expiry,
        "iv_used": iv,
        "est_premium_per_contract": round(cost_per_contract, 2),
        "contracts": n_contracts,
        "dollar_budget": round(dollar_budget, 2),
        "est_actual_cost": round(actual_cost, 2),
        "notional_covered": round(notional, 2),
        "notional_pct_of_nav": round(notional_pct, 1),
        "roll_at": expiry - timedelta(days=ROLL_AT_DAYS),
        "is_spread": use_spread,
        "short_strike": short_strike,
        "max_payoff_per_contract": (
            (ref_strike - short_strike) * multiplier if short_strike else None),
    })

    if n_contracts == 0:
        out["available"] = False
        # Escalation path, in order of what actually helps — NOT a generic
        # "use SPY" message, which is wrong when SPY is already selected.
        opts = []
        if use_spx:
            opts.append("switch to SPY (~1/10 the notional per contract)")
        if not use_spread:
            opts.append("use a PUT SPREAD (buy "
                       f"{otm_pct:.0f}% OTM / sell {SPREAD_SHORT_OTM_PCT:.0f}% "
                       f"OTM) — roughly half the cost, but the payoff CAPS "
                       f"at the spread width")
        min_nav = cost_per_contract / (budget_pct / 100.0)
        opts.append(f"accept that this structure needs ~${min_nav:,.0f} NAV "
                   f"at a {budget_pct:.2f}% budget")
        out["min_viable_nav"] = round(min_nav, 0)
        out["detail"] = (
            f"Budget ${dollar_budget:,.0f} is below the cost of one "
            f"{underlying} contract (~${cost_per_contract:,.0f}). Options: "
            + "; ".join(opts) + ".")
    else:
        out["detail"] = (
            f"{n_contracts} × {underlying} {ref_strike:.0f}P "
            f"~{tenor_days}d (~{otm_pct:.0f}% OTM), est. "
            f"${actual_cost:,.0f} ({actual_cost/nav*100:.2f}% of NAV), "
            f"covering ${notional:,.0f} notional ({notional_pct:.0f}% of NAV).")
    return out


def payoff_scenarios(plan: dict) -> list[dict]:
    """
    What the sleeve returns across index outcomes at expiry.

    Intrinsic value only — deliberately conservative. In a real fast
    drawdown the position is worth MORE than these figures before expiry,
    because implied vol spikes and remaining time value inflates the mark.
    That extra is what the harvest ladder exists to capture; it is excluded
    here so the numbers cannot flatter the trade.
    """
    if not plan.get("available"):
        return []
    spot, strike = plan["spot"], plan["strike"]
    n, cost = plan["contracts"], plan["est_actual_cost"]
    rows = []
    for drop in (0, -5, -10, -15, -20, -30, -40):
        idx = spot * (1 + drop / 100.0)
        intrinsic = max(0.0, strike - idx)
        if plan.get("short_strike"):
            # A spread's payoff caps at the width — the explicit trade-off
            # for affordability.
            intrinsic = min(intrinsic, strike - plan["short_strike"])
        intrinsic = intrinsic * 100 * n
        pnl = intrinsic - cost
        rows.append({
            "index_move_pct": drop,
            "index_level": round(idx, 1),
            "sleeve_value": round(intrinsic, 0),
            "sleeve_pnl": round(pnl, 0),
            "multiple": round(intrinsic / cost, 2) if cost else 0,
            "offset_pct_of_nav": round(pnl / plan["nav"] * 100, 2)
            if plan.get("nav") else None,
        })
    return rows


def harvest_plan(cost_basis: float) -> list[dict]:
    """The pre-committed sell ladder, in dollars."""
    return [{"multiple": m, "sell_pct": pct,
             "trigger_value": round(cost_basis * m, 0),
             "proceeds_approx": round(cost_basis * m * pct, 0),
             "note": note}
            for m, pct, note in HARVEST_LADDER]


def render(st, plan: dict, budget_info: dict, nav: float):
    """Render the Convexity Sleeve tab."""
    st.markdown("### Convexity Sleeve")
    st.caption(
        "The only sleeve that GAINS in a crash rather than merely falling "
        "less. Sized off where VIX sits in its own one-year range — buy when "
        "protection is cheap, not when it is frightening."
    )

    q = budget_info.get("quartile")
    pct = budget_info.get("pct_of_nav")
    c1, c2, c3 = st.columns(3)
    c1.metric("VIX quartile", f"Q{q}" if q else "n/a",
              help="Q1 = cheapest quartile of VIX's own year. The budget "
                   "scales inversely: cheap vol → spend more.")
    c2.metric("Budget", f"{pct:.2f}% of NAV" if pct is not None else "n/a")
    c3.metric("Dollar budget",
              f"${nav * pct / 100:,.0f}" if (nav and pct is not None) else "n/a")
    st.caption(budget_info.get("detail", ""))

    if not plan.get("available"):
        st.warning(plan.get("detail", "No structure available."))
        return

    st.markdown("#### Structure")
    st.code(
        f"{plan['contracts']} × {plan['underlying']} {plan['strike']:.0f} PUT\n"
        f"~{plan['tenor_days']} days  (approx expiry {plan['expiry_approx']})\n"
        f"{plan['otm_pct']:.0f}% out of the money   spot {plan['spot']:,.0f}\n"
        f"Est. cost ${plan['est_actual_cost']:,.0f}  "
        f"({plan['est_actual_cost']/nav*100:.2f}% of NAV)\n"
        f"Notional covered ${plan['notional_covered']:,.0f}  "
        f"({plan['notional_pct_of_nav']:.0f}% of NAV)\n"
        f"ROLL at {plan['roll_at']} ({ROLL_AT_DAYS}d remaining)",
        language="text")
    st.caption(
        "⚠ Premium is a Black-Scholes ESTIMATE with a crude skew adjustment, "
        "not a quote. Index puts trade with pronounced downside skew — the "
        "real cost of these strikes is higher than flat-IV models suggest. "
        "Price against a live chain before executing.")

    st.markdown("#### Payoff at expiry (intrinsic only)")
    rows = payoff_scenarios(plan)
    if rows:
        import pandas as pd
        df = pd.DataFrame(rows)
        df.columns = ["Index move", "Index level", "Sleeve value", "P&L",
                      "Multiple", "Offset (% NAV)"]
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.caption(
            "Intrinsic value only — deliberately conservative. In a fast "
            "drawdown the position marks HIGHER than this before expiry, "
            "because implied vol spikes and time value inflates. That excess "
            "is what the harvest ladder captures; excluding it here keeps the "
            "numbers from flattering the trade.")

    st.markdown("#### Harvest ladder — the rule most programmes omit")
    st.caption(
        "A hedge you never sell is a permanent fee. The economic value is "
        "captured at the moment of stress, when the put is worth multiples "
        "of cost AND the assets you want are cheap. These triggers are "
        "pre-committed so the decision is not made in the moment, when "
        "nobody wants to buy anything.")
    for h in harvest_plan(plan["est_actual_cost"]):
        st.markdown(
            f"**{h['multiple']:.0f}× (${h['trigger_value']:,.0f})** — sell "
            f"{h['sell_pct']*100:.0f}%, ~${h['proceeds_approx']:,.0f}")
        st.caption(h["note"])
    st.markdown(f"**Final {HARVEST_TAIL_PCT*100:.0f}%** — left to run or "
                f"expire. A deepening crisis should still find the book with "
                f"live convexity.")

    st.markdown("#### Where proceeds go — decided in advance")
    for name, share, why in PROCEEDS_DESTINATION:
        st.markdown(f"**{share*100:.0f}% — {name}**")
        st.caption(why)

    with st.expander("The honest cost of this sleeve"):
        annual = (plan["est_actual_cost"] / nav * 100) * 4 if nav else 0
        st.markdown(
            f"At this size, rolled quarterly, the sleeve costs roughly "
            f"**{annual:.1f}% of NAV per year** if every tranche expires "
            f"worthless — which is what happens in most years.\n\n"
            f"That is the design, not a failure. It has to pay for several "
            f"years of premium in the one event it exists for. The 2008 "
            f"analogue: a sleeve like this returned 10–30× during Q4, which "
            f"covered a decade of carrying cost and — more importantly — "
            f"produced buying power precisely when everything was cheap.\n\n"
            f"**If that arithmetic is uncomfortable, size it at zero "
            f"deliberately rather than drifting into it and abandoning it "
            f"after two dead quarters.** A hedging programme abandoned right "
            f"before it was needed is worse than never starting one.")


def selftest() -> dict:
    failures = []

    # At $100k with a 1.25% budget, even one SPY put exceeds the budget —
    # a REAL constraint, so the module must say so and offer the escalation
    # path rather than silently building nothing.
    small = design(nav=100_000, budget_pct=1.25, spot=7745, vix=14.8,
                   use_spx=False)
    if small["available"]:
        failures.append("expected $100k/1.25% SPY outright to be unaffordable")
    elif "PUT SPREAD" not in small["detail"]:
        failures.append("did not offer the put-spread escalation")
    elif not small.get("min_viable_nav"):
        failures.append("did not report minimum viable NAV")

    # The spread must fix it at the same NAV
    spread = design(nav=100_000, budget_pct=1.25, spot=7745, vix=14.8,
                    use_spx=False, use_spread=True)
    if not spread["available"]:
        failures.append(f"put spread still unaffordable: {spread['detail']}")
    else:
        cap = spread.get("max_payoff_per_contract")
        if not cap or cap <= 0:
            failures.append("spread max payoff not computed")

    # Larger account: outright SPY must work
    plan_spy = design(nav=400_000, budget_pct=1.25, spot=7745, vix=14.8,
                      use_spx=False)
    if not plan_spy["available"]:
        failures.append(f"SPY plan unavailable at 400k: {plan_spy['detail']}")
    else:
        if plan_spy["est_actual_cost"] > 400_000 * 0.0125 * 1.001:
            failures.append("SPY cost exceeded budget")
        rows = payoff_scenarios(plan_spy)
        if not rows:
            failures.append("no payoff scenarios")
        else:
            flat = [r for r in rows if r["index_move_pct"] == 0][0]
            if flat["sleeve_value"] != 0:
                failures.append("flat index should expire worthless")
            deep = [r for r in rows if r["index_move_pct"] == -30][0]
            if deep["multiple"] <= 1:
                failures.append(f"-30% should be profitable, got "
                                f"{deep['multiple']}x")

    # Q4 (expensive vol) must refuse to build
    zero = design(nav=100_000, budget_pct=0.0, spot=7745, vix=35)
    if zero["available"] or "insuring the house" not in zero["detail"]:
        failures.append("Q4 zero-budget case did not refuse correctly")

    h = harvest_plan(5000)
    if abs(sum(x[1] for x in HARVEST_LADDER) + HARVEST_TAIL_PCT - 1.0) > 1e-9:
        failures.append("harvest ladder + tail does not sum to 100%")
    if abs(sum(x[1] for x in PROCEEDS_DESTINATION) - 1.0) > 1e-9:
        failures.append("proceeds destinations do not sum to 100%")

    return {"ok": not failures, "failures": failures,
            "spy_contracts": plan_spy.get("contracts"),
            "spy_cost": plan_spy.get("est_actual_cost"),
            "harvest_steps": len(h)}


if __name__ == "__main__":
    import json
    print(json.dumps(selftest(), indent=2, default=str))
