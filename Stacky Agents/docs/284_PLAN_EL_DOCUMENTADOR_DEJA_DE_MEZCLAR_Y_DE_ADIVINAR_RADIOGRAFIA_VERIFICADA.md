# 284 — EL DOCUMENTADOR DEJA DE MEZCLAR Y DE ADIVINAR: FRONTERA PLANES/PROYECTO, NOTA DEL OPERADOR, PIPELINE DE 5 ETAPAS Y RADIOGRAFÍA VERIFICADA

**Estado:** **IMPLEMENTADO** F0..F7 (v2 criticado + construido) — 2026-08-01. Ver seccion 11.
**Autor:** StackyArchitectaUltraEficientCode
**Juez (v1 → v2):** StackyArchitectaUltraEficientCode (contexto limpio, red-team con verificación de anclajes abriendo archivos)
**Veredicto de la crítica v1:** **RECHAZADO** — 6 bloqueantes. Todos corregidos en esta v2.
**Depende de:** 113 (Documentador 1-click), 114 (staleness), 137 (Documentador V2: evidencia + citas + historial), 109 (grafo documental), 268 (Explorador del grafo)
**NO re-propone nada de 137 ni de 268.** La sección "Qué YA está construido" lo delimita archivo:línea.

---

## 0. CHANGELOG v1 → v2

Ratio de anclajes de la v1 verificados abriendo los archivos reales: **101 / 104 correctos** (3 fallas duras, 6 off-by-one triviales). El anclaje exacto **no predijo nada**: la v1 tenía anclajes casi perfectos y aun así 6 bloqueantes, porque los defectos no estaban en *dónde* mira sino en *qué capacidades supone que existen*.

