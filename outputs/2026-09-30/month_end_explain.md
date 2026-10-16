# Month-end value-change explain — 2026-08-28 to 2026-09-30

Portfolio value in USD, own model, full revaluation per step. Fictional portfolio; FX and swaption vols synthetic and held constant, so the vol step is zero. USD curve is a Treasury proxy.

## Market moves

| market | t0 | t1 |
|---|---|---|
| GBP 5y zero (%) | 4.3781 | 4.7357 |
| USD 5y zero (%, UST proxy) | 4.4488 | 5.0447 |
| GBP/USD spot | 1.3583 | 1.3286 |

## Explain

| step | usd | reverse_order |
|---|---|---|
| value at T0 | 5,645,075 | 5,645,075 |
| carry | -80,082 | -80,082 |
| gbp_rates | 228,966 | 225,948 |
| usd_rates | -65,701 | -69,719 |
| fx_spot | -157,584 | -150,548 |
| vols | 0 | 0 |
| new_trades | -128,127 | -128,127 |
| value at T1 | 5,442,547 | 5,442,547 |
| residual | 0 | 0 |

Steps run in the order shown; `reverse_order` switches FX before rates. The difference between the two columns is the cross effect, which a sequential explain assigns to whichever step comes later.

## Notes

- No coupons, deliveries or expiries fell in the period (checked), so no cash left the book.

## By trade

| trade_id | product | status | value_t0 | carry | gbp_rates | usd_rates | fx_spot | vols | new_trades | value_t1 |
|---|---|---|---|---|---|---|---|---|---|---|
| NBM-IRS-001 | OIS | existing | 616,974 | 1,558 | 784,071 | 0 | -30,581 | 0 | 0 | 1,372,022 |
| NBM-IRS-002 | OIS | existing | -294,465 | -730 | -262,687 | 0 | 12,164 | 0 | 0 | -545,718 |
| NBM-IRS-006 | OIS | existing | 138,895 | 470 | -657,396 | 0 | 11,295 | 0 | 0 | -506,736 |
| NBM-IRS-007 | OIS | existing | 874,217 | -2,559 | 0 | 1,153,512 | 0 | 0 | 0 | 2,025,170 |
| NBM-IRS-010 | OIS | existing | 139,941 | 2,866 | 0 | -578,000 | 0 | 0 | 0 | -435,192 |
| NBM-FXF-001 | FXFWD | existing | 432,748 | -107 | 227 | 3,517 | -294,664 | 0 | 0 | 141,721 |
| NBM-FXF-002 | FXFWD | existing | -513,505 | 2,241 | 4,024 | -25,954 | 731,510 | 0 | 0 | 198,316 |
| NBM-FXF-003 | FXFWD | existing | 1,009,183 | 1,148 | -11,569 | 27,724 | -434,248 | 0 | 0 | 592,239 |
| NBM-FXF-004 | FXFWD | existing | -103,372 | 891 | 24,776 | -36,413 | 226,186 | 0 | 0 | 112,068 |
| NBM-FXO-001 | FXOPT | existing | 415,926 | -36,486 | 175 | 3,132 | -212,890 | 0 | 0 | 169,857 |
| NBM-FXO-002 | FXOPT | existing | 110,932 | -37,198 | 279 | -1,870 | 69,133 | 0 | 0 | 141,277 |
| NBM-FXO-003 | FXOPT | existing | -369,868 | 41,556 | 4,892 | -11,968 | 152,474 | 0 | 0 | -182,914 |
| NBM-FXO-004 | FXOPT | existing | -124,792 | 8,612 | -3,880 | 6,121 | -40,393 | 0 | 0 | -154,332 |
| NBM-FXO-005 | FXOPT | existing | 715,982 | -18,892 | -41,843 | 56,169 | -180,522 | 0 | 0 | 530,895 |
| NBM-SWO-001 | SWPTN | existing | 556,891 | -25,976 | 304,710 | 0 | -18,219 | 0 | 0 | 817,405 |
| NBM-SWO-002 | SWPTN | existing | -151,972 | 11,499 | 84,065 | 0 | 1,230 | 0 | 0 | -55,177 |
| NBM-SWO-003 | SWPTN | existing | 1,700,890 | -30,319 | 0 | -661,672 | 0 | 0 | 0 | 1,008,899 |
| NBM-XCY-001 | XCCY | existing | 565,953 | 596 | -0 | 0 | -594,834 | 0 | 0 | -28,286 |
| NBM-XCY-002 | XCCY | existing | -75,483 | 747 | -880 | 0 | 444,777 | 0 | 0 | 369,162 |
| NBM-FXF-005 | FXFWD | new (2026-09-10) | 0 | 0 | 0 | 0 | 0 | 0 | 114,693 | 114,693 |
| NBM-SWO-004 | SWPTN | new (2026-09-22) | 0 | 0 | 0 | 0 | 0 | 0 | -242,820 | -242,820 |
