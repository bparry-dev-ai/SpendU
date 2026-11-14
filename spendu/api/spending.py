"""Spending entries, the combined transaction history, and CSV export.

Refunds/credits are stored as NEGATIVE amounts in the spending table, so a
plain SUM(amount) always gives "net spending". A refund can be marked as a
bill refund (bill_credit = 1, e.g. a card payment towards bill charges):
those count against Bills instead, so spending totals read from the
`spending_net` view, which leaves them out.
"""
import csv
import io
from datetime import datetime, timezone

from flask import Blueprint, Response, request

from ..auth import login_required, today, uid
from ..db import get_db, money, to_dicts
from ..errors import ApiError, body, clean_text, to_amount, to_int
from ..timeutil import parse_date
from .lookups import check_card, check_category

bp = Blueprint("spending", __name__, url_prefix="/api")

# Spending and bill payments in one list. Bill payments show the bill's name
# in the "merchant" column and the pseudo-category "Bills".
UNIFIED_SQL = """
    SELECT 'spending' AS kind, s.id, s.date, s.amount, s.merchant, s.notes,
           s.card_id, card.name AS card, card.color AS card_color,
           s.category_id, c.name AS category, c.color AS category_color, c.icon AS category_icon,
           NULL AS bill_id, NULL AS bill_month, s.recurring_id, s.bill_credit
    FROM spending s
    LEFT JOIN category_info c ON c.category_id = s.category_id
    LEFT JOIN card_info card ON card.card_id = s.card_id
    WHERE s.user_id = :uid
    UNION ALL
    SELECT 'bill' AS kind, b.id, b.date, b.amount, bi.name AS merchant, b.notes,
           b.card_id, card.name, card.color,
           NULL, 'Bills', NULL, NULL,
           b.bill_id, b.bill_month, NULL, 0
    FROM bills b
    LEFT JOIN bill_info bi ON bi.bill_id = b.bill_id
    LEFT JOIN card_info card ON card.card_id = b.card_id
    WHERE b.user_id = :uid
"""


def read_spending_input(conn, data, partial=False):
    """Validate a spending form. Returns a dict of column -> value."""
    values = {}
    if not partial or "amount" in data or "is_refund" in data:
        amount = to_amount(data.get("amount"))
        values["amount"] = -amount if data.get("is_refund") else amount
        # Only a refund can be a bill refund.
        values["bill_credit"] = 1 if data.get("is_refund") and data.get("bill_credit") else 0
    if not partial or "date" in data:
        d = parse_date(data.get("date"))
        if d is None:
            raise ApiError("Please pick a valid date.")
        values["date"] = str(d)
    if not partial or "card_id" in data:
        values["card_id"] = check_card(conn, to_int(data.get("card_id"), "card"))["card_id"]
    if not partial or "category_id" in data:
        values["category_id"] = check_category(conn, to_int(data.get("category_id"), "category"))["category_id"]
    if not partial or "merchant" in data:
        values["merchant"] = clean_text(data.get("merchant"), 80)
    if not partial or "notes" in data:
        values["notes"] = clean_text(data.get("notes"), 500)
    return values


def get_spending_row(conn, entry_id):
    row = conn.execute(f"SELECT * FROM ({UNIFIED_SQL}) WHERE kind = 'spending' AND id = :id",
                       {"uid": uid(), "id": entry_id}).fetchone()
    if row is None:
        raise ApiError("That transaction was not found.", 404)
    return dict(row)


