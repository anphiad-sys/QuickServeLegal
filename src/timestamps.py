"""
QuickServe Legal - Timestamp Utilities

South African Standard Time (SAST = UTC+2) helpers for legal documents.
All timestamps stored in the database remain UTC, but display and legal
documents use SAST as required by the project specification.
"""

from datetime import datetime, timezone, timedelta

# South African Standard Time (UTC+2, no DST)
SAST = timezone(timedelta(hours=2), name="SAST")


def now_sast() -> datetime:
    """Return the current time in SAST (UTC+2)."""
    return datetime.now(SAST)


def to_sast(utc_naive: datetime) -> datetime:
    """
    Convert a naive UTC datetime to SAST-aware datetime.

    Args:
        utc_naive: A datetime assumed to be UTC (as stored in the database).

    Returns:
        Timezone-aware datetime in SAST.
    """
    utc_aware = utc_naive.replace(tzinfo=timezone.utc)
    return utc_aware.astimezone(SAST)


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
