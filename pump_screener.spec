# pump_screener.spec
# -*- mode: python ; coding: utf-8 -*-
#
# Cross-platform PyInstaller spec for Pump Screener (onedir, windowed).
#
# Build:
#   pyinstaller pump_screener.spec
#
# Output:
#   dist/PumpScreener/PumpScreener[.exe]

import sys
from pathlib import Path

ROOT = Path(SPECPATH)

# --- Platform-specific hidden imports ---
_hidden_common = [
    # pywebview
    'webview',
    'bottle',
    'proxy_tools',

    # Flask ecosystem
    'flask.json',
    'jinja2.ext',

    # SQLAlchemy
    'sqlalchemy.dialects.sqlite',

    # Pillow (tray icon rendering)
    'PIL._tkinter_finder',

    # Bybit SDK + WebSocket
    'pybit',
    'websocket',

    # Platform paths (frozen mode)
    'platformdirs',

    # httpx transport
    'httpx',
    'httpcore',
    'h11',
    'anyio',
    'sniffio',
    'certifi',
    'idna',
]

_hidden_platform = {
    'win32': [
        'clr',              # pythonnet for WebView2
        'pythonnet',
        'pystray._win32',
    ],
    'darwin': [
        'pystray._darwin',
    ],
    'linux': [
        'pystray._xorg',
    ],
}

hiddenimports = _hidden_common + _hidden_platform.get(sys.platform, [])

# --- Icon ---
_icon_path = ROOT / 'app' / 'static' / 'favicon' / 'favicon.ico'
# macOS needs .icns; if not present, skip icon (PyInstaller will use default)
if sys.platform == 'darwin':
    _icns = ROOT / 'app' / 'static' / 'favicon' / 'favicon.icns'
    icon_file = str(_icns) if _icns.exists() else None
else:
    icon_file = str(_icon_path) if _icon_path.exists() else None

# --- Analysis ---
a = Analysis(
    [str(ROOT / 'main.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        ('app/templates', 'app/templates'),
        ('app/static', 'app/static'),
        ('app/screener/assets', 'app/screener/assets'),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'unittest',
        'test',
        'pytest',
        'setuptools',
        'pip',
        'numpy',
        'pandas',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PumpScreener',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='PumpScreener',
)
