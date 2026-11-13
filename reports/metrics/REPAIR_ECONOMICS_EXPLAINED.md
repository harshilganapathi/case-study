# Repair economics explained

This answers: how much sales value remains after reported repair costs? Identical records count once. Amounts use the export’s unspecified currency; aggregation assumes they are comparable because no currency field is available.

## Positive sales

| Measure | Value |
| --- | ---: |
| Sale records | 7,220 |
| Sales amount | 129,530,115.10 |
| Repair cost | 31,916,784.88 |
| Remaining after repair | 97,613,330.22 |
| Repair contribution margin | 75.36% |

**Repair contribution = sales amount − repair cost.** Use the extended amounts, which already cover the transaction quantity. Do not multiply them by quantity again.

**Margin = total contribution ÷ total sales.** For a sale of 1,000 with repair cost 700, contribution is 300 and margin is 30%. For a sale of 500 with repair cost 700, contribution is −200 and margin is −40%. Group margins are calculated from group totals, never averaged from individual percentages.

This is not total profit: purchase costs, freight and overhead are unavailable. A high repair contribution margin therefore does not establish a profitable transaction.

## Zero reported repair cost

1,207 positive-quantity sale records report zero repair cost. They remain included as reported, but their contribution margin needs care. Zero might mean no repair spend; it does not establish zero acquisition or total cost.

| Population | Records | Sales | Repair cost | Contribution margin |
| --- | ---: | ---: | ---: | ---: |
| Zero reported repair cost | 1,207 | 10,906,510.26 | 0.00 | 100.00% |
| Positive reported repair cost | 6,013 | 118,623,604.84 | 31,916,784.88 | 73.09% |

## Breakdown by module

| Module | Sale records | Sales | Repair cost | Contribution | Margin |
| --- | ---: | ---: | ---: | ---: | ---: |
| CORE | 2,371 | 57,561,927.84 | 12,716,051.80 | 44,845,876.04 | 77.91% |
| FAN | 1,481 | 30,687,310.78 | 6,235,244.64 | 24,452,066.14 | 79.68% |
| LPT | 657 | 17,433,340.78 | 3,643,604.42 | 13,789,736.36 | 79.10% |
| Non-HVM | 626 | 2,398,391.85 | 854,736.12 | 1,543,655.73 | 64.36% |
| QEC / LRU | 2,078 | 21,447,803.85 | 8,467,147.90 | 12,980,655.95 | 60.52% |
| Unknown | 7 | 1,340.00 | 0.00 | 1,340.00 | 100.00% |

## Weak or negative results

165 positive-quantity sale records have repair costs above sales. 497 records trigger review in total. The configurable weak-margin threshold is 20.00%; this is a review assumption, not a business-provided target. Zero-sales records are also flagged, with no percentage margin.

The examples below show the largest negative transaction contributions. Every weak transaction is exported with its source reference. Part-level totals are exported separately, because profitable sales of a part can offset individual losses.

| Source records | Part | Sales | Repair cost | Contribution | Margin |
| --- | --- | ---: | ---: | ---: | ---: |
| [4694] | 442369 | 6,500.00 | 48,950.00 | -42,450.00 | -653.08% |
| [837] | 828300-5 | 1,700.00 | 25,450.00 | -23,750.00 | -1397.06% |
| [7200] | 329695-5 | 1,500.00 | 20,890.00 | -19,390.00 | -1292.67% |
| [4611] | 849589 | 1,500.00 | 18,987.33 | -17,487.33 | -1165.82% |
| [7739] | 3031863-002 | 13,500.00 | 29,970.77 | -16,470.77 | -122.01% |
| [2145] | 6773F010000 | 1,000.00 | 16,772.04 | -15,772.04 | -1577.20% |
| [4795] | C25175000-3 | 950.00 | 15,233.26 | -14,283.26 | -1503.50% |
| [4612] | 849589 | 5,267.16 | 18,987.33 | -13,720.17 | -260.49% |
| [836] | 828300-5 | 13,044.43 | 25,450.00 | -12,405.57 | -95.10% |
| [6870] | 3031863-002 | 1,900.00 | 13,568.22 | -11,668.22 | -614.12% |

## Returns and signed reconciliation

Negative-quantity invoices with nonpositive sales/costs are treated as possible credits. They remain separate from positive-sale margins. This interpretation is unconfirmed. Reported extended amounts retain their signs; no negative × negative multiplication is used. The signed total is a reconciliation, not a second positive-sale performance measure.

| Population | Records | Signed sales | Signed repair cost | Signed contribution |
| --- | ---: | ---: | ---: | ---: |
| Positive sales | 7,220 | 129,530,115.10 | 31,916,784.88 | 97,613,330.22 |
| Possible credits | 259 | -2,473,772.83 | -897,962.25 | -1,575,810.58 |
| Combined signed total | 7,479 | 127,056,342.27 | 31,018,822.63 | 96,037,519.64 |

## Eligibility and files

- 7,479 deduplicated invoice records were considered; 0 were excluded from contribution calculations. See `economics_exclusions.csv` for every source reference and reason.
- Contribution requires a valid nonzero whole quantity and both extended amounts. Missing amounts remain unknown; they never become zero. Conflicting quantity/amount signs are excluded and shown for review. Missing classifications display as Unknown.
- Positive-quantity rows may have zero sales; their contribution remains included, but an individual margin is unavailable. There is no division by zero.
- 2 source cases remain unresolved and are absent from the audited calculation population. No estimated amounts have been added for them.
- `economics_by_module.csv`, `economics_by_subtype.csv`, and `economics_by_module_subtype.csv` contain positive-sale group totals and margins.
- `economics_by_part.csv` contains all part totals. `economics_part_review.csv` contains parts with weak aggregate results, including their sales record counts.
- `economics_positive_sales.csv`, `economics_credits.csv` and `economics_weak_transactions.csv` provide transaction detail and source references.
- `economics.json` contains all results. Reproduce with `python3 -m src.metrics`; change the threshold with `--weak-margin 0.20`.

A review flag means inspect the history. It is not a repair-or-scrap instruction, a forecast, or evidence of a safety issue.
