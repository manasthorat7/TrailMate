# TrailMate 🏔️

A clean and simple Flask-based web application to manage trekking events, book slots, and oversee staff. Built as a passionate web dev project!

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0+-green.svg)](https://flask.palletsprojects.com/)
[![SQLite](https://img.shields.io/badge/Database-SQLite-orange.svg)](https://www.sqlite.org/)

---

## 🌟 Features

### Admin Portal
- Manage all treks (create, edit, delete).
- Oversee bookings and total capacity.
- Manage users and staff members (approve, blacklist, or activate).

### Staff Portal
- See treks assigned to you.
- Track participant lists and update trek statuses (Upcoming, Ongoing, Completed).

### User Portal
- Browse through Indian and Himalayan treks (like Hampta Pass, Roopkund, Everest Base Camp).
- Book your slot with one click.
- See your trekking history and manage profile.

---

## 🛠️ Tech Stack
- **Backend**: Python, Flask, Flask-SQLAlchemy, Werkzeug
- **Frontend**: HTML5, CSS3 (Custom sleek translucent design), Bootstrap 5, Jinja2
- **Database**: SQLite

---

## 📁 Project Structure
```text
TrailMate/
│
├── app.py                      # Main Flask application
├── models.py                   # Database models (User, Trek, Booking)
├── routes.py                   # App routes & endpoints
├── seed.py                     # Generates dummy data (Indian context)
│
├── templates/                  # Jinja2 HTML Templates
│   ├── base.html
│   ├── auth/                   # Login & Register
│   ├── admin/                  # Admin dashboard & management
│   ├── staff/                  # Staff dashboard
│   └── user/                   # User dashboard & booking
│
├── static/
│   ├── css/style.css           # Custom UI styling 
│   └── images/                 # Backgrounds & Assets
│
└── instance/                   # SQLite database (auto-generated)
```

---

## 🚀 How to Run

```bash
# 1. Clone the repository
git clone <your-repo-link>
cd TrailMate

# 2. Create and activate a virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Generate Demo Data (Highly Recommended!)
# This creates all the treks, users, and staff automatically
python seed.py

# 5. Run the app
python app.py
```

The app will start at **http://127.0.0.1:5000** or **http://127.0.0.1:5001**.

---

## 🔑 Demo Logins

If you used `seed.py`, try these to explore different roles:

| Role | Email | Password |
|------|----------|----------|
| **Admin** | `admin@trailmate.com` | `admin123` |
| **Staff** | `aditya@staff.com` | `staff123` |
| **User** | `aarav@user.com` | `user123` |

---
<div align="center">
Made with ❤️ Manas Thorat
</div>
