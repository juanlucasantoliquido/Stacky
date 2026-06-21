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
  "tests/test_epic_decomposition.py"
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
