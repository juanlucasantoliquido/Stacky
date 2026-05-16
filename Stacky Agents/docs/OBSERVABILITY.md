# Observabilidad del lifecycle de ejecuciones — Stacky Agents

Este documento describe los mecanismos de observación, recovery automático y
diagnóstico forense agregados por el plan de remediación del lifecycle
(Fases 0-5). Si una ejecución queda colgada o un ticket aparece "INCONSISTENTE"
en la UI, esto es lo que tenés que mirar.

---

## 1. Componentes en runtime

| Componente | Frecuencia | Qué hace | Cómo apagarlo |
|---|---|---|---|
| **Stale recovery reaper** | cada 120s | Recorre `AgentExecution` en `running`/`queued` y cierra los huérfanos (Casos A/B/C) | `STACKY_REAPER_ENABLED=false` |
| **Manifest watcher** | cada 2.0s | Polea `backend/data/codex_runs/<id>/MANIFEST.json`. Cierra runs cuyo manifest es terminal pero la DB sigue `running` | `STACKY_MANIFEST_WATCHER_ENABLED=false` |
| **Heartbeat thread** | cada 30s | Cada runner escribe `heartbeat.json` mientras vive | (no se apaga; lo emite el runner) |

Los tres se arman en `backend/app.create_app()`. Los flags se leen de variables
de entorno; los defaults son seguros para producción (todo ON).

---

## 2. Reaper — `recover_stale_running_tickets()`

Tres casos cubiertos, en este orden:

### Caso A — `execution_ended`
Ticket con `stacky_status='running'` pero su última `AgentExecution` ya está
terminal. Sincroniza el `stacky_status` con el outcome real.

### Caso B — `execution_timeout`
`AgentExecution` en `running` o `queued` con `started_at < now - STACKY_EXECUTION_TIMEOUT_MINUTES`.
Se marca `error` con `completion_source='recovery'`. Es la red de seguridad
absoluta — opera aunque no haya heartbeat.

### Caso C — `heartbeat_timeout`
`AgentExecution` en `running` con heartbeat **presente** pero su
`last_activity_ts` es más viejo que `STACKY_HEARTBEAT_TIMEOUT_MINUTES`.
**No** dispara si nunca hubo heartbeat (eso lo maneja el Caso B).
Esto evita regresar runtimes legacy que no soportan heartbeat.

---

## 3. Variables de entorno

| Variable | Default | Descripción |
|---|---|---|
| `STACKY_REAPER_ENABLED` | `true` | Arranca el daemon de stale recovery |
| `STACKY_REAPER_INTERVAL_SECONDS` | `120` | Cada cuánto corre el reaper |
| `STACKY_RECOVERY_ON_STARTUP` | depende de gateway | Recovery one-shot al arrancar |
| `STACKY_EXECUTION_TIMEOUT_MINUTES` | `120` | Timeout absoluto Caso B |
| `STACKY_MANIFEST_WATCHER_ENABLED` | `true` | Arranca el watcher de MANIFEST.json |
| `STACKY_MANIFEST_WATCHER_INTERVAL_SECONDS` | `2.0` | Periodo de polling del watcher |
| `STACKY_HEARTBEAT_TIMEOUT_MINUTES` | `10` | Edad máxima de heartbeat antes de stale |
| `STACKY_HEARTBEAT_STARTUP_GRACE_SECONDS` | `60` | Periodo de gracia tras arranque sin heartbeat |
| `STACKY_HEARTBEAT_INTERVAL_SECONDS` | `30` | Frecuencia con que el runner emite heartbeat |

---

## 4. Endpoints

### `GET /api/diag/execution/<id>`
Snapshot forense completo de una ejecución. Devuelve:

```json
{
  "ok": true,
  "execution": { "id": 42, "status": "running", "started_at": "...", "agent_type": "developer", "completion_source": null },
  "ticket": { "id": 5, "ado_id": 27698, "stacky_status": "running", "work_item_type": "Task" },
  "manifest": { "exists": true, "valid": true, "status": "completed", "signals": {...}, "exit_code": 0 },
  "heartbeat": { "exists": true, "last_activity_ts": "...", "age_seconds": 45, "pid": 1234, "phase": "running" },
  "recovery_history": [ { "old_status": "...", "new_status": "...", "changed_by": "system:reaper:...", "reason": "..." } ],
  "diagnosis": "alive",
  "recommended_action": null,
  "thresholds": { "heartbeat_timeout_minutes": 10, "startup_grace_seconds": 60 }
}
```

