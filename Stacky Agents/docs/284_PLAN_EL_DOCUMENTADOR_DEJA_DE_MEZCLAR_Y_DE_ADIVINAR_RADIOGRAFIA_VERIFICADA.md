# 284 — EL DOCUMENTADOR DEJA DE MEZCLAR Y DE ADIVINAR: FRONTERA PLANES/PROYECTO, NOTA DEL OPERADOR, PIPELINE DE 5 ETAPAS Y RADIOGRAFÍA VERIFICADA

**Estado:** PROPUESTO (v1, sin criticar) — 2026-08-01
**Autor:** StackyArchitectaUltraEficientCode
**Depende de:** 113 (Documentador 1-click), 114 (staleness), 137 (Documentador V2: evidencia + citas + historial), 109 (grafo documental), 268 (Explorador del grafo)
**NO re-propone nada de 137 ni de 268.** La sección "Qué YA está construido" lo delimita archivo:línea.

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
| KPI-5 | Tickets barridos por el Documentador | 0 de 228 | 228 (162 ADO + 63 GitLab + 3 demo), con veredicto `signal`/`noise` por ticket |
| KPI-6 | Etapas del run con estado persistido y veredicto | 0 (hay `current_mode`, no etapas) | 5 de 5 |
| KPI-7 | Runs que terminan sin veredicto explícito | 100% | 0% |

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
| 113 | Selector determinista de modos, gate git con worktree aislado, aplicador determinista, anti-traversal, `docs/sistema/` read-only, lock de un run activo | `doc_documenter.py:115`, `:468`, `:563`, `:547`, `:558`, `:623` |
| 137 F1 | Evidencia real de módulo (árbol + símbolos con línea) | `doc_evidence.build_module_evidence` `doc_evidence.py:50` |
| 137 F2 | Verificador de citas (extracción + validación contra filesystem) | `doc_evidence.verify_citations` `doc_evidence.py:139` |
| 137 F3 | Short-circuit de modos sin targets | `should_invoke_mode` `doc_documenter.py:262` |
| 137 F4 | Historial persistente de corridas + fallback a disco | `_persist_run_report` `doc_documenter.py:758`, `list_runs` `:778` |
| 137 F5/F6 | Preview por archivo + panel de revisión | `doc_documenter.py:603-608`, `DocumenterResultPanel.tsx` |
| 268 | Explorador del grafo: filtros, búsqueda, zoom, foco, agrupación, peek, minimapa | `frontend/src/docs/docGraphModel.ts`, `forceLayout.ts` |
| 109 | Grafo documental + `classify_doc_health` | `doc_graph.build_graph` `doc_graph.py:179`, `:424` |

**Corrección de un supuesto circulante:** no existe ningún `docs/rag/rag_corpus.jsonl`. El corpus RAG se persiste en la tabla SQLite `docs_index` (`DocChunk.__tablename__`, `docs_rag.py:70-71`). Y el "grafo con tickets" del plan 276 es la vista jerárquica épica→hijos de `GET /hierarchy` (`api/tickets.py:735-736`), **no** el grafo documental. Cualquier fase que asuma lo contrario está mal.

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

| Flag | Tipo | Default | Justificación |
|---|---|---|---|
| `STACKY_DOCS_TAXONOMY_ENABLED` | bool | **ON** | Clasificar un path es solo lectura y cálculo puro. No es excepción. |
| `STACKY_DOCS_OPERATOR_NOTE_ENABLED` | bool | **ON** | Campo de texto opcional que el operador llena on-demand. Vacío ⇒ comportamiento actual. No quema tokens en reposo. |
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
2. **FlagSpec** — agregar 9 specs siguiendo el patrón de `harness_flags.py:2682-2760`. Reglas exactas:
   - Las 7 booleanas ON llevan `default=True` **y** el comentario `# curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated)`.
   - **Las 7 booleanas ON deben además agregarse a la lista `_CURATED_DEFAULTS_ON`.** Sin esto, `test_default_known_only_for_curated` se pone rojo. Buscá `_CURATED_DEFAULTS_ON` en `harness_flags.py` y sumá las 7 claves.
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
- En `launch` (`DocumenterButton.tsx:47`), cambiar la llamada de `DocumenterButton.tsx:52` a `Docs.documenterRun(projectName, note.trim() || undefined)` y agregar `note` a las deps del `useCallback` (`DocumenterButton.tsx:63`).
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
_SYNTHETIC_ADO_IDS = frozenset({-7})   # doc_documenter._CONVERSATION_ADO_ID


