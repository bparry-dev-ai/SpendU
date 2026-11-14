"""Budget Planner — one family plan. Monthly income is split into Bills,
Needs, Wants, Personal and Savings.

There is a single shared plan (table `plans`, the row with owner_user_id
NULL). Anyone in the family can edit it, and it's compared against
everyone's spending. (Older per-person plans were merged into it by
migration 4 and are no longer used.)

Each plan has lines (table `plan_lines`) of five kinds:
    bill          — added automatically for bills (Bills section).
                    Actual = payments for it.
    category      — e.g. Groceries. Actual = everyone's spending in
                    categories with that NAME (each person has their own
                    list). Also works as the category's monthly limit.
    subscription  — added automatically. Actual = confirmed charges.
    person        — a personal spending limit for one family member
                    (Personal section). Actual = that person's spending in
                    categories that AREN'T in the plan, so nothing is
                    counted twice.
    custom        — e.g. "Emergency fund". Planned only — the app can't see
                    money moving between accounts.

Bill/subscription lines with amount NULL follow the bill's usual amount
(yearly bills ÷ 12). Removing one of them only hides it, so it isn't
re-added automatically next time.

Charges from a subscription that has its own line are left out of category
and personal lines. Refunds marked as bill refunds (spending.bill_credit)
never count as spending — the `spending_net` view leaves them out.

Suggestions can be closed. Each has a key built from the numbers behind it,
so closing one hides it until the situation changes (table
`suggestion_dismissals`, per person).
"""
import math

from flask import Blueprint, request

from ..auth import login_required, today, uid
from ..db import get_db, money, to_dicts
from ..errors import ApiError, body, clean_text, to_amount, to_int
from ..migrations import guess_group
from ..timeutil import month_bounds, parse_month, shift_month
from .recurring import MONTHLY_FACTOR

bp = Blueprint("planner", __name__, url_prefix="/api/planner")

GROUPS = ("bills", "needs", "wants", "personal", "savings")
# The 50/30/20 rule of thumb: Bills + Needs 50%, Wants + Personal 30%, Savings 20%.
GUIDE = {"bills": 0.50, "needs": 0.50, "wants": 0.30, "personal": 0.30, "savings": 0.20}
HISTORY_CHOICES = (1, 3, 6, 12)
WARN_AT = 0.8
MAX_TIPS = 8


# ---------------------------------------------------------------------------
# Loading the plan and its lines
# ---------------------------------------------------------------------------
def get_plan(conn, create=True):
    row = conn.execute("SELECT * FROM plans WHERE owner_user_id IS NULL").fetchone()
    if row is None and create:
        conn.execute("INSERT INTO plans (owner_user_id) VALUES (NULL)")
        conn.commit()
        row = conn.execute("SELECT * FROM plans WHERE owner_user_id IS NULL").fetchone()
    return dict(row) if row else None


def own_line(conn, line_id):
    """A line from the family plan, else 404."""
    row = conn.execute(
        """SELECT l.* FROM plan_lines l JOIN plans p ON p.plan_id = l.plan_id
           WHERE l.line_id = ? AND p.owner_user_id IS NULL""", (line_id,)).fetchone()
    if row is None:
        raise ApiError("That budget line was not found.", 404)
    return dict(row)


def sync_auto_lines(conn, plan):
    """Add lines for bills/subscriptions that don't have one yet."""
    lines = conn.execute("SELECT kind, bill_id, recurring_id FROM plan_lines WHERE plan_id = ?",
                         (plan["plan_id"],)).fetchall()
    have_bills = {l["bill_id"] for l in lines if l["kind"] == "bill"}
    have_subs = {l["recurring_id"] for l in lines if l["kind"] == "subscription"}

    bill_ids = {r[0] for r in conn.execute("SELECT bill_id FROM bill_info WHERE active = 1").fetchall()}
    sub_ids = {r[0] for r in conn.execute("SELECT recurring_id FROM recurring WHERE active = 1").fetchall()}
    added = False
    for bill_id in sorted(bill_ids - have_bills):
        conn.execute("INSERT INTO plan_lines (plan_id, group_name, kind, bill_id) VALUES (?, 'bills', 'bill', ?)",
                     (plan["plan_id"], bill_id))
        added = True
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
                  r.name AS sub_name, r.amount AS sub_amount, r.frequency AS sub_frequency, r.active AS sub_active,
                  u.username AS person_name
           FROM plan_lines l
           LEFT JOIN bill_info bi ON bi.bill_id = l.bill_id
           LEFT JOIN recurring r ON r.recurring_id = l.recurring_id
           LEFT JOIN users u ON u.user_id = l.person_user_id
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
        elif l["kind"] == "person":
            if l["person_name"] is None:
                continue  # that user no longer exists
            l["source_amount"] = None
            l["name"] = l["person_name"]
            l["is_me"] = l["person_user_id"] == uid()
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
def _not_in(column, ids):
    """SQL leaving out the given integer ids (NULLs are kept)."""
    if not ids:
        return ""
    return f" AND ({column} IS NULL OR {column} NOT IN ({','.join(str(int(i)) for i in ids)}))"


