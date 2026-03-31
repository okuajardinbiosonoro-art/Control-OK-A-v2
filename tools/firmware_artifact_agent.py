from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from control_okua.core.firmware import (  # noqa: E402
    ArtifactAgentService,
    ArtifactBuildResult,
    DEFAULT_COMPARATIVE_FRUIT_NODE,
    DEFAULT_PLANT_TEST_NODES,
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
    parser.error(f"Comando no soportado: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
