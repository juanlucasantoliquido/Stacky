# Plan 169 — Optimizador evolutivo de artefactos de texto: mutación reflexiva (GEPA), frente Pareto calidad×costo y archive con lineage

**Estado:** PROPUESTO v1 — 2026-07-17 · **Autor:** StackyArchitectaUltraEficientCode
**Serie:** "Auto-mejora recursiva" **3 de 4** (directiva del operador 2026-07-17):
**167** = núcleo del panel + registro de propuestas + ciclo MAPE con gates humanos (PROPUESTO, dependencia DURA) ·
**168** = arnés de fitness: golden tasks, jerarquía de señal, juez local (PROPUESTO, dependencia DURA — provee `evaluate_candidate`) ·
**169 (este)** = optimizador evolutivo: generate→evaluate→select→archive sobre artefactos de texto ·
**170** = flywheel de conocimiento (NO se diseña acá; sus enchufes quedan congelados en §8).
Este documento implementa SOLO el 169. PROHIBIDO implementar acá nada del 170.

> Este documento está redactado para que un **MODELO MENOR** (Haiku, Codex CLI o
> GitHub Copilot Pro) lo implemente **SIN inferir nada**. Los nombres de símbolos,
> rutas, shapes JSON, literales de mensajes y comandos son **LITERALES**: prohibido
> desviarse de los nombres exactos, prohibido "mejorar" el alcance. Todo lo ambiguo ya
> fue decidido acá. Cada afirmación sobre código existente está anclada a
> `archivo:línea` **verificada el 2026-07-17**; este repo tiene sesiones paralelas, así
> que TODA edición se ancla por el CONTENIDO/símbolo citado, nunca solo por el número
> de línea. Los comandos con `&&` se ejecutan en **Git Bash** (en PowerShell 5.1 `&&`
> es error de parser).

**Dependencias (verificadas 2026-07-17):**

| Sustrato | Anclaje verificado | Rol en el 169 |
|---|---|---|
| **Plan 167 IMPLEMENTADO (DURA)** | `docs/167_PLAN_CENTRO_DE_EVOLUCION_…md` §4.3 (`ImprovementProposal` con `origin="optimizer"`, `parent_proposal_id`, `fitness_before/after`), §4.4 (máquina de estados), §8.2 (contrato de inyección hacia este plan), §3.1 (escalera de loop; `_HOTL_ALLOWED_ASPECTS = frozenset({"knowledge_rag"})` en `services/evolution_apply.py`) | F3 emite propuestas vía `evolution_store.create_proposal`; F4/F5 asumen `api/evolution.py` y `pages/EvolutionCenterPage.tsx` en el árbol. **Si el 167 no está implementado, DETENERSE y reportarlo.** |
| **Plan 168 IMPLEMENTADO (DURA)** | `docs/168_PLAN_ARNES_DE_FITNESS_…md` §8.2 (contrato CONGELADO `fitness_service.evaluate_candidate(aspect_key, artifact_text, case_filter, generator_model, use_judge)` → `{score, passed, eval_ref, per_case, critiques, cost, deterministic_gate}`), §4.4 (`DETERMINISTIC_FAIL_CAP=0.49`, deterministas mandan), §4.5 (`self_judge_risk` cuando `generator_model` == juez), F4 (`inject_proposal_fitness`), F1 (`case_store.prompts_dir()`, `slug_for_prompt_file`), F4 (`read_runs_tail`) | El fitness de CADA candidato es `evaluate_candidate` (sandbox, sin aplicar); las `critiques` del juez son la señal de la mutación reflexiva; `generator_model` garantiza juez≠generador. **Si el 168 no está implementado, DETENERSE y reportarlo.** |
| Invocación multi-runtime existente | `backend/agent_runner.py:77-95` (`run_agent(*, agent_type, ticket_id, context_blocks, user, …, model_override, effort_override, system_prompt_override, use_few_shot, use_anti_patterns, …, runtime="github_copilot", vscode_agent_filename=None, …)`), `:27` (`UnknownAgentError`); caller real multi-runtime: `backend/api/agents.py:1152-1164` (`run_incident_dev` pasa `runtime=runtime_raw`), `:1117` (`runtime_raw = payload.get("runtime") or "github_copilot"`), `:1135-1137` (runtimes CLI exigen `vscode_agent_filename` y auto-materializan el `.agent.md`) | F2: el generador en modo `runtime` entra por ESTA infraestructura — paridad de los 3 runtimes por delegación, cero camino nuevo |
| Precedente one-shot COMPLETO (Documentador, Plan 113) | `backend/services/doc_documenter.py:171` (`_INVOKE_TIMEOUT_S = 1800`), `:304` (`_CONVERSATION_ADO_ID = -7`), `:307-334` (`_ensure_documenter_ticket`: ticket sentinela `ado_id` discriminador + `external_id=-ticket.id`), `:337-361` (`_wait_and_read_output`: poll 1 s de `AgentExecution.status` hasta `{"completed","failed","cancelled","error"}` o timeout), `:364-416` (`invoke_documenter`: `run_agent` + espera + parse de marcadores `<<<DOC …>>>…<<<END>>>`), `:705` (`threading.Thread` on-demand), `:820` (`run_documenter(…, run_id=…)` con status consultable — docstring `:411` cita `GET /documenter/status`) | F2/F3: el generador `runtime` y la corrida asíncrona espejan ESTE patrón (ticket sentinela, espera, marcadores, thread por click + status) |
| Pool one-shot Claude CLI | `backend/services/claude_code_cli_runner.py:207-218` (comentario R1.2 + `_ONE_SHOT_ADO_IDS = frozenset({-1, -7, -8})`), `:221-223` (`_is_one_shot`); tests espejo: `backend/tests/test_plan131_run_incident.py:187-189` | F2 agrega el sentinel `-9` (sin esto, el run del mutador bajo Claude CLI queda esperando input 1800 s — gotcha documentado en el propio comentario R1.2) |
| Codex CLI runner | `backend/services/codex_cli_runner.py` (verificado: NO tiene lista one-shot equivalente; propaga `ado_id` en `:289/:367` sin gate conversacional) | F2: en Codex no hay cambio — el proceso termina solo al terminar el turno |
| Registro de agentes | `backend/agents/__init__.py:14-30` (`registry` dict por `a.type`; entrada `IncidentDevAgent(), # Plan 166 F4` en `:27`), `:10` (import); clase mínima espejo: `backend/agents/incident_dev.py:10-27` (`type/name/icon/description/inputs_hint/outputs_hint/default_blocks/system_prompt`) | F2 registra `EvolutionMutatorAgent` (`type="evolution_mutator"`) |
| Materialización de `.agent.md` runtime | `backend/services/incident_dev_context.py:97-118` (`ensure_incident_dev_agent_file`: si existe NO lo toca; si no, copia del template del repo; deploy frozen → template embebido); `backend/runtime_paths.py:220-232` (`stacky_agents_dir()`: `STACKY_AGENTS_DIR` override → `<stacky_home>/agents`), `:201-217` (`stacky_home()`) | F2: `ensure_evolution_mutator_agent_file()` es espejo EXACTO |
| LLM local (generador default) | `backend/copilot_bridge.py:241` (`invoke_local_llm(*, agent_type, system, user, on_log, execution_id=None, model=None)`), `:257-262` (RuntimeError si `LOCAL_LLM_ENDPOINT` vacío), `:263` (`model or config.LOCAL_LLM_MODEL`); `backend/config.py:90-93` (`LOCAL_LLM_ENDPOINT`/`LOCAL_LLM_MODEL`) — anclas citadas y verificadas por los Planes 167/168 | F2: generador `local` (default `auto`), USD 0, agnóstico de los 3 runtimes |
| Flags patrón triple | `backend/services/harness_flags.py:117` (`_CATEGORY_KEYS`), `:265` (tupla que contiene `"STACKY_PLANS_BOARD_ENABLED"` — los Planes 167/168 insertan ahí sus keys; este plan inserta las suyas DESPUÉS de las del 168, ubicar por `"STACKY_EVAL_RUN_TOKEN_BUDGET"`), `:3267` (FlagSpec `STACKY_PLANS_BOARD_ENABLED`; los FlagSpec del 167/168 van a continuación — insertar tras el de `STACKY_EVAL_RUN_TOKEN_BUDGET`), `type="str"` soportado (verificado: `:3333` `STACKY_INCIDENT_VISION_ENDPOINT`, `:3346` `STACKY_INCIDENT_VISION_MODEL` y 6 más) | F0 |
| `LOCAL_LLM_MODEL` es flag del registry | `backend/services/harness_flags.py:2967` (`key="LOCAL_LLM_MODEL"`) | F3: única entrada v1 de la allowlist de sugerencias `flag_change` |
| Meta-tests de flags | `backend/tests/test_harness_flags.py:467` (`_CURATED_DEFAULTS_ON`), `backend/tests/test_harness_flags_requires.py:120` (`_REQUIRES_MAP_FROZEN`) | F0 |
| `data_dir()` | `backend/runtime_paths.py:48` (ancla citada por 167/168) | Persistencia: `data_dir()/evolution/optimizer/` |
| Patrón store tolerante + lock | 167 §4.1 (store llama `runtime_paths.data_dir()` en CADA operación; lecturas tolerantes; lock; espejo de `services/incident_store.py:33/:44-52`) | F1 |
| Centro de Costos (Plan 142) | `backend/services/cost_analytics.py:35-43` (`CostRow` con `runtime/model/tokens_in/tokens_out/cost_usd`), `:138-150` (`ExecRecord.agent_type`), `:167` (`load_records`) — las ejecuciones de agentes se contabilizan SOLAS por este camino | Generador `runtime` → `AgentExecution` real con `agent_type="evolution_mutator"` → aparece como categoría propia en el Centro de Costos SIN vía nueva de ingesta (espejo del criterio 167 R7 / 168 §4.5) |
| Ratchet de tests | `backend/scripts/run_harness_tests.sh:20` (`HARNESS_TEST_FILES=(`; los 167/168 agregan sus bloques al final de la zona reciente) y `backend/scripts/run_harness_tests.ps1` (misma lista; ancla por contenido del bloque del Plan 168) | F6 |
| conftest backend | `backend/tests/conftest.py:11` (`STACKY_TEST_MODE`) | Todos los tests; LLM y `run_agent` SIEMPRE mockeados (cero egress, cero subprocess) |
| Primitivas UI (138/162) / estados (140) / formato (161) / ConfirmButton (136) / Toast (135) | `frontend/src/components/ui/index.ts:7-34` (barrel), `components/EmptyState.tsx` + `components/SkeletonList` (NO en el barrel), `services/format.ts:40-118` (`formatTokens/formatDateTime/…`), `components/ConfirmButton.tsx:23`, `components/Toast.tsx:9-19` — anclas verificadas por 167/168 | F5 |
| Página del Centro de Evolución | 167 F6 (`pages/EvolutionCenterPage.tsx`) + patrón de extensión del 168 F6 (sección nueva al FINAL de la página + namespace nuevo en `endpoints.ts` + 2 toques quirúrgicos) | F5: `OptimizerSection` se agrega igual que `FitnessSection` |

**Ortogonal a (NO tocar, NO depender):** Planes 153/154/156/163/164/165 (pendientes),
Plan 152 (notificaciones), Planes 158/159 (telemetría CLI / catálogo de modelos — cuando
el 159 exista, la allowlist de sugerencias §4.7 podrá crecer; NO bloquearse por eso).

---

## 1. Objetivo + KPI / impacto esperado

**Objetivo (1 párrafo):** con el 167 el sistema REGISTRA y GOBIERNA su mejora, y con el
168 la MIDE (`evaluate_candidate` da score + críticas de cualquier artefacto de texto,
en sandbox) — pero nadie GENERA candidatos mejores de forma sistemática: hoy mejorar el
prompt de un agente es artesanal (el operador o un chat lo reescribe a ojo, sin fitness,
sin memoria de qué mutaciones funcionaron, sin lineage). Este plan instala el
**optimizador evolutivo** (`evolution_optimizer`): una corrida on-demand (botón
"Optimizar" en el panel del 167) sobre UN artefacto objetivo (v1: un prompt
`*.agent.md` de `backend/Stacky/agents/`) que (a) evalúa el artefacto BASE con el 168;
(b) genera K variantes (default 3) con **mutación reflexiva** estilo GEPA — el prompt de
mutación lee las críticas textuales del juez y los checks fallados del propio base, los
padres del **frente Pareto** calidad×costo de corridas previas y las **lecciones de
mutación** acumuladas; (c) evalúa cada variante con `evaluate_candidate`
(`generator_model` declarado → juez≠generador garantizado por el 168); (d) selecciona
por dominancia Pareto (score máximo, costo proxy mínimo) y, SOLO si el ganador supera al
base por un **margen mínimo** configurable, emite una `ImprovementProposal` vía el
contrato del 167 (`origin="optimizer"`, `parent_proposal_id` para lineage,
`fitness_before/after` YA llenos) que entra `pending_review` — **el operador decide,
siempre**; (e) registra TODO en un **archive append-only con lineage** (también las
variantes descartadas — anti diversity-collapse, estilo Darwin Gödel Machine) y destila
**mutation lessons** reutilizables (process-level capital, survey RSI). El generador es
elegible por flag UI: **modelo local** (default si hay endpoint) o el **runtime activo**
(Codex CLI / Claude Code CLI / GitHub Copilot, por la infraestructura `run_agent`
existente). STOP conditions duras: K variantes, presupuesto de tokens, margen no
alcanzado, cancelación del operador. Sin daemons, sin cron: nada corre solo.

**KPIs binarios:**

- **KPI-1 — El optimizador JAMÁS aplica:** toda propuesta emitida nace
  `pending_review` con `origin="optimizer"`; el motor no importa `evolution_apply`; la
  allowlist HOTL del 167 sigue siendo exactamente `{"knowledge_rag"}` (test
  congelador). Comando:
  `.venv\Scripts\python.exe -m pytest tests/test_optimizer_engine.py -q` → exit 0.
- **KPI-2 — Mutación REFLEXIVA real:** el prompt de mutación enviado al generador
  (mock) contiene las críticas del juez y los checks fallados del base, las lecciones
  previas y los padres del frente. Cubierto por `tests/test_optimizer_engine.py`
  (casos 2-3).
- **KPI-3 — Selección Pareto + margen mínimo:** con fitness mockeados, el frente y el
  ganador son los esperados (incluye empates), y si `winner.score < base.score +
  margen` la corrida termina `no_improvement` SIN propuesta. Comando:
  `.venv\Scripts\python.exe -m pytest tests/test_optimizer_store.py tests/test_optimizer_engine.py -q` → exit 0.
- **KPI-4 — STOP conditions duras:** presupuesto agotado → `stopped_budget`;
  cancelación → `cancelled`; nunca más de K variantes. Cubierto por
  `tests/test_optimizer_engine.py` (casos 8-10).
- **KPI-5 — Degradación declarada del generador:** generador `local` sin
  `LOCAL_LLM_ENDPOINT` → la corrida NO arranca y el POST devuelve 409
  `generator_unavailable` con mensaje claro (estado visible, no error mudo — riel del
  Plan 135). Comando:
  `.venv\Scripts\python.exe -m pytest tests/test_optimizer_endpoints.py -q` → exit 0.
- **KPI-6 — Cero regresión / cero egress:** con `STACKY_EVOLUTION_OPTIMIZER_ENABLED=false`
  todos los endpoints nuevos (salvo `/optimizer/health`) devuelven 404 y la app queda
  byte-idéntica; ningún test del plan abre red ni lanza subprocess (`invoke_local_llm`
  y `agent_runner.run_agent` SIEMPRE monkeypatcheados). Comandos:
  `.venv\Scripts\python.exe -m pytest tests/test_optimizer_endpoints.py -q` → exit 0 y
  `npx tsc --noEmit` → exit 0.

