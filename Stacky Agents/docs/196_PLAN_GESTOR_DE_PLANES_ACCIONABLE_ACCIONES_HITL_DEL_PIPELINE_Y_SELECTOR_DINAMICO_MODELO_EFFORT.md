# Plan 196 — Gestor de Planes accionable: acciones HITL del pipeline (proponer / criticar / implementar / supervisar) con selector dinámico de modelo+effort

**Estado:** PROPUESTO — v1 (2026-07-18) · **Autor:** StackyArchitectaUltraEficientCode (pipeline proponer-plan-stacky) · pendiente de `criticar-y-mejorar-plan`

- **Versión:** v1 (PROPUESTO)
- **Fecha:** 2026-07-18
- **Base:** EXTIENDE el Tablero de Planes (Plan 128, IMPLEMENTADO y VIVO en `/planes`) — PROHIBIDO crear un tablero nuevo.
- **Consume:** el contrato del Plan 159 (catálogo unificado modelos/efforts, CRITICADO v2 sin implementar) — relación exacta en §2.3 y fase F1.
- **Ortogonal a:** Plan 167 (Centro de Evolución / RSI) — deslinde exacto en §2.4.
- **Nota de numeración:** este doc nació como "194"; una sesión paralela tomó el 194 mientras se redactaba y luego TAMBIÉN el 195 en la ventana entre el `ls` en frío y el `Write` (doble colisión en la misma corrida — el hazard de numeración es real y continuo). Número final: 196, verificado libre inmediatamente después del rename.

> Este documento está redactado para que un **MODELO MENOR** (Haiku, Codex CLI o GitHub
> Copilot Pro) lo implemente **SIN inferir nada**. Los nombres de símbolos, rutas, shapes
> JSON, literales de mensajes y comandos son **LITERALES**: prohibido desviarse de los
> nombres exactos, prohibido "mejorar" el alcance. Todo lo ambiguo ya fue decidido acá.
> Cada afirmación sobre código existente está anclada a `archivo:línea` **verificada el
> 2026-07-18**; este repo tiene sesiones paralelas que commitean todo el tiempo, así que
> TODA edición se ancla por el CONTENIDO/símbolo citado, nunca solo por el número de
> línea. Los comandos con `&&` se ejecutan en **Git Bash** (en PowerShell 5.1 `&&` es
> error de parser).

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** Stacky ya VISUALIZA su propio pipeline de auto-mejora — el
Tablero de Planes (Plan 128) parsea `Stacky Agents/docs/<NN>_PLAN_*.md`, deriva el estado
determinista (PROPUESTO / CRITICADO+veredicto / IMPLEMENTADO / IMPLEMENTADO_PARCIAL /
APROBADO-por-ledger / SIN_ESTADO), mergea el ledger de supervisión y hasta SUGIERE el
siguiente comando (`suggest_next_action`, `services/plans_board.py:180-252`) — pero la
sugerencia es **solo texto copiable**: el operador tiene que salir de la app, abrir una
terminal con Claude Code y pegar el comando a mano. Este plan cierra ese último tramo:
cada card del tablero gana **botones HITL** (Proponer / Criticar / Implementar /
Supervisar, siempre click del operador, nunca autónomos) que lanzan la corrida por la
**infraestructura de ejecución existente** (`agent_runner.run_agent` + runtime
`claude_code_cli` one-shot, espejo EXACTO del Resolutor de Incidencias,
`api/agents.py:877-1075`), con **selector dinámico de modelo Claude + effort** servido
por el catálogo del Plan 159 (cero listas hardcodeadas, recarga por mtime sin redeploy),
**serialización dura** (una sola corrida de pipeline a la vez: las skills commitean sobre
el working tree compartido), **historial de corridas** del pipeline en el propio tablero
y **commits asociados por plan** on-demand (un `git log` read-only barato). El push sigue
siendo SIEMPRE manual del operador; nada se lanza solo.

**KPIs binarios (verificados por tests):**

| KPI | Métrica | Criterio binario |
|-----|---------|------------------|
| KPI-1 | Acción gobernada por estado | `POST /api/plans-board/actions/run` con `action="criticar"` sobre un plan IMPLEMENTADO responde 409 `action_not_allowed_for_estado`; la tabla §4.3 es la única fuente (test backend) |
| KPI-2 | Selector 100% dinámico | 0 ocurrencias de `CLAUDE_MODELS`, `CLAUDE_EFFORTS`, `ALT_MODELS` o literales `claude-...-x` hardcodeados en los archivos NUEVOS del frontend de este plan; los modelos/efforts salen de `GET /api/agents/model-catalog` (159), que se recarga por mtime sin restart (test del loader 159 F0 caso 5) |
| KPI-3 | Serialización | Un segundo POST de acción con una corrida `plans_pipeline` en `status="running"` responde 409 `pipeline_action_already_running` con el `execution_id` vivo (test backend) |
| KPI-4 | Paridad/degradación por runtime | Visualización idéntica en los 3 runtimes (backend puro); `POST .../actions/run` con `runtime` ≠ `claude_code_cli` responde 409 `runtime_not_supported` con `supported: ["claude_code_cli"]` (test backend) |
| KPI-5 | Cero regresión y cero pollers | Con `STACKY_PLANS_PIPELINE_ACTIONS_ENABLED=false` los endpoints nuevos de acción devuelven 404 y la UI no muestra botones; `Select-String -Path "Stacky Agents\frontend\src\pages\PlansBoardPage.tsx" -Pattern "setInterval"` → 0 líneas; `npx tsc --noEmit` exit 0 |

**Ganancia robusta:** el ciclo "ver estado → decidir → lanzar corrida" pasa de
app+terminal+paste manual a 2 clicks dentro de Stacky, con modelo y effort elegidos por
corrida y trazabilidad (execution + telemetría de costos del Plan 142 ya la capturan
gratis, porque la corrida entra por `run_agent` como cualquier otra).

---

## 2. Por qué ahora / gap que cierra

### 2.1 Evidencia del sustrato existente (verificada, archivo:línea)

- `Stacky Agents/backend/services/plans_board.py` — Plan 128 IMPLEMENTADO: parser
  determinista y tolerante (`normalize_estado` :35-48 → `PROPUESTO | CRITICADO |
  IMPLEMENTADO | IMPLEMENTADO_PARCIAL | SIN_ESTADO`; docs viejos sin encabezado → 
  `SIN_ESTADO`, nunca crashea), `parse_plan_header` :51-79 (veredicto por regex
  `APROBADO-CON-CAMBIOS|RECHAZADO|APROBADO` :25, versión, fecha), `next_free_number`
  :118-131, ledger de supervisión :134-177 (`_supervision/ledger.json`, `doc_sha256` →
  `doc_drift`), `estado_efectivo == "APROBADO"` cuando el ledger aprueba sin drift :277,
  `suggest_next_action` :180-252 con los comandos LITERALES del pipeline
  (`/criticar-y-mejorar-plan <NN>` :218, `/implementar-plan-stacky <NN>` :228,
  `/supervisar-implementaciones-planes <NN>` :238), cache TTL 15 s `get_board_cached`
  :374-392, `repo_root()` :323-328 (None si no hay `.git` — deploy congelado),
  `docs_dir_default()` :331-333, `get_detail` :395-415. **El requerimiento de
  "derivación de estado determinista, tolerante y barata" YA ESTÁ RESUELTO acá: este
  plan NO reimplementa ningún parser.**
- `Stacky Agents/backend/api/plans_board.py` — blueprint `plans_board`,
  `url_prefix="/plans-board"` :12, `from config import config` :10 (instancia directa),
  gate `_enabled()` :15-16 sobre `STACKY_PLANS_BOARD_ENABLED`, rutas `GET /health` :32
  (siempre 200 + `next_free_number`), `GET /list` :43, `GET /detail/<int:number>` :53.
  Registrado en `api/__init__.py:59` (import) y `:120` (register).
- `Stacky Agents/backend/config.py:1331-1333` — `STACKY_PLANS_BOARD_ENABLED` con default
  **"false"** (el tablero existe pero nace apagado; §F0 lo promueve a ON por la
  directiva vigente de flags).
- `Stacky Agents/frontend/src/pages/PlansBoardPage.tsx` — página del tablero (tab
  `/planes`, gate en `App.tsx:101` + probe `App.tsx:146` a `/api/plans-board/health`),
  react-query (`queryKey ["plans-board-list"]` :74, `["plans-board-detail", n]` :80),
  helpers puros en `src/plansBoard/model.ts` (`ESTADO_CHIP`, `buildCopyPayload`,
  `filterPlans`, importados en :12-21), estilos en `PlansBoardPage.module.css` (:22).
  Cliente API `PlansBoard` en `src/api/endpoints.ts:4114-4120`.
- **Patrón de lanzamiento one-shot a espejar** — `api/agents.py:877-1075`
  (`POST /run-incident`, Plan 131): payload con `model`/`effort`/`runtime`/`project`,
  clamp `_llm_router.clamp_model(model, allow_opus=True)` :946 +
  `_clamp_effort_for_model` :948-949 (definida en `api/agents.py:588`), pool ticket con
  `ado_id` sentinel negativo creado on-demand :966-984 (comentario :962-964 enumera los
  sentinels ocupados: -1 brief, -2 devops, -3 doctor secciones, -4 consola remota,
  -5 análisis LLM local, -6 PR review, -7 documenter, -8 incidentes → **-9 está libre**,
  verificado por grep `ado_id=-9` = 0 hits el 2026-07-18), lanzamiento
  `agent_runner.run_agent(...)` :1021-1033, mapeo de errores 502 `agent_launch_failed`
  :1036-1046, respuesta `{"execution_id", "status": "running"}, 202` :1075, persistencia
  de traza en `metadata_dict` :1062-1073.
- `Stacky Agents/backend/agent_runner.py:77-98` — firma de `run_agent` (keyword-only:
  `agent_type`, `ticket_id`, `context_blocks`, `user`, `model_override`,
  `effort_override`, `runtime`, `vscode_agent_filename`, `project_name`, ...). El
  registro de agentes vive en `backend/agents/__init__.py:14-30` (`registry` dict; p.ej.
  `IncidentAgent()` :26 con `type = "incident"` en `agents/incident.py:8`).
- `Stacky Agents/backend/agent_runner.py:301-335` — rama `claude_code_cli`:
  `workspace_root` sale de `resolve_project_context(...)` :308-310 y se pasa a
  `start_claude_code_cli_run(..., workspace_root=workspace_root)` :335. El runner
  resuelve cwd en `services/claude_code_cli_runner.py:2735-2765` (`_resolve_cwd`:
  workspace_root inexistente → ValueError; vacío → fallback al dir de Stacky). **Para
  las corridas del pipeline el cwd DEBE ser la raíz del repo de Stacky** (ahí viven
  `.claude/skills/*`): F2 agrega el override explícito mínimo.
- `Stacky Agents/backend/services/claude_code_cli_runner.py:218` —
  `_ONE_SHOT_ADO_IDS = frozenset({-1, -7, -8})`: todo pool one-shot NUEVO debe entrar acá
  o la corrida queda colgada como sesión conversacional (timeout 1800 s — gotcha
  registrado).
