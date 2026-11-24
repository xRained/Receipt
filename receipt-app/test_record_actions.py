import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
import app as module


class RecordActionTests(unittest.TestCase):
    def setUp(self):
        self.original=module.DATA
        self.temp=tempfile.TemporaryDirectory()
        self.data=Path(self.temp.name)
        with module.db() as source,closing(sqlite3.connect(self.data/'receipts.sqlite3')) as target:source.backup(target)
        module.DATA=self.data
        self.client=module.app.test_client()
        with module.db() as c:
            for rid,kind in [('delete-payment','payment'),('keep-receipt','receipt')]:
                body=dict(company='<Example Corp>',amount=1120,settlement_amount=1120,payee_type='corporation',proprietor='',business_name='Example Trading')
                c.execute('INSERT INTO records VALUES(?,?,?,?,?)',(rid,kind,json.dumps(body),'Test',None))
            c.execute('INSERT INTO allocations VALUES(?,?,?)',('delete-payment','keep-receipt',100))
            c.execute('INSERT INTO documents(id,image,record_id) VALUES(?,?,?)',('test-doc','test.png','delete-payment'))

    def tearDown(self):
        module.DATA=self.original
        self.temp.cleanup()

    def test_delete_backs_up_and_preserves_counterpart_masters_and_evidence(self):
        with module.db() as c:masters=c.execute('SELECT COUNT(*) FROM suppliers').fetchone()[0]
        response=self.client.post('/api/records/delete-payment/delete')
        self.assertEqual(response.status_code,200)
        with closing(sqlite3.connect(self.data/'deleted-backups'/response.json['backup'])) as backup:
            self.assertEqual(backup.execute("SELECT COUNT(*) FROM records WHERE id='delete-payment'").fetchone()[0],1)
        with module.db() as c:
            self.assertIsNone(c.execute("SELECT * FROM records WHERE id='delete-payment'").fetchone())
            self.assertIsNotNone(c.execute("SELECT * FROM records WHERE id='keep-receipt'").fetchone())
            self.assertIsNone(c.execute("SELECT record_id FROM documents WHERE id='test-doc'").fetchone()[0])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM suppliers').fetchone()[0],masters)
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
        self.assertEqual(self.client.post('/api/records/delete-payment/delete').status_code,404)

    def test_print_escapes_content_and_separates_payee_fields(self):
        response=self.client.get('/records/delete-payment/print')
        self.assertEqual(response.status_code,200)
        html=response.data.decode()
        for value in ['&lt;Example Corp&gt;','Payee type','corporation','Company / trading name','Proprietor / owner','1,120.00','window.print()']:
            self.assertIn(value,html)
        self.assertEqual(self.client.get('/records/missing/print').status_code,404)

    def test_payee_fields_persist_separately(self):
        response=self.client.post('/api/record',json=dict(kind='receipt',company='Example Store',amount=1120,
            collection='Cash Voucher',receipt_month='2026-09',payee_type='proprietor',proprietor='Example Owner',business_name='Example Store'))
        self.assertEqual(response.status_code,200,response.json)
        with module.db() as c:
            body=json.loads(c.execute('SELECT body FROM records WHERE id=?',(response.json['id'],)).fetchone()[0])
        self.assertEqual(body['payee_type'],'proprietor')
        self.assertEqual(body['proprietor'],'Example Owner')
