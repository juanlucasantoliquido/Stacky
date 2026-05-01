"""
ticket_completion_flow.py — Orquestador del flujo de finalización de ticket.

Se ejecuta después de que el usuario confirma el commit desde el Dashboard
("Git Commit" en el modal). Ejecuta, en orden y con flags independientes:

  1. ``auto_commit``           — delega en ``scm_provider.factory.get_scm`` +
                                 ``GitProvider.commit()`` (que YA inserta el
                                 trailer ``AB#<ticket_id>``).
  2. ``auto_transition_state`` — transición ADO al ``target_state``
                                 configurado vía
                                 ``IssueProvider.transition_state``.
  3. ``auto_post_note``        — publica nota/comentario vía
                                 ``IssueProvider.add_comment`` usando el
                                 template configurado con placeholders.

Cada paso:
  - Respeta su propio flag ``enabled`` (si está apagado, NO se ejecuta).
  - Loguea éxito/fallo en stderr y en el notifier.
  - NO interrumpe los pasos siguientes ante un error — devuelve un dict con
    el detalle de cada paso para que el caller pueda decidir qué mostrar.

Diseño:
  - El commit corre sincrónico (necesitamos su ``revision`` para el render
    de la nota).
  - Transición ADO + nota corren en un thread daemon para no bloquear al UI.
  - Si ``auto_commit`` está ON pero el commit falla, los pasos 2 y 3 NO se
    ejecutan (invariante: no se publica nota si el código no se commiteó).
  - Si ``auto_commit`` está OFF, los pasos 2 y 3 sí corren — asume que el
    usuario commiteó por fuera.

Uso (desde dashboard_server.api_git_commit)::

    from ticket_completion_flow import run_completion_flow
    result = run_completion_flow(
        ticket_id="27698",
        workspace="N:/GIT/RS/RSPacifico/trunk",
        message="[BUG] #27698 — fix validación",
        files=["a.cs", "b.sql"],
        project_name="RSPACIFICO",
    )
"""

from __future__ import annotations

import logging
import sys
import threading
from dataclasses import dataclass, field

from ticket_completion_config import (
    CompletionConfig,
    load_completion_config,
    render_note_template,
)

logger = logging.getLogger("stacky.ticket_completion_flow")


@dataclass
class StepResult:
    step: str
    enabled: bool
    ok: bool = False
    detail: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {"step": self.step, "enabled": self.enabled, "ok": self.ok, "detail": self.detail}
        d.update(self.extra)
        return d


@dataclass
class FlowResult:
    ok: bool
    revision: str = ""
    commit_message: str = ""
    steps: list[StepResult] = field(default_factory=list)
    config: dict = field(default_factory=dict)
    files: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "ok":             self.ok,
            "revision":       self.revision,
            "commit_message": self.commit_message,
            "steps":          [s.to_dict() for s in self.steps],
            "config":         self.config,
            "files":          self.files,
            "error":          self.error,
        }


# ── Paso 1: commit ────────────────────────────────────────────────────────────

def _do_commit(ticket_id: str, workspace: str, message: str,
               files: list[str], project_name: str | None) -> StepResult:
    try:
        from scm_provider.factory import get_scm
    except Exception as e:
        return StepResult(step="auto_commit", enabled=True, ok=False,
                          detail=f"scm_provider no disponible: {e}")
    try:
        scm = get_scm(project_name=project_name, workspace=workspace)
        commit_res = scm.commit(workspace, message, files=files, work_item_id=ticket_id)
        return StepResult(
            step="auto_commit",
            enabled=True,
            ok=bool(commit_res.ok),
            detail=(commit_res.error or "") if not commit_res.ok else "",
            extra={
                "revision": commit_res.revision or "",
                "files": commit_res.files or files,
            },
        )
    except Exception as e:
        return StepResult(step="auto_commit", enabled=True, ok=False,
                          detail=f"Excepción al commitear: {e}")


# ── Paso 2: transición ADO ────────────────────────────────────────────────────

def _do_transition(ticket_id: str, project_name: str | None,
                   target_state: str) -> StepResult:
    if not target_state:
        return StepResult(step="auto_transition_state", enabled=True, ok=False,
                          detail="target_state vacío en config")
    try:
        from issue_provider import get_provider, load_tracker_config
    except Exception as e:
        return StepResult(step="auto_transition_state", enabled=True, ok=False,
                          detail=f"issue_provider indisponible: {e}")
    try:
        cfg = load_tracker_config(project_name)
        if not cfg:
            return StepResult(step="auto_transition_state", enabled=True, ok=False,
                              detail="issue_tracker no configurado")
        provider = get_provider(project_name, override_config=cfg)
        ok = bool(provider.transition_state(ticket_id, target_state))
        return StepResult(
            step="auto_transition_state",
            enabled=True,
            ok=ok,
            detail="" if ok else f"provider rechazó la transición a '{target_state}'",
            extra={"target_state": target_state},
        )
    except Exception as e:
        return StepResult(step="auto_transition_state", enabled=True, ok=False,
                          detail=f"Excepción: {e}")


# ── Paso 3: publicar nota ─────────────────────────────────────────────────────

