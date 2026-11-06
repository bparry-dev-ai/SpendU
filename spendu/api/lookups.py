"""Cards and categories (each user has their own list).

A card or category that is used by transactions can't be deleted — archive
it instead: it disappears from the pickers but old transactions keep it.
"""
import sqlite3

from flask import Blueprint

from ..auth import login_required, uid
from ..db import get_db, to_dicts
from ..errors import ApiError, body, clean_text

bp = Blueprint("lookups", __name__, url_prefix="/api")

# Default colours handed out to new cards/categories (charts use them).
PALETTE = ["#6366f1", "#14b8a6", "#f59e0b", "#ec4899", "#22c55e", "#3b82f6",
           "#ef4444", "#a855f7", "#06b6d4", "#84cc16", "#f97316", "#64748b"]

LOOKUPS = {
    "cards": {
        "table": "card_info", "id": "card_id", "label": "card",
        "used_by": [("spending", "card_id"), ("bills", "card_id"), ("recurring", "card_id")],
        "fields": ("name", "color", "archived"),
    },
    "categories": {
        "table": "category_info", "id": "category_id", "label": "category",
        "used_by": [("spending", "category_id"), ("recurring", "category_id")],
        "fields": ("name", "color", "icon", "archived"),
    },
}


def owned(conn, kind, item_id):
    """Fetch the user's own card/category, or fail with 404."""
    cfg = LOOKUPS[kind]
    row = conn.execute(
        f"SELECT * FROM {cfg['table']} WHERE {cfg['id']} = ? AND user_id = ?", (item_id, uid())
    ).fetchone()
    if row is None:
        raise ApiError(f"That {cfg['label']} was not found.", 404)
    return row


def check_card(conn, card_id):
    return owned(conn, "cards", card_id)


def check_category(conn, category_id):
    return owned(conn, "categories", category_id)


def load_meta(conn):
    cards = conn.execute(
        "SELECT card_id, name, color, archived, import_preset FROM card_info WHERE user_id = ? ORDER BY archived, name",
        (uid(),),
    ).fetchall()
    categories = conn.execute(
        "SELECT category_id, name, color, icon, archived FROM category_info WHERE user_id = ? ORDER BY archived, name",
        (uid(),),
    ).fetchall()
    bills = conn.execute(
        "SELECT bill_id, name, amount, due_day, frequency, due_month, card_id, autopay, active "
        "FROM bill_info ORDER BY active DESC, name"
    ).fetchall()
    return {"cards": _with_colors(to_dicts(cards)), "categories": _with_colors(to_dicts(categories)),
            "bills": to_dicts(bills)}


def _with_colors(items):
    for i, item in enumerate(items):
        item["color"] = item.get("color") or PALETTE[i % len(PALETTE)]
    return items


@bp.get("/meta")
@login_required
def meta():
    return load_meta(get_db())


@bp.post("/<any(cards, categories):kind>")
@login_required
def create_lookup(kind):
    if kind not in LOOKUPS:
        raise ApiError("Not found.", 404)
    cfg = LOOKUPS[kind]
    data = body()
    name = clean_text(data.get("name"), 50)
    if not name:
        raise ApiError(f"Please enter a {cfg['label']} name.")
    conn = get_db()
    count = conn.execute(f"SELECT COUNT(*) FROM {cfg['table']} WHERE user_id = ?", (uid(),)).fetchone()[0]
    color = data.get("color") or PALETTE[count % len(PALETTE)]
    try:
        if kind == "categories":
            cur = conn.execute("INSERT INTO category_info (name, user_id, color, icon) VALUES (?, ?, ?, ?)",
                               (name, uid(), color, clean_text(data.get("icon"), 8)))
        else:
            cur = conn.execute("INSERT INTO card_info (name, user_id, color) VALUES (?, ?, ?)",
                               (name, uid(), color))
        conn.commit()
    except sqlite3.IntegrityError:
        raise ApiError(f"You already have a {cfg['label']} called {name}.", 409)
    return {"id": cur.lastrowid, **load_meta(conn)}, 201


@bp.patch("/<any(cards, categories):kind>/<int:item_id>")
@login_required
def update_lookup(kind, item_id):
    if kind not in LOOKUPS:
        raise ApiError("Not found.", 404)
    cfg = LOOKUPS[kind]
    conn = get_db()
    current = owned(conn, kind, item_id)
    data = body()
    updates = {}
    if "name" in data:
        name = clean_text(data.get("name"), 50)
        if not name:
            raise ApiError("Name can't be empty.")
        updates["name"] = name
    if "color" in data:
        updates["color"] = clean_text(data.get("color"), 20)
    if "icon" in data and kind == "categories":
        updates["icon"] = clean_text(data.get("icon"), 8)
    if "archived" in data:
        updates["archived"] = 1 if data.get("archived") else 0
    if not updates:
        return load_meta(conn)

    sets = ", ".join(f"{col} = ?" for col in updates)
    try:
        conn.execute(f"UPDATE {cfg['table']} SET {sets} WHERE {cfg['id']} = ? AND user_id = ?",
                     (*updates.values(), item_id, uid()))
    except sqlite3.IntegrityError:
        raise ApiError(f"You already have a {cfg['label']} with that name.", 409)
    # Personal budgets refer to categories by name — keep them in step on rename.
    if kind == "categories" and "name" in updates and updates["name"] != current["name"]:
        conn.execute("UPDATE budgets SET category_name = ? WHERE user_id = ? AND is_family = 0 AND category_name = ?",
                     (updates["name"], uid(), current["name"]))
    conn.commit()
    return load_meta(conn)


@bp.delete("/<any(cards, categories):kind>/<int:item_id>")
@login_required
def delete_lookup(kind, item_id):
    if kind not in LOOKUPS:
        raise ApiError("Not found.", 404)
    cfg = LOOKUPS[kind]
    conn = get_db()
    owned(conn, kind, item_id)
    for table, column in cfg["used_by"]:
        used = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} = ?", (item_id,)).fetchone()[0]
        if used:
            raise ApiError(f"This {cfg['label']} is used by existing transactions, so it can't be deleted. "
                           f"Archive it instead to hide it.", 409)
    conn.execute(f"DELETE FROM {cfg['table']} WHERE {cfg['id']} = ? AND user_id = ?", (item_id, uid()))
    conn.commit()
    return load_meta(conn)
