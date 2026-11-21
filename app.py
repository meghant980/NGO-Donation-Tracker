from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import sqlite3, os, uuid
import qrcode
from datetime import datetime
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-demo-secret")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "NGO@Admin2026")

def admin_required():
    return session.get("is_admin") is True
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

PURPOSES = {
    "Education": {"icon": "🎓", "description": "School fees, books, learning materials and student support"},
    "Medical": {"icon": "🏥", "description": "Treatment, medicines, diagnostics and healthcare support"},
    "Food": {"icon": "🍚", "description": "Meals, groceries and food distribution programs"},
    "Shelter": {"icon": "🏠", "description": "Housing, blankets and essential shelter support"},
    "General": {"icon": "🌍", "description": "Flexible support for the NGO's general mission"},
}

ALLOWED_EXPENSES = {
    "Education": ["School fees", "Books & learning materials", "Uniforms", "Exam fees", "Educational supplies"],
    "Medical": ["Medicines", "Treatment", "Diagnostics / tests", "Doctor / hospital bill", "Medical supplies"],
    "Food": ["Groceries", "Prepared meals", "Food distribution", "Kitchen supplies"],
    "Shelter": ["Rent / shelter", "Blankets & bedding", "Shelter materials", "Essential household items"],
    "General": ["Program operations", "Community support", "General supplies", "Other approved program expense"],
}

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS donations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        donor_name TEXT NOT NULL,
        amount REAL NOT NULL CHECK(amount > 0),
        purpose TEXT NOT NULL,
        note TEXT,
        created_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Approved'
    );

    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        amount REAL NOT NULL CHECK(amount > 0),
        purpose TEXT NOT NULL,
        description TEXT NOT NULL,
        expense_category TEXT NOT NULL,
        vendor TEXT,
        receipt TEXT,
        status TEXT NOT NULL,
        rejection_reason TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_type TEXT NOT NULL,
        amount REAL NOT NULL,
        purpose TEXT NOT NULL,
        description TEXT NOT NULL,
        reference_id INTEGER,
        created_at TEXT NOT NULL
    );
    """)
    # Upgrade older databases created by previous versions.
    donation_columns = [r["name"] for r in conn.execute("PRAGMA table_info(donations)").fetchall()]
    if "status" not in donation_columns:
        conn.execute("ALTER TABLE donations ADD COLUMN status TEXT NOT NULL DEFAULT 'Approved'")
    if "qr_reference" not in donation_columns:
        conn.execute("ALTER TABLE donations ADD COLUMN qr_reference TEXT")
    if "payment_status" not in donation_columns:
        conn.execute("ALTER TABLE donations ADD COLUMN payment_status TEXT NOT NULL DEFAULT 'Not applicable'")
    columns = [r["name"] for r in conn.execute("PRAGMA table_info(expenses)").fetchall()]
    if "expense_category" not in columns:
        conn.execute("ALTER TABLE expenses ADD COLUMN expense_category TEXT NOT NULL DEFAULT 'Other approved program expense'")
        conn.commit()
    conn.close()

def money(value):
    return f"₹{value:,.0f}"

def get_fund_summary(conn):
    rows = []
    for purpose, meta in PURPOSES.items():
        received = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM donations WHERE purpose=? AND status='Approved'", (purpose,)
        ).fetchone()[0]
        spent = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM expenses WHERE purpose=? AND status='Approved'", (purpose,)
        ).fetchone()[0]
        rows.append({
            "purpose": purpose, "icon": meta["icon"], "description": meta["description"],
            "received": received, "spent": spent, "available": received-spent
        })
    return rows

def available_for_purpose(conn, purpose):
    received = conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM donations WHERE purpose=? AND status='Approved'", (purpose,)
    ).fetchone()[0]
    spent = conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM expenses WHERE purpose=? AND status='Approved'", (purpose,)
    ).fetchone()[0]
    return received - spent

@app.route("/")
def access_portal():
    return render_template("access.html", mode=request.args.get("mode", "user-login"))

@app.route("/dashboard")
def dashboard():
    conn = get_db()
    total_donations = conn.execute("SELECT COALESCE(SUM(amount),0) FROM donations WHERE status='Approved'").fetchone()[0]
    total_spent = conn.execute("SELECT COALESCE(SUM(amount),0) FROM expenses WHERE status='Approved'").fetchone()[0]
    total_available = total_donations - total_spent
    donation_count = conn.execute("SELECT COUNT(*) FROM donations WHERE status='Approved'").fetchone()[0]
    blocked_count = conn.execute("SELECT COUNT(*) FROM expenses WHERE status='Blocked'").fetchone()[0]
    approved_count = conn.execute("SELECT COUNT(*) FROM expenses WHERE status='Approved'").fetchone()[0]
    funds = get_fund_summary(conn)
    transactions = conn.execute(
        "SELECT * FROM transactions ORDER BY id DESC LIMIT 8"
    ).fetchall()
    conn.close()
    trust = 100 if (approved_count + blocked_count) == 0 else round(approved_count/(approved_count+blocked_count)*100, 1)
    return render_template("dashboard.html", total_donations=total_donations,
        total_spent=total_spent, total_available=total_available,
        donation_count=donation_count, blocked_count=blocked_count,
        funds=funds, transactions=transactions, trust=trust)

@app.route("/donate", methods=["GET","POST"])
def donate():
    if request.method == "POST":
        donor = request.form.get("donor_name","").strip()
        amount_raw = request.form.get("amount","").strip()
        purpose = request.form.get("purpose","")
        note = request.form.get("note","").strip()
        try:
            amount = float(amount_raw)
        except ValueError:
            amount = 0
        if not donor or amount <= 0 or purpose not in PURPOSES:
            flash("Please enter a valid donor, amount and purpose.", "error")
            return redirect(url_for("donate"))
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        qr_reference = "NGO-" + uuid.uuid4().hex[:12].upper()
        qr_dir = os.path.join(UPLOAD_DIR, "donation_qr")
        os.makedirs(qr_dir, exist_ok=True)
        qr_filename = qr_reference + ".png"
        # QR opens the virtual payment page. No bank/UPI transfer is performed.
        qr_payload = url_for("demo_payment", reference=qr_reference, _external=True)
        qr_image = qrcode.make(qr_payload)
        qr_image.save(os.path.join(qr_dir, qr_filename))

        conn = get_db()
        conn.execute(
            """INSERT INTO donations
               (donor_name,amount,purpose,note,created_at,status,qr_reference,payment_status)
               VALUES(?,?,?,?,?,?,?,?)""",
            (donor, amount, purpose, note, now, "Pending", qr_reference, "Demo QR - not paid")
        )
        conn.commit()
        conn.close()
        flash("Donation request submitted. The demo QR is generated; no payment has been received. Admin approval is still required.", "success")
        return redirect(url_for("donation_qr", reference=qr_reference))
    return render_template("donate.html", purposes=PURPOSES)

@app.route("/donation-qr/<reference>")
def donation_qr(reference):
    conn = get_db()
    donation = conn.execute(
        "SELECT * FROM donations WHERE qr_reference=?", (reference,)
    ).fetchone()
    conn.close()
    if donation is None:
        flash("Donation QR reference not found.", "error")
        return redirect(url_for("donate"))
    qr_file = f"uploads/donation_qr/{reference}.png"
    return render_template("donation_qr.html", donation=donation, qr_file=qr_file, money=money)

@app.route("/demo-pay/<reference>", methods=["GET", "POST"])
def demo_payment(reference):
    conn = get_db()
    donation = conn.execute("SELECT * FROM donations WHERE qr_reference=?", (reference,)).fetchone()
    if donation is None:
        conn.close()
        flash("Donation reference not found.", "error")
        return redirect(url_for("access_portal"))
    if request.method == "POST":
        if donation["payment_status"] != "Demo paid - no real money":
            conn.execute("UPDATE donations SET payment_status=? WHERE qr_reference=?",
                         ("Demo paid - no real money", reference))
            conn.commit()
        donation = conn.execute("SELECT * FROM donations WHERE qr_reference=?", (reference,)).fetchone()
        conn.close()
        return render_template("demo_payment_success.html", donation=donation, money=money)
    conn.close()
    return render_template("demo_payment.html", donation=donation, money=money)

@app.route("/funds")
def funds():
    conn = get_db()
    fund_rows = get_fund_summary(conn)
    recent_donations = conn.execute("SELECT * FROM donations WHERE status='Approved' ORDER BY id DESC LIMIT 10").fetchall()
    conn.close()
    return render_template("funds.html", funds=fund_rows, donations=recent_donations)

@app.route("/spend", methods=["GET","POST"])
def spend():
    conn = get_db()
    if request.method == "POST":
        purpose = request.form.get("purpose","")
        expense_category = request.form.get("expense_category","")
        description = request.form.get("description","").strip()
        vendor = request.form.get("vendor","").strip()
        amount_raw = request.form.get("amount","").strip()
        try:
            amount = float(amount_raw)
        except ValueError:
            amount = 0

        if purpose not in PURPOSES or expense_category not in ALLOWED_EXPENSES.get(purpose, []) or not description or amount <= 0:
            conn.close()
            flash("Choose a valid expense category for the selected protected fund.", "error")
            return redirect(url_for("spend"))

        available = available_for_purpose(conn, purpose)
        receipt_file = request.files.get("receipt")
        receipt_name = None
        if receipt_file and receipt_file.filename:
            ext = os.path.splitext(receipt_file.filename)[1].lower()
            if ext in [".jpg",".jpeg",".png",".pdf"]:
                receipt_name = secure_filename(f"{uuid.uuid4().hex}{ext}")
                receipt_file.save(os.path.join(UPLOAD_DIR, receipt_name))

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if amount > available:
            reason = f"Only ₹{available:,.0f} is available in the {purpose} Fund."
            cur = conn.execute(
                """INSERT INTO expenses(amount,purpose,description,expense_category,vendor,receipt,status,rejection_reason,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (amount,purpose,description,vendor,receipt_name,"Blocked",reason,now)
            )
            expense_id = cur.lastrowid
            conn.execute(
                """INSERT INTO transactions(transaction_type,amount,purpose,description,reference_id,created_at)
                   VALUES(?,?,?,?,?,?)""",
                ("Blocked", amount, purpose, f"{expense_category}: {description} — {reason}", expense_id, now)
            )
            conn.commit(); conn.close()
            flash(f"Expense blocked. {reason}", "error")
            return redirect(url_for("transactions"))

        cur = conn.execute(
            """INSERT INTO expenses(amount,purpose,description,vendor,receipt,status,rejection_reason,created_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (amount,purpose,description,vendor,receipt_name,"Approved",None,now)
        )
        expense_id = cur.lastrowid
        conn.execute(
            """INSERT INTO transactions(transaction_type,amount,purpose,description,reference_id,created_at)
               VALUES(?,?,?,?,?,?)""",
            ("Expense", amount, purpose, f"{expense_category}: {description}", expense_id, now)
        )
        conn.commit(); conn.close()
        flash(f"₹{amount:,.0f} expense approved from the {purpose} Fund.", "success")
        return redirect(url_for("transactions"))

    fund_rows = get_fund_summary(conn)
    conn.close()
    return render_template("spend.html", funds=fund_rows, purposes=PURPOSES, allowed_expenses=ALLOWED_EXPENSES)

@app.route("/transactions")
def transactions():
    conn = get_db()
    txns = conn.execute("SELECT * FROM transactions ORDER BY id DESC").fetchall()
    expenses = conn.execute("SELECT * FROM expenses ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("transactions.html", transactions=txns, expenses=expenses)

@app.route("/transparency")
def transparency():
    conn = get_db()
    funds = get_fund_summary(conn)
    donations = conn.execute("SELECT * FROM donations WHERE status='Approved' ORDER BY id DESC").fetchall()
    expenses = conn.execute("SELECT * FROM expenses WHERE status='Approved' ORDER BY id DESC").fetchall()
    blocked = conn.execute("SELECT * FROM expenses WHERE status='Blocked' ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("transparency.html", funds=funds, donations=donations, expenses=expenses, blocked=blocked)

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("username", "") == ADMIN_USERNAME and request.form.get("password", "") == ADMIN_PASSWORD:
            session.clear()
            session["is_admin"] = True
            flash("Admin login successful.", "success")
            return redirect(url_for("admin_donations"))
        flash("Invalid admin username or password.", "error")
        return redirect(url_for("access_portal", mode="admin"))
    return redirect(url_for("access_portal", mode="admin"))

@app.route("/signup", methods=["POST"])
def user_signup():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    if not name or not email or len(password) < 6:
        flash("Enter your name, a valid email and password (at least 6 characters).", "error")
        return redirect(url_for("access_portal", mode="signup"))
    conn = get_db()
    try:
        conn.execute("INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)",
                     (name, email, generate_password_hash(password), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        flash("This email is already registered. Please log in.", "error")
        return redirect(url_for("access_portal", mode="user-login"))
    conn.close()
    session.clear()
    session["user_email"] = email
    session["user_name"] = name
    flash("Account created successfully. Welcome!", "success")
    return redirect(url_for("transparency"))

@app.route("/user-login", methods=["POST"])
def user_login():
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    conn.close()
    if not user or not check_password_hash(user["password_hash"], password):
        flash("Invalid email or password.", "error")
        return redirect(url_for("access_portal", mode="user-login"))
    session.clear()
    session["user_email"] = user["email"]
    session["user_name"] = user["name"]
    flash("Welcome back!", "success")
    return redirect(url_for("transparency"))

@app.route("/user-logout", methods=["POST"])
def user_logout():
    session.clear()
    return redirect(url_for("access_portal"))

@app.route("/admin-logout", methods=["POST"])
def admin_logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("admin_login"))

@app.route("/admin/donations")
def admin_donations():
    if not admin_required():
        return redirect(url_for("admin_login"))
    conn = get_db()
    pending = conn.execute("SELECT * FROM donations WHERE status='Pending' ORDER BY id DESC").fetchall()
    reviewed = conn.execute("SELECT * FROM donations WHERE status IN ('Approved','Rejected') ORDER BY id DESC LIMIT 50").fetchall()
    conn.close()
    return render_template("admin_donations.html", pending=pending, reviewed=reviewed)

@app.route("/admin/donation/<int:donation_id>/<action>", methods=["POST"])
def review_donation(donation_id, action):
    if not admin_required():
        return redirect(url_for("admin_login"))
    if action not in ("approve", "reject"):
        flash("Invalid action.", "error")
        return redirect(url_for("admin_donations"))
    status = "Approved" if action == "approve" else "Rejected"
    conn = get_db()
    donation = conn.execute("SELECT * FROM donations WHERE id=? AND status='Pending'", (donation_id,)).fetchone()
    if not donation:
        conn.close()
        flash("Donation request not found or already reviewed.", "error")
        return redirect(url_for("admin_donations"))
    conn.execute("UPDATE donations SET status=? WHERE id=?", (status, donation_id))
    if status == "Approved":
        conn.execute("INSERT INTO transactions(transaction_type,amount,purpose,description,reference_id,created_at) VALUES(?,?,?,?,?,?)",
                      ("Donation", donation["amount"], donation["purpose"], f"Donation from {donation['donor_name']}", donation_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit(); conn.close()
    flash(f"Donation {status.lower()} successfully.", "success")
    return redirect(url_for("admin_donations"))

@app.route("/api/funds")
def api_funds():
    conn = get_db()
    data = get_fund_summary(conn)
    conn.close()
    return jsonify(data)

@app.context_processor
def utility_processor():
    return {"money": money, "current_year": datetime.now().year}

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
