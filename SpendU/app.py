import os
from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__, instance_relative_config=True)

def get_db_connection():
    """Helper function to connect to the database easily."""
    db_path = os.path.join(app.instance_path, 'spending.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

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


@app.route('/analytics')
def analytics():
    conn = get_db_connection()

    # Recent spending
    spending_query = """
        SELECT s.id, s.date, s.amount,
               c.name AS category,
               card.name AS card
        FROM spending s
        JOIN category_info c ON s.category_id = c.category_id
        JOIN card_info card ON s.card_id = card.card_id
        ORDER BY s.date DESC
        LIMIT 10
    """
    recent_spending = conn.execute(spending_query).fetchall()

    # Recent bills
    bills_query = """
        SELECT b.id, b.date, b.amount,
               bi.name AS bill_name,
               card.name AS card
        FROM bills b
        JOIN bill_info bi ON b.bill_id = bi.bill_id
        JOIN card_info card ON b.card_id = card.card_id
        ORDER BY b.date DESC
        LIMIT 8
    """
    recent_bills = conn.execute(bills_query).fetchall()
    
    # Apple card total
    now = datetime.now()
    
    begin = now - timedelta(days= 6)
    end = now + timedelta(days= 6)
    
    begin_str = begin.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")
    
    apple_total_query = """
        SELECT COALESCE(SUM(amount), 0)
        FROM bills 
        WHERE card_id=1
        AND date BETWEEN ? AND ?
    """
    result = conn.execute(apple_total_query, (begin_str, end_str)).fetchone()
    apple_total = result[0]

    conn.close()

    return render_template(
        'analytics.html',
        spending=recent_spending,
        bills=recent_bills,
        total=apple_total
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
    app.run(debug=True)