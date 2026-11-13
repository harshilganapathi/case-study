"""Run with: python3 -m src.audit [--input export.csv] [--output-dir directory]."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from .clean import normalize
from .ingest import FIELDS, NUMERIC, DATES, date, load, missing, number

VERSION = 'audit-v3-oh-overhaul'


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')


def totals(records):
    result = {}
    for status in sorted({r.values['Type'] for r in records}):
        subset = [r for r in records if r.values['Type'] == status]
        result[status] = {'records': len(subset)}
        for key in NUMERIC[:5]:
            nums = [number(r.values[key]) for r in subset]
            valid = [n for n in nums if n is not None]
            result[status][key] = {
                'sum': format(sum(valid, Decimal(0)), 'f') if valid else None,
                'valid_records': len(valid),
                'positive_sum': format(sum((n for n in valid if n > 0), Decimal(0)), 'f'),
                'negative_sum': format(sum((n for n in valid if n < 0), Decimal(0)), 'f'),
                'missing_or_invalid': len(nums) - len(valid),
            }
    return result


def profile(records):
    result = {}
    for status in sorted({r.values['Type'] for r in records}):
        subset = [r for r in records if r.values['Type'] == status]
        columns = {}
        for key in FIELDS:
            vals = [r.values[key] for r in subset]
            nonmissing = [v for v in vals if not missing(v)]
            entry = {'missing': len(vals) - len(nonmissing),
                     'distinct_nonmissing': len(set(nonmissing)),
                     'top_values': Counter(nonmissing).most_common(5)}
            if key in NUMERIC:
                nums = [number(v) for v in nonmissing]
                valid = [n for n in nums if n is not None]
                entry.update(invalid=len(nums)-len(valid), zero=sum(n == 0 for n in valid),
                             negative=sum(n < 0 for n in valid),
                             minimum=str(min(valid)) if valid else None,
                             maximum=str(max(valid)) if valid else None)
            if key in DATES:
                ds = [date(v) for v in nonmissing]
                valid = [d for d in ds if d]
                entry.update(invalid=len(ds)-len(valid), valid=len(valid),
                             minimum=str(min(valid)) if valid else None,
                             maximum=str(max(valid)) if valid else None)
            columns[key] = entry
        result[status] = columns
    return result


def extension_checks(records):
    result = {}
    for status in sorted({r.values['Type'] for r in records}):
        result[status] = {}
        for unit, extended in [('Repair Unit Cost', 'Repair Ext Cost'),
                               ('Unit Sales Price', 'Extended Sales Price')]:
            naive, signed, eligible = [], [], 0
            for r in records:
                if r.values['Type'] != status:
                    continue
                q, u, e = [number(r.values[k]) for k in ('QTY', unit, extended)]
                if any(n is None for n in (q, u, e)):
                    continue
                eligible += 1
                if abs(q*u-e) > Decimal('.01'):
                    naive.append(list(r.source_records))
                if abs(abs(q)*u-e) > Decimal('.01'):
                    signed.append(list(r.source_records))
            result[status][extended] = {
                'eligible_records': eligible, 'naive_qty_times_unit_mismatches': len(naive),
                'signed_unit_times_absolute_qty_mismatches': len(signed),
                'signed_mismatch_source_records': signed,
                'naive_mismatch_examples': naive[:5],
            }
    return result


def run(input_path: Path, output_dir: Path, max_expected_days: int = 3650, encoding=None):
    if max_expected_days <= 0:
        raise ValueError('max-expected-days must be positive')
    names = ['audit_records.csv', 'quarantine.jsonl', 'reconstructions.jsonl',
             'duplicate_candidates.csv', 'audit.json', 'AUDIT_REPORT.md', 'manifest.json',
             'calculation_records.csv']
    if input_path.resolve() in {(output_dir / name).resolve() for name in names}:
        raise ValueError('Output would overwrite the input')
    result = load(input_path, encoding)
    output_dir.mkdir(parents=True, exist_ok=True)
    groups = defaultdict(list)
    for r in result.records:
        key = tuple(r.values[k] for k in FIELDS) + (r.unlabelled_tail,)
        groups[key].append(r)
    duplicate_groups = [g for g in groups.values() if len(g) > 1]
    unique = [g[0] for g in groups.values()]
    representative_refs = {r.source_records for r in unique}
    group_refs = {r.source_records: [member.source_records for member in group]
                  for group in groups.values() for r in group}
    removed = [r for r in result.records if r.source_records not in representative_refs]
    dup_index = {}
    for i, group in enumerate(duplicate_groups, 1):
        for r in group:
            dup_index[r.source_records] = f'duplicate-{i:04}'
    flag_counts, status_flags, calculation_flags = Counter(), defaultdict(Counter), Counter()
    normalized = []
    for r in result.records:
        values, flags = normalize(r, max_expected_days)
        group = dup_index.get(r.source_records, '')
        if group:
            flags.append('exact_duplicate_candidate')
        flag_counts.update(flags)
        status_flags[r.values['Type']].update(flags)
        included = r.source_records in representative_refs
        if included:
            calculation_flags.update(flags)
        values.update(source_records=json.dumps(r.source_records), recovery=r.recovery,
                      unlabelled_tail=r.unlabelled_tail, duplicate_group=group,
                      included_in_calculations=included,
                      all_copy_source_records=json.dumps(group_refs[r.source_records]),
                      audit_flags=json.dumps(sorted(flags)))
        normalized.append(values)
    with (output_dir / names[0]).open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(FIELDS) + ['source_records', 'recovery',
                               'unlabelled_tail', 'duplicate_group', 'included_in_calculations',
                               'all_copy_source_records', 'audit_flags'])
        writer.writeheader()
        writer.writerows(normalized)
    with (output_dir / 'calculation_records.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(normalized[0]) if normalized else
                               list(FIELDS) + ['source_records', 'recovery', 'unlabelled_tail',
                               'duplicate_group', 'included_in_calculations',
                               'all_copy_source_records', 'audit_flags'])
        writer.writeheader()
        writer.writerows(r for r in normalized if r['included_in_calculations'])
    with (output_dir / 'quarantine.jsonl').open('w', encoding='utf-8') as f:
        for q in result.quarantine:
            f.write(json.dumps(vars(q), ensure_ascii=False) + '\n')
    recovered = [r for r in result.records if r.recovery != 'unchanged']
    complete = [r for r in result.records if r.recovery == 'unchanged']
    with (output_dir / 'reconstructions.jsonl').open('w', encoding='utf-8') as f:
        for r in recovered:
            f.write(json.dumps({**vars(r), 'raw_rows': [result.raw_rows[n-2]
                               for n in r.source_records]}, ensure_ascii=False) + '\n')
    with (output_dir / 'duplicate_candidates.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['group', 'Type', 'PART', 'TAG_NO', 'copies', 'source_records',
                         'excess_signed_qty', 'excess_sales_amount', 'excess_repair_amount'])
        for i, g in enumerate(duplicate_groups, 1):
            r = g[0]
            amounts = [number(r.values[k]) for k in ('QTY', 'Extended Sales Price', 'Repair Ext Cost')]
            writer.writerow([f'duplicate-{i:04}', r.values['Type'], r.values['PART'],
                             r.values['TAG_NO'], len(g), json.dumps([a.source_records for a in g]),
                             *[str(n*(len(g)-1)) if n is not None else '' for n in amounts]])
    summary = {
        'version': VERSION, 'encoding': result.encoding, 'source_sha256': result.sha256,
        'source_name': input_path.name, 'expected_days_review_threshold': max_expected_days,
        'accounting': {
            'raw_data_rows': len(result.raw_rows), 'accepted_logical_records': len(result.records),
            'unchanged_records': len(complete), 'reconstructed_records': len(recovered),
            'quarantined_cases': len(result.quarantine),
            'quarantined_source_rows': sum(len(q.source_records) for q in result.quarantine),
            'accepted_source_rows': sum(len(r.source_records) for r in result.records),
            'calculation_records': len(unique),
            'duplicate_copies_excluded_from_calculations': len(removed),
            'raw_rows_accounted_for_exactly_once': True,
        },
        'accepted_status_counts': dict(Counter(r.values['Type'] for r in result.records)),
        'calculation_status_counts': dict(Counter(r.values['Type'] for r in unique)),
        'recovered_status_counts': dict(Counter(r.values['Type'] for r in recovered)),
        'duplicate_candidates': {'groups': len(duplicate_groups),
                                 'records_in_groups': sum(map(len, duplicate_groups)),
                                 'excess_records': sum(len(g)-1 for g in duplicate_groups),
                                 'policy': 'Assume identical source records are repeated export copies; count once and keep first source occurrence'},
        'flags': dict(flag_counts), 'flags_by_status': dict(status_flags),
        'calculation_flags': dict(calculation_flags),
        'profile_by_status': profile(result.records),
        'calculation_profile_by_status': profile(unique),
        'extension_checks': extension_checks(unique),
        'source_controls_complete_records': totals(complete),
        'recovered_controls': totals(recovered),
        'all_accepted_controls': totals(result.records),
        'calculation_controls': totals(unique),
        'excluded_duplicate_controls': totals(removed),
        'quarantine': [vars(q) for q in result.quarantine],
        'reconstruction_examples': [vars(r) for r in recovered[:3]],
    }
    # Reconcile accepted amounts against separately accumulated source and recovery controls.
    for status, measures in summary['all_accepted_controls'].items():
        for key in NUMERIC[:5]:
            parts = [summary[s].get(status, {}).get(key, {}).get('sum')
                     for s in ('source_controls_complete_records', 'recovered_controls')]
            combined = sum((Decimal(v) for v in parts if v is not None), Decimal(0))
            actual = measures[key]['sum']
            if actual is not None and combined != Decimal(actual):
                raise AssertionError(f'Reconciliation failed: {status} {key}')
    summary['controls_reconcile'] = True
    # The calculation population must reconcile to accepted records minus extra copies.
    for status, measures in summary['all_accepted_controls'].items():
        kept = summary['calculation_controls'].get(status, {})
        excluded = summary['excluded_duplicate_controls'].get(status, {})
        for key in NUMERIC[:5]:
            actual = measures[key]['sum']
            parts = [block.get(key, {}).get('sum') for block in (kept, excluded)]
            combined = sum((Decimal(v) for v in parts if v is not None), Decimal(0))
            if actual is not None and Decimal(actual) != combined:
                raise AssertionError(f'Deduplication reconciliation failed: {status} {key}')
        if measures['records'] != kept.get('records', 0) + excluded.get('records', 0):
            raise AssertionError(f'Deduplication record count failed: {status}')
    summary['deduplication_controls_reconcile'] = True
    if hashlib.sha256(input_path.read_bytes()).hexdigest() != result.sha256:
        raise AssertionError('Source file changed during audit')
    summary['raw_source_unchanged'] = True
    write_json(output_dir / 'audit.json', summary)
    (output_dir / 'AUDIT_REPORT.md').write_text(report(summary), encoding='utf-8')
    write_json(output_dir / 'manifest.json', {
        'version': VERSION, 'source_sha256': result.sha256,
        'outputs_sha256': {n: hashlib.sha256((output_dir/n).read_bytes()).hexdigest()
                           for n in names if n != 'manifest.json'},
    })
    return summary


def report(s):
    a, p, c = s['accounting'], s['calculation_profile_by_status'], s['calculation_controls']
    lines = [
        '# Parts inventory data audit\n',
        'The audit recovers only structurally validated split records, counts identical '
        'records once under the documented duplicate-copy assumption, and preserves uncertain values. '
        'Each downstream metric applies its own eligibility rules to the audited calculation population.\n',
        '## Source and reproducibility\n',
        f"- Source: `{s['source_name']}`; SHA-256 `{s['source_sha256']}`.",
        f"- Decoding: `{s['encoding']}` (strict UTF-8 first, explicit Windows-1252 fallback, "
        'unless an encoding override is supplied). Successful decoding does not prove the original encoding.',
        f"- Rule version: `{s['version']}`; expected-days review threshold: "
        f"{s['expected_days_review_threshold']:,} days. This is a configurable review threshold, not an established business limit.",
        '- Run `python3 -m src.audit`. Uses only the Python standard library. '
        'Outputs are UTF-8; numbers use decimal arithmetic; dates are ISO formatted. '
        'Source references are CSV record ordinals with header = 1, not physical line numbers.',
        '- Raw source checksum was verified unchanged after the run.\n',
        '## Record accounting\n',
        '| Measure | Count |', '| --- | ---: |',
        *[f'| {k.replace("_", " ")} | {v:,} |' for k,v in a.items() if isinstance(v,int) and not isinstance(v,bool)],
        '',
        'Every source row is accounted for exactly once, including quarantine. '
        'Recovered pairs become one logical record; this is not deduplication.\n',
        '## Reconstruction and exceptions\n',
        f"The common rule recovered {a['reconstructed_records']:,} pairs by taking the first five "
        'fields from the head, quantity from the continuation, leaving condition unknown, '
        'and mapping the remaining fields through expected sales days. It requires valid '
        'numeric/date shapes, recognized classifications, tag number and status-specific fields. '
        'It does not infer condition from neighboring records.',
        '',
        'The continuation also contains an extra field with no source header. It is retained '
        'as `unlabelled_tail`, never assigned to a named business column. '
        f"{s['flags'].get('unlabelled_tail_value',0):,} recovered records have a non-null value in it.\n",
        f"{a['quarantined_cases']:,} cases are quarantined. Neither amount ratios nor adjacent "
        'quantities are used to fill missing quantities. Malformed, unmatched or ambiguous '
        'records are preserved in full with reasons in `quarantine.jsonl`.\n',
        '| Accepted status | Records | Reconstructed |', '| --- | ---: | ---: |',
        *[f"| {k} | {v:,} | {s['recovered_status_counts'].get(k,0):,} |"
          for k,v in sorted(s['accepted_status_counts'].items())],
        '', 'Example recoveries (see full original and mapped fields in `reconstructions.jsonl`):\n',
        '| Source records | Part | Quantity | Condition | Sales amount | Module |',
        '| --- | --- | ---: | --- | ---: | --- |',
        *[f"| {r['source_records']} | {r['values']['PART']} | {r['values']['QTY']} | Unknown | "
          f"{r['values']['Extended Sales Price']} | {r['values']['Module']} |"
          for r in s['reconstruction_examples']],
        '', 'Quarantine source records: ' + (', '.join(str(q['source_records']) for q in s['quarantine']) or 'None') + '.\n',
        '## Duplicate treatment\n',
        f"There are {s['duplicate_candidates']['groups']:,} exact candidate groups containing "
        f"{s['duplicate_candidates']['records_in_groups']:,} records. Assuming identical records are repeated export copies, "
        f"{s['duplicate_candidates']['excess_records']:,} extra copies are excluded from calculations. "
        'The first source occurrence is kept; all copies remain traceable in the audit file. '
        'Comparison uses reconstructed source field values plus the unlabelled tail, before normalization.\n',
        'The right-hand values below are the authoritative calculation totals after deduplication. '
        'Quarantine is excluded from both columns. No currency is specified by the export.\n',
        '| Status | Signed quantity before deduplication | Calculation quantity | Sales before deduplication | Calculation sales |',
        '| --- | ---: | ---: | ---: | ---: |',
    ]
    for status in sorted(c):
        before = s['all_accepted_controls'][status]
        lines.append(f"| {status} | {before['QTY']['sum']} | {c[status]['QTY']['sum']} | "
                     f"{before['Extended Sales Price']['sum'] or 'Unavailable'} | "
                     f"{c[status]['Extended Sales Price']['sum'] or 'Unavailable'} |")
    lines += [
        '', '## Signed amounts and quantity controls\n',
        'Negative invoiced quantities/prices are preserved as possible credits. '
        'Their business meaning remains unconfirmed. Never turn negative × negative '
        'into positive revenue. Observed extension conventions are checked both as '
        '`quantity × unit` and `abs(quantity) × signed unit`, within 0.01 amount units.\n',
        '| Status | Amount field | Checked | Naive mismatches | Signed convention mismatches |',
        '| --- | --- | ---: | ---: | ---: |',
    ]
    for status, checks in s['extension_checks'].items():
        for field, check in checks.items():
            lines.append(f"| {status} | {field} | {check['eligible_records']:,} | "
                         f"{check['naive_qty_times_unit_mismatches']:,} | "
                         f"{check['signed_unit_times_absolute_qty_mismatches']:,} |")
    lines += ['', '| Status | Positive quantity | Negative quantity | Net quantity |',
              '| --- | ---: | ---: | ---: |']
    for status in sorted(c):
        q = c[status]['QTY']
        lines.append(f"| {status} | {q['positive_sum']} | {q['negative_sum']} | {q['sum']} |")
    lines += [
        '', 'Accepted controls reconcile to unchanged-record controls plus recovery controls '
        'for each status and numeric amount. Complete controls come from original field positions; '
        'recovery controls are separately identified. Quarantined cases are excluded from '
        'accepted controls; their original fields are preserved rather than included through '
        'an uncertain mapping. Accepted controls therefore do not represent the entire export.\n',
        'Calculation totals equal accepted totals minus excluded duplicate copies. '
        'The extension checks, quantity totals and coverage below describe the deduplicated population.\n',
        '## Data coverage and limitations\n',
        '| Status | Missing condition | Zero repair unit cost | Missing/invalid expected days | Expected days maximum |',
        '| --- | ---: | ---: | ---: | ---: |',
    ]
    for status, pp in sorted(p.items()):
        d = pp['AvgNoofSalesDays']
        lines.append(f"| {status} | {pp['Condition']['missing']:,} | {pp['Repair Unit Cost']['zero']:,} | "
                     f"{d['missing'] + d['invalid']:,} | {d['maximum']} |")
    lines += [
        '', f"- {s['calculation_flags'].get('expected_days_outside_review_range',0):,} records have expected days "
        'outside the configurable review range. Raw values are retained; this audit does not cap or impute them.',
        '- Zero repair amounts are reported zeros, not proof of free repair or total cost. Missing repair '
        'amounts remain unknown. No acquisition cost, scrap recovery value or currency field is supplied.',
        '- Invoiced records have no warehouse; scrap records lack financial amounts and dates. '
        'These are status-specific coverage limitations, not fields to fill from unrelated rows.',
        '- There is no confirmed receipt date, snapshot date, or scrap date. '
        '`OH_DATE` is assumed to be the overhaul date. The overhaul-to-invoice interval '
        'measures days after overhaul, rather than confirmed time in inventory. '
        'No present-day stock aging or matched-cohort scrap probability is justified.',
        '- Placeholder serials are not unique identifiers; part number is a product identifier, '
        'not an event identifier. No lifecycle joins or serial-based deletions were attempted.',
        '- Supplied `Non-HVM` classifications are retained. Missing classifications stay empty '
        'for later display as Unknown; they are not inferred from other occurrences of a part.',
        '', '### Invoice date coverage\n',
        f"Invoiced records span {p.get('Invoiced', {}).get('Invoice Date', {}).get('minimum')} "
        f"through {p.get('Invoiced', {}).get('Invoice Date', {}).get('maximum')}. "
        f"There are {p.get('Invoiced', {}).get('OH_DATE', {}).get('valid', 0):,} valid OH dates, "
        f"{p.get('Invoiced', {}).get('OH_DATE', {}).get('missing', 0):,} missing OH dates and "
        f"{p.get('Invoiced', {}).get('OH_DATE', {}).get('invalid', 0):,} invalid OH dates. "
        'Invalid date strings remain visible and flagged; they are not silently converted to missing dates.',
        '', '## Audit outputs and metric use\n',
        '- `audit_records.csv`: normalized candidate records, provenance, duplicate groups and flags. '
        'All copies are preserved; `included_in_calculations` identifies the kept occurrence.',
        '- `calculation_records.csv`: one occurrence per identical record, with source references '
        'for all copies. Use this file for downstream calculations; metric-specific exclusions still apply.',
        '- `quarantine.jsonl`: original unresolved rows and reasons.',
        '- `reconstructions.jsonl`: all repaired pairs, original rows, mappings and unlabelled values.',
        '- `duplicate_candidates.csv`: every duplicate group with source references and excluded amounts.',
        '- `audit.json`: before/after profiles, flags, checks, raw/recovered controls and deduplication reconciliation.',
        '- `manifest.json`: source and output hashes for repeatability checks.',
        '', 'The application applies metric-specific eligibility to these deduplicated records. '
        'Scrap, repair contribution, inventory, overhaul-to-invoice timing and review-queue '
        'definitions are documented in README.md and the metric reports. Credits, unknown '
        'costs and excluded records remain available for inspection.\n',
    ]
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path('Case_Study_Dataset.csv'))
    parser.add_argument('--output-dir', type=Path, default=Path('reports/audit'))
    parser.add_argument('--max-expected-days', type=int, default=3650)
    parser.add_argument('--encoding', default=None)
    args = parser.parse_args()
    summary = run(args.input, args.output_dir, args.max_expected_days, args.encoding)
    print(json.dumps({'output_dir': str(args.output_dir), **summary['accounting'],
                      'raw_source_unchanged': summary['raw_source_unchanged']}, indent=2))


if __name__ == '__main__':
    main()
