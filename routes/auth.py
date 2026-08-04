from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import User
from database import db
auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/', methods=['GET'])
def index():
    return redirect(url_for('auth.login'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect_based_on_role(current_user.role)

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            if user.status == 'Pending':
                flash('Your staff account is pending Admin approval.', 'warning')
                return redirect(url_for('auth.login'))
            if user.status in ['Inactive', 'Rejected']:
                flash('Your account has been deactivated or rejected.', 'danger')
                return redirect(url_for('auth.login'))
            login_user(user)
            return redirect_based_on_role(user.role)

        else:
            flash('Invalid email or password. Please try again.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect_based_on_role(current_user.role)

    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password') or ''
        role = request.form.get('role')  # 'user' or 'staff'
        contact_details = request.form.get('contact_details')
        if role not in ['user', 'staff']:
            flash('Invalid role selected.', 'danger')
            return redirect(url_for('auth.register'))
        if len(password) < 6:
            flash('Error: Password must be at least 6 characters long.', 'danger')
            return redirect(url_for('auth.register'))
        user_exists = User.query.filter_by(email=email).first()
        if user_exists:
            flash('Email address already registered.', 'warning')
            return redirect(url_for('auth.register'))
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

        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


def redirect_based_on_role(role):
    if role == 'admin':
        return redirect('/admin/dashboard')  # We will use url_for when admin routes are built
    elif role == 'staff':
        return redirect('/staff/dashboard')
    else:
        return redirect('/user/dashboard')
