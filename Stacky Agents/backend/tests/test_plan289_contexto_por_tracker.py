"""Plan 289 — El agente deja de trabajar a ciegas sobre un ticket de GitLab.

PATA A (xfail hasta F6): con un proyecto GitLab, el enriquecimiento produce el
  bloque de comentarios con las notas del issue.
PATA B (xfail hasta F2): los 3 runtimes persisten el contador de enriquecimiento.

NO importa db, ni app, ni models (P6). El ticket es un SimpleNamespace y el
provider es un doble local.
"""
from __future__ import annotations

import ast
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# -- Dobles -------------------------------------------------------------------

NOTAS_GITLAB = [
    {"id": 11, "body": "Primera nota del cliente", "system": False,
     "author": {"name": "Ana Perez", "username": "aperez"},
     "created_at": "2026-07-30T10:11:12.000Z"},
    {"id": 12, "body": "Segunda nota con detalle", "system": False,
     "author": {"name": "Beto Diaz", "username": "bdiaz"},
     "created_at": "2026-07-31T09:00:00.000Z"},
    {"id": 13, "body": "Tercera nota", "system": False,
     "author": {"name": "Ana Perez", "username": "aperez"},
     "created_at": "2026-08-01T08:00:00.000Z"},
]


class _FakeGitLabProvider:
    name = "gitlab"

    def __init__(self, notas):
        self._notas = notas
        self.llamadas = []

    def fetch_comments(self, item_id):          # firma REAL de GitLab: SIN top
        self.llamadas.append(item_id)
        return list(self._notas)


def _ctx_gitlab():
    """Doble de ProjectContext con tracker gitlab."""
    return types.SimpleNamespace(
        stacky_project_name="GITLABTEST", tracker_type="gitlab",
        tracker_project="grupo/proyecto", organization=None,
        base_url="https://gitlab.interno", tracker_group="grupo",
        workspace_root=None, auth_path=None, vscode_port=None,
    )


@pytest.fixture
def proyecto_gitlab(monkeypatch):
    """Fija el contexto de proyecto a uno GitLab y devuelve el provider falso.

    Parchea LOS DOS seams por separado a proposito:
      - resolve_project_context: lo consume build_ado_client (project_context.py:510)
      - get_tracker_provider:    lo consumira el dispatcher de F6
    """
    import services.project_context as pc
    import services.tracker_provider as tp

    fake = _FakeGitLabProvider(NOTAS_GITLAB)
    monkeypatch.setattr(pc, "resolve_project_context", lambda *a, **k: _ctx_gitlab())
    monkeypatch.setattr(tp, "get_tracker_provider", lambda project=None: fake)
    return fake


# -- PATA A - el bloque que hoy no existe (verde en F6) -----------------------

@pytest.mark.xfail(strict=True, reason="Plan 289 F6 lo pone verde: hoy el enriquecimiento es ADO-only")
def test_un_issue_de_gitlab_con_3_notas_produce_un_bloque_con_las_3(proyecto_gitlab):
    from services.ado_context import build_ado_context_blocks

    ticket = types.SimpleNamespace(
        ado_id=1124, external_id=1124, stacky_project_name="GITLABTEST",
        tracker_type="gitlab", project="grupo/proyecto",
    )
    blocks, stats = build_ado_context_blocks(
        1124, project_name="GITLABTEST", tracker_project="grupo/proyecto", ticket=ticket,
    )

    comentarios = [b for b in blocks if b.get("id") == "ado-comments"]
    assert len(comentarios) == 1, f"esperaba 1 bloque de comentarios, hay {len(comentarios)}: {blocks}"
    contenido = comentarios[0]["content"]
    assert "Primera nota del cliente" in contenido
    assert "Segunda nota con detalle" in contenido
    assert "Tercera nota" in contenido
    assert stats["comments_count"] == 3
    # El id que se le pasa al provider es el iid, que vive en ado_id (§4.8).
    assert proyecto_gitlab.llamadas == ["1124"]


# -- PATA B - el contador que se pierde (verde en F2) -------------------------

# v2 / C3 - CONGELADO. Los tres nombres estan VERIFICADOS POR AST el 2026-08-02, no
# asumidos: `_run_in_background` en los tres, y en cada archivo el nombre es UNICO
# (no hay dos funciones con ese nombre, asi que `_funcion_del_modulo` no puede
# devolver la equivocada):
#   agent_runner.py                     :: _run_in_background   lineas 718..1231
#   services/claude_code_cli_runner.py  :: _run_in_background   lineas 595..2179
#   services/codex_cli_runner.py        :: _run_in_background   lineas 258..1260
# NO "verifiques y corregi": ya esta verificado. Si alguna pata de presencia sale
# ROJA, es porque la sesion paralela renombro algo - parala y avisa, no la edites.
_SITIOS_DE_ENRIQUECIMIENTO = (
    ("agent_runner.py", "_run_in_background"),
    ("services/claude_code_cli_runner.py", "_run_in_background"),
    ("services/codex_cli_runner.py", "_run_in_background"),
)


