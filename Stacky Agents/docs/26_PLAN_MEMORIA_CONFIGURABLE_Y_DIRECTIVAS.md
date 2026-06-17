# 26 — Plan Memoria Configurable y Directivas del Operador: de la observación recordada a la regla obligatoria

**Fecha:** 2026-06-13
**Estado:** propuesto (ningún ítem implementado)
**Predecesores:** `docs/21_PLAN_HARDENING_ARNES_MULTI_PROVEEDOR.md` (H0-H8, implementado salvo H2.5), `docs/22_PLAN_ARNES_VENTAJA_COMPETITIVA.md` (V0 implementado; V1-V2 propuestos), `docs/23_PLAN_CAPA_PERCEPTIBLE_VALOR_VISIBLE.md` (U0-U2, propuesto), `docs/24_PLAN_CAPA_AMPLIFICACION_OPERADOR.md` (C0-C2, propuesto) y el **plan de memoria colaborativa v2** (`docs/plans/plan-memoria-colaborativa-stacky-agents-2026-06-06-v2.md`, Fase A-E parcial implementada) + su manual (`docs/memoria-colaborativa-manual.md`).
**Audiencia:** dev agéntico junior. Cada ítem es autocontenido: objetivo, evidencia, diseño con archivos exactos, criterios de aceptación, tests TDD y complejidad.

**Tesis (innegociable):** la memoria de hoy es **observacional y probabilística**: se recupera por relevancia léxica (TF-IDF, `memory_store.search`) y puede no aparecer si no hay overlap con el ticket, o ser suprimida por conflicto/cap. Eso sirve para "lo que el equipo aprendió", pero NO para "esto se hace SIEMPRE así". Este plan agrega dos cosas que el operador hoy no tiene: (1) **directivas obligatorias targeteadas** — reglas que el operador escribe ("para tareas del proceso X, el agente DEBE hacerlo así") y que se inyectan SIEMPRE que el run matchee el targeting, bypasseando el scoring; y (2) **configuración 100% desde la UI** de toda la maquinaria de memoria que hoy vive hardcodeada o solo en flags genéricos (caps por agente, allowlist por proyecto, scopes/types, edición de contenido). Todo con gobernanza humana: el operador autora y firma cada directiva; nada se auto-genera ni se auto-activa.

**Relación con los docs 22/23/24 (frontera de no-solapamiento):**
- El doc 22 ataca la capa *interna* del arnés; el doc 23 la *perceptible*; el doc 24 la de *amplificación* del operador en el flujo lanzar→supervisar→revisar→publicar.
- Este plan ataca la capa de **gobierno de la memoria**: hacerla configurable y darle un tipo nuevo de primera clase (la directiva imperativa).
- **Frontera dura con el doc 24** (declarada, NO se duplica):
  - El doc 24 **C0.1** propone el "briefing visible y curable" con `POST /api/agents/briefing-preview` y `excluded_block_ids`. Este plan **NO re-implementa** briefing-preview: lo **extiende** declarando que las directivas `enforcement=always` aparecen en ese preview como un sub-bloque **locked** (no excluible) dentro del bloque `stacky-memory` (M2.2).
  - El doc 24 **C2.2** propone el "flywheel" que **"Propone como memoria"** candidatos derivados de correcciones humanas (status de moderación pendiente, respeta la allowlist de types V1.5/B5). Este plan **NO re-implementa** el flywheel: declara que el flywheel puede proponer también **directivas** (type `directive`, `enforcement=suggest` por default — una directiva propuesta por la máquina NUNCA nace `always`; ver M3.3).
- Ningún ítem de este plan bloquea en 22/23/24: todos declaran modo degradado.

> **Nota de numeración:** el ítem V2.1 del doc 22 referenciaba un futuro checklist de nuevo runtime; el doc 24 lo asignó a `docs/25_CHECKLIST_NUEVO_RUNTIME.md`, que **ya existe**. El usuario llama coloquialmente "plan 25" a este documento, pero como el 25 está tomado se materializa como **doc 26** (igual que 23/24 corrieron su numeración). El plan de mejoras invisibles del motor es el **doc 27**.

---

## 1. Punto de partida: el sustrato de memoria que YA existe (no re-implementar)

Verificado contra el código el 2026-06-13 en `codex/subida-cambios-pendientes`. Esta tabla es el hallazgo central: la maquinaria de almacenamiento, búsqueda, inyección, moderación y doble-canal ya está construida; lo que falta es **configurabilidad** y la **semántica imperativa**.

| Sustrato | Dónde vive (file:line) | Estado |
|---|---|---|
| Modelo de observación append-friendly (con `topic_key`, `revision_count`, `confidence`, `tags_json`, `review_after`, `expires_at`, `scope`, `source_agent_type`, `author_email`) | `services/memory_store.py:128` (`StackyMemoryObservation`) | OK — campos `review_after`/`expires_at` existen pero **nadie los puebla ni los respeta** (D-M5) |
| Relaciones entre memorias (supersedes/conflicts_with/not_conflict/…) | `services/memory_store.py:199` (`StackyMemoryRelation`), `mark_relation:472`, `resolve_conflicts_between:528` | OK |
| Estados del ciclo de vida; solo `active` se inyecta | `services/memory_store.py:64` (`INJECTABLE_STATUSES`), `:65` (`ALL_STATUSES`), `set_status:455` | OK |
| Scopes inyectables (project/team/global; personal/private excluidos de la inyección auto) | `services/memory_store.py:77` (`INJECT_SCOPES`) | OK |
| Upsert por `topic_key` con `revision_count` y guarda anti-degradación (un draft no pisa un active) | `services/memory_store.py:363` (`upsert_by_topic_key`), guarda `:401` | OK |
| Búsqueda TF-IDF (mismo tokenizer que `services/embeddings.py`, SIN FTS5); ranking 2 etapas (coseno + señales 0..1) | `services/memory_store.py:677` (`search`), composite `:774` | OK |
| Recuperación para un run: candidatos → filtro B5 → supresión por conflicto → caps; **redacta PII irreversible antes de medir/renderizar** | `services/memory_store.py:858` (`get_context_for_run`), supresión `_apply_conflict_suppression:786`, redacción `:912` | OK |
| **Caps por agente HARDCODEADOS** (max_memorias, max_chars) | `services/memory_store.py:107` (`_AGENT_CAPS`), `:117` (`_DEFAULT_CAP`), `_caps_for:120` | OK pero **no configurable** (D-M1) |
| Doble-canal B5/V1.5: tipos reservados al SYSTEM prompt (FA-*) — fuente única de verdad | `services/memory_store.py:84` (`_SYSTEM_PROMPT_TYPES`), `:92` (`RESERVED_TYPES`), filtro de inyección `:894` | OK |
| `POST /api/memory` **rechaza** los tipos reservados (400) para no doble-inyectar | `api/memory.py:43` | OK |
| API de memoria: crear, listar, buscar, `context-preview` (solo bloque `stacky-memory`), `set_status`, relaciones, conflict-graph, validation, sync git | `api/memory.py` (create `:31`, list `:17`, search `:70`, context-preview `:86`, status `:268`, relations `:279`) | OK |
| **NO existe** PATCH de contenido por `memory_id` (solo upsert por topic_key o cambio de status) | grep `PUT`/`PATCH` en `api/memory.py` → 0 | **Gap** (D-M3) |
| Inyección cableada en los 3 runtimes vía un solo seam (PREPEND, best-effort, OFF default) | `services/context_enrichment.py:67` y `:338` (`_inject_stacky_memory_block`), gate `cli_feature_flags.memory_injection_enabled` `:350` | OK |
| Prioridad del bloque `stacky-memory` en el presupuesto de contexto F2.4 | `services/context_enrichment.py:106` (`_BLOCK_PRIORITY`, `stacky-memory`=80) | OK |
| Flags de memoria: master `STACKY_MEMORY_INJECTION_ENABLED` (OFF) + allowlist `STACKY_MEMORY_INJECTION_PROJECTS` | `config.py:240`; `services/harness_flags.py:126` (`FLAG_REGISTRY`, `env_only=True`) | OK |
| UI de flags genérica (lista declarativa del registry) | `api/harness_flags.py` + `GET /api/harness-flags` | OK — genérica, no específica de memoria |
| Frontend de memoria (moderación/curación MVP): tabs Memorias/Borradores + Triage/Grafo tras `MEMORY_ADVANCED_ENABLED` | `frontend/src/pages/MemoryPage.tsx` (+ `.module.css`) | OK — **no permite crear, editar ni configurar** (D-M2/D-M3) |

