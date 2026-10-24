import unittest
from presence import compare,online_material


def payment(id='p',si='123',amount=100):
    return dict(id=id,kind='payment',collection='Material Expense',method='Online Payment',company='Supplier',tin='123-456-789',receipt_no=si,amount=amount)


def voucher(id='r',si='123',amount=101,code='CS-0001',date='2026-07-10'):
    return dict(id=id,kind='receipt',collection='September Cash Voucher',company='Supplier',tin='123-456-789',receipt_no=si,amount=amount,settlement_amount=amount,code=code,account='Materials' if code=='CS-0001' else 'Office Supplies',date=date)


class PresenceTests(unittest.TestCase):
    def test_si_present_despite_amount_and_old_date(self):
        rows,selected=compare([payment()],[voucher()])
        self.assertEqual(rows[0]['status'],'found');self.assertEqual(len(selected),1)
        self.assertEqual(rows[0]['candidates'][0]['amount_difference'],1)

    def test_partial_payments_each_find_existing_receipt(self):
        rows,_=compare([payment('p1',amount=10000),payment('p2',amount=10000)],[voucher(amount=20000)])
        self.assertTrue(all(r['status']=='found' for r in rows))

    def test_other_account_distinguished_from_missing(self):
        rows,selected=compare([payment()],[voucher(code='OE-0011')])
        self.assertEqual(rows[0]['status'],'other_account');self.assertEqual(selected,[])
        rows,_=compare([payment()],[voucher(code='OE-0011')],account='')
        self.assertEqual(rows[0]['status'],'found')

    def test_candidate_is_not_automatically_confirmed(self):
        p=payment(si='');r=voucher(amount=100)
        rows,_=compare([p],[r]);self.assertEqual(rows[0]['status'],'review')
        rows,_=compare([p],[r],confirmed=[('p','r')]);self.assertEqual(rows[0]['status'],'found')
        rows,_=compare([p],[r],dismissed=[('p','r')]);self.assertEqual(rows[0]['status'],'not_found')

    def test_gcashes_cash_cheques_and_other_sheets_excluded(self):
        for method in ['GCash','Cash','Cheque','Check']:
            p=payment();p['method']=method;self.assertFalse(online_material(p))
        p=payment();p['collection']='Cost of Sales Expense';self.assertFalse(online_material(p))


if __name__=='__main__':unittest.main()
