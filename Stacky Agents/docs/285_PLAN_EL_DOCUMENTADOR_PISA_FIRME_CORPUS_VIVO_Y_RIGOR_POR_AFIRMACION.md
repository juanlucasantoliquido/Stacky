# Plan 285 — El Documentador pisa firme: corpus vivo, rigor por afirmación y descarte trazable

**Estado:** PROPUESTO (v1, sin criticar)
**Fecha:** 2026-08-01
**Rama de origen:** `docs/plan-279`
**Antecesor directo:** `284_PLAN_EL_DOCUMENTADOR_DEJA_DE_MEZCLAR_Y_DE_ADIVINAR_RADIOGRAFIA_VERIFICADA.md` (IMPLEMENTADO hoy, commits `f881f615` → `ac66a7af`)

---

## 1. Objetivo y KPI

El plan 284 construyó, hoy mismo, siete capacidades para el Documentador (frontera plan/proyecto, nota del operador, gate de citas, minería de tickets, pipeline de 5 etapas, radiografía, UI). **Todas están cableadas a producción y sus 79 tests están verdes** (medido: `test_doc_evidence.py` 25, `test_documenter_v2_pipeline.py` 38, `test_docs_api.py` 16). Y sin embargo el operador, después de todo eso, sigue reportando que el Documentador *no se entiende* y *mezcla los planes con la documentación del proyecto*.

Este plan no re-propone nada del 284. Se apoya en una medición hecha sobre el árbol de HOY que encontró **cinco brechas concretas entre "la capacidad existe" y "la capacidad es portante en el camino que el operador dispara"**. Las cinco están ancladas en `archivo:línea` verificada en la sección 3.

La tesis del 285 en una frase: **el 284 arregló las reglas, pero el material sobre el que esas reglas operan está muerto, y los gates que las hacen cumplir tienen un cuantificador equivocado.**

### KPI (todos medibles con un comando, ninguno subjetivo)

| # | KPI | Valor HOY (medido 2026-08-01) | Meta del 285 |
|---|---|---|---|
| K1 | Documentos reales del proyecto activo en el corpus RAG vivo (`docs_index`) | **0** (51 chunks, 22 archivos, **todos** fixtures de test: `a.md`, `n0.md`…`n12.md`) | **≥ 40** archivos reales del proyecto activo |
| K2 | Proyectos fantasma en `docs_index` (creados por tests, no existen como proyecto) | **8** (`C1`, `D1`, `K1`, `M1`, `N1`, `PF1`, `PF2`, `ST1`) | **0** tras purga confirmada por el operador |
| K3 | Documento alucinado (0 citas + 1 sola marca en 500 líneas) que el gate deja escribir | **SÍ se escribe** (dos agujeros: `doc_documenter.py:190` y `:865`) | **Se rechaza**, con motivo visible |
| K4 | Tickets descartados que el operador puede ver, con su motivo | **0** — `api/docs.py:363` devuelve `{}` siempre (nadie escribe esa clave) | **100%** de los `noise`, con `reasons` |
| K5 | Modos del Documentador que reciben el subgrafo documental | **1 de 4** (sólo `ENRIQUECER`, `doc_documenter.py:339`) | **3 de 4** (+ `RECONSTRUIR`, `COMPLETAR`) |
| K6 | Uso de `doc_class` en el árbol de documentación que ve el operador | **0** (se calcula en `doc_indexer.py:172`, el frontend lo ignora) | El árbol **agrupa y filtra** por clase |

---

## 2. Por qué ahora — la contradicción que hay que explicar

El 284 se dio por implementado con evidencia real. La medición de hoy confirma que **no mintió**: sus siete fases están en el código y funcionan. Entonces, ¿por qué el operador sigue con el mismo dolor?

Porque en Stacky el modo de falla dominante no es "no se construyó". Es **"se construyó, se testeó, quedó verde, y el camino que el usuario dispara pasa por al lado"**. El 284 cayó en cuatro variantes de ese patrón, y una quinta que es peor:

1. **El filtro correcto sobre un corpus vacío.** `docs_rag.py:164-169` excluye los planes del retrieval con la regla estricta y correcta. Pero el corpus que filtra (`docs_index`) contiene **cero documentos reales** y `index_project` (`docs_rag.py:145`) tiene **un único llamador de producción**: `api/docs_rag.py:143`, un endpoint HTTP que nadie dispara automáticamente. El filtro es perfecto y no filtra nada útil.
2. **La clasificación que el frontend ignora.** `doc_indexer.py:172` etiqueta cada nodo con `doc_class`. El frontend usa `doc_class` en **2 lugares** y **ninguno es el árbol de documentos**. El operador sigue viendo 240 planes revueltos con 54 documentos de proyecto, sin distinción visual. Eso es, literalmente, la queja.
3. **Gates de documento con el cuantificador equivocado.** `marks_ok = any(tok in body for tok in _MARKS)` (`doc_documenter.py:190`) — **una** marca en todo el cuerpo alcanza. Y `evaluate_citation_gate` devuelve `passed=True` cuando `total <= 0` (`doc_documenter.py:865`). Combinados: un documento largo con un `[V]` al principio y **cero** citas pasa los dos gates y se escribe. Que es exactamente lo que produce un modelo que alucina: no cita.
4. **El triage que nadie ve.** `classify_ticket` (`doc_ticket_mining.py:81`) es aritmética determinista, auditable y buena. Está cableada (`doc_documenter.py:332`). Pero el resultado sale de scope en la línea siguiente y **la clave `"ticket_mining"` de la API (`api/docs.py:363`) devuelve `{}` siempre** porque nadie hace `_update_run(..., ticket_mining=...)`. El pedido "que yo vea qué se descartó y por qué" está a cero.
5. **El contexto que llega a un solo modo.** El subgrafo documental se inyecta en `doc_documenter.py:339`, dentro de la rama `elif mode == ENRIQUECER`. Los modos que documentan desde cero (`RECONSTRUIR`, `COMPLETAR`) **no lo reciben**.

Ninguno de los cinco se arregla re-escribiendo el 284. Los cinco son de cableado, cuantificador o visibilidad.

---

## 3. Foto medida — evidencia que sostiene cada fase

> Regla del plan: **toda afirmación de esta sección fue verificada abriendo el archivo el 2026-08-01.** Si el implementador encuentra una divergencia, debe detenerse y reportarla antes de codificar (los anclajes de línea caducan entre pasadas; anclá por símbolo).

### 3.1 Corpus documental (F1)

| Hecho | Evidencia |
|---|---|
| Tabla del corpus vivo | `backend/services/docs_rag.py:70` → `__tablename__ = "docs_index"` |
| Contenido real de `docs_index` | 51 chunks / 22 `file_path` distintos / 8 `project_name`: `C1`(41), `D1`(2), `K1`(2), `M1`(2), `N1`(1), `PF1`(1), `PF2`(1), `ST1`(1). Nombres de archivo: `a.md`, `b.md`, `n0.md`…`n12.md`. **Todos fixtures de test.** `indexed_at` entre `2026-07-10 10:31:54` y `10:32:12`. |
| Único llamador de producción del indexador | `backend/api/docs_rag.py:143` → `result = index_project(name, workspace_root, docs_subpath)`, dentro de `route_index()` (`api/docs_rag.py:126`, `@bp.post("/index")`) |
| El Documentador **no** indexa | `grep -rn "index_project" backend/ --include=*.py | grep -v /tests/` devuelve sólo `api/docs_rag.py:26` (import), `api/docs_rag.py:143` (llamada), `services/docs_rag.py:8` (docstring) y `services/docs_rag.py:145` (definición). **`doc_documenter.py` no aparece.** |
| El filtro plan/proyecto SÍ existe y es correcto | `backend/services/docs_rag.py:164-169` → `if not doc_taxonomy.is_plan_doc(...)`, gateado por `STACKY_DOCS_TAXONOMY_ENABLED` |
| La regla de clasificación es la ESTRICTA (no el bug de prefijo suelto) | `backend/services/doc_taxonomy.py:28-30` → `_NUMBERED_DOC_RE = re.compile(r"^\d{2,3}_(plan|incidente|checklist|auditoria|postmortem)_", re.IGNORECASE)` |
| Censo del árbol de docs | 309 `.md` totales bajo `Stacky Agents/docs/`; **240** matchean la regla estricta; **257** matchean `^\d{2,3}_` a secas ⇒ **17 falsos** que la regla estricta evita correctamente (16 en `docs/_legacy/` + `docs/176_SMOKE_MANUAL.md`) |
| El re-index purga sólo su propio proyecto | `backend/services/docs_rag.py:199` → `session.query(DocChunk).filter_by(project_name=project_name).delete()` ⇒ los 8 proyectos fantasma **nunca** se limpian solos |