@dataclass
class TicketVerdict:
    ticket_id: int
    external_id: int | None
    tracker_type: str
    title: str
    verdict: str            # "signal" | "noise"
    reasons: list[str] = field(default_factory=list)
    score: int = 0


def classify_ticket(*, ticket_id: int, external_id: int | None, tracker_type: str,
                    title: str, description: str, ado_state: str,
                    work_item_type: str) -> TicketVerdict:
    """Veredicto determinista de un ticket. PURA, sin I/O. Nunca lanza.

    Puntuación (suma de enteros; >= 2 => "signal"):
      +2  len(description) >= STRONG_SIGNAL_CHARS
      +1  len(description) >= MIN_DESCRIPTION_CHARS
      +1  len(title.strip()) >= MIN_TITLE_CHARS
      +1  work_item_type no vacío y distinto de "Task"  (épicas/features documentan mejor)
      -3  tracker_type en _SYNTHETIC_TRACKERS
      -3  ado_id sintético (external_id in _SYNTHETIC_ADO_IDS)
      -2  el título matchea _NOISE_TITLE_RE
      -2  description vacía

    `reasons` guarda un string por regla aplicada (auditoría: el operador puede
    leer POR QUÉ un ticket quedó afuera).
    """
    reasons: list[str] = []
    score = 0
    desc = (description or "").strip()
    ttl = (title or "").strip()

    if len(desc) >= STRONG_SIGNAL_CHARS:
        score += 2; reasons.append(f"descripcion_extensa:{len(desc)}")
    if len(desc) >= MIN_DESCRIPTION_CHARS:
        score += 1; reasons.append(f"descripcion_suficiente:{len(desc)}")
    if len(ttl) >= MIN_TITLE_CHARS:
        score += 1; reasons.append(f"titulo_descriptivo:{len(ttl)}")
    wit = (work_item_type or "").strip()
    if wit and wit.lower() != "task":
        score += 1; reasons.append(f"tipo_jerarquico:{wit}")
    if (tracker_type or "").strip().lower() in _SYNTHETIC_TRACKERS:
        score -= 3; reasons.append("tracker_sintetico")
    if external_id in _SYNTHETIC_ADO_IDS:
        score -= 3; reasons.append("ticket_interno_de_stacky")
    if _NOISE_TITLE_RE.match(ttl):
        score -= 2; reasons.append("titulo_ruido")
    if not desc:
        score -= 2; reasons.append("sin_descripcion")

    verdict = "signal" if score >= 2 else "noise"
    return TicketVerdict(ticket_id=ticket_id, external_id=external_id,
                         tracker_type=(tracker_type or ""), title=ttl,
                         verdict=verdict, reasons=reasons, score=score)


def mine_project_tickets(project_name: str, *, max_tickets: int | None = None
                         ) -> dict:
    """Barre los tickets del proyecto y devuelve el resumen del triage.

    Salida (forma GARANTIZADA, todas las claves siempre presentes):
      {"enabled": bool, "total": int, "signal": int, "noise": int,
       "by_tracker": {tracker: int}, "verdicts": [TicketVerdict...],
       "truncated": bool}

    Con la flag OFF devuelve la forma completa con enabled=False y ceros.
    Nunca lanza: ante error de DB loguea y devuelve la forma vacía.
    """
    from config import config as _cfg
    empty = {"enabled": False, "total": 0, "signal": 0, "noise": 0,
             "by_tracker": {}, "verdicts": [], "truncated": False}
    if not bool(getattr(_cfg, "STACKY_DOCS_TICKET_MINING_ENABLED", False)):
        return empty
    cap = int(max_tickets if max_tickets is not None
              else getattr(_cfg, "STACKY_DOCS_TICKET_MINING_MAX", 500))
    try:
        from db import session_scope
        from models import Ticket
        verdicts: list[TicketVerdict] = []
        by_tracker: dict[str, int] = {}
        with session_scope() as session:
            q = (session.query(Ticket)
                 .filter(Ticket.stacky_project_name == project_name)
                 .order_by(Ticket.id))
            total_rows = q.count()
            for t in q.limit(cap).all():
                v = classify_ticket(
                    ticket_id=t.id, external_id=t.external_id,
                    tracker_type=t.tracker_type or "", title=t.title or "",
                    description=t.description or "", ado_state=t.ado_state or "",
                    work_item_type=t.work_item_type or "")
                verdicts.append(v)
                key = v.tracker_type or "desconocido"
                by_tracker[key] = by_tracker.get(key, 0) + 1
        signal = sum(1 for v in verdicts if v.verdict == "signal")
        return {"enabled": True, "total": len(verdicts), "signal": signal,
                "noise": len(verdicts) - signal, "by_tracker": by_tracker,
                "verdicts": verdicts, "truncated": total_rows > cap}
    except Exception as exc:
        logger.warning("doc_ticket_mining: barrido fallo para %s: %s", project_name, exc)
        return dict(empty, enabled=True)


