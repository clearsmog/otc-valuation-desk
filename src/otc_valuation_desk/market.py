"""The market state for one valuation date: curves, fixings, FX spot, vols."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date

import numpy as np
import pandas as pd
from scipy.stats import norm

from . import curves as C
from . import data as D

# GBPUSD smile pillars by expiry in years: (ATM, 25-delta risk reversal,
# 25-delta butterfly), decimals. SYNTHETIC: no free FX vol source exists;
# levels are set to a plausible range and labelled synthetic in every report.
# Negative risk reversals: GBP puts over GBP calls.
GBPUSD_SMILE = {
    1 / 12: (0.075, -0.0060, 0.0015),
    0.25: (0.078, -0.0075, 0.0020),
    0.5: (0.080, -0.0085, 0.0024),
    1.0: (0.083, -0.0095, 0.0028),
    2.0: (0.086, -0.0100, 0.0030),
}

# Normal (bp) swaption vols, expiry (y) x underlying tenor (y). SYNTHETIC.
SWAPTION_NVOL_BP = {
    "GBP": {
        "expiries": (0.25, 0.5, 1.0, 2.0, 5.0),
        "tenors": (1.0, 2.0, 5.0, 10.0),
        "vols": ((92, 95, 96, 93), (95, 97, 97, 94), (98, 99, 98, 95), (99, 99, 97, 94), (96, 96, 94, 91)),
    },
    "USD": {
        "expiries": (0.25, 0.5, 1.0, 2.0, 5.0),
        "tenors": (1.0, 2.0, 5.0, 10.0),
        "vols": ((105, 110, 112, 108), (108, 112, 113, 109), (112, 114, 113, 109), (113, 113, 111, 107), (108, 108, 106, 103)),
    },
}


def _d1_d2(f: float, k: float, vol: float, t: float) -> tuple[float, float]:
    sd = vol * np.sqrt(t)
    d1 = (np.log(f / k) + 0.5 * sd * sd) / sd
    return d1, d1 - sd


@dataclass(frozen=True)
class FXSmile:
    """FX implied vol smile.

    Across expiries: ATM interpolated linearly in total variance, risk
    reversal and butterfly linearly in time, flat outside the pillars.
    Within an expiry: three pillar strikes (25-delta put, ATM delta-neutral
    straddle, 25-delta call; forward deltas) and vanna-volga interpolation in
    strike (Castagna-Mercurio second-order approximation). The pillar vols use
    the smile-strangle shortcut: sigma_25C/P = ATM + BF +/- RR/2.
    """

    pillars: dict[float, tuple[float, float, float]]
    atm_shift: float = 0.0  # parallel shift, decimals

    def params(self, t: float) -> tuple[float, float, float]:
        ts = np.array(sorted(self.pillars))
        atm = np.array([self.pillars[k][0] for k in ts])
        rr = np.array([self.pillars[k][1] for k in ts])
        bf = np.array([self.pillars[k][2] for k in ts])
        tc = min(max(t, ts[0]), ts[-1])
        w = np.interp(tc, ts, atm**2 * ts)
        return float(np.sqrt(w / tc)) + self.atm_shift, float(np.interp(tc, ts, rr)), float(np.interp(tc, ts, bf))

    def vol(self, t: float) -> float:
        """ATM vol for expiry ``t``."""
        return self.params(t)[0]

    def pillar_strikes(self, t: float, fwd: float) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        atm, rr, bf = self.params(t)
        s_c, s_p = atm + bf + rr / 2, atm + bf - rr / 2
        sq = np.sqrt(t)
        k_atm = fwd * np.exp(0.5 * atm * atm * t)
        k_c = fwd * np.exp(-norm.ppf(0.25) * s_c * sq + 0.5 * s_c * s_c * t)
        k_p = fwd * np.exp(-norm.ppf(0.75) * s_p * sq + 0.5 * s_p * s_p * t)
        return (k_p, k_atm, k_c), (s_p, atm, s_c)

    def vol_at(self, t: float, strike: float, fwd: float) -> float:
        (k1, k2, k3), (s1, s2, s3) = self.pillar_strikes(t, fwd)
        lk = np.log
        y1 = lk(k2 / strike) * lk(k3 / strike) / (lk(k2 / k1) * lk(k3 / k1))
        y2 = lk(strike / k1) * lk(k3 / strike) / (lk(k2 / k1) * lk(k3 / k2))
        y3 = lk(strike / k1) * lk(strike / k2) / (lk(k3 / k1) * lk(k3 / k2))
        first = y1 * s1 + y2 * s2 + y3 * s3 - s2
        d1, d2 = _d1_d2(fwd, strike, s2, t)
        a1, b1 = _d1_d2(fwd, k1, s2, t)
        a3, b3 = _d1_d2(fwd, k3, s2, t)
        second = y1 * a1 * b1 * (s1 - s2) ** 2 + y3 * a3 * b3 * (s3 - s2) ** 2
        dd = d1 * d2
        disc = s2 * s2 + dd * (2 * s2 * first + second)
        if abs(dd) < 1e-12 or disc < 0:
            return float(s2 + first)  # first-order fallback
        return float(s2 + (-s2 + np.sqrt(disc)) / dd)

    def shifted(self, vol_pts: float) -> "FXSmile":
        return FXSmile(self.pillars, self.atm_shift + vol_pts / 100)


@dataclass(frozen=True)
class NormalVolGrid:
    """Swaption normal vols (bp), bilinear in expiry and tenor, flat outside."""

    expiries: tuple[float, ...]
    tenors: tuple[float, ...]
    vols: tuple[tuple[float, ...], ...]
    shift_bp: float = 0.0

    def vol_bp(self, t_exp: float, tenor: float) -> float:
        by_exp = [np.interp(tenor, self.tenors, row) for row in self.vols]
        return float(np.interp(t_exp, self.expiries, by_exp)) + self.shift_bp

    def shifted(self, bp: float) -> "NormalVolGrid":
        return replace(self, shift_bp=self.shift_bp + bp)


@dataclass(frozen=True)
class Market:
    asof: date
    curves: dict[str, C.DiscountCurve]
    fixings: dict[str, pd.Series]  # index name -> percent by date
    spot: dict[str, float]
    fx_vol: dict[str, FXSmile]
    swaption_vol: dict[str, NormalVolGrid] = field(default_factory=dict)

    def bump_curve(self, ccy: str, bp: float) -> "Market":
        return replace(self, curves={**self.curves, ccy: self.curves[ccy].shifted(bp)})

    def bump_spot(self, pair: str, rel: float) -> "Market":
        return replace(self, spot={**self.spot, pair: self.spot[pair] * (1 + rel)})

    def bump_vol(self, pair: str, vol_pts: float) -> "Market":
        return replace(
            self, fx_vol={**self.fx_vol, pair: self.fx_vol[pair].shifted(vol_pts)}
        )

    def bump_swaption_vol(self, ccy: str, bp: float) -> "Market":
        return replace(
            self, swaption_vol={**self.swaption_vol, ccy: self.swaption_vol[ccy].shifted(bp)}
        )


def build_market(
    asof: date,
    fixings_start: date = date(2024, 10, 1),
    fixings_end: date = date(2026, 10, 16),
) -> Market:
    """Load the snapshot for ``asof`` and build the curves."""
    boe = D.boe_ois_curve(asof.strftime("%Y-%m")).loc[asof]
    gbp_ref = C.from_zero_rates(asof, "GBP", boe.index.values, boe.values, "BoE OIS")
    gbp = C.bootstrap(asof, "GBP", C.par_quotes(gbp_ref), "GBP SONIA OIS")
    ust = D.treasury_par(asof.year).loc[asof].to_dict()
    usd = C.bootstrap(
        asof, "USD", C.treasury_proxy_quotes(ust), "USD SOFR OIS (UST par proxy)"
    )
    fx = D.ecb_fx(date(2026, 9, 1), fixings_end)
    return Market(
        asof=asof,
        curves={"GBP": gbp, "USD": usd},
        fixings={
            "SONIA": D.sonia_fixings(fixings_start, fixings_end),
            "SOFR": D.sofr_fixings(fixings_start, fixings_end),
        },
        spot={"GBPUSD": float(fx.loc[asof, "GBPUSD"])},
        fx_vol={"GBPUSD": FXSmile(GBPUSD_SMILE)},
        swaption_vol={c: NormalVolGrid(**g) for c, g in SWAPTION_NVOL_BP.items()},
    )


def boe_interpolated(mkt: Market) -> Market:
    """The same market with the GBP curve read straight off the Bank of
    England zero curve (its smooth interpolation) instead of the log-linear
    bootstrap. Used to replay a dealer whose curve interpolates differently."""
    boe = D.boe_ois_curve(mkt.asof.strftime("%Y-%m")).loc[mkt.asof]
    gbp = C.from_zero_rates(mkt.asof, "GBP", boe.index.values, boe.values, "BoE OIS (dense)")
    gbp.quotes = mkt.curves["GBP"].quotes
    return replace(mkt, curves={**mkt.curves, "GBP": gbp})
