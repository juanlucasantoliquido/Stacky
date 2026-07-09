# Plan 112 — Retrieval híbrido en docs-rag (léxico TF-IDF + expansión 1-hop por grafo + prior de backlinks)

> **Estado:** CRITICADO v2 — 2026-07-09 (v1 → v2 por `criticar-y-mejorar-plan`)
> **Veredicto del juez:** APROBADO-CON-CAMBIOS (C1-C3 IMPORTANTES resueltos en esta v2; sin bloqueantes)
>
> **CHANGELOG v1 → v2:**
> - **C1 (IMPORTANTE):** `search_hybrid` devolvía la lista combinada SIN tope: base hits + TODOS los chunks de hasta 8 ficheros vecinos por hit → `/docs-rag/search` podía responder 10x el `top_k` pedido. Ahora cap literal `reranked[: top_k * _HYBRID_RESULT_CAP_FACTOR]` (factor 3) + test `test_result_count_capped`.
> - **C2 (IMPORTANTE):** el fallback por basename del mapeo `file_path ↔ node.path` estaba solo enunciado ("documentar el fallback") pero el pseudocódigo de F1 no lo implementaba — si los paths difieren, el híbrido degradaba en silencio y el KPI moría. Fallback por basename especificado literal (colisión → se omite, determinístico) + test `test_basename_fallback_mapping`.
> - **C3 (IMPORTANTE):** "actualizar `_REQUIRES_MAP_FROZEN` si el meta-test lo exige" era condicional/vago para un modelo menor. Instrucción literal: espejar el patrón EXISTENTE de `STACKY_RAG_CATALOG_TOP_K` (FlagSpec con `requires="STACKY_RAG_CATALOG_ENABLED"`, harness_flags.py:1447) para las 3 numéricas.
> - **C4 (MENOR):** contradicción docstring/código en `_rerank_with_backlinks` resuelta: NO se crean DocHit nuevos ni se muta el score; el score combinado es SOLO clave de orden (los scores visibles siguen siendo los léxicos).
> - **C5 (MENOR):** `test_backlink_prior_reorders_hubs` con valores exactos (scores 0.50 vs 0.48; backlinks 0 vs 10) — "score léxico similar" era subjetivo.
> - **[ADICIÓN ARQUITECTO]:** parámetro opcional `debug_hybrid` en `POST /docs-rag/search` (solo con flag ON) que agrega un bloque ADITIVO `hybrid_debug` (ficheros léxicos, ficheros expandidos, pesos efectivos) — el operador ve el efecto del híbrido en 1 request, sin tocar el shape con flag OFF. +1 test en F3.
> **Serie:** Documentación agéntica Obsidian (109 → 111 → **112**; alimenta al Documentador del plan 113). El número 110 quedó tomado por un plan ajeno (Revisor de PRs).
> **Pipeline:** este documento pasó `proponer` (este estado). Sigue `criticar-y-mejorar-plan` → `implementar-plan-stacky` → `supervisar-implementaciones-planes`.
> **Depende de:** Plan 109 (`services/doc_graph.build_graph`, aristas y `in_degree` por nodo, contrato §4.1). **Reutiliza** `services/docs_rag.py` (motor TF-IDF por proyecto) — **PROHIBIDO crear un cuarto motor léxico** (ya hay 3: `rag_retriever.py`, `docs_rag.py`, `memory_store.py`).

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** El motor `docs_rag` ancla bien por término léxico (TF-IDF coseno, `docs_rag.py:257 search()`) pero falla en **recall estructural**: cuando la respuesta vive en la nota *vecina* (linkeada) y no contiene el término de la query, no aparece. Este plan agrega, **detrás de una flag OFF por default**, un modo de retrieval **híbrido**: (a) toma los top-K hits léxicos de siempre; (b) **expande 1 salto** por las aristas del grafo documental (plan 109) para traer chunks de notas directamente enlazadas, con score heredado atenuado; (c) **reordena** con un prior de backlinks — `score_final = alpha*coseno + beta*log(1+backlinks)` — para que las notas-hub (muy referenciadas) suban. Además **cierra el bug del "DocConsultor fantasma"** (`api/docs_rag.py:32` apunta a un `.agent.md` que no existe y `_read_agent_system_prompt` devuelve `""` en silencio): se agrega persona de fallback built-in + warning no-silencioso. Con la flag OFF, el comportamiento es **byte-idéntico** al actual (patrón plan 64).

**KPI / impacto esperado.**
- **+Recall estructural (binario):** existe un test con un corpus donde la respuesta a la query está SOLO en la nota vecina; con flag OFF NO aparece en los resultados, con flag ON SÍ aparece. Es el KPI central.
- **Cero regresión (binario, patrón plan 64):** con `STACKY_DOCS_RAG_HYBRID_ENABLED` OFF, `search()` y `POST /docs-rag/search` devuelven exactamente los mismos `DocHit`/JSON que hoy (test golden byte-idéntico).
- **Observabilidad A/B:** `GET /docs-rag/stats` expone un bloque `hybrid` con contadores (queries totales, queries donde la expansión aportó ≥1 resultado nuevo, hits léxicos vs agregados por expansión) para que el operador vea si el modo aporta antes de dejarlo prendido.
- **Chat con persona siempre:** el chat de docs nunca más corre con system prompt vacío; si el `.agent.md` no está, usa una persona consultora built-in y loguea warning.

