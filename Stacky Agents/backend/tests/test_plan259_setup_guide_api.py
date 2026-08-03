"""Plan 259 F4 — Endpoints de la guia + los 6 chequeos en vivo.

CERO RED REAL: se monkeypatchea el simbolo `requests` DENTRO de
services.gitlab_setup_check (guard de red del plan 154).

Plan 295 F5 — eran CINCO chequeos y ahora son SEIS: se agrego `chk-tls`, que
distingue "el certificado no cerro" de "no se pudo llegar a esa direccion". El
doble de `requests` tuvo que crecer en consecuencia (ver FakeRequests): el modulo
bajo prueba ahora usa `requests.Session()` para poder montar el adaptador OpenSSL
del plan 276 en el prefijo del host, y `requests.exceptions.SSLError` para
distinguir el fallo de certificado del fallo de red.
"""
from __future__ import annotations

import json

import pytest

_TOKEN = "glpat-" + "SECRETO0DEPRUEBA"
_CHECK_IDS = [
    "chk-flag", "chk-tls", "chk-instancia", "chk-token", "chk-scope", "chk-proyecto",
]


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeRequests:
    """Doble de `requests` para services.gitlab_setup_check.

    RequestException es OBLIGATORIO: el modulo bajo prueba lo usa en su `except`,
    y tras el monkeypatch se resuelve contra ESTA clase, no contra el paquete
    real (Plan 259 v3, hallazgo B4). Sin este atributo los 4 escenarios de red
    mueren con AttributeError en vez de devolver `unknown`.
    """

    RequestException = Exception

    class exceptions:  # noqa: N801 -- imita el namespace real `requests.exceptions`
        """Plan 295 F5 — el modulo bajo prueba distingue `SSLError` (el certificado
        no cerro) del resto de `RequestException` (no se pudo llegar). Sin este
        namespace en el doble, el `except requests.exceptions.SSLError` muere con
        AttributeError y `chk-tls` no puede dar su veredicto."""

        class SSLError(Exception):
            pass

        RequestException = Exception

    calls: list[dict] = []
    routes: dict = {}
    raise_on: set = set()

    @classmethod
    def reset(cls, routes: dict | None = None, raise_on: set | None = None):
        cls.calls = []
        cls.routes = routes or {}
        cls.raise_on = raise_on or set()

    @classmethod
    def get(cls, url, **kw):
        cls.calls.append({"url": url, **kw})
        for frag in cls.raise_on:
            if frag in url:
                raise cls.RequestException("instancia caida")
        for frag, resp in cls.routes.items():
            if frag in url:
                return resp
        return FakeResponse(404)

    class Session:
        """Plan 295 F5 — el modulo bajo prueba pasa por una `Session` para poder
        montar el adaptador OpenSSL SOLO en el prefijo del GitLab del proyecto
        (truststore reemplaza ssl.SSLContext en TODO el proceso, app.py:26, asi
        que un `verify=<bundle>` a secas no alcanza). El doble redirige a la misma
        `FakeRequests.get` de siempre: cero red, mismos escenarios."""

        def __init__(self):
            self.montados: list[tuple] = []

        def mount(self, prefijo, adaptador):
            self.montados.append((prefijo, adaptador))

        def get(self, url, **kw):
            return FakeRequests.get(url, **kw)


def test_el_doble_expone_requestexception():
    """Centinela: evita que alguien "simplifique" el doble mas adelante."""
    assert hasattr(FakeRequests, "RequestException")


@pytest.fixture(autouse=True)
def _sin_red(monkeypatch):
    from services import gitlab_setup_check

    FakeRequests.reset()
    monkeypatch.setattr(gitlab_setup_check, "requests", FakeRequests)


