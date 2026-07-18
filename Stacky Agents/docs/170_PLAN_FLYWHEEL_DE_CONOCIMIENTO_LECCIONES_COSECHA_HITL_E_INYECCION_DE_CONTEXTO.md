# Plan 170 — Flywheel de conocimiento: lecciones estructuradas, cosecha human-in-the-loop e inyección al contexto de agentes

## Versión: v1 -> v2 (crítica adversarial aplicada)

**Estado:** IMPLEMENTADO F0-F7 (2026-07-18) — cierra la serie RSI 167-170; branch `impl/rsi`. Tests verdes por archivo: 8 flags + 14 store + 11 harvest + 10 injection + 5 eval_link + 11 endpoints = 59 backend + 12 vitest (knowledgeModel), tsc exit 0. uiDebtRatchet rojo SOLO por deuda ajena preexistente (KnowledgeSection.tsx/module.css aportan 0). Desviaciones: las 3 FlagSpec int van SIN `default=` (C14, precedente 167/168/169) con el efectivo en config.py; el enlace lección↔caso de eval arma `evidence` ANTES de `create_proposal` (el 167 no expone `evidence` en `_PATCHABLE_FIELDS` — contrato intocable). · **Autor:** StackyArchitectaUltraEficientCode · **Juez:** StackyArchitectaUltraEficientCode (adversarial)

**CHANGELOG v1 -> v2:**

- **C1 (IMPORTANTE, PII total en la cosecha):** en v1 solo el output del run `incident_dev`
  pasaba por `redact_irreversible`; el texto del intake y el doc de la incidencia entraban
  al draft SIN máscara — y una lección aprobada se inyecta a TODOS los prompts futuros
  (amplificador de fugas). v2: G15 ampliado — TODO insumo textual externo se enmascara
  antes de entrar al draft, y el draft final (title+body, incluido el manual) se enmascara
  otra vez antes de `create_proposal` (defensa en profundidad). Test nuevo F2 caso 11.
- **C2 (IMPORTANTE, dedup de cosecha robusto):** en v1 `harvested_incident_ids` contaba
  CUALQUIER propuesta de `knowledge_rag` con `"incident:<id>"` en `evidence`: (a) las
  propuestas del MAPE del 167 (regla R-A3, también sobre incidencias) podían marcar
  candidatas como "ya cosechadas" sin cosecha real; (b) una propuesta RECHAZADA dejaba la
  incidencia bloqueada para siempre en el panel. v2: el set cuenta SOLO propuestas con
  algún marker `harvest:*` en `evidence` Y `status != "rejected"` (§4.4). Los markers
  `harvest:*` quedan declarados EXCLUSIVOS de este plan. Test nuevo F1 caso 13.
- **C3 (IMPORTANTE, honestidad de contadores):** `record_injection` corre al armar el
  bloque, pero el presupuesto F2.4 del 133 corre DESPUÉS y puede podar el bloque
  (prioridad 79 podable): `usage_count` contaría lecciones que no llegaron al prompt.
  v2: semántica LITERAL congelada — `usage_count` = "veces SELECCIONADA para inyección"
  (§4.2), rótulo del panel "Seleccionada Nx" (F6) y nota en R6. Sin tocar el contrato 133.
- **C4 (IMPORTANTE, drift de contratos vecinos):** los docs 167/168/169 son v1 y serán
  reescritos a v2 por el pipeline; sus números de línea rotarán. v2: nueva G17 (citas a
  docs hermanos anclan por §sección+símbolo) y pre-check global AMPLIADO con greps de los
  símbolos consumidos en el CÓDIGO real (`update_proposal_fields`, `maybe_auto_apply`,
  `VALID_ORIGINS`/`create_case`/`read_runs_tail`) — si falta alguno, DETENERSE y reportar
  drift de contrato (§5).
- **C5 (MENOR, lecciones contradictorias):** el header literal del bloque §4.5 ahora
  incluye la regla de precedencia ("número más bajo gana; anotá el conflicto").
- **C6 (MENOR, prosa):** §3.5 decía "lo vacía SOLO su rollback"; el rollback del 167
  remueve SOLO la línea de la lección revertida (167 F2). Corregido.
- **C7 (MENOR, comentario desactualizado):** F3 toque (a-bis): extender el comentario de
  `_HIGH_PRIORITY_THRESHOLD` (`context_enrichment.py:249-250`) con `evolution-lessons(79)`.
- **C8 (MENOR, ambigüedad):** el pseudocódigo del injector F3 tenía una elipsis en el
  armado con cap; v2 trae el loop literal vía `build_lessons_block` (función pura nueva).
- **C9 (MENOR, obsolescencia):** en v1 una lección muerta solo se sugería al exceder el
  cap 200; con corpus chico vivía para siempre. v2: `retire_suggestions` agrega la razón
  `"sin_uso_prolongado"` (`usage_count == 0` y edad > `_STALE_DAYS = 60` días) SIEMPRE
  visible — sugerencia, jamás auto-retiro. Test nuevo F1 caso 14.
- **[ADICIÓN ARQUITECTO] Vista previa de inyección (dry-run):** endpoint
  `GET /knowledge/injection-preview` + panel colapsable en F6: el operador VE el bloque
  §4.5 exacto que recibiría un agente (por agent_type/proyecto/query) SIN registrar uso.
  Cierra el gap HITL del retorno: hoy el humano aprueba lecciones pero nunca ve cómo
  quedan en el prompt. Reusa `build_lessons_block` (C8); test F5 caso 11.
- **Contratos de la serie:** SIN cambios hacia 167/168/169. Única premisa nueva
  explícita: los markers `harvest:*` de `evidence` son exclusivos del 170 (C2); los
  planes hermanos no deben emitirlos (hoy ninguno los define — verificado en sus v1).
- Conteos actualizados: tests backend 8+14+11+10+5+11 = **59** (antes 55); frontend 8.
**Serie:** "Auto-mejora recursiva" **4 de 4 — CIERRA LA SERIE** (directiva del operador 2026-07-17):
**167** = Centro de Evolución: propuestas + ciclo MAPE con gates humanos (PROPUESTO, dependencia DURA) ·
**168** = arnés de fitness: golden tasks + juez local (PROPUESTO, dependencia DURA) ·
**169** = optimizador evolutivo: mutación reflexiva + Pareto + archive (PROPUESTO, dependencia BLANDA: F2.b degrada sin él) ·
**170 (este)** = flywheel de conocimiento: fallo→lección→conocimiento→agente-mejor.
No hay plan 5: este documento cierra el ciclo Monitor→Evaluar→Optimizar→**Aprender**
(§12). PROHIBIDO re-implementar acá nada de los otros tres planes: este plan CONSUME
sus contratos §8 (los honra con nombres literales, no los redefine).

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

| Sustrato | Anclaje verificado | Rol en el 170 |
|---|---|---|
| **Plan 167 IMPLEMENTADO (DURA)** | doc 167 §4.1 (layout `data_dir()/evolution/` con `lessons.jsonl`), §4.3 (`ImprovementProposal`), §4.4 (máquina de estados), §F1 (`evolution_store.create_proposal/transition/list_proposals`), §F2 (`evolution_apply.maybe_auto_apply` doc:739; apply de `knowledge_note` appendea a `lessons.jsonl` con `lesson_id = p["id"]` doc:754-757), §8.3 (contrato hacia este plan) | Pre-check obligatorio: `test -f "Stacky Agents/backend/services/evolution_store.py"` — si falta, DETENERSE y reportar "Plan 167 no implementado". |
| **Plan 168 IMPLEMENTADO (DURA)** | doc 168 §4.2 (`EvalCase` con `origin`/`source_ref`), §F1 (`backend/evals/case_store.py`: `VALID_ORIGINS`, `create_case`, `list_cases`, `read_runs_tail` — este último citado también por el 169 doc:579), §F5 (`from-incident` crea caso con `source_ref=f"incident:{incident_id}"` doc:1060), §4.6 (rúbrica `leccion_conocimiento`), §8.3 (reserva `origin="lesson"` para ESTE plan: "el 170 lo agrega con su migración" doc:1356) | Pre-check obligatorio: `test -f "Stacky Agents/backend/evals/case_store.py"` — si falta, DETENERSE y reportar "Plan 168 no implementado". |
| Plan 169 (BLANDA) | doc 169 §4.1 (layout `data_dir()/evolution/optimizer/`), §4.3 (`MutationLesson`: `{id, run_id, aspect_key, variant_id, text, outcome, delta, created_at}`), §F1 (`backend/services/evolution_optimizer_store.py`: `read_lessons_tail(aspect_key=None, limit=20)` doc:803), §8.2 ("cada MutationLesson con outcome=='mejoro' es materia prima curable — el 170 puede leer read_lessons_tail() y proponer su promoción") | F2.b: fuente 2 de cosecha. Si el 169 NO está en el árbol, F2.b degrada declaradamente (import tolerante → lista vacía) y el resto del plan funciona completo. |
| **Contrato de inyección de contexto (Plan 133)** | `backend/services/context_enrichment.py:60` (`enrich_blocks` — docstring `:3-6`: "TODOS los runtimes (github_copilot, codex_cli, claude_code_cli) inyecten el mismo contexto"), `:366-386` (`_BLOCK_PRIORITY`), `:96` (`_rag_query = title+description`), `:960-1005` (`_inject_rejection_lessons`, Plan 48 — patrón espejo EXACTO de este plan), `:876` (`_inject_stacky_memory_block`, patrón PREPEND) | F3: la inyección de lecciones entra por ESTE seam único — paridad de 3 runtimes automática. |
| Callers de `enrich_blocks` (paridad 3 runtimes) | `backend/agent_runner.py:695` (runtime github_copilot), `backend/services/claude_code_cli_runner.py:583`, `backend/services/codex_cli_runner.py:329`; render CLI: `context_enrichment.build_ticket_context_text` `:1220` + `_render_blocks` `:1255` (renderiza TODOS los blocks con `content`) | F3: un bloque agregado dentro de `enrich_blocks` viaja solo a los 3 runtimes, cero cambio por runner. |
| Motor TF-IDF compartido (Planes 64/115) | `backend/services/rag_retriever.py:16` (`RagChunk(id, text, payload)` frozen dataclass), `:63` (`build_index(chunks, content_hash) -> RagIndex`), `:75` (`retrieve(index, query, top_k) -> list[tuple[RagChunk, float]]` — "Nunca lanza; score mínimo 0.0") | F1 (dedup por similitud) y F3 (ranking top-N por relevancia). Reuso, no reinvención. |
| Incidencias (Planes 131/160/166) | `backend/services/incident_store.py:36` (`incidents_root`), `:106` (`create_incident`, status inicial `"capturada"` `:164`), `:196` (`get_incident`), `:206` (`update_incident`), `:230` (`list_incidents`); estados reales verificados: `capturada|analizando|analizada|publicada|error` (`frontend/src/incidents/incidentModel.ts:25-30`; NO existe estado "resuelta": la resolución vive en el run del dev y su comentario 🚀) | F2.a: fuente 1 de cosecha (incidencia publicada + run del dev resolutor). |
| Doc de incidencia (Plan 131 F6) | `backend/services/incident_docs.py:74` (`write_incident_doc` → `.md` bajo `STACKY_AGENTS_ROOT/docs/incidencias/` con fallback `data_dir()/incident_docs` `:29-35`); el `doc_path` queda en el intake (`frontend/src/incidents/incidentModel.ts:42` `doc_path`) | F2.a: insumo textual del draft de lección (lectura tolerante). |
| Dev resolutor (Plan 166 F4) | `backend/services/incident_dev_context.py:14` (`_AGENT_FILENAME = "IncidentDevResolver.agent.md"`), `:22-26` (frontmatter `stacky_agent_type: incident_dev`), `:79-89` (cierre 🚀 con secciones LITERALES `CAUSA RAIZ`, `ARCHIVOS MODIFICADOS`, `RESUMEN DEL FIX`, `TESTS EJECUTADOS Y RESULTADO`, `CRITERIOS DE ACEPTACION VERIFICADOS`), `:121` (`_find_incident_doc_path_for_tracker`); registrado en `backend/agents/__init__.py:27` (`IncidentDevAgent()  # Plan 166 F4`) | F2.a: el output del run `incident_dev` con `CAUSA RAIZ` es la señal EXTERNA verificada de la que nace la lección (anti self-confirming, §2.2-1). |
| Registry de agentes | `backend/agents/__init__.py:14-30` (`registry` con 12 agentes), `:33` (`list_agents`) | F1 (validación suave de scope), F5 (KPI cobertura por agente). |
| `AgentExecution` | `backend/models.py:207`; patrón de query por ticket: `context_enrichment.py:1130-1139` | F2.a: localizar el run `incident_dev` completado de la Issue de la incidencia. |
| PII mask | `services/pii_masker.redact_irreversible` (import real en `backend/evals/harvest.py:60`, aplicado en `:95` — riel G14 del 168) | F2.a: el output de ejecución que entra al draft se enmascara ANTES de usarse. |
| LLM local (redactor) | `backend/copilot_bridge.py:241-249` (firma `invoke_local_llm(*, agent_type, system, user, on_log, execution_id=None, model=None)`), `:257-262` (RuntimeError si `LOCAL_LLM_ENDPOINT` vacío), `:124-128` (`BridgeResponse.text`) | F2: redacción del draft con **degradación declarada** a plantilla determinista (precedente 167 F3 / 127). |
| `data_dir()` | `backend/runtime_paths.py` símbolo `data_dir` (ancla citada por 167/168/169; el archivo tiene WIP ajeno hoy — anclar por símbolo, no por línea) | Persistencia: `data_dir()/evolution/` (archivos del 167) + `lessons_meta.json` nuevo. |
| Flags patrón triple | `backend/services/harness_flags.py:21` (`FlagSpec`), `:117` (`_CATEGORY_KEYS`), `:265` (tupla que contiene `"STACKY_PLANS_BOARD_ENABLED"` — los 167/168/169 insertan ahí sus keys en orden), `:331` (nota "toda flag nueva…"), `:3267` (FlagSpec `STACKY_PLANS_BOARD_ENABLED`, la cadena de inserción sigue con 167→168→169) | F0: las 5 flags de este plan van INMEDIATAMENTE después de las 5 del 169 (ubicar por el literal `STACKY_EVOLUTION_OPTIMIZER_MIN_MARGIN_PCT`). |
| Meta-tests de flags | `backend/tests/test_harness_flags.py:467` (`_CURATED_DEFAULTS_ON`), `backend/tests/test_harness_flags_requires.py:120` (`_REQUIRES_MAP_FROZEN`) | F0. |
| Ratchet de tests | `backend/scripts/run_harness_tests.sh:20` (`HARNESS_TEST_FILES=(`; zona de entradas recientes `:458-460`) y `backend/scripts/run_harness_tests.ps1:412-414` | F7. |
| Registro de blueprints | `backend/api/__init__.py:61` (zona de imports), `:122` (zona de registers) + las líneas `evolution_bp` (167 F4), `evolution_fitness` (168 F5), `evolution_optimizer` (169 F4) — anclar por contenido | F5. |
| Patrón health | `backend/api/metrics.py:565-573` (`_cost_center_enabled` + health SIEMPRE 200) | F5. |
| Gotcha `config` vs `config.config` | `backend/api/tickets.py:7401` usa `config.config.STACKY_…` | Todos los archivos nuevos. |
| Corpus RAG del repo (VERIFICADO MUERTO como pipeline) | `Stacky Agents/docs/rag/` existe (`rag_corpus.jsonl`, `schema.json`, `manifest.json`, `README.txt`) pero: (a) **cero consumidores en backend** — `grep -rn "rag_corpus" backend --include=*.py` → 0 matches (verificado: solo lo citan el doc 167 y los archivos del propio corpus); (b) su `schema.json:6` exige campos documentales (`source_file`, `source_span`, `section`, `heading_path`) inaplicables a lecciones; (c) el pipeline vivo `api/docs_rag.py` (DocConsultor con persona fallback del Plan 112 F5, `api/docs_rag.py:32-40`) indexa los `.md` del PROYECTO ACTIVO del operador, no `docs/rag/` del repo | §7: la promoción de lecciones a `docs/rag/` queda FUERA de scope con justificación dura. La inyección directa vía contrato 133 ES el retorno del flywheel. |
| Primitivas UI (Planes 138+162) | `frontend/src/components/ui/index.ts:7-34` (barrel: `Button/StatusChip/Card/SectionHeader/Tabs/Skeleton/Field/Input/Select/Textarea/Checkbox`, `firstErrorFieldId`) | F6 (form manual con primitivas 162). |
| Estados (140) / formato (161) | `components/EmptyState.tsx`, `components/SkeletonList` (NO en el barrel); `services/format.ts:40-118` (`formatDateTime/formatInt/formatPercent`) | F6. |
| ConfirmButton (136) / Toast (135) | `components/ConfirmButton.tsx:23`; `components/Toast.tsx:9-19` | F6 (retirar lección = acción confirmada). |
| Frontend del 167/168/169 | 167 F5/F6: `frontend/src/evolution/model.ts`, `frontend/src/api/endpoints.ts` (namespace `Evolution`), `frontend/src/pages/EvolutionCenterPage.tsx`; 168 F6: `frontend/src/evolution/fitnessModel.ts` + `FitnessSection.tsx`; 169 F5: `optimizerModel.ts` + `OptimizerSection.tsx` | F6: `knowledgeModel.ts` + `KnowledgeSection.tsx`, wiring espejo del FitnessSection. |
| conftest backend | `backend/tests/conftest.py:11` (`STACKY_TEST_MODE`) | Todos los tests; `invoke_local_llm` SIEMPRE monkeypatcheado (cero egress). |

