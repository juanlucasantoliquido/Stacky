---
name: P0 ADO-122 — rerun_guard stage 0
description: Gate contra reruns repetidos de BLOCKED/ENV sin cambio de ambiente — diseño, ubicación y contrato.
type: project
---

Implementado como stage 0 del pipeline (antes del preflight de ambiente).

**Motivación:** 17 runs del ticket 122 en 93 minutos, todos BLOCKED/ENV, sin cambio entre ellos. Cada run gastaba ~68s y producía artefactos sin valor informativo nuevo.

**Archivos:**
- `rerun_guard.py` — módulo principal, función `run_rerun_guard()` y `write_run_result()`
- `evals/rerun_guard/*.json` — 7 fixtures de eval
- `evals/run_rerun_guard_evals.py` — runner de evals (patrón idéntico a auth_session)
- `qa_uat_pipeline.py` — integración: `_write_run_result_for_guard()` + stage 0 en `run()` + `--force-rerun` en `_parse_args()`

**Contrato clave:**
- Lee `evidence/{ticket}/latest_run_result.json` (escrito por el pipeline al finalizar cada run)
- Bloquea si: elapsed < TTL(600s) AND verdict==BLOCKED AND category==ENV AND fingerprint no cambió
- Override: `--force-rerun` o env var `QA_UAT_FORCE_RERUN=1`
- Fail-open: si rerun_guard falla por excepción, el pipeline continúa (no bloquea)

**Verdicts:** OK | BLOCKED/OPS/PREVIOUS_RUN_SAME_VERDICT | OK_OVERRIDE (forced)

**Why:** Reducir runs desperdiciados (métrica: unknown_verdict_count, blocked_without_reason_count, cost_per_actionable_failure).

**How to apply:** Cuando el pipeline vuelva a tener BLOCKED/ENV repetidos, verificar que `latest_run_result.json` se escribe correctamente en `_finalize_run_manifest`.
