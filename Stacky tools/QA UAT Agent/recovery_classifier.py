"""recovery_classifier.py — Plan 262 F3. Las 5 clases del pedido del operador.

Convierte "algo exploto" en "esto es una ruta mala, NO una caida". Todo el resto
del plan depende de este veredicto.

CAPA DE TRADUCCION, NO REEMPLAZO. Existen CUATRO taxonomias paralelas en el tool
(playwright_result_classifier, failure_triage, uat_failure_analyzer y los codigos
de navigation_driver) y este modulo no reescribe ninguna: MAPEA a ellas.

Determinista y puro: sin red, sin disco, sin modelos. La disponibilidad se recibe
YA medida (parametro `health`), nunca se consulta desde aca.
"""
from __future__ import annotations

from dataclasses import dataclass

# Las 5 clases del pedido del operador. str, no Enum: estos valores viajan a JSONL,
# a runner_output.json y al dossier; un Enum obligaria .value en ~40 sitios y en un
# archivo donde casi todo esta envuelto en `except Exception` un AttributeError
# silencioso seria invisible. Frozenset + constantes es el patron de la casa.
SERVICE_DOWN      = "SERVICE_DOWN"        # caida de servicio
ROUTE_ERROR       = "ROUTE_ERROR"         # error de ruta
SESSION_ERROR     = "SESSION_ERROR"       # error de sesion
FUNCTIONAL_ERROR  = "FUNCTIONAL_ERROR"    # error funcional de la prueba
UNRECOVERABLE     = "UNRECOVERABLE"       # error no recuperable

RECOVERY_CLASSES: frozenset[str] = frozenset({
    SERVICE_DOWN, ROUTE_ERROR, SESSION_ERROR, FUNCTIONAL_ERROR, UNRECOVERABLE,
})

# Mapeo a lo que YA existe. No reemplaza: traduce.
_CLASS_TO_TAXONOMY: dict[str, dict] = {
    SERVICE_DOWN:     {"verdict": "BLOCKED", "category": "ENV", "reason": "APP_NOT_RUNNING",
                       "owner": "devops",        "recoverable": True},
    ROUTE_ERROR:      {"verdict": "BLOCKED", "category": "NAV", "reason": "ROUTE_INVALID",
                       "owner": "qa_automation", "recoverable": True},
    SESSION_ERROR:    {"verdict": "BLOCKED", "category": "NAV", "reason": "SESSION_LOST",
                       "owner": "qa_automation", "recoverable": True},
    FUNCTIONAL_ERROR: {"verdict": "FAIL",    "category": "APP", "reason": None,
                       "owner": "developer",     "recoverable": False},
    UNRECOVERABLE:    {"verdict": "BLOCKED", "category": "OPS", "reason": "UNRECOVERABLE",
                       "owner": "qa_automation", "recoverable": False},
}

# Los ONCE codigos que navigation_driver.py puede producir (v2/C2: el v1 mapeaba 10
# y se dejaba afuera NAV_WRONG_SCREEN, que es justamente "pantalla equivocada").
# Cada linea lleva la linea REAL del driver donde nace, para que el gate de deriva
# sea auditable a mano.
_NAV_CODE_TO_CLASS: dict[str, str] = {
    "NAV_DEVIATION":                ROUTE_ERROR,     # :651, :872
    "NAV_WRONG_SCREEN":             ROUTE_ERROR,     # :569  <-- v2/C2, faltaba
    "MENU_LABEL_NOT_FOUND":         ROUTE_ERROR,     # :524, :877
    "NAV_FORM_NOT_FOUND":           ROUTE_ERROR,     # :721, :886
    "APP_ERROR_PAGE":               ROUTE_ERROR,     # :879
    "NAV_DOPOSTBACK_NOT_AVAILABLE": ROUTE_ERROR,     # :734 (ternario -> error_code=_ec)
    "NAV_SESSION_LOST":             SESSION_ERROR,   # :551, :875
    "NAV_AUTH_EXPIRED":             SESSION_ERROR,   # :807, :882
    "NAV_TIMEOUT":                  UNRECOVERABLE,   # :486, :613, :836, :884 - ver nota
    "NAV_JS_ERROR":                 UNRECOVERABLE,   # :734 (ternario -> error_code=_ec)
    "NAV_PLAYWRIGHT_ERROR":         UNRECOVERABLE,   # :887 (fallback final del driver)
}

# Senales textuales de perdida de sesion, cuando el driver no dejo codigo.
_SESSION_PATTERNS: tuple[str, ...] = (
    "frmlogin", "session", "sesion expirada", "authentication", "no autenticado",
)

_RUTA_DESCONOCIDA = "<desconocida>"