@bp.post("/spending")
@login_required
def create_spending():
    conn = get_db()
    v = read_spending_input(conn, body())
    cur = conn.execute(
        """INSERT INTO spending (category_id, card_id, user_id, amount, date, merchant, notes, bill_credit, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (v["category_id"], v["card_id"], uid(), v["amount"], v["date"], v["merchant"], v["notes"], v["bill_credit"],
         datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )
    conn.commit()
    return get_spending_row(conn, cur.lastrowid), 201


@bp.get("/spending/<int:entry_id>")
@login_required
def read_spending(entry_id):
    return get_spending_row(get_db(), entry_id)


@bp.patch("/spending/<int:entry_id>")
@login_required
def update_spending(entry_id):
    conn = get_db()
    get_spending_row(conn, entry_id)  # 404 if not yours
    v = read_spending_input(conn, body(), partial=True)
    if v:
        sets = ", ".join(f"{col} = ?" for col in v)
        conn.execute(f"UPDATE spending SET {sets} WHERE id = ? AND user_id = ?", (*v.values(), entry_id, uid()))
        conn.commit()
    return get_spending_row(conn, entry_id)


@bp.delete("/spending/<int:entry_id>")
@login_required
def delete_spending(entry_id):
    conn = get_db()
    conn.execute("DELETE FROM spending WHERE id = ? AND user_id = ?", (entry_id, uid()))
    conn.commit()
    return {"ok": True}


def _history_filters(args):
    """Build the WHERE clause for /transactions and /export.csv from the URL."""
    where, params = [], {"uid": uid()}
    if args.get("start"):
        where.append("date >= :start")
        params["start"] = args["start"]
    if args.get("end"):
        where.append("date <= :end")
        params["end"] = args["end"]
    if args.get("card_id"):
        where.append("card_id = :card_id")
        params["card_id"] = args.get("card_id")
    if args.get("category_id"):
        where.append("category_id = :category_id")
        params["category_id"] = args.get("category_id")
    kind = args.get("kind", "all")
    if kind == "spending":
        where.append("kind = 'spending' AND amount >= 0")
    elif kind == "refunds":
        where.append("kind = 'spending' AND amount < 0")
    elif kind == "bills":
        where.append("(kind = 'bill' OR bill_credit = 1)")
    if args.get("q"):
        where.append("(merchant LIKE :q OR notes LIKE :q OR category LIKE :q OR card LIKE :q)")
        params["q"] = f"%{args['q'].strip()}%"
    sql = f"SELECT * FROM ({UNIFIED_SQL})"
    if where:
        sql += " WHERE " + " AND ".join(where)
    return sql, params


@bp.get("/transactions")
@login_required
def transactions():
    conn = get_db()
    sql, params = _history_filters(request.args)
    page = max(1, request.args.get("page", 1, type=int))
    page_size = min(100, max(10, request.args.get("page_size", 50, type=int)))

    summary = conn.execute(
        f"""SELECT COUNT(*) AS count, COALESCE(SUM(amount), 0) AS total,
                   COALESCE(SUM(CASE WHEN kind = 'spending' AND amount >= 0 THEN amount END), 0) AS spending,
                   COALESCE(SUM(CASE WHEN kind = 'spending' AND amount < 0 AND bill_credit = 0 THEN -amount END), 0) AS refunds,
                   COALESCE(SUM(CASE WHEN kind = 'bill' THEN amount END), 0) AS bills,
                   COALESCE(SUM(CASE WHEN bill_credit = 1 THEN -amount END), 0) AS bill_refunds
            FROM ({sql})""", params).fetchone()
    rows = conn.execute(f"{sql} ORDER BY date DESC, kind, id DESC LIMIT :limit OFFSET :offset",
                        {**params, "limit": page_size, "offset": (page - 1) * page_size}).fetchall()
    return {
        "items": to_dicts(rows),
        "count": summary["count"],
        "total": money(summary["total"]),
        "breakdown": {k: money(summary[k]) for k in ("spending", "refunds", "bills", "bill_refunds")},
        "page": page,
        "pages": max(1, -(-summary["count"] // page_size)),
    }


@bp.get("/merchants")
@login_required
def merchants():
    """Autocomplete: your past merchants, with the category you used last time."""
    q = (request.args.get("q") or "").strip()
    rows = get_db().execute(
        """SELECT merchant, category_id, date FROM spending
           WHERE user_id = ? AND merchant IS NOT NULL AND merchant LIKE ?
           ORDER BY date DESC, id DESC LIMIT 400""",
        (uid(), f"%{q}%"),
    ).fetchall()
    seen = {}
    for row in rows:
        key = row["merchant"].lower()
        if key not in seen:
            seen[key] = {"merchant": row["merchant"], "category_id": row["category_id"], "uses": 0}
        seen[key]["uses"] += 1
    ranked = sorted(seen.values(), key=lambda m: (not m["merchant"].lower().startswith(q.lower()), -m["uses"]))
    return {"merchants": ranked[:8]}


def suggest_category(conn, merchant):
    """The category last used for this merchant (case-insensitive), or None."""
    if not merchant:
        return None
    row = conn.execute(
        """SELECT category_id FROM spending WHERE user_id = ? AND lower(merchant) = lower(?)
           ORDER BY date DESC, id DESC LIMIT 1""",
        (uid(), merchant.strip()),
    ).fetchone()
    return row["category_id"] if row else None


@bp.get("/export.csv")
@login_required
def export_csv():
    sql, params = _history_filters(request.args)
    rows = get_db().execute(f"{sql} ORDER BY date, id", params).fetchall()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Date", "Type", "Merchant / Bill", "Category", "Card", "Amount", "Notes"])
    for r in rows:
        if r["kind"] == "bill":
            kind = "Bill"
        elif r["amount"] < 0:
            kind = "Bill refund" if r["bill_credit"] else "Refund"
        else:
            kind = "Spending"
        writer.writerow([r["date"], kind, r["merchant"] or "", r["category"] or "", r["card"] or "",
                         f"{r['amount']:.2f}", r["notes"] or ""])
    filename = f"spendu-export-{today()}.csv"
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


