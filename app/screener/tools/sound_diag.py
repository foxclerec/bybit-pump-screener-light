# app/screener/tools/sound_diag.py
"""Sound diagnostic tool — tests every backend individually with visual report."""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

import os as _os

# Windows cmd.exe needs UTF-8 mode for unicode symbols
if sys.platform == "win32":
    _os.system("")  # enable ANSI escape sequences on Windows 10+

# Use ASCII-safe symbols that work on all terminals including cp1252
OK = "\033[92m[OK]\033[0m"     # green
FAIL = "\033[91m[FAIL]\033[0m" # red
SKIP = "\033[90m[--]\033[0m"   # grey
BOLD = "\033[1m"
RESET = "\033[0m"

assets = Path(__file__).parents[1] / "assets"


def _find_wav() -> Path | None:
    for name in ("pulse.wav", "boom.wav"):
        p = assets / name
        if p.exists():
            return p
    return None


def _find_mp3() -> Path | None:
    for name in ("pulse.mp3", "boom.mp3"):
        p = assets / name
        if p.exists():
            return p
    return None


def _header(text: str) -> None:
    print(f"\n{BOLD}{'=' * 50}")
    print(f"  {text}")
    print(f"{'=' * 50}{RESET}\n")


def _test(name: str, fn, *args) -> bool:
    """Run a backend test, print result, return success."""
    try:
        result = fn(*args)
        if result:
            print(f"  {OK}  {name}")
            return True
        else:
            print(f"  {FAIL}  {name}")
            return False
    except Exception as e:
        print(f"  {FAIL}  {name}  ({e!r})")
        return False


def main() -> None:
    _header("SOUND DIAGNOSTIC")

    print(f"  Platform:   {sys.platform}")
    print(f"  Assets dir: {assets}")
    print()

    wav = _find_wav()
    mp3 = _find_mp3()
    print(f"  WAV file:   {wav.name if wav else 'NOT FOUND'}")
    print(f"  MP3 file:   {mp3.name if mp3 else 'NOT FOUND'}")

    if not wav and not mp3:
        print(f"\n  {FAIL}  No sound files found in {assets}. Aborting.")
        raise SystemExit(1)

    # ── Volume setting ──
    try:
        from app.screener.utils.alert import _get_volume
        vol = _get_volume()
    except Exception:
        vol = 80
    print(f"  Volume:     {vol}%")

    # ── CLI tools availability ──
    _header("CLI TOOLS")
    tools = ["afplay", "paplay", "pw-play", "aplay", "mpg123", "ffplay"]
    for tool in tools:
        found = shutil.which(tool)
        mark = OK if found else FAIL
        print(f"  {mark}  {tool}")

    # ── Backend tests ──
    _header("BACKEND TESTS (listen for sound)")

    from app.screener.utils.alert import (
        _play_winsound, _play_mci,
        _play_afplay,
        _play_paplay, _play_pwplay, _play_aplay, _play_mpg123, _play_ffplay,
        _beep,
    )

    results: list[tuple[str, bool]] = []
    pause = 1.5  # seconds between tests

    # -- Windows backends --
    if sys.platform == "win32":
        print(f"  {BOLD}Windows backends:{RESET}")
        if wav:
            ok = _test("winsound (WAV)", _play_winsound, wav, vol)
            results.append(("winsound (WAV)", ok))
            if ok:
                time.sleep(pause)

            ok = _test("MCI (WAV)", _play_mci, wav, vol)
            results.append(("MCI (WAV)", ok))
            if ok:
                time.sleep(pause)

        if mp3:
            ok = _test("MCI (MP3)", _play_mci, mp3, vol)
            results.append(("MCI (MP3)", ok))
            if ok:
                time.sleep(pause)
    else:
        print(f"  {SKIP}  winsound — skipped (not Windows)")
        print(f"  {SKIP}  MCI — skipped (not Windows)")

    # -- macOS backends --
    if sys.platform == "darwin":
        print(f"\n  {BOLD}macOS backends:{RESET}")
        snd = wav or mp3
        if snd:
            ok = _test("afplay", _play_afplay, snd, vol)
            results.append(("afplay", ok))
            if ok:
                time.sleep(pause)
    else:
        print(f"\n  {SKIP}  afplay — skipped (not macOS)")

    # -- Linux backends --
    if sys.platform.startswith("linux"):
        print(f"\n  {BOLD}Linux backends:{RESET}")
        if wav:
            ok = _test("paplay (WAV)", _play_paplay, wav, vol)
            results.append(("paplay", ok))
            if ok:
                time.sleep(pause)

            ok = _test("pw-play (WAV)", _play_pwplay, wav, vol)
            results.append(("pw-play", ok))
            if ok:
                time.sleep(pause)

            ok = _test("aplay (WAV)", _play_aplay, wav)
            results.append(("aplay", ok))
            if ok:
                time.sleep(pause)

        if mp3:
            ok = _test("mpg123 (MP3)", _play_mpg123, mp3, vol)
            results.append(("mpg123", ok))
            if ok:
                time.sleep(pause)

        snd = wav or mp3
        if snd:
            ok = _test("ffplay", _play_ffplay, snd, vol)
            results.append(("ffplay", ok))
            if ok:
                time.sleep(pause)
    else:
        print(f"\n  {SKIP}  paplay — skipped (not Linux)")
        print(f"  {SKIP}  pw-play — skipped (not Linux)")
        print(f"  {SKIP}  aplay — skipped (not Linux)")
        print(f"  {SKIP}  mpg123 — skipped (not Linux)")
        print(f"  {SKIP}  ffplay — skipped (not Linux)")

    # -- Terminal beep (all platforms) --
    print(f"\n  {BOLD}Universal fallback:{RESET}")
    try:
        _beep()
        print(f"  {OK}  system beep")
        results.append(("system beep", True))
    except Exception:
        print(f"  {FAIL}  system beep")
        results.append(("system beep", False))

    # ── Summary ──
    _header("SUMMARY")

    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    failed = total - passed

    for name, ok in results:
        mark = OK if ok else FAIL
        print(f"  {mark}  {name}")

    print()
    if passed == 0:
        print(f"  {FAIL}  {BOLD}NO working backend found!{RESET}")
        print(f"      Sound alerts will NOT work on this system.")
    elif failed > 0:
        print(f"  {OK}  {passed}/{total} backends working — sound alerts will work")
        print(f"      Primary backend: {results[0][0] if results[0][1] else next((n for n, ok in results if ok), '???')}")
    else:
        print(f"  {OK}  All {total} backends working — sound system is bulletproof")

    print()


if __name__ == "__main__":
    main()
