import os
from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__, instance_relative_config=True)

def get_db_connection():
    """Helper function to connect to the database easily."""
    db_path = '/app/spending.db'
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
    },
    "category": {
        "table": "category_info",
        "id_column": "category_id",
        "usage_checks": [
            ("spending", "category_id"),
        ],
        "label": "category",
    },
    "bill": {
        "table": "bill_info",
        "id_column": "bill_id",
        "usage_checks": [
            ("bills", "bill_id"),
        ],
    },
}

def load_lookup_data(conn):
    """Load dropdown data for the Add Transaction Page"""
    return {
        "cards": conn.execute("SELECT * FROM card_info ORDER BY name").fetchall(),
        "bills": conn.execute("SELECT * FROM bill_info ORDER BY name").fetchall(),
        "categories": conn.execute("SELECT * FROM category_info ORDER BY name").fetchall(),
    }

def render_add_form(conn, error=None, status_code=200):
    """Render add.html with all dropdown lists and an optional error message."""
    data = load_lookup_data(conn)
    return render_template("add.html", error=error, **data), status_code

@app.route('/')
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

    query = """
        SELECT COALESCE(SUM(amount), 0) as total 
        FROM spending 
        WHERE date BETWEEN ? AND ?;
    """
    result = conn.execute(query, (monday_str, sunday_str)).fetchone()
    weekly_spent = (f"{result['total']:.2f}")

    conn.close()

    return render_template('index.html', date=current_date, time=current_time, spent=weekly_spent, wkbegin=monday_str_display, wkend=sunday_str_display)

@app.route('/add', methods=('GET', 'POST'))
def add_transaction():
    conn = get_db_connection()

    if request.method == 'POST':
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
                'INSERT INTO spending (category_id, card_id, amount, date) VALUES (?, ?, ?, ?)',
                (category_id, card_id, famount, date_val)
            )

        elif trans_type == 'bill':
            bill_id = request.form.get('bill_id')

            # 💥 This prevents the silent fail
            if not bill_id:
                conn.close()
                return "Error: No bill selected.", 400

            conn.execute(
                'INSERT INTO bills (bill_id, card_id, amount, date) VALUES (?, ?, ?, ?)',
                (bill_id, card_id, famount, date_val)
            )

        conn.commit()
        conn.close()
        return redirect(url_for('index'))

    # GET request — load form dropdown data
    cards = conn.execute('SELECT * FROM card_info').fetchall()
    bills = conn.execute('SELECT * FROM bill_info').fetchall()
    categories = conn.execute('SELECT * FROM category_info').fetchall()
    conn.close()

    return render_template('add.html', cards=cards, bills=bills, categories=categories)

@app.route("/lookup/<kind>/add", methods=["POST"])
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
        conn.execute(f"INSERT INTO {config['table']} (name) VALUES (?)", (name,))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return redirect(url_for("add_transaction", error=f"That {config['label']} already exists."))

    conn.close()
    return redirect(url_for("add_transaction"))


@app.route("/lookup/<kind>/<int:item_id>/delete", methods=["POST"])
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

    conn.execute(
        f"DELETE FROM {config['table']} WHERE {config['id_column']} = ?", (item_id,)
    )
    conn.commit()
    conn.close()
    return redirect(url_for("add_transaction"))


VALID_RANGES = (7, 14, 30)

@app.route('/analytics')
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

    cards = conn.execute('SELECT * FROM card_info').fetchall()

    # ---- Recent spending (table is unfiltered by range, just by card, like before) ----
    spending_where = []
    spending_params = []
    if card_id:
        spending_where.append("s.card_id = ?")
        spending_params.append(card_id)
    spending_where_sql = ("WHERE " + " AND ".join(spending_where)) if spending_where else ""

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

    # ---- Spending total for the selected range ----
    s_where = ["date BETWEEN ? AND ?"]
    s_params = [begin_str, end_str]
    if card_id:
        s_where.append("card_id = ?")
        s_params.append(card_id)
    s_where_sql = "WHERE " + " AND ".join(s_where)

    s_card_total_query = f"SELECT COALESCE(SUM(amount), 0) FROM spending {s_where_sql}"
    s_card_total = conn.execute(s_card_total_query, s_params).fetchone()[0]

    # ---- Recent bills (table unfiltered by range, just by card) ----
    bill_where = []
    bill_params = []
    if card_id:
        bill_where.append("b.card_id = ?")
        bill_params.append(card_id)
    bill_where_sql = ("WHERE " + " AND ".join(bill_where)) if bill_where else ""

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

    # ---- Bill total for the selected range ----
    b_where = ["date BETWEEN ? AND ?"]
    b_params = [begin_str, end_str]
    if card_id:
        b_where.append("card_id = ?")
        b_params.append(card_id)
    b_where_sql = "WHERE " + " AND ".join(b_where)

    b_card_total_query = f"SELECT COALESCE(SUM(amount), 0) FROM bills {b_where_sql}"
    b_card_total = conn.execute(b_card_total_query, b_params).fetchone()[0]

    conn.close()

    return render_template(
        'analytics.html',
        spending=recent_spending,
        bills=recent_bills,
        btotal=b_card_total,
        stotal=s_card_total,
        cards=cards,
        selected_range=range_days
    )


@app.route('/delete/<int:id>', methods=['POST'])
def delete_transaction(id):
    """Delete a spending transaction."""
    conn = get_db_connection()
    conn.execute("DELETE FROM spending WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('analytics'))

@app.route('/delete_bill/<int:id>', methods=['POST'])
def delete_bill(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM bills WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('analytics'))

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