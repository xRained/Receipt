import unittest
from matching import plan_matches, review_matches, identity


def row(id, kind, amount, **kw):
    return dict(id=id, kind=kind, amount=amount, remaining=amount, company='Supplier', **kw)


class MatchingTests(unittest.TestCase):
    def test_partial_group_and_numeric_receipt(self):
        rows=[row('p1','payment',10000,receipt_no='0012'),row('p2','payment',10000,receipt_no='12.0'),row('r','receipt',20000,receipt_no='12')]
        self.assertEqual(sum(a['cents'] for a in plan_matches(rows)),2000000)

    def test_repeated_amount_is_ambiguous(self):
        self.assertEqual(plan_matches([row('p','payment',100),row('r1','receipt',100),row('r2','receipt',100)]),[])

    def test_conflicting_tin_or_receipt(self):
        for key, a, b in [('tin','123456789','987654321'),('receipt_no','123','456')]:
            self.assertEqual(plan_matches([row('p','payment',100,**{key:a}),row('r','receipt',100,**{key:b})]),[])

    def test_tin_branches_cross_month_and_different_names(self):
        p=row('p','payment',100,tin='123-456-789-000',date='2026-07-01')
        r=row('r','receipt',100,tin='123-456-789',date='2026-09-01');r['company']='Other trade name'
        self.assertEqual(len(plan_matches([p,r])),1)

    def test_non_receipt_and_undo_block(self):
        p=row('p','payment',100);r=row('r','receipt',100,collection='Non Receipt')
        self.assertEqual(plan_matches([p,r]),[])
        r['collection']='Cash Voucher'
        self.assertEqual(plan_matches([p,r],[('p','r')]),[])

    def test_no_fuzzy_amount_or_guessed_partial(self):
        self.assertEqual(plan_matches([row('p','payment',99.99),row('r','receipt',100)]),[])
        self.assertEqual(plan_matches([row('p1','payment',50),row('p2','payment',50),row('r','receipt',100)]),[])

    def test_receipt_group_alias_review(self):
        p1=row('p1','payment',15120,receipt_no='35522')
        p2=row('p2','payment',1120,receipt_no='35522')
        r=row('r','receipt',16240,receipt_no='35522');r['company']='Different legal name'
        self.assertEqual(plan_matches([p1,p2,r]),[])
        s=review_matches([p1,p2,r])
        self.assertEqual(len(s),1)
        self.assertEqual(s[0]['difference'],0)
        self.assertEqual(set(s[0]['payments']),{'p1','p2'})
        self.assertEqual(len(plan_matches([p1,p2,r],aliases={(identity(p1),identity(r))})),2)

    def test_merged_receipt_numbers_and_personal(self):
        p=row('p','payment',32000,receipt_no='7985')
        r=row('r','receipt',32000,receipt_no='551, 7985',receipt_numbers=['551','7985'])
        self.assertEqual(len(plan_matches([p,r])),1)
        r['personal']=True
        self.assertEqual(plan_matches([p,r]),[])
        self.assertEqual(review_matches([p,r]),[])

    def test_small_difference_remains_review_only(self):
        p=row('p','payment',7591,receipt_no='132516')
        r=row('r','receipt',7591.61,receipt_no='132516')
        self.assertEqual(plan_matches([p,r]),[])
        self.assertEqual(review_matches([p,r])[0]['difference'],.61)

    def test_one_payment_multiple_receipts(self):
        p=row('p','payment',300,receipt_no='A12; B13')
        a=row('a','receipt',100,receipt_no='A12');b=row('b','receipt',200,receipt_no='B13')
        matches=plan_matches([p,a,b])
        self.assertEqual(len(matches),2)
        self.assertEqual(sum(r['cents'] for r in matches),30000)


if __name__=='__main__':unittest.main()
