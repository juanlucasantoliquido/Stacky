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
  "tests/conformance/test_runtime_conformance.py"
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
