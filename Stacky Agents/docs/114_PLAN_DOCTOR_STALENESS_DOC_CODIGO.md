# Plan 114 — Doctor de staleness doc↔código (detecta notas desactualizadas y encola su corrección al Documentador)

> **Estado:** IMPLEMENTADO — 2026-07-10 (F0..F5 verdes; ver memoria `plan-114-status`)
> **Estado previo:** CRITICADO v2 — 2026-07-09 (v1 → v2 por `criticar-y-mejorar-plan`)
> **Veredicto del juez:** APROBADO-CON-CAMBIOS (C1-C4 IMPORTANTES resueltos en esta v2; sin bloqueantes)
>
> **CHANGELOG v1 → v2:**
> - **C1 (IMPORTANTE):** `annotate_staleness` mutaba el dict CACHEADO del plan 109 (build_graph devuelve el objeto en cache): una request con flag ON contaminaba la cache y la siguiente con flag OFF servía los campos `stale` igual — rompía el golden byte-idéntico. Ahora el wiring hace `copy.deepcopy(graph)` antes de anotar + test `test_cache_not_polluted_after_annotation`.
> - **C2 (IMPORTANTE):** el path de la nota que se pasaba a git era `node.path` (relativo a la FUENTE), no relativo al repo → `git log` devolvía None para toda nota dentro de `docs/` y el detector quedaba muerto (el KPI central fallaba). Ahora el path git de la nota se construye con `graph["sources"]`: `posixpath.normpath(posixpath.join(source.relative_path, node.path))` por `source_id`.
> - **C3 (IMPORTANTE):** N subprocesos `git log` por REQUEST sin tope (la anotación corre después del cache del 109, no dentro): cache propio en `doc_staleness` con TTL 60 s por `(repo_root, rel_path)` + tope duro `_MAX_GIT_LOOKUPS = 500` por anotación (excedente → `stale=False` + warning único).
> - **C4 (IMPORTANTE):** contradicción contrato/pseudocódigo: §4 dice `stale` "solo en aristas `code_ref`" pero el código lo agregaba a TODAS las aristas. v2: las aristas no-`code_ref` NO ganan el campo (test renombrado `test_non_code_ref_edges_have_no_stale_field`).
> - **C5 (MENOR):** el `max(git, frontmatter 'updated')` del docstring no estaba implementado: v2 lo elimina — la señal es SOLO git (objetiva); frontmatter `updated` declarado fuera de scope.
> - **C6 (MENOR):** helper `graph_node_path` sin definir → definido literal: `code_id[len("code:"):]`.
> - **C7 (MENOR):** el `runtime` del endpoint `fix` no estaba especificado → mismo default/selección que el `run` del 113.
> - **[ADICIÓN ARQUITECTO]:** bloque aditivo `stale_stats: {stale_edges, stale_notes}` en el payload anotado + fila "Notas desactualizadas" en la pestaña Cobertura (109 F5) cuando el campo está presente — el operador ve el problema sin abrir el grafo. +1 test.
> **Serie:** Documentación agéntica Obsidian (109 → 111 → 112 → 113 → **114**). El número 110 quedó tomado por un plan ajeno (Revisor de PRs).
> **Pipeline:** este documento pasó `proponer` (este estado). Sigue `criticar-y-mejorar-plan` → `implementar-plan-stacky` → `supervisar-implementaciones-planes`.
> **Depende de:** Plan 109 (aristas `code_ref` nota→código en el payload §4.1). **Se integra con** Plan 111 (el Graph View ya pinta aristas `stale` punteadas rojas si vienen en el payload) y Plan 113 (encola el modo `ACTUALIZAR` del Documentador sobre una sola nota).

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** Una nota puede quedar **desactualizada** cuando el código que describe cambia después de la última edición de la nota. Hoy nada lo detecta. Este plan agrega, detrás de una flag OFF por default, un **doctor de staleness**: para cada arista `code_ref` (nota → archivo de código) del grafo (plan 109), compara la fecha del **último commit git del archivo de código** contra la fecha de la **nota** (último commit de la nota o su `updated:` de frontmatter, lo más reciente); si el código es más nuevo, marca esa **arista como `stale`** en el payload del grafo (que el Graph View del plan 111 ya sabe pintar punteada roja) y la **nota con un chip de advertencia**. Ofrece la acción **"Proponer actualización"** que encola el modo `ACTUALIZAR` del Documentador (plan 113) **solo sobre esa nota**. El diagnóstico se **integra al 1-click** del Documentador como un modo automático más cuando hay notas stale.

