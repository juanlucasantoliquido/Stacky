# 24 — Plan Capa de Amplificación del Operador: el centauro en el flujo actual

**Fecha:** 2026-06-11
**Estado:** propuesto (ningún ítem implementado)
**Predecesores:** `docs/21_PLAN_HARDENING_ARNES_MULTI_PROVEEDOR.md` (H0-H8, implementado salvo H2.5), `docs/22_PLAN_ARNES_VENTAJA_COMPETITIVA.md` (V0 implementado y verificado en código; V1-V2 propuestos), `docs/23_PLAN_CAPA_PERCEPTIBLE_VALOR_VISIBLE.md` (U0-U2, propuesto).
**Audiencia:** dev agéntico junior. Cada ítem es autocontenido: objetivo, evidencia, diseño con archivos exactos, criterios de aceptación, tests TDD y complejidad.

**Tesis (innegociable):** amplificar al operador dentro del flujo que ya usa — **lanzar → supervisar → revisar → publicar** — sin quitarle UNA sola decisión. Nada se lanza solo, nada se publica solo, nada se aprende sin aprobación humana. El valor agregado es que **cada run supervisado rinda mucho más**: mejor input (briefing curado), control fino durante el run (plan-first), iteración barata (refine sin relanzar), revisión potenciada (crítica cruzada, A/B, checklist por tipo) y aprendizaje invisible de cada corrección humana. Modelo centauro, no autopiloto.

**Relación con los docs 22 y 23 (frontera de no-solapamiento):**
- El doc 22 ataca la capa *interna* del arnés (perfiles, guardrails de launch, taxonomía de fallos, pricing, versionado de prompts, intake universal, CI, advisor, golden loop, cache). El doc 23 ataca la capa *perceptible* (panel de detalle, firma en ADO, webhooks, bandeja de revisión, self-review automático vs AC, preview pre-publicación, pipelines orquestados, digest).
- Este plan ataca la capa de **amplificación**: las palancas que multiplican el rendimiento de cada run supervisado y que hoy existen como sustrato backend sin producto (ver §1).
- Donde un ítem de acá toca una zona ya planificada, es **incremental y declara la dependencia**: C1.3 EXTIENDE U2.2 (edición inline sobre el preview pre-publicación), C1.4 EXTIENDE U1.2 (árbitro humano sobre crítica bajo demanda, vs self-review automático), C2.2 alimenta V1.1/V2.3 (propuestas de prompt y candidatos a golden — no re-implementa ni versionado ni promote). Ningún ítem bloquea en los docs 22/23: todos declaran modo degradado.
- Componentes huérfanos del frontend que el doc 23 dejó sin dueño y este plan adopta: **ABCompare** (C0.3/C2.1) y **ReplayPlayer** (fuera de scope aquí salvo nota en C0.3 — adoptarlo solo si C0.3 demuestra demanda). El **CriticAgent FA-47** gana dueño real en C1.4.

> **Nota de numeración:** el ítem V2.1 del doc 22 referencia un checklist de nuevo runtime. Ese documento se creará como `docs/25_CHECKLIST_NUEVO_RUNTIME.md` (el 23 y el 24 ya están tomados).

---

## 1. Punto de partida: el sustrato de amplificación YA existe (no re-implementar)

Verificado contra el código el 2026-06-11 en `feat/memoria-colaborativa-hardening`. Esta tabla es el hallazgo central del plan: **casi toda la maquinaria está construida y sin producto encima**.

| Sustrato | Dónde vive | Estado |
|---|---|---|
| Enriquecimiento de contexto multi-runtime (memoria → client-profile → épica → artefactos previos → tickets similares → comentarios/adjuntos ADO → budget con ranking F2.4) | `services/context_enrichment.py::enrich_blocks` (pura respecto a `raw_blocks`); llamada en los 3 runtimes: `agent_runner.py:588`, `claude_code_cli_runner.py:363`, `codex_cli_runner.py:288` | OK — **invisible para el operador** |
| Preview parcial de contexto | solo memoria: `GET /api/memory/context-preview` (`api/memory.py:77`); costo: `POST /api/agents/estimate` FA-33 (`api/agents.py:482`) | Parcial — no existe preview del briefing completo |
| Input del operador a un run vivo | `POST /api/executions/<id>/input` (`api/executions.py:71`) → claude stdin en vivo (`capabilities.py:25`); codex vía `codex exec resume` (`codex_cli_runner.py:159-165`) | OK — solo mientras corre; el texto no se persiste como señal |
| Resume multi-runtime (H7) | `harness/resume.py::resolve(*, runtime, ticket_id, agent_type, project, current_blocks=None, execution_id=None)` — acepta `execution_id` explícito | OK — solo se usa implícitamente al relanzar |
| Re-ejecución con delta (FA-32) | `previous_execution_id` en `POST /api/agents/run` → `delta_prompt.compute_diff` (elegible si ratio < 0.30) → prefix con output previo (`api/agents.py:297-309`) | OK backend — **cero consumidores frontend** (grep `previous_execution_id` en frontend → solo el type en `endpoints.ts:774`) |
| Exploración paralela (FA-49) y cadena de refinamiento (FA-48) | `services/parallel_runs.py::parallel_explore / chain_refinement` + endpoints `api/phase6.py:73,93` | OK backend — **cero consumidores frontend** |
| Diff entre ejecuciones del mismo ticket+agente | `GET /api/executions/<id>/diff/<other_id>` (`api/executions.py:171`) | OK — sin UI |
| Crítico bajo demanda (FA-47) | `agents/critic.py` + `POST /api/phase5/executions/<id>/critique` | OK — sin consumidores, sin AC (doc 23 D-P7) |
| Componentes A/B y replay construidos | `frontend/src/components/ABCompare.tsx` (props `executionIds, onPickWinner, onClose`), `ReplayPlayer.tsx` (`executionId, open, onClose`) | Huérfanos — el doc 23 §2 los dejó sin dueño; este plan adopta ABCompare |
| Verdict del operador | `POST /executions/<id>/approve|discard` (`api/executions.py:119-148`) — approve dispara `post_run_memory.capture_on_approval` (type `session_summary`, flag OFF) | OK — **discard no pide causa; nada más se captura** |
| Esqueleto de preguntas del agente (WS2) | `POST /executions/<id>/answer` + status `waiting_for_question` (`api/executions.py:309-337`) | **Muerto en WS1**: `agent_runner` no implementa `answer_question` → 501 siempre |
| Schema de artefacto por agente | `GET /api/agents/<agent_type>/schema` (`api/agents.py:438`) + reglas en `artifact_validator` | OK — no se usa para checklist visible ni briefing |
| Goldens por agente (H6) | `backend/evals/agents/<agent_type>/` (redactados sin PII vía harvest) | OK — solo sirven a evals, nunca al briefing |
| Few-shot / anti-patterns | `use_few_shot`/`use_anti_patterns` en `run_agent` (default true) → solo path copilot (`agent_runner.py:688`, `agents/base.py`) | OK — nunca expuesto al operador; CLI no lo usa |
| Guard anti-duplicados + cap de concurrencia (V0.2/V0.3 doc 22) | `api/agents.py:319-349` (`run_guard.find_active_run` → 409; `run_slots.try_acquire` → 429) | **Implementado** (verificado hoy) — C1.1/C2.1 lo reusan |
| Macros declarativas (FA-51) | `services/macros.py` (DSL de workflows del usuario) | OK — sustrato; los pipelines con gates son U2.1 (doc 23), acá no se tocan |

