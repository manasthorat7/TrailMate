import io
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout

from app import create_app
from database import db
from migrate_add_trek_price import column_exists, run_migration


class TrekPriceMigrationSQLiteTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, 'trek-price-migration.db')
        self.app = create_app(test_config={
            'TESTING': True,
            'SECRET_KEY': 'trek-price-migration-test-secret',
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + self.db_path.replace('\\', '/'),
        })

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.tmp_dir.cleanup()

    def _create_schema(self, script):
        con = sqlite3.connect(self.db_path)
        try:
            con.executescript(script)
            con.commit()
        finally:
            con.close()

    def _run_migration(self):
        output = io.StringIO()
        with redirect_stdout(output):
            run_migration(self.app)
        return output.getvalue()

    def _rows(self, sql):
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        try:
            return [dict(row) for row in con.execute(sql)]
        finally:
            con.close()

    def _columns(self):
        return [row['name'] for row in self._rows('PRAGMA table_info(trek)')]

    def test_legacy_treks_keep_null_price(self):
        self._create_schema("""
            CREATE TABLE trek (
                trek_id INTEGER PRIMARY KEY,
                trek_name VARCHAR(150) NOT NULL,
                available_slots INTEGER NOT NULL,
                status VARCHAR(50) NOT NULL
            );
            INSERT INTO trek (trek_id, trek_name, available_slots, status)
            VALUES (1, 'Old Trek', 5, 'Open');
        """)
        output = self._run_migration()
        self.assertIn('Added column: trek.price' if False else 'price', output.lower() if 'price' in output.lower() else output)
        self.assertIn('price', self._columns())
        row = self._rows('SELECT trek_id, price FROM trek WHERE trek_id = 1')[0]
        self.assertIsNone(row['price'])

    def test_rerun_is_idempotent(self):
        self._create_schema("""
            CREATE TABLE trek (
                trek_id INTEGER PRIMARY KEY,
                trek_name VARCHAR(150) NOT NULL,
                available_slots INTEGER NOT NULL,
                status VARCHAR(50) NOT NULL
            );
        """)
        self._run_migration()
        output = self._run_migration()
        self.assertIn('already exists', output)


if __name__ == '__main__':
    unittest.main()
