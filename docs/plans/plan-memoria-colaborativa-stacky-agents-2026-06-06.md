# Plan: memoria colaborativa versionada para Stacky Agents

| Campo | Valor |
|---|---|
| Fecha | 2026-06-06 |
| Estado | Propuesto |
| Alcance | Stacky Agents backend, frontend, runners, Git sync, memoria de proyecto, validador de memoria, observabilidad pre-run |
| Objetivo | Incorporar una capa de memoria colaborativa inspirada en Engram, versionada en Git, segura para varios desarrolladores/analistas, validable desde Stacky y sincronizada antes de cada ejecucion sin que el agente tenga que hacerlo. |

## 1. Resumen ejecutivo

Stacky Agents debe pasar de guardar solo ejecuciones y outputs a mantener una memoria operativa compartida del proyecto. Esa memoria debe capturar decisiones, patrones, bugs aprendidos, preferencias, restricciones, politicas de cliente y resumenes de sesiones. Debe ser buscable, inyectable como contexto, sincronizable por Git y auditable por un agente validador.

La regla de producto es:

> Stacky Agents es duenio de la memoria y de la sincronizacion Git. El agente no debe hacer `git pull`, no debe exportar memoria y no debe resolver conflictos de repositorio por su cuenta.

Antes de cada ejecucion Stacky debe mostrar una etapa visible en la UI, con spinner y texto de progreso:

```text
Sincronizando proyecto...
- Actualizando memoria compartida
- Importando nuevas memorias
- Ejecutando git pull del workspace
- Buscando contexto relevante
```

Si todo esta correcto, el desarrollador solo ve progreso. Si hay un bloqueo real, Stacky falla antes de lanzar el agente y muestra un diagnostico accionable.

## 2. Principios de diseno

1. **Local-first, Git-shared**: la DB local sigue siendo la fuente rapida para busqueda; Git transporta eventos/mutaciones append-only.
2. **Append-only para evitar conflictos**: ningun usuario modifica archivos de memoria ya publicados. Cada sync agrega nuevos chunks.
3. **Stacky-owned, agent-agnostic**: el agente consume contexto, pero no administra Git ni almacenamiento.
4. **No data loss**: `git pull` nunca debe hacer merge destructivo, stash silencioso riesgoso o sobrescribir cambios del usuario.
5. **Memoria curada, no ruido bruto**: se guardan observaciones utiles, no cada tool call ni cada log.
6. **Validacion continua**: una memoria puede entrar como `draft` o `active`, pero puede quedar `quarantined`, `superseded` o `rejected` por el validador.
7. **Trazabilidad completa**: cada memoria sabe de donde viene: ejecucion, ticket, usuario, agente, commit, branch, chunk Git.
8. **Inyeccion conservadora**: solo se inyectan memorias `active`, no vencidas, no superseded y no quarantined.
9. **Privacidad explicita**: `scope=personal` no se exporta a Git salvo opt-in; secretos y PII se bloquean antes de exportar.
10. **Fallo temprano**: si el repo no se puede actualizar de forma segura, Stacky no lanza el agente con contexto viejo.

## 3. Arquitectura objetivo

```text
Frontend React
  |
  | POST /api/agents/run
  v
Backend Flask
  |
  | 1. PreRunOrchestrator
  |      - Memory Git pull/import
  |      - Workspace git pull
  |      - Memory context search
  |
  | 2. agent_runner
  |      - context_enrichment agrega stacky-memory
  |      - BaseAgent.compose_system_prompt inyecta reglas fuertes
  |
  | 3. post-run hooks
  |      - candidate memory extraction
  |      - memory save/upsert
  |      - memory export queue
  |
  v
SQLite local
  |
  | background MemorySyncWorker
  v
Git memory worktree / branch
```

Componentes nuevos:

| Componente | Responsabilidad |
|---|---|
| `services/memory_store.py` | CRUD de memorias, busqueda FTS5, topic_key, relaciones, estados |
| `services/memory_git_sync.py` | Import/export append-only de chunks versionados en Git |
| `services/pre_run_sync.py` | Etapa obligatoria previa a cada run: memory pull + workspace pull |
| `services/memory_validator.py` | Scans deterministas y opcional LLM para inconsistencias |
| `api/memory.py` | Endpoints de memoria, busqueda, validacion, triage |
| `api/pre_run.py` | Snapshot de progreso y diagnostico pre-run |
| `frontend/pages/MemoryPage.tsx` | UI para memoria por proyecto |
| `frontend/components/PreRunProgress.tsx` | Spinner/estado visible antes de lanzar agente |

## 4. Flujo antes de cada ejecucion

### 4.1 Flujo normal

```text
Usuario clickea Run
        |
        v
Stacky crea AgentExecution en estado preparing
        |
        v
PreRunOrchestrator adquiere locks por proyecto
        |
        +-- Memory sync:
        |     git fetch/pull del worktree de memoria
        |     importa chunks nuevos a SQLite
        |
        +-- Workspace sync:
        |     verifica repo, branch, upstream
        |     git fetch
        |     git pull --ff-only segun policy
        |
        +-- Context search:
              busca memorias relevantes
              arma bloque stacky-memory
        |
        v
AgentExecution pasa a running
        |
        v
Se ejecuta el agente
```

