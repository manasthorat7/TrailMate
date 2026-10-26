from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from functools import wraps
from models import Trek, Booking, CONFIRMED_PAYMENT_STATUSES
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
    assigned = Trek.query.filter_by(assigned_staff_id=current_user.id).all()
    total_assigned = len(assigned)
    open_count = sum(1 for trek in assigned if trek.status == 'Open')
    total_participants = Booking.query.join(Trek).filter(
        Trek.assigned_staff_id == current_user.id,
        Booking.status == 'Booked',
        Booking.payment_status.in_(CONFIRMED_PAYMENT_STATUSES),
    ).count()
    recent_bookings = Booking.query.join(Trek).filter(
        Trek.assigned_staff_id == current_user.id,
        Booking.status == 'Booked',
        Booking.payment_status.in_(CONFIRMED_PAYMENT_STATUSES),
    ).order_by(Booking.booking_date.desc()).limit(5).all()
    return render_template('staff/dashboard.html',
                           total_assigned=total_assigned,
                           open_count=open_count,
                           total_participants=total_participants,
                           recent_bookings=recent_bookings,
                           assigned_treks=assigned[:5])


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
    slots = request.form.get('available_slots')
    try:
        slots = int(slots)
    except (TypeError, ValueError):
        flash('Please enter a valid number of slots.', 'danger')
        return redirect(url_for('staff.assigned_treks'))

    if slots < 0:
        flash('Available slots cannot be negative.', 'danger')
        return redirect(url_for('staff.assigned_treks'))

    # Count all active reservations (pending and verified) because each one
    # currently holds a slot. Payment status does not free capacity by itself.
    reserved_count = Booking.query.filter_by(trek_id=trek.trek_id, status='Booked').count()
    if slots < reserved_count:
        flash('Slots cannot be less than current active reservations.', 'danger')
        return redirect(url_for('staff.assigned_treks'))

    if new_status in ['Open', 'Started', 'Completed']:
        trek.status = new_status
        trek.available_slots = slots
        db.session.commit()
        flash('Trek details updated.', 'success')
    else:
        flash('Please select a valid trek status.', 'danger')

    return redirect(url_for('staff.assigned_treks'))


@staff_bp.route('/treks/<int:trek_id>/participants')
@login_required
@staff_required
def participants(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    if trek.assigned_staff_id != current_user.id:
        flash('Unauthorized. You can only view participants for your own treks.', 'danger')
        return redirect(url_for('staff.assigned_treks'))
    bookings = Booking.query.filter(
        Booking.trek_id == trek_id,
        Booking.status.in_(['Booked', 'Completed']),
        Booking.payment_status.in_(CONFIRMED_PAYMENT_STATUSES),
    ).all()
    return render_template('staff/participants.html', trek=trek, bookings=bookings)


@staff_bp.route('/bookings/<int:booking_id>/cancel', methods=['POST'])
@login_required
@staff_required
def cancel_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    trek = Trek.query.get(booking.trek_id)
    if not trek or trek.assigned_staff_id != current_user.id:
        flash('Unauthorized. You can only manage participants for your own treks.', 'danger')
        return redirect(url_for('staff.assigned_treks'))
    
    if booking.status != 'Booked':
        flash('This booking is already cancelled or completed.', 'warning')
        return redirect(url_for('staff.participants', trek_id=trek.trek_id))

    try:
        claimed = Booking.query.filter_by(
            booking_id=booking.booking_id,
            status='Booked',
        ).update({Booking.status: 'Cancelled'}, synchronize_session=False)

        if claimed:
            Trek.query.filter_by(trek_id=trek.trek_id).update({
                Trek.available_slots: Trek.available_slots + 1
            }, synchronize_session=False)
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('Unable to cancel this participant right now. Please try again.', 'danger')
        return redirect(url_for('staff.participants', trek_id=trek.trek_id))

    if claimed:
        flash('Participant booking cancelled successfully.', 'success')
    else:
        flash('This booking is already cancelled or completed.', 'warning')
    return redirect(url_for('staff.participants', trek_id=trek.trek_id))
