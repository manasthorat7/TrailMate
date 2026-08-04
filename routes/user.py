from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from functools import wraps
from models import Trek, Booking
from database import db

user_bp = Blueprint('user', __name__, url_prefix='/user')


def user_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'user':
            flash('Access Denied. Trekker account required.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


@user_bp.route('/dashboard')
@login_required
@user_required
def dashboard():
    all_treks = Trek.query.order_by(Trek.start_date.asc()).all()
    return render_template('user/dashboard.html', treks=all_treks)


@user_bp.route('/treks/<int:trek_id>')
@login_required
@user_required
def trek_details(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    existing_booking = Booking.query.filter_by(user_id=current_user.id, trek_id=trek_id).first()
    has_booked = existing_booking is not None

    return render_template('user/trek_details.html', trek=trek, has_booked=has_booked)


@user_bp.route('/treks/<int:trek_id>/book', methods=['POST'])
@login_required
@user_required
def book_trek(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    if trek.status != 'Upcoming':
        flash('Booking failed. You can only book treks that are currently open (Upcoming).', 'danger')
        return redirect(url_for('user.trek_details', trek_id=trek_id))
    if trek.available_slots <= 0:
        flash('Booking failed. This trek is fully booked.', 'danger')
        return redirect(url_for('user.trek_details', trek_id=trek_id))
    existing_booking = Booking.query.filter_by(user_id=current_user.id, trek_id=trek_id).first()
    if existing_booking:
        flash('You have already booked this trek!', 'warning')
        return redirect(url_for('user.my_bookings'))
    new_booking = Booking(user_id=current_user.id, trek_id=trek_id, status='Confirmed')
    db.session.add(new_booking)
    trek.available_slots -= 1

    db.session.commit()
    flash(f'Successfully booked {trek.trek_name}!', 'success')
    return redirect(url_for('user.my_bookings'))


@user_bp.route('/my-bookings')
@login_required
@user_required
def my_bookings():
    bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.booking_date.desc()).all()
    return render_template('user/my_bookings.html', bookings=bookings)


@user_bp.route('/history')
@login_required
@user_required
def history():
    history_bookings = Booking.query.join(Trek).filter(
        Booking.user_id == current_user.id, Trek.status == 'Completed').all()
    return render_template('user/trekking_history.html', history=history_bookings)


@user_bp.route('/profile', methods=['GET', 'POST'])
@login_required
@user_required
def profile():
    if request.method == 'POST':
        current_user.name = request.form.get('name')
        current_user.contact_details = request.form.get('contact_details')
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('user.profile'))
    return render_template('user/profile.html')
