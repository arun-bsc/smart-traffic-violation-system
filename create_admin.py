from getpass import getpass
from werkzeug.security import generate_password_hash
from db import query_one, execute

print("=== Create Admin Account ===")

username = input("Username: ").strip()
full_name = input("Full name: ").strip()
password = getpass("Password (typing is hidden): ")

if not username or not full_name:
    print("Username and full name cannot be empty.")
    raise SystemExit

if len(password) < 6:
    print("Password must be at least 6 characters.")
    raise SystemExit

existing = query_one("SELECT admin_id FROM admins WHERE username = %s", (username,))
if existing:
    print("This username already exists.")
    raise SystemExit

password_hash = generate_password_hash(password)

execute(
    "INSERT INTO admins (username, password_hash, full_name) VALUES (%s, %s, %s)",
    (username, password_hash, full_name),
)

print("Admin created successfully!")