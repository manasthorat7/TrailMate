import re
import unittest
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from app import create_app
from database import db
from models import User, Trek


class AdminTrekEditTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(test_config={
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
            'SECRET_KEY': 'admin-edit-test-secret',
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()
            admin = User(
                name='Admin', email='admin@test.com',
                password=generate_password_hash('password123'),
                role='admin', status='Active'
            )
            db.session.add(admin)
            db.session.commit()
            self.admin_id = admin.id

            trek = Trek(
                trek_name='Old Trek',
                location='Old Location',
                difficulty='Moderate',
                duration='4 Days',
                available_slots=10,
                start_date=date.today() + timedelta(days=5),
                end_date=date.today() + timedelta(days=9),
                status='Open',
                price=1000.00,
                image_url='https://res.cloudinary.com/test/old.jpg',
                image_public_id='old_pid',
            )
            db.session.add(trek)
            db.session.commit()
            self.trek_id = trek.trek_id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def _csrf(self, path):
        resp = self.client.get(path)
        self.assertEqual(resp.status_code, 200)
        import re
        match = re.search(rb'name="csrf_token"\s+value="([^"]+)"', resp.data)
        self.assertIsNotNone(match)
        return match.group(1).decode('utf-8')

    def _login(self):
        token = self._csrf('/login')
        resp = self.client.post('/login', data={
            'email': 'admin@test.com',
            'password': 'password123',
            'csrf_token': token,
        })
        self.assertEqual(resp.status_code, 302)

    def test_edit_trek_updates_values_and_preserves_image(self):
        self._login()
        token = self._csrf(f'/admin/treks/{self.trek_id}/edit')
        resp = self.client.post(f'/admin/treks/{self.trek_id}/edit', data={
            'csrf_token': token,
            'trek_name': 'Updated Trek',
            'location': 'New Location',
            'difficulty': 'Hard',
            'duration': '5 Days',
            'available_slots': '8',
            'price': '2499.50',
            'status': 'Open',
            'start_date': (date.today() + timedelta(days=5)).isoformat(),
            'end_date': (date.today() + timedelta(days=9)).isoformat(),
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Trek updated successfully', resp.data)

        with self.app.app_context():
            trek = db.session.get(Trek, self.trek_id)
            self.assertEqual(trek.trek_name, 'Updated Trek')
            self.assertEqual(trek.location, 'New Location')
            self.assertEqual(trek.difficulty, 'Hard')
            self.assertEqual(trek.duration, '5 Days')
            self.assertEqual(trek.available_slots, 8)
            self.assertEqual(float(trek.price), 2499.50)
            self.assertEqual(trek.image_url, 'https://res.cloudinary.com/test/old.jpg')
            self.assertEqual(trek.image_public_id, 'old_pid')

    def test_edit_trek_rejects_invalid_price(self):
        self._login()
        token = self._csrf(f'/admin/treks/{self.trek_id}/edit')
        resp = self.client.post(f'/admin/treks/{self.trek_id}/edit', data={
            'csrf_token': token,
            'trek_name': 'Updated Trek',
            'location': 'New Location',
            'difficulty': 'Hard',
            'duration': '5 Days',
            'available_slots': '8',
            'price': '0',
            'status': 'Open',
            'start_date': (date.today() + timedelta(days=5)).isoformat(),
            'end_date': (date.today() + timedelta(days=9)).isoformat(),
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'greater than zero', resp.data)
        with self.app.app_context():
            trek = db.session.get(Trek, self.trek_id)
            self.assertEqual(trek.trek_name, 'Old Trek')


if __name__ == '__main__':
    unittest.main()