def build_tickets_context_block(mining: dict, *, max_chars: int = 12000) -> dict | None:
    """Context block con SOLO los tickets 'signal'. None si no hay ninguno.

    Cada línea: "[<tracker>#<external_id>] <título> — <motivos>". El bloque se
    trunca a max_chars con el sufijo "\\n[...corpus truncado]" (mismo patrón que
    doc_evidence.build_module_evidence)."""
    ...
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

- `test_plan284_classify_ticket_tabla` — tabla con 8 casos y el score exacto esperado:
  - Ticket real ADO con 1200 chars de descripción, título de 40 chars, tipo `"Epic"` → `signal`, score 5.
  - Ticket con descripción de 250 chars y título de 20 → `signal`, score 2 (frontera exacta).
  - Ticket con descripción de 199 chars y título de 20 → `noise`, score 1 (frontera del otro lado).
  - Ticket con descripción vacía → `noise`, y `"sin_descripcion" in reasons`.
  - Ticket `tracker_type="demo"` con descripción larga → `noise` (score 3-3=0), y `"tracker_sintetico" in reasons`.
  - Ticket con `external_id=-7` → `noise`, y `"ticket_interno_de_stacky" in reasons`.
  - Ticket con título `"test"` → `noise`, y `"titulo_ruido" in reasons`.
  - Ticket GitLab (`tracker_type="gitlab"`) con descripción larga → `signal` (**prueba de que el triage es multiproveedor y no favorece a ADO**).
- `test_plan284_mine_project_tickets_forma_garantizada` — con la flag OFF, el dict tiene **las 7 claves** con `enabled=False` (presencia de la forma + ausencia de datos en el mismo test).
- `test_plan284_build_tickets_block_solo_signal` — con un mining de 2 signal + 3 noise, el `content` del bloque **contiene** los títulos de los 2 signal y **no contiene** los de los 3 noise.

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests/test_documenter_v2_pipeline.py -q
```

**Criterio de aceptación binario:** `0 failed`, y este censo sobre la base viva (**read-only, `mode=ro`**) imprime un total de **228** y una partición `signal + noise == 228`:

```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -c "
import sqlite3
from services.doc_ticket_mining import classify_ticket
p=r'N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\data\stacky_agents.db'
c=sqlite3.connect('file:'+p+'?mode=ro',uri=True)
rows=c.execute('select id,external_id,tracker_type,title,description,ado_state,work_item_type from tickets').fetchall()
vs=[classify_ticket(ticket_id=r[0],external_id=r[1],tracker_type=r[2] or '',title=r[3] or '',description=r[4] or '',ado_state=r[5] or '',work_item_type=r[6] or '') for r in rows]
s=sum(1 for v in vs if v.verdict=='signal')
print('total',len(vs),'signal',s,'noise',len(vs)-s)
c.close()"
```

> **Nunca corras pytest suelto contra la base viva:** un pytest sin `DATABASE_URL` en memoria escribe en la BD real. Los tests de esta fase usan `sqlite:///:memory:` (ya seteado en `test_documenter_v2_pipeline.py:9`). El comando de censo de arriba abre la base con `mode=ro` y **no** es un test.

**Flag:** `STACKY_DOCS_TICKET_MINING_ENABLED` (default **ON**), `STACKY_DOCS_TICKET_MINING_MAX` (500).
**Runtimes:** barrido SQL local, sin runtime. Idéntico en los 3.
**Trabajo del operador:** ninguno. Los umbrales quedan editables por UI como flags si algún día molestan.

---

### F5 — Pipeline interno de 5 etapas con veredicto (cierra el punto 4 del pedido)

**Objetivo:** que el Documentador deje de ser un one-shot y corra **PROPONER → CRITICAR → MEJORAR → IMPLEMENTAR → VERIFICAR**, con estado persistido por etapa y confirmación humana antes de escribir.
**Valor:** el rigor deja de depender de que el modelo tenga un buen día.

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

