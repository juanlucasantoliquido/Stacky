# Plan 114 — Doctor de staleness doc↔código (detecta notas desactualizadas y encola su corrección al Documentador)

> **Estado:** PROPUESTO v1 — 2026-07-09
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
import subprocess, os

def git_last_commit_epoch(repo_root: str, rel_path: str) -> int | None:
    """Epoch (int) del último commit que tocó rel_path, o None si no es git / no existe / error.
    Comando: git -C <repo_root> log -1 --format=%ct -- <rel_path>. Timeout corto."""
    try:
        out = subprocess.run(
            ["git", "-C", repo_root, "log", "-1", "--format=%ct", "--", rel_path],
            capture_output=True, text=True, timeout=5)
        s = (out.stdout or "").strip()
        return int(s) if s.isdigit() else None
    except Exception:
        return None

def annotate_staleness(graph: dict, repo_root: str) -> dict:
    """Agrega 'stale' a aristas code_ref y 'has_stale' a nodos nota. Determinístico.
    Regla: arista (nota -> code) es stale si epoch(code) > epoch(nota) (ambos no-None).
    epoch(nota) = max(git_last_commit_epoch(nota), frontmatter 'updated' si parsea) — se usa
    el git de la nota (la fecha de frontmatter es opcional y solo sube el umbral).
    Si falta cualquiera de los dos epochs -> stale=False (no se puede afirmar desactualización)."""
    # cache local por archivo para no repetir git en el mismo run
    epoch_cache: dict[str, int | None] = {}
    def ep(rel): 
        if rel not in epoch_cache: epoch_cache[rel] = git_last_commit_epoch(repo_root, rel)
        return epoch_cache[rel]
    note_epoch = {}  # id nota -> epoch
    id_to_path = {n["id"]: n["path"] for n in graph.get("nodes", []) if n.get("kind") == "note"}
    stale_notes: set[str] = set()
    for e in graph.get("edges", []):
        if e.get("kind") != "code_ref":
            e["stale"] = False; continue
        note_id, code_id = e["source"], e["target"]
        code_path = graph_node_path(graph, code_id)   # 'code:<path>' -> '<path>'
        npath = id_to_path.get(note_id)
        ce = ep(code_path) if code_path else None
        ne = note_epoch.get(note_id)
        if ne is None and npath:
            ne = note_epoch[note_id] = ep(npath)
        e["stale"] = bool(ce is not None and ne is not None and ce > ne)
        if e["stale"]: stale_notes.add(note_id)
    for n in graph.get("nodes", []):
        if n.get("kind") == "note":
            n["has_stale"] = n["id"] in stale_notes
    return graph
```

**Wiring:** en `api/docs.py` `get_docs_graph()` (plan 109 F4), tras `build_graph`, si `STACKY_DOCS_STALENESS_ENABLED` → `graph = doc_staleness.annotate_staleness(graph, repo_root)` donde `repo_root` = workspace del proyecto/STACKY_AGENTS_ROOT. Con flag OFF, NO se llama (payload byte-idéntico al 109).

**Tests PRIMERO — archivo:** `backend/tests/test_plan114_staleness.py` (repo git real en `tmp_path`; commitear nota y código en orden controlado con `GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE` para fechas deterministas):
- `test_code_newer_than_note_is_stale`.
- `test_note_newer_than_code_not_stale`.
- `test_missing_epoch_is_not_stale`.
- `test_non_code_ref_edges_marked_false`.
- `test_node_has_stale_reflects_edges`.
- `test_degrades_on_non_git` (repo_root sin git → todas las aristas `stale=False`, sin excepción).

**Comando:** `venv/Scripts/python.exe -m pytest tests/test_plan114_staleness.py -q`

**Criterio BINARIO:** 6/6 verdes.

**Flag/default:** anotación solo con flag ON. **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

### F2 — No-regresión del payload + endpoint de grafo condicional

**Objetivo (1 frase).** Garantizar que con flag OFF el grafo es byte-idéntico al 109 y con flag ON gana los campos aditivos. **Valor:** cero regresión demostrada.

**Archivo a editar:** `backend/api/docs.py` (el wiring de F1) + test.

**Tests PRIMERO — archivo:** `backend/tests/test_plan114_graph_payload.py` (app+client):
- `test_graph_payload_identical_when_staleness_off` (golden: sin `stale`/`has_stale`).
- `test_graph_payload_has_stale_fields_when_on` (con repo git de prueba mockeado/real).

**Comando:** `venv/Scripts/python.exe -m pytest tests/test_plan114_graph_payload.py -q`

**Criterio BINARIO:** 2/2 verdes.

**Flag/default:** OFF → byte-idéntico 109. **Trabajo del operador:** ninguno.

---

### F3 — Endpoint `POST /api/docs/staleness/fix` (encola Documentador ACTUALIZAR)

**Objetivo (1 frase).** Desde una nota stale, encolar el modo `ACTUALIZAR` del Documentador (plan 113) acotado a esa nota. **Valor:** corrección de 1 paso.

**Archivo a editar:** `backend/api/docs.py`.

**Diseño EXACTO:** `POST /api/docs/staleness/fix` body `{note_path}` → 404 si `STACKY_DOCS_STALENESS_ENABLED` OFF **o** `STACKY_DOCS_DOCUMENTER_ENABLED` OFF (necesita el 113). Llama a un helper del orquestador 113: `doc_documenter.run_documenter(project_name, runtime, only_note=note_path, forced_modes=[ACTUALIZAR])` (extender la firma del 113 con `only_note`/`forced_modes` opcionales, backward-compatible). Devuelve `{run_id}`.

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

**Tests PRIMERO — archivo:** `frontend/src/docs/staleness.test.ts` (modelo puro):
- `noteIsStale_reads_has_stale`.
- `staleEdges_filter`.

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
| Costo de `git log` por archivo en grafos grandes. | Cache por archivo dentro del run + cache del grafo (109, TTL 60 s); timeout corto; solo aristas `code_ref`. |
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
