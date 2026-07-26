"""Plan 216 F1 — Store de flujo centralizado en el perfil, con migración lazy.

La migración es idempotente y NO destructiva: el `flow_config.json` legacy nunca
se borra ni se renombra, y si el perfil no se puede escribir la lectura sigue
funcionando con el legacy.
"""
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

from services import flow_config_store as fcs  # noqa: E402

_PROY = "DEMO216"


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    """Proyecto real en tmp_path con la flag ON."""
    import project_manager
    import services.client_profile as cp
    from config import config as cfg

    projects = tmp_path / "projects"
    (projects / _PROY).mkdir(parents=True, exist_ok=True)
    # El proyecto YA tiene perfil: es el caso real de un cliente configurado, y es
    # la precondición para que la migración actúe (nunca se crea un perfil de la nada).
    (projects / _PROY / "config.json").write_text(
        json.dumps({"name": _PROY, "issue_tracker": {"type": "azure_devops"},
                    "client_profile": {"schema_version": 1, "terminology": {}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", projects)
    monkeypatch.setattr(fcs, "PROJECTS_DIR", projects, raising=True)
    monkeypatch.setattr(cp, "projects_dir", lambda: projects)
    monkeypatch.setattr(fcs, "get_active_project", lambda: _PROY, raising=True)
    monkeypatch.setattr(cfg, "STACKY_STATE_CONFIG_CENTRALIZED_ENABLED", True, raising=False)
    return projects


def _legacy(projects: Path, rules: list) -> Path:
    path = projects / _PROY / "flow_config.json"
    path.write_text(json.dumps({"version": "1.0", "updated_at": "x", "rules": rules},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _regla(ado_state, agent_type, rid="r1"):
    return {"id": rid, "ado_state": ado_state, "agent_type": agent_type,
            "on_failure_state": None, "created_at": "x", "updated_at": "x"}


def _perfil(projects: Path) -> dict:
    from services.client_profile import load_client_profile

    return load_client_profile(_PROY) or {}


def test_migra_archivo_proyecto_a_perfil(entorno):
    _legacy(entorno, [_regla("New", "business"), _regla("Active", "developer", "r2")])

    reglas = fcs.list_rules(_PROY)

    assert {r["ado_state"] for r in reglas} == {"New", "Active"}
    assert len(_perfil(entorno)["state_flow"]["rules"]) == 2


def test_archivo_legacy_queda_intacto(entorno):
    path = _legacy(entorno, [_regla("New", "business")])
    antes = path.read_bytes()

    fcs.list_rules(_PROY)

    assert path.read_bytes() == antes, "la migración NO toca el archivo legacy"


def test_sin_legacy_siembra_defaults(entorno):
    reglas = fcs.list_rules(_PROY)

    assert len(reglas) == len(fcs._DEFAULT_RULES_SEED)
    assert {r["ado_state"] for r in reglas} == {e for e, _a in fcs._DEFAULT_RULES_SEED}


def test_idempotente_segunda_llamada_noop(entorno):
    _legacy(entorno, [_regla("New", "business")])
    primero = fcs.migrate_legacy_flow_config(_PROY)

    _legacy(entorno, [_regla("Otro", "qa", "r9")])  # el legacy cambia después
    segundo = fcs.migrate_legacy_flow_config(_PROY)

    assert segundo["rules"] == primero["rules"], "ya migrado ⇒ no se re-migra"


def test_legacy_con_regla_invalida_se_sanea(entorno):
    _legacy(entorno, [
        _regla("New", "business", "r1"),
        _regla("Bad", "inventado", "r2"),
        _regla("new", "developer", "r3"),   # duplicado case-insensitive
        {"id": "r4", "ado_state": "", "agent_type": "qa"},
    ])

    reglas = fcs.list_rules(_PROY)

    assert [r["ado_state"] for r in reglas] == ["New"], \
        "un legacy editado a mano no puede romper la migración"


def test_state_flow_corrupto_se_remigra(entorno):
    """Un `state_flow` corrupto en disco se trata como ausente: se re-migra."""
    _legacy(entorno, [_regla("New", "business")])
    cfg_file = entorno / _PROY / "config.json"
    cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
    # Se escribe DIRECTO al config.json: el validador rechazaría este shape, y el
    # punto del test es justamente que un archivo ya corrupto no rompa la lectura.
    cfg["client_profile"] = {"state_flow": {"rules": "no soy lista"}}
    cfg_file.write_text(json.dumps(cfg), encoding="utf-8")

    reglas = fcs.list_rules(_PROY)

    assert [r["ado_state"] for r in reglas] == ["New"]


def test_perfil_invalido_no_rompe_lectura_cae_legacy(entorno, monkeypatch):
    import services.client_profile as cp

    _legacy(entorno, [_regla("New", "business")])

    def _boom(project_name, state_flow):
        raise cp.ClientProfileError("otra sección del perfil está mal")

    monkeypatch.setattr(cp, "set_client_profile_state_flow", _boom, raising=True)

    reglas = fcs.list_rules(_PROY)

    assert [r["ado_state"] for r in reglas] == ["New"], \
        "si el perfil no se puede escribir, la lectura sigue con el legacy"


def test_crud_completo_contra_el_perfil(entorno):
    _legacy(entorno, [])

    creada = fcs.create_rule("Testing", "qa", project_name=_PROY)
    assert creada["ado_state"] == "Testing"
    assert _perfil(entorno)["state_flow"]["rules"][0]["agent_type"] == "qa"

    fcs.update_rule(creada["id"], "Testing", "developer", project_name=_PROY)
    assert fcs.list_rules(_PROY)[0]["agent_type"] == "developer"

    resuelto = fcs.resolve("Testing", project_name=_PROY)
    assert resuelto["found"] is True
    assert resuelto["agent_type"] == "developer"

    fcs.delete_rule(creada["id"], project_name=_PROY)
    assert fcs.list_rules(_PROY) == []


def test_duplicate_state_sigue_409(entorno):
    _legacy(entorno, [])
    fcs.create_rule("Testing", "qa", project_name=_PROY)

    with pytest.raises(fcs.DuplicateStateError):
        fcs.create_rule("Testing", "developer", project_name=_PROY)


def test_write_flag_on_espeja_legacy(entorno):
    """Apagar la flag no puede perder lo que el operador guardó."""
    path = _legacy(entorno, [])

    fcs.create_rule("Testing", "qa", project_name=_PROY)

    espejo = json.loads(path.read_text(encoding="utf-8"))
    assert [r["ado_state"] for r in espejo["rules"]] == ["Testing"]


def test_flag_off_byte_identico_legacy(entorno, monkeypatch):
    from config import config as cfg
    import services.client_profile as cp

    monkeypatch.setattr(cfg, "STACKY_STATE_CONFIG_CENTRALIZED_ENABLED", False, raising=False)
    _legacy(entorno, [_regla("New", "business")])

    def _no_debe_tocarse(*a, **kw):
        raise AssertionError("con la flag OFF no se accede al perfil")

    monkeypatch.setattr(cp, "load_client_profile", _no_debe_tocarse, raising=True)

    assert [r["ado_state"] for r in fcs.list_rules(_PROY)] == ["New"]
    assert "state_flow" not in json.loads(
        (entorno / _PROY / "config.json").read_text(encoding="utf-8"))


def test_sin_proyecto_usa_legacy_global(tmp_path, monkeypatch):
    from config import config as cfg
    import project_manager

    monkeypatch.setattr(cfg, "STACKY_STATE_CONFIG_CENTRALIZED_ENABLED", True, raising=False)
    monkeypatch.setattr(fcs, "get_active_project", lambda: None, raising=True)
    monkeypatch.setattr(project_manager, "get_project_config", lambda n: None, raising=True)
    monkeypatch.setattr(fcs, "get_project_config", lambda n: None, raising=True)

    assert fcs._resolve_project(None) is None, "sin proyecto ⇒ path legacy global"


def test_override_config_file_gana_a_flag(tmp_path, monkeypatch):
    """El override de tests conserva prioridad ABSOLUTA sobre la flag."""
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_STATE_CONFIG_CENTRALIZED_ENABLED", True, raising=False)
    archivo = tmp_path / "flow_config.json"
    archivo.write_text(json.dumps({"version": "1.0", "rules": [_regla("Solo", "qa")]}),
                       encoding="utf-8")
    monkeypatch.setattr(fcs, "_CONFIG_FILE", archivo, raising=True)

    assert [r["ado_state"] for r in fcs.list_rules(None)] == ["Solo"]


def test_seed_defaults_devuelve_conteo(entorno):
    creadas = fcs.seed_defaults_if_empty(_PROY)

    assert creadas == len(fcs._DEFAULT_RULES_SEED)
    assert fcs.seed_defaults_if_empty(_PROY) == 0, "segunda vez es no-op"


def test_put_perfil_sin_state_flow_preserva_reglas(entorno, monkeypatch):
    """El editor de perfil manda el objeto completo desde un snapshot que puede
    estar stale: omitir la key no puede borrar las reglas de flujo."""
    import api.client_profile as api_cp
    from app import create_app

    monkeypatch.setattr(api_cp, "PROJECTS_DIR", entorno, raising=True)
    _legacy(entorno, [])
    fcs.create_rule("Testing", "qa", project_name=_PROY)
    antes = fcs.list_rules(_PROY)
    # OJO: `import app` ejecuta create_app() a nivel de módulo, que ya sembró los
    # defaults; lo que importa acá no es la lista exacta sino que el PUT no la toque.
    assert any(x["ado_state"] == "Testing" for x in antes)

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        r = c.put(f"/api/projects/{_PROY}/client-profile",
                  json={"profile": {"schema_version": 1, "terminology": {}}})

    assert r.status_code == 200, r.get_json()
    assert fcs.list_rules(_PROY) == antes, "omitir la key NO puede borrar las reglas"
