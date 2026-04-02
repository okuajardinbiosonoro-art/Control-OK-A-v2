from __future__ import annotations

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import mimetypes
import os
from pathlib import Path
from threading import Thread
import time
from typing import Any, Protocol
from urllib.parse import urlparse
import secrets

from control_okua.core.control_plane.runtime import (
    ControlPlaneNodeResolutionError,
    ControlPlaneRuntimeSnapshot,
    ControlPlaneRuntimeUnavailableError,
)
from control_okua.core.control_plane.runtime_snapshot import (
    ControlPlaneNodeResolutionStatus,
    ControlPlaneNodeSnapshot,
)
from control_okua.core.registry.node_models import NodeRegistrySummary, NodeSnapshot
from control_okua.core.session import SessionSnapshot, SessionState
from control_okua.services.control_transaction_service import (
    ControlTransactionFinalStatus,
    ControlTransactionResult,
)
from control_okua.services.remote_api_audit import (
    RemoteApiAuditWriter,
    build_remote_api_audit_event,
)
from control_okua.services.remote_api_auth import (
    RemoteApiAuthConfigError,
    RemoteApiAuthContext,
    RemoteApiForbiddenError,
    RemoteApiTokenBinding,
    RemoteApiUnauthorizedError,
    authenticate_bearer_request,
    authorize_remote_api_action,
    resolve_remote_api_token_bindings,
)
from control_okua.services.remote_api_contract import (
    RemoteApiConfig,
    RemoteApiError,
    build_error_response,
    build_success_response,
    serialize_control_plane_node_detail,
    serialize_control_plane_summary,
    serialize_control_transaction_result,
    serialize_node_detail,
    serialize_node_registry_summary,
    serialize_node_summary,
    serialize_session_snapshot,
)


class RemoteApiServiceError(RuntimeError):
    """Base error for the local remote API service."""


class RemoteApiRuntimeClient(Protocol):
    def get_snapshot(self) -> SessionSnapshot:
        ...

    def get_node_registry_summary(self, now: float | None = None) -> NodeRegistrySummary | None:
        ...

    def get_node_snapshots(self, now: float | None = None) -> list[NodeSnapshot]:
        ...

    def get_node_snapshot(self, node_id: int, now: float | None = None) -> NodeSnapshot | None:
        ...

    def is_control_plane_available(self) -> bool:
        ...

    def get_control_plane_runtime_snapshot(self) -> ControlPlaneRuntimeSnapshot:
        ...

    def get_control_plane_node_snapshots(self, now: float | None = None) -> list[ControlPlaneNodeSnapshot]:
        ...

    def get_control_plane_node_snapshot(
        self,
        node_id: int,
        now: float | None = None,
    ) -> ControlPlaneNodeSnapshot | None:
        ...

    def send_control_request_stat_now(
        self,
        *,
        node_id: int,
        ack_timeout_ms: int = 350,
        max_retries: int = 1,
        source: str = "remote_api",
    ) -> ControlTransactionResult:
        ...

    def send_control_reboot_soft(
        self,
        *,
        node_id: int,
        delay_ms: int = 0,
        ack_timeout_ms: int = 350,
        max_retries: int = 1,
        source: str = "remote_api",
    ) -> ControlTransactionResult:
        ...


@dataclass(frozen=True)
class _RequestAuditOutcome:
    actor_type: str
    actor_id: str
    action: str
    node_id: int | None
    result: str
    status_code: int
    role: str | None = None
    authorization_result: str | None = None
    token_label: str | None = None
    correlation_cmd_seq: int | None = None
    correlation_nonce: int | None = None


class _RemoteApiHttpServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], service: "RemoteApiService") -> None:
        self.remote_api_service = service
        super().__init__(server_address, _RemoteApiRequestHandler)


