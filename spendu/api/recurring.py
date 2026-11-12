"""Recurring spending (subscriptions like Netflix or Spotify).

These never add spending on their own. When one's date arrives it shows as
"pending" on the dashboard; you Confirm it (optionally changing the amount
or date if the price changed) or Skip it. Either way it moves on to the
next date.
"""
from datetime import datetime, timedelta, timezone

from flask import Blueprint

from ..auth import login_required, today, uid
from ..db import get_db, money, to_dicts
from ..errors import ApiError, body, clean_text, to_amount, to_int
from ..timeutil import advance, parse_date
from .lookups import check_card, check_category

bp = Blueprint("recurring", __name__, url_prefix="/api")

FREQUENCIES = ("weekly", "monthly", "yearly")
MONTHLY_FACTOR = {"weekly": 52 / 12, "monthly": 1, "yearly": 1 / 12}
PERIOD_DAYS = {"weekly": 7, "monthly": 30, "yearly": 365}

LIST_SQL = """
    SELECT r.*, c.name AS category, c.color AS category_color, c.icon AS category_icon,
           card.name AS card,
           (SELECT MAX(s.date) FROM spending s WHERE s.recurring_id = r.recurring_id) AS last_charge
    FROM recurring r
    LEFT JOIN category_info c ON c.category_id = r.category_id
    LEFT JOIN card_info card ON card.card_id = r.card_id
    WHERE r.user_id = ?
"""


def list_items(conn):
    rows = to_dicts(conn.execute(LIST_SQL + " ORDER BY r.active DESC, r.next_date", (uid(),)).fetchall())
    now = str(today())
    for r in rows:
        r["pending"] = bool(r["active"]) and r["next_date"] <= now
    return rows


def pending_items(conn):
    return [r for r in list_items(conn) if r["pending"]]


def _own(conn, recurring_id):
    row = conn.execute("SELECT * FROM recurring WHERE recurring_id = ? AND user_id = ?",
                       (recurring_id, uid())).fetchone()
    if row is None:
        raise ApiError("That subscription was not found.", 404)
    return dict(row)


def read_input(conn, data, partial=False):
    v = {}
    if not partial or "name" in data:
        v["name"] = clean_text(data.get("name"), 80)
        if not v["name"]:
            raise ApiError("Please enter a name.")
    if not partial or "amount" in data:
        v["amount"] = to_amount(data.get("amount"))
    if not partial or "category_id" in data:
        v["category_id"] = check_category(conn, to_int(data.get("category_id"), "category"))["category_id"]
    if not partial or "card_id" in data:
        v["card_id"] = check_card(conn, to_int(data.get("card_id"), "card"))["card_id"]
    if not partial or "frequency" in data:
        v["frequency"] = data.get("frequency") or "monthly"
        if v["frequency"] not in FREQUENCIES:
            raise ApiError("Frequency must be weekly, monthly or yearly.")
    if not partial or "next_date" in data:
        d = parse_date(data.get("next_date"))
        if d is None:
            raise ApiError("Pick the next charge date.")
        v["next_date"] = str(d)
        v["anchor_day"] = d.day
    if not partial or "notes" in data:
        v["notes"] = clean_text(data.get("notes"), 300)
    if "active" in data:
        v["active"] = 1 if data.get("active") else 0
    return v


def summary(items):
    active = [r for r in items if r["active"]]
    monthly = sum(r["amount"] * MONTHLY_FACTOR[r["frequency"]] for r in active)
    return {"monthly_cost": money(monthly), "yearly_cost": money(monthly * 12), "count": len(active)}


@bp.get("/recurring")
@login_required
def list_recurring():
    items = list_items(get_db())
    return {"items": items, "summary": summary(items)}


@bp.post("/recurring")
@login_required
def create_recurring():
    """Add a subscription. With "log_charge": true (from the Add transaction
    screen), next_date is the charge just made: it's logged as spending and
    the subscription moves on to the following date."""
    conn = get_db()
    data = body()
    v = read_input(conn, data)
    v["user_id"] = uid()
    cur = conn.execute(f"INSERT INTO recurring ({', '.join(v)}) VALUES ({', '.join('?' * len(v))})",
                       tuple(v.values()))
    if data.get("log_charge"):
        item = _own(conn, cur.lastrowid)
        _log_charge(conn, item, item["amount"], parse_date(item["next_date"]), item["card_id"],
                    clean_text(data.get("charge_notes"), 500))
        _move_to_next(conn, item)
    conn.commit()
    items = list_items(conn)
    return {"items": items, "summary": summary(items)}, 201


