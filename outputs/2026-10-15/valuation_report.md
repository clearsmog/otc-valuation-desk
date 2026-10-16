# Valuation report — 2026-10-15

Fictional client portfolio (20 trades). GBP curve: Bank of England OIS. USD curve: US Treasury par yields as a SOFR OIS **proxy**. FX spot: ECB reference rate. FX vols and dealer marks are **synthetic**.

## Summary

- Portfolio PV (USD, own model): 3,259,094
- QuantLib reference: 20/20 trades within tolerance
- Market-data QC exceptions: 5 (0 FAIL)
- Price challenges: EXPLAINED 7, LIKELY 4, WITHIN_TOLERANCE 9

## Market-data QC

| source | field | obs_date | check | severity | detail |
|---|---|---|---|---|---|
| SOFR | SOFR | 2026-09-17 | jump | WARN | day-on-day move +23.00bp > 10.0bp |
| Treasury | UST 3y | 2026-09-23 | jump | WARN | day-on-day move +16.00bp > 15.0bp |
| Treasury | UST 5y | 2026-09-23 | jump | WARN | day-on-day move +16.00bp > 15.0bp |
| Treasury | UST 7y | 2026-09-23 | jump | WARN | day-on-day move +16.00bp > 15.0bp |
| Treasury | UST 10y | 2026-09-23 | jump | WARN | day-on-day move +15.00bp > 15.0bp |

## Curves (own bootstrap vs QuantLib)

| curve | tenor_y | zero_pct | df_own | df_quantlib | df_diff_e6 |
|---|---|---|---|---|---|
| GBP SONIA OIS | 0.250000 | 3.952300 | 0.990195 | 0.990195 | -0.000000 |
| GBP SONIA OIS | 1.000000 | 4.389500 | 0.957055 | 0.957055 | 0.000000 |
| GBP SONIA OIS | 2.000000 | 4.622200 | 0.911701 | 0.911701 | -0.000000 |
| GBP SONIA OIS | 5.000000 | 4.685300 | 0.791150 | 0.791150 | -0.000000 |
| GBP SONIA OIS | 10.000000 | 4.861100 | 0.615013 | 0.615013 | 0.000000 |
| GBP SONIA OIS | 20.000000 | 5.180300 | 0.354848 | 0.354848 | 0.000000 |
| USD SOFR OIS (UST par proxy) | 0.250000 | 4.301800 | 0.989332 | 0.989332 | -0.000000 |
| USD SOFR OIS (UST par proxy) | 1.000000 | 4.448300 | 0.956492 | 0.956492 | 0.000000 |
| USD SOFR OIS (UST par proxy) | 2.000000 | 4.724700 | 0.909834 | 0.909834 | -0.000000 |
| USD SOFR OIS (UST par proxy) | 5.000000 | 4.866000 | 0.784037 | 0.784037 | 0.000000 |
| USD SOFR OIS (UST par proxy) | 10.000000 | 5.073400 | 0.602095 | 0.602095 | 0.000000 |
| USD SOFR OIS (UST par proxy) | 20.000000 | 5.559400 | 0.328938 | 0.328938 | -0.000000 |

## Valuations

| trade_id | product | counterparty | ccy | pv_own | pv_quantlib | own_minus_ql | diff_in_risk_units | ref_check |
|---|---|---|---|---|---|---|---|---|
| NBM-IRS-001 | OIS | Bank A | GBP | 952,194 | 952,194 | 0 | 0 | OK |
| NBM-IRS-002 | OIS | Bank B | GBP | -385,085 | -385,085 | -0 | -0 | OK |
| NBM-IRS-003 | OIS | Bank C | GBP | 4,464 | 4,464 | 0 | 0 | OK |
| NBM-IRS-004 | OIS | Bank A | GBP | 7,559 | 7,559 | -0 | -0 | OK |
| NBM-IRS-005 | OIS | Bank D | GBP | 2,751 | 2,751 | 0 | 0 | OK |
| NBM-IRS-006 | OIS | Bank B | GBP | -288,733 | -288,733 | -0 | -0 | OK |
| NBM-IRS-007 | OIS | Bank C | USD | 1,680,096 | 1,680,096 | -0 | -0 | OK |
| NBM-IRS-008 | OIS | Bank E | USD | -13,256 | -13,256 | -0 | -0 | OK |
| NBM-IRS-009 | OIS | Bank D | USD | -93,948 | -93,948 | -0 | -0 | OK |
| NBM-IRS-010 | OIS | Bank A | USD | -256,602 | -256,601 | -1 | -0 | OK |
| NBM-FXF-001 | FXFWD | Bank B | USD | 100,606 | 100,606 | 0 | 0 | OK |
| NBM-FXF-002 | FXFWD | Bank C | USD | 301,433 | 301,433 | -0 | -0 | OK |
| NBM-FXF-003 | FXFWD | Bank E | USD | 530,457 | 530,457 | -0 | -0 | OK |
| NBM-FXF-004 | FXFWD | Bank A | USD | 150,381 | 150,381 | 0 | 0 | OK |
| NBM-FXF-005 | FXFWD | Bank D | USD | 63,988 | 63,988 | -0 | -0 | OK |
| NBM-FXO-001 | FXOPT | Bank B | USD | 119,873 | 120,121 | -248 | -0 | OK |
| NBM-FXO-002 | FXOPT | Bank C | USD | 101,813 | 101,754 | 59 | 0 | OK |
| NBM-FXO-003 | FXOPT | Bank E | USD | -158,914 | -159,338 | 424 | 0 | OK |
| NBM-FXO-004 | FXOPT | Bank A | USD | -152,739 | -152,613 | -126 | -0 | OK |
| NBM-FXO-005 | FXOPT | Bank D | USD | 497,581 | 498,096 | -515 | -0 | OK |

