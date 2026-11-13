# Submission notes

## Run

Requires Python 3.11+ with `venv` and `pip`. Extract the ZIP or clone the repository, enter its directory, and run **`./run.sh`** on macOS/Linux. It creates the environment, installs pinned direct dependencies, and starts http://localhost:8501. First installation needs PyPI access. [Windows instructions](SETUP.md) and [screenshots](SCREENSHOTS.md) are available separately.

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

**Optional scrap baseline:** a smoothed Module/SubType model learns recorded scrap-versus-sale outcomes, one deduplicated record per observation. Condition, prices, costs, dates, quantity, and identifiers are excluded as predictors. A deterministic 80/20 split keeps whole part numbers apart. On 1,753 held-out records across 354 parts, Brier score is 0.1415 versus a constant comparator's 0.2611; ROC AUC is 0.8608. The app shows calibration bins and refits on full history for stock scoring. CSVs include scores and holdout predictions. See the [model report](../reports/metrics/SCRAP_MODEL_EXPLAINED.md).

The checked submission passed **79 tests**, **35 full-data behavioral checks**, and a Chrome review covering all seven views, filters, and empty states. Additional browser regressions reconcile downloads and zero-revenue losses. See [validation scope and evidence](../reports/VALIDATION.md).

Receipt/snapshot/scrap dates, reliable lifecycle identifiers, acquisition costs, future repair quotes, and recovery values are missing. The model estimates completed-outcome record patterns; no time horizon or validated future scrap probability is claimed. No stock-aging calculation or automatic repair-or-scrap recommendation is made. Next steps: confirm definitions and duplicates; validate queue rules and the model prospectively; improve coverage; lock dependencies; test more environments. Team deployment needs authentication, controlled uploads, and retained audit versions.

## AI use

I used Codex throughout the project. I drove the direction and made the final decisions.