**KPI / impacto esperado.**
- **Detección real (binario):** en un repo de prueba donde se toca un archivo de código después de la nota que lo referencia, la arista correspondiente sale `stale=true`; si se toca la nota después, sale `stale=false`.
- **Cero regresión:** con `STACKY_DOCS_STALENESS_ENABLED` OFF, el payload de `/api/docs/graph` es byte-idéntico al del plan 109 (sin campos `stale`), y el Graph View se ve igual.
- **Acción de 1 paso:** desde una nota stale, un click encola la corrección al Documentador (113) acotada a esa nota (no re-documenta todo).
- **Integrado al 1-click:** cuando hay notas stale, el Documentador (113) corre también el modo `ACTUALIZAR` sin que el operador lo pida.

---

## 2. Por qué ahora / gap que cierra

1. El plan 109 ya tiene las aristas `code_ref` (nota→código) y el 111 **ya reserva** el render de aristas `stale` (las pinta punteadas rojas si el campo viene). Falta **producir** ese campo — este plan lo hace.
2. El 113 ya tiene el modo `ACTUALIZAR` previsto pero sin disparador; el staleness es su disparador natural y acotado (una nota, no el corpus).
3. Git ya está disponible en el repo del proyecto; la fecha de último commit por archivo es un dato barato y objetivo (mejor señal que mtime del filesystem, que se pierde en checkouts).

---

## 3. Principios y guardarraíles (NO negociables)

- **3 runtimes con paridad total.** Backend puro (git + comparación de fechas). Ningún runtime LLM en la detección. La corrección la hace el Documentador (113) en el runtime seleccionado. Paridad total.
- **Cero trabajo extra + opt-in default OFF.** Flag `STACKY_DOCS_STALENESS_ENABLED` (UI). Sin ella, cero cambios.
- **No degradar.** La consulta git se cachea junto al grafo (cache del 109) y se acota; si git no está o falla, **degrada** a "sin staleness" (campo ausente), nunca rompe el grafo.
- **Human-in-the-loop.** El doctor solo detecta y *ofrece* corrección; el que decide correr el Documentador es el operador (o el 1-click que él dispara). Nada se escribe acá.
- **Aditivo y backward-compatible.** El campo `stale` en aristas y `has_stale` en nodos es ADITIVO; con flag OFF no aparece.
- **Mono-operador sin auth.** Nada de identidad.
- **Sin ambigüedad para modelos menores.** Archivo, símbolo, pseudocódigo, test + comando, criterio binario por fase.

---

## 4. Nombres canónicos (usar EXACTAMENTE estos)

| Concepto | Nombre exacto |
|---|---|
| Flag maestra | `STACKY_DOCS_STALENESS_ENABLED` (bool, default efectivo OFF) |
| Servicio | `backend/services/doc_staleness.py` |
| Fecha git de un archivo | `git_last_commit_epoch(repo_root, rel_path) -> int | None` |
| Anotador del grafo | `annotate_staleness(graph: dict, repo_root: str) -> dict` (agrega `stale` a aristas `code_ref` y `has_stale` a nodos nota) |
| Campo aditivo en arista | `stale: bool` (solo en aristas `kind=="code_ref"`) |
| Campo aditivo en nodo nota | `has_stale: bool` |
| Endpoint acción | `POST /api/docs/staleness/fix` body `{note_path}` → encola Documentador modo `ACTUALIZAR` sobre esa nota |
| Chip frontend | clase `stale-chip` en `DocViewer` / panel de backlinks |

---

## 5. Fases

### F0 — Flag `STACKY_DOCS_STALENESS_ENABLED`

**Objetivo (1 frase).** Alta de la flag editable por UI, default OFF. **Valor:** opt-in seguro.

**Archivos:** `backend/config.py` (bool default `"false"`), `backend/services/harness_flags.py` (key en `contexto_memoria` + `FlagSpec` sin `default=`, `requires="STACKY_DOCS_GRAPH_ENABLED"` porque sin grafo no hay aristas), `backend/services/harness_flags_help.py` (1 `PlainHelp`).

**Tests PRIMERO — archivo:** `backend/tests/test_plan114_flag.py`: `test_flag_default_off`, `test_flag_requires_graph`, `test_flag_has_plain_help`. Registrar en ambos scripts del arnés.

