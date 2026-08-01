"""tests/test_plan281_ruteo_por_tracker.py — Plan 281 F1..F6.

El camino completo que le pone al operador, cada 45 segundos, un error de Azure
DevOps en una pantalla de un proyecto GitLab.

Los cuatro casos de F1 nacen con `1 passed, 3 failed` A PROPÓSITO: el único verde
inicial es el GUARD del assert de ausencia (caso 2). Si al escribirlos salen los 4
en verde, los tests no están probando nada.

Aislamiento (reglas duras del plan):
  - `DATABASE_URL` a un SQLite de `tmp_path` ANTES de importar `db`/`create_app`:
    un pytest suelto sin eso escribe en la base VIVA del operador.
  - `STACKY_TEST_MODE=1` (lo pone `conftest.py`) ⇒ cero egress de red.
  - NUNCA se lee `backend/projects/RIPLEY/config.json` real: el config del
    proyecto se inyecta parcheando `get_project_config` en los DOS sitios donde
    se resuelve (por valor en `services.project_context`, por referencia dentro de
    `tracker_is_azure_devops`).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


_CFG_GITLAB = {
    "name": "RIPLEY",
    "issue_tracker": {
        "type": "gitlab",
        "base_url": "https://ejemplo.local",
        "project": "g/p",
    },
}
_CFG_ADO = {
    "name": "PACIFICO",
    "issue_tracker": {"type": "azure_devops", "project": "Strategist_Pacifico"},
}

_CARTEL = "no usa Azure DevOps"


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def bd_aislada(tmp_path, monkeypatch):
    """SQLite temporal. Va ANTES de cualquier import de `db`/`app`."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'plan281.db').as_posix()}")
    monkeypatch.setenv("STACKY_SKIP_STARTUP_SYNC", "1")
    yield


@pytest.fixture()
def app(bd_aislada):
    from app import create_app

    aplicacion = create_app()
    aplicacion.config.update(TESTING=True)
    return aplicacion


@pytest.fixture()
def client(app):
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def sin_rate_limit():
    """`sync-v2` tiene rate-limit y guard de concurrencia POR PROYECTO con estado a
    nivel de módulo: sin limpiarlo el segundo test del archivo recibe un 429."""
    try:
        import api.tickets as t
    except Exception:  # noqa: BLE001 — todavía no importado
        yield
        return
    t._last_sync_ts_by_project.clear()
    t._sync_in_progress_by_project.clear()
    yield
    t._last_sync_ts_by_project.clear()
    t._sync_in_progress_by_project.clear()


def _proyecto_gitlab(monkeypatch, nombre="RIPLEY"):
    """Todo resolvedor de config ve un proyecto GitLab. Cero disco real."""
    import project_manager
    import services.project_context as pc

    def _cfg(name=None):
        return dict(_CFG_GITLAB) if (name or "").strip().upper() == nombre else None

    monkeypatch.setattr(pc, "get_project_config", _cfg, raising=False)
    monkeypatch.setattr(project_manager, "get_project_config", _cfg, raising=False)
    monkeypatch.setattr(pc, "get_active_project", lambda: nombre, raising=False)
    monkeypatch.setattr(pc, "get_instance_info", lambda _n: None, raising=False)
    monkeypatch.setattr(pc, "find_project_for_tracker", lambda _n: (None, None), raising=False)


# ── F1 · Casos 1 y 2 — el body sin Content-Type ──────────────────────────────
#
# Van juntos y en este orden a propósito: el caso 2 garantiza, en el MISMO
# archivo, que el mecanismo sí detecta la condición cuando está presente. Sin él,
# el caso 1 podría "pasar" por un fixture que ni siquiera ejecuta el camino.


def test_request_project_name_lee_el_body_sin_content_type(app):
    """C6 — el assert es el comportamiento DESEADO, no el defecto.

    Con `fetch` y un body string sin `Content-Type`, el navegador manda
    `text/plain;charset=UTF-8`; Flask `get_json(silent=True)` devuelve None y el
    nombre del proyecto que el frontend SÍ serializó nunca llega.
    """
    from api.tickets import _request_project_name

    with app.test_request_context(
        "/api/tickets/sync-v2",
        method="POST",
        data=json.dumps({"project": "RIPLEY"}),
    ):
        assert _request_project_name() == "RIPLEY"


