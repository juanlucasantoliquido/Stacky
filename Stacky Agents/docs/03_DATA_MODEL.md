# 03 — Modelo de datos

## Tablas

```
┌────────────────────────────┐         ┌────────────────────────────┐
│ tickets                    │         │ agent_executions           │
├────────────────────────────┤         ├────────────────────────────┤
│ id          PK             │ 1     n │ id           PK            │
│ ado_id      UNIQUE         │◀────────│ ticket_id    FK            │
│ project                    │         │ agent_type                 │
│ title                      │         │ status                     │
│ description                │         │ input_context  JSON        │
│ ado_state                  │         │ chain_from     JSON (ids)  │
│ ado_url                    │         │ output         TEXT        │
│ priority                   │         │ output_format              │
│ last_synced_at             │         │ metadata_json  JSON        │
└────────────────────────────┘         │ error_message              │
                                       │ started_by                 │
                                       │ started_at                 │
                                       │ completed_at               │
                                       │ verdict                    │
                                       │ pack_run_id    FK NULL     │
                                       │ pack_step                  │
                                       └────────────────────────────┘
                                                   │ n
                                                   │
                                                   │ 1
                                                   ▼
                                       ┌────────────────────────────┐
                                       │ pack_runs                  │
                                       ├────────────────────────────┤
                                       │ id           PK            │
                                       │ pack_definition_id         │
                                       │ ticket_id    FK            │
                                       │ status                     │
                                       │ current_step               │
                                       │ options      JSON          │
                                       │ started_by                 │
                                       │ started_at                 │
                                       │ completed_at               │
                                       └────────────────────────────┘

┌────────────────────────────┐
│ execution_logs             │
├────────────────────────────┤
│ id           PK            │
│ execution_id FK            │  (índice por execution_id, timestamp)
│ timestamp                  │
│ level                      │
│ message                    │
│ group_name                 │
│ indent                     │
└────────────────────────────┘

┌────────────────────────────┐
│ users                      │
├────────────────────────────┤
│ id           PK            │
│ email        UNIQUE        │
│ name                       │
│ created_at                 │
└────────────────────────────┘
```

---

## DDL completo (SQLite / Postgres-compatible)

```sql
CREATE TABLE tickets (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  ado_id              INTEGER NOT NULL UNIQUE,
  project             VARCHAR(80) NOT NULL,
  title               VARCHAR(500) NOT NULL,
  description         TEXT,
  ado_state           VARCHAR(40),
  ado_url             VARCHAR(400),
  priority            INTEGER,
  last_synced_at      TIMESTAMP,
  created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_tickets_project_state ON tickets(project, ado_state);

CREATE TABLE users (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  email               VARCHAR(200) NOT NULL UNIQUE,
  name                VARCHAR(200),
  created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE pack_runs (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  pack_definition_id  VARCHAR(50) NOT NULL,         -- ej: "desarrollo", "qa-express"
  ticket_id           INTEGER NOT NULL REFERENCES tickets(id),
  status              VARCHAR(20) NOT NULL,         -- running | paused | completed | abandoned | error
  current_step        INTEGER NOT NULL,             -- 1-based
  options             TEXT,                         -- JSON
  started_by          VARCHAR(200) NOT NULL,
  started_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  completed_at        TIMESTAMP
);
CREATE INDEX ix_pack_runs_ticket_status ON pack_runs(ticket_id, status);

CREATE TABLE agent_executions (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  ticket_id           INTEGER NOT NULL REFERENCES tickets(id),
  agent_type          VARCHAR(20) NOT NULL,         -- business | functional | technical | developer | qa
  status              VARCHAR(20) NOT NULL,         -- queued | running | completed | error | cancelled | discarded
  verdict             VARCHAR(20),                  -- approved | discarded | NULL
  input_context       TEXT NOT NULL,                -- JSON: list[ContextBlock]
  chain_from          TEXT,                         -- JSON: list[execution_id]
  output              TEXT,
  output_format       VARCHAR(20) DEFAULT 'markdown',
  metadata_json       TEXT,                         -- JSON: tokens, model, sub_agents, duration_ms
  error_message       TEXT,
  started_by          VARCHAR(200) NOT NULL,
  started_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  completed_at        TIMESTAMP,
  pack_run_id         INTEGER REFERENCES pack_runs(id),
  pack_step           INTEGER
);
CREATE INDEX ix_exec_ticket_started ON agent_executions(ticket_id, started_at DESC);
CREATE INDEX ix_exec_ticket_agent_status ON agent_executions(ticket_id, agent_type, status);
CREATE INDEX ix_exec_pack_run ON agent_executions(pack_run_id);
CREATE INDEX ix_exec_status_started ON agent_executions(status, started_at);

CREATE TABLE execution_logs (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  execution_id        INTEGER NOT NULL REFERENCES agent_executions(id) ON DELETE CASCADE,
  timestamp           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  level               VARCHAR(10) NOT NULL,         -- debug | info | warn | error
  message             TEXT NOT NULL,
  group_name          VARCHAR(80),
  indent              INTEGER DEFAULT 0
);
CREATE INDEX ix_logs_exec_ts ON execution_logs(execution_id, timestamp);
```