**Comando:** `venv/Scripts/python.exe -m pytest tests/test_plan114_flag.py tests/test_harness_flags.py tests/test_harness_flags_requires.py -q`

**Criterio BINARIO:** verdes. **Trabajo del operador:** ninguno.

---

### F1 — `git_last_commit_epoch` + `annotate_staleness`

**Objetivo (1 frase).** Calcular la fecha git de cada archivo y marcar aristas/nodos stale, con degradación segura. **Valor:** el núcleo del doctor.

**Archivo a crear:** `backend/services/doc_staleness.py`.

**Pseudocódigo EXACTO:**
```python
import posixpath
import subprocess
import time

_MAX_GIT_LOOKUPS = 500       # (C3) tope duro de consultas git por anotación
_EPOCH_TTL_SECONDS = 60      # (C3) cache de epochs entre requests (mismo TTL que el grafo 109)
# cache módulo: (repo_root, rel_path) -> (cached_at_monotonic, epoch | None)
_epoch_cache: dict[tuple[str, str], tuple[float, int | None]] = {}


def git_last_commit_epoch(repo_root: str, rel_path: str) -> int | None:
    """Epoch (int) del último commit que tocó rel_path, o None si no es git / no existe / error.
    Comando: git -C <repo_root> log -1 --format=%ct -- <rel_path>. Timeout 5 s.
    (C3) Cachea el resultado _EPOCH_TTL_SECONDS por (repo_root, rel_path)."""
    key = (repo_root, rel_path)
    hit = _epoch_cache.get(key)
    if hit and time.monotonic() - hit[0] < _EPOCH_TTL_SECONDS:
        return hit[1]
    try:
        out = subprocess.run(
            ["git", "-C", repo_root, "log", "-1", "--format=%ct", "--", rel_path],
            capture_output=True, text=True, timeout=5)
        s = (out.stdout or "").strip()
        epoch = int(s) if s.isdigit() else None
    except Exception:
        epoch = None
    _epoch_cache[key] = (time.monotonic(), epoch)
    return epoch


def _note_repo_path(node: dict, sources_by_id: dict[str, dict]) -> str | None:
    """(C2) Path de la nota RELATIVO AL REPO: node.path es relativo a su FUENTE,
    hay que anteponer source.relative_path (de graph['sources']).
    relative_path == '.' → node.path directo. Fuente desconocida → None."""
    src = sources_by_id.get(node.get("source_id", ""))
    if not src:
        return None
    rel = str(src.get("relative_path") or ".")
    p = node["path"] if rel in (".", "") else posixpath.join(rel, node["path"])
    return posixpath.normpath(p)


def annotate_staleness(graph: dict, repo_root: str) -> dict:
    """Agrega 'stale' SOLO a aristas code_ref (C4) y 'has_stale' a nodos nota,
    más 'stale_stats' [ADICIÓN ARQUITECTO]. Determinístico. NUNCA lanza.
    Regla: arista (nota -> code) es stale si epoch_git(code) > epoch_git(nota),
    ambos no-None. (C5) La señal es SOLO git: el 'updated' de frontmatter queda
    fuera de scope. Si falta cualquiera de los dos epochs -> stale=False.
    IMPORTANTE (C1): el CALLER pasa una COPIA del grafo (deepcopy en el wiring);
    esta función asume que puede mutar su argumento."""
    lookups = 0
    def ep(rel):
        nonlocal lookups
        if lookups >= _MAX_GIT_LOOKUPS:   # (C3) excedente: no se puede afirmar nada
            return None
        lookups += 1
        return git_last_commit_epoch(repo_root, rel)

    sources_by_id = {s["id"]: s for s in graph.get("sources", [])}
    notes_by_id = {n["id"]: n for n in graph.get("nodes", []) if n.get("kind") == "note"}
    note_epoch: dict[str, int | None] = {}
    stale_notes: set[str] = set()
    stale_edges = 0
    for e in graph.get("edges", []):
        if e.get("kind") != "code_ref":
            continue                       # (C4) las demás aristas NO ganan el campo
        note_id, code_id = e["source"], e["target"]
        code_path = code_id[len("code:"):] if str(code_id).startswith("code:") else None  # (C6)
        ce = ep(code_path) if code_path else None
        if note_id not in note_epoch:
            node = notes_by_id.get(note_id)
            npath = _note_repo_path(node, sources_by_id) if node else None
            note_epoch[note_id] = ep(npath) if npath else None
        ne = note_epoch[note_id]
        e["stale"] = bool(ce is not None and ne is not None and ce > ne)
        if e["stale"]:
            stale_notes.add(note_id); stale_edges += 1
    for n in graph.get("nodes", []):
        if n.get("kind") == "note":
            n["has_stale"] = n["id"] in stale_notes
    graph["stale_stats"] = {"stale_edges": stale_edges, "stale_notes": len(stale_notes)}  # [ADICIÓN ARQUITECTO]
    return graph
```