def _funcion_del_modulo(ruta_rel: str, nombre: str):
    """Devuelve el nodo AST de la funcion, o None si no existe.

    Guarda anti-ambiguedad (v2): si hubiera DOS funciones con el mismo nombre en
    el archivo, devolver "la primera" haria que el censo mirase la equivocada.
    Se falla ruidosamente en vez de elegir.
    """
    arbol = ast.parse((ROOT / ruta_rel).read_text(encoding="utf-8"))
    encontradas = [
        n for n in ast.walk(arbol)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nombre
    ]
    assert len(encontradas) <= 1, (
        f"{ruta_rel} tiene {len(encontradas)} funciones llamadas {nombre!r}: el censo "
        f"miraria una arbitraria. Desambigua antes de seguir."
    )
    return encontradas[0] if encontradas else None


def _llama_a(nodo, nombre_funcion: str):
    """Devuelve el nodo ast.Call de la PRIMERA llamada `f(...)` o `mod.f(...)`, o None."""
    for hijo in ast.walk(nodo):
        if not isinstance(hijo, ast.Call):
            continue
        f = hijo.func
        if isinstance(f, ast.Name) and f.id == nombre_funcion:
            return hijo
        if isinstance(f, ast.Attribute) and f.attr == nombre_funcion:
            return hijo
    return None


def _nombre_del_stat_de_enrich(nodo) -> str | None:
    """Nombre local al que se desempaqueta el 2o valor de enrich_blocks(...).

    Busca `a, b = <algo>.enrich_blocks(...)` y devuelve el nombre de `b`.
    """
    for hijo in ast.walk(nodo):
        if not isinstance(hijo, ast.Assign) or not isinstance(hijo.value, ast.Call):
            continue
        f = hijo.value.func
        nombre = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
        if nombre != "enrich_blocks":
            continue
        destino = hijo.targets[0]
        if isinstance(destino, ast.Tuple) and len(destino.elts) == 2:
            segundo = destino.elts[1]
            if isinstance(segundo, ast.Name):
                return segundo.id
    return None


@pytest.mark.parametrize("ruta,funcion", _SITIOS_DE_ENRIQUECIMIENTO)
def test_pata_de_presencia_la_funcion_vigilada_existe(ruta, funcion):
    """Sin esta pata, borrar o renombrar la funcion dejaria el censo verde POR AUSENCIA."""
    assert _funcion_del_modulo(ruta, funcion) is not None, (
        f"{ruta}::{funcion} no existe. El censo de abajo quedaria verde por ausencia, "
        f"no por correccion. NO edites _SITIOS_DE_ENRIQUECIMIENTO sin leer el plan 289 F0."
    )


@pytest.mark.parametrize("ruta,funcion", _SITIOS_DE_ENRIQUECIMIENTO)
def test_pata_de_presencia_la_funcion_llama_al_pipeline(ruta, funcion):
    """La funcion vigilada es, de verdad, la que enriquece."""
    assert _llama_a(_funcion_del_modulo(ruta, funcion), "enrich_blocks") is not None


# -- v2 / C4 - el censo NO se conforma con "que la llamada exista" ------------
# Un censo por presencia de llamada se satisface con
#   persistir_stats_de_contexto(execution_id=None, stats=None)
# o con la llamada metida en una rama muerta: verde, y el contador se sigue
# perdiendo. Este censo exige ADEMAS que los dos kwargs esten y que `stats=`
# reciba EXACTAMENTE el nombre al que se desempaqueto el 2o valor de
# enrich_blocks. Eso es determinista, barato y no se puede fingir sin cablearlo
# de verdad. (Lo que sigue sin cubrir un censo estatico es que la funcion HAGA
# lo suyo: eso lo prueba tests/test_plan289_stat_de_contexto.py, ejecutandola.)

@pytest.mark.xfail(strict=True, reason="Plan 289 F2 lo pone verde: hoy 2 de 3 runtimes tiran el stat")
@pytest.mark.parametrize("ruta,funcion", _SITIOS_DE_ENRIQUECIMIENTO)
def test_los_3_runtimes_persisten_el_contador(ruta, funcion):
    nodo = _funcion_del_modulo(ruta, funcion)
    llamada = _llama_a(nodo, "persistir_stats_de_contexto")
    assert llamada is not None, (
        f"{ruta}::{funcion} llama a enrich_blocks pero no persiste el contador"
    )
    kwargs = {k.arg: k.value for k in llamada.keywords if k.arg}
    assert "execution_id" in kwargs and "stats" in kwargs, (
        f"{ruta}::{funcion} llama al helper sin execution_id= y/o sin stats=: {sorted(kwargs)}"
    )
    esperado = _nombre_del_stat_de_enrich(nodo)
    assert esperado is not None, (
        f"{ruta}::{funcion} ya no desempaqueta enrich_blocks en 2 nombres"
    )
    recibido = getattr(kwargs["stats"], "id", None)
    assert recibido == esperado, (
        f"{ruta}::{funcion} persiste `{recibido}` pero enrich_blocks devolvio `{esperado}`: "
        f"la llamada existe pero NO esta cableada al stat real"
    )
