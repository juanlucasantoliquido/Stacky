# Plan 109 — Grafo documental READ-ONLY + diagnóstico de estado documental

> **Estado:** CRITICADO v2 — 2026-07-09 (v1 → v2 por `criticar-y-mejorar-plan`)
> **Veredicto del juez:** APROBADO-CON-CAMBIOS (C1-C3 IMPORTANTES resueltos en esta v2; sin bloqueantes)
>
> **CHANGELOG v1 → v2:**
> - **C1 (IMPORTANTE):** los parsers de F1 ahora ignoran bloques de código fenced (``` ... ```) para links md y wikilinks — antes, ejemplos de código en las notas generaban aristas falsas y podían burlar la regla `FORMATO_NO_OBSIDIAN` de F3. `parse_code_refs` sigue leyendo el texto completo (las refs a código legítimas viven en backticks inline). +2 tests en F1 (14 total).
> - **C2 (IMPORTANTE):** el camino central de la cache de F2 ("TTL vencido + fingerprint distinto → rebuild") quedaba sin test (el test v1 usaba `invalidate_graph_cache()` manual). F2 ahora trae 3 tests de cache explícitos con `_GRAPH_TTL_SECONDS` monkeypatcheado (11 tests total).
> - **C3 (IMPORTANTE):** fingerprint con `OSError` especificado literal: el archivo cuenta en `n_files` con `mtime_ns=0` y `size=0` (antes decía "(0,0)" ambiguo sobre una 3-tupla).
> - **C4 (MENOR):** cita corrida corregida: `default_is_known` hoy vive en harness_flags.py:2444 — localizar SIEMPRE por símbolo, no por línea.
> - **C5 (MENOR):** colisión de nodos `missing:` por basename documentada como decisión determinística en §4.1.
> - **C6 (MENOR):** tope de entradas de cache `_MAX_CACHE_ENTRIES = 8` (evita crecimiento sin límite al alternar proyectos).
> - **C7 (MENOR):** el 500 de F4 ya no devuelve `str(exc)` al cliente; mensaje genérico + detalle solo en log.
> - **C8 (MENOR):** limitación documentada: links md con espacios/`%20` no matchean (test negativo incluido).
> - **[ADICIÓN ARQUITECTO]:** query param `?refresh=1` en `GET /api/docs/graph` + botón "Recargar" en `DocCoveragePanel` — el operador fuerza re-scan sin esperar el TTL ni reiniciar el backend; el plan 111 lo hereda gratis. +1 test en F4 (5 total).
> **Serie:** Documentación agéntica Obsidian (109 → 111 → 112; alimenta al Documentador del plan 113). Nota: el número **110 quedó tomado** por un plan ajeno (Revisor de PRs, commiteado por otra sesión), por eso esta serie salta de 109 a 111.
> **Pipeline:** este documento pasó `proponer` (este estado). Sigue `criticar-y-mejorar-plan` → `implementar-plan-stacky` → `supervisar-implementaciones-planes`.
> **Dependencias:** ninguna (es la base de la serie). Los planes 111 y 112 dependen de este.

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** Stacky ya sabe *listar y leer* documentación (`services/doc_indexer.py` resuelve fuentes: `STACKY_AGENTS_ROOT/docs`, `*.md` de raíz, `VSCODE_PROMPTS_DIR`, y carpetas `docs` del proyecto activo hasta profundidad 4, máx 50 fuentes; `api/docs.py` expone `/api/docs/sources|index|content`), pero **no sabe cómo se relacionan las notas entre sí ni con el código**: no hay noción de links, backlinks, notas huérfanas ni salud del corpus. Este plan construye un **grafo documental de solo lectura**: un servicio nuevo `backend/services/doc_graph.py` que parsea tres tipos de aristas sobre las fuentes que `doc_indexer` ya resuelve — (a) links markdown `[texto](ruta.md)`, (b) wikilinks `[[nombre]]` / `[[nombre|alias]]`, (c) referencias a rutas de código (`backend/services/foo.py`, `foo.py:123`) — un endpoint `GET /api/docs/graph` con cache invalidada por mtime, un **clasificador determinístico de salud documental** por proyecto (`SIN_DOCS` / `FORMATO_NO_OBSIDIAN` / `INCOMPLETA` / `SANA`) y una pestaña **"Cobertura"** de solo lectura en `DocsPage`. Todo gateado por la flag nueva `STACKY_DOCS_GRAPH_ENABLED` (UI, default OFF). No se escribe ni modifica ningún documento: 100% read-only.

**KPI / impacto esperado.**
- **Visibilidad:** el operador ve en 1 clic cuántas notas, aristas, backlinks y huérfanas tiene el corpus del proyecto activo, y un veredicto de salud (`doc_health`) con razones. Meta: la pestaña Cobertura carga en < 2 s para corpus de hasta 500 notas (cache tibia).
- **Sustrato para la serie:** el payload de `/api/docs/graph` es el contrato que consumen el Graph View (plan 111), el retrieval híbrido (plan 112) y el diagnóstico del Documentador (plan 113). Meta binaria: los 3 planes siguientes NO necesitan parsear markdown de nuevo — consumen este endpoint/servicio.
- **Cero regresión:** con la flag OFF, `/api/docs/*` existentes y `DocsPage` son **byte-idénticos** a hoy (garantizado por test golden `test_docs_endpoints_unchanged_when_flag_off` y porque la pestaña no se renderiza sin flag).

---

## 2. Por qué ahora / gap que cierra

Relevamiento real del sustrato (2026-07-09, verificado en código):

1. `backend/services/doc_indexer.py` ya detecta y whitelistea todas las fuentes de docs (Stacky + proyecto), con excludes (`node_modules`, `.venv`, `__pycache__`, `.git`, `data`, `dist`, `build`), anti-traversal (`_normalize_relative_path`, `_is_relative_to`) y cache TTL 5 min. **Nadie recorre el contenido buscando relaciones.**
2. `backend/api/docs.py` expone solo lectura plana (`/sources`, `/index`, `/content`). No hay noción de aristas.
3. Ya existen **3 motores TF-IDF** en el backend (`services/rag_retriever.py` plan 64, `services/docs_rag.py`, `services/memory_store.py:999-1014`). **PROHIBIDO crear un cuarto**: este plan NO hace retrieval; hace parsing estructural determinístico (regex), que es otra cosa y no duplica nada.
4. `frontend/src/pages/DocsPage.tsx` es un visor pasivo (DocTree + DocViewer). No comunica nada sobre la calidad/conectividad del corpus.
5. El operador aprobó la serie "documentación agéntica Obsidian": para que los agentes documenten con wikilinks y grafo, primero hay que **medir** qué hay (este plan), luego **verlo** (111), luego **usarlo en retrieval** (112).

---

## 3. Principios y guardarraíles (NO negociables — codificados en las fases)

