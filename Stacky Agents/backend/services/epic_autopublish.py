"""Plan 278 — publicador UNICO de la Epica/Issue del brief, agnostico de runtime.

Antes de este plan el autopublish vivia dentro de un closure del finalizador de
`services/claude_code_cli_runner.py` (`_maybe_autopublish_epic`), asi que SOLO
Claude Code CLI podia crear una epica desde un brief; Codex CLI y GitHub Copilot
eran rechazados con un 400 por runtime antes de arrancar (el literal de ese error
ya no aparece en codigo de produccion: es el gate de residuo del Plan 278 F4).

Ahora corre como post-hook de `ticket_status.on_execution_end`, que es el
chokepoint que los 3 runtimes ya disparan (claude_code_cli_runner, codex_cli_runner,
agent_runner in-proc). Mismo camino de codigo para los 3, sin ramas `if runtime ==`.

Paridad de MECANISMO, no de calidad: si el modelo devuelve narracion en vez del
HTML de la epica, el publicador falla RUIDOSO con `epic_not_in_output` ->
`needs_review`, igual en los 3 runtimes. F6-bis sella `epic_publish` para que esa
diferencia sea medible desde la UI.

EXCEPCION DURA #1, aceptada por directiva del operador (mismo precedente que
`services/incident_autopublish.py:1-4`): el autopublish desde brief YA existia y
YA era automatico para Claude. Este plan no amplia la autonomia, la vuelve uniforme.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger("stacky.services.epic_autopublish")

# Clave del claim atomico (Plan 278 F2-bis). Distinta del sello del resultado:
# el sello registra QUE paso; el claim evita la CARRERA.
_CLAIM_KEY = "epic_publish_claim"

# Estados terminales en los que tiene sentido intentar publicar. `error` y
# `cancelled` no: no hay epica que publicar.
_PUBLISHABLE_STATUSES = ("completed", "needs_review")


# ── lectura ───────────────────────────────────────────────────────────────────

def _retry(fn, label: str):
    """Reintenta una unidad de trabajo COMPLETA ante lock de SQLite (db.py:178).

    Este hook corre en el chokepoint que los 3 runtimes disparan, y `on_execution_end`
    puede llegar desde dos hilos a la vez sobre la MISMA fila (el runner en su hilo
    de fondo y el gateway de completion dentro del request HTTP de Flask). Ese es
    justamente el escenario que produce `database table is locked`. Sin reintento
    el lock no rompe nada visible —`_run_post_hooks` se traga la excepcion— pero
    la epica NO se publica y el operador solo ve un warning: un falso verde.

    Cada helper de abajo abre su propia sesion, como exige run_with_retry.
    """
    from db import run_with_retry
    return run_with_retry(fn, label=f"epic_autopublish.{label}")


def _load_run(execution_id: int) -> dict | None:
    return _retry(lambda: _load_run_once(execution_id), "_load_run")


def _load_run_once(execution_id: int) -> dict | None:
    """Lee de la fila todo lo que el publicador necesita, en UNA transaccion."""
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            return None
        project_name = None
        ticket = session.get(Ticket, row.ticket_id)
        if ticket is not None:
            project_name = ticket.stacky_project_name
        return {
            "output": row.output,
            "metadata": dict(row.metadata_dict or {}),
            "input_context": list(row.input_context or []),
            "started_at": row.started_at,
            "project_name": project_name,
        }


def _run_started_at(md: dict, started_at) -> float | None:
    """min_mtime del rescate desde disco (api/tickets.py: 'solo artefactos de ESTA run').

    El runner sella `spawn_epoch` justo antes de lanzar el proceso
    (claude_code_cli_runner.py, Plan 278 F1-bis). Derivarlo de
    `AgentExecution.started_at` amplia la ventana HACIA ATRAS (la fila se crea
    mucho antes del spawn) y habilitaria rescatar un artefacto de otra run.
    """
    v = md.get("spawn_epoch")
    if isinstance(v, (int, float)):
        return float(v)                      # camino normal: identico a hoy
    if started_at is None:
        return None
    # Fallback SOLO para runs viejas o runtimes que no sellan spawn_epoch.
    # utcnow() es naive: hay que declarar UTC o el epoch sale desplazado
    # (en Windows, horas de desfase).
    return started_at.replace(tzinfo=timezone.utc).timestamp()


# ── claim atomico (F2-bis) ────────────────────────────────────────────────────

def _claim(execution_id: int) -> bool:
    """True solo para el PRIMER llamador. Atomico: UN solo UPDATE condicional.

    No usa read-modify-write: `on_execution_end` puede dispararse mas de una vez
    para la misma ejecucion desde hilos distintos (el runner en su hilo de fondo,
    el gateway de completion dentro del request HTTP de Flask, y
    scripts/rescue_execution.py). Dos hilos leerian los dos el sello vacio y
    publicarian los dos => DOS epicas en el tracker real del operador.

    Va envuelto en `run_with_retry` (db.py:178) porque el escenario que este
    claim existe para cubrir —dos hilos sobre la MISMA fila— es exactamente el
    que produce `database table is locked` en SQLite. Sin el reintento, el
    perdedor no se va en silencio: explota. `_claim_once` abre su propia
    transaccion en cada intento, como exige el contrato de run_with_retry.
    """
    return _retry(lambda: _claim_once(execution_id), "_claim")


def _claim_once(execution_id: int) -> bool:
    import json
    from sqlalchemy import text
    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            return False
        md = dict(row.metadata_dict or {})
        if md.get(_CLAIM_KEY):
            return False                      # ya reclamado (chequeo barato previo)
        md[_CLAIM_KEY] = {"at": datetime.utcnow().isoformat(), "by": "epic_autopublish"}
        payload = json.dumps(md, ensure_ascii=False)
        res = session.execute(
            text(
                "UPDATE agent_executions SET metadata_json = :md "
                "WHERE id = :eid "
                "AND (metadata_json IS NULL OR metadata_json NOT LIKE :probe)"
            ),
            {"md": payload, "eid": execution_id, "probe": f'%"{_CLAIM_KEY}"%'},
        )
        return res.rowcount == 1              # el perdedor ve 0 y se va en silencio


# ── escritura ─────────────────────────────────────────────────────────────────

def _merge_metadata(execution_id: int, updates: dict) -> None:
    if not updates:
        return
    _retry(lambda: _merge_metadata_once(execution_id, updates), "_merge_metadata")


def _merge_metadata_once(execution_id: int, updates: dict) -> None:
    """Leer-modificar-escribir MERGEANDO sobre metadata_dict.

    Nunca reemplaza el dict entero: el runner ya escribio ahi `runtime`,
    `work_item_type`, `spawn_epoch`, `epic_convergence`, `confidence`, etc.
    """
    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            return
        md = dict(row.metadata_dict or {})
        md.update(updates)
        row.metadata_dict = md


def _degrade_execution_row(execution_id: int, error_text: str) -> None:
    _retry(lambda: _degrade_execution_row_once(execution_id, error_text),
           "_degrade_execution_row")


def _degrade_execution_row_once(execution_id: int, error_text: str) -> None:
    """Capa 1: la FILA. Hoy esto lo hace _mark_terminal(status='needs_review')
    en el runner. Sin esto, la fila queda 'completed' mientras el ticket dice
    'needs_review': incoherencia observable en /api/executions, en el
    output_watcher y en recover_stale_running_tickets."""
    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None or row.status not in ("completed",):
            return                       # no pisar error/cancelled ya escritos
        row.status = "needs_review"
        md = dict(row.metadata_dict or {})
        try:
            from harness.failure import classify      # paridad con _mark_terminal
            kind = classify(return_code=md.get("return_code"),
                            error_message=error_text,
                            metadata={**md, "status": "needs_review"})
            if kind is not None:
                md["failure_kind"] = kind
        except Exception:                              # noqa: BLE001
            logger.debug("[exec=%s] failure classify fallo", execution_id, exc_info=True)
        row.metadata_dict = md


def _degrade_ticket(ticket_id: int, execution_id: int, agent_type, error_text: str) -> None:
    """Capa 2: el TICKET.

    Usa `set_status`, NUNCA `on_execution_end`: este hook corre DENTRO de
    `_run_post_hooks`, asi que volver a llamar `on_execution_end` re-dispararia
    todos los post-hooks incluido este => recursion / doble publicacion.
    """
    from services import ticket_status
    ticket_status.set_status(
        ticket_id,
        "needs_review",
        changed_by="system:epic_autopublish",   # OBLIGATORIO: keyword-only sin default
        execution_id=execution_id,
        agent_type=agent_type,
        reason=f"autopublish de la epica fallo: {error_text}"[:500],
        guard_downgrade=False,                  # EXPLICITO. El guard del Plan 254 F1
    )                                           # solo bloquea completed->error; no
                                                # bloquearia esto, pero se declara.


def _error_kind(error_text: str, *, from_exception: bool) -> str:
    """Deriva el tipo de fallo del PREFIJO del error, sin parsear el texto entero."""
    if from_exception:
        return "exception"
    if str(error_text or "").startswith("epic_not_in_output"):
        return "epic_not_in_output"
    return "ado_error"


def _publish_seal(md: dict, *, outcome: str, error_kind: str | None,
                  recovery_method: str | None) -> dict:
    """F6-bis — bloque compacto que vuelve MEDIBLE la paridad de mecanismo.

    Aditivo: es una clave mas en metadata_dict, que la UI de la run ya renderiza.
    Sin flag nueva, sin endpoint nuevo, sin pantalla nueva.
    """
    return {
        "runtime": md.get("runtime"),
        "work_item_type": md.get("work_item_type") or "Epic",
        "outcome": outcome,
        "error_kind": error_kind,
        "recovery_method": recovery_method,
        "at": datetime.utcnow().isoformat(),
    }


def _seal_and_degrade(execution_id: int, ticket_id: int, agent_type, *,
                      error: str, from_exception: bool = False,
                      recovery_method: str | None = None,
                      md: dict | None = None) -> None:
    """Fallo RUIDOSO: sella el error y degrada las DOS capas (fila + ticket)."""
    _merge_metadata(execution_id, {
        "epic_publish_error": error,
        "epic_publish": _publish_seal(
            md or {}, outcome="failed",
            error_kind=_error_kind(error, from_exception=from_exception),
            recovery_method=recovery_method),
    })
    _degrade_execution_row(execution_id, error)
    try:
        _degrade_ticket(ticket_id, execution_id, agent_type, error)
    except Exception:  # noqa: BLE001 — el hook nunca tumba el chokepoint
        logger.warning("[exec=%s] degradacion del ticket fallo", execution_id, exc_info=True)


def _apply_result(execution_id: int, ticket_id: int, agent_type, res,
                  seal_key: str, is_issue: bool, md: dict) -> None:
    """Reproduce el contrato de sellado del closure del runner (9 filas)."""
    if res.error is not None:
        # Fallo RUIDOSO: el WI NO se creo -> needs_review visible.
        logger.error("autopublish: publicacion fallo -> needs_review: %s", res.error)
        _seal_and_degrade(execution_id, ticket_id, agent_type, error=res.error,
                          recovery_method=getattr(res, "recovery_method", None), md=md)
        return

    updates: dict = {}
    if res.ado_id is not None:
        # Exito, o ya publicada (skipped): en los dos casos se (re)afirma el sello.
        updates[seal_key] = res.ado_id
    if res.grounding_warnings:
        updates["grounding_warnings"] = res.grounding_warnings
    if res.epic_summary is not None:
        updates["epic_summary"] = res.epic_summary
    if res.recovery_method:
        updates["epic_recovery"] = res.recovery_method
    # Plan 60 F1 — baseline del aprendizaje bidireccional. Sin esto, el diff de
    # las ediciones del operador deja de funcionar (regresion silenciosa).
    if not is_issue and not res.skipped:
        if res.published_html is not None:
            updates["epic_baseline_html"] = res.published_html
        if res.baseline_rev is not None:
            updates["epic_baseline_rev"] = res.baseline_rev
    updates["epic_publish"] = _publish_seal(
        md, outcome="skipped" if res.skipped else "published",
        error_kind=None, recovery_method=getattr(res, "recovery_method", None))
    _merge_metadata(execution_id, updates)


# ── el hook ───────────────────────────────────────────────────────────────────

def maybe_autopublish_epic(*, ticket_id, execution_id, final_status, agent_type,
                           error=None, **_) -> None:
    from config import config as _cfg
    if not getattr(_cfg, "STACKY_EPIC_AUTOPUBLISH_BACKEND", True):
        return
    if (agent_type or "").lower() != "business":
        return
    if final_status not in _PUBLISHABLE_STATUSES:
        return            # error / cancelled / no terminal: nada que publicar

    run = _load_run(execution_id)
    if run is None:
        return
    brief_text = next((str(b.get("content") or "")
                       for b in run["input_context"]
                       if isinstance(b, dict) and b.get("id") == "brief"), None)
    if brief_text is None:
        return            # no es un run brief->epica (chat interactivo): NO publicar

    md = dict(run["metadata"] or {})
    is_issue = (str(md.get("work_item_type") or "Epic") == "Issue"
                and getattr(_cfg, "STACKY_ISSUE_FROM_BRIEF_ENABLED", False))
    seal_key = "issue_ado_id" if is_issue else "epic_ado_id"
    if md.get(seal_key):
        return            # ya publicada: idempotente (2a linea de defensa)

    if not _claim(execution_id):   # F2-bis: 1a linea, ATOMICA
        return

    try:
        from api.tickets import autopublish_epic_from_run, publish_issue_from_run
    except Exception as exc:  # noqa: BLE001
        logger.warning("autopublish: import fallo (no critico): %s", exc)
        return
    publish = publish_issue_from_run if is_issue else autopublish_epic_from_run
    kwargs = dict(output=run["output"], brief=brief_text,
                  project_name=run["project_name"], already_published_id=md.get(seal_key))
    if not is_issue:
        # publish_issue_from_run NO acepta run_started_at (api/tickets.py:7695).
        kwargs["run_started_at"] = _run_started_at(md, run["started_at"])

    try:
        res = publish(**kwargs)
    except Exception as exc:                      # noqa: BLE001 — nunca tumbar el chokepoint
        logger.error("autopublish: error inesperado: %s", exc)
        _seal_and_degrade(execution_id, ticket_id, agent_type, error=str(exc),
                          from_exception=True, md=md)
        return
    _apply_result(execution_id, ticket_id, agent_type, res, seal_key, is_issue, md)


def register(register_post_hook) -> None:
    register_post_hook(maybe_autopublish_epic)


# ── superficie publica para el OTRO escritor del mismo hecho ──────────────────
#
# `POST /api/tickets/epics/from-brief` (api/tickets.py:7958) publica la MISMA
# epica que este post-hook. Son dos escritores del mismo hecho, y hasta ahora no
# se conocian: el endpoint no tenia idempotencia NINGUNA y toda la defensa vivia
# en un `if` del navegador. Estos tres helpers le dan al endpoint el mismo
# registro de idempotencia (el sello) y el MISMO claim atomico que usa el hook,
# para que la exclusion sea real y no un check-then-act de cada lado.

_SEAL_KEYS = ("epic_ado_id", "issue_ado_id")


def sealed_work_item_id(execution_id: int) -> int | None:
    """El id de la epica/issue YA publicada para esta run, o None.

    Tolera el sello guardado como string: los providers no-ADO normalizan los ids
    del tracker a str (gitlab_provider.py:131-132) y las runs viejas de GitLab
    quedaron con el sello estringado. Un `isinstance(v, int)` acá revive
    exactamente la doble publicacion que este modulo existe para evitar.
    """
    run = _load_run(execution_id)
    if run is None:
        return None
    md = run["metadata"] or {}
    for key in _SEAL_KEYS:
        valor = md.get(key)
        if isinstance(valor, bool):          # `True` no es un id
            continue
        if isinstance(valor, int):
            return valor or None
        if isinstance(valor, str) and valor.strip():
            try:
                return int(valor) or None
            except ValueError:
                continue
    return None


def claim_publication(execution_id: int) -> bool:
    """True solo para el PRIMER escritor. MISMA clave que usa el post-hook, a
    proposito: si el hook ya esta publicando, el endpoint tiene que quedarse afuera."""
    return _claim(execution_id)


def release_claim(execution_id: int) -> None:
    """Devuelve el claim cuando la publicacion FALLO.

    Sin esto, un 502 del tracker dejaria la run marcada como reclamada para
    siempre y ni el operador ni el post-hook podrian reintentar: la epica no
    existiria y nadie volveria a intentarlo. Solo se llama en el camino de error,
    nunca despues de un exito.
    """
    def _once() -> None:
        from db import session_scope
        from models import AgentExecution

        with session_scope() as session:
            row = session.get(AgentExecution, execution_id)
            if row is None:
                return
            md = dict(row.metadata_dict or {})
            if md.pop(_CLAIM_KEY, None) is None:
                return
            row.metadata_dict = md

    _retry(_once, "release_claim")


def seal_published(execution_id: int, ado_id: int, *, is_issue: bool = False) -> None:
    """Sella el resultado en la MISMA clave que lee el post-hook (`:326-328`).

    Si el endpoint publicara sin sellar, el post-hook correria despues, no veria
    sello y publicaria una SEGUNDA epica: el bug de origen, con los papeles
    invertidos.
    """
    _merge_metadata(execution_id, {
        "issue_ado_id" if is_issue else "epic_ado_id": int(ado_id),
        "epic_publish": _publish_seal({}, outcome="published", error_kind=None,
                                      recovery_method="published_by_endpoint"),
    })
