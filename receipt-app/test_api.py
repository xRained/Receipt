import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
import openpyxl
import app as module


class ReviewApiTests(unittest.TestCase):
    def setUp(self):
        self.original=module.DATA
        self.temp=tempfile.TemporaryDirectory()
        self.data=Path(self.temp.name)
        with module.db() as source, closing(sqlite3.connect(self.data/'receipts.sqlite3')) as target:
            source.backup(target)
        module.DATA=self.data
        with module.db() as c:
            c.execute("DELETE FROM workspace_settings WHERE key='workflow'")
            for table in ['presence_links','presence_dismissals','allocations','match_audit','match_blocks','supplier_aliases','documents','returns','records']:
                c.execute('DELETE FROM '+table)
            for rid,kind,amount,name,si in [('p1','payment',15120,'Payment Alias','35522'),('p2','payment',1120,'Payment Alias','35522'),('r','receipt',16240,'Supplier Legal Name','35522')]:
                body=dict(company=name,amount=amount,fee=0,receipt_no=si,settlement_amount=amount)
                c.execute('INSERT INTO records VALUES(?,?,?,?,?)',(rid,kind,json.dumps(body),'Fixture',None))
        self.client=module.app.test_client()

    def tearDown(self):
        module.DATA=self.original
        self.temp.cleanup()

    def test_confirm_alias_undo_and_export(self):
        self.assertEqual(len(self.client.get('/api/review').get_json()['suggestions']),1)
        response=self.client.post('/api/confirm-group',json={'receipt':'r','payments':['p1','p2'],'remember_alias':True})
        self.assertEqual(response.status_code,200)
        with module.db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM supplier_aliases').fetchone()[0],1)
            self.assertEqual(sum(r['remaining'] for r in module.records(c)),0)
        self.assertEqual(self.client.post('/api/auto-match',json={}).get_json()['links'],0)
        self.assertEqual(self.client.post('/api/unlink',json={'payment':'p1','receipt':'r'}).status_code,200)
        self.assertEqual(self.client.post('/api/auto-match',json={}).get_json()['links'],0)
        response=self.client.get('/api/export')
        self.assertEqual(response.status_code,200)
        workbook=openpyxl.load_workbook(io.BytesIO(response.data),read_only=True)
        self.assertTrue({'Review Queue','Supplier Master','Chart of Accounts','Payment Monthly Summary'}.issubset(workbook.sheetnames))
        workbook.close()

    def test_stale_or_oversized_group_rejected(self):
        response=self.client.post('/api/confirm-group',json={'receipt':'r','payments':['p1']})
        self.assertEqual(response.status_code,400)
        with module.db() as c:
            r=json.loads(c.execute("SELECT body FROM records WHERE id='r'").fetchone()[0]);r['settlement_amount']=16000
            c.execute("UPDATE records SET body=? WHERE id='r'",(json.dumps(r),))
        self.assertEqual(self.client.post('/api/confirm-group',json={'receipt':'r','payments':['p1','p2']}).status_code,400)
        with module.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM allocations').fetchone()[0],0)

    def test_all_fourteen_modules_and_shared_masters(self):
        definitions=self.client.get('/api/modules').get_json()['modules']
        self.assertEqual(len(definitions),14)
        for definition in definitions:
            response=self.client.get('/api/modules/'+definition['id'])
            self.assertEqual(response.status_code,200,definition['id'])
        response=self.client.post('/api/master/supplier',json={'name':'New Supplier Fixture','tin':'123-456-789','address':'Fixture Street'})
        self.assertEqual(response.status_code,200)
        for slug in ['supplier-list','suppliers']:
            self.assertTrue(any(s['name']=='New Supplier Fixture' for s in self.client.get('/api/modules/'+slug).get_json()['rows']))
        self.assertEqual(self.client.post('/api/master/account',json={'code':'CS-9999','title':'Fixture Expense'}).status_code,200)
        self.assertEqual(self.client.post('/api/master/account',json={'code':'CS-9999','title':'Duplicate'}).status_code,409)

    def test_photo_intake_duplicate_and_attach(self):
        from PIL import Image
        image=io.BytesIO();Image.new('RGB',(3,3),'red').save(image,format='PNG');image=image.getvalue()
        (module.DATA/'uploads').mkdir(exist_ok=True)
        first=self.client.post('/api/upload',data={'file':(io.BytesIO(image),'proof.png')},content_type='multipart/form-data').get_json()
        again=self.client.post('/api/upload',data={'file':(io.BytesIO(image),'same.png')},content_type='multipart/form-data').get_json()
        self.assertTrue(again['duplicate_image']);self.assertEqual(first['image'],again['image'])
        draft=self.client.post('/api/intake/parse',json={'mode':'payment','text':'GCash\nSent to:\nPhoto Supplier\nAmount\nPHP 50.00\nReference No. ABC123456\nSep 10, 2026','month':'2026-09'}).get_json()['draft']
        self.assertEqual(draft['amount'],'50.00');self.assertEqual(draft['reference'],'ABC123456')
        draft['image']=first['image'];draft['company']='Photo Supplier'
        saved=self.client.post('/api/record',json=draft);self.assertEqual(saved.status_code,200,saved.data)
        rid=saved.get_json()['id']
        self.assertEqual(len(self.client.get('/api/documents/'+rid).get_json()['documents']),1)
        self.assertEqual(self.client.post('/api/record',json=draft).status_code,409)
        self.assertEqual(self.client.post('/api/intake/attach',json={'record_id':'p1','image':first['image']}).status_code,409)

    def test_advance_return_and_summary_no_double_count(self):
        b=dict(kind='payment',company='Advance Fixture',date='2026-09-10',amount=1000,fee=10,treatment='advance',collection='COS_Allowance')
        response=self.client.post('/api/record',json=b);self.assertEqual(response.status_code,200)
        rid=response.get_json()['id']
        response=self.client.post('/api/returns',json={'payment':rid,'amount':400,'date':'2026-09-12','reason':'Unused advance returned'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.client.post('/api/returns',json={'payment':rid,'amount':601,'date':'2026-09-12','reason':'Too much'}).status_code,400)
        rows=self.client.get('/api/modules/allowances').get_json()['rows']
        self.assertEqual(next(r for r in rows if r['id']==rid)['remaining'],600)
        self.client.post('/api/controls',json={'date':'2026-09-10','kind':'cash','amount':99999,'note':'Aggregate control'})
        summaries=self.client.get('/api/modules/daily').get_json()['rows']
        summary=next(r for r in summaries if r['period']=='2026-09-10')
        self.assertEqual(summary['total'],1010)

    def test_scoped_workspace_rejects_other_months(self):
        with module.db() as c:c.execute("INSERT OR REPLACE INTO workspace_settings VALUES('scope_month','2026-09')")
        self.assertEqual(self.client.post('/api/record',json={'kind':'payment','company':'Outside','amount':100,'date':'2026-08-31'}).status_code,400)
        self.assertEqual(self.client.post('/api/controls',json={'kind':'cash','date':'2026-08-31','amount':100}).status_code,400)
        self.assertEqual(self.client.get('/api/export/complete?month=2026-08').status_code,400)
        self.assertEqual(self.client.get('/api/state').get_json()['scope_month'],'2026-09')

    def test_material_presence_decision_does_not_allocate_money(self):
        with module.db() as c:
            for rid in ['p1','r']:
                body=json.loads(c.execute('SELECT body FROM records WHERE id=?',(rid,)).fetchone()[0])
                body.update(collection='Material Expense' if rid=='p1' else 'September Cash Voucher',method='Online Payment' if rid=='p1' else 'Cash',code='CS-0001',account='Materials',date='2026-09-01' if rid=='p1' else '2026-07-01')
                c.execute('UPDATE records SET body=? WHERE id=?',(json.dumps(body),rid))
        response=self.client.get('/api/materials-presence');self.assertEqual(response.status_code,200)
        self.assertEqual(len(response.get_json()['rows']),1)
        response=self.client.post('/api/materials-presence/decision',json={'payment':'p1','receipt':'r','action':'confirm'})
        self.assertEqual(response.status_code,200)
        with module.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM allocations').fetchone()[0],0)
        self.assertEqual(self.client.get('/api/materials-presence').get_json()['rows'][0]['status'],'found')
        self.assertEqual(self.client.post('/api/materials-presence/decision',json={'payment':'p1','receipt':'r','action':'dismiss'}).status_code,200)
        self.assertEqual(self.client.get('/api/materials-presence').get_json()['rows'][0]['status'],'not_found')
        response=self.client.get('/api/materials-presence/export');self.assertEqual(response.status_code,200)
        w=openpyxl.load_workbook(io.BytesIO(response.data),read_only=True)
        self.assertIn('No candidate found',w.sheetnames);w.close()


if __name__=='__main__':unittest.main()
