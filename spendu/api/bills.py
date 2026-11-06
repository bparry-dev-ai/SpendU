"""Recurring bills and the monthly checklist.

Two tables (both existed in v1, v2 adds columns):
    bill_info  — the bill itself: name, usual amount, due day, default card.
                 Shared family-wide, like v1.2's bill types.
    bills      — each payment: amount, date, card, who paid, and bill_month
                 (the month's bill it pays, e.g. '2026-11').

A bill is "paid" for a month when a payment with that bill_month exists.
"""
from datetime import timedelta

from flask import Blueprint, request

from ..auth import login_required, today, uid
from ..db import get_db, money, to_dicts
from ..errors import ApiError, body, clean_text, to_amount, to_int
from ..timeutil import day_in_month, month_str, parse_date, parse_month
from .lookups import check_card

bp = Blueprint("bills", __name__, url_prefix="/api")

DUE_SOON_DAYS = 5


def get_bill(conn, bill_id):
    row = conn.execute("SELECT * FROM bill_info WHERE bill_id = ?", (bill_id,)).fetchone()
    if row is None:
        raise ApiError("That bill was not found.", 404)
    return dict(row)


def read_bill_input(conn, data, partial=False):
    values = {}
    if not partial or "name" in data:
        name = clean_text(data.get("name"), 60)
        if not name:
            raise ApiError("Please enter a bill name.")
        values["name"] = name
    if not partial or "amount" in data:
        values["amount"] = to_amount(data["amount"]) if data.get("amount") not in (None, "") else None
    if not partial or "due_day" in data:
        due_day = to_int(data.get("due_day"), "due day", required=False)
        if due_day is not None and not 1 <= due_day <= 31:
            raise ApiError("Due day must be between 1 and 31.")
        values["due_day"] = due_day
    if not partial or "frequency" in data:
        frequency = data.get("frequency") or "monthly"
        if frequency not in ("monthly", "yearly"):
            raise ApiError("Frequency must be monthly or yearly.")
        values["frequency"] = frequency
    if not partial or "due_month" in data:
        due_month = to_int(data.get("due_month"), "due month", required=False)
        if due_month is not None and not 1 <= due_month <= 12:
            raise ApiError("Due month must be 1–12.")
        values["due_month"] = due_month
    if not partial or "card_id" in data:
        card_id = to_int(data.get("card_id"), "card", required=False)
        values["card_id"] = check_card(conn, card_id)["card_id"] if card_id else None
    if not partial or "autopay" in data:
        values["autopay"] = 1 if data.get("autopay") else 0
    if not partial or "notes" in data:
        values["notes"] = clean_text(data.get("notes"), 300)
    if "active" in data:
        values["active"] = 1 if data.get("active") else 0
    if values.get("frequency") == "yearly" and not values.get("due_month") and not partial:
        raise ApiError("Pick which month a yearly bill is due.")
    return values


def _bill_list(conn):
    rows = conn.execute(
        """SELECT bi.*, card.name AS card_name, card.user_id AS card_owner,
                  (SELECT MAX(date) FROM bills b WHERE b.bill_id = bi.bill_id) AS last_paid,
                  (SELECT amount FROM bills b WHERE b.bill_id = bi.bill_id ORDER BY date DESC, id DESC LIMIT 1) AS last_amount
           FROM bill_info bi
           LEFT JOIN card_info card ON card.card_id = bi.card_id
           ORDER BY bi.active DESC, bi.name"""
    ).fetchall()
    bills = []
    for row in to_dicts(rows):
        # The default card is someone's own card — only show it to its owner.
        if row["card_owner"] != uid():
            row["card_id"], row["card_name"] = None, None
        row.pop("card_owner")
        row["scheduled"] = row["due_day"] is not None
        bills.append(row)
    return bills


@bp.get("/bills")
@login_required
def list_bills():
    return {"bills": _bill_list(get_db())}


@bp.post("/bills")
@login_required
def create_bill():
    conn = get_db()
    v = read_bill_input(conn, body())
    if conn.execute("SELECT 1 FROM bill_info WHERE lower(name) = lower(?)", (v["name"],)).fetchone():
        raise ApiError(f"A bill called {v['name']} already exists.", 409)
    v["start_month"] = month_str(today())
    cols = ", ".join(v)
    cur = conn.execute(f"INSERT INTO bill_info ({cols}) VALUES ({', '.join('?' * len(v))})", tuple(v.values()))
    conn.commit()
    return {"bill_id": cur.lastrowid, "bills": _bill_list(conn)}, 201


