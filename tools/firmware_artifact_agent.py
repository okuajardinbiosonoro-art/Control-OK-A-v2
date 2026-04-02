from __future__ import annotations

import argparse
from dataclasses import replace
import json
import ipaddress
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from control_okua.core.firmware import (  # noqa: E402
    ArtifactAgentService,
    ArtifactBuildResult,
    DEFAULT_BANK_PROBE_NODE,
    DEFAULT_COMPARATIVE_FRUIT_NODE,
    DEFAULT_FIRST_PHYSICAL_TEST_NODE,
    DEFAULT_PLANT_TEST_NODES,
    FirmwareCatalogStore,
    resolve_firmware_catalog_path,
    resolve_artifact_agent_output_root,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Agente operativo OTA-A para planificar y generar artifacts situational.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser(
        "audit",
        help="Audita el firmware actual del repo y reporta identidad/protocolo base.",
    )
    audit_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Formatea la salida JSON con indentación.",
    )

    build_parser_cmd = subparsers.add_parser(
        "build-situational",
        help="Genera los artifacts situational OTA-A (planta actual + fruta comparativa).",
    )
    build_parser_cmd.add_argument(
        "--platformio-exe",
        help="Ruta explícita a platformio.exe si no está en PATH.",
    )
    build_parser_cmd.add_argument(
        "--output-root",
        help="Directorio raíz donde se exportarán los bins y sidecars.",
    )
    build_parser_cmd.add_argument(
        "--fruit-node-label",
        default=DEFAULT_COMPARATIVE_FRUIT_NODE[0],
        help="Etiqueta del nodo usado para el artifact comparativo de fruta.",
    )
    build_parser_cmd.add_argument(
        "--fruit-node-id",
        type=int,
        default=DEFAULT_COMPARATIVE_FRUIT_NODE[1],
        help="node_id del nodo usado para el artifact comparativo de fruta.",
    )
    build_parser_cmd.add_argument(
        "--import-generated",
        action="store_true",
        help="Importa localmente los artifacts generados al catálogo gestionado.",
    )
    build_parser_cmd.add_argument(
        "--pretty",
        action="store_true",
        help="Formatea la salida JSON con indentación.",
    )

    physical_parser = subparsers.add_parser(
        "build-first-physical-test",
        help=(
            "Prepara el primer ensayo OTA físico: identifica baseline actual del nodo "
            "de prueba y genera un comparativo OTA-compatible."
        ),
    )
    physical_parser.add_argument(
        "--platformio-exe",
        help="Ruta explícita a platformio.exe si no está en PATH.",
    )
    physical_parser.add_argument(
        "--output-root",
        help="Directorio raíz donde se exportará el comparativo OTA-compatible.",
    )
    physical_parser.add_argument(
        "--node-label",
        default=DEFAULT_FIRST_PHYSICAL_TEST_NODE[0],
        help="Etiqueta del nodo físico de prueba.",
    )
    physical_parser.add_argument(
        "--node-id",
        type=int,
        default=DEFAULT_FIRST_PHYSICAL_TEST_NODE[1],
        help="node_id del nodo físico de prueba.",
    )
    physical_parser.add_argument(
        "--comparative-version",
        help="Versión semver explícita para el comparativo compatible.",
    )
    physical_parser.add_argument(
        "--import-generated",
        action="store_true",
        help="Importa localmente el comparativo generado al catálogo gestionado.",
    )
    physical_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Formatea la salida JSON con indentación.",
    )

    probe_parser = subparsers.add_parser(
        "build-bank-probe-set",
        help=(
            "Genera un baseline actual + un probe observable OTA-compatible para banco "
            "sobre el nodo seleccionado."
        ),
    )
    probe_parser.add_argument(
        "--platformio-exe",
        help="Ruta explícita a platformio.exe si no está en PATH.",
    )
    probe_parser.add_argument(
        "--output-root",
        help="Directorio raíz donde se exportarán el baseline y el probe.",
    )
    probe_parser.add_argument(
        "--node-label",
        default=DEFAULT_BANK_PROBE_NODE[0],
        help="Etiqueta del nodo físico de banco.",
    )
    probe_parser.add_argument(
        "--node-id",
        type=int,
        default=DEFAULT_BANK_PROBE_NODE[1],
        help="node_id del nodo físico de banco.",
    )
    probe_parser.add_argument(
        "--probe-version",
        help="Versión semver explícita para el probe observable.",
    )
    probe_parser.add_argument(
        "--import-generated",
        action="store_true",
        help="Importa localmente los artifacts generados al catálogo gestionado.",
    )
    probe_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Formatea la salida JSON con indentación.",
    )

    network_parser = subparsers.add_parser(
        "build-network-bank-set",
        help=(
            "Genera un baseline actual + probe observable para un perfil de red concreto "
            "sin dejar las credenciales en texto plano en el sidecar exportado."
        ),
    )
    network_parser.add_argument("--platformio-exe", help="Ruta explícita a platformio.exe si no está en PATH.")
    network_parser.add_argument("--output-root", help="Directorio raíz donde se exportarán los artifacts.")
    network_parser.add_argument("--node-label", default=DEFAULT_BANK_PROBE_NODE[0], help="Etiqueta del nodo.")
    network_parser.add_argument("--node-id", type=int, default=DEFAULT_BANK_PROBE_NODE[1], help="node_id del nodo.")
    network_parser.add_argument("--network-name", required=True, help="Etiqueta corta de la red, por ejemplo MARIANA o MIKROTIK.")
    network_parser.add_argument("--wifi-ssid", required=True, help="SSID embebido en el firmware.")
    network_parser.add_argument("--wifi-pass", required=True, help="Password embebido en el firmware.")
    network_parser.add_argument("--control-secret", required=True, help="OKUA_CONTROL_SECRET embebido en el firmware.")
    network_parser.add_argument("--pc-ip", required=True, help="IPv4 del host CKv2 visible al nodo en esa red.")
    network_parser.add_argument("--wifi-channel", type=int, default=13, help="Canal Wi-Fi a fijar en el firmware.")
    network_parser.add_argument("--probe-version", default="1.0.1-dev", help="Versión semver del probe observable.")
    network_parser.add_argument("--import-generated", action="store_true", help="Importa localmente los artifacts generados al catálogo.")
    network_parser.add_argument("--pretty", action="store_true", help="Formatea la salida JSON con indentación.")
    return parser


