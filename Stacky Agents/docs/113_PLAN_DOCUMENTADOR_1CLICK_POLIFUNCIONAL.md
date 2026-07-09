# Plan 113 — Documentador agéntico 1-click polifuncional (detecta y deja la doc creada/corregida en un solo click)

> **Estado:** PROPUESTO v1 — 2026-07-09
> **Serie:** Documentación agéntica Obsidian (109 → 111 → 112 → **113** → 114). El número 110 quedó tomado por un plan ajeno (Revisor de PRs).
> **Pipeline:** este documento pasó `proponer` (este estado). Sigue `criticar-y-mejorar-plan` → `implementar-plan-stacky` → `supervisar-implementaciones-planes`.
> **Depende de:** Plan 109 (`doc_graph.build_graph`, `classify_doc_health`, contrato §4.1, flag `STACKY_DOCS_GRAPH_ENABLED`). **Reutiliza** `agent_runner.run_agent` (motor de agentes, paridad 3 runtimes), el patrón endpoint+background de `api/devops_agent.py:307 _launch_turn`, la infra de ejecuciones (`api/executions.py`) y `doc_indexer` (fuentes/workspace del proyecto activo).

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** Un único botón **"Lanzar Documentador"** en `DocsPage` que, con **un solo click y sin ningún formulario**, dispara un pipeline autónomo que: (1) **detecta el estado real** de la documentación del proyecto activo vía `doc_health` (plan 109) — *sin docs*, *mal formateada*, *incompleta*, *desactualizada* o *sana*; (2) **decide automáticamente qué trabajo hace falta** (reconstruir desde el código, normalizar a formato Obsidian, completar lo que falta, corregir lo desactualizado, enriquecer con wikilinks) — es **polifuncional**: corre todos los modos aplicables en secuencia, el operador no elige nada; (3) **deja la documentación efectivamente escrita, en el formato correcto**, al terminar. Para respetar el riel human-in-the-loop **sin** pedirle pasos al operador antes de arrancar, todo se escribe en una **rama git dedicada y revertible** (nunca en la rama de trabajo, nunca `push`): cuando el pipeline termina, la doc **ya está creada/corregida** en esa rama, y el operador la revisa como diff y la **conserva (merge) o descarta (borra la rama) con un click**. Anti-alucinación operacionalizado: cada afirmación generada lleva marca `[V]`/`[INF]`/`[NV]` y trazabilidad `archivo:línea`; **nunca** se duplican ni pisan las docs canónicas de `docs/sistema/`.

**KPI / impacto esperado.**
- **1 click, doc lista (binario):** desde `doc_health != SANA`, un solo POST deja una rama con la doc creada/corregida en formato Obsidian (frontmatter + wikilinks), verificable: tras el run, `doc_health` recomputado sobre la rama mejora de categoría (p.ej. `SIN_DOCS`→ no-SIN_DOCS, `FORMATO_NO_OBSIDIAN`→ frontmatter_ratio > 0 y wikilink_edges > 0, `INCOMPLETA`→ menos `uncovered_modules`).
- **Cero pasos previos al operador:** el botón no abre formularios; la selección de modos es automática por `doc_health`. Meta: 0 inputs obligatorios para lanzar.
- **Reversible atómico:** conservar = merge de la rama; descartar = borrar la rama; en ningún caso se toca la rama de trabajo del operador ni se hace `push`. Meta binaria: el working tree del operador queda intacto durante todo el run.
- **Anti-alucinación:** 100% de las afirmaciones nuevas llevan marca de confianza; las `[V]` citan `archivo:línea`; las notas nuevas nunca colisionan con `docs/sistema/`.
- **Paridad 3 runtimes:** el pipeline corre con Codex CLI, Claude Code CLI o GitHub Copilot Pro (parámetro `runtime` de `run_agent`); si el runtime seleccionado no está disponible, degrada al fallback configurado y lo reporta.

---

## 2. Por qué ahora / gap que cierra

1. Los planes 109/111/112 **miden, muestran y usan** el grafo, pero nadie **produce ni arregla** documentación. El operador todavía tiene que escribir/normalizar la doc a mano. Este plan cierra el lazo generativo.
2. `doc_health` (plan 109 §F3) ya entrega un diagnóstico determinista con las categorías exactas que el operador nombró ("no tiene / está mal / mal formato / le faltan cosas"). Es el disparador natural del pipeline polifuncional.
3. `agent_runner.run_agent(*, agent_type, ..., runtime=..., project_name=...)` ya sabe correr un agente en los 3 runtimes con contexto inyectado; `api/devops_agent.py:307 _launch_turn` ya muestra el patrón endpoint→background→ejecución visible. Reusar esto evita reinventar orquestación.
4. El operador fue explícito: **1 solo click**, y que **al terminar la doc ya esté hecha** (no una bandeja de aprobación previa que lo frene). La rama git revertible es la forma de honrar eso sin violar human-in-the-loop.

