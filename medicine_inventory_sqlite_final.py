# -----------------------------------
# MEDICINE INVENTORY FLASK APP
# -----------------------------------

from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import sqlite3
from datetime import datetime, timedelta
from flask import flash, get_flashed_messages

# --- Initialize Flask App ---
app = Flask(__name__)
app.secret_key = 'your-secret-key'  # Change this to a secure string

# --- Login Setup ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- User Class ---
class User(UserMixin):
    def __init__(self, id, username, role):
        self.id = id
        self.username = username
        self.role = role

# --- Load User from DB ---
@login_manager.user_loader
def load_user(user_id):
    with sqlite3.connect("medicine.db") as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, username, role FROM users WHERE id = ?", (user_id,))
        user = cur.fetchone()
        if user:
            return User(user[0], user[1], user[2])
    return None

# --- DB Connection ---
def get_db_connection():
    conn = sqlite3.connect("medicine.db")
    conn.row_factory = sqlite3.Row
    return conn

# --- Expiry Check ---
def is_near_expiry(expiry_str):
    try:
        expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d")
        return expiry_date <= datetime.today() + timedelta(days=90)
    except:
        return False

# --- Initialize Database ---
def init_db():
    with sqlite3.connect("medicine.db") as conn:
        cur = conn.cursor()
        # Create tables
        cur.execute("""
            CREATE TABLE IF NOT EXISTS medicine_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                district TEXT,
                report_month TEXT,
                generic TEXT,
                brand TEXT,
                form TEXT,
                strength TEXT,
                price REAL,
                expiry TEXT,
                opening INTEGER,
                receiving INTEGER,
                issue INTEGER,
                discard INTEGER,
                return_qty INTEGER,
                closing INTEGER,
                total REAL,
                remarks TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password TEXT,
                role TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS master_medicines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                generic TEXT,
                brand TEXT,
                form TEXT,
                strength TEXT,
                price REAL
            )
        """)
        # Insert default users if not exist
        cur.execute("SELECT COUNT(*) FROM users")
        if cur.fetchone()[0] == 0:
            cur.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", ("admin", "admin123", "admin"))
            cur.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", ("Kech", "kech123", "district"))
        conn.commit()

