"""Plan 252 F0/F1 — la frontera como DATO. 17 tests (12 de F0 + 5 de F1).

Una frontera que promete de mas es un bug de producto disfrazado de documentacion: el
README le dice al operador que ya esta resuelto, el operador no lo hace, y el pipeline
no anda. Por eso `evidence` es obligatorio y se verifica importando de verdad.
"""
from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from services import pipeline_capability_frontier as fr

BACKEND = Path(__file__).resolve().parent.parent

# UNICO lugar donde vive la lista negra. Se verifica por AST, JAMAS por `in` sobre el
# texto: el v1 asertaba sobre la cadena y al mismo tiempo mandaba escribir esas palabras
# en el docstring del modulo, o sea se detectaba a si mismo (rojo el dia 1).
_MODULOS_PROHIBIDOS = {
    "subprocess", "paramiko", "winrm", "pywinrm", "socket", "requests", "httpx",
    "urllib", "urllib3", "telnetlib", "ftplib", "asyncssh",
}

_MODULOS_DEL_PLAN = (
    "services/pipeline_capability_frontier.py",
    "services/pipeline_handoff_bundle.py",
)


# ── F0 ──────────────────────────────────────────────────────────────────────

def test_catalogo_tiene_14_acciones_con_ids_unicos():
    assert len(fr.ACTION_CATALOG) == 14
    ids = [a.id for a in fr.ACTION_CATALOG]
    assert len(set(ids)) == 14


def test_toda_accion_tiene_veredicto_y_motivo():
    """KPI-3."""
    for a in fr.ACTION_CATALOG:
        assert a.verdict in fr._DECLARED_VERDICTS, a.id
        assert a.reason.strip(), a.id
        assert a.label.strip(), a.id


def test_depends_declara_al_menos_una_sonda():
    for a in fr.ACTION_CATALOG:
        if a.verdict != fr.DEPENDS:
            continue
        assert len(a.probes) >= 1, a.id
        for p in a.probes:
            assert p in fr.PROBE_IDS, (a.id, p)


def test_can_y_cannot_no_declaran_sondas():
    for a in fr.ACTION_CATALOG:
        if a.verdict in (fr.CAN, fr.CANNOT):
            assert a.probes == (), a.id


def test_cannot_declarado_no_lo_promueve_ninguna_sonda():
    todo_true = {p: True for p in fr.PROBE_IDS}
    resuelto = {r.action.id: r.effective
                for r in fr.resolve_frontier(todo_true, pipeline_deploys=True)}
    assert resuelto["create_service_connection"] == fr.CANNOT
    assert resuelto["install_selfhosted_agent"] == fr.CANNOT
    assert resuelto["set_pipeline_secrets"] == fr.CANNOT


def test_probes_vacio_resuelve_unknown_nunca_can():
    """FALLA CERRADO: sin poder evaluar nada, no se promete nada."""
    resuelto = fr.resolve_frontier({}, pipeline_deploys=True)
    for r in resuelto:
        if r.action.verdict == fr.DEPENDS:
            assert r.effective == fr.UNKNOWN, r.action.id
            assert r.effective != fr.CAN
    # y todas esas cuentan como trabajo MANUAL, no como resuelto
    manuales = {r.action.id for r in fr.manual_actions(resuelto)}
    assert {a.id for a in fr.ACTION_CATALOG if a.verdict == fr.DEPENDS} <= manuales


def test_depends_con_una_sonda_true_resuelve_can():
    resuelto = {r.action.id: r for r in fr.resolve_frontier(
        {"ado_pat": True, "gitlab_token": False, "repo_writer": True},
        pipeline_deploys=True)}
    assert resuelto["register_pipeline_definition"].effective == fr.CAN
    assert "ado_pat" in resuelto["register_pipeline_definition"].probe_detail
    assert resuelto["commit_yaml_to_repo"].effective == fr.CAN


def test_depends_con_todas_false_es_cannot_now_no_unknown():
    resuelto = {r.action.id: r for r in fr.resolve_frontier(
        {"ado_pat": False, "gitlab_token": False, "repo_writer": False},
        pipeline_deploys=True)}
    assert resuelto["register_pipeline_definition"].effective == fr.CANNOT_NOW
    assert "falta" in resuelto["register_pipeline_definition"].probe_detail


