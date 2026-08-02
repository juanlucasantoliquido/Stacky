"""Plan 290 F1 — el UNICO escritor de metadata["capability_degraded"].

Cuando Stacky decide A PROPOSITO no ejecutar una capacidad porque el tracker del
proyecto no la tiene (los ocho guards del Plan 281 F7), devuelve un valor neutro
y hasta hoy no dejaba rastro: el operador leia "preflight OK" o "score 1.0" sin
forma de saber que no se valido ni se reviso nada.

Este modulo anota esa decision en la fila de la ejecucion. Es TELEMETRIA:

  * NUNCA levanta. Una corrida jamas se cae por no poder anotar un aviso.
  * Es idempotente: la misma (capability, site) en la misma corrida se anota UNA
    vez. Sin el dedup, un backlog de 200 tickets escribiria 200 entradas.
  * No cambia ningun valor de retorno de quien la llama. Se agrega una llamada
    ANTES del `return`; el `return` no se toca.

Misma disciplina que `context_enrichment.persistir_stats_de_contexto` (:284-321),
que es el hermano del Plan 289: import local de la sesion para evitar ciclos,
reasignacion COMPLETA de `metadata_dict` y `try/except` total.
"""
from __future__ import annotations

from datetime import datetime, timezone

from models import AgentExecution

#: Clave de `AgentExecution.metadata_dict` donde vive la lista de degradaciones.
#: Su AUSENCIA es el estado valido de toda ejecucion historica y de toda corrida
#: que no degrade: nada la exige.
CLAVE_METADATA = "capability_degraded"


def _noop_log(*_args, **_kwargs) -> None:
    """Sumidero de registro.

    Existe para que `declarar()` pueda loguear en su `except` sin comprobar si el
    llamador paso `log=`. Copia del idioma de `context_enrichment.py:305`
    (`log = log or _noop_log`), y se define ACA en vez de importarlo: acoplar dos
    servicios por una funcion de tres caracteres sale mas caro que repetirla.
    """
    return None


def construir_entrada(*, capability: str, reason: str, provider: str, site: str) -> dict:
    """Forma canonica de una degradacion declarada. PURA: sin I/O, sin base, sin config.

    El contrato son estas CINCO claves y ninguna mas: el consumidor de la interfaz
    (`frontend/src/services/capabilityDegradedModel.ts`) depende de ellas.

    `site` es un SIMBOLO (`business_preflight._evaluate_functional`), nunca
    `archivo:linea`: las lineas caducan entre pasadas y mandarian al operador a
    leer el lugar equivocado.
    """
    return {
        "capability": capability,
        "reason": reason,
        "provider": provider,
        "site": site,
        "at": datetime.now(timezone.utc).isoformat(),
    }


def declarar(
    *,
    execution_id: int | None,
    capability: str,
    reason: str,
    provider: str,
    site: str,
    session_factory=None,
    log=None,
) -> bool:
    """Anota la degradacion en `metadata[CLAVE_METADATA]`. NUNCA levanta. Idempotente.

    Devuelve True SOLO si escribio. `False` significa "no habia donde anotar" o
    "ya estaba anotado", nunca un error que el llamador deba manejar.

    Sin `execution_id` (el caso de `api/agents.py:542`, que evalua antes de que
    exista la fila) es un no-op silencioso: no hay destino, y anotar en una fila
    inventada seria peor que no anotar.
    """
    # C7 — PRIMERA linea, antes de cualquier cosa que pueda fallar. Con `log=None`
    # (el default, y el camino normal: los call sites de F2/F3 no pasan log) el
    # `except` de abajo llamaria `None("warn", ...)` y lanzaria TypeError DESDE el
    # manejador, rompiendo el riel "nunca levanta" justo donde dice cubrirlo.
    log = log or _noop_log

    if execution_id is None:
        return False
    if not capability:
        return False

    try:
        if session_factory is None:
            from db import session_scope as session_factory  # import local: evita ciclos

        with session_factory() as sesion:
            fila = sesion.get(AgentExecution, execution_id)
            if fila is None:
                return False

            md = dict(fila.metadata_dict or {})
            bruto = md.get(CLAVE_METADATA)
            lista = list(bruto) if isinstance(bruto, list) else []

            entrada = construir_entrada(
                capability=capability, reason=reason, provider=provider, site=site
            )

            # Dedup por (capability, site): la MISMA degradacion en la MISMA corrida
            # se anota una sola vez. Dos capacidades distintas en el mismo sitio SI
            # se anotan las dos.
            clave = (entrada["capability"], entrada["site"])
            for previa in lista:
                if not isinstance(previa, dict):
                    continue
                if (previa.get("capability"), previa.get("site")) == clave:
                    return False

            lista.append(entrada)
            md[CLAVE_METADATA] = lista
            # Reasignacion COMPLETA del dict: mutar el que devuelve el getter no
            # marca la fila como sucia en SQLAlchemy y el cambio se pierde en
            # silencio. Mismo idioma que context_enrichment.py:315-317.
            fila.metadata_dict = md
        return True
    except Exception as exc:  # noqa: BLE001 — un aviso nunca tumba un run
        log("warn", f"no se pudo declarar la degradación: {exc}")
        return False