- `Stacky Agents/backend/services/incident_context.py:116-139` —
  `ensure_incident_agent_file()`: patrón exacto para garantizar el `.agent.md` del
  agente en `stacky_agents_dir()` (backend/Stacky/agents, que es lo que lee el runtime).
- `Stacky Agents/backend/models.py:207-232` — `AgentExecution` con `agent_type` :212
  (String(20)), `status` :213, `metadata_json` :219 (+ propiedad `metadata_dict`, usada
  en `api/agents.py:867`), `started_at` :223, `completed_at` :224.
- **Pipeline de skills (fuente de las acciones):** `.claude/skills/proponer-plan-stacky/SKILL.md`
  (numeración auto-calculada, commit del doc SIN push — pasos 1 y 5),
  `.claude/skills/criticar-y-mejorar-plan/SKILL.md`, `.claude/skills/implementar-plan-stacky/SKILL.md`,
  `.claude/skills/supervisar-implementaciones-planes/SKILL.md`. Son artefactos de
  **Claude Code** en la raíz del repo: no existen para Codex CLI ni Copilot (motivo de
  la degradación §3.2).

### 2.2 El gap

El tablero 128 es un espejo pasivo. Las 4 transiciones del pipeline
(proponer→criticar→implementar→supervisar) exigen que el operador copie un comando,
cambie de herramienta y lo pegue — con el riesgo de tipear mal el número o correrlo con
el modelo equivocado. Además NO hay forma de elegir modelo/effort para esas corridas
(el operador hoy corre las skills con lo que tenga configurado su sesión interactiva), ni
historial de qué corrida del pipeline se lanzó cuándo y con qué. Todo el plumbing para
resolverlo YA existe (§2.1); falta solo el cableado.

### 2.3 Relación con el Plan 159 (catálogo dinámico de modelos/efforts) — CONTRATO

