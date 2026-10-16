"""Market-data quality control.

Runs before any curve is built. Each check returns ``Exception_`` records; a
FAIL blocks the input from use, a WARN is reported and the value is used.

Checks:
- missing: a business day with no value (or NaN) inside the look-back window
- stale: value unchanged for ``stale_days`` consecutive observations
- jump: day-on-day move beyond a threshold (in bp for rates, % for FX)
- curve shape: non-increasing discount factors or negative instantaneous
  forwards implied by a zero curve
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from .dates import business_days


@dataclass(frozen=True)
class QCException:
    source: str
    field: str
    obs_date: date
    check: str
    severity: str  # "FAIL" or "WARN"
    detail: str


def check_missing(
    series: pd.Series, source: str, start: date, end: date, cal: str
) -> list[QCException]:
    expected = business_days(start, end, cal)
    have = {d for d, v in series.items() if pd.notna(v)}
    return [
        QCException(
            source, str(series.name), d, "missing", "WARN", "no value on a business day"
        )
        for d in expected
        if d not in have
    ]


def check_stale(
    series: pd.Series, source: str, stale_days: int = 5
) -> list[QCException]:
    s = series.dropna()
    out, run = [], 1
    for i in range(1, len(s)):
        run = run + 1 if s.iloc[i] == s.iloc[i - 1] else 1
        if run == stale_days:
            out.append(
                QCException(
                    source,
                    str(s.name),
                    s.index[i],
                    "stale",
                    "WARN",
                    f"unchanged at {s.iloc[i]} for {stale_days} observations",
                )
            )
    return out


def check_jumps(
    series: pd.Series, source: str, threshold: float, unit: str
) -> list[QCException]:
    """``unit`` is "bp" (series in percent) or "pct" (relative move)."""
    s = series.dropna()
    if unit == "bp":
        moves = s.diff() * 100.0
    elif unit == "pct":
        moves = s.pct_change() * 100.0
    else:
        raise ValueError(unit)
    out = []
    for d, m in moves.dropna().items():
        if abs(m) > threshold:
            out.append(
                QCException(
                    source,
                    str(s.name),
                    d,
                    "jump",
                    "WARN",
                    f"day-on-day move {m:+.2f}{unit} > {threshold}{unit}",
                )
            )
    return out


def check_zero_curve(
    times: np.ndarray, zeros_pct: np.ndarray, source: str, obs_date: date
) -> list[QCException]:
    """Continuously compounded zeros: discount factors must fall with maturity
    and instantaneous forwards must stay above a floor."""
    t = np.asarray(times, float)
    z = np.asarray(zeros_pct, float) / 100.0
    out = []
    if np.isnan(z).any():
        out.append(
            QCException(
                source,
                "curve",
                obs_date,
                "missing",
                "FAIL",
                f"{int(np.isnan(z).sum())} NaN pillars",
            )
        )
        mask = ~np.isnan(z)
        t, z = t[mask], z[mask]
    df = np.exp(-z * t)
    if (np.diff(df) >= 0).any():
        i = int(np.argmax(np.diff(df) >= 0))
        out.append(
            QCException(
                source,
                "curve",
                obs_date,
                "curve shape",
                "FAIL",
                f"discount factor not falling at {t[i + 1]:.3f}y",
            )
        )
    fwd = np.diff(z * t) / np.diff(t)
    if (fwd < -0.01).any():
        i = int(np.argmax(fwd < -0.01))
        out.append(
            QCException(
                source,
                "curve",
                obs_date,
                "curve shape",
                "WARN",
                f"forward {fwd[i]:.2%} below -1% near {t[i + 1]:.3f}y",
            )
        )
    return out


def to_frame(exceptions: list[QCException]) -> pd.DataFrame:
    cols = ["source", "field", "obs_date", "check", "severity", "detail"]
    return pd.DataFrame([e.__dict__ for e in exceptions], columns=cols)
