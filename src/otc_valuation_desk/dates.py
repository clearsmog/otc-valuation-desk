"""Calendars, business-day adjustment, schedules and day counts.

Kept independent of QuantLib so that the QuantLib reference valuation is a
genuine second opinion rather than the same code run twice.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache

import holidays


@lru_cache(maxsize=None)
def _holiday_set(cal: str, year: int) -> frozenset[date]:
    if cal == "GBP":
        return frozenset(holidays.country_holidays("GB", subdiv="ENG", years=year))
    if cal == "USD":
        # SOFR follows the US government securities calendar; US federal
        # holidays are the close approximation available offline.
        return frozenset(holidays.country_holidays("US", years=year))
    if cal == "GBP+USD":
        return _holiday_set("GBP", year) | _holiday_set("USD", year)
    raise ValueError(f"unknown calendar {cal!r}")


def is_business_day(d: date, cal: str) -> bool:
    return d.weekday() < 5 and d not in _holiday_set(cal, d.year)


def adjust(d: date, cal: str, convention: str = "MF") -> date:
    """Following ("F") or modified following ("MF") adjustment."""
    if convention not in ("F", "MF"):
        raise ValueError(convention)
    out = d
    while not is_business_day(out, cal):
        out += timedelta(days=1)
    if convention == "MF" and out.month != d.month:
        out = d
        while not is_business_day(out, cal):
            out -= timedelta(days=1)
    return out


def add_business_days(d: date, n: int, cal: str) -> date:
    step = 1 if n >= 0 else -1
    out = d
    for _ in range(abs(n)):
        out += timedelta(days=step)
        while not is_business_day(out, cal):
            out += timedelta(days=step)
    return out


def add_months(d: date, months: int) -> date:
    """Unadjusted month arithmetic with end-of-month clipping."""
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def business_days(start: date, end: date, cal: str) -> list[date]:
    """Business days in [start, end)."""
    out, d = [], start
    while d < end:
        if is_business_day(d, cal):
            out.append(d)
        d += timedelta(days=1)
    return out


def year_fraction(d1: date, d2: date, day_count: str) -> float:
    days = (d2 - d1).days
    if day_count == "ACT/365F":
        return days / 365.0
    if day_count == "ACT/360":
        return days / 360.0
    raise ValueError(f"unknown day count {day_count!r}")


@dataclass(frozen=True)
class Period:
    start: date
    end: date


def schedule(start: date, end: date, freq_months: int, cal: str) -> list[Period]:
    """Backward-generated, modified-following adjusted accrual periods.

    A period shorter than the frequency appears at the front (short stub), the
    standard for swaps rolled from the maturity date.
    """
    unadj = [end]
    k = 1
    while True:
        d = add_months(end, -freq_months * k)
        if d <= start + timedelta(days=7):  # avoid a stub of a few days
            break
        unadj.append(d)
        k += 1
    unadj.append(start)
    unadj.reverse()
    adj = [unadj[0]] + [adjust(d, cal) for d in unadj[1:]]
    return [Period(a, b) for a, b in zip(adj[:-1], adj[1:])]
