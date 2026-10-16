# otc-valuation-desk

An independent valuation and price-challenge workflow for GBP and USD rates
and GBP/USD FX, modelled on what a third-party OTC valuation service does for
buy-side clients:

1. check the market data,
2. build OIS discount curves,
3. value the client's trades with its own pricers,
4. compare those values with an independent QuantLib reference,
5. compare them with the counterparties' marks and work every difference above
   tolerance down to a cause,
6. publish a daily report (markdown and Excel) and a month-end value-change
   explain.

Personal build, made with AI coding agents (Claude Code). The client portfolio,
vols and dealer marks are synthetic; the curves, fixings and FX spot are real
public data (sources below).

```
uv sync
uv run pytest                                                   # 25 tests, offline
uv run python -m otc_valuation_desk.cycle 2026-10-15 --prior 2026-10-14
# -> outputs/2026-10-15/valuation_report.md and .xlsx
uv run python -m otc_valuation_desk.monthend 2026-08-28 2026-09-30
# -> outputs/2026-09-30/month_end_explain.md and .xlsx
```

## The book (26 synthetic trades)

| Product | Trades | Model |
|---|---|---|
| SONIA and SOFR OIS (spot, forward-start, seasoned) | 10 | Floating leg compounded in arrears: realised fixings for the current period, telescoped forwards after |
| GBP/USD FX forwards | 5 | Covered interest parity from the spot date |
| GBP/USD FX options | 5 | Garman-Kohlhagen (forward form) off a vanna-volga smile |
| GBP and USD swaptions on OIS | 4 | Bachelier (normal vol) with the OIS annuity |
| SONIA vs SOFR cross-currency basis swaps | 2 | Constant notional, quarterly, notional exchanges; no basis curve |

## Data

| Input | Source | Note |
|---|---|---|
| GBP SONIA OIS curve | Bank of England daily OIS spot curve (current month and archive) | Real |
| SONIA fixings | Bank of England IADB (IUDSOIA) | Real |
| SOFR fixings | Federal Reserve Bank of New York | Real |
| USD curve | US Treasury daily par yield curve | Real data used as a **proxy** for SOFR OIS par rates (no free SOFR swap quotes; swap spread ignored) |
| GBP/USD spot | ECB reference rates (EUR/USD ÷ EUR/GBP) | Real; 2:15pm CET fixing |
| FX smile (ATM, 25D RR, 25D BF) | — | Synthetic |
| Swaption normal vols | — | Synthetic |
| Portfolio, trade dates, dealer marks | — | Synthetic |

Raw downloads are cached under `data/raw/`, so every date reruns offline.

## Modules

| Module | Does |
|---|---|
| `data.py` | Fetchers for the five sources, cached to disk |
| `qc.py` | Missing business days, stale values, day-on-day jumps, zero-curve shape |
| `dates.py` | UK and US calendars, modified following, backward schedules from the unadjusted maturity, ACT/365F and ACT/360 |
| `curves.py` | Par OIS quotes from the BoE zero curve; sequential bootstrap with log-linear discount factors |
| `market.py` | Market state; FX smile (vanna-volga from ATM/RR/BF pillar strikes); swaption normal-vol grid; roll-forward for carry |
| `pricing.py` | Own pricers and bump-and-reprice PV01, FX delta, vega |
| `reference.py` | The same trades in QuantLib: `OISRateHelper` curves, `OvernightIndexedSwap`, `GarmanKohlagenProcess`, `BachelierSwaptionEngine`, `OvernightLeg` |
| `marks.py` | Dealer marks generated from planted causes, with an answer key |
| `challenge.py` | Tolerance per product, then attribution of each gap |
| `cycle.py` | The daily run and report writers |
| `monthend.py` | Month-end explain: carry, GBP rates, USD rates, FX spot, vols, new trades |
| `vba/ChallengeLog.bas` | Excel macro: exception log ranked by size against tolerance, owner and resolution tracking, counterparty × status counts |

## Own engine vs QuantLib (2026-10-15)

| Product | Largest gap | Why |
|---|---|---|
| Curves | about 1e-14 in discount factor | — |
| OIS swaps | 0.79 USD (0.0001bp of PV01) | Calendars: QuantLib's SOFR calendar closes on Good Friday, US federal holidays do not |
| Swaptions, XCCY, FX forwards | under 1 cent | — |
| FX options | 0.016 vol pt of vega | Convention: QuantLib's Garman-Kohlhagen runs rates from today to expiry with no settlement lag; the own pricer runs the forward from spot date to delivery |

The comparison found one bug in the own engine (coupon dates rolled from the
adjusted maturity instead of the unadjusted one) and four test trades that
carried adjusted termination dates, which QuantLib turns into a one-day stub.

## Price-challenge attribution

| Cause | How it is tested | Status if it fits |
|---|---|---|
| Prior-day curves and spot | Reprice off the previous day's market | EXPLAINED |
| Fixed-leg day count (GBP) | Reprice with ACT/360 | EXPLAINED |
| Curve interpolation (GBP) | Reprice off the BoE curve's own interpolation | EXPLAINED |
| Direction booked the wrong way | Reprice the opposite side | EXPLAINED |
| Notional booked differently | Mark/our-value ratio gives an exact round notional | EXPLAINED |
| Mark at bid/offer, not mid | Gap is a fraction of a bp (or vol) against the client | LIKELY |
| Dealer vol differs | Gap ÷ vega | LIKELY |
| Spot snapshot time | Gap ÷ FX delta | LIKELY |

A cause is confirmed only if it closes at least 90% of the gap, and the closest
fit wins. Direction and notional tests only run when the trade's value is at
least twice the tolerance; below that they have no power and the report says
to check the confirmation. On the sample date the attribution recovers all 26
planted causes (`tests/test_challenge.py`).

## Month-end explain (28 Aug to 30 Sep 2026, real market moves)

GBP 5y zero +36bp, USD 5y (proxy) +60bp, GBP/USD −2.2%. Portfolio value
5.65m → 5.44m USD: carry −80k, GBP rates +229k, USD rates −66k, FX spot −158k,
new trades −128k, residual 0. Reversing the order of the FX and rates steps
moves 3–7k between them: the cross effect.

## Excel macro

Import `vba/ChallengeLog.bas` into `valuation_report.xlsx` (Developer →
Visual Basic → File → Import File), save as `.xlsm`, run `BuildExceptionLog`.

## Limits

- Single-curve OIS discounting; no CSA currency choice and no cross-currency
  basis curve, so XCCY values come from spread, rates and spot only.
- USD curve is a Treasury proxy, so USD values are illustrative.
- Smile pillars use the smile-strangle shortcut (σ25 = ATM + BF ± RR/2) and
  forward deltas.
- Fixings use a zero-day lookback; SONIA swaps commonly use five days.
- The month-end explain flags, rather than models, cash that leaves the book.