class _RemoteApiRequestHandler(BaseHTTPRequestHandler):
    server_version = "CKV2RemoteApi/1.0"
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802
        self.server.remote_api_service.handle_http_request(self)

    def do_POST(self) -> None:  # noqa: N802
        self.server.remote_api_service.handle_http_request(self)

    def log_message(self, format: str, *args) -> None:
        self.server.remote_api_service.logger.info(
            "Remote API %s - %s",
            self.address_string(),
            format % args,
        )


class RemoteApiService:
    def __init__(
        self,
        *,
        runtime_client: RemoteApiRuntimeClient,
        config: RemoteApiConfig,
        logger: logging.Logger | None = None,
    ) -> None:
        self._runtime_client = runtime_client
        self._config = config
        self._logger = logger or logging.getLogger(__name__)
        self._server: _RemoteApiHttpServer | None = None
        self._thread: Thread | None = None
        self._token_bindings: tuple[RemoteApiTokenBinding, ...] = ()
        self._audit_writer = RemoteApiAuditWriter(
            folder=Path(config.audit_folder),
            enabled=config.audit_enabled,
        )

    @property
    def logger(self) -> logging.Logger:
        return self._logger

    @property
    def config(self) -> RemoteApiConfig:
        return self._config

    @property
    def port(self) -> int:
        if self._server is not None:
            return int(self._server.server_port)
        return int(self._config.port)

    @property
    def is_running(self) -> bool:
        return self._server is not None and self._thread is not None and self._thread.is_alive()

    @property
    def audit_path(self) -> Path:
        return self._audit_writer.audit_path

    def start(self) -> None:
        if self.is_running:
            return
        self._token_bindings = self._load_token_bindings()
        try:
            server = _RemoteApiHttpServer(
                (self._config.bind_host, int(self._config.port)),
                self,
            )
        except OSError as exc:
            raise RemoteApiServiceError(
                f"No se pudo iniciar servicio remoto local en {self._config.bind_host}:{self._config.port}: {exc}"
            ) from exc
        self._server = server
        self._thread = Thread(
            target=server.serve_forever,
            name="remote-api-http-server",
            daemon=True,
        )
        self._thread.start()
        self._logger.info(
            "Servicio remoto local activo en http://%s:%s",
            self._config.bind_host,
            self.port,
        )
        if self._config.auth_mode == "bearer_token":
            self._logger.warning(
                "Servicio remoto en modo legado bearer_token; el token único se autoriza como admin."
            )

    def stop(self) -> None:
        server = self._server
        thread = self._thread
        self._server = None
        self._thread = None
        if server is None:
            return
        server.shutdown()
        server.server_close()
        if thread is not None:
            thread.join(timeout=2.0)

    def handle_http_request(self, handler: BaseHTTPRequestHandler) -> None:
        request_id = secrets.token_hex(8)
        parsed = urlparse(handler.path)
        method = handler.command.upper()
        raw_path = parsed.path or "/"
        if method == "GET" and _is_remote_console_path(raw_path):
            self._serve_remote_console(handler, raw_path)
            return
        actor_type = "anonymous"
        actor_id = "anonymous"
        role: str | None = None
        authorization_result: str | None = None
        token_label: str | None = None
        action = _infer_action(method, raw_path)
        node_id: int | None = _infer_node_id(raw_path)
        result = "internal_error"
        status_code = 500
        correlation_cmd_seq: int | None = None
        correlation_nonce: int | None = None
        payload: dict[str, Any]

        try:
            auth_context = self._authenticate(handler.headers.get("Authorization"))
            actor_type = auth_context.actor_type
            actor_id = auth_context.actor_id
            role = auth_context.role
            authorization_result = auth_context.authorization_result
            token_label = auth_context.token_label
            authorize_remote_api_action(
                role=auth_context.role,
                action=action,
                actor_type=auth_context.actor_type,
                actor_id=auth_context.actor_id,
                token_label=auth_context.token_label,
            )
            status_code, payload, outcome = self._dispatch(
                method=method,
                path=raw_path,
                request_id=request_id,
                body=self._read_body(handler),
            )
            action = outcome.action
            node_id = outcome.node_id
            result = outcome.result
            status_code = outcome.status_code
            correlation_cmd_seq = outcome.correlation_cmd_seq
            correlation_nonce = outcome.correlation_nonce
            actor_type = outcome.actor_type or actor_type
            actor_id = outcome.actor_id or actor_id
            role = outcome.role or role
            authorization_result = outcome.authorization_result or authorization_result
            token_label = outcome.token_label or token_label
        except RemoteApiUnauthorizedError as exc:
            actor_type = exc.actor_type
            actor_id = exc.actor_id
            role = exc.role
            authorization_result = exc.authorization_result
            token_label = exc.token_label
            result = "denied"
            status_code = 401
            payload = build_error_response(
                code="unauthorized",
                message=str(exc),
                request_id=request_id,
            )
        except RemoteApiForbiddenError as exc:
            actor_type = exc.actor_type
            actor_id = exc.actor_id
            role = exc.role
            authorization_result = exc.authorization_result
            token_label = exc.token_label
            result = "forbidden"
            status_code = 403
            payload = build_error_response(
                code="forbidden",
                message="El rol autenticado no tiene permiso para esta operación.",
                request_id=request_id,
            )
        except RemoteApiError as exc:
            action = exc.action
            node_id = exc.node_id
            result = exc.result
            status_code = exc.status_code
            correlation_cmd_seq = exc.correlation_cmd_seq
            correlation_nonce = exc.correlation_nonce
            payload = build_error_response(
                code=exc.code,
                message=exc.message,
                request_id=request_id,
            )
        except Exception as exc:
            self._logger.exception("Error no controlado en remote API: %s", exc)
            result = "internal_error"
            status_code = 500
            payload = build_error_response(
                code="internal_error",
                message="Error interno del servicio remoto.",
                request_id=request_id,
            )

        self._write_json_response(handler, status_code, payload)
        self._audit_writer.write_event(
            build_remote_api_audit_event(
                request_id=request_id,
                actor_type=actor_type,
                actor_id=actor_id,
                role=role,
                authorization_result=authorization_result,
                token_label=token_label,
                origin_remote_addr=_extract_remote_addr(handler.client_address),
                origin_via=_classify_origin(handler.client_address),
                http_method=method,
                path=raw_path,
                action=action,
                node_id=node_id,
                result=result,
                status_code=status_code,
                session_state=self._session_state_value(),
                correlation_cmd_seq=correlation_cmd_seq,
                correlation_nonce=correlation_nonce,
            )
        )

    def _dispatch(
        self,
        *,
        method: str,
        path: str,
        request_id: str,
        body: bytes,
    ) -> tuple[int, dict[str, Any], _RequestAuditOutcome]:
        if method == "GET" and path == "/api/v1/health":
            payload = {
                "service": "ckv2-remote-site-service",
                "status": "ok",
                "session": serialize_session_snapshot(self._runtime_client.get_snapshot()),
                "control_plane": {
                    "available": bool(self._runtime_client.is_control_plane_available()),
                    "listener_active": bool(
                        self._runtime_client.get_control_plane_runtime_snapshot().listener_active
                    ),
                },
            }
            return 200, build_success_response(data=payload, request_id=request_id), _RequestAuditOutcome(
                actor_type="technical_token",
                actor_id="",
                action="health.read",
                node_id=None,
                result="ok",
                status_code=200,
            )

        if method == "GET" and path == "/api/v1/runtime/summary":
            session_snapshot = self._runtime_client.get_snapshot()
            cp_snapshot = self._runtime_client.get_control_plane_runtime_snapshot()
            payload = {
                "session": serialize_session_snapshot(session_snapshot),
                "nodes": serialize_node_registry_summary(
                    self._runtime_client.get_node_registry_summary(now=time.monotonic())
                ),
                "control_plane": serialize_control_plane_summary(cp_snapshot),
            }
            return 200, build_success_response(data=payload, request_id=request_id), _RequestAuditOutcome(
                actor_type="technical_token",
                actor_id="",
                action="runtime.summary.read",
                node_id=None,
                result="ok",
                status_code=200,
            )

        if method == "GET" and path == "/api/v1/nodes":
            now_monotonic = time.monotonic()
            snapshots = self._runtime_client.get_node_snapshots(now=now_monotonic)
            cp_map = {
                item.node_id: item
                for item in self._runtime_client.get_control_plane_node_snapshots(now=now_monotonic)
            }
            payload = {
                "nodes": [
                    serialize_node_summary(
                        snapshot,
                        control_plane_snapshot=cp_map.get(int(snapshot.node_id)),
                    )
                    for snapshot in snapshots
                ]
            }
            return 200, build_success_response(data=payload, request_id=request_id), _RequestAuditOutcome(
                actor_type="technical_token",
                actor_id="",
                action="nodes.read",
                node_id=None,
                result="ok",
                status_code=200,
            )

        if method == "GET" and path.startswith("/api/v1/nodes/"):
            node_id = _parse_node_id_from_path(path)
            now_monotonic = time.monotonic()
            snapshot = self._runtime_client.get_node_snapshot(node_id=node_id, now=now_monotonic)
            if snapshot is None:
                raise RemoteApiError(
                    "node_not_found",
                    f"No existe nodo {node_id} en snapshots actuales.",
                    status_code=404,
                    action="node.read",
                    node_id=node_id,
                    result="node_not_found",
                )
            control_snapshot = self._runtime_client.get_control_plane_node_snapshot(
                node_id=node_id,
                now=now_monotonic,
            )
            payload = serialize_node_detail(
                snapshot,
                control_plane_snapshot=control_snapshot,
            )
            return 200, build_success_response(data=payload, request_id=request_id), _RequestAuditOutcome(
                actor_type="technical_token",
                actor_id="",
                action="node.read",
                node_id=node_id,
                result="ok",
                status_code=200,
            )

        if method == "POST" and path.endswith("/actions/request-stat-now"):
            node_id = _parse_node_id_from_action_path(path, "request-stat-now")
            _ = _parse_json_body(body)
            tx_result = self._execute_action_request_stat_now(node_id=node_id)
            payload = {
                "action": "request_stat_now",
                "node_id": node_id,
                "result": serialize_control_transaction_result(tx_result),
            }
            final_status = tx_result.final_status.value
            if tx_result.final_status is not ControlTransactionFinalStatus.ACK_MATCHED:
                raise RemoteApiError(
                    "command_failed",
                    f"REQUEST_STAT_NOW terminó en estado '{final_status}'.",
                    status_code=502,
                    action="node.request_stat_now",
                    node_id=node_id,
                    result=final_status,
                    correlation_cmd_seq=tx_result.cmd_seq,
                    correlation_nonce=tx_result.nonce,
                )
            return 200, build_success_response(data=payload, request_id=request_id), _RequestAuditOutcome(
                actor_type="technical_token",
                actor_id="",
                action="node.request_stat_now",
                node_id=node_id,
                result=final_status,
                status_code=200,
                correlation_cmd_seq=tx_result.cmd_seq,
                correlation_nonce=tx_result.nonce,
            )

        if method == "POST" and path.endswith("/actions/reboot"):
            node_id = _parse_node_id_from_action_path(path, "reboot")
            body_payload = _parse_json_body(body)
            delay_ms = 0
            if "delay_ms" in body_payload:
                delay_ms = _parse_delay_ms(body_payload["delay_ms"])
            tx_result = self._execute_action_reboot(node_id=node_id, delay_ms=delay_ms)
            payload = {
                "action": "reboot",
                "node_id": node_id,
                "result": serialize_control_transaction_result(tx_result),
            }
            final_status = tx_result.final_status.value
            if tx_result.final_status is not ControlTransactionFinalStatus.ACK_MATCHED:
                raise RemoteApiError(
                    "command_failed",
                    f"REBOOT_SOFT terminó en estado '{final_status}'.",
                    status_code=502,
                    action="node.reboot",
                    node_id=node_id,
                    result=final_status,
                    correlation_cmd_seq=tx_result.cmd_seq,
                    correlation_nonce=tx_result.nonce,
                )
            return 200, build_success_response(data=payload, request_id=request_id), _RequestAuditOutcome(
                actor_type="technical_token",
                actor_id="",
                action="node.reboot",
                node_id=node_id,
                result=final_status,
                status_code=200,
                correlation_cmd_seq=tx_result.cmd_seq,
                correlation_nonce=tx_result.nonce,
            )

        raise RemoteApiError(
            "invalid_request",
            "Endpoint remoto no soportado por v1.",
            status_code=400,
            action=_infer_action(method, path),
            node_id=_infer_node_id(path),
            result="invalid_request",
        )

    def _execute_action_request_stat_now(self, *, node_id: int) -> ControlTransactionResult:
        self._assert_action_preconditions(node_id=node_id, action="node.request_stat_now")
        try:
            return self._runtime_client.send_control_request_stat_now(
                node_id=node_id,
                source="remote_api",
            )
        except ControlPlaneNodeResolutionError as exc:
            raise RemoteApiError(
                "node_unresolved",
                str(exc),
                status_code=409,
                action="node.request_stat_now",
                node_id=node_id,
                result="node_unresolved",
            ) from exc
        except ControlPlaneRuntimeUnavailableError as exc:
            raise RemoteApiError(
                "control_plane_unavailable",
                str(exc),
                status_code=409,
                action="node.request_stat_now",
                node_id=node_id,
                result="control_plane_unavailable",
            ) from exc
        except Exception as exc:
            raise RemoteApiError(
                "command_failed",
                f"No se pudo ejecutar REQUEST_STAT_NOW: {exc}",
                status_code=502,
                action="node.request_stat_now",
                node_id=node_id,
                result="command_failed",
            ) from exc

    def _execute_action_reboot(self, *, node_id: int, delay_ms: int) -> ControlTransactionResult:
        self._assert_action_preconditions(node_id=node_id, action="node.reboot")
        try:
            return self._runtime_client.send_control_reboot_soft(
                node_id=node_id,
                delay_ms=delay_ms,
                source="remote_api",
            )
        except ControlPlaneNodeResolutionError as exc:
            raise RemoteApiError(
                "node_unresolved",
                str(exc),
                status_code=409,
                action="node.reboot",
                node_id=node_id,
                result="node_unresolved",
            ) from exc
        except ControlPlaneRuntimeUnavailableError as exc:
            raise RemoteApiError(
                "control_plane_unavailable",
                str(exc),
                status_code=409,
                action="node.reboot",
                node_id=node_id,
                result="control_plane_unavailable",
            ) from exc
        except Exception as exc:
            raise RemoteApiError(
                "command_failed",
                f"No se pudo ejecutar REBOOT_SOFT: {exc}",
                status_code=502,
                action="node.reboot",
                node_id=node_id,
                result="command_failed",
            ) from exc

    def _assert_action_preconditions(self, *, node_id: int, action: str) -> None:
        snapshot = self._runtime_client.get_snapshot()
        if snapshot.state is not SessionState.RUNNING:
            raise RemoteApiError(
                "session_not_running",
                "La sesión no está running.",
                status_code=409,
                action=action,
                node_id=node_id,
                result="session_not_running",
            )
        if not self._runtime_client.is_control_plane_available():
            raise RemoteApiError(
                "control_plane_unavailable",
                "Control-plane requiere sesión UDP/LAB running.",
                status_code=409,
                action=action,
                node_id=node_id,
                result="control_plane_unavailable",
            )
        runtime_node = self._runtime_client.get_node_snapshot(node_id=node_id, now=time.monotonic())
        if runtime_node is None:
            raise RemoteApiError(
                "node_not_found",
                f"No existe nodo {node_id} en snapshots actuales.",
                status_code=404,
                action=action,
                node_id=node_id,
                result="node_not_found",
            )
        control_snapshot = self._runtime_client.get_control_plane_node_snapshot(
            node_id=node_id,
            now=time.monotonic(),
        )
        if control_snapshot is not None and (
            control_snapshot.resolution_status is ControlPlaneNodeResolutionStatus.UNRESOLVED
        ):
            raise RemoteApiError(
                "node_unresolved",
                "No se pudo resolver IP para node_id en runtime actual.",
                status_code=409,
                action=action,
                node_id=node_id,
                result="node_unresolved",
            )

    def _authenticate(self, authorization_header: str | None) -> RemoteApiAuthContext:
        if not self._token_bindings:
            raise RemoteApiAuthConfigError("Servicio remoto sin inventario de tokens cargado.")
        return authenticate_bearer_request(
            authorization_header,
            token_bindings=self._token_bindings,
        )

    def _load_token_bindings(self) -> tuple[RemoteApiTokenBinding, ...]:
        try:
            return resolve_remote_api_token_bindings(
                self._config,
                environ=os.environ,
            )
        except RemoteApiAuthConfigError as exc:
            raise RemoteApiServiceError(str(exc)) from exc

    def _serve_remote_console(self, handler: BaseHTTPRequestHandler, path: str) -> None:
        asset_name = _resolve_remote_console_asset_name(path)
        if asset_name is None:
            self._write_plain_response(handler, 404, "Remote console asset not found.")
            return
        asset_path = _remote_console_asset_path(asset_name)
        if not asset_path.exists():
            self._write_plain_response(handler, 404, "Remote console asset not found.")
            return
        content_type = mimetypes.guess_type(asset_path.name)[0] or "application/octet-stream"
        raw = asset_path.read_bytes()
        self._write_bytes_response(
            handler,
            status_code=200,
            raw=raw,
            content_type=content_type,
        )

    @staticmethod
    def _read_body(handler: BaseHTTPRequestHandler) -> bytes:
        content_length = handler.headers.get("Content-Length")
        try:
            expected = int(content_length) if content_length is not None else 0
        except (TypeError, ValueError):
            expected = 0
        if expected <= 0:
            return b""
        return handler.rfile.read(expected)

    @staticmethod
    def _write_json_response(
        handler: BaseHTTPRequestHandler,
        status_code: int,
        payload: dict[str, Any],
    ) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        handler.send_response(int(status_code))
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(raw)))
        handler.end_headers()
        handler.wfile.write(raw)

    @staticmethod
    def _write_bytes_response(
        handler: BaseHTTPRequestHandler,
        *,
        status_code: int,
        raw: bytes,
        content_type: str,
    ) -> None:
        handler.send_response(int(status_code))
        handler.send_header("Content-Type", str(content_type))
        handler.send_header("Content-Length", str(len(raw)))
        handler.end_headers()
        handler.wfile.write(raw)

    @classmethod
    def _write_plain_response(
        cls,
        handler: BaseHTTPRequestHandler,
        status_code: int,
        message: str,
    ) -> None:
        cls._write_bytes_response(
            handler,
            status_code=status_code,
            raw=str(message).encode("utf-8"),
            content_type="text/plain; charset=utf-8",
        )

    def _session_state_value(self) -> str:
        snapshot = self._runtime_client.get_snapshot()
        return snapshot.state.value


