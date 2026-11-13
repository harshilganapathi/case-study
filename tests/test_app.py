"""Live Streamlit tests; skipped explicitly if UI dependencies are unavailable."""
import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.ingest import FIELDS
try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None


@unittest.skipIf(AppTest is None, 'Streamlit is not installed; live app checks require requirements.txt')
class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        path = Path(self.temp.name)/'fixture.csv'
        def row(status, qty, part='A', tag='STOCK', module='CORE'):
            r = dict.fromkeys(FIELDS,'NULL')
            r.update({'Type':status,'PART':part,'SN':'NSI','Description':'VALVE','QTY':str(qty),
                      'Condition':'R','TAG_NO':tag,'WHSE':'MDT' if status=='Inventory' else 'NULL',
                      'Module':module,'SubType':'HVM','OH_DATE':'1/1/2023',
                      'Invoice Date':'4/1/2023' if status=='Invoiced' else 'NULL',
                      'Repair Ext Cost':'90','Repair Unit Cost':'90',
                      'Extended Sales Price':'100' if status=='Invoiced' else 'NULL',
                      'Unit Sales Price':'100' if status=='Invoiced' else 'NULL','AvgNoofSalesDays':'60'})
            return r
        inventory = row('Inventory',10)
        rows = [inventory,inventory,row('Inventory',5,'B',module='FAN'),row('Scrapped',10)]
        rows += [row('Invoiced',1,tag=f'SALE-{i}') for i in range(5)]
        with path.open('w',newline='') as f:
            writer = csv.DictWriter(f,fieldnames=FIELDS)
            writer.writeheader(); writer.writerows(rows)
        self.environment=patch.dict(os.environ,{'PARTS_DATA_PATH':str(path)})
        self.environment.start()
        self.app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30)
        self.app.run()

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def test_every_view_renders_and_overview_is_deduplicated(self):
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.metric[0].value,'15')
        for view in ['Scrap','Repair economics','Inventory & timing','Review queue','Scrap-risk baseline','Data quality']:
            self.app.sidebar.radio[0].set_value(view).run()
            self.assertFalse(self.app.exception,view)

    def test_search_filters_and_empty_states_on_every_view(self):
        self.app.sidebar.text_input[0].set_value('missing-part').run()
        self.assertEqual(self.app.metric[0].value,'0')
        for view in ['Scrap','Repair economics','Inventory & timing','Review queue','Scrap-risk baseline','Data quality']:
            self.app.sidebar.radio[0].set_value(view).run()
            self.assertFalse(self.app.exception,view)

    def test_filters_and_review_rule_change(self):
        self.app.sidebar.multiselect[0].set_value(['FAN']).run()
        self.assertEqual(self.app.metric[0].value,'5')
        self.app.sidebar.multiselect[0].set_value([]).run()
        self.app.sidebar.radio[0].set_value('Review queue').run()
        self.assertEqual(self.app.metric[0].value,'1')
        self.app.number_input(key='queue_min_sales').set_value(10).run()
        self.app.number_input(key='queue_min_disposed').set_value(100).run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.metric[0].value,'0')

    def test_bad_schema_is_shown_as_load_error(self):
        bad = Path(self.temp.name)/'bad.csv'
        bad.write_text('unexpected,header\na,b\n')
        with patch.dict(os.environ,{'PARTS_DATA_PATH':str(bad)}):
            self.app.run()
        self.assertFalse(self.app.exception)
        self.assertIn('schema mismatch',self.app.error[0].value)

    def test_selected_part_reasons_are_readable_outside_the_table(self):
        self.app.sidebar.radio[0].set_value('Review queue').run()
        self.assertFalse(self.app.exception)
        reasons = [item.value for item in self.app.info]
        self.assertTrue(any('Repair contribution margin 10.0%' in text for text in reasons))
        self.assertTrue(any('Scrap share 66.7%' in text for text in reasons))
        self.app.sidebar.text_input[0].set_value('missing-part').run()
        self.assertEqual(len(self.app.info), 1)
        self.assertIn('No positive inventory', self.app.info[0].value)

    def test_chart_focus_preserves_timing_statistics(self):
        path = Path(self.temp.name)/'fixture.csv'
        with path.open(newline='') as f:
            rows = list(csv.DictReader(f))
        next(r for r in rows if r['Type'] == 'Invoiced')['OH_DATE'] = '1/1/2000'
        with path.open('w',newline='') as f:
            writer = csv.DictWriter(f,fieldnames=FIELDS)
            writer.writeheader(); writer.writerows(rows)
        self.app.sidebar.radio[0].set_value('Inventory & timing').run()
        before = [metric.value for metric in self.app.metric]
        self.assertTrue(any('Showing 4 of 5 paired records' in c.value for c in self.app.caption))
        self.app.checkbox(key='timing_full_range').check().run()
        self.assertFalse(self.app.exception)
        self.assertEqual([metric.value for metric in self.app.metric], before)
        self.assertTrue(any('Showing 5 of 5 paired records' in c.value for c in self.app.caption))

    def test_zero_revenue_loss_replacement_export_is_visible_in_default_queue(self):
        path = Path(self.temp.name)/'fixture.csv'
        with path.open(newline='') as f:
            original = list(csv.DictReader(f))
        stock = [r for r in original if r['Type'] == 'Inventory']
        template = next(r for r in original if r['Type'] == 'Invoiced')
        for count in (5, 10):
            with self.subTest(sale_records=count):
                losses = [dict(template, **{'TAG_NO':f'LOSS-{index}', 'Unit Sales Price':'0',
                          'Extended Sales Price':'0', 'Repair Unit Cost':'10', 'Repair Ext Cost':'10'})
                          for index in range(count)]
                with path.open('w',newline='') as f:
                    writer = csv.DictWriter(f,fieldnames=FIELDS)
                    writer.writeheader(); writer.writerows(stock + losses)
                self.app.sidebar.radio[0].set_value('Review queue').run()
                self.assertFalse(self.app.exception)
                self.assertEqual(self.app.metric[0].value, '1')
                self.assertTrue(any(f'contribution -{count*10:.2f} across {count} eligible sale records'
                                    in info.value for info in self.app.info))

    def test_scrap_baseline_filters_select_stock_without_retraining_history(self):
        self.app.sidebar.radio[0].set_value('Scrap-risk baseline').run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.metric[0].value,'6')
        self.assertTrue(any('Evaluation needs separate part groups' in item.value for item in self.app.info))
        self.app.sidebar.multiselect[0].set_value(['FAN']).run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.metric[0].value,'6')
        scores = self.app.dataframe[0].value
        self.assertEqual(list(scores['part']),['B'])
        self.assertEqual(list(scores['on_hand_units']),[5])
        self.app.number_input(key='baseline_min_score').set_value(100).run()
        self.assertTrue(any('No stock groups match' in item.value for item in self.app.info))
        self.assertFalse(self.app.exception)

    def test_scrap_baseline_handles_missing_and_single_class_outcomes(self):
        path = Path(self.temp.name)/'fixture.csv'
        with path.open(newline='') as f:
            rows = list(csv.DictReader(f))
        stock = [r for r in rows if r['Type']=='Inventory']
        for outcome in (None,'Invoiced','Scrapped'):
            with self.subTest(outcome=outcome):
                selected = stock + [r for r in rows if r['Type']==outcome]
                with path.open('w',newline='') as f:
                    writer=csv.DictWriter(f,fieldnames=FIELDS)
                    writer.writeheader();writer.writerows(selected)
                self.app.sidebar.radio[0].set_value('Scrap-risk baseline').run()
                self.assertFalse(self.app.exception)
                self.assertTrue(any('Need at least one eligible sold and one scrapped record'
                                    in item.value for item in self.app.info))
