# 24 — Plan Capa de Amplificación del Operador: el centauro en el flujo actual

**Versión:** **v1 → v2** (crítica adversarial + re-anclaje contra el repo real)
**Fecha v1:** 2026-06-11 · **Fecha v2:** 2026-08-01
**Estado:** **RECHAZADO en v1 · v2 = alcance recortado y re-anclado, listo para pre-flight de implementación**
**Juez v2:** StackyArchitectaUltraEficientCode (perfil normal, adversarial)
**Audiencia:** dev agéntico junior / modelo menor (Haiku, Codex CLI, GitHub Copilot Pro). Cada ítem es autocontenido: objetivo, evidencia por SÍMBOLO, archivos exactos, criterio binario, test nombrado con comando exacto.

**Tesis (innegociable, sobrevive intacta):** amplificar al operador dentro del flujo que ya usa — **lanzar → supervisar → revisar → publicar** — sin quitarle UNA sola decisión. Nada se lanza solo, nada se publica solo, nada se aprende sin aprobación humana. Modelo centauro, no autopiloto.

---

## CHANGELOG v1 → v2

> El v1 se escribió el 2026-06-11 contra `feat/memoria-colaborativa-hardening`. Entre esa fecha y hoy (2026-08-01) se implementaron, entre otros, los planes **41** (pre-vuelo de intención), **47** (veredicto humano con nota), **48/54** (rechazos como anti-patrones y lecciones), **56** (goldens de regresión), **60** (aprendizaje bidireccional de ediciones en ADO), **133** (contrato de inyección de contexto) y **254** (taxonomía de `outcome_reason`). **Cuatro de los nueve ítems del v1 quedaron total o parcialmente superados por código ya en `main`, y 20 de 21 anclajes archivo:línea del §1 caducaron.**

| C# | Severidad | Resuelto en v2 |
|---|---|---|
| **C1** | BLOQUEANTE | **C1.2 (plan-first) SUPERADO por el plan 41 — se RETIRA.** Ver §0. Reemplazado por **C1.2′**, que ataca el gap medido: el preflight del 41 sólo está cableado en `POST /agents/run-brief`. |
| **C2** | BLOQUEANTE | **C2.2 (flywheel) SUPERADO en captura e inyección por los planes 47/54/60 — se RE-ESCRIBE** como capa de LECTURA-AGREGACIÓN sobre corpus existentes. Ver §0. |
| **C3** | BLOQUEANTE | **Los 9 flags nacían en OFF con motivos prohibidos** ("retro-compat byte-idéntica", "default seguro"). v2: **todas default ON**, con la categoría (A)/(B) evaluada una por una en §5. |
| **C4** | BLOQUEANTE | **C1.3 (edición inline) dependía "duro" de U2.2, que NO existe, y su señal ya la produce el plan 60 — se RETIRA.** Ver §9. |
| **C5** | BLOQUEANTE | **20 de 21 anclajes archivo:línea del §1/§3 eran falsos.** §1 reescrito: anclaje **por SÍMBOLO** + comando de verificación reproducible. |
| **C6** | IMPORTANTE | **C0.2 superado en su mayor parte por el plan 47** (`human_review` ya persiste verdict+note). Además `metadata["discard_reason"]` colisionaba semánticamente con `metadata["outcome_reason"]` del plan 254. v2: C0.2 se reduce a agregar `kind` DENTRO del bloque `human_review` existente. |
| **C7** | IMPORTANTE | El id `filesystem-artifacts` NO existe (el real es `filesystem-artifacts-status`) y hoy hay **21** ids, no 6. v2: C0.1 usa **allowlist** explícita de excluibles, nunca denylist. |
| **C8** | IMPORTANTE | El plan **invertía** el mapeo de `api/phase6.py` y proponía un endpoint `refine` cuando ya existe `POST /api/agents/refine`. v2: el ítem nuevo se llama **`/iterate`**. |
| **C9** | IMPORTANTE | `previous_execution_id` tiene hoy **0 referencias** en `frontend/src` (el v1 decía "solo el type en `endpoints.ts:774`"), y el cap de concurrencia **no aplica a copilot**. Declarado en §1 y §6. |
| **C10** | IMPORTANTE | El fallback copilot de C1.1 fallaba en silencio: `is_delta_eligible` exige `ratio < 0.30` y un feedback corto no lo cumple. v2: el path copilot NO consulta `is_delta_eligible`. |
| **C11** | IMPORTANTE | 7 archivos de test nombrados sin comando, sin venv y sin registro en el ratchet. v2: §7 con comando literal, venv literal y criterio binario anti-falso-verde. |
| **C12** | MENOR | 6 frases vagas eliminadas ("decidir al implementar", "verificar al implementar" ×2, "tamaño razonable", "el alternativo barato", "similitud simple"). Reemplazadas por valores literales. |
| **C13** | MENOR | `agents/critic.py` es un cascarón de 37 líneas (`BaseAgent` con `default_blocks=[]` y sólo `system_prompt()`): no hay parser de hallazgos. Declarado como trabajo NUEVO en C1.4. |
| **C14** | MENOR | Métrica ">80% de descartes con causa" no era binaria (sin denominador). Reemplazada en §8. |
| **C15** | MENOR | Hoy hay **DOS** stores de goldens (`backend/evals/agents/<tipo>/` y `harness/regression_goldens.py`). C2.3 nombra el suyo explícitamente. |
| **[ADICIÓN ARQUITECTO]** | — | **C0.4 — Atribución de lecciones: qué lección viajó en qué run y con qué resultado.** El flywheel del 48/54/60 ya gira, pero **gira a ciegas**: una lección tóxica envenena todos los runs futuros y nadie puede verla ni retirarla con evidencia. Read-only, default ON, una sola clave de metadata, cero trabajo del operador. Ver §4. |

---

## 0. FALLO EXPLÍCITO: C1.2 y C2.2 frente a los planes 41 y 60

Este apartado es vinculante. Ningún implementador debe construir C1.2 ni el C2.2 del v1.

### C1.2 (modo plan-first) — **SUPERADO. SE RETIRA DEL ALCANCE.**

**Evidencia (verificada abriendo los archivos el 2026-08-01):**

- `docs/41_PLAN_PREFLIGHT_INTENCION_Y_PLAN_NEGOCIABLE.md` — header: **"Estado: IMPLEMENTADO 2026-06-19 (F0–F4)"**, con 5 archivos de test verdes citados y `IntentPreflightModal.tsx` integrado.
- `backend/services/intent_preflight.py` existe y expone exactamente el contrato que C1.2 quería inventar: `IntentBrief` (dataclass con supuestos, preguntas abiertas y confianza), `generate_intent_brief`, `derive_open_questions`, `rank_and_flag`, `build_corrections_block`, y la constante `CORRECTIONS_BLOCK_ID = "operator-corrections"`.
- Cableado real en `backend/api/agents.py`, dentro de `POST /run-brief`: `from services import intent_preflight` (:824), `generate_intent_brief(...)` (:830), `rank_and_flag(...)` (:839), `to_payload(intent)` en la respuesta (:847), y `build_corrections_block(corrections) + context_blocks` en el relanzamiento aprobado (:895). Es un flujo negociable de dos pasos (`preflight` → `approved`/`corrections`), es decir **el checkpoint humano antes de ejecutar**.
- Está **ENCENDIDO**: `backend/config.py:1069-1070` → `INTENT_PREFLIGHT_ENABLED = os.getenv("INTENT_PREFLIGHT_ENABLED", "true")`. Registrado en `services/harness_flags.py:2877` con dos flags satélite (`:2897`, `:2905`).
- La corrección del operador entra al run con **prioridad 110**, la más alta de toda la tabla `_BLOCK_PRIORITY` (`services/context_enrichment.py:377-397`), inyectada en `context_enrichment.py:1113`. O sea: no sólo existe el checkpoint, además su resultado manda sobre todo lo demás.

**Por qué además el mecanismo del v1 era estrictamente PEOR:** C1.2 proponía **quemar un run completo** del agente para producir un `plan.md`, cerrarlo en `needs_review`, y después gastar un segundo run (el refine) para ejecutar. El plan 41 resuelve lo mismo con **una pasada corta de LLM server-side** (`invoke_short_llm` vía el bridge interno), sin abrir ninguna sesión CLI. El objetivo declarado de C1.2 — "el costo de un supuesto equivocado baja de un run entero a un plan de 1-2 minutos" — el 41 lo baja a **cero runs**.