Estados propuestos para `AgentExecution.status`:

```text
preparing
running
completed
error
cancelled
discarded
```

Metadata nueva en `AgentExecution.metadata_json`:

```json
{
  "pre_run": {
    "memory_sync": {
      "status": "ok",
      "imported_chunks": 3,
      "imported_memories": 17,
      "git_before": "abc1234",
      "git_after": "def5678"
    },
    "workspace_pull": {
      "status": "ok",
      "repo": "N:/GIT/RS/CLIENTE/Repo",
      "branch": "feature/ado-241",
      "upstream": "origin/feature/ado-241",
      "before": "1122334",
      "after": "7788990",
      "mode": "ff_only_block_on_dirty"
    },
    "memory_context": {
      "hits": 8,
      "active_hits": 6,
      "suppressed_hits": 2
    }
  }
}
```

### 4.2 UI visible

El usuario debe ver un overlay o panel compacto:

```text
Preparando ejecucion

[spinner] Actualizando memoria compartida...
[ok]      17 memorias importadas
[spinner] Actualizando workspace con git pull...
[ok]      branch feature/ado-241 actualizado
[spinner] Buscando memoria relevante...
[ok]      6 memorias vigentes encontradas
```

Si falla:

```text
No se lanzo el agente

Stacky no pudo actualizar el workspace de forma segura.
Motivo: hay cambios locales sin commitear.

Opciones:
- Guardar o commitear los cambios y reintentar.
- Cambiar la politica del proyecto a dedicated_worktree.
- Ejecutar desde un workspace limpio.
```

El agente nunca recibe el error como una tarea a resolver. Stacky bloquea antes.

## 5. Git pull obligatorio del workspace

### 5.1 Regla base

Antes de cada run, Stacky debe intentar actualizar el workspace del proyecto. La implementacion segura debe ser:

```text
git rev-parse --show-toplevel
git status --porcelain=v1
git rev-parse --abbrev-ref HEAD
git rev-parse --abbrev-ref --symbolic-full-name @{u}
git fetch --prune
git pull --ff-only
```

No se permite `git pull` con merge automatico. No se permite resolver conflictos automaticamente.

### 5.2 Politicas por proyecto

Agregar en `projects/<name>/config.json`:

```json
{
  "git_sync": {
    "enabled": true,
    "required_before_run": true,
    "workspace_policy": "ff_only_block_on_dirty",
    "memory_policy": "auto_pull_import_export",
    "timeout_seconds": 60,
    "show_spinner": true
  }
}
```

Politicas soportadas:

| Politica | Descripcion | Default | Riesgo |
|---|---|---|---|
| `ff_only_block_on_dirty` | Pull solo si el working tree esta limpio. Si hay cambios locales, bloquea el run. | Si | Bajo |
| `ff_only_autostash` | Usa `git pull --ff-only --autostash`. Solo habilitable por admin. | No | Medio |
| `dedicated_worktree` | Ejecuta agentes en un worktree administrado por Stacky, siempre limpio. | Recomendado para equipos | Bajo |
| `fetch_only_warn` | Solo fetch; permite run con warning. | No para prod | Medio |

Decision recomendada:

```text
MVP: ff_only_block_on_dirty
Produccion madura: dedicated_worktree
```

### 5.3 Locks de repositorio

Debe existir un lock por workspace:

```text
Stacky/data/locks/git/<project_hash>.lock
```

Reglas:

1. Solo una ejecucion por proyecto puede hacer pull al mismo tiempo.
2. Otras ejecuciones esperan hasta `timeout_seconds`.
3. Si timeout, el run queda `error` con `pre_run.workspace_pull.status=timeout`.
4. El lock debe tener lease y PID para recovery.

### 5.4 Casos de fallo cubiertos

| Caso | Comportamiento |
|---|---|
| Repo sin upstream | Bloquear run; mostrar "branch sin upstream" |
| Working tree dirty | Bloquear en default; no stashear sin policy admin |
| Pull requiere merge | Bloquear; exigir rebase/merge humano |
| Conflicto durante autostash | Bloquear; dejar instrucciones y no lanzar agente |
| Repo no Git | Permitir solo si config `git_sync.enabled=false`; si no, bloquear |
| Network caida | Bloquear si `required_before_run=true`; retry manual |
| Git no instalado | Bloquear con diagnostico de instalacion |
| Credenciales vencidas | Bloquear y mostrar comando sugerido para reautenticar |
| Pull tarda demasiado | Cancelar proceso, liberar lock, marcar timeout |

## 6. Memoria colaborativa en Git

### 6.1 No usar el branch de trabajo como storage primario

Para evitar mezclar memoria con cambios de codigo, la recomendacion es usar un worktree dedicado administrado por Stacky:

```text
<STACKY_HOME>/memory_worktrees/<project>/
```

Ese worktree apunta al mismo remoto del proyecto, pero a una rama dedicada:

