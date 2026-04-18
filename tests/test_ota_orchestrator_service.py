from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.core.firmware import (  # noqa: E402
    FirmwareCatalogStore,
    FirmwareImportRequest,
    FirmwareIngestService,
    OtaDeployRequest,
    OtaDeployValidationError,
    OtaManifestService,
)
from control_okua.core.control_plane.protocol import ParsedOkuaAck  # noqa: E402
from control_okua.services.control_transaction_service import (  # noqa: E402
    ControlTransactionFinalStatus,
    ControlTransactionResult,
)
from control_okua.services.ota_orchestrator_service import (  # noqa: E402
    OtaOrchestratorService,
)
from control_okua.services.ota_server_service import (  # noqa: E402
    OtaServerServiceError,
)


class _FakeOtaServerService:
    def __init__(self, *, root_dir: Path, bind_host: str, port: int) -> None:
        self._root_dir = root_dir
        self._bind_host = bind_host
        self._port = port
        self._is_running = False
        self.start_calls = 0
        self.stop_calls = 0

    @property
    def root_dir(self) -> Path:
        return self._root_dir

    @property
    def bind_host(self) -> str:
        return self._bind_host

    @property
    def port(self) -> int:
        return self._port

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start(self) -> None:
        self.start_calls += 1
        self._is_running = True

    def stop(self) -> None:
        self.stop_calls += 1
        self._is_running = False


class _FakeRuntimeClient:
    def __init__(
        self,
        *,
        snapshots: list[object],
        control_results: dict[int, ControlTransactionResult | Exception],
        available: bool = True,
    ) -> None:
        self._snapshots = {int(getattr(snapshot, "node_id")): snapshot for snapshot in snapshots}
        self._control_results = dict(control_results)
        self._available = available
        self.calls: list[dict[str, object]] = []

    def is_control_plane_available(self) -> bool:
        return self._available

    def get_node_snapshots(self, now: float | None = None) -> list[object]:
        _ = now
        return list(self._snapshots.values())

    def get_node_snapshot(self, node_id: int, now: float | None = None) -> object | None:
        _ = now
        return self._snapshots.get(int(node_id))

    def send_control_ota_check_now(
        self,
        *,
        node_id: int,
        rollout_token: int,
        ack_timeout_ms: int = 350,
        max_retries: int = 1,
        source: str = "ota_manual_ui",
    ) -> ControlTransactionResult:
        self.calls.append(
            {
                "node_id": int(node_id),
                "rollout_token": int(rollout_token),
                "ack_timeout_ms": int(ack_timeout_ms),
                "max_retries": int(max_retries),
                "source": source,
            }
        )
        outcome = self._control_results[int(node_id)]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _build_services(
    tmp_path: Path,
) -> tuple[FirmwareCatalogStore, FirmwareIngestService, OtaManifestService]:
    catalog_path = tmp_path / "artifacts" / "firmware_catalog.json"
    store = FirmwareCatalogStore(catalog_path)
    ingest_service = FirmwareIngestService(store)
    manifest_service = OtaManifestService(store, publish_root_dir=tmp_path / "ota_http_root")
    return store, ingest_service, manifest_service


def _import_artifact(tmp_path: Path):
    store, ingest_service, manifest_service = _build_services(tmp_path)
    source_path = tmp_path / "ota_orchestrator.bin"
    source_path.write_bytes(b"ota-orchestrator-payload")
    result = ingest_service.import_artifact(
        FirmwareImportRequest(
            source_file_path=source_path,
            target_kind="plant",
            target_variant="eb1",
            version="3.4.5",
            status="current",
            display_name="ota-orchestrator",
            source_kind="manual_import",
        )
    )
    assert result.success is True
    artifact = result.imported_artifact
    assert artifact is not None
    store.save()
    return artifact, manifest_service


def _snapshot(
    node_id: int,
    *,
    status: str = "online",
    status_reason: str = "healthy traffic",
    ota_state_key: str = "idle",
    ota_error_key: str = "none",
    resolved_ip: str = "192.168.88.10",
    last_uptime_s: int | None = None,
    reset_reason: int | None = None,
    last_state_flags: int | None = None,
):
    return SimpleNamespace(
        node_id=node_id,
        status=status,
        status_reason=status_reason,
        health_summary=status_reason,
        ota_state_key=ota_state_key,
        ota_error_key=ota_error_key,
        resolved_ip=resolved_ip,
        last_uptime_s=last_uptime_s,
        reset_reason=reset_reason,
        last_state_flags=last_state_flags,
    )


