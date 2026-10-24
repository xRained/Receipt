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


if __name__=='__main__':unittest.main()
