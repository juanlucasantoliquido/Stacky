# Stacky Agents

> **Sistema operativo de agentes** — no es un pipeline. No es una evolución de Stacky.
> Es un producto separado donde el humano selecciona, ejecuta y compone agentes de IA por demanda.

---

## TL;DR

| | Stacky Pipeline (anterior) | **Stacky Agents (este producto)** |
|---|---|---|
| Modelo | Pipeline automático PM → Dev → QA | **Team Screen de empleados + Workbench manual** |
| Disparador | Estados ADO + daemon | **Click humano sobre un agente/empleado** |
| Orden de ejecución | Rígido, secuencial | **Cualquier orden, cualquier veces** |
| Dependencias | Acopladas por estado | **Context chaining opcional** |
| Pantalla de inicio | Dashboard de auditoría | **Team Screen — los agentes son tus empleados** |
| Flujo principal | Estado ADO → cron → output | **Empleado → Ticket → VS Code Copilot Chat** |
| UX | Cron + dashboard de auditoría | **Equipo visual + Editor + Run + VS Code Chat** |
| Mentalidad | "El sistema decide cuándo correr" | **"El humano elige su equipo y asigna tickets"** |
| Trackers soportados | Solo Azure DevOps | **Azure DevOps + Jira + Mantis BT** |
| Proyectos | Uno fijo por .env | **Multi-proyecto: cambio en 1 click** |

---

## Filosofía

> **El humano vuelve al loop.**

Stacky Pipeline funciona como una máquina de estados que mueve tickets sola. Eso es eficiente cuando el camino feliz es el 95% del tráfico — pero cuando algo falla, el operador queda fuera del loop y debe leer logs para entender qué decidió la máquina.

**Stacky Agents invierte la dirección de control** y lo hace visible desde la pantalla de inicio:

### Team Screen — los agentes como empleados

La app arranca en una pantalla tipo "equipo de trabajo": cada agente de VS Code aparece como una **tarjeta de empleado** con avatar pixel art, nombre, rol y especialidad. El operador arma su equipo eligiendo qué agentes quiere ver (de todos los `.agent.md` disponibles en la carpeta de VS Code), les pone apodo y avatar.

**Flujo principal:**
1. El humano elige su empleado (agente).
2. El humano asigna un ticket ADO al empleado.
3. Click OK → se abre **VS Code Copilot Chat** con `@agente` y el contexto del ticket pre-cargado.
4. La conversación ocurre en el chat nativo de VS Code.

**Flujo avanzado (Workbench):**
1. El humano elige el agente desde el workbench clásico.
2. El humano edita el contexto que entra al agente.
3. El humano lee el output, decide si lo usa, lo edita, lo descarta o lo reencadena al siguiente agente.

El Workbench sigue disponible desde un botón en la Team Screen para workflows complejos (packs, chains, historial detallado). El sistema no opina sobre el orden. Si querés correr el QA antes que el Dev, podés. Si querés correr el Functional dos veces con contextos distintos, podés.

---

## Agentes disponibles

| # | Agente | Rol | Input típico | Output típico |
|---|--------|-----|--------------|---------------|
| 1 | **Business** | Texto libre → Epics estructurados | Conversación / brief cliente | HTML con bloques `RF-001`, `RF-002`, actores, reglas, prioridades |
| 2 | **Functional** | Epic → análisis de cobertura | Epic ADO + docs funcionales | `analisis-funcional.md` + `plan-de-pruebas.md`, clasificación CUBRE/GAP/NUEVA |
| 3 | **Technical** | Funcional → traducción técnica | Task ADO + análisis funcional | Comentario 🔬 con 5 secciones (alcance, plan técnico, TUs, notas) |
| 4 | **Developer** | Análisis técnico → código | Task ADO + análisis técnico | Cambios en repo + comentario 🚀 de evidencia |
| 5 | **QA** | Implementación → veredicto | Task + commits | `TESTER_COMPLETADO.md`, verdict PASS/FAIL |

Cada agente es **autocontenido**. Recibe un `input_context`, devuelve un `output`. No conoce el siguiente.

---

## Cómo se compone (sin pipeline)

Tres mecanismos, todos opcionales:

1. **Context chaining manual** — al lanzar un agente, el editor te ofrece auto-fill desde outputs previos del mismo ticket. Vos decidís qué incluir.
2. **Agent Packs** (diferencial) — recetas guiadas: "Pack Desarrollo" abre los 4 agentes con sus contextos pre-cargados, pero cada paso requiere click humano. Es un asistente, no un cron.
3. **Re-run con edición** — cualquier ejecución previa puede clonarse, editarse el contexto y relanzarse. Queda nueva fila en el historial.

