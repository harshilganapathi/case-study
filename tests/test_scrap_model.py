"""Leakage, evidence, probability and held-out evaluation regressions."""
import copy
import math
import unittest

from src import scrap_model


def record(status, part='A', qty='1', **changes):
    r = {'Type':status, 'PART':part, 'QTY':str(qty), 'Module':'CORE', 'SubType':'HVM',
         'included_in_calculations':'True', 'source_records':f'{part}-{status}'}
    r.update(changes)
    return r


def sample():
    return [record(kind, f'P{index:02d}', Module=module)
            for index in range(30)
            for kind,module in [('Scrapped','CORE'),('Invoiced','FAN')]]


class ScrapModelTests(unittest.TestCase):
    def test_inventory_and_credits_never_supply_labels(self):
        rows = [record('Inventory',qty=1000),record('Invoiced',qty=-1),
                record('Scrapped',qty=0),record('Scrapped',qty='1.5'),
                record('Invoiced',qty='NaN'),record('Scrapped',part=''),
                record('Scrapped',part='S'),record('Invoiced',part='I')]
        history, exclusions = scrap_model.history(rows)
        self.assertEqual([r['scrapped'] for r in history],[1,0])
        self.assertEqual(len(exclusions),5)
        self.assertEqual(len(history),2)
        with self.assertRaisesRegex(ValueError,'deduplicated'):
            scrap_model.calculate([record('Invoiced',included_in_calculations='False')])

    def test_bulk_quantity_does_not_multiply_training_evidence(self):
        rows = [record('Scrapped',qty=1000),record('Invoiced')]
        model = scrap_model.calculate(rows)['model']
        self.assertEqual(model['records'],2)
        self.assertEqual(model['overall_score'],0.5)
        rows[0]['QTY'] = '1'
        self.assertEqual(scrap_model.calculate(rows)['model'],model)

    def test_smoothing_and_fallback_have_worked_values(self):
        rows = [record('Scrapped',Module='CORE'),record('Invoiced',Module='FAN')]
        history,_ = scrap_model.history(rows)
        model = scrap_model.fit(history,prior_strength=2)
        # Overall=.5, CORE=(1+2*.5)/3=2/3, CORE/HVM=(1+2*2/3)/3=7/9.
        pair = scrap_model.predict(model,'CORE','HVM')
        self.assertAlmostEqual(pair['baseline_scrap_score'],7/9)
        self.assertEqual(pair['category_history_records'],1)
        self.assertEqual(pair['evidence_level'],'Module + subtype')
        module = scrap_model.predict(model,'CORE','unseen')
        self.assertAlmostEqual(module['baseline_scrap_score'],2/3)
        self.assertEqual(module['evidence_level'],'Module')
        fallback = scrap_model.predict(model,'unseen','HVM')
        self.assertEqual(fallback['baseline_scrap_score'],0.5)
        self.assertEqual(fallback['category_history_records'],0)
        self.assertEqual(fallback['evidence_level'],'Overall fallback')
        self.assertEqual(scrap_model.predict(model,'','')['baseline_scrap_score'],0.5)

    def test_post_outcome_fields_cannot_change_fit_or_predictions(self):
        original = sample()
        changed = copy.deepcopy(original)
        for row in changed:
            row.update({'Condition':'X','WHSE':'LEAK','Invoice Date':'2023-08-21',
                        'OH_DATE':'2020-01-01','Repair Ext Cost':'999999',
                        'Extended Sales Price':'0','AvgNoofSalesDays':'1','TAG_NO':'LEAK'})
        self.assertEqual(scrap_model.calculate(original)['model'],scrap_model.calculate(changed)['model'])
        self.assertEqual(scrap_model.calculate(original)['validation'],scrap_model.calculate(changed)['validation'])

    def test_split_is_deterministic_and_part_disjoint(self):
        history,_ = scrap_model.history(sample())
        train,test = scrap_model.split_by_part(history)
        self.assertFalse({r['part'] for r in train} & {r['part'] for r in test})
        self.assertEqual(len({r['part'] for r in test}),6)
        reversed_train,reversed_test = scrap_model.split_by_part(list(reversed(history)))
        self.assertEqual({r['part'] for r in train},{r['part'] for r in reversed_train})
        self.assertEqual({r['part'] for r in test},{r['part'] for r in reversed_test})
        self.assertEqual(scrap_model.evaluate(history),scrap_model.evaluate(list(reversed(history))))

    def test_heldout_labels_do_not_change_the_evaluated_predictions(self):
        history,_ = scrap_model.history(sample())
        _,test = scrap_model.split_by_part(history)
        test_parts = {r['part'] for r in test}
        changed = [dict(r,scrapped=1-r['scrapped']) if r['part'] in test_parts else dict(r) for r in history]
        before = scrap_model.evaluate(history)
        after = scrap_model.evaluate(changed)
        self.assertTrue(before['available'] and after['available'])
        self.assertEqual([r['baseline_scrap_score'] for r in before['predictions']],
                         [r['baseline_scrap_score'] for r in after['predictions']])
        self.assertEqual(before['training_scrap_record_share'],after['training_scrap_record_share'])
        self.assertNotEqual(before['comparison'],after['comparison'])

    def test_probability_metrics_and_auc_ties(self):
        metric = scrap_model.probability_metrics([1,0],[0.8,0.2])
        self.assertAlmostEqual(metric['brier_score'],0.04)
        self.assertAlmostEqual(metric['log_loss'],-math.log(0.8))
        self.assertEqual(metric['roc_auc'],1)
        self.assertEqual(scrap_model.probability_metrics([1,0],[.5,.5])['roc_auc'],.5)
        self.assertEqual(scrap_model.probability_metrics([1,0],[.2,.8])['roc_auc'],0)
        self.assertIsNone(scrap_model.probability_metrics([1,1],[.5,.5])['roc_auc'])
        for labels,scores in [([],[]),([1],[.2,.3]),([2],[.4]),([1],[float('nan')]),([0],[2])]:
            with self.assertRaises(ValueError):
                scrap_model.probability_metrics(labels,scores)

    def test_empty_single_class_and_insufficient_group_evidence(self):
        for rows in ([],[record('Inventory')],[record('Scrapped')],[record('Invoiced')]):
            result = scrap_model.calculate(rows)
            self.assertFalse(result['available'])
            self.assertFalse(result['validation']['available'])
            self.assertEqual(result['inventory_scores'],[])
            self.assertTrue(result['reason'])
        same_part = scrap_model.calculate([record('Scrapped'),record('Invoiced')])
        self.assertTrue(same_part['available'])
        self.assertFalse(same_part['validation']['available'])
        for strength in (0,-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):
                scrap_model.fit([],prior_strength=strength)

    def test_stock_is_aggregated_by_part_and_categories_with_visible_fallback(self):
        history = [record('Scrapped'),record('Invoiced')]
        stock = [record('Inventory',qty=3),record('Inventory',qty=7),
                 record('Inventory',part='B',qty=2,Module='NEW'),
                 record('Inventory',qty=-1),record('Inventory',qty='1.5')]
        result = scrap_model.calculate(history+stock)
        scores = {r['part']:r for r in result['inventory_scores']}
        self.assertEqual(scores['A']['on_hand_units'],10)
        self.assertEqual(scores['B']['evidence_level'],'Overall fallback')
        self.assertEqual(scores['B']['category_history_records'],0)
        filtered = scrap_model.score_inventory([stock[0]],result['model'])
        self.assertEqual(filtered[0]['on_hand_units'],3)
        self.assertEqual(filtered[0]['baseline_scrap_score'],scores['A']['baseline_scrap_score'])

    def test_calibration_counts_and_scores_reconcile_with_holdout(self):
        result = scrap_model.calculate(sample())
        validation = result['validation']
        self.assertTrue(validation['available'])
        self.assertEqual(len(validation['predictions']),validation['test_records'])
        self.assertEqual(sum(r['records'] for r in validation['calibration']),validation['test_records'])
        self.assertTrue(all(0 <= r['mean_score'] <= 1 and 0 <= r['observed_scrap_share'] <= 1
                            for r in validation['calibration']))
        self.assertLess(validation['comparison'][0]['brier_score'],
                        validation['comparison'][1]['brier_score'])
