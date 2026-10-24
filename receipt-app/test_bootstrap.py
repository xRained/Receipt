from contextlib import closing
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from bootstrap import restore_initial_data

class BootstrapTests(unittest.TestCase):
    def test_fresh_install_restores_and_existing_database_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);data=root/'data';seed=root/'seed-data';seed.mkdir()
            source=root/'source.sqlite3'
            with closing(sqlite3.connect(source)) as c:
                c.execute('CREATE TABLE example(value TEXT)');c.execute("INSERT INTO example VALUES('saved record')");c.commit()
            with zipfile.ZipFile(seed/'workspace.zip','w') as z:
                z.write(source,'receipts.sqlite3');z.writestr('uploads/photo.jpg',b'example image')
            self.assertTrue(restore_initial_data(root,data))
            with closing(sqlite3.connect(data/'receipts.sqlite3')) as c:self.assertEqual(c.execute('SELECT value FROM example').fetchone()[0],'saved record')
            self.assertEqual((data/'uploads/photo.jpg').read_bytes(),b'example image')
            self.assertFalse(restore_initial_data(root,data))

    def test_unsafe_archive_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'seed-data').mkdir()
            with zipfile.ZipFile(root/'seed-data/workspace.zip','w') as z:
                z.writestr('receipts.sqlite3',b'bad');z.writestr('../outside',b'bad')
            with self.assertRaises(ValueError):restore_initial_data(root,root/'data')
            self.assertFalse((root/'outside').exists())
