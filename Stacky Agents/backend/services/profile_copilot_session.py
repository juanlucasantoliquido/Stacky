"""Plan 296 F3 - La sesion del copiloto del perfil, como maquina de estados.

PURO: sin flask, sin config, sin IO, sin red, sin modelo. Calca la disciplina de
services/pipeline_session.py (dataclass frozen + estados cerrados + funciones que
NUNCA lanzan).

P8 - SIN PERSISTENCIA NUEVA: la sesion viaja en el request/response y el
frontend la devuelve tal cual la recibio. No se crea ninguna tabla, ningun
archivo de estado, ningun cache global. Lo UNICO que se persiste es la eleccion
de runtime, y por el riel que ya existe (runtime_capabilities.save_run_preference).

P4 - FALLBACK DE CAPACIDAD SI; FALLBACK DE RUNTIME JAMAS. `elegir_runtime` es el
candado: sin bandera explicita del usuario el runtime NO cambia, ni siquiera
cuando el elegido falla.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from services.runtime_capabilities import RUNTIMES

SESSION_VERSION = "1"
MAX_SESSION_BYTES = 8192   # espejo de pipeline_session.py:11
MAX_PREGUNTAS = 40         # tope duro de turnos de una sesion

#: Los 7 estados. Cerrado: nada fuera de esta tupla es un estado valido.
PROFILE_SESSION_STATES = (
    "eleccion_runtime",  # 1. todavia no eligio runtime - NADA arranca antes
    "diagnostico",       # 2. runtime elegido; se leyo el perfil y se sabe que falta
    "preguntando",       # 3. hay una pregunta abierta
    "propuesta",         # 4. hay un diff armado y visible
    "confirmando",       # 5. esperando confirmacion explicita
    "aplicado",          # 6. terminal - el perfil quedo escrito
    "detenido",          # 7. terminal - con causa declarada
)

TRANSITIONS: dict[str, tuple[str, ...]] = {
    "eleccion_runtime": ("diagnostico", "detenido"),
    "diagnostico":      ("preguntando", "propuesta", "detenido"),
    "preguntando":      ("preguntando", "propuesta", "detenido"),
    "propuesta":        ("confirmando", "preguntando", "detenido"),
    "confirmando":      ("aplicado", "propuesta", "detenido"),
    "aplicado":         (),
    "detenido":         (),
}

TERMINAL_STATES = ("aplicado", "detenido")


@dataclass(frozen=True)
class ProfileCopilotSession:
    state: str = "eleccion_runtime"
    proyecto: str = ""
    runtime_elegido: str = ""              # uno de runtime_capabilities.RUNTIMES
    tracker_type: str = ""
    pregunta_actual: str = ""              # id de Pregunta
    respondidas: tuple[str, ...] = ()
    respuestas: tuple[tuple[str, str], ...] = ()   # (id_pregunta, texto)
    patch_ref: str = ""                    # hash del diff, NUNCA el diff entero
    turnos: int = 0
    motivo_detencion: str = ""
    version: str = SESSION_VERSION


def can_transition(origen: str, destino: str) -> bool:
    """True si la transicion es legal. NUNCA lanza."""
    try:
        destinos = TRANSITIONS.get(str(origen or ""), ())
    except Exception:  # pragma: no cover - defensa, no camino esperado
        return False
    return str(destino or "") in destinos


def advance(
    session: ProfileCopilotSession, destino: str, **campos
) -> tuple[ProfileCopilotSession, str]:
    """(sesion_nueva, "") si la transicion es legal; (sesion_original, motivo) si
    no. NUNCA lanza. Motivos: "estado_terminal", "transicion_ilegal",
    "error_interno" - los MISMOS literales de pipeline_session.advance."""
    try:
        origen = getattr(session, "state", "") or ""
        if origen in TERMINAL_STATES:
            return session, "estado_terminal"
        if not can_transition(origen, destino):
            return session, "transicion_ilegal"
        validos = {
            k: v for k, v in (campos or {}).items()
            if k in ProfileCopilotSession.__dataclass_fields__ and k != "state"
        }
        return replace(session, state=destino, **validos), ""
    except Exception:  # pragma: no cover - defensa: NUNCA lanza
        return session, "error_interno"


def session_to_dict(s: ProfileCopilotSession) -> dict:
    """Serializacion 1:1, json.dumps-able sin encoder custom."""
    return {
        "state": s.state,
        "proyecto": s.proyecto,
        "runtime_elegido": s.runtime_elegido,
        "tracker_type": s.tracker_type,
        "pregunta_actual": s.pregunta_actual,
        "respondidas": list(s.respondidas),
        "respuestas": [list(par) for par in s.respuestas],
        "patch_ref": s.patch_ref,
        "turnos": s.turnos,
        "motivo_detencion": s.motivo_detencion,
        "version": s.version,
    }


def _txt(d: dict, key: str) -> str:
    v = d.get(key, "")
    return v if isinstance(v, str) else ""


def _tup(d: dict, key: str) -> tuple[str, ...]:
    v = d.get(key)
    if not isinstance(v, (list, tuple)):
        return ()
    return tuple(str(x) for x in v)


def _pares(d: dict, key: str) -> tuple[tuple[str, str], ...]:
    v = d.get(key)
    if not isinstance(v, (list, tuple)):
        return ()
    salida: list[tuple[str, str]] = []
    for item in v:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            salida.append((str(item[0]), str(item[1])))
    return tuple(salida)


def session_from_dict(d: dict | None) -> ProfileCopilotSession:
    """Tolerante: cualquier dict invalido devuelve la sesion por defecto.
    Ignora claves desconocidas. NUNCA lanza."""
    if not isinstance(d, dict):
        return ProfileCopilotSession()
    try:
        estado = d.get("state")
        if not isinstance(estado, str) or estado not in PROFILE_SESSION_STATES:
            return ProfileCopilotSession()
        turnos = d.get("turnos", 0)
        return ProfileCopilotSession(
            state=estado,
            proyecto=_txt(d, "proyecto"),
            runtime_elegido=_txt(d, "runtime_elegido"),
            tracker_type=_txt(d, "tracker_type"),
            pregunta_actual=_txt(d, "pregunta_actual"),
            respondidas=_tup(d, "respondidas"),
            respuestas=_pares(d, "respuestas"),
            patch_ref=_txt(d, "patch_ref"),
            turnos=turnos if isinstance(turnos, int) and not isinstance(turnos, bool) else 0,
            motivo_detencion=_txt(d, "motivo_detencion"),
            version=_txt(d, "version") or SESSION_VERSION,
        )
    except Exception:  # pragma: no cover - defensa: NUNCA lanza
        return ProfileCopilotSession()


def elegir_runtime(
    s: ProfileCopilotSession, runtime: str, *, explicito: bool
) -> tuple[ProfileCopilotSession, str]:
    """La regla que materializa P4. NUNCA lanza.

    Motivos posibles: "" (ok), "runtime_desconocido",
    "cambio_de_runtime_requiere_confirmacion", y los de `advance`.
    """
    try:
        if runtime not in RUNTIMES:
            return s, "runtime_desconocido"
        if s.runtime_elegido and s.runtime_elegido != runtime and not explicito:
            # El candado. Sin bandera explicita del usuario NO se cambia. Ni en fallo.
            return s, "cambio_de_runtime_requiere_confirmacion"
        if s.state == "eleccion_runtime":
            return advance(s, "diagnostico", runtime_elegido=runtime)
        return replace(s, runtime_elegido=runtime), ""
    except Exception:  # pragma: no cover - defensa: NUNCA lanza
        return s, "error_interno"