---

## 2. Por qué ahora / gap que cierra

1. `services/docs_rag.py:257 search()` hace TF-IDF coseno + "expansión de ficheros" (trae todos los chunks del MISMO fichero de un top hit, `docs_rag.py:311-347`). **No cruza a ficheros vecinos por links** — ese es justo el recall que el grafo del plan 109 habilita.
2. El plan 109 ya entrega aristas y `in_degree` (backlinks) por nodo. Sin este plan, ese dato solo sirve para *ver*; acá empieza a *mejorar el retrieval de los agentes*.
3. `api/docs_rag.py:32 _DEFAULT_AGENT = "DocConsultor.agent.md"` no existe como archivo (los `.agent.md` están gitignoreados y ninguno provee esa persona); `_read_agent_system_prompt` devuelve `""` cuando `get_agent_by_filename` da `None` (`api/docs_rag.py:53-54`) **sin loguear nada** → el chat corre sin persona en silencio. Se arregla acá porque este plan ya toca ese módulo.
4. Es el tercer plan de la serie: 109 mide, 111 muestra, **112 usa el grafo en retrieval**. El 113 (Documentador) se apoya en los tres.

---

## 3. Principios y guardarraíles (NO negociables — codificados en las fases)

- **3 runtimes con paridad total.** Backend puro (Python, regex/álgebra léxica + lectura del grafo). Ningún runtime LLM interviene en el retrieval. El chat (que sí usa runtime) no cambia su selección de runtime; solo gana persona de fallback. Paridad total.
- **Cero motor nuevo.** Se EXTIENDE `docs_rag.py` con funciones nuevas; NO se importa ni duplica `rag_retriever`/`memory_store`; NO se agrega otra tabla de índice. La expansión reusa los `DocChunk` ya indexados.
- **Flag OFF = byte-idéntico (patrón plan 64).** `search()` conserva su firma y comportamiento; el camino híbrido es una función NUEVA (`search_hybrid`) que la ruta invoca SOLO con la flag ON. Golden test lo prueba.
- **Cero trabajo extra al operador.** Opt-in default OFF, editable por UI (`HarnessFlagsPanel`). Los pesos `alpha`/`beta` tienen defaults seguros; el operador no necesita tocarlos.
- **Human-in-the-loop / read-only.** El retrieval no escribe nada. La persona de fallback no cambia el flujo de aprobación del chat.
- **No degradar performance.** La expansión 1-hop se acota (máx N vecinos, chunks ya en memoria); el grafo se lee de su cache (plan 109, TTL 60 s). Si `build_graph` falla, el híbrido **degrada a léxico puro** (nunca rompe la búsqueda).
- **Mono-operador sin auth.** Nada de identidad.
- **Sin ambigüedad para modelos menores.** Cada fase con archivo, símbolo, pseudocódigo, test + comando con venv, criterio binario, flag + default.

---

## 4. Nombres canónicos (usar EXACTAMENTE estos)

| Concepto | Nombre exacto |
|---|---|
| Flag maestra | `STACKY_DOCS_RAG_HYBRID_ENABLED` (bool, default efectivo OFF) |
| Peso coseno | `STACKY_DOCS_RAG_HYBRID_ALPHA` (float, default efectivo `1.0`, `min_value=0.0`, `max_value=10.0`) |
| Peso backlinks | `STACKY_DOCS_RAG_HYBRID_BETA` (float, default efectivo `0.15`, `min_value=0.0`, `max_value=10.0`) |
| Tope de vecinos por hit | `STACKY_DOCS_RAG_HYBRID_MAX_NEIGHBORS` (int, default efectivo `8`, `min_value=0`, `max_value=100`) |
| Función híbrida nueva | `search_hybrid(project_name, query, top_k=5, expand_files=True) -> list[DocHit]` en `services/docs_rag.py` |
| Helper de reordenamiento | `_rerank_with_backlinks(hits, backlink_index, alpha, beta) -> list[DocHit]` |
| Índice backlinks (por file_path) | `_build_backlink_index(project_name) -> dict[str, int]` |
| Telemetría A/B | `_hybrid_telemetry` (dict módulo) + `record_hybrid_query(...)` + reset `_reset_hybrid_telemetry()` |
| Persona de fallback | `_DEFAULT_DOC_CONSULTOR_PROMPT` (const str en `api/docs_rag.py`) |

---

## 5. Fases

### F0 — Flags (1 bool + 2 float + 1 int) con bounds declarativos

**Objetivo (1 frase).** Dar de alta las 4 flags editables por UI (default seguro), con bounds numéricos (patrón plan 83). **Valor:** control opt-in sin tocar comportamiento.