**Wiring (C1 — copia obligatoria):** en `api/docs.py` `get_docs_graph()` (plan 109 F4), tras `build_graph`, si `STACKY_DOCS_STALENESS_ENABLED`:
```python
import copy
graph = copy.deepcopy(graph)   # (C1) build_graph devuelve el objeto CACHEADO del 109;
                               # anotar sin copiar contaminaría la cache y una request
                               # posterior con flag OFF serviría los campos stale.
graph = doc_staleness.annotate_staleness(graph, repo_root)
```
donde `repo_root` = workspace del proyecto/STACKY_AGENTS_ROOT. Con flag OFF, NO se llama (payload byte-idéntico al 109).

**Tests PRIMERO — archivo:** `backend/tests/test_plan114_staleness.py` (repo git real en `tmp_path`; commitear nota y código en orden controlado con `GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE` para fechas deterministas):
- `test_code_newer_than_note_is_stale`.
- `test_note_newer_than_code_not_stale`.
- `test_missing_epoch_is_not_stale`.
- `test_non_code_ref_edges_have_no_stale_field` **(C4)** — las aristas `md`/`wikilink` NO tienen la key `stale`.
- `test_node_has_stale_reflects_edges`.
- `test_degrades_on_non_git` (repo_root sin git → todas las aristas `code_ref` con `stale=False`, sin excepción).
- **(C2)** `test_note_path_resolved_via_source_relative_path` — nota con fuente `relative_path="docs"` y `node.path="a.md"` → el epoch se consulta con `docs/a.md` (espiar los rel_path pasados a `git_last_commit_epoch`).
- **(C3)** `test_lookup_cap_respected` — con `_MAX_GIT_LOOKUPS` monkeypatcheado a 1, la segunda consulta no ejecuta subprocess y las aristas restantes quedan `stale=False`.
- **[ADICIÓN ARQUITECTO]** `test_stale_stats_counts` — `stale_stats == {"stale_edges": N, "stale_notes": M}` coherente con las marcas.

**Comando:** `venv/Scripts/python.exe -m pytest tests/test_plan114_staleness.py -q`

**Criterio BINARIO:** 9/9 verdes.

**Flag/default:** anotación solo con flag ON. **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

### F2 — No-regresión del payload + endpoint de grafo condicional

**Objetivo (1 frase).** Garantizar que con flag OFF el grafo es byte-idéntico al 109 y con flag ON gana los campos aditivos. **Valor:** cero regresión demostrada.

**Archivo a editar:** `backend/api/docs.py` (el wiring de F1) + test.

**Tests PRIMERO — archivo:** `backend/tests/test_plan114_graph_payload.py` (app+client):
- `test_graph_payload_identical_when_staleness_off` (golden: sin `stale`/`has_stale`/`stale_stats`).
- `test_graph_payload_has_stale_fields_when_on` (con repo git de prueba mockeado/real).
- **(C1)** `test_cache_not_polluted_after_annotation` — request con flag ON (payload anotado) seguida de request con flag OFF → la segunda NO contiene `stale`/`has_stale`/`stale_stats` (la cache del 109 quedó limpia).

**Comando:** `venv/Scripts/python.exe -m pytest tests/test_plan114_graph_payload.py -q`

**Criterio BINARIO:** 3/3 verdes.

**Flag/default:** OFF → byte-idéntico 109. **Trabajo del operador:** ninguno.

---

### F3 — Endpoint `POST /api/docs/staleness/fix` (encola Documentador ACTUALIZAR)

**Objetivo (1 frase).** Desde una nota stale, encolar el modo `ACTUALIZAR` del Documentador (plan 113) acotado a esa nota. **Valor:** corrección de 1 paso.

**Archivo a editar:** `backend/api/docs.py`.