@bp.patch("/bills/<int:bill_id>")
@login_required
def update_bill(bill_id):
    conn = get_db()
    current = get_bill(conn, bill_id)
    v = read_bill_input(conn, body(), partial=True)
    if "name" in v and conn.execute("SELECT 1 FROM bill_info WHERE lower(name) = lower(?) AND bill_id != ?",
                                    (v["name"], bill_id)).fetchone():
        raise ApiError(f"A bill called {v['name']} already exists.", 409)
    # A v1 bill getting its first due day starts its checklist this month,
    # so it doesn't show every past month as "overdue".
    if v.get("due_day") and current["due_day"] is None and not current["start_month"]:
        v["start_month"] = month_str(today())
    if v:
        sets = ", ".join(f"{col} = ?" for col in v)
        conn.execute(f"UPDATE bill_info SET {sets} WHERE bill_id = ?", (*v.values(), bill_id))
        conn.commit()
    return {"bills": _bill_list(conn)}


@bp.delete("/bills/<int:bill_id>")
@login_required
def delete_bill(bill_id):
    conn = get_db()
    get_bill(conn, bill_id)
    has_payments = conn.execute("SELECT COUNT(*) FROM bills WHERE bill_id = ?", (bill_id,)).fetchone()[0]
    if has_payments:
        # Keep history: stop tracking instead of deleting.
        conn.execute("UPDATE bill_info SET active = 0 WHERE bill_id = ?", (bill_id,))
        message = "This bill has payment history, so it was archived instead of deleted."
    else:
        conn.execute("DELETE FROM bill_info WHERE bill_id = ?", (bill_id,))
        message = "Bill deleted."
    conn.commit()
    return {"message": message, "bills": _bill_list(conn)}


def bill_due_in_month(bill, year, month):
    """The bill's due date in that month, or None if it isn't due that month."""
    if not bill["active"] or bill["due_day"] is None:
        return None
    if bill["start_month"] and f"{year:04d}-{month:02d}" < bill["start_month"]:
        return None
    if bill["frequency"] == "yearly" and bill["due_month"] != month:
        return None
    return day_in_month(year, month, bill["due_day"])


def build_checklist(conn, year, month):
    """Every bill due in the month, with paid / overdue / due soon status."""
    month_key = f"{year:04d}-{month:02d}"
    now = today()
    payments = to_dicts(conn.execute(
        """SELECT b.id, b.bill_id, b.amount, b.date, b.card_id, b.notes, b.user_id,
                  u.username, card.name AS card
           FROM bills b
           LEFT JOIN users u ON u.user_id = b.user_id
           LEFT JOIN card_info card ON card.card_id = b.card_id
           WHERE b.bill_month = ? ORDER BY b.date""", (month_key,)).fetchall())
    for p in payments:
        p["is_mine"] = p["user_id"] == uid()
        if not p["is_mine"]:
            p["card"] = None  # other people's cards stay private

    bills = _bill_list(conn)
    items, scheduled_ids = [], set()
    for bill in bills:
        due = bill_due_in_month(bill, year, month)
        if due is None:
            continue
        scheduled_ids.add(bill["bill_id"])
        paid = [p for p in payments if p["bill_id"] == bill["bill_id"]]
        if paid:
            status = "paid"
        elif due < now:
            status = "overdue"
        elif due <= now + timedelta(days=DUE_SOON_DAYS):
            status = "due_soon"
        else:
            status = "upcoming"
        items.append({
            **bill,
            "due_date": str(due),
            "status": status,
            "payments": paid,
            "paid_total": money(sum(p["amount"] for p in paid)),
            "expected": bill["amount"] if bill["amount"] is not None else bill["last_amount"],
        })
    items.sort(key=lambda i: (i["status"] == "paid", i["due_date"]))

    other = [p for p in payments if p["bill_id"] not in scheduled_ids]
    names = {b["bill_id"]: b["name"] for b in bills}
    for p in other:
        p["bill_name"] = names.get(p["bill_id"], "Bill")

    expected_total = sum((i["expected"] or 0) for i in items)
    paid_total = sum(i["paid_total"] for i in items) + sum(p["amount"] for p in other)
    unpaid_expected = sum((i["expected"] or 0) for i in items if i["status"] != "paid")
    return {
        "month": month_key,
        "items": items,
        "other_payments": other,
        "needs_setup": [b for b in bills if b["active"] and not b["scheduled"]],
        "summary": {
            "count": len(items),
            "paid": sum(1 for i in items if i["status"] == "paid"),
            "overdue": sum(1 for i in items if i["status"] == "overdue"),
            "due_soon": sum(1 for i in items if i["status"] == "due_soon"),
            "expected_total": money(expected_total),
            "paid_total": money(paid_total),
            "remaining": money(unpaid_expected),
        },
    }


