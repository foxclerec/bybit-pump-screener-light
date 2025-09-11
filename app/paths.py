# app/paths.py
"""Platform-aware path resolution for dev and frozen (PyInstaller) modes.

Dev mode:   instance/ folder (Flask default, current behavior).
Frozen mode: platform-standard directories via platformdirs.
    Windows:  %LOCALAPPDATA%\\PumpScreener\\
    macOS:    ~/Library/Application Support/PumpScreener/
    Linux:    ~/.local/share/PumpScreener/
"""

from __future__ import annotations

import secrets
import shutil
import sys
from pathlib import Path

_APP_NAME = "PumpScreener"


def is_frozen() -> bool:
    """True when running inside a PyInstaller bundle."""
    return getattr(sys, "frozen", False)


def get_data_dir() -> Path:
    """Return the writable data directory (DB, metrics)."""
    if is_frozen():
        from platformdirs import user_data_path
        return user_data_path(_APP_NAME, appauthor=False, ensure_exists=True)
    return Path("instance")


def get_or_create_secret_key(data_dir: Path) -> str:
    """Load or auto-generate a SECRET_KEY, persisted to *data_dir*/secret.key."""
    key_file = data_dir / "secret.key"
    if key_file.exists():
        key = key_file.read_text(encoding="utf-8").strip()
        if key:
            return key

    key = secrets.token_hex(32)
    data_dir.mkdir(parents=True, exist_ok=True)
    key_file.write_text(key, encoding="utf-8")
    return key


def migrate_instance_db(data_dir: Path) -> None:
    """One-time migration: copy instance/app.db to platform data dir."""
    old_db = Path("instance") / "app.db"
    new_db = data_dir / "app.db"
    if old_db.exists() and not new_db.exists():
        data_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old_db, new_db)
