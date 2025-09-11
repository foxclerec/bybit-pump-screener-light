# app/services/signals_service.py
from datetime import datetime
from app.models import Signal
from app.extensions import db

def fetch_last_for_index(limit: int = 5) -> list[dict]:
    """
    Returns the latest signals for the homepage (Jinja).
    Generates the exact keys that index.html expects:
    symbol, size, pct, window, price, time (HH:MM)
    """
    rows = (
        Signal.query
        .order_by(Signal.event_ts.desc())
        .limit(limit)
        .all()
    )

    out = []
    for r in rows:
        rule = getattr(r, "rule", None)
        out.append({
            "symbol": r.symbol,
            "rule_name": rule.name if rule else "?",
            "rule_color": rule.color if rule else None,
            "pct": round(abs(float(getattr(r, "change_pct", 0.0))), 2),
            "window": getattr(r, "window", None),
            "price": float(getattr(r, "price", 0.0) or 0.0),
            "time": r.event_ts.strftime("%H:%M") if getattr(r, "event_ts", None) else "",
        })
    return out

def fetch_last_rows(
    limit: int = 10,
    symbol: str | None = None,
    exchange: str | None = None,
    page: int = 1,
    per_page: int | None = None,
) -> tuple[list[Signal], int]:
    """Return recent signals filtered by watchlist/blacklist settings.

    Returns (rows, total_count) tuple for pagination.
    """
    from app.settings import get_setting

    q = Signal.query
    if exchange:
        q = q.filter(Signal.exchange == exchange)
    if symbol:
        q = q.filter(Signal.symbol == symbol)

    watchlist: list[str] = get_setting("watchlist", [])
    blacklist: list[str] = get_setting("blacklist", [])
    if watchlist:
        q = q.filter(Signal.symbol.in_(watchlist))
    if blacklist:
        q = q.filter(Signal.symbol.notin_(blacklist))

    q = q.order_by(Signal.event_ts.desc())
    total = q.count()

    effective_limit = per_page if per_page is not None else limit
    offset = (max(page, 1) - 1) * effective_limit
    rows = q.offset(offset).limit(effective_limit).all()

    return rows, total