def command_audit(service: ArtifactAgentService, *, pretty: bool) -> int:
    audit = service.audit_current_firmware()
    print(json.dumps(audit.to_dict(), ensure_ascii=False, indent=2 if pretty else None))
    return 0


def command_build_situational(
    service: ArtifactAgentService,
    *,
    platformio_exe: str | None,
    output_root: str | None,
    fruit_node_label: str,
    fruit_node_id: int,
    import_generated: bool,
    pretty: bool,
) -> int:
    audit = service.audit_current_firmware()
    publish_root = (
        Path(output_root).expanduser().resolve()
        if output_root is not None
        else resolve_artifact_agent_output_root(service.repo_root) / "2026-03-31_situational_builds"
    )
    plans = service.build_default_situational_plans(
        audit=audit,
        plant_nodes=DEFAULT_PLANT_TEST_NODES,
        fruit_node=(fruit_node_label, fruit_node_id),
    )
    results: list[ArtifactBuildResult] = []
    for plan in plans:
        result = service.build_artifact(
            plan,
            output_root=publish_root,
            platformio_executable=platformio_exe,
            clean=True,
        )
        if import_generated:
            import_result = service.import_artifact(result)
            result = ArtifactBuildResult(
                plan=result.plan,
                output_dir=result.output_dir,
                binary_path=result.binary_path,
                override_header_path=result.override_header_path,
                metadata_path=result.metadata_path,
                sha256=result.sha256,
                file_size=result.file_size,
                artifact_id=result.artifact_id,
                imported=True,
                import_result=import_result,
            )
        results.append(result)

    payload = {
        "audit": audit.to_dict(),
        "output_root": str(publish_root),
        "artifacts": [item.to_result_dict() for item in results],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None))
    return 0


