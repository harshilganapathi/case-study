"""Smoothed category baseline for recorded scrap versus positive-sale outcomes.

This is a record-level snapshot classifier, not a lifecycle or time-to-event model.
Only Module and SubType are predictors; PART is used to keep evaluation groups apart.
"""
from collections import Counter, defaultdict
import hashlib
import math

from .ingest import number

VERSION = 'category-baseline-v1'
PRIOR_STRENGTH = 20
SCORE_COLUMNS = ['part', 'module', 'subtype', 'on_hand_units', 'baseline_scrap_score',
                 'evidence_level', 'category_history_records', 'category_scrap_records']
PREDICTION_COLUMNS = ['source_records', 'part', 'module', 'subtype', 'scrapped',
                      'baseline_scrap_score', 'constant_score', 'evidence_level']


def _category(value):
    return value.strip() or 'Unknown'


def history(records):
    eligible, excluded = [], []
    for r in records:
        if str(r.get('included_in_calculations')) not in {'True', 'true'}:
            raise ValueError('Scrap baseline requires deduplicated records')
        if r['Type'] not in {'Invoiced', 'Scrapped'}:
            continue  # Stock has no observed outcome and never supplies a label.
        qty = number(r['QTY'])
        reason = ('invalid_nonpositive_or_fractional_quantity' if qty is None or qty <= 0
                  or qty != qty.to_integral_value() else
                  'missing_part_for_grouped_evaluation' if not r['PART'].strip() else '')
        if reason:
            excluded.append({'source_records':r.get('source_records',''), 'part':r['PART'],
                             'type':r['Type'], 'qty':r['QTY'], 'reason':reason})
        else:
            eligible.append({'part':r['PART'], 'module':_category(r.get('Module','')),
                             'subtype':_category(r.get('SubType','')),
                             'scrapped':int(r['Type'] == 'Scrapped'),
                             'source_records':r.get('source_records','')})
    return eligible, excluded


def fit(rows, prior_strength=PRIOR_STRENGTH):
    if not math.isfinite(prior_strength) or prior_strength <= 0:
        raise ValueError('Prior strength must be finite and positive')
    if not rows or {r['scrapped'] for r in rows} != {0, 1}:
        return None
    total = len(rows)
    scraps = sum(r['scrapped'] for r in rows)
    overall = scraps / total
    modules, groups = defaultdict(list), defaultdict(list)
    for r in rows:
        if r['module'] != 'Unknown':
            modules[r['module']].append(r['scrapped'])
            if r['subtype'] != 'Unknown':
                groups[(r['module'],r['subtype'])].append(r['scrapped'])
    module_rates = {}
    for module, labels in sorted(modules.items()):
        module_rates[module] = {'records':len(labels), 'scrapped_records':sum(labels),
                               'score':(sum(labels)+prior_strength*overall)/(len(labels)+prior_strength)}
    group_rates = []
    for (module, subtype), labels in sorted(groups.items()):
        group_rates.append({'module':module, 'subtype':subtype, 'records':len(labels),
                            'scrapped_records':sum(labels),
                            'score':(sum(labels)+prior_strength*module_rates[module]['score']) /
                                    (len(labels)+prior_strength)})
    return {'version':VERSION, 'features':['Module','SubType'], 'prior_strength':prior_strength,
            'records':total, 'scrapped_records':scraps, 'overall_score':overall,
            'module_rates':module_rates, 'group_rates':group_rates}


def predict(model, module, subtype):
    module, subtype = _category(module), _category(subtype)
    pair = next((r for r in model['group_rates']
                 if r['module'] == module and r['subtype'] == subtype), None)
    match = pair or model['module_rates'].get(module)
    return {'baseline_scrap_score':match['score'] if match else model['overall_score'],
            'evidence_level':'Module + subtype' if pair else 'Module' if match else 'Overall fallback',
            'category_history_records':match['records'] if match else 0,
            'category_scrap_records':match['scrapped_records'] if match else 0}


def split_by_part(rows):
    parts = sorted({r['part'] for r in rows}, key=lambda p: (
        hashlib.sha256((VERSION+'|'+p).encode()).hexdigest(), p))
    if len(parts) < 2:
        return list(rows), []
    count = max(1, math.ceil(len(parts)*0.2))
    test_parts = set(parts[:count])
    return ([r for r in rows if r['part'] not in test_parts],
            [r for r in rows if r['part'] in test_parts])