`_run_paper_stage(stage, project_name, runtime, operator_note, prior_artifact) -> StageResult`:
- Arma un `context_blocks` con: el bloque de la nota del operador (F2), el bloque de salud/grafo, el bloque de tickets `signal` (F4) y, si `prior_artifact` no está vacío, un bloque `{"kind": "prior-stage", "title": "<etapa anterior>", "content": prior_artifact}`.
- Invoca vía `invoke_documenter` **con un `system_prompt_override` propio por etapa** (constantes `_STAGE_PROMPT_PROPONER`, `_STAGE_PROMPT_CRITICAR`, `_STAGE_PROMPT_MEJORAR`). Estos prompts NO piden bloques `<<<DOC>>>`: piden texto plano. Por eso `_run_paper_stage` **no** usa `parse_proposals`; lee el output crudo con `_wait_and_read_output`.
- **Corte de costo (obligatorio):** si `PROPONER` devuelve un artefacto vacío o de menos de 200 caracteres, `CRITICAR` y `MEJORAR` se marcan `skipped` con `summary="sin plan que criticar"`. No se gastan 2 invocaciones al pedo.

> **Nota de diseño honesta:** estas 3 etapas cuestan 3 invocaciones extra de LLM por run. Es el precio del rigor que pidió el operador. Está acotado: se pagan **una vez por run**, no por modo, y el corte de arriba las evita cuando no hay nada que criticar. Ver Riesgo R1.

#### F5.3 — IMPLEMENTAR con human-in-the-loop

- Si `STACKY_DOCS_PIPELINE_AUTOAPPLY` está **OFF** (default), al llegar a `IMPLEMENTAR` el run se marca `state="awaiting_approval"`, persiste el reporte con las 3 etapas de papel completas y **se detiene**. El operador lee el plan y la crítica en la UI y aprueba.
- **Endpoint nuevo** en `Stacky Agents/backend/api/docs.py`:

```python
@bp.post("/documenter/stage/approve")
def documenter_stage_approve():
    """Plan 284 — el operador aprueba pasar a IMPLEMENTAR. 404 si el master
    está OFF o si el pipeline de etapas está OFF; 409 si el run no está
    esperando aprobación."""
```
  Body: `{run, approve: true|false}`. Con `approve=false` el run termina en `state="cancelled_by_operator"` y la rama se descarta con `discard_doc_branch`.
- Si `STACKY_DOCS_PIPELINE_AUTOAPPLY` está **ON**, sigue de largo. **Es la única forma de que Stacky escriba documentación sin que el operador diga que sí.**

#### F5.4 — VERIFICAR (determinista, sin LLM)

`_run_verify_stage(result: ApplyResult, workspace_root, project_name) -> StageResult` calcula:
- `citations_total`, `citations_ok`, `files_rejected` (de `result.files`, F3).
- `coverage` (de F6, si `STACKY_DOCS_RADIOGRAPHY_ENABLED` ON).
- Veredicto con reglas EXACTAS:
  - `INSUFICIENTE` si `written == 0` **o** `files_rejected > len(written)`.
  - `RADIOGRAFIA_COMPLETA` si `written > 0` **y** `files_rejected == 0` **y** `coverage_ratio >= 0.8`.
  - `RADIOGRAFIA_PARCIAL` en cualquier otro caso.
- El veredicto va al reporte final como `report["verdict"]` y `report["stages"]`.

**Tests (PRIMERO).** Agregar a `Stacky Agents/backend/tests/test_documenter_v2_pipeline.py`:

