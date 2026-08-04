from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from functools import wraps
from models import Trek, Booking
from database import db

user_bp = Blueprint('user', __name__, url_prefix='/user')

# Custom decorator to enforce User access only
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
    """Main dashboard displaying all treks."""
    # We display all treks, but handle booking rules in the details/book route
    all_treks = Trek.query.order_by(Trek.start_date.asc()).all()
    return render_template('user/dashboard.html', treks=all_treks)

@user_bp.route('/treks/<int:trek_id>')
@login_required
@user_required
def trek_details(trek_id):
    """View detailed information about a specific trek."""
    trek = Trek.query.get_or_404(trek_id)
    
    # Check if the user has already booked this trek
    existing_booking = Booking.query.filter_by(user_id=current_user.id, trek_id=trek_id).first()
    has_booked = existing_booking is not None
    
    return render_template('user/trek_details.html', trek=trek, has_booked=has_booked)

@user_bp.route('/treks/<int:trek_id>/book', methods=['POST'])
@login_required
@user_required
def book_trek(trek_id):
    """Handles the booking logic, enforcing business rules."""
    trek = Trek.query.get_or_404(trek_id)
    
    # RULE #10: User can only book Open/Upcoming treks
    if trek.status != 'Upcoming':
        flash('Booking failed. You can only book treks that are currently open (Upcoming).', 'danger')
        return redirect(url_for('user.trek_details', trek_id=trek_id))
        
    # RULE #9: Prevent overbooking
    if trek.available_slots <= 0:
        flash('Booking failed. This trek is fully booked.', 'danger')
        return redirect(url_for('user.trek_details', trek_id=trek_id))
        
    # Prevent double booking
    existing_booking = Booking.query.filter_by(user_id=current_user.id, trek_id=trek_id).first()
    if existing_booking:
        flash('You have already booked this trek!', 'warning')
        return redirect(url_for('user.my_bookings'))
        
    # Create the booking
    new_booking = Booking(user_id=current_user.id, trek_id=trek_id, status='Confirmed')
    db.session.add(new_booking)
    
    # Decrease available slots (Enforcing Rule #9)
    trek.available_slots -= 1
    
    db.session.commit()
    flash(f'Successfully booked {trek.trek_name}!', 'success')
    return redirect(url_for('user.my_bookings'))

@user_bp.route('/my-bookings')
@login_required
@user_required
def my_bookings():
    """View user's current and past bookings."""
    bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.booking_date.desc()).all()
    return render_template('user/my_bookings.html', bookings=bookings)