```text
stacky-memory/<project>
```

Ventajas:

1. No ensucia el branch de desarrollo.
2. Stacky puede hacer pull/push de memoria sin tocar archivos del usuario.
3. Los conflictos se reducen porque los archivos son append-only.
4. Permite permisos separados en Git si el equipo lo necesita.

Fallback permitido:

```text
repo/.stacky/memory/
```

Solo usarlo si el equipo acepta versionar memorias dentro del branch de codigo.

### 6.2 Estructura append-only

```text
.stacky-memory/
  schema.json
  chunks/
    2026/
      06/
        06/
          mem-20260606T153012Z-juan-dev-a1b2c3d4.jsonl.gz
          mem-20260606T153117Z-ana-fa-b5c6d7e8.jsonl.gz
  relations/
    2026/
      06/
        rel-20260606T154000Z-validator-1122aabb.jsonl.gz
  tombstones/
    2026/
      06/
        tomb-20260606T160000Z-validator-9988ccdd.jsonl.gz
  indexes/
    README.md
```

Regla estricta:

> Los archivos dentro de `chunks`, `relations` y `tombstones` nunca se modifican despues de publicados.

No se necesita un `manifest.json` global obligatorio para importar. Stacky descubre chunks por nombre y los dedupea por `chunk_id` y checksum. Si se quiere un indice, debe ser generado y no autoritativo, o debe particionarse por autor:

```text
indexes/by-author/<author_hash>.json
```

Esto evita que varios usuarios editen el mismo manifest.

### 6.3 Formato de chunk

Cada chunk es JSONL comprimido. Cada linea es una mutacion:

```json
{
  "schema_version": 1,
  "mutation_id": "mut-01J...",
  "entity": "memory_observation",
  "op": "upsert",
  "occurred_at": "2026-06-06T15:30:12Z",
  "project": "PACIFICO",
  "actor": {
    "user_email": "dev@empresa.com",
    "display_name": "Dev",
    "role": "developer"
  },
  "source": {
    "kind": "agent_execution",
    "execution_id": 241,
    "ticket_id": 88,
    "ado_id": 27698,
    "agent_type": "developer",
    "workspace_commit": "abc1234"
  },
  "payload": {
    "memory_id": "mem-01J...",
    "type": "bugfix",
    "title": "Fixed output artifact detection for Developer completion",
    "content": "What: ...\nWhy: ...\nWhere: ...\nLearned: ...",
    "scope": "project",
    "topic_key": "bug/output-artifact-detection",
    "status": "active",
    "tags": ["ado", "developer", "output-watcher"]
  }
}
```

### 6.4 Import idempotente

Tablas locales:

```sql
CREATE TABLE stacky_memory_chunks (
  chunk_id TEXT PRIMARY KEY,
  project TEXT NOT NULL,
  path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  imported_at DATETIME NOT NULL,
  imported_by TEXT,
  status TEXT NOT NULL DEFAULT 'imported',
  error_message TEXT
);

CREATE TABLE stacky_memory_mutations (
  mutation_id TEXT PRIMARY KEY,
  chunk_id TEXT NOT NULL,
  entity TEXT NOT NULL,
  op TEXT NOT NULL,
  project TEXT NOT NULL,
  occurred_at DATETIME NOT NULL,
  actor_json TEXT,
  source_json TEXT,
  payload_json TEXT NOT NULL,
  applied_at DATETIME,
  apply_status TEXT NOT NULL DEFAULT 'pending',
  error_message TEXT,
  FOREIGN KEY(chunk_id) REFERENCES stacky_memory_chunks(chunk_id)
);
```

Reglas:

1. Si `chunk_id` ya existe con mismo sha, se saltea.
2. Si `chunk_id` existe con distinto sha, se marca `tampered` y se bloquea import.
3. Si `mutation_id` ya existe, se saltea.
4. Si una mutacion referencia una memoria inexistente, queda `deferred`.
5. Si falla 5 veces, queda `dead` y aparece en diagnostico.

### 6.5 Export y push

Cuando Stacky crea memorias locales, no debe modificar Git en caliente dentro del request del usuario. Debe encolar:

```text
stacky_memory_outbox
```

DDL:

```sql
CREATE TABLE stacky_memory_outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project TEXT NOT NULL,
  mutation_id TEXT NOT NULL UNIQUE,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at DATETIME NOT NULL,
  exported_at DATETIME,
  pushed_at DATETIME
);
```

Worker:

```text
MemorySyncWorker
  cada N segundos:
    acquire memory_git_lock(project)
    git pull --ff-only memory worktree
    import unseen chunks
    export pending outbox to new chunk
    git add new files only
    git commit -m "stacky memory: <project> <count> mutations"
    git push
```

Si push falla por remote updated:

```text
git pull --ff-only
import unseen chunks
reintentar push
```

Max retries configurables.

## 7. Modelo de memoria local

### 7.1 Tabla principal

