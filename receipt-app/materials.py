"""Material Expense entry, shared reference data and monthly voucher intake."""
import io
import json
import re
import uuid
import zipfile
from datetime import date
from pathlib import Path
import openpyxl
from flask import jsonify,request,send_file
from audit_workbooks import audit
from workbooks import normalized_receipts,account_entries
from intake import extract,duplicates
from matching import norm,tin
from matching import receipt_numbers
from openpyxl.utils.datetime import from_excel

PAYMENT_MODES=['Online Payment','Bank','GCash','Cheque','Cash']


def material_payment(row):
    return row['kind']=='payment' and row.get('collection')=='Material Expense'


def cash_voucher(row):
    return row['kind']=='receipt' and 'cash voucher' in row.get('collection','').lower()


def month_value(value):
    value=str(value or '')
    try:date.fromisoformat(value+'-01')
    except ValueError:raise ValueError('Choose a collection month in YYYY-MM format')
    return value


def workbook_rows(snapshot,kind,month):
    """Normalize only the requested source sheet, keeping original dates."""
    output=[]
    grouped={(r['source'],r['source_row']):r for r in normalized_receipts(snapshot)}
    for s in snapshot['sheets']:
        if kind=='payments' and s['name']!='Material Expense':continue
        if kind=='vouchers' and 'cash voucher' not in s['name'].lower():continue
        header=next((r for r in s['rows'] if 'DATE' in r['values'].values() and ('PAYEE' in r['values'].values() or 'PARTICULARS' in r['values'].values())),None)
        if not header:continue
        cols={v:k for k,v in header['values'].items() if isinstance(v,str)}
        previous_day='';date_source_row=None
        for row in s['rows']:
            if row['row']<=header['row']:continue
            v=row['values']
            def get(*names):return next((v[cols[n]] for n in names if n in cols and cols[n] in v),'')
            amount=get('AMOUNT');company=str(get('PAYEE','PARTICULARS')).strip()
            if not company or not isinstance(amount,(int,float)) or amount<=0:continue
            day=get('DATE')
            inherited=not bool(day) and kind=='vouchers' and bool(previous_day)
            if day:previous_day=day;date_source_row=row['row']
            elif kind=='vouchers':day=previous_day
            day=from_excel(day).date().isoformat() if isinstance(day,(int,float)) else str(day or '')
            if kind=='payments' and month and not day.startswith(month):continue
            body=dict(date=day,company=company,amount=amount,fee=get('FEES') or 0,method=get('MODE OF PAYMENT') or 'Cash',
                      receipt_no=str(get('RECEIPT NO.','S.I#')),reference=str(get('REF. NO','REFERENCE NO.')),
                      tin=str(get('TIN')),address=str(get('ADDRESS')),project=str(get('PROJECT')),
                      code=str(get('ACCOUNT CODE','CODE')),account=str(get('ACCOUNT TITLE','ACCOUNT')),
                      remarks=str(get('DESCRIPTION')),collection=s['name'],treatment='business',date_inherited=inherited,date_source_row=date_source_row,
                      receipt_month=month if kind=='vouchers' else '',settlement_amount=amount)
            source=snapshot['file']+' / '+s['name']
            if kind=='vouchers':
                extra=grouped.get((source,row['row']))
                if extra:body.update({k:x for k,x in extra.items() if k not in ['source','source_row']})
            output.append(dict(kind='payment' if kind=='payments' else 'receipt',body=body,source=source,source_row=row['row']))
    return output


