from __future__ import annotations

import sys
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parent
SRC_DIR = REPO_DIR / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.app_qt.app import run_app


if __name__ == "__main__":
    raise SystemExit(run_app())