---

## 3. Principios y guardarraíles (NO negociables — codificados en las fases)

- **1 click, cero formularios.** El endpoint recibe a lo sumo `{project?}`; todo lo demás se infiere de `doc_health` y la config del proyecto. Prohibido pedir modo/opciones al operador antes de arrancar.
- **Human-in-the-loop vía rama revertible, no vía bandeja previa.** El agente **nunca** escribe en la rama de trabajo. Escribe en una rama dedicada `stacky/doc-<timestamp>`; el operador revisa el diff **después** y conserva (merge) o descarta (borra rama). El working tree del operador queda intacto durante el run. **Jamás `git push`.**
- **El agente propone contenido; el código determinista escribe.** El LLM devuelve un artefacto estructurado (lista de `{path, action, content, confidence}`); un aplicador determinista valida y escribe a la rama. Así "el agente nunca escribe directo" se cumple aunque el resultado quede escrito en 1 click.
- **No pisar lo canónico.** `docs/sistema/` (fuente única, memoria `canonical-system-docs-location`) es **read-only** para el Documentador: puede leerla como contexto y linkearla, nunca sobrescribirla ni duplicar su contenido. Regla dura en el aplicador (F4).
- **Anti-alucinación operacionalizado.** Todo claim nuevo con `[V]` (verificado contra `archivo:línea`), `[INF]` (inferido) o `[NV]` (no verificable). El prompt del agente lo exige; el aplicador rechaza notas sin marcas.
- **3 runtimes con paridad.** `runtime` es parámetro de `run_agent`. Selección: la del proyecto/operador (config existente); fallback explícito si no disponible, reportado en el log de la ejecución.
- **Cero trabajo extra + opt-in default OFF.** Flag `STACKY_DOCS_DOCUMENTER_ENABLED` (UI, default OFF). Sin la flag, no aparece el botón ni el endpoint.
- **No degradar / seguro por defecto.** Límites duros (máx N archivos por run, máx bytes por archivo); si el target no es repo git, se degrada a carpeta-sombra (F4) en vez de escribir sin red. Idempotente: re-lanzar no duplica notas (upsert por path).
- **Mono-operador sin auth.** Nada de identidad.
- **Sin ambigüedad para modelos menores.** Cada fase: archivo, símbolo, pseudocódigo, test + comando con venv, criterio binario, flag + default, impacto por runtime.

---

## 4. Nombres canónicos (usar EXACTAMENTE estos)

| Concepto | Nombre exacto |
|---|---|
| Flag maestra | `STACKY_DOCS_DOCUMENTER_ENABLED` (bool, default efectivo OFF) |
| Tope de archivos por run | `STACKY_DOCS_DOCUMENTER_MAX_FILES` (int, default `40`, `min_value=1`, `max_value=500`, `requires` master) |
| Orquestador | `backend/services/doc_documenter.py` |
| Selector de modos | `plan_documenter_run(project_name) -> DocumenterPlan` |
| Modos | `RECONSTRUIR`, `NORMALIZAR`, `COMPLETAR`, `ACTUALIZAR`, `ENRIQUECER` (enum `DocumenterMode`) |
| Artefacto del agente | `DocProposal` = `{path:str, action:"create"|"patch", content:str, marks_ok:bool, sources:list[str]}` |
| Aplicador determinista | `apply_proposals(proposals, target_root, branch_name) -> ApplyResult` |
| Gate git | `prepare_doc_branch(target_root) -> str` / `discard_doc_branch(target_root, branch)` / `keep_doc_branch(target_root, branch)` |
| Persona del agente | `agent_type="Documentador"` (registrado en `agents`) + `Documentador.agent.md` (persona; con fallback built-in como en plan 112 F5) |
| Endpoint lanzar | `POST /api/docs/documenter/run` (en `api/docs.py`) |
| Endpoint estado | `GET /api/docs/documenter/status?run=<id>` |
| Endpoint decisión | `POST /api/docs/documenter/decide` body `{run, action:"keep"|"discard"}` |
| Botón frontend | `DocumenterButton` en `frontend/src/components/docs/DocumenterButton.tsx` |
| Panel de resultado | `DocumenterResultPanel` (diff + Conservar/Descartar) |

### 4.1 Mapeo determinista `doc_health.status` → modos que corre el 1-click

