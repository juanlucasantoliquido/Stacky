"""Verificación TLS del cliente GitLab compartido (`services/tls_pinning.py`).

Contexto: contra un GitLab interno (certificado propio, emisora fuera de todo
almacén) TODA llamada de `services/gitlab_client.py` moría con
`CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate`. La
capacidad existía sólo dentro del migrador Mantis→GitLab.

Estos tests prueban COMPORTAMIENTO (qué `verify` viaja en la request real, y que
el pin de hoja quede efectivamente aplicado), no la mera existencia del helper.

═══ ENDURECIDO POR EL PLAN 276 F10 — los 4 defectos de ESTE archivo, por escrito ═══

Estos tests estaban VERDES conviviendo con el bug, y el motivo de cada cambio queda
acá para que no se re-introduzcan:

1. `assert capturado.get("verify") is not False` quedaba verde si `verify`
   DESAPARECÍA por completo (`.get()` devuelve None, y `None is not False`). Ahora se
   exige que la clave EXISTA y no sea None.
2. La precedencia se probaba con `REQUESTS_CA_BUNDLE="/no/existe.pem"`: esa ruta se
   descartaba por no existir, así que el test NO probaba precedencia — probaba que se
   ignora una ruta rota. Ahora se usan DOS bundles que EXISTEN.
3. `test_el_pin_es_idempotente` seteaba el guard y después afirmaba que la función
   devolvía False: AUTOCUMPLIDO. Reescrito contra el diseño nuevo.
4. `test_el_migrador_sigue_usando_el_helper_compartido` seteaba el guard en True y
   afirmaba que ambos devolvían False: AUTOCUMPLIDO. Reescrito para verificar que hay
   UNA sola implementación.

Y, sobre todo: NINGUNO de estos tests corría con `truststore.inject_into_ssl()`
aplicado, que es lo que hace producción (`backend/app.py:24-28`). Por eso 27 tests
verdes convivían con un TLS roto. La inyección va ahora a nivel de MÓDULO, antes de
importar lo que se prueba.
"""
from __future__ import annotations

import os
import ssl
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_CLASE_SSL_ANTES = ssl.SSLContext
import truststore  # noqa: E402

truststore.inject_into_ssl()
assert ssl.SSLContext is not _CLASE_SSL_ANTES, (
    "truststore no se inyectó: este archivo NO está probando producción"
)

import pytest  # noqa: E402

from services import gitlab_client as gl  # noqa: E402
from services import tls_pinning as tp  # noqa: E402
from services.tls_openssl_context import CaBundleInvalido  # noqa: E402

# Certificado REAL del repo. No se generan certificados: este venv no tiene
# `cryptography` ni `openssl` (medido). Desde F2 el constructor del cliente PARSEA
# el bundle, así que un PEM falso ya no sirve como fixture.
_HOJA_REAL = Path(__file__).resolve().parents[2] / "deployment" / "srvcgit01-hoja.pem"


class _Resp:
    status_code = 200
    ok = True
    content = b"{}"
    headers = {"Content-Type": "application/json"}

    def json(self):
        return {"id": 1}


def test_el_entorno_de_test_replica_produccion():
    """Gate de la regla antifalso-verde #1: si esto falla, nada de este archivo vale."""
    assert ssl.SSLContext.__module__ == "truststore._api"


@pytest.fixture()
def bundle(tmp_path):
    assert _HOJA_REAL.is_file(), f"falta el certificado de referencia: {_HOJA_REAL}"
    p = tmp_path / "ca-bundle.pem"
    p.write_bytes(_HOJA_REAL.read_bytes())
    return p


@pytest.fixture()
def bundle_2(tmp_path):
    p = tmp_path / "otro-ca-bundle.pem"
    p.write_bytes(_HOJA_REAL.read_bytes())
    return p


def _cliente(monkeypatch, capturado, **kw):
    monkeypatch.setenv("GITLAB_TOKEN", "t0ken")
    # Plan 276 F10: se mockea `requests.Session.request` (el seam NUEVO de F2), no
    # `gl.requests.request`. Mockear el viejo dejaría el test verde sin ejecutar una
    # sola línea del transporte real.
    monkeypatch.setattr(
        gl.requests.Session, "request",
        lambda self, *a, **k: (capturado.update(k), _Resp())[1],
    )
    return gl.GitLabClient(base_url="https://gl.example", project="g/p", **kw)


