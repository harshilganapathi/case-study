# Inventory totals and scrap share

Identical records count once. This report sums quantities (units), not rows. It describes the supplied historical export; no current inventory snapshot date is established.

## Main numbers

| Question | Answer |
| --- | ---: |
| How many units are on hand? | 105,643 |
| How many units were sold, before returns? | 35,454 |
| How many units were scrapped? | 16,531 |
| What share of observed disposed units was scrapped? | 31.80% |

## How the calculation works

**Inventory:** add positive whole-number quantities on Inventory records. Group the same units by module, subtype, warehouse or condition. These are different views of the same inventory; do not add their totals together.

**Scrap share:** scrapped units divided by (scrapped units + positive sold units). Returns/credits are excluded from this denominator, not subtracted from sales. Inventory is excluded because it has no observed final outcome.

For this export: **16,531 ÷ (16,531 + 35,454) = 31.80%**.

For a small illustration, one scrap record containing 20 units and eight sale records containing 10 units each give 20 ÷ (20 + 80) = 20%. Counting rows would give 1 ÷ 9 = 11.1%, which answers a different question.

Group shares use each group’s own sold and scrapped units. The overall share is calculated from overall units, never by averaging group percentages. With no sold or scrapped units, share is unavailable, not zero.

## Inventory by module

| Module | Units |
| --- | ---: |
| CORE | 42,410 |
| LPT | 22,225 |
| Non-HVM | 20,328 |
| FAN | 17,000 |
| QEC / LRU | 3,472 |
| Unknown | 208 |

## Scrap by module

| Module | Scrapped units | Sold units | Scrap share |
| --- | ---: | ---: | ---: |
| CORE | 12,199 | 21,078 | 36.66% |
| Non-HVM | 3,128 | 719 | 81.31% |
| LPT | 825 | 7,516 | 9.89% |
| FAN | 344 | 3,985 | 7.95% |
| QEC / LRU | 35 | 2,128 | 1.62% |
| Unknown | 0 | 28 | 0.00% |

## Parts with the most scrapped units

| Part | Scrapped units | Sold units | Scrap share |
| --- | ---: | ---: | ---: |
| P263G01 | 562 | 999 | 36.00% |
| P333P03 | 501 | 186 | 72.93% |
| 2100M96P02 | 492 | 268 | 64.74% |
| P336P05 | 492 | 259 | 65.51% |
| P337P05 | 486 | 319 | 60.37% |
| P338P05 | 440 | 209 | 67.80% |
| P332P03 | 424 | 215 | 66.35% |
| 2100M96P05 | 410 | 542 | 43.07% |
| P109P38 | 390 | 544 | 41.76% |
| 338-108-304-0 | 382 | 1,316 | 22.50% |

## Coverage and interpretation

- 36,752 deduplicated records were read; 36,488 have positive whole-number quantity. 264 others are listed in `quantity_exclusions.csv` with source references and reasons.
- Inventory: excluded 1 negative-quantity records, 4 zero-quantity records and 0 unavailable/fractional quantities.
- Invoiced: excluded 259 negative-quantity records, 0 zero-quantity records and 0 unavailable/fractional quantities.
- Scrapped: excluded 0 negative-quantity records, 0 zero-quantity records and 0 unavailable/fractional quantities.
- Missing classifications display as Unknown and remain included. Missing repair amounts, dates or condition do not remove an otherwise valid quantity from these two metrics.
- 2 unresolved source cases remain quarantined by the audit and are absent from these totals.
- This scrap share compares observed outcomes across the export. It is not the probability that a newly acquired part will fail: there are no matched lifecycle cohorts or scrap dates.
- A high share with only one or two disposed units is weak evidence. Every breakdown includes its unit denominator and record counts.
- The inventory breakdowns reconcile to the inventory total; scrap breakdowns reconcile to both sold and scrapped totals. CSV shares are fractions: 0.20 means 20%.

Reproduce with `python3 -m src.metrics`. This first rebuilds the audit from the raw CSV. Use `--input`, `--output-dir`, and `--audit-dir` for another same-schema export.
