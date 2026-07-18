# Plan 168 — Arnés de fitness: golden tasks por agente, jerarquía de señal y juez local con rúbricas versionadas

**Estado:** PROPUESTO v1 — 2026-07-17 · **Autor:** StackyArchitectaUltraEficientCode
**Serie:** "Auto-mejora recursiva" **2 de 4** (directiva del operador 2026-07-17):
**167** = núcleo del panel + registro de propuestas + ciclo MAPE con gates humanos (PROPUESTO, dependencia DURA de este plan) ·
**168 (este)** = arnés de evaluación/fitness: golden tasks, jerarquía de señal, juez LLM local, scorecards y llenado de `fitness_before/after` ·
**169** = optimizador evolutivo GEPA-style (NO se diseña acá; se le deja el contrato `evaluate_candidate`) ·
**170** = flywheel de conocimiento (fallo→lección→corpus RAG→contexto).
Este documento implementa SOLO el 168. PROHIBIDO implementar acá nada del 169/170: sus
enchufes quedan congelados en §8.

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

| Sustrato | Anclaje verificado | Rol en el 168 |
|---|---|---|
| **Plan 167 IMPLEMENTADO (DURA)** | `docs/167_PLAN_CENTRO_DE_EVOLUCION_…md` §4.3 (shape `ImprovementProposal` con `fitness_before/after`), §4.7 (shape fitness), §8.1 (contrato hacia este plan) | F4/F5/F6 asumen `services/evolution_store.py`, `api/evolution.py` y `pages/EvolutionCenterPage.tsx` en el árbol. **Si el 167 no está implementado, el implementador DEBE detenerse y reportarlo** — F0..F3 son independientes, F4..F6 NO. |
| Módulo evals existente (semilla) | `backend/evals/golden_runner.py:27` (`_AGENTS_DIR`), `:31-36` (`GoldenCase`), `:40-55` (`GoldenResult.to_dict`), `:58` (`list_agents`), `:65` (`load_golden_set`), `:85` (`_evaluate`), `:109` (`run_agent`); `backend/evals/__main__.py:31` (`main`: `run/list/harvest`, exit 1 si falla); `backend/evals/harvest.py:29` (`harvest(execution_id, name=, agents_dir=)`, PII-mask en `:95`, import `redact_irreversible` en `:60`); `backend/evals/eval_gate.py:24` (`run_evals_for_agent_type` → warning suave) | El 168 lo **EXTIENDE** (mandato §8.1 del 167: reusar, no reescribir). El nivel `execution` delega en `golden_runner._evaluate`. |
| Juez determinista existente | `backend/contract_validator.py:23-29` (`ContractResult`: `passed`, `score` 0–100, `failures`, `warnings`), `:130` (`def validate(agent_type, output) -> ContractResult`) | Check `artifact_contract` (F2) |
| Registry de agentes | `backend/agents/__init__.py:14-30` (`registry` con 12 agentes), `:33` (`list_agents`), `:37` (`get`) | Seeds de casos + `behavior_score` |
| Prompts runtime | dir `backend/Stacky/agents/` (verificado en disco por el 167: `BusinessAgent.agent.md`, `Developer.agent.md`, `DevOpsAgent.agent.md`, `Documentador.agent.md`, `FunctionalAnalyst.agent.md`, `IncidentAnalyst.agent.md`, `QAUat1.agent.md`, `manifest.json`) | Seeds `subject="artifact"` por archivo |
| LLM local (juez) | `backend/copilot_bridge.py:241-249` (firma `invoke_local_llm(*, agent_type, system, user, on_log, execution_id=None, model=None)`), `:257-262` (`RuntimeError` si `LOCAL_LLM_ENDPOINT` vacío), `:263` (`model or config.LOCAL_LLM_MODEL`), `:265` (`LOCAL_LLM_TIMEOUT_SEC`); `backend/config.py:90-93` (`LOCAL_LLM_ENDPOINT` default Ollama, `LOCAL_LLM_MODEL` default `qwen3:32b`) | F3: el juez es SIEMPRE el modelo local (agnóstico de los 3 runtimes; precedente Planes 106/127) |
| `data_dir()` | `backend/runtime_paths.py:48` (`data_dir`) | Persistencia runtime: `data_dir()/evolution/evals/` |
| Store del 167 (patrón + API) | 167 §4.1 (layout `data_dir()/evolution/`), §F1 (`evolution_store.update_proposal_fields` — patch superficial de claves EXISTENTES; `fitness_before/after` SON claves del shape §4.3) | F4 persiste fitness vía `update_proposal_fields` |
| Incidencias (flywheel 1-click) | `backend/services/incident_store.py:36` (`incidents_root`), `:106` (`create_incident`, status inicial `"capturada"` `:164`), `:196` (`get_incident`), `:230` (`list_incidents`), `:237` (`find_by_execution`); resumen del ledger `{id, created_at, status, title, tracker_id}` (`:7-9`) | F5: `POST /fitness/cases/from-incident` |
| `AgentExecution` | `backend/models.py:207`; uso real en `evals/harvest.py:57-92` (`session_scope` + `exec_row.status/output/agent_type`) | F5: `POST /fitness/cases/from-execution` |
| PII mask | `backend/services/pii_masker.redact_irreversible` (import real en `evals/harvest.py:60`, aplicado en `:95`) | F5: todo output congelado se enmascara ANTES de persistir |
| Flags patrón triple | `backend/services/harness_flags.py:117` (`_CATEGORY_KEYS`), `:265` (tupla que contiene `"STACKY_PLANS_BOARD_ENABLED"`), `:331` (nota "toda flag nueva…"), `:3267` (FlagSpec `STACKY_PLANS_BOARD_ENABLED`, ancla de inserción), `:3373` (reverse map) | F0 |
| Meta-tests de flags | `backend/tests/test_harness_flags.py:467` (`_CURATED_DEFAULTS_ON`), `backend/tests/test_harness_flags_requires.py:120` (`_REQUIRES_MAP_FROZEN`) | F0 |
| Ratchet de tests | `backend/scripts/run_harness_tests.sh:20` (`HARNESS_TEST_FILES=(`; zona de entradas recientes: `tests/test_incident_dev_agent.py` en `:460`) y `backend/scripts/run_harness_tests.ps1:414` (misma entrada) | F7 |
| conftest backend | `backend/tests/conftest.py:11` (`os.environ.setdefault("STACKY_TEST_MODE", "1")`) | Todos los tests; el guard de red FORMAL es del Plan 154 (pendiente) — acá se mockea `invoke_local_llm` SIEMPRE |
| Registro de blueprints | `backend/api/__init__.py:61/:122` + las 2 líneas `evolution_bp` que agrega el 167 F4 (anclar por contenido `from .evolution import bp as evolution_bp`) | F5 |
| Primitivas UI (138/162) | `frontend/src/components/ui/index.ts:17-18` (`Tabs`/`TabItem`), `:25` (`Field`, `firstErrorFieldId`); barrel completo `:7-34` | F6 |
| Estados (140) / formato (161) | `components/EmptyState.tsx`, `components/SkeletonList` (NO en el barrel); `services/format.ts:40-118` (`formatDateTime/formatTokens/formatPercent/formatDuration…`) | F6 |
| ConfirmButton (136) / Toast (135) | `components/ConfirmButton.tsx:23`; `components/Toast.tsx:9-19` | F6 |

**Ortogonal a (NO tocar, NO depender):** Plan 154 (arnés VERAZ de la suite pytest del
repo — ver §2.3, delimitación explícita), Planes 153/156/163/164/165 (pendientes),
Plan 152 (notificaciones), Planes 158/159 (telemetría CLI / catálogo modelos).

---

## 1. Objetivo + KPI / impacto esperado

**Objetivo (1 párrafo):** el Plan 167 instala el registro y los gates de la auto-mejora
de Stacky, pero deja el campo decisivo en `null`: **`fitness_before/after`** — la señal
objetiva de "¿este artefacto es mejor que el que está?". Hoy Stacky tiene un embrión de
esa señal (`backend/evals/`: goldens congelados juzgados por `contract_validator`, 100%
determinista) pero está desconectado de todo loop, no tiene noción de caso-con-input,
ni juez con rúbrica, ni score agregado, ni persistencia de corridas, ni tendencia. Este
plan construye el **arnés de fitness**: (a) **golden tasks por agente** (`EvalCase`)
versionadas y curables, sembradas automáticamente desde los goldens existentes y los
prompts runtime; (b) una **jerarquía de señal explícita** — `deterministic` >
`execution` > `llm_judge` — donde las señales deterministas SIEMPRE mandan (guard
anti reward-hacking: si un check determinista falla, ningún juez LLM puede aprobar el
artefacto); (c) un **juez LLM local** (`invoke_local_llm`, mismo para los 3 runtimes)
con **rúbricas versionadas y auditables** que emite score + **crítica textual** (la
crítica es insumo del optimizador 169), con **degradación declarada** a
solo-deterministas si no hay endpoint local; (d) **EvalRuns persistidos** con scorecard
por aspecto y **tendencia** (delta vs corrida anterior) visibles en el panel del 167;
(e) el **llenado real de `fitness_before/after`** de las propuestas del 167 evaluando
el artefacto vigente y el propuesto **en sandbox de evaluación (sin aplicar nada)**; y
(f) el **flywheel fallo→eval en 1 click**: convertir una incidencia o una ejecución en
caso de eval borrador que el operador confirma (human-in-the-loop). Sin señal externa
no hay mejora confiable (survey RSI): este plan ES esa señal.

**KPIs binarios:**

- **KPI-1 — Reproducibilidad determinista:** dos corridas consecutivas del arnés sobre
  el mismo artefacto con el juez deshabilitado producen `score` y `per_case` idénticos.
  Comando: `.venv\Scripts\python.exe -m pytest tests/test_fitness_runner.py -q` → exit 0.
- **KPI-2 — La jerarquía manda (anti reward-hacking):** un artefacto con un check
  determinista fallado queda con `score <= 0.49` y `passed == False` aunque el juez LLM
  (mockeado) devuelva `1.0`. Cubierto por `tests/test_fitness_runner.py` (caso 8).
- **KPI-3 — Juez ≠ generador + degradación declarada:** sin `LOCAL_LLM_ENDPOINT`
  (RuntimeError del bridge) la corrida COMPLETA igual, con `judge.used == False`,
  `judge.error` no nulo y los niveles deterministas intactos; cada juicio persistido
  registra `judge.model` y `rubric_versions`. Comando:
  `.venv\Scripts\python.exe -m pytest tests/test_fitness_judge.py -q` → exit 0.
- **KPI-4 — Contrato 167 vivo:** `POST /api/evolution/proposals/<id>/fitness/run` con
  `{"which": "both"}` deja en la propuesta `fitness_before` y `fitness_after` con el
  shape EXACTO del 167 §4.7 (`score/metrics/eval_ref/evaluated_at`) **sin aplicar la
  propuesta** (el archivo target queda byte-idéntico). Comando:
  `.venv\Scripts\python.exe -m pytest tests/test_fitness_service.py -q` → exit 0.
- **KPI-5 — Cero regresión / cero egress:** con `STACKY_EVAL_HARNESS_ENABLED=false`
  todos los endpoints nuevos (salvo `/fitness/health`) devuelven 404 y la app queda
  byte-idéntica; ningún test del plan toca red (LLM local SIEMPRE monkeypatcheado).
  Comandos: `.venv\Scripts\python.exe -m pytest tests/test_fitness_endpoints.py -q` →
  exit 0 y `npx tsc --noEmit` → exit 0.
- **KPI-6 — Contrato 169 vivo día uno:** `fitness_service.evaluate_candidate(...)`
  existe con la firma y el shape de retorno EXACTOS de §8.2, y su espejo HTTP
  `POST /api/evolution/fitness/evaluate-candidate` responde 200 con mocks. Cubierto por
  `tests/test_fitness_service.py` (caso 9) y `tests/test_fitness_endpoints.py` (caso 10).

**KPIs de impacto (proyectados, verificables por observación):**

| Métrica | Hoy | Con el plan |
|---|---|---|
| `fitness_before/after` de las propuestas del 167 | siempre `null` ("—") | llenables con 1 click, shape §4.7, sin aplicar nada |
| Señal objetiva "¿mejoró el agente X?" | inexistente (vibra) | scorecard por aspecto con score 0..1, gate determinista y delta vs corrida anterior |
| Casos de eval | 12 goldens congelados sin dueño visible (`evals/agents/`) | los mismos + seeds de artefacto + casos runtime curables desde la UI |
| Fallo de producción → caso de eval permanente | proceso manual inexistente | 1 click desde incidencia o ejecución (borrador `enabled=false`, confirma el operador) |
| Crítica textual accionable por artefacto | inexistente | persistida por juicio (insumo del 169, estilo GEPA) |

---

## 2. Por qué ahora / gap que cierra

### 2.1 Evidencia local

El Plan 167 (PROPUESTO, serie 1/4) deja el contrato explícito en su §8.1: *"el 167 NO
computa fitness; PROHIBIDO llenar estos campos con heurísticas"* — los llena ESTE plan.
`backend/evals/` existe y es sólido pero mínimo: `golden_runner.py` evalúa **outputs
congelados** contra el contrato determinista por agente (`contract_validator.validate`,
`:130`), `harvest.py` convierte una `AgentExecution` en golden con PII-mask, y
`eval_gate.py` corre un gate suave al guardar un agente. Lo que NO existe hoy (todo
verificado): noción de caso con input/rúbrica/peso/origen; juez LLM; score agregado
entre niveles de señal; persistencia de corridas (cada `python -m evals run` se pierde
en stdout — `__main__.py:17-28` imprime y retorna exit code); tendencia/baseline;
conexión con propuestas del 167. El ciclo del 167 puede proponer "revisar el prompt del
developer" (regla R-A1), pero nadie puede responder objetivamente si el prompt
propuesto es MEJOR que el vigente. Ese es el gap exacto.

