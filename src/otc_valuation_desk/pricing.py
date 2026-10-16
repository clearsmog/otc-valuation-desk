"""Own pricers. No QuantLib here: see reference.py for the independent check.

Sign convention: present values are from the client's side of the trade.
OIS PVs are in the swap currency; FX PVs are in the quote currency (USD for
GBPUSD). ``pv_usd`` converts everything to USD at spot for aggregation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import log, sqrt

import pandas as pd
from scipy.stats import norm

from .curves import CONVENTIONS, t_of
from .dates import add_business_days, is_business_day, schedule, year_fraction
from .market import Market
from .trades import FXForward, FXOption, OISSwap, Swaption, Trade, XCCYSwap

DENOM = {"ACT/365F": 365.0, "ACT/360": 360.0}


@dataclass(frozen=True)
class OISConventions:
    """Overridable so a dealer's (or a mistaken) convention can be replayed."""

    fixed_day_count: str | None = None  # None = market standard for the currency


def _fixing(fixings: pd.Series, d: date) -> tuple[float, bool]:
    """Fixing for ``d`` in decimal; falls back to the last earlier fixing and
    reports that it did."""
    if d in fixings.index:
        return float(fixings[d]) / 100.0, False
    earlier = fixings[fixings.index < d]
    if earlier.empty:
        raise KeyError(f"no fixing on or before {d}")
    return float(earlier.iloc[-1]) / 100.0, True


def realised_compounding(
    fixings: pd.Series, start: date, asof: date, cal: str, day_count: str
) -> tuple[float, int]:
    """Compounded overnight factor over [start, asof): each business day's
    fixing accrues for the calendar days to the next business day."""
    factor, filled = 1.0, 0
    d = start
    while d < asof:
        if is_business_day(d, cal):
            nxt = d + timedelta(days=1)
            while not is_business_day(nxt, cal):
                nxt += timedelta(days=1)
            r, was_filled = _fixing(fixings, d)
            filled += was_filled
            factor *= 1.0 + r * (min(nxt, asof) - d).days / DENOM[day_count]
            d = nxt
        else:
            d += timedelta(days=1)
    return factor, filled


def price_ois(
    trade: OISSwap, mkt: Market, conv: OISConventions = OISConventions()
) -> float:
    c = CONVENTIONS[trade.ccy]
    curve = mkt.curves[trade.ccy]
    fixed_dc = conv.fixed_day_count or c["day_count"]
    asof = mkt.asof
    fixed = floating = 0.0
    for p in schedule(trade.start, trade.end, c["freq"], c["cal"]):
        if p.end <= asof:
            continue  # settled
        df_end = curve.df_at(p.end)
        fixed += (
            trade.notional
            * trade.fixed_rate
            * year_fraction(p.start, p.end, fixed_dc)
            * df_end
        )
        if p.start >= asof:
            floating += trade.notional * (curve.df_at(p.start) - df_end)
        else:
            a, _ = realised_compounding(
                mkt.fixings[c["index"]], p.start, asof, c["cal"], c["day_count"]
            )
            floating += trade.notional * (a - df_end)  # df(asof) = 1
    return (floating - fixed) if trade.pay_fixed else (fixed - floating)


def fx_spot_date(mkt: Market) -> date:
    return add_business_days(mkt.asof, 2, "GBP+USD")


def fx_forward_rate(mkt: Market, pair: str, delivery: date) -> float:
    """Covered interest parity, measured from the spot date."""
    base, quote = mkt.curves[pair[:3]], mkt.curves[pair[3:]]
    spot_d = fx_spot_date(mkt)
    return (
        mkt.spot[pair]
        * (base.df_at(delivery) / base.df_at(spot_d))
        / (quote.df_at(delivery) / quote.df_at(spot_d))
    )


def price_fx_forward(trade: FXForward, mkt: Market) -> float:
    if trade.delivery <= mkt.asof:
        return 0.0
    f = fx_forward_rate(mkt, trade.pair, trade.delivery)
    sign = 1.0 if trade.buy_base else -1.0
    return (
        sign
        * trade.notional
        * (f - trade.strike)
        * mkt.curves[trade.pair[3:]].df_at(trade.delivery)
    )


def black_forward(f: float, k: float, vol: float, t: float, call: bool) -> float:
    """Undiscounted Black price per unit of base currency."""
    if t <= 0 or vol <= 0:
        return max(f - k, 0.0) if call else max(k - f, 0.0)
    sd = vol * sqrt(t)
    d1 = (log(f / k) + 0.5 * sd * sd) / sd
    d2 = d1 - sd
    if call:
        return f * norm.cdf(d1) - k * norm.cdf(d2)
    return k * norm.cdf(-d2) - f * norm.cdf(-d1)


def price_fx_option(trade: FXOption, mkt: Market, vol: float | None = None) -> float:
    """Garman-Kohlhagen in forward form: forward to the delivery date,
    volatility time to the expiry date, discounted from delivery."""
    if trade.expiry < mkt.asof:
        return 0.0
    t_exp = t_of(mkt.asof, trade.expiry)
    f = fx_forward_rate(mkt, trade.pair, trade.delivery)
    sigma = mkt.fx_vol[trade.pair].vol_at(t_exp, trade.strike, f) if vol is None else vol
    df = mkt.curves[trade.pair[3:]].df_at(trade.delivery)
    sign = 1.0 if trade.long else -1.0
    return (
        sign
        * trade.notional
        * df
        * black_forward(f, trade.strike, sigma, t_exp, trade.call)
    )


