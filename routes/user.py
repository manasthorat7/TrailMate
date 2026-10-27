from flask import Blueprint, render_template, redirect, url_for, request, flash, session
from flask_login import login_required, current_user
from functools import wraps
from models import (
    Trek, Booking, ACTIVE_RESERVATION_PAYMENT_STATUSES,
    EXPIRABLE_PAYMENT_STATUSES, PAYMENT_STATUS_VERIFIED,
)
from database import db
from datetime import datetime, timedelta
import razorpay_service
import os

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
def dashboard():
    """Public trek catalogue. Personal booking data stays user-scoped."""
    search = request.args.get('search', '').strip()
    difficulty = request.args.get('difficulty', '').strip()
    location = request.args.get('location', '').strip()

    trek_query = Trek.query.filter_by(status='Open')
    if search:
        trek_query = trek_query.filter(
            (Trek.trek_name.ilike(f'%{search}%')) |
            (Trek.location.ilike(f'%{search}%'))
        )
    if difficulty:
        trek_query = trek_query.filter_by(difficulty=difficulty)
    if location:
        trek_query = trek_query.filter_by(location=location)

    all_treks = trek_query.order_by(Trek.start_date.asc()).all()
    locations = [row[0] for row in db.session.query(Trek.location).distinct().order_by(Trek.location).all()]

    my_recent_bookings = []
    if current_user.is_authenticated and current_user.role == 'user':
        my_recent_bookings = Booking.query.filter_by(user_id=current_user.id).order_by(
            Booking.booking_date.desc()).limit(3).all()

    return render_template('user/dashboard.html',
                           treks=all_treks,
                           locations=locations,
                           search=search,
                           difficulty=difficulty,
                           location=location,
                           my_recent_bookings=my_recent_bookings)


@user_bp.route('/treks/<int:trek_id>')
def trek_details(trek_id):
    """Public trek details. Booking remains protected in book_trek()."""
    trek = Trek.query.get_or_404(trek_id)

    has_booked = False
    if current_user.is_authenticated and current_user.role == 'user':
        existing_booking = Booking.query.filter(
            Booking.user_id == current_user.id,
            Booking.trek_id == trek_id,
            Booking.status != 'Cancelled',
            Booking.payment_status.in_(ACTIVE_RESERVATION_PAYMENT_STATUSES)
        ).first()
        has_booked = existing_booking is not None

    return render_template('user/trek_details.html', trek=trek, has_booked=has_booked)


@user_bp.route('/treks/<int:trek_id>/book', methods=['POST'])
@login_required
@user_required
def book_trek(trek_id):
    """
    Create a pending booking and Razorpay order, reserve slot transactionally.
    Never confirm without server-side verification.
    """
    trek = Trek.query.get_or_404(trek_id)

    # Expire old pending orders for this user/trek to free slots
    _expire_pending_bookings()

    if trek.price is None:
        flash('Booking unavailable. This trek does not have a valid price yet.', 'danger')
        return redirect(url_for('user.trek_details', trek_id=trek_id))

    if trek.status != 'Open':
        flash('Booking failed. You can only book treks that are currently open (Open).', 'danger')
        return redirect(url_for('user.trek_details', trek_id=trek_id))
    if trek.available_slots <= 0:
        flash('Booking failed. This trek is fully booked.', 'danger')
        return redirect(url_for('user.trek_details', trek_id=trek_id))

    # Prevent duplicate pending/active bookings
    existing_booking = Booking.query.filter(
        Booking.user_id == current_user.id,
        Booking.trek_id == trek_id,
        Booking.status != 'Cancelled'
    ).filter(
        Booking.payment_status.in_(ACTIVE_RESERVATION_PAYMENT_STATUSES)
    ).first()
    if existing_booking:
        if existing_booking.payment_status == 'Verified' and existing_booking.status == 'Booked':
            flash('You have already booked this trek!', 'warning')
            return redirect(url_for('user.my_bookings'))
        # If pending/unpaid/failed, redirect to checkout if order exists
        if existing_booking.razorpay_order_id:
            return redirect(url_for('user.checkout', booking_id=existing_booking.booking_id))
        flash('You already have an active reservation for this trek.', 'warning')
        return redirect(url_for('user.my_bookings'))

    if not razorpay_service.is_configured():
        flash('Payments are not configured. Please contact administrator.', 'danger')
        return redirect(url_for('user.trek_details', trek_id=trek_id))

    try:
        # Transactional reservation
        with db.session.begin_nested():
            trek_locked = Trek.query.filter_by(trek_id=trek_id).with_for_update().first()
            if not trek_locked or trek_locked.status != 'Open' or trek_locked.available_slots <= 0:
                flash('Booking failed. Trek no longer available.', 'danger')
                return redirect(url_for('user.trek_details', trek_id=trek_id))

            # Amount derived server-side from persisted Trek price (INR).
            from decimal import Decimal
            price = trek_locked.price
            if price is None:
                raise ValueError('missing trek price')
            amount_paise = int((Decimal(str(price)) * 100).to_integral_value())
            currency = os.environ.get('PAYMENT_CURRENCY', 'INR')

            order = razorpay_service.create_order(
                amount=amount_paise,
                receipt=f'tm_{current_user.id}_{trek_id}_{int(datetime.utcnow().timestamp())}',
                notes={'user_id': current_user.id, 'trek_id': trek_id},
                currency=currency
            )

            new_booking = Booking(
                user_id=current_user.id,
                trek_id=trek_id,
                status='Booked',  # will be confirmed only after verification; but we need to track payment
                payment_status='Pending',
                amount=float(price),
                currency=currency,
                razorpay_order_id=order.get('id')
            )
            db.session.add(new_booking)
            trek_locked.available_slots -= 1

        db.session.commit()
        return redirect(url_for('user.checkout', booking_id=new_booking.booking_id))
    except Exception as e:
        db.session.rollback()
        flash('Failed to initiate payment. Please try again.', 'danger')
        return redirect(url_for('user.trek_details', trek_id=trek_id))



