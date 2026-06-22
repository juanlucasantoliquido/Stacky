# Plan 64 — RAG local: recuperación semántica del catálogo de procesos para grounding preciso

> **Versión: v1 → v2** (endurecido por el juez adversarial `criticar-y-mejorar-plan`).
>
> **CHANGELOG v2:**
> - **C1 (BLOQUEANTE) — patch target incorrecto en todos los tests de F2 y F3.**
>   `load_client_profile` se importa inline dentro de `_inject_process_catalog_block`; el nombre
>   NO existe en el namespace de `services.context_enrichment` → `patch("services.context_enrichment.load_client_profile", ...)`
>   levantaba `AttributeError` antes de ejecutar una sola aserción. Corregido a
>   `patch("services.client_profile.load_client_profile", ...)` en los 8 usos de F2/F3.
> - **C2 (IMPORTANTE) — F3 entregaba instrucción vaga sobre dónde integrar `_rag_meta`.**
>   "Dentro del bloque if block is not None, ya DESPUÉS del log" no es locatable en la función
>   reescrita de F2. F3 ahora entrega el body completo final de `_inject_process_catalog_block`
>   con `_rag_meta` ya integrado (única fuente de verdad).
> - **C3 (IMPORTANTE) — `retrieved` contado por `"\n- "` en el string era frágil.**
>   Si `purpose` de un proceso contenía `"\n- "` el conteo se inflaba. Corregido: 
>   `build_process_dictionary_block_rag` retorna `tuple[dict, int] | None` donde el entero es
>   `len(results)` exacto. El caller usa ese entero para `_rag_meta["retrieved"]`.
> - **C4 (MENOR) — Agregar nota de thread-safety** en el comentario de `_RAG_INDEX_CACHE`.
> - **C5 (MENOR) — F4 ahora nombra el script de ratchet** del repo para enlazar el test de perf.
> - **[ADICIÓN ARQUITECTO] Tests de discriminación de dominio RSPACIFICO:** dos tests nuevos en
>   `test_rag_retriever.py` verifican que el TF-IDF discrimina correctamente el vocabulario
>   técnico real (Mul2Bane/GenReporte), no solo queries genéricos. Elevan el conteo de tests
>   de F0 de 13 a **15**.
>
> **Audiencia de implementación:** modelo MENOR (Haiku / Codex / GitHub Copilot Pro). Todo está dado:
> rutas exactas, símbolos exactos, casos borde, tests primero, comandos exactos. **NO inferir nada.**
> **Origen del número:** listado de `Stacky Agents/docs/` → NN máximo = 63 → este plan = **64**.

---

## 1. Objetivo + KPI

**Objetivo (un párrafo).** Hoy `_inject_process_catalog_block` vuelca **TODOS** los procesos del
catálogo de cliente (≥200 entradas en RSPACIFICO) como un único bloque de texto plano. El agente
recibe ruido masivo: procesos sin relación con la tarea actual compiten por ventana de contexto con
los procesos REALMENTE relevantes, diluyen el grounding y elevan los tokens consumidos. Este plan
introduce un **recuperador TF-IDF puro** (cero dependencias nuevas, cero red, cero LLM) que, dado
el texto del ticket (título + descripción), selecciona los **top-K procesos más relevantes** e
inyecta SOLO esos. El catálogo completo sigue disponible para el full-inject cuando RAG está OFF.
El cambio es **aditivo**: un flag lo activa; apagado, el comportamiento es byte-idéntico al actual.
Funciona con RSPACIFICO y con cualquier otro proyecto que tenga `process_catalog` en su
`client_profile`.

**KPI / impacto esperado:**
- **Tokens de contexto de catálogo:** de ≥200 entradas siempre a top-K (default 8); reducción
  estimada ≥90 % en el bloque `process-catalog` cuando el ticket es específico.
- **Grounding confidence:** sube porque el bloque inyectado contiene procesos realmente relacionados
  con el brief, no el catálogo completo.
- **Latencia de inyección:** microsegundos adicionales (TF-IDF puro sobre ~200 entradas).
- **Trabajo del operador:** ninguno. El RAG actúa en background; el operador solo enciende el flag
  desde la UI (o lo deja OFF).
- **Paridad 3 runtimes:** el RAG corre en el backend antes de cualquier runtime → idéntico para
  Codex, Claude Code y GitHub Copilot Pro.

---

## 2. Por qué ahora / gap que cierra

- **Planes 42/44** introdujeron el catálogo como bloque de contexto y el observatorio de grounding
  (telemetría pasiva de confidence). El problema de INYECTAR TODO quedó como deuda: en un catálogo
  grande, el modelo recibe texto irrelevante que degrada su grounding (proceso `Mul2Bane` cuando el
  brief habla de generación de reportes, por ejemplo).
- **Plan 54** materializó lecciones desde rechazos. **Plan 60** aprendió desde ediciones humanas.
  Ambos mejoran el contenido; este plan mejora la SELECCIÓN del contenido de contexto antes de que
  el modelo lo vea.
- **Plan 63** mejora la UI del arnés → el operador puede ver y activar el nuevo flag `STACKY_RAG_CATALOG_ENABLED`
  desde la UI categorizada (categoría `contexto_memoria`) sin ningún paso manual adicional.
- El `_context_text` (título + descripción del ticket) ya se construye en `enrich_blocks` línea 194
  para `_apply_context_budget`: es la señal de query disponible en el mismo scope.

---

## 3. Principios y guardarraíles (no negociables)

- **3 runtimes con paridad:** el RAG corre en el backend (Python puro) antes de cualquier llamada
  al runtime. Idéntico para Codex CLI, Claude Code CLI y GitHub Copilot Pro. No hay rama por
  runtime. Fallback por runtime: ninguno necesario (transparente a los 3).
- **Cero trabajo extra al operador:** flag `STACKY_RAG_CATALOG_ENABLED` default OFF. OFF →
  byte-idéntico al actual (llama `build_process_dictionary_block` igual que hoy). Opt-in desde UI.
- **Human-in-the-loop intacto:** el RAG selecciona contexto; el operador sigue aprobando el
  resultado del agente. No hay autonomía nueva.
- **Mono-operador sin auth:** no RBAC.
- **No degradar:** cero nuevas dependencias (`math`, `collections`, `re` son stdlib). Sin llamadas
  a red ni disco extra (el catálogo ya está en memoria desde `load_client_profile`). Fallback
  determinista: si el retriever falla por cualquier razón → inyecta el catálogo completo (degradación
  controlada, no error visible al operador).