El requerimiento 3 del operador ("elegir cualquier modelo de Claude disponible EN ESE
MOMENTO con todos sus efforts, DINÁMICO, cero hardcodeo") es EXACTAMENTE el objetivo del
Plan 159 (CRITICADO v2, apto para implementar, aún sin implementar). Decisión congelada:

- **Este plan CONSUME el contrato del 159 tal cual está escrito; NO lo reinventa ni lo
  contradice.** La fase F1 de este plan consiste en ejecutar las fases **F0, F1, F2 y F3
  del doc `159_PLAN_CATALOGO_UNIFICADO_MODELOS_EFFORTS_DINAMICO.md` LITERALMENTE** (sus
  archivos, símbolos, tests y comandos son los de ese doc, sin cambiar una letra):
  `backend/config/model_catalog.json` + `services/model_catalog.py` (F0 del 159),
  `GET /api/agents/model-catalog` (F1 del 159), flag `STACKY_MODEL_CATALOG_ENABLED`
  (F2 del 159), y el lado frontend `endpoints.ts` (`ModelCatalogApi`) +
  `services/modelCatalogFallback.ts` + `hooks/useModelCatalog.ts` (F3 del 159).
- **Idempotencia:** si al implementar este plan `Stacky Agents/backend/services/model_catalog.py`
  YA existe (una corrida de `implementar-plan-stacky 159` lo construyó antes), la fase F1
  se reduce a VERIFICAR: correr los comandos de aceptación de F0-F3 del doc 159 y seguir.
  Si no existe, se implementa desde el doc 159. En ambos casos el resultado es idéntico
  porque los literales provienen del MISMO doc.
- Las fases F4-F6 del 159 (migración de `IncidentResolverModal` / `EpicFromBriefModal` /
  `ModelDecisionChip`) NO son alcance de este plan: siguen siendo del 159.
- **Honestidad del "dinámico":** no existe introspección real del binario `claude`
  (159 §2, verificado). El mecanismo dinámico honesto del repo es el catálogo JSON en
  disco con caché invalidada por mtime/TTL 300 s: editar el JSON agrega/quita
  modelos/efforts SIN redeploy ni restart, y cada apertura del tablero consulta el
  endpoint y ve el estado vigente. Eso satisface "en cada momento que lo abra".

### 2.4 Deslinde con el Plan 167 (Centro de Evolución / RSI)

- **196 (este) = gestor ACCIONABLE del pipeline de PLANES** (`docs/<NN>_PLAN_*.md`,
  estados del 128, corridas de las 4 skills). Vive en el tab existente `/planes`.
- **167 = registro y gobernanza de PROPUESTAS DE MEJORA de otros artefactos** (prompts
  de agentes, flags, lecciones de conocimiento) con ciclo MAPE y su propio tab
  `/evolution` (aún sin implementar).
- No comparten superficie de UI ni endpoints ni stores. El aspecto seed
  `stacky_codebase` del 167 ENLAZA (link_only) al tablero `/planes` — este plan no
  cambia ese contrato y no toca NADA de `/api/evolution/*`. Si ambos terminan
  implementados, la navegación queda: `/planes` (pipeline de planes, con acciones de
  este plan) y `/evolution` (loops RSI), enlazados por el link seed del 167.

---

## 3. Principios y guardarraíles (NO negociables)

1. **Human-in-the-loop innegociable:** TODAS las acciones son click del operador con
   confirmación (`ConfirmButton`, `frontend/src/components/ConfirmButton.tsx:23`).
   No hay daemon, cron, retry automático ni disparo por condición. Ninguna corrida se
   lanza sola. El push a remoto queda SIEMPRE manual (las skills ya commitean sin push;
   el prompt y el `.agent.md` lo refuerzan por escrito).
2. **3 runtimes con paridad y degradación EXPLÍCITA (decisión congelada):**
   - **Visualización (tablero, historial, commits): 100% paritaria** en Codex CLI,
     Claude Code CLI y GitHub Copilot Pro — es backend Flask + React puro, sin LLM.
   - **Acciones del pipeline: SOLO `runtime="claude_code_cli"`.** Las 4 skills son
     artefactos de Claude Code (`.claude/skills/`); duplicarlas como prompts embebidos
     para codex/copilot crearía una segunda fuente de verdad del pipeline destinada a
     divergir (la clase de bug que el 159 mata para modelos). Degradación elegida:
     el backend responde 409 `runtime_not_supported` con
     `supported: ["claude_code_cli"]`, y la UI NO muestra selector de runtime — muestra
     el texto fijo `Runtime: Claude Code CLI` con el title/tooltip literal:
     `"Las acciones del pipeline usan las skills de Claude Code del repo; Codex y Copilot no las tienen. La visualización del tablero sí es idéntica en los 3 runtimes."`
   - El selector de modelos, por paridad de contrato, viene del catálogo POR RUNTIME del
     159; como las acciones son claude-only, la UI consume
     `runtimes.claude_code_cli` (modelos Claude + efforts), que es literalmente lo que
     pide el requerimiento.
3. **Cero trabajo extra para el operador:** flags default **ON** (F0); el tablero y los
   botones aparecen solos. Ninguna de las 4 excepciones duras aplica: (1) no hay bypass
   de revisión humana (cada corrida exige click + confirmación, y el artefacto queda en
   commits locales revisables ANTES del push manual); (2) nada destructivo/irreversible
   (commits git locales; prohibido push/stash/reset en el prompt y en el `.agent.md`);
   (3) el prerequisito (repo git + skills + CLI `claude`) NO se le pide al operador:
   cuando falta (deploy congelado sin `.git`), la feature degrada SOLA a botones
   deshabilitados con motivo visible y el backend responde 409 `repo_not_available` —
   sin config nueva; (4) no reduce seguridad (superficie local, mono-operador).
4. **Mono-operador sin auth real:** cero RBAC. `started_by` es descriptivo.
5. **No degradar:** el módulo del Plan 128 (`services/plans_board.py`) se toca **CERO**
   (solo se importa); `api/plans_board.py` recibe rutas ADITIVAS; cero pollers nuevos
   (sin `setInterval`; carga on-mount + botón Refrescar + refresh post-acción — espíritu
   del Plan 156); con flags OFF, byte-idéntico a hoy.
6. **Reusar, no reinventar:** parser/estados/ledger del 128; lanzamiento del 131
   (`run_incident`); clamps de modelo/effort del 43/53; catálogo del 159; telemetría de
   costos del 142 (gratis vía `run_agent`); primitivas UI existentes (`ConfirmButton`
   136, module.css del propio tablero); patrón `ensure_*_agent_file` del 131.
7. **Serialización dura del working tree:** a lo sumo UNA corrida `plans_pipeline` en
   `status="running"` a la vez (lock + chequeo en DB, §4.5). Motivo: las skills
   commitean sobre el working tree compartido del repo; dos corridas concurrentes se
   pisan. (Las sesiones paralelas HUMANAS quedan fuera del alcance del lock — riesgo
   residual documentado en §6.)

### Gotchas del repo que el implementador DEBE respetar (verificadas)

- **G1 — `config` vs `config.config`:** en `api/plans_board.py:10` ya se importa la
  INSTANCIA (`from config import config`); el código nuevo de ese archivo sigue igual.
  En archivos nuevos usar SIEMPRE `from config import config as _cfg` y
  `getattr(_cfg, "FLAG", default)`. NUNCA `getattr(<módulo config>, FLAG)` (devuelve el
  default y mata el branch OFF — gotcha registrado en `api/tickets.py`).
- **G2 — Ratchet de tests:** los 2 `test_plan196_*.py` nuevos (más los 3
  `test_plan159_*.py` si F1 los crea) DEBEN agregarse a `HARNESS_TEST_FILES` en AMBOS
  `backend/scripts/run_harness_tests.sh` (arreglo abre en `:20`) y
  `backend/scripts/run_harness_tests.ps1` (`:412`), o el meta-test del Plan 49 rompe.
- **G3 — Aristas `requires=`:** la flag nueva con `requires=` lleva su arista en
  `_REQUIRES_MAP_FROZEN` (`backend/tests/test_harness_flags_requires.py:120`).
  Profundidad 1: apunta al ROOT (`STACKY_PLANS_BOARD_ENABLED`), nunca en cadena.
- **G4 — `_CURATED_DEFAULTS_ON`:** toda flag **bool** con `default=True` va al set de
  `backend/tests/test_harness_flags.py:467`. Las dos flags bool de F0 entran ahí.
- **G5 — venv y tests por archivo:** backend desde `Stacky Agents/backend` con
  `.venv\Scripts\python.exe -m pytest tests/<archivo> -q`. ANTES de empezar, verificar
  el intérprete: `.venv\Scripts\python.exe --version` debe reportar **3.13.x** (hay un
  `venv/` py3.11 ajeno contaminado en el repo — NO usarlo). NUNCA la suite completa
  (contaminación cross-run conocida; `test_harness_flags.py` hace
  `importlib.reload(config)` y rompe tests flag-off de la misma corrida). Frontend:
  `npx vitest run src/<archivo>` por archivo, desde `Stacky Agents/frontend`.
- **G6 — Ratchet UI cero inline-style:** los `.tsx` tocados/nuevos tienen alcance 0 en
  `uiDebtRatchet`: TODO estilo va a `PlansBoardPage.module.css`; prohibido `style={{}}`.
- **G7 — `_CATEGORY_KEYS`:** toda flag nueva va también al dict `_CATEGORY_KEYS`
  (`services/harness_flags.py:117`) o `test_every_registry_flag_is_categorized` rompe.
  Ancla de inserción: la tupla que contiene el literal `"STACKY_PLANS_BOARD_ENABLED"`
  (`services/harness_flags.py:265`).
- **G8 — Meta-test rojo preexistente (criterio NO-EMPEORAR):** el juez del Plan 192
  verificó EN VIVO que `test_harness_ratchet_meta.py` está rojo preexistente. Criterio:
  el meta-test NO debe fallar POR archivos de este plan (si ya estaba rojo, su mensaje
  de fallo no debe mencionar `plan196` ni `plan159`).
- **G9 — Sin pollers:** prohibido `setInterval`/`refetchInterval` en el código nuevo
  (KPI-5). Refresh manual + invalidación de queries tras cada acción.
- **G10 — Tests frontend sin DOM:** NO hay `@testing-library/react` ni `jsdom`
  utilizables. Los tests vitest van SOLO sobre helpers puros (`src/plansBoard/actions.ts`).
  El gate de los componentes es `npx tsc --noEmit` + smoke manual documentado.
- **G11 — Sentinel one-shot:** el pool nuevo usa `ado_id=-9` (verificado libre por grep
  el 2026-07-18). Antes de escribir código, RE-VERIFICAR:
  `grep -rn "ado_id=-9" "Stacky Agents/backend"` → si diera hits (otra sesión lo tomó),
  usar `-10` y propagar ese número EXACTO a los 4 puntos que lo usan (§4.5, F2, F3 y sus
  tests). El sentinel elegido DEBE agregarse a `_ONE_SHOT_ADO_IDS`
  (`services/claude_code_cli_runner.py:218`) y al comentario-inventario de
  `api/agents.py:962-964`, o la corrida cuelga 1800 s.
- **G12 — WIP ajeno / sesiones paralelas:** antes de editar cada archivo caliente
  (`config.py`, `harness_flags.py`, `agent_runner.py`, `api/plans_board.py`,
  `endpoints.ts`, scripts de ratchet): `git status -- "<ruta>"`; staging quirúrgico por
  pathspec; PROHIBIDO `git stash/reset/checkout`. El implementador NO pushea.
- **G13 — Prosa vs gates:** ninguna cadena de comentario/docstring nueva debe matchear
  espuriamente los greps de criterio de este plan (gotcha recurrido 6×).
- **G14 — `harness_defaults.env` NO se edita a mano:** lo regenera
  `scripts/export_harness_defaults.py` tras cambiar defaults de flags (F0).

---

## 4. Contratos congelados (van tal cual al código)

### 4.1 Acciones y prompts (UNA sola línea, sin saltos de línea)

`_ACTION_COMMANDS` (dict literal en `services/plans_pipeline.py`):

```python
_ACTION_COMMANDS: dict[str, str] = {
    "proponer": "/proponer-plan-stacky",
    "criticar": "/criticar-y-mejorar-plan",
    "implementar": "/implementar-plan-stacky",
    "supervisar": "/supervisar-implementaciones-planes",
}
```

`build_action_prompt(action, plan_number_str, idea)` produce EXACTAMENTE:

| action | prompt resultante (una línea) |
|---|---|
| `proponer` sin idea | `/proponer-plan-stacky` |
| `proponer` con idea | `/proponer-plan-stacky Tema: <idea saneada>` |
| `criticar` | `/criticar-y-mejorar-plan <NN>` (NN = `number_str` del board, p.ej. `187`) |
| `implementar` | `/implementar-plan-stacky <NN>` |
| `supervisar` | `/supervisar-implementaciones-planes <NN>` |

Saneado de `idea` (función `_sanitize_idea`): `" ".join(idea.split())` (colapsa TODO
whitespace, incluidos saltos de línea — el prompt debe ser UNA línea para que el runtime
lo parsee como slash-command) y cap a **500** caracteres. Resultado vacío → sin sufijo.
`criticar/implementar/supervisar` sin `plan_number` → `ValueError("plan_number_requerido")`.

### 4.2 Payload y respuestas de `POST /api/plans-board/actions/run`

Request body (JSON):

```json
{
  "action": "proponer | criticar | implementar | supervisar",
  "plan_number": 187,
  "idea": "texto opcional, solo para proponer",
  "model": "claude-sonnet-5",
  "effort": "high",
  "runtime": "claude_code_cli"
}
```

- `plan_number`: obligatorio salvo `proponer` (int). `idea`: opcional, solo `proponer`.
- `model`/`effort`: opcionales. `model` vacío → `None` (decide el router del runner,
  igual que `run_incident`). `effort` vacío o inválido → `"high"`. Ambos pasan por los
  clamps EXISTENTES: `_llm_router.clamp_model(model, allow_opus=True)`
  (`api/agents.py:946`) y `_clamp_effort_for_model` (`api/agents.py:588`).
- `runtime`: opcional, default `"claude_code_cli"`; cualquier otro valor → 409.

Orden de validación CONGELADO (primer fallo corta):

| # | Chequeo | Respuesta |
|---|---|---|
| 1 | flags (root ON y actions ON) | 404 `{"ok": false, "error": "plans_pipeline_disabled", "message": "Las acciones del pipeline de planes están deshabilitadas (STACKY_PLANS_PIPELINE_ACTIONS_ENABLED)."}` |
| 2 | `runtime` ∈ {`claude_code_cli`} | 409 `{"ok": false, "error": "runtime_not_supported", "supported": ["claude_code_cli"]}` |
| 3 | `action` ∈ `_ACTION_COMMANDS` | 400 `{"ok": false, "error": "invalid_action"}` |
| 4 | `plans_board.repo_root()` no es None | 409 `{"ok": false, "error": "repo_not_available", "message": "No hay repo git de Stacky en esta instalación; las acciones del pipeline requieren el repo de desarrollo."}` |
| 5 | existe `repo_root()/.claude/skills/<skill>/SKILL.md` para la skill de la acción | 409 `{"ok": false, "error": "skills_not_found", "skill": "<nombre>"}` |
| 6 | para acciones con número: el plan existe en `get_board_cached(refresh=True)` | 404 `{"ok": false, "error": "plan_not_found"}` |
| 7 | la acción está permitida para el `estado` del plan (tabla §4.3) | 409 `{"ok": false, "error": "action_not_allowed_for_estado", "estado": "<estado>", "allowed": ["..."]}` |
| 8 | no hay corrida viva (dentro del lock §4.5) | 409 `{"ok": false, "error": "pipeline_action_already_running", "execution_id": <int>}` |
| 9 | lanzamiento OK | 202 `{"ok": true, "execution_id": <int>, "status": "running", "prompt_line": "<prompt exacto lanzado>"}` |
| — | `run_agent` lanza excepción | 502 `{"ok": false, "error": "agent_launch_failed", "message": "<str(exc)>"}` (espejo de `api/agents.py:1036-1046`) |

### 4.3 Tabla estado → acciones permitidas (única fuente, backend y frontend espejo)

```python
def allowed_actions_for(estado: str, doc_drift: bool | None) -> tuple[str, ...]:
    """estado = card["estado"] del board 128; doc_drift = card["ledger"]["doc_drift"]."""
    acts: list[str] = []
    if estado == "PROPUESTO":
        acts.append("criticar")
    if estado == "CRITICADO":
        acts.append("implementar")
    if estado in ("IMPLEMENTADO", "IMPLEMENTADO_PARCIAL") or doc_drift is True:
        acts.append("supervisar")
    return tuple(acts)
```

`proponer` NO entra en la tabla: es acción de tablero (sin card), siempre disponible si
pasan los chequeos 1-5 y 8. Es la misma semántica que `suggest_next_action` del 128
(:214-243) — el veredicto del juez NO gatea `implementar` porque en la práctica de la
casa toda v2 CRITICADA aplica los fixes (incluso las v1 RECHAZADAS reescritas).

### 4.4 `GET /api/plans-board/actions/runs?limit=20` (historial)

Gate: mismos flags que §4.2 chequeo 1 (404 idéntico con OFF). `limit` cap duro 50.
Respuesta 200:

```json
{
  "ok": true,
  "busy": false,
  "running_execution_id": null,
  "runs": [
    {
      "id": 123, "status": "completed",
      "started_at": "2026-07-18T12:00:00", "completed_at": "2026-07-18T12:19:03",
      "action": "criticar", "plan_number": 187,
      "model": "claude-opus-4-8", "effort": "high",
      "prompt_line": "/criticar-y-mejorar-plan 187"
    }
  ]
}
```

Fuente: query `AgentExecution` (`models.py:207`) con
`agent_type == "plans_pipeline"` (cabe en String(20): 14 chars), orden `id` DESC,
serializando `started_at/completed_at` con `.isoformat()` (None → null) y extrayendo
`action/plan_number/model/effort/prompt_line` de
`metadata_dict["plans_pipeline"]` (dict que persiste el endpoint tras lanzar — espejo
EXACTO del patrón `metadata_dict` de `api/agents.py:1062-1073`). `busy` =
`running_execution_id is not None`.

### 4.5 Serialización y pool

En `services/plans_pipeline.py`:

```python
_LAUNCH_LOCK = threading.Lock()          # serializa el chequeo-y-lanzamiento
PLANS_PIPELINE_ADO_ID = -9               # sentinel del pool (G11; re-verificar libre)
PLANS_PIPELINE_AGENT_TYPE = "plans_pipeline"

def find_running_pipeline_execution() -> int | None:
    """id de la corrida plans_pipeline en status 'running' más reciente, o None."""
    from db import session_scope
    from models import AgentExecution
    with session_scope() as s:
        row = (
            s.query(AgentExecution)
            .filter(
                AgentExecution.agent_type == PLANS_PIPELINE_AGENT_TYPE,
                AgentExecution.status == "running",
            )
            .order_by(AgentExecution.id.desc())
            .first()
        )
        return row.id if row else None
```

El endpoint envuelve chequeo 8 + lanzamiento en `with plans_pipeline._LAUNCH_LOCK:`.
El pool ticket se obtiene/crea con el patrón EXACTO de `api/agents.py:966-984`
cambiando SOLO: `ado_id=-9`, `external_id=-9`, `title="Plans Pipeline Pool Ticket"`,
`project` fijo `"default"`. `-9` se agrega a `_ONE_SHOT_ADO_IDS`
(`claude_code_cli_runner.py:218` → `frozenset({-1, -7, -8, -9})`).

### 4.6 `GET /api/plans-board/commits/<int:number>` (commits asociados, on-demand)

Gate: SOLO el root `STACKY_PLANS_BOARD_ENABLED` (es visualización; misma `_enabled()` y
404 de `api/plans_board.py:15-29`). Plan inexistente → 404 `plan_not_found`.
Repo sin git (`plans_board.repo_root()` None) → 200
`{"ok": true, "git_available": false, "commits": []}`.
Caso feliz → 200 `{"ok": true, "git_available": true, "commits": [{"hash": "8947aa4b", "date": "2026-07-18", "subject": "docs(plan-193): critica v1->v2"}]}`.

Implementación en `services/plans_pipeline.py` (NO en `plans_board.py`, que queda
intacto): `recent_commits_for_doc(filename: str) -> list[dict] | None` — UNA llamada
`subprocess.run(["git", "log", "-n", "5", "--date=short", "--pretty=format:%h|%ad|%s", "--", f"Stacky Agents/docs/{filename}"], cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)`;
cualquier excepción o returncode != 0 → `None` (el endpoint lo mapea a
`git_available: false`). Parseo: por línea no vacía, `line.split("|", 2)` →
`{"hash", "date", "subject"}` (menos de 3 partes → descartar la línea). Espejo del
estilo defensivo de `collect_unpushed_docs` (`plans_board.py:336-370`).

### 4.7 Metadata persistida por corrida

Tras el 202, el endpoint persiste (espejo de `api/agents.py:1062-1073`, mismo
try/except best-effort que nunca bloquea la respuesta):

```python
md["plans_pipeline"] = {
    "action": action,
    "plan_number": plan_number,          # int | None
    "model": model_override,             # str | None (post-clamp)
    "effort": effort_override,           # str (post-clamp)
    "prompt_line": prompt_line,
}
```

---

## 5. Fases

Orden por dependencia: **F0 → F1 → F2 → F3 → F4 → F5 → F6**.

> **Comandos:** backend desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend` con
> `.venv\Scripts\python.exe -m pytest tests/<archivo> -q` (verificar 3.13 primero, G5).
> Frontend desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend` con
> `npx vitest run src/<archivo>` y `npx tsc --noEmit`. SIEMPRE por archivo.

---

### F0 — Flags: promoción del root a ON + flag nueva de acciones (patrón triple)

**Objetivo (1 frase):** encender el tablero por default (hoy nace OFF pese a estar
implementado) y dar de alta la flag que protege las acciones, todo visible/toggleable
desde el panel de flags de la UI sin acción del operador.
**Valor:** el dashboard pedido por el operador aparece solo; kill-switch por UI.

**Archivos a editar (6):**
1. `Stacky Agents/backend/config.py` — (a) en el bloque de
   `STACKY_PLANS_BOARD_ENABLED` (:1331-1333, ubicar por la key literal) cambiar el
   default `"false"` → `"true"` (mismo patrón `.strip().lower() == "true"`, NO cambiar
   el parser); (b) agregar debajo, mismo estilo:
   ```python
    # Plan 196 — acciones HITL del pipeline de planes sobre el Tablero (128).
    # Cada accion es click+confirmacion del operador; lanza una corrida one-shot
    # claude_code_cli con las skills del repo. Nunca hace push.
    STACKY_PLANS_PIPELINE_ACTIONS_ENABLED: bool = os.getenv(
        "STACKY_PLANS_PIPELINE_ACTIONS_ENABLED", "true"
    ).strip().lower() == "true"
   ```
2. `Stacky Agents/backend/services/harness_flags.py` — (a) en el `FlagSpec` existente de
   `STACKY_PLANS_BOARD_ENABLED` (ubicar por key literal, cerca de `:3267`): asegurar
   `default=True`; (b) insertar inmediatamente después un `FlagSpec` nuevo:
   ```python
    FlagSpec(
        key="STACKY_PLANS_PIPELINE_ACTIONS_ENABLED",
        type="bool", default=True,
        label="Acciones del pipeline de planes",
        description=(
            "Plan 196 — botones Proponer/Criticar/Implementar/Supervisar en el "
            "Tablero de Planes: lanzan la corrida (Claude Code CLI + skills del "
            "repo) con modelo y effort a eleccion. Siempre con click y "
            "confirmacion; el push sigue siendo manual."
        ),
        group="global", requires="STACKY_PLANS_BOARD_ENABLED",
    ),
   ```
   (c) `_CATEGORY_KEYS` (G7): en la tupla que contiene
   `"STACKY_PLANS_BOARD_ENABLED"` (:265) agregar
   `"STACKY_PLANS_PIPELINE_ACTIONS_ENABLED",` inmediatamente después.
3. `Stacky Agents/backend/services/harness_flags_help.py` — entrada `PlainHelp` nueva:
   ```python
    "STACKY_PLANS_PIPELINE_ACTIONS_ENABLED": PlainHelp(
        what="Controla si el Tablero de Planes muestra botones para lanzar las etapas del pipeline (proponer, criticar, implementar, supervisar) sin salir de la app.",
        on_effect="Si la activás: cada plan muestra su siguiente paso como botón; al confirmarlo se lanza una corrida con el modelo y esfuerzo que elijas.",
        off_effect="Si la apagás: el tablero queda solo-lectura, como antes, con la acción sugerida copiable a mano.",
        example="Como pasar de un semáforo que solo te dice 'avanzá' a un botón que arranca el auto por vos — pero siempre apretás vos el botón.",
    ),
   ```
4. `Stacky Agents/backend/tests/test_harness_flags.py` — agregar AMBAS keys
   (`"STACKY_PLANS_BOARD_ENABLED"`, `"STACKY_PLANS_PIPELINE_ACTIONS_ENABLED"`) al set
   `_CURATED_DEFAULTS_ON` (:467) SI no están ya (la primera puede no estar porque su
   default era False).
5. `Stacky Agents/backend/tests/test_harness_flags_requires.py` — arista en
   `_REQUIRES_MAP_FROZEN` (:120):
   `"STACKY_PLANS_PIPELINE_ACTIONS_ENABLED": "STACKY_PLANS_BOARD_ENABLED",`.
6. Regenerar defaults: `.venv\Scripts\python.exe scripts/export_harness_defaults.py`
   (G14; NUNCA editar `harness_defaults.env` a mano).

**Tests primero (comandos de aceptación de la fase):**
- `.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q` → exit 0
  (incluye `test_every_registry_flag_is_categorized` y
  `test_default_known_only_for_curated` con las 2 flags).
- `.venv\Scripts\python.exe -m pytest tests/test_harness_flags_requires.py -q` → exit 0.

**Criterio binario:** ambos comandos exit 0 y
`Select-String -Path "Stacky Agents\backend\config.py" -Pattern "STACKY_PLANS_PIPELINE_ACTIONS_ENABLED"`
≥ 1 línea.
**Flags:** las 2 de arriba, default ON (excepciones duras: ninguna aplica — §3.3).
**Impacto por runtime:** idéntico en los 3 (config pura).
**Trabajo del operador: ninguno.**

---

### F1 — Catálogo dinámico de modelos/efforts: ejecutar F0-F3 del doc 159 (idempotente)

**Objetivo (1 frase):** materializar el subconjunto del Plan 159 que este plan consume
(loader + endpoint + flag + cliente/hook frontend), copiando LITERALMENTE lo que ese doc
ya especifica.
**Valor:** requerimiento 3 del operador (modelos Claude + efforts dinámicos, cero
hardcodeo) resuelto por el contrato ya criticado, sin inventar nada nuevo.

**Procedimiento EXACTO:**
1. Abrí `Stacky Agents/docs/159_PLAN_CATALOGO_UNIFICADO_MODELOS_EFFORTS_DINAMICO.md`.
2. Si `Stacky Agents/backend/services/model_catalog.py` NO existe: implementá las fases
   **F0, F1, F2 y F3** de ese doc AL PIE DE LA LETRA (archivos, símbolos, JSON, tests,
   comandos y registro en `HARNESS_TEST_FILES` tal como ese doc los define — incluye
   `backend/config/model_catalog.json`, `services/model_catalog.py`,
   `GET /api/agents/model-catalog` en `api/agents.py`, flag
   `STACKY_MODEL_CATALOG_ENABLED`, `ModelCatalogApi` en `endpoints.ts`,
   `services/modelCatalogFallback.ts`, `hooks/useModelCatalog.ts`, y la edición de
   `deployment/build_release.ps1`). PROHIBIDO implementar F4-F6 del 159 en esta corrida.
3. Si YA existe (159 implementado por otra corrida): NO reescribas nada; corré SOLO los
   comandos de aceptación de F0-F3 del doc 159 y verificá exit 0.

**Comandos de aceptación (los del doc 159, citados acá para el runner):**
```
.venv\Scripts\python.exe -m pytest tests/test_plan159_model_catalog_loader.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan159_model_catalog_endpoint.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan159_model_catalog_flag.py -q
npx vitest run src/services/__tests__/modelCatalogFallback.test.ts
```
**Criterio binario:** los 4 comandos exit 0.
**Flag:** `STACKY_MODEL_CATALOG_ENABLED` (default ON, definida por el 159).
**Impacto por runtime:** el catálogo expone los 3 runtimes (contrato 159); este plan
solo consumirá `runtimes.claude_code_cli`.
**Trabajo del operador: ninguno.**

---

### F2 — Backend: servicio `plans_pipeline` + agente registrado + override de workspace

**Objetivo (1 frase):** crear el módulo puro que arma prompts/valida acciones/serializa
corridas, registrar el agente `plans_pipeline` con su `.agent.md`, y habilitar que la
corrida corra con cwd = raíz del repo de Stacky.
**Valor:** todo el cerebro de las acciones queda testeable sin Flask.

**Archivos NUEVOS (3):**

1. `Stacky Agents/backend/services/plans_pipeline.py` — contenido (contratos §4.1, §4.3,
   §4.5, §4.6 tal cual):
   ```python
   """Plan 196 — acciones HITL del pipeline de planes sobre el Tablero (Plan 128).

   Modulo de servicio SIN Flask: prompts de las 4 skills, tabla estado->acciones,
   serializacion de corridas, lock de lanzamiento y git log por doc. El modulo del
   Plan 128 (services/plans_board.py) NO se modifica: solo se importa.
   """
   from __future__ import annotations

   import subprocess
   import threading
   from pathlib import Path

   _LAUNCH_LOCK = threading.Lock()
   PLANS_PIPELINE_ADO_ID = -9
   PLANS_PIPELINE_AGENT_TYPE = "plans_pipeline"
   _IDEA_MAX_CHARS = 500
   _GIT_TIMEOUT_SEC = 5

   _ACTION_COMMANDS: dict[str, str] = {
       "proponer": "/proponer-plan-stacky",
       "criticar": "/criticar-y-mejorar-plan",
       "implementar": "/implementar-plan-stacky",
       "supervisar": "/supervisar-implementaciones-planes",
   }

   # nombre de la carpeta de la skill bajo .claude/skills/ por accion
   _ACTION_SKILL_DIRS: dict[str, str] = {
       "proponer": "proponer-plan-stacky",
       "criticar": "criticar-y-mejorar-plan",
       "implementar": "implementar-plan-stacky",
       "supervisar": "supervisar-implementaciones-planes",
   }


   def _sanitize_idea(idea: str | None) -> str:
       if not idea:
           return ""
       return " ".join(idea.split())[:_IDEA_MAX_CHARS].strip()


   def build_action_prompt(action: str, plan_number_str: str | None, idea: str | None) -> str:
       """Prompt de UNA linea (§4.1). ValueError si la accion es invalida o falta numero."""
       cmd = _ACTION_COMMANDS.get(action)
       if cmd is None:
           raise ValueError("invalid_action")
       if action == "proponer":
           extra = _sanitize_idea(idea)
           return f"{cmd} Tema: {extra}" if extra else cmd
       if not plan_number_str:
           raise ValueError("plan_number_requerido")
       return f"{cmd} {plan_number_str}"


   def allowed_actions_for(estado: str, doc_drift: bool | None) -> tuple[str, ...]:
       acts: list[str] = []
       if estado == "PROPUESTO":
           acts.append("criticar")
       if estado == "CRITICADO":
           acts.append("implementar")
       if estado in ("IMPLEMENTADO", "IMPLEMENTADO_PARCIAL") or doc_drift is True:
           acts.append("supervisar")
       return tuple(acts)


   def skill_file_for(action: str, root: Path) -> Path:
       return root / ".claude" / "skills" / _ACTION_SKILL_DIRS[action] / "SKILL.md"


   def find_running_pipeline_execution() -> int | None:
       from db import session_scope
       from models import AgentExecution

       with session_scope() as s:
           row = (
               s.query(AgentExecution)
               .filter(
                   AgentExecution.agent_type == PLANS_PIPELINE_AGENT_TYPE,
                   AgentExecution.status == "running",
               )
               .order_by(AgentExecution.id.desc())
               .first()
           )
           return row.id if row else None


   def serialize_run(row) -> dict:
       md = dict(row.metadata_dict or {})
       pp = md.get("plans_pipeline") or {}
       return {
           "id": row.id,
           "status": row.status,
           "started_at": row.started_at.isoformat() if row.started_at else None,
           "completed_at": row.completed_at.isoformat() if row.completed_at else None,
           "action": pp.get("action"),
           "plan_number": pp.get("plan_number"),
           "model": pp.get("model"),
           "effort": pp.get("effort"),
           "prompt_line": pp.get("prompt_line"),
       }


   def recent_commits_for_doc(filename: str) -> list[dict] | None:
       """git log -n 5 read-only del doc (§4.6). None ante CUALQUIER problema."""
       from services import plans_board

       root = plans_board.repo_root()
       if root is None:
           return None
       try:
           result = subprocess.run(
               [
                   "git", "log", "-n", "5", "--date=short",
                   "--pretty=format:%h|%ad|%s",
                   "--", f"Stacky Agents/docs/{filename}",
               ],
               cwd=str(root),
               capture_output=True,
               text=True,
               encoding="utf-8",
               errors="replace",
               timeout=_GIT_TIMEOUT_SEC,
           )
       except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
           return None
       if result.returncode != 0:
           return None
       commits: list[dict] = []
       for raw_line in result.stdout.splitlines():
           parts = raw_line.strip().split("|", 2)
           if len(parts) != 3:
               continue
           commits.append({"hash": parts[0], "date": parts[1], "subject": parts[2]})
       return commits
   ```

2. `Stacky Agents/backend/services/plans_pipeline_context.py` — espejo EXACTO de
   `services/incident_context.py:116-139` con estas sustituciones:
   `_AGENT_FILENAME = "PlansPipeline.agent.md"`, función
   `ensure_plans_pipeline_agent_file() -> Path` (misma lógica de 3 niveles: existe → no
   tocar; template del repo `backend/agents/PlansPipeline.agent.md` si existe; si no,
   `_AGENT_TEMPLATE_MD` embebido; `write_text(..., encoding="utf-8", newline="")`).
   `_AGENT_TEMPLATE_MD` LITERAL:
   ```markdown
   # PlansPipeline — Ejecutor del pipeline de planes de Stacky

   Sos el ejecutor del pipeline de planes evolutivos de Stacky Agents.

   ## Única tarea
   El mensaje inicial de la corrida es UNA línea con una skill del pipeline
   (`/proponer-plan-stacky`, `/criticar-y-mejorar-plan <NN>`,
   `/implementar-plan-stacky <NN>` o `/supervisar-implementaciones-planes <NN>`).
   Ejecutá EXACTAMENTE esa skill con ese argumento, siguiendo sus pasos al pie de la letra.

   ## Reglas duras
   - PROHIBIDO `git push` (el push es siempre manual del operador).
   - PROHIBIDO `git stash`, `git reset --hard` y cambiar de rama.
   - Una corrida = una skill: no amplíes el alcance ni encadenes otras etapas.
   - Tu último mensaje es el resumen que la skill pide (ruta del artefacto + resumen corto).

   _PlansPipeline v1.0.0 — Stacky Agents (Plan 196)._
   ```

3. `Stacky Agents/backend/agents/plans_pipeline.py` — clase registrable (espejo de
   `agents/incident.py`):
   ```python
   """Plan 196 — agente ejecutor del pipeline de planes (una skill por corrida)."""
   from __future__ import annotations

   from .base import BaseAgent


   class PlansPipelineAgent(BaseAgent):
       type = "plans_pipeline"
       name = "Plans Pipeline Runner"
       icon = "🗂️"
       description = "Ejecuta una etapa del pipeline de planes (proponer/criticar/implementar/supervisar) vía las skills del repo"
       inputs_hint = ["línea de skill del pipeline con su argumento"]
       outputs_hint = ["doc de plan creado/criticado, implementación o auditoría según la skill"]
       default_blocks: list[str] = []

       def system_prompt(self) -> str:
           return (
               "Sos el ejecutor del pipeline de planes de Stacky. El mensaje inicial "
               "es UNA linea con una skill (/proponer-plan-stacky, "
               "/criticar-y-mejorar-plan, /implementar-plan-stacky o "
               "/supervisar-implementaciones-planes) y su argumento: ejecutala "
               "exactamente, sin ampliar el alcance. PROHIBIDO git push, git stash, "
               "git reset --hard o cambiar de rama: el push es siempre manual del operador."
           )
   ```

**Archivos a EDITAR (3):**

4. `Stacky Agents/backend/agents/__init__.py` — agregar
   `from .plans_pipeline import PlansPipelineAgent` (bloque de imports :1-12, orden
   alfabético tras `IncidentDevAgent`) y `PlansPipelineAgent(),  # Plan 196 — ejecutor del pipeline de planes`
   dentro de la lista del `registry` (:16-29, después de `IncidentDevAgent()`).
5. `Stacky Agents/backend/agent_runner.py` — (a) agregar a la firma de `run_agent`
   (:77-98), al final de los kwargs (después de `work_item_type: str = "Epic",`):
   `workspace_root_override: str | None = None,` con este comentario en la línea previa:
   `# Plan 196 — cwd explicito para corridas del pipeline de planes (repo de Stacky).`
   (b) en la rama `claude_code_cli` (:301-335), inmediatamente DESPUÉS del bloque
   `with session_scope() as _cs:` que setea `workspace_root` (:306-311, anclar por el
   símbolo `resolve_project_context`), insertar:
   ```python
            if workspace_root_override:
                workspace_root = workspace_root_override
   ```
   NO tocar la rama codex (:226-263) ni la de copilot: las acciones responden 409 antes
   de llegar ahí (§4.2 chequeo 2), y el parámetro queda documentado como claude-only.
6. `Stacky Agents/backend/services/claude_code_cli_runner.py` — línea :218:
   `_ONE_SHOT_ADO_IDS = frozenset({-1, -7, -8})` → `frozenset({-1, -7, -8, -9})`
   (anclar por el símbolo `_ONE_SHOT_ADO_IDS`, G11). Además, actualizar el
   comentario-inventario de sentinels en `api/agents.py:962-964` agregando
   `-9 plans pipeline` al final de la enumeración existente.

**Tests primero — NUEVO `Stacky Agents/backend/tests/test_plan196_pipeline_service.py`**
(9 casos; sin Flask, sin red):
1. `test_action_commands_frozen` — `_ACTION_COMMANDS` es EXACTAMENTE el dict de §4.1
   (comparación de igualdad completa).
2. `test_build_prompt_criticar` — `build_action_prompt("criticar", "187", None) == "/criticar-y-mejorar-plan 187"`
   y no contiene `"\n"`.
3. `test_build_prompt_proponer_sin_idea` — `== "/proponer-plan-stacky"`.
4. `test_build_prompt_proponer_sanea_idea` — idea `"linea1\nlinea2\t  x" + "a" * 600`
   → resultado de UNA línea, arranca con `"/proponer-plan-stacky Tema: linea1 linea2 x"`,
   largo total ≤ `len("/proponer-plan-stacky Tema: ") + 500`.
5. `test_build_prompt_requiere_numero` — `pytest.raises(ValueError)` para
   `build_action_prompt("implementar", None, None)`.
6. `test_allowed_actions_table` — los 5 mapeos: `("PROPUESTO", None) → ("criticar",)`;
   `("CRITICADO", None) → ("implementar",)`; `("IMPLEMENTADO", None) → ("supervisar",)`;
   `("IMPLEMENTADO_PARCIAL", None) → ("supervisar",)`; `("SIN_ESTADO", None) → ()`;
   más `("PROPUESTO", True)` contiene `"supervisar"` (drift fuerza re-supervisión).
7. `test_sentinel_registered_one_shot` —
   `from services.claude_code_cli_runner import _ONE_SHOT_ADO_IDS` y assert
   `plans_pipeline.PLANS_PIPELINE_ADO_ID in _ONE_SHOT_ADO_IDS` y
   `plans_pipeline.PLANS_PIPELINE_ADO_ID == -9`.
8. `test_agent_registered` — `import agents; a = agents.get("plans_pipeline")`;
   `a is not None`, `a.name == "Plans Pipeline Runner"`, `"push" in a.system_prompt()`.
9. `test_ensure_agent_file_writes_template` — monkeypatch de
   `plans_pipeline_context.stacky_agents_dir` (o del símbolo equivalente que importe el
   módulo, espejo del test del 131) a `tmp_path`; primera llamada crea
   `PlansPipeline.agent.md` con `"PROHIBIDO \`git push\`"` dentro; segunda llamada con el
   archivo editado a mano NO lo pisa.

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan196_pipeline_service.py -q`
**Criterio binario:** exit 0, `9 passed`.
**Flag:** ninguna nueva en esta fase (el gate vive en F3).
**Impacto por runtime:** módulo puro; el override de workspace es claude-only por diseño.
**Trabajo del operador: ninguno.**

---

### F3 — Backend: endpoints de acción, historial y commits en `api/plans_board.py`

**Objetivo (1 frase):** exponer §4.2, §4.4 y §4.6 como rutas ADITIVAS del blueprint
existente, con el lanzamiento espejado de `run_incident`.
**Valor:** el frontend tiene todo lo que necesita con 3 rutas nuevas y cero cambios a
las existentes.

**Archivo a EDITAR:** `Stacky Agents/backend/api/plans_board.py` (agregar al final del
archivo; los imports ya presentes `Blueprint, jsonify, request` y `config` alcanzan;
todo lo demás va con import lazy dentro de cada función, patrón del propio archivo :36):

```python
def _actions_enabled() -> bool:
    return _enabled() and bool(
        getattr(config, "STACKY_PLANS_PIPELINE_ACTIONS_ENABLED", False)
    )


def _actions_disabled_resp():
    return (
        jsonify({
            "ok": False,
            "error": "plans_pipeline_disabled",
            "message": (
                "Las acciones del pipeline de planes están deshabilitadas "
                "(STACKY_PLANS_PIPELINE_ACTIONS_ENABLED)."
            ),
        }),
        404,
    )


@bp.post("/actions/run")
def plans_pipeline_run():
    """Plan 196 §4.2 — lanza UNA etapa del pipeline como corrida one-shot
    claude_code_cli. Orden de validación congelado; espejo de
    api/agents.py run_incident para el lanzamiento."""
    if not _actions_enabled():
        return _actions_disabled_resp()

    from services import plans_board, plans_pipeline

    payload = request.get_json(force=True, silent=True) or {}

    runtime_raw = (payload.get("runtime") or "claude_code_cli").strip()
    if runtime_raw != "claude_code_cli":
        return jsonify({
            "ok": False, "error": "runtime_not_supported",
            "supported": ["claude_code_cli"],
        }), 409

    action = (payload.get("action") or "").strip()
    if action not in plans_pipeline._ACTION_COMMANDS:
        return jsonify({"ok": False, "error": "invalid_action"}), 400

    root = plans_board.repo_root()
    if root is None:
        return jsonify({
            "ok": False, "error": "repo_not_available",
            "message": (
                "No hay repo git de Stacky en esta instalación; las acciones "
                "del pipeline requieren el repo de desarrollo."
            ),
        }), 409

    skill_file = plans_pipeline.skill_file_for(action, root)
    if not skill_file.exists():
        return jsonify({
            "ok": False, "error": "skills_not_found",
            "skill": skill_file.parent.name,
        }), 409

    plan_number = payload.get("plan_number")
    plan_number_str: str | None = None
    if action != "proponer":
        try:
            plan_number = int(plan_number)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "plan_not_found"}), 404
        board = plans_board.get_board_cached(refresh=True)
        cards = [c for c in board["plans"] if c["number"] == plan_number]
        if not cards:
            return jsonify({"ok": False, "error": "plan_not_found"}), 404
        card = cards[0]
        ledger_info = card.get("ledger") or {}
        allowed = plans_pipeline.allowed_actions_for(
            card["estado"], ledger_info.get("doc_drift")
        )
        if action not in allowed:
            return jsonify({
                "ok": False, "error": "action_not_allowed_for_estado",
                "estado": card["estado"], "allowed": list(allowed),
            }), 409
        plan_number_str = card["number_str"]
    else:
        plan_number = None

    prompt_line = plans_pipeline.build_action_prompt(
        action, plan_number_str, payload.get("idea")
    )

    # modelo/effort: clamps EXISTENTES (espejo run_incident, api/agents.py:913-949)
    from api.agents import _clamp_effort_for_model
    from services import llm_router as _llm_router

    _model_raw = (payload.get("model") or "").strip()
    model_override = _llm_router.clamp_model(_model_raw, allow_opus=True) if _model_raw else None
    _effort_raw = (payload.get("effort") or "").strip().lower()
    effort_override = _effort_raw if _effort_raw in {"low", "medium", "high", "xhigh", "max"} else "high"
    effort_override = _clamp_effort_for_model(effort_override, model_override)

    import agent_runner
    from api.agents import current_user
    from db import session_scope
    from models import AgentExecution, Ticket
    from services.plans_pipeline_context import ensure_plans_pipeline_agent_file

    ensure_plans_pipeline_agent_file()

    with plans_pipeline._LAUNCH_LOCK:
        running_id = plans_pipeline.find_running_pipeline_execution()
        if running_id is not None:
            return jsonify({
                "ok": False, "error": "pipeline_action_already_running",
                "execution_id": running_id,
            }), 409

        # pool ticket (patrón EXACTO api/agents.py:966-984, sentinel -9)
        with session_scope() as session:
            pool_ticket = (
                session.query(Ticket)
                .filter_by(ado_id=plans_pipeline.PLANS_PIPELINE_ADO_ID, project="default")
                .first()
            )
            if pool_ticket is None:
                pool_ticket = Ticket(
                    ado_id=plans_pipeline.PLANS_PIPELINE_ADO_ID,
                    external_id=plans_pipeline.PLANS_PIPELINE_ADO_ID,
                    project="default",
                    stacky_project_name="default",
                    title="Plans Pipeline Pool Ticket",
                    work_item_type="Task",
                    ado_state="Active",
                )
                session.add(pool_ticket)
                session.flush()
            pool_ticket_id = pool_ticket.id

        context_blocks = [{
            "id": "plans-pipeline-command",
            "kind": "raw-conversation",
            "title": "Skill del pipeline a ejecutar",
            "content": prompt_line,
            "source": {"type": "plans_board_action", "action": action,
                       "plan_number": plan_number},
        }]

        try:
            execution_id = agent_runner.run_agent(
                agent_type="plans_pipeline",
                ticket_id=pool_ticket_id,
                context_blocks=context_blocks,
                user=current_user(),
                runtime="claude_code_cli",
                vscode_agent_filename="PlansPipeline.agent.md",
                project_name=None,
                use_few_shot=False,
                use_anti_patterns=False,
                model_override=model_override,
                effort_override=effort_override,
                workspace_root_override=str(root),
            )
        except Exception as exc:  # noqa: BLE001 — nunca 500 genérico (patrón Plan 39 B1)
            return jsonify({
                "ok": False, "error": "agent_launch_failed", "message": str(exc),
            }), 502

    # metadata best-effort (§4.7) — fuera del lock, nunca bloquea la respuesta
    try:
        with session_scope() as _s:
            _ex = _s.get(AgentExecution, execution_id)
            if _ex is not None:
                _md = dict(_ex.metadata_dict or {})
                _md["plans_pipeline"] = {
                    "action": action, "plan_number": plan_number,
                    "model": model_override, "effort": effort_override,
                    "prompt_line": prompt_line,
                }
                _ex.metadata_dict = _md
    except Exception:  # noqa: BLE001
        pass

    return jsonify({
        "ok": True, "execution_id": execution_id,
        "status": "running", "prompt_line": prompt_line,
    }), 202