**Restricciones vinculantes (idénticas a docs 22/23/24, no relitigar):** cap duro de modelo vía `llm_router.clamp_model` (nunca opus/fable); "solo Stacky escribe en ADO" = todo por `ado_write_outbox`; mono-operador **sin RBAC** (`current_user()` en `api/_helpers` es `X-User-Email` sin validar → la atribución NO es autorización); claves de metadata existentes son contrato (agregar, nunca renombrar); todo flag nuevo entra en `config.py` + `FLAG_REGISTRY` (`services/harness_flags.py`) en el MISMO PR, default OFF/0, retro-compat **byte-idéntica** cuando está OFF; suite contaminada → validar por archivo de test; sin fallback silencioso entre runtimes; frontend CSS modules + react-query, **cero deps npm/py nuevas** sin justificación escrita, UI degrada con gracia ante metadata ausente.

**Regla 11 (innegociable, propia también de este plan):** ninguna acción se ejecuta sin gesto explícito del operador; ningún aprendizaje modifica memoria/directivas sin aprobación humana; sin autonomía, sin auto-intake, sin lanzamientos no iniciados por el operador. Las directivas las **autora el humano**; las que proponga el flywheel C2.2 (doc 24) nacen como **borrador `suggest`** y solo un humano las promueve a `always`.

---

## 2. Qué NO es este plan (anti-scope explícito)

1. **No es un motor de reglas / DSL de workflow.** Las directivas son texto imperativo del operador con targeting estructurado, NO un lenguaje ejecutable. No se evalúan condiciones lógicas ni se disparan acciones: se **inyectan al prompt** y el agente las obedece como instrucción. (Los workflows declarativos son `services/macros.py` FA-51 y los pipelines son U2.1 del doc 23 — acá no se tocan.)
2. **No es RBAC.** Cualquier operador puede crear/editar/borrar cualquier directiva; `author_email` es atribución para auditoría, no permiso. No se construye un gate "solo admin edita directivas" porque sería teatro (`current_user()` es un header). El plan de memoria v2 §B4 ya cortó el RBAC fantasma; este plan lo respeta.
3. **No re-implementa briefing-preview ni el flywheel.** El preview de briefing es C0.1 (doc 24) y el flywheel es C2.2 (doc 24): este plan los **extiende** declarando dónde aparecen las directivas. Si no están mergeados, el modo degradado está declarado en cada ítem.
4. **No agrega FTS5.** El build congelado no tiene FTS5 verificado (plan v2 §B6). Las directivas NO usan búsqueda full-text: se recuperan por **match exacto de targeting** (relacional), no por relevancia.
5. **No auto-genera directivas obligatorias.** Una directiva `enforcement=always` SIEMPRE nace de un click humano. La máquina (flywheel) solo propone borradores `suggest`.

---

## 3. Diagnóstico: dónde la memoria de hoy se queda corta

| # | Debilidad | Evidencia (file:line) | Impacto |
|---|---|---|---|
| **D-M1** | **Los caps de contexto por agente son inmutables.** `_AGENT_CAPS` y `_DEFAULT_CAP` están hardcodeados en el módulo; el operador no puede subir/bajar cuántas memorias o caracteres recibe un agente sin tocar el código y re-buildear. El objetivo "100% configurable" choca de frente con esto. | `services/memory_store.py:107-121` | Para afinar cuánta memoria entra (más contexto a `developer`, menos a `qa`) hay que recompilar. El operador no tiene la perilla. |
| **D-M2** | **La inyección de memoria solo se enciende desde flags genéricos.** El master `STACKY_MEMORY_INJECTION_ENABLED` y la allowlist `STACKY_MEMORY_INJECTION_PROJECTS` viven en la UI de flags genérica (`harness-flags`), no en la página de memoria. El operador que trabaja en Memoria no tiene ahí ni el toggle por proyecto ni un panel de "qué se inyectaría a este agente". | `config.py:240-242`, `services/harness_flags.py:126`, `MemoryPage.tsx` (sin controles de flag) | Configurar memoria exige saltar a otra pantalla y entender flags crudos; el ciclo de afinado es torpe. |
| **D-M3** | **No se puede crear ni editar una memoria desde la UI; no existe PATCH de contenido.** `MemoryPage` solo lista y cambia status (`set_status`). El único alta es `POST /api/memory` (sin formulario en la UI). No hay endpoint para editar título/contenido de una memoria por `memory_id`: el upsert es por `topic_key` y `set_status` solo toca el estado. | `MemoryPage.tsx` (sin form de alta/edición); `api/memory.py` (no hay `PUT`/`PATCH /<id>` de contenido) | Una memoria con un typo o una regla que cambió obliga a cuarentenarla y crear otra. No hay autoría ni mantenimiento real desde la UI. |
| **D-M4** | **La memoria es puramente observacional y probabilística: no hay "regla obligatoria".** `get_context_for_run` recupera por TF-IDF (`search`), filtra por B5, suprime conflictos y aplica caps. Una memoria valiosísima que no comparte vocabulario con el ticket **no aparece**; y dos memorias en `conflicts_with` activo-activo se **ocultan ambas**. No existe forma de decir "esto va SIEMPRE, sin importar el scoring". | `services/memory_store.py:858-933` (todo el camino pasa por `search`+supresión+cap); `_apply_conflict_suppression:786` | El conocimiento "duro" del operador (políticas del cliente, convenciones del proceso) queda a merced de la relevancia léxica. La instrucción más importante puede no llegar. |
| **D-M5** | **El targeting disponible es pobre para "tareas de tal proceso".** Hoy una memoria se filtra por `scope`, `project`, `source_agent_type` (match suave que solo suma 0.15 al ranking, `:771`) y `tags_json` (que ni siquiera filtra en `get_context_for_run`). No hay forma de decir "aplica a tickets cuyo work item type es X" o "cuya épica/título contiene Y". Además `review_after`/`expires_at` existen en el modelo pero **ningún código los lee** → una directiva obsoleta viviría para siempre. | `services/memory_store.py:120` (`_caps_for` ignora tags), `:771` (agent_match suave), `:153-154` (`review_after`/`expires_at` sin lectores) | No se puede targetear por proceso/tarea con precisión; y no hay caducidad → riesgo de directivas zombi que nadie revisa. |
| **D-M6** | **El alta por API acepta cualquier tipo no reservado sin validación de targeting ni de enforcement.** `POST /api/memory` valida solo que existan `project/type/title/content` y que el type no esté en `RESERVED_TYPES`. No hay noción de `enforcement` ni de `applies_to`; un type nuevo como `directive` entraría como observación más, sin semántica imperativa. | `api/memory.py:31-67` | Sin un contrato explícito para directivas, cualquier intento de "regla obligatoria" se diluye en el pool observacional y se pierde en el scoring (D-M4). |

