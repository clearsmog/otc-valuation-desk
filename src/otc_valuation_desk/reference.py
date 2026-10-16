"""Independent reference valuation in QuantLib.

Built from the same par quotes, fixings, spot and vols as the own engine but
with QuantLib's calendars, schedule rules, curve bootstrap and pricing
engines. Where the two disagree beyond tolerance the difference is either a
bug or a convention gap, and the report says which.

Known convention gap: QuantLib's Garman-Kohlhagen engine measures rates from
today to expiry and has no settlement lag, while the own pricer runs the
forward from the spot date to the delivery date. The gap is a few dollars per
million of notional and is listed in the report as a convention difference.
"""

from __future__ import annotations

from datetime import date

import QuantLib as ql

from .curves import CONVENTIONS
from .market import Market
from .trades import FXForward, FXOption, OISSwap, Trade


def qd(d: date) -> ql.Date:
    return ql.Date(d.day, d.month, d.year)


QL_DC = {"ACT/365F": ql.Actual365Fixed(), "ACT/360": ql.Actual360()}


class QLMarket:
    def __init__(self, mkt: Market):
        self.mkt = mkt
        self.asof = qd(mkt.asof)
        ql.Settings.instance().evaluationDate = self.asof
        self.handles: dict[str, ql.RelinkableYieldTermStructureHandle] = {}
        self.indices: dict[str, ql.OvernightIndex] = {}
        for ccy in ("GBP", "USD"):
            h = ql.RelinkableYieldTermStructureHandle()
            idx = ql.Sonia(h) if ccy == "GBP" else ql.Sofr(h)
            helpers = [
                ql.OISRateHelper(
                    CONVENTIONS[ccy]["spot_lag"],
                    ql.Period(m, ql.Months),
                    ql.QuoteHandle(ql.SimpleQuote(r)),
                    idx,
                )
                for m, r in mkt.curves[ccy].quotes
            ]
            curve = ql.PiecewiseLogLinearDiscount(
                self.asof, helpers, ql.Actual365Fixed()
            )
            curve.enableExtrapolation()
            h.linkTo(curve)
            self.handles[ccy] = h
            self.indices[ccy] = idx
            fixings = mkt.fixings[CONVENTIONS[ccy]["index"]]
            for d, v in fixings.items():
                if d < mkt.asof and idx.isValidFixingDate(qd(d)):
                    idx.addFixing(qd(d), v / 100.0, True)

    def df(self, ccy: str, d: date) -> float:
        return self.handles[ccy].discount(qd(d))


def ql_ois(trade: OISSwap, qm: QLMarket) -> float:
    c = CONVENTIONS[trade.ccy]
    idx = qm.indices[trade.ccy]
    sched = ql.Schedule(
        qd(trade.start),
        qd(trade.end),
        ql.Period(ql.Annual),
        idx.fixingCalendar(),
        ql.ModifiedFollowing,
        ql.ModifiedFollowing,
        ql.DateGeneration.Backward,
        False,
    )
    side = (
        ql.OvernightIndexedSwap.Payer
        if trade.pay_fixed
        else ql.OvernightIndexedSwap.Receiver
    )
    swap = ql.OvernightIndexedSwap(
        side, trade.notional, sched, trade.fixed_rate, QL_DC[c["day_count"]], idx
    )
    swap.setPricingEngine(ql.DiscountingSwapEngine(qm.handles[trade.ccy]))
    return swap.NPV()


def ql_fx_forward(trade: FXForward, qm: QLMarket) -> float:
    if trade.delivery <= qm.mkt.asof:
        return 0.0
    spot_d = ql.JointCalendar(
        ql.UnitedKingdom(), ql.UnitedStates(ql.UnitedStates.FederalReserve)
    ).advance(qm.asof, 2, ql.Days)
    base, quote = trade.pair[:3], trade.pair[3:]
    hb, hq = qm.handles[base], qm.handles[quote]
    f = (
        qm.mkt.spot[trade.pair]
        * (hb.discount(qd(trade.delivery)) / hb.discount(spot_d))
        / (hq.discount(qd(trade.delivery)) / hq.discount(spot_d))
    )
    sign = 1.0 if trade.buy_base else -1.0
    return sign * trade.notional * (f - trade.strike) * hq.discount(qd(trade.delivery))


def ql_fx_option(trade: FXOption, qm: QLMarket) -> float:
    if trade.expiry < qm.mkt.asof:
        return 0.0
    t = ql.Actual365Fixed().yearFraction(qm.asof, qd(trade.expiry))
    vol = qm.mkt.fx_vol[trade.pair].vol(t)
    process = ql.GarmanKohlagenProcess(
        ql.QuoteHandle(ql.SimpleQuote(qm.mkt.spot[trade.pair])),
        qm.handles[trade.pair[:3]],  # foreign (base) curve
        qm.handles[trade.pair[3:]],  # domestic (quote) curve
        ql.BlackVolTermStructureHandle(
            ql.BlackConstantVol(qm.asof, ql.NullCalendar(), vol, ql.Actual365Fixed())
        ),
    )
    payoff = ql.PlainVanillaPayoff(
        ql.Option.Call if trade.call else ql.Option.Put, trade.strike
    )
    opt = ql.VanillaOption(payoff, ql.EuropeanExercise(qd(trade.expiry)))
    opt.setPricingEngine(ql.AnalyticEuropeanEngine(process))
    sign = 1.0 if trade.long else -1.0
    return sign * trade.notional * opt.NPV()


def ql_price(trade: Trade, qm: QLMarket) -> float:
    if isinstance(trade, OISSwap):
        return ql_ois(trade, qm)
    if isinstance(trade, FXForward):
        return ql_fx_forward(trade, qm)
    if isinstance(trade, FXOption):
        return ql_fx_option(trade, qm)
    raise TypeError(type(trade))
