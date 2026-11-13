"""Hand-calculated repair contribution and credit fixtures."""
import unittest
from decimal import Decimal

from src.economics import calculate


def sale(sales='1000', cost='700', qty='1', **changes):
    r = {'Type':'Invoiced', 'PART':'0001', 'Module':'CORE', 'SubType':'Airfoils',
         'QTY':qty, 'Extended Sales Price':sales, 'Repair Ext Cost':cost,
         'included_in_calculations':'True', 'source_records':'[2]'}
    r.update(changes)
    return r


class EconomicsTests(unittest.TestCase):
    def test_basic_contribution_and_margin(self):
        s = calculate([sale()])
        self.assertEqual(Decimal(s['positive_sales']['contribution']), 300)
        self.assertEqual(Decimal(s['positive_sales']['margin']), Decimal('.3'))
        self.assertEqual(s['weak_transactions'], [])

    def test_extended_amounts_not_multiplied_by_quantity(self):
        s = calculate([sale(qty='10')])
        self.assertEqual(Decimal(s['positive_sales']['contribution']), 300)
        self.assertEqual(Decimal(s['positive_sales']['sales']), 1000)
        self.assertEqual(Decimal(s['positive_sales']['units']), 10)

    def test_group_margin_uses_totals_and_missing_classifications_are_kept(self):
        s = calculate([sale('100','0', Module=''), sale('900','900', Module='FAN')])
        self.assertEqual(Decimal(s['positive_sales']['margin']), Decimal('.1'))
        self.assertEqual({r['module'] for r in s['by']['module']}, {'Unknown','FAN'})
        self.assertTrue(s['breakdowns_reconcile'])

    def test_negative_result_and_part_offset_are_both_visible(self):
        s = calculate([sale('500','700'), sale('1000','0', source_records='[3]')])
        self.assertEqual(len(s['weak_transactions']), 1)
        self.assertEqual(Decimal(s['weak_transactions'][0]['contribution']), -200)
        self.assertEqual(s['part_review'], [])
        self.assertEqual(s['positive_sales']['negative_contribution_records'], 1)

    def test_zero_cost_is_included_missing_cost_is_excluded(self):
        s = calculate([sale('100','0'), sale('100',''), sale('100','NaN')])
        self.assertEqual(s['positive_sales']['records'], 1)
        self.assertEqual(s['positive_sales']['zero_cost_records'], 1)
        self.assertEqual(s['excluded_records'], 2)
        self.assertEqual(s['nonzero_cost_positive_sales']['records'], 0)
        self.assertIsNone(s['nonzero_cost_positive_sales']['margin'])

    def test_credits_preserve_signs_and_do_not_change_positive_margin(self):
        s = calculate([sale(),sale('-500','-200','-1')])
        self.assertEqual(Decimal(s['positive_sales']['margin']), Decimal('.3'))
        self.assertEqual(Decimal(s['credits']['sales']), -500)
        self.assertEqual(Decimal(s['credits']['repair_cost']), -200)
        self.assertEqual(Decimal(s['signed_total']['sales']), 500)
        self.assertEqual(Decimal(s['signed_total']['contribution']), 0)
        self.assertEqual(len(s['credit_details']), 1)
        self.assertEqual(s['weak_transactions'], [])

    def test_conflicting_signs_and_invalid_quantities_are_explicit(self):
        s = calculate([sale('-100','10'),sale('100','-10'),sale('100','10','-1'),
                       sale(qty='0'),sale(qty='1.5'),sale(qty='NaN')])
        self.assertEqual(s['excluded_records'], 6)
        self.assertEqual(s['positive_sales']['records'], 0)
        self.assertIsNone(s['positive_sales']['margin'])
        self.assertIn('sales_sign_conflicts',s['exclusions'][0]['reasons'])

    def test_zero_sales_contribution_remains_visible_without_division_by_zero(self):
        s = calculate([sale('0','100'),sale('0','0')])
        self.assertEqual(Decimal(s['positive_sales']['contribution']), -100)
        self.assertIsNone(s['positive_sales']['margin'])
        self.assertEqual(len(s['weak_transactions']), 2)
        self.assertEqual(len(s['part_review']), 1)

    def test_decimal_amounts_and_threshold_boundary(self):
        s = calculate([sale('1.00','.80'),sale('.10','.09', PART='0002')])
        self.assertEqual(Decimal(s['positive_sales']['contribution']), Decimal('.21'))
        self.assertEqual([r['part'] for r in s['weak_transactions']], ['0002'])
        self.assertEqual(calculate([sale('1','.8')], Decimal('.21'))['positive_sales']['weak_records'], 1)
        for threshold in ['NaN','Infinity','-0.1','1.1']:
            with self.assertRaises(ValueError):
                calculate([], threshold)

    def test_duplicate_audit_copy_cannot_be_used(self):
        with self.assertRaisesRegex(ValueError,'deduplicated'):
            calculate([sale(included_in_calculations='False')])


if __name__ == '__main__':
    unittest.main()