**Lectura estratégica:** la memoria colaborativa resolvió bien el problema de *recordar lo aprendido*. Este plan resuelve dos problemas distintos y complementarios: (a) **gobernar** esa memoria desde la UI (caps, flags, scopes, edición) en vez de desde el código y flags crudos; y (b) darle al operador una herramienta **determinística** — la directiva obligatoria targeteada — para los casos en que "recordar si hay overlap" no alcanza y hace falta "obedecer siempre".

---

## 4. Hoja de ruta

Tres fases priorizadas por **valor-por-esfuerzo**. Complejidad: S ≤ ½ día, M ≤ 2 días, L > 2 días (dev agéntico). Orden recomendado: M0 (gobernanza de lo que ya existe) → M1 (el schema + recuperación de directivas, núcleo) → M2 (autoría/edición desde UI) → M3 (configurabilidad fina + frontera con doc 24).

### FASE M0 — Quick wins: hacer configurable lo que hoy está hardcodeado/escondido

---

#### M0.1 Caps de contexto por agente configurables (desde flag, sin recompilar)

- **Ataca:** D-M1.
- **Objetivo:** que el operador pueda ajustar `(max_memorias, max_chars)` por agente sin tocar el código. Default **byte-idéntico** a los `_AGENT_CAPS` actuales.
- **Diseño:**
  - Flag: `STACKY_MEMORY_CAPS_JSON` (str JSON, default `""` = usar `_AGENT_CAPS` actual) en `config.py` + `FLAG_REGISTRY` (`services/harness_flags.py`, mismo PR, `env_only=True`, `type="csv"` no aplica → declararlo `type="int"` no sirve; agregar variante de spec o documentarlo como JSON crudo; ver nota). Shape: `{"developer": [16, 16000], "qa": [8, 8000], ...}`.
  - `services/memory_store.py`: `_caps_for(agent_type)` (`:120`) deja de leer SOLO el dict del módulo: primero intenta `_load_caps_override()` (nuevo helper que parsea `STACKY_MEMORY_CAPS_JSON`, valida que cada valor sea `[int, int]` con ambos > 0, cae a `_AGENT_CAPS`/`_DEFAULT_CAP` ante cualquier malformación — mismo patrón fail-safe que `pricing._load_prices`, `harness/pricing.py:39`). Cachear el parse por proceso (TTL corto o invalidar al hot-apply de flags) para no parsear en cada run.
  - El override es **merge** sobre los defaults: un agente ausente del JSON conserva su cap actual. `max_chars` sigue siendo techo absoluto por bloque; la directiva (M1) reserva su propio slice fuera de este cap (ver M1.3).
  - **Nota de spec:** `FlagSpec.type` hoy soporta `"bool"|"csv"|"int"|"float"` (`services/harness_flags.py:20`). Para un JSON estructurado, agregar `"json"` al conjunto de tipos válidos del registry es un cambio aditivo de 1 línea + el renderer del frontend lo trata como textarea; si se quiere evitar tocar el enum, documentarlo como `"csv"` con validación propia en `memory_store`. Decidir al implementar por lo que menos toque el contrato del registry.
- **Criterios de aceptación:** flag vacío → `_caps_for` devuelve exactamente lo de hoy (test de regresión byte-idéntico); JSON válido con `developer:[16,16000]` → ese agente usa el nuevo cap, el resto intacto; JSON malformado → log warn + defaults (nunca crash, nunca run roto); valores ≤ 0 → ignorados (cae a default de ese agente).
- **Tests (TDD, `tests/test_memory_caps_override.py`):** override merge, malformado→default, valores inválidos, cache no rompe hot-apply.
- **Complejidad:** S.

---

#### M0.2 Panel de configuración de memoria en `MemoryPage` (toggles + "qué se inyectaría")

- **Ataca:** D-M2.
- **Objetivo:** que la página de Memoria tenga su propio panel de configuración: master de inyección, allowlist de proyectos, caps por agente (M0.1) y un preview "qué se inyectaría a este agente/proyecto" — sin saltar a la pantalla de flags genéricos.
- **Diseño:**
  - Backend: **reusar** `GET /api/harness-flags` (existe) para leer el estado de `STACKY_MEMORY_INJECTION_ENABLED`/`STACKY_MEMORY_INJECTION_PROJECTS`/`STACKY_MEMORY_CAPS_JSON` y el endpoint de hot-apply ya existente de `api/harness_flags.py` para escribirlos (NO crear endpoints nuevos de flags: el registry ya es la fuente única). El preview de inyección reusa `GET /api/memory/context-preview` (`api/memory.py:86`) que ya devuelve `get_context_for_run` para un `(project, agent_type, q)`.
  - Frontend: nueva sub-tab "Config" en `MemoryPage.tsx` (junto a Memorias/Borradores), visible siempre (no detrás de `MEMORY_ADVANCED_ENABLED` — la configuración es parte del MVP de gobierno). Controles: toggle master, editor de allowlist (CSV con chips), tabla editable de caps por agente (lee/escribe `STACKY_MEMORY_CAPS_JSON` vía el hot-apply de flags), y un selector `agent_type` + textarea de query que llama `context-preview` y muestra el bloque resultante (chars, hits, suppressed) — el operador VE qué recibiría el agente. react-query + CSS module; cero deps nuevas.
  - Gobernanza (rule 11): todos los cambios son escrituras explícitas del operador; el master nace OFF; cambiar un flag aquí es idéntico a cambiarlo en la pantalla de flags (mismo endpoint).