### 3.2 Gates de rigor (F2)

| Hecho | Evidencia |
|---|---|
| Marcas de confianza definidas | `backend/services/doc_documenter.py:165` → `_MARKS = ("[V]", "[INF]", "[NV]")` |
| **Agujero 1 — cuantificador existencial** | `backend/services/doc_documenter.py:190` → `marks_ok = any(tok in body for tok in _MARKS)`, dentro de `parse_proposals` (`:174`) |
| Consecuencia del agujero 1 | `apply_proposals` (`:882`) skippea con `"missing_confidence_marks"` en `:911` sólo si `marks_ok` es `False` ⇒ un `[V]` suelto en 500 líneas basta |
| **Agujero 2 — un doc sin citas pasa** | `backend/services/doc_documenter.py:865` → `if total <= 0: return {"passed": True, "ratio": 1.0, "reason": ""}` dentro de `evaluate_citation_gate` (`:843`) |
| El gate de citas SÍ rechaza (esto el 284 lo cerró bien) | `backend/services/doc_documenter.py:914-932`: la verificación (`:921`) va **antes** de la escritura (`:937`) y hay `continue` en `:932`. **Confirmado: el orden está invertido respecto al defecto original.** No tocar. |
| Defaults reales del gate | `backend/config.py:763` → `os.getenv("STACKY_DOCS_CITATION_GATE_ENABLED", "true")`; `backend/config.py:766` → `os.getenv("STACKY_DOCS_CITATION_GATE_MIN_RATIO", "0.8")` |
| El subgrafo llega a un solo modo | `backend/services/doc_documenter.py:339` → `blocks.append(_subgraph_block(project_name))`, dentro de `elif mode == DocumenterMode.ENRIQUECER`. Definición en `:219`. |

### 3.3 Minería de tickets (F3)

| Hecho | Evidencia |
|---|---|
| Base viva | `Stacky Agents/backend/data/stacky_agents.db` (193.196.032 bytes). **`Stacky Agents/DeployStackyAgents/data` NO EXISTE.** |
| Censo de tickets | **228** totales. Por proyecto: `RIPLEY` 65, `RSPACIFICO` 57, `p` 49, `P` 44, `ONP` 6, `RSSICREA` 3, `__demo__` 3, `test` 1. Por tracker: `azure_devops` 162, `gitlab` 63, `demo` 3. `ado_id < 0`: **103**. Descripción vacía: **29**. `LENGTH(description) < 200`: **112**. |
| Triage: función y umbrales | `backend/services/doc_ticket_mining.py:81` `classify_ticket`; umbrales en `:19` (`MIN_DESCRIPTION_CHARS = 200`), `:20` (`MIN_TITLE_CHARS = 15`), `:21` (`STRONG_SIGNAL_CHARS = 800`); veredicto en `:143` → `verdict = "signal" if score >= 2 else "noise"` |
| **El resultado del triage se pierde** | `backend/services/doc_documenter.py:332-333`: `mining` se calcula y se consume una sola vez para `build_tickets_context_block`; sale de scope. `grep -n "ticket_mining" backend/api/docs.py` → sólo `:363`, y **nada en el árbol de producción escribe esa clave** ⇒ el endpoint devuelve `{}` siempre. |
| **Truncamiento silencioso** | `doc_ticket_mining.py:190` calcula `total_rows = q.count()`; `:191` aplica `q.limit(cap)`; `:201` devuelve `"total": len(verdicts)` (**ya capado**); `:204` devuelve `"truncated": total_rows > cap`. Pero `build_tickets_context_block` (`:210`) **nunca lee `"truncated"`** y en `:243` escribe al prompt `f"Se barrieron {total} tickets; ..."` con el número recortado. Con cap=500 (`config.py:773`) y 65 tickets como techo real, hoy no se dispara — **pero el mensaje al modelo es falso por construcción.** |
| **El fallo del barrido es mudo** | `backend/services/doc_documenter.py:330-337`: el `try/except` traga cualquier excepción con `logger.warning`. Si el barrido falla, el modelo documenta sin historia y ni el modelo ni el operador se enteran. |
| Flags | `backend/config.py:770` → `STACKY_DOCS_TICKET_MINING_ENABLED` default **true**; `backend/config.py:773` → `STACKY_DOCS_TICKET_MINING_MAX` default **500** |

### 3.4 Legibilidad del árbol (F4)

| Hecho | Evidencia |
|---|---|
| El backend clasifica | `backend/services/doc_indexer.py:99` `_doc_class_for`, `:107` `classify_doc_path`, `:172` `"doc_class": _doc_class_for(rel_path)`, `:188` `"doc_class": "other"` para carpetas |
| El frontend lo ignora | `grep -rn "doc_class\|docClass" frontend/src/` devuelve **2** hits, ambos de la radiografía: `frontend/src/api/endpoints.ts:3595` (`by_doc_class?`) y `frontend/src/docs/documenterModel.ts:312` (`const porClase = r.by_doc_class ?? {}`). **Cero hits en el árbol de documentos.** |
| El árbol vive en | `frontend/src/pages/DocsPage.tsx` (472 líneas); tabs `"Lector"` (`:386`), `"Cobertura"` (`:395`), `"Grafo"` (`:404`); buscador en `:322-329`; `<DocumenterButton>` montado en `:368-376` |

### 3.5 Lo que el 284 SÍ dejó portante (no tocar — verificado)

Estos ejes fueron medidos y **están completos**. El 285 no propone alcance sobre ellos:

- **La nota extra del operador llega al modelo.** Cadena completa verificada: `DocumenterButton.tsx:28` (estado) → `:115` (textarea) → `:64` (`Docs.documenterRun`) → `endpoints.ts:3688-3698` (campo `operator_note`) → `api/docs.py:312-319` (lectura + validación + truncado) → `:322-323` (`start_documenter_run`) → `doc_documenter.py:1036` → `:1229` `run_documenter` → `:1363` `build_context_for_mode` → `:341-344` `blocks.insert(0, note_block)` → `_operator_note_block` (`:280-304`) → `invoke_documenter` (`:408`) → `agent_runner.run_agent(context_blocks=...)`. Hay incluso un test centinela: `test_documenter_v2_pipeline.py:516` asserta `"CENTINELA_CABLE_284" in render_blocks(...)`.
- **El orden verificar→escribir del gate de citas** (`doc_documenter.py:914-937`). Correcto.
- **La regla de clasificación estricta** (`doc_taxonomy.py:28-30`). Correcta; evita los 17 falsos.
- **Ninguna flag `DOC*` está muerta.** Las 22 tienen entrada en `config.py` y al menos un consumidor de producción.
- **El pipeline de 5 etapas con HITL** existe (`STACKY_DOCS_PIPELINE_STAGES_ENABLED` default `true`, `STACKY_DOCS_PIPELINE_AUTOAPPLY` default `false` — correctamente OFF por categoría (B)).

---

## 4. Principios y guardarraíles (obligatorios en cada fase)

1. **Paridad en 3 runtimes:** Codex CLI, Claude Code CLI, GitHub Copilot Pro. Ningún cambio de este plan toca lógica específica de un runtime: todo vive en `services/` y `api/`, aguas arriba de la bifurcación de `agent_runner.run_agent`. Cada fase declara igual su impacto y fallback por runtime.
2. **Human-in-the-loop innegociable.** Nada de este plan escribe en un sistema del operador sin confirmación. La única operación destructiva (purga del corpus fantasma, F1.3) nace OFF y además exige confirmación explícita en la UI.
3. **Mono-operador, sin auth.** Ningún RBAC. Un `403` significa flag apagada, nunca permiso.
4. **`services/` NUNCA importa de `api/`.** Verificable con `grep -n "from api\|import api" backend/services/doc_*.py` → debe seguir dando 0.
5. **Cero trabajo extra para el operador.** Todo default ON salvo la purga (categoría B, justificada por escrito en F1.3).
6. **Sobre conteos de planes usar siempre `>=`, nunca `==`.** Un criterio con igualdad exacta se pone rojo solo cuando entra el plan 286.
7. **Backward-compatible.** Todo parámetro nuevo tiene default que reproduce el comportamiento de hoy.

### 4.1 Las 7 patas de una flag nueva (checklist obligatorio, el implementador las hace TODAS)

Una flag booleana con `default=True` se rompe si falta cualquiera de estas. Verificado contra el molde real del 284 (`harness_flags.py:2848-2862`):

