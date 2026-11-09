"""Budget Planner — monthly income split into Needs, Wants and Savings.

Two kinds of plan (table `plans`):
    personal  — owner_user_id = you; compared against YOUR spending
    household — owner_user_id NULL; shared, compared against everyone's

Each plan has lines (table `plan_lines`) of four kinds:
    category      — e.g. Groceries. Actual = spending in categories with that
                    NAME (each person has their own list). Also works as the
                    category's monthly limit (warnings on Home).
    bill          — added automatically for bills. Actual = payments for it.
    subscription  — added automatically (personal plans). Actual = confirmed charges.
    custom        — e.g. "Emergency fund". Planned only — the app can't see
                    money moving between accounts.

Bill/subscription lines with amount NULL follow the bill's usual amount
(yearly bills ÷ 12). Removing one of them only hides it, so it isn't
re-added automatically next time.

Charges from a subscription that has its own line are left out of category
lines, so nothing is counted twice. Every number is recalculated on each
request, so adding a transaction or paying a bill shows up immediately.
"""
import math

from flask import Blueprint, request

from ..auth import login_required, today, uid
from ..db import get_db, money, to_dicts
from ..errors import ApiError, body, clean_text, to_amount
from ..migrations import guess_group
from ..timeutil import month_bounds, parse_month, shift_month
from .recurring import MONTHLY_FACTOR

bp = Blueprint("planner", __name__, url_prefix="/api/planner")

GROUPS = ("needs", "wants", "savings")
GUIDE = {"needs": 0.50, "wants": 0.30, "savings": 0.20}  # the 50/30/20 rule of thumb
HISTORY_CHOICES = (1, 3, 6, 12)
WARN_AT = 0.8


# ---------------------------------------------------------------------------
# Loading plans and lines
# ---------------------------------------------------------------------------
def read_scope(value):
    scope = value or "personal"
    if scope not in ("personal", "household"):
        raise ApiError("Scope must be personal or household.")
    return scope


def get_plan(conn, scope, create=True):
    owner = None if scope == "household" else uid()
    row = conn.execute("SELECT * FROM plans WHERE owner_user_id IS ?", (owner,)).fetchone()
    if row is None and create:
        conn.execute("INSERT INTO plans (owner_user_id) VALUES (?)", (owner,))
        conn.commit()
        row = conn.execute("SELECT * FROM plans WHERE owner_user_id IS ?", (owner,)).fetchone()
    return dict(row) if row else None


def own_line(conn, line_id):
    """A line from your personal plan or the household plan, else 404."""
    row = conn.execute(
        """SELECT l.*, p.owner_user_id FROM plan_lines l JOIN plans p ON p.plan_id = l.plan_id
           WHERE l.line_id = ? AND (p.owner_user_id IS NULL OR p.owner_user_id = ?)""",
        (line_id, uid())).fetchone()
    if row is None:
        raise ApiError("That budget line was not found.", 404)
    return dict(row)


def _my_bill_ids(conn):
    """Bills you usually pay: set to one of your cards, or you paid it last."""
    rows = conn.execute(
        """SELECT bi.bill_id FROM bill_info bi
           LEFT JOIN card_info card ON card.card_id = bi.card_id
           WHERE bi.active = 1 AND (
               card.user_id = :uid OR
               (SELECT b.user_id FROM bills b WHERE b.bill_id = bi.bill_id
                ORDER BY b.date DESC, b.id DESC LIMIT 1) = :uid)""",
        {"uid": uid()}).fetchall()
    return {r[0] for r in rows}


