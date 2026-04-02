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
    ControlPlaneRuntimeSnapshot,
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
    RemoteApiAuthContext,
    RemoteApiAuthConfigError,
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
from control_okua.services.remote_auth_service import (
    RemoteAuthenticatedUser,
    RemoteAuthService,
    RemoteAuthServiceError,
)
from control_okua.services.remote_session_service import RemoteSessionService
from control_okua.services.remote_user_store import RemoteUserStore


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
class _AuthenticatedPrincipal:
    actor_type: str
    actor_id: str
    role: str
    authorization_result: str
    auth_scheme: str
    username: str | None = None
    token_label: str | None = None
    session_id: str | None = None


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

    def do_PATCH(self) -> None:  # noqa: N802
        self.server.remote_api_service.handle_http_request(self)

    def do_DELETE(self) -> None:  # noqa: N802
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
        config_path: Path | str | None = None,
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
        self._site_root = Path.cwd() if config_path is None else Path(config_path).resolve().parent
        self._user_store = RemoteUserStore(self._site_root / config.user_store_filename)
        self._auth_service = RemoteAuthService(self._user_store)
        self._session_service = RemoteSessionService(ttl_s=config.session_ttl_s)

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

    @property
    def user_store_path(self) -> Path:
        return self._user_store.path

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
                "Servicio remoto con compatibilidad legado bearer_token; si existe token válido se autoriza como admin."
            )
        if not self._token_bindings:
            self._logger.info(
                "Servicio remoto sin bearer tokens técnicos cargados; la consola humana por usuario/contraseña sigue disponible."
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
        extra_headers: list[tuple[str, str]] = []
        cookie_header = handler.headers.get("Cookie")
        authorization_header = handler.headers.get("Authorization")
        body = self._read_body(handler)

        try:
            if _is_public_remote_api_route(method, raw_path):
                status_code, payload, outcome, extra_headers = self._dispatch_public(
                    method=method,
                    path=raw_path,
                    request_id=request_id,
                    body=body,
                    cookie_header=cookie_header,
                    authorization_header=authorization_header,
                )
            else:
                principal, should_clear_cookie = self._authenticate_protected_request(
                    cookie_header=cookie_header,
                    authorization_header=authorization_header,
                )
                if should_clear_cookie:
                    extra_headers.append(
                        ("Set-Cookie", self._session_service.build_clear_cookie_header())
                    )
                authorize_remote_api_action(
                    role=principal.role,
                    action=action,
                    actor_type=principal.actor_type,
                    actor_id=principal.actor_id,
                    token_label=principal.token_label,
                )
                status_code, payload, outcome, dispatch_headers = self._dispatch_protected(
                    method=method,
                    path=raw_path,
                    request_id=request_id,
                    body=body,
                    principal=principal,
                )
                extra_headers.extend(dispatch_headers)

            actor_type = outcome.actor_type
            actor_id = outcome.actor_id
            role = outcome.role
            authorization_result = outcome.authorization_result
            token_label = outcome.token_label
            action = outcome.action
            node_id = outcome.node_id
            result = outcome.result
            status_code = outcome.status_code
            correlation_cmd_seq = outcome.correlation_cmd_seq
            correlation_nonce = outcome.correlation_nonce
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
            if self._session_service.has_session_cookie(cookie_header):
                extra_headers.append(
                    ("Set-Cookie", self._session_service.build_clear_cookie_header())
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

        self._write_json_response(
            handler,
            status_code,
            payload,
            extra_headers=extra_headers,
        )
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

    def _dispatch_public(
        self,
        *,
        method: str,
        path: str,
        request_id: str,
        body: bytes,
        cookie_header: str | None,
        authorization_header: str | None,
    ) -> tuple[int, dict[str, Any], _RequestAuditOutcome, list[tuple[str, str]]]:
        if method == "GET" and path == "/api/v1/auth/session":
            return self._handle_auth_session(
                request_id=request_id,
                cookie_header=cookie_header,
                authorization_header=authorization_header,
            )
        if method == "POST" and path == "/api/v1/auth/login":
            return self._handle_auth_login(
                request_id=request_id,
                body=body,
            )
        if method == "POST" and path == "/api/v1/auth/bootstrap":
            return self._handle_auth_bootstrap(
                request_id=request_id,
                body=body,
            )
        if method == "POST" and path == "/api/v1/auth/logout":
            return self._handle_auth_logout(
                request_id=request_id,
                cookie_header=cookie_header,
                authorization_header=authorization_header,
            )
        raise RemoteApiError(
            "invalid_request",
            "Ruta pública remota inválida.",
            status_code=404,
            action="request.invalid",
            result="invalid_request",
        )

    def _dispatch_protected(
        self,
        *,
        method: str,
        path: str,
        request_id: str,
        body: bytes,
        principal: _AuthenticatedPrincipal,
    ) -> tuple[int, dict[str, Any], _RequestAuditOutcome, list[tuple[str, str]]]:
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
            return 200, build_success_response(data=payload, request_id=request_id), self._audit_outcome(
                principal=principal,
                action="health.read",
                result="ok",
                status_code=200,
            ), []

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
            return 200, build_success_response(data=payload, request_id=request_id), self._audit_outcome(
                principal=principal,
                action="runtime.summary.read",
                result="ok",
                status_code=200,
            ), []

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
                        control_plane_snapshot=cp_map.get(snapshot.node_id),
                    )
                    for snapshot in snapshots
                ]
            }
            return 200, build_success_response(data=payload, request_id=request_id), self._audit_outcome(
                principal=principal,
                action="nodes.read",
                result="ok",
                status_code=200,
            ), []

        if method == "GET" and path.startswith("/api/v1/nodes/"):
            node_id = _parse_node_id_from_path(path)
            snapshot = self._runtime_client.get_node_snapshot(node_id, now=time.monotonic())
            if snapshot is None:
                raise RemoteApiError(
                    "node_not_found",
                    f"No existe node_id {node_id} en runtime actual.",
                    status_code=404,
                    action="node.read",
                    node_id=node_id,
                    result="node_not_found",
                )
            payload = serialize_node_detail(
                snapshot,
                control_plane_snapshot=self._runtime_client.get_control_plane_node_snapshot(
                    node_id,
                    now=time.monotonic(),
                ),
            )
            return 200, build_success_response(data=payload, request_id=request_id), self._audit_outcome(
                principal=principal,
                action="node.read",
                node_id=node_id,
                result="ok",
                status_code=200,
            ), []

        if method == "POST" and path.endswith("/actions/request-stat-now"):
            node_id = _parse_node_id_from_action_path(path, "request-stat-now")
            self._ensure_runtime_ready_for_action(node_id=node_id, action="node.request_stat_now")
            result = self._runtime_client.send_control_request_stat_now(
                node_id=node_id,
                source="remote_api",
            )
            payload = {"result": serialize_control_transaction_result(result)}
            return 200, build_success_response(data=payload, request_id=request_id), self._audit_outcome(
                principal=principal,
                action="node.request_stat_now",
                node_id=node_id,
                result="ok",
                status_code=200,
                correlation_cmd_seq=getattr(result, "cmd_seq", None),
                correlation_nonce=getattr(result, "nonce", None),
            ), []

        if method == "POST" and path.endswith("/actions/reboot"):
            node_id = _parse_node_id_from_action_path(path, "reboot")
            request_payload = _parse_json_body(body)
            delay_ms = _parse_delay_ms(request_payload.get("delay_ms", 0))
            self._ensure_runtime_ready_for_action(node_id=node_id, action="node.reboot")
            result = self._runtime_client.send_control_reboot_soft(
                node_id=node_id,
                delay_ms=delay_ms,
                source="remote_api",
            )
            payload = {"result": serialize_control_transaction_result(result)}
            return 200, build_success_response(data=payload, request_id=request_id), self._audit_outcome(
                principal=principal,
                action="node.reboot",
                node_id=node_id,
                result="ok",
                status_code=200,
                correlation_cmd_seq=getattr(result, "cmd_seq", None),
                correlation_nonce=getattr(result, "nonce", None),
            ), []

        if method == "GET" and path == "/api/v1/accounts":
            users = [item.to_public_dict() for item in self._auth_service.list_public_users()]
            payload = {"users": users}
            return 200, build_success_response(data=payload, request_id=request_id), self._audit_outcome(
                principal=principal,
                action="accounts.read",
                result="ok",
                status_code=200,
            ), []

        if method == "POST" and path == "/api/v1/accounts":
            request_payload = _parse_json_body(body)
            user = self._auth_service.create_user(
                username=str(request_payload.get("username", "")),
                password=str(request_payload.get("password", "")),
                role=str(request_payload.get("role", "")),
                enabled=bool(request_payload.get("enabled", True)),
                notes=_coerce_optional_text(request_payload.get("notes")),
            )
            payload = {"user": user.to_public_dict()}
            return 201, build_success_response(data=payload, request_id=request_id), self._audit_outcome(
                principal=principal,
                action="account.create",
                result="ok",
                status_code=201,
            ), []

        if method == "PATCH" and path.startswith("/api/v1/accounts/"):
            target_username = _parse_account_username_from_path(path)
            request_payload = _parse_json_body(body)
            updated = self._auth_service.update_user_profile(
                username=target_username,
                new_username=_coerce_optional_text(request_payload.get("username")),
                role=_coerce_optional_text(request_payload.get("role")),
                enabled=_coerce_optional_bool(request_payload.get("enabled")),
                notes=_coerce_optional_text_for_patch(request_payload),
            )
            headers = self._refresh_session_headers_if_needed(
                principal=principal,
                old_username=target_username,
                updated_user=updated,
            )
            payload = {"user": updated.to_public_dict()}
            return 200, build_success_response(data=payload, request_id=request_id), self._audit_outcome(
                principal=principal,
                action="account.update",
                result="ok",
                status_code=200,
            ), headers

        if method == "POST" and path.startswith("/api/v1/accounts/") and path.endswith("/password"):
            target_username = _parse_account_username_from_password_path(path)
            request_payload = _parse_json_body(body)
            updated = self._auth_service.change_password(
                username=target_username,
                new_password=str(request_payload.get("new_password", "")),
            )
            headers = self._refresh_session_headers_if_needed(
                principal=principal,
                old_username=target_username,
                updated_user=updated,
            )
            payload = {"user": updated.to_public_dict()}
            return 200, build_success_response(data=payload, request_id=request_id), self._audit_outcome(
                principal=principal,
                action="account.change_password",
                result="ok",
                status_code=200,
            ), headers

        if method == "DELETE" and path.startswith("/api/v1/accounts/"):
            target_username = _parse_account_username_from_path(path)
            self._auth_service.delete_user(username=target_username)
            headers = self._clear_session_headers_if_current_user(
                principal=principal,
                username=target_username,
            )
            payload = {"deleted_username": target_username}
            return 200, build_success_response(data=payload, request_id=request_id), self._audit_outcome(
                principal=principal,
                action="account.delete",
                result="ok",
                status_code=200,
            ), headers

        raise RemoteApiError(
            "invalid_request",
            "Ruta protegida remota inválida.",
            status_code=404,
            action="request.invalid",
            result="invalid_request",
        )

    def _handle_auth_session(
        self,
        *,
        request_id: str,
        cookie_header: str | None,
        authorization_header: str | None,
    ) -> tuple[int, dict[str, Any], _RequestAuditOutcome, list[tuple[str, str]]]:
        principal, should_clear_cookie = self._resolve_optional_principal(
            cookie_header=cookie_header,
            authorization_header=authorization_header,
        )
        headers: list[tuple[str, str]] = []
        if should_clear_cookie:
            headers.append(("Set-Cookie", self._session_service.build_clear_cookie_header()))
        payload = {
            "bootstrap_required": self._auth_service.bootstrap_required(),
            "authenticated": principal is not None,
            "auth_scheme": None if principal is None else principal.auth_scheme,
            "user": None if principal is None else {
                "username": principal.username,
                "role": principal.role,
            },
            "legacy_token_available": bool(self._token_bindings),
            "session_ttl_s": self._config.session_ttl_s,
        }
        actor_type = principal.actor_type if principal is not None else "anonymous"
        actor_id = principal.actor_id if principal is not None else "anonymous"
        return 200, build_success_response(data=payload, request_id=request_id), _RequestAuditOutcome(
            actor_type=actor_type,
            actor_id=actor_id,
            role=None if principal is None else principal.role,
            authorization_result=None if principal is None else principal.authorization_result,
            token_label=None if principal is None else principal.token_label,
            action="auth.session.read",
            node_id=None,
            result="ok",
            status_code=200,
        ), headers

    def _handle_auth_login(
        self,
        *,
        request_id: str,
        body: bytes,
    ) -> tuple[int, dict[str, Any], _RequestAuditOutcome, list[tuple[str, str]]]:
        request_payload = _parse_json_body(body)
        username = str(request_payload.get("username", "")).strip()
        password = str(request_payload.get("password", ""))
        if not username or not password:
            raise RemoteApiError(
                "invalid_request",
                "Login remoto requiere username y password.",
                status_code=400,
                action="auth.login",
                result="invalid_request",
            )
        try:
            user = self._auth_service.authenticate_credentials(
                username=username,
                password=password,
            )
        except RemoteAuthServiceError as exc:
            raise self._map_remote_auth_error(exc, action="auth.login") from exc

        session = self._session_service.create_session(username=user.username)
        principal = self._principal_from_user(
            user,
            session_id=session.session_id,
            auth_scheme="session_cookie",
            authorization_result="granted_session",
        )
        payload = {
            "authenticated": True,
            "bootstrap_required": False,
            "auth_scheme": "session_cookie",
            "user": user.to_public_dict(),
        }
        headers = [("Set-Cookie", self._session_service.build_set_cookie_header(session.session_id))]
        return 200, build_success_response(data=payload, request_id=request_id), self._audit_outcome(
            principal=principal,
            action="auth.login",
            result="ok",
            status_code=200,
        ), headers

    def _handle_auth_bootstrap(
        self,
        *,
        request_id: str,
        body: bytes,
    ) -> tuple[int, dict[str, Any], _RequestAuditOutcome, list[tuple[str, str]]]:
        request_payload = _parse_json_body(body)
        raw_accounts = request_payload.get("accounts")
        if not isinstance(raw_accounts, list):
            raise RemoteApiError(
                "invalid_request",
                "Bootstrap remoto requiere una lista 'accounts'.",
                status_code=400,
                action="auth.bootstrap",
                result="invalid_request",
            )
        try:
            created = self._auth_service.bootstrap_initial_accounts(raw_accounts)
        except RemoteAuthServiceError as exc:
            raise self._map_remote_auth_error(exc, action="auth.bootstrap") from exc

        admin_user = next((item for item in created if item.role == "admin"), None)
        if admin_user is None:
            raise RemoteApiError(
                "invalid_bootstrap",
                "Bootstrap inicial sin cuenta admin resultante.",
                status_code=400,
                action="auth.bootstrap",
                result="invalid_bootstrap",
            )
        session = self._session_service.create_session(username=admin_user.username)
        principal = self._principal_from_user(
            admin_user,
            session_id=session.session_id,
            auth_scheme="session_cookie",
            authorization_result="granted_session",
        )
        payload = {
            "authenticated": True,
            "bootstrap_required": False,
            "auth_scheme": "session_cookie",
            "user": admin_user.to_public_dict(),
            "created_users": [item.to_public_dict() for item in created],
        }
        headers = [("Set-Cookie", self._session_service.build_set_cookie_header(session.session_id))]
        return 200, build_success_response(data=payload, request_id=request_id), self._audit_outcome(
            principal=principal,
            action="auth.bootstrap",
            result="ok",
            status_code=200,
        ), headers

    def _handle_auth_logout(
        self,
        *,
        request_id: str,
        cookie_header: str | None,
        authorization_header: str | None,
    ) -> tuple[int, dict[str, Any], _RequestAuditOutcome, list[tuple[str, str]]]:
        principal, _ = self._resolve_optional_principal(
            cookie_header=cookie_header,
            authorization_header=authorization_header,
        )
        if principal is not None and principal.session_id is not None:
            self._session_service.destroy_session(principal.session_id)
        else:
            self._session_service.destroy_session_from_cookie(cookie_header)

        actor_type = principal.actor_type if principal is not None else "anonymous"
        actor_id = principal.actor_id if principal is not None else "anonymous"
        role = principal.role if principal is not None else None
        authorization_result = (
            principal.authorization_result if principal is not None else "granted_logout"
        )
        payload = {
            "authenticated": False,
            "logged_out": True,
        }
        headers = [("Set-Cookie", self._session_service.build_clear_cookie_header())]
        return 200, build_success_response(data=payload, request_id=request_id), _RequestAuditOutcome(
            actor_type=actor_type,
            actor_id=actor_id,
            role=role,
            authorization_result=authorization_result,
            token_label=None if principal is None else principal.token_label,
            action="auth.logout",
            node_id=None,
            result="ok",
            status_code=200,
        ), headers

    def _authenticate_protected_request(
        self,
        *,
        cookie_header: str | None,
        authorization_header: str | None,
    ) -> tuple[_AuthenticatedPrincipal, bool]:
        session_cookie_present = self._session_service.has_session_cookie(cookie_header)
        session_record = self._session_service.resolve_session(cookie_header)
        if session_record is not None:
            principal = self._principal_from_session_record(session_record)
            if principal is not None:
                return principal, False
            self._session_service.destroy_session(session_record.session_id)
            raise RemoteApiUnauthorizedError(
                "Sesión remota inválida o expirada.",
                actor_type="remote_user_session",
                actor_id="anonymous",
                authorization_result="denied_invalid_session",
            )
        if session_cookie_present:
            self._session_service.destroy_session_from_cookie(cookie_header)
            raise RemoteApiUnauthorizedError(
                "Sesión remota inválida o expirada.",
                actor_type="remote_user_session",
                actor_id="anonymous",
                authorization_result="denied_invalid_session",
            )
        if authorization_header is not None:
            if not self._token_bindings:
                raise RemoteApiUnauthorizedError(
                    "Bearer token invalido.",
                    actor_type="technical_token",
                    actor_id="anonymous",
                    authorization_result="denied_invalid_token",
                )
            context = authenticate_bearer_request(
                authorization_header,
                token_bindings=self._token_bindings,
            )
            return self._principal_from_bearer_context(context), False
        raise RemoteApiUnauthorizedError(
            "Autenticación requerida para esta operación.",
            actor_type="anonymous",
            actor_id="anonymous",
            authorization_result="denied_missing_token",
        )

    def _resolve_optional_principal(
        self,
        *,
        cookie_header: str | None,
        authorization_header: str | None,
    ) -> tuple[_AuthenticatedPrincipal | None, bool]:
        session_cookie_present = self._session_service.has_session_cookie(cookie_header)
        session_record = self._session_service.resolve_session(cookie_header)
        if session_record is not None:
            principal = self._principal_from_session_record(session_record)
            if principal is not None:
                return principal, False
            self._session_service.destroy_session(session_record.session_id)
            return None, True
        if session_cookie_present:
            self._session_service.destroy_session_from_cookie(cookie_header)
            return None, True
        if authorization_header is not None and self._token_bindings:
            try:
                context = authenticate_bearer_request(
                    authorization_header,
                    token_bindings=self._token_bindings,
                )
            except RemoteApiUnauthorizedError:
                return None, False
            return self._principal_from_bearer_context(context), False
        return None, False

    def _principal_from_session_record(
        self,
        session_record: Any,
    ) -> _AuthenticatedPrincipal | None:
        try:
            user = self._auth_service.get_user(session_record.username)
        except RemoteAuthServiceError as exc:
            raise self._map_remote_auth_error(exc, action="auth.session.read") from exc
        if user is None or not user.enabled:
            return None
        return self._principal_from_user(
            user,
            session_id=session_record.session_id,
            auth_scheme="session_cookie",
            authorization_result="granted_session",
        )

    @staticmethod
    def _principal_from_user(
        user: RemoteAuthenticatedUser,
        *,
        session_id: str | None,
        auth_scheme: str,
        authorization_result: str,
    ) -> _AuthenticatedPrincipal:
        return _AuthenticatedPrincipal(
            actor_type="remote_user_session",
            actor_id=user.actor_id,
            username=user.username,
            role=user.role,
            token_label=None,
            session_id=session_id,
            auth_scheme=auth_scheme,
            authorization_result=authorization_result,
        )

    @staticmethod
    def _principal_from_bearer_context(context: RemoteApiAuthContext) -> _AuthenticatedPrincipal:
        return _AuthenticatedPrincipal(
            actor_type=context.actor_type,
            actor_id=context.actor_id,
            role=context.role,
            authorization_result=context.authorization_result,
            auth_scheme="bearer_token",
            token_label=context.token_label,
        )

    @staticmethod
    def _audit_outcome(
        *,
        principal: _AuthenticatedPrincipal,
        action: str,
        result: str,
        status_code: int,
        node_id: int | None = None,
        correlation_cmd_seq: int | None = None,
        correlation_nonce: int | None = None,
    ) -> _RequestAuditOutcome:
        return _RequestAuditOutcome(
            actor_type=principal.actor_type,
            actor_id=principal.actor_id,
            role=principal.role,
            authorization_result=principal.authorization_result,
            token_label=principal.token_label,
            action=action,
            node_id=node_id,
            result=result,
            status_code=status_code,
            correlation_cmd_seq=correlation_cmd_seq,
            correlation_nonce=correlation_nonce,
        )

    def _refresh_session_headers_if_needed(
        self,
        *,
        principal: _AuthenticatedPrincipal,
        old_username: str,
        updated_user: RemoteAuthenticatedUser,
    ) -> list[tuple[str, str]]:
        if principal.auth_scheme != "session_cookie" or principal.session_id is None:
            return []
        if principal.username != old_username:
            return []
        self._session_service.destroy_session(principal.session_id)
        if not updated_user.enabled:
            return [("Set-Cookie", self._session_service.build_clear_cookie_header())]
        session = self._session_service.create_session(username=updated_user.username)
        return [("Set-Cookie", self._session_service.build_set_cookie_header(session.session_id))]

    def _clear_session_headers_if_current_user(
        self,
        *,
        principal: _AuthenticatedPrincipal,
        username: str,
    ) -> list[tuple[str, str]]:
        if principal.auth_scheme != "session_cookie" or principal.session_id is None:
            return []
        if principal.username != username:
            return []
        self._session_service.destroy_session(principal.session_id)
        return [("Set-Cookie", self._session_service.build_clear_cookie_header())]

    def _ensure_runtime_ready_for_action(self, *, node_id: int, action: str) -> None:
        snapshot = self._runtime_client.get_snapshot()
        if snapshot.state is not SessionState.RUNNING:
            raise RemoteApiError(
                "session_not_running",
                "La sesión CKv2 no está running; no se puede ejecutar acción remota.",
                status_code=409,
                action=action,
                node_id=node_id,
                result="session_not_running",
            )
        if not self._runtime_client.is_control_plane_available():
            raise RemoteApiError(
                "control_plane_unavailable",
                "Control-plane F3 no disponible en runtime actual.",
                status_code=409,
                action=action,
                node_id=node_id,
                result="control_plane_unavailable",
            )
        node_snapshot = self._runtime_client.get_node_snapshot(node_id, now=time.monotonic())
        if node_snapshot is None:
            raise RemoteApiError(
                "node_not_found",
                f"No existe node_id {node_id} en runtime actual.",
                status_code=404,
                action=action,
                node_id=node_id,
                result="node_not_found",
            )
        control_snapshot = self._runtime_client.get_control_plane_node_snapshot(
            node_id,
            now=time.monotonic(),
        )
        if control_snapshot is None:
            raise RemoteApiError(
                "node_unresolved",
                "No existe snapshot de control-plane para node_id solicitado.",
                status_code=409,
                action=action,
                node_id=node_id,
                result="node_unresolved",
            )
        if control_snapshot.resolution_status is ControlPlaneNodeResolutionStatus.UNRESOLVED:
            raise RemoteApiError(
                "node_unresolved",
                "No se pudo resolver IP para node_id en runtime actual.",
                status_code=409,
                action=action,
                node_id=node_id,
                result="node_unresolved",
            )

    def _load_token_bindings(self) -> tuple[RemoteApiTokenBinding, ...]:
        try:
            return resolve_remote_api_token_bindings(
                self._config,
                environ=os.environ,
            )
        except RemoteApiAuthConfigError as exc:
            self._logger.warning(
                "Compatibilidad bearer token no disponible al iniciar servicio remoto: %s",
                exc,
            )
            return ()

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
        *,
        extra_headers: list[tuple[str, str]] | None = None,
    ) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        handler.send_response(int(status_code))
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Cache-Control", "no-store")
        if extra_headers:
            for header_name, header_value in extra_headers:
                handler.send_header(str(header_name), str(header_value))
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

    def _map_remote_auth_error(
        self,
        exc: RemoteAuthServiceError,
        *,
        action: str,
    ) -> RemoteApiError:
        code = exc.code
        if code == "invalid_credentials":
            return RemoteApiError(
                "unauthorized",
                "Usuario o contraseña inválidos.",
                status_code=401,
                action=action,
                result="unauthorized",
            )
        if code == "account_disabled":
            return RemoteApiError(
                "account_disabled",
                exc.message,
                status_code=403,
                action=action,
                result="account_disabled",
            )
        if code in {"invalid_bootstrap", "invalid_username", "invalid_role", "invalid_password"}:
            return RemoteApiError(
                code,
                exc.message,
                status_code=400,
                action=action,
                result=code,
            )
        if code in {"username_conflict", "bootstrap_already_completed", "last_admin_violation", "bootstrap_required"}:
            return RemoteApiError(
                code,
                exc.message,
                status_code=409,
                action=action,
                result=code,
            )
        if code == "user_not_found":
            return RemoteApiError(
                code,
                exc.message,
                status_code=404,
                action=action,
                result=code,
            )
        return RemoteApiError(
            "internal_error",
            "Error interno del servicio remoto.",
            status_code=500,
            action=action,
            result="internal_error",
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


def _coerce_optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    return bool(value)


class _UnsetSentinel:
    pass


_UNSET = _UnsetSentinel()


def _coerce_optional_text_for_patch(payload: dict[str, Any]) -> str | None | object:
    if "notes" not in payload:
        return _UNSET
    return _coerce_optional_text(payload.get("notes"))


def _is_remote_console_path(path: str) -> bool:
    return path == "/remote" or path.startswith("/remote/")


def _is_public_remote_api_route(method: str, path: str) -> bool:
    if method == "GET" and path == "/api/v1/auth/session":
        return True
    if method == "POST" and path in {
        "/api/v1/auth/login",
        "/api/v1/auth/bootstrap",
        "/api/v1/auth/logout",
    }:
        return True
    return False


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


def _parse_account_username_from_path(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    if len(parts) != 4 or parts[:3] != ["api", "v1", "accounts"]:
        raise RemoteApiError(
            "invalid_request",
            "Path de cuenta remota invalido para v1.",
            status_code=400,
            action="account.update",
            result="invalid_request",
        )
    return str(parts[3]).strip().lower()


def _parse_account_username_from_password_path(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    if len(parts) != 5 or parts[:3] != ["api", "v1", "accounts"] or parts[4] != "password":
        raise RemoteApiError(
            "invalid_request",
            "Path de cambio de password remoto invalido para v1.",
            status_code=400,
            action="account.change_password",
            result="invalid_request",
        )
    return str(parts[3]).strip().lower()


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
    if method == "GET" and path == "/api/v1/auth/session":
        return "auth.session.read"
    if method == "POST" and path == "/api/v1/auth/login":
        return "auth.login"
    if method == "POST" and path == "/api/v1/auth/bootstrap":
        return "auth.bootstrap"
    if method == "POST" and path == "/api/v1/auth/logout":
        return "auth.logout"
    if method == "GET" and path == "/api/v1/accounts":
        return "accounts.read"
    if method == "POST" and path == "/api/v1/accounts":
        return "account.create"
    if method == "PATCH" and path.startswith("/api/v1/accounts/"):
        return "account.update"
    if method == "POST" and path.startswith("/api/v1/accounts/") and path.endswith("/password"):
        return "account.change_password"
    if method == "DELETE" and path.startswith("/api/v1/accounts/"):
        return "account.delete"
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
