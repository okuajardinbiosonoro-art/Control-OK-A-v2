from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.control_plane.auth import (  # noqa: E402
    CONTROL_SECRET_ENV,
    CONTROL_SECRET_FILE_ENV,
    ControlSecretNotConfiguredError,
    resolve_control_secret,
)


def test_resolve_control_secret_prefers_env_over_auto_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_header = tmp_path / "okua_node_secrets.h"
    secret_header.write_text(
        '#define OKUA_CONTROL_SECRET "FILE_SECRET_123"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "control_okua.core.control_plane.auth._iter_default_secret_candidates",
        lambda: (secret_header,),
    )
    monkeypatch.setenv(CONTROL_SECRET_ENV, "ENV_SECRET_456")
    monkeypatch.delenv(CONTROL_SECRET_FILE_ENV, raising=False)

    resolved = resolve_control_secret()
    assert resolved == b"ENV_SECRET_456"


def test_resolve_control_secret_uses_auto_firmware_secret_header(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_header = tmp_path / "okua_node_secrets.h"
    secret_header.write_text(
        '#define OKUA_CONTROL_SECRET "OKUA_TEST_SECRET_2026"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "control_okua.core.control_plane.auth._iter_default_secret_candidates",
        lambda: (secret_header,),
    )
    monkeypatch.delenv(CONTROL_SECRET_ENV, raising=False)
    monkeypatch.delenv(CONTROL_SECRET_FILE_ENV, raising=False)

    resolved = resolve_control_secret()
    assert resolved == b"OKUA_TEST_SECRET_2026"


def test_resolve_control_secret_rejects_placeholder_from_auto_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_header = tmp_path / "okua_node_secrets.h"
    secret_header.write_text(
        '#define OKUA_CONTROL_SECRET "CHANGE_ME_CONTROL_SECRET"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "control_okua.core.control_plane.auth._iter_default_secret_candidates",
        lambda: (secret_header,),
    )
    monkeypatch.delenv(CONTROL_SECRET_ENV, raising=False)
    monkeypatch.delenv(CONTROL_SECRET_FILE_ENV, raising=False)

    with pytest.raises(ControlSecretNotConfiguredError):
        resolve_control_secret()

