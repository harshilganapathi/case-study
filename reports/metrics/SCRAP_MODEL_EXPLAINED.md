# Experimental scrap-risk baseline

A smoothed Module/SubType classifier for recorded scrap versus positive-sale outcomes. Each deduplicated outcome record has weight one; quantities are not expanded into independent samples. Its score is not the unit-weighted scrap share and is not a validated future lifecycle probability.

Eligible history: 11,769 records across 1,770 part numbers; 4,549 scrapped and 7,220 positive-sale records. Excluded outcome records: 259. Inventory is never a training label.

## Fit and features

The global prior is the training scrap-record fraction. Module score = (module scrap records + 20 × global prior) / (module records + 20). Module/subtype score = (group scrap records + 20 × module score) / (group records + 20). The fixed prior strength of 20 is a baseline assumption, not a tuned optimum. Missing/unseen subtype falls back to module; missing/unseen module falls back to the overall rate. Fallback source and matching history counts accompany every stock score.

Only Module and SubType are predictors. Type supplies the label only. PART is used only for evaluation grouping and stock display, never as a predictor. Condition, warehouse, quantity, identifiers, dates, expected days, costs and sale prices are excluded: their timing, missingness or values could reveal the recorded outcome. Module/subtype availability before an actual decision still needs business confirmation.

## Held-out evaluation

Sort unique part numbers by SHA-256 of a fixed model-version prefix plus the part number; hold out 20% of whole part numbers (rounded up). No part occurs in both training and test. All rates, including the constant comparator, are fitted on training records alone. There is no tuning on the test set. Test rows from the same part can remain correlated; no independent-observation confidence interval is claimed.

Training: 10,016 records / 1,416 parts. Test: 1,753 records / 354 parts. Overlap: 0 parts.

| Model | Brier score ↓ | Log loss ↓ | ROC AUC ↑ |
| --- | ---: | ---: | ---: |
| Category baseline | 0.1415 | 0.4440 | 0.8608 |
| Constant training rate | 0.2611 | 0.7162 | 0.5000 |

Brier score measures mean squared probability error. Log loss penalizes confident wrong predictions. ROC AUC measures ranking across the two labels. The held-out calibration bins compare mean scores with observed record shares; they are a diagnostic, not proof of future calibration. No held-out labels enter the evaluated model.

## Stock scoring and limits

After evaluation, refit on all eligible outcome history to score current stock categories. That refit is separate from the held-out metrics. Stock is grouped by part, module and subtype; a part with inconsistent classifications can have multiple rows. Sidebar/location filters select stock only and do not retrain the model or alter evaluation. Scores do not replace the review queue.

There are no scrap dates, acquisition cohorts, reliable lifecycle identifiers or observation windows. The train/test split cannot validate forecasting over time. Completed outcomes are a selected population; unsold stock, conditions, lot mix and business decisions may differ. No time horizon, future scrap probability, expected scrap units, safety decision or automatic repair/scrap recommendation is established. Evaluate prospectively with confirmed field timing and lifecycle data before operational use. A high score means investigate the category history.

Reproduce with `python3 -m src.metrics`. Outputs: `scrap_model.json`, `scrap_model_stock_scores.csv`, `scrap_model_holdout_predictions.csv`, `scrap_model_calibration.csv`, and `scrap_model_exclusions.csv`.

Method references: [grouped validation](https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-iterators-for-grouped-data), [data leakage](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage), [probability evaluation](https://scikit-learn.org/stable/modules/calibration.html). The implementation uses the Python standard library; scikit-learn is not a runtime dependency.