def restore_shared_dates(data,db):
    """Recover blank transaction dates from retained workbook audit snapshots."""
    snapshots=[]
    for name in ['workbook-audit.json','september-additional-audit.json']:
        path=data/name
        if not path.exists():continue
        try:
            value=json.loads(path.read_text(encoding='utf-8'))
            snapshots.extend(value if isinstance(value,list) else [value])
        except (ValueError,OSError):continue
    lookup={}
    for snapshot in snapshots:
        for row in workbook_rows(snapshot,'vouchers',''):
            if row['body'].get('date_inherited'):lookup[(row['source'],row['source_row'])]=row['body']
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        updates=[]
        for row in c.execute("SELECT * FROM records WHERE kind='receipt'"):
            body=json.loads(row['body'])
            source=re.sub(r' \[\d{4}-\d{2}\]$','',row['source'] or '')
            original=lookup.get((source,row['source_row']))
            if not body.get('date') and original and original.get('date'):
                body.update({k:original[k] for k in ['date','date_inherited','date_source_row']})
                updates.append((json.dumps(body),row['id']))
        if updates:
            import sqlite3
            from datetime import datetime
            backup=data/('before-shared-date-repair-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3')
            with sqlite3.connect(data/'receipts.sqlite3') as source,sqlite3.connect(backup) as target:source.backup(target)
            c.executemany('UPDATE records SET body=? WHERE id=?',updates)
    return len(updates)