- **Reuso obligatorio:** reutiliza `client_profile.process_catalog` ya cargado, el bloque
  `"process-catalog"` existente, el sistema de flags de `harness_flags.FLAG_REGISTRY`, la
  telemetría de `grounding_observatory`.
- **Regla dura config-por-UI:** los dos flags nuevos se registran en `FLAG_REGISTRY` (no env-only)
  → aparecen automáticamente en el panel de flags (plan 33/63) sin tocar el frontend.

---

## 4. Fases

> **Orden de dependencia:** F0 → F1 → F2 → F3 → F4.
> F0 = módulo RAG puro (cero acoplamiento a Stacky); F1 = flags en UI; F2 = wiring en
> `context_enrichment`; F3 = telemetría; F4 = ratchet de performance.
> Cada fase es verificable de forma aislada.

> **Intérprete de tests (usar en todos los comandos pytest):**
> `& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest <archivo> -q`
> ejecutado desde `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend`.

---

### F0 — Módulo RAG puro: TF-IDF + recuperador (sin acoplamiento a Stacky)

**Objetivo (1 frase).** Crear `services/rag_retriever.py` con funciones PURAS que indexan una lista
de chunks de texto con TF-IDF y recuperan los top-K más similares a un query — sin dependencias
externas, sin estado global, sin red. **Valor:** módulo reutilizable para cualquier catálogo futuro
(procesos, skills, documentos de proyecto).

**Archivo a crear:** `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/services/rag_retriever.py`

**Implementación exacta (copiá esto tal cual):**

```python
"""RAG local: TF-IDF puro sin dependencias externas.

Funciones puras: sin estado global, sin red, sin LLM.
Compatible con Python 3.10+ stdlib (math, re, collections).
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Sequence


@dataclass(frozen=True)
class RagChunk:
    id: str          # identificador estable del chunk (ej. process name slug)
    text: str        # texto plano del chunk (para scoring)
    payload: dict    # datos originales (se devuelve intacto al llamador)


@dataclass
class RagIndex:
    chunks: list[RagChunk]
    idf: dict[str, float]          # term -> idf score
    tf_vecs: list[dict[str, float]] # un dict tf por chunk, alineado con chunks[]
    # Cache key: hash del contenido original para invalidar automáticamente.
    content_hash: str = ""


def _tokenize(text: str) -> list[str]:
    """Tokenización simple: lower, solo alfanum + guión/subguión, min 2 chars."""
    return [t for t in re.findall(r"[a-záéíóúüñ\w]{2,}", text.lower()) if len(t) >= 2]


def _tf(tokens: list[str]) -> dict[str, float]:
    if not tokens:
        return {}
    counts = Counter(tokens)
    n = len(tokens)
    return {term: count / n for term, count in counts.items()}


def _build_idf(token_sets: list[set[str]], n_docs: int) -> dict[str, float]:
    df: Counter[str] = Counter()
    for ts in token_sets:
        df.update(ts)
    return {term: math.log((n_docs + 1) / (cnt + 1)) + 1.0 for term, cnt in df.items()}


def _tfidf_vec(tf: dict[str, float], idf: dict[str, float]) -> dict[str, float]:
    return {term: tf_val * idf.get(term, 1.0) for term, tf_val in tf.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a.get(t, 0.0) * v for t, v in b.items())
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def build_index(chunks: Sequence[RagChunk], content_hash: str = "") -> RagIndex:
    """Construye el índice TF-IDF a partir de una lista de chunks. O(N*V)."""
    chunk_list = list(chunks)
    if not chunk_list:
        return RagIndex(chunks=[], idf={}, tf_vecs=[], content_hash=content_hash)
    tokenized = [_tokenize(c.text) for c in chunk_list]
    token_sets = [set(t) for t in tokenized]
    idf = _build_idf(token_sets, len(chunk_list))
    tf_vecs = [_tfidf_vec(_tf(tokens), idf) for tokens in tokenized]
    return RagIndex(chunks=chunk_list, idf=idf, tf_vecs=tf_vecs, content_hash=content_hash)


def retrieve(index: RagIndex, query: str, top_k: int = 8) -> list[tuple[RagChunk, float]]:
    """Devuelve los top_k chunks más similares al query, ordenados por score desc.

    Retorna lista de (chunk, score). Si el índice está vacío o top_k<=0, devuelve [].
    Nunca lanza; score mínimo = 0.0.
    """
    if not index.chunks or top_k <= 0 or not query.strip():
        return []
    q_tokens = _tokenize(query)
    q_tf = _tf(q_tokens)
    q_vec = _tfidf_vec(q_tf, index.idf)
    scored = [
        (chunk, _cosine(q_vec, tv))
        for chunk, tv in zip(index.chunks, index.tf_vecs)
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def chunks_from_process_catalog(catalog: list[dict]) -> list[RagChunk]:
    """Convierte el process_catalog de client_profile en chunks indexables.

    Cada proceso = un chunk. El texto es: name + kind + purpose (concatenados).
    El payload es el dict original del proceso para reconstruir el bloque.
    El id es el slug del name (lowercase, spaces→guión).
    """
    result: list[RagChunk] = []
    for p in (catalog or []):
        name = (p.get("name") or "").strip()
        purpose = (p.get("purpose") or "").strip()
        kind = (p.get("kind") or "otro").strip()
        if not name or not purpose:
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        text = f"{name} {kind} {purpose}"
        result.append(RagChunk(id=slug, text=text, payload=p))
    return result
```

**Tests PRIMERO** — archivo a crear:
`N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/tests/test_rag_retriever.py`

