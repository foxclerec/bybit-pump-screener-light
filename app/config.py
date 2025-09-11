# app/config.py
import os

class Config:
    # Secrets and sensitive values must come from environment/.env
    SECRET_KEY = os.environ.get('SECRET_KEY')  # REQUIRED
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    ENABLE_SOUNDS = os.getenv("ENABLE_SOUNDS", "1") == "1"

    SEND_FILE_MAX_AGE_DEFAULT = 0  # no browser caching for static files
    TEMPLATES_AUTO_RELOAD = True

    SITE_TITLE = os.environ.get('SITE_TITLE', 'Pump Alerts')
    # APP_VERSION lives in constants.py (single source of truth)