| `doc_health.status` | Modos (en orden) | Qué produce |
|---|---|---|
| `SIN_DOCS` | RECONSTRUIR → ENRIQUECER | Doc base por módulo desde el código + índice + wikilinks. |
| `FORMATO_NO_OBSIDIAN` | NORMALIZAR → ENRIQUECER | Frontmatter YAML + wikilinks agregados a las notas existentes (sin reescribir su prosa). |
| `INCOMPLETA` | COMPLETAR → ENRIQUECER | Notas nuevas para `uncovered_modules` + wikilinks que las integran. |
| `SANA` | ENRIQUECER (marginal) | Solo agrega wikilinks/backlinks faltantes; si no hay nada, no-op reportado. |
| (stale, plan 114) | ACTUALIZAR | Corrige notas cuyo código referenciado cambió. Este plan **tolera** el modo pero el disparo por staleness llega en 114. |

---

## 5. Fases

### F0 — Flags + registro del agente `Documentador`

**Objetivo (1 frase).** Alta de la flag maestra + tope, y registro del `agent_type="Documentador"` con persona (y fallback built-in). **Valor:** superficie opt-in y agente invocable.

**Archivos:**
1. `backend/config.py` — `STACKY_DOCS_DOCUMENTER_ENABLED` (bool, default `"false"`) y `STACKY_DOCS_DOCUMENTER_MAX_FILES` (int, default `40`).
2. `backend/services/harness_flags.py` — 2 keys en `_CATEGORY_KEYS["contexto_memoria"]`; 2 `FlagSpec` (bool sin `default=`; int con `min_value=1,max_value=500`, `requires="STACKY_DOCS_DOCUMENTER_ENABLED"`, sin `default=`).
3. `backend/services/harness_flags_help.py` — 2 `PlainHelp` (qué hace el Documentador; qué pasa si lo prendés/apagás).
4. `backend/Stacky/agents/Documentador.agent.md` — persona (español): documentador técnico anti-alucinación; SIEMPRE marca `[V]/[INF]/[NV]`; cita `archivo:línea`; NUNCA toca `docs/sistema/`; produce SOLO el artefacto estructurado pedido. **Fallback:** const `_DEFAULT_DOCUMENTADOR_PROMPT` en `doc_documenter.py` usada si el `.agent.md` no está (patrón plan 112 F5, porque los `.agent.md` están gitignoreados).
5. Registro en el dict `agents` (donde se registran QAUat1/Business/Functional/Technical/Developer/DevOpsAgent) → agregar `Documentador` apuntando a su definición.

**Tests PRIMERO — archivo:** `backend/tests/test_plan113_flags_and_agent.py`:
- `test_flags_registered_and_default_off`.
- `test_max_files_bounds_and_requires`.
- `test_flags_have_plain_help`.
- `test_documentador_agent_registered` (`from agent_runner import agents; assert "Documentador" in agents`).
- `test_documentador_has_fallback_prompt` (`_DEFAULT_DOCUMENTADOR_PROMPT` no vacío y menciona las marcas `[V]`).

Registrar en `run_harness_tests.sh` **y** `.ps1`.

**Comando (desde `Stacky Agents/backend`):**
```
venv/Scripts/python.exe -m pytest tests/test_plan113_flags_and_agent.py tests/test_harness_flags.py tests/test_harness_flags_help.py tests/test_harness_flags_requires.py -q
```

**Criterio BINARIO:** 4 archivos verdes.

**Flag/default:** master OFF. **Impacto por runtime:** ninguno (registro). **Trabajo del operador:** ninguno.

---

### F1 — Selector de modos determinista `plan_documenter_run`

**Objetivo (1 frase).** Dado el `doc_health` del proyecto (plan 109), devolver el `DocumenterPlan` (lista ordenada de modos + targets) sin LLM. **Valor:** el "polifuncional automático" es determinista y testeable.

**Archivo a crear:** `backend/services/doc_documenter.py` (en F1 solo el selector).