**Restricciones vinculantes (idénticas a docs 22/23, no relitigar):** cap duro de modelo vía `llm_router.clamp_model`; "solo Stacky escribe en ADO" = todo por `ado_write_outbox`; mono-operador sin RBAC; claves de metadata existentes son contrato (agregar, nunca renombrar); todo flag nuevo entra en `FLAG_REGISTRY` en el MISMO PR; suite completa contaminada → validar por archivo.

---

## 2. Qué NO es este plan (anti-scope explícito)

1. **No es autonomía.** Sin auto-intake, sin triage automático, sin procesamiento nocturno, sin lanzamientos no iniciados por el operador. Ese enfoque fue evaluado y descartado: la forma de trabajo actual (humano decide todo) se mantiene y se potencia.
2. **No re-propone lo planificado.** El self-review automático contra AC es U1.2 (doc 23); el preview pre-publicación es U2.2 (doc 23); el versionado de prompts es V1.1 (doc 22); promote-to-golden es V2.3 (doc 22); la bandeja de revisión es U1.1 (doc 23); los pipelines orquestados son U2.1 (doc 23). Acá solo hay extensiones declaradas sobre esas piezas.
3. **No agrega decisiones automáticas.** Toda acción nueva es un gesto explícito del operador; todo aprendizaje produce *propuestas* que un humano aprueba. Default OFF u opt-in en el 100% de los ítems.

---

## 3. Diagnóstico: dónde se desperdicia el rendimiento del run supervisado

| # | Debilidad | Evidencia | Impacto |
|---|---|---|---|
| **D-A1** | **El briefing es invisible e inajustable.** El operador controla: ticket + runtime + un textarea opcional (1 solo bloque `modal_user_input`, `AgentLaunchModal.tsx:223-233`). Todo lo demás (memoria, client-profile, épica, artefactos previos, similares, comentarios ADO) se ensambla server-side DESPUÉS del launch, dentro del runner (`enrich_blocks` en los 3 runtimes). No hay preview del briefing completo (solo del bloque de memoria, `api/memory.py:77`) ni forma de incluir/excluir bloques. | `AgentLaunchModal.tsx`, `context_enrichment.py:34-96` | El mejor predictor del output es el input, y el operador no puede ni verlo ni curarlo. Contexto irrelevante entra (ruido + tokens); contexto que el operador sabe valioso no se puede priorizar. |
| **D-A2** | **No hay checkpoint humano dentro del run.** El esqueleto de preguntas está muerto: `answer_question` aborta 501 (`api/executions.py:329-331`, `agent_runner` WS1 no lo implementa); ningún runner produce `waiting_for_question`. El transporte para checkpoints SÍ existe (claude stdin vivo; codex `exec resume`; H7 resume con `execution_id` explícito) pero no hay producto: el agente ejecuta de punta a punta sin validar supuestos. | `api/executions.py:309-337`, `capabilities.py`, `harness/resume.py` | Encargos ambiguos queman un run completo para descubrir que el enfoque era otro. El costo de un supuesto equivocado es el run entero. |
| **D-A3** | **Iterar = relanzar de cero; toda la maquinaria de iteración está sin UI.** FA-32 (delta re-run) sin consumidor frontend; FA-48/FA-49 (refinamiento encadenado, exploración paralela) con endpoints y cero consumidores; `GET diff` entre ejecuciones sin UI; ABCompare/ReplayPlayer huérfanos; resume H7 solo implícito. Si el output no convence, las opciones reales del operador son: descartar y relanzar completo (pagando contexto + trabajo ya hecho) o editar a mano por fuera. | §1 filas 5-9 | Cada corrección cuesta un run completo en vez de una fracción. La sensación es "o sale a la primera o es caro". |
| **D-A4** | **Las correcciones humanas se pierden.** `discard` no pide causa (`_set_verdict`, `api/executions.py:129-137`); solo `approve` captura memoria (`session_summary`, flag OFF, `post_run_memory.py:169`); el texto correctivo que el operador manda por `send_input` no se persiste como señal (solo log `"operator input queued"`, `codex_cli_runner.py:170-175`); no existe vínculo corrección→prompt del agente. | `api/executions.py`, `post_run_memory.py` | El sistema comete los mismos errores indefinidamente. El conocimiento más valioso del equipo (qué corrige SIEMPRE el humano) se evapora con cada sesión. |
| **D-A5** | **No hay segunda opinión.** El CriticAgent FA-47 existe sin consumidores y sin AC (doc 23 D-P7); `parallel_explore` permite correr 2 modelos sobre el mismo encargo y nadie puede invocarlo; no hay forma de pedir "que otro modelo revise esto" ni de comparar outputs lado a lado. | `api/phase5.py:67`, `api/phase6.py:93`, ABCompare huérfano | La calidad de la revisión depende 100% del ojo del operador en ese momento. Errores que un segundo modelo detectaría en segundos llegan a ADO. |
| **D-A6** | **Sin profundidad por tipo de artefacto.** El schema por agente existe (`api/agents.py:438`) y el validator tiene reglas, pero no se renderizan como checklist de completitud visible en la revisión; los goldens H6 (ejemplos perfectos, ya redactados sin PII) nunca se inyectan como exemplar en el briefing; few-shot solo vive en el path copilot y el operador no lo controla. | §1 filas 12-14 | El agente re-descubre en cada run qué forma debe tener un buen análisis funcional / plan técnico / set de casos; el operador revisa sin una vara objetiva de completitud. |

