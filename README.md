# TrailMate 🏔️

TrailMate is a Flask-based web application for discovering alpine trekking expeditions, reserving slots, managing trek operations, and processing Razorpay test-mode payments. It supports public visitors plus three authenticated roles: trekkers, staff/guides, and administrators.

This repository is suitable for local development, university project evaluation, and deployment experiments. Payment integration is configured for Razorpay **test mode** only.

---

## Table of Contents

1. [Overview](#overview)
2. [Key Features](#key-features)
3. [Technology Stack](#technology-stack)
4. [Project Structure](#project-structure)
5. [Core Workflows](#core-workflows)
6. [Prerequisites](#prerequisites)
7. [Local Installation on Windows](#local-installation-on-windows)
8. [Environment Variables](#environment-variables)
9. [Database Setup and Migrations](#database-setup-and-migrations)
10. [Running the Application](#running-the-application)
11. [Running Tests](#running-tests)
12. [Razorpay Test-Mode Payments](#razorpay-test-mode-payments)
13. [Cloudinary Trek Images](#cloudinary-trek-images)
14. [Render Deployment](#render-deployment)
15. [Security Notes](#security-notes)
16. [Current Limitations](#current-limitations)
17. [Future Improvements](#future-improvements)
18. [Contributing](#contributing)
19. [License](#license)

---

## Overview

TrailMate connects trekkers with curated mountain expeditions. Public visitors can browse open treks and view expedition details without logging in. Authenticated trekkers can filter treks, reserve slots, complete test-mode Razorpay payments, and manage bookings. Staff members manage assigned expeditions and participant rosters. Administrators manage treks, users, staff, bookings, and optional Cloudinary cover images.

---

## Key Features

### Public Visitors
- Browse open treks by keyword, difficulty, and region.
- View trek details, dates, duration, difficulty, slots, guide, overview, and safety notes.
- Open a login or registration flow from a trek details page while preserving the selected trek.

### Trekkers
- Register and log in with role-based access.
- Reserve trek slots through a server-side booking flow.
- Complete Razorpay test-mode checkout and server-side payment verification.
- View bookings, checkout, payment status, booking history, and profile.
- Cancel eligible bookings before departure.

### Staff / Guides
- View assigned expeditions.
- Update available slots and expedition status.
- View participant rosters for assigned treks.
- Cancel participant bookings where permitted.

### Administrators
- Create, edit, and delete treks.
- Upload, replace, and remove Cloudinary cover images.
- Manage users and staff approval/status.
- View bookings and trek capacity.
- Access admin-only routes protected by role checks and CSRF.

---

## Technology Stack

- **Backend:** Python, Flask, Flask-SQLAlchemy, Flask-Login, Flask-WTF
- **Frontend:** Jinja2, Bootstrap 5, custom CSS (`static/css/style.css`)
- **Database:** SQLite by default; PostgreSQL supported through `DATABASE_URL`
- **Payments:** Razorpay Python SDK in test mode
- **Images:** Cloudinary Python SDK
- **WSGI Server:** Gunicorn
- **Testing:** Python `unittest`

---

## Project Structure

```text
TrailMate/
├── app.py                      # Flask application factory and CLI commands
├── wsgi.py                     # Production WSGI entry point
├── models.py                   # SQLAlchemy models
├── database.py                 # SQLAlchemy database instance
├── seed.py                     # Demo data generator
├── test_app.py                 # Separate test database on port 5001
├── cloudinary_service.py        # Cloudinary upload/delete helpers
├── razorpay_service.py         # Razorpay order/signature helpers
├── migrate_add_payment_fields.py
├── migrate_add_image_fields.py
├── requirements.txt
├── .env.example
├── routes/
│   ├── auth.py
│   ├── admin.py
│   ├── staff.py
│   └── user.py
├── templates/
├── static/
├── tests/
└── instance/                   # Local SQLite databases (ignored by Git)
```

---

## Core Workflows

### Authentication
- Login and registration use CSRF-protected forms.
- Role-based decorators protect admin, staff, and booking routes.
- Post-login redirect targets are validated to prevent open redirects.

### Trek Discovery
- Public visitors can browse `/user/dashboard` and open `/user/treks/<id>`.
- Filters support keyword, difficulty, and region.
- Open treks are listed; completed treks are not bookable.

### Booking
- Booking requires an authenticated trekker account.
- The server checks trek status and available slots.
- A pending booking reserves a slot transactionally.

### Razorpay Test-Mode Payments
- Booking creates a Razorpay order and a `Pending` booking.
- Checkout uses server-provided order details.
- Payment verification validates the Razorpay signature server-side.
- Invalid signatures mark the booking as `Failed` but keep the slot reserved until expiry.

### Cloudinary Trek Images
- Admins can upload, replace, and remove trek cover images.
- Images are stored in Cloudinary and referenced by `image_url` and `image_public_id`.
- Treks without an uploaded image use local fallback images.

### Booking Management
- Trekkers can view bookings, checkout, payment status, and history.
- Eligible bookings can be cancelled.
- Staff can manage assigned treks and participants.
- Stale pending payments are expired by a CLI command and existing lazy route checks.

---

## Prerequisites

- Python 3.8 or newer
- Git
- A virtual environment tool (`venv`)
- Optional: Razorpay test-mode account
- Optional: Cloudinary account
- Optional: PostgreSQL for production-style persistence

---

## Local Installation on Windows

```powershell
git clone <your-repo-url>
cd TrailMate

python -m venv venv
venv\Scripts\activate

python -m pip install --upgrade pip
pip install -r requirements.txt

copy .env.example .env
```

Edit `.env` with your local values. Do not commit `.env`.

Optional demo data:

```powershell
python seed.py
```

This creates demo users, staff, treks, and bookings. Demo credentials are listed below.

---

## Environment Variables

Copy `.env.example` to `.env` and configure values. Never commit real secrets.

Core variables:

```text
FLASK_APP=wsgi.py
FLASK_DEBUG=0
SECRET_KEY=replace-with-a-secure-random-secret-key
DATABASE_URL=postgresql://user:password@localhost:5432/trailmate_db
ADMIN_NAME=System Admin
ADMIN_EMAIL=admin@trailmate.com
ADMIN_PASSWORD=replace-with-a-strong-admin-password
PORT=5000
SESSION_COOKIE_SECURE=true
```

Razorpay test-mode variables:

```text
RAZORPAY_KEY_ID=rzp_test_...
RAZORPAY_KEY_SECRET=...
PAYMENT_CURRENCY=INR
PAYMENT_PENDING_EXPIRY_MINUTES=15
```

Cloudinary variables, optional:

```text
CLOUDINARY_CLOUD_NAME=
CLOUDINARY_API_KEY=
CLOUDINARY_API_SECRET=
```

If Cloudinary variables are empty, TrailMate uses local fallback images.

Notes:
- `DATABASE_URL` is optional. When unset, TrailMate uses `instance/trekking.db`.
- `SECRET_KEY` must be strong in production; placeholder values are rejected.
- `ADMIN_EMAIL` and `ADMIN_PASSWORD` are required for production database initialization.

---

## Database Setup and Migrations

### Fresh Database

Create tables and the initial administrator:

```powershell
python -m flask --app app init-db
```

In non-production mode, `python app.py` also initializes the database automatically.

### Existing Database Migration

For an existing database created before payment or image fields were added, run:

```powershell
python migrate_add_payment_fields.py
python migrate_add_image_fields.py
```

These scripts use raw `ALTER TABLE` statements and check for existing columns before changing the schema. The payment migration has SQLite-specific atomic transaction handling. Review migrations before running them against a database containing real data.

### SQLite and PostgreSQL

- SQLite is the default and is suitable for local development.
- PostgreSQL can be used by setting `DATABASE_URL`.
- Migrations are dialect-aware, but SQLite-specific transaction hardening is not applied to PostgreSQL.
- On Render, SQLite files are ephemeral. Use PostgreSQL for persistent production data.

---

## Running the Application

Normal mode:

```powershell
python app.py
```

The app starts at `http://127.0.0.1:5000`.

Separate test database on port 5001:

```powershell
python test_app.py
```

Production-style entry point:

```powershell
python -m flask --app wsgi run
```

Or with Gunicorn:

```powershell
gunicorn wsgi:app
```

---

## Running Tests

Run the complete suite:

```powershell
python -m unittest discover -s tests -t .
```

Focused examples:

```powershell
python -m unittest tests.test_csrf_protection
python -m unittest tests.test_cloudinary
python -m unittest tests.test_razorpay_payments
python -m unittest tests.test_pending_payment_expiry
python -m unittest tests.test_expire_pending_cli
python -m unittest tests.test_public_discovery
python -m unittest tests.test_payment_migration
```

Tests use isolated in-memory or temporary SQLite databases. They do not use the real `instance/trekking.db`.

---

## Razorpay Test-Mode Payments

1. Create a Razorpay test-mode account.
2. Set `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` in `.env`.
3. Keep `PAYMENT_CURRENCY=INR`.
4. Start TrailMate and book a trek as a trekker.
5. Complete checkout using Razorpay test-mode credentials and test payment methods from Razorpay documentation.

Important:
- Do not use live Razorpay keys in development.
- The current booking amount is a fixed server-side test amount of ₹1,000.00.
- Payment verification is performed server-side using Razorpay signatures.
- Pending payments expire after `PAYMENT_PENDING_EXPIRY_MINUTES` minutes.

---

## Cloudinary Trek Images

1. Create a Cloudinary account.
2. Set `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, and `CLOUDINARY_API_SECRET`.
3. Log in as an admin.
4. Open Add or Edit Expedition.
5. Upload a JPEG, PNG, or WebP image up to 5 MB.
6. Replace or remove the image from the same page.

If Cloudinary is not configured, TrailMate uses local fallback images and disables uploads.

---

## Render Deployment

### Build and Start

Build command:

```text
pip install -r requirements.txt
```

Start command:

```text
gunicorn --bind 0.0.0.0:$PORT wsgi:app
```

### Required Environment Variables

Set at least:

```text
SECRET_KEY=<strong-random-secret>
DATABASE_URL=<postgresql-connection-string>
ADMIN_EMAIL=<admin-email>
ADMIN_PASSWORD=<strong-admin-password>
RAZORPAY_KEY_ID=<razorpay-test-key-id>
RAZORPAY_KEY_SECRET=<razorpay-test-key-secret>
PAYMENT_CURRENCY=INR
PAYMENT_PENDING_EXPIRY_MINUTES=15
CLOUDINARY_CLOUD_NAME=
CLOUDINARY_API_KEY=
CLOUDINARY_API_SECRET=
SESSION_COOKIE_SECURE=true
FLASK_DEBUG=0
```

### Database Initialization

Initialize the database in a Render shell or one-off job:

```powershell
python -m flask --app wsgi init-db
```

For an existing database, run the required migration scripts before starting the app.

### Persistent Database Considerations

- The default SQLite database is not persistent on Render.
- Use PostgreSQL for deployed data.
- Do not rely on local SQLite files for production.

### Images

- Uploaded images are stored in Cloudinary, not on the Render filesystem.
- Local fallback images are bundled with the application.

### Pending Payment Expiry

TrailMate includes a CLI command:

```powershell
python -m flask --app wsgi expire-pending-bookings
```

A Render Cron Job is recommended but is not configured automatically. Configure it to run every 1 to 5 minutes if you want stale pending payments expired without waiting for user traffic.

---

## Security Notes

- CSRF protection is enabled globally with Flask-WTF.
- Forms include hidden CSRF tokens.
- Same-origin JSON/fetch POSTs use `X-CSRFToken` from the meta tag via `static/js/csrf.js`.
- Passwords are hashed with Werkzeug.
- Admin, staff, and booking routes use role-based decorators.
- Payment signatures are verified server-side.
- Post-login redirect targets are validated against open redirects.
- `.env` is ignored by Git and must never be committed.
- Use strong production secrets and admin credentials.
- Use HTTPS and set `SESSION_COOKIE_SECURE=true` in production.

Production limitations:
- SQLite is not recommended for production.
- No built-in background scheduler is included; use the CLI command with Render Cron.
- The default fixed payment amount is for testing.
- No rate limiting is currently implemented.

---

## Current Limitations

- Trek records do not include price, itinerary, inclusions, or requirements fields.
- The booking amount is currently a fixed server-side test amount.
- Cloudinary validation checks extension and size, but not file content type or magic bytes.
- No pagination is implemented for large trek or booking lists.
- No email notifications are sent for bookings or payment status.
- Payment expiry runs on selected requests and through the optional CLI cron job.

---

## Future Improvements

- Add trek pricing, itinerary, inclusions, and requirements fields.
- Add payment history and invoice details.
- Add pagination and search improvements.
- Add rate limiting and production logging.
- Add automated browser-level tests.
- Add a formal contribution guide and license.

---

## Contributing

1. Fork the repository.
2. Create a feature branch.
3. Make focused changes.
4. Run `python -m unittest discover -s tests -t .`.
5. Open a pull request with a clear description.

No formal `CONTRIBUTING.md` file currently exists.

---

## License

No license file is currently included in the repository. Add a license before public reuse or distribution.

---

<div align="center">
Made with ❤️ by Manas Thorat
</div>