```sql
CREATE TABLE stacky_memory_observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  memory_id TEXT NOT NULL UNIQUE,
  project TEXT NOT NULL,
  scope TEXT NOT NULL DEFAULT 'project',
  type TEXT NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  topic_key TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  confidence REAL,
  source_kind TEXT,
  source_execution_id INTEGER,
  source_ticket_id INTEGER,
  source_ado_id INTEGER,
  source_agent_type TEXT,
  author_email TEXT,
  author_role TEXT,
  tags_json TEXT,
  normalized_hash TEXT,
  revision_count INTEGER NOT NULL DEFAULT 1,
  duplicate_count INTEGER NOT NULL DEFAULT 1,
  last_seen_at DATETIME,
  review_after DATETIME,
  expires_at DATETIME,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  deleted_at DATETIME
);

CREATE INDEX ix_stacky_mem_project_status ON stacky_memory_observations(project, status);
CREATE INDEX ix_stacky_mem_topic ON stacky_memory_observations(project, scope, topic_key, updated_at DESC);
CREATE INDEX ix_stacky_mem_source_exec ON stacky_memory_observations(source_execution_id);
CREATE INDEX ix_stacky_mem_hash ON stacky_memory_observations(project, scope, type, normalized_hash);
```

Estados:

| Estado | Se inyecta | Significado |
|---|---|---|
| `draft` | No por default | Candidato pendiente de revision |
| `active` | Si | Memoria vigente |
| `needs_review` | No, salvo override | Requiere curacion |
| `superseded` | No | Reemplazada por otra |
| `rejected` | No | Descartada por validador/humano |
| `quarantined` | No | Riesgo de secreto, PII, inconsistencia grave o corrupcion |
| `deleted` | No | Borrado logico/tombstone |

### 7.2 FTS5

SQLite:

```sql
CREATE VIRTUAL TABLE stacky_memory_fts USING fts5(
  title,
  content,
  type,
  project,
  topic_key,
  tags,
  content='stacky_memory_observations',
  content_rowid='id'
);
```

Triggers:

```sql
AFTER INSERT -> insert FTS
AFTER UPDATE -> delete old FTS + insert new FTS
AFTER DELETE -> delete FTS
```

Busqueda:

1. Si query contiene `/`, buscar exacto por `topic_key`.
2. Si no, FTS5 por title/content/type/tags.
3. Filtrar por `project`, `scope`, `status='active'`, `deleted_at IS NULL`.
4. Adjuntar relaciones relevantes.

### 7.3 Relaciones

```sql
CREATE TABLE stacky_memory_relations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  relation_id TEXT NOT NULL UNIQUE,
  project TEXT NOT NULL,
  source_memory_id TEXT NOT NULL,
  target_memory_id TEXT NOT NULL,
  relation TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'judged',
  reason TEXT,
  evidence TEXT,
  confidence REAL,
  marked_by_actor TEXT,
  marked_by_kind TEXT,
  marked_by_model TEXT,
  source_validation_run_id INTEGER,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);

CREATE INDEX ix_stacky_memrel_source ON stacky_memory_relations(source_memory_id, relation);
CREATE INDEX ix_stacky_memrel_target ON stacky_memory_relations(target_memory_id, relation);
```

Relaciones soportadas:

```text
related
compatible
scoped
conflicts_with
supersedes
duplicates
not_conflict
```

Reglas de inyeccion:

1. Si memoria A `supersedes` B, se inyecta A y se oculta B.
2. Si A `conflicts_with` B y ambas estan active, no se inyecta ninguna sin resolver; se abre finding.
3. Si A `scoped` B, se inyecta solo si el scope coincide con proyecto/cliente/agente.
4. `related` y `compatible` no bloquean.

## 8. Creacion de memorias

### 8.1 Fuentes

| Fuente | Estado inicial | Exportable |
|---|---|---|
| Operador crea manualmente | `active` o `draft` segun UI | Si |
| Output aprobado | `active` | Si |
| Output completado no aprobado | `draft` | No hasta aprobar |
| Agente propone aprendizaje | `draft` | No hasta aprobar |
| Validador crea relacion | `active` | Si |
| Preferencia personal | `active`, `scope=personal` | No por default |
| Deteccion de secreto/PII | `quarantined` | No |

### 8.2 Extraccion post-run

Al completar una ejecucion:

```text
PostRunMemoryExtractor
  |
  +-- si contract_result score >= umbral
  +-- si output contiene secciones de aprendizaje o evidencia
  +-- si verdict approved, permite active
  +-- si no approved, guarda draft local
```

Tipos sugeridos:

```text
decision
architecture
pattern
bugfix
discovery
client_policy
constraint
preference
session_summary
anti_pattern
qa_finding
release_note
```

### 8.3 Topic key

Formato:

```text
familia/descripcion-kebab-case
```

Familias:

```text
client/*
architecture/*
pattern/*
bug/*
decision/*
policy/*
qa/*
ado/*
runtime/*
preference/*
```

Regla:

1. Si `topic_key` existe en mismo `project + scope`, hacer upsert.
2. Incrementar `revision_count`.
3. Mantener historico como mutaciones Git, pero una sola fila vigente local.
4. Si el cambio contradice fuerte una memoria activa distinta, crear `needs_review`.