```python
"""Tests TDD de services/rag_retriever.py (F0 — Plan 64)."""
import pytest
from services.rag_retriever import (
    RagChunk, build_index, retrieve, chunks_from_process_catalog, _tokenize,
)

CATALOG = [
    {"name": "Mul2Bane", "kind": "batch", "purpose": "Carga multigestion de bancos y entidades financieras"},
    {"name": "IncHost", "kind": "batch", "purpose": "Procesa incrementos de host para cuentas activas productivas"},
    {"name": "RSCore", "kind": "batch", "purpose": "Aplica reglas de negocio centrales sobre saldos y movimientos"},
    {"name": "RsExtrae", "kind": "batch", "purpose": "Extrae datos de salida y genera reportes de cierre"},
    {"name": "GenReporte", "kind": "batch", "purpose": "Generacion de reportes de conciliacion y auditoria"},
]


def test_chunks_from_catalog_length():
    chunks = chunks_from_process_catalog(CATALOG)
    assert len(chunks) == len(CATALOG)


def test_chunks_from_catalog_ids_unique():
    chunks = chunks_from_process_catalog(CATALOG)
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids))


def test_chunks_from_catalog_skips_empty():
    partial = [{"name": "", "kind": "batch", "purpose": "algo"}, CATALOG[0]]
    chunks = chunks_from_process_catalog(partial)
    assert len(chunks) == 1


def test_build_index_empty():
    idx = build_index([])
    assert idx.chunks == []
    assert idx.tf_vecs == []


def test_build_index_non_empty():
    chunks = chunks_from_process_catalog(CATALOG)
    idx = build_index(chunks)
    assert len(idx.chunks) == len(CATALOG)
    assert len(idx.tf_vecs) == len(CATALOG)
    assert len(idx.idf) > 0


def test_retrieve_returns_top_k():
    chunks = chunks_from_process_catalog(CATALOG)
    idx = build_index(chunks)
    results = retrieve(idx, "reportes de conciliacion y auditoria", top_k=2)
    assert len(results) == 2
    # El chunk de GenReporte debe estar primero (mayor similitud)
    top_id = results[0][0].id
    assert top_id == "genreporte"


def test_retrieve_scores_descending():
    chunks = chunks_from_process_catalog(CATALOG)
    idx = build_index(chunks)
    results = retrieve(idx, "bancos entidades financieras", top_k=5)
    scores = [s for _, s in results]
    assert scores == sorted(scores, reverse=True)


def test_retrieve_empty_query_returns_empty():
    chunks = chunks_from_process_catalog(CATALOG)
    idx = build_index(chunks)
    assert retrieve(idx, "", top_k=3) == []
    assert retrieve(idx, "   ", top_k=3) == []


def test_retrieve_top_k_zero_returns_empty():
    chunks = chunks_from_process_catalog(CATALOG)
    idx = build_index(chunks)
    assert retrieve(idx, "algo", top_k=0) == []


def test_retrieve_top_k_greater_than_corpus():
    chunks = chunks_from_process_catalog(CATALOG)
    idx = build_index(chunks)
    results = retrieve(idx, "proceso batch", top_k=100)
    assert len(results) == len(CATALOG)  # nunca más que el corpus


def test_retrieve_payload_intact():
    chunks = chunks_from_process_catalog(CATALOG)
    idx = build_index(chunks)
    results = retrieve(idx, "host cuentas activas", top_k=1)
    assert results[0][0].payload["name"] == "IncHost"


def test_tokenize_basic():
    tokens = _tokenize("Mul2Bane carga multigestion")
    assert "mul2bane" in tokens or "mul" in tokens  # al menos una parte
    assert "multigestion" in tokens


def test_retrieve_no_crash_on_single_chunk():
    chunks = [RagChunk(id="x", text="proceso unico especial", payload={})]
    idx = build_index(chunks)
    results = retrieve(idx, "proceso especial", top_k=3)
    assert len(results) == 1
    assert results[0][1] > 0.0


def test_content_hash_stored():
    chunks = chunks_from_process_catalog(CATALOG)
    idx = build_index(chunks, content_hash="abc123")
    assert idx.content_hash == "abc123"


# [ADICIÓN ARQUITECTO v2] — Discriminación de vocabulario real RSPACIFICO
def test_domain_discrimination_mul2bane():
    """'multigestion bancos entidades' debe recuperar Mul2Bane como top-1."""
    chunks = chunks_from_process_catalog(CATALOG)
    idx = build_index(chunks)
    results = retrieve(idx, "multigestion bancos entidades", top_k=3)
    assert len(results) > 0
    assert results[0][0].payload["name"] == "Mul2Bane", (
        f"Esperaba Mul2Bane como top-1, obtuve {results[0][0].payload['name']}"
    )


def test_domain_discrimination_reporte():
    """'conciliacion auditoria reportes' debe recuperar GenReporte como top-1."""
    chunks = chunks_from_process_catalog(CATALOG)
    idx = build_index(chunks)
    results = retrieve(idx, "conciliacion auditoria reportes", top_k=3)
    assert len(results) > 0
    assert results[0][0].payload["name"] == "GenReporte", (
        f"Esperaba GenReporte como top-1, obtuve {results[0][0].payload['name']}"
    )
```

**Comando exacto:**
```powershell
& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest tests/test_rag_retriever.py -q
```

**Criterio de aceptación BINARIO:** todos los **15** tests pasan (exit 0; +2 de discriminación de
dominio RSPACIFICO vs. los 13 originales). Ningún import externo a `stdlib`.

**Flag que la protege:** ninguna (módulo puro, no se llama desde ningún lado aún).
**Impacto por runtime:** ninguno (F0 solo crea el módulo).
**Trabajo del operador: ninguno.**

---

### F1 — Flags en FLAG_REGISTRY (visibles en la UI)

**Objetivo (1 frase).** Declarar `STACKY_RAG_CATALOG_ENABLED` (bool, default OFF) y
`STACKY_RAG_CATALOG_TOP_K` (int, default 8) en `FLAG_REGISTRY` para que aparezcan en la UI sin
tocar el frontend. **Valor:** el operador puede activar/ajustar el RAG desde la UI del arnés.

**Archivo a editar:**
`N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/services/harness_flags.py`

**Símbolo exacto:** `FLAG_REGISTRY` (tupla que arranca en línea `:29`).

Insertar las dos `FlagSpec` siguientes DESPUÉS del bloque
`"STACKY_INJECT_PROCESS_CATALOG"` (localizar con `grep "STACKY_INJECT_PROCESS_CATALOG"` en el
archivo; insertar justo después de ese entry, antes del cierre de la tupla de su grupo):

```python
FlagSpec(
    key="STACKY_RAG_CATALOG_ENABLED",
    type="bool",
    label="RAG catálogo de procesos",
    description=(
        "Si ON, inyecta solo los top-K procesos más relevantes al ticket "
        "(TF-IDF puro) en lugar del catálogo completo. "
        "Reduce ruido de contexto y mejora el grounding. Default OFF."
    ),
    group="global",
    pair="STACKY_RAG_CATALOG_TOP_K",
),
FlagSpec(
    key="STACKY_RAG_CATALOG_TOP_K",
    type="int",
    label="RAG catálogo: top-K procesos",
    description=(
        "Cantidad de procesos a recuperar por similitud TF-IDF cuando "
        "STACKY_RAG_CATALOG_ENABLED=true. Rango recomendado: 5–15. Default 8."
    ),
    group="global",
),
```

