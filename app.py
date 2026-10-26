import os
import click
from flask import Flask, request, url_for, redirect, flash
from dotenv import load_dotenv
from database import db

# Load environment variables from .env if present
load_dotenv()

INSECURE_SECRET_KEYS = {
    '',
    'trailmate-secret-key-123',
    'trailmate-dev-secret-key-change-in-prod',
    'trailmate-dev-secret-key',
    'dev',
    'secret',
    'secret-key',
    'changeme',
    'change-this-in-production-to-a-secure-random-key',
    'replace-with-a-secure-random-secret-key',
    'default',
}

INSECURE_ADMIN_PASSWORDS = {
    '',
    'admin123',
    'admin',
    'password',
    '123456',
    'changeme',
    'secret',
    'trailmate',
    'root',
}


def is_production_mode(config_dict=None):
    """
    Determine whether the application is running in production mode.
    Explicit test mode and development mode opt out.
    """
    if config_dict and config_dict.get('TESTING'):
        return False
    if config_dict and (config_dict.get('ENV') == 'production' or config_dict.get('FLASK_ENV') == 'production'):
        return True

    flask_env = os.environ.get('FLASK_ENV', '').lower()
    env = os.environ.get('ENV', '').lower()
    if flask_env == 'production' or env == 'production':
        return True
    if flask_env == 'development' or env == 'development':
        return False

    # Remote database connection indicates a production/staging environment
    db_url = os.environ.get('DATABASE_URL', '')
    if db_url and not db_url.startswith('sqlite'):
        return True

    # Explicit non-debug setting indicates production
    debug_val = os.environ.get('FLASK_DEBUG', '').lower()
    if debug_val in ('0', 'false', 'f'):
        return True

    return False


def normalize_database_url(url):
    """Normalize legacy postgres:// scheme to postgresql:// for SQLAlchemy compatibility."""
    if not url:
        return url
    if url.startswith('postgres://'):
        return url.replace('postgres://', 'postgresql://', 1)
    return url


def init_db(target_app, admin_email=None, admin_password=None, admin_name=None):
    """
    Explicit database initialization and administrator provisioning:
    - Creates database tables if they do not exist.
    - Provisions an initial administrator account if none exists.
    - In production, strictly requires explicit, non-default admin credentials.
    - Preserves existing administrator without reset or modification.
    """
    with target_app.app_context():
        db.create_all()
        from models import User
        from werkzeug.security import generate_password_hash

        existing_admin = User.query.filter_by(role='admin').first()
        if existing_admin:
            target_app.logger.info(
                f"Administrator account '{existing_admin.email}' already exists. Preserving existing account without modification."
            )
            return

        is_prod = is_production_mode(target_app.config)
        email = (admin_email or os.environ.get('ADMIN_EMAIL') or '').strip()
        password = (admin_password or os.environ.get('ADMIN_PASSWORD') or '').strip()
        name = (admin_name or os.environ.get('ADMIN_NAME') or 'System Admin').strip()

        if is_prod:
            if not email:
                raise ValueError(
                    "Production administrator provisioning requires an explicit ADMIN_EMAIL environment variable or --email option."
                )
            if not password or password.lower() in INSECURE_ADMIN_PASSWORDS or len(password) < 8:
                raise ValueError(
                    "Production administrator provisioning requires an explicit, secure ADMIN_PASSWORD environment variable or --password option (minimum 8 characters, non-default)."
                )
        else:
            # Convenient development fallbacks
            if not email:
                email = 'admin@trailmate.com'
            if not password:
                password = 'admin123'

        default_admin = User(
            name=name,
            email=email,
            password=generate_password_hash(password),
            role='admin',
            status='Active'
        )
        try:
            db.session.add(default_admin)
            db.session.commit()
            target_app.logger.info(f"Initial Administrator ({email}) provisioned successfully.")
        except Exception:
            db.session.rollback()
            raise


