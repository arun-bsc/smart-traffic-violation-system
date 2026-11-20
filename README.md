# Smart Traffic Violation Detection and Management System

A web application that helps traffic officers record violations, calculate fines automatically, generate QR code challans, and produce monthly reports.

## Features

- Secure admin login (passwords stored as hashes)
- Vehicle registration with owner details
- Violation entry with automatic fine calculation
- Search and filters (vehicle number, status, type, date)
- QR code challan with a public status page
- Payment status management (Paid / Unpaid)
- Repeat offender detection (3 or more violations)
- Monthly reports with Excel export
- Dashboard with statistics

## Tech Stack

- Frontend: HTML, CSS
- Backend: Python (Flask)
- Database: MySQL
- Libraries: mysql-connector-python, qrcode, openpyxl, python-dotenv

## How to Run Locally

1. Install Python 3 and MySQL.
2. Create a virtual environment and install the libraries:

       python -m venv venv
       venv\Scripts\activate
       python -m pip install -r requirements.txt

3. Create the database: run `schema.sql` in MySQL Workbench.
4. Copy `.env.example` to `.env` and fill in your own values.
5. Create the first admin:

       python create_admin.py

6. Start the app:

       python app.py

7. Open http://127.0.0.1:5000/login

## Security

- Passwords are hashed, and secrets are kept in a `.env` file (never uploaded).
- Database queries use placeholders to prevent SQL injection.
- Officer pages need login; the public QR page uses a random token.

## Author

ARUN KUMAR.M | JAMAL MOHAMED COLLEGE | GitHub: https://github.com/arun-bsc/smart-traffic-violation-system