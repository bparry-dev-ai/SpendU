PRAGMA foreign_keys = ON;

CREATE TABLE card_info (
    card_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE bill_info (
    bill_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE category_info (
    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE spending (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL,
    card_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    date TEXT NOT NULL DEFAULT (date('now')),
    FOREIGN KEY (category_id) REFERENCES category_info(category_id),
    FOREIGN KEY (card_id) REFERENCES card_info(card_id)
);

CREATE TABLE bills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_id INTEGER NOT NULL,
    card_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    date TEXT NOT NULL DEFAULT (date('now')),
    FOREIGN KEY (bill_id) REFERENCES bill_info(bill_id),
    FOREIGN KEY (card_id) REFERENCES card_info(card_id)
);