| # | Hallazgo | Sev. | Qué cambió en la v2 |
|---|---|---|---|
| **C1** | **F5 invocaba `invoke_documenter` con `system_prompt_override`, parámetro que NO EXISTE** (firma real `doc_documenter.py:364-367`; el override está hardcodeado a `_DEFAULT_DOCUMENTADOR_PROMPT` en `:381`). Además `invoke_documenter` devuelve `list[DocProposal]` — parsea adentro — así que era imposible obtener el texto crudo que las etapas de papel necesitan. | BLOQ | **F5.0 nueva**: se extiende `invoke_documenter` con el kwarg y se agrega `invoke_raw_stage()` que devuelve texto. Sin esto F5 era papel mojado. |
| **C2** | **F4 era inalcanzable: `mine_project_tickets` filtra por `stacky_project_name` y los 228 tickets están repartidos en 8 proyectos** (RIPLEY 65, RSPACIFICO 57, `p` 49, `P` 44, ONP 6, RSSICREA 3, `__demo__` 3, `test` 1). El techo real por proyecto es **65**, no 228. Y el censo de aceptación corría SQL **sin filtro de proyecto** ⇒ no ejercitaba la función de producción. | BLOQ | KPI-5 reescrito a la realidad medida; `scope` explícito (`project` \| `all`); match de proyecto **case-insensitive** (`p`/`P` son el mismo proyecto partido en dos); el censo ahora llama a `mine_project_tickets`, no a SQL suelto. |
| **C3** | **El filtro de tickets sintéticos capturaba ~1 de 103.** `_SYNTHETIC_ADO_IDS = {-7}` se evaluaba contra `external_id`, pero `-7` es sentinela de **`ado_id`** (`doc_documenter.py:304`) y la fila cuyo `external_id == -7` tiene `ado_id == -2`. Hay **103 filas con `ado_id < 0`**. | BLOQ | Regla nueva: sintético = `ado_id < 0` **o** `external_id < 0`. Se elimina el frozenset de un elemento. |
| **C4** | **F0.1 ponía rojo un test en el primer paso del plan.** `default_is_known(spec)` es `spec.default is not None` (`harness_flags.py:6566`) y `test_default_known_only_for_curated` asserta **igualdad de sets**. El plan declaraba **10** flags (decía 9), mandaba a `_CURATED_DEFAULTS_ON` sólo "las 7 booleanas ON" (que en realidad son **6**) y omitía la OFF y las 3 numéricas ⇒ 4 claves faltantes. | BLOQ | Conteo corregido a **10 flags (6 bool ON + 1 bool OFF + 3 numéricas)**; **las 10** van a `_CURATED_DEFAULTS_ON`; se corrige la ubicación del set. |
| **C5** | **El camino por defecto del producto quedaba colgado.** Con `STAGES=ON` + `AUTOAPPLY=OFF` **todo** run se detiene en `awaiting_approval`, y la única salida era un endpoint (`/documenter/stage/approve`) **sin un solo test**, **sin función cliente en `endpoints.ts`**, y con `test_docs_api.py` **no registrado en ninguno de los dos ratchets**. | BLOQ | F5.3 ahora especifica el endpoint completo, su función cliente, sus 4 tests, y **registra `test_docs_api.py` en los DOS scripts** del arnés. |
| **C6** | **F2 no probaba el cable, sólo el último eslabón.** El censo AST demostraba que `_operator_note_block` se llama dentro de `build_context_for_mode`, pero **nada** probaba que `run_documenter(operator_note=…)` propagara hasta ahí. Cinco saltos, uno verificado: el patrón *construido, testeado y jamás cableado* exacto. | BLOQ | Test nuevo `test_plan284_nota_viaja_de_run_documenter_al_prompt`: monkeypatchea `invoke_documenter` para **capturar** `context_blocks` y asserta el centinela sobre `render_blocks` del capturado. |
| **C7** | KPI-7 ("0% de runs sin veredicto") **se contradecía con los defaults del propio plan**: con `AUTOAPPLY=OFF` el run se detiene antes de VERIFICAR ⇒ 100% de los runs terminan sin veredicto. | IMP | KPI-7 reescrito: el veredicto se emite **también** en la parada por aprobación (`PENDIENTE_DE_APROBACION`). |
| **C8** | F7 afirmaba "ningún trabajo nuevo: la aprobación **reemplaza** al Conservar/Descartar", pero el plan **no elimina** `POST /documenter/decide` (`api/docs.py:364`) ⇒ el operador queda con **dos** decisiones por run. | IMP | Se declara honestamente y se fusionan: aprobar-e-implementar encadena la decisión de rama en la misma pantalla. |
| **C9** | `_CURATED_DEFAULTS_ON` anclado a `services/harness_flags.py`, donde **sólo hay un comentario** (`:710`). Vive en `backend/tests/test_harness_flags.py:467-1003`. Un modelo menor lo grepea, no lo encuentra y se traba. | IMP | Ruta y rango corregidos. |
| **C10** | F7 no mandaba extender `DocumenterStatusResponse` (`endpoints.ts:3552-3573`) con las 5 claves nuevas ⇒ **`npx tsc --noEmit` falla**, y ese exit 0 es criterio binario de la propia fase. | IMP | F7.0 nueva: extender el tipo primero. |
| **C11** | **Cuerpos sin especificar** (inimplementables para un modelo menor): `build_tickets_context_block` (`...`), `compute_coverage` (sólo docstring), `StageResult.to_dict` (`...`), `_run_paper_stage` (prosa), `_STAGE_PROMPT_*` (nunca escritos), y `compute_verify_verdict` que **sólo aparecía en el test**. | IMP | Los 6 quedan escritos con cuerpo completo. |
| **C12** | **Tabla de `classify_ticket` subespecificada**: "demo con descripción larga → noise, score 0" sólo cierra si la descripción está entre 200 y 799 y el tipo no es Task; con 1200 chars da 2 ⇒ **signal**, y el test sale rojo o se "arregla" debilitando el assert. Idem el caso `external_id=-7`. | IMP | Cada caso de la tabla ahora fija **todos** los campos y el score exacto. |
| **C13** | **`ado_state` se aceptaba y se ignoraba.** Los estados vivos (`Active` 109, `opened` 63, `Done` 23, `Doing` 12, `Reviewed by Dev` 11, `To Do` 6, `Done by dev` 2, `New` 1, `Done by AI` 1) son justamente la señal de "obsoleto" que pidió el operador en su punto 6. | IMP | `ado_state` entra al scoring con las constantes medidas. |
| **C14** | **El censo HITL de F5 no probaba lo que decía**: `Select-String … AUTOAPPLY \| Count == 1` cuenta menciones por subcadena (un comentario lo rompe) y no verifica que la consulta esté **antes** de escribir. Un gate que premia no documentar. | IMP | Reemplazado por censo AST de orden + el test de comportamiento como criterio real. |
| **C15** | El censo de F6 era una **ausencia por subcadena sin presencia gemela** (y se evade con `getattr`). | IMP | Se agrega la presencia: `compute_coverage` debe leer `graph["doc_health"]["uncovered_modules"]` y `graph["orphans"]`. |
| **C16** | La sección 2 afirmaba **"no existe ningún `docs/rag/rag_corpus.jsonl`"**. **Sí existe** (169.544 bytes, 2026-07-15). | IMP | Corregido: existe pero es un **sidecar muerto** (0 referencias en `backend/**` y `frontend/src/**`); la tesis de fondo (el corpus vivo es la tabla `docs_index`) **se sostiene**, pero la frase era falsa en un plan cuya bandera es no adivinar. |
| **C17** | PROPONER sin gate de calidad más allá de `<200 chars`: 250 chars de basura pasan y disparan 2 invocaciones más. | IMP | Gate reforzado: longitud **y** al menos una ruta real del contexto. |
| **C18** | F2 daba **dos instrucciones contradictorias para la misma línea** (`note.trim() \|\| undefined` en F2.1 vs `normalizeOperatorNote(note)` en el bloque de frontend), y `maxLength={4000}` hardcodeado contra una flag configurable. | MEN | Una sola instrucción; el máximo viaja desde el backend. |
| **C19** | **Anclajes `:547` y `:558` invertidos**: `:547` es `_safe_rel_path` (anti-traversal) y `:558` es `_is_canonical` (`docs/sistema/` read-only), al revés de lo que decía la tabla. | MEN | Corregidos. |
| **C20** | Off-by-one decorador-vs-`def` en `api/docs.py:67`, `:269`, `:292` (los `def` están en 68, 270, 293) y `FlagSpec` abre en `:2681`, no `:2682`. | MEN | Corregidos. |
| **C21** | La tabla de defaults de flags **omitía `STACKY_DOCS_OPERATOR_NOTE_MAX_CHARS`** — una flag sin default declarado en la tabla que gobierna los defaults. | MEN | Agregada. |
| **C22** | R4 **sobreafirmaba**: el enforcement determinista protege el **filesystem**, no el **contenido**. Y F3 explícitamente no valida semántica (fuera de scope #5). | MEN | R4 reescrito con el alcance real y el modelo de amenaza mono-operador. |
| **C23** | Sin huella de regresión en `docs/sistema/error_fingerprints.json`. | MEN | Agregada en el DoD. |
| **C24** | `p` (49) y `P` (44) son el **mismo proyecto partido en dos claves** por case-sensitivity de SQLite. Hazard de datos no mencionado. | MEN | Documentado y mitigado con match case-insensitive. |

**Adiciones proactivas de esta v2** (ver marcas `[ADICIÓN ARQUITECTO]`):
- **A1 — Presupuesto de invocaciones LLM por run, medido y con tope duro.** La v1 admitía N→N+3 sin techo ni telemetría.
- **A2 — Delta de radiografía entre runs.** Convierte el Documentador de one-shot en instrumento: "subiste de 62% a 74%, cerraste 3 módulos". Cero LLM extra.

---

## 1. Objetivo

El Documentador de Stacky hoy **produce, pero no convence**: mezcla 240 documentos de plan con 15 notas de sistema en el mismo árbol, no acepta ni una línea de indicación del operador al lanzarse, verifica las citas `archivo:línea` **después** de haber escrito el archivo (o sea: no las verifica, las reporta), ignora por completo los 228 tickets del corpus, y resuelve todo en una sola pasada sin criticarse a sí mismo.

Este plan lo convierte en un **instrumento de radiografía**: separa con frontera dura la documentación de PLANES de la del PROYECTO, acepta una **nota libre del operador** que llega verificablemente al prompt, convierte el verificador de citas en un **gate que rechaza**, **mina los 228 tickets** con un triage señal/ruido auditable (sin LLM), y corre un **pipeline interno de 5 etapas** (PROPONER → CRITICAR → MEJORAR → IMPLEMENTAR → VERIFICAR) con estado persistido por etapa y confirmación humana en la frontera que escribe.

### KPI / impacto esperado (medibles, todos con comando)

| # | KPI | Hoy (medido) | Meta |
|---|-----|--------------|------|
| KPI-1 | Nodos del DocTree técnico clasificados como PLAN vs PROYECTO | 0 de 309 (`doc_class` no existe) | 309 de 309 |
| KPI-2 | Documentos con `doc_class="plan"` excluibles del corpus RAG y del cómputo de salud | 0 (los 240 planes contaminan) | 240 |
| KPI-3 | Notas del operador que llegan al prompt del agente | 0 (el body es `{project}` y nada más) | 1 por run, verificable por test sobre `render_blocks` |
| KPI-4 | Archivos escritos con citas `archivo:línea` inválidas | sin tope (se escriben y después se cuentan) | 0 con el gate ON |
| KPI-5 | Tickets barridos por el Documentador **en el proyecto activo** | 0 | **65 de 65** con `scope="project"` sobre RIPLEY (el proyecto activo, `data/active_project.json`); **228 de 228** con `scope="all"`. Veredicto `signal`/`noise` por ticket en ambos casos |
| KPI-6 | Etapas del run con estado persistido y veredicto | 0 (hay `current_mode`, no etapas) | 5 de 5 |
| KPI-7 | Runs que terminan sin veredicto explícito | 100% | 0% — **incluida la parada por aprobación**, que emite `PENDIENTE_DE_APROBACION` (ver C7) |

> **Corrección v2 sobre KPI-5.** La v1 prometía "228 tickets barridos" con una función que filtra por `stacky_project_name`. Medido el 2026-08-01 sobre la base viva, los 228 tickets están repartidos en **8 proyectos**: `RIPLEY` 65, `RSPACIFICO` 57, `p` 49, `P` 44, `ONP` 6, `RSSICREA` 3, `__demo__` 3, `test` 1. **Ningún proyecto llega a 228**; el mayor es 65. Prometer 228 con un barrido por proyecto era un KPI inalcanzable por construcción. Además `p` y `P` son **el mismo proyecto partido en dos claves** por la comparación sensible a mayúsculas de SQLite — de ahí el match case-insensitive de F4.

---

## 2. Por qué ahora / gap que cierra

Los planes recientes (276-283) cerraron paridad GitLab, ruteo por tracker y desenlace por evidencia. El Documentador quedó como está desde el **137 (2026-07-15)**. Es la única superficie del producto que produce un artefacto que el operador va a **leer y creer**, y hoy no da garantías sobre él.

### Evidencia del estado actual (todo verificado abriendo los archivos)

**(a) La mezcla planes/proyecto es masiva y estructural.**
- `Stacky Agents/backend/services/doc_indexer.py:265` define `docs_dir = STACKY_AGENTS_ROOT / "docs"`, y `doc_indexer.py:270` lo recorre con `docs_dir.rglob("*.md")` — recursivo y sin filtro de nombre.
- Los únicos filtros existentes son `_EXCLUDE_DIRS` (`doc_indexer.py:44-52`) y `_EXCLUDE_EXTENSIONS = {".db"}` (`doc_indexer.py:54`), aplicados en `_should_exclude` (`doc_indexer.py:89-96`). **Ninguno mira el nombre del archivo.**
- Resultado medido (2026-08-01, censo propio sobre `Stacky Agents/docs/`): de **309** `.md` totales, **240** son documentos de plan (238 `NN_PLAN_*`, 1 `NN_INCIDENTE_*`, 1 `NN_CHECKLIST_*`), **15** son notas canónicas de `docs/sistema/` y **54** son documentación de producto. Los 309 caen aplanados en la misma lista de nodos (`doc_indexer.py:274`) bajo el mismo root `"technical-docs"` (`doc_indexer.py:339-342`). **Los planes son el 78% del árbol y sepultan a las 15 notas de sistema.**
- El nodo del índice se construye en `_make_node` (`doc_indexer.py:138`), dict en `doc_indexer.py:150-160`: campos `id, kind, label, path, display_path, source_id, size_bytes, headings, children`. **No hay ningún campo de categoría.**
- Un `NN_PLAN_*.md` y un `docs/sistema/*.md` comparten `source_id == "stacky"` ⇒ son **indistinguibles** para `classify_doc_health`, que filtra por `source_id.startswith(PROJECT_DOC_SOURCE_PREFIX)` (`doc_graph.py:433`).
- El corpus RAG repite el mismo error por un camino paralelo: `docs_rag.py:155` hace `root = Path(workspace_root) / docs_subpath` y `docs_rag.py:160` `md_files = sorted(root.rglob("*.md"))`. Se traga los 240 planes igual.

**(b) No hay forma de decirle nada al Documentador.**
- El botón manda **un solo campo**: `endpoints.ts:3651` arma el body como `project ? { project } : {}`. La firma es `documenterRun: (project?: string)` en `endpoints.ts:3648`.
- El handler `launch` está en `DocumenterButton.tsx:47` y llama `Docs.documenterRun(projectName)` en `DocumenterButton.tsx:52`. El componente se autodescribe como "1-click, sin formularios" (`DocumenterButton.tsx:2`).
- El endpoint sólo lee `project` y `runtime`: `api/docs.py:280` y `api/docs.py:283`. Todo lo demás del body se descarta.

**(c) El verificador de citas es decorativo.**
- `doc_documenter.py:597` escribe el archivo: `dest.write_text(prop.content, encoding="utf-8")`.
- `doc_documenter.py:601` recién entonces llama `doc_evidence.verify_citations(...)`, y el resultado va a `result.files` (`doc_documenter.py:603-608`) **sólo para mostrarlo**.
- Nada en `apply_proposals` (`doc_documenter.py:563-612`) usa `citations["bad"]` para rechazar. Las razones de skip existentes son `unsafe_path`, `canonical_readonly`, `missing_confidence_marks`, `max_files_cap`, `write_error` (`doc_documenter.py:582-611`). **No existe una razón de skip por citas inválidas.**
- Peor: `workspace_root` sólo se pasa si la V2 está ON (`doc_documenter.py:915`); con V2 OFF ni siquiera se cuentan.
- La maquinaria de verificación **ya existe y funciona**: `verify_citations` en `doc_evidence.py:139-175` valida que el archivo exista y que la línea esté dentro del rango, con filtro anti-URL y anti-versión (`doc_evidence.py:101-136`). Sólo falta usarla como gate.

**(d) Los tickets no participan de la documentación.**
- `grep -i ticket` sobre `backend/services/docs_rag.py` → **0 matches**. Sobre `backend/services/doc_graph.py` → **0 matches**.
- No existe ningún barrido completo del corpus: los barridos existentes están todos filtrados (`ado_sync.py:344` por proyecto, `ticket_assigner.py:59-61` por persona, `few_shot.py:70-77` con limit 50).
- No existe scoring de calidad de ticket. Lo que hay puntúa otra cosa: `cost_scoring.py:351` puntúa costo/tokens, `ticket_assigner.py:282` afinidad persona↔ticket, `ticket_diagnostics.py:172` explica por qué un ticket está trabado. **Ninguno dice si un ticket es útil o basura.**
- Corpus real medido en la base viva `Stacky Agents/backend/data/stacky_agents.db` (SELECT read-only, 2026-08-01): **228 tickets** — `azure_devops` 162, `gitlab` 63, `demo` 3. **199** con descripción no vacía (⇒ 29 vacías), **112** con descripción de menos de 200 caracteres, **7** títulos duplicados.

**(e) El run no se critica a sí mismo ni deja veredicto.**
- `run_documenter` (`doc_documenter.py:824-962`) itera modos y termina. El reporte final (`doc_documenter.py:941-958`) tiene `state, written, skipped, health_before, health_after, branch, degraded, diff_stat, error, modes_skipped, files`. **No hay `verdict` ni etapas.**
- La UI muestra el modo en curso como texto (`DocumenterButton.tsx:85`) y nada más: no hay progreso por etapa.

### Qué YA está construido (y este plan NO vuelve a proponer)

| Del plan | Qué existe | Anclaje |
|---|---|---|
| 113 | Selector determinista de modos (`plan_documenter_run`), gate git con worktree aislado (`prepare_doc_branch`), aplicador determinista (`apply_proposals`), anti-traversal (`_safe_rel_path`), `docs/sistema/` read-only (`_is_canonical`), lock de un run activo (`DocumenterBusy`) | `doc_documenter.py:115`, `:468`, `:563`, **`:547`**, **`:558`**, `:623` |

> **Corrección v2 (C19):** la v1 tenía `:547` y `:558` **invertidos**. Verificado abriendo el archivo: `:547` es `def _safe_rel_path(path: str) -> str | None:` (**anti-traversal**) y `:558` es `def _is_canonical(norm: str) -> bool:` (**`docs/sistema/` read-only**). El lock efectivo, además, no está en `:623` (que es `class DocumenterBusy`) sino en `:704-706` (`with _registry_lock` → `raise DocumenterBusy()`).
| 137 F1 | Evidencia real de módulo (árbol + símbolos con línea) | `doc_evidence.build_module_evidence` `doc_evidence.py:50` |
| 137 F2 | Verificador de citas (extracción + validación contra filesystem) | `doc_evidence.verify_citations` `doc_evidence.py:139` |
| 137 F3 | Short-circuit de modos sin targets | `should_invoke_mode` `doc_documenter.py:262` |
| 137 F4 | Historial persistente de corridas + fallback a disco | `_persist_run_report` `doc_documenter.py:758`, `list_runs` `:778` |
| 137 F5/F6 | Preview por archivo + panel de revisión | `doc_documenter.py:603-608`, `DocumenterResultPanel.tsx` |
| 268 | Explorador del grafo: filtros, búsqueda, zoom, foco, agrupación, peek, minimapa | `frontend/src/docs/docGraphModel.ts`, `forceLayout.ts` |
| 109 | Grafo documental + `classify_doc_health` | `doc_graph.build_graph` `doc_graph.py:179`, `:424` |

**Corrección de un supuesto circulante (reescrita en v2 — la v1 decía lo contrario y estaba mal).**

`Stacky Agents/docs/rag/rag_corpus.jsonl` **SÍ EXISTE** (169.544 bytes, mtime 2026-07-15 15:28), junto a `manifest.json`, `schema.json` y `README.txt`. La v1 de este plan afirmaba que no existía: **era falso**, y en un plan cuya bandera es "dejar de adivinar" eso no puede pasar.

Lo que **sí** es cierto, y es lo que importa para F1 y F6:

- El corpus RAG **vivo** es la tabla SQLite `docs_index` (`DocChunk.__tablename__`, `docs_rag.py:70`). `docs_rag.py` es 100% SQLAlchemy: **no toca disco**.
- `rag_corpus.jsonl` es un **sidecar muerto**: `grep -r "rag_corpus"` sobre `backend/**` y `frontend/src/**` da **0 referencias**. No tiene productor ni consumidor en código. Nació de un único commit (`4e56a779`) y su propio `README.txt` se declara sidecar: *"NO reemplaza ni modifica la fuente, ni el indice runtime TF-IDF (services/docs_rag.py -> tabla SQLite docs_index)"*. Usa extensión no-`.md` a propósito para que el `rglob("*.md")` de `_index_technical_docs` no lo indexe.
- **Consecuencia para este plan:** F1.3 filtra `docs_rag.index_project`, que es el camino vivo — correcto. El `.jsonl` **no** se toca, no se regenera y no se borra. Queda anotado en "Fuera de scope" porque si alguien lo regenerara con la herramienta que lo creó, volvería a mezclar planes con doc de proyecto por el camino que este plan acaba de cerrar.

Y el "grafo con tickets" del plan 276 es la vista jerárquica épica→hijos de `GET /hierarchy` (`api/tickets.py:735-736`), **no** el grafo documental. Cualquier fase que asuma lo contrario está mal.

---

## 3. Principios y guardarraíles (no negociables)

1. **Human-in-the-loop.** El pipeline propone y verifica solo; la etapa que escribe pide confirmación salvo que el operador encienda explícitamente el autoaplicado (flag OFF por default, categoría B).
2. **Mono-operador, sin auth real.** Ningún RBAC, ningún multiusuario. Un 403/404 por flag apagada es "capacidad desactivada", no "permiso denegado".
3. **Toda config del operador va por UI.** Las flags nuevas se registran en `harness_flags.py` con su categoría, y quedan visibles y editables en el panel de flags.
4. **Backward-compatible.** Con cada flag nueva en OFF, el comportamiento es byte-idéntico al de hoy. Los campos nuevos de respuesta son aditivos y el frontend actual los ignora sin romperse.
5. **El enforcement es determinista, nunca del prompt.** La nota del operador **no puede** aflojar un guardarraíl: aunque el LLM le obedezca, el aplicador determinista sigue bloqueando `docs/sistema/` (`doc_documenter.py:588`), el path traversal (`doc_documenter.py:584`) y el tope de archivos (`doc_documenter.py:581`). Esto es una propiedad de diseño, no un supuesto.
6. **Nunca push, nunca merge, nunca stash.** Ya está enforced en `_git` (`doc_documenter.py:456-458`); este plan no lo toca.
7. **Sin trabajo nuevo para el operador.** Todo lo nuevo es automático o es un campo opcional que, vacío, deja el comportamiento actual.
8. **Los 3 runtimes.** Todo lo nuevo es Python/TypeScript determinista salvo las etapas que invocan al LLM, que pasan por `invoke_documenter` → `agent_runner.run_agent`, ya agnóstico de runtime (`doc_documenter.py:385-399`).

### Regla de default de flags aplicada a este plan

> **Conteo corregido en v2 (C4/C21): son 10 flags, no 9.** La v1 decía "9 flags" en tres lugares (objetivo de F0, orden de implementación y DoD) pero su propio bloque de `config.py` declaraba **10** asignaciones, y la tabla de defaults **omitía `STACKY_DOCS_OPERATOR_NOTE_MAX_CHARS`**. Desglose real: **6 booleanas ON + 1 booleana OFF + 3 numéricas = 10**. (La v1 también decía "las 7 booleanas ON": son **6**.)

| Flag | Tipo | Default | Justificación |
|---|---|---|---|
| `STACKY_DOCS_TAXONOMY_ENABLED` | bool | **ON** | Clasificar un path es solo lectura y cálculo puro. No es excepción. |
| `STACKY_DOCS_OPERATOR_NOTE_ENABLED` | bool | **ON** | Campo de texto opcional que el operador llena on-demand. Vacío ⇒ comportamiento actual. No quema tokens en reposo. |
| `STACKY_DOCS_OPERATOR_NOTE_MAX_CHARS` | int | **4000** | *(faltaba en la v1 — C21.)* Tope de la nota. Bounds `[0, 100000]`. Numérico, no booleano. |
| `STACKY_DOCS_CITATION_GATE_ENABLED` | bool | **ON** | Endurece (rechaza archivos con citas falsas). Aumenta la seguridad del artefacto, no la reduce. |
| `STACKY_DOCS_CITATION_GATE_MIN_RATIO` | float | **0.8** | Umbral numérico, no booleano. Bounds `[0.0, 1.0]`. |
| `STACKY_DOCS_TICKET_MINING_ENABLED` | bool | **ON** | Barrido SQL determinista, sin LLM, y **sólo cuando el operador lanza el Documentador**. No hay loop ni daemon ⇒ no es categoría (A). |
| `STACKY_DOCS_TICKET_MINING_MAX` | int | **500** | Tope de tickets barridos. Bounds `[1, 100000]`. |
| `STACKY_DOCS_PIPELINE_STAGES_ENABLED` | bool | **ON** | Estructura el run en etapas con veredicto. Planear, criticar y verificar son lectura y cálculo. |
| `STACKY_DOCS_PIPELINE_AUTOAPPLY` | bool | **OFF** | **Excepción (B): le saca la decisión al operador.** Con ON, la etapa IMPLEMENTAR escribe sin esperar la confirmación humana que hoy exige `POST /documenter/decide` (`api/docs.py:364`). Es exactamente el precedente `STACKY_PIPELINE_NL_EDIT_ENABLED` (ON) vs `..._COMMIT_ENABLED` (OFF): la parte que planea y diffea va ON, la que decide sola va OFF. |
| `STACKY_DOCS_RADIOGRAPHY_ENABLED` | bool | **ON** | Calcular cobertura sobre el grafo ya construido es solo lectura. |

---

## 4. Fases

### Convenciones para el implementador

- **Intérprete backend (verificado):** `Stacky Agents/backend/.venv/Scripts/python.exe` es **Python 3.13.5** y corre los tests (comprobado: `test_doc_evidence.py` → `18 passed in 0.91s`). Existe también `backend/venv` con **Python 3.11.9**: **no lo uses**.
- **Tests backend por archivo, nunca la suite entera** (contaminación conocida). Con `-k` verificá siempre que el número de tests seleccionados sea > 0: un `-k` sin match da exit 0 y es un falso verde.
- **Ratchet del arnés:** los tests nuevos de este plan van **exclusivamente** dentro de archivos **ya registrados en los DOS scripts**:
  - `tests/test_documenter_v2_pipeline.py` → `run_harness_tests.ps1:366` y `run_harness_tests.sh:417`
  - `tests/test_doc_evidence.py` → `run_harness_tests.ps1:364` y `run_harness_tests.sh:415`
  - `tests/test_documenter_autonomy.py` → `run_harness_tests.ps1:210` y `run_harness_tests.sh:217`
  **No crees archivos de test backend nuevos.** Evita la trampa: el ratchet es de commit, no sólo de edición.
- **Tests frontend:** vitest está instalado localmente (`frontend/node_modules/.bin/vitest`, v4.1.9). **RTL y jsdom NO están instalados** ⇒ toda lógica de UI testeable va en `.ts` puro. Los tests nuevos de frontend van en `frontend/src/docs/documenterModel.test.ts` (ya existe).
- **Comando frontend:** `cd "Stacky Agents/frontend" && npx vitest run src/docs/documenterModel.test.ts`
- **Typecheck frontend:** `cd "Stacky Agents/frontend" && npx tsc --noEmit`
- **Todo test nuevo guarda PRESENCIA además de ausencia.** Un `assert x not in y` solo puede pasar por accidente (por ejemplo si `y` está vacío por un error de setup): en el mismo test, asertá también que algo que **sí** debe estar, está.

---

### F0 — Sustrato: flags + módulo de taxonomía puro (sin cablear)

**Objetivo:** dejar registradas las 9 flags y un módulo de clasificación puro y testeado, sin que nada de producción lo consuma todavía.
**Valor:** todas las fases siguientes tienen su interruptor y su función pura desde el minuto cero.

#### F0.1 — Registrar las flags

**Archivo a editar:** `Stacky Agents/backend/config.py`
Agregar, inmediatamente después del bloque de `STACKY_DOCS_STALENESS_ENABLED` (que hoy termina en `config.py:748`):

```python
    # Plan 284 — taxonomía documental (plan vs proyecto)
    STACKY_DOCS_TAXONOMY_ENABLED: bool = os.getenv(
        "STACKY_DOCS_TAXONOMY_ENABLED", "true"
    ).strip().lower() in ("1", "true", "yes", "on")
    # Plan 284 — nota libre del operador al lanzar el Documentador
    STACKY_DOCS_OPERATOR_NOTE_ENABLED: bool = os.getenv(
        "STACKY_DOCS_OPERATOR_NOTE_ENABLED", "true"
    ).strip().lower() in ("1", "true", "yes", "on")
    STACKY_DOCS_OPERATOR_NOTE_MAX_CHARS: int = int(
        os.getenv("STACKY_DOCS_OPERATOR_NOTE_MAX_CHARS", "4000") or "4000"
    )
    # Plan 284 — el verificador de citas pasa a ser gate bloqueante
    STACKY_DOCS_CITATION_GATE_ENABLED: bool = os.getenv(
        "STACKY_DOCS_CITATION_GATE_ENABLED", "true"
    ).strip().lower() in ("1", "true", "yes", "on")
    STACKY_DOCS_CITATION_GATE_MIN_RATIO: float = float(
        os.getenv("STACKY_DOCS_CITATION_GATE_MIN_RATIO", "0.8") or "0.8"
    )
    # Plan 284 — minería determinista del corpus de tickets
    STACKY_DOCS_TICKET_MINING_ENABLED: bool = os.getenv(
        "STACKY_DOCS_TICKET_MINING_ENABLED", "true"
    ).strip().lower() in ("1", "true", "yes", "on")
    STACKY_DOCS_TICKET_MINING_MAX: int = int(
        os.getenv("STACKY_DOCS_TICKET_MINING_MAX", "500") or "500"
    )
    # Plan 284 — pipeline interno de 5 etapas con veredicto
    STACKY_DOCS_PIPELINE_STAGES_ENABLED: bool = os.getenv(
        "STACKY_DOCS_PIPELINE_STAGES_ENABLED", "true"
    ).strip().lower() in ("1", "true", "yes", "on")
    # Plan 284 — autoaplicado sin confirmación humana. Excepción (B).
    STACKY_DOCS_PIPELINE_AUTOAPPLY: bool = os.getenv(
        "STACKY_DOCS_PIPELINE_AUTOAPPLY", "false"
    ).strip().lower() in ("1", "true", "yes", "on")
    # Plan 284 — cobertura/radiografía sobre el grafo del 268
    STACKY_DOCS_RADIOGRAPHY_ENABLED: bool = os.getenv(
        "STACKY_DOCS_RADIOGRAPHY_ENABLED", "true"
    ).strip().lower() in ("1", "true", "yes", "on")
```

> **Copiá el patrón exacto del `os.getenv(...).strip().lower() in (...)` que usan las flags vecinas** (`config.py:707-748`). No inventes un helper nuevo.

**Archivo a editar:** `Stacky Agents/backend/services/harness_flags.py`

1. **Categorías** — en `_CATEGORY_KEYS` (`harness_flags.py:120`):
   - Agregar a la tupla numérica (la que hoy contiene `"STACKY_DOCS_DOCUMENTER_MAX_FILES"` en `harness_flags.py:151` y `"STACKY_DOCS_DOCUMENTER_EVIDENCE_MAX_CHARS"` en `:152`) las claves: `"STACKY_DOCS_OPERATOR_NOTE_MAX_CHARS"`, `"STACKY_DOCS_CITATION_GATE_MIN_RATIO"`, `"STACKY_DOCS_TICKET_MINING_MAX"`.
   - Agregar a la tupla de capacidades de docs (la que hoy contiene `"STACKY_DOCS_DOCUMENTER_V2_ENABLED"` en `harness_flags.py:446`) las claves booleanas: `"STACKY_DOCS_TAXONOMY_ENABLED"`, `"STACKY_DOCS_OPERATOR_NOTE_ENABLED"`, `"STACKY_DOCS_CITATION_GATE_ENABLED"`, `"STACKY_DOCS_TICKET_MINING_ENABLED"`, `"STACKY_DOCS_PIPELINE_STAGES_ENABLED"`, `"STACKY_DOCS_PIPELINE_AUTOAPPLY"`, `"STACKY_DOCS_RADIOGRAPHY_ENABLED"`.
2. **FlagSpec** — agregar **10** specs siguiendo el patrón de `harness_flags.py:2681-2760` (el `FlagSpec(` abre en **`:2681`**, no en `:2682` — C20). Reglas exactas:
   - Las **6** booleanas ON llevan `default=True` **y** el comentario `# curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated)`.
   - **⚠️ BLOQUEANTE DE LA v1 (C4) — leé esto dos veces.** La v1 decía "agregá las 7 booleanas ON a `_CURATED_DEFAULTS_ON`". Eso pone el test **rojo** y era el primer paso del plan. La regla real, verificada:
     - `default_is_known(spec)` es literalmente `return spec.default is not None` (`services/harness_flags.py:6566`).
     - `test_default_known_only_for_curated` (`backend/tests/test_harness_flags.py:1078`) asserta **`known_keys == _CURATED_DEFAULTS_ON`**: **igualdad de sets**, que detecta drift en las **dos** direcciones.
     - Por lo tanto **TODA** flag con `default=` explícito cuenta como "known": las 6 booleanas ON, **la booleana OFF** (`default=False` **no es** `None`) **y las 3 numéricas** (`4000`, `0.8`, `500`).
     - ⇒ **Las 10 claves van a `_CURATED_DEFAULTS_ON`.** Si agregás sólo las 6 ON, faltan 4 y el test sale rojo con un diff de 4 claves.
   - **Ubicación corregida (C9):** `_CURATED_DEFAULTS_ON` **NO vive en `services/harness_flags.py`** (ahí sólo hay una mención en un comentario, `:710`). Vive en **`backend/tests/test_harness_flags.py`**, abre en **`:467`** y cierra en **`:1003`**; es un **`set` literal de `str`** con ~308 claves agrupadas por plan. Agregá las 10 al final del bloque de docs, con el comentario `# Plan 284`.
   - **Procedimiento a prueba de ambigüedad:** después de agregar las specs, corré `pytest tests/test_harness_flags.py -q -k default_known` y, si falla, **leé el diff de sets que imprime el assert** y agregá exactamente las claves que reporta. No adivines la lista.
   - `STACKY_DOCS_PIPELINE_AUTOAPPLY` lleva `default=False` **explícito** (no lo omitas: una flag que nace OFF sin declararlo es ambigua) y en su `help` la frase literal `Si la encendés, el Documentador escribe sin pedirte confirmación.`
   - Las que dependen del master llevan `requires="STACKY_DOCS_DOCUMENTER_ENABLED"`, igual que `harness_flags.py:2708` y `:2728`. `STACKY_DOCS_TAXONOMY_ENABLED` lleva `requires="STACKY_DOCS_GRAPH_ENABLED"` (mismo patrón que `harness_flags.py:2760`).
   - **Trampa conocida:** el gate del texto de ayuda exige la palabra `Si ` **sin tilde** al abrir la condicional. Escribí `Si está en ON...`, nunca `Sí está...`.
   - Bounds numéricos: `STACKY_DOCS_CITATION_GATE_MIN_RATIO` → `[0.0, 1.0]`; `STACKY_DOCS_TICKET_MINING_MAX` → `[1, 100000]`; `STACKY_DOCS_OPERATOR_NOTE_MAX_CHARS` → `[0, 100000]`.

**Advertencia al implementador:** registrar flags pone en rojo **5 tests ajenos de fábrica** (4 de `test_harness_flags_help` + 1 de `env_read_meta`). Antes de tocar nada, sacá la foto del rojo previo con el comando de abajo y compará **delta**, no valor absoluto.

```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q > "$env:TEMP\284_rojo_base.txt" 2>&1; Get-Content "$env:TEMP\284_rojo_base.txt" -Tail 3
```

#### F0.2 — Módulo de taxonomía puro

**Archivo a CREAR:** `Stacky Agents/backend/services/doc_taxonomy.py`

```python
"""Plan 284 — Clasificación determinista de documentos (plan vs proyecto).

Módulo PURO: sin I/O, sin DB, sin LLM. Clasifica por la forma del path.
"""
from __future__ import annotations

import re

# Clases posibles. Orden estable, usado por la UI para agrupar.
DOC_CLASS_PLAN = "plan"        # Stacky Agents/docs/NN_PLAN_*.md y hermanos numerados
DOC_CLASS_SYSTEM = "system"    # docs/sistema/*.md — documentación canónica del proyecto
DOC_CLASS_PROJECT = "project"  # el resto de la doc del proyecto documentado
DOC_CLASS_AGENT = "agent"      # *.agent.md
DOC_CLASS_OTHER = "other"

DOC_CLASSES: tuple[str, ...] = (
    DOC_CLASS_PLAN, DOC_CLASS_SYSTEM, DOC_CLASS_PROJECT, DOC_CLASS_AGENT, DOC_CLASS_OTHER,
)

# NN_ con 2 o 3 dígitos SEGUIDO DE UNA PALABRA CLAVE DE PLAN.
#
# OJO — el prefijo numérico solo NO alcanza y clasificar por `^\d{2,3}_` a secas
# es un BUG MEDIDO: en este mismo repo, `00_VISION.md`, `02_ARCHITECTURE.md` y
# `03_DATA_MODEL.md` son documentación DEL PROYECTO y caerían como "plan"
# (medido 2026-08-01: 257 falsos "plan" con la regla laxa vs 240 con esta).
# La secuencia NN_ es compartida entre planes, incidentes y checklists, pero
# también la usan documentos de producto. Por eso: prefijo + palabra clave.
_NUMBERED_DOC_RE = re.compile(
    r"^\d{2,3}_(plan|incidente|checklist|auditoria|postmortem)_", re.IGNORECASE
)


def classify_doc_path(rel_path: str) -> str:
    """Clase de un documento a partir de su path relativo POSIX. Nunca lanza.

    Reglas EXACTAS, evaluadas en este orden (la primera que matchea gana):
      1. basename termina en ".agent.md"                      -> "agent"
      2. el path contiene el segmento de carpeta "sistema"    -> "system"
      3. basename matchea _NUMBERED_DOC_RE (NN_ + palabra)    -> "plan"
      4. basename termina en ".md"                            -> "project"
      5. cualquier otra cosa                                  -> "other"
    """
    try:
        norm = (rel_path or "").replace("\\", "/").strip().lower()
        if not norm:
            return DOC_CLASS_OTHER
        basename = norm.rsplit("/", 1)[-1]
        if basename.endswith(".agent.md"):
            return DOC_CLASS_AGENT
        if "sistema" in norm.split("/")[:-1]:
            return DOC_CLASS_SYSTEM
        if _NUMBERED_DOC_RE.match(basename):
            return DOC_CLASS_PLAN
        if basename.endswith(".md"):
            return DOC_CLASS_PROJECT
        return DOC_CLASS_OTHER
    except Exception:
        return DOC_CLASS_OTHER


def is_plan_doc(rel_path: str) -> bool:
    """True si el documento es un plan/checklist/incidente numerado."""
    return classify_doc_path(rel_path) == DOC_CLASS_PLAN


def summarize_classes(rel_paths: list[str]) -> dict[str, int]:
    """{clase: cantidad} sobre una lista de paths. Incluye TODAS las claves de
    DOC_CLASSES con 0 si no aparecen (forma garantizada para la UI)."""
    out = {c: 0 for c in DOC_CLASSES}
    for p in rel_paths or []:
        out[classify_doc_path(p)] += 1
    return out
```

**Tests (PRIMERO).** Agregar al final de `Stacky Agents/backend/tests/test_doc_evidence.py`:

- `test_plan284_classify_doc_path_tabla_completa` — tabla exacta, incluyendo el caso que hoy rompe todo:
  - `"docs/137_PLAN_DOCUMENTADOR_V2.md"` → `"plan"`
  - `"docs/20_INCIDENTE_ADO_241.md"` → `"plan"`
  - `"docs/25_CHECKLIST_NUEVO_RUNTIME.md"` → `"plan"`
  - `"docs/sistema/01-overview.md"` → `"system"`
  - `"docs/sistema/13-docs-rag-grafo.md"` → `"system"`
  - `"docs/arquitectura.md"` → `"project"`
  - `"prompts/Documentador.agent.md"` → `"agent"`
  - `"docs/sistema/error_fingerprints.json"` → `"system"` (gana la regla 2 antes que la extensión)
  - `"README.txt"` → `"other"`
  - `""` → `"other"`, `None` → `"other"`
  - **Caso frontera obligatorio 1:** `"docs/sistema/99_PLAN_FALSO.md"` → `"system"` (la regla 2 tiene prioridad sobre la 3; documentá esto en el test con un comentario).
  - **Casos frontera obligatorios 2 (los que hacen fallar la regla laxa — NO los omitas):**
    `"docs/00_VISION.md"` → `"project"`, `"docs/02_ARCHITECTURE.md"` → `"project"`,
    `"docs/03_DATA_MODEL.md"` → `"project"`, `"docs/14_MANUAL_PARA_AGENTES_WS2.md"` → `"project"`.
    Estos 4 archivos **existen de verdad** en `Stacky Agents/docs/` y son documentación del
    producto, no planes. Si tu regex los clasifica como `"plan"`, está mal y vas a sacar del
    corpus RAG la documentación de arquitectura del proyecto — exactamente el bug opuesto al
    que este plan viene a arreglar.
- `test_plan284_summarize_classes_forma_garantizada` — con una lista mixta, aserta el conteo correcto **y además** que el dict devuelto tiene exactamente las 5 claves de `DOC_CLASSES` aun cuando alguna sea 0 (presencia + ausencia en el mismo test).

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests/test_doc_evidence.py -q
```

**Criterio de aceptación binario:** el comando termina con `0 failed` y con **al menos 20 tests** (hoy son 18; se suman 2). Si el número total no subió, los tests nuevos no se recolectaron.

**Flag:** ninguna consume `doc_taxonomy` todavía (F0 es sustrato inerte).
**Runtimes:** Python puro, sin dependencia de runtime. Codex / Claude Code CLI / Copilot: idéntico.
**Trabajo del operador:** ninguno.

---

### F1 — Frontera dura PLANES vs PROYECTO (cierra el punto 2 del pedido)

**Objetivo:** que cada nodo del árbol documental, del grafo y del corpus RAG lleve su `doc_class`, y que los planes dejen de contaminar la salud y el retrieval del proyecto.
**Valor:** 240 documentos de plan dejan de disfrazarse de documentación del proyecto.

#### F1.1 — `doc_class` en el índice

**Archivo a editar:** `Stacky Agents/backend/services/doc_indexer.py`

En `_make_node` (`doc_indexer.py:138`), dentro del dict que hoy va de `:150` a `:160`, agregar **una** clave al final (antes de `"children"`):

```python
        "doc_class": _doc_class_for(rel_path),
```

En `_make_folder_node` (`doc_indexer.py:163`), dict `:165-175`, agregar la misma clave con valor `"other"` (una carpeta no es un documento).

Agregar el helper cerca de `_should_exclude` (`doc_indexer.py:89`):

```python
def _doc_class_for(rel_path: str) -> str:
    """Plan 284 — clase del documento. Con la flag OFF devuelve "" (campo inerte,
    aditivo: el frontend actual lo ignora). Nunca lanza."""
    try:
        from config import config
        if not bool(getattr(config, "STACKY_DOCS_TAXONOMY_ENABLED", False)):
            return ""
        from services import doc_taxonomy
        return doc_taxonomy.classify_doc_path(rel_path)
    except Exception:
        return ""
```

> **Cuidado con la cache:** `doc_indexer` cachea el índice 300 s (`_CACHE_TTL_SECONDS = 300`, `doc_indexer.py:61`). En los tests, llamá `doc_indexer.invalidate_cache()` (`doc_indexer.py:612`) antes de cada aserción, o vas a leer un árbol construido con la flag anterior.

#### F1.2 — `doc_class` en el grafo

**Archivo a editar:** `Stacky Agents/backend/services/doc_graph.py`

En `_serialize_node` (`doc_graph.py:232`), dict `:233-238`, agregar `"doc_class": ...` derivado del `path` del nodo con el mismo helper (importalo de `doc_taxonomy` con el mismo guard de flag). Con la flag OFF el valor es `""` y el payload queda equivalente al de hoy.

#### F1.3 — Los planes salen del cómputo de salud y del corpus RAG

**Archivo a editar:** `Stacky Agents/backend/services/doc_graph.py`, función `classify_doc_health` (`doc_graph.py:424`).
Con `STACKY_DOCS_TAXONOMY_ENABLED` ON, **excluir** de los nodos considerados aquellos cuyo `doc_class == "plan"`. Razón: la salud documental mide la doc **del proyecto**; 240 planes con frontmatter propio distorsionan `frontmatter_ratio` y el conteo de huérfanas.

**Archivo a editar:** `Stacky Agents/backend/services/docs_rag.py`, función `index_project` (`docs_rag.py:145`).
Después del `md_files = sorted(root.rglob("*.md"))` de `docs_rag.py:160`, insertar el filtro:

```python
    # Plan 284 — los documentos de plan no son documentación del proyecto:
    # con 240 planes contra 15 notas de sistema, el retrieval devolvía planes.
    from config import config as _cfg
    if bool(getattr(_cfg, "STACKY_DOCS_TAXONOMY_ENABLED", False)):
        from services import doc_taxonomy
        md_files = [
            f for f in md_files
            if not doc_taxonomy.is_plan_doc(f.relative_to(root).as_posix())
        ]
```

#### F1.4 — La API expone el resumen

**Archivo a editar:** `Stacky Agents/backend/api/docs.py`, endpoint `get_docs_index` (`api/docs.py:67`).
En el `jsonify` de `api/docs.py:122-129`, agregar la clave `"class_summary"` con el resultado de `doc_taxonomy.summarize_classes(...)` sobre los paths de archivo del árbol (recorrido recursivo, reusando el patrón de `count_files` de `api/docs.py:103-110`). Con la flag OFF, `{}`.

**Tests (PRIMERO).** Agregar a `Stacky Agents/backend/tests/test_documenter_v2_pipeline.py`:

- `test_plan284_index_node_lleva_doc_class` — con `monkeypatch.setattr(config.config, "STACKY_DOCS_TAXONOMY_ENABLED", True)` y `doc_indexer.invalidate_cache()`, construir el índice técnico y asertar que **existe al menos un nodo con `doc_class == "plan"`** y **al menos uno con `doc_class == "system"`** (presencia), y que **ningún nodo de archivo tiene `doc_class` ausente o `None`** (ausencia). Los dos asserts en el mismo test.
- `test_plan284_doc_class_inerte_con_flag_off` — con la flag en `False`, todo nodo de archivo tiene `doc_class == ""`, y además el árbol **sigue teniendo nodos** (si estuviera vacío, el assert de ausencia pasaría por accidente).
- `test_plan284_rag_excluye_planes` — armar un `tmp_path/docs` con 3 archivos: `137_PLAN_X.md`, `sistema/01-overview.md`, `guia.md`; correr `docs_rag.index_project` con la flag ON y asertar que los `file_path` indexados **contienen** `sistema/01-overview.md` y `guia.md` (presencia) y **no contienen** `137_PLAN_X.md` (ausencia).
- `test_plan284_salud_ignora_planes` — construir dos listas de nodos idénticas salvo que una suma 5 nodos `doc_class="plan"` sin frontmatter; asertar que `classify_doc_health` devuelve el **mismo** `frontmatter_ratio` en ambas con la flag ON, y **distinto** con la flag OFF (esto prueba que el filtro está vivo y que la flag lo gobierna).

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests/test_documenter_v2_pipeline.py -q
```

**Criterio de aceptación binario.** `0 failed` **y** este censo cumple las 4 condiciones de abajo.
Medición de referencia tomada el 2026-08-01 sobre `Stacky Agents/docs/`: **309** `.md` totales →
`plan=240`, `system=15`, `project=54`, `agent=0`, `other=0`.

```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -c @"
from services import doc_taxonomy as t
import pathlib
d = pathlib.Path(r'N:\GIT\RS\STACKY\Stacky\Stacky Agents\docs')
ps = [p.relative_to(d.parent).as_posix() for p in d.rglob('*.md')]
s = t.summarize_classes(ps)
print('total', len(ps), s)
print('C1 system==15        ->', s['system'] == 15)
print('C2 plan>=240         ->', s['plan'] >= 240)
print('C3 particion completa->', sum(s.values()) == len(ps))
print('C4 vision es project ->', t.classify_doc_path('docs/00_VISION.md') == 'project')
"@
```

Las 4 condiciones (`C1..C4`) deben imprimir `True`.
- **C1** es exacto: `docs/sistema/` es un conjunto cerrado y estable.
- **C2** es `>=` a propósito, **no `==`**: cada plan nuevo que se escriba incrementa el número, y
  un criterio con igualdad exacta se pondría rojo solo con el tiempo.
- **C3** prueba que la clasificación es una partición (ningún documento se pierde ni se cuenta dos veces).
- **C4** es el gate anti-regresión de la regla laxa.

**Flag:** `STACKY_DOCS_TAXONOMY_ENABLED` (default **ON**).
**Runtimes:** sin impacto — es indexación local. Idéntico en los 3.
**Trabajo del operador:** ninguno. El árbol se ve igual; gana un agrupador.

---

### F2 — La nota del operador llega al prompt (cierra el punto 3 del pedido)

**Objetivo:** que el operador pueda escribir indicaciones libres al lanzar el Documentador, y que esas indicaciones **lleguen demostrablemente al prompt del agente**.
**Valor:** el Documentador deja de ser una caja negra de un solo botón.

> **El gate real de esta fase no es "existe el campo", es "existe un consumidor de producción".** Un campo que viaja, se persiste y nadie inyecta al prompt es exactamente el patrón *construido, testeado y jamás cableado*. El criterio de aceptación de F2 se corre sobre `render_blocks`, que es la función que arma el texto que el modelo ve.

#### F2.1 — UI: el campo

**Archivo a editar:** `Stacky Agents/frontend/src/components/docs/DocumenterButton.tsx`

- Agregar estado: `const [note, setNote] = useState("");` junto a los de `DocumenterButton.tsx:17-21`.
- Agregar, antes del `<button>` de `DocumenterButton.tsx:83`, un `<textarea>` con:
  - `value={note}`, `onChange={(e) => setNote(e.target.value)}`
  - `placeholder="Indicaciones extra para el Documentador (opcional). Ej: 'enfocate en el módulo de pipelines y no toques la doc de DevOps'."`
  - `maxLength={4000}`
  - `disabled={launching || summary.running}`
  - `aria-label="Nota para el Documentador"`
  - Debajo, un contador `{note.length}/4000`.
- En `launch` (`DocumenterButton.tsx:47`), cambiar la llamada de `DocumenterButton.tsx:52` a **`Docs.documenterRun(projectName, normalizeOperatorNote(note))`** y agregar `note` a las deps del `useCallback` (`DocumenterButton.tsx:63`, hoy `}, [projectName]);`).

> **FIX C18 — una sola instrucción, no dos.** La v1 decía aquí `note.trim() || undefined` y más abajo, en el bloque de frontend, `normalizeOperatorNote(note)`, para **la misma línea**. Un modelo menor no puede resolver cuál gana. Manda `normalizeOperatorNote` (es la que tiene test). Importala desde `../../docs/documenterModel`.
- El textarea **no se limpia** al terminar el run: el operador suele reintentar afinando la nota.

#### F2.2 — API cliente

**Archivo a editar:** `Stacky Agents/frontend/src/api/endpoints.ts`
Reemplazar `documenterRun` (`endpoints.ts:3648-3652`) por:

```ts
  /** Plan 113 — lanza el Documentador en background. 404 si la flag OFF, 409 si busy.
   *  Plan 284 — `operatorNote`: indicaciones libres del operador que se inyectan
   *  como context block en el prompt del agente. */
  documenterRun: (
    project?: string,
    operatorNote?: string
  ): Promise<{ ok: boolean; run_id?: string; error?: string }> =>
    api.post<{ ok: boolean; run_id?: string; error?: string }>(
      `/api/docs/documenter/run`,
      {
        ...(project ? { project } : {}),
        ...(operatorNote ? { operator_note: operatorNote } : {}),
      }
    ),
```

> Nota: la firma sigue siendo compatible — `documenterRun(project)` sin segundo argumento produce **el mismo body de hoy**.

#### F2.3 — Endpoint

**Archivo a editar:** `Stacky Agents/backend/api/docs.py`, `documenter_run` (`api/docs.py:269`).
Después de leer `runtime` (`api/docs.py:283`), agregar:

```python
    operator_note = ""
    if bool(getattr(config, "STACKY_DOCS_OPERATOR_NOTE_ENABLED", False)):
        raw_note = body.get("operator_note")
        if raw_note is not None and not isinstance(raw_note, str):
            return jsonify({"ok": False, "error": "operator_note_invalid",
                            "message": "La nota debe ser texto."}), 400
        max_chars = int(getattr(config, "STACKY_DOCS_OPERATOR_NOTE_MAX_CHARS", 4000))
        operator_note = (raw_note or "").strip()[:max_chars]
```

y pasarlo: `run_id = doc_documenter.start_documenter_run(project, runtime, operator_note=operator_note)` (`api/docs.py:286`).

> **Truncar, no rechazar por largo.** Un 400 por nota larga es trabajo extra para el operador; el truncado silencioso a 4000 chars no lo es. El rechazo 400 queda **sólo** para tipo inválido.

#### F2.4 — Persistencia con la corrida

**Archivo a editar:** `Stacky Agents/backend/services/doc_documenter.py`

- `start_documenter_run` (`doc_documenter.py:696`): agregar el kwarg `operator_note: str = ""` y propagarlo por el `kwargs` del `Thread` (`doc_documenter.py:712`).
- `_new_run_record` (`doc_documenter.py:686`): agregar `"operator_note": ""` al dict.
- `_run_documenter_thread` (`doc_documenter.py:813`) y `run_documenter` (`doc_documenter.py:824`): agregar el mismo kwarg y propagarlo.
- En `run_documenter`, incluir `"operator_note": operator_note` en el `report` (`doc_documenter.py:941-958`) **y** en el snapshot inicial `_persist_run_report` (`doc_documenter.py:861-866`). Así la nota queda en el `.json` del historial y sobrevive a un restart.

#### F2.5 — CONSUMIDOR DE PRODUCCIÓN: la nota entra al prompt

**Archivo a editar:** `Stacky Agents/backend/services/doc_documenter.py`

Agregar el bloque:

```python
def _operator_note_block(operator_note: str) -> dict | None:
    """Plan 284 — context block con las indicaciones libres del operador.

    Devuelve None si la nota está vacía o la flag está OFF (el prompt queda
    byte-idéntico al de hoy). El texto se inyecta TAL CUAL: el enforcement de
    los guardarraíles NO depende del prompt (lo hace apply_proposals), así que
    una nota no puede aflojar docs/sistema/ read-only ni el anti-traversal.
    """
    from config import config as _cfg
    if not bool(getattr(_cfg, "STACKY_DOCS_OPERATOR_NOTE_ENABLED", False)):
        return None
    note = (operator_note or "").strip()
    if not note:
        return None
    return {
        "id": "operator-note",
        "kind": "operator-note",
        "title": "INDICACIONES DEL OPERADOR (prioridad alta)",
        "content": (
            "El operador escribió estas indicaciones al lanzarte. Respetalas salvo "
            "que contradigan las reglas duras de tu system prompt (marcas de "
            "confianza, formato de bloques, docs/sistema/ read-only):\n\n" + note
        ),
        "source": {"type": "operator", "readonly": True},
    }
```

Cambiar la firma de `build_context_for_mode` (`doc_documenter.py:280`) a:

```python
def build_context_for_mode(mode: DocumenterMode, plan: DocumenterPlan,
                           project_name: str, operator_note: str = "") -> list[dict]:
```

y, **antes** del `blocks.append(_sistema_readonly_block(project_name))` de `doc_documenter.py:300`, insertar:

```python
    note_block = _operator_note_block(operator_note)
    if note_block is not None:
        blocks.insert(0, note_block)   # primero: el modelo lo lee antes que el resto
```

En `run_documenter`, la llamada de `doc_documenter.py:890` pasa a `ctx = build_context_for_mode(mode, plan, project_name, operator_note)`.

> El parámetro tiene default `""` ⇒ todos los llamadores existentes siguen compilando sin cambios.

**Tests (PRIMERO).** Agregar a `Stacky Agents/backend/tests/test_documenter_v2_pipeline.py`:

- **`test_plan284_nota_del_operador_llega_al_prompt`** — el test que importa. Pasos exactos:
  1. `monkeypatch.setattr(config.config, "STACKY_DOCS_OPERATOR_NOTE_ENABLED", True)`
  2. `blocks = doc_documenter.build_context_for_mode(DocumenterMode.ENRIQUECER, plan, "P", "NOTA_SENTINELA_284")`
  3. `from prompt_builder import render_blocks; texto = render_blocks(blocks)`
  4. `assert "NOTA_SENTINELA_284" in texto` ← **la nota llega al texto real del prompt**
  5. `assert "INDICACIONES DEL OPERADOR" in texto` (el título también se renderiza)
  6. `assert blocks[0]["id"] == "operator-note"` (va primero)
  7. **Presencia de control:** `assert "docs/sistema/" in texto` — prueba que el bloque canónico sigue ahí y que el render no está vacío por un error de setup.
- `test_plan284_nota_vacia_no_agrega_bloque` — con nota `""` y con nota `"   "`, `build_context_for_mode` devuelve **la misma cantidad de bloques** que sin el argumento, y ninguno tiene `id == "operator-note"` (ausencia) **y** el bloque canónico sigue presente (presencia).
- `test_plan284_nota_inerte_con_flag_off` — flag en `False` + nota no vacía ⇒ ningún bloque `operator-note`, pero el resto de los bloques intacto.
- `test_plan284_nota_se_persiste_en_el_reporte` — `run_documenter` (con `invoke_documenter` monkeypatcheado a `lambda *a, **k: []` para no llamar al LLM) devuelve un report cuyo `report["operator_note"] == "hola"`.
- **`test_plan284_nota_viaja_de_run_documenter_al_prompt`** — **[FIX C6 — el test que la v1 no tenía y que es el gate real de esta fase].**

  **Por qué existe.** El censo AST prueba que `_operator_note_block` se llama **dentro de** `build_context_for_mode`. No prueba nada sobre los **otros 4 saltos** de la cadena: `documenter_run` → `start_documenter_run` → `_run_documenter_thread` → `run_documenter` → `build_context_for_mode`. Un `operator_note` que se persiste en el reporte y nunca se pasa hacia abajo satisface *todos* los tests de la v1 y aun así **jamás llega al modelo**. Es la deuda nº 1 de este repo: código construido, testeado, verde y jamás cableado.

  **Pasos exactos:**
  1. `monkeypatch.setattr(config.config, "STACKY_DOCS_OPERATOR_NOTE_ENABLED", True)`
  2. Capturá los bloques que recibe el LLM:
     ```python
     capturado = {}
     def _fake_invoke(mode, context_blocks, project_name, runtime, **kw):
         capturado["blocks"] = context_blocks
         return []
     monkeypatch.setattr(doc_documenter, "invoke_documenter", _fake_invoke)
     ```
  3. `doc_documenter.run_documenter("P", "claude_code_cli", operator_note="CENTINELA_CABLE_284")`
  4. **Presencia (lo que importa):**
     `from prompt_builder import render_blocks` →
     `assert "CENTINELA_CABLE_284" in render_blocks(capturado["blocks"])`
  5. **Presencia de control:** `assert capturado.get("blocks")`, para que el paso 4 no pueda pasar por accidente sobre una lista vacía si el monkeypatch no enganchó.
  6. **Ausencia gemela:** repetir con `operator_note=""` y asertar que el centinela **no** está, pero que `capturado["blocks"]` **sigue teniendo bloques**.

  Si este test pasa, la nota del operador está cableada de punta a punta. Si el resto de F2 pasa pero éste falla, F2 **no está hecha**, por más verde que se vea el panel.

**Frontend.** Agregar a `Stacky Agents/frontend/src/docs/documenterModel.test.ts` un test del helper puro nuevo. Para que haya lógica testeable sin RTL, agregar a `Stacky Agents/frontend/src/docs/documenterModel.ts`:

```ts
/** Plan 284 — normaliza la nota del operador antes de mandarla al backend.
 *  Devuelve undefined si no hay nada que mandar (así el body queda como el de hoy). */
export function normalizeOperatorNote(raw: string, maxChars = 4000): string | undefined {
  const trimmed = (raw ?? "").trim();
  if (!trimmed) return undefined;
  return trimmed.slice(0, maxChars);
}
```

y usarla en `DocumenterButton.tsx` (`Docs.documenterRun(projectName, normalizeOperatorNote(note))`).
Test `test_plan284_normalizeOperatorNote`: `""` → `undefined`; `"   "` → `undefined`; `"  hola  "` → `"hola"`; string de 5000 chars → largo exactamente 4000.

**Comandos:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests/test_documenter_v2_pipeline.py -q
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/docs/documenterModel.test.ts
npx tsc --noEmit
```

**Criterio de aceptación binario (los 3 tienen que dar):**
1. `pytest tests/test_documenter_v2_pipeline.py -q` → `0 failed`.
2. `npx tsc --noEmit` → sin salida (exit 0).
3. Este censo devuelve **exactamente 1** (existe un consumidor de producción de `_operator_note_block`, no sólo su definición):
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -c "import ast,pathlib; src=pathlib.Path('services/doc_documenter.py').read_text(encoding='utf-8'); t=ast.parse(src); print(sum(1 for n in ast.walk(t) if isinstance(n,ast.Call) and getattr(n.func,'id','')=='_operator_note_block'))"
```

**Flag:** `STACKY_DOCS_OPERATOR_NOTE_ENABLED` (default **ON**), `STACKY_DOCS_OPERATOR_NOTE_MAX_CHARS` (4000).
**Runtimes:** la nota viaja como `context_block`, que `agent_runner.run_agent` ya propaga a los 3 runners (`claude_code_cli_runner.py:105`, `codex_cli_runner.py:91`, y el puente Copilot). **Fallback:** si un runtime trunca el prompt, la nota va **primera** (`blocks.insert(0, ...)`), que es la posición con más chance de sobrevivir a un recorte por presupuesto de contexto.
**Trabajo del operador:** ninguno obligatorio — el campo vacío deja el flujo 1-click intacto.

---

### F3 — El gate de citas deja de ser decorativo (cierra el punto 7 del pedido)

**Objetivo:** que un archivo con citas `archivo:línea` que no resuelven **no se escriba**, en vez de escribirse y reportarse.
**Valor:** la marca `[V]` pasa a significar algo. Es la diferencia entre documentación y prosa plausible.

**Archivo a editar:** `Stacky Agents/backend/services/doc_documenter.py`, función `apply_proposals` (`doc_documenter.py:563`).

Cambio conceptual: hoy el orden es **escribir → verificar**. Pasa a ser **verificar → decidir → escribir**.

```python
        if not prop.marks_ok:
            result.skipped.append((prop.path, "missing_confidence_marks"))
            continue

        # ---- Plan 284: GATE DE CITAS (antes existía sólo como reporte) ----
        citations = None
        if workspace_root is not None:
            from services import doc_evidence
            citations = doc_evidence.verify_citations(
                prop.content + " " + ",".join(prop.sources), workspace_root)
            if _citation_gate_enabled():
                verdict = evaluate_citation_gate(citations)
                if not verdict["passed"]:
                    result.skipped.append((prop.path, verdict["reason"]))
                    result.files.append({
                        "path": norm, "action": prop.action, "citations": citations,
                        "content_preview": prop.content[:_PREVIEW_MAX_CHARS],
                        "rejected": True, "reject_reason": verdict["reason"],
                    })
                    continue
        # -------------------------------------------------------------------
        try:
            dest = (root / norm)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(prop.content, encoding="utf-8")
            result.written.append(norm)
            if citations is not None:
                result.files.append({
                    "path": norm, "action": prop.action, "citations": citations,
                    "content_preview": prop.content[:_PREVIEW_MAX_CHARS],
                    "rejected": False, "reject_reason": "",
                })
        except Exception as exc:
            ...
```

Agregar la función pura (es la que se testea sola):

```python
def evaluate_citation_gate(citations: dict, *, min_ratio: float | None = None,
                           ) -> dict:
    """Plan 284 — veredicto del gate de citas. PURA, sin I/O. Nunca lanza.

    Entrada: el dict de doc_evidence.verify_citations → {"total","ok","bad"}.
    Salida:  {"passed": bool, "ratio": float, "reason": str}

    Reglas EXACTAS:
      - total == 0  -> passed=True, ratio=1.0, reason=""      (un doc sin citas
        no se rechaza: puede ser legítimamente todo [INF]/[NV]. El que miente es
        el que cita mal, no el que no cita.)
      - ratio = ok / total
      - ratio >= min_ratio -> passed=True, reason=""
      - ratio <  min_ratio -> passed=False,
        reason="citations_below_threshold:{ok}/{total}"
    """
    from config import config as _cfg
    if min_ratio is None:
        min_ratio = float(getattr(_cfg, "STACKY_DOCS_CITATION_GATE_MIN_RATIO", 0.8))
    total = int((citations or {}).get("total", 0) or 0)
    ok = int((citations or {}).get("ok", 0) or 0)
    if total <= 0:
        return {"passed": True, "ratio": 1.0, "reason": ""}
    ratio = ok / total
    if ratio >= min_ratio:
        return {"passed": True, "ratio": ratio, "reason": ""}
    return {"passed": False, "ratio": ratio,
            "reason": f"citations_below_threshold:{ok}/{total}"}


def _citation_gate_enabled() -> bool:
    from config import config as _cfg
    return bool(getattr(_cfg, "STACKY_DOCS_CITATION_GATE_ENABLED", False))
```

**Cambio necesario aguas arriba:** hoy `workspace_root` se pasa a `apply_proposals` sólo con V2 ON (`doc_documenter.py:915`). Cambiar esa línea a:

```python
        workspace_root=(workspace_root if (_v2_enabled() or _citation_gate_enabled()) else None),
```

**Etiqueta legible en la UI.** En `Stacky Agents/frontend/src/docs/documenterModel.ts`, `formatSkipReason` (`documenterModel.ts:76`) debe mapear el prefijo nuevo. Como la razón trae el detalle (`citations_below_threshold:2/9`), el mapeo es por prefijo:

```ts
  if (reason.startsWith("citations_below_threshold")) {
    const detail = reason.split(":")[1] ?? "";
    return `Rechazado: citas archivo:línea que no existen (${detail} verificadas)`;
  }
```

**Tests (PRIMERO).** Agregar a `Stacky Agents/backend/tests/test_doc_evidence.py`:

- `test_plan284_evaluate_citation_gate_tabla` — tabla completa con `min_ratio=0.8` explícito (no dependas del config en un test puro):
  - `{"total":0,"ok":0,"bad":[]}` → `passed=True`, `ratio=1.0`
  - `{"total":10,"ok":10,"bad":[]}` → `passed=True`, `ratio=1.0`
  - `{"total":10,"ok":8,"bad":[...]}` → `passed=True` (frontera exacta: `0.8 >= 0.8`)
  - `{"total":10,"ok":7,"bad":[...]}` → `passed=False`, `reason == "citations_below_threshold:7/10"`
  - `{"total":1,"ok":0,"bad":["x.py:9"]}` → `passed=False`
  - `None` → `passed=True` (degradación, nunca lanza)

Agregar a `Stacky Agents/backend/tests/test_documenter_v2_pipeline.py`:

- **`test_plan284_gate_no_escribe_el_archivo_con_citas_falsas`** — el test que prueba el comportamiento real:
  1. `tmp_path` como `workspace_root`, con **un** archivo real `real.py` de 3 líneas.
  2. Dos propuestas: `buena.md` con `[V] real.py:2` y `mala.md` con `[V] real.py:999` + `[V] inexistente.py:1`.
  3. `apply_proposals([...], target_root=str(tmp_out), branch_name=None, workspace_root=str(tmp_path))` con la flag ON.
  4. **Presencia:** `"buena.md" in result.written` y `(tmp_out/"buena.md").is_file()`.
  5. **Ausencia:** `"mala.md" not in result.written` y `not (tmp_out/"mala.md").exists()` ← **el archivo NO existe en disco**; esto es lo que hoy falla.
  6. `("mala.md", "citations_below_threshold:0/2") in result.skipped`.
- `test_plan284_gate_off_conserva_comportamiento_137` — con `STACKY_DOCS_CITATION_GATE_ENABLED=False`, **ambos** archivos se escriben (incluido el de citas falsas) y `result.files` sigue trayendo el conteo de citas. Prueba backward-compat exacta.
- `test_plan284_doc_sin_citas_no_se_rechaza` — propuesta con marcas `[INF]`/`[NV]` y cero citas ⇒ se escribe.

**Comandos:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests/test_doc_evidence.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_documenter_v2_pipeline.py -q
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/docs/documenterModel.test.ts
```

**Criterio de aceptación binario:** los 3 comandos en `0 failed`, y este censo por AST devuelve **exactamente 0** (la escritura ya no ocurre antes de la verificación):

```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -c "import ast,pathlib; src=pathlib.Path('services/doc_documenter.py').read_text(encoding='utf-8'); fn=[n for n in ast.walk(ast.parse(src)) if isinstance(n,ast.FunctionDef) and n.name=='apply_proposals'][0]; ws=[n.lineno for n in ast.walk(fn) if isinstance(n,ast.Call) and getattr(n.func,'attr','')=='write_text']; vc=[n.lineno for n in ast.walk(fn) if isinstance(n,ast.Call) and getattr(n.func,'attr','')=='verify_citations']; print(sum(1 for w in ws for v in vc if w < v))"
```

**Flag:** `STACKY_DOCS_CITATION_GATE_ENABLED` (default **ON**), `STACKY_DOCS_CITATION_GATE_MIN_RATIO` (0.8).
**Runtimes:** el gate corre sobre el texto ya devuelto, después de la invocación. Idéntico en los 3. **Fallback:** un runtime que cite peor produce más rechazos y el operador lo ve en el panel con la razón exacta — no falla en silencio.
**Trabajo del operador:** ninguno.

---

### F4 — Minería del corpus de tickets con triage auditable (cierra el punto 6 del pedido)

**Objetivo:** barrer los 228 tickets (ADO + GitLab + demo) y separar **señal** de **ruido** con criterios deterministas, auditables y explicables, sin pedirle el juicio al LLM.
**Valor:** la documentación gana la historia real del proyecto, sin arrastrar tickets obsoletos o mal planteados.

> **Por qué el triage NO lo hace el LLM.** Un scoring por LLM sobre 228 tickets es caro, no reproducible y no auditable. Este triage es aritmética sobre campos que ya están en la tabla: se puede explicar, testear y discutir. El LLM recibe **sólo los tickets que pasaron**, con el motivo del veredicto adjunto.

**Archivo a CREAR:** `Stacky Agents/backend/services/doc_ticket_mining.py`

```python
"""Plan 284 — Minería determinista del corpus de tickets para documentación.

Barre los tickets del proyecto y los clasifica en señal vs ruido con criterios
auditables (sin LLM). El resultado alimenta el contexto del Documentador.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Umbrales del triage. Constantes con nombre: son el contrato auditable.
MIN_DESCRIPTION_CHARS = 200      # 112 de 228 tickets caen debajo (medido 2026-08-01)
MIN_TITLE_CHARS = 15
STRONG_SIGNAL_CHARS = 800

# Títulos que no aportan nada aunque el ticket exista.
_NOISE_TITLE_RE = re.compile(
    r"^\s*(test|prueba|tmp|temp|borrar|delete|asdf|xxx+|aaa+|sin titulo|untitled|todo)\b",
    re.IGNORECASE,
)
# Tickets sintéticos del propio Stacky (no son historia del proyecto).
_SYNTHETIC_TRACKERS = frozenset({"demo"})

# ── FIX C3 (bloqueante de la v1) ──────────────────────────────────────────
# La v1 hacía: _SYNTHETIC_ADO_IDS = frozenset({-7}) y evaluaba `external_id in
# _SYNTHETIC_ADO_IDS`. Estaba mal por DOS motivos, ambos medidos en la base viva
# el 2026-08-01:
#   1) -7 es sentinela de **ado_id** (doc_documenter.py:304
#      `_CONVERSATION_ADO_ID = -7`), NO de external_id. La fila cuyo
#      external_id == -7 tiene ado_id == -2: es otro sentinela distinto.
#   2) No son "unos pocos": hay **103 filas con ado_id < 0** de 228. Los
#      sentinelas observados van (ado_id -2, -4, ...) x (external_id -4 .. -146+).
# Con el frozenset de un elemento, el filtro capturaba ~1 de 103.
# Regla correcta: cualquier id negativo es sintético. Es aritmética, no catálogo.
def _es_sintetico(ado_id: int | None, external_id: int | None) -> bool:
    """True si el ticket es interno de Stacky (ids sentinela negativos)."""
    for v in (ado_id, external_id):
        try:
            if v is not None and int(v) < 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


# ── FIX C13 — estados que marcan un ticket como CERRADO/OBSOLETO ──────────
# El operador pidió explícitamente distinguir "obsoletos". La v1 aceptaba
# `ado_state` como parámetro y NUNCA lo usaba. Estos son los estados REALES
# medidos en la base viva (2026-08-01), con su conteo:
#   Active 109 | opened 63 | Done 23 | Doing 12 | Reviewed by Dev 11
#   To Do 6 | Done by dev 2 | New 1 | Done by AI 1
# Un ticket cerrado NO es basura: documenta lo que YA se hizo, que es
# justamente la historia que buscamos. Pero un ticket cerrado y ADEMÁS flaco
# no aporta nada. Por eso el cierre no penaliza solo: modula.
_CLOSED_STATES = frozenset({
    "done", "done by dev", "done by ai", "closed", "resolved", "completed",
})
_ACTIVE_STATES = frozenset({
    "active", "opened", "doing", "new", "to do", "reviewed by dev",
})


@dataclass
class TicketVerdict:
    ticket_id: int
    external_id: int | None
    tracker_type: str
    title: str
    verdict: str            # "signal" | "noise"
    reasons: list[str] = field(default_factory=list)
    score: int = 0


def classify_ticket(*, ticket_id: int, ado_id: int | None,
                    external_id: int | None, tracker_type: str,
                    title: str, description: str, ado_state: str,
                    work_item_type: str) -> TicketVerdict:
    """Veredicto determinista de un ticket. PURA, sin I/O. Nunca lanza.

    OJO v2: la firma cambió respecto de la v1 — ahora recibe **ado_id** además
    de external_id (fix C3: los sentinelas sintéticos viven en ado_id).

    Puntuación (suma de enteros; >= 2 => "signal"):
      +2  len(description) >= STRONG_SIGNAL_CHARS      (descripción rica)
      +1  len(description) >= MIN_DESCRIPTION_CHARS    (descripción mínima)
      +1  len(title.strip()) >= MIN_TITLE_CHARS        (título descriptivo)
      +1  work_item_type no vacío y distinto de "Task" (épicas/features documentan mejor)
      +1  ado_state cerrado Y descripción >= MIN_DESCRIPTION_CHARS
          (fix C13: un ticket TERMINADO y bien descrito es la mejor historia
           que existe — es trabajo real, hecho y contado)
      -2  ado_state cerrado Y descripción < MIN_DESCRIPTION_CHARS
          (fix C13: cerrado y flaco = obsoleto, exactamente la "basura" del pedido)
      -3  tracker_type en _SYNTHETIC_TRACKERS
      -3  _es_sintetico(ado_id, external_id)           (fix C3)
      -2  el título matchea _NOISE_TITLE_RE
      -2  description vacía

    `reasons` guarda un string por regla aplicada (auditoría: el operador puede
    leer POR QUÉ un ticket quedó afuera).
    """
    reasons: list[str] = []
    score = 0
    desc = (description or "").strip()
    ttl = (title or "").strip()
    estado = (ado_state or "").strip().lower()

    if len(desc) >= STRONG_SIGNAL_CHARS:
        score += 2; reasons.append(f"descripcion_extensa:{len(desc)}")
    if len(desc) >= MIN_DESCRIPTION_CHARS:
        score += 1; reasons.append(f"descripcion_suficiente:{len(desc)}")
    if len(ttl) >= MIN_TITLE_CHARS:
        score += 1; reasons.append(f"titulo_descriptivo:{len(ttl)}")
    wit = (work_item_type or "").strip()
    if wit and wit.lower() != "task":
        score += 1; reasons.append(f"tipo_jerarquico:{wit}")
    if estado in _CLOSED_STATES:
        if len(desc) >= MIN_DESCRIPTION_CHARS:
            score += 1; reasons.append(f"cerrado_y_documentado:{estado}")
        else:
            score -= 2; reasons.append(f"cerrado_sin_contenido:{estado}")
    if (tracker_type or "").strip().lower() in _SYNTHETIC_TRACKERS:
        score -= 3; reasons.append("tracker_sintetico")
    if _es_sintetico(ado_id, external_id):
        score -= 3; reasons.append("ticket_interno_de_stacky")
    if _NOISE_TITLE_RE.match(ttl):
        score -= 2; reasons.append("titulo_ruido")
    if not desc:
        score -= 2; reasons.append("sin_descripcion")

    verdict = "signal" if score >= 2 else "noise"
    return TicketVerdict(ticket_id=ticket_id, external_id=external_id,
                         tracker_type=(tracker_type or ""), title=ttl,
                         verdict=verdict, reasons=reasons, score=score)


def mine_project_tickets(project_name: str, *, max_tickets: int | None = None,
                         scope: str = "project") -> dict:
    """Barre los tickets y devuelve el resumen del triage.

    `scope`:
      - "project" (default): sólo los del proyecto, con match CASE-INSENSITIVE.
      - "all": todo el corpus, sin filtro de proyecto.

    Salida (forma GARANTIZADA, todas las claves siempre presentes):
      {"enabled": bool, "scope": str, "total": int, "signal": int, "noise": int,
       "by_tracker": {tracker: int}, "verdicts": [TicketVerdict...],
       "truncated": bool}

    Con la flag OFF devuelve la forma completa con enabled=False y ceros.
    Nunca lanza: ante error de DB loguea y devuelve la forma vacía.
    """
    from config import config as _cfg
    empty = {"enabled": False, "scope": scope, "total": 0, "signal": 0,
             "noise": 0, "by_tracker": {}, "verdicts": [], "truncated": False}
    if not bool(getattr(_cfg, "STACKY_DOCS_TICKET_MINING_ENABLED", False)):
        return empty
    cap = int(max_tickets if max_tickets is not None
              else getattr(_cfg, "STACKY_DOCS_TICKET_MINING_MAX", 500))
    try:
        from sqlalchemy import func
        from db import session_scope
        from models import Ticket
        verdicts: list[TicketVerdict] = []
        by_tracker: dict[str, int] = {}
        with session_scope() as session:
            q = session.query(Ticket)
            if scope != "all":
                # FIX C24: 'p' (49 filas) y 'P' (44) son el MISMO proyecto
                # partido en dos claves porque la comparación de SQLite es
                # sensible a mayúsculas. Un == exacto pierde la mitad del
                # corpus sin avisar. Comparamos en minúsculas.
                q = q.filter(func.lower(Ticket.stacky_project_name)
                             == (project_name or "").strip().lower())
            q = q.order_by(Ticket.id)
            total_rows = q.count()
            for t in q.limit(cap).all():
                v = classify_ticket(
                    ticket_id=t.id, ado_id=t.ado_id, external_id=t.external_id,
                    tracker_type=t.tracker_type or "", title=t.title or "",
                    description=t.description or "", ado_state=t.ado_state or "",
                    work_item_type=t.work_item_type or "")
                verdicts.append(v)
                key = v.tracker_type or "desconocido"
                by_tracker[key] = by_tracker.get(key, 0) + 1
        signal = sum(1 for v in verdicts if v.verdict == "signal")
        return {"enabled": True, "scope": scope, "total": len(verdicts),
                "signal": signal, "noise": len(verdicts) - signal,
                "by_tracker": by_tracker, "verdicts": verdicts,
                "truncated": total_rows > cap}
    except Exception as exc:
        logger.warning("doc_ticket_mining: barrido fallo para %s: %s", project_name, exc)
        return dict(empty, enabled=True)


def build_tickets_context_block(mining: dict, *, max_chars: int = 12000
                                ) -> dict | None:
    """Context block con SOLO los tickets 'signal'. None si no hay ninguno.

    FIX C11: la v1 dejaba este cuerpo como `...` (inimplementable para un
    modelo menor). Acá va completo.

    Las claves del dict devuelto son las que consume prompt_builder.render_blocks
    (verificado: usa `kind`, `title`, `content`; ignora el resto).
    """
    verdicts = (mining or {}).get("verdicts") or []
    signal = [v for v in verdicts if getattr(v, "verdict", "") == "signal"]
    if not signal:
        return None
    lineas: list[str] = []
    usado = 0
    truncado = False
    for v in signal:
        motivos = ", ".join(v.reasons[:3])
        ident = v.external_id if v.external_id is not None else v.ticket_id
        linea = f"[{v.tracker_type or 'desconocido'}#{ident}] {v.title} — {motivos}"
        if usado + len(linea) + 1 > max_chars:
            truncado = True
            break
        lineas.append(linea)
        usado += len(linea) + 1
    cuerpo = "\n".join(lineas)
    if truncado:
        cuerpo += "\n[...corpus truncado]"
    total = int(mining.get("total", 0) or 0)
    ruido = int(mining.get("noise", 0) or 0)
    return {
        "id": "tickets-signal",
        "kind": "tickets-signal",
        "title": "HISTORIA DEL PROYECTO SEGÚN SUS TICKETS (triage determinista)",
        "content": (
            f"Se barrieron {total} tickets; {len(signal)} aportan historia "
            f"documentable y {ruido} se descartaron por ruido/obsolescencia.\n"
            f"Usá estos tickets como CONTEXTO HISTÓRICO. No los cites como "
            f"archivo:línea: no son código, y una cita inventada te va a hacer "
            f"rechazar el archivo por el gate de citas.\n\n" + cuerpo
        ),
        "source": {"type": "tickets", "readonly": True},
    }
```

**Cableado (consumidor de producción).** En `Stacky Agents/backend/services/doc_documenter.py`, dentro de `build_context_for_mode`, para los modos `RECONSTRUIR` y `COMPLETAR` (rama de `doc_documenter.py:293-296`), agregar después del loop de módulos:

```python
        mining = doc_ticket_mining.mine_project_tickets(project_name)
        tickets_block = doc_ticket_mining.build_tickets_context_block(mining)
        if tickets_block is not None:
            blocks.append(tickets_block)
```

y guardar el resumen en el run record: `_update_run(run_id, ticket_mining={k: v for k, v in mining.items() if k != "verdicts"})` (los veredictos individuales no van al record: son 228 objetos).

**Tests (PRIMERO).** Agregar a `Stacky Agents/backend/tests/test_documenter_v2_pipeline.py`:

- `test_plan284_classify_ticket_tabla` — **[REESCRITA EN v2 — FIX C12]**.

  > **Por qué se reescribió.** La v1 decía cosas como *"Ticket `tracker_type="demo"` con descripción larga → `noise` (score 3-3=0)"*. Esa aritmética sólo cierra si la descripción está entre 200 y 799 chars **y** el tipo no es `Task`. Si el implementador escribe una descripción de 1200 chars — que es lo que "larga" sugiere — el score es 5-3=**2** ⇒ **`signal`**, y el test sale rojo. El riesgo real no es el rojo: es que alguien "arregle" el test debilitando el assert. **Cada fila fija ahora TODOS los campos.** Todos los casos usan `ado_state="Active"` salvo donde se indique.

  | # | ado_id | external_id | tracker | título (chars) | desc (chars) | work_item_type | ado_state | score | veredicto |
  |---|---|---|---|---|---|---|---|---|---|
  | 1 | 1001 | 1001 | azure_devops | 40 | 1200 | `Epic` | Active | **5** | signal |
  | 2 | 1002 | 1002 | azure_devops | 20 | 250 | `Task` | Active | **2** | signal (frontera) |
  | 3 | 1003 | 1003 | azure_devops | 20 | 199 | `Task` | Active | **1** | noise (frontera) |
  | 4 | 1004 | 1004 | azure_devops | 20 | 0 | `Task` | Active | **-1** | noise + `sin_descripcion` |
  | 5 | 1005 | 1005 | **demo** | 20 | 300 | `Epic` | Active | **0** | noise + `tracker_sintetico` |
  | 6 | **-2** | **-7** | azure_devops | 20 | 300 | `Epic` | Active | **0** | noise + `ticket_interno_de_stacky` |
  | 7 | 1007 | 1007 | azure_devops | `"test"` (4) | 300 | `Task` | Active | **-1** | noise + `titulo_ruido` |
  | 8 | 1008 | 1008 | **gitlab** | 40 | 1200 | `Issue` | opened | **5** | signal (**multiproveedor: no favorece a ADO**) |
  | 9 | 1009 | 1009 | azure_devops | 40 | 1200 | `Epic` | **Done** | **6** | signal + `cerrado_y_documentado` |
  | 10 | 1010 | 1010 | azure_devops | 20 | 50 | `Task` | **Done** | **-1** | noise + `cerrado_sin_contenido` (**el "obsoleto" del pedido**) |

  La fila **6** es el caso que la v1 tenía roto (C3): con `external_id=-7` **y** `ado_id=-2`, la regla vieja no lo detectaba porque miraba `external_id` contra un frozenset de ado_ids. Las filas **9 y 10** son las que cubren `ado_state`, que la v1 aceptaba y tiraba a la basura (C13).

- `test_plan284_es_sintetico_cubre_los_103` — **[NUEVO en v2]**. Tabla de `_es_sintetico`: `(-2, -7)`→True, `(-4, -123)`→True, `(1001, 1001)`→False, `(None, None)`→False, `(None, -5)`→True, `("x", None)`→False (no lanza). **Presencia + ausencia en el mismo test.**
- `test_plan284_mine_project_tickets_forma_garantizada` — con la flag OFF, el dict tiene **las 8 claves** (`enabled, scope, total, signal, noise, by_tracker, verdicts, truncated`) con `enabled=False` (presencia de la forma + ausencia de datos en el mismo test).
- `test_plan284_scope_project_es_case_insensitive` — **[NUEVO en v2 — FIX C24]**. Con una DB en memoria que tiene 2 tickets en `"p"` y 2 en `"P"`, `mine_project_tickets("P", scope="project")` devuelve `total == 4` (no 2). **Ausencia gemela:** un ticket en `"OTRO"` no aparece.
- `test_plan284_build_tickets_block_solo_signal` — con un mining de 2 signal + 3 noise, el `content` del bloque **contiene** los títulos de los 2 signal y **no contiene** los de los 3 noise.

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests/test_documenter_v2_pipeline.py -q
```

**Criterio de aceptación binario:** `0 failed`, y el censo de abajo cumple las 4 condiciones.

> **FIX C2 — el censo de la v1 no ejercitaba la función de producción.** La v1 corría SQL crudo `select … from tickets` **sin filtro de proyecto** y esperaba 228. Pero la función que va a producción es `mine_project_tickets`, que **sí** filtra por proyecto. O sea: el gate validaba `classify_ticket` sobre 228 filas mientras el código real veía como mucho 65. Un gate que aprueba algo distinto de lo que se va a ejecutar no es un gate. Este censo llama a **`mine_project_tickets`**, en sus dos scopes.

```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -c @"
from services.doc_ticket_mining import mine_project_tickets as m
a = m('RIPLEY', scope='all')        # corpus completo
p = m('RIPLEY', scope='project')    # proyecto activo (data/active_project.json)
print('all   ', a['total'], a['signal'], a['noise'], a['by_tracker'])
print('RIPLEY', p['total'], p['signal'], p['noise'])
print('C1 corpus completo == 228     ->', a['total'] == 228)
print('C2 particion all              ->', a['signal'] + a['noise'] == a['total'])
print('C3 RIPLEY == 65               ->', p['total'] == 65)
print('C4 particion proyecto         ->', p['signal'] + p['noise'] == p['total'])
"@
```

Las 4 condiciones deben imprimir `True`.
- **C1/C3** son los números **medidos** el 2026-08-01 sobre la base viva. Si `C3` da 65 y no 44 o 49, el match case-insensitive de C24 está bien puesto.
- **C2/C4** prueban que el triage es una **partición**: ningún ticket se pierde ni se cuenta dos veces.
- **Este comando NO es un test**: corre contra la base viva y `mine_project_tickets` es sólo `SELECT`. Si preferís blindarlo, exportá `DATABASE_URL` apuntando a una copia. **Nunca corras `pytest` suelto contra la base viva** (escribe).

> **Nunca corras pytest suelto contra la base viva:** un pytest sin `DATABASE_URL` en memoria escribe en la BD real. Los tests de esta fase usan `sqlite:///:memory:` (ya seteado en `test_documenter_v2_pipeline.py:9`). El comando de censo de arriba abre la base con `mode=ro` y **no** es un test.

**Flag:** `STACKY_DOCS_TICKET_MINING_ENABLED` (default **ON**), `STACKY_DOCS_TICKET_MINING_MAX` (500).
**Runtimes:** barrido SQL local, sin runtime. Idéntico en los 3.
**Trabajo del operador:** ninguno. Los umbrales quedan editables por UI como flags si algún día molestan.

---

### F5 — Pipeline interno de 5 etapas con veredicto (cierra el punto 4 del pedido)

**Objetivo:** que el Documentador deje de ser un one-shot y corra **PROPONER → CRITICAR → MEJORAR → IMPLEMENTAR → VERIFICAR**, con estado persistido por etapa y confirmación humana antes de escribir.
**Valor:** el rigor deja de depender de que el modelo tenga un buen día.

#### F5.0 — [BLOQUEANTE C1] Habilitar lo que F5 da por sentado

> **La v1 era inimplementable acá y hay que arreglarlo ANTES de escribir una línea de F5.**
>
> La v1 decía: *"Invoca vía `invoke_documenter` **con un `system_prompt_override` propio por etapa**"* y *"`_run_paper_stage` **no** usa `parse_proposals`; lee el output crudo con `_wait_and_read_output`"*. Verificado abriendo el archivo, **las dos cosas son imposibles hoy**:
>
> 1. **`invoke_documenter` no acepta `system_prompt_override`.** Firma real (`doc_documenter.py:364-367`):
>    ```python
>    def invoke_documenter(mode: DocumenterMode, context_blocks: list[dict],
>                          project_name: str, runtime: str, *,
>                          on_execution_started: Callable[[int], None] | None = None
>                          ) -> list[DocProposal]:
>    ```
>    El override existe pero está **hardcodeado adentro**: `:381` `system_override = _DEFAULT_DOCUMENTADOR_PROMPT`, y recién ahí se pasa a `run_agent` (`:392`). No hay forma de inyectarlo desde afuera.
> 2. **`invoke_documenter` devuelve `list[DocProposal]`**: parsea el output **adentro**. Las etapas de papel necesitan **texto plano**, y ese texto se pierde antes de volver.
>
> Sin F5.0, F5 entera es papel mojado: compila el plan, no compila el código.

**Archivo a editar:** `Stacky Agents/backend/services/doc_documenter.py`

**(a) Abrir el override.** Cambiar la firma de `invoke_documenter` (`:364`) agregando **un solo kwarg opcional al final**, y cambiar `:381`:

```python
def invoke_documenter(mode: DocumenterMode, context_blocks: list[dict],
                      project_name: str, runtime: str, *,
                      on_execution_started: Callable[[int], None] | None = None,
                      system_prompt_override: str | None = None,   # Plan 284 F5.0
                      ) -> list[DocProposal]:
    ...
    # :381 pasa de:  system_override = _DEFAULT_DOCUMENTADOR_PROMPT
    system_override = system_prompt_override or _DEFAULT_DOCUMENTADOR_PROMPT
```

> Default `None` ⇒ **todos** los llamadores existentes conservan el comportamiento byte-idéntico. Es aditivo puro.

**(b) Una vía para el texto crudo.** Agregar al lado de `invoke_documenter`:

```python
def invoke_raw_stage(stage_prompt: str, context_blocks: list[dict],
                     project_name: str, runtime: str, *,
                     on_execution_started: Callable[[int], None] | None = None
                     ) -> str:
    """Plan 284 F5.0 — invoca al agente y devuelve el TEXTO CRUDO, sin parsear.

    Es el gemelo de invoke_documenter para las etapas de papel (PROPONER,
    CRITICAR, MEJORAR), que producen prosa y no bloques <<<DOC>>>.
    Reusa exactamente el mismo camino de invocación (agent_runner.run_agent),
    así que es agnóstico de runtime igual que invoke_documenter.
    Nunca lanza: ante error devuelve "".
    """
    try:
        _sel = resolve_run_selection(runtime=runtime, project_name=project_name)
        execution_id = agent_runner.run_agent(
            agent_type="Documentador", ticket_id=_CONVERSATION_ADO_ID,
            context_blocks=context_blocks, user="documenter", runtime=runtime,
            vscode_agent_filename="Documentador.agent.md",
            system_prompt_override=stage_prompt, project_name=project_name,
            use_few_shot=False, use_anti_patterns=False, work_item_type="Doc",
            model_override=_sel["model"], effort_override=_sel["effort"])
        if on_execution_started is not None:
            on_execution_started(execution_id)
        return _wait_and_read_output(execution_id) or ""
    except Exception as exc:
        logger.warning("invoke_raw_stage: fallo en etapa de papel: %s", exc)
        return ""
```

> **Copiá el cuerpo de `invoke_documenter` (`:380-399`) como molde**: mismos kwargs de `run_agent`, misma `resolve_run_selection`. Lo único que cambia es que **no** llama a `parse_proposals` y devuelve el texto.

**Tests (PRIMERO).** Agregar a `Stacky Agents/backend/tests/test_documenter_v2_pipeline.py`:

- `test_plan284_invoke_documenter_acepta_override` — monkeypatchear `agent_runner.run_agent` para capturar sus kwargs. Llamar `invoke_documenter(..., system_prompt_override="PROMPT_X")` y asertar `capturado["system_prompt_override"] == "PROMPT_X"` (**presencia**). **Ausencia gemela:** llamarla **sin** el kwarg y asertar que el valor capturado es `_DEFAULT_DOCUMENTADOR_PROMPT` — o sea, backward-compat exacta.
- `test_plan284_invoke_raw_stage_devuelve_texto` — con `run_agent` y `_wait_and_read_output` monkeypatcheados, `invoke_raw_stage("P", [], "P", "claude_code_cli")` devuelve el texto crudo **y** `parse_proposals` **no** fue llamada (monkeypatcheala para que lance `AssertionError`; si el texto vuelve, es que no pasó por el parser).

**Criterio de aceptación binario:** `0 failed`, y este censo AST devuelve **exactamente 1** (el override es un parámetro real, no un literal hardcodeado):

```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -c "import ast,pathlib; t=ast.parse(pathlib.Path('services/doc_documenter.py').read_text(encoding='utf-8')); f=[n for n in ast.walk(t) if isinstance(n,ast.FunctionDef) and n.name=='invoke_documenter'][0]; print(sum(1 for a in f.args.kwonlyargs if a.arg=='system_prompt_override'))"
```

**Flag:** ninguna (es habilitación de sustrato; sin llamadores nuevos no cambia nada).
**Runtimes:** `invoke_raw_stage` usa el mismo `agent_runner.run_agent` que `invoke_documenter`, **sin branching por runtime**. Idéntico en los 3.
**Trabajo del operador:** ninguno.

#### F5.1 — Contrato de etapas

**Archivo a editar:** `Stacky Agents/backend/services/doc_documenter.py`

```python
class DocumenterStage(str, Enum):
    PROPONER = "PROPONER"       # el agente propone un plan de documentación
    CRITICAR = "CRITICAR"       # el agente critica su propio plan
    MEJORAR = "MEJORAR"         # el agente reescribe el plan corregido
    IMPLEMENTAR = "IMPLEMENTAR" # se ejecutan los modos del 113 (escribe)
    VERIFICAR = "VERIFICAR"     # verificación DETERMINISTA, sin LLM


# Orden canónico. La UI y el reporte lo respetan.
STAGE_ORDER: tuple[DocumenterStage, ...] = (
    DocumenterStage.PROPONER, DocumenterStage.CRITICAR, DocumenterStage.MEJORAR,
    DocumenterStage.IMPLEMENTAR, DocumenterStage.VERIFICAR,
)


@dataclass
class StageResult:
    stage: str
    state: str                 # "pending" | "running" | "done" | "skipped" | "failed" | "awaiting_approval"
    summary: str = ""
    artifact: str = ""         # texto producido por la etapa (plan, crítica, plan mejorado)
    verdict: str = ""          # sólo VERIFICAR: "RADIOGRAFIA_COMPLETA" | "RADIOGRAFIA_PARCIAL" | "INSUFICIENTE"
    started_at: str = ""
    ended_at: str = ""
    execution_id: int | None = None

    def to_dict(self) -> dict: ...
```

#### F5.2 — Las 3 etapas de papel

Los 3 prompts de etapa, **escritos** (la v1 los nombraba y nunca los definía — C11). Cada uno es una constante de módulo en `doc_documenter.py`:

```python
_STAGE_PROMPT_PROPONER = (
    "Sos el Documentador de Stacky en la etapa PROPONER.\n"
    "NO escribas documentación todavía. NO uses bloques <<<DOC>>>.\n"
    "Devolvé TEXTO PLANO con un plan de documentación para este proyecto:\n"
    "1. Qué módulos hay que documentar y por qué, EN ORDEN DE PRIORIDAD.\n"
    "2. Para cada uno, qué archivo de doc le corresponde y qué debe contener.\n"
    "3. Qué NO se puede afirmar todavía por falta de evidencia en el contexto.\n"
    "Citá rutas reales del contexto provisto. Si no tenés evidencia, decilo."
)
_STAGE_PROMPT_CRITICAR = (
    "Sos el Documentador de Stacky en la etapa CRITICAR.\n"
    "Arriba tenés TU PROPIO plan de la etapa anterior. Atacalo sin piedad.\n"
    "NO escribas documentación. NO uses bloques <<<DOC>>>. TEXTO PLANO.\n"
    "Listá C1..Cn: qué afirma el plan sin evidencia, qué módulo importante "
    "omite, qué ruta citada no aparece en el contexto, y qué parte no se "
    "puede verificar contra el código provisto."
)
_STAGE_PROMPT_MEJORAR = (
    "Sos el Documentador de Stacky en la etapa MEJORAR.\n"
    "Arriba tenés tu plan y su crítica. Reescribí el plan corrigiendo cada "
    "punto de la crítica. NO escribas documentación todavía. TEXTO PLANO.\n"
    "Si un punto de la crítica no se puede resolver con la evidencia "
    "disponible, sacá ese ítem del plan en vez de inventarlo."
)
```

`_run_paper_stage(stage, project_name, runtime, operator_note, prior_artifact) -> StageResult`:
- Arma un `context_blocks` con: el bloque de la nota del operador (F2), el bloque de salud/grafo, el bloque de tickets `signal` (F4) y, si `prior_artifact` no está vacío, un bloque `{"id": "prior-stage", "kind": "prior-stage", "title": "<etapa anterior>", "content": prior_artifact}`.
- Invoca vía **`invoke_raw_stage(_STAGE_PROMPT_<ETAPA>, blocks, project_name, runtime)`** (la primitiva que crea **F5.0**). **No** usa `invoke_documenter` ni `parse_proposals`: estas etapas producen prosa, no bloques `<<<DOC>>>`.
- Devuelve `StageResult` con `artifact` = el texto devuelto, `state="done"` si hubo texto, `state="failed"` si volvió `""`.

**Corte de costo (obligatorio) — reforzado en v2 (FIX C17).** La v1 cortaba sólo por longitud (`<200 chars`), así que 250 caracteres de basura pasaban el gate y disparaban 2 invocaciones más. El corte ahora es una función pura, testeable:

```python
def stage_artifact_is_usable(artifact: str, context_blocks: list[dict],
                             *, min_chars: int = 200) -> bool:
    """Plan 284 — ¿el artefacto de PROPONER amerita gastar CRITICAR + MEJORAR?

    PURA, sin I/O. Nunca lanza. Dos condiciones, ambas necesarias:
      1. Longitud >= min_chars.
      2. Menciona al menos UNA ruta que aparezca en el contexto que le dimos.
         Un plan que no nombra ni un archivo del repo no es un plan: es prosa.
    """
    try:
        txt = (artifact or "").strip()
        if len(txt) < min_chars:
            return False
        ctx = "\n".join(str(b.get("content", "")) for b in (context_blocks or []))
        candidatos = {w.strip(".,;:()[]\"'") for w in ctx.split()
                      if "/" in w and "." in w and len(w) > 6}
        return any(c in txt for c in candidatos)
    except Exception:
        return False
```

Si `stage_artifact_is_usable(...)` es `False`, `CRITICAR` y `MEJORAR` quedan `state="skipped"` con `summary="sin plan que criticar"`. No se gastan 2 invocaciones al pedo.

> **Nota de diseño honesta:** estas 3 etapas cuestan 3 invocaciones extra de LLM por run. Es el precio del rigor que pidió el operador. Está acotado: se pagan **una vez por run**, no por modo, y el corte de arriba las evita cuando no hay nada que criticar. Ver Riesgo R1.

#### F5.3 — IMPLEMENTAR con human-in-the-loop

- Si `STACKY_DOCS_PIPELINE_AUTOAPPLY` está **OFF** (default), al llegar a `IMPLEMENTAR` el run se marca `state="awaiting_approval"`, persiste el reporte con las 3 etapas de papel completas y **se detiene**. El operador lee el plan y la crítica en la UI y aprueba.
- **Endpoint nuevo** en `Stacky Agents/backend/api/docs.py` (blueprint `bp`, `api/docs.py:28`, `url_prefix="/docs"` bajo `/api`; los POST usan el atajo `@bp.post`).

> **⚠️ FIX C5 — esto era un bloqueante silencioso de la v1.** Con los defaults del propio plan (`STAGES=ON`, `AUTOAPPLY=OFF`), **todo** run se detiene en `awaiting_approval`. O sea: **el camino por defecto del producto** depende enteramente de este endpoint. La v1 lo dejaba con (a) **cero tests**, (b) **sin función cliente en `endpoints.ts`** — el botón de F7 no tenía a qué llamar — y (c) apoyado en `test_docs_api.py`, que **no está registrado en ninguno de los dos ratchets** (verificado: `grep test_docs_api` → 0 hits en `run_harness_tests.ps1` y en `.sh`). Endpoint construido, jamás cableado, y encima invisible para el arnés.

```python
@bp.post("/documenter/stage/approve")
def documenter_stage_approve():
    """Plan 284 — el operador aprueba (o cancela) pasar a IMPLEMENTAR.

    Body: {"run": "<run_id>", "approve": true|false, "keep_branch": true|false}
    404 si STACKY_DOCS_DOCUMENTER_ENABLED o STACKY_DOCS_PIPELINE_STAGES_ENABLED
        están OFF  (capacidad desactivada, NO "permiso denegado": mono-operador).
    404 run_not_found si el run_id no existe (reinicio del backend).
    409 si el run no está en state == "awaiting_approval".
    200 {"ok": true, "state": "running"|"cancelled_by_operator"}
    """
```

  - `approve=true` ⇒ el run reanuda en IMPLEMENTAR (los modos del 113) y sigue a VERIFICAR.
  - `approve=false` ⇒ `state="cancelled_by_operator"` y la rama se descarta con `discard_doc_branch` (`doc_documenter.py:514`).
  - **`keep_branch` (FIX C8).** La v1 afirmaba que esta aprobación *"reemplaza al Conservar/Descartar"*, pero **no eliminaba** `POST /documenter/decide` (`api/docs.py:364`), así que el operador quedaba con **dos** decisiones por run — es decir, la v1 agregaba trabajo mientras decía que no lo agregaba. Se resuelve fusionando: `keep_branch` viaja en **la misma** llamada y el backend encadena la decisión de rama al terminar. `POST /documenter/decide` **se conserva** por backward-compat (runs viejos, y el caso en que el operador cambie de opinión después), pero en el flujo con etapas ON ya no hace falta tocarlo. **Una decisión por run, no dos.**

**Función cliente (faltaba por completo en la v1).** En `Stacky Agents/frontend/src/api/endpoints.ts`, junto a `documenterRun` (`:3648`):

```ts
  /** Plan 284 — aprueba (o cancela) el paso a IMPLEMENTAR de un run detenido
   *  en awaiting_approval. 404 si la flag OFF, 409 si el run no está esperando. */
  documenterStageApprove: (
    run: string, approve: boolean, keepBranch = true
  ): Promise<{ ok: boolean; state?: string; error?: string }> =>
    api.post<{ ok: boolean; state?: string; error?: string }>(
      `/api/docs/documenter/stage/approve`,
      { run, approve, keep_branch: keepBranch }
    ),
```

**Registrar el archivo de test en el arnés (obligatorio).** `test_docs_api.py` existe pero **no** está en los ratchets. Agregarlo a **LOS DOS**, respetando la sintaxis de cada uno (divergen):
- `backend/scripts/run_harness_tests.ps1` → `  "tests/test_docs_api.py",` junto a `"tests/test_doc_evidence.py"` (`:364`).
- `backend/scripts/run_harness_tests.sh` → `  tests/test_docs_api.py` junto a `tests/test_doc_evidence.py` (`:415`).
> El ratchet es una **trampa de commit, no sólo de edición**: si no lo registrás en ambos, el commit pasa y el arnés nunca corre estos tests.

**Tests del endpoint (PRIMERO).** En `Stacky Agents/backend/tests/test_docs_api.py`:
- `test_plan284_approve_404_con_stages_off` — flag OFF ⇒ 404, y el body dice capacidad desactivada (**no** "permiso denegado").
- `test_plan284_approve_409_si_no_espera` — run en `state="running"` ⇒ 409 y el run **no** cambia de estado (ausencia) **y** sigue existiendo (presencia).
- `test_plan284_approve_true_reanuda` — run en `awaiting_approval` ⇒ 200 y `state != "awaiting_approval"`.
- `test_plan284_approve_false_cancela_y_descarta` — 200, `state == "cancelled_by_operator"` **y** `discard_doc_branch` fue llamada exactamente 1 vez (monkeypatch con contador).
- Si `STACKY_DOCS_PIPELINE_AUTOAPPLY` está **ON**, sigue de largo. **Es la única forma de que Stacky escriba documentación sin que el operador diga que sí.**

#### F5.4 — VERIFICAR (determinista, sin LLM)

`_run_verify_stage(result: ApplyResult, workspace_root, project_name) -> StageResult` calcula:
- `citations_total`, `citations_ok`, `files_rejected` (de `result.files`, F3).
- `coverage` (de F6, si `STACKY_DOCS_RADIOGRAPHY_ENABLED` ON).
- El veredicto sale de una **función pura** (la v1 la usaba en un test y nunca la definía — C11):

```python
VERDICT_COMPLETA = "RADIOGRAFIA_COMPLETA"
VERDICT_PARCIAL = "RADIOGRAFIA_PARCIAL"
VERDICT_INSUFICIENTE = "INSUFICIENTE"
VERDICT_PENDIENTE = "PENDIENTE_DE_APROBACION"   # FIX C7


def compute_verify_verdict(written_count: int, files_rejected: int,
                           coverage_ratio: float) -> str:
    """Plan 284 — veredicto del run. PURA, sin I/O. Nunca lanza.

    Reglas EXACTAS, en este orden (la primera que matchea gana):
      1. written == 0                      -> INSUFICIENTE
      2. files_rejected > written          -> INSUFICIENTE
      3. files_rejected == 0 y ratio>=0.8  -> RADIOGRAFIA_COMPLETA
      4. cualquier otro caso               -> RADIOGRAFIA_PARCIAL
    """
    try:
        w = int(written_count or 0)
        r = int(files_rejected or 0)
        c = float(coverage_ratio or 0.0)
        if w == 0 or r > w:
            return VERDICT_INSUFICIENTE
        if r == 0 and c >= 0.8:
            return VERDICT_COMPLETA
        return VERDICT_PARCIAL
    except Exception:
        return VERDICT_INSUFICIENTE
```

- El veredicto va al reporte final como `report["verdict"]` y las etapas como `report["stages"]`.

> **FIX C7 — el KPI-7 de la v1 se contradecía con sus propios defaults.** KPI-7 promete *"0% de runs que terminan sin veredicto explícito"*. Pero con `STAGES=ON` + `AUTOAPPLY=OFF` (los defaults **del plan**), **todo** run se detiene en `awaiting_approval` y `VERIFICAR` **nunca corre** ⇒ el 100% de los runs terminaría sin veredicto. La fase prometía exactamente lo contrario de lo que sus defaults producen.
>
> **Resolución:** la parada por aprobación **también emite veredicto**. Al entrar en `awaiting_approval`, el run persiste `report["verdict"] = VERDICT_PENDIENTE` con el resumen de las 3 etapas de papel. No es un veredicto de calidad documental — es un estado terminal honesto y explícito, que es lo que KPI-7 mide. Cuando el operador aprueba, `VERIFICAR` corre y lo reemplaza por el veredicto real.

**Tests (PRIMERO).** Agregar a `Stacky Agents/backend/tests/test_documenter_v2_pipeline.py`:

- `test_plan284_stage_order_es_el_contrato` — `STAGE_ORDER` tiene exactamente 5 elementos en el orden PROPONER, CRITICAR, MEJORAR, IMPLEMENTAR, VERIFICAR.
- `test_plan284_verdict_tabla` — función pura `compute_verify_verdict(written_count, files_rejected, coverage_ratio)` con la tabla de las 3 reglas, incluyendo las fronteras `coverage_ratio=0.8` (COMPLETA) y `0.79` (PARCIAL).
- **`test_plan284_sin_autoaplicado_el_run_espera_aprobacion`** — con `STACKY_DOCS_PIPELINE_AUTOAPPLY=False`, `STACKY_DOCS_PIPELINE_STAGES_ENABLED=True` y `invoke_documenter` monkeypatcheado para devolver un artefacto de papel válido: el run termina en `state == "awaiting_approval"` (presencia) **y** `result.written == []` — no se escribió ni un archivo (ausencia). Es el test del riel human-in-the-loop.
- `test_plan284_corte_de_costo_sin_plan` — si PROPONER devuelve `""`, las etapas CRITICAR y MEJORAR quedan `state="skipped"` y **`invoke_raw_stage` fue llamada exactamente 1 vez** (contador en el monkeypatch). Prueba que el corte ahorra de verdad. **Precondición obligatoria del test:** fijar `STACKY_DOCS_PIPELINE_AUTOAPPLY=False`; si quedara en `True` el run seguiría a IMPLEMENTAR y el contador subiría por los modos del 113, y el "exactamente 1" sería un falso rojo.
- `test_plan284_stage_artifact_is_usable_tabla` — **[NUEVO en v2 — FIX C17]**: `("", ctx)`→False; 199 chars→False; 250 chars sin ninguna ruta del contexto→**False** (el caso que la v1 dejaba pasar); 250 chars que mencionan `services/doc_graph.py` presente en el contexto→True; `(None, None)`→False (no lanza).
- `test_plan284_pipeline_off_es_backward_compatible` — con `STACKY_DOCS_PIPELINE_STAGES_ENABLED=False`, `run_documenter` devuelve un reporte **sin** las claves `stages` ni `verdict`, y con las mismas claves que hoy.

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests/test_documenter_v2_pipeline.py -q
```

**Criterio de aceptación binario:** `0 failed`, **y** el censo de orden de abajo imprime `True`.

> **FIX C14 — el censo de la v1 no probaba lo que decía.** Era `Select-String … "STACKY_DOCS_PIPELINE_AUTOAPPLY" | Count == 1`, con la glosa *"existe un único punto donde el autoaplicado se consulta, **y está antes de escribir**"*. Tres defectos: (1) cuenta **por subcadena**, así que un comentario que nombre la flag lo pone en 2 y lo rompe — un gate que **premia no documentar**; (2) no verifica **nada** sobre el orden, que es justo lo que la glosa promete; (3) el riel human-in-the-loop es de **comportamiento**, y eso se prueba con un test, no con un grep.

```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -c @"
import ast, pathlib
src = pathlib.Path('services/doc_documenter.py').read_text(encoding='utf-8')
t = ast.parse(src)
# 1) la consulta del autoaplicado existe como LECTURA de config, no como literal
lecturas = [n.lineno for n in ast.walk(t)
            if isinstance(n, ast.Constant) and n.value == 'STACKY_DOCS_PIPELINE_AUTOAPPLY']
# 2) toda escritura de doc vive en apply_proposals; el gate tiene que ser previo
fn = [n for n in ast.walk(t) if isinstance(n, ast.FunctionDef)
      and n.name == 'apply_proposals'][0]
escrituras = [n.lineno for n in ast.walk(fn)
              if isinstance(n, ast.Call) and getattr(n.func, 'attr', '') == 'write_text']
print('lecturas de la flag:', lecturas)
print('escrituras en apply_proposals:', escrituras)
print('G1 la flag se lee               ->', len(lecturas) >= 1)
print('G2 toda lectura precede a la escritura ->',
      all(l < w for l in lecturas for w in escrituras) if escrituras else True)
"@
```

`G1` y `G2` deben imprimir `True`. **Pero el gate REAL de este riel es el test** `test_plan284_sin_autoaplicado_el_run_espera_aprobacion`: si ese test pasa, el operador no puede ser salteado, censo o no censo.

**Flag:** `STACKY_DOCS_PIPELINE_STAGES_ENABLED` (**ON**) + `STACKY_DOCS_PIPELINE_AUTOAPPLY` (**OFF**, excepción B).
**Runtimes:** las 3 etapas de papel usan `invoke_documenter`, agnóstico de runtime. **Fallback por runtime:** si el runtime devuelve vacío en PROPONER (típico de un modelo con poco presupuesto), el corte de costo salta a IMPLEMENTAR con los modos del 113 — el comportamiento degrada exactamente al de hoy, nunca a un error.
**Trabajo del operador:** una aprobación por run. **Es human-in-the-loop, no fricción**: es la decisión que hoy ya toma con Conservar/Descartar, movida antes de escribir en vez de después.

---

### F6 — Radiografía: cobertura sobre el grafo existente (cierra el punto 5 del pedido)

**Objetivo:** medir qué parte del proyecto está documentada y qué no, **enriqueciendo** el grafo del 268 en vez de construir uno paralelo.
**Valor:** el operador ve el hueco, no una lista de archivos escritos.

**Archivo a CREAR:** `Stacky Agents/backend/services/doc_radiography.py`

```python
"""Plan 284 — Radiografía documental: cobertura módulo↔nota sobre el grafo del 109/268."""

def compute_coverage(graph: dict, workspace_root: str | None) -> dict:
    """Cobertura documental. PURA respecto del grafo: NO reconstruye nada.

    Forma GARANTIZADA (las 7 claves siempre presentes):
      {"enabled": bool, "modules_total": int, "modules_covered": int,
       "coverage_ratio": float, "uncovered": [str], "orphan_notes": [str],
       "by_doc_class": {clase: int}}

    Nunca lanza: ante error devuelve la forma con enabled=True y ceros.
    """
    from config import config as _cfg
    vacio = {"enabled": False, "modules_total": 0, "modules_covered": 0,
             "coverage_ratio": 0.0, "uncovered": [], "orphan_notes": [],
             "by_doc_class": {}}
    if not bool(getattr(_cfg, "STACKY_DOCS_RADIOGRAPHY_ENABLED", False)):
        return vacio
    try:
        g = graph or {}
        salud = g.get("doc_health") or {}
        uncovered = list(salud.get("uncovered_modules") or [])
        nodos = g.get("nodes") or []

        # ── OJO: el total NO sale de doc_health ──────────────────────────
        # La v1 decía "modules_total / modules_covered / uncovered salen de
        # doc_health.uncovered_modules". Imposible: uncovered_modules es SOLO
        # la lista de los NO cubiertos — no trae el total, y además viene
        # vacía en 3 de las 4 ramas de classify_doc_health (SIN_DOCS,
        # FORMATO_NO_OBSIDIAN, SANA) y en el except. De ahí no se puede
        # derivar un ratio. El total sale de los nodos de código del grafo.
        modulos = {str(n.get("path") or "") for n in nodos
                   if str(n.get("kind") or "") in ("code", "module", "missing")}
        modulos.discard("")
        total = len(modulos) or len(uncovered)
        cubiertos = max(total - len(uncovered), 0)
        ratio = 1.0 if total == 0 else cubiertos / total

        notas = [str(n.get("path") or "") for n in nodos
                 if str(n.get("kind") or "") == "note"]
        from services import doc_taxonomy
        return {"enabled": True, "modules_total": total,
                "modules_covered": cubiertos, "coverage_ratio": ratio,
                "uncovered": uncovered,
                "orphan_notes": list(g.get("orphans") or []),
                "by_doc_class": doc_taxonomy.summarize_classes(notas)}
    except Exception:
        return dict(vacio, enabled=True)
```

> **Nota de honestidad (hallazgo del juez, no del autor).** Si `classify_doc_health` devuelve `SANA` o `SIN_DOCS`, `uncovered_modules` viene `[]` y la cobertura da `1.0` aunque no haya una sola nota. Es un artefacto de reusar la salud existente en vez de recalcular — y reusar es lo correcto. El caso queda **explícito** en el test `test_plan284_coverage_ratio_fronteras` y el veredicto lo compensa: con `written == 0` el run es `INSUFICIENTE` sin importar el ratio.

**Cableado:** en `run_documenter`, después de calcular `health_after` (`doc_documenter.py:934`), agregar `report["radiography"] = doc_radiography.compute_coverage(...)` cuando `STACKY_DOCS_RADIOGRAPHY_ENABLED` esté ON (si no, la clave no aparece).

**API:** `documenter_status` (`api/docs.py:292`) agrega al `jsonify` (`api/docs.py:302-320`) las claves `"stages": rec.get("stages", [])`, `"verdict": rec.get("verdict", "")`, `"radiography": rec.get("radiography", {})`, `"ticket_mining": rec.get("ticket_mining", {})`, `"operator_note": rec.get("operator_note", "")`. Todas aditivas.

> **Explícitamente NO se hace:** no se crea un grafo nuevo, no se persiste un `.jsonl`, no se toca `docGraphModel.ts` ni `forceLayout.ts` del 268. La radiografía es una **lectura derivada** del grafo que ya existe.

**Tests (PRIMERO).** En `Stacky Agents/backend/tests/test_doc_evidence.py`:
- `test_plan284_compute_coverage_forma_garantizada` — con un grafo mínimo, el dict trae **las 7 claves** aunque estén en cero.
- `test_plan284_coverage_ratio_fronteras` — `modules_total=0` → `1.0`; `4 de 5` → `0.8`; `0 de 5` → `0.0`.
- `test_plan284_coverage_no_recalcula_health` — monkeypatchear `doc_graph.classify_doc_health` para que lance `AssertionError` y verificar que `compute_coverage` **no la llama** (lee `graph["doc_health"]`), y que aun así devuelve la forma completa.

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests/test_doc_evidence.py -q
```

**Criterio de aceptación binario:** `0 failed` **y** el censo de abajo imprime `True` en sus dos condiciones.

> **FIX C15 — la v1 tenía una ausencia sin presencia gemela.** El censo era `Select-String … "build_graph|rglob|_enumerate_note_files" | Count == 0`. Dos defectos: (1) es un **assert de ausencia** que pasa por accidente si el archivo está vacío o si alguien evade la subcadena (`getattr(doc_graph, "build_" + "graph")`); (2) no prueba lo único que importa — que `compute_coverage` **efectivamente lea el grafo que ya existe**. Ausencia **y** presencia, en el mismo censo:

```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -c @"
import pathlib
src = pathlib.Path('services/doc_radiography.py').read_text(encoding='utf-8')
ausencia = not any(p in src for p in ('build_graph', 'rglob', '_enumerate_note_files'))
presencia = ('doc_health' in src and 'uncovered_modules' in src and 'orphans' in src)
print('A1 no hay motor paralelo   ->', ausencia)
print('P1 lee el grafo existente  ->', presencia)
"@
```

#### F6.1 — [ADICIÓN ARQUITECTO A2] Delta de radiografía entre runs

**Por qué.** El plan v1 medía la cobertura **de este run** y la mostraba como un número absoluto. Un número absoluto no le dice al operador si mejoró: "cobertura 68%" no se interpreta sin memoria. Lo que convierte al Documentador de *one-shot* en **instrumento** es la derivada, y este plan ya tiene todo para calcularla — sólo faltaba conectarlo.

**Reuso puro, cero LLM, cero trabajo del operador.** El historial de corridas ya existe: `list_runs` (`doc_documenter.py:778`) y `_persist_run_report` (`:758`). Sólo hay que leer el run anterior y restar.

**Archivo:** `Stacky Agents/backend/services/doc_radiography.py`

```python
def compute_coverage_delta(actual: dict, previo: dict | None) -> dict:
    """Plan 284 A2 — variación de cobertura respecto del run anterior.

    Forma GARANTIZADA: {"has_previous": bool, "ratio_delta": float,
                        "modules_closed": [str], "modules_opened": [str]}
    - modules_closed: módulos que estaban sin cubrir y ahora sí lo están.
    - modules_opened: módulos que aparecieron sin cubrir (regresión o código nuevo).
    Nunca lanza.
    """
    vacio = {"has_previous": False, "ratio_delta": 0.0,
             "modules_closed": [], "modules_opened": []}
    try:
        if not previo or not previo.get("enabled"):
            return vacio
        ant = set(previo.get("uncovered") or [])
        act = set((actual or {}).get("uncovered") or [])
        return {
            "has_previous": True,
            "ratio_delta": float((actual or {}).get("coverage_ratio", 0.0))
                           - float(previo.get("coverage_ratio", 0.0)),
            "modules_closed": sorted(ant - act),
            "modules_opened": sorted(act - ant),
        }
    except Exception:
        return vacio
```

**Cableado:** en `run_documenter`, junto a `report["radiography"]`, agregar `report["radiography_delta"]` leyendo la `radiography` del run inmediatamente anterior vía `list_runs(limit=2)`. Si no hay run previo, `has_previous=False` y la UI no muestra nada (degradación silenciosa, nunca un error).

**UI (F7):** `buildRadiographyView` suma `deltaLabel`: `"+12 pts desde el run anterior — cerraste 3 módulos"`, o `""` cuando `has_previous === false`.

**Tests:** `test_plan284_coverage_delta_tabla` en `test_doc_evidence.py` — sin previo → `has_previous=False` (**y** las 4 claves presentes); previo con 5 uncovered y actual con 2 → `modules_closed` tiene los 3 (**presencia**) y `modules_opened` vacío (**ausencia gemela**); regresión inversa → al revés.

**Flag:** hereda `STACKY_DOCS_RADIOGRAPHY_ENABLED` (**ON**). Es lectura y resta: no es excepción (A) ni (B).
**Runtimes:** aritmética local. Idéntico en los 3.
**Trabajo del operador:** ninguno. Aparece solo.

**Flag:** `STACKY_DOCS_RADIOGRAPHY_ENABLED` (default **ON**).
**Runtimes:** cálculo local. Idéntico en los 3.
**Trabajo del operador:** ninguno.

---

### F6.2 — [ADICIÓN ARQUITECTO A1] Presupuesto de invocaciones LLM, medido y con tope duro

**Por qué.** El riesgo R1 de la v1 reconoce que el run pasa de N a **N+3** invocaciones y lo mitiga con "se puede apagar la flag". Eso no es una mitigación: es un interruptor. Faltaban las dos cosas que hacen falta de verdad — **saber cuánto se gastó** y **que no se pueda ir al carajo**. El precedente del repo es explícito: un tope mal puesto (`RUNAWAY_MAX_TURNS=0` = *sin límite*) es peor que no tener tope.

**Contador (observabilidad).** En `run_documenter`, llevar `llm_calls: int` incrementado en cada `invoke_documenter` / `invoke_raw_stage`, y publicarlo en el reporte:
`report["llm_calls"] = llm_calls` y `report["llm_calls_budget"] = budget`.

**Tope duro (seguridad).** Flag nueva — **son 11 flags, no 10**:

| Flag | Tipo | Default | Justificación |
|---|---|---|---|
| `STACKY_DOCS_PIPELINE_MAX_LLM_CALLS` | int | **12** | Techo de invocaciones por run. Bounds `[1, 200]`. **Numérico, no booleano**; va a `_CURATED_DEFAULTS_ON` como las otras 3. `12` = 5 modos del 113 (techo observado) + 3 etapas de papel + 4 de holgura. |

```python
def budget_exhausted(llm_calls: int, budget: int) -> bool:
    """Plan 284 A1 — ¿se agotó el presupuesto de invocaciones del run?

    OJO: budget <= 0 significa AGOTADO, nunca "sin límite". Un 0 que
    significa infinito es la forma más cara de romper un tope.
    """
    try:
        return int(llm_calls) >= int(budget) if int(budget) > 0 else True
    except Exception:
        return False
```

Al agotarse: el run **no falla**, se detiene ordenadamente con `state="budget_exhausted"`, veredicto `RADIOGRAFIA_PARCIAL` y el detalle en el reporte. Los archivos ya escritos se conservan.

**Tests** (en `test_documenter_v2_pipeline.py`):
- `test_plan284_budget_exhausted_tabla` — `(0, 12)`→False; `(11, 12)`→False; `(12, 12)`→**True** (frontera); `(3, 0)`→**True** (**el caso que importa: cero NO es infinito**); `(3, -1)`→True; `("x", 12)`→False (no lanza).
- `test_plan284_run_respeta_el_presupuesto` — con `STACKY_DOCS_PIPELINE_MAX_LLM_CALLS=2` y un `invoke_*` contado, el run se detiene con `state == "budget_exhausted"` (**presencia**) y `invoke_*` fue llamado **exactamente 2 veces** (**el tope se respeta, no se excede en uno**).

**Flag:** `STACKY_DOCS_PIPELINE_MAX_LLM_CALLS` (**12**). Numérica con tope: no es excepción (A) ni (B) — **acota** el gasto, no lo genera.
**Runtimes:** el contador es agnóstico; cuenta invocaciones, no runtimes. Idéntico en los 3.
**Trabajo del operador:** ninguno. Si algún día le queda corto, es un número editable desde el panel de flags.

---

### F7 — La UI se entiende (cierra el punto 1 del pedido)

**Objetivo:** que el panel del Documentador se lea de un vistazo: veredicto arriba, etapas con su estado, archivos agrupados por clase, rechazos con motivo en castellano.
**Valor:** el operador entiende qué pasó sin leer un `diff --stat`.

#### F7.0 — [FIX C10] Extender el tipo ANTES de escribir la lógica

> **La v1 hacía imposible su propio criterio de aceptación.** F7 exige `npx tsc --noEmit` con exit 0, y a la vez manda escribir `buildStagesView(status: DocumenterStatusResponse)` leyendo `status.stages`, `status.verdict`, `status.radiography`, `status.ticket_mining` y `status.operator_note` — **cinco claves que ese tipo no tiene**. `DocumenterStatusResponse` está en `endpoints.ts:3552-3573` con 16 claves y ninguna de esas cinco. `tsc` falla, y con él el criterio binario de la fase.

**Archivo a editar:** `Stacky Agents/frontend/src/api/endpoints.ts`, interfaz `DocumenterStatusResponse` (`:3552-3573`). Agregar **6** campos, todos **opcionales** (`?`) para no romper a ningún consumidor actual:

```ts
  /** Plan 284 — etapas del pipeline en orden canónico. */
  stages?: Array<{
    stage: string; state: string; summary?: string; artifact?: string;
    verdict?: string; started_at?: string; ended_at?: string;
    execution_id?: number | null;
  }>;
  /** Plan 284 — veredicto del run. "" si el pipeline está OFF. */
  verdict?: string;
  /** Plan 284 — cobertura documental (F6). */
  radiography?: {
    enabled?: boolean; modules_total?: number; modules_covered?: number;
    coverage_ratio?: number; uncovered?: string[]; orphan_notes?: string[];
    by_doc_class?: Record<string, number>;
  };
  /** Plan 284 A2 — variación contra el run anterior. */
  radiography_delta?: {
    has_previous?: boolean; ratio_delta?: number;
    modules_closed?: string[]; modules_opened?: string[];
  };
  /** Plan 284 — resumen del triage de tickets (F4), sin los veredictos individuales. */
  ticket_mining?: {
    enabled?: boolean; scope?: string; total?: number; signal?: number;
    noise?: number; by_tracker?: Record<string, number>; truncated?: boolean;
  };
  /** Plan 284 — la nota que el operador escribió al lanzar el run. */
  operator_note?: string;
```

> Todos con `?`: con las flags en OFF el backend no manda las claves y el tipo sigue siendo válido. **Aditivo puro, backward-compatible.**

**Archivo a editar:** `Stacky Agents/frontend/src/docs/documenterModel.ts` (lógica pura, testeable sin RTL).

Agregar 3 funciones exportadas:

```ts
export interface StageView { stage: string; label: string; state: string; badge: string; summary: string; }
/** Plan 284 — filas de etapa en el orden canónico, incluso las que no llegaron a correr. */
export function buildStagesView(status: DocumenterStatusResponse | null | undefined): StageView[];

export interface VerdictView { verdict: string; label: string; tone: "ok" | "warn" | "bad"; detail: string; }
/** Plan 284 — veredicto legible. Sin veredicto => label "Sin veredicto", tone "warn". */
export function buildVerdictView(status: DocumenterStatusResponse | null | undefined): VerdictView;

export interface RadiographyView { coverageLabel: string; uncovered: string[]; classLabel: string; ticketsLabel: string; }
/** Plan 284 — resumen de radiografía + minería en texto llano. */
export function buildRadiographyView(status: DocumenterStatusResponse | null | undefined): RadiographyView;
```

Reglas de etiqueta (exactas, sin inventar):
- `RADIOGRAFIA_COMPLETA` → `"Radiografía completa"`, tone `"ok"`.
- `RADIOGRAFIA_PARCIAL` → `"Radiografía parcial"`, tone `"warn"`.
- `INSUFICIENTE` → `"Insuficiente: revisá los rechazos"`, tone `"bad"`.
- `""` / null → `"Sin veredicto"`, tone `"warn"`.
- Estados de etapa: `pending`→`"Pendiente"`, `running`→`"En curso"`, `done`→`"Hecha"`, `skipped`→`"Salteada"`, `failed`→`"Falló"`, `awaiting_approval`→`"Esperando tu aprobación"`.
- `coverageLabel`: `"Cobertura 12 de 15 módulos (80%)"`. Con `modules_total===0`: `"Sin módulos que cubrir"`.
- `ticketsLabel`: `"228 tickets barridos — 96 aportaron historia, 132 descartados"`. Con `enabled===false`: `"Minería de tickets desactivada"`.

**Archivo a editar:** `Stacky Agents/frontend/src/components/docs/DocumenterResultPanel.tsx`
- Poner el veredicto **arriba de todo** (antes del encabezado de `DocumenterResultPanel.tsx:52`), con el color según `tone` usando **tokens reales del tema**: `var(--success)`, `var(--danger)`, `var(--accent)`, `var(--text-primary)`, `var(--border)`. **No existen tokens `--color-*`**: si los usás, no pinta nada.
- Debajo, la lista de etapas de `buildStagesView`.
- Agrupar la lista de archivos por `doc_class` con subtítulos "Documentación del proyecto" / "Documentación de sistema" / "Otros" (los `plan` no deberían aparecer nunca; si aparecen, mostrarlos bajo "Planes (inesperado)").
- Los archivos rechazados por el gate van en su propia sección con el título **"Rechazados por citas inválidas"** y el motivo formateado por `formatSkipReason`.
- Si el run está en `awaiting_approval`, mostrar el artefacto de las etapas PROPONER/CRITICAR/MEJORAR en un `<details>` y dos botones: **"Aprobar e implementar"** / **"Cancelar"**, que llaman al endpoint nuevo.

**Tests.** En `Stacky Agents/frontend/src/docs/documenterModel.test.ts`:
- `test_plan284_buildStagesView_orden_y_relleno` — con un status que trae sólo 2 etapas, devuelve **5** filas en el orden canónico y las 3 faltantes con `state === "pending"`.
- `test_plan284_buildVerdictView_tabla` — los 4 casos de la tabla de arriba, verificando `label` **y** `tone`.
- `test_plan284_buildRadiographyView_labels` — cobertura 12/15 → `"Cobertura 12 de 15 módulos (80%)"`; `modules_total=0` → `"Sin módulos que cubrir"`; minería deshabilitada → el label correspondiente.
- `test_plan284_formatSkipReason_citas` — `"citations_below_threshold:2/9"` → el string en castellano con `"(2/9 verificadas)"`, **y** (presencia de control) que una razón preexistente como `"canonical_readonly"` sigue devolviendo su etiqueta de siempre — para probar que no rompimos el mapeo del 137.

**Comandos:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/docs/documenterModel.test.ts
npx tsc --noEmit
```

**Criterio de aceptación binario:** vitest `0 failed` con **al menos 4 tests más** que antes de la fase, y `npx tsc --noEmit` con exit 0 y sin salida.

**Verificación visual manual (la hace el operador, no el implementador):** lanzar el Documentador con una nota, confirmar que (1) el textarea aparece y acepta texto, (2) el run se detiene en "Esperando tu aprobación", (3) el veredicto se ve arriba con color, (4) los archivos aparecen agrupados.

**Flag:** hereda `STACKY_DOCS_PIPELINE_STAGES_ENABLED` y `STACKY_DOCS_RADIOGRAPHY_ENABLED`. Con ambas OFF el panel se ve exactamente como hoy.
**Runtimes:** la UI es única para los 3.
**Trabajo del operador:** ninguno nuevo (la aprobación de F5 reemplaza al Conservar/Descartar posterior, no se suma a él).

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Impacto | Mitigación |
|---|---|---|---|
| **R1** | **Las 3 etapas de papel triplican el costo de LLM por run.** Hoy el run cuesta N invocaciones (una por modo); pasa a N+3. | Alto en tokens | Corte de costo obligatorio en F5.2 (sin plan ⇒ no se critica ni se mejora); las 3 etapas se pagan **una vez por run**, no por modo; `STACKY_DOCS_PIPELINE_STAGES_ENABLED` se puede apagar desde la UI de flags y el run vuelve a costar lo de hoy. |
| **R2** | **El gate de citas rechaza demasiado y el run queda en 0 archivos.** Un modelo que cita mal produce `written=[]`. | Alto en UX | El umbral es una flag numérica editable (`..._MIN_RATIO`, default 0.8, no 1.0); los rechazados aparecen con su motivo y su preview en el panel (no desaparecen); el veredicto `INSUFICIENTE` lo dice explícitamente en vez de fingir éxito. Un doc sin citas **no** se rechaza (regla `total==0`). |
| **R3** | **La regla de taxonomía clasifica mal en repos de cliente.** `^\d{2,3}_` es la convención de Stacky; un proyecto del operador puede numerar distinto, o tener una carpeta `sistema/` que no sea canónica. | Medio | La clasificación es **aditiva y no destructiva**: sólo excluye del RAG y de la salud. Si clasifica de más, se apaga `STACKY_DOCS_TAXONOMY_ENABLED` y todo vuelve atrás sin migración. El caso frontera `docs/sistema/99_PLAN_FALSO.md` está explícitamente testeado. |
| **R4** | **La nota del operador desvía la documentación.** *(Reescrito en v2 — C22: la v1 sobreafirmaba.)* | Bajo, **pero real** | **Lo que la mitigación SÍ cubre:** el enforcement de **filesystem** es determinista en `apply_proposals` (anti-traversal `_safe_rel_path` `:547`, `docs/sistema/` read-only `_is_canonical` `:558`, tope de archivos `:581`, marcas de confianza `:591`). Ninguna nota puede escribir donde no debe, obedezca el modelo o no. **Lo que NO cubre, y hay que decirlo:** la nota **sí** puede desviar el *contenido* ("no menciones el módulo X", "decí que Y es seguro"). El gate de citas (F3) verifica que `archivo:línea` **exista y esté en rango**, explícitamente **no** que la línea diga lo que la doc afirma (Fuera de scope #5) ⇒ una nota puede producir prosa confiadamente sesgada con citas formalmente válidas. **Por qué se acepta:** Stacky es **mono-operador sin auth real**; la nota la escribe el operador para sí mismo. El modelo de amenaza no es un atacante, es el propio operador equivocándose. Blindar contra prompt-injection acá sería teatro (el mismo teatro que un RBAC en un producto sin login). **Mitigación efectiva:** la nota se persiste **verbatim** en el reporte y en el `.json` del historial (F2.4) y se muestra en el panel, así que siempre es auditable qué se pidió; y el veredicto de VERIFICAR no depende de la nota. |
| **R5** | **Registrar 9 flags rompe tests ajenos de fábrica** (4 de `test_harness_flags_help` + 1 de `env_read_meta`). | Medio | F0 obliga a sacar la foto del rojo previo **antes** de tocar nada y a comparar delta. Además: `_CURATED_DEFAULTS_ON` es obligatorio para las 7 ON, y el gate del texto de ayuda exige `Si ` sin tilde. Ambas trampas están escritas en F0.1. |
| **R6** | **El barrido de tickets toca la base viva.** | Alto si sale mal | El barrido es **sólo SELECT** (`session.query(Ticket)...`, sin `add`/`delete`/`commit`). Los tests corren con `sqlite:///:memory:` (ya seteado en `test_documenter_v2_pipeline.py:9`). El comando de censo abre la DB con `mode=ro`. **Nunca correr un pytest sin `DATABASE_URL` en memoria.** |
| **R7** | **`awaiting_approval` deja ramas `stacky/doc-*` colgadas** si el operador nunca aprueba. | Medio | `prepare_doc_branch` ya corre `git worktree prune` en cada arranque (`doc_documenter.py:477`); el endpoint de aprobación con `approve=false` llama `discard_doc_branch`; el mensaje de `run_not_found` ya instruye la limpieza manual (`api/docs.py:380-381`). |
| **R8** | **Sesión paralela en el árbol.** El repo tiene trabajo ajeno sin commitear. | Alto | El implementador commitea **sólo sus rutas** con `git commit -- "<ruta>"`. Prohibido `git add -A`, `git add .`, `git stash`, `git reset`, `git checkout --`. |

---

## 6. Fuera de scope (explícito, no tapado)

1. **Reescribir el Explorador del grafo del 268.** No se toca `docGraphModel.ts`, `forceLayout.ts` ni el layout. La radiografía es una lectura derivada.
2. **Meter los tickets en el grafo documental o en el corpus RAG.** Este plan los usa como **contexto del prompt** (F4), no los indexa como nodos. Meterlos en `doc_graph`/`docs_rag` es un plan aparte: exige decidir identidad de nodo, aristas ticket↔código y política de PII. **Queda fuera y se declara.**
3. **Minería de comentarios de tickets.** La tabla `pm_work_item_comments` (`services/pm/models.py:155`) tiene **0 filas** en la base viva: no hay corpus que minar todavía. Cuando lo haya, es una extensión natural de `doc_ticket_mining`.
4. **Triage de tickets por LLM.** Deliberadamente no: ver la justificación al inicio de F4.
5. **Validación semántica de la cita.** El gate verifica que `archivo:línea` **exista y esté en rango**; no verifica que la línea diga lo que la doc afirma. Eso requiere comparar contenido y es otro plan.
6. **Multi-idioma de la documentación generada.** Todo en español, como el resto del producto.
7. **Migrar los 240 planes a otra carpeta.** Se los clasifica, no se los mueve: mover 240 archivos rompería enlaces, historial de git y los anclajes de todos los planes anteriores.
8. **Tocar `docs/rag/rag_corpus.jsonl`** *(nuevo en v2 — C16)*. El archivo **existe** (169.544 bytes, 2026-07-15) pero es un **sidecar muerto**: 0 referencias en `backend/**` y `frontend/src/**`, sin productor ni consumidor en código. Este plan **no lo lee, no lo regenera y no lo borra**. Queda anotado como deuda declarada: **si alguien lo regenerara con la herramienta que lo creó, volvería a mezclar planes con documentación de proyecto** por el camino que F1 acaba de cerrar. Cerrar esa puerta (o borrar el sidecar) es un plan aparte de una sola fase.

---

## 7. Glosario

| Término | Significado en este plan |
|---|---|
| **Documentador** | El agente + pipeline de `doc_documenter.py` que genera documentación desde el código. Se lanza desde la pestaña Docs. |
| **DocTree** | El árbol de documentos que arma `doc_indexer.build_index` y sirve `GET /api/docs/index`. |
| **Grafo documental** | Nodos (notas, código, faltantes) y aristas (markdown, wikilink, code_ref) que arma `doc_graph.build_graph`. Del plan 109; explorado por el 268. |
| **`doc_class`** | Campo nuevo de este plan: `plan` \| `system` \| `project` \| `agent` \| `other`. |
| **Marcas de confianza** | `[V]` verificado contra código con archivo:línea, `[INF]` inferido, `[NV]` no verificable. Ya exigidas por el prompt (`doc_documenter.py:28-31`) y por el aplicador (`doc_documenter.py:591`). |
| **Cita** | Un `archivo:línea` dentro del texto. Extraída por `doc_evidence.extract_citations` y validada por `verify_citations`. |
| **Gate** | Un chequeo que **rechaza**, no que reporta. La diferencia entera de F3. |
| **Señal / ruido** | Veredicto del triage de tickets: `signal` aporta historia documentable, `noise` no. |
| **Radiografía** | Vista de cobertura: qué módulos tienen nota y cuáles no, más el veredicto del run. |
| **Etapa (stage)** | Una de las 5 del pipeline de F5. Distinto de **modo** (`RECONSTRUIR`/`NORMALIZAR`/…), que es del plan 113 y vive dentro de la etapa IMPLEMENTAR. |
| **Ratchet del arnés** | Los dos scripts `run_harness_tests.ps1` / `.sh` que exigen que todo archivo de test esté registrado. Divergen en sintaxis. |
| **Flag curada** | Flag booleana con `default=True` que además figura en `_CURATED_DEFAULTS_ON`. Sin las dos cosas, el test de defaults se pone rojo. |
| **Carpeta-sombra** | Fallback de `.stacky-docs-proposed` cuando el target no es un repo git (`doc_documenter.py:853`). |

---

## 8. Orden de implementación

> **Cambios de orden en v2:** F5.0 (habilitar `system_prompt_override` + `invoke_raw_stage`) va **antes** de todo F5 — sin eso F5 no compila. F7.0 (extender el tipo TS) va **antes** de la lógica de F7 — sin eso `tsc` falla. Y F1.2 (`doc_class` en `_serialize_node`) es **prerrequisito duro** de F1.3: `classify_doc_health` recibe nodos de `_serialize_node`, que hoy expone 9 claves y **ninguna es `doc_class`` — si F1.3 se hace primero, filtra sobre un campo que no existe y no filtra nada (falso verde silencioso).

1. **F0.1** — Registrar las **11** flags (foto del rojo previo ANTES). Las **11** van a `_CURATED_DEFAULTS_ON` en `backend/tests/test_harness_flags.py:467-1003`. Correr `tests/test_harness_flags.py` y comparar **delta**.
2. **F0.2** — `doc_taxonomy.py` + sus 2 tests en `test_doc_evidence.py`. Verde.
3. **F1** — `doc_class` en índice, grafo, salud y RAG + `class_summary` en la API. 4 tests en `test_documenter_v2_pipeline.py`. Verde + censo C1..C4 en True.
4. **F2** — Nota del operador: UI → `endpoints.ts` → `api/docs.py` → `doc_documenter` → `_operator_note_block` → `build_context_for_mode`. **5** tests backend + 1 frontend. Verde + censo AST del consumidor = 1 + **`test_plan284_nota_viaja_de_run_documenter_al_prompt` en verde (gate real de la fase)**.
5. **F3** — Gate de citas: `evaluate_citation_gate` puro primero, después reordenar `apply_proposals`. 3+1 tests. Verde + censo AST de orden write/verify = 0.
6. **F4** — `doc_ticket_mining.py` (con `_es_sintetico`, `ado_state` y `scope`) + cableado en `build_context_for_mode`. **5** tests. Verde + censo `mine_project_tickets` C1..C4 en True (**all=228, RIPLEY=65**).
7. **F5.0** — **PRIMERO**: `system_prompt_override` en `invoke_documenter` + `invoke_raw_stage`. 2 tests. Verde + censo AST del kwarg = 1. **Sin esto, nada de F5 se puede construir.**
8. **F5** — Etapas, prompts, corte de costo, HITL y endpoint de aprobación **con sus 4 tests y su función cliente**. Registrar `test_docs_api.py` en **los dos** ratchets. 7 tests. Verde + censo de orden G1/G2.
9. **F6** — `doc_radiography.py` + delta (A2) + presupuesto (A1) + claves nuevas en `documenter_status`. 6 tests. Verde + censo A1/P1 en True.
10. **F7.0** — Extender `DocumenterStatusResponse` con las 6 claves opcionales. `tsc --noEmit` verde **antes** de escribir la lógica.
11. **F7** — UI: 3 funciones puras en `documenterModel.ts` + panel. 4 tests vitest + `tsc --noEmit`. Verde.
10. **Cierre** — correr los 3 archivos de test backend por separado + vitest + tsc, y anotar el resultado real (pegado, no resumido) en la sección de estado de este documento.

---

## 9. Definición de Hecho (DoD) global

Un implementador puede declarar este plan terminado **sólo si** todo lo siguiente es cierto y está pegado como evidencia:

- [ ] `pytest tests/test_doc_evidence.py -q` → `0 failed`, con **≥ 20** tests (hoy 18).
- [ ] `pytest tests/test_documenter_v2_pipeline.py -q` → `0 failed`, con **≥ 16** tests más que el baseline del archivo.
- [ ] `pytest tests/test_documenter_autonomy.py -q` → `0 failed` (no debe romperse: es el guardián de la autonomía del 113).
- [ ] `pytest tests/test_docs_api.py -q` → `0 failed` (los endpoints tocados, incluido `/documenter/stage/approve`).
- [ ] `pytest tests/test_harness_flags.py -q` → **el mismo número de fallos que el baseline capturado en F0.1**, ni uno más. Los 4-5 rojos ajenos son de fábrica; sumar uno nuevo es un defecto de este plan. **En particular `test_default_known_only_for_curated` tiene que quedar en el mismo estado que el baseline** — si se pone rojo, faltan claves en `_CURATED_DEFAULTS_ON` (ver C4).
- [ ] `npx vitest run src/docs/documenterModel.test.ts` → `0 failed`, con **≥ 5** tests nuevos (hoy son **14**; el piso es **19**).
- [ ] `npx tsc --noEmit` → exit 0, sin salida. **Requiere haber hecho F7.0 primero** (extender `DocumenterStatusResponse`), o falla por las 6 claves nuevas.
- [ ] Los censos por comando de **F1, F2, F3, F5.0, F5, F6 y F4** devuelven exactamente el valor declarado.
- [ ] **Con las 11 flags en su default, el comportamiento del Documentador es el descrito por este plan; con las 7 booleanas nuevas ON puestas en OFF y `AUTOAPPLY` en su default, el reporte tiene exactamente las mismas claves que hoy.** (Backward-compat probada por `test_plan284_pipeline_off_es_backward_compatible`.)
- [ ] **El cable de la nota está probado end-to-end**: `test_plan284_nota_viaja_de_run_documenter_al_prompt` en verde. Sin este test, F2 **no está hecha** aunque el resto esté verde (C6).
- [ ] **`test_docs_api.py` quedó registrado en `run_harness_tests.ps1` Y en `run_harness_tests.sh`** (hoy no está en ninguno). El ratchet es trampa de commit, no sólo de edición.
- [ ] Ningún archivo de test backend nuevo fue creado (los 4 archivos usados —`test_doc_evidence.py`, `test_documenter_v2_pipeline.py`, `test_documenter_autonomy.py`, `test_docs_api.py`— existen; los 3 primeros ya estaban registrados en ambos scripts y el cuarto se registra en esta implementación).
- [ ] **Huella de regresión anotada** en `Stacky Agents/docs/sistema/error_fingerprints.json` (C23): id `plan284-citas-decorativas`, patrón "archivo escrito con citas `archivo:línea` inexistentes", plan/commit, fecha y `guard_test = test_plan284_gate_no_escribe_el_archivo_con_citas_falsas`.
- [ ] Ningún `git add -A`, `git add .`, `git stash`, `git reset` ni `git checkout --` durante la implementación. Commits con pathspec explícito.
- [ ] Sin `git push`.
- [ ] La sección de estado de este documento quedó actualizada con el output real de los comandos, pegado.

---

## 10. Trazabilidad: los 7 pedidos del operador → fases

| # | Pedido textual | Fase | Criterio que lo prueba |
|---|---|---|---|
| 1 | "no se entiende bien" | **F7** (+ F5.4 veredicto) | 4 tests de vitest sobre `buildStagesView`/`buildVerdictView`/`buildRadiographyView` + verificación visual del operador |
| 2 | "se mezclan los planes de los del proyecto" | **F1** | Censo C1..C4 en True (240 `plan` / 15 `system` al 2026-08-01); el RAG excluye planes; la salud los ignora |
| 3 | "que me permita darle una NOTA EXTRA" | **F2** | **`test_plan284_nota_viaja_de_run_documenter_al_prompt`**: el centinela aparece en `render_blocks` de los bloques que **realmente recibe el LLM** desde `run_documenter`. El censo AST del consumidor (=1) es complementario, **no** suficiente |
| 4 | "primero proponer, criticar, mejorar, implementar, verificar" | **F5.0 + F5** | `STAGE_ORDER` de 5; los 3 prompts de etapa escritos; `invoke_raw_stage` devuelve texto crudo; el run se detiene en `awaiting_approval` **sin escribir**; veredicto siempre presente (incl. `PENDIENTE_DE_APROBACION`) |
| 5 | "grafo súper complejo que robustezca lo existente, radiografía" | **F6 + A2** | `compute_coverage` sobre el grafo del 268 **sin** motor paralelo (A1) **y leyéndolo de verdad** (P1); más el **delta contra el run anterior**, que es lo que lo vuelve radiografía y no foto |
| 6 | "mirar TODOS los tickets, diferenciar basura de valioso" | **F4** | **228** con `scope="all"` / **65** en el proyecto activo (números medidos, no prometidos); `classify_ticket` con **10** casos de tabla con todos los campos fijados; `_es_sintetico` cubre las **103** filas con id negativo; `ado_state` separa **obsoleto** (cerrado y flaco) de **historia** (cerrado y documentado) |
| 7 | "muy lento y pausado para no alucinar sobre el código" | **F3** (+ F0.2) | El archivo con citas falsas **no existe en disco**; censo AST de orden write/verify = 0 |

---

**Última línea:** este plan **no** re-propone la evidencia de módulo (137 F1), el verificador de citas (137 F2), el short-circuit (137 F3), el historial (137 F4), el preview (137 F5) ni el explorador (268). Los usa. Lo único que hace con ellos es **conectarlos y darles consecuencia**.

---

## 11. ESTADO DE IMPLEMENTACIÓN (2026-08-01)

**Estado:** IMPLEMENTADO F0..F7 — rama `docs/plan-279`, 6 commits, **sin push**.
**Implementador:** StackyArchitectaUltraEficientCode (contexto limpio, no escribió ni criticó este plan).

### 11.1 Foto del ROJO PREVIO (F0.1, tomada ANTES de tocar un solo archivo)

| Archivo | Baseline |
|---|---|
| `tests/test_doc_evidence.py` | `18 passed` |
| `tests/test_documenter_v2_pipeline.py` | `10 passed` |
| `tests/test_documenter_autonomy.py` | `6 passed` |
| `tests/test_docs_api.py` | `11 passed` |
| `tests/test_harness_flags.py` | **`56 passed, 0 failed`** |
| `tests/test_harness_flags_help.py` | **`4 failed, 4 passed`** (rojo ajeno) |
| `tests/test_error_fingerprints_catalog.py` | **`3 failed, 5 passed`** (rojo ajeno) |
| `npx vitest run src/docs/documenterModel.test.ts` | `14 passed` |
| `npx tsc --noEmit` | exit 0 |

> **El plan se equivocaba en R5/F0.1:** anunciaba "5 tests ajenos en rojo de fábrica"
> en `test_harness_flags.py`. **Ese archivo estaba en VERDE (56 passed, 0 failed).**
> Los 4 rojos ajenos viven en `test_harness_flags_help.py`, que es otro archivo.
> La barra quedó por lo tanto más exigente: cualquier rojo en `test_harness_flags.py`
> después del cambio sería mío.

### 11.2 Resultado final REAL (output pegado, no resumido)

```
test_doc_evidence                    25 passed in 0.81s
test_documenter_v2_pipeline          38 passed, 7 warnings in 19.69s
test_documenter_autonomy              6 passed in 2.82s
test_docs_api                        16 passed, 100 warnings in 10.91s
test_harness_flags                   56 passed, 29 warnings in 6.39s
test_harness_flags_help               4 failed, 4 passed in 2.59s   <- = baseline
test_error_fingerprints_catalog       3 failed, 5 passed in 0.81s   <- = baseline

npx vitest run src/docs/documenterModel.test.ts   20 passed (20)
```

**Delta contra el baseline: +7 / +28 / 0 / +5 / 0 / 0 / 0 backend, +6 frontend.
Ningún rojo nuevo.** Los pisos del DoD se cumplen: `test_doc_evidence` ≥ 20 (25),
`test_documenter_v2_pipeline` ≥ 26 (38), vitest ≥ 19 (20).

### 11.3 Los 3 gates innegociables

| Gate | Resultado |
|---|---|
| `test_plan284_nota_viaja_de_run_documenter_al_prompt` | **VERDE** — `1 passed, 18 deselected` (collected 1: no es un `-k` sin match) |
| `test_plan284_sin_autoaplicado_el_run_espera_aprobacion` | **VERDE** — `1 passed, 37 deselected` |
| `test_docs_api.py` en los DOS ratchets | **OK** — `run_harness_tests.ps1:366` y `run_harness_tests.sh:417`, cada uno en su sintaxis |

### 11.4 Censos

| Censo | Esperado | Real |
|---|---|---|
| F1 taxonomía C1..C4 | 4× True | **4× True** — 309 `.md` → `plan=240, system=15, project=54` (idéntico a lo medido en el plan) |
| F2 consumidor `_operator_note_block` | 1 | **2** — ver desvío D2 |
| F3 orden `write_text`/`verify_citations` | 0 | **0** (verify en `:675`, write en `:691`) |
| F4 `mine_project_tickets` C1..C4 | 4× True | **4× True** — all=228 (signal 116 / noise 112), RIPLEY=65 (signal 63 / noise 2), `{azure_devops:162, gitlab:63, demo:3}` |
| F5.0 kwarg `system_prompt_override` | 1 | **1** |
| F5 orden G1/G2 | 2× True | **2× True** (flag leída en `:840`, escritura en `:937`) |
| F6 A1/P1 | 2× True | **2× True** |

### 11.5 Desvíos declarados

**D1 — `_CURATED_DEFAULTS_ON`: van 6 claves, no 11 (el plan pedía 11).**
C4 mandaba curar las 11 flags. **Es imposible:** el set está vigilado por DOS asserts
que se contradicen si se lo hace. `test_default_known_only_for_curated` exige que toda
spec con `default=` esté en el set; `test_declared_default_true_set` exige que toda key
del set tenga `declared_default is True`. Un `default=False` (`AUTOAPPLY`) o un `default=`
numérico (los 4 knobs) no puede cumplir ambos. Se siguió la convención real del repo,
idéntica al precedente que el propio archivo documenta para el plan 279: sólo las **6
booleanas ON** declaran `default=True` y se curan; la OFF y las 4 numéricas **no declaran
`default=`**. Resultado: `56 passed, 0 failed`, igual al baseline.

**D2 — el censo AST de F2 da 2, no 1.**
Después de F5 hay **dos** consumidores de producción de `_operator_note_block`, ambos
legítimos: `build_context_for_mode:341` (la nota llega a los modos que escriben) y
`_run_paper_stage:802` (la nota también guía PROPONER/CRITICAR/MEJORAR, que es
justamente lo que el operador quiere). El criterio `=1` se escribió para F2 en
aislamiento, antes de que F5 existiera. La **intención** del censo ("existe un consumidor
de producción, no sólo la definición") se cumple con más fuerza. El gate real de F2 es el
test end-to-end, y el propio plan dice que el censo AST es "complementario, **no**
suficiente".

**D3 — `harness_flags_help.py` no estaba en el plan.**
Registrar flags sin su ayuda llana habría engrosado la deuda de
`test_plain_help_covers_all_registry_keys` (82 claves sin ayuda). Se escribieron las **11**
entradas `PlainHelp` respetando el gate de `"Si "` sin tilde y la denylist de jerga.
Delta del archivo: 0 (sigue en `4 failed, 4 passed`, y ninguna key del 284 aparece en los rojos).

**D4 — dos tests preexistentes ajustados (no debilitados).**
Con las etapas ON por default, `test_short_circuit_no_invoca_modos_sin_targets` y
`test_flag_off_invoca_todos_los_modos` pasaban a medir el gate humano en vez del
short-circuit de MODOS que les da nombre. Se les fija
`STACKY_DOCS_PIPELINE_STAGES_ENABLED=False` explícitamente (la regla del repo al flipear
un default), **conservando intactos todos sus asserts**.

**D5 — el máximo de la nota viaja desde el backend.**
C18 pedía que el tope no se hardcodeara. Se agregó `operator_note_max_chars` (y
`operator_note_enabled`) a `GET /api/docs/sources`, que es la superficie que la página
Docs ya consume.

### 11.6 Bug de cableado encontrado y cerrado (no estaba en el plan)

El panel se renderiza sólo si `uiState !== "running" && !== "unknown"`, y
`"awaiting_approval"` caía en `"unknown"` ⇒ los botones **"Aprobar e implementar" /
"Cancelar" habrían existido y nadie los habría visto nunca**: el patrón exacto de
*código construido, testeado y jamás cableado* que este plan viene a combatir, esta vez
en la UI. Corregido: `awaiting_approval` y `budget_exhausted` son estados de UI de
primera clase, el polling sigue vivo mientras espera aprobación, y quedó el test de
guardia `test_plan284_awaiting_approval_no_cae_en_unknown` con presencia de control.

### 11.7 Pendiente para el operador

1. **`npx tsc --noEmit` da exit 2 por trabajo AJENO sin commitear.** Los 9 errores están
   en `FinishWorkButton.tsx`, `QaBrowserRunModal.tsx` y `TicketBoard.tsx` (plan 282 F4 en
   vuelo: un `import { useWorkbench }` duplicado). **Ninguno de los 3 archivos aparece en
   ninguno de los 6 commits de este plan, y `tsc` no reporta un solo error en los archivos
   del 284.** Al cerrar F7 (commit `241a228f`) `tsc` daba **exit 0**.
2. **Smoke visual manual** (lo hace el operador): lanzar el Documentador con una nota y
   confirmar que (1) el textarea aparece y acepta texto, (2) el run se detiene en
   "Esperando tu aprobación", (3) el veredicto se ve arriba con color, (4) los archivos
   aparecen agrupados y los rechazados por citas tienen su sección.
3. **Sin push** (riel del repo: el push es siempre manual).
4. `endpoints.ts` conserva cambios sin commitear de la sesión paralela (plan 282, región
   `Tickets`): se commitearon **sólo** los hunks del 284 vía index.