**Archivos a editar:**
1. `Stacky Agents/backend/config.py` — 4 atributos (junto a las flags STACKY existentes):
   ```python
   STACKY_DOCS_RAG_HYBRID_ENABLED: bool = os.getenv("STACKY_DOCS_RAG_HYBRID_ENABLED", "false").strip().lower() == "true"
   STACKY_DOCS_RAG_HYBRID_ALPHA: float = float(os.getenv("STACKY_DOCS_RAG_HYBRID_ALPHA", "1.0") or "1.0")
   STACKY_DOCS_RAG_HYBRID_BETA: float = float(os.getenv("STACKY_DOCS_RAG_HYBRID_BETA", "0.15") or "0.15")
   STACKY_DOCS_RAG_HYBRID_MAX_NEIGHBORS: int = int(os.getenv("STACKY_DOCS_RAG_HYBRID_MAX_NEIGHBORS", "8") or "8")
   ```
   > Los defaults efectivos viven ACÁ. Envolver los `float()`/`int()` en try/except a nivel módulo NO hace falta si se usa el patrón `or "default"`; para robustez ante valores basura, el helper de lectura en runtime (F2) hace `getattr(config, ..., default)` y clamp a bounds.
2. `Stacky Agents/backend/services/harness_flags.py`:
   - En `_CATEGORY_KEYS["contexto_memoria"]` agregar las 4 keys.
   - En `FLAG_REGISTRY`, 4 `FlagSpec`. La bool copia el shape de `STACKY_DOCS_GRAPH_ENABLED` (plan 109, **sin `default=`**, `env_only=False`). Las numéricas con `type="float"`/`"int"`, `min_value`/`max_value` (ver tabla §4), `env_only=False`, **sin `default=`** (gotcha `_CURATED_DEFAULTS_ON`). Descripciones que expliquen: hybrid = "expandir 1 salto por links + priorizar notas muy referenciadas"; alpha = peso del match léxico; beta = peso del prior de backlinks; max_neighbors = tope de notas vecinas traídas por hit.
   - `requires`: declarar `requires="STACKY_DOCS_RAG_HYBRID_ENABLED"` en las 3 numéricas (NO en la master). **(C3) Instrucción literal:** copiar EXACTAMENTE el patrón existente de `STACKY_RAG_CATALOG_TOP_K` (FlagSpec con `requires="STACKY_RAG_CATALOG_ENABLED"`, hoy harness_flags.py:1447 — localizar por símbolo). Es profundidad-1 contra una master bool (gotcha R4 del plan 104: OK). Si `test_harness_flags_requires.py` falla por un mapa congelado, agregar las 3 keys nuevas a ese mapa con el MISMO shape que tengan ahí las keys de `STACKY_RAG_CATALOG_*` — nada más.
3. `Stacky Agents/backend/services/harness_flags_help.py` — 4 entradas `PlainHelp` (what/on_effect/off_effect/example en español llano).

**Tests PRIMERO — archivo:** `Stacky Agents/backend/tests/test_plan112_flags.py`:
- `test_flags_registered_in_contexto_memoria` (las 4 en la categoría).
- `test_hybrid_default_off` (`config.STACKY_DOCS_RAG_HYBRID_ENABLED is False`).
- `test_numeric_defaults` (alpha 1.0, beta 0.15, max_neighbors 8).
- `test_numeric_bounds_declared` (los FlagSpec tienen min_value/max_value correctos).
- `test_numeric_flags_require_master` (las 3 numéricas tienen `requires == "STACKY_DOCS_RAG_HYBRID_ENABLED"`).
- `test_flags_have_plain_help` (las 4 en el dict de ayudas).

Registrar el archivo en `run_harness_tests.sh` **y** `.ps1` (obligatorio, ratchet plan 49).

**Comando (desde `Stacky Agents/backend`):**
```
venv/Scripts/python.exe -m pytest tests/test_plan112_flags.py tests/test_harness_flags.py tests/test_harness_flags_help.py tests/test_harness_flags_requires.py -q
```

**Criterio BINARIO:** 4 archivos verdes.

**Flag/default:** las flags mismas, defaults seguros. **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno (opt-in default off).

---

### F1 — Índice de backlinks por `file_path` (puente grafo↔docs_rag)

**Objetivo (1 frase).** Traducir el grafo del plan 109 a un mapa `file_path_docs_rag -> in_degree` y a un mapa de vecindad `file_path -> [file_paths vecinos]`, resolviendo la diferencia de identidad entre ambos mundos. **Valor:** el puente sin el cual la expansión y el prior no pueden computarse.

**Problema de identidad (explícito):** `docs_rag` guarda `DocChunk.file_path` = ruta del fichero **relativa a la carpeta de docs del proyecto** (como la indexa `index_project`). El grafo 109 usa ids `note:<source_id>:<path>`. La resolución es por **coincidencia de `path` de nodo con el `file_path` del chunk** dentro de las fuentes `project-docs:*`. Regla determinista (C2, implementada en el pseudocódigo de abajo): normalizar ambos con `/` y comparar exacto; **fallback por basename** para los nodos que no matchearon exacto: se indexa `basename_lower(node.path) -> node_id` y se resuelve contra `basename_lower(chunk.file_path)`; si DOS nodos comparten basename en el fallback, ese basename se OMITE del fallback (ambiguo → determinístico, sin adivinar). El fallback existe porque `doc_indexer` puede descubrir varias carpetas `docs` (fuentes anidadas) y `docs_rag` indexa una sola raíz: los relativos pueden diferir en prefijo.