@bp.get("/actions/runs")
def plans_pipeline_runs():
    """Plan 196 §4.4 — historial de corridas del pipeline (sin pollers: el
    frontend refresca a demanda)."""
    if not _actions_enabled():
        return _actions_disabled_resp()

    from db import session_scope
    from models import AgentExecution
    from services import plans_pipeline

    try:
        limit = min(max(int(request.args.get("limit", "20")), 1), 50)
    except ValueError:
        limit = 20

    with session_scope() as s:
        rows = (
            s.query(AgentExecution)
            .filter(AgentExecution.agent_type == plans_pipeline.PLANS_PIPELINE_AGENT_TYPE)
            .order_by(AgentExecution.id.desc())
            .limit(limit)
            .all()
        )
        runs = [plans_pipeline.serialize_run(r) for r in rows]

    running_id = plans_pipeline.find_running_pipeline_execution()
    return jsonify({
        "ok": True,
        "busy": running_id is not None,
        "running_execution_id": running_id,
        "runs": runs,
    })


@bp.get("/commits/<int:number>")
def plans_board_commits(number: int):
    """Plan 196 §4.6 — commits recientes del doc del plan (git log read-only)."""
    if not _enabled():
        return _disabled_resp()

    from services import plans_board, plans_pipeline

    detail = plans_board.get_detail(number)
    if detail is None:
        return jsonify({"ok": False, "error": "plan_not_found"}), 404

    commits = plans_pipeline.recent_commits_for_doc(detail["plan"]["filename"])
    if commits is None:
        return jsonify({"ok": True, "git_available": False, "commits": []})
    return jsonify({"ok": True, "git_available": True, "commits": commits})