### 2.2 Fundamento de diseño (investigación citada por nombre → decisión concreta)

1. **Survey RSI (arXiv 2607.07663)** — *la calidad de la señal de verificación es el
   TECHO de toda auto-mejora* ("no external signal, no reliable improvement"); jerarquía
   de verificación: formal/determinista > ejecución real > juez aprendido > señal
   intrínseca; *failure mode #1: self-confirming loops cuando generador y evaluador
   comparten pesos* → acá: (a) cada caso declara su **nivel** y el agregado pondera
   deterministas 3×, ejecución 2×, juez 1× (§4.4); (b) guard duro: determinista fallado
   ⇒ `score ≤ 0.49` (KPI-2); (c) el juez es el **modelo local**, distinto de los
   runtimes que generan artefactos, y cuando el generador declarado coincide con el
   juez, el peso del juez cae a la mitad y se marca `self_judge_risk` (§4.5); (d)
   rúbricas **versionadas en archivos auditables**, nunca prompts opacos (§4.6).
2. **Flywheel MAPE-K (arXiv 2510.27051) + práctica LangChain/Arize** — *"cada fallo de
   producción se convierte en caso de eval permanente con un click"; el golden set
   CRECE desde fallos reales* → F5: `from-incident` y `from-execution` crean casos
   **borrador** (`enabled=false`) que el operador confirma en el panel — el flywheel
   completo (lección→corpus) es del Plan 170.
3. **GEPA (Cerebras/DSPy/Databricks)** — *100-500 evaluaciones bastan; el feedback
   textual del juez ("por qué falló") vale tanto como el score* → el juicio persiste
   `critique` textual por caso y `evaluate_candidate` devuelve `critiques[]` (§8.2):
   ese texto es EL insumo del loop reflexivo del 169. Presupuesto de tokens por corrida
   (flag int), no fuerza bruta.
4. **Meta-Rewarding (arXiv 2407.19594) + CriticGPT (OpenAI)** — jueces que critican
   para ENCONTRAR errores → la rúbrica seed instruye al juez a listar defectos
   concretos, no a elogiar; la meta-evaluación de jueces queda documentada como futuro
   explícito (§7), no se implementa acá.
5. **AlphaEvolve / Sakana** — evaluadores automáticos BARATOS como fitness es lo que
   permite iterar → el nivel determinista corre siempre y gratis; el juez es local
   (costo USD 0) y acotado por presupuesto; nada de evaluación en la nube.

### 2.3 Delimitación EXPLÍCITA con el Plan 154 (para que nadie los confunda)

El Plan 154 ("Arnés veraz: ratchet, fixtures y guard de red", CRITICADO v2, NO
implementado) es sobre la **suite pytest del REPO**: que los tests de Stacky digan la
verdad (ratchet verde, fixtures correctas, cero egress desde pytest — su KPI-5). Este
plan 168 es sobre la **calidad de los AGENTES en runtime**: evaluar artefactos
(prompts, lecciones) y comportamientos (outputs) con señal objetiva. NO se toca ningún
archivo del alcance del 154 (`tests/harness_ratchet_allowlist.txt`,
`tests/test_output_watcher.py`, `tests/test_plan105_*`, `api/executions.py`) ni se
implementa su guard de red. Lo ÚNICO compartido es el principio "cero egress en tests"
(154 §2.5): **todos los tests de este plan monkeypatchean `invoke_local_llm`** — regla
dura porque el conftest actual (`tests/conftest.py:11`) solo setea `STACKY_TEST_MODE`,
no bloquea red todavía.

---

## 3. Principios y guardarraíles (NO negociables)

1. **La señal determinista manda.** Ningún artefacto "aprueba" por juez LLM si tiene
   checks deterministas definidos que fallan (KPI-2). Los umbrales y pesos viven en
   constantes con nombre en el código (§4.4), visibles y testeadas — rúbrica auditable,
   no reward opaco.
2. **Juez ≠ generador (anti self-confirming loop).** El juez es SIEMPRE
   `invoke_local_llm` (modelo local, `config.LOCAL_LLM_MODEL`). Si no hay endpoint
   local: **degradación declarada** a solo-deterministas (el run completa, `judge.used
   = False`, sin romper — espejo exacto del patrón del 167 F3). PROHIBIDO llamar al
   runtime de agentes (Codex/Claude/Copilot) para juzgar.
3. **Human-in-the-loop innegociable:** el arnés corre SOLO on-demand (botón del panel o
   llamada del 169, que a su vez entra por gates del 167). No hay daemon, no hay cron,
   no hay disparo automático (el repo NO tiene scheduler genérico — verificado por el
   167 §3.2; este plan tampoco lo crea). Los casos creados por flywheel nacen
   **borrador** (`enabled=false`) y solo el operador los habilita. Evaluar fitness NO
   aplica ninguna propuesta: es lectura + escritura de los campos `fitness_*`.
4. **Cero trabajo extra al operador:** arnés y panel default **ON**; los seeds se
   generan solos (migración lazy idempotente, patrón `ensure_seed_aspects` del 167);
   nada que configurar. El juez LLM default **ON** y NO cita la excepción dura #3
   (prerequisito no garantizado) porque **degrada declaradamente** sin endpoint: con la
   instalación default el arnés funciona completo en modo determinista, cero error.
   Todo configurable desde la UI del Arnés (registry dinámico); **nada env-only**.
5. **3 runtimes con paridad:** el arnés es backend Flask + panel React, idéntico bajo
   Codex CLI, Claude Code CLI y GitHub Copilot Pro. El único LLM es el **local**
   (agnóstico del runtime — precedente Planes 106/127/167). Ninguna fase toca el camino
   de ejecución de agentes. Fallback por ítem: sin LLM local → deterministas puros, en
   los 3 por igual.
6. **Mono-operador sin auth:** cero RBAC. `actor` descriptivo donde aplique.
7. **No degradar:** panel sin pollers (carga on-mount + botones — riel G9 del 167);
   stores con lock y lecturas tolerantes; con flags OFF byte-idéntico a hoy;
   `python -m evals` y `eval_gate` existentes siguen funcionando SIN cambios (solo se
   agrega, no se modifica su comportamiento).
8. **Reusar, no reinventar:** `golden_runner`/`contract_validator`/`harvest`/
   `pii_masker` existentes; store y API del 167; primitivas 138/162; estados 140;
   formato 161; ConfirmButton 136; Toast 135.

### Gotchas del repo que el implementador DEBE respetar (verificadas)

- **G1 — `config` vs `config.config`:** en archivos nuevos usar SIEMPRE
  `from config import config as _cfg` y `getattr(_cfg, "FLAG", default)` (espejo de
  `api/metrics.py:565-566`; gotcha recurrente de `api/tickets.py:7401`).
- **G2 — Ratchet de tests:** los 6 `test_*.py` nuevos DEBEN agregarse a
  `HARNESS_TEST_FILES` en `backend/scripts/run_harness_tests.sh` (`:20`; zona reciente
  `:460`) **y** `backend/scripts/run_harness_tests.ps1` (`:414`), o el meta-test del
  Plan 49 se pone rojo.
- **G3 — Aristas `requires=`:** cada flag con `requires=` DEBE tener su arista en
  `_REQUIRES_MAP_FROZEN` (`backend/tests/test_harness_flags_requires.py:120`).
- **G4 — `_CURATED_DEFAULTS_ON`:** cada flag **bool** con default efectivo ON va al set
  de `backend/tests/test_harness_flags.py:467`; las `type="int"` NO.
- **G5 — venv y tests por archivo:** backend con `.venv`
  (`.venv\Scripts\python.exe -m pytest tests/<archivo> -q`; `backend/venv` NO existe —
  verificado por el Plan 154), NUNCA la suite completa. Frontend `npx vitest run
  src/<archivo>`, por archivo.
- **G6 — Ratchet UI cero inline-style:** los `.tsx` nuevos tienen alcance 0 en
  `uiDebtRatchet`: TODO estilo va al `.module.css`; prohibido `style={{}}`.
- **G7 — `_CATEGORY_KEYS` obligatorio:** toda flag nueva va también al dict
  `_CATEGORY_KEYS` (`services/harness_flags.py:117`; nota normativa `:331`). Ancla de
  inserción: la tupla que contiene `"STACKY_PLANS_BOARD_ENABLED"` (`:265`) — el 167
  agrega ahí sus 4 keys; este plan agrega las suyas INMEDIATAMENTE después de las del
  167 (ubicar por el literal `STACKY_EVOLUTION_CYCLE_TOKEN_BUDGET`).
- **G8 — `requires` profundidad 1:** TODAS las aristas apuntan al ROOT
  `STACKY_EVOLUTION_CENTER_ENABLED` (flag master del 167, sin `requires` propio) —
  NUNCA en cadena a `STACKY_EVAL_HARNESS_ENABLED` (precedente normativo
  `harness_flags.py:3336` citado por el 167 G8; gotcha del Plan 104). El gate efectivo
  compuesto se hace EN CÓDIGO (§F5 `_fitness_enabled()`), no en el grafo de flags.
- **G9 — Sin pollers nuevos:** cero `setInterval`/`refetchInterval` en el frontend
  nuevo. Carga on-mount/on-expand + botones + refresh post-acción.
- **G10 — Corpus bajo `docs/`:** NADA de este plan escribe bajo `docs/`. Las rúbricas
  van en `backend/evals/rubrics/*.md` (fuera del alcance de `doc_indexer`, que escanea
  `docs/**/*.md`); los casos runtime y runs van a `data_dir()/evolution/evals/`.
- **G11 — `harness_defaults.env` NO se toca a mano** (lo regenera
  `scripts/export_harness_defaults.py` — riel del Plan 133 §3.6).
- **G12 — WIP ajeno / sesiones paralelas:** antes de editar cada archivo caliente
  (`config.py`, `harness_flags.py`, `harness_flags_help.py`, `api/__init__.py`,
  `endpoints.ts`, `EvolutionCenterPage.tsx`, scripts de ratchet): `git status --
  "<ruta>"`; staging quirúrgico por pathspec; PROHIBIDO `git stash/reset/checkout`. El
  implementador NO commitea (lo hace el orquestador).
- **G13 — Prosa vs gates propios:** ninguna cadena/comentario/docstring del código
  nuevo debe matchear espuriamente los greps de criterio de este plan (gotcha recurrido
  6×: el gate siempre gana; se reescribe la prosa).
- **G14 — PII:** todo output de ejecución que se congele como caso pasa por
  `redact_irreversible` ANTES de persistir (mismo riel que `harvest.py:95`).
- **G15 — Deploy frozen tolerante:** en el deploy PyInstaller los fixtures del repo
  pueden no estar junto al binario; TODA resolución de goldens/rúbricas/prompts es
  tolerante (dir ausente → lista vacía / caso `skipped`, NUNCA excepción) — mismo
  patrón que `golden_runner.list_agents` (`:58-62`, devuelve `[]` si no existe el dir).

---

## 4. Contratos congelados (van tal cual al código)

### 4.1 Layout de persistencia (bajo `data_dir()/evolution/evals/`)

```
data_dir()/evolution/evals/
  cases.json     # lista completa de EvalCase (archivo entero, como proposals.json del 167; NUNCA se borra un caso: se deshabilita)
  runs.jsonl     # una línea por EvalRun (append-only)
```

Reglas duras (espejo del 167 §4.1): el store llama `runtime_paths.data_dir()` **en cada
operación** (sin cache de módulo — los tests lo monkeypatchean); lecturas tolerantes
(ausente/corrupto → vacío); escrituras bajo `_EVALS_LOCK = threading.Lock()`;
`mkdir(parents=True, exist_ok=True)`.

### 4.2 `EvalCase` (golden task; todas las claves SIEMPRE presentes; `null` cuando no aplica)

```json
{
  "id": "case-<uuid4-hex>  |  case-seed-artifact-<slug>  |  case-seed-golden-<agent_type>-<golden_name>",
  "aspect_key": "agent_prompts/developer",
  "agent_type": "developer",
  "subject": "artifact | output",
  "level": "deterministic | execution | llm_judge",
  "title": "…",
  "input": {"kind": "artifact_text | golden_ref | frozen_output", "text": null, "golden_name": null},
  "checks": [{"kind": "…", "…": "…"}],
  "rubric_id": null,
  "weight": 1.0,
  "origin": "seed | incident | execution | manual",
  "enabled": true,
  "source_ref": null,
  "created_at": "<iso utc>", "updated_at": "<iso utc>"
}
```

Semántica congelada (validada por el store, `ValueError("invalid_case:<campo>")` si
falla):

| level | exige | prohíbe | qué evalúa |
|---|---|---|---|
| `deterministic` | `checks` no vacío | `rubric_id` | el TEXTO bajo evaluación con los checks de §4.3; gratis, corre SIEMPRE |
| `execution` | `input.kind ∈ {golden_ref, frozen_output}` | `rubric_id` | comportamiento congelado: `golden_ref` delega en `golden_runner`; `frozen_output` corre `checks` (típicamente `artifact_contract`) sobre `input.text` |
| `llm_judge` | `rubric_id` no nulo | — | el TEXTO bajo evaluación con el juez local + rúbrica (`checks` opcionales corren igual y mandan) |

