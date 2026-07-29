"""Plan 267 F1 + F3 — Tests de /api/devops/actions/*.

19 tests: 5 de F1 (catalogo + health keys) + 14 de F3 (/propose, /preview).

SOLO LECTURA: ninguno de estos endpoints escribe en la DB ni en un sistema
externo, asi que este archivo no deberia ser flaky por SQLITE_LOCKED (R9).
"""
from __future__ import annotations

import pytest


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
_FLAGS = (
    "STACKY_DEVOPS_ACTION_CATALOG_ENABLED",
    "STACKY_DEVOPS_ACTION_NL_ENABLED",
    "STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED",
)


@pytest.fixture
def app():
    from app import create_app

    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def flags(monkeypatch):
    """Setea las 3 flags del plan y las restaura. Devuelve el setter."""
    import config as cfg

    def _set(**kwargs):
        for key, value in kwargs.items():
            assert key in _FLAGS, key
            monkeypatch.setattr(cfg.config, key, value, raising=False)

    return _set


@pytest.fixture
def health_all_on(monkeypatch):
    """Parchea el seam _health_payload_for_catalog con un health sintetico donde
    el master y todos los health_key del catalogo estan en True. Evita
    monkeypatchear ~45 atributos de config.config [C13]."""
    import api.devops_actions as mod
    from services.devops_action_catalog import DEVOPS_ACTION_CATALOG, MASTER_HEALTH_KEY

    payload = {MASTER_HEALTH_KEY: True}
    for a in DEVOPS_ACTION_CATALOG:
        if a.health_key:
            payload[a.health_key] = True
    monkeypatch.setattr(
        mod, "_health_payload_for_catalog", lambda: dict(payload), raising=False
    )
    return payload


# ==========================================================================
# F1 — 5 tests
# ==========================================================================
def test_catalog_flag_off_404(client, flags):
    flags(STACKY_DEVOPS_ACTION_CATALOG_ENABLED=False)
    r = client.get("/api/devops/actions/catalog")
    assert r.status_code == 404
    assert r.get_json() == {"error": "devops_action_catalog_disabled"}


def test_catalog_flag_on_200_y_shape(client, flags, health_all_on):
    flags(STACKY_DEVOPS_ACTION_CATALOG_ENABLED=True)
    r = client.get("/api/devops/actions/catalog")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["version"] == "1"
    assert isinstance(body["actions"], list) and body["actions"]
    esperado = {
        "id", "label", "summary", "section_id", "nav_path", "effect", "impact",
        "targets_environment", "health_key", "flag_key", "reach", "params",
        "phrases",
    }
    for item in body["actions"]:
        assert set(item.keys()) == esperado, sorted(set(item.keys()) ^ esperado)


def test_catalog_filtra_por_health(client, flags, monkeypatch):
    """[C13] El seam se parchea; no se enumeran las ~45 flags de _health_payload."""
    import api.devops_actions as mod

    flags(STACKY_DEVOPS_ACTION_CATALOG_ENABLED=True)
    monkeypatch.setattr(
        mod, "_health_payload_for_catalog", lambda: {"flag_enabled": False},
        raising=False,
    )
    r = client.get("/api/devops/actions/catalog")
    assert r.status_code == 200
    ids = {a["id"] for a in r.get_json()["actions"]}
    assert ids == {"devops.logs.tail", "devops.incidents.list"}, sorted(ids)


def test_health_expone_las_tres_keys_nuevas(client):
    body = client.get("/api/devops/health").get_json()
    for key in ("action_catalog_enabled", "action_nl_enabled",
                "agent_action_run_enabled"):
        assert key in body, key


def test_bootstrap_health_paridad(client, monkeypatch):
    """/bootstrap y /health comparten _health_payload(): mismas 3 keys."""
    from api.devops import _health_payload

    health = client.get("/api/devops/health").get_json()
    directo = _health_payload()
    tres = ("action_catalog_enabled", "action_nl_enabled", "agent_action_run_enabled")
    assert {k: health[k] for k in tres} == {k: directo[k] for k in tres}


# ==========================================================================
# F3 — 14 tests
# ==========================================================================
def _propose(client, **body):
    return client.post("/api/devops/actions/propose", json=body)


def test_propose_nl_flag_off_404(client, flags):
    flags(STACKY_DEVOPS_ACTION_CATALOG_ENABLED=True,
          STACKY_DEVOPS_ACTION_NL_ENABLED=False)
    r = _propose(client, text="ver los logs")
    assert r.status_code == 404
    assert r.get_json() == {"error": "devops_action_nl_disabled"}


