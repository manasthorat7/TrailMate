from database import db
from flask_login import UserMixin
from datetime import datetime


# Payment lifecycle groups shared by routes, templates, and migrations.
# "Legacy" marks bookings that predate Razorpay. They are preserved as
# historical reservations and are never treated as newly verified payments.
PAYMENT_STATUS_VERIFIED = 'Verified'
PAYMENT_STATUS_LEGACY = 'Legacy'
CONFIRMED_PAYMENT_STATUSES = (PAYMENT_STATUS_VERIFIED, PAYMENT_STATUS_LEGACY)
EXPIRABLE_PAYMENT_STATUSES = ('Pending', 'Unpaid', 'Failed')
ACTIVE_RESERVATION_PAYMENT_STATUSES = (
    'Unpaid', 'Pending', 'Failed', PAYMENT_STATUS_VERIFIED, PAYMENT_STATUS_LEGACY
)


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user')
    contact_details = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='Active')  # Active/Inactive/Pending
    assigned_treks = db.relationship('Trek', backref='assigned_staff', lazy=True)
    bookings = db.relationship('Booking', backref='user', lazy=True)


class Trek(db.Model):
    trek_id = db.Column(db.Integer, primary_key=True)
    trek_name = db.Column(db.String(150), nullable=False)
    location = db.Column(db.String(150), nullable=False)
    difficulty = db.Column(db.String(50), nullable=False)
    duration = db.Column(db.String(50), nullable=False)  # e.g., '5 Days'
    available_slots = db.Column(db.Integer, nullable=False)
    assigned_staff_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    status = db.Column(db.String(50), nullable=False, default='Open')  # Open/Started/Completed
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)

    # Cloudinary image fields — nullable; treks without uploads fall back to local images
    image_url = db.Column(db.String(500), nullable=True)
    image_public_id = db.Column(db.String(200), nullable=True)

    # Required INR price for new treks. Nullable so legacy rows created before
    # pricing existed remain intact until an administrator sets a valid price.
    price = db.Column(db.Numeric(10, 2), nullable=True)

    bookings = db.relationship('Booking', backref='trek', lazy=True)



class Booking(db.Model):
    booking_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    trek_id = db.Column(db.Integer, db.ForeignKey('trek.trek_id'), nullable=False)

    booking_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(50), nullable=False, default='Booked')  # Booked/Cancelled

    # Payment fields (Razorpay test-mode)
    payment_status = db.Column(db.String(50), nullable=False, default='Unpaid')  # Unpaid/Pending/Verified/Failed/Refunded/Legacy
    amount = db.Column(db.Float, nullable=True)
    currency = db.Column(db.String(10), nullable=False, default='INR')
    razorpay_order_id = db.Column(db.String(100), unique=True, nullable=True)
    razorpay_payment_id = db.Column(db.String(100), nullable=True)
    razorpay_signature = db.Column(db.String(200), nullable=True)