**Archivo a editar:** `Stacky Agents/backend/services/docs_rag.py` (agregar helpers; NO tocar `search`).

**Pseudocódigo EXACTO:**
```python
def _build_backlink_index(project_name: str) -> tuple[dict[str, int], dict[str, list[str]]]:
    """Devuelve (backlinks_by_path, neighbors_by_path) para las notas de PROYECTO.
    - backlinks_by_path[file_path] = in_degree del nodo nota correspondiente.
    - neighbors_by_path[file_path] = file_paths de notas a 1 arista (out o in), dedup.
    Si el grafo no está disponible o la flag 109 está OFF, devuelve ({}, {}):
    el híbrido degrada a léxico puro sin romper."""
    try:
        from services import doc_graph
        from config import config
        if not getattr(config, "STACKY_DOCS_GRAPH_ENABLED", False):
            return {}, {}
        graph = doc_graph.build_graph(project_name=project_name)
    except Exception as exc:
        logger.warning("docs_rag: hybrid backlink index unavailable: %s", exc)
        return {}, {}

    # nodo nota -> file_path estilo docs_rag (path relativo a la fuente project-docs)
    id_to_path: dict[str, str] = {}
    backlinks: dict[str, int] = {}
    for n in graph.get("nodes", []):
        if n.get("kind") != "note" or not str(n.get("source_id", "")).startswith("project-docs"):
            continue
        p = str(n["path"]).replace("\\", "/")
        id_to_path[n["id"]] = p
        backlinks[p] = int(n.get("in_degree", 0))

    # (C2) Fallback por basename para chunks cuyo file_path no matchea exacto:
    # se aplica al construir los mapas de salida, ANTES de las aristas.
    # 1. chunk_paths = file_paths distintos presentes en la tabla DocChunk del proyecto.
    # 2. exact = {p for p in chunk_paths if p in backlinks}  (match exacto, camino feliz)
    # 3. Para los chunk_paths NO exactos: base_index = {basename_lower(node_path): node_path
    #    for node_path in backlinks}, construido OMITIENDO los basenames repetidos
    #    (ambiguos). Si basename_lower(chunk_path) está en base_index, se agrega un
    #    alias: backlinks[chunk_path] = backlinks[node_path_resuelto] y las aristas
    #    de ese nodo se reportan bajo chunk_path en neighbors (remap del alias).
    # 4. Sin match ni por basename → ese chunk queda sin backlinks/vecinos (0, []).
    neighbors: dict[str, list[str]] = {}
    for e in graph.get("edges", []):
        s, t = e.get("source"), e.get("target")
        sp, tp = id_to_path.get(s), id_to_path.get(t)
        if sp and tp:
            neighbors.setdefault(sp, []).append(tp)
            neighbors.setdefault(tp, []).append(sp)   # vecindad no dirigida (1-hop en cualquier sentido)
    # dedup preservando orden
    for k in list(neighbors):
        seen, out = set(), []
        for v in neighbors[k]:
            if v not in seen and v != k:
                seen.add(v); out.append(v)
        neighbors[k] = out
    return backlinks, neighbors
```

**Tests PRIMERO — archivo:** `Stacky Agents/backend/tests/test_plan112_backlink_index.py` (monkeypatch `doc_graph.build_graph` con un grafo fake + `config.STACKY_DOCS_GRAPH_ENABLED=True`):
- `test_backlinks_by_path_from_in_degree`.
- `test_neighbors_undirected_dedup`.
- `test_returns_empty_when_graph_flag_off`.
- `test_returns_empty_and_logs_when_build_graph_raises` (degradación segura).
- `test_ignores_non_project_and_code_nodes`.
- **(C2)** `test_basename_fallback_mapping` — caso 1: chunk `file_path="a.md"` y nodo `path="sub/a.md"` → el fallback resuelve por basename y `backlinks["a.md"]` hereda el `in_degree` del nodo. Caso 2: DOS nodos `x/a.md` e `y/a.md` → el basename `a.md` es ambiguo y se omite del fallback (el chunk queda con 0 backlinks, sin alias y sin excepción).

**Comando (desde `Stacky Agents/backend`):**
```
venv/Scripts/python.exe -m pytest tests/test_plan112_backlink_index.py -q
```

**Criterio BINARIO:** 6/6 verdes.

**Flag/default:** lee `STACKY_DOCS_GRAPH_ENABLED` (109); si OFF → `({}, {})`. **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

### F2 — `search_hybrid` + `_rerank_with_backlinks` (expansión 1-hop + prior)

**Objetivo (1 frase).** Función nueva que produce los hits léxicos, agrega chunks de notas vecinas con score heredado atenuado y reordena con el prior de backlinks — sin tocar `search()`. **Valor:** el corazón del recall estructural.

