"""Synthetic counterparty (dealer) marks.

A real client receives one mark per trade from each counterparty and never
learns why a mark differs. Here every mark is generated from a stated cause so
the price-challenge attribution can be tested against an answer key.

Causes:
- NONE              agrees within tolerance (small noise)
- PRIOR_DAY         dealer marked off the previous day's curves and spot
- DAY_COUNT         GBP fixed leg accrued ACT/360 instead of ACT/365F
- INTERPOLATION     GBP curve taken straight from the BoE zero curve (smooth
                    interpolation) instead of bootstrapped log-linear
- BID_SIDE          mark at the dealer's side of the bid/offer, not mid
- NOTIONAL          dealer booked a different notional
- DIRECTION         dealer booked the opposite direction
- VOL               dealer's vol differs by a few points
- SPOT_SNAPSHOT     FX spot taken at a different time of day

All names, sizes and marks are invented; the causes are planted, not observed.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

import numpy as np

from . import pricing as P
from .market import Market, boe_interpolated, build_market
from .trades import FXForward, FXOption, OISSwap, Trade

# trade_id -> (cause, parameter). Explicit so the answer key is readable.
PLANTED: dict[str, tuple[str, float]] = {
    "NBM-IRS-001": ("DAY_COUNT", 0.0),
    "NBM-IRS-002": ("NONE", 0.0),
    "NBM-IRS-003": ("NOTIONAL", 4_000_000.0),  # dealer booked 4m, not 40m
    "NBM-IRS-004": ("NONE", 0.0),
    "NBM-IRS-005": ("BID_SIDE", 0.5),  # bp
    "NBM-IRS-006": ("INTERPOLATION", 0.0),  # forward start, off-pillar dates
    "NBM-IRS-007": ("PRIOR_DAY", 0.0),
    "NBM-IRS-008": ("NONE", 0.0),
    "NBM-IRS-009": ("DIRECTION", 0.0),
    "NBM-IRS-010": ("NONE", 0.0),
    "NBM-FXF-001": ("NONE", 0.0),
    "NBM-FXF-002": ("SPOT_SNAPSHOT", 0.25),  # % spot difference
    "NBM-FXF-003": ("NONE", 0.0),
    "NBM-FXF-004": ("PRIOR_DAY", 0.0),
    "NBM-FXF-005": ("NONE", 0.0),
    "NBM-FXO-001": ("NONE", 0.0),
    "NBM-FXO-002": ("VOL", 1.5),  # vol points
    "NBM-FXO-003": ("BID_SIDE", 0.4),  # vol points
    "NBM-FXO-004": ("NONE", 0.0),
    "NBM-FXO-005": ("NOTIONAL", 15_000_000.0),  # dealer booked 15m, not 12m
}


@dataclass(frozen=True)
class DealerMark:
    trade_id: str
    counterparty: str
    ccy: str
    mark: float


def _risk_unit(trade: Trade, mkt: Market) -> float:
    s = P.sensitivities(trade, mkt)
    if isinstance(trade, OISSwap):
        return abs(s[f"pv01_{trade.ccy}"])
    if isinstance(trade, FXOption):
        return abs(s["vega_1pt"])
    return abs(s["fx_delta_1pct"]) / 100.0  # per 1bp of spot


def marked_value(
    trade: Trade, mkt: Market, cause: str, param: float, prior: Market | None
) -> float:
    """The value a dealer would show for ``trade`` under ``cause``."""
    own = P.price(trade, mkt)
    if cause == "NONE":
        return own
    if cause == "PRIOR_DAY":
        assert prior is not None
        return P.price(trade, prior)
    if cause == "DAY_COUNT":
        assert isinstance(trade, OISSwap)
        return P.price_ois(trade, mkt, P.OISConventions(fixed_day_count="ACT/360"))
    if cause == "INTERPOLATION":
        return P.price(trade, boe_interpolated(mkt))
    if cause == "BID_SIDE":
        # always against the client: the dealer's side of the spread
        return own - param * _risk_unit(trade, mkt)
    if cause == "NOTIONAL":
        return P.price(replace(trade, notional=param), mkt)
    if cause == "DIRECTION":
        if isinstance(trade, OISSwap):
            return P.price(replace(trade, pay_fixed=not trade.pay_fixed), mkt)
        if isinstance(trade, FXForward):
            return P.price(replace(trade, buy_base=not trade.buy_base), mkt)
        return P.price(replace(trade, long=not trade.long), mkt)
    if cause == "VOL":
        return P.price(trade, mkt.bump_vol(trade.pair, param))
    if cause == "SPOT_SNAPSHOT":
        return P.price(trade, mkt.bump_spot(trade.pair, param / 100.0))
    raise ValueError(cause)


def generate_marks(
    trades: list[Trade], mkt: Market, prior_asof: date, seed: int = 7
) -> tuple[list[DealerMark], list[dict]]:
    """Dealer marks plus the answer key (kept apart from the challenge code)."""
    rng = np.random.default_rng(seed)
    prior = build_market(prior_asof)
    marks, key = [], []
    for t in trades:
        cause, param = PLANTED.get(t.trade_id, ("NONE", 0.0))
        v = marked_value(t, mkt, cause, param, prior)
        if cause == "NONE":
            v += rng.uniform(-0.05, 0.05) * _risk_unit(
                t, mkt
            )  # noise well inside tolerance
        marks.append(DealerMark(t.trade_id, t.counterparty, P.pv_ccy(t), v))
        key.append({"trade_id": t.trade_id, "cause": cause, "param": param})
    return marks, key
