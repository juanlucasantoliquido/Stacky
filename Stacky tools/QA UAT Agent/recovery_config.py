"""recovery_config.py — Plan 262 F2. Lector unico de la config de recuperacion.

DOS CAMINOS, UN SOLO DEFAULT. Cuando el pipeline corre desde el backend,
api/qa_uat.py::_export_qa_uat_flags escribe estas keys en os.environ. Cuando corre
desde la CLI (que es como se depura y como se verifica el DoD), NADIE las exporta
—trampa documentada del plan 240 C13—. Por eso los defaults EFECTIVOS viven aca
duplicados a proposito, y un test de paridad cross-arbol falla si divergen de config.py.

LIMITACION HEREDADA (plan 240 C5, no empeorada aca): os.environ es global al proceso
y el pipeline corre en un threading.Thread, asi que dos corridas concurrentes
comparten los valores del ultimo export. Es aceptable en el modelo mono-operador.

NADA de esto levanta. Un ValueError leyendo config terminaria rotulado
PIPELINE_CRASH, que es exactamente el bug que este plan cierra.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("stacky.qa_uat.recovery_config")

DEFAULTS: dict[str, str] = {
    "STACKY_QA_UAT_HOT_RECOVERY_ENABLED":    "true",
    "STACKY_QA_UAT_RECOVERY_MAX_PER_RUN":    "6",
    "STACKY_QA_UAT_RECOVERY_MAX_PER_CASE":   "1",
    "STACKY_QA_UAT_HEALTH_PROBE_TIMEOUT_S":  "5.0",
    "STACKY_QA_UAT_HEALTH_PROBE_CONFIRM_S":  "2.0",
    "STACKY_QA_UAT_ROUTE_ALLOWLIST":         "",
    "STACKY_QA_UAT_SAFE_ROUTE":              "",
    "AGENDA_WEB_BASE_URL":                   "http://localhost:35017/AgendaWeb/",
    "QA_NAV_RETRIES":                        "3",
}

# Los mismos bounds que declaran las FlagSpec. value_in_bounds protege la escritura
# por UI, pero NO protege una env var puesta a mano: aca se clampea.
_BOUNDS: dict[str, tuple[float, float]] = {
    "STACKY_QA_UAT_RECOVERY_MAX_PER_RUN":   (0, 50),
    "STACKY_QA_UAT_RECOVERY_MAX_PER_CASE":  (0, 10),
    "STACKY_QA_UAT_HEALTH_PROBE_TIMEOUT_S": (1, 30),
    "STACKY_QA_UAT_HEALTH_PROBE_CONFIRM_S": (0, 15),
    "QA_NAV_RETRIES":                       (0, 10),
}

_TRUTHY = ("1", "true", "yes", "si", "sí", "on")


def _raw(key: str) -> str:
    return os.environ.get(key, DEFAULTS.get(key, ""))


def _clamp(key: str, value: float) -> float:
    lo, hi = _BOUNDS[key]
    if value < lo:
        logger.warning("%s=%s por debajo del minimo %s; se clampea", key, value, lo)
        return lo
    if value > hi:
        logger.warning("%s=%s por encima del maximo %s; se clampea", key, value, hi)
        return hi
    return value


def _num(key: str, caster):
    """Lee una numerica: no parseable -> default; fuera de bounds -> clampeo."""
    raw = _raw(key)
    try:
        value = caster(raw)
    except (TypeError, ValueError):
        logger.warning("%s=%r no es numerico; se usa el default %s",
                       key, raw, DEFAULTS.get(key))
        try:
            value = caster(DEFAULTS[key])
        except (TypeError, ValueError, KeyError):
            return caster(0)
    return caster(_clamp(key, value)) if key in _BOUNDS else value


def hot_recovery_enabled() -> bool:
    return _raw("STACKY_QA_UAT_HOT_RECOVERY_ENABLED").strip().lower() in _TRUTHY


def recovery_max_per_run() -> int:
    return int(_num("STACKY_QA_UAT_RECOVERY_MAX_PER_RUN", int))


def recovery_max_per_case() -> int:
    return int(_num("STACKY_QA_UAT_RECOVERY_MAX_PER_CASE", int))


def health_probe_timeout_s() -> float:
    return float(_num("STACKY_QA_UAT_HEALTH_PROBE_TIMEOUT_S", float))


def health_probe_confirm_s() -> float:
    return float(_num("STACKY_QA_UAT_HEALTH_PROBE_CONFIRM_S", float))


def route_allowlist_raw() -> list[str]:
    """csv con espacios y comas colgantes -> lista limpia, sin vacios."""
    return [p.strip() for p in _raw("STACKY_QA_UAT_ROUTE_ALLOWLIST").split(",") if p.strip()]


def safe_route_raw() -> str:
    """v2/C5: type='str'. Devuelve el string TAL CUAL, no una lista."""
    return _raw("STACKY_QA_UAT_SAFE_ROUTE").strip()


def base_url() -> str:
    """Normalizada con '/' final, igual que environment_preflight.py:77."""
    raw = _raw("AGENDA_WEB_BASE_URL").strip() or DEFAULTS["AGENDA_WEB_BASE_URL"]
    return raw.rstrip("/") + "/"


def nav_retries() -> int:
    return int(_num("QA_NAV_RETRIES", int))


def validate_recovery_config() -> list[str]:
    """[] = OK. Cada string es un problema legible para el operador."""
    problemas: list[str] = []
    declarada = route_allowlist_raw()
    segura = safe_route_raw()
    if segura and declarada:
        nombres = {p.rsplit("/", 1)[-1].lower() for p in declarada}
        if segura.rsplit("/", 1)[-1].lower() not in nombres:
            problemas.append(
                f"la ruta segura {segura!r} no pertenece a la allowlist declarada "
                f"{declarada!r}: volver a una ruta que el validador rechaza es un bucle"
            )
    if recovery_max_per_case() > recovery_max_per_run():
        problemas.append(
            "el maximo por caso supera al maximo por corrida; se clampea al minimo"
        )
    return problemas


def snapshot() -> dict:
    """Para el log y para runtime-doctor. SIN credenciales: solo las 9 keys."""
    return {
        "STACKY_QA_UAT_HOT_RECOVERY_ENABLED": hot_recovery_enabled(),
        "STACKY_QA_UAT_RECOVERY_MAX_PER_RUN": recovery_max_per_run(),
        "STACKY_QA_UAT_RECOVERY_MAX_PER_CASE": recovery_max_per_case(),
        "STACKY_QA_UAT_HEALTH_PROBE_TIMEOUT_S": health_probe_timeout_s(),
        "STACKY_QA_UAT_HEALTH_PROBE_CONFIRM_S": health_probe_confirm_s(),
        "STACKY_QA_UAT_ROUTE_ALLOWLIST": route_allowlist_raw(),
        "STACKY_QA_UAT_SAFE_ROUTE": safe_route_raw(),
        "AGENDA_WEB_BASE_URL": base_url(),
        "QA_NAV_RETRIES": nav_retries(),
    }
