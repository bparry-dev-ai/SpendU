"""Small helpers for returning errors and reading request input."""
from flask import request


class ApiError(Exception):
    """Raise this anywhere in an API view to send {"error": message} back."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def body():
    """The JSON body of the request (empty dict if none)."""
    return request.get_json(silent=True) or {}


def require(data, *fields):
    missing = [f for f in fields if data.get(f) in (None, "")]
    if missing:
        raise ApiError(f"Missing: {', '.join(missing)}.")


def to_int(value, field, required=True):
    if value in (None, ""):
        if required:
            raise ApiError(f"Missing: {field}.")
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ApiError(f"{field} must be a whole number.")


def to_amount(value, field="amount", allow_zero=False):
    try:
        amount = round(float(value), 2)
    except (TypeError, ValueError):
        raise ApiError(f"{field} must be a number.")
    if amount < 0 or (amount == 0 and not allow_zero):
        raise ApiError(f"{field} must be more than zero.")
    if amount > 1_000_000:
        raise ApiError(f"{field} looks too large.")
    return amount


def clean_text(value, max_len=200):
    text = (value or "").strip()
    return text[:max_len] or None
