"""Insights: breakdowns, month-over-month trends, and the calendar.

All numbers are your own (family totals live on the dashboard and budgets).
"Spending" is net of refunds. Bill payments are included when
include_bills=1 and show up as their own "Bills" category. Refunds marked
as bill refunds (spending.bill_credit = 1) reduce Bills, not spending.
"""
from datetime import date, timedelta

from flask import Blueprint, request

from ..auth import login_required, today, uid
from ..db import get_db, money, to_dicts
from ..timeutil import month_bounds, parse_date, parse_month, shift_month
from .bills import build_checklist
from .recurring import list_items

bp = Blueprint("analytics", __name__, url_prefix="/api/analytics")

BILLS_COLOR = "#94a3b8"

# Bill payments plus bill refunds (stored negative in spending).
BILLS_NET = """SELECT card_id, amount, date, user_id FROM bills
               UNION ALL SELECT card_id, amount, date, user_id FROM spending WHERE bill_credit = 1"""


def _range():
    now = today()
    start = parse_date(request.args.get("start")) or now.replace(day=1)
    end = parse_date(request.args.get("end")) or now
    if end < start:
        start, end = end, start
    return str(start), str(end)


@bp.get("/summary")
@login_required
def summary():
    conn = get_db()
    start, end = _range()
    include_bills = request.args.get("include_bills") == "1"
    p = (uid(), start, end)

    by_category = to_dicts(conn.execute(
        """SELECT c.category_id, c.name, c.color, c.icon, SUM(s.amount) AS total, COUNT(*) AS count
           FROM spending_net s JOIN category_info c ON c.category_id = s.category_id
           WHERE s.user_id = ? AND s.date BETWEEN ? AND ?
           GROUP BY c.category_id ORDER BY total DESC""", p).fetchall())

    card_sql = """SELECT card.card_id, card.name, card.color, SUM(t.amount) AS total, COUNT(*) AS count
                  FROM ({source}) t JOIN card_info card ON card.card_id = t.card_id
                  GROUP BY card.card_id ORDER BY total DESC"""
    source = "SELECT card_id, amount FROM spending_net WHERE user_id = ? AND date BETWEEN ? AND ?"
    params = list(p)
    if include_bills:
        source += f" UNION ALL SELECT card_id, amount FROM ({BILLS_NET}) WHERE user_id = ? AND date BETWEEN ? AND ?"
        params += list(p)
    by_card = to_dicts(conn.execute(card_sql.format(source=source), params).fetchall())

    bills_total = money(conn.execute(
        f"SELECT COALESCE(SUM(amount), 0) FROM ({BILLS_NET}) WHERE user_id = ? AND date BETWEEN ? AND ?", p).fetchone()[0])
    bill_refunds_total = money(conn.execute(
        "SELECT COALESCE(SUM(-amount), 0) FROM spending WHERE bill_credit = 1 AND user_id = ? AND date BETWEEN ? AND ?",
        p).fetchone()[0])
    if include_bills and bills_total:
        count = conn.execute(f"SELECT COUNT(*) FROM ({BILLS_NET}) WHERE user_id = ? AND date BETWEEN ? AND ?", p).fetchone()[0]
        by_category.append({"category_id": None, "name": "Bills", "color": BILLS_COLOR, "icon": "🧾",
                            "total": bills_total, "count": count})
        by_category.sort(key=lambda c: -c["total"])

    daily_rows = conn.execute(
        "SELECT date, SUM(amount) AS total FROM spending_net WHERE user_id = ? AND date BETWEEN ? AND ? GROUP BY date",
        p).fetchall()
    by_day = {r["date"]: r["total"] for r in daily_rows}
    d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
    daily = [{"date": str(d0 + timedelta(days=i)), "total": money(by_day.get(str(d0 + timedelta(days=i)), 0))}
             for i in range((d1 - d0).days + 1)] if (d1 - d0).days <= 400 else []

    merchants = to_dicts(conn.execute(
        """SELECT merchant AS name, SUM(amount) AS total, COUNT(*) AS count FROM spending_net
           WHERE user_id = ? AND date BETWEEN ? AND ? AND merchant IS NOT NULL
           GROUP BY lower(merchant) HAVING total > 0 ORDER BY total DESC LIMIT 8""", p).fetchall())

    spending_total = money(conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM spending_net WHERE user_id = ? AND date BETWEEN ? AND ?", p).fetchone()[0])
    refunds_total = money(conn.execute(
        "SELECT COALESCE(SUM(-amount), 0) FROM spending_net WHERE user_id = ? AND date BETWEEN ? AND ? AND amount < 0",
        p).fetchone()[0])

    for row in by_category + by_card + merchants:
        row["total"] = money(row["total"])
    return {
        "start": start, "end": end,
        "spending_total": spending_total,
        "refunds_total": refunds_total,
        "bills_total": bills_total,
        "bill_refunds_total": bill_refunds_total,
        "total": money(spending_total + (bills_total if include_bills else 0)),
        "by_category": by_category,
        "by_card": by_card,
        "daily": daily,
        "top_merchants": merchants,
    }


@bp.get("/trends")
@login_required
def trends():
    """Month-by-month totals for the last N months (default 12)."""
    conn = get_db()
    months = min(36, max(2, request.args.get("months", 12, type=int)))
    now = today()
    keys = []
    for i in range(months - 1, -1, -1):
        y, m = shift_month(now.year, now.month, -i)
        keys.append(f"{y:04d}-{m:02d}")
    first = keys[0] + "-01"

    def per_month(sql):
        rows = conn.execute(sql, (uid(), first)).fetchall()
        return {r["month"]: r["total"] for r in rows}

    spending = per_month("SELECT substr(date,1,7) AS month, SUM(amount) AS total FROM spending_net "
                         "WHERE user_id = ? AND date >= ? GROUP BY month")
    refunds = per_month("SELECT substr(date,1,7) AS month, SUM(-amount) AS total FROM spending_net "
                        "WHERE user_id = ? AND date >= ? AND amount < 0 GROUP BY month")
    bills = per_month(f"SELECT substr(date,1,7) AS month, SUM(amount) AS total FROM ({BILLS_NET}) "
                      "WHERE user_id = ? AND date >= ? GROUP BY month")

    cat_rows = conn.execute(
        """SELECT substr(s.date,1,7) AS month, c.name, c.color, SUM(s.amount) AS total
           FROM spending_net s JOIN category_info c ON c.category_id = s.category_id
           WHERE s.user_id = ? AND s.date >= ? GROUP BY month, c.category_id""", (uid(), first)).fetchall()
    totals, colors, grid = {}, {}, {}
    for r in cat_rows:
        totals[r["name"]] = totals.get(r["name"], 0) + r["total"]
        colors[r["name"]] = r["color"]
        grid[(r["month"], r["name"])] = r["total"]
    top = [name for name, _ in sorted(totals.items(), key=lambda kv: -kv[1])[:6]]
    series = [{"name": name, "color": colors[name], "values": [money(grid.get((k, name), 0)) for k in keys]}
              for name in top]
    other = [money(sum(v for (k2, n), v in grid.items() if k2 == k and n not in top)) for k in keys]
    if any(other):
        series.append({"name": "Other", "color": "#94a3b8", "values": other})

    # This month vs last month, per category (for the comparison table).
    this_key, last_key = keys[-1], keys[-2]
    compare = []
    for name in sorted(totals, key=lambda n: -(grid.get((this_key, n), 0) + grid.get((last_key, n), 0))):
        a, b = grid.get((this_key, name), 0), grid.get((last_key, name), 0)
        if a or b:
            compare.append({"name": name, "color": colors[name], "this_month": money(a), "last_month": money(b),
                            "change": money(a - b)})

    return {
        "months": keys,
        "spending": [money(spending.get(k, 0)) for k in keys],
        "refunds": [money(refunds.get(k, 0)) for k in keys],
        "bills": [money(bills.get(k, 0)) for k in keys],
        "categories": series,
        "compare": compare,
    }


@bp.get("/calendar")
@login_required
def calendar_view():
    conn = get_db()
    ym = parse_month(request.args.get("month")) or (today().year, today().month)
    start, end = month_bounds(*ym)
    days = {}
    for r in conn.execute(
        """SELECT date, SUM(amount) AS total, COUNT(*) AS count FROM spending_net
           WHERE user_id = ? AND date BETWEEN ? AND ? GROUP BY date""", (uid(), start, end)).fetchall():
        days[r["date"]] = {"spent": money(r["total"]), "count": r["count"]}

    checklist = build_checklist(conn, *ym)
    bills = [{"bill_id": i["bill_id"], "name": i["name"], "due_date": i["due_date"], "status": i["status"],
              "amount": i["expected"]} for i in checklist["items"]]
    subs = [{"name": r["name"], "date": r["next_date"], "amount": r["amount"]}
            for r in list_items(conn) if r["active"] and start <= r["next_date"] <= end]
    return {"month": start[:7], "start": start, "end": end, "days": days, "bills": bills, "subscriptions": subs,
            "total": money(sum(d["spent"] for d in days.values()))}