**Lectura estratégica:** los docs 21/22 hicieron el arnés confiable; el doc 23 lo hace visible. Este plan cierra el triángulo: hace que **el mismo operador, con el mismo flujo, produzca más y mejor por run** — curando el input, cortando temprano los enfoques equivocados, iterando a costo marginal, revisando con ayuda, y dejando que cada corrección mejore el sistema sin trabajo extra. Todo el plan se apoya en sustrato ya construido: es producto sobre maquinaria existente, no maquinaria nueva.

---

## 4. Hoja de ruta

Tres fases priorizadas por **valor-por-esfuerzo**. Complejidad: S ≤ ½ día, M ≤ 2 días, L > 2 días (dev agéntico). Orden recomendado: C0 completo → C1.1 (núcleo del plan) → C1.2, C1.4 → C2.3, C2.1 → C1.3 (cuando U2.2 exista) → C2.2 (último: consume todas las señales).

### FASE C0 — Quick wins: visibilidad y señal sin tocar el flujo

---

#### C0.1 Briefing visible y curable en el launch ("esto va a ver el agente")

- **Ataca:** D-A1.
- **Objetivo:** que el operador vea ANTES de lanzar exactamente qué bloques de contexto va a recibir el agente — con título, origen, tamaño estimado — y pueda destildar los que no aportan. Mejor input = mejor output; control total humano.
- **Diseño:**
  - `context_enrichment.enrich_blocks` gana parámetro aditivo `exclude_ids: frozenset[str] = frozenset()`: cada injector se saltea si su block id está en la lista (ids ya estables: `stacky-memory`, `client-profile`, `ado-epic-structured`, `filesystem-artifacts`, `ado-similar-tickets`, `ado-comments`…). Los `raw_blocks` del operador NUNCA se excluyen. Default vacío = byte-idéntico.
  - Nuevo endpoint `POST /api/agents/briefing-preview` (en `api/agents.py`): body `{agent_type, ticket_id, project, context_blocks}` → llama `enrich_blocks` en dry-run (es pura respecto a los blocks; no crea execution) y devuelve:
    `{blocks: [{id, title, source, chars, tokens_est, priority, locked: bool}], budget: {applied: bool, limit}, cost_estimate}`. `locked=true` para los raw_blocks del operador. `tokens_est` reusa `_block_token_estimate` (F2.4); `cost_estimate` reusa la lógica de FA-33 (`/estimate`) — `dep: V0.5 doc 22 para $ multi-proveedor; degrada mostrando solo tokens`.
  - `POST /api/agents/run` acepta `excluded_block_ids: list[str]` (aditivo); `agent_runner.run_agent` lo recibe y los 3 runtimes lo pasan a `enrich_blocks`. Sello: `metadata["briefing"] = {"excluded": [...], "previewed": true}` (clave nueva).
  - Frontend: en `AgentLaunchModal.tsx`, al seleccionar ticket, sección colapsable "📋 Lo que va a ver el agente" (fetch del preview): lista de bloques con checkbox (default todos ON), tamaño y total de tokens; los `locked` sin checkbox. Lanzar manda los destildados como `excluded_block_ids`.
  - Flag: `STACKY_BRIEFING_PREVIEW_ENABLED` (bool, default **false**) + `FLAG_REGISTRY`; OFF → el modal no llama al preview y el launch no manda exclusiones (byte-idéntico).
- **Criterios de aceptación:** preview de un ticket con épica+similares+memoria lista todos los bloques con tokens; destildar `ado-similar-tickets` → el run NO contiene ese bloque (verificable en `input_context` persistido) y `metadata.briefing.excluded` lo registra; `exclude_ids` vacío → `enrich_blocks` byte-idéntico (test de regresión); el preview no crea ninguna execution ni toca ADO; flag OFF → modal idéntico al actual.
- **Tests (TDD):** `tests/test_briefing_preview.py` — exclusión por injector (cada id), raw_blocks inmunes, dry-run sin efectos, shape del response; extensión de `tests/test_context_budget.py` (exclude + budget conviven).
- **Complejidad:** M.

---

#### C0.2 Verdict con causa (el rechazo deja de ser mudo)

- **Ataca:** D-A4 (primera mitad). Prerrequisito de C2.2.
- **Objetivo:** que descartar un output cueste 2 clicks más y a cambio deje una señal estructurada de POR QUÉ no sirvió.
- **Diseño:**
  - `POST /executions/<id>/discard` acepta body opcional `{reason_kind, reason_text}`. Taxonomía corta y cerrada: `incomplete | wrong_approach | hallucination | bad_format | out_of_scope | other`. `_set_verdict` (`api/executions.py:129`) persiste `metadata["discard_reason"] = {"kind": ..., "text": ...}` (clave nueva; body ausente → comportamiento actual exacto).
  - `POST /executions/<id>/approve` acepta `{note}` opcional → `metadata["approve_note"]` (el "esto estuvo especialmente bien" también es señal).
  - Frontend: al click en Descartar, mini-popover con los 6 kinds (radio) + texto opcional + botón "Descartar sin motivo" (nunca obligar — fricción cero si el operador no quiere).
  - Sin flag (aditivo y opcional por diseño).
- **Criterios de aceptación:** discard con body → metadata poblada y verdict `discarded`; sin body → byte-idéntico al actual; kind inválido → 400 con la lista válida; approve con note → `approve_note` persistida; el popover permite saltearse el motivo en 1 click.
- **Tests:** extensión de los tests de verdict existentes — body válido/ausente/inválido, approve note.
- **Complejidad:** S.

---

#### C0.3 Comparar ejecuciones lado a lado (adoptar ABCompare)

- **Ataca:** D-A3 (primera mitad). Prerrequisito visual de C1.1 y C2.1.
- **Objetivo:** que dos runs del mismo ticket+agente se comparen en pantalla en un click — hoy el endpoint existe y el componente existe, pero no se tocan.
- **Diseño:**
  - Backend: ninguno. `GET /api/executions/<id>/diff/<other_id>` (`api/executions.py:171`) ya valida mismo ticket+agente y devuelve `{left, right}`.
  - Frontend: en `AgentHistoryModal.tsx`, modo selección: tildar 2 ejecuciones → botón "Comparar" → montar `ABCompare` (validar props `executionIds/onPickWinner/onClose` contra `types.ts` y el shape real del diff endpoint — regla 8 del doc 23: huérfano no se reusa sin validar contrato + test vitest). `onPickWinner` → `POST approve` del ganador (con confirm) y `metadata["ab_winner"]=true` vía el mismo approve (param opcional `ab_winner: true` en el body, aditivo).
  - `ReplayPlayer` queda explícitamente FUERA de este ítem (nota: adoptarlo solo si la comparación demuestra demanda de "ver cómo llegó hasta ahí"; evita revivir dos huérfanos en un PR).
  - Sin flag (UI aditiva read-only salvo el approve explícito).
