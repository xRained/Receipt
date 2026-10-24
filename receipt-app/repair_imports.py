"""Restore net payable fields for previously imported voucher rows, by source row."""
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
import openpyxl
from app import DATA, auto_match, cents, clean, db


def repair(path):
    backup=DATA / ('before-matching-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.sqlite3')
    with db() as source, sqlite3.connect(backup) as target:
        source.backup(target)
    w=openpyxl.load_workbook(path,read_only=True,data_only=True)
    updated=0
    with db() as c:
        for s in w:
            if 'Voucher' not in s.title:continue
            headers=None
            for n,row in enumerate(s.iter_rows(values_only=True),1):
                vals=[clean(v) for v in row]
                if headers is None:
                    if 'AMOUNT' in vals and 'DATE' in vals:headers=vals
                    continue
                paid_col=next((headers.index(k) for k in ['AMOUNT PAID','CASH IN BANK'] if k in headers),None)
                if paid_col is None or paid_col>=len(vals) or not vals[paid_col]:continue
                r=c.execute('SELECT * FROM records WHERE source=? AND source_row=?',(Path(path).name+' / '+s.title,n)).fetchone()
                if not r:continue
                b=json.loads(r['body'])
                b['settlement_amount']=cents(vals[paid_col])/100
                ewt=headers.index('EXPANDED WITHHOLDING TAX')
                b['withholding']=cents(vals[ewt])/100
                allocated=c.execute('SELECT COALESCE(SUM(cents),0) FROM allocations WHERE receipt=?',(r['id'],)).fetchone()[0]
                if cents(b['settlement_amount'])<allocated:raise ValueError('Existing allocation exceeds net payable; manual review needed')
                c.execute('UPDATE records SET body=? WHERE id=?',(json.dumps(b),r['id']))
                updated+=1
    w.close()
    print('Backup:',backup)
    print('Net payable fields restored:',updated)
    print('Automatic matches:',auto_match())


if __name__=='__main__':repair(sys.argv[1])
