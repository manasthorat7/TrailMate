"""
tests/test_expire_pending_cli.py
-------------------------------
Isolated tests for the expire-pending-bookings Flask CLI command.

Uses only an in-memory SQLite database. No migration, network call, or real
database is used.
"""
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch

from click.testing import CliRunner
from werkzeug.security import generate_password_hash

from app import create_app
from database import db
from models import User, Trek, Booking


class ExpirePendingCliTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(test_config={
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
            'WTF_CSRF_ENABLED': False,
            'SECRET_KEY': 'expire-cli-test-secret',
        })

        with self.app.app_context():
            db.create_all()

            user = User(
                name='CLI Trekker',
                email='cli@test.com',
                password=generate_password_hash('pass123'),
                role='user',
                status='Active',
            )
            db.session.add(user)
            db.session.flush()

            trek = Trek(
                trek_name='CLI Test Trek',
                location='Test Range',
                difficulty='Moderate',
                duration='3 Days',
                available_slots=2,
                start_date=date.today() + timedelta(days=5),
                end_date=date.today() + timedelta(days=7),
                status='Open',
            )
            db.session.add(trek)
            db.session.flush()

            self.user_id = user.id
            self.trek_id = trek.trek_id
            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def _add_booking(self, status, payment_status, old=False):
        with self.app.app_context():
            booking = Booking(
                user_id=self.user_id,
                trek_id=self.trek_id,
                status=status,
                payment_status=payment_status,
                booking_date=datetime.utcnow() - timedelta(minutes=30) if old
                else datetime.utcnow(),
            )
            db.session.add(booking)
            db.session.commit()
            return booking.booking_id

    def _booking(self, booking_id):
        with self.app.app_context():
            return db.session.get(Booking, booking_id)

    def _slots(self):
        with self.app.app_context():
            return db.session.get(Trek, self.trek_id).available_slots

    def test_cli_command_expires_stale_booking_once(self):
        booking_id = self._add_booking('Booked', 'Pending', old=True)

        runner = self.app.test_cli_runner()
        result = runner.invoke(args=['expire-pending-bookings'])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn('Expired 1 stale pending booking(s).', result.output)

        booking = self._booking(booking_id)
        self.assertEqual(booking.status, 'Cancelled')
        self.assertEqual(booking.payment_status, 'Failed')
        self.assertEqual(self._slots(), 3)

        result = runner.invoke(self.app.cli, ['expire-pending-bookings'])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn('Expired 0 stale pending booking(s).', result.output)
        self.assertEqual(self._slots(), 3)

    def test_cli_command_does_not_expire_recent_booking(self):
        booking_id = self._add_booking('Booked', 'Pending', old=False)

        runner = self.app.test_cli_runner()
        result = runner.invoke(args=['expire-pending-bookings'])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn('Expired 0 stale pending booking(s).', result.output)

        booking = self._booking(booking_id)
        self.assertEqual(booking.status, 'Booked')
        self.assertEqual(booking.payment_status, 'Pending')
        self.assertEqual(self._slots(), 2)

    def test_cli_command_reports_failure_without_secret_leakage(self):
        runner = CliRunner()

        with patch('routes.user._expire_pending_bookings', side_effect=RuntimeError('boom')):
            result = runner.invoke(self.app.cli, ['expire-pending-bookings'])

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn('Failed to expire pending bookings: boom', result.output)


if __name__ == '__main__':
    unittest.main()