def _control_result(
    *,
    node_id: int,
    node_ip: str,
    final_status: ControlTransactionFinalStatus,
    cmd_seq: int = 200,
    nonce: int = 0xAABBCCDD00000001,
    last_error: str | None = None,
) -> ControlTransactionResult:
    ack = None
    if final_status is ControlTransactionFinalStatus.ACK_MATCHED:
        ack = ParsedOkuaAck(
            node_id_source=node_id,
            cmd_seq=cmd_seq,
            cmd_id_echo=0x08,
            nonce_echo=nonce,
            ack_stage=1,
            status_code=0,
            ack_flags=0,
            err_detail=0,
            retry_after_ms=0,
            auth_tag32=0x12345678,
        )
    return ControlTransactionResult(
        command_name="OTA_CHECK_NOW",
        cmd_id=0x08,
        node_ip=node_ip,
        node_id=node_id,
        cmd_seq=cmd_seq,
        nonce=nonce,
        attempt_count=1,
        final_status=final_status,
        ack=ack,
        matched_sent_command=None,
        elapsed_ms=25.0,
        last_error=last_error,
        events=tuple(),
    )


def test_ota_deploy_request_validates_basic_fields() -> None:
    with pytest.raises(OtaDeployValidationError):
        OtaDeployRequest(
            artifact_id="sha256:abc",
            node_ids=[],
            advertise_host="192.168.88.254",
        )

    with pytest.raises(OtaDeployValidationError):
        OtaDeployRequest(
            artifact_id="sha256:abc",
            node_ids=[1],
            advertise_host="0.0.0.0",
        )

    with pytest.raises(OtaDeployValidationError):
        OtaDeployRequest(
            artifact_id="sha256:abc",
            node_ids=[1],
            advertise_host="192.168.88.254",
            rollout_token="0x00000000",
        )


def test_orchestrator_publishes_rollout_starts_server_and_dispatches_nodes(tmp_path: Path) -> None:
    artifact, manifest_service = _import_artifact(tmp_path)
    runtime_client = _FakeRuntimeClient(
        snapshots=[
            _snapshot(1, ota_state_key="triggered", resolved_ip="192.168.88.101"),
            _snapshot(2, ota_state_key="idle", resolved_ip="192.168.88.102"),
        ],
        control_results={
            1: _control_result(
                node_id=1,
                node_ip="192.168.88.101",
                final_status=ControlTransactionFinalStatus.ACK_MATCHED,
            ),
            2: _control_result(
                node_id=2,
                node_ip="192.168.88.102",
                final_status=ControlTransactionFinalStatus.ACK_MATCHED,
                cmd_seq=201,
                nonce=0xAABBCCDD00000002,
            ),
        },
    )
    fake_server = _FakeOtaServerService(
        root_dir=manifest_service.publish_root_dir,
        bind_host="0.0.0.0",
        port=18080,
    )
    orchestrator = OtaOrchestratorService(
        runtime_client=runtime_client,
        manifest_service=manifest_service,
        ota_server_service=fake_server,
    )

    result = orchestrator.deploy(
        OtaDeployRequest(
            artifact_id=artifact.artifact_id,
            node_ids=[1, 2],
            advertise_host="192.168.88.254",
            bind_host="0.0.0.0",
            port=18080,
            rollout_token="20260328",
            rollout_channel="stable",
        )
    )

    assert result.success is True
    assert Path(result.manifest_path).exists()
    assert Path(result.firmware_path).exists()
    assert Path(result.audit_path).exists()
    assert fake_server.start_calls == 1
    assert len(runtime_client.calls) == 2
    assert runtime_client.calls[0]["rollout_token"] == int("20260328", 16)
    assert result.node_statuses[0].phase.value == "triggered"
    assert result.node_statuses[1].phase.value == "acknowledged"


