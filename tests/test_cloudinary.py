"""
tests/test_cloudinary.py
------------------------
Automated tests for the Cloudinary image management feature.

All Cloudinary SDK network calls are mocked — no real credentials
or external uploads are required to run this suite.
"""

import io
import os
import unittest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
from werkzeug.datastructures import FileStorage
from werkzeug.security import generate_password_hash

from app import create_app, init_db
from database import db
from models import User, Trek


def _make_app():
    """Create a fresh test application with in-memory SQLite."""
    app = create_app(test_config={
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-secret-for-cloudinary',
    })
    with app.app_context():
        db.create_all()
    return app


def _create_admin(app):
    with app.app_context():
        admin = User(
            name='Admin',
            email='admin@trailmate.com',
            password=generate_password_hash('admin123'),
            role='admin',
            status='Active',
        )
        db.session.add(admin)
        db.session.commit()


def _create_trek(app, **kwargs):
    """Create a test trek and return its ID."""
    defaults = dict(
        trek_name='Test Summit Trek',
        location='Uttarakhand, India',
        difficulty='Moderate',
        duration='5 Days',
        available_slots=20,
        start_date=date.today() + timedelta(days=30),
        end_date=date.today() + timedelta(days=35),
    )
    defaults.update(kwargs)
    with app.app_context():
        trek = Trek(**defaults)
        db.session.add(trek)
        db.session.commit()
        return trek.trek_id


def _fake_file(name='photo.jpg', content=b'FAKEIMAGEBYTES', size=None):
    """Create a synthetic FileStorage object."""
    if size:
        content = b'X' * size
    return FileStorage(
        stream=io.BytesIO(content),
        filename=name,
        content_type='image/jpeg',
    )


# ---------------------------------------------------------------------------
# 1. cloudinary_service unit tests (no Flask app needed)
# ---------------------------------------------------------------------------

