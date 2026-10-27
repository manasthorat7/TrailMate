"""
tests/test_session_and_ui_safety.py
-----------------------------------
Focused release-safety regressions:

- Deactivating an account invalidates an existing login session.
- Dynamic names are never interpolated directly into JavaScript confirm()
  strings; they travel through escaped HTML data attributes instead.
"""
import unittest
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from app import create_app
from database import db
from models import Booking, Trek, User


PASSWORD = 'password123'
PAYLOAD = "Evil'); alert(1);//"


class SessionAndUiSafetyTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(test_config={
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
            'WTF_CSRF_ENABLED': False,
            'SECRET_KEY': 'ui-safety-test-secret',
        })

        with self.app.app_context():
            db.create_all()

            admin = User(
                name='Admin', email='admin@test.com',
                password=generate_password_hash(PASSWORD),
                role='admin', status='Active',
            )
            staff = User(
                name='Guide', email='staff@test.com',
                password=generate_password_hash(PASSWORD),
                role='staff', status='Active',
            )
            user = User(
                name=PAYLOAD, email='user@test.com',
                password=generate_password_hash(PASSWORD),
                role='user', status='Active',
            )
            db.session.add_all([admin, staff, user])
            db.session.flush()

            trek = Trek(
                trek_name=PAYLOAD,
                location='Test Range',
                difficulty='Easy',
                duration='2 Days',
                available_slots=5,
                assigned_staff_id=staff.id,
                start_date=date.today() + timedelta(days=5),
                end_date=date.today() + timedelta(days=7),
                status='Open',
            )
            db.session.add(trek)
            db.session.flush()

            booking = Booking(
                user_id=user.id,
                trek_id=trek.trek_id,
                status='Booked',
                payment_status='Verified',
                amount=1000.0,
                currency='INR',
            )
            db.session.add(booking)
            db.session.commit()

            self.user_id = user.id
            self.trek_id = trek.trek_id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def _login(self, email):
        client = self.app.test_client()
        response = client.post('/login', data={
            'email': email,
            'password': PASSWORD,
        })
        self.assertEqual(response.status_code, 302, f'Login failed for {email}')
        return client

    def _assert_escaped_confirm(self, response):
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        # The raw JavaScript-breaking payload must never be rendered.
        self.assertNotIn(PAYLOAD, body)
        # The name is still shown, but only as escaped HTML attribute text.
        self.assertIn(
            "Evil&#39;); alert(1);//",
            body,
        )
        self.assertIn('this.dataset.confirmMessage', body)

    def test_registration_rejects_admin_role(self):
        """Public registration must not allow privilege escalation."""
        client = self.app.test_client()
        response = client.post('/register', data={
            'name': 'Attacker',
            'email': 'attacker@test.com',
            'password': PASSWORD,
            'role': 'admin',
        })

        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertIsNone(User.query.filter_by(email='attacker@test.com').first())

    def test_deactivated_user_session_is_invalidated(self):
        client = self._login('user@test.com')

        with self.app.app_context():
            user = db.session.get(User, self.user_id)
            user.status = 'Inactive'
            db.session.commit()

        response = client.get('/user/my-bookings')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers['Location'])

    def test_staff_participant_dialog_escapes_user_name(self):
        client = self._login('staff@test.com')
        response = client.get(f'/staff/treks/{self.trek_id}/participants')
        self._assert_escaped_confirm(response)

    def test_admin_trek_dialog_escapes_trek_name(self):
        client = self._login('admin@test.com')
        response = client.get('/admin/treks')
        self._assert_escaped_confirm(response)

    def test_admin_user_dialog_escapes_user_name(self):
        client = self._login('admin@test.com')
        response = client.get('/admin/users')
        self._assert_escaped_confirm(response)

    def test_user_booking_dialog_escapes_trek_name(self):
        client = self._login('user@test.com')
        response = client.get('/user/my-bookings')
        self._assert_escaped_confirm(response)


if __name__ == '__main__':
    unittest.main()
