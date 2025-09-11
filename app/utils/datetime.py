# app/utils/datetime.py
from datetime import datetime, timezone

def to_iso_utc(dt: datetime | None) -> str | None:
    """Return ISO-8601 UTC string like 2025-09-12T13:22:05Z."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Treat naive datetime as UTC (adjust here if needed)
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")