def _parse_json_body(body: bytes) -> dict[str, Any]:
    if not body:
        return {}
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RemoteApiError(
            "invalid_request",
            f"Body JSON invalido: {exc}",
            status_code=400,
            action="request.invalid",
            result="invalid_request",
        ) from exc
    if not isinstance(payload, dict):
        raise RemoteApiError(
            "invalid_request",
            "Body JSON invalido: se esperaba objeto JSON.",
            status_code=400,
            action="request.invalid",
            result="invalid_request",
        )
    return payload


def _is_remote_console_path(path: str) -> bool:
    return path == "/remote" or path.startswith("/remote/")


def _resolve_remote_console_asset_name(path: str) -> str | None:
    if path in {"/remote", "/remote/", "/remote/index.html"}:
        return "index.html"
    if path == "/remote/app.js":
        return "app.js"
    if path == "/remote/styles.css":
        return "styles.css"
    return None


def _remote_console_asset_path(asset_name: str) -> Path:
    return Path(__file__).resolve().parent / "remote_console_assets" / asset_name


def _parse_node_id_from_path(path: str) -> int:
    parts = [part for part in path.split("/") if part]
    if len(parts) != 4 or parts[:3] != ["api", "v1", "nodes"]:
        raise RemoteApiError(
            "invalid_request",
            "Path de nodo invalido para v1.",
            status_code=400,
            action="node.read",
            result="invalid_request",
        )
    return _parse_node_id(parts[3], action="node.read")