**Nota sobre la categorización (Plan 63):** si el plan 63 ya está implementado y existe
`_CATEGORY_KEYS` en `harness_flags.py`, agregar `"STACKY_RAG_CATALOG_ENABLED"` y
`"STACKY_RAG_CATALOG_TOP_K"` a la categoría `"contexto_memoria"` en `_CATEGORY_KEYS`. Si el
plan 63 no está implementado, omitir ese paso (los flags aparecen igualmente en la UI bajo
`global`).

**Tests PRIMERO** — agregar a `tests/test_harness_flags.py`:

```python
def test_rag_catalog_enabled_in_registry():
    from services.harness_flags import FLAG_REGISTRY
    keys = {s.key for s in FLAG_REGISTRY}
    assert "STACKY_RAG_CATALOG_ENABLED" in keys
    assert "STACKY_RAG_CATALOG_TOP_K" in keys

def test_rag_catalog_enabled_is_bool_off_by_default():
    from services.harness_flags import FLAG_REGISTRY
    spec = next(s for s in FLAG_REGISTRY if s.key == "STACKY_RAG_CATALOG_ENABLED")
    assert spec.type == "bool"
    # default NOT declared (= type-zero = False) — flag arranca OFF
    assert spec.default is None  # no tiene default declarado → OFF por type-zero

def test_rag_catalog_top_k_is_int():
    from services.harness_flags import FLAG_REGISTRY
    spec = next(s for s in FLAG_REGISTRY if s.key == "STACKY_RAG_CATALOG_TOP_K")
    assert spec.type == "int"

def test_rag_flags_pair_linkage():
    from services.harness_flags import FLAG_REGISTRY
    spec = next(s for s in FLAG_REGISTRY if s.key == "STACKY_RAG_CATALOG_ENABLED")
    assert spec.pair == "STACKY_RAG_CATALOG_TOP_K"
```

**Comando exacto:**
```powershell
& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest tests/test_harness_flags.py -q
```

**Criterio BINARIO:** los 4 tests nuevos + todos los existentes de `test_harness_flags.py` pasan
(exit 0).

**Flag:** ninguna (declaración pura; la activación llega en F2).
**Impacto por runtime:** ninguno (solo registro de metadata).
**Trabajo del operador: ninguno.**

---

### F2 — Wiring en `context_enrichment.py`: RAG reemplaza full-inject cuando está ON

**Objetivo (1 frase).** Modificar `_inject_process_catalog_block` (y su helper) para que, cuando
`STACKY_RAG_CATALOG_ENABLED=true`, use el recuperador TF-IDF (F0) con el query del ticket en lugar
del volcado completo. **Valor:** el modelo solo ve los procesos relevantes al ticket actual.

**Archivo a editar:**
`N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/services/context_enrichment.py`

**Paso 1 — Agregar helper de índice en-memoria** (DESPUÉS de los imports, antes de `enrich_blocks`):

```python
# Cache en-memoria: content_hash -> RagIndex. Se invalida automáticamente cuando
# el catálogo cambia (hash distinto). Usa un único slot (clear en cada cambio).
# Thread-safety: no es safe para gunicorn multi-worker (cada worker tiene su propia
# copia del proceso; para Stacky single-worker es OK).
_RAG_INDEX_CACHE: dict[str, "RagIndex"] = {}  # type: ignore[name-defined]

def _get_rag_index(catalog: list[dict]) -> "RagIndex":
    """Devuelve el índice TF-IDF del catálogo; lo construye si el hash cambió."""
    import hashlib, json
    from services.rag_retriever import build_index, chunks_from_process_catalog
    content_hash = hashlib.md5(
        json.dumps(catalog, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    if content_hash not in _RAG_INDEX_CACHE:
        chunks = chunks_from_process_catalog(catalog)
        _RAG_INDEX_CACHE.clear()  # máximo 1 entrada; libera si cambió el catálogo
        _RAG_INDEX_CACHE[content_hash] = build_index(chunks, content_hash=content_hash)
    return _RAG_INDEX_CACHE[content_hash]
```

**Paso 2 — Nueva función pura `build_process_dictionary_block_rag`** (DESPUÉS de
`build_process_dictionary_block` existente, línea 624):

```python
def build_process_dictionary_block_rag(
    client_profile: dict | None,
    query: str,
    top_k: int = 8,
) -> tuple[dict, int] | None:
    """Plan 64 F2 — Bloque 'process-catalog' con solo los top-K procesos relevantes al query.

    Función PURA. Retorna (block, n_retrieved) donde n_retrieved = len(results) exacto.
    Fallback: si falla el retriever o no hay resultados → None
    (el caller usa el fallback al full-inject).
    """
    if not client_profile or not query or not query.strip():
        return None
    catalog = client_profile.get("process_catalog") or []
    if not catalog:
        return None
    try:
        from services.rag_retriever import retrieve
        index = _get_rag_index(catalog)
        results = retrieve(index, query, top_k=top_k)
        if not results:
            return None
        lines = [
            f"PROCESOS RELEVANTES AL TICKET (top-{len(results)} de {len(catalog)}, "
            f"TF-IDF — NO inventes nombres ni propósitos):"
        ]
        for chunk, score in results:
            p = chunk.payload
            name = (p.get("name") or "").strip()
            purpose = (p.get("purpose") or "").strip()
            kind = (p.get("kind") or "otro").strip()
            if name and purpose:
                lines.append(f"- {name} [{kind}]: {purpose}")
        if len(lines) == 1:
            return None
        block = {"id": "process-catalog", "kind": "process-catalog", "content": "\n".join(lines)}
        return block, len(results)  # (v2/C3) — n_retrieved exacto, no string-counted
    except Exception:  # noqa: BLE001
        return None  # degradación controlada → caller usa full-inject
```

**Paso 3 — Modificar `_inject_process_catalog_block`** para llamar al RAG si está habilitado:

> **v2/C2 — ATENCIÓN:** El body completo y definitivo de esta función (integrando RAG + telemetría
> `_rag_meta`) está en **F3** de este plan (fuente única de verdad). Implementar directamente
> desde F3; NO usar este Paso 3 como referencia. Se mantiene aquí solo para trazabilidad.

