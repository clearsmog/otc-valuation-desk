from otc_valuation_desk import reference as R
from otc_valuation_desk.cycle import REF_TOL, valuation_table


def test_own_engine_agrees_with_quantlib(mkt, trades):
    df = valuation_table(trades, mkt, R.QLMarket(mkt))
    bad = df[df["ref_check"] != "OK"]
    assert bad.empty, bad[["trade_id", "own_minus_ql", "diff_in_risk_units"]]
    assert set(REF_TOL) == set(df["product"])