def is_recoverable(recovery_class: str) -> bool:
    """v2/C14 — API PUBLICA para F5. Un modulo externo no indexa _CLASS_TO_TAXONOMY:
    una clase desconocida daria KeyError dentro del presupuesto, y un KeyError ahi
    termina rotulado PIPELINE_CRASH, que es el bug que este plan cierra.
    Clase desconocida -> False (conservador: no se recupera lo que no se entiende).
    """
    return bool(_CLASS_TO_TAXONOMY.get(recovery_class, {}).get("recoverable", False))


@dataclass(frozen=True)
class RecoveryVerdict:
    recovery_class: str
    reason_code: str
    route_used: str
    route_allowed: bool | None      # None = no se pudo evaluar
    health: object | None           # HealthProbe | None
    nav_code: str | None            # el codigo de navigation_driver si lo hubo
    evidence: str                   # 1 frase determinista de POR QUE esta clase
    taxonomy: dict                  # copia de _CLASS_TO_TAXONOMY[recovery_class]


def _verdict(clase: str, *, route_used: str, route_allowed: bool | None,
             health: object | None, nav_code: str | None,
             evidence: str) -> RecoveryVerdict:
    tax = dict(_CLASS_TO_TAXONOMY[clase])
    return RecoveryVerdict(
        recovery_class=clase,
        reason_code=tax["reason"] or clase,
        route_used=route_used,
        route_allowed=route_allowed,
        health=health,
        nav_code=nav_code,
        evidence=evidence,
        taxonomy=tax,
    )


def classify_recovery(
    *, exc: BaseException | None = None, exc_text: str = "",
    route_used: str = "", nav_code: str | None = None,
    health: object | None = None, route_allowed: bool | None = None,
) -> RecoveryVerdict:
    """Devuelve EXACTAMENTE una de las 5 clases, en el orden que pidio el operador."""
    # PASO 1 — capturar y registrar la ruta usada. No se decide nada todavia.
    ruta = (route_used or "").strip() or _RUTA_DESCONOCIDA
    texto = (exc_text or "").strip()
    if not texto and exc is not None:
        texto = f"{type(exc).__name__}: {exc}"

    def _mk(clase: str, evidence: str) -> RecoveryVerdict:
        return _verdict(clase, route_used=ruta, route_allowed=route_allowed,
                        health=health, nav_code=nav_code, evidence=evidence)

    # BORDE: sin excepcion ni texto no hay nada que clasificar. Inventar un fallo
    # funcional a partir de la nada es fabricar un veredicto.
    if not texto and nav_code is None:
        return _mk(UNRECOVERABLE, "sin excepcion ni texto: no hay nada que clasificar")

    # PASO 3 — el llamador ya midio la disponibilidad contra la URL base (INV-5).
    # BORDE: sin evidencia de salud NO se afirma ni caida ni fallo funcional.
    if health is None:
        return _mk(UNRECOVERABLE,
                   "sin evidencia de disponibilidad: no se afirma caida ni fallo funcional")

    alive = bool(getattr(health, "alive", False))
    samples = int(getattr(health, "samples", 1) or 1)

    # PASO 5 — NO responde.
    if not alive:
        if samples >= 2:
            return _mk(SERVICE_DOWN,
                       f"la aplicacion no respondio en {samples} muestras consecutivas")
        # v2/F1.5: una sola observacion no alcanza para gastar el unico arranque
        # de servicio del run.
        return _mk(UNRECOVERABLE, "probe sin confirmar: 1 muestra")

    # PASO 4 — SI responde.
    # 4a. La senal mas especifica gana: el driver miro la excepcion Y la URL actual.
    if nav_code and nav_code in _NAV_CODE_TO_CLASS:
        clase = _NAV_CODE_TO_CLASS[nav_code]
        evidencia = f"la aplicacion responde y el navegador reporto {nav_code}"
        if route_allowed is False:
            evidencia += (" (conflicto: la ruta tampoco pertenece a la allowlist; "
                          "gana el codigo del navegador)")
        return _mk(clase, evidencia)

    # 4b. Sin codigo y ruta fuera de la allowlist.
    if route_allowed is False:
        return _mk(ROUTE_ERROR,
                   f"la aplicacion responde y la ruta {ruta!r} esta fuera de la "
                   "allowlist declarada")

    # 4c. Sin codigo, ruta legal, y el texto huele a sesion perdida.
    bajo = texto.lower()
    if any(p in bajo for p in _SESSION_PATTERNS):
        return _mk(SESSION_ERROR,
                   "la aplicacion responde y el error menciona perdida de sesion")

    # 4d. La app esta viva, la ruta es legal, la navegacion no se quejo:
    # entonces la prueba fallo. Esto es un RESULTADO, no un incidente. INV-2.
    return _mk(FUNCTIONAL_ERROR,
               "la aplicacion responde, la ruta es legal y el navegador no reporto "
               "problemas: el fallo es de la prueba")
