"""
seed.py
Initializes the database with testing data for TrailMate.
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
        
        
        print("Initializing database...")
        db.create_all()

        if User.query.count() > 1:
            print("Database is already populated. Skipping seed.")
            return

        print("Database is empty. Seeding data...")


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


        staff_templates = [
            {"name": "Aditya (Active Staff)", "email": "aditya@staff.com", "status": "Active"},
            {"name": "Neha (Active Staff)", "email": "neha@staff.com", "status": "Active"},
            {"name": "Rohan (Active Staff)", "email": "rohan@staff.com", "status": "Active"},
            {"name": "Simran (Pending Staff)", "email": "simran@staff.com", "status": "Pending"},
            {"name": "Kabir (Blacklisted)", "email": "kabir@staff.com", "status": "Inactive"}
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


        user_templates = [
            {"name": "Tanishq Pardeshi", "email": "tanishq@user.com", "status": "Active"},
            {"name": "Kushagra Shukla", "email": "kushagra@user.com", "status": "Active"},
            {"name": "Kush Patel", "email": "kush@user.com", "status": "Active"},
            {"name": "Ananya Gupta", "email": "ananya@user.com", "status": "Active"},
            {"name": "Diya Reddy", "email": "diya@user.com", "status": "Active"},
            {"name": "Aditi Deshpande", "email": "aditi@user.com", "status": "Active"},
            {"name": "Riya Desai", "email": "riya@user.com", "status": "Active"},
            {"name": "Om Nerkar", "email": "om@user.com", "status": "Active"},
            {"name": "Siddharth Iyer", "email": "siddharth@user.com", "status": "Active"},
            {"name": "Arjun Patil", "email": "arjun@user.com", "status": "Active"},
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


        today = date.today()
        treks_templates = [
            {"name": "Everest Base Camp", "loc": "Nepal", "diff": "Hard", "dur": "14 Days", "slots": 20, "status": "Open", "start": today + timedelta(days=30), "end": today + timedelta(days=44)},
            {"name": "Annapurna Base Camp", "loc": "Nepal", "diff": "Hard", "dur": "12 Days", "slots": 15, "status": "Started", "start": today - timedelta(days=2), "end": today + timedelta(days=10)},
            {"name": "Roopkund Lake", "loc": "Uttarakhand, India", "diff": "Moderate", "dur": "8 Days", "slots": 25, "status": "Completed", "start": today - timedelta(days=20), "end": today - timedelta(days=12)},
            {"name": "Hampta Pass", "loc": "Himachal Pradesh, India", "diff": "Moderate", "dur": "5 Days", "slots": 50, "status": "Open", "start": today + timedelta(days=60), "end": today + timedelta(days=64)},
            {"name": "K2 Base Camp", "loc": "Pakistan", "diff": "Hard", "dur": "14 Days", "slots": 10, "status": "Open", "start": today + timedelta(days=15), "end": today + timedelta(days=28)},
            {"name": "Valley of Flowers", "loc": "Uttarakhand, India", "diff": "Easy", "dur": "4 Days", "slots": 30, "status": "Completed", "start": today - timedelta(days=60), "end": today - timedelta(days=56)},
            {"name": "Goechala Trek", "loc": "Sikkim, India", "diff": "Hard", "dur": "11 Days", "slots": 12, "status": "Open", "start": today + timedelta(days=45), "end": today + timedelta(days=56)},
            {"name": "Harishchandragad Fort", "loc": "Maharashtra, India", "diff": "Easy", "dur": "1 Day", "slots": 40, "status": "Started", "start": today, "end": today},
            {"name": "Stok Kangri", "loc": "Ladakh, India", "diff": "Hard", "dur": "9 Days", "slots": 20, "status": "Open", "start": today + timedelta(days=25), "end": today + timedelta(days=33)},
            {"name": "Sandakphu Trek", "loc": "West Bengal, India", "diff": "Moderate", "dur": "6 Days", "slots": 18, "status": "Open", "start": today + timedelta(days=80), "end": today + timedelta(days=85)},
            {"name": "Triund Trek", "loc": "Himachal Pradesh, India", "diff": "Easy", "dur": "2 Days", "slots": 25, "status": "Completed", "start": today - timedelta(days=100), "end": today - timedelta(days=98)},
            {"name": "Kedarkantha Winter Trek", "loc": "Uttarakhand, India", "diff": "Moderate", "dur": "6 Days", "slots": 15, "status": "Open", "start": today + timedelta(days=10), "end": today + timedelta(days=15)},
            {"name": "Overbooking Test Trek", "loc": "Bhutan", "diff": "Easy", "dur": "3 Days", "slots": 3, "status": "Open", "start": today + timedelta(days=5), "end": today + timedelta(days=8)},
            {"name": "Unassigned Trail", "loc": "Meghalaya, India", "diff": "Easy", "dur": "2 Days", "slots": 10, "status": "Open", "start": today + timedelta(days=1), "end": today + timedelta(days=2)}
        ]

        treks = []
        for t in treks_templates:
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


        booking_count = 0
        for i in range(35):
            u_id = random.choice(active_user_ids)
            t = random.choice(treks)
            
            if t.status == 'Completed':
                booking_status = 'Completed'
            elif t.status == 'Open':
                booking_status = random.choices(['Booked', 'Cancelled'], weights=[80, 20])[0]
            else: 
                booking_status = 'Booked'
                
            if booking_status == 'Booked' and t.available_slots > 0:
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
        print(f"=> Created {booking_count} Bookings (Booked, Cancelled, Completed).")
        
        print("\n*** Seed Process Completed Successfully! ***")
        print("You can now test all major functionalities with this data.")

if __name__ == '__main__':
    run_seed()
