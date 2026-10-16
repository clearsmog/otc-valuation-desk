"""Price challenges: compare our value with the counterparty mark and work any
difference above tolerance down to a cause.

The attribution replays the usual reasons a dealer's mark differs, one at a
time, and keeps the first that brings the two values within tolerance:

Tested by repricing (the cause is confirmed if it closes the gap):
    PRIOR_DAY, DAY_COUNT, INTERPOLATION, DIRECTION, NOTIONAL
Implied from a risk measure (the size is inferred, so the cause is "likely"
and goes to the dealer as a question, not a finding):
    BID_SIDE (gap is a fraction of a bp / vol point against the client),
    VOL (gap / vega), SPOT_SNAPSHOT (gap / FX delta)

A gap no hypothesis explains is UNEXPLAINED and escalated.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

from . import pricing as P
from .marks import DealerMark
from .market import Market, boe_interpolated
from .trades import FXForward, FXOption, OISSwap, Trade

ACTIONS = {
    "PRIOR_DAY": "Ask the dealer for the curve/spot snapshot date; re-request today's mark",
    "DAY_COUNT": "Confirm fixed-leg day count against the confirmation; ask the dealer to correct its booking",
    "INTERPOLATION": "Methodology difference (curve interpolation); document, no booking change",
    "DIRECTION": "Booking break: confirm direction against the confirmation; escalate to operations",
    "NOTIONAL": "Booking break: confirm notional against the confirmation; escalate to operations",
    "BID_SIDE": "Ask whether the mark is mid or bid/offer; request a mid mark",
    "VOL": "Request the dealer's vol for this expiry/strike and compare with our surface",
    "SPOT_SNAPSHOT": "Ask for the spot fixing time used; align snapshot times",
    "UNEXPLAINED": "Escalate: request full valuation inputs from the dealer",
}


@dataclass(frozen=True)
class ChallengeResult:
    trade_id: str
    counterparty: str
    product: str
    ccy: str
    our_value: float
    dealer_mark: float
    difference: float  # dealer - ours
    tolerance: float
    status: str  # WITHIN_TOLERANCE | EXPLAINED | LIKELY | UNEXPLAINED
    cause: str
    detail: str
    residual: float
    action: str


def risk_units(trade: Trade, mkt: Market) -> dict[str, float]:
    s = P.sensitivities(trade, mkt)
    out = {}
    if isinstance(trade, OISSwap):
        out["pv01"] = s[f"pv01_{trade.ccy}"]
    else:
        out["delta_1pct"] = s["fx_delta_1pct"]
    if isinstance(trade, FXOption):
        out["vega"] = s["vega_1pt"]
    return out


def tolerance(trade: Trade, units: dict[str, float]) -> float:
    """Absolute floor of 1,000 in the PV currency, or a quarter of the
    product's natural risk unit, whichever is larger."""
    if isinstance(trade, OISSwap):
        scaled = 0.25 * abs(units["pv01"])  # 0.25bp
    elif isinstance(trade, FXOption):
        scaled = 0.25 * abs(units["vega"])  # 0.25 vol point
    else:
        scaled = 2.0 * abs(units["delta_1pct"]) / 100.0  # 2bp of spot
    return max(1_000.0, scaled)


def _round_notional(x: float) -> float:
    return round(x / 1_000_000) * 1_000_000


