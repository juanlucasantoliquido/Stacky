# Plan 104 — Filtro de presets por stack + Doctores IA por sección del panel DevOps

**Estado:** CRITICADO v2 → v3 (2026-07-06, APROBADO-CON-CAMBIOS — 2 BLOQUEANTES + 2 IMPORTANTES + 1 MENOR nuevos resueltos)
**Versión:** v3 (v1 → v2 → v3, 2ª crítica adversarial 2026-07-06)
**Fecha:** 2026-07-06 (crítica v3: 2026-07-06)
**Veredicto del juez (v3):** APROBADO-CON-CAMBIOS (2 BLOQUEANTES nuevos —C10 external_id, C11 import— resueltos en F2; contradicciones stale v1 purgadas de §5/F3/DoD).

## Changelog v2 → v3 (2ª crítica adversarial — verificado contra código real)

- **C10 (BLOQUEANTE, resuelto en F2):** el `Ticket` ancla de v2 (F2) NO sellaba
  `external_id = -ticket.id`, pero el plan 90 —del que v2 dice copiar el "patrón EXACTO"—
  descubrió DURANTE la implementación (`devops_agent.py:58-81`, comentario "HALLAZGO impl")
  que la **2ª conversación del mismo proyecto NO puede dejar `external_id=NULL`**: en cada
  `init_db()`, `db._backfill_multi_project_ticket_columns` (`db.py:158-196`) rellena
  `external_id = COALESCE(external_id, ado_id)` ⇒ dos tickets doctor NULL del mismo proyecto
  terminan ambos con `external_id=-3` y **colisionan en el UNIQUE
  `ux_tickets_stacky_tracker_external (stacky_project_name, tracker_type, external_id)`**.
  v2 dropeó la única línea que el 90 aprendió a los golpes. Peor: el propio test C9
  `test_two_clicks_create_two_distinct_tickets` PROBARÍA el crash tras el próximo backfill.
  v3 replica el patrón COMPLETO del 90: `session.flush()` → `ticket.external_id = -ticket.id`
  → `session.flush()`, y setea también `project=project, work_item_type="Task",
  ado_state="Active"` (el 90 los pone). Nuevo test **[ADICIÓN ARQUITECTO v3]**
  `test_second_doctor_ticket_same_project_no_collision` corre el backfill real y verifica 0
  IntegrityError + `external_id` distintos. `session_scope` commitea en `__exit__`
  (`db.py:306`) ⇒ el ticket es visible para el preflight de `run_agent` (patrón 90 probado).
- **C11 (BLOQUEANTE, resuelto en F2):** v2 importaba `from services import _config` y leía
  `_config.config`. **NO existe `services/_config.py`** — todos los endpoints reales
  (incluido el plan 90, `devops_agent.py:8`) usan `import config as _config` (módulo
  top-level). El import de v2 lanzaría `ImportError` al registrar el blueprint ⇒ `api/__init__`
  falla ⇒ **la app no bootea**. v3 corrige a `import config as _config` (paridad con el 90 y
  con `ci.py:18`, `devops.py:9`, `devops_servers.py:13`, `pipeline_generator.py:15`).
- **C12 (IMPORTANTE, resuelto en §5):** la tabla de Riesgos de v2 era stale v1 —citaba
  `run_agent no acepta ticket_id=None`, el test `test_doctor_launches_without_ticket` y
  "github_copilot → 400 fallback", TODO removido por C1/C3. Un modelo menor que leyera §5
  re-introduciría los bugs que el changelog ya arregló. v3 reescribe la tabla a la realidad v2/v3.
- **C13 (IMPORTANTE, resuelto en F3 + DoD):** "Impacto por runtime" de F3 y la DoD todavía
  decían "Copilot puede caer a 400 / copilot con fallback 400" —contradice C3 (copilot ES
  runtime válido de `run_agent`, `agent_runner.py:94,219,373`; NO se rechaza). v3 alinea:
  los 3 runtimes funcionan; el único 400 es para runtimes inventados (`"foo"`).
- **C14 (MENOR, resuelto en DoD):** la DoD decía "12 tests backend verdes" pero F2 lista 13
  (ahora 14 con la regresión de C10). v3 unifica el conteo a **14**.

## Changelog v1 → v2 (crítica adversarial)

