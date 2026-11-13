# Parts inventory data audit

The audit recovers only structurally validated split records, counts identical records once under the documented duplicate-copy assumption, and preserves uncertain values. Each downstream metric applies its own eligibility rules to the audited calculation population.

## Source and reproducibility

- Source: `Case_Study_Dataset.csv`; SHA-256 `45b1002418585e2e2d1193edd9d927dc3cc97b505b3ab5e310cb5e0637f7cfe3`.
- Decoding: `cp1252` (strict UTF-8 first, explicit Windows-1252 fallback, unless an encoding override is supplied). Successful decoding does not prove the original encoding.
- Rule version: `audit-v3-oh-overhaul`; expected-days review threshold: 3,650 days. This is a configurable review threshold, not an established business limit.
- Run `python3 -m src.audit`. Uses only the Python standard library. Outputs are UTF-8; numbers use decimal arithmetic; dates are ISO formatted. Source references are CSV record ordinals with header = 1, not physical line numbers.
- Raw source checksum was verified unchanged after the run.

## Record accounting

| Measure | Count |
| --- | ---: |
| raw data rows | 39,338 |
| accepted logical records | 37,003 |
| unchanged records | 34,672 |
| reconstructed records | 2,331 |
| quarantined cases | 2 |
| quarantined source rows | 4 |
| accepted source rows | 39,334 |
| calculation records | 36,752 |
| duplicate copies excluded from calculations | 251 |

Every source row is accounted for exactly once, including quarantine. Recovered pairs become one logical record; this is not deduplication.

## Reconstruction and exceptions

The common rule recovered 2,331 pairs by taking the first five fields from the head, quantity from the continuation, leaving condition unknown, and mapping the remaining fields through expected sales days. It requires valid numeric/date shapes, recognized classifications, tag number and status-specific fields. It does not infer condition from neighboring records.

The continuation also contains an extra field with no source header. It is retained as `unlabelled_tail`, never assigned to a named business column. 398 recovered records have a non-null value in it.

2 cases are quarantined. Neither amount ratios nor adjacent quantities are used to fill missing quantities. Malformed, unmatched or ambiguous records are preserved in full with reasons in `quarantine.jsonl`.

| Accepted status | Records | Reconstructed |
| --- | ---: | ---: |
| Inventory | 24,917 | 2,129 |
| Invoiced | 7,537 | 202 |
| Scrapped | 4,549 | 0 |

Example recoveries (see full original and mapped fields in `reconstructions.jsonl`):

| Source records | Part | Quantity | Condition | Sales amount | Module |
| --- | --- | ---: | --- | ---: | --- |
| (61, 62) | 9725M79P05 | 1 | Unknown | 225 | Non-HVM |
| (174, 175) | 338-020-706-0 | 1 | Unknown | 6500 | Non-HVM |
| (177, 178) | 338-020-706-0 | 1 | Unknown | 6500 | Non-HVM |

Quarantine source records: (4723, 4724), (4733, 4734).

## Duplicate treatment

There are 235 exact candidate groups containing 486 records. Assuming identical records are repeated export copies, 251 extra copies are excluded from calculations. The first source occurrence is kept; all copies remain traceable in the audit file. Comparison uses reconstructed source field values plus the unlabelled tail, before normalization.

The right-hand values below are the authoritative calculation totals after deduplication. Quarantine is excluded from both columns. No currency is specified by the export.

| Status | Signed quantity before deduplication | Calculation quantity | Sales before deduplication | Calculation sales |
| --- | ---: | ---: | ---: | ---: |
| Inventory | 105868 | 105634 | Unavailable | Unavailable |
| Invoiced | 34221 | 34155 | 127889177.27 | 127056342.27 |
| Scrapped | 16531 | 16531 | Unavailable | Unavailable |

## Signed amounts and quantity controls

Negative invoiced quantities/prices are preserved as possible credits. Their business meaning remains unconfirmed. Never turn negative × negative into positive revenue. Observed extension conventions are checked both as `quantity × unit` and `abs(quantity) × signed unit`, within 0.01 amount units.