- **Criterios de aceptación:** con master OFF, el panel lo refleja y el preview muestra "inyección apagada"; subir un cap y recargar el preview muestra más memorias; allowlist con un proyecto restringe la inyección a ese proyecto (verificable porque el helper `memory_injection_enabled` ya combina master+allowlist, `context_enrichment.py:350`); la página degrada con gracia si `harness-flags` no trae las claves (panel read-only con aviso).
- **Tests (vitest, `pages/__tests__/MemoryPage.config.test.tsx`):** render del panel con flags ON/OFF, edición de caps dispara el mutation correcto, preview consume `context-preview` y renderiza chars/hits.
- **Complejidad:** M.

---

#### M0.3 Caducidad y revisión de memorias (`review_after`/`expires_at` dejan de ser letra muerta)

- **Ataca:** D-M5 (mitad caducidad). Prerrequisito de salud para las directivas (M1): una regla obligatoria que nadie revisa es peligrosa.
- **Objetivo:** que las columnas `review_after`/`expires_at` que ya existen en el modelo se respeten: una memoria **expirada no se inyecta**, y una memoria **vencida de revisión** se marca para que el operador la mire.
- **Diseño:**
  - `services/memory_store.py`: en `search` (`:677`), el filtro de candidatos suma `(StackyMemoryObservation.expires_at.is_(None)) | (expires_at > now)` — una memoria expirada nunca entra al pool. Cambio aditivo al WHERE; sin migración (las columnas existen, `:153-154`).
  - Nuevo helper `mark_stale_for_review() -> int`: marca `status="needs_review"` (estado existente) las `active` con `review_after < now`. Se invoca desde el reaper/daemon existente (mismo patrón que otros barridos del repo) con un flag de cadencia; **nunca** borra ni desactiva por sí solo (rule 11: solo mueve a `needs_review`, el humano decide). Default: el daemon corre solo si `STACKY_MEMORY_REVIEW_SWEEP_HOURS > 0` (int, default **0**=off) en `config.py` + `FLAG_REGISTRY`.
  - El alta (`save_observation`/`upsert_by_topic_key`) ya acepta `expires_at`; agregar paso de `review_after` (param aditivo) para que M2 pueda setearlo desde el formulario.
- **Criterios de aceptación:** memoria con `expires_at` en el pasado → no aparece en `search` ni en `get_context_for_run`; `review_after` vencido + sweep ON → pasa a `needs_review` (no `deleted`); sweep OFF (default) → cero efecto, byte-idéntico; memoria sin fechas → comportamiento actual exacto.
- **Tests (TDD, `tests/test_memory_expiry_review.py`):** expirada no se inyecta, review vencido→needs_review, sweep off no-op, sin fechas intacto.
- **Complejidad:** S.

---

### FASE M1 — Estructural: la directiva obligatoria targeteada (núcleo del plan)

---

#### M1.1 Schema de directiva (type `directive` + `enforcement` + `applies_to`, add-only)

- **Ataca:** D-M4, D-M6. Es el cimiento de toda la fase.
- **Objetivo:** modelar la directiva como ciudadano de primera clase **sin migración destructiva**, reusando la tabla `StackyMemoryObservation` con columnas add-only (patrón del repo: ORM + `ALTER TABLE ADD COLUMN` idempotente con try/except, como `db.py::_ensure_*`).
- **Diseño:**
  - **Decisión de modelado (la más jugada del plan):** NO crear tabla nueva. Una directiva ES una observación con semántica reforzada. Se agregan 3 columnas add-only a `StackyMemoryObservation` (`services/memory_store.py:128`):
    - `enforcement = Column(String(12))` — `None`/`"suggest"` (observacional, comportamiento actual) | `"always"` (obligatoria). Default lógico para filas viejas: `None` ≡ suggest. Las observaciones existentes quedan **byte-idénticas** (enforcement nulo = no es directiva).
    - `priority = Column(Integer, nullable=False, default=0)` — orden dentro de la sección de directivas (mayor primero). 0 para todo lo existente.
    - `applies_to_json = Column(Text)` — targeting estructurado (ver abajo). `None` para todo lo existente.
  - El **type** nuevo es `"directive"`. Se agrega a la lista de types válidos del alta (M2.1), y **explícitamente NO** se agrega a `RESERVED_TYPES` (`:92`): la directiva es canal USER (inyectable), no SYSTEM. Reconciliación con B5: el filtro `:894` excluye `_SYSTEM_PROMPT_TYPES`; `directive` no está en ese set → pasa. Pero las directivas **no** se recuperan por `search` (ver M1.2), así que no compiten con el pool observacional.
  - **Shape de `applies_to_json`** (todos los campos opcionales; un campo ausente = "no restringe por esa dimensión"; un run matchea si cumple TODAS las dimensiones presentes — AND):
    ```json
    {
      "agent_types": ["functional", "developer"],
      "projects": ["Strategist_Pacifico"],
      "work_item_types": ["Epic", "User Story"],
      "title_keywords": ["facturación", "nota de crédito"],
      "tags": ["proceso-cobranzas"]
    }
    ```
    - `agent_types`/`projects`: match exacto (case-insensitive). Ausente = todos.
    - `work_item_types`: match contra `Ticket.work_item_type` del run.
    - `title_keywords`: match si ALGUNA keyword (case-insensitive, substring) aparece en `Ticket.title` o `Ticket.description`. Es el disparador de "proceso/tarea".
    - `tags`: match si la directiva comparte ≥1 tag con… (no aplica al run; los tags son del autor — se usan para filtrar/organizar en la UI, no para el match de run). **Decisión:** `tags` NO participa del match de run (evita semántica ambigua); el match de proceso es `work_item_types` + `title_keywords`. Documentarlo.
  - Helper nuevo `directive_matches_run(directive_dict, *, agent_type, project, ticket_title, ticket_description, work_item_type) -> bool` — puro, testeable, sin DB. Es el corazón del targeting.
  - **Justificación de reusar la tabla vs tabla nueva:** add-only sobre `StackyMemoryObservation` hereda gratis: estados (`active`/`needs_review`/…), `author_email` (atribución), `review_after`/`expires_at` (M0.3, caducidad de directivas), `revision_count` (auditoría de ediciones M2.3), redacción PII (`get_context_for_run:912`), la UI de moderación existente y los endpoints de status/relations. Una tabla nueva duplicaría todo eso. El costo es 3 columnas nulas en filas que no son directivas — irrelevante.
