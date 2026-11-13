"""Worked business examples for unit totals and scrap share."""
import csv
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from src.ingest import FIELDS
from src.metrics import calculate, run


def record(status, qty, **changes):
    r = {'Type': status, 'QTY': str(qty), 'Module': 'CORE', 'SubType': 'Airfoils',
         'WHSE': 'MDT', 'Condition': 'R', 'PART': '0001', 'included_in_calculations': 'True',
         'source_records': '[2]'}
    r.update(changes)
    return r


class CalculationTests(unittest.TestCase):
    def test_quantity_weighting_not_row_count(self):
        rows = [record('Scrapped', 20)] + [record('Invoiced', 10) for _ in range(8)]
        s = calculate(rows)
        self.assertEqual(s['scrapped_units'], 20)
        self.assertEqual(s['sold_units'], 80)
        self.assertEqual(Decimal(s['scrap_share']), Decimal('.2'))
        self.assertEqual(s['scrap_by']['module'][0]['disposed_units'], 100)

    def test_inventory_returns_and_zero_do_not_enter_scrap_denominator(self):
        rows = [record('Inventory', 900), record('Inventory', -9), record('Inventory', 0),
                record('Invoiced', 80), record('Invoiced', -20), record('Scrapped', 20)]
        s = calculate(rows)
        self.assertEqual(s['inventory_units'], 900)
        self.assertEqual(s['disposed_units'], 100)
        self.assertEqual(Decimal(s['scrap_share']), Decimal('.2'))
        self.assertEqual(s['excluded_records'], 3)

    def test_overall_share_is_not_average_of_group_shares(self):
        s = calculate([record('Scrapped', 1, Module='FAN'),
                       record('Invoiced', 99, Module='CORE')])
        self.assertEqual(Decimal(s['scrap_share']), Decimal('.01'))
        self.assertEqual({r['module']: Decimal(r['scrap_share']) for r in s['scrap_by']['module']},
                         {'FAN': Decimal(1), 'CORE': Decimal(0)})

    def test_unknown_dimensions_are_included_and_inventory_breakdowns_reconcile(self):
        s = calculate([record('Inventory', 3, Module='', Condition='', WHSE=''),
                       record('Inventory', 5, SubType='')])
        self.assertEqual(s['inventory_units'], 8)
        self.assertIn({'condition': 'Unknown', 'records': 1, 'units': 3},
                      s['inventory_by']['condition'])
        for rows in s['inventory_by'].values():
            self.assertEqual(sum(r['units'] for r in rows), 8)
        self.assertTrue(s['breakdowns_reconcile'])

    def test_no_disposed_units_is_unavailable_not_zero(self):
        for rows in [[], [record('Inventory', 10)], [record('Invoiced', -1)]]:
            self.assertIsNone(calculate(rows)['scrap_share'])

    def test_invalid_nonfinite_fractional_and_missing_quantity_are_explicit(self):
        rows = [record('Inventory', q) for q in ['', 'NULL', 'NaN', '1.5']]
        s = calculate(rows)
        self.assertEqual(s['inventory_units'], 0)
        self.assertEqual(s['excluded_records'], 4)
        self.assertEqual(s['exclusions'][-1]['reason'], 'fractional_quantity')

    def test_all_copy_audit_input_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'deduplicated'):
            calculate([record('Inventory', 1, included_in_calculations='False')])

    def test_end_to_end_deduplication_and_replacement_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'input.csv'
            def write(rows):
                with source.open('w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction='ignore')
                    writer.writeheader()
                    writer.writerows(rows)
            priced_sale = record('Invoiced', 80, **{'Extended Sales Price': '1000', 'Repair Ext Cost': '700',
                                  'OH_DATE': '1/1/2023', 'Invoice Date': '4/1/2023', 'AvgNoofSalesDays': '60'})
            write([record('Scrapped', 20), record('Scrapped', 20), priced_sale, priced_sale,
                   record('Inventory', 10)])
            s = run(source, root/'metrics', root/'audit')
            self.assertEqual(s['scrapped_units'], 20)
            self.assertEqual(Decimal(s['scrap_share']), Decimal('.2'))
            self.assertEqual(s['input_records'], 3)
            self.assertEqual(Decimal(s['economics']['positive_sales']['contribution']), 300)
            self.assertEqual(s['timing']['observed_records'], 1)
            self.assertEqual(s['timing']['median_paired_difference_days'], '30')
            baseline = json.loads((root/'metrics'/'scrap_model.json').read_text())
            self.assertTrue(baseline['available'])
            self.assertEqual(baseline['history_records'],2)
            self.assertFalse(baseline['validation']['available'])
            self.assertEqual(baseline['source_sha256'],s['source_sha256'])
            with (root/'metrics'/'scrap_model_stock_scores.csv').open() as f:
                stock_scores = list(csv.DictReader(f))
            self.assertEqual(len(stock_scores),1)
            self.assertEqual(stock_scores[0]['on_hand_units'],'10')
            with (root/'metrics'/'economics_positive_sales.csv').open() as f:
                self.assertEqual(len(list(csv.DictReader(f))), 1)
            first_hash = s['source_sha256']
            limited = run(source, root/'metrics', root/'audit', max_expected_days=50)
            self.assertEqual(limited['timing']['paired_records'], 0)
            self.assertEqual(limited['timing']['observed_records'], 1)
            audit_summary = json.loads((root/'audit'/'audit.json').read_text())
            self.assertEqual(audit_summary['expected_days_review_threshold'], 50)
            self.assertTrue((root/'metrics'/'inventory_detail.csv').exists())
            write([record('Scrapped', 10), record('Invoiced', 90)])
            s = run(source, root/'metrics', root/'audit')
            self.assertNotEqual(s['source_sha256'], first_hash)
            self.assertEqual(Decimal(s['scrap_share']), Decimal('.1'))
            self.assertEqual(s['inventory_units'], 0)
            baseline = json.loads((root/'metrics'/'scrap_model.json').read_text())
            self.assertEqual(baseline['inventory_scores'],[])
            self.assertEqual(s['economics']['excluded_records'], 1)
            self.assertEqual(s['economics']['positive_sales']['records'], 0)
            self.assertEqual(s['timing']['observed_records'], 0)
            with (root/'metrics'/'timing_details.csv').open() as f:
                self.assertEqual(list(csv.DictReader(f)), [])
            with (root/'metrics'/'economics_positive_sales.csv').open() as f:
                self.assertEqual(list(csv.DictReader(f)), [])
            with (root/'metrics'/'inventory_by_module.csv').open() as f:
                self.assertEqual(list(csv.DictReader(f)), [])
            self.assertEqual(json.loads((root/'metrics'/'metrics.json').read_text())['scrapped_units'], 10)


if __name__ == '__main__':
    unittest.main()