1. `backend/services/harness_flags.py` → `FlagSpec(key=..., default=True, type="bool", label=..., description=..., group="global", env_only=False, requires="STACKY_DOCS_DOCUMENTER_ENABLED")`. **Usar exactamente ese `requires`**: ya existe en el mapa (lo usan las 6 flags DOC del 284), así que no hay que tocar ningún mapa congelado.
2. `backend/config.py` → `os.getenv("<KEY>", "true").strip().lower() in ("1","true","yes","on")`. **El default efectivo es éste, no el del `FlagSpec`.**
3. `backend/tests/test_harness_flags.py` → agregar la key al set `_CURATED_DEFAULTS_ON` (arranca en `:467`). **Sin esto, `test_default_known_only_for_curated` se pone rojo.**
4. Categoría: cae en `capacidades_optin` por el prefijo; verificar que `test_flag_registry_categorization` siga verde.
5. `backend/services/harness_flags_help.py` → una entrada `PlainHelp(what=..., on_effect=..., off_effect=..., example=...)` en lenguaje llano (molde real en `:434-440`).
6. **Un consumidor real de producción** (no sólo un test). Sin esto la flag está registrada y muerta.
7. `deployment/harness_defaults.env` → regenerar con el generador del repo; **no editar a mano.**

**Flags numéricas (`int`/`float`): NO declaran `default=` en el `FlagSpec`** (molde real: `harness_flags.py:2864-2878`). `_CURATED_DEFAULTS_ON` sólo admite booleanas ON. Sí llevan `min_value`/`max_value` y sí llevan entrada en `config.py` y en `harness_flags_help.py`.

### 4.2 Cómo correr los tests (comando exacto)

```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./.venv/Scripts/python.exe -m pytest tests/<archivo>.py -q --no-header -p no:cacheprovider
```

- El intérprete es **`backend/.venv`** (py3.13.5). **No usar `backend/venv`** (py3.11.9, no tiene las dependencias).
- **Correr SIEMPRE por archivo.** `pytest tests` entero da miles de errores de contaminación cruzada y **no es un veredicto**.
- **Los tres archivos de test del Documentador ya están registrados en los dos ratchets** (`backend/scripts/run_harness_tests.ps1:367,369,371` y `backend/scripts/run_harness_tests.sh:418,420,422`). **Si los tests nuevos van dentro de esos tres archivos, no hay que tocar ningún ratchet.** Es la ruta recomendada. Si se crea un archivo nuevo, hay que registrarlo en **los dos** scripts (tienen sintaxis distinta) o el ratchet se pone rojo al commitear.
- **Un pytest suelto puede escribir en la base real.** Todo test que toque `docs_index` o `tickets` debe usar una base en memoria o un `tmp_path`; nunca `backend/data/stacky_agents.db`. (Este plan existe en parte *por* esa contaminación.)

---

## 5. Fases

### F0 — Red-team: probar los 5 defectos antes de tocar producción

**Objetivo.** Escribir los tests que fallan HOY y que demuestran cada defecto medido, para que ninguna fase posterior pueda declararse verde sin haberlo cerrado de verdad.

**Valor.** Sin F0, cada fase siguiente corre el riesgo de ser "verde por accidente". Con F0, el criterio de aceptación de F1..F4 es literalmente "estos tests que fallaban ahora pasan".

**Archivos a editar (no crear archivos nuevos — usar los ya registrados en los ratchets):**
- `Stacky Agents/backend/tests/test_documenter_v2_pipeline.py` (agregar al final)
- `Stacky Agents/backend/tests/test_doc_evidence.py` (agregar al final)

**Tests exactos a agregar** (nombres literales; cada uno debe FALLAR en el árbol actual):

En `test_doc_evidence.py`:

1. `test_f0_documento_sin_citas_y_una_sola_marca_es_rechazado`
   Construye un `DocProposal` con `content` de 60 líneas, exactamente **un** `[V]` en la primera línea, **cero** cadenas `archivo.py:NN`, y `sources=[]`. Llama a `parse_proposals` sobre el texto crudo equivalente y luego a `apply_proposals` con un `target_root` en `tmp_path` y un `workspace_root` válido. **Asserta que el archivo NO existe en disco** y que aparece en `result.skipped` con un motivo. Hoy FALLA: el archivo se escribe (dos agujeros, `doc_documenter.py:190` y `:865`).
2. `test_f0_densidad_de_marcas_por_afirmacion`
   Llama a la función nueva `evaluate_rigor_gate` (F2) con un cuerpo de 60 líneas y 1 marca ⇒ espera `passed=False`; con 10 líneas y 6 marcas ⇒ espera `passed=True`. Hoy FALLA: la función no existe (`ImportError`).
3. `test_f0_gate_conserva_el_caso_legitimo_todo_NV`
   Un documento corto (≤ 8 líneas) marcado íntegramente `[NV]` y sin citas debe **seguir pasando** (es el caso legítimo que `doc_documenter.py:865` protege y que NO hay que romper). Este test protege contra el sobre-endurecimiento.

En `test_documenter_v2_pipeline.py`:

4. `test_f0_corpus_rag_del_proyecto_activo_no_esta_vacio`
   Con una base temporal, corre el hook de auto-indexación de F1 sobre un `tmp_path` con 3 `.md` de proyecto y 2 con nombre de plan (`101_PLAN_X.md`). Asserta `chunks_indexed >= 3` y que ningún `file_path` indexado matchee la regla de plan. Hoy FALLA: el hook no existe.
5. `test_f0_ticket_mining_queda_en_el_run_record`
   Corre un `run_documenter` con la minería activa y asserta que el reporte persistido tiene `report["ticket_mining"]["noise_sample"]` no vacío y que cada entrada trae `reasons`. Hoy FALLA: la clave nunca se escribe (`api/docs.py:363` devuelve `{}`).
6. `test_f0_truncamiento_se_declara_en_el_prompt`
   Llama a `build_tickets_context_block({"total": 500, "truncated": True, ...})` y asserta que el `content` del bloque contiene la palabra `"truncado"`. Hoy FALLA: `doc_ticket_mining.py:210-243` nunca lee `"truncated"`.
7. `test_f0_subgrafo_llega_a_reconstruir_y_completar`
   Llama a `build_context_for_mode(DocumenterMode.RECONSTRUIR, plan, "X")` y asserta que existe un bloque cuyo `id`/`kind` corresponde al subgrafo. Idem para `COMPLETAR`. Hoy FALLA: sólo `ENRIQUECER` lo recibe (`doc_documenter.py:339`).
8. `test_f0_fallo_del_barrido_no_es_mudo`
   Monkeypatchea `doc_ticket_mining.mine_project_tickets` para que lance, y asserta que `build_context_for_mode` **igual devuelve un bloque** que declara que la historia de tickets no está disponible. Hoy FALLA: el `except` de `doc_documenter.py:330-337` es mudo.