def probability_metrics(labels, scores):
    if not labels or len(labels) != len(scores):
        raise ValueError('Metrics require paired, nonempty labels and scores')
    if any(y not in {0,1} for y in labels) or any(not math.isfinite(p) or not 0 <= p <= 1 for p in scores):
        raise ValueError('Invalid outcome label or probability')
    n = len(labels)
    brier = sum((p-y)**2 for y,p in zip(labels,scores))/n
    log_loss = -sum(y*math.log(max(p,1e-15))+(1-y)*math.log(max(1-p,1e-15))
                    for y,p in zip(labels,scores))/n
    # Mann-Whitney rank statistic; ties receive their average rank.
    ranked = sorted(zip(scores,labels))
    positive_ranks, index = 0.0, 0
    while index < n:
        end = index+1
        while end < n and ranked[end][0] == ranked[index][0]:
            end += 1
        positive_ranks += sum(y for _,y in ranked[index:end]) * (index+1+end)/2
        index = end
    positives = sum(labels)
    negatives = n-positives
    auc = ((positive_ranks-positives*(positives+1)/2)/(positives*negatives)
           if positives and negatives else None)
    return {'brier_score':brier, 'log_loss':log_loss, 'roc_auc':auc}


def evaluate(rows):
    train, test = split_by_part(rows)
    train_parts, test_parts = {r['part'] for r in train}, {r['part'] for r in test}
    assert not train_parts & test_parts
    result = {'available':False, 'train_records':len(train), 'test_records':len(test),
              'train_part_numbers':len(train_parts), 'test_part_numbers':len(test_parts),
              'overlapping_parts':0, 'split':'Deterministic 80/20 split of whole part numbers',
              'comparison':[], 'calibration':[], 'predictions':[]}
    model = fit(train)
    if model is None or not test:
        result['reason'] = 'Evaluation needs separate part groups and both outcomes in training.'
        return result
    if {r['scrapped'] for r in test} != {0,1}:
        result['reason'] = 'The held-out part groups do not contain both recorded outcomes.'
        return result
    predictions = []
    for r in sorted(test, key=lambda r:(r['part'],r['source_records'])):
        estimate = predict(model,r['module'],r['subtype'])
        predictions.append(dict(r, baseline_scrap_score=estimate['baseline_scrap_score'],
                                constant_score=model['overall_score'], evidence_level=estimate['evidence_level']))
    labels = [r['scrapped'] for r in predictions]
    scores = [r['baseline_scrap_score'] for r in predictions]
    baseline = [model['overall_score']]*len(test)
    bins = defaultdict(list)
    for r in predictions:
        bins[min(9,int(r['baseline_scrap_score']*10))].append(r)
    calibration = [{'score_band':f'{index*10}–{(index+1)*10}%', 'records':len(items),
                    'mean_score':sum(r['baseline_scrap_score'] for r in items)/len(items),
                    'observed_scrap_share':sum(r['scrapped'] for r in items)/len(items)}
                   for index,items in sorted(bins.items())]
    result.update(available=True, training_scrap_record_share=model['overall_score'],
                  test_scrap_record_share=sum(labels)/len(labels),
                  comparison=[{'model':'Category baseline', **probability_metrics(labels,scores)},
                              {'model':'Constant training rate', **probability_metrics(labels,baseline)}],
                  calibration=calibration, predictions=predictions)
    return result


def score_inventory(records, model):
    if model is None:
        return []
    stock = Counter()
    for r in records:
        if str(r.get('included_in_calculations')) not in {'True','true'}:
            raise ValueError('Scrap baseline requires deduplicated stock records')
        if r['Type'] != 'Inventory' or not r['PART'].strip():
            continue
        qty = number(r['QTY'])
        if qty is not None and qty > 0 and qty == qty.to_integral_value():
            stock[(r['PART'],_category(r.get('Module','')),_category(r.get('SubType','')))] += int(qty)
    scores = [dict(part=part,module=module,subtype=subtype,on_hand_units=qty,
                   **predict(model,module,subtype)) for (part,module,subtype),qty in stock.items()]
    return sorted(scores,key=lambda r:(-r['baseline_scrap_score'],-r['on_hand_units'],
                                       r['part'],r['module'],r['subtype']))


def calculate(records):
    rows, excluded = history(records)
    model = fit(rows)
    return {'available':model is not None,
            'reason':'' if model else 'Need at least one eligible sold and one scrapped record to fit the baseline.',
            'target':'Scrapped versus positive-quantity Invoiced outcome record; each deduplicated record counts once',
            'features':['Module','SubType'], 'history_records':len(rows),
            'scrapped_records':sum(r['scrapped'] for r in rows),
            'sold_records':sum(1-r['scrapped'] for r in rows),
            'outcome_parts':len({r['part'] for r in rows}),
            'excluded_history':excluded, 'model':model, 'validation':evaluate(rows),
            'inventory_scores':score_inventory(records,model)}