def _parse_node_id_from_action_path(path: str, action_name: str) -> int:
    parts = [part for part in path.split("/") if part]
    if len(parts) != 6 or parts[:3] != ["api", "v1", "nodes"] or parts[4] != "actions" or parts[5] != action_name:
        raise RemoteApiError(
            "invalid_request",
            "Path de acción invalido para v1.",
            status_code=400,
            action=f"node.{action_name.replace('-', '_')}",
            result="invalid_request",
        )
    return _parse_node_id(parts[3], action=f"node.{action_name.replace('-', '_')}")


def _parse_node_id(raw_value: str, *, action: str) -> int:
    try:
        node_id = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise RemoteApiError(
            "invalid_node_id",
            f"node_id invalido: {raw_value!r}",
            status_code=400,
            action=action,
            result="invalid_node_id",
        ) from exc
    if node_id < 1 or node_id > 0xFFFF:
        raise RemoteApiError(
            "invalid_node_id",
            f"node_id fuera de rango unicast: {node_id}",
            status_code=400,
            action=action,
            node_id=node_id,
            result="invalid_node_id",
        )
    return node_id


def _parse_delay_ms(raw_value: Any) -> int:
    try:
        delay_ms = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise RemoteApiError(
            "invalid_request",
            "delay_ms invalido: se esperaba entero.",
            status_code=400,
            action="node.reboot",
            result="invalid_request",
        ) from exc
    if delay_ms < 0 or delay_ms > 60000:
        raise RemoteApiError(
            "invalid_request",
            "delay_ms fuera de rango permitido (0..60000).",
            status_code=400,
            action="node.reboot",
            result="invalid_request",
        )
    return delay_ms