- **Criterios de aceptación:** seleccionar 2 runs del mismo ticket+agente → vista lado a lado con ambos outputs; runs de distinto agente → el botón Comparar deshabilitado (el endpoint daría 400); elegir ganador dispara approve normal + marca; cerrar sin elegir no persiste nada.
- **Tests:** vitest `components/__tests__/ABCompare.test.tsx` (render con fixture del diff endpoint, pick winner, cierre limpio); test backend del param `ab_winner` en approve.
- **Complejidad:** S/M.

---

### FASE C1 — Estructurales: iteración barata y control fino

---

#### C1.1 Iterar con feedback (refine sin relanzar) — el núcleo del plan

- **Ataca:** D-A3 (cierre). Reusa H7 resume + FA-32 delta + guard/slots V0.2-V0.3 (ya en código).
- **Objetivo:** que "no me convence, ajustá esto" cueste una fracción de un relanzamiento: el operador escribe la corrección y el agente continúa SOBRE la misma sesión, con todo el contexto ya pagado. Cada iteración queda vinculada, comparable y con costo visible.
- **Diseño:**
  - Nuevo `backend/services/run_refine.py`:
    ```python
    def refine(*, execution_id: int, feedback: str, user: str) -> int:
        # 1. valida: execution terminal (completed | needs_review) y con runtime conocido
        # 2. crea NUEVA execution (hija) mismo ticket/agente/proyecto/runtime con:
        #    context_blocks = [bloque "operator_feedback" con el texto]   (señal para C2.2)
        #    excluded_block_ids = TODOS los ids de enrichment (reusa C0.1):
        #      en resume la sesión YA tiene el contexto; re-inyectarlo duplica tokens
        #    metadata: refined_from=<padre>, iteration=<n_padre+1>, refine_transport=...
        # 3. transporte por runtime (vía capabilities, sin if-runtime dispersos):
        #    supports_resume (claude/codex) → harness.resume.resolve(execution_id=padre)
        #      y el prompt del run = feedback + recordatorio corto de contrato
        #    github_copilot (sin resume) → path FA-32: previous_execution_id=padre
        #      (delta_prompt ya construye prefix con el output previo); transport="delta"
        # 4. pasa por run_guard (V0.2) y run_slots (V0.3) como cualquier launch
    ```
  - Endpoint: `POST /api/executions/<id>/refine` body `{feedback: str}` → `202 {execution_id}` (la hija). Errores: 409 si la origen no está terminal o hay run activo (guard), 400 sin feedback.
  - El bloque `operator_feedback` se persiste en `input_context` de la hija — ES la señal estructurada de corrección (D-A4) sin trabajo extra del operador.
  - Frontend: botón "🔁 Iterar con feedback" + textarea en el panel de detalle de ejecución (U0.1 doc 23; `degradado: en AgentHistoryModal` mientras U0.1 no exista). Cadena de iteraciones visible (1 → 2 → 3) con costo por iteración (telemetría existente) y chip "esta iteración: $X vs relanzar: ~$Y" (Y = costo del padre); link "ver diff con la anterior" → C0.3.
  - Flag: `STACKY_REFINE_ENABLED` (bool, default **false**) + `FLAG_REGISTRY`; OFF → endpoint 404 feature-gated.
- **Criterios de aceptación:** refine sobre run claude `completed` → hija con `refined_from` correcto, sesión reanudada (misma `session_id` de metadata del padre resuelta por `harness.resume.resolve`) y SOLO el bloque de feedback como contexto nuevo; refine sobre copilot → hija con `previous_execution_id` y prefix delta (transport `delta`); refine sobre run `running` → 409; cadena de 3 iteraciones navegable con costos individuales; flag OFF → 404; guard V0.2 aplica (no se puede refinar si ya hay una hija corriendo).
- **Tests (TDD, `tests/test_run_refine.py`):** mock de runners — hija vinculada e iteración incrementada; resolución de resume con `execution_id` explícito; path copilot→delta; bloque operator_feedback persistido; terminal-only; flag OFF; integración con guard.
- **Complejidad:** M/L (partible: PR1 servicio+endpoint+claude/codex, PR2 copilot delta + UI cadena).
- **Dependencias:** C0.1 (mecanismo `excluded_block_ids` — si no está, el refine re-inyecta enrichment: funciona pero gasta tokens de más; declararlo como degradado aceptable), C0.3 (diff visual, opcional).

---

#### C1.2 Modo plan-first (checkpoint humano antes de ejecutar)

- **Ataca:** D-A2. Depende de C1.1 (duro: el "continuar" ES un refine).
- **Objetivo:** que para encargos grandes/ambiguos el agente produzca primero un plan corto — qué va a crear, qué supuestos toma, qué preguntas tiene — y ESPERE la aprobación o el ajuste del operador antes de ejecutar. El costo de un supuesto equivocado baja de "un run entero" a "un plan de 1-2 minutos".
- **Diseño:**
  - Flags: `STACKY_PLAN_FIRST_AGENTS` (str CSV de agent_types, default `""` = ninguno) + `FLAG_REGISTRY`. Sin flag global ON/OFF aparte: lista vacía = feature apagada (mismo patrón `*_PROJECTS` del registry). El modal de launch muestra además un toggle "Plan primero" por-run (opt-in puntual aunque el agent_type no esté en la lista; el flag por agente solo pre-tilda).
  - Lanzamiento en modo plan: `run_agent` recibe `plan_first: bool = False` (aditivo). Si ON, se antepone al prompt del run una instrucción fija (constante en `harness/run_contract.py`, junto a las reglas existentes): *"PASO PREVIO OBLIGATORIO: producí ÚNICAMENTE un plan corto en `plan.md`: (1) artefactos que vas a crear, (2) supuestos que estás tomando, (3) preguntas abiertas. NO crees ningún otro artefacto. Terminá después del plan."*
  - Cierre del run-plan: en `harness/post_run.py::finalize_run`, si `metadata["plan_gate"]` está armado (lo sella el runner cuando `plan_first=True`) → status `needs_review` con `metadata["plan_gate"] = {"stage": "plan_pending"}`. NO se inventa un status nuevo (consistente con contract gate y self-review U1.2 que ya usan `needs_review`); NO se publica nada a ADO (el plan no es un artefacto publicable).
  - Revisión del plan: el operador lo ve (panel U0.1 / bandeja U1.1; `degradado: AgentHistoryModal` + output-files) y tiene 3 acciones:
    - **Aprobar y ejecutar** → `refine(execution_id, feedback="Plan aprobado. Ejecutá exactamente lo planificado.")` — resume preserva todo el contexto del plan.
    - **Ajustar** → refine con las correcciones del operador al plan.
    - **Descartar** → C0.2 con causa.
  - Explícitamente NO se revive el esqueleto `waiting_for_question`/`answer_question` (WS2): bloquear un thread esperando respuesta no aplica a runners CLI por subproceso. El checkpoint es ENTRE runs vía resume — más simple, sin estado colgado, sin timeout. Dejar comentario en `api/executions.py:309` apuntando a este diseño.