Diagnosis posibles:

| Diagnosis | Significado | Acción recomendada |
|---|---|---|
| `terminal_clean` | Estado terminal en DB coherente con MANIFEST | — |
| `terminal_no_manifest` | Terminal en DB pero falta MANIFEST en disco | — (sólo forense) |
| `alive` | Corriendo, heartbeat reciente | — |
| `starting` | Corriendo, sin heartbeat aún pero dentro del grace | — (esperar) |
| `manifest_orphan` | MANIFEST terminal pero DB en `running` | `POST /api/tickets/recover-stale-status` |
| `heartbeat_stale_no_manifest` | Heartbeat viejo, sin MANIFEST terminal | `POST /api/tickets/recover-stale-status` |
| `no_heartbeat_after_grace` | Nunca emitió heartbeat tras el grace | `POST /api/tickets/recover-stale-status` (o investigar el runtime) |
| `unknown` | Estado fuera del set conocido | — |

### `GET /api/diag/metrics`
Métricas operacionales. JSON con:

```json
{
  "ok": true,
  "executions_by_status": { "running": 2, "completed": 145, "error": 3 },
  "duration_ms": { "count": 200, "p50": 8500, "p95": 24000, "p99": 45000, "max": 60000 },
  "recoveries": { "heartbeat_timeout": 1, "execution_timeout": 0, "execution_ended": 12, "no_execution": 0 },
  "currently_running": 2,
  "oldest_running_age_seconds": 312.5,
  "thresholds": { "execution_timeout_minutes": 120, "heartbeat_timeout_minutes": 10, "startup_grace_seconds": 60 }
}
```

`duration_ms` se calcula sobre los últimos 200 runs `completed` (ventana
deslizante, no all-time).

---

## 5. SLOs y umbrales sugeridos

| Métrica | SLO | Alerta cuando |
|---|---|---|
| `executions_by_status.running` | < 3 simultáneas | > 5 por más de 10 min |
| `duration_ms.p50` | < 15 min | p50 > 20 min |
| `duration_ms.p99` | < 60 min | p99 > 90 min |
| `recoveries.heartbeat_timeout` | < 2 por hora | > 5 en 1 hora |
| `recoveries.execution_timeout` | 0 en condición estable | > 0 sostenido |
| `oldest_running_age_seconds` | < 7200s (2h) | > 7200s |

Si `recoveries.execution_timeout` empieza a subir, es señal de que los runs no
están escribiendo heartbeat (regresión en el runner) o de runtimes legacy
nuevos sin soporte de heartbeat — investigar antes de subir el threshold.

---

## 6. Artifacts en disco

Cada run tiene su carpeta `backend/data/codex_runs/<execution_id>/`:

| Archivo | Origen | Uso |
|---|---|---|
| `MANIFEST.json` | runner al terminar | Watcher cierra orphans usando este archivo |
| `heartbeat.json` | heartbeat thread mientras vive | Reaper detecta runs colgados |
| `events.jsonl` | runner en cada transición (append-only) | Forense post-mortem sin tocar DB |
| `last_message.md`, `prompt.md` | codex_cli_runner | Output y prompt del run |

`events.jsonl` ejemplo (una línea por evento):

```jsonl
{"ts": "2026-05-15T10:00:01Z", "execution_id": 42, "event_type": "process_started", "payload": {"pid": 12345, "agent_type": "developer"}}
{"ts": "2026-05-15T10:08:30Z", "execution_id": 42, "event_type": "completed", "payload": {"exit_code": 0, "duration_ms": 509000}}
```

---

## 7. Diagnóstico rápido — "¿por qué este run sigue en running?"

1. `GET /api/diag/execution/<id>` y mirar `diagnosis` + `recommended_action`.
2. Si `diagnosis == "alive"` → está vivo, esperar.
3. Si `diagnosis == "manifest_orphan"` → el watcher debería haberlo cerrado.
   Si persiste > 30s, hay bug en watcher; ver `backend/services/manifest_watcher.py`.
4. Si `diagnosis == "heartbeat_stale_*"` → proceso muerto. Trigger
   `POST /api/tickets/recover-stale-status` o esperar al próximo ciclo del reaper.
5. Si `diagnosis == "no_heartbeat_after_grace"` → el runtime nunca escribió
   heartbeat. Mirar logs del runner (`stacky_logger.agent_event`) en
   `system_logs`.

Para reconstruir la timeline forense sin DB, leer `events.jsonl` de la run dir.