#  This route is for login/logout/index/home routes
@app.route("/")
def index():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        with sqlite3.connect("medicine.db") as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, username, role FROM users WHERE username = ? AND password = ?", (username, password))
            user = cur.fetchone()
            if user:
                login_user(User(user[0], user[1], user[2]))
                return redirect(url_for("home"))
            return "Invalid credentials", 401
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# this route is for admin dashboard logic
@app.route("/home")
@login_required
def home():
    if current_user.role != "admin":
        return redirect(url_for("district_dashboard"))

    filters = {
        'district': request.args.get("district"),
        'generic': request.args.get("generic"),
        'brand': request.args.get("brand"),
        'form': request.args.get("form"),
        'start_date': request.args.get("start_date"),
        'end_date': request.args.get("end_date")
    }

    query = "SELECT * FROM medicine_data WHERE 1=1"
    params = []
    for key, value in filters.items():
        if value:
            if key == 'district':
                query += " AND LOWER(district) = ?"
                params.append(value.lower())
            elif key in ['generic', 'brand', 'form']:
                query += f" AND LOWER({key}) LIKE ?"
                params.append(f"%{value.lower()}%")
            elif key == 'start_date':
                query += " AND date >= ?"
                params.append(value)
            elif key == 'end_date':
                query += " AND date <= ?"
                params.append(value)

    conn = get_db_connection()
    rows = conn.execute(query, params).fetchall()

    data, near_expiry, low_stock = [], 0, 0
    today = datetime.today()

    for row in rows:
        try:
            price = float(row["price"])
            closing = float(row["closing"])
            expiry_date = datetime.strptime(row["expiry"], "%Y-%m-%d")
        except:
            price, closing, expiry_date = 0.0, 0.0, None

        total = round(price * closing, 2)
        expiry_status = ""
        if expiry_date:
            if expiry_date < today:
                expiry_status = "Expired"
            elif expiry_date <= today + timedelta(days=90):
                expiry_status = "Near Expiry"

        if expiry_status == "Near Expiry":
            near_expiry += 1
        if closing < 10:
            low_stock += 1

        data.append(dict(row, total=total, expiry_status=expiry_status))

    # Sort: expired → near expiry → others
    data.sort(key=lambda x: (
        0 if x.get('expiry_status') == 'Expired' else
        1 if x.get('expiry_status') == 'Near Expiry' else
        2
    ))

    summary = {
        "total_entries": len(data),
        "near_expiry": near_expiry,
        "low_stock": low_stock
    }

    generics = [row["generic"] for row in conn.execute("SELECT DISTINCT generic FROM medicine_data WHERE generic IS NOT NULL")]
    brands = [row["brand"] for row in conn.execute("SELECT DISTINCT brand FROM medicine_data WHERE brand IS NOT NULL")]
    forms = [row["form"] for row in conn.execute("SELECT DISTINCT form FROM medicine_data WHERE form IS NOT NULL")]
    districts = sorted([
        "Awaran", "Barkhan", "Chaghi", "Chaman", "Dera Bugti", "Dukki", "Gwadar", "Harnai", "Hub", "Jaffarabad",
        "Jhal Magsi", "Kachhi", "Kalat", "Kech", "Khuzdar", "Kharan", "Killa Abdullah", "Killa Saifullah",
        "Kohlu", "Lasbela", "Loralai", "Mastung", "Musakhel", "Nasirabad", "Nushki", "Panjgur", "Pishin",
        "Quetta", "Sherani", "Sibi", "Sohbatpur", "Surab", "Usta Muhammad", "Washuk", "Zhob", "Ziarat"
    ])

    conn.close()
    return render_template("dashboard.html",
                           data=data,
                           summary=summary,
                           districts=districts,
                           generics=generics,
                           brands=brands,
                           forms=forms,
                           current_user=current_user)

@app.route("/admin-users", methods=["GET", "POST"])
@login_required
def admin_users():
    if current_user.role != "admin":
        return "Access denied", 403

    conn = get_db_connection()
    cur = conn.cursor()

    # Add new user
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        role = request.form.get("role")

        if username and password and role:
            try:
                cur.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (username, password, role))
                conn.commit()
            except sqlite3.IntegrityError:
                return "Username already exists", 400

    users = cur.execute("SELECT * FROM users").fetchall()
    conn.close()
    return render_template("admin_users.html", users=users)
#this is for reseting the password 
@app.route("/reset-password/<int:user_id>", methods=["GET", "POST"])
@login_required
def reset_password(user_id):
    if current_user.role != "admin":
        return "Access denied", 403

    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    if request.method == "POST":
        new_pass = request.form.get("new_password")
        confirm_pass = request.form.get("confirm_password")

        if new_pass != confirm_pass:
            return "Passwords do not match", 400

        conn.execute("UPDATE users SET password = ? WHERE id = ?", (new_pass, user_id))
        conn.commit()
        conn.close()
        return redirect(url_for("admin_users"))

    return render_template("reset_password.html", user=user)

# this route is for deleting a user
@app.route("/delete-user/<int:user_id>", methods=["POST"])
@login_required
def delete_user(user_id):
    if current_user.role != "admin":
        return "Access denied", 403

    conn = get_db_connection()
    cur = conn.cursor()

    # Prevent deletion of main admin
    cur.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    user = cur.fetchone()
    if user and user["username"].lower() == "admin":
        conn.close()
        return "Cannot delete the main admin user.", 403

    cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    return redirect(url_for("admin_users"))
    
