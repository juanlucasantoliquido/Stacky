"""tests/test_plan292_paridad_runtimes.py — Plan 292 F6.

La paridad de los tres runtimes sale GRATIS porque el sync vive fuera de ellos, y
eso NO se afirma: se prueba. Mas los cuatro disparadores, ejercitados EJECUTANDO.

POR QUE LOS CASOS 3..6 EJECUTAN Y NO GREPEAN: un test estatico sobre un defecto de
EJECUCION es uno de los moldes clasicos de gate muerto. Que la linea
`forzar_full=True` este escrita en app.py no prueba que llegue — podria estar en
una rama muerta. Los cuatro llaman a la funcion real con un espia y miran el
kwarg RECIBIDO.
"""
import ast
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_BACKEND = Path(__file__).resolve().parents[1]
_SIMBOLO = "sync_gitlab_tickets"
_ESPERADOS = {"app.py", "api/tickets.py", "services/completion_sync.py"}
_EXCLUIDOS = {"tests", ".venv", "venv", "node_modules", "__pycache__", "build", "dist"}


def _fuentes():
    for ruta in _BACKEND.rglob("*.py"):
        rel = ruta.relative_to(_BACKEND)
        if any(parte in _EXCLUIDOS for parte in rel.parts):
            continue
        yield rel, ruta


def test_los_tres_disparadores_llaman_al_mismo_sync():
    """Censo por AST, no por grep.

    Un censo por grep da SEIS archivos y falla el dia uno: fuera de tests/ el
    simbolo aparece tambien en tres comentarios, en la propia `def`, en el
    `__all__` y en una cadena de capacidad ("services/gitlab_sync.py:
    sync_gitlab_tickets"). Solo el nodo `ast.Call` distingue una LLAMADA de todo
    eso.

    Y el AST tiene su propia trampa: cuenta CERO si la llamada va por alias. Por
    eso se aceptan las dos formas (`sync_gitlab_tickets(...)` y
    `gs.sync_gitlab_tickets(...)`) y se asserta que el censo reproduce los tres
    archivos POR NOMBRE — un conteo de 3 que cayera en tres archivos equivocados
    pasaria igual.
    """
    llamadas: list[str] = []
    for rel, ruta in _fuentes():
        try:
            arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Call):
                continue
            f = nodo.func
            nombre = (
                f.id if isinstance(f, ast.Name)
                else f.attr if isinstance(f, ast.Attribute)
                else None
            )
            if nombre == _SIMBOLO:
                llamadas.append(rel.as_posix())

    assert set(llamadas) == _ESPERADOS, f"los llamadores cambiaron: {sorted(set(llamadas))}"
    assert len(llamadas) == 3, f"se esperaban 3 llamadas, hay {len(llamadas)}: {llamadas}"


def test_ningun_runner_conoce_el_sync_de_gitlab():
    """EL GATE DE PARIDAD. Si un runner empezara a hablar de GitLab, la paridad
    dejaria de ser gratis y este test lo diria. Es un invariante PREEXISTENTE que
    este plan conserva: su mitad de contraste es agregar una linea `# gitlab` a
    cualquiera de los tres y verlo ponerse rojo."""
    runners = (
        _BACKEND / "services" / "codex_cli_runner.py",
        _BACKEND / "services" / "claude_code_cli_runner.py",
        _BACKEND / "copilot_bridge.py",
    )
    for ruta in runners:
        assert ruta.exists(), f"no existe el runner {ruta}"
        texto = ruta.read_text(encoding="utf-8", errors="replace").lower()
        for token in ("gitlab", "sync_gitlab_tickets", "completion_sync"):
            assert token not in texto, f"{ruta.name} menciona '{token}'"


# ───────────────── los cuatro disparadores, EJECUTANDO ─────────────────


class _ProvFalso:
    name = "gitlab"

    def fetch_open_items(self, query):
        return []