---

## Estructura del repo

```
Tools/Stacky Agents/
├── README.md                          ← este archivo
├── docs/
│   ├── 00_VISION.md                   ← cambio de paradigma + product north
│   ├── 01_UX_DESIGN.md                ← wireframes low+high fi, layout, estados
│   ├── 02_ARCHITECTURE.md             ← frontend + backend + integración
│   ├── 03_DATA_MODEL.md               ← AgentExecution + relaciones + queries
│   ├── 04_INTERACTION_FLOWS.md        ← user journeys (team screen, run, re-run, chain, pack)
│   ├── 05_COMPONENTS.md               ← catálogo de componentes UI
│   ├── 06_MIGRATION_FROM_STACKY.md    ← qué se mantiene, qué se descarta, cómo
│   ├── 07_AGENT_PACKS.md              ← propuesta diferencial: packs guiados
│   ├── 08_ROADMAP.md                  ← roadmap por fases + features game-changer
│   └── 09_EVOLUTION_V2.md             ← análisis crítico + features estratégicas
├── backend/                           ← Flask modular
│   ├── README.md
│   ├── requirements.txt
│   ├── app.py                         ← entrypoint Flask + CORS + SSE
│   ├── config.py
│   ├── db.py                          ← SQLite + SQLAlchemy
│   ├── models.py                      ← AgentExecution, Ticket, Pack
│   ├── agent_runner.py                ← núcleo: run_agent(type, ctx)
│   ├── prompt_builder.py              ← modular por agente
│   ├── copilot_bridge.py              ← wrapper del LLM (mock/copilot)
│   ├── project_manager.py             ← gestión multi-proyecto (ADO/Jira/Mantis)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── agents.py                  ← POST /api/agents/run, GET /api/agents, route, estimate
│   │   ├── executions.py              ← GET /api/executions, /api/executions/:id
│   │   ├── tickets.py                 ← GET /api/tickets
│   │   ├── packs.py                   ← GET /api/packs, POST /api/packs/start
│   │   ├── projects.py                ← CRUD proyectos, activo, tracker multi-tipo
│   │   ├── preferences.py             ← GET/PUT /api/preferences (avatares, nicknames)
│   │   ├── logs.py                    ← System logs: list, export, stats, purge
│   │   ├── qa_uat.py                  ← POST /api/qa-uat/run (pipeline Playwright)
│   │   ├── phase4.py                  ← FA-07, FA-16, FA-25, FA-15 (glossary)
│   │   ├── phase5.py                  ← FA-36, FA-47, FA-40, FA-39, FA-08, FA-10
│   │   ├── phase6.py                  ← FA-41, FA-48, FA-49, FA-51, FA-29, FA-28, FA-01, FA-02, FA-17, FA-27
│   │   ├── similarity.py              ← FA-45, FA-14
│   │   ├── decisions.py               ← FA-13 CRUD
│   │   ├── anti_patterns.py           ← FA-11 CRUD
│   │   ├── webhooks.py                ← FA-52 CRUD
│   │   ├── git.py                     ← FA-05 file-context, context-block
│   │   ├── extras.py                  ← FA-43, FA-46, FA-22, FA-23
│   │   └── glossary.py                ← FA-15 entries/candidates
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py                    ← BaseAgent + RunContext + compose_system_prompt
│   │   ├── business.py
│   │   ├── functional.py
│   │   ├── technical.py
│   │   ├── developer.py
│   │   ├── qa.py
│   │   ├── debug.py                   ← FA-29 Debug Agent
│   │   ├── critic.py                  ← FA-47 Critic Agent
│   │   └── custom.py                  ← agentes custom configurables
│   ├── services/
│   │   ├── ado_client.py              ← ADO REST API client
│   │   ├── jira_client.py             ← Jira REST API client (v2/v3)
│   │   ├── mantis_client.py           ← Mantis BT REST/SOAP client
│   │   ├── ado_sync.py                ← sync ADO → BD local
│   │   ├── jira_sync.py               ← sync Jira → BD local
│   │   ├── mantis_sync.py             ← sync Mantis → BD local
│   │   ├── stacky_logger.py           ← logger estructurado async → system_logs
│   │   └── ... (50+ servicios de moats)
│   └── packs/
│       ├── __init__.py
│       └── definitions.py
└── frontend/                          ← React + Vite + TypeScript
    ├── README.md
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts
    ├── index.html
    ├── public/
    │   └── avatars/                   ← SVGs pixel art (trabajadores IT, 15-20 personajes)
    └── src/
        ├── main.tsx
        ├── App.tsx                    ← view router: "team" | "workbench"
        ├── theme.css
        ├── api/client.ts
        ├── hooks/useAgentRun.ts
        ├── services/
        │   ├── preferences.ts         ← localStorage: equipo, avatares, apodos, roles
        │   └── avatarGallery.ts       ← metadata 20 avatares pixel art + resolveAvatarSrc()
        ├── store/workbench.ts
        ├── pages/
        │   ├── TeamScreen.tsx         ← pantalla principal: grid de empleados-agentes
        │   └── Workbench.tsx          ← workbench clásico (accesible desde TeamScreen)
        └── components/
            ├── EmployeeCard.tsx       ← tarjeta de empleado con avatar pixel art
            ├── AgentLaunchModal.tsx   ← modal: buscar ticket → OK → VS Code Chat
            ├── TeamManageDrawer.tsx   ← agregar/quitar agentes del equipo
            ├── EmployeeEditDrawer.tsx ← editar apodo, rol y avatar
            ├── PixelAvatar.tsx        ← display de avatar (galería o base64 custom)
            ├── AvatarPicker.tsx       ← selector de avatar: galería + upload con pixelado
            ├── TicketSelector.tsx
            ├── AgentSelector.tsx
            ├── AgentCard.tsx
            ├── InputContextEditor.tsx
            ├── RunButton.tsx
            ├── OutputPanel.tsx
            ├── LogsPanel.tsx
            ├── ExecutionHistory.tsx
            └── PackLauncher.tsx
```