- **3 runtimes con paridad total.** Este plan es **runtime-agnóstico por construcción**: backend Flask puro (regex + filesystem read-only) + UI React. **No hay ninguna llamada a runtime LLM** (Codex CLI / Claude Code CLI / GitHub Copilot Pro). Paridad trivial y total; no hay fallback que definir porque no hay dependencia de runtime.
- **Cero trabajo extra al operador.** Opt-in con default OFF vía UI (`HarnessFlagsPanel`, categoría *Contexto y memoria*). Sin pasos manuales nuevos: el grafo se computa solo, con cache invalidada por mtime. Backward-compatible: ningún endpoint existente cambia su payload (la única adición es la key aditiva `graph_enabled` en `/api/docs/sources`, ver F0).
- **Human-in-the-loop / read-only.** El grafo NO escribe, NO mueve, NO corrige documentos. Solo diagnostica. Cualquier acción correctiva es de planes posteriores y siempre con aprobación humana.
- **Mono-operador sin auth.** No se agrega RBAC. `current_user` sigue siendo un header sin validar.
- **No degradar performance/seguridad/estabilidad.** Lectura de archivos SOLO dentro de las raíces que `doc_indexer` ya whitelistea (se reutilizan sus funciones; cero rutas nuevas de lectura). Límite duro de trabajo: máx 2000 notas y 2 MB por archivo (constantes nombradas, ver F2). Cache en memoria con invalidación por mtime para no re-escanear en cada request.
- **Reusar lo existente.** `doc_graph.py` consume `doc_indexer.list_doc_sources()` / `build_index()` / `build_project_docs_index()` para enumerar notas. NO re-implementa descubrimiento de fuentes ni excludes ni anti-traversal.
- **Toda flag desde la UI, default OFF.** `env_only=False`, sin `default=` explícito en el `FlagSpec` (gotcha `_CURATED_DEFAULTS_ON`, ver F0).
- **Sin ambigüedad para modelos menores.** Cada fase indica archivo exacto, símbolo exacto, pseudocódigo con casos borde, test nombrado, comando exacto con el venv del repo y criterio binario.

---

## 4. Nombres canónicos (usar EXACTAMENTE estos)

| Concepto | Nombre exacto |
|---|---|
| Flag | `STACKY_DOCS_GRAPH_ENABLED` (bool, default efectivo OFF) |
| Servicio nuevo | `backend/services/doc_graph.py` |
| Parser links md | `parse_markdown_links(text: str) -> list[str]` |
| Parser wikilinks | `parse_wikilinks(text: str) -> list[str]` |
| Parser refs de código | `parse_code_refs(text: str) -> list[str]` |
| Builder del grafo | `build_graph(project_name: str | None = None, vscode_prompts_dir: str | None = None) -> dict` |
| Clasificador de salud | `classify_doc_health(nodes: list[dict], edges: list[dict], workspace_root: str | None) -> dict` |
| Invalidador (tests) | `invalidate_graph_cache() -> None` |
| Endpoint nuevo | `GET /api/docs/graph` (en `backend/api/docs.py`) |
| Key aditiva en /sources | `graph_enabled: bool` |
| Componente frontend | `DocCoveragePanel` en `frontend/src/components/docs/DocCoveragePanel.tsx` |
| Modelo puro frontend | `summarizeGraph(graph: DocGraphResponse): DocCoverageSummary` en `frontend/src/docs/docGraphModel.ts` |
| Cliente API frontend | `Docs.getGraph` en `frontend/src/api/endpoints.ts` |

### 4.1 Contrato del payload de `/api/docs/graph` (fuente única de verdad para 109/111/112)

```jsonc
{
  "ok": true,
  "generated_at": "2026-07-09T12:00:00+00:00",   // ISO-8601 UTC
  "active_project": "RSSTANDAR",                  // o null
  "sources": [                                    // metadata por fuente (subset de list_doc_sources)
    { "id": "stacky", "kind": "stacky", "label": "Stacky Agents",
      "relative_path": ".", "absolute_path": "N:/..." },
    { "id": "project-docs:docs", "kind": "project-docs", "label": "docs",
      "relative_path": "docs", "absolute_path": "N:/..." }
  ],
  "nodes": [
    { "id": "note:project-docs:docs:arquitectura.md",  // "note:<source_id>:<path>" | "code:<path>" | "missing:<nombre>"
      "kind": "note",                // "note" | "code" | "missing"
      "label": "arquitectura.md",    // basename (para "missing": el nombre del wikilink)
      "path": "arquitectura.md",     // relativo a la raíz de la fuente ('/' como separador); para "code": ruta tal como aparece en el texto, normalizada
      "source_id": "project-docs:docs",  // para "code" y "missing": ""
      "in_degree": 3,
      "out_degree": 5,
      "has_frontmatter": true,       // solo kind="note"; false en code/missing
      "exists": true                 // kind="code": si la ruta resuelve bajo workspace_root o STACKY_AGENTS_ROOT; note=true; missing=false
    }
  ],
  "edges": [
    { "source": "note:project-docs:docs:arquitectura.md",
      "target": "note:project-docs:docs:modulos/motor.md",
      "kind": "md" }                 // "md" | "wikilink" | "code_ref"
  ],
  "orphans": ["note:project-docs:docs:vieja-nota.md"],  // ids de notas con in_degree==0 AND out_degree==0
  "stats": {
    "notes": 42, "code_refs": 17, "missing": 3,
    "edges_md": 51, "edges_wikilink": 12, "edges_code_ref": 17,
    "orphans": 4, "sources": 2
  },
  "doc_health": {
    "status": "INCOMPLETA",          // "SIN_DOCS" | "FORMATO_NO_OBSIDIAN" | "INCOMPLETA" | "SANA"
    "reasons": ["3 módulos de código de primer nivel sin ninguna nota que los referencie: backend, frontend, deployment"],
    "frontmatter_ratio": 0.62,       // notas con frontmatter / notas totales (0.0 si 0 notas)
    "wikilink_edges": 12,
    "uncovered_modules": ["backend", "frontend", "deployment"]  // [] si no aplica
  }
}
```

Reglas de identidad (deterministas):
- `id` de nota = `"note:" + source_id + ":" + path` (path relativo a la raíz de la fuente, separador `/`).
- `id` de código = `"code:" + ruta_normalizada` (backslashes → `/`, sin `./` inicial, sin sufijo `:NNN` de línea).
- `id` de missing = `"missing:" + nombre_lower` (nombre del wikilink sin resolver, lowercase, sin extensión). **Decisión determinística (C5):** para links md rotos el id usa solo el basename (sin ruta); dos links rotos a rutas distintas con el mismo basename COLISIONAN en un único nodo `missing:` — aceptado y estable (el nodo missing representa "algo con ese nombre no existe", no una ruta).
- `nodes` ordenados por `id` asc; `edges` ordenadas por `(source, target, kind)` asc; sin duplicados exactos de arista (set). Determinismo total: dos corridas sobre el mismo corpus dan el mismo JSON.

---

## 5. Fases

### F0 — Flag `STACKY_DOCS_GRAPH_ENABLED` + exposición en `/api/docs/sources`

**Objetivo (1 frase).** Dar de alta la flag editable por UI (default OFF) y exponer su valor como key aditiva `graph_enabled` en la respuesta de `/api/docs/sources`, para que el frontend gatee la pestaña sin llamada extra. **Valor:** opt-in seguro, cero cambio de comportamiento.

**Archivos a editar (rutas exactas):**

1. `Stacky Agents/backend/config.py` — agregar 1 atributo junto a las demás flags STACKY (buscar el bloque de `STACKY_RAG_CATALOG_ENABLED` y agregar debajo, mismo patrón textual):
   ```python
   STACKY_DOCS_GRAPH_ENABLED: bool = os.getenv(
       "STACKY_DOCS_GRAPH_ENABLED", "false"
   ).strip().lower() == "true"
   ```
   > El default efectivo en runtime vive ACÁ (`"false"`), no en el FlagSpec (memoria `harness-flag-default-runtime-vs-ui`).

