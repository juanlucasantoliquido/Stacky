"""Plan 216 F0 — Esquema y validación de `client_profile.state_flow`."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services.client_profile import (  # noqa: E402
    _check_state_flow,
    set_client_profile_state_flow,
    validate_client_profile,
)

_KEY = "STACKY_STATE_CONFIG_CENTRALIZED_ENABLED"


def _regla(ado_state="New", agent_type="business", rid="r1"):
    return {"id": rid, "ado_state": ado_state, "agent_type": agent_type,
            "on_failure_state": None, "created_at": "x", "updated_at": "x"}


def _perfil(state_flow=None):
    base = {"schema_version": 1, "code_layout": {}, "language": {}, "database": {},
            "build": {}, "conventions": {}, "docs_indexes": {}, "terminology": {},
            "extensions": {}, "tracker_state_machine": {}}
    if state_flow is not None:
        base["state_flow"] = state_flow
    return base


def test_state_flow_ausente_no_valida_nada():
    assert _check_state_flow(None) == []
    assert validate_client_profile(_perfil()).ok is True


def test_state_flow_valido_pasa():
    sf = {"version": "1.0", "rules": [_regla("New", "business", "r1"),
                                      _regla("Active", "developer", "r2")]}

    assert _check_state_flow(sf) == []
    assert validate_client_profile(_perfil(sf)).ok is True


def test_state_flow_no_dict_falla():
    errores = _check_state_flow(["no", "soy", "dict"])

    assert any("debe ser un objeto" in e for e in errores)


def test_rules_no_lista_falla():
    assert any("rules debe ser una lista" in e
               for e in _check_state_flow({"version": "1.0", "rules": "x"}))


def test_regla_sin_ado_state_falla():
    sf = {"rules": [{"id": "r1", "agent_type": "business"}]}

    assert any("ado_state es requerido" in e for e in _check_state_flow(sf))


def test_agent_type_invalido_falla():
    sf = {"rules": [_regla("New", "inventado")]}
    errores = _check_state_flow(sf)

    assert any("agent_type inválido" in e for e in errores)


def test_ado_state_duplicado_falla():
    sf = {"rules": [_regla("New", "business", "r1"), _regla("new", "developer", "r2")]}

    assert any("duplicado" in e for e in _check_state_flow(sf)), \
        "dos reglas para el mismo estado harían ambiguo qué agente corresponde"


def test_state_flow_invalido_es_error_bloqueante():
    resultado = validate_client_profile(_perfil({"rules": [_regla("New", "inventado")]}))

    assert resultado.ok is False


def test_set_client_profile_state_flow_persiste_y_relee(tmp_path, monkeypatch):
    import project_manager
    import services.client_profile as cp

    projects = tmp_path / "projects"
    (projects / "DEMO").mkdir(parents=True, exist_ok=True)
    (projects / "DEMO" / "config.json").write_text(
        json.dumps({"name": "DEMO", "issue_tracker": {"type": "azure_devops"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", projects)
    monkeypatch.setattr(cp, "projects_dir", lambda: projects)

    sf = {"version": "1.0", "rules": [_regla("New", "business")]}
    set_client_profile_state_flow("DEMO", sf)

    guardado = cp.load_client_profile("DEMO")
    assert guardado["state_flow"]["rules"][0]["ado_state"] == "New"


def test_set_client_profile_state_flow_rechaza_invalido(tmp_path, monkeypatch):
    import project_manager
    import services.client_profile as cp

    projects = tmp_path / "projects"
    (projects / "DEMO").mkdir(parents=True, exist_ok=True)
    (projects / "DEMO" / "config.json").write_text(
        json.dumps({"name": "DEMO"}), encoding="utf-8")
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", projects)
    monkeypatch.setattr(cp, "projects_dir", lambda: projects)

    with pytest.raises(cp.ClientProfileError):
        set_client_profile_state_flow("DEMO", {"rules": [_regla("New", "inventado")]})


def test_flag_registrada_default_on():
    from config import config as cfg
    from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    spec = next((s for s in FLAG_REGISTRY if s.key == _KEY), None)
    assert spec is not None
    assert spec.default is True
    assert _KEY in _CATEGORY_KEYS["flujo_funcional"]
    assert _KEY in _CURATED_DEFAULTS_ON
    assert getattr(cfg, _KEY) is True
