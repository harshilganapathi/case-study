import unittest
from decimal import Decimal

from src.decision_support import build_queue


def record(status, qty, part='A', **changes):
    r = {'Type':status,'QTY':str(qty),'PART':part,'Module':'CORE','SubType':'HVM',
         'WHSE':'MDT','Condition':'R','included_in_calculations':'True','audit_flags':'[]',
         'Extended Sales Price':'100','Repair Ext Cost':'90','source_records':'[2]'}
    r.update(changes)
    return r


class QueueTests(unittest.TestCase):
    def test_both_rules_with_independent_aggregation_and_location_filters(self):
        stock = [record('Inventory',3),record('Inventory',4,WHSE='HAJ')]
        history = [record('Invoiced',1) for _ in range(5)]+[record('Scrapped',10)]
        r = build_queue(stock+history)[0]
        self.assertEqual(r['on_hand_units'],7)
        self.assertEqual(r['eligible_sale_records'],5)
        self.assertEqual(r['sales'],'500')
        self.assertEqual(r['disposed_units'],15)
        self.assertEqual(r['triggered_rules'],2)
        self.assertEqual(r['rank'],1)
        filtered = build_queue(stock+history, [stock[0]])[0]
        self.assertEqual(filtered['on_hand_units'],3)
        self.assertEqual(filtered['sales'],'500')
        self.assertEqual(filtered['warehouses'],'MDT')

    def test_insufficient_history_is_not_zero_risk(self):
        r = build_queue([record('Inventory',1),record('Invoiced',1)])[0]
        self.assertEqual(r['status'],'Insufficient evidence')
        self.assertIsNone(r['rank'])
        self.assertFalse(r['repair_evidence_supported'])

    def test_evidence_support_without_rule_trigger(self):
        rows = [record('Inventory',1)]+[record('Invoiced',2,**{'Repair Ext Cost':'0'}) for _ in range(5)]
        r = build_queue(rows)[0]
        self.assertEqual(r['status'],'No rule triggered')
        self.assertTrue(r['repair_evidence_supported'])
        self.assertEqual(r['zero_cost_sale_share'],'1')

    def test_threshold_changes_and_tie_breaks(self):
        rows = [record('Inventory',2,'B'),record('Inventory',2,'A')]
        rows += [record('Scrapped',10,p) for p in ['A','B']]
        q = build_queue(rows)
        self.assertEqual([r['part'] for r in q],['A','B'])
        self.assertEqual([r['rank'] for r in q],[1,2])
        raised = build_queue(rows, min_disposed=11)
        self.assertTrue(all(r['status']=='Insufficient evidence' for r in raised))
        # Changing the margin boundary actually changes inclusion.
        finance = [record('Inventory',1)]+[record('Invoiced',1) for _ in range(5)]
        self.assertEqual(build_queue(finance,weak_margin=Decimal('.11'))[0]['status'],'Review')
        self.assertEqual(build_queue(finance,weak_margin=Decimal('.09'))[0]['status'],'No rule triggered')

    def test_credit_and_bad_stock_not_counted(self):
        rows = [record('Inventory',1),record('Inventory',-10),record('Inventory',0),
                record('Invoiced',-1,**{'Extended Sales Price':'-100','Repair Ext Cost':'-90'})]
        r = build_queue(rows)[0]
        self.assertEqual(r['on_hand_units'],1)
        self.assertEqual(r['disposed_units'],0)
        self.assertEqual(r['eligible_sale_records'],0)
        self.assertIsNone(r['repair_margin'])

    def test_missing_cost_does_not_become_zero_margin_evidence(self):
        rows = [record('Inventory',1)]+[record('Invoiced',1,**{'Repair Ext Cost':''}) for _ in range(5)]
        r = build_queue(rows)[0]
        self.assertEqual(r['eligible_sale_records'],0)
        self.assertEqual(r['status'],'Insufficient evidence')

    def test_noninventory_parts_are_absent_and_invalid_rules_fail(self):
        self.assertEqual(build_queue([record('Scrapped',100)]),[])
        for kwargs in [{'min_sales':0},{'min_disposed':0},{'scrap_threshold':'NaN'},{'weak_margin':2}]:
            with self.assertRaises(ValueError):
                build_queue([],**kwargs)
        with self.assertRaises(ValueError):
            build_queue([record('Inventory',1,included_in_calculations='False')])

    def test_zero_revenue_losses_trigger_review_without_inventing_a_margin(self):
        for count in (5, 10):
            with self.subTest(sale_records=count):
                rows = [record('Inventory', 1)] + [record('Invoiced', 1,
                        **{'Extended Sales Price':'0', 'Repair Ext Cost':'10'}) for _ in range(count)]
                r = build_queue(rows)[0]
                self.assertEqual(r['status'], 'Review')
                self.assertEqual(r['triggered_rules'], 1)
                self.assertEqual(r['rank'], 1)
                self.assertTrue(r['repair_evidence_supported'])
                self.assertIsNone(r['repair_margin'])
                self.assertEqual(Decimal(r['repair_contribution']), Decimal(-10*count))
                self.assertIn('Repair costs exceed zero sales', r['reasons'])

    def test_zero_revenue_rule_still_requires_support_and_an_actual_loss(self):
        insufficient = [record('Inventory', 1)] + [record('Invoiced', 1,
                        **{'Extended Sales Price':'0','Repair Ext Cost':'10'}) for _ in range(4)]
        self.assertEqual(build_queue(insufficient)[0]['status'], 'Insufficient evidence')
        no_loss = [record('Inventory', 1)] + [record('Invoiced', 1,
                        **{'Extended Sales Price':'0','Repair Ext Cost':'0'}) for _ in range(5)]
        r = build_queue(no_loss)[0]
        self.assertTrue(r['repair_evidence_supported'])
        self.assertEqual(r['status'], 'No rule triggered')
        self.assertEqual(r['triggered_rules'], 0)
