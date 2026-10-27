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
├── render.yaml                 # Render Blueprint (free web service + PostgreSQL)
├── .python-version             # Python version used by Render
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

- Python 3.10 or newer (Render uses Python 3.13 from `.python-version`)
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

This creates demo users, staff, treks, and bookings. Demo credentials are defined in `seed.py`; never run this script against a production database. Use `flask --app wsgi init-db` instead when you only need the schema and the initial administrator.

---

## Environment Variables

Copy `.env.example` to `.env` and configure values. Never commit real secrets.

Core variables:

```text
FLASK_APP=wsgi.py
FLASK_DEBUG=1
SECRET_KEY=replace-with-a-secure-random-secret-key
ADMIN_NAME=System Admin
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=replace-with-a-strong-admin-password
PORT=5000
```

For production, also set:

```text
ENV=production
DATABASE_URL=postgresql://user:password@host:5432/database
SESSION_COOKIE_SECURE=true
```

`FLASK_DEBUG=0` alone does **not** enable production mode. Production is activated by `ENV=production` / `FLASK_ENV=production`, a non-SQLite `DATABASE_URL`, or `RENDER=true`.

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
- `DATABASE_URL` is optional in development. When unset, TrailMate uses `instance/trekking.db`.
- Production requires `DATABASE_URL` to be PostgreSQL; a missing or SQLite URL stops startup.
- `SECRET_KEY` must be strong in production; placeholder values are rejected.
- `ADMIN_EMAIL` and `ADMIN_PASSWORD` are required when provisioning the first production administrator. They are not needed once an administrator already exists.

---

## Database Setup and Migrations

### Fresh Database

Create the complete schema and the initial administrator:

```powershell
python -m flask --app wsgi init-db
```

`db.create_all()` creates every current table and column, including the Trek image fields, the Booking payment fields, and the unique `razorpay_order_id` constraint. The command is safe to re-run: it never duplicates an administrator and never resets an existing one. In local development, `python app.py` also initializes the database automatically. On Render, the service start command runs this step automatically.

Initial administrator provisioning:

- Set `ADMIN_EMAIL` and a strong `ADMIN_PASSWORD` (minimum 8 characters, not a documented placeholder), or pass `--email` and `--password`.
- Production rejects missing, default, or placeholder credentials.
- If an administrator already exists, that account is preserved and the environment password is ignored.
- Never put the administrator password in source code, `render.yaml`, or logs.

### Existing Database Migration

The two legacy scripts are only for databases created before these fields existed:

```powershell
python migrate_add_payment_fields.py
python migrate_add_image_fields.py
```

Do **not** run them against a fresh database: the current models already create the full schema. They are not run automatically at application startup. Back up existing data first, and review the SQL before using them on PostgreSQL. The payment migration was written primarily for SQLite; its PostgreSQL index checks are less reliable, so verify the resulting schema (especially the unique `razorpay_order_id` constraint) instead of assuming success.

### SQLite and PostgreSQL

- SQLite is the default and is suitable for local development.
- PostgreSQL is required in production and is selected through `DATABASE_URL`; `postgres://` URLs are normalized to `postgresql://`.
- Local SQLite databases under `instance/` are not committed to Git.
- On Render, the filesystem is ephemeral, so SQLite data is lost on restart. Use the provisioned PostgreSQL database instead.

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

Production-style WSGI import check (no traffic served):

```powershell
python -c "import wsgi; print(wsgi.app)"
```

The Flask development server is not a production server. On Linux/macOS or Render, run:

```bash
gunicorn --bind 0.0.0.0:$PORT wsgi:app
```

Gunicorn is not supported on Windows, so use `python app.py` locally.

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
python -m unittest tests.test_deployment_config
python -m unittest tests.test_session_and_ui_safety
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

### Blueprint (recommended)

`render.yaml` defines a single free Python web service and a single free PostgreSQL database. All commands and environment wiring live in that file; the `Procfile` is not used.

Build command:

```text
pip install -r requirements.txt
```

Start command:

```text
sh -c "flask --app wsgi init-db && gunicorn --bind 0.0.0.0:$PORT wsgi:app"
```

The first half creates missing tables and provisions the initial administrator. It is idempotent, so later restarts detect the existing administrator and change nothing. On a free Render service this must run in the start command: Render's `preDeployCommand`, shell access, and one-off jobs are paid-plan features, and free services cannot use them.

Python 3.13 is selected by `.python-version`. `psycopg2-binary` and Gunicorn are already listed in `requirements.txt`.

### Environment Variables

Configure these in the Render Dashboard (or let the Blueprint create the core ones):

