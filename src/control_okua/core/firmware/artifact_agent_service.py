from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import ctypes
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Iterable

from control_okua.core.firmware.catalog_models import (
    FirmwareStatus,
    FirmwareTargetKind,
    build_artifact_id,
    normalize_key,
    normalize_target_kind,
    normalize_target_variant,
    normalize_text,
    utc_now_iso,
)
from control_okua.core.firmware.catalog_store import (
    FirmwareCatalogStore,
    resolve_firmware_catalog_path,
)
from control_okua.core.firmware.ingest_models import FirmwareImportRequest, FirmwareImportResult
from control_okua.core.firmware.ingest_service import (
    DEFAULT_MANAGED_FIRMWARE_STORE_DIRNAME,
    FirmwareIngestService,
)
from control_okua.core.firmware.ota_manifest_models import (
    DEFAULT_OTA_COMPATIBLE_HW,
    DEFAULT_OTA_FIRMWARE_FAMILY,
    DEFAULT_OTA_PROTOCOL_VERSION,
    derive_version_code,
)


DEFAULT_ARTIFACT_AGENT_OUTPUT_DIRNAME = "ota_artifact_agent"
DEFAULT_ARTIFACT_AGENT_PLATFORMIO_ENV = "okua_node_esp32dev"
DEFAULT_PLANT_TEST_NODES = (
    ("EB1", 1),
    ("EC1", 2),
    ("ED1", 3),
)
DEFAULT_FIRST_PHYSICAL_TEST_NODE = ("ED1", 3)
DEFAULT_BANK_PROBE_NODE = ("ED1", 3)
DEFAULT_COMPARATIVE_FRUIT_NODE = ("ED1", 3)
_SEMVER_PATTERN = re.compile(
    r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?P<suffix>(?:[-+][0-9A-Za-z._-]+)?)$"
)


class ArtifactIntent(str, Enum):
    CURRENT_CLONE = "current_clone"
    COMPARATIVE = "comparative"
    OBSERVABLE_PROBE = "observable_probe"


class ArtifactAgentError(RuntimeError):
    """Base error for OTA artifact-agent operations."""


class ArtifactAgentValidationError(ArtifactAgentError):
    """Raised when an artifact plan request is invalid."""


class ArtifactAgentBuildError(ArtifactAgentError):
    """Raised when a build/export operation fails."""


@dataclass(frozen=True)
class ArtifactSourceAudit:
    repo_root: str
    platformio_env: str
    source_file: str
    default_version: str
    default_version_code: int
    default_build_profile: str
    default_target_kind: FirmwareTargetKind
    firmware_family: str
    protocol_version: str
    compatible_hw: tuple[str, ...]
    identity_scope: str
    identity_scope_reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "repo_root": self.repo_root,
            "platformio_env": self.platformio_env,
            "source_file": self.source_file,
            "default_version": self.default_version,
            "default_version_code": self.default_version_code,
            "default_build_profile": self.default_build_profile,
            "default_target_kind": self.default_target_kind.value,
            "firmware_family": self.firmware_family,
            "protocol_version": self.protocol_version,
            "compatible_hw": list(self.compatible_hw),
            "identity_scope": self.identity_scope,
            "identity_scope_reason": self.identity_scope_reason,
        }


@dataclass(frozen=True)
class ArtifactPlanRequest:
    intent: ArtifactIntent | str
    node_label: str
    node_id: int
    target_kind: FirmwareTargetKind | str | None = None
    version: str | None = None
    version_label: str = ""
    display_name: str = ""
    status: FirmwareStatus | str | None = None
    changelog_short: str = ""
    notes: str = ""
    source_notes: str = ""
    tags: tuple[str, ...] | list[str] = field(default_factory=tuple)
    build_profile: str | None = None
    source_kind: str = "artifact_agent"

    def __post_init__(self) -> None:
        normalized_label = normalize_text(self.node_label).upper()
        if not normalized_label:
            raise ArtifactAgentValidationError("node_label es obligatorio")
        try:
            normalized_node_id = int(self.node_id)
        except (TypeError, ValueError) as exc:
            raise ArtifactAgentValidationError(
                f"node_id invalido: {self.node_id!r}"
            ) from exc
        if normalized_node_id <= 0:
            raise ArtifactAgentValidationError("node_id debe ser > 0")
        object.__setattr__(self, "node_label", normalized_label)
        object.__setattr__(self, "node_id", normalized_node_id)
        object.__setattr__(self, "version_label", normalize_text(self.version_label))
        object.__setattr__(self, "display_name", normalize_text(self.display_name))
        object.__setattr__(self, "changelog_short", normalize_text(self.changelog_short))
        object.__setattr__(self, "notes", normalize_text(self.notes))
        object.__setattr__(self, "source_notes", normalize_text(self.source_notes))
        object.__setattr__(
            self,
            "tags",
            tuple(normalize_key(item) for item in self.tags if normalize_key(item)),
        )
        object.__setattr__(self, "build_profile", normalize_text(self.build_profile))
        object.__setattr__(self, "source_kind", normalize_key(self.source_kind) or "artifact_agent")


