"""Plan 254 F2 — taxonomía de desenlaces de una corrida (`outcome_reason`).

Módulo PURO: sin DB, sin red, sin imports de `db`/`models`. Se testea solo.

El operador hoy ve `error` para seis causas radicalmente distintas — cuota del
plan agotada, repo ausente, sesión ociosa tras entregar, timeout del reaper,
heartbeat viejo y fallo real del CLI — y las acciones correctas son OPUESTAS.
Este módulo las separa con reglas deterministas y un orden de precedencia
explícito, para que ni un modelo menor pueda resolverlo de dos maneras.
"""
from __future__ import annotations

OUTCOME_REASONS = (
    "clean_exit",             # rc == 0
    "dirty_exit_after_work",  # rc != 0 PERO hubo result ok / ticket ya terminal
    "quota_exhausted",        # "session limit", "rate limit", "quota"
    "stall_after_work",       # watchdog disparó con result ok previo
    "stall_no_work",          # watchdog disparó sin nada entregado  → fallo real
    "preflight_blocked",      # G0.1 gate: repo_missing, etc.
    "reaper_timeout",         # timeout_guardian
    "reaper_heartbeat",       # heartbeat_stale
    "cli_failure",            # rc != 0 sin evidencia de trabajo → fallo real
)

_QUOTA_MARKERS = ("session limit", "rate limit", "quota", "usage limit")

# Reasons donde el operador NO puede hacer nada distinto de esperar.
_NOT_ACTIONABLE = frozenset({"quota_exhausted", "clean_exit"})

# Mapa reason → estado terminal. SOLO estados de status_vocabulary.
# `dirty_exit_after_work` y `stall_after_work` van a 'needs_review', NUNCA a
# 'completed': hay trabajo entregado pero el cierre fue sucio, y eso lo mira un
# humano. Stacky no declara éxito por su cuenta.
_REASON_TO_STATUS = {
    "clean_exit": "completed",
    "dirty_exit_after_work": "needs_review",
    "quota_exhausted": "error",
    "stall_after_work": "needs_review",
    "stall_no_work": "error",
    "preflight_blocked": "error",
    "reaper_timeout": "error",
    "reaper_heartbeat": "error",
    "cli_failure": "error",
}


def _has_quota_marker(*texts: str) -> bool:
    for text in texts:
        low = (text or "").lower()
        if any(marker in low for marker in _QUOTA_MARKERS):
            return True
    return False


def classify_outcome_reason(
    *,
    return_code: int | None,
    result_ok_seen: bool = False,
    stall_fired: bool = False,
    stderr_excerpt: str = "",
    last_result_text: str = "",
    ticket_already_terminal: bool = False,
    reaper_kind: str | None = None,
    preflight_block: str | None = None,
) -> str:
    """Devuelve exactamente uno de OUTCOME_REASONS. Puro y determinístico.

    Todo parámetro salvo `return_code` tiene default, para que un call-site que
    no puede computar una entrada NO rompa (C9). Nunca devuelve None.

    ORDEN DE PRECEDENCIA OBLIGATORIO — se evalúa en este orden y se devuelve en
    el PRIMER match (sin esto, dos reglas pueden matchear y el resultado es
    ambiguo para un modelo menor):

      1. preflight_block no vacío                       → preflight_blocked
      2. reaper_kind == "timeout_guardian"              → reaper_timeout
      3. reaper_kind no vacío (cualquier otro)          → reaper_heartbeat
      4. marcador de cuota en stderr o último result    → quota_exhausted
      5. stall_fired y (result_ok o ticket terminal)    → stall_after_work
      6. stall_fired                                    → stall_no_work
      7. return_code == 0                               → clean_exit
      8. result_ok_seen o ticket_already_terminal       → dirty_exit_after_work
      9. resto                                          → cli_failure
    """
    if preflight_block:
        return "preflight_blocked"
    if reaper_kind == "timeout_guardian":
        return "reaper_timeout"
    if reaper_kind:
        return "reaper_heartbeat"
    if _has_quota_marker(stderr_excerpt, last_result_text):
        return "quota_exhausted"
    if stall_fired and (result_ok_seen or ticket_already_terminal):
        return "stall_after_work"
    if stall_fired:
        return "stall_no_work"
    if return_code == 0:
        return "clean_exit"
    if result_ok_seen or ticket_already_terminal:
        return "dirty_exit_after_work"
    return "cli_failure"


def is_operator_actionable(reason: str) -> bool:
    """True si el operador puede hacer algo distinto de reintentar.

    quota_exhausted → False (esperar). cli_failure → True (mirar el error).
    Un `reason` desconocido devuelve True (mejor molestar que ocultar).
    """
    return reason not in _NOT_ACTIONABLE


def outcome_reason_to_status(reason: str) -> str:
    """Mapa reason → estado terminal: 'completed' | 'needs_review' | 'error'.

    Solo devuelve estados de status_vocabulary.VALID_TICKET_STATUSES.
    dirty_exit_after_work y stall_after_work → 'needs_review', NUNCA 'completed'
    automático: el trabajo existe pero el cierre fue sucio, y eso lo mira un
    humano. Un reason desconocido cae a 'needs_review' (nunca a un verde).
    """
    return _REASON_TO_STATUS.get(reason, "needs_review")