**Ortogonal a (NO tocar, NO depender):** Planes 153/154/156/163/164/165 (pendientes),
Plan 152 (notificaciones), Planes 158/159 (telemetría CLI / catálogo de modelos), el
módulo `api/docs_rag.py`/`services/docs_rag.py` (RAG del proyecto del operador — NO se
toca), `services/memory_store` (memoria colaborativa — sistema hermano, NO se fusiona:
ver §3.9).

---

## 1. Objetivo + KPI / impacto esperado

**Objetivo (1 párrafo):** con 167+168+169, Stacky registra propuestas con gates
humanos, mide fitness objetivo y optimiza prompts — pero **lo aprendido no se acumula
en ningún lado consultable por los agentes**: cada incidencia resuelta muere en su doc
(`docs/incidencias/INC-*.md`), cada mutation lesson del optimizador queda enterrada en
su archive, y la próxima corrida de un agente arranca sin saber nada de eso. El survey
RSI lo dice exacto: *"process-level beats result-level — accumulated procedures are
capital"*. Este plan cierra el ciclo instalando el **flywheel de conocimiento**: (a)
una entidad **Lesson** estructurada (título, cuerpo accionable, scope, trazabilidad
dura al origen, contadores de uso) montada SOBRE el `lessons.jsonl` que el 167 ya
definió (sin tocar su contrato: sidecar de metadata); (b) **cosecha human-in-the-loop
de 3 fuentes** — incidencia resuelta (draft redactado por el LLM local estilo
Reflexion desde el doc + la CAUSA RAIZ del dev resolutor), mutation lessons del 169
con `outcome=="mejoro"` (promoción 1-click), y alta manual — todas entrando como
propuestas `knowledge_note` por la máquina de estados del 167 (NADA nuevo para
aprobar; `maybe_auto_apply` del 167 gobierna el único camino human-on-the-loop); (c)
**el retorno del flywheel**: las lecciones activas cuyo scope matchea se inyectan al
contexto de las próximas corridas VÍA `enrich_blocks` (contrato 133) — un solo seam,
paridad automática en los 3 runtimes, top-N por relevancia TF-IDF, **cap duro de
caracteres**, y byte-idéntico cuando no hay lecciones matching; (d) **cierre medible**:
enlace opcional lección↔caso de eval del 168, contadores de inyección, y KPIs honestos
del flywheel (correlación visible, jamás atribución causal inventada); y (e) **higiene
del corpus**: dedup TF-IDF al crear, retiro 1-click (rollback del 167, reuso total) y
sugerencias LRU-por-uso al exceder el cap. El operador no hace nada nuevo obligatorio:
la cosecha se OFRECE, nunca corre sola.

**KPIs binarios:**

- **KPI-1 — Backward-compatible byte a byte:** un run cuyo agente/proyecto no matchea
  ninguna lección activa (o con `STACKY_KNOWLEDGE_INJECTION_ENABLED=false`) produce
  una lista de bloques IGUAL (`==`) a la de hoy — el injector devuelve la lista de
  entrada sin tocar. Comando:
  `.venv\Scripts\python.exe -m pytest tests/test_knowledge_injection.py -q` → exit 0.
- **KPI-2 — Cap duro de contexto:** con N lecciones enormes activas, el bloque
  `evolution-lessons` nunca supera `STACKY_KNOWLEDGE_INJECT_MAX_CHARS` caracteres de
  `content` y lo declara (`metadata.truncated`). Cubierto por
  `tests/test_knowledge_injection.py` (casos 5-6).
- **KPI-3 — Toda lección pasa por el gate del 167:** la cosecha SOLO emite propuestas
  (`create_proposal` con `artifact_type="knowledge_note"`, `initial_status="pending_review"`)
  y el único auto-apply posible es `evolution_apply.maybe_auto_apply` del 167 (flag
  OFF default). Verificable:
  `grep -n "append_lesson\|lessons.jsonl" "Stacky Agents/backend/services/knowledge_harvest.py"`
  → 0 matches (el harvest NO escribe lecciones: escribe propuestas). Comando:
  `.venv\Scripts\python.exe -m pytest tests/test_knowledge_harvest.py -q` → exit 0.
- **KPI-4 — Degradación declarada sin LLM:** sin `LOCAL_LLM_ENDPOINT` (RuntimeError
  del bridge) `from-incident` igual produce un draft válido con la plantilla
  determinista y `evidence` contiene `"harvest:plantilla"`. Cubierto por
  `tests/test_knowledge_harvest.py` (caso 4).
- **KPI-5 — Cero regresión / cero egress:** con `STACKY_KNOWLEDGE_FLYWHEEL_ENABLED=false`
  todos los endpoints nuevos (salvo `/knowledge/health`) devuelven 404, la sección no
  renderiza y la app queda byte-idéntica; ningún test del plan abre red
  (`invoke_local_llm` SIEMPRE monkeypatcheado). Comandos:
  `.venv\Scripts\python.exe -m pytest tests/test_knowledge_endpoints.py -q` → exit 0 y
  `npx tsc --noEmit` → exit 0.
- **KPI-6 — Contrato reservado del 168 cumplido:** `origin="lesson"` queda agregado a
  `VALID_ORIGINS` de `case_store` (la migración que el 168 §8.3 reservó para este
  plan) y `to-eval-case` crea un caso borrador (`enabled=false`,
  `source_ref="lesson:<id>"`). Comando:
  `.venv\Scripts\python.exe -m pytest tests/test_knowledge_eval_link.py -q` → exit 0.

**KPIs de impacto (proyectados, verificables por observación):**

| Métrica | Hoy | Con el plan |
|---|---|---|
| Conocimiento consultable por agentes nacido de fallos resueltos | 0 (muere en `docs/incidencias/` y en el archive del 169) | lecciones activas inyectadas en el contexto de los 3 runtimes |
| Costo de convertir una incidencia resuelta en aprendizaje durable | reescritura manual en algún doc (nunca pasa) | 1 click (draft redactado solo) + 1 aprobación |
| Uso real de cada lección | invisible | `usage_count` + `last_injected_at` por lección, visibles en el panel |
| Riesgo de prompt bloat por conocimiento acumulado | n/a | cap duro configurable (default 4000 chars) + top-N (default 3) |
| Mutation lessons del 169 con `outcome=="mejoro"` | mueren en `optimizer/lessons.jsonl` | promovibles a lección de conocimiento con 1 click |

---

## 2. Por qué ahora / gap que cierra

### 2.1 Evidencia local

El gap es la ÚLTIMA arista sin cablear del ciclo: el 166 (IMPLEMENTADO) captura fallos
y los resuelve con evidencia (`CAUSA RAIZ` con archivo:línea en el cierre 🚀 del
IncidentDevResolver — `incident_dev_context.py:79-89`); el 167 (PROPUESTO) define
DÓNDE viven las lecciones (`data_dir()/evolution/lessons.jsonl`, aspecto
`knowledge_rag`, apply/rollback reversible) pero NO define quién las produce ni quién
las consume; el 168 (PROPUESTO) sabe EVALUAR una lección (rúbrica
`leccion_conocimiento`, casos seed `knowledge_rag`) y convierte fallos en casos de
eval (`from-incident`), pero un caso de eval NO es una lección (protege contra la
regresión, no enseña el patrón); el 169 (PROPUESTO) EMITE aprendizaje de proceso
(`MutationLesson` con outcome real) pero lo deja en su archive "como materia prima
curable" (169 §8.2). Y del lado del consumo, el contrato 133 (`enrich_blocks`,
IMPLEMENTADO) ya inyecta 15+ tipos de bloque a los 3 runtimes — incluyendo DOS
precedentes de "lecciones" (`rejection-lessons` del Plan 48 `:960` y `stacky-memory`
`:876`) — pero NINGUNO se alimenta del ciclo de incidencias ni del optimizador. Cada
pieza existe; el flywheel no gira. Este plan es el eslabón que falta y es DELIBERADO
que sea el último: sin gobernanza (167) sería autonomía, sin fitness (168) sería
acumulación sin verificación, sin optimizador (169) le faltaría una fuente.

### 2.2 Fundamento de diseño (investigación citada por nombre → decisión concreta)

1. **Survey RSI (arXiv 2607.07663)** — *"process-level beats result-level":
   procedimientos/lecciones/esquemas acumulados son CAPITAL reusable entre problemas
   (capex); filtrar respuestas finales es opex. Skill libraries con acumulación
   persistente = mecanismo deployment-time estrella. Failure mode: self-confirming
   loops* → (a) las lecciones son la unidad de capital de este plan: texto corto
   accionable, versionado, con dueño y trazabilidad; (b) **las lecciones nacen SOLO de
   señal externa verificada**: incidencia con resolución real (CAUSA RAIZ del dev con
   evidencia), mutation lesson con `outcome=="mejoro"` computado por el MOTOR del 169
   (nunca por el LLM — 169 §4.3), o el juicio del propio operador (manual). PROHIBIDO
   cosechar de la opinión de un agente sobre sí mismo (§3.6).
2. **Voyager (NVIDIA/Caltech)** — *skill library incremental: cada habilidad
   verificada se guarda, se indexa y se RECUPERA por relevancia en tareas futuras; el
   agente mejora sin reentrenar porque su biblioteca crece* → la inyección F3 es
   exactamente eso: biblioteca persistente + retrieval por relevancia (TF-IDF
   existente) + top-N acotado. Stacky es mono-operador sin fine-tuning: la biblioteca
   ES el mecanismo de mejora.
3. **Flywheel MAPE-K (arXiv 2510.27051) + práctica Arize/LangChain** — *fallo de
   producción → etiquetado humano → entra al set permanente → menos fallos futuros; el
   loop más maduro convierte CADA incidente resuelto en activo durable (test +
   lección)* → F2.a produce la LECCIÓN y enlaza el CASO DE EVAL que el 168
   `from-incident` ya crea del mismo incidente (§4.4): el par test+lección del
   flywheel completo, cada mitad por su plan.
4. **Reflexion (verbal RL)** — *reflexiones textuales almacenadas en memoria episódica
   mejoran corridas futuras SIN tocar pesos* → el redactor F2 es una reflexión
   dirigida: lee el doc de la incidencia + la resolución verificada y emite "qué
   aprender / cómo aplicarlo" en texto; el retorno es la inyección verbal al contexto.
   Exactamente el mecanismo correcto para un sistema sin fine-tuning.
5. **GEPA / Sakana RSI Lab** — *feedback textual rico > score escalar; eficiencia
   muestral; aprendizaje estructurado de fallos* → la lección conserva el "por qué"
   (causa raíz, no solo la regla); la cosecha es barata (1 llamada al LLM local, USD
   0, con degradación gratis); y el corpus se protege de sí mismo (dedup + cap + LRU)
   en vez de crecer por fuerza bruta.

### 2.3 Delimitación explícita con sistemas hermanos (para que nadie los confunda)

- **`memory_store` (memoria colaborativa, bloque `stacky-memory` `:876`):** memoria
  POR PROYECTO del operador sobre SU dominio (hechos del cliente, decisiones de
  negocio). Las lecciones del 170 son conocimiento del ECOSISTEMA nacido de fallos
  RESUELTOS con gobernanza del 167 (aprobación, fitness, rollback, lineage). No se
  fusionan ni se migran: bloques distintos, stores distintos, ciclos de vida
  distintos.
- **`rejection_lessons` (Plan 48, bloque `rejection-lessons` `:960`):** lecciones de
  RECHAZO de outputs (anti-patrones de publicación). Siguen intactas. El injector
  nuevo es un bloque HERMANO con id propio.
- **Casos de eval del 168:** un caso PROTEGE (falla si el artefacto regresa); una
  lección ENSEÑA (se inyecta al contexto). Este plan enlaza ambos, no los mezcla.

---

## 3. Principios y guardarraíles (NO negociables)

