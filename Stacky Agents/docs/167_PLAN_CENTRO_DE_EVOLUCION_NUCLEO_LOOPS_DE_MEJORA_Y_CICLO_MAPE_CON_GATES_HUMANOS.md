# Plan 167 — Centro de Evolución: núcleo del panel de auto-mejora, registro de loops de mejora y ciclo MAPE con gates humanos

**Estado:** CRITICADO v2 (2026-07-18) — v1 RECHAZADO (1 bloqueante C1 + 5 importantes); v2 aplica todos los fixes → APTO PARA IMPLEMENTAR · **Autor:** StackyArchitectaUltraEficientCode · **Juez:** crítica adversarial 2026-07-18
**Serie:** "Auto-mejora recursiva" **1 de 4** (directiva del operador 2026-07-17):
**167 (este)** = núcleo del panel + registro de propuestas + ciclo MAPE con gates humanos ·
**168** = arnés de evaluación/fitness (golden tasks + jueces) ·
**169** = optimizador evolutivo GEPA-style (generate→evaluate→select→archive) ·
**170** = flywheel de conocimiento (fallo→lección→corpus RAG→contexto de agentes).
Este documento implementa SOLO el 167 y deja los **contratos** hacia 168/169/170 en §8
(campos placeholder, endpoint de inyección, destino del flywheel). PROHIBIDO implementar
acá nada de los otros tres planes.

## Versión: v1 -> v2 (crítica adversarial aplicada)

**CHANGELOG v1 -> v2 (veredicto v1: RECHAZADO — 1 bloqueante, 5 importantes, 4 menores, 2 adiciones):**

- **C1 (BLOQUEANTE, F0):** el FlagSpec de `STACKY_EVOLUTION_CYCLE_TOKEN_BUDGET` declaraba
  `default=20000` → `test_default_known_only_for_curated` rompe DETERMINISTA:
  `default_is_known` es type-agnostic (`spec.default is not None`,
  `harness_flags.py:3397-3399`) y G4 prohíbe curar ints. Fix: FlagSpec int SIN `default=`
  (precedente real `CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES`, `harness_flags.py:350-358`:
  el default efectivo vive en `config.py` y la description lo documenta); test F0 caso 4
  ahora exige `default is None`. **IMPACTO SERIE: 168/169/170 (v1) copian este patrón —
  sus FlagSpec `type="int"` (y toda no-bool-ON) tampoco deben declarar `default=`.**
- **C2 (IMPORTANTE, F1):** `update_proposal_fields(**patch)` aceptaba cualquier clave
  existente (p.ej. `status`, `applied_at`) = bypass in-process de la máquina de estados
  sin ledger. Fix: allowlist dura `_PATCHABLE_FIELDS` + test caso 13. Compatible con el
  168 (persiste `fitness_before/after` por esta vía — están en la allowlist).
- **C3 (IMPORTANTE, F2):** apply/rollback sin lock end-to-end → dos POST concurrentes
  (doble click / dos pestañas) duplicaban el side-effect y el 2º snapshot pisaba al 1º
  (rollback restauraría el contenido YA aplicado: KPI-3 roto bajo carrera). Fix:
  `_APPLY_LOCK` + re-chequeo de status dentro del lock + test caso 11.
- **C4 (IMPORTANTE, F3):** `_ERROR_STATUSES = ("error",)` omitía `"failed"`
  (`agent_runner.py:117`) → R-A1 subcontaba fallos reales. Fix: `("error", "failed")` +
  fixture mixto en el caso 3.
- **C5 (IMPORTANTE, F3):** corridas MAPE sucesivas re-emitían el mismo draft mientras la
  condición persistiera → spam de duplicados en la bandeja (= trabajo extra del operador,
  propuestas stale sin política). Fix: dedup por `(aspect_id, evidence[0])` contra
  propuestas abiertas + clave `skipped_duplicate_rules` en §4.9 + caso 12.
- **C6 (IMPORTANTE, F2/§4.3/§4.8):** drift de artefacto sin detección (el archivo cambia
  entre propuesta y apply, o entre apply y rollback — sesión paralela u otra propuesta).
  Fix: clave `base_hash` (sha256 opcional) en §4.3 + chequeo en apply → 409
  `target_drifted`; rollback compara el hash actual vs `proposed_content` y exige
  `{"force": true}` para pisar ediciones posteriores; casos 12-13 de F2. §8.2 recomienda
  al 169 enviar `base_hash`.
- **C7 (MENOR, F2):** `maybe_auto_apply` tragaba excepciones sin rastro → ahora deja
  evento `apply_failed` best-effort en el ledger.
- **C8 (MENOR, F3):** el truncado por presupuesto partía el JSON sin marcador → sufijo
  literal `[TRUNCADO_POR_PRESUPUESTO]`.
- **C9 (MENOR, DoD):** el grep "run_cycle sin callers" filtraba con `grep -v evolution`
  (excluía cualquier path que contenga "evolution") → pathspec afinado.
- **C10 (MENOR, §8.2):** el 169 v1 inyecta por llamada de servicio in-process
  (`evolution_store.create_proposal`), no por HTTP → §8.2 declara AMBAS vías válidas
  (misma validación).
- **[ADICIÓN ARQUITECTO] A1 — Kill-switch env-only `STACKY_EVOLUTION_HARD_DISABLE`:**
  freno de emergencia FUERA del alcance de cualquier propuesta o flag del registry (una
  propuesta `flag_change` puede sugerir tocar las flags del propio Centro; el kill-switch
  no es alcanzable desde la app). Helper único `evolution_store.evolution_hard_disabled()`;
  con env truthy: endpoints (salvo `health`, que reporta `hard_disabled`) → 404,
  `run_cycle` y `apply_proposal`/`maybe_auto_apply` rechazan. Permitido por el riel de la
  casa (kill-switches internos pueden ser env-only). **CONTRATO NUEVO §8.0: 168/169/170
  componen su `_enabled()` con este helper (1 línea c/u).**
- **[ADICIÓN ARQUITECTO] A2 — Espejo de auditoría en logs del sistema:** `append_ledger`
  emite además UNA línea INFO por `logging.getLogger("stacky.evolution")` → cada gate
  humano queda visible en la página de logs (Plan 145) sin infra nueva (caso 14 de F1).
- Conteos actualizados: tests backend **59 casos (8+14+14+12+11)**; frontend sin cambio
  de conteo (los DTO nuevos son type-only, los verifica `tsc`).

> Este documento está redactado para que un **MODELO MENOR** (Haiku, Codex CLI o
> GitHub Copilot Pro) lo implemente **SIN inferir nada**. Los nombres de símbolos,
> rutas, shapes JSON, literales de mensajes y comandos son **LITERALES**: prohibido
> desviarse de los nombres exactos, prohibido "mejorar" el alcance. Todo lo ambiguo ya
> fue decidido acá. Cada afirmación sobre código existente está anclada a
> `archivo:línea` **verificada el 2026-07-17**; este repo tiene sesiones paralelas, así
> que TODA edición se ancla por el CONTENIDO/símbolo citado, nunca solo por el número
> de línea. Los comandos con `&&` se ejecutan en **Git Bash** (en PowerShell 5.1 `&&`
> es error de parser).

**Dependencias (todas verificadas, ninguna dura — el plan reusa, no bloquea):**

| Sustrato | Anclaje verificado | Rol en el 167 |
|---|---|---|
| `data_dir()` | `backend/runtime_paths.py:48` | Raíz de persistencia: `data_dir()/evolution/` |
| Patrón store en data dir (Plan 131) | `backend/services/incident_store.py:6-9` (layout), `:33` (`_LEDGER_LOCK`), `:196/:206/:230` (`get/update/list`) | F1 espeja el patrón (JSON tolerante + lock) |
| `invoke_local_llm` | `backend/copilot_bridge.py:241-263` (firma; RuntimeError si `LOCAL_LLM_ENDPOINT` vacío `:257-262`), `BridgeResponse` `:124-128` (`text/format/metadata`) | F3 Analyze: enriquecimiento LLM opcional con degradación declarada |
| `cost_analytics` | `backend/services/cost_analytics.py:35-43` (`CostRow`: `runtime/model/tokens_in/tokens_out/cost_usd/cost_kind`), `:138-150` (`ExecRecord`), `:154-164` (`CostFilters`), `:167` (`load_records`), `:213` (`_billable`) | F3 Monitor: señal de costos y de ejecuciones con UNA query |
| Tablero de Planes (Plan 128, IMPLEMENTADO) | `backend/services/plans_board.py:118` (`next_free_number`), `:378` (`get_board_cached`) | F3 Monitor: señal del pipeline de planes; aspecto seed `stacky_codebase` SOLO enlaza (read-only) |
| Incidencias (Planes 131/160/166) | `backend/services/incident_store.py:230` (`list_incidents`) | F3 Monitor: señal de incidencias |
| Flags patrón triple | `backend/services/harness_flags.py:21` (`FlagSpec`), `:117` (`_CATEGORY_KEYS`), `:265` (tupla que contiene `STACKY_PLANS_BOARD_ENABLED`), `:331` (nota "toda flag nueva…"), `:3267` (FlagSpec `STACKY_PLANS_BOARD_ENABLED`, espejo), `:3336` (precedente requires→ROOT, profundidad 1), `type="int"` soportado (`:352` y 4 más) | F0 |
| Meta-tests de flags | `backend/tests/test_harness_flags.py:467` (`_CURATED_DEFAULTS_ON`), `backend/tests/test_harness_flags_requires.py:120` (`_REQUIRES_MAP_FROZEN`) | F0 |
| Ayuda llana de flags | `backend/services/harness_flags_help.py:1376` (entrada `PlainHelp` del Plan 166, ancla de inserción) | F0 |
| Ratchet de tests | `backend/scripts/run_harness_tests.sh:20` (`HARNESS_TEST_FILES=(`, última entrada `:458`), `backend/scripts/run_harness_tests.ps1:412` | F7 |
| Registro de blueprints | `backend/api/__init__.py:61` (import `incidents_bp`), `:122` (register), `:125-127` (health raíz) | F4 |
| Patrón health de panel | `backend/api/metrics.py:565-573` (`_cost_center_enabled` + `/cost-center/health` SIEMPRE 200) | F4 |
| Gotcha `config` vs `config.config` | `backend/api/tickets.py:7401` usa `config.config.STACKY_…` (G1 del Plan 166) | F2/F3/F4 |
| Router casero + tab gateado | `frontend/src/App.tsx:43` (union `Tab`), `:45` (`TAB_PATHS`), `:64` (`tabFromPath`), `:101` (`planesEnabled`), `:134-151` (probes), `:213-221` (fallback+deps), `:252` (render), `:394-397` (botón nav legacy) | F6 |
| `probeFlagHealth` (Plan 135) | `frontend/src/utils/flagHealth.ts:34` | F6 |
| App Shell v2 (Plan 139, flag OFF) | `frontend/src/components/shell/shellNav.ts:5-8` (`ShellTab`), `:15-32` (`TAB_META`), `:40-46` (`SHELL_NAV_GROUPS`), `:48-55` (`VisibilityInput`), `:62-74` (`computeVisibleTabs`); test `frontend/src/components/shell/__tests__/shellNav.test.ts:11-15` (`ALL_TABS`) | F6: el tab se ve en AMBAS navegaciones |
| Primitivas UI (Planes 138+162) | `frontend/src/components/ui/index.ts:7-34` (barrel: `Button/IconButton/StatusChip/Card/SectionHeader/Tabs/Skeleton/Spinner/Field/Input/Select/Textarea/Checkbox`, `firstErrorFieldId`) | F6 |
| Estados universales (Plan 140) | `frontend/src/components/EmptyState.tsx` + `frontend/src/components/SkeletonList` (tests `components/__tests__/EmptyState.presets.test.ts:7`, `SkeletonList.test.ts:8`); NO están en el barrel (nota `components/ui/index.ts:3-4`) | F6 |
| Formato humano (Plan 161) | `frontend/src/services/format.ts:40-118` (`formatDate/formatTime/formatDateTime/formatDuration/formatCostUsd/formatTokens/formatInt/formatBytes/formatPercent/formatDurationBetween`) | F6 |
| Acciones seguras (Plan 136) | `frontend/src/components/ConfirmButton.tsx:23` (`export default function ConfirmButton`) | F6 |
| Toast (Plan 135) | `frontend/src/components/Toast.tsx:9-19` (`ToastVariant`, `ToastState`, default export; patrón component-local) | F6 |
| Query params (receptor informal) | `frontend/src/utils/queryParams.ts:6-12` (`parseQueryParam`/`readQueryParam`, citado por el Plan 165 §2.2) | F6: deep-link `?proposal=` |
| Prompts runtime de agentes | `backend/Stacky/agents/` (verificado en disco: `BusinessAgent.agent.md`, `Developer.agent.md`, `DevOpsAgent.agent.md`, `Documentador.agent.md`, `FunctionalAnalyst.agent.md`, `IncidentAnalyst.agent.md`, `QAUat1.agent.md`, `manifest.json`) | F2: allowlist del handler `prompt_file` |
| Evals existentes (semilla del 168) | `backend/evals/` (verificado: `golden_runner.py`, `eval_gate.py`, `harvest.py`, `extraction_golden_runner.py`, `catalog_diff_runner.py`, `__main__.py`, fixtures por agente) | §8: el arnés 168 nace de acá; el 167 NO lo toca |
| Ledger de supervisión | `Stacky Agents/docs/_supervision/ledger.json` (existe, verificado) | Read-only vía Tablero 128; el 167 NO lo lee directo |
| Corpus RAG | `Stacky Agents/docs/rag/` (verificado: `rag_corpus.jsonl`, `schema.json`, `manifest.json`, `README.txt`) | §8: destino del flywheel 170; el 167 escribe lecciones en `data_dir()`, NO en `docs/` |
| `AgentExecution` | `backend/models.py:207` | F3 Monitor (vía `cost_analytics.load_records`, sin query propia) |

**Ortogonal a (NO tocar, NO depender):** Planes 153/154/156/163/164/165 (pendientes de
implementar — este plan se ALINEA a sus contratos sin bloquearlos ni ser bloqueado: ver
§3.G9 y §3.G10). Plan 152 (centro de notificaciones, pendiente). Plan 158/159 (telemetría
CLI / catálogo de modelos).

---

## 1. Objetivo + KPI / impacto esperado

**Objetivo (1 párrafo):** Stacky ya es un sistema que se auto-mejora — el pipeline
proponer→criticar→implementar→supervisar produjo 167 planes, hay un tablero que lo
visualiza (Plan 128), un módulo de evals (`backend/evals/`), memoria colaborativa,
telemetría de costos (Plan 142) y un ciclo de incidencias (131/160/166) — pero **el loop
de mejora del PROPIO Stacky no tiene superficie en la app**: las oportunidades de mejora
viven en la memoria del asistente y en chats, no hay registro estructurado de "propuestas
de mejora" con estado/auditoría/rollback, y ninguna pieza lee la telemetría que YA existe
para proponer el siguiente paso. Este plan instala el **Centro de Evolución**: (a) un
modelo de datos de **aspectos mejorables** (4 seeds), **propuestas de mejora** con máquina
de estados `draft→pending_review→approved→applied→rejected/rolled_back` y **corridas de
ciclo MAPE**; (b) un **ciclo MAPE on-demand** (Monitor lee SOLO telemetría existente,
Analyze aplica reglas deterministas + enriquecimiento LLM local opcional, Plan emite
borradores de propuesta, Execute aplica SOLO tras aprobación del operador, con snapshot y
rollback 1-click); (c) un **ledger de evolución append-only** que audita cada transición;
(d) un **panel** visible en las dos navegaciones con gates humanos explícitos; y (e) los
**contratos congelados** que los planes 168 (fitness), 169 (optimizador) y 170 (flywheel)
van a consumir. La **escalera de cierre de loop** queda codificada: `human_in_the_loop`
default para todo; `human_on_the_loop` SOLO para lecciones de conocimiento reversibles
detrás de flag default OFF; `closed_loop` **PROHIBIDO para siempre** en Stacky.

