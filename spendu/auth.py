"""Sign-in: password login, passkeys (Face ID), rate limiting, settings.

Accounts are still created only from the command line:
    flask --app spendu create-user
"""
import os
import time
from functools import wraps

from flask import Blueprint, g, jsonify, request, session
from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db, to_dicts
from .errors import ApiError, body
from .timeutil import default_timezone, today_for, valid_timezone

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# Rate limiting: after this many failed logins inside the window, further
# attempts are refused until old failures age out.
FAIL_WINDOW_SECONDS = 15 * 60
MAX_FAILS_PER_USERNAME = 5
MAX_FAILS_PER_IP = 20


# ---------------------------------------------------------------------------
# Helpers used by every other API file
# ---------------------------------------------------------------------------
def login_required(view):
    """Only signed-in users may call this view. Loads the user into g.user."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        user_id = session.get("user_id")
        if user_id is None:
            return jsonify(error="Please sign in."), 401
        user = get_db().execute(
            "SELECT user_id, username, timezone FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if user is None:
            session.clear()
            return jsonify(error="Please sign in."), 401
        g.user = dict(user)
        return view(*args, **kwargs)
    return wrapped


def uid():
    return g.user["user_id"]


def today():
    """Today's date in the signed-in user's timezone."""
    return today_for(g.user.get("timezone"))


def user_payload(conn, user):
    family = conn.execute("SELECT user_id, username FROM users ORDER BY user_id").fetchall()
    return {
        "user": {
            "user_id": user["user_id"],
            "username": user["username"],
            "timezone": user["timezone"] or default_timezone(),
        },
        "family": to_dicts(family),
        "today": str(today_for(user["timezone"])),
    }


def _start_session(user_id, remember):
    session.clear()
    session["user_id"] = user_id
    session.permanent = bool(remember)  # permanent = 30 days, else until browser closes


# ---------------------------------------------------------------------------
# Rate limiting (stored in the database so it survives restarts)
# ---------------------------------------------------------------------------
def _too_many_attempts(conn, ip, username):
    since = time.time() - FAIL_WINDOW_SECONDS
    conn.execute("DELETE FROM login_attempts WHERE attempted_at < ?", (since,))
    by_user = conn.execute(
        "SELECT COUNT(*) FROM login_attempts WHERE username = ? AND attempted_at >= ?",
        (username.lower(), since),
    ).fetchone()[0]
    by_ip = conn.execute(
        "SELECT COUNT(*) FROM login_attempts WHERE ip = ? AND attempted_at >= ?", (ip, since)
    ).fetchone()[0]
    return by_user >= MAX_FAILS_PER_USERNAME or by_ip >= MAX_FAILS_PER_IP


def _record_failure(conn, ip, username):
    conn.execute(
        "INSERT INTO login_attempts (ip, username, attempted_at) VALUES (?, ?, ?)",
        (ip, username.lower(), time.time()),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Password login
# ---------------------------------------------------------------------------
@bp.get("/me")
@login_required
def me():
    return user_payload(get_db(), g.user)


@bp.post("/login")
def login():
    data = body()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    ip = request.remote_addr or "unknown"
    conn = get_db()

    if _too_many_attempts(conn, ip, username):
        conn.commit()
        raise ApiError("Too many failed attempts. Wait 15 minutes and try again.", 429)

    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    # Same message whether the username or the password was wrong.
    if user is None or not check_password_hash(user["password_hash"], password):
        _record_failure(conn, ip, username)
        raise ApiError("Invalid username or password.", 401)

    conn.execute("DELETE FROM login_attempts WHERE username = ?", (username.lower(),))
    conn.commit()
    _start_session(user["user_id"], data.get("remember", True))
    return user_payload(conn, user)


@bp.post("/logout")
def logout():
    session.clear()
    return {"ok": True}


@bp.post("/password")
@login_required
def change_password():
    data = body()
    conn = get_db()
    row = conn.execute("SELECT password_hash FROM users WHERE user_id = ?", (g.user["user_id"],)).fetchone()
    if not check_password_hash(row["password_hash"], data.get("current") or ""):
        raise ApiError("Your current password is wrong.")
    new = data.get("new") or ""
    if len(new) < 8:
        raise ApiError("The new password must be at least 8 characters.")
    conn.execute("UPDATE users SET password_hash = ? WHERE user_id = ?",
                 (generate_password_hash(new), g.user["user_id"]))
    conn.commit()
    return {"ok": True}


@bp.patch("/settings")
@login_required
def update_settings():
    data = body()
    tz = data.get("timezone")
    if tz is not None:
        if not valid_timezone(tz):
            raise ApiError("Unknown timezone.")
        conn = get_db()
        conn.execute("UPDATE users SET timezone = ? WHERE user_id = ?", (tz, g.user["user_id"]))
        conn.commit()
        g.user["timezone"] = tz
    return user_payload(get_db(), g.user)


# ---------------------------------------------------------------------------
# Passkeys (Face ID / Touch ID via WebAuthn) — same behaviour as v1.2
# ---------------------------------------------------------------------------
def get_rp_id():
    """The domain passkeys are bound to. Override with RP_ID behind a proxy."""
    return os.environ.get("RP_ID") or request.host.split(":")[0]


def get_rp_origin():
    """The origin the browser reports. Override with RP_ORIGIN behind a
    proxy/tunnel, where Flask sees http but the browser is on https."""
    return os.environ.get("RP_ORIGIN") or f"{request.scheme}://{request.host}"


@bp.get("/passkeys")
@login_required
def list_passkeys():
    rows = get_db().execute(
        "SELECT credential_id, created FROM passkeys WHERE user_id = ? ORDER BY created",
        (g.user["user_id"],),
    ).fetchall()
    return {"passkeys": to_dicts(rows)}


@bp.delete("/passkeys/<path:credential_id>")
@login_required
def delete_passkey(credential_id):
    conn = get_db()
    conn.execute("DELETE FROM passkeys WHERE credential_id = ? AND user_id = ?",
                 (credential_id, g.user["user_id"]))
    conn.commit()
    return {"ok": True}


@bp.post("/passkey/register/begin")
@login_required
def passkey_register_begin():
    existing = get_db().execute(
        "SELECT credential_id FROM passkeys WHERE user_id = ?", (g.user["user_id"],)
    ).fetchall()
    options = generate_registration_options(
        rp_id=get_rp_id(),
        rp_name="SpendU",
        user_name=g.user["username"],
        user_id=str(g.user["user_id"]).encode(),
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(row["credential_id"])) for row in existing
        ],
    )
    session["reg_challenge"] = bytes_to_base64url(options.challenge)
    return options_to_json(options), 200, {"Content-Type": "application/json"}


@bp.post("/passkey/register/complete")
@login_required
def passkey_register_complete():
    challenge_b64 = session.pop("reg_challenge", None)
    if not challenge_b64:
        raise ApiError("No registration in progress.")
    try:
        verification = verify_registration_response(
            credential=request.get_json(),
            expected_challenge=base64url_to_bytes(challenge_b64),
            expected_rp_id=get_rp_id(),
            expected_origin=get_rp_origin(),
            require_user_verification=True,
        )
    except Exception:
        raise ApiError("Passkey registration failed.")
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO passkeys (credential_id, user_id, public_key, sign_count) VALUES (?, ?, ?, ?)",
        (bytes_to_base64url(verification.credential_id), g.user["user_id"],
         verification.credential_public_key, verification.sign_count),
    )
    conn.commit()
    return {"ok": True}


@bp.post("/passkey/login/begin")
def passkey_login_begin():
    options = generate_authentication_options(
        rp_id=get_rp_id(), user_verification=UserVerificationRequirement.REQUIRED,
    )
    session["auth_challenge"] = bytes_to_base64url(options.challenge)
    return options_to_json(options), 200, {"Content-Type": "application/json"}


@bp.post("/passkey/login/complete")
def passkey_login_complete():
    challenge_b64 = session.pop("auth_challenge", None)
    if not challenge_b64:
        raise ApiError("No sign-in in progress.")
    data = body()
    credential = data.get("credential")
    if not credential or "id" not in credential:
        raise ApiError("Malformed passkey response.")

    conn = get_db()
    row = conn.execute("SELECT * FROM passkeys WHERE credential_id = ?", (credential["id"],)).fetchone()
    if row is None:
        raise ApiError("Unknown passkey.")
    try:
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(challenge_b64),
            expected_rp_id=get_rp_id(),
            expected_origin=get_rp_origin(),
            credential_public_key=row["public_key"],
            credential_current_sign_count=row["sign_count"],
            require_user_verification=True,
        )
    except Exception:
        raise ApiError("Passkey sign-in failed.")
    conn.execute("UPDATE passkeys SET sign_count = ? WHERE credential_id = ?",
                 (verification.new_sign_count, credential["id"]))
    conn.commit()

    _start_session(row["user_id"], data.get("remember", True))
    user = conn.execute("SELECT user_id, username, timezone FROM users WHERE user_id = ?",
                        (row["user_id"],)).fetchone()
    return user_payload(conn, user)
