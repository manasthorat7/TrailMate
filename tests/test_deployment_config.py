"""
tests/test_deployment_config.py
-------------------------------
Focused tests for Render/PostgreSQL deployment configuration:

- Production refuses to start without an explicit, strong SECRET_KEY.
- Production refuses to fall back to local SQLite.
- Render-style PostgreSQL URLs are normalized to the installed psycopg2 driver.
- Secure session cookies and one-hop proxy handling are enabled.
- Documented placeholder admin passwords are rejected during provisioning.
- The init-db CLI reports provisioning errors without echoing the password.

These tests never open the real SQLite database; in-memory SQLite is used for
provisioning checks and fake PostgreSQL URLs are never connected to.
"""
import os
import unittest
from unittest.mock import patch

from werkzeug.middleware.proxy_fix import ProxyFix

from app import create_app, init_db
from database import db
from models import User


STRONG_SECRET = 'x89Fq2!vN$1z90LaQwe9876543210zyxwvutsrq'
POSTGRES_URL = 'postgresql+psycopg2://trek_user:pass123@db.internal:5432/treks'
LEGACY_POSTGRES_URL = 'postgres://trek_user:pass123@db.internal:5432/treks'


def production_config(**overrides):
    config = {
        'TESTING': False,
        'ENV': 'production',
        'SECRET_KEY': STRONG_SECRET,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
    }
    config.update(overrides)
    return config