**KPIs binarios:**

- **KPI-1 — Gobernanza total:** ninguna propuesta se aplica sin pasar por `approved`
  (test: `apply` desde cualquier otro estado → 409 `invalid_transition`) y CADA
  transición queda en `ledger.jsonl` (test de conteo de eventos). Comando:
  `.venv\Scripts\python.exe -m pytest tests/test_evolution_store.py -q` → exit 0.
- **KPI-2 — Ciclo MAPE acotado:** `run_cycle` sobre fixtures dispara las reglas
  deterministas esperadas, crea SOLO borradores (`status=="draft"`), no aplica nada,
  respeta el presupuesto de tokens y NO duplica borradores abiertos en corridas
  sucesivas (C5). Comando:
  `.venv\Scripts\python.exe -m pytest tests/test_evolution_cycle.py -q` → exit 0.
- **KPI-3 — Reversibilidad:** para `prompt_file`, `apply`→`rollback` deja el archivo
  **byte-idéntico** al original; para `knowledge_note`, `rollback` elimina exactamente la
  lección agregada. Comando:
  `.venv\Scripts\python.exe -m pytest tests/test_evolution_apply.py -q` → exit 0.
- **KPI-4 — Cero regresión:** con `STACKY_EVOLUTION_CENTER_ENABLED=false` los endpoints
  (salvo `/health`) devuelven 404, el tab no se renderiza en ninguna de las dos
  navegaciones y el resto de la app queda byte-idéntico. Comandos:
  `.venv\Scripts\python.exe -m pytest tests/test_evolution_endpoints.py -q` → exit 0 y
  `npx tsc --noEmit` → exit 0.
- **KPI-5 — Contratos hacia 168/169 vivos día uno:** `POST /api/evolution/proposals` con
  `origin="optimizer"` es aceptado, y toda propuesta nace con `fitness_before=null`,
  `fitness_after=null`, `parent_proposal_id=null` (los llenan los planes 168/169).
  Cubierto por `tests/test_evolution_endpoints.py` (caso 7) y
  `tests/test_evolution_store.py` (caso 5).

**KPIs de impacto (proyectados, verificables por observación):**

| Métrica | Hoy | Con el plan |
|---|---|---|
| Superficie en la app del loop de mejora de Stacky | 0 (vive en memoria del asistente + chats) | 1 panel con aspectos, propuestas, ciclo y ledger |
| Auditoría de "quién aprobó/aplicó qué mejora y cuándo" | inexistente | `ledger.jsonl` append-only, visible en el panel |
| Rollback de una mejora aplicada | manual (buscar el estado anterior a mano) | 1 click (snapshot automático al aplicar) |
| Requests de red del panel por tick | — | **0 pollers** (carga on-mount + refresh manual + refresh post-acción; alineado al espíritu del Plan 156) |
| Contrato para inyectar propuestas del optimizador (169) | inexistente | `POST /api/evolution/proposals` con `origin="optimizer"` |

---

## 2. Por qué ahora / gap que cierra

**Evidencia local (planes recientes leídos):** el Plan 128 (IMPLEMENTADO) visualiza el
pipeline de planes pero es **solo lectura de docs/**: no registra propuestas de mejora de
otros aspectos (prompts, flags/modelos, conocimiento), no tiene ciclo que lea telemetría,
no tiene rollback. El Plan 142 (IMPLEMENTADO) produce la telemetría de costos que nadie
consume para decidir mejoras. Los Planes 131/160/166 cierran el ciclo de incidencias del
PROYECTO del operador, pero ninguna pieza convierte esas señales en mejoras del PROPIO
Stacky. `backend/evals/` existe con runners golden (semilla natural del arnés 168) pero
está desconectado de cualquier loop. El gap real: **Stacky no tiene dónde registrar,
gobernar ni auditar su propia evolución** — y la serie 167-170 lo cierra empezando por el
riel de gobernanza (este plan), porque sin gates humanos y auditoría primero, un
optimizador (169) sería irresponsable.

**Fundamento de diseño (investigación citada por nombre — cada hallazgo mapea a una
decisión concreta de este plan):**

1. **Survey RSI (arXiv 2607.07663, jul 2026)** — *"harness as primary artifact"*: el loop
   (trigger, objetivo, verificación, stopping rule, memoria) debe ser un artefacto
   inspeccionable y versionable → acá el loop ES datos (`aspects.json`, `proposals.json`,
   `cycles.jsonl`, `ledger.jsonl`) visibles en un panel. *"No external signal, no
   reliable improvement"*: la calidad de la señal es el techo → el Monitor lee SOLO
   telemetría determinista que ya existe (costos, ejecuciones, incidencias, tablero de
   planes) y el fitness formal queda para el 168; el LLM redacta, **nunca decide**.
   *La masa de la industria está en human-on-the-loop con gates de auditoría* → escalera
   de cierre de loop por aspecto (§3.1) con `closed_loop` prohibido.
2. **AlphaEvolve (Google DeepMind, 2025)** — loop generate→evaluate→select con
   evaluadores automáticos como fitness, RSI acotada y medida en producción → este plan
   construye el **registro y los gates** sobre los que el 169 montará ese loop; el shape
   `fitness_before/after` (§4.7) es el enchufe.
3. **Darwin Gödel Machine (Sakana AI, 2025)** — archive/lineage expansivo de variantes,
   todo en sandbox y trazable → las propuestas **nunca se borran** (rechazadas quedan
   archivadas con razón) y `parent_proposal_id` existe desde el día uno para el lineage
   del 169.
4. **GEPA (Cerebras/DSPy)** — evolución reflexiva de **artefactos de texto** (prompts,
   skills, políticas) leyendo trazas completas; 100-500 evals, no 10K → los aspectos seed
   priorizan artefactos de texto (`agent_prompts`, `knowledge_rag`) y el ciclo declara
   **presupuesto de tokens** configurable (§F0), no fuerza bruta.
5. **Flywheel MAPE-K (arXiv 2510.27051 + práctica LangChain/Arize/NVIDIA)** — ciclo
   Monitor→Analyze→Plan→Execute sobre Knowledge compartido; señales = éxito/fallo,
   trazas, costos; *"cada fallo de producción se convierte en caso de eval permanente"*;
   automatizado lo de bajo riesgo, human-gated lo demás → las 4 fases del ciclo (§F3) y
   la escalera (§3.1) son la traducción literal a los rieles de Stacky.
6. **Sakana RSI Lab (2026)** — eficiencia muestral sobre fuerza bruta; aprender
   estructuradamente de los fallos; *"responsible RSI is what makes capability
   sustainable"* → salvaguardas por diseño: ledger append-only, snapshots, allowlist
   dura para human-on-the-loop, prohibición explícita de closed-loop.

---

## 3. Principios y guardarraíles (NO negociables)

1. **Escalera de cierre de loop POR ASPECTO** (traducción de la taxonomía del survey a
   los rieles de Stacky):

   | Nivel | Qué significa en Stacky | Estado en este plan |
   |---|---|---|
   | `human_in_the_loop` | TODA aplicación de una propuesta pasa por Aprobar (click del operador) y Aplicar (click del operador). | **Default de los 4 aspectos.** |
   | `human_on_the_loop` | El sistema aplica solo y el operador audita/revierte después. | SOLO artefactos **reversibles de bajo riesgo**: lecciones de conocimiento (`knowledge_note` del aspecto `knowledge_rag`), detrás de `STACKY_EVOLUTION_AUTO_APPLY_KNOWLEDGE_ENABLED` **default OFF** citando la **EXCEPCIÓN DURA #1 (bypass de revisión humana)**. Allowlist dura en código: `_HOTL_ALLOWED_ASPECTS = frozenset({"knowledge_rag"})`. |
   | `closed_loop` | El sistema se auto-modifica sin supervisión. | **PROHIBIDO PARA SIEMPRE en Stacky.** No es un valor válido de `loop_mode` (`VALID_LOOP_MODES` no lo contiene; test F1 caso 11). El riel human-in-the-loop es innegociable (`human-in-the-loop-fundamental`). Ningún plan futuro de la serie puede habilitarlo. |

2. **Human-in-the-loop innegociable:** el ciclo MAPE corre SOLO on-demand (botón del
   panel); no hay daemon, no hay cron, no hay disparo automático (verificado: el repo NO
   tiene scheduler genérico — solo daemon loops puntuales en `backend/app.py`
   (`_digest_loop`, `_memory_review_sweep_loop`) que este plan NO replica; un daemon
   nuevo obligaría a otro gate `STACKY_TEST_MODE` como el del Plan 146 y no aporta valor
   acá). El ciclo **propone**; el operador **decide**.
3. **Cero trabajo extra al operador:** panel y ciclo default **ON** (invisibles hasta que
   los abre; no piden config). La única excepción es la auto-aplicación
   human-on-the-loop, default **OFF** citando la EXCEPCIÓN DURA #1 — misma clase que el
   precedente aceptado *épica-desde-brief*. TODO configurable desde la UI (el registry de
   flags es dinámico: aparecen solos en el panel del Arnés); **nada env-only** para el
   operador. Única pieza env-only: el kill-switch interno `STACKY_EVOLUTION_HARD_DISABLE`
   (A1, §8.0) — NO es config del operador sino freno de emergencia fuera del alcance de
   cualquier propuesta, amparado por el riel de la casa "kill-switches internos pueden
   ser env-only".
4. **3 runtimes con paridad:** el feature es backend Flask + frontend React, idéntico
   bajo Codex CLI, Claude Code CLI y GitHub Copilot Pro. El ÚNICO punto con LLM es el
   enriquecimiento del Analyze, que usa el **modelo local** (`invoke_local_llm`,
   agnóstico del runtime de agentes — precedente exacto: Plan 127, doctor local) con
   **degradación declarada**: sin endpoint local, el ciclo corre igual en modo
   determinista puro (las reglas R-A1..R-A4 no necesitan LLM). Ninguna fase toca el
   camino de ejecución de agentes.
5. **Mono-operador sin auth real:** cero RBAC, cero multiusuario. El campo `actor` del
   ledger es descriptivo (`"operator"`, `"mape"`, `"optimizer"`, `"auto_hotl"`), no un
   sistema de permisos.
6. **No degradar:** panel sin pollers (0 requests por tick — mejor cumplimiento posible
   del patrón "latido único" del Plan 156, que está CRITICADO sin implementar: este plan
   NO crea deuda nueva que ese plan deba matar). Store con lock y lecturas tolerantes.
   Backward-compatible: con el flag master OFF, byte-idéntico a hoy.
7. **Reusar, no reinventar:** telemetría del 142 (`cost_analytics`), incidencias del 131
   (`incident_store`), tablero del 128 (`plans_board`), LLM local del 106/127
   (`invoke_local_llm`), primitivas 138/162, estados 140, formato 161, ConfirmButton 136,
   Toast 135, probeFlagHealth 135. El aspecto `stacky_codebase` **enlaza** al Tablero 128
   y NO re-orquesta el pipeline de planes.

### Gotchas del repo que el implementador DEBE respetar (verificadas)

- **G1 — `config` vs `config.config`:** en `api/tickets.py` la instancia de flags es
  `config.config` (`api/tickets.py:7401`); `getattr(config, FLAG)` sobre el MÓDULO
  devuelve siempre el default. En los archivos NUEVOS de este plan usar SIEMPRE
  `from config import config as _cfg` y leer `getattr(_cfg, "FLAG", default)` (espejo
  EXACTO de `api/metrics.py:565-566`).
- **G2 — Ratchet de tests:** los 5 `test_*.py` nuevos DEBEN agregarse a
  `HARNESS_TEST_FILES` en **ambos** `backend/scripts/run_harness_tests.sh` (`:20`,
  última entrada hoy `:458`) y `backend/scripts/run_harness_tests.ps1` (`:412`) o el
  meta-test del Plan 49 se pone rojo.
- **G3 — Aristas `requires=`:** cada flag con `requires=` DEBE tener su arista en
  `_REQUIRES_MAP_FROZEN` (`backend/tests/test_harness_flags_requires.py:120`).
- **G4 — `_CURATED_DEFAULTS_ON`:** cada flag **bool** con `default=True` DEBE estar en el
  set de `backend/tests/test_harness_flags.py:467`. Las flags `type="int"` NO van al set.
- **G5 — venv y tests por archivo:** backend con `backend\.venv`
  (`.venv\Scripts\python.exe -m pytest tests/<archivo> -q`), NUNCA la suite completa
  (contaminación cross-run conocida). Frontend con `npx vitest run src/<archivo>`, por
  archivo, mismo motivo.
- **G6 — Ratchet UI cero inline-style:** los `.tsx` nuevos tienen alcance 0 en
  `uiDebtRatchet` (`frontend/src/__tests__/uiDebtRatchet.test.ts`): TODO estilo va al
  `.module.css`; prohibido `style={{}}` en `EvolutionCenterPage.tsx`.
- **G7 — `_CATEGORY_KEYS` obligatorio:** toda flag nueva va también al dict
  `_CATEGORY_KEYS` (`services/harness_flags.py:117`; nota literal `:331`) o
  `test_every_registry_flag_is_categorized` rompe. Ancla de inserción: la tupla que
  contiene el literal `"STACKY_PLANS_BOARD_ENABLED"` (`:265`).
- **G8 — `requires` profundidad 1 (precedente Plan 166):** las aristas `requires` apuntan
  SIEMPRE al flag ROOT (`STACKY_EVOLUTION_CENTER_ENABLED`), nunca en cadena a una flag
  hija (comentario normativo en `services/harness_flags.py:3336`).
- **G9 — Sin pollers nuevos:** el Plan 156 (latido único) está aprobado sin implementar;
  este panel NO introduce `setInterval`/`refetchInterval` de ningún tipo. Carga
  on-mount + botón "Refrescar" + refresh tras cada acción. El único spinner es el del
  POST síncrono del ciclo.
- **G10 — Contrato de URL (Plan 165, pendiente):** el tab entra por el router casero
  (`TAB_PATHS`, path nuevo `/evolution`); el deep-link de detalle usa la clave de query
  `proposal` leída con `readQueryParam` (`frontend/src/utils/queryParams.ts:10-12`) — el
  MISMO patrón informal que hoy usa `?flag=` — y queda documentado para que el Plan 165
  lo absorba en `routes.ts` cuando se implemente. No se inventa un router.
- **G11 — Corpus bajo `docs/` (gotcha del indexador):** `doc_indexer` escanea
  `docs/**/*.md`; NUNCA escribir artefactos generados `.md` bajo `docs/`. Este plan NO
  escribe nada bajo `docs/`: las lecciones van a `data_dir()/evolution/lessons.jsonl`
  (runtime data). La promoción curada al corpus `docs/rag/` es contrato del Plan 170
  (§8.3), siempre `.jsonl/.json/.txt`.
- **G12 — `harness_defaults.env` NO se toca a mano:** lo regenera
  `scripts/export_harness_defaults.py` (riel del Plan 133 §3.6). Este plan NO lo edita.
- **G13 — WIP ajeno / sesiones paralelas:** antes de editar cada archivo caliente
  (`config.py`, `harness_flags.py`, `App.tsx`, `shellNav.ts`, `api/__init__.py`,
  `endpoints.ts`, scripts de ratchet): `git status -- "<ruta>"`; staging quirúrgico por
  pathspec; PROHIBIDO `git stash/reset/checkout`. El implementador NO commitea (lo hace
  el orquestador).
- **G14 — Prosa vs gates propios:** ninguna cadena de comentario/docstring del código
  nuevo debe matchear los greps de criterio de este plan de forma espuria (gotcha
  recurrido 6×: el gate siempre gana; se reescribe la prosa).

---

## 4. Contratos congelados (van tal cual al código)

### 4.1 Layout de persistencia (todo bajo `data_dir()/evolution/`)

```
data_dir()/evolution/
  aspects.json      # lista de EvolutionAspect (los 4 seeds + futuros)
  proposals.json    # lista de ImprovementProposal (archivo completo; archive: NUNCA se borra una propuesta)
  cycles.jsonl      # una línea por EvolutionCycleRun (append-only)
  ledger.jsonl      # una línea por evento de auditoría (append-only)
  lessons.jsonl     # una línea por lección aplicada (aspecto knowledge_rag)
  snapshots/<proposal_id>/   # snapshot del artefacto previo al apply (rollback)