def test_needs_deploy_filtra_acciones():
    assert len(fr.resolve_frontier({}, pipeline_deploys=False)) == 12
    assert len(fr.resolve_frontier({}, pipeline_deploys=True)) == 14


def test_manual_y_automatic_son_particion():
    for deploys in (False, True):
        for probes in ({}, {p: True for p in fr.PROBE_IDS},
                       {p: False for p in fr.PROBE_IDS}):
            resuelto = fr.resolve_frontier(probes, pipeline_deploys=deploys)
            man = fr.manual_actions(resuelto)
            aut = fr.automatic_actions(resuelto)
            assert not ({id(x) for x in man} & {id(x) for x in aut})
            assert len(man) + len(aut) == len(resuelto)


def test_modulos_sin_ejecucion_remota():
    """Por AST, no por texto. Y sin imports dinamicos, para que sea DECIDIBLE."""
    for rel in _MODULOS_DEL_PLAN:
        ruta = BACKEND / rel
        if not ruta.exists():
            pytest.skip("%s todavia no existe (nace en F2)" % rel)
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    raiz = alias.name.split(".")[0]
                    assert raiz not in _MODULOS_PROHIBIDOS, (rel, alias.name)
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                raiz = nodo.module.split(".")[0]
                assert raiz not in _MODULOS_PROHIBIDOS, (rel, nodo.module)
            elif isinstance(nodo, ast.Call):
                fn = nodo.func
                nombre = getattr(fn, "id", None) or getattr(fn, "attr", None)
                assert nombre not in ("__import__", "import_module"), (rel, nombre)


def test_toda_accion_ejecutable_cita_un_simbolo_que_existe():
    """§5.1 — si no hay ejecutor, la fila NO puede quedar CAN ni DEPENDS."""
    for a in fr.ACTION_CATALOG:
        if a.verdict not in (fr.CAN, fr.DEPENDS):
            continue
        assert a.evidence, "%s se declara ejecutable y no nombra ejecutor" % a.id
        modulo, _, simbolo = a.evidence.rpartition(".")
        assert modulo and simbolo, (a.id, a.evidence)
        try:
            mod = importlib.import_module(modulo)
        except Exception as e:  # noqa: BLE001
            pytest.fail("%s: no se pudo importar %s (%s)" % (a.id, modulo, e))
        assert hasattr(mod, simbolo), (a.id, a.evidence)


def test_cannot_no_tiene_ejecutor():
    """Reciproca: el dia que aparezca un ejecutor, la fila deja de ser CANNOT o el test
    se pone ROJO. Nunca sigue mintiendo en silencio."""
    for a in fr.ACTION_CATALOG:
        if a.verdict == fr.CANNOT:
            assert a.evidence == "", a.id
            assert a.manual_instruction.strip(), a.id


# ── F1 ──────────────────────────────────────────────────────────────────────

def test_probe_environment_devuelve_las_3_sondas():
    sondas = fr.probe_environment()
    assert set(sondas) == set(fr.PROBE_IDS)
    for v in sondas.values():
        assert v in (True, False, None)


def test_probe_nunca_lanza(monkeypatch):
    import services.ado_client as ado_client

    def _explota():
        raise RuntimeError("boom")

    monkeypatch.setattr(ado_client, "ado_pat_present", _explota)
    assert fr.probe_environment()["ado_pat"] is None


def test_probe_gitlab_env_vacia_es_false(monkeypatch, tmp_path):
    import runtime_paths

    monkeypatch.setenv("GITLAB_TOKEN", "")
    monkeypatch.setattr(runtime_paths, "backend_root", lambda: tmp_path)
    assert fr._probe_gitlab_token() is False


def test_probe_gitlab_env_con_valor_es_true(monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "x")
    assert fr._probe_gitlab_token() is True


def test_evaluate_frontier_no_lanza_y_es_deterministico():
    a = [(r.action.id, r.effective) for r in fr.evaluate_frontier()]
    b = [(r.action.id, r.effective) for r in fr.evaluate_frontier()]
    assert a == b
    assert len(a) == 12
    for _id, efectivo in a:
        assert efectivo in fr._EFFECTIVE_VERDICTS