- **Criterios de aceptación:** run con plan-first ON termina en `needs_review` con `plan_gate` y `plan.md` como único artefacto; "Aprobar y ejecutar" lanza refine que produce los artefactos reales con la sesión preservada; copilot (sin resume) usa el path delta de C1.1 con el plan como output previo; agent_type fuera de la lista y toggle OFF → byte-idéntico al actual; el run-plan nunca publica a ADO.
- **Tests (TDD, `tests/test_plan_first.py`):** instrucción anteponida solo con flag/toggle; finalize → needs_review + plan_gate; aprobación dispara refine con el feedback fijo; sin flag byte-idéntico.
- **Complejidad:** M.
- **Dependencias:** C1.1 (duro). U1.1/U0.1 del doc 23 (UI ideal; degradado declarado).

---

#### C1.3 Edición inline antes de publicar + captura del delta humano — EXTIENDE U2.2 (doc 23)

- **Ataca:** D-A4 (la señal de mayor calidad). Incremental sobre U2.2 — NO re-propone el preview pre-publicación.
- **Objetivo:** que el operador corrija detalles del artefacto en la UI sin relanzar nada (typo, una sección floja, un criterio mal redactado), publique la versión corregida, y el sistema capture el diff humano como señal estructurada — el "qué le faltó al agente" perfecto.
- **Diseño:**
  - **Requiere U2.2 implementado** (publish_hold + preview + publish real). Sobre ese preview: botón "✏️ Editar" → editor del `comment.html` (mismo saneado/sandbox que U2.2 ya define; texto plano para campos no-HTML). Al guardar: el hold pasa a contener `edited_html`; "Publicar a ADO" publica la versión editada por el path real de U2.2 (outbox incluido).
  - Captura: `metadata["human_delta"] = {"diff": unified_diff(original, edited)[:N], "chars_changed": n, "edited_at": iso}` (clave nueva; `difflib`, truncado a tamaño razonable). El original NUNCA se pierde (queda en `output` de la execution; el editado solo vive en el hold y en lo publicado).
  - **Modo degradado sin U2.2 (declarado):** no existe edición pre-publicación porque la publicación es automática (`close_execution_with_publish`). La captura de delta humano se limita a las señales de C0.2 (discard reasons) y C1.1 (operator_feedback). Este ítem NO construye un mecanismo de hold paralelo — esperar a U2.2 es más barato que duplicarlo.
  - Sin flag propio: hereda el gate de U2.2 (`publish_mode: review` por proyecto).
- **Criterios de aceptación:** editar y publicar → ADO recibe la versión editada, la execution conserva el output original y `human_delta` registra el diff; publicar sin editar → sin `human_delta` (no señal vacía); descartar el hold editado no publica nada; el diff nunca incluye el HTML completo (solo el unified diff truncado).
- **Tests (TDD, `tests/test_inline_edit_delta.py`):** hold editado publica versión editada; human_delta correcto; original intacto; extensión de los tests de U2.2.
- **Complejidad:** M (sobre U2.2 existente).
- **Dependencias:** U2.2 (doc 23) — **dura para la edición**; degradado = ítem pospuesto, no bloquea el resto del plan.

---

#### C1.4 Segunda opinión bajo demanda (crítica cruzada con árbitro humano) — EXTIENDE U1.2 (doc 23), da dueño a FA-47

- **Ataca:** D-A5. Incremental sobre U1.2 — NO re-propone el self-review automático.
- **Frontera con U1.2 (declarada):** U1.2 = revisión AUTOMÁTICA contra AC dentro del pipeline de publicación (modos off/annotate/gate, mismo flujo). C1.4 = revisión BAJO DEMANDA, disparada por el operador, hecha por OTRO modelo/runtime (cross-model), cuyo resultado el humano arbitra hallazgo por hallazgo y alimenta la iteración (C1.1). Comparten una sola pieza: el fetch de acceptance criteria (helper de U1.2 si existe; `degradado: crítica sin AC, como FA-47 hoy`).
- **Objetivo:** botón "Pedir crítica": otro modelo revisa el artefacto y anota hallazgos concretos; el operador decide cuáles valen y los convierte en feedback de refine en un click. Nunca automático, nunca bloquea nada.
- **Diseño:**
  - Nuevo `POST /api/executions/<id>/critique-v2` (en `api/executions.py`; v2 para no romper el FA-47 de `api/phase5.py`, que queda deprecado con comentario): body `{model?: str}`. Reusa `agents/critic.py` con dos cambios aditivos: (a) si U1.2 está mergeado, incluye los AC del ticket en el prompt de crítica; (b) el modelo default es DISTINTO al que produjo el artefacto (leído de metadata; si coinciden, el router elige el alternativo barato; clamp existente aplica solo). Output estructurado: `[{finding, severity: high|medium|low, suggestion}]` parseado estricto → `metadata["critique"] = {"model": ..., "findings": [...], "requested_at": ...}`. Error de parse → 502 con detalle (bajo demanda: el error se muestra, no se traga).
  - Arbitraje en UI (panel U0.1; `degradado: AgentHistoryModal`): cada hallazgo con botones **Aceptar** / **Rechazar**. Los aceptados se acumulan en un textarea pre-armado de feedback → botón "Iterar con esto" → C1.1 refine. Los rechazados → `findings[i].dismissed=true` (señal de falsos positivos del crítico para C2.2).
  - Costo visible antes de pedir: estimación FA-33 en el botón ("~$0.05").
  - Flag: `STACKY_CRITIQUE_ENABLED` (bool, default **false**) + `FLAG_REGISTRY`.