def test_orchestrator_rejects_loopback_advertise_host_for_remote_nodes(tmp_path: Path) -> None:
    artifact, manifest_service = _import_artifact(tmp_path)
    runtime_client = _FakeRuntimeClient(
        snapshots=[_snapshot(1, resolved_ip="192.168.88.101")],
        control_results={
            1: _control_result(
                node_id=1,
                node_ip="192.168.88.101",
                final_status=ControlTransactionFinalStatus.ACK_MATCHED,
            ),
        },
    )
    fake_server = _FakeOtaServerService(
        root_dir=manifest_service.publish_root_dir,
        bind_host="0.0.0.0",
        port=18080,
    )
    orchestrator = OtaOrchestratorService(
        runtime_client=runtime_client,
        manifest_service=manifest_service,
        ota_server_service=fake_server,
    )

    result = orchestrator.deploy(
        OtaDeployRequest(
            artifact_id=artifact.artifact_id,
            node_ids=[1],
            advertise_host="127.0.0.1",
            bind_host="0.0.0.0",
            port=18080,
            rollout_token="20260329",
        )
    )

    assert result.success is False
    assert "loopback" in result.errors[0].lower()
    assert fake_server.start_calls == 0
    assert runtime_client.calls == []


def test_orchestrator_refreshes_runtime_progress_and_timeout_visibility(tmp_path: Path) -> None:
    artifact, manifest_service = _import_artifact(tmp_path)
    runtime_client = _FakeRuntimeClient(
        snapshots=[_snapshot(7, ota_state_key="idle", resolved_ip="127.0.0.1")],
        control_results={
            7: _control_result(
                node_id=7,
                node_ip="127.0.0.1",
                final_status=ControlTransactionFinalStatus.TIMEOUT,
                last_error="timeout esperando ACK OTA",
            ),
        },
    )
    fake_server = _FakeOtaServerService(
        root_dir=manifest_service.publish_root_dir,
        bind_host="127.0.0.1",
        port=18081,
    )
    orchestrator = OtaOrchestratorService(
        runtime_client=runtime_client,
        manifest_service=manifest_service,
        ota_server_service=fake_server,
    )

    initial = orchestrator.deploy(
        OtaDeployRequest(
            artifact_id=artifact.artifact_id,
            node_ids=[7],
            advertise_host="127.0.0.1",
            bind_host="127.0.0.1",
            port=18081,
            rollout_token="20260330",
        )
    )
    assert initial.success is False
    assert initial.node_statuses[0].phase.value == "timeout"

    runtime_client._snapshots[7] = _snapshot(
        7,
        ota_state_key="boot_confirmed",
        status_reason="healthy traffic",
        resolved_ip="127.0.0.1",
    )
    refreshed = orchestrator.refresh_deploy_statuses(initial)

    assert refreshed.node_statuses[0].phase.value == "confirmed"
    assert "boot_confirmed" in refreshed.node_statuses[0].last_message


def test_orchestrator_confirms_ota_after_reboot_reset_and_healthy_runtime(
    tmp_path: Path,
) -> None:
    artifact, manifest_service = _import_artifact(tmp_path)
    runtime_client = _FakeRuntimeClient(
        snapshots=[
            _snapshot(
                7,
                last_uptime_s=106,
                reset_reason=1,
                last_state_flags=0x10,
                resolved_ip="127.0.0.1",
            )
        ],
        control_results={
            7: _control_result(
                node_id=7,
                node_ip="127.0.0.1",
                final_status=ControlTransactionFinalStatus.ACK_MATCHED,
            ),
        },
    )
    fake_server = _FakeOtaServerService(
        root_dir=manifest_service.publish_root_dir,
        bind_host="127.0.0.1",
        port=18081,
    )
    orchestrator = OtaOrchestratorService(
        runtime_client=runtime_client,
        manifest_service=manifest_service,
        ota_server_service=fake_server,
    )

    initial = orchestrator.deploy(
        OtaDeployRequest(
            artifact_id=artifact.artifact_id,
            node_ids=[7],
            advertise_host="127.0.0.1",
            bind_host="127.0.0.1",
            port=18081,
            rollout_token="20260331",
        )
    )
    assert initial.success is True
    assert initial.node_statuses[0].phase.value == "acknowledged"
    assert initial.node_statuses[0].baseline_uptime_s == 106

    runtime_client._snapshots[7] = _snapshot(
        7,
        status="online",
        status_reason="healthy traffic",
        ota_state_key="idle",
        last_uptime_s=56,
        reset_reason=1,
        last_state_flags=0x10,
        resolved_ip="127.0.0.1",
    )
    refreshed = orchestrator.refresh_deploy_statuses(initial)

    assert refreshed.node_statuses[0].phase.value == "confirmed"
    assert refreshed.node_statuses[0].last_message == (
        "OTA confirmada: nodo volvió online tras el reboot."
    )
    assert "confirmados: 1" in refreshed.message