Semántica de `subject`: `artifact` = el caso evalúa el TEXTO del artefacto (prompt de
agente, lección) — es el ÚNICO subject usable para comparar before/after; `output` = el
caso evalúa un comportamiento congelado del agente VIGENTE (goldens, outputs
cosechados) — informativo, no comparable con un candidato sin ejecutarlo (eso es
sandbox de ejecución real, territorio del 169+, fuera de scope §7).

Convención de `aspect_key` (congelada): `"agent_prompts/" + slug` para prompts de
agente, donde `slug = slug_for_prompt_file(filename)` (§F1); `"knowledge_rag"` para
lecciones. Cualquier otro string es válido (forward-compat con el 169/170) — el arnés
filtra por igualdad exacta.

### 4.3 Checks deterministas (kinds congelados — F2; cualquier otro `kind` → `ValueError("unknown_check_kind:<kind>")`)

| kind | params | ok cuando |
|---|---|---|
| `contains` | `{"value": str, "case_sensitive": false}` | `value` aparece en el texto (casefold si `case_sensitive` false) |
| `not_contains` | `{"value": str, "case_sensitive": false}` | `value` NO aparece |
| `regex` | `{"pattern": str}` | `re.search(pattern, text, re.MULTILINE)` no es None (pattern inválido → check `ok=False` con `detail="regex_invalida: <msg>"`, NUNCA excepción) |
| `min_len` | `{"value": int}` | `len(text) >= value` |
| `max_len` | `{"value": int}` | `len(text) <= value` |
| `json_valid` | `{}` | `json.loads(text)` no lanza |
| `artifact_contract` | `{"agent_type": str, "min_score": int, "must_pass": true}` | `contract_validator.validate(agent_type, text)` → `score >= min_score` y (`must_pass` → `passed`) |

Resultado por check: `{"kind": "…", "ok": true|false, "detail": "<str>"}`.

### 4.4 Jerarquía de señal y agregación (constantes con NOMBRE, en `fitness_runner.py`)

```python
LEVEL_MULTIPLIERS = {"deterministic": 3.0, "execution": 2.0, "llm_judge": 1.0}
SELF_JUDGE_MULTIPLIER = 0.5      # multiplica el peso llm_judge si generador == juez
DETERMINISTIC_FAIL_CAP = 0.49    # techo del score agregado si falla un determinista
PASS_THRESHOLD = 0.7             # passed = gate determinista OK y score >= umbral
```

- Score por caso: `deterministic`/`execution` con checks → `checks_ok / checks_total`
  (float 0..1; `passed` del caso = todos ok); `execution` con `golden_ref` → `1.0` si
  `GoldenResult.ok` sino `0.0`; `llm_judge` → score del juez (0..1, clamp) — si el
  juicio falló (sin endpoint, sin parse), el caso queda `skipped` con `skip_reason` y
  **NO entra al agregado** (no se penaliza al artefacto por fallas del juez).
- Agregado: media ponderada `Σ(weight_i × LEVEL_MULTIPLIERS[level_i] × score_i) /
  Σ(weight_i × LEVEL_MULTIPLIERS[level_i])` sobre casos corridos no-skipped; redondeo a
  4 decimales. Sin casos corridos → `score = None`, `passed = False`,
  `deterministic_gate = "none"`.
- **Guard (KPI-2):** si algún caso `deterministic` corrido tiene `passed == False` →
  `score = min(score, DETERMINISTIC_FAIL_CAP)` y `deterministic_gate = "failed"`; si
  todos pasan → `"passed"`; si no hubo deterministas → `"none"`.
- `passed` global = `deterministic_gate != "failed"` **y** `score is not None` **y**
  `score >= PASS_THRESHOLD`.

### 4.5 `EvalRun` (una línea de `runs.jsonl`)

```json
{"id": "eval-<uuid4-hex>", "started_at": "<iso>", "finished_at": "<iso>",
 "aspect_key": "agent_prompts/developer",
 "trigger": "manual | proposal_before | proposal_after | candidate",
 "proposal_id": null, "artifact_hash": "sha256:<hex> | null",
 "score": 0.83, "passed": true, "deterministic_gate": "passed | failed | none",
 "per_case": [{"case_id": "…", "title": "…", "level": "…", "subject": "…",
               "score": 1.0, "passed": true, "skipped": false, "skip_reason": null,
               "checks": [{"kind": "…", "ok": true, "detail": "…"}],
               "critique": null}],
 "levels": {"deterministic": {"total": 0, "passed": 0},
            "execution": {"total": 0, "passed": 0},
            "llm_judge": {"total": 0, "passed": 0, "skipped": 0}},
 "judge": {"used": false, "model": null, "error": null,
           "rubric_versions": {}, "parse_errors": 0, "self_judge_risk": false},
 "cost": {"tokens_est_in": 0, "tokens_est_out": 0, "duration_ms": 0, "cost_usd": 0.0},
 "budget": {"limit_tokens": 30000, "exhausted": false, "judge_cases_skipped": 0}}
```

`self_judge_risk`: `True` cuando el caller declaró `generator_model` y coincide
(comparación casefold exacta) con el modelo del juez (`config.LOCAL_LLM_MODEL` o el
override) — en ese caso los casos `llm_judge` ponderan
`LEVEL_MULTIPLIERS["llm_judge"] × SELF_JUDGE_MULTIPLIER`. Registro de costos: espejo
del criterio del 167 R7 — el juez local cuesta USD 0; los tokens ESTIMADOS quedan en
`cost` del run y visibles en el panel con `formatTokens`; NO se inventa una vía nueva
de ingesta en `cost_analytics` (las ejecuciones reales de agentes ya se contabilizan
solas por el camino existente; este arnés NO ejecuta agentes).

### 4.6 Rúbricas versionadas (archivos en `backend/evals/rubrics/`)

Formato congelado: **línea 1 EXACTA** `RUBRICA: <id> v<int>` + texto libre con los
criterios. Parser: `re.match(r"^RUBRICA:\s*(\S+)\s+v(\d+)\s*$", primera_línea)`;
archivo que no matchea → se ignora con warning en el resultado de `load_rubrics()`
(tolerante, G15). Los 3 seeds (contenido literal en §F3): `prompt_de_agente.md` (v1),
`leccion_conocimiento.md` (v1), `salida_de_agente.md` (v1). Editar una rúbrica exige
subir `v<int>`: el juicio persiste `rubric_versions` — auditoría de qué versión juzgó
qué (survey RSI: rúbricas evolutivas y auditables > jueces opacos).

### 4.7 Fitness de una propuesta del 167 (qué se evalúa por `artifact_type`)

| artifact_type (167 §4.3) | fitness_before | fitness_after | casos usados |
|---|---|---|---|
| `prompt_file` | contenido ACTUAL del archivo `backend/Stacky/agents/<target_ref>` (si no existe → `before` queda `null` y `metrics.reason="artefacto_inexistente"`… NO: ver regla abajo) | `proposed_content` | SOLO casos `subject=="artifact"` del `aspect_key` correspondiente (comparabilidad exacta before/after) + juez con `prompt_de_agente` |
| `knowledge_note` | no aplica → `before` se persiste `null` (no hay artefacto previo) | `proposed_content` | casos `subject=="artifact"` de `aspect_key=="knowledge_rag"` + juez con `leccion_conocimiento` |
| `free_text` / `flag_change` | no evaluables → la API responde 409 `fitness_not_applicable` | ídem | — |

Regla `prompt_file` sin archivo previo: si el target NO existe en disco, `before` se
persiste con el shape §4.7 del 167 y `score = 0.0`,
`metrics = {"reason": "artefacto_inexistente"}` (comparable: cualquier `after` con
contenido real ganará; consistente con el semantics `absent` del apply del 167 F2).
Además, SOLO para `before` de `prompt_file`, se agrega `metrics.behavior_score`
informativo: el score de los casos `subject=="output"` del mismo `aspect_key` (goldens
del agente vigente). El `after` NO los corre (medir el comportamiento de un candidato
exigiría ejecutar el agente — fuera de scope §7) y lo declara:
`metrics.behavior_cases_skipped = <n>`.

El shape persistido en la propuesta es EXACTAMENTE el del 167 §4.7:

```json
{"score": 0.83, "metrics": {"passed": true, "deterministic_gate": "passed",
  "levels": {…}, "judge_used": true, "behavior_score": 0.9,
  "behavior_cases_skipped": 0},
 "eval_ref": "eval-<uuid4-hex>", "evaluated_at": "<iso utc>"}
```

(`metrics` es el resumen de arriba; el detalle completo vive en el `EvalRun`
referenciado por `eval_ref`.)

### 4.8 Contratos HTTP (blueprint `evolution_fitness`, url_prefix `/evolution` → `/api/evolution/...`)

Gate: `_fitness_enabled() = CENTER && EVAL_HARNESS` (dos flags, gate compuesto en
código — G8). Flag OFF → 404 literal
`{"ok": false, "error": "fitness_disabled", "message": "El arnés de fitness está deshabilitado (STACKY_EVAL_HARNESS_ENABLED)."}`
(salvo `/fitness/health`, siempre 200 — patrón `api/metrics.py:565-573`).

| Método y ruta | ON |
|---|---|
| `GET /api/evolution/fitness/health` | 200 `{"ok": true, "flag_enabled": <bool>, "judge_configured": <bool LOCAL_LLM_ENDPOINT no vacío>}` (health SIEMPRE 200, también OFF) |
| `GET /api/evolution/fitness/cases?aspect_key=&enabled=` | 200 `{"ok": true, "cases": […]}` (`enabled` = `"true"`/`"false"`/ausente) |
| `POST /api/evolution/fitness/cases` | 201 `{"ok": true, "case": {…}}` \| 400 `invalid_case` |
| `PATCH /api/evolution/fitness/cases/<cid>` | 200 caso actualizado \| 404 `case_not_found` \| 400 `invalid_case` (patch permitido SOLO de: `title, checks, rubric_id, weight, enabled, input`; NUNCA delete — archive por `enabled=false`) |
| `POST /api/evolution/fitness/cases/from-incident` body `{"incident_id": "…"}` | 201 caso borrador (`enabled=false`, `origin="incident"`) \| 404 `incident_not_found` |
| `POST /api/evolution/fitness/cases/from-execution` body `{"execution_id": <int>}` | 201 caso borrador (`enabled=false`, `origin="execution"`, output PII-masked) \| 404 `execution_not_found` \| 409 `execution_not_usable` (sin output o status ≠ completed) |
| `POST /api/evolution/fitness/run` body `{"aspect_key": "…", "use_judge": true}` | 200 `{"ok": true, "run": {EvalRun}}` \| 400 `aspect_key_requerido` \| 409 `eval_already_running` |
| `GET /api/evolution/fitness/runs?aspect_key=&limit=20` | 200 `{"ok": true, "runs": […]}` (tail, más nuevo primero; clamp limit 1..100) |
| `GET /api/evolution/fitness/scorecard` | 200 `{"ok": true, "scorecards": [{"aspect_key": "…", "latest": {resumen del último run no-candidate}, "previous_score": 0.8\|null, "delta": 0.03\|null, "history": [{"ts": "…", "score": 0.8}] (≤20, viejo→nuevo), "cases_enabled": n, "cases_total": n}]}` |
| `GET /api/evolution/fitness/rubrics` | 200 `{"ok": true, "rubrics": [{"id": "…", "version": 1, "text": "…"}]}` |
| `POST /api/evolution/proposals/<pid>/fitness` body `{"which": "before"\|"after", "fitness": {shape 167 §4.7}}` | **contrato LITERAL del 167 §8.1 (inyección: el caller ya computó)** — 200 propuesta actualizada \| 404 `proposal_not_found` \| 400 `invalid_payload` (which inválido o fitness sin `score`/`eval_ref`) |
| `POST /api/evolution/proposals/<pid>/fitness/run` body `{"which": "before"\|"after"\|"both", "use_judge": true}` | 200 `{"ok": true, "proposal": {…}, "runs": {"before": {EvalRun}\|null, "after": {EvalRun}\|null}}` \| 404 `proposal_not_found` \| 409 `fitness_not_applicable` (free_text/flag_change) |
| `POST /api/evolution/fitness/evaluate-candidate` body `{"aspect_key": "…", "artifact_text": "…", "case_filter": null\|{...}, "generator_model": null\|"…"}` | **contrato HTTP hacia el 169 (§8.2)** — 200 `{"ok": true, "result": {shape §8.2}}` \| 400 `invalid_payload` |

---

## 5. Fases

Orden por dependencia: **F0 → F1 → F2 → F3 → F4 → F5 → F6 → F7**. F0..F3 no requieren
el 167 en el árbol; **F4, F5 y F6 SÍ** (pre-check obligatorio en cada una:
`test -f "Stacky Agents/backend/services/evolution_store.py"` — si falta, DETENERSE y
reportar "Plan 167 no implementado").

