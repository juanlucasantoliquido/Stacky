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
│   ├── copilot_bridge.py              ← stub que invoca al engine real
│   ├── api/
│   │   ├── __init__.py
│   │   ├── agents.py                  ← POST /api/agents/run, GET /api/agents, GET /api/agents/vscode
│   │   ├── executions.py              ← GET /api/executions, /api/executions/:id
│   │   ├── tickets.py                 ← GET /api/tickets
│   │   └── packs.py                   ← GET /api/packs, POST /api/packs/start
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py                    ← BaseAgent
│   │   ├── business.py
│   │   ├── functional.py
│   │   ├── technical.py
│   │   ├── developer.py
│   │   └── qa.py
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
| Documentación de diseño (00–09) | **Completa** — incluye roadmap + 52 moats catalogados + evolución estratégica V2 |
| Backend Flask + modelos + endpoints | **Runnable** — copilot_bridge en modo mock |
| Frontend React + componentes principales | **Runnable** — UI navegable, llamadas reales al backend |
| **Team Screen (pantalla de empleados)** | **En desarrollo** — `TeamScreen.tsx`, `EmployeeCard.tsx`, avatares pixel art |
| **Agent Launch Modal (→ VS Code Chat)** | **En desarrollo** — bridge `POST localhost:5052/open-chat` ya disponible |
| **Gestión de equipo + avatares** | **En desarrollo** — `TeamManageDrawer`, `AvatarPicker`, `preferences.ts` |
| VS Code extension + bridge HTTP (:5052) | **Implementado** — `/open-chat`, `/invoke`, `/models` |
| SSE de logs en vivo | **Implementado** |
| Persistencia de history y re-run | **Implementado** |
| Agent Packs ejecutándose | **Diseñado + endpoint stub** — UI guía paso a paso |

### Moats implementados (de las 52 del catálogo)