2. `Stacky Agents/backend/services/harness_flags.py`:
   - En `_CATEGORY_KEYS`, tupla `"contexto_memoria"` (harness_flags.py:119-132), agregar al final del bloque:
     ```python
     "STACKY_DOCS_GRAPH_ENABLED",  # Plan 109 — grafo documental read-only
     ```
   - En `FLAG_REGISTRY` agregar 1 `FlagSpec` (copiar el shape de `STACKY_RAG_CATALOG_ENABLED`). Valores EXACTOS:
     ```python
     FlagSpec(
         key="STACKY_DOCS_GRAPH_ENABLED",
         type="bool",
         label="Grafo documental (Plan 109)",
         description=(
             "Plan 109 — Construye un grafo READ-ONLY de la documentación del "
             "proyecto (links markdown, wikilinks [[nombre]] y referencias a "
             "código) y lo expone en GET /api/docs/graph junto a un diagnóstico "
             "de salud documental. Habilita la pestaña 'Cobertura' (y en Plan "
             "111 la pestaña 'Grafo') de la página Docs. No escribe ni modifica "
             "ningún documento. Default OFF."
         ),
         group="global",
         env_only=False,
     ),
     ```
     > **GOTCHA `_CURATED_DEFAULTS_ON` (memoria `harness-flags-default-explicit-gotcha`):** NO pasar `default=False` ni `default=True`. `default_is_known(spec)` es `spec.default is not None` (localizar por símbolo `def default_is_known` en harness_flags.py — hoy línea 2444; las líneas driftean, el símbolo no — C4) y `test_default_known_only_for_curated` exige que SOLO las keys curadas tengan default declarado. Omitir el parámetro `default` (queda `None` → type-zero `False` para la UI, que es lo correcto).
     > **`requires`:** NO declarar `requires` (queda `None`): esta flag no depende de ninguna otra. Por eso NO se toca `_REQUIRES_MAP_FROZEN` en este plan.

3. `Stacky Agents/backend/services/harness_flags_help.py` — agregar 1 entrada `PlainHelp` (mismo shape que las existentes; hay un meta-test de cobertura de ayuda en `tests/test_harness_flags_help.py` que falla si falta):
   ```python
   "STACKY_DOCS_GRAPH_ENABLED": PlainHelp(
       what="Arma un mapa de cómo se conectan entre sí los documentos del proyecto (quién linkea a quién).",
       on_effect="Si la activás: en la página Docs aparece la pestaña 'Cobertura' con métricas del corpus (notas, links, huérfanas) y un semáforo de salud documental. No cambia ningún documento.",
       off_effect="Si la apagás: la página Docs se ve y funciona exactamente como siempre.",
       example="Como el 'graph view' de Obsidian, pero de solo lectura y con un chequeo de salud.",
   ),
   ```

4. `Stacky Agents/backend/services/doc_indexer.py` — NO se toca en F0 (se toca en F2).

5. `Stacky Agents/backend/api/docs.py` — en `get_doc_sources()` (docs.py:52-57), agregar la key aditiva ANTES de devolver:
   ```python
   @bp.get("/sources")
   def get_doc_sources():
       payload = doc_indexer.list_doc_sources(project_name=_get_project_param())
       payload["graph_enabled"] = bool(getattr(config, "STACKY_DOCS_GRAPH_ENABLED", False))  # Plan 109
       return jsonify(payload)
   ```
   (El import `from config import config` ya existe en docs.py:26.)

**Tests PRIMERO — archivo:** `Stacky Agents/backend/tests/test_plan109_flag.py`. Casos:
- `test_flag_registered_in_contexto_memoria` — la key está en la tupla `contexto_memoria` de `_CATEGORY_KEYS` (importar `from services.harness_flags import _CATEGORY_KEYS`; assert `"STACKY_DOCS_GRAPH_ENABLED" in _CATEGORY_KEYS["contexto_memoria"]`).
- `test_flag_default_off` — `from config import config; assert config.STACKY_DOCS_GRAPH_ENABLED is False` (sin env var seteada).
- `test_flag_spec_no_declared_default_and_no_requires` — en `FLAG_REGISTRY`, el spec de la key tiene `spec.default is None` y `spec.requires is None` y `spec.env_only is False`.
- `test_flag_has_plain_help` — la key existe en el dict de ayudas de `harness_flags_help` (importar el dict público del módulo y assert `in`).
- `test_sources_endpoint_exposes_graph_enabled` — con el `app` de test (mismo patrón/fixture que `tests/test_plan89_environments_endpoints.py`: crear app Flask de test y `client.get`), `GET /api/docs/sources` responde 200 y el JSON contiene `graph_enabled` de tipo bool con valor `False` (flag OFF por default).

Registrar el archivo en `Stacky Agents/backend/scripts/run_harness_tests.sh` **y** `run_harness_tests.ps1` (lista `HARNESS_TEST_FILES`). **Obligatorio** (memoria ratchet Plan 49: todo test backend nuevo va en ambos scripts o el meta-test falla). Repetir este registro en F1-F4 con sus archivos.

**Comando de tests (desde `Stacky Agents/backend`):**
```
venv/Scripts/python.exe -m pytest tests/test_plan109_flag.py tests/test_harness_flags.py tests/test_harness_flags_help.py tests/test_harness_flags_requires.py -q
```

**Criterio de aceptación BINARIO:** los 4 archivos en verde (0 fallos). `venv/Scripts/python.exe -c "import config; print(config.config.STACKY_DOCS_GRAPH_ENABLED)"` imprime `False`.

**Flag/default:** la flag misma, default OFF. **Impacto por runtime:** ninguno (capa config; los 3 runtimes ni se enteran). **Fallback:** N/A. **Trabajo del operador:** ninguno (opt-in default off).

---

### F1 — Parsers puros de aristas (sin I/O)

**Objetivo (1 frase).** Tres funciones puras que extraen destinos de links markdown, wikilinks y referencias a código desde un string, con casos borde cerrados. **Valor:** núcleo determinístico y testeable aislado de todo el plan.

**Archivo a crear:** `Stacky Agents/backend/services/doc_graph.py` (en F1 solo los parsers; F2 agrega el builder al MISMO archivo).

**Pseudocódigo EXACTO (regex incluidas):**
```python
"""doc_graph.py — Grafo documental READ-ONLY (Plan 109).

Parsea aristas entre notas markdown y hacia archivos de código, sobre las
fuentes que doc_indexer ya resuelve. NO escribe nada. NO usa LLM. NO hace
retrieval (los 3 motores TF-IDF existentes no se tocan ni se duplican).
"""
from __future__ import annotations

import re

# (a) Links markdown a .md: [texto](ruta.md) o [texto](ruta.md#ancla)
#     Se ignoran destinos http(s):// y mailto:.
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s#]+\.md)(?:#[^)]*)?\)", re.IGNORECASE)

# (b) Wikilinks: [[nombre]] o [[nombre|alias]] (nombre sin | ni ]] ; alias libre)
_WIKILINK_RE = re.compile(r"\[\[([^\]\|\n]+?)(?:\|[^\]\n]*)?\]\]")

# (C1) Bloques de código fenced: ``` ... ``` (o ~~~). Se ELIMINAN antes de
#      parsear links md y wikilinks (ejemplos de código no son aristas).
#      parse_code_refs NO los elimina: las refs a código legítimas suelen
#      escribirse en backticks (inline o fenced) y son justamente lo que se busca.
_FENCED_BLOCK_RE = re.compile(r"^(```|~~~).*?^\1\s*$", re.MULTILINE | re.DOTALL)


def _strip_fenced_blocks(text: str) -> str:
    """Reemplaza cada bloque fenced por '\n' (preserva el resto del texto).
    Fence sin cerrar: se elimina desde el fence hasta el final del texto."""
    stripped = _FENCED_BLOCK_RE.sub("\n", text or "")
    # fence abierto sin cierre → cortar desde ahí
    open_fence = re.search(r"^(```|~~~)", stripped, re.MULTILINE)
    if open_fence:
        stripped = stripped[: open_fence.start()]
    return stripped

# (c) Referencias a código: rutas con al menos un '/' y extensión de código,
#     opcionalmente con ':NNN' de línea; o 'archivo.ext:NNN' sin directorio.
_CODE_EXTS = r"(?:py|ts|tsx|js|jsx|cs|sql|ps1|sh|bat|ya?ml|json|toml|css|html)"
_CODE_PATH_RE = re.compile(
    r"(?<![\w/\\])((?:[\w.\-]+[/\\])+[\w.\-]+\." + _CODE_EXTS + r")(?::\d+)?\b"
)
_CODE_FILELINE_RE = re.compile(
    r"(?<![\w/\\])([\w.\-]+\." + _CODE_EXTS + r"):\d+\b"
)


