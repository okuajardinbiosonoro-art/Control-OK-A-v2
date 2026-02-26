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
    """Prefiere ICO y cae a PNG si no existe."""
    ico = resource_path("assets/icons/app_icon.ico")
    if ico.exists():
        return ico

    png = resource_path("assets/icons/app_icon.png")
    return png