def _skip_categories(names, params):
    """SQL (plus params) leaving out spending in the plan's category names."""
    if not names:
        return ""
    keys = []
    for i, name in enumerate(sorted(names)):
        params[f"cat{i}"] = name
        keys.append(f":cat{i}")
    return (" AND s.category_id NOT IN (SELECT category_id FROM category_info "
            f"WHERE lower(name) IN ({','.join(keys)}))")


def line_actual(conn, line, start, end, ctx):
    params = {"start": start, "end": end}
    if line["kind"] == "category":
        sql = ("SELECT COALESCE(SUM(s.amount), 0) FROM spending_net s "
               "JOIN category_info c ON c.category_id = s.category_id "
               "WHERE lower(c.name) = lower(:name) AND s.date BETWEEN :start AND :end"
               + _not_in("s.recurring_id", ctx["sub_ids"]))
        params["name"] = line["category_name"]
    elif line["kind"] == "bill":
        # Bill payments count toward the month they pay for.
        sql = ("SELECT COALESCE(SUM(b.amount), 0) FROM bills b WHERE b.bill_id = :id "
               "AND b.bill_month BETWEEN :start_m AND :end_m")
        params.update(id=line["bill_id"], start_m=start[:7], end_m=end[:7])
    elif line["kind"] == "subscription":
        sql = ("SELECT COALESCE(SUM(s.amount), 0) FROM spending_net s WHERE s.recurring_id = :id "
               "AND s.date BETWEEN :start AND :end")
        params["id"] = line["recurring_id"]
    elif line["kind"] == "person":
        sql = ("SELECT COALESCE(SUM(s.amount), 0) FROM spending_net s WHERE s.user_id = :person "
               "AND s.date BETWEEN :start AND :end" + _not_in("s.recurring_id", ctx["sub_ids"]))
        sql += _skip_categories(ctx["planned_names"], params)
        params["person"] = line["person_user_id"]
    else:
        return None  # custom lines aren't tracked
    return money(conn.execute(sql, params).fetchone()[0])


def history_months(conn, year, month, wanted):
    """How many complete months before (year, month) to average over —
    fewer if the family's history doesn't go back that far."""
    first = conn.execute(
        "SELECT MIN(d) FROM (SELECT MIN(date) AS d FROM spending UNION ALL SELECT MIN(date) FROM bills)").fetchone()[0]
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
def build_report(conn, year, month, months_wanted):
    plan = get_plan(conn)
    sync_auto_lines(conn, plan)
    lines = load_lines(conn, plan)
    visible = [l for l in lines if not l["hidden"]]

    start, end = month_bounds(year, month)
    n = history_months(conn, year, month, months_wanted)
    if n:
        hy, hm = shift_month(year, month, -n)
        h_start = month_bounds(hy, hm)[0]
        h_end = month_bounds(*shift_month(year, month, -1))[1]
    progress = month_progress_for(year, month)
    planned_names = {(l["category_name"] or "").lower() for l in visible if l["kind"] == "category"}
    ctx = {"sub_ids": [l["recurring_id"] for l in visible if l["kind"] == "subscription"],
           "planned_names": planned_names}

    for l in visible:
        l["spent"] = line_actual(conn, l, start, end, ctx)
        total = line_actual(conn, l, h_start, h_end, ctx) if n else None
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

    # Spending in categories that aren't in the plan, by people who don't
    # have a personal limit (theirs counts toward that limit instead).
    with_limits = [l["person_user_id"] for l in visible if l["kind"] == "person"]
    unplanned = _unplanned_categories(conn, planned_names, ctx["sub_ids"], with_limits, start, end,
                                      (h_start, h_end, n) if n else None)

    spending_this_month = money(conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM spending_net WHERE date BETWEEN :s AND :e",
        {"s": start, "e": end}).fetchone()[0])

    report = {
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
        "category_choices": _category_choices(conn, planned_names),
        "person_choices": _person_choices(conn, {l["person_user_id"] for l in lines if l["kind"] == "person"}),
    }
    dismissed = _dismissed_keys(conn)
    tips = suggestions(report)
    report["suggestions"] = [t for t in tips if t["key"] not in dismissed][:MAX_TIPS]
    report["dismissed_count"] = sum(1 for t in tips if t["key"] in dismissed)
    return report