```

**Tests primero — NUEVO `Stacky Agents/backend/tests/test_plan196_actions_api.py`**
(fixture `client` con el patrón de `tests/test_plan131_incident_flag.py`; para los casos
flag-ON, monkeypatch SIEMPRE sobre la INSTANCIA
`from config import config as config_instance` con `raising=False` — 10 casos):
1. `test_actions_flag_off_404` — `STACKY_PLANS_PIPELINE_ACTIONS_ENABLED=False` →
   POST `/api/plans-board/actions/run` → 404 `plans_pipeline_disabled`; GET
   `/api/plans-board/actions/runs` → 404 igual.
2. `test_runtime_not_supported` — flags ON, body `{"action":"proponer","runtime":"codex_cli"}`
   → 409, `supported == ["claude_code_cli"]`.
3. `test_invalid_action_400` — `{"action":"deployar"}` → 400 `invalid_action`.
4. `test_repo_not_available_409` — monkeypatch
   `services.plans_board.repo_root` → `lambda: None` → 409 `repo_not_available`.
5. `test_skills_not_found_409` — monkeypatch `repo_root` → `tmp_path` (sin `.claude`)
   → 409 `skills_not_found`.
6. `test_action_not_allowed_for_estado` — monkeypatch `repo_root` → `tmp_path` con el
   árbol `tmp_path/.claude/skills/criticar-y-mejorar-plan/SKILL.md` creado, y
   `services.plans_board.get_board_cached` → board fixture con un plan
   `{"number": 42, "number_str": "042", "estado": "IMPLEMENTADO", "ledger": None, ...}`;
   POST criticar sobre 42 → 409 `action_not_allowed_for_estado` y
   `allowed == ["supervisar"]`.
7. `test_busy_409` — mismo setup + monkeypatch
   `services.plans_pipeline.find_running_pipeline_execution` → `lambda: 777` →
   409 `pipeline_action_already_running` con `execution_id == 777`.
8. `test_happy_path_launches_run_agent` — setup del caso 6 con plan
   `estado="PROPUESTO"` + monkeypatch `agent_runner.run_agent` por un fake que captura
   kwargs y devuelve `123` + `find_running_pipeline_execution` → `lambda: None` +
   `ensure_plans_pipeline_agent_file` → no-op. POST criticar → 202,
   `execution_id == 123`, `prompt_line == "/criticar-y-mejorar-plan 042"`; los kwargs
   capturados cumplen: `agent_type == "plans_pipeline"`,
   `runtime == "claude_code_cli"`,
   `vscode_agent_filename == "PlansPipeline.agent.md"`,
   `workspace_root_override` termina en el nombre del `tmp_path`, y
   `context_blocks[0]["content"]` es EXACTAMENTE el `prompt_line`.
9. `test_runs_history_serialization` — sembrar en DB (fixture de sesión del patrón de
   `tests/test_plan131_run_incident.py`) un `Ticket` pool + un `AgentExecution` con
   `agent_type="plans_pipeline"`, `status="completed"` y
   `metadata_json` conteniendo `{"plans_pipeline": {"action": "proponer", ...}}` →
   GET runs → 200, `runs[0]["action"] == "proponer"`, `busy is False`.
10. `test_commits_endpoint` — (a) plan inexistente → 404 `plan_not_found`;
    (b) monkeypatch `services.plans_pipeline.recent_commits_for_doc` → `lambda f: None`
    con un plan del board fixture → `git_available is False` y `commits == []`.

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan196_actions_api.py -q`
**Criterio binario:** exit 0, `10 passed`.