# this route is for adding medicine
@app.route("/add-medicine", methods=["GET", "POST"])
@login_required
def add_medicine():
    if current_user.role != "admin":
        return "Access denied", 403

    if request.method == "POST":
        generic = request.form.get("generic")
        brand = request.form.get("brand")
        form = request.form.get("form")
        strength = request.form.get("strength")
        price = request.form.get("price")

        with sqlite3.connect("medicine.db") as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO master_medicines (generic, brand, form, strength, price)
                VALUES (?, ?, ?, ?, ?)
            """, (generic, brand, form, strength, float(price)))
            conn.commit()

        flash("✅ Medicine added successfully!")
        return redirect(url_for("add_medicine"))

    return render_template("add_medicine.html")

#this route is for uploading  csv file
@app.route("/upload-csv", methods=["POST"])
@login_required
def upload_csv():
    if current_user.role != "admin":
        return "Access denied", 403

    file = request.files.get("csv_file")
    if not file:
        return "No file uploaded", 400

    import csv
    import io

    stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
    reader = csv.DictReader(stream)

    with sqlite3.connect("medicine.db") as conn:
        cur = conn.cursor()
        for row in reader:
            cur.execute("""
                INSERT INTO master_medicines (generic, brand, form, strength, price)
                VALUES (?, ?, ?, ?, ?)
            """, (
                row.get("Generic"),
                row.get("Brand"),
                row.get("Form"),
                row.get("Strength"),
                float(row.get("Price", 0))
            ))
        conn.commit()
    flash("✅ CSV uploaded and medicines added!")
    return redirect(url_for("add_medicine"))


# this route is for edit medicine
@app.route("/edit-medicine/<int:medicine_id>", methods=["GET", "POST"])
@login_required
def edit_medicine(medicine_id):
    if current_user.role != "admin":
        return "Access denied", 403

    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == "POST":
        generic = request.form["generic"]
        brand = request.form["brand"]
        form = request.form["form"]
        strength = request.form["strength"]
        price = request.form["price"]

        cur.execute("""
            UPDATE master_medicines
            SET generic = ?, brand = ?, form = ?, strength = ?, price = ?
            WHERE id = ?
        """, (generic, brand, form, strength, float(price), medicine_id))
        conn.commit()
        conn.close()
        return redirect(url_for("manage_medicines"))

    medicine = conn.execute("SELECT * FROM master_medicines WHERE id = ?", (medicine_id,)).fetchone()
    conn.close()

    if not medicine:
        return "Medicine not found", 404

    return render_template("edit_medicine.html", medicine=medicine)
 #this route is for medicine management
@app.route("/manage-medicines")
@login_required
def manage_medicines():
    if current_user.role != "admin":
        return "Access denied", 403

    conn = get_db_connection()
    medicines = conn.execute("SELECT * FROM master_medicines").fetchall()
    conn.close()

    return render_template("manage_medicines.html", medicines=medicines)

@app.route("/delete-medicine/<int:medicine_id>")
@login_required
def delete_medicine(medicine_id):
    if current_user.role != "admin":
        return "Access denied", 403

    conn = get_db_connection()
    conn.execute("DELETE FROM master_medicines WHERE id = ?", (medicine_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("manage_medicines"))

# this route is for warehouse entry 
@app.route("/warehouse-entry", methods=["GET", "POST"])
@login_required
def warehouse_entry():
    if current_user.role != "district":
        return "Access denied", 403

    selected_month = request.args.get("month")
    selected_year = request.args.get("year")

    conn = get_db_connection()
    cur = conn.cursor()

    # Fetch master medicine list
    cur.execute("SELECT * FROM master_medicines")
    rows = cur.fetchall()
    sample_medicines = [
        {
            "generic": row["generic"],
            "brand": row["brand"],
            "form": row["form"],
            "strength": row["strength"],
            "price": row["price"]
        } for row in rows
    ]
    conn.close()

    if request.method == "POST":
        month = request.form.get("month")
        year = request.form.get("year")
        date = datetime.today().strftime("%Y-%m-%d")
        district = current_user.username

        entries = zip(
            request.form.getlist("generic"),
            request.form.getlist("brand"),
            request.form.getlist("form"),
            request.form.getlist("strength"),
            request.form.getlist("price"),
            request.form.getlist("expiry"),
            request.form.getlist("opening"),
            request.form.getlist("receiving"),
            request.form.getlist("issue"),
            request.form.getlist("discard"),
            request.form.getlist("return_qty"),
            request.form.getlist("closing"),
            request.form.getlist("total"),
            request.form.getlist("remarks")
        )

        conn = get_db_connection()
        cur = conn.cursor()
        for entry in entries:
            cur.execute("""
                INSERT INTO medicine_data (
                    date, district, report_month, generic, brand, form, strength, price, expiry,
                    opening, receiving, issue, discard, return_qty, closing, total, remarks
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                date, district, f"{month}-{year}", *entry
            ))
        conn.commit()
        conn.close()

        return render_template("warehouse_submit_popup.html")

    return render_template("warehouse_entry.html",
                           medicines=sample_medicines,
                           selected_month=selected_month,
                           selected_year=selected_year)

