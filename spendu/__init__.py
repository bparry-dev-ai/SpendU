"""SpendU v2 — Flask JSON API + the built React app.

Layout:
    spendu/__init__.py   create_app(): config, security checks, blueprints
    spendu/db.py         database connection helpers
    spendu/migrations.py upgrades an existing database in place
    spendu/backups.py    automatic database backups
    spendu/auth.py       login, logout, passkeys (Face ID), rate limiting
    spendu/api/*.py      one file per feature (spending, bills, budgets, ...)
    frontend/            the React app (built into frontend/dist)
"""
import os
from datetime import timedelta

import click
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash

from . import backups, db, migrations
from .errors import ApiError

FRONTEND_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")


def create_app():
    load_dotenv()
    app = Flask(__name__, static_folder=None)

    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
    if not app.config["SECRET_KEY"]:
        raise RuntimeError("SECRET_KEY is not set. Add it to your .env file or docker environment.")
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)  # "Remember me"
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # CSV uploads up to 5 MB

    # Behind a reverse proxy (Nginx Proxy Manager, Tailscale serve, Cloudflare)
    # the real visitor IP arrives in X-Forwarded-For. Only trust it when told to,
    # otherwise anyone could fake their IP to dodge the login rate limit.
    if os.environ.get("TRUST_PROXY") == "1":
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    migrations.migrate(db.db_path())
    app.teardown_appcontext(db.close_db)

    from .api import register_blueprints
    from .auth import bp as auth_bp
    app.register_blueprint(auth_bp)
    register_blueprints(app)

    @app.before_request
    def before_request():
        if not request.path.startswith("/api/"):
            return None
        # CSRF protection: browsers can't add custom headers to cross-site
        # requests without permission, so requiring this header on every
        # change-making request blocks forged requests from other sites.
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("X-SpendU") != "1":
            return jsonify(error="Missing request header."), 400
        backups.daily_backup_if_needed(db.db_path())
        return None

    @app.errorhandler(ApiError)
    def handle_api_error(err):
        return jsonify(error=err.message), err.status

    @app.errorhandler(HTTPException)
    def handle_http_error(err):
        if request.path.startswith("/api/"):
            return jsonify(error=err.description), err.code
        return err

    @app.errorhandler(Exception)
    def handle_unexpected(err):
        app.logger.exception("Unhandled error")
        return jsonify(error="Something went wrong on the server. Check the logs."), 500

    # ---- The React app: any non-API path serves index.html ----
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def frontend(path):
        if path.startswith("api/"):
            return jsonify(error="Not found."), 404
        file_path = os.path.join(FRONTEND_DIST, path)
        if path and os.path.isfile(file_path):
            return send_from_directory(FRONTEND_DIST, path)
        if not os.path.isfile(os.path.join(FRONTEND_DIST, "index.html")):
            return ("Frontend not built. Run `npm run build` in frontend/, "
                    "or use `npm run dev` during development."), 503
        response = send_from_directory(FRONTEND_DIST, "index.html")
        response.headers["Cache-Control"] = "no-cache"
        return response

    register_cli(app)
    return app


def register_cli(app):
    @app.cli.command("create-user")
    def create_user():
        """Create a user, or reset an existing user's password."""
        username = click.prompt("Username").strip()
        password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
        if len(password) < 8:
            print("Password must be at least 8 characters.")
            return
        conn = db.connect()
        conn.execute(
            """INSERT INTO users (username, password_hash) VALUES (?, ?)
               ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash""",
            (username, generate_password_hash(password)),
        )
        migrations.adopt_unowned_rows(conn)
        conn.commit()
        conn.close()
        print(f"User '{username}' is ready to log in.")

    @app.cli.command("backup")
    def backup_now():
        """Take a manual backup right now."""
        path = backups.create_backup(db.db_path(), "manual")
        print(f"Backup written to {path}")

    @app.cli.command("list-backups")
    def list_backups():
        """Show the backups in the backups/ folder, newest first."""
        from datetime import datetime
        for b in backups.list_backups(db.db_path()):
            print(f"{datetime.fromtimestamp(b['modified']):%Y-%m-%d %H:%M}  {b['size'] // 1024:>6} KB  {b['name']}")