def test_orchestrator_confirms_ota_when_reset_reason_or_boot_marker_changes(
    tmp_path: Path,
) -> None:
    artifact, manifest_service = _import_artifact(tmp_path)
    runtime_client = _FakeRuntimeClient(
        snapshots=[
            _snapshot(
                7,
                last_uptime_s=106,
                reset_reason=1,
                last_state_flags=0x10,
                resolved_ip="127.0.0.1",
            )
        ],
        control_results={
            7: _control_result(
                node_id=7,
                node_ip="127.0.0.1",
                final_status=ControlTransactionFinalStatus.ACK_MATCHED,
            ),
        },
    )
    fake_server = _FakeOtaServerService(
        root_dir=manifest_service.publish_root_dir,
        bind_host="127.0.0.1",
        port=18081,
    )
    orchestrator = OtaOrchestratorService(
        runtime_client=runtime_client,
        manifest_service=manifest_service,
        ota_server_service=fake_server,
    )

    initial = orchestrator.deploy(
        OtaDeployRequest(
            artifact_id=artifact.artifact_id,
            node_ids=[7],
            advertise_host="127.0.0.1",
            bind_host="127.0.0.1",
            port=18081,
            rollout_token="20260332",
        )
    )
    assert initial.success is True
    assert initial.node_statuses[0].phase.value == "acknowledged"
    assert initial.node_statuses[0].baseline_reset_reason == 1
    assert initial.node_statuses[0].baseline_boot_marker == 1

    runtime_client._snapshots[7] = _snapshot(
        7,
        status="online",
        status_reason="healthy traffic",
        ota_state_key="idle",
        last_uptime_s=156,
        reset_reason=2,
        last_state_flags=0x20,
        resolved_ip="127.0.0.1",
    )
    refreshed = orchestrator.refresh_deploy_statuses(initial)

    assert refreshed.node_statuses[0].phase.value == "confirmed"
    assert refreshed.node_statuses[0].last_message == (
        "OTA confirmada: nodo volvió online tras el reboot."
    )
    assert refreshed.node_statuses[0].baseline_reset_reason == 1
    assert refreshed.node_statuses[0].baseline_boot_marker == 1
    assert "confirmados: 1" in refreshed.message


def test_orchestrator_passes_allow_downgrade_to_manifest_publish(tmp_path: Path) -> None:
    artifact, manifest_service = _import_artifact(tmp_path)
    runtime_client = _FakeRuntimeClient(
        snapshots=[_snapshot(1, ota_state_key="idle", resolved_ip="192.168.80.33")],
        control_results={
            1: _control_result(
                node_id=1,
                node_ip="192.168.80.33",
                final_status=ControlTransactionFinalStatus.ACK_MATCHED,
            ),
        },
    )
    fake_server = _FakeOtaServerService(
        root_dir=manifest_service.publish_root_dir,
        bind_host="0.0.0.0",
        port=18082,
    )
    orchestrator = OtaOrchestratorService(
        runtime_client=runtime_client,
        manifest_service=manifest_service,
        ota_server_service=fake_server,
    )

    result = orchestrator.deploy(
        OtaDeployRequest(
            artifact_id=artifact.artifact_id,
            node_ids=[1],
            advertise_host="192.168.80.14",
            bind_host="0.0.0.0",
            port=18082,
            rollout_token="20260341",
            allow_downgrade=True,
        )
    )

    assert result.success is True
    manifest_payload = Path(result.manifest_path).read_text(encoding="utf-8")
    assert '"allow_downgrade": true' in manifest_payload


