"""Database connection helpers.

Every request gets one SQLite connection (stored on Flask's `g`), which is
closed automatically when the request ends.
"""
import os
import sqlite3

from flask import g


def db_path():
    """Where the database file lives.

    Docker: /app/data/spending.db (the whole data folder is mounted, so the
    backups/ folder next to it survives rebuilds). Locally: set DB_PATH in .env.
    """
    return os.environ.get("DB_PATH", "/app/data/spending.db")


def connect(path=None):
    conn = sqlite3.connect(path or db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def get_db():
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_error=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def to_dicts(rows):
    """sqlite3.Row objects -> plain dicts, so Flask can turn them into JSON."""
    return [dict(row) for row in rows]


def one(row):
    return dict(row) if row is not None else None


def money(value):
    """Round to cents. Amounts are stored as REAL (dollars), like v1."""
    return round(float(value or 0), 2)
