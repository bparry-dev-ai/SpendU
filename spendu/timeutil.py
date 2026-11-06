"""Date helpers. All dates are stored as 'YYYY-MM-DD' text, months as 'YYYY-MM'.

"Today" depends on the signed-in user's timezone setting (Settings page),
so it stays correct when the server is in one country and you are in another.
"""
import calendar
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def default_timezone():
    return os.environ.get("DEFAULT_TIMEZONE") or os.environ.get("TZ") or "Europe/London"


def valid_timezone(name):
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return False


def today_for(tz_name):
    tz_name = tz_name if tz_name and valid_timezone(tz_name) else default_timezone()
    return datetime.now(ZoneInfo(tz_name)).date()


def parse_date(text):
    """'YYYY-MM-DD' -> date, or None if it isn't a valid date."""
    try:
        return datetime.strptime(str(text), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def parse_month(text):
    """'YYYY-MM' -> (year, month), or None."""
    try:
        d = datetime.strptime(str(text), "%Y-%m")
        return d.year, d.month
    except (ValueError, TypeError):
        return None


def month_str(d):
    return f"{d.year:04d}-{d.month:02d}"


def month_bounds(year, month):
    """First and last day of a month as 'YYYY-MM-DD' strings."""
    last = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last:02d}"


def shift_month(year, month, delta):
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def day_in_month(year, month, day):
    """Clamp a day to the month: a bill due on the 31st is due on Feb 28/29."""
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def advance(d, frequency, anchor_day):
    """Next occurrence after date d for a recurring item."""
    if frequency == "weekly":
        return d + timedelta(days=7)
    months = 12 if frequency == "yearly" else 1
    y, m = shift_month(d.year, d.month, months)
    return day_in_month(y, m, anchor_day or d.day)
