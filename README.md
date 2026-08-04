# TrailMate - Trekking Management Application

TrailMate is a web-based Trekking Management Application developed using a modular Flask architecture. It is designed to be simple, maintainable, and readable, strictly adhering to core web development principles without over-engineering.

## Technology Stack
- **Backend:** Python, Flask, Flask-Blueprints
- **Database:** SQLite, SQLAlchemy (ORM)
- **Authentication:** Flask-Login, Werkzeug Security
- **Frontend:** HTML5, Jinja2 Templating, Bootstrap 5 (CSS framework), Traditional CSS (Theme styling)

## Core Features & Business Rules Implemented
1. **Role-Based Access Control (RBAC):** Distinct dashboards and routing for `Admin`, `Staff`, and `User` roles.
2. **Pre-existing Admin:** The database automatically seeds a default System Admin upon initialization if one does not exist.
3. **Staff Approval Workflow:** Users registering as 'Staff' are placed in a 'Pending' status. They cannot log in until the Admin explicitly approves their account. Standard 'Users' do not require approval.
4. **Isolated Staff Management:** Trek Guides (Staff) can only view participants and update the status of treks that are explicitly assigned to their `Staff ID`.
5. **Booking Constraints:**
   - **Prevent Overbooking:** A trekker cannot book a trek if `available_slots <= 0`. Upon successful booking, slots decrease programmatically.
   - **Status Checks:** Trekkers can only book treks that are currently in the 'Upcoming' (Open) state.
   - **No Double Booking:** A user cannot book the same trek twice.
6. **Data Validation:** Backend logic ensures logical dates (Start Date <= End Date) and positive capacity inputs.

## Database Schema Highlights
- **User Table:** A unified table handling authentication for all three roles, eliminating the need for complex polymorphic inheritance.
- **Trek Table:** Stores all mandatory event data. Features a Foreign Key (`assigned_staff_id`) linking to the User table (One-to-Many).
- **Booking Table:** Acts as an association table, managing the Many-to-Many relationship between Users and Treks.

## How to Run the Project Locally

1. **Open your terminal** and navigate to the project root directory (`TrailMate/`).
2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   ```
3. **Activate the virtual environment:**
   - Windows: `.\venv\Scripts\activate`
   - Mac/Linux: `source venv/bin/activate`
4. **Install required dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
5. **Run the application:**
   ```bash
   python app.py
   ```
   *Note: The SQLite database (`instance/trekking.db`) and the default Admin account will be created automatically upon the first run.*

## Default Credentials
To evaluate the admin features, log in using the automatically generated credentials:
- **Email:** `admin@trailmate.com`
- **Password:** `admin123`

---
*Developed for IIT Madras MAD1/MAD2 Project Evaluation.*
