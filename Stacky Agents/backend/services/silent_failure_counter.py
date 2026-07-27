"""Plan 255 F1/F2 — contador de fallos TRAGADOS + nivel de log por clase de error.

Por qué existe
--------------
El backend tiene 165 `except Exception: pass` medidos por AST. Muchos son
CORRECTOS (telemetría best-effort, limpieza en `finally`, matar un proceso ya
muerto) y este módulo **no** los convierte en `raise`: los hace CONTABLES.
Antes de tocar un `pass` hay que saber si se dispara de verdad.

Reglas duras
------------
- `note_swallowed` **jamás** levanta: su cuerpo entero va dentro de un
  `try/except BaseException`. Si el contador falla, no puede tumbar el código
  que estaba protegiendo.
- `note_swallowed` **no loguea**. Si lo hiciera, los 12 sitios instrumentados
  generarían exactamente el ruido que el plan 257 va a combatir — y en
  `console_log_handler` (el sink de logs) crearía recursión.
- `site` es un identificador estable `"modulo.funcion"` **sin número de línea**:
  las líneas se mueven en cada edición y el histórico se partiría.
- Cota de memoria: máximo 500 sites distintos.

REGLA ANTI-CONCLUSIÓN (leer antes de usar el reporte)
-----------------------------------------------------
El contador vive en RAM y el backend reinicia varias veces por día. Por eso
`swallowed_report()` declara SIEMPRE su ventana. Un `count == 0` **NO** prueba
que un sitio sea inerte: solo prueba que no se disparó en ESTA ventana. Nunca se
retira instrumentación ni se degrada un sitio basándose en un cero. El reporte
sirve para PRIORIZAR qué investigar, jamás para descartar.

No se persiste a disco a propósito: los ledgers JSONL son del plan 258.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

__all__ = [
    "note_swallowed",
    "swallowed_report",
    "reset_swallowed",
    "log_level_for",
    "log_at_level",
    "level_int_for",
    "MAX_SITES",
]

MAX_SITES = 500

_PROCESS_STARTED_AT = datetime.now(timezone.utc)
_PROCESS_STARTED_MONOTONIC = time.monotonic()

# site -> {"count": int, "last_exc_type": str | None, "last_seen": str}
_COUNTS: dict[str, dict] = {}


def _flag_on(key: str) -> bool:
    """Lee la flag desde la INSTANCIA `config.config` (nunca desde el módulo).

    Ante cualquier problema devuelve True: un contador de diagnóstico no puede
    apagarse por un fallo al leer su propia configuración.
    """
    try:
        from config import config

        return bool(getattr(config, key, True))
    except Exception:  # noqa: BLE001
        return True


def note_swallowed(site: str, exc: BaseException | None = None) -> None:
    """Registra que un `except` tragó un fallo, SIN loguear y SIN levantar.

    `site` es un identificador estable "modulo.funcion" (SIN número de línea).
    Costo: un incremento de dict. Pensado para llamarse dentro de un
    `except ...: pass` sin cambiar su semántica ni su performance.
    """
    try:
        if not _flag_on("STACKY_SILENT_FAILURE_COUNTER_ENABLED"):
            return
        clave = str(site)
        fila = _COUNTS.get(clave)
        if fila is None:
            if len(_COUNTS) >= MAX_SITES:
                return  # cota dura: no se crean claves nuevas
            fila = {"count": 0, "last_exc_type": None, "last_seen": None}
            _COUNTS[clave] = fila
        fila["count"] += 1
        if exc is not None:
            fila["last_exc_type"] = type(exc).__name__
        fila["last_seen"] = datetime.now(timezone.utc).isoformat()
    except BaseException:  # noqa: BLE001
        # silence-ok: el contador de fallos jamás puede tumbar el código que protege
        pass


def swallowed_report(top: int = 30) -> dict:
    """Reporte ordenado por `count` desc, con la VENTANA declarada.

    {'window': {'process_started_at': iso, 'window_seconds': int},
     'rows': [{'site','count','last_exc_type','last_seen'}]}
    """
    try:
        limite = max(1, int(top))
    except (TypeError, ValueError):
        limite = 30

    filas = [
        {
            "site": site,
            "count": int(datos.get("count", 0)),
            "last_exc_type": datos.get("last_exc_type"),
            "last_seen": datos.get("last_seen"),
        }
        for site, datos in _COUNTS.items()
    ]
    filas.sort(key=lambda f: (-f["count"], f["site"]))

    return {
        "window": {
            "process_started_at": _PROCESS_STARTED_AT.isoformat(),
            "window_seconds": int(time.monotonic() - _PROCESS_STARTED_MONOTONIC),
        },
        "rows": filas[:limite],
        "sites_total": len(_COUNTS),
        "sites_cap": MAX_SITES,
    }


def reset_swallowed() -> None:
    """Solo para tests."""
    _COUNTS.clear()


# ── F2 — nivel de log por CLASE de excepción ──────────────────────────────────

# TypeError EXCLUIDO a propósito (plan 255 C10): es la excepción más común por
# datos malos del operador o de una API externa, no por un bug. Meterla acá
# inunda el log. Promoverla requiere el throttle del plan 257 en el árbol.
_STRUCTURAL = (ImportError, ModuleNotFoundError, AttributeError, NameError)


def log_level_for(exc: BaseException) -> str:
    """'error' si es un bug estructural, 'warning' si es transitorio.

    Estructural = ImportError / ModuleNotFoundError / AttributeError / NameError:
    son bugs de código, no se arreglan solos y no son transitorios. Todo lo
    demás (locks, timeouts, red, datos malos) es transitorio → 'warning'.
    """
    return "error" if isinstance(exc, _STRUCTURAL) else "warning"


def _nivel_efectivo(exc: BaseException) -> str:
    """Nivel efectivo de `exc`. UN SOLO lugar decide (lo consumen log_at_level y
    level_int_for). Con `STACKY_STRUCTURAL_ERRORS_TO_ERROR_LEVEL` en OFF todo
    sale a 'warning', que es el comportamiento previo exacto."""
    if _flag_on("STACKY_STRUCTURAL_ERRORS_TO_ERROR_LEVEL"):
        return log_level_for(exc)
    return "warning"


def log_at_level(logger, exc: BaseException, msg: str, *args) -> None:
    """Loguea `msg` al nivel que corresponde a `exc`. UN SOLO lugar decide.

    Con `STACKY_STRUCTURAL_ERRORS_TO_ERROR_LEVEL` en OFF todo sale a `warning`,
    que es el comportamiento previo exacto (kill-switch sin cambio de datos).
    """
    getattr(logger, _nivel_efectivo(exc))(msg, *args)


def level_int_for(exc: BaseException) -> int:
    """Plan 257 F1-bis — el MISMO nivel que decide `log_at_level`, como int de
    `logging`, para poder pasarlo a `log_throttled` sin duplicar la regla.

    Existe porque el throttle del 257 necesita el nivel ANTES de loguear y
    `log_at_level` ya loguea. Prohibido revertir el nivel del plan 255 para
    hacer throttleable un sitio: `log_throttled` respeta su intervalo sea cual
    sea el nivel.
    """
    import logging

    return logging.ERROR if _nivel_efectivo(exc) == "error" else logging.WARNING
