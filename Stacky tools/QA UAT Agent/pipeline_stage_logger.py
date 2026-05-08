"""
pipeline_stage_logger.py — Logger de ciclo de vida de stages del pipeline QA UAT.

Orquesta la instrumentación forense completa de cada stage:
  1. Emite stage.started con parámetros de entrada.
  2. Actualiza run_state.json con el stage actual.
  3. Escribe checkpoint al finalizar (completed | failed | blocked).
  4. Emite stage.completed | stage.failed | stage.blocked.
  5. Actualiza run_state.json con el resultado.
  6. Integra con CommandRunner y FilesystemLogger.

También provee la función `get_stage_context()` para uso como context manager.

Uso como context manager:
    from pipeline_stage_logger import PipelineStageLogger

    stage_log = PipelineStageLogger(
        run_dir=run_dir,
        forensic_log=log,
        manifest=manifest_mgr,
        checkpoint_mgr=cp_mgr,
        store=store,
    )

    with stage_log.stage("reader", params={"ticket_id": 70}) as ctx:
        # ctx.runner → CommandRunner pre-configurado
        # ctx.fs → FilesystemLogger pre-configurado
        result = do_reader_work()
        ctx.set_result(result)  # opcional, para incluir en checkpoint

    # Al salir del with: checkpoint escrito, estado actualizado, eventos emitidos
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional

from checkpoint_manager import CheckpointManager
from command_runner import CommandRunner
from filesystem_logger import FilesystemLogger
from run_manifest import RunManifest

import logging

_py_logger = logging.getLogger("stacky.qa_uat.pipeline_stage_logger")


# ── StageContext ───────────────────────────────────────────────────────────────

class StageContext:
    """
    Contexto de ejecución de un stage.

    Provee acceso a runner, fs y métodos de control del stage.
    Se obtiene via PipelineStageLogger.stage().
    """

    def __init__(
        self,
        stage_name: str,
        stage_logger: "PipelineStageLogger",
        params: Optional[dict] = None,
    ) -> None:
        self.stage_name = stage_name
        self._stage_logger = stage_logger
        self._params = params or {}
        self._result: Optional[dict] = None
        self._blocked: bool = False
        self._blocked_reason: str = ""
        self._t0: float = 0.0
        self.start_event_id: Optional[str] = None

        # Herramientas pre-configuradas para el stage
        self.runner: CommandRunner = CommandRunner(
            run_dir=stage_logger.run_dir,
            stage=stage_name,
            forensic_log=stage_logger.forensic_log,
            run_id=stage_logger.run_id,
            ticket_id=stage_logger.ticket_id,
        )
        self.fs: FilesystemLogger = FilesystemLogger(
            run_dir=stage_logger.run_dir,
            stage=stage_name,
            forensic_log=stage_logger.forensic_log,
            artifact_registry=stage_logger.artifact_registry,
            run_id=stage_logger.run_id,
            ticket_id=stage_logger.ticket_id,
        )

    def set_result(self, result: dict) -> None:
        """Guardar resultado del stage para incluirlo en el checkpoint."""
        self._result = result

    def block(self, reason: str) -> None:
        """Marcar el stage como bloqueado (sin lanzar excepción)."""
        self._blocked = True
        self._blocked_reason = reason

    def duration_ms(self) -> int:
        return int((time.monotonic() - self._t0) * 1000)


# ── PipelineStageLogger ────────────────────────────────────────────────────────

class PipelineStageLogger:
    """
    Gestiona el ciclo de vida de stages del pipeline con logging forense.

    Centraliza:
      - ForensicEventLogger para eventos
      - RunManifest para run_state.json
      - CheckpointManager para checkpoints
      - EventStore para persistencia SQLite
    """

    def __init__(
        self,
        run_dir: Path,
        *,
        forensic_log: Any = None,           # ForensicEventLogger
        manifest: Optional[RunManifest] = None,
        checkpoint_mgr: Optional[CheckpointManager] = None,
        store: Any = None,                  # EventStore
        artifact_registry: Any = None,      # ArtifactRegistry
        run_id: str = "",
        ticket_id: Any = "",
    ) -> None:
        self.run_dir = run_dir
        self.forensic_log = forensic_log
        self.manifest = manifest
        self.checkpoint_mgr = checkpoint_mgr or CheckpointManager(run_id=run_id, run_dir=run_dir)
        self.store = store
        self.artifact_registry = artifact_registry
        self.run_id = run_id
        self.ticket_id = ticket_id

    def stage(
        self,
        stage_name: str,
        params: Optional[dict] = None,
    ) -> "_StageCM":
        """Devuelve un context manager para ejecutar un stage con logging forense completo."""
        return _StageCM(self, stage_name, params)

    def run_stage(
        self,
        stage_name: str,
        fn: Any,
        params: Optional[dict] = None,
    ) -> dict:
        """
        Ejecutar una función como stage con logging forense.

        fn debe ser callable que recibe (ctx: StageContext) → dict.
        """
        with _StageCM(self, stage_name, params) as ctx:
            result = fn(ctx)
            if isinstance(result, dict):
                ctx.set_result(result)
            return result

    # ── Consultas ──────────────────────────────────────────────────────────────

    def is_stage_completed(self, stage_name: str) -> bool:
        """Verificar si un stage ya fue completado (para reanudación)."""
        return self.checkpoint_mgr.is_completed(stage_name)

    def last_completed(self) -> Optional[str]:
        """Devolver el último stage completado."""
        return self.checkpoint_mgr.last_completed_stage()

    def get_resume_point(self, stage_sequence: list[str]) -> Optional[str]:
        """
        Dado el orden de stages, devolver el primer stage no completado.
        Útil para reanudar un run bloqueado sin repetir stages ya terminados.
        """
        for s in stage_sequence:
            if not self.checkpoint_mgr.is_completed(s):
                return s
        return None


# ── Context Manager interno ────────────────────────────────────────────────────

class _StageCM:
    """Context manager para un stage individual."""

    def __init__(
        self,
        stage_logger: PipelineStageLogger,
        stage_name: str,
        params: Optional[dict] = None,
    ) -> None:
        self._sl = stage_logger
        self._stage_name = stage_name
        self._params = params or {}
        self._ctx: Optional[StageContext] = None

    def __enter__(self) -> StageContext:
        ctx = StageContext(
            stage_name=self._stage_name,
            stage_logger=self._sl,
            params=self._params,
        )
        ctx._t0 = time.monotonic()
        self._ctx = ctx

        # Actualizar run_state.json
        if self._sl.manifest:
            try:
                self._sl.manifest.update_state(
                    status="running",
                    current_stage=self._stage_name,
                )
            except Exception:
                pass

        # Emitir stage.started
        if self._sl.forensic_log:
            try:
                eid = self._sl.forensic_log.emit_stage_started(
                    self._stage_name,
                    payload=self._params or None,
                )
                ctx.start_event_id = eid
            except Exception:
                pass

        return ctx

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        ctx = self._ctx
        if ctx is None:
            return False

        duration_ms = ctx.duration_ms()
        stage_name = self._stage_name

        if exc_type is not None:
            # Excepción no manejada → stage.failed
            reason = str(exc_val)
            _py_logger.error("Stage '%s' falló con excepción: %s", stage_name, reason)

            if self._sl.forensic_log:
                try:
                    self._sl.forensic_log.emit_stage_failed(
                        stage_name,
                        reason=reason,
                        payload={"exception_type": exc_type.__name__ if exc_type else ""},
                        duration_ms=duration_ms,
                    )
                except Exception:
                    pass

            if self._sl.checkpoint_mgr:
                try:
                    self._sl.checkpoint_mgr.mark_failed(
                        stage_name,
                        payload={"error": reason, "duration_ms": duration_ms},
                        store=self._sl.store,
                    )
                except Exception:
                    pass

            if self._sl.manifest:
                try:
                    self._sl.manifest.mark_failed(reason=reason, stage=stage_name)
                except Exception:
                    pass

            # No suprimir la excepción
            return False

        elif ctx._blocked:
            # Stage bloqueado explícitamente via ctx.block()
            reason = ctx._blocked_reason

            if self._sl.forensic_log:
                try:
                    self._sl.forensic_log.emit_stage_blocked(
                        stage_name,
                        reason=reason,
                        payload=ctx._result,
                    )
                except Exception:
                    pass

            if self._sl.checkpoint_mgr:
                try:
                    self._sl.checkpoint_mgr.mark_blocked(
                        stage_name,
                        payload={
                            "reason": reason,
                            "duration_ms": duration_ms,
                            **(ctx._result or {}),
                        },
                        store=self._sl.store,
                    )
                except Exception:
                    pass

            if self._sl.manifest:
                try:
                    self._sl.manifest.mark_blocked(
                        reason=reason,
                        stage=stage_name,
                        waiting_for_human=True,
                    )
                except Exception:
                    pass

        else:
            # Stage completado exitosamente
            if self._sl.forensic_log:
                try:
                    self._sl.forensic_log.emit_stage_completed(
                        stage_name,
                        payload=ctx._result,
                        duration_ms=duration_ms,
                    )
                except Exception:
                    pass

            if self._sl.checkpoint_mgr:
                try:
                    self._sl.checkpoint_mgr.mark_completed(
                        stage_name,
                        payload={
                            "duration_ms": duration_ms,
                            **(ctx._result or {}),
                        },
                        store=self._sl.store,
                    )
                except Exception:
                    pass

            if self._sl.manifest:
                try:
                    self._sl.manifest.update_state(
                        last_completed_stage=stage_name,
                    )
                except Exception:
                    pass

        return False  # No suprimir excepciones