1. **Human-in-the-loop innegociable:** TODA lección entra como propuesta
   `knowledge_note` por la máquina de estados del 167 y requiere aprobación + apply
   del operador. El ÚNICO camino human-on-the-loop es `evolution_apply.maybe_auto_apply`
   del 167 (flag `STACKY_EVOLUTION_AUTO_APPLY_KNOWLEDGE_ENABLED` default OFF,
   excepción dura #1 ya citada allá) — este plan lo LLAMA, no lo duplica ni agrega
   otro. La cosecha NUNCA corre sola: no hay daemon, no hay cron, no hay hook
   post-ejecución; se ofrece contextualmente en el panel (lista de candidatas
   on-mount) y corre solo por click. `closed_loop` sigue PROHIBIDO PARA SIEMPRE
   (167 §3.1).
2. **Cero trabajo extra al operador:** todo default ON (cosecha ofrecida, inyección
   acotada y aditiva, panel visible); los drafts se redactan solos; ningún paso manual
   nuevo obligatorio. Backward-compatible: agente sin lecciones matching = prompt
   **byte-idéntico** al de hoy (KPI-1, criterio binario). Nada env-only: las 5 flags
   por UI (registry dinámico del Arnés).
3. **3 runtimes con paridad:** la inyección viaja por `enrich_blocks` (contrato 133),
   que los 3 runtimes ya llaman (`agent_runner.py:695`,
   `claude_code_cli_runner.py:583`, `codex_cli_runner.py:329`); los CLI renderizan
   todos los blocks vía `build_ticket_context_text` (`:1220`) — cero cambio por
   runner. La cosecha es backend Flask + LLM LOCAL (agnóstico del runtime; precedente
   106/127/167/168). Fallback por ítem: sin LLM local → plantilla determinista (F2);
   sin Plan 169 en el árbol → fuente 2 vacía declarada (F2.b); sin lecciones → bloque
   ausente (F3). Idéntico en los 3.
4. **Cap duro de contexto (no degradar):** el bloque inyectado respeta
   `STACKY_KNOWLEDGE_INJECT_TOP_N` (default 3) y
   `STACKY_KNOWLEDGE_INJECT_MAX_CHARS` (default 4000) — el prompt NO crece sin
   límite. El bloque además participa del presupuesto global F2.4 del 133 con
   prioridad 79 (podable bajo presión extrema, debajo de `stacky-memory` 80). Cero
   pollers nuevos en el panel (riel G9 del 167).
5. **El contrato del 167 es INTOCABLE:** `lessons.jsonl` lo escribe SOLO
   `evolution_apply` del 167 (apply de `knowledge_note`) y la única remoción de líneas
   es su rollback, que quita SOLO la línea de la lección revertida (167 F2, C6).
   Este plan agrega un SIDECAR (`lessons_meta.json`) para los campos nuevos y NUNCA
   escribe `lessons.jsonl` directamente (KPI-3). Retirar una lección = transición
   `rollback` de su propuesta (API del 167, reuso total, auditada en su ledger).
6. **Anti self-confirming (señal externa o nada):** `from-incident` exige incidencia
   con `status=="publicada"` (pasó el ciclo real); el draft cita la CAUSA RAIZ del run
   `incident_dev` completado cuando existe y lo declara en `evidence`;
   `from-optimizer-lesson` exige `outcome=="mejoro"` (computado por el motor 169
   contra fitness del 168, no por el LLM). El LLM local REDACTA, nunca decide qué es
   verdad (espejo de la regla del Analyze 167 §4.6).
7. **Mono-operador sin auth:** cero RBAC; `actor` descriptivo donde el 167 lo pida.
8. **Reusar, no reinventar:** máquina de estados/ledger/auto-apply del 167; casos y
   rúbrica `leccion_conocimiento` del 168; mutation lessons del 169; `rag_retriever`
   (64/115); `enrich_blocks` (133); `incident_store`/`incident_docs` (131/166);
   `pii_masker`; primitivas 138/162; estados 140; formato 161; ConfirmButton 136;
   Toast 135.
9. **Anti-contaminación de docs:** NADA de este plan escribe bajo `docs/` (ni `.md` ni
   `.jsonl`). Las lecciones viven en `data_dir()` (runtime data). La promoción al
   corpus `docs/rag/` queda fuera de scope con justificación verificada (§7.1).

### Gotchas del repo que el implementador DEBE respetar (verificadas)

- **G1 — `config` vs `config.config`:** en archivos nuevos usar SIEMPRE
  `from config import config as _cfg` y `getattr(_cfg, "FLAG", default)` (espejo de
  `api/metrics.py:565-566`; gotcha recurrente de `api/tickets.py:7401`).
- **G2 — Ratchet de tests:** los 6 `test_*.py` nuevos DEBEN agregarse a
  `HARNESS_TEST_FILES` en `backend/scripts/run_harness_tests.sh` (`:20`; zona
  reciente `:458-460`) **y** `backend/scripts/run_harness_tests.ps1` (`:412-414`), o
  el meta-test del Plan 49 se pone rojo.
- **G3 — Aristas `requires=`:** cada flag con `requires=` DEBE tener su arista en
  `_REQUIRES_MAP_FROZEN` (`backend/tests/test_harness_flags_requires.py:120`).
- **G4 — `_CURATED_DEFAULTS_ON`:** cada flag **bool** con default efectivo ON va al
  set de `backend/tests/test_harness_flags.py:467`; las `type="int"` NO.
- **G5 — venv y tests por archivo:** backend con `.venv`
  (`.venv\Scripts\python.exe -m pytest tests/<archivo> -q`), NUNCA la suite completa
  (contaminación cross-run conocida). Frontend `npx vitest run src/<archivo>`, por
  archivo.
- **G6 — Ratchet UI cero inline-style:** los `.tsx` nuevos tienen alcance 0 en
  `uiDebtRatchet`: TODO estilo va al `.module.css`; prohibido `style={{}}` en
  `KnowledgeSection.tsx`.
- **G7 — `_CATEGORY_KEYS` obligatorio:** toda flag nueva va también al dict
  `_CATEGORY_KEYS` (`services/harness_flags.py:117`; nota normativa `:331`). Ancla:
  la tupla de `:265`, INMEDIATAMENTE después de las 5 entradas del 169 (ubicar por el
  literal `STACKY_EVOLUTION_OPTIMIZER_MIN_MARGIN_PCT`).
- **G8 — `requires` profundidad 1:** las 5 aristas apuntan al ROOT del 167
  `STACKY_EVOLUTION_CENTER_ENABLED` (precedente normativo `harness_flags.py:3336`,
  regla heredada 167/168/169). El gate compuesto `_knowledge_enabled()` va EN CÓDIGO
  (§4.6), no en el grafo de flags.
- **G9 — Sin pollers nuevos:** cero `setInterval`/`refetchInterval` en el frontend
  nuevo. Carga on-mount/on-expand + botones + refresh post-acción.
- **G10 — DOS `lessons.jsonl` distintos (colisión de nombres REAL):**
  `data_dir()/evolution/lessons.jsonl` = **lecciones de conocimiento** aplicadas
  (167 F2); `data_dir()/evolution/optimizer/lessons.jsonl` = **mutation lessons** del
  optimizador (169 §4.1). Este plan LEE ambos (el primero como fuente de verdad de
  activas; el segundo como fuente de cosecha vía
  `evolution_optimizer_store.read_lessons_tail`) y NO ESCRIBE ninguno. Nombrarlos
  SIEMPRE con su prefijo en código y tests.
- **G11 — Corpus bajo `docs/`:** NADA de este plan escribe bajo `docs/` (`doc_indexer`
  escanea `docs/**/*.md`; y el corpus `docs/rag/` no tiene consumidor runtime — tabla
  de dependencias). Las lecciones viven en `data_dir()`.
- **G12 — `harness_defaults.env` NO se toca a mano** (lo regenera
  `scripts/export_harness_defaults.py` — riel del Plan 133 §3.6).
- **G13 — WIP ajeno / sesiones paralelas:** antes de editar cada archivo caliente
  (`config.py`, `harness_flags.py`, `harness_flags_help.py`, `api/__init__.py`,
  `context_enrichment.py`, `evals/case_store.py`, `endpoints.ts`,
  `EvolutionCenterPage.tsx`, `fitnessModel.ts`, scripts de ratchet): `git status --
  "<ruta>"`; staging quirúrgico por pathspec; PROHIBIDO `git stash/reset/checkout`.
  OJO especial: `runtime_paths.py` y `run_preflight.py` tienen WIP ajeno HOY — no
  tocarlos (este plan no los edita). El implementador NO commitea (lo hace el
  orquestador).
- **G14 — Prosa vs gates propios:** ninguna cadena/comentario/docstring del código
  nuevo debe matchear espuriamente los greps de criterio de este plan (gotcha
  recurrido 6×: el gate siempre gana; se reescribe la prosa). En particular: el
  módulo `knowledge_harvest.py` NO debe contener los literales `append_lesson` ni
  `lessons.jsonl` ni siquiera en comentarios (KPI-3); y `api/evolution_knowledge.py`
  NO debe contener el literal del registrador de contadores (`record_` + `injection`)
  ni siquiera en comentarios/docstrings (criterio F5 del preview dry-run).
- **G15 — PII TOTAL (C1):** TODO insumo textual externo que entre al draft —
  texto del intake de la incidencia, contenido del doc (`doc_path`) Y output de
  ejecución — pasa por `services.pii_masker.redact_irreversible` ANTES de usarse
  (mismo riel que `evals/harvest.py:95`). Además, defensa en profundidad: el draft
  final (`title` y `body`, TAMBIÉN el de `harvest_manual` y el determinista del
  optimizador) pasa por `redact_irreversible` inmediatamente ANTES de
  `create_proposal`. Razón: una lección aprobada se inyecta a TODOS los prompts
  futuros — un secreto que se cuele se amplifica en cada corrida.
- **G16 — Deploy frozen tolerante:** `doc_path` de una incidencia puede no existir en
  disco (deploy congelado, o doc en el fallback `data_dir()/incident_docs`). TODA
  lectura de archivos es tolerante (ausente/ilegible → se omite esa parte del insumo,
  NUNCA excepción) — patrón `incident_docs.py:29-35`.
- **G17 — Citas a docs hermanos (C4):** los docs 167/168/169 son v1 y el pipeline los
  reescribirá a v2: sus números de línea (`doc 167:739`, `doc 168:1356`, `doc 169:803`,
  etc.) son ORIENTATIVOS. Toda cita a un plan hermano ancla por §sección + símbolo con
  nombre (`maybe_auto_apply`, `VALID_ORIGINS`, `read_lessons_tail`…), nunca por línea.
  La verificación vinculante es el pre-check de símbolos EN CÓDIGO del §5: si un símbolo
  consumido no existe en el archivo implementado, DETENERSE y reportar drift de contrato
  (no "adaptarse" en silencio).

---

## 4. Contratos congelados (van tal cual al código)

### 4.1 Layout de persistencia (bajo `data_dir()/evolution/`)

```
data_dir()/evolution/
  lessons.jsonl        # DEL 167 — fuente de verdad de lecciones ACTIVAS (este plan solo LEE)
  lessons_meta.json    # NUEVO — sidecar: dict {lesson_id: LessonMeta} (este plan lo escribe)
  proposals.json       # DEL 167 — las propuestas knowledge_note (este plan crea vía evolution_store)
  optimizer/lessons.jsonl  # DEL 169 — mutation lessons (este plan solo LEE, tolerante)
```

Reglas duras (espejo 167 §4.1): el store llama `runtime_paths.data_dir()` **en cada
operación** (sin cache de módulo — los tests lo monkeypatchean); lecturas tolerantes
(ausente/corrupto → vacío); escrituras del sidecar bajo
`_KNOWLEDGE_LOCK = threading.Lock()`; `mkdir(parents=True, exist_ok=True)`.
**Regla de oro:** `lessons.jsonl` y `optimizer/lessons.jsonl` son READ-ONLY para todo
código de este plan (G10, KPI-3).

### 4.2 `LessonMeta` (una entrada del dict de `lessons_meta.json`) y `Lesson` (vista compuesta)

```json
{
  "lesson_id": "prop-<uuid4-hex>",
  "title": "…",
  "scope": {"agent_types": [], "projects": [], "tags": []},
  "source": {"kind": "incident | optimizer_lesson | manual", "ref": "inc-… | les-… | null"},
  "eval_case_id": null,
  "usage_count": 0,
  "last_injected_at": null,
  "created_at": "<iso utc>", "updated_at": "<iso utc>"
}
```

Reglas congeladas:
- **`lesson_id` == id de la propuesta del 167** (su F2 escribe la línea de
  `lessons.jsonl` con `lesson_id = p["id"]` — doc 167:755). La meta se crea EN LA
  COSECHA (junto con la propuesta) con el MISMO id: cuando la propuesta se aplica, la
  línea y la meta ya se corresponden solas. Cero migración.
- `scope`: listas de strings casefold-normalizadas. **Lista vacía = global** (matchea
  todo). `agent_types` se valida SUAVE contra `agents.registry` (`agents/__init__.py:14`):
  un type desconocido produce warning en la respuesta, no error (forward-compat).
  `tags` NO participa del matching de runs (es organización/búsqueda del panel).
- `source.kind` ∈ `("incident", "optimizer_lesson", "manual")`; `ref` es el id de la
  fuente o `null` para manual.
- **Semántica de `usage_count` (C3, congelada):** cantidad de veces que la lección fue
  **SELECCIONADA para inyección** por el injector F3. Con el presupuesto global F2.4 del
  133 activo (OFF default), el bloque puede podarse DESPUÉS de contar: seleccionada ≠
  garantizada en el prompt final. El panel la rotula "Seleccionada Nx" (F6) — nunca
  "usada" ni "leída". Misma semántica para `last_injected_at`.
- **Backward-compat:** una línea de `lessons.jsonl` SIN meta (aplicada antes de este
  plan) es válida: la vista compuesta le asigna defaults —
  `title` = primera línea de `text` (cap 80 chars), `scope` global, `usage_count` 0,
  `source` `{"kind": "manual", "ref": null}`.

La **vista compuesta `Lesson`** que devuelve el store (F1 `list_lessons`):

```json
{
  "lesson_id": "…", "aspect_id": "knowledge_rag", "text": "…", "origin": "…",
  "created_at": "…",
  "active": true,
  "title": "…", "scope": {…}, "source": {…}, "eval_case_id": null,
  "usage_count": 0, "last_injected_at": null
}
```

`active` = la línea existe en `lessons.jsonl` (el rollback del 167 la remueve →
`active=false` y la meta se CONSERVA como historial de retiradas).

### 4.3 Scope matching y ranking (funciones puras, F1)

```python
def lesson_matches(scope: dict, *, agent_type: str | None, project_name: str | None) -> bool:
    # agent_types vacío O agent_type (casefold) en la lista → matchea eje agente.
    # projects vacío O project_name (casefold) en la lista → matchea eje proyecto.
    # agent_type/project_name None cuentan como "matchea solo contra lista vacía".
    # Resultado = AND de ambos ejes. tags NO participa.
```

Ranking top-N (F3): si hay `query` (título+descripción del ticket, mismo insumo que
`_rag_query` de `context_enrichment.py:96`) → `rag_retriever.build_index` sobre las
matcheadas (`RagChunk(id=lesson_id, text=title + "\n" + text, payload=lesson)`) +
`retrieve(index, query, top_k=N)`; las que no entren al índice o si `retrieve`
devuelve vacío → fallback determinista `created_at` DESC. Sin query → directamente
`created_at` DESC. Nunca lanza (contrato de `rag_retriever:75`).

### 4.4 Evidencia trazable de las propuestas cosechadas (strings congelados en `evidence[]`)

| Fuente | `evidence` (orden congelado; los opcionales solo si existen) |
|---|---|
| `from-incident` | `["incident:<incident_id>", "harvest:llm_local" \| "harvest:plantilla", "execution:<exec_id>"?, "eval_case:<case_id>"?]` |
| `from-optimizer-lesson` | `["optimizer_lesson:<les_id>", "optimizer_run:<run_id>", "harvest:promocion_determinista"]` |
| `manual` | `["harvest:manual"]` |

`origin` de la propuesta (VALID_ORIGINS del 167, sin tocar): `from-incident` →
`"agent"` (la redactó un no-humano); `from-optimizer-lesson` → `"optimizer"`;
`manual` → `"manual"`.

**Set de fuentes ya cosechadas (C2, determinista y robusto):** una propuesta cuenta
como "cosecha" SOLO si (i) su `evidence` contiene AL MENOS un item con prefijo
`"harvest:"` — los markers `harvest:*` son EXCLUSIVOS de este plan; ningún plan hermano
los emite (el MAPE del 167 crea propuestas `knowledge_rag` por su regla R-A3 SIN esos
markers, y así no contaminan este set) — y (ii) `p["status"] != "rejected"` (un draft
rechazado LIBERA la fuente: el operador puede re-cosechar). Pseudocódigo congelado:

```python
harvested = {
    e.split(":", 1)[1]
    for p in evolution_store.list_proposals(aspect_id="knowledge_rag")
    if p.get("status") != "rejected"
    and any(str(x).startswith("harvest:") for x in (p.get("evidence") or []))
    for e in (p.get("evidence") or [])
    if isinstance(e, str) and e.startswith("incident:")
}
```

(ídem para `optimizer_lesson:` en `harvested_optimizer_lesson_ids`).

### 4.5 Bloque de contexto `evolution-lessons` (el retorno del flywheel, F3)

```json
{"kind": "text", "id": "evolution-lessons",
 "title": "Lecciones aprendidas (Stacky) — <n>",
 "content": "LECCIONES APRENDIDAS DE INCIDENCIAS RESUELTAS Y MEJORAS VERIFICADAS (aplicalas cuando toquen tu tarea; no las transcribas en el output; si dos lecciones se contradicen, priorizá la de número más bajo y anotá el conflicto en tu resumen):\n1. [<title>] <text>\n2. …",
 "metadata": {"lesson_ids": ["prop-…"], "truncated": false}}
```

Reglas congeladas:
- Prioridad: entrada nueva `"evolution-lessons": 79` en `_BLOCK_PRIORITY`
  (`context_enrichment.py:366` — entre `stacky-memory` 80 y `modal_user_input` 78).
- Posición: APPEND al final de la lista (patrón `_inject_process_discipline_block`
  `:780`), NO prepend — las lecciones informan, no mandan.
- Cap: se agregan lecciones en el orden del ranking mientras
  `len(content) + len(próxima_entrada) <= MAX_CHARS`; la primera que no entra corta
  el loop (`truncated=true`). Caso borde: si la PRIMERA entrada sola excede el cap,
  se trunca a `MAX_CHARS - len(header)` con sufijo `"…"` y `truncated=true` (el
  bloque nunca sale vacío si hubo al menos 1 matcheada).
- Sin lecciones matching / flag OFF / store vacío → **se devuelve la lista de entrada
  tal cual** (identidad — KPI-1).
- **Armado = función PURA `build_lessons_block` (C8/ADICIÓN):** la selección+armado del
  bloque vive en `knowledge_store.build_lessons_block(lessons, query, top_n, max_chars)
  -> dict | None` (None si `lessons` vacío). El injector F3 la llama y DESPUÉS registra
  contadores; el preview (§4.8) la llama y NO registra. Un solo armador, dos consumidores.
- Contadores: tras armar el bloque, `knowledge_store.record_injection(lesson_ids)`
  best-effort (excepción → warning en log, el run sigue). Semántica C3 (§4.2):
  "seleccionada", no "garantizada en el prompt" — el budget F2.4 del 133 corre después.

### 4.6 Gate compuesto y helper de flags (en código, G8)

```python
def _knowledge_enabled() -> bool:
    from config import config as _cfg
    return bool(getattr(_cfg, "STACKY_EVOLUTION_CENTER_ENABLED", False)) and \
           bool(getattr(_cfg, "STACKY_KNOWLEDGE_FLYWHEEL_ENABLED", False))
```

La INYECCIÓN (F3) exige además `STACKY_KNOWLEDGE_INJECTION_ENABLED` (kill-switch
independiente: si una lección rompe prompts, se apaga la inyección sin perder panel
ni cosecha).

### 4.7 Draft del redactor (F2): prompt del LLM local y plantilla determinista

**Constantes con nombre (en `knowledge_harvest.py`):**

```python
_HARVEST_MAX_INPUT_CHARS = 24000   # cap del insumo total al LLM (~6k tokens, len//4 — convención 167/169)
_TITLE_MAX = 80
_BODY_MAX = 1200
_HARVEST_SYSTEM_PROMPT = (
    "Sos el destilador de lecciones de un sistema de agentes. Recibís el material de una "
    "incidencia RESUELTA (reporte + causa raíz verificada). Redactá UNA lección corta y "
    "accionable para que futuros agentes no repitan el problema. Respondé SOLO un JSON: "
    '{"title": "<max 80 chars>", "body": "<max 1200 chars: qué pasó, causa raíz, regla '
    'accionable para el futuro>", "tags": ["…"]}. Nada fuera del JSON. No inventes: usá '
    "solo lo que el material afirma."
)
```

Parse tolerante de la respuesta: strip de fences ``` → primer bloque `{…}` balanceado
→ `json.loads` → clamp `title[:_TITLE_MAX]`, `body[:_BODY_MAX]`, `tags` lista de
strings (max 6). Cualquier fallo (RuntimeError del bridge, timeout, parse, claves
faltantes) → **plantilla determinista**:

```python
def _deterministic_draft(incident: dict, root_cause: str | None) -> dict:
    # title = ("Lección: " + (incident.get("title") or incident["id"]))[:_TITLE_MAX]
    # body  = líneas deterministas:
    #   "Incidencia <id> (<created_at>)."
    #   "Reporte: <primeras 300 chars de incident['text']>"
    #   + ("Causa raíz verificada: <root_cause[:500]>" si root_cause)
    #   + "Regla: completá la regla accionable al aprobar esta lección."
    # tags = []
```

`root_cause` se extrae DETERMINISTA del output PII-masked del run `incident_dev`:
`re.search(r"CAUSA RAIZ\s*:?\s*(.+?)(?=\n\s*(?:ARCHIVOS MODIFICADOS|RESUMEN DEL FIX|$))", output, re.S | re.I)`
(secciones literales del cierre 🚀 — `incident_dev_context.py:81-86`); sin match →
`None` (tolerante).

### 4.8 Contratos HTTP (blueprint `evolution_knowledge`, url_prefix `/evolution` → `/api/evolution/...`)

Flag OFF → 404 literal
`{"ok": false, "error": "knowledge_disabled", "message": "El flywheel de conocimiento está deshabilitado (STACKY_KNOWLEDGE_FLYWHEEL_ENABLED)."}`
(salvo `/knowledge/health`, SIEMPRE 200 — patrón `api/metrics.py:565-573`).

| Método y ruta | ON |
|---|---|
| `GET /api/evolution/knowledge/health` | 200 `{"ok": true, "flag_enabled": <bool>, "injection_enabled": <bool>, "llm_configured": <bool LOCAL_LLM_ENDPOINT no vacío>}` (también con flag OFF) |
| `GET /api/evolution/knowledge/lessons?include_retired=` | 200 `{"ok": true, "lessons": [Lesson §4.2], "cap": <int>, "over_cap": <bool>}` (activas primero, `created_at` DESC; `include_retired` = `"true"`/ausente) |
| `PATCH /api/evolution/knowledge/lessons/<lid>` body `{"title"?: "…", "scope"?: {…}}` | 200 lección actualizada \| 404 `lesson_not_found` \| 400 `invalid_payload` (solo `title`/`scope` patcheables; el TEXTO de una lección aplicada NO se edita — se retira y se re-cosecha, §7) |
| `GET /api/evolution/knowledge/harvest/candidates` | 200 `{"ok": true, "incidents": [{"incident_id", "title", "created_at", "has_dev_run": <bool>, "already_harvested": <bool>}], "optimizer_lessons": [{"lesson_id", "run_id", "aspect_key", "text", "delta", "already_harvested": <bool>}]}` — incidencias `status=="publicada"` (las `already_harvested` van al final); mutation lessons `outcome=="mejoro"` vía `read_lessons_tail(limit=50)` (sin 169 → `[]`) |
| `POST /api/evolution/knowledge/harvest/from-incident` body `{"incident_id": "…", "force": false}` | 201 `{"ok": true, "proposal": {…167 §4.3}, "auto_applied": <bool>, "duplicates": []}` \| 404 `incident_not_found` \| 409 `incident_not_harvestable` (status ≠ `publicada`; message incluye el status) \| 409 `duplicate_suspect` (§4.9; se supera con `force=true`) |
| `POST /api/evolution/knowledge/harvest/from-optimizer-lesson` body `{"lesson_id": "…", "force": false}` | 201 ídem \| 404 `optimizer_lesson_not_found` \| 409 `lesson_outcome_invalido` (outcome ≠ `mejoro`) \| 409 `duplicate_suspect` \| 409 `optimizer_unavailable` (Plan 169 ausente) |
| `POST /api/evolution/knowledge/harvest/manual` body `{"title": "…", "body": "…", "scope"?: {…}, "force": false}` | 201 ídem \| 400 `invalid_payload` (title/body vacíos o sobre límites) \| 409 `duplicate_suspect` |
| `POST /api/evolution/knowledge/lessons/<lid>/to-eval-case` | 201 `{"ok": true, "case": {EvalCase 168 §4.2}}` \| 404 `lesson_not_found` \| 409 `lesson_not_active` \| 409 `case_already_exists` (ya hay caso con `source_ref=="lesson:<lid>"`) |
| `GET /api/evolution/knowledge/overview` | 200 shape §4.10 |
| `GET /api/evolution/knowledge/injection-preview?agent_type=<t>&project=<p>&query=<q>` | **[ADICIÓN ARQUITECTO]** 200 `{"ok": true, "block": {shape §4.5} \| null, "matched_count": <int>}` — dry-run EXACTO del injector F3 (mismos flags TOP_N/MAX_CHARS, mismo ranking) pero SIN `record_injection` y SIN exigir `STACKY_KNOWLEDGE_INJECTION_ENABLED` (el operador puede previsualizar con la inyección apagada); `block=null` si nada matchea. `query` opcional (simula título+descripción de un ticket) |

**Retiro de lección:** SIN endpoint nuevo — la UI llama
`POST /api/evolution/proposals/<lesson_id>/transition` con
`{"action": "rollback", "note": "retiro de lección desde el panel de conocimiento"}`
(API del 167 §4.8; `lesson_id` == proposal id). El 167 remueve la línea de
`lessons.jsonl` y audita en su ledger. La respuesta de la cosecha (`201`) incluye la
propuesta completa para que el panel deep-linkee `?proposal=<id>` (riel G10 del 167).

### 4.9 Dedup en la cosecha (constantes con nombre, F1)

```python
_DEDUP_SIMILARITY_THRESHOLD = 0.55   # coseno TF-IDF sobre title+text de activas
def find_similar(candidate_title: str, candidate_body: str) -> list[dict]
    # 1) match EXACTO de título normalizado (casefold + colapso de espacios) → score 1.0
    # 2) rag_retriever.build_index sobre activas + retrieve(index, candidate_title+"\n"+candidate_body, top_k=3)
    #    → conserva los de score >= _DEDUP_SIMILARITY_THRESHOLD
    # Devuelve [{"lesson_id", "title", "score"}] orden score DESC; [] si no hay activas.
```

`duplicate_suspect` (409) devuelve `{"ok": false, "error": "duplicate_suspect",
"message": "Ya existe una lección muy similar.", "duplicates": [ …find_similar… ]}`.
Con `force=true` la cosecha procede igual y `duplicates` viaja en el 201 (el operador
decide — human-in-the-loop, no auto-rechazo).

### 4.10 `overview` — KPIs del flywheel (shape congelado)

```json
{"ok": true,
 "lessons": {"active": 0, "retired": 0, "cap": 200, "over_cap": false},
 "coverage": {"agents_total": 12, "agents_with_lessons": 0,
              "by_agent_type": {"developer": 0}},
 "flywheel": {"incidents_published": 0, "incidents_harvested": 0,
              "eval_cases_from_incidents": 0, "eval_cases_from_lessons": 0,
              "optimizer_lessons_mejoro": 0, "optimizer_lessons_promoted": 0},
 "usage": {"injections_total": 0, "never_injected": 0,
           "top": [{"lesson_id": "…", "title": "…", "usage_count": 0}]},
 "fitness_knowledge": {"latest_score": null, "baseline_score": null,
                       "delta": null, "runs": 0},
 "retire_suggestions": [{"lesson_id": "…", "title": "…", "usage_count": 0,
                          "created_at": "…", "reason": "lru_por_uso | sin_uso_prolongado"}]}
```

Fuentes (cada una en su propio `try/except` tolerante — una fuente caída produce su
clave con valores vacíos/null, el overview SIEMPRE responde 200):
`coverage` itera `agents.registry` (scope global cuenta para todos los types);
`flywheel.eval_cases_*` cuenta `case_store.list_cases()` con `origin=="incident"` /
`origin=="lesson"`; `optimizer_lessons_*` vía `read_lessons_tail(limit=200)` (sin 169
→ 0); `fitness_knowledge` lee `case_store.read_runs_tail` filtrando
`aspect_key=="knowledge_rag"` y `trigger != "candidate"` (símbolo citado por el 169
doc:579): `latest_score` = run más nuevo, `baseline_score` = más viejo del tail,
`delta` = diferencia redondeada a 4 decimales (correlación HONESTA: el panel la
rotula "correlación, no causalidad" — §F6); `retire_suggestions` (C9) = unión de DOS reglas, ambas **sugerencia, NUNCA
auto-borrado**: (1) si `active > cap`: las `active - cap` activas con menor
`(usage_count, created_at)` ascendente, `reason` literal `"lru_por_uso"`; (2) SIEMPRE
(independiente del cap): activas con `usage_count == 0` y `created_at` anterior a hoy
menos `_STALE_DAYS` (constante `_STALE_DAYS = 60` en `knowledge_store.py`), `reason`
literal `"sin_uso_prolongado"`. Una lección que cae en ambas aparece UNA vez con
`"lru_por_uso"` (precedencia regla 1); orden final: `(usage_count, created_at)` asc.

---

## 5. Fases

Orden por dependencia: **F0 → F1 → F2 → F3 → F4 → F5 → F6 → F7**. Pre-check GLOBAL
antes de F0, en DOS niveles (C4/G17):

**(1) Existencia (ambos obligatorios):**
`test -f "Stacky Agents/backend/services/evolution_store.py"` (Plan 167) y
`test -f "Stacky Agents/backend/evals/case_store.py"` (Plan 168) — si falta
cualquiera, DETENERSE y reportar "Plan 167/168 no implementado". El Plan 169 NO es
pre-check (dependencia blanda: F2.b degrada declaradamente).

**(2) Símbolos del contrato EN CÓDIGO (todos deben dar ≥ 1 match; si alguno da 0,
DETENERSE y reportar "drift de contrato 167/168: <símbolo> ausente"):**

```bash
grep -c "def create_proposal" "Stacky Agents/backend/services/evolution_store.py"
grep -c "def update_proposal_fields" "Stacky Agents/backend/services/evolution_store.py"
grep -c "def list_proposals" "Stacky Agents/backend/services/evolution_store.py"
grep -c "def maybe_auto_apply" "Stacky Agents/backend/services/evolution_apply.py"
grep -c "VALID_ORIGINS" "Stacky Agents/backend/evals/case_store.py"
grep -c "def create_case" "Stacky Agents/backend/evals/case_store.py"
grep -c "def read_runs_tail" "Stacky Agents/backend/evals/case_store.py"
```

> **Comandos de test:** backend desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend`
> con `.venv\Scripts\python.exe -m pytest tests/<archivo> -q` (Git Bash:
> `cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/<archivo> -q`).
> Frontend desde `Stacky Agents/frontend` con `npx vitest run src/<archivo>`. SIEMPRE
> por archivo (G5). **REGLA DURA de red:** todo test que alcance el camino del
> redactor monkeypatchea `copilot_bridge.invoke_local_llm` — ningún test del plan
> abre sockets.

---

### F0 — Flags del flywheel (patrón triple)

**Objetivo (1 frase):** declarar las 5 configuraciones del flywheel con el patrón
triple, editables por UI, nada env-only.
**Valor:** kill-switch por UI del flywheel completo Y de la inyección por separado;
N/cap/tope gobernados desde el panel del Arnés.

**Archivos a editar (5):** `backend/config.py`, `backend/services/harness_flags.py`,
`backend/services/harness_flags_help.py`, `backend/tests/test_harness_flags.py`
(set `:467`), `backend/tests/test_harness_flags_requires.py` (mapa `:120`).

**Flags (nombres EXACTOS), defaults y excepciones:**

| Flag | type | Default | `requires=` | Excepción dura |
|---|---|---|---|---|
| `STACKY_KNOWLEDGE_FLYWHEEL_ENABLED` | bool | **ON** | `STACKY_EVOLUTION_CENTER_ENABLED` | ninguna (panel + cosecha on-click; nada corre solo; el único auto-apply es el del 167 con SU flag OFF) |
| `STACKY_KNOWLEDGE_INJECTION_ENABLED` | bool | **ON** | `STACKY_EVOLUTION_CENTER_ENABLED` | ninguna (inyección aditiva y acotada; kill-switch independiente si algo rompe prompts) |
| `STACKY_KNOWLEDGE_INJECT_TOP_N` | int | `3` | `STACKY_EVOLUTION_CENTER_ENABLED` | ninguna (clamp en código 1..10) |
| `STACKY_KNOWLEDGE_INJECT_MAX_CHARS` | int | `4000` | `STACKY_EVOLUTION_CENTER_ENABLED` | ninguna (clamp en código 500..20000) |
| `STACKY_KNOWLEDGE_MAX_LESSONS` | int | `200` | `STACKY_EVOLUTION_CENTER_ENABLED` | ninguna (cap SUGERENTE: dispara sugerencias LRU, jamás borra) |

(G8: las 5 aristas al ROOT `STACKY_EVOLUTION_CENTER_ENABLED`, profundidad 1.)

**Diff ilustrativo — `config.py`** (insertar inmediatamente DESPUÉS del bloque del
Plan 169 — ubicar por el literal `STACKY_EVOLUTION_OPTIMIZER_MIN_MARGIN_PCT`):

```python
    # ── Plan 170 — Flywheel de conocimiento (serie auto-mejora recursiva 4/4) ──
    # Lecciones estructuradas: cosecha con aprobacion humana e inyeccion acotada
    # al contexto de agentes. Default ON: la cosecha es on-click y la inyeccion
    # es aditiva con tope duro de caracteres.
    STACKY_KNOWLEDGE_FLYWHEEL_ENABLED: bool = os.getenv(
        "STACKY_KNOWLEDGE_FLYWHEEL_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # Kill-switch independiente de la inyeccion de lecciones al contexto.
    STACKY_KNOWLEDGE_INJECTION_ENABLED: bool = os.getenv(
        "STACKY_KNOWLEDGE_INJECTION_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # Cuantas lecciones (top por relevancia) entran por corrida.
    STACKY_KNOWLEDGE_INJECT_TOP_N: int = int(os.getenv(
        "STACKY_KNOWLEDGE_INJECT_TOP_N", "3"
    ) or "3")

    # Tope duro de caracteres del bloque de lecciones en el prompt.
    STACKY_KNOWLEDGE_INJECT_MAX_CHARS: int = int(os.getenv(
        "STACKY_KNOWLEDGE_INJECT_MAX_CHARS", "4000"
    ) or "4000")

    # Cap del corpus: al excederse, el panel sugiere retiros LRU (nunca borra).
    STACKY_KNOWLEDGE_MAX_LESSONS: int = int(os.getenv(
        "STACKY_KNOWLEDGE_MAX_LESSONS", "200"
    ) or "200")
```

**`harness_flags.py` — 2 toques:** (a) `_CATEGORY_KEYS`: en la MISMA tupla de `:265`,
inmediatamente después de las 5 entradas del Plan 169 (ubicar por
`"STACKY_EVOLUTION_OPTIMIZER_MIN_MARGIN_PCT"`):

```python
        "STACKY_KNOWLEDGE_FLYWHEEL_ENABLED",    # Plan 170 — flywheel de conocimiento
        "STACKY_KNOWLEDGE_INJECTION_ENABLED",   # Plan 170 — inyeccion de lecciones
        "STACKY_KNOWLEDGE_INJECT_TOP_N",        # Plan 170 — top-N por corrida
        "STACKY_KNOWLEDGE_INJECT_MAX_CHARS",    # Plan 170 — tope de caracteres
        "STACKY_KNOWLEDGE_MAX_LESSONS",         # Plan 170 — cap sugerente del corpus
```

(b) `FLAG_REGISTRY`: 5 `FlagSpec` inmediatamente DESPUÉS de los 5 del 169 (ubicar por
`key="STACKY_EVOLUTION_OPTIMIZER_MIN_MARGIN_PCT"`), `group="global"`:

```python
    FlagSpec(
        key="STACKY_KNOWLEDGE_FLYWHEEL_ENABLED",
        type="bool", default=True,
        label="Flywheel de conocimiento",
        description="Lecciones aprendidas de incidencias resueltas y mejoras verificadas: cosecha con tu aprobación, panel con uso e impacto, y retiro con un click.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_KNOWLEDGE_INJECTION_ENABLED",
        type="bool", default=True,
        label="Inyectar lecciones al contexto de agentes",
        description="Agrega a cada corrida un bloque acotado con las lecciones activas que aplican al agente y al proyecto. Con tope duro de tamaño; apagalo si un prompt se comporta raro.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_KNOWLEDGE_INJECT_TOP_N",
        type="int", default=3,
        label="Lecciones por corrida (top-N)",
        description="Cuántas lecciones, ordenadas por relevancia al ticket, entran al contexto de una corrida.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_KNOWLEDGE_INJECT_MAX_CHARS",
        type="int", default=4000,
        label="Tope de caracteres del bloque de lecciones",
        description="Límite duro del tamaño del bloque de lecciones en el prompt. El prompt nunca crece sin control por conocimiento acumulado.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_KNOWLEDGE_MAX_LESSONS",
        type="int", default=200,
        label="Cap del corpus de lecciones",
        description="Al superarlo, el panel sugiere retirar las lecciones menos usadas (LRU). Solo sugiere: retirar siempre es tu decisión.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
```

**`harness_flags_help.py`:** 5 entradas `PlainHelp` (espejo del formato de las del
169, insertadas a continuación), lenguaje llano: qué es, efecto ON, efecto OFF,
ejemplo. La de `STACKY_KNOWLEDGE_INJECTION_ENABLED` DEBE decir en `off_effect` que
"las corridas vuelven a salir exactamente como antes de este plan".

**Meta-tests:** en `_CURATED_DEFAULTS_ON` (`test_harness_flags.py:467`) agregar SOLO
las 2 bool: `STACKY_KNOWLEDGE_FLYWHEEL_ENABLED`, `STACKY_KNOWLEDGE_INJECTION_ENABLED`
(G4). En `_REQUIRES_MAP_FROZEN` (`test_harness_flags_requires.py:120`) las 5 aristas:

```python
    "STACKY_KNOWLEDGE_FLYWHEEL_ENABLED": "STACKY_EVOLUTION_CENTER_ENABLED",
    "STACKY_KNOWLEDGE_INJECTION_ENABLED": "STACKY_EVOLUTION_CENTER_ENABLED",
    "STACKY_KNOWLEDGE_INJECT_TOP_N": "STACKY_EVOLUTION_CENTER_ENABLED",
    "STACKY_KNOWLEDGE_INJECT_MAX_CHARS": "STACKY_EVOLUTION_CENTER_ENABLED",
    "STACKY_KNOWLEDGE_MAX_LESSONS": "STACKY_EVOLUTION_CENTER_ENABLED",
```

**Tests PRIMERO (TDD):** crear `backend/tests/test_knowledge_flags.py` (espejo
estructural de `tests/test_fitness_flags.py` del 168 F0). 8 casos:
1. `test_flywheel_flag_en_registry` — FlagSpec existe, `type=="bool"`, `default is True`, `requires=="STACKY_EVOLUTION_CENTER_ENABLED"`.
2. `test_injection_flag_en_registry` — ídem para INJECTION.
3. `test_top_n_flag_int` — `type=="int"`, `default==3`.
4. `test_max_chars_flag_int` — `type=="int"`, `default==4000`.
5. `test_max_lessons_flag_int` — `type=="int"`, `default==200`.
6. `test_las_5_estan_categorizadas` — las 5 keys en algún valor de `_CATEGORY_KEYS`.
7. `test_config_defaults_y_aristas` — env limpio: FLYWHEEL True, INJECTION True, 3/4000/200 (leer de `config.config`); las 5 aristas en `_REQUIRES_MAP_FROZEN` apuntando al ROOT.
8. `test_help_presente` — el dict de `harness_flags_help` contiene las 5 keys.

**Comando (Git Bash):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_knowledge_flags.py tests/test_harness_flags.py tests/test_harness_flags_requires.py -q
```
**Criterio BINARIO:** los 3 archivos verdes (foto previa de fallos preexistentes de
`test_harness_flags.py`; criterio = sin regresión vs. foto).
**Flag:** las declaradas acá. **Runtimes:** N/A (declaración). **Trabajo del operador:** ninguno.

---

### F1 — Store de conocimiento: `backend/services/knowledge_store.py` (sidecar + vista compuesta + matching + dedup + LRU)

**Objetivo (1 frase):** exponer la vista compuesta `Lesson` (línea del `lessons.jsonl`
del 167 + `LessonMeta` del sidecar nuevo) con matching de scope, contadores de uso,
dedup y sugerencias LRU — sin escribir JAMÁS `lessons.jsonl`.
**Valor:** toda la lógica del flywheel testeable con `tmp_path`, y el contrato del 167
intacto byte a byte.

**Archivo a crear:** `backend/services/knowledge_store.py`

**Símbolos EXACTOS (además de los contratos §4.1-§4.3, §4.9):**

```python
import runtime_paths                      # data_dir() en CADA llamada (testabilidad)
_KNOWLEDGE_LOCK = threading.Lock()
_DEDUP_SIMILARITY_THRESHOLD = 0.55
_STALE_DAYS = 60                          # C9: días sin uso para sugerir revisión
VALID_SOURCE_KINDS = ("incident", "optimizer_lesson", "manual")

def evolution_root() -> Path              # runtime_paths.data_dir() / "evolution"
def _meta_path() -> Path                  # evolution_root() / "lessons_meta.json"
def _read_active_lines() -> list[dict]
    # Lee evolution_root()/"lessons.jsonl" línea a línea, json.loads tolerante
    # (línea corrupta → se omite). READ-ONLY (G10). Ausente → [].
def read_meta() -> dict                   # dict completo del sidecar; tolerante → {}
def upsert_meta(lesson_id: str, *, title, scope=None, source=None,
                eval_case_id=None) -> dict
    # Crea/actualiza la entrada §4.2 (normaliza scope: casefold + strip + dedup
    # de listas; scope None → {"agent_types": [], "projects": [], "tags": []}).
    # Valida source["kind"] in VALID_SOURCE_KINDS. Preserva usage_count/
    # last_injected_at/created_at existentes; updated_at = ahora.
    # ValueError("invalid_meta:<campo>") si falla.
def patch_meta(lesson_id: str, **patch) -> dict
    # SOLO claves {"title", "scope"} (otra → ValueError("invalid_meta:campo_no_editable")).
    # KeyError("lesson_not_found") si no hay meta NI línea activa con ese id
    # (para lecciones legacy sin meta: el patch CREA la meta con defaults §4.2 y aplica).
def list_lessons(include_retired: bool = False) -> list[dict]
    # Vista compuesta §4.2: activas = líneas de lessons.jsonl (+ meta o defaults);
    # retiradas = metas cuyo lesson_id NO está en las líneas activas (solo si
    # include_retired). Orden: activas primero, created_at DESC.
def get_lesson(lesson_id: str) -> dict | None
def active_lessons_for(agent_type: str | None, project_name: str | None) -> list[dict]
    # Filtra list_lessons(False) con lesson_matches(§4.3). Orden created_at DESC.
def lesson_matches(scope: dict, *, agent_type, project_name) -> bool   # §4.3, pura
def rank_lessons(lessons: list[dict], query: str | None, top_n: int) -> list[dict]
    # §4.3: TF-IDF via rag_retriever si query no vacío; fallback created_at DESC.
    # Pura sobre la lista. Nunca lanza.
def build_lessons_block(lessons: list[dict], *, query: str | None,
                        top_n: int, max_chars: int) -> dict | None
    # §4.5 (C8/ADICIÓN): PURA. rank_lessons(...) + header literal + entradas
    # numeradas "N. [<title>] <text>" + cap duro (loop: corta en la primera que no
    # entra → truncated=True; primera sola > cap → truncar con "…"). Devuelve el
    # dict block §4.5 completo o None si lessons está vacío. NO toca contadores,
    # NO lee flags (los límites llegan por parámetro). Único armador: lo consumen
    # el injector F3 (que luego registra) y el preview §4.8 (que no registra).
def record_injection(lesson_ids: list[str]) -> None
    # Bajo _KNOWLEDGE_LOCK: usage_count += 1 y last_injected_at = ahora para cada
    # id (id sin meta → la crea con defaults §4.2 antes de contar). Best-effort:
    # cualquier excepción se traga con log warning (NUNCA rompe un run).
def find_similar(candidate_title: str, candidate_body: str) -> list[dict]   # §4.9
def harvested_incident_ids() -> set[str]
    # §4.4 (C2): recorre evolution_store.list_proposals(aspect_id="knowledge_rag")
    # y junta los sufijos "incident:<id>" SOLO de propuestas con status != "rejected"
    # Y con algún marker "harvest:*" en evidence (pseudocódigo congelado §4.4).
    # Tolerante → set().
def harvested_optimizer_lesson_ids() -> set[str]     # ídem con "optimizer_lesson:<id>"
def retire_suggestions() -> list[dict]
    # §4.10 (C9): unión de (1) LRU si activas > STACKY_KNOWLEDGE_MAX_LESSONS (leer
    # via config.config, G1): las (activas - cap) con menor (usage_count, created_at)
    # asc, reason "lru_por_uso"; y (2) SIEMPRE: activas con usage_count == 0 y edad
    # > _STALE_DAYS días, reason "sin_uso_prolongado". Dedup con precedencia (1).
```

**Tests PRIMERO (TDD):** crear `backend/tests/test_knowledge_store.py`. Fixture
común: `monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)` +
helper `_write_lesson_line(tmp_path, lesson_id, text, ...)` que appendea una línea
válida a `tmp_path/"evolution"/"lessons.jsonl"` (simula el apply del 167 — los tests
del store NO llaman a `evolution_apply`). 14 casos:
1. `test_lessons_jsonl_ausente_da_vacio` — sin archivos → `list_lessons() == []`.
2. `test_vista_compuesta_con_meta` — 1 línea + `upsert_meta` → `list_lessons()[0]` trae `active is True`, title/scope de la meta y `text` de la línea.
3. `test_linea_sin_meta_usa_defaults` — 1 línea sin meta → `title` = primera línea del text (cap 80), scope global, `usage_count == 0` (backward-compat §4.2).
4. `test_retirada_va_con_include_retired` — meta sin línea activa → ausente de `list_lessons(False)`, presente con `active is False` en `list_lessons(True)`.
5. `test_lesson_matches_ejes` — tabla: scope global matchea todo; agent_types=["developer"] matchea solo developer; projects=["x"] + project "X" matchea (casefold); ambos ejes AND; agent_type None solo matchea lista vacía.
6. `test_active_lessons_for_filtra` — 3 líneas con scopes distintos → el filtro devuelve exactamente las esperadas.
7. `test_rank_lessons_tfidf_y_fallback` — con query que matchea una lección puntual → esa primera; con query None → created_at DESC.
8. `test_record_injection_incrementa` — 2 llamadas → `usage_count == 2`, `last_injected_at` no nulo; id sin meta → meta creada.
9. `test_record_injection_nunca_lanza` — monkeypatch `_meta_path` para que la escritura reviente → la llamada NO propaga excepción.
10. `test_find_similar_titulo_exacto_y_tfidf` — título normalizado igual → score 1.0; cuerpo casi idéntico → score ≥ umbral; corpus vacío → [].
11. `test_patch_meta_solo_title_scope` — patch de `title` ok; patch de `usage_count` → ValueError; id inexistente → KeyError.
12. `test_retire_suggestions_lru` — cap monkeypatcheado a 2 con 4 activas de usos [5,0,1,0] → sugiere las 2 de menor (usage, created_at) con `reason=="lru_por_uso"`; con cap 10 y todas recientes/usadas → [].
13. `test_harvested_ids_ignora_rechazadas_y_ajenas` (C2) — 3 propuestas `knowledge_rag` sembradas vía `evolution_store`: (a) evidence `["incident:inc-1", "harvest:llm_local"]` status `pending_review` → cuenta; (b) evidence `["incident:inc-2", "harvest:plantilla"]` status `rejected` → NO cuenta; (c) evidence `["incident:inc-3"]` SIN marker `harvest:*` (simula propuesta R-A3 del MAPE 167) → NO cuenta. `harvested_incident_ids() == {"inc-1"}`.
14. `test_retire_suggestions_sin_uso_prolongado` (C9) — 1 activa con `usage_count == 0` y `created_at` 90 días atrás + 1 activa reciente usada, cap 10 → sugiere SOLO la primera con `reason=="sin_uso_prolongado"`; la misma lección bajo cap excedido aparece UNA vez con `"lru_por_uso"`.

**Comando:**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_knowledge_store.py -q
```
**Criterio BINARIO:** exit 0 (14/14). Además:
`grep -n "write_text\|open(" "Stacky Agents/backend/services/knowledge_store.py" | grep -i "lessons.jsonl"` → 0 matches
(el store nunca escribe el jsonl del 167 — la única escritura es `_meta_path()`).
**Flag:** ninguna (módulo puro; los gates viven en F3/F5). **Runtimes:** N/A.
**Trabajo del operador:** ninguno.

