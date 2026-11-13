"""Timing fixtures separate known date arithmetic from unconfirmed date meaning."""
import unittest
from datetime import date, timedelta
from decimal import Decimal

from src.timing import calculate


def invoice(days=90, expected='60', **changes):
    start = date(2023,1,1)
    r = {'Type':'Invoiced', 'PART':'0001', 'Module':'CORE', 'SubType':'Airfoils', 'QTY':'1',
         'OH_DATE':start.isoformat(), 'Invoice Date':(start+timedelta(days=days)).isoformat(),
         'AvgNoofSalesDays':expected, 'included_in_calculations':'True', 'source_records':'[2]',
         'audit_flags':'[]'}
    r.update(changes)
    return r


class TimingTests(unittest.TestCase):
    def test_calendar_interval_expected_difference_and_fraction(self):
        s = calculate([invoice()])
        self.assertEqual(s['details'][0]['observed_days'],90)
        self.assertEqual(Decimal(s['details'][0]['difference_days']),30)
        self.assertEqual(Decimal(s['summary']['above_expected_share']),1)

    def test_median_of_paired_differences_not_difference_of_medians(self):
        s = calculate([invoice(1,'1'),invoice(100,'100'),invoice(101,'2')])['summary']
        self.assertEqual(Decimal(s['paired_median_observed_days']),100)
        self.assertEqual(Decimal(s['paired_median_expected_days']),2)
        self.assertEqual(Decimal(s['median_paired_difference_days']),0)

    def test_missing_or_outlier_expectations_only_exclude_comparison(self):
        s = calculate([invoice(expected=e) for e in ['', 'NaN','131638','0','-1','60']])
        self.assertEqual(s['summary']['observed_records'],6)
        self.assertEqual(s['summary']['paired_records'],1)
        self.assertEqual(len(s['comparison_exclusions']),5)
        self.assertEqual(s['summary']['median_observed_days'],'90')

    def test_returns_missing_invalid_dates_and_negative_intervals(self):
        rows = [invoice(QTY='-1'),invoice(QTY='NaN'),invoice(QTY='1.5'),
                invoice(**{'OH_DATE':''}),invoice(**{'Invoice Date':'invalid'}),invoice(-1)]
        s = calculate(rows)
        self.assertEqual(len(s['observed_exclusions']),6)
        self.assertEqual(s['summary']['observed_records'],0)
        self.assertIsNone(s['summary']['above_expected_share'])
        self.assertIn('negative_oh_to_invoice_interval',s['observed_exclusions'][-1]['reasons'])

    def test_audit_invalid_date_flag_cannot_be_overridden_by_iso_parsing(self):
        s = calculate([invoice(**{'OH_DATE':'0222-02-17', 'audit_flags':'["invalid_date:OH_DATE"]'})])
        self.assertEqual(s['summary']['observed_records'],0)

    def test_zero_day_interval_ties_and_fractional_expectations(self):
        s = calculate([invoice(0,'1'),invoice(1,'1'),invoice(2,'1.5')])
        self.assertEqual(s['summary']['paired_records'],3)
        self.assertEqual(s['summary']['above_expected_records'],1)
        self.assertEqual(s['details'][-1]['difference_days'],'0.5')

    def test_long_observed_interval_is_flagged_not_capped_or_removed(self):
        s = calculate([invoice(4000,'20')])
        self.assertEqual(s['summary']['median_observed_days'],'4000')
        self.assertEqual(s['summary']['long_observed_records'],1)
        self.assertEqual(s['summary']['paired_records'],1)

    def test_groups_unknown_classification_and_transaction_weighting(self):
        s = calculate([invoice(10,'10',QTY='100',Module=''),invoice(100,'10')])
        self.assertEqual(s['summary']['median_observed_days'],'55')
        self.assertEqual({r['module'] for r in s['by']['module']},{'Unknown','CORE'})
        self.assertTrue(s['coverage_reconciles'])

    def test_review_threshold_boundary_and_input_guard(self):
        s = calculate([invoice(expected='100'),invoice(expected='101')],100)
        self.assertEqual(s['summary']['paired_records'],1)
        with self.assertRaises(ValueError):
            calculate([invoice(included_in_calculations='False')])
        with self.assertRaises(ValueError):
            calculate([],0)


if __name__ == '__main__':
    unittest.main()