def test_request_project_name_lee_el_body_con_content_type(app):
    """GUARD del assert de ausencia: con el header correcto ya funciona hoy."""
    from api.tickets import _request_project_name

    with app.test_request_context(
        "/api/tickets/sync-v2",
        method="POST",
        data=json.dumps({"project": "RIPLEY"}),
        content_type="application/json",
    ):
        assert _request_project_name() == "RIPLEY"


# ── F1 · Casos 3 y 4 — el fallo cerrado que convierte "no sé" en "es ADO" ────


def test_sync_v2_de_proyecto_gitlab_no_menciona_azure_devops(client, monkeypatch):
    """§4.4 — con el contexto irresoluble, `tipo` cae por el `or` a "azure_devops",
    el branch no-ADO no ejecuta y se termina construyendo un cliente ADO para un
    proyecto GitLab.

    El guard contra el falso verde está en los asserts de forma: la respuesta
    tiene que seguir siendo `400 {"error": "config"}` — o sea, el camino CORRIÓ y
    produjo el mismo envelope. Lo único que cambia es que el mensaje deja de
    nombrar al proveedor equivocado.
    """
    import api.tickets as t

    _proyecto_gitlab(monkeypatch)
    # El contexto NO se resuelve en `_sync_via_provider_or_ado` (el `resolve_` de
    # api/tickets.py), pero `build_ado_client` sí resuelve por proyecto activo.
    monkeypatch.setattr(t, "resolve_project_context", lambda *a, **k: None)
    monkeypatch.setattr(t, "_provider_for_ticket", lambda *a, **k: None)

    r = client.post("/api/tickets/sync-v2", json={})
    cuerpo = r.get_data(as_text=True)

    assert r.status_code == 400, cuerpo
    assert r.get_json().get("error") == "config", cuerpo
    assert _CARTEL not in cuerpo, cuerpo


def test_sync_via_provider_no_asume_ado_con_contexto_nulo(app, monkeypatch):
    """"No pude resolver el contexto" NO es "es Azure DevOps"."""
    import api.tickets as t

    _proyecto_gitlab(monkeypatch)
    monkeypatch.setattr(t, "resolve_project_context", lambda *a, **k: None)
    monkeypatch.setattr(t, "_provider_for_ticket", lambda *a, **k: None)

    llamadas: list = []

    def _spy(*a, **k):
        llamadas.append((a, k))
        raise AssertionError("no debería construirse un cliente ADO")

    monkeypatch.setattr(t, "_ado_client_for_ticket", _spy)

    from services.tracker_provider import TrackerConfigError

    with app.app_context():
        with pytest.raises(TrackerConfigError):
            t._sync_via_provider_or_ado(project_name=None)

    assert llamadas == [], "se construyó un cliente ADO con el contexto irresoluble"


# ── F3 · El mensaje nombra el problema real, no el proveedor equivocado ──────


def test_contexto_irresoluble_no_nombra_azure_devops(app, monkeypatch):
    """El operador tiene que leer QUÉ le pasa, no el nombre de un tracker que no usa."""
    import api.tickets as t
    from services.tracker_provider import TrackerConfigError

    _proyecto_gitlab(monkeypatch)
    monkeypatch.setattr(t, "resolve_project_context", lambda *a, **k: None)
    monkeypatch.setattr(t, "_provider_for_ticket", lambda *a, **k: None)

    with app.app_context():
        with pytest.raises(TrackerConfigError) as info:
            t._sync_via_provider_or_ado(project_name="RIPLEY")

    mensaje = str(info.value)
    assert "azure devops" not in mensaje.lower(), mensaje
    assert "no se pudo resolver" in mensaje.lower(), mensaje


# ── F4 · El sync de arranque deja de ser ADO-only ────────────────────────────
#
# `create_app()` fuera de pytest tiene efectos REALES: estos casos importan
# `_startup_sync` y lo invocan con las dependencias mockeadas; nunca llaman a
# `create_app()`.


