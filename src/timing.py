"""Overhaul-to-invoice intervals; OH_DATE is assumed to be the overhaul date."""
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal
from statistics import median

from .ingest import number

DETAIL_COLUMNS = ['source_records', 'part', 'module', 'subtype', 'qty', 'oh_date',
                  'invoice_date', 'observed_days', 'expected_days', 'difference_days',
                  'above_expected', 'long_observed_interval', 'comparison_exclusion']
SUMMARY_COLUMNS = ['observed_records', 'paired_records', 'median_observed_days',
                   'paired_median_observed_days', 'paired_median_expected_days',
                   'median_paired_difference_days', 'above_expected_records',
                   'above_expected_share', 'long_observed_records']


def parse_date(value, field, flags):
    if f'invalid_date:{field}' in flags:
        return None
    try:
        parsed = date.fromisoformat(value)
        return parsed if parsed.isoformat() == value else None
    except (ValueError, TypeError):
        return None


def middle(values):
    return str(median([Decimal(str(v)) for v in values])) if values else None


def summarize(rows):
    paired = [r for r in rows if not r['comparison_exclusion']]
    above = sum(r['above_expected'] for r in paired)
    return {'observed_records': len(rows), 'paired_records': len(paired),
            'median_observed_days': middle([r['observed_days'] for r in rows]),
            'paired_median_observed_days': middle([r['observed_days'] for r in paired]),
            'paired_median_expected_days': middle([r['expected_days'] for r in paired]),
            'median_paired_difference_days': middle([r['difference_days'] for r in paired]),
            'above_expected_records': above,
            'above_expected_share': str(Decimal(above)/len(paired)) if paired else None,
            'long_observed_records': sum(r['long_observed_interval'] for r in rows)}


def calculate(records, max_expected_days=3650):
    if max_expected_days <= 0:
        raise ValueError('Expected-days review threshold must be positive')
    details, exclusions = [], []
    invoices, positive_candidates = 0, 0
    for r in records:
        if str(r.get('included_in_calculations')) not in {'True', 'true'}:
            raise ValueError('Timing requires the deduplicated calculation population')
        if r['Type'] != 'Invoiced':
            continue
        invoices += 1
        qty = number(r['QTY'])
        reasons = []
        if qty is None or qty != qty.to_integral_value():
            reasons.append('missing_invalid_or_fractional_quantity')
        elif qty <= 0:
            reasons.append('credit_or_nonpositive_quantity')
        else:
            positive_candidates += 1
        flags = json.loads(r.get('audit_flags', '[]'))
        oh = parse_date(r.get('OH_DATE', ''), 'OH_DATE', flags)
        invoice = parse_date(r.get('Invoice Date', ''), 'Invoice Date', flags)
        if oh is None:
            reasons.append('oh_date_missing_or_invalid')
        if invoice is None:
            reasons.append('invoice_date_missing_or_invalid')
        days = (invoice-oh).days if invoice and oh else None
        if days is not None and days < 0:
            reasons.append('negative_oh_to_invoice_interval')
        if reasons:
            exclusions.append({'source_records': r.get('source_records', ''), 'part': r['PART'],
                               'qty': r['QTY'], 'oh_date': r.get('OH_DATE', ''),
                               'invoice_date': r.get('Invoice Date', ''), 'reasons': ';'.join(reasons)})
            continue
        expected = number(r.get('AvgNoofSalesDays', ''))
        exclusion = ('expected_days_missing_or_invalid' if expected is None else
                     'expected_days_nonpositive' if expected <= 0 else
                     'expected_days_above_review_threshold' if expected > max_expected_days else '')
        difference = Decimal(days)-expected if not exclusion else None
        details.append({'source_records': r.get('source_records', ''),
                        'part': r['PART'], 'module': r.get('Module', '').strip() or 'Unknown',
                        'subtype': r.get('SubType', '').strip() or 'Unknown', 'qty': str(qty),
                        'oh_date': oh.isoformat(), 'invoice_date': invoice.isoformat(),
                        'observed_days': days, 'expected_days': str(expected) if expected is not None else None,
                        'difference_days': str(difference) if difference is not None else None,
                        'above_expected': difference > 0 if difference is not None else None,
                        'long_observed_interval': days > max_expected_days,
                        'comparison_exclusion': exclusion})
    by = {}
    for dimensions in [('module',), ('subtype',), ('module', 'subtype')]:
        buckets = defaultdict(list)
        for r in details:
            buckets[tuple(r[k] for k in dimensions)].append(r)
        by['_'.join(dimensions)] = [dict(zip(dimensions, key), **summarize(rows))
                                   for key, rows in sorted(buckets.items())]
    total = summarize(details)
    for rows in by.values():
        for field in ('observed_records', 'paired_records', 'above_expected_records'):
            if sum(r[field] for r in rows) != total[field]:
                raise AssertionError('Timing coverage does not reconcile')
    assert invoices == len(details)+len(exclusions)
    return {'oh_date_assumption': 'OH_DATE is assumed to be the overhaul date; business definition unverified',
            'invoiced_records': invoices, 'positive_quantity_candidates': positive_candidates,
            'max_expected_days': max_expected_days, 'summary': total, 'details': details,
            'observed_exclusions': exclusions,
            'comparison_exclusions': [r for r in details if r['comparison_exclusion']],
            'by': by, 'coverage_reconciles': True}