**Registro en el arnés (G2, obligatorio):** agregar a `HARNESS_TEST_FILES` en
`backend/scripts/run_harness_tests.sh` Y `backend/scripts/run_harness_tests.ps1`
(sección nueva `— Plan 196 —`):
```
tests/test_plan196_pipeline_service.py
tests/test_plan196_actions_api.py
```
Verificación: `.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q`
bajo criterio NO-EMPEORAR (G8).

**Flag:** `STACKY_PLANS_PIPELINE_ACTIONS_ENABLED` (F0) gatea run/runs; el root gatea
commits. **Impacto por runtime:** acciones claude-only con 409 explícito (KPI-4);
visualización paritaria. **Trabajo del operador: ninguno.**

---

### F4 — Frontend: helpers puros + cliente API (testeables sin DOM)

**Objetivo (1 frase):** toda la lógica de UI (acciones permitidas, disponibilidad por
runtime, efforts por modelo, payloads) en funciones puras con tests vitest.
**Valor:** el componente de F5 queda "tonto" y el gate real es testeable (G10).

**Archivo NUEVO `Stacky Agents/frontend/src/plansBoard/actions.ts`:**

```typescript
import type { RuntimeModelCatalog } from "../api/endpoints";

export type PipelineAction = "proponer" | "criticar" | "implementar" | "supervisar";

export const ACTION_LABEL: Record<PipelineAction, string> = {
  proponer: "Proponer plan nuevo",
  criticar: "Criticar este plan",
  implementar: "Implementar este plan",
  supervisar: "Supervisar este plan",
};

export const RUNTIME_ACTION_NOTE =
  "Las acciones del pipeline usan las skills de Claude Code del repo; Codex y Copilot no las tienen. La visualización del tablero sí es idéntica en los 3 runtimes.";

/** Espejo EXACTO de allowed_actions_for del backend (§4.3). */
export function allowedActionsForCard(
  estado: string,
  docDrift: boolean | null | undefined
): PipelineAction[] {
  const acts: PipelineAction[] = [];
  if (estado === "PROPUESTO") acts.push("criticar");
  if (estado === "CRITICADO") acts.push("implementar");
  if (estado === "IMPLEMENTADO" || estado === "IMPLEMENTADO_PARCIAL" || docDrift === true) {
    acts.push("supervisar");
  }
  return acts;
}

/** Efforts válidos para un modelo según effort_support del catálogo (159).
 * Matriz vacía o modelo desconocido → TODOS los efforts del runtime (fallback
 * permisivo: el backend re-clampa igual). */
export function effortsForModel(
  rt: RuntimeModelCatalog | undefined,
  modelId: string
): { id: string; label: string }[] {
  const all = rt?.efforts ?? [];
  const supported = rt?.effort_support?.[modelId];
  if (!supported || supported.length === 0) return all;
  return all.filter((e) => supported.includes(e.id));
}

export interface RunPipelineActionPayload {
  action: PipelineAction;
  plan_number: number | null;
  idea: string | null;
  model: string | null;
  effort: string | null;
  runtime: "claude_code_cli";
}

export function buildRunPayload(
  action: PipelineAction,
  planNumber: number | null,
  idea: string,
  model: string,
  effort: string
): RunPipelineActionPayload {
  return {
    action,
    plan_number: action === "proponer" ? null : planNumber,
    idea: action === "proponer" && idea.trim() ? idea.trim() : null,
    model: model || null,
    effort: effort || null,
    runtime: "claude_code_cli",
  };
}
```

