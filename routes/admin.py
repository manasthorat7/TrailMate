from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from functools import wraps
from models import (
    User, Trek, Booking, CONFIRMED_PAYMENT_STATUSES,
    EXPIRABLE_PAYMENT_STATUSES, PAYMENT_STATUS_VERIFIED,
)
from database import db
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation
from sqlalchemy import func
from sqlalchemy.orm import joinedload
import cloudinary_service

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# ---------------------------------------------------------------------------
# Analytics configuration
#
# These values document the exact rules used by the dashboard. They are kept
# here (rather than in templates) so every metric has one server-side source
# of truth.
# ---------------------------------------------------------------------------
BOOKING_TREND_WINDOW_DAYS = 30   # Rolling daily window, today inclusive
POPULAR_TREK_LIMIT = 5           # Chart C shows the top five treks
LOW_CAPACITY_THRESHOLD = 3       # Remaining slots considered "low"
INSIGHT_LIST_LIMIT = 5           # Rows per operational insight list

# "Confirmed" means an active or completed reservation whose payment is
# either Razorpay-verified or a pre-Razorpay legacy record.
CONFIRMED_BOOKING_STATUSES = ('Booked', 'Completed')
# "Pending payments" are active reservations whose payment has not been
# verified yet (Pending / Unpaid / Failed).
PENDING_PAYMENT_STATUSES = EXPIRABLE_PAYMENT_STATUSES


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Access Denied. Administrator privileges required.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def format_currency(currency, amount):
    """Format an amount consistently, e.g. ``INR 1,000.00``."""
    currency = (currency or 'INR').strip() or 'INR'
    try:
        value = float(amount or 0)
    except (TypeError, ValueError):
        value = 0.0
    return f'{currency} {value:,.2f}'


