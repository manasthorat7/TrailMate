"""
seed.py
Original seed script for TrailMate to generate testing data.
This script programmatically sets up the database with Users, Treks, and Bookings
to cover all major testing scenarios (e.g. searching, overbooking, statuses, blacklists).
"""

from app import create_app
from database import db
from models import User, Trek, Booking
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta, date
import random

def run_seed():
    app = create_app(db_name='test_trekking.db')
    with app.app_context():
        
        # REQUIREMENT 1: Database must be created programmatically
        print("Initializing database...")
        db.create_all()

        # REQUIREMENT 2: Seed data should automatically create if database is empty
        # We check if there's more than the default admin to determine if it's empty
        if User.query.count() > 1:
            print("Database is already populated. Skipping seed.")
            return

        print("Database is empty. Seeding data...")

        # REQUIREMENT 3: Create exactly one pre-existing Admin
        admin = User.query.filter_by(role='admin').first()
        if not admin:
            admin = User(
                name="Admin User",
                email="admin@trailmate.com",
                password=generate_password_hash("admin123"),
                role="admin",
                status="Active"
            )
            db.session.add(admin)
            db.session.commit()
            print("=> Admin created.")

        # REQUIREMENT 4: Create multiple Trek Staff (Pending, Approved, Blacklisted)
        staff_templates = [
            {"name": "Arjun (Active Staff)", "email": "arjun@staff.com", "status": "Active"},
            {"name": "Priya (Active Staff)", "email": "priya@staff.com", "status": "Active"},
            {"name": "Rahul (Active Staff)", "email": "rahul@staff.com", "status": "Active"},
            {"name": "Sneha (Pending Staff)", "email": "sneha@staff.com", "status": "Pending"},
            {"name": "Karan (Blacklisted)", "email": "karan@staff.com", "status": "Inactive"}
        ]
        
        active_staff_ids = []
        for s in staff_templates:
            staff_user = User(
                name=s['name'],
                email=s['email'],
                password=generate_password_hash("staff123"),
                role="staff",
                status=s['status'],
                contact_details="1234567890"
            )
            db.session.add(staff_user)
            db.session.flush() # To get the ID before committing
            if s['status'] == 'Active':
                active_staff_ids.append(staff_user.id)
                
        print(f"=> Created 5 Staff members.")

        # REQUIREMENT 5: Create multiple Users (Active, Blacklisted)
        user_templates = [
            {"name": "Alice Trekker", "email": "alice@user.com", "status": "Active"},
            {"name": "Bob Explorer", "email": "bob@user.com", "status": "Active"},
            {"name": "Charlie Hiker", "email": "charlie@user.com", "status": "Active"},
            {"name": "Diana Walker", "email": "diana@user.com", "status": "Active"},
            {"name": "Eve Climber", "email": "eve@user.com", "status": "Active"},
            {"name": "Frank Camper", "email": "frank@user.com", "status": "Active"},
            {"name": "Grace Ranger", "email": "grace@user.com", "status": "Active"},
            {"name": "Henry Peak", "email": "henry@user.com", "status": "Active"},
            {"name": "Isabel Mountain", "email": "isabel@user.com", "status": "Active"},
            {"name": "Jack Valley", "email": "jack@user.com", "status": "Active"},
            {"name": "Spammer (Blacklisted)", "email": "spam@user.com", "status": "Inactive"},
            {"name": "Bot (Blacklisted)", "email": "bot@user.com", "status": "Inactive"}
        ]
        
        active_user_ids = []
        for u in user_templates:
            trekker = User(
                name=u['name'],
                email=u['email'],
                password=generate_password_hash("user123"),
                role="user",
                status=u['status']
            )
            db.session.add(trekker)
            db.session.flush()
            if u['status'] == 'Active':
                active_user_ids.append(trekker.id)
                
        print(f"=> Created 12 Users.")
        db.session.commit()

        # REQUIREMENT 6: Create multiple Treks with different Statuses, Difficulties, Dates
        today = date.today()
        treks_templates = [
            {"name": "Everest Base Camp", "loc": "Nepal", "diff": "Hard", "dur": "14 Days", "slots": 20, "status": "Upcoming", "start": today + timedelta(days=30), "end": today + timedelta(days=44)},
            {"name": "Annapurna Circuit", "loc": "Nepal", "diff": "Hard", "dur": "12 Days", "slots": 15, "status": "Ongoing", "start": today - timedelta(days=2), "end": today + timedelta(days=10)},
            {"name": "Roopkund Lake", "loc": "India", "diff": "Moderate", "dur": "8 Days", "slots": 25, "status": "Completed", "start": today - timedelta(days=20), "end": today - timedelta(days=12)},
            {"name": "Mount Fuji Sunrise", "loc": "Japan", "diff": "Moderate", "dur": "2 Days", "slots": 50, "status": "Upcoming", "start": today + timedelta(days=60), "end": today + timedelta(days=62)},
            {"name": "Kilimanjaro Summit", "loc": "Tanzania", "diff": "Hard", "dur": "7 Days", "slots": 10, "status": "Upcoming", "start": today + timedelta(days=15), "end": today + timedelta(days=22)},
            {"name": "Inca Trail Classic", "loc": "Peru", "diff": "Moderate", "dur": "4 Days", "slots": 30, "status": "Completed", "start": today - timedelta(days=60), "end": today - timedelta(days=56)},
            {"name": "Tour du Mont Blanc", "loc": "France", "diff": "Hard", "dur": "11 Days", "slots": 12, "status": "Upcoming", "start": today + timedelta(days=45), "end": today + timedelta(days=56)},
            {"name": "Zion Narrows Run", "loc": "USA", "diff": "Moderate", "dur": "1 Day", "slots": 40, "status": "Ongoing", "start": today, "end": today},
            {"name": "Patagonia W Trek", "loc": "Chile", "diff": "Hard", "dur": "5 Days", "slots": 20, "status": "Upcoming", "start": today + timedelta(days=25), "end": today + timedelta(days=30)},
            {"name": "Laugavegur Trail", "loc": "Iceland", "diff": "Moderate", "dur": "4 Days", "slots": 18, "status": "Upcoming", "start": today + timedelta(days=80), "end": today + timedelta(days=84)},
            {"name": "West Highland Way", "loc": "Scotland", "diff": "Easy", "dur": "7 Days", "slots": 25, "status": "Completed", "start": today - timedelta(days=100), "end": today - timedelta(days=93)},
            {"name": "Kalalau Trail", "loc": "USA", "diff": "Hard", "dur": "2 Days", "slots": 15, "status": "Upcoming", "start": today + timedelta(days=10), "end": today + timedelta(days=12)},
            {"name": "Overbooking Test Trek", "loc": "Bhutan", "diff": "Easy", "dur": "3 Days", "slots": 3, "status": "Upcoming", "start": today + timedelta(days=5), "end": today + timedelta(days=8)},
            {"name": "Unassigned Trail", "loc": "Canada", "diff": "Easy", "dur": "1 Day", "slots": 10, "status": "Upcoming", "start": today + timedelta(days=1), "end": today + timedelta(days=2)}
        ]

        treks = []
        for t in treks_templates:
            # Leave the 'Unassigned Trail' without staff to test assignment functionality
            assigned_staff = None
            if t['name'] != 'Unassigned Trail':
                assigned_staff = random.choice(active_staff_ids)
                
            trek = Trek(
                trek_name=t['name'],
                location=t['loc'],
                difficulty=t['diff'],
                duration=t['dur'],
                available_slots=t['slots'],
                assigned_staff_id=assigned_staff,
                status=t['status'],
                start_date=t['start'],
                end_date=t['end']
            )
            db.session.add(trek)
            treks.append(trek)
            
        db.session.commit()
        print(f"=> Created 14 Treks covering all edge cases.")

        # REQUIREMENT 7 & 8: Create Bookings to cover scenarios (Booked, Cancelled, Completed)
        # We will create about 35 bookings across the active users and treks
        booking_count = 0
        for i in range(35):
            u_id = random.choice(active_user_ids)
            t = random.choice(treks)
            
            # Match booking status logically with the trek status
            if t.status == 'Completed':
                booking_status = 'Completed'
            elif t.status == 'Upcoming':
                # Mostly confirmed, some cancelled for realistic testing
                booking_status = random.choices(['Confirmed', 'Cancelled'], weights=[80, 20])[0]
            else: # Ongoing
                booking_status = 'Confirmed'
                
            # Prevent exceeding slots in our test data to keep database rules valid
            # (Testing overbooking prevention happens on the frontend/backend routes, not during seed)
            if booking_status == 'Confirmed' and t.available_slots > 0:
                booking = Booking(
                    user_id=u_id,
                    trek_id=t.trek_id,
                    booking_date=datetime.utcnow() - timedelta(days=random.randint(1, 15)),
                    status=booking_status
                )
                t.available_slots -= 1
                db.session.add(booking)
                booking_count += 1
            elif booking_status == 'Cancelled':
                booking = Booking(
                    user_id=u_id,
                    trek_id=t.trek_id,
                    booking_date=datetime.utcnow() - timedelta(days=random.randint(1, 15)),
                    status=booking_status
                )
                db.session.add(booking)
                booking_count += 1

        db.session.commit()
        print(f"=> Created {booking_count} Bookings (Confirmed, Cancelled, Completed).")
        
        print("\n*** Seed Process Completed Successfully! ***")
        print("You can now test all major functionalities with this data.")

if __name__ == '__main__':
    run_seed()
