from dataclasses import replace
from datetime import date

import pandas as pd

from otc_valuation_desk import pricing as P
from otc_valuation_desk.curves import ois_dates, par_ois_rate
from otc_valuation_desk.trades import FXForward, FXOption, OISSwap


def test_spot_ois_at_par_is_worth_zero(mkt):
    start, end = ois_dates(mkt.asof, "GBP", 60)
    swap = OISSwap("T", "X", "GBP", 1e8, par_ois_rate(mkt.curves["GBP"], 60), True, start, end)
    assert abs(P.price(swap, mkt)) < 1.0


def test_payer_plus_receiver_is_zero(mkt, trades):
    swap = next(t for t in trades if t.trade_id == "NBM-IRS-001")
    assert abs(P.price(swap, mkt) + P.price(replace(swap, pay_fixed=False), mkt)) < 1e-6


def test_realised_compounding_with_flat_fixings():
    fixings = pd.Series({date(2026, 10, d): 4.0 for d in range(1, 16)})
    factor, filled = P.realised_compounding(fixings, date(2026, 10, 5), date(2026, 10, 12), "GBP", "ACT/365F")
    # Mon-Fri, with Friday's fixing accruing over the weekend: 7 days at 4%
    expected = (1 + 0.04 / 365) ** 4 * (1 + 0.04 * 3 / 365)
    assert abs(factor - expected) < 1e-14 and filled == 0


def test_fx_forward_at_forward_rate_is_worth_zero(mkt):
    d = date(2027, 4, 19)
    fwd = FXForward("T", "X", "GBPUSD", 1e7, P.fx_forward_rate(mkt, "GBPUSD", d), True, d)
    assert abs(P.price(fwd, mkt)) < 1e-6


def test_put_call_parity(mkt):
    exp, dlv = date(2027, 4, 15), date(2027, 4, 19)
    k = 1.33
    call = FXOption("C", "X", "GBPUSD", 1e7, k, True, True, exp, dlv)
    put = replace(call, trade_id="P", call=False)
    fwd = FXForward("F", "X", "GBPUSD", 1e7, k, True, dlv)
    assert abs(P.price(call, mkt) - P.price(put, mkt) - P.price(fwd, mkt)) < 1e-6