## Price challenges (dealer mark minus our value)

| trade_id | counterparty | ccy | our_value | dealer_mark | difference | tolerance | status | cause | detail | action |
|---|---|---|---|---|---|---|---|---|---|---|
| NBM-IRS-001 | Bank A | GBP | 952,194 | 847,658 | -104,536 | 3,999 | EXPLAINED | DAY_COUNT | matches a fixed leg accrued ACT/360 | Confirm fixed-leg day count against the confirmation; ask the dealer to correct its booking |
| NBM-IRS-002 | Bank B | GBP | -385,085 | -385,018 | 68 | 1,355 | WITHIN_TOLERANCE |  |  |  |
| NBM-IRS-003 | Bank C | GBP | 4,464 | 446 | -4,017 | 1,960 | EXPLAINED | NOTIONAL | matches a notional of 4,000,000 (booked 40,000,000) | Booking break: confirm notional against the confirmation; escalate to operations |
| NBM-IRS-004 | Bank A | GBP | 7,559 | 7,921 | 363 | 2,282 | WITHIN_TOLERANCE |  |  |  |
| NBM-IRS-005 | Bank D | GBP | 2,751 | -3,335 | -6,085 | 3,043 | LIKELY | BID_SIDE | value too small to test direction/notional: check the confirmation. gap = 0.50bp of PV01 against us | Ask whether the mark is mid or bid/offer; request a mid mark |
| NBM-IRS-006 | Bank B | GBP | -288,733 | -279,999 | 8,734 | 3,325 | EXPLAINED | INTERPOLATION | matches a curve read off the BoE zero curve | Methodology difference (curve interpolation); document, no booking change |
| NBM-IRS-007 | Bank C | USD | 1,680,096 | 1,837,214 | 157,118 | 5,031 | EXPLAINED | PRIOR_DAY | matches a mark off 2026-10-14 curves and spot | Ask the dealer for the curve/spot snapshot date; re-request today's mark |
| NBM-IRS-008 | Bank E | USD | -13,256 | -13,067 | 189 | 1,710 | WITHIN_TOLERANCE |  |  |  |
| NBM-IRS-009 | Bank D | USD | -93,948 | 93,948 | 187,897 | 3,039 | EXPLAINED | DIRECTION | matches the opposite direction | Booking break: confirm direction against the confirmation; escalate to operations |
| NBM-IRS-010 | Bank A | USD | -256,602 | -256,875 | -273 | 2,488 | WITHIN_TOLERANCE |  |  |  |
| NBM-FXF-001 | Bank B | USD | 100,606 | 100,580 | -26 | 2,640 | WITHIN_TOLERANCE |  |  |  |
| NBM-FXF-002 | Bank C | USD | 301,433 | 219,505 | -81,928 | 6,554 | LIKELY | SPOT_SNAPSHOT | gap equals spot +0.250% from ours | Ask for the spot fixing time used; align snapshot times |
| NBM-FXF-003 | Bank E | USD | 530,457 | 530,529 | 73 | 3,891 | WITHIN_TOLERANCE |  |  |  |
| NBM-FXF-004 | Bank A | USD | 150,381 | 132,389 | -17,992 | 2,027 | EXPLAINED | PRIOR_DAY | matches a mark off 2026-10-14 curves and spot | Ask the dealer for the curve/spot snapshot date; re-request today's mark |
| NBM-FXF-005 | Bank D | USD | 63,988 | 63,910 | -78 | 3,158 | WITHIN_TOLERANCE |  |  |  |
| NBM-FXO-001 | Bank B | USD | 119,873 | 120,382 | 508 | 3,957 | WITHIN_TOLERANCE |  |  |  |
| NBM-FXO-002 | Bank C | USD | 101,813 | 157,040 | 55,227 | 9,027 | LIKELY | VOL | dealer vol about +1.53 pts from ours | Request the dealer's vol for this expiry/strike and compare with our surface |
| NBM-FXO-003 | Bank E | USD | -158,914 | -176,844 | -17,930 | 11,206 | LIKELY | BID_SIDE | gap = 0.40 vol pts against us (bid/offer side) | Ask whether the mark is mid or bid/offer; request a mid mark |
| NBM-FXO-004 | Bank A | USD | -152,739 | -152,014 | 725 | 6,103 | WITHIN_TOLERANCE |  |  |  |
| NBM-FXO-005 | Bank D | USD | 497,581 | 621,977 | 124,395 | 18,013 | EXPLAINED | NOTIONAL | matches a notional of 15,000,000 (booked 12,000,000) | Booking break: confirm notional against the confirmation; escalate to operations |
