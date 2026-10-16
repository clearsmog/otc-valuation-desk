from datetime import date

from otc_valuation_desk.monthend import explain


def test_explain_ties_out_and_orders_agree_on_totals():
    per_trade, summary, notes = explain(date(2026, 8, 28), date(2026, 9, 30))
    s = summary.set_index("step")
    assert abs(per_trade["check"]).max() < 1e-6
    total_move = s.loc["value at T1", "usd"] - s.loc["value at T0", "usd"]
    assert abs(sum(s.loc[k, "usd"] for k in ("carry", "gbp_rates", "usd_rates", "fx_spot", "vols", "new_trades")) - total_move) < 1e-6
    # the order changes the split, not the total
    assert abs(sum(s.loc[k, "reverse_order"] for k in ("carry", "gbp_rates", "usd_rates", "fx_spot", "vols", "new_trades")) - total_move) < 1e-6
    assert set(per_trade.loc[per_trade["status"].str.startswith("new"), "trade_id"]) == {"NBM-FXF-005", "NBM-SWO-004"}