def test_propose_sin_text_400(client, flags):
    flags(STACKY_DEVOPS_ACTION_CATALOG_ENABLED=True,
          STACKY_DEVOPS_ACTION_NL_ENABLED=True)
    r = _propose(client, text="   ")
    assert r.status_code == 400
    assert r.get_json()["ok"] is False


def test_propose_devuelve_accion_tipada(client, flags, health_all_on):
    flags(STACKY_DEVOPS_ACTION_CATALOG_ENABLED=True,
          STACKY_DEVOPS_ACTION_NL_ENABLED=True)
    r = _propose(client, text="quiero ver los logs", params={"project": "Pacifico"})
    assert r.status_code == 200
    p = r.get_json()["proposal"]
    assert p["action_id"] == "devops.logs.tail", p["action_id"]
    assert p["effect"] == "read"
    assert p["needs_confirmation"] is False
    assert p["blocked_reason"] == ""


def test_propose_write_marca_needs_confirmation(client, flags, health_all_on):
    flags(STACKY_DEVOPS_ACTION_CATALOG_ENABLED=True,
          STACKY_DEVOPS_ACTION_NL_ENABLED=True,
          STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED=True)
    r = _propose(client, text="disparar la pipeline",
                 params={"project": "P", "environment": "qa", "pipeline_id": "7"})
    p = r.get_json()["proposal"]
    assert p["action_id"] == "devops.pipeline.trigger", p["action_id"]
    assert p["effect"] == "write"
    assert p["impact"] == "high"
    assert p["needs_confirmation"] is True


def test_propose_write_bloqueada_si_run_flag_off(client, flags, health_all_on):
    """La propuesta IGUAL se devuelve: el operador la ve y navega al panel."""
    flags(STACKY_DEVOPS_ACTION_CATALOG_ENABLED=True,
          STACKY_DEVOPS_ACTION_NL_ENABLED=True,
          STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED=False)
    r = _propose(client, text="disparar la pipeline",
                 params={"project": "P", "environment": "qa", "pipeline_id": "7"})
    p = r.get_json()["proposal"]
    assert p is not None
    assert p["blocked_reason"] == "agent_write_disabled", p["blocked_reason"]


def test_propose_param_faltante_genera_pregunta(client, flags, health_all_on):
    flags(STACKY_DEVOPS_ACTION_CATALOG_ENABLED=True,
          STACKY_DEVOPS_ACTION_NL_ENABLED=True,
          STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED=True)
    r = _propose(client, text="disparar la pipeline",
                 params={"project": "P", "pipeline_id": "7"})
    p = r.get_json()["proposal"]
    assert p["blocked_reason"] == "missing_params", p["blocked_reason"]
    assert len(p["open_questions"]) == 1, p["open_questions"]
    assert "Entorno" in p["open_questions"][0], p["open_questions"][0]


def test_propose_sin_match_no_lanza(client, flags, health_all_on):
    flags(STACKY_DEVOPS_ACTION_CATALOG_ENABLED=True,
          STACKY_DEVOPS_ACTION_NL_ENABLED=True)
    r = _propose(client, text="receta de milanesas")
    assert r.status_code == 200
    body = r.get_json()
    assert body["proposal"] is None
    assert body["blocked_reason"] == "no_match"
    assert body["suggestions"]


def test_propose_copilot_mismo_resultado_que_cli(client, flags, health_all_on):
    """KPI-5: los 3 runtimes obtienen el MISMO proposal. Es el test que hace
    fallar cualquier regresion que reintroduzca el 400 de devops_agent.py."""
    flags(STACKY_DEVOPS_ACTION_CATALOG_ENABLED=True,
          STACKY_DEVOPS_ACTION_NL_ENABLED=True,
          STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED=True)
    salidas = []
    for runtime in ("codex_cli", "claude_code_cli", "copilot"):
        r = _propose(client, text="ver los logs", runtime=runtime,
                     params={"project": "Pacifico"})
        assert r.status_code == 200, (runtime, r.status_code)
        salidas.append(r.get_json()["proposal"])
    assert salidas[0] == salidas[1] == salidas[2], salidas


def test_preview_action_id_desconocido_404(client, flags, health_all_on):
    flags(STACKY_DEVOPS_ACTION_CATALOG_ENABLED=True,
          STACKY_DEVOPS_ACTION_NL_ENABLED=True)
    r = client.post("/api/devops/actions/preview", json={"action_id": "devops.no.existe"})
    assert r.status_code == 404
    assert r.get_json() == {"error": "devops_action_unknown"}


