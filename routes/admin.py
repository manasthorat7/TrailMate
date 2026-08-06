from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from functools import wraps
from models import User, Trek, Booking
from database import db
from datetime import datetime

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


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
    total_treks = Trek.query.count()
    total_users = User.query.filter_by(role='user').count()
    total_staff = User.query.filter_by(role='staff', status='Active').count()
    total_bookings = Booking.query.count()
    recent_bookings = Booking.query.order_by(Booking.booking_date.desc()).limit(5).all()
    open_treks = Trek.query.filter_by(status='Upcoming').order_by(Trek.start_date.asc()).limit(5).all()
    pending_staff = User.query.filter_by(role='staff', status='Pending').count()

    return render_template('admin/dashboard.html',
                           total_treks=total_treks,
                           total_users=total_users,
                           total_staff=total_staff,
                           total_bookings=total_bookings,
                           recent_bookings=recent_bookings,
                           open_treks=open_treks,
                           pending_staff=pending_staff)


@admin_bp.route('/treks')
@login_required
@admin_required
def manage_treks():
    search = request.args.get('search', '').strip()
    treks_query = Trek.query
    if search:
        treks_query = treks_query.filter(
            (Trek.trek_name.ilike(f'%{search}%')) |
            (Trek.location.ilike(f'%{search}%')) |
            (Trek.difficulty.ilike(f'%{search}%'))
        )
    treks = treks_query.order_by(Trek.start_date.asc()).all()
    return render_template('admin/treks.html', treks=treks, search=search)