class ProductionConfigTestCase(unittest.TestCase):
    def test_production_requires_database_url(self):
        """Production must fail closed instead of using instance/trekking.db."""
        with patch.dict(os.environ, {'ENV': 'production', 'SECRET_KEY': STRONG_SECRET}):
            os.environ.pop('DATABASE_URL', None)
            with self.assertRaises(ValueError) as ctx:
                create_app(test_config={'TESTING': False, 'ENV': 'production'})
        self.assertIn('DATABASE_URL', str(ctx.exception))

    def test_production_rejects_sqlite_database_url(self):
        """A SQLite DATABASE_URL is rejected even when explicitly supplied."""
        env = {
            'ENV': 'production',
            'SECRET_KEY': STRONG_SECRET,
            'DATABASE_URL': 'sqlite:///instance/trekking.db',
        }
        with patch.dict(os.environ, env):
            with self.assertRaises(ValueError) as ctx:
                create_app(test_config={'TESTING': False, 'ENV': 'production'})
        self.assertIn('DATABASE_URL', str(ctx.exception))
        self.assertIn('SQLite', str(ctx.exception))

    def test_production_normalizes_render_postgres_url(self):
        """Render's legacy postgres:// scheme is normalized and accepted."""
        env = {
            'ENV': 'production',
            'SECRET_KEY': STRONG_SECRET,
            'DATABASE_URL': '  ' + LEGACY_POSTGRES_URL + '  ',
        }
        with patch.dict(os.environ, env):
            app = create_app(test_config={'TESTING': False, 'ENV': 'production'})

        self.assertEqual(app.config['SQLALCHEMY_DATABASE_URI'], POSTGRES_URL)
        self.assertTrue(app.config['SESSION_COOKIE_SECURE'])
        self.assertTrue(app.config['SESSION_COOKIE_HTTPONLY'])
        self.assertEqual(app.config['SESSION_COOKIE_SAMESITE'], 'Lax')
        self.assertIsInstance(app.wsgi_app, ProxyFix)
        self.assertTrue(app.config['SQLALCHEMY_ENGINE_OPTIONS']['pool_pre_ping'])

    def test_production_preserves_postgres_credentials_and_query(self):
        """Normalization must not alter encoded credentials or query parameters."""
        url = 'postgres://us%40er:p%3Ass@db.internal:5432/treks?sslmode=require'
        with patch.dict(os.environ, {
            'ENV': 'production',
            'SECRET_KEY': STRONG_SECRET,
            'DATABASE_URL': url,
        }):
            app = create_app(test_config={'TESTING': False, 'ENV': 'production'})

        self.assertEqual(
            app.config['SQLALCHEMY_DATABASE_URI'],
            'postgresql+psycopg2://us%40er:p%3Ass@db.internal:5432/treks?sslmode=require',
        )

    def test_production_rejects_placeholder_secret_prefix(self):
        """Documentation-style secrets are rejected even if not in the deny list."""
        with patch.dict(os.environ, {
            'ENV': 'production',
            'SECRET_KEY': 'replace-with-any-long-value-at-all',
        }):
            with self.assertRaises(ValueError) as ctx:
                create_app(test_config=production_config(SECRET_KEY=None))
        self.assertIn('SECRET_KEY', str(ctx.exception))

    def test_development_keeps_sqlite_and_dev_secret(self):
        """Local development keeps the SQLite workflow and a fallback key."""
        with patch.dict(os.environ, {'FLASK_ENV': 'development'}):
            for key in ('ENV', 'DATABASE_URL', 'SECRET_KEY', 'SESSION_COOKIE_SECURE'):
                os.environ.pop(key, None)
            app = create_app(test_config={
                'TESTING': False,
                'FLASK_ENV': 'development',
            })

        self.assertTrue(app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite:///'))
        self.assertTrue(app.config['SQLALCHEMY_DATABASE_URI'].endswith('trekking.db'))
        self.assertTrue(app.config['SECRET_KEY'])
        self.assertFalse(app.config['SESSION_COOKIE_SECURE'])

    def test_flask_debug_zero_alone_is_not_production(self):
        """A local .env copied from the example must not force production mode."""
        with patch.dict(os.environ, {'FLASK_DEBUG': '0'}):
            for key in (
                'ENV', 'FLASK_ENV', 'DATABASE_URL', 'RENDER',
                'SECRET_KEY', 'SESSION_COOKIE_SECURE',
            ):
                os.environ.pop(key, None)
            app = create_app(test_config={'TESTING': False})

        self.assertTrue(app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite:///'))
        self.assertFalse(app.config['SESSION_COOKIE_SECURE'])

    def test_render_environment_flag_requires_shared_database(self):
        """Render's RENDER=true flag makes missing DATABASE_URL fail closed."""
        with patch.dict(os.environ, {'RENDER': 'true', 'SECRET_KEY': STRONG_SECRET}):
            for key in ('ENV', 'FLASK_ENV', 'DATABASE_URL'):
                os.environ.pop(key, None)
            with self.assertRaises(ValueError) as ctx:
                create_app(test_config={'TESTING': False})
        self.assertIn('DATABASE_URL', str(ctx.exception))

    def test_render_blueprint_avoids_paid_only_predeploy(self):
        """Free web services cannot use preDeployCommand; init must run at start."""
        import re
        from pathlib import Path

        blueprint = (Path(__file__).resolve().parents[1] / 'render.yaml').read_text(encoding='utf-8')

        self.assertIsNone(
            re.search(r'(?m)^\s*preDeployCommand:', blueprint),
            'preDeployCommand is paid-plan only and must not be used on the free plan.',
        )
        self.assertIn(
            'startCommand: \'sh -c "python migrate_add_trek_price.py && flask --app wsgi init-db && gunicorn --bind 0.0.0.0:$PORT wsgi:app"\'',
            blueprint,
        )
        self.assertIn('plan: free', blueprint)


class ProvisioningPasswordTestCase(unittest.TestCase):
    def _production_app(self):
        app = create_app(test_config=production_config())
        self.addCleanup(self._dispose_app, app)
        return app

    @staticmethod
    def _dispose_app(app):
        with app.app_context():
            db.session.remove()
            db.engine.dispose()

    def test_seed_script_refuses_production(self):
        """Demo seeding must fail safely instead of touching production data."""
        from seed import run_seed

        app = self._production_app()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('ALLOW_PRODUCTION_SEED', None)
            with self.assertRaises(RuntimeError) as ctx:
                run_seed(app=app)
        self.assertIn('ALLOW_PRODUCTION_SEED', str(ctx.exception))

    def test_rejects_documented_placeholder_password(self):
        """The password shown in .env.example must never reach production."""
        app = self._production_app()
        with self.assertRaises(ValueError) as ctx:
            init_db(
                app,
                admin_email='admin@example.com',
                admin_password='replace-with-a-strong-admin-password',
            )
        self.assertIn('ADMIN_PASSWORD', str(ctx.exception))

        with app.app_context():
            self.assertIsNone(User.query.filter_by(role='admin').first())

    def test_rejects_change_me_style_password(self):
        """A long but obviously placeholder password is still rejected."""
        app = self._production_app()
        with self.assertRaises(ValueError) as ctx:
            init_db(app, admin_email='admin@example.com', admin_password='ChangeMe-please-123')
        self.assertIn('ADMIN_PASSWORD', str(ctx.exception))

    def test_cli_error_does_not_echo_password(self):
        """A failed one-time provisioning run must not print the secret."""
        app = self._production_app()
        runner = app.test_cli_runner()
        bad_password = 'replace-with-a-strong-admin-password'

        result = runner.invoke(
            args=['init-db', '--email', 'admin@example.com', '--password', bad_password]
        )

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn('ADMIN_PASSWORD', result.output)
        self.assertNotIn(bad_password, result.output)

        with app.app_context():
            self.assertIsNone(User.query.filter_by(role='admin').first())

    def test_cli_provisions_exactly_one_admin_across_reruns(self):
        """Repeated init-db runs must not create duplicate administrators."""
        app = self._production_app()
        runner = app.test_cli_runner()
        password = 'SuperSecurePassword2026!'

        first = runner.invoke(
            args=['init-db', '--email', 'lead_admin@example.com', '--password', password]
        )
        second = runner.invoke(
            args=['init-db', '--email', 'other_admin@example.com', '--password', 'AnotherSecurePassword1!']
        )

        self.assertEqual(first.exit_code, 0, first.output)
        self.assertEqual(second.exit_code, 0, second.output)

        with app.app_context():
            admins = User.query.filter_by(role='admin').all()
            self.assertEqual(len(admins), 1)
            self.assertEqual(admins[0].email, 'lead_admin@example.com')


if __name__ == '__main__':
    unittest.main()