## 9. Inyeccion de memoria en ejecuciones

### 9.1 En `context_enrichment.py`

Agregar paso:

```text
0. stacky-memory-context
1. client-profile
2. ado-epic-structured
3. filesystem-artifacts
4. ado-similar-tickets
5. ado-comments/attachments
```

Se inyecta al principio para que todo el resto pueda usarlo como contexto base.

ContextBlock:

```json
{
  "kind": "text",
  "id": "stacky-memory",
  "title": "Memoria operativa vigente",
  "content": "...",
  "metadata": {
    "hits": 6,
    "suppressed": 2,
    "memory_ids": ["mem-01J...", "mem-01K..."]
  }
}
```

### 9.2 Ranking

Score combinado:

```text
0.35 FTS/title-content
0.20 topic_key/tag match
0.15 same agent_type
0.15 same client/project
0.10 recency
0.05 validator_confidence
```

Caps:

| Agente | Max memorias | Max chars |
|---|---:|---:|
| Business | 6 | 6000 |
| Functional | 10 | 10000 |
| Technical | 12 | 12000 |
| Developer | 14 | 14000 |
| QA | 12 | 12000 |
| PM/Critic/Debug | 12 | 12000 |

### 9.3 No inyectar

No se inyecta:

1. `scope=personal` de otro usuario.
2. `status != active`.
3. Memorias con `expires_at` vencido.
4. Memorias superseded.
5. Memorias en conflicto no resuelto.
6. Memorias con PII/secret flag.
7. Memorias de otro proyecto salvo `scope=global` o busqueda cross-project explicita.

## 10. Validador de memoria

### 10.1 Objetivo

El validador debe ser lanzable desde Stacky para:

1. Detectar inconsistencias.
2. Marcar memorias duplicadas.
3. Resolver o proponer relaciones `supersedes`/`conflicts_with`.
4. Detectar memorias obsoletas.
5. Detectar secretos/PII antes de exportar o inyectar.
6. Generar un reporte accionable para el operador.

### 10.2 UI

Pantalla: `Memory Validator`.

Controles:

```text
Proyecto: [PACIFICO v]
Scope: [project/team/global]
Modo:
  [ ] Deterministico rapido
  [ ] Semantic LLM judge
  [ ] Incluir draft
  [ ] Incluir personal propia
Accion:
  [Run validation]
```

Resultados:

```text
Memory Validation Run #17

Resumen:
- 1432 memorias analizadas
- 22 duplicados
- 7 conflictos posibles
- 3 politicas obsoletas
- 1 memoria en cuarentena por secreto

Findings:
[major] Conflicto: policy/db-dml-runtime vs client/pacifico-db-policy
        Sugerencia: marcar nueva como supersedes vieja
        [Aceptar] [Marcar compatible] [Ignorar] [Abrir detalle]
```

### 10.3 Pipeline del validador

```text
MemoryValidator.run(project)
  |
  +-- sync memory Git pull/import
  +-- schema checks
  +-- integrity checks
  +-- privacy checks
  +-- duplicate checks
  +-- topic_key checks
  +-- relation graph checks
  +-- semantic candidate generation
  +-- optional LLM judge
  +-- write findings
  +-- optionally write relation proposals
```

### 10.4 DDL

```sql
CREATE TABLE stacky_memory_validation_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project TEXT NOT NULL,
  mode TEXT NOT NULL,
  status TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  started_at DATETIME NOT NULL,
  completed_at DATETIME,
  summary_json TEXT,
  error_message TEXT
);

CREATE TABLE stacky_memory_findings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  project TEXT NOT NULL,
  severity TEXT NOT NULL,
  finding_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  source_memory_id TEXT,
  target_memory_id TEXT,
  title TEXT NOT NULL,
  detail TEXT NOT NULL,
  evidence_json TEXT,
  recommended_action TEXT,
  action_payload_json TEXT,
  resolved_by TEXT,
  resolved_at DATETIME,
  created_at DATETIME NOT NULL,
  FOREIGN KEY(run_id) REFERENCES stacky_memory_validation_runs(id)
);
```

### 10.5 Checks deterministas

| Check | Severidad | Accion |
|---|---|---|
| Schema invalido | blocker | Quarantine chunk/mutation |
| Checksum distinto | blocker | Marcar tampered, bloquear import |
| Secret pattern | blocker | Quarantine memoria, no exportar |
| PII alto | major | Quarantine o redactar |
| Topic key vacio en decision/policy | minor | Proponer topic_key |
| Duplicado exacto | minor | Incrementar duplicate_count o relation duplicates |
| Duplicado semantico | major | Proponer merge/supersedes |
| Conflicto active-active | blocker | No inyectar ambas |
| Superseded aun active | major | Marcar vieja superseded |
| Memoria vencida | minor | needs_review |
| Proyecto incorrecto | major | Proponer reclasificacion |
| Source execution inexistente | minor | Marcar orphan_source |
| Memoria sin autor | minor | Completar si chunk trae actor |
| Mutacion deferred vieja | major | Reportar dependencia faltante |

