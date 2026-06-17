"""E1.1 — Gate + pase correctivo único dirigido al fallo ejecutable.

Solo se invoca cuando exec_verification está en modo 'gate' y hay hard_failed.
Reusa el seam de run_repair/autocorrect existente.

API pública:
    attempt_exec_repair(run_id, workspace, runtime, hard_failed, budget_remaining,
                        send_fn) -> RepairResult

Contratos de metadata (clave nueva bajo exec_verification):
    metadata["exec_verification"]["repair"] = {
        "attempted": bool,
        "failed_before": [...],
        "recovered": bool,
    }

Restricciones:
  - Si runtime sin supports_resume → skip, degrada a needs_review, no repara
  - UN solo pase correctivo (STACKY_EXEC_REPAIR_MAX_RETRIES default 1)
  - Re-verificación usa verificador ORIGINAL INMUTABLE (caché invalidada)
  - Modificar el propio test cuenta como nuevo artefacto (nuevo hash → re-corre)
  - Presupuesto compartido con autocorrect/run_repair/Q1.1
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

from harness.capabilities import CAPABILITIES

logger = logging.getLogger("stacky.exec_repair")

_MAX_EXCERPT = 800  # chars del log de fallo a pasar al agente


@dataclass
class RepairResult:
    attempted: bool
    recovered: bool
    failed_before: list[str] = field(default_factory=list)
    skip_reason: str | None = None

    def to_metadata(self) -> dict:
        return {
            "attempted": self.attempted,
            "failed_before": self.failed_before,
            "recovered": self.recovered,
            "skip_reason": self.skip_reason,
        }


def attempt_exec_repair(
    *,
    run_id: str | int | None,
    workspace: str,
    runtime: str,
    hard_failed: list,  # list[VerifierResult]
    budget_remaining: int,
    send_fn: Callable[[str], str] | None = None,
    changed_files: list[str] | None = None,
) -> RepairResult:
    """Intenta un único pase correctivo ante fallo ejecutable.

    Args:
        run_id: id del run (informativo, para logging).
        workspace: directorio de trabajo del agente.
        runtime: identificador del runtime.
        hard_failed: lista de VerifierResult con status 'hard'.
        budget_remaining: segundos de presupuesto restante (compartido).
        send_fn: callable(message) → str (nueva salida). None si no disponible.
        changed_files: archivos cambiados (para re-verificación).

    Returns:
        RepairResult con attempted, recovered, failed_before.
    """
    try:
        from config import config as _cfg
        enabled = getattr(_cfg, "STACKY_EXEC_REPAIR_ENABLED", False)
        max_retries = int(getattr(_cfg, "STACKY_EXEC_REPAIR_MAX_RETRIES", 1))
    except Exception:
        enabled = False
        max_retries = 1

    if not enabled:
        return RepairResult(attempted=False, recovered=False, skip_reason="flag OFF")

    if not hard_failed:
        return RepairResult(attempted=False, recovered=False, skip_reason="sin hard_failed")

    # Verificar soporte de resume en el runtime
    caps = CAPABILITIES.get(runtime)
    if caps is None or not caps.supports_resume:
        logger.debug("exec_repair: runtime %r sin soporte de resume, skip", runtime)
        return RepairResult(
            attempted=False,
            recovered=False,
            skip_reason=f"runtime {runtime!r} sin supports_resume",
        )

    if send_fn is None:
        logger.debug("exec_repair: send_fn no disponible, skip")
        return RepairResult(
            attempted=False,
            recovered=False,
            skip_reason="send_fn no disponible",
        )

    if budget_remaining <= 0:
        logger.debug("exec_repair: presupuesto agotado (%ds), skip", budget_remaining)
        return RepairResult(
            attempted=False,
            recovered=False,
            skip_reason=f"presupuesto agotado ({budget_remaining}s)",
        )

    # Construir mensaje de reparación dirigido al fallo
    failed_before = [r.name for r in hard_failed]
    excerpts = []
    for r in hard_failed[:max_retries]:
        excerpt = r.detail[:_MAX_EXCERPT] if r.detail else "(sin detalle)"
        excerpts.append(f"`{r.name}` → {excerpt}")

    repair_msg = (
        "La verificación ejecutable del entregable falló:\n"
        + "\n".join(excerpts)
        + "\n\nCorregí SOLO eso, manteniendo el resto; mismo formato."
    )

    logger.info(
        "exec_repair: enviando pase correctivo para run %s (hard: %s)",
        run_id,
        ", ".join(failed_before),
    )

    try:
        new_output = send_fn(repair_msg)
    except Exception as exc:  # noqa: BLE001
        logger.warning("exec_repair: send_fn lanzó excepción: %s", exc)
        return RepairResult(
            attempted=True,
            recovered=False,
            failed_before=failed_before,
            skip_reason=f"send_fn error: {exc}",
        )

    # Re-verificar con verificador ORIGINAL INMUTABLE
    # Invalidar caché para que no use el resultado anterior
    if changed_files is not None:
        try:
            from services.exec_verification import invalidate_cache, verify
            invalidate_cache(workspace, changed_files)
            re_report = verify(
                workspace=workspace,
                changed_files=changed_files,
                runtime=runtime,
                budget_s=max(budget_remaining // 2, 30),
            )
            recovered = re_report.passed is True
        except Exception as exc:  # noqa: BLE001
            logger.warning("exec_repair: re-verificación falló: %s", exc)
            recovered = False
    else:
        # Sin changed_files → no podemos re-verificar, asumimos no recuperado
        logger.debug("exec_repair: sin changed_files para re-verificar")
        recovered = False

    logger.info(
        "exec_repair: run %s → %s",
        run_id,
        "RECUPERADO" if recovered else "sigue fallando → needs_review",
    )

    return RepairResult(
        attempted=True,
        recovered=recovered,
        failed_before=failed_before,
    )