- **Criterios de aceptación:** crítica sobre run claude/sonnet usa otro modelo y lo registra; hallazgos visibles con severidad; aceptar 2 de 5 → refine arranca con SOLO esos 2 en el feedback; rechazar persiste `dismissed`; flag OFF → 404; FA-47 viejo sigue respondiendo igual (compat).
- **Tests (TDD, `tests/test_critique_v2.py`):** mock LLM — parse estricto, modelo cruzado, con/sin AC, dismissed, flag OFF.
- **Complejidad:** M.
- **Dependencias:** C1.1 (para "Iterar con esto"; degradado: copiar el feedback a mano), U1.2 (solo el helper de AC; degradado declarado).

---

### FASE C2 — Diferenciales: el sistema aprende del humano (sin pedirle nada)

---

#### C2.1 Duelo A/B de modelos/runtimes bajo demanda — da dueño a FA-49 + ABCompare

- **Ataca:** D-A5/D-A3 (lado comparación). Reusa `parallel_explore` (backend completo) + C0.3 (UI de comparación).
- **Objetivo:** para encargos importantes, el operador lanza el MISMO encargo con 2 variantes (modelo y/o runtime) y elige el mejor lado a lado. Decisión humana, datos reales, y de paso señal de routing.
- **Diseño:**
  - Frontend: en el modal de launch, opt-in "⚔ Duelo A/B" (visible solo con flag ON): selector de la segunda variante (modelo/runtime) + estimación de costo doble (FA-33) + confirm explícito ("esto lanza 2 runs: ~$X"). Llama al endpoint FA-49 existente (`api/phase6.py:93`) con cap duro de 2 variantes.
  - Interacción con el guard V0.2 (verificar al implementar): `parallel_explore` lanza N runs del mismo ticket+agente → el segundo chocaría con el guard. Ajuste mínimo y aditivo: `parallel_explore` marca `metadata["ab_group"] = <uuid>` y pasa `force=true` interno SOLO para los miembros del grupo (decisión consciente del operador ya confirmada en el modal — el guard sigue protegiendo los launches normales).
  - Al terminar ambos: notificación (U0.4 doc 23 si existe; `degradado: el operador los ve en el historial`) → C0.3 ABCompare con `onPickWinner` → ganador `approved` + `metadata["ab_winner"]`, perdedor `discarded` + `discard_reason={"kind":"ab_loser"}` (C0.2). El perdedor NUNCA se publica a ADO (si el proyecto publica automático, el duelo exige `publish_mode: review` de U2.2 o lo limita a agentes sin publicación automática — verificar al implementar y documentar la restricción en el modal).
  - Señal: la marca `ab_winner` queda disponible para el advisor V1.2 (doc 22) — `degradado: solo se persiste; el advisor la consumirá cuando exista. NO se implementa routing acá`.
  - Flag: `STACKY_AB_DUEL_ENABLED` (bool, default **false**) + `FLAG_REGISTRY`.
- **Criterios de aceptación:** duelo lanza exactamente 2 runs con el mismo `input_context` y `ab_group` compartido; el confirm muestra costo estimado doble; elegir ganador aplica los dos verdicts; cancelar el duelo a mitad cancela ambos (flujo cancel existente); flag OFF → sin opción en el modal; doble publicación a ADO imposible (restricción verificada por test).
- **Tests (TDD, `tests/test_ab_duel.py`):** 2 runs mismo contexto, ab_group, verdicts del pick, interacción con guard (force solo intra-grupo), no-publicación del perdedor.
- **Complejidad:** M.
- **Dependencias:** C0.3 (duro), C0.2 (kind `ab_loser`), U2.2/V1.2 opcionales (degradados declarados).

---

#### C2.2 Flywheel de correcciones humanas (aprendizaje invisible)

- **Ataca:** D-A4 (cierre). Consume TODAS las señales de C0.2/C1.1/C1.3/C1.4/C2.1. Cruza con V1.1/V2.3 (doc 22) sin re-proponerlos.
- **Objetivo:** el operador trabaja normal; el sistema convierte sus correcciones en propuestas concretas de mejora — memoria, prompts, goldens — que el humano aprueba cuando quiere. "Trabajo invisible, resultados que se notan."
- **Diseño:**
  - Nuevo `backend/services/operator_signals.py`:
    ```python
    def collect(*, agent_type: str | None, project: str | None, days: int = 30) -> list[Signal]
    # Signal = {kind: discard_reason|operator_feedback|human_delta|critique_arbitration|ab_result,
    #           execution_id, agent_type, project, payload, at}
    # Lee SOLO metadata/input_context ya persistidos por C0.2/C1.1/C1.3/C1.4/C2.1 — no captura nada nuevo.
    def summarize(signals) -> dict   # agrupa por agent_type + kind + similitud simple (mismo reason_kind / keywords compartidas)
    ```
  - Endpoint: `GET /api/operator-signals/summary?agent_type=X&days=30` → grupos con conteo y ejemplos. Página/sección "Mejora continua" (en Diagnóstico o MemoryPage) que muestra: "Para `functional`: 4 descartes por `incomplete` en 30 días; 3 refines pidiendo 'incluir casos de error'".
  - Destinos (TODOS con aprobación humana explícita; nada se auto-aplica):
    - **(a) Candidatos a memoria colaborativa:** grupo recurrente (≥`STACKY_SIGNALS_MIN_COUNT`, default 3) → botón "Proponer como memoria" → `memory_store` con status de moderación pendiente (la pantalla de moderación de memoria Fase A ya existe — `MemoryPage`). Respeta la allowlist de types de V1.5/B5 (`dep: V1.5 doc 22; degradado: type session_summary actual`).
    - **(b) Propuestas de mejora del prompt del agente:** para un grupo recurrente, botón "Sugerir mejora de prompt" → UNA llamada LLM (modelo barato; clamp aplica) con el `.agent.md` actual + las correcciones del grupo → devuelve una sugerencia de cambio puntual presentada como diff contra el prompt actual (`dep: V1.1 doc 22 para el diff de versiones y el historial; degradado: sugerencia en texto plano`). El operador la aplica editando/importando el `.agent.md` por el flujo normal de import — que ya versiona (V1.1) y pasa el eval gate (H6). **El sistema JAMÁS escribe el `.agent.md` solo.**
    - **(c) Candidatos a golden:** execution `approved` que es la iteración final de una cadena de refine exitosa, o ganadora de un duelo → `metadata["golden_candidate"]=true` + aparece en la sección con botón que LINKEA al promote-to-golden de V2.3 (doc 22) (`degradado sin V2.3: la marca queda persistida y lista`). NO se re-implementa promote ni harvest.
  - Flags: `STACKY_OPERATOR_SIGNALS_ENABLED` (bool, default **false**) + `STACKY_SIGNALS_MIN_COUNT` (int, default 3) + `FLAG_REGISTRY`.