---

### F2 — Cosecha: `backend/services/knowledge_harvest.py` (3 fuentes, LLM local con degradación, gate del 167)

**Objetivo (1 frase):** convertir una incidencia resuelta, una mutation lesson del 169
o un alta manual en una PROPUESTA `knowledge_note` del 167 (draft redactado solo, con
trazabilidad §4.4), pasando por `maybe_auto_apply` del 167 como único camino HOTL.
**Valor:** el costo de capturar aprendizaje baja a 1 click + 1 aprobación.

**Archivo a crear:** `backend/services/knowledge_harvest.py`
**Símbolos EXACTOS (además de §4.7):**

```python
def harvest_from_incident(incident_id: str, *, force: bool = False) -> dict
    # 1) incident_store.get_incident(incident_id) → None → KeyError("incident_not_found").
    # 2) incident["status"] != "publicada" → ValueError("incident_not_harvestable:<status>").
    # 3) Insumos (todos tolerantes, G16; TODOS pasan por
    #    pii_masker.redact_irreversible ANTES de usarse — G15/C1):
    #    a) texto del intake: redact_irreversible(incident.get("text") or "")
    #    b) doc de la incidencia: incident.get("doc_path") → Path.read_text tolerante
    #       → redact_irreversible(...), cap _HARVEST_MAX_INPUT_CHARS // 2
    #    c) run del dev: última AgentExecution con agent_type == "incident_dev",
    #       status == "completed", cuyo Ticket.ado_id coincide (como string) con
    #       incident.get("tracker_id") (query patrón context_enrichment.py:1130-1139;
    #       sin match → None). output → pii_masker.redact_irreversible (G15) →
    #       root_cause via regex §4.7 → exec_id para evidence.
    # 4) Draft: _render_llm_draft(...) con invoke_local_llm; fallo → _deterministic_draft
    #    (§4.7). marker = "harvest:llm_local" | "harvest:plantilla".
    # 4b) Defensa en profundidad (G15/C1): draft["title"] y draft["body"] pasan por
    #     redact_irreversible ANTES de crear la propuesta (también en
    #     harvest_from_optimizer_lesson y harvest_manual — helper común
    #     _mask_draft(draft) -> dict).
    # 5) Dedup: find_similar(title, body) → no vacío y not force →
    #    DuplicateSuspect(similars) (excepción propia del módulo).
    # 6) proposal = evolution_store.create_proposal(
    #        aspect_id="knowledge_rag", title=draft["title"],
    #        rationale="Lección cosechada de la incidencia " + incident_id,
    #        origin="agent", artifact_type="knowledge_note",
    #        proposed_content=draft["body"], evidence=<§4.4>,
    #        initial_status="pending_review", actor="operator")
    # 7) eval_case: case_store.list_cases() → primero con
    #    source_ref == f"incident:{incident_id}" → evidence += ["eval_case:<id>"]
    #    (via evolution_store.update_proposal_fields) y eval_case_id en la meta.
    # 8) knowledge_store.upsert_meta(proposal["id"], title=…, scope=<sugerido>,
    #    source={"kind": "incident", "ref": incident_id}, eval_case_id=…)
    #    Scope sugerido determinista: {"agent_types": [], "projects": [p] si la
    #    incidencia tiene proyecto detectable (no lo tiene hoy → []), "tags": draft["tags"]}.
    # 9) auto_applied = evolution_apply.maybe_auto_apply(proposal)  ← ÚNICO camino HOTL
    # 10) return {"proposal": <refetch>, "auto_applied": bool, "duplicates": [...]}
def harvest_from_optimizer_lesson(lesson_id: str, *, force: bool = False) -> dict
    # import tolerante de services.evolution_optimizer_store (ausente →
    # RuntimeError("optimizer_unavailable")). read_lessons_tail(limit=200) →
    # buscar id == lesson_id → KeyError("optimizer_lesson_not_found").
    # outcome != "mejoro" → ValueError("lesson_outcome_invalido:<outcome>").
    # Draft DETERMINISTA (sin LLM — el texto ya es curado por el motor 169):
    #   title = ("Mejora verificada en " + lesson["aspect_key"])[:_TITLE_MAX]
    #   body  = lesson["text"] + f"\n(Delta de fitness verificado: +{lesson['delta']}"
    #           f" en {lesson['aspect_key']}, corrida {lesson['run_id']}.)"
    # origin="optimizer", evidence=§4.4, initial_status="pending_review",
    # scope sugerido: aspect_key con forma "agent_prompts/<slug>" →
    # {"agent_types": [<slug>], ...}; sino global. Resto idéntico (dedup → meta →
    # maybe_auto_apply → return).
def harvest_manual(title: str, body: str, *, scope: dict | None = None,
                   force: bool = False) -> dict
    # Valida title/body no vacíos y <= _TITLE_MAX/_BODY_MAX →
    # ValueError("invalid_payload:<campo>"). origin="manual", evidence=["harvest:manual"].
    # Resto idéntico.
class DuplicateSuspect(Exception):        # .similars: list[dict]
```

