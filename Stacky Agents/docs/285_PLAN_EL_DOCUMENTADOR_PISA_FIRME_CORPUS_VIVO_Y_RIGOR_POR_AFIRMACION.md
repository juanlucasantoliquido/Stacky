# Plan 285 — El Documentador pisa firme: corpus vivo, rigor por afirmación y descarte trazable

**Estado:** **IMPLEMENTADO** (v2 construida el 2026-08-02 — ver §13)
**Versión:** v1 (PROPUESTO, commit `56c7f42c`) → **v2** (esta, `e4d3ef30`) → IMPLEMENTADA
**Veredicto de la crítica v1:** **RECHAZADO** — 6 hallazgos BLOQUEANTES, 9 MAYORES, 3 MENORES.
**Fecha:** 2026-08-01
**Rama de origen:** `docs/plan-279`

| Fase | Estado | Evidencia |
|---|---|---|
| **F0.1** saldar el mapa `requires` | **IMPLEMENTADA** | `1 failed, 8 passed` → **`9 passed`** |
| **F0** red-team (11 tests) | **IMPLEMENTADA** | rojo previo medido: `4 failed, 25 passed` + `7 failed, 38 passed` |
| **F1.0** `build_base_blocks` | **IMPLEMENTADA** | las etapas de papel pasan de **1** bloque a **≥ 4** |
| **F1.1** `ensure_corpus_indexed` | **IMPLEMENTADA** | + `skipped_plans` aditivo en `index_project` |
| **F1.4** `_corpus_block` | **IMPLEMENTADA** | `grep docs_rag doc_documenter.py`: **0 → 6** |
| **F1.2** panel del corpus | **IMPLEMENTADA** | `buildCorpusView` cableada en `DocumenterResultPanel` |
| **F1.3** huérfanos + backup + purga | **IMPLEMENTADA** (purga **NO EJECUTADA**) | pendiente de aprobación del operador — ver §13.3 |
| **F2** rigor por afirmación | **IMPLEMENTADA** | alcanzable en las 4 combinaciones de flags |
| **F3** descarte trazable | **IMPLEMENTADA** | `ticket_mining` deja de devolver `{}` |
| **F4** el árbol deja de mezclar | **IMPLEMENTADA** | `doc_class` en el frontend: **2 → 11** hits |
| **F5** 7 ratchets | **IMPLEMENTADA** | por ALCANZABILIDAD, no por orden de líneas |
**Antecesor directo:** `284_PLAN_EL_DOCUMENTADOR_DEJA_DE_MEZCLAR_Y_DE_ADIVINAR_RADIOGRAFIA_VERIFICADA.md` (IMPLEMENTADO hoy, commits `f881f615` → `ac66a7af`)

> **Lección que gobierna esta v2.** La v1 tenía **91 de 93 anclajes `archivo:línea` correctos (97,8 %)** y aun así fue rechazada. Igual que el 284 (101/104 y 6 bloqueantes), sus defectos **no estaban en dónde miraba sino en qué daba por existente y en qué orden lo hacía**. Verificar anclajes es el **piso**, no el techo. Todo lo que sigue está medido el 2026-08-01 sobre el árbol de HOY, **ejecutando** los comandos, no leyéndolos.

---

## 1. Objetivo y KPI

El plan 284 construyó, hoy mismo, siete capacidades para el Documentador. **Sus 79 tests pasan cuando se corren por archivo** (medido: `test_doc_evidence.py` 25, `test_documenter_v2_pipeline.py` 38, `test_docs_api.py` 16). Y sin embargo el operador, después de todo eso, sigue reportando que el Documentador *no se entiende* y *mezcla los planes con la documentación del proyecto*.

Este plan no re-propone nada del 284. Se apoya en una medición hecha sobre el árbol de HOY. La v1 encontró cinco brechas; **la crítica encontró que la más importante estaba mal diagnosticada** y descubrió una sexta que las explica a todas.

### 1.1 La tesis corregida (v2)

La v1 decía: *"el material sobre el que operan las reglas está muerto"*. Es cierto que está muerto, pero **la v1 nunca verificó quién LEE ese material**, y la respuesta es: **el Documentador no lo lee**. La tesis correcta es:

> **El operador aprieta el botón, el sistema hace TRES llamadas al LLM con UN SOLO bloque de contexto, y se detiene a esperar su aprobación. Todo el contexto rico que el 284 construyó (evidencia de código, tickets, subgrafo) vive del OTRO LADO de esa barrera y sólo se usa DESPUÉS de que el operador aprobó algo que leyó a ciegas.**

Evidencia dura (§3.0). Por eso este plan agrega una fase **F1.0** que no existía en la v1 y que es, ahora, la fase raíz.

### 1.2 KPI (todos medibles con un comando, ninguno subjetivo)

| # | KPI | Valor HOY (medido y **ejecutado** 2026-08-01) | Meta del 285 |
|---|---|---|---|
| **K0** | Bloques de contexto que reciben las 3 etapas de papel (el camino DEFAULT, lo que el operador lee antes de aprobar) | **1** (`_sistema_readonly_block`, `doc_documenter.py:1287`) + la nota si la hay | **≥ 4** (suma corpus, subgrafo y tickets) |
| K1 | Documentos reales del proyecto activo en el corpus RAG vivo (`docs_index`) | **0** (51 chunks, 22 archivos, **todos** fixtures de test) | **≥ 1 archivo real** y `chunks_indexed > 0` para el proyecto activo — **nunca un número absoluto** (ver C12) |
| K2 | Proyectos fantasma en `docs_index` | **8** (`C1` 41, `D1` 2, `K1` 2, `M1` 2, `N1` 1, `PF1` 1, `PF2` 1, `ST1` 1) | **0** tras purga confirmada por el operador |
| K3 | Documento alucinado (0 citas + 1 sola marca en 500 líneas) que el gate deja escribir | **SÍ se escribe** (`doc_documenter.py:190` y `:865`) | **Se rechaza en las 4 combinaciones de flags**, con motivo visible |
| K4 | Tickets descartados que el operador puede ver, con su motivo | **0** — `api/docs.py:363` devuelve `{}` siempre | **100 %** de los `noise`, con `reasons` |
| K5 | Modos del Documentador que reciben el subgrafo documental | **1 de 5** (sólo `ENRIQUECER`, `doc_documenter.py:339`) | **3 de 5** (+ `RECONSTRUIR`, `COMPLETAR`); `NORMALIZAR` y `ACTUALIZAR` **congelados en NO** |
| K6 | Uso de `doc_class` en el árbol de documentación que ve el operador | **2 hits, ninguno en el árbol** (`endpoints.ts:3595`, `documenterModel.ts:312`) | El árbol **agrupa y filtra** por clase |
| **K7** | Rojos de fábrica en las suites que este plan toca | **3 archivos** (`test_harness_flags_help.py` 4F/4P, `test_error_fingerprints_catalog.py` 3F/5P, **`test_harness_flags_requires.py` 1F/8P**) | **≤ 2** (este plan **salda** el tercero, que es deuda directa del 284) |

---

## 2. Por qué ahora — la contradicción que hay que explicar

El 284 se dio por implementado con evidencia real. La medición confirma que **no mintió**. Entonces, ¿por qué el operador sigue con el mismo dolor?

Porque en Stacky el modo de falla dominante no es "no se construyó". Es **"se construyó, se testeó, quedó verde, y el camino que el usuario dispara pasa por al lado"**. Hay **seis** variantes vivas:

0. **(NUEVO en v2 — el que explica a todos los demás) El camino default se corta antes.** `run_documenter` retorna en `:1335` esperando aprobación humana, **antes** del loop de modos. Las 3 llamadas al LLM que sí ocurren (`:1289-1307`) reciben `base_blocks = [_sistema_readonly_block(project_name)]` — un solo bloque. El operador juzga *eso*.
1. **El filtro correcto sobre un corpus vacío… que además nadie lee.** `docs_rag.py:164-169` excluye los planes con la regla correcta, pero el corpus (`docs_index`) tiene cero documentos reales **y `doc_documenter.py` nunca consulta `docs_rag`** (§3.1). El filtro es perfecto, no filtra nada útil, y el Documentador ni se entera.
2. **La clasificación que el frontend ignora.** `doc_indexer.py:172` etiqueta `doc_class`; el frontend lo usa en 2 lugares y **ninguno es el árbol**. El operador sigue viendo ~241 planes revueltos con la documentación del proyecto. Eso es, literalmente, la queja.
3. **Gates con el cuantificador equivocado.** `marks_ok = any(...)` (`:190`) + `total <= 0 ⇒ passed=True` (`:865`): un documento largo con un `[V]` decorativo y cero citas pasa los dos y se escribe.
4. **El triage que nadie ve.** `classify_ticket` está cableada (`:332`) pero el resultado sale de scope y `api/docs.py:363` devuelve `{}` siempre.
5. **El contexto que llega a un solo modo.** El subgrafo se inyecta sólo en la rama `ENRIQUECER` (`:339`), de **cinco** modos.

Ninguno se arregla re-escribiendo el 284. Los seis son de **cableado, cuantificador, orden o visibilidad**.

---

## 3. Foto medida — evidencia que sostiene cada fase

> **Regla del plan:** toda afirmación de esta sección fue verificada **ejecutando** el comando o abriendo el archivo el 2026-08-01. Los anclajes de línea **caducan entre pasadas**: anclá por **símbolo**, y si encontrás divergencia **detenete y reportala antes de codificar**.

### 3.0 (NUEVO v2) El camino que el operador dispara — la barrera HITL

| Hecho | Evidencia |
|---|---|
| El run se detiene ANTES del loop de modos | `backend/services/doc_documenter.py:1311` → `if _stages_enabled() and not _resolve_autoapply(autoapply_override):` … `return pending` en `:1335` |
| Los defaults ponen esa barrera ACTIVA | `backend/config.py:776` → `STACKY_DOCS_PIPELINE_STAGES_ENABLED` default **true**; `STACKY_DOCS_PIPELINE_AUTOAPPLY` default **false** (correcto por categoría B) |
| Las 3 etapas de papel reciben UN bloque | `doc_documenter.py:1287` → `base_blocks = [_sistema_readonly_block(project_name)]`; el loop de etapas en `:1289-1307` |
| `_run_paper_stage` no agrega contexto de dominio | `doc_documenter.py:792-811`: `blocks = list(base_blocks or [])`, + `_operator_note_block` (`:802`) + el artefacto previo (`:805-810`). Nada más. |
| El loop de modos (con TODO el contexto rico) vive después | `doc_documenter.py:1349` (`for mode in plan.modes:`) → `:1363` `build_context_for_mode(...)` |
| Sólo se llega ahí tras aprobación | `resolve_stage_approval` (`:1060`) → `_resume_after_approval` (`:1098`) → `run_documenter(..., autoapply_override=True, _prior_stages=...)` (`:1101-1107`) |

**Consecuencia operativa:** cualquier mejora que se cablee **sólo** en `build_context_for_mode` es invisible para el artefacto que el operador lee y aprueba. Es la razón de F1.0.

### 3.1 Corpus documental — quién lo escribe y quién lo lee (F1)

| Hecho | Evidencia |
|---|---|
| Tabla del corpus vivo | `backend/services/docs_rag.py:70` → `__tablename__ = "docs_index"` |
| Contenido real (SELECT **ejecutado**, solo lectura) | 51 chunks / 22 `file_path` / 8 `project_name`: `C1`(41), `D1`(2), `K1`(2), `M1`(2), `N1`(1), `PF1`(1), `PF2`(1), `ST1`(1). Archivos: `a.md`, `b.md`, `n0.md`…`n19.md`. **Todos fixtures de test.** `indexed_at` entre `2026-07-10 10:31:54` y `10:32:12`. |
| Base viva | `Stacky Agents/backend/data/stacky_agents.db` (**193.253.376 bytes**). `Stacky Agents/DeployStackyAgents/data` **NO EXISTE**. |
| Único **escritor** de producción | `backend/api/docs_rag.py:143` → `result = index_project(name, workspace_root, docs_subpath)`, dentro de `route_index()` (`:127`, decorador `@bp.post("/index")` en `:126`) |
| **(NUEVO v2) Los únicos LECTORES de producción** | `backend/api/docs_rag.py:192` y `:195` → `docs_rag_service.search_hybrid(...)` (endpoints HTTP de búsqueda/chat) y `backend/services/validation_playbook.py:429` → `docs_rag.search(project_name, f"cómo validar {ticket_title}", top_k=5)`. **Nada más.** |
| **(NUEVO v2) `doc_documenter.py` NO consulta el corpus** | `grep -rn "docs_rag" backend/services/doc_documenter.py` → **0 líneas**. El Documentador no importa `docs_rag` ni llama a `search`/`search_hybrid` en ninguna parte. **Por eso indexar, solo, no le da nada: hay que cablear también la lectura (F1.4).** |
| El filtro plan/proyecto existe y es correcto | `backend/services/docs_rag.py:164-169` → `if not doc_taxonomy.is_plan_doc(...)`, gateado por `STACKY_DOCS_TAXONOMY_ENABLED` |
| La regla de clasificación es la ESTRICTA | `backend/services/doc_taxonomy.py:28-30` → `_NUMBERED_DOC_RE = re.compile(r"^\d{2,3}_(plan\|incidente\|checklist\|auditoria\|postmortem)_", re.IGNORECASE)` |
| Censo del árbol de docs (**re-medido**) | **310** `.md` bajo `Stacky Agents/docs/`; **241** matchean la regla estricta; **258** matchean `^\d{2,3}_` a secas ⇒ **17 falsos** que la regla estricta evita. (La v1 decía 309/240/257 porque se contó **antes de escribirse a sí misma**. Es la prueba de por qué **estos números NO pueden ser criterios de aceptación** — ver C12.) |
| El re-index purga sólo su propio proyecto | `backend/services/docs_rag.py:199` → `session.query(DocChunk).filter_by(project_name=project_name).delete()` ⇒ los 8 fantasmas **nunca** se limpian solos |
| `index_project` devuelve | `docs_rag.py:205-208` → `{"chunks_indexed", "files_scanned"}` (y `{"...","warning"}` en `:158` si el dir no existe) |

### 3.2 Gates de rigor (F2)

