"""tests/test_mg_cableado_config.py — que lo que dice el config LLEGUE al payload.

Tres bugs de cableado detectados auditando los payloads ANTES de migrar los 1008
(no en los tests: los tests unitarios de cada pieza pasaban):

1. **`timezone_offset` no llegaba.** `_build_payload` llamaba
   `extraer_fechas_issue(issue)` sin el offset, así que el ISO salía pelado
   (`2025-11-21T11:52:00`) mientras el config declaraba `-03:00`. GitLab lo
   interpreta como UTC → **3 h de corrimiento en ~3900 timestamps**.
2. **`field_mapping.resolution` no llegaba.** `_field_mapping_to_dict` no lo
   serializaba y `FieldMappingConfig` no lo tenía. Funcionaba de casualidad por el
   default del `.get(...)`, así que cambiar el prefijo en el config no tenía
   efecto.
3. **`milestone` se descartaba.** Calculado y tirado, como el `state`. Medido:
   **17 tickets** del proyecto 310 traen `target_version`.

La lección: un valor de config puede estar validado, tipado y con su propio test
verde, y aun así no llegar a la API. Estos tests cubren el CAMINO COMPLETO
config → payload.
"""
from __future__ import annotations

import json

import pytest

from tools.migrar_mantis_gitlab.__main__ import _field_mapping_to_dict
from tools.migrar_mantis_gitlab.config_schema import validate_config
from tools.migrar_mantis_gitlab.migrator_mg_core import _build_payload, plan_migration

_ISSUE = {
    "id": 1, "summary": "t", "status": "closed",
    "date_submitted": "21/11/2025 11:52",
    "last_modified": "05/03/2026 11:38",
    "date_closed": "05/03/2026 11:38",
    "resolution": "wont-fix",
    "target_version": "Release 2026-Q1",
}


def _config_min(extra_origin: dict | None = None, extra_fm: dict | None = None) -> dict:
    fm = {
        "status": {
            "closed": {"gitlab_state": "closed", "label": "status::closed"},
            "_unmapped_fallback": {"gitlab_state": "opened", "label": "status::sin_mapear"},
        },
    }
    fm.update(extra_fm or {})
    origin = {
        "type": "mantis", "base_url": "https://m.local/mantis", "project_ids": [310],
        "auth": {"auth_file": "auth/x.json"},
    }
    origin.update(extra_origin or {})
    return {
        "origin": origin,
        "destination": {
            "type": "gitlab", "base_url": "https://g.local",
            "project_path": "ns/p", "auth": {"auth_file": "auth/y.json"},
        },
        "field_mapping": fm,
    }


class _AdapterFake:
    def fetch_all_issues(self):
        return [dict(_ISSUE)]

    def fetch_issue_detail(self, issue_id):
        return dict(_ISSUE)

    def fetch_comments(self, issue_id):
        return [{"id": 9, "reporter": "X", "date": "13/01/2026 10:00", "text": "n"}]

    def fetch_attachments(self, issue_id):
        return []

    def fetch_relationships(self, issue_id):
        return []


# ── 1) timezone_offset ─────────────────────────────────────────────────────


def test_el_offset_del_config_llega_al_created_at_del_issue():
    cfg = validate_config(_config_min({"timezone_offset": "-03:00"}))
    assert cfg.origin.timezone_offset == "-03:00"

    plan = plan_migration(
        _AdapterFake(), {}, _field_mapping_to_dict(cfg.field_mapping), {},
        cfg.origin.timezone_offset,
    )
    create = [o for o in plan.ops if o.op_kind == "create_item"][0]
    assert create.payload["created_at"] == "2025-11-21T11:52:00-03:00"
    assert create.payload["updated_at"] == "2026-03-05T11:38:00-03:00"


def test_el_offset_del_config_llega_al_created_at_de_las_notas():
    """Son 2888 notas: si el offset no llega acá, la timeline queda desplazada
    3 h aunque el issue esté bien."""
    cfg = validate_config(_config_min({"timezone_offset": "-03:00"}))
    plan = plan_migration(
        _AdapterFake(), {}, _field_mapping_to_dict(cfg.field_mapping), {},
        cfg.origin.timezone_offset,
    )
    nota = [o for o in plan.ops if o.op_kind == "post_comment"][0]
    assert nota.payload["created_at"] == "2026-01-13T10:00:00-03:00"


def test_sin_offset_declarado_el_iso_sale_pelado():
    """Comportamiento previo, preservado a propósito: sin offset NO se inventa
    uno. Pero el CLI avisa en cada corrida."""
    cfg = validate_config(_config_min())
    assert cfg.origin.timezone_offset == ""
    p = _build_payload(dict(_ISSUE), _field_mapping_to_dict(cfg.field_mapping), {}, [], "")
    assert p["created_at"] == "2025-11-21T11:52:00"