---

## Estructura del campo `input_context` (JSON)

Lista de bloques de contexto, cada uno con metadata para que la UI los pueda re-hidratar:

```json
[
  {
    "id": "ticket-meta",
    "kind": "auto",
    "title": "Ticket metadata",
    "content": "Title: RF-008 nuevo flujo...\nType: Task\nState: Tech review\nPriority: 2",
    "source": { "type": "ticket", "ticket_id": 1234 }
  },
  {
    "id": "functional-analysis",
    "kind": "auto",
    "title": "Análisis funcional aprobado",
    "content": "# Análisis funcional RF-008\n## Cobertura: GAP MENOR\n...",
    "source": { "type": "execution", "execution_id": 20 }
  },
  {
    "id": "tech-docs",
    "kind": "choice",
    "title": "Documentación técnica selectiva",
    "items": [
      { "selected": true,  "label": "trunk/OnLine/Cobranzas/CobranzaController.cs" },
      { "selected": true,  "label": "trunk/lib/Pacifico.Common/CobranzaService.cs" },
      { "selected": false, "label": "trunk/Batch/CobranzaBatch/" }
    ],
    "source": { "type": "code-tree" }
  },
  {
    "id": "notes",
    "kind": "editable",
    "title": "Notas adicionales",
    "content": "Tener en cuenta que el cliente pidió compatibilidad con clientes mobile...",
    "source": { "type": "user-input" }
  }
]
```

**Por qué guardamos los bloques y no sólo el prompt final:**
1. Trazabilidad: en una auditoría podemos decir exactamente qué bloque venía de dónde.
2. Re-run con edición: el editor puede reconstruir el estado exacto.
3. Diff entre execs: si dos execs del mismo agente difieren, podemos mostrar qué bloque cambió, no qué caracteres.
4. El prompt final se reconstruye determinísticamente con `prompt_builder.build(blocks, agent_type)`.

---

## Estructura de `metadata_json`

```json
{
  "model": "claude-sonnet-4-6",
  "tokens_in": 8421,
  "tokens_out": 1812,
  "duration_ms": 14037,
  "sub_agents": [
    { "name": "explore-online", "duration_ms": 3120, "files_inspected": 4 },
    { "name": "explore-batch",  "duration_ms": 102,  "skipped_reason": "no batch in scope" },
    { "name": "docs-lookup",    "duration_ms": 1840 }
  ],
  "db_queries": [
    { "query_hash": "a3f2...", "rows": 24, "duration_ms": 18 }
  ],
  "warnings": [],
  "cost_usd_estimate": 0.041
}
```

---

## Queries operativas frecuentes

### Listar ejecuciones por ticket (más recientes primero)
```sql
SELECT id, agent_type, status, verdict, started_by, started_at, completed_at
FROM agent_executions
WHERE ticket_id = ?
ORDER BY started_at DESC
LIMIT 50;
```

### Última exec aprobada de un agente para un ticket
```sql
SELECT *
FROM agent_executions
WHERE ticket_id = ? AND agent_type = ? AND verdict = 'approved'
ORDER BY started_at DESC
LIMIT 1;
```

Esta query es la base del **auto-fill**: cuando el operador selecciona "Technical", buscamos la última exec aprobada de "Functional" para ese ticket y la incrustamos como bloque `auto`.

### Diff entre dos execs del mismo agente
```sql
SELECT id, started_at, output
FROM agent_executions
WHERE id IN (?, ?) AND ticket_id = ? AND agent_type = ?;
```

