"""cli_autocorrect.py — Loop de autocorrección sobre stdin (F1.3).

Máquina de estados simple disparada al fin de cada turno del agente
(evento `result` del stream-json de Claude Code CLI):

    idle ──result──> validating ──ok──────────> passed   (terminal)
                        │ inválido & quedan reintentos
                        └────────> correcting (mensaje por stdin, vuelve a idle)
                        │ inválido & cap agotado
                        └────────> exhausted (terminal: no se escribe más)

Reglas:
  - UN mensaje correctivo por turno fallido, con el error exacto por archivo.
  - Cap de reintentos configurable (CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES).
  - Solo se corrigen artifacts PRESENTES e inválidos; la ausencia no dispara
    corrección (output_watcher/agent_completion quedan como fallback).
  - Todo se loguea en el stream visible al operador.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable

from services import artifact_validator

logger = logging.getLogger("stacky.cli_autocorrect")

# Acciones que retorna on_turn_end()
ACTION_NO_ARTIFACTS = "no_artifacts"
ACTION_OK = "ok"
ACTION_CORRECTED = "corrected"
ACTION_EXHAUSTED = "exhausted"
ACTION_DONE = "done"          # loop ya terminal, no hace nada
ACTION_SEND_FAILED = "send_failed"


def build_correction_message(invalid: list[artifact_validator.ArtifactValidation]) -> str:
    """Mensaje correctivo con el error exacto por archivo (UN mensaje por turno)."""
    lines = [
        "Stacky validó los archivos de salida de este run y encontró problemas "
        "que impiden crear la Task / publicar el comentario en Azure DevOps:",
        "",
    ]
    for art in invalid:
        lines.append(f"- {art.path}")
        for err in art.errors:
            lines.append(f"    ERROR: {err}")
        for warn in art.warnings:
            lines.append(f"    AVISO: {warn}")
    lines.extend([
        "",
        "Corregí esos archivos reescribiéndolos en su ubicación actual y avisá "
        "cuando estén corregidos. Recordatorios:",
        "- El directorio debe llamarse epic-<ADO_ID real> y el campo epic_id debe "
        "ser el ADO id REAL del Epic (no el número ordinal del RF).",
        "- pending-task.json debe ser JSON estrictamente válido con todos los "
        "campos requeridos y status 'pending_manual_creation'.",
        "- No toques Azure DevOps: Stacky valida y publica.",
    ])
    return "\n".join(lines)


class AutocorrectLoop:
    """Estado de autocorrección de UN run de Claude Code CLI."""

    def __init__(
        self,
        *,
        ado_id: int,
        max_retries: int,
        send: Callable[[str], bool],
        log: Callable[..., None] | None = None,
        outputs_root=None,
        since_epoch: float | None = None,
        check_db: bool = True,
    ) -> None:
        self.ado_id = int(ado_id)
        self.max_retries = max(0, int(max_retries))
        self._send = send
        self._log = log or (lambda *a, **k: None)
        self._outputs_root = outputs_root
        self._since_epoch = since_epoch
        self._check_db = check_db
        self._lock = threading.Lock()
        self.attempts = 0
        self.last_action: str | None = None
        self.last_errors: list[dict] = []
        self._terminal = False

    # ── API ──────────────────────────────────────────────────────────────────

    def on_turn_end(self) -> str:
        """Valida artifacts al fin de turno; envía corrección si corresponde.

        Thread-safe y no reentrante: si ya hay una validación en curso o el
        loop quedó terminal, retorna ACTION_DONE.
        """
        if not self._lock.acquire(blocking=False):
            return ACTION_DONE
        try:
            if self._terminal:
                return ACTION_DONE
            return self._validate_and_react()
        finally:
            self._lock.release()

    def summary(self) -> dict:
        return {
            "attempts": self.attempts,
            "max_retries": self.max_retries,
            "last_action": self.last_action,
            "last_errors": self.last_errors,
        }

    # ── Interno ──────────────────────────────────────────────────────────────

    def _validate_and_react(self) -> str:
        try:
            report = artifact_validator.validate_run_artifacts(
                ado_id=self.ado_id,
                outputs_root=self._outputs_root,
                since_epoch=self._since_epoch,
                check_db=self._check_db,
            )
        except Exception as exc:  # noqa: BLE001 — la validación nunca tumba el run
            logger.exception("autocorrect: validación falló para ADO-%s", self.ado_id)
            self._log("warn", f"autocorrección: validación de artifacts falló: {exc}")
            self.last_action = ACTION_DONE
            return ACTION_DONE

        if report.checked == 0:
            self.last_action = ACTION_NO_ARTIFACTS
            return ACTION_NO_ARTIFACTS

        invalid = report.invalid
        if not invalid:
            if self.attempts:
                self._log(
                    "info",
                    f"autocorrección: artifacts válidos tras {self.attempts} corrección(es)",
                    group="operator",
                )
            self.last_action = ACTION_OK
            self.last_errors = []
            self._terminal = True
            return ACTION_OK

        self.last_errors = [a.to_dict() for a in invalid]
        names = ", ".join(sorted({Path(a.path).name for a in invalid}))

        if self.attempts >= self.max_retries:
            self._terminal = True
            self.last_action = ACTION_EXHAUSTED
            self._log(
                "warn",
                f"Stacky detectó {names} inválido pero se agotaron los reintentos "
                f"({self.max_retries}); el run cerrará con los errores registrados.",
                group="operator",
            )
            return ACTION_EXHAUSTED

        message = build_correction_message(invalid)
        self.attempts += 1
        self._log(
            "warn",
            f"Stacky detectó {names} inválido, pidiendo corrección… "
            f"(intento {self.attempts}/{self.max_retries})",
            group="operator",
        )
        if not self._send(message):
            self._terminal = True
            self.last_action = ACTION_SEND_FAILED
            self._log("warn", "autocorrección: no se pudo escribir en el stdin del agente")
            return ACTION_SEND_FAILED

        self.last_action = ACTION_CORRECTED
        return ACTION_CORRECTED