> **Comandos de test:** backend desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend`
> con `.venv\Scripts\python.exe -m pytest tests/<archivo> -q` (Git Bash:
> `cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/<archivo> -q`).
> Frontend desde `Stacky Agents/frontend` con `npx vitest run src/<archivo>`. SIEMPRE
> por archivo (G5). **REGLA DURA de red:** todo test que toque el camino del juez
> monkeypatchea `copilot_bridge.invoke_local_llm` — ningún test del plan abre sockets
> (§2.3).

---

### F0 — Flags del arnés (patrón triple)

**Objetivo (1 frase):** declarar las 3 configuraciones del arnés de fitness con el
patrón triple para que todo quede gateado y editable por UI.
**Valor:** kill-switch por UI; presupuesto del juez gobernado desde el panel del Arnés.

**Archivos a editar (5):** `backend/config.py`, `backend/services/harness_flags.py`,
`backend/services/harness_flags_help.py`, `backend/tests/test_harness_flags.py`
(set `:467`), `backend/tests/test_harness_flags_requires.py` (mapa `:120`).

**Flags (nombres EXACTOS), defaults y excepciones:**

| Flag | type | Default | `requires=` | Excepción dura |
|---|---|---|---|---|
| `STACKY_EVAL_HARNESS_ENABLED` | bool | **ON** | `STACKY_EVOLUTION_CENTER_ENABLED` | ninguna (arnés on-demand de lectura/medición; no aplica cambios) |
| `STACKY_EVAL_JUDGE_ENABLED` | bool | **ON** | `STACKY_EVOLUTION_CENTER_ENABLED` | ninguna — NO aplica la excepción #3 (prerequisito no garantizado) porque sin `LOCAL_LLM_ENDPOINT` **degrada declaradamente** a solo-deterministas sin error (§3.4) |
| `STACKY_EVAL_RUN_TOKEN_BUDGET` | int | `30000` | `STACKY_EVOLUTION_CENTER_ENABLED` | ninguna (presupuesto, no capacidad) |

(G8: las 3 aristas apuntan al ROOT del 167 `STACKY_EVOLUTION_CENTER_ENABLED`,
profundidad 1. El gate compuesto EVAL_HARNESS→dentro-del-código, §4.8.)

**Diff ilustrativo — `config.py`** (insertar inmediatamente DESPUÉS del bloque del Plan
167 — ubicar por el literal `STACKY_EVOLUTION_CYCLE_TOKEN_BUDGET`):

```python
    # ── Plan 168 — Arnés de fitness (serie auto-mejora recursiva 2/4) ──
    # Golden tasks + jerarquía de señal + juez LLM local. Default ON: solo
    # corre on-demand y sin endpoint local degrada a deterministas puros.
    STACKY_EVAL_HARNESS_ENABLED: bool = os.getenv(
        "STACKY_EVAL_HARNESS_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # Juez LLM local (rubricas versionadas). Sin LOCAL_LLM_ENDPOINT el arnés
    # corre igual solo con niveles deterministas y lo declara en el run.
    STACKY_EVAL_JUDGE_ENABLED: bool = os.getenv(
        "STACKY_EVAL_JUDGE_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # Presupuesto de tokens ESTIMADOS por corrida de evals (entrada+salida del juez).
    STACKY_EVAL_RUN_TOKEN_BUDGET: int = int(os.getenv(
        "STACKY_EVAL_RUN_TOKEN_BUDGET", "30000"
    ) or "30000")
```

**`harness_flags.py` — 2 toques:** (a) `_CATEGORY_KEYS`: en la MISMA tupla de `:265`,
inmediatamente después de las 4 entradas del Plan 167 (ubicar por
`"STACKY_EVOLUTION_CYCLE_TOKEN_BUDGET"`):

```python
        "STACKY_EVAL_HARNESS_ENABLED",     # Plan 168 — arnés de fitness (golden tasks)
        "STACKY_EVAL_JUDGE_ENABLED",       # Plan 168 — juez LLM local con rubricas
        "STACKY_EVAL_RUN_TOKEN_BUDGET",    # Plan 168 — presupuesto tokens por corrida
```

(b) `FLAG_REGISTRY`: 3 `FlagSpec` inmediatamente DESPUÉS de los 4 del 167 (ubicar por
`key="STACKY_EVOLUTION_CYCLE_TOKEN_BUDGET"`), `group="global"`:

```python
    FlagSpec(
        key="STACKY_EVAL_HARNESS_ENABLED",
        type="bool", default=True,
        label="Arnés de fitness de agentes",
        description="Golden tasks por agente con jerarquía de señal (deterministas > ejecución > juez LLM), scorecards con tendencia y fitness before/after de las propuestas del Centro de Evolución.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_EVAL_JUDGE_ENABLED",
        type="bool", default=True,
        label="Juez LLM local de evals",
        description="Evalúa artefactos con el modelo local y rubricas versionadas, emitiendo score y crítica textual. Sin endpoint local configurado, el arnés corre igual solo con señales deterministas.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_EVAL_RUN_TOKEN_BUDGET",
        type="int", default=30000,
        label="Presupuesto de tokens por corrida de evals",
        description="Tope de tokens estimados que una corrida puede mandar al juez local. Al agotarse, los casos con juez restantes quedan como omitidos y la corrida lo registra.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
```

**`harness_flags_help.py`:** 3 entradas `PlainHelp` (espejo del formato de las entradas
del 167, insertadas a continuación), lenguaje llano: qué es, efecto ON, efecto OFF,
ejemplo. La de `STACKY_EVAL_JUDGE_ENABLED` DEBE decir en `on_effect` que "si no hay
modelo local configurado, las corridas siguen funcionando solo con los chequeos
automáticos y lo dejan anotado".

**Meta-tests:** en `_CURATED_DEFAULTS_ON` (`test_harness_flags.py:467`) agregar SOLO
las 2 bool: `STACKY_EVAL_HARNESS_ENABLED`, `STACKY_EVAL_JUDGE_ENABLED` (G4). En
`_REQUIRES_MAP_FROZEN` (`test_harness_flags_requires.py:120`) las 3 aristas:

```python
    "STACKY_EVAL_HARNESS_ENABLED": "STACKY_EVOLUTION_CENTER_ENABLED",
    "STACKY_EVAL_JUDGE_ENABLED": "STACKY_EVOLUTION_CENTER_ENABLED",
    "STACKY_EVAL_RUN_TOKEN_BUDGET": "STACKY_EVOLUTION_CENTER_ENABLED",
```

**Tests PRIMERO (TDD):** crear `backend/tests/test_fitness_flags.py` (espejo
estructural de `tests/test_evolution_flags.py` del 167 F0). 7 casos:
1. `test_harness_flag_en_registry` — FlagSpec `STACKY_EVAL_HARNESS_ENABLED` existe, `type=="bool"`, `default is True`, `requires=="STACKY_EVOLUTION_CENTER_ENABLED"`.
2. `test_judge_flag_en_registry` — ídem para `STACKY_EVAL_JUDGE_ENABLED`.
3. `test_budget_flag_int` — `STACKY_EVAL_RUN_TOKEN_BUDGET`: `type=="int"`, `default==30000`.
4. `test_las_3_estan_categorizadas` — las 3 keys en algún valor de `_CATEGORY_KEYS`.
5. `test_config_defaults` — env limpio: HARNESS True, JUDGE True, BUDGET 30000 (leer de `config.config`).
6. `test_aristas_requires_congeladas` — las 3 aristas en `_REQUIRES_MAP_FROZEN` apuntando al ROOT.
7. `test_help_presente` — el dict de `harness_flags_help` contiene las 3 keys.

**Comando (Git Bash):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_fitness_flags.py tests/test_harness_flags.py tests/test_harness_flags_requires.py -q
```
**Criterio BINARIO:** los 3 archivos verdes (foto previa de fallos preexistentes de
`test_harness_flags.py`; criterio = sin regresión vs. foto).
**Flag:** las declaradas acá. **Runtimes:** N/A (declaración). **Trabajo del operador:** ninguno.

---

### F1 — Store de casos: `backend/evals/case_store.py` (EvalCase + seeds idempotentes)

**Objetivo (1 frase):** persistir y validar golden tasks en
`data_dir()/evolution/evals/cases.json`, con seeds generados solos desde los goldens
existentes y los prompts runtime.
**Valor:** el catálogo de casos existe día uno sin que el operador escriba nada.

**Archivo a crear:** `backend/evals/case_store.py`

**Símbolos EXACTOS:**

```python
import runtime_paths                     # data_dir() en CADA llamada (testabilidad)
_EVALS_LOCK = threading.Lock()
VALID_SUBJECTS = ("artifact", "output")
VALID_LEVELS = ("deterministic", "execution", "llm_judge")
VALID_ORIGINS = ("seed", "incident", "execution", "manual")
VALID_INPUT_KINDS = ("artifact_text", "golden_ref", "frozen_output")
PATCHABLE_FIELDS = frozenset({"title", "checks", "rubric_id", "weight", "enabled", "input"})

def evals_root() -> Path                 # runtime_paths.data_dir() / "evolution" / "evals"
def prompts_dir() -> Path                # Path(runtime_paths.backend_root()) / "Stacky" / "agents"
def slug_for_prompt_file(filename: str) -> str
    # "Developer.agent.md" -> "developer"; regla: quitar el sufijo ".agent.md"
    # (case-insensitive) y lowercased. Si no termina en ".agent.md", lower() del stem.
def list_cases(aspect_key: str | None = None, enabled: bool | None = None) -> list[dict]
def get_case(case_id: str) -> dict | None
def create_case(**fields) -> dict
    # Valida §4.2 (subject/level/origin/input.kind en los VALID_*; reglas de la tabla
    # de niveles; checks con kinds de §4.3 — delega la validación de kinds en
    # checks.validate_check_spec de F2). id = "case-<uuid4().hex>" salvo que venga
    # explícito (seeds). ValueError("invalid_case:<campo>") si falla. Llena TODAS las
    # claves de §4.2 con defaults (weight=1.0, enabled=True, source_ref=None).
def patch_case(case_id: str, **patch) -> dict
    # Solo claves de PATCHABLE_FIELDS (otra clave -> ValueError("invalid_case:campo_no_editable")).
    # Revalida el caso completo tras el patch. Actualiza updated_at. KeyError("case_not_found") si no existe.
def ensure_seed_cases() -> list[dict]
    # Idempotente por ID DETERMINISTA (si el id ya existe NO se recrea ni se pisa —
    # respeta ediciones del operador). Dos familias:
    # (a) por cada archivo *.agent.md en prompts_dir() (glob tolerante, G15):
    #     slug = slug_for_prompt_file(nombre); TRES casos:
    #     - id "case-seed-artifact-<slug>-estructura", subject="artifact",
    #       level="deterministic", aspect_key="agent_prompts/<slug>",
    #       agent_type=(slug si slug in agents.registry else None),
    #       input={"kind":"artifact_text","text":None,"golden_name":None},
    #       checks=[{"kind":"min_len","value":200},
    #               {"kind":"regex","pattern":"(?m)^#{1,6}\\s"},
    #               {"kind":"max_len","value":400000}],
    #       title="Estructura mínima del prompt <slug>"
    #     - id "case-seed-artifact-<slug>-rubrica", subject="artifact",
    #       level="llm_judge", rubric_id="prompt_de_agente", mismo aspect_key,
    #       title="Rúbrica de calidad del prompt <slug>"
    # (b) por cada agent_type con golden set (golden_runner.list_agents(), :58) y cada
    #     caso (load_golden_set, :65): id "case-seed-golden-<agent_type>-<name>",
    #     subject="output", level="execution", aspect_key="agent_prompts/<agent_type>",
    #     input={"kind":"golden_ref","text":None,"golden_name":"<name>"}, checks=[],
    #     title="Golden <agent_type>/<name>"
    # (c) UN caso para lecciones: id "case-seed-artifact-leccion-rubrica",
    #     subject="artifact", level="llm_judge", aspect_key="knowledge_rag",
    #     rubric_id="leccion_conocimiento", agent_type=None,
    #     title="Rúbrica de calidad de la lección"
    #     + id "case-seed-artifact-leccion-estructura", level="deterministic",
    #       checks=[{"kind":"min_len","value":40},{"kind":"max_len","value":8000}],
    #       aspect_key="knowledge_rag", title="Estructura mínima de la lección"
    # NOTA seeds (b): NO copian el output (fuente única = el .json del golden en el
    # repo); el runner los resuelve en F2 y si el golden no está (deploy frozen, G15)
    # el caso queda skipped con skip_reason="golden_no_disponible".
def list_aspect_keys() -> list[str]      # únicos de list_cases(), orden alfabético
```

Persistencia: `cases.json` = lista completa (espejo del patrón `proposals.json` del
167); lecturas tolerantes; escrituras bajo `_EVALS_LOCK`. `ensure_seed_cases` se llama
LAZY desde los endpoints de F5 (patrón `ensure_seed_aspects` del 167) — NUNCA en
startup.

**Incidencias como seed automático — decisión con evidencia:** NO. El intake de
incidencias es texto libre + archivos del operador sin estructura de caso
(`incident_store.py:106-164`; status inicial `"capturada"`), y convertirlas en masa
generaría casos podridos (riesgo R4 de §6). Entran SOLO por el botón 1-click de F5
(human-in-the-loop), que es exactamente el flywheel del survey MAPE-K.

**Tests PRIMERO:** `backend/tests/test_fitness_case_store.py`. Fixture común:
`monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)` +
`monkeypatch.setattr(case_store, "prompts_dir", lambda: tmp_path / "agents")` (crear 2
`*.agent.md` sintéticos) + `monkeypatch.setattr(golden_runner, "_AGENTS_DIR", tmp_path / "goldens")`
(crear 1 golden sintético `developer/caso_a.json` con el shape de `golden_runner.py:3-14`).
10 casos:
1. `test_slug_for_prompt_file` — `"Developer.agent.md"→"developer"`, `"BusinessAgent.agent.md"→"businessagent"`, `"raro.md"→"raro"`.
2. `test_seed_idempotente` — 2 llamadas a `ensure_seed_cases` → mismo conteo, ids únicos, sin duplicar.
3. `test_seed_shape_artifact` — el caso `case-seed-artifact-<slug>-estructura` tiene los 3 checks EXACTOS y `subject=="artifact"`.
4. `test_seed_golden_ref` — el caso del golden sintético referencia `golden_name=="caso_a"` sin copiar el output.
5. `test_seed_respeta_ediciones` — editar `weight` de un seed con `patch_case` y re-llamar `ensure_seed_cases` → el weight editado sobrevive.
6. `test_create_case_valida_level` — `level="llm_judge"` sin `rubric_id` → `ValueError("invalid_case:rubric_id")`.
7. `test_create_case_valida_check_kind` — check `{"kind": "magia"}` → `ValueError` con `unknown_check_kind` en el mensaje.
8. `test_patch_case_solo_campos_permitidos` — patch de `aspect_key` → `ValueError("invalid_case:campo_no_editable")`; patch de `enabled=False` OK.
9. `test_list_cases_filtros` — por `aspect_key` y por `enabled` (AND).
10. `test_lecturas_tolerantes` — `cases.json` corrupto → `list_cases() == []` sin excepción.

**Comando (Git Bash):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_fitness_case_store.py -q
```
**Criterio BINARIO:** 10/10 verdes.
**Flag:** módulo puro — N/A. **Runtimes:** N/A. **Trabajo del operador:** ninguno.

---

### F2 — Checks + runner de niveles: `backend/evals/checks.py` y `backend/evals/fitness_runner.py`

**Objetivo (1 frase):** evaluar un texto contra los checks de §4.3 y agregar scores por
la jerarquía de §4.4, produciendo el `EvalRun` §4.5 sin Flask y sin LLM (el juez entra
en F3 como colaborador inyectable).
**Valor:** el corazón determinista del arnés, 100% testeable con `tmp_path`.

**Archivos a crear (2):**

`backend/evals/checks.py`:
```python
VALID_CHECK_KINDS = ("contains", "not_contains", "regex", "min_len", "max_len",
                     "json_valid", "artifact_contract")
def validate_check_spec(spec: dict) -> None      # ValueError("unknown_check_kind:<kind>") / ValueError("invalid_check:<campo>")
def run_check(spec: dict, text: str) -> dict     # {"kind","ok","detail"} según tabla §4.3; NUNCA lanza
def run_checks(specs: list[dict], text: str) -> list[dict]
```
`artifact_contract` importa `contract_validator` LAZY dentro de `run_check` (import de
módulo top-level de `backend/` — los módulos de `evals/` ya lo hacen:
`golden_runner.py:25`).

`backend/evals/fitness_runner.py`:
```python
LEVEL_MULTIPLIERS = {"deterministic": 3.0, "execution": 2.0, "llm_judge": 1.0}
SELF_JUDGE_MULTIPLIER = 0.5
DETERMINISTIC_FAIL_CAP = 0.49
PASS_THRESHOLD = 0.7
_RUN_LOCK = threading.Lock()                     # single-flight de corridas

def _estimate_tokens(text: str) -> int           # max(1, len(text) // 4) — mismo helper del 167 F3

def resolve_case_text(case: dict, artifact_text: str | None) -> str | None
    # input.kind == "artifact_text"  -> artifact_text (None => caso skipped "sin_artefacto")
    # input.kind == "frozen_output"  -> case["input"]["text"]
    # input.kind == "golden_ref"     -> None (lo resuelve run_case vía golden_runner)

def run_case(case: dict, artifact_text: str | None, *, judge_fn=None,
             judge_context: dict | None = None) -> dict
    # Devuelve el elemento per_case de §4.5.
    # level deterministic/execution con checks: run_checks sobre el texto resuelto;
    #   score = ok/total; passed = todos ok.
    # level execution con golden_ref: buscar el GoldenCase por nombre en
    #   golden_runner.load_golden_set(case["agent_type"]) y delegar en
    #   golden_runner._evaluate (:85); score = 1.0 si .ok sino 0.0; golden ausente ->
    #   skipped, skip_reason="golden_no_disponible" (G15).
    # level llm_judge: si judge_fn es None -> skipped, skip_reason="juez_deshabilitado";
    #   si judge_fn devuelve {"error": ...} -> skipped, skip_reason="juez_error:<motivo>";
    #   si devuelve score -> clamp [0,1], critique al per_case. Los checks opcionales
    #   del caso corren IGUAL y su fallo marca passed=False del caso (la señal
    #   determinista embebida manda también acá).

def aggregate(per_case: list[dict], *, self_judge_risk: bool) -> dict
    # Implementa §4.4 EXACTO. Devuelve {"score", "passed", "deterministic_gate", "levels"}.

def run_eval(*, aspect_key: str, cases: list[dict], artifact_text: str | None,
             trigger: str, proposal_id: str | None = None,
             judge_fn=None, generator_model: str | None = None,
             budget_tokens: int = 30000) -> dict
    # 1) if not _RUN_LOCK.acquire(blocking=False): raise RuntimeError("eval_already_running")
    #    (try/finally release).
    # 2) Filtra cases enabled=True. artifact_hash = "sha256:"+hexdigest(artifact_text) si hay texto.
    # 3) Corre casos en orden: deterministic, execution, llm_judge (los baratos primero;
    #    el presupuesto solo limita al juez).
    # 4) Presupuesto: antes de CADA juicio, si tokens_est_acumulados + estimado_del_juicio
    #    > budget_tokens -> caso skipped, skip_reason="budget_exhausted",
    #    budget.exhausted=True, budget.judge_cases_skipped += 1.
    # 5) self_judge_risk = generator_model no nulo y casefold igual al modelo del juez
    #    (lo informa judge_context["model"] que arma F3/F4).
    # 6) aggregate + shape EXACTO §4.5; id="eval-"+uuid4().hex; duration_ms real.
    #    NO persiste (persistir es de fitness_service, F4). Devuelve el dict.
```

**Tests PRIMERO:** `backend/tests/test_fitness_runner.py` (sin red; `judge_fn` siempre
un stub local). 12 casos:
1. `test_checks_contains_y_regex` — tabla §4.3: `contains` case-insensitive, `regex` multiline, `regex` inválida → ok=False con `regex_invalida` en detail (sin excepción).
2. `test_checks_len_y_json` — `min_len`/`max_len`/`json_valid` en ambos sentidos.
3. `test_check_artifact_contract` — monkeypatch de `contract_validator.validate` → respeta `min_score`/`must_pass`.
4. `test_validate_check_spec_desconocido` — `ValueError("unknown_check_kind:magia")`.
5. `test_run_case_deterministic_score_fraccional` — 2 checks, 1 ok → score 0.5, passed False.
6. `test_run_case_golden_ref` — golden sintético (monkeypatch `golden_runner._AGENTS_DIR`) ok → score 1.0; golden ausente → skipped `golden_no_disponible`.
7. `test_run_case_judge_skips` — sin judge_fn → `juez_deshabilitado`; judge_fn que devuelve `{"error": "x"}` → skipped `juez_error:x` y NO cuenta en el agregado.
8. `test_guard_deterministic_cap` — caso deterministic failed + judge_fn stub que da 1.0 → `score <= 0.49`, `deterministic_gate=="failed"`, `passed is False` (**KPI-2**).
9. `test_aggregate_ponderacion` — 1 deterministic score 1.0 (peso 3) + 1 llm_judge score 0.0 (peso 1) → score == 0.75.
10. `test_self_judge_risk_pondera_mitad` — mismo setup con `self_judge_risk` → el peso del juez es 0.5 → score == 6/7 redondeado a 4 decimales (0.8571).
11. `test_budget_agota` — budget chico + 2 casos llm_judge → el 2º queda `budget_exhausted` y `budget.exhausted is True`.
12. `test_reproducibilidad` — 2 llamadas a `run_eval` sin juez sobre el mismo artefacto → `score` y `per_case` (sin ids/timestamps) idénticos (**KPI-1**).

**Comando (Git Bash):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_fitness_runner.py -q
```
**Criterio BINARIO:** 12/12 verdes.
**Flag:** módulo puro — N/A. **Runtimes:** N/A (determinista local). **Trabajo del operador:** ninguno.

---

### F3 — Juez local con rúbricas: `backend/evals/judge.py` + `backend/evals/rubrics/`

**Objetivo (1 frase):** juzgar un texto con el modelo LOCAL y una rúbrica versionada,
devolviendo score + crítica textual, con degradación declarada si no hay endpoint.
**Valor:** la señal semántica del arnés sin atarse a ningún runtime de agentes y sin
costo USD.

**Archivos a crear:** `backend/evals/judge.py` + 3 rúbricas seed en
`backend/evals/rubrics/` (`.md` fuera de `docs/` — G10).

**Rúbricas seed (contenido LITERAL; línea 1 es el header parseable §4.6):**

`backend/evals/rubrics/prompt_de_agente.md`:
```
RUBRICA: prompt_de_agente v1
Evaluás el PROMPT DE SISTEMA de un agente de Stacky. Buscá defectos concretos, no elogios.
Criterios (cada uno pesa igual):
1. Rol y objetivo: el prompt define QUIÉN es el agente y QUÉ debe lograr, sin ambigüedad.
2. Contrato de salida: formato de salida esperado explícito (secciones, JSON, artefactos) y verificable.
3. Límites y rieles: dice qué NO debe hacer (no inventar datos, no salirse del alcance, human-in-the-loop).
4. Accionabilidad: instrucciones ejecutables por un modelo menor sin inferir contexto no dado.
5. Consistencia interna: sin instrucciones contradictorias ni redundancia que diluya las reglas.
Devolvé score entre 0 y 1 (promedio de criterios) y una crítica que liste los defectos más graves con la frase exacta del prompt que los causa.
```

`backend/evals/rubrics/leccion_conocimiento.md`:
```
RUBRICA: leccion_conocimiento v1
Evaluás una LECCIÓN de conocimiento propuesta para el corpus de Stacky. Buscá defectos concretos.
Criterios:
1. Hecho durable: enuncia un hecho/patrón reutilizable, no una anécdota puntual sin generalidad.
2. Accionable: un agente que la lea sabe qué hacer distinto la próxima vez.
3. Verificable: cita el contexto que la origina (síntoma, módulo, condición) de forma chequeable.
4. Autocontenida: se entiende sin leer la conversación que la parió.
Devolvé score entre 0 y 1 y una crítica con los defectos concretos.
```

`backend/evals/rubrics/salida_de_agente.md`:
```
RUBRICA: salida_de_agente v1
Evaluás la SALIDA producida por un agente de Stacky frente a su tarea. Buscá defectos concretos.
Criterios:
1. Completitud: responde TODO lo pedido, sin partes omitidas en silencio.
2. Estructura: respeta el formato/contrato de salida del agente.
3. Veracidad interna: sin afirmaciones inventadas ni referencias a cosas que no están en la entrada.
4. Señal/ruido: sin relleno; lo importante es localizable.
Devolvé score entre 0 y 1 y una crítica con los defectos concretos.
```

**`judge.py` — símbolos EXACTOS:**

```python
_RUBRICS_DIR = Path(__file__).resolve().parent / "rubrics"
_RUBRIC_HEADER_RE = re.compile(r"^RUBRICA:\s*(\S+)\s+v(\d+)\s*$")
_JUDGE_SYSTEM = (
    "Sos el JUEZ del arnés de fitness de Stacky. Recibís una RUBRICA y un TEXTO a "
    "evaluar. Tu única tarea es aplicar la rúbrica al texto. Respondé SOLO JSON con "
    'el shape {"score": <float 0..1>, "critique": "<defectos concretos>"} sin '
    "markdown ni texto extra. Sé severo: tu valor está en ENCONTRAR errores."
)

def load_rubrics(rubrics_dir: Path | None = None) -> dict[str, dict]
    # dir ausente -> {} (G15). Por cada *.md cuyo header línea-1 matchea
    # _RUBRIC_HEADER_RE: {id: {"id", "version": int, "text": <archivo completo>,
    # "path": str}}. Archivo sin header válido -> se ignora.

def judge_model() -> str                 # str(getattr(config, "LOCAL_LLM_MODEL", "") or "")

def judge_text(*, rubric: dict, text: str, case_title: str) -> dict
    # user = f"RUBRICA:\n{rubric['text']}\n\nCASO: {case_title}\n\nTEXTO A EVALUAR:\n{text}"
    # from copilot_bridge import invoke_local_llm   (import LAZY dentro de la función)
    # invoke_local_llm(agent_type="fitness_judge", system=_JUDGE_SYSTEM, user=user,
    #                  on_log=lambda level, msg: None, execution_id=None, model=None)
    # RuntimeError (endpoint no configurado / caído — copilot_bridge.py:257-262) ->
    #   {"error": str(exc), "score": None, "critique": None, "model": judge_model(),
    #    "tokens_est_in": _est(user)+_est(_JUDGE_SYSTEM), "tokens_est_out": 0}
    # Respuesta: parse tolerante del primer '{' de resp.text; sin parse o sin "score"
    #   numérico -> {"error": "judge_parse_error", ...} (cuenta en judge.parse_errors).
    # OK -> {"error": None, "score": clamp(float, 0, 1), "critique": str(critique)[:2000],
    #        "model": judge_model(), "tokens_est_in": ..., "tokens_est_out": _est(resp.text)}
```

**Tests PRIMERO:** `backend/tests/test_fitness_judge.py` (monkeypatch de
`copilot_bridge.invoke_local_llm` SIEMPRE — cero red, §2.3). 8 casos:
1. `test_load_rubrics_seed` — las 3 rúbricas del repo cargan con ids `prompt_de_agente/leccion_conocimiento/salida_de_agente` y `version == 1`.
2. `test_load_rubrics_dir_ausente` — dir inexistente → `{}` sin excepción (G15).
3. `test_load_rubrics_header_invalido` — archivo sin header → ignorado.
4. `test_judge_text_ok` — mock devuelve `{"score": 0.8, "critique": "flojo en límites"}` → score 0.8, critique presente, error None.
5. `test_judge_text_clamp` — mock devuelve score 1.7 → 1.0; score -0.2 → 0.0.
6. `test_judge_text_runtime_error_degrada` — mock lanza `RuntimeError("LOCAL_LLM_ENDPOINT no está configurado…")` → `error` no nulo, score None (**KPI-3**).
7. `test_judge_text_parse_error` — mock devuelve prosa sin JSON → `error == "judge_parse_error"`.
8. `test_judge_model_es_local` — `judge_model()` devuelve `config.LOCAL_LLM_MODEL` (monkeypatch del atributo) — el juez NUNCA consulta el runtime de agentes.

**Comando (Git Bash):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_fitness_judge.py -q
```
**Criterio BINARIO:** 8/8 verdes.
**Flag:** `STACKY_EVAL_JUDGE_ENABLED` la aplica F4 (el módulo es puro).
**Impacto por runtime:** idéntico en los 3 — el juez es el modelo local, jamás el
runtime que ejecuta agentes. **Fallback:** sin endpoint → los callers reciben `error` y
el runner marca skipped (degradación declarada). **Trabajo del operador:** ninguno
(opcional: configurar modelo local, capacidad preexistente de los Planes 106/127).

---

### F4 — Servicio de fitness: `backend/services/fitness_service.py` (scorecards + contrato 167 + contrato 169)

**Objetivo (1 frase):** orquestar corridas (casos + juez + presupuesto), persistir
`EvalRun`s, computar scorecards con tendencia, llenar `fitness_before/after` de
propuestas del 167 SIN aplicarlas, y exponer `evaluate_candidate` para el 169.
**Valor:** el enchufe que convierte el arnés en la señal del Centro de Evolución.

**Pre-check:** exige `services/evolution_store.py` en el árbol (Plan 167). Si falta →
DETENERSE.

**Archivo a crear:** `backend/services/fitness_service.py`

**Símbolos EXACTOS:**

```python
from config import config as _cfg        # G1

def _budget() -> int                     # int(getattr(_cfg, "STACKY_EVAL_RUN_TOKEN_BUDGET", 30000))
def _judge_enabled() -> bool             # bool(getattr(_cfg, "STACKY_EVAL_JUDGE_ENABLED", False))
def _make_judge_fn(use_judge: bool)      # None si (not use_judge or not _judge_enabled());
    # si no: closure que resuelve la rúbrica del caso vía judge.load_rubrics() y llama
    # judge.judge_text; rúbrica inexistente -> {"error": "rubrica_no_encontrada:<id>"}.

def run_scorecard(*, aspect_key: str, use_judge: bool = True) -> dict
    # ensure_seed_cases(); cases = list_cases(aspect_key=aspect_key, enabled=True).
    # artifact_text: si aspect_key startswith "agent_prompts/" y existe el archivo
    #   <ArchivoReal>.agent.md cuyo slug coincide (iterar prompts_dir().glob("*.agent.md")
    #   y comparar slug_for_prompt_file) -> read_text(utf-8); si no, None (los casos
    #   subject=artifact quedarán skipped "sin_artefacto").
    # run = fitness_runner.run_eval(..., trigger="manual", judge_fn=..., budget_tokens=_budget())
    # append a runs.jsonl (bajo _EVALS_LOCK, vía case_store helpers de persistencia:
    #   def append_run(run) / def read_runs_tail(aspect_key=None, limit=20) — AGREGARLOS
    #   en case_store.py en esta fase, mismos contratos tolerantes §4.1).
    # Devuelve el run completo.

def evaluate_candidate(aspect_key: str, artifact_text: str,
                       case_filter: dict | None = None,
                       generator_model: str | None = None,
                       use_judge: bool = True) -> dict
    # CONTRATO HACIA EL 169 (§8.2 — NO cambiar firma ni shape).
    # cases = list_cases(aspect_key=aspect_key, enabled=True) filtrados a
    #   subject=="artifact" (un candidato es TEXTO; sus behaviors no son medibles acá);
    #   case_filter opcional: {"ids": [...]} interseca por id, {"levels": [...]} por level.
    # run = run_eval(..., trigger="candidate", generator_model=generator_model, ...).
    # append_run(run). Devuelve:
    # {"score": run["score"], "passed": run["passed"], "eval_ref": run["id"],
    #  "per_case": run["per_case"],
    #  "critiques": [c["critique"] for c in per_case si critique no nulo],
    #  "cost": run["cost"], "deterministic_gate": run["deterministic_gate"]}

def compute_proposal_fitness(proposal_id: str, which: str = "both",
                             use_judge: bool = True) -> dict
    # p = evolution_store.get_proposal(...); None -> KeyError("proposal_not_found").
    # artifact_type free_text/flag_change -> ValueError("fitness_not_applicable").
    # prompt_file: aspect_key = "agent_prompts/" + slug_for_prompt_file(p["target_ref"]);
    #   before_text = contenido actual del target (allowlist ANTI path-traversal:
    #   resolver (prompts_dir()/target_ref) y exigir prefijo prompts_dir() + sufijo
    #   ".agent.md" — espejo EXACTO del guard del 167 F2; fuera de allowlist ->
    #   ValueError("target_fuera_de_allowlist")); inexistente -> before shape con
    #   score 0.0 y metrics.reason="artefacto_inexistente" (§4.7); after_text =
    #   p["proposed_content"].
    # knowledge_note: aspect_key = "knowledge_rag"; before NO se computa (queda como
    #   está, null); after_text = p["proposed_content"].
    # Por cada lado pedido en which ("before"/"after"/"both"):
    #   run = run_eval(cases subject=="artifact", trigger="proposal_before|proposal_after",
    #                  proposal_id=..., artifact_text=<lado>, ...)
    #   (para before de prompt_file: correr ADEMÁS los casos subject=="output" en un
    #    run auxiliar SOLO para metrics.behavior_score; el after registra
    #    behavior_cases_skipped = len(esos casos) — §4.7)
    #   fitness = {"score": run["score"] if not None else 0.0,
    #              "metrics": {...resumen §4.7...}, "eval_ref": run["id"],
    #              "evaluated_at": iso_utc_now()}
    #   evolution_store.update_proposal_fields(proposal_id, fitness_before=fitness) (o after)
    # PROHIBIDO tocar el estado de la propuesta, escribir el archivo target o llamar
    # a evolution_apply: el sandbox de evaluación es solo-lectura del artefacto.
    # Devuelve {"proposal": <dict actualizado>, "runs": {"before": run|None, "after": run|None}}.

def inject_proposal_fitness(proposal_id: str, which: str, fitness: dict) -> dict
    # Contrato LITERAL 167 §8.1 (inyección para el 169): valida which in ("before","after")
    # y fitness con claves "score" numérica y "eval_ref" str no vacía ->
    # ValueError("invalid_payload:<campo>") si falla; completa "evaluated_at" si falta;
    # update_proposal_fields(...). Devuelve la propuesta actualizada.

def build_scorecards() -> list[dict]
    # shape EXACTO de la fila de §4.8 GET /fitness/scorecard: por aspect_key de
    # list_aspect_keys(): runs = read_runs_tail(aspect_key, 21) EXCLUYENDO
    # trigger=="candidate" (los candidatos del 169 no contaminan la tendencia);
    # latest = runs[0] resumido; previous_score = runs[1]["score"] si existe;
    # delta = latest - previous si ambos no-None (4 decimales); history = hasta 20
    # (viejo->nuevo) con {"ts": finished_at, "score": score}.
```

**Tests PRIMERO:** `backend/tests/test_fitness_service.py` (fixtures: `data_dir` →
`tmp_path`; `case_store.prompts_dir` → tmp; `golden_runner._AGENTS_DIR` → tmp;
`copilot_bridge.invoke_local_llm` → mock; sembrar una propuesta real con
`evolution_store.create_proposal` — el 167 en el árbol). 10 casos:
1. `test_run_scorecard_persiste_run` — corre y `read_runs_tail` lo devuelve con `trigger=="manual"`.
2. `test_judge_flag_off_no_llama_llm` — monkeypatch `_cfg.STACKY_EVAL_JUDGE_ENABLED=False` + mock del bridge con contador → 0 llamadas, run completa con casos juez skipped `juez_deshabilitado`.
3. `test_compute_fitness_prompt_file_both` — propuesta `prompt_file` con target sintético existente → `fitness_before` y `fitness_after` con shape §4.7 (claves `score/metrics/eval_ref/evaluated_at`), `eval_ref` distinto entre before y after (**KPI-4**).
4. `test_compute_fitness_no_aplica_nada` — tras `both`, el archivo target queda **byte-idéntico** y `p["status"]` NO cambió (**KPI-4**, sandbox).
5. `test_compute_fitness_target_inexistente` — before con `score == 0.0` y `metrics["reason"] == "artefacto_inexistente"`.
6. `test_compute_fitness_path_traversal` — `target_ref="../../config.py"` → `ValueError("target_fuera_de_allowlist")` y cero lecturas fuera.
7. `test_compute_fitness_free_text_rechaza` — `ValueError("fitness_not_applicable")`.
8. `test_behavior_score_solo_before` — con 1 golden sintético: `fitness_before.metrics.behavior_score` no nulo y `fitness_after.metrics.behavior_cases_skipped >= 1`.
9. `test_evaluate_candidate_contrato` — firma con los 5 parámetros de §8.2; retorno con EXACTAMENTE las claves `score/passed/eval_ref/per_case/critiques/cost/deterministic_gate`; `critiques` lista de strings; el run persistido tiene `trigger=="candidate"` (**KPI-6**).
10. `test_inject_proposal_fitness_valida` — payload sin `eval_ref` → `ValueError("invalid_payload:eval_ref")`; válido → la propuesta lo persiste tal cual.

**Comando (Git Bash):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_fitness_service.py -q
```
**Criterio BINARIO:** 10/10 verdes.
**Flag:** `STACKY_EVAL_JUDGE_ENABLED` (gate del juez); el gate HTTP maestro va en F5.
**Impacto por runtime:** idéntico en los 3 (backend local). **Fallback:** juez caído →
runs deterministas (declarado en `judge`). **Trabajo del operador:** ninguno.

---

### F5 — API Flask: `backend/api/evolution_fitness.py` + flywheel 1-click + registro

**Objetivo (1 frase):** exponer los contratos §4.8 gateados por flag, incluidos el
endpoint del contrato 167 y el flywheel incidencia/ejecución→caso borrador.
**Valor:** panel (F6) y optimizador (169) tienen su superficie HTTP completa.

**Pre-check:** exige `api/evolution.py` en el árbol (Plan 167 F4).

**Archivo a crear:** `backend/api/evolution_fitness.py`

```python
from flask import Blueprint, jsonify, request
from config import config as _cfg                       # G1

bp = Blueprint("evolution_fitness", __name__, url_prefix="/evolution")

def _fitness_enabled() -> bool:
    return bool(getattr(_cfg, "STACKY_EVOLUTION_CENTER_ENABLED", False)) and \
           bool(getattr(_cfg, "STACKY_EVAL_HARNESS_ENABLED", False))

def _disabled_resp():
    return jsonify({"ok": False, "error": "fitness_disabled",
                    "message": "El arnés de fitness está deshabilitado (STACKY_EVAL_HARNESS_ENABLED)."}), 404
```

Rutas EXACTAS de §4.8 (imports de `services`/`evals` LAZY dentro de cada handler —
patrón del 167 F4). Mapeos de error congelados: `KeyError("proposal_not_found")` → 404;
`ValueError` cuyo mensaje empieza con `invalid_case`/`invalid_payload` → 400 con ese
`error`; `ValueError("fitness_not_applicable")` → 409; `ValueError("target_fuera_de_allowlist")`
→ 400 `invalid_payload`; `RuntimeError("eval_already_running")` → 409
`eval_already_running`. `GET /fitness/health` responde SIEMPRE 200 con
`{"ok": True, "flag_enabled": _fitness_enabled(), "judge_configured": bool(getattr(_cfg, "LOCAL_LLM_ENDPOINT", ""))}`.

**Flywheel 1-click (handlers de `from-incident` / `from-execution`):**

- `from-incident`: `incident_store.get_incident(incident_id)` (`:196`); None → 404. Crea
  vía `case_store.create_case` un caso `origin="incident"`, `enabled=False` (BORRADOR —
  human-in-the-loop §3.3), `subject="output"`, `level="deterministic"`,
  `aspect_key="knowledge_rag"`, `agent_type=None`,
  `input={"kind": "frozen_output", "text": <texto compuesto>, "golden_name": None}`,
  `checks=[{"kind": "min_len", "value": 1}]` (placeholder editable),
  `source_ref=f"incident:{incident_id}"`,
  `title=f"Caso desde incidencia: {incident.get('title') or incident_id}"`. El
  `<texto compuesto>` = `redact_irreversible(` título + `"\n\n"` + texto del intake
  (clave `"text"` del incident dict; ausente → `""`) `)` (G14). El operador luego lo
  edita/habilita en el panel (F6) — el botón solo CREA el borrador.
- `from-execution`: espejo de la validación de `harvest.py:62-92` (`session_scope` +
  `session.get(AgentExecution, execution_id)`): None → 404 `execution_not_found`;
  `status != "completed"` o sin `output` → 409 `execution_not_usable`. Crea caso
  `origin="execution"`, `enabled=False`, `subject="output"`, `level="execution"`,
  `aspect_key=f"agent_prompts/{exec_row.agent_type}"`, `agent_type=exec_row.agent_type`,
  `input={"kind": "frozen_output", "text": redact_irreversible(exec_row.output), "golden_name": None}`,
  `checks=[{"kind": "artifact_contract", "agent_type": exec_row.agent_type, "min_score": 0, "must_pass": True}]`,
  `source_ref=f"execution:{execution_id}"` (NO se usa `harvest()` directamente porque
  escribe goldens al árbol del repo — `harvest.py:116-123` —, inválido en deploy
  frozen; el caso runtime vive en `data_dir()`, G15; `harvest` sigue disponible por CLI
  para goldens de repo, sin cambios).

**Registro — `backend/api/__init__.py` (2 líneas):** tras la línea del 167
`from .evolution import bp as evolution_bp` agregar
`from .evolution_fitness import bp as evolution_fitness_bp  # Plan 168 — arnés de fitness`
y tras `api_bp.register_blueprint(evolution_bp)` agregar
`api_bp.register_blueprint(evolution_fitness_bp)  # Plan 168 — /api/evolution/fitness/...`.
(Dos blueprints con el MISMO url_prefix `/evolution` y nombres distintos: válido en
Flask; las rutas no colisionan — las del 167 no incluyen `/fitness/*` ni
`/proposals/<pid>/fitness*`.)

**Tests PRIMERO:** `backend/tests/test_fitness_endpoints.py` (fixtures
`app_flag_off`/`app_flag_on` espejo del patrón del 167 F4 — attr
`STACKY_EVAL_HARNESS_ENABLED` con el master del 167 ON en ambos; + `data_dir→tmp_path`
+ mocks de bridge). 12 casos:
1. `test_health_200_flag_off` — 200 y `flag_enabled False`.
2. `test_cases_404_flag_off` — `GET /api/evolution/fitness/cases` → 404 `fitness_disabled` (**KPI-5**).
3. `test_cases_lista_con_seeds` — flag ON → 200 y los seeds (a)+(c) presentes (con `prompts_dir` mockeado a 1 archivo).
4. `test_crear_y_patchear_caso` — POST 201 → PATCH `enabled=false` 200 → GET con `enabled=false` lo contiene.
5. `test_patch_campo_prohibido_400` — PATCH `aspect_key` → 400 `invalid_case`.
6. `test_from_incident_crea_borrador` — con incidencia sintética en `data_dir` (crear con `incident_store.create_incident`) → 201, caso `enabled is False`, `origin=="incident"`, `source_ref` correcto.
7. `test_from_execution_valida` — execution inexistente → 404; no completada → 409 `execution_not_usable` (sembrar con sqlite de test, espejo del patrón de `tests/` para `AgentExecution`).
8. `test_run_y_runs_tail` — `POST /fitness/run` con aspect sembrado → 200 con shape §4.5; `GET /fitness/runs` lo lista.
9. `test_scorecard_delta` — 2 runs del mismo aspect → `scorecards[0].delta == round(s2-s1, 4)` y `history` viejo→nuevo.
10. `test_evaluate_candidate_http` — POST con `artifact_text` → 200 con `result.score/critiques/eval_ref` (**KPI-6**).
11. `test_proposal_fitness_run_both` — propuesta `prompt_file` sembrada → 200, `fitness_before/after` en la propuesta (shape §4.7) y target intacto (**KPI-4**).
12. `test_proposal_fitness_inject_contrato_167` — `POST /proposals/<pid>/fitness` con `{"which": "after", "fitness": {...}}` → 200 y persiste; body inválido → 400 `invalid_payload`.

**Comando (Git Bash):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_fitness_endpoints.py -q
```
**Criterio BINARIO:** 12/12 verdes.
**Flag:** `STACKY_EVAL_HARNESS_ENABLED` (+ master 167) — gating 404 testeado.
**Runtimes:** N/A (API local). **Trabajo del operador:** ninguno.

---

### F6 — Panel: sección "Fitness" en `EvolutionCenterPage` + modelo puro TS

**Objetivo (1 frase):** scorecards con tendencia, curación de casos y botón "Evaluar
fitness" de propuestas, como sección nueva del panel del 167 (sin refactorizarlo).
**Valor:** la señal visible donde se decide: el Centro de Evolución.

**Pre-check:** exige `frontend/src/pages/EvolutionCenterPage.tsx` en el árbol (167 F6).

**Archivos a crear (3):** `frontend/src/evolution/fitnessModel.ts`,
`frontend/src/evolution/FitnessSection.tsx`,
`frontend/src/evolution/FitnessSection.module.css`.
**Archivos a editar (2):** `frontend/src/api/endpoints.ts` (namespace nuevo
`EvolutionFitness`, espejo del namespace `Evolution` del 167 F5, con métodos:
`health`, `cases(q)`, `createCase(body)`, `patchCase(id, body)`,
`fromIncident(incidentId)`, `fromExecution(executionId)`, `run(aspectKey, useJudge)`,
`runs(aspectKey, limit)`, `scorecard()`, `rubrics()`,
`proposalFitnessRun(proposalId, which, useJudge)` — cada uno `fetch` a la ruta EXACTA
de §4.8 con el mismo estilo de manejo `{ok, status, data}` del 167);
`frontend/src/pages/EvolutionCenterPage.tsx` (2 toques quirúrgicos, anclar por
contenido: (1) import de `FitnessSection`; (2) render de `<FitnessSection />` como
ÚLTIMA sección de la página, después de la sección del Ledger del 167).

**`fitnessModel.ts` — símbolos EXACTOS (funciones puras, testeables sin RTL/jsdom):**

```typescript
export type SignalLevel = "deterministic" | "execution" | "llm_judge";
export interface EvalCaseDto { id: string; aspect_key: string; agent_type: string | null; subject: "artifact" | "output"; level: SignalLevel; title: string; checks: Record<string, unknown>[]; rubric_id: string | null; weight: number; origin: "seed" | "incident" | "execution" | "manual"; enabled: boolean; source_ref: string | null; created_at: string; updated_at: string; }
export interface EvalRunSummaryDto { id: string; finished_at: string; aspect_key: string; trigger: string; score: number | null; passed: boolean; deterministic_gate: "passed" | "failed" | "none"; }
export interface ScorecardDto { aspect_key: string; latest: EvalRunSummaryDto | null; previous_score: number | null; delta: number | null; history: { ts: string; score: number | null }[]; cases_enabled: number; cases_total: number; }

export function levelLabel(l: SignalLevel): string
  // deterministic→"Determinista"; execution→"Ejecución"; llm_judge→"Juez LLM".
export function levelTone(l: SignalLevel): "success" | "info" | "warning"
  // deterministic→"success"; execution→"info"; llm_judge→"warning" (jerarquía visible).
export function gateLabel(g: "passed" | "failed" | "none"): string
  // passed→"Deterministas OK"; failed→"Determinista FALLÓ"; none→"Sin deterministas".
export function scoreDisplay(s: number | null): string
  // null→"—"; si no → s.toFixed(2) (score 0..1; NO usar Intl — ratchet del 161).
export function deltaDisplay(d: number | null): string
  // null→""; d>0→`▲ +${d.toFixed(2)}`; d<0→`▼ ${d.toFixed(2)}`; 0→"= 0.00".
export function deltaTone(d: number | null): "success" | "danger" | "neutral"
export function aspectLabel(key: string): string
  // "agent_prompts/<slug>"→"Prompt: <slug>"; "knowledge_rag"→"Lecciones (RAG)"; otro→key.
export function canEvaluateProposal(artifactType: string, status: string): boolean
  // artifactType ∈ {"prompt_file","knowledge_note"} y status ∈ {"draft","pending_review","approved"}.
```

**`FitnessSection.tsx` (estructura; TODO estilo en el `.module.css` — G6; CERO
pollers — G9):**
- On-mount: `EvolutionFitness.health()`; si `flag_enabled === false` → no renderiza
  nada (`return null`). Si ON: `Promise.all([scorecard(), cases({})])` con estados
  `loading` (`SkeletonList`), `error` (banner + "Reintentar"), `data`.
- **Scorecards** (`SectionHeader` "Fitness de agentes" + grid de `Card` por aspecto):
  `aspectLabel`, score grande (`scoreDisplay`), `StatusChip` con `gateLabel`, delta
  (`deltaDisplay` + tono), "casos: {enabled}/{total}", mini-historial textual (últimos
  scores separados por "·"), tokens del último run (`formatTokens`), y botón "Correr
  evals" (`Button` + `Spinner` mientras corre; POST síncrono; al volver, refresh; 409 →
  Toast warning "Ya hay una corrida en curso"). Si `health.judge_configured === false`,
  chip informativo "Juez local sin configurar — solo señales deterministas" (tone
  `neutral`; la degradación es visible, no muda).
- **Casos** (colapsable, lazy on-expand): tabla `Título / Aspecto / Nivel
  (StatusChip levelTone) / Origen / Peso / Estado`; toggle habilitar-deshabilitar
  (deshabilitar con `ConfirmButton` — archive, nunca delete); borradores del flywheel
  (`enabled=false` + origin incident/execution) resaltados con chip "Borrador — revisá
  y habilitá". Formulario "Nuevo caso" (colapsable) con primitivas del 162 (`Field` +
  `Input`/`Select`/`Textarea`; validación inline título/aspect_key obligatorios; foco
  al primer error con `firstErrorFieldId`).
- **Rúbricas** (colapsable, lazy): lista read-only `id vN` + `<pre>` con el texto
  (auditable a la vista; editar = editar el archivo versionado, fuera de la UI en v1).
- En la tabla de PROPUESTAS del 167 NO se toca nada en esta fase salvo el botón:
  agregar en la fila expandida (ancla por contenido: el bloque de detalle que muestra
  `proposed_content`) un `Button` "Evaluar fitness (before/after)" visible cuando
  `canEvaluateProposal(...)`, que llama
  `EvolutionFitness.proposalFitnessRun(p.id, "both", true)` y refresca — la celda
  Fitness del 167 (`fitnessDisplay`) empieza a mostrar valores reales sin cambiarle el
  código.

**Tests PRIMERO:** `frontend/src/evolution/fitnessModel.test.ts` (vitest puro). 8 casos:
1. `levelLabel`/`levelTone` los 3 niveles exactos.
2. `gateLabel` los 3 valores.
3. `scoreDisplay(null) === "—"` y `scoreDisplay(0.8347) === "0.83"`.
4. `deltaDisplay` positivo/negativo/cero/null con los literales EXACTOS.
5. `deltaTone` los 3 tonos.
6. `aspectLabel` las 3 formas.
7. `canEvaluateProposal` — tabla de verdad: `("prompt_file","approved")→true`, `("free_text","approved")→false`, `("prompt_file","applied")→false`.
8. Inmutabilidad de helpers (los DTOs de entrada no se mutan).

**Comandos (BINARIO, Git Bash):**
```bash
cd "Stacky Agents/frontend" && npx vitest run src/evolution/fitnessModel.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
cd "Stacky Agents/frontend" && npx vitest run src/__tests__/uiDebtRatchet.test.ts
grep -c "setInterval" "Stacky Agents/frontend/src/evolution/FitnessSection.tsx"   # debe dar 0
```
**Criterio BINARIO:** 8/8 + tsc exit 0 + ratchet UI verde + grep `0`. Smoke visual del
operador: declarado pendiente-de-operador (patrón disclosure Plan 111; RTL/jsdom no
están en `package.json` — gap estructural conocido).
**Flag:** con `STACKY_EVAL_HARNESS_ENABLED` OFF el health devuelve `flag_enabled false`
y la sección no renderiza (cero fetchs extra).
**Impacto por runtime:** idéntico (panel web). **Trabajo del operador:** ninguno.

---

### F7 — Cierre: ratchet + estado del doc + verificación final

**Objetivo (1 frase):** registrar los 6 tests nuevos en el ratchet, sincronizar el
estado del doc y correr la verificación completa por archivo.

**Archivos a editar:** `backend/scripts/run_harness_tests.sh` (dentro de
`HARNESS_TEST_FILES=(`, `:20`, zona reciente `:460`) y
`backend/scripts/run_harness_tests.ps1` (`:414`): bloque nuevo "Plan 168" con los 6
archivos: `tests/test_fitness_flags.py`, `tests/test_fitness_case_store.py`,
`tests/test_fitness_runner.py`, `tests/test_fitness_judge.py`,
`tests/test_fitness_service.py`, `tests/test_fitness_endpoints.py` (mismo estilo de
las entradas vecinas). Este doc: actualizar `**Estado:**` al cerrar (regla de la casa).

**Comandos de cierre (todos por archivo, todos verdes):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_fitness_flags.py -q
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_fitness_case_store.py -q
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_fitness_runner.py -q
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_fitness_judge.py -q
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_fitness_service.py -q
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_fitness_endpoints.py -q
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_harness_flags.py -q
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_harness_flags_requires.py -q
cd "Stacky Agents/frontend" && npx vitest run src/evolution/fitnessModel.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
```
**Criterio BINARIO:** los 10 comandos exit 0 (fallos preexistentes de
`test_harness_flags.py`: cuenta la foto previa de F0). **Trabajo del operador:** ninguno.

---

## 6. Riesgos y mitigaciones

- **R1 — Reward hacking / rúbrica gameada (survey RSI failure #3).** El juez NUNCA
  decide solo: deterministas ponderan 3×, gate duro `DETERMINISTIC_FAIL_CAP` (KPI-2),
  rúbricas versionadas en archivos auditables con `rubric_versions` persistido por
  juicio. Cambiar la rúbrica exige subir versión → el drift queda visible en los runs.
- **R2 — Self-confirming loop (survey failure #1).** Juez = modelo LOCAL, distinto de
  los runtimes generadores. Para el caso residual (artefacto redactado por el mismo
  modelo local — p. ej. drafts del ciclo 167 con `llm_used=true`, o candidatos del
  169), el caller declara `generator_model` y el arnés aplica `SELF_JUDGE_MULTIPLIER`
  0.5 + `self_judge_risk=true` visible (test F2 caso 10). La señal determinista, que no
  comparte pesos con nadie, sigue mandando.
- **R3 — Juez local caído/no configurado.** Degradación declarada (KPI-3): RuntimeError
  del bridge → casos juez `skipped` con razón, run válido, chip visible en el panel.
  Timeout ya acotado por `LOCAL_LLM_TIMEOUT_SEC` (`copilot_bridge.py:265`). Nunca un
  run roto por el juez.
- **R4 — Casos podridos (garbage in).** Los seeds son deterministas y mínimos; el
  flywheel crea SOLO borradores `enabled=false` que el operador cura (human-in-the-loop);
  los casos nunca se borran, se deshabilitan (auditable). No hay ingesta masiva
  automática de incidencias (decisión con evidencia en F1).
- **R5 — Costo del juez.** Presupuesto por corrida (`STACKY_EVAL_RUN_TOKEN_BUDGET`,
  editable por UI) con corte declarado (`budget_exhausted`); juez local = USD 0; tokens
  estimados visibles en panel (espejo del criterio 167 R7). Sin scheduler: solo
  on-demand.
- **R6 — before/after incomparables.** Regla dura §4.7: ambos lados corren EXACTAMENTE
  los casos `subject=="artifact"` del mismo `aspect_key`; el comportamiento histórico
  entra solo como `metrics.behavior_score` informativo del before y el after declara
  `behavior_cases_skipped`. Nada de comparar peras con manzanas en silencio.
- **R7 — Evaluar ≠ aplicar (sandbox).** `compute_proposal_fitness` es solo-lectura del
  artefacto: prohibido llamar `evolution_apply`, prohibido escribir el target (test F4
  caso 4 verifica byte-identidad). Allowlist anti path-traversal espejo del 167 F2
  (test F4 caso 6).
- **R8 — Deploy frozen sin fixtures del repo.** Toda resolución es tolerante (G15):
  goldens ausentes → `skipped:golden_no_disponible`; rúbricas ausentes → juez reporta
  `rubrica_no_encontrada`; los casos runtime viven en `data_dir()`. Nada crashea.
- **R9 — Números de línea que rotan (sesiones paralelas).** Citas orientativas: anclar
  SIEMPRE por contenido/símbolo (regla heredada 128/167). WIP ajeno: G12.
- **R10 — `runs.jsonl` crece.** Append-only aceptado en v1 (KB de texto); los tails
  clampan `limit`. Particionar/compactar sería un plan futuro — NO acá.

## 7. Fuera de scope (explícito)

- **Optimizador evolutivo (generate→evaluate→select→archive): Plan 169.** Acá solo vive
  su enchufe (`evaluate_candidate` §8.2 + inyección §4.8). PROHIBIDO implementar
  generación de candidatos, selección Pareto o lineage.
- **Flywheel completo de conocimiento (lección→curación→corpus RAG→contexto): Plan
  170.** Acá solo el botón fallo→caso-borrador.
- **Ejecutar agentes REALES con un prompt candidato (sandbox de ejecución).** Medir el
  comportamiento de un candidato exige correr el agente: costo/latencia de runtime CLI
  y aislamiento que este plan no introduce. El fitness v1 de candidatos es
  artefacto-céntrico (deterministas + juez) y lo DECLARA (`behavior_cases_skipped`).
- **Meta-evaluación de jueces (juzgar al juez, Meta-Rewarding).** Documentado como
  dirección futura; v1 se cubre con jerarquía + versionado de rúbricas.
- **Tocar la suite de tests del repo (ratchet/fixtures/guard de red): Plan 154** (§2.3).
- **Scheduler/cron/daemon de evals** (on-demand only; no existe scheduler genérico).
- **Editor de rúbricas en la UI** (v1: archivos versionados en el repo, visibles
  read-only en el panel).
- Notificaciones (152), auth/RBAC, react-router.

## 8. Contratos hacia 169 / 170 (congelados acá, implementados allá)

### 8.1 ← Plan 167 (lo que este plan HONRA, nombres del 167)

- Llena `fitness_before` / `fitness_after` con el shape EXACTO del 167 §4.7
  (`score/metrics/eval_ref/evaluated_at`) vía `evolution_store.update_proposal_fields`.
- Implementa el endpoint placeholder del 167 §8.1: `POST
  /api/evolution/proposals/<id>/fitness` body `{"which": "before"|"after", "fitness":
  {…}}` — literal.
- Reusa `backend/evals/` sin reescribirlo (golden_runner/harvest/eval_gate intactos).
- Cumple la regla de separación del 167 §8.1: evaluador ≠ generador; deterministas
  rankean por encima de jueces LLM (§4.4).

### 8.2 → Plan 169 (optimizador evolutivo — NO diseñarlo acá)

**Función (firma y semántica CONGELADAS):**

```python
fitness_service.evaluate_candidate(
    aspect_key: str,              # p. ej. "agent_prompts/developer"
    artifact_text: str,           # el candidato COMPLETO (texto)
    case_filter: dict | None = None,   # {"ids": [...]} y/o {"levels": [...]}
    generator_model: str | None = None,  # modelo que GENERÓ el candidato (anti self-judge)
    use_judge: bool = True,
) -> {"score": float | None,     # 0..1, DETERMINISTIC_FAIL_CAP aplicado
      "passed": bool,
      "eval_ref": str,           # id del EvalRun persistido (trigger="candidate")
      "per_case": [...],         # detalle §4.5 per_case
      "critiques": [str, ...],   # feedback textual del juez (insumo GEPA del loop reflexivo)
      "cost": {"tokens_est_in": int, "tokens_est_out": int, "duration_ms": int, "cost_usd": 0.0},
      "deterministic_gate": "passed" | "failed" | "none"}
```

Semántica que el 169 puede asumir: solo casos `subject=="artifact"` habilitados;
determinismo con `use_judge=False` (misma entrada → mismo score, KPI-1); los runs
`trigger=="candidate"` NO contaminan la tendencia del scorecard; el resultado se
inyecta a una propuesta con `POST /proposals/<id>/fitness` (§4.8) o
`inject_proposal_fitness`. Espejo HTTP: `POST /api/evolution/fitness/evaluate-candidate`.
El loop generate→evaluate→select, el archive Pareto y el lineage
(`parent_proposal_id`) viven en el 169; sus propuestas entran `pending_review` — el
gate humano del 167 no cambia.

### 8.3 → Plan 170 (flywheel de conocimiento)

- Este plan deja: `from-incident`/`from-execution` (fallo→caso borrador) y la rúbrica
  `leccion_conocimiento` que evalúa lecciones ANTES de aplicarse (fitness del
  `knowledge_note`).
- El 170 conecta el resto (lección aplicada → curación → promoción a `docs/rag/` —
  SIEMPRE `.jsonl/.json/.txt`, riel G11 del 167). Reservado para el 170: valor
  `origin="lesson"` en `EvalCase` (NO agregarlo a `VALID_ORIGINS` ahora; queda
  documentado que el 170 lo agrega con su migración).

## 9. Glosario (para un modelo menor)

| Término | Definición |
|---|---|
| **golden task / EvalCase** | Caso de evaluación versionado: input + checks/rúbrica + peso + origen. El conjunto de casos de un aspecto es su "golden set". |
| **fitness** | Score objetivo 0..1 de un artefacto (prompt, lección) producido por el arnés: media ponderada por nivel de señal, con gate determinista. Llena `fitness_before/after` del 167. |
| **jerarquía de señal** | Orden de confiabilidad de la verificación (survey RSI): checks deterministas (3×) > ejecución congelada (2×) > juez LLM (1×). La señal fuerte SIEMPRE manda sobre la débil. |
| **check determinista** | Verificación sin LLM (contains/regex/longitud/JSON/contrato). Gratis, reproducible, imposible de "convencer". |
| **LLM-as-judge / juez** | El modelo LOCAL (`invoke_local_llm`) aplicando una rúbrica a un texto y devolviendo score + crítica. Nunca es el runtime que generó el artefacto. |
| **rúbrica** | Criterios de juicio en un archivo versionado (`RUBRICA: <id> v<n>`), auditable y evolutivo. El juicio registra qué versión usó. |
| **crítica (critique)** | El "por qué" textual del juez. Tan valiosa como el score (GEPA): es el insumo del optimizador 169. |
| **EvalRun / scorecard** | Una corrida persistida del arnés (scores por caso + agregado + costo) / el resumen por aspecto con tendencia (delta vs corrida anterior). |
| **baseline / tendencia** | Score de la corrida anterior no-candidata del mismo aspecto; el delta ▲/▼ muestra si el aspecto mejora o empeora. |
| **sandbox de evaluación** | Evaluar un artefacto SIN aplicarlo: el fitness de una propuesta se computa leyendo el artefacto vigente y el propuesto, jamás escribiéndolos. |
| **flywheel fallo→eval** | Convertir un fallo real (incidencia, ejecución) en caso de eval permanente con 1 click; nace borrador y lo confirma el operador. |
| **self-judge risk** | El generador del artefacto y el juez son el mismo modelo → el peso del juicio cae a la mitad y queda marcado (anti self-confirming loop). |
| **degradación declarada** | Sin endpoint LLM local, el arnés corre igual solo-deterministas y lo registra (`judge.used=false`) — nunca rompe, nunca miente. |
| **aspecto / aspect_key** | Área evaluable: `agent_prompts/<slug>` (un prompt de agente) o `knowledge_rag` (lecciones). Mapea a los aspectos del 167. |
| **subject artifact/output** | `artifact` = se evalúa el TEXTO del artefacto (comparable before/after); `output` = se evalúa un comportamiento congelado del agente vigente (informativo). |

## 10. Orden de implementación

1. **F0** — flags + config + help + meta-tests (foto previa de `test_harness_flags.py`).
2. **F1** — case_store + seeds idempotentes + 10 tests.
3. **F2** — checks + fitness_runner (jerarquía, cap, presupuesto) + 12 tests.
4. **F3** — rúbricas seed + judge + 8 tests.
5. **F4** — fitness_service (scorecards, contrato 167, contrato 169) + 10 tests. *(Requiere 167 en el árbol.)*
6. **F5** — API + flywheel + registro de blueprint + 12 tests. *(Requiere 167.)*
7. **F6** — fitnessModel + FitnessSection + wiring EvolutionCenterPage + 8 tests + tsc. *(Requiere 167.)*
8. **F7** — ratchet (sh + ps1) + estado del doc + corrida completa de cierre.

## 11. Definición de Hecho (DoD)

- [ ] Las 3 flags con patrón triple completo (config + FlagSpec + `_CATEGORY_KEYS` +
      help + curated + requires al ROOT del 167), editables desde la UI del Arnés;
      `harness_defaults.env` NO tocado a mano (G11).
- [ ] Los 6 archivos de test backend verdes POR ARCHIVO (59 casos: 7+10+12+8+10+12),
      registrados en `HARNESS_TEST_FILES` (sh + ps1); `fitnessModel.test.ts` (8) verde;
      `npx tsc --noEmit` exit 0; `uiDebtRatchet` verde.
- [ ] KPI-1: dos corridas sin juez → resultado idéntico. KPI-2: determinista fallado →
      `score ≤ 0.49` con juez en 1.0. KPI-3: sin endpoint local → run completo con
      `judge.used=false`. KPI-4: `fitness_before/after` shape 167 §4.7 y target
      byte-idéntico. KPI-6: `evaluate_candidate` con firma/shape §8.2.
- [ ] Con `STACKY_EVAL_HARNESS_ENABLED=false`: endpoints (salvo `/fitness/health`) →
      404 `fitness_disabled`; la sección Fitness no renderiza; resto byte-idéntico.
- [ ] Ningún test del plan abre red: `invoke_local_llm` monkeypatcheado en TODOS los
      tests que tocan el camino del juez (§2.3).
- [ ] Cero pollers nuevos: `grep -c "setInterval" frontend/src/evolution/FitnessSection.tsx` → 0.
- [ ] El arnés no corre en startup ni en background: `ensure_seed_cases`/`run_eval`
      solo tienen callers en los módulos del plan (api/services/evals) y en tests.
- [ ] Los seeds se generan solos (lazy) y re-llamar `ensure_seed_cases` no pisa
      ediciones del operador.
- [ ] Casos del flywheel nacen `enabled=false` y solo el operador los habilita
      (human-in-the-loop verificado por test F5 caso 6).
- [ ] `python -m evals run all` y `eval_gate` siguen funcionando igual que hoy (cero
      cambios de comportamiento en el módulo existente).
- [ ] Encabezado `**Estado:**` de este doc actualizado al cerrar; `git status` final
      con WIP ajeno intacto (G12).
