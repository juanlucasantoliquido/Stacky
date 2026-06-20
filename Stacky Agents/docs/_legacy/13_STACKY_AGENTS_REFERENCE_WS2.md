# Stacky Agents — Documento completo de funcionalidades

> **Propósito de este documento:** descripción exhaustiva de todas las funcionalidades
> de Stacky Agents, pensada para ser entregada a otro agente de IA o desarrollador
> que NO tiene acceso al código y necesita entender exactamente qué hace el sistema,
> cómo funciona, qué endpoints existen, cómo se comporta cada moat, y qué integrar.

---

## Índice

1. [¿Qué es Stacky Agents?](#1-qué-es-stacky-agents)
2. [Arquitectura general](#2-arquitectura-general)
3. [Los 8 agentes disponibles](#3-los-8-agentes-disponibles)
4. [Los 5 Agent Packs predefinidos](#4-los-5-agent-packs-predefinidos)
5. [Todos los endpoints REST](#5-todos-los-endpoints-rest)
6. [Las 52 funcionalidades (moats) — descripción completa](#6-las-52-funcionalidades-moats)
7. [Modelo de datos completo](#7-modelo-de-datos-completo)
8. [Flujo de ejecución (agent_runner)](#8-flujo-de-ejecución-agent_runner)
9. [Variables de entorno](#9-variables-de-entorno)
10. [Cómo arrancar el sistema](#10-cómo-arrancar-el-sistema)
11. [Frontend — pantallas y componentes](#11-frontend--pantallas-y-componentes)
12. [VS Code extension](#12-vs-code-extension)
13. [Integración externa (webhooks, slack, CI)](#13-integración-externa)

---

## 1. ¿Qué es Stacky Agents?

Stacky Agents es un **workbench de agentes de IA** para el flujo de desarrollo de tickets en Azure DevOps (ADO). No es un pipeline automático: es un sistema donde **el humano selecciona manualmente cada agente y lo dispara cuando quiere**.

### Diferencia clave con Stacky Pipeline (el sistema anterior)

| Aspecto | Stacky Pipeline | Stacky Agents |
|---|---|---|
| Quién dispara los agentes | El sistema (daemon cron) | El humano (click en Run) |
| Orden de ejecución | Rígido (estados ADO) | Libre — cualquier agente, cualquier momento |
| Contexto del agente | Fijo por diseño | Editable antes de cada Run |
| Re-ejecutar | Revertir estado ADO | Click en "Clone & edit" |
| Trazabilidad | Parcial (artefactos) | Total (cada exec en BD con prompt+output) |

### Filosofía central

> El humano vuelve al loop. Cada Run es una decisión consciente del operador.

---

## 2. Arquitectura general

```
┌─────────────────────────────────────────────────────────────────┐
│  FRONTEND (React + Vite, :5173)                                 │
│  Workbench de 3 columnas:                                       │
│  [Ticket + Agente + Packs] | [Editor de contexto] | [Output]   │
└───────────────────────┬─────────────────────────────────────────┘
                        │ HTTPS + SSE
┌───────────────────────▼─────────────────────────────────────────┐
│  BACKEND (Flask 3, :5050)                                       │
│  agent_runner.py — orquesta 10 etapas por Run                  │
│  Blueprints: agents, packs, executions, tickets, phase4-6, ... │
└───────┬──────────────────┬───────────────────┬──────────────────┘
        │                  │                   │
   SQLite/Postgres    copilot_bridge.py     ADO API (REST)
   (todas las tablas)  (LLM engine)        (tickets, comments)
```

### Componentes backend (archivos clave)

| Archivo | Responsabilidad |
|---|---|
| `app.py` | Entrypoint Flask; registra blueprints, init_db, reconcilia orphans |
| `agent_runner.py` | Núcleo: dispara ejecuciones en threads, orquesta 10 etapas |
| `agents/base.py` | `BaseAgent` + `RunContext`; `compose_system_prompt` encadena 6 fuentes |
| `copilot_bridge.py` | Wrapper del LLM (mock/copilot); acepta `model`, `on_log`, `execution_id` |
| `log_streamer.py` | Buffer in-memory de logs por exec; SSE feed |
| `prompt_builder.py` | `render_blocks(blocks)` → markdown del contexto |
| `db.py` | SQLAlchemy engine, `init_db()`, `session_scope()` |
| `models.py` | ORM: Ticket, AgentExecution, ExecutionLog, PackRun, User |

---

## 3. Los 8 agentes disponibles

Cada agente es una clase Python que extiende `BaseAgent`. Tiene: `type`, `name`, `icon`, `description`, `inputs_hint`, `outputs_hint`, `system_prompt()`.

### 3.1 Business Agent (`type="business"`)

**Responsabilidad:** convertir texto libre / entrevistas con el cliente en Epics estructurados en ADO.

**Input esperado:**
- Conversación o brief del cliente
- Notas del operador

**Output que genera:**
- HTML estructurado con bloques `RF-001`, `RF-002`, etc.
- Identificación de actores, reglas de negocio, datos involucrados, prioridades
- Formato: `<hr><h2>RF-XXX — Título</h2>...`

**System prompt clave:** identifica RF por requerimiento, actores, datos, reglas. Si falta información, marca `[PENDIENTE: ...]`.

---

### 3.2 Functional Agent (`type="functional"`)

**Responsabilidad:** analizar un Epic ADO y producir análisis funcional + plan de pruebas.

**Input esperado:**
- Descripción del Epic con bloques RF-XXX
- Documentación funcional del módulo (desde INDEX.md)

**Output que genera:**
- `analisis-funcional.md` con clasificación de cobertura
- `plan-de-pruebas.md` con escenarios de validación
- Clasificación: `CUBRE Sin modificación` / `CUBRE Con configuración` / `GAP Menor` / `Nueva Funcionalidad`

**System prompt clave:** para cada RF, clasifica, cita documentos consultados, genera plan de pruebas.

---

### 3.3 Technical Agent (`type="technical"`)

**Responsabilidad:** traducir el análisis funcional a un análisis técnico de 5 secciones.

**Input esperado:**
- Task ADO con análisis funcional aprobado
- Documentación técnica del módulo
- Fragmentos de código relevantes

**Output que genera:** comentario `🔬 ANÁLISIS TÉCNICO — ADO-{id}` con 5 secciones:
1. Traducción funcional → técnica (flujo actual vs propuesto)
2. Alcance de cambios (archivo, clase, método, línea ~N, qué cambia)
3. Plan de pruebas técnico (datos reales de BD, queries SELECT)
4. Tests unitarios obligatorios (TU-001…TU-N: clase, método, input, expected, assert)
5. Notas para el desarrollador (convenciones, precauciones, patrón de referencia)

**Caso bloqueante:** si detecta información faltante, produce comentario `🚫 BLOQUEANTE TÉCNICO` y no cierra el análisis.

---

### 3.4 Developer Agent (`type="developer"`)

**Responsabilidad:** implementar código siguiendo exactamente el análisis técnico aprobado.

**Input esperado:**
- Task ADO con las 5 secciones del análisis técnico
- Código fuente relevante
- Archivo maestro RIDIOMA

**Output que genera:** comentario `🚀 IMPLEMENTACIÓN COMPLETADA — ADO-{id}` con:
1. Resumen de archivos modificados + líneas
2. Trazabilidad (`// ADO-{id} | YYYY-MM-DD | descripción`)
3. Resultados de tests unitarios (TU-001…TU-N: PASS/FAIL)
4. Verificaciones de BD post-implementación
5. Resultado de compilación (MSBuild)
6. Notas para QA

**Regla clave RIDIOMA:** las entradas RIDIOMA/RTABL/RPARAM se agregan SIEMPRE al archivo maestro existente en `trunk/BD/1 - Inicializacion BD/600804 - Inserts RIDIOMA.sql`. Nunca se crean archivos .sql nuevos.

---

### 3.5 QA Agent (`type="qa"`)

**Responsabilidad:** validar la implementación y emitir un veredicto PASS/FAIL.

**Input esperado:**
- Task completa (funcional + técnica + evidencia del Developer)
- Commits del branch
- Plan de pruebas funcional y técnico

**Output que genera:**
- `TESTER_COMPLETADO.md`
- Verdict: `PASS` / `FAIL`
- Casos verificados (con ✓/✗)
- Riesgos de regresión identificados
- Recomendación para QA humano

---

### 3.6 Debug Agent (`type="debug"`)

**Responsabilidad:** analizar fallos de CI / tests y proponer causa + fix tentativo.

**Input esperado:**
- Build log de CI
- Diff del commit
- Lista de tests fallidos

**Output que genera:**
1. Causa probable (con evidencia del log)
2. Ubicación exacta (archivo:línea)
3. Fix tentativo (diff sugerido)
4. Comandos de reproducción local
5. Riesgo de regresión del fix

**Disparado por:** webhook `/api/ci/failure-webhook` automáticamente.

---

### 3.7 PR Review Agent (`type="pr_review"`)

**Responsabilidad:** revisar un diff de PR y comentar findings estructurados.

**Input esperado:**
- Diff del PR
- Descripción del PR
- Convenciones del proyecto

**Output que genera:** lista de findings con:
- Severidad: `blocker | major | minor | nit`
- Ubicación: `archivo:línea`
- Tipo: `bug | security | performance | style | maintainability`
- Detalle + sugerencia de fix

**Comportamiento clave:** si el PR está bien, lo dice claramente. Limita a 5 findings relevantes.

**Disparado por:** webhook `/api/pr/review-webhook`.

---

### 3.8 Critic Agent (`type="__critic__"`)

**Responsabilidad:** desafiar el output de otro agente sin re-escribirlo.

**Input esperado:**
- Output de cualquier agente (markdown)

**Output que genera:** lista de 8 puntos máximo:
- Asunciones no declaradas
- Edge cases no cubiertos
- Contradicciones internas
- Preguntas que el operador debe responder

**Cómo se invoca:** `POST /api/executions/:id/critique` — recibe el `execution_id` de la exec a criticar.

---

## 4. Los 5 Agent Packs predefinidos

Los packs son recetas guiadas de múltiples agentes con pausa humana entre cada paso. El humano debe hacer "Approve & Continue" para avanzar. Cada paso puede editarse.

### Pack Desarrollo (`id="desarrollo"`)
**Pasos:** Functional → Technical → Developer → QA
**Uso:** flujo completo desde Epic nuevo hasta QA.

### Pack QA Express (`id="qa-express"`)
**Pasos:** QA (solo)
**Uso:** cuando el Developer ya terminó y sólo se necesita validar.

### Pack Discovery (`id="discovery"`)
**Pasos:** Functional → Technical
**Uso:** explorar qué pide un Epic antes de comprometerse a implementar.

### Pack Hotfix (`id="hotfix"`)
**Pasos:** Technical → Developer → QA
**Uso:** bug en producción, sin pasar por Functional.

### Pack Refactor (`id="refactor"`)
**Pasos:** Technical → Developer → QA
**Uso:** mejora de código sin cambio de comportamiento. Developer con flag `iso_functional`.

---

## 5. Todos los endpoints REST

El backend corre en `http://localhost:5050`. Todos los endpoints bajo `/api`.

### Health
| Método | Path | Descripción |
|---|---|---|
| GET | `/api/health` | Smoke check → `{"ok": true}` |

### Agentes
| Método | Path | Body/Query | Respuesta |
|---|---|---|---|
| GET | `/api/agents` | — | Lista de 8 agentes con type, name, description, inputs, outputs |
| POST | `/api/agents/run` | `{agent_type, ticket_id, context_blocks, chain_from?, model_override?, system_prompt_override?, use_few_shot?, use_anti_patterns?, fingerprint_complexity?, previous_execution_id?, delta_prefix?}` | `{execution_id, status: "running"}` (202) |
| POST | `/api/agents/cancel/:exec_id` | — | `{ok: true}` |
| POST | `/api/agents/estimate` | `{agent_type, context_blocks, model?}` | `{tokens_in, tokens_out, cost_usd_total, latency_ms, cache_hit}` |
| POST | `/api/agents/route` | `{agent_type, context_blocks, model_override?, fingerprint_complexity?}` | `{model, reason, available: [...]}` |
| GET | `/api/agents/:type/system-prompt` | — | `{agent_type, system_prompt}` |
| GET | `/api/agents/:type/schema` | — | `{agent_type, rules: [{name, description, weight, severity}]}` |
| GET | `/api/agents/next-suggestion` | `?after_agent=` | `[{agent_type, probability, sample_size, source}]` |
| POST | `/api/agents/speculate` | `{agent_type, ticket_id, context_blocks}` | `{spec_id, status}` |
| GET | `/api/agents/speculate/:spec_id` | — | `{...spec}` |
| DELETE | `/api/agents/speculate/:spec_id` | — | `{ok: true}` |
| POST | `/api/agents/speculate/claim` | `{agent_type, context_blocks}` | `{found: bool, spec?}` |
| POST | `/api/agents/explore` | `{agent_type, ticket_id, context_blocks, variants?}` | `{execution_ids, variants}` |
| POST | `/api/agents/refine` | `{agent_type, ticket_id, context_blocks, template?, custom_prompts?}` | `{execution_ids, prompts, first_execution_id}` |

### Ejecuciones
| Método | Path | Query/Body | Respuesta |
|---|---|---|---|
| GET | `/api/executions` | `?ticket_id=&agent_type=&status=&limit=` | Lista de execs (sin output) |
| GET | `/api/executions/:id` | — | Exec completa con output |
| GET | `/api/executions/:id/logs` | — | `[LogLine]` snapshot |
| GET | `/api/executions/:id/logs/stream` | — | **SSE stream** de logs en vivo |
| POST | `/api/executions/:id/approve` | — | Exec con `verdict="approved"` |
| POST | `/api/executions/:id/discard` | — | Exec con `verdict="discarded"` |
| POST | `/api/executions/:id/publish-to-ado` | `{target: "comment"\|"task"}` | `{ok, ado_url}` |
| GET | `/api/executions/:id/diff/:other_id` | — | `{left: exec, right: exec}` |
| POST | `/api/executions/:id/critique` | — | `{execution_id, critique, output_format}` |
| POST | `/api/executions/:id/run-selects` | — | `{queries: [{sql, rows, error}], total_found}` |

### Tickets
| Método | Path | Query | Respuesta |
|---|---|---|---|
| GET | `/api/tickets` | `?project=&search=` | Lista con `last_execution` |
| GET | `/api/tickets/:id` | — | Ticket + últimas 50 execs |
| GET | `/api/tickets/:id/fingerprint` | — | `{change_type, domain, complexity, suggested_pack, keywords}` |
| GET | `/api/tickets/:id/glossary` | — | ContextBlock con glosario detectado |

### Packs
| Método | Path | Body | Respuesta |
|---|---|---|---|
| GET | `/api/packs` | — | Catálogo de 5 packs |
| POST | `/api/packs/start` | `{pack_id, ticket_id, options?}` | PackRun |
| GET | `/api/packs/runs/:id` | — | PackRun con execs |
| POST | `/api/packs/runs/:id/advance` | — | Avanza al siguiente paso |
| POST | `/api/packs/runs/:id/pause` | — | Pausa |
| POST | `/api/packs/runs/:id/resume` | — | Reanuda |
| DELETE | `/api/packs/runs/:id` | — | Abandona |

### Búsqueda y retrieval
| Método | Path | Query/Body | Respuesta |
|---|---|---|---|
| GET | `/api/similarity/similar` | `?ticket_id=&agent_type=&limit=` | `[SimilarHit]` por Jaccard |
| GET | `/api/similarity/graveyard` | `?q=&agent_type=&limit=` | Execs descartadas/fallidas similares |
| POST | `/api/retrieval/top-k` | `{query, agent_type?, k?, only_approved?}` | `[SemanticHit]` por TF-IDF cosine |
| POST | `/api/retrieval/reindex` | — | `{reindexed: N}` |

### Glossary (FA-15)
| Método | Path | Body/Query | Respuesta |
|---|---|---|---|
| GET | `/api/glossary/entries` | `?project=` | Lista de términos activos |
| POST | `/api/glossary/entries` | `{term, definition, project?}` | `{id}` |
| GET | `/api/glossary/candidates` | `?status=pending\|approved\|rejected` | Candidatos para review |
| POST | `/api/glossary/candidates/scan` | `{project?, days?, min_occurrences?}` | `{new_candidates: N}` |
| POST | `/api/glossary/candidates/:id/promote` | `{definition}` | `{entry_id}` |
| POST | `/api/glossary/candidates/:id/reject` | — | `{ok: true}` |
| POST | `/api/glossary/scan` | `{project?, days?}` | `{new_candidates: N}` |

### Anti-patterns (FA-11)
| Método | Path | Respuesta |
|---|---|---|
| GET | `/api/anti-patterns` | Lista activos |
| POST | `/api/anti-patterns` | `{id}` |
| DELETE | `/api/anti-patterns/:id` | `{ok: true}` |

### Decisions (FA-13)
| Método | Path | Respuesta |
|---|---|---|
| GET | `/api/decisions` | Lista activas |
| POST | `/api/decisions` | `{id}` |
| DELETE | `/api/decisions/:id` | `{ok: true}` |

### Constraints (FA-08)
| Método | Path | Respuesta |
|---|---|---|
| GET | `/api/constraints` | Lista activas |
| POST | `/api/constraints` | `{id}` |
| DELETE | `/api/constraints/:id` | `{ok: true}` |

### Webhooks (FA-52)
| Método | Path | Respuesta |
|---|---|---|
| GET | `/api/webhooks` | Lista |
| POST | `/api/webhooks` | `{id}` |
| DELETE | `/api/webhooks/:id` | `{ok: true}` |
| POST | `/api/webhooks/test/:id` | Dispara payload de test |

### Drift detection (FA-16)
| Método | Path | Respuesta |
|---|---|---|
| GET | `/api/drift/alerts` | `?unacknowledged=true\|false` |
| POST | `/api/drift/run` | `{window_days?}` → `{alerts_generated, alerts}` |
| POST | `/api/drift/alerts/:id/ack` | `{ok: true}` |

### Release context (FA-07)
| Método | Path | Respuesta |
|---|---|---|
| GET | `/api/release/context` | `{next_release, freeze_date, days_to_release, days_to_freeze, policy}` |
| GET | `/api/release/block` | ContextBlock listo para inyectar |

### Audit chain (FA-39)
| Método | Path | Respuesta |
|---|---|---|
| GET | `/api/audit/:ticket_id/chain` | `{valid, length, first_tampered_exec_id, detail}` |
| POST | `/api/audit/:exec_id/seal` | `{execution_id, node_hash}` |

### Egress controls (FA-41)
| Método | Path | Respuesta |
|---|---|---|
| GET | `/api/egress/policies` | Lista |
| POST | `/api/egress/policies` | `{id}` |
| DELETE | `/api/egress/policies/:id` | `{ok: true}` |
| POST | `/api/egress/check` | `{allowed, blocked_classes, warning_classes, detected_classes, reason}` |

### Macros DSL (FA-51)
| Método | Path | Respuesta |
|---|---|---|
| GET | `/api/macros` | Lista |
| POST | `/api/macros` | `{id}` |
| DELETE | `/api/macros/:id` | `{ok: true}` |
| POST | `/api/macros/:id/run` | `{macro_id, execution_ids, next_step_index, total_steps}` |

### Speculative (FA-36)
| Método | Path | Respuesta |
|---|---|---|
| POST | `/api/agents/speculate` | `{spec_id, status}` |
| GET | `/api/agents/speculate/:id` | `{...spec, output?}` |
| DELETE | `/api/agents/speculate/:id` | `{ok: true}` |
| POST | `/api/agents/speculate/claim` | `{found, spec?}` |

### Varios
| Método | Path | Descripción |
|---|---|---|
| GET | `/api/context/bookmarklet.js` | Devuelve el snippet JS del bookmarklet |
| POST | `/api/context/inbox` | `{url, selection, title?}` → `{block, hint}` |
| GET | `/api/release/block` | ContextBlock de release context |
| POST | `/api/live-db/select` | `{sql, project?, max_rows?, apply_pii_mask?}` → QueryResult |
| POST | `/api/live-db/block` | `{sql}` → ContextBlock |
| POST | `/api/typecheck/output` | `{output\|execution_id}` → `{results, any_failed}` |
| POST | `/api/slash/stacky` | Slash command handler (HMAC auth) |
| POST | `/api/ci/failure-webhook` | `{ticket_ado_id, build_log, failed_tests, commit_sha}` |
| POST | `/api/pr/review-webhook` | `{ticket_ado_id, pr_id, diff, description}` |
| GET | `/api/best-practices/feed` | `?days=7` → `{sections: [{title, items}]}` |
| GET | `/api/coaching/tips` | `?user=&days=` → `{user, tips: [{severity, title, detail, metric}]}` |
| POST | `/api/translate` | `{target_lang, output\|execution_id}` |
| POST | `/api/export` | `{format, output\|execution_id}` → `{content, filename, mime}` |
| POST | `/api/admin/erase` | `{user_email\|customer_keyword}` → GDPR erase |
| GET | `/api/git/file-context` | `?path=` → commits/blame |
| POST | `/api/git/context-block` | `{paths, n?}` → ContextBlock |
| GET | `/api/users/:email/style-profile` | `?agent_type=` → perfil de estilo |
| POST | `/api/users/:email/style-profile/compute` | `{agent_type}` → computa y persiste |

---

## 6. Las 52 funcionalidades (moats)

Organizadas en 8 categorías. Cada una describe exactamente qué hace, cuándo se activa, y cómo interactúa con el sistema.

---

### Categoría A — Context superpowers (FA-01 a FA-09)

#### FA-01 — Cross-ticket retrieval con TF-IDF
**Qué hace:** al completar cada exec, indexa su contenido (input+output) en la tabla `execution_embeddings` con vectores TF-IDF. El endpoint `/api/retrieval/top-k` busca las execs más similares por cosine similarity.
**Cuándo se activa:** automáticamente al finalizar cada exec exitosa. Consulta manual vía endpoint.
**Parámetros de búsqueda:** `query_text`, `agent_type`, `exclude_ticket_id`, `only_approved`, `k`.
**Calidad actual:** TF-IDF puro Python (sin dependencias). Reemplazable por sentence-transformers o pgvector sin cambiar la API.
**Integración en editor:** la vista "Similares aprobadas" del `SimilarPanel` usa este endpoint.

#### FA-02 — Live BD context injection
**Qué hace:** ejecuta SELECT read-only contra la base de datos del proyecto y devuelve los resultados como ContextBlock para inyectar al agente.
**Cuándo se activa:** manual, vía `/api/live-db/select` o `/api/live-db/block`.
**Seguridad:**
- Solo SELECT / WITH (rechaza INSERT, UPDATE, DROP, etc.)
- No acepta `;` (múltiples statements)
- Timeout 5 segundos
- Máximo 50 filas (default 10)
- PII masking automático en resultados
**En modo mock:** devuelve 3 filas dummy sin tocar BD real.
**Configuración:** variable de entorno `PROJECT_DB_URL` o `PROJECT_DB_URL_{PROYECTO}`.

#### FA-03 — Codebase semantic search
**Qué hace:** busca archivos relevantes del repo por intención ("flujo de notificación SMS de cobranza") en lugar de por nombre.
**Estado:** scaffolded — integra con `Tools/Stacky/codebase_indexer.py` existente. API: `GET /api/git/file-context` y `POST /api/git/context-block`.

#### FA-04 — Multi-LLM routing
**Qué hace:** antes de invocar al LLM, elige automáticamente el modelo óptimo según agente + complejidad del contexto.
**Reglas de routing:**
- `fingerprint_complexity=XL` → Opus siempre
- `tokens > 30.000` → Opus
- `developer + tokens > 12.000` → Opus
- `qa + tokens < 6.000` → Haiku
- `functional + tokens < 3.000` → Haiku
- Default por agente: QA=Haiku, resto=Sonnet
- `model_override` del operador tiene prioridad máxima
**Endpoint de preview:** `POST /api/agents/route` devuelve qué modelo se usaría sin ejecutar.
**En UI:** `ModelPicker` muestra el modelo auto-elegido y permite override.
**Log:** el agent_runner loguea `"router → claude-haiku-4-5 (qa rápido)"` en cada exec.

#### FA-05 — Git context awareness
**Qué hace:** para archivos afectados por el ticket, devuelve los últimos N commits con autor, fecha y subject.
**Cuándo se activa:** manual, `GET /api/git/file-context?path=trunk/OnLine/X.cs&n=5`.
**Block generado:** título "Contexto Git (N archivos)" con tabla de commits por archivo.
**Configuración:** variable `GIT_REPO_ROOT` (default: 3 niveles arriba del backend).
**Caché:** 5 minutos por (archivo, HEAD SHA).

#### FA-06 — Test coverage map injection
**Qué hace:** inyecta datos de cobertura de tests por método para que el agente priorice TUs faltantes.
**Estado:** scaffolded — importa coverage XML/lcov. Bloque `[auto] Cobertura del área`.

#### FA-07 — Schedule & release context
**Qué hace:** lee las variables de entorno `NEXT_RELEASE_DATE` y `RELEASE_FREEZE_DATE` y genera un ContextBlock con la política activa.
**Políticas:**
- `normal` → sin restricciones
- `soft-freeze` → días_hasta_freeze ≤ 2: solo crítico, revisión extra
- `hard-freeze` → días_hasta_freeze ≤ 0: sólo hotfixes bloqueantes
**Endpoint:** `GET /api/release/context` y `GET /api/release/block`.
**Uso en editor:** el bloque se inyecta automáticamente si hay release configurada.

#### FA-08 — Customer/project constraints injection
**Qué hace:** reglas declarativas que se activan cuando el contexto contiene ciertos keywords. Se inyectan como "obligaciones" al inicio del system prompt.
**Ejemplo:** si el contexto contiene "cobranza" → "Toda modificación en cobranza requiere entrada de auditoría".
**Diferencia con anti-patterns:** los constraints son obligaciones positivas; los anti-patterns son errores a evitar.
**Tabla:** `project_constraints` con columnas: `project`, `trigger_keywords` (CSV), `constraint_text`, `agent_types`, `priority`.
**Endpoint:** CRUD en `/api/constraints`.

#### FA-09 — RIDIOMA / glossary auto-injection
**Qué hace:** detecta términos de dominio del proyecto (RIDIOMA, RTABL, RPARAM, CobranzaService, etc.) en el contexto del ticket y los inyecta como bloque `[auto]` con definiciones.
**Fuente de términos:** diccionario inline (FA-09 original) + tabla `glossary_entries` (FA-15 ampliada).
**Cuándo se activa:** al seleccionar ticket + agente, automáticamente en `useAutoFillBlocks`.
**Endpoint:** `GET /api/tickets/:id/glossary` → ContextBlock listo.

---

### Categoría B — Memory compounding (FA-10 a FA-16)

#### FA-10 — Personal style memory
**Qué hace:** analiza outputs aprobados del operador y calcula su perfil de preferencias de estilo: longitud, profundidad y formatos favoritos (tablas, código, listas).
**Perfil generado:**
- `length_pref`: "concise" (<250 palabras promedio) / "balanced" / "thorough" (>600)
- `depth_pref`: "high-level" (<2 secciones) / "balanced" / "detailed" (>5)
- `format_hints`: `{tables_ratio, code_ratio, lists_ratio}` (0.0–1.0)
**Cómo se inyecta:** nota de calibración al inicio del system prompt: "Este operador prefiere outputs concisos con tablas".
**Requiere:** mínimo 3 outputs aprobados del mismo operador + agent_type.
**Endpoint:** `GET /api/users/:email/style-profile` y `POST .../compute`.

#### FA-11 — Anti-pattern registry
**Qué hace:** catálogo de errores que el equipo cometió antes y no quiere repetir. Se inyectan al system prompt como "evitá X porque Y".
**Tabla:** `anti_patterns` con `agent_type` (None=todos), `project`, `pattern`, `reason`, `example`.
**Cuándo se activa:** en cada Run, `compose_system_prompt` consulta los anti-patterns relevantes por agent_type + project.
**Endpoint:** CRUD en `/api/anti-patterns`.

#### FA-12 — Best-output few-shot examples
**Qué hace:** selecciona 1-2 outputs aprobados del mismo agente+proyecto con mejor puntaje (contract score + confidence) y los inyecta como ejemplos few-shot en el system prompt.
**Formato de inyección:**
```
## Ejemplos de outputs aprobados (few-shot)
<example exec_id="23" hint="RF-008 cobranza SMS">
# 🔬 ANÁLISIS TÉCNICO...
</example>
```
**Exclusión:** nunca incluye execs del mismo ticket activo.
**Cap:** máx 6.000 caracteres por ejemplo.

#### FA-13 — Historical decisions database
**Qué hace:** decisiones técnicas tomadas por el equipo quedan vivas y consultables. Cuando el contexto contiene keywords relacionados, la decisión se inyecta al system prompt.
**Ejemplo:** "Decidimos NO usar decimal.Round sin MidpointRounding porque causó diferencias en cobranzas en 2025-Q3".
**Tabla:** `decisions` con `summary`, `reasoning`, `tags` (CSV), `supersedes_id`, `made_at`, `made_by`.
**Matching:** Jaccard entre keywords del contexto y tags de la decisión.
**Endpoint:** CRUD en `/api/decisions`.

#### FA-14 — Output graveyard search
**Qué hace:** busca outputs descartados / fallidos similares al contexto actual para evitar repetir soluciones rechazadas.
**Cuándo se usa:** el operador abre el panel "Graveyard" en el editor y busca por texto.
**Endpoint:** `GET /api/similarity/graveyard?q=...`.
**Algoritmo:** Jaccard sobre n-grams de tokens (≥3 chars, sin stopwords).

#### FA-15 — Project glossary auto-build
**Qué hace:** escanea outputs aprobados y extrae términos candidatos (bold/code/ALLCAPS que aparecen ≥2 veces) para que el operador los promueva al glosario permanente.
**Pipeline:**
1. `POST /api/glossary/candidates/scan` → extrae candidatos del período
2. Operador revisa en `/api/glossary/candidates`
3. `POST /api/glossary/candidates/:id/promote` con definición → entra a `glossary_entries`
4. FA-09 incorpora los entries de la tabla en el bloque de glosario auto
**Filtros:** ignora términos ya en el glosario, stopwords (>3 chars), tokens conocidos.

#### FA-16 — Drift detection sobre prompts
**Qué hace:** compara métricas de calidad de los últimos 7 días vs los 7 días anteriores, por agente. Si la degradación supera umbrales, genera alertas.
**Métricas monitoreadas:**
- `avg_contract_score` → umbral warning: -8, critical: -15
- `avg_confidence` → umbral warning: -8, critical: -15
- `approval_rate` → umbral warning: -0.10, critical: -0.20
- `error_rate` → umbral warning: +0.08, critical: +0.15
**Tabla:** `drift_alerts` con severidad (warning/critical), acknowledged flag.
**Cómo correr:** `POST /api/drift/run` o manualmente. Alertas en `GET /api/drift/alerts`.

---

### Categoría C — Execution enrichment (FA-17 a FA-23)

#### FA-17 — Auto-typecheck del output del Developer
**Qué hace:** detecta bloques de código en el output y los valida con el compilador/typechecker correspondiente.
**Soportado:**
- Python: `compile()` nativo (sin subprocess)
- TypeScript: `tsc --noEmit` si disponible en PATH
- C#: stub (devuelve pass con nota "requiere proyecto context")
**Cuándo se activa:** `POST /api/typecheck/output` con output o execution_id.
**Output:** `{blocks_checked: N, any_failed: bool, results: [{language, passed, issues: [{line, column, severity, message}]}]}`.

#### FA-18 — Auto-execute SELECTs del output
**Qué hace:** detecta bloques ` ```sql ` en el output y los ejecuta read-only, mostrando resultados inline.
**Cuándo se activa:** `POST /api/executions/:id/run-selects`.
**Límite:** máx 5 queries por exec; solo SELECT/WITH.
**En modo mock:** devuelve 2 filas dummy por query.

#### FA-19 — Output schema validation (parte de N1/Contract Validator)
**Qué hace:** expone el schema (reglas del contrato) de cada agente para que la UI pueda mostrarlo.
**Endpoint:** `GET /api/agents/:type/schema` → lista de reglas con nombre, descripción, peso y severidad.
**Agentes cubiertos:** business, functional, technical, developer, qa.

#### FA-20 — Citation linker
**Qué hace:** en el frontend, detecta referencias `archivo.ext:NN` y `ADO-XXXX` en el output y las renderiza como links clickeables.
- `archivo.cs:84` → `vscode://file/archivo.cs:84` (abre en VS Code)
- `ADO-1234` → link a Azure DevOps
**Implementación:** custom renderers de react-markdown en `StructuredOutput.tsx`.

#### FA-21 — Auto UML / sequence diagram render
**Qué hace:** detecta bloques ` ```mermaid ` en los outputs y los renderiza como diagramas SVG interactivos.
**Funcionalidades del componente `MermaidDiagram`:**
- Renderizado SVG con tema oscuro
- Botón "expandir" (modo fullscreen)
- Link "Editar en mermaid.live"
- Botón "copiar código"
- Carga lazy del engine Mermaid (sólo cuando hay diagramas)

#### FA-22 — Output translator
**Qué hace:** traduce el output de una exec a otro idioma sin volver a correr el agente original.
**Idiomas soportados:** `es` (español), `en` (inglés), `pt` (portugués brasileño).
**Cómo:** prompt de sistema que preserva markdown, código, nombres propios.
**Caché:** por hash(output + target_lang), tabla `translation_cache`.
**Endpoint:** `POST /api/translate` con `{target_lang, output|execution_id}`.

#### FA-23 — Multi-format export
**Qué hace:** exporta el output en distintos formatos descargables.
**Formatos:**
- `md` → markdown puro
- `html` → página HTML standalone con CSS embebido
- `slack` → mrkdwn adaptado a Slack (headings → *bold*)
- `email` → draft `.eml` con Subject auto-detectado del primer heading
**Endpoint:** `POST /api/export` con `{format, output|execution_id}`.
**Frontend:** botones de exportación en el OutputPanel.

---

### Categoría D — Workflow integration (FA-24 a FA-30)

#### FA-24 — VS Code extension nativa
**Qué hace:** extensión VS Code con 5 comandos accesibles desde command palette y menú contextual.
**Comandos:**
1. `Stacky: Run agent on current ticket` → quickPick de agente + contexto del archivo actual
2. `Stacky: Open Workbench` → abre `http://localhost:5173` en browser
3. `Stacky: Include this file as context` → POST del archivo al inbox
4. `Stacky: Include selection as context` → POST de la selección al inbox
5. `Stacky: Set active ticket` → input de ADO ID; persiste en globalState
**Status bar:** bottom-left muestra "◆ Stacky: ADO-1234". Click → set active ticket.
**Menú contextual:** `include this file` / `include selection` al hacer click derecho en el editor.
**Build:** `cd vscode_extension && npm install && npm run compile` → `out/extension.js`.

#### FA-25 — Browser bookmarklet "send as context"
**Qué hace:** el operador selecciona texto en cualquier web (Confluence, Jira, etc.) y hace click en el bookmarklet. El texto llega como ContextBlock al backend.
**Cómo obtenerlo:** `GET /api/context/bookmarklet.js` → JS one-liner descargable.
**Endpoint receptor:** `POST /api/context/inbox` con `{url, selection, title?}`.
**Respuesta:** `{block: ContextBlock, hint: "Abrí el editor..."}`.

#### FA-27 — Slack/Teams slash commands
**Qué hace:** endpoint que recibe slash commands estilo Slack y ejecuta operaciones en Stacky Agents.
**Auth:** header `X-Stacky-Slash-Token` con HMAC compare_digest.
**Comandos disponibles:**
- `/stacky run <agent> <ado_id>` → dispara exec; devuelve exec_id + link
- `/stacky status <exec_id>` → estado actual de la exec
- `/stacky approve <exec_id>` → marca como aprobada
- `/stacky discard <exec_id>` → marca como descartada
- `/stacky list <ado_id>` → últimas 10 execs del ticket
- `/stacky help` → lista de comandos
**Endpoint:** `POST /api/slash/stacky` (form-data: `text`, `user_name`).

#### FA-28 — PR review hook
**Qué hace:** recibe un webhook cuando un reviewer @-menciona stacky-bot en un PR, y dispara el `PRReviewAgent` automáticamente.
**Endpoint:** `POST /api/pr/review-webhook` con `{ticket_ado_id, pr_id, diff, description}`.
**Output:** exec del `pr_review` agent con findings en el ticket.

#### FA-29 — CI failure auto-debug
**Qué hace:** recibe un webhook cuando un build/test falla en CI y dispara el `DebugAgent` con el log.
**Endpoint:** `POST /api/ci/failure-webhook` con `{ticket_ado_id, build_log, failed_tests, commit_sha, commit_diff?}`.
**Si el ticket no existe:** lo crea automáticamente como placeholder.
**Output:** exec del `debug` agent con análisis del fallo.

#### FA-30 — CLI `stacky-agents` (referencia)
**Estado:** No implementado (en backlog). Sería `pipx install stacky-agents-cli` con comandos `run`, `status`, `tail`, `approve`.

---

### Categoría E — Cost & quality control (FA-31 a FA-36)

#### FA-31 — Output cache por hash
**Qué hace:** antes de invocar al LLM, computa un hash SHA-256 del (agent_type + versión de prompt + blocks normalizados). Si existe un output cacheado no expirado, lo devuelve directamente.
**TTL:** 7 días.
**Hash computation:** normaliza blocks (quita IDs y fuentes volátiles, mantiene kind+title+content).
**Solo cachea:** execs que pasaron el contract validator (score ≥ 70 y 0 failures).
**Badge en UI:** "🔁 cached" en el header del OutputPanel.
**Metadata:** `from_cache: true`, `cache_key: "abc123..."`.
**Tabla:** `output_cache`.

#### FA-32 — Diff-based re-execution
**Qué hace:** cuando el operador re-corre con un cambio pequeño de contexto (<30%), el sistema detecta el delta y arma un prompt especial: "tu output anterior fue X, el contexto cambió en estos puntos, actualizá solo las secciones afectadas".
**Cómo se activa:** pasar `previous_execution_id` en el payload de `/api/agents/run`.
**Algoritmo:** calcula `change_ratio` por Levenshtein sobre el contenido de cada block; si ratio < 0.30 → genera `delta_prefix`.
**Beneficio:** reduce tokens ~5x y produce outputs más precisos al actualizar solo lo necesario.

#### FA-33 — Cost preview pre-Run
**Qué hace:** muestra estimación de tokens + USD + latencia antes de hacer click en Run.
**Cómo:** debounced (600ms) en el frontend; llama a `POST /api/agents/estimate`.
**Modelo de estimación:** 1 token ≈ 4 caracteres + coste por modelo (tabla hardcodeada actualizable).
**También indica:** si habría cache hit → muestra "cached — gratis · <100ms".
**Componente UI:** `CostPreview` en el footer del editor.

#### FA-34 — Token/cost budgets con enforcement (referencia)
**Estado:** diseñado, no implementado. Tabla `budgets` (scope, period, limit_usd, used_usd). En backlog.

#### FA-35 — Confidence scoring del output
**Qué hace:** calcula un score de confianza 0-100 analizando señales del texto del output: hedge phrases ("no estoy seguro"), TODOs, frases de evasión, longitud, presencia de tablas/código/citas/TUs.
**Señales que bajan el score:** "no estoy seguro", "creo que", "TODO", "FIXME", "quizás", "no puedo determinar".
**Señales que suben:** tablas markdown, bloques de código, citaciones `archivo.ext:NN`, marcadores TU-XXX.
**Dónde se persiste:** `metadata_json.confidence.overall` (0-100) + `.signals` (lista).
**Badge en UI:** `ConfidenceBadge` en el header del OutputPanel con colores: ✓ verde (≥80), ◐ amarillo (60-79), ⚠ rojo (<60).

#### FA-36 — Speculative pre-execution
**Qué hace:** mientras el operador edita el contexto, el backend puede pre-ejecutar el agente en background. Si el hash del contexto coincide al hacer Run → respuesta instantánea.
**Cómo activar:** `POST /api/agents/speculate` con el contexto actual (debounced en frontend).
**Reclamar:** `POST /api/agents/speculate/claim` con el contexto final.
**TTL:** 10 minutos por spec.
**Tabla:** `spec_executions`.

---

### Categoría F — Compliance & safety (FA-37 a FA-41)

#### FA-37 — PII auto-masking pre-prompt + logs
**Qué hace:** antes de mandar cualquier texto al LLM (y antes del cache), enmascara automáticamente identificadores personales.
**Datos enmascarados:** DNI (7-8 dígitos), CUIT (XX-XXXXXXXX-X), email, teléfono, CBU (22 dígitos), tarjeta (16 dígitos).
**Mecanismo:** cada PII recibe un token único `ZZZ_PII_EMAIL_0001Z`. El map `{token: original}` vive sólo en memoria durante el Run. El output se re-hidrata antes de mostrarlo.
**Cross-block consistency:** el mismo email recibe el mismo token en todos los blocks.
**Cache:** cachea la versión masked; re-hidrata al servir.

#### FA-38 — Prompt injection detection (referencia)
**Estado:** diseñado (heurísticas + clasificador). No implementado como servicio. En backlog.

#### FA-39 — Audit immutability con HMAC hash chain
**Qué hace:** al completar cada exec, crea una entrada criptográficamente encadenada con la anterior del mismo ticket.
**Hash de cada nodo:** HMAC-SHA256(`AUDIT_SECRET`, JSON({exec_id, ticket_id, agent_type, started_at, output_hash, prev_hash})).
**Detección de tampering:** `GET /api/audit/:ticket_id/chain` re-computa cada hash y los compara. Si no coinciden → devuelve `{valid: false, first_tampered_exec_id: N}`.
**Secret:** variable de entorno `AUDIT_SECRET` (default dev: "stacky-agents-audit-default-secret-change-in-prod").
**Tabla:** `audit_entries`.

#### FA-40 — Right-to-be-forgotten (GDPR)
**Qué hace:** enmascara PII en outputs históricos de un usuario sin destruir la estructura de la exec.
**Endpoint:** `POST /api/admin/erase` con `{user_email|customer_keyword}`.
**Comportamiento:** aplica PII masker sobre todos los outputs de las execs del user, in-place en BD. Registra la operación.
**Nota:** no borra la exec — sólo enmascara los datos sensibles.

#### FA-41 — Data egress controls
**Qué hace:** policy declarativa que define qué datos pueden mandarse a qué modelo LLM. Se verifica antes de cada invocación.
**Clases de datos detectadas automáticamente:**
- `pii` → DNI/CUIT/email/teléfono en el contexto
- `financial` → CBU/tarjeta en el contexto
- `production` → keywords "producción", "PROD", "data real"
- `regulatory` → keywords "SOX", "BCRA", "GDPR", "HIPAA"
**Acciones:** `block` (cancela la exec con mensaje de error) | `warn` (loguea y continúa).
**Tabla:** `egress_policies` con `data_class`, `allowed_llms` (CSV), `action`, `project`.
**Endpoint check:** `POST /api/egress/check` → devuelve decisión sin ejecutar.

---

### Categoría G — Discoverability & coaching (FA-42 a FA-46)

#### FA-42 — Suggested next agent (markov)
**Qué hace:** después de aprobar un Run, el sistema sugiere qué agente correr a continuación basándose en transiciones históricas aprobadas del mismo ticket.
**Algoritmo:** Markov chain sobre pares (agent_A, agent_B) de execs aprobadas del mismo ticket en ventana de 24h.
**Fallback:** si muestra < 5, usa la cadena clásica (business→functional→technical→developer→qa).
**UI:** `NextAgentSuggestion` aparece en el OutputPanel cuando `verdict="approved"`.
**Endpoint:** `GET /api/agents/next-suggestion?after_agent=technical`.

#### FA-43 — Operator coaching
**Qué hace:** analiza el historial del operador y genera tips personalizados con severidad `info | warning | high`.
**Tips generados:**
- Aprobación ≥85% → "excelente, considerá hacer template"
- Aprobación <50% → "revisá tu pipeline, probá Agent Packs"
- Descarte >25% → "muchos descartes, probá Cost Preview y Fork"
- Re-run >30% → "repetís mucho, mirá los similares antes de re-correr"
- Error >10% → "alta tasa de errores, revisá los logs detallados"
- Confidence promedio <70 → "outputs con baja confianza, agregá más contexto"
**Endpoint:** `GET /api/coaching/tips?user=&days=`.

#### FA-44 — Onboarding sandbox
**Qué hace:** proyecto `__sandbox__` con 4 tickets ficticios y 1 exec pre-aprobada para que operadores nuevos practiquen sin riesgo.
**Tickets del sandbox:**
1. RF-001 — Alta de cliente persona física (To Do)
2. RF-002 — Consulta de saldo de cuenta (Technical review) + exec Functional pre-aprobada
3. RF-003 — Envío de notificación SMS (To Do)
4. RF-004 — Reporte mensual de movimientos (To Do)
**Tour:** overlay de 4 pasos en la UI (localStorage, no se repite). Componente `OnboardingTour`.
**Crear sandbox:** `python scripts/seed_sandbox.py`.

#### FA-45 — Similar past executions
**Qué hace:** panel "Similares aprobadas" en el editor que muestra execs de otros tickets con contenido parecido.
**Algoritmo:** Jaccard sobre tokens del título+descripción del ticket activo vs el texto de las execs.
**UI:** `SimilarPanel` con dos tabs: "Similares aprobadas" y "Graveyard".
**Endpoint:** `GET /api/similarity/similar?ticket_id=&agent_type=&limit=`.

#### FA-46 — Org-wide best practices feed
**Qué hace:** resumen periódico de qué patrones correlacionan con alta tasa de aprobación.
**Secciones del feed:**
1. Agentes por tasa de aprobación y total de runs
2. Top 10 operadores por runs y tasa de aprobación
3. Top 10 reglas de contrato más incumplidas (oportunidad de mejora)
4. Modelos LLM más usados
5. Bloques de contexto que más correlacionan con aprobación (por block_id)
**Endpoint:** `GET /api/best-practices/feed?days=7`.

---

### Categoría H — Power-user composability (FA-47 a FA-52)

#### FA-47 — Agent debate / critic loop
**Qué hace:** el `CriticAgent` recibe el output de cualquier agente y genera desafíos sin reescribirlo.
**Tipo de críticas:** asunciones no declaradas, edge cases no cubiertos, contradicciones internas, preguntas accionables.
**Límite:** máximo 8 puntos.
**Cómo activar:** `POST /api/executions/:id/critique`.
**UI:** botón "Run Critic" en el OutputPanel.

#### FA-48 — Multi-step prompt refinement
**Qué hace:** encadena N prompts secuenciales sobre el mismo agente. Cada paso recibe el output del anterior como contexto adicional.
**Templates predefinidos:**
- `default` → "analizá" → "criticá tu análisis" → "refiná"
- `deep_dive` → "análisis inicial" → "profundizá en lo complejo" → "sintetizá"
- `validate` → "producí" → "validá vs docs/restricciones/decisiones" → "reescribí"
**Custom:** pasar `custom_prompts: [...]` con prompts propios.
**Mecánica:** el paso 1 se dispara inmediatamente; los siguientes en background esperando que el anterior complete (timeout 120s por paso).
**Endpoint:** `POST /api/agents/refine`.

#### FA-49 — Parallel exploration
**Qué hace:** lanza N ejecuciones del mismo agente con el mismo contexto pero distintos modelos. El operador compara y elige la mejor.
**Default (3 variantes):** Haiku (rápido), Sonnet (balanceado), Opus (exhaustivo).
**Custom:** pasar `variants: [{model, label}]`.
**Endpoint:** `POST /api/agents/explore`.
**Respuesta:** `{execution_ids: [N, ...], variants: [...]}`.

#### FA-50 — Agent forking inline
**Qué hace:** permite editar el system prompt del agente sólo para este Run, sin modificar la definición global.
**Cómo ver el default:** `GET /api/agents/:type/system-prompt`.
**Cómo usarlo:** pasar `system_prompt_override: "..."` en el payload de `/api/agents/run`.
**Metadata:** persiste `system_prompt_source: "override"` en `metadata_json`.
**UI:** `SystemPromptDrawer` en el editor, colapsable.

#### FA-51 — Macros declarativas (DSL)
**Qué hace:** permite definir workflows custom como JSON y ejecutarlos por nombre.
**Schema de una macro:**
```json
{
  "id": "hotfix-cobranza",
  "name": "Hotfix Cobranza",
  "steps": [
    {"agent": "technical", "model": "claude-opus-4-7", "auto_continue": false},
    {"agent": "developer"},
    {"agent": "qa"}
  ],
  "options": {"stop_on_first_error": true}
}
```
**Tabla:** `macros` con slug único por proyecto.
**Endpoint:** CRUD en `/api/macros` + `POST /api/macros/:id/run`.
**Diferencia con Packs:** los Packs son recetas inmutables del sistema; las Macros son definidas por el usuario.

#### FA-52 — Webhooks out on exec.completed
**Qué hace:** al completar cada exec, dispara todos los webhooks suscritos al evento `exec.completed` para el proyecto.
**Eventos disponibles:** `exec.completed`, `exec.approved`, `exec.discarded`.
**Seguridad:** HMAC-SHA256 en header `X-StackyAgents-Signature` usando el secret del webhook.
**Delivery:** en background thread; retry log en tabla (last_status, last_error, fires).
**Tabla:** `webhooks` con url, event, project, secret, active.
**Endpoint:** CRUD en `/api/webhooks`.

---

## 7. Modelo de datos completo

### Tablas principales

| Tabla | Propósito | Columnas clave |
|---|---|---|
| `tickets` | Tickets de ADO sincronizados | ado_id, project, title, ado_state, priority, last_synced_at |
| `users` | Operadores del sistema | email, name |
| `agent_executions` | Cada Run (inmutable) | ticket_id, agent_type, status, verdict, input_context_json, output, metadata_json, contract_result_json, started_by, started_at, completed_at, pack_run_id |
| `execution_logs` | Logs por exec | execution_id, timestamp, level, message, group_name, indent |
| `pack_runs` | Estado de un pack en ejecución | pack_definition_id, ticket_id, status, current_step, options_json |

### Tablas de moats

| Tabla | Moat | Descripción |
|---|---|---|
| `output_cache` | FA-31 | Caché por hash de contexto. TTL 7d |
| `anti_patterns` | FA-11 | Errores a evitar por proyecto/agente |
| `webhooks` | FA-52 | Suscripciones a eventos de exec |
| `decisions` | FA-13 | Decisiones técnicas históricas |
| `translation_cache` | FA-22 | Traducciones cacheadas por hash |
| `glossary_entries` | FA-15 | Términos aprobados del proyecto |
| `glossary_candidates` | FA-15 | Candidatos pendientes de review |
| `drift_alerts` | FA-16 | Alertas de degradación de calidad |
| `audit_entries` | FA-39 | Hash chain por ticket |
| `project_constraints` | FA-08 | Restricciones declarativas por proyecto |
| `user_style_profiles` | FA-10 | Perfiles de estilo por operador+agente |
| `spec_executions` | FA-36 | Pre-runs especulativos |
| `egress_policies` | FA-41 | Políticas de egress de datos |
| `macros` | FA-51 | Workflows custom del usuario |
| `execution_embeddings` | FA-01 | Vectores TF-IDF por exec |

### Estructura de `input_context_json`

Array de ContextBlocks. Cada block:
```json
{
  "id": "ticket-meta",
  "kind": "auto | editable | choice",
  "title": "Ticket metadata",
  "content": "Title: RF-008...",
  "items": [{"selected": true, "label": "trunk/OnLine/x.cs"}],
  "source": {"type": "ticket | execution | user-input | glossary | git | bookmarklet | refinement", "...": "..."}
}
```

### Estructura de `metadata_json`

```json
{
  "model": "claude-sonnet-4-6",
  "tokens_in": 8421,
  "tokens_out": 1812,
  "duration_ms": 14037,
  "from_cache": false,
  "pii_masked": true,
  "routing_reason": "default por agente",
  "confidence": {"overall": 87, "sections": {"1. Algo": 90}, "signals": []},
  "few_shot_count": 2,
  "anti_patterns_count": 1,
  "decisions_count": 0,
  "constraints_count": 1,
  "style_memory_active": true,
  "system_prompt_source": "default | override"
}
```

### Estados de `agent_executions.status`

```
running → completed | error | cancelled | discarded
```

### Estados de `agent_executions.verdict`

```
null → approved | discarded
```
(Solo execs `completed` pueden tener verdict.)

---

## 8. Flujo de ejecución (agent_runner)

Cuando se llama a `POST /api/agents/run`, el backend:

1. **Crea la fila** `AgentExecution` en estado `running` en BD.
2. **Abre el log buffer** en memoria (`log_streamer.open(exec_id)`).
3. **Dispara un thread** en background y devuelve `{execution_id, status: "running"}` en < 100ms.

El thread ejecuta estas **10 etapas en orden**:

```
1.  PII mask blocks (FA-37)
    → masked_blocks, mask_map

2.  Cache lookup (FA-31)
    → Si hit: des-enmascara PII, persiste output, cierra thread. FIN.

3.  LLM router decide modelo (FA-04)
    → decision.model, decision.reason (logueado)

4.  Egress policy check (FA-41)
    → Si blocked: falla la exec con mensaje. FIN.

5.  Texto unificado del contexto
    → context_text (para FA-13, FA-08)

6.  Lee usuario (FA-10 style memory input)

7.  compose_system_prompt con 6 fuentes encadenadas:
    a. Override (FA-50) → si existe, usa sólo este
    b. Few-shot (FA-12) → inyecta 2 ejemplos
    c. Anti-patterns (FA-11) → inyecta reglas
    d. Decisions (FA-13) → inyecta decisiones relevantes
    e. Constraints (FA-08) → inyecta obligaciones
    f. Style memory (FA-10) → nota de calibración
    → full_system_prompt, metadata parcial

8.  build_prompt(blocks, delta_prefix?) (FA-32)
    → user_prompt completo

9.  copilot_bridge.invoke(system, user, model, on_log, execution_id)
    → result.output, result.metadata

10. Post-procesamiento:
    a. unmask PII en output (FA-37)
    b. contract_validator.validate() (N1) → contract_result
    c. confidence.score() (FA-35) → confidence metadata
    d. Persiste todo en BD (output, metadata, contract_result, status=completed)
    e. Cache store si contract passed (FA-31)
    f. webhooks.fire_completed_safe() (FA-52)
    g. audit_chain.seal() (FA-39)
    h. embeddings.index_execution() (FA-01)
```

### SSE de logs

El cliente puede abrir `GET /api/executions/:id/logs/stream` para recibir logs en tiempo real. El servidor envía:

```
event: log
data: {"timestamp": "...", "level": "info", "message": "router → claude-sonnet-4-6"}

event: completed
data: {"execution_id": 23, "duration_ms": 14000}

event: ping
data: {}
```

El cliente reconecta automáticamente con `Last-Event-ID`.

---

## 9. Variables de entorno

| Variable | Default | Descripción |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/stacky_agents.db` | URL de la BD |
| `LLM_BACKEND` | `mock` | `mock` (sin LLM) o `copilot` |
| `LLM_MODEL` | `claude-sonnet-4-6` | Modelo default |
| `ADO_ORG` | `` | Organización ADO (e.g. `UbimiaPacifico`) |
| `ADO_PROJECT` | `` | Proyecto ADO (e.g. `Strategist_Pacifico`) |
| `ADO_PAT` | `` | Personal Access Token de ADO |
| `ALLOWED_ORIGINS` | `http://localhost:5173` | CORS whitelist (CSV) |
| `PORT` | `5050` | Puerto del backend |
| `LOG_LEVEL` | `INFO` | Nivel de log (DEBUG/INFO/WARN/ERROR) |
| `AUDIT_SECRET` | `stacky-agents-audit-default-secret-change-in-prod` | HMAC key para audit chain |
| `SLASH_TOKEN` | `stacky-slash-default-secret` | Token para slash commands |
| `NEXT_RELEASE_DATE` | `` | Fecha ISO de próxima release (FA-07) |
| `RELEASE_FREEZE_DATE` | `` | Fecha ISO de code freeze (FA-07) |
| `PROJECT_DB_URL` | `` | URL BD del proyecto para live queries (FA-02) |
| `GIT_REPO_ROOT` | 3 niveles arriba del backend | Path al repo git (FA-05) |

---

## 10. Cómo arrancar el sistema

### Primera vez (setup completo)

```bash
# 1. Clonar / abrir el repo
cd "Tools/Stacky Agents"

# 2. Doble click en start_dashboard.bat (Windows)
#    Hace todo automáticamente:
#    - Crea venv en backend/.venv
#    - pip install -r backend/requirements.txt
#    - Crea backend/.env desde .env.example
#    - Crea BD con seed de 5 tickets dummy
#    - npm install en frontend/
#    - Abre backend (:5050) y frontend (:5173) en ventanas separadas
#    - Abre http://localhost:5173 en el browser
```

### Manual

```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate           # Windows
pip install -r requirements.txt
python scripts/seed_dev.py       # 5 tickets dummy
python app.py                    # http://localhost:5050

# Frontend (otra terminal)
cd frontend
npm install
npm run dev                      # http://localhost:5173
```

### Tests

```bash
cd backend
pytest tests/                    # 40+ tests en 5 archivos test_moats_v1-v6.py
```

### Onboarding sandbox

```bash
cd backend
python scripts/seed_sandbox.py   # Crea proyecto __sandbox__ con 4 tickets
```

---

## 11. Frontend — pantallas y componentes

### Layout (3 columnas fijas)

```
TopBar (header fijo)
│
├── Columna izquierda (280px)
│   ├── TicketSelector    ← lista de tickets con filtro; auto-refresh 60s
│   ├── AgentSelector     ← 8 AgentCards con descripción
│   └── PackList          ← 5 packs con botón ▶
│
├── Columna central (flex)
│   ├── OnboardingTour   ← overlay 4 pasos (primera visita)
│   ├── TicketFingerprint ← N3: análisis automático al seleccionar ticket
│   ├── SystemPromptDrawer ← FA-50: editor del system prompt (colapsable)
│   ├── SimilarPanel     ← FA-45/14: similares + graveyard (colapsable)
│   └── InputContextEditor
│       ├── BlockView × N (auto/editable/choice)
│       ├── ModelPicker   ← FA-04: dropdown del modelo
│       └── Footer
│           ├── TokenCounter
│           ├── CostPreview  ← FA-33: estimación en tiempo real
│           └── RunButton
│
└── Columna derecha (440px)
    ├── OutputPanel
    │   ├── OutputHeader (exec info + 🔁 cached + ConfidenceBadge)
    │   ├── ContractBadge (N1: score + failures)
    │   ├── StructuredOutput (N2: secciones colapsables + citations + mermaid)
    │   ├── OutputTools (FA-22: traducir + FA-23: exportar)
    │   ├── OutputActions (Approve / Send to ADO / Discard)
    │   └── NextAgentSuggestion (FA-42: después de aprobar)
    ├── LogsPanel         ← SSE live logs con filtros y auto-scroll
    └── ExecutionHistory  ← historial del ticket con filtros
```

### Estados de la pantalla principal

1. **Sin ticket:** hero "Seleccioná un ticket"
2. **Ticket sin agente:** `TicketFingerprint` visible + `AgentSelector` destacado
3. **Pre-run (listo):** editor con contexto + botón Run pulsando
4. **Running:** botón "Running ▮▮", LogsPanel abierto, output streameando
5. **Completed (sin verdict):** output renderizado + botones Approve/Discard/Send
6. **Approved:** output + `NextAgentSuggestion`
7. **Error:** output en rojo + logs auto-expandidos + botón Retry

### Componentes clave

| Componente | Moat | Función |
|---|---|---|
| `StructuredOutput` | N2 | Secciones colapsables + copy + citation links + mermaid |
| `MermaidDiagram` | FA-21 | SVG render de diagramas con zoom y link a mermaid.live |
| `ContractBadge` | N1 | Badge con score del contrato y failures |
| `ConfidenceBadge` | FA-35 | Badge de confianza con color semántico |
| `CostPreview` | FA-33 | Estimación de tokens/USD/latencia debounced |
| `ModelPicker` | FA-04 | Dropdown de modelo con razón del router |
| `SimilarPanel` | FA-45/14 | Tabs similares aprobadas + graveyard |
| `SystemPromptDrawer` | FA-50 | Editor del system prompt per-Run |
| `NextAgentSuggestion` | FA-42 | Botones de agente siguiente post-approve |
| `OutputTools` | FA-22/23 | Traducir y exportar el output |
| `OnboardingTour` | FA-44 | Overlay de 4 pasos para nuevos usuarios |
| `TicketFingerprint` | N3 | Análisis automático del ticket al seleccionarlo |

---

## 12. VS Code extension

**Ubicación:** `Tools/Stacky Agents/vscode_extension/`

**Comandos (Command Palette):**
- `Stacky: Run agent on current ticket` → quickPick agente → dispara Run con el archivo actual como contexto
- `Stacky: Open Workbench` → abre el browser en `http://localhost:5173`
- `Stacky: Include this file as context` → envía archivo al inbox
- `Stacky: Include selection as context` → envía selección al inbox
- `Stacky: Set active ticket` → input de ADO ID persistido en globalState

**Menú contextual del editor:** "Include this file" y "Include selection" al hacer click derecho.

**Status bar:** `◆ Stacky: ADO-1234` en el extremo inferior izquierdo. Click → set active ticket.

**Configuración** (settings.json):
- `stackyAgents.apiBase` — URL del backend
- `stackyAgents.userEmail` — email para auth

**Build:**
```bash
cd vscode_extension
npm install
npm run compile
# Para empaquetar:
npx @vscode/vsce package
# Para instalar:
code --install-extension stacky-agents-0.1.0.vsix
```

---

## 13. Integración externa

### Webhooks de salida (FA-52)

Al completar cada exec, el sistema hace POST a todas las URLs suscritas:

```http
POST https://tu-sistema.com/hook
Content-Type: application/json
X-StackyAgents-Signature: abc123def456...

{
  "event": "exec.completed",
  "execution": {
    "id": 23,
    "ticket_id": 5,
    "agent_type": "technical",
    "status": "completed",
    "verdict": null,
    ...
  }
}
```

Gestionar webhooks: `POST /api/webhooks` con `{url, event, project?, secret?}`.

---

### Slack / Teams slash commands (FA-27)

```bash
# Registrar token
export SLASH_TOKEN="mi-secret-seguro"

# Configurar en Slack:
# Slash command URL: https://stacky-agents.ejemplo.com/api/slash/stacky
# Header: X-Stacky-Slash-Token: mi-secret-seguro

# Uso en Slack:
/stacky run technical 1234    # lanza exec
/stacky status 42             # consulta exec #42
/stacky approve 42            # aprueba
/stacky list 1234             # lista execs del ticket
```

---

### CI/CD (FA-29)

```bash
# GitHub Actions example:
- name: Notify Stacky on failure
  if: failure()
  run: |
    curl -X POST https://stacky-agents.ejemplo.com/api/ci/failure-webhook \
      -H "Content-Type: application/json" \
      -d '{
        "ticket_ado_id": 1234,
        "build_log": "${{ steps.build.outputs.log }}",
        "commit_sha": "${{ github.sha }}",
        "failed_tests": ${{ steps.test.outputs.failures }}
      }'
```

---

### PR review hook (FA-28)

```bash
# ADO Repos webhook:
# URL: https://stacky-agents.ejemplo.com/api/pr/review-webhook
# Trigger: Pull Request comment added / reviewer added

curl -X POST /api/pr/review-webhook \
  -d '{
    "ticket_ado_id": 1234,
    "pr_id": 99,
    "diff": "--- a/x.cs\n+++ b/x.cs\n...",
    "description": "Fix cobranza SMS"
  }'
```

---

### Browser bookmarklet (FA-25)

1. Ir a `http://localhost:5173` → panel de settings → "Obtener bookmarklet"
2. O manualmente: `GET http://localhost:5050/api/context/bookmarklet.js` → drag-and-drop a la barra
3. En cualquier web: seleccionar texto → click en el bookmarklet → el bloque llega al inbox de Stacky

---

## Resumen rápido para onboarding de otro agente

```
STACKY AGENTS — FACTS SHEET

Qué es: workbench de IA para tickets ADO. El humano decide cuándo correr cada agente.

Tech stack:
  - Backend: Flask 3.x + SQLAlchemy + SQLite (dev) / Postgres (prod)
  - Frontend: React 18 + Vite + Zustand + TanStack Query
  - LLM: mock por default; conectar copilot_bridge.py al engine real para prod

8 agentes: business | functional | technical | developer | qa | debug | pr_review | __critic__

5 packs: desarrollo | qa-express | discovery | hotfix | refactor

52 moats activos: 8 categorías (context / memory / enrichment / workflow /
                  cost-quality / compliance / discoverability / power-user)

Flujo de un Run (10 etapas): PII mask → cache → LLM router → egress check →
  compose_system_prompt (6 fuentes) → build_prompt → LLM call →
  unmask PII → validate + confidence → persist + seal + index

Para correr: cd "Tools/Stacky Agents" && doble click start_dashboard.bat
Para tests: cd backend && pytest tests/
Para onboarding: python scripts/seed_sandbox.py

Endpoints principales:
  POST /api/agents/run          → dispara una exec
  GET  /api/executions/:id/logs/stream  → SSE de logs
  POST /api/executions/:id/approve      → aprueba
  POST /api/translate           → traduce output
  POST /api/ci/failure-webhook  → CI debug automático

Variables críticas: LLM_BACKEND, ADO_PAT, AUDIT_SECRET, DATABASE_URL
```