```text
DATABASE_URL=<injected automatically from the Render database>
SECRET_KEY=<generated by Render; never hardcode it>
ENV=production
ADMIN_EMAIL=<your administrator email>
ADMIN_PASSWORD=<strong password used only for the first provision>
PAYMENT_CURRENCY=INR
PAYMENT_PENDING_EXPIRY_MINUTES=15
RAZORPAY_KEY_ID=<optional; Razorpay test-mode key id>
RAZORPAY_KEY_SECRET=<optional; Razorpay test-mode key secret>
CLOUDINARY_CLOUD_NAME=<optional>
CLOUDINARY_API_KEY=<optional>
CLOUDINARY_API_SECRET=<optional>
```

The Blueprint prompts for the administrator credentials and creates the non-secret payment settings. Razorpay and Cloudinary credentials are optional and are not part of the Blueprint, so the first deployment can complete without them. Add them in the dashboard when those features are needed.

Notes:

- Render supplies `PORT` and `RENDER=true` automatically.
- `SESSION_COOKIE_SECURE=true` is set in `render.yaml` and is also forced whenever production mode is active.
- `ADMIN_PASSWORD` is used only while no administrator exists. Keep it in the dashboard rather than in Git.
- Never set `ALLOW_PRODUCTION_SEED`; `seed.py` is for local demo data only.
- If Razorpay or Cloudinary values are empty, booking/payment or image-upload features stay unavailable. The rest of the application still runs.

### First Deployment

1. Push the repository (without local databases or `.env`) to GitHub.
2. In Render, choose **New > Blueprint** and connect the repository.
3. Confirm the `trailmate-db` and `trailmate` resources and enter `ADMIN_EMAIL` and `ADMIN_PASSWORD` when prompted.
4. Apply the Blueprint and wait for the build, start-command initialization, and first boot to finish.
5. Open the `onrender.com` URL and log in as the administrator.
6. If needed, add Razorpay or Cloudinary credentials in the service's Environment settings and redeploy.

If initialization fails, the deploy fails before serving traffic. Check the deploy logs for a missing or invalid `SECRET_KEY`, a non-PostgreSQL `DATABASE_URL`, or rejected administrator credentials; secret values are never printed.

### Free-Plan Limitations

Free instances are suitable for a college demonstration, not durable production use:

- A free web service spins down after 15 minutes without traffic and takes about a minute to wake.
- The filesystem is ephemeral. Local SQLite databases and uploaded files are lost on restart or redeploy.
- Free web services have no Shell, no one-off jobs, and no Cron Jobs, and cannot use `preDeployCommand`.
- Each workspace can have only one free PostgreSQL database, with a 1 GB limit.
- Free PostgreSQL expires **30 days after creation**, has no backups, and is deleted after a further 14-day grace period unless upgraded. Export important data or upgrade before then.
- There are monthly limits on free instance hours, bandwidth, and build pipeline minutes.

Schedule/export data before expiry if the project must stay available after the semester. Upgrading the database to a paid plan preserves its data; do not recreate the free database and expect the old data to remain.

### Optional Paid-Plan Improvements

If the service is upgraded, `flask --app wsgi init-db` can be moved to `preDeployCommand`, and `flask --app wsgi expire-pending-bookings` can run as a scheduled Cron Job every few minutes. Neither is required for the free deployment, and neither is configured automatically.

### Images

- Uploaded images are stored in Cloudinary, not on the Render filesystem.
- Local fallback images are bundled with the application.

### Pending Payment Expiry

TrailMate includes a CLI command:

```powershell
python -m flask --app wsgi expire-pending-bookings
```

Free Render services cannot run a Cron Job, so stale pending payments are expired lazily when relevant booking pages are loaded. On a paid plan, schedule the command if you want expiry to run without user traffic.

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
- Production startup fails closed on a missing/placeholder `SECRET_KEY` or a missing/SQLite `DATABASE_URL`.
- Production forces secure cookies, trusts one reverse-proxy hop for HTTPS, and refuses to run the Flask development server.
- Deactivated or rejected accounts lose access on their next request, even if they still hold a session.
- Use strong production secrets and admin credentials.
- Use HTTPS and set `SESSION_COOKIE_SECURE=true` in production.

Production limitations:
- SQLite is not recommended for production.
- No built-in background scheduler is included. Free Render services cannot run Cron Jobs; use the CLI command on a paid plan if needed.
- The default fixed payment amount is for testing.
- No rate limiting is currently implemented.

---

## Current Limitations

- Trek records do not include price, itinerary, inclusions, or requirements fields.
- The booking amount is currently a fixed server-side test amount.
- Cloudinary validation checks extension and size, but not file content type or magic bytes.
- No pagination is implemented for large trek or booking lists.
- No email notifications are sent for bookings or payment status.
- Payment expiry runs on selected requests and, on paid plans, through the optional CLI command.
- Free Render PostgreSQL expires after 30 days and has no backups.

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