**Pseudocódigo EXACTO:**
```python
from enum import Enum
from dataclasses import dataclass, field

class DocumenterMode(str, Enum):
    RECONSTRUIR = "RECONSTRUIR"; NORMALIZAR = "NORMALIZAR"
    COMPLETAR = "COMPLETAR"; ACTUALIZAR = "ACTUALIZAR"; ENRIQUECER = "ENRIQUECER"

@dataclass
class DocumenterPlan:
    status: str                      # doc_health.status
    modes: list[DocumenterMode]
    uncovered_modules: list[str] = field(default_factory=list)
    notes_to_normalize: list[str] = field(default_factory=list)  # file_paths sin frontmatter
    reason: str = ""

def plan_documenter_run(project_name: str) -> DocumenterPlan:
    from services import doc_graph
    graph = doc_graph.build_graph(project_name=project_name)
    health = graph.get("doc_health") or {"status": "SIN_DOCS"}
    st = health["status"]
    if st == "SIN_DOCS":
        return DocumenterPlan(st, [DocumenterMode.RECONSTRUIR, DocumenterMode.ENRIQUECER],
                              reason="El proyecto no tiene notas; se reconstruye desde el código.")
    if st == "FORMATO_NO_OBSIDIAN":
        no_fm = [n["path"] for n in graph["nodes"]
                 if n["kind"] == "note" and n["source_id"].startswith("project-docs")
                 and not n.get("has_frontmatter")]
        return DocumenterPlan(st, [DocumenterMode.NORMALIZAR, DocumenterMode.ENRIQUECER],
                              notes_to_normalize=no_fm, reason="Notas sin frontmatter ni wikilinks.")
    if st == "INCOMPLETA":
        return DocumenterPlan(st, [DocumenterMode.COMPLETAR, DocumenterMode.ENRIQUECER],
                              uncovered_modules=health.get("uncovered_modules", []),
                              reason="Módulos de código sin nota.")
    # SANA
    return DocumenterPlan(st, [DocumenterMode.ENRIQUECER], reason="Doc sana; solo enriquecer links.")
```

**Tests PRIMERO — archivo:** `backend/tests/test_plan113_plan_selector.py` (monkeypatch `doc_graph.build_graph` con grafos fake por status):
- `test_sin_docs_reconstruir`.
- `test_formato_no_obsidian_lists_notes_without_frontmatter`.
- `test_incompleta_carries_uncovered_modules`.
- `test_sana_only_enriquecer`.
- `test_modes_are_deterministic_ordered`.

**Comando:** `venv/Scripts/python.exe -m pytest tests/test_plan113_plan_selector.py -q`

**Criterio BINARIO:** 5/5 verdes.

**Flag/default:** no lee la master (la ruta gatea). **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

### F2 — Construcción de contexto + invocación del agente por modo

**Objetivo (1 frase).** Por cada modo del plan, armar los `context_blocks` (código relevante + notas existentes + subgrafo) y llamar `agent_runner.run_agent(agent_type="Documentador", runtime=<sel>, ...)`, recogiendo el artefacto estructurado `list[DocProposal]`. **Valor:** el paso generativo, con paridad de runtime y contexto anclado.

**Archivo a editar:** `backend/services/doc_documenter.py`.

**Diseño EXACTO:**
- `build_context_for_mode(mode, plan, project_name) -> list[dict]`: 
  - RECONSTRUIR/COMPLETAR: por cada módulo objetivo, un bloque con el árbol de archivos del módulo (reusar `doc_indexer`/`repo_explainer` para no releer todo) + snippets de símbolos top (para que el agente cite `archivo:línea`).
  - NORMALIZAR: por cada nota en `notes_to_normalize`, un bloque con el contenido actual de la nota (para agregar frontmatter/wikilinks SIN reescribir prosa).
  - ENRIQUECER: subgrafo (nodos + huérfanas) para proponer wikilinks faltantes.
  - Siempre: un bloque read-only con el índice de `docs/sistema/` (para linkear, marcado "NO EDITAR").
- `invoke_documenter(mode, context_blocks, project_name, runtime) -> list[DocProposal]`:
  - `execution_id = agent_runner.run_agent(agent_type="Documentador", ticket_id=<ticket sintético o 0 si el motor lo permite>, context_blocks=context_blocks, user="documenter", runtime=runtime, project_name=project_name, system_prompt_override=_DEFAULT_DOCUMENTADOR_PROMPT if no .agent.md, work_item_type="Doc")`.
  - Parsear la salida del agente a `list[DocProposal]` con `parse_proposals(raw) `: exige bloques con front `path:`, `action:`, `sources:` y cuerpo; **marca `marks_ok=True`** solo si el cuerpo contiene al menos una de `[V]`/`[INF]`/`[NV]`. Salidas malformadas → se descartan con log (nunca crashea).

> **Contrato de salida del agente (documentado en `Documentador.agent.md`):** el agente responde SOLO un bloque por archivo, delimitado, con encabezado `<<<DOC path="..." action="create|patch" sources="a.py:10,b.ts:3">>>` … `<<<END>>>`, cuerpo markdown con frontmatter y marcas. `parse_proposals` parsea ese formato determinista (regex), no prosa libre.