**Archivo a editar:** `Stacky Agents/backend/services/docs_rag.py`.

**Pseudocódigo EXACTO:**
```python
def _read_hybrid_weights() -> tuple[float, float, int]:
    from config import config
    def _clamp(v, lo, hi): return max(lo, min(hi, v))
    alpha = _clamp(float(getattr(config, "STACKY_DOCS_RAG_HYBRID_ALPHA", 1.0)), 0.0, 10.0)
    beta  = _clamp(float(getattr(config, "STACKY_DOCS_RAG_HYBRID_BETA", 0.15)), 0.0, 10.0)
    maxn  = int(_clamp(int(getattr(config, "STACKY_DOCS_RAG_HYBRID_MAX_NEIGHBORS", 8)), 0, 100))
    return alpha, beta, maxn


_HYBRID_RESULT_CAP_FACTOR = 3  # (C1) tope duro: len(resultado) <= top_k * 3


def _rerank_with_backlinks(hits: list[DocHit], backlinks: dict[str, int],
                           alpha: float, beta: float) -> list[DocHit]:
    """Reordena: clave = alpha*score + beta*log(1+backlinks(file)).
    Estable ante empates (sorted es estable: mismo orden relativo previo).
    (C4) NO muta los DocHit ni crea copias: la clave combinada es SOLO para
    ordenar; los scores visibles siguen siendo los léxicos originales
    (los vecinos agregados muestran score 0.0)."""
    import math
    def _key(h):
        bl = backlinks.get(h.file_path, 0)
        return alpha * h.score + beta * math.log1p(bl)
    ranked = sorted(hits, key=_key, reverse=True)
    return ranked


def search_hybrid(project_name: str, query: str, top_k: int = 5,
                  expand_files: bool = True) -> list[DocHit]:
    """Retrieval híbrido: léxico (search) + expansión 1-hop por grafo + prior backlinks.
    Contrato: si no hay grafo (flag 109 OFF o error) degrada EXACTAMENTE a search()."""
    alpha, beta, max_neighbors = _read_hybrid_weights()
    base_hits = search(project_name, query, top_k=top_k, expand_files=expand_files)
    backlinks, neighbors = _build_backlink_index(project_name)
    if not neighbors and not backlinks:
        record_hybrid_query(lexical=len(base_hits), added=0, new_from_expansion=False)
        return base_hits  # degradación a léxico puro

    # 1-hop: para cada file_path presente en los top hits léxicos, traer chunks de vecinos
    lexical_files = []
    for h in base_hits:
        if h.file_path not in lexical_files:
            lexical_files.append(h.file_path)
    neighbor_files: list[str] = []
    for fp in lexical_files:
        for nb in neighbors.get(fp, [])[:max_neighbors]:
            if nb not in lexical_files and nb not in neighbor_files:
                neighbor_files.append(nb)

    added: list[DocHit] = []
    if neighbor_files:
        with session_scope() as session:
            for nb in neighbor_files:
                for fc in (session.query(DocChunk)
                           .filter_by(project_name=project_name, file_path=nb)
                           .order_by(DocChunk.id).all()):
                    added.append(DocHit(file_path=fc.file_path,
                                        section_heading=fc.section_heading,
                                        chunk_text=fc.chunk_text,
                                        score=0.0))  # relevante por vecindad, sin score léxico
    combined = base_hits + added
    reranked = _rerank_with_backlinks(combined, backlinks, alpha, beta)
    reranked = reranked[: max(1, top_k) * _HYBRID_RESULT_CAP_FACTOR]  # (C1) tope duro
    record_hybrid_query(lexical=len(base_hits), added=len(added),
                        new_from_expansion=bool(added))
    return reranked
```

**Casos borde cerrados:** grafo vacío → `search()` puro; `max_neighbors=0` → sin expansión, pero SÍ rerank por backlinks (sigue mejorando orden); nota vecina sin chunks indexados → no aporta; empates → orden estable; **(C1)** el resultado final NUNCA supera `top_k * 3` elementos (los base hits, mejor rankeados, sobreviven al corte salvo que el prior los hunda — comportamiento deseado).

**Tests PRIMERO — archivo:** `Stacky Agents/backend/tests/test_plan112_search_hybrid.py` (corpus fake en DB de test + monkeypatch de `_build_backlink_index` para inyectar backlinks/neighbors deterministas):
- `test_degrades_to_search_when_no_graph` — con `_build_backlink_index` → `({},{})`, `search_hybrid == search` (mismos DocHit, mismo orden).
- `test_pulls_neighbor_note_chunk` — **KPI CENTRAL:** query cuyo término solo está en `a.md`, respuesta en `b.md` (vecina, sin el término); `search` no trae `b.md`, `search_hybrid` sí.
- `test_backlink_prior_reorders_hubs` — **(C5) valores exactos:** hit A score `0.50` con `backlinks=0` vs hit B score `0.48` con `backlinks=10`; con `alpha=1.0, beta=0.15`: clave A = 0.50, clave B = 0.48 + 0.15*log1p(10) ≈ 0.8397 → B queda primero.
- `test_max_neighbors_zero_still_reranks` — sin expansión pero rerank aplicado.
- `test_does_not_mutate_base_hits` — los `DocHit` de `search` conservan su `score` original.
- `test_stable_on_ties`.
- **(C1)** `test_result_count_capped` — corpus con muchos vecinos/chunks: `len(search_hybrid(..., top_k=5)) <= 15`.