**Diseño EXACTO:** `POST /api/docs/staleness/fix` body `{note_path}` → 404 si `STACKY_DOCS_STALENESS_ENABLED` OFF **o** `STACKY_DOCS_DOCUMENTER_ENABLED` OFF (necesita el 113). Llama a un helper del orquestador 113: `doc_documenter.run_documenter(project_name, runtime, only_note=note_path, forced_modes=[ACTUALIZAR])` (extender la firma del 113 con `only_note`/`forced_modes` opcionales, backward-compatible). **(C7)** `runtime` = el MISMO valor/selección default que usa `POST /api/docs/documenter/run` del 113 (no se pide en el body). Devuelve `{run_id}` (y hereda el 409 `documenter_busy` del 113 si hay un run activo).

> **Dependencia dura:** si el plan 113 aún no está implementado, esta fase queda detrás de su flag y el endpoint responde 404 (no rompe). El resto del plan (F0-F2, detección y visual) funciona sin 113.

**Tests PRIMERO — archivo:** `backend/tests/test_plan114_fix_endpoint.py`:
- `test_fix_404_when_staleness_off`.
- `test_fix_404_when_documenter_off`.
- `test_fix_enqueues_actualizar_for_single_note` (orquestador 113 mockeado; verificar `only_note`/`forced_modes`).

**Comando:** `venv/Scripts/python.exe -m pytest tests/test_plan114_fix_endpoint.py -q`

**Criterio BINARIO:** 3/3 verdes.

**Flag/default:** doble gate (staleness + documenter). **Impacto por runtime:** la corrección corre en el runtime seleccionado (113). **Trabajo del operador:** 1 click.

---

### F4 — Frontend: chip de advertencia + acción "Proponer actualización"

**Objetivo (1 frase).** Mostrar el estado stale en la nota (chip) y ofrecer el botón de corrección; el Graph View del 111 ya pinta las aristas. **Valor:** la señal visible + acción.

**Archivos:**
1. `frontend/src/api/endpoints.ts` — `Docs.stalenessFix(notePath)`.
2. `frontend/src/components/DocViewer.tsx` (o el panel de backlinks del 111) — si el nodo de la nota abierta tiene `has_stale`, mostrar chip `stale-chip` ("⚠ referencia código que cambió") + botón "Proponer actualización" → `stalenessFix`. Solo con `graph_enabled` y `staleness_enabled` (key aditiva en `/api/docs/sources`).
3. El Graph View (plan 111) ya consume `edge.stale`; no requiere cambios salvo confirmar tolerancia del campo.
4. **[ADICIÓN ARQUITECTO]** `DocCoveragePanel` (109 F5): si el payload trae `stale_stats`, agregar la fila "Notas desactualizadas" a la tabla de métricas (valor `stale_stats.stale_notes`); si el campo no viene (flag OFF), la fila no se renderiza.

**Tests PRIMERO — archivo:** `frontend/src/docs/staleness.test.ts` (modelo puro):
- `noteIsStale_reads_has_stale`.
- `staleEdges_filter`.
- **[ADICIÓN ARQUITECTO]** `coverage_summary_includes_stale_notes_when_present` (extender `summarizeGraph` del 109 para propagar `stale_stats` opcional; ausente → undefined, sin lanzar).

> Disclosure entorno (plan 107): `.test.tsx` bloqueado; criterio = modelo puro + `tsc --noEmit` + verificación manual.

**Comando (desde `Stacky Agents/frontend`):** `npx vitest run src/docs/staleness.test.ts && npx tsc --noEmit`

**Criterio BINARIO:** verdes + tsc 0 errores. Con flag OFF: sin chip ni botón.

**Flag/default:** `STACKY_DOCS_STALENESS_ENABLED` OFF → nada. **Trabajo del operador:** 1 click (opcional).

---

### F5 — Integración al 1-click del Documentador + cierre

**Objetivo (1 frase).** Que el 1-click del 113 corra también `ACTUALIZAR` cuando hay notas stale, y sellar el plan.

**Cambios:**
1. En `doc_documenter.plan_documenter_run` (plan 113 F1): si `STACKY_DOCS_STALENESS_ENABLED` y el grafo anotado tiene `has_stale` en alguna nota, **agregar `ACTUALIZAR`** a `modes` (antes de `ENRIQUECER`) con la lista de notas stale como target. (Cambio aditivo; con la flag OFF el comportamiento del 113 no cambia.)
2. Registrar los archivos de test nuevos en `run_harness_tests.sh` y `.ps1`.
3. No-regresión backend + frontend (comandos de F1-F4).

