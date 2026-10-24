import unittest
from rebuild_september import prepare


class SeptemberSourceTests(unittest.TestCase):
    def test_payment_dates_filtered_receipt_collection_preserved(self):
        sources=[{'file':'Quarter.xlsx','sheets':[dict(name='Material Expense',merges=[],rows=[
            dict(row=3,values={'A':'DATE','E':'PAYEE','L':'AMOUNT'}),
            dict(row=4,values={'A':'2026-07-10','E':'Old payment','L':100}),
            dict(row=5,values={'A':'2026-09-10','E':'September payment','L':200}),
            dict(row=6,values={'E':'Undated payment','L':300}),
        ])]}, {'file':'September.xlsx','sheets':[dict(name='Non Receipt',merges=[],rows=[
            dict(row=13,values={'A':'DATE','B':'PATRICULARS','F':'AMOUNT'}),
            dict(row=14,values={'A':'2026-08-26','B':'Older collected voucher','F':500}),
        ])]}]
        rows,excluded,_,_=prepare(sources)
        import json
        self.assertEqual(len(rows),2)
        self.assertEqual(len(excluded),2)
        bodies=[json.loads(r[2]) for r in rows]
        self.assertEqual(bodies[0]['date'],'2026-09-10')
        self.assertEqual(bodies[1]['date'],'2026-08-26')
        self.assertEqual(bodies[1]['receipt_month'],'2026-09')


if __name__=='__main__':unittest.main()