**Tests PRIMERO — archivo:** `backend/tests/test_plan113_invoke_and_parse.py` (monkeypatch `agent_runner.run_agent` y la recuperación de salida; NO invoca LLM real):
- `test_parse_well_formed_proposals`.
- `test_parse_rejects_missing_marks` (`marks_ok=False` si no hay `[V]/[INF]/[NV]`).
- `test_parse_ignores_malformed_blocks`.
- `test_build_context_normalize_includes_note_content`.
- `test_build_context_always_includes_sistema_readonly_block`.
- `test_invoke_uses_selected_runtime` (el `runtime` pasa tal cual a `run_agent`).

**Comando:** `venv/Scripts/python.exe -m pytest tests/test_plan113_invoke_and_parse.py -q`

**Criterio BINARIO:** 6/6 verdes.

**Flag/default:** no gatea acá. **Impacto por runtime:** `runtime` se propaga; fallback si no disponible se maneja en F3 (orquestador). **Trabajo del operador:** ninguno.

---

### F3 — Gate git: rama revertible (`prepare`/`keep`/`discard`)

**Objetivo (1 frase).** Aislar toda la escritura en una rama git dedicada, con el working tree del operador intacto, y operaciones atómicas de conservar/descartar. **Valor:** el mecanismo que hace seguro el "1-click que ya deja la doc escrita".

**Archivo a editar:** `backend/services/doc_documenter.py`.

**Diseño EXACTO (usa `subprocess` git, como el resto de DevOps; nunca `push`):**
```python
def prepare_doc_branch(target_root: str) -> str | None:
    """Crea y checkoutea una rama 'stacky/doc-<UTCstamp>' desde HEAD, SIN tocar el
    working tree del operador: usa un `git worktree add` en un dir temporal para no
    mover la rama activa. Devuelve el PATH del worktree (donde se escribe) o None si
    target_root no es repo git (→ caller degrada a carpeta-sombra)."""
    # git -C target_root rev-parse --is-inside-work-tree ; si falla → None
    # branch = "stacky/doc-" + utcnow.strftime("%Y%m%d-%H%M%S")
    # git -C target_root worktree add -b <branch> <tmp_worktree> HEAD
    # return tmp_worktree

def keep_doc_branch(target_root: str, branch: str) -> None:
    """Deja la rama disponible para que el operador la mergee cuando quiera
    (NO hace merge automático a la de trabajo, NO push). Limpia el worktree temporal
    con `git worktree remove` conservando la rama."""

def discard_doc_branch(target_root: str, branch: str) -> None:
    """Borra el worktree temporal y la rama (`git worktree remove` + `git branch -D`).
    El working tree del operador nunca fue tocado."""
```
- Degradación sin git: si `prepare_doc_branch` devuelve None, el aplicador (F4) escribe en `<target_root>/.stacky-docs-proposed/` (carpeta-sombra, git-ignorada por convención) y el panel avisa "no es repo git: revisá y copiá a mano".

**Tests PRIMERO — archivo:** `backend/tests/test_plan113_git_gate.py` (usar `tmp_path` como repo git real: `git init`, commit inicial):
- `test_prepare_creates_branch_worktree_without_touching_main` (tras prepare, `git -C repo status` limpio en el working tree original).
- `test_discard_removes_branch_and_worktree`.
- `test_keep_preserves_branch_removes_worktree`.
- `test_prepare_returns_none_on_non_git` (dir sin `.git` → None).
- `test_never_pushes` (verificar que ningún comando incluye `push` — inspección del runner de subprocess mockeado o del historial de comandos).

**Comando:** `venv/Scripts/python.exe -m pytest tests/test_plan113_git_gate.py -q`

**Criterio BINARIO:** 5/5 verdes.

**Flag/default:** N/A. **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno durante el run; decide después.

---

### F4 — Aplicador determinista `apply_proposals` (escribe a la rama, protege lo canónico)

**Objetivo (1 frase).** Validar y escribir los `DocProposal` en el worktree de la rama, con reglas duras: no tocar `docs/sistema/`, exigir marcas, upsert idempotente por path, respetar topes. **Valor:** convierte propuestas del LLM en archivos reales, seguro y determinista.

**Archivo a editar:** `backend/services/doc_documenter.py`.