**EDITAR `Stacky Agents/frontend/src/api/endpoints.ts`** — inmediatamente DESPUÉS del
objeto `PlansBoard` (:4114-4120, anclar por el literal `"/api/plans-board/health"`):

```typescript
export interface PlanCommitDto { hash: string; date: string; subject: string }
export interface PipelineRunDto {
  id: number; status: string;
  started_at: string | null; completed_at: string | null;
  action: string | null; plan_number: number | null;
  model: string | null; effort: string | null; prompt_line: string | null;
}
export interface PipelineRunsResponse {
  ok: boolean; busy: boolean; running_execution_id: number | null; runs: PipelineRunDto[];
}
export interface RunPipelineActionResponse {
  ok: boolean; execution_id?: number; status?: string; prompt_line?: string;
  error?: string; message?: string; estado?: string; allowed?: string[];
}
export const PlansPipeline = {
  run: (payload: unknown) =>
    api.post<RunPipelineActionResponse>("/api/plans-board/actions/run", payload),
  runs: (limit = 20) =>
    api.get<PipelineRunsResponse>(`/api/plans-board/actions/runs?limit=${limit}`),
  commits: (number: number) =>
    api.get<{ ok: boolean; git_available: boolean; commits: PlanCommitDto[] }>(
      `/api/plans-board/commits/${number}`
    ),
};
```

(El tipo `RuntimeModelCatalog` ya existe en `endpoints.ts` desde F1/159-F3.)

**Tests primero — NUEVO `Stacky Agents/frontend/src/plansBoard/__tests__/actions.test.ts`**
(vitest puro, sin DOM; 8 casos):
1. `allowedActionsForCard("PROPUESTO", null)` → `["criticar"]`.
2. `allowedActionsForCard("CRITICADO", null)` → `["implementar"]`.
3. `allowedActionsForCard("IMPLEMENTADO", null)` → `["supervisar"]`.
4. `allowedActionsForCard("SIN_ESTADO", null)` → `[]`.
5. `allowedActionsForCard("PROPUESTO", true)` contiene `"supervisar"` (drift).
6. `effortsForModel` filtra por `effort_support` (catálogo fixture con
   `{"claude-haiku-4-5": ["low","medium","high"]}` → 3 efforts) y cae a TODOS con
   matriz vacía.
7. `buildRunPayload("proponer", null, " mi idea ", "", "")` →
   `{action:"proponer", plan_number:null, idea:"mi idea", model:null, effort:null, runtime:"claude_code_cli"}`.
8. `buildRunPayload("criticar", 187, "", "claude-opus-4-8", "xhigh")` →
   `plan_number === 187`, `idea === null`, `model === "claude-opus-4-8"`.

**Comandos:** `npx vitest run src/plansBoard/__tests__/actions.test.ts` → exit 0,
`8 passed`; `npx tsc --noEmit` → exit 0.
**Flag:** ninguna nueva. **Impacto por runtime:** helpers puros idénticos en los 3.
**Trabajo del operador: ninguno.**

---

### F5 — Frontend: cableado en `PlansBoardPage.tsx` (botones, selector, historial)

**Objetivo (1 frase):** sumar al tablero existente el panel de acciones con selector
modelo/effort dinámico, confirmación, estado busy, historial y commits — sin pollers y
sin inline styles.
**Valor:** el operador opera el pipeline completo desde `/planes` en 2 clicks.

**Archivos a EDITAR (2):** `Stacky Agents/frontend/src/pages/PlansBoardPage.tsx` y
`Stacky Agents/frontend/src/pages/PlansBoardPage.module.css` (todas las clases nuevas
van acá — G6; nombres: `.actionsPanel`, `.actionsRow`, `.actionsSelect`,
`.actionsNote`, `.runsList`, `.runRow`, `.runStatus`, `.commitsList`, `.busyChip`).

**Cableado EXACTO (sin decisiones libres):**
1. Imports nuevos: `ConfirmButton` (default export,
   `../components/ConfirmButton`), `PlansPipeline` y tipos desde `../api/endpoints`,
   `useModelCatalog` desde `../hooks/useModelCatalog` (F1/159-F3), y los helpers de
   `../plansBoard/actions`.
2. Estado nuevo del componente: `const [actionModel, setActionModel] = useState("")`,
   `const [actionEffort, setActionEffort] = useState("")`,
   `const [proposeIdea, setProposeIdea] = useState("")`,
   `const [lastLaunch, setLastLaunch] = useState<string | null>(null)` (mensaje de
   resultado, éxito o error).
3. Datos: `const { catalog } = useModelCatalog();`
   `const claudeCat = catalog.claude_code_cli;` — al resolver el catálogo, si
   `actionModel === ""` inicializarlo con `claudeCat?.default_model ?? ""` y
   `actionEffort` con `claudeCat?.default_effort ?? "high"` vía `useEffect` (dep:
   `claudeCat`). Query nueva react-query
   `{ queryKey: ["plans-pipeline-runs"], queryFn: () => PlansPipeline.runs(), retry: false }`
   — SIN `refetchInterval` (G9). Query de commits SOLO al abrir detalle:
   `{ queryKey: ["plans-board-commits", selectedNumber], queryFn: () => PlansPipeline.commits(selectedNumber as number), enabled: selectedNumber !== null, retry: false }`.
4. Gate de visibilidad del panel: el panel de acciones se renderiza SOLO si
   `runsQuery.data?.ok === true` (si el backend devolvió 404 por flag OFF o error de
   red, la página queda EXACTAMENTE como hoy — cero regresión, KPI-5). `busy` =
   `runsQuery.data?.busy === true`.
5. UI del panel superior (debajo de los filtros existentes), en este orden:
   - Selector de modelo: `<select>` sobre `claudeCat?.models ?? []`
     (`value={actionModel}`), label visible `Modelo`.
   - Selector de effort: `<select>` sobre `effortsForModel(claudeCat, actionModel)`
     (`value={actionEffort}`), label `Esfuerzo`. Si el effort seleccionado deja de ser
     válido al cambiar de modelo, resetear al primero de la lista filtrada (useEffect).
   - Texto fijo `Runtime: Claude Code CLI` con `title={RUNTIME_ACTION_NOTE}` (§3.2).
   - Input de texto opcional para la idea (`placeholder="Idea para el próximo plan (opcional)"`,
     `value={proposeIdea}`).
   - `<ConfirmButton>` con label `ACTION_LABEL.proponer`, deshabilitado si `busy`,
     `onConfirm` → `launch("proponer", null)`.
   - Si `busy`: chip `.busyChip` con el texto
     `Corrida #${runsQuery.data?.running_execution_id} en curso — el pipeline corre de a una`.
6. UI por card (en el drawer de detalle existente, `selectedNumber !== null`): por cada
   `a` de `allowedActionsForCard(plan.estado, plan.ledger?.doc_drift ?? null)` un
   `<ConfirmButton>` con `ACTION_LABEL[a]`, deshabilitado si `busy`, `onConfirm` →
   `launch(a, plan.number)`. Debajo, lista de commits del query de commits
   (`hash — date — subject` por fila; si `git_available === false`, el texto literal
   `Sin git disponible en esta instalación`).