Reemplazar el cuerpo actual de `_inject_process_catalog_block` (líneas 627-650) con el cuerpo
completo que aparece en F3 más abajo. El body de F3 es la versión definitiva.

**Paso 4 — Pasar `query` desde `enrich_blocks`.**
En `enrich_blocks` (línea 83), el `_context_text` ya se construye en la línea 194. Como F2 necesita
el query ANTES de la inyección del catálogo (línea 83), se debe derivar el query al inicio de
`enrich_blocks`. Editar el inicio de `enrich_blocks` (después de capturar los escalares del ticket,
antes de la primera inyección):

Localizar el bloque donde se definen `ticket_title` y `ticket_description` (líneas ~56-65).
Inmediatamente DESPUÉS, agregar:

```python
    # Plan 64 F2 — query para RAG (disponible desde el inicio del pipeline)
    _rag_query = " ".join(p for p in [ticket_title, ticket_description] if p) or None
```

Luego cambiar la llamada de línea 83:
```python
    # ANTES:
    blocks = _inject_process_catalog_block(blocks, project_name, log)
    # DESPUÉS:
    blocks = _inject_process_catalog_block(blocks, project_name, log, query=_rag_query)
```

**Tests PRIMERO** — archivo a crear:
`N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/tests/test_rag_context_enrichment.py`

```python
"""Tests TDD del wiring RAG en context_enrichment (F2 — Plan 64)."""
import os
import pytest
from unittest.mock import patch, MagicMock

CATALOG = [
    {"name": "Mul2Bane", "kind": "batch", "purpose": "Carga multigestion bancos"},
    {"name": "IncHost", "kind": "batch", "purpose": "Procesa incrementos host cuentas activas"},
    {"name": "RSCore", "kind": "batch", "purpose": "Aplica reglas negocio saldos movimientos"},
    {"name": "RsExtrae", "kind": "batch", "purpose": "Extrae datos salida reportes cierre"},
    {"name": "GenReporte", "kind": "batch", "purpose": "Generacion reportes conciliacion auditoria"},
]
PROFILE = {"process_catalog": CATALOG}


def _make_profile_loader(profile):
    def loader(project_name):
        return profile
    return loader


def test_rag_disabled_injects_full_catalog(monkeypatch):
    """Con RAG OFF → inyecta el catálogo completo (comportamiento original)."""
    monkeypatch.setenv("STACKY_RAG_CATALOG_ENABLED", "false")
    monkeypatch.setenv("STACKY_INJECT_PROCESS_CATALOG", "true")
    from services import context_enrichment as ce
    with patch("services.client_profile.load_client_profile", _make_profile_loader(PROFILE)):
        result = ce._inject_process_catalog_block([], "mi-proyecto", lambda *a, **k: None, query="reportes")
    assert any(b.get("id") == "process-catalog" for b in result)
    block = next(b for b in result if b.get("id") == "process-catalog")
    # Con RAG OFF debe contener TODOS los procesos del catálogo
    assert "Mul2Bane" in block["content"]
    assert "IncHost" in block["content"]
    assert "GenReporte" in block["content"]


def test_rag_enabled_injects_subset(monkeypatch):
    """Con RAG ON → inyecta solo el top-K (no todos)."""
    monkeypatch.setenv("STACKY_RAG_CATALOG_ENABLED", "true")
    monkeypatch.setenv("STACKY_RAG_CATALOG_TOP_K", "2")
    monkeypatch.setenv("STACKY_INJECT_PROCESS_CATALOG", "true")
    from services import context_enrichment as ce
    # Limpiar cache para forzar rebuild
    ce._RAG_INDEX_CACHE.clear()
    with patch("services.client_profile.load_client_profile", _make_profile_loader(PROFILE)):
        result = ce._inject_process_catalog_block(
            [], "mi-proyecto", lambda *a, **k: None, query="reportes conciliacion auditoria"
        )
    assert any(b.get("id") == "process-catalog" for b in result)
    block = next(b for b in result if b.get("id") == "process-catalog")
    # Con top-k=2, el bloque tiene como máximo 2 procesos
    process_lines = [l for l in block["content"].splitlines() if l.startswith("- ")]
    assert len(process_lines) <= 2


def test_rag_enabled_no_query_falls_back_to_full(monkeypatch):
    """Con RAG ON pero sin query → degradación limpia → full-inject."""
    monkeypatch.setenv("STACKY_RAG_CATALOG_ENABLED", "true")
    monkeypatch.setenv("STACKY_INJECT_PROCESS_CATALOG", "true")
    from services import context_enrichment as ce
    ce._RAG_INDEX_CACHE.clear()
    with patch("services.client_profile.load_client_profile", _make_profile_loader(PROFILE)):
        result = ce._inject_process_catalog_block(
            [], "mi-proyecto", lambda *a, **k: None, query=None
        )
    block = next((b for b in result if b.get("id") == "process-catalog"), None)
    assert block is not None
    # Sin query → full-inject
    assert "Mul2Bane" in block["content"]


def test_rag_disabled_env_off(monkeypatch):
    """Con STACKY_INJECT_PROCESS_CATALOG=false → no inyecta nada."""
    monkeypatch.setenv("STACKY_INJECT_PROCESS_CATALOG", "false")
    from services import context_enrichment as ce
    result = ce._inject_process_catalog_block([], "mi-proyecto", lambda *a, **k: None)
    assert not any(b.get("id") == "process-catalog" for b in result)


def test_rag_already_present_skips(monkeypatch):
    """Si el bloque ya está en blocks → no duplicar."""
    monkeypatch.setenv("STACKY_INJECT_PROCESS_CATALOG", "true")
    from services import context_enrichment as ce
    existing = [{"id": "process-catalog", "content": "ya está"}]
    result = ce._inject_process_catalog_block(existing, "mi-proyecto", lambda *a, **k: None)
    catalog_blocks = [b for b in result if b.get("id") == "process-catalog"]
    assert len(catalog_blocks) == 1  # no duplica


def test_build_process_dictionary_block_rag_returns_top_k():
    """build_process_dictionary_block_rag devuelve un bloque con ≤top_k procesos."""
    from services.context_enrichment import build_process_dictionary_block_rag, _RAG_INDEX_CACHE
    _RAG_INDEX_CACHE.clear()
    block = build_process_dictionary_block_rag(PROFILE, query="host cuentas activas", top_k=2)
    assert block is not None
    assert block["id"] == "process-catalog"
    process_lines = [l for l in block["content"].splitlines() if l.startswith("- ")]
    assert len(process_lines) <= 2


def test_build_process_dictionary_block_rag_empty_query_returns_none():
    from services.context_enrichment import build_process_dictionary_block_rag
    assert build_process_dictionary_block_rag(PROFILE, query="") is None
    assert build_process_dictionary_block_rag(PROFILE, query="   ") is None


def test_rag_index_cache_hit(monkeypatch):
    """El índice se reconstruye solo cuando el catálogo cambia (no en cada llamada)."""
    from services import context_enrichment as ce
    ce._RAG_INDEX_CACHE.clear()
    # Primera llamada: construye el índice
    ce._get_rag_index(CATALOG)
    first_hash = list(ce._RAG_INDEX_CACHE.keys())[0]
    # Segunda llamada con el mismo catálogo: no cambia el hash
    ce._get_rag_index(CATALOG)
    assert list(ce._RAG_INDEX_CACHE.keys()) == [first_hash]
    # Catálogo distinto: invalida el cache
    ce._get_rag_index(CATALOG + [{"name": "Nuevo", "kind": "x", "purpose": "algo nuevo"}])
    assert first_hash not in ce._RAG_INDEX_CACHE
```