**Lo que SÍ queda vivo (gap medido, no supuesto):** el preflight está cableado **únicamente** en `POST /run-brief` (`api/agents.py:715`). Las otras tres puertas de lanzamiento **no lo tienen**: `POST /run` (`:383` — la que usa `AgentLaunchModal`), `POST /run-incident` (`:985`) y `POST /run-incident-dev` (`:1195`). Ese hueco se formaliza como **C1.2′** en §4.

### C2.2 (flywheel de correcciones humanas) — **SUPERADO EN CAPTURA E INYECCIÓN. NO superado en agregación ni en propuesta. SE RE-ESCRIBE.**

**Lo que quedó superado (y por lo tanto se BORRA del diseño):**

- **Captura de la corrección humana sobre el artefacto publicado** → plan 60, `docs/60_PLAN_APRENDIZAJE_BIDIRECCIONAL_EDICIONES_ADO.md`, header **"IMPLEMENTADO 2026-06-21 · v3 · F0..F6 verdes"**. Código vivo: `backend/harness/ado_edit_detect.py`, `backend/harness/ado_edit_diff.py`, `backend/services/ado_edit_ledger.py`, `backend/services/ado_edit_learning.py` (`edit_to_lesson_content:45`, `learn_from_work_item:85`, `sweep_recent_runs:233`). Flag `STACKY_ADO_EDIT_LEARNING_ENABLED` registrado en `services/harness_flags.py:3294` y **default ON desde 2026-07-05** (`harness_flags.py:3344`).
- **Captura del rechazo con nota** → plan 47: `backend/services/human_review.py::build_human_review(*, verdict, note, reviewed_by)` con veredictos canónicos `("approved","rejected","approved_with_notes")`, `MAX_NOTE_CHARS=2000` y normalización de `discarded`→`rejected`; endpoint `POST /api/executions/<id>/human-review` (`api/executions.py:422`), con consumidor frontend real en `frontend/src/api/endpoints.ts:1467`.
- **Conversión de rechazos en lecciones e inyección en runs futuros** → planes 48/54: `backend/services/rejection_lessons.py` (`build_items:36`, `build_prefix:83`, `load_for_run:100`, `pure_rejection_to_lesson:138`) + `backend/services/anti_patterns.py` + `backend/api/anti_patterns.py`. La inyección es automática: bloque `rejection-lessons` con prioridad **82** en `_BLOCK_PRIORITY`, más `evolution-lessons` (79) del plan 170.
- **Promoción a golden** → plan 56: `backend/harness/regression_goldens.py` (`derive_positive_golden:146`, `derive_negative_golden:59`, `save_golden:237`, `load_goldens:259`), ya puenteado desde el 60 (F4 de su v3).

**Conclusión dura:** la premisa **D-A4 del v1 — "las correcciones humanas se pierden" — es FALSA hoy.** El lazo captura → lección → corpus → inyección en el siguiente run está cerrado y encendido. Todo el diseño de C2.2 que hablaba de "capturar" hay que borrarlo.

**Lo que NO está superado y por lo tanto SOBREVIVE como C2.2′:**

1. **Taxonomía cerrada y agrupable del rechazo.** `human_review.note` es texto libre; agrupar por texto libre no es determinista. Y `metadata["outcome_reason"]` **no sirve para esto**: sus 9 valores (`services/run_outcome.py`, espejados en `frontend/src/utils/outcomeReason.ts`) describen **cómo terminó el proceso** (`clean_exit`, `quota_exhausted`, `reaper_timeout`, `cli_failure`…), no **por qué el humano lo rechazó**. Son ejes ortogonales.
2. **Vista agregada "qué corrijo siempre".** No existe ningún endpoint ni pantalla que responda "para el agente `functional`, ¿cuáles son mis 3 correcciones más repetidas de los últimos 30 días?".
3. **Propuesta de mejora del `.agent.md`.** La idea C del portafolio del plan 41 ("Banco de Pruebas de Prompts en Sombra") fue documentada y **descartada** — se eligió la D. No hay nada construido.

---

## 1. Sustrato real (anclado por SÍMBOLO, verificado 2026-08-01)

> **Regla anti-caducidad (C5):** ningún ítem de este plan cita un número de línea como contrato. Se cita **archivo + símbolo**. Antes de tocar nada, el implementador corre el comando de verificación y si un símbolo no aparece, **para y reporta** en vez de inferir.
>
> ```powershell
> $py = "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\venv\Scripts\python.exe"
> $bk = "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
> Select-String -Path "$bk\services\context_enrichment.py" -Pattern "^def enrich_blocks|^_BLOCK_PRIORITY"
> Select-String -Path "$bk\harness\resume.py" -Pattern "^def resolve"
> Select-String -Path "$bk\services\human_review.py" -Pattern "^def build_human_review|^HUMAN_VERDICTS"
> Select-String -Path "$bk\services\delta_prompt.py" -Pattern "^def compute_diff|is_delta_eligible"
> Select-String -Path "$bk\services\parallel_runs.py" -Pattern "^def parallel_explore|^def chain_refinement"
> ```

