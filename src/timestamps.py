"""
QuickServe Legal - Timestamp Utilities

South African Standard Time (SAST = UTC+2) helpers for legal documents.
All timestamps stored in the database remain UTC, but display and legal
documents use SAST as required by the project specification.
"""

from datetime import datetime, timezone, timedelta

# South African Standard Time (UTC+2, no DST)
SAST = timezone(timedelta(hours=2), name="SAST")


def now_utc() -> datetime:
    """Return the current time as naive UTC (compatible with database datetimes).

    Non-deprecated replacement for the old utcnow pattern.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def now_sast() -> datetime:
    """Return the current time in SAST (UTC+2)."""
    return datetime.now(SAST)


def to_sast(dt: datetime) -> datetime:
    """
    Convert a UTC datetime to SAST-aware datetime.

    Args:
        dt: A datetime in UTC (naive or aware).

    Returns:
        Timezone-aware datetime in SAST.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(SAST)


def format_sast(utc_naive: datetime, fmt: str = "%d %B %Y at %H:%M:%S SAST") -> str:
    """
    Format a naive UTC datetime as a SAST string for display.

    Args:
        utc_naive: A datetime assumed to be UTC.
        fmt: strftime format string (default includes SAST suffix).

    Returns:
        Formatted string in SAST.
    """
    sast_dt = to_sast(utc_naive)
    return sast_dt.strftime(fmt)