def sync_auto_lines(conn, plan, scope):
    """Add lines for bills/subscriptions that don't have one yet."""
    lines = conn.execute("SELECT kind, bill_id, recurring_id FROM plan_lines WHERE plan_id = ?",
                         (plan["plan_id"],)).fetchall()
    have_bills = {l["bill_id"] for l in lines if l["kind"] == "bill"}
    have_subs = {l["recurring_id"] for l in lines if l["kind"] == "subscription"}

    if scope == "household":
        bill_ids = {r[0] for r in conn.execute("SELECT bill_id FROM bill_info WHERE active = 1").fetchall()}
    else:
        bill_ids = _my_bill_ids(conn)
    added = False
    for bill_id in sorted(bill_ids - have_bills):
        conn.execute("INSERT INTO plan_lines (plan_id, group_name, kind, bill_id) VALUES (?, 'needs', 'bill', ?)",
                     (plan["plan_id"], bill_id))
        added = True
    if scope == "personal":
        sub_ids = {r[0] for r in conn.execute(
            "SELECT recurring_id FROM recurring WHERE user_id = ? AND active = 1", (uid(),)).fetchall()}
        for recurring_id in sorted(sub_ids - have_subs):
            conn.execute(
                "INSERT INTO plan_lines (plan_id, group_name, kind, recurring_id) VALUES (?, 'wants', 'subscription', ?)",
                (plan["plan_id"], recurring_id))
            added = True
    if added:
        conn.commit()


def load_lines(conn, plan):
    """All lines with their source details. Lines whose bill/subscription
    was archived or deleted are skipped (they come back if it's restored)."""
    rows = to_dicts(conn.execute(
        """SELECT l.*, bi.name AS bill_name, bi.amount AS bill_amount, bi.frequency AS bill_frequency,
                  bi.active AS bill_active, bi.due_day,
                  (SELECT amount FROM bills b WHERE b.bill_id = l.bill_id ORDER BY date DESC, id DESC LIMIT 1) AS bill_last,
                  r.name AS sub_name, r.amount AS sub_amount, r.frequency AS sub_frequency, r.active AS sub_active
           FROM plan_lines l
           LEFT JOIN bill_info bi ON bi.bill_id = l.bill_id
           LEFT JOIN recurring r ON r.recurring_id = l.recurring_id
           WHERE l.plan_id = ?
           ORDER BY l.sort_order, l.line_id""", (plan["plan_id"],)).fetchall())
    lines = []
    for l in rows:
        if l["kind"] == "bill":
            if not l["bill_active"]:
                continue
            usual = l["bill_amount"] if l["bill_amount"] is not None else (l["bill_last"] or 0)
            l["source_amount"] = money(usual / 12 if l["bill_frequency"] == "yearly" else usual)
            l["name"] = l["bill_name"]
        elif l["kind"] == "subscription":
            if l["sub_active"] is None or not l["sub_active"]:
                continue
            l["source_amount"] = money(l["sub_amount"] * MONTHLY_FACTOR.get(l["sub_frequency"], 1))
            l["name"] = l["sub_name"]
        elif l["kind"] == "category":
            l["source_amount"] = None
            l["name"] = l["category_name"]
        else:
            l["source_amount"] = None
            l["name"] = l["label"] or "Untitled"
        l["follows_source"] = l["amount"] is None and l["source_amount"] is not None
        l["planned"] = money(l["amount"] if l["amount"] is not None else (l["source_amount"] or 0))
        lines.append(l)
    return lines


# ---------------------------------------------------------------------------
# Actual spending per line
# ---------------------------------------------------------------------------
def line_actual(conn, scope, line, start, end, sub_ids):
    who = "" if scope == "household" else " AND {t}.user_id = :uid"
    params = {"uid": uid(), "start": start, "end": end}
    if line["kind"] == "category":
        sql = ("SELECT COALESCE(SUM(s.amount), 0) FROM spending s "
               "JOIN category_info c ON c.category_id = s.category_id "
               "WHERE lower(c.name) = lower(:name) AND s.date BETWEEN :start AND :end" + who.format(t="s"))
        if sub_ids:
            sql += f" AND (s.recurring_id IS NULL OR s.recurring_id NOT IN ({','.join(str(i) for i in sub_ids)}))"
        params["name"] = line["category_name"]
    elif line["kind"] == "bill":
        # Bill payments count toward the month they pay for.
        sql = ("SELECT COALESCE(SUM(b.amount), 0) FROM bills b WHERE b.bill_id = :id "
               "AND b.bill_month BETWEEN :start_m AND :end_m" + who.format(t="b"))
        params.update(id=line["bill_id"], start_m=start[:7], end_m=end[:7])
    elif line["kind"] == "subscription":
        sql = ("SELECT COALESCE(SUM(s.amount), 0) FROM spending s WHERE s.recurring_id = :id "
               "AND s.date BETWEEN :start AND :end" + who.format(t="s"))
        params["id"] = line["recurring_id"]
    else:
        return None  # custom lines aren't tracked
    return money(conn.execute(sql, params).fetchone()[0])