def _unplanned_categories(conn, planned_names, sub_ids, skip_users, start, end, history):
    sql = ("SELECT c.name, MAX(c.color) AS color, COALESCE(SUM(s.amount), 0) AS total FROM spending_net s "
           "JOIN category_info c ON c.category_id = s.category_id "
           "WHERE s.date BETWEEN :start AND :end" + _not_in("s.recurring_id", sub_ids)
           + (f" AND s.user_id NOT IN ({','.join(str(int(u)) for u in skip_users)})" if skip_users else "")
           + " GROUP BY lower(c.name)")
    this_month = {r["name"].lower(): dict(r) for r in conn.execute(sql, {"start": start, "end": end})}
    averages = {}
    if history:
        h_start, h_end, n = history
        for r in conn.execute(sql, {"start": h_start, "end": h_end}):
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


def _category_choices(conn, planned_names):
    rows = conn.execute("SELECT name FROM category_info WHERE archived = 0 ORDER BY lower(name)")
    seen, out = set(), []
    for (name,) in rows:
        key = name.lower()
        if key not in planned_names and key not in seen:
            seen.add(key)
            out.append(name)
    return out


def _person_choices(conn, have):
    rows = conn.execute("SELECT user_id, username FROM users ORDER BY user_id").fetchall()
    return [{"user_id": r["user_id"], "username": r["username"]} for r in rows if r["user_id"] not in have]


def _dismissed_keys(conn):
    return {r[0] for r in conn.execute("SELECT key FROM suggestion_dismissals WHERE user_id = ?", (uid(),))}