**Comando exacto:**
```powershell
& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest tests/test_rag_context_enrichment.py -q
```

**Criterio de aceptación BINARIO:** todos los 9 tests pasan (exit 0). Con
`STACKY_RAG_CATALOG_ENABLED=false` (default), el comportamiento es byte-idéntico al actual.

**Flag:** `STACKY_RAG_CATALOG_ENABLED` (default OFF = env no seteado / "false") +
`STACKY_RAG_CATALOG_TOP_K` (int, default 8 si no está seteado).
**Impacto por runtime:** ninguno (el RAG corre en backend antes de cualquier runtime).
**Trabajo del operador: ninguno** (opt-in desde UI).

---

### F3 — Telemetría: reportar chunks recuperados en el resumen de grounding

**Objetivo (1 frase).** Cuando el RAG está ON, agregar `rag_catalog_retrieved` y
`rag_catalog_total` al campo `epic_summary`/`grounding_observatory` para que el observatorio
muestre cuántos procesos se inyectaron vs. cuántos había en el catálogo. **Valor:** el operador
puede ver la eficacia del RAG sin ningún paso manual.

**Archivos a editar:**
- `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/services/context_enrichment.py`

**Cambio exacto (v2/C2 — body completo, fuente única de verdad).**
Reemplazar el body de `_inject_process_catalog_block` del Paso 3 de F2 por esta versión
final que integra `_rag_meta`. Este es el cuerpo DEFINITIVO de la función; F2/Paso 3 queda
OBSOLETO y debe ignorarse — este es el cuerpo correcto para implementar:

```python
def _inject_process_catalog_block(
    blocks: list[dict],
    project_name: str | None,
    log: LogFn,
    query: str | None = None,  # query para RAG (ticket title+description)
) -> list[dict]:
    """Plan 42 F0 + Plan 64 F2/F3 — Inyecta el bloque 'process-catalog'.

    Con STACKY_RAG_CATALOG_ENABLED=true y query disponible: recupera los top-K
    procesos más relevantes (TF-IDF puro) e incluye telemetría _rag_meta.
    Fallback: full-inject si RAG falla, está OFF, o query es vacío/None.
    Con STACKY_RAG_CATALOG_ENABLED=false (default): byte-idéntico al comportamiento anterior.
    Nota: _RAG_INDEX_CACHE usa un único slot; no es thread-safe para multi-worker gunicorn
    (para Stacky single-worker es OK; si se mueve a multi-worker, usar threading.Lock).
    """
    if os.getenv("STACKY_INJECT_PROCESS_CATALOG", "true").lower() in {"0", "false", "off"}:
        return blocks
    existing_ids = {b.get("id") for b in (blocks or []) if isinstance(b, dict)}
    if "process-catalog" in existing_ids:
        return blocks
    if not project_name:
        return blocks
    # Nota: ticket_id=None (flujo epic-from-brief sin ticket) → query=None → full-inject.
    # Esto es correcto: el brief tiene su propio contexto; el RAG aplica solo con ticket.
    try:
        from services.client_profile import load_client_profile
        profile = load_client_profile(project_name)
        if not isinstance(profile, dict):
            return blocks

        rag_enabled = os.getenv("STACKY_RAG_CATALOG_ENABLED", "false").lower() in {
            "1", "true", "on"
        }
        block: dict | None = None
        _rag_meta: dict | None = None

        if rag_enabled and query and query.strip():
            top_k_raw = os.getenv("STACKY_RAG_CATALOG_TOP_K", "8")
            try:
                top_k = max(1, int(top_k_raw))
            except ValueError:
                top_k = 8
            rag_result = build_process_dictionary_block_rag(profile, query=query, top_k=top_k)
            if rag_result is not None:
                block, n_retrieved = rag_result  # tuple (dict, int) — v2/C3
                catalog_size = len(profile.get("process_catalog") or [])
                log(
                    "info",
                    f"process-catalog RAG: {n_retrieved}/{catalog_size} procesos para proyecto={project_name}",
                )
                _rag_meta = {
                    "rag_enabled": True,
                    "retrieved": n_retrieved,       # exacto: len(results), no string-counted
                    "catalog_total": catalog_size,
                    "top_k": top_k,
                }

        # Fallback: full-inject (comportamiento original)
        if block is None:
            block = build_process_dictionary_block(profile)
            if block is not None:
                log("info", f"process-catalog inyectado para proyecto={project_name}")

        if block is None:
            return blocks

        # Agregar telemetría solo cuando RAG estuvo activo (no en full-inject)
        if _rag_meta is not None:
            block = dict(block)          # shallow copy para no mutar el objeto original
            block["_rag_meta"] = _rag_meta

        return list(blocks) + [block]
    except Exception as exc:  # noqa: BLE001
        log("warn", f"process-catalog no se pudo inyectar (continuando): {exc}")
        return blocks
```

> **Nota:** `_rag_meta` es metadata interna (prefijo `_`). Los runners procesan solo el campo
> `content` del bloque; los campos desconocidos se ignoran. El observatorio de grounding
> (plan 44, `services/grounding_observatory.py`) puede leer `_rag_meta` en el futuro;
> **no tocar `grounding_observatory.py` en este plan** (la integración es aditiva y diferida).

