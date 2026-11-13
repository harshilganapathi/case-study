# Overhaul to sale timing explained

**OH_DATE is assumed to be the overhaul date**. The export does not independently verify this business definition. The calculation measures calendar days from overhaul to invoice; receipt dates and current stock age are not inferred.

## What we calculate

**Observed interval = invoice date − OH_DATE**, in calendar days. For a Jan 1 OH date and an Apr 1 invoice in a non-leap year, this is 90 days. If the supplied expectation is 60 days, the paired difference is +30 days.

The supplied `AvgNoofSalesDays` is used as the comparison benchmark; the fields may use different starting points. A positive difference means the recorded interval exceeds the supplied expectation; it does not establish slow inventory or a missed sales target.

## Results

| Measure | Result |
| --- | ---: |
| Positive-quantity invoice records considered | 7,220 |
| Records with a usable OH-to-invoice interval | 6,055 |
| Median interval across usable records | 60 days |
| Records with both usable interval and expectation | 6,050 |
| Median observed interval on paired records | 60 days |
| Median supplied expectation on paired records | 97 days |
| Median of individual paired differences | -25 days |
| Paired intervals above supplied expectation | 33.79% |

The median paired difference is calculated from each record’s observed-minus-expected difference. It is not the difference between two independently calculated medians. Each deduplicated transaction counts once in these timing statistics; a bulk quantity does not provide additional independently observed sale dates.

## Paired comparison by module

| Module | Usable intervals | Paired records | Median paired difference in days | Above expected |
| --- | ---: | ---: | ---: | ---: |
| CORE | 2,262 | 2,257 | -19 | 33.54% |
| FAN | 1,431 | 1,431 | -35 | 38.43% |
| LPT | 587 | 587 | -23 | 31.35% |
| Non-HVM | 437 | 437 | -40 | 30.89% |
| QEC / LRU | 1,338 | 1,338 | -32 | 31.24% |

## What is excluded and preserved

- 7,479 deduplicated invoice records were read. 1,424 cannot enter the observed-interval calculation. The exclusion CSV lists every source reference and all applicable reasons.
- Returns/nonpositive quantities, invalid/fractional quantities, missing or invalid dates, and negative date intervals are excluded. A same-day interval is valid zero days.
- 5 otherwise valid intervals have an unusable expectation. Their observed intervals remain included in the overall interval statistics.
- Expected days must be positive and no greater than 3,650. This configurable review threshold follows the audit rule; it is an assumption. Values are neither replaced nor capped.
- 3 observed intervals exceed that threshold. They remain included and flagged: a long interval alone does not prove a bad date.
- 2 unresolved source cases remain absent from the calculation population. Missing classifications display as Unknown. Identical records count once.
- No stock age is calculated: receipt dates and an inventory snapshot date are unavailable. We do not subtract OH dates from today’s date.
- These are records of completed positive-quantity sales. They cannot establish how long unsold inventory will take to sell. The origin and calculation window of `AvgNoofSalesDays` are also unknown.

## Reproduce and inspect

Run `python3 -m src.metrics`; use `--max-expected-days 3650` to set the review threshold. The same threshold is used in the audit and timing comparison.

- `timing_details.csv`: every valid observed interval, expected value, comparison difference and flags.
- `timing_observed_exclusions.csv`: invoices without a usable interval, including returns.
- `timing_comparison_exclusions.csv`: valid intervals excluded only from paired comparisons.
- `timing_by_module.csv`, `timing_by_subtype.csv`, `timing_by_module_subtype.csv`: coverage and statistics for each group.
- `timing.json`: results, source hashes and coverage checks.
