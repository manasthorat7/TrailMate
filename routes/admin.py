from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from functools import wraps
from models import User, Trek, Booking
from database import db
from datetime import datetime
import cloudinary_service

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
    open_treks = Trek.query.filter_by(status='Open').order_by(Trek.start_date.asc()).limit(5).all()
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

    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        slots_int = int(available_slots)
    except (TypeError, ValueError):
        flash('Error: Please enter valid trek details.', 'danger')
        return None, redirect(redirect_target)

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
