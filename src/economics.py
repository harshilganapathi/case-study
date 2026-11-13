"""Exact-decimal repair contribution using reported extended transaction amounts."""
from collections import defaultdict
from decimal import Decimal

from .ingest import number

DIMENSIONS = {'module': 'Module', 'subtype': 'SubType', 'part': 'PART'}
DETAIL_COLUMNS = ['source_records', 'part', 'module', 'subtype', 'qty', 'sales',
                  'repair_cost', 'contribution', 'margin', 'reported_zero_repair_cost', 'review_reason']
SUMMARY_COLUMNS = ['records', 'units', 'sales', 'repair_cost', 'contribution', 'margin',
                   'zero_cost_records', 'negative_contribution_records', 'weak_records']


def amount(value):
    return format(value, 'f')


def summarize(rows):
    sales = sum((Decimal(r['sales']) for r in rows), Decimal(0))
    costs = sum((Decimal(r['repair_cost']) for r in rows), Decimal(0))
    contribution = sales - costs
    return {'records': len(rows), 'units': amount(sum((Decimal(r['qty']) for r in rows), Decimal(0))),
            'sales': amount(sales), 'repair_cost': amount(costs),
            'contribution': amount(contribution),
            'margin': amount(contribution/sales) if sales > 0 else None,
            'zero_cost_records': sum(r['reported_zero_repair_cost'] for r in rows),
            'negative_contribution_records': sum(Decimal(r['contribution']) < 0 for r in rows),
            'weak_records': sum(bool(r['review_reason']) for r in rows)}


def calculate(records, weak_margin=Decimal('.20')):
    threshold = Decimal(str(weak_margin))
    if not threshold.is_finite() or not 0 <= threshold <= 1:
        raise ValueError('Weak margin threshold must be a fraction between zero and one')
    positive, credits, exclusions = [], [], []
    invoiced_count = 0
    for r in records:
        if str(r.get('included_in_calculations')) not in {'True', 'true'}:
            raise ValueError('Economics requires the deduplicated calculation population')
        if r['Type'] != 'Invoiced':
            continue
        invoiced_count += 1
        qty = number(r['QTY'])
        sales = number(r.get('Extended Sales Price', ''))
        cost = number(r.get('Repair Ext Cost', ''))
        reasons = []
        if qty is None or qty == 0 or qty != qty.to_integral_value():
            reasons.append('unavailable_zero_or_fractional_quantity')
        if sales is None:
            reasons.append('sales_unavailable')
        if cost is None:
            reasons.append('repair_cost_unavailable')
        if qty is not None and qty != 0:
            if sales is not None and qty*sales < 0:
                reasons.append('sales_sign_conflicts_with_quantity')
            if cost is not None and qty*cost < 0:
                reasons.append('repair_sign_conflicts_with_quantity')
        if reasons:
            exclusions.append({'source_records': r.get('source_records', ''), 'part': r['PART'],
                               'qty': r['QTY'], 'sales': r.get('Extended Sales Price', ''),
                               'repair_cost': r.get('Repair Ext Cost', ''), 'reasons': ';'.join(reasons)})
            continue
        contribution = sales-cost
        margin = contribution/sales if sales > 0 else None
        # Credit reversal amounts do not diagnose the margin of a new positive sale.
        review = ''
        if qty > 0:
            if contribution < 0:
                review = 'negative_repair_contribution'
            elif sales == 0:
                review = 'zero_sales_amount'
            elif margin < threshold:
                review = 'below_margin_threshold'
        detail = {'source_records': r.get('source_records', ''),
                  **{name: r.get(key, '').strip() or 'Unknown' for name,key in DIMENSIONS.items()},
                  'qty': amount(qty), 'sales': amount(sales), 'repair_cost': amount(cost),
                  'contribution': amount(contribution), 'margin': amount(margin) if margin is not None else None,
                  'reported_zero_repair_cost': cost == 0, 'review_reason': review}
        (positive if qty > 0 else credits).append(detail)
    groups = {}
    for dimensions in [('module',), ('subtype',), ('module', 'subtype'), ('part',)]:
        buckets = defaultdict(list)
        for r in positive:
            buckets[tuple(r[k] for k in dimensions)].append(r)
        groups['_'.join(dimensions)] = [dict(zip(dimensions, key), **summarize(rows))
                                       for key,rows in sorted(buckets.items())]
    primary = summarize(positive)
    credit_summary = summarize(credits)
    signed = summarize(positive + credits)
    for rows in groups.values():
        for field in ('sales', 'repair_cost', 'contribution', 'units'):
            if sum((Decimal(r[field]) for r in rows), Decimal(0)) != Decimal(primary[field]):
                raise AssertionError('Economics group totals do not reconcile')
    weak = sorted((r for r in positive if r['review_reason']),
                  key=lambda r: (Decimal(r['contribution']), r['part'], r['source_records']))
    part_review = [dict(r, review_reason=(
        'negative_repair_contribution' if Decimal(r['contribution']) < 0 else
        'zero_sales_amount' if Decimal(r['sales']) == 0 else 'below_margin_threshold'))
        for r in groups['part'] if Decimal(r['contribution']) < 0 or Decimal(r['sales']) == 0
        or (r['margin'] is not None and Decimal(r['margin']) < threshold)]
    part_review.sort(key=lambda r: (Decimal(r['contribution']), r['part']))
    assert invoiced_count == len(positive) + len(credits) + len(exclusions)
    return {'weak_margin_threshold': amount(threshold), 'invoiced_records': invoiced_count,
            'positive_sales': primary, 'credits': credit_summary, 'signed_total': signed,
            'zero_cost_positive_sales': summarize([r for r in positive if r['reported_zero_repair_cost']]),
            'nonzero_cost_positive_sales': summarize([r for r in positive if not r['reported_zero_repair_cost']]),
            'positive_details': positive, 'credit_details': credits, 'weak_transactions': weak,
            'part_review': part_review, 'by': groups, 'exclusions': exclusions,
            'excluded_records': len(exclusions), 'breakdowns_reconcile': True}


