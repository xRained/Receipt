import unittest
from workbooks import normalized_receipts,account_entries


class WorkbookTests(unittest.TestCase):
    def test_merged_voucher_preserves_lines(self):
        w={'file':'September.xlsx','sheets':[{'name':'September Check Voucher','merges':['D19:L20','Y19:Y20'], 'rows':[
            {'row':13,'values':{'D':'PARTICULARS','M':'S.I#','T':'AMOUNT','X':'EXPANDED WITHHOLDING TAX','Y':'CASH IN BANK'}},
            {'row':19,'values':{'D':'Security supplier','M':551,'T':3300,'X':60,'Y':32000}},
            {'row':20,'values':{'M':7985,'T':28700,'X':0}},
        ]}]}
        r=normalized_receipts(w)[0]
        self.assertEqual(r['receipt_numbers'],['551','7985'])
        self.assertEqual(r['amount'],32000)
        self.assertEqual(r['settlement_amount'],32000)
        self.assertEqual(r['withholding'],60)

    def test_all_account_prefixes(self):
        w={'sheets':[{'name':'COA','rows':[{'values':{'B':'L-0001','C':'SSS Payable'}},{'values':{'B':'PEOE-0022','C':'Bank Charges'}}]}]}
        self.assertEqual(list(account_entries(w)),[('L-0001','SSS Payable'),('PEOE-0022','Bank Charges')])




    def test_shared_date_keeps_each_receipt_separate(self):
        from materials import workbook_rows
        w={'file':'Example.xlsx','sheets':[{'name':'Cash Voucher','merges':[], 'rows':[
            {'row':13,'values':{'A':'DATE','D':'PARTICULARS','M':'S.I#','S':'AMOUNT','W':'EXPANDED WITHHOLDING TAX','X':'AMOUNT PAID'}},
            {'row':14,'values':{'A':46266,'D':'Supplier A','M':101,'S':100}},
            {'row':15,'values':{'D':'Supplier B','M':102,'S':200}},
            {'row':16,'values':{'A':46267,'D':'Supplier C','M':103,'S':300}},
        ]}]}
        rows=workbook_rows(w,'vouchers','2026-09')
        self.assertEqual(len(rows),3)
        self.assertEqual(rows[0]['body']['date'],rows[1]['body']['date'])
        self.assertNotEqual(rows[1]['body']['date'],rows[2]['body']['date'])
        self.assertTrue(rows[1]['body']['date_inherited'])
        self.assertEqual([r['body']['receipt_no'] for r in rows],['101','102','103'])