def suggestions(report):
    """Plain-English tips, most useful first. Each has a `key` (so it can be
    closed) and may carry a one-tap action. The key includes the numbers, so
    a closed tip comes back as a new one when they change."""
    tips = []
    s = report["summary"]
    income = s["income"]
    n = report["history_months"]
    span = f"last {n} month{'s' if n != 1 else ''}"

    if not income:
        tips.append({"key": "no_income", "tone": "info",
                     "message": "Add the family's monthly income to see how much is left to assign."})
    elif s["left_to_assign"] < -0.005:
        tips.append({"key": f"overplanned:{-s['left_to_assign']:.0f}", "tone": "bad",
                     "message": f"You've planned ${-s['left_to_assign']:,.2f} more than your income. "
                                "Trim a Want or a personal limit to balance it."})
    elif s["left_to_assign"] >= 1:
        tips.append({"key": f"unassigned:{s['left_to_assign']:.0f}", "tone": "info",
                     "message": f"${s['left_to_assign']:,.2f} of income has no job yet. Consider giving it to Savings.",
                     "action": {"kind": "add_savings", "amount": s["left_to_assign"]}})

    for l in report["lines"]:
        what = f"{l['name']}'s personal spending" if l["kind"] == "person" else l["name"]
        if l["history"] == "over" and l["kind"] in ("category", "bill", "person"):
            diff = l["average"] - l["planned"]
            tips.append({"key": f"over:{l['line_id']}:{round_up(l['average']):.0f}:{l['planned']:.0f}",
                         "tone": "warn", "line_id": l["line_id"],
                         "message": f"You average ${l['average']:,.2f} on {what} ({span}) but planned "
                                    f"${l['planned']:,.2f}. Raise the plan, or aim to cut about ${diff:,.0f}/month.",
                         "action": {"kind": "set_amount", "line_id": l["line_id"], "amount": round_up(l["average"])}})
        elif l["history"] == "under" and l["kind"] in ("category", "person"):
            diff = l["planned"] - l["average"]
            tips.append({"key": f"under:{l['line_id']}:{round_up(l['average']):.0f}:{l['planned']:.0f}",
                         "tone": "ok", "line_id": l["line_id"],
                         "message": f"You planned ${l['planned']:,.2f} for {what} but average "
                                    f"${l['average']:,.2f}. Lowering it frees up about ${diff:,.0f}/month.",
                         "action": {"kind": "set_amount", "line_id": l["line_id"], "amount": round_up(l["average"])}})

    for u in report["unplanned"][:4]:
        amount = u["average"] if u["average"] else u["spent"]
        when = f"about ${u['average']:,.2f}/month" if u["average"] else f"${u['spent']:,.2f} this month"
        tips.append({"key": f"unplanned:{u['name'].lower()}:{round_up(amount):.0f}", "tone": "warn",
                     "message": f"You spend {when} on {u['name']}, which isn't in your plan.",
                     "action": {"kind": "add_category", "category_name": u["name"], "amount": round_up(amount),
                                "group": guess_group(u["name"])}})

    if income:
        g = report["groups"]
        essentials = (g["bills"]["planned"] + g["needs"]["planned"]) / income
        extras = (g["wants"]["planned"] + g["personal"]["planned"]) / income
        if essentials > 0.6:
            tips.append({"key": f"share:essentials:{essentials * 100:.0f}", "tone": "info",
                         "message": f"Bills and Needs take {essentials * 100:.0f}% of income "
                                    "(the 50/30/20 guide suggests about 50%)."})
        if extras > 0.4:
            tips.append({"key": f"share:extras:{extras * 100:.0f}", "tone": "info",
                         "message": f"Wants and Personal take {extras * 100:.0f}% of income "
                                    "(the 50/30/20 guide suggests about 30%)."})
        sav = g["savings"]
        if sav["share"] is not None and sav["share"] < 0.1:
            tips.append({"key": f"savings_low:{sav['share'] * 100:.0f}", "tone": "info",
                         "message": f"Savings are {sav['share'] * 100:.0f}% of income — the guide suggests 20%."})
    return tips


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@bp.get("")
@login_required
def planner():
    ym = parse_month(request.args.get("month")) or (today().year, today().month)
    months = request.args.get("months", 3, type=int)
    if months not in HISTORY_CHOICES:
        months = 3
    return build_report(get_db(), ym[0], ym[1], months)


@bp.patch("")
@login_required
def update_plan():
    data = body()
    conn = get_db()
    plan = get_plan(conn)
    for field in ("income", "overall_cap"):
        if field in data:
            value = data[field]
            value = None if value in (None, "") else to_amount(value, field, allow_zero=True)
            conn.execute(f"UPDATE plans SET {field} = ? WHERE plan_id = ?", (value, plan["plan_id"]))
    conn.commit()
    return {"ok": True}


def _read_group(value):
    group = value or "wants"
    if group not in GROUPS or group == "personal":
        raise ApiError("Group must be Bills, Needs, Wants or Savings.")
    return group


