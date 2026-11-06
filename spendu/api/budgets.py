"""Monthly budgets.

- Personal budgets track only your own spending.
- Family budgets track everyone's spending. Because each person has their
  own category list, a family budget matches categories by NAME — e.g. a
  family "Groceries" budget counts everyone's "Groceries" category.
- category_name NULL means "all spending". Bills are tracked separately on
  the Bills page and don't count toward budgets.
"""
import calendar
import sqlite3

from flask import Blueprint, request

from ..auth import login_required, today, uid
from ..db import get_db, money, to_dicts
from ..errors import ApiError, body, clean_text, to_amount
from ..timeutil import month_bounds, parse_month

bp = Blueprint("budgets", __name__, url_prefix="/api")

WARN_AT = 0.8  # show a warning once 80% of a budget is used


def spent_for(conn, budget, start, end):
    sql = """SELECT COALESCE(SUM(s.amount), 0) FROM spending s
             JOIN category_info c ON c.category_id = s.category_id
             WHERE s.date BETWEEN ? AND ?"""
    params = [start, end]
    if not budget["is_family"]:
        sql += " AND s.user_id = ?"
        params.append(budget["user_id"])
    if budget["category_name"]:
        sql += " AND lower(c.name) = lower(?)"
        params.append(budget["category_name"])
    return money(conn.execute(sql, params).fetchone()[0])


def budget_report(conn, year, month):
    start, end = month_bounds(year, month)
    rows = to_dicts(conn.execute(
        """SELECT b.*, u.username AS owner FROM budgets b LEFT JOIN users u ON u.user_id = b.user_id
           WHERE b.is_family = 1 OR b.user_id = ?
           ORDER BY b.is_family, b.category_name IS NOT NULL, b.category_name""", (uid(),)).fetchall())

    now = today()
    days = calendar.monthrange(year, month)[1]
    if (now.year, now.month) == (year, month):
        month_progress = now.day / days
    else:
        month_progress = 1.0 if (year, month) < (now.year, now.month) else 0.0

    for b in rows:
        b["spent"] = spent_for(conn, b, start, end)
        b["remaining"] = money(b["amount"] - b["spent"])
        b["pct"] = round(b["spent"] / b["amount"], 3) if b["amount"] else 0
        if b["pct"] >= 1:
            b["status"] = "over"
        elif b["pct"] >= WARN_AT:
            b["status"] = "warning"
        elif b["pct"] > month_progress + 0.1:
            b["status"] = "ahead"  # spending faster than the month is passing
        else:
            b["status"] = "ok"
        b["can_edit"] = bool(b["is_family"]) or b["user_id"] == uid()
    return {"month": f"{year:04d}-{month:02d}", "month_progress": round(month_progress, 3),
            "personal": [b for b in rows if not b["is_family"]],
            "family": [b for b in rows if b["is_family"]]}


@bp.get("/budgets")
@login_required
def list_budgets():
    ym = parse_month(request.args.get("month")) or (today().year, today().month)
    return budget_report(get_db(), *ym)


def _editable(conn, budget_id):
    row = conn.execute("SELECT * FROM budgets WHERE budget_id = ? AND (is_family = 1 OR user_id = ?)",
                       (budget_id, uid())).fetchone()
    if row is None:
        raise ApiError("That budget was not found.", 404)
    return dict(row)


def _check_unique(conn, is_family, category_name, ignore_id=None):
    sql = "SELECT budget_id FROM budgets WHERE is_family = ? AND IFNULL(lower(category_name), '') = IFNULL(lower(?), '')"
    params = [is_family, category_name]
    if not is_family:
        sql += " AND user_id = ?"
        params.append(uid())
    if ignore_id:
        sql += " AND budget_id != ?"
        params.append(ignore_id)
    if conn.execute(sql, params).fetchone():
        raise ApiError("There's already a budget for that.", 409)


@bp.post("/budgets")
@login_required
def create_budget():
    data = body()
    conn = get_db()
    is_family = 1 if data.get("is_family") else 0
    category_name = clean_text(data.get("category_name"), 50)
    amount = to_amount(data.get("amount"))
    _check_unique(conn, is_family, category_name)
    try:
        conn.execute("INSERT INTO budgets (user_id, is_family, category_name, amount) VALUES (?, ?, ?, ?)",
                     (uid(), is_family, category_name, amount))
        conn.commit()
    except sqlite3.IntegrityError:
        raise ApiError("Couldn't save that budget.")
    return budget_report(conn, today().year, today().month), 201


@bp.patch("/budgets/<int:budget_id>")
@login_required
def update_budget(budget_id):
    data = body()
    conn = get_db()
    current = _editable(conn, budget_id)
    amount = to_amount(data.get("amount")) if "amount" in data else current["amount"]
    category_name = clean_text(data.get("category_name"), 50) if "category_name" in data else current["category_name"]
    _check_unique(conn, current["is_family"], category_name, ignore_id=budget_id)
    conn.execute("UPDATE budgets SET amount = ?, category_name = ? WHERE budget_id = ?",
                 (amount, category_name, budget_id))
    conn.commit()
    return budget_report(conn, today().year, today().month)


@bp.delete("/budgets/<int:budget_id>")
@login_required
def delete_budget(budget_id):
    conn = get_db()
    _editable(conn, budget_id)
    conn.execute("DELETE FROM budgets WHERE budget_id = ?", (budget_id,))
    conn.commit()
    return budget_report(conn, today().year, today().month)


@bp.get("/budgets/family-categories")
@login_required
def family_categories():
    """Category names used by anyone — choices for a family budget."""
    rows = get_db().execute(
        "SELECT DISTINCT name FROM category_info WHERE archived = 0 ORDER BY lower(name)").fetchall()
    return {"names": [r["name"] for r in rows]}