**Reglas EXACTAS (rechazo = se saltea con log, nunca crashea):**
1. **Path seguro:** normalizar; rechazar absolutos y `..` (anti-traversal); debe caer bajo la carpeta de docs del proyecto (o crearse ahí para notas nuevas).
2. **Canónico read-only:** si el path resuelto cae bajo `docs/sistema/` → **rechazar** (regla dura; memoria `canonical-system-docs-location`).
3. **Marcas obligatorias:** `proposal.marks_ok` debe ser True; si no → rechazar.
4. **Tope:** máx `STACKY_DOCS_DOCUMENTER_MAX_FILES` archivos por run; superado → cortar y reportar.
5. **Idempotencia:** `action="create"` sobre path existente se trata como `patch` (upsert); re-lanzar no duplica.
6. Escribir; devolver `ApplyResult{written:list[str], skipped:list[(path,reason)], branch, degraded:bool}`.

**Tests PRIMERO — archivo:** `backend/tests/test_plan113_apply.py` (worktree fake en `tmp_path`):
- `test_writes_valid_proposals`.
- `test_rejects_docs_sistema_paths`.
- `test_rejects_proposals_without_marks`.
- `test_rejects_path_traversal`.
- `test_respects_max_files_cap`.
- `test_idempotent_upsert_no_duplicate`.

**Comando:** `venv/Scripts/python.exe -m pytest tests/test_plan113_apply.py -q`

**Criterio BINARIO:** 6/6 verdes.

**Flag/default:** lee el tope. **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

### F5 — Orquestador + endpoints (run en background, status, decide)

**Objetivo (1 frase).** Cablear todo detrás de 3 endpoints: `run` (1-click, background), `status` (progreso vía infra de ejecuciones), `decide` (keep/discard). **Valor:** la experiencia 1-click end-to-end.

**Archivos a editar:** `backend/services/doc_documenter.py` (orquestador) + `backend/api/docs.py` (endpoints, gateados por la master).

**Orquestador `run_documenter(project_name, runtime) -> dict` (background, patrón `_pre_run_then_run_in_background`):**
```
plan = plan_documenter_run(project_name)
target_root = <workspace_root del proyecto activo, de doc_indexer/sources>
worktree = prepare_doc_branch(target_root)  # None → carpeta-sombra (degraded)
all_props = []
for mode in plan.modes:
    ctx = build_context_for_mode(mode, plan, project_name)
    props = invoke_documenter(mode, ctx, project_name, runtime)  # fallback runtime si no disponible
    all_props += props
result = apply_proposals(all_props, worktree or shadow_dir, branch)
# recomputar doc_health sobre la rama para el KPI (build_graph apuntando al worktree)
report = {plan, result, health_before, health_after, branch, degraded}
persistir report asociado al run_id
```
- **Fallback de runtime:** si `runtime` no disponible, probar el orden configurado (`github_copilot`→`claude_code_cli`→`codex`) y registrar cuál se usó en el log de la ejecución. Si ninguno, marcar el run `failed` con mensaje claro (nunca a medias sin avisar).
- **Progreso visible:** cada modo emite eventos al `log_streamer`/infra de ejecuciones (como los agentes DevOps), así el frontend muestra avance sin polling ad-hoc.

**Endpoints en `api/docs.py` (todos 404 si `STACKY_DOCS_DOCUMENTER_ENABLED` OFF):**
- `POST /api/docs/documenter/run` body `{project?}` → lanza en background, devuelve `{run_id}`.
- `GET /api/docs/documenter/status?run=<id>` → `{state, current_mode, written, skipped, health_before, health_after, branch, degraded}`.
- `POST /api/docs/documenter/decide` body `{run, action}` → `keep_doc_branch`/`discard_doc_branch`; devuelve `{ok, action}`.

**Tests PRIMERO — archivo:** `backend/tests/test_plan113_endpoints.py` (app+client; monkeypatch del orquestador para no invocar LLM):
- `test_run_404_when_flag_off`.
- `test_status_404_when_flag_off`.
- `test_decide_404_when_flag_off`.
- `test_run_returns_run_id_when_flag_on` (orquestador mockeado).
- `test_decide_keep_calls_keep_branch` / `test_decide_discard_calls_discard_branch`.
- `test_run_selects_modes_from_health` (integra selector con orquestador mockeando build_graph + run_agent).

**Comando:** `venv/Scripts/python.exe -m pytest tests/test_plan113_endpoints.py -q`

**Criterio BINARIO:** 6/6 verdes.

**Flag/default:** master OFF → los 3 endpoints 404. **Impacto por runtime:** el pipeline corre en el runtime seleccionado con fallback; reportado. **Trabajo del operador:** 1 click para lanzar; 1 click para conservar/descartar.

---

### F6 — Frontend: botón 1-click + panel de resultado (diff, Conservar/Descartar)

**Objetivo (1 frase).** Botón "Lanzar Documentador" en `DocsPage` (solo con flag ON) que dispara el run, muestra progreso y, al terminar, presenta el diff con acciones Conservar/Descartar. **Valor:** la cara 1-click de todo el plan.

