---
name: Project P5 Cutover State
description: Estado post-implementación P5 — gateway modo on, bloqueos resueltos, branches y commits
type: project
---

Estado al 2026-05-15: Fases A (bloqueos pre-P5) y B (P5 Cutover) implementadas.

## Branches y commits

| Branch | Tip Commit | Contenido |
|---|---|---|
| `fix/stacky-rescue-p0-execution-149` | `9fe22b8` | P0 ADO-149 rescate |
| `feat/stacky-gateway-p1-shadow` | `6e453bf` | P1 gateway shadow + fix CORS B3 |
| `feat/stacky-idempotency-p2` | `751c951` | P2 UNIQUE DB + completion_source |
| `feat/stacky-workflow-p3` | `21991ef` | P3 workflow.json + B5 developer.to=Done by AI |
| `feat/stacky-ui-recovery-p4` | `2eb731c` | P4 UI recovery |
| `chore/stacky-pre-p5-fixes` | `2674beb` | B1 vitest + B2 .env.example |
| `feat/stacky-cutover-p5` | `b17224d` | P5 gateway on + reaper + metrics |

**Topología:** P2 y P3 están en rama lateral desde c1b0078. P0/P1/P4 están en cadena lineal. P5 parte de P4.

**Merge order propuesto:** P2 → P3 → P1 → P4 → chore/pre-p5-fixes → P5.

**Ningún branch está mergeado en main (main = c1b0078).**

## Bloqueos resueltos

- **B1 (vitest):** Instalado en frontend. vite.config.ts actualizado. Script `test` agregado. 38 tests de P4 pasan.
- **B2 (.env.example):** Creado con VITE_STACKY_AGENT_TOKEN=. README actualizado con sección Variables + Tests.
- **B3 (CORS):** Fix en branch P1 (`6e453bf`). Agrega X-Stacky-Agent-Token, X-User-Email en allow_headers. X-Request-ID en expose_headers.
- **B5 (workflow.json):** developer.to cambiado de "Resolved" a "Done by AI" en P3 branch (`21991ef`). 15/15 tests P3 verdes.

## P5 implementado

**run_on() en agent_completion.py:** Transacción de 6 pasos real. Funciones auxiliares:
- `_close_execution()`: muta AgentExecution, completion_source='agent_gateway' defensivo
- `_publish_to_ado()`: llama ado_publisher, tolerante a falla (reaper reintenta)
- `_apply_workflow_transition()`: llama ado_workflow si disponible (P3), graceful fallback
- `_seal_audit()`: llama audit_chain.seal si disponible, fallback a SystemLog

**Legacy override auditado:** PATCH /stacky-status escribe completion_source='manual', SystemLog con correlation_id, gateway_active_warning=true si gateway=on.

**Reaper extendido:** recover_stale_running_tickets() ahora cierra executions con timeout (EXECUTION_TIMEOUT_MINUTES=120). Retorna list[dict] en lugar de int.

**stop_stale_recovery():** Shim de compatibilidad para tests (no-op).

**Métricas:** GET /api/metrics/agent-completion — counters desde system_logs.

**Tests P5:** 11/11 verdes en test_cutover_p5.py.

## Nota de deuda técnica (no bloqueante)

Los tests de P1 (test_agent_completion_gateway.py) tienen errores preexistentes:
- `stop_stale_recovery` ausente en P1 (solucionado en P5 con el shim)
- `AgentExecution.html_output_path` no existe en P1 (es campo de P2)
- Estos errores son anteriores a P5 y no fueron introducidos por los cambios

**Why:** Plan SSD §15 establece merge order P2→P3→P1→P4→P5. Los tests de P1 asumen campos de P2 que estarán cuando se mergee en orden.

**How to apply:** Al hacer merge de P2 antes de P1, los tests de P1 deberían pasar.
