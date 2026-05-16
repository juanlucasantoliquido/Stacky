---
name: ADO-122 compilador v1.3.0 — formato dual
description: uat_scenario_compiler emite screen+steps[alias_semantic] junto con pantalla+pasos legacy; override QA_UAT_COMPILER_LEGACY_ONLY=1
type: project
---

uat_scenario_compiler.py migrado a v1.3.0 con emisión dual de formatos.

**Why:** el selector_contract activo necesita `screen` + `steps[].alias_semantic` para validar aliases. El compilador solo emitía `pantalla` + `pasos`, forzando uso de override QA_UAT_SKIP_SELECTOR_CONTRACT=1.

**How to apply:**
- Escenarios compilados ahora tienen ambos campos: `pantalla`/`pasos` (legacy) y `screen`/`steps` (v2).
- `steps[].alias_semantic` se infiere cruzando `paso.target` contra `ui_aliases`. Si no matchea → null (evento `compiler_alias_inference_miss` en logs).
- Override `QA_UAT_COMPILER_LEGACY_ONLY=1` emite solo legacy (sin v2 fields).
- Meta del resultado incluye `v2_schema_emitted` y `compiler_legacy_only`.
- Evals: `evals/scenario_compiler/` — 5 fixtures, runner `evals/run_scenario_compiler_evals.py`.
- Integración con selector_contract: compilar → validar → ALLOW cuando todos los aliases están en el UI map.
