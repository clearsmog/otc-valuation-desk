# otc-valuation-desk

An independent valuation and price-challenge workflow for GBP and USD rates
and GBP/USD FX, modelled on what a third-party OTC valuation service does for
buy-side clients each day:

1. check the market data,
2. build OIS discount curves,
3. value the client's trades with its own pricers,
4. compare those values with an independent QuantLib reference,
5. compare them with the counterparties' marks and work every difference above
   tolerance down to a cause,
6. publish a daily report (markdown and Excel).

Personal build, made with AI coding agents (Claude Code). The client portfolio,
FX vols and dealer marks are synthetic; the curves, fixings and FX spot are
real public data (sources below).

```
uv sync
uv run pytest                                                   # 20 tests, offline
uv run python -m otc_valuation_desk.cycle 2026-10-15 --prior 2026-10-14
# -> outputs/2026-10-15/valuation_report.md and valuation_report.xlsx
```

## Data

| Input | Source | Note |
|---|---|---|
| GBP SONIA OIS curve | Bank of England daily OIS spot curve | Real |
| SONIA fixings | Bank of England IADB (IUDSOIA) | Real |
| SOFR fixings | Federal Reserve Bank of New York | Real |
| USD curve | US Treasury daily par yield curve | Real data used as a **proxy** for SOFR OIS par rates (no free SOFR swap quotes; swap spread ignored) |
| GBP/USD spot | ECB reference rates (EUR/USD ÷ EUR/GBP) | Real; 2:15pm CET fixing |
| GBP/USD ATM vols | — | Synthetic |
| Client portfolio (20 trades) | — | Synthetic fictional fund |
| Dealer marks | — | Synthetic, generated from planted causes |

Raw downloads are cached under `data/raw/`, so a valuation date reruns offline.

## Modules

| Module | Does |
|---|---|
| `data.py` | Fetchers for the five sources, cached to disk |
| `qc.py` | Missing business days, stale values, day-on-day jumps, zero-curve shape (falling discount factors, forward floor) |
| `dates.py` | UK and US calendars, modified-following adjustment, backward schedules with a front stub, ACT/365F and ACT/360 |
| `curves.py` | Par OIS quotes from the BoE zero curve; sequential bootstrap with log-linear discount factors; the round trip reprices every quote to 1e-10 |
| `pricing.py` | OIS swaps with the floating leg compounded in arrears (realised fixings for seasoned trades, telescoped forwards for the rest); FX forwards by covered interest parity from the spot date; FX options by Garman-Kohlhagen in forward form; bump-and-reprice PV01, FX delta and vega |
| `reference.py` | The same trades in QuantLib: `OISRateHelper` curves, `OvernightIndexedSwap`, `GarmanKohlagenProcess` |
| `marks.py` | Dealer marks generated from planted causes, with an answer key |
| `challenge.py` | Tolerance per product, then attribution: each candidate cause is replayed and the closest one that closes at least 90% of the gap is kept |
| `cycle.py` | The daily run and the report writers |

## Price-challenge attribution

| Cause | How it is tested | Status if it fits |
|---|---|---|
| Prior-day curves and spot | Reprice off the previous day's market | EXPLAINED |
| Fixed-leg day count (GBP) | Reprice with ACT/360 | EXPLAINED |
| Curve interpolation (GBP) | Reprice off the BoE curve's own interpolation | EXPLAINED |
| Direction booked the wrong way | Reprice the opposite side | EXPLAINED |
| Notional booked differently | Mark/our-value ratio gives an exact round notional | EXPLAINED |
| Mark at bid/offer, not mid | Gap is a fraction of a bp (or vol point) against the client | LIKELY |
| Dealer vol differs | Gap ÷ vega | LIKELY |
| Spot snapshot time | Gap ÷ FX delta | LIKELY |

Tolerance: the larger of 1,000 in the PV currency and 0.25bp of PV01 (swaps),
0.25 vol point of vega (options) or 2bp of spot (forwards). Direction and
notional tests only run when the trade's value is at least twice the
tolerance: on a trade near par they have no power, and the report says to
check the confirmation instead. On the sample date the attribution recovers
all 20 planted causes (`tests/test_challenge.py`).

## Own engine vs QuantLib (2026-10-15)

| Product | Largest gap | Why |
|---|---|---|
| Curves | about 1e-14 in discount factor | — |
| OIS swaps | 0.79 USD on a 25m swap (0.0001bp of PV01) | Calendars: QuantLib's SOFR calendar closes on Good Friday, US federal holidays do not |
| FX forwards | under 1 cent | — |
| FX options | 0.007 vol pt of vega (515 USD on 12m GBP) | Convention: QuantLib's Garman-Kohlhagen runs rates from today to expiry with no settlement lag; the own pricer runs the forward from spot date to delivery |

Two bugs found by this comparison and fixed: the schedule rolled back from the
adjusted maturity instead of the unadjusted one (moved coupon dates by up to
two days), and four test trades carried adjusted termination dates, which
QuantLib turns into a one-day first stub.

## Limits

- Single-curve OIS discounting; no CSA currency choice or cross-currency basis.
- USD curve is a Treasury proxy, so USD values are illustrative.
- FX vol is a flat-smile ATM term structure (smile planned).
- Fixings use a zero-day lookback; real SONIA swaps commonly use a 5-day lookback.

## Roadmap

Swaptions (Bachelier), FX smile from ATM/RR/BF, SONIA–SOFR cross-currency
swap, month-end cycle with a value-change explain, Excel/VBA exception view.
See `PLAN.md`.
