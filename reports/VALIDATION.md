# Completed application validation

The app was reviewed in a real, separate Chrome browser using Playwright against **http://127.0.0.1:8501/**. This report describes the final reviewed code.

The final zero-revenue regression used a fresh app process on **http://127.0.0.1:8614/** to verify the updated calculation module.

## Results

| Check | Result |
| --- | --- |
| Automated Python and Streamlit AppTest suite | **67 passed, zero skipped**, including two HTTP middleware regressions |
| Full supplied-export behavioral checks | **31 passed** |
| Real-browser capture sequence | **39 checks passed**, including 38 captured UI states and a CSV download |
| JavaScript page errors during the successful capture run | **None** |
| Visual inspection | All six views, alternative groupings, filters and empty states reviewed through screenshots and contact sheets |
| Responsive checks | 1,440-pixel desktop; 1,024-pixel financial-card readability; 390-pixel mobile overview |
| CSV reconciliation | Overview inventory export totals **105,643 units** |
| Weak-margin filter | At zero threshold, downloaded table contains exactly **165 negative-contribution sales** |
| Narrow invoice-date filter | August 1–29, 2023 positive-sale amount equals independent source sum **9,875,968.42** |
| Source replacement | Synthetic valid upload shows **7 units**; removing it restores **105,643 units** |
| Zero-revenue loss regression | Five and ten eligible loss records trigger **Review**; downloaded margins remain unavailable; removing uploads restores **123 Review parts** |
| Invalid input | A synthetic bad-header upload shows a friendly load error |
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

## Evidence and reproduction

- `screenshots/`: nine selected full-resolution screenshots, included in the submission ZIP.
- `browser-review/captures/results.json`: successful browser run, covered states and visual-review status.
- Full captures and contact sheets are generated locally by `./review_browser.sh`; they are not included in the submission ZIP. The ZIP includes the nine selected images in `screenshots/` and the machine-readable capture results.
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
