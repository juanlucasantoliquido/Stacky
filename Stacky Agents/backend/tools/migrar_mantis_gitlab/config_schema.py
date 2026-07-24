"""tools/migrar_mantis_gitlab/config_schema.py — Plan 217 F1a.

Dataclasses estándar (stdlib, SIN pydantic — decisión dura C9 del plan v2:
el repo no depende de pydantic) que representan el `migration_config.json`
completo (§4 del plan). `validate_config(raw: dict) -> MigrationConfig`
valida explícitamente (funciones `_validate_*`, no un framework de
validación) que los campos obligatorios existan y tengan el tipo esperado.

Regla dura (§4, "Reglas duras del archivo de config"): ningún valor de
Mantis sin mapeo explícito puede causar un abort silencioso, por eso
`field_mapping.status._unmapped_fallback` es OBLIGATORIO — su ausencia
lanza `ConfigValidationError` con mensaje claro, nunca un KeyError crudo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


class ConfigValidationError(Exception):
    """Error de validación de migration_config.json (mensaje claro, nunca
    un KeyError/TypeError crudo)."""


# ── Origin ───────────────────────────────────────────────────────────────


@dataclass(slots=True)
class OriginAuthConfig:
    auth_file: str
    protocol: str = "rest"


@dataclass(slots=True)
class OriginConfig:
    type: str
    base_url: str
    project_ids: list[int]
    auth: OriginAuthConfig
    extraction_mode: str = "auto"
    include_resolved_closed: bool = True
    csv_export_fallback: bool = True


# ── Destination ──────────────────────────────────────────────────────────


@dataclass(slots=True)
class DestinationAuthConfig:
    auth_file: str
    secret_backend: str = "auto"


@dataclass(slots=True)
class DestinationConfig:
    type: str
    base_url: str
    project_path: str
    auth: DestinationAuthConfig
    preserve_authorship_mode: str = "metadata_only"
    epics_strategy: str = "auto"


# ── User mapping ─────────────────────────────────────────────────────────


@dataclass(slots=True)
class UserMappingConfig:
    default_fallback: str = "unassigned"
    map: dict[str, str] = field(default_factory=dict)


# ── Field mapping ────────────────────────────────────────────────────────


@dataclass(slots=True)
class StatusEntry:
    gitlab_state: str
    label: str


@dataclass(slots=True)
class StatusMapping:
    entries: dict[str, StatusEntry]
    unmapped_fallback: StatusEntry


@dataclass(slots=True)
class PriorityMapping:
    label_prefix: str = "priority::"
    reuse: Optional[str] = None
    scale: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class LabelPrefixMapping:
    label_prefix: str


@dataclass(slots=True)
class VersionMapping:
    target_version_as: str = "milestone"
    fixed_in_version_as: str = "label:fixed_in::"
    affects_version_as: str = "label:affects::"


@dataclass(slots=True)
class CustomFieldsMapping:
    mode: str = "metadata_block"


@dataclass(slots=True)
class FieldMappingConfig:
    status: StatusMapping
    priority: PriorityMapping
    severity: LabelPrefixMapping
    category: LabelPrefixMapping
    tags: LabelPrefixMapping
    version: VersionMapping
    relationships: dict[str, str]
    custom_fields: CustomFieldsMapping


# ── Options ──────────────────────────────────────────────────────────────


@dataclass(slots=True)
class AttachmentsOptions:
    max_size_mb: int = 50
    skip_if_over_limit: bool = True
    download_temp_dir: Optional[str] = None


@dataclass(slots=True)
class IncrementalOptions:
    enabled: bool = False
    since_field: str = "last_updated"
    checkpoint_file: Optional[str] = None


@dataclass(slots=True)
class OptionsConfig:
    dry_run: bool = True
    batch_size: int = 25
    max_retries: int = 5
    retry_backoff_seconds: list[int] = field(default_factory=lambda: [2, 5, 15, 30, 60])
    rate_limit_pause_on_429_seconds: int = 60
    attachments: AttachmentsOptions = field(default_factory=AttachmentsOptions)
    incremental: IncrementalOptions = field(default_factory=IncrementalOptions)
    verify_after_execute: bool = True
    report_formats: list[str] = field(default_factory=lambda: ["markdown", "json"])
    report_output_dir: str = "reports/"


# ── Logging ──────────────────────────────────────────────────────────────


@dataclass(slots=True)
class LoggingConfig:
    level: str = "INFO"
    file: str = "logs/migrar_mantis_gitlab_{run_id}.log"
    redact_secrets: bool = True


# ── Root ─────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class MigrationConfig:
    schema_version: str
    origin: OriginConfig
    destination: DestinationConfig
    user_mapping: UserMappingConfig
    field_mapping: FieldMappingConfig
    options: OptionsConfig
    logging: LoggingConfig


# ── Validación ───────────────────────────────────────────────────────────


def validate_config(raw: Any) -> MigrationConfig:
    """Parsea y valida un dict crudo (ya deserializado de JSON) a
    `MigrationConfig`. Lanza `ConfigValidationError` con mensaje claro ante
    cualquier campo obligatorio ausente o mal tipado."""
    if not isinstance(raw, dict):
        raise ConfigValidationError(
            "El migration_config.json debe ser un objeto JSON en la raíz "
            f"(se recibió {type(raw).__name__})."
        )

    schema_version = str(raw.get("$schema_version") or raw.get("schema_version") or "1.0")

    origin = _validate_origin(raw.get("origin"))
    destination = _validate_destination(raw.get("destination"))
    user_mapping = _validate_user_mapping(raw.get("user_mapping") or {})
    field_mapping = _validate_field_mapping(raw.get("field_mapping"))
    options = _validate_options(raw.get("options") or {})
    logging_cfg = _validate_logging(raw.get("logging") or {})

    return MigrationConfig(
        schema_version=schema_version,
        origin=origin,
        destination=destination,
        user_mapping=user_mapping,
        field_mapping=field_mapping,
        options=options,
        logging=logging_cfg,
    )


def _validate_origin(raw: Optional[dict]) -> OriginConfig:
    if not isinstance(raw, dict):
        raise ConfigValidationError("'origin' es obligatorio y debe ser un objeto.")

    base_url = raw.get("base_url")
    if not base_url or not isinstance(base_url, str):
        raise ConfigValidationError("'origin.base_url' es obligatorio (string no vacío).")

    project_ids = raw.get("project_ids")
    if not project_ids or not isinstance(project_ids, list):
        raise ConfigValidationError(
            "'origin.project_ids' es obligatorio y debe ser una lista no vacía de IDs."
        )

    auth_raw = raw.get("auth")
    if not isinstance(auth_raw, dict) or not auth_raw.get("auth_file"):
        raise ConfigValidationError("'origin.auth.auth_file' es obligatorio.")
    auth_file = auth_raw["auth_file"]
    if not isinstance(auth_file, str):
        raise ConfigValidationError("'origin.auth.auth_file' debe ser una ruta (string).")

    return OriginConfig(
        type=raw.get("type", "mantis"),
        base_url=base_url,
        project_ids=list(project_ids),
        auth=OriginAuthConfig(auth_file=auth_file, protocol=auth_raw.get("protocol", "rest")),
        extraction_mode=raw.get("extraction_mode", "auto"),
        include_resolved_closed=bool(raw.get("include_resolved_closed", True)),
        csv_export_fallback=bool(raw.get("csv_export_fallback", True)),
    )


def _validate_destination(raw: Optional[dict]) -> DestinationConfig:
    if not isinstance(raw, dict):
        raise ConfigValidationError("'destination' es obligatorio y debe ser un objeto.")

    base_url = raw.get("base_url")
    if not base_url or not isinstance(base_url, str):
        raise ConfigValidationError("'destination.base_url' es obligatorio (string no vacío).")

    project_path = raw.get("project_path")
    if not project_path or not isinstance(project_path, str):
        raise ConfigValidationError(
            "'destination.project_path' es obligatorio (string no vacío)."
        )

    auth_raw = raw.get("auth")
    if not isinstance(auth_raw, dict) or not auth_raw.get("auth_file"):
        raise ConfigValidationError("'destination.auth.auth_file' es obligatorio.")
    auth_file = auth_raw["auth_file"]
    if not isinstance(auth_file, str):
        raise ConfigValidationError("'destination.auth.auth_file' debe ser una ruta (string).")

    return DestinationConfig(
        type=raw.get("type", "gitlab"),
        base_url=base_url,
        project_path=project_path,
        auth=DestinationAuthConfig(
            auth_file=auth_file, secret_backend=auth_raw.get("secret_backend", "auto")
        ),
        preserve_authorship_mode=raw.get("preserve_authorship_mode", "metadata_only"),
        epics_strategy=raw.get("epics_strategy", "auto"),
    )


def _validate_user_mapping(raw: dict) -> UserMappingConfig:
    if not isinstance(raw, dict):
        raise ConfigValidationError("'user_mapping' debe ser un objeto si está presente.")

    mapping = raw.get("map") or {}
    if not isinstance(mapping, dict):
        raise ConfigValidationError(
            "'user_mapping.map' debe ser un objeto {mantis_username: gitlab_username}."
        )
    clean_map = {k: v for k, v in mapping.items() if k != "_comment"}

    return UserMappingConfig(
        default_fallback=raw.get("default_fallback", "unassigned"),
        map=clean_map,
    )


def _validate_status_entry(raw: Any, *, where: str) -> StatusEntry:
    if not isinstance(raw, dict):
        raise ConfigValidationError(f"'{where}' debe ser un objeto con 'gitlab_state' y 'label'.")
    gitlab_state = raw.get("gitlab_state")
    label = raw.get("label")
    if not gitlab_state or not label:
        raise ConfigValidationError(f"'{where}' debe tener 'gitlab_state' y 'label' no vacíos.")
    return StatusEntry(gitlab_state=gitlab_state, label=label)


def _validate_status_mapping(raw: Optional[dict]) -> StatusMapping:
    if not isinstance(raw, dict):
        raise ConfigValidationError("'field_mapping.status' es obligatorio y debe ser un objeto.")

    if "_unmapped_fallback" not in raw:
        raise ConfigValidationError(
            "'field_mapping.status._unmapped_fallback' es OBLIGATORIO (regla dura §4 "
            "del Plan 217): ningún valor de status Mantis sin mapeo explícito puede "
            "causar un abort silencioso; siempre debe caer a un estado/label conocido."
        )
    unmapped = _validate_status_entry(
        raw["_unmapped_fallback"], where="field_mapping.status._unmapped_fallback"
    )
    entries = {
        key: _validate_status_entry(value, where=f"field_mapping.status.{key}")
        for key, value in raw.items()
        if key != "_unmapped_fallback"
    }
    return StatusMapping(entries=entries, unmapped_fallback=unmapped)


def _validate_priority_mapping(raw: dict) -> PriorityMapping:
    if not isinstance(raw, dict):
        raise ConfigValidationError("'field_mapping.priority' debe ser un objeto si está presente.")
    scale = raw.get("scale") or {}
    if not isinstance(scale, dict):
        raise ConfigValidationError("'field_mapping.priority.scale' debe ser un objeto.")
    return PriorityMapping(
        label_prefix=raw.get("label_prefix", "priority::"),
        reuse=raw.get("_reuse"),
        scale=dict(scale),
    )


def _validate_label_prefix_mapping(raw: dict, *, default_prefix: str, where: str) -> LabelPrefixMapping:
    if not isinstance(raw, dict):
        raise ConfigValidationError(f"'{where}' debe ser un objeto con 'label_prefix' si está presente.")
    return LabelPrefixMapping(label_prefix=raw.get("label_prefix", default_prefix))


def _validate_version_mapping(raw: dict) -> VersionMapping:
    if not isinstance(raw, dict):
        raise ConfigValidationError("'field_mapping.version' debe ser un objeto si está presente.")
    return VersionMapping(
        target_version_as=raw.get("target_version_as", "milestone"),
        fixed_in_version_as=raw.get("fixed_in_version_as", "label:fixed_in::"),
        affects_version_as=raw.get("affects_version_as", "label:affects::"),
    )


def _validate_field_mapping(raw: Optional[dict]) -> FieldMappingConfig:
    if not isinstance(raw, dict):
        raise ConfigValidationError("'field_mapping' es obligatorio y debe ser un objeto.")

    status = _validate_status_mapping(raw.get("status"))
    priority = _validate_priority_mapping(raw.get("priority") or {})
    severity = _validate_label_prefix_mapping(
        raw.get("severity") or {}, default_prefix="severity::", where="field_mapping.severity"
    )
    category = _validate_label_prefix_mapping(
        raw.get("category") or {}, default_prefix="category::", where="field_mapping.category"
    )
    tags = _validate_label_prefix_mapping(
        raw.get("tags") or {}, default_prefix="tag::", where="field_mapping.tags"
    )
    version = _validate_version_mapping(raw.get("version") or {})

    relationships = raw.get("relationships") or {}
    if not isinstance(relationships, dict):
        raise ConfigValidationError("'field_mapping.relationships' debe ser un objeto.")

    custom_fields_raw = raw.get("custom_fields") or {}
    if not isinstance(custom_fields_raw, dict):
        raise ConfigValidationError("'field_mapping.custom_fields' debe ser un objeto.")
    custom_fields = CustomFieldsMapping(mode=custom_fields_raw.get("mode", "metadata_block"))

    return FieldMappingConfig(
        status=status,
        priority=priority,
        severity=severity,
        category=category,
        tags=tags,
        version=version,
        relationships=dict(relationships),
        custom_fields=custom_fields,
    )


def _validate_options(raw: dict) -> OptionsConfig:
    if not isinstance(raw, dict):
        raise ConfigValidationError("'options' debe ser un objeto si está presente.")

    attachments_raw = raw.get("attachments") or {}
    if not isinstance(attachments_raw, dict):
        raise ConfigValidationError("'options.attachments' debe ser un objeto.")
    attachments = AttachmentsOptions(
        max_size_mb=int(attachments_raw.get("max_size_mb", 50)),
        skip_if_over_limit=bool(attachments_raw.get("skip_if_over_limit", True)),
        download_temp_dir=attachments_raw.get("download_temp_dir"),
    )

    incremental_raw = raw.get("incremental") or {}
    if not isinstance(incremental_raw, dict):
        raise ConfigValidationError("'options.incremental' debe ser un objeto.")
    incremental = IncrementalOptions(
        enabled=bool(incremental_raw.get("enabled", False)),
        since_field=incremental_raw.get("since_field", "last_updated"),
        checkpoint_file=incremental_raw.get("checkpoint_file"),
    )

    retry_backoff = raw.get("retry_backoff_seconds") or [2, 5, 15, 30, 60]
    if not isinstance(retry_backoff, list):
        raise ConfigValidationError("'options.retry_backoff_seconds' debe ser una lista.")

    report_formats = raw.get("report_formats") or ["markdown", "json"]
    if not isinstance(report_formats, list):
        raise ConfigValidationError("'options.report_formats' debe ser una lista.")

    return OptionsConfig(
        dry_run=bool(raw.get("dry_run", True)),
        batch_size=int(raw.get("batch_size", 25)),
        max_retries=int(raw.get("max_retries", 5)),
        retry_backoff_seconds=list(retry_backoff),
        rate_limit_pause_on_429_seconds=int(raw.get("rate_limit_pause_on_429_seconds", 60)),
        attachments=attachments,
        incremental=incremental,
        verify_after_execute=bool(raw.get("verify_after_execute", True)),
        report_formats=list(report_formats),
        report_output_dir=raw.get("report_output_dir", "reports/"),
    )


def _validate_logging(raw: dict) -> LoggingConfig:
    if not isinstance(raw, dict):
        raise ConfigValidationError("'logging' debe ser un objeto si está presente.")
    return LoggingConfig(
        level=raw.get("level", "INFO"),
        file=raw.get("file", "logs/migrar_mantis_gitlab_{run_id}.log"),
        redact_secrets=bool(raw.get("redact_secrets", True)),
    )


__all__ = [
    "AttachmentsOptions",
    "ConfigValidationError",
    "CustomFieldsMapping",
    "DestinationAuthConfig",
    "DestinationConfig",
    "FieldMappingConfig",
    "IncrementalOptions",
    "LabelPrefixMapping",
    "LoggingConfig",
    "MigrationConfig",
    "OptionsConfig",
    "OriginAuthConfig",
    "OriginConfig",
    "PriorityMapping",
    "StatusEntry",
    "StatusMapping",
    "UserMappingConfig",
    "VersionMapping",
    "validate_config",
]
