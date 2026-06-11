"""H1.1 — Post-run pipeline compartido entre runtimes.

finalize_run(runtime, agent_type, output_text, ado_id, gate_enabled, log)
  -> PostRunResult

Lógica:
  - Corre contract_validator + confidence sobre el output.
  - Si gate_enabled y hay failures → status_suggestion="needs_review".
  - Caso contrario → status_suggestion="completed".
  - Siempre devuelve contract_score, confidence, metadata_patch.
  - artifacts: resultado de validate_run_artifacts si el runtime escribe artifacts
    (según harness.capabilities.CAPABILITIES[runtime].writes_artifacts).
    Si el runtime NO escribe artifacts, artifacts es None.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("stacky.harness.post_run")


@dataclass
class PostRunResult:
    status_suggestion: str            # "completed" | "needs_review"
    contract_score: int
    contract_passed: bool
    contract_failures: list[str]
    confidence_overall: int
    metadata_patch: dict[str, Any]    # claves listas para fusionar en metadata
    artifacts: Any | None             # ArtifactReport o None


def finalize_run(
    *,
    runtime: str,
    agent_type: str,
    output_text: str,
    ado_id: int | None = None,
    gate_enabled: bool = False,
    log=None,
) -> PostRunResult:
    """Pipeline de calidad post-run unificado.

    Args:
        runtime: "claude_code_cli" | "codex_cli" | otros
        agent_type: tipo de agente (para contract_validator)
        output_text: texto de salida del run
        ado_id: id ADO para validate_run_artifacts (None = skip artifacts)
        gate_enabled: si True, failures de contrato → needs_review
        log: callable(level, msg) opcional para el stream visible al operador
    """
    import contract_validator
    from services import confidence
    from harness import capabilities

    _log = log or (lambda level, msg: logger.debug("[%s] %s", level, msg))

    # --- Contract validator + confidence ---
    _log("info", "validando contrato del output…")
    cv_result = contract_validator.validate(agent_type, output_text or "")
    _log(
        "info" if cv_result.passed else "warn",
        f"contrato {'OK' if cv_result.passed else 'WARNINGS'} — score {cv_result.score}/100"
        + (f" ({len(cv_result.failures)} errores)" if cv_result.failures else ""),
    )

    conf = confidence.score(output_text or "")
    _log(
        "info" if conf.overall >= 70 else "warn",
        f"confidence {conf.overall}/100",
    )

    status = "completed"
    if gate_enabled and cv_result.failures:
        status = "needs_review"
        _log(
            "warn",
            f"contrato con {len(cv_result.failures)} error(es) → needs_review (gate ON)",
        )

    # --- Artifact validation (solo si el runtime escribe artifacts) ---
    cap = capabilities.CAPABILITIES.get(runtime)
    artifacts = None
    if cap is not None and cap.writes_artifacts and ado_id is not None:
        try:
            from services import artifact_validator
            artifacts = artifact_validator.validate_run_artifacts(ado_id, check_db=False)
            invalid_count = len(artifacts.invalid)
            _log(
                "info" if artifacts.ok else "warn",
                f"artifacts: {artifacts.checked} chequeados, {invalid_count} inválidos",
            )
        except Exception as exc:  # noqa: BLE001
            _log("warn", f"artifact validation falló (no crítico): {exc}")

    metadata_patch: dict[str, Any] = {
        "contract_score": cv_result.score,
        "confidence": conf.to_dict(),
    }

    return PostRunResult(
        status_suggestion=status,
        contract_score=cv_result.score,
        contract_passed=cv_result.passed,
        contract_failures=list(cv_result.failures),
        confidence_overall=conf.overall,
        metadata_patch=metadata_patch,
        artifacts=artifacts,
    )