### Métricas — duración promedio por agente
```sql
SELECT agent_type,
       COUNT(*) AS total,
       AVG((julianday(completed_at) - julianday(started_at)) * 86400) AS avg_seconds,
       SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS errors,
       SUM(CASE WHEN verdict='approved' THEN 1 ELSE 0 END) AS approved
FROM agent_executions
WHERE started_at > date('now','-30 day')
GROUP BY agent_type;
```

---

## Migraciones

Usamos **Alembic** desde el día 1 (aunque empecemos con SQLite). Ventaja: cuando saltemos a Postgres, sólo cambia la URL.

```
backend/migrations/
├── env.py
├── alembic.ini
└── versions/
    └── 001_initial.py
```

Convención:
- 1 migration por feature (no acumular cambios sueltos).
- `down_revision` siempre apuntando explícitamente.
- Las migrations no destruyen data sin opt-in explícito en el nombre del archivo (`002_drop_legacy_logs.py`).

---

## Política de retención

| Tabla | Retención | Acción al expirar |
|---|---|---|
| `agent_executions` | indefinida | nunca borrar |
| `execution_logs` | 90 días | archivar a S3/blob, borrar de BD |
| `pack_runs` | indefinida | nunca borrar |
| `tickets` | mientras existan en ADO | sync periódico, no borramos |

---

## Estados y transiciones — `agent_executions.status`

```
        queued              ← (estado opcional, sólo si hay queue futura)
          │
          ▼
       running
          │
   ┌──────┼──────────┬─────────────┐
   ▼      ▼          ▼             ▼
completed error  cancelled   discarded
   │
   ▼
 verdict ∈ { approved, discarded, NULL }
```

- `discarded` como status (alguien marca la exec como descartada antes de que termine — raro pero soportado).
- `discarded` como verdict (la exec terminó ok pero el humano la rechazó después de leer).
- Una exec `completed` puede pasar a verdict `approved` o `discarded` por acción del usuario; nunca vuelve a `running`.

---

## Estados y transiciones — `pack_runs.status`

```
running ◀──── (al iniciar)
   │
   ├─▶ paused ─────────▶ running (resume)
   │
   ├─▶ completed (paso final aprobado)
   │
   ├─▶ abandoned (usuario aborta)
   │
   └─▶ error (paso falló y opción "stop on error")
```

`current_step` se incrementa al aprobar el paso actual. Al alcanzar `total_steps`, status pasa a `completed`.

---

## Concurrencia: locks

Para SQLite usamos transacciones cortas. Para Postgres futuro:
- `SELECT ... FOR UPDATE SKIP LOCKED` cuando armemos una queue real.
- Por ahora: optimistic locking en `pack_runs.current_step` con un `WHERE current_step = ?` en el UPDATE para detectar carreras (operador A y operador B avanzan el mismo paso al mismo tiempo).

---

## Datos sensibles

- `agent_executions.input_context` puede contener fragmentos de código y datos de BD (de SELECT). **No** debe contener PII de clientes.
- Política: las queries SELECT del agente Technical pueden devolver datos reales para enriquecer pruebas; el agente debe limitar a 5 filas y enmascarar campos `dni`, `cuit`, `email` antes de almacenarlos en `metadata_json.db_queries.preview`.
- En logs: nunca persistir el system prompt completo del LLM (puede contener secrets si se inyectaron por error). Sí el user prompt.

---

## Tamaño esperado y escala

Estimaciones:

| Métrica | Hoy | 6 meses |
|---|---|---|
| Tickets activos / mes | 50 | 300 |
| Execs / ticket promedio | 6 | 8 |
| Execs totales / mes | 300 | 2.400 |
| Tamaño promedio de output | 8 KB | 12 KB |
| Tamaño total de BD / año | ~50 MB | ~500 MB |

SQLite aguanta cómodamente. Migración a Postgres recién cuando:
- > 5 usuarios concurrentes,
- > 100 execs/día,
- o cuando se quiera una réplica de lectura.

---

## Datos de seed (dev)

`backend/scripts/seed_dev.py` carga:
- 5 tickets dummy con metadata creíble.
- 1 user `dev@local`.
- 0 ejecuciones (para que el operador haga las primeras a mano y vea el flujo).