def attribute(
    trade: Trade, mark: float, mkt: Market, prior: Market | None
) -> tuple[str, str, str, float]:
    """Return (status, cause, detail, residual)."""
    own = P.price(trade, mkt)
    units = risk_units(trade, mkt)
    tol = tolerance(trade, units)
    gap = mark - own
    if abs(gap) <= tol:
        return "WITHIN_TOLERANCE", "", "", gap

    # --- confirmed by repricing ---------------------------------------------
    trials: list[tuple[str, str, float]] = []
    if prior is not None:
        trials.append(
            (
                "PRIOR_DAY",
                f"matches a mark off {prior.asof} curves and spot",
                P.price(trade, prior),
            )
        )
    if isinstance(trade, OISSwap) and trade.ccy == "GBP":
        trials.append(
            (
                "DAY_COUNT",
                "matches a fixed leg accrued ACT/360",
                P.price_ois(trade, mkt, P.OISConventions(fixed_day_count="ACT/360")),
            )
        )
        trials.append(
            (
                "INTERPOLATION",
                "matches a curve read off the BoE zero curve",
                P.price(trade, boe_interpolated(mkt)),
            )
        )
    if isinstance(trade, OISSwap):
        flipped = replace(trade, pay_fixed=not trade.pay_fixed)
    elif isinstance(trade, FXForward):
        flipped = replace(trade, buy_base=not trade.buy_base)
    else:
        flipped = replace(trade, long=not trade.long)
    # Direction and notional errors scale the value, so on a trade worth
    # little (near par, near the money) they cannot be told apart from
    # noise: the test only runs when the value is large against tolerance.
    has_power = abs(own) >= 2 * tol
    if has_power:
        trials.append(
            ("DIRECTION", "matches the opposite direction", P.price(flipped, mkt))
        )
    if has_power:
        raw_n = trade.notional * mark / own
        implied_n = _round_notional(raw_n)
        # PV is linear in notional, so a booking error shows as an exact ratio
        if (
            implied_n > 0
            and implied_n != trade.notional
            and abs(raw_n - implied_n) <= 0.002 * implied_n
        ):
            trials.append(
                (
                    "NOTIONAL",
                    f"matches a notional of {implied_n:,.0f} (booked {trade.notional:,.0f})",
                    P.price(replace(trade, notional=implied_n), mkt),
                )
            )
    # a cause is confirmed only if it closes at least 90% of the gap; the
    # closest fit wins, so a coincidental near-match loses to the real one
    fits = [(abs(mark - v), c, d, mark - v) for c, d, v in trials]
    fits = [f for f in fits if f[0] <= min(tol, 0.1 * abs(gap))]
    if fits:
        _, cause, detail, residual = min(fits)
        return "EXPLAINED", cause, detail, residual

    # --- implied from risk (likely, to be confirmed with the dealer) --------
    if isinstance(trade, FXOption):
        shift = gap / units["vega"]
        if abs(shift) <= 5.0:
            # bid side: a small move always against the client
            if gap < 0 and abs(shift) <= 0.6:
                return (
                    "LIKELY",
                    "BID_SIDE",
                    f"gap = {abs(shift):.2f} vol pts against us (bid/offer side)",
                    0.0,
                )
            value = P.price(trade, mkt.bump_vol(trade.pair, shift))
            return (
                "LIKELY",
                "VOL",
                f"dealer vol about {shift:+.2f} pts from ours",
                mark - value,
            )
    detail = (
        ""
        if has_power
        else "value too small to test direction/notional: check the confirmation. "
    )
    if isinstance(trade, OISSwap):
        bp = gap / units["pv01"] if units["pv01"] else 0.0
        if gap < 0 and abs(gap) <= 1.0 * abs(units["pv01"]):
            return (
                "LIKELY",
                "BID_SIDE",
                detail + f"gap = {abs(gap / units['pv01']):.2f}bp of PV01 against us",
                0.0,
            )
        detail += f"gap equals a {bp:+.2f}bp curve shift"
    if isinstance(trade, FXForward | FXOption):
        pct = gap / units["delta_1pct"]
        if abs(pct) <= 0.5:
            value = P.price(trade, mkt.bump_spot(trade.pair, pct / 100.0))
            if abs(mark - value) <= tol:
                return (
                    "LIKELY",
                    "SPOT_SNAPSHOT",
                    f"gap equals spot {pct:+.3f}% from ours",
                    mark - value,
                )
        detail += f"gap equals spot {pct:+.3f}%"
    return "UNEXPLAINED", "UNEXPLAINED", detail, gap


def run_challenges(
    trades: list[Trade], marks: list[DealerMark], mkt: Market, prior_asof: date | None
) -> list[ChallengeResult]:
    from .market import build_market

    prior = build_market(prior_asof) if prior_asof else None
    by_id = {m.trade_id: m for m in marks}
    out = []
    for t in trades:
        m = by_id[t.trade_id]
        own = P.price(t, mkt)
        tol = tolerance(t, risk_units(t, mkt))
        status, cause, detail, residual = attribute(t, m.mark, mkt, prior)
        out.append(
            ChallengeResult(
                t.trade_id,
                t.counterparty,
                t.product,
                m.ccy,
                own,
                m.mark,
                m.mark - own,
                tol,
                status,
                cause,
                detail,
                residual,
                ACTIONS.get(cause, "") if cause else "",
            )
        )
    return out
