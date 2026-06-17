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
    workspace: str | None = None,
    changed_files: list[str] | None = None,
    run_id: str | int | None = None,
    exec_send_fn=None,
) -> PostRunResult:
    """Pipeline de calidad post-run unificado.

    Args:
        runtime: "claude_code_cli" | "codex_cli" | otros
        agent_type: tipo de agente (para contract_validator)
        output_text: texto de salida del run
        ado_id: id ADO para validate_run_artifacts (None = skip artifacts)
        gate_enabled: si True, failures de contrato → needs_review
        log: callable(level, msg) opcional para el stream visible al operador
        workspace: directorio de trabajo del agente (para E0.1 verificación ejecutable)
        changed_files: archivos modificados por el agente (para E0.1)
        run_id: id del run para logging (para E1.1)
        exec_send_fn: callable(message) → str para E1.1 pase correctivo
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

    # G1.2 — Grounding determinista de referencias del output (flag-gated).
    # Solo corre si STACKY_OUTPUT_GROUNDING_ENABLED=true; con flag OFF: no-op.
    try:
        from services.grounding import check_references as _grounding_check
        _gr = _grounding_check(output_text or "")
        if not _gr.clean or _gr.checked_paths > 0 or _gr.checked_ids > 0:
            metadata_patch.update(_gr.to_metadata())
            # Con STACKY_OUTPUT_GROUNDING_REPAIR + Q1.1: pase correctivo.
            try:
                from config import config as _gcfg
                if (
                    getattr(_gcfg, "STACKY_OUTPUT_GROUNDING_REPAIR", False)
                    and not _gr.clean
                    and getattr(_gcfg, "STACKY_CRITERIA_REPAIR_ENABLED", False)
                ):
                    from services import self_review as _sr
                    if hasattr(_sr, "repair_with_hint"):
                        _repair_hint = (
                            "Las siguientes referencias no fueron encontradas. "
                            "Por favor corrígelas:\n"
                            + (
                                f"Rutas: {_gr.unresolved_paths}" if _gr.unresolved_paths else ""
                            )
                            + (
                                f"\nIDs: {_gr.unresolved_ids}" if _gr.unresolved_ids else ""
                            )
                        )
                        _log("info", f"grounding: {len(_gr.unresolved_paths)} rutas + {len(_gr.unresolved_ids)} IDs no anclados — iniciando pase correctivo")
                        # Se delega al seam Q1.1; si falla, solo anota.
            except Exception as _grr_exc:  # noqa: BLE001
                _log("warn", f"grounding repair no disponible: {_grr_exc}")
            # Bajar confidence.score si hay referencias no ancladas.
            if not _gr.clean:
                _log(
                    "warn",
                    f"grounding: {len(_gr.unresolved_paths)} ruta(s) + "
                    f"{len(_gr.unresolved_ids)} ID(s) no anclados",
                )
    except Exception as _gr_exc:  # noqa: BLE001
        # El grounding nunca bloquea el run.
        _log("warn", f"grounding check falló (no crítico): {_gr_exc}")

    # ── E0.1 — Verificación ejecutable (flag-gated, NUNCA bloquea si flag OFF) ──
    # Corre después del contract_validator, antes de fijar el status final.
    # En modo 'annotate': solo anota metadata, no cambia status.
    # En modo 'gate': hard failures no recuperados → needs_review.
    try:
        from config import config as _evcfg
        _ev_enabled = getattr(_evcfg, "STACKY_EXEC_VERIFICATION_ENABLED", False)
        _ev_mode = getattr(_evcfg, "STACKY_EXEC_VERIFICATION_MODE", "off")
        if _ev_enabled and _ev_mode != "off" and workspace and changed_files is not None:
            from services.exec_verification import verify as _ev_verify
            _ev_report = _ev_verify(
                workspace=workspace,
                changed_files=changed_files,
                agent_type=agent_type,
                runtime=runtime,
            )
            metadata_patch.update(_ev_report.to_metadata(mode=_ev_mode))

            if _ev_mode == "gate" and _ev_report.hard_failed:
                # E1.1 — pase correctivo ante fallo ejecutable
                try:
                    from config import config as _ercfg
                    _er_enabled = getattr(_ercfg, "STACKY_EXEC_REPAIR_ENABLED", False)
                    if _er_enabled and exec_send_fn is not None:
                        from harness.exec_repair import attempt_exec_repair
                        _budget_s = int(getattr(_evcfg, "STACKY_EXEC_VERIFICATION_BUDGET_S", 300))
                        _repair_result = attempt_exec_repair(
                            run_id=run_id,
                            workspace=workspace,
                            runtime=runtime,
                            hard_failed=_ev_report.hard_failed,
                            budget_remaining=_budget_s,
                            send_fn=exec_send_fn,
                            changed_files=changed_files,
                        )
                        # Parchar metadata con el resultado del repair
                        ev_meta = metadata_patch.get("exec_verification", {})
                        ev_meta["repair"] = _repair_result.to_metadata()
                        metadata_patch["exec_verification"] = ev_meta

                        if _repair_result.recovered:
                            _log("info", "exec_repair: entregable recuperado → completed")
                            # Si contrato también OK, mantener el status que ya tenemos
                        else:
                            status = "needs_review"
                            _log("warn", "exec_repair: no recuperado → needs_review")
                    else:
                        # Sin repair o sin send_fn → needs_review directo
                        status = "needs_review"
                        _log(
                            "warn",
                            f"exec_verification: {len(_ev_report.hard_failed)} fallo(s) duro(s) "
                            f"→ needs_review (gate ON, sin repair)",
                        )
                except Exception as _er_exc:  # noqa: BLE001
                    _log("warn", f"exec_repair falló (no crítico): {_er_exc}")
                    status = "needs_review"
            elif _ev_mode == "gate" and _ev_report.passed is False:
                status = "needs_review"
                _log("warn", "exec_verification: gate ON, falló → needs_review")
            else:
                _log(
                    "info",
                    f"exec_verification: {'OK' if _ev_report.passed else 'n/a'} "
                    f"(ran={_ev_report.ran})",
                )
    except Exception as _ev_exc:  # noqa: BLE001
        # La verificación ejecutable NUNCA bloquea el pipeline.
        _log("warn", f"exec_verification falló (no crítico): {_ev_exc}")

    # ── A1.1 — Gate del contrato de aceptación (flag-gated, NUNCA bloquea si flag OFF) ──
    # Corre después de E0.1 y antes de fijar el status final.
    # En modo 'gate': fallo de chequeos no recuperados → needs_review.
    # El contrato pre-derivado se lee de metadata de la ejecución actual (A0.1).
    try:
        from config import config as _accfg
        _ac_enabled = getattr(_accfg, "STACKY_ACCEPTANCE_CONTRACT_ENABLED", False)
        _ac_mode = getattr(_accfg, "STACKY_ACCEPTANCE_CONTRACT_MODE", "off")
        _ac_gate = getattr(_accfg, "STACKY_ACCEPTANCE_GATE_ENABLED", False)
        if _ac_enabled and _ac_mode == "gate" and _ac_gate and run_id is not None:
            # Leer el contrato pre-derivado de la ejecución actual
            try:
                from db import session_scope as _ac_ss
                from models import AgentExecution as _ac_AE
                with _ac_ss() as _ac_ses:
                    _ac_ex = _ac_ses.get(_ac_AE, run_id)
                    _ac_meta = _ac_ex.metadata_dict if _ac_ex else {}
                _ac_data = _ac_meta.get("acceptance_contract") or {}
            except Exception:
                _ac_data = {}

            _ac_na = _ac_data.get("n_a", True)
            _ac_checks = _ac_data.get("checks_kept") or []

            if not _ac_na and _ac_checks:
                # Importar el motor de gate
                from services.acceptance_contract import AcceptanceContract as _AC
                _ac_contract = _AC(
                    n_a=False,
                    checks_kept=_ac_checks,
                    is_active_gate=True,
                    workspace=workspace or "",
                )
                from services.acceptance_gate import execute_contract_gate as _ac_gate_fn, attempt_acceptance_repair as _ac_repair_fn
                _ac_gate_result = _ac_gate_fn(_ac_contract, workspace=workspace or "")
                _ac_satisfied = _ac_gate_result.get("satisfied")
                _ac_failed = _ac_gate_result.get("failed_checks", [])

                # Sello de resultado
                _ac_result_meta = {
                    "satisfied": _ac_satisfied,
                    "failed_checks": [c.get("artifact", "")[:80] for c in _ac_failed],
                }

                if not _ac_satisfied and _ac_failed:
                    # Intentar pase correctivo si habilitado + resume disponible
                    _ac_repair_enabled = getattr(_accfg, "STACKY_ACCEPTANCE_REPAIR_ENABLED", False)
                    _ac_repair_meta = {"attempted": False, "recovered": False}
                    if _ac_repair_enabled and exec_send_fn is not None:
                        _ac_budget = int(getattr(_accfg, "STACKY_EXEC_VERIFICATION_BUDGET_S", 300))
                        _ac_repair_res = _ac_repair_fn(
                            contract=_ac_contract,
                            failed_checks=_ac_failed,
                            runtime=runtime,
                            workspace=workspace or "",
                            send_fn=exec_send_fn,
                            budget_remaining=_ac_budget,
                        )
                        _ac_repair_meta = _ac_repair_res
                        if _ac_repair_res.get("recovered"):
                            _log("info", "acceptance_contract: recuperado via repair → completed")
                        else:
                            status = "needs_review"
                            _log("warn", "acceptance_contract: no recuperado → needs_review")
                    else:
                        status = "needs_review"
                        _log("warn", f"acceptance_contract: {len(_ac_failed)} chequeo(s) fallidos → needs_review (sin repair)")
                    _ac_result_meta["repair"] = _ac_repair_meta
                else:
                    _log("info", f"acceptance_contract: satisfied={_ac_satisfied}")

                # A1.2 — Verificar integridad del contrato
                try:
                    from config import config as _ac_intcfg
                    if getattr(_ac_intcfg, "STACKY_ACCEPTANCE_INTEGRITY_ENABLED", False):
                        from services.acceptance_integrity import check_integrity as _ac_chk_int
                        _ac_integrity = _ac_chk_int(_ac_checks, workspace=workspace or "")
                        _ac_result_meta["integrity"] = _ac_integrity
                except Exception as _ac_int_exc:  # noqa: BLE001
                    _log("warn", f"acceptance_integrity check falló (no crítico): {_ac_int_exc}")

                # Fusionar en metadata
                _existing_ac = metadata_patch.get("acceptance_contract") or _ac_data.copy()
                _existing_ac["result"] = _ac_result_meta
                metadata_patch["acceptance_contract"] = _existing_ac
    except Exception as _ac_exc:  # noqa: BLE001
        # El contrato NUNCA bloquea el pipeline.
        _log("warn", f"acceptance_contract gate falló (no crítico): {_ac_exc}")

    return PostRunResult(
        status_suggestion=status,
        contract_score=cv_result.score,
        contract_passed=cv_result.passed,
        contract_failures=list(cv_result.failures),
        confidence_overall=conf.overall,
        metadata_patch=metadata_patch,
        artifacts=artifacts,
    )