**Tests PRIMERO (TDD):** crear `backend/tests/test_knowledge_harvest.py`. Fixtures:
`data_dir` monkeypatcheado; incidencia sintética vía `incident_store.create_incident`
+ `incident_store.update_incident(id, status="publicada", tracker_id="777")`;
`invoke_local_llm` SIEMPRE monkeypatcheado. 11 casos:
1. `test_from_incident_crea_propuesta_pending` — mock LLM devuelve JSON válido → 201-shape: propuesta `knowledge_note`/`knowledge_rag`/`origin=="agent"`/`status=="pending_review"`, `proposed_content == body` del mock, evidence empieza `["incident:<id>", "harvest:llm_local"]`, meta creada con source incident.
2. `test_from_incident_no_publicada_rechaza` — status `capturada` → ValueError `incident_not_harvestable`.
3. `test_from_incident_inexistente` — KeyError `incident_not_found`.
4. `test_degradacion_sin_llm` — mock lanza RuntimeError → propuesta igual creada con `"harvest:plantilla"` en evidence y body de plantilla determinista (KPI-4).
5. `test_root_cause_del_dev_run` — Ticket(ado_id=777) + AgentExecution(agent_type="incident_dev", status="completed", output con "CAUSA RAIZ: ...") → el insumo del LLM (capturar user del mock) contiene la causa; evidence contiene `execution:<id>`; el output pasó por `redact_irreversible` (monkeypatch spy).
6. `test_dedup_bloquea_y_force_pasa` — lección activa similar → `DuplicateSuspect`; con `force=True` → crea igual con `duplicates` no vacío.
7. `test_auto_apply_respetado` — con `STACKY_EVOLUTION_AUTO_APPLY_KNOWLEDGE_ENABLED` OFF (default) → `auto_applied is False` y status `pending_review`; monkeypatch de `evolution_apply.maybe_auto_apply` a True → `auto_applied is True` (el harvest NO aplica por su cuenta: solo reporta lo que el 167 hizo).
8. `test_from_optimizer_promocion` — monkeypatch `evolution_optimizer_store.read_lessons_tail` → lesson `mejoro` → propuesta `origin=="optimizer"`, evidence `["optimizer_lesson:<id>", "optimizer_run:<rid>", "harvest:promocion_determinista"]`, scope sugerido `agent_types==["developer"]` para aspect_key `agent_prompts/developer`.
9. `test_from_optimizer_sin_169_degrada` — import de `evolution_optimizer_store` forzado a fallar → RuntimeError `optimizer_unavailable` (declarado, no crash).
10. `test_manual_valida_limites` — title vacío → `invalid_payload:title`; body de 5000 chars → `invalid_payload:body`; válido → propuesta `origin=="manual"`.
11. `test_pii_enmascarada_en_todos_los_insumos` (C1) — incidencia cuyo `text` contiene un literal tipo secreto (partir el string en el fixture — gotcha push-protection) y doc con otro; monkeypatch de `redact_irreversible` como spy que reemplaza por `"[MASKED]"` → el `user` prompt capturado del mock LLM NO contiene los literales y sí `"[MASKED]"`; y con el mock LLM devolviendo un body que contiene un tercer literal → `proposed_content` de la propuesta lo trae enmascarado (paso 4b).