| Sustrato | Símbolo real (archivo::símbolo) | Estado / trampa |
|---|---|---|
| Enriquecimiento multi-runtime | `services/context_enrichment.py::enrich_blocks` — firma **keyword-only**: `(*, ticket_id, agent_type, raw_blocks, project_ctx=None, log=None) -> tuple[list[dict], dict\|None]` | **NO acepta `exclude_ids`** (el único `exclude*` del módulo es `exclude_ticket_id`, interno del few-shot). C0.1 debe AGREGAR el parámetro. |
| Los 3 puntos de llamada | `agent_runner.py`, `services/claude_code_cli_runner.py`, `services/codex_cli_runner.py` — buscar la llamada literal `enrich_blocks(` | **Siguen siendo exactamente 3.** Los dos runners CLI **se movieron a `backend/services/`** (el v1 los citaba en la raíz y con líneas ~300 corridas ~350). |
| Tabla de prioridades / ids de bloque | `services/context_enrichment.py::_BLOCK_PRIORITY` | **21 ids, no 6.** El id `filesystem-artifacts` del v1 **NO EXISTE**: el real es `filesystem-artifacts-status` (definido en `services/artifact_context.py`). |
| Preview de contexto (sólo memoria) | `api/memory.py::context_preview_route` — ruta `GET /api/memory/context-preview`; consumidor `frontend/src/api/endpoints.ts` (`StackyMemoryContextPreview`) | Parcial: no hay preview del briefing completo. Es el hueco de C0.1. |
| Estimación de costo | `api/agents.py::estimate_cost` — ruta `POST /api/agents/estimate` | OK. |
| Input a run vivo | `api/executions.py::send_execution_input` — ruta `POST /api/executions/<id>/input` | OK; el texto NO se persiste como señal. |
| Resume multi-runtime (H7) | `harness/resume.py::resolve(*, runtime, ticket_id, agent_type, project, current_blocks=None, execution_id=None) -> tuple[str\|None, str\|None]` | **VÁLIDO — acepta `execution_id`.** Es el único anclaje del v1 que sobrevivió sin cambios. |
| Re-ejecución con delta (FA-32) | `api/agents.py` (bloque `prev_exec_id` → `delta_prompt.compute_diff` → `build_delta_prompt`) + `services/delta_prompt.py::compute_diff(old_blocks, new_blocks) -> DiffResult` (**posicional**, no keyword-only) | **Trampa C10:** `DiffResult.is_delta_eligible` = `ratio < 0.30 and len(changed) > 0`. Un feedback corto contra blocks vacíos NO califica ⇒ el delta se descarta en silencio. |
| Consumidores frontend del delta | — | **0 (cero) referencias a `previous_execution_id` en todo `frontend/src`.** El v1 decía "sólo el type en `endpoints.ts:774`"; ese type ya no está. |
| Exploración paralela / cadena | `services/parallel_runs.py::parallel_explore(*, agent_type, ticket_id, context_blocks, user, variants=None)` y `::chain_refinement(...)`; endpoints en `api/phase6.py` | **Trampa C8: el v1 invierte el mapeo.** La ruta `POST /api/agents/refine` llama a `chain_refinement`; `POST /api/agents/explore` llama a `parallel_explore`. **`/agents/refine` YA EXISTE** ⇒ el ítem nuevo NO puede llamarse `refine`. |
| Diff entre ejecuciones | `api/executions.py::diff` — ruta `GET /api/executions/<id>/diff/<other_id>`; devuelve `{"left": a.to_dict(), "right": b.to_dict()}`; 404 si falta una, **400 si difieren `ticket_id` o `agent_type`** | OK, sin UI. |
| Crítico bajo demanda (FA-47) | `agents/critic.py::CriticAgent(BaseAgent)` — 37 líneas, `type="__critic__"`, `default_blocks=[]`, único método `system_prompt()`; ruta real `POST /api/executions/<id>/critique` (`api/phase5.py::critique`) | **Trampa C13: es un cascarón.** No hay parser de hallazgos ni salida estructurada. Ojo: el docstring de `critic.py` dice `/api/agents/...` y **miente** sobre la ruta. |
| ABCompare / ReplayPlayer | `frontend/src/components/ABCompare.tsx` (props `executionIds, onPickWinner, onClose`), `ReplayPlayer.tsx` | **Huérfanos CONFIRMADOS.** Las únicas referencias a `ABCompare` fuera del propio módulo son `__tests__/uiDebtBaseline.json` y `__tests__/adhocModalAllowlist.json`, que son **baselines de ratchet, no consumidores de producción**. |
| Veredicto humano | `services/human_review.py::build_human_review` + `api/executions.py::human_review_route` (`POST /api/executions/<id>/human-review`) | **Superó a C0.2 (C6).** Ya hay verdict + note validada + `approved_with_notes`. `POST /approve` y `/discard` siguen **sin body** y `_set_verdict` exige `status == "completed"`. |
| Causa mecánica del cierre | `services/run_outcome.py::classify_outcome_reason` (9 valores) + `frontend/src/utils/outcomeReason.ts` | **Eje ORTOGONAL** al juicio humano. No reusar como taxonomía de rechazo (C6). |
| Preguntas del agente (WS2) | `api/executions.py::answer_question` — ruta `POST /api/executions/<id>/answer` | **Sigue muerto:** `agent_runner` no define `answer_question`, el `hasattr` nunca pasa, `abort(501)` siempre. Confirmado. |
| Schema por agente | `api/agents.py::schema` — ruta `GET /api/agents/<agent_type>/schema` | OK. |
| Goldens (DOS stores, C15) | (1) `backend/evals/agents/{business,developer,functional,qa,technical}/` — el de H6/harvest. (2) `harness/regression_goldens.py` — el del plan 56, con `_store_path` por proyecto+agente+work_item_type | C2.3 usa **el (1)**, explícitamente. |
| Few-shot / anti-patterns | `agent_runner.py::run_agent(..., use_few_shot=True, use_anti_patterns=True)`; consumo real en `agents/base.py` | **Sigue siendo path copilot.** Los CLI tienen su propio camino: `_inject_cli_fewshot` / `_inject_rejection_lessons` en `context_enrichment.py`. |
| Guard + slots | `api/agents.py` → `run_guard.find_active_run` (409 `duplicate_run`) y `run_slots.try_acquire` (429 `max_concurrent_runs`) | **Trampa C9: el 429 sólo se evalúa si `runtime in ("claude_code_cli","codex_cli")`.** GitHub Copilot **no tiene cap de concurrencia**. |
| Cierre del run | `harness/post_run.py::finalize_run(*, runtime, agent_type, output_text, ado_id=None, gate_enabled=False, ...) -> PostRunResult` | `PostRunResult.status_suggestion` sólo puede ser `"completed"` o `"needs_review"`. |
| Contrato de reglas del run | `harness/run_contract.py` — `rules_text(*, runtime, mcp_enabled)`, `assumption_rules_text()`, `applies_to(agent_type)`, `with_assumption_policy(rules, agent_type)` | Punto de inserción para cualquier instrucción fija. |
| Panel de detalle de ejecución | `frontend/src/components/ExecutionDetailDrawer.tsx` | **EXISTE.** Todos los "degradado: AgentHistoryModal mientras U0.1 no exista" del v1 quedan obsoletos: el destino es este drawer. |

**Restricciones vinculantes (sin cambios):** cap duro de modelo vía `llm_router.clamp_model`; "solo Stacky escribe en ADO" = todo por `ado_write_outbox`; mono-operador sin RBAC (`current_user` es un header sin validar — **cualquier control de permisos es sobre-ingeniería**); claves de metadata existentes son contrato (agregar, nunca renombrar); todo flag nuevo entra en `FLAG_REGISTRY` en el MISMO PR; suite completa contaminada → validar por archivo.

---

## 2. Qué NO es este plan (anti-scope explícito)

1. **No es autonomía.** Sin auto-intake, sin triage automático, sin procesamiento nocturno, sin lanzamientos no iniciados por el operador.
2. **No re-propone lo ya implementado.** Todo lo listado en §0 y en §9 está construido y encendido; tocarlo es regresión, no mejora.
3. **No agrega decisiones automáticas.** Toda acción nueva es un gesto explícito del operador; todo aprendizaje produce *propuestas* que un humano aprueba.
4. **No agrega roles ni permisos.** Mono-operador.

---

## 3. Diagnóstico corregido

| # | Debilidad | Estado 2026-08-01 |
|---|---|---|
| **D-A1** | El briefing es invisible e inajustable: el operador controla ticket + runtime + un textarea (`modal_user_input`); los otros 20 bloques se ensamblan server-side dentro de `enrich_blocks`. | **VIGENTE.** Sigue sin haber preview del briefing completo (sólo del bloque de memoria) ni forma de excluir bloques. → **C0.1** |
| **D-A2** | No hay checkpoint humano antes de ejecutar. | **RESUELTO PARA `run-brief`** por el plan 41 (flag ON). **VIGENTE para `POST /run`, `/run-incident`, `/run-incident-dev`.** → **C1.2′** |
| **D-A3** | Iterar = relanzar de cero; toda la maquinaria de iteración sin UI. | **VIGENTE y EMPEORADA:** `previous_execution_id` ya no tiene ni el type en frontend (0 refs). → **C1.1**, **C0.3** |
| **D-A4** | Las correcciones humanas se pierden. | **FALSO HOY.** Planes 47/48/54/56/60 cierran captura → lección → inyección, con flags ON. Lo que falta es **agregación y visibilidad**, no captura. → **C0.2 (reducido)**, **C2.2′** |
| **D-A5** | No hay segunda opinión. | **VIGENTE.** `CriticAgent` es un cascarón sin parser ni consumidores; `parallel_explore` sin UI. → **C1.4**, **C2.1** |
| **D-A6** | Sin profundidad por tipo de artefacto. | **VIGENTE.** El schema existe pero no se renderiza como checklist; los goldens de `evals/agents/` nunca entran al briefing. → **C2.3** |
| **D-A7 (NUEVO, v2)** | **El flywheel gira a ciegas.** Los bloques `operator-corrections` (prio 110), `rejection-lessons` (82) y `evolution-lessons` (79) se inyectan en TODOS los runs, pero no existe ninguna forma de saber **qué lección viajó en qué run** ni **si el run que la llevó salió mejor o peor**. Una lección mal derivada envenena todos los runs futuros de forma silenciosa y permanente. | **VIGENTE, no atacado por ningún plan.** → **C0.4 [ADICIÓN ARQUITECTO]** |

---

## 4. Alcance v2 (8 ítems: 6 sobrevivientes recortados + 1 re-scope + 1 adición)

Complejidad: S ≤ ½ día, M ≤ 2 días, L > 2 días (dev agéntico).

---

### C0.1 — Briefing visible y curable en el launch