@user_bp.route('/checkout/<int:booking_id>')
@login_required
@user_required
def checkout(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.user_id != current_user.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('user.my_bookings'))
    if booking.payment_status == 'Verified' and booking.status == 'Booked':
        flash('This booking is already confirmed.', 'info')
        return redirect(url_for('user.my_bookings'))
    if booking.status != 'Booked' or booking.payment_status not in EXPIRABLE_PAYMENT_STATUSES:
        flash('This booking is no longer valid. Please book again.', 'warning')
        return redirect(url_for('user.dashboard'))
    if not booking.razorpay_order_id or not razorpay_service.is_configured():
        flash('Payment information missing or not configured.', 'danger')
        return redirect(url_for('user.my_bookings'))
    trek = Trek.query.get(booking.trek_id)
    return render_template('user/checkout.html',
                           booking=booking,
                           trek=trek,
                           razorpay_key_id=os.environ.get('RAZORPAY_KEY_ID') or '')


@user_bp.route('/payment/verify', methods=['POST'])
@login_required
@user_required
def verify_payment():
    # Expire old pending orders before accepting a callback.
    _expire_pending_bookings()

    is_json = request.is_json
    payload = request.get_json(silent=True) if is_json else request.form
    if not isinstance(payload, dict):
        payload = {}

    def _field(name):
        return str(payload.get(name) or '').strip()

    razorpay_order_id = _field('razorpay_order_id')
    razorpay_payment_id = _field('razorpay_payment_id')
    razorpay_signature = _field('razorpay_signature')

    def _error(message, status_code=400, category='danger'):
        if is_json:
            return {'status': 'error', 'message': message}, status_code
        flash(message, category)
        return redirect(url_for('user.my_bookings'))

    def _success(message, status_code=200):
        if is_json:
            return {'status': 'success', 'message': message}, status_code
        flash(message, 'success')
        return redirect(url_for('user.my_bookings'))

    if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
        return _error('Payment verification failed: missing details.')

    booking = Booking.query.filter_by(razorpay_order_id=razorpay_order_id).first()
    if not booking:
        return _error('Payment verification failed: order not found.', 404)
    if booking.user_id != current_user.id:
        return _error('Payment verification failed: unauthorized.', 403)

    # Duplicate callback: record nothing new and never change an existing outcome.
    if booking.payment_status == PAYMENT_STATUS_VERIFIED:
        return _success('Payment already verified. Booking confirmed.')

    # A late callback must never resurrect a cancelled or completed booking.
    if booking.status != 'Booked':
        return _error(
            'Payment callback ignored: this booking is already cancelled or completed.',
            409, 'warning'
        )
    if booking.payment_status not in EXPIRABLE_PAYMENT_STATUSES:
        return _error(
            'Payment callback ignored: this booking is not awaiting payment.',
            409, 'warning'
        )

    # Verify signature server-side. An invalid signature is only a failed
    # attempt: keep the slot reserved until expiry, because a client-supplied
    # failure message is not proof that no money was captured.
    if not razorpay_service.verify_payment_signature(
        razorpay_order_id, razorpay_payment_id, razorpay_signature
    ):
        try:
            Booking.query.filter(
                Booking.booking_id == booking.booking_id,
                Booking.status == 'Booked',
                Booking.payment_status.in_(EXPIRABLE_PAYMENT_STATUSES),
            ).update({
                Booking.payment_status: 'Failed',
                Booking.razorpay_payment_id: razorpay_payment_id,
                Booking.razorpay_signature: razorpay_signature,
            }, synchronize_session=False)
            db.session.commit()
        except Exception:
            db.session.rollback()
        return _error('Payment verification failed. Invalid signature.')

    # Atomic transition prevents a concurrent expiry/cancel from being
    # overwritten by this callback.
    try:
        updated = Booking.query.filter(
            Booking.booking_id == booking.booking_id,
            Booking.status == 'Booked',
            Booking.payment_status.in_(EXPIRABLE_PAYMENT_STATUSES),
        ).update({
            Booking.payment_status: PAYMENT_STATUS_VERIFIED,
            Booking.razorpay_payment_id: razorpay_payment_id,
            Booking.razorpay_signature: razorpay_signature,
        }, synchronize_session=False)
        if updated != 1:
            db.session.rollback()
            return _error(
                'Payment callback ignored: this booking is no longer active.',
                409, 'warning'
            )
        db.session.commit()
    except Exception:
        db.session.rollback()
        return _error(
            'Payment verification encountered an error. Please contact support.',
            500
        )

    return _success('Payment successful! Booking confirmed.')