class TestCloudinaryServiceUnit(unittest.TestCase):
    """Tests for the cloudinary_service module in isolation."""

    def setUp(self):
        # Make sure no stale Cloudinary env vars leak between tests
        for key in ('CLOUDINARY_CLOUD_NAME', 'CLOUDINARY_API_KEY', 'CLOUDINARY_API_SECRET'):
            os.environ.pop(key, None)

    def tearDown(self):
        for key in ('CLOUDINARY_CLOUD_NAME', 'CLOUDINARY_API_KEY', 'CLOUDINARY_API_SECRET'):
            os.environ.pop(key, None)

    # -- Configuration detection -------------------------------------------

    def test_unconfigured_when_env_missing(self):
        """is_cloudinary_configured() returns False when env vars absent."""
        import cloudinary_service
        self.assertFalse(cloudinary_service.is_cloudinary_configured())

    def test_configured_when_all_env_present(self):
        """is_cloudinary_configured() returns True when all three vars are set."""
        import cloudinary_service
        os.environ['CLOUDINARY_CLOUD_NAME'] = 'testcloud'
        os.environ['CLOUDINARY_API_KEY'] = '111222333'
        os.environ['CLOUDINARY_API_SECRET'] = 'abc123secret'
        self.assertTrue(cloudinary_service.is_cloudinary_configured())

    def test_partially_configured_returns_false(self):
        """is_cloudinary_configured() returns False when only some vars are set."""
        import cloudinary_service
        os.environ['CLOUDINARY_CLOUD_NAME'] = 'testcloud'
        # API_KEY and SECRET deliberately omitted
        self.assertFalse(cloudinary_service.is_cloudinary_configured())

    # -- File validation ---------------------------------------------------

    def test_allowed_file_accepts_jpeg(self):
        import cloudinary_service
        self.assertTrue(cloudinary_service.allowed_file('photo.jpg'))
        self.assertTrue(cloudinary_service.allowed_file('photo.JPEG'))
        self.assertTrue(cloudinary_service.allowed_file('photo.jpeg'))

    def test_allowed_file_accepts_png(self):
        import cloudinary_service
        self.assertTrue(cloudinary_service.allowed_file('image.png'))
        self.assertTrue(cloudinary_service.allowed_file('image.PNG'))

    def test_allowed_file_accepts_webp(self):
        import cloudinary_service
        self.assertTrue(cloudinary_service.allowed_file('cover.webp'))

    def test_allowed_file_rejects_pdf(self):
        import cloudinary_service
        self.assertFalse(cloudinary_service.allowed_file('document.pdf'))

    def test_allowed_file_rejects_gif(self):
        import cloudinary_service
        self.assertFalse(cloudinary_service.allowed_file('animated.gif'))

    def test_allowed_file_rejects_executable(self):
        import cloudinary_service
        self.assertFalse(cloudinary_service.allowed_file('evil.exe'))

    def test_allowed_file_rejects_no_extension(self):
        import cloudinary_service
        self.assertFalse(cloudinary_service.allowed_file('noext'))

    def test_allowed_file_rejects_empty_string(self):
        import cloudinary_service
        self.assertFalse(cloudinary_service.allowed_file(''))

    def test_validate_upload_rejects_missing_file(self):
        import cloudinary_service
        ok, err = cloudinary_service.validate_upload(None)
        self.assertFalse(ok)
        self.assertIn('No file', err)

    def test_validate_upload_rejects_invalid_type(self):
        import cloudinary_service
        f = _fake_file('document.pdf')
        ok, err = cloudinary_service.validate_upload(f)
        self.assertFalse(ok)
        self.assertIn('Unsupported', err)

    def test_validate_upload_rejects_oversized_file(self):
        import cloudinary_service
        # 6 MB — exceeds the 5 MB limit
        f = _fake_file('big.jpg', size=6 * 1024 * 1024)
        ok, err = cloudinary_service.validate_upload(f)
        self.assertFalse(ok)
        self.assertIn('too large', err)

    def test_validate_upload_rejects_empty_file(self):
        """validate_upload() rejects an empty upload."""
        import cloudinary_service
        f = _fake_file('empty.jpg', content=b'')
        ok, err = cloudinary_service.validate_upload(f)
        self.assertFalse(ok)
        self.assertIn('empty', err.lower())
        import cloudinary_service
        f = _fake_file('valid.jpg', size=1024)   # 1 KB
        ok, err = cloudinary_service.validate_upload(f)
        self.assertTrue(ok)
        self.assertIsNone(err)

    # -- Upload raises error when unconfigured -----------------------------

    def test_upload_raises_when_unconfigured(self):
        import cloudinary_service
        f = _fake_file('trek.jpg', size=1024)
        with self.assertRaises(RuntimeError) as ctx:
            cloudinary_service.upload_trek_image(f)
        self.assertIn('not configured', str(ctx.exception))

    # -- Upload (mocked SDK) -----------------------------------------------

    def test_upload_returns_url_and_public_id(self):
        """upload_trek_image() returns url + public_id from Cloudinary response."""
        import cloudinary_service
        os.environ['CLOUDINARY_CLOUD_NAME'] = 'testcloud'
        os.environ['CLOUDINARY_API_KEY'] = '111'
        os.environ['CLOUDINARY_API_SECRET'] = 'secret'

        mock_result = {
            'secure_url': 'https://res.cloudinary.com/testcloud/image/upload/v1/trailmate/treks/abc.jpg',
            'public_id': 'trailmate/treks/abc',
        }

        with patch('cloudinary.uploader.upload', return_value=mock_result):
            f = _fake_file('trek.jpg', size=512)
            result = cloudinary_service.upload_trek_image(f)

        self.assertEqual(result['url'], mock_result['secure_url'])
        self.assertEqual(result['public_id'], mock_result['public_id'])

    def test_upload_raises_runtime_error_on_sdk_exception(self):
        """upload_trek_image() wraps SDK exceptions in RuntimeError."""
        import cloudinary_service
        os.environ['CLOUDINARY_CLOUD_NAME'] = 'testcloud'
        os.environ['CLOUDINARY_API_KEY'] = '111'
        os.environ['CLOUDINARY_API_SECRET'] = 'secret'

        with patch('cloudinary.uploader.upload', side_effect=Exception('Network timeout')):
            f = _fake_file('trek.jpg', size=512)
            with self.assertRaises(RuntimeError) as ctx:
                cloudinary_service.upload_trek_image(f)
            self.assertIn('upload failed', str(ctx.exception).lower())

    # -- Delete -----------------------------------------------------------

    def test_delete_returns_false_when_unconfigured(self):
        """delete_trek_image() is not successful when Cloudinary is not configured."""
        import cloudinary_service
        result = cloudinary_service.delete_trek_image('trailmate/treks/xyz')
        self.assertFalse(result)

    def test_delete_returns_true_for_empty_public_id(self):
        """delete_trek_image() returns True harmlessly for empty/None public_id."""
        import cloudinary_service
        self.assertTrue(cloudinary_service.delete_trek_image(None))
        self.assertTrue(cloudinary_service.delete_trek_image(''))

    def test_delete_rejects_arbitrary_public_id(self):
        """delete_trek_image() refuses public IDs not in our designated folder."""
        import cloudinary_service
        os.environ['CLOUDINARY_CLOUD_NAME'] = 'testcloud'
        os.environ['CLOUDINARY_API_KEY'] = '111'
        os.environ['CLOUDINARY_API_SECRET'] = 'secret'

        result = cloudinary_service.delete_trek_image('other/folder/asset')
        self.assertFalse(result)

    def test_delete_calls_sdk_for_valid_public_id(self):
        """delete_trek_image() calls cloudinary.uploader.destroy for valid public_id."""
        import cloudinary_service
        os.environ['CLOUDINARY_CLOUD_NAME'] = 'testcloud'
        os.environ['CLOUDINARY_API_KEY'] = '111'
        os.environ['CLOUDINARY_API_SECRET'] = 'secret'

        with patch('cloudinary.uploader.destroy', return_value={'result': 'ok'}) as mock_destroy:
            result = cloudinary_service.delete_trek_image('trailmate/treks/abc123')
            self.assertTrue(result)
            mock_destroy.assert_called_once_with('trailmate/treks/abc123', resource_type='image')


