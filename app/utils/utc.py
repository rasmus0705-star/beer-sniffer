"""Helpers for timezone-safe UTC timestamps stored as naive database values."""
from datetime import datetime, timezone


def utcnow_naive():
    """Return current UTC time without tzinfo for existing DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