@user_bp.route('/my-bookings')
@login_required
@user_required
def my_bookings():
    # Expire old pending bookings on access
    _expire_pending_bookings()
    bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.booking_date.desc()).all()
    return render_template('user/my_bookings.html', bookings=bookings)


def _expire_pending_bookings():
    """
    Expire pending/unpaid/failed bookings older than
    PAYMENT_PENDING_EXPIRY_MINUTES and release each reserved slot exactly once.

    Only an active 'Booked' booking with a non-verified payment can expire.
    Legacy, verified, completed, and cancelled bookings are never touched.
    This is not a scheduler - call it on relevant requests or run via cron.

    Returns the number of bookings expired by this call.
    """
    try:
        expiry_minutes = int(os.environ.get('PAYMENT_PENDING_EXPIRY_MINUTES', '15'))
    except Exception:
        expiry_minutes = 15
    cutoff = datetime.utcnow() - timedelta(minutes=expiry_minutes)

    candidates = Booking.query.filter(
        Booking.status == 'Booked',
        Booking.payment_status.in_(EXPIRABLE_PAYMENT_STATUSES),
        Booking.booking_date < cutoff
    ).all()

    if not candidates:
        return 0

    expired_count = 0
    try:
        for booking in candidates:
            # Claim the booking atomically. A concurrent callback or cancel
            # will either win this update or be rejected by verify_payment.
            claimed = Booking.query.filter(
                Booking.booking_id == booking.booking_id,
                Booking.status == 'Booked',
                Booking.payment_status.in_(EXPIRABLE_PAYMENT_STATUSES),
            ).update({
                Booking.status: 'Cancelled',
                Booking.payment_status: 'Failed',
            }, synchronize_session=False)

            if claimed:
                Trek.query.filter_by(trek_id=booking.trek_id).update({
                    Trek.available_slots: Trek.available_slots + 1
                }, synchronize_session=False)
                expired_count += 1
        db.session.commit()
    except Exception:
        db.session.rollback()
    return expired_count



@user_bp.route('/bookings/<int:booking_id>/cancel', methods=['POST'])
@login_required
@user_required
def cancel_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.user_id != current_user.id:
        flash('You can cancel only your own booking.', 'danger')
        return redirect(url_for('user.my_bookings'))
    if booking.status != 'Booked':
        flash('This booking is already cancelled or completed.', 'warning')
        return redirect(url_for('user.my_bookings'))
    if booking.trek.status == 'Completed':
        flash('Completed trek booking cannot be cancelled.', 'warning')
        return redirect(url_for('user.my_bookings'))
    if booking.trek.status == 'Started':
        flash('Started trek booking cannot be cancelled.', 'warning')
        return redirect(url_for('user.my_bookings'))

    try:
        # Atomic status transition ensures the slot is released at most once
        # even if two cancel requests arrive together.
        claimed = Booking.query.filter_by(
            booking_id=booking.booking_id,
            status='Booked',
        ).update({Booking.status: 'Cancelled'}, synchronize_session=False)

        if claimed:
            Trek.query.filter_by(trek_id=booking.trek_id).update({
                Trek.available_slots: Trek.available_slots + 1
            }, synchronize_session=False)
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('Unable to cancel this booking right now. Please try again.', 'danger')
        return redirect(url_for('user.my_bookings'))

    if claimed:
        flash('Booking cancelled successfully.', 'success')
    else:
        flash('This booking is already cancelled or completed.', 'warning')
    return redirect(url_for('user.my_bookings'))


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
        name = (request.form.get('name') or '').strip()
        if not name:
            flash('Name cannot be empty.', 'danger')
            return redirect(url_for('user.profile'))
        current_user.name = name
        current_user.contact_details = (request.form.get('contact_details') or '').strip()
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('user.profile'))
    return render_template('user/profile.html')
