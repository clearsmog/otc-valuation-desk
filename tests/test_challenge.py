from otc_valuation_desk import challenge as CH
from otc_valuation_desk import marks as M
from conftest import PRIOR


def test_attribution_recovers_every_planted_cause(mkt, trades):
    marks, key = M.generate_marks(trades, mkt, PRIOR)
    planted = {k["trade_id"]: k["cause"] for k in key}
    results = CH.run_challenges(trades, marks, mkt, PRIOR)
    for r in results:
        assert (r.cause or "NONE") == planted[r.trade_id], (r.trade_id, r.status, r.detail)


def test_confirmed_causes_close_the_gap(mkt, trades):
    marks, _ = M.generate_marks(trades, mkt, PRIOR)
    for r in CH.run_challenges(trades, marks, mkt, PRIOR):
        if r.status == "EXPLAINED":
            assert abs(r.residual) <= min(r.tolerance, 0.1 * abs(r.difference))


def test_untested_gap_is_unexplained(mkt, trades):
    swap = next(t for t in trades if t.trade_id == "NBM-IRS-007")
    own = CH.P.price(swap, mkt)
    status, cause, _, _ = CH.attribute(swap, own + 0.37 * own, mkt, prior=None)
    assert (status, cause) == ("UNEXPLAINED", "UNEXPLAINED")