# this route is for district dashboard
@app.route("/district_dashboard")
@login_required
def district_dashboard():
    user_district = current_user.username

    filters = {
        'generic': request.args.get("generic"),
        'brand': request.args.get("brand"),
        'form': request.args.get("form"),
        'start_date': request.args.get("start_date"),
        'end_date': request.args.get("end_date")
    }

    query = "SELECT * FROM medicine_data WHERE district = ?"
    params = [user_district]

    for key, value in filters.items():
        if value:
            if key == 'generic':
                query += f" AND {key} LIKE ?"
                params.append(f"%{value}%")
            elif key == 'start_date':
                query += " AND date >= ?"
                params.append(value)
            elif key == 'end_date':
                query += " AND date <= ?"
                params.append(value)
            else:
                query += f" AND {key} = ?"
                params.append(value)

    conn = get_db_connection()
    rows = conn.execute(query, params).fetchall()

    data = []
    near_expiry = low_stock = 0
    for row in rows:
        try:
            price = float(row["price"])
        except (TypeError, ValueError):
            price = 0.0
        try:
            closing = float(row["closing"])
        except (TypeError, ValueError):
            closing = 0.0
        total = round(price * closing, 2)

        expiring = is_near_expiry(row["expiry"])
        if expiring:
            near_expiry += 1
        if closing < 10:
            low_stock += 1

        data.append(dict(row, total=total, is_expiring=expiring))

    summary = {
        "total_entries": len(data),
        "near_expiry": near_expiry,
        "low_stock": low_stock
    }

    generics = [row["generic"] for row in conn.execute("SELECT DISTINCT generic FROM medicine_data WHERE district = ?", [user_district])]
    brands = [row["brand"] for row in conn.execute("SELECT DISTINCT brand FROM medicine_data WHERE district = ?", [user_district])]
    forms = [row["form"] for row in conn.execute("SELECT DISTINCT form FROM medicine_data WHERE district = ?", [user_district])]

    conn.close()
    return render_template("district_dashboard.html", data=data, summary=summary,
                           generics=generics, brands=brands, forms=forms)
                           
#this route is for chart or visualization
@app.route("/charts-data")
@login_required
def charts_data():
    conn = get_db_connection()
    rows = conn.execute("""
        SELECT district, report_month, SUM(closing) AS total
        FROM medicine_data
        GROUP BY district, report_month
        ORDER BY report_month
    """).fetchall()

    line_data = {}
    months = sorted(set(row["report_month"] for row in rows))
    for row in rows:
        district = row["district"]
        if district not in line_data:
            line_data[district] = {m: 0 for m in months}
        line_data[district][row["report_month"]] = row["total"]

    line_chart = {
        "labels": months,
        "datasets": [
            {"label": district, "data": [line_data[district][m] for m in months]}
            for district in line_data
        ]
    }

    pie_data = conn.execute("SELECT SUM(issue), SUM(discard), SUM(return_qty), SUM(closing) FROM medicine_data").fetchone()
    pie_chart = {
        "labels": ["Issued", "Damaged", "Returned", "Available"],
        "data": [pie_data[0] or 0, pie_data[1] or 0, pie_data[2] or 0, pie_data[3] or 0]
    }

    conn.close()
    return jsonify({"line_chart": line_chart, "pie_chart": pie_chart})


if __name__ == "__main__":
    init_db()
    app.run(debug=True)