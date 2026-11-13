# Submission notes

## Run

Requires Python 3.11+ with `venv` and `pip`. Extract the ZIP or clone the repository, enter its directory, and run **`./run.sh`** on macOS/Linux. It creates the environment, installs pinned direct dependencies, and starts http://localhost:8501. First installation needs PyPI access. [Windows instructions and screenshots](../README.md) are in the expanded README.

The supplied CSV loads automatically. Upload a same-schema replacement in the sidebar or set `PARTS_DATA_PATH`. No account, external API, or AI service is used at runtime.

## Data handling

**39,338 raw rows → 37,003 reconstructed/complete records → 36,752 after removing 251 duplicate copies.** Two ambiguous pairs, comprising four source rows, remain quarantined. The raw CSV is unchanged.

Strict UTF-8 parsing falls back to Windows-1252. Require the exact header and unpadded Type labels; unknown statuses are quarantined. Dates accept M/D/YYYY or YYYY-MM-DD. Recover 2,331 split pairs only when their structure passes validation. Preserve source references, missing condition, and unlabelled continuation values. Assume identical reconstructed records are repeated export copies; compare all source fields before normalization and retain the first once. Part number alone never establishes duplication.

Preserve identifier strings and unknown classifications. Report negative-quantity invoices separately as possible returns/credits. Missing cost stays unknown; reported zero stays zero with coverage shown. Invalid quantities, amounts, dates, and expectations have metric-specific exclusions. Rebuild the audit and reports with `python3 -m src.metrics`.

## Definitions and decision support

**Scrap share:** positive scrapped units / (positive scrapped + positive sold units), excluding inventory and returns. The result is **31.80%**. This describes observed outcomes, not a matched-cohort failure probability.

**Repair contribution:** extended sales minus extended repair cost. Aggregate margin divides total contribution by total sales; extended amounts are not multiplied by quantity again. Missing acquisition cost, freight, and overhead prevent total-profit calculation. Zero revenue has no percentage margin. Currency is unspecified; aggregation assumes comparable amounts.

**Inventory:** positive whole-number Inventory quantities, totaling **105,643 units**. Module, subtype, warehouse, and condition are alternative breakdowns of that total.

**Timing:** invoice date minus OH_DATE, assuming OH_DATE means overhaul date. It is not receipt-to-sale time or current stock age. Exclude returns, invalid dates, and negative intervals. Compare with the supplied `AvgNoofSalesDays`, whose origin is unknown. Median valid interval: **60 days**. Unusable expectations do not remove valid observed intervals.

**Review queue:** independently aggregate stock and history by part. At least five usable positive-quantity sale records support a margin-below-20% flag or a zero-revenue/negative-contribution flag. At least ten disposed units support a scrap-share-at-least-50% flag. Defaults are editable. Rank by triggered-rule count, stock quantity, then part number. The default flags **123 parts**; **2,479 of 2,957 stocked parts lack minimum support**.

Show reasons, denominators, cost coverage, locations, and history. Insufficient evidence and no rule triggered are distinct; neither means low risk. A single bulk record can meet the unit minimum. Ranking is inspection priority, not expected loss. Stock filters select locations; history uses full part history without condition matching or a date window.

## Verification and limits

The checked submission passed **65 tests**, **31 full-data behavioral checks**, and a Chrome review covering all six views, filters, and empty states. Additional browser regressions reconcile downloads and zero-revenue losses. Tests/full-data checks were rerun from the extracted ZIP. See [validation scope and evidence](../reports/VALIDATION.md).

Receipt/snapshot/scrap dates, reliable lifecycle identifiers, acquisition costs, future repair quotes, and recovery values are missing. No stock-aging calculation, validated scrap prediction, or automatic repair-or-scrap recommendation is claimed. Next steps: confirm definitions and duplicate authenticity; validate queue thresholds/ordering with a manager; improve history coverage; lock transitive dependencies; test more environments. Team deployment needs authenticated internal hosting, controlled uploads, and retained audit versions.

## AI use

I used AI extensively for inspection, planning, implementation, tests, browser automation, and documentation. Duplicate treatment and OH_DATE meaning remain assumptions, not verified company definitions. Reproducible checks establish behavior; I remain responsible for explaining the code and its limits.