- **Ataca:** D-A1. **Complejidad:** M. **Dependencias:** ninguna.
- **Objetivo:** que el operador vea ANTES de lanzar exactamente qué bloques va a recibir el agente, con título/origen/tamaño, y pueda destildar los que no aportan.
- **Diseño:**
  1. `services/context_enrichment.py::enrich_blocks` gana un parámetro **aditivo keyword-only** `exclude_ids: frozenset[str] = frozenset()`. Cada injector se saltea si su id está en la lista. `exclude_ids` vacío ⇒ resultado **byte-idéntico** (test de regresión obligatorio).
  2. **ALLOWLIST de excluibles (C7), literal y cerrada** — sólo estos 6 ids pueden destildarse:
     `{"ado-similar-tickets", "ado-comments", "ado-attachments", "glossary-auto", "few-shot-approved", "filesystem-artifacts-status"}`.
     Cualquier otro id en `exclude_ids` ⇒ **400** con la allowlist en el mensaje. Razón: los 15 restantes son contrato de otros planes — `operator-corrections` (41), `run-directive`/`process-catalog`/`process-discipline`/`acceptance-contract` (133), `acceptance-criteria` (Q0.1), `rejection-lessons` (48/54), `evolution-lessons` (170). Permitir destildarlos degrada gates ajenos en silencio. **Denylist prohibida:** un id nuevo de un plan futuro caería del lado excluible por accidente.
  3. Endpoint nuevo `POST /api/agents/briefing-preview` en `api/agents.py`: body `{agent_type, ticket_id, project, context_blocks}` → llama `enrich_blocks` en dry-run (no crea execution, no toca ADO en escritura) → devuelve `{blocks:[{id,title,source,chars,tokens_est,priority,excludable:bool}], budget:{applied,limit}, cost_estimate}`. `excludable` = `id in ALLOWLIST`. `tokens_est` reusa el estimador de bloques ya existente en `context_enrichment`; `cost_estimate` reusa `api/agents.py::estimate_cost`.
  4. `POST /api/agents/run` acepta `excluded_block_ids: list[str]` (aditivo, default `[]`); los 3 runtimes lo pasan a `enrich_blocks`. Sello: `metadata["briefing"] = {"excluded": [...], "previewed": true}` (clave nueva).
  5. Frontend: en `AgentLaunchModal.tsx`, sección colapsable "Lo que va a ver el agente" con checkbox por bloque (todos tildados por default; los no excluibles se muestran **sin** checkbox y con el motivo).
- **Criterio binario:** (a) `enrich_blocks(..., exclude_ids=frozenset())` devuelve exactamente la misma lista que sin el parámetro, comparada por `json.dumps(sort_keys=True)`; (b) excluir `ado-similar-tickets` ⇒ ese id no aparece en `input_context` persistido de la run y sí aparece en `metadata.briefing.excluded`; (c) excluir `acceptance-criteria` ⇒ HTTP 400; (d) el preview no crea ninguna fila en `agent_executions`.
- **Tests:** `backend/tests/test_plan24_briefing_preview.py` — 8 casos: regresión byte-idéntica, exclusión por cada uno de los 6 ids de la allowlist (parametrizado, `\b` en el assert para no contar subcadenas), 400 por id fuera de allowlist, dry-run sin efectos.

---

### C0.2 — Causa estructurada del rechazo (REDUCIDO por C6)

- **Ataca:** D-A4 (lo único que le falta). **Complejidad:** S. **Dependencias:** ninguna.
- **Qué NO se hace (C6):** no se crea `metadata["discard_reason"]`; no se toca `POST /approve` ni `POST /discard`; no se reusa `outcome_reason` (eje ortogonal).
- **Diseño:** `services/human_review.py::build_human_review` gana un parámetro **opcional** `kind: str | None = None`, validado contra una taxonomía cerrada literal:
  `HUMAN_REVIEW_KINDS = ("incomplete", "wrong_approach", "hallucination", "bad_format", "out_of_scope", "other")`.
  `kind` ausente ⇒ el bloque resultante es **idéntico** al actual (la clave no se agrega). `kind` inválido ⇒ `ValueError` ⇒ el endpoint responde **400** con la lista válida. El endpoint `human_review_route` lee `payload.get("kind")` y lo pasa.
  Frontend: en el flujo de rechazo de `ExecutionDetailDrawer.tsx`, 6 radios + el botón existente sin motivo (**nunca obligar**: fricción cero).
- **Criterio binario:** body sin `kind` ⇒ el dict devuelto por `build_human_review` no contiene la clave `kind` (assert de ausencia **precedido por un assert que garantiza que el dict no está vacío**, para que la ausencia no pase por accidente); `kind="wrong_approach"` ⇒ persistido en `metadata.human_review.kind`; `kind="lo_que_sea"` ⇒ 400 con los 6 valores en el mensaje.
- **Tests:** `backend/tests/test_plan24_review_kind.py` — 6 casos.

---

### C0.3 — Comparar ejecuciones lado a lado (adoptar ABCompare)

- **Ataca:** D-A3. **Complejidad:** S/M. **Dependencias:** ninguna. **Prerrequisito visual de C2.1.**
- **Backend:** ninguno. `api/executions.py::diff` ya valida mismo ticket+agente y devuelve `{left, right}`.
- **Frontend:** en `AgentHistoryModal.tsx`, modo selección de 2 ejecuciones → botón "Comparar" → montar `ABCompare`. **Antes de montarlo hay que validar el contrato:** `ABCompare` recibe `executionIds` pero el endpoint devuelve `{left, right}` con `to_dict()` completo; si los tipos no calzan, se adapta en el call site, **no** reescribiendo el huérfano.
- **Criterio binario:** 2 runs del mismo ticket+agente ⇒ vista lado a lado; distinto `agent_type` ⇒ botón deshabilitado (el endpoint daría 400); cerrar sin elegir ⇒ cero escrituras.
- **Tests:** `frontend/src/utils/__tests__/plan24AbCompare.test.ts` — módulo **`.ts` puro** que mapea `{left,right}` → props de `ABCompare`. **No** un `.test.tsx`: `@testing-library/react` y `jsdom` no están instalados en este repo y un test que renderice React reporta "no tests" con **exit 0** (falso verde).
- **Nota de ratchet:** `ABCompare.tsx` figura en `frontend/src/__tests__/uiDebtBaseline.json` y en `adhocModalAllowlist.json`. Adoptarlo **no** debe subir su deuda: si el call site agrega estilos inline o un color HEX, el ratchet de uiDebt se pone rojo. Usar tokens del tema (`--accent`, `--border`, `--text-primary`, `--bg-panel`; **`--color-*` NO existe**).

---

### C0.4 — Atribución de lecciones: qué lección viajó, en qué run, con qué resultado · **[ADICIÓN ARQUITECTO]**

- **Ataca:** D-A7 (nuevo). **Complejidad:** M. **Dependencias:** ninguna (C2.2′ la consume, pero C0.4 vale sola).
- **El problema, en una frase:** hoy Stacky **aprende** (planes 48/54/60, todos ON) e **inyecta** lo aprendido en cada run (prioridades 110/82/79), pero **nadie puede auditar el aprendizaje**. Si una lección se derivó mal — un `edit_to_lesson_content` sobre una edición de ADO que fue un typo, o un rechazo cuya nota decía otra cosa — esa lección viaja en el briefing de **todos** los runs futuros de ese agente, para siempre, sin dejar rastro y sin forma de identificarla. Es el único mecanismo del sistema que se auto-refuerza sin ningún lazo de control humano. Eso es exactamente lo que la Regla 11 prohíbe, y está pasando ahora.
- **Diseño (mínimo, read-only, una sola clave nueva):**
  1. En `services/context_enrichment.py::enrich_blocks`, cada injector de lecciones (`rejection-lessons`, `evolution-lessons`, `operator-corrections`, `few-shot-approved`) ya conoce los identificadores de las piezas que empaqueta. `enrich_blocks` acumula esos ids y los devuelve dentro del `dict` de metadata que **ya retorna** como segundo elemento de su tupla — **sin cambiar la aridad de la firma**. Los runtimes sellan `metadata["lesson_attribution"] = {"<block_id>": ["<lesson_id>", ...]}`.
     *Si un injector no expone un id estable, se usa un `sha256(content)[:12]` calculado en el propio injector: determinista, sin PII adicional y estable entre runs mientras la lección no cambie.*
  2. Endpoint `GET /api/operator-signals/lessons?agent_type=X&days=30` (**read-only puro**): para cada `lesson_id` visto, agrega `{lesson_id, block_id, runs_total, runs_approved, runs_rejected, first_seen, last_seen, sample_execution_ids[:5]}` leyendo `metadata.lesson_attribution` cruzado con `metadata.human_review.verdict`. **Cero LLM, cero escritura, cero red.**
  3. UI: tabla en la sección "Mejora continua" (ver C2.2′) ordenada por `runs_rejected` descendente. Cada fila tiene **un solo botón: "Retirar esta lección"**, que llama al flujo de moderación de memoria **ya existente** (`MemoryPage`) para pasarla a inactiva. El sistema **nunca** retira una lección solo; propone la evidencia, el humano decide.