@bp.post("/lines")
@login_required
def add_line():
    data = body()
    conn = get_db()
    plan = get_plan(conn)
    kind = data.get("kind") or "category"
    amount = to_amount(data.get("amount") or 0, allow_zero=True)
    if kind == "category":
        group = _read_group(data.get("group"))
        name = clean_text(data.get("category_name"), 50)
        if not name:
            raise ApiError("Pick a category.")
        exists = conn.execute(
            "SELECT 1 FROM plan_lines WHERE plan_id = ? AND kind = 'category' AND lower(category_name) = lower(?)",
            (plan["plan_id"], name)).fetchone()
        if exists:
            raise ApiError(f"{name} is already in this plan.", 409)
        conn.execute("INSERT INTO plan_lines (plan_id, group_name, kind, category_name, amount) VALUES (?, ?, 'category', ?, ?)",
                     (plan["plan_id"], group, name, amount))
    elif kind == "custom":
        group = _read_group(data.get("group"))
        label = clean_text(data.get("label"), 50)
        if not label:
            raise ApiError("Give this budget area a name.")
        conn.execute("INSERT INTO plan_lines (plan_id, group_name, kind, label, amount) VALUES (?, ?, 'custom', ?, ?)",
                     (plan["plan_id"], group, label, amount))
    elif kind == "person":
        person = to_int(data.get("person_user_id"), "person")
        if not conn.execute("SELECT 1 FROM users WHERE user_id = ?", (person,)).fetchone():
            raise ApiError("Pick someone in the family.")
        if conn.execute("SELECT 1 FROM plan_lines WHERE plan_id = ? AND kind = 'person' AND person_user_id = ?",
                        (plan["plan_id"], person)).fetchone():
            raise ApiError("That person already has a personal limit.", 409)
        conn.execute("INSERT INTO plan_lines (plan_id, group_name, kind, person_user_id, amount) "
                     "VALUES (?, 'personal', 'person', ?, ?)", (plan["plan_id"], person, amount))
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
    if "group" in data and line["kind"] != "person":
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


@bp.post("/suggestions/dismiss")
@login_required
def dismiss_suggestion():
    key = clean_text(body().get("key"), 200)
    if not key:
        raise ApiError("Which suggestion?")
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO suggestion_dismissals (user_id, key) VALUES (?, ?)", (uid(), key))
    conn.commit()
    return {"ok": True}


@bp.delete("/suggestions/dismissed")
@login_required
def restore_suggestions():
    conn = get_db()
    conn.execute("DELETE FROM suggestion_dismissals WHERE user_id = ?", (uid(),))
    conn.commit()
    return {"ok": True}


@bp.post("/start")
@login_required
def start_from_spending():
    """Fill an empty plan with a line for each category the family has spent
    on, using the recent average (rounded up to $5)."""
    conn = get_db()
    now = today()
    report = build_report(conn, now.year, now.month, 3)
    added = 0
    for u in report["unplanned"]:
        amount = round_up(u["average"] if u["average"] else u["spent"])
        conn.execute("INSERT INTO plan_lines (plan_id, group_name, kind, category_name, amount) VALUES (?, ?, 'category', ?, ?)",
                     (report["plan"]["plan_id"], guess_group(u["name"]), u["name"], amount))
        added += 1
    conn.commit()
    return {"added": added}


def limits_for_dashboard(conn):
    """Monthly limits for Home, worst first: the family plan's category
    lines, your own personal limit and the overall cap. Also returns the
    budget behind Home's "safe to spend" figure (or None)."""
    if get_plan(conn, create=False) is None:
        return [], None
    now = today()
    report = build_report(conn, now.year, now.month, 3)
    out, mine = [], None
    for l in report["lines"]:
        if l["kind"] == "category" and l["planned"] > 0:
            out.append({"line_id": l["line_id"], "label": l["name"], "is_family": True,
                        "amount": l["planned"], "spent": l["spent"], "remaining": l["remaining"],
                        "pct": l["pct"], "status": l["status"]})
        elif l["kind"] == "person" and l.get("is_me") and l["planned"] > 0:
            mine = {"line_id": l["line_id"], "label": "My personal spending", "is_family": False,
                    "amount": l["planned"], "spent": l["spent"], "remaining": l["remaining"],
                    "pct": l["pct"], "status": l["status"]}
            out.append(mine)
    cap = report["plan"]["overall_cap"]
    if cap:
        spent = report["summary"]["spent_this_month"]
        out.append({"line_id": "cap-family", "label": "All family spending", "is_family": True,
                    "amount": cap, "spent": spent, "remaining": money(cap - spent),
                    "pct": round(spent / cap, 3), "status": status_for(cap, spent, report["month_progress"])})
    out.sort(key=lambda b: -b["pct"])

    # Safe to spend: your personal limit if you have one, otherwise the
    # family's everyday spending (not bills) against the plan.
    if mine:
        return out, {"amount": mine["amount"], "spent": mine["spent"], "kind": "personal"}
    everyday = cap or money(sum(l["planned"] for l in report["lines"]
                                if l["kind"] in ("category", "subscription", "person")))
    if not everyday:
        return out, None
    return out, {"amount": everyday, "spent": report["summary"]["spent_this_month"], "kind": "family"}
