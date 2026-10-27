"""
tests/test_public_discovery.py
------------------------------
Isolated tests for public trek discovery and protected booking.

Every test uses an in-memory SQLite database. No real database file is opened.
"""
import unittest
from datetime import date, timedelta
from urllib.parse import unquote

from werkzeug.security import generate_password_hash

from app import create_app
from database import db
from models import User, Trek, Booking


PASSWORD = 'pass123'


class PublicDiscoveryTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(test_config={
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
            'WTF_CSRF_ENABLED': False,
            'SECRET_KEY': 'public-discovery-test-secret',
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()

            user = User(
                name='Public Trekker',
                email='trekker@test.com',
                password=generate_password_hash(PASSWORD),
                role='user',
                status='Active',
            )
            db.session.add(user)
            db.session.flush()

            open_trek = Trek(
                trek_name='Public Alpine Trek',
                location='Solang Valley',
                difficulty='Moderate',
                duration='4 Days',
                available_slots=8,
                start_date=date.today() + timedelta(days=10),
                end_date=date.today() + timedelta(days=13),
                status='Open', price=1000.00,
            )
            completed_trek = Trek(
                trek_name='Old Completed Trek',
                location='Past Valley',
                difficulty='Easy',
                duration='2 Days',
                available_slots=5,
                start_date=date.today() - timedelta(days=6),
                end_date=date.today() - timedelta(days=4),
                status='Completed',
            )
            db.session.add_all([open_trek, completed_trek])
            db.session.commit()

            self.open_trek_id = open_trek.trek_id
            self.completed_trek_id = completed_trek.trek_id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    # ------------------------------------------------------------------
    # Public catalogue and details
    # ------------------------------------------------------------------
    def test_public_catalogue_is_accessible_without_login(self):
        resp = self.client.get('/user/dashboard')

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Public Alpine Trek', resp.data)
        self.assertIn(b'Solang Valley', resp.data)
        self.assertIn(b'Moderate', resp.data)
        self.assertIn(b'4 Days', resp.data)
        self.assertIn(b'8 slots open', resp.data)
        # The public catalogue only lists Open treks.
        self.assertNotIn(b'Old Completed Trek', resp.data)

    def test_public_details_are_accessible_without_login(self):
        resp = self.client.get(f'/user/treks/{self.open_trek_id}')

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Public Alpine Trek', resp.data)
        self.assertIn(b'Solang Valley', resp.data)
        self.assertIn(b'Expedition Overview', resp.data)
        self.assertIn(b'Safety & Logistics', resp.data)
        self.assertIn(b'Book This Trek', resp.data)
        self.assertIn(b'/login?next=', resp.data)

    def test_completed_trek_details_are_public_but_not_bookable(self):
        resp = self.client.get(f'/user/treks/{self.completed_trek_id}')

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Old Completed Trek', resp.data)
        self.assertIn(b'Booking Unavailable', resp.data)
        self.assertNotIn(b'Book This Trek', resp.data)

    # ------------------------------------------------------------------
    # Protected booking
    # ------------------------------------------------------------------
    def test_unauthenticated_booking_redirects_to_login_with_trek(self):
        resp = self.client.post(f'/user/treks/{self.open_trek_id}/book')

        self.assertEqual(resp.status_code, 302)
        location = unquote(resp.headers['Location'])
        self.assertEqual(
            location,
            f'/login?next=/user/treks/{self.open_trek_id}',
        )

        with self.app.app_context():
            self.assertEqual(Booking.query.count(), 0)
            trek = db.session.get(Trek, self.open_trek_id)
            self.assertEqual(trek.available_slots, 8)

    def test_unauthenticated_user_cannot_reach_my_bookings(self):
        resp = self.client.get('/user/my-bookings')

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            unquote(resp.headers['Location']),
            '/login?next=/user/my-bookings',
        )

    def test_login_returns_to_selected_trek(self):
        next_url = f'/user/treks/{self.open_trek_id}'

        page = self.client.get(f'/login?next={next_url}')
        self.assertIn(
            f'name="next" value="{next_url}"'.encode(),
            page.data,
        )

        resp = self.client.post('/login', data={
            'email': 'trekker@test.com',
            'password': PASSWORD,
            'next': next_url,
        })

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.headers['Location'], next_url)

    def test_registration_preserves_selected_trek(self):
        next_url = f'/user/treks/{self.open_trek_id}'

        page = self.client.get(f'/register?next={next_url}')
        self.assertEqual(page.status_code, 200)
        self.assertIn(
            f'name="next" value="{next_url}"'.encode(),
            page.data,
        )

        resp = self.client.post('/register', data={
            'name': 'New Public Trekker',
            'email': 'new-trekker@test.com',
            'password': PASSWORD,
            'role': 'user',
            'next': next_url,
        })

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            unquote(resp.headers['Location']),
            f'/login?next={next_url}',
        )
        with self.app.app_context():
            self.assertIsNotNone(
                User.query.filter_by(email='new-trekker@test.com').first()
            )

    def test_login_rejects_external_next_targets(self):
        unsafe_targets = [
            'https://evil.example/phish',
            '//evil.example/phish',
            '/\\evil.example/phish',
        ]
        for target in unsafe_targets:
            client = self.app.test_client()
            resp = client.post('/login', data={
                'email': 'trekker@test.com',
                'password': PASSWORD,
                'next': target,
            })
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(resp.headers['Location'], '/user/dashboard')

    def test_authenticated_user_cannot_book_completed_trek(self):
        login_resp = self.client.post('/login', data={
            'email': 'trekker@test.com',
            'password': PASSWORD,
        })
        self.assertEqual(login_resp.status_code, 302)

        resp = self.client.post(
            f'/user/treks/{self.completed_trek_id}/book'
        )

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp.headers['Location'],
            f'/user/treks/{self.completed_trek_id}',
        )
        with self.app.app_context():
            self.assertEqual(Booking.query.count(), 0)
            trek = db.session.get(Trek, self.completed_trek_id)
            self.assertEqual(trek.available_slots, 5)


if __name__ == '__main__':
    unittest.main()