def parse_markdown_links(text: str) -> list[str]:
    """Destinos .md de links estándar, en orden de aparición, sin duplicados.
    Excluye http(s)://, mailto: y rutas absolutas (C:\\..., /...). Devuelve la
    ruta tal como está escrita, con backslashes normalizados a '/'.
    Ignora links dentro de bloques fenced (C1). Limitación documentada (C8):
    destinos con espacios o %20 NO matchean (regex excluye whitespace)."""
    out: list[str] = []
    for m in _MD_LINK_RE.finditer(_strip_fenced_blocks(text)):
        target = m.group(1).replace("\\", "/").strip()
        low = target.lower()
        if low.startswith(("http://", "https://", "mailto:")):
            continue
        if low.startswith("/") or re.match(r"^[a-z]:", low):
            continue  # absolutas: fuera (anti-traversal; solo relativas)
        if target and target not in out:
            out.append(target)
    return out


def parse_wikilinks(text: str) -> list[str]:
    """Nombres de wikilinks (sin alias), trimmed, sin duplicados, orden de aparición.
    '[[Nota Motor|el motor]]' -> 'Nota Motor'. Ignora vacíos ('[[]]').
    Ignora wikilinks dentro de bloques fenced (C1)."""
    out: list[str] = []
    for m in _WIKILINK_RE.finditer(_strip_fenced_blocks(text)):
        name = m.group(1).strip()
        if name and name not in out:
            out.append(name)
    return out


def parse_code_refs(text: str) -> list[str]:
    """Rutas de código referidas en el texto, normalizadas ('\\'->'/', sin ':NNN',
    sin './' inicial), sin duplicados, orden de aparición. Matchea:
      - 'backend/services/foo.py' y 'backend\\services\\foo.py:123'
      - 'foo.py:123' (archivo con línea, sin directorio)
    NO matchea 'foo.py' pelado sin '/' ni ':NNN' (demasiado ruido)."""
    out: list[str] = []
    for regex in (_CODE_PATH_RE, _CODE_FILELINE_RE):
        for m in regex.finditer(text or ""):
            ref = m.group(1).replace("\\", "/")
            ref = re.sub(r"^\./", "", ref)
            if ref and ref not in out:
                out.append(ref)
    return out
