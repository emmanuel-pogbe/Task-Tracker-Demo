from datetime import datetime, timezone

from config import TIME_FORMAT


def utc_now_str() -> str:
    """Current UTC time in the fixed storage format."""
    return datetime.now(timezone.utc).strftime(TIME_FORMAT)


def normalize_iso(value) -> str:
    """
    Convert an ISO-8601 string (with 'Z' or an offset, or naive = assumed UTC)
    into the fixed UTC storage format. Raises ValueError if invalid.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError("empty or non-string datetime")
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime(TIME_FORMAT)


def csv_safe(text: str) -> str:
    """Prefix a quote if the text could be run as a spreadsheet formula."""
    if text and text[0] in ("=", "+", "-", "@"):
        return "'" + text
    return text