---

## Cómo correrlo (modo dev)

```bash
# Backend
cd "Tools/Stacky Agents/backend"
python -m venv .venv && source .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py                                            # http://localhost:5050

# Frontend (otra terminal)
cd "Tools/Stacky Agents/frontend"
npm install
npm run dev                                              # http://localhost:5173
```

El frontend habla al backend por `http://localhost:5050`. El backend persiste en `backend/data/stacky_agents.db` (SQLite).

---

## Estado actual del scaffold

| Pieza | Estado |
|---|---|
| Documentación de diseño (00–09) | **Completa** |
| Backend Flask + modelos + endpoints | **Completo** — 52 moats implementados |
| Frontend React + componentes | **Completo** — UI navegable, todas las funcionalidades activas |
| Team Screen (pantalla de empleados) | **Completo** — avatares pixel art, gestión de equipo |
| Agent Launch Modal (→ VS Code Chat) | **Completo** |
| Multi-tracker (ADO + Jira + Mantis) | **Completo** — sync al arranque, switch en 1 click |
| Multi-proyecto | **Completo** — UI + API CRUD + activo persistido |
| QA UAT Pipeline (Playwright) | **Completo** — POST /api/qa-uat/run |
| System Logs API | **Completo** — list, export CSV/JSON, stats, purge |
| Preferences API | **Completo** — pinnedAgents, avatares, nicknames, roles |
| VS Code extension + bridge HTTP (:5052) | **Completo** — 5 comandos + status bar |
| SSE de logs en vivo | **Completo** |
| Agent Packs ejecutándose | **Completo** — 5 packs + advance/pause/resume |

### 52 moats implementados

