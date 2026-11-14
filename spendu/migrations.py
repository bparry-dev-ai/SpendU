"""Database migrations — upgrades an existing spending.db in place.

The database's version number is kept in SQLite's built-in `PRAGMA
user_version` (0 for any database made before v2). Each migration below runs
once, in order, inside a transaction: if anything fails, the database is left
exactly as it was and the error shows in `docker compose logs`.

Rules followed so existing data keeps working:
- only ADD tables/columns, never rename or drop anything holding data
- new columns are optional (NULL for old rows)
- a backup is taken before migrating (see backups.py)
"""
import sqlite3

from . import backups

# Same palette as api/lookups.py PALETTE (kept here so migrations never
# depend on code that may change later).
DEFAULT_COLORS = ["#6366f1", "#14b8a6", "#f59e0b", "#ec4899", "#22c55e", "#3b82f6",
                  "#ef4444", "#a855f7", "#06b6d4", "#84cc16", "#f97316", "#64748b"]


def _columns(conn, table):
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def _add_column(conn, table, column, definition):
    if column not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def adopt_unowned_rows(conn):
    """Give rows with no owner to the earliest-created user (v1.2 behaviour)."""
    first_user = conn.execute("SELECT MIN(user_id) FROM users").fetchone()[0]
    if first_user is None:
        return
    for table in ("spending", "bills", "card_info", "category_info"):
        conn.execute(f"UPDATE {table} SET user_id = ? WHERE user_id IS NULL", (first_user,))


