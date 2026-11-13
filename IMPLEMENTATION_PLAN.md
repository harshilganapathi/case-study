# Parts inventory implementation guide

The planned application is implemented locally. The final scope is Streamlit, reproducible standard-library Python cleaning, SQLite SQL quantity breakdowns, exact Decimal financial calculations, and an explainable part review queue. See README.md for launch instructions and reports/VALIDATION.md for the verification actually achieved in this environment.

## Required behavior and implementation

| Requirement | Implementation |
| --- | --- |
| Reproducible data layer | src/ingest.py, src/clean.py and src/audit.py; schema checks, split reconstruction, quarantine and source accounting |
| Identical records count once | Audit keeps all source occurrences; calculation_records.csv selects one representative per exact reconstructed-field group |
| Scrap view | src/metrics.py SQLite queries; quantities, module/subtype breakdowns and top scrapped parts |
| Repair economics | src/economics.py; positive-sale contribution, weighted margins, weak transactions, credits and cost coverage |
| Inventory | Positive stock by module/subtype/warehouse/condition, locations and quantity exceptions |
| Sell-through comparison | src/timing.py; overhaul-to-invoice intervals versus supplied expected days, paired comparisons and coverage |
| Decision support | src/decision_support.py; independently aggregated stock/history, review reasons, supporting counts and configurable thresholds |
| Optional scrap baseline | src/scrap_model.py; smoothed Module/SubType outcome-record classifier, part-disjoint holdout, constant comparator, calibration and stock scores |
| Local application | app.py; seven views, scope-aware filters, file upload, content-keyed cache, charts, detail and CSV exports |
| Single-command launch | run.sh; creates a local virtual environment, installs requirements.txt and launches Streamlit |
| Submission | README.md, tests/, generated reports and scripts/package_submission.py |

## Accepted business decisions

- Identical reconstructed source records are genuine duplicates and contribute once. Keep the first occurrence and all source references.
- OH_DATE is assumed to be the overhaul date. The interval ends at invoice; inventory receipt and snapshot dates are not inferred.
- Negative invoice quantities are possible credits. Financial amounts keep their signs, while credits stay separate from positive-sale performance.
- Reported zero repair costs remain included with visible coverage. Missing costs remain unknown.
- Scrap share uses scrapped plus positive sold units; inventory and returns are outside the denominator.
- Review thresholds are initial assumptions: margin below 20% or zero-revenue negative contribution with five eligible sale records, or scrap share at least 50% with ten disposed units. They are editable in the app.
- Timing expectations above 3,650 days are excluded only from paired comparisons by default. Long observed intervals stay flagged and included.
- The scrap baseline weights completed outcome records equally and uses only Module/SubType. It holds out whole part numbers, then separately refits on full history for stock scores. Scores are experimental historical associations, without a validated future time horizon.

## App workflow

Start with Overview, inspect Scrap and Repair economics, then examine Inventory & timing. Use Review queue to inspect parts with evidence-backed concerns and drill into locations and full history. Data quality exposes file-wide accounting and source-level exceptions.

Sidebar module/subtype/search filters select the displayed records. Invoice-date filters belong only to invoiced views. Warehouse and condition filters apply only to stock. Review-queue history intentionally uses all records for the stock-selected part numbers to avoid pretending that sold history is warehouse- or condition-matched.

## Checks and delivery

Unit tests cover source corruption, quantity and amount conventions, deduplication, missing/zero values, weighted margins, paired date statistics, review evidence/ranking and filter/export behavior. Optional live AppTest checks cover every view, empty filters, rule changes and bad-schema handling when Streamlit is installed. The final suite and real-browser visual review have passed; the completed evidence and scope are recorded in reports/VALIDATION.md.

The submission ZIP includes source, tests, the unchanged dataset/spec copy, configuration, launch script and generated reports. It excludes local environments, caches, hidden machine files and nested archives. Rebuild with python3 scripts/package_submission.py.