def history_months(conn, scope, year, month, wanted):
    """How many complete months before (year, month) to average over —
    fewer if your history doesn't go back that far."""
    who = "" if scope == "household" else " WHERE user_id = :uid"
    first = conn.execute(
        f"SELECT MIN(d) FROM (SELECT MIN(date) AS d FROM spending{who} UNION ALL SELECT MIN(date) FROM bills{who})",
        {"uid": uid()}).fetchone()[0]
    if not first:
        return 0
    fy, fm = int(first[:4]), int(first[5:7])
    available = (year * 12 + month) - (fy * 12 + fm)
    return max(0, min(wanted, available))


def status_for(planned, spent, month_progress):
    if not planned:
        return "unplanned" if spent > 0 else "ok"
    if spent > planned + 0.005:
        return "over"
    if spent >= planned * WARN_AT:
        return "warning"
    if spent / planned > month_progress + 0.1:
        return "ahead"
    return "ok"


def history_flag(planned, average):
    if average is None:
        return None
    if average > planned * 1.1 and average - planned >= 5:
        return "over"
    if average < planned * 0.8 and planned - average >= 5:
        return "under"
    return "on_track"


def round_up(x, step=5):
    return float(math.ceil(x / step) * step) if x > 0 else 0.0


def month_progress_for(year, month):
    now = today()
    days = int(month_bounds(year, month)[1][-2:])
    if (now.year, now.month) == (year, month):
        return now.day / days
    return 1.0 if (year, month) < (now.year, now.month) else 0.0


# ---------------------------------------------------------------------------
# The full report
# ---------------------------------------------------------------------------
def build_report(conn, scope, year, month, months_wanted):
    plan = get_plan(conn, scope)
    sync_auto_lines(conn, plan, scope)
    lines = load_lines(conn, plan)
    visible = [l for l in lines if not l["hidden"]]

    start, end = month_bounds(year, month)
    n = history_months(conn, scope, year, month, months_wanted)
    if n:
        hy, hm = shift_month(year, month, -n)
        h_start = month_bounds(hy, hm)[0]
        h_end = month_bounds(*shift_month(year, month, -1))[1]
    progress = month_progress_for(year, month)
    sub_ids = [l["recurring_id"] for l in visible if l["kind"] == "subscription"]

    for l in visible:
        l["spent"] = line_actual(conn, scope, l, start, end, sub_ids)
        total = line_actual(conn, scope, l, h_start, h_end, sub_ids) if n else None
        l["average"] = money(total / n) if total is not None and n else None
        tracked = l["spent"] is not None
        l["tracked"] = tracked
        if not tracked:
            l["status"] = l["history"] = None
        elif l["kind"] in ("bill", "subscription"):
            # Paid-or-not matters for these, not "pace"; and a yearly bill or a
            # brand-new subscription averaging $0 isn't "underspending".
            over = l["planned"] and l["spent"] > l["planned"] * 1.05 + 0.5
            l["status"] = "over" if over else "paid" if l["spent"] > 0 else "due"
            flag = history_flag(l["planned"], l["average"])
            yearly = l["kind"] == "bill" and l["bill_frequency"] == "yearly"
            l["history"] = "over" if flag == "over" and not yearly else ("on_track" if l["average"] is not None else None)
        else:
            l["status"] = status_for(l["planned"], l["spent"], progress)
            l["history"] = history_flag(l["planned"], l["average"])
        l["remaining"] = money(l["planned"] - l["spent"]) if tracked else None
        l["pct"] = round(l["spent"] / l["planned"], 3) if tracked and l["planned"] else 0

    income = plan["income"] or 0
    planned_total = money(sum(l["planned"] for l in visible))
    groups = {}
    for g in GROUPS:
        g_lines = [l for l in visible if l["group_name"] == g]
        planned = money(sum(l["planned"] for l in g_lines))
        groups[g] = {
            "planned": planned,
            "spent": money(sum(l["spent"] or 0 for l in g_lines)),
            "share": round(planned / income, 3) if income else None,
            "guide": GUIDE[g],
        }

    # Spending in categories that aren't in the plan.
    planned_names = {(l["category_name"] or "").lower() for l in visible if l["kind"] == "category"}
    unplanned = _unplanned_categories(conn, scope, planned_names, sub_ids, start, end,
                                      (h_start, h_end, n) if n else None)

    # Overall cap (from an old "All spending" budget, or set here).
    who = "" if scope == "household" else " AND user_id = :uid"
    spending_this_month = money(conn.execute(
        f"SELECT COALESCE(SUM(amount), 0) FROM spending WHERE date BETWEEN :s AND :e{who}",
        {"s": start, "e": end, "uid": uid()}).fetchone()[0])

    report = {
        "scope": scope,
        "month": f"{year:04d}-{month:02d}",
        "month_progress": round(progress, 3),
        "history_months": n,
        "history_wanted": months_wanted,
        "plan": {"plan_id": plan["plan_id"], "income": plan["income"], "overall_cap": plan["overall_cap"]},
        "summary": {
            "income": money(income),
            "planned": planned_total,
            "left_to_assign": money(income - planned_total),
            "spent_this_month": spending_this_month,
            "tracked_spent": money(sum(l["spent"] or 0 for l in visible)),
        },
        "groups": groups,
        "lines": visible,
        "hidden": [{"line_id": l["line_id"], "name": l["name"], "kind": l["kind"]} for l in lines if l["hidden"]],
        "unplanned": unplanned,
        "category_choices": _category_choices(conn, scope, planned_names),
    }
    report["suggestions"] = suggestions(report)
    return report