| Status | Amount field | Checked | Naive mismatches | Signed convention mismatches |
| --- | --- | ---: | ---: | ---: |
| Inventory | Repair Ext Cost | 24,724 | 0 | 0 |
| Inventory | Extended Sales Price | 0 | 0 | 0 |
| Invoiced | Repair Ext Cost | 7,479 | 155 | 0 |
| Invoiced | Extended Sales Price | 7,479 | 259 | 0 |
| Scrapped | Repair Ext Cost | 0 | 0 | 0 |
| Scrapped | Extended Sales Price | 0 | 0 | 0 |

| Status | Positive quantity | Negative quantity | Net quantity |
| --- | ---: | ---: | ---: |
| Inventory | 105643 | -9 | 105634 |
| Invoiced | 35454 | -1299 | 34155 |
| Scrapped | 16531 | 0 | 16531 |

Accepted controls reconcile to unchanged-record controls plus recovery controls for each status and numeric amount. Complete controls come from original field positions; recovery controls are separately identified. Quarantined cases are excluded from accepted controls; their original fields are preserved rather than included through an uncertain mapping. Accepted controls therefore do not represent the entire export.

Calculation totals equal accepted totals minus excluded duplicate copies. The extension checks, quantity totals and coverage below describe the deduplicated population.

## Data coverage and limitations

| Status | Missing condition | Zero repair unit cost | Missing/invalid expected days | Expected days maximum |
| --- | ---: | ---: | ---: | ---: |
| Inventory | 2,124 | 21,496 | 1,599 | 131638 |
| Invoiced | 202 | 1,311 | 49 | 131638 |
| Scrapped | 0 | 0 | 46 | 813 |

- 27 records have expected days outside the configurable review range. Raw values are retained; this audit does not cap or impute them.
- Zero repair amounts are reported zeros, not proof of free repair or total cost. Missing repair amounts remain unknown. No acquisition cost, scrap recovery value or currency field is supplied.
- Invoiced records have no warehouse; scrap records lack financial amounts and dates. These are status-specific coverage limitations, not fields to fill from unrelated rows.
- There is no confirmed receipt date, snapshot date, or scrap date. `OH_DATE` is assumed to be the overhaul date. The overhaul-to-invoice interval measures days after overhaul, rather than confirmed time in inventory. No present-day stock aging or matched-cohort scrap probability is justified.
- Placeholder serials are not unique identifiers; part number is a product identifier, not an event identifier. No lifecycle joins or serial-based deletions were attempted.
- Supplied `Non-HVM` classifications are retained. Missing classifications stay empty for later display as Unknown; they are not inferred from other occurrences of a part.

### Invoice date coverage

Invoiced records span 2021-02-05 through 2023-08-29. There are 6,219 valid OH dates, 1,260 missing OH dates and 0 invalid OH dates. Invalid date strings remain visible and flagged; they are not silently converted to missing dates.

## Audit outputs and metric use

- `audit_records.csv`: normalized candidate records, provenance, duplicate groups and flags. All copies are preserved; `included_in_calculations` identifies the kept occurrence.
- `calculation_records.csv`: one occurrence per identical record, with source references for all copies. Use this file for downstream calculations; metric-specific exclusions still apply.
- `quarantine.jsonl`: original unresolved rows and reasons.
- `reconstructions.jsonl`: all repaired pairs, original rows, mappings and unlabelled values.
- `duplicate_candidates.csv`: every duplicate group with source references and excluded amounts.
- `audit.json`: before/after profiles, flags, checks, raw/recovered controls and deduplication reconciliation.
- `manifest.json`: source and output hashes for repeatability checks.

The application applies metric-specific eligibility to these deduplicated records. Scrap, repair contribution, inventory, overhaul-to-invoice timing and review-queue definitions are documented in README.md and the metric reports. Credits, unknown costs and excluded records remain available for inspection.