```

**Casos borde que el pseudocódigo cierra (y los tests verifican):**
- Link md con ancla `[x](a/b.md#seccion)` → `a/b.md`.
- Link externo `[x](https://foo.com/a.md)` → ignorado.
- Link absoluto `[x](C:/docs/a.md)` o `[x](/etc/a.md)` → ignorado.
- Wikilink con alias `[[Nota|alias]]` → `Nota`. Wikilink vacío `[[]]` → ignorado. `[[a]] [[a]]` → 1 resultado.
- Ref con línea `backend/services/foo.py:123` → `backend/services/foo.py`.
- Backslashes `backend\services\foo.py` → `backend/services/foo.py`.
- `foo.py` suelto (sin `/` ni `:NNN`) → NO matchea. `foo.py:42` → matchea `foo.py`.
- Texto `None`/`""` → lista vacía (los parsers usan `text or ""`).
- **(C1)** `[[nota]]` o `[x](a.md)` dentro de un bloque ``` fenced ``` → NO generan resultado en `parse_wikilinks`/`parse_markdown_links`; `backend/foo.py:1` dentro del mismo bloque SÍ genera resultado en `parse_code_refs`.
- **(C1)** Fence abierto sin cerrar → todo lo que sigue al fence se ignora para links/wikilinks (no lanza).
- **(C8)** `[x](mi nota.md)` (espacio en el destino) → NO matchea (limitación documentada).

**Tests PRIMERO — archivo:** `Stacky Agents/backend/tests/test_plan109_parsers.py`. Un test por caso borde de la lista anterior (14 tests, nombres `test_md_link_with_anchor`, `test_md_link_external_ignored`, `test_md_link_absolute_ignored`, `test_md_link_space_in_target_not_matched`, `test_wikilink_alias`, `test_wikilink_empty_ignored`, `test_wikilink_dedup`, `test_fenced_block_ignored_for_links_and_wikilinks_but_not_code_refs`, `test_unclosed_fence_ignores_rest`, `test_code_ref_with_line`, `test_code_ref_backslashes`, `test_code_ref_bare_filename_not_matched`, `test_code_ref_fileline_without_dir`, `test_none_and_empty_input`). (El caso orden-sin-duplicados de v1 queda cubierto dentro de `test_wikilink_dedup` y `test_code_ref_with_line` con inputs repetidos.)

**Comando (desde `Stacky Agents/backend`):**
```
venv/Scripts/python.exe -m pytest tests/test_plan109_parsers.py -q
```

**Criterio BINARIO:** 14/14 verdes. `venv/Scripts/python.exe -c "from services.doc_graph import parse_wikilinks; print(parse_wikilinks('[[A|b]]'))"` imprime `['A']`.

**Flag/default:** los parsers no leen flags (puros). **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

### F2 — `build_graph`: nodos, aristas, backlinks, huérfanas + cache por mtime

**Objetivo (1 frase).** Construir el grafo completo (contrato §4.1 sin `doc_health`, que llega en F3) reutilizando `doc_indexer` para enumerar y leer notas, con cache en memoria invalidada por mtime. **Valor:** el corazón del plan; todo lo demás lo consume.

**Archivo a editar:** `Stacky Agents/backend/services/doc_graph.py` (agregar debajo de los parsers de F1).

**Diseño EXACTO:**

```python
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from services import doc_indexer

_MAX_NOTES = 2000            # límite duro de notas a procesar
_MAX_FILE_BYTES = 2_000_000  # archivos más grandes se saltean (con node igual, sin out-edges)
_GRAPH_TTL_SECONDS = 60      # re-chequeo de mtimes como mucho 1 vez por minuto
_MAX_CACHE_ENTRIES = 8       # (C6) tope de payloads cacheados; al superarlo se
                             # elimina la entrada con built_at más viejo

# cache: key -> (built_at_monotonic, fingerprint, payload)
# fingerprint = (n_files, max_mtime_ns, total_size) sobre la lista de archivos
# escaneados. (C3) Si os.stat lanza OSError para un abs_path, ese archivo
# igual cuenta en n_files y aporta mtime_ns=0 y size=0 a max/sum.
_graph_cache: dict[tuple, tuple[float, tuple, dict]] = {}


def invalidate_graph_cache() -> None:
    """Para tests y para forzar re-scan."""
    _graph_cache.clear()
```

**Algoritmo de `build_graph(project_name=None, vscode_prompts_dir=None)` (paso a paso):**

1. **Enumerar fuentes y notas (reusar doc_indexer, NO reimplementar):**
   - `sources_info = doc_indexer.list_doc_sources(project_name)`.
   - Para la fuente `stacky`: `index = doc_indexer.build_index(vscode_prompts_dir)`; recorrer `index["roots"]` recursivamente juntando nodos `kind=="file"`; la ruta absoluta de cada nota = `doc_indexer.STACKY_AGENTS_ROOT / node["path"]` (para agentes con `_absolute_path`, usar esa key).
   - Para cada fuente `kind=="project-docs"` de `sources_info["sources"]`: `idx = doc_indexer.build_project_docs_index(project_name, source_id=fuente["id"])`; recorrer recursivo; ruta absoluta = `Path(fuente["absolute_path"]) / node["path"]`.
   - Acumular `note_files: list[tuple[source_id, rel_path, abs_path]]`, cortando en `_MAX_NOTES` (determinístico: orden de fuentes según `sources_info["sources"]`, dentro de cada fuente orden del índice).
2. **Cache:** `cache_key = ("graph", active_project or "", tuple(sorted(source_ids)), vscode_prompts_dir or "")`. Calcular `fingerprint = (len(note_files), max(st_mtime_ns), sum(st_size))` con `os.stat` sobre cada `abs_path` — **(C3)** si `os.stat` lanza `OSError`, el archivo cuenta igual en `len` y aporta `mtime_ns=0` y `size=0` a `max`/`sum` (con 0 archivos: `fingerprint = (0, 0, 0)`). Semántica del TTL (literal): el TTL limita la frecuencia del stat-scan, no la validez: si `now - built_at < _GRAPH_TTL_SECONDS`, devolver payload cacheado SIN computar fingerprint; si TTL vencido, computar fingerprint y devolver cache si coincide (refrescando `built_at`), o reconstruir si difiere. Así un archivo tocado se refleja como mucho 60 s después, y nunca se re-parsea sin cambios. Al insertar en `_graph_cache`, si `len(_graph_cache) > _MAX_CACHE_ENTRIES`, eliminar la entrada de `built_at` más viejo (C6).
3. **Leer y parsear cada nota:** `content = abs_path.read_text(encoding="utf-8", errors="replace")` (saltear con try/except `OSError`; si `st_size > _MAX_FILE_BYTES`, no leer: nota sin out-edges). Detectar frontmatter: `has_frontmatter = content.lstrip().startswith("---")`.
4. **Resolver aristas:**
   - `parse_markdown_links`: destino relativo se resuelve contra el **directorio de la nota dentro de su fuente** con `posixpath.normpath(posixpath.join(posixpath.dirname(rel_path), target))`; si el resultado empieza con `..` → descartar arista (escape de la fuente); si el path resuelto existe en el set de notas de la MISMA fuente → arista `kind="md"` hacia esa nota; si no existe → arista `kind="md"` hacia nodo `missing:<basename_lower_sin_ext>`.
   - `parse_wikilinks`: resolución por nombre **case-insensitive** contra un índice global `name_index: dict[str, node_id]` donde la key es `basename lower sin extensión .md` de TODAS las notas de TODAS las fuentes. Colisión (dos notas con el mismo basename): gana la de `path` lexicográficamente menor con `source_id` lexicográficamente menor como desempate (determinístico; documentado en el docstring). Sin match → nodo `missing:<nombre_lower>` + arista `kind="wikilink"`.
   - `parse_code_refs`: nodo `code:<ruta>`; `exists = (Path(workspace_root)/ruta).is_file() or (doc_indexer.STACKY_AGENTS_ROOT/ruta).is_file()` donde `workspace_root = sources_info.get("workspace_root")` (si es None, solo se chequea STACKY_AGENTS_ROOT). Arista `kind="code_ref"`.
5. **Grados y huérfanas:** `in_degree`/`out_degree` por conteo de aristas; `orphans` = ids de nodos `kind=="note"` con ambos grados en 0.
6. **Ensamblar payload** según §4.1 (con `doc_health` agregado en F3; en F2 devolver `"doc_health": None`), ordenar nodos/aristas como manda §4.1, cachear y devolver.

**Tests PRIMERO — archivo:** `Stacky Agents/backend/tests/test_plan109_build_graph.py`. Usar `tmp_path` + `monkeypatch` sobre `doc_indexer` (patchear `doc_indexer.list_doc_sources`, `doc_indexer.build_project_docs_index` y `doc_indexer.build_index` para apuntar a un mini-corpus creado en `tmp_path` — patchear EN `services.doc_graph` no hace falta porque el import es `from services import doc_indexer` a nivel módulo: patchear los atributos del módulo `doc_indexer` directamente con `monkeypatch.setattr(doc_indexer, "list_doc_sources", fake)`). Mini-corpus fixture: 4 notas (`a.md` linkea `[x](b.md)` y `[[c]]` y `backend/services/foo.py:10`; `b.md` con frontmatter `---`; `c.md` sin links; `huerfana.md` sin links ni referencias entrantes) + un wikilink roto `[[no-existe]]` en `b.md`. Casos:
- `test_nodes_and_edges_shape` — payload cumple §4.1: keys exactas, ids con prefijos `note:`/`code:`/`missing:`.
- `test_md_link_resolved_same_source` — `a.md → b.md` arista `kind="md"`.
- `test_wikilink_resolved_case_insensitive` — `[[C]]` resuelve a `c.md`.
- `test_wikilink_unresolved_creates_missing_node` — `[[no-existe]]` genera nodo `missing:no-existe` con `exists=False`.
- `test_code_ref_node_and_exists_flag` — nodo `code:backend/services/foo.py` con `exists` correcto (crear el archivo en el workspace fake y assert True; borrarlo y `invalidate_graph_cache()` y assert False).
- `test_orphan_detection` — `huerfana.md` está en `orphans`; `b.md` no.
- `test_md_link_escaping_source_dropped` — `[x](../../fuera.md)` NO genera arista.
- **(C2)** `test_cache_hit_within_ttl` — 2ª llamada dentro del TTL devuelve el payload cacheado SIN re-leer archivos (contador de lecturas: monkeypatchear `Path.read_text` o el helper de lectura y assert que no se invoca en la 2ª llamada).
- **(C2)** `test_ttl_expired_fingerprint_change_rebuilds` — con `monkeypatch.setattr(doc_graph, "_GRAPH_TTL_SECONDS", 0)`, modificar el contenido de una nota (cambia mtime/size) → la llamada siguiente reconstruye y el grafo refleja el cambio (SIN llamar `invalidate_graph_cache()`).
- **(C2)** `test_ttl_expired_fingerprint_same_serves_cache` — con `_GRAPH_TTL_SECONDS = 0` y corpus sin cambios → la llamada siguiente devuelve el payload cacheado sin re-parsear (contador de lecturas en 0).
- `test_invalidate_graph_cache_forces_rebuild` — `invalidate_graph_cache()` → la llamada siguiente re-lee (contador > 0).
- `test_determinism_two_runs_equal_json` — `json.dumps(g1, sort_keys=True) == json.dumps(g2, sort_keys=True)` tras invalidar cache entre corridas.

**Comando (desde `Stacky Agents/backend`):**
```
venv/Scripts/python.exe -m pytest tests/test_plan109_build_graph.py tests/test_plan109_parsers.py -q
```

**Criterio BINARIO:** 12 casos F2 + 14 de F1 verdes.

**Flag/default:** `build_graph` NO lee flags (el gate es del endpoint, F4). **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

### F3 — Clasificador determinístico `classify_doc_health`

**Objetivo (1 frase).** Etiquetar el corpus del proyecto activo con `SIN_DOCS` / `FORMATO_NO_OBSIDIAN` / `INCOMPLETA` / `SANA` con reglas cerradas y razones legibles, como campo `doc_health` del mismo payload. **Valor:** semáforo accionable que alimenta al Documentador (plan 113).

**Archivo a editar:** `Stacky Agents/backend/services/doc_graph.py`.

**Reglas EXACTAS (en orden, primera que aplica gana):**

```python
_CODE_MODULE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".cs", ".sql"}
_MAX_MODULE_SCAN_ENTRIES = 500  # tope de entradas listadas por módulo (performance)


def classify_doc_health(nodes: list[dict], edges: list[dict],
                        workspace_root: str | None) -> dict:
    """Determinístico, sin LLM, NUNCA lanza. Solo considera notas de fuentes
    de PROYECTO (source_id startswith 'project-docs:'): la doc interna de
    Stacky no cuenta para la salud del proyecto del cliente."""
    project_notes = [n for n in nodes
                     if n["kind"] == "note"
                     and n["source_id"].startswith(doc_indexer.PROJECT_DOC_SOURCE_PREFIX)]
    wikilink_edges = sum(1 for e in edges if e["kind"] == "wikilink")
    n_notes = len(project_notes)
    fm = sum(1 for n in project_notes if n.get("has_frontmatter"))
    frontmatter_ratio = (fm / n_notes) if n_notes else 0.0

    # Regla 1 — SIN_DOCS: cero notas de proyecto.
    if n_notes == 0:
        return {"status": "SIN_DOCS",
                "reasons": ["El proyecto activo no tiene ninguna nota .md en sus fuentes de docs."],
                "frontmatter_ratio": 0.0, "wikilink_edges": wikilink_edges,
                "uncovered_modules": []}

    # Regla 2 — FORMATO_NO_OBSIDIAN: hay notas pero 0% frontmatter Y 0 wikilinks.
    if fm == 0 and wikilink_edges == 0:
        return {"status": "FORMATO_NO_OBSIDIAN",
                "reasons": [f"{n_notes} notas sin frontmatter y sin ningún wikilink [[...]]."],
                "frontmatter_ratio": 0.0, "wikilink_edges": 0,
                "uncovered_modules": []}

    # Regla 3 — INCOMPLETA: módulos de código de PRIMER NIVEL sin referencia.
    # Módulo = subdirectorio directo de workspace_root (excluyendo
    # doc_indexer._EXCLUDE_DIRS y los que empiezan con '.') que contenga >=1
    # archivo con extensión de _CODE_MODULE_EXTS en cualquier profundidad
    # (scan con os.walk cortado a _MAX_MODULE_SCAN_ENTRIES entradas por módulo).
    # 'Cubierto' = existe >=1 arista kind='code_ref' cuyo target path
    # (sin el prefijo 'code:') empieza con '<modulo>/'.
    uncovered = _uncovered_modules(edges, workspace_root)  # helper privado, mismas reglas
    if uncovered:
        return {"status": "INCOMPLETA",
                "reasons": [f"{len(uncovered)} módulos de código de primer nivel sin ninguna "
                            f"nota que los referencie: {', '.join(uncovered)}"],
                "frontmatter_ratio": round(frontmatter_ratio, 2),
                "wikilink_edges": wikilink_edges,
                "uncovered_modules": uncovered}

    # Regla 4 — SANA.
    return {"status": "SANA", "reasons": [],
            "frontmatter_ratio": round(frontmatter_ratio, 2),
            "wikilink_edges": wikilink_edges, "uncovered_modules": []}
```

Casos borde cerrados: `workspace_root` None/inexistente → `_uncovered_modules` devuelve `[]` (no se puede evaluar Regla 3 → cae en SANA si pasó 1 y 2); módulos ordenados alfabéticamente; frontmatter = contenido que tras `lstrip()` empieza con `---` (ya computado en F2 como `has_frontmatter`).

**Wiring:** en `build_graph` (F2), reemplazar `"doc_health": None` por `classify_doc_health(nodes, edges, sources_info.get("workspace_root"))`.

**Tests PRIMERO — archivo:** `Stacky Agents/backend/tests/test_plan109_doc_health.py` (unit sobre `classify_doc_health` con nodos/aristas construidos a mano — no necesita filesystem salvo la Regla 3, que usa `tmp_path` como workspace):
- `test_sin_docs_when_no_project_notes` (notas solo de source `stacky` → SIN_DOCS).
- `test_formato_no_obsidian` (2 notas, 0 frontmatter, 0 wikilinks → FORMATO_NO_OBSIDIAN).
- `test_formato_ok_with_only_wikilinks` (0 frontmatter pero 1 wikilink → NO es FORMATO_NO_OBSIDIAN).
- `test_incompleta_uncovered_module` (workspace con `backend/foo.py` y `frontend/app.tsx`; solo arista `code:backend/foo.py` → uncovered `["frontend"]`, INCOMPLETA).
- `test_sana_all_modules_covered`.
- `test_excluded_dirs_not_modules` (crear `node_modules/x.js` y `.git/hooks/x.py` → no cuentan como módulos).
- `test_no_workspace_root_skips_rule3` (workspace_root=None con notas sanas → SANA).
- `test_never_raises_on_garbage` (edges con dicts incompletos → devuelve dict con status válido, no excepción).

**Comando (desde `Stacky Agents/backend`):**
```
venv/Scripts/python.exe -m pytest tests/test_plan109_doc_health.py -q
```

**Criterio BINARIO:** 8/8 verdes.

**Flag/default:** no lee flags. **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

### F4 — Endpoint `GET /api/docs/graph` (read-only, gateado por flag)

**Objetivo (1 frase).** Exponer el grafo por HTTP con gate de flag, parámetro de proyecto y observabilidad, sin tocar los endpoints existentes. **Valor:** contrato consumible por la UI (F5), el plan 111 y el plan 112.

**Archivo a editar:** `Stacky Agents/backend/api/docs.py` — agregar al final:

```python
# ── GET /api/docs/graph ──────────────────────────────────────────────────────

@bp.get("/graph")
def get_docs_graph():
    """Plan 109 — Grafo documental read-only del proyecto activo/indicado.

    Query params: project (opcional, igual semántica que /index);
                  refresh=1 (opcional, [ADICIÓN ARQUITECTO]: invalida la cache
                  y fuerza re-scan antes de construir — read-only igual).
    404 {"ok": false, "error": "docs_graph_disabled"} si la flag está OFF.
    """
    if not bool(getattr(config, "STACKY_DOCS_GRAPH_ENABLED", False)):
        return jsonify({"ok": False, "error": "docs_graph_disabled",
                        "message": "El grafo documental está deshabilitado (STACKY_DOCS_GRAPH_ENABLED)."}), 404

    t0 = time.monotonic()
    from services import doc_graph  # import lazy: no cargar el módulo si la flag está OFF
    if request.args.get("refresh", "").strip() == "1":  # [ADICIÓN ARQUITECTO]
        doc_graph.invalidate_graph_cache()
    try:
        graph = doc_graph.build_graph(
            project_name=_get_project_param(),
            vscode_prompts_dir=_get_vscode_prompts_dir(),
        )
    except Exception as exc:  # nunca 500 sin log estructurado
        logger.warning("docs_api", "docs_graph_failed", detail=str(exc))
        # (C7) el detalle queda en el log; al cliente va un mensaje genérico
        return jsonify({"ok": False, "error": "docs_graph_failed",
                        "message": "No se pudo construir el grafo documental. Ver logs (docs_graph_failed)."}), 500

    logger.info("docs_api", "docs_graph_built",
                nodes=len(graph.get("nodes", [])), edges=len(graph.get("edges", [])),
                duration_ms=round((time.monotonic() - t0) * 1000),
                doc_health=(graph.get("doc_health") or {}).get("status"))
    return jsonify({"ok": True, **graph})
```

(`time`, `jsonify`, `request`, `logger`, `config` ya están importados en docs.py:20-26.)

**Tests PRIMERO — archivo:** `Stacky Agents/backend/tests/test_plan109_graph_endpoint.py` (fixture app+client, mismo patrón que `tests/test_plan89_environments_endpoints.py`; `monkeypatch.setattr(config_module.config, "STACKY_DOCS_GRAPH_ENABLED", True/False)` y monkeypatch de `services.doc_graph.build_graph` para el caso feliz):
- `test_graph_404_when_flag_off` — flag OFF → 404, JSON `error == "docs_graph_disabled"`.
- `test_graph_ok_when_flag_on` — flag ON + `build_graph` mockeado → 200, `ok=True`, keys del contrato §4.1 presentes (`nodes`, `edges`, `orphans`, `stats`, `doc_health`, `sources`, `generated_at`).
- `test_graph_500_wrapped_on_exception` — `build_graph` que lanza → 500 con `error == "docs_graph_failed"` (no traceback HTML).
- `test_docs_endpoints_unchanged_when_flag_off` — **golden de no-regresión:** con flag OFF, `GET /api/docs/sources` devuelve exactamente las mismas keys que hoy MÁS `graph_enabled=False` (única adición sancionada, de F0), y `/api/docs/index` + `/api/docs/content` no cambian en nada (comparar sets de keys de la respuesta contra los actuales, fijados en el test).
- **[ADICIÓN ARQUITECTO]** `test_graph_refresh_param_forces_rebuild` — flag ON, `build_graph` mockeado con contador: `GET /api/docs/graph?refresh=1` invoca `invalidate_graph_cache` (monkeypatch con MagicMock y assert `called`); sin `refresh` no la invoca.

**Comando (desde `Stacky Agents/backend`):**
```
venv/Scripts/python.exe -m pytest tests/test_plan109_graph_endpoint.py -q
```

**Criterio BINARIO:** 5/5 verdes.

**Flag/default:** `STACKY_DOCS_GRAPH_ENABLED` OFF → 404 y cero trabajo de CPU (import lazy). **Impacto por runtime:** ninguno (endpoint HTTP; ningún runner lo llama). **Fallback:** sin flag, el endpoint no existe a efectos prácticos. **Trabajo del operador:** ninguno.

---

### F5 — Frontend: cliente `Docs.getGraph`, modelo puro y pestaña "Cobertura"

**Objetivo (1 frase).** Pestaña "Cobertura" en `DocsPage` (visible solo con flag ON, detectada vía `graph_enabled` de `/sources`) con tabla simple de métricas y lista de huérfanas, solo lectura. **Valor:** primera superficie visible de la serie para el operador.

**Archivos:**

1. **Crear** `Stacky Agents/frontend/src/docs/docGraphModel.ts` — tipos + modelo puro:
   ```ts
   export interface DocGraphNode {
     id: string; kind: "note" | "code" | "missing"; label: string; path: string;
     source_id: string; in_degree: number; out_degree: number;
     has_frontmatter: boolean; exists: boolean;
   }
   export interface DocGraphEdge { source: string; target: string; kind: "md" | "wikilink" | "code_ref"; }
   export interface DocHealth {
     status: "SIN_DOCS" | "FORMATO_NO_OBSIDIAN" | "INCOMPLETA" | "SANA";
     reasons: string[]; frontmatter_ratio: number; wikilink_edges: number;
     uncovered_modules: string[];
   }
   export interface DocGraphResponse {
     ok: boolean; generated_at: string; active_project: string | null;
     sources: { id: string; kind: string; label: string; relative_path: string; absolute_path: string }[];
     nodes: DocGraphNode[]; edges: DocGraphEdge[]; orphans: string[];
     stats: Record<string, number>; doc_health: DocHealth | null;
   }
   export interface DocCoverageSummary {
     notes: number; codeRefs: number; missing: number; totalEdges: number;
     totalBacklinks: number;           // suma de in_degree de nodos kind==="note"
     orphanNotes: DocGraphNode[];      // nodos cuyo id está en orphans, ordenados por path
     sources: number;
     health: DocHealth | null;
   }
   /** Puro y total: tolera arrays vacíos y doc_health null. */
   export function summarizeGraph(graph: DocGraphResponse): DocCoverageSummary { /* derivar de stats+nodes+orphans */ }
   ```
2. **Editar** `Stacky Agents/frontend/src/api/endpoints.ts` — en el objeto `Docs` (endpoints.ts:2649), agregar:
   ```ts
   /** Plan 109 — grafo documental read-only. 404 si la flag está OFF. */
   getGraph: (project?: string): Promise<DocGraphResponse> => {
     const qs = project ? `?project=${encodeURIComponent(project)}` : "";
     return api.get<DocGraphResponse>(`/api/docs/graph${qs}`);
   },
   ```
   y agregar `graph_enabled?: boolean;` al tipo `DocsSourcesResponse` existente (localizar por símbolo `DocsSourcesResponse`, no por línea). Importar los tipos desde `../docs/docGraphModel` o re-declararlos ahí — decisión fija: **importar** desde `docGraphModel.ts` (una sola fuente de tipos).
3. **Crear** `Stacky Agents/frontend/src/components/docs/DocCoveragePanel.tsx`:
   - Props: `{ graph: DocGraphResponse | undefined; isLoading: boolean; error: string | null; onOpenNote?: (node: DocGraphNode) => void }`.
   - **[ADICIÓN ARQUITECTO]** Prop extra `onRefresh?: () => void`: `DocsPage` la cablea a `queryClient.invalidateQueries({ queryKey: ["docs-graph"] })` tras llamar `Docs.getGraph(projectName, { refresh: true })` — implementación fija: `getGraph` acepta segundo parámetro opcional `opts?: { refresh?: boolean }` que agrega `refresh=1` al querystring; el botón "Recargar" (un `<button>` junto al badge de salud) fuerza el re-scan del backend. Si `onRefresh` es undefined, el botón no se renderiza.
   - Render: (a) badge de salud con color por status (`SANA`=verde, `INCOMPLETA`=ámbar, `FORMATO_NO_OBSIDIAN`=ámbar, `SIN_DOCS`=rojo — reusar clases existentes de `DocsPage.module.css` o agregar clases nuevas al final de ese archivo, theme-aware light/dark) + lista `reasons`; (b) `<table>` simple de métricas de `summarizeGraph` (filas: Notas, Aristas totales, Backlinks totales, Huérfanas, Fuentes, Refs a código, Wikilinks rotos=missing); (c) lista de notas huérfanas (máx 50, `<button>` por fila que llama `onOpenNote` si está definido); (d) estados loading/error/vacío.
   - Accesibilidad: botones reales, sin `window.confirm`/`alert`.
4. **Editar** `Stacky Agents/frontend/src/pages/DocsPage.tsx`:
   - Estado nuevo: `const [docsView, setDocsView] = useState<'reader' | 'coverage'>('reader');` — resetear a `'reader'` en el `useEffect` de cambio de proyecto (DocsPage.tsx:31-35).
   - `const graphEnabled = sourcesData?.graph_enabled === true;`
   - Query nueva (solo si `graphEnabled && docsView === 'coverage'`):
     ```ts
     const { data: graphData, isLoading: graphLoading, error: graphError } = useQuery({
       queryKey: ["docs-graph", projectName ?? "active"],
       queryFn: () => Docs.getGraph(projectName),
       enabled: graphEnabled && docsView === "coverage",
       staleTime: 60 * 1000, retry: 1,
     });
     ```
   - UI: barra de pestañas arriba del `<main className={styles.viewerPanel}>` — SOLO se renderiza cuando `graphEnabled` (con flag OFF no aparece NINGÚN elemento nuevo): dos `<button>` "Lector" / "Cobertura" con `aria-pressed`. Cuando `docsView === 'coverage'`, el panel principal renderiza `<DocCoveragePanel graph={graphData} isLoading={graphLoading} error={graphError ? String(graphError) : null} />` en lugar de DocViewer/welcome. El panel lateral (DocTree) queda igual en ambas vistas.

**Tests PRIMERO — archivo:** `Stacky Agents/frontend/src/docs/docGraphModel.test.ts` (vitest, modelo puro):
- `summarizes empty graph` — arrays vacíos → todos los contadores 0, `orphanNotes=[]`, no lanza.
- `counts backlinks as sum of note in_degree`.
- `orphan notes resolved from ids and sorted by path`.
- `tolerates null doc_health`.
- `missing and code nodes not counted as notes`.

> **Nota honesta de entorno (disclosure preexistente, plan 107):** los tests `.test.tsx` de componentes están BLOQUEADOS en este checkout (`@testing-library/react`/`jsdom` no instalados). Por eso el test obligatorio de F5 es el del **modelo puro** (`.test.ts`, corre con vitest sin DOM) + `tsc --noEmit`. NO crear `DocCoveragePanel.test.tsx` como criterio de aceptación.

**Comando (desde `Stacky Agents/frontend`):**
```
npx vitest run src/docs/docGraphModel.test.ts
npx tsc --noEmit
```

**Criterio BINARIO:** 5/5 vitest verdes + `tsc --noEmit` 0 errores. Con flag OFF (default), `DocsPage` no renderiza ningún elemento nuevo (garantizado por el gate `graphEnabled` que nace de `graph_enabled=false`).

**Flag/default:** `STACKY_DOCS_GRAPH_ENABLED` OFF → pestañas ausentes, cero fetch nuevo (la query tiene `enabled: graphEnabled && ...`). **Impacto por runtime:** ninguno. **Fallback:** DocsPage idéntica a hoy. **Trabajo del operador:** ninguno (opt-in default off).

---

### F6 — Cierre: no-regresión global y DoD

**Objetivo (1 frase).** Sellar el plan: registro de tests, no-regresión dirigida y checklist final.

**Acciones:**
1. Confirmar registro de los 5 archivos de test backend nuevos (`test_plan109_flag.py`, `test_plan109_parsers.py`, `test_plan109_build_graph.py`, `test_plan109_doc_health.py`, `test_plan109_graph_endpoint.py`) en `run_harness_tests.sh` **y** `.ps1`.
2. `Stacky Agents/backend/harness_defaults.env` — **NO** editar a mano; el generador real es `deployment/export_harness_defaults.py` (memoria drift 87-91). La flag nueva default OFF no exige cambios en el `.env` del deploy.
3. No-regresión backend (desde `Stacky Agents/backend`):
   ```
   venv/Scripts/python.exe -m pytest tests/test_plan109_flag.py tests/test_plan109_parsers.py tests/test_plan109_build_graph.py tests/test_plan109_doc_health.py tests/test_plan109_graph_endpoint.py tests/test_harness_flags.py tests/test_harness_flags_help.py tests/test_harness_flags_requires.py -q
   ```
4. Frontend (desde `Stacky Agents/frontend`):
   ```
   npx vitest run src/docs/docGraphModel.test.ts
   npx tsc --noEmit
   ```

**Criterio BINARIO global (DoD):**
- [ ] Todos los comandos de F0-F6 en verde; `tsc --noEmit` 0 errores.
- [ ] Con flag OFF: `/api/docs/sources|index|content` byte-idénticos a hoy salvo la key aditiva `graph_enabled=false`; `/api/docs/graph` responde 404; DocsPage sin elementos nuevos.
- [ ] `/api/docs/graph` con flag ON cumple el contrato §4.1 (nodos/aristas/orphans/stats/doc_health, determinístico).
- [ ] Cero motores TF-IDF nuevos (el módulo `doc_graph.py` no importa `rag_retriever`, `docs_rag` ni `memory_store`, y no computa similitud alguna — verificable por lectura del diff).
- [ ] Los 5 tests backend registrados en ambos scripts del arnés.

---

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Escaneo caro en corpus grandes en cada request. | Cache con TTL 60 s + fingerprint por mtime/size (F2); límites `_MAX_NOTES=2000` y `_MAX_FILE_BYTES=2MB`. |
| Falsos positivos en `parse_code_refs` (ruido). | Regex conservadora: exige `/` en la ruta o `:NNN`; `foo.py` pelado NO matchea (F1, test binario). |
| Aristas falsas por ejemplos de código en las notas (C1). | Bloques fenced eliminados antes de parsear links md y wikilinks (`_strip_fenced_blocks`, F1, 2 tests binarios). |
| Colisión de nombres de wikilinks entre fuentes. | Regla determinística documentada: path lexicográficamente menor gana (F2). El plan 111 usa el MISMO índice. |
| Path traversal por links `../..`. | Aristas que escapan la fuente se descartan (F2); la lectura de archivos reusa las rutas absolutas que `doc_indexer` ya whitelistó — no hay lectura por input del usuario. |
| Regla 3 (INCOMPLETA) escanea el workspace y puede ser lenta. | Solo subdirectorios de primer nivel, excludes de `doc_indexer`, tope `_MAX_MODULE_SCAN_ENTRIES=500` por módulo, y corre solo dentro de `build_graph` (cacheado). |
| Drift de payload que rompa 111/112. | §4.1 es contrato congelado; `test_graph_ok_when_flag_on` fija las keys. Cambios = plan nuevo. |
| Romper `/api/docs/sources` para consumidores actuales. | Key ADITIVA `graph_enabled`; golden `test_docs_endpoints_unchanged_when_flag_off` (F4). |

---

## 7. Fuera de scope

- Renderizar el grafo visualmente (plan 111: Graph View canvas).
- Wikilinks clickeables y backlinks en el visor (plan 111).
- Usar el grafo en retrieval (plan 112).
- Escribir/corregir/crear documentación (plan 113, Documentador).
- Detección de aristas "stale" (plan 114; el campo se tolera pero no se produce acá).
- Cualquier embedding/TF-IDF/similitud (prohibido: ya hay 3 motores).
- Watchers de filesystem (la invalidación es por mtime bajo demanda).

---

## 8. Glosario (términos para modelos menores)

- **Fuente de docs:** cada raíz que `doc_indexer.list_doc_sources()` devuelve (`stacky` o `project-docs:<rel>`); ver doc_indexer.py:494-528.
- **Nota:** archivo `.md` dentro de una fuente.
- **Wikilink:** sintaxis Obsidian `[[nombre]]` o `[[nombre|alias]]`; resuelve por basename sin extensión, case-insensitive.
- **Backlink:** arista entrante a una nota (in_degree).
- **Huérfana:** nota con in_degree 0 y out_degree 0.
- **Frontmatter:** bloque YAML inicial delimitado por `---` al comienzo del archivo.
- **doc_health:** clasificación determinística del corpus del proyecto (§F3), pensada para que el Documentador (plan 113) decida qué hacer.
- **FlagSpec / `HarnessFlagsPanel`:** registro declarativo de flags (`services/harness_flags.py`) y su panel de UI; `env_only=False` = editable desde la UI.
- **venv del repo:** `Stacky Agents/backend/venv` (Python 3.13). Correr pytest **por archivo** (memoria: la suite completa tiene ruido preexistente).

---

## 9. Orden de implementación (secuencial)

1. **F0** — flag + `graph_enabled` en `/sources` y sus tests.
2. **F1** — parsers puros y sus 14 tests.
3. **F2** — `build_graph` + cache y sus 12 tests.
4. **F3** — `classify_doc_health` + wiring y sus 8 tests.
5. **F4** — endpoint `/api/docs/graph` y sus 5 tests (incluye golden de no-regresión y `refresh=1`).
6. **F5** — cliente + modelo puro + pestaña Cobertura (vitest + tsc).
7. **F6** — cierre, no-regresión, DoD.

---

## 10. Definición de Hecho (DoD) — resumen binario

Hecho cuando: (a) las 5 suites backend nuevas + 3 suites del arnés (flags/help/requires) y la suite vitest nueva están verdes; (b) `tsc --noEmit` 0 errores; (c) con flag OFF el sistema es byte-idéntico a hoy salvo `graph_enabled=false` aditivo en `/sources`; (d) `/api/docs/graph` cumple el contrato §4.1 y es determinístico; (e) `doc_health` clasifica los 4 estados con las reglas de F3; (f) tests registrados en ambos scripts del arnés; (g) cero motores de similitud nuevos.
