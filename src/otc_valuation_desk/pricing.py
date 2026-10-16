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
from .trades import FXForward, FXOption, OISSwap, Trade

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
    sigma = mkt.fx_vol[trade.pair].vol(t_exp) if vol is None else vol
    f = fx_forward_rate(mkt, trade.pair, trade.delivery)
    df = mkt.curves[trade.pair[3:]].df_at(trade.delivery)
    sign = 1.0 if trade.long else -1.0
    return (
        sign
        * trade.notional
        * df
        * black_forward(f, trade.strike, sigma, t_exp, trade.call)
    )


def price(trade: Trade, mkt: Market) -> float:
    if isinstance(trade, OISSwap):
        return price_ois(trade, mkt)
    if isinstance(trade, FXForward):
        return price_fx_forward(trade, mkt)
    if isinstance(trade, FXOption):
        return price_fx_option(trade, mkt)
    raise TypeError(type(trade))


def pv_ccy(trade: Trade) -> str:
    return trade.ccy if isinstance(trade, OISSwap) else trade.pair[3:]


def to_usd(value: float, ccy: str, mkt: Market) -> float:
    return value * mkt.spot["GBPUSD"] if ccy == "GBP" else value


# --- Sensitivities (bump and reprice) --------------------------------------------


def sensitivities(trade: Trade, mkt: Market) -> dict[str, float]:
    """PV01 per currency (+1bp parallel zero shift), FX delta (+1% spot) and
    vega (+1 vol point), all in the trade's PV currency."""
    base = price(trade, mkt)
    out = {}
    for ccy in ("GBP", "USD"):
        out[f"pv01_{ccy}"] = price(trade, mkt.bump_curve(ccy, 1.0)) - base
    if not isinstance(trade, OISSwap):
        out["fx_delta_1pct"] = price(trade, mkt.bump_spot(trade.pair, 0.01)) - base
    if isinstance(trade, FXOption):
        out["vega_1pt"] = price(trade, mkt.bump_vol(trade.pair, 1.0)) - base
    return out