def create_app(test_config=None, db_name='trekking.db'):
    app = Flask(__name__)

    # Merge test_config early if provided so we know if TESTING is enabled
    if test_config:
        app.config.update(test_config)

    is_prod = is_production_mode(app.config)

    # Secret key handling: require explicit, non-placeholder in production
    secret_key = app.config.get('SECRET_KEY') or os.environ.get('SECRET_KEY', '')
    if is_prod:
        if not secret_key or secret_key.strip() in INSECURE_SECRET_KEYS:
            raise ValueError(
                "Production startup failed: A secure, non-placeholder SECRET_KEY environment variable "
                "must be explicitly configured. Using default or placeholder secret keys in production is prohibited."
            )
        app.config['SECRET_KEY'] = secret_key
    else:
        # Development fallback
        app.config['SECRET_KEY'] = secret_key if secret_key and secret_key.strip() not in INSECURE_SECRET_KEYS else 'trailmate-dev-secret-key-123'

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Session cookie hardening defaults
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    if os.environ.get('SESSION_COOKIE_SECURE', '').lower() in ('true', '1'):
        app.config['SESSION_COOKIE_SECURE'] = True

    # Database configuration: support DATABASE_URL (PostgreSQL) or fallback to SQLite
    basedir = os.path.abspath(os.path.dirname(__file__))
    instance_path = os.path.join(basedir, 'instance')
    if not os.path.exists(instance_path):
        os.makedirs(instance_path, exist_ok=True)

    if not app.config.get('SQLALCHEMY_DATABASE_URI'):
        if db_name != 'trekking.db':
            app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(instance_path, db_name)
        else:
            database_url = os.environ.get('DATABASE_URL')
            if database_url:
                app.config['SQLALCHEMY_DATABASE_URI'] = normalize_database_url(database_url)
            else:
                app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(instance_path, db_name)

    db.init_app(app)

    # CSRF protection via Flask-WTF
    from flask_wtf.csrf import CSRFProtect
    csrf = CSRFProtect(app)

    from flask_login import LoginManager
    from models import User

    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'warning'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        """
        Preserve the requested local path for post-login return.

        A protected booking POST cannot be replayed as a GET, so map it back to
        the trek details page instead.
        """
        next_url = request.path
        if request.query_string:
            next_url = f"{next_url}?{request.query_string.decode('utf-8', 'ignore')}"
        if request.endpoint == 'user.book_trek':
            trek_id = (request.view_args or {}).get('trek_id')
            if trek_id is not None:
                next_url = url_for('user.trek_details', trek_id=trek_id)
        flash(login_manager.login_message, login_manager.login_message_category)
        return redirect(url_for('auth.login', next=next_url))

    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.staff import staff_bp
    from routes.user import user_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(staff_bp)
    app.register_blueprint(user_bp)

    @app.cli.command('expire-pending-bookings')
    def expire_pending_bookings_command():
        """Expire stale pending/unpaid/failed payments and release slots."""
        from routes.user import _expire_pending_bookings

        try:
            expired_count = _expire_pending_bookings()
        except Exception as exc:  # pragma: no cover - defensive CLI handling
            click.echo(f'Failed to expire pending bookings: {exc}', err=True)
            raise SystemExit(1)

        click.echo(f'Expired {expired_count} stale pending booking(s).')

    # -------------------------------------------------------------------
    # Prefers Cloudinary URL when present; falls back to terrain-mapped
    # local static images. Used by all trek-card and trek-detail templates.
    # -------------------------------------------------------------------
    def trek_image_url(trek):
        """Return the best available image URL for a trek."""
        if trek.image_url:
            return trek.image_url
        name = trek.trek_name or ''
        if any(k in name for k in ('Lake', 'Roopkund')):
            local = 'images/trek_lake.jpg'
        elif any(k in name for k in ('Valley', 'Flower', 'Fort', 'Trail', 'Triund')):
            local = 'images/trek_forest.jpg'
        elif any(k in name for k in ('Summit', 'K2', 'Kangri')):
            local = 'images/trek_summit.jpg'
        else:
            local = 'images/trek_himalayas.jpg'
        # url_for needs an application context, which is guaranteed here
        return url_for('static', filename=local)

    app.jinja_env.globals['trek_image_url'] = trek_image_url

    from models import Trek, Booking, CONFIRMED_PAYMENT_STATUSES

    def booking_display(booking):
        """
        Return (label, css_class) for a booking.

        A reservation that is not payment-verified is shown as 'Reserved'
        rather than 'Booked' so the UI never implies a paid confirmation.
        """
        if booking.status == 'Booked' and booking.payment_status not in CONFIRMED_PAYMENT_STATUSES:
            return 'Reserved', 'pending'
        return booking.status, (booking.status or '').lower()

    app.jinja_env.globals['booking_display'] = booking_display

    @app.before_request
    def update_trek_statuses():
        if request.endpoint == 'static':
            return

        from datetime import date
        today = date.today()
        changed = False

        # Auto-complete treks whose end date has passed
        for t in Trek.query.filter(Trek.end_date < today, Trek.status != 'Completed').all():
            t.status = 'Completed'
            for b in Booking.query.filter_by(trek_id=t.trek_id, status='Booked').all():
                b.status = 'Completed'
            changed = True

        # Auto-start treks that are currently happening
        for t in Trek.query.filter(Trek.start_date <= today, Trek.end_date >= today, Trek.status != 'Started').all():
            t.status = 'Started'
            changed = True

        # Ensure future treks are open
        for t in Trek.query.filter(Trek.start_date > today, Trek.status != 'Open').all():
            t.status = 'Open'
            changed = True

        if changed:
            db.session.commit()

    @app.cli.command('init-db')
    @click.option('--email', default=None, help='Initial admin email address')
    @click.option('--password', default=None, help='Initial admin password (min 8 chars in production)')
    @click.option('--name', default=None, help='Initial admin name')
    def init_db_cli(email, password, name):
        """Initialize database schema and provision initial administrator."""
        init_db(app, admin_email=email, admin_password=password, admin_name=name)
        click.echo("Database initialized successfully.")

    return app


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_DEBUG', '1').lower() in ('true', '1', 't')
    app = create_app()
    # In local development via `python app.py`, ensure SQLite database exists for developer convenience
    if not is_production_mode(app.config):
        init_db(app)
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
