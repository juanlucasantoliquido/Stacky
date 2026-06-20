# Cutover P5 — Gateway AgentCompletion en modo `on`

**Versión:** 1.0
**Fase:** P5 — Cutover
**Referencia:** 10_PLAN_CIERRE_PUBLICACION_AGENTES.md §5.4, §15

---

## Pre-requisitos

Antes de hacer el cutover a modo `on`, confirmar que:

1. Las ramas P0, P1, P2, P3, P4 y P5 estén mergeadas en main (merge order: P2 → P3 → P1 → P4 → chore/pre-p5-fixes → P5).
2. El `workflow.json` de cada proyecto esté correcto:
   - PACIFICO: `developer.to = "Done by AI"`, `functional.to = "Doing"`, `technical.to = "To Do"`.
   - Verificar con `tests/test_ado_workflow.py` (W01, W14).
3. La migración de DB de P2 esté aplicada (`UNIQUE` en `AgentHtmlPublish`, `completion_source` en `AgentExecution`).
4. El token `STACKY_AGENT_TOKEN` esté seteado en prod y compartido con los agentes (y el frontend a través de `VITE_STACKY_AGENT_TOKEN`).
5. La suite de tests esté verde: `python -m pytest tests/ -q` (backend) y `npm test` (frontend).

---

## Pasos de cutover

### Paso 1 — Validar en shadow (recomendado: 24-72 horas)

```
STACKY_COMPLETION_GATEWAY=shadow
```

- Los agentes siguen usando el flujo legacy, pero el gateway corre en paralelo y registra discrepancias en `system_logs` (`action='shadow.discrepancy_detected'`).
- Verificar que `stacky_shadow_discrepancy_total` en `/api/metrics/agent-completion` sea 0 o bajo.
- Si hay discrepancias, investigar antes de continuar.

### Paso 2 — Setear el token en producción

Configurar la variable de entorno del backend:
```
STACKY_AGENT_TOKEN=<valor_seguro_generado>
```

Y en el frontend (si aplica):
```
VITE_STACKY_AGENT_TOKEN=<mismo_valor>
```

El token debe generarse con `python -c "import secrets; print(secrets.token_urlsafe(32))"` o similar.

### Paso 3 — Habilitar el gateway en modo `on`

Cambiar en la configuración del servidor:
```
STACKY_COMPLETION_GATEWAY=on
STACKY_RECOVERY_ON_STARTUP=true
EXECUTION_TIMEOUT_MINUTES=120
```

Reiniciar el proceso Flask.

### Paso 4 — Verificar post-switch

Inmediatamente después del restart:
- Confirmar que `/api/health` responde 200.
- Revisar logs del startup para "startup recovery".
- Invocar `/api/metrics/agent-completion` y confirmar que `mode_breakdown.on` empieza a crecer.
- Ejecutar un agente de prueba (developer o functional) y verificar que:
  - La `AgentExecution` queda en `completed`.
  - Aparece un comentario HTML en ADO.
  - `stacky_status` del ticket queda correcto.
  - `completion_source = 'agent_gateway'` en la `AgentExecution`.

### Paso 5 — Monitor continuo (primeros 7 días)

Revisar diariamente:
- `GET /api/metrics/agent-completion?since_hours=24`
- Buscar `gateway_active_warning=true` en system_logs (indica uso de legacy override mientras gateway activo).
- Verificar que `stacky_execution_orphans_detected_total` no crezca.

---

## Kill switch (revertir sin downtime)

Si el gateway en modo `on` causa problemas:

1. Cambiar `STACKY_COMPLETION_GATEWAY=shadow` → el gateway deja de mutar ADO/DB. El legacy `PATCH /stacky-status` sigue funcionando y toma control.
2. O bien `STACKY_COMPLETION_GATEWAY=off` → el endpoint `agent-completion` devuelve 404. Solo el legacy opera.
3. Reiniciar el proceso.

No hay pérdida de datos: la DB no requiere rollback. Las `AgentExecution` que quedaron en `running` serán recuperadas por el reaper en el siguiente startup.

---

## Troubleshooting

| Error code | Causa | Acción |
|---|---|---|
| `ticket_not_found` | ADO ID no está en DB local | Forzar sync: `POST /api/tickets/sync` |
| `no_active_execution` | No hay AgentExecution running para el ticket | Verificar que el agente inició la ejecución correctamente. Revisar `agent_executions` |
| `execution_state_invalid` | La execution ya está en estado terminal | Puede ser replay; verificar si es idempotente |
| `html_invalid` | El HTML generado por el agente no pasa validación | Revisar el output del agente. Abrir ticket para el agente Developer |
| `auth_required` | Falta `X-Stacky-Agent-Token` o es incorrecto | Verificar que el agente tiene el token correcto (mismo que `STACKY_AGENT_TOKEN` del backend) |
| `internal_error` | Error no controlado en el gateway | Buscar `correlation_id` en system_logs |

---

## Rollback de DB (si aplica)

Las migraciones de P2 (UNIQUE en AgentHtmlPublish, completion_source) son aditivas. Para revertir:
1. Remover la columna `completion_source` con una migración Alembic de downgrade.
2. Remover el constraint UNIQUE de `AgentHtmlPublish`.

Ambas operaciones son seguras (los datos existentes no se pierden).

---

## Fuera de alcance en P5

- Remoción del endpoint legacy `PATCH /stacky-status` → se planifica en plan derivado.
- Migración de Jira/Mantis → plan derivado.
- UI de administración del `workflow.json` → se edita por PR.