def test_orchestrator_falls_back_to_advertise_host_when_wildcard_bind_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact, manifest_service = _import_artifact(tmp_path)
    runtime_client = _FakeRuntimeClient(
        snapshots=[_snapshot(1, resolved_ip="192.168.88.101")],
        control_results={
            1: _control_result(
                node_id=1,
                node_ip="192.168.88.101",
                final_status=ControlTransactionFinalStatus.ACK_MATCHED,
            ),
        },
    )
    started_hosts: list[str] = []

    class _FlakyOtaServerService:
        def __init__(self, *, root_dir: Path, bind_host: str, port: int) -> None:
            self._root_dir = root_dir
            self._bind_host = bind_host
            self._port = port
            self._is_running = False
            started_hosts.append(bind_host)

        @property
        def root_dir(self) -> Path:
            return self._root_dir

        @property
        def bind_host(self) -> str:
            return self._bind_host

        @property
        def port(self) -> int:
            return self._port

        @property
        def is_running(self) -> bool:
            return self._is_running

        def start(self) -> None:
            if self._bind_host == "0.0.0.0":
                raise OtaServerServiceError("bind bloqueado por la plataforma")
            self._is_running = True

        def stop(self) -> None:
            self._is_running = False

    monkeypatch.setattr(
        "control_okua.services.ota_orchestrator_service.OtaServerService",
        _FlakyOtaServerService,
    )

    orchestrator = OtaOrchestratorService(
        runtime_client=runtime_client,
        manifest_service=manifest_service,
    )

    result = orchestrator.deploy(
        OtaDeployRequest(
            artifact_id=artifact.artifact_id,
            node_ids=[1],
            advertise_host="192.168.88.254",
            bind_host="0.0.0.0",
            port=18083,
            rollout_token="20260401",
        )
    )

    assert result.success is True
    assert started_hosts == ["0.0.0.0", "192.168.88.254"]
    assert orchestrator.ota_server_service is not None
    assert orchestrator.ota_server_service.bind_host == "192.168.88.254"
    assert any("192.168.88.254:18083" in warning for warning in result.warnings)


def test_orchestrator_probes_port_before_publish_and_uses_fallback_when_blocked(
    tmp_path: Path, monkeypatch
) -> None:
    """Cuando el puerto preferido está bloqueado (WinError 10013), _find_available_port
    debe elegir un puerto alternativo ANTES de publicar el manifest, de forma que la
    URL del manifest y el servidor coincidan en el puerto real disponible."""
    import socket as _socket

    artifact, manifest_service = _import_artifact(tmp_path)
    runtime_client = _FakeRuntimeClient(
        snapshots=[_snapshot(1, resolved_ip="192.168.88.101")],
        control_results={
            1: _control_result(
                node_id=1,
                node_ip="192.168.88.101",
                final_status=ControlTransactionFinalStatus.ACK_MATCHED,
            )
        },
    )

    # Puerto elegido que "funcionará" — primer fallback en _FALLBACK_OTA_PORTS
    BLOCKED_PORT = 19080
    AVAILABLE_PORT = 18080

    original_socket_class = _socket.socket

    class _ProbingSocket:
        """Socket falso: falla al bind en BLOCKED_PORT, acepta en AVAILABLE_PORT."""

        def __init__(self, *args, **kwargs):
            self._inner = original_socket_class(*args, **kwargs)

        def setsockopt(self, *a, **k):
            return self._inner.setsockopt(*a, **k)

        def bind(self, addr):
            host, port = addr
            if port == BLOCKED_PORT:
                err = OSError(10013, "Acceso denegado")
                err.winerror = 10013  # type: ignore[attr-defined]
                raise err
            return self._inner.bind(addr)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            self._inner.close()

        def close(self):
            self._inner.close()

    monkeypatch.setattr(
        "control_okua.services.ota_orchestrator_service.socket.socket",
        _ProbingSocket,
    )

    fake_server = _FakeOtaServerService(
        root_dir=manifest_service.publish_root_dir,
        bind_host="0.0.0.0",
        port=AVAILABLE_PORT,
    )
    orchestrator = OtaOrchestratorService(
        runtime_client=runtime_client,
        manifest_service=manifest_service,
        ota_server_service=fake_server,
    )

    result = orchestrator.deploy(
        OtaDeployRequest(
            artifact_id=artifact.artifact_id,
            node_ids=[1],
            advertise_host="192.168.88.254",
            bind_host="0.0.0.0",
            port=BLOCKED_PORT,
            rollout_token="20260418",
        )
    )

    assert result.success is True, f"deploy falló: {result.errors}"
    # El manifest debe haberse publicado con el puerto de respaldo
    assert f":{AVAILABLE_PORT}/" in result.manifest_url, (
        f"manifest_url debería tener :{AVAILABLE_PORT}/ pero es {result.manifest_url!r}"
    )
    assert f":{BLOCKED_PORT}/" not in result.manifest_url
    # Debe haber un aviso que mencione el cambio de puerto
    assert any(str(BLOCKED_PORT) in w and str(AVAILABLE_PORT) in w for w in result.warnings), (
        f"Se esperaba advertencia sobre cambio de puerto en warnings={result.warnings!r}"
    )
