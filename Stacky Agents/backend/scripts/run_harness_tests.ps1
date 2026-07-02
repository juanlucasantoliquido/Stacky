# V1.4a — Runner curado del arnes (plan 22), version PowerShell para dev local.
# Equivalente a run_harness_tests.sh: corre cada archivo del arnes UNO POR UNO
# (esquiva la polucion de la suite completa). Exit 1 si alguno falla o falta.
#
# Uso:  pwsh scripts/run_harness_tests.ps1   (o powershell)
# La lista es un RATCHET: solo crece. Mantener en sync con run_harness_tests.sh.

$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")

$python = if ($env:PYTHON) { $env:PYTHON } else { "python" }

$HarnessTestFiles = @(
  # Nucleo del arnes
  "tests/test_harness_flags.py",
  "tests/test_harness_health.py",
  "tests/test_harness_h8_kpis.py",
  "tests/test_model_policy.py",
  "tests/test_run_contract.py",
  "tests/test_runaway_guard.py",
  "tests/test_codex_telemetry.py",
  "tests/test_codex_post_run.py",
  "tests/test_claude_code_cli_phase1.py",
  # Plan 22 V0
  "tests/test_harness_profiles.py",
  "tests/test_harness_failure.py",
  "tests/test_harness_pricing.py",
  "tests/test_harness_health_v0.py",
  "tests/test_run_guard.py",
  "tests/test_run_slots.py",
  "tests/test_run_launch_guards.py",
  "tests/test_mark_terminal_failure_kind.py",
  "tests/test_telemetry_cost_estimation.py",
  # Plan 22 V1
  "tests/test_u1_executions_filters.py",
  "tests/test_u1_local_diag_cli_runtimes.py",
  "tests/test_u1_self_review.py",
  "tests/test_agent_prompt_registry.py",
  "tests/test_run_advisor.py",
  "tests/test_artifact_intake.py",
  "tests/test_v15_memory_channel.py",
  # Plan 22 V2
  "tests/test_u2_cost_metrics.py",
  "tests/test_u2_pipeline_orchestrator.py",
  "tests/test_u2_publish_review_mode.py",
  "tests/test_run_fingerprint.py",
  "tests/test_evals_promote.py",
  "tests/test_eval_gate_modes.py",
  "tests/conformance/test_runtime_conformance.py",
  # Plan 49 - Blindaje de calidad determinista
  "tests/test_golden_extraction.py",
  "tests/test_extraction_detects_pathologies.py",
  "tests/test_harness_ratchet_meta.py",
  "tests/test_no_determinism_sentinel.py",
  # Plan 50 - Saneamiento determinista de la epica + warnings
  "tests/test_epic_sanitize.py",
  "tests/test_epic_structure_warnings.py",
  "tests/test_catalog_grounding_warnings.py",
  # Plan 51 - Gates correctivos deterministas de epica
  "tests/test_epic_gate.py",
  "tests/test_golden_catalog_diff.py",
  # Plan 52 - Paridad runtimes autopublish + idempotencia comentarios
  "tests/test_run_brief_autopublish_parity.py",
  "tests/test_ado_comment_idempotency.py",
  "tests/test_issue_observability.py",
  "tests/test_persist_issue_ticket.py",
  # Plan 53 - Selector adaptativo de modelo/effort por confidence
  "tests/test_adaptive_selector.py",
  "tests/test_adaptive_selector_wiring.py",
  # Plan 54 - Memoria que empuja: paridad rejection_lessons 3 runtimes
  "tests/test_memory_prefix.py",
  "tests/test_base_prompt_parity.py",
  "tests/test_cli_memory_parity.py",
  "tests/test_rejection_sink.py",
  "tests/test_rejection_lessons_trim.py",
  # Plan 55 - Preview ejecutable portafolio epicas
  "tests/test_epic_payload_preview.py",
  "tests/test_epic_preview_endpoint.py",
  "tests/test_epic_portfolio_preview.py",
  # Plan 56 - Gate de regresion golden
  "tests/test_regression_capture.py",
  "tests/test_regression_goldens.py",
  "tests/test_regression_goldens_store.py",
  "tests/test_epic_gate_regression.py",
  # Plan 57 - FA-36 Especulacion anticipatoria
  "tests/test_speculative_hash.py",
  "tests/test_speculative_parity.py",
  "tests/test_speculative_flag.py",
  "tests/test_speculative_claim_flow.py",
  # Plan 58 - Bucle de convergencia de calidad determinista
  "tests/test_convergence_loop.py",
  "tests/test_convergence_wiring.py",
  # Plan 59 - Descomposicion vertical epica->hijos
  "tests/test_epic_decomposition.py",
  # Plan 60 - Aprendizaje bidireccional ediciones ADO
  "tests/test_ado_edit_diff.py",
  "tests/test_ado_edit_detect.py",
  "tests/test_ado_edit_ledger.py",
  "tests/test_ado_edit_learning.py",
  "tests/test_ado_edit_sweep.py",
  "tests/test_plan81_negative_golden_from_edits.py",
  # Plan 61 - Gate determinista del flujo funcional (Task)
  "tests/test_task_gate_flags.py",
  "tests/test_task_gate.py",
  "tests/test_create_child_task_gate.py",
  # Plan 68 - Paridad de visibilidad de streams Codex vs Claude (AD-1 stderr tail)
  "tests/test_cli_visibility_parity.py",
  # Clasificacion colateral (Plan 68): 2 tests preexistentes sin clasificar
  "tests/test_codex_prompt_dedup.py",
  "tests/test_prompt_dedup_guard.py",
  # Plan 67 - Disciplina de procesos: reusar por default
  "tests/test_process_discipline.py",
  # Plan 66 - Desatascador visibilidad total + subida forzada
  "tests/test_unblocker_board.py",
  # Plan 73 - Generador declarativo PipelineSpec->ADO/GitLab
  "tests/test_plan73_pipeline_spec.py",
  "tests/test_plan73_validate.py",
  "tests/test_plan73_render_ado.py",
  "tests/test_plan73_render_gitlab.py",
  "tests/test_plan73_repo_writer.py",
  "tests/test_plan73_generator_endpoint.py",
  "tests/test_plan73_routes_registered.py",
  "tests/test_plan73_round_trip.py",
  # Plan 74 — Migrador ADO→GitLab
  "tests/test_plan74_migrator_map.py",
  "tests/test_plan74_migrator_core.py",
  "tests/test_plan74_migrator_epics.py",
  "tests/test_plan74_migrator_attachments.py",
  "tests/test_plan74_migrator_executor.py",
  "tests/test_plan74_migrator_verify.py",
  "tests/test_plan74_migrator_api.py",
  "tests/test_plan74_migrator_wiring.py",
  "tests/test_plan74_migrator_idempotency.py",
  "tests/test_plan74_migrator_readonly_origin.py",
  "tests/test_plan74_routes_registered.py",
  # Plan 75 — Deep links bidireccionales GitLab
  "tests/test_plan75_deep_links_compose.py",
  "tests/test_plan75_gitlab_provider_urls.py",
  "tests/test_plan75_deep_links_epic_fallback.py",
  "tests/test_plan75_deep_links_bidirectional.py",
  "tests/test_plan75_deep_links_wiring.py",
  "tests/test_plan75_deep_links_no_double_encode.py",
  # Plan 76 — Eval codebase-memory-mcp
  "tests/test_plan76_codebase_memory_mcp.py",
  "tests/test_plan76_routes_registered.py",
  "tests/test_plan76_ratchet_byteidentical.py",
  # Plan 77 — Issue pipeline fases comentarios + color
  "tests/test_issue_phase_mapper.py",
  "tests/test_issue_phase_publisher.py",
  "tests/test_issue_no_children_guard.py",
  "tests/test_issue_phase_runtime_parity.py",
  "tests/test_harness_flags.py",
  # Plan 79 — Estados de tarea deterministas y configurables
  "tests/test_plan79_flag.py",
  "tests/test_plan79_resolver.py",
  "tests/test_plan79_safe_transition.py",
  "tests/test_plan79_apply_start.py",
  "tests/test_plan79_apply_final.py",
  "tests/test_plan79_centinela_estados.py",
  "tests/test_plan79_validate_states.py",
  "tests/test_plan79_agent_md_note.py",
  "tests/test_plan79_ratchet.py",
  # Plan 80 — Wiring real codebase-memory-mcp
  "tests/test_plan80_flags.py",
  "tests/test_plan80_wiring_pure.py",
  "tests/test_plan80_writer.py",
  "tests/test_plan80_codex.py",
  "tests/test_plan80_copilot.py",
  "tests/test_plan80_savings.py",
  "tests/test_plan80_status_shape.py",
  "tests/test_plan80_ratchet_byteidentical.py",
  "tests/test_plan80_routes_registered.py"
)

$pass = 0; $fail = 0; $missing = 0
$failed = @()

foreach ($f in $HarnessTestFiles) {
  if (-not (Test-Path $f)) {
    Write-Host "MISSING  $f"
    $missing++; $failed += "$f (missing)"; continue
  }
  & $python -m pytest $f -q | Out-Null
  if ($LASTEXITCODE -eq 0) {
    Write-Host "PASS     $f"; $pass++
  } else {
    Write-Host "FAIL     $f"; $fail++; $failed += $f
  }
}

Write-Host ""
Write-Host "===================== RESUMEN ARNES ====================="
Write-Host "PASS=$pass  FAIL=$fail  MISSING=$missing  TOTAL=$($HarnessTestFiles.Count)"
if ($fail -gt 0 -or $missing -gt 0) {
  Write-Host "Archivos con problema:"
  foreach ($ff in $failed) { Write-Host "  - $ff" }
  exit 1
}
Write-Host "Todos los archivos del arnes pasan aislados."
exit 0