- `test_plan284_stage_order_es_el_contrato` — `STAGE_ORDER` tiene exactamente 5 elementos en el orden PROPONER, CRITICAR, MEJORAR, IMPLEMENTAR, VERIFICAR.
- `test_plan284_verdict_tabla` — función pura `compute_verify_verdict(written_count, files_rejected, coverage_ratio)` con la tabla de las 3 reglas, incluyendo las fronteras `coverage_ratio=0.8` (COMPLETA) y `0.79` (PARCIAL).
- **`test_plan284_sin_autoaplicado_el_run_espera_aprobacion`** — con `STACKY_DOCS_PIPELINE_AUTOAPPLY=False`, `STACKY_DOCS_PIPELINE_STAGES_ENABLED=True` y `invoke_documenter` monkeypatcheado para devolver un artefacto de papel válido: el run termina en `state == "awaiting_approval"` (presencia) **y** `result.written == []` — no se escribió ni un archivo (ausencia). Es el test del riel human-in-the-loop.
- `test_plan284_corte_de_costo_sin_plan` — si PROPONER devuelve `""`, las etapas CRITICAR y MEJORAR quedan `state="skipped"` y **`invoke_documenter` fue llamado exactamente 1 vez** (contador en el monkeypatch). Prueba que el corte ahorra de verdad.
- `test_plan284_pipeline_off_es_backward_compatible` — con `STACKY_DOCS_PIPELINE_STAGES_ENABLED=False`, `run_documenter` devuelve un reporte **sin** las claves `stages` ni `verdict`, y con las mismas claves que hoy.

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests/test_documenter_v2_pipeline.py -q
```

**Criterio de aceptación binario:** `0 failed` y el censo del riel HITL devuelve **exactamente 1** (existe un único punto donde el autoaplicado se consulta, y está antes de escribir):

```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
Select-String -Path "services\doc_documenter.py" -Pattern "STACKY_DOCS_PIPELINE_AUTOAPPLY" | Measure-Object | Select-Object -ExpandProperty Count
```

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
    """Cobertura documental. Forma GARANTIZADA (todas las claves siempre):
      {"enabled": bool, "modules_total": int, "modules_covered": int,
       "coverage_ratio": float, "uncovered": [str], "orphan_notes": [str],
       "by_doc_class": {clase: int}}

    - modules_total / modules_covered / uncovered salen de doc_health.uncovered_modules
      (ya calculado por classify_doc_health, doc_graph.py:424) — NO se recalcula.
    - orphan_notes sale de graph["orphans"] (ya calculado por build_graph).
    - by_doc_class usa doc_taxonomy.summarize_classes sobre los paths de las notas.
    - coverage_ratio = modules_covered / modules_total, o 1.0 si modules_total == 0.
    Nunca lanza: ante error devuelve la forma con enabled=True y ceros."""
```

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

**Criterio de aceptación binario:** `0 failed` y este censo devuelve **0** (no se creó un motor de grafo paralelo):

```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
Select-String -Path "services\doc_radiography.py" -Pattern "build_graph|rglob|_enumerate_note_files" | Measure-Object | Select-Object -ExpandProperty Count
```

**Flag:** `STACKY_DOCS_RADIOGRAPHY_ENABLED` (default **ON**).
**Runtimes:** cálculo local. Idéntico en los 3.
**Trabajo del operador:** ninguno.

---

### F7 — La UI se entiende (cierra el punto 1 del pedido)

**Objetivo:** que el panel del Documentador se lea de un vistazo: veredicto arriba, etapas con su estado, archivos agrupados por clase, rechazos con motivo en castellano.
**Valor:** el operador entiende qué pasó sin leer un `diff --stat`.

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
| **R4** | **La nota del operador se usa para intentar aflojar un guardarraíl.** | Bajo | Estructural: el enforcement es determinista en `apply_proposals` (`doc_documenter.py:584-592`), no en el prompt. Aunque el modelo obedezca, `docs/sistema/` sigue bloqueado y el traversal también. Testeado indirectamente por los tests preexistentes del 113. |
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

1. **F0.1** — Registrar las 9 flags (foto del rojo previo ANTES). Correr `tests/test_harness_flags.py` y comparar **delta**.
2. **F0.2** — `doc_taxonomy.py` + sus 2 tests en `test_doc_evidence.py`. Verde.
3. **F1** — `doc_class` en índice, grafo, salud y RAG + `class_summary` en la API. 4 tests en `test_documenter_v2_pipeline.py`. Verde + censo C1..C4 en True.
4. **F2** — Nota del operador: UI → `endpoints.ts` → `api/docs.py` → `doc_documenter` → `_operator_note_block` → `build_context_for_mode`. 4 tests backend + 1 frontend. Verde + censo AST del consumidor = 1.
5. **F3** — Gate de citas: `evaluate_citation_gate` puro primero, después reordenar `apply_proposals`. 3+1 tests. Verde + censo AST de orden write/verify = 0.
6. **F4** — `doc_ticket_mining.py` + cableado en `build_context_for_mode`. 3 tests. Verde + censo sobre la base viva (read-only) = 228.
7. **F5** — Etapas, HITL y endpoint de aprobación. 5 tests. Verde + censo del riel HITL.
8. **F6** — `doc_radiography.py` + claves nuevas en `documenter_status`. 3 tests. Verde + censo de motor paralelo = 0.
9. **F7** — UI: 3 funciones puras en `documenterModel.ts` + panel. 4 tests vitest + `tsc --noEmit`. Verde.
10. **Cierre** — correr los 3 archivos de test backend por separado + vitest + tsc, y anotar el resultado real (pegado, no resumido) en la sección de estado de este documento.

