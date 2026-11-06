"""CSV import from bank / card statements.

Flow:
  1. POST /api/import/preview  — upload a CSV + pick a card. We detect the
     bank format, parse every row, suggest a category for each, and flag
     duplicates. Nothing is saved yet.
  2. You review/adjust in the app.
  3. POST /api/import/commit   — saves the rows you kept (after a backup).

Every bank exports different columns, so each preset below lists the column
names to look for. If a preset is wrong for your file, the app lets you pick
the columns by hand (the "generic" mapping), and remembers it for that card.
"""
import csv
import hashlib
import io
import json
import re
from datetime import date, datetime, timezone

from flask import Blueprint, request

from .. import backups
from ..auth import login_required, uid
from ..db import db_path, get_db, money
from ..errors import ApiError, body, clean_text, to_int
from .lookups import check_card, check_category

bp = Blueprint("imports", __name__, url_prefix="/api/import")

# Column names are matched case-insensitively. "sign" says how the file
# writes a purchase: charge_positive (purchases are +), charge_negative
# (purchases are −, typical for bank/checking accounts) or auto (guess).
PRESETS = {
    "apple": {
        "label": "Apple Card",
        "date": ["Transaction Date"], "description": ["Merchant", "Description"],
        "amount": ["Amount (USD)", "Amount"], "category": ["Category"], "type": ["Type"],
        "sign": "charge_positive", "detect": ["clearing date", "amount (usd)"],
    },
    "amex": {
        "label": "American Express",
        "date": ["Date"], "description": ["Description"], "amount": ["Amount"], "category": ["Category"],
        "sign": "charge_positive", "detect": ["appears on your statement as", "extended details"],
    },
    "navy_federal": {
        "label": "Navy Federal",
        "date": ["Transaction Date", "Posting Date", "Date"], "description": ["Description", "Merchant"],
        "amount": ["Amount"], "indicator": ["Credit Debit Indicator"], "debit": ["Debit"], "credit": ["Credit"],
        "category": ["Category"], "sign": "auto", "detect": ["credit debit indicator"],
    },
    "keesler": {
        "label": "Keesler Federal",
        "date": ["Transaction Date", "Date", "Posted Date", "Post Date", "Posting Date"],
        "description": ["Description", "Payee", "Merchant", "Memo"],
        "amount": ["Amount", "Transaction Amount"], "debit": ["Debit", "Withdrawal", "Withdrawals", "Amount Debit"],
        "credit": ["Credit", "Deposit", "Deposits", "Amount Credit"], "category": ["Category"],
        "sign": "auto", "detect": [],
    },
    "generic": {
        "label": "Other (pick columns)",
        "date": ["Transaction Date", "Date", "Trans. Date", "Posted Date", "Posting Date", "Post Date"],
        "description": ["Merchant", "Description", "Payee", "Name", "Memo", "Details"],
        "amount": ["Amount", "Amount (USD)", "Transaction Amount"], "debit": ["Debit", "Withdrawal"],
        "credit": ["Credit", "Deposit"], "indicator": ["Credit Debit Indicator"], "category": ["Category"],
        "sign": "auto", "detect": [],
    },
}

DATE_FORMATS = ["%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y", "%m-%d-%Y", "%Y/%m/%d", "%b %d, %Y", "%d %b %Y"]
PAYMENT_WORDS = re.compile(r"payment|thank you|autopay|auto pay|pymt|transfer", re.I)
REFUND_WORDS = re.compile(r"refund|return|reversal|credit|cashback|cash back", re.I)
# Credit-card-only issuers: any money back on these is a refund/credit,
# never income. Navy Federal and Keesler can be checking accounts too.
CARD_ONLY_PRESETS = ("apple", "amex")
MAX_ROWS = 2000


# ---------------------------------------------------------------------------
# Reading the file
# ---------------------------------------------------------------------------
def read_csv(raw_bytes):
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw_bytes.decode("latin-1")
    rows = [r for r in csv.reader(io.StringIO(text)) if any(cell.strip() for cell in r)]
    if not rows:
        raise ApiError("That file is empty.")
    # Some banks put a few info lines above the real header — find it.
    header_index = 0
    for i, row in enumerate(rows[:15]):
        lowered = " ".join(c.lower() for c in row)
        if "date" in lowered and any(w in lowered for w in ("amount", "debit", "credit", "withdrawal")):
            header_index = i
            break
    headers = [h.strip() for h in rows[header_index]]
    records = []
    for row in rows[header_index + 1:]:
        records.append({headers[i]: (row[i].strip() if i < len(row) else "") for i in range(len(headers))})
    return headers, records[:MAX_ROWS]


def find_column(headers, candidates):
    lookup = {h.lower(): h for h in headers}
    for name in candidates or []:
        if name.lower() in lookup:
            return lookup[name.lower()]
    return None


def detect_preset(headers):
    lowered = [h.lower() for h in headers]
    for key, preset in PRESETS.items():
        if any(d in lowered for d in preset["detect"]):
            return key
    return "generic"


