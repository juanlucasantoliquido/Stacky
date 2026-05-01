---
name: Integración aditiva de módulos de observabilidad (F1-F4)
description: Patrón confirmado para extender Stacky sin romper la base estable.
type: feedback
---

Al integrar módulos de observabilidad (action_tracker, pipeline_events, sse_bus, error_classifier, ticket_scoring, estimation_store) en archivos de producción (pipeline_runner, copilot_bridge, dashboard_server, metrics_collector), siempre hacer imports defensivos con try/except a nivel módulo, y que la ausencia degrade a no-op en vez de romper el caller.

**Why:** Hubo un incidente con `git stash` donde la versión estable del usuario incluye features propias (Rally, Sync) en los mismos archivos. Cualquier cambio debe ser ADITIVO: si los módulos F1-F4 no están disponibles (o el tracker falla en runtime), el pipeline principal debe seguir funcionando normal. El tracking es observabilidad, no una dependencia dura.

**How to apply:**
- En cada sitio de integración, rodear el import con `try/except` y exponer un flag `_HAS_X`.
- Los wrappers (ej: `_invoke_with_tracking` en pipeline_runner, `_emit_progress` en copilot_bridge) deben ser no-op si el flag es False.
- En dashboard_server, importar los módulos DENTRO del handler del endpoint (no a nivel módulo) y retornar 503 con diagnóstico si falla.
- En CSS/JS del dashboard.html, usar prefijos propios (`sl-`, `scoring-`, `error-banner-`) y todo el JS en una IIFE que expone `window.SL`.
- Los 57 tests F1-F4 (tests/unit/test_action_tracker + test_pipeline_events + test_error_classifier + test_ticket_scoring + test_estimation_store + tests/integration/test_sse_bus) son el contrato que debe seguir pasando tras cualquier refactor.
