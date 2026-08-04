from database import db
from flask_login import UserMixin
from datetime import datetime

class User(db.Model, UserMixin):
    """
    Handles authentication and profile data for Admin, Staff, and Users.
    Inherits from UserMixin to integrate easily with Flask-Login.
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    
    # role can be 'admin', 'staff', or 'user'
    role = db.Column(db.String(20), nullable=False, default='user')
    
    # Mandatory Staff fields (also useful for standard users)
    contact_details = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='Active') # Active/Inactive/Pending
    
    # Relationship: A staff user can be assigned to multiple treks
    assigned_treks = db.relationship('Trek', backref='assigned_staff', lazy=True)
    
    # Relationship: A user can have multiple bookings
    bookings = db.relationship('Booking', backref='user', lazy=True)

class Trek(db.Model):
    """
    Stores all mandatory information about a Trek.
    """
    trek_id = db.Column(db.Integer, primary_key=True)
    trek_name = db.Column(db.String(150), nullable=False)
    location = db.Column(db.String(150), nullable=False)
    difficulty = db.Column(db.String(50), nullable=False)
    duration = db.Column(db.String(50), nullable=False) # e.g., '5 Days'
    available_slots = db.Column(db.Integer, nullable=False)
    
    # Foreign Key linking to a User with the role 'staff'
    assigned_staff_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    status = db.Column(db.String(50), nullable=False, default='Upcoming') # Upcoming/Ongoing/Completed
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    
    # Relationship: A trek can have multiple bookings
    bookings = db.relationship('Booking', backref='trek', lazy=True)

class Booking(db.Model):
    """
    Logs which user has booked which trek.
    """
    booking_id = db.Column(db.Integer, primary_key=True)
    
    # Foreign Keys
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    trek_id = db.Column(db.Integer, db.ForeignKey('trek.trek_id'), nullable=False)
    
    booking_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(50), nullable=False, default='Confirmed') # Confirmed/Cancelled