**Archivos:**
1. `frontend/src/api/endpoints.ts` — en `Docs`: `documenterRun(project?)`, `documenterStatus(runId)`, `documenterDecide(runId, action)`.
2. `frontend/src/components/docs/DocumenterButton.tsx` — botón primario; onClick → `documenterRun` → poll `documenterStatus` (react-query con `refetchInterval` mientras `state==="running"`); muestra modo actual y contador de archivos.
3. `frontend/src/components/docs/DocumenterResultPanel.tsx` — al terminar: resumen (`health_before → health_after`, N escritos, N saltados con razón, badge `degraded` si carpeta-sombra) + lista de archivos + botones **"Conservar"** (`decide keep`) y **"Descartar"** (`decide discard`). Sin `window.confirm`.
4. `frontend/src/pages/DocsPage.tsx` — montar `DocumenterButton` en la barra superior **solo si `graph_enabled` y** una segunda flag expuesta `documenter_enabled` (agregar key aditiva `documenter_enabled` en `/api/docs/sources`, como se hizo con `graph_enabled` en 109 F0). Con flag OFF: nada nuevo.

**Tests PRIMERO — archivo:** `frontend/src/docs/documenterModel.test.ts` (modelo puro; la lógica testeable = derivación del resumen de status):
- `summarizeDocumenterStatus_maps_states`.
- `summarizeDocumenterStatus_flags_degraded`.
- `healthDelta_describes_improvement`.

> Disclosure de entorno (plan 107): `.test.tsx` bloqueado; criterio = modelo puro `.test.ts` + `tsc --noEmit` + verificación manual.

**Comando (desde `Stacky Agents/frontend`):**
```
npx vitest run src/docs/documenterModel.test.ts
npx tsc --noEmit
```

**Criterio BINARIO:** 3/3 vitest verdes + tsc 0 errores. Con flag OFF, DocsPage sin botón ni panel.

**Flag/default:** `STACKY_DOCS_DOCUMENTER_ENABLED` OFF → botón ausente. **Impacto por runtime:** ninguno (UI). **Trabajo del operador:** 1 click.

---

### F7 — Cierre: no-regresión, verificación manual y DoD

**Acciones:**
1. Registrar los 6 archivos backend nuevos en `run_harness_tests.sh` **y** `.ps1`.
2. Backend (desde `Stacky Agents/backend`):
   ```
   venv/Scripts/python.exe -m pytest tests/test_plan113_flags_and_agent.py tests/test_plan113_plan_selector.py tests/test_plan113_invoke_and_parse.py tests/test_plan113_git_gate.py tests/test_plan113_apply.py tests/test_plan113_endpoints.py tests/test_harness_flags.py tests/test_harness_flags_help.py tests/test_harness_flags_requires.py -q
   ```
3. Frontend: `npx vitest run src/docs/documenterModel.test.ts && npx tsc --noEmit`.
4. **Verificación manual (flag ON)** sobre un proyecto de prueba con `doc_health` distinto de SANA: 1 click → progreso visible → al terminar hay rama `stacky/doc-*` con notas en formato Obsidian (frontmatter + wikilinks) y marcas `[V]/[INF]/[NV]`; `docs/sistema/` intacta; working tree del operador intacto; Conservar mergea / Descartar borra la rama.

**Criterio BINARIO global (DoD):**
- [ ] 6 suites backend nuevas + 3 del arnés + 1 vitest verdes; `tsc --noEmit` 0 errores.
- [ ] Con la master OFF: sin botón, sin endpoints (404), DocsPage byte-idéntica a hoy.
- [ ] 1 click sin formularios lanza el pipeline; los modos salen de `doc_health` (F1).
- [ ] Al terminar, la doc está escrita en una rama git dedicada, en formato Obsidian, con marcas anti-alucinación; `docs/sistema/` nunca modificada; working tree del operador intacto; jamás `push`.
- [ ] Conservar/Descartar operan atómicamente (merge disponible / borrado de rama).
- [ ] Idempotente (re-lanzar no duplica) y acotado (tope de archivos).
- [ ] Paridad 3 runtimes con fallback reportado.

