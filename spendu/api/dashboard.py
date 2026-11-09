"""The home screen: everything important about this month in one request."""
from datetime import date, timedelta

from flask import Blueprint

from ..auth import login_required, today, uid
from ..db import get_db, money, to_dicts
from ..timeutil import month_bounds, shift_month
from .bills import build_checklist
from .planner import limits_for_dashboard
from .recurring import pending_items
from .spending import UNIFIED_SQL

bp = Blueprint("dashboard", __name__, url_prefix="/api")


def _sum(conn, sql, params):
    return money(conn.execute(sql, params).fetchone()[0])


def daily_cumulative(conn, start, days, user_id):
    rows = conn.execute(
        """SELECT date, SUM(amount) AS total FROM spending
           WHERE user_id = ? AND date BETWEEN ? AND date(?, ?) GROUP BY date""",
        (user_id, start, start, f"+{days - 1} days"),
    ).fetchall()
    by_day = {r["date"]: r["total"] for r in rows}
    running, out = 0.0, []
    first = date.fromisoformat(start)
    for i in range(days):
        running += by_day.get(str(first + timedelta(days=i)), 0)
        out.append(money(running))
    return out


@bp.get("/dashboard")
@login_required
def dashboard():
    conn = get_db()
    now = today()
    start, end = month_bounds(now.year, now.month)
    py, pm = shift_month(now.year, now.month, -1)
    prev_start, prev_end = month_bounds(py, pm)
    prev_same_day = min(now.day, int(prev_end[-2:]))
    prev_cutoff = f"{py:04d}-{pm:02d}-{prev_same_day:02d}"
    monday = now - timedelta(days=now.weekday())
    sunday = monday + timedelta(days=6)

    spend_sql = "SELECT COALESCE(SUM(amount), 0) FROM spending WHERE date BETWEEN ? AND ?"
    mine = spend_sql + " AND user_id = ?"
    month_spent = _sum(conn, mine, (start, end, uid()))
    last_month_to_date = _sum(conn, mine, (prev_start, prev_cutoff, uid()))
    last_month_total = _sum(conn, mine, (prev_start, prev_end, uid()))
    bills_paid = _sum(conn, "SELECT COALESCE(SUM(amount), 0) FROM bills WHERE date BETWEEN ? AND ? AND user_id = ?",
                      (start, end, uid()))

    top_categories = to_dicts(conn.execute(
        """SELECT c.name, c.color, c.icon, SUM(s.amount) AS total FROM spending s
           JOIN category_info c ON c.category_id = s.category_id
           WHERE s.user_id = ? AND s.date BETWEEN ? AND ?
           GROUP BY c.category_id HAVING total > 0 ORDER BY total DESC LIMIT 5""",
        (uid(), start, end)).fetchall())

    checklist = build_checklist(conn, now.year, now.month)
    open_bills = [i for i in checklist["items"] if i["status"] != "paid"][:4]

    limits = limits_for_dashboard(conn)

    recent = to_dicts(conn.execute(f"SELECT * FROM ({UNIFIED_SQL}) ORDER BY date DESC, id DESC LIMIT 6",
                                   {"uid": uid()}).fetchall())

    days_in_month = int(end[-2:])
    return {
        "today": str(now),
        "month": start[:7],
        "spending": {
            "month": month_spent,
            "last_month_to_date": last_month_to_date,
            "last_month_total": last_month_total,
            "week": _sum(conn, mine, (str(monday), str(sunday), uid())),
            "week_start": str(monday),
            "week_end": str(sunday),
            "bills_paid": bills_paid,
            "family_month": _sum(conn, spend_sql, (start, end)),
            "family_week": _sum(conn, spend_sql, (str(monday), str(sunday))),
        },
        "pace": {
            "this_month": daily_cumulative(conn, start, now.day, uid()),
            "last_month": daily_cumulative(conn, prev_start, int(prev_end[-2:]), uid()),
            "days_in_month": days_in_month,
        },
        "top_categories": top_categories,
        "bills": {"summary": checklist["summary"], "open": open_bills},
        "pending_recurring": pending_items(conn),
        "budgets": limits[:4],
        "recent": recent,
    }
