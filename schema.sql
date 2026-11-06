-- SpendU v2 database schema (reference only).
-- The real source of truth is spendu/migrations.py, which creates and
-- upgrades the database automatically when the app starts.
-- Regenerate this file after adding a migration.

CREATE TABLE bill_info (
            bill_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        , amount REAL, due_day INTEGER, frequency TEXT NOT NULL DEFAULT 'monthly', due_month INTEGER, card_id INTEGER, autopay INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1, start_month TEXT, notes TEXT);

CREATE TABLE bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_id INTEGER NOT NULL,
            card_id INTEGER NOT NULL,
            user_id INTEGER REFERENCES users(user_id),
            amount REAL NOT NULL,
            date TEXT NOT NULL DEFAULT (date('now')), bill_month TEXT, notes TEXT,
            FOREIGN KEY (bill_id) REFERENCES bill_info(bill_id),
            FOREIGN KEY (card_id) REFERENCES card_info(card_id)
        );

CREATE TABLE budgets (
            budget_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(user_id),
            is_family INTEGER NOT NULL DEFAULT 0,
            category_name TEXT,          -- NULL = all spending
            amount REAL NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

CREATE TABLE card_info (
            card_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            user_id INTEGER REFERENCES users(user_id), color TEXT, archived INTEGER NOT NULL DEFAULT 0, import_preset TEXT, import_mapping TEXT,
            UNIQUE(user_id, name)
        );

CREATE TABLE category_info (
            category_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            user_id INTEGER REFERENCES users(user_id), color TEXT, icon TEXT, archived INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, name)
        );

CREATE TABLE login_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT,
            username TEXT,
            attempted_at REAL NOT NULL
        );

CREATE TABLE passkeys (
            credential_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            public_key BLOB NOT NULL,
            sign_count INTEGER NOT NULL DEFAULT 0,
            created TEXT NOT NULL DEFAULT (date('now')),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );

CREATE TABLE recurring (
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
        );

CREATE TABLE spending (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            card_id INTEGER NOT NULL,
            user_id INTEGER REFERENCES users(user_id),
            amount REAL NOT NULL,
            date TEXT NOT NULL DEFAULT (date('now')), merchant TEXT, notes TEXT, recurring_id INTEGER, import_hash TEXT, created_at TEXT,
            FOREIGN KEY (category_id) REFERENCES category_info(category_id),
            FOREIGN KEY (card_id) REFERENCES card_info(card_id)
        );

CREATE TABLE users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        , timezone TEXT);

CREATE INDEX idx_bills_month ON bills(bill_id, bill_month);

CREATE INDEX idx_bills_user_date ON bills(user_id, date);

CREATE INDEX idx_login_attempts ON login_attempts(attempted_at);

CREATE INDEX idx_spending_import ON spending(import_hash);

CREATE INDEX idx_spending_user_date ON spending(user_id, date);