- **C1 (BLOQUEANTE, resuelto en F2):** v1 decía que `agent_runner.run_agent` aceptaba
  `ticket_id=None` ("fire-and-forget, sin conversación ancla"). **FALSO verificado contra
  el código real**: el signature es `def run_agent(*, agent_type, ticket_id: int, ...)`
  (`agent_runner.py:77-98`) — `ticket_id` es OBLIGATORIO y se usa en el preflight G0.1
  (`session.query(Ticket).filter_by(id=ticket_id).first()`, `:108`), en el guard de resume
  (`:637`) y para crear el `AgentExecution`. El propio plan 90 —del que v1 dice "reuso el
  cableado"— crea SIEMPRE un `Ticket` de conversación ANTES de llamar a `run_agent`
  (`devops_agent.py:70` `Ticket(...)`, `:82` `conversation_id = ticket.id`, `:241`
  `ticket_id=conversation_id`). Con la letra de v1, `run_agent(ticket_id=None)` lanzaría
  `TypeError` o rompería en el preflight — el doctor NUNCA arrancaba, y el test
  `test_doctor_launches_without_ticket` era una trampa verde-falsa (v1 decía "si None no
  funciona, cae al fallback -3" sin especificar el fallback). v2 FIJA el camino real: el
  endpoint doctor crea un `Ticket` ancla **exacto** al patrón del plan 90 (`Ticket(...,
  ado_id=_DOCTOR_CONVERSATION_ADO_ID, title=f"Doctor DevOps · {section_id} · {project}")`)
  y pasa su `id` como `ticket_id`. Se reusa la constante `_CONVERSATION_ADO_ID` del 90 con
  un valor DISTINTO (`_DOCTOR_CONVERSATION_ADO_ID = -3`) para distinguir doctor de chat en
  el historial. El ticket se persiste (igual que el plan 90 persiste el de conversación);
  no es "fire-and-forget invisible" — es "ancla determinista, como el 90". Nuevo test
  `test_doctor_creates_anchor_ticket` blinda este invariante.
- **C2 (IMPORTANTE, resuelto en F2):** v1 importaba `current_user` de `api._helpers` con
  el alias `from api._helpers import current_user as _cu` y la llamaba `_cu()`. Verificado:
  el plan 90 la importa vía `_current_user()` local (`devops_agent.py:21-25`) que a su vez
  llama a `current_user` de `api._helpers`. v2 usa el MISMO helper `_current_user` del
  módulo `devops_agent` (no duplica la indirección): `from api.devops_agent import
  _current_user` — paridad canónica con el 90, sin riesgo de drift si el plan 90 cambia el
  origen de `current_user`.
- **C3 (IMPORTANTE, resuelto en F2 + §3):** v1 declaraba paridad 3 runtimes "ya probada en
  el plan 90 (claude_code_cli + codex_cli)" y trataba `github_copilot` como "probablemente
  no registrado como runtime de agente ⇒ 400 controlado". Esto es una contradicción no
  resuelta: `run_agent` tiene `runtime: str = "github_copilot"` como DEFAULT
  (`agent_runner.py:94`) y lo despacha al `copilot_bridge` (`:219`, `:373`, `:537`) — o
  sea, github_copilot ES un runtime de agente perfectamente válido, no un caso a rechazar.
  v2 corrige: los 3 runtimes están soportados (`claude_code_cli`, `codex_cli`,
  `github_copilot`), el backend NO rechaza copilot (no hay 400). El test
  `test_runtime_no_soportado_400` se mantiene SOLO para runtimes inventados (`"foo"`). Se
  elimina el "fallback 400 para copilot" — era un falso síntoma heredado de confundir el
  guard del chat del plan 90 (que rechaza copilot para **chat conversacional** por
  `devops_chat_requires_cli_runtime`, `devops_agent.py`) con el dispatcher de run_agent
  (que SÍ acepta copilot). El doctor NO es chat conversacional, es run_agent puro ⇒ copilot
  válido. Documentado en §3.1.
- **C4 (IMPORTANTE, resuelto en F2 + F5):** v1 decía "la respuesta markdown se consume vía
  el canal EXISTENTE de logs/streams del execution_id" SIN especificar cuál. El plan 90
  consume la respuesta vía el stream de logs del `execution_id`
  (`DevOpsAgentSection.tsx` + `endpoints.ts:3126`). v2 FIJA el camino: el frontend reusa el
  endpoint `GET /api/executions/<id>/logs` (stream SSE) ya existente, y muestra la
  respuesta en el panel del **agente DevOps del 90** referenciado por `execution_id` +
  `conversation_id` (el ticket ancla creado en C1). El operador ve "Análisis lanzado
  (execution #N, conversación #M). Ver en el panel Agente DevOps" con un link que cambia el
  tab activo. NO se inventa canal nuevo, NO se duplica renderer markdown.
- **C5 (IMPORTANTE, resuelto en F1):** v1 permitía que el botón "Detectar stack" del plan
  97 auto-setee `setStackFilter(detected)` "si la flag del 97 está ON" — pero NO verificaba
  que `detected` sea un `StackId` válido del plan 104. El detector del 97 devuelve
  `"python" | "node" | "dotnet" | null` (`pipeline_stack_detector.py:1036`) — los 3 son
  `StackId` válidos, PERO si el 97 evoluciona y agrega un stack nuevo, el cast
  `detected as StackId` introduce un bug silencioso. v2 añade un guard `isStackId(x)` que
  valida contra `STACK_OPTIONS` antes de setear el filtro; si no es válido, no muta el
  filtro (degrada silencioso, sin romper). Test `isStackId_rejects_unknown` en F0.
- **C6 (MENOR, resuelto en F2):** v1 usaba `kind: "raw-conversation"` en el
  `context_blocks` del doctor. Verificado: el plan 90 usa `{"source": {"type":
  "devops_panel"}}` y el `kind` real del canal de conversación es manejado por
  `_launch_turn`. v2 deja `kind` sin hardcodear (omite la key) para heredar el default del
  `agent_runner`/plan 90 — paridad canónica.
- **C7 (MENOR, resuelto en F3):** v1 usaba `styles.btnPrimary`/`styles.textMuted` en
  `SectionDoctorButton.tsx` sin verificar que existan. El plan 87/96 ya los usa en otros
  componentes devops — verificado existen. v2 lo mantiene PERO añade una NOTA literal: si
  un modelo menor no encuentra esas clases, cae a estilos inline (no rompe `tsc`).
- **C8 (MENOR, resuelto en F4):** v1 decía "editar `test_harness_flags.py` (
  `_REQUIRES_MAP_FROZEN`)" en F4 pero la memoria `harness-requires-r4-depth1` documenta
  que el mapa vive en `tests/test_harness_flags_requires.py` (archivo DISTINTO). v2
  corrige la cita literal (F4 ya lo tenía bien en el cuerpo, pero el encabezado de la
  sección lo confundía — unificado).
- **C9 (MENOR, resuelto en §3 + F2):** v1 no especificaba qué pasa si el operador clickea
  "Doctor" dos veces seguidas (run pegado en "running" / duplicación). v2 añade: el botón
  se deshabilita mientras `busy` (ya en v1) Y el backend es idempotente porque crea un
  `Ticket` nuevo por invocación (no reutiliza el anterior) — cada click es una conversación
  doctor distinta, sin ancla compartida. El operador puede abortar vía el
  `ActiveRunsPanel`/cancel del plan 90 (reuso del `copilot_bridge.cancel` /
  `claude_code_cli_runner.cancel`).
- **[ADICIÓN ARQUITECTO v2] (F2 + F3):** el doctor RECIBE el YAML renderizado del pipeline
  ACTIVO (no solo el `spec` draft) cuando la sección lo expone, vía un parámetro opcional
  `rendered` en el payload. Hoy el builder renderiza YAML ADO+GitLab via preview (plan
  88/99). El doctor pasa AMBOS YAML al contexto de la IA — así la IA razona sobre el
  pipeline REAL que se commitearía, no sobre una abstracción. Cero costo extra, paridad
  ADO+GitLab reforzada, HITL intacto (solo lectura). v1 pasaba solo `spec` + previews
  opcionales "si existen"; v2 los hace PARTE DEL CONTRATO del payload (keys `yaml_ado` /
  `yaml_gitlab` tipadas, `null` si la sección no los tiene — el backend los ignora si
  faltan).

## Pedido textual del operador
**Pedido textual del operador:** "En la sección de DevOps aparecen muchos presets de DevOps y
me ensucian. Debería tener una parte donde, una vez que selecciono un stack como .NET, filtre solo
los de .NET. Y también que haya un doctor de pipelines y despliegues en cada sección, un doctor
diferente, donde haga una llamada a un agente IA (ya sea Claude, Codex o GitHub) con el contexto
necesario para que arregle o mejore la pipeline o despliegue."
**Dependencias:** plan 97 IMPLEMENTADO (`717a77f5` — presets por stack + biblioteca de ≥60 acciones
+ detector opcional de stack), plan 90 IMPLEMENTADO (`5859ceba` — agente DevOps conversacional
multi-turno + `_launch_turn` + `run_agent(agent_type="devops", ...)`), plan 87 IMPLEMENTADO
(`84a9ecb5` — host del panel + contrato de extensión §3.12 + `DEVOPS_SECTIONS` + `FlagGateBanner`).
**No depende de** la serie 93-96 (todas CRITICADAS, sin implementar): el plan 96 (doctor de
diagnóstico post-fallo por regex) es COMPLEMENTARIO y NO se superpone (el 96 clasifica fallos ya
ocurridos sin invocar IA; este plan 104 invoca IA para ANALIZAR/MEJORAR el pipeline o despliegue).
Puede implementarse en paralelo a 93-96.

---

## 1. Objetivo + KPI

Entregar DOS features al panel DevOps, ambas ADITIVAS, opt-in con default seguro, paridad 3
runtimes, cero trabajo extra al operador:

**Feature A — Filtro de presets/snippets/recetas por stack.** Hoy el catálogo del plan 97
(4 presets + ≥60 snippets + ≥11 recetas) se muestra TODO junto y el operador reporta que "ensucia".
Se agrega un **selector de stack** (`dotnet` | `node` | `python` | `go` | `rust` | `java` | `php` |
`generic` | `all`) en el builder de pipelines que filtra y muestra SOLO los elementos relevantes
al stack elegido. Opcionalmente, el botón "Detectar stack" del plan 97 pre-selecciona el filtro.

**Feature B — Doctores IA por sección.** Cada sección relevante del panel DevOps
(Pipeline Builder, Environments, Publications — y CommitPipelineModal/TriggerPipeline como
extensión) gana un botón **"Doctor"** que invoca a un agente IA (Claude Code CLI, Codex CLI o
GitHub Copilot Pro) pasándole el **contexto estructurado de ESA sección** (YAML del pipeline,
definición de environment, spec de publicación, etc.) para que ANALICE y proponga
arreglos/mejoras concretos en markdown. El doctor PROPONE, nunca aplica (HITL innegociable). El
operador ve la respuesta en un panel de texto y decide manualmente qué hacer.

**KPI (aspiracional; los criterios binarios están en cada fase):**
- Feature A: el operador elige un stack y ve ≥50% menos elementos irrelevantes en la galería de
  presets/snippets/recetas (en `.NET`, 0 snippets de `composer`/`cargo`/`go`). Cero clics de
  configuración nueva (es un `<select>` siempre visible, default `all` = comportamiento actual).
- Feature B: cada sección con doctor entrega un análisis IA con ≤1 click del operador (sin
  copy-paste manual del YAML, sin prompts de cero). Funciona en los 3 runtimes con paridad
  (mismo `run_agent`, mismo `agent_type="devops"`, distinto `context_blocks` por sección).
- 0 pasos manuales obligatorios nuevos. 0 flags nuevas obligatorias para usar la feature B
  (reusa `STACKY_DEVOPS_AGENT_ENABLED` del plan 90, default `true`). 0 autocommuting/aplicar
  automático (HITL).

## 2. Por qué ahora / gap que cierra (evidencia)

| Hecho verificado | Evidencia (archivo:línea) |
|---|---|
| El plan 97 entregó 4 presets, ≥60 snippets y ≥11 recetas, TODO mostrado sin filtro | `frontend/src/devops/pipelinePresets.ts`, `pipelineStepSnippets.ts`, `pipelineRecipes.ts` (implementación plan 97) |
| El `<select>` de snippets de F1-ter agrupa por `category`, NO por stack | `frontend/src/components/devops/PipelineBuilderSection.tsx` (F1-ter v4 del 97) |
| Los snippets YA tienen info de stack implícita en el `script`/`id` (`dep-npm-ci`, `dotnet restore`, `cargo fetch`), pero ningún campo `stack` los clasifica | `pipelineStepSnippets.ts` (interface `StepSnippet` no tiene `stack`) |
| El operador declaró textualmente que "ensucia" (ver pedido) | — |
| El cableado canónico para invocar a un runtime IA ya existe y es runtime-agnóstico | `backend/api/devops_agent.py:219` (`_launch_turn` → `agent_runner.run_agent(agent_type="devops", runtime=..., context_blocks=...)`) |
| `run_agent` despacha a los 3 runtimes (claude_code_cli, codex_cli, copilot) con paridad | `backend/agent_runner.py:77-98,375-394` (verificado en plan 90 C5) |
| `STACKY_DEVOPS_AGENT_ENABLED` ya existe con default `true` (operador la activó 2026-07-05) | `backend/config.py:883-884`, `backend/api/devops.py:36` |
| `DevOpsAgentApi.start` ya acepta `runtime` y `message` y devuelve `execution_id` | `frontend/src/api/endpoints.ts:3126-3137`, `backend/api/devops_agent.py:84` |
| NO existe hoy ningún "doctor IA por sección": el plan 96 es doctor post-fallo por regex (sin IA) | `docs/96_PLAN_DOCTOR_PIPELINES_DIAGNOSTICO_FALLOS.md` (CRITICADO, no implementado) |

**Gap Feature A:** los elementos del plan 97 carecen de clasificación por stack → el operador ve
todo junto → reporta "ensucia". Cerrar el gap es barato: agregar campo `stack` a los datos
estáticos + un `<select>` filtro. Valor alto (afecta el 100% del uso del builder).

**Gap Feature B:** no existe manera de pedirle a la IA "analizá ESTE pipeline/ESTE environment y
proponé mejoras" desde el panel. El operador tendría que copiar el YAML, abrir el agente DevOps
del plan 90, pegarlo y pedirlo a mano — fricción alta. El doctor por sección automatiza el
armado del contexto y reusa el cableado de invocación ya probado.

## 3. Principios y guardarraíles (NO negociables)

1. **3 runtimes con paridad (Codex CLI / Claude Code CLI / GitHub Copilot Pro):**
   - Feature A: 100% UI + datos estáticos. Cero impacto en runtimes.
   - Feature B: invoca al runtime vía `agent_runner.run_agent(agent_type="devops", runtime=...)`
     — mismo camino que el plan 90, ya probado en los 3 runtimes. El operador elige runtime en
     el botón del doctor (mismo `<select>` que `DevOpsAgentSection.tsx:116`). Paridad real.
2. **Cero trabajo extra para el operador:** Feature A es un `<select>` siempre visible (default
   `all` = comportamiento actual). Feature B es un botón opt-in (default `off` implícito: no se
   invoca nada hasta que el operador hace click). Ninguna flag nueva obligatoria.
3. **Human-in-the-loop innegociable:** el doctor PROPONE markdown con análisis/mejoras; NUNCA
   escribe archivos, NUNCA aplica diffs, NUNCA commitea. El operador lee y decide. Prohibida la
   autonomía proactiva. Feature A solo filtra la vista (no aplica ningún cambio al spec).
4. **Mono-operador, sin auth real:** ningún concepto de roles/permisos.
5. **Paridad dura ADO+GitLab:** el doctor pasa el `PipelineSpecDraft` y opcionalmente el YAML de
   AMBOS renderers (`to_ado_yaml`/`to_gitlab_yaml`) para que la IA razone sobre el pipeline real.
6. **No degradar lo existente:** el catálogo del plan 97, `_launch_turn`, `run_agent`,
   `DevOpsAgentApi`, `DevOpsAgentSection` NO cambian de contrato. Todo es ADITIVO.
7. **Reusar, no reinventar:** el doctor reusa `agent_runner.run_agent` (NO un nuevo endpoint de
   IA); Feature A reusa los datos estáticos del 97 (NO nuevos presets).
8. **Ratchet de tests:** todo test backend nuevo se registra en
   `backend/scripts/run_harness_tests.sh` **y** `run_harness_tests.ps1`.
9. **Ayuda llana (plan 86):** la flag nueva (si la hubiera) necesita `PlainHelp`. En este plan la
   única flag nueva es `STACKY_DEVOPS_SECTION_DOCTOR_ENABLED` (Feature B), con default OFF para
   que el operador la encienda por UI cuando quiera; Feature A no introduce flag.
10. **Nunca 500 / nunca bloquear:** el doctor degrada siempre a un mensaje en llano ("no pude
    lanzar el análisis, ver consola") si `run_agent` falla — nunca deja al operador colgado.

## 4. Fases

> Comando de tests backend (por archivo, venv del repo — suite completa contaminada, plan 49):
> `"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/<archivo>" -q`
> ejecutado desde `Stacky Agents/backend`. Gate frontend: `npx tsc --noEmit` (0 err) +
> `npx vitest run <archivo>` SIEMPRE por archivo.

---

### FEATURE A — Filtro de presets/snippets/recetas por stack

### F0 — Clasificación por stack de los datos estáticos del plan 97

**Objetivo:** cada preset, snippet y receta del plan 97 declara a qué stack(es) pertenece, sin
cambiar el `build()` ni el `StepDraft` que produce. Aditivo, puro, sin flag.

**Archivo a EDITAR:** `Stacky Agents/frontend/src/devops/pipelinePresets.ts`

Agregar campo `stack` a `PipelinePreset` y poblarlo en cada uno de los 4 presets existentes:

```ts
export type StackId = "dotnet" | "node" | "python" | "go" | "rust" | "java" | "php" | "generic";

export interface PipelinePreset {
  id: PresetId;
  label: string;
  description: string;
  stack: StackId;            // Plan 104 F0 — clasificación para el filtro
  build: () => PipelineSpecDraft;
}
// python  -> stack: "python"
// node    -> stack: "node"
// dotnet  -> stack: "dotnet"
// generic -> stack: "generic"
```

**Archivo a EDITAR:** `Stacky Agents/frontend/src/devops/pipelineStepSnippets.ts`

Agregar campo `stacks` a `StepSnippet` (`readonly StackId[]` — un snippet puede aplicar a varios
stacks, ej. `sec-trivy-fs` aplica a todos; `dep-npm-ci` solo `["node"]`). Clasificar los ≥60
snippets existentes por inspección del `id`/`script`:

```ts
export interface StepSnippet {
  id: string;
  category: SnippetCategory;
  stacks: readonly StackId[];   // Plan 104 F0 — a qué stacks aplica; [] = "all"
  label: string;
  description: string;
  needsEdit?: boolean;
  requires?: string;
  build: () => StepDraft;
}
```

**Tabla de clasificación determinista** (el implementador la aplica literalmente — si un `id`
contiene el token del stack, se clasifica así; los genéricos como `versionar`/`infra` van a
`[]` = todos):

| Token en `id` o `script` | stack |
|---|---|
| `pip`, `flake8`, `pytest`, `black`, `ruff`, `poetry`, `mypy`, `bandit`, `twine`, `pip-audit`, `python -m`, `coverage` | `python` |
| `npm`, `yarn`, `eslint`, `prettier`, `jest`, `vitest`, `tsc`, `node` | `node` |
| `dotnet`, `nuget` | `dotnet` |
| `go `, `gofmt`, `go mod`, `go test`, `go build`, `go vet` | `go` |
| `cargo`, `rust`, `clippy`, `rustc` | `rust` |
| `mvn`, `maven`, `gradle`, `gradlew`, `java` | `java` |
| `composer`, `phpunit`, `php` | `php` |
| `docker`, `git describe`, `git rev-parse`, `sonar`, `trivy`, `gitleaks`, `semgrep`, `hadolint`, `yamllint`, `terraform`, `helm`, `ansible`, `tar -czf` | `[]` (aplica a todos) |

**Archivo a EDITAR:** `Stacky Agents/frontend/src/devops/pipelineRecipes.ts`

Agregar campo `stack` a `StepRecipe` y poblarlo (las recetas del 97 ya son por stack:
`ci-python`→`python`, `ci-node`→`node`, `ci-dotnet`→`dotnet`, `ci-go`→`go`, `ci-rust`→`rust`,
`ci-java-maven`→`java`, `ci-php`→`php`, `docker-build-push`→`[]` (todos), `quality-python`→`python`,
`sec-audit-node`→`node`, `sec-audit-python`→`python`):

```ts
export interface StepRecipe {
  id: string;
  label: string;
  description: string;
  stack: StackId | "all";      // Plan 104 F0
  stepIds: readonly string[];
}
```

**Helpers nuevos** (en `pipelineStepSnippets.ts`):

```ts
export function filterSnippetsByStack(
  snippets: readonly StepSnippet[], stack: StackId | "all"
): readonly StepSnippet[] {
  if (stack === "all") return snippets;
  return snippets.filter((s) => s.stacks.length === 0 || s.stacks.includes(stack));
}

export const STACK_OPTIONS: readonly (StackId | "all")[] = [
  "all", "dotnet", "node", "python", "go", "rust", "java", "php", "generic",
];
```

**Tests PRIMERO** — EXTENDER los archivos de test existentes del 97:
- `Stacky Agents/frontend/src/devops/pipelinePresets.test.ts`: agregar
  `every_preset_has_stack_field` (los 4 presets tienen `stack ∈ STACK_OPTIONS`) y
  `stack_field_matches_id` (`python`→`"python"`, etc.).
- `Stacky Agents/frontend/src/devops/pipelineStepSnippets.test.ts`: agregar
  `every_snippet_has_stacks_array` (todos tienen `stacks` array, puede ser vacío),
  `filterSnippetsByStack_all_returns_everything` (`stack="all"` devuelve los 63),
  `filterSnippetsByStack_dotnet_excludes_python` (`stack="dotnet"` → ningún snippet con
  `script` que contenga `pip`/`pytest`),
  `filterSnippetsByStack_python_excludes_dotnet` (simétrico),
  `generic_snippets_have_empty_stacks` (los que aplican a todos tienen `stacks=[]`),
  `at_least_one_snippet_per_known_stack` (para cada `StackId ≠ "all"` hay ≥1 snippet),
  **[C5]** `isStackId_rejects_unknown` (`isStackId("kotlin") === false`, `isStackId("python")
  === true`, `isStackId(null) === false`, `isStackId(undefined) === false`).
- `Stacky Agents/frontend/src/devops/pipelineRecipes.test.ts`: agregar
  `every_recipe_has_stack_field` y `recipe_stack_matches_step_ids` (`ci-python`→`python`).

Comando: `npx vitest run src/devops/pipelinePresets.test.ts src/devops/pipelineStepSnippets.test.ts src/devops/pipelineRecipes.test.ts`

**Criterio BINARIO:** los 3 archivos de test pasan (con los nuevos casos) + `npx tsc --noEmit`
0 errores. `PIPELINE_PRESETS.length === 4`, `PIPELINE_STEP_SNIPPETS.length >= 60`,
`PIPELINE_RECIPES.length >= 10` (no se borró nada del 97).
**Flag:** ninguna (datos estáticos).
**Impacto por runtime:** NINGUNO (UI pura).
**Trabajo del operador:** ninguno.

---

### F1 — Selector de stack en el builder + filtrado de la galería

**Objetivo:** el operador elige un stack y la galería de presets, el `<select>` de snippets y el
`<select>` de recetas muestran SOLO los elementos relevantes.

**Archivo a EDITAR:** `Stacky Agents/frontend/src/components/devops/PipelineBuilderSection.tsx`

Agregar estado de filtro + `<select>` visible, y aplicar `filterSnippetsByStack` a los snapshots
usados por los `<optgroup>` y `PIPELINE_RECIPES`:

```tsx
import { STACK_OPTIONS, filterSnippetsByStack, type StackId } from '../../devops/pipelineStepSnippets';

const [stackFilter, setStackFilter] = useState<StackId | "all">("all");

// …en el JSX, antes de la galería de presets de F1 del 97:
<div style={{ marginBottom: '12px', display: 'flex', gap: '8px', alignItems: 'center' }}>
  <label className={styles.textMuted}>Stack:</label>
  <select
    value={stackFilter}
    onChange={(e) => setStackFilter(e.target.value as StackId | "all")}
    style={{ padding: '4px 8px' }}
  >
    {STACK_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
  </select>
</div>
```

Aplicar el filtro:
- **Presets:** `const visiblePresets = PIPELINE_PRESETS.filter((p) => stackFilter === "all" || p.stack === stackFilter);`
  y mapear `visiblePresets` en la galería (en vez de `PIPELINE_PRESETS`).
- **Snippets:** `const visibleSnippets = filterSnippetsByStack(PIPELINE_STEP_SNIPPETS, stackFilter);`
  y usar `visibleSnippets` (en vez de `PIPELINE_STEP_SNIPPETS`) tanto en el cálculo de
  `filteredSnippets` como en la construcción de los `<optgroup>` por categoría. Si el operador
  tecleó un filtro de texto, ambos se componen: `visibleSnippets.filter(texto…)`.
- **Recetas:** `const visibleRecipes = PIPELINE_RECIPES.filter((r) => stackFilter === "all" || r.stack === stackFilter || r.stack === "all");`

**Integración con detección del plan 97 (opcional, sin flag):** si el operador usa el botón
"Detectar stack" del plan 97 (F2) y este devuelve `detected: "dotnet"`, el frontend puede
auto-setear `setStackFilter("dotnet")`. **[C5]** IMPORTANTE: el detector del 97 devuelve
hoy `"python" | "node" | "dotnet" | null` (`pipeline_stack_detector.py:1036`) — los 3 son
`StackId` válidos, pero v2 exige un guard `isStackId(x)` antes de mutar el filtro (defensivo
ante futura evolución del 97). Implementación literal:

```tsx
// [C5] guard defensivo — si el 97 evoluciona y devuelve un stack nuevo no listado en
// STACK_OPTIONS, el filtro NO muta (degrada silencioso, sin romper). El operador puede
// seguir eligiendo manualmente.
function isStackId(x: unknown): x is StackId | "all" {
  return typeof x === "string" && (STACK_OPTIONS as readonly string[]).includes(x);
}
// en handleDetect (existe del 97):
if (isStackId(detected)) setStackFilter(detected);
```

Esto es una UX aditiva: el operador puede cambiar el filtro manualmente después. Si el 97
está OFF, no pasa nada (el filtro sigue manual). **No introduce dependencia dura con el 97 F2.**

**Casos borde:**
- `stackFilter === "all"` (default) → comportamiento idéntico al actual (no rompe nada).
- Si al filtrar un stack no hay recetas (ej. `generic` no tiene receta propia), el `<select>`
  muestra solo la opción vacía "— elegí una receta —" (no rompe).
- Si al filtrar no hay snippets en una categoría, el `<optgroup>` no se renderiza (ya manejado
  por el algoritmo del 97 F1-ter v4 C4: `.filter((g) => g.items.length > 0)`).

**Tests** — no hay test de React (sin `@testing-library/react`). Verificación:
- `npx tsc --noEmit` 0 errores.
- Grep: `grep -n "stackFilter\|visiblePresets\|visibleSnippets\|visibleRecipes" PipelineBuilderSection.tsx` → ≥4 ocurrencias.
- Grep negativo: el diff NO borra el import de `PIPELINE_PRESETS`/`PIPELINE_STEP_SNIPPETS`/`PIPELINE_RECIPES`.

**Criterio BINARIO:** `tsc` 0 err; los greps pasan; `stackFilter === "all"` reproduce el
comportamiento del 97 exacto (manual: elegir `all` y verificar que se ven los 63 snippets).
**Flag:** ninguna.
**Impacto por runtime:** NINGUNO.
**Trabajo del operador:** ninguno (default `all` = hoy).

---

### FEATURE B — Doctores IA por sección

### F2 — Backend: endpoint genérico "doctor de sección" (reusa `run_agent`)

**Objetivo:** un endpoint `POST /api/devops/sections/<id>/doctor` que arma un `context_blocks`
específico de la sección y despacha a `agent_runner.run_agent(agent_type="devops", runtime=...)`
— mismo cableado del plan 90. Devuelve `{execution_id, runtime}`. La respuesta de la IA se
consume por el canal EXISTENTE de logs/streams del `execution_id` (no se inventa canal nuevo).

**Archivo NUEVO:** `Stacky Agents/backend/api/devops_section_doctor.py`

```python
"""api/devops_section_doctor.py — Plan 104 F2 (v2).
Doctores IA por seccion del panel DevOps. Reusa el cableado de invocacion del
plan 90 (_launch_turn -> agent_runner.run_agent con agent_type="devops"). Cada
seccion define su propio context_blocks (YAML del pipeline, environment, etc.).
El doctor PROPONE analisis/mejoras en markdown; NUNCA aplica cambios (HITL).

v2 (C1 BLOQUEANTE): run_agent exige ticket_id: int OBLIGATORIO — el doctor crea
un Ticket ancla determinista (ado_id=-3) identico al patron del plan 90 (que usa
_CONVERSATION_ADO_ID). NO es fire-and-forget invisible.
"""
from __future__ import annotations
from flask import Blueprint, jsonify, request, abort
import config as _config  # [C11] módulo top-level, NO `services._config` (no existe)

bp = Blueprint("devops_section_doctor", __name__, url_prefix="/devops/sections")

# [C1] ado_id negativo DISTINTO al del plan 90 para distinguir doctor de chat en
# el historial. El plan 90 usa _CONVERSATION_ADO_ID (ver devops_agent.py); el
# doctor usa -3. Asi el historial del 90 puede filtrar "solo conversaciones
# reales" excluyendo doctores si hace falta.
_DOCTOR_CONVERSATION_ADO_ID = -3

# Registry declarativo: id_seccion -> (titulo, instruccion_base). El PAYLOAD lo
# arma el frontend (que tiene el estado de la seccion) y se valida aca.
SECTION_DOCTORS: dict[str, dict[str, str]] = {
    "pipeline": {
        "title": "Doctor de pipeline",
        "instruction": (
            "Sos un ingeniero DevOps senior. Analiza el siguiente pipeline (spec + YAML "
            "ADO + GitLab) y proponé mejoras concretas: steps faltantes, orden subóptimo, "
            "riesgos de seguridad, caché de dependencias, paralelismo, artifacts. "
            "Devolvé un informe en markdown con secciones 'Hallazgos' y 'Cambios sugeridos' "
            "(como diffs de los steps a cambiar). NO inventes pasos que no apliquen al stack. "
            "NO modifiques archivos: solo proponé."
        ),
    },
    "environments": {
        "title": "Doctor de environments",
        "instruction": (
            "Sos un ingeniero DevOps senior. Analizá la definición de los environments "
            "DevOps del proyecto y proponé mejoras: naming, secretos faltantes, "
            "promoción entre ambientes, drift, validaciones. Devolvé markdown con "
            "'Hallazgos' y 'Cambios sugeridos'. NO apliques cambios."
        ),
    },
    "publications": {
        "title": "Doctor de publicaciones",
        "instruction": (
            "Sos un ingeniero DevOps senior. Analizá la spec de publicación (qué se "
            "publica, a dónde, bajo qué conditions) y proponé mejoras: rollback, "
            "idempotencia, versionado, gates de calidad. Devolvé markdown con 'Hallazgos' "
            "y 'Cambios sugeridos'. NO apliques cambios."
        ),
    },
}


@bp.post("/<section_id>/doctor")
def section_doctor_route(section_id: str):
    """Invoca al doctor IA de la seccion. Flag STACKY_DEVOPS_SECTION_DOCTOR_ENABLED."""
    if not getattr(_config.config, "STACKY_DEVOPS_SECTION_DOCTOR_ENABLED", False):
        abort(404)
    if not getattr(_config.config, "STACKY_DEVOPS_AGENT_ENABLED", False):
        # Reusa el gate del plan 90 (sin agente DevOps no hay runtime IA).
        return jsonify({"error": "devops_agent_disabled"}), 404
    spec = SECTION_DOCTORS.get(section_id)
    if spec is None:
        return jsonify({"error": "unknown_section", "section": section_id}), 404

    body = request.get_json(silent=True) or {}
    project = body.get("project")
    runtime = body.get("runtime", "claude_code_cli")
    payload = body.get("payload")  # dict estructurado por seccion
    if not project or not isinstance(payload, dict):
        return jsonify({"error": "project y payload son obligatorios"}), 400
    # [C3] los 3 runtimes son VALIDOS (run_agent los despacha: agent_runner.py:94,219,373).
    # github_copilot NO se rechaza aqui — el guard del plan 90 que lo rechaza es para CHAT
    # CONVERSACIONAL (devops_chat_requires_cli_runtime), NO aplica al doctor.
    if runtime not in ("claude_code_cli", "codex_cli", "github_copilot"):
        return jsonify({"error": "runtime_no_soportado"}), 400

    import json
    # [C6] NO hardcodear kind — hereda el default del agent_runner/plan 90 (paridad).
    # [ADICION ARQUITECTO v2] el payload incluye opcionalmente yaml_ado/yaml_gitlab
    # renderizados (keys tipadas, null si la seccion no los tiene); el json los incluye
    # tal cual y la IA razona sobre el pipeline REAL.
    context_blocks = [{
        "id": f"doctor-{section_id}",
        "title": spec["title"],
        "content": (
            f"{spec['instruction']}\n\n"
            f"== CONTEXTO DE LA SECCION ({section_id}) ==\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        ),
        "source": {"type": "devops_panel", "section": section_id},
    }]

    # [C1 BLOQUEANTE resuelto] run_agent exige ticket_id: int. Patron EXACTO del plan 90:
    # crear un Ticket ancla ANTES de invocar (devops_agent.py:70-82). Usamos ado_id=-3 para
    # distinguir doctor de conversacion de chat (-2 del 90). Cada click del doctor crea un
    # Ticket nuevo (idempotente a nivel invocacion: dos clicks = dos conversaciones doctor).
    from db import session_scope
    from models import Ticket
    from api.devops_agent import _current_user  # [C2] reuso el helper canonico del 90
    import agent_runner

    try:
        with session_scope() as session:
            # [C10 BLOQUEANTE] patrón COMPLETO del plan 90 (devops_agent.py:70-82): setear
            # los mismos campos Y sellar external_id = -ticket.id. SIN ese sello, el 2º
            # doctor del MISMO proyecto deja external_id=NULL → el backfill de init_db
            # (db._backfill_multi_project_ticket_columns, db.py:158-196) lo rellena con
            # ado_id=-3 → colisión en el UNIQUE ux_tickets_stacky_tracker_external
            # (stacky_project_name, tracker_type, external_id). Negativo+único ⇒ nunca choca.
            ticket = Ticket(
                title=f"Doctor DevOps · {section_id} · {project}",
                ado_id=_DOCTOR_CONVERSATION_ADO_ID,
                project=project,
                stacky_project_name=project,
                work_item_type="Task",
                ado_state="Active",
            )
            session.add(ticket)
            session.flush()               # asigna ticket.id
            ticket.external_id = -ticket.id  # [C10] único, negativo, no-NULL ⇒ backfill lo respeta
            session.flush()
            doctor_ticket_id = ticket.id
            # session_scope commitea en __exit__ (db.py:306) ⇒ visible al preflight de run_agent.
    except Exception as exc:
        return jsonify({"ok": False, "error": "anchor_ticket_failed",
                        "message": str(exc)}), 502

    try:
        execution_id = agent_runner.run_agent(
            agent_type="devops",
            ticket_id=doctor_ticket_id,    # [C1] int OBLIGATORIO — NO None
            context_blocks=context_blocks,
            user=_current_user(),
            runtime=runtime,
            vscode_agent_filename="DevOpsAgent.agent.md",
            project_name=project,
            use_few_shot=False,
            use_anti_patterns=False,
            work_item_type="Task",
        )
    except agent_runner.UnknownAgentError:
        return jsonify({"ok": False, "error": "devops_agent_not_registered"}), 500
    except Exception as exc:  # patrón run_brief (api/agents.py:782-792)
        return jsonify({"ok": False, "error": "agent_launch_failed",
                        "message": str(exc)}), 502

    return jsonify({
        "ok": True,
        "execution_id": execution_id,
        "conversation_id": doctor_ticket_id,   # [C4] el frontend lo usa para linkear al panel del 90
        "runtime": runtime,
        "section": section_id,
    })
```

**NOTA para el implementador (verificado contra código real v3):**
- **[C11] `import config as _config`** (módulo top-level) — NO `from services import _config`
  (ese módulo no existe; usar el mismo import que `devops_agent.py:8`).
- **[C10] Sellar `external_id = -ticket.id`** tras el primer `flush()` es OBLIGATORIO
  (`devops_agent.py:80`): sin él, el 2º doctor del mismo proyecto colisiona en el UNIQUE
  `ux_tickets_stacky_tracker_external` tras el backfill de `init_db` (`db.py:158-196`).
- **[C1] `ticket_id` es `int` OBLIGATORIO** (`agent_runner.py:77-98`, `:108` preflight G0.1
  hace `Ticket.query.filter_by(id=ticket_id).first()` — None rompería ahí). v2 crea el
  Ticket ancla determinista antes de invocar (patrón plan 90 `devops_agent.py:70-82`).
- **[C2] `current_user`** se reusa vía `from api.devops_agent import _current_user` (NO
  duplicar la indirección del 90; paridad canónica con un único punto de cambio).
- **[C3] `github_copilot` SÍ es runtime válido** para `run_agent` (`agent_runner.py:94`
  default, `:219`/`:373` dispatch al `copilot_bridge`). El 400 controlado NO aplica al
  doctor (eso era solo para CHAT del plan 90, `devops_chat_requires_cli_runtime`). Los 3
  runtimes funcionan.
- **[C6] `kind` omitido** en `context_blocks`: hereda el default del agent_runner (paridad
  con el plan 90, que tampoco lo setea en `_launch_turn`).
- **[ADICIÓN ARQUITECTO v2] `payload.yaml_ado` / `payload.yaml_gitlab`** son keys tipadas y
  opcionales (null si la sección no las tiene); el backend las incluye en el JSON del
  contexto tal cual — la IA razona sobre el pipeline REAL renderizado, no solo el `spec`.

**Registro:** EDITAR `Stacky Agents/backend/api/__init__.py` — agregar:
```python
from .devops_section_doctor import bp as devops_section_doctor_bp  # Plan 104
# …dentro de register:
api_bp.register_blueprint(devops_section_doctor_bp)  # url_prefix="/devops/sections" -> /api/devops/sections
```

**Tests PRIMERO** — archivo NUEVO `Stacky Agents/backend/tests/test_plan104_section_doctor.py`:
- `test_flag_off_404`: `STACKY_DEVOPS_SECTION_DOCTOR_ENABLED=False` → POST 404.
- `test_agent_disabled_404`: flag doctor ON pero `STACKY_DEVOPS_AGENT_ENABLED=False` → 404.
- `test_unknown_section_404`: flag ON, section_id `"inventada"` → 404.
- `test_missing_project_400`: flag ON, section `"pipeline"`, body sin `project` → 400.
- `test_missing_payload_400`: idem sin `payload` → 400.
- `test_runtime_no_soportado_400`: runtime `"foo"` (inventado) → 400. (NO testear copilot:
  copilot es válido, ver C3.)
- `test_known_section_launches_agent`: mock `agent_runner.run_agent` → devuelve
  `{ok, execution_id, conversation_id, runtime, section}`. Verifica que `run_agent` se llamó
  con `agent_type="devops"` y `context_blocks[0].content` contiene el YAML enviado.
- `test_doctor_creates_anchor_ticket` **[C1 BLOQUEANTE, anti-verde-falso]**: el endpoint
  crea un `Ticket` con `ado_id == -3` ANTES de invocar `run_agent`, y pasa su `id` (NO None)
  como `ticket_id`. El test mockea la sesión y verifica: (a) se creó el Ticket con título
  `"Doctor DevOps · pipeline · <project>"` y `ado_id=-3`; (b) `run_agent` fue llamado con
  `ticket_id=<ese id entero>` (jamás None). Este test se pone ROJO si alguien vuelve al
  `ticket_id=None` de v1.
- `test_two_clicks_create_two_distinct_tickets` **[C9]**: dos POST consecutivos crean dos
  Tickets distintos (no comparten ancla) — cada click es una conversación doctor independiente.
- `test_second_doctor_ticket_same_project_no_collision` **[C10 BLOQUEANTE, ADICIÓN ARQUITECTO
  v3, anti-crash]**: crea DOS tickets doctor del MISMO proyecto, corre el backfill real
  (`db._backfill_multi_project_ticket_columns` / `init_db()`) y verifica: (a) ningún
  `IntegrityError` por el UNIQUE `ux_tickets_stacky_tracker_external`; (b) ambos tickets tienen
  `external_id` distintos y negativos (`-id1 ≠ -id2`). Este test se pone ROJO si alguien vuelve
  a omitir el sello `external_id = -ticket.id` de v2 — el bug exacto que el plan 90 documentó.
- `test_route_registered`: `"/api/devops/sections/<section_id>/doctor"` ∈ `app.url_map`.
- `test_payload_yaml_reaches_context_block` **[ADICIÓN ARQUITECTO v2]**: envía
  `payload={"yaml_ado": "...", "yaml_gitlab": "...", "spec": {...}}` y verifica que el
  `context_blocks[0].content` pasado a `run_agent` contiene los strings `yaml_ado` e
  `yaml_gitlab` y el JSON del spec (la IA ve el pipeline renderizado REAL, no solo el spec).
- `test_unknown_agent_500`: mock que levanta `UnknownAgentError` → 500 con
  `error: "devops_agent_not_registered"`.
- `test_launch_failure_502`: mock que levanta `Exception("boom")` (post-creación del Ticket)
  → 502 con `error: "agent_launch_failed"`.

Comando:
`"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan104_section_doctor.py" -q`

**Ratchet:** registrar `test_plan104_section_doctor.py` en `run_harness_tests.sh` **y**
`run_harness_tests.ps1`.

**Criterio BINARIO:** los 14 tests pasan (incluido `test_doctor_creates_anchor_ticket`
**[C1]** anti-verde-falso, `test_payload_yaml_reaches_context_block` **[ADICIÓN v2]** y
`test_second_doctor_ticket_same_project_no_collision` **[C10]** anti-crash);
ningún test del plan 90 (`test_plan90_*.py`) se rompe.
**Flag:** `STACKY_DEVOPS_SECTION_DOCTOR_ENABLED` (default OFF) — ver F4.
**Impacto por runtime:** los 3 (`claude_code_cli`, `codex_cli`, `github_copilot`) funcionan
— `run_agent` los despacha a todos (`agent_runner.py:94,219,373`). **[C3]** el doctor NO
hereda el rechazo de copilot del plan 90 (eso era para chat conversacional,
`devops_chat_requires_cli_runtime`; el doctor es `run_agent` puro, no chat).
**Trabajo del operador:** opt-in (activar flag por UI + elegir runtime en el botón).

---

### F3 — Frontend: API client + botón "Doctor" por sección + visor de respuesta

**Objetivo:** cada sección (Pipeline Builder, Environments, Publications) gana un botón
"Doctor" que arma el `payload` con el estado local de la sección, elige runtime, POST al
endpoint, y muestra la respuesta markdown del `execution_id` en un panel.

**Archivo a EDITAR:** `Stacky Agents/frontend/src/api/endpoints.ts`

Agregar al final (junto a `DevOpsAgentApi`):

```ts
/** Plan 104 — Doctores IA por sección del panel DevOps. */
export const SectionDoctorApi = {
  run: (sectionId: string, body: {
    project: string;
    runtime: "claude_code_cli" | "codex_cli" | "github_copilot";
    payload: Record<string, unknown>;
  }) =>
    api.post<{
      ok: boolean;
      execution_id: number;
      conversation_id: number;   // [C4] ticket ancla — para linkear al panel del 90
      runtime: string;
      section: string;
    }>(
      `/api/devops/sections/${encodeURIComponent(sectionId)}/doctor`,
      body,
    ),
};
```

**Archivo NUEVO:** `Stacky Agents/frontend/src/components/devops/SectionDoctorButton.tsx`

Componente reutilizable. Props: `sectionId`, `project`, `buildPayload: () => Record<string,unknown>`,
`runtime` (estado local con default `claude_code_cli`), `disabled?`. Estado: `busy`, `error`,
`executionId`, `markdownRespuesta`. El flujo:
1. Operador clickea "Doctor".
2. `const payload = buildPayload();` (cada sección arma el suyo).
3. `SectionDoctorApi.run(sectionId, {project, runtime, payload})` → `{execution_id}`.
4. La respuesta markdown se consume vía el canal EXISTENTE de logs del `execution_id` (mismo
   mecanismo que `DevOpsAgentSection` usa para mostrar la respuesta del agente — reusar el hook
   o endpoint de streaming de logs ya existente, ej. `useExecutionLogs(execution_id)` si existe;
   si no, un polling simple al endpoint de logs del execution). Mostrar en un `<pre>`/markdown
   renderer mínimo dentro de un `<details>` colapsable (no invasivo).
5. Errores → mensaje en llano (`error` del body o `error.message`).

```tsx
import { useState } from 'react';
import { SectionDoctorApi } from '../../api/endpoints';
import type { CliRuntime } from '../../api/endpoints';

type Runtime = "claude_code_cli" | "codex_cli" | "github_copilot";

export function SectionDoctorButton(props: {
  sectionId: "pipeline" | "environments" | "publications";
  project: string;
  buildPayload: () => Record<string, unknown>;
  disabled?: boolean;
  gateMessage?: string;  // si la flag está OFF, el padre pasa el mensaje y el botón se deshabilita
}) {
  const [runtime, setRuntime] = useState<Runtime>("claude_code_cli");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [executionId, setExecutionId] = useState<number | null>(null);

  const handle = async () => {
    if (props.gateMessage || busy) return;
    setBusy(true); setError(null); setExecutionId(null);
    try {
      const res = await SectionDoctorApi.run(props.sectionId, {
        project: props.project,
        runtime,
        payload: props.buildPayload(),
      });
      setExecutionId(res.execution_id);
    } catch (e: any) {
      setError(e?.body?.error || e?.message || "doctor_failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ marginTop: '8px' }}>
      <select value={runtime} onChange={(e) => setRuntime(e.target.value as Runtime)} disabled={busy}>
        <option value="claude_code_cli">Claude</option>
        <option value="codex_cli">Codex</option>
        <option value="github_copilot">Copilot</option>
      </select>
      <button onClick={handle} disabled={busy || !!props.gateMessage || props.disabled} className={styles.btnPrimary}>
        {busy ? "Analizando…" : "Doctor"}
      </button>
      {props.gateMessage && <p className={styles.textMuted}>{props.gateMessage}</p>}
      {error && <p className={styles.textMuted}>No pude lanzar el análisis ({error}).</p>}
      {executionId !== null && (
        <p className={styles.textMuted}>
          Análisis lanzado (execution #{executionId}). Mirá la respuesta en el panel del agente DevOps.
        </p>
      )}
    </div>
  );
}
```

**Decisión de UX (HITL + simplicidad):** la respuesta markdown de la IA se muestra en el panel
del **agente DevOps conversacional del plan 90** (que ya tiene el renderer de markdown y el
canal de logs), referenciado por `execution_id`. Esto evita duplicar un renderer markdown por
sección y reusa lo construido. Alternativa (si el implementador lo prefiere): un `<details>`
inline con un fetch de logs. Lo fijo: **referenciar `execution_id` + CTA "ver en el agente
DevOps"**, NO duplicar renderer (menor costo, paridad con plan 90).

**Archivos a EDITAR (3 secciones) — agregar `<SectionDoctorButton>` al pie de cada una:**

1. `Stacky Agents/frontend/src/components/devops/PipelineBuilderSection.tsx`:
   ```tsx
   import { SectionDoctorButton } from './SectionDoctorButton';
   // al pie del componente, después del árbol de bloques:
   <SectionDoctorButton
     sectionId="pipeline"
     project={activeProject ?? ""}
     buildPayload={() => ({
       spec,                                   // el PipelineSpecDraft actual
       yaml_ado: adoYamlPreview ?? null,       // si existe el preview del plan 99/88
       yaml_gitlab: gitlabYamlPreview ?? null,
     })}
     gateMessage={doctorFlagOff ? "El doctor de secciones está apagado (activá la flag en el panel Arnés)." : undefined}
   />
   ```
   `activeProject` ya existe (`PipelineBuilderSection.tsx:50-51`). `adoYamlPreview`/`gitlabYamlPreview`
   se obtienen del componente de preview YAML (`PipelineYamlPreview.tsx`) si está disponible; si no,
   se omite la key (el backend tolera `null`).

2. `Stacky Agents/frontend/src/components/devops/EnvironmentsSection.tsx`: mismo patrón,
   `sectionId="environments"`, `buildPayload={() => ({ environments: environmentsState })}`.

3. `Stacky Agents/frontend/src/components/devops/PublicationsSection.tsx`: idem,
   `sectionId="publications"`, `buildPayload={() => ({ publications: pubsState })}`.

**Tests** — sin test de React. Verificación:
- `npx tsc --noEmit` 0 errores.
- Grep: `grep -rn "SectionDoctorButton" frontend/src/components/devops/` → ≥4 ocurrencias (3 usos + 1 definición).
- Grep: `grep -n "SectionDoctorApi" frontend/src/api/endpoints.ts` → 1 ocurrencia.

**Criterio BINARIO:** `tsc` 0 err; los greps pasan; el botón aparece disabled con mensaje cuando
`doctorFlagOff` (manual: apagar la flag y verificar el `gateMessage`).
**Flag:** `STACKY_DEVOPS_SECTION_DOCTOR_ENABLED` (F4).
**Impacto por runtime:** **[C13]** el `<select>` ofrece los 3 y los 3 son válidos —
`run_agent` despacha claude_code_cli, codex_cli y github_copilot (`agent_runner.py:94,219,373`).
El backend solo rechaza (400) runtimes inventados (`"foo"`), NO copilot (ver C3).
**Trabajo del operador:** opt-in (flag ON + click).

---

### F4 — Flag `STACKY_DEVOPS_SECTION_DOCTOR_ENABLED` (6 patas) + health

**Objetivo:** dar de alta la flag Feature B en las 5+1 patas (requires
`STACKY_DEVOPS_AGENT_ENABLED` — sin agente no hay runtime IA) + exponerla en el health block.

**Archivos a EDITAR:**

1. `Stacky Agents/backend/config.py` (junto a `STACKY_DEVOPS_AGENT_ENABLED`):
   ```python
   # Plan 104 — Doctores IA por seccion del panel DevOps. Default OFF (opt-in).
   STACKY_DEVOPS_SECTION_DOCTOR_ENABLED: bool = os.getenv(
       "STACKY_DEVOPS_SECTION_DOCTOR_ENABLED", "false"
   ).lower() in ("1", "true", "yes")
   ```

2. `Stacky Agents/backend/services/harness_flags.py`:
   - `_CATEGORY_KEYS["devops"]`: agregar `"STACKY_DEVOPS_SECTION_DOCTOR_ENABLED"`.
   - `FlagSpec` completo (key, type="bool", label, description, group, requires=["STACKY_DEVOPS_AGENT_ENABLED"]).
   - **NO agregar `default=`** (gotcha plan 63 / memoria `harness-flags-default-explicit-gotcha.md`).

3. `Stacky Agents/backend/services/harness_flags_help.py`: entrada `PlainHelp` (plan 86).

4. `Stacky Agents/backend/harness_defaults.env`: `STACKY_DEVOPS_SECTION_DOCTOR_ENABLED=false`.

5. `Stacky Agents/backend/tests/test_harness_flags_requires.py` (`_REQUIRES_MAP_FROZEN`):
   agregar arista `"STACKY_DEVOPS_SECTION_DOCTOR_ENABLED" -> "STACKY_DEVOPS_AGENT_ENABLED"`
   (junto a las de 88-91/97). **R4 profundidad 1** — verificar que no se forme cadena.

6. `Stacky Agents/backend/api/devops.py` (health block, ~línea 26-40): agregar
   `"section_doctor_enabled": bool(getattr(cfg, "STACKY_DEVOPS_SECTION_DOCTOR_ENABLED", False)),  # Plan 104`.

7. `Stacky Agents/frontend/src/pages/DevOpsPage.tsx` (`DevOpsHealth` index signature):
   agregar `section_doctor_enabled?: boolean; // Plan 104` (aditivo, igual que plan 96 C14).

**Tests:**
- EXTENDER `tests/test_plan104_section_doctor.py` con `test_flag_off_404` (ya en F2).
- CORRER `tests/test_harness_flags_requires.py` (debe quedar verde con la nueva arista).
- CORRER `tests/test_harness_flags.py` (flag aparece en categoría devops, sin default explícito).

Comando: `"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest tests/test_harness_flags_requires.py tests/test_harness_flags.py tests/test_plan104_section_doctor.py -q`

**Ratchet:** ya registrados.

**Criterio BINARIO:** la flag aparece en la UI Arnés con su ayuda llana; `requires` válido;
health expone `section_doctor_enabled`; meta-tests R4 verdes.
**Impacto por runtime:** NINGUNO.
**Trabajo del operador:** opt-in (encender por UI).

---

### F5 — Health wiring: `section_doctor_enabled` llega a las secciones

**Objetivo:** que cada sección conozca su gate (flag ON/OFF) para mostrar el `gateMessage`.

**Archivo a EDITAR:** `Stacky Agents/frontend/src/pages/DevOpsPage.tsx` y los 3 contenedores
que ya pasan `ctx` a las secciones (patrón plan 96 C7). El `ctx.health` ya incluye
`section_doctor_enabled` tras F4. En cada sección, derivar:
```ts
const doctorFlagOff = ctx?.health?.section_doctor_enabled === false;
```
y pasarlo como `gateMessage` al `<SectionDoctorButton>`.

**Criterio BINARIO:** `tsc` 0 err; grep `section_doctor_enabled` en `DevOpsPage.tsx` y en los 3
componentes de sección. Manual: apagar la flag → los 3 botones Doctor muestran `gateMessage`.
**Flag:** —
**Impacto por runtime:** NINGUNO.
**Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| Riesgo | Severidad | Mitigación |
|---|---|---|
| **[C10]** 2º doctor del mismo proyecto colisiona en el UNIQUE tras el backfill de `init_db` | ALTO | F2 sella `external_id = -ticket.id` (patrón COMPLETO del plan 90, `devops_agent.py:80`); test `test_second_doctor_ticket_same_project_no_collision` lo blinda |
| **[C1]** `run_agent` exige `ticket_id: int` (no acepta None) | RESUELTO | F2 crea un `Ticket` ancla (`ado_id=-3`) y pasa su `id`; test `test_doctor_creates_anchor_ticket` (anti-verde-falso) |
| Clasificación de snippets por stack ambigua (alguno aplica a varios) | BAJA | Campo `stacks` es array; los genéricos van a `[]` = todos; la tabla de F0 es determinista |
| El doctor podría tentarse a "aplicar" cambios | ALTO (HITL) | Instrucción explícita "NO apliques cambios" en cada SECTION_DOCTORS; el flujo NUNCA escribe archivos (solo `run_agent` con `agent_type="devops"` que no tiene tool de escritura por defecto en este contexto) |
| Costo de tokens por invocar IA en cada click | MEDIO | Opt-in (flag + click); el operador decide; no hay auto-invocación |
| **[C3]** Paridad 3 runtimes | BAJO | Los 3 (`claude_code_cli`, `codex_cli`, `github_copilot`) los despacha `run_agent` (`agent_runner.py:94,219,373`); el 400 es SOLO para runtimes inventados |
| Snippets nuevos del 97 futuros sin `stacks` | BAJA | Test `every_snippet_has_stacks_array` los obliga |

## 6. Fuera de scope

- Doctores para `CommitPipelineModal` y `TriggerPipelineSection` (diferible a v1.1; la
  arquitectura F2/F3 lo permite agregando entradas a `SECTION_DOCTORS`).
- Auto-aplicar las mejoras propuestas por el doctor (HITL innegociable — nunca).
- Streaming markdown inline del execution (se referencia el panel del agente DevOps del 90).
- Filtro por stack en `TriggerPipelineSection` (no tiene galería de presets).
- Conectar el doctor con la "memoria que empuja" (planes 48-54) — diferible.

## 7. Glosario + Orden de implementación + DoD

**Glosario:**
- **Preset/Snippet/Receta** (plan 97): preset = pipeline completo; snippet = acción individual;
  receta = bundle ordenado de snippets.
- **Doctor de sección** (este plan): botón que invoca IA con el contexto estructurado de UNA
  sección para que proponga mejoras en markdown. NO es el "doctor de diagnóstico post-fallo" del
  plan 96 (que clasifica fallos por regex, sin IA).
- **HITL**: Human-in-the-loop. El doctor propone, el operador decide.
- **`run_agent`**: dispatcher de runtimes IA (`agent_runner.py`), ya usado por el plan 90.
- **Runtime**: Claude Code CLI / Codex CLI / GitHub Copilot Pro.

**Orden de implementación:**
1. F0 (clasificación por stack — frontend puro, sin flag).
2. F1 (selector + filtrado en el builder).
3. F4 (flag `STACKY_DEVOPS_SECTION_DOCTOR_ENABLED` 6 patas + health).
4. F2 (endpoint doctor backend).
5. F5 (health wiring a secciones).
6. F3 (botones Doctor en las 3 secciones).

**Definición de Hecho (DoD):**
- Feature A: `stackFilter` funciona, default `all` = comportamiento 97; todos los tests del 97
  siguen verdes + los nuevos casos de F0; `tsc` 0 err.
- Feature B: las 3 secciones (Pipeline/Environments/Publications) tienen botón Doctor; el doctor
  lanza `run_agent` con `agent_type="devops"` y el `payload` correcto; flag OFF → botones
  deshabilitados con `gateMessage`; flag ON → flujo completo; **14** tests backend verdes; `tsc` 0 err.
- **[C13]** Paridad 3 runtimes: los 3 (claude_code_cli, codex_cli, github_copilot) los despacha
  `run_agent`; el único 400 es para runtimes inventados (no para copilot).
- Cero trabajo extra al operador (todo opt-in). HITL intacto (nunca aplica cambios).
- Ratchet actualizado (`.sh` y `.ps1`). Health expone `section_doctor_enabled`.