| Hecho | Evidencia |
|---|---|
| Marcas de confianza | `doc_documenter.py:165` → `_MARKS = ("[V]", "[INF]", "[NV]")` |
| **Agujero 1 — cuantificador existencial** | `doc_documenter.py:190` → `marks_ok = any(tok in body for tok in _MARKS)`, dentro de `parse_proposals` (`:174`) |
| Consecuencia del agujero 1 | `apply_proposals` (`:882`) skippea con `"missing_confidence_marks"` en `:911` sólo si `marks_ok` es `False` ⇒ un `[V]` suelto en 500 líneas basta |
| **Agujero 2 — un doc sin citas pasa** | `doc_documenter.py:865` → `if total <= 0: return {"passed": True, "ratio": 1.0, "reason": ""}` dentro de `evaluate_citation_gate` (`:843`) |
| El gate de citas SÍ rechaza (el 284 lo cerró bien) | `doc_documenter.py:914-932`: la verificación (`:921`) va **antes** de la escritura (`:937`), con `continue` en `:932`. **No tocar.** |
| **(NUEVO v2) `citations` es `None` fuera del `if`** | `doc_documenter.py:918` → `citations = None`; sólo se puebla dentro de `if workspace_root is not None:` (`:919-922`) |
| **(NUEVO v2) y `workspace_root` puede llegar `None`** | `doc_documenter.py:1391` → `workspace_root=(workspace_root if (_v2_enabled() or _citation_gate_enabled()) else None)` ⇒ con V2 OFF **y** gate de citas OFF, `citations` es `None` en todo el loop. **Éste es el motivo de C4.** |
| Degradación del gate de citas | `doc_documenter.py:872-874` → `except Exception: return {"passed": True, ...}` |
| Defaults reales del gate | `backend/config.py:763` → `os.getenv("STACKY_DOCS_CITATION_GATE_ENABLED", "true")`; `:766` → `os.getenv("STACKY_DOCS_CITATION_GATE_MIN_RATIO", "0.8")` |
| **(CORREGIDO v2) Hay CINCO modos, no cuatro** | `doc_documenter.py:56-61` → `RECONSTRUIR`, `NORMALIZAR`, `COMPLETAR`, `ACTUALIZAR`, `ENRIQUECER` |
| El subgrafo llega a un solo modo | `doc_documenter.py:339` → `blocks.append(_subgraph_block(project_name))`, dentro de `elif mode == DocumenterMode.ENRIQUECER` (`:338`). Definición en `:219`. La rama `RECONSTRUIR/COMPLETAR` arranca en `:324`. |
| **(NUEVO v2) `_render_blocks` ignora `kind`** | `backend/services/context_enrichment.py:1433-1455` → usa `title`, `content` e `items`; **nunca lee `kind`**. Un bloque nuevo comunica **por `title` + `content`**; poner semántica en `kind` es decorativo. |

### 3.3 Minería de tickets (F3)

| Hecho | Evidencia |
|---|---|
| Censo de tickets (SELECT **ejecutado**) | **228** totales. Por proyecto: `RIPLEY` 65, `RSPACIFICO` 57, `p` 49, `P` 44, `ONP` 6, `RSSICREA` 3, `__demo__` 3, `test` 1. Por tracker: `azure_devops` 162, `gitlab` 63, `demo` 3. `ado_id < 0`: **103**. |
| Triage: función y umbrales | `doc_ticket_mining.py:81` `classify_ticket`; umbrales en `:19` (`MIN_DESCRIPTION_CHARS = 200`), `:20` (`MIN_TITLE_CHARS = 15`), `:21` (`STRONG_SIGNAL_CHARS = 800`); veredicto en `:143` → `verdict = "signal" if score >= 2 else "noise"` |
| El caso de `p`/`P` ya está resuelto | `doc_ticket_mining.py:182-188`: el filtro compara con `func.lower(...)`. **No re-abrir.** |
| **El resultado del triage se pierde** | `doc_documenter.py:332-333`: `mining` se calcula, se consume una vez para `build_tickets_context_block` y sale de scope. `grep -n "ticket_mining" backend/api/docs.py` → sólo `:363`, y **nada de producción escribe esa clave** ⇒ el endpoint devuelve `{}` siempre. |
| **Truncamiento silencioso nº1 (SQL)** | `doc_ticket_mining.py:190` `total_rows = q.count()`; `:191` `q.limit(cap)`; `:201` devuelve `"total": len(verdicts)` (**ya capado**); `:204` `"truncated": total_rows > cap`. `build_tickets_context_block` (`:210`) **nunca lee `"truncated"`** y en `:243` escribe `f"Se barrieron {total} tickets; ..."` con el número recortado. |
| **(NUEVO v2) Truncamiento silencioso nº2 (caracteres)** | `doc_ticket_mining.py:228-235`: el propio bloque corta por `max_chars=12000` (`:210`), setea `truncado = True` (`:229`) y agrega `"\n[...corpus truncado]"` (`:235`). **Son DOS ejes de truncamiento.** Además `total` (`:236`) cuenta **signal + noise** mientras el cuerpo lista **sólo signal**. |
| `verdicts` son dataclasses, no dicts | `doc_ticket_mining.py:71` `class TicketVerdict`; `:217-218` filtra con `getattr(v, "verdict", "")` |
| **El fallo del barrido es mudo** | `doc_documenter.py:330-337`: el `try/except` traga con `logger.warning`. El modelo documenta sin historia y nadie se entera. |
| Flags | `config.py:770` → `STACKY_DOCS_TICKET_MINING_ENABLED` default **true**; `:773` → `STACKY_DOCS_TICKET_MINING_MAX` default **500** |

### 3.4 Legibilidad del árbol (F4)

| Hecho | Evidencia |
|---|---|
| El backend clasifica | `doc_indexer.py:99` `_doc_class_for` (devuelve `""` con la flag de taxonomía OFF), `:172` `"doc_class": _doc_class_for(rel_path)`, `:188` `"doc_class": "other"` para carpetas |
| El frontend lo ignora | `grep -rn "doc_class\|docClass" frontend/src/` → **2** hits, ambos de la radiografía: `frontend/src/api/endpoints.ts:3595` (`by_doc_class?`) y `frontend/src/docs/documenterModel.ts:312` (`const porClase = r.by_doc_class ?? {}`). **Cero en el árbol.** |
| El árbol vive en | `frontend/src/pages/DocsPage.tsx` (472 líneas); tabs `"Lector"` (`:386`), `"Cobertura"` (`:395`), `"Grafo"` (`:404`); buscador en `:322-329`; `<DocumenterButton>` montado en `:368-376` |
| **(CORREGIDO v2) NO existe `frontend/src/docs/__tests__/`** | El directorio **no existe**. Los tests del modelo son hermanos del módulo: `frontend/src/docs/documenterModel.test.ts` (**20 tests, verde**, medido). Ver C6. |

### 3.5 Lo que el 284 SÍ dejó portante (no tocar — **verificado abriendo cada archivo**)

- **La nota extra del operador llega al modelo.** Cadena completa **confirmada**: `DocumenterButton.tsx:28` (`const [note, setNote] = useState("")`) → `:115` (`<textarea value={note}`) → `:64` (`Docs.documenterRun(projectName, normalizeOperatorNote(note))`) → `endpoints.ts:3688-3698` (campo `operator_note`) → `api/docs.py:312-319` (lectura + validación + truncado) → `:322-323` (`start_documenter_run`) → `doc_documenter.py:1036` → `:1229` → `:1363` `build_context_for_mode` → `:341-344` `blocks.insert(0, note_block)` → `_operator_note_block` (`:280-304`) → `invoke_documenter` (`:408`). **Y también llega a las etapas de papel** por `_run_paper_stage:802-804`. Test centinela: `test_documenter_v2_pipeline.py:516` (`assert "CENTINELA_CABLE_284" in render_blocks(...)`). **Nada que hacer.**
- **El orden verificar→escribir del gate de citas** (`doc_documenter.py:914-937`). Correcto.
- **`invoke_documenter` YA acepta `system_prompt_override`** (`doc_documenter.py:408`, kwarg). Es la F5.0 que agregó la crítica del 284. **No hace falta abrirlo de nuevo.**
- **`_run_paper_stage` existe** en `doc_documenter.py:792` (la v1 decía 793: es la segunda línea de la firma).
- **La regla de clasificación estricta** (`doc_taxonomy.py:28-30`). Correcta; evita los 17 falsos.
- **`services/` no importa de `api/`**: `grep -n "from api\|import api" backend/services/doc_*.py` → **0**.
- **El pipeline de 5 etapas con HITL** existe y su `AUTOAPPLY` está correctamente OFF (categoría B).
- **`docs/rag/rag_corpus.jsonl` existe (169.544 bytes) pero es un sidecar MUERTO**: 0 referencias en `backend/**` y `frontend/src/**`. El corpus vivo es `docs_index`. **No planificar contra el sidecar.**

---

## 4. Principios y guardarraíles (obligatorios en cada fase)

1. **Paridad en 3 runtimes:** Codex CLI, Claude Code CLI, GitHub Copilot Pro. Todo este plan vive en `services/`, `api/` y el frontend, aguas arriba de la bifurcación por runtime. Los bloques nuevos comunican **por `title` + `content`** porque el renderizador CLI (`context_enrichment._render_blocks:1433`) **ignora `kind`**.
2. **Human-in-the-loop innegociable.** Nada escribe en un sistema del operador sin confirmación. La única operación destructiva (purga del corpus fantasma, F1.3) nace OFF, hace backup, y exige confirmación con conteo exacto.
3. **Mono-operador, sin auth.** Ningún RBAC. Un `403` significa flag apagada, nunca permiso.
4. **`services/` NUNCA importa de `api/`.** Verificable: `grep -n "from api\|import api" backend/services/doc_*.py` → debe seguir dando **0**.
5. **Cero trabajo extra para el operador.** Todo default ON salvo la purga (categoría B, justificada por escrito en F1.3).
6. **Sobre conteos que cambian solos (planes, documentos, tests ajenos): usar siempre `>=`, nunca `==`, y NUNCA hardcodear el número en la UI.** La v1 se equivocó por 1 en el censo de docs porque se contó antes de existir.
7. **Backward-compatible.** Todo parámetro nuevo tiene default que reproduce el comportamiento de hoy.
8. **(NUEVO v2) Todo gate se prueba por ALCANZABILIDAD, no por orden de líneas.** Un test que compara números de línea pasa igual si el código es inalcanzable. Ver F5 y §4.3.

### 4.1 Las **8 patas** de una flag nueva (checklist obligatorio — el implementador las hace TODAS)

> **Corrección crítica de la v1:** la v1 decía "7 patas" y afirmaba que *"no hay que tocar ningún mapa congelado"*. **Es falso y pone rojo un test registrado en los dos ratchets.** Son **8**.

Verificado contra el molde real (`harness_flags.py:2848-2862` para bool, `:2864-2878` para numérica):

1. `backend/services/harness_flags.py` → `FlagSpec(key=..., default=True, type="bool", label=..., description=..., group="global", env_only=False, requires="STACKY_DOCS_DOCUMENTER_ENABLED")`.
2. `backend/config.py` → `os.getenv("<KEY>", "true").strip().lower() in ("1","true","yes","on")`. **El default efectivo es éste, no el del `FlagSpec`.** Una flag `env_only=True` sin entrada acá queda **INERTE**.
3. `backend/tests/test_harness_flags.py` → agregar la key al set `_CURATED_DEFAULTS_ON` (arranca en `:467`, hoy **12 keys**). El assert de `:1151` es **por IGUALDAD en los dos sentidos** (`known_keys == _CURATED_DEFAULTS_ON`): sobra o falta y se pone rojo.
4. **Sólo las booleanas `default=True` entran a `_CURATED_DEFAULTS_ON`.** Las numéricas **NO declaran `default=`** en el `FlagSpec` (si lo declaran, `default_is_known` las mete en `known_keys` y rompe el assert de `:1151`). Sí llevan `min_value`/`max_value`.
5. **`backend/tests/test_harness_flags_requires.py:120` → agregar la key nueva a `_REQUIRES_MAP_FROZEN`.** El guardián es `test_requires_map_is_frozen` (`:364-372`): `actual = {s.key: s.requires for s in FLAG_REGISTRY if s.requires}` comparado **por igualdad** contra un mapa de **165 keys**. El mapa está indexado **por key de flag**, no por el valor de `requires`: **reusar un `requires` que ya existe NO exime de agregar la key nueva.** El archivo está registrado en `run_harness_tests.ps1:351` y `run_harness_tests.sh:402`. Y ojo: `tests/test_fitness_flags.py:69` y `tests/test_knowledge_flags.py:93` **también** importan ese mapa.
6. **[CORREGIDO AL IMPLEMENTAR — la v2 se equivocaba]** La categoría **NO se deriva del prefijo**. `_CATEGORY_KEYS` (`harness_flags.py:120`) es un mapa **explícito** y hay que declarar cada key a mano: las booleanas en `"capacidades_optin"` (`:460`) y las numéricas en el grupo de knobs (`:149-157`). **Medido:** con las 9 flags registradas y sin declararlas acá, `test_every_registry_flag_is_categorized` da **`1 failed, 58 passed`**; declarándolas, **`59 passed`**.
7. `backend/services/harness_flags_help.py` → una entrada `PlainHelp(what=..., on_effect=..., off_effect=..., example=...)` en lenguaje llano (molde real en `:434-440`). **Sin jerga**: la denylist de `test_harness_flags_help.py` ya está roja de fábrica; no la empeores.
8. **Un consumidor real de producción** (no sólo un test) + `deployment/harness_defaults.env` regenerado **con el generador del repo, no a mano**.

### 4.2 Las **8** flags de este plan (la v1 decía 7: se contó mal)

| # | Flag | Fase | Tipo | Default | ¿`_CURATED_DEFAULTS_ON`? |
|---|---|---|---|---|---|
| 1 | `STACKY_DOCS_CORPUS_AUTOINDEX_ENABLED` | F1.1 | bool | **ON** | **SÍ** |
| 2 | `STACKY_DOCS_CORPUS_RETRIEVAL_ENABLED` | **F1.4 (nueva)** | bool | **ON** | **SÍ** |
| 3 | `STACKY_DOCS_CORPUS_ORPHANS_ENABLED` | F1.3 | bool | **ON** | **SÍ** |
| 4 | `STACKY_DOCS_CORPUS_PURGE_ENABLED` | F1.3 | bool | **OFF** (categoría B) | **NO** |
| 5 | `STACKY_DOCS_RIGOR_PER_CLAIM_ENABLED` | F2 | bool | **ON** | **SÍ** |
| 6 | `STACKY_DOCS_RIGOR_MIN_DENSITY` | F2 | float | 0.5 | **NO** (numérica, sin `default=`) |
| 7 | `STACKY_DOCS_RIGOR_MIN_CITATIONS` | F2 | int | 1 | **NO** (numérica, sin `default=`) |
| 8 | `STACKY_DOCS_TICKET_TRIAGE_VISIBLE_ENABLED` | F3 | bool | **ON** | **SÍ** |
| 9 | `STACKY_DOCS_TREE_GROUP_BY_CLASS_ENABLED` | F4 | bool | **ON** | **SÍ** |

**Total: 9 flags** (F1.4 agrega una). **6 booleanas ON** → 6 entradas nuevas exactas en `_CURATED_DEFAULTS_ON` (12 → **18**). **1 booleana OFF.** **2 numéricas.** **Las 9 van a `_REQUIRES_MAP_FROZEN`.**

### 4.3 Cómo correr los tests (comando exacto) y por qué **uno por archivo**

```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./.venv/Scripts/python.exe -m pytest tests/<UN_SOLO_ARCHIVO>.py -q --no-header -p no:cacheprovider
```

