from dataclasses import replace

import numpy as np

from otc_valuation_desk import pricing as P


def test_smile_reproduces_pillar_vols(mkt):
    smile = mkt.fx_vol["GBPUSD"]
    for t in (0.25, 0.5, 1.0, 2.0):
        strikes, vols = smile.pillar_strikes(t, 1.32)
        for k, v in zip(strikes, vols):
            assert abs(smile.vol_at(t, k, 1.32) - v) < 1e-10


def test_smile_is_skewed_to_gbp_puts(mkt):
    smile = mkt.fx_vol["GBPUSD"]
    assert smile.vol_at(1.0, 1.22, 1.32) > smile.vol_at(1.0, 1.42, 1.32)
    # convex: the wings sit above the minimum
    vols = [smile.vol_at(1.0, k, 1.32) for k in np.linspace(1.15, 1.50, 36)]
    assert vols[0] > min(vols) and vols[-1] > min(vols)


def test_payer_minus_receiver_is_forward_swap(mkt, trades):
    payer = next(t for t in trades if t.trade_id == "NBM-SWO-001")
    receiver = replace(payer, payer=False)
    annuity, fwd, _ = P.forward_swap(mkt, payer.ccy, payer.start, payer.end)
    parity = payer.notional * annuity * (fwd - payer.strike)
    assert abs(P.price(payer, mkt) - P.price(receiver, mkt) - parity) < 1e-6
