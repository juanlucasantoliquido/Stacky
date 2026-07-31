"""tests/test_plan276_gitlab_session_adapter.py — Plan 276 F2.

REGLA ANTIFALSO-VERDE #1: producción inyecta truststore (backend/app.py:24-28).
La inyección va a nivel de MÓDULO, ANTES de importar lo que se prueba: sin esto
el test no prueba producción y puede quedar verde con el bug vivo.

REGLA #5: GITLAB_TOKEN dummy para separar TLS de AUTH y para que el cliente NO
lea (ni reescriba) el archivo de credenciales real (gitlab_client.py:78-80).
"""
import ssl

import pytest
import requests

_CLASE_SSL_ANTES = ssl.SSLContext
import truststore                                    # noqa: E402

truststore.inject_into_ssl()
assert ssl.SSLContext is not _CLASE_SSL_ANTES, (
    "truststore no se inyectó: este archivo NO está probando producción"
)

import config as config_mod                          # noqa: E402
from services.gitlab_client import GitLabClient, _AdaptadorOpenSSL  # noqa: E402
from services.tracker_provider import TrackerApiError, TrackerConfigError  # noqa: E402

BUNDLE = r"N:\GIT\RS\STACKY\Stacky\Stacky Agents\deployment\ca-bundle-migrador.pem"
BASE = "https://gl.interno"


@pytest.fixture(autouse=True)
def entorno_limpio(monkeypatch):
    """Token dummy y sin bundles heredados del entorno del operador."""
    monkeypatch.setenv("GITLAB_TOKEN", "dummy-para-aislar-tls")
    monkeypatch.delenv("STACKY_GITLAB_CA_BUNDLE", raising=False)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.delenv("GITLAB_URL", raising=False)


def _cliente(**kw):
    kw.setdefault("base_url", BASE)
    kw.setdefault("project", "grupo/proyecto")
    return GitLabClient(**kw)


def test_el_entorno_de_test_replica_produccion():
    assert ssl.SSLContext.__module__ == "truststore._api"


def test_con_bundle_monta_el_adapter_en_el_prefijo_de_gitlab():
    c = _cliente(ca_bundle=BUNDLE)
    assert BASE in c._session.adapters, f"adapters: {list(c._session.adapters)}"
    adapter = c._session.adapters[BASE]
    assert isinstance(adapter, _AdaptadorOpenSSL)
    assert type(adapter) is not requests.adapters.HTTPAdapter


def test_el_contexto_del_adapter_es_openssl_genuino():
    c = _cliente(ca_bundle=BUNDLE)
    adapter = c._session.adapters[BASE]
    assert adapter._contexto.cert_store_stats()["x509"] == 119
    assert not any(
        m.__module__.startswith("truststore") for m in type(adapter._contexto).__mro__
    ), f"el contexto es de truststore: {type(adapter._contexto).__mro__}"


def test_sin_bundle_no_monta_nada():
    """EL GATE DE 'no rompo Zscaler': sin bundle la sesión queda de fábrica y
    todo sale por truststore, que es lo que resuelve gitlab.com."""
    c = _cliente(ca_bundle=None)
    assert set(c._session.adapters) == {"http://", "https://"}


def test_no_toca_la_sesion_global_de_requests():
    antes_ssl = ssl.SSLContext
    antes_ctx = requests.adapters._preloaded_ssl_context
    _cliente(ca_bundle=BUNDLE)
    assert ssl.SSLContext is antes_ssl, "se tocó ssl.SSLContext"
    assert requests.adapters._preloaded_ssl_context is antes_ctx, (
        "se tocó el contexto global de requests"
    )


def test_sslerror_se_envuelve_en_trackerapierror(monkeypatch):
    """P1-7: sin esto la SSLError sube CRUDA y ningún `except TrackerApiError`
    aguas arriba la ve — el operador recibe un 500 mudo."""
    c = _cliente(ca_bundle=BUNDLE)

    def _explota(*a, **kw):
        raise requests.exceptions.SSLError("boom")

    monkeypatch.setattr(c._session, "request", _explota)
    with pytest.raises(TrackerApiError) as exc_info:
        c._request("GET", "/user")
    assert exc_info.value.kind == "tls"
    assert "ca-bundle-migrador.pem" in str(exc_info.value), (
        f"el mensaje no nombra el bundle en uso: {exc_info.value}"
    )


def test_connectionerror_se_envuelve_en_trackerapierror(monkeypatch):
    c = _cliente(ca_bundle=BUNDLE)

    def _explota(*a, **kw):
        raise requests.exceptions.ConnectionError("sin ruta al host")

    monkeypatch.setattr(c._session, "request", _explota)
    with pytest.raises(TrackerApiError) as exc_info:
        c._request("GET", "/user")
    assert exc_info.value.kind == "network"


def test_con_la_flag_off_vuelve_el_camino_de_hoy(monkeypatch):
    monkeypatch.setattr(
        config_mod.config, "STACKY_GITLAB_TLS_ADAPTER_ENABLED", False, raising=False
    )
    c = _cliente(ca_bundle=BUNDLE)
    assert set(c._session.adapters) == {"http://", "https://"}, "se montó adapter con la flag OFF"
    assert c._verify and str(c._verify).endswith("ca-bundle-migrador.pem"), (
        f"con la flag OFF el bundle tiene que viajar por verify=: {c._verify!r}"
    )


def test_bundle_inexistente_falla_ruidoso():
    """P0-2: fallar ABIERTO está prohibido. NUNCA un cliente construido con la
    verificación degradada en silencio."""
    with pytest.raises(TrackerConfigError):
        _cliente(ca_bundle=r"C:\no\existe.pem")
