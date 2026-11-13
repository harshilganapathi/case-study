"""Failure-focused fixtures for the observed export corruption and accounting."""
import csv
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from src.audit import extension_checks, run
from src.clean import normalize
from src.ingest import FIELDS, Record, decode, ingest_rows, load, number


def row(**changes):
    values = dict.fromkeys(FIELDS, 'NULL')
    values.update({'Type': 'Invoiced', 'PART': '001-ABC', 'Invoice Date': '8/21/2023',
                   'SN': '0007', 'Description': 'Valve', 'QTY': '2', 'Condition': 'R',
                   'TAG_NO': '0009', 'OH_DATE': '7/21/2023', 'Repair Unit Cost': '10',
                   'Repair Ext Cost': '20', 'Unit Sales Price': '50',
                   'Extended Sales Price': '100', 'Module': 'CORE', 'SubType': 'HVM',
                   'AvgNoofSalesDays': '90'})
    values.update(changes)
    return [values[k] for k in FIELDS]


def split(values, extra='NULL'):
    return [values[:5] + [''] * 20,
            [values[5]] + values[7:] + [extra] + [''] * 5]


class IngestTests(unittest.TestCase):
    def test_common_split_mapping_and_provenance(self):
        original = row()
        result = ingest_rows(split(original, '12.34'))
        self.assertFalse(result.quarantine)
        self.assertEqual(len(result.records), 1)
        recovered = result.records[0]
        expected = dict(zip(FIELDS, original))
        expected['Condition'] = ''
        self.assertEqual(recovered.values, expected)
        self.assertEqual(recovered.source_records, (2, 3))
        self.assertEqual(recovered.unlabelled_tail, '12.34')

    def test_inventory_split(self):
        result = ingest_rows(split(row(**{'Type': 'Inventory', 'Invoice Date': 'NULL',
                                         'WHSE': 'MDT'})))
        self.assertEqual(result.records[0].values['WHSE'], 'MDT')

    def test_nozzle_quantity_is_not_inferred_from_equal_amounts(self):
        base = row(Description='')
        head = base[:5] + [''] * 20
        tail = ['NOZZLE'] + base[6:] + ['123'] + [''] * 4
        result = ingest_rows([head, tail])
        self.assertFalse(result.records)
        self.assertEqual(result.quarantine[0].reason, 'ambiguous_split')
        self.assertEqual(result.quarantine[0].raw_rows, [head, tail])

    def test_invalid_mapping_is_quarantined(self):
        for changes in [{'Module': 'MDT'}, {'OH_DATE': 'not a date'},
                        {'Extended Sales Price': 'price'}, {'QTY': 'NaN'},
                        {'QTY': '1.5'}, {'TAG_NO': 'NULL'}]:
            with self.subTest(changes=changes):
                result = ingest_rows(split(row(**changes)))
                self.assertFalse(result.records)
                self.assertEqual(result.quarantine[0].reason, 'ambiguous_split')

    def test_unmatched_heads_do_not_consume_next_valid_record(self):
        result = ingest_rows([split(row())[0], row()])
        self.assertEqual(result.records[0].source_records, (3,))
        self.assertEqual(result.quarantine[0].source_records, (2,))

    def test_orphans_wrong_width_and_accounting(self):
        result = ingest_rows([['bad'], ['orphan'] + ['']*24, row(), []])
        all_refs = [i for r in result.records + result.quarantine for i in r.source_records]
        self.assertEqual(sorted(all_refs), [2, 3, 4, 5])
        self.assertEqual(len(result.quarantine), 3)

    def test_encoding_policy_has_no_character_replacement(self):
        text, encoding = decode('Válve'.encode('cp1252'))
        self.assertEqual(text, 'Válve')
        self.assertEqual(encoding, 'cp1252')
        self.assertEqual(decode(b'Valve')[1], 'utf-8-sig')
        with self.assertRaises(UnicodeDecodeError):
            decode(b'\x81')

    def test_schema_drift_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'bad.csv'
            path.write_text('PART,Type\na,Inventory\n')
            with self.assertRaisesRegex(ValueError, 'schema mismatch'):
                load(path)


