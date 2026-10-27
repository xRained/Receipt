"""VAT calculations and persisted recalculation use a disposable database."""
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from contextlib import closing

import app as module
from vat import purchase_vat, automatic_withholding


class VatTests(unittest.TestCase):
    def test_inclusive_split_and_cent_rounding(self):
        for tag, goods, services in [('pg',120,0),('PS',0,120),('EX',0,0)]:
            result=purchase_vat('1,120.00',tag)
            self.assertEqual(result['input_tax_goods'],goods)
            self.assertEqual(result['input_tax_services'],services)
            self.assertEqual(result['net_tax_base'],1120-goods-services)
        result=purchase_vat('100', 'PG')
        self.assertEqual(result['input_tax_goods'],10.71)
        self.assertEqual(result['net_tax_base'],89.29)
        for amount in ['NaN','Infinity','-1']:
            with self.assertRaises(ValueError):purchase_vat(amount,'PG')
        with self.assertRaises(ValueError):purchase_vat(1120,'INVALID')

    def setUp(self):
        self.original=module.DATA
        self.temp=tempfile.TemporaryDirectory()
        self.data=Path(self.temp.name)
        with module.db() as source, closing(sqlite3.connect(self.data/'receipts.sqlite3')) as target:
            source.backup(target)
        module.DATA=self.data
        self.client=module.app.test_client()

    def tearDown(self):
        module.DATA=self.original
        self.temp.cleanup()

    def record(self, **changes):
        body=dict(kind='receipt',collection='Cash Voucher',company='VAT Test Supplier',amount=1120,
                  receipt_month='2026-10',date='2026-10-27',tax_tag='pg',receipt_no='TEST-VAT-1')
        body.update(changes)
        response=self.client.post('/api/record',json=body)
        self.assertEqual(response.status_code,200,response.json)
        return response.json['id']

    def saved(self,rid):
        return next(r for r in self.client.get('/api/state').json['records'] if r['id']==rid)

    def test_save_reclassify_and_recalculate(self):
        rid=self.record(input_tax_goods=999,input_tax_services=999)
        r=self.saved(rid)
        self.assertEqual((r['tax_tag'],r['input_tax_goods'],r['input_tax_services'],r['net_tax_base']),('PG',120,0,1000))
        self.assertEqual(r['settlement_amount'],1120)  # Input VAT is not withholding.
        self.record(id=rid,amount=2240,tax_tag='ps')
        r=self.saved(rid)
        self.assertEqual((r['input_tax_goods'],r['input_tax_services'],r['net_tax_base']),(0,240,2000))
        self.record(id=rid,tax_tag='EX')
        r=self.saved(rid)
        self.assertEqual((r['input_tax_goods'],r['input_tax_services'],r['net_tax_base']),(0,0,1120))
        self.record(id=rid,tax_tag='')
        self.assertNotIn('vat_basis',self.saved(rid))

    def test_personal_portion_fees_and_withholding(self):
        rid=self.record(kind='payment',collection='Material Expense',method='Bank',transfer_amount=2240,
                        personal_amount=1120,fee=25)
        r=self.saved(rid)
        self.assertEqual((r['amount'],r['input_tax_goods'],r['net_tax_base']),(1120,120,1000))
        rid=self.record(receipt_no='TEST-VAT-2',withholding=10)
        self.assertEqual(self.saved(rid)['settlement_amount'],1110)

    def test_invalid_tag_rejected_and_blank_not_assumed(self):
        response=self.client.post('/api/record',json=dict(kind='receipt',collection='Cash Voucher',
            company='VAT Test',amount=1120,receipt_month='2026-10',tax_tag='ZZ'))
        self.assertEqual(response.status_code,400)
        rid=self.record(tax_tag='')
        self.assertNotIn('input_tax_goods',self.saved(rid))

    def test_tax_fields_export(self):
        import openpyxl
        self.record(kind='payment',collection='Material Expense',method='Bank')
        response=self.client.get('/api/materials/export')
        self.assertEqual(response.status_code,200)
        workbook=openpyxl.load_workbook(io.BytesIO(response.data),read_only=True)
        row=list(workbook.active.values)
        index=row[0].index('INPUT VAT - GOODS')
        self.assertEqual(row[1][index],120)
        workbook.close()

    def test_withholding_choice_changes_net_without_changing_vat(self):
        rid=self.record(withholding_status='yes',withholding=20)
        r=self.saved(rid)
        self.assertEqual((r['input_tax_goods'],r['settlement_amount']),(120,1100))
        self.record(id=rid,withholding_status='no',withholding=20)
        r=self.saved(rid)
        self.assertEqual((r['input_tax_goods'],r['withholding'],r['settlement_amount']),(120,0,1120))
        # VAT exemption does not imply an exemption from income withholding.
        self.record(id=rid,tax_tag='EX',withholding_status='yes',withholding=20)
        r=self.saved(rid)
        self.assertEqual((r['input_tax_goods'],r['withholding'],r['settlement_amount']),(0,20,1100))
        response=self.client.post('/api/record',json=dict(kind='receipt',company='Test',amount=1120,
            withholding_status='yes',withholding=0))
        self.assertEqual(response.status_code,400)

    def test_automatic_withholding_recomputes_tag_amount_and_no_choice(self):
        rid=self.record(withholding_status='yes',withholding_mode='auto',withholding=999,net_override=1)
        r=self.saved(rid)
        self.assertEqual((r['withholding'],r['withholding_rate'],r['settlement_amount']),(10,1,1110))
        self.record(id=rid,kind='receipt',withholding_status='yes',withholding_mode='auto',fee=25)
        self.assertEqual(self.saved(rid)['withholding'],10)
        self.record(id=rid,tax_tag='PS',withholding_status='yes',withholding_mode='auto',amount=2240)
        r=self.saved(rid)
        self.assertEqual((r['withholding'],r['withholding_rate'],r['settlement_amount']),(40,2,2200))
        self.record(id=rid,tax_tag='PS',withholding_status='no',withholding_mode='auto',amount=2240)
        r=self.saved(rid)
        self.assertEqual((r['withholding'],r['withholding_rate'],r['settlement_amount']),(0,0,2240))
        response=self.client.post('/api/record',json=dict(kind='receipt',collection='Cash Voucher',company='EX test',
            amount=1120,receipt_month='2026-10',tax_tag='EX',withholding_status='yes',withholding_mode='auto'))
        self.assertEqual(response.status_code,400)

    def test_screenshot_amount_rounding_for_selected_invoice_treatment(self):
        pg=automatic_withholding('25133.48','PG')
        ps=automatic_withholding('25133.48','PS')
        self.assertEqual(pg['withholding'],224.41)
        self.assertEqual(ps['withholding'],448.81)
        self.assertEqual(pg['withholding_base'],22440.61)

if __name__=='__main__':unittest.main()
