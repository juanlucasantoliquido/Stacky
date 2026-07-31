"""tests/test_plan276_tls_context.py — Plan 276 F1.

REGLA ANTIFALSO-VERDE #1: producción inyecta truststore (backend/app.py:24-28).
Un test de TLS que no lo inyecte NO prueba producción: los 27 tests verdes de
GitLab que ya existen conviven con el bug por exactamente esto.
La inyección va a nivel de MÓDULO, ANTES de importar lo que se prueba.
"""
import ssl

import pytest

_CLASE_SSL_ANTES = ssl.SSLContext
import truststore                                    # noqa: E402

truststore.inject_into_ssl()
assert ssl.SSLContext is not _CLASE_SSL_ANTES, (
    "truststore no se inyectó: este archivo NO está probando producción"
)

from services import tls_openssl_context as toc      # noqa: E402

BUNDLE = r"N:\GIT\RS\STACKY\Stacky\Stacky Agents\deployment\ca-bundle-migrador.pem"


def test_el_entorno_de_test_replica_produccion():
    """Gate de la regla #1: si esto falla, ningún otro test de este archivo vale."""
    assert ssl.SSLContext.__module__ == "truststore._api"


def test_recupera_la_clase_ssl_original_pese_al_inject():
    original = toc.clase_ssl_context_original()
    assert original.__module__ == "ssl" and original.__name__ == "SSLContext"
    assert original in ssl.SSLContext.__mro__


def test_setear_verify_mode_no_lanza_recursion_error():
    """LA TRAMPA. Un contexto construido con la clase original SIN las
    propiedades delegadas lanza RecursionError acá (verificado en F0 paso 3).
    Este test es el gate corrido CONTRA el defecto."""
    ctx = toc.crear_contexto_openssl(BUNDLE)
    ctx.verify_mode = ssl.CERT_REQUIRED              # no debe lanzar
    assert ctx.verify_mode == ssl.CERT_REQUIRED


def test_el_contexto_no_es_de_truststore():
    ctx = toc.crear_contexto_openssl(BUNDLE)
    assert not any(m.__module__.startswith("truststore") for m in type(ctx).__mro__), (
        f"el contexto es de truststore: {type(ctx).__mro__}"
    )
    # discriminador independiente: truststore._api.SSLContext.cert_store_stats
    # lanza NotImplementedError (truststore/_api.py:195); el genuino responde.
    assert isinstance(ctx.cert_store_stats(), dict)


def test_el_bundle_llega_a_openssl_incluida_la_hoja():
    """get_ca_certs() OMITE los certs que no son CA — y el que hace falta es una
    HOJA. Por eso el gate es cert_store_stats(), no get_ca_certs()."""
    ctx = toc.crear_contexto_openssl(BUNDLE)
    stats = ctx.cert_store_stats()
    assert stats["x509"] == 119, f"certs cargados: {stats}"
    assert stats["x509"] - stats["x509_ca"] == 1, (
        f"la HOJA de srvcgit01 no entró al store: {stats}"
    )
    assert len(ctx.get_ca_certs()) == 118, "control: get_ca_certs es ciego a la hoja"


def test_el_pin_de_hoja_y_la_verificacion_conviven():
    ctx = toc.crear_contexto_openssl(BUNDLE)
    assert ctx.verify_flags & ssl.VERIFY_X509_PARTIAL_CHAIN
    assert ctx.verify_mode == ssl.CERT_REQUIRED, "la verificación NO se debilita"
    assert ctx.check_hostname is True, "check_hostname sigue activo"
    assert ctx.minimum_version == ssl.TLSVersion.TLSv1_2


def test_no_muta_nada_global():
    """P1-5: el pin vive en el contexto, no en urllib3 ni en el módulo ssl."""
    import urllib3.util.ssl_ as u3ssl

    antes_ssl = ssl.SSLContext
    antes_u3 = u3ssl.create_urllib3_context
    toc.crear_contexto_openssl(BUNDLE)
    assert ssl.SSLContext is antes_ssl, "se tocó ssl.SSLContext"
    assert u3ssl.create_urllib3_context is antes_u3, "se parcheó urllib3 (prohibido)"


def test_sin_bundle_devuelve_none_y_no_construye_nada():
    """Sin bundle NO se monta adapter: la sesión sigue por truststore (Zscaler)."""
    assert toc.crear_contexto_openssl(None) is None
    assert toc.crear_contexto_openssl("") is None


def test_ruta_inexistente_no_se_ignora_en_silencio():
    """P0-2: fallar ABIERTO está prohibido."""
    with pytest.raises(toc.CaBundleInvalido):
        toc.crear_contexto_openssl(r"C:\ruta\que\no\existe.pem")