def report(s):
    def money(value):
        return f'{Decimal(value):,.2f}'
    def percent(value):
        return f'{Decimal(value)*100:.2f}%' if value is not None else 'Unavailable'
    p = s['positive_sales']
    lines = ['# Repair economics explained\n',
             'This answers: how much sales value remains after reported repair costs? '
             'Identical records count once. Amounts use the export’s unspecified currency; '
             'aggregation assumes they are comparable because no currency field is available.\n',
             '## Positive sales\n', '| Measure | Value |', '| --- | ---: |',
             f"| Sale records | {p['records']:,} |",
             f"| Sales amount | {money(p['sales'])} |",
             f"| Repair cost | {money(p['repair_cost'])} |",
             f"| Remaining after repair | {money(p['contribution'])} |",
             f"| Repair contribution margin | {percent(p['margin'])} |",
             '', '**Repair contribution = sales amount − repair cost.** '
             'Use the extended amounts, which already cover the transaction quantity. '
             'Do not multiply them by quantity again.\n',
             '**Margin = total contribution ÷ total sales.** '
             'For a sale of 1,000 with repair cost 700, contribution is 300 and margin is 30%. '
             'For a sale of 500 with repair cost 700, contribution is −200 and margin is −40%. '
             'Group margins are calculated from group totals, never averaged from individual percentages.\n',
             'This is not total profit: purchase costs, freight and overhead are unavailable. '
             'A high repair contribution margin therefore does not establish a profitable transaction.\n',
             '## Zero reported repair cost\n',
             f"{p['zero_cost_records']:,} positive-quantity sale records report zero repair cost. "
             'They remain included as reported, but their contribution margin needs care. '
             'Zero might mean no repair spend; it does not establish zero acquisition or total cost.\n',
             '| Population | Records | Sales | Repair cost | Contribution margin |',
             '| --- | ---: | ---: | ---: | ---: |']
    for key,label in [('zero_cost_positive_sales','Zero reported repair cost'),
                      ('nonzero_cost_positive_sales','Positive reported repair cost')]:
        r = s[key]
        lines.append(f"| {label} | {r['records']:,} | {money(r['sales'])} | {money(r['repair_cost'])} | {percent(r['margin'])} |")
    lines += ['', '## Breakdown by module\n',
              '| Module | Sale records | Sales | Repair cost | Contribution | Margin |',
              '| --- | ---: | ---: | ---: | ---: | ---: |']
    for r in s['by']['module']:
        lines.append(f"| {r['module']} | {r['records']:,} | {money(r['sales'])} | {money(r['repair_cost'])} | "
                     f"{money(r['contribution'])} | {percent(r['margin'])} |")
    lines += ['', '## Weak or negative results\n',
              f"{p['negative_contribution_records']:,} positive-quantity sale records have repair costs "
              f"above sales. {len(s['weak_transactions']):,} records trigger review in total. "
              f"The configurable weak-margin threshold is {percent(s['weak_margin_threshold'])}; "
              'this is a review assumption, not a business-provided target. '
              'Zero-sales records are also flagged, with no percentage margin.\n',
              'The examples below show the largest negative transaction contributions. '
              'Every weak transaction is exported with its source reference. Part-level totals '
              'are exported separately, because profitable sales of a part can offset individual losses.\n',
              '| Source records | Part | Sales | Repair cost | Contribution | Margin |',
              '| --- | --- | ---: | ---: | ---: | ---: |']
    for r in s['weak_transactions'][:10]:
        lines.append(f"| {r['source_records']} | {r['part']} | {money(r['sales'])} | {money(r['repair_cost'])} | "
                     f"{money(r['contribution'])} | {percent(r['margin'])} |")
    lines += ['', '## Returns and signed reconciliation\n',
              'Negative-quantity invoices with nonpositive sales/costs are treated as possible credits. '
              'They remain separate from positive-sale margins. This interpretation is unconfirmed. '
              'Reported extended amounts retain their signs; no negative × negative multiplication is used. '
              'The signed total is a reconciliation, not a second positive-sale performance measure.\n',
              '| Population | Records | Signed sales | Signed repair cost | Signed contribution |',
              '| --- | ---: | ---: | ---: | ---: |']
    for key,label in [('positive_sales','Positive sales'),('credits','Possible credits'),('signed_total','Combined signed total')]:
        r = s[key]
        lines.append(f"| {label} | {r['records']:,} | {money(r['sales'])} | {money(r['repair_cost'])} | {money(r['contribution'])} |")
    lines += ['', '## Eligibility and files\n',
              f"- {s['invoiced_records']:,} deduplicated invoice records were considered; "
              f"{s['excluded_records']:,} were excluded from contribution calculations. "
              'See `economics_exclusions.csv` for every source reference and reason.',
              '- Contribution requires a valid nonzero whole quantity and both extended amounts. '
              'Missing amounts remain unknown; they never become zero. Conflicting quantity/amount '
              'signs are excluded and shown for review. Missing classifications display as Unknown.',
              '- Positive-quantity rows may have zero sales; their contribution remains included, '
              'but an individual margin is unavailable. There is no division by zero.',
              f"- {s.get('quarantined_cases', 0):,} source cases remain unresolved and are absent "
              'from the audited calculation population. No estimated amounts have been added for them.',
              '- `economics_by_module.csv`, `economics_by_subtype.csv`, and '
              '`economics_by_module_subtype.csv` contain positive-sale group totals and margins.',
              '- `economics_by_part.csv` contains all part totals. `economics_part_review.csv` '
              'contains parts with weak aggregate results, including their sales record counts.',
              '- `economics_positive_sales.csv`, `economics_credits.csv` and '
              '`economics_weak_transactions.csv` provide transaction detail and source references.',
              '- `economics.json` contains all results. Reproduce with `python3 -m src.metrics`; '
              'change the threshold with `--weak-margin 0.20`.',
              '', 'A review flag means inspect the history. It is not a repair-or-scrap instruction, '
              'a forecast, or evidence of a safety issue.\n']
    return '\n'.join(lines)
