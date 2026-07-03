PRAGMA foreign_keys = ON;

CREATE TABLE users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
);

CREATE TABLE passkeys (
    credential_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    public_key BLOB NOT NULL,
    sign_count INTEGER NOT NULL DEFAULT 0,
    created TEXT NOT NULL DEFAULT (date('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE card_info (
    card_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    user_id INTEGER REFERENCES users(user_id),
    UNIQUE(user_id, name)
);

CREATE TABLE bill_info (
    bill_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE category_info (
    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    user_id INTEGER REFERENCES users(user_id),
    UNIQUE(user_id, name)
);

CREATE TABLE spending (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL,
    card_id INTEGER NOT NULL,
    user_id INTEGER REFERENCES users(user_id),
    amount REAL NOT NULL,
    date TEXT NOT NULL DEFAULT (date('now')),
    FOREIGN KEY (category_id) REFERENCES category_info(category_id),
    FOREIGN KEY (card_id) REFERENCES card_info(card_id)
);

CREATE TABLE bills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_id INTEGER NOT NULL,
    card_id INTEGER NOT NULL,
    user_id INTEGER REFERENCES users(user_id),
    amount REAL NOT NULL,
    date TEXT NOT NULL DEFAULT (date('now')),
    FOREIGN KEY (bill_id) REFERENCES bill_info(bill_id),
    FOREIGN KEY (card_id) REFERENCES card_info(card_id)
);