### 10.6 LLM judge opcional

El LLM no decide solo cambios destructivos. Produce propuestas:

```json
{
  "relation": "supersedes",
  "confidence": 0.82,
  "reason": "La nueva politica reemplaza explicitamente la anterior para el mismo cliente.",
  "requires_human": true
}
```

Reglas:

1. `confidence < 0.70`: siempre requiere humano.
2. `conflicts_with` en `policy`, `client_policy`, `architecture`, `decision`: requiere humano.
3. `duplicates` exacto puede auto-resolverse.
4. `secret` nunca lo resuelve el LLM; lo resuelve politica determinista.

### 10.7 Acciones del validador

Acciones posibles:

```text
mark_supersedes
mark_conflicts_with
mark_compatible
mark_scoped
mark_duplicate
quarantine
reject
promote_draft_to_active
edit_topic_key
reclassify_project
redact_content
ignore_finding
```

Toda accion debe escribir una mutacion en `stacky_memory_outbox` para que viaje por Git.

## 11. Seguridad y privacidad

### 11.1 Scopes

| Scope | Export a Git | Inyeccion |
|---|---|---|
| `project` | Si | A todos los usuarios del proyecto |
| `team` | Si | A usuarios con equipo/rol permitido |
| `global` | Si, si admin | Cross-project |
| `personal` | No por default | Solo autor |
| `private` | No | Nunca se inyecta fuera del autor |

### 11.2 Redaccion

Antes de guardar/exportar:

1. Reusar `pii_masker.py`.
2. Agregar `secret_scanner.py` para tokens, passwords, connection strings, PATs.
3. Soportar tags:

```text
<private>...</private>
<secret>...</secret>
```

Regla:

```text
Si hay secreto probable, memoria queda quarantined y no se exporta.
```

### 11.3 Permisos

Roles:

| Rol | Permisos |
|---|---|
| Developer/Analyst | Crear memorias propias, ver memorias active del proyecto |
| Lead/PM | Promover draft, resolver findings no destructivos |
| Memory Curator | Resolver conflictos, quarantine, supersedes |
| Admin | Cambiar politicas Git, habilitar autostash, borrar/tombstone |

## 12. Observabilidad

### 12.1 Eventos

Extender `stacky_logger`:

```text
memory_sync_started
memory_sync_completed
memory_sync_failed
workspace_pull_started
workspace_pull_completed
workspace_pull_failed
memory_context_injected
memory_saved
memory_exported
memory_validation_started
memory_validation_completed
memory_finding_created
```

### 12.2 Endpoints diagnosticos

| Metodo | Path | Uso |
|---|---|---|
| GET | `/api/memory/status?project=` | Estado local, chunks importados, outbox pendiente |
| POST | `/api/memory/sync-now` | Pull/import/export/push manual |
| POST | `/api/memory/validate` | Lanza validador |
| GET | `/api/memory/validation-runs` | Lista runs |
| GET | `/api/memory/findings` | Findings abiertos |
| POST | `/api/memory/findings/<id>/resolve` | Aplica accion |
| GET | `/api/diag/pre-run/<execution_id>` | Estado de preparacion |
| POST | `/api/diag/git/pull-check` | Dry-run diagnostico de workspace |

### 12.3 Metricas

```json
{
  "memory": {
    "active": 1203,
    "draft": 88,
    "quarantined": 2,
    "open_findings": 14,
    "outbox_pending": 5,
    "last_sync_at": "2026-06-06T15:30:00Z"
  },
  "pre_run": {
    "pull_success_rate_24h": 0.97,
    "avg_pull_ms": 2100,
    "blocked_dirty_tree_24h": 3
  }
}
```

## 13. Frontend

### 13.1 Cambios en Run

Al apretar Run:

1. Crear ejecucion en `preparing`.
2. Abrir `PreRunProgress`.
3. Consumir SSE de logs/pre-run.
4. No mostrar prompt del agente hasta que pase pre-run.
5. Si falla, mostrar diagnostico y no permitir "continuar igual" salvo permiso admin.

### 13.2 Pagina de memoria

Tabs:

```text
Memorias
Conflictos
Drafts
Quarantine
Validaciones
Git Sync
Configuracion
```

Filtros:

```text
project
scope
type
status
agent_type
author
topic_key
ticket/ADO
```

Acciones:

```text
crear memoria
editar memoria
marcar supersedes
marcar conflicto
promover draft
quarantine
exportar ahora
validar ahora
ver historial Git
```

### 13.3 Team Screen

En cada tarjeta de ticket/agente:

```text
Memoria: 6 hits vigentes
Ultimo sync: hace 3 min
Findings abiertos: 2
```

No saturar la UI principal. Mostrar detalles solo al expandir.

## 14. Configuracion por proyecto

Archivo:

```text
Stacky Agents/projects/<PROJECT>/config.json
```

Propuesta:

```json
{
  "memory": {
    "enabled": true,
    "git_enabled": true,
    "storage_mode": "dedicated_memory_worktree",
    "memory_branch": "stacky-memory/PACIFICO",
    "auto_export": true,
    "auto_push": true,
    "inject_before_run": true,
    "max_context_chars": 12000,
    "validator_required_for_policy": true,
    "draft_requires_approval": true,
    "personal_export_default": false
  },
  "git_sync": {
    "enabled": true,
    "required_before_run": true,
    "workspace_policy": "ff_only_block_on_dirty",
    "timeout_seconds": 60,
    "show_spinner": true
  }
}
```

Feature flags:

```text
STACKY_MEMORY_ENABLED=true
STACKY_MEMORY_GIT_SYNC_ENABLED=true
STACKY_PRE_RUN_GIT_PULL_ENABLED=true
STACKY_PRE_RUN_GIT_PULL_REQUIRED=true
STACKY_MEMORY_VALIDATOR_ENABLED=true
STACKY_MEMORY_INJECTION_ENABLED=true
```

## 15. Fases de implementacion

### Fase 0 - Decisiones y guardrails

1. Confirmar storage default: `dedicated_memory_worktree`.
2. Confirmar branch naming: `stacky-memory/<PROJECT>`.
3. Confirmar politica workspace default: `ff_only_block_on_dirty`.
4. Definir roles iniciales.
5. Definir que tipos de memoria nacen `active` vs `draft`.

Criterio de salida:

```text
Documento de decision aprobado.
Config por proyecto soporta memory/git_sync.
```

### Fase 1 - DB local y FTS

1. Crear `services/memory_store.py`.
2. Agregar tablas:
   - `stacky_memory_observations`
   - `stacky_memory_relations`
   - `stacky_memory_chunks`
   - `stacky_memory_mutations`
   - `stacky_memory_outbox`
3. Crear FTS5 y triggers.
4. Implementar:
   - `save_observation`
   - `search`
   - `get_context_for_run`
   - `upsert_by_topic_key`
   - `mark_relation`
5. Tests unitarios con SQLite in-memory y DB real temporal.

Criterio de salida:

```text
Se pueden guardar, actualizar, buscar e inyectar memorias activas.
Topic_key actualiza revision_count.
Memorias superseded/quarantined no aparecen en busqueda de contexto.
```

### Fase 2 - Git memory sync append-only

1. Crear `services/memory_git_sync.py`.
2. Crear worktree dedicado por proyecto.
3. Implementar pull/import idempotente.
4. Implementar outbox/export a chunk.
5. Implementar commit/push con retry.
6. Implementar checksum/tamper detection.
7. Agregar endpoint `/api/memory/sync-now`.

Criterio de salida:

```text
Dos usuarios pueden crear memorias en paralelo y sincronizarlas sin editar el mismo archivo.
Un chunk corrupto queda bloqueado.
Un push rechazado por remote update se recupera con pull+retry.
```

### Fase 3 - Pre-run pull obligatorio

1. Crear `services/pre_run_sync.py`.
2. Integrar en `agent_runner.run_agent` antes de crear thread real, o crear estado `preparing`.
3. Agregar locks por proyecto/workspace.
4. Implementar workspace pull segun policy.
5. Emitir eventos SSE/log_streamer.
6. Guardar metadata `pre_run`.
7. UI `PreRunProgress`.

Criterio de salida:

```text
Cada ejecucion pasa por pre-run.
Si Git esta limpio, se ejecuta pull y luego agente.
Si Git esta dirty, no se lanza agente y la UI muestra diagnostico.
El agente nunca recibe instrucciones para hacer pull.
```

### Fase 4 - Inyeccion de memoria en contexto

1. Integrar `memory_store.get_context_for_run` en `context_enrichment.py`.
2. Agregar bloque `stacky-memory`.
3. Registrar `memory_context` en metadata.
4. Agregar filtros por agente/proyecto/ticket.
5. Tests de no inyeccion de quarantined/superseded/conflicted.

Criterio de salida:

```text
El prompt final incluye memorias relevantes.
No incluye memorias personales de otro usuario.
No incluye memorias conflictivas sin resolver.
```

### Fase 5 - Captura post-run

1. Crear `services/post_run_memory.py`.
2. Extraer candidate memories desde outputs aprobados.
3. Guardar `session_summary` por ejecucion/pack.
4. Crear UI para aprobar candidatos si nacen draft.
5. Encolar export si aplica.

Criterio de salida:

```text
Una ejecucion aprobada genera al menos resumen reusable.
Las memorias exportables entran en outbox.
Las memorias draft no viajan a Git hasta aprobacion.
```

### Fase 6 - Validador de memoria

1. Crear `services/memory_validator.py`.
2. Agregar tablas de validation runs/findings.
3. Implementar checks deterministas.
4. Implementar candidate generation para conflictos.
5. Agregar LLM judge opcional.
6. Crear UI de findings y acciones.
7. Exportar acciones como mutaciones Git.

Criterio de salida:

```text
Stacky puede lanzar validacion desde UI.
Findings quedan persistidos.
Resolver un finding crea relacion/mutacion.
Memorias conflictivas dejan de inyectarse hasta resolucion.
```