# ── resolución del bundle ──────────────────────────────────────────────────


def test_resolver_ca_bundle_prefiere_el_explicito(bundle, bundle_2, monkeypatch):
    """F10 #2: con DOS bundles que EXISTEN, esto prueba precedencia de verdad."""
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(bundle_2))
    monkeypatch.setenv("STACKY_GITLAB_CA_BUNDLE", str(bundle_2))
    assert tp.resolver_ca_bundle(str(bundle)) == str(bundle.resolve()), (
        "el parámetro explícito tiene que ganarle a las dos env vars"
    )


def test_resolver_ca_bundle_cae_a_la_env(bundle, monkeypatch):
    monkeypatch.delenv("STACKY_GITLAB_CA_BUNDLE", raising=False)
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(bundle))
    assert tp.resolver_ca_bundle(None) == str(bundle.resolve())


def test_resolver_ca_bundle_ignora_ruta_inexistente_de_la_env(monkeypatch):
    """Una ruta rota en `REQUESTS_CA_BUNDLE` NO rompe: se degrada.

    PLAN 276 F3 cambió el contrato SOLO para las rutas que el operador DECLARA
    (parámetro del proyecto o `STACKY_GITLAB_CA_BUNDLE`): esas ahora lanzan, porque
    degradar en silencio lo dejaba sin ninguna señal de que su ruta estaba mal.
    `REQUESTS_CA_BUNDLE` la puede setear el entorno corporativo por motivos ajenos
    a Stacky, así que ahí se conserva la degradación — que es lo que este test
    siempre quiso proteger.
    """
    monkeypatch.delenv("STACKY_GITLAB_CA_BUNDLE", raising=False)
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", "/ruta/que/no/existe.pem")
    assert tp.resolver_ca_bundle(None) is None


def test_una_ruta_declarada_inexistente_ahora_lanza(monkeypatch):
    """La otra mitad del contrato nuevo (F3/P0-2): fallar ABIERTO está prohibido."""
    monkeypatch.delenv("STACKY_GITLAB_CA_BUNDLE", raising=False)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    with pytest.raises(CaBundleInvalido):
        tp.resolver_ca_bundle("/ruta/que/no/existe.pem")


# ── comportamiento observable en la request ────────────────────────────────


def test_el_cliente_manda_el_bundle_en_verify(bundle, monkeypatch):
    capturado: dict = {}
    c = _cliente(monkeypatch, capturado, ca_bundle=str(bundle))
    c._request("GET", "/user")
    assert capturado.get("verify") == str(bundle.resolve()), (
        f"verify={capturado.get('verify')!r}: el bundle no llegó a requests"
    )


def test_sin_bundle_verify_queda_en_true(monkeypatch):
    """Sin bundle NO se toca nada: verificación estándar, no `verify=False`."""
    monkeypatch.delenv("STACKY_GITLAB_CA_BUNDLE", raising=False)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    capturado: dict = {}
    c = _cliente(monkeypatch, capturado)
    c._request("GET", "/user")
    assert capturado.get("verify") is True, f"verify={capturado.get('verify')!r}"


def test_nunca_desactiva_la_verificacion(bundle, monkeypatch):
    """Riel de seguridad: `verify` jamás puede salir en False.

    F10 #1: antes era `assert capturado.get("verify") is not False`, que quedaba
    VERDE si `verify` desaparecía del todo (None is not False). Ahora se exige que
    la clave exista y tenga un valor de verificación real.
    """
    for kw in ({"ca_bundle": str(bundle)}, {}):
        capturado: dict = {}
        c = _cliente(monkeypatch, capturado, **kw)
        c._request("GET", "/user")
        assert "verify" in capturado, (
            "`verify` DESAPARECIÓ de la request: requests caería a su default y este "
            f"assert quedaría verde con la verificación fuera de control. kwargs={capturado}"
        )
        assert capturado["verify"] is not False
        assert capturado["verify"] is not None


# ── el pin de hoja se aplica de verdad (ahora POR CONEXIÓN) ────────────────


