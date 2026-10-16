from datetime import date

import numpy as np
import pandas as pd

from otc_valuation_desk import qc


def _series(values, start=date(2026, 10, 5)):
    idx = pd.bdate_range(start, periods=len(values)).date
    return pd.Series(values, index=idx, name="X")


def test_stale_value_is_flagged():
    out = qc.check_stale(_series([4.0, 4.1, 4.1, 4.1, 4.1, 4.1]), "src", stale_days=5)
    assert [e.check for e in out] == ["stale"]


def test_jump_is_flagged_in_bp():
    out = qc.check_jumps(_series([4.00, 4.02, 4.30]), "src", threshold=10, unit="bp")
    assert len(out) == 1 and out[0].obs_date == _series([0, 0, 0]).index[2]


def test_missing_business_day_is_flagged():
    s = _series([4.0, 4.0, 4.0]).drop(_series([0, 0, 0]).index[1])
    out = qc.check_missing(s, "src", date(2026, 10, 5), date(2026, 10, 8), "GBP")
    assert [e.obs_date for e in out] == [date(2026, 10, 6)]


def test_inverted_discount_curve_fails():
    t = np.array([1.0, 2.0, 3.0])
    out = qc.check_zero_curve(t, np.array([4.0, 4.0, 1.0]), "src", date(2026, 10, 15))
    assert any(e.severity == "FAIL" for e in out)