**Comando:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./.venv/Scripts/python.exe -m pytest tests/test_doc_evidence.py tests/test_documenter_v2_pipeline.py -q --no-header -p no:cacheprovider
```

**Criterio de aceptación BINARIO.** Los 8 tests nuevos **fallan** (no error de import por typo, sino fallo de aserción o `ImportError` esperado en 2 y 4), y los **63 preexistentes** (25 + 38) siguen pasando. Se verifica con:
```bash
./.venv/Scripts/python.exe -m pytest tests/test_doc_evidence.py tests/test_documenter_v2_pipeline.py -q --no-header -p no:cacheprovider -k "f0_" 2>&1 | tail -3
```
Debe reportar **`8 failed`** (o `8 failed`/`errors` equivalente) y cero passed en el subconjunto `f0_`.

**Flag que la protege.** Ninguna: F0 no toca producción.
**Impacto por runtime.** Nulo (sólo tests). Codex / Claude Code / Copilot: idéntico.
**Trabajo del operador: ninguno.**

---

### F1 — El corpus documental deja de estar muerto

**Objetivo.** Que el Documentador indexe la documentación real del proyecto activo antes de usarla, y que el operador vea el estado del corpus en vez de adivinarlo.

**Valor.** Es el defecto nº1 y bloquea a todos los demás: hoy el retrieval documental del proyecto activo devuelve **cero documentos reales** y ocho proyectos fantasma de tests. Cualquier mejora de rigor o de UI sobre un corpus vacío es cosmética.

#### F1.1 — Hook de auto-indexación antes de la corrida

**Archivo a editar:** `Stacky Agents/backend/services/doc_documenter.py`

**Símbolo nuevo:** `def ensure_corpus_indexed(project_name: str, workspace_root: str | None) -> dict`

Colocarla **inmediatamente antes** de `def run_documenter(` (hoy en `:1229`) y llamarla **dentro de `run_documenter`, antes del loop de modos** (el loop que contiene `:1363`).

**Pseudocódigo exacto:**
```python
def ensure_corpus_indexed(project_name: str, workspace_root: str | None) -> dict:
    """Plan 285 F1.1 — Reindexa el corpus documental del proyecto antes de documentar.

    Sin esto el retrieval consulta un indice viejo o vacio: medido 2026-08-01,
    docs_index tenia 51 chunks y CERO documentos reales (todos fixtures de test).

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
    except Exception as exc:                     # nunca tumba el run
        out["error"] = str(exc)[:200]
        logger.warning("doc_documenter: auto-index del corpus fallo: %s", exc)
    return out
```

**Cambio acompañante en `docs_rag.index_project`** (`Stacky Agents/backend/services/docs_rag.py:145`): el `return` final (que hoy devuelve `{"chunks_indexed", "files_scanned"}`) debe agregar la key `"skipped_plans"` con la cantidad de archivos que el filtro de `:164-169` descartó. Calcularla como `len(md_files_antes) - len(md_files_despues)` guardando el largo antes del filtro. **Aditivo: ningún llamador existente se rompe.**

**Persistencia:** el dict devuelto se guarda en el reporte del run con la clave `"corpus"`, junto a `"radiography"` (patrón existente en `doc_documenter.py:1442-1458`).

**Exposición:** en `Stacky Agents/backend/api/docs.py`, dentro de `documenter_status()` (`:330`), agregar junto a `:363`:
```python
"corpus": rec.get("corpus", {}),
```

#### F1.2 — El operador ve el estado del corpus

**Archivos a editar:**
- `Stacky Agents/frontend/src/docs/documenterModel.ts` — nueva función pura `buildCorpusView(corpus)` que devuelve `{ visible: boolean, label: string, tone: "ok" | "warn" }`. Reglas: `chunks_indexed === 0` ⇒ `tone:"warn"`, `label:"Corpus vacío: el Documentador no tiene documentación del proyecto que consultar"`. `error !== ""` ⇒ `tone:"warn"` con el error. Si no, `tone:"ok"`, `label:"Corpus: N documentos indexados (M planes excluidos)"`.
- `Stacky Agents/frontend/src/components/docs/DocumenterResultPanel.tsx` — renderizar `buildCorpusView(...)` arriba de la línea de cobertura (hoy en `:139`).

**Por qué la lógica va en `documenterModel.ts` y no en el `.tsx`:** RTL/jsdom **no están instalados** en este repo. La lógica de UI testeable debe vivir en `.ts` puro y probarse con vitest; los `.test.tsx` con RTL reportan "no tests" y **exit 0** (falso verde).

**Test:** `Stacky Agents/frontend/src/docs/__tests__/documenterModel.test.ts` (archivo existente) — casos: corpus vacío, corpus con error, corpus sano, corpus ausente (`undefined` ⇒ `visible:false`).
**Comando:** `cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend" && npx vitest run src/docs/__tests__/documenterModel.test.ts`

#### F1.3 — Purga del corpus fantasma (la única operación destructiva)

**Archivos:**
- `Stacky Agents/backend/services/docs_rag.py` — dos funciones nuevas:
  - `def list_orphan_corpus_projects() -> list[dict]` — **solo lectura**. Devuelve, por cada `project_name` distinto en `docs_index` que **no** exista en la configuración de proyectos de Stacky, `{"project_name", "chunks", "files", "indexed_at"}`. Hoy debe devolver los 8: `C1`, `D1`, `K1`, `M1`, `N1`, `PF1`, `PF2`, `ST1`.
  - `def purge_orphan_corpus_projects(project_names: list[str]) -> dict` — **destructiva**. Borra de `docs_index` sólo los `project_name` pasados explícitamente por parámetro. **Nunca** borra un proyecto que exista en la configuración, aunque venga en la lista (guarda de seguridad, con test).
- `Stacky Agents/backend/api/docs_rag.py` — `@bp.get("/corpus/orphans")` (siempre disponible) y `@bp.post("/corpus/purge")` (gateado por la flag OFF; devuelve `403` con `{"error":"flag_disabled"}` si está apagada — recordar: en Stacky un `403` significa flag apagada, nunca permiso).
- Frontend: botón "Limpiar corpus huérfano" en el panel de docs, que **primero lista** los proyectos huérfanos con sus conteos y **exige confirmación explícita** del operador nombrando cuántas filas se borran.

**Flags de F1** (respetando la regla de partir la capacidad inocua de la destructiva — precedente `STACKY_PIPELINE_NL_EDIT_ENABLED` ON vs `..._COMMIT_ENABLED` OFF):

| Flag | Tipo | Default | Justificación |
|---|---|---|---|
| `STACKY_DOCS_CORPUS_AUTOINDEX_ENABLED` | bool | **ON** | Lee `.md` locales y escribe en una tabla derivada **propia de Stacky** (`docs_index`), sólo cuando el operador lanza el Documentador. **No es (A)**: no hay loop, daemon ni polling, y no llama a ningún modelo (el indexado es TF-IDF puro, `docs_rag.py:145-205`). **No es (B)**: no toca ningún sistema del operador. Va ON. |
| `STACKY_DOCS_CORPUS_ORPHANS_ENABLED` | bool | **ON** | Sólo lista y muestra. Lectura pura ⇒ nunca es excepción. Va ON. |
| `STACKY_DOCS_CORPUS_PURGE_ENABLED` | bool | **OFF** | **Excepción (B): destruye datos.** Borra filas de `docs_index` de forma irreversible; el re-index sólo regenera proyectos que existen, así que un proyecto huérgano borrado **no vuelve** (`docs_rag.py:199` purga por `project_name`, nada re-crea `C1`). Nace OFF y además exige confirmación en UI. |

**Criterio de aceptación BINARIO de F1:**
1. `test_f0_corpus_rag_del_proyecto_activo_no_esta_vacio` pasa.
2. Nuevo `test_f1_purga_nunca_borra_un_proyecto_configurado` pasa (pasarle un `project_name` real y verificar que las filas siguen ahí).
3. Nuevo `test_f1_index_project_reporta_skipped_plans` pasa: con 3 docs y 2 planes en `tmp_path`, `res["skipped_plans"] == 2`.
4. `POST /api/docs-rag/corpus/purge` con la flag OFF devuelve **403**.
5. Los 79 tests preexistentes (`test_doc_evidence.py` 25, `test_documenter_v2_pipeline.py` 38, `test_docs_api.py` 16) siguen verdes.

**Comando de verificación:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./.venv/Scripts/python.exe -m pytest tests/test_doc_evidence.py tests/test_documenter_v2_pipeline.py tests/test_docs_api.py -q --no-header -p no:cacheprovider
```
Debe reportar **`>= 84 passed, 0 failed`** (79 previos + al menos los 5 nuevos de F0/F1 que esta fase cierra). Usar `>=`, no `==`.

**Impacto por runtime.** Codex / Claude Code / Copilot: **idéntico**. El indexado ocurre en `services/`, antes de `agent_runner.run_agent`, aguas arriba de cualquier bifurcación por runtime. **Fallback común:** si `workspace_root` no está configurado o el directorio `docs/` no existe, `ensure_corpus_indexed` devuelve `{"error": "..."}`, el run continúa normalmente y el panel muestra el aviso. Nunca rompe.

**Trabajo del operador: ninguno** para F1.1 y F1.2 (automático). F1.3 es opt-in con default OFF por categoría (B), y su parte de sólo lectura (ver los huérfanos) está ON.

---

### F2 — Rigor por afirmación: pisar firme deja de ser una exhortación

**Objetivo.** Convertir "ir lento y pisando firme, sin alucinar" en un gate mecánico que mida **densidad de marcas** y **presencia mínima de citas**, en vez de aceptar una marca suelta y cero citas.

**Valor.** Cierra el agujero exacto por el que se cuela un documento íntegramente alucinado: hoy `marks_ok = any(...)` (`doc_documenter.py:190`) más `total <= 0 ⇒ passed=True` (`:865`) dejan pasar un texto de 500 líneas con un `[V]` decorativo y ninguna cita.

**Archivos a editar:**
- `Stacky Agents/backend/services/doc_documenter.py`
- `Stacky Agents/backend/services/harness_flags.py`, `backend/config.py`, `backend/services/harness_flags_help.py`, `backend/tests/test_harness_flags.py` (las 7 patas)

#### F2.1 — Función pura nueva `evaluate_rigor_gate`

Colocarla **inmediatamente después** de `evaluate_citation_gate` (hoy en `:843`), siguiendo el mismo estilo (pura, sin I/O, nunca lanza).

```python
def evaluate_rigor_gate(body: str, citations: dict, *,
                        min_density: float | None = None,
                        min_citations: int | None = None,
                        trivial_lines: int = 8) -> dict:
    """Plan 285 F2 — rigor POR AFIRMACION. PURA, sin I/O. Nunca lanza.

    El 284 midio rigor a nivel DOCUMENTO con cuantificador existencial:
    doc_documenter.py:190 acepta con UNA marca en todo el cuerpo, y
    doc_documenter.py:865 acepta un documento con CERO citas. Un texto
    alucinado cumple las dos cosas: no cita y le sobra con una marca.

    Definiciones EXACTAS:
      - "afirmacion" = linea no vacia que no sea encabezado markdown (no
        empieza con '#'), no sea separador ('---', '===') y no sea delimitador
        de bloque de codigo ('```'). Las lineas DENTRO de un bloque de codigo
        no cuentan como afirmacion.
      - densidad = (afirmaciones que contienen al menos una de _MARKS)
                   / (afirmaciones totales)
      - documento trivial = afirmaciones totales <= trivial_lines. Un doc
        trivial NO se rechaza por densidad ni por citas (protege el caso
        legitimo de una nota corta toda [NV]).

    Salida: {"passed": bool, "density": float, "claims": int,
             "marked": int, "citations_ok": int, "reason": str}
    Razones posibles: "" | "rigor_density_below:{m}/{c}" | "rigor_no_citations"
    """
```

**Reglas de decisión (en este orden, sin ambigüedad):**
1. Si la flag `STACKY_DOCS_RIGOR_PER_CLAIM_ENABLED` está OFF ⇒ `passed=True`, `reason=""`. (El llamador decide; la función pura recibe los umbrales ya resueltos.)
2. `claims <= trivial_lines` ⇒ `passed=True`. **Caso legítimo protegido.**
3. `density < min_density` ⇒ `passed=False`, `reason=f"rigor_density_below:{marked}/{claims}"`.
4. `citations["ok"] < min_citations` ⇒ `passed=False`, `reason="rigor_no_citations"`.
5. En cualquier otro caso ⇒ `passed=True`.
6. Ante cualquier excepción ⇒ `{"passed": True, ...}` (degradar sin bloquear, igual que `evaluate_citation_gate` en `:874`).

**Defaults:** `min_density = 0.5`, `min_citations = 1`, `trivial_lines = 8`.

#### F2.2 — Cablear el gate en `apply_proposals`

En `Stacky Agents/backend/services/doc_documenter.py`, dentro de `apply_proposals` (`:882`), **inmediatamente después** del bloque del gate de citas (que termina en `:932` con el `continue`) y **antes** del `try:` de escritura (`:934`):

```python
        # ---- Plan 285 F2: GATE DE RIGOR POR AFIRMACION ----
        if _rigor_gate_enabled() and citations is not None:
            rigor = evaluate_rigor_gate(prop.content, citations)
            if not rigor["passed"]:
                result.skipped.append((prop.path, rigor["reason"]))
                result.files.append({
                    "path": norm, "action": prop.action, "citations": citations,
                    "rigor": rigor,
                    "content_preview": prop.content[:_PREVIEW_MAX_CHARS],
                    "rejected": True, "reject_reason": rigor["reason"],
                })
                continue
        # ---------------------------------------------------
```

**Importante — no tocar `:190`.** `marks_ok = any(...)` se **conserva** tal cual: sigue siendo el filtro barato de primer nivel (un documento con cero marcas se descarta antes, en `:911`). El gate nuevo es el segundo nivel, más fino. Cambiar `:190` rompería `test_documenter_v2_pipeline.py` sin ganar nada.

**Importante — no tocar `:865`.** `evaluate_citation_gate` sigue devolviendo `passed=True` con `total==0`: es correcto para su propia semántica ("el que miente es el que cita mal, no el que no cita"). El requisito de citas mínimas lo impone `evaluate_rigor_gate`, que **sí** distingue documento trivial de documento largo.

#### F2.3 — El subgrafo llega a los modos que documentan de cero

En `Stacky Agents/backend/services/doc_documenter.py`, dentro de `build_context_for_mode` (`:307`): mover `blocks.append(_subgraph_block(project_name))` (hoy en `:339`, exclusivo de `ENRIQUECER`) para que también se ejecute en la rama `elif mode in (DocumenterMode.RECONSTRUIR, DocumenterMode.COMPLETAR)` (la rama que arranca en `:324`). La forma más simple y sin duplicar código: sacar el `append` de las dos ramas y ponerlo una sola vez, junto al `_sistema_readonly_block` de `:344`, gateado por `if mode in (RECONSTRUIR, COMPLETAR, ENRIQUECER)`.

#### F2.4 — El fallo del barrido de tickets deja de ser mudo

En el `except` de `doc_documenter.py:330-337`, además del `logger.warning`, agregar un bloque de contexto que **le diga al modelo** que la historia de tickets no está disponible:
```python
        except Exception as exc:
            logger.warning("doc_documenter: mineria de tickets fallo: %s", exc)
            blocks.append({
                "id": "tickets-unavailable", "kind": "warning",
                "title": "Historia de tickets NO disponible",
                "content": ("El barrido de tickets fallo en este run. NO afirmes "
                            "nada sobre la historia del proyecto derivada de "
                            "tickets: marcalo [NV]."),
            })
```

**Flags de F2:**

| Flag | Tipo | Default | Justificación |
|---|---|---|---|
| `STACKY_DOCS_RIGOR_PER_CLAIM_ENABLED` | bool | **ON** | Endurece un gate de calidad sobre un artefacto que Stacky genera en su propia rama git revertible. No es (A) ni (B). Va ON. |
| `STACKY_DOCS_RIGOR_MIN_DENSITY` | float | **0.5** | `min_value=0.0`, `max_value=1.0`. Sin `default=` en el `FlagSpec` (numérica). |
| `STACKY_DOCS_RIGOR_MIN_CITATIONS` | int | **1** | `min_value=0`, `max_value=50`. Sin `default=` en el `FlagSpec` (numérica). |

**Tests (TDD, primero):** en `Stacky Agents/backend/tests/test_doc_evidence.py`, además de los de F0:
- `test_f2_rigor_documento_trivial_pasa` — 5 líneas, 0 marcas, 0 citas ⇒ `passed=True`.
- `test_f2_rigor_densidad_justo_en_el_umbral` — 10 afirmaciones, 5 marcadas, `min_density=0.5` ⇒ `passed=True` (el `>=` importa).
- `test_f2_rigor_densidad_un_pelo_abajo` — 10 afirmaciones, 4 marcadas ⇒ `passed=False`, `reason` empieza con `"rigor_density_below:"`.
- `test_f2_rigor_lineas_de_codigo_no_cuentan_como_afirmacion` — un doc con 3 afirmaciones marcadas y 40 líneas dentro de un bloque ```` ``` ```` ⇒ `passed=True` (si contara el código, la densidad se hundiría y sería un falso rojo).
- `test_f2_rigor_encabezados_no_cuentan` — idem con 20 líneas `##`.
- `test_f2_rigor_degrada_ante_basura` — pasarle `None` y `{}` ⇒ `passed=True`, no lanza.
- `test_f2_gate_apagado_no_rechaza_nada` — con `STACKY_DOCS_RIGOR_PER_CLAIM_ENABLED=false`, el documento de `test_f0_documento_sin_citas_y_una_sola_marca_es_rechazado` **sí** se escribe. **Este test prueba que la flag es portante, no decorativa.**

**Criterio de aceptación BINARIO de F2:**
1. `test_f0_documento_sin_citas_y_una_sola_marca_es_rechazado` pasa.
2. `test_f0_documento_sin_citas_y_una_sola_marca_es_rechazado` **falla al revés** con la flag apagada — cubierto por `test_f2_gate_apagado_no_rechaza_nada`.
3. `test_f0_gate_conserva_el_caso_legitimo_todo_NV` pasa (no se sobre-endureció).
4. `test_f0_subgrafo_llega_a_reconstruir_y_completar` pasa.
5. `test_f0_fallo_del_barrido_no_es_mudo` pasa.
6. El registro de flags sigue verde: `./.venv/Scripts/python.exe -m pytest tests/test_harness_flags.py -q --no-header -p no:cacheprovider` debe dar **`>= 56 passed, 0 failed`** (56 es el valor medido hoy en este archivo; usar `>=` porque las 3 flags nuevas suman casos).

**Nota sobre rojos de fábrica.** `tests/test_harness_flags_help.py` está **rojo de fábrica** (4 fallos preexistentes, deuda ajena) y `tests/test_error_fingerprints_catalog.py` también (3 fallos). **No son de este plan.** El criterio se mide como **delta**: los conteos de fallos de esos dos archivos deben quedar **iguales o menores** que antes del cambio, nunca mayores. Medirlos antes de empezar y anotarlos.

**Impacto por runtime.** Codex / Claude Code / Copilot: **idéntico**. `evaluate_rigor_gate` y `apply_proposals` corren en el proceso del backend, después de que cualquiera de los tres runtimes devolvió su texto. **Fallback:** con la flag OFF el comportamiento es exactamente el de hoy (backward-compatible bit a bit).

**Trabajo del operador: ninguno** (default ON, invisible). Los dos knobs numéricos quedan editables desde el panel de flags de la UI, que lee el registry dinámicamente (`frontend/src/components/HarnessFlagsPanel.tsx`) — no hay que tocar el frontend para que aparezcan.

---

### F3 — El descarte de tickets se vuelve trazable

**Objetivo.** Que el operador pueda ver **qué tickets se descartaron y por qué**, y que el modelo nunca reciba una afirmación de cobertura total que sea falsa.

**Valor.** Cierra el pedido textual del operador ("tiene que saber diferenciar entre basura y algo valioso... el descarte trazable"). El triage ya existe y es bueno; lo que falta es que salga del scope de una función.

**Archivos a editar:**
- `Stacky Agents/backend/services/doc_ticket_mining.py`
- `Stacky Agents/backend/services/doc_documenter.py`
- `Stacky Agents/backend/api/docs.py`
- `Stacky Agents/frontend/src/docs/documenterModel.ts`
- `Stacky Agents/frontend/src/components/docs/DocumenterResultPanel.tsx`

#### F3.1 — Fin del truncamiento silencioso

En `Stacky Agents/backend/services/doc_ticket_mining.py`, dentro de `build_tickets_context_block` (`:210`):
- Agregar al dict que se lee en `:236-237` la lectura de `mining.get("truncated", False)` y `mining.get("total_rows")`.
- Cambiar el texto de `:243`. Hoy: `f"Se barrieron {total} tickets; ..."`. Debe pasar a:
  - si **no** truncó: `f"Se barrieron los {total} tickets del proyecto (barrido COMPLETO); ..."`
  - si truncó: `f"Se barrieron {total} de {total_rows} tickets (barrido TRUNCADO, faltan {total_rows - total}). NO afirmes cobertura total de la historia del proyecto; ..."`
- Agregar `"total_rows": total_rows` al dict devuelto por `mine_project_tickets` (`:201-204`) — hoy `total_rows` se calcula en `:190` y se usa sólo para el booleano `"truncated"` de `:204`, y se descarta.

#### F3.2 — El triage se persiste y se expone

En `Stacky Agents/backend/services/doc_ticket_mining.py`, función nueva:
```python
def build_triage_report(mining: dict, *, max_noise: int = 50) -> dict:
    """Plan 285 F3 — resumen AUDITABLE del triage, para el operador.

    Devuelve SIEMPRE las mismas keys:
      {"total": int, "total_rows": int, "truncated": bool,
       "signal": int, "noise": int, "by_tracker": dict,
       "noise_sample": [{"external_id","tracker_type","title","score","reasons"}],
       "reason_counts": {"<motivo>": int}}

    noise_sample lleva los peores primero (score ascendente) hasta max_noise.
    reason_counts cuenta cuantas veces disparo cada motivo sobre TODO el
    barrido, no solo sobre la muestra: es el numero que responde "por que se
    descarto tanto".
    """
```

En `Stacky Agents/backend/services/doc_documenter.py:332`, después de calcular `mining`, agregar:
```python
                triage = doc_ticket_mining.build_triage_report(mining)
```
y que `run_documenter` lo persista en el reporte del run bajo la clave `"ticket_mining"` — **la clave que `api/docs.py:363` ya expone y que hoy siempre devuelve `{}`**. Como `build_context_for_mode` (`:307`) es una función pura de armado de contexto y **no** debe escribir en el run record, el camino correcto es que devuelva el triage junto a los bloques. Opción de implementación **obligatoria** (para no romper los llamadores existentes de `build_context_for_mode`): agregar una función hermana `build_context_and_triage_for_mode(...) -> tuple[list[dict], dict]` que llame internamente a la lógica compartida, y que `run_documenter` (`:1363`) use la nueva. `build_context_for_mode` se conserva con la misma firma delegando en la nueva y devolviendo sólo los bloques. **Backward-compatible: todos los tests existentes de `build_context_for_mode` siguen pasando sin cambios.**

#### F3.3 — El operador lo ve

- `documenterModel.ts` — función pura nueva `buildTriageView(ticketMining)` que devuelve `{ visible, headline, truncatedWarning, reasonRows: [{reason, count, human}], noiseRows: [...] }`. Mapear cada motivo interno a texto llano (patrón existente: `formatSkipReason` en `documenterModel.ts:91`). Ejemplos obligatorios: `"desc_vacia"` → "Sin descripción"; `"sintetico"` → "Ticket sintético (id negativo)"; `"titulo_ruido"` → "Título de prueba o descartable"; `"cerrado_sin_desc"` → "Cerrado sin descripción".
- `DocumenterResultPanel.tsx` — una sección plegable "Tickets descartados (N)" que renderice `reasonRows` (el resumen) y, al abrir, `noiseRows`.

**Flag de F3:**

| Flag | Tipo | Default | Justificación |
|---|---|---|---|
| `STACKY_DOCS_TICKET_TRIAGE_VISIBLE_ENABLED` | bool | **ON** | Persiste y muestra un resumen de un cálculo que ya se hace. Lectura + escritura en el reporte propio del run. No es (A) ni (B). Va ON. |

**Tests:**
- Backend, en `test_documenter_v2_pipeline.py`: `test_f0_ticket_mining_queda_en_el_run_record`, `test_f0_truncamiento_se_declara_en_el_prompt`, más `test_f3_reason_counts_suma_todo_el_barrido` (con 10 noise y `max_noise=3`, `sum(reason_counts.values()) >= 10` aunque `len(noise_sample) == 3`) y `test_f3_build_context_for_mode_conserva_su_firma` (llamarla con la firma vieja y asertar que devuelve `list`).
- Frontend, en `documenterModel.test.ts`: `buildTriageView` con truncado / sin truncado / vacío / `undefined`.

**Criterio de aceptación BINARIO de F3:**
1. Los 4 tests backend nombrados pasan.
2. `./.venv/Scripts/python.exe -m pytest tests/test_docs_api.py -q --no-header -p no:cacheprovider` da **`>= 16 passed, 0 failed`**.
3. Verificación de que la clave dejó de estar muerta:
   `grep -n "ticket_mining" backend/services/doc_documenter.py` debe devolver **al menos 1** línea de escritura en el reporte (hoy devuelve **0**).
4. `npx vitest run src/docs/__tests__/documenterModel.test.ts` verde.

**Impacto por runtime.** Codex / Claude Code / Copilot: **idéntico**. El barrido de tickets es SQL puro sobre la base de Stacky (`doc_ticket_mining.py:180-191`), sin LLM y sin dependencia de runtime. **Fallback:** si el barrido falla, F2.4 ya garantiza que el modelo recibe el aviso y el panel muestra la sección vacía con el motivo.

**Trabajo del operador: ninguno.**

---

### F4 — El árbol de documentación deja de mezclar

**Objetivo.** Que el operador, al abrir la pestaña de documentación, distinga de un vistazo la documentación **del proyecto** de los **planes**, y pueda filtrar.

**Valor.** Es la queja textual ("se mezclan los planes con los del proyecto"). El backend ya clasifica (`doc_indexer.py:172`); el frontend tiene la información y **no la usa** (0 hits de `doc_class` en el árbol).

**Archivos a editar:**
- `Stacky Agents/frontend/src/docs/docTreeModel.ts` — **crear si no existe**; si existe, extender. Función pura nueva:
  ```ts
  export type DocClass = "plan" | "system" | "project" | "agent" | "other";
  export function partitionTreeByClass(
    nodes: DocNode[],
    active: Set<DocClass>
  ): { visible: DocNode[]; counts: Record<DocClass, number>; hidden: number }
  ```
  Reglas: un nodo de tipo carpeta se conserva si **algún** descendiente queda visible (si no, se poda). `counts` cuenta hojas por clase sobre el árbol **completo**, no sobre el filtrado. Un nodo sin `doc_class` (backend viejo o flag de taxonomía OFF) se trata como `"other"` y **siempre queda visible** — backward-compatible.
- `Stacky Agents/frontend/src/pages/DocsPage.tsx` — barra de filtros con un chip por clase mostrando el conteo (`Proyecto 54`, `Planes 240`, `Sistema 15`, `Agentes N`, `Otros N`), y **default: `plan` desactivado**, el resto activo. Es decir: **por defecto el operador NO ve los 240 planes revueltos con su documentación.** Montarla junto al buscador existente (`:322-329`).
- `Stacky Agents/frontend/src/api/endpoints.ts` — agregar `doc_class?: string` al tipo del nodo del árbol (hoy sólo existe `by_doc_class` en `:3595`, que es de la radiografía, otro objeto).

**Test:** `Stacky Agents/frontend/src/docs/__tests__/docTreeModel.test.ts`
Casos obligatorios: (a) con `plan` desactivado, un árbol de 3 planes + 2 docs de proyecto deja 2 visibles y `hidden === 3`; (b) una carpeta que sólo contiene planes se poda; (c) una carpeta con un plan y un doc de proyecto se conserva con un solo hijo; (d) nodos sin `doc_class` sobreviven a cualquier filtro; (e) `counts` se calcula sobre el árbol completo aunque `visible` esté filtrado.

**Comando:** `cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend" && npx vitest run src/docs/__tests__/docTreeModel.test.ts`

> Recordatorio para el implementador: correr vitest **por archivo**; hay contaminación por orden de test conocida en este frontend. Y un `.test.tsx` con RTL reporta **"no tests" con exit 0** — por eso toda la lógica va en `.ts` puro.

**Flag de F4:**

| Flag | Tipo | Default | Justificación |
|---|---|---|---|
| `STACKY_DOCS_TREE_GROUP_BY_CLASS_ENABLED` | bool | **ON** | Sólo cambia la presentación de datos que el backend ya envía. Lectura pura ⇒ nunca es excepción. Va ON. |

**Criterio de aceptación BINARIO de F4:**
1. Los 5 casos de `docTreeModel.test.ts` pasan.
2. `cd "Stacky Agents/frontend" && npx tsc --noEmit` termina con **0 errores**.
3. El conteo deja de ser cero: `grep -rn "doc_class\|docClass" frontend/src/ | wc -l` debe dar **`>= 8`** (hoy da 2).
4. Con la flag OFF, el árbol se comporta exactamente como hoy (test `test_f4_flag_off_no_filtra_nada`).

**Impacto por runtime.** Ninguno: es frontend puro. Codex / Claude Code / Copilot ven la misma UI. **Fallback:** si el backend no manda `doc_class` (flag de taxonomía OFF), todos los nodos caen en `"other"` y quedan visibles ⇒ el comportamiento degrada al de hoy, sin romper.

**Trabajo del operador: ninguno.**

---

### F5 — Anti-regresión: que estos cinco defectos no vuelvan

**Objetivo.** Congelar por test las cinco propiedades que este plan establece, para que un plan futuro no las deshaga en silencio.

**Archivo a editar:** `Stacky Agents/backend/tests/test_documenter_v2_pipeline.py` (ya registrado en los dos ratchets).

**Tests de ratchet (nombres exactos):**
1. `test_r285_el_documentador_indexa_antes_de_documentar` — censo por AST sobre `doc_documenter.py`: `run_documenter` debe contener una llamada a `ensure_corpus_indexed`. **Censar por referencia de símbolo, no por regex de texto**: un `grep` da cero si la llamada va por alias.
2. `test_r285_apply_proposals_evalua_rigor_antes_de_escribir` — sobre el AST de `apply_proposals`, el número de línea de la llamada a `evaluate_rigor_gate` debe ser **menor** que el de `dest.write_text`. Esto congela el orden, que es la propiedad que importa.
3. `test_r285_ticket_mining_no_es_una_clave_muerta` — el reporte de un run real (con base temporal) debe traer `ticket_mining` **no vacío**. Assertar la **presencia** de una key concreta (`"reason_counts"`), no sólo `!= {}`: un assert de ausencia o de "no vacío" pasa por accidente.
4. `test_r285_todos_los_modos_de_documentacion_ven_el_grafo` — `for mode in (RECONSTRUIR, COMPLETAR, ENRIQUECER)` debe haber bloque de subgrafo; para `NORMALIZAR` **no**. Congela ambos lados.
5. `test_r285_las_flags_del_285_tienen_consumidor_de_produccion` — para cada una de las **7** flags nuevas, contar referencias fuera de `tests/` y `__tests__/`; exigir `>= 1`. Es el gate que distingue una flag viva de una registrada y muerta.

**Criterio de aceptación BINARIO de F5:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./.venv/Scripts/python.exe -m pytest tests/test_documenter_v2_pipeline.py -q --no-header -p no:cacheprovider
```
Debe reportar **`>= 50 passed, 0 failed`** (38 preexistentes + los de F0/F3/F5). Usar `>=`.

Y el ratchet global sigue verde:
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./.venv/Scripts/python.exe -m pytest tests/test_harness_ratchet_meta.py tests/test_plan259_ratchet_script_parity.py -q --no-header -p no:cacheprovider
```
**0 failed.** (Si se agregó algún archivo de test nuevo, esta corrida lo detecta: hay que registrarlo en `run_harness_tests.ps1` **y** en `run_harness_tests.sh`.)

**Flag:** ninguna (son tests).
**Impacto por runtime:** nulo.
**Trabajo del operador: ninguno.**

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Mitigación (concreta) |
|---|---|---|---|
| R1 | **El gate de rigor rechaza documentos legítimos** (sobre-endurecimiento) y el Documentador deja de producir nada. | Media | `trivial_lines=8` protege notas cortas; las líneas de código y los encabezados no cuentan como afirmación (dos tests dedicados); umbrales editables por UI; flag ON/OFF. Y `test_f0_gate_conserva_el_caso_legitimo_todo_NV` congela el caso legítimo. |
| R2 | **La auto-indexación agrega latencia** perceptible a cada corrida del Documentador. | Media | El indexado es TF-IDF puro, sin LLM y sin red (`docs_rag.py:145-205`). Sobre 309 `.md` (de los cuales 240 se excluyen por el filtro de plan) el trabajo real es ~69 archivos. Medir el tiempo en el test de F1 y dejarlo asertado con un techo generoso. Si molesta, la flag lo apaga. |
| R3 | **La purga borra algo que importaba.** | Baja | Nace OFF (categoría B), lista antes de borrar, exige confirmación explícita con conteo, y tiene guarda dura con test: nunca borra un `project_name` que exista en la configuración. |
| R4 | **`build_context_for_mode` cambia de firma** y rompe llamadores o tests. | Media | Prohibido cambiar su firma. F3.2 obliga a agregar una función hermana y dejar la vieja delegando. Hay un test dedicado (`test_f3_build_context_for_mode_conserva_su_firma`). |
| R5 | **Los tests nuevos contaminan la base real.** Es literalmente el origen de los 51 chunks basura que este plan viene a limpiar. | **Alta** | Todo test que toque `docs_index` o `tickets` usa base en memoria o `tmp_path`. Antes de commitear, verificar: `SELECT COUNT(*) FROM docs_index` sobre `backend/data/stacky_agents.db` **no debe crecer** por correr los tests. Si crece, el test está mal escrito. |
| R6 | **El default de ocultar planes en el árbol confunde** al operador que buscaba un plan. | Baja | El chip "Planes 240" está visible y muestra el conteo aunque esté desactivado: se ve que existen y se prenden con un clic. No se oculta información, se reordena. |
| R7 | **Rojos de fábrica ajenos** (`test_harness_flags_help.py` 4F, `test_error_fingerprints_catalog.py` 3F) se confunden con daño de este plan. | Alta | Medir esos dos archivos **antes** de empezar y anotar el conteo. El criterio es delta: igual o menor, nunca mayor. |
| R8 | Una **sesión paralela viva** en este repo pisa el trabajo. | Media | Prohibido `git stash`, `git reset`, `git checkout --`, `git commit --amend` y `git rebase`. Commitear siempre con pathspec explícito (`git commit -m "..." -- "<ruta>"`, el `-m` va **antes** del `--`), porque el índice es compartido y un commit sin pathspec se roba archivos ajenos. |

---

## 7. Fuera de scope (deliberado, con la evidencia de por qué)

Estos ejes **fueron medidos y NO necesitan trabajo**, o el trabajo no se justifica todavía. Incluirlos sería inventar alcance:

1. **La nota extra del operador.** Verificada punta a punta (sección 3.5). Hay hasta un test centinela (`test_documenter_v2_pipeline.py:516`). **Nada que hacer.**
2. **El orden verificar→escribir del gate de citas.** Ya invertido correctamente en `doc_documenter.py:914-937`. **No tocar.**
3. **La regla de clasificación plan/proyecto.** `doc_taxonomy.py:28-30` usa la regla estricta correcta y evita los 17 falsos positivos que produciría `^\d{2,3}_` a secas. **No tocar.**
4. **Flags muertas del Documentador.** Se auditaron las 22 flags `DOC*`: todas tienen entrada en `config.py` y consumidor de producción. **Cero muertas.**
5. **Unificar los dos renderizadores de bloques.** Existen dos implementaciones paralelas: `prompt_builder.render_blocks` (`prompt_builder.py:10`, usada sólo por la rama Copilot) y `context_enrichment._render_blocks` (`context_enrichment.py:1433`, usada por las ramas CLI). Es una asimetría real y un riesgo de paridad, **pero no está causando el dolor que el operador reporta** y tocarla cruza el runtime de los 3 backends. Merece **su propio plan**, no un pedazo de éste.
6. **`staleness_fix` no acepta `operator_note`** (`api/docs.py:440-442`). Es un segundo punto de entrada, pero acotado a arreglar una nota stale específica, donde una instrucción libre del operador tiene poco sentido. **Deuda declarada, no cerrada acá.**
7. **El estado `"unknown"` no renderiza el panel** (`documenterModel.ts:11-20`, `DocumenterButton.tsx:138`). Es un riesgo real (un estado nuevo del backend se vuelve invisible), pero este plan no agrega estados nuevos al backend, así que no lo dispara. **Anotado como deuda.**
8. **Grafo exportable a formato agéntico (YAML/Mermaid para otros agentes).** Se midió: `grep -rln "doc_graph|grafo documental|graph.yaml" backend/Stacky` = **0**, y `Documentador.agent.md` no menciona el grafo. Pero el grafo **sí llega al modelo** como bloque de contexto vía `_subgraph_block` (`doc_documenter.py:219`), y F2.3 lo extiende a 3 de 4 modos. Un formato de exportación nuevo sin un consumidor concreto que lo pida sería **construir algo y no cablearlo** — exactamente el defecto que este plan combate. **Se difiere hasta que exista el agente que lo consuma.**
9. **`rag_corpus.jsonl`.** El archivo existe en `docs/rag/` pero tiene **0 referencias** en `backend/**` y `frontend/src/**`: es un sidecar muerto. El corpus vivo es la tabla `docs_index`. **No planificar contra el sidecar.**

---

## 8. Glosario

| Término | Significado en Stacky |
|---|---|
| **Documentador** | El agente 1-click que genera/actualiza documentación del proyecto. Entrada: `POST /api/docs/documenter/run` (`api/docs.py:294`). |
| **Modo** (`DocumenterMode`) | Uno de `RECONSTRUIR`, `COMPLETAR`, `ENRIQUECER`, `NORMALIZAR`, `ACTUALIZAR`. Determina qué contexto recibe el agente (`doc_documenter.py:307-345`). |
| **`context_block`** | Dict `{"id","kind","title","content"}` que el backend inyecta en el prompt del agente. El runtime lo renderiza a texto. |
| **Corpus RAG** | La tabla SQLite `docs_index` (`docs_rag.py:70`), poblada por `index_project`. **No** es `docs/rag/rag_corpus.jsonl` (sidecar muerto). |
| **Marca de confianza** | `[V]` verificado con `archivo:línea`, `[INF]` inferido, `[NV]` no verificable. Definidas en `doc_documenter.py:165`. |
| **Afirmación** (nuevo en 285) | Línea no vacía que no es encabezado, ni separador, ni parte de un bloque de código. La unidad sobre la que F2 mide densidad. |
| **Gate** | Chequeo binario que puede **rechazar** un artefacto antes de escribirlo. Distinto de un reporte, que sólo informa. |
| **Triage señal/ruido** | Clasificación determinista de tickets por puntaje (`doc_ticket_mining.py:81-143`). `signal` si `score >= 2`. |
| **Ratchet** | Test que congela una propiedad para que no se pueda deshacer sin que algo se ponga rojo. En este repo son dos scripts con sintaxis distinta (`.ps1` y `.sh`) que hay que mantener sincronizados. |
| **Rojo de fábrica** | Test que ya fallaba antes de tu cambio (deuda ajena). Los criterios se miden como **delta**, no en absoluto. |
| **Las 7 patas** | Los siete lugares que hay que tocar para que una flag booleana ON funcione (sección 4.1). |
| **Runtime** | Codex CLI, Claude Code CLI o GitHub Copilot Pro. El motor que ejecuta al agente. Ortogonal a `LLM_BACKEND`. |

---

## 9. Orden de implementación

1. **Medir el estado inicial y anotarlo.** Correr los 3 archivos de test del Documentador (79 esperados) y los 2 rojos de fábrica (`test_harness_flags_help.py`, `test_error_fingerprints_catalog.py`), y anotar los conteos exactos. Correr `SELECT COUNT(*) FROM docs_index` y anotarlo.
2. **F0** — escribir los 8 tests que fallan. **No avanzar hasta ver los 8 en rojo.**
3. **F1.1** + el `skipped_plans` de `docs_rag.index_project`. Verificar que `test_f0_corpus_rag_del_proyecto_activo_no_esta_vacio` pasa a verde.
4. **F1.2** (frontend, panel del corpus).
5. **F1.3** (huérfanos + purga). Las 3 flags de F1 con sus 7 patas cada una.
6. **F2.1** + **F2.2** (`evaluate_rigor_gate` y su cableado). Las 3 flags de F2.
7. **F2.3** (subgrafo a 3 modos) y **F2.4** (fallo del barrido deja de ser mudo).
8. **F3.1** (truncamiento) → **F3.2** (persistencia + función hermana) → **F3.3** (frontend). La flag de F3.
9. **F4** (árbol agrupado). La flag de F4. Correr `tsc --noEmit`.
10. **F5** (los 5 ratchets).
11. **Cierre:** regenerar `deployment/harness_defaults.env` con el generador del repo. Re-correr todo el bloque de verificación y comparar contra los conteos del paso 1. Verificar que `docs_index` **no creció** por los tests.

---

## 10. Definición de Hecho (DoD) global

El plan 285 está HECHO cuando **todas** estas afirmaciones son verificables con un comando:

- [ ] Los 8 tests de F0 pasan, y ninguno pasa por accidente (cada uno falló primero).
- [ ] `./.venv/Scripts/python.exe -m pytest tests/test_doc_evidence.py tests/test_documenter_v2_pipeline.py tests/test_docs_api.py -q` → **`>= 95 passed, 0 failed`** (79 previos + los nuevos).
- [ ] `./.venv/Scripts/python.exe -m pytest tests/test_harness_flags.py -q` → **`>= 56 passed, 0 failed`**.
- [ ] `test_harness_flags_help.py` y `test_error_fingerprints_catalog.py` tienen **igual o menos** fallos que en el paso 1 del orden de implementación (delta, no absoluto).
- [ ] `./.venv/Scripts/python.exe -m pytest tests/test_harness_ratchet_meta.py tests/test_plan259_ratchet_script_parity.py -q` → **0 failed**.
- [ ] `cd frontend && npx vitest run src/docs/__tests__/documenterModel.test.ts` → verde.
- [ ] `cd frontend && npx vitest run src/docs/__tests__/docTreeModel.test.ts` → verde.
- [ ] `cd frontend && npx tsc --noEmit` → **0 errores**.
- [ ] Las **7 flags nuevas** tienen sus 7 patas completas y **cada una tiene al menos un consumidor de producción** (congelado por `test_r285_las_flags_del_285_tienen_consumidor_de_produccion`).
- [ ] `grep -n "from api\|import api" backend/services/doc_*.py` → **0 líneas** (`services/` no importa de `api/`).
- [ ] `grep -rn "doc_class\|docClass" frontend/src/ | wc -l` → **`>= 8`** (hoy 2).
- [ ] `grep -n "ticket_mining" backend/services/doc_documenter.py` → **`>= 1`** (hoy 0).
- [ ] `SELECT COUNT(*) FROM docs_index` sobre `backend/data/stacky_agents.db` **no creció** por correr la suite.
- [ ] `deployment/harness_defaults.env` regenerado con el generador (no editado a mano).
- [ ] Ningún `git stash`, `reset`, `checkout --`, `amend` ni `rebase` fue ejecutado; todos los commits llevan pathspec explícito.
- [ ] **Smoke manual del operador** (human-in-the-loop, el paso que el 284 dejó pendiente): lanzar el Documentador desde la UI con una nota extra, y confirmar que ve — en una sola pantalla — el estado del corpus, la cobertura, los archivos rechazados con motivo, y los tickets descartados con su razón.

---

## 11. Nota de honestidad sobre este plan

Este documento **no propone re-hacer el 284**. Cinco de sus siete ejes fueron medidos y están completos; están enumerados en la sección 7 con la evidencia de por qué no se tocan. Lo que el 285 agrega es exactamente lo que la medición encontró roto: un corpus muerto, dos gates con el cuantificador equivocado, un triage invisible, un contexto que llega a un solo modo y un árbol que ignora su propia clasificación.

Si al implementarlo alguna afirmación de la sección 3 no se reproduce, **el implementador debe detenerse y reportarlo antes de codificar**. Un plan anclado en una foto vieja del repo es peor que no tener plan.
