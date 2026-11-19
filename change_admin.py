from getpass import getpass
from werkzeug.security import generate_password_hash
from db import query_one, execute

print("=== Change Admin Username / Password ===")

old_username = input("Current username: ").strip()
admin = query_one("SELECT admin_id FROM admins WHERE username = %s", (old_username,))

if not admin:
    print("No admin found with that username.")
    raise SystemExit

new_username = input("New username (press Enter to keep the same): ").strip() or old_username
new_password = getpass("New password (typing is hidden): ")

if len(new_password) < 6:
    print("Password must be at least 6 characters.")
    raise SystemExit

if new_username != old_username:
    taken = query_one("SELECT admin_id FROM admins WHERE username = %s", (new_username,))
    if taken:
        print("That new username is already taken.")
        raise SystemExit

execute(
    "UPDATE admins SET username = %s, password_hash = %s WHERE admin_id = %s",
    (new_username, generate_password_hash(new_password), admin["admin_id"]),
)

print("Admin updated successfully!")