def test_preview_accion_gateada_404(client, flags, monkeypatch):
    """Una accion cuyo health_key esta en False NO se previsualiza."""
    import api.devops_actions as mod

    flags(STACKY_DEVOPS_ACTION_CATALOG_ENABLED=True,
          STACKY_DEVOPS_ACTION_NL_ENABLED=True)
    monkeypatch.setattr(
        mod, "_health_payload_for_catalog", lambda: {"flag_enabled": False},
        raising=False,
    )
    r = client.post("/api/devops/actions/preview",
                    json={"action_id": "devops.pipeline.trigger"})
    assert r.status_code == 404
    assert r.get_json() == {"error": "devops_action_gated"}


def test_preview_no_ejecuta_nada(client, flags, health_all_on, monkeypatch):
    """Los modulos de ejecucion revientan si se los llama; el endpoint da 200."""
    import services.devops_action_proposal as dap

    flags(STACKY_DEVOPS_ACTION_CATALOG_ENABLED=True,
          STACKY_DEVOPS_ACTION_NL_ENABLED=True,
          STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED=True)

    def _boom(*a, **k):  # pragma: no cover - debe NO llamarse
        raise AssertionError("el preview ejecuto algo")

    import subprocess

    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)
    assert dap.PROPOSAL_VERSION == "1"

    r = client.post("/api/devops/actions/preview", json={
        "action_id": "devops.remote_console.run",
        "params": {"project": "P", "environment": "prod",
                   "server_alias": "srv", "command": "dir"},
    })
    assert r.status_code == 200, r.get_json()


def test_what_will_happen_nombra_entorno_e_impacto(client, flags, health_all_on):
    flags(STACKY_DEVOPS_ACTION_CATALOG_ENABLED=True,
          STACKY_DEVOPS_ACTION_NL_ENABLED=True,
          STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED=True)
    r = client.post("/api/devops/actions/preview", json={
        "action_id": "devops.deployment.execute",
        "params": {"project": "P", "environment": "prod", "deployment_id": "9"},
    })
    frase = r.get_json()["proposal"]["what_will_happen"]
    assert "prod" in frase, frase
    assert any(t in frase for t in
               ("sin impacto", "impacto bajo", "impacto alto")), frase


def test_propose_ambiguo_devuelve_alternativas(client, flags, monkeypatch,
                                               health_all_on):
    """[C7] Es el UNICO test que ejecuta la linea replace(prop, ...). Sin el, el
    NameError del v1 llegaba a produccion con la suite en verde."""
    import api.devops_actions as mod
    from services.devops_action_catalog import DevOpsAction, canonical_reach

    flags(STACKY_DEVOPS_ACTION_CATALOG_ENABLED=True,
          STACKY_DEVOPS_ACTION_NL_ENABLED=True,
          STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED=True)

    def _mk(action_id: str) -> DevOpsAction:
        return DevOpsAction(
            id=action_id, label=action_id, summary="s", section_id=None,
            nav_path="/x", effect="read", impact="none",
            targets_environment=False, health_key="", flag_key="",
            reach=canonical_reach("read"), params=(), phrases=("empate exacto ahora",),
        )

    gemelas = [_mk("devops.gemela.uno"), _mk("devops.gemela.dos")]
    monkeypatch.setattr(
        "services.devops_action_catalog.assistant_actions",
        lambda health: gemelas, raising=False,
    )
    monkeypatch.setattr(
        "services.devops_action_catalog.get_action",
        lambda aid: {a.id: a for a in gemelas}.get(aid), raising=False,
    )
    assert mod.bp.name == "devops_actions"

    r = _propose(client, text="empate exacto ahora")
    assert r.status_code == 200, r.get_json()
    p = r.get_json()["proposal"]
    assert p["blocked_reason"] == "ambiguous", p["blocked_reason"]
    assert p["alternatives"], p


def test_propose_respeta_reach_assistant(client, flags, monkeypatch, health_all_on):
    """Una accion sin 'assistant' en reach NUNCA sale propuesta, aunque su frase
    sea un match perfecto: assistant_actions() es el unico universo del matcher."""
    from services.devops_action_catalog import DevOpsAction, assistant_actions

    flags(STACKY_DEVOPS_ACTION_CATALOG_ENABLED=True,
          STACKY_DEVOPS_ACTION_NL_ENABLED=True)

    sin_assistant = DevOpsAction(
        id="devops.oculta.accion", label="Oculta", summary="s", section_id=None,
        nav_path="/x", effect="read", impact="none", targets_environment=False,
        health_key="", flag_key="", reach=("button",), params=(),
        phrases=("frase magica irrepetible",),
    )
    universo = [*assistant_actions(health_all_on), sin_assistant]
    monkeypatch.setattr(
        "services.devops_action_catalog.assistant_actions",
        lambda health: [a for a in universo if "assistant" in a.reach],
        raising=False,
    )
    r = _propose(client, text="frase magica irrepetible")
    assert r.status_code == 200
    assert r.get_json()["proposal"] is None, r.get_json()