**Tests PRIMERO** — agregar a `tests/test_rag_context_enrichment.py`:

```python
def test_rag_block_has_meta_when_rag_on(monkeypatch):
    """Con RAG ON el bloque tiene _rag_meta con los conteos."""
    monkeypatch.setenv("STACKY_RAG_CATALOG_ENABLED", "true")
    monkeypatch.setenv("STACKY_RAG_CATALOG_TOP_K", "3")
    monkeypatch.setenv("STACKY_INJECT_PROCESS_CATALOG", "true")
    from services import context_enrichment as ce
    ce._RAG_INDEX_CACHE.clear()
    with patch("services.client_profile.load_client_profile", _make_profile_loader(PROFILE)):
        result = ce._inject_process_catalog_block(
            [], "mi-proyecto", lambda *a, **k: None, query="reportes conciliacion"
        )
    block = next(b for b in result if b.get("id") == "process-catalog")
    meta = block.get("_rag_meta")
    assert meta is not None
    assert meta["rag_enabled"] is True
    assert meta["catalog_total"] == len(CATALOG)
    assert 0 < meta["retrieved"] <= 3


def test_rag_block_no_meta_when_rag_off(monkeypatch):
    """Con RAG OFF el bloque NO tiene _rag_meta."""
    monkeypatch.setenv("STACKY_RAG_CATALOG_ENABLED", "false")
    monkeypatch.setenv("STACKY_INJECT_PROCESS_CATALOG", "true")
    from services import context_enrichment as ce
    with patch("services.client_profile.load_client_profile", _make_profile_loader(PROFILE)):
        result = ce._inject_process_catalog_block(
            [], "mi-proyecto", lambda *a, **k: None, query="reportes"
        )
    block = next(b for b in result if b.get("id") == "process-catalog")
    assert "_rag_meta" not in block
```

**Comando exacto:** mismo que F2 (mismo archivo de test).

**Criterio BINARIO:** los 2 tests nuevos + todos los de F2 pasan (exit 0).

**Flag:** ninguna nueva. **Runtime:** sin impacto. **Trabajo del operador: ninguno.**

---

### F4 — Ratchet de performance: el retriever es O(N) y termina en <100 ms

**Objetivo (1 frase).** Agregar un test de performance al ratchet del repo para garantizar que el
retriever no degrada latencia cuando el catálogo crece (≤100 ms para 500 procesos sintéticos).
**Valor:** seguridad de que el RAG no se convierte en un cuello de botella si el catálogo escala.

**Archivo a crear:**
`N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/tests/test_rag_perf.py`

```python
"""Test de performance del RAG (F4 — Plan 64). No debe superar 100 ms para N=500."""
import time
import pytest
from services.rag_retriever import build_index, retrieve, chunks_from_process_catalog


def _synthetic_catalog(n: int) -> list[dict]:
    return [
        {
            "name": f"Proceso{i:04d}",
            "kind": "batch",
            "purpose": f"Procesamiento de datos financieros tipo {i % 20} con validacion de saldos y movimientos",
        }
        for i in range(n)
    ]


def test_retriever_perf_500_chunks():
    """build_index + retrieve sobre 500 chunks debe completar en <100 ms."""
    catalog = _synthetic_catalog(500)
    chunks = chunks_from_process_catalog(catalog)
    t0 = time.perf_counter()
    index = build_index(chunks)
    results = retrieve(index, "validacion saldos movimientos financieros", top_k=8)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 100, f"RAG tardó {elapsed_ms:.1f} ms para N=500 (límite: 100 ms)"
    assert len(results) == 8


def test_retriever_perf_cache_hit_negligible():
    """Segunda llamada a build_index con mismo hash no reconstruye el índice (< 5 ms)."""
    from services.context_enrichment import _get_rag_index, _RAG_INDEX_CACHE
    _RAG_INDEX_CACHE.clear()
    catalog = _synthetic_catalog(200)
    _get_rag_index(catalog)  # build
    t0 = time.perf_counter()
    _get_rag_index(catalog)  # cache hit
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 5, f"Cache hit tardó {elapsed_ms:.1f} ms (límite: 5 ms)"
```

**Comando exacto:**
```powershell
& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest tests/test_rag_perf.py -q
```

**Criterio BINARIO:** los 2 tests de performance pasan en el entorno de desarrollo (exit 0).
Si el entorno de CI es particularmente lento, el límite de 100 ms puede relajarse a 300 ms
editando la constante en el test (no en el código de producción).

**Enlace al ratchet del repo (v2/C5):** agregar `test_rag_perf.py` al script de ratchet existente
del repo. Localizar con `grep -r "run_harness_tests\|pytest.*tests/" scripts/` y agregar el archivo
al grupo de tests que corre el ratchet. Si el script no existe aún en el repo, correr manualmente:
```powershell
& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest tests/test_rag_perf.py tests/test_rag_retriever.py tests/test_rag_context_enrichment.py -q
```

**Flag:** ninguna. **Runtime:** sin impacto. **Trabajo del operador: ninguno.**

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El retriever devuelve 0 resultados para un query extraño | `build_process_dictionary_block_rag` devuelve `None` → `_inject_process_catalog_block` usa full-inject (fallback). Test `test_rag_enabled_no_query_falls_back_to_full` lo verifica. |
| El catálogo tiene procesos con nombres homófonos (baja discriminación TF-IDF) | TF-IDF funciona a nivel lexical; para RSPACIFICO (procesos con nombres únicos como Mul2Bane/IncHost) es suficiente. Si el catálogo crece a >1000 entradas similares, se puede subir `TOP_K` desde la UI. |
| El catálogo cambia en runtime (reload del client_profile) | `_get_rag_index` usa MD5 del contenido; si el catálogo cambia, el hash cambia y el índice se reconstruye en la siguiente llamada. Test `test_rag_index_cache_hit` lo verifica. |
| Latencia de build_index en cada deploy con catálogos grandes | El índice se cachea en memoria por proceso (singleton del worker). El primer call post-startup paga O(N); los siguientes son O(Q). F4 garantiza <100 ms para N=500. |
| `_rag_meta` en el bloque llega al modelo y lo confunde | El campo `_rag_meta` es metadata interna (prefijo `_`). Los runners ya procesan el campo `content` del bloque, no los campos de metadata. Si algún runner lo pasa literalmente, el modelo lo ignora (no es instrucción). Mitigación adicional: renombrarlo a `__rag_meta__` si hay evidencia de fuga. |
| Plan 63 no implementado: flags sin categoría | Si `_CATEGORY_KEYS` no existe, los flags aparecen bajo `group="global"` en la UI del arnés — comportamiento idéntico al pre-63. No bloqueante. |
| Tokenización en español (tildes, ñ) | `_tokenize` usa `\w` con `re.UNICODE` (default en Python 3) → tildes y ñ se incluyen. Test `test_tokenize_basic` lo verifica implícitamente. Para afinar, se puede agregar normalización NFC (stdlib `unicodedata`). |