- **Criterios de aceptación:** `create_all` sobre DB nueva crea las 3 columnas; `ALTER` idempotente sobre DB viva no rompe y filas existentes quedan con `enforcement=NULL, priority=0, applies_to_json=NULL`; una observación sin enforcement se comporta byte-idéntico (no aparece como directiva en ningún lado); `directive_matches_run` cubre AND multi-dimensión, dimensión ausente = no restringe, keyword substring case-insensitive.
- **Tests (TDD, `tests/test_directive_schema.py`):** migración add-only idempotente; `directive_matches_run` (cada dimensión, AND, vacío=matchea todo, keyword en title vs description); observación legacy intacta.
- **Complejidad:** M.

---

#### M1.2 Recuperación de directivas: inyección SIEMPRE, bypass del scoring

- **Ataca:** D-M4. El comportamiento distintivo de la directiva.
- **Objetivo:** que las directivas `enforcement=always` que matchean el targeting del run se inyecten **siempre**, sin pasar por TF-IDF ni por la supresión de conflictos, con presupuesto reservado y renderizadas en una sección imperativa separada al tope del bloque `stacky-memory`.
- **Diseño:**
  - Nuevo `services/memory_store.py::get_directives_for_run(*, project, agent_type, ticket_title, ticket_description, work_item_type, scopes=INJECT_SCOPES) -> list[dict]`:
    1. Query relacional (NO `search`): `status="active"`, `enforcement="always"`, `scope IN scopes`, `project == project` (o scope global), `deleted_at IS NULL`, y el filtro de expiración de M0.3. Esto trae candidatos sin scoring léxico.
    2. Filtrar en Python con `directive_matches_run(...)` (M1.1) — solo las que matchean el targeting del run.
    3. Ordenar por `priority` desc, luego `updated_at` desc.
    - **NO** pasa por `_apply_conflict_suppression`: una directiva obligatoria no se oculta por conflicto (si dos directivas se contradicen, eso es un problema de gobierno que la UI debe exponer — ver M3.2 — no algo que el sistema resuelva ocultando ambas en silencio).
  - `get_context_for_run` (`:858`) se reestructura aditivamente:
    - Calcula primero `directives = get_directives_for_run(...)`.
    - Reserva un **slice de presupuesto** para directivas: `directive_cap_chars = min(char_cap // 2, STACKY_MEMORY_DIRECTIVE_MAX_CHARS)` (nuevo flag int, default 4000, en `config.py`+`FLAG_REGISTRY`). Las directivas se redactan PII (mismo `redact_irreversible`) y se llenan hasta ese slice por orden de prioridad; si una directiva no entra, se trunca con marcador (NUNCA se dropea silenciosamente una directiva por cap — se trunca y se loguea; las directivas son demasiado importantes para desaparecer sin rastro).
    - El **resto** del presupuesto (`char_cap - usado_por_directivas`) lo consume el pool observacional como hoy (search → supresión → caps).
    - Render: la sección de directivas va PRIMERO, bajo un encabezado imperativo distinto: `## REGLAS OBLIGATORIAS DEL OPERADOR (cumplir SIEMPRE)`, seguida del bloque observacional habitual bajo su encabezado actual. Helper de render nuevo `_render_directives(items)` (espejo de `_render_memory:842` pero con framing imperativo).
    - El dict de retorno suma `directive_ids: [str]` y `directive_hits: int` (claves NUEVAS, aditivas — el `metadata` del bloque en `context_enrichment.py:382` las expone sin romper consumidores).
  - **Doble-canal B5:** las directivas son type `directive` (no reservado), así que conviven; pero ojo: si el operador targetea un agente y el conocimiento ya viaja por el SYSTEM prompt (FA-*), la directiva igual va por USER — es intencional (la directiva es una orden del operador, distinta del conocimiento FA-*). Documentar que NO hay riesgo de doble-inyección porque `directive` no está en `_SYSTEM_PROMPT_TYPES`.
  - **Flag maestro:** las directivas respetan el MISMO `STACKY_MEMORY_INJECTION_ENABLED` + allowlist que el bloque `stacky-memory` (si la inyección de memoria está OFF, no hay bloque donde meter las directivas). Esto es coherente y evita un segundo master.
- **Criterios de aceptación:** una directiva `always` que matchea el work_item_type del run se inyecta aunque su texto no comparta NINGUNA palabra con el ticket (verificable: query sin TF-IDF); una directiva en `conflicts_with` activo-activo con otra **NO** se oculta (a diferencia de las observaciones); el render pone las directivas primero, bajo el encabezado imperativo; el slice de directivas no canibaliza más de `directive_cap_chars`; una directiva que no entra se trunca con marcador y se loguea (no desaparece); con `enforcement=suggest` o `None`, la memoria se comporta byte-idéntico al actual (las directivas son aditivas); flag maestro OFF → cero inyección (directivas incluidas).
- **Tests (TDD, `tests/test_directive_retrieval.py`):** inyección sin overlap léxico; bypass de supresión de conflicto; orden por prioridad; slice de presupuesto y truncado con marcador; coexistencia con pool observacional (totales = directivas + observaciones); B5 sin doble-inyección; flag OFF byte-idéntico. Extensión de `tests/test_memory_injection.py` y `tests/test_memory_store.py` para el render combinado.
- **Complejidad:** L (es el ítem más profundo; partible: PR1 `get_directives_for_run` + matcher, PR2 integración en `get_context_for_run` + render + presupuesto).

---

#### M1.3 Coexistencia de directivas con los caps `_AGENT_CAPS`

- **Ataca:** D-M4 (cierre fino). Sub-ítem explícito porque es donde más fácil se rompe algo.
- **Objetivo:** garantizar que las directivas NUNCA sean dropeadas por el cap de cantidad/chars del pool observacional, y que la suma directivas+observaciones respete el techo absoluto del agente.
- **Diseño:**
  - El `char_cap` del agente (M0.1) es el techo **total** del bloque `stacky-memory`. Las directivas reservan su slice primero (M1.2); el pool observacional usa lo que queda. Si las directivas (truncadas a `directive_cap_chars`) más una sola observación exceden el techo total, la observación se dropea — pero las directivas NO.
  - El cap de **cantidad** (`max_memorias`) aplica solo al pool observacional, no a las directivas (una directiva no cuenta como "memoria" para ese tope). Documentar en el docstring de `get_context_for_run`.
  - Edge: si NO hay presupuesto ni para las directivas (agente con `max_chars` muy chico configurado en M0.1 < `directive_cap_chars`), las directivas se truncan al `char_cap` total y el pool observacional queda vacío — las directivas SIEMPRE ganan al pool. Loguear `directives_crowded_out_observations: true` para que el operador lo note (es señal de que su cap es demasiado chico para sus directivas).