@bp.patch("/recurring/<int:recurring_id>")
@login_required
def update_recurring(recurring_id):
    conn = get_db()
    _own(conn, recurring_id)
    v = read_input(conn, body(), partial=True)
    if v:
        sets = ", ".join(f"{c} = ?" for c in v)
        conn.execute(f"UPDATE recurring SET {sets} WHERE recurring_id = ?", (*v.values(), recurring_id))
        conn.commit()
    items = list_items(conn)
    return {"items": items, "summary": summary(items)}


@bp.delete("/recurring/<int:recurring_id>")
@login_required
def delete_recurring(recurring_id):
    conn = get_db()
    _own(conn, recurring_id)
    # Spending already confirmed from it stays; just unlink it.
    conn.execute("UPDATE spending SET recurring_id = NULL WHERE recurring_id = ?", (recurring_id,))
    conn.execute("DELETE FROM recurring WHERE recurring_id = ?", (recurring_id,))
    conn.commit()
    items = list_items(conn)
    return {"items": items, "summary": summary(items)}


def _move_to_next(conn, item):
    nxt = advance(parse_date(item["next_date"]), item["frequency"], item["anchor_day"])
    conn.execute("UPDATE recurring SET next_date = ? WHERE recurring_id = ?", (str(nxt), item["recurring_id"]))
    return nxt


def _log_charge(conn, item, amount, charge_date, card_id, notes=None):
    """Add one charge of this subscription to spending."""
    conn.execute(
        """INSERT INTO spending (category_id, card_id, user_id, amount, date, merchant, notes, recurring_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (item["category_id"], card_id, uid(), amount, str(charge_date), item["name"], notes,
         item["recurring_id"], datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )


def counts_as_next(item, charge_date):
    """Is a charge on this date the upcoming one (so the next date should move
    on)? Yes if it's on/after the due date, or up to half a period early.
    An older charge (e.g. typing in last month's statement) leaves it alone."""
    due = parse_date(item["next_date"])
    return charge_date >= due - timedelta(days=PERIOD_DAYS[item["frequency"]] // 2)


@bp.post("/recurring/<int:recurring_id>/confirm")
@login_required
def confirm(recurring_id):
    """Log this charge as spending, then move on to the next date."""
    conn = get_db()
    item = _own(conn, recurring_id)
    data = body()
    amount = to_amount(data["amount"]) if data.get("amount") not in (None, "") else item["amount"]
    charge_date = parse_date(data.get("date")) or parse_date(item["next_date"])
    if data.get("update_amount"):
        conn.execute("UPDATE recurring SET amount = ? WHERE recurring_id = ?", (amount, recurring_id))
    _log_charge(conn, item, amount, charge_date, item["card_id"])
    _move_to_next(conn, item)
    conn.commit()
    return {"ok": True, "pending": pending_items(conn)}


@bp.post("/recurring/<int:recurring_id>/charge")
@login_required
def log_charge(recurring_id):
    """A charge entered from the Add transaction screen (e.g. typed in from a
    card statement). Unlike confirm, it can be any date: the next date only
    moves on if this is the upcoming charge (see counts_as_next)."""
    conn = get_db()
    item = _own(conn, recurring_id)
    data = body()
    amount = to_amount(data.get("amount"))
    charge_date = parse_date(data.get("date"))
    if charge_date is None:
        raise ApiError("Pick the date of the charge.")
    card_id = check_card(conn, to_int(data.get("card_id"), "card"))["card_id"]
    updates = {}
    if data.get("update_amount"):
        updates["amount"] = amount
    if card_id != item["card_id"]:
        updates["card_id"] = card_id  # paid with a different card: that's the card from now on
    if updates:
        conn.execute(f"UPDATE recurring SET {', '.join(f'{c} = ?' for c in updates)} WHERE recurring_id = ?",
                     (*updates.values(), recurring_id))
    _log_charge(conn, item, amount, charge_date, card_id, clean_text(data.get("notes"), 500))
    moved = counts_as_next(item, charge_date)
    next_date = _move_to_next(conn, item) if moved else parse_date(item["next_date"])
    conn.commit()
    return {"ok": True, "moved": moved, "next_date": str(next_date), "pending": pending_items(conn)}


@bp.post("/recurring/<int:recurring_id>/skip")
@login_required
def skip(recurring_id):
    conn = get_db()
    _move_to_next(conn, _own(conn, recurring_id))
    conn.commit()
    return {"ok": True, "pending": pending_items(conn)}