| ID | Nombre | Categoría |
|---|---|---|
| N1 | Contract Validator | Execution enrichment |
| N2 | Structured Output Renderer | Execution enrichment |
| N3 | Ticket Fingerprint | Discoverability |
| FA-01 | Cross-ticket retrieval (TF-IDF) | Context |
| FA-02 | Live BD context injection | Context |
| FA-03 | Codebase semantic search | Context |
| FA-04 | Multi-LLM routing | Cost & quality |
| FA-05 | Git context awareness | Context |
| FA-06 | Test coverage map | Context |
| FA-07 | Schedule & release context | Context |
| FA-08 | Project constraints injection | Context |
| FA-09 | RIDIOMA/glossary auto-injection | Context |
| FA-10 | Personal style memory | Memory |
| FA-11 | Anti-pattern registry | Memory |
| FA-12 | Best-output few-shot | Memory |
| FA-13 | Historical decisions DB | Memory |
| FA-14 | Output graveyard search | Memory |
| FA-15 | Project glossary auto-build | Memory |
| FA-16 | Drift detection | Cost & quality |
| FA-17 | Auto-typecheck del Developer | Execution enrichment |
| FA-18 | Auto-execute SELECTs | Execution enrichment |
| FA-19 | Output schema endpoint | Execution enrichment |
| FA-20 | Citation linker | Execution enrichment |
| FA-21 | Mermaid diagram render | Execution enrichment |
| FA-22 | Output translator | Execution enrichment |
| FA-23 | Multi-format export | Execution enrichment |
| FA-24 | VS Code extension | Workflow |
| FA-25 | Browser bookmarklet | Workflow |
| FA-27 | Slack/Teams slash commands | Workflow |
| FA-28 | PR review hook | Workflow |
| FA-29 | CI failure auto-debug | Workflow |
| FA-31 | Output cache por hash | Cost & quality |
| FA-32 | Diff-based re-execution | Cost & quality |
| FA-33 | Cost preview pre-Run | Cost & quality |
| FA-35 | Confidence scoring | Cost & quality |
| FA-36 | Speculative pre-execution | Cost & quality |
| FA-37 | PII auto-masking | Compliance |
| FA-39 | Audit HMAC chain | Compliance |
| FA-40 | Right-to-be-forgotten (GDPR) | Compliance |
| FA-41 | Data egress controls | Compliance |
| FA-42 | Suggested next agent (markov) | Discoverability |
| FA-43 | Operator coaching | Discoverability |
| FA-44 | Onboarding sandbox | Discoverability |
| FA-45 | Similar past executions | Discoverability |
| FA-46 | Org-wide best practices feed | Discoverability |
| FA-47 | Agent critic loop | Power-user |
| FA-48 | Multi-step prompt refinement | Power-user |
| FA-49 | Parallel exploration | Power-user |
| FA-50 | Agent forking inline | Power-user |
| FA-51 | Macros declarativas (DSL) | Power-user |
| FA-52 | Webhooks out | Power-user |

**Total: 52 / 52 moats** ✅

---

## Lectura recomendada por rol

- **Producto / UX** → [docs/00_VISION.md](docs/00_VISION.md), [docs/01_UX_DESIGN.md](docs/01_UX_DESIGN.md), [docs/04_INTERACTION_FLOWS.md](docs/04_INTERACTION_FLOWS.md)
- **Frontend** → [docs/01_UX_DESIGN.md](docs/01_UX_DESIGN.md), [docs/05_COMPONENTS.md](docs/05_COMPONENTS.md), [frontend/](frontend/)
- **Backend** → [docs/02_ARCHITECTURE.md](docs/02_ARCHITECTURE.md), [docs/03_DATA_MODEL.md](docs/03_DATA_MODEL.md), [backend/](backend/)
- **Tech Lead** → [docs/02_ARCHITECTURE.md](docs/02_ARCHITECTURE.md), [docs/06_MIGRATION_FROM_STACKY.md](docs/06_MIGRATION_FROM_STACKY.md), [docs/08_ROADMAP.md](docs/08_ROADMAP.md), [docs/09_EVOLUTION_V2.md](docs/09_EVOLUTION_V2.md)
- **Equipo Stacky actual** → [docs/06_MIGRATION_FROM_STACKY.md](docs/06_MIGRATION_FROM_STACKY.md), [docs/07_AGENT_PACKS.md](docs/07_AGENT_PACKS.md)
- **Sponsor / Producto** → [docs/00_VISION.md](docs/00_VISION.md), [docs/08_ROADMAP.md](docs/08_ROADMAP.md), [docs/09_EVOLUTION_V2.md](docs/09_EVOLUTION_V2.md)

---

## Riesgos identificados (y mitigación)

| Riesgo | Mitigación incorporada al diseño |
|---|---|
| Pérdida de coherencia entre outputs | **Context chaining** explícito en el editor: el usuario ve qué outputs previos está reusando |
| Sobrecarga cognitiva del usuario | **Agent Packs** y **presets** de input por agente; defaults inteligentes |
| Outputs inconsistentes | **Templates estrictos** por agente (system prompt + JSON schema en respuesta estructurada) |
| Pérdida de auditoría vs pipeline | **Historial inmutable** por ticket; toda ejecución queda registrada con prompt+output |
| Doble fuente de verdad con Stacky existente | Migración por convivencia: Stacky Agents lee, no escribe en `pipeline_state.py`. Ver [docs/06_MIGRATION_FROM_STACKY.md](docs/06_MIGRATION_FROM_STACKY.md) |