**Comando:**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_knowledge_harvest.py -q
```
**Criterio BINARIO:** exit 0 (11/11). Además (KPI-3, G14):
`grep -n "append_lesson\|lessons.jsonl" "Stacky Agents/backend/services/knowledge_harvest.py"` → 0 matches.
**Flag:** gate en F5 (el service es puro). **Runtimes:** cosecha backend-agnóstica;
LLM local con degradación declarada (los 3 por igual). **Trabajo del operador:** ninguno.

---

### F3 — El retorno del flywheel: `_inject_evolution_lessons` en `context_enrichment.py`

**Objetivo (1 frase):** inyectar el bloque `evolution-lessons` (§4.5) en
`enrich_blocks` — espejo del patrón `_inject_rejection_lessons` — para que las
lecciones activas lleguen a los 3 runtimes por el seam único del contrato 133.
**Valor:** el conocimiento acumulado vuelve a las corridas; sin lecciones matching el
prompt es byte-idéntico al de hoy.

**Archivo a editar:** `backend/services/context_enrichment.py` (2 toques quirúrgicos;
G13: `git status` antes).

**(a) `_BLOCK_PRIORITY` (`:366`):** agregar UNA línea dentro del dict, después de la
entrada `"stacky-memory": 80,`:

```python
    "evolution-lessons": 79,     # Plan 170 — lecciones aprendidas (flywheel de conocimiento)
```

**(a-bis, C7)** En el comentario de `_HIGH_PRIORITY_THRESHOLD`
(`context_enrichment.py:249-250`, "cubre: ado-epic-structured(100), …"), agregar
`evolution-lessons(79)` a la lista enumerada — el bloque nuevo queda ≥ 75 y es fuente
de verdad para el dedup léxico I0.1; el comentario no debe quedar mentiroso.

**(b) Nuevo injector + wiring.** Definir (ubicación: inmediatamente después de
`_inject_rejection_lessons`, `:1005`):

```python
def _inject_evolution_lessons(
    *, blocks: list[dict], project_name: str | None, agent_type: str,
    query: str | None, log: LogFn,
) -> list[dict]:
    """Plan 170 — inyecta lecciones de conocimiento activas (top-N, cap duro).

    Identidad estricta cuando: flags OFF, sin lecciones matching, o error.
    """
    from config import config as _cfg
    if not getattr(_cfg, "STACKY_KNOWLEDGE_FLYWHEEL_ENABLED", False):
        return blocks
    if not getattr(_cfg, "STACKY_KNOWLEDGE_INJECTION_ENABLED", False):
        return blocks
    if not getattr(_cfg, "STACKY_EVOLUTION_CENTER_ENABLED", False):
        return blocks
    existing_ids = {b.get("id") for b in (blocks or []) if isinstance(b, dict)}
    if "evolution-lessons" in existing_ids:
        return blocks
    try:
        from services import knowledge_store
        matched = knowledge_store.active_lessons_for(agent_type, project_name)
        if not matched:
            return blocks
        top_n = max(1, min(10, int(getattr(_cfg, "STACKY_KNOWLEDGE_INJECT_TOP_N", 3))))
        max_chars = max(500, min(20000, int(getattr(_cfg, "STACKY_KNOWLEDGE_INJECT_MAX_CHARS", 4000))))
        # C8: armado delegado a la función PURA de F1 (ranking + header + cap §4.5).
        block = knowledge_store.build_lessons_block(
            matched, query=query, top_n=top_n, max_chars=max_chars
        )
        if block is None:
            return blocks
        used_ids = block["metadata"]["lesson_ids"]
        knowledge_store.record_injection(used_ids)   # semántica C3: "seleccionada"
        log("info", f"evolution-lessons inyectado (n={len(used_ids)}, "
                    f"truncated={block['metadata']['truncated']})")
        return list(blocks) + [block]
    except Exception as exc:  # noqa: BLE001 — best-effort, contrato del módulo
        log("warn", f"evolution-lessons no se pudo inyectar (continuando): {exc}")
        return blocks
```

Wiring en `enrich_blocks`: UNA llamada inmediatamente DESPUÉS de
`blocks = _inject_rejection_lessons(...)` (`:231-233` — así el dedup léxico I0.1 y el
presupuesto F2.4 que corren después `:235-240` también gobiernan el bloque nuevo):

```python
    # Plan 170 — lecciones de conocimiento del flywheel (top-N, cap duro).
    blocks = _inject_evolution_lessons(
        blocks=blocks, project_name=project_name, agent_type=agent_type,
        query=_rag_query, log=log,
    )
```

(`_rag_query` ya existe en `:96` — mismo insumo de relevancia que el catálogo RAG.)

**Tests PRIMERO (TDD):** crear `backend/tests/test_knowledge_injection.py` (espejo
estructural de `tests/test_context_enrichment.py` — fixture `app_ctx` con DB real,
`data_dir` monkeypatcheado, lecciones sembradas con el helper de F1). 10 casos:
1. `test_sin_lecciones_identidad` — store vacío → `enrich_blocks(...)` devuelve lista SIN bloque `evolution-lessons` e IGUAL (`==`) a la corrida baseline (KPI-1).
2. `test_flag_injection_off_identidad` — 3 lecciones activas + `STACKY_KNOWLEDGE_INJECTION_ENABLED=False` (monkeypatch en `config.config`) → sin bloque, lista `==` baseline.
3. `test_inyecta_matching` — lección scope global + lección scope `agent_types=["qa"]`, run con `agent_type="developer"` → el bloque contiene SOLO la global; `metadata.lesson_ids` correcto.
4. `test_retired_no_se_inyecta` — lección cuya línea fue removida del jsonl (retirada) → no aparece.
5. `test_cap_duro_max_chars` — 5 lecciones de 2000 chars con `MAX_CHARS=3000` → `len(content) <= 3000`, `truncated is True` (KPI-2).
6. `test_primera_leccion_gigante_se_trunca` — 1 lección de 30000 chars → bloque presente, `len(content) <= MAX_CHARS`, sufijo `…`, `truncated is True`.
7. `test_top_n_respeta_flag` — 6 activas, `TOP_N=2` → exactamente 2 entradas.
8. `test_ranking_por_query` — 2 lecciones, ticket cuyo título matchea léxicamente la segunda → esa aparece primera.
9. `test_contadores_se_actualizan` — tras la corrida, `usage_count` de las inyectadas es 1 y `last_injected_at` no nulo.
10. `test_prioridad_y_participa_del_budget` — `_BLOCK_PRIORITY["evolution-lessons"] == 79`; con budget global F2.4 chico (flags de budget del 133 ON, monkeypatch) el bloque es podable y los de alta prioridad sobreviven.

**Comando:**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_knowledge_injection.py tests/test_context_enrichment.py -q
```
**Criterio BINARIO:** exit 0 en ambos (el segundo protege regresión del contrato 133).
Verificación de paridad (los 3 callers intactos pasando por el seam):
`grep -c "enrich_blocks" "Stacky Agents/backend/agent_runner.py" "Stacky Agents/backend/services/claude_code_cli_runner.py" "Stacky Agents/backend/services/codex_cli_runner.py"`
→ cada archivo ≥ 1.
**Flag:** `STACKY_KNOWLEDGE_INJECTION_ENABLED` (+ master + N + cap). **Runtimes:**
paridad AUTOMÁTICA — un solo seam (`enrich_blocks`); los CLI renderizan el bloque vía
`build_ticket_context_text` (`:1220`) sin cambios; copilot lo recibe como block
directo. Fallback: sin lecciones → identidad en los 3. **Trabajo del operador:** ninguno.

---

### F4 — Migración reservada del 168: `origin="lesson"` + lección→caso de eval

**Objetivo (1 frase):** cumplir la reserva del 168 §8.3 (agregar `"lesson"` a
`VALID_ORIGINS` de `case_store` y al DTO TS) y crear desde una lección un caso de eval
BORRADOR que la proteja a futuro.
**Valor:** el par lección-que-enseña + caso-que-protege queda enlazado en ambos
sentidos (flywheel MAPE-K completo).

**Archivos a editar (2, quirúrgicos — G13):**
1. `backend/evals/case_store.py` — ubicar la tupla
   `VALID_ORIGINS = ("seed", "incident", "execution", "manual")` (168 F1) y dejarla
   `("seed", "incident", "execution", "manual", "lesson")`.
2. `frontend/src/evolution/fitnessModel.ts` — ubicar el union del `EvalCaseDto`
   `origin: "seed" | "incident" | "execution" | "manual"` (168 F6) y agregar
   `| "lesson"`.

**Función nueva (en `knowledge_harvest.py`):**

```python
def lesson_to_eval_case(lesson_id: str) -> dict
    # knowledge_store.get_lesson → None → KeyError("lesson_not_found");
    # lesson["active"] is False → ValueError("lesson_not_active").
    # case_store.list_cases() con source_ref == f"lesson:{lesson_id}" ya existente
    # → ValueError("case_already_exists").
    # aspect_key: si scope["agent_types"] tiene EXACTAMENTE 1 → "agent_prompts/<type>";
    # sino "knowledge_rag".
    # case = case_store.create_case(
    #     aspect_key=…, agent_type=(el type si hubo 1, sino None),
    #     subject="artifact", level="deterministic",
    #     title=("Protege lección: " + lesson["title"])[:120],
    #     input={"kind": "artifact_text", "text": None, "golden_name": None},
    #     checks=[{"kind": "not_contains",
    #              "value": "COMPLETAR: anti-patron exacto que esta leccion prohibe",
    #              "case_sensitive": False}],
    #     origin="lesson", enabled=False,          # BORRADOR: el operador lo termina
    #     source_ref=f"lesson:{lesson_id}")
    # knowledge_store.upsert_meta(lesson_id, …, eval_case_id=case["id"])  (preserva resto)
    # return case
```