def _unplanned_categories(conn, scope, planned_names, sub_ids, start, end, history):
    who = "" if scope == "household" else " AND s.user_id = :uid"
    skip_subs = (f" AND (s.recurring_id IS NULL OR s.recurring_id NOT IN ({','.join(str(i) for i in sub_ids)}))"
                 if sub_ids else "")
    sql = ("SELECT c.name, MAX(c.color) AS color, COALESCE(SUM(s.amount), 0) AS total FROM spending s "
           "JOIN category_info c ON c.category_id = s.category_id "
           "WHERE s.date BETWEEN :start AND :end" + who + skip_subs + " GROUP BY lower(c.name)")
    this_month = {r["name"].lower(): dict(r) for r in conn.execute(sql, {"start": start, "end": end, "uid": uid()})}
    averages = {}
    if history:
        h_start, h_end, n = history
        for r in conn.execute(sql, {"start": h_start, "end": h_end, "uid": uid()}):
            averages[r["name"].lower()] = (dict(r), r["total"] / n)
    result = []
    for key in set(this_month) | set(averages):
        if key in planned_names:
            continue
        info = this_month.get(key) or averages[key][0]
        spent = money(this_month[key]["total"]) if key in this_month else 0
        avg = money(averages[key][1]) if key in averages else None
        if max(spent, avg or 0) >= 5:
            result.append({"name": info["name"], "color": info["color"], "spent": spent, "average": avg})
    return sorted(result, key=lambda r: -(r["average"] or r["spent"]))


def _category_choices(conn, scope, planned_names):
    if scope == "household":
        rows = conn.execute("SELECT DISTINCT name FROM category_info WHERE archived = 0 ORDER BY lower(name)")
    else:
        rows = conn.execute("SELECT name FROM category_info WHERE user_id = ? AND archived = 0 ORDER BY lower(name)",
                            (uid(),))
    return [r[0] for r in rows if r[0].lower() not in planned_names]


