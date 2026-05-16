---
name: ADO-122 deployment_fingerprint — ticket_config.json resolver
description: resolve_expected_build() busca en QA_UAT_EXPECTED_BUILD (env JSON) → evidence/<ticket>/ticket_config.json → None (WARN legacy)
type: project
---

deployment_fingerprint.py extendido con resolver de expected_build por ticket.

**Why:** todos los runs del ticket 122 mostraban WARN/NO_EXPECTED_BUILD_DEFINED. El fingerprint nunca fallaba porque nunca tenía contra qué comparar — era un WARN inerte.

**How to apply:**
- `resolve_expected_build(ticket_id, evidence_root)` resuelve en orden:
  1. Env var `QA_UAT_EXPECTED_BUILD` (JSON string) — override por run.
  2. `evidence/<ticket>/ticket_config.json` campo `expected_build`.
  3. None → WARN (comportamiento legacy, no rompe tickets viejos).
- CLI helper: `python deployment_fingerprint.py set-expected --ticket N --commit X --build-number Y`.
- `ticket_config.json` schema: `{ticket_id, expected_build:{commit_sha, build_number, deploy_timestamp}, match_strategy, notes}`.
- qa_uat_pipeline.py usa resolve_expected_build antes de los env vars legacy.
- Evals: `evals/deployment_fingerprint/` — 6 fixtures, runner `evals/run_deployment_fingerprint_evals.py`.
- `ticket_config.json` ya existe en `evidence/122/` para el ticket 122 (escrito durante testing).
