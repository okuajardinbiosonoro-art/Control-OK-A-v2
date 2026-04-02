from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.services.remote_api_audit import (  # noqa: E402
    RemoteApiAuditWriter,
    build_remote_api_audit_event,
)


def test_remote_api_audit_writer_persists_jsonl_with_expected_fields(tmp_path: Path) -> None:
    writer = RemoteApiAuditWriter(folder=tmp_path / "audit", enabled=True)
    event = build_remote_api_audit_event(
        request_id="req_01",
        actor_type="technical_token",
        actor_id="remote_api_token:abcdef123456",
        role="tecnico",
        authorization_result="granted",
        token_label="tech-main",
        origin_remote_addr="127.0.0.1",
        origin_via="local_lan",
        http_method="GET",
        path="/api/v1/health",
        action="health.read",
        node_id=None,
        result="ok",
        status_code=200,
        session_state="idle",
        correlation_cmd_seq=42,
        correlation_nonce=777,
    )

    target = writer.write_event(event)

    assert target is not None
    assert target.exists()

    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["request_id"] == "req_01"
    assert payload["actor_id"] == "remote_api_token:abcdef123456"
    assert payload["role"] == "tecnico"
    assert payload["authorization_result"] == "granted"
    assert payload["token_label"] == "tech-main"
    assert payload["path"] == "/api/v1/health"
    assert payload["result"] == "ok"
    assert payload["correlation"]["cmd_seq"] == 42
    assert payload["correlation"]["nonce"] == 777
    assert "super-secret" not in lines[0]