@pytest.fixture()
def arranque(bd_aislada, tmp_path, monkeypatch):
    """`_startup_sync` con TODAS sus dependencias de disco/red neutralizadas."""
    import app as app_module
    import services.gitlab_sync as gitlab_sync
    import services.project_context as pc
    import services.tracker_provider as tp
    from services import integration_breaker as brk

    monkeypatch.setattr(brk, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(app_module, "get_active_project", lambda: "RIPLEY")
    monkeypatch.setattr(app_module, "purge_non_project_tickets", lambda keep_project: 0)
    monkeypatch.setattr(pc, "get_active_project", lambda: None, raising=False)

    espias: dict = {"ado": [], "gitlab": [], "ado_sync": []}

    def _build_ado(*a, **k):
        espias["ado"].append((a, k))
        return object()

    def _sync_gitlab(*a, **k):
        espias["gitlab"].append((a, k))
        return {"fetched": 3, "created": 1, "updated": 0, "removed": 0}

    def _ado_sync(client=None):
        espias["ado_sync"].append(client)
        return {"project": "RIPLEY", "fetched": 0, "created": 0, "updated": 0, "removed": 0}

    monkeypatch.setattr(pc, "build_ado_client", _build_ado)
    monkeypatch.setattr(gitlab_sync, "sync_gitlab_tickets", _sync_gitlab)
    monkeypatch.setattr(app_module, "_ado_sync", _ado_sync)
    monkeypatch.setattr(
        tp, "get_tracker_provider",
        lambda *a, **k: type("P", (), {"name": "gitlab"})(),
    )
    return app_module, pc, espias


def _tracker_es_ado(pc, monkeypatch, valor: bool, app_module):
    monkeypatch.setattr(pc, "tracker_is_azure_devops", lambda _n: valor)
    tipo = "azure_devops" if valor else "gitlab"
    monkeypatch.setattr(
        app_module, "get_project_config",
        lambda name: {"name": "RIPLEY", "issue_tracker": {"type": tipo, "project": "g/p"}},
    )


def test_startup_sync_gitlab_no_construye_cliente_ado(arranque, monkeypatch):
    import logging

    app_module, pc, espias = arranque
    _tracker_es_ado(pc, monkeypatch, False, app_module)

    app_module._startup_sync(logging.getLogger("test.plan281.f4"))

    assert espias["ado"] == [], "se construyó un cliente ADO para un proyecto GitLab"
    assert espias["ado_sync"] == []


def test_startup_sync_gitlab_invoca_sync_gitlab_tickets(arranque, monkeypatch):
    import logging

    app_module, pc, espias = arranque
    _tracker_es_ado(pc, monkeypatch, False, app_module)

    app_module._startup_sync(logging.getLogger("test.plan281.f4"))

    assert len(espias["gitlab"]) == 1, espias["gitlab"]
    assert espias["gitlab"][0][0][0] == "RIPLEY"


def test_startup_sync_ado_sigue_igual(arranque, monkeypatch):
    """NO-REGRESIÓN: sin este caso, un `return` mal puesto rompería también ADO."""
    import logging

    app_module, pc, espias = arranque
    _tracker_es_ado(pc, monkeypatch, True, app_module)

    app_module._startup_sync(logging.getLogger("test.plan281.f4"))

    assert len(espias["ado"]) == 1, espias["ado"]
    assert espias["gitlab"] == []


# ── F5 · El dispatch de `completion_sync` deja de romperse en GitLab ─────────


@pytest.fixture()
def completion(tmp_path, monkeypatch):
    """`_do_project_sync` con breaker aislado y sin red."""
    import services.completion_sync as cs
    from services import integration_breaker as brk

    monkeypatch.setattr(brk, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(cs, "_log_sync", lambda *a, **k: None)
    monkeypatch.setattr(cs, "_tracker_config_for", lambda p: {"project": p})

    fallos: list = []
    monkeypatch.setattr(brk, "record_failure", lambda *a, **k: fallos.append(a))
    monkeypatch.setattr(brk, "should_skip", lambda *a, **k: False)
    return cs, fallos


def test_completion_sync_gitlab_llama_sync_gitlab_tickets(completion, monkeypatch):
    cs, _fallos = completion
    import services.gitlab_sync as gs

    llamadas: list = []
    monkeypatch.setattr(
        gs, "sync_gitlab_tickets",
        lambda *a, **k: llamadas.append((a, k)) or {"fetched": 1},
    )

    cs._do_project_sync("RIPLEY", "gitlab")

    assert len(llamadas) == 1, llamadas
    assert llamadas[0][0] == ("RIPLEY",), "el project va POSICIONAL"


def test_completion_sync_gitlab_no_levanta_attribute_error(completion, monkeypatch):
    """El defecto viejo: AttributeError tragado ⇒ el breaker registraba un fallo
    y el sync no corría nunca, en silencio."""
    cs, fallos = completion
    import services.gitlab_sync as gs

    monkeypatch.setattr(gs, "sync_gitlab_tickets", lambda *a, **k: {"fetched": 0})

    cs._do_project_sync("RIPLEY", "gitlab")

    assert fallos == [], f"se registró un fallo en el breaker: {fallos}"
    # `_breaker_target` ya ruteaba bien: la key NO puede quedar compartida con ADO.
    assert cs._breaker_target("RIPLEY", "gitlab") == ("gitlab_sync", "RIPLEY")


def test_completion_sync_jira_sigue_igual(completion, monkeypatch):
    """NO-REGRESIÓN: Jira sigue entrando por `tracker_config=` (kwarg)."""
    cs, fallos = completion
    import services.jira_sync as js

    llamadas: list = []
    monkeypatch.setattr(
        js, "sync_tickets",
        lambda *a, **k: llamadas.append((a, k)) or {"fetched": 2},
    )

    cs._do_project_sync("PACIFICO", "jira")

    assert len(llamadas) == 1, llamadas
    assert "tracker_config" in llamadas[0][1], llamadas[0]
    assert fallos == []


# ── F6 · `run_ticket_refresh` deja de leer la columna que miente ─────────────


@pytest.fixture()
def refresh(tmp_path, monkeypatch):
    """`refresh_ticket_snapshot` con BD SQLite propia y la flag que lo gatea FORZADA.

    C12 — `STACKY_RUN_TICKET_REFRESH_ENABLED` se lee con `getattr(config, ..., False)`;
    su default efectivo es "true", pero el fixture lo fuerza para no depender del
    `.env` de la máquina: si no, el test pasaría por la razón equivocada.
    """
    from contextlib import contextmanager

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'p281refresh.db').as_posix()}")

    import config as config_module
    import models
    import services.run_ticket_refresh as rtr
    from db import Base

    monkeypatch.setattr(config_module.config, "STACKY_RUN_TICKET_REFRESH_ENABLED", True)

    motor = create_engine(f"sqlite:///{(tmp_path / 'p281refresh.db').as_posix()}", future=True)
    Sesion = sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(motor)
    assert tmp_path.name in str(motor.url), f"la BD del test NO está aislada: {motor.url}"

    @contextmanager
    def _scope():
        s = Sesion()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    # `run_ticket_refresh` importó `session_scope` POR VALOR: hay que re-apuntarlo
    # acá o el test escribiría en la BD REAL del operador.
    monkeypatch.setattr(rtr, "session_scope", _scope)

    def _alta(**kw):
        with _scope() as s:
            t = models.Ticket(**kw)
            s.add(t)
            s.flush()
            return t.id

    return rtr, _alta


