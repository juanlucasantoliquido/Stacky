"""tests/test_plan276_tls_bundle_estricto.py — Plan 276 F3.

Dos defectos, los dos de tipeo del operador y los dos hoy MUDOS:

P0-2 — una ruta de certificado declarada que no existe se ignoraba con un warning
en un log que nadie mira y se caía a `verify=True`. El operador veía "no confía en
el certificado" SIN ninguna señal de que su ruta estaba mal. Ahora lanza.

P1-4 — una `base_url` con el namespace pegado (`https://host/grupo`) producía
`https://host/grupo/api/v4/...` => HTTP 404 mudo. Ahora el error nombra el
sobrante y dice a qué campo va.
"""
import ssl

import pytest

_CLASE_SSL_ANTES = ssl.SSLContext
import truststore                                    # noqa: E402

truststore.inject_into_ssl()
assert ssl.SSLContext is not _CLASE_SSL_ANTES, (
    "truststore no se inyectó: este archivo NO está probando producción"
)

from services import tls_pinning as tp               # noqa: E402
from services.gitlab_client import _validar_base_url  # noqa: E402
from services.tls_openssl_context import CaBundleInvalido  # noqa: E402
from services.tracker_provider import TrackerConfigError    # noqa: E402


@pytest.fixture(autouse=True)
def sin_bundles_del_entorno(monkeypatch):
    monkeypatch.delenv("STACKY_GITLAB_CA_BUNDLE", raising=False)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)


# ── P0-2: el bundle deja de fallar ABIERTO ────────────────────────────────────

def test_ruta_declarada_inexistente_lanza():
    """EL GATE CORRIDO CONTRA EL DEFECTO: hoy devolvía None y degradaba mudo."""
    with pytest.raises(CaBundleInvalido) as exc_info:
        tp.resolver_ca_bundle(r"C:\ruta\que\no\existe.pem")
    assert "no existe" in str(exc_info.value)
    assert "Certificado de la empresa" in str(exc_info.value), (
        "el mensaje tiene que decirle al operador QUÉ campo corregir"
    )


def test_env_declarada_inexistente_tambien_lanza(monkeypatch):
    """STACKY_GITLAB_CA_BUNDLE es una declaración del operador (se administra
    por UI): una ruta rota ahí es su error y tiene que verlo."""
    monkeypatch.setenv("STACKY_GITLAB_CA_BUNDLE", r"C:\tampoco\existe.pem")
    with pytest.raises(CaBundleInvalido):
        tp.resolver_ca_bundle(None)


def test_requests_ca_bundle_inexistente_degrada_con_warning(monkeypatch, caplog):
    """REQUESTS_CA_BUNDLE la puede setear el entorno corporativo por motivos
    ajenos a Stacky: una ruta rota ahí NO es una declaración del operador, así
    que degrada con warning en vez de romper."""
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", r"C:\del\entorno\roto.pem")
    with caplog.at_level("WARNING"):
        assert tp.resolver_ca_bundle(None) is None
    mensajes = [r.getMessage() for r in caplog.records]
    assert any("no existe" in m for m in mensajes), f"sin warning: {mensajes}"


def test_bundle_valido_devuelve_ruta_absoluta(tmp_path):
    p = tmp_path / "bundle.pem"
    p.write_text("-----BEGIN CERTIFICATE-----\nx\n-----END CERTIFICATE-----\n", encoding="utf-8")
    resuelto = tp.resolver_ca_bundle(str(p))
    assert resuelto == str(p.resolve())


def test_con_estricto_false_vuelve_el_comportamiento_de_hoy():
    """La rama con el adapter apagado tiene que ser byte-idéntica a hoy."""
    assert tp.resolver_ca_bundle(r"C:\no\existe.pem", estricto=False) is None
    assert tp.preparar_verificacion(r"C:\no\existe.pem", estricto=False) is True


# ── P1-4: la base_url se valida ───────────────────────────────────────────────

def test_base_url_con_api_v4_nombra_api_v4():
    with pytest.raises(TrackerConfigError) as exc_info:
        _validar_base_url("https://srvcgit01.imsolutions.local/api/v4")
    assert "/api/v4" in str(exc_info.value)


def test_base_url_con_namespace_pegado_nombra_el_sobrante():
    """El gotcha histórico: el namespace en la URL da un 404 mudo."""
    with pytest.raises(TrackerConfigError) as exc_info:
        _validar_base_url("https://srvcgit01.imsolutions.local/ripley/agenda")
    mensaje = str(exc_info.value)
    assert "/ripley/agenda" in mensaje, f"el error no nombra el sobrante: {mensaje}"
    assert "Proyecto" in mensaje, "el error no dice a qué campo va el sobrante"


def test_base_url_sin_esquema_falla():
    with pytest.raises(TrackerConfigError):
        _validar_base_url("srvcgit01.imsolutions.local")


def test_base_url_limpia_pasa_y_vacia_devuelve_vacio():
    assert _validar_base_url("https://srvcgit01.imsolutions.local") == (
        "https://srvcgit01.imsolutions.local"
    )
    assert _validar_base_url("https://gl.interno:8443/") == "https://gl.interno:8443"
    # Vacía: comportamiento de hoy — se resuelve más tarde con TrackerConfigError
    # en _request ("GITLAB_URL no configurada"), no acá.
    assert _validar_base_url("") == ""
    assert _validar_base_url(None) == ""