- **Por qué vale mucho más de lo que cuesta:** convierte el flywheel de una caja negra auto-reforzante en un lazo **auditable y reversible**. Sin esto, C2.2′ propondría mejoras derivadas de un corpus que nadie puede verificar. Con esto, la pregunta "¿esta lección me está ayudando o me está arruinando los runs?" tiene una respuesta con números.
- **Restricciones que respeta:** cero trabajo del operador (la atribución se sella sola); **default ON** (§5, categoría ninguna: es lectura + una clave de metadata); los 3 runtimes por construcción (`enrich_blocks` es el único punto de inyección y es compartido); human-in-the-loop intacto (retirar una lección es un click humano); mono-operador (sin permisos); backward-compatible (un run viejo sin la clave ⇒ la UI muestra "sin datos", nunca rompe).
- **Criterio binario:** (a) un run cuyo briefing incluyó 2 lecciones ⇒ `metadata.lesson_attribution` tiene esos 2 ids y ningún otro; (b) `enrich_blocks` sigue devolviendo una tupla de 2 elementos (test que lo asertá explícitamente); (c) el endpoint sobre una BD sin ninguna `lesson_attribution` devuelve `200 []`, no 500; (d) el endpoint no ejecuta ningún `INSERT`/`UPDATE` (test con sesión en modo lectura o con espía sobre `session.commit`).
- **Tests:** `backend/tests/test_plan24_lesson_attribution.py` — 7 casos: sellado por injector, aridad de la tupla, agregación con verdicts mixtos, BD vacía, ausencia de escrituras, run legacy sin la clave, id estable por sha256.

---

### C1.1 — Iterar con feedback sin relanzar (renombrado a `/iterate` por C8)

- **Ataca:** D-A3 (cierre). **Complejidad:** M/L. **Dependencias:** C0.1 (suave).
- **Nombre:** el endpoint es **`POST /api/executions/<id>/iterate`**. **Prohibido llamarlo `refine`**: `POST /api/agents/refine` ya existe y llama a `parallel_runs.chain_refinement` (C8). El servicio nuevo es `backend/services/run_iterate.py` (no `run_refine.py`).
- **Diseño:**
  ```python
  # backend/services/run_iterate.py
  def iterate(*, execution_id: int, feedback: str, user: str) -> int:
      # 1. valida: la origen está en status "completed" o "needs_review"; si no → 409
      # 2. crea execution hija (mismo ticket/agente/proyecto/runtime) con:
      #      context_blocks = [{"id": "operator_feedback", "kind": "editable", ...}]
      #      excluded_block_ids = los 6 de la allowlist de C0.1 (el resume ya
      #      trae el contexto; re-inyectarlo duplica tokens). Sin C0.1 → se
      #      re-inyecta: funciona, gasta de más, y así queda declarado.
      #      metadata: iterated_from=<padre>, iteration=<n_padre+1>, iterate_transport=...
      # 3. transporte por runtime:
      #      claude_code_cli | codex_cli → harness.resume.resolve(execution_id=<padre>)
      #      github_copilot → prefix construido a mano con el output del padre
      # 4. pasa por run_guard.find_active_run y run_slots.try_acquire como cualquier launch
  ```
- **Fallback copilot (corrección C10):** el path copilot **NO** consulta `delta_prompt.DiffResult.is_delta_eligible`. Ese predicado exige `ratio < 0.30 and len(changed) > 0` y un feedback corto contra `context_blocks` casi vacíos **no lo cumple** ⇒ el delta se descartaría en silencio y la iteración se lanzaría completa, pagando todo el contexto de nuevo sin avisar. En su lugar, el prefix se construye directo: `output` del padre (truncado a **12.000 caracteres**, valor literal) + el bloque `operator_feedback`. `iterate_transport` vale `"resume"` o `"prefix"`, nunca `"delta"`.
- **Cap de concurrencia (C9):** `run_slots.try_acquire` sólo se evalúa para `claude_code_cli` y `codex_cli`. En copilot la iteración **no tiene cap**; `run_guard.find_active_run` (409 por duplicado) sí aplica en los 3. Queda declarado, no se agrega cap nuevo (fuera de scope).
- **Frontend:** botón "Iterar con feedback" + textarea en `ExecutionDetailDrawer.tsx` (**no** en `AgentHistoryModal`: el drawer ya existe). Cadena visible 1→2→3 con costo por iteración desde la telemetría existente y link "ver diff con la anterior" → C0.3.
- **Criterio binario:** iterate sobre run claude `completed` ⇒ hija con `metadata.iterated_from` = id del padre, `iteration = padre+1`, `iterate_transport="resume"`, y su `input_context` contiene **exactamente un** bloque `operator_feedback`; iterate sobre copilot ⇒ `iterate_transport="prefix"` y el prefix contiene el output del padre truncado a 12.000 chars; iterate sobre run en `running` ⇒ **409**; con una hija ya corriendo ⇒ **409** del guard.
- **Tests:** `backend/tests/test_plan24_run_iterate.py` — 9 casos con runners mockeados.

---

### C1.2′ — Extender el pre-vuelo del plan 41 a `POST /agents/run` (REEMPLAZA a C1.2)

- **Ataca:** D-A2, en las 3 puertas que el plan 41 no cableó. **Complejidad:** S/M. **Dependencias:** ninguna (el 41 ya está ON).
- **Qué NO se hace (C1):** no se construye ningún "modo plan-first", no se antepone ninguna instrucción al prompt, no se quema un run para producir `plan.md`, no se crea `metadata["plan_gate"]`, no se revive `waiting_for_question`. Todo eso lo resuelve el plan 41 con una pasada corta y sin abrir sesión.
- **Diseño:** replicar en `POST /api/agents/run` (`api/agents.py`) el mismo protocolo de dos pasos que ya usa `POST /run-brief`: si `config.INTENT_PREFLIGHT_ENABLED` y el body trae `preflight=true` y no `approved`, llamar `intent_preflight.generate_intent_brief(...)` + `rank_and_flag(...)` y devolver `{"intent": to_payload(intent)}` **sin lanzar nada**; en el segundo llamado (`approved=true`), anteponer `intent_preflight.build_corrections_block(corrections)` a `context_blocks` y lanzar. Frontend: reusar `IntentPreflightModal.tsx` **tal cual** desde `AgentLaunchModal.tsx`.
- **Fallback (paridad 3 runtimes):** el preflight corre server-side con el LLM backend interno, no con el runtime del agente ⇒ es idéntico en Codex, Claude Code y Copilot. Si el bridge no responde, `PreflightRuntimeUnavailable` ⇒ **se lanza el run normal**, exactamente como con el flag OFF. Nunca bloquea.
- **Criterio binario:** `POST /run` con `preflight=true` ⇒ respuesta con `intent` y **cero filas nuevas** en `agent_executions`; segundo llamado con `approved=true` y correcciones ⇒ el `input_context` de la run contiene el bloque `operator-corrections`; `INTENT_PREFLIGHT_ENABLED=false` ⇒ `POST /run` byte-idéntico al actual; bridge caído ⇒ la run se lanza igual.
- **Tests:** `backend/tests/test_plan24_preflight_run.py` — 6 casos (mock de `generate_intent_brief`, incluido el que levanta `PreflightRuntimeUnavailable`).

---

### C1.4 — Segunda opinión bajo demanda (crítica cruzada con árbitro humano)