---

## 6. Fuera de scope

- **Vectores semánticos (embeddings):** no se usa ningún modelo de embeddings. El TF-IDF lexical
  es suficiente para catálogos de procesos con nombres técnicos únicos y propósitos descriptivos.
  Si en el futuro se quiere semántica real, este módulo es el seam correcto para reemplazar el
  retriever sin tocar el wiring.
- **RAG sobre documentos de texto libre** (CATALOGO_PROCESOS_BATCH.md, technical_master.md):
  este plan solo aplica RAG al `process_catalog` estructurado (lista de dicts). La extensión a
  docs markdown es un plan futuro que puede reusar `rag_retriever.py` con chunks de secciones.
- **RAG sobre lecciones/goldens del arnés** (planes 54/56): fuera de scope. El corpus de
  lecciones ya tiene su propia lógica de retrieval (`few_shot.py`, `rejection_lessons.py`).
- **UI de visualización de chunks recuperados:** la telemetría `_rag_meta` queda disponible
  para el observatorio de grounding (plan 44); la integración visual es un plan futuro.
- **Soporte multi-catálogo simultáneo** (varios proyectos activos en el mismo worker): el
  cache es un dict simple con 1 entrada (clear en cada cambio). Si en el futuro hay múltiples
  proyectos activos a la vez, se puede hacer el cache keyed por (project, hash). Fuera de scope.
- **Integración con `_apply_context_budget`** (plan 42, línea 194): el budget ya puede podar
  bloques; el RAG reduce el tamaño del bloque antes del budget, son complementarios sin
  conflicto.

---

## 7. Glosario + Orden de implementación + DoD

**Glosario (términos Stacky y RAG para un modelo menor):**

- **TF-IDF (Term Frequency-Inverse Document Frequency):** técnica de recuperación de información
  que pondera la relevancia de un término en un documento relativa a su frecuencia global en el
  corpus. No requiere dependencias externas; es puro álgebra de vectores.
- **Cosine similarity:** medida de similitud entre dos vectores (0.0 = ortogonal/irrelevante;
  1.0 = idéntico). Se usa para rankear chunks por relevancia a un query.
- **RagChunk:** unidad indexable: un proceso del catálogo con su texto y su payload (dict original).
- **RagIndex:** estructura inmutable con los vectores TF-IDF de todos los chunks + el IDF global.
- **process_catalog:** lista de dicts `{name, kind, purpose}` en el `client_profile` del proyecto.
  En RSPACIFICO tiene ≥200 procesos batch (Mul2Bane, IncHost, RSCore, RsExtrae, GenReporte, etc.).
- **client_profile:** datos de configuración del proyecto cargados por `load_client_profile`.
- **block:** dict `{id, kind, content}` que se inyecta en el contexto del agente antes de cada run.
- **context_enrichment:** módulo Python (`services/context_enrichment.py`) que construye la lista
  de bloques de contexto para el agente. El RAG se enchufa en `_inject_process_catalog_block`.
- **FLAG_REGISTRY:** tupla de `FlagSpec` en `services/harness_flags.py`. Toda flag registrada aquí
  aparece automáticamente en la UI del arnés (plan 33/63); no hay que tocar el frontend.
- **full-inject:** comportamiento actual (pre-Plan 64): inyectar TODOS los procesos del catálogo
  como un único bloque de texto.
- **content_hash:** MD5 del contenido serializado del catálogo. Sirve como clave de cache para
  invalidar el índice TF-IDF cuando el catálogo cambia.
- **3 runtimes:** Codex CLI, Claude Code CLI, GitHub Copilot Pro. El RAG corre en backend (Python
  puro) antes de cualquier runtime → ningún runtime sabe si el catálogo fue reducido por RAG.

**Orden de implementación:**
1. F0 — Crear `services/rag_retriever.py` + todos sus tests → verde.
2. F1 — Agregar 2 `FlagSpec` en `FLAG_REGISTRY` + 4 tests → verde.
3. F2 — Wiring en `context_enrichment.py` + 9 tests → verde.
4. F3 — Telemetría `_rag_meta` + 2 tests → verde.
5. F4 — Ratchet de performance → verde.

**Definición de Hecho (DoD) global:**
- [ ] `tests/test_rag_retriever.py` — **15** tests verdes (13 originales + 2 discriminación dominio RSPACIFICO).
- [ ] `tests/test_harness_flags.py` — 4 tests nuevos + todos los existentes verdes.
- [ ] `tests/test_rag_context_enrichment.py` — 11 tests verdes (9 de F2 + 2 de F3).
- [ ] `tests/test_rag_perf.py` — 2 tests de performance verdes (<100 ms para N=500).
- [ ] Con `STACKY_RAG_CATALOG_ENABLED=false` (default), el comportamiento de
  `_inject_process_catalog_block` es **byte-idéntico al actual** (full-inject).
- [ ] `STACKY_RAG_CATALOG_ENABLED` y `STACKY_RAG_CATALOG_TOP_K` aparecen en la UI del arnés
  (verificar en `GET /api/harness-flags`).
- [ ] Ninguna dependencia externa nueva (solo stdlib: `math`, `re`, `collections`, `hashlib`,
  `json`). Verificar con: `python -c "import services.rag_retriever"` en el venv sin instalar nada.
- [ ] El full-inject sigue funcionando cuando el flag está OFF (test `test_rag_disabled_injects_full_catalog`).
- [ ] El RAG degrada limpiamente a full-inject cuando el query es vacío/None
  (test `test_rag_enabled_no_query_falls_back_to_full`).
- [ ] No se implementó código fuera del alcance de este plan (no se tocaron runners, frontend,
  grounding_observatory.py ni otros módulos).
