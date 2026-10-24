import unittest
from modules import filter_module_rows

class ModuleFilterTests(unittest.TestCase):
    def setUp(self):
        self.rows=[dict(company='Example Supplier',tin='123-456-789',reference='PC-EXAMPLE-001',receipt_no='SI-123',amount=100,method='GCash',code='CS-0001',date='2026-09-01',remaining=100,allocated=0),dict(company='Other Supplier',amount=200,method='Bank',code='OE-0001',date='2026-09-02',remaining=0,allocated=200)]

    def test_search_reference_tin_and_amount(self):
        for query in ['example supplier','123456789','PC EXAMPLE 001','SI123','100']:
            self.assertEqual(filter_module_rows(self.rows,'payment',{'q':query}),self.rows[:1])

    def test_combined_filters(self):
        args=dict(method='GCash',code='CS-0001',status='open',min='90',max='110')
        self.assertEqual(filter_module_rows(self.rows,'payment',args),self.rows[:1])
        self.assertEqual(filter_module_rows(self.rows,'payment',{'from':'2026-09-02','status':'closed'}),self.rows[1:])

    def test_control_amounts_use_pesos(self):
        self.assertEqual(len(filter_module_rows([dict(amount=10000)],'controls',{'min':'100','max':'100'})),1)
        self.assertEqual(filter_module_rows([dict(amount=10000)],'controls',{'min':'101'}),[])

    def test_master_search_and_bad_amount(self):
        self.assertEqual(len(filter_module_rows([dict(code='CS-0001',title='Materials')],'accounts',{'q':'materials'})),1)
        with self.assertRaises(ValueError):filter_module_rows(self.rows,'payment',{'min':'bad'})
