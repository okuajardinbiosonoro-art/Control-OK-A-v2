# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
# Opcional (solo si quieres blindaje extra):
# from PyInstaller.utils.hooks import collect_submodules

PROJECT_DIR = Path(SPEC).resolve().parent

# Icono cross-platform (prefiere .ico, fallback .png, o None si no existe)
ICO_PATH = PROJECT_DIR / "assets" / "icons" / "app_icon.ico"
PNG_PATH = PROJECT_DIR / "assets" / "icons" / "app_icon.png"

if ICO_PATH.exists():
    ICON_FILE = ICO_PATH
elif PNG_PATH.exists():
    ICON_FILE = PNG_PATH
else:
    ICON_FILE = None

hiddenimports = [
    "rtmidi",
    "mido.backends.rtmidi",
]

# Blindaje extra opcional (si alguna vez vuelve a molestar rtmidi en runtime):
# hiddenimports += collect_submodules("rtmidi")

a = Analysis(
    ["main.py"],
    pathex=[str(PROJECT_DIR / "src")],
    binaries=[],
    datas=[(str(PROJECT_DIR / "assets"), "assets")],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Control Okua",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON_FILE) if ICON_FILE and ICON_FILE.exists() else None,
)
