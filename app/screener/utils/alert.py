# app/screener/utils/alert.py
"""Cross-platform sound alert system with per-OS fallback chains.

Fallback order:
  Windows: winsound (WAV) -> MCI (MP3/WAV) -> winsound.Beep
  macOS:   afplay (all common formats) -> terminal bell
  Linux:   paplay -> pw-play -> aplay -> mpg123 -> ffplay -> terminal bell
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_SOUND_FILES: dict[str, Path] = {}
_recent_plays: list[float] = []     # monotonic timestamps of recent sound plays
_BURST_THRESHOLD = 3                # suppress after this many sounds in the window

# ---------------------------------------------------------------------------
# Asset helpers
# ---------------------------------------------------------------------------

def _assets_dir() -> Path:
    relative = Path(__file__).resolve().parents[1] / "assets"
    if relative.exists():
        return relative.resolve()
    # Frozen mode (PyInstaller): assets are under sys._MEIPASS
    if getattr(sys, "frozen", False):
        frozen = Path(sys._MEIPASS) / "app" / "screener" / "assets"
        if frozen.exists():
            return frozen.resolve()
    return relative.resolve()


def set_sound_files(rules_sounds: dict[str, str | None] | None = None) -> None:
    """Register sound files for detection rules.

    rules_sounds: {rule_name: filename_or_None}
    If None passed, registers a single default sound.
    """
    global _SOUND_FILES
    base = _assets_dir()
    _SOUND_FILES.clear()

    if not rules_sounds:
        rules_sounds = {"default": "pulse.wav"}

    for name, filename in rules_sounds.items():
        if not filename:
            continue
        path = (base / filename).resolve()
        if path.exists():
            _SOUND_FILES[name] = path
        else:
            logger.warning("[alert] %s: file not found: %s", name, path)


# ---------------------------------------------------------------------------
# Volume helper
# ---------------------------------------------------------------------------

def _get_volume() -> int:
    """Return sound volume 0-100 from DB setting. Default 80."""
    try:
        from app.settings import get_setting
        val = get_setting("sound_volume")
        if val is not None:
            return max(0, min(100, int(val)))
    except Exception:
        pass
    return 80


# ---------------------------------------------------------------------------
# Platform checks
# ---------------------------------------------------------------------------

def _is_windows() -> bool:
    return sys.platform == "win32"


def _is_mac() -> bool:
    return sys.platform == "darwin"


def _is_linux() -> bool:
    return sys.platform.startswith("linux")


# ---------------------------------------------------------------------------
# Subprocess helper — fire-and-forget (non-blocking)
# ---------------------------------------------------------------------------

def _popen(cmd: list[str]) -> bool:
    """Launch a subprocess and return immediately (fire-and-forget).

    Returns True if the process was launched successfully.
    """
    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Windows backends
# ---------------------------------------------------------------------------

def _play_winsound(path: Path, volume: int) -> bool:
    """Windows WAV playback via winsound (stdlib). Async flag = non-blocking."""
    if not _is_windows() or path.suffix.lower() != ".wav":
        return False
    try:
        import winsound
        # No SND_ASYNC here: blocking is correct because we're inside a daemon thread.
        # SND_ASYNC + daemon thread = sound cut off when thread exits.
        winsound.PlaySound(
            str(path),
            winsound.SND_FILENAME | winsound.SND_NODEFAULT,
        )
        return True
    except Exception as exc:
        logger.debug("[alert] winsound failed: %r", exc)
        return False


def _mci_alias(path: Path) -> str:
    """Unique MCI alias based on md5 of absolute path (no collision)."""
    digest = hashlib.md5(str(path).encode()).hexdigest()[:12]
    return f"ps_{digest}"


def _mci_close_later(alias: str, delay: float = 10.0) -> None:
    """Close MCI alias after a delay to prevent resource leaks."""
    def _closer():
        time.sleep(delay)
        try:
            import ctypes
            ctypes.windll.winmm.mciSendStringW(f"close {alias}", None, 0, None)
        except Exception:
            pass
    threading.Thread(target=_closer, daemon=True).start()


def _play_mci(path: Path, volume: int) -> bool:
    """Windows MCI: plays MP3 and WAV with volume control."""
    if not _is_windows():
        return False
    try:
        import ctypes
        mci = ctypes.windll.winmm.mciSendStringW
        alias = _mci_alias(path)

        # Close any previous instance of this alias
        mci(f"close {alias}", None, 0, None)

        # Try mpegvideo (MP3/WAV), fall back to waveaudio (WAV only)
        rc = mci(f'open "{path}" type mpegvideo alias {alias}', None, 0, None)
        if rc != 0:
            rc = mci(f'open "{path}" type waveaudio alias {alias}', None, 0, None)
            if rc != 0:
                return False

        # Volume: MCI scale is 0-1000
        mci_vol = int(volume * 10)
        mci(f"setaudio {alias} volume to {mci_vol}", None, 0, None)

        if mci(f"play {alias}", None, 0, None) != 0:
            mci(f"close {alias}", None, 0, None)
            return False

        # Schedule alias cleanup
        _mci_close_later(alias)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# macOS backend
# ---------------------------------------------------------------------------

def _play_afplay(path: Path, volume: int) -> bool:
    """macOS afplay with volume control. Pre-installed since OS X 10.5."""
    if not _is_mac():
        return False
    if shutil.which("afplay") is None:
        return False
    # afplay -v: 0.0 = silent, 1.0 = normal, >1.0 = amplified
    vol = round(volume / 100, 2)
    return _popen(["afplay", "-v", str(vol), str(path)])


# ---------------------------------------------------------------------------
# Linux backends
# ---------------------------------------------------------------------------

def _play_paplay(path: Path, volume: int) -> bool:
    """PulseAudio playback. Supports WAV, OGG, FLAC (not MP3)."""
    if not _is_linux():
        return False
    if shutil.which("paplay") is None:
        return False
    # paplay --volume: 0=silent, 65536=100%
    pa_vol = int(volume * 655.36)
    return _popen(["paplay", f"--volume={pa_vol}", str(path)])


def _play_pwplay(path: Path, volume: int) -> bool:
    """PipeWire playback (modern replacement for PulseAudio)."""
    if not _is_linux():
        return False
    if shutil.which("pw-play") is None:
        return False
    # pw-play --volume: float 0.0-1.0
    vol = round(volume / 100, 2)
    return _popen(["pw-play", f"--volume={vol}", str(path)])


def _play_aplay(path: Path) -> bool:
    """ALSA playback. WAV only, no volume control."""
    if not _is_linux():
        return False
    if path.suffix.lower() != ".wav":
        return False
    if shutil.which("aplay") is None:
        return False
    return _popen(["aplay", "-q", str(path)])


def _play_mpg123(path: Path, volume: int) -> bool:
    """mpg123 playback. MP3 only, with volume control."""
    if not _is_linux():
        return False
    if shutil.which("mpg123") is None:
        return False
    # mpg123 -f: scale factor, 32768 = 100%
    scale = int(volume * 327.68)
    return _popen(["mpg123", "-q", "-f", str(scale), str(path)])


def _play_ffplay(path: Path, volume: int) -> bool:
    """FFmpeg ffplay as universal fallback. Plays any format."""
    if not _is_linux():
        return False
    if shutil.which("ffplay") is None:
        return False
    # ffplay -volume: 0-100
    return _popen([
        "ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
        "-volume", str(volume), str(path),
    ])


# ---------------------------------------------------------------------------
# Terminal beep (last resort)
# ---------------------------------------------------------------------------

def _beep() -> None:
    """System beep as ultimate fallback."""
    try:
        if _is_windows():
            import winsound
            winsound.Beep(1200, 200)
        else:
            print("\a", end="", flush=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def _play(path: Optional[Path]) -> None:
    """Try all backends in platform-specific order. Never raises."""
    try:
        if not path or not path.exists():
            _beep()
            return

        volume = _get_volume()
        if volume <= 0:
            return

        if _is_windows():
            if _play_winsound(path, volume):
                return
            if _play_mci(path, volume):
                return

        elif _is_mac():
            if _play_afplay(path, volume):
                return

        elif _is_linux():
            if _play_paplay(path, volume):
                return
            if _play_pwplay(path, volume):
                return
            if _play_aplay(path):
                return
            if _play_mpg123(path, volume):
                return
            if _play_ffplay(path, volume):
                return

        _beep()
    except Exception as exc:
        logger.warning("[alert] playback error: %s", exc)
        try:
            _beep()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _sounds_enabled() -> bool:
    """Check if sounds are enabled via DB setting, env var, or default."""
    try:
        from app.settings import get_setting
        val = get_setting("sound_enabled")
        if val is not None:
            return bool(val)
    except Exception:
        pass
    return os.getenv("ENABLE_SOUNDS", "1") == "1"


def _get_cooldown() -> int:
    """Return alert cooldown in seconds from DB setting. Default 30."""
    try:
        from app.settings import get_setting, DEFAULTS
        val = get_setting("alert_cooldown_seconds",
                          DEFAULTS["alert_cooldown_seconds"])
        if val is not None:
            return max(0, int(val))
    except Exception:
        pass
    return 30


def play_alert(rule_name: str = "default") -> None:
    """Play an alert sound for a given rule. Non-blocking (daemon thread).

    Burst suppression: tracks how many sounds played within the
    ``alert_cooldown_seconds`` window.  Once the count reaches
    ``_BURST_THRESHOLD`` (3), further sounds are suppressed until
    the window clears.  Individual signals always play.
    Signals still appear in the table — only the sound is suppressed.
    """
    if not _sounds_enabled():
        logger.debug("[alert] Sounds disabled by config/env")
        return
    from app.screener.utils.tray import is_muted
    if is_muted():
        logger.debug("[alert] Muted via tray")
        return

    # Burst suppression: skip sound only during cascades
    cooldown = _get_cooldown()
    if cooldown > 0:
        now = time.monotonic()
        cutoff = now - cooldown
        # Trim timestamps outside the window
        _recent_plays[:] = [t for t in _recent_plays if t > cutoff]
        if len(_recent_plays) >= _BURST_THRESHOLD:
            logger.debug("[alert] Burst suppressed (%d sounds in %ds window)",
                         len(_recent_plays), cooldown)
            return
        _recent_plays.append(now)

    if not _SOUND_FILES:
        set_sound_files()
    snd = _SOUND_FILES.get(rule_name) or next(iter(_SOUND_FILES.values()), None)
    logger.debug("[alert] play_alert(%s) -> %s", rule_name, snd)
    threading.Thread(target=_play, args=(snd,), daemon=True).start()