---

## 9. Definición de Hecho (DoD) global

Un implementador puede declarar este plan terminado **sólo si** todo lo siguiente es cierto y está pegado como evidencia:

- [ ] `pytest tests/test_doc_evidence.py -q` → `0 failed`, con **≥ 20** tests (hoy 18).
- [ ] `pytest tests/test_documenter_v2_pipeline.py -q` → `0 failed`, con **≥ 16** tests más que el baseline del archivo.
- [ ] `pytest tests/test_documenter_autonomy.py -q` → `0 failed` (no debe romperse: es el guardián de la autonomía del 113).
- [ ] `pytest tests/test_docs_api.py -q` → `0 failed` (los endpoints tocados).
- [ ] `pytest tests/test_harness_flags.py -q` → **el mismo número de fallos que el baseline capturado en F0.1**, ni uno más. Los 4-5 rojos ajenos son de fábrica; sumar uno nuevo es un defecto de este plan.
- [ ] `npx vitest run src/docs/documenterModel.test.ts` → `0 failed`, con **≥ 5** tests nuevos.
- [ ] `npx tsc --noEmit` → exit 0, sin salida.
- [ ] Los 5 censos por comando de F1, F2, F3, F5 y F6 devuelven exactamente el valor declarado.
- [ ] **Con las 9 flags en su default, el comportamiento del Documentador es el descrito por este plan; con las 8 nuevas ON puestas en OFF y `AUTOAPPLY` en su default, el reporte tiene exactamente las mismas claves que hoy.** (Backward-compat probada por `test_plan284_pipeline_off_es_backward_compatible`.)
- [ ] Ningún archivo de test backend nuevo fue creado (los 3 archivos usados ya están registrados en `run_harness_tests.ps1` **y** `.sh`).
- [ ] Ningún `git add -A`, `git add .`, `git stash`, `git reset` ni `git checkout --` durante la implementación. Commits con pathspec explícito.
- [ ] Sin `git push`.
- [ ] La sección de estado de este documento quedó actualizada con el output real de los comandos, pegado.

---

## 10. Trazabilidad: los 7 pedidos del operador → fases

| # | Pedido textual | Fase | Criterio que lo prueba |
|---|---|---|---|
| 1 | "no se entiende bien" | **F7** (+ F5.4 veredicto) | 4 tests de vitest sobre `buildStagesView`/`buildVerdictView`/`buildRadiographyView` + verificación visual del operador |
| 2 | "se mezclan los planes de los del proyecto" | **F1** | Censo C1..C4 en True (240 `plan` / 15 `system` al 2026-08-01); el RAG excluye planes; la salud los ignora |
| 3 | "que me permita darle una NOTA EXTRA" | **F2** | `render_blocks(build_context_for_mode(...))` contiene el texto sentinela; censo AST del consumidor = 1 |
| 4 | "primero proponer, criticar, mejorar, implementar, verificar" | **F5** | `STAGE_ORDER` de 5; el run se detiene en `awaiting_approval` sin escribir; veredicto en el reporte |
| 5 | "grafo súper complejo que robustezca lo existente, radiografía" | **F6** | `compute_coverage` sobre el grafo del 268 **sin** motor paralelo (censo = 0) |
| 6 | "mirar TODOS los tickets, diferenciar basura de valioso" | **F4** | 228 tickets barridos (162 ADO + 63 GitLab + 3 demo); `classify_ticket` con 8 casos de tabla y motivos auditables |
| 7 | "muy lento y pausado para no alucinar sobre el código" | **F3** (+ F0.2) | El archivo con citas falsas **no existe en disco**; censo AST de orden write/verify = 0 |

---

**Última línea:** este plan **no** re-propone la evidencia de módulo (137 F1), el verificador de citas (137 F2), el short-circuit (137 F3), el historial (137 F4), el preview (137 F5) ni el explorador (268). Los usa. Lo único que hace con ellos es **conectarlos y darles consecuencia**.