**Comando (desde `Stacky Agents/backend`):**
```
venv/Scripts/python.exe -m pytest tests/test_plan112_search_hybrid.py tests/test_plan112_backlink_index.py -q
```

**Criterio BINARIO:** 7 + 6 verdes.

**Flag/default:** `search_hybrid` NO lee la master (la ruta decide, F3); pero degrada solo si no hay grafo. **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

### F3 — Ruta `POST /docs-rag/search` con selección por flag + golden de no-regresión

**Objetivo (1 frase).** La ruta llama `search_hybrid` SOLO si `STACKY_DOCS_RAG_HYBRID_ENABLED` está ON; si no, llama `search` exactamente como hoy. **Valor:** activación segura, byte-idéntica apagada.

**Archivo a editar:** `Stacky Agents/backend/api/docs_rag.py` — en `route_search()` (docs_rag.py:157):
```python
from config import config
use_hybrid = bool(getattr(config, "STACKY_DOCS_RAG_HYBRID_ENABLED", False))
fn = docs_rag_service.search_hybrid if use_hybrid else docs_rag_service.search
hits = fn(name, query, top_k=top_k, expand_files=expand_files)
```
(No cambiar el shape de la respuesta ni el manejo de errores existente con flag OFF.)

**[ADICIÓN ARQUITECTO] — bloque de diagnóstico opt-in por request:** el body de `POST /docs-rag/search` acepta la key opcional `debug_hybrid` (bool, default false). SOLO cuando `use_hybrid` es True **y** `debug_hybrid` es true, la respuesta agrega la key ADITIVA:
```json
"hybrid_debug": {
  "lexical_files": ["a.md"],
  "expanded_files": ["b.md", "c.md"],
  "weights": {"alpha": 1.0, "beta": 0.15, "max_neighbors": 8}
}
```
Implementación: `search_hybrid` gana un parámetro keyword-only `collect_debug: bool = False`; cuando es True devuelve `(hits, debug_dict)` — la ruta es el único caller que lo usa (la firma pública sin `collect_debug` no cambia). Con flag OFF, `debug_hybrid` en el body se IGNORA (el golden no cambia). Así el operador mide el efecto del híbrido en 1 request desde la UI o curl, sin logs ni config.

**Tests PRIMERO — archivo:** `Stacky Agents/backend/tests/test_plan112_search_route.py` (app+client, patrón `test_plan89_environments_endpoints.py`):
- `test_search_uses_plain_when_flag_off` — flag OFF → llama `search` (monkeypatch/espía), NO `search_hybrid`.
- `test_search_uses_hybrid_when_flag_on` — flag ON → llama `search_hybrid`.
- `test_search_response_shape_unchanged` — **golden:** con flag OFF, el JSON de `/docs-rag/search` tiene exactamente las mismas keys/estructura que hoy (fijar el shape esperado en el test), incluso mandando `debug_hybrid=true` en el body.
- **[ADICIÓN ARQUITECTO]** `test_debug_block_only_when_flag_on_and_requested` — flag ON + `debug_hybrid=true` → la respuesta contiene `hybrid_debug` con las 3 keys; flag ON sin `debug_hybrid` → NO contiene `hybrid_debug`.

**Comando (desde `Stacky Agents/backend`):**
```
venv/Scripts/python.exe -m pytest tests/test_plan112_search_route.py -q
```

**Criterio BINARIO:** 4/4 verdes.

**Flag/default:** `STACKY_DOCS_RAG_HYBRID_ENABLED` OFF → ruta idéntica a hoy. **Impacto por runtime:** ninguno. **Fallback:** flag OFF = léxico puro. **Trabajo del operador:** ninguno (opt-in default off).

---

### F4 — Telemetría A/B en `GET /docs-rag/stats`

**Objetivo (1 frase).** Contadores en memoria del uso del híbrido, expuestos bajo `stats["hybrid"]`, para que el operador mida si aporta. **Valor:** decisión informada de dejar la flag prendida.

**Archivo a editar:** `Stacky Agents/backend/services/docs_rag.py` (telemetría) y consumo en `get_stats`.

**Pseudocódigo EXACTO:**
```python
_hybrid_telemetry = {"queries": 0, "queries_with_new": 0, "hits_lexical": 0, "hits_added": 0}

def record_hybrid_query(lexical: int, added: int, new_from_expansion: bool) -> None:
    _hybrid_telemetry["queries"] += 1
    _hybrid_telemetry["hits_lexical"] += int(lexical)
    _hybrid_telemetry["hits_added"] += int(added)
    if new_from_expansion:
        _hybrid_telemetry["queries_with_new"] += 1

def _reset_hybrid_telemetry() -> None:  # para tests
    for k in _hybrid_telemetry: _hybrid_telemetry[k] = 0

def get_hybrid_telemetry() -> dict:
    return dict(_hybrid_telemetry)
```
En `get_stats(project_name)` (docs_rag.py:354), agregar al dict devuelto (key ADITIVA, no cambia las existentes):
```python
stats["hybrid"] = get_hybrid_telemetry()
```

