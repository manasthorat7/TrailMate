from database import db
from flask_login import UserMixin
from datetime import datetime


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

    status = db.Column(db.String(50), nullable=False, default='Upcoming')  # Upcoming/Ongoing/Completed
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    bookings = db.relationship('Booking', backref='trek', lazy=True)


class Booking(db.Model):
    booking_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    trek_id = db.Column(db.Integer, db.ForeignKey('trek.trek_id'), nullable=False)

    booking_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(50), nullable=False, default='Confirmed')  # Confirmed/Cancelled
