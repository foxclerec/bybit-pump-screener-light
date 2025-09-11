# app/blueprints/site/routes.py
from __future__ import annotations

from flask import Blueprint, render_template, jsonify, request, redirect, Response, stream_with_context
import re
from app.screener.signals import fetch_last_rows
from app.utils.datetime import to_iso_utc
from app.blueprints.site.settings_api import RULE_COLORS, _list_sounds
from app.constants import BYBIT_REFERRAL_CODE, NOWPAYMENTS_REFERRAL_URL

bp = Blueprint('site', __name__)


@bp.after_app_request
def inject_app_js(response):
    # Make sure app.js is present on every HTML page; add no-cache for HTML
    try:
        ct = (response.headers.get('Content-Type') or '').split(';')[0].strip().lower()
        if response.status_code == 200 and ct == 'text/html':
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            body = response.get_data(as_text=True)
            from app.constants import APP_VERSION
            has_helpers = 'static/js/helpers.js' in body
            has_app = 'static/js/app.js' in body
            tags = ''
            if not has_helpers:
                tags += f'<script src="/static/js/helpers.js?v={APP_VERSION}"></script>'
            if not has_app:
                tags += f'<script src="/static/js/app.js?v={APP_VERSION}" defer></script>'
            if tags:
                new_body = re.sub(r'</body\s*>', tags + '</body>', body, flags=re.IGNORECASE)
                if new_body != body:
                    response.set_data(new_body)
    except Exception:
        pass
    return response


@bp.get("/go/bybit/<symbol>")
def go_bybit(symbol: str):
    safe_sym = "".join(ch for ch in symbol.upper() if ch.isalnum())[:24]
    base = f"https://www.bybit.com/trade/usdt/{safe_sym}"
    ref = BYBIT_REFERRAL_CODE
    if ref:
        return redirect(f"{base}?ref={ref}", code=302)
    return redirect(base, code=302)


_EXCHANGE_REFERRAL_URLS: dict[str, str] = {
    "bybit": (
        f"https://www.bybit.com/invite?ref={BYBIT_REFERRAL_CODE}"
        if BYBIT_REFERRAL_CODE else "https://www.bybit.com"
    ),
}


@bp.get("/go/exchange/<name>")
def go_exchange(name: str):
    """Redirect to exchange registration page, with referral code if configured."""
    url = _EXCHANGE_REFERRAL_URLS.get(name.lower())
    if not url:
        return redirect("/", code=302)
    return redirect(url, code=302)


@bp.get("/go/nowpayments")
def go_nowpayments():
    """Redirect to NOWPayments via affiliate link."""
    return redirect(NOWPAYMENTS_REFERRAL_URL, code=302)

# -------- Pages --------
@bp.get('/')
def index():
    return render_template('index.html')


@bp.app_errorhandler(404)
def handle_404(e):
    return render_template('pages/404.html'), 404

@bp.get('/404')
def page_404():
    return render_template('pages/404.html'), 404

@bp.get('/privacy')
def privacy():
    return render_template('pages/privacy.html')

@bp.get('/terms')
def terms():
    return render_template('pages/terms.html')

@bp.get('/disclaimer')
def disclaimer():
    return render_template('pages/disclaimer.html')

@bp.get('/risk-disclosure')
def risk_disclosure():
    return redirect('/disclaimer', code=301)

@bp.get("/support-project")
def support_project():
    return render_template('pages/support-project.html')

@bp.get("/upgrade")
def upgrade():
    return render_template('pages/upgrade.html')

@bp.get('/donate')
def donate():
    return redirect('/support-project#donate', code=301)

@bp.get('/settings')
def settings():
    from app.models import DetectionRule
    from app.settings import TIMEZONES
    rules = DetectionRule.query.order_by(DetectionRule.sort_order).all()
    sounds = _list_sounds()
    return render_template('pages/settings.html', rules=rules, colors=RULE_COLORS, sounds=sounds, timezones=TIMEZONES)


# -------- Public API --------
@bp.get('/api/signals')
def api_signals():
    """Public JSON feed with pagination support."""
    from app.settings import get_setting

    page = max(int(request.args.get('page', 1)), 1)
    per_page = int(request.args.get('per_page', 0)) or get_setting('rows_per_page', 8)
    symbol = request.args.get('symbol') or None
    exchange = request.args.get('exchange') or None

    rows, total = fetch_last_rows(
        symbol=symbol, exchange=exchange, page=page, per_page=per_page,
    )
    signals = []
    for r in rows:
        rule = getattr(r, "rule", None)
        signals.append({
            "id": r.id,
            "exchange": r.exchange,
            "symbol": r.symbol,
            "rule_name": rule.name if rule else "?",
            "rule_label": r.rule_label or (f"{rule.threshold_pct:g}%/{rule.lookback_min}m" if rule else "?"),
            "rule_color": r.rule_color or (rule.color if rule else None),
            "pct": round(abs(float(getattr(r, "change_pct", 0.0))), 2),
            "window": getattr(r, "window", None),
            "price": getattr(r, "price", None),
            "event_ts": to_iso_utc(getattr(r, "event_ts", None)),
        })
    resp = jsonify({"signals": signals, "total": total, "page": page, "per_page": per_page})
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return resp


@bp.get('/api/signals/stream')
def api_signals_stream():
    """SSE stream — pushes new signals to the frontend in real time."""
    import json
    import time
    from app.models import Signal
    from app.extensions import db

    def generate():
        last_id = 0
        # Start from the latest signal
        latest = Signal.query.order_by(Signal.id.desc()).first()
        if latest:
            last_id = latest.id

        while True:
            time.sleep(1)
            try:
                db.session.remove()
                new_rows = (
                    Signal.query
                    .filter(Signal.id > last_id)
                    .order_by(Signal.id.asc())
                    .all()
                )
                for r in new_rows:
                    last_id = r.id
                    rule = getattr(r, "rule", None)
                    sig = {
                        "id": r.id,
                        "exchange": r.exchange,
                        "symbol": r.symbol,
                        "rule_name": rule.name if rule else "?",
                        "rule_label": r.rule_label or (f"{rule.threshold_pct:g}%/{rule.lookback_min}m" if rule else "?"),
                        "rule_color": r.rule_color or (rule.color if rule else None),
                        "pct": round(abs(float(getattr(r, "change_pct", 0.0))), 2),
                        "window": getattr(r, "window", None),
                        "price": getattr(r, "price", None),
                        "event_ts": to_iso_utc(getattr(r, "event_ts", None)),
                    }
                    yield f"data: {json.dumps(sig)}\n\n"
            except Exception:
                pass

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        },
    )


@bp.delete('/api/signals')
def api_clear_signals():
    """Clear all signals from the database."""
    from app.models import Signal, SignalDedup
    from app.extensions import db

    Signal.query.delete()
    SignalDedup.query.delete()
    db.session.commit()
    return jsonify({"ok": True})