@pytest.fixture()
def client():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _motor_apagado(monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_GITLAB_ENABLED", False, raising=False)


def _verify(client, **extra):
    body = {
        "gitlab_url": "https://gitlab.com",
        "gitlab_project": "acme/api",
        "gitlab_token": _TOKEN,
    }
    body.update(extra)
    return client.post("/api/setup-guide/gitlab/verify", json=body)


def _by_id(resp) -> dict:
    return {c["id"]: c for c in resp.get_json()["checks"]}


def _todo_ok():
    return {
        "/version": FakeResponse(200, {"version": "17.0.0"}),
        "/user": FakeResponse(200, {"username": "usuario-de-prueba"}),
        "/personal_access_tokens/self": FakeResponse(200, {"scopes": ["api"]}),
        "/projects/": FakeResponse(200, {"issues_enabled": True,
                                         "name_with_namespace": "Acme / api"}),
    }


# ── GET de la guia ───────────────────────────────────────────────────────────

def test_get_guia_gitlab_200(client):
    resp = client.get("/api/setup-guide/gitlab")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    guide = resp.get_json()["guide"]
    assert guide["provider"] == "gitlab"
    assert len(guide["steps"]) == 12
    assert len(guide["checks"]) == 5


def test_get_guia_desconocida_404(client):
    assert client.get("/api/setup-guide/azure_devops").status_code == 404


def test_get_flag_off_403(client, monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_SETUP_GUIDE_ENABLED", False)
    assert client.get("/api/setup-guide/gitlab").status_code == 403


def test_verify_flag_off_403(client, monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_SETUP_GUIDE_VERIFY_ENABLED", False)
    FakeRequests.reset(_todo_ok())
    assert _verify(client).status_code == 403
    assert FakeRequests.calls == [], "con la flag apagada NO se debe salir a la red"


# ── los 5 chequeos ───────────────────────────────────────────────────────────

def test_verify_todo_ok(client):
    FakeRequests.reset(_todo_ok())
    resp = _verify(client, gitlab_enable_engine=True)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    for cid, chk in _by_id(resp).items():
        assert chk["status"] == "ok", f"{cid}: {chk}"


@pytest.mark.parametrize("escenario", ["sin_url", "url_caida", "sin_token", "proyecto_404"])
def test_verify_devuelve_siempre_6_chequeos(client, escenario):
    """INVARIANTE que la UI necesita para pintar la lista.

    Plan 295 F5 — eran 5 y ahora son 6 (`chk-tls`). El invariante NO se relaja:
    se sigue exigiendo la MISMA cantidad y la MISMA lista de ids en TODOS los
    caminos de salida; sólo cambió el número, que es el contrato que F5 mueve a
    proposito."""
    if escenario == "sin_url":
        FakeRequests.reset(_todo_ok())
        resp = _verify(client, gitlab_url="")
    elif escenario == "url_caida":
        FakeRequests.reset(_todo_ok(), raise_on={"/version"})
        resp = _verify(client)
    elif escenario == "sin_token":
        FakeRequests.reset(_todo_ok())
        resp = _verify(client, gitlab_token="")
    else:
        routes = _todo_ok()
        routes["/projects/"] = FakeResponse(404)
        FakeRequests.reset(routes)
        resp = _verify(client)

    checks = resp.get_json()["checks"]
    assert len(checks) == 6, f"{escenario}: {checks}"
    assert [c["id"] for c in checks] == _CHECK_IDS


def test_verify_url_invalida(client):
    FakeRequests.reset(_todo_ok())
    resp = _verify(client, gitlab_url="gitlab.com")
    checks = _by_id(resp)
    assert checks["chk-instancia"]["status"] == "fail"
    for cid in ("chk-token", "chk-scope", "chk-proyecto"):
        assert checks[cid]["status"] == "unknown"
    assert FakeRequests.calls == [], "sin esquema NO se debe salir a la red"


def test_verify_redirect_no_reenvia_token(client):
    """ANTI-FUGA DE CREDENCIAL: un 30x podria reenviar PRIVATE-TOKEN a otro host."""
    routes = _todo_ok()
    routes["/version"] = FakeResponse(302)
    FakeRequests.reset(routes)
    resp = _verify(client)

    assert _by_id(resp)["chk-instancia"]["status"] == "fail"
    # Plan 295 F5 — ahora son DOS llamadas a /version, no una: `chk-tls` sondea el
    # handshake ANTES de que exista un status HTTP, y recién después corre
    # chk-instancia. El invariante anti-fuga se ENDURECE en vez de relajarse: se
    # exige que NINGUNA de las llamadas lleve el header, no sólo la primera.
    assert len(FakeRequests.calls) == 2, FakeRequests.calls
    for llamada in FakeRequests.calls:
        assert "PRIVATE-TOKEN" not in llamada["headers"], llamada


def test_verify_token_401(client):
    routes = _todo_ok()
    routes["/user"] = FakeResponse(401)
    FakeRequests.reset(routes)
    assert _by_id(_verify(client))["chk-token"]["status"] == "fail"


def test_verify_scope_read_api(client):
    routes = _todo_ok()
    routes["/personal_access_tokens/self"] = FakeResponse(200, {"scopes": ["read_api"]})
    FakeRequests.reset(routes)
    chk = _by_id(_verify(client))["chk-scope"]
    assert chk["status"] == "fail"
    assert "solo puede LEER" in chk["message"]


def test_verify_scope_404_es_unknown(client):
    routes = _todo_ok()
    routes["/personal_access_tokens/self"] = FakeResponse(404)
    FakeRequests.reset(routes)
    assert _by_id(_verify(client))["chk-scope"]["status"] == "unknown"


def test_verify_issues_deshabilitado(client):
    routes = _todo_ok()
    routes["/projects/"] = FakeResponse(200, {"issues_enabled": False,
                                              "name_with_namespace": "Acme / api"})
    FakeRequests.reset(routes)
    assert _by_id(_verify(client))["chk-proyecto"]["status"] == "fail"


def test_verify_project_path_numerico_no_se_encodea(client):
    FakeRequests.reset(_todo_ok())
    _verify(client, gitlab_project="4711")
    assert any(c["url"].endswith("/projects/4711") for c in FakeRequests.calls), FakeRequests.calls


def test_verify_project_path_con_barras_se_encodea(client):
    FakeRequests.reset(_todo_ok())
    _verify(client, gitlab_project="acme/backend/api")
    assert any(
        c["url"].endswith("/projects/acme%2Fbackend%2Fapi") for c in FakeRequests.calls
    ), FakeRequests.calls


def test_verify_nunca_devuelve_el_token(client):
    FakeRequests.reset(_todo_ok())
    resp = _verify(client)
    assert _TOKEN not in json.dumps(resp.get_json())


def test_verify_timeout_y_sin_redirects(client):
    FakeRequests.reset(_todo_ok())
    _verify(client)
    assert FakeRequests.calls
    for call in FakeRequests.calls:
        assert call["timeout"] == 8
        assert call["allow_redirects"] is False


# ── el cliente NO puede pintar un verde falso (v2, C5) ───────────────────────

def test_engine_enabled_lo_pone_el_servidor(client):
    """Body con engine_enabled mentiroso (clave que el handler IGNORA)."""
    FakeRequests.reset(_todo_ok())
    resp = _verify(client, engine_enabled=True)
    assert _by_id(resp)["chk-flag"]["status"] == "fail"


def test_chk_flag_intencion_declarada_no_es_rojo(client):
    """El camino feliz ANTES de crear. Con la F4 de v1 esto era fail y volvia
    inalcanzable la DoD."""
    FakeRequests.reset(_todo_ok())
    chk = _by_id(_verify(client, gitlab_enable_engine=True))["chk-flag"]
    assert chk["status"] == "ok"
    assert "se va a activar al crear" in chk["message"]


def test_chk_flag_destildada_es_rojo(client):
    FakeRequests.reset(_todo_ok())
    assert _by_id(_verify(client, gitlab_enable_engine=False))["chk-flag"]["status"] == "fail"


def test_chk_instancia_401_es_ok_pero_lo_dice(client):
    """v2, C15: un 401 dice "pide autenticacion", no "es GitLab". Un portal SSO
    corporativo responde igual."""
    routes = _todo_ok()
    routes["/version"] = FakeResponse(401)
    FakeRequests.reset(routes)
    chk = _by_id(_verify(client))["chk-instancia"]
    assert chk["status"] == "ok"
    assert chk["message"] != "La URL responde y es un GitLab."
    assert "pide autenticación" in chk["message"]


# ── F4.c — las 3 flags salen por /api/diag/health ─────────────────────────────

def test_health_expone_las_3_flags(client):
    body = client.get("/api/diag/health").get_json()
    flags = body.get("flags") or {}
    for key in ("STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED",
                "STACKY_SETUP_GUIDE_ENABLED",
                "STACKY_SETUP_GUIDE_VERIFY_ENABLED"):
        assert flags.get(key) is True, f"{key} no sale en True por default: {flags}"


def test_health_refleja_la_flag_apagada(client, monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_SETUP_GUIDE_ENABLED", False)
    body = client.get("/api/diag/health").get_json()
    assert body["flags"]["STACKY_SETUP_GUIDE_ENABLED"] is False


def test_health_no_rompe_las_claves_viejas(client):
    """No-regresion: la clave `flags` es ADITIVA."""
    body = client.get("/api/diag/health").get_json()
    for key in ("version", "ok", "healthy", "source_commit"):
        assert key in body, f"falta la clave preexistente {key}"
