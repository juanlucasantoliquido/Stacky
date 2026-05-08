# Stacky Agents — README operativo para agentes de IA

> **Para agentes:** este documento describe exhaustivamente qué es Stacky Agents, cómo funciona, qué puede hacer, y cómo interactuar con él. Leerlo completo antes de tomar cualquier decisión sobre el sistema.

---

## Índice rápido

1. [Qué es Stacky Agents](#1-qué-es-stacky-agents)
2. [Arquitectura del sistema](#2-arquitectura-del-sistema)
3. [Cómo arrancar el sistema](#3-cómo-arrancar-el-sistema)
4. [Los 8 agentes disponibles](#4-los-8-agentes-disponibles)
5. [Los 5 Agent Packs predefinidos](#5-los-5-agent-packs-predefinidos)
6. [Herramientas CLI complementarias](#6-herramientas-cli-complementarias)
7. [Todos los endpoints REST](#7-todos-los-endpoints-rest)
8. [Las 52 funcionalidades (moats)](#8-las-52-funcionalidades-moats)
9. [Modelo de datos](#9-modelo-de-datos)
10. [Variables de entorno](#10-variables-de-entorno)
11. [Multi-proyecto y Multi-tracker](#11-multi-proyecto-y-multi-tracker)
12. [QA UAT Pipeline (Playwright)](#12-qa-uat-pipeline-playwright)
13. [System Logs API](#13-system-logs-api)
14. [Rollback de acciones ADO](#14-rollback-de-acciones-ado)
15. [Extensión VS Code](#15-extensión-vs-code)
16. [Pendientes y backlog](#16-pendientes-y-backlog)

---

## 1. Qué es Stacky Agents

**Stacky Agents** es un workbench de agentes de IA para el flujo de desarrollo de tickets en múltiples issue trackers (Azure DevOps, Jira, Mantis BT). Es un **producto separado** del Stacky Pipeline anterior, con soporte multi-proyecto nativo.

### Diferencia fundamental con Stacky Pipeline

| Aspecto | Stacky Pipeline (anterior) | Stacky Agents (este producto) |
|---|---|---|
| Quién dispara los agentes | El sistema (daemon cron) | El humano (click en Run) |
| Orden de ejecución | Rígido (estados ADO) | Libre — cualquier agente, cualquier momento |
| Contexto del agente | Fijo por diseño | Editable antes de cada Run |
| Re-ejecutar | Revertir estado ADO | Click en "Clone & edit" |
| Issue tracker | Solo Azure DevOps | ADO + Jira + Mantis BT |
| Proyectos | Uno fijo por .env | Multi-proyecto, switch en 1 click |
| Trazabilidad | Parcial (artefactos) | Total (cada exec en BD con prompt+output) |
| Pantalla principal | Dashboard de auditoría | Team Screen — agentes como empleados |

### Filosofía central

> El humano vuelve al loop. Cada Run es una decisión consciente del operador.

El sistema NO es un pipeline automático. No tiene cron. No mueve estados de ADO por su cuenta. El operador elige el agente, construye el contexto, hace click en Run, y decide qué hacer con el output (aprobar, descartar, publicar a ADO).

### Flujo principal (Team Screen)

1. El humano elige su empleado (agente) desde la pantalla Team Screen.
2. El humano asigna un ticket ADO al agente.
3. Click OK → se abre VS Code Copilot Chat con `@agente` y el contexto pre-cargado.

### Flujo avanzado (Workbench)

1. El humano elige el agente desde el workbench clásico de 3 columnas.
2. El humano edita el contexto antes de ejecutar.
3. El humano lee el output, decide: aprobar / descartar / publicar a ADO / encadenar al siguiente agente.

---

## 2. Arquitectura del sistema

```
┌─────────────────────────────────────────────────────────────────┐
│  FRONTEND (React + Vite, :5173)                                 │
│  Team Screen + Workbench de 3 columnas:                         │
│  [Ticket + Agente + Packs] | [Editor de contexto] | [Output]   │
└───────────────────────┬─────────────────────────────────────────┘
                        │ HTTPS + SSE
┌───────────────────────▼─────────────────────────────────────────┐
│  BACKEND (Flask 3, :5050)                                       │
│  agent_runner.py — orquesta 10 etapas por Run                  │
│  Blueprints: agents, packs, executions, tickets, projects,     │
│              preferences, logs, qa_uat, phase4-6, ...          │
└───────┬──────────────────┬───────────────────┬──────────────────┘
        │                  │                   │
   SQLite/Postgres    copilot_bridge.py     Issue Tracker
   (todas las tablas)  (LLM engine)        (ADO | Jira | Mantis)
```

### Issue trackers soportados

| Tracker | Auth | Protocolo |
|---|---|---|
| Azure DevOps | PAT | REST v7 |
| Jira Cloud / Server DC | Basic (email + token) | REST v2 / v3 |
| Mantis BT | API Token o usuario/contraseña | REST o SOAP |

El tracker activo se determina por el **proyecto activo** (`/api/active_project`). Al cambiar de proyecto activo, los tickets del panel se sincronizan del nuevo tracker automáticamente.

### Rutas de archivos clave

```
Tools/Stacky/Stacky Agents/
├── README.md                     ← descripción general del producto
├── README_PARA_AGENTES.md        ← este archivo
├── STACKY_AGENTS_COMPLETE.md     ← referencia exhaustiva (52 moats, endpoints, multi-tracker)
├── MejorasStackyAgent.md         ← mejoras aprobadas y estado de implementación
├── backend/
│   ├── app.py                    ← entrypoint Flask; registra blueprints, init_db, startup_sync
│   ├── agent_runner.py           ← núcleo: ejecuta agentes en threads, 10 etapas
│   ├── project_manager.py        ← gestión multi-proyecto (ADO/Jira/Mantis)
│   ├── agents/base.py            ← BaseAgent + RunContext; compose_system_prompt 6 fuentes
│   ├── copilot_bridge.py         ← wrapper del LLM (mock/copilot)
│   ├── log_streamer.py           ← buffer in-memory de logs por exec; SSE feed
│   ├── prompt_builder.py         ← render_blocks(blocks) → markdown
│   ├── db.py                     ← SQLAlchemy engine, init_db(), session_scope()
│   ├── models.py                 ← ORM: Ticket, AgentExecution, ExecutionLog, PackRun, User, SystemLog
│   ├── fingerprint.py            ← análisis de complejidad de tickets
│   ├── contract_validator.py     ← validación de outputs por agente
│   ├── agents/                   ← 8 clases: base, business, functional, technical,
│   │                                developer, qa, debug, critic, custom
│   ├── api/                      ← 20 blueprints Flask
│   │   ├── agents.py / executions.py / tickets.py / packs.py
│   │   ├── projects.py           ← /api/projects/* (multi-proyecto CRUD)
│   │   ├── preferences.py        ← /api/preferences (avatares, nicknames, roles)
│   │   ├── logs.py               ← /api/logs/* (system logs, export, stats, purge)
│   │   ├── qa_uat.py             ← /api/qa-uat/run (pipeline Playwright)
│   │   └── phase4/5/6 + extras + similarity + decisions + anti_patterns + webhooks + git + glossary
│   ├── services/                 ← 50+ servicios de moats + trackers
│   │   ├── ado_client.py / ado_sync.py
│   │   ├── jira_client.py / jira_sync.py   ← Jira Cloud + Server/DC
│   │   ├── mantis_client.py / mantis_sync.py ← Mantis BT REST + SOAP
│   │   └── stacky_logger.py               ← logger estructurado async → system_logs
│   ├── packs/                    ← definición de los 5 packs
│   └── projects/                 ← configuraciones por proyecto ({NOMBRE}/config.json)
├── frontend/                     ← React + Vite + TypeScript
├── vscode_extension/             ← extensión nativa de VS Code
└── docs/                         ← documentación ampliada (00_VISION.md … 09_EVOLUTION_V2.md)
```

### Las 10 etapas de agent_runner por cada Run

Cuando se ejecuta `POST /api/agents/run`, el `agent_runner.py` pasa por estas etapas en orden:

1. **Validate** — valida el payload (agent_type, ticket_id, blocks)
2. **PII masking** — enmascara DNI/CUIT/email/CBU antes de exponer al LLM (FA-37)
3. **Egress check** — verifica políticas de datos sensibles (FA-41)
4. **Cache lookup** — busca hash SHA-256 del contexto en `output_cache` (FA-31)
5. **Prompt composition** — `compose_system_prompt` encadena 6 fuentes: base + style + few-shot + anti-patterns + decisions + constraints
6. **LLM invocation** — `copilot_bridge.invoke()` con modelo elegido por router (FA-04)
7. **Contract validation** — valida que el output cumple el schema del agente
8. **Confidence scoring** — calcula score 0-100 (FA-35)
9. **Audit seal** — crea hash HMAC encadenado (FA-39)
10. **Post-processing** — indexa TF-IDF (FA-01), dispara webhooks (FA-52), cache store (FA-31)

---

## 3. Cómo arrancar el sistema

### Requisitos

- Python 3.8+
- Node.js 18+ (para frontend y VS Code extension)

### Inicio rápido (Windows)

```bat
REM Doble click en start_dashboard.bat
REM Hace automáticamente:
REM   - Crea venv en backend/.venv
REM   - pip install -r backend/requirements.txt
REM   - Crea backend/.env desde .env.example si no existe
REM   - Crea BD y seed de 5 tickets dummy
REM   - npm install en frontend/
REM   - Abre backend (:5050) y frontend (:5173) en ventanas separadas
REM   - Abre http://localhost:5173 en el browser
```

### Manual

```bash
# Backend
cd "Tools/Stacky/Stacky Agents/backend"
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
python app.py                 # http://localhost:5050

# Frontend (otra terminal)
cd "Tools/Stacky/Stacky Agents/frontend"
npm install
npm run dev                   # http://localhost:5173
```

### Tests

```bash
cd backend
pytest tests/
# 40+ tests cubriendo los moats principales
```

### Onboarding sandbox

```bash
cd backend
python scripts/seed_sandbox.py
# Crea proyecto __sandbox__ con 4 tickets ficticios y 1 exec pre-aprobada
```

### Configurar un proyecto nuevo (multi-tracker)

```bash
# Azure DevOps
curl -X POST http://localhost:5050/api/init_project \
  -H "Content-Type: application/json" \
  -d '{"name":"RSPACIFICO","tracker_type":"azure_devops","organization":"UbimiaPacifico","ado_project":"Strategist_Pacifico","pat":"TOKEN"}'

# Jira
curl -X POST http://localhost:5050/api/init_project \
  -H "Content-Type: application/json" \
  -d '{"name":"JIRA_PROJ","tracker_type":"jira","jira_url":"https://empresa.atlassian.net","jira_key":"B2IM","jira_user":"me@empresa.com","jira_token":"ATATT..."}'

# Mantis BT
curl -X POST http://localhost:5050/api/init_project \
  -H "Content-Type: application/json" \
  -d '{"name":"MANTIS_PROJ","tracker_type":"mantis","mantis_url":"https://mantis.empresa.com","mantis_project_id":"1","protocol":"rest","mantis_token":"TOKEN"}'

# Activar proyecto
curl -X POST http://localhost:5050/api/active_project -d '{"name":"RSPACIFICO"}'
```
- Node.js 18+ (para frontend y VS Code extension)

### Backend

```bash
cd "Tools/Stacky/Stacky Agents/backend"
python -m venv .venv
.venv\Scripts\activate       # Windows
pip install -r requirements.txt
python app.py
# → escucha en http://localhost:5050
```

### Frontend

```bash
cd "Tools/Stacky/Stacky Agents/frontend"
npm install
npm run dev
# → escucha en http://localhost:5173
```

### Sandbox (datos de prueba)

```bash
cd "Tools/Stacky/Stacky Agents/backend"
python scripts/seed_sandbox.py
# → crea proyecto __sandbox__ con 4 tickets ficticios
```

### Dashboard alternativo (Stacky pipeline legacy)

```bash
# Tools/Stacky/Stacky Agents/start_dashboard.bat
```

---

## 4. Los 8 agentes disponibles

Cada agente es una clase Python en `backend/agents/` que extiende `BaseAgent`. Tiene: `type`, `name`, `icon`, `description`, `inputs_hint`, `outputs_hint`, `system_prompt()`.

El context del sistema prompt se compone de 6 fuentes encadenadas: prompt base del agente + perfil de estilo del operador (FA-10) + few-shot ejemplos aprobados (FA-12) + anti-patterns del proyecto (FA-11) + decisiones técnicas históricas (FA-13) + constraints del proyecto (FA-08).

---

### 4.1 Business Agent (`type="business"`)

**Rol:** convertir texto libre / entrevistas con el cliente en Epics estructurados en ADO.

**Input esperado:**
- Conversación o brief del cliente
- Notas del operador

**Output que genera:**
- HTML estructurado con bloques `RF-001`, `RF-002`, etc.
- Identificación de actores, reglas de negocio, datos involucrados, prioridades
- Formato: `<hr><h2>RF-XXX — Título</h2>...`
- Si falta información, marca `[PENDIENTE: ...]`

---

### 4.2 Functional Agent (`type="functional"`)

**Rol:** analizar un Epic ADO y producir análisis funcional + plan de pruebas.

**Input esperado:**
- Descripción del Epic con bloques RF-XXX
- Documentación funcional del módulo

**Output que genera:**
- `analisis-funcional.md` con clasificación de cobertura
- `plan-de-pruebas.md` con escenarios de validación
- Clasificación por RF: `CUBRE Sin modificación` / `CUBRE Con configuración` / `GAP Menor` / `Nueva Funcionalidad`

---

### 4.3 Technical Agent (`type="technical"`)

**Rol:** traducir el análisis funcional a un análisis técnico accionable.

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

### 4.4 Developer Agent (`type="developer"`)

**Rol:** implementar código siguiendo exactamente el análisis técnico aprobado.

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

**Regla crítica RIDIOMA:** los inserts RIDIOMA/RTABL/RPARAM van SIEMPRE al archivo maestro existente en `trunk/BD/1 - Inicializacion BD/600804 - Inserts RIDIOMA.sql`. Nunca crear archivos .sql nuevos.

---

### 4.5 QA Agent (`type="qa"`)

**Rol:** validar la implementación y emitir un veredicto PASS/FAIL.

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

### 4.6 Debug Agent (`type="debug"`)

**Rol:** analizar fallos de CI / tests y proponer causa + fix tentativo.

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

**Disparado automáticamente por:** webhook `POST /api/ci/failure-webhook`

---

### 4.7 PR Review Agent (`type="pr_review"`)

**Rol:** revisar un diff de PR y generar findings estructurados.

**Input esperado:**
- Diff del PR
- Descripción del PR
- Convenciones del proyecto

**Output que genera:** lista de findings (máx 5) con:
- Severidad: `blocker | major | minor | nit`
- Ubicación: `archivo:línea`
- Tipo: `bug | security | performance | style | maintainability`
- Detalle + sugerencia de fix

**Disparado automáticamente por:** webhook `POST /api/pr/review-webhook`

---

### 4.8 Critic Agent (`type="__critic__"`)

**Rol:** desafiar el output de otro agente sin reescribirlo.

**Input esperado:**
- Output de cualquier agente (markdown)

**Output que genera:** lista de hasta 8 puntos:
- Asunciones no declaradas
- Edge cases no cubiertos
- Contradicciones internas
- Preguntas que el operador debe responder

**Cómo se invoca:** `POST /api/executions/:id/critique`

---

## 5. Los 5 Agent Packs predefinidos

Los Packs son recetas guiadas de múltiples agentes con **pausa humana** obligatoria entre cada paso. El humano debe hacer "Approve & Continue" para avanzar. Cada paso puede editarse antes de ejecutar.

**Diferencia con Macros (FA-51):** los Packs son recetas inmutables del sistema; las Macros las define el usuario.

| Pack | ID | Pasos | Cuándo usar |
|---|---|---|---|
| Desarrollo | `desarrollo` | Functional → Technical → Developer → QA | Flujo completo desde Epic nuevo |
| QA Express | `qa-express` | QA | Developer ya terminó, sólo validar |
| Discovery | `discovery` | Functional → Technical | Explorar un Epic antes de comprometerse |
| Hotfix | `hotfix` | Technical → Developer → QA | Bug en producción |
| Refactor | `refactor` | Technical → Developer → QA | Mejora sin cambio de comportamiento (`iso_functional`) |

---

## 6. Herramientas CLI complementarias

Estas herramientas están en `Tools/Stacky/Stacky tools/` y son **independientes del servidor**. Son scripts Python standalone que los agentes llaman directamente desde terminal.

### 6.1 ADO Manager (`Stacky tools/ADO Manager/ado.py`)

CLI para gestionar tickets de Azure DevOps. Sin servidor, sin dependencias externas, stdlib Python 3.8+.

**Configuración:** `ado-config.json` con `org`, `project`, `pat`. Fallback automático al PAT en `Tools/PAT-ADO`.

**Acciones disponibles:**

```bash
python ado.py list                          # listar tickets activos
python ado.py list --state "Technical review"
python ado.py list --search "cobranza" --limit 50
python ado.py list --all                    # incluir cerrados

python ado.py get 1234                      # detalle de un ticket

python ado.py create --title "Título" --desc "Descripción"
python ado.py create --title "..." --desc "<h2>HTML</h2>" --html --type "Task" --priority 2 --assigned "user@empresa.com"
# Tipos: Task | Bug | User Story | Feature | Epic
# Prioridades: 1=crítica 2=alta 3=media 4=baja

python ado.py comment 1234 "Texto del comentario"
python ado.py comment 1234 --file comentario.html --html

python ado.py state 1234 "Technical review"
python ado.py state 1234 "Done"

python ado.py comments 1234                 # ver comentarios
python ado.py states                        # estados disponibles
python ado.py types                         # tipos disponibles
```

**Salida JSON siempre:**
```json
{ "ok": true, "action": "get", "result": { "id": 1234, "title": "...", "state": "...", ... } }
{ "ok": false, "action": "comment", "error": "ado_api_404", "message": "HTTP 404 ..." }
```

---

### 6.2 Git Manager (`Stacky tools/Git Manager/git.py`)

CLI para gestionar repositorios Git de Azure DevOps. Sin servidor, stdlib Python 3.8+.

**Configuración:** `git-config.json` con `org`, `project`, `repo`, `pat`.

**Acciones disponibles:**

| Acción | Descripción |
|---|---|
| `repos` | Lista todos los repos del proyecto |
| `branches` | Lista branches de un repo |
| `pr list` | Lista pull requests (filtrable por status, branch) |
| `pr get` | Detalle completo de un PR |
| `pr create` | Crea un PR |
| `pr update` | Actualiza título/descripción de un PR |
| `pr abandon` | Abandona un PR |
| `identity` | Busca usuarios por email/nombre (para GUIDs de reviewers) |

```bash
python git.py repos
python git.py branches --repo Strategist_Pacifico
python git.py pr list --repo Strategist_Pacifico --status active
python git.py pr get 42 --repo Strategist_Pacifico
python git.py pr create --repo Strategist_Pacifico --source feature/X --target main --title "..."
```

---

### 6.3 Batch Test Generator (`Stacky tools/Batch Test Generator/`)

Generador automático de tests unitarios para proyectos C# BatchVC. Lee clases de negocio del proyecto y genera archivos `Test_*.cs` con el patrón BTG-AUTO.

**Archivos de configuración:**
- `config.json` — configuración del proyecto y rutas
- `btg-state.json` — estado persistente del generador

**Directorio de tests generados:** `trunk/BatchVC/TESTBD/Inchost/`

**Convenciones de los tests generados:**
- Cada test lleva el marcador `// [BTG-AUTO] <categoria>`
- Categorías: `IntegrationTrue`, `ConexionInvalida`, `Void/Writer`
- Los archivos siguen el patrón `Test_<NombreClase>.cs`

---

### 6.4 StackyBrain (`StackyBrain/`)

Chat HTML standalone (`chat.html`) para conversaciones con agentes sin VS Code. Arrancar con `iniciar_chat.bat`.

---

## 7. Todos los endpoints REST

**Base:** `http://localhost:5050/api`

### Health

| Método | Endpoint | Descripción |
|---|---|---|
| GET | `/api/health` | `{"ok": true}` — smoke check |

---

### Agentes

| Método | Endpoint | Body / Query | Respuesta |
|---|---|---|---|
| GET | `/api/agents` | — | Lista de 8 agentes con type, name, description |
| POST | `/api/agents/run` | `{agent_type, ticket_id, context_blocks, chain_from?, model_override?, system_prompt_override?, use_few_shot?, use_anti_patterns?, fingerprint_complexity?, previous_execution_id?, delta_prefix?}` | `{execution_id, status:"running"}` (202) |
| POST | `/api/agents/cancel/:exec_id` | — | `{ok: true}` |
| POST | `/api/agents/estimate` | `{agent_type, context_blocks, model?}` | `{tokens_in, tokens_out, cost_usd_total, latency_ms, cache_hit}` |
| POST | `/api/agents/route` | `{agent_type, context_blocks, model_override?, fingerprint_complexity?}` | `{model, reason, available:[...]}` |
| GET | `/api/agents/:type/system-prompt` | — | `{agent_type, system_prompt}` |
| GET | `/api/agents/:type/schema` | — | `{agent_type, rules:[{name, description, weight, severity}]}` |
| GET | `/api/agents/next-suggestion` | `?after_agent=technical` | `[{agent_type, probability, sample_size, source}]` |
| POST | `/api/agents/speculate` | `{agent_type, ticket_id, context_blocks}` | `{spec_id, status}` |
| GET | `/api/agents/speculate/:spec_id` | — | `{...spec, output?}` |
| DELETE | `/api/agents/speculate/:spec_id` | — | `{ok: true}` |
| POST | `/api/agents/speculate/claim` | `{agent_type, context_blocks}` | `{found: bool, spec?}` |
| POST | `/api/agents/explore` | `{agent_type, ticket_id, context_blocks, variants?}` | `{execution_ids, variants}` |
| POST | `/api/agents/refine` | `{agent_type, ticket_id, context_blocks, template?, custom_prompts?}` | `{execution_ids, prompts, first_execution_id}` |

---

### Ejecuciones

| Método | Endpoint | Query / Body | Respuesta |
|---|---|---|---|
| GET | `/api/executions` | `?ticket_id=&agent_type=&status=&limit=` | Lista de execs sin output |
| GET | `/api/executions/:id` | — | Exec completa con output |
| GET | `/api/executions/:id/logs` | — | `[LogLine]` snapshot |
| GET | `/api/executions/:id/logs/stream` | — | **SSE stream** de logs en vivo |
| POST | `/api/executions/:id/approve` | — | Exec con `verdict="approved"` |
| POST | `/api/executions/:id/discard` | — | Exec con `verdict="discarded"` |
| POST | `/api/executions/:id/publish-to-ado` | `{target:"comment"\|"task"}` | `{ok, ado_url}` |
| GET | `/api/executions/:id/diff/:other_id` | — | `{left: exec, right: exec}` |
| POST | `/api/executions/:id/critique` | — | `{execution_id, critique, output_format}` |
| POST | `/api/executions/:id/run-selects` | — | `{queries:[{sql, rows, error}], total_found}` |

---

### Tickets

| Método | Endpoint | Query | Respuesta |
|---|---|---|---|
| GET | `/api/tickets` | `?project=&search=` | Lista con `last_execution` |
| GET | `/api/tickets/:id` | — | Ticket + últimas 50 execs |
| GET | `/api/tickets/:id/fingerprint` | — | `{change_type, domain, complexity, suggested_pack, keywords}` |
| GET | `/api/tickets/:id/glossary` | — | ContextBlock con glosario detectado |

---

### Packs

| Método | Endpoint | Body | Respuesta |
|---|---|---|---|
| GET | `/api/packs` | — | Catálogo de 5 packs |
| POST | `/api/packs/start` | `{pack_id, ticket_id, options?}` | PackRun |
| GET | `/api/packs/runs/:id` | — | PackRun con execs |
| POST | `/api/packs/runs/:id/advance` | — | Avanza al siguiente paso |
| POST | `/api/packs/runs/:id/pause` | — | Pausa |
| POST | `/api/packs/runs/:id/resume` | — | Reanuda |
| DELETE | `/api/packs/runs/:id` | — | Abandona |

---

### Búsqueda y retrieval semántico

| Método | Endpoint | Query / Body | Respuesta |
|---|---|---|---|
| GET | `/api/similarity/similar` | `?ticket_id=&agent_type=&limit=` | `[SimilarHit]` por Jaccard |
| GET | `/api/similarity/graveyard` | `?q=&agent_type=&limit=` | Execs descartadas similares |
| POST | `/api/retrieval/top-k` | `{query, agent_type?, k?, only_approved?}` | `[SemanticHit]` por TF-IDF cosine |
| POST | `/api/retrieval/reindex` | — | `{reindexed: N}` |

---

### Glosario (FA-15)

| Método | Endpoint | Body / Query | Respuesta |
|---|---|---|---|
| GET | `/api/glossary/entries` | `?project=` | Lista de términos activos |
| POST | `/api/glossary/entries` | `{term, definition, project?}` | `{id}` |
| GET | `/api/glossary/candidates` | `?status=pending\|approved\|rejected` | Candidatos para review |
| POST | `/api/glossary/candidates/scan` | `{project?, days?, min_occurrences?}` | `{new_candidates: N}` |
| POST | `/api/glossary/candidates/:id/promote` | `{definition}` | `{entry_id}` |
| POST | `/api/glossary/candidates/:id/reject` | — | `{ok: true}` |

---

### Otros endpoints notables

| Método | Endpoint | Descripción |
|---|---|---|
| GET | `/api/anti-patterns` | Lista anti-patterns del proyecto |
| POST | `/api/anti-patterns` | Crea anti-pattern |
| GET | `/api/decisions` | Lista decisiones técnicas históricas |
| POST | `/api/decisions` | Crea decisión |
| GET | `/api/constraints` | Lista constraints del proyecto |
| POST | `/api/constraints` | Crea constraint |
| GET | `/api/webhooks` | Lista webhooks suscritos |
| POST | `/api/webhooks` | Crea webhook |
| POST | `/api/webhooks/test/:id` | Dispara payload de test |
| GET | `/api/drift/alerts` | Alertas de degradación de calidad |
| POST | `/api/drift/run` | Corre detección de drift |
| GET | `/api/release/context` | Contexto de release activo |
| GET | `/api/audit/:ticket_id/chain` | Verifica integridad del audit chain |
| POST | `/api/audit/:exec_id/seal` | Sella una exec en el audit chain |
| GET | `/api/egress/policies` | Lista políticas de egress |
| POST | `/api/egress/check` | Verifica si el contexto puede enviarse al LLM |
| GET | `/api/macros` | Lista macros definidas por el usuario |
| POST | `/api/macros/:id/run` | Ejecuta una macro |
| POST | `/api/live-db/select` | Ejecuta SELECT read-only contra BD del proyecto |
| POST | `/api/live-db/block` | SELECT → ContextBlock inyectable |
| POST | `/api/typecheck/output` | Valida bloques de código del output |
| POST | `/api/translate` | Traduce output sin re-ejecutar el agente |
| POST | `/api/export` | Exporta output en md / html / slack / email |
| GET | `/api/context/bookmarklet.js` | Snippet JS del bookmarklet para browser |
| POST | `/api/context/inbox` | Recibe texto desde bookmarklet o VS Code extension |
| POST | `/api/slash/stacky` | Slash commands desde Slack/Teams |
| POST | `/api/ci/failure-webhook` | Trigger Debug Agent desde CI |
| POST | `/api/pr/review-webhook` | Trigger PR Review Agent desde ADO |
| GET | `/api/best-practices/feed` | Feed de mejores prácticas del equipo |
| GET | `/api/coaching/tips` | Tips personalizados por operador |
| POST | `/api/admin/erase` | GDPR: enmascara PII de un usuario |

---

## 8. Las 52 funcionalidades (moats)

Organizadas en 8 categorías. Para detalle exhaustivo de cada una, ver [STACKY_AGENTS_COMPLETE.md](STACKY_AGENTS_COMPLETE.md).

---

### Categoría A — Context superpowers (FA-01 a FA-09)

| ID | Nombre | Qué hace | Estado |
|---|---|---|---|
| FA-01 | Cross-ticket retrieval TF-IDF | Indexa input+output de cada exec con vectores TF-IDF. `/api/retrieval/top-k` busca similares por cosine similarity. | Activo |
| FA-02 | Live BD context injection | Ejecuta SELECT read-only contra la BD del proyecto y devuelve ContextBlock. Solo SELECT/WITH. Timeout 5s. Max 50 filas. PII masking automático. | Activo |
| FA-03 | Codebase semantic search | Busca archivos por intención (no por nombre) en el repo. Integra con `codebase_indexer.py`. | Scaffolded |
| FA-04 | Multi-LLM routing | Elige automáticamente el modelo (Haiku/Sonnet/Opus) según agente + complejidad. `model_override` tiene prioridad. | Activo |
| FA-05 | Git context awareness | Devuelve últimos N commits con autor/fecha/subject para archivos del ticket. Caché 5 min. | Activo |
| FA-06 | Test coverage map injection | Inyecta datos de cobertura de tests (coverage XML/lcov) para priorizar TUs faltantes. | Scaffolded |
| FA-07 | Schedule & release context | Lee `NEXT_RELEASE_DATE` y `RELEASE_FREEZE_DATE`. Políticas: normal / soft-freeze / hard-freeze. | Activo |
| FA-08 | Project constraints injection | Reglas declarativas que se activan por keywords del contexto y se inyectan como obligaciones al system prompt. | Activo |
| FA-09 | RIDIOMA / glossary auto-injection | Detecta términos RIDIOMA/RTABL/RPARAM en el contexto y los inyecta con definiciones como bloque `[auto]`. | Activo |

**Routing de modelos (FA-04):**
- `fingerprint_complexity=XL` → Opus siempre
- `tokens > 30.000` → Opus
- `developer + tokens > 12.000` → Opus
- `qa + tokens < 6.000` → Haiku
- `functional + tokens < 3.000` → Haiku
- Default: QA=Haiku, resto=Sonnet

---

### Categoría B — Memory compounding (FA-10 a FA-16)

| ID | Nombre | Qué hace | Estado |
|---|---|---|---|
| FA-10 | Personal style memory | Analiza outputs aprobados del operador → perfil de estilo (longitud/profundidad/formatos). Se inyecta como nota de calibración. Requiere 3+ outputs aprobados. | Activo |
| FA-11 | Anti-pattern registry | Catálogo de errores del equipo a evitar. Se inyectan como "evitá X porque Y" en cada Run. | Activo |
| FA-12 | Best-output few-shot examples | Selecciona 1-2 outputs aprobados del mismo agente+proyecto (mejor score) como ejemplos few-shot. Cap 6.000 chars. | Activo |
| FA-13 | Historical decisions database | Decisiones técnicas pasadas. Se inyectan cuando el contexto contiene keywords relacionados (Jaccard matching). | Activo |
| FA-14 | Output graveyard search | Busca outputs descartados/fallidos similares para evitar repetir soluciones rechazadas. | Activo |
| FA-15 | Project glossary auto-build | Escanea outputs aprobados y extrae candidatos al glosario (bold/ALLCAPS que aparecen ≥2 veces). Flujo: scan → review → promote. | Activo |
| FA-16 | Drift detection | Compara métricas de calidad últimos 7 días vs 7 anteriores. Genera alertas `warning`/`critical` si degrada. | Activo |

**Umbrales de drift (FA-16):**
- `avg_contract_score`: warning -8%, critical -15%
- `approval_rate`: warning -10%, critical -20%
- `error_rate`: warning +8%, critical +15%

---

### Categoría C — Execution enrichment (FA-17 a FA-23)

| ID | Nombre | Qué hace | Estado |
|---|---|---|---|
| FA-17 | Auto-typecheck del output | Valida bloques de código del output con compilador/typechecker (Python nativo, TypeScript `tsc`, C# stub). | Activo |
| FA-18 | Auto-execute SELECTs del output | Detecta bloques SQL en el output y los ejecuta read-only, mostrando resultados inline. Max 5 queries. | Activo |
| FA-19 | Output schema validation | Expone el schema (reglas del contrato) de cada agente via `GET /api/agents/:type/schema`. | Activo |
| FA-20 | Citation linker | Renderiza `archivo.cs:84` como link `vscode://file/...` y `ADO-1234` como link a ADO. | Activo (frontend) |
| FA-21 | Auto UML / sequence diagram | Renderiza bloques ` ```mermaid ` como SVG interactivo con fullscreen, editar en mermaid.live y copiar. | Activo (frontend) |
| FA-22 | Output translator | Traduce el output a es/en/pt sin re-ejecutar el agente. Caché por hash(output+lang). | Activo |
| FA-23 | Multi-format export | Exporta output en `md` / `html` (standalone) / `slack` (mrkdwn) / `email` (draft .eml). | Activo |

---

### Categoría D — Workflow integration (FA-24 a FA-30)

| ID | Nombre | Qué hace | Estado |
|---|---|---|---|
| FA-24 | VS Code extension nativa | 5 comandos en command palette: run agent, open workbench, include file, include selection, set ticket. Status bar con ticket activo. | Activo |
| FA-25 | Browser bookmarklet | Seleccioná texto en cualquier web → click bookmarklet → llega como ContextBlock al backend. | Activo |
| FA-27 | Slack/Teams slash commands | `/stacky run|status|approve|discard|list|help`. Auth HMAC. | Activo |
| FA-28 | PR review hook | Webhook: @mencionar stacky-bot en un PR dispara el PR Review Agent automáticamente. | Activo |
| FA-29 | CI failure auto-debug | Webhook: CI falla → dispara Debug Agent con el build log. Si el ticket no existe, lo crea. | Activo |
| FA-30 | CLI `stacky-agents` | Interfaz de línea de comandos. | Backlog |

---

### Categoría E — Cost & quality control (FA-31 a FA-36)

| ID | Nombre | Qué hace | Estado |
|---|---|---|---|
| FA-31 | Output cache por hash | Cache SHA-256 del (agent_type + versión prompt + blocks normalizados). TTL 7 días. Solo cachea si contract score ≥ 70. | Activo |
| FA-32 | Diff-based re-execution | Si el contexto cambió <30% vs ejecución anterior, arma un delta_prefix en lugar del prompt completo. Reduce tokens ~5x. | Activo |
| FA-33 | Cost preview pre-Run | Muestra tokens + USD estimados antes de hacer click en Run. Si habría cache hit: "cached — gratis · <100ms". | Activo |
| FA-34 | Token/cost budgets | Tabla `budgets` para límites de gasto por usuario/proyecto. | Backlog |
| FA-35 | Confidence scoring | Score 0-100 del output basado en hedge phrases, TODOs, tablas, código, citas. Badge verde/amarillo/rojo. | Activo |
| FA-36 | Speculative pre-execution | Pre-ejecuta el agente mientras el operador edita el contexto. Si el hash coincide al Run: respuesta instantánea. TTL 10 min. | Activo |

---

### Categoría F — Compliance & safety (FA-37 a FA-41)

| ID | Nombre | Qué hace | Estado |
|---|---|---|---|
| FA-37 | PII auto-masking | Enmascara DNI/CUIT/email/teléfono/CBU/tarjeta antes de enviar al LLM. Token `ZZZ_PII_EMAIL_0001Z`. Se rehidrata al mostrar. | Activo |
| FA-38 | Prompt injection detection | Detección heurística de inyección de prompts. | Backlog |
| FA-39 | Audit HMAC hash chain | Cada exec genera un nodo HMAC-SHA256 encadenado. `GET /api/audit/:ticket_id/chain` verifica integridad. | Activo |
| FA-40 | Right-to-be-forgotten GDPR | Enmascara PII de outputs históricos de un usuario sin borrar las execs. `POST /api/admin/erase`. | Activo |
| FA-41 | Data egress controls | Verifica antes de cada invocación si los datos (pii/financial/production/regulatory) pueden enviarse al modelo elegido. | Activo |

---

### Categoría G — Discoverability & coaching (FA-42 a FA-46)

| ID | Nombre | Qué hace | Estado |
|---|---|---|---|
| FA-42 | Suggested next agent (Markov) | Después de aprobar un Run, sugiere qué agente correr siguiente basándose en transiciones históricas del mismo ticket. | Activo |
| FA-43 | Operator coaching | Analiza el historial del operador → tips personalizados con severidad info/warning/high. | Activo |
| FA-44 | Onboarding sandbox | Proyecto `__sandbox__` con 4 tickets ficticios y 1 exec pre-aprobada. Tour de 4 pasos en la UI. | Activo |
| FA-45 | Similar past executions | Panel "Similares aprobadas" — execs de otros tickets con contenido parecido (Jaccard). | Activo |
| FA-46 | Org-wide best practices feed | Resumen periódico de patrones que correlacionan con alta tasa de aprobación. | Activo |

---

### Categoría H — Power-user composability (FA-47 a FA-52)

| ID | Nombre | Qué hace | Estado |
|---|---|---|---|
| FA-47 | Agent debate / critic loop | El Critic Agent desafía el output de otro agente (asunciones, edge cases, contradicciones). | Activo |
| FA-48 | Multi-step prompt refinement | Encadena N prompts sobre el mismo agente (analizá → criticá → refiná). Templates: default / deep_dive / validate. | Activo |
| FA-49 | Parallel exploration | Lanza el mismo agente con 3 modelos distintos en paralelo. El operador compara y elige. | Activo |
| FA-50 | Agent forking inline | Permite editar el system prompt sólo para este Run sin cambiar la definición global. `system_prompt_override`. | Activo |
| FA-51 | Macros declarativas (DSL) | Workflows custom definidos como JSON por el usuario. Diferente a Packs (éstos son del sistema). | Activo |
| FA-52 | Webhooks out on exec.completed | Dispara webhooks externos cuando una exec completa / se aprueba / se descarta. Auth HMAC. | Activo |

---

## 9. Modelo de datos

### Tablas principales

| Tabla | Propósito | Columnas clave |
|---|---|---|
| `tickets` | Tickets ADO sincronizados | `ado_id`, `project`, `title`, `ado_state`, `priority`, `last_synced_at` |
| `users` | Operadores del sistema | `email`, `name` |
| `agent_executions` | Cada Run (inmutable) | `ticket_id`, `agent_type`, `status`, `verdict`, `input_context_json`, `output`, `metadata_json`, `contract_result_json`, `started_by`, `started_at`, `completed_at`, `pack_run_id` |
| `execution_logs` | Logs por exec | `execution_id`, `timestamp`, `level`, `message`, `group_name`, `indent` |
| `pack_runs` | Estado de un pack en ejecución | `pack_definition_id`, `ticket_id`, `status`, `current_step`, `options_json` |

### Tablas de moats

| Tabla | Moat | Descripción |
|---|---|---|
| `output_cache` | FA-31 | Caché por hash de contexto. TTL 7 días |
| `execution_embeddings` | FA-01 | Vectores TF-IDF por exec para retrieval semántico |
| `anti_patterns` | FA-11 | Errores a evitar por proyecto/agente |
| `project_constraints` | FA-08 | Obligaciones declarativas por proyecto/keywords |
| `decisions` | FA-13 | Decisiones técnicas históricas del equipo |
| `glossary_entries` | FA-15 | Términos aprobados del glosario del proyecto |
| `glossary_candidates` | FA-15 | Candidatos pendientes de review |
| `translation_cache` | FA-22 | Traducciones cacheadas por hash(output+lang) |
| `drift_alerts` | FA-16 | Alertas de degradación de calidad por agente |
| `spec_executions` | FA-36 | Ejecuciones especulativas en background |
| `audit_entries` | FA-39 | Audit hash chain inmutable por ticket |
| `egress_policies` | FA-41 | Políticas de control de egress de datos |
| `macros` | FA-51 | Workflows DSL definidos por el usuario |
| `webhooks` | FA-52 | Suscripciones a eventos de exec |

### Campos clave de `agent_executions`

- `status`: `pending | running | completed | failed | cancelled`
- `verdict`: `null | approved | discarded`
- `input_context_json`: array de `ContextBlock` con los bloques de contexto usados
- `output`: markdown del output del agente
- `metadata_json`: `{model_used, tokens_in, tokens_out, cost_usd, from_cache, confidence, fingerprint_complexity, system_prompt_source}`
- `contract_result_json`: `{score, failures:[], warnings:[]}`

---

## 10. Variables de entorno

El archivo `.env` vive en `backend/.env`. No committear. Ver `backend/.env.example`.

| Variable | Descripción | Default dev |
|---|---|---|
| `FLASK_SECRET_KEY` | Secret de la app Flask | — |
| `ANTHROPIC_API_KEY` | API key de Anthropic/Claude | — |
| `ADO_ORG` | Organización de Azure DevOps (override global) | `UbimiaPacifico` |
| `ADO_PROJECT` | Proyecto de ADO (override global) | `Strategist_Pacifico` |
| `ADO_PAT` | Personal Access Token de ADO | (desde `Tools/PAT-ADO`) |
| `JIRA_URL` | URL base de Jira (e.g. `https://empresa.atlassian.net`) | — |
| `JIRA_USER` | Email del usuario Jira | — |
| `JIRA_TOKEN` | API Token Jira o contraseña | — |
| `MANTIS_URL` | URL base de Mantis BT | — |
| `MANTIS_TOKEN` | API Token Mantis REST | — |
| `MANTIS_PROJECT_ID` | ID numérico del proyecto Mantis | — |
| `PROJECT_DB_URL` | Connection string BD del proyecto (FA-02) | — |
| `PROJECT_DB_URL_{PROYECTO}` | Connection string por proyecto específico | — |
| `GIT_REPO_ROOT` | Raíz del repositorio Git (FA-05) | 3 niveles arriba del backend |
| `AUDIT_SECRET` | Secret HMAC para el audit chain (FA-39) | `stacky-agents-audit-default-secret-change-in-prod` |
| `SLASH_TOKEN` | Secret HMAC para slash commands (FA-27) | `stacky-slash-default-secret` |
| `NEXT_RELEASE_DATE` | Fecha próxima release ISO (FA-07) | — |
| `RELEASE_FREEZE_DATE` | Fecha de code freeze ISO (FA-07) | — |
| `SYSLOG_RETENTION_DAYS` | Retención de system_logs en días | `90` |
| `MOCK_LLM` | Si `true`, no llama al LLM real | `false` |

---

## 11. Multi-proyecto y Multi-tracker

### Gestión de proyectos

Cada proyecto vive en `backend/projects/{NOMBRE}/config.json` con su propio tracker, workspace y credenciales. Las credenciales sensibles van en `backend/projects/{NOMBRE}/auth/`.

**Endpoints:**

| Acción | Endpoint | Descripción |
|---|---|---|
| Listar proyectos | `GET /api/projects` | Lista todos los proyectos inicializados con estado |
| Proyecto activo | `GET /api/active_project` | Proyecto activo actual |
| Cambiar activo | `POST /api/active_project` | `{"name": "RSPACIFICO"}` — cambia y sincroniza tickets |
| Crear proyecto | `POST /api/init_project` | Inicializa proyecto con tracker (ADO/Jira/Mantis) |
| Actualizar | `PATCH /api/projects/<name>` | Actualiza configuración del proyecto |
| Eliminar | `DELETE /api/projects/<name>` | Elimina proyecto y su configuración |

### Sincronización automática al arranque

`app.py` ejecuta `_startup_sync()` que detecta el tipo de tracker del proyecto activo y sincroniza los tickets automáticamente. Soporta:
- **Azure DevOps**: via `services/ado_sync.py`
- **Jira**: via `services/jira_sync.py` (Cloud v3 + Server/DC v2)
- **Mantis BT**: via `services/mantis_sync.py` (REST + SOAP)

Si no hay credenciales configuradas, el arranque continúa sin sincronizar (warning en logs).

### Credenciales por proyecto

Las credenciales se almacenan en `backend/projects/{NOMBRE}/auth/`:
- ADO: `ado_auth.json` → `{"org": "...", "project": "...", "pat": "..."}`
- Jira: `jira_auth.json` → `{"url": "...", "user": "...", "token": "..."}`
- Mantis: `mantis_auth.json` → `{"url": "...", "token": "...", "project_id": "...", "protocol": "rest"}`

---

## 12. QA UAT Pipeline (Playwright)

Ejecuta el pipeline de QA automatizado basado en Playwright desde la UI de Stacky Agents. Los resultados quedan en el historial de ejecuciones del ticket.

### Uso

```bash
# Lanzar pipeline (dry-run por defecto)
curl -X POST http://localhost:5050/api/qa-uat/run \
  -H "Content-Type: application/json" \
  -d '{"ticket_id": 70, "mode": "dry-run", "headed": false, "timeout_ms": 30000}'
# → {"execution_id": 42, "stream_url": "/api/executions/42/logs/stream"}

# Seguir logs en tiempo real
curl -N http://localhost:5050/api/executions/42/logs/stream

# Consultar resultado final
curl http://localhost:5050/api/qa-uat/run/42
# → {"pipeline_result": {"verdict": "PASS", ...}}
```

### Modos

| Modo | Comportamiento |
|---|---|
| `dry-run` (default) | Ejecuta Playwright, genera evidencia, NO publica al tracker |
| `publish` | Ejecuta y publica los resultados como comentario en el ticket |

**Veredictos:** `PASS` / `FAIL` / `BLOCKED` / `MIXED`

---

## 13. System Logs API

Todos los eventos del backend se persisten en `system_logs` via `stacky_logger.py` (async, no-bloqueante). Los logs incluyen: HTTP requests, lifecycle de execs, llamadas a trackers externos, errores.

### Endpoints principales

```bash
# Listar logs (con filtros)
GET /api/logs?level=ERROR&source=agent_runner&limit=50

# Exportar como CSV
GET /api/logs/export?format=csv&from=2026-01-01

# Estadísticas por level/source
GET /api/logs/stats

# Purgar logs antiguos
DELETE /api/logs/purge?days=30
```

**Filtros disponibles:** `level`, `source`, `action`, `execution_id`, `ticket_id`, `user`, `from`/`to` (ISO), `q` (full-text).

Los datos sensibles (tokens, passwords, PAT) son **redactados automáticamente** antes de persistir.

---

## 14. Rollback de acciones ADO

Si un agente publicó un comentario o tarea incorrecta en ADO, el operador puede revertirla sin perder el output en Stacky.

```bash
POST /api/executions/42/rollback-ado
```

Comportamiento:
- Borra el comentario/task del tracker (ADO/Jira/Mantis)
- Actualiza `verdict` a `"rolled_back"` en BD local
- Preserva el output para auditoría
- Registra la operación en system_logs

---

## 15. Extensión VS Code

Ubicación: `Tools/Stacky/Stacky Agents/vscode_extension/`

**Build:**
```bash
cd vscode_extension
npm install
npm run compile
# → genera out/extension.js

# Empaquetar e instalar
npx @vscode/vsce package
code --install-extension stacky-agents-0.1.0.vsix
```

**Comandos disponibles desde la command palette:**

| Comando | Acción |
|---|---|
| `Stacky: Run agent on current ticket` | QuickPick de agente + contexto del archivo activo |
| `Stacky: Open Workbench` | Abre `http://localhost:5173` en el browser |
| `Stacky: Include this file as context` | POST del archivo actual al inbox del backend |
| `Stacky: Include selection as context` | POST del texto seleccionado al inbox |
| `Stacky: Set active ticket` | Input del ADO/Jira/Mantis ID; persiste en `globalState` |

**Status bar:** muestra `◆ Stacky: ADO-1234` (bottom-left). Click → set active ticket.

**Menú contextual:** click derecho en editor → "Include this file" / "Include selection".

**Configuración** (settings.json):
- `stackyAgents.apiBase` — URL del backend (default: `http://localhost:5050`)
- `stackyAgents.userEmail` — email para auth

---

## 16. Pendientes y backlog

| ID | Feature | Estado |
|---|---|---|
| FA-34 | Token/cost budgets con enforcement | Backlog — diseñado, tabla `budgets` pendiente |
| FA-38 | Prompt injection detection | Backlog — heurísticas diseñadas |
| FA-30 | CLI `stacky-agents` | Backlog — `pipx install stacky-agents-cli` |

---

## Notas para agentes que lean este documento

- **No modificar BD directamente.** Usar siempre los endpoints REST del backend.
- **No ejecutar DML contra la BD del proyecto.** Solo SELECT read-only via `/api/live-db/select`.
- **Para publicar comentarios en ADO**, usar `POST /api/executions/:id/publish-to-ado` con `target="comment"`.
- **Para cambiar estado de un ticket ADO**, usar la CLI `ado.py state <id> "<estado>"`.
- **El archivo de RIDIOMA maestro** es `trunk/BD/1 - Inicializacion BD/600804 - Inserts RIDIOMA.sql`. Nunca crear SQL nuevos.
- **Cada ejecución es inmutable.** Para re-ejecutar con cambios, usar `Clone & edit` (pasar `previous_execution_id`).
- **El sistema no toma decisiones autónomas.** Toda ejecución de agente requiere que el humano la apruebe antes de publicarla a ADO.