def suggestions(report):
    """Plain-English tips, most useful first. Each may carry a one-tap action."""
    tips = []
    s = report["summary"]
    income = s["income"]
    n = report["history_months"]
    span = f"last {n} month{'s' if n != 1 else ''}"

    if not income:
        tips.append({"tone": "info", "message": "Add your monthly income to see how much is left to assign."})
    elif s["left_to_assign"] < -0.005:
        tips.append({"tone": "bad", "message": f"You've planned ${-s['left_to_assign']:,.2f} more than your income. "
                                               "Trim a Want or two to balance it."})
    elif s["left_to_assign"] >= 1:
        tips.append({"tone": "info", "message": f"${s['left_to_assign']:,.2f} of income has no job yet. "
                                                "Consider giving it to Savings.",
                     "action": {"kind": "add_savings", "amount": s["left_to_assign"]}})

    for l in report["lines"]:
        if l["history"] == "over" and l["kind"] in ("category", "bill"):
            diff = l["average"] - l["planned"]
            tips.append({"tone": "warn", "line_id": l["line_id"],
                         "message": f"You average ${l['average']:,.2f} on {l['name']} ({span}) but planned "
                                    f"${l['planned']:,.2f}. Raise the plan, or aim to cut about ${diff:,.0f}/month.",
                         "action": {"kind": "set_amount", "line_id": l["line_id"], "amount": round_up(l["average"])}})
        elif l["history"] == "under" and l["kind"] == "category":
            diff = l["planned"] - l["average"]
            tips.append({"tone": "ok", "line_id": l["line_id"],
                         "message": f"You planned ${l['planned']:,.2f} for {l['name']} but average "
                                    f"${l['average']:,.2f}. Lowering it frees up about ${diff:,.0f}/month.",
                         "action": {"kind": "set_amount", "line_id": l["line_id"], "amount": round_up(l["average"])}})

    for u in report["unplanned"][:3]:
        amount = u["average"] if u["average"] else u["spent"]
        when = f"about ${u['average']:,.2f}/month" if u["average"] else f"${u['spent']:,.2f} this month"
        tips.append({"tone": "warn", "message": f"You spend {when} on {u['name']}, which isn't in your plan.",
                     "action": {"kind": "add_category", "category_name": u["name"], "amount": round_up(amount),
                                "group": guess_group(u["name"])}})

    if income:
        names = {"needs": "Needs", "wants": "Wants", "savings": "Savings"}
        for g, info in report["groups"].items():
            if g != "savings" and info["share"] is not None and info["share"] > info["guide"] + 0.1:
                tips.append({"tone": "info", "message": f"{names[g]} take {info['share'] * 100:.0f}% of income "
                                                        f"(the 50/30/20 guide suggests {info['guide'] * 100:.0f}%)."})
        sav = report["groups"]["savings"]
        if sav["share"] is not None and sav["share"] < 0.1:
            tips.append({"tone": "info", "message": f"Savings are {sav['share'] * 100:.0f}% of income "
                                                    "— the guide suggests 20%."})
    return tips[:8]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@bp.get("")
@login_required
def planner():
    scope = read_scope(request.args.get("scope"))
    ym = parse_month(request.args.get("month")) or (today().year, today().month)
    months = request.args.get("months", 3, type=int)
    if months not in HISTORY_CHOICES:
        months = 3
    return build_report(get_db(), scope, ym[0], ym[1], months)


@bp.patch("")
@login_required
def update_plan():
    data = body()
    conn = get_db()
    plan = get_plan(conn, read_scope(data.get("scope")))
    for field in ("income", "overall_cap"):
        if field in data:
            value = data[field]
            value = None if value in (None, "") else to_amount(value, field, allow_zero=True)
            conn.execute(f"UPDATE plans SET {field} = ? WHERE plan_id = ?", (value, plan["plan_id"]))
    conn.commit()
    return {"ok": True}


def _read_group(value):
    group = value or "wants"
    if group not in GROUPS:
        raise ApiError("Group must be needs, wants or savings.")
    return group


