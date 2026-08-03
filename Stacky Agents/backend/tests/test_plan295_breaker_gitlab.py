"""Plan 295 F7 + F8 — GitLab tiene su propio circuit breaker, y el de ADO se
consulta DESPUÉS de saber qué tracker es.

F7. Hoy un GitLab con PAT vencido se golpea en cada sync, cada 45 segundos,
indefinidamente: ADO y Jira tienen backoff exponencial (15 min -> tope 6 h,
integration_breaker.py:22-23) y GitLab tiene CERO referencias de breaker en
producción (medido). La key es `"gitlab_sync"` y su parte `project` es el
`stacky_project_name`, NUNCA `ado_breaker_project`: en GitLab el token, la URL y
el ca_bundle son POR PROYECTO, y mezclar las keys es exactamente el bug que el
plan 281 documentó en app.py:204-208.

F8. `should_skip("ado_sync", ...)` vivía ARRIBA de `resolve_project_context`, así
que un proyecto GITLAB podía recibir `{"error":"ado_degraded"}` por el breaker de
Azure DevOps de OTRO proyecto. El 281 F4 arregló ese mismo defecto en el arranque y
dejó `sync-v2` en su propia lista de diferidos. Esta fase paga ese diferido.

AISLAMIENTO OBLIGATORIO: el breaker escribe `integration_breaker.json` en
`data_dir()`. Sin `STACKY_DATA_DIR` en tmp_path el test contamina el estado de
degradación REAL del operador.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_PROYECTO = "ProyDePrueba"
# Key ADO FIJA. `ado_breaker_project()` resuelve el contexto REAL del disco
# (integration_breaker.py:40-53) y devolvería el proyecto del operador: la key que
# abre el test no coincidiría con la que consulta el endpoint, `should_skip` daría
# siempre False y los casos 11 y 12 pasarían EN FALSO -- justo los dos que tienen
# que discriminar el bug de F8.
_ADO_KEY = "KEY-ADO-DE-PRUEBA"


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    """Base y data_dir frescos. Devuelve el módulo del breaker ya aislado."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'plan295.db'}")
    monkeypatch.setenv("STACKY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("STACKY_SYNC_MIN_INTERVAL_SEC", "0")

    import runtime_paths

    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path, raising=False)
    from services import integration_breaker as brk

    monkeypatch.setattr(brk, "data_dir", lambda: tmp_path, raising=False)
    monkeypatch.setattr(brk, "ado_breaker_project", lambda _pn=None: _ADO_KEY)
    return brk


@pytest.fixture
def cliente(entorno, monkeypatch):
    import api.tickets as tickets_api

    tickets_api._last_sync_ts_by_project.clear()
    tickets_api._sync_in_progress_by_project.clear()

    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _lanzar(monkeypatch, exc):
    import api.tickets as tickets_api

    def _boom(*a, **kw):
        raise exc

    monkeypatch.setattr(tickets_api, "_sync_via_provider_or_ado", _boom)


def _ok(monkeypatch):
    import api.tickets as tickets_api

    def _bien(*a, **kw):
        return {"fetched": 0, "created": 0, "updated": 0, "removed": 0,
                "stacky_project_name": _PROYECTO}

    monkeypatch.setattr(tickets_api, "_sync_via_provider_or_ado", _bien)


def _api_error(status, kind):
    from services.tracker_provider import TrackerApiError

    return TrackerApiError(status, f"HTTP {status}", kind=kind)


def _ctx_de(monkeypatch, tracker_type: str):
    """Fuerza el tracker del contexto SIN tocar services/project_context.py (que la
    sesión paralela está editando): se parchea el símbolo YA IMPORTADO en
    api.tickets, que es el que el endpoint llama."""
    import api.tickets as tickets_api

    class _Ctx:
        stacky_project_name = _PROYECTO
        tracker_project = "grupo/proy"
        organization = "org"
        auth_path = None

    _Ctx.tracker_type = tracker_type
    monkeypatch.setattr(tickets_api, "resolve_project_context", lambda **kw: _Ctx())
    return _Ctx


# ------------------------------------------------------------- F7 (1-9) -----
def test_1_auth_clasifica_como_token_invalido(entorno):
    r = entorno.classify_gitlab_error("auth", "HTTP 401")
    assert r is not None and r[0] == "gitlab_token_invalid"


def test_2_not_found_clasifica_como_proyecto_inexistente(entorno):
    r = entorno.classify_gitlab_error("not_found", "HTTP 404")
    assert r is not None and r[0] == "gitlab_project_not_found"


def test_3_los_cuatro_kinds_transitorios_no_abren(entorno):
    """rate_limited/server/network/tls son TRANSITORIOS o de entorno: abrir por
    ellos dejaría GitLab apagado hasta 6 h por un blip de red."""
    assert all(
        entorno.classify_gitlab_error(k, "x") is None
        for k in ("rate_limited", "server", "network", "tls")
    )


def test_4_un_kind_desconocido_no_abre(entorno):
    """Fail-safe: un kind nuevo de un plan futuro NO apaga la integración."""
    assert entorno.classify_gitlab_error("marciano", "x") is None


def test_5_pat_vencido_abre_gitlab_sync(cliente, entorno, monkeypatch):
    _ctx_de(monkeypatch, "gitlab")
    _lanzar(monkeypatch, _api_error(401, "auth"))
    assert cliente.post("/api/tickets/sync-v2").status_code == 502
    assert entorno.get_state("gitlab_sync", _PROYECTO).open is True


