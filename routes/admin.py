from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from functools import wraps
from models import User, Trek, Booking
from database import db
from datetime import datetime

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Custom decorator to enforce Admin access only
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Access Denied. Administrator privileges required.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    """Admin landing page with high-level statistics."""
    total_treks = Trek.query.count()
    total_users = User.query.filter_by(role='user').count()
    total_staff = User.query.filter_by(role='staff').count()
    total_bookings = Booking.query.count()
    recent_bookings = Booking.query.order_by(Booking.booking_date.desc()).limit(5).all()
    
    return render_template('admin/dashboard.html', 
                           total_treks=total_treks, 
                           total_users=total_users, 
                           total_staff=total_staff, 
                           total_bookings=total_bookings,
                           recent_bookings=recent_bookings)

@admin_bp.route('/treks')
@login_required
@admin_required
def manage_treks():
    """Lists all treks."""
    treks = Trek.query.all()
    return render_template('admin/treks.html', treks=treks)

@admin_bp.route('/treks/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_trek():
    """Handles adding a new trek to the database."""
    if request.method == 'POST':
        trek_name = request.form.get('trek_name')
        location = request.form.get('location')
        difficulty = request.form.get('difficulty')
        duration = request.form.get('duration')
        available_slots = request.form.get('available_slots')
        assigned_staff_id = request.form.get('assigned_staff_id') or None
        
        # Convert string dates to Python date objects
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        
        new_trek = Trek(
            trek_name=trek_name,
            location=location,
            difficulty=difficulty,
            duration=duration,
            available_slots=int(available_slots),
            assigned_staff_id=assigned_staff_id,
            start_date=start_date,
            end_date=end_date
        )
        
        db.session.add(new_trek)
        db.session.commit()
        flash('New trek successfully added.', 'success')
        return redirect(url_for('admin.manage_treks'))
        
    # GET request: fetch active staff to populate the dropdown
    active_staff = User.query.filter_by(role='staff', status='Active').all()
    return render_template('admin/add_trek.html', active_staff=active_staff)

@admin_bp.route('/staff', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_staff():
    """Lists all staff and handles approval/rejection of pending accounts."""
    if request.method == 'POST':
        staff_id = request.form.get('staff_id')
        action = request.form.get('action') # 'approve' or 'reject'
        
        staff_member = User.query.get(int(staff_id))
        if staff_member and staff_member.role == 'staff':
            if action == 'approve':
                staff_member.status = 'Active'
                flash(f'Staff account for {staff_member.name} approved.', 'success')
            elif action == 'reject':
                staff_member.status = 'Rejected' # Or we could delete it
                flash(f'Staff account for {staff_member.name} rejected.', 'danger')
            db.session.commit()
            
    # GET request: Show pending and active staff
    pending_staff = User.query.filter_by(role='staff', status='Pending').all()
    active_staff = User.query.filter_by(role='staff', status='Active').all()
    return render_template('admin/staff.html', pending_staff=pending_staff, active_staff=active_staff)

@admin_bp.route('/users')
@login_required
@admin_required
def manage_users():
    """Simple view to list all trekkers."""
    users = User.query.filter_by(role='user').all()
    return render_template('admin/users.html', users=users)

@admin_bp.route('/bookings')
@login_required
@admin_required
def view_bookings():
    """Simple view to list all bookings."""
    bookings = Booking.query.order_by(Booking.booking_date.desc()).all()
    return render_template('admin/bookings.html', bookings=bookings)
