"""Rebuild September source records atomically; preserve a complete backup first."""
import json
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from openpyxl.utils.datetime import from_excel
from app import app,DATA,db,cents,clean,auto_match,records
from audit_workbooks import audit
from workbooks import normalized_receipts,account_entries

MONTH='2026-09'
SOURCES=[Path(r'C:\Users\ADMIN\OneDrive\Desktop\2026 EXPENSES 3rd Quarter.xlsx'),Path(r'D:\download\9 SEPTEMBER 2026.xlsx')]


def source_date(value):
    if isinstance(value,(int,float)):
        try:return from_excel(value).date().isoformat()
        except (ValueError,OverflowError,AttributeError):return ''
    return clean(value)


def prepare(snapshots):
    result=[];excluded=[];suppliers={};accounts={}
    for wi,workbook in enumerate(snapshots):
        grouped={(r['source'],r['source_row']):r for r in normalized_receipts(workbook)}
        for code,title in account_entries(workbook):accounts[code]=title
        for s in workbook['sheets']:
            if s['name'] in ['Suppliers','Suppliers List']:
                for r in s['rows']:
                    v=r['values'];name=v.get('A')
                    if r['row']>1 and isinstance(name,str) and name.strip():suppliers[name.strip()]=(clean(v.get('B')),clean(v.get('C')))
                continue
            payment=s['name'] in ['Material Expense','Cost of Sales Expense','Operating Expense','COS_Allowance']
            receipt='Voucher' in s['name'] or s['name']=='Non Receipt'
            if not payment and not receipt:continue
            header=next((r for r in s['rows'] if 'DATE' in r['values'].values() and any(v in r['values'].values() for v in ['PAYEE','PARTICULARS','PATRICULARS','EMPLOYEE NAME'])),None)
            if not header:continue
            mapping={v:k for k,v in header['values'].items() if isinstance(v,str)}
            raw={r['row']:r['values'] for r in s['rows']}
            for row in s['rows']:
                if row['row']<=header['row']:continue
                v=row['values']
                def get(*names):
                    return next((v[mapping[n]] for n in names if n in mapping and mapping[n] in v),'')
                company=clean(get('PAYEE','PARTICULARS','PATRICULARS','EMPLOYEE NAME'));amount=get('AMOUNT','ALLOWANCE AMOUNT')
                if not company or not isinstance(amount,(int,float)) or amount<=0:continue
                day=source_date(get('DATE'));source=workbook['file']+' / '+s['name']
                if payment and not day.startswith(MONTH):
                    excluded.append(dict(source=source,row=row['row'],date=day,company=company,amount=amount,reason='Outside September' if day else 'Missing payment date'))
                    continue
                b=dict(date=day,company=company,amount=cents(amount)/100,fee=cents(get('FEES'))/100,
                       reference=clean(get('REF. NO','REFERENCE NO.','CHECK #')),method=clean(get('MODE OF PAYMENT')) or ('Cheque' if 'Check' in s['name'] else 'Cash'),
                       receipt_no=clean(get('RECEIPT NO.','S.I#')),tin=clean(get('TIN')),address=clean(get('ADDRESS')),
                       code=clean(get('ACCOUNT CODE','CODE')),account=clean(get('ACCOUNT TITLE','ACCOUNT')),
                       project=clean(get('PROJECT','SITE LOCATION')),remarks=clean(get('DESCRIPTION')),collection=s['name'],receipt_month=MONTH if receipt else '',
                       treatment='advance' if s['name']=='COS_Allowance' else 'no_receipt' if s['name']=='Non Receipt' else 'business')
                if receipt:
                    extra=grouped.get((source,row['row']))
                    if extra:
                        b.update({k:val for k,val in extra.items() if k not in ['source','source_row']})
                        lines=[raw.get(n,{}) for n in b['source_rows']]
                        b['source_lines']=lines;b['tax_tag']=v.get('S' if 'Check' in s['name'] else 'R','')
                        b['net_tax_base']=sum(float(p.get('W' if 'Check' in s['name'] else 'V',0) or 0) for p in lines)
                        if b.get('personal'):b['treatment']='personal'
                    else:b.update(settlement_amount=b['amount'],withholding=0)
                else:b['settlement_amount']=b['amount']
                result.append((uuid.uuid4().hex,'payment' if payment else 'receipt',json.dumps(b),source,row['row']))
    return result,excluded,suppliers,accounts


def rebuild():
    # Complete the read/validation work before touching the active ledger.
    snapshots=[audit(path) for path in SOURCES]
    rows,excluded,suppliers,accounts=prepare(snapshots)
    assert rows and any(r[1]=='payment' for r in rows) and any(r[1]=='receipt' for r in rows)
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
    backup=DATA/('before-september-reset-'+stamp+'.zip')
    with app.test_request_context('/api/backup'):
        response=app.view_functions['backup']();response.direct_passthrough=False
        backup.write_bytes(response.get_data());response.close()
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        for table in ['allocations','match_audit','match_blocks','supplier_aliases','returns','documents','records','controls','suppliers','accounts','templates']:
            c.execute('DELETE FROM '+table)
        c.execute("INSERT OR REPLACE INTO workspace_settings VALUES('scope_month',?)",(MONTH,))
        c.executemany('INSERT INTO records VALUES(?,?,?,?,?)',rows)
        c.executemany('INSERT INTO suppliers VALUES(?,?,?)',[(n,*v) for n,v in suppliers.items()])
        c.executemany('INSERT INTO accounts VALUES(?,?)',accounts.items())
    for kind,path,snapshot in zip(['quarterly','monthly'],SOURCES,snapshots):app.register_source(path,kind,snapshot)
    matching=auto_match()
    with db() as c:
        current=records(c)
        assert all(r['date'].startswith(MONTH) for r in current if r['kind']=='payment')
        assert all(r['receipt_month']==MONTH for r in current if r['kind']=='receipt')
        controls=c.execute('SELECT COUNT(*) FROM controls').fetchone()[0]
    manifest=dict(month=MONTH,backup=str(backup),counts=dict(Counter(r['collection'] for r in current)),
                  payments=sum(r['kind']=='payment' for r in current),receipt_groups=sum(r['kind']=='receipt' for r in current),
                  excluded_payment_rows=len(excluded),controls=controls,matching=matching,
                  policy='September payment dates only; all September-register receipt groups retained, including older or blank document dates. Reference supplier/COA masters retained. Prior matches, manual edits and document links are archived in the backup, not reused.')
    (DATA/'september-reset-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (DATA/('september-excluded-payments-'+stamp+'.json')).write_text(json.dumps(excluded,indent=2),encoding='utf-8')
    (DATA/'workbook-audit.json').write_text(json.dumps(snapshots),encoding='utf-8')
    print(json.dumps(manifest,indent=2),flush=True)


if __name__=='__main__':rebuild()