def _as_date(value):
    """Normalise SQL date/string results from different database dialects."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _booking_trend(today=None):
    """
    Daily booking counts for the last ``BOOKING_TREND_WINDOW_DAYS`` days.

    Counting rule: every booking record is counted once by its
    ``booking_date`` (creation date), regardless of its current status. This
    measures booking activity, not confirmed revenue.
    """
    today = today or date.today()
    start_day = today - timedelta(days=BOOKING_TREND_WINDOW_DAYS - 1)
    start_dt = datetime.combine(start_day, datetime.min.time())

    rows = (
        db.session.query(
            func.date(Booking.booking_date).label('booking_day'),
            func.count(Booking.booking_id),
        )
        .filter(Booking.booking_date >= start_dt)
        .group_by(func.date(Booking.booking_date))
        .all()
    )

    counts = {}
    for day_value, count in rows:
        day = _as_date(day_value)
        if day is None:
            continue
        counts[day] = counts.get(day, 0) + int(count or 0)

    labels, values = [], []
    for offset in range(BOOKING_TREND_WINDOW_DAYS):
        day = start_day + timedelta(days=offset)
        labels.append(day.strftime('%b %d'))
        values.append(counts.get(day, 0))

    return {
        'labels': labels,
        'values': values,
        'window_days': BOOKING_TREND_WINDOW_DAYS,
        'start_date': start_day.isoformat(),
        'end_date': today.isoformat(),
        'total': int(sum(values)),
    }


def _booking_status_distribution():
    """
    Booking-status counts (Booked / Cancelled / Completed), kept separate from
    payment status. Unknown future statuses are rendered verbatim.
    """
    rows = (
        db.session.query(Booking.status, func.count(Booking.booking_id))
        .group_by(Booking.status)
        .all()
    )

    items = [
        {'status': (status or 'Unknown'), 'count': int(count or 0)}
        for status, count in rows
    ]
    items.sort(key=lambda item: (-item['count'], item['status']))

    return {
        'labels': [item['status'] for item in items],
        'values': [item['count'] for item in items],
        'total': sum(item['count'] for item in items),
    }


def _popular_treks(limit=POPULAR_TREK_LIMIT):
    """
    Top treks by booking count.

    Counting rule: cancelled bookings are excluded, because the chart reflects
    participation/demand rather than historical attempts. Ties are broken by
    trek name for a stable ordering.
    """
    rows = (
        db.session.query(
            Trek.trek_id,
            Trek.trek_name,
            func.count(Booking.booking_id).label('booking_count'),
        )
        .join(Booking, Booking.trek_id == Trek.trek_id)
        .filter(Booking.status != 'Cancelled')
        .group_by(Trek.trek_id, Trek.trek_name)
        .order_by(func.count(Booking.booking_id).desc(), Trek.trek_name.asc())
        .limit(limit)
        .all()
    )

    return [
        {
            'trek_id': row[0],
            'trek_name': row[1] or 'Unnamed trek',
            'count': int(row[2] or 0),
        }
        for row in rows
    ]


def _verified_revenue():
    """
    Verified revenue, grouped by currency.

    Only bookings whose Razorpay signature was verified are counted.
    Pending, Unpaid, Failed and Legacy payments are excluded, and cancelled
    bookings are excluded because refunds are not tracked by the application.
    Amounts are the server-stored booking amount, which is the same value used
    to create the Razorpay order.
    """
    rows = (
        db.session.query(Booking.currency, func.sum(Booking.amount))
        .filter(
            Booking.payment_status == PAYMENT_STATUS_VERIFIED,
            Booking.status.in_(CONFIRMED_BOOKING_STATUSES),
            Booking.amount.isnot(None),
        )
        .group_by(Booking.currency)
        .all()
    )

    breakdown = []
    for currency, total in rows:
        value = float(total or 0)
        breakdown.append({
            'currency': currency or 'INR',
            'amount': round(value, 2),
            'display': format_currency(currency, value),
        })
    breakdown.sort(key=lambda item: item['currency'])

    return {
        'breakdown': breakdown,
        'displays': [item['display'] for item in breakdown],
        'primary': breakdown[0]['display'] if breakdown else format_currency('INR', 0),
        'is_empty': not breakdown,
    }


def _operational_insights(today=None, limit=INSIGHT_LIST_LIMIT):
    """
    Compact, schema-supported operational lists. No customer contact details
    or payment secrets are exposed.
    """
    today = today or date.today()

    upcoming_filters = (Trek.start_date > today, Trek.status != 'Completed')
    low_capacity_filters = (
        Trek.status == 'Open',
        Trek.start_date > today,
        Trek.available_slots <= LOW_CAPACITY_THRESHOLD,
    )
    unassigned_filters = (Trek.assigned_staff_id.is_(None), Trek.status != 'Completed')
    pending_filters = (
        Booking.status == 'Booked',
        Booking.payment_status.in_(PENDING_PAYMENT_STATUSES),
    )

    upcoming_treks = (
        Trek.query.filter(*upcoming_filters)
        .order_by(Trek.start_date.asc(), Trek.trek_name.asc())
        .limit(limit)
        .all()
    )
    low_capacity_treks = (
        Trek.query.filter(*low_capacity_filters)
        .order_by(Trek.available_slots.asc(), Trek.start_date.asc())
        .limit(limit)
        .all()
    )
    unassigned_treks = (
        Trek.query.filter(*unassigned_filters)
        .order_by(Trek.start_date.asc(), Trek.trek_name.asc())
        .limit(limit)
        .all()
    )
    pending_bookings = (
        Booking.query.options(joinedload(Booking.trek))
        .filter(*pending_filters)
        .order_by(Booking.booking_date.asc())
        .limit(limit)
        .all()
    )

    return {
        'upcoming_treks': upcoming_treks,
        'upcoming_count': Trek.query.filter(*upcoming_filters).count(),
        'low_capacity_treks': low_capacity_treks,
        'low_capacity_count': Trek.query.filter(*low_capacity_filters).count(),
        'low_capacity_threshold': LOW_CAPACITY_THRESHOLD,
        'unassigned_treks': unassigned_treks,
        'unassigned_count': Trek.query.filter(*unassigned_filters).count(),
        'pending_bookings': pending_bookings,
        'pending_count': Booking.query.filter(*pending_filters).count(),
    }


def build_dashboard_analytics(today=None):
    """
    Build every dashboard metric server-side.

    Metric definitions:
      * Total bookings      - all booking records.
      * Confirmed bookings  - status Booked/Completed with payment Verified/Legacy.
      * Upcoming expeditions- treks starting after today and not Completed.
      * Verified revenue    - sum of amounts on Verified, non-cancelled bookings.
      * Pending payments    - Booked reservations with Pending/Unpaid/Failed payment.

    A verified-revenue *trend* is intentionally not produced: the schema stores
    no payment-verification timestamp, so revenue cannot be attributed to the
    date it was actually collected.
    """
    today = today or date.today()

    total_bookings = db.session.query(func.count(Booking.booking_id)).scalar() or 0
    confirmed_bookings = (
        db.session.query(func.count(Booking.booking_id))
        .filter(
            Booking.status.in_(CONFIRMED_BOOKING_STATUSES),
            Booking.payment_status.in_(CONFIRMED_PAYMENT_STATUSES),
        )
        .scalar() or 0
    )
    upcoming_expeditions = (
        db.session.query(func.count(Trek.trek_id))
        .filter(Trek.start_date > today, Trek.status != 'Completed')
        .scalar() or 0
    )
    pending_payments = (
        db.session.query(func.count(Booking.booking_id))
        .filter(Booking.status == 'Booked', Booking.payment_status.in_(PENDING_PAYMENT_STATUSES))
        .scalar() or 0
    )

    return {
        'kpis': {
            'total_bookings': int(total_bookings),
            'confirmed_bookings': int(confirmed_bookings),
            'upcoming_expeditions': int(upcoming_expeditions),
            'pending_payments': int(pending_payments),
        },
        'verified_revenue': _verified_revenue(),
        'booking_trend': _booking_trend(today),
        'booking_status': _booking_status_distribution(),
        'popular_treks': _popular_treks(),
        'insights': _operational_insights(today),
    }


@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    analytics = build_dashboard_analytics()

    total_treks = Trek.query.count()
    total_users = User.query.filter_by(role='user').count()
    total_staff = User.query.filter_by(role='staff', status='Active').count()
    recent_bookings = (
        Booking.query.options(joinedload(Booking.user), joinedload(Booking.trek))
        .order_by(Booking.booking_date.desc())
        .limit(5)
        .all()
    )
    open_treks = Trek.query.filter_by(status='Open').order_by(Trek.start_date.asc()).limit(5).all()
    pending_staff = User.query.filter_by(role='staff', status='Pending').count()

    return render_template('admin/dashboard.html',
                           analytics=analytics,
                           total_treks=total_treks,
                           total_users=total_users,
                           total_staff=total_staff,
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
    return render_template('admin/treks.html', treks=treks, search=search,
                           cloudinary_configured=cloudinary_service.is_cloudinary_configured())


def _parse_trek_form(form, redirect_target):
    """
    Parse and validate common trek form fields.
    Returns (fields_dict, error_response) — if error_response is not None,
    the caller should return it immediately.
    """
    trek_name = (form.get('trek_name') or '').strip()
    location = (form.get('location') or '').strip()
    difficulty = form.get('difficulty')
    duration = (form.get('duration') or '').strip()
    available_slots = form.get('available_slots')
    assigned_staff_id = form.get('assigned_staff_id') or None
    start_date_str = form.get('start_date')
    end_date_str = form.get('end_date')
    price_raw = (form.get('price') or '').strip()

    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        slots_int = int(available_slots)
    except (TypeError, ValueError):
        flash('Error: Please enter valid trek details.', 'danger')
        return None, redirect(redirect_target)

    # Validate required trek price (INR), decimal, finite, positive.
    try:
        price = Decimal(price_raw)
    except (InvalidOperation, ValueError, TypeError):
        flash('Error: Please enter a valid trek price in INR.', 'danger')
        return None, redirect(redirect_target)
    if not price_raw or price.is_nan() or price.is_infinite():
        flash('Error: Please enter a valid trek price in INR.', 'danger')
        return None, redirect(redirect_target)
    if price <= 0:
        flash('Error: Trek price must be greater than zero.', 'danger')
        return None, redirect(redirect_target)
    if price > Decimal('9999999.99'):
        flash('Error: Trek price is too large.', 'danger')
        return None, redirect(redirect_target)
    price = price.quantize(Decimal('0.01'))

    if not trek_name or not location or not duration:
        flash('Error: Trek name, location and duration are required.', 'danger')
        return None, redirect(redirect_target)
    if difficulty not in ['Easy', 'Moderate', 'Hard']:
        flash('Error: Please select a valid difficulty.', 'danger')
        return None, redirect(redirect_target)
    if start_date > end_date:
        flash('Error: The End Date cannot be earlier than the Start Date.', 'danger')
        return None, redirect(redirect_target)
    if slots_int < 0:
        flash('Error: Available slots cannot be negative.', 'danger')
        return None, redirect(redirect_target)

    resolved_staff_id = None
    if assigned_staff_id:
        try:
            assigned_staff_id = int(assigned_staff_id)
        except ValueError:
            flash('Error: Please select a valid approved staff member.', 'danger')
            return None, redirect(redirect_target)
        assigned_staff = User.query.filter_by(id=assigned_staff_id, role='staff', status='Active').first()
        if not assigned_staff:
            flash('Error: Please select a valid approved staff member.', 'danger')
            return None, redirect(redirect_target)
        resolved_staff_id = assigned_staff.id

    return {
        'trek_name': trek_name,
        'location': location,
        'difficulty': difficulty,
        'duration': duration,
        'available_slots': slots_int,
        'assigned_staff_id': resolved_staff_id,
        'start_date': start_date,
        'end_date': end_date,
        'price': price,
    }, None


def _handle_image_upload(file_storage, current_public_id=None):
    """
    Attempt to upload a new image to Cloudinary.

    Returns (new_image_url, new_public_id, had_error).
    If had_error is True, the caller should flash an appropriate message
    and abort the save (the existing image is preserved).
    """
    if not file_storage or not file_storage.filename:
        # No file supplied — keep current image unchanged
        return None, None, False

    ok, err = cloudinary_service.validate_upload(file_storage)
    if not ok:
        flash(f'Image upload error: {err}', 'danger')
        return None, None, True

    if not cloudinary_service.is_cloudinary_configured():
        flash('Cloudinary is not configured. Image was not uploaded. '
              'Set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET.', 'warning')
        return None, None, True

    try:
        result = cloudinary_service.upload_trek_image(file_storage)
    except RuntimeError as exc:
        flash(f'Image upload failed: {exc} — trek data was preserved.', 'danger')
        return None, None, True

    return result['url'], result['public_id'], False


@admin_bp.route('/treks/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_trek():
    if request.method == 'POST':
        fields, err = _parse_trek_form(
            request.form,
            redirect_target=url_for('admin.add_trek')
        )
        if err:
            return err

        # Validate slots > 0 for new treks
        if fields['available_slots'] <= 0:
            flash('Error: Available slots must be at least 1.', 'danger')
            return redirect(url_for('admin.add_trek'))

        # Handle optional image upload
        image_file = request.files.get('trek_image')
        image_url = None
        image_public_id = None

        if image_file and image_file.filename:
            new_url, new_pid, had_error = _handle_image_upload(image_file)
            if had_error:
                # Re-render the form with validation errors; do NOT save the trek yet
                active_staff = User.query.filter_by(role='staff', status='Active').all()
                return render_template('admin/add_trek.html', active_staff=active_staff,
                                       cloudinary_configured=cloudinary_service.is_cloudinary_configured())
            image_url = new_url
            image_public_id = new_pid

        new_trek = Trek(
            trek_name=fields['trek_name'],
            location=fields['location'],
            difficulty=fields['difficulty'],
            duration=fields['duration'],
            available_slots=fields['available_slots'],
            assigned_staff_id=fields['assigned_staff_id'],
            start_date=fields['start_date'],
            end_date=fields['end_date'],
            image_url=image_url,
            image_public_id=image_public_id,
            price=fields['price'],
        )

        db.session.add(new_trek)
        db.session.commit()
        flash('New trek successfully added.', 'success')
        return redirect(url_for('admin.manage_treks'))

    active_staff = User.query.filter_by(role='staff', status='Active').all()
    return render_template('admin/add_trek.html', active_staff=active_staff,
                           cloudinary_configured=cloudinary_service.is_cloudinary_configured())


@admin_bp.route('/treks/<int:trek_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_trek(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    if request.method == 'POST':
        fields, err = _parse_trek_form(
            request.form,
            redirect_target=url_for('admin.edit_trek', trek_id=trek.trek_id)
        )
        if err:
            return err

        new_status = request.form.get('status')
        if new_status not in ['Open', 'Started', 'Completed']:
            flash('Error: Please select a valid trek status.', 'danger')
            return redirect(url_for('admin.edit_trek', trek_id=trek.trek_id))

        # ---------------------------------------------------------------
        # Image replacement: upload first, then update DB, then delete old
        # ---------------------------------------------------------------
        image_file = request.files.get('trek_image')
        new_url = None
        new_pid = None

        if image_file and image_file.filename:
            new_url, new_pid, had_error = _handle_image_upload(
                image_file, current_public_id=trek.image_public_id
            )
            if had_error:
                # Preserve existing trek data; stay on edit form
                active_staff = User.query.filter_by(role='staff', status='Active').all()
                return render_template('admin/add_trek.html', active_staff=active_staff,
                                       trek=trek,
                                       cloudinary_configured=cloudinary_service.is_cloudinary_configured())

        # Capture old public_id before overwriting it in the DB
        old_public_id = trek.image_public_id if new_pid else None

        # Update all fields atomically
        trek.trek_name = fields['trek_name']
        trek.location = fields['location']
        trek.difficulty = fields['difficulty']
        trek.duration = fields['duration']
        trek.available_slots = fields['available_slots']
        trek.assigned_staff_id = fields['assigned_staff_id']
        trek.status = new_status
        trek.start_date = fields['start_date']
        trek.end_date = fields['end_date']
        trek.price = fields['price']

        if new_url:
            trek.image_url = new_url
            trek.image_public_id = new_pid

        db.session.commit()

        # Only delete the previous Cloudinary asset AFTER the DB commit succeeds
        if old_public_id:
            deleted = cloudinary_service.delete_trek_image(old_public_id)
            if not deleted:
                flash('Trek updated, but the previous Cloudinary image could not be '
                      'deleted and may need manual cleanup.', 'warning')

        flash('Trek updated successfully.', 'success')
        return redirect(url_for('admin.manage_treks'))

    active_staff = User.query.filter_by(role='staff', status='Active').all()
    return render_template('admin/add_trek.html', active_staff=active_staff, trek=trek,
                           cloudinary_configured=cloudinary_service.is_cloudinary_configured())


@admin_bp.route('/treks/<int:trek_id>/image/remove', methods=['POST'])
@login_required
@admin_required
def remove_trek_image(trek_id):
    """
    Remove the Cloudinary image from a trek, reverting to local fallback.

    The public_id for deletion is read EXCLUSIVELY from the database record —
    never from the request — to prevent client-controlled asset deletion.
    """
    trek = Trek.query.get_or_404(trek_id)

    old_public_id = trek.image_public_id  # read from DB only

    if not old_public_id:
        flash('No uploaded image was associated with this trek.', 'info')
        return redirect(url_for('admin.edit_trek', trek_id=trek_id))

    # Delete the remote asset before changing the database reference. If
    # deletion fails, keep the existing reference so the record stays
    # consistent with Cloudinary.
    success = cloudinary_service.delete_trek_image(old_public_id)
    if not success:
        flash('Trek image could not be removed from Cloudinary. '
              'The existing image reference was preserved.', 'warning')
        return redirect(url_for('admin.edit_trek', trek_id=trek_id))

    trek.image_url = None
    trek.image_public_id = None
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('Trek image was removed from Cloudinary, but the database update '
              'failed. Please try again.', 'danger')
        return redirect(url_for('admin.edit_trek', trek_id=trek_id))

    flash('Trek image removed. The local fallback image will be shown.', 'success')
    return redirect(url_for('admin.edit_trek', trek_id=trek_id))


@admin_bp.route('/treks/<int:trek_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_trek(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    if trek.bookings:
        flash('This trek has bookings, so it cannot be deleted. You can close it instead.', 'warning')
        return redirect(url_for('admin.manage_treks'))

    # Clean up Cloudinary asset before removing the DB record. If deletion
    # fails, keep the trek so its image reference remains consistent.
    if trek.image_public_id:
        success = cloudinary_service.delete_trek_image(trek.image_public_id)
        if not success:
            flash('Trek could not be deleted because its Cloudinary image could '
                  'not be removed. The trek and image reference were preserved.', 'warning')
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