- El intérprete es **`backend/.venv`** (py3.13.5). **No usar `backend/venv`** (py3.11.9, sin dependencias).
- **UNA invocación POR ARCHIVO. Sin excepciones.** **Medido hoy:** los tres archivos por separado dan `25` + `38` + `16` = **79 verdes**; los tres **juntos en una invocación** dan **`1 failed, 78 passed`** — falla `tests/test_docs_api.py::TestPlan284StageApprove::test_plan284_approve_404_con_stages_off` por contaminación de orden. La v1 se contradecía: pedía "por archivo" y después daba un comando de 3 archivos como criterio de aceptación con `0 failed`. **Ese criterio era insatisfacible.**
- `pytest tests` entero **no es un veredicto** (miles de errores de contaminación).
- **`pytest -k` sin match da exit 0.** Nunca uses `-k` como criterio de aceptación sin verificar que el subconjunto no está vacío.
- **Los tres archivos de test del Documentador ya están registrados en los DOS ratchets** — **verificado grepeando**: `run_harness_tests.ps1:367` (`test_doc_evidence.py`), `:369` (`test_docs_api.py`), `:371` (`test_documenter_v2_pipeline.py`); `run_harness_tests.sh:418`, `:420`, `:422`. **Si los tests nuevos van dentro de esos tres archivos, no hay que tocar ningún ratchet.** Es la ruta obligatoria de este plan. **No crear archivos de test nuevos en backend.**
- **Un pytest suelto puede escribir en la base real.** Todo test que toque `docs_index` o `tickets` usa base en memoria o `tmp_path`; nunca `backend/data/stacky_agents.db`. (Este plan existe en parte *por* esa contaminación.)

**Frontend — rutas REALES (la v1 las tenía mal):**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend"
npx vitest run src/docs/documenterModel.test.ts    # existe hoy: 20 tests verdes
npx vitest run src/docs/docTreeModel.test.ts       # nuevo, hermano del modulo
```
- **NO existe `src/docs/__tests__/`.** Un `vitest run` contra una ruta inexistente imprime *"No test files found"* y sale con **código 1** — pero **si lo pipeás (`| tail`) el exit code se pierde y lo leés como éxito**. **Prohibido pipear el comando de aceptación.** Leer la línea `Tests N passed`.
- Correr vitest **por archivo** (hay contaminación por orden conocida). Un `.test.tsx` con RTL reporta **"no tests" con exit 0**: por eso **toda** la lógica de UI va en `.ts` puro.

### 4.4 Rojos de fábrica — **medidos hoy, son TRES archivos**

| Archivo | Estado HOY (medido) | ¿De este plan? |
|---|---|---|
| `tests/test_harness_flags_help.py` | **4 failed, 4 passed** | No — deuda ajena |
| `tests/test_error_fingerprints_catalog.py` | **3 failed, 5 passed** | No — deuda ajena |
| **`tests/test_harness_flags_requires.py`** | **1 failed, 8 passed** | **Deuda directa del 284** — este plan la **SALDA** (F0.1) |
| **`tests/test_harness_ratchet_meta.py`** | **1 failed, 3 passed** | **[AGREGADO AL IMPLEMENTAR — la v2 no lo vio]** Deuda del 284 también; **SALDADO** |

El criterio para los dos primeros es **delta**: igual o menos fallos, nunca más. El tercero **pasa a verde** en F0.1.

> **CORRECCIÓN v2 → implementación: son CUATRO, no tres.** El DoD de §10 exigía `test_harness_ratchet_meta.py` con **0 failed** y **hoy daba `1 failed`**: `test_allowlist_no_se_solapa_con_ratchet` fallaba porque el plan 284 registró `tests/test_docs_api.py` en el ratchet (`run_harness_tests.ps1:369`, `.sh:420`) y lo **dejó también** en `tests/harness_ratchet_allowlist.txt:71`, o sea declarado a la vez *vigilado* y *deliberadamente fuera*. Es exactamente la misma forma que C3 y el mismo origen (commit `3b233376`). Se saldó sacándolo de la allowlist: estar en el ratchet es estrictamente mejor que estar exento. Queda en **`4 passed`**.
> **La lección se repite:** la v2 midió los rojos de las suites que *pensaba tocar*, pero su propio DoD nombraba una cuarta suite cuyo estado nunca midió. Un DoD que nombra un comando obliga a medir ese comando.

---

## 5. Fases

> **Orden innegociable (dependencias reales, no preferencias):**
> **F0.1 → F0 → F1.0 → F1.1 → F1.4 → F1.2 → F1.3 → F2 → F3 → F4 → F5.**
> Los tres cruces que **no se pueden invertir**:
> - **F0.1 antes que cualquier flag**, o el primer `FlagSpec` nuevo deja rojo un test ya rojo y se pierde la señal de qué lo rompió.
> - **F1.1 antes que F1.4**: no se puede leer un corpus que todavía nadie indexa; invertirlo da un retrieval vacío que **pasa los tests igual** (falso verde silencioso).
> - **F1.0 antes que F2.3 y F3**: si el contexto nuevo no llega a las etapas de papel, F2.3/F3 mejoran un camino que en la config default no se ejecuta, y los criterios dan verde igual.

---

### F0.1 — Saldar el rojo de fábrica del mapa `requires` (habilitador de TODO lo demás)

**Objetivo.** Dejar `tests/test_harness_flags_requires.py` en **verde** ANTES de agregar una sola flag, para que su rojo vuelva a ser una señal útil.

**Por qué primero.** El test compara por igualdad un mapa de 165 keys contra el registro vivo, y hoy le faltan **11 keys que agregó el 284**. Está registrado en los dos ratchets (`run_harness_tests.ps1:351`, `run_harness_tests.sh:402`) ⇒ **es una trampa de COMMIT**. Si agregás las 9 flags de este plan primero, el mensaje de error mezcla 11 ajenas con 9 propias y no se sabe qué rompiste.

**Paso a paso:**
1. Correr y **copiar la salida completa**:
   ```bash
   cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
   ./.venv/Scripts/python.exe -m pytest tests/test_harness_flags_requires.py::test_requires_map_is_frozen -q --no-header -p no:cacheprovider -vv
   ```
2. La sección `Extras:` lista las keys que están en el registro y faltan en el mapa. **Agregar exactamente esas** a `_REQUIRES_MAP_FROZEN` (`tests/test_harness_flags_requires.py:120`), con el valor de `requires` que el error indica.
3. **No borrar** ninguna entrada existente. Si aparece algo en `Faltantes:`, **detenerse y reportar**: significa que una flag desapareció del registro y eso no es de este plan.

**Criterio de aceptación BINARIO:**
```bash
./.venv/Scripts/python.exe -m pytest tests/test_harness_flags_requires.py -q --no-header -p no:cacheprovider
./.venv/Scripts/python.exe -m pytest tests/test_fitness_flags.py -q --no-header -p no:cacheprovider
./.venv/Scripts/python.exe -m pytest tests/test_knowledge_flags.py -q --no-header -p no:cacheprovider
```
Los tres: **`0 failed`**. Antes del paso 2, el primero da **`1 failed, 8 passed`** (ése es el rojo contra el que se corre el gate).

**Flag:** ninguna. **Impacto por runtime:** nulo. **Trabajo del operador: ninguno.**

---

### F0 — Red-team: probar los defectos antes de tocar producción

**Objetivo.** Escribir los tests que fallan HOY y que demuestran cada defecto medido, para que ninguna fase posterior pueda declararse verde sin haberlo cerrado de verdad.

**Archivos a editar (no crear archivos nuevos — usar los ya registrados en los ratchets):**
- `Stacky Agents/backend/tests/test_documenter_v2_pipeline.py` (agregar al final)
- `Stacky Agents/backend/tests/test_doc_evidence.py` (agregar al final)

**Regla dura para TODOS los tests de este plan (anti-falso-verde):**
- **Un assert de AUSENCIA pasa por accidente** (typo en la key, fixture vacío). Cada test que asserte que algo NO está debe assertar, en el MISMO test, que **su gemelo SÍ está**.
- **Nunca `assert x != {}` como criterio.** Assertar la **presencia de una key concreta**.
- **`N passed` sólo vale si N puede cambiar.**
- **`xfail(strict=False)` que pasa da `xpassed`, no falla.** Prohibido.

**Tests exactos a agregar** (nombres literales; cada uno debe FALLAR en el árbol actual):

En `test_doc_evidence.py`:

1. `test_f0_documento_sin_citas_y_una_sola_marca_es_rechazado`
   `DocProposal` con 60 líneas, exactamente **un** `[V]` en la primera, **cero** cadenas `archivo.py:NN`, `sources=[]`. Llamar `apply_proposals` con `target_root` en `tmp_path` y un `workspace_root` válido. Assertar que el archivo **NO existe en disco** *y* — **gemelo obligatorio de presencia** — que un segundo `DocProposal` bien marcado y bien citado **SÍ existe en disco** en la misma llamada. Hoy FALLA.
2. **`test_f0_rigor_rechaza_tambien_sin_workspace_root`** *(NUEVO v2 — cierra C4)*
   La misma propuesta alucinada, pero `apply_proposals(..., workspace_root=None)`. Assertar que **igual se rechaza** por densidad. Hoy FALLA, y con el diseño de la v1 **habría seguido fallando en producción mientras el test nº1 daba verde**.
3. `test_f0_densidad_de_marcas_por_afirmacion`
   `evaluate_rigor_gate` con 60 líneas y 1 marca ⇒ `passed=False`; con 10 líneas y 6 marcas ⇒ `passed=True`. Hoy FALLA (`ImportError`).
4. `test_f0_gate_conserva_el_caso_legitimo_todo_NV`
   Documento corto (≤ 8 líneas) íntegramente `[NV]` y sin citas ⇒ **sigue pasando**. Protege contra el sobre-endurecimiento.

En `test_documenter_v2_pipeline.py`:

5. `test_f0_corpus_rag_del_proyecto_activo_no_esta_vacio`
   Con base temporal, correr `ensure_corpus_indexed` (F1.1) sobre un `tmp_path` con 3 `.md` de proyecto y 2 con nombre de plan (`101_PLAN_X.md`). Assertar `chunks_indexed >= 3` **y** que ningún `file_path` indexado matchee la regla de plan **y** que los 3 de proyecto SÍ están (presencia). Hoy FALLA.
6. **`test_f0_el_corpus_llega_al_prompt`** *(NUEVO v2 — cierra C1)*
   Con el corpus temporal poblado, llamar al constructor de bloques y assertar que existe un bloque con `id == "docs-corpus"` cuyo `content` contiene el texto de uno de los `.md` indexados. Hoy FALLA: `doc_documenter.py` **no importa `docs_rag`** (0 líneas).
7. **`test_f0_las_etapas_de_papel_reciben_el_contexto_rico`** *(NUEVO v2 — cierra C2)*
   Monkeypatchear `invoke_raw_stage` para capturar sus `blocks`. Correr `run_documenter` con los defaults (etapas ON, autoapply OFF). Assertar que los `blocks` de la etapa `PROPONER` tienen **≥ 4** entradas y que entre sus `id` están `"docs-corpus"` y `"doc-subgraph"`. Hoy FALLA: son **1** (`doc_documenter.py:1287`).
8. `test_f0_ticket_mining_queda_en_el_run_record`
   Correr `run_documenter(..., autoapply_override=True)` **— el `autoapply_override=True` es OBLIGATORIO**: con los defaults el run retorna en `doc_documenter.py:1335` sin llegar nunca al loop de modos, y el test sería inejecutable. Assertar que el reporte persistido tiene `report["ticket_mining"]["noise_sample"]` no vacío, que cada entrada trae `reasons`, y que existe la key `"reason_counts"`. Hoy FALLA.
9. `test_f0_truncamiento_se_declara_en_el_prompt`
   `build_tickets_context_block({"total": 500, "total_rows": 900, "truncated": True, "verdicts": [...con al menos 1 signal...]})` ⇒ el `content` contiene `"TRUNCADO"`. **Gemelo obligatorio:** con `truncated=False` y sin corte por caracteres, el `content` contiene `"COMPLETO"`. Hoy FALLA.
10. `test_f0_subgrafo_llega_a_reconstruir_y_completar`
    `build_context_for_mode(DocumenterMode.RECONSTRUIR, plan, "X")` ⇒ existe bloque con `id == "doc-subgraph"`. Idem `COMPLETAR`. **Gemelo obligatorio:** para `NORMALIZAR` **y** para `ACTUALIZAR` **no** existe. Hoy FALLA.
11. `test_f0_fallo_del_barrido_no_es_mudo`
    Monkeypatchear `doc_ticket_mining.mine_project_tickets` para que lance; assertar que `build_context_for_mode` **igual devuelve un bloque** cuyo `title` contiene `"NO disponible"`. Hoy FALLA.

**Comando (uno por archivo):**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./.venv/Scripts/python.exe -m pytest tests/test_doc_evidence.py -q --no-header -p no:cacheprovider
./.venv/Scripts/python.exe -m pytest tests/test_documenter_v2_pipeline.py -q --no-header -p no:cacheprovider
```

**Criterio de aceptación BINARIO.** `test_doc_evidence.py` reporta **`4 failed, 25 passed`** y `test_documenter_v2_pipeline.py` reporta **`7 failed, 38 passed`**. Los 63 preexistentes siguen pasando. **Si algún test nuevo pasa en verde, está mal escrito: reescribirlo hasta que se ponga rojo contra el código de hoy.** Un gate que no se pone rojo contra el defecto no prueba nada.

**Flag:** ninguna. **Impacto por runtime:** nulo. **Trabajo del operador: ninguno.**

---

### F1 — El corpus documental deja de estar muerto **y empieza a leerse**

**Objetivo.** Que el Documentador (a) indexe la documentación real del proyecto antes de usarla, (b) **la consulte**, y (c) que el operador vea el estado del corpus en vez de adivinarlo.

**Valor.** La v1 medía bien el síntoma (corpus con cero documentos reales) pero **nunca verificó quién lee ese corpus**. Medido: `doc_documenter.py` **no importa `docs_rag`**. Indexar sin cablear la lectura sería *"construir algo y no cablearlo"* — exactamente el defecto que este plan combate. Por eso F1 ahora tiene **cuatro** sub-fases y la de lectura (F1.4) es obligatoria.

#### F1.0 — (NUEVA v2) El contexto rico llega a las etapas de papel

**Archivo a editar:** `Stacky Agents/backend/services/doc_documenter.py`

**Símbolo nuevo:** `def build_base_blocks(project_name: str) -> list[dict]`

Colocarla **inmediatamente antes** de `def run_documenter(` (hoy `:1229`).

```python
def build_base_blocks(project_name: str) -> list[dict]:
    """Plan 285 F1.0 — contexto de las ETAPAS DE PAPEL (camino DEFAULT).

    Medido 2026-08-01: con STACKY_DOCS_PIPELINE_STAGES_ENABLED=true (default)
    y STACKY_DOCS_PIPELINE_AUTOAPPLY=false (default, categoria B), run_documenter
    RETORNA en :1335 antes del loop de modos. Las 3 llamadas al LLM que el
    operador realmente lee recibian UN solo bloque (:1287). Todo el contexto
    rico del 284 quedaba del otro lado de la barrera HITL.

    Devuelve SIEMPRE una lista con al menos el bloque canonico. Nunca lanza.
    """
    blocks: list[dict] = [_sistema_readonly_block(project_name)]
    for builder in (_corpus_block, _subgraph_block, _tickets_block_safe):
        try:
            b = builder(project_name)
            if b is not None:
                blocks.append(b)
        except Exception as exc:            # nunca tumba el run
            logger.warning("doc_documenter: bloque base no disponible: %s", exc)
    return blocks
```