def install(app,get_data,db,records,cents):
    def refresh_matches():
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute("DELETE FROM presence_links WHERE match_kind='automatic'")
            allrows=records(c);ps=[r for r in allrows if material_payment(r)]
            rs=[r for r in allrows if cash_voucher(r) and receipt_numbers(r)]
            blocked={tuple(r) for r in c.execute('SELECT payment,receipt FROM presence_dismissals')}
            manual={tuple(r) for r in c.execute('SELECT payment,receipt FROM presence_links')}
            candidates=[];exact_pairs=[]
            for p in ps:
                for r in rs:
                    pair=(p['id'],r['id'])
                    if pair in blocked or any(pid==p['id'] or rid==r['id'] for pid,rid in manual):continue
                    pt,rt=tin(p.get('tin')),tin(r.get('tin'))
                    if pt and rt and pt!=rt:continue
                    same=bool((pt and pt==rt) or (norm(p['company']) and norm(p['company'])==norm(r['company'])))
                    if receipt_numbers(p):
                        if same and receipt_numbers(p)&receipt_numbers(r):exact_pairs.append(pair)
                        continue
                    if same and cents(p['amount']) in {cents(r['amount']),cents(r.get('settlement_amount',r['amount']))}:candidates.append(pair)
            from collections import Counter
            pc=Counter(p for p,r in candidates);rc=Counter(r for p,r in candidates)
            ec=Counter(p for p,r in exact_pairs)
            accepted=[(p,r) for p,r in exact_pairs if ec[p]==1]+[(p,r) for p,r in candidates if pc[p]==1 and rc[r]==1]
            c.executemany("INSERT INTO presence_links(payment,receipt,match_kind) VALUES(?,?,'automatic')",accepted)
        return len(accepted)
    app.refresh_material_presence=refresh_matches

    def save_snapshot(snapshot,kind,month):
        imported=skipped=0;conflicts=[];suppliers=0
        incoming=workbook_rows(snapshot,kind,month) if kind!='references' else []
        if kind!='references' and not incoming:raise ValueError('No supported '+('Material Expense' if kind=='payments' else 'Cash Voucher')+' rows found for this import')
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            for s in snapshot['sheets']:
                if s['name'] not in ['Suppliers List','Suppliers']:continue
                for row in s['rows']:
                    v=row['values'];name=v.get('A')
                    if row['row']<=1 or not isinstance(name,str) or not name.strip():continue
                    c.execute('INSERT INTO suppliers VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET tin=excluded.tin,address=excluded.address',(name.strip(),str(v.get('B') or ''),str(v.get('C') or '')));suppliers+=1
            ac=list(account_entries(snapshot))
            for code,title in ac:c.execute('INSERT INTO accounts VALUES(?,?) ON CONFLICT(code) DO UPDATE SET title=excluded.title',(code,title))
            if kind=='references' and not suppliers and not ac:raise ValueError('Workbook must contain Suppliers List / Suppliers or Copy of Accounts / COA')
            existing=records(c)
            for item in incoming:
                b=item['body'];b['amount']=cents(b['amount'])/100;b['settlement_amount']=cents(b['settlement_amount'])/100;b['fee']=cents(b.get('fee'))/100
                original_source=item['source']
                if kind=='vouchers':item['source']=original_source+' ['+month+']'
                old=c.execute('SELECT * FROM records WHERE source=? AND source_row=?',(item['source'],item['source_row'])).fetchone()
                if not old and kind=='vouchers':
                    legacy=c.execute('SELECT * FROM records WHERE source=? AND source_row=?',(original_source,item['source_row'])).fetchone()
                    if legacy and json.loads(legacy['body']).get('receipt_month')==month:old=legacy
                if old:
                    prior=json.loads(old['body'])
                    if any(str(prior.get(k,''))!=str(b.get(k,'')) for k in ['company','reference','receipt_no']) or cents(prior['amount'])!=cents(b['amount']):conflicts.append(dict(row=item['source_row'],company=b['company'],reason='Source row changed. Existing entry preserved; review it before updating.'))
                    skipped+=1;continue
                repeated=[r for r in existing if r['kind']==item['kind'] and r.get('receipt_month','')==b.get('receipt_month','') and ((b.get('reference') and norm(r.get('reference'))==norm(b['reference'])) or (b.get('receipt_no') and norm(r.get('receipt_no'))==norm(b['receipt_no']) and norm(r['company'])==norm(b['company']) and cents(r['amount'])==cents(b['amount'])))]
                if repeated:
                    if any(cents(r['amount'])!=cents(b['amount']) for r in repeated):conflicts.append(dict(row=item['source_row'],company=b['company'],reason='An existing reference has a different amount. Review the saved entry; it was not overwritten.'))
                    skipped+=1;continue
                rid=uuid.uuid4().hex
                c.execute('INSERT INTO records VALUES(?,?,?,?,?)',(rid,item['kind'],json.dumps(b),item['source'],item['source_row']))
                existing.append(dict(b,id=rid,kind=item['kind']));imported+=1
        matched=refresh_matches()
        return dict(imported=imported,skipped=skipped,conflicts=conflicts,supplier_rows=suppliers,account_rows=len(ac),automatic_receipt_links=matched)
    app.import_material_snapshot=save_snapshot

    restore_shared_dates(get_data(),db)
    refresh_matches()

    @app.get('/api/materials/config')
    def config():
        with db() as c:
            rs=records(c);scope=c.execute("SELECT value FROM workspace_settings WHERE key='scope_month'").fetchone()
            return jsonify(modes=PAYMENT_MODES,month=scope['value'] if scope else '2026-09',
                           months=sorted({r.get('receipt_month') for r in rs if cash_voucher(r) and r.get('receipt_month')}),
                           suppliers=[dict(r) for r in c.execute('SELECT * FROM suppliers ORDER BY name')],
                           accounts=[dict(r) for r in c.execute('SELECT * FROM accounts ORDER BY code')],read_only=app.config.get('HOSTED_PREVIEW',False))

    @app.get('/api/materials/entries')
    def entries():
        month=request.args.get('month','');method=request.args.get('method','')
        with db() as c:
            allrows=records(c);byid={r['id']:r for r in allrows}
            rows=[r for r in allrows if material_payment(r) and (not month or r.get('date','').startswith(month)) and (not method or norm(r.get('method'))==norm(method))]
            links=list(c.execute('SELECT payment,receipt FROM presence_links'))
            for r in rows:r['matched_receipt_numbers']=', '.join(dict.fromkeys(byid[link['receipt']].get('receipt_no','') for link in links if link['payment']==r['id']))
        return jsonify(rows=sorted(rows,key=lambda r:r.get('date','')),modes=PAYMENT_MODES)

    @app.post('/api/materials/enrich')
    def enrich():
        b=request.get_json() or {}
        with db() as c:
            suppliers=[dict(r) for r in c.execute('SELECT * FROM suppliers')]
            matched=[s for s in suppliers if norm(s['name'])==norm(b.get('company'))]
            if not matched and tin(b.get('tin')):matched=[s for s in suppliers if tin(s['tin'])==tin(b['tin'])]
            fields={}
            if len(matched)==1:fields.update(company=matched[0]['name'],tin=matched[0]['tin'],address=matched[0]['address'])
            code=b.get('code') or 'CS-0001';account=c.execute('SELECT title FROM accounts WHERE code=?',(code,)).fetchone()
            if account:fields.update(code=code,account=account['title'])
        return jsonify(fields=fields,ambiguous=len(matched)>1)

    @app.post('/api/materials/parse')
    def parse_material():
        b=request.get_json() or {};mode=b.get('mode','payment')
        if mode not in ['payment','receipt']:return jsonify(error='Choose payment or voucher receipt'),400
        try:month=month_value(b.get('month','2026-09'))
        except ValueError as e:return jsonify(error=str(e)),400
        with db() as c:
            rs=records(c);suppliers=[dict(r) for r in c.execute('SELECT * FROM suppliers')]
            draft,warnings=extract(b.get('text',''),mode,suppliers,rs)
            # This form is specifically the Material Expense input, so Materials
            # is a module default rather than an inferred tax/accounting choice.
            account=c.execute("SELECT title FROM accounts WHERE code='CS-0001'").fetchone()
            draft.update(collection='Material Expense' if mode=='payment' else 'Cash Voucher',receipt_month=month if mode=='receipt' else '',code='CS-0001',account=account['title'] if account else 'Materials')
            if b.get('image'):c.execute('UPDATE documents SET text=? WHERE image=?',(b.get('text',''),b['image']))
            return jsonify(draft=draft,warnings=warnings,duplicates=duplicates(draft,rs))

    @app.post('/api/materials/import')
    def import_file():
        kind=request.form.get('kind','vouchers');f=request.files.get('file')
        if kind not in ['payments','vouchers','references'] or not f or Path(f.filename).suffix.lower()!='.xlsx':return jsonify(error='Choose an XLSX workbook and import type'),400
        try:
            month=month_value(request.form.get('month','2026-09'));folder=get_data()/'uploads';folder.mkdir(parents=True,exist_ok=True)
            path=folder/(uuid.uuid4().hex+'.xlsx');f.save(path)
            snapshot=audit(path);snapshot['file']=Path(f.filename).name
            return jsonify(save_snapshot(snapshot,kind,month))
        except ValueError as e:return jsonify(error=str(e)),400
        except (KeyError,zipfile.BadZipFile,openpyxl.utils.exceptions.InvalidFileException):return jsonify(error='Workbook format could not be read'),400

    @app.get('/api/materials/export')
    def export_material():
        month=request.args.get('month','')
        with db() as c:
            allrows=records(c);byid={r['id']:r for r in allrows};links=list(c.execute('SELECT payment,receipt FROM presence_links'))
            rs=[r for r in allrows if material_payment(r) and (not month or r.get('date','').startswith(month))]
            for r in rs:
                if not r.get('receipt_no'):r['receipt_no']=', '.join(dict.fromkeys(byid[a['receipt']].get('receipt_no','') for a in links if a['payment']==r['id']))
        w=openpyxl.Workbook();s=w.active;s.title='Material Expense'
        fields=['date','method','receipt_no','reference','company','remarks','tin','address','project','code','account','amount','fee']
        s.append(['DATE','MODE OF PAYMENT','RECEIPT NO.','REF. NO','PAYEE','DESCRIPTION','TIN','ADDRESS','PROJECT','ACCOUNT CODE','ACCOUNT TITLE','AMOUNT','FEES','PAYABLE AMOUNT','FULL TRANSFER BEFORE FEES','PERSONAL PORTION EXCLUDED','PERSONAL NOTES'])
        def safe(v):return "'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v
        for r in sorted(rs,key=lambda r:r.get('date','')):s.append([safe(r.get(k,'')) for k in fields]+[(cents(r['amount'])+cents(r.get('fee')))/100,r.get('transfer_amount',r['amount']),r.get('personal_amount',0),safe(r.get('personal_note',''))])
        s.freeze_panes='A2';s.auto_filter.ref=s.dimensions
        for col in ['L','M','N']:
            for cell in s[col][1:]:cell.number_format='#,##0.00'
        out=io.BytesIO();w.save(out);out.seek(0)
        return send_file(out,download_name='Material Expense '+(month or 'all months')+'.xlsx',as_attachment=True)
