"""
action_tracker.py — Tracker de acciones del pipeline, correlacionado por
``execution_id``. Emite eventos al bus (``pipeline_events``) y escribe logs
estructurados vía ``slog.action()`` / ``slog.error_classified()``.

API principal:

    with ActionContext(action="invoke_dev", ticket_id="0027698", phase="dev") as ac:
        ac.progress(25, "agent_typing")
        ...

    @track_action(action="scm_push", phase="deploy")
    def push(ticket_id, ...): ...

Responsabilidades:
    - Asignar ``execution_id`` (UUID4).
    - Heredar ``parent_execution_id`` desde el contexto padre (via ContextVar).
    - Emitir eventos ``action_started`` / ``action_progress`` / ``action_done``
      / ``action_error`` con la fase y detalle correspondientes.
    - Clasificar excepciones con ``error_classifier`` y generar ``user_friendly``.
    - **NUNCA propagar errores del tracker** al caller — toda emisión va en
      try/except silencioso. El log del flujo principal sigue siendo la fuente
      primaria; el tracker es observabilidad aditiva.
"""

from __future__ import annotations

import contextvars
import functools
import logging
import time
import uuid
from typing import Any, Callable, Literal, TypeVar

from pipeline_events import emit as _emit, new_execution_id
from error_classifier import classify_exception, friendly_message
from stacky_log import slog

logger = logging.getLogger("stacky.action_tracker")

T = TypeVar("T")

EventPhase = Literal["pm", "dev", "tester", "dba", "tl", "deploy", "sync", "other"]


# ── ContextVar para parent_execution_id ──────────────────────────────────────
# Usa contextvars para que el tracker herede el execution_id del caller
# incluso a través de ``threading.Thread`` (vía ``context.run``) y ``asyncio``.
_current_execution_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "stacky_current_execution_id", default=None,
)


def current_execution_id() -> str | None:
    """Retorna el ``execution_id`` de la ActionContext activa, o None."""
    return _current_execution_id.get()


# ── ActionContext ────────────────────────────────────────────────────────────