**KPIs de impacto (proyectados, verificables por observación):**

| Métrica | Hoy | Con el plan |
|---|---|---|
| Generación sistemática de candidatos de mejora | inexistente (artesanal, a ojo) | 1 click → K variantes con fitness objetivo y propuesta gateada |
| Uso de las críticas del juez del 168 | se leen a mano en el panel | insumo automático del prompt de mutación (loop reflexivo GEPA) |
| Memoria de "qué tipo de cambio funcionó" | ninguna | `lessons.jsonl` por aspecto, inyectada en corridas futuras |
| Lineage de variantes (elegidas Y descartadas) | inexistente | `archive.jsonl` append-only + vista de árbol en el panel |
| Costo por corrida | — | acotado por presupuesto de tokens UI-configurable; generador local = USD 0; generador runtime = AgentExecutions reales visibles en el Centro de Costos como `evolution_mutator` |
| Evaluaciones por corrida | — | ≤ 1 (base) + K (variantes) — decenas, no miles (eficiencia muestral GEPA/Sakana) |

---

## 2. Por qué ahora / gap que cierra

### 2.1 Evidencia local

El 167 §8.2 congela el enchufe de este plan (*"Inyección: `POST /api/evolution/proposals`
con `origin="optimizer"`, `parent_proposal_id` para lineage y `evidence` con las trazas
leídas"*; *"el buffer Pareto/selección vive en el 169"*). El 168 §8.2 congela la firma de
`evaluate_candidate` y declara que *"el loop generate→evaluate→select, el archive Pareto
y el lineage viven en el 169; sus propuestas entran `pending_review`"*, y sus KPI-1/KPI-6
garantizan determinismo sin juez y runs `trigger=="candidate"` que no contaminan la
tendencia. Todo el sustrato de invocación ya existe: `run_agent` corre agentes bajo los 3
runtimes con un solo parámetro (`api/agents.py:1152-1164`), el Documentador ya resolvió
el patrón one-shot completo (ticket sentinela + espera + parse de marcadores —
`doc_documenter.py:307-416`) y el LLM local ya es el camino barato agnóstico de runtime
(Planes 106/127/167/168). Lo ÚNICO que falta es el motor que junta las piezas:
generate→evaluate→select→archive. Ese es este plan.

### 2.2 Fundamento de diseño (investigación citada por nombre → decisión concreta)

1. **GEPA (Cerebras/DSPy; adoptado por Databricks/Shopify/OpenAI)** — el corazón:
   evolución REFLEXIVA de texto. En vez de mutación ciega, el optimizador LEE las trazas
   completas de la evaluación (por qué falló cada caso) y propone una mutación DIRIGIDA;
   Pareto multi-objetivo en lugar de un escalar; muestrear padres desde el frente, no
   solo el mejor (anti estancamiento); 100-500 evaluaciones máximo teórico por corrida,
   90× más barato que RL → acá: el prompt de mutación (§4.5) recibe `critiques` +
   checks fallados del 168; frente calidad×`cost_proxy` (§4.4) persistido por aspecto
   con muestreo de padres (§F3); presupuesto default de Stacky MUY menor al teórico:
   K=3 variantes × 1 eval cada una + 1 eval del base (≤ 4 evals por corrida, cap de
   tokens UI-configurable).
2. **AlphaEvolve (Google DeepMind, 2025)** — loop generate→evaluate→select con base de
   datos evolutiva de programas; el LLM produce VARIANTES del artefacto actual;
   evaluadores automáticos como fitness → el loop de §F3 es esa traducción con el 168
   como evaluador automático y el archive como base evolutiva.
3. **Darwin Gödel Machine (Sakana AI, 2025)** — ARCHIVE expansivo de variantes con
   lineage, no hill-climbing simple: guardar también variantes sub-óptimas interesantes
   habilita open-ended exploration y evita diversity collapse; todo trazable; sandbox
   siempre → `archive.jsonl` append-only registra TODAS las variantes (también
   `dominated`/`invalid`) con `parent_id`; el frente Pareto conserva sub-óptimas no
   dominadas como padres futuros; evaluar nunca aplica (sandbox del 168).
4. **Survey RSI (arXiv 2607.07663)** — failure modes a mitigar POR DISEÑO:
   *self-confirming loops* (generador ≠ juez: el juez del 168 es el modelo local y este
   plan declara SIEMPRE `generator_model`; el mutador además NO puede optimizarse a sí
   mismo — §4.6 denylist); *diversity collapse* (archive + frente + muestreo de
   padres); *reward hacking* (deterministas mandan con cap 0.49 del 168; margen mínimo
   sobre el score CAPEADO; y el operador aprueba SIEMPRE — escalera del 167).
   *"Process-level beats result-level"*: el archive acumula ADEMÁS lecciones de
   mutación reutilizables entre corridas (§4.3 `mutation_lesson` + §F3 paso 7).
5. **Sakana RSI Lab (2026)** — eficiencia muestral sobre fuerza bruta; presupuestos
   chicos; aprendizaje estructurado de fallos → defaults conservadores (K=3, budget
   60000 tokens estimados, margen 2 puntos), STOP conditions duras, lecciones con
   outcome (`mejoro/empeoro/…`) en vez de re-descubrir a ciegas.

### 2.3 Delimitación con 167/168 (para que nadie los confunda)

El 167 es el REGISTRO y los GATES (dónde viven las propuestas y quién aprueba). El 168
es la MEDICIÓN (qué tan bueno es un texto). Este plan es la BÚSQUEDA (cómo encontrar un
texto mejor). No se modifica NINGÚN archivo creado por el 167/168 salvo los 4 puntos de
extensión explícitos: `_CATEGORY_KEYS`/`FLAG_REGISTRY`/help/meta-tests (F0, archivos de
flags compartidos), `api/__init__.py` (F4, registro de blueprint — 2 líneas),
`EvolutionCenterPage.tsx` (F5, 2 toques quirúrgicos idénticos al patrón del 168 F6) y
`endpoints.ts` (F5, namespace nuevo). PROHIBIDO tocar `evolution_store.py`,
`evolution_apply.py`, `evolution_cycle.py`, `fitness_service.py`, `case_store.py`,
`fitness_runner.py`, `judge.py`, `checks.py` o sus tests.

---

## 3. Principios y guardarraíles (NO negociables)

1. **El optimizador propone, el operador dispone.** Ninguna corrida aplica NADA: la
   única salida con efecto es una `ImprovementProposal` en `pending_review` (contrato
   167 §8.2). El motor NO importa `evolution_apply` (DoD lo verifica por grep). La
   allowlist human-on-the-loop del 167 (`_HOTL_ALLOWED_ASPECTS`) NO se toca: el
   optimizador NO está ni estará en ella (test congelador F3 caso 12). `closed_loop`
   sigue PROHIBIDO PARA SIEMPRE (167 §3.1).
2. **Human-in-the-loop innegociable / sin autonomía proactiva:** una corrida existe
   SOLO por click del operador en el panel (POST explícito). No hay daemon, no hay
   cron, no hay corridas programadas en v1 (el repo NO tiene scheduler genérico —
   verificado por el 167 §3.2). El único thread es POR corrida, nace con el click y
   muere al terminar (precedente exacto: `doc_documenter.py:705`).
3. **Cero trabajo extra al operador:** motor y UI default **ON** — el flag ON solo
   habilita el botón "Optimizar"; NO dispara nada solo. Defaults sanos para todo
   (generador `auto` = local si hay endpoint, si no runtime; K=3; budget 60000; margen
   2). TODO configurable desde la UI del Arnés (registry dinámico); **nada env-only**.
   Sin pasos manuales nuevos; backward-compatible (flag OFF → byte-idéntico).
4. **3 runtimes con paridad:** la generación de variantes funciona con Codex CLI,
   Claude Code CLI y GitHub Copilot vía `agent_runner.run_agent(runtime=…)`
   (`agent_runner.py:77-95`, caller espejo `api/agents.py:1152-1164`) Y con el LLM
   local (`invoke_local_llm`). Fallback declarado por combinación (tabla §F2). El
   resto del plan (motor, store, API, panel) es backend Flask + React idéntico en los 3.
5. **Juez ≠ generador (anti self-confirming loop):** el fitness SIEMPRE lo computa el
   168 (juez = modelo local); este plan declara `generator_model` en CADA
   `evaluate_candidate` (modo `local` → `config.LOCAL_LLM_MODEL`, y el 168 aplica solo
   su `SELF_JUDGE_MULTIPLIER`; modo `runtime` → `"runtime:<runtime>"`, que nunca
   coincide con el juez). El mutador NO se optimiza a sí mismo (§4.6).
6. **Mono-operador sin auth:** cero RBAC; `actor="optimizer"` es descriptivo (riel 167
   §3.5).
7. **No degradar:** cero pollers de página (el ÚNICO polling es el de una corrida EN
   CURSO, con `setTimeout` encadenado, tope duro y auto-stop — §F5; `setInterval`
   sigue en 0 como en el DoD del 167); stores con lock y lecturas tolerantes; con flag
   OFF byte-idéntico; los módulos del 167/168 quedan intactos (§2.3).
8. **Reusar, no reinventar:** `evaluate_candidate` + `inject_proposal_fitness` +
   `read_runs_tail` + `prompts_dir`/`slug_for_prompt_file` (168); `create_proposal` +
   `list_proposals` (167); `run_agent` + patrón one-shot del Documentador;
   `invoke_local_llm`; primitivas 138/162; estados 140; formato 161; ConfirmButton
   136; Toast 135.

### Gotchas del repo que el implementador DEBE respetar (verificadas)

- **G1 — `config` vs `config.config`:** en archivos nuevos usar SIEMPRE
  `from config import config as _cfg` y `getattr(_cfg, "FLAG", default)` (espejo de
  `api/metrics.py:565-566`; gotcha recurrente de `api/tickets.py:7401`).
- **G2 — Ratchet de tests:** los 5 `test_*.py` nuevos DEBEN agregarse a
  `HARNESS_TEST_FILES` en `backend/scripts/run_harness_tests.sh` (`:20`) **y**
  `backend/scripts/run_harness_tests.ps1`, como bloque "Plan 169" DESPUÉS del bloque
  del Plan 168 (anclar por contenido `tests/test_fitness_endpoints.py`), o el
  meta-test del Plan 49 se pone rojo.
- **G3 — Aristas `requires=`:** cada flag con `requires=` DEBE tener su arista en
  `_REQUIRES_MAP_FROZEN` (`backend/tests/test_harness_flags_requires.py:120`).
- **G4 — `_CURATED_DEFAULTS_ON`:** SOLO las flags **bool** con default efectivo ON van
  al set de `backend/tests/test_harness_flags.py:467`; las `type="int"` y `type="str"`
  NO (precedente: el 168 F0 declara `default=30000` en su int sin curarla, y
  `LOCAL_LLM_MODEL` es `type="str"` con default sin curar — `harness_flags.py:2967`).
- **G5 — venv y tests por archivo:** backend con `.venv`
  (`.venv\Scripts\python.exe -m pytest tests/<archivo> -q`), NUNCA la suite completa
  (contaminación cross-run conocida). Frontend `npx vitest run src/<archivo>`, por
  archivo.
- **G6 — Ratchet UI cero inline-style:** los `.tsx` nuevos tienen alcance 0 en
  `uiDebtRatchet`: TODO estilo va al `.module.css`; prohibido `style={{}}`.
- **G7 — `_CATEGORY_KEYS` obligatorio:** toda flag nueva va también al dict
  `_CATEGORY_KEYS` (`services/harness_flags.py:117`; nota normativa `:331`), en la
  MISMA tupla que contiene `"STACKY_PLANS_BOARD_ENABLED"` (`:265`), inmediatamente
  después de las entradas del Plan 168 (ubicar por `"STACKY_EVAL_RUN_TOKEN_BUDGET"`).
- **G8 — `requires` profundidad 1:** TODAS las aristas apuntan al ROOT
  `STACKY_EVOLUTION_CENTER_ENABLED` (master del 167), NUNCA en cadena a
  `STACKY_EVOLUTION_OPTIMIZER_ENABLED` ni a `STACKY_EVAL_HARNESS_ENABLED`
  (precedente normativo `harness_flags.py:3336`; gotcha del Plan 104). Los gates
  compuestos van EN CÓDIGO (§4.8 `_optimizer_enabled()` y el pre-check de F3).
- **G9 — Polling SOLO de corrida en curso:** cero `setInterval` (grep del DoD); el
  seguimiento de una corrida usa `setTimeout` encadenado con tope duro y stop en
  estado terminal/unmount (§F5). Fuera de una corrida activa, el panel NO emite
  requests periódicos (riel G9 del 167).
- **G10 — Corpus bajo `docs/`:** NADA de este plan escribe bajo `docs/`. Todo artefacto
  runtime va a `data_dir()/evolution/optimizer/`; el `.agent.md` del mutador va al dir
  runtime de agentes (`stacky_agents_dir()`), que está gitignorado.
- **G11 — `harness_defaults.env` NO se toca a mano** (lo regenera
  `scripts/export_harness_defaults.py` — riel del Plan 133 §3.6).
- **G12 — WIP ajeno / sesiones paralelas:** antes de editar cada archivo caliente
  (`config.py`, `harness_flags.py`, `harness_flags_help.py`, `api/__init__.py`,
  `agents/__init__.py`, `claude_code_cli_runner.py`, `endpoints.ts`,
  `EvolutionCenterPage.tsx`, scripts de ratchet): `git status -- "<ruta>"`; staging
  quirúrgico por pathspec; PROHIBIDO `git stash/reset/checkout`. OJO: al 2026-07-17
  `runtime_paths.py` y `run_preflight.py` tienen WIP ajeno sin commitear — este plan
  NO los edita (solo importa `runtime_paths`).
- **G13 — Prosa vs gates propios:** ninguna cadena/comentario/docstring del código
  nuevo debe matchear espuriamente los greps de criterio de este plan (gotcha
  recurrido 6×: el gate siempre gana; se reescribe la prosa).
- **G14 — Threads y SQLAlchemy en tests:** hay un crash nativo conocido cuando threads
  daemon tocan la DB durante el teardown de pytest. Riel duro: NINGÚN test de este
  plan lanza el thread real de la corrida — los tests llaman `_run_optimization_sync`
  (la función síncrona interna) directamente, con generador y fitness mockeados. El
  endpoint `POST /optimizer/run` se testea con `_start_run_async` monkeypatcheado a
  ejecución síncrona.
- **G15 — Deploy frozen tolerante:** resolución de targets/archivos SIEMPRE tolerante
  (dir ausente → lista vacía, NUNCA excepción — patrón `golden_runner.list_agents`);
  el template del mutador va embebido en el módulo (espejo
  `incident_dev_context.py:103-104`).

---

## 4. Contratos congelados (van tal cual al código)

### 4.1 Layout de persistencia (bajo `data_dir()/evolution/optimizer/`)

```
data_dir()/evolution/optimizer/
  runs.json      # lista completa de OptimizationRun (archivo entero, mutable con lock:
                 # una corrida CAMBIA de estado running->terminal; espejo de proposals.json del 167)
  archive.jsonl  # una línea por ArchiveEntry (append-only; el lineage NUNCA se borra)
  lessons.jsonl  # una línea por MutationLesson (append-only)
  pareto.json    # dict {aspect_key: [ParetoPoint, ...]} (frente vigente por aspecto)
```

Reglas duras (espejo del 167 §4.1): el store llama `runtime_paths.data_dir()` **en cada
operación** (sin cache de módulo — los tests lo monkeypatchean); lecturas tolerantes
(ausente/corrupto → vacío); escrituras bajo `_OPTIMIZER_LOCK = threading.Lock()`;
`mkdir(parents=True, exist_ok=True)`.

### 4.2 `OptimizationRun` (elemento de `runs.json`; todas las claves SIEMPRE presentes)

```json
{
  "id": "opt-<uuid4-hex>",
  "aspect_key": "agent_prompts/developer",
  "target_ref": "Developer.agent.md",
  "status": "running | completed | no_improvement | stopped_budget | cancelled | error",
  "error": null,
  "cancel_requested": false,
  "generator": {"mode": "local | runtime", "runtime": null, "model": "qwen3:32b"},
  "use_judge": true,
  "variants_planned": 3,
  "variants_done": 0,
  "base": null,
  "winner": null,
  "proposal_id": null,
  "parent_proposal_id": null,
  "margin_used": 0.02,
  "budget": {"limit_tokens": 60000, "tokens_est_in": 0, "tokens_est_out": 0, "exhausted": false},
  "steps": [{"ts": "<iso utc>", "text": "…"}],
  "started_at": "<iso utc>", "finished_at": null
}
```

Semántica congelada de `status` (única máquina de estados del run):

| status | significado | terminal |
|---|---|---|
| `running` | corrida en curso (thread vivo) | no |
| `completed` | terminó y EMITIÓ propuesta (`proposal_id` no nulo) | sí |
| `no_improvement` | terminó; el mejor candidato NO superó `base.score + margen` (o no hubo candidato válido) → SIN propuesta | sí |
| `stopped_budget` | presupuesto agotado antes de completar K variantes SIN ganador con margen (si hasta ahí HUBO ganador con margen, la propuesta se emite igual y el status final es `completed`) | sí |
| `cancelled` | el operador canceló; nunca emite propuesta | sí |
| `error` | excepción no recuperable; `error` tiene el detalle | sí |

`base` y `winner` (cuando no son `null`) tienen el shape
`{"variant_id": "var-…", "score": 0.81, "cost_proxy": 1234, "eval_ref": "eval-…"}`.
`steps` es un log humano-legible append-only dentro del run (máx 60 entradas; al
llegar al tope se deja de appendear y se agrega UNA entrada final con el texto
`"log truncado"`) — es lo que el panel muestra como progreso.

### 4.3 `ArchiveEntry` (una línea de `archive.jsonl`) y `MutationLesson` (una línea de `lessons.jsonl`)

```json
{
  "id": "var-<uuid4-hex>",
  "run_id": "opt-…",
  "aspect_key": "agent_prompts/developer",
  "target_ref": "Developer.agent.md",
  "parent_id": null,
  "kind": "base | variant",
  "artifact_hash": "sha256:<hex>",
  "artifact_text": "…",
  "fitness": {"score": 0.81, "passed": true, "deterministic_gate": "passed", "eval_ref": "eval-…"},
  "cost_proxy": 1234,
  "verdict": "base | winner | pareto | dominated | invalid",
  "invalid_reason": null,
  "critique_summary": null,
  "mutation_lesson": null,
  "generator_model": null,
  "created_at": "<iso utc>"
}
```

Reglas: `kind=="base"` tiene `parent_id=null`, `verdict=="base"` y
`generator_model=null`; toda `variant` tiene `parent_id` = id de la entry base de SU
corrida (v1: lineage de profundidad 1 por corrida; el lineage entre corridas se lee
por `aspect_key` + orden temporal + `parent_proposal_id` de las propuestas).
`artifact_text` se guarda completo SOLO si
`len(artifact_text) <= _ARCHIVE_TEXT_MAX_CHARS` (constante `20000`); si excede, se
persiste `null` y queda el `artifact_hash` (el texto completo de un ganador siempre
vive en la propuesta emitida). `verdict=="invalid"` (generación fallida, sin marcador,
idéntica al base) lleva `invalid_reason` y `fitness=null`. `critique_summary` =
concatenación de las `critiques` del 168 separadas por `" | "`, truncada a 500 chars.
Los demás verdicts: `winner` (elegida y con margen), `pareto` (quedó en el frente sin
ser winner), `dominated` (válida pero dominada).

```json
{"id": "les-<uuid4-hex>", "run_id": "opt-…", "aspect_key": "agent_prompts/developer",
 "variant_id": "var-…", "text": "<1-3 líneas del generador>",
 "outcome": "mejoro | empeoro | igual | invalida",
 "delta": 0.03,
 "created_at": "<iso utc>"}
```

`outcome` lo computa el MOTOR (nunca el LLM): `mejoro` si `variant.score >
base.score`; `empeoro` si `<`; `igual` si `==` (floats redondeados a 4 decimales, como
los emite el 168); `invalida` si la variante fue `invalid` (ahí `delta=null`; el
`text` del marcador se conserva si vino). `delta = variant.score - base.score`
redondeado a 4 decimales. Solo se persiste lesson si el generador emitió el bloque
`LECCION` (sin bloque → sin lesson; el motor NO inventa lecciones).

### 4.4 Frente Pareto calidad×costo (`pareto.json` + función pura)

- **Eje calidad:** `score` del 168 (0..1, ya con `DETERMINISTIC_FAIL_CAP` aplicado).
- **Eje costo:** `cost_proxy = max(1, len(artifact_text) // 4)` — tokens ESTIMADOS del
  artefacto. Por qué es un proxy honesto: el prompt de sistema del agente entra
  COMPLETO en cada ejecución del agente, así que su longitud es costo de entrada
  recurrente — la misma dimensión que el Centro de Costos 142 mide como `tokens_in`
  (`cost_analytics.py:35-43`). Mismo estimador `len//4` que 167 F3 / 168 F2.
- **Dominancia (congelada):** `a` domina a `b` sii `a.score >= b.score` y
  `a.cost_proxy <= b.cost_proxy` y (`a.score > b.score` o
  `a.cost_proxy < b.cost_proxy`). Empate EXACTO en ambos ejes: ninguno domina; se
  conservan ambos. Puntos con `score is None` NUNCA entran al frente.
- **Frente:** entradas no dominadas por ninguna otra. Función pura
  `pareto_front(points: list[dict]) -> list[dict]` (devuelve orden `score` DESC,
  desempate `cost_proxy` ASC, desempate final `variant_id` ASC — determinista total).
- **`ParetoPoint` persistido:**
  `{"variant_id": "var-…", "run_id": "opt-…", "score": 0.81, "cost_proxy": 1234, "artifact_hash": "sha256:…", "created_at": "<iso>"}`.
- **Actualización por corrida:** al cerrar una corrida (cualquier status terminal
  salvo `error`), el frente del `aspect_key` se recomputa con
  `frente_previo ∪ {base, variantes válidas de la corrida}` y se poda a
  `_PARETO_MAX = 8` puntos (si excede, se eliminan los de MENOR `score`; empate →
  mayor `cost_proxy` primero).
- **Muestreo de padres:** la corrida siguiente inyecta al prompt de mutación hasta
  `_PARETO_PARENTS = 2` puntos del frente (excluyendo los que tengan el mismo
  `artifact_hash` que el base actual), elegidos con `rng.sample`; el motor recibe el
  RNG inyectable (`rng: random.Random | None = None` → default `random.Random()`)
  para testeo determinista.

### 4.5 Prompt de mutación reflexiva (literales)

```python
_MUTATOR_SYSTEM = (
    "Sos el MUTADOR del optimizador evolutivo de Stacky. Recibis un ARTEFACTO DE TEXTO "
    "(el prompt de sistema de un agente), las CRITICAS de su ultima evaluacion (por que "
    "fallo cada caso), LECCIONES de mutaciones previas y opcionalmente PADRES (variantes "
    "prometedoras anteriores). Tu unica tarea es producir UNA variante COMPLETA y "
    "mejorada del artefacto que ataque especificamente las criticas, conservando todo "
    "lo que ya funciona (rol, contrato de salida, limites). PROHIBIDO: acortar el "
    "artefacto a menos de la mitad, cambiar el idioma, inventar herramientas o "
    "capacidades, eliminar rieles de seguridad o de supervision del operador. Responde "
    "EXACTAMENTE con este formato y nada mas:\n"
    "<<<VARIANTE>>>\n{artefacto completo}\n<<<FIN_VARIANTE>>>\n"
    "<<<LECCION>>>\n{1-3 lineas: que cambiaste y por que deberia mejorar el score}\n"
    "<<<FIN_LECCION>>>"
)
```

El mensaje `user` lo arma `build_mutation_prompt` (§F3) con EXACTAMENTE estas
secciones en este orden (una sección sin datos se omite completa, encabezado
incluido):

```
ARTEFACTO ACTUAL (score {base_score}, costo {base_cost} tokens est.):
{base_text}

CRITICAS DE LA ULTIMA EVALUACION:
- {critique 1}
- {critique 2}

CHECKS DETERMINISTAS FALLADOS:
- {case_title}: {check kind} -> {detail}

LECCIONES DE MUTACIONES PREVIAS (outcome entre parentesis):
- ({outcome}, delta {delta}) {text}

PADRES DEL FRENTE PARETO (variantes previas prometedoras, resumen):
- score {score} / costo {cost_proxy} tokens est.:
{primeras 40 lineas del artifact_text del padre, si esta en el archive}

VARIANTE {k} de {K}. Ataca las criticas senaladas.
```

Marcadores de extracción (helper `extract_block(text, start_marker, end_marker) ->
str | None`, tolerante: sin marcador o desbalanceado → `None`):
`<<<VARIANTE>>>`/`<<<FIN_VARIANTE>>>`, `<<<LECCION>>>`/`<<<FIN_LECCION>>>`,
`<<<SUGERENCIA_FLAG>>>`/`<<<FIN_SUGERENCIA_FLAG>>>` (§4.7). Precedente del patrón de
marcadores en el repo: bloques `<<<DOC …>>>…<<<END>>>` del Documentador
(`doc_documenter.py:437-438`).

### 4.6 Targets elegibles v1 y selección/emisión (congelados)

- **Target elegible v1:** cada archivo `*.agent.md` de `case_store.prompts_dir()`
  (contrato 168 F1 — el MISMO dir que la allowlist de apply del 167 F2 y que los
  seeds del 168; verificado en disco por el 167: `BusinessAgent.agent.md`,
  `Developer.agent.md`, `DevOpsAgent.agent.md`, `Documentador.agent.md`,
  `FunctionalAnalyst.agent.md`, `IncidentAnalyst.agent.md`, `QAUat1.agent.md` — ahí
  NO hay "skills" sueltas: los artefactos optimizables v1 son EXACTAMENTE los
  `.agent.md`, que además son lo único que el apply del 167 acepta), MENOS la
  denylist dura:

  ```python
  _TARGET_DENYLIST = frozenset({"EvolutionMutator.agent.md"})
  ```

  (el optimizador NO se optimiza a sí mismo en v1 — anti self-confirming loop del
  survey RSI; test congelador F3). `aspect_key` del target =
  `"agent_prompts/" + case_store.slug_for_prompt_file(filename)` (contrato 168 §4.2).
  `knowledge_rag` y `stacky_codebase` quedan FUERA del optimizador v1 (§7).
- **Selección:** candidatos = variantes de la corrida con `fitness` no nulo y `score`
  no nulo. Frente local = `pareto_front(candidatos)`. `winner` = primer elemento del
  frente (mejor `score`; empate → menor `cost_proxy`).
- **Margen mínimo:** `margen = max(0, int(getattr(_cfg,
  "STACKY_EVOLUTION_OPTIMIZER_MIN_MARGIN_PCT", 2))) / 100.0`. Se emite propuesta sii
  `winner` existe **y** `winner.fitness["deterministic_gate"] != "failed"` **y**
  `round(winner.score, 4) >= round(base.score + margen, 4)`. Caso borde congelado:
  `base.score is None` (aspecto sin casos corridos) → NUNCA se emite
  (`no_improvement`, step literal `"base sin score evaluable"`).
- **Emisión (contrato 167 §8.2, llamada de servicio en el mismo proceso):**

  ```python
  proposal = evolution_store.create_proposal(
      aspect_id="agent_prompts",
      title=f"[Optimizador] Mejora de {target_ref}: score {base_score:.2f} -> {winner_score:.2f}",
      rationale=<resumen determinista: margen usado, criticas atacadas (primeras 3),
                 mutation_lesson de la ganadora si existe>,
      origin="optimizer",
      artifact_type="prompt_file",
      target_ref=target_ref,
      proposed_content=<texto COMPLETO de la variante ganadora>,
      evidence=[f"optimizer:{run_id}", f"base_score={base_score}",
                f"winner_score={winner_score}", f"margen={margen}",
                f"eval_base={base_eval_ref}", f"eval_winner={winner_eval_ref}"],
      initial_status="pending_review",
      parent_proposal_id=<regla abajo>,
      actor="optimizer",
  )
  ```

  seguido de `fitness_service.inject_proposal_fitness(pid, "before", {...})` y
  `inject_proposal_fitness(pid, "after", {...})` con el shape EXACTO del 167 §4.7:
  `{"score": <score>, "metrics": {"passed": <bool>, "deterministic_gate": <str>, "generator_model": <str|null>, "cost_proxy": <int>}, "eval_ref": <id del EvalRun del 168>, "evaluated_at": <iso utc>}`
  — `before` desde la evaluación del BASE, `after` desde la del WINNER. Así la
  propuesta llega a la bandeja del 167 con `fitness_before/after` YA llenos (el 167
  los muestra sin cambiar una línea).
- **Regla `parent_proposal_id` (lineage entre corridas):** la propuesta MÁS RECIENTE
  (por `created_at`) de `evolution_store.list_proposals(origin="optimizer")` cuyo
  `target_ref` coincide con el de esta corrida; si no hay ninguna, `null`.

### 4.7 Sugerencia de valor de flag (`config_flags_models`, modo SUGERENCIA — sin loop)

El aspecto `config_flags_models` NO tiene fitness (el 168 responde
`fitness_not_applicable` a `flag_change`), así que NO corre loop evolutivo. En cambio,
el generador PUEDE emitir en la misma respuesta un bloque opcional:

```
<<<SUGERENCIA_FLAG>>>
{"flag": "LOCAL_LLM_MODEL", "value": "qwen3:14b", "razon": "…"}
<<<FIN_SUGERENCIA_FLAG>>>
```

Reglas duras: (a) allowlist congelada
`_SUGGESTABLE_FLAGS = frozenset({"LOCAL_LLM_MODEL"})` — única flag de modelo/costo
verificada en el registry (`harness_flags.py:2967`); ampliarla es un plan futuro
(p. ej. cuando exista el catálogo del Plan 159). (b) TODO lo que no está en la
allowlist se DESCARTA con step literal
`"sugerencia de flag descartada: <flag> fuera de allowlist"` — en particular NINGUNA
flag `STACKY_EVOLUTION_*` / `STACKY_EVAL_*` puede estar jamás en
`_SUGGESTABLE_FLAGS` (test congelador F3: el optimizador no puede sugerir tocar sus
propios rieles ni los del arnés — esto congela la denylist de "flags de seguridad" por
construcción: allowlist-only). (c) A lo sumo UNA sugerencia por corrida (la primera
válida; JSON no parseable → descartada con step). (d) La sugerencia se emite como
propuesta del 167 con `aspect_id="config_flags_models"`,
`artifact_type="flag_change"`, `target_ref=<flag>`, `proposed_content=<value>`,
`origin="optimizer"`, `initial_status="pending_review"`, `evidence=[f"optimizer:{run_id}", f"razon={razon}"]`
— y el 167 YA garantiza que `flag_change` NUNCA se aplica automáticamente (167 §4.3:
deep-link al Arnés; `apply` → 409 `artifact_not_appliable`).

### 4.8 Contratos HTTP (blueprint `evolution_optimizer`, url_prefix `/evolution` → `/api/evolution/...`)

Gate compuesto EN CÓDIGO (G8):
`_optimizer_enabled() = bool(getattr(_cfg, "STACKY_EVOLUTION_CENTER_ENABLED", False)) and bool(getattr(_cfg, "STACKY_EVOLUTION_OPTIMIZER_ENABLED", False))`.
Flag OFF → 404 literal
`{"ok": false, "error": "optimizer_disabled", "message": "El optimizador evolutivo está deshabilitado (STACKY_EVOLUTION_OPTIMIZER_ENABLED)."}`
(salvo `/optimizer/health`, SIEMPRE 200 — patrón `api/metrics.py:565-573`).

| Método y ruta | ON |
|---|---|
| `GET /api/evolution/optimizer/health` | 200 `{"ok": true, "flag_enabled": <bool>, "generator_mode": "local\|runtime", "generator_ready": <bool>, "harness_enabled": <bool>}` — `generator_mode` = `resolve_generator_mode()` (§F2); `generator_ready`: modo `local` → `LOCAL_LLM_ENDPOINT` no vacío, modo `runtime` → `true`; `harness_enabled` = CENTER && `STACKY_EVAL_HARNESS_ENABLED`. Health responde 200 también con flag OFF. |
| `GET /api/evolution/optimizer/targets` | 200 `{"ok": true, "targets": [{"target_ref": "Developer.agent.md", "aspect_key": "agent_prompts/developer", "cases_enabled": 3, "last_score": 0.81}]}` — glob tolerante de `case_store.prompts_dir()` menos `_TARGET_DENYLIST`, orden alfabético; `cases_enabled` = `len(case_store.list_cases(aspect_key=…, enabled=True))` filtrado `subject=="artifact"`; `last_score` = score del run más reciente con `trigger != "candidate"` de ese aspecto vía `case_store.read_runs_tail` (o `null`). |
| `POST /api/evolution/optimizer/run` body `{"target_ref": "…", "runtime": null, "use_judge": true}` | **202** `{"ok": true, "run": {OptimizationRun con status "running"}}` \| 404 `target_not_found` (no está en el glob o está en denylist) \| 409 `optimizer_already_running` \| 409 `generator_unavailable` con message literal `"El generador local no está configurado (LOCAL_LLM_ENDPOINT). Configuralo en el Arnés o elegí el generador runtime."` \| 409 `fitness_harness_disabled` (si `harness_enabled` es false — sin el 168 no hay fitness) \| 400 `invalid_payload` (`runtime` fuera de `{null, "github_copilot", "claude_code_cli", "codex_cli"}`) |
| `POST /api/evolution/optimizer/runs/<rid>/cancel` | 200 `{"ok": true, "run": {…}, "note": "cancelación cooperativa: se aplica entre pasos; la invocación en curso termina sola"}` (setea `cancel_requested=true`) \| 404 `run_not_found` \| 409 `run_not_running` (ya terminal) |
| `GET /api/evolution/optimizer/runs/<rid>` | 200 `{"ok": true, "run": {…}}` \| 404 `run_not_found` — la vista de corrida POLLEA este endpoint SOLO mientras `status=="running"` (§F5) |
| `GET /api/evolution/optimizer/runs?limit=20` | 200 `{"ok": true, "runs": […]}` (más nuevo primero; clamp limit 1..100) |
| `GET /api/evolution/optimizer/archive?run_id=&aspect_key=&limit=50` | 200 `{"ok": true, "entries": […]}` (filtros AND opcionales; tail más nuevo primero; clamp 1..200) |
| `GET /api/evolution/optimizer/lessons?aspect_key=&limit=20` | 200 `{"ok": true, "lessons": […]}` (tail más nuevo primero; clamp 1..100) |
| `GET /api/evolution/optimizer/pareto?aspect_key=` | 200 `{"ok": true, "front": […]}` \| 400 `aspect_key_requerido` si falta |

---

## 5. Fases

Orden por dependencia: **F0 → F1 → F2 → F3 → F4 → F5 → F6**. Pre-check GLOBAL antes de
F0 (los dos, obligatorios):
`test -f "Stacky Agents/backend/services/evolution_store.py"` (Plan 167) y
`test -f "Stacky Agents/backend/services/fitness_service.py"` (Plan 168) — si falta
cualquiera, DETENERSE y reportar "Plan 167/168 no implementado".

> **Comandos de test:** backend desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend`
> con `.venv\Scripts\python.exe -m pytest tests/<archivo> -q` (Git Bash:
> `cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/<archivo> -q`).
> Frontend desde `Stacky Agents/frontend` con `npx vitest run src/<archivo>`. SIEMPRE
> por archivo (G5). **REGLA DURA de red/subprocess:** TODO test de este plan
> monkeypatchea `copilot_bridge.invoke_local_llm` Y `agent_runner.run_agent` cuando su
> camino los alcanza — ningún test abre sockets ni lanza procesos (G14: tampoco
> threads reales).

---

### F0 — Flags del optimizador (patrón triple)

**Objetivo (1 frase):** declarar las 5 configuraciones del optimizador con el patrón
triple, editables por UI, sin nada env-only.
**Valor:** kill-switch por UI; generador, K, presupuesto y margen gobernados desde el
panel del Arnés.

**Archivos a editar (5):** `backend/config.py`, `backend/services/harness_flags.py`,
`backend/services/harness_flags_help.py`, `backend/tests/test_harness_flags.py`
(set `:467`), `backend/tests/test_harness_flags_requires.py` (mapa `:120`).

**Flags (nombres EXACTOS), defaults y excepciones:**

| Flag | type | Default | `requires=` | Excepción dura |
|---|---|---|---|---|
| `STACKY_EVOLUTION_OPTIMIZER_ENABLED` | bool | **ON** | `STACKY_EVOLUTION_CENTER_ENABLED` | ninguna — ON solo habilita el botón "Optimizar"; NADA corre sin click del operador y NADA se aplica sin aprobación (gates del 167) |
| `STACKY_EVOLUTION_OPTIMIZER_GENERATOR` | str | `"auto"` | `STACKY_EVOLUTION_CENTER_ENABLED` | ninguna (valores válidos `auto\|local\|runtime`, validados en código) |
| `STACKY_EVOLUTION_OPTIMIZER_VARIANTS` | int | `3` | `STACKY_EVOLUTION_CENTER_ENABLED` | ninguna (K por corrida; clamp en código 1..6) |
| `STACKY_EVOLUTION_OPTIMIZER_TOKEN_BUDGET` | int | `60000` | `STACKY_EVOLUTION_CENTER_ENABLED` | ninguna (presupuesto, no capacidad) |
| `STACKY_EVOLUTION_OPTIMIZER_MIN_MARGIN_PCT` | int | `2` | `STACKY_EVOLUTION_CENTER_ENABLED` | ninguna (margen mínimo en centésimas de score: 2 → 0.02) |

(G8: las 5 aristas apuntan al ROOT del 167 `STACKY_EVOLUTION_CENTER_ENABLED`,
profundidad 1. Los gates compuestos con OPTIMIZER/EVAL_HARNESS van EN CÓDIGO — §4.8.)

**Diff ilustrativo — `config.py`** (insertar inmediatamente DESPUÉS del bloque del
Plan 168 — ubicar por el literal `STACKY_EVAL_RUN_TOKEN_BUDGET`):

```python
    # ── Plan 169 — Optimizador evolutivo (serie auto-mejora recursiva 3/4) ──
    # generate->evaluate->select->archive sobre prompts de agentes. Default ON:
    # el flag solo habilita el boton "Optimizar"; correr es SIEMPRE un click
    # explicito del operador y aplicar exige aprobacion (gates del Plan 167).
    STACKY_EVOLUTION_OPTIMIZER_ENABLED: bool = os.getenv(
        "STACKY_EVOLUTION_OPTIMIZER_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # Generador de variantes: auto = modelo local si hay endpoint, si no el
    # runtime de agentes. Valores: auto | local | runtime.
    STACKY_EVOLUTION_OPTIMIZER_GENERATOR: str = os.getenv(
        "STACKY_EVOLUTION_OPTIMIZER_GENERATOR", "auto"
    ).strip().lower() or "auto"

    # K variantes por corrida (clamp 1..6 en el motor).
    STACKY_EVOLUTION_OPTIMIZER_VARIANTS: int = int(os.getenv(
        "STACKY_EVOLUTION_OPTIMIZER_VARIANTS", "3"
    ) or "3")

    # Presupuesto de tokens ESTIMADOS por corrida (generacion; las evaluaciones
    # tienen su propio presupuesto del Plan 168).
    STACKY_EVOLUTION_OPTIMIZER_TOKEN_BUDGET: int = int(os.getenv(
        "STACKY_EVOLUTION_OPTIMIZER_TOKEN_BUDGET", "60000"
    ) or "60000")

    # Margen minimo de mejora para emitir propuesta, en centesimas de score
    # (2 = el ganador debe superar al base por 0.02).
    STACKY_EVOLUTION_OPTIMIZER_MIN_MARGIN_PCT: int = int(os.getenv(
        "STACKY_EVOLUTION_OPTIMIZER_MIN_MARGIN_PCT", "2"
    ) or "2")
```

**`harness_flags.py` — 2 toques:** (a) `_CATEGORY_KEYS`: en la MISMA tupla de `:265`,
inmediatamente después de las 3 entradas del Plan 168 (ubicar por
`"STACKY_EVAL_RUN_TOKEN_BUDGET"`):

```python
        "STACKY_EVOLUTION_OPTIMIZER_ENABLED",         # Plan 169 — optimizador evolutivo
        "STACKY_EVOLUTION_OPTIMIZER_GENERATOR",       # Plan 169 — generador (auto/local/runtime)
        "STACKY_EVOLUTION_OPTIMIZER_VARIANTS",        # Plan 169 — K variantes por corrida
        "STACKY_EVOLUTION_OPTIMIZER_TOKEN_BUDGET",    # Plan 169 — presupuesto tokens por corrida
        "STACKY_EVOLUTION_OPTIMIZER_MIN_MARGIN_PCT",  # Plan 169 — margen minimo (centesimas)
```

(b) `FLAG_REGISTRY`: 5 `FlagSpec` inmediatamente DESPUÉS de los 3 del 168 (ubicar por
`key="STACKY_EVAL_RUN_TOKEN_BUDGET"`), `group="global"`:

```python
    FlagSpec(
        key="STACKY_EVOLUTION_OPTIMIZER_ENABLED",
        type="bool", default=True,
        label="Optimizador evolutivo de prompts",
        description="Habilita el botón 'Optimizar' del Centro de Evolución: genera variantes de un prompt de agente con mutación reflexiva, las evalúa con el arnés de fitness y emite una propuesta que vos aprobás. Nunca aplica nada solo.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_EVOLUTION_OPTIMIZER_GENERATOR",
        type="str", default="auto",
        label="Generador de variantes",
        description="Quién redacta las variantes: 'auto' usa el modelo local si está configurado y si no el runtime de agentes; 'local' exige modelo local; 'runtime' usa Codex/Claude/Copilot.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_EVOLUTION_OPTIMIZER_VARIANTS",
        type="int", default=3,
        label="Variantes por corrida (K)",
        description="Cuántas variantes genera y evalúa una corrida de optimización. Más variantes = más señal y más tokens.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_EVOLUTION_OPTIMIZER_TOKEN_BUDGET",
        type="int", default=60000,
        label="Presupuesto de tokens por corrida del optimizador",
        description="Tope de tokens estimados que una corrida puede gastar generando variantes. Al agotarse, la corrida se detiene y lo registra.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_EVOLUTION_OPTIMIZER_MIN_MARGIN_PCT",
        type="int", default=2,
        label="Margen mínimo de mejora (centésimas de score)",
        description="Cuánto debe superar la mejor variante al artefacto actual para que se emita una propuesta. 2 significa 0.02 puntos de score.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
```

**`harness_flags_help.py`:** 5 entradas `PlainHelp` (espejo del formato de las
entradas del 168, insertadas a continuación de ellas), lenguaje llano: qué es, efecto
ON, efecto OFF, ejemplo. La de `STACKY_EVOLUTION_OPTIMIZER_ENABLED` DEBE decir en
`on_effect` que "solo aparece el botón: nada corre ni se aplica sin tu click y tu
aprobación".

**Meta-tests:** en `_CURATED_DEFAULTS_ON` (`test_harness_flags.py:467`) agregar SOLO
la bool: `STACKY_EVOLUTION_OPTIMIZER_ENABLED` (G4 — ni la str ni las int van al set).
En `_REQUIRES_MAP_FROZEN` (`test_harness_flags_requires.py:120`) las 5 aristas:

```python
    "STACKY_EVOLUTION_OPTIMIZER_ENABLED": "STACKY_EVOLUTION_CENTER_ENABLED",
    "STACKY_EVOLUTION_OPTIMIZER_GENERATOR": "STACKY_EVOLUTION_CENTER_ENABLED",
    "STACKY_EVOLUTION_OPTIMIZER_VARIANTS": "STACKY_EVOLUTION_CENTER_ENABLED",
    "STACKY_EVOLUTION_OPTIMIZER_TOKEN_BUDGET": "STACKY_EVOLUTION_CENTER_ENABLED",
    "STACKY_EVOLUTION_OPTIMIZER_MIN_MARGIN_PCT": "STACKY_EVOLUTION_CENTER_ENABLED",
```

**Tests PRIMERO (TDD):** crear `backend/tests/test_optimizer_flags.py` (espejo
estructural de `tests/test_fitness_flags.py` del 168 F0). 8 casos:
1. `test_master_flag_en_registry` — FlagSpec `STACKY_EVOLUTION_OPTIMIZER_ENABLED`: `type=="bool"`, `default is True`, `requires=="STACKY_EVOLUTION_CENTER_ENABLED"`.
2. `test_generator_flag_str` — FlagSpec GENERATOR: `type=="str"`, `default=="auto"`.
3. `test_variants_y_budget_int` — VARIANTS `type=="int"` `default==3`; TOKEN_BUDGET `type=="int"` `default==60000`.
4. `test_margin_flag_int` — MIN_MARGIN_PCT `type=="int"`, `default==2`.
5. `test_las_5_estan_categorizadas` — las 5 keys en algún valor de `_CATEGORY_KEYS`.
6. `test_config_defaults` — env limpio: ENABLED True, GENERATOR "auto", VARIANTS 3, BUDGET 60000, MARGIN 2 (leer de `config.config`).
7. `test_aristas_requires_congeladas` — las 5 aristas en `_REQUIRES_MAP_FROZEN` apuntando al ROOT.
8. `test_help_presente` — el dict de `harness_flags_help` contiene las 5 keys.

**Comando (Git Bash):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_optimizer_flags.py tests/test_harness_flags.py tests/test_harness_flags_requires.py -q
```
**Criterio BINARIO:** los 3 archivos verdes (foto previa de fallos preexistentes de
`test_harness_flags.py`; criterio = sin regresión vs. foto).
**Flag:** las declaradas acá. **Runtimes:** N/A (declaración). **Trabajo del operador:** ninguno.

---

### F1 — Store del optimizador: `backend/services/evolution_optimizer_store.py`

**Objetivo (1 frase):** persistir corridas, archive, lecciones y frente Pareto bajo
`data_dir()/evolution/optimizer/` con lock, lecturas tolerantes y la función pura
`pareto_front`.
**Valor:** todo el estado del optimizador testeable con `tmp_path`; el archive
append-only es el "harness as primary artifact" del survey.

**Archivo a crear:** `backend/services/evolution_optimizer_store.py`

**Símbolos EXACTOS (además de los contratos §4.1-§4.4):**

```python
import runtime_paths                       # data_dir() en CADA llamada (testabilidad)
_OPTIMIZER_LOCK = threading.Lock()
_ARCHIVE_TEXT_MAX_CHARS = 20000
_PARETO_MAX = 8
_PARETO_PARENTS = 2
VALID_RUN_STATUSES = ("running", "completed", "no_improvement",
                      "stopped_budget", "cancelled", "error")
TERMINAL_RUN_STATUSES = frozenset({"completed", "no_improvement",
                                   "stopped_budget", "cancelled", "error"})
VALID_VERDICTS = ("base", "winner", "pareto", "dominated", "invalid")

def optimizer_root() -> Path               # runtime_paths.data_dir() / "evolution" / "optimizer"
def create_run(**fields) -> dict           # llena TODAS las claves de §4.2; status="running";
                                           # id="opt-"+uuid4().hex; valida status/generator.mode;
                                           # ValueError("invalid_run:<campo>") si falla
def get_run(run_id: str) -> dict | None
def list_runs(limit: int = 20) -> list[dict]        # más nuevo primero (por started_at)
def update_run(run_id: str, **patch) -> dict
    # Patch superficial de claves EXISTENTES de §4.2 (clave desconocida -> ValueError;
    # status fuera de VALID_RUN_STATUSES -> ValueError). KeyError("run_not_found") si no existe.
def append_step(run_id: str, text: str) -> None     # respeta el tope de 60 (§4.2)
def request_cancel(run_id: str) -> dict             # cancel_requested=True; KeyError si no existe;
                                                    # ValueError("run_not_running") si ya terminal
def any_run_running() -> bool                       # existe run con status=="running"
def append_archive_entry(entry: dict) -> dict       # valida §4.3 (kind/verdict en VALID_*;
                                                    # trunca artifact_text > _ARCHIVE_TEXT_MAX_CHARS a None);
                                                    # id="var-"+uuid4().hex si no viene
def read_archive(run_id=None, aspect_key=None, limit=50) -> list[dict]   # AND; más nuevo primero
def append_lesson(lesson: dict) -> dict             # id="les-"+uuid4().hex; valida outcome
def read_lessons_tail(aspect_key=None, limit=20) -> list[dict]           # más nuevo primero
def pareto_front(points: list[dict]) -> list[dict]  # PURA — dominancia §4.4, orden determinista
def get_pareto(aspect_key: str) -> list[dict]
def update_pareto(aspect_key: str, new_points: list[dict]) -> list[dict]
    # merge frente_previo + new_points -> pareto_front -> poda _PARETO_MAX (§4.4) -> persiste
def sample_parents(aspect_key: str, exclude_hash: str, rng) -> list[dict]
    # hasta _PARETO_PARENTS puntos del frente sin exclude_hash, con rng.sample;
    # frente vacío -> []
```

**Tests PRIMERO:** `backend/tests/test_optimizer_store.py`. Fixture común:
`monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)`. 12 casos:
1. `test_create_run_shape_completo` — todas las claves de §4.2 presentes; `status=="running"`, `proposal_id is None`.
2. `test_update_run_valida_claves` — patch de clave inexistente → `ValueError`; patch de `status="terminado"` (inválido) → `ValueError`.
3. `test_request_cancel` — sobre running → `cancel_requested is True`; sobre run terminal → `ValueError("run_not_running")`.
4. `test_any_run_running` — False con todo terminal; True con uno running.
5. `test_archive_append_only_y_lineage` — 1 base + 2 variantes con `parent_id` del base → `read_archive(run_id=…)` devuelve 3, los `parent_id` correctos, nada se puede borrar (no existe API de delete).
6. `test_archive_trunca_texto_grande` — `artifact_text` de 30000 chars → persistido `None`, `artifact_hash` presente.
7. `test_pareto_front_dominancia` — puntos `(score, cost)`: (0.9, 100), (0.8, 50), (0.7, 200) → frente == [(0.9,100), (0.8,50)] (el (0.7,200) dominado por ambos).
8. `test_pareto_front_empates` — dos puntos (0.8, 100) idénticos en ejes → AMBOS en el frente; orden final determinista por `variant_id`.
9. `test_pareto_none_score_excluido` — punto con `score=None` nunca entra.
10. `test_update_pareto_poda` — 10 puntos no dominados entre sí → quedan 8 (se caen los 2 de menor score).
11. `test_sample_parents_deterministico` — con `random.Random(42)` el sample es reproducible y excluye el `exclude_hash`.
12. `test_lecturas_tolerantes` — `runs.json` y `pareto.json` corruptos → `list_runs()==[]`, `get_pareto(...)==[]` sin excepción.

**Comando (Git Bash):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_optimizer_store.py -q
```
**Criterio BINARIO:** 12/12 verdes.
**Flag:** módulo puro — N/A. **Runtimes:** N/A. **Trabajo del operador:** ninguno.

---

### F2 — Generador de variantes: `backend/services/variant_generator.py` + agente mutador

**Objetivo (1 frase):** una función única `generate(...)` que produce el texto de una
variante vía el modelo LOCAL o vía el RUNTIME de agentes (Codex/Claude/Copilot) con el
patrón one-shot del Documentador, con fallback declarado por combinación.
**Valor:** paridad real de los 3 runtimes + camino barato local, sin caminos nuevos de
invocación.

**Archivos a crear (2):** `backend/services/variant_generator.py`,
`backend/agents/evolution_mutator.py`.
**Archivos a editar (2):** `backend/agents/__init__.py` (2 líneas),
`backend/services/claude_code_cli_runner.py` (1 línea + comentario).

**`agents/evolution_mutator.py` (espejo estructural de `agents/incident_dev.py:10-27`):**

```python
from .base import BaseAgent


class EvolutionMutatorAgent(BaseAgent):
    type = "evolution_mutator"
    name = "Evolution Mutator"
    icon = "🧬"
    description = "Genera variantes mejoradas de un artefacto de texto para el optimizador evolutivo"
    inputs_hint = ["artefacto base", "criticas de la ultima evaluacion", "lecciones previas"]
    outputs_hint = ["una variante completa entre marcadores <<<VARIANTE>>>...<<<FIN_VARIANTE>>>"]
    default_blocks: list[str] = []

    def system_prompt(self) -> str:
        from services.variant_generator import _MUTATOR_SYSTEM
        return _MUTATOR_SYSTEM
```

**`agents/__init__.py` — 2 toques (anclar por contenido):** tras
`from .incident_dev import IncidentDevAgent` (`:10`) agregar
`from .evolution_mutator import EvolutionMutatorAgent`; en la lista del `registry`
(`:16-29`), tras la entrada `IncidentDevAgent(), # Plan 166 F4 …` (`:27`) agregar
`EvolutionMutatorAgent(),  # Plan 169 — generador de variantes del optimizador`.

**`claude_code_cli_runner.py` — 1 toque:** en `_ONE_SHOT_ADO_IDS = frozenset({-1, -7, -8})`
(`:218`) agregar `-9` → `frozenset({-1, -7, -8, -9})`, y extender el comentario R1.2
(`:207-215`) con la línea:
`#   -9 = Optimizador evolutivo (Plan 169, variant_generator._OPTIMIZER_ADO_ID): mutador one-shot en background.`
(Sin esto, el run del mutador bajo Claude CLI queda esperando input hasta el timeout
de 1800 s — exactamente el bug que el comentario R1.2 documenta para -7/-8. En
`codex_cli_runner.py` NO hay cambio: no existe mecanismo equivalente, el proceso
termina solo — verificado. En `github_copilot` NO hay cambio: no usa sesión
conversacional persistente.)

**`variant_generator.py` — símbolos EXACTOS:**

```python
from config import config as _cfg          # G1
_MUTATOR_SYSTEM = <literal §4.5>
_OPTIMIZER_ADO_ID = -9
_GENERATE_TIMEOUT_S = 1800                 # mismo anti-zombie que doc_documenter.py:171
VALID_RUNTIMES = ("github_copilot", "claude_code_cli", "codex_cli")

def _estimate_tokens(text: str) -> int     # max(1, len(text) // 4)
def extract_block(text: str, start_marker: str, end_marker: str) -> str | None
    # primer start_marker y el PRIMER end_marker posterior; strip(); sin par -> None
def resolve_generator_mode() -> tuple[str, bool]
    # flag = getattr(_cfg, "STACKY_EVOLUTION_OPTIMIZER_GENERATOR", "auto") normalizada
    # "local"   -> ("local", bool(getattr(_cfg, "LOCAL_LLM_ENDPOINT", "")))
    # "runtime" -> ("runtime", True)
    # "auto"/otro -> ("local", True) si LOCAL_LLM_ENDPOINT no vacío, sino ("runtime", True)
    # Devuelve (mode, ready).
def generator_model_for(mode: str, runtime: str | None) -> str
    # "local" -> str(getattr(_cfg, "LOCAL_LLM_MODEL", "") or "local")
    # "runtime" -> f"runtime:{runtime}"  (NUNCA coincide casefold con el juez local ->
    #              el 168 no marca self_judge_risk espurio; para "local" SÍ coincide y
    #              el 168 aplica su SELF_JUDGE_MULTIPLIER — comportamiento DESEADO)
def _ensure_optimizer_ticket() -> int
    # Espejo EXACTO de doc_documenter._ensure_documenter_ticket (:307-334) con:
    # ado_id=_OPTIMIZER_ADO_ID, stacky_project_name="stacky-evolution",
    # project="stacky-evolution", title="[Optimizador] mutacion de artefactos",
    # work_item_type="Task", ado_state="Active", external_id=-ticket.id.
def _wait_and_read_output(execution_id: int, timeout_s: int = _GENERATE_TIMEOUT_S) -> str
    # Espejo EXACTO de doc_documenter._wait_and_read_output (:337-361): poll 1.0 s de
    # AgentExecution.status hasta {"completed","failed","cancelled","error"} o timeout;
    # devuelve output ("" si vacío/timeout); nunca crashea.
def generate(*, user_prompt: str, mode: str, runtime: str | None,
             on_step=None) -> dict
    # Devuelve SIEMPRE el dict:
    # {"text": str|None, "lesson": str|None, "flag_suggestion": dict|None,
    #  "model": str, "tokens_est_in": int, "tokens_est_out": int, "error": str|None}
    # mode == "local":
    #   from copilot_bridge import invoke_local_llm   (import LAZY)
    #   resp = invoke_local_llm(agent_type="evolution_mutator", system=_MUTATOR_SYSTEM,
    #                           user=user_prompt, on_log=lambda level, msg: None,
    #                           execution_id=None, model=None)
    #   RuntimeError -> {"error": str(exc), ...} (degradación declarada)
    #   raw = resp.text
    # mode == "runtime":
    #   from services import incident_dev_context  # NO: ver ensure abajo
    #   ensure_evolution_mutator_agent_file()
    #   import agent_runner
    #   execution_id = agent_runner.run_agent(
    #       agent_type="evolution_mutator", ticket_id=_ensure_optimizer_ticket(),
    #       context_blocks=[{"id": "mutation", "kind": "raw-conversation",
    #                        "title": "Pedido de mutacion",
    #                        "content": user_prompt,
    #                        "source": {"type": "evolution_optimizer"}}],
    #       user="optimizer", runtime=runtime,
    #       vscode_agent_filename="EvolutionMutator.agent.md",
    #       system_prompt_override=_MUTATOR_SYSTEM,
    #       use_few_shot=False, use_anti_patterns=False, work_item_type="Task")
    #   (espejo EXACTO del call del Documentador doc_documenter.py:383-395 y del
    #    resolutor api/agents.py:1152-1164)
    #   Exception -> {"error": f"runtime_launch_failed: {exc}", ...}
    #   raw = _wait_and_read_output(execution_id); "" -> error "runtime_sin_output"
    # Común: text = extract_block(raw, "<<<VARIANTE>>>", "<<<FIN_VARIANTE>>>");
    #   None -> error "sin_marcador_variante". lesson = extract_block(..., LECCION).
    #   flag_suggestion = parse JSON tolerante del bloque SUGERENCIA_FLAG (no parsea
    #   -> None). tokens_est_in/_out con _estimate_tokens(user_prompt)/(raw).
    #   model = generator_model_for(mode, runtime).
def ensure_evolution_mutator_agent_file() -> Path
    # Espejo EXACTO de incident_dev_context.ensure_incident_dev_agent_file (:97-118):
    # dest = runtime_paths.stacky_agents_dir() / "EvolutionMutator.agent.md";
    # si existe NO tocar; si no, copiar de backend/agents/EvolutionMutator.agent.md
    # (crearlo en el repo con el frontmatter mínimo + _MUTATOR_SYSTEM como cuerpo);
    # si tampoco está (deploy frozen, G15) escribir _AGENT_TEMPLATE_MD embebido.
```

NOTA de diseño (anti confusión del implementador): el `.agent.md` del mutador vive en
el dir RUNTIME (`stacky_agents_dir()`, gitignorado) SOLO para que los runtimes CLI
puedan cargarlo (`api/agents.py:1135-1137` exige `vscode_agent_filename` para CLI); su
contenido NO es el prompt-fuente (el fuente es `_MUTATOR_SYSTEM`, pasado además como
`system_prompt_override`). Y aunque quede en la misma carpeta que los targets, la
`_TARGET_DENYLIST` (§4.6) lo excluye de la optimización — el 168 sí puede sembrarle
casos seed (inofensivo: es medición, no mutación).

**Tests PRIMERO:** `backend/tests/test_optimizer_generator.py` (fixtures:
`data_dir→tmp_path`; `monkeypatch.setattr(runtime_paths, "stacky_agents_dir", …)` a
tmp; `copilot_bridge.invoke_local_llm` y `agent_runner.run_agent` SIEMPRE mockeados;
`variant_generator._wait_and_read_output` mockeado en los casos runtime). 10 casos:
1. `test_extract_block` — con marcadores → contenido stripped; sin end marker → None; texto vacío → None.
2. `test_resolve_generator_mode_auto` — con `LOCAL_LLM_ENDPOINT` (monkeypatch `_cfg`) → ("local", True); sin endpoint → ("runtime", True).
3. `test_resolve_generator_mode_local_sin_endpoint` — flag "local" sin endpoint → ("local", False) (el caller decide 409 — KPI-5).
4. `test_generate_local_ok` — mock del bridge devuelve `<<<VARIANTE>>>\nnuevo\n<<<FIN_VARIANTE>>>\n<<<LECCION>>>\ncambie X\n<<<FIN_LECCION>>>` → text=="nuevo", lesson=="cambie X", error None, model==LOCAL_LLM_MODEL.
5. `test_generate_local_runtime_error_degrada` — bridge lanza RuntimeError → error no nulo, text None.
6. `test_generate_sin_marcador` — respuesta prosa sin marcadores → error=="sin_marcador_variante".
7. `test_generate_runtime_llama_run_agent` — mock `run_agent` con captura de kwargs → `agent_type=="evolution_mutator"`, `runtime` passthrough, `vscode_agent_filename=="EvolutionMutator.agent.md"`, `system_prompt_override==_MUTATOR_SYSTEM`; `_wait_and_read_output` mockeado con marcadores → text OK; model==f"runtime:{runtime}".
8. `test_generate_runtime_launch_failed` — `run_agent` lanza → error empieza con "runtime_launch_failed".
9. `test_flag_suggestion_parse` — bloque SUGERENCIA_FLAG con JSON válido → dict con flag/value/razon; JSON roto → None.
10. `test_one_shot_incluye_menos_nueve` — `from services.claude_code_cli_runner import _ONE_SHOT_ADO_IDS; assert -9 in _ONE_SHOT_ADO_IDS` y `assert variant_generator._OPTIMIZER_ADO_ID == -9` (espejo de `test_plan131_run_incident.py:187-189`).

**Comando (Git Bash):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_optimizer_generator.py -q
```
**Criterio BINARIO:** 10/10 verdes.
**Flag:** `STACKY_EVOLUTION_OPTIMIZER_GENERATOR` (leída por `resolve_generator_mode`).
**Impacto por runtime + fallback (tabla congelada):**

| Generador efectivo | Codex CLI | Claude Code CLI | GitHub Copilot | Fallback |
|---|---|---|---|---|
| `local` (default con endpoint) | idéntico (no toca el runtime) | idéntico | idéntico | sin `LOCAL_LLM_ENDPOINT` → la corrida NO arranca: 409 `generator_unavailable` declarado en panel (KPI-5) |
| `runtime` | `run_agent(runtime="codex_cli")` — proceso termina solo | `run_agent(runtime="claude_code_cli")` — one-shot por `-9 ∈ _ONE_SHOT_ADO_IDS` | `run_agent(runtime="github_copilot")` — camino síncrono del bridge | lanzamiento falla → variante `invalid` con `invalid_reason="runtime_launch_failed…"`; la corrida sigue con la próxima variante |

**Trabajo del operador:** ninguno (el agente mutador y su ticket se materializan solos).

---

### F3 — Motor de la corrida: `backend/services/evolution_optimizer.py`

**Objetivo (1 frase):** el loop generate→evaluate→select→archive de UNA corrida, con
mutación reflexiva, STOP conditions duras, emisión gateada de la propuesta y registro
completo en el archive.
**Valor:** el corazón del plan; convierte fitness (168) + gobernanza (167) en mejora
sistemática.

**Archivo a crear:** `backend/services/evolution_optimizer.py`

**Símbolos EXACTOS:**

```python
from config import config as _cfg          # G1
_SUGGESTABLE_FLAGS = frozenset({"LOCAL_LLM_MODEL"})     # §4.7 — allowlist-only
_TARGET_DENYLIST = frozenset({"EvolutionMutator.agent.md"})  # §4.6
_MAX_CRITIQUES = 6
_MAX_FAILED_CHECKS = 6
_MAX_LESSONS = 10
_PARENT_HEAD_LINES = 40

def _now_iso() -> str
def _estimate_tokens(text: str) -> int     # max(1, len(text) // 4)
def _margin() -> float                     # §4.6
def _variants_planned() -> int             # clamp(int(getattr(_cfg, "STACKY_EVOLUTION_OPTIMIZER_VARIANTS", 3)), 1, 6)
def _budget() -> int                       # int(getattr(_cfg, "STACKY_EVOLUTION_OPTIMIZER_TOKEN_BUDGET", 60000))
def list_targets() -> list[dict]
    # glob tolerante de case_store.prompts_dir()/*.agent.md (G15), menos
    # _TARGET_DENYLIST, orden alfabético; shape de §4.8 GET /targets.
def read_target_text(target_ref: str) -> str
    # Allowlist ANTI path-traversal espejo EXACTO del guard del 167 F2 / 168 F4:
    # resolver (case_store.prompts_dir() / target_ref); exigir sufijo ".agent.md" y
    # prefijo prompts_dir() resuelto; fuera -> ValueError("target_fuera_de_allowlist");
    # inexistente -> KeyError("target_not_found"). Devuelve read_text(encoding="utf-8").
def build_mutation_prompt(*, base_text, base_score, base_cost, critiques,
                          failed_checks, lessons, parents, k, total) -> str
    # Arma el user prompt LITERAL de §4.5 (secciones vacías se omiten con encabezado;
    # critiques cap _MAX_CRITIQUES; failed_checks cap _MAX_FAILED_CHECKS; lessons cap
    # _MAX_LESSONS; parents ya vienen ≤ _PARETO_PARENTS con las primeras
    # _PARENT_HEAD_LINES líneas).
def collect_failed_checks(per_case: list[dict]) -> list[str]
    # Por cada caso con checks: por cada check ok=False ->
    # f"{case_title}: {kind} -> {detail}" (formato §4.5).
def start_run(*, target_ref: str, runtime: str | None, use_judge: bool) -> dict
    # Validaciones SÍNCRONAS (antes del thread): target en list_targets() (si no ->
    # KeyError("target_not_found")); store.any_run_running() -> RuntimeError("optimizer_already_running");
    # (mode, ready) = variant_generator.resolve_generator_mode(); not ready ->
    # RuntimeError("generator_unavailable"); runtime normalizado: None -> "github_copilot"
    # (default de agent_runner.py:94) si mode=="runtime", validado contra VALID_RUNTIMES.
    # run = store.create_run(aspect_key=…, target_ref=…, generator={...},
    #                        use_judge=use_judge, variants_planned=_variants_planned(),
    #                        margin_used=_margin(),
    #                        budget={"limit_tokens": _budget(), ...}).
    # _start_run_async(run["id"], ...) y devuelve el run (status "running").
def _start_run_async(run_id: str, **kwargs) -> None
    # threading.Thread(target=_run_optimization_sync, args=(run_id,), kwargs=kwargs,
    #                  daemon=True).start()
    # (precedente doc_documenter.py:705; thread POR corrida, muere al terminar;
    #  en tests SIEMPRE se monkeypatchea a llamada síncrona — G14).
def _run_optimization_sync(run_id: str, *, rng=None) -> dict
    # EL LOOP (todo en try/except global -> status "error" + error=str(exc)):
    # 1) run = store.get_run(run_id); target_text = read_target_text(target_ref);
    #    base_cost = _estimate_tokens(target_text).
    # 2) BASE: res = fitness_service.evaluate_candidate(aspect_key, target_text,
    #        case_filter=None, generator_model=None, use_judge=use_judge)
    #    base_entry = store.append_archive_entry(kind="base", verdict="base",
    #        fitness={score,passed,deterministic_gate,eval_ref}, cost_proxy=base_cost,
    #        critique_summary=<join critiques>, artifact_text=target_text, ...)
    #    store.update_run(run_id, base={"variant_id","score","cost_proxy","eval_ref"});
    #    append_step "base evaluado: score {…}".
    #    base score None -> cerrar "no_improvement" con step "base sin score evaluable" (§4.6).
    # 3) Señal reflexiva: critiques = res["critiques"]; failed = collect_failed_checks(res["per_case"]);
    #    lessons = store.read_lessons_tail(aspect_key, _MAX_LESSONS);
    #    parents = store.sample_parents(aspect_key, base_hash, rng or random.Random())
    #    (el texto de cada parent sale de read_archive por variant_id; sin texto -> se omite).
    # 4) LOOP k in 1.._variants_planned():
    #    a) store.get_run(run_id)["cancel_requested"] -> status "cancelled", step, break.
    #    b) tokens_gastados + _estimate_tokens(prompt siguiente) > limit_tokens ->
    #       budget.exhausted=True, step "presupuesto agotado", break.
    #    c) prompt = build_mutation_prompt(..., k=k, total=K)
    #    d) gen = variant_generator.generate(user_prompt=prompt, mode=…, runtime=…)
    #       sumar tokens_est_in/out del gen al budget del run.
    #       gen["error"] -> archive entry verdict="invalid" invalid_reason=gen["error"],
    #       step, continue.
    #    e) sha256(gen["text"]) == sha256(base) -> invalid "variante_identica", continue.
    #    f) fit = fitness_service.evaluate_candidate(aspect_key, gen["text"],
    #           case_filter=None,
    #           generator_model=variant_generator.generator_model_for(mode, runtime),
    #           use_judge=use_judge)
    #    g) entry = append_archive_entry(kind="variant", parent_id=base_entry["id"],
    #           fitness={...}, cost_proxy=_estimate_tokens(gen["text"]),
    #           critique_summary=…, mutation_lesson=gen["lesson"],
    #           generator_model=…, artifact_text=gen["text"])
    #    h) si gen["lesson"]: store.append_lesson(outcome/delta según §4.3).
    #    i) primera flag_suggestion válida (§4.7): validar contra _SUGGESTABLE_FLAGS;
    #       válida -> create_proposal flag_change (§4.7) una sola vez por corrida;
    #       inválida -> step "sugerencia de flag descartada: …".
    #    j) update_run(variants_done=k, steps…).
    # 5) SELECT: candidatos válidos -> front = store.pareto_front(...);
    #    marcar verdicts: winner / pareto / dominated (update de las entries NO:
    #    archive es append-only -> el verdict se decide ANTES de appendear? NO:
    #    las entries de variantes se appendean en (g) con verdict PROVISORIO
    #    "dominated"; al cerrar, la selección re-appendea NADA: el verdict final
    #    de cada variante se registra en el RUN (steps + winner) y en pareto.json;
    #    para no romper el append-only, §4.3 fija: el verdict de la ENTRY es el
    #    computado AL CIERRE de la corrida, así que (g) se difiere: las entries de
    #    variantes se appendean TODAS JUNTAS en este paso 5, ya con su verdict final.
    #    (Los datos viven en memoria durante el loop; el run.steps da el progreso.)
    # 6) EMITIR según §4.6 (margen + gate determinista):
    #    sí -> create_proposal + inject_proposal_fitness before/after;
    #          update_run(proposal_id=…, parent_proposal_id=…, winner=…, status="completed")
    #    no -> status = "stopped_budget" si budget.exhausted sino "no_improvement"
    #          (cancelled ya salió en 4a); winner=… si hubo.
    # 7) store.update_pareto(aspect_key, base + variantes válidas) — salvo status "error".
    # 8) update_run(finished_at=_now_iso()). Devuelve el run final.
```

Aclaración NORMATIVA del paso 5 (para que el modelo menor no dude): durante el loop
las variantes viven en una lista local `pending_entries`; `archive.jsonl` recibe la
entry del BASE en el paso 2 y TODAS las entries de variantes JUNTAS en el paso 5, cada
una ya con su `verdict` definitivo (`winner`/`pareto`/`dominated`/`invalid`). Así el
archive queda estrictamente append-only sin updates. El progreso en vivo lo dan
`run.steps` y `variants_done`, no el archive.

**Tests PRIMERO:** `backend/tests/test_optimizer_engine.py` (fixtures:
`data_dir→tmp_path`; `case_store.prompts_dir` → tmp con 2 `.agent.md` sintéticos
(`Developer.agent.md` y `EvolutionMutator.agent.md`); `fitness_service.evaluate_candidate`
→ mock con scores programables por texto; `variant_generator.generate` → mock que
devuelve variantes sintéticas; SIN threads: llamar `_run_optimization_sync` directo —
G14; el 167/168 reales en el árbol para `create_proposal`/`inject_proposal_fitness`).
14 casos:
1. `test_list_targets_excluye_denylist` — con los 2 archivos → targets == solo `Developer.agent.md` (KPI-1 parcial).
2. `test_build_mutation_prompt_reflexivo` — el prompt contiene el texto base, las 2 críticas del mock, el check fallado, la lección previa y el resumen del padre (**KPI-2**).
3. `test_build_mutation_prompt_omite_secciones_vacias` — sin críticas/lecciones/padres → esos encabezados NO aparecen.
4. `test_corrida_feliz_emite_propuesta` — base 0.60, variantes 0.55/0.70/0.65, margen 0.02 → propuesta emitida `origin=="optimizer"`, `initial_status=="pending_review"` real en `evolution_store`, `proposed_content` == texto de la 0.70, `fitness_before.score==0.6` y `fitness_after.score==0.7` en la propuesta (shape 167 §4.7), run `completed` (**KPI-1/KPI-3**).
5. `test_margen_no_alcanzado_no_emite` — base 0.69, mejor variante 0.70, margen 0.02 → `no_improvement`, `evolution_store.list_proposals()` NO crece (**KPI-3**).
6. `test_gate_determinista_bloquea` — mejor variante con `deterministic_gate=="failed"` → NO se emite aunque el score supere el margen.
7. `test_seleccion_pareto_empate_score` — dos variantes score 0.8, costos 200 y 100 → winner la de costo 100.
8. `test_stop_presupuesto` — budget chico (monkeypatch `_cfg`) → corta antes de K, `budget.exhausted is True`, status `stopped_budget` (**KPI-4**).
9. `test_stop_cancelacion` — `request_cancel` tras la 1ª variante (hook en el mock del generate) → status `cancelled`, sin propuesta (**KPI-4**).
10. `test_variante_invalida_no_rompe` — generate devuelve error en la 2ª → entry `invalid` con `invalid_reason`, la corrida sigue y completa.
11. `test_archive_lineage_y_verdicts` — tras la corrida feliz: 1 entry base + 3 variantes, `parent_id` == id del base, verdicts {winner, pareto/dominated} coherentes con los scores, `generator_model` presente en variantes.
12. `test_congelador_denylist_y_hotl` — `"EvolutionMutator.agent.md" in _TARGET_DENYLIST` **y** `evolution_apply._HOTL_ALLOWED_ASPECTS == frozenset({"knowledge_rag"})` (import real del 167 — el optimizador ni aparece) (**KPI-1**).
13. `test_congelador_suggestable_flags` — `_SUGGESTABLE_FLAGS == frozenset({"LOCAL_LLM_MODEL"})` y ningún elemento empieza con `"STACKY_EVOLUTION"` ni `"STACKY_EVAL"` (§4.7).
14. `test_parent_proposal_id_lineage` — segunda corrida sobre el mismo target que también emite → su propuesta tiene `parent_proposal_id` == id de la primera.

**Comando (Git Bash):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_optimizer_engine.py -q
```
**Criterio BINARIO:** 14/14 verdes.
**Flag:** las 5 de F0 (el gate HTTP va en F4).
**Impacto por runtime:** idéntico en los 3 (el motor es backend; el único punto
runtime-dependiente es F2). **Fallback:** generador caído por variante → entry
`invalid` y la corrida sigue; fitness caído (excepción del 168) → status `error` con
detalle (el 168 ya degrada el juez internamente, así que esto solo pasa por bugs
reales). **Trabajo del operador:** ninguno.

---

### F4 — API Flask: `backend/api/evolution_optimizer.py` + registro

**Objetivo (1 frase):** exponer los contratos §4.8 gateados por flag, con health
siempre-200 y el POST que lanza el thread de la corrida.
**Valor:** el panel (F5) tiene su superficie; el operador tiene cancelación.

**Pre-check:** exige `api/evolution.py` (167 F4) y `api/evolution_fitness.py` (168 F5)
en el árbol.

**Archivo a crear:** `backend/api/evolution_optimizer.py`

```python
from flask import Blueprint, jsonify, request
from config import config as _cfg                       # G1

bp = Blueprint("evolution_optimizer", __name__, url_prefix="/evolution")

def _optimizer_enabled() -> bool:
    return bool(getattr(_cfg, "STACKY_EVOLUTION_CENTER_ENABLED", False)) and \
           bool(getattr(_cfg, "STACKY_EVOLUTION_OPTIMIZER_ENABLED", False))

def _harness_enabled() -> bool:
    return bool(getattr(_cfg, "STACKY_EVOLUTION_CENTER_ENABLED", False)) and \
           bool(getattr(_cfg, "STACKY_EVAL_HARNESS_ENABLED", False))

def _disabled_resp():
    return jsonify({"ok": False, "error": "optimizer_disabled",
                    "message": "El optimizador evolutivo está deshabilitado (STACKY_EVOLUTION_OPTIMIZER_ENABLED)."}), 404
```

Rutas EXACTAS de §4.8 (imports de `services` LAZY dentro de cada handler — patrón del
167 F4). Mapeos de error congelados: `KeyError("target_not_found")` → 404
`target_not_found`; `KeyError("run_not_found")` → 404 `run_not_found`;
`RuntimeError("optimizer_already_running")` → 409; `RuntimeError("generator_unavailable")`
→ 409 con el message literal de §4.8; `_harness_enabled()` False en el POST → 409
`fitness_harness_disabled`; `ValueError("run_not_running")` → 409;
`ValueError("invalid_payload…")` / runtime inválido → 400 `invalid_payload`. El POST
`/optimizer/run` responde **202** con el run en estado `running` (el thread ya quedó
lanzado por `start_run`).

**Registro — `backend/api/__init__.py` (2 líneas, espejo del 168 F5):** tras la línea
del 168 `from .evolution_fitness import bp as evolution_fitness_bp` agregar
`from .evolution_optimizer import bp as evolution_optimizer_bp  # Plan 169 — optimizador evolutivo`
y tras `api_bp.register_blueprint(evolution_fitness_bp)` agregar
`api_bp.register_blueprint(evolution_optimizer_bp)  # Plan 169 — /api/evolution/optimizer/...`.
(Tres blueprints con el MISMO url_prefix `/evolution` y nombres distintos: válido en
Flask — precedente explícito del 168 F5; las rutas `/optimizer/*` no colisionan con
las del 167 ni las `/fitness/*` del 168.)

**Tests PRIMERO:** `backend/tests/test_optimizer_endpoints.py` (fixtures
`app_flag_off`/`app_flag_on` espejo del patrón del 168 F5 — attr
`STACKY_EVOLUTION_OPTIMIZER_ENABLED`, con CENTER y EVAL_HARNESS ON en ambos; +
`data_dir→tmp_path` + `case_store.prompts_dir` → tmp con 1 `.agent.md`; +
monkeypatch de `evolution_optimizer._start_run_async` a ejecución SÍNCRONA con
generator/fitness mockeados — G14). 12 casos:
1. `test_health_200_flag_off` — 200 y `flag_enabled False`.
2. `test_targets_404_flag_off` — `GET /api/evolution/optimizer/targets` → 404 `optimizer_disabled` (**KPI-6**).
3. `test_targets_lista` — flag ON → 200, el target sintético presente con `aspect_key` correcto.
4. `test_run_target_inexistente_404` — POST con `target_ref="NoExiste.agent.md"` → 404 `target_not_found`.
5. `test_run_generator_unavailable_409` — flag GENERATOR="local" sin endpoint (monkeypatch `_cfg`) → 409 `generator_unavailable` con el message literal (**KPI-5**).
6. `test_run_harness_off_409` — `STACKY_EVAL_HARNESS_ENABLED` False → 409 `fitness_harness_disabled`.
7. `test_run_feliz_202_y_get` — POST → 202 con `run.status` terminal (async mockeado síncrono) y `GET /runs/<rid>` lo devuelve.
8. `test_run_already_running_409` — sembrar un run `running` en el store → POST → 409 `optimizer_already_running`.
9. `test_cancel` — run running → POST cancel → 200 y `cancel_requested True`; run terminal → 409 `run_not_running`; inexistente → 404.
10. `test_runs_tail_y_archive` — corrida completada → `GET /runs` la lista; `GET /archive?run_id=` devuelve base+variantes.
11. `test_lessons_y_pareto` — `GET /lessons?aspect_key=` y `GET /pareto?aspect_key=` con datos sembrados; `GET /pareto` sin aspect_key → 400 `aspect_key_requerido`.
12. `test_rutas_sin_doble_prefijo` — el url_map contiene `/api/evolution/optimizer/health` y NO `/api/api/evolution/optimizer/health` (centinela, patrón `test_plan74_routes_registered.py`).

**Comando (Git Bash):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_optimizer_endpoints.py -q
```
**Criterio BINARIO:** 12/12 verdes.
**Flag:** `STACKY_EVOLUTION_OPTIMIZER_ENABLED` (+ master 167) — gating 404 testeado.
**Runtimes:** N/A (API local). **Trabajo del operador:** ninguno.

---

### F5 — Panel: sección "Optimizador" en `EvolutionCenterPage` + modelo puro TS

**Objetivo (1 frase):** botón "Optimizar" por target, vista de corrida con progreso
(polling acotado SOLO en corrida activa), lineage del archive, lecciones y frente —
como sección nueva del panel del 167, espejo del patrón de extensión del 168 F6.
**Valor:** el loop completo usable con 1 click; las propuestas emitidas aparecen en la
bandeja NORMAL del 167 (cero UI nueva para aprobar).

**Pre-check:** exige `frontend/src/pages/EvolutionCenterPage.tsx` (167 F6) y
`frontend/src/evolution/FitnessSection.tsx` (168 F6) en el árbol.

**Archivos a crear (3):** `frontend/src/evolution/optimizerModel.ts`,
`frontend/src/evolution/OptimizerSection.tsx`,
`frontend/src/evolution/OptimizerSection.module.css`.
**Archivos a editar (2):** `frontend/src/api/endpoints.ts` (namespace nuevo
`EvolutionOptimizer`, espejo del namespace `EvolutionFitness` del 168 F6, con métodos:
`health()`, `targets()`, `run(targetRef, runtime, useJudge)`, `cancel(runId)`,
`getRun(runId)`, `runs(limit)`, `archive(q)`, `lessons(aspectKey, limit)`,
`pareto(aspectKey)` — cada uno `fetch` a la ruta EXACTA de §4.8 con el estilo
`{ok, status, data}` del 167 F5); `frontend/src/pages/EvolutionCenterPage.tsx`
(2 toques quirúrgicos, anclar por contenido: (1) import de `OptimizerSection`;
(2) render de `<OptimizerSection />` como ÚLTIMA sección de la página,
inmediatamente DESPUÉS de `<FitnessSection />` del 168).

**`optimizerModel.ts` — símbolos EXACTOS (funciones puras, testeables sin RTL/jsdom):**

```typescript
export type RunStatus = "running" | "completed" | "no_improvement" | "stopped_budget" | "cancelled" | "error";
export type Verdict = "base" | "winner" | "pareto" | "dominated" | "invalid";
export interface OptimizerTargetDto { target_ref: string; aspect_key: string; cases_enabled: number; last_score: number | null; }
export interface OptimizationRunDto { id: string; aspect_key: string; target_ref: string; status: RunStatus; error: string | null; cancel_requested: boolean; generator: { mode: string; runtime: string | null; model: string | null }; variants_planned: number; variants_done: number; base: { score: number | null; cost_proxy: number } | null; winner: { score: number | null; cost_proxy: number } | null; proposal_id: string | null; margin_used: number; budget: { limit_tokens: number; tokens_est_in: number; tokens_est_out: number; exhausted: boolean }; steps: { ts: string; text: string }[]; started_at: string; finished_at: string | null; }
export interface ArchiveEntryDto { id: string; run_id: string; parent_id: string | null; kind: "base" | "variant"; verdict: Verdict; invalid_reason: string | null; fitness: { score: number | null; deterministic_gate: string } | null; cost_proxy: number; mutation_lesson: string | null; generator_model: string | null; created_at: string; }

export const RUN_POLL_MS = 2000;          // §F5: intervalo del setTimeout encadenado
export const RUN_POLL_MAX = 900;          // tope duro: 900 * 2 s = 30 min

export function runStatusTone(s: RunStatus): "success" | "warning" | "danger" | "info" | "neutral"
  // running->"info"; completed->"success"; no_improvement->"neutral";
  // stopped_budget->"warning"; cancelled->"neutral"; error->"danger".
export function runStatusLabel(s: RunStatus): string
  // running->"Corriendo"; completed->"Propuesta emitida"; no_improvement->"Sin mejora suficiente";
  // stopped_budget->"Presupuesto agotado"; cancelled->"Cancelada"; error->"Error".
export function verdictTone(v: Verdict): "success" | "warning" | "danger" | "info" | "neutral"
  // winner->"success"; pareto->"info"; base->"neutral"; dominated->"neutral"; invalid->"danger".
export function verdictLabel(v: Verdict): string
  // base->"Base"; winner->"Ganadora"; pareto->"Frente Pareto"; dominated->"Dominada"; invalid->"Inválida".
export function generatorLabel(g: { mode: string; runtime: string | null }): string
  // mode "local"->"Modelo local"; mode "runtime"->`Runtime: ${runtime}`; otro->mode.
export function isTerminal(s: RunStatus): boolean       // s !== "running"
export function lineageRows(entries: ArchiveEntryDto[]): { entry: ArchiveEntryDto; depth: number }[]
  // Orden para lista indentada: bases (kind==="base") por created_at ASC, y debajo de
  // cada base sus hijas (parent_id === base.id) por created_at ASC con depth 1;
  // huérfanas al final con depth 0. PURA, no muta el input.
export function improvementDisplay(base: number | null, winner: number | null): string
  // ambos numéricos -> `${base.toFixed(2)} → ${winner.toFixed(2)}`; si falta alguno -> "—".
  // (score 0..1 con toFixed — NO usar Intl, ratchet del 161.)
```

**`OptimizerSection.tsx` (estructura; TODO estilo en el `.module.css` — G6; polling
SOLO de corrida activa — G9):**
- On-mount: `EvolutionOptimizer.health()`; si `flag_enabled === false` → `return null`.
  Si ON: `Promise.all([targets(), runs(10)])` con estados `loading` (`SkeletonList`),
  `error` (banner + "Reintentar"), `data`. Si `health.harness_enabled === false`, chip
  informativo "Arnés de fitness deshabilitado — el optimizador no puede correr" y
  botones "Optimizar" deshabilitados (estado visible, no error mudo).
- **Targets** (`SectionHeader` "Optimizador evolutivo" + tabla): `target_ref`,
  `aspect_key`, "casos: {cases_enabled}", "último score: {last_score ?? '—'}", botón
  `Button` "Optimizar". Si `health.generator_mode === "runtime"`, mostrar además un
  `Field`+`Select` "Runtime generador" con opciones EXACTAS
  `github_copilot | claude_code_cli | codex_cli` (default `github_copilot`); con
  `generator_mode === "local"` no se muestra (se manda `runtime: null`).
- **Click "Optimizar":** `EvolutionOptimizer.run(targetRef, runtimeOrNull, true)`;
  202 → guardar `activeRun` y arrancar el polling; 409/404 → Toast `warning` con el
  `message` del backend (los tres 409 de §4.8 son estados esperables, no errores).
- **Polling de corrida activa (contrato G9, literal):**
  ```typescript
  // SOLO mientras hay corrida running. setTimeout encadenado, JAMAS setInterval.
  const pollRef = useRef<{ stop: boolean; count: number }>({ stop: false, count: 0 });
  function pollActiveRun(runId: string) {
    if (pollRef.current.stop || pollRef.current.count >= RUN_POLL_MAX) return;
    pollRef.current.count += 1;
    window.setTimeout(async () => {
      const res = await EvolutionOptimizer.getRun(runId);
      // actualizar estado; si isTerminal(status) -> refresh de runs/targets y FIN;
      // si sigue running -> pollActiveRun(runId)
    }, RUN_POLL_MS);
  }
  // cleanup del effect: pollRef.current.stop = true  (unmount corta el ciclo)
  ```
- **Vista de corrida activa/última** (`Card`): `StatusChip` con
  `runStatusTone/Label`, `generatorLabel`, progreso "variante {variants_done}/{variants_planned}",
  tokens (`formatTokens(budget.tokens_est_in + budget.tokens_est_out)` — Plan 161),
  `improvementDisplay(base?.score, winner?.score)`, lista de `steps` (los últimos 10,
  `formatTime` para el ts), botón "Cancelar" (`ConfirmButton` — Plan 136) visible solo
  con `status === "running"`, y si `proposal_id` no es nulo, link
  `<a href={"/evolution?proposal=" + proposal_id}>Ver propuesta emitida</a>`
  (deep-link G10 del 167: la bandeja del 167 la abre — CERO UI nueva de aprobación).
- **Historial de corridas** (colapsable, lazy on-expand): tabla `target / estado /
  score base→winner / propuesta / fecha` (`formatDateTime`).
- **Lineage / archive** (colapsable, lazy): al expandir una corrida,
  `archive({ run_id })` → lista indentada con `lineageRows` (depth 1 = sangría CSS),
  por fila: `verdictLabel` en `StatusChip`, score, `cost_proxy` en tokens
  (`formatTokens`), `mutation_lesson` como subtexto, `invalid_reason` si aplica.
- **Lecciones** (colapsable, lazy): `lessons(aspectKey)` → lista "({outcome},
  Δ{delta}) {text}" — el capital de proceso visible.
- **Empty state:** `EmptyState` (Plan 140) cuando no hay targets ("Sin prompts
  optimizables — agregá agentes en backend/Stacky/agents/") o no hay corridas ("Sin
  corridas todavía", hint "Elegí un prompt y tocá Optimizar").
- **Toast:** patrón component-local (`components/Toast.tsx`).

**Tests PRIMERO:** `frontend/src/evolution/optimizerModel.test.ts` (vitest puro).
8 casos:
1. `runStatusTone`/`runStatusLabel` — los 6 estados con los literales EXACTOS.
2. `verdictTone`/`verdictLabel` — los 5 verdicts.
3. `generatorLabel` — local / runtime:codex_cli / desconocido.
4. `isTerminal` — running false; los otros 5 true.
5. `lineageRows` — 1 base + 2 hijas + 1 huérfana → orden y depths exactos (base 0, hijas 1, huérfana 0 al final).
6. `lineageRows` no muta el input (deep-equal antes/después).
7. `improvementDisplay` — (0.6, 0.7) → "0.60 → 0.70"; (null, 0.7) → "—".
8. `RUN_POLL_MS === 2000` y `RUN_POLL_MAX === 900` (contrato del polling acotado congelado).

**Comandos (BINARIO, Git Bash):**
```bash
cd "Stacky Agents/frontend" && npx vitest run src/evolution/optimizerModel.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
cd "Stacky Agents/frontend" && npx vitest run src/__tests__/uiDebtRatchet.test.ts
grep -c "setInterval" "Stacky Agents/frontend/src/evolution/OptimizerSection.tsx"   # debe dar 0
```
**Criterio BINARIO:** 8/8 + tsc exit 0 + ratchet UI verde + grep `0`. Smoke visual del
operador: declarado pendiente-de-operador (patrón disclosure Plan 111; RTL/jsdom no
están en `package.json` — gap estructural conocido).
**Flag:** con `STACKY_EVOLUTION_OPTIMIZER_ENABLED` OFF el health devuelve
`flag_enabled false` y la sección no renderiza (cero fetchs extra).
**Impacto por runtime:** idéntico (panel web). **Trabajo del operador:** ninguno
(optimizar es opcional y explícito).

---

### F6 — Cierre: ratchet + estado del doc + verificación final

**Objetivo (1 frase):** registrar los 5 tests nuevos en el ratchet, sincronizar el
estado del doc y correr la verificación completa por archivo.

**Archivos a editar:** `backend/scripts/run_harness_tests.sh` (dentro de
`HARNESS_TEST_FILES=(`, `:20`) y `backend/scripts/run_harness_tests.ps1`: bloque nuevo
"Plan 169" inmediatamente DESPUÉS del bloque del Plan 168 (anclar por contenido
`tests/test_fitness_endpoints.py`), con los 5 archivos:
`tests/test_optimizer_flags.py`, `tests/test_optimizer_store.py`,
`tests/test_optimizer_generator.py`, `tests/test_optimizer_engine.py`,
`tests/test_optimizer_endpoints.py` (mismo estilo de las entradas vecinas). Este doc:
actualizar `**Estado:**` al cerrar (regla de la casa).

**Comandos de cierre (todos por archivo, todos verdes):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_optimizer_flags.py -q
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_optimizer_store.py -q
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_optimizer_generator.py -q
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_optimizer_engine.py -q
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_optimizer_endpoints.py -q
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_harness_flags.py -q
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_harness_flags_requires.py -q
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_documenter_autonomy.py -q
cd "Stacky Agents/frontend" && npx vitest run src/evolution/optimizerModel.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
```
(El 8º comando re-corre la suite que asserta sobre `_ONE_SHOT_ADO_IDS` — verificación
de no-regresión del toque de F2.)
**Criterio BINARIO:** los 10 comandos exit 0 (fallos preexistentes de
`test_harness_flags.py`: cuenta la foto previa de F0). **Trabajo del operador:** ninguno.

---

## 6. Riesgos y mitigaciones

- **R1 — Self-confirming loop (survey RSI failure #1): el que genera se aprueba a sí
  mismo.** Mitigación en 4 capas: (1) el fitness SIEMPRE lo computa el 168, cuyo juez
  es el modelo LOCAL con rúbricas versionadas; (2) este plan declara `generator_model`
  en cada `evaluate_candidate` — si generador y juez coinciden (modo `local`), el 168
  aplica `SELF_JUDGE_MULTIPLIER` 0.5 y marca `self_judge_risk`; en modo `runtime` el
  modelo es `runtime:<r>` y nunca coincide; (3) la señal determinista (que no comparte
  pesos con nadie) manda con cap 0.49; (4) el mutador NO puede optimizarse a sí mismo
  (`_TARGET_DENYLIST`, test F3 caso 12).
- **R2 — Diversity collapse (survey failure #2): converger a una sola línea.**
  Mitigación: archive append-only que conserva TODAS las variantes (también
  `dominated`/`invalid`) con lineage; frente Pareto multi-objetivo persistido (no un
  "mejor único"); muestreo aleatorio de padres del frente en corridas siguientes
  (GEPA); `_PARETO_MAX=8` mantiene diversidad acotada sin explotar.
- **R3 — Reward hacking (survey failure #3): optimizar la métrica, no el objetivo.**
  Mitigación: (1) deterministas del 168 mandan (cap 0.49) — una variante que "suena
  linda" pero rompe estructura no pasa; (2) el margen se computa sobre el score YA
  capeado; (3) `cost_proxy` en el frente castiga el inflado de prompts (una variante
  que solo agrega texto no domina); (4) el prompt del mutador prohíbe eliminar rieles
  y acortar a menos de la mitad, y los checks seed del 168 (`min_len`/`max_len`/
  estructura) lo verifican DETERMINISTA; (5) la última línea de defensa es humana: la
  propuesta entra `pending_review` con diff visible y el operador aprueba (167).
- **R4 — Autonomía por la puerta de atrás.** El motor no importa `evolution_apply`
  (DoD por grep); la allowlist HOTL del 167 queda congelada por test (F3 caso 12);
  `_SUGGESTABLE_FLAGS` es allowlist-only y no puede contener flags de la serie
  (test F3 caso 13); no hay scheduler ni cron; el thread nace de un click y muere.
- **R5 — Corridas largas / thread colgado.** El generador tiene timeout duro
  (`_GENERATE_TIMEOUT_S=1800`, mismo anti-zombie del CLI); el `evaluate_candidate`
  está acotado por el presupuesto del 168; el run tiene `RUN_POLL_MAX` en la UI (deja
  de pollear a los 30 min aunque siga `running`) y cancelación cooperativa; el lock
  `any_run_running` impide corridas simultáneas. Peor caso residual: run huérfano en
  `running` tras un crash del backend → el POST siguiente devolvería
  `optimizer_already_running`; mitigación congelada: `start_run` trata como NO-running
  cualquier run `running` con `started_at` más viejo que 2 horas (constante
  `_STALE_RUN_HOURS = 2`, chequeada en `any_run_running`) y lo cierra como `error`
  con `error="stale_run_reaped"` (step incluido).
- **R6 — Threads + SQLAlchemy en pytest (gotcha real del repo).** Riel G14: ningún
  test lanza el thread; `_start_run_async` se monkeypatchea; el motor solo toca DB en
  modo `runtime` (vía `_wait_and_read_output`), que en tests siempre está mockeado.
- **R7 — Costo.** Generador local = USD 0 + presupuesto de tokens estimados por
  corrida (flag UI); generador runtime = AgentExecutions REALES que el Centro de
  Costos 142 contabiliza solo, visibles bajo `agent_type="evolution_mutator"` (espejo
  del criterio 167 R7 / 168 §4.5 — NO se inventa vía nueva de ingesta); K clampeado
  1..6; ≤ K+1 evaluaciones por corrida.
- **R8 — Variantes basura del generador (garbage in).** Marcadores obligatorios
  (`sin_marcador_variante` → `invalid`, no rompe); variante idéntica al base →
  `invalid`; el prompt exige conservar rol/contrato/límites; los checks deterministas
  del 168 filtran el resto; TODO queda en el archive con `invalid_reason` (auditable).
- **R9 — `archive.jsonl`/`lessons.jsonl` crecen.** Aceptado en v1 (KB de texto; los
  textos > 20000 chars no se duplican en el archive); tails clampeados. Compactar
  sería un plan futuro — NO acá (espejo 167 R8 / 168 R10).
- **R10 — Números de línea que rotan (sesiones paralelas).** Citas orientativas:
  anclar SIEMPRE por contenido/símbolo (regla heredada 128/167/168). WIP ajeno: G12
  (`runtime_paths.py` y `run_preflight.py` tienen WIP ajeno HOY — no tocarlos).

## 7. Fuera de scope (explícito)

- **Flywheel de conocimiento (lección→curación→corpus RAG→contexto): Plan 170.** Acá
  solo quedan sus enchufes (§8).
- **Optimizar `knowledge_rag`:** las lecciones se evalúan (168) y auto-aplican gateadas
  (167 HOTL), pero NO entran al loop evolutivo v1 — el 170 es el dueño del ciclo de
  conocimiento. Declararlo evita dos escritores del mismo aspecto.
- **Optimizar `stacky_codebase`:** el pipeline proponer→criticar→implementar→supervisar
  YA es el optimizador del código de Stacky (Tablero 128); este motor no compite.
- **Loop evolutivo sobre flags/config:** sin fitness evaluable (168 lo rechaza) no hay
  selección honesta; v1 = solo "sugerencia de valor" allowlist-only (§4.7). Ampliar la
  allowlist espera al catálogo del Plan 159.
- **Ejecutar agentes REALES con un prompt candidato (behavior fitness del candidato):**
  fuera de scope explícito del 168 §7; el fitness v1 es artefacto-céntrico y lo declara.
- **Corridas programadas / scheduler / daemon:** PROHIBIDO en v1 (riel §3.2).
- **Crossover multi-padre real, mutación multi-objetivo simultánea, meta-optimización
  del prompt del mutador:** direcciones futuras documentadas; v1 = mutación dirigida
  simple + padres como contexto.
- **Editor UI del prompt de mutación / de la denylist:** constantes en código
  auditables + tests congeladores; editarlas = editar el repo (a propósito).
- Notificaciones (152), auth/RBAC, react-router.

## 8. Contratos hacia 170 (congelados acá, implementados allá)

### 8.1 ← Planes 167/168 (lo que este plan HONRA, nombres de ellos)

- Emite propuestas EXCLUSIVAMENTE vía `evolution_store.create_proposal(origin="optimizer",
  initial_status="pending_review", parent_proposal_id=…)` — contrato 167 §8.2 al pie de
  la letra (el gate humano no cambia).
- Computa fitness EXCLUSIVAMENTE vía `fitness_service.evaluate_candidate(…)` (168 §8.2,
  firma congelada, `generator_model` SIEMPRE declarado) y llena `fitness_before/after`
  vía `inject_proposal_fitness` con el shape 167 §4.7.
- Los runs de evaluación de candidatos quedan `trigger=="candidate"` y NO contaminan la
  tendencia del scorecard (garantía del 168 que este plan asume).

### 8.2 → Plan 170 (flywheel de conocimiento — NO diseñarlo acá)

- **`lessons.jsonl` como fuente de lecciones candidatas:** cada `MutationLesson` con
  `outcome=="mejoro"` es materia prima curable — el 170 puede leer
  `evolution_optimizer_store.read_lessons_tail()` y proponer su promoción a
  `knowledge_note` del 167 (y de ahí, con curaduría, al corpus `docs/rag/` — riel G11
  del 167: SIEMPRE `.jsonl/.json/.txt`). Este plan NO promueve nada.
- **El archive como memoria de proceso:** `read_archive(aspect_key=…)` da al 170 la
  historia completa de qué variantes existieron y por qué ganaron/perdieron
  (`critique_summary`, `mutation_lesson`, `verdict`) — trazabilidad estilo DGM lista
  para minar.
- **Reservado para el 170:** valor `origin="lesson"` en `EvalCase` del 168 (ya
  reservado por el 168 §8.3) y cualquier escritura al corpus RAG. Este plan no toca
  `docs/` (G10).

## 9. Glosario (para un modelo menor)

| Término | Definición |
|---|---|
| **mutación reflexiva** | Generar una variante LEYENDO por qué falló el artefacto actual (críticas del juez + checks fallados), en vez de mutar a ciegas. Corazón de GEPA: el feedback textual vale tanto como el score. |
| **variante / candidato** | Un texto alternativo COMPLETO del artefacto (no un diff), producido por el generador y evaluado por el 168 sin aplicarse. |
| **frente Pareto** | Conjunto de variantes NO dominadas en calidad×costo: nadie las supera en ambos ejes a la vez. Optimizar multi-objetivo evita colapsar todo a un escalar gameable. |
| **dominancia** | `a` domina a `b` si es al menos igual en ambos ejes y mejor en uno (§4.4). |
| **archive / lineage** | Registro append-only de TODAS las variantes (también descartadas) con su `parent_id`: el árbol genealógico de la búsqueda. Estilo Darwin Gödel Machine: guardar sub-óptimas habilita exploración open-ended. |
| **hill-climbing vs open-ended** | Hill-climbing: quedarse solo con el mejor y mutarlo (se estanca en óptimos locales). Open-ended: mantener un frente/archive diverso y muestrear padres desde ahí (anti estancamiento). Este plan es open-ended acotado. |
| **padre (parent)** | Variante previa del frente que se inyecta como contexto al prompt de mutación de una corrida nueva. |
| **margen mínimo** | Mejora mínima de score (default 0.02) que el ganador debe superar sobre el base para que se emita propuesta. Sin margen no hay propuesta: el ruido no genera trabajo al operador. |
| **STOP condition** | Condición dura que termina la corrida: K variantes, presupuesto agotado, margen no alcanzado, cancelación del operador. Nada corre sin fin. |
| **cost_proxy** | Costo estimado del artefacto en tokens (`len//4`): el prompt de sistema entra completo en cada ejecución del agente, así que su longitud es costo recurrente real. |
| **mutation lesson** | 1-3 líneas de "qué cambié y por qué debería mejorar", emitidas por el generador y anotadas por el motor con el outcome real (`mejoro/empeoro/…`). Capital de proceso reutilizable entre corridas (survey RSI: process-level beats result-level). |
| **generador** | Quién redacta las variantes: el modelo LOCAL (`invoke_local_llm`, USD 0) o el RUNTIME de agentes (Codex/Claude/Copilot vía `run_agent`). Configurable por flag UI; el juez NUNCA es el generador (168). |
| **one-shot ticket** | Ticket sentinela con `ado_id` negativo (`-9` para este plan) que hace que la sesión CLI cierre sola al primer resultado (`_ONE_SHOT_ADO_IDS`) — sin él, el run del mutador bajo Claude CLI colgaría 1800 s. |
| **cancelación cooperativa** | El botón Cancelar setea un flag que el motor honra ENTRE pasos (no mata la invocación en curso). Simple y sin procesos zombie. |
| **corrida (OptimizationRun)** | Una ejecución completa del loop sobre UN target, persistida con estado, progreso, presupuesto y resultado. |

## 10. Orden de implementación

1. **Pre-check global** — 167 y 168 en el árbol (si no, DETENERSE).
2. **F0** — flags + config + help + meta-tests (foto previa de `test_harness_flags.py`).
3. **F1** — store (runs/archive/lessons/pareto + `pareto_front`) + 12 tests.
4. **F2** — agente mutador + registro + `-9` en `_ONE_SHOT_ADO_IDS` + `variant_generator` + 10 tests.
5. **F3** — motor (`start_run`/`_run_optimization_sync` + emisión gateada) + 14 tests.
6. **F4** — API + registro de blueprint + 12 tests.
7. **F5** — `optimizerModel` + `OptimizerSection` + wiring `EvolutionCenterPage` + 8 tests + tsc.
8. **F6** — ratchet (sh + ps1) + estado del doc + corrida completa de cierre.

## 11. Definición de Hecho (DoD)

- [ ] Las 5 flags con patrón triple completo (config + FlagSpec + `_CATEGORY_KEYS` +
      help + curated SOLO la bool + requires al ROOT del 167), editables desde la UI
      del Arnés; `harness_defaults.env` NO tocado a mano (G11).
- [ ] Los 5 archivos de test backend verdes POR ARCHIVO (56 casos: 8+12+10+14+12),
      registrados en `HARNESS_TEST_FILES` (sh + ps1); `optimizerModel.test.ts` (8)
      verde; `npx tsc --noEmit` exit 0; `uiDebtRatchet` verde.
- [ ] KPI-1: propuesta emitida real con `origin="optimizer"` + `pending_review`;
      `_TARGET_DENYLIST` y `_HOTL_ALLOWED_ASPECTS` congelados por test. KPI-2: prompt
      de mutación contiene críticas/checks/lecciones/padres. KPI-3: Pareto + margen
      con empates y `no_improvement` sin propuesta. KPI-4: `stopped_budget` y
      `cancelled` verificados. KPI-5: 409 `generator_unavailable` declarado.
- [ ] Con `STACKY_EVOLUTION_OPTIMIZER_ENABLED=false`: endpoints (salvo
      `/optimizer/health`) → 404 `optimizer_disabled`; la sección no renderiza; resto
      byte-idéntico (KPI-6).
- [ ] El motor NUNCA aplica: `grep -n "evolution_apply" "Stacky Agents/backend/services/evolution_optimizer.py"`
      → 0 matches (el import está PROHIBIDO; la única emisión es `create_proposal` +
      `inject_proposal_fitness`).
- [ ] Sin autonomía: `grep -rn "start_run\|_run_optimization_sync" "Stacky Agents/backend" --include=*.py | grep -v tests | grep -v evolution_optimizer`
      → 0 matches fuera de `api/evolution_optimizer.py` (único caller: el POST del
      operador).
- [ ] Cero egress/subprocess en tests: `invoke_local_llm`, `run_agent` y
      `_wait_and_read_output` mockeados en TODO test que alcance sus caminos; ningún
      test lanza el thread real (G14).
- [ ] Cero `setInterval`: `grep -c "setInterval" "Stacky Agents/frontend/src/evolution/OptimizerSection.tsx"`
      → `0`; el polling de corrida usa `setTimeout` encadenado con `RUN_POLL_MAX` y
      stop en unmount/terminal.
- [ ] `-9 ∈ _ONE_SHOT_ADO_IDS` con su línea de comentario R1.2;
      `test_documenter_autonomy.py` sigue verde (no-regresión del frozenset).
- [ ] Las propuestas del optimizador aparecen y se operan en la bandeja NORMAL del 167
      (aprobar/rechazar/aplicar/rollback sin UI nueva), con `fitness_before/after`
      visibles.
- [ ] Encabezado `**Estado:**` de este doc actualizado al cerrar; `git status` final
      con WIP ajeno intacto (G12).