El caso nace **borrador con placeholder**: el operador edita el check en el panel del
168 (PATCH de `checks`/`enabled` ya permitido por su §4.8) y recién ahí protege de
verdad — human-in-the-loop, cero automatismo mentiroso.

**Tests PRIMERO (TDD):** crear `backend/tests/test_knowledge_eval_link.py`. 5 casos:
1. `test_valid_origins_incluye_lesson` — `case_store.VALID_ORIGINS` contiene `"lesson"` (KPI-6) y `create_case(origin="lesson", …)` NO lanza.
2. `test_to_eval_case_crea_borrador` — lección activa → caso `enabled is False`, `origin=="lesson"`, `source_ref=="lesson:<id>"`, check placeholder presente; meta de la lección con `eval_case_id` del caso.
3. `test_to_eval_case_scope_un_agente` — scope `agent_types=["developer"]` → `aspect_key=="agent_prompts/developer"` y `agent_type=="developer"`; scope global → `"knowledge_rag"`.
4. `test_to_eval_case_idempotente` — segunda llamada → ValueError `case_already_exists`.
5. `test_to_eval_case_retirada_rechaza` — lección retirada → ValueError `lesson_not_active`.

**Comando:**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_knowledge_eval_link.py -q
```
**Criterio BINARIO:** exit 0 (5/5) y los tests del 168 NO regresionan:
`.venv\Scripts\python.exe -m pytest tests/test_fitness_runner.py -q` → exit 0 (foto
previa si tuviera fallos preexistentes).
**Flag:** gate del endpoint en F5. **Runtimes:** N/A (datos). **Trabajo del operador:**
completar el check del caso borrador SOLO si quiere activarlo (opcional).

---

### F5 — API: `backend/api/evolution_knowledge.py` + registro + overview

**Objetivo (1 frase):** exponer los contratos HTTP §4.8-§4.10 con gate compuesto,
health siempre-200 y errores literales.
**Valor:** el panel (F6) y cualquier automatización futura consumen el flywheel por
HTTP local.

**Archivo a crear:** `backend/api/evolution_knowledge.py` — blueprint
`evolution_knowledge`, `url_prefix="/evolution"` (tercer blueprint del prefijo, mismo
patrón que 168 F5 / 169 F4: Flask permite N blueprints con el mismo prefijo y nombres
distintos). Estructura: `_knowledge_enabled()` (§4.6) + `@bp.before_request` que deja
pasar `/knowledge/health` y responde el 404 literal §4.8 para el resto con flag OFF
(espejo del gate del 168 F5). Mapeo de excepciones del service: `KeyError` → 404;
`ValueError("incident_not_harvestable:*")` → 409 con message que incluye el status;
`DuplicateSuspect` → 409 §4.9; `RuntimeError("optimizer_unavailable")` → 409;
`ValueError("invalid_payload:*")` → 400.

**Archivo a editar:** `backend/api/__init__.py` — 2 líneas por contenido (G13):
`from .evolution_knowledge import bp as evolution_knowledge_bp` en la zona de imports
(`:61`, después del import del blueprint del 169) y
`app.register_blueprint(evolution_knowledge_bp, url_prefix=f"{base}/evolution")`
en la zona de registers (`:122`, espejo EXACTO de la línea del 167/168/169 — copiar
la forma real que el 167 F4 haya dejado).

`GET /knowledge/harvest/candidates` (detalle determinista): incidencias =
`incident_store.list_incidents()` filtrado `status=="publicada"`, enriquecido con
`has_dev_run` (UNA query de `AgentExecution` `agent_type=="incident_dev" and
status=="completed"` + join lógico por `tracker_id`→`Ticket.ado_id`) y
`already_harvested` (set de `knowledge_store.harvested_incident_ids()`); mutation
lessons = `read_lessons_tail(limit=50)` filtrado `outcome=="mejoro"` + set de
`harvested_optimizer_lesson_ids()`. Sin pollers: el panel lo pide on-mount y tras
cada acción.

`GET /knowledge/injection-preview` (**[ADICIÓN ARQUITECTO]**, detalle determinista):
lee `agent_type`/`project`/`query` de la querystring (todos opcionales; ausentes →
`None`), llama `knowledge_store.active_lessons_for(agent_type, project)` +
`knowledge_store.build_lessons_block(...)` con los MISMOS clamps de flags del injector
F3, y responde `{"ok": true, "block": <dict | null>, "matched_count": <len de
matcheadas>}`. PROHIBIDO llamar `record_injection` acá (dry-run; el grep del DoD lo
verifica). Requiere solo el gate compuesto §4.6 (NO exige
`STACKY_KNOWLEDGE_INJECTION_ENABLED`: sirve para auditar ANTES de prender la
inyección o después de apagarla).

**Tests PRIMERO (TDD):** crear `backend/tests/test_knowledge_endpoints.py` (Flask
test client, patrón de los tests de endpoints del 167/168; `data_dir`
monkeypatcheado; `invoke_local_llm` mockeado). 11 casos:
1. `test_health_siempre_200` — flag ON y OFF → 200 con `flag_enabled` correcto.
2. `test_flag_off_404_literal` — `STACKY_KNOWLEDGE_FLYWHEEL_ENABLED=False` → `GET /api/evolution/knowledge/lessons` = 404 con `error=="knowledge_disabled"` (KPI-5).
3. `test_lessons_lista_y_retiradas` — 2 activas + 1 retirada → sin query 2; `?include_retired=true` → 3.
4. `test_patch_lesson_scope` — PATCH scope válido → 200 y la meta cambió; clave extraña → 400.
5. `test_candidates_shape` — incidencia publicada + una capturada → solo la publicada; `already_harvested` correcto tras cosechar; sin 169 → `optimizer_lessons == []`.
6. `test_from_incident_201_y_409` — 201 shape §4.8; repetir sin force sobre lección similar → 409 `duplicate_suspect` con `duplicates`.
7. `test_from_optimizer_endpoint` — mock del store 169 → 201; outcome `empeoro` → 409 `lesson_outcome_invalido`.
8. `test_manual_endpoint` — 201; title vacío → 400 `invalid_payload`.
9. `test_to_eval_case_endpoint` — 201 con caso borrador; segunda vez → 409 `case_already_exists`.
10. `test_overview_shape_y_tolerancia` — shape §4.10 completo con datos sembrados; con `case_store` roto (monkeypatch que lanza) → 200 igual con `fitness_knowledge` en nulls (tolerancia por fuente).
11. `test_injection_preview_no_cuenta_uso` (ADICIÓN) — 2 lecciones activas (una scope global, una `agent_types=["qa"]`): `GET /injection-preview?agent_type=developer` → 200 con `block.content` conteniendo SOLO la global, `matched_count == 1` y `usage_count` de TODAS las lecciones sigue en 0 tras la llamada; sin lecciones matching → `block is null`; con `STACKY_KNOWLEDGE_INJECTION_ENABLED=False` el preview RESPONDE igual (200).

**Comando:**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_knowledge_endpoints.py -q
```
**Criterio BINARIO:** exit 0 (11/11). Además (ADICIÓN, dry-run puro):
`grep -n "record_injection" "Stacky Agents/backend/api/evolution_knowledge.py"` → 0
matches (el endpoint de preview no registra uso; los registros viven SOLO en el
injector F3). **Flag:** `STACKY_KNOWLEDGE_FLYWHEEL_ENABLED` (gate §4.6). **Runtimes:**
N/A (HTTP local). **Trabajo del operador:** ninguno.

---

### F6 — Panel: `knowledgeModel.ts` + `KnowledgeSection.tsx` + wiring en `EvolutionCenterPage`

**Objetivo (1 frase):** sección "Conocimiento" del Centro de Evolución con KPIs del
flywheel, lista de lecciones (uso/scope/origen/impacto), candidatas a cosechar y alta
manual — sin pollers y con primitivas existentes.
**Valor:** el flywheel es visible y operable en 1 lugar; el operador ve qué aprendió
Stacky, cuánto se usa y qué conviene retirar.

**Archivos:**
1. CREAR `frontend/src/evolution/knowledgeModel.ts` — DTOs espejo de §4.2/§4.8/§4.10
   (`LessonDto`, `LessonScopeDto`, `HarvestCandidatesDto`, `KnowledgeOverviewDto`) +
   funciones PURAS testeables:
   `scopeLabel(scope)` ("Global" | "developer · qa" | "proyecto X"),
   `lessonStatusChip(l)` (`active` → `{tone:"ok", label:"Activa"}`; retirada →
   `{tone:"muted", label:"Retirada"}`),
   `formatDelta(delta)` (null → "—"; ±ddd con signo, 4 decimales via `formatPercent`
   NO: score plano con `toFixed(4)` — los scores del 168 son 0..1),
   `validateManualLesson({title, body})` → `{ok, errors}` (límites 80/1200, espejo
   §4.7 — para `firstErrorFieldId` del 162).
