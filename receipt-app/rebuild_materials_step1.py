"""Reset active data to online Material Expense vs September Cash Voucher only."""
import json
from datetime import datetime
from collections import Counter
from app import app,DATA,db,records
from rebuild_september import SOURCES,prepare
from audit_workbooks import audit
from presence import online_material,compare


def rebuild():
    snapshots=[audit(p) for p in SOURCES]
    prepared,excluded,suppliers,accounts=prepare(snapshots)
    kept=[];excluded_material=[]
    for row in prepared:
        body=json.loads(row[2]);body.update(id=row[0],kind=row[1])
        if online_material(body) or (row[1]=='receipt' and body['collection']=='September Cash Voucher'):kept.append(row)
        elif row[1]=='payment' and body['collection']=='Material Expense':excluded_material.append(body)
    assert any(r[1]=='payment' for r in kept) and any(r[1]=='receipt' for r in kept)
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S');backup=DATA/('before-materials-step1-'+stamp+'.zip')
    with app.test_request_context('/api/backup'):
        response=app.view_functions['backup']();response.direct_passthrough=False
        backup.write_bytes(response.get_data());response.close()
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        for table in ['presence_links','presence_dismissals','allocations','match_audit','match_blocks','supplier_aliases','returns','documents','records','controls','templates','suppliers','accounts']:c.execute('DELETE FROM '+table)
        c.executemany('INSERT OR REPLACE INTO workspace_settings VALUES(?,?)',[('scope_month','2026-09'),('workflow','online_material_receipt_presence')])
        c.executemany('INSERT INTO records VALUES(?,?,?,?,?)',kept)
        c.executemany('INSERT INTO suppliers VALUES(?,?,?)',[(name,*value) for name,value in suppliers.items()])
        c.executemany('INSERT INTO accounts VALUES(?,?)',accounts.items())
    for kind,path,snapshot in zip(['quarterly','monthly'],SOURCES,snapshots):app.register_source(path,kind,snapshot)
    with db() as c:
        c.execute('DELETE FROM controls')
        rows=records(c)
    ps=[r for r in rows if online_material(r)];rs=[r for r in rows if r['kind']=='receipt']
    compared,selected=compare(ps,rs)
    manifest=dict(backup=str(backup),payments=len(ps),cash_vouchers=len(rs),materials_vouchers=len(selected),
                  statuses=dict(Counter(r['status'] for r in compared)),excluded_non_online_material_rows=excluded_material,
                  policy='Step 1 only. September online Material Expense payments against September Cash Voucher; default Materials account, filterable to other accounts. All voucher dates retained. No aggregate total reconciliation, allocation, GCashCheck, cheque-voucher or non-receipt ledger.')
    (DATA/'materials-step1-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (DATA/'workbook-audit.json').write_text(json.dumps(snapshots),encoding='utf-8')
    print(json.dumps({k:v for k,v in manifest.items() if k!='excluded_non_online_material_rows'},indent=2),flush=True)


if __name__=='__main__':rebuild()