- **Ataca:** D-A5. **Complejidad:** M. **Dependencias:** C1.1 (para "Iterar con esto"; degradado: copiar el feedback a mano).
- **Trabajo NUEVO declarado (C13):** `agents/critic.py` es un `BaseAgent` de 37 líneas con `default_blocks=[]` y sólo `system_prompt()`. **No existe** parser de hallazgos, ni schema, ni salida estructurada. Hay que construir `backend/services/critique_parse.py::parse_findings(text) -> list[Finding]` con `Finding = {finding, severity, suggestion}` y `severity in ("high","medium","low")`.
- **Diseño:** `POST /api/executions/<id>/critique-v2` en `api/executions.py` (v2 para no romper `api/phase5.py::critique`, que queda deprecado con comentario). Body `{model?: str}`. **Modelo cruzado, regla literal (C12):** se lee el modelo del padre de `metadata`; el crítico usa el **primer modelo de `llm_router` distinto del padre cuyo tier sea el más bajo disponible**; si no hay ninguno distinto, se usa el mismo y se sella `metadata.critique.cross_model=false`. `clamp_model` aplica siempre. Resultado: `metadata["critique"] = {"model", "cross_model", "findings", "requested_at"}`. Parse fallido ⇒ **502 con el texto crudo en el detalle** (bajo demanda: el error se muestra, no se traga).
- **Arbitraje:** en `ExecutionDetailDrawer.tsx`, cada hallazgo con Aceptar/Rechazar. Aceptados ⇒ textarea pre-armado ⇒ "Iterar con esto" ⇒ C1.1. Rechazados ⇒ `findings[i].dismissed=true` (señal de falsos positivos del crítico para C2.2′).
- **Criterio binario:** crítica sobre un run cuyo modelo es M ⇒ `metadata.critique.model != M` o `cross_model=false`; aceptar 2 de 5 hallazgos ⇒ el feedback del iterate contiene **exactamente** esos 2; salida no parseable ⇒ 502 y **cero** escritura en `metadata.critique`; el endpoint de FA-47 sigue respondiendo igual (test de compat).
- **Tests:** `backend/tests/test_plan24_critique_v2.py` — 8 casos con LLM mockeado.

---

### C2.1 — Duelo A/B de modelos/runtimes bajo demanda

- **Ataca:** D-A5/D-A3. **Complejidad:** M. **Dependencias:** C0.3 (dura), C0.2.
- **Diseño:** opt-in en el modal de launch: selector de la 2ª variante + estimación de costo doble (`estimate_cost`) + confirm explícito ("esto lanza 2 runs: ~$X"). Llama a `POST /api/agents/explore` (**el que mapea a `parallel_explore`**, C8) con cap duro de 2 variantes.
- **Guard (resuelto, ya no "verificar al implementar" — C12):** `parallel_explore` sella `metadata["ab_group"] = <uuid>` y **el 2º miembro del grupo se lanza con `skip_duplicate_guard=True`**, parámetro interno nuevo que sólo `parallel_explore` puede pasar y que **no** se expone en el body de ningún endpoint. El guard sigue protegiendo los launches normales.
- **No-publicación del perdedor (resuelto, ya no "verificar al implementar" — C12):** **invariante dura, no flag.** El endpoint del duelo devuelve **409 `ab_duel_autopublish_conflict`** si el `agent_type` del ticket tiene autopublicación activa para ese proyecto. Sin excepciones, sin modo degradado. Razón: dos runs simultáneos con autopublish crean **dos** work items en ADO — eso es escritura destructiva en el sistema real del operador (categoría B), y ningún confirm de UI lo compensa.
- **Cierre:** al terminar ambos ⇒ C0.3 ⇒ `onPickWinner` ⇒ ganador `approved` + `metadata["ab_winner"]=true`; perdedor vía `human-review` con `verdict="rejected"` y `kind="other"` + nota `"ab_loser"` (C0.2 — **no** se inventa un 7º kind).
- **Criterio binario:** el duelo lanza **exactamente 2** runs con el mismo `input_context` (comparado por hash) y el mismo `ab_group`; sobre un agente con autopublish ⇒ 409; el 2º run no dispara 409 del guard; **cero** work items creados en ADO durante el test (espía sobre `ado_write_outbox`).
- **Tests:** `backend/tests/test_plan24_ab_duel.py` — 7 casos.

---

### C2.2′ — Mejora continua: agregación y propuesta sobre los corpus existentes (RE-ESCRITO por C2)

- **Ataca:** D-A4 (lo que falta) + D-A7. **Complejidad:** M (era L; se cayó toda la mitad de captura). **Dependencias:** C0.2 (para el `kind`), C0.4 (para la atribución).
- **Qué NO se hace (C2):** **cero captura nueva.** No se lee ADO, no se detectan ediciones, no se derivan lecciones, no se escriben goldens. Todo eso ya lo hacen `services/ado_edit_learning.py`, `services/rejection_lessons.py`, `services/anti_patterns.py` y `harness/regression_goldens.py`, con flags ON.
- **Diseño:** nuevo `backend/services/operator_signals.py`, **lector puro**:
  ```python
  def collect(*, agent_type: str | None, project: str | None, days: int = 30) -> list[Signal]
  # Signal = {kind, execution_id, agent_type, project, payload, at}
  # Fuentes (todas YA persistidas por otros planes, ninguna nueva):
  #   metadata.human_review          → verdict/note/kind        (plan 47 + C0.2)
  #   metadata.critique.findings     → aceptados/dismissed      (C1.4)
  #   metadata.ab_winner             → resultado de duelo       (C2.1)
  #   metadata.lesson_attribution    → qué lección viajó        (C0.4)
  #   input_context[id=operator_feedback] → texto de iteración  (C1.1)
  def summarize(signals) -> dict
  ```
- **Agrupación (literal, ya no "similitud simple" — C12):** se agrupa **exclusivamente por la tupla `(agent_type, human_review.kind)`**. **No hay agrupación por keywords ni por similitud de texto**: el texto libre no es determinista, no es testeable con un criterio binario, y un modelo menor implementaría seis heurísticas distintas. Un grupo se muestra si `count >= STACKY_SIGNALS_MIN_COUNT` (default **3**).
- **Endpoints (read-only):** `GET /api/operator-signals/summary?agent_type=X&days=30` y el `…/lessons` de C0.4.
- **UI "Mejora continua"** (sección en Diagnóstico): (1) grupos de rechazo por kind con conteo y ejemplos; (2) la tabla de atribución de C0.4.
- **Destinos, TODOS con click humano explícito:**
  - **(a) Proponer como memoria** ⇒ `memory_store.save_observation(...)` con estado **pendiente de moderación** (la pantalla ya existe: `MemoryPage`). Nunca activa directa.
  - **(b) Sugerir mejora del prompt** ⇒ **una** llamada LLM (modelo del tier más bajo; `clamp_model` aplica) con el `.agent.md` actual + los ejemplos del grupo ⇒ devuelve texto de sugerencia. **El sistema JAMÁS escribe el `.agent.md`.** El operador lo aplica por el flujo de import normal.
  - **(c) Candidatos a golden** ⇒ marca `metadata["golden_candidate"]=true` en la última iteración aprobada de una cadena o en el ganador de un duelo, con botón que **linkea** a `harness/regression_goldens.py::save_golden`. No se re-implementa nada del plan 56.
- **Criterio binario:** con 3 `human_review` de `kind="incomplete"` para `functional` ⇒ el summary devuelve 1 grupo con `count=3`; con 2 ⇒ **0 grupos** (mínimo); la propuesta de memoria crea una entrada con estado pendiente y **ninguna** activa; la sugerencia de prompt **no modifica ningún `.agent.md`** (test con hash del archivo antes/después); ninguna escritura ocurre sin llamada explícita al endpoint de destino (test que corre `collect`+`summarize` y espía `session.commit`).
- **Tests:** `backend/tests/test_plan24_operator_signals.py` — 9 casos con fixtures de metadata.

---

### C2.3 — Profundidad por tipo de artefacto (exemplar dorado + checklist de completitud)