def report(s):
    def show(value):
        return str(value) if value is not None else 'Unavailable'
    def percent(value):
        return f'{Decimal(value)*100:.2f}%' if value is not None else 'Unavailable'
    p = s['summary']
    lines = ['# Overhaul to sale timing explained\n',
             '**OH_DATE is assumed to be the overhaul date**. '
             'The export does not independently verify this business definition. '
             'The calculation measures calendar days from overhaul to invoice; receipt dates '
             'and current stock age are not inferred.\n',
             '## What we calculate\n',
             '**Observed interval = invoice date − OH_DATE**, in calendar days. '
             'For a Jan 1 OH date and an Apr 1 invoice in a non-leap year, this is 90 days. '
             'If the supplied expectation is 60 days, the paired difference is +30 days.\n',
             'The supplied `AvgNoofSalesDays` is used as the comparison benchmark; the fields may use different '
             'starting points. A positive difference means the recorded interval exceeds the '
             'supplied expectation; it does not establish slow inventory or a missed sales target.\n',
             '## Results\n', '| Measure | Result |', '| --- | ---: |',
             f"| Positive-quantity invoice records considered | {s['positive_quantity_candidates']:,} |",
             f"| Records with a usable OH-to-invoice interval | {p['observed_records']:,} |",
             f"| Median interval across usable records | {show(p['median_observed_days'])} days |",
             f"| Records with both usable interval and expectation | {p['paired_records']:,} |",
             f"| Median observed interval on paired records | {show(p['paired_median_observed_days'])} days |",
             f"| Median supplied expectation on paired records | {show(p['paired_median_expected_days'])} days |",
             f"| Median of individual paired differences | {show(p['median_paired_difference_days'])} days |",
             f"| Paired intervals above supplied expectation | {percent(p['above_expected_share'])} |",
             '', 'The median paired difference is calculated from each record’s observed-minus-expected '
             'difference. It is not the difference between two independently calculated medians. '
             'Each deduplicated transaction counts once in these timing statistics; a bulk quantity '
             'does not provide additional independently observed sale dates.\n',
             '## Paired comparison by module\n',
             '| Module | Usable intervals | Paired records | Median paired difference in days | Above expected |',
             '| --- | ---: | ---: | ---: | ---: |']
    for r in s['by']['module']:
        lines.append(f"| {r['module']} | {r['observed_records']:,} | {r['paired_records']:,} | "
                     f"{show(r['median_paired_difference_days'])} | {percent(r['above_expected_share'])} |")
    lines += ['', '## What is excluded and preserved\n',
              f"- {s['invoiced_records']:,} deduplicated invoice records were read. "
              f"{len(s['observed_exclusions']):,} cannot enter the observed-interval calculation. "
              'The exclusion CSV lists every source reference and all applicable reasons.',
              '- Returns/nonpositive quantities, invalid/fractional quantities, missing or invalid dates, '
              'and negative date intervals are excluded. A same-day interval is valid zero days.',
              f"- {len(s['comparison_exclusions']):,} otherwise valid intervals have an unusable expectation. "
              'Their observed intervals remain included in the overall interval statistics.',
              f"- Expected days must be positive and no greater than {s['max_expected_days']:,}. "
              'This configurable review threshold follows the audit rule; it is an assumption. '
              'Values are neither replaced nor capped.',
              f"- {p['long_observed_records']:,} observed intervals exceed that threshold. "
              'They remain included and flagged: a long interval alone does not prove a bad date.',
              f"- {s.get('quarantined_cases', 0):,} unresolved source cases remain absent from the calculation population. "
              'Missing classifications display as Unknown. Identical records count once.',
              '- No stock age is calculated: receipt dates and an inventory snapshot date are unavailable. '
              'We do not subtract OH dates from today’s date.',
              '- These are records of completed positive-quantity sales. They cannot establish how '
              'long unsold inventory will take to sell. The origin and calculation window of '
              '`AvgNoofSalesDays` are also unknown.',
              '', '## Reproduce and inspect\n',
              'Run `python3 -m src.metrics`; use `--max-expected-days 3650` to set the review threshold. '
              'The same threshold is used in the audit and timing comparison.\n',
              '- `timing_details.csv`: every valid observed interval, expected value, comparison difference and flags.',
              '- `timing_observed_exclusions.csv`: invoices without a usable interval, including returns.',
              '- `timing_comparison_exclusions.csv`: valid intervals excluded only from paired comparisons.',
              '- `timing_by_module.csv`, `timing_by_subtype.csv`, `timing_by_module_subtype.csv`: '
              'coverage and statistics for each group.',
              '- `timing.json`: results, source hashes and coverage checks.\n']
    return '\n'.join(lines)
