"""tests/test_plan294_wizard_api.py — Plan 294 F6.

Los 4 endpoints del asistente, DELGADOS a proposito: validan el cuerpo, llaman a
services/ y serializan. Cero logica de dominio.

EL CASO MAS IMPORTANTE ES EL 8: el blueprint NO expone escritura. El paso 7 reusa
los endpoints de commit y de disparo que ya tienen su confirmacion explicita; no
se crea un tercero. Sin ese caso, "no duplicamos el HITL" es una promesa.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

_BACKEND = pathlib.Path(__file__).resolve().parents[1]

_RUTAS = (
    ("get", "/api/pipeline-wizard/detect"),
    ("post", "/api/pipeline-wizard/questions"),
    ("post", "/api/pipeline-wizard/draft"),
    ("post", "/api/pipeline-wizard/review"),
)

_INTENT_OK = {
    "project": "RecoveryStrategy",
    "provider": "ado",
    "default_branch": "main",
    "stack": "dotnet",
    "goal": "ci_completo",
    "pipeline_kind": "ci",
    "triggers": ["main"],
    "build_command": "dotnet build",
    "test_command": "dotnet test",
    "runtime": "claude_code_cli",
}


@pytest.fixture
def app():
    from app import create_app

    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    import config as cfg

    # GOTCHA: se parchea la INSTANCIA (_config.config), no el modulo.
    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_WIZARD_ENABLED", True, raising=False)
    yield


@pytest.fixture(autouse=True)
def _sin_inventario_real(monkeypatch):
    """El paso 1 no debe depender del repositorio del operador para testearse."""
    import services.pipeline_project_probe as probe

    monkeypatch.setattr(
        probe, "_build_inventory",
        lambda *a, **k: {"ok": True, "pipelines": [], "sources": [], "counts": {}},
    )
    yield


def test_r11_flag_apagada_los_cuatro_dan_404(app, monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_WIZARD_ENABLED", False, raising=False)
    c = app.test_client()
    for metodo, ruta in _RUTAS:
        resp = getattr(c, metodo)(ruta, json={})
        assert resp.status_code == 404, f"{metodo.upper()} {ruta} -> {resp.status_code}"


def test_detect_devuelve_las_trece_claves(app):
    resp = app.test_client().get("/api/pipeline-wizard/detect")
    assert resp.status_code == 200
    body = resp.get_json()
    for clave in (
        "ok", "project", "provider", "repository", "default_branch", "stack",
        "framework", "package_manager", "build_command", "test_command",
        "variables", "inventory", "sources",
    ):
        assert clave in body, f"falta {clave}"


def test_questions_del_objetivo_simple_no_pasa_de_cuatro(app):
    resp = app.test_client().post(
        "/api/pipeline-wizard/questions", json={"goal": "ejecutar_tests", "stack": "node"}
    )
    assert resp.status_code == 200
    preguntas = resp.get_json()["questions"]
    assert len(preguntas) <= 4, [q["id"] for q in preguntas]


def test_questions_con_objetivo_desconocido_da_400_en_castellano(app):
    resp = app.test_client().post(
        "/api/pipeline-wizard/questions", json={"goal": "hacer_magia"}
    )
    assert resp.status_code == 400
    motivos = resp.get_json()["errors"]
    assert motivos and all(m.strip() for m in motivos)


def test_draft_devuelve_los_dos_proveedores_y_ningun_valor_de_variable(app):
    cuerpo = dict(_INTENT_OK, variables=["NUGET_FEED", "SIGNING_KEY"])
    resp = app.test_client().post("/api/pipeline-wizard/draft", json=cuerpo)
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert "ado" in body and "gitlab" in body
    texto = str(body["ado"]) + str(body["gitlab"])
    # R3: el NOMBRE puede viajar; un VALOR nunca. El puente los pone en vacio.
    assert "NUGET_FEED" in texto
    assert "secreto" not in texto.lower()


def test_draft_sin_objetivo_da_400(app):
    resp = app.test_client().post("/api/pipeline-wizard/draft", json=dict(_INTENT_OK, goal=""))
    assert resp.status_code == 400
    assert resp.get_json()["errors"]


def test_review_separa_advertencias_de_bloqueantes(app):
    """El brief lo exige explicitamente: advertencia != error bloqueante."""
    resp = app.test_client().post("/api/pipeline-wizard/review", json=_INTENT_OK)
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert "warnings" in body and "blocking" in body
    assert isinstance(body["warnings"], list)
    assert isinstance(body["blocking"], list)


def test_el_blueprint_no_expone_escritura(app):
    """Guarda arquitectonica: el paso 7 reusa el commit y el disparo que YA
    existen, con su confirmacion explicita. No se crea un tercero."""
    reglas = [
        r for r in app.url_map.iter_rules()
        if str(r.rule).startswith("/api/pipeline-wizard/")
    ]
    assert reglas, "el blueprint del asistente no quedo registrado"
    for r in reglas:
        endpoint = str(r.endpoint).lower()
        for prohibido in ("commit", "trigger", "apply", "delete"):
            assert prohibido not in endpoint, f"{r.rule} expone {prohibido}"
        assert set(r.methods) <= {"GET", "POST", "HEAD", "OPTIONS"}, (r.rule, r.methods)


def test_r3_una_variable_con_valor_pegado_da_400(app):
    resp = app.test_client().post(
        "/api/pipeline-wizard/draft", json=dict(_INTENT_OK, variables=["K=v"])
    )
    assert resp.status_code == 400


def test_kpi4_el_blueprint_no_llama_a_ningun_modelo(app):
    """C19 — determinista: se lee el fuente Y ademas se comprueba que los 4
    endpoints responden en la corrida normal."""
    fuente = (_BACKEND / "api" / "pipeline_wizard.py").read_text(encoding="utf-8")
    for prohibida in (
        "llm", "anthropic", "openai", "copilot_bridge", "model_router",
        "requests", "urllib", "httpx",
    ):
        assert prohibida not in fuente, f"api/pipeline_wizard.py menciona {prohibida!r}"

    c = app.test_client()
    assert c.get("/api/pipeline-wizard/detect").status_code == 200
    assert c.post("/api/pipeline-wizard/questions", json={"goal": "ejecutar_tests"}).status_code == 200
    assert c.post("/api/pipeline-wizard/draft", json=_INTENT_OK).status_code == 200
    assert c.post("/api/pipeline-wizard/review", json=_INTENT_OK).status_code == 200


def test_c7_el_mapeo_paso_estado_es_total_y_legal():
    """ESTE es el caso que convierte 'reusamos la maquina del plan 279' de
    promesa en hecho. Si alguien inventa un estado, se pone rojo."""
    from services.pipeline_intent import WIZARD_STEP_TO_STATE
    from services.pipeline_session import PIPELINE_SESSION_STATES, can_transition

    assert set(WIZARD_STEP_TO_STATE) == {f"p{k}" for k in range(1, 8)}
    assert set(WIZARD_STEP_TO_STATE.values()) <= set(PIPELINE_SESSION_STATES)
    for k in range(1, 7):
        o, d = WIZARD_STEP_TO_STATE[f"p{k}"], WIZARD_STEP_TO_STATE[f"p{k + 1}"]
        assert o == d or can_transition(o, d), (k, o, d)
