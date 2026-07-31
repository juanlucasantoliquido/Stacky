"""services/tls_pinning.py — verificación TLS contra certificados internos.

Extraído de `tools/migrar_mantis_gitlab/destination_writer.py`, donde la
capacidad nació para poder hablar con `srvcgit01.imsolutions.local`. Vive acá
para que la use también el cliente compartido `services/gitlab_client.py`: el
migrador podía llegar al GitLab interno y el resto del producto no, con lo cual
toda funcionalidad GitLab del backend moría en `CERTIFICATE_VERIFY_FAILED`.

DIFERENCIA IMPORTANTE CON EL MIGRADOR: el migrador exporta `REQUESTS_CA_BUNDLE`,
que es **global al proceso**. En un proceso corto y monopropósito eso es
aceptable; en el backend NO, porque el mismo proceso habla con Azure DevOps,
Jira, Mantis y APIs de LLM, y apuntar el bundle a un CA interno rompería la
verificación de todos los demás destinos. (El propio config del migrador lo
documenta: `deployment/migration_config_ripley.json` → `_ca_bundle_nota`, donde
una corrida murió contra el ORIGEN por exactamente esto.) Por eso acá el bundle
se aplica **por conexión**, vía el parámetro `verify=` de `requests`.

PLAN 276 F2.3 — EL PARCHE GLOBAL DE urllib3 SE ELIMINÓ. Este módulo tenía un
`habilitar_pin_de_certificado_hoja()` que reemplazaba, en DOS módulos de urllib3,
la fábrica compartida de contextos SSL para agregarle `VERIFY_X509_PARTIAL_CHAIN`.
Esa fábrica la usa TODO el proceso: mientras el TLS de GitLab estaba roto el
parche era inerte, pero apenas empezó a funcionar habría aplicado el pin de hoja
a las conexiones de Azure DevOps, Jira y las APIs de LLM, debilitando su
verificación (P1-5). El pin vive ahora en el `ssl_context` de un HTTPAdapter
montado SOLO en la sesión de GitLab: ver `services/tls_openssl_context.py` y
`_AdaptadorOpenSSL` en `services/gitlab_client.py`.

Este archivo NO debe volver a nombrar ni tocar esa fábrica de urllib3: el criterio
de aceptación de F2.3 es que una búsqueda de su nombre acá devuelva cero.

PLAN 276 F3 — EL BUNDLE DEJÓ DE FALLAR ABIERTO. Una ruta de certificado que el
operador DECLARÓ (parámetro del proyecto o `STACKY_GITLAB_CA_BUNDLE`) y que no
existe ya no se ignora con un warning en un log que nadie mira: lanza
`CaBundleInvalido`. Antes, un typo en el campo "Certificado de la empresa" caía
en `verify=True` y el operador veía "no confía en el certificado" sin ninguna
señal de que su ruta estaba mal.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from services.tls_openssl_context import CaBundleInvalido

logger = logging.getLogger(__name__)

_ENV_VARS = ("STACKY_GITLAB_CA_BUNDLE", "REQUESTS_CA_BUNDLE")

# Fuentes que constituyen una DECLARACIÓN del operador: si apuntan a un archivo
# que no existe, es un error suyo y tiene que verlo. `REQUESTS_CA_BUNDLE` queda
# afuera a propósito: la puede setear el entorno corporativo por motivos ajenos a
# Stacky, así que una ruta rota ahí degrada con warning en vez de romper.
_FUENTES_DECLARADAS = ("parámetro del proyecto", "STACKY_GITLAB_CA_BUNDLE")

# Valor de `verify=` para la verificación estándar de requests (el almacén por
# defecto). Solo se alcanza cuando NO se declaró ningún bundle: una ruta
# declarada y rota lanza (F3). Es una constante nombrada y no un `True` suelto
# para que quede explícito que este camino NO es una degradación silenciosa.
_VERIFICACION_ESTANDAR = True


def resolver_ca_bundle(
    explicito: Optional[str] = None, *, estricto: bool = True
) -> Optional[str]:
    """Resuelve la ruta del bundle: parámetro > STACKY_GITLAB_CA_BUNDLE > REQUESTS_CA_BUNDLE.

    Devuelve la ruta absoluta si el archivo existe, o None si no se declaró
    ninguno.

    Args:
        explicito: ruta declarada por el proyecto (campo "Certificado de la
            empresa"). Tiene precedencia sobre las variables de entorno.
        estricto: con True (default, Plan 276 F3), una ruta DECLARADA que no
            existe lanza `CaBundleInvalido` en vez de degradar en silencio. Con
            False vuelve el comportamiento previo (warning + None), que es lo
            que usa la rama con `STACKY_GITLAB_TLS_ADAPTER_ENABLED` apagada.

    Raises:
        CaBundleInvalido: solo con `estricto=True`, y solo para las fuentes de
            `_FUENTES_DECLARADAS`.
    """
    candidatos = [explicito] + [os.environ.get(v) for v in _ENV_VARS]
    etiquetas = ("parámetro del proyecto",) + _ENV_VARS
    for cand, etiqueta in zip(candidatos, etiquetas):
        if not cand or not str(cand).strip():
            continue
        ruta = Path(str(cand).strip()).expanduser()
        if ruta.is_file():
            return str(ruta.resolve())
        if estricto and etiqueta in _FUENTES_DECLARADAS:
            raise CaBundleInvalido(
                f"El certificado declarado ({etiqueta}) no existe: '{cand}'. "
                "Corregí la ruta en el campo 'Certificado de la empresa' del proyecto "
                "o dejalo vacío para usar la verificación estándar."
            )
        logger.warning(
            "CA bundle declarado en '%s' (%s) pero el archivo no existe; se ignora "
            "y se usa la verificación por defecto.", cand, etiqueta
        )
    return None


def preparar_verificacion(ca_bundle: Optional[str] = None, *, estricto: bool = True):
    """Devuelve el valor para el `verify=` de `requests`.

    Si hay bundle, devuelve su ruta absoluta. Si NO se declaró ninguno, devuelve
    la verificación estándar. Una ruta declarada que no existe lanza
    `CaBundleInvalido` cuando `estricto` (F3): no se degrada nunca en silencio.

    El pin de hoja (`VERIFY_X509_PARTIAL_CHAIN`) ya NO se habilita acá — vive en
    el ssl_context del adapter de la sesión de GitLab (F1/F2), porque hacerlo
    global debilitaba la verificación de ADO/Jira/LLM.
    """
    ruta = resolver_ca_bundle(ca_bundle, estricto=estricto)
    return ruta or _VERIFICACION_ESTANDAR


__all__ = [
    "CaBundleInvalido",
    "resolver_ca_bundle",
    "preparar_verificacion",
]