# ---------------------------------------------------------------------------
# Migration 1 — the v1.2 schema (login, passkeys, family profiles).
# A no-op on the live server (already v1.2); creates everything on a fresh
# install; upgrades a pre-1.2 database the same way v1.2's code did.
# ---------------------------------------------------------------------------
def migration_1_v12_baseline(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS passkeys (
            credential_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            public_key BLOB NOT NULL,
            sign_count INTEGER NOT NULL DEFAULT 0,
            created TEXT NOT NULL DEFAULT (date('now')),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS card_info (
            card_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            user_id INTEGER REFERENCES users(user_id),
            UNIQUE(user_id, name)
        )""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bill_info (
            bill_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS category_info (
            category_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            user_id INTEGER REFERENCES users(user_id),
            UNIQUE(user_id, name)
        )""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS spending (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            card_id INTEGER NOT NULL,
            user_id INTEGER REFERENCES users(user_id),
            amount REAL NOT NULL,
            date TEXT NOT NULL DEFAULT (date('now')),
            FOREIGN KEY (category_id) REFERENCES category_info(category_id),
            FOREIGN KEY (card_id) REFERENCES card_info(card_id)
        )""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_id INTEGER NOT NULL,
            card_id INTEGER NOT NULL,
            user_id INTEGER REFERENCES users(user_id),
            amount REAL NOT NULL,
            date TEXT NOT NULL DEFAULT (date('now')),
            FOREIGN KEY (bill_id) REFERENCES bill_info(bill_id),
            FOREIGN KEY (card_id) REFERENCES card_info(card_id)
        )""")

    # Pre-1.2 databases: same steps as v1.2's migrate_family_columns().
    for table in ("spending", "bills"):
        _add_column(conn, table, "user_id", "INTEGER REFERENCES users(user_id)")
    for table, id_col in (("card_info", "card_id"), ("category_info", "category_id")):
        if "user_id" not in _columns(conn, table):
            conn.execute(f"""
                CREATE TABLE {table}_new (
                    {id_col} INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    user_id INTEGER REFERENCES users(user_id),
                    UNIQUE(user_id, name)
                )""")
            conn.execute(f"INSERT INTO {table}_new ({id_col}, name) SELECT {id_col}, name FROM {table}")
            conn.execute(f"DROP TABLE {table}")
            conn.execute(f"ALTER TABLE {table}_new RENAME TO {table}")
    adopt_unowned_rows(conn)


# ---------------------------------------------------------------------------
# Migration 2 — SpendU v2.
# ---------------------------------------------------------------------------
def migration_2_v2_features(conn):
    # Spending: merchant, notes, refunds (stored as negative amounts),
    # link to a subscription, and a fingerprint for CSV-import de-duplication.
    _add_column(conn, "spending", "merchant", "TEXT")
    _add_column(conn, "spending", "notes", "TEXT")
    _add_column(conn, "spending", "recurring_id", "INTEGER")
    _add_column(conn, "spending", "import_hash", "TEXT")
    _add_column(conn, "spending", "created_at", "TEXT")

    # Bill payments: which month's bill this payment covers, plus notes.
    _add_column(conn, "bills", "bill_month", "TEXT")
    _add_column(conn, "bills", "notes", "TEXT")
    conn.execute("UPDATE bills SET bill_month = substr(date, 1, 7) WHERE bill_month IS NULL")

    # Bill types become recurring bills: usual amount, due day, default card.
    _add_column(conn, "bill_info", "amount", "REAL")
    _add_column(conn, "bill_info", "due_day", "INTEGER")
    _add_column(conn, "bill_info", "frequency", "TEXT NOT NULL DEFAULT 'monthly'")
    _add_column(conn, "bill_info", "due_month", "INTEGER")
    _add_column(conn, "bill_info", "card_id", "INTEGER")
    _add_column(conn, "bill_info", "autopay", "INTEGER NOT NULL DEFAULT 0")
    _add_column(conn, "bill_info", "active", "INTEGER NOT NULL DEFAULT 1")
    _add_column(conn, "bill_info", "start_month", "TEXT")
    _add_column(conn, "bill_info", "notes", "TEXT")

    # Cards and categories: colour for charts, archive instead of delete.
    _add_column(conn, "card_info", "color", "TEXT")
    _add_column(conn, "card_info", "archived", "INTEGER NOT NULL DEFAULT 0")
    _add_column(conn, "card_info", "import_preset", "TEXT")
    _add_column(conn, "card_info", "import_mapping", "TEXT")
    _add_column(conn, "category_info", "color", "TEXT")
    _add_column(conn, "category_info", "icon", "TEXT")
    _add_column(conn, "category_info", "archived", "INTEGER NOT NULL DEFAULT 0")

    # Give existing cards/categories a colour so charts can tell them apart.
    for table, id_col in (("card_info", "card_id"), ("category_info", "category_id")):
        rows = conn.execute(f"SELECT {id_col}, user_id FROM {table} WHERE color IS NULL ORDER BY user_id, name").fetchall()
        position = {}
        for item_id, owner in rows:
            i = position.get(owner, 0)
            position[owner] = i + 1
            conn.execute(f"UPDATE {table} SET color = ? WHERE {id_col} = ?", (DEFAULT_COLORS[i % len(DEFAULT_COLORS)], item_id))

    _add_column(conn, "users", "timezone", "TEXT")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            budget_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(user_id),
            is_family INTEGER NOT NULL DEFAULT 0,
            category_name TEXT,          -- NULL = all spending
            amount REAL NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recurring (
            recurring_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(user_id),
            name TEXT NOT NULL,
            amount REAL NOT NULL,
            category_id INTEGER NOT NULL REFERENCES category_info(category_id),
            card_id INTEGER NOT NULL REFERENCES card_info(card_id),
            frequency TEXT NOT NULL DEFAULT 'monthly',  -- weekly / monthly / yearly
            anchor_day INTEGER,
            next_date TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            notes TEXT
        )""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS login_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT,
            username TEXT,
            attempted_at REAL NOT NULL
        )""")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_spending_user_date ON spending(user_id, date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_spending_import ON spending(import_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bills_user_date ON bills(user_id, date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bills_month ON bills(bill_id, bill_month)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_login_attempts ON login_attempts(attempted_at)")


# ---------------------------------------------------------------------------
# Migration 3 — Budget Planner (replaces the Budgets page).
# The old `budgets` table is kept untouched; its rows are copied into plans.
# ---------------------------------------------------------------------------
NEEDS_WORDS = ("grocer", "gas", "fuel", "rent", "mortgage", "util", "insur", "medic", "health", "pharm",
               "transport", "childcare", "electric", "water", "phone", "internet")


def guess_group(name):
    lowered = (name or "").lower()
    return "needs" if any(w in lowered for w in NEEDS_WORDS) else "wants"


def migration_3_budget_planner(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS plans (
            plan_id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_user_id INTEGER UNIQUE REFERENCES users(user_id),  -- NULL = the household plan
            income REAL,
            overall_cap REAL,             -- optional limit on all spending
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS plan_lines (
            line_id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL REFERENCES plans(plan_id),
            group_name TEXT NOT NULL DEFAULT 'wants',     -- needs / wants / savings
            kind TEXT NOT NULL,                           -- category / bill / subscription / custom
            label TEXT,
            category_name TEXT,
            bill_id INTEGER REFERENCES bill_info(bill_id),
            recurring_id INTEGER REFERENCES recurring(recurring_id),
            amount REAL,                  -- NULL on bill/subscription lines = follow the bill's usual amount
            hidden INTEGER NOT NULL DEFAULT 0,  -- removed auto lines stay hidden so they don't come back
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_plan_lines_plan ON plan_lines(plan_id)")

    # Copy existing budgets into plans: personal budgets -> that person's
    # plan, family budgets -> the household plan, "All spending" -> overall cap.
    def plan_for(owner):
        row = conn.execute("SELECT plan_id FROM plans WHERE owner_user_id IS ?", (owner,)).fetchone()
        if row:
            return row[0]
        return conn.execute("INSERT INTO plans (owner_user_id) VALUES (?)", (owner,)).lastrowid

    for user_id, is_family, category_name, amount in conn.execute(
            "SELECT user_id, is_family, category_name, amount FROM budgets ORDER BY budget_id").fetchall():
        plan_id = plan_for(None if is_family else user_id)
        if category_name is None:
            conn.execute("UPDATE plans SET overall_cap = ? WHERE plan_id = ?", (amount, plan_id))
        else:
            conn.execute(
                "INSERT INTO plan_lines (plan_id, group_name, kind, category_name, amount) VALUES (?, ?, 'category', ?, ?)",
                (plan_id, guess_group(category_name), category_name, amount))


def _line_key(kind, category_name, bill_id, recurring_id, label, person_user_id=None):
    if kind == "category":
        return ("category", (category_name or "").lower())
    if kind == "bill":
        return ("bill", bill_id)
    if kind == "subscription":
        return ("subscription", recurring_id)
    if kind == "person":
        return ("person", person_user_id)
    return ("custom", (label or "").lower())


# ---------------------------------------------------------------------------
# Migration 4 — one family plan with Bills and Personal sections, bill
# refunds, and dismissable planner suggestions.
# Nothing is deleted: the old personal plans stay in the database, but their
# lines are moved into the family (household) plan, skipping any the family
# plan already has.
# ---------------------------------------------------------------------------
def migration_4_family_plan(conn):
    # A refund that pays back a bill (e.g. a card payment towards bill charges)
    # counts against Bills instead of reducing spending.
    _add_column(conn, "spending", "bill_credit", "INTEGER NOT NULL DEFAULT 0")
    # Everyday spending: everything except bill refunds.
    conn.execute("CREATE VIEW IF NOT EXISTS spending_net AS SELECT * FROM spending WHERE bill_credit = 0")

    # Personal spending limits: plan lines of kind 'person'.
    _add_column(conn, "plan_lines", "person_user_id", "INTEGER REFERENCES users(user_id)")

    # Suggestions someone closed. The key includes the numbers behind the
    # suggestion, so a changed situation brings up a fresh one.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS suggestion_dismissals (
            user_id INTEGER NOT NULL REFERENCES users(user_id),
            key TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (user_id, key)
        )""")

    # Merge personal plans into the one family plan.
    row = conn.execute("SELECT plan_id, income FROM plans WHERE owner_user_id IS NULL").fetchone()
    if row:
        family_id, family_income = row
    else:
        family_id = conn.execute("INSERT INTO plans (owner_user_id) VALUES (NULL)").lastrowid
        family_income = None
    have = {_line_key(*r) for r in conn.execute(
        "SELECT kind, category_name, bill_id, recurring_id, label FROM plan_lines WHERE plan_id = ?", (family_id,))}
    personal = conn.execute("SELECT plan_id, income FROM plans WHERE owner_user_id IS NOT NULL ORDER BY plan_id").fetchall()
    for plan_id, _ in personal:
        for line_id, *fields in conn.execute(
                "SELECT line_id, kind, category_name, bill_id, recurring_id, label FROM plan_lines "
                "WHERE plan_id = ? ORDER BY line_id", (plan_id,)).fetchall():
            key = _line_key(*fields)
            if key in have:
                continue
            conn.execute("UPDATE plan_lines SET plan_id = ? WHERE line_id = ?", (family_id, line_id))
            have.add(key)
    incomes = [inc for _, inc in personal if inc]
    if family_income is None and incomes:
        conn.execute("UPDATE plans SET income = ? WHERE plan_id = ?", (round(sum(incomes), 2), family_id))

    # Bills get their own section.
    conn.execute("UPDATE plan_lines SET group_name = 'bills' WHERE kind = 'bill'")


MIGRATIONS = [
    (1, migration_1_v12_baseline),
    (2, migration_2_v2_features),
    (3, migration_3_budget_planner),
    (4, migration_4_family_plan),
]
LATEST_VERSION = MIGRATIONS[-1][0]


def migrate(db_file):
    """Bring the database up to LATEST_VERSION. Safe to call on every start."""
    conn = sqlite3.connect(db_file)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version >= LATEST_VERSION:
            return
        has_tables = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'"
        ).fetchone()[0] > 0
        if has_tables:
            backups.create_backup(db_file, "premigrate")

        conn.isolation_level = None  # we manage BEGIN/COMMIT ourselves
        for number, step in MIGRATIONS:
            if number <= version:
                continue
            print(f"[migrate] applying migration {number}: {step.__name__}", flush=True)
            conn.execute("BEGIN")
            try:
                step(conn)
                conn.execute(f"PRAGMA user_version = {number}")
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                print(f"[migrate] migration {number} FAILED — database left unchanged", flush=True)
                raise
        # WAL lets the app read while writing; set once, remembered by the file.
        conn.execute("PRAGMA journal_mode = WAL")
        print(f"[migrate] database is at version {LATEST_VERSION}", flush=True)
    finally:
        conn.close()
