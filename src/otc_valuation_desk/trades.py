"""Trade representations and the client portfolio file.

The portfolio is a fictional buy-side fund; every trade is invented.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class OISSwap:
    trade_id: str
    counterparty: str
    ccy: str
    notional: float
    fixed_rate: float  # decimal
    pay_fixed: bool
    start: date
    end: date
    product: str = "OIS"


@dataclass(frozen=True)
class FXForward:
    trade_id: str
    counterparty: str
    pair: str  # base/quote, e.g. GBPUSD
    notional: float  # in base currency
    strike: float  # quote per base
    buy_base: bool
    delivery: date
    product: str = "FXFWD"


@dataclass(frozen=True)
class FXOption:
    trade_id: str
    counterparty: str
    pair: str
    notional: float  # in base currency
    strike: float
    call: bool  # call on the base currency
    long: bool
    expiry: date
    delivery: date
    product: str = "FXOPT"


@dataclass(frozen=True)
class Swaption:
    """European swaption on a spot-starting OIS (annual fixed vs compounded
    overnight). ``start``/``end`` are the underlying swap's dates."""

    trade_id: str
    counterparty: str
    ccy: str
    notional: float
    strike: float  # decimal
    payer: bool
    long: bool
    expiry: date
    start: date
    end: date
    product: str = "SWPTN"


@dataclass(frozen=True)
class XCCYSwap:
    """Constant-notional cross-currency basis swap: compounded SONIA (+ spread)
    on the GBP notional against compounded SOFR on the USD notional, quarterly,
    with initial and final notional exchanges."""

    trade_id: str
    counterparty: str
    notional: float  # GBP
    notional_usd: float
    spread: float  # decimal, on the GBP leg
    receive_gbp: bool
    start: date
    end: date
    pair: str = "GBPUSD"
    product: str = "XCCY"


Trade = OISSwap | FXForward | FXOption | Swaption | XCCYSwap


def _d(x) -> date:
    return date.fromisoformat(str(x))


def load_portfolio(path: Path) -> list[Trade]:
    df = pd.read_csv(path, dtype=str).fillna("")
    out: list[Trade] = []
    for r in df.to_dict("records"):
        p = r["product"]
        if p == "OIS":
            out.append(
                OISSwap(
                    r["trade_id"],
                    r["counterparty"],
                    r["ccy"],
                    float(r["notional"]),
                    float(r["rate"]),
                    r["direction"] == "PAY_FIXED",
                    _d(r["start"]),
                    _d(r["end"]),
                )
            )
        elif p == "FXFWD":
            out.append(
                FXForward(
                    r["trade_id"],
                    r["counterparty"],
                    r["pair"],
                    float(r["notional"]),
                    float(r["rate"]),
                    r["direction"] == "BUY",
                    _d(r["end"]),
                )
            )
        elif p == "FXOPT":
            out.append(
                FXOption(
                    r["trade_id"],
                    r["counterparty"],
                    r["pair"],
                    float(r["notional"]),
                    float(r["rate"]),
                    r["option_type"] == "CALL",
                    r["direction"] == "BUY",
                    _d(r["expiry"]),
                    _d(r["end"]),
                )
            )
        elif p == "SWPTN":
            out.append(
                Swaption(r["trade_id"], r["counterparty"], r["ccy"], float(r["notional"]), float(r["rate"]),
                         r["option_type"] == "PAYER", r["direction"] == "BUY", _d(r["expiry"]), _d(r["start"]), _d(r["end"]))
            )
        elif p == "XCCY":
            out.append(
                XCCYSwap(r["trade_id"], r["counterparty"], float(r["notional"]), float(r["notional_quote"]),
                         float(r["rate"]), r["direction"] == "RECEIVE_GBP", _d(r["start"]), _d(r["end"]))
            )
        else:
            raise ValueError(f"unknown product {p!r} in {r['trade_id']}")
    return out