- **Criterios de aceptación:** con 3 directivas y 10 observaciones y un cap holgado → entran las 3 directivas + las observaciones que quepan; con un cap chiquito → entran las directivas (truncadas si hace falta) y 0 observaciones, con el flag de log; `max_memorias` no recorta directivas.
- **Tests (TDD, dentro de `tests/test_directive_retrieval.py`):** directivas ganan al pool bajo presión de cap; max_memorias no afecta directivas; log de crowding.
- **Complejidad:** S (es lógica de presupuesto sobre M1.2).

---

### FASE M2 — Autoría y edición desde la UI (el operador como autor)

---

#### M2.1 Formulario de alta de memoria/directiva en `MemoryPage`

- **Ataca:** D-M3 (alta), D-M6.
- **Objetivo:** que el operador cree una memoria — y en particular una **directiva** — desde la UI, con targeting estructurado, enforcement y un preview "esto se inyectará SIEMPRE que…".
- **Diseño:**
  - Backend: extender `POST /api/memory` (`api/memory.py:31`) aditivamente para aceptar `enforcement` (`"suggest"|"always"`, default `"suggest"`), `priority` (int, default 0) y `applies_to` (dict → se serializa a `applies_to_json`). Validaciones nuevas: si `type == "directive"` → `applies_to` no puede estar **completamente vacío** (una directiva sin targeting es peligrosa: aplicaría a todo; rechazar 400 con mensaje claro "una directiva necesita al menos una dimensión de targeting"); `enforcement="always"` solo permitido para `type == "directive"` (una observación obligatoria no tiene sentido; 400). El rechazo de `RESERVED_TYPES` (`:43`) se mantiene; `directive` NO está reservado, así que pasa.
  - Validar `applies_to` con un helper (`_validate_applies_to`) que chequee tipos (listas de strings) y rechace claves desconocidas (contrato estricto: solo las 5 dimensiones de M1.1).
  - Frontend: en `MemoryPage.tsx`, botón "➕ Nueva" → modal/drawer con: selector de tipo (los injectables + `directive`), título, contenido, scope, y — cuando type=`directive` — sección de targeting (multiselect de `agent_types`; multiselect/CSV de `projects`; multiselect de `work_item_types`; chips de `title_keywords`; selector `enforcement` suggest/always; `priority`). Debajo, **preview imperativo**: "Esta directiva se inyectará SIEMPRE que el run sea de agente {X}, proyecto {Y}, tipo {Z} y el ticket mencione {kw}". El preview es texto compuesto en el cliente desde el targeting (no requiere backend); opcionalmente un botón "Probar contra un ticket" que llama un endpoint dry-run (M2.2).
  - Gobernanza (rule 11): el alta es un gesto explícito; `author_email` se sella desde `current_user()` (`api/memory.py:63`) como hoy — atribución, no permiso. Una directiva `always` creada por el operador es su responsabilidad firmada.
- **Criterios de aceptación:** crear una observación normal → idéntico a hoy; crear una directiva con targeting → fila con `type=directive`, `enforcement`, `applies_to_json` poblados; directiva sin targeting → 400; `enforcement=always` con type≠directive → 400; `applies_to` con clave desconocida → 400; el preview en la UI refleja el targeting elegido.
- **Tests (TDD):** backend `tests/test_memory_create_directive.py` (alta directiva, validaciones, applies_to estricto); vitest `pages/__tests__/MemoryPage.create.test.tsx` (form, preview imperativo, submit).
- **Complejidad:** M.

---

#### M2.2 Edición de contenido por `memory_id` (cerrar el gap del PATCH) + dry-run de targeting

- **Ataca:** D-M3 (edición).
- **Objetivo:** poder editar título/contenido/targeting/enforcement/priority de una memoria existente sin cuarentenarla y recrearla; y poder probar el targeting de una directiva contra un ticket real antes de guardarla.
- **Diseño:**
  - Backend: nuevo `services/memory_store.py::update_observation(memory_id, *, title=None, content=None, enforcement=None, priority=None, applies_to_json=None, expires_at=None, review_after=None) -> bool` — **add-only / no destructivo**: solo actualiza los campos provistos (None = no tocar), recalcula `normalized_hash` si cambió título/contenido, incrementa `revision_count` (auditoría), actualiza `updated_at`. NO cambia `status` (eso es `set_status`), NO toca `topic_key` (la unicidad se mantiene), NO crea fila nueva. Coexiste con `upsert_by_topic_key` (que es por clave): este es por id.
  - Endpoint: `PATCH /api/memory/<memory_id>` (nuevo, `api/memory.py`) body con los campos editables; valida lo mismo que M2.1 (directiva sin targeting → 400, etc.); 404 si no existe. Mantener `POST /<id>/status` (`:268`) intacto.
  - Dry-run de targeting: `POST /api/memory/directive-preview` body `{applies_to, ticket_id}` → carga el `Ticket` y devuelve `{matches: bool, reasons: [str]}` usando `directive_matches_run`. Read-only, no crea nada. Sirve al "Probar contra un ticket" de M2.1.
  - Frontend: cada `MemoryRow` (`MemoryPage.tsx:45`) gana botón "✏️ Editar" → reusa el modal de M2.1 pre-cargado; guardar llama el PATCH. La cadena de revisiones (`revision_count`) se muestra como chip.
- **Criterios de aceptación:** editar el contenido de una memoria → mismo `memory_id`, `revision_count` +1, `normalized_hash` recalculado; editar el targeting de una directiva → `applies_to_json` actualizado y el match cambia; PATCH de id inexistente → 404; PATCH sin campos → 400 (nada que actualizar); `directive-preview` contra un ticket que matchea → `matches:true` con razones; status NO cambia por el PATCH (sigue siendo competencia de `set_status`).
- **Tests (TDD, `tests/test_memory_update.py`):** update parcial, revision_count, hash recalculado, 404, directive-preview match/no-match; el upsert por topic_key sigue verde (no se rompió).
- **Complejidad:** M.

---

### FASE M3 — Diferenciales: configurabilidad fina y frontera con doc 24

---

#### M3.1 Gestión de scopes y types visibles desde la UI

