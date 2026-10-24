"""Enable all Material Expense payment modes without resetting user decisions."""
import json
from datetime import datetime
from app import app,DATA,db,records


if __name__=='__main__':
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
    backup=DATA/('before-material-entry-'+stamp+'.zip')
    with app.test_request_context('/api/backup'):
        response=app.view_functions['backup']();response.direct_passthrough=False
        backup.write_bytes(response.get_data());response.close()
    snapshots=json.loads((DATA/'workbook-audit.json').read_text(encoding='utf-8'))
    with db() as c:c.execute("INSERT OR REPLACE INTO workspace_settings VALUES('workflow','materials_intake_receipt_presence')")
    results=[]
    for snapshot in snapshots:
        kind='payments' if any(s['name']=='Material Expense' for s in snapshot['sheets']) else 'references'
        results.append(app.import_material_snapshot(snapshot,kind,'2026-09'))
    with db() as c:
        rs=records(c)
        from collections import Counter
        print('Material payment modes:',dict(Counter(r['method'] for r in rs if r['kind']=='payment' and r.get('collection')=='Material Expense')))
        print('Suppliers:',c.execute('SELECT COUNT(*) FROM suppliers').fetchone()[0])
        print('COA:',c.execute('SELECT COUNT(*) FROM accounts').fetchone()[0])
    print('Import results:',json.dumps(results));print('Backup:',backup)