- **Criterios de aceptación:** con señales sintéticas (2 discards `incomplete` + 1 refine con keywords compartidas para `functional`) el summary los agrupa; "Proponer como memoria" crea entrada PENDIENTE de moderación (nunca activa directa); la sugerencia de prompt se genera solo bajo demanda y produce diff/texto sin tocar el archivo; un grupo bajo el mínimo no genera botones; flag OFF → endpoint 404 y cero secciones en UI; ninguna escritura a memoria/prompt/golden ocurre sin click humano (test que lo verifique explícitamente).
- **Tests (TDD, `tests/test_operator_signals.py`):** collect lee las 5 fuentes desde fixtures de metadata; agrupación; mínimo; propuesta de memoria pendiente; mock LLM para sugerencia de prompt; flag OFF.
- **Complejidad:** L.
- **Dependencias:** C0.2 (duro — sin causas no hay señal), C1.1 (fuerte), C1.3/C1.4/C2.1 (suman fuentes, no bloquean), V1.1/V2.3/V1.5 doc 22 (degradados declarados).

---

#### C2.3 Profundidad por tipo de artefacto (exemplar dorado + checklist de completitud)

- **Ataca:** D-A6. Reusa goldens H6, schema por agente y `artifact_validator`.
- **Objetivo:** que el agente reciba en el briefing un ejemplo perfecto del tipo de artefacto que debe producir, y que el operador revise contra una checklist objetiva de completitud por tipo — sin escribir ni el ejemplo ni la checklist a mano.
- **Diseño:**
  - **(a) Exemplar dorado en el briefing (extiende C0.1):** el preview gana un bloque opcional `golden-exemplar` (default **destildado** — opt-in por run): toma el golden más reciente de `backend/evals/agents/<agent_type>/` (ya redactados sin PII por harvest H6), truncado al budget F2.4. Nuevo injector `_inject_golden_exemplar` en `context_enrichment.py` (mismo patrón que los existentes), gateado por `STACKY_GOLDEN_EXEMPLAR_ENABLED` (bool, default **false**) Y por la selección del operador en el preview (`included_optional_ids` aditivo en el payload, espejo de `excluded_block_ids`). Sin goldens para el agent_type → el bloque no aparece (nunca placeholder vacío).
  - **(b) Checklist de completitud por tipo:** nuevo `backend/services/artifact_checklist.py`: `get_checklist(agent_type) -> list[{item, source}]` — deriva ítems de (1) el schema del agente (`GET /api/agents/<agent_type>/schema` ya existe — campos requeridos → "debe incluir X"), (2) reglas del `artifact_validator` aplicables al kind, (3) ítems custom por proyecto+agent_type (tabla simple nueva `artifact_checklist_items` o entrada en el storage de config por proyecto existente — decidir al implementar por lo que menos migración requiera; add-only). `evaluate(agent_type, artifact_text) -> list[{item, met: bool|None}]` — `met` solo cuando el validator puede decidirlo mecánicamente; `None` = "a criterio del operador" (NUNCA inventar un veredicto con LLM acá: esta checklist es mecánica y barata; el juicio profundo es U1.2/C1.4).
  - Visibilidad: (1) en el briefing, la checklist viaja como bloque `completeness-checklist` ("tu artefacto debe incluir: …") — mismo gate que (a) con flag propio `STACKY_ARTIFACT_CHECKLIST_ENABLED` (default **false**); (2) en la revisión (panel U0.1; `degradado: AgentHistoryModal`), la checklist se muestra con ✓/✗/— calculados por `evaluate` — el operador ve completitud de un vistazo sin leer todo el artefacto.
- **Criterios de aceptación:** agente con golden → bloque exemplar disponible en el preview, destildado por default, y solo viaja si el operador lo tilda; sin goldens → bloque ausente; checklist de `functional` deriva del schema real (test con el schema actual) + ítems custom del proyecto; `evaluate` marca `met=None` para ítems no mecanizables; flags OFF → byte-idéntico; la checklist en revisión no rompe con artefactos viejos/vacíos.
- **Tests (TDD, `tests/test_artifact_checklist.py` + `tests/test_golden_exemplar_injection.py`):** derivación desde schema, custom items, evaluate mecánico vs None, injector con/sin goldens, opt-in del operador.
- **Complejidad:** M.
- **Dependencias:** C0.1 (duro para la parte briefing — los bloques opcionales viven en su preview), U0.1 doc 23 (UI ideal de revisión; degradado declarado).

---

## 5. Priorización y secuencia

| Orden | Ítem | Complejidad | Valor | Riesgo | Dependencias |
|---|---|---|---|---|---|
| 1 | C0.2 Verdict con causa | S | Alto (habilita el flywheel) | Bajo (aditivo) | — |
| 2 | C0.3 Adoptar ABCompare | S/M | Alto | Bajo (UI sobre endpoint existente) | — |
| 3 | C0.1 Briefing visible y curable | M | Muy alto (mejor input, control total) | Bajo (param aditivo + flag OFF) | — |
| 4 | C1.1 Refine sin relanzar | M/L | **Muy alto (núcleo del plan)** | Medio (toca launch path → flag OFF) | C0.1 suave, V0.2/V0.3 ya en código |
| 5 | C1.2 Plan-first | M | Muy alto (mata el run quemado por supuesto) | Bajo (instrucción + needs_review existente) | C1.1 dura |
| 6 | C1.4 Crítica cruzada con árbitro | M | Alto | Bajo (bajo demanda, flag OFF) | C1.1 suave, U1.2 suave |
| 7 | C2.3 Exemplar + checklist por tipo | M | Alto | Bajo | C0.1 dura |
| 8 | C2.1 Duelo A/B | M | Medio/alto | Medio (interacción guard + publicación) | C0.3 dura, C0.2 |
| 9 | C1.3 Edición inline + delta humano | M | Alto (la mejor señal) | Bajo (sobre U2.2) | **U2.2 doc 23 dura** |
| 10 | C2.2 Flywheel de correcciones | L | Muy alto (compuesto en el tiempo) | Bajo (solo propone, nunca aplica) | C0.2 dura, C1.1 fuerte, resto suma |