# ---------------------------------------------------------------------------
# 2. Integration tests — route-level (Flask test client)
# ---------------------------------------------------------------------------

class TestCloudinaryRoutes(unittest.TestCase):
    """Route-level integration tests for image upload / remove / display."""

    def setUp(self):
        for key in ('CLOUDINARY_CLOUD_NAME', 'CLOUDINARY_API_KEY', 'CLOUDINARY_API_SECRET'):
            os.environ.pop(key, None)
        self.app = _make_app()
        self.client = self.app.test_client()
        _create_admin(self.app)
        self.trek_id = _create_trek(self.app)
        # Log in as admin
        self.client.post('/login', data={
            'email': 'admin@trailmate.com',
            'password': 'admin123',
        })

    def tearDown(self):
        for key in ('CLOUDINARY_CLOUD_NAME', 'CLOUDINARY_API_KEY', 'CLOUDINARY_API_SECRET'):
            os.environ.pop(key, None)
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    # -- Unauthorized access ----------------------------------------------

    def test_unauthenticated_cannot_upload(self):
        """Unauthenticated users are redirected to login when accessing image remove."""
        self.client.get('/logout')
        resp = self.client.post(f'/admin/treks/{self.trek_id}/image/remove',
                                follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.headers.get('Location', ''))

    def test_non_admin_cannot_remove_image(self):
        """Regular users cannot access the image remove endpoint."""
        # Create and log in as a regular user
        with self.app.app_context():
            u = User(name='Plain User', email='user@test.com',
                     password=generate_password_hash('pass123'),
                     role='user', status='Active')
            db.session.add(u)
            db.session.commit()
        self.client.get('/logout')
        self.client.post('/login', data={'email': 'user@test.com', 'password': 'pass123'})
        resp = self.client.post(f'/admin/treks/{self.trek_id}/image/remove',
                                follow_redirects=True)
        self.assertIn(b'Administrator privileges required', resp.data)

    # -- Upload validation (no Cloudinary configured) ---------------------

    def test_upload_invalid_file_type_shows_error(self):
        """Invalid file types are rejected with a user-facing error."""
        resp = self.client.post(
            f'/admin/treks/{self.trek_id}/edit',
            data={
                'trek_name': 'Test Summit Trek',
                'location': 'Uttarakhand, India',
                'difficulty': 'Moderate',
                'duration': '5 Days',
                'available_slots': '20',
                'price': '1000.00',
                'start_date': (date.today() + timedelta(days=30)).strftime('%Y-%m-%d'),
                'end_date': (date.today() + timedelta(days=35)).strftime('%Y-%m-%d'),
                'status': 'Open',
                'trek_image': (io.BytesIO(b'%PDF-1.4 fake'), 'evil.pdf'),
            },
            content_type='multipart/form-data',
            follow_redirects=True,
        )
        self.assertIn(b'Unsupported', resp.data)

    def test_upload_oversized_file_shows_error(self):
        """Files larger than 5 MB are rejected with a clear error message."""
        big_content = b'X' * (6 * 1024 * 1024)  # 6 MB
        resp = self.client.post(
            f'/admin/treks/{self.trek_id}/edit',
            data={
                'trek_name': 'Test Summit Trek',
                'location': 'Uttarakhand, India',
                'difficulty': 'Moderate',
                'duration': '5 Days',
                'available_slots': '20',
                'price': '1000.00',
                'start_date': (date.today() + timedelta(days=30)).strftime('%Y-%m-%d'),
                'end_date': (date.today() + timedelta(days=35)).strftime('%Y-%m-%d'),
                'status': 'Open',
                'trek_image': (io.BytesIO(big_content), 'big.jpg'),
            },
            content_type='multipart/form-data',
            follow_redirects=True,
        )
        self.assertIn(b'too large', resp.data)

    def test_upload_when_cloudinary_not_configured_shows_warning(self):
        """Valid file upload shows a clear warning when Cloudinary is not configured."""
        resp = self.client.post(
            f'/admin/treks/{self.trek_id}/edit',
            data={
                'trek_name': 'Test Summit Trek',
                'location': 'Uttarakhand, India',
                'difficulty': 'Moderate',
                'duration': '5 Days',
                'available_slots': '20',
                'price': '1000.00',
                'start_date': (date.today() + timedelta(days=30)).strftime('%Y-%m-%d'),
                'end_date': (date.today() + timedelta(days=35)).strftime('%Y-%m-%d'),
                'status': 'Open',
                'trek_image': (io.BytesIO(b'FAKEJPEG'), 'photo.jpg'),
            },
            content_type='multipart/form-data',
            follow_redirects=True,
        )
        self.assertIn(b'Cloudinary is not configured', resp.data)

    # -- Upload with mocked Cloudinary ------------------------------------

    def test_successful_upload_saves_image_url_to_db(self):
        """A valid upload stores image_url and image_public_id in the database."""
        os.environ['CLOUDINARY_CLOUD_NAME'] = 'testcloud'
        os.environ['CLOUDINARY_API_KEY'] = '111'
        os.environ['CLOUDINARY_API_SECRET'] = 'secret'

        mock_result = {
            'secure_url': 'https://res.cloudinary.com/testcloud/image/upload/trek1.jpg',
            'public_id': 'trailmate/treks/abc123',
        }

        with patch('cloudinary.uploader.upload', return_value=mock_result):
            resp = self.client.post(
                f'/admin/treks/{self.trek_id}/edit',
                data={
                    'trek_name': 'Test Summit Trek',
                    'location': 'Uttarakhand, India',
                    'difficulty': 'Moderate',
                    'duration': '5 Days',
                    'available_slots': '20',
                'price': '1000.00',
                    'start_date': (date.today() + timedelta(days=30)).strftime('%Y-%m-%d'),
                    'end_date': (date.today() + timedelta(days=35)).strftime('%Y-%m-%d'),
                    'status': 'Open',
                    'trek_image': (io.BytesIO(b'FAKEJPEG'), 'photo.jpg'),
                },
                content_type='multipart/form-data',
                follow_redirects=True,
            )
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            trek = Trek.query.get(self.trek_id)
            self.assertEqual(trek.image_url, mock_result['secure_url'])
            self.assertEqual(trek.image_public_id, mock_result['public_id'])

    def test_upload_failure_preserves_existing_image(self):
        """When SDK throws, existing image_url is NOT overwritten."""
        # First, put a known image on the trek
        with self.app.app_context():
            trek = Trek.query.get(self.trek_id)
            trek.image_url = 'https://res.cloudinary.com/old/image.jpg'
            trek.image_public_id = 'trailmate/treks/oldpid'
            db.session.commit()

        os.environ['CLOUDINARY_CLOUD_NAME'] = 'testcloud'
        os.environ['CLOUDINARY_API_KEY'] = '111'
        os.environ['CLOUDINARY_API_SECRET'] = 'secret'

        with patch('cloudinary.uploader.upload', side_effect=Exception('Timeout')):
            self.client.post(
                f'/admin/treks/{self.trek_id}/edit',
                data={
                    'trek_name': 'Test Summit Trek',
                    'location': 'Uttarakhand, India',
                    'difficulty': 'Moderate',
                    'duration': '5 Days',
                    'available_slots': '20',
                'price': '1000.00',
                    'start_date': (date.today() + timedelta(days=30)).strftime('%Y-%m-%d'),
                    'end_date': (date.today() + timedelta(days=35)).strftime('%Y-%m-%d'),
                    'status': 'Open',
                    'trek_image': (io.BytesIO(b'FAKEJPEG'), 'photo.jpg'),
                },
                content_type='multipart/form-data',
                follow_redirects=True,
            )

        # Old image must still be present in DB
        with self.app.app_context():
            trek = Trek.query.get(self.trek_id)
            self.assertEqual(trek.image_url, 'https://res.cloudinary.com/old/image.jpg')
            self.assertEqual(trek.image_public_id, 'trailmate/treks/oldpid')

    def test_image_replacement_deletes_old_asset(self):
        """Replacing an image deletes the previous Cloudinary asset after DB commit."""
        with self.app.app_context():
            trek = Trek.query.get(self.trek_id)
            trek.image_url = 'https://res.cloudinary.com/old/image.jpg'
            trek.image_public_id = 'trailmate/treks/oldpid'
            db.session.commit()

        os.environ['CLOUDINARY_CLOUD_NAME'] = 'testcloud'
        os.environ['CLOUDINARY_API_KEY'] = '111'
        os.environ['CLOUDINARY_API_SECRET'] = 'secret'

        new_result = {
            'secure_url': 'https://res.cloudinary.com/testcloud/image/upload/new.jpg',
            'public_id': 'trailmate/treks/newpid',
        }

        with patch('cloudinary.uploader.upload', return_value=new_result), \
             patch('cloudinary.uploader.destroy', return_value={'result': 'ok'}) as mock_destroy:
            self.client.post(
                f'/admin/treks/{self.trek_id}/edit',
                data={
                    'trek_name': 'Test Summit Trek',
                    'location': 'Uttarakhand, India',
                    'difficulty': 'Moderate',
                    'duration': '5 Days',
                    'available_slots': '20',
                'price': '1000.00',
                    'start_date': (date.today() + timedelta(days=30)).strftime('%Y-%m-%d'),
                    'end_date': (date.today() + timedelta(days=35)).strftime('%Y-%m-%d'),
                    'status': 'Open',
                    'trek_image': (io.BytesIO(b'FAKEJPEG'), 'photo.jpg'),
                },
                content_type='multipart/form-data',
                follow_redirects=True,
            )

        mock_destroy.assert_called_once_with('trailmate/treks/oldpid', resource_type='image')

        with self.app.app_context():
            trek = Trek.query.get(self.trek_id)
            self.assertEqual(trek.image_url, new_result['secure_url'])
            self.assertEqual(trek.image_public_id, new_result['public_id'])

    # -- Image remove -----------------------------------------------------

    def test_remove_image_clears_db_fields(self):
        """Remove image endpoint clears image_url and image_public_id in DB."""
        with self.app.app_context():
            trek = Trek.query.get(self.trek_id)
            trek.image_url = 'https://res.cloudinary.com/testcloud/image.jpg'
            trek.image_public_id = 'trailmate/treks/abcpid'
            db.session.commit()

        with patch('cloudinary.uploader.destroy', return_value={'result': 'ok'}):
            os.environ['CLOUDINARY_CLOUD_NAME'] = 'testcloud'
            os.environ['CLOUDINARY_API_KEY'] = '111'
            os.environ['CLOUDINARY_API_SECRET'] = 'secret'
            resp = self.client.post(
                f'/admin/treks/{self.trek_id}/image/remove',
                follow_redirects=True,
            )

        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            trek = Trek.query.get(self.trek_id)
            self.assertIsNone(trek.image_url)
            self.assertIsNone(trek.image_public_id)

    def test_remove_image_shows_success_flash(self):
        """Remove image endpoint shows a success flash message."""
        with self.app.app_context():
            trek = Trek.query.get(self.trek_id)
            trek.image_url = 'https://res.cloudinary.com/testcloud/image.jpg'
            trek.image_public_id = 'trailmate/treks/abcpid'
            db.session.commit()

        os.environ['CLOUDINARY_CLOUD_NAME'] = 'testcloud'
        os.environ['CLOUDINARY_API_KEY'] = '111'
        os.environ['CLOUDINARY_API_SECRET'] = 'secret'

        with patch('cloudinary.uploader.destroy', return_value={'result': 'ok'}):
            resp = self.client.post(
                f'/admin/treks/{self.trek_id}/image/remove',
                follow_redirects=True,
            )

        self.assertIn(b'removed', resp.data)

    # -- Fallback rendering -----------------------------------------------

    def test_trek_without_image_renders_fallback(self):
        """User dashboard renders correctly for treks without a Cloudinary image."""
        with self.app.app_context():
            u = User(name='Trekker', email='trekker@test.com',
                     password=generate_password_hash('pass123'),
                     role='user', status='Active')
            db.session.add(u)
            db.session.commit()

        self.client.get('/logout')
        self.client.post('/login', data={'email': 'trekker@test.com', 'password': 'pass123'})

        resp = self.client.get('/user/dashboard')
        self.assertEqual(resp.status_code, 200)
        # No Cloudinary URL present — should still render successfully
        self.assertIn(b'Test Summit Trek', resp.data)

    def test_trek_with_cloudinary_image_displays_url(self):
        """Trek detail page uses the Cloudinary URL when image_url is set."""
        cloudinary_url = 'https://res.cloudinary.com/testcloud/trek_image.jpg'
        with self.app.app_context():
            trek = Trek.query.get(self.trek_id)
            trek.image_url = cloudinary_url
            trek.image_public_id = 'trailmate/treks/abcdef'
            db.session.commit()

            u = User(name='Trekker', email='trekker2@test.com',
                     password=generate_password_hash('pass123'),
                     role='user', status='Active')
            db.session.add(u)
            db.session.commit()

        self.client.get('/logout')
        self.client.post('/login', data={'email': 'trekker2@test.com', 'password': 'pass123'})

        resp = self.client.get(f'/user/treks/{self.trek_id}')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(cloudinary_url.encode(), resp.data)

    def test_staff_assigned_treks_display_cloudinary_image(self):
        """Staff assigned-trek cards use trek_image_url for uploaded images."""
        cloudinary_url = 'https://res.cloudinary.com/testcloud/staff_trek.jpg'
        with self.app.app_context():
            staff = User(
                name='Guide',
                email='guide@test.com',
                password=generate_password_hash('pass123'),
                role='staff',
                status='Active',
            )
            db.session.add(staff)
            db.session.flush()
            trek = Trek.query.get(self.trek_id)
            trek.assigned_staff_id = staff.id
            trek.image_url = cloudinary_url
            trek.image_public_id = 'trailmate/treks/staffpid'
            db.session.commit()
            staff_email = staff.email

        self.client.get('/logout')
        self.client.post('/login', data={'email': staff_email, 'password': 'pass123'})

        resp = self.client.get('/staff/assigned-treks')

        self.assertEqual(resp.status_code, 200)
        self.assertIn(cloudinary_url.encode(), resp.data)

    # -- API secret never exposed -----------------------------------------

    def test_api_secret_not_in_response(self):
        """The Cloudinary API secret is never present in any page response."""
        os.environ['CLOUDINARY_CLOUD_NAME'] = 'testcloud'
        os.environ['CLOUDINARY_API_KEY'] = '111222333'
        os.environ['CLOUDINARY_API_SECRET'] = 'SUPERSECRETVALUE'

        for path in ['/admin/treks', f'/admin/treks/{self.trek_id}/edit',
                     '/admin/dashboard']:
            resp = self.client.get(path)
            self.assertNotIn(b'SUPERSECRETVALUE', resp.data,
                             f'API secret found in response for {path}')

    # -- Add new trek with image ------------------------------------------

    def test_add_trek_with_valid_image(self):
        """Admin can add a trek with a Cloudinary image via the add form."""
        os.environ['CLOUDINARY_CLOUD_NAME'] = 'testcloud'
        os.environ['CLOUDINARY_API_KEY'] = '111'
        os.environ['CLOUDINARY_API_SECRET'] = 'secret'

        mock_result = {
            'secure_url': 'https://res.cloudinary.com/testcloud/new_trek.jpg',
            'public_id': 'trailmate/treks/newtrek123',
        }

        with patch('cloudinary.uploader.upload', return_value=mock_result):
            resp = self.client.post(
                '/admin/treks/add',
                data={
                    'trek_name': 'Chandrashila Summit',
                    'location': 'Chopta, Uttarakhand',
                    'difficulty': 'Hard',
                    'duration': '3 Days',
                    'available_slots': '12',
                'price': '1000.00',
                    'start_date': (date.today() + timedelta(days=45)).strftime('%Y-%m-%d'),
                    'end_date': (date.today() + timedelta(days=48)).strftime('%Y-%m-%d'),
                    'trek_image': (io.BytesIO(b'FAKEJPEG'), 'summit.jpg'),
                },
                content_type='multipart/form-data',
                follow_redirects=True,
            )

        self.assertEqual(resp.status_code, 200)
        with self.app.app_context():
            trek = Trek.query.filter_by(trek_name='Chandrashila Summit').first()
            self.assertIsNotNone(trek)
            self.assertEqual(trek.image_url, mock_result['secure_url'])

    def test_delete_trek_removes_cloudinary_asset(self):
        """Deleting a trek with a Cloudinary image also removes the Cloudinary asset."""
        # First upload an image to the trek
        with self.app.app_context():
            trek = Trek.query.get(self.trek_id)
            trek.image_url = 'https://res.cloudinary.com/testcloud/image.jpg'
            trek.image_public_id = 'trailmate/treks/todelete'
            db.session.commit()

        os.environ['CLOUDINARY_CLOUD_NAME'] = 'testcloud'
        os.environ['CLOUDINARY_API_KEY'] = '111'
        os.environ['CLOUDINARY_API_SECRET'] = 'secret'

        with patch('cloudinary.uploader.destroy', return_value={'result': 'ok'}) as mock_destroy:
            resp = self.client.post(
                f'/admin/treks/{self.trek_id}/delete',
                follow_redirects=True,
            )

        self.assertEqual(resp.status_code, 200)
        mock_destroy.assert_called_once_with('trailmate/treks/todelete', resource_type='image')

        with self.app.app_context():
            trek = Trek.query.get(self.trek_id)
            self.assertIsNone(trek)


    def test_remove_image_deletion_failure_preserves_reference(self):
        """Failed Cloudinary deletion keeps the existing image reference."""
        with self.app.app_context():
            trek = Trek.query.get(self.trek_id)
            trek.image_url = 'https://res.cloudinary.com/testcloud/image.jpg'
            trek.image_public_id = 'trailmate/treks/keepme'
            db.session.commit()

        os.environ['CLOUDINARY_CLOUD_NAME'] = 'testcloud'
        os.environ['CLOUDINARY_API_KEY'] = '111'
        os.environ['CLOUDINARY_API_SECRET'] = 'secret'

        with patch('cloudinary.uploader.destroy', side_effect=Exception('network error')):
            resp = self.client.post(
                f'/admin/treks/{self.trek_id}/image/remove',
                follow_redirects=True,
            )

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'preserved', resp.data)

        with self.app.app_context():
            trek = Trek.query.get(self.trek_id)
            self.assertEqual(trek.image_url, 'https://res.cloudinary.com/testcloud/image.jpg')
            self.assertEqual(trek.image_public_id, 'trailmate/treks/keepme')

    def test_remove_image_unconfigured_preserves_reference(self):
        """Unconfigured Cloudinary deletion keeps the existing image reference."""
        with self.app.app_context():
            trek = Trek.query.get(self.trek_id)
            trek.image_url = 'https://res.cloudinary.com/testcloud/image.jpg'
            trek.image_public_id = 'trailmate/treks/keepme'
            db.session.commit()

        resp = self.client.post(
            f'/admin/treks/{self.trek_id}/image/remove',
            follow_redirects=True,
        )

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'preserved', resp.data)

        with self.app.app_context():
            trek = Trek.query.get(self.trek_id)
            self.assertEqual(trek.image_public_id, 'trailmate/treks/keepme')

    def test_delete_trek_deletion_failure_preserves_trek(self):
        """Failed Cloudinary deletion prevents trek deletion."""
        with self.app.app_context():
            trek = Trek.query.get(self.trek_id)
            trek.image_url = 'https://res.cloudinary.com/testcloud/image.jpg'
            trek.image_public_id = 'trailmate/treks/keepme'
            db.session.commit()

        os.environ['CLOUDINARY_CLOUD_NAME'] = 'testcloud'
        os.environ['CLOUDINARY_API_KEY'] = '111'
        os.environ['CLOUDINARY_API_SECRET'] = 'secret'

        with patch('cloudinary.uploader.destroy', side_effect=Exception('network error')):
            resp = self.client.post(
                f'/admin/treks/{self.trek_id}/delete',
                follow_redirects=True,
            )

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'preserved', resp.data)

        with self.app.app_context():
            trek = Trek.query.get(self.trek_id)
            self.assertIsNotNone(trek)

    def test_delete_trek_unconfigured_preserves_trek(self):
        """Unconfigured Cloudinary deletion prevents trek deletion."""
        with self.app.app_context():
            trek = Trek.query.get(self.trek_id)
            trek.image_url = 'https://res.cloudinary.com/testcloud/image.jpg'
            trek.image_public_id = 'trailmate/treks/keepme'
            db.session.commit()

        resp = self.client.post(
            f'/admin/treks/{self.trek_id}/delete',
            follow_redirects=True,
        )

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'preserved', resp.data)

        with self.app.app_context():
            trek = Trek.query.get(self.trek_id)
            self.assertIsNotNone(trek)

    def test_image_replacement_reports_old_deletion_failure(self):
        """A failed old-image deletion is reported after a successful replacement."""
        with self.app.app_context():
            trek = Trek.query.get(self.trek_id)
            trek.image_url = 'https://res.cloudinary.com/old/image.jpg'
            trek.image_public_id = 'trailmate/treks/oldpid'
            db.session.commit()

        os.environ['CLOUDINARY_CLOUD_NAME'] = 'testcloud'
        os.environ['CLOUDINARY_API_KEY'] = '111'
        os.environ['CLOUDINARY_API_SECRET'] = 'secret'

        new_result = {
            'secure_url': 'https://res.cloudinary.com/testcloud/image/upload/new.jpg',
            'public_id': 'trailmate/treks/newpid',
        }

        with patch('cloudinary.uploader.upload', return_value=new_result), \
             patch('cloudinary.uploader.destroy', side_effect=Exception('network error')):
            resp = self.client.post(
                f'/admin/treks/{self.trek_id}/edit',
                data={
                    'trek_name': 'Test Summit Trek',
                    'location': 'Uttarakhand, India',
                    'difficulty': 'Moderate',
                    'duration': '5 Days',
                    'available_slots': '20',
                'price': '1000.00',
                    'start_date': (date.today() + timedelta(days=30)).strftime('%Y-%m-%d'),
                    'end_date': (date.today() + timedelta(days=35)).strftime('%Y-%m-%d'),
                    'status': 'Open',
                    'trek_image': (io.BytesIO(b'FAKEJPEG'), 'photo.jpg'),
                },
                content_type='multipart/form-data',
                follow_redirects=True,
            )

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'could not be', resp.data)

        with self.app.app_context():
            trek = Trek.query.get(self.trek_id)
            self.assertEqual(trek.image_public_id, 'trailmate/treks/newpid')


if __name__ == '__main__':
    unittest.main()