- **Ataca:** D-A6. **Complejidad:** M. **Dependencias:** C0.1 (dura, para la parte de briefing).
- **(a) Exemplar dorado.** Nuevo injector `_inject_golden_exemplar` en `services/context_enrichment.py`, id de bloque **`golden-exemplar`**, prioridad **55** (mismo tier que `few-shot-approved`, podable bajo presión de budget). Fuente: **`backend/evals/agents/<agent_type>/`** — el store de H6/harvest, ya redactado sin PII — **no** `harness/regression_goldens.py`, que es el store del plan 56 y tiene otra clave (C15). Toma el golden más reciente por mtime, truncado a **8.000 caracteres** (valor literal). Sin goldens para el `agent_type` ⇒ el bloque **no se agrega** (nunca un placeholder vacío). El id **no** entra en la allowlist de excluibles de C0.1: se controla por su flag.
- **(b) Checklist de completitud.** Nuevo `backend/services/artifact_checklist.py`:
  `get_checklist(agent_type) -> list[{item, source}]` deriva de (1) los campos requeridos del schema (`api/agents.py::schema`) y (2) las reglas de `artifact_validator` aplicables al kind. **Los "ítems custom por proyecto" del v1 se ELIMINAN del alcance** (C12: "decidir al implementar por lo que menos migración requiera" es exactamente la ambigüedad que un modelo menor resuelve mal — y crear una tabla nueva por una feature opcional no se justifica).
  `evaluate(agent_type, artifact_text) -> list[{item, met: bool | None}]` — `met=None` significa "a criterio del operador". **Prohibido usar un LLM acá**: la checklist es mecánica y barata; el juicio profundo es C1.4.
  Visibilidad: (1) bloque `completeness-checklist` en el briefing; (2) en `ExecutionDetailDrawer.tsx`, la checklist con ✓ / ✗ / — .
- **Criterio binario:** agente con golden ⇒ el bloque `golden-exemplar` aparece en `input_context` con ≤ 8.000 chars; agente sin goldens ⇒ el bloque **no existe** en la lista (assert de ausencia precedido de assert de lista no vacía); `get_checklist("functional")` deriva ≥1 ítem del schema **real** de hoy; `evaluate` sobre un artefacto vacío no lanza excepción y devuelve todos los ítems con `met` en `False` o `None`.
- **Tests:** `backend/tests/test_plan24_artifact_checklist.py` (7 casos) y `backend/tests/test_plan24_golden_exemplar.py` (6 casos).

---

## 5. Flags: **todas default ON** (resolución de C3)

> **Regla de la casa:** default ON es la regla. Una flag en OFF debe citar por escrito **(A)** quema tokens **en reposo** (loop/daemon/barrido/polling/prefetch/inyección que llama a un modelo sin que el operador pida nada) o **(B)** escribe en un sistema **real** del operador, destruye datos o le saca la decisión. El v1 justificaba sus 9 flags en OFF con "retro-compat byte-idéntica" y "default seguro" — **motivos rechazados**. Precedente en este mismo repo: `INTENT_PREFLIGHT_ENABLED` nace en `"true"` (`config.py:1069`) y `STACKY_ADO_EDIT_LEARNING_ENABLED` está ON desde 2026-07-05; ninguno rompió nada.

| Flag | Tipo | Default | ¿(A) reposo? | ¿(B) escribe real? | Veredicto |
|---|---|---|---|---|---|
| `STACKY_BRIEFING_PREVIEW_ENABLED` | bool | **true** | No — sólo corre si el operador abre el modal | No — dry-run, no crea execution | **ON** |
| `STACKY_ITERATE_ENABLED` | bool | **true** | No — sólo con click en "Iterar" | No — la hija usa el mismo camino de publicación que cualquier run que el operador lance; no agrega capacidad de escritura nueva | **ON** |
| `STACKY_CRITIQUE_ENABLED` | bool | **true** | No — sólo con click en "Pedir crítica" | No — escribe sólo `metadata` | **ON** |
| `STACKY_AB_DUEL_ENABLED` | bool | **true** | No — sólo con click + confirm de costo | No — **el 409 por autopublish es invariante dura, no flag** (C2.1). Con esa invariante la capacidad deja de ser (B) | **ON** |
| `STACKY_OPERATOR_SIGNALS_ENABLED` | bool | **true** | No — endpoint bajo demanda | No — lectura pura | **ON** |
| `STACKY_SIGNALS_MIN_COUNT` | int | **3** | — | — | umbral, no interruptor |
| `STACKY_PROMPT_SUGGESTION_ENABLED` | bool | **true** | No — 1 llamada LLM por click | No — **nunca** escribe el `.agent.md` | **ON** |
| `STACKY_GOLDEN_EXEMPLAR_ENABLED` | bool | **true** | No — se inyecta sólo cuando el operador lanza | No — lee `evals/agents/`, ya redactado sin PII | **ON** |
| `STACKY_ARTIFACT_CHECKLIST_ENABLED` | bool | **true** | No — derivación mecánica, sin LLM | No | **ON** |
| `STACKY_LESSON_ATTRIBUTION_ENABLED` | bool | **true** | No — se sella durante un run que el operador pidió | No — una clave de metadata | **ON** |
| ~~`STACKY_PLAN_FIRST_AGENTS`~~ | — | — | — | — | **ELIMINADA** (C1.2 retirado) |

**Ninguna flag mezclada.** El único caso que lo era en el v1 — el duelo A/B, que combinaba "comparar dos outputs" (inocuo) con "crear dos work items en ADO" (destructivo) — se resuelve **sacando la mitad destructiva del producto** (409 duro), no partiendo la flag.

**Cableado obligatorio de cada flag (bloque atómico, mismo PR):** `backend/config.py` (con `os.getenv(..., "true")` — el comentario no es el default, el `os.getenv` sí), `backend/services/harness_flags.py::FLAG_REGISTRY` (con `group` y categorización en `_CATEGORY_KEYS`), `backend/.env.example`, y el generador de `harness_defaults.env`. Verificación: `python -m pytest backend/tests/test_harness_flags_help.py -q` — **este archivo tiene rojos ajenos de fábrica**; el criterio es **delta cero**, no verde absoluto.

---

## 6. Priorización y secuencia

| Orden | Ítem | Compl. | Valor | Riesgo | Dependencias |
|---|---|---|---|---|---|
| 1 | **C0.2** Causa estructurada del rechazo | S | Alto (habilita C2.2′) | Bajo | — |
| 2 | **C0.4** Atribución de lecciones **[ADICIÓN]** | M | **Muy alto** (hace auditable el flywheel que ya corre a ciegas) | Bajo (read-only + 1 clave) | — |
| 3 | **C0.3** Adoptar ABCompare | S/M | Alto | Bajo | — |
| 4 | **C0.1** Briefing visible y curable | M | Muy alto | Bajo | — |
| 5 | **C1.2′** Preflight del 41 en `POST /run` | S/M | **Muy alto por esfuerzo** (reusa un plan ya implementado y encendido) | Bajo | — |
| 6 | **C1.1** Iterar sin relanzar | M/L | Muy alto | Medio (toca launch path) | C0.1 suave |
| 7 | **C1.4** Crítica cruzada con árbitro | M | Alto | Bajo | C1.1 suave |
| 8 | **C2.3** Exemplar + checklist | M | Alto | Bajo | C0.1 dura |
| 9 | **C2.2′** Mejora continua (agregación) | M | Muy alto (compuesto) | Bajo | C0.2 dura, C0.4 dura |
| 10 | **C2.1** Duelo A/B | M | Medio | Medio (guard + invariante de publicación) | C0.3 dura, C0.2 |

**Reglas de implementación vinculantes:**
1. TDD: test rojo primero, por la razón correcta, antes del código.
2. Validar **por archivo** de test (la suite completa está contaminada; `pytest tests` entero no es un veredicto).
3. Flag nuevo = bloque atómico del §5 en el MISMO PR.
4. Metadata: **sólo claves nuevas**, nunca renombrar. Las de este plan: `briefing`, `human_review.kind`, `lesson_attribution`, `iterated_from`, `iteration`, `iterate_transport`, `critique`, `ab_group`, `ab_winner`, `golden_candidate`.
5. ADO sólo vía `ado_write_outbox`.
6. Sin fallback silencioso entre runtimes: si un transporte no aplica, se declara en `iterate_transport` y se muestra.
7. Ningún huérfano se reusa sin validar el contrato de props contra el shape real del endpoint.
8. CSS modules + tokens del tema (`--accent`, `--success`, `--danger`, `--border`, `--text-primary`, `--bg-panel`; **`--color-*` no existe**), cero deps npm nuevas.
9. UI degrada con gracia ante metadata ausente (los runs viejos no tienen ninguna de las claves nuevas).
10. **Regla 11, innegociable:** ninguna acción se ejecuta sin gesto explícito del operador y ningún aprendizaje modifica prompts/memoria/goldens sin aprobación humana. Si un ítem puede leerse como "el sistema decidió solo", está mal implementado.

