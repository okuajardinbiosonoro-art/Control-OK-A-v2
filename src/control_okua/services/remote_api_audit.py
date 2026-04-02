from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Lock


@dataclass(frozen=True)
class RemoteApiAuditEvent:
    ts_utc: str
    request_id: str
    actor_type: str
    actor_id: str
    origin_remote_addr: str
    origin_via: str
    http_method: str
    path: str
    action: str
    node_id: int | None
    result: str
    status_code: int
    session_state: str
    correlation_cmd_seq: int | None = None
    correlation_nonce: int | None = None

    def to_dict(self) -> dict[str, object | None]:
        return {
            "ts_utc": self.ts_utc,
            "request_id": self.request_id,
            "actor_type": self.actor_type,
            "actor_id": self.actor_id,
            "origin_remote_addr": self.origin_remote_addr,
            "origin_via": self.origin_via,
            "http_method": self.http_method,
            "path": self.path,
            "action": self.action,
            "node_id": self.node_id,
            "result": self.result,
            "status_code": self.status_code,
            "session_state": self.session_state,
            "correlation": {
                "cmd_seq": self.correlation_cmd_seq,
                "nonce": self.correlation_nonce,
            },
        }


class RemoteApiAuditWriter:
    def __init__(
        self,
        *,
        folder: Path | str,
        enabled: bool = True,
    ) -> None:
        self._folder = Path(folder)
        self._enabled = bool(enabled)
        self._lock = Lock()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def audit_path(self) -> Path:
        return self._folder / "remote_api.jsonl"

    def write_event(self, event: RemoteApiAuditEvent) -> Path | None:
        if not self._enabled:
            return None
        payload = event.to_dict()
        self._folder.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, ensure_ascii=False, sort_keys=False)
        target = self.audit_path
        with self._lock:
            with target.open("a", encoding="utf-8") as fobj:
                fobj.write(line)
                fobj.write("\n")
        return target


def build_remote_api_audit_event(
    *,
    request_id: str,
    actor_type: str,
    actor_id: str,
    origin_remote_addr: str,
    origin_via: str,
    http_method: str,
    path: str,
    action: str,
    node_id: int | None,
    result: str,
    status_code: int,
    session_state: str,
    correlation_cmd_seq: int | None = None,
    correlation_nonce: int | None = None,
) -> RemoteApiAuditEvent:
    return RemoteApiAuditEvent(
        ts_utc=_utc_now_iso(),
        request_id=str(request_id),
        actor_type=str(actor_type),
        actor_id=str(actor_id),
        origin_remote_addr=str(origin_remote_addr),
        origin_via=str(origin_via),
        http_method=str(http_method),
        path=str(path),
        action=str(action),
        node_id=None if node_id is None else int(node_id),
        result=str(result),
        status_code=int(status_code),
        session_state=str(session_state),
        correlation_cmd_seq=None if correlation_cmd_seq is None else int(correlation_cmd_seq),
        correlation_nonce=None if correlation_nonce is None else int(correlation_nonce),
    )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