@dataclass(frozen=True)
class ArtifactBuildPlan:
    intent: ArtifactIntent
    node_label: str
    node_id: int
    version: str
    version_code: int
    version_label: str
    display_name: str
    target_kind: FirmwareTargetKind
    target_variant: str
    status: FirmwareStatus
    build_profile: str
    changelog_short: str
    notes: str
    source_notes: str
    source_kind: str
    tags: tuple[str, ...]
    compatibility: tuple[str, ...]
    firmware_family: str
    protocol_version: str
    platformio_env: str
    output_slug: str
    output_file_name: str
    override_header_lines: tuple[str, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_plan_dict(self) -> dict[str, object]:
        return {
            "intent": self.intent.value,
            "node_label": self.node_label,
            "node_id": self.node_id,
            "version": self.version,
            "version_code": self.version_code,
            "version_label": self.version_label,
            "display_name": self.display_name,
            "target_kind": self.target_kind.value,
            "target_variant": self.target_variant,
            "status": self.status.value,
            "build_profile": self.build_profile,
            "changelog_short": self.changelog_short,
            "notes": self.notes,
            "source_notes": self.source_notes,
            "source_kind": self.source_kind,
            "tags": list(self.tags),
            "compatibility": list(self.compatibility),
            "firmware_family": self.firmware_family,
            "protocol_version": self.protocol_version,
            "platformio_env": self.platformio_env,
            "output_slug": self.output_slug,
            "output_file_name": self.output_file_name,
            "override_header_lines": list(self.override_header_lines),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class ArtifactBuildResult:
    plan: ArtifactBuildPlan
    output_dir: str
    binary_path: str
    override_header_path: str
    metadata_path: str
    sha256: str
    file_size: int
    artifact_id: str
    imported: bool = False
    import_result: FirmwareImportResult | None = None

    def to_result_dict(self) -> dict[str, object]:
        payload = {
            "artifact_id": self.artifact_id,
            "sha256": self.sha256,
            "file_size": self.file_size,
            "output_dir": self.output_dir,
            "binary_path": self.binary_path,
            "override_header_path": self.override_header_path,
            "metadata_path": self.metadata_path,
            "imported": self.imported,
            "plan": self.plan.to_plan_dict(),
        }
        if self.import_result is not None:
            payload["import_result"] = {
                "success": self.import_result.success,
                "artifact_id": self.import_result.artifact_id,
                "was_duplicate": self.import_result.was_duplicate,
                "message": self.import_result.message,
                "warnings": list(self.import_result.warnings),
            }
        return payload

    def to_import_request(self, *, copy_to_managed_store: bool = True) -> FirmwareImportRequest:
        return FirmwareImportRequest(
            source_file_path=self.binary_path,
            display_name=self.plan.display_name,
            version=self.plan.version,
            version_label=self.plan.version_label,
            target_kind=self.plan.target_kind,
            target_variant=self.plan.target_variant,
            status=self.plan.status,
            source_kind=self.plan.source_kind,
            source_notes=self.plan.source_notes,
            changelog=self.plan.changelog_short,
            notes=self.plan.notes,
            compatibility=self.plan.compatibility,
            tags=self.plan.tags,
            mark_as_current=False,
            copy_to_managed_store=copy_to_managed_store,
        )


def resolve_artifact_agent_output_root(repo_root: Path | str | None = None) -> Path:
    if repo_root is None:
        base_dir = Path(__file__).resolve().parents[4]
    else:
        base_dir = Path(repo_root).expanduser().resolve()
    return base_dir / "artifacts" / DEFAULT_ARTIFACT_AGENT_OUTPUT_DIRNAME


class ArtifactAgentService:
    def __init__(self, repo_root: Path | str | None = None) -> None:
        self._repo_root = (
            Path(repo_root).expanduser().resolve()
            if repo_root is not None
            else Path(__file__).resolve().parents[4]
        )
        self._platformio_ini_path = self._repo_root / "platformio.ini"
        self._firmware_source_path = (
            self._repo_root / "firmware" / "okua_node_udp_v1" / "okua_node_udp_v1.ino"
        )

    @property
    def repo_root(self) -> Path:
        return self._repo_root

    @property
    def firmware_source_path(self) -> Path:
        return self._firmware_source_path

    def audit_current_firmware(self) -> ArtifactSourceAudit:
        platformio_text = self._read_text(self._platformio_ini_path)
        source_text = self._read_text(self._firmware_source_path)
        default_env = self._extract_platformio_default_env(platformio_text)
        default_version = self._extract_string_define(source_text, "OKUA_FW_VERSION_STR")
        default_build_profile = self._extract_build_profile(source_text)
        default_target_kind = self._extract_default_target_kind(source_text)
        identity_scope = "single_shared_bin"
        identity_scope_reason = "No se detectó identidad compile-time dependiente del nodo."
        if "NODE_LABEL," in source_text:
            identity_scope = "per_node_variant"
            identity_scope_reason = (
                "kOkuaBuildInfoConfig usa NODE_LABEL como target_variant; cada nodo compila "
                "un artifact distinto aunque el perfil funcional sea el mismo."
            )
        return ArtifactSourceAudit(
            repo_root=str(self._repo_root),
            platformio_env=default_env,
            source_file=str(self._firmware_source_path),
            default_version=default_version,
            default_version_code=derive_version_code(default_version),
            default_build_profile=default_build_profile,
            default_target_kind=default_target_kind,
            firmware_family=DEFAULT_OTA_FIRMWARE_FAMILY,
            protocol_version=DEFAULT_OTA_PROTOCOL_VERSION,
            compatible_hw=tuple(DEFAULT_OTA_COMPATIBLE_HW),
            identity_scope=identity_scope,
            identity_scope_reason=identity_scope_reason,
        )

    def build_plan(
        self,
        request: ArtifactPlanRequest,
        *,
        audit: ArtifactSourceAudit | None = None,
    ) -> ArtifactBuildPlan:
        resolved_audit = audit or self.audit_current_firmware()
        intent = self._coerce_intent(request.intent)
        target_kind = self._resolve_target_kind(intent, request.target_kind, resolved_audit)
        status = self._resolve_status(request.status)
        if status is not FirmwareStatus.SITUATIONAL:
            raise ArtifactAgentValidationError(
                "Todos los artifacts de prueba/comparación generados por OTA-A deben ser situational."
            )

        version = self._resolve_version(intent, request.version, resolved_audit)
        version_code = derive_version_code(version)
        major, minor, patch = self._parse_semver(version)
        target_variant = normalize_target_variant(request.node_label)
        build_profile = normalize_text(
            request.build_profile,
            fallback=resolved_audit.default_build_profile,
        )
        ota_compatible_comparative = (
            intent is ArtifactIntent.COMPARATIVE
            and target_kind is resolved_audit.default_target_kind
        )
        probe_artifact = intent is ArtifactIntent.OBSERVABLE_PROBE
        display_name = self._resolve_display_name(
            intent=intent,
            target_kind=target_kind,
            baseline_target_kind=resolved_audit.default_target_kind,
            node_label=request.node_label,
            version=version,
            explicit_value=request.display_name,
        )
        version_label = normalize_text(
            request.version_label,
            fallback=(
                f"v{version} probe observable situational"
                if probe_artifact
                else f"v{version} {'comparativo' if intent is ArtifactIntent.COMPARATIVE else 'baseline'} situational"
            ),
        )
        changelog_short = normalize_text(
            request.changelog_short,
            fallback=self._default_changelog(
                intent,
                target_kind,
                ota_compatible=ota_compatible_comparative,
            ),
        )
        notes = normalize_text(
            request.notes,
            fallback=self._default_notes(
                intent,
                target_kind,
                request.node_label,
                build_profile=build_profile,
                ota_compatible=ota_compatible_comparative,
                baseline_target_kind=resolved_audit.default_target_kind,
            ),
        )
        source_notes = normalize_text(
            request.source_notes,
            fallback=self._default_source_notes(
                intent,
                request.node_label,
                ota_compatible=ota_compatible_comparative,
            ),
        )

        warnings: list[str] = []
        if target_kind is FirmwareTargetKind.FRUIT and resolved_audit.default_target_kind is FirmwareTargetKind.PLANT:
            warnings.append(
                "El artifact comparativo de fruta no será OTA-compatible sobre un baseline actual de planta; "
                "target_kind difiere y el firmware rechazará ese manifest."
            )
        if ota_compatible_comparative:
            warnings.append(
                "El artifact comparativo mantiene target_kind, target_variant y build_profile del baseline; "
                "el cambio observable esperado es la nueva version/artifact_id para validar OTA física real."
            )
        if probe_artifact:
            warnings.append(
                "El artifact probe observable mantiene compatibilidad OTA con el baseline y agrega "
                "blink LED + notas ascendentes para verificación física de banco."
            )
        if build_profile != resolved_audit.default_build_profile:
            warnings.append(
                "El build_profile solicitado difiere del baseline actual del repo; confirma compatibilidad OTA antes de desplegar."
            )

        tags = self._resolve_tags(
            intent=intent,
            target_kind=target_kind,
            target_variant=target_variant,
            build_profile=build_profile,
            ota_compatible=ota_compatible_comparative,
            explicit_tags=request.tags,
        )
        output_slug = self._build_output_slug(
            intent=intent,
            target_kind=target_kind,
            target_variant=target_variant,
            version=version,
        )
        output_file_name = f"{output_slug}.bin"
        override_header_lines = (
            "#pragma once",
            f'#define OKUA_BUILD_NODE_LABEL "{request.node_label}"',
            f"#define OKUA_BUILD_NODE_ID {request.node_id}",
            f"#define ACTIVE_MODE {'MODE_FIELD' if build_profile == 'field' else 'MODE_TEST'}",
            f"#define ACTIVE_SENSOR {'SENSOR_FRUIT' if target_kind is FirmwareTargetKind.FRUIT else 'SENSOR_PLANT'}",
            f"#define FW_MAJOR {major}",
            f"#define FW_MINOR {minor}",
            f"#define FW_PATCH {patch}",
            f'#define OKUA_FW_VERSION_STR "{version}"',
            f"#define OKUA_FW_VERSION_CODE {version_code}",
        ) + (
            (
                "#define OKUA_TEST_PROBE_ENABLED 1",
                "#define OKUA_TEST_PROBE_LED_PIN 2",
                "#define OKUA_TEST_PROBE_INTERVAL_MS 1000UL",
                "#define OKUA_TEST_PROBE_NOTE_START 0",
                "#define OKUA_TEST_PROBE_NOTE_MAX 80",
            )
            if probe_artifact
            else tuple()
        )
        return ArtifactBuildPlan(
            intent=intent,
            node_label=request.node_label,
            node_id=request.node_id,
            version=version,
            version_code=version_code,
            version_label=version_label,
            display_name=display_name,
            target_kind=target_kind,
            target_variant=target_variant,
            status=status,
            build_profile=build_profile,
            changelog_short=changelog_short,
            notes=notes,
            source_notes=source_notes,
            source_kind=request.source_kind,
            tags=tags,
            compatibility=tuple(DEFAULT_OTA_COMPATIBLE_HW),
            firmware_family=resolved_audit.firmware_family,
            protocol_version=resolved_audit.protocol_version,
            platformio_env=resolved_audit.platformio_env,
            output_slug=output_slug,
            output_file_name=output_file_name,
            override_header_lines=override_header_lines,
            warnings=tuple(warnings),
        )

    def build_default_situational_plans(
        self,
        *,
        audit: ArtifactSourceAudit | None = None,
        plant_nodes: Iterable[tuple[str, int]] = DEFAULT_PLANT_TEST_NODES,
        fruit_node: tuple[str, int] = DEFAULT_COMPARATIVE_FRUIT_NODE,
    ) -> tuple[ArtifactBuildPlan, ...]:
        resolved_audit = audit or self.audit_current_firmware()
        plans: list[ArtifactBuildPlan] = []
        for node_label, node_id in plant_nodes:
            plans.append(
                self.build_plan(
                    ArtifactPlanRequest(
                        intent=ArtifactIntent.CURRENT_CLONE,
                        node_label=node_label,
                        node_id=node_id,
                    ),
                    audit=resolved_audit,
                )
            )
        fruit_label, fruit_node_id = fruit_node
        plans.append(
            self.build_plan(
                ArtifactPlanRequest(
                    intent=ArtifactIntent.COMPARATIVE,
                    node_label=fruit_label,
                    node_id=fruit_node_id,
                ),
                audit=resolved_audit,
            )
        )
        return tuple(plans)

    def build_first_physical_test_plans(
        self,
        *,
        audit: ArtifactSourceAudit | None = None,
        catalog_store: FirmwareCatalogStore | None = None,
        node_label: str = DEFAULT_FIRST_PHYSICAL_TEST_NODE[0],
        node_id: int = DEFAULT_FIRST_PHYSICAL_TEST_NODE[1],
        comparative_version: str | None = None,
    ) -> tuple[ArtifactBuildPlan, ArtifactBuildPlan]:
        resolved_audit = audit or self.audit_current_firmware()
        baseline_plan = self.build_plan(
            ArtifactPlanRequest(
                intent=ArtifactIntent.CURRENT_CLONE,
                node_label=node_label,
                node_id=node_id,
            ),
            audit=resolved_audit,
        )
        compatible_version = comparative_version or self.suggest_next_version_for_variant(
            node_label=node_label,
            catalog_store=catalog_store,
            audit=resolved_audit,
        )
        comparative_plan = self.build_plan(
            ArtifactPlanRequest(
                intent=ArtifactIntent.COMPARATIVE,
                node_label=node_label,
                node_id=node_id,
                target_kind=resolved_audit.default_target_kind,
                version=compatible_version,
                version_label=f"v{compatible_version} comparativo OTA situational",
                changelog_short=(
                    "Build comparativo situational de planta para validar la primera OTA física "
                    "compatible sobre el baseline actual."
                ),
                notes=(
                    "Artifact comparativo OTA-B para la primera prueba física. Mantiene "
                    "target_kind=plant, target_variant del nodo y build_profile del baseline; "
                    "el cambio observable esperado es version/artifact_id/sha256 nuevos."
                ),
                source_notes=(
                    f"Generado por artifact agent OTA-B como comparativo OTA-compatible para {normalize_text(node_label).upper()}."
                ),
                tags=("ota_b", "first_physical_test", "ota_compatible"),
            ),
            audit=resolved_audit,
        )
        return baseline_plan, comparative_plan

    def build_bank_probe_plans(
        self,
        *,
        audit: ArtifactSourceAudit | None = None,
        catalog_store: FirmwareCatalogStore | None = None,
        node_label: str = DEFAULT_BANK_PROBE_NODE[0],
        node_id: int = DEFAULT_BANK_PROBE_NODE[1],
        probe_version: str | None = None,
    ) -> tuple[ArtifactBuildPlan, ArtifactBuildPlan]:
        resolved_audit = audit or self.audit_current_firmware()
        baseline_plan = self.build_plan(
            ArtifactPlanRequest(
                intent=ArtifactIntent.CURRENT_CLONE,
                node_label=node_label,
                node_id=node_id,
            ),
            audit=resolved_audit,
        )
        resolved_probe_version = probe_version or self.suggest_next_version_for_variant(
            node_label=node_label,
            catalog_store=catalog_store,
            audit=resolved_audit,
        )
        probe_plan = self.build_plan(
            ArtifactPlanRequest(
                intent=ArtifactIntent.OBSERVABLE_PROBE,
                node_label=node_label,
                node_id=node_id,
                target_kind=resolved_audit.default_target_kind,
                version=resolved_probe_version,
            ),
            audit=resolved_audit,
        )
        return baseline_plan, probe_plan

    def resolve_catalog_artifact(
        self,
        *,
        node_label: str,
        target_kind: FirmwareTargetKind | str,
        catalog_store: FirmwareCatalogStore | None = None,
        version: str | None = None,
    ) -> FirmwareArtifact | None:
        store = catalog_store or FirmwareCatalogStore(resolve_firmware_catalog_path())
        store.load()
        normalized_variant = normalize_target_variant(node_label)
        candidates = store.filter_by_target(target_kind, normalized_variant)
        if version:
            candidates = [item for item in candidates if item.version == normalize_text(version)]
        if not candidates:
            return None
        preferred = sorted(
            candidates,
            key=lambda item: (
                0 if item.source_kind == "artifact_agent" else 1,
                0 if "current_clone" in item.tags else 1,
                item.imported_at_utc,
            ),
            reverse=False,
        )
        return preferred[0]

    def suggest_next_version_for_variant(
        self,
        *,
        node_label: str,
        catalog_store: FirmwareCatalogStore | None = None,
        audit: ArtifactSourceAudit | None = None,
    ) -> str:
        resolved_audit = audit or self.audit_current_firmware()
        major, minor, patch, suffix = self._parse_semver_with_suffix(resolved_audit.default_version)
        max_components = (major, minor, patch)
        suffix_candidate = suffix
        store = catalog_store or FirmwareCatalogStore(resolve_firmware_catalog_path())
        store.load()
        normalized_variant = normalize_target_variant(node_label)
        for artifact in store.list_all():
            if artifact.target_variant != normalized_variant:
                continue
            try:
                artifact_major, artifact_minor, artifact_patch, artifact_suffix = (
                    self._parse_semver_with_suffix(artifact.version)
                )
            except ArtifactAgentValidationError:
                continue
            candidate_components = (artifact_major, artifact_minor, artifact_patch)
            if candidate_components >= max_components:
                max_components = candidate_components
                suffix_candidate = artifact_suffix
        next_patch = max_components[2] + 1
        resolved_suffix = suffix_candidate or suffix
        return f"{max_components[0]}.{max_components[1]}.{next_patch}{resolved_suffix}"

    def build_artifact(
        self,
        plan: ArtifactBuildPlan,
        *,
        output_root: Path | str | None = None,
        platformio_executable: str | None = None,
        clean: bool = True,
        extra_override_lines: Iterable[str] = (),
        exported_override_lines: Iterable[str] | None = None,
    ) -> ArtifactBuildResult:
        resolved_output_root = (
            Path(output_root).expanduser().resolve()
            if output_root is not None
            else resolve_artifact_agent_output_root(self._repo_root) / utc_now_iso().replace(":", "-")
        )
        output_dir = resolved_output_root / plan.output_slug
        output_dir.mkdir(parents=True, exist_ok=True)
        build_work_dir = self._resolve_platformio_work_dir(plan.output_slug)
        build_work_dir.mkdir(parents=True, exist_ok=True)
        build_override_header_path = build_work_dir / "artifact_build_overrides.h"
        compile_override_lines = tuple(plan.override_header_lines) + tuple(extra_override_lines)
        export_override_lines = (
            tuple(exported_override_lines)
            if exported_override_lines is not None
            else compile_override_lines
        )
        build_override_header_path.write_text(
            "\n".join(compile_override_lines) + "\n",
            encoding="utf-8",
        )
        platformio_bin = self._resolve_platformio_executable(platformio_executable)
        include_path = self._platformio_include_path(build_override_header_path)
        build_project_conf_path = self._write_project_conf(plan.platformio_env, include_path, build_work_dir)

        if clean:
            self._run_platformio(
                platformio_bin,
                ["run", "--project-conf", str(build_project_conf_path), "-e", plan.platformio_env, "-t", "clean"],
            )
        self._run_platformio(
            platformio_bin,
            ["run", "--project-conf", str(build_project_conf_path), "-e", plan.platformio_env],
        )

        built_bin_path = self._repo_root / ".pio" / "build" / plan.platformio_env / "firmware.bin"
        if not built_bin_path.exists():
            raise ArtifactAgentBuildError(
                f"No se encontró firmware.bin tras compilar '{plan.output_slug}': '{built_bin_path}'"
            )
        binary_path = output_dir / plan.output_file_name
        override_header_path = output_dir / "artifact_build_overrides.h"
        project_conf_path = output_dir / "platformio_artifact.ini"
        shutil.copy2(built_bin_path, binary_path)
        override_header_path.write_text(
            "\n".join(export_override_lines) + "\n",
            encoding="utf-8",
        )
        shutil.copy2(build_project_conf_path, project_conf_path)
        payload = binary_path.read_bytes()
        sha256 = hashlib.sha256(payload).hexdigest()
        file_size = len(payload)
        artifact_id = build_artifact_id(sha256)
        metadata_path = output_dir / "artifact_plan.json"
        metadata = {
            "generated_at_utc": utc_now_iso(),
            "artifact_id": artifact_id,
            "sha256": sha256,
            "file_size": file_size,
            "binary_path": str(binary_path),
            "override_header_path": str(override_header_path),
            "project_conf_path": str(project_conf_path),
            "plan": plan.to_plan_dict(),
            "import_payload": {
                "display_name": plan.display_name,
                "version": plan.version,
                "version_label": plan.version_label,
                "target_kind": plan.target_kind.value,
                "target_variant": plan.target_variant,
                "status": plan.status.value,
                "source_kind": plan.source_kind,
                "source_notes": plan.source_notes,
                "changelog": plan.changelog_short,
                "notes": plan.notes,
                "compatibility": list(plan.compatibility),
                "tags": list(plan.tags),
            },
        }
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return ArtifactBuildResult(
            plan=plan,
            output_dir=str(output_dir),
            binary_path=str(binary_path),
            override_header_path=str(override_header_path),
            metadata_path=str(metadata_path),
            sha256=sha256,
            file_size=file_size,
            artifact_id=artifact_id,
        )

    def import_artifact(
        self,
        result: ArtifactBuildResult,
        *,
        catalog_store: FirmwareCatalogStore | None = None,
        ingest_service: FirmwareIngestService | None = None,
        copy_to_managed_store: bool = True,
    ) -> FirmwareImportResult:
        store = catalog_store or FirmwareCatalogStore(resolve_firmware_catalog_path())
        ingest = ingest_service or FirmwareIngestService(
            store,
            managed_store_dir=store.catalog_path.parent / DEFAULT_MANAGED_FIRMWARE_STORE_DIRNAME,
        )
        return ingest.import_artifact(
            result.to_import_request(copy_to_managed_store=copy_to_managed_store)
        )

    def _run_platformio(self, executable: str, args: list[str]) -> None:
        try:
            completed = subprocess.run(
                [executable, *args],
                cwd=self._repo_root,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            raise ArtifactAgentBuildError(
                f"No se pudo ejecutar PlatformIO '{executable}': {exc}"
            ) from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "sin detalle"
            raise ArtifactAgentBuildError(
                f"PlatformIO falló para {args!r}: {detail}"
            )

    def _resolve_platformio_executable(self, explicit_value: str | None) -> str:
        candidates = []
        if explicit_value:
            candidates.append(explicit_value)
        candidates.extend(
            [
                "platformio",
                str(Path.home() / ".platformio" / "penv" / "Scripts" / "platformio.exe"),
            ]
        )
        for candidate in candidates:
            resolved = shutil.which(candidate) if candidate == "platformio" else candidate
            if resolved and Path(resolved).exists():
                return str(Path(resolved))
        raise ArtifactAgentBuildError(
            "No se encontró PlatformIO. Usa --platformio-exe o instala el ejecutable en PATH."
        )

    def _platformio_include_path(self, header_path: Path) -> str:
        resolved = header_path.resolve()
        if sys.platform.startswith("win"):
            short_path = self._try_windows_short_path(resolved)
            if short_path is not None:
                return short_path.replace("\\", "/")
        return f"\"{resolved.as_posix()}\""

    @staticmethod
    def _resolve_platformio_work_dir(output_slug: str) -> Path:
        if sys.platform.startswith("win"):
            return Path("C:/okua_artifact_agent_tmp") / output_slug
        return Path("/tmp/okua_artifact_agent_tmp") / output_slug

    def _write_project_conf(self, env_name: str, include_path: str, output_dir: Path) -> Path:
        base_text = self._read_text(self._platformio_ini_path)
        header = f"[env:{env_name}]"
        start = base_text.find(header)
        if start < 0:
            raise ArtifactAgentBuildError(
                f"No se encontró la sección '{header}' en platformio.ini"
            )
        next_section = re.search(r"^\[", base_text[start + len(header) :], re.MULTILINE)
        if next_section is None:
            insert_at = len(base_text)
        else:
            insert_at = start + len(header) + next_section.start()
        build_flags_line = f"\nbuild_flags = -include {include_path}\n"
        patched_text = base_text[:insert_at] + build_flags_line + base_text[insert_at:]
        project_conf_path = output_dir / "platformio_artifact.ini"
        project_conf_path.write_text(patched_text, encoding="utf-8")
        return project_conf_path

    @staticmethod
    def _try_windows_short_path(path: Path) -> str | None:
        try:
            buffer_len = 260
            buffer = ctypes.create_unicode_buffer(buffer_len)
            get_short_path = ctypes.windll.kernel32.GetShortPathNameW
            result = get_short_path(str(path), buffer, buffer_len)
            if result == 0:
                return None
            return buffer.value
        except (AttributeError, OSError):
            return None

    @staticmethod
    def _coerce_intent(value: ArtifactIntent | str) -> ArtifactIntent:
        if isinstance(value, ArtifactIntent):
            return value
        try:
            return ArtifactIntent(normalize_key(value))
        except ValueError as exc:
            raise ArtifactAgentValidationError(
                f"intent invalido para artifact agent: {value!r}"
            ) from exc

    @staticmethod
    def _resolve_target_kind(
        intent: ArtifactIntent,
        explicit_value: FirmwareTargetKind | str | None,
        audit: ArtifactSourceAudit,
    ) -> FirmwareTargetKind:
        if explicit_value is None:
            return (
                FirmwareTargetKind.FRUIT
                if intent is ArtifactIntent.COMPARATIVE
                else audit.default_target_kind
            )
        target_kind = normalize_target_kind(explicit_value)
        if target_kind is FirmwareTargetKind.UNKNOWN:
            raise ArtifactAgentValidationError("target_kind no puede ser unknown")
        return target_kind

    @staticmethod
    def _resolve_status(explicit_value: FirmwareStatus | str | None) -> FirmwareStatus:
        if explicit_value is None:
            return FirmwareStatus.SITUATIONAL
        text = normalize_key(explicit_value)
        try:
            return FirmwareStatus(text)
        except ValueError as exc:
            raise ArtifactAgentValidationError(
                f"status invalido para artifact agent: {explicit_value!r}"
            ) from exc

    def _resolve_version(
        self,
        intent: ArtifactIntent,
        explicit_value: str | None,
        audit: ArtifactSourceAudit,
    ) -> str:
        if normalize_text(explicit_value):
            version = normalize_text(explicit_value)
            try:
                derive_version_code(version)
            except ValueError as exc:
                raise ArtifactAgentValidationError(str(exc)) from exc
            return version
        if intent in (ArtifactIntent.COMPARATIVE, ArtifactIntent.OBSERVABLE_PROBE):
            return self._increment_patch_version(audit.default_version)
        return audit.default_version

    @staticmethod
    def _default_changelog(
        intent: ArtifactIntent,
        target_kind: FirmwareTargetKind,
        *,
        ota_compatible: bool,
    ) -> str:
        if intent is ArtifactIntent.OBSERVABLE_PROBE:
            return (
                f"Build probe observable situational de {target_kind.value} para validar OTA física "
                "con blink LED y notas ascendentes de banco."
            )
        if intent is ArtifactIntent.COMPARATIVE:
            if ota_compatible:
                return (
                    f"Build comparativo situational de {target_kind.value} para validar una OTA física "
                    "compatible sin cambiar target_kind."
                )
            return (
                f"Build comparativo situational de {target_kind.value} para validar un cambio visible frente al baseline actual."
            )
        return "Clon situational del baseline actual para validar y catalogar el firmware ya implementado."

    @staticmethod
    def _default_notes(
        intent: ArtifactIntent,
        target_kind: FirmwareTargetKind,
        node_label: str,
        *,
        build_profile: str,
        ota_compatible: bool,
        baseline_target_kind: FirmwareTargetKind,
    ) -> str:
        if intent is ArtifactIntent.OBSERVABLE_PROBE:
            return (
                f"Artifact probe observable para {node_label}. Mantiene target_kind={target_kind.value}, "
                f"target_variant={normalize_target_variant(node_label)} y build_profile={build_profile}; "
                "al arrancar debe hacer blink del LED azul cada segundo y emitir notas ascendentes de 0 a 80."
            )
        if intent is ArtifactIntent.COMPARATIVE:
            if ota_compatible:
                return (
                    f"Artifact comparativo OTA-compatible para {node_label}. Mantiene target_kind={target_kind.value}, "
                    f"target_variant={normalize_target_variant(node_label)} y build_profile={build_profile}; "
                    "el cambio observable esperado es version/artifact_id/sha256 distintos tras la OTA."
                )
            return (
                f"Artifact comparativo OTA-A para {node_label}. Es útil para observar un cambio real en banco; "
                f"si el baseline actual es {baseline_target_kind.value}, este build {target_kind.value} no será OTA-compatible por target_kind."
            )
        return (
            f"Representa el firmware actualmente implementado en {node_label} para {target_kind.value} prueba. "
            "Generado por OTA-A como artifact situational."
        )

    @staticmethod
    def _default_source_notes(
        intent: ArtifactIntent,
        node_label: str,
        *,
        ota_compatible: bool,
    ) -> str:
        if intent is ArtifactIntent.OBSERVABLE_PROBE:
            return f"Generado por artifact agent como probe observable OTA-compatible para {node_label}."
        if intent is ArtifactIntent.COMPARATIVE:
            if ota_compatible:
                return (
                    f"Generado por artifact agent OTA-B como comparativo OTA-compatible para {node_label}."
                )
            return f"Generado por artifact agent OTA-A como comparativo controlado para {node_label}."
        return f"Generado por artifact agent OTA-A como clon del baseline actual de {node_label}."

    @staticmethod
    def _resolve_tags(
        *,
        intent: ArtifactIntent,
        target_kind: FirmwareTargetKind,
        target_variant: str,
        build_profile: str,
        ota_compatible: bool,
        explicit_tags: Iterable[str],
    ) -> tuple[str, ...]:
        ordered: list[str] = []
        seen: set[str] = set()
        derived_tags = [
            "ota_a",
            "situational",
            intent.value,
            target_kind.value,
            target_variant,
            f"build_profile_{build_profile}",
        ]
        if intent is ArtifactIntent.OBSERVABLE_PROBE:
            derived_tags.extend(("ota_compatible", "probe", "bank_probe"))
        if intent is ArtifactIntent.COMPARATIVE:
            derived_tags.append("ota_compatible" if ota_compatible else "cross_kind_comparison")
        for tag in (*derived_tags, *explicit_tags):
            normalized = normalize_key(tag)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
        return tuple(ordered)

    @staticmethod
    def _resolve_display_name(
        *,
        intent: ArtifactIntent,
        target_kind: FirmwareTargetKind,
        baseline_target_kind: FirmwareTargetKind,
        node_label: str,
        version: str,
        explicit_value: str,
    ) -> str:
        if explicit_value:
            return explicit_value
        if intent is ArtifactIntent.CURRENT_CLONE:
            kind_text = "planta prueba actual"
        elif intent is ArtifactIntent.OBSERVABLE_PROBE:
            kind_text = "planta prueba sonda observable OTA-compatible"
        elif target_kind is baseline_target_kind:
            kind_text = "planta prueba comparativa OTA-compatible"
        elif target_kind is FirmwareTargetKind.FRUIT:
            kind_text = "fruta prueba comparativa"
        else:
            kind_text = f"{target_kind.value} prueba comparativa"
        return f"OKUA Node UDP v1 - {node_label} {kind_text} ({version})"

    @staticmethod
    def _build_output_slug(
        *,
        intent: ArtifactIntent,
        target_kind: FirmwareTargetKind,
        target_variant: str,
        version: str,
    ) -> str:
        version_slug = normalize_key(version) or "unknown"
        return f"okua_node_udp_v1-{target_kind.value}-{target_variant}-{version_slug}-{intent.value}"

    @staticmethod
    def _extract_platformio_default_env(platformio_text: str) -> str:
        match = re.search(
            r"^\s*default_envs\s*=\s*(?P<value>[A-Za-z0-9_\\-]+)\s*$",
            platformio_text,
            re.MULTILINE,
        )
        if match is None:
            raise ArtifactAgentValidationError("No se pudo resolver default_envs desde platformio.ini")
        return match.group("value")

    @staticmethod
    def _extract_string_define(source_text: str, define_name: str) -> str:
        pattern = rf"^\s*#define\s+{re.escape(define_name)}\s+\"(?P<value>[^\"]+)\"\s*$"
        match = re.search(pattern, source_text, re.MULTILINE)
        if match is None:
            raise ArtifactAgentValidationError(
                f"No se pudo extraer {define_name} desde el firmware actual."
            )
        return match.group("value")

    @staticmethod
    def _extract_build_profile(source_text: str) -> str:
        _DIRECT = re.compile(
            r"^\s*#define\s+ACTIVE_MODE\s+(?P<value>MODE_TEST|MODE_FIELD)\s*$",
            re.MULTILINE,
        )
        direct = _DIRECT.search(source_text)
        if direct is not None:
            return "field" if direct.group("value") == "MODE_FIELD" else "test"

        # Indirect define: #define ACTIVE_MODE <SYMBOL> then #define <SYMBOL> MODE_TEST|MODE_FIELD
        indirect = re.search(
            r"^\s*#define\s+ACTIVE_MODE\s+(?P<symbol>[A-Za-z_][A-Za-z0-9_]*)\s*$",
            source_text,
            re.MULTILINE,
        )
        if indirect is not None:
            symbol = re.escape(indirect.group("symbol"))
            resolved = re.search(
                rf"^\s*#define\s+{symbol}\s+(?P<value>MODE_TEST|MODE_FIELD)\s*$",
                source_text,
                re.MULTILINE,
            )
            if resolved is not None:
                return "field" if resolved.group("value") == "MODE_FIELD" else "test"

        raise ArtifactAgentValidationError(
            "No se pudo resolver ACTIVE_MODE desde el firmware actual."
        )

    @staticmethod
    def _extract_default_target_kind(source_text: str) -> FirmwareTargetKind:
        _DIRECT = re.compile(
            r"^\s*#define\s+ACTIVE_SENSOR\s+(?P<value>SENSOR_PLANT|SENSOR_FRUIT)\s*$",
            re.MULTILINE,
        )
        direct = _DIRECT.search(source_text)
        if direct is not None:
            return (
                FirmwareTargetKind.FRUIT
                if direct.group("value") == "SENSOR_FRUIT"
                else FirmwareTargetKind.PLANT
            )

        # Indirect define: #define ACTIVE_SENSOR <SYMBOL> then #define <SYMBOL> SENSOR_*
        indirect = re.search(
            r"^\s*#define\s+ACTIVE_SENSOR\s+(?P<symbol>[A-Za-z_][A-Za-z0-9_]*)\s*$",
            source_text,
            re.MULTILINE,
        )
        if indirect is not None:
            symbol = re.escape(indirect.group("symbol"))
            resolved = re.search(
                rf"^\s*#define\s+{symbol}\s+(?P<value>SENSOR_PLANT|SENSOR_FRUIT)\s*$",
                source_text,
                re.MULTILINE,
            )
            if resolved is not None:
                return (
                    FirmwareTargetKind.FRUIT
                    if resolved.group("value") == "SENSOR_FRUIT"
                    else FirmwareTargetKind.PLANT
                )

        raise ArtifactAgentValidationError(
            "No se pudo resolver ACTIVE_SENSOR desde el firmware actual."
        )

    @staticmethod
    def _parse_semver(version: str) -> tuple[int, int, int]:
        text = normalize_text(version)
        match = _SEMVER_PATTERN.fullmatch(text)
        if match is None:
            raise ArtifactAgentValidationError(
                f"version invalida para artifact agent; se esperaba semver MAJOR.MINOR.PATCH: {version!r}"
            )
        return (
            int(match.group("major")),
            int(match.group("minor")),
            int(match.group("patch")),
        )

    @staticmethod
    def _parse_semver_with_suffix(version: str) -> tuple[int, int, int, str]:
        text = normalize_text(version)
        match = _SEMVER_PATTERN.fullmatch(text)
        if match is None:
            raise ArtifactAgentValidationError(
                f"version invalida para artifact agent; se esperaba semver MAJOR.MINOR.PATCH: {version!r}"
            )
        return (
            int(match.group("major")),
            int(match.group("minor")),
            int(match.group("patch")),
            match.group("suffix") or "",
        )

    @staticmethod
    def _increment_patch_version(version: str) -> str:
        text = normalize_text(version)
        match = _SEMVER_PATTERN.fullmatch(text)
        if match is None:
            raise ArtifactAgentValidationError(
                f"No se puede derivar la siguiente version desde {version!r}"
            )
        major = int(match.group("major"))
        minor = int(match.group("minor"))
        patch = int(match.group("patch")) + 1
        suffix = match.group("suffix") or ""
        return f"{major}.{minor}.{patch}{suffix}"

    @staticmethod
    def _read_text(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ArtifactAgentValidationError(
                f"No se pudo leer '{path}': {exc}"
            ) from exc
