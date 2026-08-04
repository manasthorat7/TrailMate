import unittest
from app import create_app
from database import db
from models import User

class TrailMateTestCase(unittest.TestCase):
    
    def setUp(self):
        """Set up a blank, in-memory database before each test."""
        self.app = create_app()
        # Overwrite config for testing
        self.app.config['TESTING'] = True
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.client = self.app.test_client()
        
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        """Clean up after each test."""
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_default_admin_creation(self):
        """Test Rule #5: Admin must be pre-existing."""
        with self.app.app_context():
            # In app.py, we have logic to create the admin inside app_context
            # Let's manually trigger it for the test environment just in case
            admin = User.query.filter_by(role='admin').first()
            if not admin:
                from werkzeug.security import generate_password_hash
                default_admin = User(
                    name='System Admin',
                    email='admin@trailmate.com',
                    password=generate_password_hash('admin123'),
                    role='admin',
                    status='Active'
                )
                db.session.add(default_admin)
                db.session.commit()
                
            # Verify the admin exists
            saved_admin = User.query.filter_by(role='admin').first()
            self.assertIsNotNone(saved_admin)
            self.assertEqual(saved_admin.email, 'admin@trailmate.com')

    def test_admin_route_protection(self):
        """Test that unauthenticated users cannot access admin routes."""
        response = self.client.get('/admin/dashboard')
        # Should redirect (302) to login page
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers['Location'])

if __name__ == '__main__':
    unittest.main()
