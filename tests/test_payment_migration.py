"""
tests/test_payment_migration.py
--------------------------------
Isolated SQLite tests for migrate_add_payment_fields.py.

Each test creates a throwaway SQLite database under a temporary directory. The
real instance database is never opened or modified.
"""
import io
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from app import create_app
from database import db
from migrate_add_payment_fields import column_exists, run_migration


PAYMENT_COLUMNS = (
    'payment_status',
    'amount',
    'currency',
    'razorpay_order_id',
    'razorpay_payment_id',
    'razorpay_signature',
)


class PaymentMigrationSQLiteTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, 'migration-test.db')
        self.app = create_app(test_config={
            'TESTING': True,
            'SECRET_KEY': 'payment-migration-test-secret',
            'SQLALCHEMY_DATABASE_URI':
                'sqlite:///' + self.db_path.replace('\\', '/'),
        })

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.tmp_dir.cleanup()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _execute(self, sql, params=()):
        con = sqlite3.connect(self.db_path)
        try:
            con.execute(sql, params)
            con.commit()
        finally:
            con.close()

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
        return [row['name'] for row in self._rows('PRAGMA table_info(booking)')]

    def _indexes(self):
        return self._rows('PRAGMA index_list(booking)')

    def _create_legacy_schema(self):
        self._create_schema("""
            CREATE TABLE trek (
                trek_id INTEGER PRIMARY KEY,
                trek_name VARCHAR(150) NOT NULL,
                available_slots INTEGER NOT NULL,
                status VARCHAR(50) NOT NULL
            );
            CREATE TABLE booking (
                booking_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                trek_id INTEGER NOT NULL,
                booking_date DATETIME NOT NULL,
                status VARCHAR(50) NOT NULL
            );
            INSERT INTO trek (trek_id, trek_name, available_slots, status)
            VALUES
                (1, 'Kalsubai Trek', 14, 'Completed'),
                (2, 'Nanda Devi', 19, 'Completed');
            INSERT INTO booking
                (booking_id, user_id, trek_id, booking_date, status)
            VALUES
                (1, 2, 1, '2026-08-06 07:03:27.236235', 'Confirmed'),
                (2, 2, 2, '2026-08-09 10:12:49.258599', 'Completed');
        """)

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------
    def test_fresh_migration_tags_legacy_and_preserves_status_and_slots(self):
        self._create_legacy_schema()

        output = self._run_migration()

        self.assertIn("Added column: booking.payment_status", output)
        self.assertEqual(
            set(PAYMENT_COLUMNS).issubset(set(self._columns())),
            True,
        )

        table_info = {
            row['name']: row for row in self._rows('PRAGMA table_info(booking)')
        }
        self.assertEqual(table_info['payment_status']['notnull'], 1)
        self.assertEqual(table_info['payment_status']['dflt_value'], "'Unpaid'")
        self.assertEqual(table_info['currency']['notnull'], 1)
        self.assertEqual(table_info['currency']['dflt_value'], "'INR'")
        self.assertEqual(table_info['amount']['notnull'], 0)
        self.assertEqual(table_info['razorpay_order_id']['notnull'], 0)

        bookings = self._rows("""
            SELECT booking_id, status, payment_status, amount, currency,
                   razorpay_order_id, razorpay_payment_id, razorpay_signature
            FROM booking
            ORDER BY booking_id
        """)
        self.assertEqual(bookings, [
            {
                'booking_id': 1, 'status': 'Confirmed',
                'payment_status': 'Legacy', 'amount': None,
                'currency': 'INR', 'razorpay_order_id': None,
                'razorpay_payment_id': None, 'razorpay_signature': None,
            },
            {
                'booking_id': 2, 'status': 'Completed',
                'payment_status': 'Legacy', 'amount': None,
                'currency': 'INR', 'razorpay_order_id': None,
                'razorpay_payment_id': None, 'razorpay_signature': None,
            },
        ])

        treks = self._rows("""
            SELECT trek_id, status, available_slots
            FROM trek
            ORDER BY trek_id
        """)
        self.assertEqual(treks, [
            {'trek_id': 1, 'status': 'Completed', 'available_slots': 14},
            {'trek_id': 2, 'status': 'Completed', 'available_slots': 19},
        ])

        index_names = [row['name'] for row in self._indexes()]
        self.assertIn('ix_booking_razorpay_order_id', index_names)
        index = next(
            row for row in self._indexes()
            if row['name'] == 'ix_booking_razorpay_order_id'
        )
        self.assertEqual(index['unique'], 1)

    def test_historical_booked_row_is_legacy_and_not_expirable(self):
        self._create_schema("""
            CREATE TABLE trek (
                trek_id INTEGER PRIMARY KEY,
                trek_name VARCHAR(150) NOT NULL,
                available_slots INTEGER NOT NULL,
                status VARCHAR(50) NOT NULL
            );
            CREATE TABLE booking (
                booking_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                trek_id INTEGER NOT NULL,
                booking_date DATETIME NOT NULL,
                status VARCHAR(50) NOT NULL
            );
            INSERT INTO trek (trek_id, trek_name, available_slots, status)
            VALUES (1, 'Old Trek', 9, 'Completed');
            INSERT INTO booking
                (booking_id, user_id, trek_id, booking_date, status)
            VALUES
                (1, 2, 1, '2026-08-01 09:00:00', 'Booked');
        """)

        self._run_migration()

        row = self._rows("""
            SELECT booking_id, status, payment_status
            FROM booking WHERE booking_id = 1
        """)[0]
        self.assertEqual(row, {
            'booking_id': 1,
            'status': 'Booked',
            'payment_status': 'Legacy',
        })
        self.assertEqual(self._rows("""
            SELECT booking_id
            FROM booking
            WHERE status = 'Booked'
              AND payment_status IN ('Pending', 'Unpaid', 'Failed')
              AND booking_date < datetime('now', '-15 minutes')
        """), [])
        self.assertEqual(self._rows("""
            SELECT available_slots FROM trek WHERE trek_id = 1
        """)[0]['available_slots'], 9)

    def test_failure_after_payment_status_rolls_back_and_rerun_succeeds(self):
        self._create_legacy_schema()

        def fail_on_amount(conn, table, column):
            if column == 'amount':
                raise RuntimeError('simulated failure after payment_status')
            return column_exists(conn, table, column)

        with mock.patch(
            'migrate_add_payment_fields.column_exists',
            side_effect=fail_on_amount,
        ):
            with self.assertRaises(RuntimeError):
                self._run_migration()

        # The payment_status ALTER and Legacy UPDATE must both be rolled back.
        self.assertNotIn('payment_status', self._columns())
        self.assertEqual(self._rows("""
            SELECT booking_id, status FROM booking ORDER BY booking_id
        """), [
            {'booking_id': 1, 'status': 'Confirmed'},
            {'booking_id': 2, 'status': 'Completed'},
        ])
        self.assertEqual(self._rows("""
            SELECT trek_id, status, available_slots
            FROM trek ORDER BY trek_id
        """), [
            {'trek_id': 1, 'status': 'Completed', 'available_slots': 14},
            {'trek_id': 2, 'status': 'Completed', 'available_slots': 19},
        ])

        # A clean rerun must complete normally.
        self._run_migration()
        self.assertIn('payment_status', self._columns())
        rows = self._rows("""
            SELECT booking_id, status, payment_status
            FROM booking ORDER BY booking_id
        """)
        self.assertEqual(rows, [
            {'booking_id': 1, 'status': 'Confirmed', 'payment_status': 'Legacy'},
            {'booking_id': 2, 'status': 'Completed', 'payment_status': 'Legacy'},
        ])

    def test_rerun_does_not_retag_new_unpaid_or_pending_bookings(self):
        self._create_legacy_schema()
        self._run_migration()

        self._execute("""
            INSERT INTO booking
                (booking_id, user_id, trek_id, booking_date, status,
                 payment_status, amount, currency, razorpay_order_id)
            VALUES
                (3, 2, 1, '2026-10-26 10:00:00', 'Booked',
                 'Unpaid', NULL, 'INR', NULL),
                (4, 2, 1, '2026-10-26 10:01:00', 'Booked',
                 'Pending', 1200.0, 'INR', 'order_new')
        """)

        output = self._run_migration()
        self.assertIn('No schema changes needed', output)
        self.assertIn("still have payment_status='Unpaid'", output)

        bookings = self._rows("""
            SELECT booking_id, status, payment_status, amount, currency,
                   razorpay_order_id
            FROM booking
            ORDER BY booking_id
        """)
        self.assertEqual([row['payment_status'] for row in bookings], [
            'Legacy', 'Legacy', 'Unpaid', 'Pending',
        ])
        self.assertEqual([row['status'] for row in bookings], [
            'Confirmed', 'Completed', 'Booked', 'Booked',
        ])
        self.assertEqual(bookings[2]['amount'], None)
        self.assertEqual(bookings[2]['razorpay_order_id'], None)
        self.assertEqual(bookings[3]['amount'], 1200.0)
        self.assertEqual(bookings[3]['razorpay_order_id'], 'order_new')

        treks = self._rows("""
            SELECT trek_id, status, available_slots
            FROM trek
            ORDER BY trek_id
        """)
        self.assertEqual(treks, [
            {'trek_id': 1, 'status': 'Completed', 'available_slots': 14},
            {'trek_id': 2, 'status': 'Completed', 'available_slots': 19},
        ])

    def test_index_failure_rolls_back_and_rerun_can_succeed(self):
        self._create_schema("""
            CREATE TABLE trek (
                trek_id INTEGER PRIMARY KEY,
                trek_name VARCHAR(150) NOT NULL,
                available_slots INTEGER NOT NULL,
                status VARCHAR(50) NOT NULL
            );
            CREATE TABLE booking (
                booking_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                trek_id INTEGER NOT NULL,
                booking_date DATETIME NOT NULL,
                status VARCHAR(50) NOT NULL,
                payment_status VARCHAR(50) NOT NULL DEFAULT 'Unpaid',
                razorpay_order_id VARCHAR(100)
            );
            INSERT INTO trek (trek_id, trek_name, available_slots, status)
            VALUES
                (1, 'Kalsubai Trek', 14, 'Completed'),
                (2, 'Nanda Devi', 19, 'Completed');
            INSERT INTO booking
                (booking_id, user_id, trek_id, booking_date, status,
                 payment_status, razorpay_order_id)
            VALUES
                (1, 2, 1, '2026-08-06 07:03:27.236235', 'Confirmed',
                 'Legacy', 'order_dup'),
                (2, 2, 2, '2026-08-09 10:12:49.258599', 'Completed',
                 'Legacy', 'order_dup');
        """)

        columns_before = self._columns()

        with self.assertRaises(RuntimeError):
            self._run_migration()

        self.assertEqual(self._columns(), columns_before)
        self.assertNotIn('amount', self._columns())
        self.assertNotIn(
            'ix_booking_razorpay_order_id',
            [row['name'] for row in self._indexes()],
        )
        rows_after_failure = self._rows("""
            SELECT booking_id, status, payment_status, razorpay_order_id
            FROM booking
            ORDER BY booking_id
        """)
        self.assertEqual(rows_after_failure, [
            {
                'booking_id': 1, 'status': 'Confirmed',
                'payment_status': 'Legacy', 'razorpay_order_id': 'order_dup',
            },
            {
                'booking_id': 2, 'status': 'Completed',
                'payment_status': 'Legacy', 'razorpay_order_id': 'order_dup',
            },
        ])
        self.assertEqual(self._rows("""
            SELECT trek_id, status, available_slots
            FROM trek
            ORDER BY trek_id
        """), [
            {'trek_id': 1, 'status': 'Completed', 'available_slots': 14},
            {'trek_id': 2, 'status': 'Completed', 'available_slots': 19},
        ])

        # Resolve the duplicate that caused the unique-index failure and rerun.
        self._execute("""
            UPDATE booking SET razorpay_order_id = NULL WHERE booking_id = 2
        """)
        self._run_migration()

        self.assertTrue(set(PAYMENT_COLUMNS).issubset(set(self._columns())))
        self.assertIn(
            'ix_booking_razorpay_order_id',
            [row['name'] for row in self._indexes()],
        )
        rows_after_rerun = self._rows("""
            SELECT booking_id, status, payment_status, razorpay_order_id
            FROM booking
            ORDER BY booking_id
        """)
        self.assertEqual(rows_after_rerun, [
            {
                'booking_id': 1, 'status': 'Confirmed',
                'payment_status': 'Legacy', 'razorpay_order_id': 'order_dup',
            },
            {
                'booking_id': 2, 'status': 'Completed',
                'payment_status': 'Legacy', 'razorpay_order_id': None,
            },
        ])

    def test_index_only_rerun_commits_and_preserves_payment_data(self):
        self._create_schema("""
            CREATE TABLE trek (
                trek_id INTEGER PRIMARY KEY,
                trek_name VARCHAR(150) NOT NULL,
                available_slots INTEGER NOT NULL,
                status VARCHAR(50) NOT NULL
            );
            CREATE TABLE booking (
                booking_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                trek_id INTEGER NOT NULL,
                booking_date DATETIME NOT NULL,
                status VARCHAR(50) NOT NULL,
                payment_status VARCHAR(50) NOT NULL DEFAULT 'Unpaid',
                amount FLOAT,
                currency VARCHAR(10) NOT NULL DEFAULT 'INR',
                razorpay_order_id VARCHAR(100),
                razorpay_payment_id VARCHAR(100),
                razorpay_signature VARCHAR(200)
            );
            INSERT INTO trek (trek_id, trek_name, available_slots, status)
            VALUES
                (1, 'Kalsubai Trek', 14, 'Completed'),
                (2, 'Nanda Devi', 19, 'Completed');
            INSERT INTO booking
                (booking_id, user_id, trek_id, booking_date, status,
                 payment_status, amount, currency, razorpay_order_id,
                 razorpay_payment_id, razorpay_signature)
            VALUES
                (1, 2, 1, '2026-08-06 07:03:27.236235', 'Confirmed',
                 'Verified', 1000.0, 'INR', 'order_1', 'pay_1', 'sig_1'),
                (2, 2, 2, '2026-08-09 10:12:49.258599', 'Completed',
                 'Legacy', NULL, 'INR', NULL, NULL, NULL);
        """)

        before = self._rows("""
            SELECT booking_id, status, payment_status, amount, currency,
                   razorpay_order_id, razorpay_payment_id, razorpay_signature
            FROM booking
            ORDER BY booking_id
        """)

        output = self._run_migration()

        self.assertIn('Added unique index', output)
        self.assertIn('No schema changes needed', output)
        self.assertIn(
            'ix_booking_razorpay_order_id',
            [row['name'] for row in self._indexes()],
        )
        self.assertEqual(self._rows("""
            SELECT booking_id, status, payment_status, amount, currency,
                   razorpay_order_id, razorpay_payment_id, razorpay_signature
            FROM booking
            ORDER BY booking_id
        """), before)


if __name__ == '__main__':
    unittest.main()