- **Ataca:** D-M2 (cierre).
- **Objetivo:** que el operador configure qué scopes se inyectan (más allá del default project/team/global) y vea/gestione los types disponibles, todo desde la página de memoria.
- **Diseño:**
  - `INJECT_SCOPES` (`memory_store.py:77`) deja de ser la única fuente: `get_context_for_run` y `get_directives_for_run` aceptan `inject_scopes` por parámetro (ya lo hacen) — agregar un flag `STACKY_MEMORY_INJECT_SCOPES` (csv, default `"project,team,global"` = byte-idéntico) que el seam de inyección (`context_enrichment.py:369`) pasa como `inject_scopes`. Permite, p. ej., incluir `personal` para un operador único (caso mono-operador real). Default OFF/idéntico.
  - Panel en la sub-tab Config (M0.2): checkboxes de scopes inyectables + lista informativa de types (injectables vs reservados B5, leídos de `RESERVED_TYPES` vía un endpoint trivial `GET /api/memory/types` que exponga `{injectable: [...], reserved: list(RESERVED_TYPES)}` — read-only, sin lógica).
  - Gobernanza: cambiar scopes es escritura explícita de flag; el default no cambia nada.
- **Criterios de aceptación:** default → scopes idénticos a hoy; agregar `personal` → memorias personales del operador entran a la inyección; `GET /api/memory/types` lista injectables y reservados correctamente; quitar `team` → memorias team dejan de inyectarse.
- **Tests (TDD, `tests/test_memory_scopes_config.py`):** scopes por flag, default idéntico, endpoint de types; vitest del panel de scopes.
- **Complejidad:** S/M.

---

#### M3.2 Salud de directivas: contradicciones, inflación y obsolescencia

- **Ataca:** D-M5 (cierre), riesgo central de las directivas. Es la red de seguridad de gobierno.
- **Objetivo:** que el operador vea en un panel los riesgos de su set de directivas: directivas que se contradicen (mismo targeting, contenido opuesto — heurística), directivas que inflan el presupuesto (suma de chars cerca del cap), y directivas obsoletas (`review_after`/`expires_at` vencidos, o sin uso).
- **Diseño:**
  - Nuevo `services/memory_store.py::directive_health(project) -> dict`:
    - `overlapping: [{ids, shared_targeting}]` — directivas activas cuyos `applies_to` se solapan en TODAS las dimensiones presentes (mismo agente+proyecto+work_item_type al menos). NO juzga si el contenido se contradice (eso requiere LLM, fuera de scope MVP); solo señala "estas dos aplican al mismo escenario, revisá que no se peleen".
    - `budget_pressure: {project, agent_type, directive_chars, cap, ratio}` por agente — usando los caps de M0.1 y `directive_cap_chars`. `ratio > 0.8` = bandera.
    - `stale: [{id, review_after, expires_at}]` — vencidas de revisión o expiradas (reusa la lógica de M0.3).
  - Endpoint `GET /api/memory/directive-health?project=X` (read-only).
  - Frontend: sección "Salud de directivas" en la sub-tab Config (o una sub-tab propia si hay muchas): tres listas con acciones que llevan al editor (M2.2) o al `set_status`. Cada bandera enlaza a las directivas involucradas.
  - **Conexión con conflict-suppression:** las directivas NO se suprimen por conflicto (M1.2). Por eso este panel es la ÚNICA forma de que el operador detecte que dos directivas se pelean: el sistema no lo resuelve por él (rule 11), se lo **muestra**.
- **Criterios de aceptación:** dos directivas con el mismo targeting → aparecen en `overlapping`; directivas que suman > 80% del slice → `budget_pressure` con bandera; directiva con `review_after` vencido → `stale`; proyecto sin directivas → todo vacío (no error).
- **Tests (TDD, `tests/test_directive_health.py`):** overlapping multi-dimensión, budget ratio, stale; vitest del panel.
- **Complejidad:** M.

---

#### M3.3 Directiva en el briefing-preview (locked) y como candidato del flywheel — EXTIENDE C0.1 y C2.2 (doc 24)

- **Ataca:** integración con la capa de amplificación. Incremental — NO re-implementa C0.1 ni C2.2.
- **Frontera con doc 24 (declarada):**
  - **C0.1** (briefing-preview, `POST /api/agents/briefing-preview` + `excluded_block_ids`): cuando exista, el bloque `stacky-memory` que ya lista incluirá, en su preview, las directivas inyectadas. Este plan declara que esas directivas se marcan **`locked: true`** en el preview (igual que C0.1 marca locked los `raw_blocks` del operador): el operador NO puede destildar una directiva obligatoria desde el preview de un run (sería contradecir su propia regla; para desactivarla va a la página de memoria y la cuarentena/edita). Implementación: cuando C0.1 arme el preview del bloque `stacky-memory`, si `directive_ids` está en el metadata del bloque, esos sub-ítems se reportan locked. Es un cambio de ~5 líneas EN C0.1, no acá.
  - **C2.2** (flywheel de correcciones): cuando un grupo recurrente de correcciones sugiera una regla estable, el botón "Proponer como memoria" podrá proponer una **directiva** (type `directive`) en vez de una observación — pero SIEMPRE como `enforcement="suggest"` y `status` de moderación pendiente. **Una directiva propuesta por la máquina NUNCA nace `always`**: solo el operador, revisándola, la promueve a obligatoria (vía M2.2). Esto preserva rule 11 al 100%: la máquina propone una regla blanda; el humano decide si es obligatoria.
  - **Modo degradado (sin C0.1/C2.2):** las directivas funcionan completas igual (M1/M2); simplemente no aparecen en el preview de briefing (porque no existe) ni las propone el flywheel (porque no existe). Este ítem NO construye briefing-preview ni flywheel — espera a que existan y los extiende.
- **Objetivo:** declarar el contrato de integración para que, cuando C0.1/C2.2 se implementen, las directivas encajen sin retrabajo.
- **Diseño:** documentación de contrato + los dos cambios mínimos descritos (locked en C0.1; type+enforcement en el "Proponer como memoria" de C2.2). El metadata del bloque `stacky-memory` ya expone `memory_ids`; M1.2 le suma `directive_ids` → C0.1 los lee.
- **Criterios de aceptación:** (cuando C0.1 exista) las directivas aparecen locked en el preview y no son excluibles; (cuando C2.2 exista) "Proponer como memoria" puede crear un borrador de directiva `suggest` pendiente, jamás `always`; sin C0.1/C2.2 → las directivas funcionan y este ítem es no-op verificable.
- **Tests:** se incorporan a los tests de C0.1/C2.2 cuando esos ítems se implementen (este ítem es contrato, no código nuevo aislado).
- **Complejidad:** S (contrato + 2 cambios mínimos en ítems ajenos).

---

## 5. Priorización y secuencia