**Tests PRIMERO — archivo:** `Stacky Agents/backend/tests/test_plan112_telemetry.py`:
- `test_record_increments_counters`.
- `test_queries_with_new_only_when_added`.
- `test_stats_includes_hybrid_block` (ruta `/docs-rag/stats` con app de test → JSON contiene `hybrid` con las 4 keys).
- `test_existing_stats_keys_unchanged` (golden aditivo: `chunks`, `files`, `last_indexed` siguen presentes e intactas).

**Comando (desde `Stacky Agents/backend`):**
```
venv/Scripts/python.exe -m pytest tests/test_plan112_telemetry.py -q
```

**Criterio BINARIO:** 4/4 verdes.

**Flag/default:** telemetría siempre se puede leer; solo se incrementa cuando el híbrido corre (flag ON). **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

### F5 — Cierre del "DocConsultor fantasma"

**Objetivo (1 frase).** Que el chat de docs nunca corra sin persona: warning no-silencioso + persona de fallback built-in cuando el `.agent.md` no existe. **Valor:** calidad del chat de docs sin depender de un archivo gitignoreado.

**Archivo a editar:** `Stacky Agents/backend/api/docs_rag.py`.

**Cambios EXACTOS:**
1. Const nueva (cerca de `_DEFAULT_AGENT`):
   ```python
   _DEFAULT_DOC_CONSULTOR_PROMPT = (
       "Sos un consultor de documentación técnica. Respondés SOLO con base en el "
       "contexto documental provisto; si algo no está en la doc, lo decís explícitamente "
       "en vez de inventar. Citás el fichero de donde sale cada afirmación. Español, "
       "conciso y accionable. No ejecutás acciones: solo informás."
   )
   ```
2. En `_read_agent_system_prompt` (docs_rag.py:41-58): cuando `agent is None`, **loguear warning** (hoy retorna `""` en silencio, línea 53-54) y devolver `""` (el fallback lo aplica el caller, para no cambiar la firma):
   ```python
   if agent is None:
       logger.warning("docs_rag: agent '%s' no encontrado en VSCODE_PROMPTS_DIR; se usará persona de fallback", agent_filename)
       return ""
   ```
3. En el handler de chat (`route_chat`, docs_rag.py:187+): donde hoy se usa el system prompt leído, aplicar fallback:
   ```python
   system_prompt = _read_agent_system_prompt(agent_filename) or _DEFAULT_DOC_CONSULTOR_PROMPT
   ```

**Tests PRIMERO — archivo:** `Stacky Agents/backend/tests/test_plan112_doc_consultor_fallback.py`:
- `test_missing_agent_logs_warning` (monkeypatch `vscode_agents.get_agent_by_filename` → None; capturar log; assert warning emitido).
- `test_chat_uses_fallback_persona_when_agent_missing` (con agente ausente, el system prompt efectivo == `_DEFAULT_DOC_CONSULTOR_PROMPT`; testear el helper de composición, sin invocar LLM real — mockear el runtime/inyección).
- `test_present_agent_takes_precedence` (si `get_agent_by_filename` devuelve un agente con system_prompt no vacío, se usa ESE, no el fallback).

**Comando (desde `Stacky Agents/backend`):**
```
venv/Scripts/python.exe -m pytest tests/test_plan112_doc_consultor_fallback.py -q
```

**Criterio BINARIO:** 3/3 verdes.

**Flag/default:** no gateado por flag (es un fix de robustez, backward-compatible: antes system prompt vacío, ahora persona útil). **Impacto por runtime:** el chat (Codex/Claude/Copilot) ahora recibe persona no vacía; ninguno se rompe (antes recibían `""`). **Trabajo del operador:** ninguno.

---

### F6 — Cierre: no-regresión global y DoD

**Acciones:**
1. Registrar los 6 archivos de test nuevos en `run_harness_tests.sh` **y** `.ps1`.
2. No-regresión (desde `Stacky Agents/backend`):
   ```
   venv/Scripts/python.exe -m pytest tests/test_plan112_flags.py tests/test_plan112_backlink_index.py tests/test_plan112_search_hybrid.py tests/test_plan112_search_route.py tests/test_plan112_telemetry.py tests/test_plan112_doc_consultor_fallback.py tests/test_harness_flags.py tests/test_harness_flags_help.py tests/test_harness_flags_requires.py -q
   ```