**Reglas de implementación (las 7 del doc 22 + las 3 de frontend del doc 23 aplican íntegras a todos los ítems):** TDD; validar por archivo de test (suite contaminada); flag nuevo = `config.py` + `FLAG_REGISTRY` + preset V0.1 cuando corresponda, mismo PR; metadata solo claves nuevas (las de este plan: `briefing`, `discard_reason`, `approve_note`, `ab_winner`, `ab_group`, `refined_from`, `iteration`, `refine_transport`, `plan_gate`, `human_delta`, `critique`, `golden_candidate`); default OFF/0 (retro-compat byte-idéntica); ADO solo vía `ado_write_outbox`; sin fallback silencioso entre runtimes; ningún huérfano se reusa sin validar props contra `types.ts` + test vitest; CSS modules + react-query + cero deps npm nuevas; UI degrada con gracia ante metadata ausente.

**Regla 11 (propia de este plan, innegociable):** ninguna acción se ejecuta sin gesto explícito del operador y ningún aprendizaje modifica prompts/memoria/goldens sin aprobación humana. Si un ítem puede interpretarse como "el sistema decidió solo", está mal implementado.

---

## 6. Qué va a notar cada audiencia (antes → después)

### Operador (quien lanza, supervisa, revisa y publica — el centauro)
- **Hoy:** elige ticket y runtime, escribe (o no) un mensaje, lanza a ciegas: no sabe qué contexto recibió el agente. Si el output no convence: relanzar de cero y pagar todo de nuevo, o corregir a mano por fuera. Su criterio (por qué descartó, qué corrigió) se evapora.
- **Post-C0:** antes de lanzar ve "esto va a ver el agente" y destila el briefing en segundos; al descartar deja la causa en 2 clicks; compara dos runs lado a lado en un click.
- **Post-C1:** "no me convence" se resuelve escribiendo la corrección y apretando Iterar — el agente continúa con todo el contexto ya pagado, a una fracción del costo, con diff contra la versión anterior. Para encargos grandes activa Plan-first: aprueba o ajusta el plan en 2 minutos antes de que el agente queme un run entero. Ante la duda, pide crítica de otro modelo y arbitra hallazgo por hallazgo.
- **Post-C2:** lanza duelos A/B para los encargos importantes y elige con evidencia; corrige detalles inline antes de publicar; y una sección de "Mejora continua" le propone — derivado de SUS correcciones — memorias, mejoras de prompt y goldens que aprueba cuando quiere. Trabaja igual que siempre; rinde varias veces más por run.

### Equipo / quien vive en ADO
- **Hoy:** recibe el primer intento del agente, con la calidad que haya salido.
- **Después:** recibe la iteración que el operador aprobó — pulida con refine, validada contra checklist de completitud, con crítica cruzada cuando hizo falta y editada inline en los detalles. Menos idas y vueltas en comentarios; los artefactos llegan más completos y más consistentes entre sí (mismo exemplar dorado como vara).

### Management
- **Hoy:** el costo de calidad es invisible: outputs descartados, relanzamientos completos, tiempo de revisión sin medida.
- **Después:** métricas nuevas y defendibles: costo marginal por iteración vs relanzamiento (ahorro directo y medible por C1.1), tasa de descartes con causa (dónde duele cada agente), planes frenados a tiempo (runs grandes salvados por C1.2), y un flywheel auditable: cuántas correcciones humanas se convirtieron en mejoras aprobadas de prompts/memoria/goldens. El digest U1.5 (doc 23) puede incorporar estos agregados sin trabajo extra.

---

## 7. Ventaja competitiva: por qué el centauro con Stacky aplasta al mismo operador con un CLI suelto

1. **El briefing se acumula; la terminal olvida.** Con un CLI suelto, el contexto (épica, artefactos previos, tickets similares, perfil del cliente, memoria del equipo, ejemplo dorado) se re-escribe a mano en cada sesión y muere al cerrarla. Stacky lo ensambla solo en cada run (sustrato ya construido) y con C0.1/C2.3 el operador lo CURA en segundos en vez de redactarlo en minutos — y la curaduría misma queda registrada.
2. **Iterar cuesta una fracción, no un run.** En un CLI suelto, "ajustá esto" = nueva sesión pagando todo el contexto de nuevo, o una conversación eterna sin estructura. Con C1.1/C1.2 cada corrección continúa la sesión real (resume H7), queda vinculada, comparable (diff) y costeada — y el plan-first corta los enfoques equivocados cuando valen centavos, no dólares.
3. **Cada corrección humana mejora el sistema; el CLI las tira.** El operador que descarta con causa, refina con feedback, edita inline y arbitra críticas está — sin saberlo — entrenando a Stacky: C2.2 convierte esas señales en propuestas de memoria, prompts y goldens que se aprueban con un click y quedan para SIEMPRE (versionadas V1.1, evaluadas H6, inyectadas en cada run futuro). Un CLI suelto olvida la corrección al cerrar la terminal; Stacky la convierte en activo del equipo. Ese interés compuesto es imposible de replicar a mano — y el humano firma cada paso.

---

## 8. Métricas de éxito del plan

| Métrica | Hoy | Objetivo |
|---|---|---|
| Control del operador sobre el contexto del run | 1 textarea opcional | briefing completo visible y curable (C0.1) |
| Costo de una corrección sobre un output | 1 run completo | fracción medible (iteración refine, C1.1) y visible por chip |
| Runs grandes quemados por un supuesto equivocado | costo total del run | costo de un plan de 1-2 min (C1.2) |
| Descartes con causa estructurada | 0% | >80% de los descartes (C0.2, sin obligar) |
| Forma de pedir segunda opinión / comparar modelos | no existe | 1 click (C1.4 crítica, C2.1 duelo, C0.3 diff) |
| Correcciones humanas convertidas en mejoras persistentes | 0 (se evaporan) | propuestas aprobadas/mes visibles en "Mejora continua" (C2.2) |
| Artefactos producidos con exemplar + checklist por tipo | 0% | opt-in disponible para todo agent_type con golden (C2.3) |
