# TrailMate

TrailMate is a Flask web application for discovering alpine trekking expeditions, reserving slots, managing trek operations, and processing Razorpay test-mode payments.

## Live Demo

- **Live Application:** [Open TrailMate](https://trailmate-hc9y.onrender.com)
- **Demo Video:** [Watch the demo](https://drive.google.com/drive/folders/1TdV_-yY3NBgjSfau7o5rXQynbrYliPLP?usp=drive_link)
- **Repository:** [GitHub](https://github.com/manasthorat7/TrailMate)

**Note for Evaluators:** This application is hosted on Render's free tier, which may spin down after inactivity. The first visit can take around 30–60 seconds while the service starts. Please allow time for the application to load and retry if necessary. This is a hosting cold-start delay, not an application feature limitation.

## Overview

TrailMate connects trekkers with curated mountain expeditions. Public visitors can browse and filter open treks. Authenticated trekkers can reserve slots, complete test-mode Razorpay payments, and manage bookings. Staff members manage assigned expeditions and participants. Administrators manage treks, users, staff, bookings, images, and pricing.

## Features

### Visitors and Trekkers
- Browse open treks by keyword, difficulty, and region.
- View trek details, dates, duration, difficulty, slots, guide, overview, and safety notes.
- Register and log in with role-based access.
- Reserve trek slots through a server-side booking flow.
- Complete Razorpay test-mode checkout with server-side payment verification.
- View bookings, checkout details, payment status, and booking history.
- Cancel eligible bookings before departure.

### Staff
- View assigned expeditions.
- Update available slots and expedition status.
- View participant rosters for assigned treks.
- Cancel participant bookings where permitted.

### Administrators
- Create, edit, and delete treks.
- Set and update required INR trek prices.
- Manage users, staff approvals, and bookings.
- Upload, replace, and remove Cloudinary trek images.
- View analytics, including verified revenue based on verified payments.

## Technology Stack

- **Backend:** Flask, Flask-SQLAlchemy, Flask-Login, Flask-WTF
- **Database:** PostgreSQL in production, SQLite for local development and tests
- **Payments:** Razorpay test-mode order creation and signature verification
- **Images:** Cloudinary uploads with local fallback images
- **Frontend:** Jinja2 templates, Bootstrap 5, Bootstrap Icons
- **Deployment:** Render web service and Render PostgreSQL
- **Testing:** Python `unittest`

## How It Works

- **Authentication and roles:** Users register as trekkers. Staff and administrator accounts are managed by administrators. Role checks protect routes for trekkers, staff, and administrators.
- **Trek discovery:** Public pages show open treks with filtering by keyword, difficulty, and region.
- **Booking and payment:** Booking amounts are calculated server-side from the persisted trek price. Razorpay orders are created with that amount, and payment signatures are verified before a booking is marked verified.
- **Pending payments:** Pending, unpaid, or failed reservations can expire automatically, releasing reserved slots.
- **Trek administration:** Administrators manage trek details, pricing, slot counts, status, dates, staff assignment, and images.
- **Staff operations:** Staff update assigned trek status and slots and manage participants.
- **Image uploads:** Cloudinary stores uploaded images when configured; otherwise local fallback images are used.

## Project Structure

```text
TrailMate/
├── app.py
├── models.py
├── wsgi.py
├── render.yaml
├── migrate_add_trek_price.py
├── routes/
│   ├── admin.py
│   ├── auth.py
│   ├── staff.py
│   └── user.py
├── templates/
├── static/
├── tests/
├── .env.example
└── requirements.txt
```

## Getting Started

### Prerequisites
- Python 3.10 or newer
- Git
- A virtual environment

### Local setup on Windows

```powershell
git clone https://github.com/manasthorat7/TrailMate.git
cd TrailMate
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` for your local environment. For basic local development, SQLite is used automatically when `DATABASE_URL` is not set.

### Database setup and migrations

For a new local database:

```powershell
flask --app wsgi init-db
```

For an existing database that needs the trek-price column:

```powershell
python migrate_add_trek_price.py
```

The migration is idempotent and preserves existing trek records. Legacy prices remain `NULL` until an administrator sets them.

### Running the application

```powershell
flask --app wsgi run
```

Or, for the local development server:

```powershell
python app.py
```

## Environment Configuration

Essential variables are documented in `.env.example`. Important variables include:

- `SECRET_KEY`
- `DATABASE_URL`
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`
- `RAZORPAY_KEY_ID`
- `RAZORPAY_KEY_SECRET`
- `CLOUDINARY_CLOUD_NAME`
- `CLOUDINARY_API_KEY`
- `CLOUDINARY_API_SECRET`
- `PAYMENT_CURRENCY`
- `PAYMENT_PENDING_EXPIRY_MINUTES`

Razorpay and Cloudinary are optional for basic startup. Razorpay is required for payments, and Cloudinary is required for remote image uploads.

## Testing

Run the complete test suite:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -t .
```

## Deployment

TrailMate is deployed on Render using Gunicorn and Render PostgreSQL. The Render startup command runs the trek-price migration, initializes the database, and starts Gunicorn. Production requires `SECRET_KEY`, PostgreSQL `DATABASE_URL`, and administrator credentials.

Render's free tier may sleep after inactivity and can take about a minute to wake.

## Current Limitations

- Razorpay integration is test-mode only.
- Cloudinary image uploads require Cloudinary configuration.
- Free-tier Render PostgreSQL and web services have resource and availability limits.
- Some PostgreSQL-specific migration behavior is validated by design but not by a live PostgreSQL test suite.

## Future Roadmap

- Trek itineraries, inclusions, and participant requirements.
- Booking confirmations, receipts, or invoices.
- Pagination and improved discovery filters.
- Email notifications.
- Rate limiting, operational monitoring, and improved production logging.
- More end-to-end browser-level tests.

## Author

Manas Thorat