def _artifact_summary(artifact) -> dict[str, object] | None:
    if artifact is None:
        return None
    return {
        "artifact_id": artifact.artifact_id,
        "display_name": artifact.display_name,
        "version": artifact.version,
        "version_label": artifact.version_label,
        "target_kind": artifact.target_kind.value,
        "target_variant": artifact.target_variant,
        "status": artifact.status.value,
        "file_path": artifact.file_path,
        "sha256": artifact.sha256,
        "tags": list(artifact.tags),
        "notes": artifact.notes,
        "changelog": artifact.changelog,
    }


def command_build_first_physical_test(
    service: ArtifactAgentService,
    *,
    platformio_exe: str | None,
    output_root: str | None,
    node_label: str,
    node_id: int,
    comparative_version: str | None,
    import_generated: bool,
    pretty: bool,
) -> int:
    audit = service.audit_current_firmware()
    catalog_store = FirmwareCatalogStore(resolve_firmware_catalog_path())
    catalog_store.load()
    publish_root = (
        Path(output_root).expanduser().resolve()
        if output_root is not None
        else resolve_artifact_agent_output_root(service.repo_root) / "2026-03-31_first_physical_ota_test"
    )
    baseline_plan, comparative_plan = service.build_first_physical_test_plans(
        audit=audit,
        catalog_store=catalog_store,
        node_label=node_label,
        node_id=node_id,
        comparative_version=comparative_version,
    )
    baseline_artifact = service.resolve_catalog_artifact(
        node_label=node_label,
        target_kind=audit.default_target_kind,
        catalog_store=catalog_store,
        version=baseline_plan.version,
    )
    fruit_artifact = service.resolve_catalog_artifact(
        node_label=node_label,
        target_kind="fruit",
        catalog_store=catalog_store,
    )
    comparative_result = service.build_artifact(
        comparative_plan,
        output_root=publish_root,
        platformio_executable=platformio_exe,
        clean=True,
    )
    if import_generated:
        import_result = service.import_artifact(
            comparative_result,
            catalog_store=catalog_store,
        )
        comparative_result = ArtifactBuildResult(
            plan=comparative_result.plan,
            output_dir=comparative_result.output_dir,
            binary_path=comparative_result.binary_path,
            override_header_path=comparative_result.override_header_path,
            metadata_path=comparative_result.metadata_path,
            sha256=comparative_result.sha256,
            file_size=comparative_result.file_size,
            artifact_id=comparative_result.artifact_id,
            imported=True,
            import_result=import_result,
        )

    warnings: list[str] = []
    if baseline_artifact is None:
        warnings.append(
            "No se encontró en el catálogo local un baseline situational/current_clone para este nodo; "
            "usa baseline_plan para regenerarlo o impórtalo antes del ensayo físico."
        )
    if fruit_artifact is not None:
        warnings.append(
            "Existe un artifact fruit comparativo para este nodo; es útil para comparación de comportamiento, "
            "pero no debe usarse como primera OTA física sobre baseline plant."
        )
    payload = {
        "audit": audit.to_dict(),
        "selected_test_node": {
            "node_label": node_label.upper(),
            "node_id": int(node_id),
        },
        "baseline_plan": baseline_plan.to_plan_dict(),
        "baseline_artifact": _artifact_summary(baseline_artifact),
        "compatible_comparative": comparative_result.to_result_dict(),
        "fruit_comparative_artifact": _artifact_summary(fruit_artifact),
        "output_root": str(publish_root),
        "warnings": warnings,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None))
    return 0


def command_build_bank_probe_set(
    service: ArtifactAgentService,
    *,
    platformio_exe: str | None,
    output_root: str | None,
    node_label: str,
    node_id: int,
    probe_version: str | None,
    import_generated: bool,
    pretty: bool,
) -> int:
    audit = service.audit_current_firmware()
    catalog_store = FirmwareCatalogStore(resolve_firmware_catalog_path())
    catalog_store.load()
    publish_root = (
        Path(output_root).expanduser().resolve()
        if output_root is not None
        else resolve_artifact_agent_output_root(service.repo_root) / "2026-04-01_bank_probe_set"
    )
    baseline_plan, probe_plan = service.build_bank_probe_plans(
        audit=audit,
        catalog_store=catalog_store,
        node_label=node_label,
        node_id=node_id,
        probe_version=probe_version,
    )
    results: list[ArtifactBuildResult] = []
    for plan in (baseline_plan, probe_plan):
        result = service.build_artifact(
            plan,
            output_root=publish_root,
            platformio_executable=platformio_exe,
            clean=True,
        )
        if import_generated:
            import_result = service.import_artifact(
                result,
                catalog_store=catalog_store,
            )
            result = ArtifactBuildResult(
                plan=result.plan,
                output_dir=result.output_dir,
                binary_path=result.binary_path,
                override_header_path=result.override_header_path,
                metadata_path=result.metadata_path,
                sha256=result.sha256,
                file_size=result.file_size,
                artifact_id=result.artifact_id,
                imported=True,
                import_result=import_result,
            )
        results.append(result)
    payload = {
        "audit": audit.to_dict(),
        "selected_test_node": {
            "node_label": node_label.upper(),
            "node_id": int(node_id),
        },
        "output_root": str(publish_root),
        "artifacts": [item.to_result_dict() for item in results],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None))
    return 0