---

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| "1-click que escribe" choca con human-in-the-loop. | Escribe en rama dedicada revertible, nunca en la de trabajo, nunca push; el operador conserva/descarta después (F3). Working tree intacto (test). |
| Alucinación en doc generada. | Marcas `[V]/[INF]/[NV]` obligatorias (aplicador rechaza sin marcas, F4); `[V]` con `archivo:línea`; formato de salida determinista parseado por regex, no prosa libre. |
| Pisar/duplicar `docs/sistema/` canónicas. | Regla dura en el aplicador: paths bajo `docs/sistema/` rechazados (F4, test). Solo se linkean. |
| Escribir sin red en repo no-git o sucio. | `worktree add` aísla; si no es git → carpeta-sombra `.stacky-docs-proposed/` + aviso `degraded` (F3/F4). |
| Runtime seleccionado no disponible. | Fallback ordenado con reporte del runtime usado; si ninguno, run `failed` explícito (F5). |
| Runs enormes / bucles. | Tope `STACKY_DOCS_DOCUMENTER_MAX_FILES` + 1-hop de contexto acotado; idempotente por upsert. |
| El agente ignora el contrato de salida. | `parse_proposals` descarta bloques malformados con log; nunca crashea; los válidos igual se aplican. |
| Costo/latencia de varios modos en serie. | Modos solo los que `doc_health` exige; SANA = casi no-op; progreso visible para cancelar (infra de ejecuciones). |

---

## 7. Fuera de scope

- Detección de staleness doc↔código (plan 114; este plan tolera el modo ACTUALIZAR pero el disparo por staleness llega en 114).
- Merge automático a la rama de trabajo (siempre lo decide el operador; solo se deja la rama lista).
- Edición de `docs/sistema/` (canónicas, read-only para el Documentador).
- Traducción/versionado de docs, publicación externa, PRs remotos.
- Generar el grafo o el retrieval (planes 109/112; acá se consumen).
- Editar `alpha/beta` del híbrido u otras flags (fuera de este plan).

---

## 8. Glosario (términos para modelos menores)

- **Polifuncional:** el mismo botón cubre varios trabajos (reconstruir, normalizar, completar, enriquecer) y elige cuáles correr según el diagnóstico.
- **`doc_health`:** diagnóstico determinista del plan 109 (`SIN_DOCS`/`FORMATO_NO_OBSIDIAN`/`INCOMPLETA`/`SANA`) que dispara los modos.
- **Modo:** una tarea concreta del Documentador (ver enum `DocumenterMode`).
- **`DocProposal`:** propuesta de un archivo (crear/parchear) que el agente devuelve y el aplicador escribe.
- **Rama dedicada / worktree:** copia de trabajo aislada (`git worktree`) donde se escribe sin tocar la rama del operador; se conserva (merge) o se borra.
- **Marcas `[V]/[INF]/[NV]`:** Verificado (con `archivo:línea`) / Inferido / No verificable — operacionalizan el anti-alucinación.
- **`agent_runner.run_agent`:** motor que corre un agente en Codex/Claude/Copilot con contexto inyectado (`runtime` es parámetro).
- **Carpeta-sombra:** `.stacky-docs-proposed/`, destino de degradación cuando el target no es repo git.
- **Canónico:** `docs/sistema/` (fuente única de verdad); read-only para el Documentador.
- **venv del repo:** `Stacky Agents/backend/venv` (Python 3.13); pytest por archivo.

---

## 9. Orden de implementación (secuencial)

1. **F0** — flags + registro del agente `Documentador` + persona/fallback.
2. **F1** — `plan_documenter_run` (selector de modos) + 5 tests.
3. **F2** — contexto por modo + `invoke_documenter` + `parse_proposals` + 6 tests.
4. **F3** — gate git (`prepare`/`keep`/`discard`) + 5 tests.
5. **F4** — `apply_proposals` (protege canónico, exige marcas) + 6 tests.
6. **F5** — orquestador background + 3 endpoints + 6 tests.
7. **F6** — botón 1-click + panel de resultado + modelo puro (vitest + tsc).
8. **F7** — cierre, no-regresión, verificación manual, DoD.

---

## 10. Definición de Hecho (DoD) — resumen binario

Hecho cuando: (a) las 6 suites backend + 3 del arnés + la vitest están verdes y `tsc --noEmit` da 0 errores; (b) con la master OFF no hay botón ni endpoints y DocsPage es byte-idéntica a hoy; (c) un solo click sin formularios lanza el pipeline, que elige los modos desde `doc_health`; (d) al terminar, la documentación queda **escrita y en formato Obsidian** (frontmatter + wikilinks) en una rama git dedicada, con marcas anti-alucinación y sin tocar `docs/sistema/` ni el working tree del operador, y **sin `push`**; (e) el operador conserva (merge disponible) o descarta (borra rama) con un click; (f) el pipeline es idempotente y acotado por el tope de archivos; (g) corre en los 3 runtimes con fallback reportado.
