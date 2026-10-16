# otc-valuation-desk: plan

A personal build that mirrors what an independent OTC valuation team does each
day for buy-side clients: check the market data, build curves, value the
client's trades with its own models, compare those values with an independent
reference (QuantLib) and with the client's counterparty (dealer) marks, and
work every difference above tolerance down to a cause.

Scope agreed 2026-10-16: **rates and FX only**, full version in about a week;
the CV application waits for the core version. Status 2026-10-16: core and full version built (phases 1-12).

## Data

| Input | Source | Real or synthetic |
|---|---|---|
| GBP SONIA OIS curve | Bank of England daily OIS spot curve (zip, xlsx) | Real |
| SONIA fixings | BoE IADB series IUDSOIA | Real |
| SOFR fixings | NY Fed markets API | Real |
| USD curve | US Treasury daily par yield curve, used as a SOFR OIS **proxy** (no free SOFR swap quotes; swap spread ignored) | Real data, proxy use stated |
| FX spot | ECB reference rates (EUR/USD, EUR/GBP, cross GBP/USD) | Real |
| FX vol (ATM, 25D RR, 25D BF) | Generated | Synthetic, labelled |
| Swaption normal vols | Generated | Synthetic, labelled |
| Client portfolio | Generated fictional buy-side fund | Synthetic |
| Dealer marks | Our model values plus injected, known discrepancies | Synthetic |

## Architecture

```
fetch raw data (cached by date) -> [qc] market-data checks
                                   -> [curves] OIS bootstrap (own) 
                                   -> [pricing] own pricers --------------+
client trades (CSV) -------------------------------------------------------+-> [challenge]
                                   [reference] QuantLib pricers ----------+    tolerance, attribution,
                                   [marks] dealer marks (synthetic) ------+    exception log
                                                                           -> [cycle] daily / month-end
                                                                              run, markdown + Excel report
```

The own engine must not import QuantLib, so the reference stays independent.

## Phases

### Core (apply after this)

1. **Data and QC**: fetchers with on-disk cache; checks for missing points,
   stale values (unchanged N days), day-on-day jumps beyond a threshold,
   curve shape (negative forwards, non-monotone discount factors).
2. **Curves**: day counts (ACT/365F for GBP, ACT/360 for USD), business-day
   calendars (UK, US), schedule generation; par OIS quotes derived from the BoE
   spot curve, then bootstrapped back (log-linear discount factors). Test: the
   bootstrap reproduces the BoE zero rates and reprices every par quote.
3. **Pricers (own)**: SONIA and SOFR OIS swaps (compounded-in-arrears floating
   leg, with past fixings for seasoned trades); FX forwards by covered interest
   parity; FX vanilla options (Garman-Kohlhagen). PV and bump-and-reprice PV01,
   FX delta, vega.
4. **Reference**: the same trades in QuantLib (OISRateHelper curves,
   OvernightIndexedSwap, FX forward via discounting, GarmanKohlagenProcess).
   Test: own vs QuantLib within a stated tolerance per product.
5. **Dealer marks and price challenge**: injected causes (curve snapshot time,
   day-count convention, stale or missing fixing, bid vs mid, wrong notional or
   direction, vol surface); tolerance rules per product (absolute and in bp of
   notional / vega units); attribution by swapping one input at a time and
   repricing, so each difference is explained or left as unexplained residual.
6. **Daily run**: one command produces the valuation report (markdown + Excel):
   QC exceptions, values, own vs reference, own vs dealer, challenge log.

### Full (rest of the week)

7. Swaptions (Bachelier on the OIS curve) and own vs QuantLib.
8. FX vol smile from ATM / RR / BF (delta conventions, vanna-volga or SABR),
   options priced off the smile.
9. Cross-currency SONIA vs SOFR swap (constant notional; MtM resets optional).
10. Month-end cycle: month-on-month value change explained by market move vs
    time decay vs new trades; month-end client pack.
11. Excel output with a VBA module (exception filter, challenge-log formatting);
    the user writes or reviews the VBA so it can be defended.
12. README, `docs/explainer-zh.md` (every model explained in plain Chinese, with
    the formulas and the interview questions it answers), GitHub publish.

## Rules

- CV wording: "personal build", "built with AI coding agents", synthetic parts
  named. Real data sources named exactly.
- Every model must be explainable by the user without the code
  (`docs/explainer-zh.md`).
- Numbers that reach the CV get recorded in `~/Documents/Jobs/CV/FROZEN-FACTS.md`.
