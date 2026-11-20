import os
import re
import uuid
import qrcode
from datetime import date
from functools import wraps
from flask import Flask, render_template, request, redirect, session, flash, abort, send_file
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from werkzeug.security import check_password_hash
from dotenv import load_dotenv
from db import query_all, query_one, execute

load_dotenv()

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:5000")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

REPEAT_LIMIT = 3   # 3 or more violations = repeat offender


# ---------- Login protection ----------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "admin_id" not in session:
            flash("Please login first.", "warning")
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapper


def clean_date(text):
    """Return the text if it is a valid date, otherwise an empty text."""
    try:
        date.fromisoformat(text)
        return text
    except ValueError:
        return ""


# ---------- Home ----------
@app.route("/")
def home():
    return redirect("/dashboard")


# ---------- Module 1: Admin login ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        admin = query_one("SELECT * FROM admins WHERE username = %s", (username,))

        if admin and check_password_hash(admin["password_hash"], password):
            session.clear()
            session["admin_id"] = admin["admin_id"]
            session["admin_name"] = admin["full_name"]
            return redirect("/dashboard")

        flash("Invalid username or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect("/login")


# ---------- Module 2 and 12: Dashboard and statistics ----------
@app.route("/dashboard")
@login_required
def dashboard():
    vehicles = query_one("SELECT COUNT(*) AS total FROM vehicles")

    counts = query_one("""
        SELECT COUNT(*) AS total_violations,
               COALESCE(SUM(payment_status = 'Paid'), 0)   AS paid,
               COALESCE(SUM(payment_status = 'Unpaid'), 0) AS unpaid,
               COALESCE(SUM(CASE WHEN payment_status = 'Paid'
                                 THEN fine_amount END), 0)   AS paid_amount,
               COALESCE(SUM(CASE WHEN payment_status = 'Unpaid'
                                 THEN fine_amount END), 0)   AS unpaid_amount
        FROM violations
    """)

    stats = {
        "total_vehicles": vehicles["total"],
        "total_violations": counts["total_violations"],
        "paid": int(counts["paid"]),
        "unpaid": int(counts["unpaid"]),
        "paid_amount": float(counts["paid_amount"]),
        "unpaid_amount": float(counts["unpaid_amount"]),
    }

    monthly = query_all("""
        SELECT DATE_FORMAT(violation_date, '%Y-%m') AS month,
               COUNT(*) AS total
        FROM violations
        GROUP BY month
        ORDER BY month DESC
        LIMIT 6
    """)
    monthly.reverse()
    max_total = max([m["total"] for m in monthly], default=1)

    type_stats = query_all("""
        SELECT vt.violation_name, COUNT(v.violation_id) AS total
        FROM violation_types vt
        JOIN violations v ON v.type_id = vt.type_id
        GROUP BY vt.type_id, vt.violation_name
        ORDER BY total DESC
    """)

    recent = query_all("""
        SELECT v.violation_id, v.vehicle_id, ve.vehicle_number,
               vt.violation_name, v.location, v.violation_date,
               v.fine_amount, v.payment_status
        FROM violations v
        JOIN vehicles ve ON v.vehicle_id = ve.vehicle_id
        JOIN violation_types vt ON v.type_id = vt.type_id
        ORDER BY v.violation_id DESC
        LIMIT 5
    """)

    return render_template("dashboard.html", stats=stats, monthly=monthly,
                           max_total=max_total, type_stats=type_stats,
                           recent=recent)


# ---------- Module 3: Vehicle registration ----------
@app.route("/register-vehicle", methods=["GET", "POST"])
@login_required
def register_vehicle():
    if request.method == "POST":
        vehicle_number = request.form["vehicle_number"].strip().upper().replace(" ", "")
        vehicle_type = request.form["vehicle_type"].strip()
        owner_name = request.form["owner_name"].strip()
        owner_phone = request.form.get("owner_phone", "").strip()
        owner_address = request.form.get("owner_address", "").strip()

        if not re.fullmatch(r"[A-Z0-9]{6,12}", vehicle_number):
            flash("Vehicle number must be 6 to 12 letters or digits.", "danger")
            return redirect("/register-vehicle")

        if not vehicle_type or not owner_name:
            flash("Vehicle type and owner name are required.", "danger")
            return redirect("/register-vehicle")

        if owner_phone and not re.fullmatch(r"[0-9]{10}", owner_phone):
            flash("Phone number must be exactly 10 digits.", "danger")
            return redirect("/register-vehicle")

        existing = query_one(
            "SELECT vehicle_id FROM vehicles WHERE vehicle_number = %s",
            (vehicle_number,),
        )
        if existing:
            flash(f"Vehicle {vehicle_number} is already registered.", "warning")
            return redirect("/register-vehicle")

        execute(
            """INSERT INTO vehicles
               (vehicle_number, vehicle_type, owner_name, owner_phone, owner_address)
               VALUES (%s, %s, %s, %s, %s)""",
            (vehicle_number, vehicle_type, owner_name,
             owner_phone or None, owner_address or None),
        )
        flash(f"Vehicle {vehicle_number} registered successfully.", "success")
        return redirect("/register-vehicle")

    return render_template("register_vehicle.html")


# ---------- Module 4 and 5: Add violation with automatic fine ----------
@app.route("/add-violation", methods=["GET", "POST"])
@login_required
def add_violation():
    if request.method == "POST":
        vehicle_number = request.form["vehicle_number"].strip().upper().replace(" ", "")
        type_id = request.form["type_id"]
        location = request.form["location"].strip()
        date_text = request.form["violation_date"]

        # 1. The vehicle must already be registered
        vehicle = query_one(
            "SELECT vehicle_id FROM vehicles WHERE vehicle_number = %s",
            (vehicle_number,),
        )
        if not vehicle:
            flash(f"Vehicle {vehicle_number} is not registered. Please register it first.", "danger")
            return redirect("/add-violation")

        # 2. Automatic fine calculation: the fine comes from the database
        violation_type = query_one(
            "SELECT type_id, violation_name, fine_amount FROM violation_types WHERE type_id = %s",
            (type_id,),
        )
        if not violation_type:
            flash("Please select a valid violation type.", "danger")
            return redirect("/add-violation")

        # 3. Check the location and the date
        if not location:
            flash("Location is required.", "danger")
            return redirect("/add-violation")

        try:
            violation_date = date.fromisoformat(date_text)
        except ValueError:
            flash("Please enter a valid date.", "danger")
            return redirect("/add-violation")

        if violation_date > date.today():
            flash("Violation date cannot be in the future.", "danger")
            return redirect("/add-violation")

        # 4. Save the violation (payment status becomes 'Unpaid' automatically)
        fine = violation_type["fine_amount"]
        new_id = execute(
            """INSERT INTO violations
               (vehicle_id, type_id, admin_id, location, violation_date, fine_amount)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (vehicle["vehicle_id"], violation_type["type_id"], session["admin_id"],
             location, violation_date, fine),
        )

        flash(f"Violation recorded for {vehicle_number}. "
              f"Fine of ₹{fine:.2f} added. Status: Unpaid.", "success")
        return redirect(f"/challan/{new_id}")

    vehicles = query_all(
        "SELECT vehicle_number, owner_name FROM vehicles ORDER BY vehicle_number"
    )
    types = query_all(
        "SELECT type_id, violation_name, fine_amount FROM violation_types ORDER BY violation_name"
    )
    return render_template("add_violation.html", vehicles=vehicles, types=types,
                           today=date.today().isoformat())


# ---------- Module 6: Violation history with search and filter ----------
@app.route("/history")
@login_required
def history():
    filters = {
        "q": re.sub(r"[^A-Z0-9]", "", request.args.get("q", "").upper()),
        "status": request.args.get("status", ""),
        "type_id": request.args.get("type_id", ""),
        "date_from": clean_date(request.args.get("date_from", "")),
        "date_to": clean_date(request.args.get("date_to", "")),
    }

    sql = """
        SELECT v.violation_id, v.vehicle_id, ve.vehicle_number, ve.owner_name,
               vt.violation_name, v.location, v.violation_date,
               v.fine_amount, v.payment_status, v.paid_on
        FROM violations v
        JOIN vehicles ve ON v.vehicle_id = ve.vehicle_id
        JOIN violation_types vt ON v.type_id = vt.type_id
        WHERE 1 = 1
    """
    params = []

    if filters["q"]:
        sql += " AND ve.vehicle_number LIKE %s"
        params.append("%" + filters["q"] + "%")

    if filters["status"] in ("Paid", "Unpaid"):
        sql += " AND v.payment_status = %s"
        params.append(filters["status"])

    if filters["type_id"].isdigit():
        sql += " AND v.type_id = %s"
        params.append(int(filters["type_id"]))

    if filters["date_from"]:
        sql += " AND v.violation_date >= %s"
        params.append(filters["date_from"])

    if filters["date_to"]:
        sql += " AND v.violation_date <= %s"
        params.append(filters["date_to"])

    sql += " ORDER BY v.violation_id DESC"

    violations = query_all(sql, tuple(params))
    types = query_all("SELECT type_id, violation_name FROM violation_types ORDER BY violation_name")

    return render_template("history.html", filters=filters, types=types,
                           violations=violations)


# ---------- Module 6 and 9: Vehicle details ----------
@app.route("/vehicle/<int:vehicle_id>")
@login_required
def vehicle_details(vehicle_id):
    vehicle = query_one("SELECT * FROM vehicles WHERE vehicle_id = %s", (vehicle_id,))
    if not vehicle:
        flash("Vehicle not found.", "danger")
        return redirect("/history")

    violations = query_all("""
        SELECT v.violation_id, vt.violation_name, v.location,
               v.violation_date, v.fine_amount, v.payment_status
        FROM violations v
        JOIN violation_types vt ON v.type_id = vt.type_id
        WHERE v.vehicle_id = %s
        ORDER BY v.violation_id DESC
    """, (vehicle_id,))

    total = len(violations)
    unpaid_amount = sum(float(v["fine_amount"]) for v in violations
                        if v["payment_status"] == "Unpaid")
    is_repeat = total >= REPEAT_LIMIT

    return render_template("vehicle_details.html", vehicle=vehicle,
                           violations=violations, total=total,
                           unpaid_amount=unpaid_amount, is_repeat=is_repeat)


# ---------- Module 8: Payment status management ----------
@app.route("/mark-paid/<int:violation_id>", methods=["POST"])
@login_required
def mark_paid(violation_id):
    violation = query_one(
        "SELECT payment_status FROM violations WHERE violation_id = %s",
        (violation_id,),
    )

    if not violation:
        flash("Violation not found.", "danger")
    elif violation["payment_status"] == "Paid":
        flash("This fine is already marked as paid.", "info")
    else:
        execute(
            "UPDATE violations SET payment_status = 'Paid', paid_on = %s WHERE violation_id = %s",
            (date.today(), violation_id),
        )
        flash(f"Violation {violation_id} marked as Paid.", "success")

    return redirect(request.referrer or "/history")


# ---------- Module 7: QR code challan ----------
def make_qr(token):
    """Create the QR image for a token and return the file name."""
    folder = os.path.join(app.root_path, "static", "qrcodes")
    os.makedirs(folder, exist_ok=True)

    filename = f"{token}.png"
    image = qrcode.make(f"{BASE_URL}/status/{token}")
    image.save(os.path.join(folder, filename))
    return filename


@app.route("/challan/<int:violation_id>")
@login_required
def challan(violation_id):
    v = query_one("""
        SELECT v.violation_id, v.public_token, ve.vehicle_number, ve.vehicle_type,
               ve.owner_name, vt.violation_name, v.location, v.violation_date,
               v.fine_amount, v.payment_status, a.full_name AS officer_name
        FROM violations v
        JOIN vehicles ve ON v.vehicle_id = ve.vehicle_id
        JOIN violation_types vt ON v.type_id = vt.type_id
        JOIN admins a ON v.admin_id = a.admin_id
        WHERE v.violation_id = %s
    """, (violation_id,))

    if not v:
        flash("Challan not found.", "danger")
        return redirect("/history")

    token = v["public_token"]
    if not token:
        token = uuid.uuid4().hex
        execute("UPDATE violations SET public_token = %s WHERE violation_id = %s",
                (token, violation_id))

    qr_file = make_qr(token)
    return render_template("challan.html", v=v, qr_file=qr_file)


# ---------- Public status page (no login) ----------
@app.route("/status/<token>")
def status(token):
    v = query_one("""
        SELECT v.violation_id, ve.vehicle_number, vt.violation_name,
               v.location, v.violation_date, v.fine_amount,
               v.payment_status, v.paid_on
        FROM violations v
        JOIN vehicles ve ON v.vehicle_id = ve.vehicle_id
        JOIN violation_types vt ON v.type_id = vt.type_id
        WHERE v.public_token = %s
    """, (token,))

    if not v:
        abort(404)

    return render_template("status.html", v=v)

# ---------- Modules 9, 10, 11, 12: Monthly reports and Excel export ----------
def get_month_range(month_text):
    """Turn '2026-11' into (text, first day of month, first day of next month)."""
    month_text = (month_text or "").strip()
    try:
        if not re.fullmatch(r"\d{4}-\d{2}", month_text):
            raise ValueError
        year, month = int(month_text[:4]), int(month_text[5:7])
        start = date(year, month, 1)
        end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    except ValueError:
        # Wrong or empty month: use the current month instead
        today = date.today()
        month_text = today.strftime("%Y-%m")
        start = date(today.year, today.month, 1)
        end = date(today.year + 1, 1, 1) if today.month == 12 else date(today.year, today.month + 1, 1)
    return month_text, start, end


def safe_text(text):
    """Stop Excel from treating text that starts with = as a formula."""
    if isinstance(text, str) and text.startswith("="):
        return "'" + text
    return text


def load_report(month_text):
    """Collect all the report data for one month."""
    month_text, start, end = get_month_range(month_text)

    summary = query_one("""
        SELECT COUNT(*) AS total,
               COALESCE(SUM(fine_amount), 0) AS total_fine,
               COALESCE(SUM(CASE WHEN payment_status = 'Paid'
                                 THEN fine_amount END), 0)   AS paid_amount,
               COALESCE(SUM(CASE WHEN payment_status = 'Unpaid'
                                 THEN fine_amount END), 0)   AS unpaid_amount
        FROM violations
        WHERE violation_date >= %s AND violation_date < %s
    """, (start, end))
    for key in ("total_fine", "paid_amount", "unpaid_amount"):
        summary[key] = float(summary[key])

    type_stats = query_all("""
        SELECT vt.violation_name, COUNT(*) AS total
        FROM violations v
        JOIN violation_types vt ON v.type_id = vt.type_id
        WHERE v.violation_date >= %s AND v.violation_date < %s
        GROUP BY vt.type_id, vt.violation_name
        ORDER BY total DESC
    """, (start, end))

    repeat_offenders = query_all("""
        SELECT ve.vehicle_id, ve.vehicle_number, ve.owner_name,
               COUNT(v.violation_id) AS total
        FROM vehicles ve
        JOIN violations v ON v.vehicle_id = ve.vehicle_id
        GROUP BY ve.vehicle_id, ve.vehicle_number, ve.owner_name
        HAVING COUNT(v.violation_id) >= %s
        ORDER BY total DESC
    """, (REPEAT_LIMIT,))

    report_rows = query_all("""
        SELECT v.violation_id, ve.vehicle_number, ve.owner_name,
               vt.violation_name, v.location, v.violation_date,
               v.fine_amount, v.payment_status, v.paid_on
        FROM violations v
        JOIN vehicles ve ON v.vehicle_id = ve.vehicle_id
        JOIN violation_types vt ON v.type_id = vt.type_id
        WHERE v.violation_date >= %s AND v.violation_date < %s
        ORDER BY v.violation_date, v.violation_id
    """, (start, end))

    return {
        "month": month_text,
        "summary": summary,
        "type_stats": type_stats,
        "repeat_offenders": repeat_offenders,
        "report_rows": report_rows,
    }


@app.route("/reports")
@login_required
def reports():
    data = load_report(request.args.get("month", ""))
    return render_template("reports.html", **data)


@app.route("/export-excel")
@login_required
def export_excel():
    data = load_report(request.args.get("month", ""))
    month = data["month"]
    summary = data["summary"]

    wb = Workbook()
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1E3A8A")

    def style_header(sheet, row_number):
        for cell in sheet[row_number]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")

    # ----- Sheet 1: Summary -----
    ws = wb.active
    ws.title = "Summary"
    ws.append(["Monthly Traffic Violation Report", month])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([])
    ws.append(["Item", "Value"])
    style_header(ws, 3)
    ws.append(["Total violations", summary["total"]])
    ws.append(["Total fine amount (₹)", summary["total_fine"]])
    ws.append(["Collected (₹)", summary["paid_amount"]])
    ws.append(["Pending (₹)", summary["unpaid_amount"]])
    ws.append([])
    ws.append(["Violation type", "Total"])
    style_header(ws, ws.max_row)
    for t in data["type_stats"]:
        ws.append([t["violation_name"], t["total"]])
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 16

    # ----- Sheet 2: Violations -----
    ws2 = wb.create_sheet("Violations")
    ws2.append(["ID", "Vehicle No.", "Owner", "Violation", "Location",
                "Date", "Fine (₹)", "Status", "Paid On"])
    style_header(ws2, 1)
    for r in data["report_rows"]:
        ws2.append([
            r["violation_id"], r["vehicle_number"], safe_text(r["owner_name"]),
            r["violation_name"], safe_text(r["location"]), r["violation_date"],
            float(r["fine_amount"]), r["payment_status"], r["paid_on"],
        ])
    for column in ("F", "I"):
        for cell in ws2[column][1:]:
            cell.number_format = "DD-MM-YYYY"
    for column, width in zip("ABCDEFGHI", [8, 16, 20, 28, 28, 14, 12, 10, 14]):
        ws2.column_dimensions[column].width = width

    # ----- Sheet 3: Repeat offenders -----
    ws3 = wb.create_sheet("Repeat Offenders")
    ws3.append(["Vehicle No.", "Owner", "Total Violations"])
    style_header(ws3, 1)
    for r in data["repeat_offenders"]:
        ws3.append([r["vehicle_number"], safe_text(r["owner_name"]), r["total"]])
    for column, width in zip("ABC", [16, 24, 18]):
        ws3.column_dimensions[column].width = width

    # ----- Save a copy in the exports folder and send it -----
    folder = os.path.join(app.root_path, "exports")
    os.makedirs(folder, exist_ok=True)
    filename = f"traffic_report_{month}.xlsx"
    path = os.path.join(folder, filename)
    wb.save(path)

    return send_file(path, as_attachment=True, download_name=filename)


if __name__ == "__main__":
    app.run(debug=False)