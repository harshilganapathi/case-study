import unittest
from datetime import date
from src.presentation import csv_bytes, invoice_window, select_records


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.rows = [dict(Type='Inventory',Module='',SubType='HVM',PART='001',Description='Valve',
                          Updated_Description='',WHSE='MDT',Condition='R',**{'Invoice Date':''}),
                     dict(Type='Invoiced',Module='CORE',SubType='HVM',PART='002',Description='Tube',
                          Updated_Description='',WHSE='',Condition='O',**{'Invoice Date':'2023-08-01'})]

    def test_filters_and_empty_scope(self):
        self.assertEqual(select_records(self.rows,modules=['Unknown']),self.rows[:1])
        self.assertEqual(select_records(self.rows,search='vAlVe'),self.rows[:1])
        self.assertEqual(select_records(self.rows,warehouses=['MDT']),self.rows[:1])
        self.assertEqual(select_records(self.rows,search='no such part'),[])
        self.assertEqual(select_records(self.rows),self.rows)

    def test_dates_are_only_for_invoice_views(self):
        self.assertEqual(invoice_window(self.rows,date(2023,8,1),date(2023,8,1)),self.rows[1:])
        self.assertEqual(invoice_window(self.rows,date(2024,1,1),date(2024,2,1)),[])
        self.assertEqual(select_records(self.rows),self.rows)

    def test_csv_preserves_identifiers_and_exact_amounts(self):
        data=csv_bytes([{'part':'0001','sales':'123456789.01'}]).decode('utf-8-sig')
        self.assertIn('0001,123456789.01',data)
        self.assertIn('part,sales',data)

    def test_date_filter_respects_audit_flags_and_rejects_noncanonical_dates(self):
        template = self.rows[1]
        for changes in ({'audit_flags':'["invalid_date:Invoice Date"]'},
                        {'Invoice Date':'20230801'}, {'Invoice Date':'2023-W31-2'}):
            with self.subTest(changes=changes):
                self.assertEqual(invoice_window([dict(template, **changes)],
                                               date(2023,8,1), date(2023,8,1)), [])