- `_corpus_block` es el símbolo nuevo de **F1.4**.
- `_subgraph_block` ya existe (`:219`).
- `_tickets_block_safe` es un wrapper nuevo, inmediatamente después de `_subgraph_block`, que hace lo mismo que `doc_documenter.py:330-337` pero **devolviendo** el bloque en vez de mutar una lista, y devolviendo el bloque de aviso de **F2.4** cuando el barrido falla.

**Cableado:** en `run_documenter`, reemplazar la línea `:1287`
`base_blocks = [_sistema_readonly_block(project_name)]`
por
`base_blocks = build_base_blocks(project_name)`.

**Y `build_context_for_mode` (`:307`) reusa los mismos constructores** — no se duplica lógica: la rama `RECONSTRUIR/COMPLETAR` (`:324-337`) pasa a llamar `_tickets_block_safe`.

**Criterio BINARIO:** `test_f0_las_etapas_de_papel_reciben_el_contexto_rico` pasa.

#### F1.1 — Hook de auto-indexación **antes** de las etapas de papel

**Archivo a editar:** `Stacky Agents/backend/services/doc_documenter.py`

**Símbolo nuevo:** `def ensure_corpus_indexed(project_name: str, workspace_root: str | None) -> dict`

Colocarla **inmediatamente antes** de `build_base_blocks`. **Llamarla dentro de `run_documenter` INMEDIATAMENTE DESPUÉS de `:1249`** (`target_root, docs_root, workspace_root = _resolve_target_paths(project_name)`) **y ANTES del bloque de etapas de papel (`:1283`)**.

> **Corrección crítica de la v1.** La v1 decía *"antes del loop de modos"*. El loop de modos está en `:1349`, **después del `return pending` de `:1335`** ⇒ en la configuración default **la indexación nunca se habría ejecutado en la primera pasada**. Tiene que ir arriba de todo.

```python
def ensure_corpus_indexed(project_name: str, workspace_root: str | None) -> dict:
    """Plan 285 F1.1 — Reindexa el corpus documental del proyecto antes de documentar.

    Medido 2026-08-01: docs_index tenia 51 chunks y CERO documentos reales
    (todos fixtures de test de 8 proyectos que no existen).

    Devuelve SIEMPRE un dict con las mismas keys (nunca lanza):
      {"enabled": bool, "chunks_indexed": int, "files_scanned": int,
       "skipped_plans": int, "error": str}
    """
    out = {"enabled": False, "chunks_indexed": 0, "files_scanned": 0,
           "skipped_plans": 0, "error": ""}
    try:
        from config import config as _cfg
        if not bool(getattr(_cfg, "STACKY_DOCS_CORPUS_AUTOINDEX_ENABLED", False)):
            return out
        out["enabled"] = True
        if not workspace_root:
            out["error"] = "sin_workspace_root"
            return out
        from services import docs_rag
        res = docs_rag.index_project(project_name, workspace_root, "docs")
        out["chunks_indexed"] = int(res.get("chunks_indexed", 0) or 0)
        out["files_scanned"] = int(res.get("files_scanned", 0) or 0)
        out["skipped_plans"] = int(res.get("skipped_plans", 0) or 0)
        if res.get("warning"):
            out["error"] = str(res["warning"])[:200]
    except Exception as exc:                     # nunca tumba el run
        out["error"] = str(exc)[:200]
        logger.warning("doc_documenter: auto-index del corpus fallo: %s", exc)
    return out
```

**Cambio acompañante en `docs_rag.index_project`** (`docs_rag.py:145`): el `return` final (`:205-208`, hoy `{"chunks_indexed","files_scanned"}`) agrega `"skipped_plans"` = cantidad de archivos que el filtro de `:164-169` descartó. Calcularla guardando `len(md_files)` **antes** del filtro (la línea `md_files = sorted(root.rglob("*.md"))` está en `:160`). **Aditivo: ningún llamador existente se rompe.** El `return` temprano de `:158` también agrega `"skipped_plans": 0`.

**Persistencia:** el dict se guarda en el reporte del run bajo la clave `"corpus"`, con el mismo patrón que `report["radiography"]` (`doc_documenter.py:1442-1458`).

**Exposición:** en `api/docs.py`, dentro de `documenter_status()` (`:330`), agregar junto a `:363`:
```python
        "corpus": rec.get("corpus", {}),
```

#### F1.4 — (NUEVA v2) El corpus **se lee**: bloque `docs-corpus`

**Archivo a editar:** `Stacky Agents/backend/services/doc_documenter.py`

**Símbolo nuevo:** `def _corpus_block(project_name: str) -> dict | None`, inmediatamente después de `_subgraph_block` (`:219`).

```python
_CORPUS_QUERY = ("arquitectura modulos componentes flujo datos integraciones "
                 "decisiones tecnicas del proyecto")

def _corpus_block(project_name: str) -> dict | None:
    """Plan 285 F1.4 — la documentacion YA ESCRITA del proyecto, via retrieval.

    Medido 2026-08-01: `grep -rn "docs_rag" doc_documenter.py` daba 0 lineas.
    El corpus se indexaba (1 endpoint HTTP manual) y NADIE lo leia desde el
    Documentador. Indexar sin este bloque es construir y no cablear.

    None si la flag esta OFF o si el retrieval no devuelve nada. Nunca lanza.
    """
    from config import config as _cfg
    if not bool(getattr(_cfg, "STACKY_DOCS_CORPUS_RETRIEVAL_ENABLED", False)):
        return None
    try:
        from services import docs_rag
        hits = docs_rag.search_hybrid(project_name, _CORPUS_QUERY, top_k=8) or []
    except Exception as exc:
        logger.warning("doc_documenter: retrieval del corpus fallo: %s", exc)
        return None
    if not hits:
        return None
    lineas = [f"- {h.file_path} :: {h.section_heading}" for h in hits[:8]]
    return {
        "id": "docs-corpus",
        "kind": "docs-corpus",
        "title": "DOCUMENTACION YA ESCRITA DE ESTE PROYECTO (no la dupliques)",
        "content": ("Estas notas ya existen. Ampliá o corregí, NO reescribas "
                    "desde cero ni dupliques su contenido:\n" + "\n".join(lineas)),
        "source": {"type": "corpus", "readonly": True},
    }
```

- **Nota de contrato:** `search_hybrid` (`docs_rag.py:500`) devuelve `DocHit` (`:259`) con `to_dict()` en `:265`. Si la firma real difiere, **detenerse y reportar** antes de codificar.
- **`kind` es decorativo**: el renderizador CLI (`context_enrichment._render_blocks:1433`) **sólo lee `title`, `content` e `items`**. Toda la señal va en `title` + `content`.

#### F1.2 — El operador ve el estado del corpus

**Archivos a editar:**
- `Stacky Agents/frontend/src/docs/documenterModel.ts` — función pura nueva `buildCorpusView(corpus)` ⇒ `{ visible: boolean, label: string, tone: "ok" | "warn" }`. Reglas: `corpus === undefined` ⇒ `visible:false`. `error !== ""` ⇒ `tone:"warn"` con el error. `chunks_indexed === 0` ⇒ `tone:"warn"`, `label:"Corpus vacío: el Documentador no tiene documentación del proyecto que consultar"`. Si no ⇒ `tone:"ok"`, `label:"Corpus: N documentos indexados (M planes excluidos)"` con N y M **tomados del dato**, nunca literales.
- `Stacky Agents/frontend/src/components/docs/DocumenterResultPanel.tsx` — renderizar `buildCorpusView(...)` **arriba de la línea de cobertura** (`:139`, `<div>{radiography.coverageLabel}</div>`).

**Por qué la lógica va en `documenterModel.ts` y no en el `.tsx`:** RTL/jsdom **no están instalados**. Un `.test.tsx` con RTL reporta "no tests" y **exit 0** (falso verde).

**Test:** en `Stacky Agents/frontend/src/docs/documenterModel.test.ts` (**archivo existente, 20 tests verdes hoy — la ruta `__tests__/` de la v1 NO EXISTE**). Casos: corpus vacío, corpus con error, corpus sano, corpus `undefined`.
**Comando:** `cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend" && npx vitest run src/docs/documenterModel.test.ts` — **sin pipe**; leer `Tests N passed` con **N ≥ 24**.

#### F1.3 — Purga del corpus fantasma (la única operación destructiva)

**Archivos:**
- `Stacky Agents/backend/services/docs_rag.py` — tres funciones nuevas:
  - `def list_orphan_corpus_projects() -> list[dict]` — **solo lectura**. Por cada `project_name` distinto en `docs_index` que **no** exista en la configuración de proyectos de Stacky (vía `project_manager.get_all_projects`), devuelve `{"project_name", "chunks", "files", "indexed_at"}`. Hoy debe devolver los 8: `C1`(41), `D1`(2), `K1`(2), `M1`(2), `N1`(1), `PF1`(1), `PF2`(1), `ST1`(1).
  - **`def backup_corpus_projects(project_names: list[str], dest_dir: str) -> str`** *(NUEVO v2)* — vuelca a un `.jsonl` en `backend/data/backups/` **todas** las filas de esos proyectos antes de borrar. Devuelve la ruta. `docs_index` es una tabla **derivada**: el backup la hace reversible.
  - `def purge_orphan_corpus_projects(project_names: list[str], *, expected_rows: int) -> dict` — **destructiva**. Borra de `docs_index` sólo los `project_name` pasados **explícitamente por parámetro**. **Guardas duras, cada una con test:** (a) **nunca** borra un proyecto que exista en la configuración, aunque venga en la lista; (b) si el conteo real de filas a borrar **no coincide** con `expected_rows`, **no borra nada** y devuelve `{"ok": False, "reason": "row_count_mismatch", ...}` (anti-race: entre que el operador miró la lista y confirmó, algo pudo cambiar); (c) llama a `backup_corpus_projects` **antes** de cualquier `DELETE` y devuelve la ruta del backup.
- `Stacky Agents/backend/api/docs_rag.py` — `@bp.get("/corpus/orphans")` (gateado por `STACKY_DOCS_CORPUS_ORPHANS_ENABLED`, ON) y `@bp.post("/corpus/purge")` (gateado por `STACKY_DOCS_CORPUS_PURGE_ENABLED`, OFF; devuelve `403` con `{"error":"flag_disabled"}` si está apagada — **en Stacky un `403` significa flag apagada, nunca permiso**). El body de `/corpus/purge` **exige** `{"project_names": [...], "expected_rows": N}`; falta cualquiera ⇒ `400`.
- Frontend: botón "Limpiar corpus huérfano" en el panel de docs que **primero lista** los huérfanos con sus conteos y **exige confirmación explícita** nombrando cuántas filas se borran y dónde quedó el backup.

**Flags de F1:**

| Flag | Tipo | Default | Justificación |
|---|---|---|---|
| `STACKY_DOCS_CORPUS_AUTOINDEX_ENABLED` | bool | **ON** | Lee `.md` locales y escribe en una tabla derivada **propia de Stacky** (`docs_index`), sólo cuando el operador lanza el Documentador. **No es (A)**: no hay loop, daemon ni polling, y no llama a ningún modelo (TF-IDF puro, `docs_rag.py:145-208`). **No es (B)**: no toca ningún sistema del operador. Va ON. |
| `STACKY_DOCS_CORPUS_RETRIEVAL_ENABLED` | bool | **ON** | Lectura pura + armado de un bloque de contexto local, sin llamada extra a ningún modelo (el bloque viaja en el prompt que ya se iba a mandar). **No es (A)**: no engorda el prompt "en reposo", sólo cuando el operador dispara el Documentador. **No es (B)**. Va ON. |
| `STACKY_DOCS_CORPUS_ORPHANS_ENABLED` | bool | **ON** | Sólo lista y muestra. Lectura pura ⇒ nunca es excepción. Va ON. |
| `STACKY_DOCS_CORPUS_PURGE_ENABLED` | bool | **OFF** | **Excepción (B): destruye datos.** Borra filas de `docs_index` de forma irreversible sin el backup; el re-index sólo regenera proyectos que existen, así que un huérfano borrado **no vuelve** (`docs_rag.py:199` purga por `project_name`; nada re-crea `C1`). Nace OFF, hace backup, valida el conteo y exige confirmación en UI. |

**Criterio de aceptación BINARIO de F1:**
1. `test_f0_corpus_rag_del_proyecto_activo_no_esta_vacio` pasa.
2. **`test_f0_el_corpus_llega_al_prompt` pasa** (sin esto, F1 no vale nada).
3. **`test_f0_las_etapas_de_papel_reciben_el_contexto_rico` pasa.**
4. `test_f1_purga_nunca_borra_un_proyecto_configurado` pasa (pasarle un `project_name` real y verificar que las filas siguen ahí). **Gemelo:** en la misma llamada, un huérfano de la lista **sí** se borra.
5. `test_f1_purga_aborta_si_el_conteo_no_coincide` pasa.
6. `test_f1_purga_deja_backup_leible` pasa (el `.jsonl` existe y tiene tantas líneas como filas borradas).
7. `test_f1_index_project_reporta_skipped_plans` pasa: con 3 docs y 2 planes en `tmp_path`, `res["skipped_plans"] == 2` **y** `res["files_scanned"] == 3`.
8. `POST /api/docs-rag/corpus/purge` con la flag OFF devuelve **403**; con la flag ON y sin `expected_rows` devuelve **400**.
9. Los tres archivos backend, **uno por invocación**: `test_doc_evidence.py` **`>= 29 passed, 0 failed`**, `test_documenter_v2_pipeline.py` **`>= 45 passed, 0 failed`**, `test_docs_api.py` **`>= 16 passed, 0 failed`**.

**Impacto por runtime.** Codex / Claude Code / Copilot: **idéntico**. El indexado y el retrieval ocurren en `services/`, antes de `agent_runner.run_agent`, aguas arriba de cualquier bifurcación. **Fallback común:** si `workspace_root` no está configurado, si `docs/` no existe o si el retrieval no devuelve hits, `ensure_corpus_indexed` devuelve `{"error": ...}`, `_corpus_block` devuelve `None`, el run continúa normalmente y el panel muestra el aviso. **Nunca rompe.**

**Trabajo del operador: ninguno** para F1.0/F1.1/F1.4/F1.2. F1.3 es opt-in con default OFF por categoría (B); su parte de sólo lectura está ON.

---

### F2 — Rigor por afirmación: pisar firme deja de ser una exhortación

**Objetivo.** Convertir "ir lento y pisando firme, sin alucinar" en un gate mecánico que mida **densidad de marcas** y **presencia mínima de citas**, en vez de aceptar una marca suelta y cero citas.

**Archivos a editar:** `backend/services/doc_documenter.py`; y para las 3 flags: `backend/services/harness_flags.py`, `backend/config.py`, `backend/services/harness_flags_help.py`, `backend/tests/test_harness_flags.py`, **`backend/tests/test_harness_flags_requires.py`**, `deployment/harness_defaults.env`.

#### F2.1 — Función nueva `evaluate_rigor_gate`

Colocarla **inmediatamente después** de `evaluate_citation_gate` (`:843-874`), **copiando su idioma exacto**.

> **Corrección de la v1 (C10).** La v1 la declaraba "PURA, sin I/O" y a la vez le daba `min_density: float | None = None` con "Defaults: 0.5". Si el `None` se resolvía a un literal, las flags `STACKY_DOCS_RIGOR_MIN_DENSITY` y `..._MIN_CITATIONS` quedaban **registradas y muertas** ⇒ violaban el DoD y el ratchet F5 nº5. **El idioma del repo ya lo resuelve:** `evaluate_citation_gate` importa config **dentro del `try`** (`:859-862`). "Pura" en este repo significa *sin filesystem, sin red, nunca lanza* — **leer config está permitido y es obligatorio acá.**