7. Función `launch(action, planNumber)`:
   ```typescript
   const launch = (action: PipelineAction, planNumber: number | null) => {
     void PlansPipeline.run(buildRunPayload(action, planNumber, proposeIdea, actionModel, actionEffort))
       .then((r) => {
         if (r.ok && r.execution_id) {
           setLastLaunch(`Corrida #${r.execution_id} lanzada: ${r.prompt_line ?? action}`);
         } else {
           setLastLaunch(`No se lanzó: ${r.error ?? "error desconocido"}${r.message ? " — " + r.message : ""}`);
         }
       })
       .catch((e) => setLastLaunch(`No se lanzó: ${String(e)}`))
       .finally(() => {
         void queryClient.invalidateQueries({ queryKey: ["plans-pipeline-runs"] });
         void queryClient.invalidateQueries({ queryKey: ["plans-board-list"] });
       });
   };
   ```
   (`queryClient` = `useQueryClient()` de `@tanstack/react-query`, import nuevo.)
   `lastLaunch` se muestra en un `<div className={styles.actionsNote}>` persistente
   (sin auto-dismiss: el operador lo lee cuando quiere).
8. Sección `Corridas del pipeline` al pie de la página: tabla/lista de
   `runsQuery.data?.runs ?? []` con columnas `#id · action · plan_number · model ·
   effort · status · started_at` + botón `Refrescar` que invalida
   `["plans-pipeline-runs"]` y `["plans-board-list"]`. Sin links nuevos de navegación
   (el deep-link a ejecuciones queda para el Plan 165 — fuera de scope §7).

**Verificación:** `npx tsc --noEmit` → exit 0;
`npx vitest run src/plansBoard/__tests__/actions.test.ts` → sigue verde;
`Select-String -Path "Stacky Agents\frontend\src\pages\PlansBoardPage.tsx" -Pattern "setInterval"`
→ 0 líneas; `Select-String -Path "Stacky Agents\frontend\src\pages\PlansBoardPage.tsx" -Pattern "style=\{\{"`
→ 0 líneas.
**Criterio binario:** los 4 comandos con el resultado indicado.
**Flag:** el panel se auto-oculta con flag OFF (gate por respuesta del backend, punto 4).
**Impacto por runtime:** idéntico en los 3 (los botones lanzan siempre claude_code_cli;
§3.2). **Trabajo del operador: ninguno.**

---

### F6 — Cierre: verificación consolidada + smoke manual documentado

**Objetivo (1 frase):** correr todos los comandos de aceptación en una pasada y dejar
por escrito el smoke E2E que NO es automatizable acá.

**Comandos en orden (backend desde `Stacky Agents/backend`, frontend desde
`Stacky Agents/frontend`):**

```
.venv\Scripts\python.exe --version                                        (debe ser 3.13.x — G5)
.venv\Scripts\python.exe -m pytest tests/test_plan159_model_catalog_loader.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan159_model_catalog_endpoint.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan159_model_catalog_flag.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan196_pipeline_service.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan196_actions_api.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_flags_requires.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q   (NO-EMPEORAR, G8)
npx vitest run src/services/__tests__/modelCatalogFallback.test.ts
npx vitest run src/plansBoard/__tests__/actions.test.ts
npx tsc --noEmit
```

**Criterio binario global:** todos exit 0 (el ratchet-meta bajo NO-EMPEORAR: si falla,
su output NO menciona `plan196` ni `plan159`).

**Smoke manual (documentar como pendiente en el resumen final, NO bloqueante):** con el
backend dev corriendo y las flags ON: abrir `/planes` → el selector de modelo muestra
`Sonnet 5 (recomendado)` primero (catálogo vivo) → elegir un plan PROPUESTO → botón
`Criticar este plan` → confirmar → aparece `Corrida #N lanzada: /criticar-y-mejorar-plan <NN>`
y el chip busy; un segundo intento inmediato muestra `pipeline_action_already_running`;
al terminar la corrida, `Refrescar` muestra el run `completed` y el doc del plan pasó a
v2 en un commit local SIN push (verificar con `git log --oneline -1` y `git status`).

**Trabajo del operador: ninguno** (el smoke es verificación de quien implementa).

---

## 6. Riesgos y mitigaciones

- **Las skills son solo de Claude Code** → degradación explícita y honesta (409 +
  tooltip §3.2); la visualización queda 100% paritaria. Si algún día las skills se
  portan a otro runtime, solo cambia la lista `supported` (1 línea + tests).
- **Dos corridas concurrentes pisándose el working tree** → lock + busy-check §4.5
  (KPI-3). Riesgo residual: sesiones HUMANAS paralelas (documentado en el repo) — fuera
  del alcance del lock; mitigación heredada: las skills recalculan numeración en frío y
  commitean por pathspec.
- **La corrida se lanza y el operador la pierde de vista** → historial §4.4 con
  `execution_id` + las superficies existentes de ejecuciones/telemetría (142) la
  muestran gratis porque entra por `run_agent`.
- **CLI colgado / sesión zombie** → el pool entra en `_ONE_SHOT_ADO_IDS` (G11), y rige
  el timeout existente de 1800 s del runner (gotcha ya resuelto en el repo).
- **Auth del CLI limitada (OAuth = solo Haiku, gotcha registrado)** → el runner YA tiene
  fallback de modelo (`_spawn_claude_with_fallback`,
  `claude_code_cli_runner.py:904-919`); el run degrada de modelo, no muere. El
  historial muestra el modelo pedido; el log del run muestra el efectivo.
- **Board cache TTL 15 s podría validar la acción contra estado viejo** → el endpoint
  usa `get_board_cached(refresh=True)` (§4.2 chequeo 6) — costo: un scan de docs por
  click, aceptable.
- **`plan_number` con ceros a la izquierda** → el prompt usa `number_str` del board
  (preserva `042`), igual que `suggest_next_action` — cero divergencia con lo que el
  operador copiaba a mano.
- **Deploy congelado (sin `.git`, sin skills)** → chequeos 4-5 devuelven 409 con
  mensaje claro; el tablero sigue funcionando en lo que el deploy permita.
- **`test_harness_ratchet_meta` rojo preexistente** → criterio NO-EMPEORAR (G8),
  heredado del veredicto del 193.

## 7. Fuera de scope

- Portar las 4 skills a Codex CLI / Copilot (prompt embebido equivalente) — decisión
  explícita §3.2; si se quiere, es un plan futuro.
- Auto-push, auto-retry, scheduling/cron o disparo por condición de cualquier corrida.
- Editar/crear docs de planes desde la UI (el tablero sigue leyendo; escriben las skills).
- Fases F4-F6 del Plan 159 (migración de los 3 modales viejos) — siguen siendo del 159.
- Panel RSI, aspectos, propuestas y ciclo MAPE — Plan 167 (§2.4).
- Deep-links a la vista de ejecuciones y estado en URL — Plan 165 (pendiente).
- Streaming en vivo del log de la corrida dentro del tablero (existe en las superficies
  de ejecución actuales; duplicarlo acá es deuda).
- Cancelación de corridas desde el tablero (usa la superficie existente de ejecuciones).

## 8. Glosario, orden de implementación y Definición de Hecho

**Glosario (para un modelo menor):**
- **Plan / NN:** documento `Stacky Agents/docs/<NN>_PLAN_<SLUG>.md`; NN es secuencia
  compartida con checklists/incidentes.
- **Pipeline de skills:** las 4 etapas proponer → criticar → implementar → supervisar,
  implementadas como skills de Claude Code en `.claude/skills/<nombre>/SKILL.md`.
- **Juez / veredicto:** la skill `criticar-y-mejorar-plan` emite
  APROBADO / APROBADO-CON-CAMBIOS / RECHAZADO y reescribe el doc a v2.
- **Ledger de supervisión:** `Stacky Agents/docs/_supervision/ledger.json` — marca
  planes APROBADO con hash del doc; el board deriva `doc_drift` comparando sha256.
- **Tablero de Planes (128):** `services/plans_board.py` + `api/plans_board.py` +
  `pages/PlansBoardPage.tsx` — la base que este plan extiende.
- **Runtime:** motor que ejecuta un agente: `github_copilot`, `codex_cli` o
  `claude_code_cli` (`frontend/src/types.ts:10`).
- **Effort:** nivel de esfuerzo del Claude Code CLI (`low|medium|high|xhigh|max`),
  clampeado por modelo (`api/agents.py:588`).
- **Catálogo de modelos (159):** JSON en disco + endpoint
  `GET /api/agents/model-catalog`, recargado por mtime/TTL — la fuente dinámica de
  modelos/efforts.
- **One-shot / pool ticket / sentinel:** corrida CLI no conversacional anclada a un
  Ticket sintético con `ado_id` negativo; el sentinel DEBE estar en
  `_ONE_SHOT_ADO_IDS` o la corrida cuelga.
- **Execution:** fila `AgentExecution` (`models.py:207`) creada por `run_agent`; su
  `status` (`running/completed/error/failed`) es lo que muestra el historial.
- **FlagSpec / patrón triple:** alta de flag en `config.py` + `harness_flags.py`
  (registry + categoría) + ayuda llana; bools default-ON van a `_CURATED_DEFAULTS_ON`.
- **Ratchet:** meta-tests que obligan a registrar tests nuevos (`HARNESS_TEST_FILES`) y
  prohíben inline-styles nuevos en frontend.
- **HITL:** human-in-the-loop — toda acción es click del operador.

**Orden de implementación (estrictamente secuencial):**
1. F0 (flags) — 2. F1 (catálogo 159 F0-F3, idempotente) — 3. F2 (servicio + agente +
override) — 4. F3 (endpoints) — 5. F4 (helpers/cliente frontend) — 6. F5 (UI) —
7. F6 (cierre).
Dependencias: F3 necesita F0+F2; F5 necesita F1 (hook del catálogo) + F4; F6 todo.

**Definición de Hecho (DoD) global:**
1. Los 12 comandos de F6 con el resultado indicado (ratchet-meta bajo NO-EMPEORAR).
2. `grep -rn "CLAUDE_MODELS\|CLAUDE_EFFORTS\|ALT_MODELS" "Stacky Agents/frontend/src/plansBoard" "Stacky Agents/frontend/src/pages/PlansBoardPage.tsx"` → 0 resultados (KPI-2).
3. `grep -n "frozenset({-1, -7, -8, -9})" "Stacky Agents/backend/services/claude_code_cli_runner.py"` → 1 resultado (G11).
4. Los 2 tests `plan196` (y los 3 `plan159` si F1 los creó) registrados en
   `HARNESS_TEST_FILES` de `run_harness_tests.sh` Y `run_harness_tests.ps1`.
5. Las flags `STACKY_PLANS_BOARD_ENABLED` (ahora ON) y
   `STACKY_PLANS_PIPELINE_ACTIONS_ENABLED` visibles y toggleables en el panel de flags
   de la UI, con ayuda llana.
6. `harness_defaults.env` regenerado por `scripts/export_harness_defaults.py`
   (nunca a mano).
7. Smoke manual de F6 documentado como pendiente en el resumen final de la
   implementación (con su resultado si se corrió).
8. El módulo `services/plans_board.py` quedó BYTE-IDÉNTICO (`git diff --stat` no lo
   lista) — guardarraíl §3.5.