2. CREAR `frontend/src/evolution/KnowledgeSection.tsx` + `KnowledgeSection.module.css`
   (G6: cero inline-style). Estructura: `SectionHeader` "Conocimiento (flywheel)" +
   fila de KPIs (Card por métrica: activas, cobertura de agentes
   `agents_with_lessons/agents_total`, casos de eval nacidos de incidencias, delta de
   fitness `knowledge_rag` con rótulo literal "correlación, no causalidad") +
   `Tabs` con 3 pestañas:
   - **Lecciones**: lista (title, `StatusChip`, scope, `usage_count` con rótulo
     literal **"Seleccionada Nx"** (semántica C3 §4.2 — nunca "usada"),
     `formatDateTime(last_injected_at)`, origen con deep-link `?proposal=<lesson_id>`
     — riel G10 del 167); acciones por fila: "Retirar" (`ConfirmButton` →
     `Evolution.transition(lesson_id, "rollback", nota literal §4.8)` del namespace
     del 167), "Proteger con caso de eval" (POST to-eval-case; deshabilitado si
     `eval_case_id` ya existe), editor inline de scope (PATCH). Banner de
     `retire_suggestions` cuando la lista NO está vacía (C9: cubre `lru_por_uso` Y
     `sin_uso_prolongado`; `EmptyState` variant informativa + lista sugerida con su
     `reason` — solo sugerencia). **[ADICIÓN ARQUITECTO] Panel colapsable "Vista
     previa de inyección"**: `Select` de `agent_type` (opciones del registry vía
     overview `coverage.by_agent_type` + opción "—"), `Input` opcional de query, botón
     "Previsualizar" → `GET /injection-preview` y render del `block.content` en un
     `<pre>` estilado por `.module.css` (G6) + aviso "`matched_count` lecciones
     matchean; esto es EXACTAMENTE lo que recibiría el agente" (o `EmptyState` si
     `block` es null). Sin poller (G9): solo on-click.
   - **Cosechar**: candidatas de `harvest/candidates` — incidencias publicadas
     (badge `has_dev_run` "con resolución verificada") con botón "Extraer lección";
     mutation lessons `mejoro` con botón "Promover a lección"; `already_harvested`
     deshabilitado con label "Ya cosechada". Diálogo de confirmación en 409
     `duplicate_suspect` mostrando `duplicates` con opción "Crear igual" (`force`).
   - **Nueva lección**: form manual con primitivas 162 (`Field`+`Input` title,
     `Field`+`Textarea` body, `Input` tags CSV, selects de scope) +
     `firstErrorFieldId` + `validateManualLesson`.
   Estados: `SkeletonList` cargando, `EmptyState` sin lecciones ("Todavía no hay
   lecciones. Cosechá la primera desde una incidencia resuelta."), `Toast` en
   éxito/error de cada acción. Refresh: on-mount + tras cada acción + botón
   "Refrescar" (G9: cero `setInterval`).
3. EDITAR `frontend/src/api/endpoints.ts` — namespace nuevo `EvolutionKnowledge`
   (espejo del estilo del namespace `Evolution` del 167 F5) con las 10 rutas §4.8
   (incluida `injectionPreview`).
4. EDITAR `frontend/src/pages/EvolutionCenterPage.tsx` — montar `<KnowledgeSection />`
   gated por su health (`flag_enabled`), espejo EXACTO del wiring con que el 168 F6
   montó `FitnessSection` (ubicar por el literal `FitnessSection` y replicar el
   patrón inmediatamente después de la sección del 169).

**Tests PRIMERO (TDD):** crear `frontend/src/evolution/knowledgeModel.test.ts`
(vitest puro, sin DOM — G5 y gap RTL/jsdom conocido). 8 casos:
1. `scopeLabel` global → "Global"; con agentes → lista unida.
2. `lessonStatusChip` activa/retirada.
3. `formatDelta` null → "—"; 0.0312 → "+0.0312"; negativo con signo.
4. `validateManualLesson` título vacío → error en `title`.
5. `validateManualLesson` body > 1200 → error en `body`.
6. `validateManualLesson` válido → `ok true` y sin errores.
7. DTO round-trip: `KnowledgeOverviewDto` de fixture §4.10 parsea sin `any`.
8. Candidatas: helper `sortCandidates` (no cosechadas primero, luego por `created_at` DESC) — pura.

**Comandos:**
```bash
cd "Stacky Agents/frontend" && npx vitest run src/evolution/knowledgeModel.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
```
**Criterio BINARIO:** vitest 8/8 y `tsc` exit 0; `uiDebtRatchet` verde
(`npx vitest run src/__tests__/uiDebtRatchet.test.ts`);
`grep -c "setInterval" "Stacky Agents/frontend/src/evolution/KnowledgeSection.tsx"` → 0 (G9).
**Flag:** la sección solo renderiza con health `flag_enabled` (kill-switch UI).
**Runtimes:** N/A (panel). **Trabajo del operador:** ninguno obligatorio (cosechar,
retirar, proteger y editar scope son SIEMPRE opcionales).

---

### F7 — Ratchet, cierre y verificación global

**Objetivo (1 frase):** registrar los tests nuevos en el ratchet (sh + ps1),
actualizar el estado del doc y correr la verificación de cierre completa.

**Archivos a editar:** `backend/scripts/run_harness_tests.sh` (agregar en la zona
reciente `:458-460`, después de las entradas del 169) y
`backend/scripts/run_harness_tests.ps1` (`:412-414`, mismas entradas):

```
  tests/test_knowledge_flags.py
  tests/test_knowledge_store.py
  tests/test_knowledge_harvest.py
  tests/test_knowledge_injection.py
  tests/test_knowledge_eval_link.py
  tests/test_knowledge_endpoints.py
```

**Corrida de cierre (por archivo, G5):**

```bash
cd "Stacky Agents/backend" \
  && .venv/Scripts/python.exe -m pytest tests/test_knowledge_flags.py -q \
  && .venv/Scripts/python.exe -m pytest tests/test_knowledge_store.py -q \
  && .venv/Scripts/python.exe -m pytest tests/test_knowledge_harvest.py -q \
  && .venv/Scripts/python.exe -m pytest tests/test_knowledge_injection.py -q \
  && .venv/Scripts/python.exe -m pytest tests/test_knowledge_eval_link.py -q \
  && .venv/Scripts/python.exe -m pytest tests/test_knowledge_endpoints.py -q \
  && .venv/Scripts/python.exe -m pytest tests/test_context_enrichment.py -q \
  && .venv/Scripts/python.exe -m pytest tests/test_harness_flags.py -q \
  && .venv/Scripts/python.exe -m pytest tests/test_harness_flags_requires.py -q
cd "Stacky Agents/frontend" \
  && npx vitest run src/evolution/knowledgeModel.test.ts \
  && npx tsc --noEmit
```

**Criterio BINARIO:** todo exit 0 (con foto previa de fallos preexistentes ajenos).
Actualizar el encabezado `**Estado:**` de ESTE doc (riel
`feedback_actualizar-estado-plan-en-doc`). `git status` final: WIP ajeno intacto
(G13); el implementador NO commitea.

---

## 6. Riesgos y mitigaciones

- **R1 — Prompt bloat (el prompt crece sin límite).** Cap DURO doble: top-N (default
  3) + `MAX_CHARS` (default 4000, clamp 500..20000) en el injector (KPI-2), y el
  bloque además participa del presupuesto global F2.4 del 133 con prioridad 79
  (podable bajo presión). Kill-switch independiente
  `STACKY_KNOWLEDGE_INJECTION_ENABLED` por UI.
- **R2 — Lecciones malas o tóxicas para los prompts.** Toda lección pasa por
  aprobación humana (KPI-3); retiro 1-click auditado (rollback del 167); el panel
  muestra uso + delta de fitness del aspecto como CORRELACIÓN rotulada (nunca
  causalidad inventada); y el caso de eval enlazado protege contra regresiones si el
  operador lo activa.
- **R3 — Self-confirming loop (el sistema aprende de su propia opinión).** Las
  lecciones nacen SOLO de: incidencia publicada con resolución real (CAUSA RAIZ del
  dev con evidencia — señal externa), mutation lesson con `outcome=="mejoro"`
  computado por el MOTOR del 169 contra el fitness del 168 (nunca por el LLM), o
  juicio del operador. El LLM local solo REDACTA (§3.6); sin LLM, plantilla
  determinista (KPI-4).
- **R4 — Corpus podrido (acumulación sin curación).** Dedup en la cosecha (título
  exacto + TF-IDF ≥ 0.55, override consciente con `force`), cap sugerente con LRU
  por uso (sugerencia visible, jamás auto-borrado), retiradas conservadas como
  historial (archive del 167: nada se borra).
- **R5 — Confusión entre los DOS `lessons.jsonl` (167 vs 169).** G10 lo congela:
  nombres SIEMPRE con prefijo; este plan no escribe ninguno de los dos; test F1
  criterio-grep verifica que el store solo escribe `lessons_meta.json`.
- **R6 — `record_injection` en el camino caliente de runs.** Best-effort estricto
  (test F1 caso 9: la excepción no propaga); escritura chica (un dict JSON) bajo
  lock; si el disco falla, el run sigue idéntico. Semántica C3: cuenta "seleccionada
  para inyección" — con el budget F2.4 del 133 ON el bloque puede podarse después;
  el panel lo rotula así y nunca afirma "el agente la leyó".
- **R7 — LLM local no disponible / lento / respuesta basura.** Degradación declarada
  a plantilla determinista (KPI-4) con marker en `evidence`; timeout ya gobernado por
  `LOCAL_LLM_TIMEOUT_SEC` (riel del bridge); insumo cap `_HARVEST_MAX_INPUT_CHARS`.
- **R8 — Números de línea que rotan (sesiones paralelas).** Citas orientativas:
  anclar SIEMPRE por contenido/símbolo (regla heredada 128/167/168/169). WIP ajeno
  HOY en `runtime_paths.py`/`run_preflight.py`: este plan NO los toca (G13).
- **R9 — `lessons_meta.json` crece.** Dict de metas de cientos de lecciones = KB de
  texto; aceptado en v1 (espejo de R8 del 167 / R10 del 168). Particionar sería un
  plan futuro.
- **R10 — Dependencia dura no cumplida (167/168 sin implementar).** Pre-check global
  §5 detiene la implementación con mensaje claro; F2.b además degrada sin el 169
  (blanda) con error declarado `optimizer_unavailable`.

## 7. Fuera de scope (explícito)

- **7.1 — Promoción de lecciones al corpus `docs/rag/` del repo.** Verificado
  2026-07-17: `rag_corpus.jsonl` tiene CERO consumidores en el backend (grep en tabla
  de dependencias), su `schema.json` exige campos documentales inaplicables a
  lecciones (`source_file`, `source_span`, `heading_path` — `schema.json:6`), y el
  pipeline RAG vivo (`api/docs_rag.py`, DocConsultor con fallback del Plan 112)
  indexa los docs del PROYECTO del operador, no `docs/rag/`. Promover ahí sería
  escribir a un destino que nadie lee: infraestructura muerta que este plan NO revive
  (riel del 167 G11 satisfecho en su parte viva: lecciones en `data_dir()` +
  inyección directa por el contrato 133). Si algún día existe un consumidor real del
  corpus del repo, la promoción curada será un plan propio.
- **Export/import de lecciones** (mono-operador; sin caso de uso).
- **Editar el TEXTO de una lección aplicada** (romperia la trazabilidad
  propuesta→lección del 167; el camino es retirar + re-cosechar/alta manual; `title`
  y `scope` sí son editables porque viven en el sidecar).
- **Daemon/cron/hook post-ejecución de cosecha** (autonomía proactiva prohibida; la
  cosecha es on-click; las candidatas se listan on-mount).
- **Cosechar de la "opinión" de un agente sobre su propia corrida** (anti
  self-confirming §3.6 — solo fallos RESUELTOS y mejoras VERIFICADAS).
- **Ejecutar agentes para validar lecciones** (territorio del sandbox de ejecución,
  ya excluido por el 168 §7).
- **Tocar `memory_store` / `rejection_lessons` / `docs_rag`** (sistemas hermanos,
  §2.3).
- **Notificaciones (152), auth/RBAC, react-router, scheduler genérico.**

## 8. Contratos que este plan HONRA (nombres de los planes 167/168/169)

- **← 167 §8.3:** el destino es el aspecto `knowledge_rag` +
  `data_dir()/evolution/lessons.jsonl` — este plan lo consume TAL CUAL: crea
  propuestas `knowledge_note` vía `evolution_store.create_proposal`, deja que
  `evolution_apply` escriba/borre las líneas (apply/rollback), y el único camino
  human-on-the-loop es `maybe_auto_apply` con
  `STACKY_EVOLUTION_AUTO_APPLY_KNOWLEDGE_ENABLED` (default OFF, excepción dura #1
  citada allá). La promoción al corpus del repo NO se implementa (§7.1, con
  evidencia).
- **← 168 §8.3:** consume `from-incident` (enlace lección↔caso por
  `source_ref=="incident:<id>"`), la rúbrica `leccion_conocimiento` (que ya evalúa
  las lecciones ANTES de aplicarse vía fitness del `knowledge_note`), y EJECUTA la
  migración reservada: `origin="lesson"` en `VALID_ORIGINS` de `case_store` + DTO
  (F4, KPI-6).
- **← 169 §8.2:** lee `evolution_optimizer_store.read_lessons_tail()` y promueve
  SOLO `outcome=="mejoro"` a propuestas `knowledge_note` (F2.b) — el 169 no promueve
  nada, este plan sí, siempre con gate humano.
- **→ nadie:** este plan CIERRA la serie. No deja contratos hacia un plan 5. Las
  extensiones posibles (promoción a corpus con consumidor real, particionado de
  stores, meta-evaluación de lecciones) quedan documentadas en §7 como futuros SIN
  reserva de nombres.

## 9. Glosario (para un modelo menor)

| Término | Definición |
|---|---|
| **flywheel (de conocimiento)** | Ciclo que se auto-refuerza: fallo real → lección aprobada → inyección al contexto → menos fallos → más capacidad de resolver los nuevos. Cada vuelta deja capital acumulado. |
| **lección (Lesson)** | Unidad de conocimiento corta y accionable (título ≤80 + cuerpo ≤1200) nacida de un fallo resuelto o mejora verificada, con scope, trazabilidad al origen y contadores de uso. Vive como línea del `lessons.jsonl` del 167 + metadata en sidecar. |
| **harvest (cosecha)** | Convertir una fuente (incidencia resuelta, mutation lesson, alta manual) en una PROPUESTA de lección del 167. Siempre por click; el LLM local redacta el borrador; el operador aprueba. |
| **inyección de contexto** | Agregar bloques de texto al prompt de una corrida vía `enrich_blocks` (contrato del Plan 133) — el seam único por el que TODOS los runtimes reciben el mismo contexto. |
| **scope matching** | Decidir si una lección aplica a una corrida: por agente y por proyecto (lista vacía = global). Los tags no filtran corridas: organizan el panel. |
| **LRU (por uso)** | "Least Recently/Frequently Used": al exceder el cap del corpus, se SUGIEREN para retiro las lecciones con menos inyecciones (y más viejas). Sugerencia — retirar siempre lo decide el operador. |
| **capex process-level** | (Survey RSI) El aprendizaje a nivel de PROCESO (procedimientos, lecciones) es capital reutilizable entre problemas; filtrar solo respuestas finales es gasto por problema (opex). Este plan acumula capex. |
| **Reflexion** | Técnica de "verbal RL": reflexiones textuales guardadas en memoria mejoran corridas futuras sin tocar pesos. El redactor de drafts y la inyección son su traducción a Stacky. |
| **skill library** | (Voyager) Biblioteca incremental de habilidades verificadas, indexada y recuperada por relevancia. Acá: lecciones activas + TF-IDF + top-N. |
| **sidecar (`lessons_meta.json`)** | Archivo hermano que agrega metadata (scope, uso, origen) a las líneas del `lessons.jsonl` del 167 SIN tocar su contrato. Correspondencia por `lesson_id` (= id de la propuesta). |
| **señal externa** | Verificación que NO depende de la opinión del generador: resolución real de una incidencia, outcome computado contra fitness, decisión del operador. Única fuente válida de lecciones (anti self-confirming). |
| **correlación, no causalidad** | El panel muestra "el fitness del aspecto subió desde que existen estas lecciones" como correlación honesta; NUNCA afirma que una lección causó la mejora. |
| **retiro (retire)** | Sacar una lección de circulación: rollback de su propuesta del 167 (auditado, reversible el día que se re-cosecha). La meta queda como historial. |
| **mutation lesson** | (169) 1-3 líneas de "qué cambié y por qué", anotadas por el motor con el outcome real contra fitness. Con `outcome=="mejoro"` es candidata a lección de conocimiento. |
| **caso que protege / lección que enseña** | Un `EvalCase` (168) falla si el defecto vuelve (protección); una lección se inyecta al contexto para no cometerlo (enseñanza). Este plan los enlaza (`origin="lesson"`, `source_ref`). |

## 10. Orden de implementación

1. **Pre-check global** — 167 y 168 en el árbol + greps de símbolos del contrato
   (§5, C4) — si algo falta, DETENERSE y reportar.
2. **F0** — flags + config + help + meta-tests (foto previa de `test_harness_flags.py`).
3. **F1** — knowledge_store (sidecar + vista + matching + dedup + LRU + staleness +
   `build_lessons_block`) + 14 tests.
4. **F2** — knowledge_harvest (3 fuentes + degradación + PII total + gate 167) + 11 tests.
5. **F3** — `_inject_evolution_lessons` + `_BLOCK_PRIORITY` + wiring `enrich_blocks` + 10 tests (+ regresión `test_context_enrichment.py`).
6. **F4** — migración `origin="lesson"` (py + ts) + `lesson_to_eval_case` + 5 tests (+ regresión `test_fitness_runner.py`).
7. **F5** — API + registro de blueprint + overview + preview dry-run + 11 tests.
8. **F6** — knowledgeModel + KnowledgeSection + endpoints + wiring EvolutionCenterPage + 8 tests + tsc + ratchet UI.
9. **F7** — ratchet (sh + ps1) + estado del doc + corrida completa de cierre.

## 11. Definición de Hecho (DoD)

- [ ] Las 5 flags con patrón triple completo (config + FlagSpec + `_CATEGORY_KEYS` +
      help + curated SOLO las 2 bool + requires al ROOT del 167), editables desde la
      UI del Arnés; `harness_defaults.env` NO tocado a mano (G12).
- [ ] Los 6 archivos de test backend verdes POR ARCHIVO (59 casos: 8+14+11+10+5+11),
      registrados en `HARNESS_TEST_FILES` (sh + ps1); `knowledgeModel.test.ts` (8)
      verde; `npx tsc --noEmit` exit 0; `uiDebtRatchet` verde.
- [ ] PII (C1): los 3 insumos del draft Y el draft final pasan por
      `redact_irreversible` (test F2 caso 11 verde).
- [ ] Preview dry-run (ADICIÓN): `grep -n "record_injection"
      "Stacky Agents/backend/api/evolution_knowledge.py"` → 0 matches; test F5
      caso 11 verde (el preview no altera contadores).
- [ ] KPI-1: sin lecciones matching o flag OFF → lista de bloques `==` baseline
      (byte-idéntico). KPI-2: `len(content) <= MAX_CHARS` siempre, `truncated`
      declarado. KPI-3: la cosecha solo crea propuestas — grep de
      `append_lesson|lessons.jsonl` en `knowledge_harvest.py` → 0. KPI-4: sin LLM →
      plantilla determinista con `"harvest:plantilla"`. KPI-6: `origin="lesson"`
      migrado y `to-eval-case` crea borradores.
- [ ] Con `STACKY_KNOWLEDGE_FLYWHEEL_ENABLED=false`: endpoints (salvo
      `/knowledge/health`) → 404 `knowledge_disabled`; la sección no renderiza; resto
      byte-idéntico (KPI-5).
- [ ] Ningún test del plan abre red: `invoke_local_llm` monkeypatcheado en TODOS los
      tests que alcanzan el redactor.
- [ ] Sin autonomía: la cosecha no tiene callers fuera de `api/evolution_knowledge.py`
      y tests (verificable:
      `grep -rn "harvest_from_incident\|harvest_from_optimizer_lesson\|harvest_manual" "Stacky Agents/backend" --include=*.py | grep -v tests | grep -v knowledge` → 0 matches).
- [ ] Cero pollers nuevos: `grep -c "setInterval" "Stacky Agents/frontend/src/evolution/KnowledgeSection.tsx"` → 0 (G9).
- [ ] Los DOS jsonl de lecciones (167 y 169) quedan READ-ONLY para el código nuevo
      (G10; criterio-grep de F1).
- [ ] `test_context_enrichment.py` y `test_fitness_runner.py` sin regresión vs. foto
      previa (contratos 133 y 168 intactos).
- [ ] Retirar una lección desde el panel ejecuta el `rollback` del 167 (sin endpoint
      nuevo) y queda auditado en su ledger.
- [ ] Encabezado `**Estado:**` de este doc actualizado al cerrar; `git status` final
      con WIP ajeno intacto (G13).

## 12. Cierre de la serie RSI 167-170

Con este plan, el ciclo completo queda cableado y gobernado: el **167** MONITOREA la
telemetría existente y registra propuestas con gates humanos, ledger y rollback; el
**168** EVALÚA con señal jerárquica (deterministas > ejecución > juez local) y llena
el fitness que convierte "me parece mejor" en un número auditable; el **169** OPTIMIZA
artefactos de texto con mutación reflexiva, frente Pareto y archive, emitiendo
solo propuestas que el operador aprueba; y el **170** APRENDE: cada incidencia
resuelta y cada mejora verificada puede volverse una lección corta, aprobada,
trazable y medible, que vuelve al contexto de las próximas corridas por el mismo
contrato de inyección que ya usan los 3 runtimes. El operador está SIEMPRE en el
lazo: aprueba cada lección, ve cuánto se usa y qué correlación tiene con el fitness,
retira con un click, y el único atajo (auto-aplicar lecciones reversibles) es una
flag que él prende a conciencia y puede auditar línea por línea. El flywheel gira a
la velocidad que el operador decide — esa es la diferencia entre auto-mejora
gobernada y automatismo.

Lo que NO se hará nunca, en esta serie ni en las siguientes: **closed loop**. Ningún
plan futuro puede hacer que Stacky se auto-modifique sin supervisión — no es un valor
válido de `loop_mode` (167 §4.2), no hay daemon de cosecha ni de ciclo ni de
optimización, y ninguna pieza de esta serie puede aplicar un cambio que un humano no
haya aprobado (con la única excepción, explícita, reversible y default-OFF, de las
lecciones de conocimiento del 167). La serie 167-170 termina acá porque el ciclo está
cerrado: Monitor→Evaluar→Optimizar→Aprender→(operador)→Monitor. Lo que sigue no es
más autonomía: es más señal, más casos, mejores lecciones — capital que se acumula
vuelta a vuelta con el humano girando la manivela.
