"""services/gitlab_sync_watermark.py — Plan 292.

Hasta qué momento se sincronizó cada proyecto de GitLab. Molde EXACTO de
`services/integration_breaker.py` (:55-67): un JSON en data_dir(), lectura
tolerante que degrada a vacío, escritura best-effort.

POR QUÉ TOLERA TODO. Este store existe para AHORRAR trabajo, nunca para
habilitarlo. Cada camino de error devuelve "no sé", y "no sé" significa
sincronización COMPLETA — o sea, exactamente lo que el sync hacía antes de que
este módulo existiera. NINGÚN fallo de acá puede hacer que el sync traiga MENOS
de lo que traería sin este módulo.

LA HORA ES LA DE GITLAB, NUNCA LA DE LA MÁQUINA. La marca sale de
`item["updated_at"]`, que lo puso el servidor. Con `datetime.utcnow()`, un reloj
local adelantado dejaría fuera del delta siguiente todo lo modificado en la
ventana de desfase, en silencio y para siempre.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional

import config  # el MÓDULO: la instancia de opciones es `config.config`
from runtime_paths import data_dir

logger = logging.getLogger(__name__)

_FILENAME = "gitlab_sync_watermark.json"
_LOCK = threading.Lock()

# Cota de seguridad, NO opción de operador. Mismo criterio que `_TOPE_PADRES = 50`
# de gitlab_sync.py:47. 120 s cubren dos cosas a la vez: el issue modificado
# DURANTE el sync (entre la primera página y la última) y la duda sobre si
# `updated_after` de GitLab es inclusivo o exclusivo — con este solapamiento el
# diseño es correcto en los dos casos.
_SOLAPAMIENTO_SEG = 120

# Si la marca quedó más vieja que esto, se hace una corrida COMPLETA aunque el
# contador no haya llegado a su cuota. Red de seguridad para el backend apagado
# varios días.
_EDAD_MAX_MARCA_H = 24


def _path():
    return data_dir() / _FILENAME


def _load() -> dict:
    """Todo el archivo, o {} ante CUALQUIER anomalía. Nunca lanza."""
    try:
        p = _path()
        if not p.exists():
            return {}
        datos = json.loads(p.read_text(encoding="utf-8"))
        return datos if isinstance(datos, dict) else {}
    except Exception:   # noqa: BLE001 — degradar a COMPLETO es siempre correcto
        logger.warning(
            "Plan 292: marca de sincronización ilegible; se hará completa", exc_info=True
        )
        return {}


def _save(datos: dict) -> None:
    """Best-effort. Si no se puede escribir, la próxima corrida es completa."""
    try:
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(datos, indent=2, sort_keys=True), encoding="utf-8")
    except Exception:   # noqa: BLE001
        logger.warning("Plan 292: no se pudo guardar la marca de sincronización", exc_info=True)


def parsear(valor) -> Optional[datetime]:
    """ISO-8601 de GitLab -> datetime naive UTC. None si no parsea.

    Receta idéntica a services/ado_sync.py:57. NO usar strptime con "%SZ": los
    milisegundos de GitLab (".000Z") lo rompen. Tampoco `.rstrip("Z")`, que
    descarta la zona en vez de convertirla.
    """
    if not valor or not isinstance(valor, str):
        return None
    try:
        return datetime.fromisoformat(valor.strip().replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def marca_maxima(valores) -> Optional[str]:
    """El `updated_at` más nuevo de la tanda, MENOS el solapamiento, en ISO con Z.

    Devuelve None si la tanda está vacía o si ninguno parsea — y ese None hace
    que el llamador NO toque la marca guardada, que es lo correcto: un delta
    vacío significa "no cambió nada", no "avanzá el reloj".
    """
    fechas = [d for d in (parsear(v) for v in (valores or [])) if d is not None]
    if not fechas:
        return None
    tope = max(fechas) - timedelta(seconds=_SOLAPAMIENTO_SEG)
    return tope.isoformat(timespec="seconds") + "Z"


def leer_marca(proyecto: str) -> tuple[Optional[str], int]:
    """(marca_iso, contador_de_parciales) o (None, 0) ante cualquier anomalía."""
    with _LOCK:
        entrada = _load().get(proyecto)
    if not isinstance(entrada, dict):
        return (None, 0)
    marca = entrada.get("marca")
    contador = entrada.get("contador")
    # `isinstance(True, int)` es True en Python: el `is True` descarta booleanos,
    # que en un JSON escrito a mano son un error de tipo, no un contador.
    if parsear(marca) is None or not isinstance(contador, int) or contador is True or contador < 0:
        return (None, 0)
    return (marca, contador)


def escribir_marca(proyecto: str, marca: Optional[str], contador: int) -> None:
    """Guarda la marca del proyecto. MONOTONA: la marca nunca retrocede.

    Si `marca` es None (delta vacío o toda la tanda ilegible) NO la toca.
    Si `marca` es MAS VIEJA que la guardada, tampoco: se conserva la vieja.

    POR QUE NUNCA RETROCEDE (plan 292 v2, R11). En modo COMPLETO la query es de
    ABIERTOS, así que `items` no incluye los cerrados. Si el cambio más reciente
    del proyecto fue sobre un issue cerrado, el max(updated_at) de esa tanda es
    MAS VIEJO que la marca que dejó el último incremental. Escribirlo haría que
    la corrida siguiente pidiera una ventana enorme — matando el ahorro y
    arrastrando una tanda grande de cerrados.

    Quedarse ATRAS sólo cuesta traer de más, que es el lado seguro; adelantarse
    pierde ítems en silencio. La asimetría es la misma que gobierna todo el
    módulo, y por eso acá se resuelve con un max() y no con una condición.
    """
    with _LOCK:
        datos = _load()
        actual = datos.get(proyecto) if isinstance(datos.get(proyecto), dict) else {}
        previa = actual.get("marca")
        elegida = previa
        if marca is not None:
            d_nueva, d_previa = parsear(marca), parsear(previa)
            if d_previa is None or (d_nueva is not None and d_nueva > d_previa):
                elegida = marca
        datos[proyecto] = {
            "marca": elegida,
            "contador": max(0, int(contador)),
        }
        _save(datos)


# ── Plan 292 v2 §3.1-bis — la barrera de admisión del delta ────────────────────
# Estados que GitLab reporta como "no cerrado". `_upsert_ticket_gitlab` cae a
# "opened" cuando el campo falta (gitlab_sync.py:148), así que la barrera NO
# puede ser más estricta que él: un ítem sin estado se admite.
_ESTADOS_ABIERTOS = ("opened", "reopened", "")


def admitir_del_delta(item: dict, *, fila_existe: bool, modo: str) -> bool:
    """¿Este ítem del listado puede llegar al upsert?

    En modo COMPLETO devuelve SIEMPRE True: la query es de abiertos, ningún
    cerrado llega, y el camino queda byte-idéntico al de antes de este plan.

    En modo INCREMENTAL la query es `state="all"`, así que SI llegan cerrados.
    Un cerrado que YA tiene fila local se admite —es la detección de cierre de
    §3.1—, pero un cerrado que NO tiene fila local se SALTEA: hoy esa fila no
    existe, `list_tickets` (api/tickets.py:1104) no filtra por estado y ordena
    por last_synced_at con tope 500, así que crearla la pondría arriba del
    tablero del operador y le comería una posición a un abierto real. Nadie la
    saca nunca: el modo COMPLETO marca cerrado por ausencia, jamás borra.
    """
    if modo != "incremental":
        return True
    if fila_existe:
        return True
    estado = (item.get("state") or "").strip().lower()
    return estado in _ESTADOS_ABIERTOS