def mapping_for(preset_key, headers):
    p = PRESETS[preset_key]
    m = {field: find_column(headers, p.get(field)) for field in
         ("date", "description", "amount", "debit", "credit", "indicator", "category", "type")}
    # Prefer separate debit/credit columns only when there's no single amount column.
    if m["amount"]:
        m["debit"] = m["credit"] = None
    m["sign"] = p["sign"]
    return m


def fits(preset_key, headers):
    """True if this preset finds a date column and some amount column in the file."""
    m = mapping_for(preset_key, headers)
    return bool(m["date"] and (m["amount"] or m["debit"] or m["credit"]))


def parse_amount(text):
    if text is None:
        return None
    t = str(text).strip().replace("$", "").replace(",", "").replace("USD", "").strip()
    if not t:
        return None
    negative = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    if t.upper().endswith("CR"):
        negative, t = True, t[:-2].strip()
    try:
        value = float(t)
    except ValueError:
        return None
    return -value if negative else value


def parse_any_date(text):
    t = (text or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    return None


def charge_amounts(records, m):
    """Each row's purchase amount: + for a purchase, − for a credit/refund/payment."""
    values = []
    for r in records:
        if m.get("debit") or m.get("credit"):
            debit = abs(parse_amount(r.get(m.get("debit"))) or 0)
            credit = abs(parse_amount(r.get(m.get("credit"))) or 0)
            values.append(debit - credit if (debit or credit) else None)
        elif m.get("indicator"):
            amount = parse_amount(r.get(m.get("amount")))
            if amount is None:
                values.append(None)
            else:
                is_credit = r.get(m["indicator"], "").strip().lower().startswith("credit")
                values.append(-abs(amount) if is_credit else abs(amount))
        else:
            values.append(parse_amount(r.get(m.get("amount"))))

    if not (m.get("debit") or m.get("credit") or m.get("indicator")):
        sign = m.get("sign", "auto")
        if sign == "auto":
            nonzero = [v for v in values if v]
            sign = "charge_negative" if nonzero and sum(v < 0 for v in nonzero) > len(nonzero) / 2 else "charge_positive"
            m["sign"] = sign
        if sign == "charge_negative":
            values = [-v if v is not None else None for v in values]
    return values


def tidy_merchant(text):
    t = re.sub(r"\s+", " ", (text or "")).strip()
    return t[:80] or None


# ---------------------------------------------------------------------------
# Category suggestions and duplicate detection
# ---------------------------------------------------------------------------
def category_suggester(conn):
    """Returns a function: (merchant, bank_category) -> category_id or None."""
    known = {}
    for r in conn.execute(
        "SELECT merchant, category_id FROM spending WHERE user_id = ? AND merchant IS NOT NULL "
        "ORDER BY date, id", (uid(),)).fetchall():
        known[r["merchant"].lower()] = r["category_id"]  # later rows win = most recent
    by_length = sorted((k for k in known if len(k) >= 3), key=len, reverse=True)
    categories = {r["name"].lower(): r["category_id"] for r in conn.execute(
        "SELECT name, category_id FROM category_info WHERE user_id = ? AND archived = 0", (uid(),)).fetchall()}

    def suggest(merchant, bank_category):
        m = (merchant or "").lower()
        if m in known:
            return known[m]
        for k in by_length:  # e.g. known "tesco" matches "TESCO STORES 2345"
            if k in m:
                return known[k]
        bc = (bank_category or "").lower().strip()
        if bc:
            if bc in categories:
                return categories[bc]
            for name, cid in categories.items():
                if name in bc or bc in name:
                    return cid
        return None
    return suggest


def fingerprint(card_id, d, amount, merchant, occurrence):
    key = f"{uid()}|{card_id}|{d}|{amount:.2f}|{(merchant or '').lower()}|{occurrence}"
    return hashlib.sha1(key.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@bp.get("/presets")
@login_required
def presets():
    return {"presets": [{"key": k, "label": p["label"]} for k, p in PRESETS.items()]}


@bp.post("/preview")
@login_required
def preview():
    conn = get_db()
    upload = request.files.get("file")
    if upload is None:
        raise ApiError("Choose a CSV file to import.")
    card = check_card(conn, to_int(request.form.get("card_id"), "card"))
    headers, records = read_csv(upload.read())

    preset = request.form.get("preset")
    if not preset:
        # Use the card's remembered format only if this file actually has its columns —
        # otherwise (e.g. the wrong card was picked) work the format out from the file.
        remembered = card["import_preset"]
        preset = remembered if remembered in PRESETS and fits(remembered, headers) else detect_preset(headers)
    if preset not in PRESETS:
        preset = "generic"
    if request.form.get("mapping"):
        mapping = json.loads(request.form["mapping"])
    elif card["import_mapping"] and card["import_preset"] == preset:
        mapping = json.loads(card["import_mapping"])
        if not all(v in headers for k, v in mapping.items() if k != "sign" and v):
            mapping = mapping_for(preset, headers)  # saved mapping doesn't fit this file
    else:
        mapping = mapping_for(preset, headers)
    if request.form.get("flip") == "1":
        mapping["sign"] = "charge_negative" if mapping.get("sign") != "charge_negative" else "charge_positive"

    problems = []
    if not mapping.get("date"):
        problems.append("Couldn't find the date column.")
    if not (mapping.get("amount") or mapping.get("debit") or mapping.get("credit")):
        problems.append("Couldn't find the amount column.")
    if problems:
        return {"headers": headers, "preset": preset, "mapping": mapping, "rows": [], "problems": problems,
                "presets": [{"key": k, "label": p["label"]} for k, p in PRESETS.items()]}

    amounts = charge_amounts(records, mapping)
    suggest = category_suggester(conn)
    existing_hashes = {r[0] for r in conn.execute(
        "SELECT import_hash FROM spending WHERE user_id = ? AND card_id = ? AND import_hash IS NOT NULL",
        (uid(), card["card_id"])).fetchall()}
    manual = [dict(r) for r in conn.execute(
        "SELECT id, date, amount FROM spending WHERE user_id = ? AND card_id = ? AND import_hash IS NULL",
        (uid(), card["card_id"])).fetchall()]
    used_manual = set()
    seen = {}
    rows = []

    for i, (record, amount) in enumerate(zip(records, amounts)):
        d = parse_any_date(record.get(mapping["date"]))
        merchant = tidy_merchant(record.get(mapping.get("description") or "", ""))
        if d is None or amount is None or amount == 0:
            continue
        amount = money(amount)
        bank_type = record.get(mapping.get("type") or "", "")
        if amount > 0:
            kind = "purchase"
        elif bank_type.lower() == "payment" or PAYMENT_WORDS.search(merchant or ""):
            kind = "payment"  # paying the card off — not spending
        elif REFUND_WORDS.search(merchant or "") or preset in CARD_ONLY_PRESETS:
            kind = "refund"
        else:
            kind = "income"  # money in on a bank account (pay, deposits) — not a refund

        key = (str(d), amount, (merchant or "").lower())
        seen[key] = seen.get(key, 0) + 1
        h = fingerprint(card["card_id"], d, amount, merchant, seen[key])

        status = "new"
        if h in existing_hashes:
            status = "duplicate"
        else:
            for m in manual:
                if m["id"] in used_manual or abs(m["amount"] - amount) > 0.005:
                    continue
                if abs((date.fromisoformat(m["date"]) - d).days) <= 3:
                    status = "possible_duplicate"
                    used_manual.add(m["id"])
                    break

        rows.append({
            "row": i, "date": str(d), "merchant": merchant, "amount": amount, "kind": kind,
            "bank_category": record.get(mapping.get("category") or "", "") or None,
            "category_id": suggest(merchant, record.get(mapping.get("category") or "", "")),
            "import_hash": h, "status": status,
            "include": status == "new" and kind in ("purchase", "refund"),
        })

    return {"headers": headers, "preset": preset, "mapping": mapping, "rows": rows, "problems": [],
            "presets": [{"key": k, "label": p["label"]} for k, p in PRESETS.items()],
            "card_id": card["card_id"]}


@bp.post("/commit")
@login_required
def commit():
    conn = get_db()
    data = body()
    card = check_card(conn, to_int(data.get("card_id"), "card"))
    rows = data.get("rows") or []
    if not rows:
        raise ApiError("Nothing selected to import.")
    if len(rows) > MAX_ROWS:
        raise ApiError("Too many rows in one import.")

    clean = []
    for r in rows:
        d = parse_any_date(r.get("date"))
        if d is None:
            raise ApiError(f"Row with bad date: {r.get('date')}")
        try:
            amount = money(r.get("amount"))
        except (TypeError, ValueError):
            raise ApiError("Row with a bad amount.")
        if amount == 0:
            continue
        category_id = check_category(conn, to_int(r.get("category_id"), "category for every row"))["category_id"]
        clean.append((category_id, card["card_id"], uid(), amount, str(d), tidy_merchant(r.get("merchant")),
                      clean_text(r.get("notes"), 500), (r.get("import_hash") or "")[:40] or None))

    hashes = [c[7] for c in clean if c[7]]
    if hashes:
        placeholders = ",".join("?" * len(hashes))
        already = {row[0] for row in conn.execute(
            f"SELECT import_hash FROM spending WHERE import_hash IN ({placeholders})", hashes).fetchall()}
        clean = [c for c in clean if c[7] not in already]

    backups.create_backup(db_path(), "preimport")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.executemany(
        """INSERT INTO spending (category_id, card_id, user_id, amount, date, merchant, notes, import_hash, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", [c + (now,) for c in clean])

    if data.get("preset") in PRESETS:
        conn.execute("UPDATE card_info SET import_preset = ?, import_mapping = ? WHERE card_id = ?",
                     (data["preset"], json.dumps(data.get("mapping") or {}), card["card_id"]))
    conn.commit()
    return {"imported": len(clean)}

