"""In-app database backups (see BACKUPS.md for the full story).

- Before every migration:  spending-premigrate-YYYY-MM-DD-HHMMSS.db  (kept)
- Before every CSV import: spending-preimport-YYYY-MM-DD-HHMMSS.db   (kept)
- Once a day:              spending-daily-YYYY-MM-DD.db              (14 days)

Retention: daily backups older than 14 days are deleted, EXCEPT the newest
backup in the folder, which is never deleted no matter how old it is, so
there is always at least one backup.
"""
import os
import sqlite3
import threading
from datetime import datetime, timedelta

DAILY_KEEP_DAYS = 14
_lock = threading.Lock()
_last_daily_check = None  # date of the last daily check, so most requests skip the disk


def backup_dir(db_file):
    return os.path.join(os.path.dirname(os.path.abspath(db_file)), "backups")


def create_backup(db_file, reason):
    """Copy the database with SQLite's online backup API (safe while in use).

    Returns the backup's path. Writes to a temp name first so a half-written
    file is never mistaken for a good backup.
    """
    folder = backup_dir(db_file)
    os.makedirs(folder, exist_ok=True)
    now = datetime.now()
    if reason == "daily":
        name = f"spending-daily-{now:%Y-%m-%d}.db"
    else:
        name = f"spending-{reason}-{now:%Y-%m-%d-%H%M%S}.db"
    final_path = os.path.join(folder, name)
    temp_path = final_path + ".tmp"

    source = sqlite3.connect(db_file)
    target = sqlite3.connect(temp_path)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    os.replace(temp_path, final_path)
    print(f"[backup] created {final_path}", flush=True)
    return final_path


def list_backups(db_file):
    folder = backup_dir(db_file)
    if not os.path.isdir(folder):
        return []
    result = []
    for name in os.listdir(folder):
        if name.startswith("spending-") and name.endswith(".db"):
            path = os.path.join(folder, name)
            result.append({"name": name, "path": path, "modified": os.path.getmtime(path),
                           "size": os.path.getsize(path)})
    return sorted(result, key=lambda b: b["modified"], reverse=True)


def prune_backups(db_file, now=None):
    """Delete daily backups older than 14 days, but never the newest backup."""
    now = now or datetime.now()
    cutoff = (now - timedelta(days=DAILY_KEEP_DAYS)).timestamp()
    backups = list_backups(db_file)
    if not backups:
        return []
    newest = backups[0]["path"]
    deleted = []
    for b in backups:
        if b["path"] == newest:
            continue  # always keep at least one backup
        if b["name"].startswith("spending-daily-") and b["modified"] < cutoff:
            os.remove(b["path"])
            deleted.append(b["name"])
    for name in deleted:
        print(f"[backup] deleted old daily backup {name}", flush=True)
    return deleted


def daily_backup_if_needed(db_file):
    """Called on each request; does real work at most once per day."""
    global _last_daily_check
    today = datetime.now().date()
    if _last_daily_check == today:
        return
    with _lock:
        if _last_daily_check == today:
            return
        try:
            if not os.path.exists(db_file):
                return
            name = f"spending-daily-{today:%Y-%m-%d}.db"
            if not os.path.exists(os.path.join(backup_dir(db_file), name)):
                create_backup(db_file, "daily")
            prune_backups(db_file)
            _last_daily_check = today
        except (OSError, sqlite3.Error) as exc:
            # A failed backup must never take the app down; it retries next request.
            print(f"[backup] daily backup failed: {exc}", flush=True)
