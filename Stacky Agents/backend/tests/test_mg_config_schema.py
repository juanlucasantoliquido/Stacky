"""tests/test_mg_config_schema.py — Plan 217 F1a.

Valida `tools/migrar_mantis_gitlab/config_schema.py`: parseo de un
migration_config.json completo y de uno mínimo, y la regla dura de que
`field_mapping.status._unmapped_fallback` es obligatorio.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from tools.migrar_mantis_gitlab.config_schema import (
    ConfigValidationError,
    MigrationConfig,
    validate_config,
)

_FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "mg"


def _load_fixture(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def test_config_completo_valido_parsea_ok():
    raw = _load_fixture("migration_config_complete.json")
    cfg = validate_config(raw)

    assert isinstance(cfg, MigrationConfig)
    assert cfg.origin.base_url == "https://mantis.ejemplo.local/mantis"
    assert cfg.origin.project_ids == [900, 901]
    assert cfg.origin.auth.auth_file == "auth/mantis_auth_ejemplo.json"
    assert cfg.destination.project_path == "grupo-ejemplo/proyecto-ejemplo"
    assert cfg.destination.auth.secret_backend == "auto"
    assert cfg.user_mapping.map["usuario.origen.uno"] == "usuario.destino.uno"
    assert "_comment" not in cfg.user_mapping.map
    assert cfg.field_mapping.status.unmapped_fallback.label == "status::sin_mapear"
    assert cfg.field_mapping.status.entries["resolved"].gitlab_state == "closed"
    assert cfg.field_mapping.priority.scale["1"] == "P1-critica"
    assert cfg.field_mapping.relationships["depends_on"] == "blocks"
    assert cfg.options.batch_size == 25
    assert cfg.options.attachments.max_size_mb == 50
    assert cfg.options.incremental.enabled is True
    assert cfg.logging.redact_secrets is True


def test_falta_unmapped_fallback_lanza_config_validation_error():
    raw = _load_fixture("migration_config_complete.json")
    del raw["field_mapping"]["status"]["_unmapped_fallback"]

    with pytest.raises(ConfigValidationError, match="_unmapped_fallback"):
        validate_config(raw)


def test_falta_destination_project_path_lanza_error_claro():
    raw = _load_fixture("migration_config_complete.json")
    del raw["destination"]["project_path"]

    with pytest.raises(ConfigValidationError, match="project_path"):
        validate_config(raw)


def test_config_minimo_completo_parsea_ok():
    raw = _load_fixture("migration_config_minimal.json")
    cfg = validate_config(raw)

    assert isinstance(cfg, MigrationConfig)
    # Defaults aplicados cuando el bloque opcional no está presente.
    assert cfg.origin.extraction_mode == "auto"
    assert cfg.origin.include_resolved_closed is True
    assert cfg.origin.auth.protocol == "rest"
    assert cfg.destination.preserve_authorship_mode == "metadata_only"
    assert cfg.destination.auth.secret_backend == "auto"
    assert cfg.user_mapping.default_fallback == "unassigned"
    assert cfg.user_mapping.map == {}
    assert cfg.field_mapping.status.unmapped_fallback.gitlab_state == "opened"
    assert cfg.field_mapping.priority.label_prefix == "priority::"
    assert cfg.field_mapping.severity.label_prefix == "severity::"
    assert cfg.options.dry_run is True
    assert cfg.options.batch_size == 25
    assert cfg.options.retry_backoff_seconds == [2, 5, 15, 30, 60]
    assert cfg.options.attachments.max_size_mb == 50
    assert cfg.options.incremental.enabled is False
    assert cfg.options.report_formats == ["markdown", "json"]
    assert cfg.logging.level == "INFO"
    assert cfg.logging.redact_secrets is True


def test_falta_origin_lanza_config_validation_error():
    raw = _load_fixture("migration_config_minimal.json")
    del raw["origin"]

    with pytest.raises(ConfigValidationError, match="origin"):
        validate_config(raw)


def test_config_no_dict_lanza_config_validation_error():
    with pytest.raises(ConfigValidationError):
        validate_config([])  # type: ignore[arg-type]


def test_no_mutar_el_dict_original():
    raw = _load_fixture("migration_config_complete.json")
    raw_copy = copy.deepcopy(raw)
    validate_config(raw)
    assert raw == raw_copy
