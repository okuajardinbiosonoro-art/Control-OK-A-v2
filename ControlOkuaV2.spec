# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
# Opcional (solo si quieres blindaje extra):
# from PyInstaller.utils.hooks import collect_submodules

PROJECT_DIR = Path(SPEC).resolve().parent

# Icono cross-platform del set de branding actual.
ICO_PATH = PROJECT_DIR / "assets" / "branding" / "okua_app_icon.ico"
PNG_PATH = PROJECT_DIR / "assets" / "branding" / "okua_icon_256.png"

if ICO_PATH.exists():
    ICON_FILE = ICO_PATH
elif PNG_PATH.exists():
    ICON_FILE = PNG_PATH
else:
    ICON_FILE = None

hiddenimports = [
    "control_okua.app_qt.app",
    "rtmidi",
    "mido.backends.rtmidi",
]

# Blindaje extra opcional (si alguna vez vuelve a molestar rtmidi en runtime):
# hiddenimports += collect_submodules("rtmidi")

a = Analysis(
    ["main.py"],
    pathex=[str(PROJECT_DIR / "src")],
    binaries=[],
    datas=[
        (str(PROJECT_DIR / "assets"), "assets"),
        (
            str(PROJECT_DIR / "src" / "control_okua" / "services" / "remote_console_assets"),
            "src/control_okua/services/remote_console_assets",
        ),
    ],
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
    [],
    exclude_binaries=True,
    name="Control OKÚA CKv2",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON_FILE) if ICON_FILE and ICON_FILE.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Control OKÚA CKv2",
)
