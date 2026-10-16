"""The market state for one valuation date: curves, fixings, FX spot, vols."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

import numpy as np
import pandas as pd

from . import curves as C
from . import data as D

# GBPUSD ATM implied vols by expiry in years. SYNTHETIC: no free FX vol source
# exists; levels are set to a plausible range and labelled synthetic in every
# report.
GBPUSD_ATM_VOL = {1 / 12: 0.075, 0.25: 0.078, 0.5: 0.080, 1.0: 0.083, 2.0: 0.086}


@dataclass(frozen=True)
class FXVol:
    """ATM vol term structure, linear in total variance between pillars."""

    pillars: dict[float, float]

    def vol(self, t: float) -> float:
        ts = np.array(sorted(self.pillars))
        vs = np.array([self.pillars[k] for k in ts])
        w = np.interp(
            t, ts, vs**2 * ts, left=vs[0] ** 2 * ts[0], right=vs[-1] ** 2 * ts[-1]
        )
        if t <= ts[0]:
            return float(vs[0])
        if t >= ts[-1]:
            return float(vs[-1])
        return float(np.sqrt(w / t))

    def shifted(self, vol_pts: float) -> "FXVol":
        return FXVol({k: v + vol_pts / 100 for k, v in self.pillars.items()})


@dataclass(frozen=True)
class Market:
    asof: date
    curves: dict[str, C.DiscountCurve]
    fixings: dict[str, pd.Series]  # index name -> percent by date
    spot: dict[str, float]
    fx_vol: dict[str, FXVol]

    def bump_curve(self, ccy: str, bp: float) -> "Market":
        return replace(self, curves={**self.curves, ccy: self.curves[ccy].shifted(bp)})

    def bump_spot(self, pair: str, rel: float) -> "Market":
        return replace(self, spot={**self.spot, pair: self.spot[pair] * (1 + rel)})

    def bump_vol(self, pair: str, vol_pts: float) -> "Market":
        return replace(
            self, fx_vol={**self.fx_vol, pair: self.fx_vol[pair].shifted(vol_pts)}
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
        fx_vol={"GBPUSD": FXVol(GBPUSD_ATM_VOL)},
    )


def boe_interpolated(mkt: Market) -> Market:
    """The same market with the GBP curve read straight off the Bank of
    England zero curve (its smooth interpolation) instead of the log-linear
    bootstrap. Used to replay a dealer whose curve interpolates differently."""
    boe = D.boe_ois_curve(mkt.asof.strftime("%Y-%m")).loc[mkt.asof]
    gbp = C.from_zero_rates(mkt.asof, "GBP", boe.index.values, boe.values, "BoE OIS (dense)")
    gbp.quotes = mkt.curves["GBP"].quotes
    return replace(mkt, curves={**mkt.curves, "GBP": gbp})