def report(s):
    v = s['validation']
    lines = ['# Experimental scrap-risk baseline\n',
             'A smoothed Module/SubType classifier for recorded scrap versus positive-sale outcomes. '
             'Each deduplicated outcome record has weight one; quantities are not expanded into independent samples. '
             'Its score is not the unit-weighted scrap share and is not a validated future lifecycle probability.\n',
             f"Eligible history: {s['history_records']:,} records across {s['outcome_parts']:,} part numbers; "
             f"{s['scrapped_records']:,} scrapped and {s['sold_records']:,} positive-sale records. "
             f"Excluded outcome records: {len(s['excluded_history']):,}. Inventory is never a training label.\n",
             '## Fit and features\n',
             'The global prior is the training scrap-record fraction. Module score = '
             '(module scrap records + 20 × global prior) / (module records + 20). '
             'Module/subtype score = (group scrap records + 20 × module score) / (group records + 20). '
             'The fixed prior strength of 20 is a baseline assumption, not a tuned optimum. '
             'Missing/unseen subtype falls back to module; missing/unseen module falls back to the overall rate. '
             'Fallback source and matching history counts accompany every stock score.\n',
             'Only Module and SubType are predictors. Type supplies the label only. PART is used only for '
             'evaluation grouping and stock display, never as a predictor. Condition, warehouse, quantity, '
             'identifiers, dates, expected days, costs and sale prices are excluded: their timing, missingness '
             'or values could reveal the recorded outcome. Module/subtype availability before an actual '
             'decision still needs business confirmation.\n',
             '## Held-out evaluation\n',
             'Sort unique part numbers by SHA-256 of a fixed model-version prefix plus the part number; '
             'hold out 20% of whole part numbers (rounded up). No part occurs in both training and test. '
             'All rates, including the constant comparator, are fitted on training records alone. '
             'There is no tuning on the test set. Test rows from the same part can remain correlated; '
             'no independent-observation confidence interval is claimed.\n',
             f"Training: {v['train_records']:,} records / {v['train_part_numbers']:,} parts. "
             f"Test: {v['test_records']:,} records / {v['test_part_numbers']:,} parts. Overlap: 0 parts.\n"]
    if v['available']:
        lines += ['| Model | Brier score ↓ | Log loss ↓ | ROC AUC ↑ |', '| --- | ---: | ---: | ---: |']
        for r in v['comparison']:
            lines.append(f"| {r['model']} | {r['brier_score']:.4f} | {r['log_loss']:.4f} | {r['roc_auc']:.4f} |")
        lines += ['', 'Brier score measures mean squared probability error. Log loss penalizes confident '
                  'wrong predictions. ROC AUC measures ranking across the two labels. The held-out calibration '
                  'bins compare mean scores with observed record shares; they are a diagnostic, not proof of '
                  'future calibration. No held-out labels enter the evaluated model.\n']
    else:
        lines += [v['reason']+'\n']
    lines += ['## Stock scoring and limits\n',
              'After evaluation, refit on all eligible outcome history to score current stock categories. '
              'That refit is separate from the held-out metrics. Stock is grouped by part, module and subtype; '
              'a part with inconsistent classifications can have multiple rows. Sidebar/location filters select '
              'stock only and do not retrain the model or alter evaluation. Scores do not replace the review queue.\n',
              'There are no scrap dates, acquisition cohorts, reliable lifecycle identifiers or observation '
              'windows. The train/test split cannot validate forecasting over time. Completed outcomes are a '
              'selected population; unsold stock, conditions, lot mix and business decisions may differ. '
              'No time horizon, future scrap probability, expected scrap units, safety decision or automatic '
              'repair/scrap recommendation is established. Evaluate prospectively with confirmed field timing '
              'and lifecycle data before operational use. A high score means investigate the category history.\n',
              'Reproduce with `python3 -m src.metrics`. Outputs: `scrap_model.json`, '
              '`scrap_model_stock_scores.csv`, `scrap_model_holdout_predictions.csv`, '
              '`scrap_model_calibration.csv`, and `scrap_model_exclusions.csv`.\n',
              'Method references: [grouped validation](https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-iterators-for-grouped-data), '
              '[data leakage](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage), '
              '[probability evaluation](https://scikit-learn.org/stable/modules/calibration.html). '
              'The implementation uses the Python standard library; scikit-learn is not a runtime dependency.\n']
    return '\n'.join(lines)