@admin_bp.route('/treks/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_trek():
    if request.method == 'POST':
        trek_name = (request.form.get('trek_name') or '').strip()
        location = (request.form.get('location') or '').strip()
        difficulty = request.form.get('difficulty')
        duration = (request.form.get('duration') or '').strip()
        available_slots = request.form.get('available_slots')
        assigned_staff_id = request.form.get('assigned_staff_id') or None
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            slots_int = int(available_slots)
        except (TypeError, ValueError):
            flash('Error: Please enter valid trek details.', 'danger')
            return redirect(url_for('admin.add_trek'))
        if not trek_name or not location or not duration:
            flash('Error: Trek name, location and duration are required.', 'danger')
            return redirect(url_for('admin.add_trek'))
        if difficulty not in ['Easy', 'Moderate', 'Hard']:
            flash('Error: Please select a valid difficulty.', 'danger')
            return redirect(url_for('admin.add_trek'))
        if start_date > end_date:
            flash('Error: The End Date cannot be earlier than the Start Date.', 'danger')
            return redirect(url_for('admin.add_trek'))
        if slots_int <= 0:
            flash('Error: Available slots must be at least 1.', 'danger')
            return redirect(url_for('admin.add_trek'))
        if assigned_staff_id:
            try:
                assigned_staff_id = int(assigned_staff_id)
            except ValueError:
                flash('Error: Please select a valid approved staff member.', 'danger')
                return redirect(url_for('admin.add_trek'))
            assigned_staff = User.query.filter_by(id=assigned_staff_id, role='staff', status='Active').first()
            if not assigned_staff:
                flash('Error: Please select a valid approved staff member.', 'danger')
                return redirect(url_for('admin.add_trek'))
            assigned_staff_id = assigned_staff.id

        new_trek = Trek(
            trek_name=trek_name,
            location=location,
            difficulty=difficulty,
            duration=duration,
            available_slots=slots_int,
            assigned_staff_id=assigned_staff_id,
            start_date=start_date,
            end_date=end_date
        )

        db.session.add(new_trek)
        db.session.commit()
        flash('New trek successfully added.', 'success')
        return redirect(url_for('admin.manage_treks'))
    active_staff = User.query.filter_by(role='staff', status='Active').all()
    return render_template('admin/add_trek.html', active_staff=active_staff)


@admin_bp.route('/treks/<int:trek_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_trek(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    if request.method == 'POST':
        trek.trek_name = (request.form.get('trek_name') or '').strip()
        trek.location = (request.form.get('location') or '').strip()
        trek.difficulty = request.form.get('difficulty')
        trek.duration = (request.form.get('duration') or '').strip()
        assigned_staff_id = request.form.get('assigned_staff_id') or None

        try:
            slots_int = int(request.form.get('available_slots'))
            start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
            end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
        except (TypeError, ValueError):
            flash('Error: Please enter valid trek details.', 'danger')
            return redirect(url_for('admin.edit_trek', trek_id=trek.trek_id))
        if not trek.trek_name or not trek.location or not trek.duration:
            flash('Error: Trek name, location and duration are required.', 'danger')
            return redirect(url_for('admin.edit_trek', trek_id=trek.trek_id))
        if trek.difficulty not in ['Easy', 'Moderate', 'Hard']:
            flash('Error: Please select a valid difficulty.', 'danger')
            return redirect(url_for('admin.edit_trek', trek_id=trek.trek_id))

        if start_date > end_date:
            flash('Error: The End Date cannot be earlier than the Start Date.', 'danger')
            return redirect(url_for('admin.edit_trek', trek_id=trek.trek_id))
        if slots_int < 0:
            flash('Error: Available slots cannot be negative.', 'danger')
            return redirect(url_for('admin.edit_trek', trek_id=trek.trek_id))

        if assigned_staff_id:
            try:
                assigned_staff_id = int(assigned_staff_id)
            except ValueError:
                flash('Error: Please select a valid approved staff member.', 'danger')
                return redirect(url_for('admin.edit_trek', trek_id=trek.trek_id))
            assigned_staff = User.query.filter_by(id=assigned_staff_id, role='staff', status='Active').first()
            if not assigned_staff:
                flash('Error: Please select a valid approved staff member.', 'danger')
                return redirect(url_for('admin.edit_trek', trek_id=trek.trek_id))

        trek.available_slots = slots_int
        trek.assigned_staff_id = assigned_staff_id
        new_status = request.form.get('status')
        if new_status not in ['Upcoming', 'Ongoing', 'Completed']:
            flash('Error: Please select a valid trek status.', 'danger')
            return redirect(url_for('admin.edit_trek', trek_id=trek.trek_id))
        trek.status = new_status
        trek.start_date = start_date
        trek.end_date = end_date
        db.session.commit()
        flash('Trek updated successfully.', 'success')
        return redirect(url_for('admin.manage_treks'))

    active_staff = User.query.filter_by(role='staff', status='Active').all()
    return render_template('admin/add_trek.html', active_staff=active_staff, trek=trek)


@admin_bp.route('/treks/<int:trek_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_trek(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    if trek.bookings:
        flash('This trek has bookings, so it cannot be deleted. You can close it instead.', 'warning')
        return redirect(url_for('admin.manage_treks'))
    db.session.delete(trek)
    db.session.commit()
    flash('Trek deleted successfully.', 'success')
    return redirect(url_for('admin.manage_treks'))


@admin_bp.route('/staff', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_staff():
    if request.method == 'POST':
        staff_id = request.form.get('staff_id')
        action = request.form.get('action')

        try:
            staff_id = int(staff_id)
        except (TypeError, ValueError):
            flash('Invalid staff selected.', 'danger')
            return redirect(url_for('admin.manage_staff'))

        staff_member = User.query.get(staff_id)
        if staff_member and staff_member.role == 'staff':
            if action == 'approve':
                staff_member.status = 'Active'
                flash(f'Staff account for {staff_member.name} approved.', 'success')
            elif action == 'reject':
                staff_member.status = 'Rejected'
                flash(f'Staff account for {staff_member.name} rejected.', 'danger')
            elif action == 'deactivate':
                staff_member.status = 'Inactive'
                flash(f'{staff_member.name} has been blacklisted.', 'warning')
            elif action == 'activate':
                staff_member.status = 'Active'
                flash(f'{staff_member.name} is active again.', 'success')
            db.session.commit()
    search = request.args.get('search', '').strip()
    staff_query = User.query.filter_by(role='staff')
    if search:
        staff_query = staff_query.filter(
            (User.name.ilike(f'%{search}%')) |
            (User.email.ilike(f'%{search}%'))
        )
    staff_list = staff_query.order_by(User.name.asc()).all()
    return render_template('admin/staff.html', staff_list=staff_list, search=search)


@admin_bp.route('/users')
@login_required
@admin_required
def manage_users():
    search = request.args.get('search', '').strip()
    users_query = User.query.filter_by(role='user')
    if search:
        users_query = users_query.filter(
            (User.name.ilike(f'%{search}%')) |
            (User.email.ilike(f'%{search}%'))
        )
    users = users_query.order_by(User.name.asc()).all()
    return render_template('admin/users.html', users=users, search=search)


@admin_bp.route('/users/<int:user_id>/status', methods=['POST'])
@login_required
@admin_required
def update_user_status(user_id):
    user = User.query.get_or_404(user_id)
    if user.role != 'user':
        flash('Only trekker accounts can be changed here.', 'danger')
        return redirect(url_for('admin.manage_users'))
    action = request.form.get('action')
    if action == 'deactivate':
        user.status = 'Inactive'
        flash(f'{user.name} has been blacklisted.', 'warning')
    elif action == 'activate':
        user.status = 'Active'
        flash(f'{user.name} is active again.', 'success')
    db.session.commit()
    return redirect(url_for('admin.manage_users'))


@admin_bp.route('/bookings')
@login_required
@admin_required
def view_bookings():
    bookings = Booking.query.order_by(Booking.booking_date.desc()).all()
    return render_template('admin/bookings.html', bookings=bookings)
