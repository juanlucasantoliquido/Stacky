"""Plan 250 F5 — la puerta de entrada en lenguaje natural. 11 tests, CERO red.

El LLM NO escribe YAML. Nunca. Devuelve un EditIntent de 9 campos que el operador lee
de un vistazo; el tramo intent -> patch es determinista byte a byte (F1). Todo el no
determinismo del modelo queda concentrado ahi, en vez de repartido por 130 lineas.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from services import pipeline_patcher as pp
from services.cicd_task_catalog import PROFILE_DOTNET_FRAMEWORK as PERFIL

BACKEND = Path(__file__).resolve().parent.parent
GOLDEN = BACKEND / "tests" / "fixtures" / "cicd_nl" / "golden"
INTENTS = BACKEND / "tests" / "fixtures" / "pipeline_edit" / "intents"
BASE = "/api/pipeline-editor"


def _yaml() -> str:
    return (GOLDEN / "ci-cd-online.yml").read_text(encoding="utf-8")


@pytest.fixture
def app():
    from app import create_app

    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch, tmp_path):
    import config as cfg
    import runtime_paths

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_NL_EDIT_ENABLED", True, raising=False)
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    yield


class _Resultado:
    def __init__(self, texto, success=True, error=None):
        self.text = texto
        self.parsed_json = None
        self.success = success
        self.error = error


def _doble_call_llm(monkeypatch, payload, success=True, error=None):
    """Doble de call_llm que CUENTA invocaciones (KPI-5)."""
    from services.pm import pm_llm_client

    contador = {"n": 0}

    def _fake(spec):
        contador["n"] += 1
        # el spec tiene que ser construible: el plan escribia LLMCallSpec(prompt=...),
        # que es un TypeError contra el dataclass real.
        assert spec.prompt_type == "pipeline_edit_intent_v1"
        assert spec.temperature == 0.0
        assert spec.expect_json is True
        return _Resultado(json.dumps(payload) if payload is not None else "",
                          success=success, error=error)

    monkeypatch.setattr(pm_llm_client, "call_llm", _fake)
    return contador


# ── 1 ────────────────────────────────────────────────────────────────────────
def test_seis_fixtures_producen_el_intent_esperado():
    archivos = sorted(INTENTS.glob("*.json"))
    assert len(archivos) >= 6
    for archivo in archivos:
        crudo = json.loads(archivo.read_text(encoding="utf-8"))
        intent, errores = pp.validate_intent_dict(crudo, profile=PERFIL)
        assert errores == (), f"{archivo.name}: {errores}"
        assert intent is not None
        assert intent.verb == crudo["verb"]
        assert intent.verb in pp.EDIT_VERBS
        assert intent.target_path == (crudo.get("target_path") or "")
        assert intent.task_ref == crudo.get("task_ref")
        assert intent.notes == tuple(crudo.get("notes") or ())
        # y cada intent de fixture COMPILA de verdad contra el corpus
        if intent.verb != "add_stage" or "stages" in _yaml():
            ops, errs = pp.plan_edit(_yaml(), intent, profile=PERFIL)
            assert errs == (), f"{archivo.name}: {errs}"
            assert ops


# ── 2 ────────────────────────────────────────────────────────────────────────
def test_pedido_ambiguo_devuelve_preguntas(monkeypatch):
    from api import pipeline_editor as pe

    contador = _doble_call_llm(monkeypatch, {"questions": [
        "¿sobre que job querés el cambio? Necesito el target_path"]})
    intent, preguntas = pe.interpret_edit("mejora esto", yaml_text=_yaml(),
                                          profile=PERFIL)
    assert intent is None
    assert preguntas and "target_path" in preguntas[0]
    assert contador["n"] == 1


# ── 3 ────────────────────────────────────────────────────────────────────────
def test_verbo_fuera_de_la_lista_rechazado(monkeypatch):
    from api import pipeline_editor as pe

    contador = _doble_call_llm(monkeypatch, {"verb": "delete_pipeline"})
    intent, errores = pe.interpret_edit("borra la pipeline", yaml_text=_yaml(),
                                        profile=PERFIL)
    assert intent is None
    assert any("delete_pipeline" in e for e in errores)
    assert contador["n"] == 1
    ops, _e = pp.plan_edit(_yaml(), pp.EditIntent(verb="delete_pipeline"), profile=PERFIL)
    assert ops == ()


# ── 4 ────────────────────────────────────────────────────────────────────────
def test_tarea_alucinada_rechazada(monkeypatch):
    from api import pipeline_editor as pe

    _doble_call_llm(monkeypatch, {
        "verb": "add_step", "target_path": "stages[0].jobs[0].steps",
        "position": "end", "task_ref": "VSBuild@2", "inputs": {}})
    intent, errores = pe.interpret_edit("agrega VSBuild 2", yaml_text=_yaml(),
                                        profile=PERFIL)
    assert intent is None
    assert any("VSBuild@2" in e and "catalogo" in e for e in errores)


# ── 5 ────────────────────────────────────────────────────────────────────────
def test_una_sola_llamada_llm_por_pedido(monkeypatch):
    """KPI-5 — exactamente 1, INCLUSO cuando el JSON devuelto es invalido.
    Cero reintentos automaticos: con el operador mirando la pantalla, preguntarle
    cuesta 0 tokens y acierta mas que un bucle de auto-reparacion."""
    from api import pipeline_editor as pe

    contador = _doble_call_llm(monkeypatch, {"verb": "no_existe", "target_path": 5})
    intent, errores = pe.interpret_edit("x", yaml_text=_yaml(), profile=PERFIL)
    assert intent is None and errores
    assert contador["n"] == 1
    assert pe.MAX_LLM_CALLS_PER_REQUEST == 1


# ── 6 ────────────────────────────────────────────────────────────────────────
def test_no_lanza_si_call_llm_falla(monkeypatch):
    from api import pipeline_editor as pe

    _doble_call_llm(monkeypatch, None, success=False, error="ConnectionError: sin red")
    intent, errores = pe.interpret_edit("x", yaml_text=_yaml(), profile=PERFIL)
    assert intent is None
    assert any("sin red" in e for e in errores)


# ── 7 ────────────────────────────────────────────────────────────────────────
def test_el_texto_nl_no_llega_al_yaml(monkeypatch):
    """El texto en lenguaje natural NUNCA se copia al YAML, ni como comentario."""
    from api import pipeline_editor as pe

    veneno = "# hackme $(malicious)"
    _doble_call_llm(monkeypatch, {
        "verb": "add_step", "target_path": "stages[0].jobs[0].steps", "position": "end",
        "task_ref": "PublishCodeCoverageResults@2",
        "inputs": {"summaryFileLocation": "cov.xml"}, "display_name": "Cobertura"})
    intent, errores = pe.interpret_edit("agregá cobertura y " + veneno,
                                        yaml_text=_yaml(), profile=PERFIL)
    assert errores == (), errores
    ops, errs = pp.plan_edit(_yaml(), intent, profile=PERFIL)
    assert errs == ()
    res = pp.apply_ops(_yaml(), ops)
    assert res.ok
    assert "hackme" not in res.text
    assert "$(malicious)" not in res.text


# ── 8 ────────────────────────────────────────────────────────────────────────
def test_recomendacion_sin_plan_248_degrada(monkeypatch):
    """Import BLANDO: sin el modulo del 248 devuelve mensaje, NUNCA ImportError."""
    import builtins

    from api import pipeline_editor as pe

    real = builtins.__import__

    def _sin_248(nombre, *a, **kw):
        if nombre == "services.pipeline_recommendations":
            raise ImportError("no existe")
        return real(nombre, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", _sin_248)
    intent, mensajes = pe.recommendation_to_intent("OPT001", _yaml(), profile=PERFIL)
    assert intent is None
    assert any("plan 248" in m for m in mensajes)


def test_recomendacion_con_plan_248_presente_no_lanza():
    from api import pipeline_editor as pe

    intent, mensajes = pe.recommendation_to_intent("OPT001", _yaml(), profile=PERFIL)
    assert intent is None
    assert mensajes and isinstance(mensajes[0], str)


# ── 9 ────────────────────────────────────────────────────────────────────────
def test_intent_se_muestra_antes_del_diff(app, monkeypatch):
    _doble_call_llm(monkeypatch, {
        "verb": "set_task_input", "target_path": "stages[0].jobs[0].steps",
        "anchor_ref": "VSBuild@1", "task_ref": "VSBuild@1",
        "inputs": {"configuration": "Debug"},
        "notes": ["asumi que te referias al build principal"]})
    r = app.test_client().post(BASE + "/interpret",
                               json={"text": "pasalo a Debug", "yaml": _yaml()})
    assert r.status_code == 200
    body = r.get_json()
    assert body["intent"]["verb"] == "set_task_input"
    assert body["notes"] == ["asumi que te referias al build principal"]
    assert "yaml" not in body and "hunks" not in body


# ── 10 ───────────────────────────────────────────────────────────────────────
def test_interpret_404_con_flag_off(app, monkeypatch):
    """C7 — /interpret es el UNICO endpoint que gasta tokens. Un endpoint de LLM sin
    test de flag-off es una fuga esperando a que alguien lo llame."""
    import config as cfg

    contador = _doble_call_llm(monkeypatch, {"verb": "add_step"})
    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_NL_EDIT_ENABLED", False,
                        raising=False)
    r = app.test_client().post(BASE + "/interpret",
                               json={"text": "algo", "yaml": _yaml()})
    assert r.status_code == 404
    assert contador["n"] == 0, "con la flag OFF no se puede gastar ni un token"


# ── 11 ───────────────────────────────────────────────────────────────────────
def test_validate_intent_dict_es_puro():
    """C1 — la validacion vive en services/pipeline_patcher.py y no importa nada de
    api/: se la invoca con un dict crudo, sin app Flask ni red."""
    import ast

    fuente = (BACKEND / "services" / "pipeline_patcher.py").read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    importados = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom) and nodo.module:
            importados.append(nodo.module)
        elif isinstance(nodo, ast.Import):
            importados.extend(a.name for a in nodo.names)
    assert not [m for m in importados if m.startswith("api")], importados
    assert not [m for m in importados if m in ("flask", "requests")], importados

    intent, errores = pp.validate_intent_dict(
        {"verb": "remove_step", "target_path": "steps", "anchor_ref": "X@1"},
        profile=PERFIL)
    assert errores == ()
    assert intent.verb == "remove_step"
    assert pp.INTENT_SCHEMA["verb"]["enum"] == pp.EDIT_VERBS
