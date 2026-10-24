"""Register immutable original templates and saved audit snapshots locally."""
import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from app import DATA,app,db


if __name__=='__main__':
    with db() as source,closing(sqlite3.connect(DATA/('before-whole-system-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.sqlite3'))) as target:source.backup(target)
    snapshots=json.loads((DATA/'workbook-audit.json').read_text(encoding='utf-8'))
    paths=[Path(r'C:\Users\ADMIN\OneDrive\Desktop\2026 EXPENSES 3rd Quarter.xlsx'),Path(r'D:\download\9 SEPTEMBER 2026.xlsx')]
    for kind,path,snapshot in zip(['quarterly','monthly'],paths,snapshots):
        app.register_source(path,kind,snapshot)
        print('Registered',kind, len(snapshot['sheets']),'sheets')
