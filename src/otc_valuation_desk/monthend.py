"""Month-end value-change explain.

    uv run python -m otc_valuation_desk.monthend 2026-08-28 2026-09-30

Splits the change in portfolio value (USD) between two dates into steps by
full revaluation, each step switching one block of market data:

1. carry: valuation date moved to T1 on T0's curves (forwards realised),
   spot and vols held; realised SONIA/SOFR fixings enter here
2. GBP rates: GBP curve switched to T1's
3. USD rates: USD curve switched to T1's
4. FX spot: switched to T1's (includes translating GBP values to USD)
5. vols: FX smile and swaption vols switched (synthetic and static, so zero)
6. new trades: trades booked in (T0, T1], at their T1 value

Sequential steps leave no residual by construction, but the split depends on
the order: the cross effect (e.g. FX move on the rates move) lands in the
later step. The report gives the reverse order's split as a check.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import date
from pathlib import Path

import pandas as pd

from . import pricing as P
from .cycle import PORTFOLIO, ROOT, _md_table, write_excel
from .dates import schedule
from .market import Market, build_market, roll_to
from .pricing import XCCY_FREQ
from .trades import (
    FXForward,
    FXOption,
    OISSwap,
    Swaption,
    Trade,
    XCCYSwap,
    load_portfolio,
)

TRADE_DATES = ROOT / "data" / "trades" / "trade_dates.csv"


def value_usd(t: Trade, mkt: Market) -> float:
    return P.to_usd(P.price(t, mkt), P.pv_ccy(t), mkt)


def cash_events(t: Trade, t0: date, t1: date) -> list[str]:
    """Payments or expiries in (t0, t1]; the explain does not model cash
    leaving the book, so any event is reported rather than silently lost."""
    events = []
    if isinstance(t, OISSwap):
        from .curves import CONVENTIONS

        c = CONVENTIONS[t.ccy]
        events = [
            f"coupon {p.end}"
            for p in schedule(t.start, t.end, c["freq"], c["cal"])
            if t0 < p.end <= t1
        ]
    elif isinstance(t, XCCYSwap):
        events = [
            f"coupon {p.end}"
            for p in schedule(t.start, t.end, XCCY_FREQ, "GBP+USD")
            if t0 < p.end <= t1
        ]
    elif isinstance(t, FXForward) and t0 < t.delivery <= t1:
        events = [f"delivery {t.delivery}"]
    elif isinstance(t, FXOption | Swaption) and t0 < t.expiry <= t1:
        events = [f"expiry {t.expiry}"]
    return events


def explain(t0: date, t1: date) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    m0, m1 = build_market(t0), build_market(t1)
    trades = load_portfolio(PORTFOLIO)
    td = {
        r.trade_id: date.fromisoformat(r.trade_date)
        for r in pd.read_csv(TRADE_DATES).itertuples()
    }
    old = [t for t in trades if td[t.trade_id] <= t0]
    new = [t for t in trades if t0 < td[t.trade_id] <= t1]

    s1 = roll_to(m0, t1)
    s2 = replace(s1, curves={**s1.curves, "GBP": m1.curves["GBP"]})
    s3 = replace(s2, curves={**s2.curves, "USD": m1.curves["USD"]})
    s4 = replace(s3, spot=m1.spot)
    s5 = replace(s4, fx_vol=m1.fx_vol, swaption_vol=m1.swaption_vol)
    seq = [
        ("carry", m0, s1),
        ("gbp_rates", s1, s2),
        ("usd_rates", s2, s3),
        ("fx_spot", s3, s4),
        ("vols", s4, s5),
    ]

    # reverse order for the cross-effect check: FX and vols first, then rates
    r1 = replace(s1, spot=m1.spot, fx_vol=m1.fx_vol, swaption_vol=m1.swaption_vol)
    r2 = replace(r1, curves={**r1.curves, "USD": m1.curves["USD"]})
    r3 = replace(r2, curves={**r2.curves, "GBP": m1.curves["GBP"]})
    rev = [
        ("carry", m0, s1),
        ("fx_spot", s1, r1),
        ("usd_rates", r1, r2),
        ("gbp_rates", r2, r3),
    ]

    rows, notes = [], []
    for t in old:
        r = {
            "trade_id": t.trade_id,
            "product": t.product,
            "status": "existing",
            "value_t0": value_usd(t, m0),
        }
        for name, a, b in seq:
            r[name] = value_usd(t, b) - value_usd(t, a)
        r["new_trades"] = 0.0
        r["value_t1"] = value_usd(t, m1)
        r["check"] = r["value_t1"] - r["value_t0"] - sum(r[n] for n, _, _ in seq)
        rows.append(r)
        notes += [f"{t.trade_id}: {e} not modelled" for e in cash_events(t, t0, t1)]
    for t in new:
        v1 = value_usd(t, m1)
        rows.append(
            {
                "trade_id": t.trade_id,
                "product": t.product,
                "status": f"new ({td[t.trade_id]})",
                "value_t0": 0.0,
                **{n: 0.0 for n, _, _ in seq},
                "new_trades": v1,
                "value_t1": v1,
                "check": 0.0,
            }
        )
    per_trade = pd.DataFrame(rows)

    steps = ["carry", "gbp_rates", "usd_rates", "fx_spot", "vols", "new_trades"]
    rev_tot = {
        name: sum(value_usd(t, b) - value_usd(t, a) for t in old) for name, a, b in rev
    }
    summary = pd.DataFrame(
        [
            {
                "step": "value at T0",
                "usd": per_trade["value_t0"].sum(),
                "reverse_order": per_trade["value_t0"].sum(),
            }
        ]
        + [
            {
                "step": s,
                "usd": per_trade[s].sum(),
                "reverse_order": rev_tot.get(s, per_trade[s].sum()),
            }
            for s in steps
        ]
        + [
            {
                "step": "value at T1",
                "usd": per_trade["value_t1"].sum(),
                "reverse_order": per_trade["value_t1"].sum(),
            },
            {"step": "residual", "usd": per_trade["check"].sum(), "reverse_order": 0.0},
        ]
    )
    if not notes:
        notes = [
            "No coupons, deliveries or expiries fell in the period (checked), so no cash left the book."
        ]
    return per_trade, summary, notes


def write(
    t0: date,
    t1: date,
    per_trade: pd.DataFrame,
    summary: pd.DataFrame,
    notes: list[str],
    m0: Market,
    m1: Market,
) -> Path:
    out = ROOT / "outputs" / str(t1)
    out.mkdir(parents=True, exist_ok=True)
    moves = pd.DataFrame(
        [
            {
                "market": "GBP 5y zero (%)",
                "t0": m0.curves["GBP"].zero(5) * 100,
                "t1": m1.curves["GBP"].zero(5) * 100,
            },
            {
                "market": "USD 5y zero (%, UST proxy)",
                "t0": m0.curves["USD"].zero(5) * 100,
                "t1": m1.curves["USD"].zero(5) * 100,
            },
            {
                "market": "GBP/USD spot",
                "t0": m0.spot["GBPUSD"],
                "t1": m1.spot["GBPUSD"],
            },
        ]
    )
    lines = [
        f"# Month-end value-change explain — {t0} to {t1}",
        "",
        "Portfolio value in USD, own model, full revaluation per step. Fictional portfolio; FX and swaption vols "
        "synthetic and held constant, so the vol step is zero. USD curve is a Treasury proxy.",
        "",
        "## Market moves",
        "",
        _md_table(moves, ",.4f"),
        "",
        "## Explain",
        "",
        _md_table(summary),
        "",
        "Steps run in the order shown; `reverse_order` switches FX before rates. The difference between the two "
        "columns is the cross effect, which a sequential explain assigns to whichever step comes later.",
        "",
        "## Notes",
        "",
        *[f"- {n}" for n in notes],
        "",
        "## By trade",
        "",
        _md_table(per_trade.drop(columns=["check"])),
        "",
    ]
    (out / "month_end_explain.md").write_text("\n".join(lines))
    write_excel(
        out / "month_end_explain.xlsx",
        {"Summary": summary, "ByTrade": per_trade, "Moves": moves},
    )
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Month-end value-change explain")
    ap.add_argument("t0", type=date.fromisoformat)
    ap.add_argument("t1", type=date.fromisoformat)
    a = ap.parse_args()
    per_trade, summary, notes = explain(a.t0, a.t1)
    out = write(
        a.t0, a.t1, per_trade, summary, notes, build_market(a.t0), build_market(a.t1)
    )
    print(summary.to_string(index=False, float_format=lambda x: f"{x:,.0f}"))
    print(*notes, sep="\n")
    print(f"report: {out.relative_to(ROOT)}/month_end_explain.md, .xlsx")


if __name__ == "__main__":
    main()
