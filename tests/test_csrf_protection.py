"""
tests/test_csrf_protection.py
-----------------------------
Regression tests for CSRF protection with Flask-WTF enabled.

These tests deliberately do NOT set WTF_CSRF_ENABLED=False. They cover
login, registration, representative staff/admin POST actions, rejected
requests without a token, and the JSON payment-verification header path.
"""
import hashlib
import hmac
import os
import re
import unittest
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from app import create_app
from database import db
from models import User, Trek, Booking


PASSWORD = 'password123'
RAZORPAY_SECRET = 'csrf-test-razorpay-secret'

CSRF_INPUT_RE = re.compile(rb'name="csrf_token"\s+value="([^"]+)"')
CSRF_META_RE = re.compile(rb'name="csrf-token"\s+content="([^"]+)"')


class CSRFProtectionTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(test_config={
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
            'SECRET_KEY': 'csrf-test-secret-key',
            # Intentionally no WTF_CSRF_ENABLED override.
        })
        self.client = self.app.test_client()
        os.environ['RAZORPAY_KEY_ID'] = 'rzp_test_csrf'
        os.environ['RAZORPAY_KEY_SECRET'] = RAZORPAY_SECRET

        with self.app.app_context():
            db.create_all()

            admin = User(
                name='Admin', email='admin@test.com',
                password=generate_password_hash(PASSWORD),
                role='admin', status='Active'
            )
            staff = User(
                name='Guide', email='staff@test.com',
                password=generate_password_hash(PASSWORD),
                role='staff', status='Active'
            )
            pending_staff = User(
                name='Pending Guide', email='pending@test.com',
                password=generate_password_hash(PASSWORD),
                role='staff', status='Pending'
            )
            user = User(
                name='Trekker', email='user@test.com',
                password=generate_password_hash(PASSWORD),
                role='user', status='Active'
            )
            db.session.add_all([admin, staff, pending_staff, user])
            db.session.flush()

            trek = Trek(
                trek_name='CSRF Trek',
                location='Test Range',
                difficulty='Easy',
                duration='2 Days',
                available_slots=10,
                assigned_staff_id=staff.id,
                start_date=date.today() + timedelta(days=5),
                end_date=date.today() + timedelta(days=7),
                status='Open'
            )
            db.session.add(trek)
            db.session.commit()

            self.admin_id = admin.id
            self.staff_id = staff.id
            self.pending_staff_id = pending_staff.id
            self.user_id = user.id
            self.trek_id = trek.trek_id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
        os.environ.pop('RAZORPAY_KEY_ID', None)
        os.environ.pop('RAZORPAY_KEY_SECRET', None)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _csrf(self, path):
        resp = self.client.get(path)
        self.assertEqual(resp.status_code, 200, f'GET {path} failed')
        match = CSRF_INPUT_RE.search(resp.data) or CSRF_META_RE.search(resp.data)
        self.assertIsNotNone(match, f'No CSRF token rendered on {path}')
        return match.group(1).decode('utf-8')

    def _login(self, email):
        token = self._csrf('/login')
        resp = self.client.post('/login', data={
            'email': email,
            'password': PASSWORD,
            'csrf_token': token,
        })
        self.assertEqual(resp.status_code, 302, f'Login failed for {email}')
        return resp

    @staticmethod
    def _signature(order_id, payment_id):
        message = f'{order_id}|{payment_id}'.encode('utf-8')
        return hmac.new(
            RAZORPAY_SECRET.encode('utf-8'), message, hashlib.sha256
        ).hexdigest()

    # ------------------------------------------------------------------
    # Login / registration
    # ------------------------------------------------------------------
    def test_login_rejects_missing_csrf_token(self):
        resp = self.client.post('/login', data={
            'email': 'user@test.com',
            'password': PASSWORD,
        })
        self.assertEqual(resp.status_code, 400)

    def test_login_accepts_valid_csrf_token(self):
        resp = self._login('user@test.com')
        self.assertTrue(resp.headers['Location'].endswith('/user/dashboard'))

    def test_registration_rejects_missing_csrf_token(self):
        resp = self.client.post('/register', data={
            'name': 'No Token',
            'email': 'no-token@test.com',
            'password': PASSWORD,
            'role': 'user',
        })
        self.assertEqual(resp.status_code, 400)
        with self.app.app_context():
            self.assertIsNone(User.query.filter_by(email='no-token@test.com').first())

    def test_registration_accepts_valid_csrf_token(self):
        token = self._csrf('/register')
        resp = self.client.post('/register', data={
            'name': 'New Trekker',
            'email': 'new-trekker@test.com',
            'password': PASSWORD,
            'role': 'user',
            'csrf_token': token,
        })
        self.assertEqual(resp.status_code, 302)
        with self.app.app_context():
            created = User.query.filter_by(email='new-trekker@test.com').first()
            self.assertIsNotNone(created)
            self.assertEqual(created.role, 'user')
            self.assertEqual(created.status, 'Active')

    # ------------------------------------------------------------------
    # Admin trek forms render CSRF as a hidden input
    # ------------------------------------------------------------------
    def test_admin_add_trek_renders_hidden_csrf_input(self):
        self._login('admin@test.com')
        resp = self.client.get('/admin/treks/add')

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'<input type="hidden" name="csrf_token"', resp.data)
        self.assertNotIn(b'&lt;input type="hidden" name="csrf_token"', resp.data)

    def test_admin_edit_trek_renders_hidden_csrf_input(self):
        self._login('admin@test.com')
        resp = self.client.get(f'/admin/treks/{self.trek_id}/edit')

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'<input type="hidden" name="csrf_token"', resp.data)
        self.assertNotIn(b'&lt;input type="hidden" name="csrf_token"', resp.data)

    # ------------------------------------------------------------------
    # Staff POST actions
    # ------------------------------------------------------------------
    def test_staff_update_rejects_missing_csrf_token(self):
        self._login('staff@test.com')
        resp = self.client.post(
            f'/staff/treks/{self.trek_id}/update',
            data={'status': 'Started', 'available_slots': '5'}
        )
        self.assertEqual(resp.status_code, 400)
        with self.app.app_context():
            trek = db.session.get(Trek, self.trek_id)
            self.assertEqual(trek.status, 'Open')
            self.assertEqual(trek.available_slots, 10)

    def test_staff_update_accepts_valid_csrf_token(self):
        self._login('staff@test.com')
        token = self._csrf('/staff/assigned-treks')
        resp = self.client.post(
            f'/staff/treks/{self.trek_id}/update',
            data={
                'status': 'Started',
                'available_slots': '5',
                'csrf_token': token,
            }
        )
        self.assertEqual(resp.status_code, 302)
        with self.app.app_context():
            trek = db.session.get(Trek, self.trek_id)
            self.assertEqual(trek.status, 'Started')
            self.assertEqual(trek.available_slots, 5)

    def test_staff_cancel_requires_and_accepts_csrf_token(self):
        with self.app.app_context():
            booking = Booking(
                user_id=self.user_id,
                trek_id=self.trek_id,
                status='Booked',
                payment_status='Verified',
            )
            db.session.add(booking)
            trek = db.session.get(Trek, self.trek_id)
            trek.available_slots = 9
            db.session.commit()
            booking_id = booking.booking_id

        self._login('staff@test.com')

        resp = self.client.post(f'/staff/bookings/{booking_id}/cancel')
        self.assertEqual(resp.status_code, 400)
        with self.app.app_context():
            booking = db.session.get(Booking, booking_id)
            self.assertEqual(booking.status, 'Booked')

        token = self._csrf(f'/staff/treks/{self.trek_id}/participants')
        resp = self.client.post(
            f'/staff/bookings/{booking_id}/cancel',
            data={'csrf_token': token}
        )
        self.assertEqual(resp.status_code, 302)
        with self.app.app_context():
            booking = db.session.get(Booking, booking_id)
            trek = db.session.get(Trek, self.trek_id)
            self.assertEqual(booking.status, 'Cancelled')
            self.assertEqual(trek.available_slots, 10)

    # ------------------------------------------------------------------
    # Admin POST actions
    # ------------------------------------------------------------------
    def test_admin_action_rejects_missing_csrf_token(self):
        self._login('admin@test.com')
        resp = self.client.post('/admin/staff', data={
            'staff_id': str(self.pending_staff_id),
            'action': 'approve',
        })
        self.assertEqual(resp.status_code, 400)
        with self.app.app_context():
            pending = db.session.get(User, self.pending_staff_id)
            self.assertEqual(pending.status, 'Pending')

    def test_admin_action_accepts_valid_csrf_token(self):
        self._login('admin@test.com')
        token = self._csrf('/admin/staff')
        resp = self.client.post('/admin/staff', data={
            'staff_id': str(self.pending_staff_id),
            'action': 'approve',
            'csrf_token': token,
        })
        # This route renders the refreshed staff list after a successful POST.
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Pending Guide', resp.data)
        with self.app.app_context():
            approved = db.session.get(User, self.pending_staff_id)
            self.assertEqual(approved.status, 'Active')

    def test_admin_user_status_requires_and_accepts_csrf_token(self):
        self._login('admin@test.com')

        resp = self.client.post(
            f'/admin/users/{self.user_id}/status',
            data={'action': 'deactivate'}
        )
        self.assertEqual(resp.status_code, 400)
        with self.app.app_context():
            self.assertEqual(db.session.get(User, self.user_id).status, 'Active')

        token = self._csrf('/admin/users')
        resp = self.client.post(
            f'/admin/users/{self.user_id}/status',
            data={'action': 'deactivate', 'csrf_token': token}
        )
        self.assertEqual(resp.status_code, 302)
        with self.app.app_context():
            self.assertEqual(db.session.get(User, self.user_id).status, 'Inactive')

    def test_admin_delete_trek_requires_and_accepts_csrf_token(self):
        self._login('admin@test.com')

        resp = self.client.post(f'/admin/treks/{self.trek_id}/delete')
        self.assertEqual(resp.status_code, 400)
        with self.app.app_context():
            self.assertIsNotNone(db.session.get(Trek, self.trek_id))

        token = self._csrf('/admin/treks')
        resp = self.client.post(
            f'/admin/treks/{self.trek_id}/delete',
            data={'csrf_token': token}
        )
        self.assertEqual(resp.status_code, 302)
        with self.app.app_context():
            self.assertIsNone(db.session.get(Trek, self.trek_id))

    # ------------------------------------------------------------------
    # User POST actions
    # ------------------------------------------------------------------
    def test_profile_update_requires_and_accepts_csrf_token(self):
        self._login('user@test.com')

        resp = self.client.post('/user/profile', data={'name': 'Changed Without Token'})
        self.assertEqual(resp.status_code, 400)
        with self.app.app_context():
            self.assertEqual(db.session.get(User, self.user_id).name, 'Trekker')

        token = self._csrf('/user/profile')
        resp = self.client.post('/user/profile', data={
            'name': 'Updated Trekker',
            'contact_details': '+91 90000 00000',
            'csrf_token': token,
        })
        self.assertEqual(resp.status_code, 302)
        with self.app.app_context():
            updated = db.session.get(User, self.user_id)
            self.assertEqual(updated.name, 'Updated Trekker')
            self.assertEqual(updated.contact_details, '+91 90000 00000')

    # ------------------------------------------------------------------
    # Admin staff contact details rendering
    # ------------------------------------------------------------------
    def test_admin_staff_contact_details_render_correctly(self):
        self._login('admin@test.com')

        with self.app.app_context():
            staff = User.query.filter_by(email='staff@test.com').first()
            staff.contact_details = '+91 98765 43210'
            db.session.commit()

        resp = self.client.get('/admin/staff')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'+91 98765 43210', resp.data)
        self.assertNotIn(b'&mdash;', resp.data)

        with self.app.app_context():
            staff = User.query.filter_by(email='staff@test.com').first()
            staff.contact_details = None
            db.session.commit()

        resp = self.client.get('/admin/staff')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('—'.encode('utf-8'), resp.data)
        self.assertNotIn(b'&mdash;', resp.data)

    # ------------------------------------------------------------------
    # JSON payment verification
    # ------------------------------------------------------------------
    def test_json_payment_verification_requires_csrf_header(self):
        order_id = 'order_csrf_json'
        payment_id = 'pay_csrf_json'
        with self.app.app_context():
            booking = Booking(
                user_id=self.user_id,
                trek_id=self.trek_id,
                status='Booked',
                payment_status='Pending',
                razorpay_order_id=order_id,
            )
            db.session.add(booking)
            db.session.commit()
            booking_id = booking.booking_id

        self._login('user@test.com')
        token = self._csrf('/user/my-bookings')
        payload = {
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': self._signature(order_id, payment_id),
        }

        resp = self.client.post('/user/payment/verify', json=payload)
        self.assertEqual(resp.status_code, 400)
        with self.app.app_context():
            booking = db.session.get(Booking, booking_id)
            self.assertEqual(booking.payment_status, 'Pending')

        resp = self.client.post(
            '/user/payment/verify',
            json=payload,
            headers={'X-CSRFToken': token},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['status'], 'success')
        with self.app.app_context():
            booking = db.session.get(Booking, booking_id)
            self.assertEqual(booking.payment_status, 'Verified')


if __name__ == '__main__':
    unittest.main()
