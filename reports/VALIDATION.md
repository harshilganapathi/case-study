# Completed application validation

The app was reviewed in a real, separate Chrome browser using Playwright against **http://127.0.0.1:8501/**. This report describes the final reviewed code.

The final zero-revenue regression used a fresh app process on **http://127.0.0.1:8614/** to verify the updated calculation module.

## Results

| Check | Result |
| --- | --- |
| Automated Python and Streamlit AppTest suite | **79 passed, zero skipped**, including HTTP middleware and scrap-model regressions |
| Full supplied-export behavioral checks | **35 passed** |
| Real-browser capture sequence | **44 checks passed**, including 42 captured UI states and two CSV downloads; three additional targeted checks passed |
| JavaScript page errors during the successful capture run | **None** |
| Visual inspection | Original six views reviewed previously; seven-view captures refreshed and new baseline view inspected |
| Responsive checks | 1,440-pixel desktop; 1,024-pixel financial-card readability; 390-pixel mobile overview |
| CSV reconciliation | Overview inventory export totals **105,643 units** |
| Weak-margin filter | At zero threshold, downloaded table contains exactly **165 negative-contribution sales** |
| Narrow invoice-date filter | August 1–29, 2023 positive-sale amount equals independent source sum **9,875,968.42** |
| Source replacement | Synthetic valid upload shows **7 units**; removing it restores **105,643 units** |
| Zero-revenue loss regression | Five and ten eligible loss records trigger **Review**; downloaded margins remain unavailable; removing uploads restores **123 Review parts** |
| Invalid input | A synthetic bad-header upload shows a friendly load error |
| Scrap baseline | Part-disjoint holdout: **354 test parts / 1,753 records**, no part overlap; Brier **0.1415** vs constant **0.2611**, ROC AUC **0.8608** |
| Baseline exports | Browser stock CSV has **2,957 groups / 105,643 units**; holdout CSV matches all **1,753** generated predictions |
| Raw dataset | Unchanged SHA-256 `45b1002418585e2e2d1193edd9d927dc3cc97b505b3ab5e310cb5e0637f7cfe3` |

## Issues fixed and rechecked

- Replaced generated chart-axis names and raw table headings with readable labels.
- Changed additive sales/cost and timing comparisons to side-by-side bars. Ordered bars by value so top-part charts read from largest down.
- Changed financial summary cards to two rows: full amounts now remain readable in a narrower desktop window.
- Displayed each selected part’s complete review reasons outside the horizontally scrollable table, with supporting history counts and stock locations.
- Added a labeled 0–1,000-day focus for the timing scatterplot, plus a full-range checkbox. All eligible records remain in statistics and CSV exports.
- Removed the duplicate empty-queue message and disabled the full-queue download when no stock matches.
- Added regression tests for readable review reasons and unchanged statistics when switching chart focus.

The presentation changes leave the underlying quantity and financial calculations unchanged. The final review-queue correction additionally flags supported zero-revenue histories with negative contribution, while keeping percentage margin unavailable. Regression fixtures cover five and ten such sale records, insufficient history, and zero-revenue histories without losses.

The final input-format regression accepts canonical YYYY-MM-DD dates alongside M/D/YYYY. Invoice-date controls share the timing calculation's normalized-date/audit-flag policy, so invalid or noncanonical preserved text cannot enter date-filtered totals. The original supplied-export quantities and financial totals remain unchanged.

## HTTP runtime recheck — November 13, 2026