@bp.get("/bills/checklist")
@login_required
def checklist():
    ym = parse_month(request.args.get("month")) or (today().year, today().month)
    return build_checklist(get_db(), *ym)


@bp.get("/bills/<int:bill_id>/payments")
@login_required
def bill_payments(bill_id):
    conn = get_db()
    bill = get_bill(conn, bill_id)
    rows = to_dicts(conn.execute(
        """SELECT b.id, b.amount, b.date, b.bill_month, b.notes, b.user_id, u.username, card.name AS card
           FROM bills b LEFT JOIN users u ON u.user_id = b.user_id
           LEFT JOIN card_info card ON card.card_id = b.card_id
           WHERE b.bill_id = ? ORDER BY b.date DESC LIMIT 60""", (bill_id,)).fetchall())
    for r in rows:
        r["is_mine"] = r["user_id"] == uid()
        if not r["is_mine"]:
            r["card"] = None
    return {"bill": bill, "payments": rows}


def read_payment_input(conn, data, partial=False):
    values = {}
    if not partial or "bill_id" in data:
        values["bill_id"] = get_bill(conn, to_int(data.get("bill_id"), "bill"))["bill_id"]
    if not partial or "amount" in data:
        values["amount"] = to_amount(data.get("amount"))
    if not partial or "date" in data:
        d = parse_date(data.get("date"))
        if d is None:
            raise ApiError("Please pick a valid date.")
        values["date"] = str(d)
    if not partial or "card_id" in data:
        values["card_id"] = check_card(conn, to_int(data.get("card_id"), "card"))["card_id"]
    if not partial or "bill_month" in data:
        month = data.get("bill_month") or (values.get("date") or "")[:7]
        if not parse_month(month):
            raise ApiError("Pick which month's bill this pays.")
        values["bill_month"] = month
    if not partial or "notes" in data:
        values["notes"] = clean_text(data.get("notes"), 300)
    return values


def _own_payment(conn, payment_id):
    row = conn.execute("SELECT * FROM bills WHERE id = ? AND user_id = ?", (payment_id, uid())).fetchone()
    if row is None:
        raise ApiError("That payment was not found.", 404)
    return dict(row)


@bp.post("/bill-payments")
@login_required
def create_payment():
    conn = get_db()
    v = read_payment_input(conn, body())
    cur = conn.execute(
        "INSERT INTO bills (bill_id, card_id, user_id, amount, date, bill_month, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (v["bill_id"], v["card_id"], uid(), v["amount"], v["date"], v["bill_month"], v["notes"]),
    )
    conn.commit()
    return {"id": cur.lastrowid, **_own_payment(conn, cur.lastrowid)}, 201


@bp.patch("/bill-payments/<int:payment_id>")
@login_required
def update_payment(payment_id):
    conn = get_db()
    _own_payment(conn, payment_id)
    v = read_payment_input(conn, body(), partial=True)
    if v:
        sets = ", ".join(f"{col} = ?" for col in v)
        conn.execute(f"UPDATE bills SET {sets} WHERE id = ? AND user_id = ?", (*v.values(), payment_id, uid()))
        conn.commit()
    return _own_payment(conn, payment_id)


@bp.delete("/bill-payments/<int:payment_id>")
@login_required
def delete_payment(payment_id):
    conn = get_db()
    conn.execute("DELETE FROM bills WHERE id = ? AND user_id = ?", (payment_id, uid()))
    conn.commit()
    return {"ok": True}
