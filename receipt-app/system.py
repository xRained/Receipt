"""End-to-end local document intake, month closing, controls and backups."""
import csv
import hashlib
import io
import json
import shutil
import sqlite3
import uuid
import zipfile
from datetime import date, datetime
from pathlib import Path
from flask import jsonify, request, send_file
from intake import extract, duplicates
from matching import norm
from reports import build_workbook, money
from openpyxl.utils.datetime import from_excel


def install(app, get_data, db, records, cents, auto_match):
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, image TEXT NOT NULL, sha256 TEXT UNIQUE, original_name TEXT, text TEXT, record_id TEXT REFERENCES records(id), created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS templates(kind TEXT PRIMARY KEY, label TEXT, filename TEXT, sha256 TEXT, snapshot TEXT);
        CREATE TABLE IF NOT EXISTS controls(id TEXT PRIMARY KEY, kind TEXT, day TEXT, company TEXT, amount INTEGER, source TEXT, source_row INTEGER, note TEXT);
        CREATE TABLE IF NOT EXISTS returns(id TEXT PRIMARY KEY, payment TEXT REFERENCES records(id), cents INTEGER CHECK(cents>0), day TEXT, reason TEXT);
        ''')

    def register_source(path,kind,snapshot):
        path=Path(path);data=get_data();folder=data/'templates';folder.mkdir(exist_ok=True)
        content=path.read_bytes();digest=hashlib.sha256(content).hexdigest();filename=kind+'-'+digest[:12]+'.xlsx'
        destination=folder/filename
        if not destination.exists():shutil.copy2(path,destination)
        with db() as c:
            scoped=c.execute("SELECT value FROM workspace_settings WHERE key='scope_month'").fetchone()
            scope=scoped['value'] if scoped else None
            c.execute('INSERT OR REPLACE INTO templates VALUES(?,?,?,?,?)',(kind,path.name,filename,digest,json.dumps(snapshot)))
            if kind=='quarterly':
                for sheet in snapshot['sheets']:
                    if sheet['name']!='GCashCheck':continue
                    for row in sheet['rows']:
                        n=row['row'];values=row['values']
                        if n<=4:continue
                        for method,dc,ac,nc in [('cash','A','B',None),('gcash','D','E',None),('cheque','G','I','H')]:
                            day=values.get(dc);amount=values.get(ac)
                            if not isinstance(day,(int,float)) or not isinstance(amount,(int,float)) or amount<=0:continue
                            if scope and not from_excel(day).date().isoformat().startswith(scope):continue
                            key=f'{path.name}|{n}|{method}'
                            c.execute('INSERT OR IGNORE INTO controls VALUES(?,?,?,?,?,?,?,?)',(key,method,from_excel(day).date().isoformat(),values.get(nc,'') if nc else '',cents(amount),path.name+' / GCashCheck',n,'Imported aggregate control; not another expense'))
            # Retain line-level tax tags and amounts for the merged source groups.
            for sheet in snapshot['sheets']:
                if 'Voucher' not in sheet['name']:continue
                source=path.name+' / '+sheet['name'];raw={r['row']:r['values'] for r in sheet['rows']}
                check='Check' in sheet['name']
                for row in c.execute('SELECT * FROM records WHERE source=?',(source,)).fetchall():
                    body=json.loads(row['body']);lines=[raw.get(n,{}) for n in body.get('source_rows',[row['source_row']])]
                    body.setdefault('source_lines',lines)
                    body.setdefault('tax_tag',raw.get(row['source_row'],{}).get('S' if check else 'R',''))
                    body.setdefault('net_tax_base',sum(float(v.get('W' if check else 'V',0) or 0) for v in lines))
                    c.execute('UPDATE records SET body=? WHERE id=?',(json.dumps(body),row['id']))
        return digest

    app.register_source=register_source

    @app.post('/api/intake/parse')
    def parse():
        b=request.get_json() or {}
        with db() as c:
            rs=records(c);suppliers=[dict(r) for r in c.execute('SELECT * FROM suppliers')]
            try:draft,warnings=extract(b.get('text',''),b.get('mode','auto'),suppliers,rs)
            except ValueError as e:return jsonify(error=str(e)),400
            if b.get('image'):
                c.execute('UPDATE documents SET text=? WHERE image=?',(b.get('text',''),b['image']))
            draft['receipt_month']=b.get('month') or date.today().strftime('%Y-%m')
            return jsonify(draft=draft,warnings=warnings,duplicates=duplicates(draft,rs))

    @app.post('/api/intake/duplicates')
    def check_duplicates():
        with db() as c:return jsonify(duplicates=duplicates(request.get_json() or {},records(c)))

    @app.post('/api/intake/attach')
    def attach():
        b=request.get_json() or {}
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT * FROM records WHERE id=?',(b.get('record_id'),)).fetchone()
            document=c.execute('SELECT * FROM documents WHERE image=?',(b.get('image'),)).fetchone()
            if not row or not document:return jsonify(error='Choose an existing entry and an uploaded image'),400
            if document['record_id'] and document['record_id']!=row['id']:return jsonify(error='This image is already attached to another entry'),409
            c.execute('UPDATE documents SET record_id=?,text=COALESCE(?,text) WHERE id=?',(row['id'],b.get('text'),document['id']))
        return jsonify(ok=True,id=row['id'])

    @app.get('/api/documents/<rid>')
    def documents(rid):
        with db() as c:return jsonify(documents=[dict(r) for r in c.execute('SELECT id,image,original_name,text FROM documents WHERE record_id=?',(rid,))])

    def closing(month):
        with db() as c:
            rs=records(c)
            controls=[dict(r) for r in c.execute('SELECT * FROM controls WHERE day LIKE ? ORDER BY day',(month+'%',))]
            templates=[dict(r) for r in c.execute('SELECT kind,label,sha256 FROM templates')]
        payments=[r for r in rs if r['kind']=='payment' and r.get('date','').startswith(month)]
        receipts=[r for r in rs if r['kind']=='receipt' and r.get('receipt_month')==month]
        compared=[]
        for method in ['cash','gcash','cheque']:
            ct=sum(r['amount'] for r in controls if r['kind']==method)/100
            details=money(sum(r['amount']+float(r.get('fee',0) or 0) for r in payments if r.get('method','').lower() in ({'cheque','check'} if method=='cheque' else {method})))
            compared.append(dict(method=method,control=ct if any(r['kind']==method for r in controls) else None,detail=details,difference=money(ct-details) if any(r['kind']==method for r in controls) else None))
        open_payments=[r for r in payments if r['remaining']>.005 and r.get('treatment') not in ['personal','no_receipt']]
        issues=[]
        for r in receipts:
            if r.get('personal'):issues.append(dict(id=r['id'],company=r['company'],issue='Personal or mixed group: confirm classification',amount=r['amount']))
            if r.get('collection')!='Non Receipt' and not r.get('receipt_no'):issues.append(dict(id=r['id'],company=r['company'],issue='Receipt number missing in source',amount=r['amount']))
            if abs(money(r['amount']-float(r.get('withholding',0))-r['settlement_amount']))>.01:
                issues.append(dict(id=r['id'],company=r['company'],issue='Recorded gross minus withholding differs from recorded net payable',amount=money(r['amount']-float(r.get('withholding',0))-r['settlement_amount'])))
        return dict(month=month,payments=len(payments),receipt_groups=len(receipts),open_payments=len(open_payments),
                    payment_principal=money(sum(r['amount'] for r in payments)),fees=money(sum(float(r.get('fee',0) or 0) for r in payments)),
                    linked=money(sum(r['allocated'] for r in payments)),open_balance=money(sum(r['remaining'] for r in open_payments)),
                    controls=compared,issues=issues,templates=templates,
                    note='September receipts can match payments from earlier months. Missing aggregate controls are unknown, not zero. Unlinked cash receipts may already represent cash expenses; no duplicate payment is created.')

    @app.get('/api/closing')
    def close_status():return jsonify(closing(request.args.get('month','2026-09')))

    @app.post('/api/controls')
    def control():
        b=request.get_json() or {}
        try:
            value=cents(b.get('amount'));day=date.fromisoformat(b['date']).isoformat()
            if b.get('kind') not in ['cash','gcash','cheque']:raise ValueError('Choose cash, GCash or cheque')
        except (ValueError,KeyError) as e:return jsonify(error=str(e)),400
        with db() as c:
            scope=c.execute("SELECT value FROM workspace_settings WHERE key='scope_month' AND NOT EXISTS (SELECT 1 FROM workspace_settings WHERE key='workflow' AND value='materials_intake_receipt_presence')").fetchone()
            if scope and not day.startswith(scope['value']):return jsonify(error='Control date must be in the active workspace month'),400
            if b.get('id'):
                old=c.execute('SELECT * FROM controls WHERE id=?',(b['id'],)).fetchone()
                if not old:return jsonify(error='Control not found'),404
                c.execute('UPDATE controls SET kind=?,day=?,company=?,amount=?,note=? WHERE id=?',(b['kind'],day,b.get('company',''),value,b.get('note',''),b['id']))
            else:c.execute('INSERT INTO controls VALUES(?,?,?,?,?,?,?,?)',(uuid.uuid4().hex,b['kind'],day,b.get('company',''),value,'User control',None,b.get('note','')))
        return jsonify(ok=True)

    @app.post('/api/returns')
    def advance_return():
        b=request.get_json() or {}
        try:
            value=cents(b.get('amount'))
            if value<=0 or not str(b.get('reason','')).strip():raise ValueError('Enter a positive returned amount and explanation')
            day=date.fromisoformat(b['date']).isoformat()
            with db() as c:
                c.execute('BEGIN IMMEDIATE');r=next((r for r in records(c) if r['id']==b.get('payment')),None)
                scope=c.execute("SELECT value FROM workspace_settings WHERE key='scope_month' AND NOT EXISTS (SELECT 1 FROM workspace_settings WHERE key='workflow' AND value='materials_intake_receipt_presence')").fetchone()
                if scope and not day.startswith(scope['value']):raise ValueError('Return date must be in the active workspace month')
                if not r or r['kind']!='payment' or r.get('treatment')!='advance':raise ValueError('Select an advance payment first')
                if value>cents(r['remaining']):raise ValueError('Return exceeds the remaining advance')
                c.execute('INSERT INTO returns VALUES(?,?,?,?,?)',(uuid.uuid4().hex,r['id'],value,day,b['reason']))
            return jsonify(ok=True)
        except (KeyError,ValueError) as e:return jsonify(error=str(e)),400

    @app.get('/api/backup')
    def backup():
        data=get_data();buf=io.BytesIO()
        # SQLite's backup API gives a consistent snapshot while the app is open.
        memory=sqlite3.connect(':memory:')
        with db() as c:c.backup(memory)
        database=memory.serialize();memory.close()
        with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('receipts.sqlite3',database)
            for folder in ['uploads','templates']:
                for p in (data/folder).glob('*'):
                    if p.is_file():z.write(p,folder+'/'+p.name)
        buf.seek(0)
        return send_file(buf,download_name='tally-backup-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.zip',as_attachment=True)

    @app.get('/api/export/complete')
    def complete_export():
        month=request.args.get('month','2026-09')
        try:date.fromisoformat(month+'-01')
        except ValueError:return jsonify(error='Use a valid YYYY-MM month'),400
        with db() as c:
            templates=[dict(r) for r in c.execute('SELECT * FROM templates')]
            scoped=c.execute("SELECT value FROM workspace_settings WHERE key='scope_month'").fetchone()
            scope=scoped['value'] if scoped else None
            if c.execute("SELECT 1 FROM workspace_settings WHERE key='workflow' AND value='materials_intake_receipt_presence'").fetchone():scope=None
            if scope and month!=scope:return jsonify(error='Export the active workspace month: '+scope),400
            rs=records(c);suppliers=[dict(r) for r in c.execute('SELECT * FROM suppliers ORDER BY name')];accounts=[dict(r) for r in c.execute('SELECT * FROM accounts ORDER BY code')]
            controls=[dict(r) for r in c.execute('SELECT * FROM controls ORDER BY day')]
            for r in controls:r.update(date=r['day'],amount=r['amount']/100)
        if {r['kind'] for r in templates}!={'quarterly','monthly'}:return jsonify(error='Import both the quarterly and monthly workbook templates first'),400
        output=io.BytesIO();manifests=[]
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
            for t in templates:
                content,manifest=build_workbook(get_data()/'templates'/t['filename'],json.loads(t['snapshot']),rs,suppliers,accounts,controls,month,t['kind']=='quarterly',scope_month=scope)
                z.writestr(('Quarterly Expenses' if t['kind']=='quarterly' else 'Monthly Vouchers')+' '+month+'.xlsx',content)
                manifests.append(manifest)
            # Include the detailed reconciliation workbook from the same request context.
            with app.test_request_context('/api/export'):
                response=app.view_functions['export']();response.direct_passthrough=False
                z.writestr('Reconciliation '+month+'.xlsx',response.get_data());response.close()
            z.writestr('Month-end checks.json',json.dumps(closing(month),indent=2))
            z.writestr('Export manifest.json',json.dumps(manifests,indent=2))
            z.writestr('READ ME.txt','All original worksheet names and column positions are retained. Detail and summary areas are regenerated from the app records. Grouped receipts are displayed together with every S.I#. Original line-level evidence remains in the application and original templates.\nPayment and receipt totals are separate; do not add them together. Controls, personal/mixed groups, source tax discrepancies and open balances require review. Historical external values remain snapshots. This export is a reviewable month-end package, not evidence that every discrepancy is resolved.\n')
        output.seek(0)
        return send_file(output,download_name='Tally complete '+month+'.zip',as_attachment=True)

    return register_source
