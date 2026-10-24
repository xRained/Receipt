"""Restore a bundled private workspace only on a fresh local installation."""
from contextlib import closing
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path


def restore_initial_data(root,data):
    root,data=Path(root),Path(data)
    bundle=root/'seed-data'/'workspace.zip'
    database=data/'receipts.sqlite3'
    if database.exists() or not bundle.exists():return False
    data.mkdir(parents=True,exist_ok=True)
    allowed={'receipts.sqlite3','workbook-audit.json','september-additional-audit.json'}
    with zipfile.ZipFile(bundle) as archive:
        names=archive.namelist()
        if 'receipts.sqlite3' not in names:raise ValueError('Initial data package has no database')
        for name in names:
            parts=Path(name).parts
            if name.startswith(('/', '\\')) or '..' in parts or '\\' in name or ':' in name:
                raise ValueError('Unsafe initial data package path')
            if name not in allowed and not (len(parts)==2 and parts[0] in ['uploads','templates']):
                raise ValueError('Unexpected initial data package file')
        if archive.testzip():raise ValueError('Initial data package is damaged')
        with tempfile.TemporaryDirectory(prefix='.initial-data-',dir=data) as folder:
            staged=Path(folder)
            for name in names:
                target=staged/name;target.parent.mkdir(parents=True,exist_ok=True)
                with archive.open(name) as source,target.open('wb') as output:shutil.copyfileobj(source,output)
            with closing(sqlite3.connect(staged/'receipts.sqlite3')) as c:
                if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Initial database is damaged')
            for name in names:
                if name=='receipts.sqlite3':continue
                target=data/name
                if target.exists():raise ValueError('Initial data would overwrite existing files')
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(staged/name,target)
            # Publish the database last, after its attachments have been copied.
            if database.exists():return False
            shutil.copy2(staged/'receipts.sqlite3',database)
    return True
