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


# Plan 280 F1 — umbral de evidencia de trabajo. Es el MISMO que usa la consulta
# que midio el defecto sobre la BD viva (44 corridas en 'error' con
# length(output) > 200), y separa un output real de un eco de error.
WORK_EVIDENCE_MIN_CHARS = 200


def has_delivered_work(
    *,
    output: str = "",
    artifact_count: int = 0,
    result_ok_seen: bool = False,
    ticket_already_terminal: bool = False,
) -> bool:
    """¿Hay evidencia OBJETIVA de que el agente entregó trabajo?

    Riel G2: se prueba con el ARTEFACTO, no con el auto-reporte del agente. Un
    agente que dice "terminé" sin escribir nada no entregó nada.

    Las señales clásicas (`result_ok_seen`, `ticket_already_terminal`) se
    siguen respetando: son evidencia válida, solo que no son la ÚNICA. El
    aporte de este plan es que un output real también cuenta — que es lo que
    faltaba cuando el drenaje del stream vence antes de leer el `result`
    (claude_code_cli_runner.py:1559-1562) y `result_ok_seen` queda en False
    pese a haber trabajo en disco.
    """
    if result_ok_seen or ticket_already_terminal:
        return True
    if artifact_count > 0:
        return True
    return len((output or "").strip()) >= WORK_EVIDENCE_MIN_CHARS


# Estados desde los que la taxonomía PUEDE rescatar. Incluye 'failed' a
# propósito: no está en `status_vocabulary.VALID_TICKET_STATUSES` (que es el
# vocabulario del TICKET), pero sí es lo que los runners escriben en la FILA de
# ejecución vía `_mark_terminal(status="failed")`
# (claude_code_cli_runner.py:1829). La cohorte medida del defecto es
# `status IN ('error','failed')` — 38 de esas 109 filas son 'failed', y dejarlas
# afuera excluiría un tercio del rescate por construcción.
_RESCATABLES = frozenset({"error", "failed", "completed"})


def reconciliar_estado(actual: str, taxonomia: str) -> str:
    """Aplica la taxonomía como TECHO sobre el estado ya decidido por el runner.

    La taxonomía solo puede BAJAR a 'needs_review'. Jamás asciende nada.

      - error       + needs_review -> needs_review  (rescata el falso ROJO)
      - completed   + needs_review -> needs_review  (tapa el falso VERDE)
      - needs_review + completed   -> needs_review  (NO asciende)

    El último caso es el que obliga a que esto sea un techo y no una
    sustitución: la ejecución 210 tiene `reason=clean_exit` (la taxonomía diría
    'completed') pero su estado real es 'needs_review' porque
    `_evaluate_output_quality` la degradó por contrato. Sustituir la
    ascendería de vuelta y destruiría el gate de calidad.

    Riel G1: esta función NUNCA devuelve 'completed' si `actual` no lo era ya.
    Stacky no declara éxito por su cuenta.
    """
    if taxonomia == "needs_review" and actual in _RESCATABLES:
        return "needs_review"
    return actual


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
    work_delivered: bool = False,
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
      5. stall_fired y (result_ok o ticket terminal o work_delivered)
                                                        → stall_after_work
      6. stall_fired                                    → stall_no_work
      7. return_code == 0                               → clean_exit
      8. result_ok_seen o ticket_already_terminal o work_delivered
                                                        → dirty_exit_after_work
      9. resto                                          → cli_failure

    Plan 280 F1 — `work_delivered` entra en las reglas 5 y 8. Antes, esta
    función RECIBÍA el output (`last_result_text`) y solo lo miraba para buscar
    marcadores de cuota: la regla 8 decidía "hubo trabajo" mirando únicamente
    proxies del proceso. Cuando el drenaje del stream vence, `result_ok_seen`
    queda en False aunque el archivo ya esté escrito, y una corrida entregada
    caía en `cli_failure` (ejecución 212: 19.593 chars → 'error').

    El default `False` preserva a cualquier call-site no migrado (C9 del 254).
    """
    if preflight_block:
        return "preflight_blocked"
    if reaper_kind == "timeout_guardian":
        return "reaper_timeout"
    if reaper_kind:
        return "reaper_heartbeat"
    if _has_quota_marker(stderr_excerpt, last_result_text):
        return "quota_exhausted"
    # Plan 280 F1 — el trabajo entregado, explícito o DERIVADO del texto que esta
    # función ya recibía. La derivación es la que le da la corrección GRATIS a los
    # call-sites que hoy pasan `last_result_text` pero no `work_delivered`
    # (codex_cli_runner.py:804), sin tocar su código.
    _trabajo = work_delivered or has_delivered_work(
        output=last_result_text,
        result_ok_seen=result_ok_seen,
        ticket_already_terminal=ticket_already_terminal,
    )
    if stall_fired and _trabajo:
        return "stall_after_work"
    if stall_fired:
        return "stall_no_work"
    if return_code == 0:
        return "clean_exit"
    if _trabajo:
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