def _do_post_note(ticket_id: str, project_name: str | None,
                  note: str, is_html: bool) -> StepResult:
    if not note.strip():
        return StepResult(step="auto_post_note", enabled=True, ok=False,
                          detail="nota vacía tras render del template")
    try:
        from issue_provider import get_provider, load_tracker_config, CommentKind
    except Exception as e:
        return StepResult(step="auto_post_note", enabled=True, ok=False,
                          detail=f"issue_provider indisponible: {e}")
    try:
        cfg = load_tracker_config(project_name)
        if not cfg:
            return StepResult(step="auto_post_note", enabled=True, ok=False,
                              detail="issue_tracker no configurado")
        provider = get_provider(project_name, override_config=cfg)
        ok = bool(provider.add_comment(
            ticket_id, note, kind=CommentKind.GENERIC, is_html=is_html,
        ))
        return StepResult(
            step="auto_post_note",
            enabled=True,
            ok=ok,
            detail="" if ok else "provider rechazó el comentario",
            extra={"note_preview": note[:200]},
        )
    except Exception as e:
        return StepResult(step="auto_post_note", enabled=True, ok=False,
                          detail=f"Excepción: {e}")


# ── Orquestación ──────────────────────────────────────────────────────────────

def _current_branch(workspace: str) -> str:
    try:
        from scm_provider.factory import get_scm
        scm = get_scm(workspace=workspace)
        return scm.current_branch(workspace) or ""
    except Exception:
        return ""


def run_completion_flow(
    ticket_id: str,
    workspace: str,
    message: str,
    files: list[str],
    project_name: str | None = None,
    run_ado_async: bool = True,
) -> FlowResult:
    """Corre el flujo de finalización. Ver docstring del módulo.

    ``run_ado_async=True`` ejecuta los pasos 2 y 3 (ADO) en un thread para
    devolver rápido al UI. El resultado ``FlowResult.steps`` no incluirá los
    pasos ADO cuando son async — emiten logs/notificaciones por su cuenta.
    ``run_ado_async=False`` los corre sincrónico y los reporta en ``steps``.
    """
    cfg = load_completion_config(project_name)
    cfg_dict = cfg.to_dict()
    steps: list[StepResult] = []

    # ── Paso 1: commit (siempre sincrónico — necesitamos la revision) ─────
    revision = ""
    files_out = list(files or [])
    commit_skipped = not cfg.auto_commit.enabled
    if cfg.auto_commit.enabled:
        s1 = _do_commit(ticket_id, workspace, message, files, project_name)
        steps.append(s1)
        if s1.ok:
            revision = s1.extra.get("revision", "") or ""
            files_out = s1.extra.get("files", files_out) or files_out
        else:
            # Abortamos pasos ADO si el commit falla (invariante de seguridad)
            return FlowResult(
                ok=False,
                revision="",
                commit_message=message,
                steps=steps,
                config=cfg_dict,
                files=files_out,
                error=s1.detail or "commit falló",
            )
    else:
        steps.append(StepResult(step="auto_commit", enabled=False, ok=True,
                                detail="auto_commit deshabilitado — pasos ADO asumen commit externo"))

    # ── Context para el template de nota ────────────────────────────────────
    branch = _current_branch(workspace)
    first_line = (message or "").splitlines()[0] if message else ""
    note_ctx = {
        "ticket_id":   ticket_id,
        "branch":      branch,
        "files_count": len(files_out),
        "revision":    (revision[:10] if revision else ""),
        "commit_msg":  first_line,
    }

    # ── Pasos 2 y 3: ADO ────────────────────────────────────────────────────
    def _run_ado():
        ado_steps: list[StepResult] = []
        if cfg.auto_transition_state.enabled:
            target = cfg.auto_transition_state.get("target_state", "") or ""
            s = _do_transition(ticket_id, project_name, target)
            ado_steps.append(s)
            _log_step(ticket_id, s)
        else:
            ado_steps.append(StepResult(step="auto_transition_state",
                                        enabled=False, ok=True,
                                        detail="deshabilitado"))
        if cfg.auto_post_note.enabled:
            tpl  = cfg.auto_post_note.get("note_template", "") or ""
            html = bool(cfg.auto_post_note.get("is_html", False))
            rendered = render_note_template(tpl, **note_ctx)
            s = _do_post_note(ticket_id, project_name, rendered, html)
            ado_steps.append(s)
            _log_step(ticket_id, s)
        else:
            ado_steps.append(StepResult(step="auto_post_note",
                                        enabled=False, ok=True,
                                        detail="deshabilitado"))
        return ado_steps

    if run_ado_async:
        threading.Thread(target=_run_ado, daemon=True).start()
    else:
        steps.extend(_run_ado())

    return FlowResult(
        ok=True,
        revision=revision,
        commit_message=message,
        steps=steps,
        config=cfg_dict,
        files=files_out,
        error="",
    )


def _log_step(ticket_id: str, step: StepResult) -> None:
    tag = f"[TICKET_COMPLETION:{step.step}]"
    msg = f"#{ticket_id} enabled={step.enabled} ok={step.ok} detail={step.detail}"
    try:
        if step.ok:
            print(f"{tag} {msg}", flush=True)
        else:
            print(f"{tag} {msg}", file=sys.stderr, flush=True)
    except Exception:
        pass
    # Notifier (best-effort)
    try:
        from notifier import notify as _notify
        level = "info" if step.ok else "warning"
        _notify(f"{step.step} {'OK' if step.ok else 'FALLO'} #{ticket_id}",
                step.detail or "", level=level, ticket_id=ticket_id)
    except Exception:
        pass
