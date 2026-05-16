---
name: P1.A ADO-122 selector_contract activado
description: Stage selector_contract activado — BLOCKED/PIP cuando escenarios existen sin alias_semantic; override QA_UAT_SKIP_SELECTOR_CONTRACT=1
type: project
---

Stage `selector_contract` en `qa_uat_pipeline.py` ahora distingue tres casos:
1. Escenarios vacíos (plan vacío) → skip legítimo.
2. Escenarios sin alias_semantic (formato legacy) → BLOCKED/PIP/SELECTOR_CONTRACT_MISSING_INPUTS.
3. Escenarios con alias_semantic → validación activa vía `validate_all_scenarios`.

Override: `QA_UAT_SKIP_SELECTOR_CONTRACT=1` activa forced_skip y lo loguea en execution.jsonl.
Evento consolidado: `{"event": "selector_contract", "verdict": ..., "validated_count": N, "elapsed_ms": ...}`.

**Why:** En ticket 122 el stage quedaba siempre `skipped=true` porque los escenarios usaban formato pantalla/pasos (legacy). Un UI map desactualizado fallaba tarde (en el runner caro) en vez de temprano.

**How to apply:** Si en un ticket futuro selector_contract muestra skipped=true revisar si los escenarios tienen `screen` + `steps[].alias_semantic`. Si no → migrar o usar override explícito.
