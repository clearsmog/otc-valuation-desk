import numpy as np

from otc_valuation_desk import curves as C
from otc_valuation_desk import data as D
from conftest import ASOF


def test_bootstrap_reprices_every_quote(mkt):
    for ccy, curve in mkt.curves.items():
        for m, r in curve.quotes:
            assert abs(C.par_ois_rate(curve, m) - r) < 1e-10, (ccy, m)


def test_gbp_round_trip_matches_bank_of_england_curve(mkt):
    boe = D.boe_ois_curve("2026-10").loc[ASOF]
    ref = C.from_zero_rates(ASOF, "GBP", boe.index.values, boe.values, "BoE")
    gbp = mkt.curves["GBP"]
    # at quote maturities the curves agree; between sparse long pillars the
    # log-linear interpolation drifts from the BoE spline by a fraction of a bp
    for t in (0.5, 1, 2, 3, 5):
        assert abs(gbp.zero(t) - ref.zero(t)) * 1e4 < 0.1
    for t in (10, 15, 20, 25):
        assert abs(gbp.zero(t) - ref.zero(t)) * 1e4 < 0.5


def test_discount_factors_fall_with_maturity(mkt):
    for curve in mkt.curves.values():
        dfs = [curve.df(t) for t in np.linspace(0.1, 30, 300)]
        assert all(a > b for a, b in zip(dfs, dfs[1:]))