---

## 7. TDD: comandos exactos y criterio anti-falso-verde (resolución de C11)

**Venv (literal, el que funciona):** `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\venv\Scripts\python.exe` (Python 3.11.9). El otro (`backend\.venv`) **no** es el de referencia.

**Comando por archivo (PowerShell, rutas absolutas por los espacios en "Stacky Agents"):**
```powershell
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\venv\Scripts\python.exe" -m pytest `
  "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_plan24_briefing_preview.py" -q
```

**Frontend:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/utils/__tests__/plan24AbCompare.test.ts --testTimeout=60000
npx tsc --noEmit
```

**Criterio BINARIO por fase (los tres, no dos):**
1. La salida dice `N passed` con el **N exacto** declarado en el ítem, y `0 failed`.
2. La salida **no** dice `no tests ran` ni `deselected` — `pytest -k` sin match devuelve **exit 0** y es el falso verde más común de la casa.
3. `npx tsc --noEmit` sale **0** para todo ítem que toque frontend.

**Registro en el ratchet (obligatorio, mismo PR):** cada archivo de test nuevo se registra en **AMBOS**: `backend/scripts/run_harness_tests.sh` y `backend/scripts/run_harness_tests.ps1`. Tienen sintaxis distinta y **ya divergen entre sí**; hay que editar los dos a mano. Alternativa válida y más barata: meter los casos nuevos dentro de un archivo **ya registrado**, evitando el trámite. **El ratchet no admite rutas con espacios** — los archivos van bajo `backend/tests/`, nunca fuera del backend.

**Rojos ajenos conocidos:** `test_harness_flags_help.py` y las suites de deuda de UI (`uiDebtBaseline.json`, `formatDebtBaseline.json`, `motionDebtBaseline.json`) están rojas de fábrica. El criterio es **delta cero contra el commit base**, nunca "verde absoluto".

**Casos borde obligatorios en todo ítem que toque el launch path (C1.1, C1.2′, C2.1):** run zombie / pegado en `running` ⇒ 409, nunca cuelgue; JSON inválido en el body ⇒ 400 con mensaje, nunca 500 mudo; BD read-only ⇒ el endpoint de lectura sigue respondiendo y el de escritura devuelve error explícito; `metadata_json` corrupto o no-dict ⇒ tratado como `{}`, nunca excepción.

---

## 8. Métricas de éxito (todas binarias o contables — resolución de C14)

| Métrica | Hoy (medido 2026-08-01) | Objetivo |
|---|---|---|
| Bloques del briefing visibles antes de lanzar | 1 de 21 (sólo el de memoria) | 21 de 21 listados con tokens (C0.1) |
| Ids de bloque que el operador puede excluir | 0 | 6 (la allowlist de C0.1), ni uno más |
| Puertas de lanzamiento con pre-vuelo de intención | 1 de 4 (`/run-brief`) | 2 de 4 (`+ /run`) (C1.2′) |
| Costo de una corrección sobre un output | 1 run completo | 1 iteración con `iterate_transport="resume"` en 2 de 3 runtimes (C1.1) |
| Rechazos con `kind` de taxonomía cerrada | 0 (hoy sólo texto libre) | el campo existe, se ofrece siempre y **nunca** se obliga (C0.2) |
| Lecciones inyectadas cuyo impacto es auditable | **0 de todas** | 100% de las inyectadas después de C0.4, con conteo aprobado/rechazado por lección |
| Formas de pedir segunda opinión | 0 con consumidor | 2 (crítica C1.4, duelo C2.1) |
| Escrituras automáticas a prompt/memoria/golden sin click humano | 0 | **0** (test explícito que lo verifica en C2.2′) |
| Work items duplicados en ADO por un duelo A/B | n/a | **0**, garantizado por 409, no por convención (C2.1) |

---

## 9. Ítems retirados del alcance (y por qué)

| Ítem v1 | Destino | Evidencia |
|---|---|---|
| **C1.2 — Modo plan-first** | **RETIRADO.** Superado por el plan 41 (IMPLEMENTADO 2026-06-19, flag ON), que además lo resuelve **sin quemar ningún run**. Sustituido por **C1.2′**, que cubre el gap real (3 de 4 puertas de lanzamiento sin preflight). | `services/intent_preflight.py`; `api/agents.py` `:824-895`; `config.py:1069`; `IntentPreflightModal.tsx` |
| **C1.3 — Edición inline + `human_delta`** | **RETIRADO.** (a) Su dependencia "dura" U2.2 (doc 23) **no existe** y el propio v1 declaraba que su modo degradado era "ítem pospuesto" — eso no es un ítem, es una nota. (b) Su señal ya la produce el plan 60 por un canal **mejor**: captura la edición humana real sobre el work item publicado, con **cero** trabajo del operador y sin construir un editor. | `harness/ado_edit_detect.py`, `harness/ado_edit_diff.py`, `services/ado_edit_ledger.py`, `services/ado_edit_learning.py::edit_to_lesson_content`; flag ON desde 2026-07-05 |
| **C2.2 — Flywheel (mitad de captura)** | **RETIRADO** y re-escrito como **C2.2′** (sólo agregación + propuesta). La premisa "las correcciones humanas se pierden" es falsa hoy. | `services/rejection_lessons.py`, `services/anti_patterns.py`, `services/human_review.py`, `harness/regression_goldens.py` |
| **Revivir `waiting_for_question` / `answer_question`** | **CONFIRMADO FUERA DE SCOPE** (el v1 ya lo excluía y v2 lo ratifica midiéndolo: `agent_runner` no define `answer_question`, el `hasattr` nunca pasa, `abort(501)` siempre). El checkpoint humano es ENTRE runs (plan 41), no dentro de uno. | `api/executions.py::answer_question` |
| **Adoptar `ReplayPlayer`** | **FUERA DE SCOPE**, igual que en v1. Sigue huérfano (sus únicas referencias son 3 baselines de ratchet). Adoptarlo sólo si C0.3 demuestra demanda. | `frontend/src/components/ReplayPlayer.tsx` |
| **`metadata["discard_reason"]`** | **RETIRADO.** Colisiona semánticamente con `metadata["outcome_reason"]` (plan 254, 9 valores, con mapa de UI). El `kind` va DENTRO de `human_review`. | `services/run_outcome.py`; `frontend/src/utils/outcomeReason.ts` |
| **Ítems custom de checklist por proyecto** | **RETIRADO** de C2.3. El v1 decía "decidir al implementar por lo que menos migración requiera" — ambigüedad pura para un modelo menor, y no se justifica una tabla nueva por una feature opcional. | C12 |

---

## 10. Veredicto de la crítica v1 → v2

**RECHAZADO** (5 bloqueantes: C1, C2, C3, C4, C5).

**Criterios binarios del veredicto:**
1. ≥1 BLOQUEANTE ⇒ RECHAZADO. **Hay 5.**
2. Un ítem cuyo objetivo ya está implementado y encendido en `main` es un bloqueante, no un detalle: implementarlo es regresión. **C1.2 y C1.3 califican; C2.2 califica en su mayor parte.**
3. Una flag en OFF sin citar (A) o (B) es bloqueante. **9 de 9 lo estaban.**
4. Un plan cuya sección "punto de partida" tiene 20 de 21 anclajes falsos no es implementable por un modelo menor sin inferir. **Bloqueante de mecanismo.**

**La v2 es el plan vigente.** Sale del recorte con 8 ítems (de 9), todos con símbolo verificado, criterio binario, test nombrado con comando literal y flag en ON justificada — más una capacidad nueva (**C0.4**) que ningún plan del repo cubre y que hace auditable, por primera vez, el aprendizaje que Stacky ya está aplicando en cada run.
