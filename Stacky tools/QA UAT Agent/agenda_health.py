"""agenda_health.py — Plan 262 F1. UNICA fuente de verdad de "AgendaWeb responde AHORA".

POR QUE EXISTE. environment_preflight.run_environment_preflight corre UNA VEZ, antes
de abrir el navegador (qa_uat_pipeline.py:400) y esta disenado para NO reintentar
(comentario literal en environment_preflight.py:53). Este modulo es el chequeo EN
CALIENTE: barato, acotado, repetible, y SIEMPRE contra la URL base estable, nunca
contra la ruta que fallo (invariante INV-5 del plan 262).

NUNCA lanza. NUNCA usa un modelo. Determinista.

DIRECCION DE DEPENDENCIA (explicita, para que no nazca un ciclo): este modulo POSEE
ALIVE_STATUS_CODES y NO importa environment_preflight a nivel de modulo. Es
environment_preflight el que importa a este en F9. El import de get_agenda_base_url
va DENTRO de la funcion justamente por eso.
"""
from __future__ import annotations

import time
import urllib.error
import urllib.request
from dataclasses import dataclass, replace

ALIVE_STATUS_CODES: frozenset[int] = frozenset({200, 301, 302, 400, 401, 403})
DEFAULT_PROBE_TIMEOUT_S: float = 5.0
DEFAULT_CONFIRM_PAUSE_S: float = 2.0        # F1.5

# v2 / C11 — UNICA constante del default de la URL base en este modulo. El v1 la
# hardcodeaba inline, agregando un CUARTO literal "http://localhost:35017/AgendaWeb/"
# en el mismo plan cuya F9 borra uno y asserta 0 hits en otro archivo.
DEFAULT_BASE_URL: str = "http://localhost:35017/AgendaWeb/"

_MIN_TIMEOUT_S: float = 0.5
_MAX_CONFIRM_PAUSE_S: float = 15.0


@dataclass(frozen=True)
class HealthProbe:
    alive: bool
    status: int | None
    url: str
    elapsed_ms: int
    error: str            # "" cuando alive is True
    source: str           # "http_probe" | "http_probe_confirmed" | "http_probe_flapped"
    samples: int = 1      # F1.5 — cuantas muestras sostienen este veredicto


def _ms(t0: float) -> int:
    return int((time.time() - t0) * 1000)


def probe_url(url: str, *, timeout_s: float | None = None) -> HealthProbe:
    """Un GET contra `url`. NUNCA lanza: toda excepcion se traduce a alive=False."""
    t0 = time.time()
    to = DEFAULT_PROBE_TIMEOUT_S if timeout_s is None else float(timeout_s)
    # BORDE 1: timeout <= 0 seria un probe que nunca puede dar vivo. Se clampea.
    to = max(_MIN_TIMEOUT_S, to)
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=to) as resp:
            code = int(resp.getcode())
            return HealthProbe(
                code in ALIVE_STATUS_CODES, code, url, _ms(t0), "", "http_probe"
            )
    except urllib.error.HTTPError as exc:
        # BORDE 2: 401/403/302 PRUEBAN que el proceso sirve HTTP. Vivo.
        code = int(getattr(exc, "code", 0))
        alive = code in ALIVE_STATUS_CODES
        return HealthProbe(
            alive, code, url, _ms(t0), "" if alive else f"HTTP {code}", "http_probe"
        )
    except urllib.error.URLError as exc:
        return HealthProbe(
            False, None, url, _ms(t0), f"URLError: {exc.reason}", "http_probe"
        )
    except OSError as exc:
        return HealthProbe(False, None, url, _ms(t0), f"OSError: {exc}", "http_probe")
    except Exception as exc:                       # noqa: BLE001 — NUNCA lanza
        return HealthProbe(
            False, None, url, _ms(t0), f"{type(exc).__name__}: {exc}", "http_probe"
        )


def probe_agenda(*, base_url: str | None = None,
                 timeout_s: float | None = None) -> HealthProbe:
    """Probe contra la URL BASE estable. INV-5: nunca contra la ruta que fallo."""
    url = base_url
    if not url:
        # IMPORT DIFERIDO A PROPOSITO: environment_preflight va a importar ESTE modulo
        # en F9 para su alias de alive codes. Un import de modulo aca crearia un ciclo.
        try:
            from environment_preflight import get_agenda_base_url
            url = get_agenda_base_url()
        except Exception:                          # noqa: BLE001
            url = DEFAULT_BASE_URL                 # v2/C11: la constante, no un literal
    if timeout_s is None:
        try:
            from recovery_config import health_probe_timeout_s   # F2; opcional
            timeout_s = health_probe_timeout_s()
        except Exception:                          # noqa: BLE001
            timeout_s = DEFAULT_PROBE_TIMEOUT_S
    return probe_url(url, timeout_s=timeout_s)


def probe_agenda_confirmed(*, base_url: str | None = None,
                           timeout_s: float | None = None,
                           confirm_pause_s: float | None = None) -> HealthProbe:
    """SERVICE_DOWN necesita DOS muertos consecutivos. Un muerto seguido de un vivo
    es un FLAP (reciclado de AppPool), no una caida: no autoriza arrancar nada.

    Es la unica funcion cuyo veredicto negativo puede abrir un proceso en la maquina
    del operador, y por eso es la unica que paga una segunda muestra.
    """
    first = probe_agenda(base_url=base_url, timeout_s=timeout_s)
    if first.alive:
        return replace(first, source="http_probe_confirmed", samples=1)
    pause = DEFAULT_CONFIRM_PAUSE_S if confirm_pause_s is None else float(confirm_pause_s)
    pause = min(_MAX_CONFIRM_PAUSE_S, max(0.0, pause))   # BORDE: negativo -> 0
    if pause > 0:
        time.sleep(pause)
    second = probe_agenda(base_url=base_url, timeout_s=timeout_s)
    if second.alive:
        # FLAP: la app volvio sola. NO se gasta el arranque de servicio.
        return replace(second, source="http_probe_flapped", samples=2)
    return replace(second, source="http_probe_confirmed", samples=2)


def is_alive(*, base_url: str | None = None, timeout_s: float | None = None) -> bool:
    return probe_agenda(base_url=base_url, timeout_s=timeout_s).alive
