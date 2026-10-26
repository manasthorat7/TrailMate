"""
tests/test_razorpay_payments.py
-------------------------------
Automated tests for Razorpay test-mode payments using mocked API calls.

Covers form and JSON callbacks, invalid signatures, duplicate callbacks,
late callbacks, slot accounting, legacy bookings, and staff/admin display.
"""
import hashlib
import hmac
import os
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from app import create_app
from database import db
from models import User, Trek, Booking
from routes.user import _expire_pending_bookings


SECRET = 'mock_secret'


class RazorpayPaymentTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(test_config={
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
            'WTF_CSRF_ENABLED': False,
            'SECRET_KEY': 'test-secret-key-for-testing'
        })
        self.client = self.app.test_client()
        os.environ['RAZORPAY_KEY_ID'] = 'rzp_test_mock'
        os.environ['RAZORPAY_KEY_SECRET'] = SECRET
        os.environ['PAYMENT_CURRENCY'] = 'INR'

        with self.app.app_context():
            db.create_all()
            user = User(
                name='Test User', email='user@test.com',
                password=generate_password_hash('pass123'),
                role='user', status='Active'
            )
            db.session.add(user)
            trek = Trek(
                trek_name='Test Trek',
                location='Himalayas',
                difficulty='Moderate',
                duration='3 Days',
                available_slots=2,
                start_date=date.today() + timedelta(days=5),
                end_date=date.today() + timedelta(days=7),
                status='Open'
            )
            db.session.add(trek)
            db.session.commit()
            self.user_id = user.id
            self.trek_id = trek.trek_id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
        for key in ('RAZORPAY_KEY_ID', 'RAZORPAY_KEY_SECRET', 'PAYMENT_CURRENCY'):
            os.environ.pop(key, None)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def login_user(self, email='user@test.com', password='pass123'):
        return self.client.post(
            '/login', data={'email': email, 'password': password},
            follow_redirects=True
        )

    def _book(self, order_id='order_123'):
        with patch('razorpay_service.create_order', return_value={
            'id': order_id, 'amount': 100000, 'currency': 'INR'
        }):
            return self.client.post(
                f'/user/treks/{self.trek_id}/book',
                follow_redirects=True
            )

    @staticmethod
    def _signature(order_id, payment_id, secret=SECRET):
        msg = f'{order_id}|{payment_id}'.encode('utf-8')
        return hmac.new(secret.encode('utf-8'), msg, hashlib.sha256).hexdigest()

    def _booking(self, order_id):
        return Booking.query.filter_by(razorpay_order_id=order_id).first()

    def _make_user(self, name, email, role='user', status='Active'):
        user = User(
            name=name, email=email,
            password=generate_password_hash('pass123'),
            role=role, status=status
        )
        db.session.add(user)
        db.session.flush()
        return user

    # ------------------------------------------------------------------
    # Order creation / reservation
    # ------------------------------------------------------------------
    def test_checkout_page_renders_booking_details_and_formatted_amount(self):
        """Checkout page shows trek details, formatted amount, and payment action."""
        self.login_user()
        self._book('order_checkout')

        with self.app.app_context():
            booking = self._booking('order_checkout')
            checkout_url = f'/user/checkout/{booking.booking_id}'
            trek = db.session.get(Trek, booking.trek_id)
            trek.image_url = 'https://res.cloudinary.com/testcloud/checkout.jpg'
            db.session.commit()

        resp = self.client.get(checkout_url)

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Test Trek', resp.data)
        self.assertIn(b'Himalayas', resp.data)
        self.assertIn(b'INR 1000.00', resp.data)
        self.assertIn(b'Pay Securely', resp.data)
        self.assertIn(b'rzp-button', resp.data)
        self.assertIn(b'order_checkout', resp.data)
        self.assertIn(b'https://res.cloudinary.com/testcloud/checkout.jpg', resp.data)
        self.assertIn(b'Razorpay Test Mode', resp.data)
        self.assertIn(b'No real charge will be made.', resp.data)
        self.assertNotIn(b'INR 1000.0\n', resp.data)

    def test_order_creation_reserves_slot(self):
        self.login_user()
        resp = self._book('order_123')
        self.assertEqual(resp.status_code, 200)
        with self.app.app_context():
            booking = Booking.query.filter_by(
                user_id=self.user_id, trek_id=self.trek_id
            ).first()
            self.assertIsNotNone(booking)
            self.assertEqual(booking.payment_status, 'Pending')
            self.assertEqual(booking.razorpay_order_id, 'order_123')
            self.assertNotEqual(booking.payment_status, 'Verified')
            trek = db.session.get(Trek, self.trek_id)
            self.assertEqual(trek.available_slots, 1)  # reserved

    # ------------------------------------------------------------------
    # Successful verification
    # ------------------------------------------------------------------
    def test_valid_form_signature_confirms_booking(self):
        self.login_user()
        self._book('order_form')
        sig = self._signature('order_form', 'pay_form')

        resp = self.client.post('/user/payment/verify', data={
            'razorpay_order_id': 'order_form',
            'razorpay_payment_id': 'pay_form',
            'razorpay_signature': sig,
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            booking = self._booking('order_form')
            self.assertEqual(booking.payment_status, 'Verified')
            self.assertEqual(booking.status, 'Booked')
            trek = db.session.get(Trek, self.trek_id)
            self.assertEqual(trek.available_slots, 1)

    def test_valid_json_signature_confirms_booking(self):
        self.login_user()
        self._book('order_json')
        sig = self._signature('order_json', 'pay_json')

        resp = self.client.post('/user/payment/verify', json={
            'razorpay_order_id': 'order_json',
            'razorpay_payment_id': 'pay_json',
            'razorpay_signature': sig,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['status'], 'success')

        with self.app.app_context():
            booking = self._booking('order_json')
            self.assertEqual(booking.payment_status, 'Verified')
            self.assertEqual(booking.status, 'Booked')

    # ------------------------------------------------------------------
    # Invalid / failed attempts
    # ------------------------------------------------------------------
    def test_invalid_signature_marks_failed_but_keeps_slot_reserved(self):
        self.login_user()
        self._book('order_bad')

        resp = self.client.post('/user/payment/verify', data={
            'razorpay_order_id': 'order_bad',
            'razorpay_payment_id': 'pay_bad',
            'razorpay_signature': 'badsig',
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            booking = self._booking('order_bad')
            self.assertEqual(booking.payment_status, 'Failed')
            self.assertEqual(booking.status, 'Booked')
            trek = db.session.get(Trek, self.trek_id)
            # The slot is held until expiry; a client failure message alone
            # is not proof that no payment was captured.
            self.assertEqual(trek.available_slots, 1)

    def test_failed_booking_blocks_duplicate_reservation(self):
        self.login_user()
        self._book('order_retry')
        with self.app.app_context():
            existing_order_id = self._booking('order_retry').razorpay_order_id
            self.assertEqual(existing_order_id, 'order_retry')
        self.client.post('/user/payment/verify', data={
            'razorpay_order_id': 'order_retry',
            'razorpay_payment_id': 'pay_retry',
            'razorpay_signature': 'badsig',
        }, follow_redirects=True)

        self._book('order_should_not_exist')
        with self.app.app_context():
            bookings = Booking.query.filter_by(
                user_id=self.user_id, trek_id=self.trek_id
            ).all()
            self.assertEqual(len(bookings), 1)
            trek = db.session.get(Trek, self.trek_id)
            self.assertEqual(trek.available_slots, 1)

    def test_unverified_booking_is_displayed_as_reserved(self):
        self.login_user()
        self._book('order_display')

        resp = self.client.get('/user/my-bookings')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Reserved', resp.data)
        self.assertIn(b'Payment: Pending', resp.data)

        with self.app.app_context():
            booking = self._booking('order_display')
            self.assertNotEqual(booking.payment_status, 'Verified')

    # ------------------------------------------------------------------
    # Duplicate and late callbacks
    # ------------------------------------------------------------------
    def test_duplicate_callback_is_idempotent_and_does_not_release_slot(self):
        self.login_user()
        self._book('order_dup')
        sig = self._signature('order_dup', 'pay_dup')

        payload = {
            'razorpay_order_id': 'order_dup',
            'razorpay_payment_id': 'pay_dup',
            'razorpay_signature': sig,
        }
        self.client.post('/user/payment/verify', data=payload)
        resp = self.client.post(
            '/user/payment/verify', data=payload, follow_redirects=True
        )
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            booking = self._booking('order_dup')
            self.assertEqual(booking.payment_status, 'Verified')
            self.assertEqual(booking.status, 'Booked')
            trek = db.session.get(Trek, self.trek_id)
            self.assertEqual(trek.available_slots, 1)
            self.assertEqual(
                Booking.query.filter_by(razorpay_order_id='order_dup').count(), 1
            )

    def test_late_callback_after_cancel_does_not_resurrect_booking(self):
        self.login_user()
        self._book('order_cancel')
        with self.app.app_context():
            booking_id = self._booking('order_cancel').booking_id

        self.client.post(
            f'/user/bookings/{booking_id}/cancel', follow_redirects=True
        )

        sig = self._signature('order_cancel', 'pay_cancel')
        resp = self.client.post('/user/payment/verify', data={
            'razorpay_order_id': 'order_cancel',
            'razorpay_payment_id': 'pay_cancel',
            'razorpay_signature': sig,
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            booking = self._booking('order_cancel')
            self.assertEqual(booking.status, 'Cancelled')
            self.assertNotEqual(booking.payment_status, 'Verified')
            trek = db.session.get(Trek, self.trek_id)
            self.assertEqual(trek.available_slots, 2)  # released exactly once

    def test_late_callback_after_expiry_does_not_resurrect_booking(self):
        self.login_user()
        self._book('order_expire')
        with self.app.app_context():
            booking = self._booking('order_expire')
            booking.booking_date = datetime.utcnow() - timedelta(minutes=30)
            db.session.commit()

        with self.app.app_context():
            _expire_pending_bookings()

        sig = self._signature('order_expire', 'pay_expire')
        self.client.post('/user/payment/verify', data={
            'razorpay_order_id': 'order_expire',
            'razorpay_payment_id': 'pay_expire',
            'razorpay_signature': sig,
        }, follow_redirects=True)

        with self.app.app_context():
            booking = self._booking('order_expire')
            self.assertEqual(booking.status, 'Cancelled')
            self.assertEqual(booking.payment_status, 'Failed')
            trek = db.session.get(Trek, self.trek_id)
            self.assertEqual(trek.available_slots, 2)

    # ------------------------------------------------------------------
    # Expiry / slot accounting
    # ------------------------------------------------------------------
    def test_expired_booking_releases_slot_exactly_once(self):
        self.login_user()
        self._book('order_once')
        with self.app.app_context():
            booking = self._booking('order_once')
            booking.booking_date = datetime.utcnow() - timedelta(minutes=30)
            db.session.commit()

        with self.app.app_context():
            _expire_pending_bookings()
            _expire_pending_bookings()  # must be a no-op
            booking = self._booking('order_once')
            self.assertEqual(booking.status, 'Cancelled')
            self.assertEqual(booking.payment_status, 'Failed')
            trek = db.session.get(Trek, self.trek_id)
            self.assertEqual(trek.available_slots, 2)

    def test_expired_failed_booking_releases_slot_exactly_once(self):
        self.login_user()
        self._book('order_failed_expire')
        self.client.post('/user/payment/verify', data={
            'razorpay_order_id': 'order_failed_expire',
            'razorpay_payment_id': 'pay_failed',
            'razorpay_signature': 'badsig',
        }, follow_redirects=True)

        with self.app.app_context():
            booking = self._booking('order_failed_expire')
            self.assertEqual(booking.payment_status, 'Failed')
            booking.booking_date = datetime.utcnow() - timedelta(minutes=30)
            db.session.commit()

        with self.app.app_context():
            _expire_pending_bookings()
            _expire_pending_bookings()
            booking = self._booking('order_failed_expire')
            self.assertEqual(booking.status, 'Cancelled')
            trek = db.session.get(Trek, self.trek_id)
            self.assertEqual(trek.available_slots, 2)

    def test_legacy_completed_and_legacy_bookings_are_not_expired(self):
        with self.app.app_context():
            completed = Booking(
                user_id=self.user_id, trek_id=self.trek_id,
                status='Completed', payment_status='Unpaid',
                booking_date=datetime.utcnow() - timedelta(days=10),
            )
            legacy_booked = Booking(
                user_id=self.user_id, trek_id=self.trek_id,
                status='Booked', payment_status='Legacy',
                booking_date=datetime.utcnow() - timedelta(days=10),
            )
            db.session.add_all([completed, legacy_booked])
            db.session.commit()
            trek = db.session.get(Trek, self.trek_id)
            slots_before = trek.available_slots

            _expire_pending_bookings()

            completed = db.session.get(Booking, completed.booking_id)
            legacy_booked = db.session.get(Booking, legacy_booked.booking_id)
            trek = db.session.get(Trek, self.trek_id)
            self.assertEqual(completed.status, 'Completed')
            self.assertEqual(completed.payment_status, 'Unpaid')
            self.assertEqual(legacy_booked.status, 'Booked')
            self.assertEqual(legacy_booked.payment_status, 'Legacy')
            self.assertEqual(trek.available_slots, slots_before)

    # ------------------------------------------------------------------
    # Staff / admin presentation
    # ------------------------------------------------------------------
    def test_staff_participants_exclude_pending_and_failed_payments(self):
        with self.app.app_context():
            staff = self._make_user('Guide', 'guide@test.com', role='staff')
            trek = db.session.get(Trek, self.trek_id)
            trek.assigned_staff_id = staff.id

            pending_user = self._make_user('Pending Trekker', 'pending@test.com')
            failed_user = self._make_user('Failed Trekker', 'failed@test.com')
            verified_user = self._make_user('Verified Trekker', 'verified@test.com')
            legacy_user = self._make_user('Legacy Trekker', 'legacy@test.com')

            db.session.add_all([
                Booking(user_id=pending_user.id, trek_id=self.trek_id,
                        status='Booked', payment_status='Pending'),
                Booking(user_id=failed_user.id, trek_id=self.trek_id,
                        status='Booked', payment_status='Failed'),
                Booking(user_id=verified_user.id, trek_id=self.trek_id,
                        status='Booked', payment_status='Verified'),
                Booking(user_id=legacy_user.id, trek_id=self.trek_id,
                        status='Booked', payment_status='Legacy'),
            ])
            db.session.commit()

        self.client.get('/logout')
        self.login_user('guide@test.com', 'pass123')

        resp = self.client.get(f'/staff/treks/{self.trek_id}/participants')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'verified@test.com', resp.data)
        self.assertIn(b'legacy@test.com', resp.data)
        self.assertNotIn(b'pending@test.com', resp.data)
        self.assertNotIn(b'failed@test.com', resp.data)

        dashboard = self.client.get('/staff/dashboard')
        self.assertIn(b'Verified Trekker', dashboard.data)
        self.assertNotIn(b'Pending Trekker', dashboard.data)

    def test_admin_booking_ledger_labels_unverified_as_reserved(self):
        self.login_user()
        self._book('order_admin_display')

        with self.app.app_context():
            self._make_user('Admin', 'admin@test.com', role='admin')
            db.session.commit()

        self.client.get('/logout')
        self.login_user('admin@test.com', 'pass123')

        resp = self.client.get('/admin/bookings')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Reserved', resp.data)
        self.assertIn(b'Payment: Pending', resp.data)

    # ------------------------------------------------------------------
    # JSON validation
    # ------------------------------------------------------------------
    def test_json_verification_rejects_missing_fields(self):
        self.login_user()
        resp = self.client.post('/user/payment/verify', json={})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()['status'], 'error')


if __name__ == '__main__':
    unittest.main()
