"""H2.3 — Autocorrección codex via exec resume.

Análogo a cli_autocorrect.AutocorrectLoop pero para codex, donde el canal
de feedback es `codex exec resume <session_id> "<mensaje>"` en vez de stdin.

Diseño:
  - run_autocorrect_loop: función pura con dependencias inyectadas (resume_fn,
    validate_fn) → testeable sin invocar codex real.
  - El runner (codex_cli_runner.py) construye las dependencias reales y llama
    esta función ANTES de finalize_run.
  - Sin session_id → log warn y saltar (0 retries).
  - Sin artifacts detectados → saltar (0 retries).
  - Cap: CODEX_CLI_AUTOCORRECT_MAX_RETRIES (default 2).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from services import artifact_validator
from services.cli_autocorrect import build_correction_message

logger = logging.getLogger("stacky.codex_autocorrect")


@dataclass
class AutocorrectResult:
    status_suggestion: str   # "completed" | "needs_review"
    retries_used: int
    final_artifacts_ok: bool


def run_autocorrect_loop(
    *,
    session_id: str | None,
    ado_id: int,
    max_retries: int,
    gate_enabled: bool,
    resume_fn: Callable[[str, str], bool],
    validate_fn: Callable[..., artifact_validator.ArtifactReport],
    log: Callable[..., None] | None = None,
) -> AutocorrectResult:
    """Loop de autocorrección codex.

    Args:
        session_id: codex session id; si None → skip.
        ado_id: id ADO para validate_run_artifacts.
        max_retries: máximo de resumes a intentar.
        gate_enabled: si True, failure final → needs_review.
        resume_fn: callable(session_id, prompt) → bool (True = lanzado OK).
        validate_fn: callable(ado_id, check_db=False) → ArtifactReport.
        log: callable(level, msg).
    """
    _log = log or (lambda level, msg: logger.debug("[%s] %s", level, msg))

    if session_id is None:
        _log("warn", "codex autocorrect: sin session_id, skip loop")
        return AutocorrectResult(
            status_suggestion="completed",
            retries_used=0,
            final_artifacts_ok=True,
        )

    # Primera validación
    report = validate_fn(ado_id, check_db=False)

    if report.checked == 0:
        _log("info", "codex autocorrect: sin artifacts detectados, skip")
        return AutocorrectResult(
            status_suggestion="completed",
            retries_used=0,
            final_artifacts_ok=True,
        )

    if report.ok:
        _log("info", f"codex autocorrect: {report.checked} artifacts válidos, no resume necesario")
        return AutocorrectResult(
            status_suggestion="completed",
            retries_used=0,
            final_artifacts_ok=True,
        )

    retries = 0
    while retries < max_retries and not report.ok:
        invalid = report.invalid
        _log(
            "warn",
            f"codex autocorrect: {len(invalid)} artifact(s) inválido(s) "
            f"(intento {retries + 1}/{max_retries}), lanzando exec resume…",
        )
        msg = build_correction_message(invalid)
        launched = resume_fn(session_id, msg)
        retries += 1

        if not launched:
            _log("warn", "codex autocorrect: resume_fn reportó fallo, cortando loop")
            break

        # Re-validar tras el resume
        report = validate_fn(ado_id, check_db=False)
        if report.ok:
            _log("info", f"codex autocorrect: artifacts válidos tras {retries} resume(s)")
            break

    final_ok = report.ok
    status = "completed"
    if not final_ok and gate_enabled:
        status = "needs_review"
        _log(
            "warn",
            f"codex autocorrect: artifacts aún inválidos tras {retries} resume(s) "
            "+ gate ON → needs_review",
        )
    elif not final_ok:
        _log(
            "warn",
            f"codex autocorrect: artifacts aún inválidos tras {retries} resume(s) "
            "(gate OFF → completed)",
        )

    return AutocorrectResult(
        status_suggestion=status,
        retries_used=retries,
        final_artifacts_ok=final_ok,
    )