```

Reglas duras: el módulo store llama `runtime_paths.data_dir()` **en cada operación**
(sin cache a nivel módulo — requisito de testabilidad: los tests lo monkeypatchean);
todas las lecturas son tolerantes (archivo ausente/corrupto → valor vacío, espejo de
`incident_store._read_ledger` `:44-52`); todas las escrituras van bajo
`_EVOLUTION_LOCK = threading.Lock()` (espejo de `_LEDGER_LOCK` `:33`) y crean el
directorio con `mkdir(parents=True, exist_ok=True)`.

### 4.2 `EvolutionAspect` (shape; los 4 seeds LITERALES van en F1)

```json
{
  "id": "agent_prompts",
  "name": "Prompts y agentes de Stacky",
  "description": "…",
  "target_kind": "prompt_file | flag_change | knowledge_note | link_only",
  "loop_mode": "human_in_the_loop",
  "links": [{"label": "…", "href": "/planes"}],
  "created_at": "2026-07-17T00:00:00+00:00"
}
```

`VALID_LOOP_MODES = frozenset({"human_in_the_loop", "human_on_the_loop"})` — nótese que
`closed_loop` NO existe: cualquier intento de escribir un `loop_mode` fuera del frozenset
lanza `ValueError("loop_mode_invalido")` (test F1 caso 11).

### 4.3 `ImprovementProposal` (todas las claves SIEMPRE presentes; `null` cuando no aplica)

```json
{
  "id": "prop-<uuid4-hex>",
  "aspect_id": "agent_prompts",
  "title": "…",
  "rationale": "…",
  "origin": "manual | agent | optimizer | mape",
  "artifact_type": "free_text | knowledge_note | prompt_file | flag_change",
  "target_ref": null,
  "proposed_content": null,
  "base_hash": null,
  "evidence": ["…"],
  "status": "draft | pending_review | approved | applied | rejected | rolled_back",
  "fitness_before": null,
  "fitness_after": null,
  "parent_proposal_id": null,
  "cycle_id": null,
  "snapshot_info": null,
  "notes": [{"ts": "…", "actor": "…", "text": "…"}],
  "created_at": "…", "updated_at": "…",
  "applied_at": null, "rolled_back_at": null
}
```

Semántica de `artifact_type` + `target_ref` + `proposed_content`:

| artifact_type | target_ref | proposed_content | ¿Aplicable (Execute)? |
|---|---|---|---|
| `free_text` | `null` | `null` o texto | **NO** (informativa; su ciclo termina en approved/rejected) |
| `knowledge_note` | `null` | texto de la lección (obligatorio) | SÍ → append a `lessons.jsonl` |
| `prompt_file` | nombre de archivo `*.agent.md` DENTRO de `backend/Stacky/agents/` (ej. `"Developer.agent.md"`) | contenido COMPLETO propuesto del archivo (obligatorio) | SÍ → escribe el archivo con snapshot previo |
| `flag_change` | key EXACTA de una flag del arnés (ej. `"LOCAL_LLM_MODEL"`) | valor propuesto como string | **NO automático en el 167**: la UI muestra el deep-link `/settings?flag=<target_ref>` (receptor `?flag=` preexistente, Plan 165 §2.4) y el operador la cambia en el panel oficial del Arnés. `apply` sobre `flag_change` → 409 `artifact_not_appliable`. |

**`base_hash` (C6, anti-drift; SOLO significativo para `prompt_file`):** sha256 hex del
contenido del artefacto sobre el que se redactó la propuesta (`null` si el proponente no
lo conoce o el archivo no existía — entonces se usa el literal `"absent"`). Lo llena el
proponente (el 169 DEBE enviarlo — §8.2; el formulario manual y el MAPE lo dejan `null`).
En `apply` de `prompt_file`: si `base_hash` no es `null` y difiere del sha256 del
contenido ACTUAL del target (o de `"absent"` si hoy no existe) → el apply falla SIN
escribir con `RuntimeError("target_drifted")` → API 409 `target_drifted` (el artefacto
cambió entre la propuesta y el apply; el operador re-genera o re-confirma). `null` = sin
chequeo (backward-compatible).

### 4.4 Máquina de estados (tabla congelada de acciones)

| action | estados origen válidos | estado destino | side-effect |
|---|---|---|---|
| `submit` | `draft` | `pending_review` | — |
| `approve` | `pending_review` | `approved` | — |
| `reject` | `draft`, `pending_review`, `approved` | `rejected` | — (queda archivada con `note`; NUNCA se borra) |
| `apply` | `approved` | `applied` | `evolution_apply.apply_proposal` (snapshot + escritura); solo `artifact_type ∈ {knowledge_note, prompt_file}` |
| `rollback` | `applied` | `rolled_back` | `evolution_apply.rollback_proposal` (restaura snapshot) |

Cualquier otra combinación → excepción `InvalidTransition` (la API la mapea a 409
`{"ok": false, "error": "invalid_transition", "message": "<action> no es válida desde <status>"}`).

**`force` (C6):** el body de `transition` acepta `"force": bool` (default `false`). NO
agrega estados ni transiciones: solo relaja el chequeo anti-drift del `rollback` de
`prompt_file` (si el archivo fue editado DESPUÉS del apply, `rollback` sin `force` → 409
`target_drifted`; con `force: true` restaura el snapshot igual, pisando la edición — el
operador lo decide con confirmación explícita). `force` NO relaja el chequeo de
`base_hash` en `apply` (ahí siempre corresponde re-generar la propuesta) ni ninguna otra
validación de la máquina de estados.

### 4.5 Evento del ledger (`ledger.jsonl`, una línea JSON por evento)

```json
{"ts": "<iso utc>", "event": "created | transition | apply_failed | cycle | auto_apply",
 "proposal_id": "prop-… | null", "action": "submit|approve|reject|apply|rollback|null",
 "from": "<status|null>", "to": "<status|null>",
 "actor": "operator | mape | optimizer | agent | auto_hotl",
 "note": "<str|null>", "cycle_id": "cyc-…|null"}
```

### 4.6 Señales del Monitor (shape congelado) y reglas deterministas del Analyze

`collect_signals()` devuelve EXACTAMENTE (cada fuente en su propio `try/except` — una
fuente caída produce su clave con `{"error": "<msg>"}` y el ciclo sigue):

```json
{
  "generated_at": "<iso utc>",
  "window_days": 14,
  "executions": {"total": 0, "by_agent_type": {"<type>": {"total": 0, "errors": 0, "error_rate": 0.0}}},
  "costs": {"total_usd": 0.0, "by_model": {"<model>": 0.0}, "top_model": null, "top_model_share": 0.0},
  "incidents": {"total": 0, "non_terminal": 0, "stale_48h": 0},
  "plans": {"total": 0, "propuestos": 0, "criticados": 0, "drift": 0, "unpushed": 0, "next_free_number": 0}
}
```

Fuentes (nombres EXACTOS): `executions` y `costs` salen de UNA sola llamada
`ca.load_records(ca.CostFilters(days=14))` (`cost_analytics.py:167`) — `errors` cuenta
`r.status == "error"`; `usd` de cada record es `r.row.cost_usd or 0.0` SOLO si
`ca._billable(r.row.cost_kind)` (`:213`); `incidents` sale de
`incident_store.list_incidents()` (`:230`) con
`_INCIDENT_TERMINAL = ("publicada", "error")` y `stale_48h` = no-terminales con
`created_at` hace más de 48 h; `plans` sale de `plans_board.get_board_cached()` (`:378`):
`totals` + conteo de cards con `ledger.doc_drift is True` + `next_free_number`.

**Reglas deterministas del Analyze (tabla congelada; cada regla emite a lo sumo UN draft
por corrida; `rule_id` va en `evidence[0]` del draft):**

| rule_id | condición (sobre las señales) | draft emitido (aspect / artifact_type / title literal con placeholders) |
|---|---|---|
| `R-A1` | algún `agent_type` con `error_rate >= 0.3` y `total >= 5` | `agent_prompts` / `free_text` / `"Revisar prompt/flujo del agente {agent_type}: {errors}/{total} ejecuciones con error en 14 días"` |
| `R-A2` | `top_model_share >= 0.6` y `total_usd >= 1.0` | `config_flags_models` / `free_text` / `"Concentración de costo: {top_model} explica {pct}% del gasto de 14 días — evaluar modelo/effort más económico para tareas mecánicas"` |
| `R-A3` | `incidents.stale_48h >= 3` | `knowledge_rag` / `knowledge_note` / `"Lección: hay {n} incidencias sin cierre hace más de 48 h — documentar el patrón de bloqueo detectado"` (el `proposed_content` inicial es el resumen determinista de las incidencias: id + título + status) |
| `R-A4` | `plans.drift >= 1` | `stacky_codebase` / `free_text` / `"{n} plan(es) con drift doc-vs-aprobación en el Tablero de Planes — corresponde re-supervisar"` |

El enriquecimiento LLM (si está disponible) SOLO puede reescribir `title`/`rationale` de
los drafts ya emitidos por las reglas; **no crea ni elimina drafts** (anti
reward-hacking: la señal determinista decide QUÉ, el LLM solo redacta CÓMO).

### 4.7 `fitness_before/after` — placeholder congelado (contrato hacia el Plan 168)

Shape que el arnés 168 escribirá (el 167 solo lo persiste como `null` y lo muestra "—"):

```json
{"score": 0.0, "metrics": {}, "eval_ref": "<id de corrida de eval>", "evaluated_at": "<iso>"}
```

El 167 NO computa fitness. PROHIBIDO en esta implementación llenar estos campos con
heurísticas: si `fitness_before` no es `null` sin que exista el 168, es un bug.

### 4.8 Contratos HTTP (blueprint `evolution`, url_prefix `/evolution` → `/api/evolution/...`)

| Método y ruta | Flag OFF | Flag ON |
|---|---|---|
| `GET /api/evolution/health` | **200** `{"ok": true, "flag_enabled": false, "hard_disabled": false}` (patrón `api/metrics.py:569-573`) | 200 `{"ok": true, "flag_enabled": true, "hard_disabled": false}` |
| `GET /api/evolution/overview` | 404 `evolution_disabled` | 200 `{"ok": true, "aspects": […], "counts": {"draft": n, "pending_review": n, "approved": n, "applied": n, "rejected": n, "rolled_back": n}, "last_cycle": {…}\|null}` |
| `GET /api/evolution/proposals?status=&aspect_id=&origin=` | 404 | 200 `{"ok": true, "proposals": […]}` (orden `updated_at` DESC) |
| `GET /api/evolution/proposals/<id>` | 404 | 200 `{"ok": true, "proposal": {…}}` \| 404 `proposal_not_found` |
| `POST /api/evolution/proposals` | 404 | 201 `{"ok": true, "proposal": {…}}` \| 400 `invalid_payload` (aspect inexistente, origin/artifact inválido, `initial_status` ∉ {`draft`,`pending_review`}) |
| `POST /api/evolution/proposals/<id>/transition` body `{"action": "…", "note": "…", "force": false}` | 404 | 200 `{"ok": true, "proposal": {…}}` \| 409 `invalid_transition` \| 409 `artifact_not_appliable` \| 409 `target_drifted` (C6: `base_hash` no coincide en `apply`, o el archivo cambió post-apply en `rollback` sin `force`) \| 502 `apply_failed` (side-effect falló; la propuesta sigue `approved`) |
| `POST /api/evolution/cycle/run` body `{"aspects": null\|[…], "use_llm": true}` | 404 | 200 `{"ok": true, "cycle": {…}}` \| 409 `cycle_already_running` |
| `GET /api/evolution/cycles?limit=20` | 404 | 200 `{"ok": true, "cycles": […]}` (tail, más nuevo primero) |
| `GET /api/evolution/ledger?limit=50` | 404 | 200 `{"ok": true, "events": […]}` (tail, más nuevo primero) |

El shape 404 OFF es literal:
`{"ok": false, "error": "evolution_disabled", "message": "El Centro de Evolución está deshabilitado (STACKY_EVOLUTION_CENTER_ENABLED)."}`.

**Kill-switch (A1):** si la env var `STACKY_EVOLUTION_HARD_DISABLE` es truthy
(`"1"/"true"/"yes"`, case-insensitive), `_enabled()` devuelve `False` sin importar las
flags → TODO (salvo `health`) responde el mismo 404 `evolution_disabled`; `health`
responde 200 con `"hard_disabled": true` (diagnóstico). No aparece en el registry del
Arnés: es un freno interno de emergencia, no config del operador (§3.3).

### 4.9 `EvolutionCycleRun` (una línea de `cycles.jsonl`)

```json
{"id": "cyc-<uuid4-hex>", "started_at": "…", "finished_at": "…",
 "status": "completed | error", "error": null,
 "aspects": ["agent_prompts", "config_flags_models", "knowledge_rag", "stacky_codebase"],
 "signals": {…}, "signals_truncated": false,
 "rules_fired": ["R-A1"], "proposal_ids": ["prop-…"],
 "skipped_duplicate_rules": [],
 "llm_used": false, "llm_error": null,
 "tokens_est_in": 0, "tokens_est_out": 0}
