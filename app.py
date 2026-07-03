import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
from datetime import datetime, timedelta
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
    options_to_json,
    base64url_to_bytes,
)
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    ResidentKeyRequirement,
    UserVerificationRequirement,
    PublicKeyCredentialDescriptor,
)

load_dotenv()

app = Flask(__name__, instance_relative_config=True)

# Secret key signs the session cookie so it cannot be forged.
# Set SECRET_KEY in a .env file locally and in the docker environment on the server.
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
if not app.config["SECRET_KEY"]:
    raise RuntimeError("SECRET_KEY is not set. Add it to your .env file or docker environment.")

app.config["SESSION_COOKIE_HTTPONLY"] = True   # JS on the page can never read the cookie
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"  # blocks the cookie on cross-site POSTs (CSRF mitigation)

def get_db_connection():
    """Helper function to connect to the database easily."""
    # Defaults to the docker path; set DB_PATH in .env to run locally.
    db_path = os.environ.get('DB_PATH', '/app/spending.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

LOOKUP_TABLES = {
    "card": {
        "table": "card_info",
        "id_column": "card_id",
        "usage_checks": [
            ("spending", "card_id"),
            ("bills", "card_id"),
        ],
        "label": "card",
        "scoped": True,   # each user has their own list
    },
    "category": {
        "table": "category_info",
        "id_column": "category_id",
        "usage_checks": [
            ("spending", "category_id"),
        ],
        "label": "category",
        "scoped": True,
    },
    "bill": {
        "table": "bill_info",
        "id_column": "bill_id",
        "usage_checks": [
            ("bills", "bill_id"),
        ],
        "label": "bill",
        "scoped": False,  # bill types are shared family-wide
    },
}

def load_lookup_data(conn):
    """Load dropdown data for the Add Transaction Page (cards/categories are per-user)."""
    return {
        "cards": conn.execute(
            "SELECT * FROM card_info WHERE user_id = ? ORDER BY name", (session["user_id"],)
        ).fetchall(),
        "bills": conn.execute("SELECT * FROM bill_info ORDER BY name").fetchall(),
        "categories": conn.execute(
            "SELECT * FROM category_info WHERE user_id = ? ORDER BY name", (session["user_id"],)
        ).fetchall(),
    }

def render_add_form(conn, error=None, status_code=200):
    """Render add.html with all dropdown lists and an optional error message."""
    data = load_lookup_data(conn)
    return render_template("add.html", error=error, **data), status_code

def login_required(view):
    """Redirect to the login page if the user is not signed in."""
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped_view

@app.route('/login', methods=('GET', 'POST'))
def login():
    if session.get("user_id") is not None:
        return redirect(url_for("index"))

    error = None
    if request.method == 'POST':
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        conn.close()

        # Same message whether the username or the password was wrong,
        # so an attacker can't tell which usernames exist.
        if user is None or not check_password_hash(user["password_hash"], password):
            error = "Invalid username or password."
        else:
            session.clear()
            session["user_id"] = user["user_id"]
            return redirect(url_for("index"))

    return render_template("login.html", error=error)

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------------------------------------------------------------
# Passkeys (Face ID / Touch ID sign-in via WebAuthn)
# ---------------------------------------------------------------

def get_rp_id():
    """The domain passkeys are bound to. Override with RP_ID behind a proxy."""
    return os.environ.get("RP_ID") or request.host.split(":")[0]

def get_rp_origin():
    """The origin the browser reports. Override with RP_ORIGIN behind a
    proxy/tunnel, where Flask sees http but the browser is on https."""
    return os.environ.get("RP_ORIGIN") or f"{request.scheme}://{request.host}"

def ensure_passkeys_table(conn):
    """Safe to run against an existing database — only creates the table once."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS passkeys (
            credential_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            public_key BLOB NOT NULL,
            sign_count INTEGER NOT NULL DEFAULT 0,
            created TEXT NOT NULL DEFAULT (date('now')),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)

def migrate_family_columns():
    """Upgrade an existing database for per-user spending.

    Adds a user_id column to spending/bills if missing, and assigns any
    unowned rows to the earliest-created user. Runs at startup and after
    create-user; a no-op once the database is up to date.
    """
    conn = get_db_connection()
    try:
        try:
            first_user = conn.execute("SELECT MIN(user_id) FROM users").fetchone()[0]
        except sqlite3.Error:
            first_user = None  # users table not created yet

        for table in ("spending", "bills"):
            cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
            if not cols:
                continue  # table doesn't exist yet (fresh install uses schema.sql)
            if "user_id" not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER REFERENCES users(user_id)")
            if first_user is not None:
                conn.execute(f"UPDATE {table} SET user_id = ? WHERE user_id IS NULL", (first_user,))

        # Cards and categories are per-user with names unique per user, not
        # globally. The old tables had a global UNIQUE(name) that ALTER can't
        # remove, so these are rebuilt once (keeping ids so transaction
        # references stay valid).
        for table, id_col in (("card_info", "card_id"), ("category_info", "category_id")):
            cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
            if not cols:
                continue
            if "user_id" not in cols:
                conn.execute(f"""
                    CREATE TABLE {table}_new (
                        {id_col} INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        user_id INTEGER REFERENCES users(user_id),
                        UNIQUE(user_id, name)
                    )
                """)
                conn.execute(f"INSERT INTO {table}_new ({id_col}, name) SELECT {id_col}, name FROM {table}")
                conn.execute(f"DROP TABLE {table}")
                conn.execute(f"ALTER TABLE {table}_new RENAME TO {table}")
            if first_user is not None:
                conn.execute(f"UPDATE {table} SET user_id = ? WHERE user_id IS NULL", (first_user,))
        conn.commit()
    except sqlite3.Error:
        # Database not initialized yet (e.g. before init-db / create-user) — nothing to migrate.
        pass
    finally:
        conn.close()

migrate_family_columns()

@app.route('/passkey/register/begin', methods=['POST'])
@login_required
def passkey_register_begin():
    conn = get_db_connection()
    ensure_passkeys_table(conn)
    user = conn.execute(
        "SELECT * FROM users WHERE user_id = ?", (session["user_id"],)
    ).fetchone()
    existing = conn.execute(
        "SELECT credential_id FROM passkeys WHERE user_id = ?", (session["user_id"],)
    ).fetchall()
    conn.commit()
    conn.close()

    options = generate_registration_options(
        rp_id=get_rp_id(),
        rp_name="SpendU",
        user_name=user["username"],
        user_id=str(user["user_id"]).encode(),
        authenticator_selection=AuthenticatorSelectionCriteria(
            # resident key -> the phone remembers the account, so login
            # needs no username; user_verification -> Face ID is required,
            # simply possessing the phone is not enough
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(row["credential_id"]))
            for row in existing
        ],
    )
    session["reg_challenge"] = bytes_to_base64url(options.challenge)
    return options_to_json(options), 200, {"Content-Type": "application/json"}

@app.route('/passkey/register/complete', methods=['POST'])
@login_required
def passkey_register_complete():
    challenge_b64 = session.pop("reg_challenge", None)
    if not challenge_b64:
        return {"error": "No registration in progress."}, 400

    try:
        verification = verify_registration_response(
            credential=request.get_json(),
            expected_challenge=base64url_to_bytes(challenge_b64),
            expected_rp_id=get_rp_id(),
            expected_origin=get_rp_origin(),
            require_user_verification=True,
        )
    except Exception:
        return {"error": "Passkey registration failed."}, 400

    conn = get_db_connection()
    ensure_passkeys_table(conn)
    conn.execute(
        "INSERT OR REPLACE INTO passkeys (credential_id, user_id, public_key, sign_count) VALUES (?, ?, ?, ?)",
        (
            bytes_to_base64url(verification.credential_id),
            session["user_id"],
            verification.credential_public_key,
            verification.sign_count,
        ),
    )
    conn.commit()
    conn.close()
    return {"ok": True}

@app.route('/passkey/login/begin', methods=['POST'])
def passkey_login_begin():
    options = generate_authentication_options(
        rp_id=get_rp_id(),
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    session["auth_challenge"] = bytes_to_base64url(options.challenge)
    return options_to_json(options), 200, {"Content-Type": "application/json"}

@app.route('/passkey/login/complete', methods=['POST'])
def passkey_login_complete():
    challenge_b64 = session.pop("auth_challenge", None)
    if not challenge_b64:
        return {"error": "No sign-in in progress."}, 400

    credential = request.get_json()
    if not credential or "id" not in credential:
        return {"error": "Malformed passkey response."}, 400

    conn = get_db_connection()
    ensure_passkeys_table(conn)
    row = conn.execute(
        "SELECT * FROM passkeys WHERE credential_id = ?", (credential["id"],)
    ).fetchone()
    if row is None:
        conn.close()
        return {"error": "Unknown passkey."}, 400

    try:
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(challenge_b64),
            expected_rp_id=get_rp_id(),
            expected_origin=get_rp_origin(),
            credential_public_key=row["public_key"],
            credential_current_sign_count=row["sign_count"],
            require_user_verification=True,
        )
    except Exception:
        conn.close()
        return {"error": "Passkey sign-in failed."}, 400

    conn.execute(
        "UPDATE passkeys SET sign_count = ? WHERE credential_id = ?",
        (verification.new_sign_count, credential["id"]),
    )
    conn.commit()
    conn.close()

    session.clear()
    session["user_id"] = row["user_id"]
    return {"ok": True}

@app.route('/')
@login_required
def index():
    """The Homepage: Shows date, time, and weekly spending."""
    conn = get_db_connection()
    
    now = datetime.now()
    current_date = now.strftime("%Y-%m-%d")
    current_time = now.strftime("%I:%M %p")
    
    monday = now - timedelta(days=now.weekday())
    sunday = monday + timedelta(days= 6)
    
    monday_str = monday.strftime("%Y-%m-%d")
    sunday_str = sunday.strftime("%Y-%m-%d")
    
    monday_str_display = monday.strftime("%m/%d")
    sunday_str_display = sunday.strftime("%m/%d")

    user_total = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) as total FROM spending WHERE date BETWEEN ? AND ? AND user_id = ?",
        (monday_str, sunday_str, session["user_id"]),
    ).fetchone()
    weekly_spent = f"{user_total['total']:.2f}"

    family_total = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) as total FROM spending WHERE date BETWEEN ? AND ?",
        (monday_str, sunday_str),
    ).fetchone()
    family_spent = f"{family_total['total']:.2f}"

    user = conn.execute(
        "SELECT username FROM users WHERE user_id = ?", (session["user_id"],)
    ).fetchone()
    username = user["username"] if user else ""

    conn.close()

    return render_template(
        'index.html',
        date=current_date, time=current_time,
        spent=weekly_spent, family_spent=family_spent, username=username,
        wkbegin=monday_str_display, wkend=sunday_str_display,
    )

@app.route('/add', methods=('GET', 'POST'))
@login_required
def add_transaction():
    conn = get_db_connection()

    if request.method == 'POST':
        print(dict(request.form), flush=True)
        trans_type = request.form.get('type')
        amount = request.form.get('amount')
        date_val = request.form.get('date')
        card_id = request.form.get('card_id')

        # Validate base inputs
        if amount is None or date_val is None or card_id is None:
            conn.close()
            return "Missing required fields", 400
        
        amount = float(amount)
        famount = float(f"{amount:.2f}")

        if trans_type == 'spending':
            category_id = request.form.get('category_id')
            if not category_id:
                conn.close()
                return "Error: No category selected for spending.", 400

            conn.execute(
                'INSERT INTO spending (category_id, card_id, user_id, amount, date) VALUES (?, ?, ?, ?, ?)',
                (category_id, card_id, session["user_id"], famount, date_val)
            )

        elif trans_type == 'bill':
            bill_id = request.form.get('bill_id')

            # 💥 This prevents the silent fail
            if not bill_id:
                conn.close()
                return "Error: No bill selected.", 400

            conn.execute(
                'INSERT INTO bills (bill_id, card_id, user_id, amount, date) VALUES (?, ?, ?, ?, ?)',
                (bill_id, card_id, session["user_id"], famount, date_val)
            )

        conn.commit()
        conn.close()
        return redirect(url_for('index'))

    # GET request — load form dropdown data (cards/categories are the user's own)
    data = load_lookup_data(conn)
    conn.close()

    return render_template('add.html', **data)

@app.route("/lookup/<kind>/add", methods=["POST"])
@login_required
def add_lookup(kind):
    """Add a card, spending category, or bill type from the Add Transaction page."""
    config = LOOKUP_TABLES.get(kind)
    if not config:
        return redirect(url_for("add_transaction", error="Unknown list type."))

    name = (request.form.get("name") or "").strip()
    if not name:
        return redirect(url_for("add_transaction", error=f"Please enter a {config['label']} name."))

    conn = get_db_connection()
    try:
        if config["scoped"]:
            conn.execute(
                f"INSERT INTO {config['table']} (name, user_id) VALUES (?, ?)",
                (name, session["user_id"]),
            )
        else:
            conn.execute(f"INSERT INTO {config['table']} (name) VALUES (?)", (name,))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return redirect(url_for("add_transaction", error=f"That {config['label']} already exists."))

    conn.close()
    return redirect(url_for("add_transaction"))


@app.route("/lookup/<kind>/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_lookup(kind, item_id):
    """Delete a card, spending category, or bill type if it is not used by transactions."""
    config = LOOKUP_TABLES.get(kind)
    if not config:
        return redirect(url_for("add_transaction", error="Unknown list type."))

    conn = get_db_connection()
    for table, column in config["usage_checks"]:
        used_count = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {column} = ?", (item_id,)
        ).fetchone()[0]
        if used_count:
            conn.close()
            return redirect(
                url_for(
                    "add_transaction",
                    error=f"You cannot delete that {config['label']} because it is used by existing transactions.",
                )
            )

    if config["scoped"]:
        conn.execute(
            f"DELETE FROM {config['table']} WHERE {config['id_column']} = ? AND user_id = ?",
            (item_id, session["user_id"]),
        )
    else:
        conn.execute(
            f"DELETE FROM {config['table']} WHERE {config['id_column']} = ?", (item_id,)
        )
    conn.commit()
    conn.close()
    return redirect(url_for("add_transaction"))


VALID_RANGES = (7, 14, 30)

@app.route('/analytics')
@login_required
def analytics():
    conn = get_db_connection()

    card_id = request.args.get('card_id')

    # Range filter: 7 / 14 / 30 trailing days, ending today. Defaults to 7.
    try:
        range_days = int(request.args.get('range', 7))
    except ValueError:
        range_days = 7
    if range_days not in VALID_RANGES:
        range_days = 7

    now = datetime.now()
    begin = now - timedelta(days=range_days - 1)
    begin_str = begin.strftime("%Y-%m-%d")
    end_str = now.strftime("%Y-%m-%d")

    cards = conn.execute(
        'SELECT * FROM card_info WHERE user_id = ? ORDER BY name', (session["user_id"],)
    ).fetchall()

    # ---- Recent spending (only your own transactions are listed) ----
    spending_where = ["s.user_id = ?"]
    spending_params = [session["user_id"]]
    if card_id:
        spending_where.append("s.card_id = ?")
        spending_params.append(card_id)
    spending_where_sql = "WHERE " + " AND ".join(spending_where)

    spending_query = f"""
        SELECT s.id, s.date, s.amount,
               c.name AS category,
               card.name AS card
        FROM spending s
        JOIN category_info c ON s.category_id = c.category_id
        JOIN card_info card ON s.card_id = card.card_id
        {spending_where_sql}
        ORDER BY s.date DESC
        LIMIT 20
    """
    recent_spending = conn.execute(spending_query, spending_params).fetchall()

    # ---- Spending totals for the selected range: yours and the family's ----
    s_where = ["date BETWEEN ? AND ?"]
    s_params = [begin_str, end_str]
    if card_id:
        s_where.append("card_id = ?")
        s_params.append(card_id)
    s_where_sql = "WHERE " + " AND ".join(s_where)

    s_family_total = conn.execute(
        f"SELECT COALESCE(SUM(amount), 0) FROM spending {s_where_sql}", s_params
    ).fetchone()[0]
    s_card_total = conn.execute(
        f"SELECT COALESCE(SUM(amount), 0) FROM spending {s_where_sql} AND user_id = ?",
        s_params + [session["user_id"]],
    ).fetchone()[0]

    # ---- Recent bills (only your own transactions are listed) ----
    bill_where = ["b.user_id = ?"]
    bill_params = [session["user_id"]]
    if card_id:
        bill_where.append("b.card_id = ?")
        bill_params.append(card_id)
    bill_where_sql = "WHERE " + " AND ".join(bill_where)

    bills_query = f"""
        SELECT b.id, b.date, b.amount,
               bi.name AS bill_name,
               card.name AS card
        FROM bills b
        JOIN bill_info bi ON b.bill_id = bi.bill_id
        JOIN card_info card ON b.card_id = card.card_id
        {bill_where_sql}
        ORDER BY b.date DESC
        LIMIT 10
    """
    recent_bills = conn.execute(bills_query, bill_params).fetchall()

    # ---- Bill totals for the selected range: yours and the family's ----
    b_where = ["date BETWEEN ? AND ?"]
    b_params = [begin_str, end_str]
    if card_id:
        b_where.append("card_id = ?")
        b_params.append(card_id)
    b_where_sql = "WHERE " + " AND ".join(b_where)

    b_family_total = conn.execute(
        f"SELECT COALESCE(SUM(amount), 0) FROM bills {b_where_sql}", b_params
    ).fetchone()[0]
    b_card_total = conn.execute(
        f"SELECT COALESCE(SUM(amount), 0) FROM bills {b_where_sql} AND user_id = ?",
        b_params + [session["user_id"]],
    ).fetchone()[0]

    conn.close()

    return render_template(
        'analytics.html',
        spending=recent_spending,
        bills=recent_bills,
        btotal=b_card_total,
        stotal=s_card_total,
        btotal_family=b_family_total,
        stotal_family=s_family_total,
        cards=cards,
        selected_range=range_days
    )


@app.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete_transaction(id):
    """Delete a spending transaction (only your own)."""
    conn = get_db_connection()
    conn.execute("DELETE FROM spending WHERE id = ? AND user_id = ?", (id, session["user_id"]))
    conn.commit()
    conn.close()
    return redirect(url_for('analytics'))

@app.route('/delete_bill/<int:id>', methods=['POST'])
@login_required
def delete_bill(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM bills WHERE id = ? AND user_id = ?", (id, session["user_id"]))
    conn.commit()
    conn.close()
    return redirect(url_for('analytics'))

@app.cli.command("create-user")
def create_user():
    """Create (or update) the login user. Prompts for username and password."""
    import click
    username = click.prompt("Username").strip()
    password = click.prompt("Password", hide_input=True, confirmation_prompt=True)

    if len(password) < 8:
        print("Password must be at least 8 characters.")
        return

    conn = get_db_connection()
    # Safe to run against an existing database — only creates the table the first time.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    """)
    conn.execute(
        """
        INSERT INTO users (username, password_hash) VALUES (?, ?)
        ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash
        """,
        (username, generate_password_hash(password)),
    )
    conn.commit()
    conn.close()

    # Adopt any pre-existing unowned transactions (first-created user gets them).
    migrate_family_columns()
    print(f"User '{username}' is ready to log in.")

@app.cli.command("init-db")
def init_db():
    """Initialize the database using schema.sql"""
    db_path = os.path.join(app.instance_path, "spending.db")
    conn = sqlite3.connect(db_path)
    
    with app.open_resource("schema.sql") as f:
        conn.executescript(f.read().decode("utf8"))
        
    conn.commit()
    conn.close()
    print("Database initialized.")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)