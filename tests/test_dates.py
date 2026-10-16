from datetime import date

from otc_valuation_desk.dates import add_business_days, adjust, schedule, year_fraction


def test_modified_following_stays_in_month():
    # Sat 31 Oct 2026: following would roll to November, so MF rolls back
    assert adjust(date(2026, 10, 31), "GBP", "MF") == date(2026, 10, 30)
    assert adjust(date(2026, 10, 31), "GBP", "F") == date(2026, 11, 2)


def test_uk_bank_holiday_skipped():
    # Christmas and Boxing Day 2026 fall Fri/Sat; 28 Dec is the substitute day
    assert add_business_days(date(2026, 12, 24), 1, "GBP") == date(2026, 12, 29)


def test_schedule_backward_with_front_stub():
    periods = schedule(date(2026, 1, 15), date(2028, 7, 17), 12, "GBP")
    assert periods[0].start == date(2026, 1, 15)
    assert periods[-1].end == date(2028, 7, 17)
    assert len(periods) == 3  # short front stub, then two annual periods


def test_day_counts():
    assert year_fraction(date(2026, 1, 1), date(2027, 1, 1), "ACT/365F") == 1.0
    assert abs(year_fraction(date(2026, 1, 1), date(2027, 1, 1), "ACT/360") - 365 / 360) < 1e-12