| ID | Nombre | Categoría | Fase | Notas |
|---|---|---|---|---|
| **N1** | Contract Validator | Execution enrichment | Fase 1 | reglas por agente, score 0-100, badge en UI |
| **N2** | Structured Output Renderer | Execution enrichment | Fase 1 | secciones colapsables, copy por sección |
| **N3** | Ticket Pre-Analysis Fingerprint | Discoverability | Fase 1 | tipo / dominio / complejidad / pack sugerido |
| **FA-09** | RIDIOMA / glossary auto-injection | Context | Fase 1 | bloque `[auto]` con términos de dominio detectados |
| **FA-20** | Citation linker | Execution enrichment | Fase 2 | `archivo.ext:NN` y `ADO-XXXX` clickeables (vscode://, ADO) |
| **FA-31** | Output cache por hash | Cost & quality | Fase 3 | hit gratuito si dos operadores corren mismo contexto |
| **FA-33** | Cost preview pre-Run | Cost & quality | Fase 3 | tokens + USD + latencia visible antes de Run |
| **FA-35** | Confidence scoring | Cost & quality | Fase 3 | score heurístico en metadata + badge |
| **FA-45** | Similar past executions | Discoverability | Fase 3 | Jaccard sobre tokens; reemplazable por embeddings en Fase 6 |
| **FA-14** | Output graveyard search | Memory | Fase 3 | búsqueda en discarded / errored para no repetir intentos |
| **FA-12** | Best-output few-shot examples | Memory | Fase 3 | inyecta 1-2 outputs aprobados al system prompt; selecciona por contract+confidence |
| **FA-04** | Multi-LLM routing con override | Cost & quality | Fase 3 | router elige Haiku/Sonnet/Opus por agente+contexto; UI override |
| **FA-37** | PII auto-masking pre-prompt + logs | Compliance | Fase 3 | DNI/CUIT/email/tel/CBU/CARD enmascarados; map en memoria; unmask al render |
| **FA-42** | Suggested next agent (markov) | Discoverability | Fase 4 | aprende transiciones aprobadas; default chain como fallback |
| **FA-50** | Agent forking inline | Power-user | Fase 5 | system prompt editable per-Run; persiste en metadata |
| **FA-11** | Anti-pattern registry | Memory | Fase 3 | tabla + CRUD + injection automática en system prompt |
| **FA-52** | Webhooks out on exec.completed | Power-user | Fase 5 | tabla + delivery con HMAC-SHA256; events: completed/approved/discarded |
| **FA-05** | Git context awareness | Context | Fase 3 | commits + autores + bloque `[auto]` por archivo afectado |
| **FA-13** | Historical decisions database | Memory | Fase 5 | tabla + CRUD + matching por tags + injection en system prompt |
| **FA-43** | Operator coaching | Discoverability | Fase 5 | tips heurísticos por usuario (re-run/discard/error/confidence) |
| **FA-46** | Org-wide best practices feed | Discoverability | Fase 5 | resumen por agente/operador/contract failures/modelos/bloques |
| **FA-22** | Output translator (en/es/pt) | Execution enrichment | Fase 4 | sin re-correr al agente; cache por hash; mock fallback |
| **FA-23** | Multi-format export | Execution enrichment | Fase 4 | md/html/slack/email descargable desde el OutputPanel |
| **FA-19** | Output schema endpoint | Execution enrichment | Fase 2 | `/api/agents/:type/schema` expuesto (consumible por UI) |
| **FA-21** | Mermaid diagram auto-render | Execution enrichment | Fase 4 | detecta ```mermaid en outputs, renderiza SVG + zoom + link mermaid.live |
| **FA-15** | Project glossary auto-build | Memory | Fase 4 | escanea outputs aprobados, extrae candidatos, operador los promueve |
| **FA-16** | Drift detection | Cost & quality | Fase 4 | compara ventanas 7d: approval_rate, confidence, contract_score, error_rate |
| **FA-07** | Schedule & release context | Context | Fase 4 | lee env `NEXT_RELEASE_DATE`/`RELEASE_FREEZE_DATE`, inyecta policy activa |
| **FA-25** | Browser bookmarklet | Workflow | Fase 4 | POST selección desde cualquier web al editor; JS descargable |
| **FA-44** | Onboarding sandbox | Discoverability | Fase 4 | proyecto `__sandbox__` con 4 tickets + exec pre-aprobada + tour 4 pasos |

| **FA-39** | Audit immutability (HMAC chain) | Compliance | Fase 5 | hash chain por ticket; verify detecta tampering exacto; se sella al completar exec |
| **FA-08** | Project constraints injection | Context | Fase 5 | tabla `project_constraints` trigger/keywords → obligaciones inyectadas en system prompt |
| **FA-32** | Diff-based re-execution | Cost & quality | Fase 5 | compute_diff → si < 30% cambió, delta-prompt solo actualiza secciones afectadas |
| **FA-10** | Personal style memory | Memory | Fase 5 | analiza outputs aprobados del operador → profile length/depth/format → nota calibración |
| **FA-36** | Speculative pre-execution | Cost & quality | Fase 5 | background pre-run mientras el operador edita; claim instantáneo si hash coincide |
| **FA-47** | Agent critic loop | Power-user | Fase 5 | `CriticAgent` desafía output sin re-escribirlo; endpoint `/critique` por exec |
| **FA-40** | Right-to-be-forgotten (GDPR) | Compliance | Fase 5 | enmascara PII en outputs históricos por user_email; preserva estructura |
| **FA-18** | Auto-execute SELECTs del output | Execution enrichment | Fase 5 | detecta ```sql en output, ejecuta read-only (mock en dev, PROJECT_DB en prod) |
| **FA-41** | Data egress controls | Compliance | Fase 6 | policies por (proyecto, data_class, allowed_llms) → block/warn antes del LLM call |
| **FA-49** | Parallel exploration | Power-user | Fase 6 | N execs simultáneas con modelos distintos (Haiku/Sonnet/Opus) |
| **FA-48** | Multi-step prompt refinement | Power-user | Fase 6 | chain de N prompts (analizar → criticar → refinar) |
| **FA-51** | Macros declarativas (DSL) | Power-user | Fase 6 | tabla `macros` con definitions JSON ejecutables |
| **FA-29** | CI failure auto-debug | Workflow | Fase 6 | webhook recibe build log → DebugAgent dispara análisis |
| **FA-28** | PR review hook | Workflow | Fase 6 | webhook recibe diff → PRReviewAgent comenta findings |
| **FA-01** | Cross-ticket retrieval (TF-IDF) | Context | Fase 6 | embeddings TF-IDF + cosine; auto-index al completar exec |
| **FA-02** | Live BD context injection | Context | Fase 6 | SELECT-only contra PROJECT_DB con timeout + PII mask + max_rows |
| **FA-17** | Auto-typecheck del Developer | Execution enrichment | Fase 6 | extract code blocks → compile/tsc; bloquea Approve si falla |
| **FA-27** | Slack/Teams slash commands | Workflow | Fase 6 | webhook `/slash/stacky` con HMAC; comandos run/status/approve/discard/list |
| **FA-24** | VS Code extension | Workflow | Fase 6 | comandos: run, includeFile, includeSelection, openWorkbench; status bar |

**Total: 52 / 52 moats activos** ✅ — catálogo completo cerrado.

### Tablas activas
**Fase 1-3:** `tickets`, `agent_executions`, `execution_logs`, `pack_runs`, `users`, `output_cache`, `anti_patterns`, `webhooks`, `decisions`, `translation_cache`
**Fase 4:** `glossary_entries`, `glossary_candidates`, `drift_alerts`
**Fase 5:** `audit_entries`, `project_constraints`, `user_style_profiles`, `spec_executions`
**Fase 6:** `egress_policies`, `macros`, `execution_embeddings`

### Agentes activos
business · functional · technical · developer · qa · debug (FA-29) · pr_review (FA-28) · __critic__ (FA-47)

### Flujo agent_runner actualizado (orden de operaciones)
```
1. PII mask blocks (FA-37)
2. Cache lookup (FA-31)  ← devuelve inmediato si hit
3. LLM router decide modelo (FA-04)
4. compose_system_prompt:
   a. Override (FA-50) | few-shot (FA-12) | anti-patterns (FA-11) |
      decisions (FA-13) | constraints (FA-08) | style memory (FA-10)
5. build_prompt + delta_prefix si re-run incremental (FA-32)
6. copilot_bridge.invoke (modelo decidido por router)
7. unmask PII en output (FA-37)
8. contract validator (N1) + confidence (FA-35)
9. persist + cache store (FA-31) + webhooks (FA-52) + audit seal (FA-39)
```

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