class NormalizationTests(unittest.TestCase):
    def test_iso_dates_share_the_same_normalization_and_flags_as_source_dates(self):
        source = dict(zip(FIELDS, row()))
        iso = dict(source, **{'Invoice Date':'2023-08-21', 'OH_DATE':'2023-07-21'})
        self.assertEqual(normalize(Record(iso, (2,)), 3650),
                         normalize(Record(source, (2,)), 3650))
        invalid = dict(iso, **{'Invoice Date':'2023-02-30'})
        self.assertIn('invalid_date:Invoice Date', normalize(Record(invalid, (2,)), 3650)[1])
        self.assertIn('invoice_date_unavailable', normalize(Record(invalid, (2,)), 3650)[1])

    def test_identifier_zero_and_unknown_are_preserved(self):
        record = Record(dict(zip(FIELDS, row(**{'Repair Unit Cost': '0',
                                              'Repair Ext Cost': 'NULL'}))), (2,))
        values, flags = normalize(record, 3650)
        self.assertEqual(values['PART'], '001-ABC')
        self.assertEqual(values['SN'], '0007')
        self.assertEqual(values['Repair Unit Cost'], '0')
        self.assertEqual(values['Repair Ext Cost'], '')
        self.assertEqual(values['Invoice Date'], '2023-08-21')
        self.assertIn('reported_zero:Repair Unit Cost', flags)
        self.assertIn('cost_unavailable:Repair Ext Cost', flags)

    def test_outlier_and_invalid_values_stay_visible(self):
        record = Record(dict(zip(FIELDS, row(**{'AvgNoofSalesDays': '131638',
                                              'QTY': 'not available'}))), (2,))
        values, flags = normalize(record, 3650)
        self.assertEqual(values['AvgNoofSalesDays'], '131638')
        self.assertEqual(values['QTY'], 'not available')
        self.assertIn('quantity_unavailable', flags)
        self.assertIn('expected_days_outside_review_range', flags)

    def test_nonfinite_numbers_are_invalid(self):
        for value in ['NaN', 'Infinity', '-Infinity', '', 'NULL']:
            self.assertIsNone(number(value))

    def test_negative_date_interval(self):
        record = Record(dict(zip(FIELDS, row(**{'OH_DATE': '9/21/2023'}))), (2,))
        self.assertIn('negative_oh_to_invoice_interval', normalize(record, 3650)[1])

    def test_signed_extension_does_not_flip_credit(self):
        credit = row(**{'QTY': '-2', 'Unit Sales Price': '-50',
                        'Extended Sales Price': '-100', 'Repair Unit Cost': '-10',
                        'Repair Ext Cost': '-20'})
        record = ingest_rows([credit]).records[0]
        check = extension_checks([record])['Invoiced']['Extended Sales Price']
        self.assertEqual(check['naive_qty_times_unit_mismatches'], 1)
        self.assertEqual(check['signed_unit_times_absolute_qty_mismatches'], 0)
        self.assertEqual(record.values['Extended Sales Price'], '-100')


class EndToEndTests(unittest.TestCase):
    def test_outputs_deduplication_and_repeatability(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'input.csv'
            with source.open('w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(FIELDS)
                writer.writerows([row(), row(), *split(row(PART='RECOVERED')), ['orphan']+['']*24])
            original = source.read_bytes()
            first = run(source, root/'first')
            second = run(source, root/'second')
            self.assertEqual(first, second)
            for path in (root/'first').iterdir():
                self.assertEqual(path.read_bytes(), (root/'second'/path.name).read_bytes())
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(first['accounting']['raw_data_rows'], 5)
            self.assertEqual(first['accounting']['accepted_logical_records'], 3)
            self.assertEqual(first['accounting']['quarantined_source_rows'], 1)
            self.assertEqual(first['duplicate_candidates']['excess_records'], 1)
            self.assertEqual(Decimal(first['all_accepted_controls']['Invoiced']['Extended Sales Price']['sum']), 300)
            self.assertEqual(Decimal(first['calculation_controls']['Invoiced']['Extended Sales Price']['sum']), 200)
            self.assertEqual(first['accounting']['calculation_records'], 2)
            self.assertTrue(first['deduplication_controls_reconcile'])
            with (root/'first'/'calculation_records.csv').open() as f:
                calculation_rows = list(csv.DictReader(f))
            self.assertEqual(len(calculation_rows), 2)
            self.assertEqual(json.loads(calculation_rows[0]['all_copy_source_records']), [[2], [3]])
            with (root/'first'/'audit_records.csv').open() as f:
                audit_rows = list(csv.DictReader(f))
            self.assertEqual([r['included_in_calculations'] for r in audit_rows], ['True', 'False', 'True'])
            self.assertTrue(first['controls_reconcile'])
            self.assertEqual(len((root/'first'/'quarantine.jsonl').read_text().splitlines()), 1)

    def test_only_identical_records_are_collapsed_including_recovered_and_credit_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'input.csv'
            credit = row(**{'QTY': '-2', 'Unit Sales Price': '-50',
                            'Extended Sales Price': '-100', 'Repair Unit Cost': '-10',
                            'Repair Ext Cost': '-20'})
            records = [row(), row(**{'Extended Sales Price': '101'}), credit, credit,
                       *split(row(PART='RECOVERED')), *split(row(PART='RECOVERED'))]
            with source.open('w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(FIELDS)
                writer.writerows(records)
            summary = run(source, root/'output')
            self.assertEqual(summary['accounting']['calculation_records'], 4)
            self.assertEqual(summary['accounting']['duplicate_copies_excluded_from_calculations'], 2)
            self.assertEqual(Decimal(summary['calculation_controls']['Invoiced']['Extended Sales Price']['sum']), 201)
            self.assertEqual(Decimal(summary['excluded_duplicate_controls']['Invoiced']['Extended Sales Price']['sum']), 0)

    def test_input_cannot_be_overwritten(self):
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            run(Path('/tmp/audit_records.csv'), Path('/tmp'))

    def test_zero_and_negative_review_threshold_rejected(self):
        for threshold in [0, -1]:
            with self.assertRaises(ValueError):
                run(Path('unused'), Path('unused'), threshold)


if __name__ == '__main__':
    unittest.main()
