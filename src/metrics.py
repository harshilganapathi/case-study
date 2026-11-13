"""Inventory, scrap, repair economics and timing. Run: python3 -m src.metrics."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from decimal import Decimal
from pathlib import Path

from .audit import run as audit, write_json
from .ingest import STATUSES, number
from . import economics, scrap_model, timing
from .decision_support import build_queue, COLUMNS as QUEUE_COLUMNS

DIMENSIONS = {'module': 'Module', 'subtype': 'SubType', 'warehouse': 'WHSE',
              'condition': 'Condition', 'part': 'PART'}


def calculate(records: list[dict]) -> dict:
    """Use deduplicated rows; quantity is the number of units, not the row count."""
    exclusions = []
    connection = sqlite3.connect(':memory:')
    connection.row_factory = sqlite3.Row
    try:
        connection.execute('CREATE TABLE parts (status TEXT, qty INTEGER, module TEXT, '
                           'subtype TEXT, warehouse TEXT, condition TEXT, part TEXT)')
        values = []
        for r in records:
            if str(r.get('included_in_calculations')) not in {'True', 'true'}:
                raise ValueError('Metrics require the deduplicated calculation population')
            if r['Type'] not in STATUSES:
                raise ValueError('Unexpected status in calculation population')
            q = number(r['QTY'])
            reason = ('missing_or_invalid_quantity' if q is None else
                      'fractional_quantity' if q != q.to_integral_value() else
                      'negative_quantity' if q < 0 else 'zero_quantity' if q == 0 else None)
            if reason:
                exclusions.append({'source_records': r.get('source_records', ''),
                                   'Type': r['Type'], 'PART': r['PART'],
                                   'QTY': r['QTY'], 'reason': reason})
            else:
                dimensions = [r[key].strip() or 'Unknown' for key in DIMENSIONS.values()]
                values.append((r['Type'], int(q), *dimensions))
        connection.executemany('INSERT INTO parts VALUES (?,?,?,?,?,?,?)', values)

        def query(sql):
            return [dict(row) for row in connection.execute(sql)]

        counts = query("SELECT status, COUNT(*) records, SUM(qty) units FROM parts GROUP BY status")
        by_status = {row['status']: row for row in counts}
        inventory = by_status.get('Inventory', {'records': 0, 'units': 0})
        sold = by_status.get('Invoiced', {'records': 0, 'units': 0})
        scrap = by_status.get('Scrapped', {'records': 0, 'units': 0})
        denominator = sold['units'] + scrap['units']
        fraction = str(Decimal(scrap['units']) / Decimal(denominator)) if denominator else None
        inventory_groups = {}
        for dimension in DIMENSIONS:
            inventory_groups[dimension] = query(
                f"SELECT {dimension}, COUNT(*) records, SUM(qty) units FROM parts "
                f"WHERE status='Inventory' GROUP BY {dimension} ORDER BY units DESC, {dimension}")
        inventory_detail = query("SELECT module,subtype,warehouse,condition,COUNT(*) records, "
                                 "SUM(qty) units FROM parts WHERE status='Inventory' "
                                 "GROUP BY module,subtype,warehouse,condition "
                                 "ORDER BY units DESC,module,subtype,warehouse,condition")
        scrap_groups = {}
        for dimensions in [('module',), ('subtype',), ('module', 'subtype'), ('part',)]:
            cols = ','.join(dimensions)
            grouped = query(
                f"SELECT {cols}, SUM(CASE WHEN status='Scrapped' THEN qty ELSE 0 END) scrapped_units, "
                "SUM(CASE WHEN status='Invoiced' THEN qty ELSE 0 END) sold_units, "
                "SUM(CASE WHEN status='Scrapped' THEN 1 ELSE 0 END) scrap_records, "
                "SUM(CASE WHEN status='Invoiced' THEN 1 ELSE 0 END) sale_records "
                f"FROM parts WHERE status IN ('Scrapped','Invoiced') GROUP BY {cols} "
                f"ORDER BY scrapped_units DESC,{cols}")
            for row in grouped:
                total = row['scrapped_units'] + row['sold_units']
                row['disposed_units'] = total
                row['scrap_share'] = str(Decimal(row['scrapped_units']) / Decimal(total)) if total else None
            scrap_groups['_'.join(dimensions)] = grouped
        # Each breakdown partitions the same population; rates are never averaged.
        for rows in inventory_groups.values():
            assert sum(r['units'] for r in rows) == inventory['units']
        assert sum(r['units'] for r in inventory_detail) == inventory['units']
        for rows in scrap_groups.values():
            assert sum(r['scrapped_units'] for r in rows) == scrap['units']
            assert sum(r['sold_units'] for r in rows) == sold['units']
        return {
            'input_records': len(records), 'eligible_records': len(values),
            'excluded_records': len(exclusions), 'exclusions': exclusions,
            'inventory_units': inventory['units'], 'inventory_records': inventory['records'],
            'sold_units': sold['units'], 'sale_records': sold['records'],
            'scrapped_units': scrap['units'], 'scrap_records': scrap['records'],
            'disposed_units': denominator, 'scrap_share': fraction,
            'inventory_by': inventory_groups, 'inventory_detail': inventory_detail,
            'scrap_by': scrap_groups, 'breakdowns_reconcile': True,
        }
    finally:
        connection.close()


def write_csv(path, rows, columns):
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def pct(value):
    return f'{Decimal(value)*100:.2f}%' if value is not None else 'Unavailable'


def report(result):
    s = result
    lines = [
        '# Inventory totals and scrap share\n',
        'Identical records count once. This report sums quantities (units), not rows. '
        'It describes the supplied historical export; no current inventory snapshot date is established.\n',
        '## Main numbers\n',
        '| Question | Answer |', '| --- | ---: |',
        f"| How many units are on hand? | {s['inventory_units']:,} |",
        f"| How many units were sold, before returns? | {s['sold_units']:,} |",
        f"| How many units were scrapped? | {s['scrapped_units']:,} |",
        f"| What share of observed disposed units was scrapped? | {pct(s['scrap_share'])} |",
        '', '## How the calculation works\n',
        '**Inventory:** add positive whole-number quantities on Inventory records. '
        'Group the same units by module, subtype, warehouse or condition. '
        'These are different views of the same inventory; do not add their totals together.\n',
        '**Scrap share:** scrapped units divided by (scrapped units + positive sold units). '
        'Returns/credits are excluded from this denominator, not subtracted from sales. '
        'Inventory is excluded because it has no observed final outcome.\n',
        f"For this export: **{s['scrapped_units']:,} ÷ ({s['scrapped_units']:,} + "
        f"{s['sold_units']:,}) = {pct(s['scrap_share'])}**.\n",
        'For a small illustration, one scrap record containing 20 units and eight sale records '
        'containing 10 units each give 20 ÷ (20 + 80) = 20%. Counting rows would give '
        '1 ÷ 9 = 11.1%, which answers a different question.\n',
        'Group shares use each group’s own sold and scrapped units. The overall share is '
        'calculated from overall units, never by averaging group percentages. '
        'With no sold or scrapped units, share is unavailable, not zero.\n',
        '## Inventory by module\n', '| Module | Units |', '| --- | ---: |',
        *[f"| {r['module']} | {r['units']:,} |" for r in s['inventory_by']['module']],
        '', '## Scrap by module\n', '| Module | Scrapped units | Sold units | Scrap share |',
        '| --- | ---: | ---: | ---: |',
        *[f"| {r['module']} | {r['scrapped_units']:,} | {r['sold_units']:,} | {pct(r['scrap_share'])} |"
          for r in s['scrap_by']['module']],
        '', '## Parts with the most scrapped units\n',
        '| Part | Scrapped units | Sold units | Scrap share |', '| --- | ---: | ---: | ---: |',
        *[f"| {r['part']} | {r['scrapped_units']:,} | {r['sold_units']:,} | {pct(r['scrap_share'])} |"
          for r in [r for r in s['scrap_by']['part'] if r['scrapped_units'] > 0][:10]],
        '', '## Coverage and interpretation\n',
        f"- {s['input_records']:,} deduplicated records were read; {s['eligible_records']:,} "
        f"have positive whole-number quantity. {s['excluded_records']:,} others are listed "
        'in `quantity_exclusions.csv` with source references and reasons.',
    ]
    for status in sorted(STATUSES):
        excluded = [r for r in s['exclusions'] if r['Type'] == status]
        negative = [r for r in excluded if r['reason'] == 'negative_quantity']
        zeros = [r for r in excluded if r['reason'] == 'zero_quantity']
        others = len(excluded)-len(negative)-len(zeros)
        lines.append(f'- {status}: excluded {len(negative):,} negative-quantity records, '
                     f'{len(zeros):,} zero-quantity records and {others:,} unavailable/fractional quantities.')
    lines += [
        '- Missing classifications display as Unknown and remain included. Missing repair amounts, '
        'dates or condition do not remove an otherwise valid quantity from these two metrics.',
        f"- {s.get('quarantined_cases', 0):,} unresolved source cases remain quarantined by the audit "
        'and are absent from these totals.',
        '- This scrap share compares observed outcomes across the export. It is not the probability '
        'that a newly acquired part will fail: there are no matched lifecycle cohorts or scrap dates.',
        '- A high share with only one or two disposed units is weak evidence. Every breakdown '
        'includes its unit denominator and record counts.',
        '- The inventory breakdowns reconcile to the inventory total; scrap breakdowns reconcile '
        'to both sold and scrapped totals. CSV shares are fractions: 0.20 means 20%.',
        '', 'Reproduce with `python3 -m src.metrics`. This first rebuilds the audit from the raw CSV. '
        'Use `--input`, `--output-dir`, and `--audit-dir` for another same-schema export.\n',
    ]
    return '\n'.join(lines)


def run(input_path, output_dir, audit_dir, weak_margin=Decimal('.20'), max_expected_days=3650):
    if output_dir.resolve() == audit_dir.resolve():
        raise ValueError('Metric and audit directories must differ')
    if input_path.resolve().is_relative_to(output_dir.resolve()):
        raise ValueError('Keep the input outside the metrics output directory')
    audit_summary = audit(input_path, audit_dir, max_expected_days=max_expected_days)
    candidate = audit_dir/'calculation_records.csv'
    with candidate.open(encoding='utf-8', newline='') as f:
        records = list(csv.DictReader(f))
    result = calculate(records)
    repair = economics.calculate(records, weak_margin)
    intervals = timing.calculate(records, max_expected_days)
    queue = build_queue(records, weak_margin=weak_margin)
    baseline = scrap_model.calculate(records)
    intervals['quarantined_cases'] = audit_summary['accounting']['quarantined_cases']
    repair['quarantined_cases'] = audit_summary['accounting']['quarantined_cases']
    if not repair['excluded_records']:
        controls = audit_summary['calculation_controls'].get('Invoiced', {})
        for field, name in [('Extended Sales Price', 'sales'), ('Repair Ext Cost', 'repair_cost')]:
            expected = controls.get(field, {}).get('sum')
            if expected is not None and Decimal(expected) != Decimal(repair['signed_total'][name]):
                raise AssertionError('Economics signed amounts do not reconcile to the audit')
    for status, key in [('Inventory', 'inventory_units'), ('Invoiced', 'sold_units'), ('Scrapped', 'scrapped_units')]:
        # The export has only whole quantities; a future fractional quantity is excluded explicitly.
        if not any(r['Type'] == status and r['reason'] == 'fractional_quantity' for r in result['exclusions']):
            control = audit_summary['calculation_controls'].get(status, {}).get('QTY', {}).get('positive_sum', '0')
            if Decimal(control) != result[key]:
                raise AssertionError('Audit quantity control does not match metrics')
    result['source_sha256'] = audit_summary['source_sha256']
    result['quarantined_cases'] = audit_summary['accounting']['quarantined_cases']
    result['calculation_input_sha256'] = hashlib.sha256(candidate.read_bytes()).hexdigest()
    repair['source_sha256'] = result['source_sha256']
    repair['calculation_input_sha256'] = result['calculation_input_sha256']
    intervals['source_sha256'] = result['source_sha256']
    intervals['calculation_input_sha256'] = result['calculation_input_sha256']
    baseline['source_sha256'] = result['source_sha256']
    baseline['calculation_input_sha256'] = result['calculation_input_sha256']
    result['timing'] = intervals['summary']
    result['review_queue'] = {status: sum(r['status'] == status for r in queue)
                              for status in ('Review', 'Insufficient evidence', 'No rule triggered')}
    result['economics'] = {key: repair[key] for key in ('positive_sales', 'credits', 'signed_total',
                                                     'excluded_records', 'weak_margin_threshold')}
    result['scrap_baseline'] = {key: baseline[key] for key in ('available', 'history_records',
                                                            'outcome_parts', 'features')}
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir/'metrics.json', result)
    write_json(output_dir/'scrap_model.json', baseline)
    (output_dir/'SCRAP_MODEL_EXPLAINED.md').write_text(scrap_model.report(baseline), encoding='utf-8')
    write_csv(output_dir/'scrap_model_stock_scores.csv', baseline['inventory_scores'], scrap_model.SCORE_COLUMNS)
    write_csv(output_dir/'scrap_model_holdout_predictions.csv', baseline['validation']['predictions'],
              scrap_model.PREDICTION_COLUMNS)
    write_csv(output_dir/'scrap_model_calibration.csv', baseline['validation']['calibration'],
              ['score_band', 'records', 'mean_score', 'observed_scrap_share'])
    write_csv(output_dir/'scrap_model_exclusions.csv', baseline['excluded_history'],
              ['source_records', 'part', 'type', 'qty', 'reason'])
    write_csv(output_dir/'review_queue.csv', queue, QUEUE_COLUMNS)
    write_json(output_dir/'review_queue.json', {
        'source_sha256': result['source_sha256'],
        'calculation_input_sha256': result['calculation_input_sha256'],
        'rules': {'weak_margin': str(weak_margin), 'min_sale_records': 5,
                  'review_zero_sales_losses': True,
                  'scrap_share_at_least': '0.50', 'min_disposed_units': 10},
        'status_counts': result['review_queue'], 'queue': queue})
    (output_dir/'REVIEW_QUEUE_EXPLAINED.md').write_text(
        '# Inventory review queue\n\n'
        'Positive on-hand stock is grouped by part number before attaching independently aggregated history. '
        'Each deduplicated historical record contributes once, regardless of how many stock locations exist.\n\n'
        f"- Review: {result['review_queue']['Review']:,} part numbers.\n"
        f"- Insufficient evidence: {result['review_queue']['Insufficient evidence']:,} part numbers.\n"
        f"- No rule triggered: {result['review_queue']['No rule triggered']:,} part numbers.\n\n"
        f'Repair review requires at least five eligible positive-sale records and aggregate repair '
        f'contribution margin below {Decimal(weak_margin):.0%}, or zero sales with negative repair '
        'contribution. In the zero-sales case, the percentage margin remains unavailable. '
        'Scrap review requires at least ten '
        'disposed units and observed scrap share at least 50%. These are adjustable assumptions in the app.\n\n'
        'Review items are ranked by number of triggered rules, then on-hand units descending, then '
        'part number. This is an inspection priority, not an expected loss estimate. The CSV includes '
        'all parts on hand; only Review items have a numeric rank.\n\n'
        'Insufficient evidence means neither rule has its minimum usable support. No rule triggered '
        'means at least one rule has support but neither triggers; check each evidence-support field '
        'before drawing conclusions. Neither status establishes low risk. Zero-cost sale coverage '
        'and flagged stock record counts are included for inspection.\n\n'
        'App location/condition filters select stock only. History uses all deduplicated records for '
        'the selected part numbers and is not a condition-matched prediction. No date interval is '
        'used for ranking. OH_DATE is assumed to mean overhaul date, not receipt date.\n\n'
        'Missing future repair quotes, acquisition cost, scrap recovery value, receipt dates and '
        'snapshot date prevent an automatic repair-or-scrap decision or a current aging watchlist.\n',
        encoding='utf-8')
    (output_dir/'METRICS_EXPLAINED.md').write_text(report(result), encoding='utf-8')
    write_json(output_dir/'economics.json', repair)
    (output_dir/'REPAIR_ECONOMICS_EXPLAINED.md').write_text(economics.report(repair), encoding='utf-8')
    write_json(output_dir/'timing.json', intervals)
    (output_dir/'TIMING_EXPLAINED.md').write_text(timing.report(intervals), encoding='utf-8')
    write_csv(output_dir/'timing_details.csv', intervals['details'], timing.DETAIL_COLUMNS)
    write_csv(output_dir/'timing_comparison_exclusions.csv', intervals['comparison_exclusions'], timing.DETAIL_COLUMNS)
    write_csv(output_dir/'timing_observed_exclusions.csv', intervals['observed_exclusions'],
              ['source_records', 'part', 'qty', 'oh_date', 'invoice_date', 'reasons'])
    for name, rows in intervals['by'].items():
        write_csv(output_dir/f'timing_by_{name}.csv', rows, name.split('_') + timing.SUMMARY_COLUMNS)
    for key, name in [('positive_details','positive_sales'), ('credit_details','credits'),
                      ('weak_transactions','weak_transactions')]:
        write_csv(output_dir/f'economics_{name}.csv', repair[key], economics.DETAIL_COLUMNS)
    for name, rows in repair['by'].items():
        write_csv(output_dir/f'economics_by_{name}.csv', rows,
                  name.split('_') + economics.SUMMARY_COLUMNS)
    write_csv(output_dir/'economics_part_review.csv', repair['part_review'],
              ['part'] + economics.SUMMARY_COLUMNS + ['review_reason'])
    write_csv(output_dir/'economics_exclusions.csv', repair['exclusions'],
              ['source_records', 'part', 'qty', 'sales', 'repair_cost', 'reasons'])
    write_csv(output_dir/'quantity_exclusions.csv', result['exclusions'],
              ['source_records', 'Type', 'PART', 'QTY', 'reason'])
    for name, rows in result['inventory_by'].items():
        write_csv(output_dir/f'inventory_by_{name}.csv', rows, [name, 'records', 'units'])
    write_csv(output_dir/'inventory_detail.csv', result['inventory_detail'],
              ['module', 'subtype', 'warehouse', 'condition', 'records', 'units'])
    for name, rows in result['scrap_by'].items():
        write_csv(output_dir/f'scrap_by_{name}.csv', rows, name.split('_') +
                  ['scrapped_units', 'sold_units', 'scrap_records', 'sale_records', 'disposed_units', 'scrap_share'])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path('Case_Study_Dataset.csv'))
    parser.add_argument('--output-dir', type=Path, default=Path('reports/metrics'))
    parser.add_argument('--audit-dir', type=Path, default=Path('reports/audit'))
    parser.add_argument('--weak-margin', type=Decimal, default=Decimal('.20'),
                        help='Review margin threshold as a fraction (default: 0.20)')
    parser.add_argument('--max-expected-days', type=int, default=3650,
                        help='Audit and timing expected-days review threshold (default: 3650)')
    args = parser.parse_args()
    result = run(args.input, args.output_dir, args.audit_dir, args.weak_margin, args.max_expected_days)
    print(json.dumps({k: result[k] for k in ('inventory_units', 'sold_units', 'scrapped_units',
                                           'disposed_units', 'scrap_share', 'excluded_records')}, indent=2))


if __name__ == '__main__':
    main()