### Fase 7 - Hardening, permisos y rollout

1. Roles/permisos.
2. Secret scanner.
3. Backups.
4. Metrics.
5. Migration docs.
6. Flags de rollout gradual.
7. Pruebas E2E con 2 clones locales.

Criterio de salida:

```text
Se puede activar por proyecto.
Se puede apagar sin romper ejecuciones.
Hay diagnostico claro para Git, memoria y validador.
```

## 16. Plan de pruebas

### 16.1 Unit tests

| Area | Tests |
|---|---|
| memory_store | save/search/upsert/delete/status filters |
| FTS | query especial, topic_key exacto, ranking |
| relations | supersedes oculta vieja, conflicts bloquea ambas |
| privacy | personal no exporta, secret quarantine |
| outbox | pending/exported/pushed/retry |
| git_sync | import idempotente, checksum mismatch, duplicate chunk |
| pre_run_sync | clean pull, dirty block, no upstream, timeout |
| validator | duplicates, conflicts, expired, orphan, quarantine |

### 16.2 Integration tests

1. Crear dos clones del mismo repo en temp.
2. Usuario A crea memoria y push.
3. Usuario B pre-run pull importa memoria.
4. Usuario B ejecuta agente con bloque `stacky-memory`.
5. Usuario B crea memoria con mismo topic_key.
6. Usuario A pull importa revision nueva.
7. Validador detecta conflicto y crea relation `supersedes`.
8. Nueva ejecucion inyecta solo memoria vigente.

### 16.3 E2E UI

1. Run muestra spinner pre-run.
2. Run bloqueado por dirty tree muestra diagnostico.
3. Memory page lista memorias.
4. Validator page muestra findings.
5. Resolver finding actualiza memoria.
6. Estado de sync visible.

### 16.4 Failure injection

| Falla | Resultado esperado |
|---|---|
| Git remote no disponible | Run bloqueado si required |
| Memory push rejected | Worker pull+retry |
| Chunk corrupto | Quarantine chunk, no crash |
| DB lock | Retry/backoff, diagnostico |
| LLM validator falla | Findings deterministas siguen |
| Usuario sin permisos | 403 en acciones curator/admin |
| Workspace dirty | Bloqueo seguro |

## 17. Riesgos y mitigaciones

| Riesgo | Mitigacion |
|---|---|
| Git pull bloquea demasiado | Timeout, locks, UI visible, metrics |
| Dirty tree frecuente | Dedicated worktree para ejecucion automatica |
| Memoria ruidosa | Draft por default para extracciones no aprobadas |
| Secretos en memoria | Scanner antes de save/export/inject |
| Conflictos semanticos | Validador y suppression de active-active conflicts |
| Branch de memoria divergente | Append-only + pull+retry + no manifest global |
| Usuarios sin credenciales Git | Diagnostico pre-run y setup guide |
| Exceso de contexto | Caps por agente y ranking |
| Baja confianza del LLM validator | Acciones de alto impacto requieren humano |
| Migration rompe features actuales | Flags por proyecto, fallback disabled |

## 18. Definicion de Done

El agregado se considera completo cuando:

1. Cada ejecucion pasa por pre-run sync y muestra progreso.
2. Stacky ejecuta `git pull` del workspace de forma segura antes del agente.
3. La memoria colaborativa se guarda localmente y se sincroniza por Git append-only.
4. Dos usuarios pueden compartir memorias sin conflictos de archivo.
5. Las memorias relevantes se inyectan automaticamente al prompt.
6. Memorias personales, quarantined, superseded o conflictivas no se inyectan.
7. Existe UI para ver memorias, sync y validaciones.
8. El validador se puede lanzar desde Stacky.
9. Los findings se pueden resolver y viajan por Git.
10. Hay tests unitarios, integracion multi-clone y E2E UI.
11. Hay flags para activar/desactivar por proyecto.
12. Hay documentacion operativa para usuarios y administradores.

## 19. Orden recomendado de implementacion real

Para capturar valor sin abrir todos los frentes a la vez:

1. **Pre-run git pull con spinner**: aporta seguridad inmediata y es requisito transversal.
2. **Memory store local + FTS**: permite probar inyeccion sin Git.
3. **Inyeccion `stacky-memory`**: muestra valor directo en outputs.
4. **Git memory sync append-only**: habilita colaboracion real.
5. **Post-run memory extraction**: empieza a alimentar memoria automaticamente.
6. **Memory Validator MVP deterministico**: evita basura y contradicciones.
7. **LLM judge opcional y UI avanzada**: mejora curacion, no bloquea MVP.

## 20. Decision pendiente

Antes de implementar, confirmar estas decisiones:

1. Usar `dedicated_memory_worktree` como default para memoria compartida.
2. Usar `ff_only_block_on_dirty` como default para workspace pull.
3. Bloquear ejecucion si el workspace no puede actualizarse.
4. Exportar automaticamente solo memorias `active` y no personales.
5. Requerir humano para conflictos de policy/decision/architecture.
6. Definir quienes tienen rol `Memory Curator`.