def test_offset_invalido_aborta_en_la_validacion_del_config():
    """Un offset mal escrito tiene que romper en `validate`, no a mitad de una
    corrida de 1008 issues."""
    from tools.migrar_mantis_gitlab.config_schema import ConfigValidationError

    with pytest.raises(ConfigValidationError):
        validate_config(_config_min({"timezone_offset": "America/Argentina/Buenos_Aires"}))


# ── 2) field_mapping.resolution ────────────────────────────────────────────


def test_resolution_del_config_llega_al_dict_y_al_label():
    cfg = validate_config(_config_min(extra_fm={"resolution": {"label_prefix": "res::"}}))
    fm = _field_mapping_to_dict(cfg.field_mapping)
    assert fm["resolution"]["label_prefix"] == "res::"

    p = _build_payload(dict(_ISSUE), fm, {}, [], "-03:00")
    assert "res::wont-fix" in p["labels"]
    assert not any(l.startswith("mantis-resolution::") for l in p["labels"])


def test_resolution_tiene_default_si_el_config_no_la_declara():
    """Backward-compat: los configs viejos no tienen el bloque."""
    cfg = validate_config(_config_min())
    fm = _field_mapping_to_dict(cfg.field_mapping)
    assert fm["resolution"]["label_prefix"] == "mantis-resolution::"
    p = _build_payload(dict(_ISSUE), fm, {}, [], "")
    assert "mantis-resolution::wont-fix" in p["labels"]


# ── 3) milestone ───────────────────────────────────────────────────────────


def test_el_milestone_llega_al_payload():
    cfg = validate_config(_config_min())
    p = _build_payload(dict(_ISSUE), _field_mapping_to_dict(cfg.field_mapping), {}, [], "")
    assert p["milestone"] == "Release 2026-Q1"


def test_el_writer_resuelve_el_milestone_y_lo_manda_en_el_create():
    """El milestone sólo puede viajar por el POST directo: el provider no tiene
    slot para él, igual que con `created_at`."""
    from tools.migrar_mantis_gitlab.destination_writer import DryRunGitLabWriter

    class _Cfg:
        base_url = "https://g.local"
        project_path = "ns/p"

    w = DryRunGitLabWriter(_Cfg())
    mid = w.ensure_milestone("Release 2026-Q1")
    assert isinstance(mid, int)
    # Idempotente por título: el segundo pedido no crea otro.
    assert w.ensure_milestone("Release 2026-Q1") == mid
    assert len([o for o in w.simulated_ops if o.get("op") == "ensure_milestone"]) == 1
    assert w.ensure_milestone("   ") is None


def test_el_create_con_milestone_usa_el_camino_directo():
    """Si el payload trae milestone, `create_item` NO debe delegar en el provider
    (que lo perdería)."""
    from tools.migrar_mantis_gitlab import destination_writer as dw

    llamadas = {"directo": 0, "provider": 0}

    class _W(dw.GitLabDestinationWriter):
        def __init__(self):
            self._logger = dw.logging.getLogger("t")
            self._milestone_cache = {}

        def _create_item_con_fecha(self, payload):
            llamadas["directo"] += 1
            return {"iid": "1"}

        def _create_item_via_provider(self, payload):
            llamadas["provider"] += 1
            return {"iid": "2"}

    w = _W()
    w.create_item({"title": "a", "milestone": "R1"})
    assert llamadas == {"directo": 1, "provider": 0}

    w.create_item({"title": "b"})
    assert llamadas == {"directo": 1, "provider": 1}


# ── El config REAL de Ripley ───────────────────────────────────────────────


def test_el_config_real_de_ripley_declara_lo_que_se_decidio():
    """Guarda contra que alguien pise las decisiones del operador."""
    import pathlib

    ruta = pathlib.Path(__file__).parents[2] / "deployment" / "migration_config_ripley.json"
    if not ruta.exists():
        pytest.skip("config de Ripley no disponible en este checkout")
    cfg = validate_config(json.loads(ruta.read_text(encoding="utf-8")))

    assert cfg.origin.project_ids == [310]
    assert cfg.origin.include_resolved_closed is True
    # Decisión del operador 2026-07-29: Argentina, sin DST desde 2009.
    assert cfg.origin.timezone_offset == "-03:00"
    assert cfg.field_mapping.status.entries["resolved"].gitlab_state == "closed"
    assert cfg.field_mapping.status.entries["closed"].gitlab_state == "closed"
    # Sólo se mapean usuarios con evidencia fuerte; el resto cae a unassigned.
    assert cfg.user_mapping.default_fallback == "unassigned"
    reales = {k: v for k, v in cfg.user_mapping.map.items() if not k.startswith("_")}
    assert reales, "el user_mapping quedó sin ningún mapeo real"
    assert all("." in v for v in reales.values()), "los valores deben ser usernames GitLab"