def test_6_y_NO_toca_el_breaker_de_ado(cliente, entorno, monkeypatch):
    """EL CORAZÓN DE LA FASE. Sin este assert el test pasaría con un breaker que
    abre la key equivocada, que es literalmente el bug que el 281 arregló."""
    _ctx_de(monkeypatch, "gitlab")
    _lanzar(monkeypatch, _api_error(401, "auth"))
    cliente.post("/api/tickets/sync-v2")
    assert entorno.get_state("ado_sync", _ADO_KEY).open is False
    assert entorno.get_state("ado_sync", _PROYECTO).open is False


def test_7_rate_limited_no_abre_nada(cliente, entorno, monkeypatch):
    _ctx_de(monkeypatch, "gitlab")
    _lanzar(monkeypatch, _api_error(429, "rate_limited"))
    assert cliente.post("/api/tickets/sync-v2").status_code == 502
    assert entorno.get_state("gitlab_sync", _PROYECTO).open is False


def test_8_un_sync_exitoso_cierra_el_breaker_abierto(cliente, entorno, monkeypatch):
    """Sin esto el breaker queda abierto PARA SIEMPRE y el operador tiene que
    reiniciar el backend.

    Se simula que la ventana de backoff YA VENCIÓ (`should_skip` False, que es lo
    que hace `integration_breaker` cuando pasan los 15 min): el breaker sigue
    ABIERTO en disco pero el sync se deja correr. Es el único momento en que el
    camino de éxito puede cerrarlo, y es exactamente el que hay que probar."""
    _ctx_de(monkeypatch, "gitlab")
    entorno.record_failure("gitlab_sync", _PROYECTO, "gitlab_token_invalid", "token vencido")
    assert entorno.get_state("gitlab_sync", _PROYECTO).open is True, "precondición"
    monkeypatch.setattr(entorno, "should_skip", lambda *a, **kw: False)
    _ok(monkeypatch)

    resp = cliente.post("/api/tickets/sync-v2")

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert entorno.get_state("gitlab_sync", _PROYECTO).open is False, (
        "el sync salió bien y el breaker quedó abierto: nadie llama a record_success"
    )


def test_9_las_dos_reason_nuevas_no_colisionan_con_las_seis(entorno):
    nombres = {
        v for k, v in vars(entorno).items()
        if k.startswith("REASON_") and isinstance(v, str)
    }
    assert len(nombres) == 8, sorted(nombres)


# ------------------------------------------------------------ F8 (11-15) ----
def test_11_proyecto_gitlab_NO_recibe_ado_degraded(cliente, entorno, monkeypatch):
    """EL BUG DE HOY: el breaker de Azure DevOps de otro proyecto apagaba el sync
    de un proyecto GitLab, y el operador leía "Azure DevOps degradado" en un
    proyecto que no usa Azure DevOps."""
    _ctx_de(monkeypatch, "gitlab")
    entorno.record_failure("ado_sync", _ADO_KEY, "ado_pat_expired", "PAT vencido")
    _ok(monkeypatch)
    data = cliente.post("/api/tickets/sync-v2").get_json()
    assert data.get("error") != "ado_degraded", data


def test_12_proyecto_ADO_con_su_breaker_abierto_sigue_degradando(cliente, entorno, monkeypatch):
    """NO-REGRESIÓN: pasa ANTES y DESPUÉS. Es la prueba de que el camino ADO no se
    movió, sólo se evalúa unas líneas más abajo."""
    _ctx_de(monkeypatch, "azure_devops")
    entorno.record_failure("ado_sync", _ADO_KEY, "ado_pat_expired", "PAT vencido")
    _ok(monkeypatch)
    resp = cliente.post("/api/tickets/sync-v2")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["error"] == "ado_degraded", data


def test_13_proyecto_gitlab_con_SU_breaker_abierto_da_gitlab_degraded(cliente, entorno, monkeypatch):
    _ctx_de(monkeypatch, "gitlab")
    entorno.record_failure("gitlab_sync", _PROYECTO, "gitlab_token_invalid", "token vencido")
    _ok(monkeypatch)
    resp = cliente.post("/api/tickets/sync-v2")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["error"] == "gitlab_degraded", data


def test_14_el_mensaje_viene_del_breaker_no_hardcodeado(cliente, entorno, monkeypatch):
    _ctx_de(monkeypatch, "gitlab")
    entorno.record_failure("gitlab_sync", _PROYECTO, "gitlab_token_invalid", "token vencido")
    st = entorno.get_state("gitlab_sync", _PROYECTO)
    _ok(monkeypatch)
    data = cliente.post("/api/tickets/sync-v2").get_json()
    assert data["message"] == st.message


def test_15_con_la_flag_OFF_el_gemelo_de_gitlab_no_dispara(cliente, entorno, monkeypatch):
    import config as _config

    _ctx_de(monkeypatch, "gitlab")
    monkeypatch.setattr(
        _config.config, "STACKY_GITLAB_SYNC_ERRORS_ROUTED_ENABLED", False, raising=False
    )
    entorno.record_failure("gitlab_sync", _PROYECTO, "gitlab_token_invalid", "token vencido")
    _ok(monkeypatch)
    data = cliente.post("/api/tickets/sync-v2").get_json()
    assert data.get("error") != "gitlab_degraded", data
