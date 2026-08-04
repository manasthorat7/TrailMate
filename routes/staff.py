from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from functools import wraps
from models import Trek, Booking
from database import db

staff_bp = Blueprint('staff', __name__, url_prefix='/staff')


def staff_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'staff':
            flash('Access Denied. Staff privileges required.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


@staff_bp.route('/dashboard')
@login_required
@staff_required
def dashboard():
    total_assigned = Trek.query.filter_by(assigned_staff_id=current_user.id).count()
    return render_template('staff/dashboard.html', total_assigned=total_assigned)


@staff_bp.route('/assigned-treks')
@login_required
@staff_required
def assigned_treks():
    my_treks = Trek.query.filter_by(assigned_staff_id=current_user.id).all()
    return render_template('staff/assigned_treks.html', treks=my_treks)


@staff_bp.route('/treks/<int:trek_id>/update', methods=['POST'])
@login_required
@staff_required
def update_status(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    if trek.assigned_staff_id != current_user.id:
        flash('Unauthorized. You can only manage treks assigned to you.', 'danger')
        return redirect(url_for('staff.assigned_treks'))

    new_status = request.form.get('status')
    if new_status in ['Upcoming', 'Ongoing', 'Completed']:
        trek.status = new_status
        db.session.commit()
        flash(f'Trek status updated to {new_status}.', 'success')

    return redirect(url_for('staff.assigned_treks'))


@staff_bp.route('/treks/<int:trek_id>/participants')
@login_required
@staff_required
def participants(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    if trek.assigned_staff_id != current_user.id:
        flash('Unauthorized. You can only view participants for your own treks.', 'danger')
        return redirect(url_for('staff.assigned_treks'))
    bookings = Booking.query.filter_by(trek_id=trek_id, status='Confirmed').all()
    return render_template('staff/participants.html', trek=trek, bookings=bookings)
