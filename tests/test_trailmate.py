"""
Automated Test Suite for TrailMate Trekking Management Application.
Tests production safety, secrets validation, explicit database initialization,
safe administrator provisioning, password hashing, role authorization, and workflows.
"""

import os
import unittest
from datetime import date, timedelta
from unittest.mock import patch
from werkzeug.security import check_password_hash, generate_password_hash

from app import create_app, init_db, normalize_database_url
from database import db
from models import User, Trek, Booking


class TrailMateTestCase(unittest.TestCase):
    def setUp(self):
        # Create an in-memory SQLite database for isolated test execution
        self.app = create_app(test_config={
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
            'WTF_CSRF_ENABLED': False,
            'SECRET_KEY': 'test-secret-key-for-testing'
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    # ---------------------------------------------------------
    # 1. Production Secrets & Insecure Defaults Validation
    # ---------------------------------------------------------

    def test_production_rejects_missing_secret_key(self):
        """Verify production startup fails when SECRET_KEY is not configured."""
        os.environ['ENV'] = 'production'
        old_key = os.environ.pop('SECRET_KEY', None)
        try:
            with self.assertRaises(ValueError) as ctx:
                create_app(test_config={'TESTING': False, 'ENV': 'production', 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'})
            self.assertIn("SECRET_KEY", str(ctx.exception))
        finally:
            os.environ.pop('ENV', None)
            if old_key:
                os.environ['SECRET_KEY'] = old_key

    def test_production_rejects_placeholder_secret_key(self):
        """Verify production startup fails if SECRET_KEY is a known placeholder."""
        placeholders = [
            'trailmate-secret-key-123',
            'replace-with-a-secure-random-secret-key',
            'change-this-in-production-to-a-secure-random-key',
            'secret',
            'dev'
        ]
        for placeholder in placeholders:
            os.environ['ENV'] = 'production'
            os.environ['SECRET_KEY'] = placeholder
            try:
                with self.assertRaises(ValueError) as ctx:
                    create_app(test_config={'TESTING': False, 'ENV': 'production', 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'})
                self.assertIn("SECRET_KEY", str(ctx.exception))
            finally:
                os.environ.pop('ENV', None)
                os.environ.pop('SECRET_KEY', None)

    def test_production_accepts_strong_secret_key(self):
        """Verify production startup succeeds when a strong, explicit SECRET_KEY is provided."""
        os.environ['ENV'] = 'production'
        os.environ['SECRET_KEY'] = 'x89Fq2!vN$1z90LaQwe9876543210zyxwvutsrq'
        try:
            prod_app = create_app(test_config={
                'TESTING': False,
                'ENV': 'production',
                'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'
            })
            self.assertEqual(prod_app.config['SECRET_KEY'], 'x89Fq2!vN$1z90LaQwe9876543210zyxwvutsrq')
        finally:
            os.environ.pop('ENV', None)
            os.environ.pop('SECRET_KEY', None)

    def test_development_allows_default_secret_key(self):
        """Verify development mode retains convenient fallback SECRET_KEY when unset."""
        os.environ['FLASK_ENV'] = 'development'
        old_key = os.environ.pop('SECRET_KEY', None)
        try:
            dev_app = create_app(test_config={
                'TESTING': False,
                'FLASK_ENV': 'development',
                'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'
            })
            self.assertIsNotNone(dev_app.config['SECRET_KEY'])
            self.assertTrue(len(dev_app.config['SECRET_KEY']) > 0)
        finally:
            os.environ.pop('FLASK_ENV', None)
            if old_key:
                os.environ['SECRET_KEY'] = old_key

    # ---------------------------------------------------------
    # 2. Explicit Database Initialization & Safe Admin Provisioning
    # ---------------------------------------------------------

    def test_create_app_does_not_create_tables_automatically(self):
        """Verify normal create_app() does not automatically execute schema creation."""
        from sqlalchemy import inspect
        uninit_app = create_app(test_config={
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'
        })
        with uninit_app.app_context():
            inspector = inspect(db.engine)
            # Table 'user' should not exist before explicit init_db or db.create_all()
            self.assertFalse(inspector.has_table('user'))

            # Now explicitly initialize
            init_db(uninit_app)
            inspector = inspect(db.engine)
            self.assertTrue(inspector.has_table('user'))

    def test_production_provisioning_rejects_insecure_or_default_password(self):
        """Verify production provisioning strictly refuses admin123 or weak fallback passwords."""
        prod_app = create_app(test_config={
            'TESTING': False,
            'ENV': 'production',
            'SECRET_KEY': 'valid-prod-secret-key-12345678',
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'
        })
        # 1. Test default 'admin123'
        with self.assertRaises(ValueError) as ctx:
            init_db(prod_app, admin_email='admin@trailmate.com', admin_password='admin123')
        self.assertIn("ADMIN_PASSWORD", str(ctx.exception))

        # 2. Test short password (< 8 chars)
        with self.assertRaises(ValueError) as ctx:
            init_db(prod_app, admin_email='admin@trailmate.com', admin_password='short')
        self.assertIn("ADMIN_PASSWORD", str(ctx.exception))

        # 3. Test missing password
        with self.assertRaises(ValueError) as ctx:
            init_db(prod_app, admin_email='admin@trailmate.com', admin_password='')
        self.assertIn("ADMIN_PASSWORD", str(ctx.exception))

    def test_production_provisioning_rejects_missing_email(self):
        """Verify production provisioning strictly requires an explicit admin email."""
        prod_app = create_app(test_config={
            'TESTING': False,
            'ENV': 'production',
            'SECRET_KEY': 'valid-prod-secret-key-12345678',
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'
        })
        with self.assertRaises(ValueError) as ctx:
            init_db(prod_app, admin_email='', admin_password='StrongPassword2026!')
        self.assertIn("ADMIN_EMAIL", str(ctx.exception))

    def test_production_provisioning_succeeds_with_explicit_credentials(self):
        """Verify production provisioning succeeds with explicit, secure credentials."""
        prod_app = create_app(test_config={
            'TESTING': False,
            'ENV': 'production',
            'SECRET_KEY': 'valid-prod-secret-key-12345678',
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'
        })
        init_db(prod_app, admin_email='lead_admin@trailmate.org', admin_password='SuperSecurePassword2026!')
        with prod_app.app_context():
            admin = User.query.filter_by(email='lead_admin@trailmate.org').first()
            self.assertIsNotNone(admin)
            self.assertEqual(admin.role, 'admin')
            self.assertTrue(check_password_hash(admin.password, 'SuperSecurePassword2026!'))

    def test_provisioning_never_resets_existing_admin(self):
        """Verify running init_db() preserves existing admin and never overwrites their credentials."""
        temp_app = create_app(test_config={
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'
        })
        with temp_app.app_context():
            # Initial provisioning
            init_db(temp_app, admin_email='admin@trailmate.com', admin_password='InitialPassword1!')
            admin = User.query.filter_by(role='admin').first()
            initial_hash = admin.password

            # Simulate admin changing password later
            admin.password = generate_password_hash('NewRotatedPassword2026!')
            db.session.commit()
            updated_hash = admin.password

            # Run init_db again with different credentials
            init_db(temp_app, admin_email='intruder@trailmate.com', admin_password='OverwritingPassword3!')

            # Verify existing admin was completely untouched
            admins = User.query.filter_by(role='admin').all()
            self.assertEqual(len(admins), 1)
            self.assertEqual(admins[0].email, 'admin@trailmate.com')
            self.assertEqual(admins[0].password, updated_hash)
            self.assertTrue(check_password_hash(admins[0].password, 'NewRotatedPassword2026!'))

    # ---------------------------------------------------------
    # 3. Database URL & Configuration Tests
    # ---------------------------------------------------------

    def test_postgres_url_normalization(self):
        """Verify legacy postgres:// URLs are converted to postgresql://."""
        legacy_url = "postgres://user:secret@host.render.com:5432/trailmate_db"
        expected = "postgresql://user:secret@host.render.com:5432/trailmate_db"
        self.assertEqual(normalize_database_url(legacy_url), expected)

        standard_url = "postgresql://user:secret@localhost:5432/trailmate_db"
        self.assertEqual(normalize_database_url(standard_url), standard_url)

    def test_database_url_from_environment(self):
        """Verify app uses DATABASE_URL from environment when configured."""
        test_url = "postgres://trek_user:pass123@db.internal:5432/treks"
        os.environ['DATABASE_URL'] = test_url
        try:
            temp_app = create_app(test_config={'TESTING': True})
            self.assertEqual(
                temp_app.config['SQLALCHEMY_DATABASE_URI'],
                "postgresql://trek_user:pass123@db.internal:5432/treks"
            )
        finally:
            os.environ.pop('DATABASE_URL', None)

    # ---------------------------------------------------------
    # 4. Authentication, Passwords & Role Management Tests
    # ---------------------------------------------------------

    def test_password_hashing(self):
        """Verify passwords are never stored in plaintext and are securely hashed."""
        with self.app.app_context():
            user = User(
                name="Security Test",
                email="security@example.com",
                password=generate_password_hash("PlainTextNeverStored"),
                role="user",
                status="Active"
            )
            db.session.add(user)
            db.session.commit()

            fetched = User.query.filter_by(email="security@example.com").first()
            self.assertNotEqual(fetched.password, "PlainTextNeverStored")
            self.assertTrue(fetched.password.startswith(('scrypt:', 'pbkdf2:')))
            self.assertTrue(check_password_hash(fetched.password, "PlainTextNeverStored"))

    def test_user_registration_and_login(self):
        """Verify a user can register, gets Active status, and can log in."""
        resp = self.client.post('/register', data={
            'name': 'Test Trekker',
            'email': 'trekker@example.com',
            'password': 'password123',
            'role': 'user',
            'contact_details': '9876543210'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            u = User.query.filter_by(email='trekker@example.com').first()
            self.assertIsNotNone(u)
            self.assertEqual(u.role, 'user')
            self.assertEqual(u.status, 'Active')

        login_resp = self.client.post('/login', data={
            'email': 'trekker@example.com',
            'password': 'password123'
        }, follow_redirects=True)
        self.assertEqual(login_resp.status_code, 200)
        self.assertIn(b'Browse Treks', login_resp.data)

    def test_staff_registration_requires_approval(self):
        """Verify staff registration creates Pending status and blocks login until approved."""
        self.client.post('/register', data={
            'name': 'Guide Ram',
            'email': 'ram@staff.com',
            'password': 'staffpassword',
            'role': 'staff',
            'contact_details': '1122334455'
        }, follow_redirects=True)

        with self.app.app_context():
            staff = User.query.filter_by(email='ram@staff.com').first()
            self.assertIsNotNone(staff)
            self.assertEqual(staff.status, 'Pending')

        login_resp = self.client.post('/login', data={
            'email': 'ram@staff.com',
            'password': 'staffpassword'
        }, follow_redirects=True)
        self.assertIn(b'pending Admin approval', login_resp.data)

    def test_login_invalid_credentials(self):
        """Verify invalid passwords and nonexistent users are rejected."""
        resp = self.client.post('/login', data={
            'email': 'nonexistent@example.com',
            'password': 'randompassword'
        }, follow_redirects=True)
        self.assertIn(b'Invalid email or password', resp.data)

    def test_logout(self):
        """Verify logout clears session and redirects to login."""
        with self.app.app_context():
            u = User(name='User Logout', email='logout@test.com',
                     password=generate_password_hash('pass123'), role='user', status='Active')
            db.session.add(u)
            db.session.commit()

        self.client.post('/login', data={'email': 'logout@test.com', 'password': 'pass123'})
        resp = self.client.get('/logout', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Login', resp.data)

    # ---------------------------------------------------------
    # 5. Role-Based Authorization Tests
    # ---------------------------------------------------------

    def test_unauthenticated_access_blocked(self):
        """Verify protected portals redirect to login while the catalogue is public."""
        for path in ['/admin/dashboard', '/staff/dashboard']:
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 302)
            self.assertIn('/login', resp.headers['Location'])

        public_resp = self.client.get('/user/dashboard')
        self.assertEqual(public_resp.status_code, 200)
        self.assertIn(b'Browse Treks', public_resp.data)

    def test_user_cannot_access_admin_or_staff(self):
        """Verify regular user cannot access admin or staff portals."""
        with self.app.app_context():
            u = User(name='Plain Trekker', email='plain@trekker.com',
                     password=generate_password_hash('plain123'), role='user', status='Active')
            db.session.add(u)
            db.session.commit()

        self.client.post('/login', data={'email': 'plain@trekker.com', 'password': 'plain123'})

        admin_resp = self.client.get('/admin/dashboard', follow_redirects=True)
        self.assertIn(b'Administrator privileges required', admin_resp.data)

        staff_resp = self.client.get('/staff/dashboard', follow_redirects=True)
        self.assertIn(b'Staff privileges required', staff_resp.data)

    def test_staff_cannot_access_admin_but_can_browse_public_catalogue(self):
        """Verify staff cannot access admin portal but can browse public treks."""
        with self.app.app_context():
            s = User(name='Staff Member', email='staff@example.com',
                     password=generate_password_hash('staff123'), role='staff', status='Active')
            db.session.add(s)
            db.session.commit()

        self.client.post('/login', data={'email': 'staff@example.com', 'password': 'staff123'})

        admin_resp = self.client.get('/admin/dashboard', follow_redirects=True)
        self.assertIn(b'Administrator privileges required', admin_resp.data)

        user_resp = self.client.get('/user/dashboard')
        self.assertEqual(user_resp.status_code, 200)
        self.assertIn(b'Browse Treks', user_resp.data)

    def test_admin_can_access_admin_dashboard(self):
        """Verify admin can access admin dashboard."""
        with self.app.app_context():
            admin = User(name='Admin', email='admin@trailmate.com',
                         password=generate_password_hash('admin123'), role='admin', status='Active')
            db.session.add(admin)
            db.session.commit()

        self.client.post('/login', data={'email': 'admin@trailmate.com', 'password': 'admin123'})
        resp = self.client.get('/admin/dashboard')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Admin Panel', resp.data)

    # ---------------------------------------------------------
    # 6. End-to-End Workflow Tests (Trek Management & Booking)
    # ---------------------------------------------------------

    @patch('razorpay_service.create_order')
    def test_trek_creation_booking_and_cancellation_workflow(self, mock_create_order):
        """Verify end-to-end flow: admin creates trek, user books it, slot decrements, user cancels, slot increments."""
        mock_create_order.return_value = {
            'id': 'order_workflow', 'amount': 100000, 'currency': 'INR'
        }
        os.environ['RAZORPAY_KEY_ID'] = 'rzp_test_mock'
        os.environ['RAZORPAY_KEY_SECRET'] = 'mock_secret'
        self.addCleanup(os.environ.pop, 'RAZORPAY_KEY_ID', None)
        self.addCleanup(os.environ.pop, 'RAZORPAY_KEY_SECRET', None)

        with self.app.app_context():
            admin = User(name='Admin', email='admin@trailmate.com',
                         password=generate_password_hash('admin123'), role='admin', status='Active')
            db.session.add(admin)
            db.session.commit()

        # 1. Admin logs in and creates a trek
        self.client.post('/login', data={'email': 'admin@trailmate.com', 'password': 'admin123'})
        create_resp = self.client.post('/admin/treks/add', data={
            'trek_name': 'Kedarkantha Summit',
            'location': 'Uttarakhand, India',
            'difficulty': 'Moderate',
            'duration': '6 Days',
            'available_slots': '10',
            'start_date': (date.today() + timedelta(days=20)).strftime('%Y-%m-%d'),
            'end_date': (date.today() + timedelta(days=26)).strftime('%Y-%m-%d')
        }, follow_redirects=True)
        self.assertEqual(create_resp.status_code, 200)

        with self.app.app_context():
            trek = Trek.query.filter_by(trek_name='Kedarkantha Summit').first()
            self.assertIsNotNone(trek)
            trek_id = trek.trek_id
            self.assertEqual(trek.available_slots, 10)

        # 2. Register & login as user
        self.client.get('/logout')
        with self.app.app_context():
            u = User(name='Booking User', email='booker@test.com',
                     password=generate_password_hash('pass123'), role='user', status='Active')
            db.session.add(u)
            db.session.commit()

        self.client.post('/login', data={'email': 'booker@test.com', 'password': 'pass123'})

        # 3. Book the trek
        book_resp = self.client.post(f'/user/treks/{trek_id}/book', follow_redirects=True)
        self.assertEqual(book_resp.status_code, 200)

        with self.app.app_context():
            trek = db.session.get(Trek, trek_id)
            self.assertEqual(trek.available_slots, 9)
            booking = Booking.query.filter_by(trek_id=trek_id, status='Booked').first()
            self.assertIsNotNone(booking)
            booking_id = booking.booking_id

        # 4. Cancel booking
        cancel_resp = self.client.post(f'/user/bookings/{booking_id}/cancel', follow_redirects=True)
        self.assertEqual(cancel_resp.status_code, 200)

        with self.app.app_context():
            trek = db.session.get(Trek, trek_id)
            self.assertEqual(trek.available_slots, 10)
            booking = db.session.get(Booking, booking_id)
            self.assertEqual(booking.status, 'Cancelled')

    # ---------------------------------------------------------
    # 7. Template & Static Asset Resolution Tests
    # ---------------------------------------------------------

    def test_root_renders_public_landing_page(self):
        """Verify root route '/' renders the public landing page with HTTP 200."""
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'TrailMate', resp.data)
        self.assertIn(b'Where the Trail Begins', resp.data)

    def test_static_assets_resolve(self):
        """Verify static CSS and background images return HTTP 200."""
        css_resp = self.client.get('/static/css/style.css')
        self.assertEqual(css_resp.status_code, 200)

        login_bg_resp = self.client.get('/static/images/login-bg.jpg')
        self.assertEqual(login_bg_resp.status_code, 200)


if __name__ == '__main__':
    unittest.main()
