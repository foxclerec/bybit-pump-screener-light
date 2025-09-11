# app/__init__.py
from __future__ import annotations
from dotenv import load_dotenv

from pathlib import Path
from datetime import timezone
from datetime import datetime
from flask import Flask, request, abort
from .extensions import db, migrate, csrf

# IMPORTANT: Load .env before importing Config
load_dotenv(override=False)
from .config import Config

def create_app() -> Flask:
    from .paths import is_frozen, get_data_dir, get_or_create_secret_key, migrate_instance_db

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)

    if is_frozen():
        # Bundled exe: use platform-standard data directory
        data_dir = get_data_dir()
        app.instance_path = str(data_dir)
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{data_dir / 'app.db'}"
        app.config["SECRET_KEY"] = get_or_create_secret_key(data_dir)
        migrate_instance_db(data_dir)
    else:
        # Dev mode: SECRET_KEY must come from .env
        if not app.config.get('SECRET_KEY'):
            raise RuntimeError('SECRET_KEY is not set. Provide it via environment or .env')

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    _ALLOWED_HOSTS = ("127.0.0.1", "localhost")
    _MUTATING_METHODS = ("POST", "PUT", "PATCH", "DELETE")

    @app.before_request
    def _validate_host():
        """Reject requests with non-localhost Host header (DNS rebinding protection)."""
        host = request.host.split(":")[0]
        if host not in _ALLOWED_HOSTS:
            abort(403)

    @app.before_request
    def _validate_origin():
        """Reject cross-origin mutating requests to JSON endpoints."""
        if request.method not in _MUTATING_METHODS:
            return
        origin = request.headers.get("Origin")
        if origin is None:
            return  # same-origin or non-browser client
        try:
            host_part = origin.split("//", 1)[1].split(":")[0]
        except (IndexError, ValueError):
            abort(403)
        if host_part not in _ALLOWED_HOSTS:
            abort(403)

    from .blueprints.site.routes import bp as site_bp
    from .blueprints.site.settings_api import bp as settings_api_bp
    from .blueprints.status import bp as status_bp
    app.register_blueprint(site_bp)
    app.register_blueprint(settings_api_bp)
    app.register_blueprint(status_bp, url_prefix="/api")

    @app.context_processor
    def inject_globals():
        from .constants import APP_VERSION, GITHUB_REPO_URL, SUPPORT_EMAIL, DONATION_URL, KOFI_URL, NOWPAYMENTS_REFERRAL_URL
        return {
            "current_year": datetime.now(timezone.utc).year,
            "utc_time": datetime.now(timezone.utc).strftime("%H:%M"),
            "site_title": app.config.get("SITE_TITLE", "Pump Alerts"),
            "app_version": f"v{APP_VERSION}",
            "github_repo_url": GITHUB_REPO_URL,
            "support_email": SUPPORT_EMAIL,
            "donation_url": DONATION_URL,
            "kofi_url": KOFI_URL,
            "nowpayments_referral_url": NOWPAYMENTS_REFERRAL_URL,
        }

    # Check for updates in background (non-blocking)
    from .services.update_checker import check_on_startup
    check_on_startup()

    @app.cli.command("init-db")
    def init_db():
        from .models import DetectionRule
        from .settings import seed_defaults
        with app.app_context():
            db.create_all()
            seed_defaults()
            if DetectionRule.query.count() == 0:
                db.session.add(DetectionRule(
                    name="Pump 2%/2m",
                    lookback_min=2,
                    threshold_pct=2.0,
                    color="#10b981",
                    sound_file="pulse.mp3",
                    sort_order=0,
                ))
                db.session.commit()
            print("DB initialized.")


    @app.cli.command("screener-run")
    def screener_run():
        from app.screener.runner import run_screener
        run_screener(app)

    @app.cli.command("prune-signals")
    def prune_signals():
        from datetime import timedelta
        from app.models import Signal
        with app.app_context():
            from app.constants import SIGNAL_PRUNE_HOURS
            cutoff = datetime.now(timezone.utc) - timedelta(hours=SIGNAL_PRUNE_HOURS)
            deleted = Signal.query.filter(Signal.event_ts < cutoff).delete()
            db.session.commit()
            print(f"pruned {deleted} signals older than 72h")

    return app