def _infer_action(method: str, path: str) -> str:
    if method == "GET" and path == "/api/v1/health":
        return "health.read"
    if method == "GET" and path == "/api/v1/runtime/summary":
        return "runtime.summary.read"
    if method == "GET" and path == "/api/v1/nodes":
        return "nodes.read"
    if method == "GET" and path.startswith("/api/v1/nodes/"):
        return "node.read"
    if method == "POST" and path.endswith("/actions/request-stat-now"):
        return "node.request_stat_now"
    if method == "POST" and path.endswith("/actions/reboot"):
        return "node.reboot"
    return "request.invalid"


def _infer_node_id(path: str) -> int | None:
    parts = [part for part in path.split("/") if part]
    if len(parts) >= 4 and parts[:3] == ["api", "v1", "nodes"]:
        try:
            value = int(parts[3])
        except (TypeError, ValueError):
            return None
        if value < 1 or value > 0xFFFF:
            return None
        return value
    return None


def _extract_remote_addr(client_address: Any) -> str:
    if isinstance(client_address, tuple) and client_address:
        return str(client_address[0])
    return "unknown"


def _classify_origin(client_address: Any) -> str:
    host = _extract_remote_addr(client_address)
    if host == "unknown":
        return "unknown"
    if host.startswith("100.") or host.startswith("100.64.") or host.startswith("100.127."):
        return "tailscale"
    if host.startswith("127.") or host == "::1":
        return "local_lan"
    if host.startswith("10.") or host.startswith("192.168.") or host.startswith("172.16.") or host.startswith("172.17.") or host.startswith("172.18.") or host.startswith("172.19.") or host.startswith("172.2"):
        return "local_lan"
    return "unknown"