```

---

## 5. Fases

Orden por dependencia: **F0 → F1 → F2 → F3 → F4 → F5 → F6 → F7**.

> **Comandos de test:** backend desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend`
> con `.venv\Scripts\python.exe -m pytest tests/<archivo> -q` (equivalente Git Bash:
> `cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/<archivo> -q`).
> Frontend desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend` con
> `npx vitest run src/<archivo>`. SIEMPRE por archivo (G5).

---

### F0 — Flags del arnés (patrón triple)

**Objetivo (1 frase):** declarar los 4 valores de configuración del Centro de Evolución
con el patrón triple, para que todas las fases queden protegidas y configurables por UI.
**Valor:** kill-switch por UI de todo el feature; la escalera de cierre de loop queda
gobernada por flags visibles.

**Archivos a editar (5):**
1. `Stacky Agents/backend/config.py`
2. `Stacky Agents/backend/services/harness_flags.py`
3. `Stacky Agents/backend/services/harness_flags_help.py`
4. `Stacky Agents/backend/tests/test_harness_flags.py` (set `_CURATED_DEFAULTS_ON` `:467`)
5. `Stacky Agents/backend/tests/test_harness_flags_requires.py` (mapa `:120`)

**Flags (nombres EXACTOS), defaults y excepciones:**

| Flag | type | Default | `requires=` | Excepción dura |
|---|---|---|---|---|
| `STACKY_EVOLUTION_CENTER_ENABLED` | bool | **ON** | (ninguno — master) | ninguna (panel read-mostly con gates humanos) |
| `STACKY_EVOLUTION_CYCLE_ENABLED` | bool | **ON** | `STACKY_EVOLUTION_CENTER_ENABLED` | ninguna (solo corre on-click; sin LLM configurado es determinista puro y gratis) |
| `STACKY_EVOLUTION_AUTO_APPLY_KNOWLEDGE_ENABLED` | bool | **OFF** | `STACKY_EVOLUTION_CENTER_ENABLED` | **#1 bypass de revisión humana** — human-on-the-loop SOLO para lecciones reversibles; el operador lo prende a conciencia |
| `STACKY_EVOLUTION_CYCLE_TOKEN_BUDGET` | int | `20000` | `STACKY_EVOLUTION_CENTER_ENABLED` | ninguna (presupuesto, no capacidad) |

(G8: las 3 aristas apuntan al ROOT `STACKY_EVOLUTION_CENTER_ENABLED`, profundidad 1 —
precedente normativo `harness_flags.py:3336`.)

**Diff ilustrativo — `config.py`** (insertar como bloque nuevo al final de la zona de
flags de planes recientes; ubicar por contenido el bloque del plan anterior más nuevo):

```python
    # ── Plan 167 — Centro de Evolución (serie auto-mejora recursiva 1/4) ──
    # Panel de aspectos/propuestas/ciclo MAPE con gates humanos. Default ON:
    # solo agrega superficie de lectura + acciones on-click del operador.
    STACKY_EVOLUTION_CENTER_ENABLED: bool = os.getenv(
        "STACKY_EVOLUTION_CENTER_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # Ciclo MAPE on-demand (botón "Correr ciclo"). Sin LLM local configurado
    # corre en modo determinista puro (reglas R-A1..R-A4), costo cero.
    STACKY_EVOLUTION_CYCLE_ENABLED: bool = os.getenv(
        "STACKY_EVOLUTION_CYCLE_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # human-on-the-loop SOLO para lecciones de conocimiento (reversibles).
    # EXCEPCIÓN DURA #1 (bypass de revisión humana) → default OFF a conciencia.
    STACKY_EVOLUTION_AUTO_APPLY_KNOWLEDGE_ENABLED: bool = os.getenv(
        "STACKY_EVOLUTION_AUTO_APPLY_KNOWLEDGE_ENABLED", "false"
    ).lower() in ("1", "true", "yes")

    # Presupuesto de tokens ESTIMADOS por corrida del ciclo (entrada al LLM local).
    STACKY_EVOLUTION_CYCLE_TOKEN_BUDGET: int = int(os.getenv(
        "STACKY_EVOLUTION_CYCLE_TOKEN_BUDGET", "20000"
    ) or "20000")
```

**`harness_flags.py` — 2 toques:**
(a) `_CATEGORY_KEYS` (G7): ubicar la tupla que contiene `"STACKY_PLANS_BOARD_ENABLED"`
(`:265`) y agregar inmediatamente después, dentro de la MISMA tupla:

```python
        "STACKY_EVOLUTION_CENTER_ENABLED",              # Plan 167 — Centro de Evolución (panel)
        "STACKY_EVOLUTION_CYCLE_ENABLED",               # Plan 167 — ciclo MAPE on-demand
        "STACKY_EVOLUTION_AUTO_APPLY_KNOWLEDGE_ENABLED",# Plan 167 — human-on-the-loop lecciones (OFF)
        "STACKY_EVOLUTION_CYCLE_TOKEN_BUDGET",          # Plan 167 — presupuesto tokens/ciclo
```

(b) `FLAG_REGISTRY`: insertar 4 `FlagSpec` inmediatamente DESPUÉS del `FlagSpec` de
`STACKY_PLANS_BOARD_ENABLED` (`:3267`, ubicar por key literal). `group="global"` (espejo
del hermano del Plan 166). Literales:

```python
    FlagSpec(
        key="STACKY_EVOLUTION_CENTER_ENABLED",
        type="bool", default=True,
        label="Centro de Evolución",
        description="Panel de auto-mejora de Stacky: aspectos mejorables, propuestas con aprobación humana, ciclo MAPE on-demand, ledger auditable y rollback 1-click.",
        group="global",
    ),
    FlagSpec(
        key="STACKY_EVOLUTION_CYCLE_ENABLED",
        type="bool", default=True,
        label="Ciclo MAPE on-demand",
        description="Habilita el botón 'Correr ciclo': lee la telemetría existente (costos, ejecuciones, incidencias, tablero de planes) y emite borradores de propuesta. Nunca aplica nada solo.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_EVOLUTION_AUTO_APPLY_KNOWLEDGE_ENABLED",
        type="bool",
        label="Auto-aplicar lecciones de conocimiento (human-on-the-loop)",
        description="SOLO lecciones de conocimiento reversibles: el ciclo las aplica solo y vos auditás/revertís después. Apagada por defecto porque saltea la revisión previa.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_EVOLUTION_CYCLE_TOKEN_BUDGET",
        type="int",
        label="Presupuesto de tokens por ciclo",
        description="Tope de tokens estimados que una corrida del ciclo puede mandar al modelo local (default 20000, definido en config). Si las señales exceden el tope, se truncan y el ciclo lo deja registrado.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
```

NOTA (C1 — regla general): SOLO las 2 bool default ON llevan `default=True` explícito
(y van curadas). `STACKY_EVOLUTION_AUTO_APPLY_KNOWLEDGE_ENABLED` **y también**
`STACKY_EVOLUTION_CYCLE_TOKEN_BUDGET` van SIN `default=` explícito: `default_is_known`
es type-agnostic (`spec.default is not None`, `harness_flags.py:3397-3399`) y
`test_default_known_only_for_curated` exige igualdad de conjuntos con
`_CURATED_DEFAULTS_ON` (donde los int NO entran — G4). El default EFECTIVO (OFF / 20000)
lo da `config.py`; precedente real de int sin default: `CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES`
(`harness_flags.py:350-358`, con el default documentado en la description).

**`harness_flags_help.py`:** agregar 4 entradas `PlainHelp` (espejo del formato de la
entrada del Plan 166 en `:1376`, ubicar por el texto "Al publicar una incidencia como
ticket"), una por flag, en lenguaje llano: qué es, efecto de ON, efecto de OFF, ejemplo.
Para `STACKY_EVOLUTION_AUTO_APPLY_KNOWLEDGE_ENABLED` el `on_effect` DEBE decir
explícitamente "saltea la revisión previa: el ciclo aplica la lección solo y te queda el
botón Revertir" (transparencia de la excepción dura).

**Meta-tests:** en `test_harness_flags.py:467` agregar al set `_CURATED_DEFAULTS_ON`
SOLO las 2 bool default ON: `STACKY_EVOLUTION_CENTER_ENABLED`,
`STACKY_EVOLUTION_CYCLE_ENABLED` (NO la int, NO la OFF — G4). En
`test_harness_flags_requires.py:120` agregar las 3 aristas:

```python
    "STACKY_EVOLUTION_CYCLE_ENABLED": "STACKY_EVOLUTION_CENTER_ENABLED",
    "STACKY_EVOLUTION_AUTO_APPLY_KNOWLEDGE_ENABLED": "STACKY_EVOLUTION_CENTER_ENABLED",
    "STACKY_EVOLUTION_CYCLE_TOKEN_BUDGET": "STACKY_EVOLUTION_CENTER_ENABLED",
```

**Tests PRIMERO (TDD):** crear `Stacky Agents/backend/tests/test_evolution_flags.py`
(espejo estructural de `tests/test_plan128_plans_board_flag.py`). 8 casos:
1. `test_center_flag_en_registry` — existe FlagSpec `STACKY_EVOLUTION_CENTER_ENABLED`, `type=="bool"`, `default is True`.
2. `test_cycle_flag_requires_center` — spec de CYCLE tiene `requires=="STACKY_EVOLUTION_CENTER_ENABLED"`.
3. `test_auto_apply_default_off` — spec de AUTO_APPLY: `default is None` Y con env limpio `config.STACKY_EVOLUTION_AUTO_APPLY_KNOWLEDGE_ENABLED is False`.
4. `test_budget_flag_int` — spec de TOKEN_BUDGET: `type=="int"` y `default is None`
   (C1: el default efectivo 20000 lo da `config.py` — lo cubre el caso 6).
5. `test_las_4_estan_categorizadas` — las 4 keys están en algún valor de `_CATEGORY_KEYS` (importar de `services.harness_flags`).
6. `test_config_defaults` — env limpio: CENTER True, CYCLE True, BUDGET 20000.
7. `test_aristas_requires_congeladas` — las 3 aristas están en `_REQUIRES_MAP_FROZEN` con el ROOT como destino.
8. `test_help_presente` — el dict de `harness_flags_help` contiene las 4 keys.

**Comando (Git Bash):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_evolution_flags.py tests/test_harness_flags.py tests/test_harness_flags_requires.py -q
```
**Criterio BINARIO:** los 3 archivos verdes (fotografiar ANTES los fallos preexistentes
de `test_harness_flags.py` si los hubiera; el criterio es "sin regresión vs. la foto").
**Flag:** las declaradas acá. **Runtimes:** N/A (declaración). **Trabajo del operador:** ninguno.

---

### F1 — Store puro: `services/evolution_store.py` (entidades + máquina de estados + ledger + seeds)

**Objetivo (1 frase):** persistir aspectos, propuestas, ciclos y ledger en
`data_dir()/evolution/` con máquina de estados validada y auditoría append-only, sin
Flask y sin side-effects de artefactos.
**Valor:** toda la gobernanza testeable con `tmp_path`; el "harness as primary artifact"
del survey hecho datos.

**Archivo a crear:** `Stacky Agents/backend/services/evolution_store.py`

**Símbolos EXACTOS (además de los contratos §4.1-§4.5):**

```python
import runtime_paths                      # data_dir() en CADA llamada (testabilidad)
_EVOLUTION_LOCK = threading.Lock()
_PATCHABLE_FIELDS = frozenset({"title", "rationale", "snapshot_info",
                               "fitness_before", "fitness_after"})  # C2: allowlist dura
VALID_LOOP_MODES = frozenset({"human_in_the_loop", "human_on_the_loop"})
VALID_STATUSES = ("draft", "pending_review", "approved", "applied", "rejected", "rolled_back")
VALID_ORIGINS = ("manual", "agent", "optimizer", "mape")
VALID_ARTIFACT_TYPES = ("free_text", "knowledge_note", "prompt_file", "flag_change")
APPLIABLE_ARTIFACT_TYPES = frozenset({"knowledge_note", "prompt_file"})
TRANSITIONS: dict[str, dict] = {
    "submit":   {"from": ("draft",), "to": "pending_review"},
    "approve":  {"from": ("pending_review",), "to": "approved"},
    "reject":   {"from": ("draft", "pending_review", "approved"), "to": "rejected"},
    "apply":    {"from": ("approved",), "to": "applied"},
    "rollback": {"from": ("applied",), "to": "rolled_back"},
}

class InvalidTransition(ValueError): ...

def evolution_hard_disabled() -> bool
    # A1 — kill-switch env-only: os.getenv("STACKY_EVOLUTION_HARD_DISABLE", "")
    #      .strip().lower() in ("1", "true", "yes"). Leer el env EN CADA llamada
    #      (testabilidad con monkeypatch.setenv). NO va al registry del Arnés.
def evolution_root() -> Path            # runtime_paths.data_dir() / "evolution"
def ensure_seed_aspects() -> list[dict] # idempotente: crea los 4 seeds si faltan; NO pisa existentes
def list_aspects() -> list[dict]
def get_aspect(aspect_id: str) -> dict | None
def create_proposal(*, aspect_id, title, rationale, origin, artifact_type,
                    target_ref=None, proposed_content=None, evidence=None,
                    initial_status="pending_review", cycle_id=None,
                    parent_proposal_id=None, base_hash=None, actor="operator") -> dict
    # Valida: aspecto existe; origin/artifact en los VALID_*; initial_status ∈
    # ("draft","pending_review"); knowledge_note/prompt_file exigen proposed_content
    # no vacío; prompt_file exige target_ref no vacío. ValueError("invalid_payload:<campo>")
    # si falla. Llena TODAS las claves de §4.3 (fitness_* = None). Append ledger
    # {"event":"created", ...}. Devuelve el dict completo.
def list_proposals(status=None, aspect_id=None, origin=None) -> list[dict]   # updated_at DESC
def get_proposal(proposal_id: str) -> dict | None
def transition(proposal_id: str, action: str, *, actor: str, note=None) -> dict
    # Valida contra TRANSITIONS (InvalidTransition si no aplica); NO ejecuta
    # side-effects de archivos (eso es evolution_apply, F2). Actualiza status,
    # updated_at, notes (si note), applied_at/rolled_back_at cuando corresponde.
    # Append ledger {"event":"transition", ...}. Devuelve el dict actualizado.
def update_proposal_fields(proposal_id: str, **patch) -> dict
    # C2: patch superficial SOLO de claves en _PATCHABLE_FIELDS (snapshot_info,
    # title/rationale del enriquecimiento LLM, fitness_* que llenará el 168).
    # Cualquier otra clave — exista o no en el shape (status, applied_at, id, …) →
    # ValueError("campo_no_patcheable:<clave>"). El status SOLO muta vía transition()
    # (la máquina de estados es el único camino; sin esto KPI-1 sería prosa).
def append_ledger(event: dict) -> None
    # A2: además de la línea en ledger.jsonl, emite UNA línea INFO por
    # logging.getLogger("stacky.evolution") con json compacto del evento
    # (auditoría visible en la página de logs del Plan 145; best-effort, jamás rompe).
def read_ledger_tail(limit: int = 50) -> list[dict]     # más nuevo primero
def append_cycle(record: dict) -> None
def read_cycles_tail(limit: int = 20) -> list[dict]     # más nuevo primero
```

**Los 4 aspectos seed (LITERALES — `ensure_seed_aspects` los crea con estos ids):**

| id | name | target_kind | loop_mode | links |
|---|---|---|---|---|
| `agent_prompts` | `Prompts y agentes de Stacky` | `prompt_file` | `human_in_the_loop` | `[]` (la card muestra la ruta runtime `backend/Stacky/agents/`) |
| `config_flags_models` | `Flags del arnés y selección de modelo/costo` | `flag_change` | `human_in_the_loop` | `[{"label": "Abrir Configuración del Arnés", "href": "/settings"}]` |
| `knowledge_rag` | `Conocimiento y lecciones (RAG)` | `knowledge_note` | `human_in_the_loop` | `[]` (la card muestra la ruta `data_dir()/evolution/lessons.jsonl`) |
| `stacky_codebase` | `Código de Stacky (pipeline de planes)` | `link_only` | `human_in_the_loop` | `[{"label": "Abrir Tablero de Planes", "href": "/planes"}]` |

`descriptions` (una frase cada una, redactarlas informativas): qué artefactos cubre el
aspecto y quién lo mejora. Para `stacky_codebase` la description DEBE decir que el
pipeline proponer→criticar→implementar→supervisar YA existe (Tablero 128) y que este
aspecto solo lo enlaza en modo lectura.

`ensure_seed_aspects` se invoca de forma lazy en `list_aspects()` y en el endpoint
`overview` (F4) — NO en el startup de la app (cero riesgo en `create_app`, cero daemons).

**Tests PRIMERO:** `Stacky Agents/backend/tests/test_evolution_store.py`. Fixture común:
`monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)` (funciona porque el
store llama `runtime_paths.data_dir()` en cada operación). 14 casos:
1. `test_seed_aspects_idempotente` — 2 llamadas → 4 aspectos, ids exactos, sin duplicar.
2. `test_create_proposal_shape_completo` — todas las claves de §4.3 presentes; `fitness_before is None`, `parent_proposal_id is None`.
3. `test_create_valida_aspect_inexistente` — `ValueError` con `"invalid_payload"` en el mensaje.
4. `test_create_prompt_file_exige_target_y_content` — sin `target_ref` o sin `proposed_content` → `ValueError`.
5. `test_create_origin_optimizer_ok` — `origin="optimizer"` acepta y persiste (KPI-5).
6. `test_transiciones_validas_happy_path` — draft→submit→approve→apply(vía transition directa)→rollback recorre los estados EXACTOS de §4.4.
7. `test_transicion_invalida` — `apply` sobre `draft` → `InvalidTransition`.
8. `test_reject_archiva_no_borra` — reject deja la propuesta en la lista con `status=="rejected"`.
9. `test_ledger_registra_cada_evento` — created + 3 transiciones → 4 líneas en `ledger.jsonl`, shape §4.5.
10. `test_ledger_y_cycles_tail_orden` — tail devuelve más nuevo primero y respeta `limit`.
11. `test_loop_mode_closed_loop_rechazado` — intentar escribir un aspecto con `loop_mode="closed_loop"` → `ValueError("loop_mode_invalido")`.
12. `test_lecturas_tolerantes` — `proposals.json` corrupto → `list_proposals() == []` sin excepción.
13. `test_update_fields_campo_protegido` (C2) — `update_proposal_fields(pid, status="applied")` → `ValueError` con `"campo_no_patcheable"`; el status NO cambió y el ledger NO tiene evento nuevo. `update_proposal_fields(pid, fitness_before={...})` sí funciona (contrato 168).
14. `test_ledger_espejo_en_logs` (A2) — con `caplog` a nivel INFO en el logger `stacky.evolution`: `append_ledger` de 1 evento deja ≥1 record con el `proposal_id` en el mensaje.

**Comando (Git Bash):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_evolution_store.py -q
```
**Criterio BINARIO:** 14/14 verdes.
**Flag:** módulo puro (nadie lo importa aún) — N/A. **Runtimes:** N/A. **Trabajo del operador:** ninguno.

---

### F2 — Motor de aplicación y rollback: `services/evolution_apply.py`

**Objetivo (1 frase):** ejecutar el Execute del MAPE — aplicar una propuesta aprobada
con snapshot previo del artefacto y revertirla 1-click — más el auto-apply
human-on-the-loop gateado.
**Valor:** reversibilidad garantizada (KPI-3); la única escritura de artefactos del plan
vive en UN módulo con allowlist dura.

**Archivo a crear:** `Stacky Agents/backend/services/evolution_apply.py`

**Símbolos EXACTOS:**

```python
_HOTL_ALLOWED_ASPECTS = frozenset({"knowledge_rag"})
_APPLY_LOCK = threading.Lock()   # C3: serializa apply/rollback end-to-end

def agents_prompts_dir() -> Path
    # Path(runtime_paths.backend_root()) / "Stacky" / "agents"
    # (dir verificado en disco con los .agent.md del runtime)

def apply_proposal(proposal_id: str, *, actor: str = "operator") -> dict
    # 0) A1: if store.evolution_hard_disabled(): raise RuntimeError("evolution_hard_disabled").
    #    C3: TODO el cuerpo bajo `with _APPLY_LOCK:` (blocking; las ops son cortas y
    #    locales — el lock del store es OTRO lock, se toma y suelta dentro de cada op,
    #    no hay deadlock). El re-chequeo del status DENTRO del lock elimina la carrera
    #    doble-click/dos-pestañas (sin él, el 2º apply duplicaba el side-effect y su
    #    snapshot pisaba al 1º → rollback restauraba el contenido YA aplicado).
    # 1) p = store.get_proposal(...); si None → KeyError("proposal_not_found").
    # 2) Si p["status"] != "approved" → store re-lanzará InvalidTransition en el paso 5;
    #    validarlo acá primero y lanzar InvalidTransition directamente (mensaje claro).
    # 3) Si p["artifact_type"] not in store.APPLIABLE_ARTIFACT_TYPES →
    #    ValueError("artifact_not_appliable").
    # 3b) C6 anti-drift (solo prompt_file con base_hash no nulo): actual =
    #    sha256 hex del contenido ACTUAL del target, o el literal "absent" si no
    #    existe; si p["base_hash"] != actual → RuntimeError("target_drifted") SIN
    #    escribir nada (la API lo mapea a 409 target_drifted).
    # 4) side-effect según artifact_type (abajo). Si falla →
    #    store.append_ledger({"event": "apply_failed", ...}) y re-raise
    #    RuntimeError("apply_failed: <detalle>") — la propuesta QUEDA en approved.
    # 5) store.update_proposal_fields(pid, snapshot_info=...) y
    #    store.transition(pid, "apply", actor=actor).

def rollback_proposal(proposal_id: str, *, actor: str = "operator", force: bool = False) -> dict
    # Simétrico y también bajo _APPLY_LOCK (C3) + guard A1: exige status "applied";
    # C6: para prompt_file, si sha256(contenido ACTUAL) != sha256(p["proposed_content"])
    # (el archivo fue editado DESPUÉS del apply) y force es False →
    # RuntimeError("target_drifted") sin tocar nada; con force=True restaura igual.
    # Deshace según snapshot_info; store.transition(pid, "rollback", actor=actor).

def maybe_auto_apply(proposal: dict) -> bool
    # human-on-the-loop. Devuelve False (sin efecto) salvo que TODO se cumpla:
    #   store.evolution_hard_disabled() es False (A1 — el kill-switch gana SIEMPRE)
    #   y getattr(_cfg, "STACKY_EVOLUTION_AUTO_APPLY_KNOWLEDGE_ENABLED", False) es True
    #   y proposal["aspect_id"] in _HOTL_ALLOWED_ASPECTS
    #   y proposal["artifact_type"] == "knowledge_note"
    #   y proposal["status"] == "draft"
    # Si aplica: encadena transition submit→approve con actor="auto_hotl" y
    # apply_proposal(actor="auto_hotl") — CADA transición queda en el ledger
    # (auditoría completa del bypass) + un evento {"event": "auto_apply"}.
    # Cualquier excepción → False, PERO (C7) antes deja rastro best-effort:
    # store.append_ledger({"event": "apply_failed", "actor": "auto_hotl",
    # "proposal_id": ..., "note": str(exc)}) dentro de su propio try/except
    # (el draft queda para revisión manual; nada muere en silencio).
```

**Side-effects por `artifact_type` (contrato §4.3):**

- `knowledge_note` → append de UNA línea JSON a
  `evolution_root()/lessons.jsonl`:
  `{"lesson_id": p["id"], "aspect_id": …, "text": p["proposed_content"], "origin": …, "created_at": iso}`.
  `snapshot_info = {"kind": "lesson_append", "lesson_id": p["id"]}`.
  Rollback: reescribir `lessons.jsonl` filtrando la línea cuyo `lesson_id` coincide.
- `prompt_file` → guard de allowlist ANTI path-traversal:
  `target = (agents_prompts_dir() / p["target_ref"]).resolve()`; exigir
  `target.suffix == ".md"`, que el nombre termine en `.agent.md`, y
  `str(target).startswith(str(agents_prompts_dir().resolve()))` — si no,
  `ValueError("target_fuera_de_allowlist")`. Snapshot: si el archivo existe, copiar el
  contenido previo a `evolution_root()/snapshots/<proposal_id>/before_<filename>` y
  `snapshot_info = {"kind": "file", "target": p["target_ref"], "absent": False}`; si NO
  existía, `{"kind": "file", "target": …, "absent": True}`. Escribir
  `p["proposed_content"]` con `encoding="utf-8"`. Rollback: si `absent` → borrar el
  archivo; si no → restaurar el snapshot byte-idéntico.
- `flag_change` y `free_text` → NUNCA llegan acá (paso 3 los rechaza).

**Tests PRIMERO:** `Stacky Agents/backend/tests/test_evolution_apply.py` (mismo fixture
`data_dir→tmp_path`; para `prompt_file` monkeypatchear también
`evolution_apply.agents_prompts_dir` a un `tmp_path / "agents"`). 14 casos:
1. `test_apply_knowledge_note_appendea_leccion` — tras apply, `lessons.jsonl` tiene 1 línea con `lesson_id` correcto y la propuesta queda `applied` con `applied_at` no nulo.
2. `test_rollback_knowledge_note_remueve_leccion` — roundtrip → `lessons.jsonl` sin esa lección; status `rolled_back`.
3. `test_apply_prompt_file_snapshot_y_escritura` — archivo previo con contenido A, propuesta con contenido B → archivo == B y snapshot == A.
4. `test_rollback_prompt_file_byte_identico` — tras rollback, el archivo vuelve EXACTAMENTE a A (comparación de bytes) (KPI-3).
5. `test_apply_prompt_file_ausente_y_rollback_borra` — target inexistente → apply lo crea; rollback lo borra.
6. `test_prompt_file_fuera_de_allowlist` — `target_ref="../../config.py"` → `ValueError("target_fuera_de_allowlist")` y NO se escribió nada.
7. `test_apply_free_text_rechazado` — `ValueError("artifact_not_appliable")`.
8. `test_apply_desde_estado_no_aprobado` — `InvalidTransition`.
9. `test_auto_apply_flag_off_noop` — con el flag OFF (default), `maybe_auto_apply` → False y el draft sigue `draft`.
10. `test_auto_apply_on_solo_knowledge` — flag ON (monkeypatch de `_cfg`): un draft `knowledge_note` de `knowledge_rag` termina `applied` con actor `auto_hotl` en el ledger; un draft `prompt_file` NO se toca.
11. `test_doble_apply_secuencial_no_duplica` (C3) — apply dos veces la misma propuesta `knowledge_note`: la 2ª lanza `InvalidTransition` y `lessons.jsonl` tiene EXACTAMENTE 1 línea (el side-effect no se duplicó); verificar además que `evolution_apply._APPLY_LOCK` existe y es `threading.Lock`.
12. `test_apply_base_hash_drift` (C6) — propuesta `prompt_file` con `base_hash` del contenido A; el archivo se edita a A' ANTES del apply → `RuntimeError` con `"target_drifted"`, el archivo sigue A' (no se escribió) y la propuesta sigue `approved`. Con `base_hash=None` el mismo apply pasa (backward-compat).
13. `test_rollback_drift_requiere_force` (C6) — apply OK escribe B; se edita el archivo a B' a mano; `rollback_proposal` sin force → `RuntimeError("target_drifted")` y el archivo sigue B'; con `force=True` → restaura el snapshot A byte-idéntico y status `rolled_back`.
14. `test_hard_disable_bloquea_apply_y_hotl` (A1) — `monkeypatch.setenv("STACKY_EVOLUTION_HARD_DISABLE", "true")`: `apply_proposal` lanza `RuntimeError("evolution_hard_disabled")` y `maybe_auto_apply` (con el flag HOTL ON) devuelve `False` sin efectos.

**Comando (Git Bash):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_evolution_apply.py -q
```
**Criterio BINARIO:** 14/14 verdes.
**Flag:** `STACKY_EVOLUTION_AUTO_APPLY_KNOWLEDGE_ENABLED` (OFF — EXCEPCIÓN DURA #1
citada en F0) gobierna SOLO `maybe_auto_apply`; apply/rollback manuales quedan bajo el
master (gateados por la API en F4).
**Runtimes:** N/A (side-effects locales de archivos, agnósticos). **Fallback:** N/A.
**Trabajo del operador:** ninguno (la auto-aplicación es opt-in explícito).

---

### F3 — Ciclo MAPE: `services/evolution_cycle.py`

**Objetivo (1 frase):** una corrida on-demand Monitor→Analyze→Plan (Execute queda en F2,
gateado por humano) que lee SOLO telemetría existente, aplica las reglas deterministas
R-A1..R-A4, opcionalmente pule la redacción con el LLM local dentro del presupuesto, y
persiste la corrida en `cycles.jsonl`.
**Valor:** la telemetría que ya existe empieza a producir propuestas accionables, con
costo acotado y sin autonomía.

**Archivo a crear:** `Stacky Agents/backend/services/evolution_cycle.py`

**Símbolos EXACTOS:**

```python
_CYCLE_LOCK = threading.Lock()           # single-flight
_WINDOW_DAYS = 14
_ERROR_STATUSES = ("error", "failed")    # C4: agent_runner marca AMBOS (p.ej. agent_runner.py:117 "failed", :289 "error")
_INCIDENT_TERMINAL = ("publicada", "error")
_ANALYZE_SYSTEM = (
    "Sos el redactor del Centro de Evolución de Stacky. Recibís señales de telemetría "
    "y una lista de borradores de propuesta ya decididos por reglas deterministas. "
    "Tu ÚNICA tarea es mejorar title y rationale de cada borrador (más claros, "
    "específicos y accionables, en castellano). Respondé SOLO JSON con el shape "
    '{"proposals": [{"index": <int>, "title": "...", "rationale": "..."}]}. '
    "PROHIBIDO crear, eliminar o reordenar borradores."
)

def _estimate_tokens(text: str) -> int   # max(1, len(text) // 4)

def collect_signals() -> dict            # shape EXACTO §4.6; cada fuente en try/except
def analyze(signals: dict) -> list[dict] # aplica R-A1..R-A4 (tabla §4.6); devuelve
                                         # "draft specs": dicts con aspect_id, artifact_type,
                                         # title, rationale, evidence=[rule_id, ...detalle],
                                         # proposed_content (solo R-A3)
def enrich_with_llm(draft_specs: list[dict], signals: dict) -> tuple[list[dict], dict]
    # Devuelve (specs_actualizados, info) con info = {"llm_used": bool,
    # "llm_error": str|None, "tokens_est_in": int, "tokens_est_out": int,
    # "signals_truncated": bool}.
    # 1) budget = int(getattr(_cfg, "STACKY_EVOLUTION_CYCLE_TOKEN_BUDGET", 20000)).
    # 2) user = json.dumps({"signals": signals, "drafts": [...]}, ensure_ascii=False);
    #    si _estimate_tokens(user) > budget → truncar user a budget*4 chars, agregarle
    #    el sufijo literal "[TRUNCADO_POR_PRESUPUESTO]" (C8: el JSON queda partido a
    #    propósito y el marcador se lo dice al modelo) y signals_truncated=True.
    # 3) from copilot_bridge import invoke_local_llm; llamarla con
    #    agent_type="evolution_analyze", system=_ANALYZE_SYSTEM, user=user,
    #    on_log=lambda level, msg: None, execution_id=None, model=None.
    #    RuntimeError (endpoint no configurado/no responde — copilot_bridge.py:257-262)
    #    → llm_used=False, llm_error=str(exc), specs sin tocar (DEGRADACIÓN DECLARADA).
    # 4) Parse tolerante del JSON de resp.text (buscar el primer '{'); si no parsea →
    #    specs sin tocar. Si parsea: aplicar SOLO title/rationale por index válido.
    # 5) tokens_est_out = _estimate_tokens(resp.text) cuando hubo respuesta.

def run_cycle(*, aspects: list[str] | None = None, use_llm: bool = True) -> dict
    # 0) A1: if store.evolution_hard_disabled(): raise RuntimeError("evolution_hard_disabled").
    # 1) if not _CYCLE_LOCK.acquire(blocking=False): raise RuntimeError("cycle_already_running")
    #    (try/finally release).
    # 2) store.ensure_seed_aspects(); filtrar draft_specs por `aspects` si vino.
    # 3) signals = collect_signals(); specs = analyze(signals);
    #    (specs, info) = enrich_with_llm(specs, signals) SOLO si use_llm.
    # 4) C5 dedup ANTES de crear: abiertas = store.list_proposals() con
    #    status in ("draft", "pending_review"); si ya existe una abierta con el MISMO
    #    aspect_id y el MISMO evidence[0] (rule_id) que el spec → NO crear, agregar el
    #    rule_id a skipped_duplicate_rules (el ciclo no spamea la bandeja mientras la
    #    condición persista; al cerrarse la propuesta, la regla puede volver a emitir).
    #    Por cada spec NO duplicado → store.create_proposal(..., origin="mape",
    #    initial_status="draft", cycle_id=cid, actor="mape").
    # 5) por cada propuesta creada → evolution_apply.maybe_auto_apply(p)
    #    (no-op salvo flag HOTL ON — ver F2).
    # 6) record §4.9 (incluye skipped_duplicate_rules) → store.append_cycle(record) +
    #    ledger {"event": "cycle", ...};
    #    devolver record. Cualquier excepción → record con status="error" y re-raise NO:
    #    se persiste el record de error y se devuelve (el endpoint lo muestra).
```

Detalle del Monitor (fuentes EXACTAS, cada una en su `try/except` que deja
`{"error": str(exc)}` en su clave):
- `executions` + `costs`: `from services import cost_analytics as ca;`
  `records = ca.load_records(ca.CostFilters(days=_WINDOW_DAYS))`; agrupar por
  `r.agent_type` (None → `"desconocido"`); `errors` = `r.status in _ERROR_STATUSES`;
  `usd` por record = `float(r.row.cost_usd or 0.0)` si `ca._billable(r.row.cost_kind)`
  sino `0.0`; `by_model` clave = `r.row.model or "desconocido"`;
  `top_model`/`top_model_share` derivados de `by_model` (share = top/total si total>0).
- `incidents`: `from services import incident_store;`
  `items = incident_store.list_incidents()`; `non_terminal` =
  `status not in _INCIDENT_TERMINAL`; `stale_48h` = no-terminales con `created_at`
  (ISO) anterior a `now - 48h` (parse tolerante: si no parsea, no cuenta).
- `plans`: `from services import plans_board;` `board = plans_board.get_board_cached()`;
  `total/propuestos/criticados` de `board["totals"]` (claves `"total"`, `"PROPUESTO"`,
  `"CRITICADO"`, default 0); `drift` = cantidad de cards con
  `(card.get("ledger") or {}).get("doc_drift") is True`; `unpushed` =
  `board["totals"].get("unpushed", 0)`; `next_free_number` = `board.get("next_free_number")
  or 0`.

**Tests PRIMERO:** `Stacky Agents/backend/tests/test_evolution_cycle.py` (fixture
`data_dir→tmp_path`; monkeypatch de `ca.load_records`, `incident_store.list_incidents`,
`plans_board.get_board_cached` con fixtures sintéticos; monkeypatch de
`copilot_bridge.invoke_local_llm` donde aplique). 12 casos:
1. `test_collect_signals_shape` — con mocks devuelve EXACTAMENTE las claves de §4.6.
2. `test_fuente_caida_no_tumba` — `list_incidents` lanza → `signals["incidents"]["error"]` presente y el resto completo.
3. `test_ra1_error_rate` — fixture con 6 runs de `developer`, 2 con status `"error"` y 1 con `"failed"` (C4: ambos cuentan) → draft `agent_prompts` con `evidence[0]=="R-A1"`.
4. `test_ra2_concentracion_costo` — 70% del USD en un modelo, total ≥ 1.0 → draft `config_flags_models` con `"R-A2"`.
5. `test_ra3_incidencias_stale` — 3 incidencias no terminales de hace 3 días → draft `knowledge_note` con `proposed_content` no vacío y `"R-A3"`.
6. `test_ra4_drift_planes` — 2 cards con `doc_drift=True` → draft `stacky_codebase` con `"R-A4"`.
7. `test_sin_senales_sin_drafts` — señales sanas → `rules_fired == []` y 0 propuestas (el ciclo NO inventa trabajo).
8. `test_llm_no_configurado_degrada` — `invoke_local_llm` lanza `RuntimeError` → `llm_used False`, `llm_error` no nulo, drafts intactos.
9. `test_llm_reescribe_solo_titulo_rationale` — mock devuelve JSON válido → title/rationale cambian; aspect/artifact/evidence NO.
10. `test_presupuesto_trunca` — señales gigantes + budget chico (monkeypatch `_cfg`) → `signals_truncated True` y el `user` enviado al mock mide ≤ budget*4 chars.
11. `test_single_flight` — con el lock tomado, `run_cycle` lanza `RuntimeError("cycle_already_running")`.
12. `test_ciclo_dedup_no_duplica_drafts` (C5) — dos `run_cycle` seguidos con las MISMAS señales que disparan R-A1: la 1ª corrida crea 1 draft; la 2ª crea 0, su record tiene `skipped_duplicate_rules == ["R-A1"]` y `list_proposals()` sigue con 1 propuesta.

**Comando (Git Bash):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_evolution_cycle.py -q
```
**Criterio BINARIO:** 12/12 verdes.
**Flag:** `STACKY_EVOLUTION_CYCLE_ENABLED` (la API la gatea en F4; el módulo en sí es puro).
**Impacto por runtime:** Claude Code CLI / Codex CLI / GitHub Copilot Pro — **idéntico**:
el ciclo corre en el backend, sin tocar el runtime de agentes. **Fallback:** sin
`LOCAL_LLM_ENDPOINT` (o con `use_llm=false`), modo determinista puro — mismas reglas,
cero tokens, cero costo, en los 3 runtimes por igual.
**Trabajo del operador:** ninguno (opcional: configurar el modelo local en el Arnés para
mejor redacción — ya existía como capacidad del Plan 106/127).

---

### F4 — API Flask: `api/evolution.py` + registro

**Objetivo (1 frase):** exponer los contratos §4.8 gateados por flag, con el patrón
health-siempre-200 para el gating de navegación.
**Valor:** el frontend (F5/F6) y el optimizador del Plan 169 tienen su superficie.

**Archivo a crear:** `Stacky Agents/backend/api/evolution.py`

```python
from flask import Blueprint, jsonify, request
from config import config as _cfg                       # G1

bp = Blueprint("evolution", __name__, url_prefix="/evolution")

def _enabled() -> bool:
    from services import evolution_store as _st          # lazy (patrón del archivo)
    if _st.evolution_hard_disabled():                    # A1: el kill-switch gana SIEMPRE
        return False
    return bool(getattr(_cfg, "STACKY_EVOLUTION_CENTER_ENABLED", False))

def _cycle_enabled() -> bool:
    return _enabled() and bool(getattr(_cfg, "STACKY_EVOLUTION_CYCLE_ENABLED", False))

def _disabled_resp():
    return jsonify({"ok": False, "error": "evolution_disabled",
                    "message": "El Centro de Evolución está deshabilitado (STACKY_EVOLUTION_CENTER_ENABLED)."}), 404
```

Rutas (imports de `services` LAZY dentro de cada handler — patrón del Plan 128,
`api/plans_board.py`): `GET /health` (siempre 200,
`{"ok": True, "flag_enabled": _enabled(), "hard_disabled": evolution_store.evolution_hard_disabled()}`),
`GET /overview` (llama `ensure_seed_aspects()`, arma `counts` por status sobre
`list_proposals()` y `last_cycle` = primer elemento de `read_cycles_tail(1)` o `None`),
`GET /proposals` (query params `status/aspect_id/origin` pasados tal cual al store),
`GET /proposals/<pid>`, `POST /proposals` (mapea `ValueError` con `"invalid_payload"` →
400; `origin` del body, default `"manual"`; `actor="operator"` salvo
`origin=="optimizer"` → `actor="optimizer"`; acepta `base_hash` opcional del body — C6),
`POST /proposals/<pid>/transition`
(mapea `InvalidTransition` → 409 `invalid_transition`; `ValueError("artifact_not_appliable")`
→ 409 `artifact_not_appliable`; `RuntimeError` cuyo mensaje empieza con `"target_drifted"`
→ 409 `target_drifted` (C6); cualquier otro `RuntimeError("apply_failed…")` → 502
`apply_failed`; el bool `force` del body (default `false`) se pasa SOLO a
`rollback_proposal(force=...)`;
acciones `apply`/`rollback` van vía `evolution_apply`, el resto vía `store.transition`
con `actor="operator"`), `POST /cycle/run` (gate extra `_cycle_enabled()` → si el master
ON pero CYCLE OFF → 404 con `error="evolution_cycle_disabled"`;
`RuntimeError("cycle_already_running")` → 409), `GET /cycles`, `GET /ledger`
(query `limit`, clamp 1..200).

**Registro — `Stacky Agents/backend/api/__init__.py` (2 líneas, espejo del Plan 131):**
tras la línea `from .incidents import bp as incidents_bp` (`:61`):
```python
from .evolution import bp as evolution_bp  # Plan 167 — Centro de Evolución
```
y tras `api_bp.register_blueprint(incidents_bp)` (`:122`):
```python
api_bp.register_blueprint(evolution_bp)  # Plan 167 — url_prefix="/evolution" → /api/evolution/...
```

**Tests PRIMERO:** `Stacky Agents/backend/tests/test_evolution_endpoints.py` (fixtures
`app_flag_off`/`app_flag_on` espejo del patrón real
`tests/test_plan87_devops_endpoints.py:6-29` cambiando el attr a
`STACKY_EVOLUTION_CENTER_ENABLED`; + fixture `data_dir→tmp_path`). 11 casos:
1. `test_health_200_flag_off` — 200 y `flag_enabled False`.
2. `test_overview_404_flag_off` — 404 `evolution_disabled`.
3. `test_overview_200_con_seeds` — flag ON → 200 con 4 aspects y `counts` con las 6 claves de status.
4. `test_crear_y_listar_proposal` — POST 201 → GET proposals la contiene.
5. `test_post_invalido_400` — aspecto inexistente → 400 `invalid_payload`.
6. `test_transition_flujo_completo` — submit→approve→apply (knowledge_note) → 200 y status final `applied`.
7. `test_post_origin_optimizer` — `origin="optimizer"` → 201 y el ledger registra actor `optimizer` (KPI-5).
8. `test_transition_invalida_409` — approve sobre `draft` → 409 `invalid_transition`.
9. `test_cycle_run_gate_y_shape` — con CYCLE OFF → 404 `evolution_cycle_disabled`; con ON (mocks del Monitor como en F3) → 200 con las claves de §4.9.
10. `test_rutas_sin_doble_prefijo` — el url_map contiene `/api/evolution/overview` y NO `/api/api/evolution/overview` (centinela, patrón `test_plan74_routes_registered.py`).
11. `test_hard_disable_env_gana` (A1) — con flag master ON y `monkeypatch.setenv("STACKY_EVOLUTION_HARD_DISABLE", "1")`: `GET /overview` → 404 `evolution_disabled` y `GET /health` → 200 con `hard_disabled true`.

**Comando (Git Bash):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_evolution_endpoints.py -q
```
**Criterio BINARIO:** 11/11 verdes.
**Flag:** `STACKY_EVOLUTION_CENTER_ENABLED` (gating 404 verificado por tests).
**Runtimes:** N/A (API local). **Trabajo del operador:** ninguno.

---

### F5 — Modelo puro frontend: `src/evolution/model.ts` + namespace de endpoints

**Objetivo (1 frase):** tipos DTO + lógica de chips/filtros/predicados de acción como
funciones puras testeables con vitest (sin RTL/jsdom — gap estructural conocido del repo).
**Valor:** la página de F6 queda sin lógica, solo render.

**Archivos:** CREAR `Stacky Agents/frontend/src/evolution/model.ts`; EDITAR
`Stacky Agents/frontend/src/api/endpoints.ts` (namespace nuevo, espejo del estilo
`PlansBoard` existente):

```typescript
export const Evolution = {
  health: () => fetch("/api/evolution/health").then((r) => r.json()),
  overview: () => fetch("/api/evolution/overview").then((r) => { if (!r.ok) throw new Error(`evolution overview ${r.status}`); return r.json(); }),
  proposals: (q: { status?: string; aspect_id?: string; origin?: string } = {}) => { const p = new URLSearchParams(Object.entries(q).filter(([, v]) => !!v) as [string, string][]); const qs = p.toString(); return fetch(`/api/evolution/proposals${qs ? `?${qs}` : ""}`).then((r) => { if (!r.ok) throw new Error(`evolution proposals ${r.status}`); return r.json(); }); },
  proposal: (id: string) => fetch(`/api/evolution/proposals/${id}`).then((r) => { if (!r.ok) throw new Error(`evolution proposal ${r.status}`); return r.json(); }),
  createProposal: (body: unknown) => fetch("/api/evolution/proposals", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then((r) => r.json().then((d) => ({ ok: r.ok, status: r.status, data: d }))),
  transition: (id: string, action: string, note?: string, force?: boolean) => fetch(`/api/evolution/proposals/${id}/transition`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, note: note ?? null, force: force ?? false }) }).then((r) => r.json().then((d) => ({ ok: r.ok, status: r.status, data: d }))),
  runCycle: (useLlm: boolean) => fetch("/api/evolution/cycle/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ aspects: null, use_llm: useLlm }) }).then((r) => r.json().then((d) => ({ ok: r.ok, status: r.status, data: d }))),
  ledger: (limit = 50) => fetch(`/api/evolution/ledger?limit=${limit}`).then((r) => r.json()),
  cycles: (limit = 20) => fetch(`/api/evolution/cycles?limit=${limit}`).then((r) => r.json()),
};
```

**`model.ts` — símbolos EXACTOS:**

```typescript
export type ProposalStatus = "draft" | "pending_review" | "approved" | "applied" | "rejected" | "rolled_back";
export type ProposalOrigin = "manual" | "agent" | "optimizer" | "mape";
export type ArtifactType = "free_text" | "knowledge_note" | "prompt_file" | "flag_change";
export type LoopMode = "human_in_the_loop" | "human_on_the_loop";
export interface AspectDto { id: string; name: string; description: string; target_kind: string; loop_mode: LoopMode; links: { label: string; href: string }[]; created_at: string; }
export interface FitnessDto { score: number | null; metrics: Record<string, unknown>; eval_ref: string | null; evaluated_at: string; }
export interface ProposalDto { id: string; aspect_id: string; title: string; rationale: string; origin: ProposalOrigin; artifact_type: ArtifactType; target_ref: string | null; proposed_content: string | null; base_hash: string | null; evidence: string[]; status: ProposalStatus; fitness_before: FitnessDto | null; fitness_after: FitnessDto | null; parent_proposal_id: string | null; cycle_id: string | null; snapshot_info: Record<string, unknown> | null; notes: { ts: string; actor: string; text: string }[]; created_at: string; updated_at: string; applied_at: string | null; rolled_back_at: string | null; }
export interface CycleDto { id: string; started_at: string; finished_at: string; status: string; error: string | null; rules_fired: string[]; skipped_duplicate_rules: string[]; proposal_ids: string[]; llm_used: boolean; llm_error: string | null; tokens_est_in: number; tokens_est_out: number; signals_truncated: boolean; }

// tono del StatusChip (valores REALES del barrel: components/ui/StatusChip.tsx:4)
export function statusTone(s: ProposalStatus): "success" | "warning" | "danger" | "info" | "neutral"
  // draft→"neutral"; pending_review→"info"; approved→"warning";
  // applied→"success"; rejected→"danger"; rolled_back→"neutral".
export function statusLabel(s: ProposalStatus): string
  // draft→"Borrador"; pending_review→"En revisión"; approved→"Aprobada";
  // applied→"Aplicada"; rejected→"Rechazada"; rolled_back→"Revertida".
export function loopModeLabel(m: LoopMode): string
  // human_in_the_loop→"Humano en el lazo"; human_on_the_loop→"Humano sobre el lazo".
export interface ProposalFilters { status: ProposalStatus | "TODAS"; aspectId: string | "TODOS"; origin: ProposalOrigin | "TODOS"; }
export function filterProposals(list: ProposalDto[], f: ProposalFilters): ProposalDto[]
  // AND de los 3 filtros; "TODAS"/"TODOS" no filtra; NO muta el input.
export function availableActions(p: ProposalDto): { action: string; label: string; confirm: boolean }[]
  // draft → [{submit,"Enviar a revisión",false},{reject,"Rechazar",true}]
  // pending_review → [{approve,"Aprobar",false},{reject,"Rechazar",true}]
  // approved → (artifact_type ∈ {knowledge_note,prompt_file} ? [{apply,"Aplicar",true}] : [])
  //            .concat([{reject,"Rechazar",true}])
  // applied → [{rollback,"Revertir",true}]
  // rejected/rolled_back → []
export function flagDeepLink(targetRef: string | null): string | null
  // artifact flag_change: `/settings?flag=${encodeURIComponent(targetRef)}`; null si no hay ref.
export function fitnessDisplay(f: FitnessDto | null): string
  // null → "—" (el Plan 168 lo llenará); si no → String(f.score ?? "—").
```

**Tests PRIMERO:** `Stacky Agents/frontend/src/evolution/model.test.ts` (vitest puro).
10 casos:
1. `statusTone` mapea los 6 estados a los tonos EXACTOS de arriba.
2. `statusLabel` los 6 labels exactos.
3. `loopModeLabel` los 2 labels.
4-6. `filterProposals`: por status, por aspecto+origen combinados (AND), y "TODAS/TODOS" no filtra.
7. `filterProposals` no muta el input (deep-equal antes/después).
8. `availableActions` para los 6 estados (incluye: `approved` de `free_text` NO ofrece `apply`; `applied` solo `rollback` con `confirm true`).
9. `flagDeepLink("LOCAL_LLM_MODEL") === "/settings?flag=LOCAL_LLM_MODEL"` y `flagDeepLink(null) === null`.
10. `fitnessDisplay(null) === "—"` (contrato 168: placeholder visible, jamás inventado).

**Comando (Git Bash):**
```bash
cd "Stacky Agents/frontend" && npx vitest run src/evolution/model.test.ts
```
**Criterio BINARIO:** 10/10 verdes.
**Flag:** N/A (módulo puro). **Runtimes:** N/A. **Trabajo del operador:** ninguno.

---

### F6 — Página + wiring en AMBAS navegaciones: `EvolutionCenterPage`

**Objetivo (1 frase):** el tab "🧬 Evolución" visible SOLO con flag ON, en la nav legacy
Y en el App Shell v2, con hero de KPIs, aspectos, tabla de propuestas con acciones
gateadas, botón de ciclo y ledger.
**Valor:** el feature completo usable el día uno, coherente con los planes 138/140/161/162.

**Archivos a crear (2):**
1. `Stacky Agents/frontend/src/pages/EvolutionCenterPage.tsx`
2. `Stacky Agents/frontend/src/pages/EvolutionCenterPage.module.css`

**Archivos a editar (4):**
1. `Stacky Agents/frontend/src/App.tsx` — 7 toques quirúrgicos, espejo EXACTO del patrón
   del tab `planes` (buscar por contenido; líneas de referencia 2026-07-17):
   - Union `Tab` (`:43`): agregar `| "evolution"`.
   - `TAB_PATHS` (`:45`): agregar `evolution: "/evolution",`.
   - Estado (junto a `planesEnabled`, `:101`): `const [evolutionEnabled, setEvolutionEnabled] = useState(false);`
   - Probe (espejo del bloque de `:146-148`):
     ```typescript
     void probeFlagHealth("/api/evolution/health").then((v) => {
       if (alive) setEvolutionEnabled(v);
     });
     ```
     (adentro del MISMO effect de montaje que los otros probes; respeta el patrón `alive`.)
   - Effect de fallback (`:213`): agregar `else if (tab === "evolution" && !evolutionEnabled) selectTab("team");` y `evolutionEnabled` al array de deps (`:214` y `:221`).
   - Render (`:252`): `{tab === "evolution" && evolutionEnabled && <EvolutionCenterPage />} {/* Plan 167 */}` + import arriba.
   - Nav legacy (espejo del botón de `planes`, `:394-397`): botón `🧬 Evolución` gateado por `evolutionEnabled`.
2. `Stacky Agents/frontend/src/components/shell/shellNav.ts` — 5 toques:
   - `ShellTab` (`:5-8`): agregar `| "evolution"`.
   - `TAB_META` (`:15-32`): `evolution: { label: "Evolución", iconName: "Zap" },` — **elegir un iconName que EXISTA en `ICON_BY_NAME` (`shellIcons.ts`)**; verificar con grep y si `Zap` está tomado semánticamente, usar otro existente (p. ej. el de diagnóstico) — NUNCA inventar una clave nueva sin agregar el ícono.
   - `SHELL_NAV_GROUPS` (`:40-46`): agregar `"evolution"` al FINAL de `tabs` del grupo `observabilidad` (junto a `costcenter` y `planes`).
   - `VisibilityInput` (`:48-55`): agregar `evolutionEnabled: boolean;`.
   - `computeVisibleTabs` (`:62-74`): agregar `if (input.evolutionEnabled) v.add("evolution");`.
   - NOTA: `npx tsc --noEmit` va a marcar TODOS los call-sites de `computeVisibleTabs`/`VisibilityInput` que falte actualizar (buscarlos con `grep -rn "computeVisibleTabs" frontend/src` y agregar `evolutionEnabled` en cada objeto literal — el type-checker es el verificador).
3. `Stacky Agents/frontend/src/components/shell/__tests__/shellNav.test.ts` — actualizar:
   `ALL_TABS` (`:11-15`) agrega `"evolution"`; el nombre del caso `"TAB_META cubre exactamente los 16 tabs"` (`:18`) pasa a decir `17`; los 3 objetos `VisibilityInput` literales (`:42-46`, `:53-57`, `:62-66`) agregan `evolutionEnabled: false/true/false` respectivamente (en el caso `:52-59` va `true`).
4. `Stacky Agents/frontend/src/api/endpoints.ts` — namespace `Evolution` (F5).

**Contenido EXACTO de `EvolutionCenterPage.tsx` (estructura; TODO estilo en el
`.module.css` — G6, cero `style={{}}`):**
- **Carga:** `useEffect` de montaje → `Promise.all([Evolution.overview(), Evolution.proposals()])`;
  estados `loading` (render `SkeletonList` de `components/SkeletonList`, Plan 140),
  `error` (banner con mensaje + botón "Reintentar"), `data`. **CERO pollers** (G9):
  refresco SOLO on-mount, botón "↻ Refrescar" y después de cada acción exitosa.
- **Deep-link:** en el mismo effect, `const pid = readQueryParam("proposal")`
  (`utils/queryParams.ts:10-12`); si viene, expandir el detalle de esa propuesta (G10).
- **Hero** (fila de `Card` del barrel): "Propuestas en revisión: {counts.pending_review}",
  "Aplicadas: {counts.applied}", "Aspectos: {aspects.length}", "Último ciclo:
  {formatDateTime(last_cycle.finished_at)} · {formatTokens(last_cycle.tokens_est_in +
  last_cycle.tokens_est_out)} tokens est." (o "— todavía sin ciclos"). Formateadores del
  Plan 161 (`services/format.ts`) — PROHIBIDO `Intl.*` directo (ratchet del 161).
- **Sección "Aspectos"** (`SectionHeader` + grid de 4 `Card`): nombre, description,
  `StatusChip` con `loopModeLabel` (tone `info` para HITL, `warning` para HOTL), y los
  `links` del aspecto como `<a href={link.href}>` (navegación de recarga completa por el
  router casero; el Plan 165 la absorberá — G10). La card de `knowledge_rag` muestra
  además, si el flag HOTL está ON (viene en `overview.aspects` — NO: mostrar el estado
  leyendo el chip del aspecto; el flag no viaja — mantenerlo simple: texto fijo
  "auto-aplicación configurable en el Arnés").
- **Sección "Propuestas"**: filtros con primitivas del barrel (3 `Field`+`Select`:
  Estado/Aspecto/Origen — opciones desde `model.ts`), aplicados con `filterProposals` en
  `useMemo`. Tabla: columnas `Título` (con `origin` y `evidence[0]` en subtexto),
  `Aspecto`, `Estado` (`StatusChip` con `statusTone`/`statusLabel`), `Fitness`
  (`fitnessDisplay` — hoy siempre "—", contrato 168), `Actualizada`
  (`formatDateTime`), `Acciones` (`availableActions`: las de `confirm: false` con
  `Button` del barrel; las de `confirm: true` con `ConfirmButton`
  (`components/ConfirmButton.tsx:23`) — NUNCA diálogos nativos del navegador).
  Para `flag_change` aprobadas: en lugar de "Aplicar", link "Cambiar en el Arnés" con
  `flagDeepLink(target_ref)`.
  **Manejo de 409 `target_drifted` (C6):** si viene de `apply` → Toast `warning`
  "El artefacto cambió desde que se creó la propuesta — regenerala"; si viene de
  `rollback` → Toast `warning` con un segundo `ConfirmButton` "Forzar revert (pisa la
  edición manual)" que reintenta `Evolution.transition(id, "rollback", note, true)`. Fila expandible (click) → detalle: rationale, evidence
  completa, `proposed_content` en `<pre>` con scroll, notes, snapshot_info.
- **Empty state:** `EmptyState` (`components/EmptyState.tsx`, Plan 140) cuando no hay
  propuestas tras filtrar: título "Sin propuestas todavía", hint "Corré un ciclo MAPE o
  creá una propuesta manual".
- **Formulario "Nueva propuesta"** (colapsable): primitivas del Plan 162 — `Field` +
  `Input` (título), `Field` + `Select` (aspecto; artifact_type), `Field` + `Textarea`
  (racional; contenido propuesto), `Field` + `Input` (target_ref, visible solo para
  `prompt_file`/`flag_change`). Validación inline: título y racional obligatorios;
  al enviar con errores, foco al primer error con `firstErrorFieldId`
  (`components/ui/index.ts:25`). POST → `Evolution.createProposal({..., origin: "manual"})`;
  éxito → Toast success + refresh; 400 → errores inline.
- **Botón "Correr ciclo MAPE"** (con `Checkbox` del barrel "Usar modelo local si está
  configurado", default marcado): deshabilitado + `Spinner` del barrel mientras el POST
  síncrono corre; al volver, panel de resumen del ciclo (reglas disparadas, propuestas
  creadas, `llm_used`, tokens estimados con `formatTokens`, `signals_truncated` como
  warning). Respuesta 409 → Toast `warning` "Ya hay un ciclo corriendo". Si el backend
  devolvió 404 `evolution_cycle_disabled` → ocultar el botón (leer una vez el estado con
  la primera respuesta).
- **Sección "Ledger de evolución"** (colapsable): `Evolution.ledger(50)` on-expand
  (lazy, no en el mount) → tabla `ts` (`formatDateTime`) / `event` / `action` /
  `proposal_id` / `actor` / `note`.
- **Toast:** patrón component-local del repo (`components/Toast.tsx`, default export +
  `ToastState`): estado local `toast`, render condicional.

**Tests:** los de F5 cubren la lógica; el componente NO se testea con render (RTL/jsdom
no están en `package.json` — gap estructural conocido; el gate real es `tsc` + smoke).
**Verificación de fase (BINARIA, comandos exactos):**
```bash
cd "Stacky Agents/frontend" && npx tsc --noEmit
cd "Stacky Agents/frontend" && npx vitest run src/evolution/model.test.ts
cd "Stacky Agents/frontend" && npx vitest run src/components/shell/__tests__/shellNav.test.ts
cd "Stacky Agents/frontend" && npx vitest run src/__tests__/uiDebtRatchet.test.ts
grep -c "evolution" "Stacky Agents/frontend/src/App.tsx"          # ≥ 6 (union, path, state, probe, fallback, render, nav)
grep -c "evolution" "Stacky Agents/frontend/src/components/shell/shellNav.ts"  # ≥ 4
```
**Criterio BINARIO:** los 4 comandos de test/tsc con exit 0 y los 2 greps con los mínimos
indicados. Smoke manual del operador (flag ON, backend corriendo): declarado
pendiente-de-operador (patrón disclosure Plan 111).
**Flag:** con OFF, `probeFlagHealth` devuelve false → tab ausente en las DOS navs y cero
fetchs extra.
**Impacto por runtime:** idéntico en los 3 (panel web). **Fallback:** N/A.
**Trabajo del operador:** ninguno.

---

### F7 — Cierre: ratchet + estado del doc + verificación final

**Objetivo (1 frase):** registrar los tests nuevos en el ratchet, sincronizar el estado
del doc y correr la verificación completa por archivo.

**Archivos a editar:**
1. `Stacky Agents/backend/scripts/run_harness_tests.sh` (`HARNESS_TEST_FILES=(`, `:20`) y
   `Stacky Agents/backend/scripts/run_harness_tests.ps1` (`:412` zona de entradas
   recientes): agregar como bloque nuevo "Plan 167" los 5 archivos:
   `tests/test_evolution_flags.py`, `tests/test_evolution_store.py`,
   `tests/test_evolution_apply.py`, `tests/test_evolution_cycle.py`,
   `tests/test_evolution_endpoints.py` (mismo estilo de las entradas del Plan 166).
2. Este doc (`167_PLAN_…md`): actualizar la línea `**Estado:**` a
   `IMPLEMENTADO — <fecha> (F0..F7 …)` al cerrar (regla de la casa: estado sincronizado
   en el doc).

**Comandos de cierre (todos por archivo, todos deben quedar verdes):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_evolution_flags.py -q
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_evolution_store.py -q
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_evolution_apply.py -q
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_evolution_cycle.py -q
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_evolution_endpoints.py -q
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_harness_flags.py -q
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_harness_flags_requires.py -q
cd "Stacky Agents/frontend" && npx vitest run src/evolution/model.test.ts
cd "Stacky Agents/frontend" && npx vitest run src/components/shell/__tests__/shellNav.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
```
**Criterio BINARIO:** los 10 comandos con exit 0 (fallos preexistentes de
`test_harness_flags.py` cuentan solo si la foto previa a F0 los tenía — anotar conteos
antes/después). **Runtimes:** N/A. **Trabajo del operador:** ninguno.

---

## 6. Riesgos y mitigaciones

- **R1 — Self-confirming loop (failure mode #1 del survey RSI): el generador se evalúa a
  sí mismo.** Mitigación por diseño: el ciclo 167 SOLO propone (drafts); el juicio es del
  operador (gates) y el fitness formal llega con el **arnés 168, que por contrato debe
  ser un evaluador SEPARADO del generador** (§8.1). El LLM del Analyze no puede crear ni
  eliminar drafts (solo redacción — test F3 caso 9): la señal determinista decide.
- **R2 — Diversity collapse (failure mode #2): el archivo converge a lo mismo.**
  Mitigación: archive-first como la DGM — las propuestas NUNCA se borran (rechazadas
  quedan con razón, test F1 caso 8) y `parent_proposal_id` existe desde el día uno para
  que el 169 mantenga lineage expansivo, no un "mejor único".
- **R3 — Reward hacking (failure mode #3): optimizar la métrica, no el objetivo.**
  Mitigación: señales del Monitor 100% deterministas de sistemas que ya existen (costos,
  ejecuciones, incidencias, tablero), con shapes congelados y tests; los umbrales de las
  reglas (R-A1..R-A4) son visibles en el código y el panel muestra `evidence` — rúbrica
  auditable, no reward opaco.
- **R4 — Autonomía por la puerta de atrás.** Mitigación: `closed_loop` no es un valor
  válido (test F1 caso 11); `maybe_auto_apply` tiene doble gate (flag OFF default +
  allowlist dura `{"knowledge_rag"}` + solo `knowledge_note`) y CADA transición
  automática queda en el ledger con actor `auto_hotl` (test F2 caso 10). No hay daemon ni
  cron: el ciclo solo corre on-click.
- **R5 — Escritura de artefactos fuera de alcance.** Mitigación: el único handler que
  escribe archivos del repo es `prompt_file` con allowlist anti path-traversal (resolve +
  prefijo + sufijo `.agent.md`, test F2 caso 6); `flag_change` NO se aplica
  automáticamente (el camino de escritura de flags sigue siendo ÚNICO: el panel del
  Arnés); las lecciones van a `data_dir()`, no al repo (G11).
- **R6 — Números de línea que rotan (sesiones paralelas).** TODAS las citas son
  orientativas: ubicar por contenido/símbolo (regla heredada del Plan 128 §3.9). WIP
  ajeno: G13.
- **R7 — LLM local no disponible o lento.** El enriquecimiento es best-effort con
  degradación declarada (RuntimeError → determinista puro, test F3 caso 8); el timeout lo
  gobierna `LOCAL_LLM_TIMEOUT_SEC` ya existente (`copilot_bridge.py:265`); presupuesto de
  tokens con truncado registrado (test F3 caso 10). El costo del modelo local es cero
  USD; los tokens estimados quedan en el registro del ciclo y visibles en el panel — la
  integración con el Centro de Costos para ejecuciones REALES de evals llega con el 168
  por el camino existente (las AgentExecutions ya se contabilizan solas).
- **R8 — `proposals.json` crece.** Aceptado en v1: es texto plano de decenas/cientos de
  propuestas (KB); el archive es un requisito (R2), no un leak. Si algún día pesa,
  particionar es un plan futuro — NO hacerlo ahora.
- **R9 — Un ciclo colgado deja el lock tomado.** El lock se libera en `finally` y el
  ciclo es síncrono dentro del request; el peor caso es el timeout del LLM local ya
  acotado (R7). El 409 `cycle_already_running` es informativo, no un deadlock.
- **R10 — Drift y carreras sobre el mismo artefacto (sesión paralela, dos pestañas, otra
  propuesta aplicada).** Mitigación v2: `base_hash` chequeado en apply (409
  `target_drifted`, C6), rollback que detecta edición posterior y exige `force` explícito
  (C6), `_APPLY_LOCK` end-to-end con re-chequeo de status (C3). El snapshot SIEMPRE se
  toma del contenido real previo al write, así el rollback nunca pierde datos aunque el
  operador fuerce.
- **R11 — El sistema propone tocar sus propias flags de gobernanza.** Una propuesta
  `flag_change` puede apuntar a `STACKY_EVOLUTION_*` (p.ej. sugerir prender el
  auto-apply). Eso es aceptable porque `flag_change` JAMÁS se aplica solo (§4.3) — pero
  el freno de última instancia es A1: `STACKY_EVOLUTION_HARD_DISABLE` vive FUERA del
  registry y de la app; ninguna propuesta ni flag puede alcanzarlo.

## 7. Fuera de scope (explícito)

- **Arnés de evaluación/fitness (golden tasks + jueces): Plan 168.** Acá solo viven los
  placeholders `fitness_before/after` y el módulo `backend/evals/` intocado.
- **Optimizador evolutivo GEPA-style (generate→evaluate→select→archive): Plan 169.** Acá
  solo vive su enchufe (`POST /proposals` con `origin="optimizer"` +
  `parent_proposal_id`).
- **Flywheel de conocimiento (fallo→lección→corpus RAG→contexto): Plan 170.** Acá solo
  vive el destino (`lessons.jsonl` + aspecto `knowledge_rag`).
- **`closed_loop` / autonomía proactiva: PROHIBIDO SIEMPRE** (no es "scope futuro": es un
  anti-objetivo declarado — §3.1).
- Aplicación automática de `flag_change` (el Arnés es el único camino de escritura de
  flags).
- Scheduler/cron del ciclo (no existe scheduler genérico en el repo; on-demand only).
- Editar el pipeline de planes, el ledger de supervisión o el Tablero 128 (el aspecto
  `stacky_codebase` es read-only + link).
- Notificaciones (Plan 152, pendiente), auth/RBAC/multiusuario, react-router.

## 8. Contratos hacia 168 / 169 / 170 (congelados acá, implementados allá)

### 8.0 → Los TRES planes (A1 — kill-switch compuesto, contrato NUEVO en v2)
- `services/evolution_store.evolution_hard_disabled()` es el único lector del env
  `STACKY_EVOLUTION_HARD_DISABLE`. Los planes 168, 169 y 170 DEBEN componer su gate de
  habilitación con este helper (1 línea en su `_enabled()`/equivalente), de modo que el
  kill-switch apague la SERIE COMPLETA de un solo golpe. Sus health endpoints pueden
  exponer `hard_disabled` igual que el del 167.

### 8.1 → Plan 168 (arnés de evaluación / fitness)
- **Campo:** `fitness_before` / `fitness_after` de cada propuesta, shape §4.7. El 167 los
  persiste `null` y los muestra "—".
- **Endpoint placeholder (documentado, NO implementado en 167):**
  `POST /api/evolution/proposals/<id>/fitness` body
  `{"which": "before"|"after", "fitness": {shape §4.7}}` — lo define e implementa el 168.
- **Semilla:** `backend/evals/` (golden_runner/eval_gate/harvest + fixtures por agente,
  verificados) es la base del arnés; el 168 debe REUSAR ese módulo, no reescribirlo.
- **Regla de separación (anti R1):** el evaluador del 168 NUNCA puede ser el mismo LLM
  call que generó la propuesta; señales deterministas (tests, golden) rankean por encima
  de jueces LLM.

### 8.2 → Plan 169 (optimizador evolutivo)
- **Inyección (C10 — DOS vías equivalentes, misma validación):** por HTTP
  `POST /api/evolution/proposals`, o por llamada de servicio in-process
  `evolution_store.create_proposal(...)` (lo que el 169 v1 ya especifica) — ambas con
  `origin="optimizer"`, `parent_proposal_id` para lineage y `evidence` con las trazas
  leídas (estilo GEPA: reflexión sobre trazas completas, no reward escalar). Toda la
  validación vive en `create_proposal`, así que las dos vías son el mismo contrato.
- **`base_hash` (C6, recomendación fuerte):** el optimizador DEBE enviar
  `base_hash = sha256 hex del texto del artefacto que mutó` en cada propuesta
  `prompt_file`, para que el apply detecte drift del artefacto entre la corrida y la
  aprobación. Con `null` sigue funcionando (sin chequeo).
- **Archive:** `list_proposals()` sin filtro ES el archive (nunca se borra — R2); el
  buffer Pareto/selección vive en el 169, no acá.
- **Gate:** las propuestas del optimizador entran `pending_review` — el operador sigue
  siendo el gate (la escalera §3.1 no cambia con el 169).

### 8.3 → Plan 170 (flywheel de conocimiento)
- **Destino:** aspecto `knowledge_rag` + `data_dir()/evolution/lessons.jsonl` (shape en
  F2). El 170 conecta: incidencias/fallos → lección (`knowledge_note`) → curaduría →
  promoción al corpus `docs/rag/` (SIEMPRE `.jsonl/.json/.txt`, NUNCA `.md` — G11,
  respetando `docs/rag/schema.json`) → contexto de agentes.
- **Camino human-on-the-loop:** si el operador prendió
  `STACKY_EVOLUTION_AUTO_APPLY_KNOWLEDGE_ENABLED`, el flywheel puede acumular lecciones
  solo; la promoción al corpus del repo SIEMPRE queda human-in-the-loop.

## 9. Glosario (para un modelo menor)

| Término | Definición |
|---|---|
| **MAPE** | Ciclo de auto-mejora Monitor→Analyze→Plan→Execute sobre una base de conocimiento compartida (MAPE-K). Acá: Monitor lee telemetría existente; Analyze aplica reglas; Plan emite borradores; Execute aplica SOLO con aprobación humana. |
| **human-in-the-loop (HITL)** | El humano decide ANTES: nada se aplica sin su aprobación explícita. Default de todos los aspectos. |
| **human-on-the-loop (HOTL)** | El sistema aplica solo y el humano audita/revierte DESPUÉS. Acá: solo lecciones reversibles, flag OFF por default. |
| **closed loop** | Auto-modificación sin supervisión humana. PROHIBIDO en Stacky (no es un valor válido del sistema). |
| **fitness** | Medida objetiva de si una propuesta mejora al sistema (score + métricas de un arnés de evaluación). En el 167 es un placeholder `null`; lo llena el Plan 168. |
| **lineage / archive** | Historial genealógico de propuestas (`parent_proposal_id`) + el registro completo que nunca borra nada. Evita que la evolución colapse a una sola línea (Darwin Gödel Machine). |
| **aspecto (EvolutionAspect)** | Un área mejorable de Stacky con su nivel de cierre de loop permitido: prompts de agentes, flags/modelos, conocimiento RAG, código de Stacky. |
| **propuesta (ImprovementProposal)** | Un cambio concreto propuesto sobre un aspecto, con estado (`draft→…→applied`), evidencia, y snapshot para rollback. |
| **ledger de evolución** | `ledger.jsonl` append-only: cada creación/transición/aplicación queda registrada con actor y timestamp. La auditoría del loop. |
| **ciclo (EvolutionCycleRun)** | Una corrida on-demand del MAPE, persistida en `cycles.jsonl` con señales, reglas disparadas, tokens estimados y propuestas emitidas. |
| **flag del arnés / patrón triple** | Toggle declarado en `harness_flags.py` (FlagSpec) + leído desde `config.py` + editable desde el panel del Arnés en la UI (registry dinámico). |
| **kill-switch (A1)** | Env var interna `STACKY_EVOLUTION_HARD_DISABLE`: si es `1/true/yes`, TODO el Centro de Evolución (endpoints, ciclo, apply, auto-apply) queda apagado sin importar las flags. NO aparece en la UI: es un freno de emergencia fuera del alcance del propio sistema. |
| **base_hash (C6)** | sha256 del contenido del artefacto sobre el que se redactó una propuesta `prompt_file`. Si al aplicar el contenido actual ya no coincide, el apply se niega (409 `target_drifted`): el operador aprueba diffs reales, no diffs viejos. |
| **3 runtimes** | Codex CLI, Claude Code CLI y GitHub Copilot Pro — los motores que ejecutan agentes de Stacky. Este plan es backend+panel: idéntico en los 3; el único LLM que usa es el modelo LOCAL (Ollama/LM Studio), opcional. |
| **data dir** | `runtime_paths.data_dir()` — carpeta de datos del runtime (en deploy, `DeployStackyAgents\data`). Todo lo que este plan persiste vive ahí, no en el repo. |
| **ratchet** | Tests-trinquete del repo: contadores que solo pueden bajar (deuda UI) y listas que solo pueden crecer (registro de suites). Los tests nuevos DEBEN registrarse. |
| **Tablero de Planes (Plan 128)** | Tab read-only que visualiza el pipeline proponer→criticar→implementar→supervisar de `docs/NN_PLAN_*.md`. El aspecto `stacky_codebase` enlaza ahí. |

## 10. Orden de implementación

1. **F0** — flags + config + help + meta-tests (foto previa de `test_harness_flags.py`).
2. **F1** — store puro + 14 tests.
3. **F2** — apply/rollback/auto-apply + 14 tests.
4. **F3** — ciclo MAPE + 12 tests.
5. **F4** — API + registro + 11 tests.
6. **F5** — modelo TS + namespace endpoints + 10 tests.
7. **F6** — página + wiring App.tsx/shellNav/tests de shell + tsc + ratchet UI.
8. **F7** — ratchet de tests + estado del doc + corrida completa de cierre.

## 11. Definición de Hecho (DoD)

- [ ] Las 4 flags declaradas (patrón triple completo: config + FlagSpec + `_CATEGORY_KEYS`
      + help + curated + requires), editables desde la UI del Arnés; `harness_defaults.env`
      NO tocado a mano (G12).
- [ ] Los 5 archivos de test backend verdes POR ARCHIVO con los comandos exactos de §5
      (59 casos: 8+14+14+12+11 + los meta de flags), registrados en `HARNESS_TEST_FILES`
      (sh + ps1).
- [ ] `model.test.ts` (10 casos) y `shellNav.test.ts` (actualizado a 17 tabs) verdes;
      `npx tsc --noEmit` exit 0; `uiDebtRatchet` verde (cero inline-style nuevo).
- [ ] Con flag master OFF: endpoints (salvo `/health`) → 404 `evolution_disabled`; tab
      ausente en la nav legacy Y en el Shell v2; comportamiento byte-idéntico a hoy.
- [ ] Ninguna propuesta puede aplicarse sin `approved` (KPI-1); apply→rollback de
      `prompt_file` es byte-idéntico (KPI-3); el ciclo solo emite drafts (KPI-2).
- [ ] `POST /proposals` acepta `origin="optimizer"`; `fitness_before/after` nacen `null`
      y se muestran "—" (KPI-5 — contratos 168/169 vivos).
- [ ] `closed_loop` rechazado por el store (test F1 caso 11); `maybe_auto_apply` inerte
      con el flag OFF (default) y auditado en el ledger cuando ON.
- [ ] Kill-switch A1 verificado: con `STACKY_EVOLUTION_HARD_DISABLE=1`, endpoints → 404,
      `health.hard_disabled == true`, `apply_proposal`/`run_cycle` rechazan y
      `maybe_auto_apply` devuelve False (tests F2 caso 14 y F4 caso 11).
- [ ] `update_proposal_fields` limitado a `_PATCHABLE_FIELDS` (C2, test F1 caso 13): el
      status SOLO muta por `transition()`.
- [ ] Cero pollers nuevos en el frontend (G9): ni `setInterval` ni `refetchInterval` en
      los archivos nuevos (verificable:
      `grep -c "setInterval" "Stacky Agents/frontend/src/pages/EvolutionCenterPage.tsx"` → `0`).
- [ ] El ciclo NO corre en startup ni en background: `run_cycle` solo tiene callers en
      `api/evolution.py` y en su propio módulo (verificable con pathspec fino — C9:
      `grep -rn "run_cycle" "Stacky Agents/backend" --include=*.py | grep -v "/tests/" | grep -v "services/evolution_cycle.py" | grep -v "api/evolution.py"` → 0 matches).
- [ ] Encabezado `**Estado:**` de este doc actualizado al cerrar; `git status` final con
      WIP ajeno intacto (G13).