def test_el_pin_de_hoja_vive_en_el_contexto_del_adapter(bundle, monkeypatch):
    """Reemplaza al test que miraba el contexto GLOBAL de urllib3.

    Ese test era decorativo bajo truststore: `u3ssl.create_urllib3_context()`
    devolvía un contexto de truststore, cuyo `verify_flags` NO participa de la
    construcción de cadena (verifica por Windows CryptoAPI). El pin real vive ahora
    en el `ssl_context` del adapter montado en la sesión de GitLab.
    """
    capturado: dict = {}
    c = _cliente(monkeypatch, capturado, ca_bundle=str(bundle))

    adapter = c._session.adapters.get("https://gl.example")
    assert adapter is not None, f"no se montó el adapter: {list(c._session.adapters)}"
    ctx = adapter._contexto
    assert ctx.verify_flags & ssl.VERIFY_X509_PARTIAL_CHAIN, (
        "el contexto del adapter no quedó con VERIFY_X509_PARTIAL_CHAIN"
    )
    assert ctx.verify_mode == ssl.CERT_REQUIRED, "la verificación NO se debilita"
    assert ctx.check_hostname is True, "check_hostname debe seguir activo"
    assert not any(m.__module__.startswith("truststore") for m in type(ctx).__mro__), (
        "el contexto es de truststore: no verifica por OpenSSL y el pin es inerte"
    )


def test_dos_contextos_no_comparten_estado_global(bundle, bundle_2):
    """Reemplaza a `test_el_pin_es_idempotente`, que era AUTOCUMPLIDO (seteaba el
    guard y después afirmaba que la función devolvía False).

    El diseño nuevo no tiene guard ni estado global: cada llamada devuelve su propio
    contexto, y tocar uno no puede afectar al otro ni al resto del proceso.
    """
    from services.tls_openssl_context import crear_contexto_openssl

    import urllib3.util.ssl_ as u3ssl

    antes = u3ssl.create_urllib3_context
    a = crear_contexto_openssl(str(bundle))
    b = crear_contexto_openssl(str(bundle_2))

    assert a is not b, "se devolvió el MISMO contexto: habría estado compartido"
    assert u3ssl.create_urllib3_context is antes, "se parcheó urllib3 (prohibido: es global)"

    # Tocar uno no toca al otro.
    a.verify_flags &= ~ssl.VERIFY_X509_PARTIAL_CHAIN
    assert b.verify_flags & ssl.VERIFY_X509_PARTIAL_CHAIN, "los contextos comparten estado"


def test_el_migrador_usa_la_implementacion_compartida():
    """Reemplaza a `test_el_migrador_sigue_usando_el_helper_compartido`, que era
    AUTOCUMPLIDO. La propiedad que importa es que haya UNA sola implementación del
    pin y que el migrador NO mantenga una copia divergente.
    """
    from tools.migrar_mantis_gitlab import destination_writer as dw

    import re

    fuente = Path(dw.__file__).read_text(encoding="utf-8")
    assert "from services.tls_openssl_context import crear_contexto_openssl" in fuente, (
        "el migrador dejó de delegar en la implementación compartida"
    )
    # Se busca la ASIGNACIÓN (el defecto real), no la mención: nombrar el símbolo en
    # un comentario que explica por qué se eliminó es correcto y no debe dar rojo.
    # Este criterio es además más fuerte que un grep de la palabra: no se puede
    # esquivar renombrando un comentario.
    patron = re.compile(
        r"(create_urllib3_context\s*=)|(setattr\([^)]*create_urllib3_context)"
    )
    ofensores = [
        f"{n}: {l.strip()}"
        for n, l in enumerate(fuente.splitlines(), 1)
        if patron.search(l)
    ]
    assert ofensores == [], (
        "el migrador volvió a parchear la fábrica global de contextos de urllib3: "
        f"eso debilita la verificación de Azure DevOps, Jira y las APIs de LLM. {ofensores}"
    )
    # Y la función que expone existe y delega (no reimplementa).
    assert callable(dw.verificar_pin_de_certificado_hoja)
    assert not hasattr(dw, "habilitar_pin_de_certificado_hoja"), (
        "volvió el punto de entrada del parche global"
    )
