"""Discount curves and the OIS bootstrap.

One discount curve per currency (single-curve OIS: the overnight index both
projects and discounts, as for collateralised SONIA and SOFR swaps).

Time axis: ACT/365F year fractions from the curve date. Interpolation: linear
in log discount factor (piecewise-constant forwards), flat-forward
extrapolation past the last pillar.

GBP: par OIS quotes are derived from the Bank of England's published zero
curve and bootstrapped back; the round trip is the curve test.
USD: no free SOFR swap quotes exist, so the US Treasury par curve is used as a
**proxy** for SOFR OIS par rates. The swap spread is ignored and the curve is
labelled as a proxy wherever it is reported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
from scipy.optimize import brentq

from .dates import add_business_days, add_months, adjust, schedule, year_fraction

CONVENTIONS = {
    # fixed and floating accrual day count, calendar, spot lag (business days),
    # fixed-leg frequency in months
    "GBP": {
        "day_count": "ACT/365F",
        "cal": "GBP",
        "spot_lag": 0,
        "freq": 12,
        "index": "SONIA",
    },
    "USD": {
        "day_count": "ACT/360",
        "cal": "USD",
        "spot_lag": 2,
        "freq": 12,
        "index": "SOFR",
    },
}

QUOTE_TENORS_M = [1, 2, 3, 6, 9, 12, 18, 24, 36, 48, 60, 84, 120, 180, 240, 300]


def t_of(asof: date, d: date) -> float:
    return year_fraction(asof, d, "ACT/365F")


@dataclass
class DiscountCurve:
    asof: date
    ccy: str
    times: np.ndarray  # includes 0.0
    log_df: np.ndarray  # log discount factors at ``times``
    label: str = ""
    quotes: list[tuple[int, float]] = field(default_factory=list)

    def df(self, t: float) -> float:
        t = max(t, 0.0)
        ts, ld = self.times, self.log_df
        if t <= ts[-1]:
            return float(np.exp(np.interp(t, ts, ld)))
        slope = (ld[-1] - ld[-2]) / (ts[-1] - ts[-2])
        return float(np.exp(ld[-1] + slope * (t - ts[-1])))

    def df_at(self, d: date) -> float:
        return self.df(t_of(self.asof, d))

    def zero(self, t: float) -> float:
        """Continuously compounded zero rate (decimal)."""
        return -np.log(self.df(t)) / t if t > 0 else -self.log_df[1] / self.times[1]

    def forward(self, d1: date, d2: date, day_count: str) -> float:
        return (self.df_at(d1) / self.df_at(d2) - 1.0) / year_fraction(
            d1, d2, day_count
        )

    def shifted(self, bp: float) -> "DiscountCurve":
        """Parallel shift of the continuously compounded zero curve."""
        return DiscountCurve(
            self.asof,
            self.ccy,
            self.times,
            self.log_df - bp * 1e-4 * self.times,
            f"{self.label} {bp:+g}bp",
        )


def from_zero_rates(
    asof: date, ccy: str, years: np.ndarray, zeros_pct: np.ndarray, label: str
) -> DiscountCurve:
    years = np.asarray(years, float)
    z = np.asarray(zeros_pct, float) / 100.0
    mask = ~np.isnan(z)
    t = np.concatenate([[0.0], years[mask]])
    return DiscountCurve(
        asof, ccy, t, np.concatenate([[0.0], -z[mask] * years[mask]]), label
    )


# --- OIS par rates --------------------------------------------------------------


def ois_dates(asof: date, ccy: str, tenor_m: int) -> tuple[date, date]:
    c = CONVENTIONS[ccy]
    start = (
        add_business_days(asof, c["spot_lag"], c["cal"])
        if c["spot_lag"]
        else adjust(asof, c["cal"], "F")
    )
    # unadjusted maturity: the schedule rolls back from it and adjusts each
    # date, so intermediate dates sit on the anniversary, not on the rolled end
    return start, add_months(start, tenor_m)


def par_ois_rate(curve: DiscountCurve, tenor_m: int) -> float:
    """Spot-starting OIS par rate. The compounded floating leg telescopes to
    df(start) - df(end); payment lag is zero."""
    c = CONVENTIONS[curve.ccy]
    start, unadj_end = ois_dates(curve.asof, curve.ccy, tenor_m)
    periods = schedule(start, unadj_end, c["freq"], c["cal"])
    end = periods[-1].end
    annuity = sum(
        year_fraction(p.start, p.end, c["day_count"]) * curve.df_at(p.end)
        for p in periods
    )
    return (curve.df_at(start) - curve.df_at(end)) / annuity


def par_quotes(
    curve: DiscountCurve, tenors_m: list[int] = QUOTE_TENORS_M
) -> list[tuple[int, float]]:
    last_t = curve.times[-1]
    out = []
    for m in tenors_m:
        if m / 12 <= last_t + 1e-9:
            out.append((m, par_ois_rate(curve, m)))
    return out


# --- Bootstrap ------------------------------------------------------------------


def bootstrap(
    asof: date, ccy: str, quotes: list[tuple[int, float]], label: str
) -> DiscountCurve:
    """Sequential bootstrap: each quote adds one pillar at its maturity and the
    pillar's discount factor is solved so the swap reprices to par.

    Log-linear interpolation is local, so payments before the previous pillar
    are unaffected by the new unknown.
    """
    c = CONVENTIONS[ccy]
    times, logs = [0.0], [0.0]
    for tenor_m, rate in sorted(quotes):
        start, unadj_end = ois_dates(asof, ccy, tenor_m)
        periods = schedule(start, unadj_end, c["freq"], c["cal"])
        end = periods[-1].end
        t_end = t_of(asof, end)

        def pv(log_df_end: float) -> float:
            curve = DiscountCurve(
                asof, ccy, np.array(times + [t_end]), np.array(logs + [log_df_end])
            )
            annuity = sum(
                year_fraction(p.start, p.end, c["day_count"]) * curve.df_at(p.end)
                for p in periods
            )
            return curve.df_at(start) - curve.df_at(end) - rate * annuity

        guess = -rate * t_end
        sol = brentq(pv, guess - 0.5, guess + 0.5, xtol=1e-14)
        times.append(t_end)
        logs.append(sol)
    return DiscountCurve(
        asof, ccy, np.array(times), np.array(logs), label, list(quotes)
    )


def treasury_proxy_quotes(par_row: dict[float, float]) -> list[tuple[int, float]]:
    """US Treasury par yields (percent) as proxy USD OIS par rates (decimal)."""
    return [
        (int(round(t * 12)), r / 100.0)
        for t, r in sorted(par_row.items())
        if not np.isnan(r)
    ]