def test_refresh_no_confia_en_la_columna_mentirosa(refresh, monkeypatch):
    """La fila MIENTE (`tracker_type='azure_devops'`) pero el proyecto es GitLab."""
    rtr, alta = refresh
    import services.project_context as pc

    tid = alta(
        ado_id=1115, external_id=1115, title="epica gitlab", project="g/p",
        stacky_project_name="RIPLEY", tracker_type="azure_devops",
    )
    monkeypatch.setattr(pc, "tracker_is_azure_devops", lambda _n: False)

    construidos: list = []
    monkeypatch.setattr(
        pc, "build_ado_client",
        lambda **k: construidos.append(k) or object(),
    )

    r = rtr.refresh_ticket_snapshot(tid)

    assert r == {"refreshed": False, "reason": "non_ado_tracker"}, r
    assert construidos == [], "se construyó un cliente ADO para un proyecto GitLab"


def test_refresh_ado_sigue_refrescando(refresh, monkeypatch):
    """NO-REGRESIÓN: un proyecto ADO real sigue refrescando."""
    rtr, alta = refresh
    import services.ado_read_cache as arc
    import services.project_context as pc

    tid = alta(
        ado_id=4242, external_id=4242, title="wi ado", project="Strategist_Pacifico",
        stacky_project_name="PACIFICO", tracker_type="azure_devops",
    )
    monkeypatch.setattr(pc, "tracker_is_azure_devops", lambda _n: True)

    construidos: list = []
    monkeypatch.setattr(
        pc, "build_ado_client",
        lambda **k: construidos.append(k) or object(),
    )
    monkeypatch.setattr(arc, "get_or_fetch", lambda *a, **k: {"id": 4242})

    r = rtr.refresh_ticket_snapshot(tid)

    assert r == {"refreshed": True, "reason": "ok"}, r
    assert len(construidos) == 1, construidos
