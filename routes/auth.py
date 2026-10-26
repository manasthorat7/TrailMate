from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from urllib.parse import urlsplit
from models import User
from database import db

auth_bp = Blueprint('auth', __name__)


def _safe_next_url(target):
    """Return a local path suitable for post-login redirect, or None.

    Reject absolute URLs, protocol-relative URLs, and backslash tricks so the
    ``next`` parameter can never become an open redirect.
    """
    if not target:
        return None
    target = target.strip()
    if not target.startswith('/') or target.startswith('//') or '\\' in target:
        return None
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc:
        return None
    return target


def _redirect_with_next(endpoint, next_url, **values):
    if next_url:
        values['next'] = next_url
    return redirect(url_for(endpoint, **values))


@auth_bp.route('/', methods=['GET'])
def index():
    from models import Trek
    featured_treks = Trek.query.filter_by(status='Open').order_by(Trek.start_date.asc()).limit(6).all()
    return render_template('landing.html', treks=featured_treks)



@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect_based_on_role(current_user.role)

    next_url = _safe_next_url(request.values.get('next'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            if user.status == 'Pending':
                flash('Your staff account is pending Admin approval.', 'warning')
                return _redirect_with_next('auth.login', next_url)
            if user.status in ['Inactive', 'Rejected']:
                flash('Your account has been deactivated or rejected.', 'danger')
                return _redirect_with_next('auth.login', next_url)
            login_user(user)
            if next_url:
                return redirect(next_url)
            return redirect_based_on_role(user.role)

        else:
            flash('Invalid email or password. Please try again.', 'danger')

    return render_template('auth/login.html', next_url=next_url)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect_based_on_role(current_user.role)

    next_url = _safe_next_url(request.values.get('next'))

    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password') or ''
        role = request.form.get('role')  # 'user' or 'staff'
        contact_details = request.form.get('contact_details')
        if role not in ['user', 'staff']:
            flash('Invalid role selected.', 'danger')
            return _redirect_with_next('auth.register', next_url)
        if len(password) < 6:
            flash('Error: Password must be at least 6 characters long.', 'danger')
            return _redirect_with_next('auth.register', next_url)
        user_exists = User.query.filter_by(email=email).first()
        if user_exists:
            flash('Email address already registered.', 'warning')
            return _redirect_with_next('auth.register', next_url)
        initial_status = 'Pending' if role == 'staff' else 'Active'
        new_user = User(
            name=name,
            email=email,
            password=generate_password_hash(password),
            role=role,
            contact_details=contact_details,
            status=initial_status
        )

        db.session.add(new_user)
        db.session.commit()

        if role == 'staff':
            flash('Staff registration successful! Please wait for Admin approval to login.', 'success')
        else:
            flash('Registration successful! You can now login.', 'success')

        return _redirect_with_next('auth.login', next_url)

    return render_template('auth/register.html', next_url=next_url)


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


def redirect_based_on_role(role):
    if role == 'admin':
        return redirect(url_for('admin.dashboard'))
    elif role == 'staff':
        return redirect(url_for('staff.dashboard'))
    else:
        return redirect(url_for('user.dashboard'))