@pytest.fixture()
def espia(monkeypatch):
    """Reemplaza `sync_gitlab_tickets` por un espia que anota sus kwargs."""
    import services.gitlab_sync as gs

    recibido = {}

    def _falso(project_name, *, provider=None, forzar_full=False, **resto):
        recibido["project_name"] = project_name
        recibido["forzar_full"] = forzar_full
        return {"fetched": 0, "created": 0, "updated": 0, "removed": 0,
                "stacky_project_name": project_name}

    monkeypatch.setattr(gs, _SIMBOLO, _falso)
    return recibido


def test_el_arranque_fuerza_completo(espia, monkeypatch):
    """El arranque ocurre una vez por proceso, no es polling, y el proceso pudo
    estar apagado dias: es el momento donde mas conviene una foto completa."""
    import logging

    import app as app_mod
    import services.project_context as pc
    import services.tracker_provider as tp

    monkeypatch.setattr(app_mod, "get_active_project", lambda: "RIPLEY")
    monkeypatch.setattr(
        app_mod, "get_project_config", lambda _p: {"issue_tracker": {"type": "gitlab"}}
    )
    monkeypatch.setattr(pc, "tracker_is_azure_devops", lambda _p: False)
    monkeypatch.setattr(tp, "get_tracker_provider", lambda _p: _ProvFalso())

    app_mod._startup_sync(logging.getLogger("test-plan292"))

    assert espia.get("project_name") == "RIPLEY"
    assert espia["forzar_full"] is True, "el arranque NO forzo una corrida completa"


@pytest.fixture()
def espia_via(monkeypatch):
    """Espia sobre `_sync_via_provider_or_ado`, que es donde los dos endpoints
    deciden el modo. Anota el kwarg RECIBIDO, no el escrito."""
    import api.tickets as t

    recibido = {}

    def _falso(project_name=None, **kwargs):
        recibido["forzar_full"] = kwargs.get("forzar_full")
        return {"fetched": 0, "created": 0, "updated": 0, "removed": 0,
                "stacky_project_name": project_name or "RIPLEY"}

    monkeypatch.setattr(t, "_sync_via_provider_or_ado", _falso)
    return recibido


def _contexto_http(metodo="POST"):
    from flask import Flask

    return Flask(__name__).test_request_context(
        "/", method=metodo, json={"project": "RIPLEY"}
    )


def test_el_pedido_manual_fuerza_completo(espia_via, monkeypatch):
    """El operador pidiendo sync a mano ya es la forma de forzar una completa: no
    hace falta agregar ni un control nuevo a la interfaz."""
    import api.tickets as t

    with _contexto_http():
        t.sync_from_ado()

    assert espia_via["forzar_full"] is True, "el pedido manual NO forzo una completa"


def test_el_poll_automatico_no_fuerza_completo(espia_via, monkeypatch):
    """El poll del tablero es JUSTO el que tiene que ir parcial: es el que corre
    cada 45 s y el unico lugar donde el ahorro existe."""
    import api.tickets as t
    import services.integration_breaker as brk

    monkeypatch.setattr(brk, "should_skip", lambda *a, **k: False)
    monkeypatch.setattr(
        t, "resolve_project_context",
        lambda **k: SimpleNamespace(stacky_project_name="RIPLEY", tracker_type="gitlab"),
    )
    t._last_sync_ts_by_project.clear()
    t._sync_in_progress_by_project.clear()

    with _contexto_http():
        t.sync_from_ado_v2()

    assert espia_via.get("forzar_full") in (None, False), (
        "el poll automatico forzo una completa y mata todo el ahorro del plan"
    )


def test_la_completacion_no_fuerza_completo(espia, monkeypatch):
    """Sync reactivo y frecuente: exactamente el caso del modo parcial."""
    import services.completion_sync as cs
    import services.integration_breaker as brk

    monkeypatch.setattr(brk, "should_skip", lambda *a, **k: False)

    cs._do_project_sync("RIPLEY", "gitlab")

    assert espia.get("project_name") == "RIPLEY"
    assert espia.get("forzar_full") in (None, False), (
        "el sync post-completacion forzo una completa"
    )
