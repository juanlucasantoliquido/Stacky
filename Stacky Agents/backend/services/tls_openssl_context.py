"""services/tls_openssl_context.py — contexto SSL OpenSSL GENUINO por conexión.

POR QUÉ EXISTE: backend/app.py:24-28 llama truststore.inject_into_ssl(), que
reemplaza ssl.SSLContext para TODO el proceso. Truststore es NECESARIO (la red
tiene inspección TLS de Zscaler) y LETAL para el GitLab interno: verifica por
Windows CryptoAPI, ignora VERIFY_X509_PARTIAL_CHAIN (truststore/_windows.py:366-371)
y busca los certs del bundle con get_ca_certs(), que OMITE los que no son CA — y
el cert que hace falta es la HOJA de srvcgit01. Este módulo devuelve un contexto
OpenSSL de verdad para montarlo SOLO en la sesión de GitLab.

PROHIBIDO en este módulo: truststore.extract_from_ssl() (global, y el backend es
multi-hilo), REQUESTS_CA_BUNDLE/SSL_CERT_FILE/CURL_CA_BUNDLE (globales),
verify=False, y parchear urllib3.
"""
from __future__ import annotations

import _ssl                     # extensión C de CPython: los descriptores reales
import logging
import ssl
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class CaBundleInvalido(ValueError):
    """El bundle declarado no existe o no es legible. NUNCA se degrada en silencio."""


# Propiedades que hay que delegar al descriptor C. Ver el docstring de
# _construir_clase_genuina para el porqué.
_PROPIEDADES_DELEGADAS = (
    "verify_mode", "verify_flags", "options", "minimum_version", "maximum_version",
)

_clase_genuina: Optional[type] = None


def clase_ssl_context_original() -> type:
    """Devuelve la clase ssl.SSLContext GENUINA, haya o no inyectado truststore.

    - Sin inject: ssl.SSLContext ya es la genuina (__module__ == "ssl").
    - Con inject: en CPython truststore SUBCLASEA la genuina
      (truststore/_ssl_constants.py:20-22), así que está en el MRO.
    """
    actual = ssl.SSLContext
    if getattr(actual, "__module__", "") == "ssl":
        return actual
    for base in actual.__mro__:
        if base.__module__ == "ssl" and base.__name__ == "SSLContext":
            return base
    raise RuntimeError(
        "no se pudo recuperar ssl.SSLContext original; ¿intérprete no-CPython? "
        f"MRO actual: {actual.__mro__}"
    )


def _construir_clase_genuina() -> type:
    """Subclase de ssl.SSLContext cuyas properties saltean el setter de ssl.py.

    LA TRAMPA (documentada en §6 del plan 276): urllib3/connection.py:937 ejecuta
    `context.verify_mode = resolve_cert_reqs(cert_reqs)` SIEMPRE, aun con un
    ssl_context provisto. El setter de CPython resuelve el nombre `SSLContext`
    desde el módulo `ssl` — que truststore ya pisó — y entra en recursión
    infinita: RecursionError, NO un error de TLS. Un implementador que vea ese
    stack va a creer que se equivocó de certificado.

    La salida: delegar cada property al descriptor de _ssl._SSLContext, que es C
    y no pasa por el namespace envenenado. Es el mismo mecanismo que usa el
    propio truststore en _ssl_constants.py:28-31.
    """
    global _clase_genuina
    if _clase_genuina is not None:
        return _clase_genuina

    base = clase_ssl_context_original()
    espacio: dict = {}
    for nombre in _PROPIEDADES_DELEGADAS:
        descriptor = getattr(_ssl._SSLContext, nombre)
        espacio[nombre] = property(
            (lambda d: lambda self: d.__get__(self))(descriptor),
            (lambda d: lambda self, valor: d.__set__(self, valor))(descriptor),
        )
    _clase_genuina = type("_ContextoOpenSSLGenuino", (base,), espacio)
    return _clase_genuina


def crear_contexto_openssl(ca_bundle: Optional[str]) -> Optional[ssl.SSLContext]:
    """Contexto OpenSSL con el bundle cargado y el pin de hoja habilitado.

    Devuelve None si no hay bundle: en ese caso NO se monta ningún adapter y la
    sesión sigue por truststore (que es lo correcto para gitlab.com/Zscaler).

    Lanza CaBundleInvalido si el bundle está declarado pero no existe: fallar
    ABIERTO deja al operador sin señal (P0-2).
    """
    if not ca_bundle or not str(ca_bundle).strip():
        return None

    ruta = Path(str(ca_bundle).strip()).expanduser()
    if not ruta.is_file():
        raise CaBundleInvalido(
            f"El certificado declarado no existe: '{ca_bundle}'. "
            "Corregí la ruta en el campo 'Certificado de la empresa' del proyecto "
            "o dejalo vacío para usar la verificación estándar."
        )

    ctx = _construir_clase_genuina()(ssl.PROTOCOL_TLS_CLIENT)
    ctx.verify_mode = ssl.CERT_REQUIRED          # <- la línea de la trampa
    ctx.check_hostname = True
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        ctx.load_verify_locations(cafile=str(ruta.resolve()))
    except (ssl.SSLError, OSError) as exc:
        raise CaBundleInvalido(f"El certificado '{ca_bundle}' no se pudo leer: {exc}") from exc

    # Permite que una HOJA presente en el bundle actúe como ancla. NO debilita:
    # la hoja tiene que coincidir exactamente con la que presenta el servidor
    # (es pinning) y check_hostname sigue activo.
    ctx.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN

    stats = ctx.cert_store_stats()
    logger.info(
        "Contexto OpenSSL genuino para GitLab: %s certs (%s CA, %s hoja) desde %s",
        stats["x509"], stats["x509_ca"], stats["x509"] - stats["x509_ca"], ruta.name,
    )
    return ctx


__all__ = ["CaBundleInvalido", "clase_ssl_context_original", "crear_contexto_openssl"]