def _network_key(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def _network_display(value: str) -> str:
    return value.strip().upper()


def _pc_ip_override_lines(ip_text: str) -> tuple[str, ...]:
    ip = ipaddress.IPv4Address(ip_text.strip())
    octets = str(ip).split(".")
    return (
        f"#define PC_IP_A {octets[0]}",
        f"#define PC_IP_B {octets[1]}",
        f"#define PC_IP_C {octets[2]}",
        f"#define PC_IP_D {octets[3]}",
    )


def _build_network_overrides(
    *,
    wifi_ssid: str,
    wifi_pass: str,
    control_secret: str,
    wifi_channel: int,
    pc_ip: str,
    redact_sensitive: bool,
) -> tuple[str, ...]:
    if wifi_channel < 0 or wifi_channel > 13:
        raise ValueError(f"wifi_channel fuera de rango: {wifi_channel}")
    password_value = "<redacted>" if redact_sensitive else wifi_pass
    secret_value = "<redacted>" if redact_sensitive else control_secret
    return (
        f'#define OKUA_BUILD_WIFI_SSID "{wifi_ssid}"',
        f'#define OKUA_BUILD_WIFI_PASS "{password_value}"',
        f'#define OKUA_BUILD_CONTROL_SECRET "{secret_value}"',
        f"#define OKUA_BUILD_WIFI_CHANNEL {wifi_channel}",
        *(line.replace("PC_IP_", "OKUA_BUILD_PC_IP_") for line in _pc_ip_override_lines(pc_ip)),
    )


def command_build_network_bank_set(
    service: ArtifactAgentService,
    *,
    platformio_exe: str | None,
    output_root: str | None,
    node_label: str,
    node_id: int,
    network_name: str,
    wifi_ssid: str,
    wifi_pass: str,
    control_secret: str,
    pc_ip: str,
    wifi_channel: int,
    probe_version: str,
    import_generated: bool,
    pretty: bool,
) -> int:
    audit = service.audit_current_firmware()
    catalog_store = FirmwareCatalogStore(resolve_firmware_catalog_path())
    catalog_store.load()
    network_display = _network_display(network_name)
    network_key = _network_key(network_name)
    publish_root = (
        Path(output_root).expanduser().resolve()
        if output_root is not None
        else resolve_artifact_agent_output_root(service.repo_root) / f"2026-04-01_{network_key}_bank_set"
    )
    baseline_plan, probe_plan = service.build_bank_probe_plans(
        audit=audit,
        catalog_store=catalog_store,
        node_label=node_label,
        node_id=node_id,
        probe_version=probe_version,
    )
    plans = (
        replace(
            baseline_plan,
            display_name=f"OKUA Node UDP v1 - {node_label.upper()} planta prueba actual [{network_display}] ({baseline_plan.version})",
            source_notes=f"{baseline_plan.source_notes} Perfil de red: {network_display}.",
            notes=f"{baseline_plan.notes} Red embebida: {network_display} ({wifi_ssid}, canal {wifi_channel}, PC_IP={pc_ip}).",
            tags=tuple((*baseline_plan.tags, f"network_{network_key}")),
            output_slug=f"{baseline_plan.output_slug}-{network_key}",
            output_file_name=f"{baseline_plan.output_slug}-{network_key}.bin",
        ),
        replace(
            probe_plan,
            display_name=f"OKUA Node UDP v1 - {node_label.upper()} planta prueba sonda observable OTA-compatible [{network_display}] ({probe_plan.version})",
            source_notes=f"{probe_plan.source_notes} Perfil de red: {network_display}.",
            notes=f"{probe_plan.notes} Red embebida: {network_display} ({wifi_ssid}, canal {wifi_channel}, PC_IP={pc_ip}).",
            tags=tuple((*probe_plan.tags, f"network_{network_key}")),
            output_slug=f"{probe_plan.output_slug}-{network_key}",
            output_file_name=f"{probe_plan.output_slug}-{network_key}.bin",
        ),
    )
    compile_network_lines = _build_network_overrides(
        wifi_ssid=wifi_ssid,
        wifi_pass=wifi_pass,
        control_secret=control_secret,
        wifi_channel=wifi_channel,
        pc_ip=pc_ip,
        redact_sensitive=False,
    )
    exported_network_lines = _build_network_overrides(
        wifi_ssid=wifi_ssid,
        wifi_pass=wifi_pass,
        control_secret=control_secret,
        wifi_channel=wifi_channel,
        pc_ip=pc_ip,
        redact_sensitive=True,
    )
    results: list[ArtifactBuildResult] = []
    for plan in plans:
        result = service.build_artifact(
            plan,
            output_root=publish_root,
            platformio_executable=platformio_exe,
            clean=True,
            extra_override_lines=compile_network_lines,
            exported_override_lines=tuple(plan.override_header_lines) + exported_network_lines,
        )
        if import_generated:
            import_result = service.import_artifact(
                result,
                catalog_store=catalog_store,
            )
            result = ArtifactBuildResult(
                plan=result.plan,
                output_dir=result.output_dir,
                binary_path=result.binary_path,
                override_header_path=result.override_header_path,
                metadata_path=result.metadata_path,
                sha256=result.sha256,
                file_size=result.file_size,
                artifact_id=result.artifact_id,
                imported=True,
                import_result=import_result,
            )
        results.append(result)
    payload = {
        "audit": audit.to_dict(),
        "selected_test_node": {
            "node_label": node_label.upper(),
            "node_id": int(node_id),
        },
        "network_profile": {
            "network_name": network_display,
            "wifi_ssid": wifi_ssid,
            "pc_ip": pc_ip,
            "wifi_channel": wifi_channel,
        },
        "output_root": str(publish_root),
        "artifacts": [item.to_result_dict() for item in results],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    service = ArtifactAgentService(REPO_ROOT)

    if args.command == "audit":
        return command_audit(service, pretty=args.pretty)
    if args.command == "build-situational":
        return command_build_situational(
            service,
            platformio_exe=args.platformio_exe,
            output_root=args.output_root,
            fruit_node_label=args.fruit_node_label,
            fruit_node_id=args.fruit_node_id,
            import_generated=args.import_generated,
            pretty=args.pretty,
        )
    if args.command == "build-first-physical-test":
        return command_build_first_physical_test(
            service,
            platformio_exe=args.platformio_exe,
            output_root=args.output_root,
            node_label=args.node_label,
            node_id=args.node_id,
            comparative_version=args.comparative_version,
            import_generated=args.import_generated,
            pretty=args.pretty,
        )
    if args.command == "build-bank-probe-set":
        return command_build_bank_probe_set(
            service,
            platformio_exe=args.platformio_exe,
            output_root=args.output_root,
            node_label=args.node_label,
            node_id=args.node_id,
            probe_version=args.probe_version,
            import_generated=args.import_generated,
            pretty=args.pretty,
        )
    if args.command == "build-network-bank-set":
        return command_build_network_bank_set(
            service,
            platformio_exe=args.platformio_exe,
            output_root=args.output_root,
            node_label=args.node_label,
            node_id=args.node_id,
            network_name=args.network_name,
            wifi_ssid=args.wifi_ssid,
            wifi_pass=args.wifi_pass,
            control_secret=args.control_secret,
            pc_ip=args.pc_ip,
            wifi_channel=args.wifi_channel,
            probe_version=args.probe_version,
            import_generated=args.import_generated,
            pretty=args.pretty,
        )
    parser.error(f"Comando no soportado: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