class ActionContext:
    """
    Context manager para trackear una acción con inicio/progreso/fin/error.

    Ejemplo::

        with ActionContext("invoke_dev", ticket_id="0027698", phase="dev") as ac:
            ac.progress(10, "workspace_ready")
            ...
            ac.progress(75, "agent_typing")

    - Al entrar emite ``action_started``.
    - Al salir sin excepción emite ``action_done`` con ``duration_ms``.
    - Al salir con excepción emite ``action_error`` con ``error_kind`` y
      ``user_friendly`` clasificados, y **no** suprime la excepción (re-raise).

    Si el tracker falla internamente (emit, clasificación, log), loguea a DEBUG
    y sigue — nunca rompe el caller.
    """

    def __init__(
        self,
        action: str,
        *,
        ticket_id: str | None = None,
        project: str | None = None,
        phase: EventPhase | None = None,
        parent_execution_id: str | None = None,
        execution_id: str | None = None,
        correlation: dict[str, str] | None = None,
        ticket_folder: str | None = None,
    ) -> None:
        self.action = action
        self.ticket_id = ticket_id
        self.project = project
        self.phase: EventPhase | None = phase
        self.correlation = dict(correlation or {})
        self.ticket_folder = ticket_folder

        self.execution_id = execution_id or new_execution_id()
        self.parent_execution_id = (
            parent_execution_id
            if parent_execution_id is not None
            else current_execution_id()
        )

        self._start_monotonic: float | None = None
        self._token: contextvars.Token[str | None] | None = None
        self._finished = False

    # ── Context manager protocol ──────────────────────────────────────────
    def __enter__(self) -> "ActionContext":
        self._start_monotonic = time.monotonic()
        self._token = _current_execution_id.set(self.execution_id)
        self._safe_emit_started()
        self._safe_log_action(detail="start")
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            if exc is None:
                self.done()
            else:
                self.error(exc)
        finally:
            if self._token is not None:
                try:
                    _current_execution_id.reset(self._token)
                except Exception:
                    pass
                self._token = None
        # No suprimimos excepciones
        return False

    # ── API pública ───────────────────────────────────────────────────────
    def progress(self, pct: int | None = None, subaction: str | None = None,
                 detail: str | None = None) -> None:
        """Emite un evento ``action_progress`` (opcionalmente con pct y subaction)."""
        self._safe_emit(
            kind="action_progress",
            pct=_clamp_pct(pct),
            subaction=subaction,
            detail=detail,
        )
        self._safe_log_action(
            subaction=subaction,
            detail=detail or (subaction or ""),
            pct=pct,
        )

    def done(self, detail: str | None = None) -> None:
        """Emite ``action_done`` con duration_ms. Idempotente."""
        if self._finished:
            return
        self._finished = True
        duration_ms = self._elapsed_ms()
        self._safe_emit(
            kind="action_done",
            duration_ms=duration_ms,
            detail=detail,
        )
        self._safe_log_action(detail=(detail or f"done ({duration_ms} ms)"), pct=100)

    def error(self, exc: BaseException, detail: str | None = None) -> None:
        """Emite ``action_error`` clasificando la excepción."""
        if self._finished:
            return
        self._finished = True
        duration_ms = self._elapsed_ms()
        try:
            kind = classify_exception(exc, ticket_folder=self.ticket_folder, action=self.action)
        except Exception:
            kind = "technical"
        try:
            friendly = friendly_message(
                exc, kind=kind, action=self.action, ticket_folder=self.ticket_folder,
            )
        except Exception:
            friendly = ""

        self._safe_emit(
            kind="action_error",
            duration_ms=duration_ms,
            error_kind=kind,
            message=str(exc)[:500],
            user_friendly=friendly,
            detail=detail,
        )
        try:
            slog.error_classified(
                self.execution_id, self.ticket_id or "-", self.action,
                kind, exc, friendly,
            )
        except Exception as tracker_err:  # pragma: no cover
            logger.debug("slog.error_classified falló: %s", tracker_err)

        # F3 — Persistir en NOTIFICATIONS.json con mensaje user-friendly.
        # Fire-and-forget: errores aquí no deben propagarse al caller.
        try:
            from notifier import notify as _notify
            _notify(
                title=f"Error en {self.action} — #{self.ticket_id or '-'}",
                message=friendly or str(exc)[:300],
                level="error",
                ticket_id=self.ticket_id or "",
            )
        except Exception as notify_err:  # pragma: no cover
            logger.debug("notify desde action_error falló: %s", notify_err)

    # ── Internals defensivos ──────────────────────────────────────────────
    def _elapsed_ms(self) -> int:
        if self._start_monotonic is None:
            return 0
        return int((time.monotonic() - self._start_monotonic) * 1000)

    def _safe_emit_started(self) -> None:
        self._safe_emit(kind="action_started", pct=0)

    def _safe_emit(self, *, kind: str, **kwargs: Any) -> None:
        try:
            _emit(
                kind=kind,  # type: ignore[arg-type]
                execution_id=self.execution_id,
                parent_execution_id=self.parent_execution_id,
                ticket_id=self.ticket_id,
                project=self.project,
                action=self.action,
                phase=self.phase,
                correlation=self.correlation,
                **kwargs,
            )
        except Exception as e:  # pragma: no cover
            logger.debug("ActionContext._safe_emit falló: %s", e)

    def _safe_log_action(self, *, subaction: str | None = None,
                         detail: str = "", pct: int | None = None) -> None:
        try:
            slog.action(
                self.execution_id,
                self.ticket_id or "-",
                self.action,
                phase=self.phase or "",
                detail=detail,
                pct=_clamp_pct(pct),
            )
        except Exception as e:  # pragma: no cover
            logger.debug("slog.action falló: %s", e)


def _clamp_pct(pct: int | None) -> int | None:
    if pct is None:
        return None
    try:
        p = int(pct)
    except (TypeError, ValueError):
        return None
    return max(0, min(100, p))


# ── Decorator ────────────────────────────────────────────────────────────────

def track_action(
    action: str,
    *,
    phase: EventPhase | None = None,
    ticket_id_arg: str = "ticket_id",
    project_arg: str = "project",
    folder_arg: str = "folder",
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator para envolver una función en una ``ActionContext`` automáticamente.

    Lee ``ticket_id``, ``project`` y ``folder`` de los kwargs si existen.
    Si la función recibe esos nombres como kwargs, se populan en el contexto.

    El tracker **nunca** rompe el callable: si algo del tracking falla, la
    función igual se ejecuta. Si la función levanta, el error se registra como
    ``action_error`` y se re-lanza.
    """
    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            tid = kwargs.get(ticket_id_arg)
            proj = kwargs.get(project_arg)
            folder = kwargs.get(folder_arg)
            try:
                ctx = ActionContext(
                    action=action,
                    phase=phase,
                    ticket_id=str(tid) if tid is not None else None,
                    project=str(proj) if proj is not None else None,
                    ticket_folder=str(folder) if folder is not None else None,
                )
            except Exception as e:
                logger.debug("track_action: no se pudo construir contexto: %s", e)
                return fn(*args, **kwargs)

            with ctx:
                return fn(*args, **kwargs)
        return wrapper
    return decorator
