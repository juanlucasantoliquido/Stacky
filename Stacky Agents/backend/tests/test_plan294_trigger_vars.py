"""tests/test_plan294_trigger_vars.py — Plan 294 F7.

El disparo puede llevar variables de ESA corrida, detras de una flag que nace
APAGADA (excepcion dura (B): inyecta valores en una corrida REAL del sistema del
operador y puede cambiar a que ambiente apunta). Sin la flag y sin el campo, el
comportamiento es byte-identico al de hoy.

NINGUN TEST DE ESTE ARCHIVO DISPARA UNA PIPELINE REAL: todos los proveedores son
dobles y el caso 12 prohibe la red monkeypatcheando socket.socket.
"""
from __future__ import annotations

import pathlib
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


@pytest.fixture
def app():
    from app import create_app

    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def _trigger_on(monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_TRIGGER_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_TRIGGER_ENV_GATE_ENABLED", False, raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_TRIGGER_VARS_ENABLED", False, raising=False)
    yield


def _vars_on(monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_TRIGGER_VARS_ENABLED", True, raising=False)


class _DobleProvider:
    """Doble del puerto CI. Guarda con que lo llamaron. NO habla con nadie."""

    name = "azure_devops"

    def __init__(self):
        self.recibido = {}

    def trigger_pipeline(self, item_ref, ref, variables=None):
        self.recibido = {"ref": ref, "variables": variables}
        return {"id": "1234", "status": "running", "ref": ref, "web_url": ""}


def _post(client, **extra):
    cuerpo = {"confirm": True, "ref": "main", "sha": "abc123"}
    cuerpo.update(extra)
    return client.post("/api/ci/RecoveryStrategy/trigger", json=cuerpo)


def _con_provider(prov):
    return (
        patch("api.ci.get_ci_provider", return_value=prov),
        patch("api.ci._read_pat_scopes", return_value=None),
    )


def _disparar(client, prov, **extra):
    a, b = _con_provider(prov)
    with a, b:
        return _post(client, **extra)


@pytest.fixture(autouse=True)
def _sin_idempotencia_pegada():
    """La ventana de 60 s es global al proceso: se limpia entre casos para que un
    caso no le robe el disparo al siguiente."""
    import api.ci as ci_mod

    ci_mod._RECENT_TRIGGERS.clear()
    yield
    ci_mod._RECENT_TRIGGERS.clear()


# ── 1..2 · el comportamiento de hoy no se mueve ──────────────────────────────

def test_r10_flag_apagada_y_sin_variables_es_lo_de_hoy(client):
    prov = _DobleProvider()
    r = _disparar(client, prov)
    assert r.status_code == 200, r.get_json()
    assert prov.recibido["variables"] is None


def test_r11_flag_apagada_con_variables_da_409(client):
    """409 y no 403: la ruta existe y la flag madre esta encendida. Es un
    conflicto de configuracion, no un permiso. En este producto no hay permisos."""
    prov = _DobleProvider()
    r = _disparar(client, prov, variables={"ENV": "qa"})
    assert r.status_code == 409
    body = r.get_json()
    assert body["kind"] == "trigger_vars_disabled"
    assert body["hint"].strip()


# ── 3..7 · la capacidad nueva, en los dos proveedores ────────────────────────

def test_flag_encendida_el_proveedor_recibe_las_variables(client, monkeypatch):
    _vars_on(monkeypatch)
    prov = _DobleProvider()
    r = _disparar(client, prov, variables={"ENV": "qa"})
    assert r.status_code == 200, r.get_json()
    assert prov.recibido["variables"] == {"ENV": "qa"}


def test_ado_arma_el_cuerpo_con_la_forma_de_su_api(monkeypatch):
    from services.ado_ci_provider import AdoCIProvider
    from services.ci_provider import ItemRef

    capturado = {}

    class _Cliente:
        _base_proj = "https://ado.example/org/proj"

        def _request(self, metodo, url, body=None):
            capturado["body"] = body
            return {"id": 7, "state": "inProgress", "_links": {"web": {"href": "u"}}}

    prov = AdoCIProvider("proj")
    with patch("services.ado_pipeline_definitions.find_yaml_definition",
               return_value={"id": 42}), \
         patch("services.ado_client.AdoClient", return_value=_Cliente()):
        prov.trigger_pipeline(ItemRef("1", "azure_devops", "main"), "main",
                              {"ENV": "qa"})

    assert capturado["body"]["variables"] == {"ENV": {"value": "qa", "isSecret": False}}


def test_gitlab_delega_con_la_forma_de_su_api():
    from services.ci_provider import ItemRef
    from services.gitlab_ci_provider import GitLabCIProvider

    capturado = {}

    class _Delegate:
        def trigger_pipeline(self, ref, variables=None):
            capturado["ref"] = ref
            capturado["variables"] = variables
            return {"id": 9, "status": "running"}

    prov = GitLabCIProvider.__new__(GitLabCIProvider)
    prov._delegate = _Delegate()
    prov.trigger_pipeline(ItemRef("1", "gitlab", "main"), "main", {"ENV": "qa"})

    assert capturado["variables"] == [{"key": "ENV", "value": "qa"}]


def test_paridad_el_mismo_cuerpo_dispara_en_los_dos(client, monkeypatch):
    _vars_on(monkeypatch)
    for nombre in ("azure_devops", "gitlab"):
        prov = _DobleProvider()
        prov.name = nombre
        r = _disparar(client, prov, variables={"ENV": "qa"})
        assert r.status_code == 200, (nombre, r.get_json())
        assert prov.recibido["variables"] == {"ENV": "qa"}, nombre


def test_degradacion_visible_si_el_delegate_viejo_no_acepta_variables():
    """Si el delegate no conoce el argumento, el disparo IGUAL ocurre y la
    respuesta lo declara. Degradacion VISIBLE, nunca silenciosa."""
    from services.ci_provider import ItemRef
    from services.gitlab_ci_provider import GitLabCIProvider

    class _DelegateViejo:
        def trigger_pipeline(self, ref):
            return {"id": 9, "status": "running"}

    prov = GitLabCIProvider.__new__(GitLabCIProvider)
    prov._delegate = _DelegateViejo()
    out = prov.trigger_pipeline(ItemRef("1", "gitlab", "main"), "main", {"ENV": "qa"})

    assert out["id"] == 9
    assert out["variables_applied"] is False


# ── 8..9 · validacion del cuerpo ─────────────────────────────────────────────

def test_veintiseis_claves_da_400(client, monkeypatch):
    _vars_on(monkeypatch)
    prov = _DobleProvider()
    r = _disparar(client, prov, variables={f"V{i}": "x" for i in range(26)})
    assert r.status_code == 400


def test_una_clave_con_guion_da_400(client, monkeypatch):
    _vars_on(monkeypatch)
    prov = _DobleProvider()
    r = _disparar(client, prov, variables={"MI-VAR": "x"})
    assert r.status_code == 400


# ── 10..11 · los rieles de siempre siguen intactos ───────────────────────────

def test_hitl_intacto_sin_confirm_es_400_con_y_sin_variables(client, monkeypatch):
    _vars_on(monkeypatch)
    prov = _DobleProvider()
    a, b = _con_provider(prov)
    with a, b:
        sin = client.post("/api/ci/RecoveryStrategy/trigger", json={"ref": "main"})
        con = client.post("/api/ci/RecoveryStrategy/trigger",
                          json={"ref": "main", "variables": {"ENV": "qa"}})
    assert sin.status_code == 400
    assert con.status_code == 400


def test_idempotencia_intacta(client, monkeypatch):
    _vars_on(monkeypatch)
    prov = _DobleProvider()
    primero = _disparar(client, prov, variables={"ENV": "qa"})
    segundo = _disparar(client, prov, variables={"ENV": "qa"})
    assert primero.status_code == 200
    assert segundo.get_json().get("status") == "reused"


# ── 12..13 · cero red y el orden del gate del plan 260 ───────────────────────

def test_cero_red_en_todo_el_archivo(monkeypatch, client):
    import socket

    class _Prohibido(socket.socket):
        def __init__(self, *a, **k):
            raise AssertionError("un test de este archivo intento abrir un socket")

    monkeypatch.setattr(socket, "socket", _Prohibido)
    prov = _DobleProvider()
    r = _disparar(client, prov)
    assert r.status_code == 200


def test_c16_el_orden_del_gate_del_plan_260_no_se_movio(client, monkeypatch):
    """Con la flag de variables ENCENDIDA y el gate del 260 BLOQUEANDO, el
    disparo no ocurre y la idempotencia no se consume. Es el invariante que
    test_plan260_trigger_gate.py espia en su propia corrida; aca se repite CON
    variables en el cuerpo, que es la combinacion nueva que ese test no cubre."""
    import api.ci as ci_mod
    import config as cfg

    _vars_on(monkeypatch)
    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_TRIGGER_ENV_GATE_ENABLED", True, raising=False)

    class _Readiness:
        verdict = "bloquea"
        pending_count = 1
        missing = (("SONAR_TOKEN", "prod"),)
        pending_fingerprint = "hhh"
        elapsed_ms = 1

    contador = {"n": 0}
    real = ci_mod.should_trigger

    def _espia(*a, **kw):
        contador["n"] += 1
        return real(*a, **kw)

    monkeypatch.setattr(ci_mod, "should_trigger", _espia)
    monkeypatch.setattr(ci_mod, "_evaluar_readiness", lambda *a, **k: _Readiness())

    prov = _DobleProvider()
    r = _disparar(client, prov, variables={"ENV": "qa"})

    assert r.status_code == 409
    assert r.get_json()["kind"] == "env_pending"
    assert contador["n"] == 0, "should_trigger no debe llamarse si el gate ya bloqueo"
    assert prov.recibido == {}, "no se disparo nada, como corresponde"
