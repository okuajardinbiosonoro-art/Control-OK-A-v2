from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Callable


REPO_DIR = Path(__file__).resolve().parent
SRC_DIR = REPO_DIR / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _load_run_app() -> Callable[[], int]:
    module = importlib.import_module("control_okua.app_qt.app")
    run_app = getattr(module, "run_app", None)
    if not callable(run_app):
        raise RuntimeError("No se encontro una funcion callable 'run_app'.")
    return run_app


if __name__ == "__main__":
    raise SystemExit(_load_run_app()())