def forward_swap(mkt: Market, ccy: str, start: date, end: date) -> tuple[float, float, date]:
    """Annuity, forward par rate and adjusted end of an OIS from ``start``."""
    c = CONVENTIONS[ccy]
    curve = mkt.curves[ccy]
    periods = schedule(start, end, c["freq"], c["cal"])
    annuity = sum(year_fraction(p.start, p.end, c["day_count"]) * curve.df_at(p.end) for p in periods)
    adj_end = periods[-1].end
    return annuity, (curve.df_at(start) - curve.df_at(adj_end)) / annuity, adj_end


def bachelier(f: float, k: float, vol: float, t: float, payer: bool) -> float:
    """Undiscounted normal-model option on a rate, per unit annuity."""
    w = 1.0 if payer else -1.0
    if t <= 0 or vol <= 0:
        return max(w * (f - k), 0.0)
    sd = vol * sqrt(t)
    d = (f - k) / sd
    return w * (f - k) * norm.cdf(w * d) + sd * norm.pdf(d)


def swaption_tenor(trade: Swaption) -> float:
    return round((trade.end - trade.start).days / 365.25, 2)


def price_swaption(trade: Swaption, mkt: Market, vol_bp: float | None = None) -> float:
    """Bachelier (normal) model, physically settled into the OIS, valued with
    the OIS curve's annuity; vol from the expiry x tenor normal-vol grid."""
    if trade.expiry < mkt.asof:
        return 0.0
    t_exp = t_of(mkt.asof, trade.expiry)
    annuity, fwd, _ = forward_swap(mkt, trade.ccy, trade.start, trade.end)
    if vol_bp is None:
        vol_bp = mkt.swaption_vol[trade.ccy].vol_bp(t_exp, swaption_tenor(trade))
    sign = 1.0 if trade.long else -1.0
    return sign * trade.notional * annuity * bachelier(fwd, trade.strike, vol_bp / 1e4, t_exp, trade.payer)


XCCY_FREQ = 3  # months, both legs


def overnight_leg_with_exchanges(mkt: Market, ccy: str, notional: float, spread: float, start: date, end: date) -> float:
    """PV of receiving a compounded overnight leg (+ simple spread) with the
    notional paid at start (if still to come) and received at maturity."""
    c = CONVENTIONS[ccy]
    curve = mkt.curves[ccy]
    asof = mkt.asof
    periods = schedule(start, end, XCCY_FREQ, c["cal"])
    pv = 0.0
    for p in periods:
        if p.end <= asof:
            continue
        df_end = curve.df_at(p.end)
        pv += notional * spread * year_fraction(p.start, p.end, c["day_count"]) * df_end
        if p.start >= asof:
            pv += notional * (curve.df_at(p.start) - df_end)
        else:
            a, _ = realised_compounding(mkt.fixings[c["index"]], p.start, asof, c["cal"], c["day_count"])
            pv += notional * (a - df_end)
    if start > asof:
        pv -= notional * curve.df_at(start)
    end_adj = periods[-1].end
    if end_adj > asof:
        pv += notional * curve.df_at(end_adj)
    return pv


def price_xccy(trade: XCCYSwap, mkt: Market) -> float:
    """PV in USD. Single-curve per currency, so the model carries no
    cross-currency basis: the value comes from the spread, rates and the move
    in spot since the notionals were fixed."""
    gbp = overnight_leg_with_exchanges(mkt, "GBP", trade.notional, trade.spread, trade.start, trade.end)
    usd = overnight_leg_with_exchanges(mkt, "USD", trade.notional_usd, 0.0, trade.start, trade.end)
    value = gbp * mkt.spot[trade.pair] - usd
    return value if trade.receive_gbp else -value


def price(trade: Trade, mkt: Market) -> float:
    if isinstance(trade, OISSwap):
        return price_ois(trade, mkt)
    if isinstance(trade, FXForward):
        return price_fx_forward(trade, mkt)
    if isinstance(trade, FXOption):
        return price_fx_option(trade, mkt)
    if isinstance(trade, Swaption):
        return price_swaption(trade, mkt)
    if isinstance(trade, XCCYSwap):
        return price_xccy(trade, mkt)
    raise TypeError(type(trade))


def pv_ccy(trade: Trade) -> str:
    return trade.ccy if isinstance(trade, OISSwap | Swaption) else trade.pair[3:]


def to_usd(value: float, ccy: str, mkt: Market) -> float:
    return value * mkt.spot["GBPUSD"] if ccy == "GBP" else value


# --- Sensitivities (bump and reprice) --------------------------------------------


def sensitivities(trade: Trade, mkt: Market) -> dict[str, float]:
    """PV01 per currency (+1bp parallel zero shift), FX delta (+1% spot) and
    vega (+1 vol point; +1bp normal vol for swaptions), all in the trade's PV
    currency."""
    base = price(trade, mkt)
    out = {}
    for ccy in ("GBP", "USD"):
        out[f"pv01_{ccy}"] = price(trade, mkt.bump_curve(ccy, 1.0)) - base
    if isinstance(trade, FXForward | FXOption | XCCYSwap):
        out["fx_delta_1pct"] = price(trade, mkt.bump_spot(trade.pair, 0.01)) - base
    if isinstance(trade, FXOption):
        out["vega_1pt"] = price(trade, mkt.bump_vol(trade.pair, 1.0)) - base
    if isinstance(trade, Swaption):
        out["vega_1bp"] = price(trade, mkt.bump_swaption_vol(trade.ccy, 1.0)) - base
    return out