@bp.post("/lines")
@login_required
def add_line():
    data = body()
    conn = get_db()
    plan = get_plan(conn, read_scope(data.get("scope")))
    kind = data.get("kind") or "category"
    group = _read_group(data.get("group"))
    amount = to_amount(data.get("amount") or 0, allow_zero=True)
    if kind == "category":
        name = clean_text(data.get("category_name"), 50)
        if not name:
            raise ApiError("Pick a category.")
        exists = conn.execute(
            "SELECT line_id, hidden FROM plan_lines WHERE plan_id = ? AND kind = 'category' AND lower(category_name) = lower(?)",
            (plan["plan_id"], name)).fetchone()
        if exists:
            raise ApiError(f"{name} is already in this plan.", 409)
        conn.execute("INSERT INTO plan_lines (plan_id, group_name, kind, category_name, amount) VALUES (?, ?, 'category', ?, ?)",
                     (plan["plan_id"], group, name, amount))
    elif kind == "custom":
        label = clean_text(data.get("label"), 50)
        if not label:
            raise ApiError("Give this budget area a name.")
        conn.execute("INSERT INTO plan_lines (plan_id, group_name, kind, label, amount) VALUES (?, ?, 'custom', ?, ?)",
                     (plan["plan_id"], group, label, amount))
    else:
        raise ApiError("Bills and subscriptions are added automatically.")
    conn.commit()
    return {"ok": True}, 201


@bp.patch("/lines/<int:line_id>")
@login_required
def update_line(line_id):
    data = body()
    conn = get_db()
    line = own_line(conn, line_id)
    updates = {}
    if "amount" in data:
        if data["amount"] in (None, "") and line["kind"] in ("bill", "subscription"):
            updates["amount"] = None  # follow the bill/subscription's usual amount again
        else:
            updates["amount"] = to_amount(data["amount"] or 0, allow_zero=True)
    if "group" in data:
        updates["group_name"] = _read_group(data["group"])
    if "label" in data and line["kind"] == "custom":
        updates["label"] = clean_text(data["label"], 50) or line["label"]
    if updates:
        sets = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(f"UPDATE plan_lines SET {sets} WHERE line_id = ?", (*updates.values(), line_id))
        conn.commit()
    return {"ok": True}


@bp.delete("/lines/<int:line_id>")
@login_required
def delete_line(line_id):
    conn = get_db()
    line = own_line(conn, line_id)
    if line["kind"] in ("bill", "subscription"):
        conn.execute("UPDATE plan_lines SET hidden = 1 WHERE line_id = ?", (line_id,))
    else:
        conn.execute("DELETE FROM plan_lines WHERE line_id = ?", (line_id,))
    conn.commit()
    return {"ok": True}


@bp.post("/lines/<int:line_id>/restore")
@login_required
def restore_line(line_id):
    conn = get_db()
    own_line(conn, line_id)
    conn.execute("UPDATE plan_lines SET hidden = 0 WHERE line_id = ?", (line_id,))
    conn.commit()
    return {"ok": True}


@bp.post("/start")
@login_required
def start_from_spending():
    """Fill an empty plan with a line for each category you've spent on,
    using your recent average (rounded up to $5)."""
    data = body()
    conn = get_db()
    scope = read_scope(data.get("scope"))
    now = today()
    report = build_report(conn, scope, now.year, now.month, 3)
    added = 0
    for u in report["unplanned"]:
        amount = round_up(u["average"] if u["average"] else u["spent"])
        conn.execute("INSERT INTO plan_lines (plan_id, group_name, kind, category_name, amount) VALUES (?, ?, 'category', ?, ?)",
                     (report["plan"]["plan_id"], guess_group(u["name"]), u["name"], amount))
        added += 1
    conn.commit()
    return {"added": added}


def limits_for_dashboard(conn):
    """Category lines from your plan and the household plan, as monthly
    limits with this month's progress — shown on Home, worst first."""
    now = today()
    out = []
    for scope in ("personal", "household"):
        if get_plan(conn, scope, create=False) is None:
            continue
        report = build_report(conn, scope, now.year, now.month, 3)
        for l in report["lines"]:
            if l["kind"] == "category" and l["planned"] > 0:
                out.append({"line_id": l["line_id"], "label": l["name"], "is_family": scope == "household",
                            "amount": l["planned"], "spent": l["spent"], "remaining": l["remaining"],
                            "pct": l["pct"], "status": l["status"]})
        cap = report["plan"]["overall_cap"]
        if cap:
            spent = report["summary"]["spent_this_month"]
            out.append({"line_id": f"cap-{scope}", "label": "All spending", "is_family": scope == "household",
                        "amount": cap, "spent": spent, "remaining": money(cap - spent),
                        "pct": round(spent / cap, 3), "status": status_for(cap, spent, report["month_progress"])})
    out.sort(key=lambda b: -b["pct"])
    return out
