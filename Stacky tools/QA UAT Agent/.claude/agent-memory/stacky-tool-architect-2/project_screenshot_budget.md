---
name: P1.B ADO-122 screenshot_budget
description: Budget de screenshots por step/escenario — reduce volumen desde ~56 PNG a ~28 en run nominal
type: project
---

Módulo `screenshot_budget.py` expone `ScreenshotBudget`, `load_budget()`, `should_capture()`, `build_ts_budget_block()`.
Template `playwright_test.spec.ts.j2` inyecta bloque TS `__shouldCapture()` + `__captureIfBudget()`.
`playwright_test_generator.py` pasa `screenshot_budget_block` al `template.render()` (ambos paths: normal y playbook).

Defaults: on_success_per_step=1, on_failure_per_step=3, max_total_per_scenario=25.
Override: `QA_UAT_SCREENSHOT_BUDGET_DISABLED=1` → modo legacy sin límite.
Evento: `screenshot_budget_summary` emitido vía `console.log(JSON.stringify(...))` al final de cada spec.

**Why:** Ticket 122 generó ~56 PNG (2 capturas × 7 pasos × 4 escenarios). Usuario percibió "un millón de screenshots". Sin valor diagnóstico en pasos exitosos.

**How to apply:** Si en un run futuro hay exceso de PNG, verificar que el budget está activo (`QA_UAT_SCREENSHOT_BUDGET_DISABLED` no está seteado). Si se necesita debug exhaustivo, usar la env var para revertir al comportamiento legacy.
