"""Transparent part-level review rules, with stock and history aggregated separately."""
from collections import defaultdict
from decimal import Decimal

from . import economics
from .ingest import number

COLUMNS = ['rank', 'part', 'status', 'on_hand_units', 'triggered_rules', 'reasons',
           'eligible_sale_records', 'sales', 'repair_cost', 'repair_contribution', 'repair_margin',
           'repair_evidence_supported', 'zero_cost_sale_records', 'zero_cost_sale_share',
           'scrapped_units', 'sold_units', 'disposed_units', 'scrap_share',
           'scrap_evidence_supported', 'outcome_records', 'warehouses', 'conditions',
           'flagged_stock_records']


def positive_qty(record):
    q = number(record['QTY'])
    return int(q) if q is not None and q > 0 and q == q.to_integral_value() else None


def build_queue(records, inventory_records=None, weak_margin=Decimal('.20'),
                min_sales=5, min_disposed=10, scrap_threshold=Decimal('.50')):
    weak_margin, scrap_threshold = Decimal(str(weak_margin)), Decimal(str(scrap_threshold))
    if min_sales < 1 or min_disposed < 1:
        raise ValueError('Evidence minimums must be positive')
    for threshold in (weak_margin, scrap_threshold):
        if not threshold.is_finite() or not 0 <= threshold <= 1:
            raise ValueError('Review thresholds must be fractions between zero and one')
    for r in records:
        if str(r.get('included_in_calculations')) not in {'True', 'true'}:
            raise ValueError('Review queue requires deduplicated records')
    stock = defaultdict(list)
    for r in records if inventory_records is None else inventory_records:
        if str(r.get('included_in_calculations')) not in {'True', 'true'}:
            raise ValueError('Review queue requires deduplicated stock records')
        if r['Type'] == 'Inventory' and positive_qty(r) and r['PART'].strip():
            stock[r['PART']].append(r)
    financial = economics.calculate(records, weak_margin)
    finance = {r['part']: r for r in financial['by']['part']}
    outcomes = defaultdict(lambda: {'scrapped_units': 0, 'sold_units': 0, 'records': 0})
    for r in records:
        q = positive_qty(r)
        if q and r['Type'] in {'Scrapped', 'Invoiced'}:
            k = 'scrapped_units' if r['Type'] == 'Scrapped' else 'sold_units'
            outcomes[r['PART']][k] += q
            outcomes[r['PART']]['records'] += 1
    queue = []
    for part, items in stock.items():
        f = finance.get(part)
        outcome = outcomes[part]
        disposed = outcome['scrapped_units'] + outcome['sold_units']
        scrap_share = Decimal(outcome['scrapped_units'])/disposed if disposed else None
        margin = Decimal(f['margin']) if f and f['margin'] is not None else None
        sale_records = f['records'] if f else 0
        # Usable transaction evidence can establish a loss even when zero sales
        # make its percentage margin undefined.
        repair_supported = sale_records >= min_sales
        scrap_supported = disposed >= min_disposed
        reasons = []
        if repair_supported and Decimal(f['sales']) == 0 and Decimal(f['contribution']) < 0:
            reasons.append(f'Repair costs exceed zero sales, contribution {Decimal(f["contribution"]):,.2f} '
                           f'across {sale_records} eligible sale records')
        elif repair_supported and margin is not None and margin < weak_margin:
            reasons.append(f'Repair contribution margin {margin:.1%} below {weak_margin:.0%} '
                           f'across {sale_records} eligible sale records')
        if scrap_supported and scrap_share >= scrap_threshold:
            reasons.append(f'Scrap share {scrap_share:.1%} at or above {scrap_threshold:.0%} '
                           f'across {disposed} disposed units')
        queue.append({'rank': None, 'part': part,
                      'status': 'Review' if reasons else 'No rule triggered' if repair_supported or scrap_supported
                      else 'Insufficient evidence',
                      'on_hand_units': sum(positive_qty(r) for r in items),
                      'triggered_rules': len(reasons), 'reasons': '; '.join(reasons),
                      'eligible_sale_records': sale_records, 'sales': f['sales'] if f else None,
                      'repair_cost': f['repair_cost'] if f else None,
                      'repair_contribution': f['contribution'] if f else None,
                      'repair_margin': str(margin) if margin is not None else None,
                      'repair_evidence_supported': repair_supported,
                      'zero_cost_sale_records': f['zero_cost_records'] if f else 0,
                      'zero_cost_sale_share': str(Decimal(f['zero_cost_records'])/sale_records) if sale_records else None,
                      'scrapped_units': outcome['scrapped_units'], 'sold_units': outcome['sold_units'],
                      'disposed_units': disposed, 'scrap_share': str(scrap_share) if scrap_share is not None else None,
                      'scrap_evidence_supported': scrap_supported, 'outcome_records': outcome['records'],
                      'warehouses': ', '.join(sorted({r.get('WHSE', '').strip() or 'Unknown' for r in items})),
                      'conditions': ', '.join(sorted({r.get('Condition', '').strip() or 'Unknown' for r in items})),
                      'flagged_stock_records': sum(r.get('audit_flags', '[]') not in ('[]', '') for r in items)})
    priority = {'Review': 0, 'Insufficient evidence': 1, 'No rule triggered': 2}
    queue.sort(key=lambda r: (priority[r['status']], -r['triggered_rules'], -r['on_hand_units'], r['part']))
    for rank, r in enumerate((r for r in queue if r['status'] == 'Review'), 1):
        r['rank'] = rank
    return queue