```python
def evaluate_rigor_gate(body: str, citations: dict | None, *,
                        min_density: float | None = None,
                        min_citations: int | None = None,
                        trivial_lines: int = 8) -> dict:
    """Plan 285 F2 — rigor POR AFIRMACION. Sin filesystem, sin red. Nunca lanza.

    Lee sus umbrales de config cuando llegan en None (mismo idioma que
    evaluate_citation_gate:859-862). NO consulta la flag maestra: eso lo hace
    el llamador (_rigor_gate_enabled).

    Definiciones EXACTAS:
      - "afirmacion" = linea no vacia que no sea encabezado markdown (no empieza
        con '#'), no sea separador ('---', '===') y no sea delimitador de bloque
        de codigo ('```'). Las lineas DENTRO de un bloque de codigo NO cuentan.
      - densidad = (afirmaciones con al menos una de _MARKS) / afirmaciones totales
      - documento trivial = afirmaciones totales <= trivial_lines.

    Salida: {"passed": bool, "density": float, "claims": int, "marked": int,
             "citations_ok": int, "reason": str}
    Razones: "" | "rigor_density_below:{marked}/{claims}" | "rigor_no_citations"
    """
```

**Reglas de decisión (en este orden, sin ambigüedad):**
1. Resolver umbrales: si `min_density is None` ⇒ `float(getattr(_cfg, "STACKY_DOCS_RIGOR_MIN_DENSITY", 0.5))`; si `min_citations is None` ⇒ `int(getattr(_cfg, "STACKY_DOCS_RIGOR_MIN_CITATIONS", 1))`.
2. `claims <= trivial_lines` ⇒ `passed=True`, `reason=""`. **Caso legítimo protegido.**
3. `density < min_density` ⇒ `passed=False`, `reason=f"rigor_density_below:{marked}/{claims}"`. **La comparación es `<`, así que justo en el umbral PASA.**
4. **`citations is None` ⇒ el sub-chequeo de citas se OMITE** (no hay con qué evaluarlo) y se sigue a la regla 6. **Nunca rechaza por citas cuando no las pudo contar.**
5. `int(citations.get("ok", 0)) < min_citations` ⇒ `passed=False`, `reason="rigor_no_citations"`.
6. En cualquier otro caso ⇒ `passed=True`.
7. Ante cualquier excepción ⇒ `{"passed": True, "density": 1.0, "claims": 0, "marked": 0, "citations_ok": 0, "reason": ""}` (degradar sin bloquear, igual que `:872-874`).

**Defaults efectivos:** `min_density = 0.5`, `min_citations = 1`, `trivial_lines = 8`.

#### F2.2 — Cablear el gate en `apply_proposals` — **alcanzable en las 4 combinaciones**

> **Corrección BLOQUEANTE de la v1 (C4).** La v1 escribía `if _rigor_gate_enabled() and citations is not None:`. Medido: `citations` sólo deja de ser `None` dentro de `if workspace_root is not None:` (`:918-922`), y `run_documenter` pasa `workspace_root=(... if (_v2_enabled() or _citation_gate_enabled()) else None)` (`:1391`). Con V2 OFF y gate de citas OFF, **el gate de rigor de la v1 nacía inerte y nadie se enteraba** — mientras el test de F0 (escrito con `workspace_root` válido) daba verde. **Falso verde de manual.** La densidad de marcas **no necesita citas para calcularse.**

En `apply_proposals` (`:882`), **inmediatamente después** del bloque del gate de citas (que cierra en `:932` con `continue`, línea `:933` es el comentario de cierre) y **antes** del `try:` de escritura (`:934`), al nivel de indentación del `for` (8 espacios):

```python
        # ---- Plan 285 F2: GATE DE RIGOR POR AFIRMACION ----
        # NO se cuelga de `citations`: la densidad de marcas se calcula sobre el
        # cuerpo y es independiente del workspace_root. Colgarlo de
        # `citations is not None` lo dejaba muerto con V2 OFF + citas OFF.
        if _rigor_gate_enabled():
            rigor = evaluate_rigor_gate(prop.content, citations)
            if not rigor["passed"]:
                result.skipped.append((prop.path, rigor["reason"]))
                result.files.append({
                    "path": norm, "action": prop.action, "citations": citations or {},
                    "rigor": rigor,
                    "content_preview": prop.content[:_PREVIEW_MAX_CHARS],
                    "rejected": True, "reject_reason": rigor["reason"],
                })
                continue
        # ---------------------------------------------------
```

**Y en `run_documenter:1391`, extender la resolución de `workspace_root`:**
```python
        workspace_root=(workspace_root
                        if (_v2_enabled() or _citation_gate_enabled() or _rigor_gate_enabled())
                        else None),
```
Sin este cambio el sub-chequeo de citas del gate de rigor nunca se evalúa con V2 y citas apagadas. (La densidad sí funciona igual, por el diseño de arriba.)

**Helper nuevo** junto a `_citation_gate_enabled` (`:877`):
```python
def _rigor_gate_enabled() -> bool:
    from config import config as _cfg
    return bool(getattr(_cfg, "STACKY_DOCS_RIGOR_PER_CLAIM_ENABLED", False))
```

**Importante — no tocar `:190`.** `marks_ok = any(...)` se **conserva**: es el filtro barato de primer nivel (cero marcas ⇒ descarte en `:911`). El gate nuevo es el segundo nivel. Cambiar `:190` rompería `test_documenter_v2_pipeline.py` sin ganar nada.

**Importante — no tocar `:865`.** `evaluate_citation_gate` sigue devolviendo `passed=True` con `total==0`: es correcto para su semántica ("el que miente es el que cita mal, no el que no cita"). El requisito de citas mínimas lo impone `evaluate_rigor_gate`, que **sí** distingue trivial de largo.

#### F2.3 — El subgrafo llega a los modos que documentan de cero

En `build_context_for_mode` (`:307`): sacar `blocks.append(_subgraph_block(project_name))` de la rama exclusiva de `ENRIQUECER` (`:338-339`) y ponerlo **una sola vez**, inmediatamente antes de `blocks.append(_sistema_readonly_block(project_name))` (`:344`), gateado por:
```python
    if mode in (DocumenterMode.RECONSTRUIR, DocumenterMode.COMPLETAR,
                DocumenterMode.ENRIQUECER):
        blocks.append(_subgraph_block(project_name))
```
**`NORMALIZAR` y `ACTUALIZAR` quedan explícitamente afuera**, y el ratchet F5 nº4 congela **los dos** lados. (La v1 hablaba de "1 de 4" y "3 de 4": **hay CINCO modos** — `doc_documenter.py:56-61` — y su propio glosario los listaba bien. Corregido a **1 de 5 → 3 de 5**.)

#### F2.4 — El fallo del barrido de tickets deja de ser mudo

En el `except` de `doc_documenter.py:330-337` (ahora dentro de `_tickets_block_safe`, F1.0), además del `logger.warning`, **devolver** un bloque:
```python
        except Exception as exc:
            logger.warning("doc_documenter: mineria de tickets fallo: %s", exc)
            return {
                "id": "tickets-unavailable", "kind": "warning",
                "title": "Historia de tickets NO disponible",
                "content": ("El barrido de tickets fallo en este run. NO afirmes "
                            "nada sobre la historia del proyecto derivada de "
                            "tickets: marcalo [NV]."),
            }
```
Recordar: el renderizador CLI **ignora `kind`** (`context_enrichment.py:1433-1455`); toda la señal está en `title` + `content`. **Correcto por construcción.**

**Flags de F2:**

| Flag | Tipo | Default | Justificación |
|---|---|---|---|
| `STACKY_DOCS_RIGOR_PER_CLAIM_ENABLED` | bool | **ON** | Endurece un gate de calidad sobre un artefacto que Stacky genera en su propia rama git revertible. No es (A) ni (B). Va ON. |
| `STACKY_DOCS_RIGOR_MIN_DENSITY` | float | **0.5** | `min_value=0.0`, `max_value=1.0`. **Sin `default=` en el `FlagSpec`** (numérica). Consumidor: `evaluate_rigor_gate` regla 1. |
| `STACKY_DOCS_RIGOR_MIN_CITATIONS` | int | **1** | `min_value=0`, `max_value=50`. **Sin `default=` en el `FlagSpec`** (numérica). Consumidor: `evaluate_rigor_gate` regla 1. |

**Tests (TDD, primero) — en `test_doc_evidence.py`:**
- `test_f2_rigor_documento_trivial_pasa` — 5 líneas, 0 marcas, 0 citas ⇒ `passed=True`.
- `test_f2_rigor_densidad_justo_en_el_umbral` — 10 afirmaciones, 5 marcadas, `min_density=0.5` ⇒ `passed=True` (la comparación es `<`).
- `test_f2_rigor_densidad_un_pelo_abajo` — 10 afirmaciones, 4 marcadas ⇒ `passed=False`, `reason` empieza con `"rigor_density_below:"`.
- `test_f2_rigor_lineas_de_codigo_no_cuentan_como_afirmacion` — 3 afirmaciones marcadas + 40 líneas dentro de un bloque de código ⇒ `passed=True`.
- `test_f2_rigor_encabezados_no_cuentan` — idem con 20 líneas `##`.
- `test_f2_rigor_degrada_ante_basura` — pasarle `None` y `{}` ⇒ `passed=True`, no lanza.
- **`test_f2_rigor_lee_los_umbrales_de_config`** *(NUEVO v2 — prueba que las 2 numéricas son PORTANTES)* — monkeypatchear `config.STACKY_DOCS_RIGOR_MIN_DENSITY` a `0.9`; el mismo documento que pasaba con `0.5` ahora **falla**. Idem con `MIN_CITATIONS`. **Sin este test las 2 flags numéricas son decorativas.**
- **`test_f2_rigor_alcanzable_en_las_4_combinaciones`** *(NUEVO v2 — cierra C4)* — matriz `V2 ∈ {on,off} × CITATION_GATE ∈ {on,off}`: en las **4**, el documento alucinado se rechaza. **Gemelo:** en las 4, el documento bien marcado y bien citado **se escribe**.
- `test_f2_gate_apagado_no_rechaza_nada` — con `STACKY_DOCS_RIGOR_PER_CLAIM_ENABLED=false`, el documento de `test_f0_documento_sin_citas_y_una_sola_marca_es_rechazado` **sí** se escribe. **Prueba que la flag es portante, no decorativa.**

**Criterio de aceptación BINARIO de F2:**
1. Pasan `test_f0_documento_sin_citas_y_una_sola_marca_es_rechazado`, **`test_f0_rigor_rechaza_tambien_sin_workspace_root`**, `test_f0_gate_conserva_el_caso_legitimo_todo_NV`, `test_f0_subgrafo_llega_a_reconstruir_y_completar`, `test_f0_fallo_del_barrido_no_es_mudo`.
2. Pasan los 9 tests `test_f2_*`.
3. El registro de flags sigue verde, **uno por archivo**:
   - `tests/test_harness_flags.py` ⇒ **`>= 59 passed, 0 failed`** (**59 es el valor MEDIDO hoy** — la v1 decía 56 y un `>= 56` no habría detectado la pérdida de hasta 3 tests). Además, **grepear las keys propias**: un conteo global no discrimina si contaminaste.
   - `tests/test_harness_flags_requires.py` ⇒ **`0 failed`** (saldado en F0.1; las 9 keys nuevas ya agregadas).
   - `tests/test_fitness_flags.py` y `tests/test_knowledge_flags.py` ⇒ **`0 failed`**.
4. **Delta de rojos de fábrica**: `test_harness_flags_help.py` **≤ 4 failed**; `test_error_fingerprints_catalog.py` **≤ 3 failed**.

**Impacto por runtime.** Idéntico en los 3: `evaluate_rigor_gate` y `apply_proposals` corren en el backend, **después** de que cualquiera de los tres runtimes devolvió su texto. **Fallback:** con la flag OFF el comportamiento es el de hoy, bit a bit.

**Trabajo del operador: ninguno** (default ON, invisible). Los dos knobs numéricos quedan editables desde el panel de flags, que lee el registry dinámicamente — no hay que tocar el frontend.

---

### F3 — El descarte de tickets se vuelve trazable

**Objetivo.** Que el operador vea **qué tickets se descartaron y por qué**, y que el modelo nunca reciba una afirmación de cobertura que sea falsa.

**Archivos a editar:** `backend/services/doc_ticket_mining.py`, `backend/services/doc_documenter.py`, `backend/api/docs.py`, `frontend/src/docs/documenterModel.ts`, `frontend/src/components/docs/DocumenterResultPanel.tsx`.

#### F3.1 — Fin del truncamiento silencioso — **son DOS ejes, no uno**

> **Corrección de la v1 (C9).** La v1 sólo vio el cap SQL y proponía escribir *"barrido COMPLETO"*. **Hay un segundo truncamiento**, por caracteres, dentro del propio bloque (`doc_ticket_mining.py:228-235`, `max_chars=12000`). Declarar "COMPLETO" mientras el cuerpo se cortó por caracteres **cambia una afirmación falsa por otra más enfática.** Además `total` (`:236`) cuenta signal+noise, y el cuerpo lista **sólo signal**.

En `build_tickets_context_block` (`:210`):
- Leer `mining.get("truncated", False)` y `mining.get("total_rows")` junto a `:236-237`.
- El texto de `:243` pasa a declarar **los dos ejes y la asimetría signal/total**:
  - **completo** (`not truncated_sql and not truncado_chars`):
    `f"Se barrieron los {total} tickets del proyecto (barrido COMPLETO). {len(signal)} aportan historia documentable y {ruido} se descartaron. Abajo se listan los {len(lineas)} 'signal'."`
  - **truncado por SQL**: agrega
    `f" ATENCION: barrido TRUNCADO — se leyeron {total} de {total_rows} tickets, faltan {total_rows - total}. NO afirmes cobertura total de la historia del proyecto."`
  - **truncado por caracteres**: agrega
    `f" ATENCION: la lista de abajo se corto por tamano: se muestran {len(lineas)} de {len(signal)} tickets 'signal'."`
  - Los dos avisos pueden aparecer juntos. La palabra `"TRUNCADO"` debe estar presente si **cualquiera** de los dos disparó, y `"COMPLETO"` **sólo** si ninguno.
- Agregar `"total_rows": total_rows` al dict de `mine_project_tickets` (`:201-204`): hoy `total_rows` se calcula en `:190`, se usa sólo para el booleano de `:204` y se descarta.

#### F3.2 — El triage se persiste y se expone

En `doc_ticket_mining.py`, función nueva:
```python
def build_triage_report(mining: dict, *, max_noise: int = 50) -> dict:
    """Plan 285 F3 — resumen AUDITABLE del triage, para el operador.

    Devuelve SIEMPRE las mismas keys:
      {"total": int, "total_rows": int, "truncated": bool,
       "signal": int, "noise": int, "by_tracker": dict,
       "noise_sample": [{"external_id","tracker_type","title","score","reasons"}],
       "reason_counts": {"<motivo>": int}}

    `mining["verdicts"]` son dataclasses TicketVerdict (doc_ticket_mining.py:71),
    NO dicts: leer con getattr.
    noise_sample lleva los peores primero (score ascendente) hasta max_noise.
    reason_counts cuenta cuantas veces disparo cada motivo sobre TODO el barrido,
    no solo sobre la muestra. Nunca lanza: ante basura devuelve la forma vacia.
    """
```

En `doc_documenter.py`, dentro de `_tickets_block_safe` (F1.0), después de calcular `mining`, calcular también `triage = doc_ticket_mining.build_triage_report(mining)`.

**Cómo llega al run record sin romper firmas (obligatorio):** `build_context_for_mode` (`:307`) es un constructor de contexto y **no** debe escribir en el run record. Agregar una función hermana
`def build_context_and_triage_for_mode(...) -> tuple[list[dict], dict]`
que contenga la lógica, y dejar `build_context_for_mode` **con la misma firma exacta** (`mode, plan, project_name, operator_note=""`) delegando y devolviendo sólo los bloques. `run_documenter` (`:1363`) usa la nueva y persiste el triage bajo la clave `"ticket_mining"` — **la clave que `api/docs.py:363` ya expone y que hoy siempre devuelve `{}`**. **Backward-compatible: todos los tests existentes de `build_context_for_mode` siguen pasando sin cambios.**

#### F3.3 — El operador lo ve

- `documenterModel.ts` — función pura nueva `buildTriageView(ticketMining)` ⇒ `{ visible, headline, truncatedWarning, reasonRows: [{reason, count, human}], noiseRows: [...] }`. Mapear cada motivo interno a texto llano siguiendo el patrón de `formatSkipReason` (**`documenterModel.ts:87`** — la v1 decía 91, que es una línea del map interno). Mapeos obligatorios (usar **los strings reales** que emite `classify_ticket`, verificándolos en `doc_ticket_mining.py:81-146` antes de escribir el map; `"sin_descripcion"` está en `:141`): sin descripción, ticket sintético (id negativo), título de prueba o descartable, cerrado sin descripción. **Todo motivo desconocido cae en un default legible que muestra el string crudo** — nunca se pierde.
- `DocumenterResultPanel.tsx` — sección plegable "Tickets descartados (N)" que renderice `reasonRows` y, al abrir, `noiseRows`.

**Flag de F3:**

| Flag | Tipo | Default | Justificación |
|---|---|---|---|
| `STACKY_DOCS_TICKET_TRIAGE_VISIBLE_ENABLED` | bool | **ON** | Persiste y muestra un resumen de un cálculo que **ya se hace**. Lectura + escritura en el reporte propio del run. No es (A) ni (B). Va ON. |

**Tests:**
- Backend (`test_documenter_v2_pipeline.py`): `test_f0_ticket_mining_queda_en_el_run_record`, `test_f0_truncamiento_se_declara_en_el_prompt`, `test_f3_reason_counts_suma_todo_el_barrido` (con 10 noise y `max_noise=3`: `sum(reason_counts.values()) >= 10` aunque `len(noise_sample) == 3`), `test_f3_build_context_for_mode_conserva_su_firma` (llamarla con la firma vieja de 3 y de 4 args y assertar que devuelve `list`), **`test_f3_truncamiento_por_caracteres_tambien_se_declara`** *(NUEVO v2)* (forzar `max_chars` chico con muchos signal ⇒ el content dice `"TRUNCADO"`; **gemelo:** con `max_chars` grande dice `"COMPLETO"`).
- Frontend (`src/docs/documenterModel.test.ts`): `buildTriageView` con truncado / sin truncado / vacío / `undefined` / motivo desconocido.

**Criterio de aceptación BINARIO de F3:**
1. Los 5 tests backend nombrados pasan.
2. `tests/test_docs_api.py` **una invocación sola** ⇒ **`>= 16 passed, 0 failed`**.
3. La clave dejó de estar muerta: `grep -n "ticket_mining" backend/services/doc_documenter.py` ⇒ **`>= 1`** línea de escritura en el reporte (hoy **0**).
4. `npx vitest run src/docs/documenterModel.test.ts` **sin pipe** ⇒ `Tests N passed` con **N ≥ 29**.

**Impacto por runtime.** Idéntico: el barrido es SQL puro sobre la base de Stacky (`doc_ticket_mining.py:180-191`), sin LLM. **Fallback:** si el barrido falla, F2.4 garantiza el aviso al modelo y el panel muestra la sección vacía con el motivo.

**Trabajo del operador: ninguno.**

---

### F4 — El árbol de documentación deja de mezclar

**Objetivo.** Que el operador, al abrir la pestaña de documentación, distinga de un vistazo la documentación **del proyecto** de los **planes**, y pueda filtrar.

**Valor.** Es la queja textual. El backend ya clasifica (`doc_indexer.py:172`); el frontend tiene la información y **no la usa** (2 hits, 0 en el árbol).

**Archivos a editar:**
- `Stacky Agents/frontend/src/docs/docTreeModel.ts` — **crear** (no existe). Función pura:
  ```ts
  export type DocClass = "plan" | "system" | "project" | "agent" | "other";
  export function partitionTreeByClass(
    nodes: DocNode[],
    active: Set<DocClass>
  ): { visible: DocNode[]; counts: Record<DocClass, number>; hidden: number }
  ```
  Reglas: una carpeta se conserva si **algún** descendiente queda visible (si no, se poda). `counts` cuenta hojas por clase sobre el árbol **completo**, no sobre el filtrado. Un nodo con `doc_class` ausente o `""` (backend viejo o `STACKY_DOCS_TAXONOMY_ENABLED` OFF ⇒ `doc_indexer.py:99` devuelve `""`) se trata como `"other"` y **siempre queda visible** — backward-compatible.
  **Las clases válidas se toman de `doc_taxonomy.classify_doc_path` (`doc_taxonomy.py:33`), no se inventan:** verificar el conjunto real antes de escribir el tipo.
- `Stacky Agents/frontend/src/pages/DocsPage.tsx` — barra de filtros con un chip por clase mostrando su conteo, montada junto al buscador existente (`:322-329`). **Default: `plan` desactivado**, el resto activo ⇒ por defecto el operador **no** ve los planes revueltos con su documentación.
  **Los conteos se COMPUTAN de `counts`. Prohibido hardcodear números** (la v1 escribía `Planes 240`; medido hoy son **241** y sube con cada plan nuevo — un literal envejece solo).
- `Stacky Agents/frontend/src/api/endpoints.ts` — agregar `doc_class?: string` al tipo del nodo del árbol (hoy sólo existe `by_doc_class` en `:3595`, que es de la radiografía, **otro objeto**).

**Test:** `Stacky Agents/frontend/src/docs/docTreeModel.test.ts` (**hermano del módulo; NO existe `__tests__/`**).
Casos obligatorios: (a) con `plan` desactivado, un árbol de 3 planes + 2 docs de proyecto deja 2 visibles y `hidden === 3`; (b) una carpeta con sólo planes se poda; (c) una carpeta con un plan y un doc de proyecto se conserva con un solo hijo; (d) nodos sin `doc_class` **y** con `doc_class: ""` sobreviven a cualquier filtro; (e) `counts` se calcula sobre el árbol completo aunque `visible` esté filtrado; (f) con `active` conteniendo **todas** las clases, `visible` es igual al árbol original y `hidden === 0` (**el caso "flag OFF"**).

**Comando:** `cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend" && npx vitest run src/docs/docTreeModel.test.ts` — **sin pipe.**

**Flag de F4:**

| Flag | Tipo | Default | Justificación |
|---|---|---|---|
| `STACKY_DOCS_TREE_GROUP_BY_CLASS_ENABLED` | bool | **ON** | Sólo cambia la presentación de datos que el backend ya envía. Lectura pura ⇒ nunca es excepción. Va ON. |

**Criterio de aceptación BINARIO de F4:**
1. Los 6 casos de `docTreeModel.test.ts` pasan (`Tests 6 passed` mínimo).
2. `cd "Stacky Agents/frontend" && npx tsc --noEmit` ⇒ **0 errores**.
3. El conteo deja de ser cero: `grep -rn "doc_class\|docClass" frontend/src/ | wc -l` ⇒ **`>= 8`** (hoy **2**, medido).
4. Con la flag OFF el árbol se comporta como hoy — cubierto por el caso (f).

**Impacto por runtime.** Ninguno: frontend puro. **Fallback:** si el backend no manda `doc_class` (taxonomía OFF ⇒ `""`), todos los nodos caen en `"other"` y quedan visibles ⇒ degrada al comportamiento de hoy sin romper.

**Trabajo del operador: ninguno.**

---

### F5 — Anti-regresión: que estos defectos no vuelvan

**Objetivo.** Congelar por test las propiedades que este plan establece, **por ALCANZABILIDAD y no por orden de líneas**.

**Archivo a editar:** `Stacky Agents/backend/tests/test_documenter_v2_pipeline.py` (ya registrado en los dos ratchets — **no crear archivos nuevos**).

**Tests de ratchet (nombres exactos):**
1. `test_r285_el_documentador_indexa_antes_de_las_etapas_de_papel` — censo por **AST** sobre `doc_documenter.py`: dentro de `run_documenter`, el `lineno` de la llamada a `ensure_corpus_indexed` debe ser **menor** que el del `return` del bloque HITL. **Censar por referencia de símbolo, no por regex de texto**: el AST da cero si la llamada va por alias, y un `grep` de texto premia el bug.
2. **`test_r285_el_gate_de_rigor_es_ALCANZABLE_en_las_4_combinaciones`** *(reemplaza al ratchet de números de línea de la v1)* — ejecuta `apply_proposals` con la matriz `V2 ∈ {on,off} × CITATION_GATE ∈ {on,off}` y exige rechazo del documento alucinado en las **4**. **Gemelo:** el documento sano se escribe en las 4.
   **Por qué se reemplaza:** el ratchet de la v1 comparaba `lineno(evaluate_rigor_gate) < lineno(dest.write_text)`. Esa comparación **se cumple igual si el gate está dentro de un `if` que nunca es verdadero**. Un ratchet de ORDEN no puede ver ALCANZABILIDAD.
3. **`test_r285_las_etapas_de_papel_no_vuelven_a_recibir_un_solo_bloque`** — captura los `blocks` de `invoke_raw_stage` en un run default y exige `len(blocks) >= 4` **y** presencia de los `id` `"docs-corpus"` y `"doc-subgraph"`. Congela F1.0, que es la fase raíz.
4. `test_r285_ticket_mining_no_es_una_clave_muerta` — el reporte de un run real (base temporal, `autoapply_override=True`) trae `ticket_mining` con la **key concreta** `"reason_counts"`. **Assertar presencia de la key, nunca `!= {}`**: un assert de "no vacío" pasa por accidente.
5. `test_r285_todos_los_modos_de_documentacion_ven_el_grafo` — `for mode in (RECONSTRUIR, COMPLETAR, ENRIQUECER)` hay bloque `"doc-subgraph"`; para **`NORMALIZAR` y `ACTUALIZAR` NO lo hay**. Congela **los dos** lados y **los cinco** modos (la v1 omitía `ACTUALIZAR`).
6. `test_r285_las_flags_del_285_tienen_consumidor_de_produccion` — para cada una de las **9** flags nuevas (lista literal en el test, no derivada), contar referencias fuera de `tests/` y `__tests__/`; exigir **`>= 1`**. Es el gate que distingue una flag viva de una registrada y muerta.
7. **`test_r285_el_mapa_requires_incluye_las_flags_del_285`** — las 9 keys están en `_REQUIRES_MAP_FROZEN`. Cierra la trampa de commit de C3.

**Criterio de aceptación BINARIO de F5 (una invocación por archivo):**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./.venv/Scripts/python.exe -m pytest tests/test_documenter_v2_pipeline.py -q --no-header -p no:cacheprovider
./.venv/Scripts/python.exe -m pytest tests/test_harness_ratchet_meta.py -q --no-header -p no:cacheprovider
./.venv/Scripts/python.exe -m pytest tests/test_plan259_ratchet_script_parity.py -q --no-header -p no:cacheprovider
```
El primero: **`>= 52 passed, 0 failed`** (38 preexistentes + 7 de F0 + 7 de F5). Los otros dos: **`0 failed`**.
**No se crean archivos de test nuevos en backend**, así que no hay que tocar ningún ratchet. Si por algún motivo se creara uno, hay que registrarlo en `run_harness_tests.ps1` **y** en `run_harness_tests.sh` (**sintaxis distinta, y los dos ya divergen entre sí**).

**Flag:** ninguna. **Impacto por runtime:** nulo. **Trabajo del operador: ninguno.**

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Prob. | Mitigación (concreta) |
|---|---|---|---|
| R1 | **El gate de rigor rechaza documentos legítimos** y el Documentador deja de producir nada. | Media | `trivial_lines=8`; código y encabezados no cuentan (dos tests dedicados); umbrales editables por UI; flag ON/OFF; `test_f0_gate_conserva_el_caso_legitimo_todo_NV` congela el caso legítimo. |
| R2 | **La auto-indexación agrega latencia** a cada corrida. | Media | TF-IDF puro, sin LLM y sin red (`docs_rag.py:145-208`). Sobre 310 `.md` (241 se excluyen) el trabajo real es ~69 archivos. Medir el tiempo en el test de F1 con un techo generoso. La flag lo apaga. |
| R3 | **La purga borra algo que importaba.** | Baja | Nace OFF (categoría B); lista antes de borrar; **backup a `.jsonl` antes de cualquier `DELETE`**; **aborta si el conteo de filas no coincide con el confirmado**; guarda dura con test: nunca borra un `project_name` configurado. |
| R4 | **`build_context_for_mode` cambia de firma** y rompe llamadores o tests. | Media | Prohibido cambiar su firma. F3.2 obliga a la función hermana. Test dedicado `test_f3_build_context_for_mode_conserva_su_firma`. |
| R5 | **Los tests nuevos contaminan la base real.** Es literalmente el origen de los 51 chunks basura. | **Alta** | Todo test que toque `docs_index` o `tickets` usa base en memoria o `tmp_path`. Antes de commitear: `SELECT COUNT(*) FROM docs_index` sobre `backend/data/stacky_agents.db` **no debe crecer** (hoy **51**). Si crece, el test está mal escrito. |
| R6 | **El default de ocultar planes confunde** al operador que buscaba un plan. | Baja | El chip "Planes" está visible **con su conteo computado** aunque esté desactivado: se ve que existen y se prenden con un clic. No se oculta información, se reordena. |
| R7 | **Rojos de fábrica ajenos** se confunden con daño de este plan. | Alta | Son **TRES** archivos (§4.4), no dos. Medirlos **antes** y anotar. Delta, nunca absoluto. El tercero (`test_harness_flags_requires.py`) **se salda** en F0.1. |
| R8 | Una **sesión paralela viva** pisa el trabajo. | Media | Prohibido `git stash`, `git reset`, `git checkout --`, `git commit --amend` y `git rebase`. Commitear con pathspec explícito: `git commit -m "..." -- "<ruta>"` (**el `-m` va ANTES del `--`**; después del `--` todo es pathspec). Un untracked pide `git add -- "<ruta>"` primero. |
| **R9** | **Contaminación de orden entre los 3 archivos de test.** | **Alta (MEDIDA)** | Los tres juntos dan `1 failed` (`test_plan284_approve_404_con_stages_off`); por separado, 79 verdes. **Todos los criterios de este plan son por archivo.** Si aparece un rojo, correr ese archivo solo antes de culpar al cambio. |
| **R10** | **El retrieval del corpus mete ruido en el prompt** (F1.4). | Media | `top_k=8` y sólo `file_path :: section_heading`, no el cuerpo entero. El filtro de planes de `docs_rag.py:164-169` ya excluye los 241 planes. Flag ON/OFF. Si no hay hits, el bloque **no se agrega** (`None`). |

---

## 7. Fuera de scope (deliberado, con la evidencia de por qué)

Estos ejes **fueron medidos y NO necesitan trabajo**, o el trabajo no se justifica todavía:

1. **La nota extra del operador.** Verificada punta a punta (§3.5), incluyendo que **también llega a las etapas de papel** (`_run_paper_stage:802-804`). Test centinela en `test_documenter_v2_pipeline.py:516`. **Nada que hacer.**
2. **El orden verificar→escribir del gate de citas** (`doc_documenter.py:914-937`). **No tocar.**
3. **`invoke_documenter` ya acepta `system_prompt_override`** (`:408`). El 284 lo abrió. **No tocar.**
4. **La regla de clasificación plan/proyecto.** `doc_taxonomy.py:28-30`, estricta, evita los 17 falsos. **No tocar.**
5. **Flags muertas del Documentador.** Las 22 flags `DOC*` tienen entrada en `config.py` y consumidor de producción. **Cero muertas.**
6. **Unificar los dos renderizadores de bloques.** `prompt_builder.render_blocks` (rama Copilot) vs `context_enrichment._render_blocks` (`:1433`, ramas CLI). **Verificado que el CLI ignora `kind` y usa `title`/`content`/`items`**, así que los bloques de este plan viajan bien por ambos. La asimetría es real y es riesgo de paridad, pero **no causa el dolor reportado** y tocarla cruza los 3 runtimes. **Merece su propio plan.**
7. **`staleness_fix` no acepta `operator_note`** (`api/docs.py:440-442`). Segundo punto de entrada, acotado a arreglar una nota stale. **Deuda declarada, no cerrada acá.**
8. **El estado `"unknown"` no renderiza el panel** (`documenterModel.ts:11-20`, `DocumenterButton.tsx:138`). Riesgo real (un estado nuevo del backend se vuelve invisible), pero **este plan no agrega estados nuevos**, así que no lo dispara. **Anotado como deuda.**
9. **Grafo exportable a formato agéntico (YAML/Mermaid).** El grafo **sí llega al modelo** vía `_subgraph_block` (`:219`), y F2.3 lo extiende a 3 de 5 modos. Un formato de exportación sin consumidor concreto sería **construir algo y no cablearlo**. **Se difiere hasta que exista el agente que lo consuma.**
10. **`rag_corpus.jsonl`** (`docs/rag/`, 169.544 bytes) tiene **0 referencias** en `backend/**` y `frontend/src/**`: **sidecar muerto**. El corpus vivo es `docs_index`. **No planificar contra el sidecar.**
11. **La contaminación de orden de `test_docs_api.py`** (R9). Es un bug de fixtures ajeno al Documentador; arreglarlo es un plan aparte. Acá se **declara y se esquiva** corriendo por archivo.

---

## 8. Glosario

| Término | Significado en Stacky |
|---|---|
| **Documentador** | Agente 1-click que genera/actualiza documentación. Entrada: `POST /api/docs/documenter/run` (`api/docs.py:294`). |
| **Modo** (`DocumenterMode`) | Uno de **CINCO**: `RECONSTRUIR`, `NORMALIZAR`, `COMPLETAR`, `ACTUALIZAR`, `ENRIQUECER` (`doc_documenter.py:56-61`). |
| **Etapa de papel** | `PROPONER` / `CRITICAR` / `MEJORAR` (`doc_documenter.py:1289-1307`). **Son el camino DEFAULT**: producen prosa y frenan en HITL antes de escribir un solo archivo. |
| **Barrera HITL** | El `return` de `doc_documenter.py:1335`. Con los defaults, el run se detiene ahí. Todo lo que esté **después** sólo corre tras la aprobación del operador. |
| **`context_block`** | Dict `{"id","kind","title","content"}`. El renderizador CLI (`context_enrichment.py:1433`) **ignora `kind`**: la señal va en `title` + `content`. |
| **Corpus RAG** | La tabla SQLite `docs_index` (`docs_rag.py:70`), escrita por `index_project` y leída por `search`/`search_hybrid`. **No** es `docs/rag/rag_corpus.jsonl` (sidecar muerto). |
| **Marca de confianza** | `[V]` verificado con `archivo:línea`, `[INF]` inferido, `[NV]` no verificable (`doc_documenter.py:165`). |
| **Afirmación** (nuevo en 285) | Línea no vacía que no es encabezado, ni separador, ni parte de un bloque de código. Unidad sobre la que F2 mide densidad. |
| **Gate** | Chequeo binario que puede **rechazar** un artefacto antes de escribirlo. Distinto de un reporte, que sólo informa. |
| **Alcanzabilidad** (nuevo en 285) | Que el gate **se ejecute** en las combinaciones de flags reales. Un test de ORDEN de líneas **no** la prueba. |
| **Triage señal/ruido** | Clasificación determinista por puntaje (`doc_ticket_mining.py:81-146`); `signal` si `score >= 2` (`:143`). |
| **Ratchet** | Test que congela una propiedad. Son **dos** scripts con sintaxis distinta (`.ps1` y `.sh`) que **ya divergen**. Es una trampa de **COMMIT**, no sólo de edición. |
| **Rojo de fábrica** | Test que ya fallaba antes de tu cambio. Los criterios se miden como **delta**. Hoy son **TRES** (§4.4). |
| **Las 8 patas** | Los ocho lugares que hay que tocar para que una flag funcione (§4.1). La octava —`_REQUIRES_MAP_FROZEN`— es la que la v1 negaba. |
| **Runtime** | Codex CLI, Claude Code CLI o GitHub Copilot Pro. Ortogonal a `LLM_BACKEND`. |

---

## 9. Orden de implementación

1. **Medir el estado inicial y ANOTARLO.** Correr los 3 archivos del Documentador **uno por invocación** (esperado 25 / 38 / 16), los **3** rojos de fábrica (esperado 4F, 3F, 1F), `test_harness_flags.py` (esperado 59), y `SELECT COUNT(*) FROM docs_index` (esperado **51**). **Pegar la salida real.**
2. **F0.1** — saldar `test_harness_flags_requires.py`. **No avanzar hasta verlo verde.**
3. **F0** — escribir los 11 tests que fallan. **No avanzar hasta ver 4 rojos en `test_doc_evidence.py` y 7 en `test_documenter_v2_pipeline.py`.**
4. **F1.1** + el `skipped_plans` de `docs_rag.index_project`.
5. **F1.4** (`_corpus_block`) — **después de F1.1, nunca antes**: leer un corpus que nadie indexó da un retrieval vacío que pasa los tests igual.
6. **F1.0** (`build_base_blocks` + reemplazo de `:1287`). Verificar `test_f0_las_etapas_de_papel_reciben_el_contexto_rico`.
7. **F1.2** (panel del corpus).
8. **F1.3** (huérfanos + backup + purga). Sus 4 flags con las **8 patas** cada una.
9. **F2.1** + **F2.2** (incluido el cambio de `:1391`). Sus 3 flags.
10. **F2.3** (subgrafo a 3 de 5 modos) y **F2.4** (el fallo del barrido deja de ser mudo).
11. **F3.1** → **F3.2** → **F3.3**. Su flag.
12. **F4**. Su flag. Correr `tsc --noEmit`.
13. **F5** (los 7 ratchets).
14. **Cierre:** regenerar `deployment/harness_defaults.env` **con el generador del repo** (`deployment/`, no a mano). Re-correr todo el bloque de verificación **por archivo** y comparar contra el paso 1. Verificar que `docs_index` **sigue en 51** (o en lo que quede tras una purga que el operador haya confirmado a mano).

---

## 10. Definición de Hecho (DoD) global

El plan 285 está HECHO cuando **todas** estas afirmaciones son verificables con un comando. **Cada comando es UNA invocación de UN archivo** (§4.3); no hay criterios agregados.

- [ ] Los 11 tests de F0 pasan, y **ninguno pasó por accidente**: cada uno se vio rojo primero (evidencia pegada en el reporte de implementación).
- [ ] `pytest tests/test_doc_evidence.py` → **`>= 38 passed, 0 failed`** (25 previos + 4 de F0 + 9 de F2).
- [ ] `pytest tests/test_documenter_v2_pipeline.py` → **`>= 52 passed, 0 failed`** (38 previos + 7 de F0 + 7 de F5).
- [ ] `pytest tests/test_docs_api.py` → **`>= 16 passed, 0 failed`**.
- [ ] `pytest tests/test_harness_flags.py` → **`>= 59 passed, 0 failed`** (**59 medido hoy**), y las 9 keys nuevas aparecen grepeadas en la salida de `_CURATED_DEFAULTS_ON` / registro — **un conteo global no discrimina si contaminaste**.
- [ ] `pytest tests/test_harness_flags_requires.py` → **`0 failed`** (hoy `1 failed`). Idem `test_fitness_flags.py` y `test_knowledge_flags.py`.
- [ ] `test_harness_flags_help.py` **≤ 4 failed** y `test_error_fingerprints_catalog.py` **≤ 3 failed** (delta contra el paso 1, nunca absoluto).
- [ ] `pytest tests/test_harness_ratchet_meta.py` y `pytest tests/test_plan259_ratchet_script_parity.py` → **0 failed**.
- [ ] `npx vitest run src/docs/documenterModel.test.ts` → `Tests N passed`, **N ≥ 29**. **Sin pipe** (un pipe se come el exit code).
- [ ] `npx vitest run src/docs/docTreeModel.test.ts` → `Tests N passed`, **N ≥ 6**.
- [ ] `npx tsc --noEmit` → **0 errores**.
- [ ] Las **9 flags nuevas** tienen sus **8 patas** completas y **cada una tiene al menos un consumidor de producción** (congelado por `test_r285_las_flags_del_285_tienen_consumidor_de_produccion`).
- [ ] `grep -n "from api\|import api" backend/services/doc_*.py` → **0 líneas**.
- [ ] `grep -rn "doc_class\|docClass" frontend/src/ | wc -l` → **`>= 8`** (hoy **2**).
- [ ] ~~`grep -n "ticket_mining" backend/services/doc_documenter.py` → **`>= 1`** (hoy **0**).~~
      **[CRITERIO CORREGIDO AL IMPLEMENTAR — la afirmación era FALSA]** Hoy da **3**, no 0
      (`:331` el import y `:332-333` las dos llamadas del 284). Un `>= 1` estaba
      satisfecho de antemano y **no discriminaba nada**. El criterio real es la clave
      ESCRITA en el reporte: `grep -c '"ticket_mining"' backend/services/doc_documenter.py`
      → **`>= 1`** (hoy **0**, medido).
- [ ] `grep -rn "docs_rag" backend/services/doc_documenter.py` → **`>= 1`** (hoy **0**) — **el corpus se lee, no sólo se escribe.**
- [ ] `SELECT COUNT(*) FROM docs_index` sobre `backend/data/stacky_agents.db` **no creció** por correr la suite (hoy **51**).
- [ ] `deployment/harness_defaults.env` regenerado **con el generador**, no editado a mano.
- [ ] Ningún `git stash`, `reset`, `checkout --`, `amend` ni `rebase`; todos los commits con pathspec explícito.
- [ ] **Smoke manual del operador** (human-in-the-loop): lanzar el Documentador desde la UI con una nota extra y confirmar que, **en la pantalla de aprobación — antes de aprobar nada —**, ve el estado del corpus; y tras aprobar, la cobertura, los archivos rechazados con motivo y los tickets descartados con su razón.

---

## 11. Nota de honestidad sobre este plan

Este documento **no propone re-hacer el 284**. Lo que el 285 agrega es exactamente lo que la medición encontró roto.

La **v1 de este plan fue RECHAZADA con 91 de 93 anclajes correctos.** Ninguno de sus seis bloqueantes era un `archivo:línea` mal escrito:

- creía que el corpus muerto bloqueaba al Documentador, sin verificar que **el Documentador nunca lo lee**;
- ponía la indexación *"antes del loop de modos"* sin ver que **el camino default retorna antes de llegar ahí**;
- prohibía tocar un mapa congelado que **hay que tocar** y que **ya estaba rojo**;
- colgaba un gate de densidad de una variable de citas que **puede ser `None` en producción** mientras su test la forzaba a existir;
- exigía `0 failed` con un comando que **hoy da `1 failed`**;
- y apuntaba dos comandos de test a un directorio que **no existe**.

Todos son **supuestos de capacidad y de orden**, no de ubicación. Por eso la v2 agrega F0.1, F1.0 y F1.4, cambia el ratchet de orden por uno de **alcanzabilidad**, y mueve todos los criterios a **una invocación por archivo**.

Si al implementar alguna afirmación de la §3 no se reproduce, **detenete y reportalo antes de codificar**. Un plan anclado en una foto vieja del repo es peor que no tener plan — y un plan anclado en una capacidad que no existe es peor todavía, porque sus anclajes están todos bien.

---

## 12. Changelog v1 → v2

### BLOQUEANTES resueltos

- **C1 — F1 indexaba un corpus que el Documentador nunca lee.** Medido: `grep -rn "docs_rag" backend/services/doc_documenter.py` → **0 líneas**; los únicos lectores de producción son `api/docs_rag.py:192,195` y `services/validation_playbook.py:429`. La v1 verificó al **escritor** y nunca al **lector**, y aun así llamaba a esto "el defecto nº1 que bloquea a todos los demás". ⇒ **Fase nueva F1.4** (`_corpus_block`, retrieval cableado al prompt), flag `STACKY_DOCS_CORPUS_RETRIEVAL_ENABLED` ON, test `test_f0_el_corpus_llega_al_prompt`, DoD `grep docs_rag >= 1`.
- **C2 — el camino DEFAULT retorna en `:1335` antes del loop de modos.** Con `STACKY_DOCS_PIPELINE_STAGES_ENABLED=true` y `AUTOAPPLY=false` (defaults), las 3 llamadas al LLM que el operador lee reciben `base_blocks = [_sistema_readonly_block(...)]` — **un bloque** (`:1287`, `_run_paper_stage:792-811`). Todo lo que la v1 mejoraba vivía del otro lado de la barrera HITL, y `ensure_corpus_indexed` "antes del loop de modos" **nunca se habría ejecutado** en la primera pasada. ⇒ **Fase nueva F1.0** (`build_base_blocks`), reubicación de `ensure_corpus_indexed` a **después de `:1249` y antes de `:1283`**, KPI **K0**, tests `test_f0_las_etapas_de_papel_reciben_el_contexto_rico` y ratchet nº3.
- **C3 — §4.1 prohibía tocar el mapa congelado de `requires`; hay que tocarlo, y ya estaba rojo.** `tests/test_harness_flags_requires.py:364-372` compara **por igualdad** `{s.key: s.requires}` contra un mapa de **165 keys indexado por KEY DE FLAG**: reusar un `requires` existente **no** exime. Registrado en `run_harness_tests.ps1:351` y `.sh:402` ⇒ trampa de COMMIT. **Medido: `1 failed, 8 passed` HOY**, por 11 keys del 284. ⇒ **Pata 8** en §4.1, **fase nueva F0.1** que lo salda antes de agregar nada, KPI **K7**, ratchet nº7, y `test_fitness_flags.py`/`test_knowledge_flags.py` sumados al DoD.
- **C4 — el gate de rigor nacía INERTE.** La v1 lo colgaba de `citations is not None`, pero `citations` sólo se puebla dentro de `if workspace_root is not None:` (`:918-922`) y `:1391` pasa `None` con V2 OFF + citas OFF. La densidad de marcas **no necesita citas**. Peor: el test de F0 forzaba `workspace_root` válido ⇒ **verde en test, muerto en producción**. ⇒ guard cambiado a `if _rigor_gate_enabled():`, regla 4 nueva (`citations is None` ⇒ omitir sólo el sub-chequeo de citas), extensión de `:1391`, tests `test_f0_rigor_rechaza_tambien_sin_workspace_root` y `test_f2_rigor_alcanzable_en_las_4_combinaciones`.
- **C5 — el DoD exigía `0 failed` con un comando que hoy da `1 failed`.** Medido: por archivo 25+38+16 = **79 verdes**; los tres juntos → **`1 failed, 78 passed`** (`test_docs_api.py::TestPlan284StageApprove::test_plan284_approve_404_con_stages_off`, contaminación de orden). La v1 se contradecía: pedía "por archivo" y daba un comando de 3. ⇒ **todos** los criterios pasan a una invocación por archivo, con conteo por archivo; criterio agregado `>= 95` eliminado; riesgo **R9** nuevo; §7.11.
- **C6 — dos comandos de vitest apuntaban a un directorio inexistente.** `frontend/src/docs/__tests__/` **no existe**; el archivo real es `src/docs/documenterModel.test.ts` (**20 tests verdes**). La v1 lo llamaba "archivo existente". Medido: `vitest run` contra ruta inexistente imprime "No test files found" y sale **1**, **pero pipeado el exit code se pierde**. ⇒ rutas corregidas, **prohibido pipear** el comando de aceptación, criterio por `Tests N passed`.

### MAYORES resueltos

- **C7 — el plan contaba mal sus propias flags:** decía "7 (6 ON, 1 OFF)"; eran **8** (5 bool ON + 1 OFF + 2 numéricas), y con F1.4 son **9** (6 bool ON). ⇒ tabla completa en §4.2; `_CURATED_DEFAULTS_ON` pasa de 12 a **18**; ratchet nº6 con la lista literal de 9.
- **C8 — "1 de 4 modos" / "3 de 4": hay CINCO.** `doc_documenter.py:56-61`. El propio glosario de la v1 los listaba bien ⇒ contradicción interna §1 vs §8. Y el ratchet omitía `ACTUALIZAR`. ⇒ K5 corregido a **1 de 5 → 3 de 5**; ratchet nº5 congela los **cinco**.
- **C9 — F3.1 cambiaba una afirmación falsa por otra más enfática.** Hay **dos** truncamientos: el cap SQL (`:190-191`) y el cap de caracteres del propio bloque (`:228-235`, `max_chars=12000`). Declarar "COMPLETO" con el segundo activo es mentir más fuerte. Además `total` (`:236`) cuenta signal+noise y el cuerpo lista sólo signal. ⇒ el mensaje declara los **dos ejes** y la asimetría; test `test_f3_truncamiento_por_caracteres_tambien_se_declara` con gemelo.
- **C10 — `evaluate_rigor_gate` "pura" con umbrales que sólo salen de config** ⇒ las 2 flags numéricas quedaban **registradas y muertas**, violando el DoD y el ratchet nº6. ⇒ se copia el idioma real de `evaluate_citation_gate:859-862` (config dentro del `try`), regla 1 explícita, test `test_f2_rigor_lee_los_umbrales_de_config`.
- **C11 — `test_f0_ticket_mining_queda_en_el_run_record` era inejecutable:** con los defaults `run_documenter` retorna en `:1335` sin llegar al triage. ⇒ `autoapply_override=True` declarado **obligatorio** en el test.
- **C12 — conteos hardcodeados que envejecen solos.** Medido hoy: **310** `.md`, **241** estricta, **258** laxa (la v1 decía 309/240/257: se contó **antes de existir**). F4 escribía `Planes 240` como literal. ⇒ los chips se **computan**; K1 pasa de "≥ 40 archivos" a "≥ 1 archivo real y `chunks_indexed > 0`"; principio 6 endurecido.
- **C13 — `test_harness_flags.py >= 56` estaba anclado 3 por debajo de la realidad (medido: 59)** ⇒ no detectaba la pérdida de hasta 3 tests. ⇒ `>= 59` + grep de las keys propias.
- **C14 — F1.3 destruía datos de la base viva de 193 MB sin backup ni reversión.** ⇒ `backup_corpus_projects` antes de todo `DELETE`, `expected_rows` obligatorio en el body con aborto por `row_count_mismatch`, `400` si falta, y 3 tests nuevos.
- **C15 — sólo declaraba 2 rojos de fábrica; hay 3.** ⇒ §4.4 con los tres medidos, K7, R7 actualizado.

### MENORES resueltos

- **C16 — 2 anclajes errados de 93 (97,8 % correctos):** `_run_paper_stage` está en `:792` (v1: 793); `formatSkipReason` está en `documenterModel.ts:87` (v1: 91, que es una línea del map interno). Corregidos y anotados.
- **C17 — `kind` es decorativo en el renderizador CLI** (`context_enrichment.py:1433-1455` usa `title`/`content`/`items`). Documentado en §3.2, §4.1 y el glosario para que nadie ponga semántica ahí.
- **C18 — sin huella de regresión.** Este plan mata clases de error reales (gate inerte, clave muerta, contexto que no llega). Queda anotado que corresponde registrarlas en `docs/sistema/error_fingerprints.json` al implementar (convención del repo, no bloqueante).

### [ADICIÓN ARQUITECTO] — mejoras que la v1 no tenía

- **[ADICIÓN ARQUITECTO 1] F1.0 `build_base_blocks` — el contexto rico cruza la barrera HITL.** Es la adición de mayor valor del plan: sin ella, F1/F2.3/F3 mejoran un camino que en la configuración default **no se ejecuta antes de que el operador apruebe**. Convierte el KPI K0 de **1 bloque a ≥ 4** en el único momento que el operador realmente lee. Respeta los rieles: cero trabajo extra (automático), HITL intacto (**mejora** la decisión humana en vez de saltearla — el operador ahora aprueba algo escrito **con** contexto), idéntico en los 3 runtimes (vive en `services/`, aguas arriba de `agent_runner.run_agent`), y reusa `_subgraph_block`/`_corpus_block`/`_tickets_block_safe` en vez de duplicar.
- **[ADICIÓN ARQUITECTO 2] El ratchet de ALCANZABILIDAD reemplaza al de orden de líneas.** El ratchet de la v1 (`lineno(evaluate_rigor_gate) < lineno(dest.write_text)`) **se cumple igual si el gate es inalcanzable** — habría congelado el bug de C4 como si fuera la solución. El nuevo ejecuta la matriz de 4 combinaciones de flags. Es la lección destilada de los planes 280 y 284 ("función construida, testeada, verde y jamás cableada") convertida en un test que se puede copiar a cualquier gate futuro.
- **[ADICIÓN ARQUITECTO 3] F0.1 — saldar el rojo antes de sumarle deuda.** Un test ratchet que ya está rojo **no protege nada**: cualquier daño nuevo se esconde en el mismo mensaje de error. Saldar `test_harness_flags_requires.py` cuesta una edición de lista y devuelve una señal viva para las 9 flags de este plan y para todos los planes que vengan.
- **[ADICIÓN ARQUITECTO 4] Backup + `expected_rows` en la purga.** `docs_index` es una tabla **derivada**: volcarla a `.jsonl` antes de borrar hace reversible la única operación destructiva del plan, sin costo ni trabajo para el operador. El `expected_rows` cierra la ventana de carrera entre "el operador miró la lista" y "el operador confirmó".

---

## 13. Reporte de implementación (2026-08-02)

Implementado en la rama `docs/plan-279`, **sin push**, con pathspec explícito en cada commit.

### 13.1 Resultado real de los tests — **una invocación por archivo**

| Archivo | Antes (medido) | Después (medido) | Criterio |
|---|---|---|---|
| `test_doc_evidence.py` | `25 passed` | **`38 passed`** | DoD `>= 38` ✅ |
| `test_documenter_v2_pipeline.py` | `38 passed` | **`60 passed`** | DoD `>= 52` ✅ |
| `test_docs_api.py` | `16 passed` | **`21 passed`** | DoD `>= 16` ✅ |
| `test_harness_flags.py` | `59 passed` | **`59 passed`** | DoD `>= 59` ✅ |
| `test_harness_flags_requires.py` | **`1 failed`, 8 passed** | **`9 passed`** | F0.1 ✅ |
| `test_fitness_flags.py` | `7 passed` | `7 passed` | ✅ |
| `test_knowledge_flags.py` | `8 passed` | `8 passed` | ✅ |
| `test_harness_ratchet_meta.py` | **`1 failed`, 3 passed** | **`4 passed`** | ✅ (4.º rojo, saldado) |
| `test_plan259_ratchet_script_parity.py` | `12 passed` | `12 passed` | ✅ |
| `test_harness_flags_help.py` | `4 failed, 4 passed` | `4 failed, 4 passed` | delta **0** ✅ (ajeno) |
| `test_error_fingerprints_catalog.py` | `3 failed, 5 passed` | `3 failed, 5 passed` | delta **0** ✅ (ajeno) |

Frontend: `documenterModel.test.ts` **20 → 29 passed** (DoD `>= 29`), `docTreeModel.test.ts` **7 passed**
(DoD `>= 6`), `npx tsc --noEmit` **EXIT 0, cero errores**.

**Delta de rojos: −2** (los dos saldados). Ningún rojo nuevo.

### 13.2 Los greps del DoD

| Comando | Antes | Después |
|---|---|---|
| `grep -c docs_rag backend/services/doc_documenter.py` | **0** | **6** (2 son llamadas reales) |
| `grep -c '"ticket_mining"' backend/services/doc_documenter.py` | **0** | **2** |
| `grep -rn "doc_class\|docClass" frontend/src/ \| wc -l` | **2** | **11** |
| `grep -c "from api\|import api" backend/services/doc_*.py` | **0** | **0** |
| `SELECT COUNT(*) FROM docs_index` (base viva) | **51** | **51** (no creció) |

### 13.3 La purga: **CONSTRUIDA, NO EJECUTADA — PENDIENTE DE APROBACIÓN DEL OPERADOR**

El código está completo y testeado, y la flag `STACKY_DOCS_CORPUS_PURGE_ENABLED` nace **OFF**.
Durante la implementación sólo se hicieron `SELECT` contra `backend/data/stacky_agents.db`.

**Estado medido de los huérfanos (2026-08-02, sólo lectura):** 51 filas en 8 proyectos —
`C1`(41), `D1`(2), `K1`(2), `M1`(2), `N1`(1), `PF1`(1), `PF2`(1), `ST1`(1).

Para ejecutarla hacen falta **dos** cosas del operador:
1. Encender la flag desde el panel del arnés (o `STACKY_DOCS_CORPUS_PURGE_ENABLED=true`).
2. Confirmar el conteo exacto. Si no coincide, **no borra nada** (`row_count_mismatch`).

```bash
# 1) Verificar la lista (sólo lectura, no borra)
curl -s http://localhost:5000/api/docs-rag/corpus/orphans

# 2) Purgar — SÓLO tras aprobación explícita. Hace backup a
#    backend/data/backups/docs_index_backup_<sello>.jsonl ANTES de cualquier DELETE.
curl -s -X POST http://localhost:5000/api/docs-rag/corpus/purge \
  -H "Content-Type: application/json" \
  -d '{"project_names":["C1","D1","K1","M1","N1","PF1","PF2","ST1"],"expected_rows":51}'
```

### 13.4 Afirmaciones del plan que resultaron **FALSAS** al implementarlas

1. **Pata 6 de §4.1** — *"cae en `capacidades_optin` por el prefijo"*. **Falso**: `_CATEGORY_KEYS` es un
   mapa explícito. Corregido arriba, con la medición.
2. **DoD §10** — *"`grep -n "ticket_mining" backend/services/doc_documenter.py` → `>= 1` (hoy 0)"*.
   **Falso**: hoy da **3**. El criterio no discriminaba. Corregido arriba.
3. **§4.4** — *"son TRES archivos"* rojos de fábrica. Son **CUATRO**: el DoD nombraba
   `test_harness_ratchet_meta.py` con `0 failed` y estaba en `1 failed`. Corregido arriba.
4. **F0.1 paso 2** — *"agregar exactamente esas con el valor de `requires` que el error indica"*. El
   mensaje del test lista **keys pero no valores**, y trunca a 4. Dos de las 11
   (`STACKY_DOCS_TAXONOMY_ENABLED`, `STACKY_DOCS_RADIOGRAPHY_ENABLED`) cuelgan de
   `STACKY_DOCS_GRAPH_ENABLED`, no del Documentador. Copiar el valor de las vecinas deja el test rojo
   con **`Extras: [] / Faltantes: []`** — completamente indiagnóstico.
5. **Rojos ajenos del brief** — se anunciaban 9 errores de `tsc` (`FinishWorkButton.tsx`,
   `QaBrowserRunModal.tsx`, `TicketBoard.tsx`). **Ya no existen**: `tsc --noEmit` da EXIT 0.

### 13.5 Desvíos deliberados

- **Las 9 flags se registraron en un solo paso**, no fase por fase. Sin dependencias entre ellas y con la
  ventaja de que el rojo de `_CATEGORY_KEYS` apareció una sola vez y fue atribuible.
- **Guarda extra en `list_orphan_corpus_projects`** que el plan no pedía: si la lista de proyectos
  configurados viene vacía devuelve `[]` en vez de declarar huérfano a **todo** el corpus. Un fallo de
  lectura de configuración no puede convertir la base entera en basura borrable.
- **`total_rows` en `mine_project_tickets`** rompía `test_plan284_mine_project_tickets_forma_garantizada`
  (assert de igualdad de claves). Se actualizó el test del 284 con el motivo escrito: la forma sigue
  siendo garantizada (misma clave en OFF, en OK y en el `except`).

### 13.6 Honestidad sobre el rojo previo

Los **11 tests de F0 se midieron rojos** contra el árbol de hoy, con el output pegado en el commit
`41b8b13c`. Los `test_f2_*`, `test_f3_*`, `test_f1_*` y `test_r285_*` se escribieron **después** de su
implementación en la misma fase: **no se midieron rojos**. Su símbolo objetivo no existía antes
(`evaluate_rigor_gate` dio `ImportError` en F0, medido), así que eran rojos por construcción — pero eso es
una deducción, no una medición. La excepción es `test_f2_rigor_lee_los_umbrales_de_config`, donde sí se
corrió una **prueba de mutación**: con los umbrales hardcodeados el test cae, o sea discrimina de verdad.