**Criterio BINARIO global (DoD):**
- [ ] Los 6 suites nuevas + 3 del arnés verdes.
- [ ] Con `STACKY_DOCS_RAG_HYBRID_ENABLED` OFF: `search()` y `/docs-rag/search` byte-idénticos a hoy (golden F3); `DocHit` de `search` sin mutar.
- [ ] Con flag ON: el test KPI (`test_pulls_neighbor_note_chunk`) demuestra recall estructural; el prior de backlinks reordena hubs.
- [ ] `search_hybrid` degrada a léxico puro si el grafo (109) no está disponible.
- [ ] `/docs-rag/stats` gana bloque `hybrid` aditivo; keys viejas intactas.
- [ ] El chat nunca corre con system prompt vacío (fallback + warning).
- [ ] Cero motor léxico nuevo (el diff de `docs_rag.py` no importa `rag_retriever` ni `memory_store`; no crea tablas nuevas).

---

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Regresión del retrieval actual. | Camino híbrido en función NUEVA; `search()` intacto; golden byte-idéntico con flag OFF (F3). |
| Grafo (109) caído rompe la búsqueda. | `_build_backlink_index` atrapa toda excepción y devuelve `({},{})`; `search_hybrid` degrada a `search()` (F1/F2). |
| Mismatch de identidad file_path ↔ node.path. | Comparación normalizada `/`; fallback por basename documentado; solo nodos `project-docs`. Tests fijan el mapeo. |
| Expansión trae demasiados chunks (contexto inflado). | Tope `STACKY_DOCS_RAG_HYBRID_MAX_NEIGHBORS` (default 8) + **cap duro del resultado a `top_k * 3` (C1)** + los chunks vecinos entran con score 0 y quedan detrás salvo prior de backlinks. `_build_context_block` ya trunca a `_MAX_CONTEXT_CHARS`. |
| Cuarto motor TF-IDF por accidente. | Guardarraíl duro de DoD: el diff no importa `rag_retriever`/`memory_store` ni crea índice nuevo; reusa `DocChunk`. |
| Persona de fallback tapa un `.agent.md` real. | El fallback solo aplica cuando el prompt leído es vacío; agente presente tiene precedencia (test F5). |
| Telemetría en memoria se pierde al reiniciar. | Aceptable: es señal A/B de sesión, no métrica persistida; documentado. Si se quiere persistencia, plan aparte. |

---

## 7. Fuera de scope

- Cambiar el motor TF-IDF o migrar a embeddings (prohibido: ya hay 3 motores; y viola la filosofía cero-red/cero-LLM del plan 64).
- Persistir la telemetría A/B en DB.
- Expansión multi-hop (>1 salto): explícitamente 1-hop por costo/precisión.
- UI para editar alpha/beta más allá del `HarnessFlagsPanel` (las flags ya son editables ahí).
- Usar el híbrido en `rag_retriever.py` (catálogo de procesos): este plan es solo `docs_rag`.
- Escribir/crear documentación (plan 113).

---

## 8. Glosario (términos para modelos menores)

- **TF-IDF / coseno:** puntaje de similitud léxica entre query y chunk; lo que `docs_rag.search` ya calcula.
- **Recall estructural:** recuperar información relevante que NO contiene el término de la query pero vive en una nota enlazada.
- **Expansión 1-hop:** traer las notas a exactamente 1 arista de las que puntuaron alto.
- **Prior de backlinks:** sumar al score un término proporcional a cuántas notas referencian el fichero (nota-hub = más relevante).
- **`in_degree` / backlinks:** número de aristas entrantes a un nodo (dato que da el plan 109).
- **DocChunk:** fila de la tabla `docs_index` (un fragmento de una nota, con `file_path`, `section_heading`, `term_freqs_json`).
- **Golden byte-idéntico:** test que fija la salida exacta con la flag OFF para garantizar cero regresión (patrón plan 64).
- **DocConsultor:** persona del chat de docs; hoy su `.agent.md` no existe → este plan da fallback built-in.
- **venv del repo:** `Stacky Agents/backend/venv` (Python 3.13); correr pytest por archivo.

---

## 9. Orden de implementación (secuencial)

1. **F0** — 4 flags + bounds + tests.
2. **F1** — `_build_backlink_index` (puente grafo↔docs_rag, con fallback basename C2) + 6 tests.
3. **F2** — `search_hybrid` + `_rerank_with_backlinks` + cap de resultados (C1) + 7 tests (incluye KPI central).
4. **F3** — ruta con selección por flag + golden + `debug_hybrid` + 4 tests.
5. **F4** — telemetría A/B en `/stats` + 4 tests.
6. **F5** — fallback DocConsultor + warning + 3 tests.
7. **F6** — cierre, no-regresión, DoD.

---

## 10. Definición de Hecho (DoD) — resumen binario

Hecho cuando: (a) las 6 suites backend nuevas + 3 del arnés están verdes; (b) con la flag OFF, `search()` y `/docs-rag/search` son byte-idénticos a hoy y los `DocHit` no se mutan; (c) con la flag ON, el test de recall estructural pasa (trae la nota vecina) y el prior de backlinks reordena hubs; (d) el híbrido degrada a léxico puro si el grafo del 109 no está; (e) `/docs-rag/stats` expone el bloque `hybrid` aditivo sin alterar las keys previas; (f) el chat de docs nunca usa system prompt vacío (fallback + warning); (g) no se creó ningún motor léxico ni tabla de índice nuevos.
