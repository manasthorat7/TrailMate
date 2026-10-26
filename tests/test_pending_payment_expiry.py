"""
tests/test_pending_payment_expiry.py
-----------------------------------
Focused regression tests for pending-payment expiry.

These tests use only an isolated in-memory SQLite database and do not run
migrations, network calls, or any Razorpay API requests.
"""
import unittest
from datetime import date, datetime, timedelta

from werkzeug.security import generate_password_hash

from app import create_app
from database import db
from models import User, Trek, Booking
from routes.user import _expire_pending_bookings


class PendingPaymentExpiryTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(test_config={
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
            'WTF_CSRF_ENABLED': False,
            'SECRET_KEY': 'pending-expiry-test-secret',
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()

            user = User(
                name='Expiry Trekker',
                email='expiry@test.com',
                password=generate_password_hash('pass123'),
                role='user',
                status='Active',
            )
            db.session.add(user)
            db.session.flush()

            trek = Trek(
                trek_name='Expiry Test Trek',
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

    def _add_booking(self, status, payment_status, old=False, slots_delta=0):
        with self.app.app_context():
            if slots_delta:
                trek = db.session.get(Trek, self.trek_id)
                trek.available_slots += slots_delta
                db.session.flush()

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

    def test_old_pending_booking_expires_and_releases_slot_once(self):
        booking_id = self._add_booking('Booked', 'Pending', old=True)

        with self.app.app_context():
            _expire_pending_bookings()
            _expire_pending_bookings()

        booking = self._booking(booking_id)
        self.assertEqual(booking.status, 'Cancelled')
        self.assertEqual(booking.payment_status, 'Failed')
        self.assertEqual(self._slots(), 3)

    def test_recent_pending_booking_remains_reserved(self):
        booking_id = self._add_booking('Booked', 'Pending', old=False)

        with self.app.app_context():
            _expire_pending_bookings()

        booking = self._booking(booking_id)
        self.assertEqual(booking.status, 'Booked')
        self.assertEqual(booking.payment_status, 'Pending')
        self.assertEqual(self._slots(), 2)

    def test_old_failed_booking_expires_and_releases_slot(self):
        booking_id = self._add_booking('Booked', 'Failed', old=True)

        with self.app.app_context():
            _expire_pending_bookings()
            _expire_pending_bookings()

        booking = self._booking(booking_id)
        self.assertEqual(booking.status, 'Cancelled')
        self.assertEqual(booking.payment_status, 'Failed')
        self.assertEqual(self._slots(), 3)

    def test_protected_bookings_are_not_expired(self):
        cases = [
            ('Booked', 'Verified'),
            ('Booked', 'Legacy'),
            ('Completed', 'Pending'),
            ('Cancelled', 'Pending'),
        ]
        booking_ids = [
            self._add_booking(status, payment_status, old=True)
            for status, payment_status in cases
        ]

        with self.app.app_context():
            _expire_pending_bookings()

        for booking_id, (status, payment_status) in zip(booking_ids, cases):
            booking = self._booking(booking_id)
            self.assertEqual(booking.status, status)
            self.assertEqual(booking.payment_status, payment_status)

        self.assertEqual(self._slots(), 2)


if __name__ == '__main__':
    unittest.main()