**Criterio BINARIO global (DoD):**
- [ ] Todas las suites de F0-F4 verdes; `tsc --noEmit` 0 errores.
- [ ] Con `STACKY_DOCS_STALENESS_ENABLED` OFF: `/api/docs/graph` byte-idéntico al 109; sin chip; sin endpoint (404).
- [ ] Con flag ON: aristas `code_ref` ganan `stale` correcto (git), nodos nota ganan `has_stale`; el Graph View las pinta punteadas rojas.
- [ ] "Proponer actualización" encola el Documentador (113) modo `ACTUALIZAR` acotado a una nota.
- [ ] El 1-click del 113 incorpora `ACTUALIZAR` cuando hay notas stale (con la flag ON).
- [ ] Degradación segura sin git.

---

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Falsos positivos por fechas de commit engañosas (rebase, squash). | Señal git de último commit es la mejor disponible; el resultado es una *sugerencia* (chip), no una acción automática; el operador decide. |
| Costo de `git log` por archivo en grafos grandes (la anotación corre por request, DESPUÉS del cache del 109 — C3). | Cache de epochs en `doc_staleness` con TTL 60 s por `(repo_root, rel_path)` + tope duro `_MAX_GIT_LOOKUPS=500` por anotación; timeout 5 s; solo aristas `code_ref`. |
| Contaminar la cache del grafo 109 al anotar (C1). | `copy.deepcopy` obligatorio en el wiring antes de anotar + test `test_cache_not_polluted_after_annotation`. |
| Repo no-git o shallow clone sin historia. | `git_last_commit_epoch` devuelve None → `stale=False`; degradación total sin excepción. |
| Acoplamiento al plan 113 no implementado. | F3/F5 detrás de doble gate; si 113 no está, endpoint 404 y el resto (detección/visual) funciona igual. |
| Drift del payload que confunda al 111. | Campos ADITIVOS `stale`/`has_stale`; el 111 ya los tolera ausentes; golden de no-regresión (F2). |

---

## 7. Fuera de scope

- Corregir la doc (lo hace el Documentador, plan 113; acá solo se detecta y encola).
- Staleness semántico (que el *contenido* contradiga el código): esto es solo temporal (fechas). El contraste semántico lo cubre el Documentador al ejecutar.
- Watchers de git en tiempo real; la detección es bajo demanda al pedir el grafo.
- Editar `docs/sistema/` (canónicas).

---

## 8. Glosario (términos para modelos menores)

- **Staleness:** que una nota quedó vieja respecto al código que describe.
- **Arista `code_ref`:** enlace nota→archivo de código en el grafo (plan 109).
- **Epoch git:** timestamp Unix del último commit que tocó un archivo (`git log -1 --format=%ct`).
- **`has_stale`:** flag en un nodo nota que indica que al menos una de sus referencias a código es más nueva que la nota.
- **Modo `ACTUALIZAR`:** trabajo del Documentador (plan 113) que corrige una nota desactualizada.
- **Degradación segura:** ante ausencia de git, no marcar nada stale en vez de fallar.
- **venv del repo:** `Stacky Agents/backend/venv` (Python 3.13); pytest por archivo.

---

## 9. Orden de implementación (secuencial)

1. **F0** — flag.
2. **F1** — `git_last_commit_epoch` + `annotate_staleness` + 6 tests.
3. **F2** — no-regresión del payload + wiring condicional + 2 tests.
4. **F3** — endpoint `staleness/fix` (encola 113) + 3 tests.
5. **F4** — chip + acción en frontend + modelo puro.
6. **F5** — integración al 1-click del 113 + cierre.

---

## 10. Definición de Hecho (DoD) — resumen binario

Hecho cuando: (a) las suites de F0-F4 están verdes y `tsc --noEmit` da 0 errores; (b) con la flag OFF el grafo es byte-idéntico al 109 y no hay chip ni endpoint; (c) con la flag ON las aristas `code_ref` tienen `stale` correcto por git y los nodos nota `has_stale`, y el Graph View del 111 las pinta punteadas rojas; (d) "Proponer actualización" encola el Documentador (113) en modo `ACTUALIZAR` acotado a una nota; (e) el 1-click del 113 corre `ACTUALIZAR` cuando hay notas stale; (f) todo degrada de forma segura si no hay git.
