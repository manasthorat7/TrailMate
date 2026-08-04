from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import User
from database import db

# Create the authentication blueprint
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/', methods=['GET'])
def index():
    """Redirect root URL to login page."""
    return redirect(url_for('auth.login'))

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handles the login process and role-based redirection."""
    # If user is already logged in, redirect them based on their role
    if current_user.is_authenticated:
        return redirect_based_on_role(current_user.role)

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Look up the user in the database
        user = User.query.filter_by(email=email).first()
        
        # Check if user exists and password is correct
        if user and check_password_hash(user.password, password):
            
            # Prevent login if staff account is not yet approved
            if user.status == 'Pending':
                flash('Your staff account is pending Admin approval.', 'warning')
                return redirect(url_for('auth.login'))
                
            # Prevent login if account is deactivated
            if user.status == 'Inactive':
                flash('Your account has been deactivated.', 'danger')
                return redirect(url_for('auth.login'))
                
            # Log the user in
            login_user(user)
            return redirect_based_on_role(user.role)
            
        else:
            flash('Invalid email or password. Please try again.', 'danger')

    return render_template('auth/login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Handles new account creation for Users and Staff."""
    if current_user.is_authenticated:
        return redirect_based_on_role(current_user.role)

    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role') # 'user' or 'staff'
        contact_details = request.form.get('contact_details')
        
        # --- Validation Logic ---
        if len(password) < 6:
            flash('Error: Password must be at least 6 characters long.', 'danger')
            return redirect(url_for('auth.register'))
        # ------------------------
        
        # Check if email is already taken
        user_exists = User.query.filter_by(email=email).first()
        if user_exists:
            flash('Email address already registered.', 'warning')
            return redirect(url_for('auth.register'))
            
        # Determine initial status based on rules #6 and #7
        # Staff requires approval (Pending), Users do not (Active)
        initial_status = 'Pending' if role == 'staff' else 'Active'
        
        # Create new user
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
    """Logs out the current user and clears session."""
    logout_user()
    return redirect(url_for('auth.login'))

# Helper function to keep code DRY and small
def redirect_based_on_role(role):
    """Redirects to the correct dashboard based on the user's role."""
    if role == 'admin':
        return redirect('/admin/dashboard') # We will use url_for when admin routes are built
    elif role == 'staff':
        return redirect('/staff/dashboard')
    else:
        return redirect('/user/dashboard')
