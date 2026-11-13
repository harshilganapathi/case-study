# Inventory review queue

Positive on-hand stock is grouped by part number before attaching independently aggregated history. Each deduplicated historical record contributes once, regardless of how many stock locations exist.

- Review: 123 part numbers.
- Insufficient evidence: 2,479 part numbers.
- No rule triggered: 355 part numbers.

Repair review requires at least five eligible positive-sale records and aggregate repair contribution margin below 20%, or zero sales with negative repair contribution. In the zero-sales case, the percentage margin remains unavailable. Scrap review requires at least ten disposed units and observed scrap share at least 50%. These are adjustable assumptions in the app.

Review items are ranked by number of triggered rules, then on-hand units descending, then part number. This is an inspection priority, not an expected loss estimate. The CSV includes all parts on hand; only Review items have a numeric rank.

Insufficient evidence means neither rule has its minimum usable support. No rule triggered means at least one rule has support but neither triggers; check each evidence-support field before drawing conclusions. Neither status establishes low risk. Zero-cost sale coverage and flagged stock record counts are included for inspection.

App location/condition filters select stock only. History uses all deduplicated records for the selected part numbers and is not a condition-matched prediction. No date interval is used for ranking. OH_DATE is assumed to mean overhaul date, not receipt date.

Missing future repair quotes, acquisition cost, scrap recovery value, receipt dates and snapshot date prevent an automatic repair-or-scrap decision or a current aging watchlist.