| Orden | Ítem | Complejidad | Valor | Riesgo | Dependencias |
|---|---|---|---|---|---|
| 1 | M0.1 Caps por agente configurables | S | Alto (perilla que faltaba) | Bajo (flag, default idéntico) | — |
| 2 | M0.3 Caducidad/revisión (`expires_at`/`review_after`) | S | Medio/alto (salud) | Bajo (aditivo) | — |
| 3 | M1.1 Schema de directiva (add-only) | M | **Muy alto (cimiento)** | Medio (migración add-only) | — |
| 4 | M1.2 Recuperación de directivas (bypass scoring) | L | **Muy alto (núcleo)** | Medio (toca `get_context_for_run` → aditivo, flag) | M1.1, M0.1 (slice de budget) |
| 5 | M1.3 Coexistencia con caps | S | Alto | Bajo | M1.2 |
| 6 | M2.1 Formulario de alta directiva | M | Muy alto (autoría) | Bajo | M1.1 |
| 7 | M2.2 PATCH de contenido + dry-run | M | Alto (cierra D-M3) | Bajo | M1.1 |
| 8 | M0.2 Panel de config en MemoryPage | M | Alto (gobierno visible) | Bajo (reusa flags+preview) | M0.1 |
| 9 | M3.1 Scopes/types desde UI | S/M | Medio | Bajo | M0.2 |
| 10 | M3.2 Salud de directivas | M | Alto (red de seguridad) | Bajo | M1.1, M1.2 |
| 11 | M3.3 Frontera C0.1/C2.2 (contrato) | S | Medio (encaje futuro) | Bajo | C0.1/C2.2 (doc 24, degradado) |

**Reglas de implementación (las 7 del doc 22 + las 3 de frontend del doc 23 aplican íntegras):** TDD; validar por archivo de test (suite contaminada — ver el caveat del manual de memoria §6: correr los archivos de a uno); flag nuevo = `config.py` + `FLAG_REGISTRY` mismo PR; metadata solo claves nuevas (las de este plan: `directive_ids`, `directive_hits`, y las columnas add-only `enforcement`/`priority`/`applies_to_json`); default OFF/idéntico (retro-compat byte-idéntica — una DB sin directivas y con los flags en default se comporta EXACTAMENTE como hoy); ADO solo vía `ado_write_outbox` (este plan no escribe a ADO); sin fallback silencioso; ningún componente huérfano se reusa sin validar props + test vitest; CSS modules + react-query + cero deps nuevas; UI degrada con gracia.

**Regla 11 (innegociable):** las directivas `always` las autora y firma el operador; la máquina (flywheel C2.2) solo propone borradores `suggest`; nada se auto-activa; el sistema NUNCA resuelve una contradicción entre directivas ocultándolas (las muestra en M3.2 y el humano decide). Si un ítem se puede leer como "el sistema decidió obedecer/ignorar una regla por su cuenta", está mal.

---

## 6. Qué va a notar cada audiencia (antes → después)

### Operador (autor de la memoria y de las reglas)
- **Hoy:** la memoria "aparece si hay suerte léxica". No puede crear ni editar una memoria desde la UI (solo cambiar su estado), los caps por agente están en el código, y la inyección se prende desde una pantalla de flags crudos. No tiene forma de decir "para los tickets de facturación, hacelo SIEMPRE así".
- **Post-M0:** ajusta los caps por agente desde la página de memoria, ve "qué se inyectaría" a cada agente, y las memorias caducas dejan de contaminar el contexto.
- **Post-M1:** escribe una **directiva obligatoria** ("para `developer` en tickets `User Story` que mencionen 'nota de crédito', usá el procedimiento X") y esa regla se inyecta SIEMPRE que el run matchee, al tope del prompt, sin importar el scoring ni los conflictos.
- **Post-M2/M3:** crea y edita directivas con un formulario, las prueba contra un ticket antes de guardarlas, configura scopes desde la UI, y un panel le avisa si dos directivas se pisan, si infló el presupuesto o si alguna quedó obsoleta.

### Desarrollador / equipo (quien vive en ADO)
- **Hoy:** recibe artefactos cuya consistencia depende de que la memoria relevante haya hecho match.
- **Después:** recibe artefactos que respetan las **convenciones obligatorias del proceso** que el operador codificó como directivas — más consistentes entre tickets del mismo tipo, sin que dependa de la suerte del retrieval.

### Management
- **Hoy:** el conocimiento operativo del equipo es tácito y volátil.
- **Después:** las reglas de negocio críticas ("así se procesa cobranzas") son **activos auditables**: directivas con autor, fecha, targeting y caducidad, gobernadas desde una UI, con un panel de salud que mide cuántas hay, si se contradicen y cuántas están obsoletas.

---

## 7. Ventaja competitiva: por qué la directiva targeteada supera al "system prompt grande" y a la memoria suelta

1. **Targeting quirúrgico vs prompt global.** Meter "para facturación hacé X" en el `.agent.md` lo aplica a TODO run de ese agente (ruido y tokens en los 9 de cada 10 tickets que no son de facturación). La directiva targeteada solo se inyecta cuando el run matchea el proceso — el contexto correcto en el momento correcto, sin inflar el resto.
2. **Determinismo donde importa, probabilidad donde alcanza.** La memoria observacional (TF-IDF) es perfecta para "lo que el equipo aprendió" — barata, auto-alimentada, tolerante. Pero una **política del cliente** no puede depender de overlap léxico. La directiva da el determinismo ("esto SIEMPRE") sin sacrificar la riqueza del pool observacional para todo lo demás. Las dos capas conviven en el mismo bloque, cada una en lo suyo.
3. **Gobierno auditable y editable, no un prompt monolítico.** Un `.agent.md` enorme con reglas de proceso es imposible de auditar, versionar por regla, o caducar. Cada directiva es una fila con autor, targeting, prioridad, `review_after`, `revision_count` e historial de estado — y se edita desde una UI. El conocimiento duro del equipo deja de vivir enterrado en un prompt y pasa a ser un activo gestionable. Un CLI suelto no tiene nada de esto: re-tipeás la regla en cada sesión y se evapora al cerrar.

---

## 8. Métricas de éxito del plan

| Métrica | Hoy | Objetivo |
|---|---|---|
| Configurar el cap de contexto de un agente | editar código + rebuild | 1 edición en la UI de memoria (M0.1/M0.2) |
| Crear/editar una memoria desde la app | imposible (solo cambiar status) | formulario de alta + PATCH de contenido (M2.1/M2.2) |
| Garantizar que una regla del proceso se aplique a sus tickets | depende del overlap TF-IDF | 100% cuando el run matchea el targeting (directiva `always`, M1.2) |
| Reglas obligatorias aplicadas a TODO run (ruido) vs targeteadas | system prompt global (todo o nada) | targeteadas por agente/proyecto/tipo/keyword (M1.1) |
| Directivas obsoletas detectadas | 0 (no hay caducidad ni panel) | `review_after`/`expires_at` respetados + panel de salud (M0.3/M3.2) |
| Riesgo de directivas contradictorias visible al operador | invisible | panel `directive-health` con overlapping (M3.2) |
| Encendido/scopes de inyección desde la página de memoria | solo flags crudos en otra pantalla | panel propio en MemoryPage (M0.2/M3.1) |
