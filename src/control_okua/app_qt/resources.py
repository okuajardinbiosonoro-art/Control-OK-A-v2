"""Helpers para resolver recursos en desarrollo y en build PyInstaller."""

from __future__ import annotations

from pathlib import Path
import sys


def project_root() -> Path:
    """Retorna la carpeta base del proyecto (dev) o base de bundle (frozen)."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass).resolve()
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parents[3]


def resource_path(relative: str) -> Path:
    """Resuelve una ruta de recurso para dev/frozen."""
    meipass = getattr(sys, "_MEIPASS", None)
    base = Path(meipass).resolve() if meipass else project_root()
    return (base / relative).resolve()


def load_qss(path: Path) -> str:
    """Lee una hoja QSS UTF-8."""
    return path.read_text(encoding="utf-8")


def app_icon_path() -> Path:
    """Prefiere el set de branding actual y cae a legados solo si hace falta."""
    candidates = (
        "assets/branding/okua_app_icon.ico",
        "assets/branding/okua_icon_256.png",
        "assets/branding/okua_icon_128.png",
        "assets/branding/okua_icon_64.png",
        "assets/icons/app_icon.ico",
        "assets/icons/app_icon.png",
    )
    for relative in candidates:
        candidate = resource_path(relative)
        if candidate.exists():
            return candidate
    return resource_path("assets/branding/okua_app_icon.ico")