Streamlit 1.57.0 with Starlette 1.10.0 could send an image or precompressed response body without its response-start headers. Two new middleware tests reproduced the failure. Streamlit 1.62.0 uses the upstream native gzip handling and passes both tests; the tested Starlette version is pinned alongside it. See the [upstream change](https://github.com/streamlit/streamlit/pull/16462).

After upgrading and restarting the server, all 67 tests, 31 full-export checks, and the 39-check Chrome sequence passed. No JavaScript page errors or ASGI tracebacks were recorded in that run. Both localhost and 127.0.0.1 health endpoints returned HTTP 200. A stale imported helper in the old running process was cleared by restarting; no inventory calculation changes were needed.

`browser-review/runtime/checks.json` records this recheck and installed versions. New captures remain local under `.cache/runtime-review/`; the nine selected submission screenshots are retained from the earlier visual review. The README was left unchanged.

## Optional scrap baseline — November 13, 2026

Added the smoothed Module/SubType outcome-record model, a seventh view, category evidence/fallbacks, held-out calibration, and CSV exports. Tests cover unit-versus-record weighting, predictor leakage, disjoint/deterministic part splits, held-out label perturbation, probability metrics, missing categories, single-class/empty history, stock filters, and report provenance. The independent review reproduced the formulas, scores, pairwise AUC and train/test isolation without finding a model-source blocker.

The 44-check Chrome sequence passed after adding the view. Final targeted checks verified the numeric calibration chart, downloaded all held-out predictions, and rechecked financial cards at 1,024 pixels. Browser JavaScript/HTTP errors and server tracebacks were absent. The new view is an experimental classifier of completed outcome records, not a calibrated future lifecycle probability. See `metrics/SCRAP_MODEL_EXPLAINED.md` for weighting, formulas, evaluation and limits.

## Final submission recheck after README trim

The root README was reduced to 623 words; extended setup and screenshots moved to `docs/SETUP.md` and `docs/SCREENSHOTS.md`. The app now displays the OH_DATE assumption directly beneath every view title and labels timing as overhaul-to-invoice, explicitly separating it from stock age and receipt-to-sale time.

On this final application code, the submitting agent reran all **79 tests**, **35 full-export checks**, and the complete **44-check Chrome sequence** with **42 captured states** and two CSV downloads. Three targeted checks also passed: the final model chart/stock view, held-out prediction download, and financial cards at 1,024 pixels. The visible timing assumption was checked on initial load. Overview and timing captures were visually inspected; all ten selected screenshots were refreshed. JavaScript/HTTP errors and server tracebacks were absent.

`browser-review/final-submission/checks.json` records this run, including hashes of the checked application/source and README. These are checks performed on the final version, rather than claims carried forward from an earlier build. Full captures remain local under `.cache/final-submission-review/`.

## Evidence and reproduction

- `screenshots/`: ten selected full-resolution screenshots, including the new baseline view, included in the submission ZIP.
- `browser-review/captures/results.json`: successful browser run, covered states and visual-review status.
- Full captures and contact sheets are generated locally by `./review_browser.sh`; they are not included in the submission ZIP. The ZIP includes the ten selected images in `screenshots/` and the machine-readable capture results.
- `browser-review/scrap-model/checks.json`: final model/browser/export checks. Full new captures remain local under `.cache/scrap-model-review/`.
- `browser-review/supplemental/checks.json`: browser filter/export totals reconciled independently to source data.
- `browser-review/zero-revenue/checks.json` and `queue-5.csv` / `queue-10.csv` in that directory: final replacement-export regression and downloaded evidence. Its screenshots are local artifacts, outside the ZIP.
- The selected narrower-window evidence is included as `screenshots/repair-narrow-window.png`. Other responsive captures are local review artifacts and are not included in the ZIP.

```sh
./run.sh
# In a second terminal:
./review_browser.sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/full_export_review.py
.venv/bin/python scripts/browser_review_calculations.py
.venv/bin/python scripts/browser_review_zero_revenue.py
```

The review runner uses a separate Chrome profile, exercises the views and controls, and captures screenshots after Streamlit finishes rendering. Captures from a future run still require visual inspection; the runner does not automatically approve its own screenshots. The calculation reconciliation script targets the supplied case-study export and its known date window.

Review scope is Chrome on this Mac with the stated viewport sizes. A fresh clean-machine Streamlit installation, other browsers and hosted deployment were not part of this UI review. Wide detail tables intentionally scroll horizontally; complete CSV downloads preserve every field.
