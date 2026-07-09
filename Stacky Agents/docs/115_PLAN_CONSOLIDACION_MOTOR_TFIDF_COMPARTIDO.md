# Plan 115 — Consolidación de los 3 motores TF-IDF en un núcleo léxico compartido (refactor puro, cero cambio de comportamiento)

> **Estado:** PROPUESTO v1 — 2026-07-09
> **Serie:** Documentación agéntica Obsidian (109 → 111 → 112 → 113 → 114 → **115**, opcional/último). El número 110 quedó tomado por un plan ajeno (Revisor de PRs).
> **Pipeline:** este documento pasó `proponer` (este estado). Sigue `criticar-y-mejorar-plan` → `implementar-plan-stacky` → `supervisar-implementaciones-planes`.
> **Depende de:** nada nuevo. Es un **refactor puro** de código existente. **Recomendado implementar DESPUÉS del 112** (para no mover el motor mientras 112 lo extiende).

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** El backend tiene **tres implementaciones paralelas de TF-IDF léxico** que se relevaron durante la serie: `services/rag_retriever.py` (catálogo de procesos, plan 64), `services/docs_rag.py` (documentación por proyecto) y `services/memory_store.py:999-1014` (memoria colaborativa). Comparten la misma matemática (tokenizar → TF → IDF → coseno) con tokenizers ligeramente distintos. Este plan **extrae un único núcleo léxico compartido** `services/lexical_core.py` (tokenizador + TF/IDF + coseno, funciones puras, cero deps) y hace que los tres consumidores lo usen **sin cambiar su comportamiento observable** (mismos scores, mismos rankings, mismos payloads). Es un refactor de **higiene**: menos superficie, un solo lugar donde arreglar/optimizar, y una base limpia si el híbrido (112) se quisiera llevar a los otros motores. **Es opcional**: solo se justifica si el operador quiere pagar el refactor por la deuda técnica; no agrega ninguna feature.

**KPI / impacto esperado.**
- **Byte-idéntico (binario, el KPI que manda):** para cada uno de los 3 motores existe un test golden que fija sus salidas ANTES del refactor y las verifica IGUALES después. Si algo cambia un score, el refactor está mal.
- **Menos duplicación:** de 3 tokenizers/TF-IDF a 1 núcleo + 3 adaptadores finos. Meta: las funciones matemáticas duplicadas quedan en un solo módulo.
- **Cero deps nuevas, cero features:** no cambia ningún endpoint, ningún payload, ninguna flag.

---

## 2. Por qué ahora / gap que cierra

1. La serie 109-114 tocó/leyó los tres motores y confirmó la duplicación (memoria `docs-rag-substrate`). Es el momento natural de consolidar, con los goldens frescos.
2. Cada bug o mejora léxica hoy hay que hacerlo 3 veces (o peor, se hace en 1 y los otros divergen). Un núcleo único elimina esa clase de drift.
3. **Por qué al final y opcional:** mover el motor mientras 112 lo extiende sería arriesgado; hacerlo después, con goldens, es seguro. Y como no da feature, su prioridad es la más baja de la serie.

---

## 3. Principios y guardarraíles (NO negociables)

- **Refactor puro = comportamiento idéntico.** Prohibido cambiar scores, orden de resultados, tokenización efectiva o payloads. Los goldens lo garantizan.
- **3 runtimes con paridad total.** Backend puro; ningún runtime interviene. Trivial.
- **Cero trabajo al operador, cero features, cero flags.** No hay nada opt-in: o el refactor es transparente o no se hace.
- **No degradar performance.** El núcleo compartido no debe ser más lento; si algún motor tenía una optimización (p.ej. cache de IDF en `docs_rag`), se preserva en su adaptador.
- **Reversible por diseño.** Cada motor se migra en su propia fase con su golden; si uno falla, se revierte solo ese sin afectar a los otros.
- **Sin ambigüedad para modelos menores.** Archivo, símbolo, golden nombrado + comando, criterio binario por fase.

---

## 4. Nombres canónicos (usar EXACTAMENTE estos)

| Concepto | Nombre exacto |
|---|---|
| Núcleo nuevo | `backend/services/lexical_core.py` |
| Tokenizador | `tokenize(text: str) -> list[str]` |
| TF | `term_frequencies(tokens: list[str]) -> dict[str, int]` |
| IDF | `inverse_doc_frequencies(doc_term_sets: list[set[str]]) -> dict[str, float]` |
| Similitud | `cosine_tfidf(query_tf, doc_tf, idf) -> float` |
| Flag | (ninguna — es refactor transparente) |

> **Nota sobre tokenizers divergentes:** si los 3 motores tokenizan distinto, `tokenize` acepta un parámetro de política (`TokenizeOptions`) con los defaults que **replican exactamente** el tokenizer de cada motor; cada adaptador pasa su política. NO se unifica el comportamiento, se unifica el CÓDIGO.

---

## 5. Fases

### F0 — Goldens de captura (ANTES de tocar nada)

**Objetivo (1 frase).** Fijar la salida actual de los 3 motores como golden, para comparar después. **Valor:** la red de seguridad del refactor.

**Archivos a crear (tests que capturan el comportamiento ACTUAL):**
- `backend/tests/test_plan115_golden_rag_retriever.py` — corpus fijo → top-K con scores exactos de `rag_retriever` (hoy).
- `backend/tests/test_plan115_golden_docs_rag.py` — corpus fijo → `search()` con `DocHit.score` exactos (hoy).
- `backend/tests/test_plan115_golden_memory_store.py` — corpus fijo → ranking/score exactos del TF-IDF de `memory_store` (hoy).

Cada golden fija valores numéricos redondeados (p.ej. 6 decimales) y orden. Registrar en `run_harness_tests.sh` y `.ps1`.

**Comando (desde `Stacky Agents/backend`):**
```
venv/Scripts/python.exe -m pytest tests/test_plan115_golden_rag_retriever.py tests/test_plan115_golden_docs_rag.py tests/test_plan115_golden_memory_store.py -q
```

**Criterio BINARIO:** 3 goldens verdes CONTRA el código actual (antes del refactor).

**Trabajo del operador:** ninguno.

---

### F1 — Crear `lexical_core.py` (funciones puras + política de tokenización)

**Objetivo (1 frase).** El núcleo compartido, con `TokenizeOptions` que puede reproducir cada tokenizer existente. **Valor:** un solo lugar para la matemática léxica.

**Archivo a crear:** `backend/services/lexical_core.py`.

**Diseño EXACTO:**
```python
from dataclasses import dataclass
from collections import Counter
import math, re

@dataclass(frozen=True)
class TokenizeOptions:
    lowercase: bool = True
    min_len: int = 2
    pattern: str = r"[a-záéíóúñ0-9]+"   # ajustar por adaptador para replicar cada motor
    stopwords: frozenset = frozenset()

def tokenize(text: str, opts: TokenizeOptions = TokenizeOptions()) -> list[str]:
    t = (text or "")
    if opts.lowercase: t = t.lower()
    toks = re.findall(opts.pattern, t)
    return [w for w in toks if len(w) >= opts.min_len and w not in opts.stopwords]

def term_frequencies(tokens): return dict(Counter(tokens))

def inverse_doc_frequencies(doc_term_sets):
    n = len(doc_term_sets) or 1
    df = Counter()
    for s in doc_term_sets:
        for term in s: df[term] += 1
    return {t: math.log(n / (1 + c)) + 1.0 for t, c in df.items()}   # replicar la fórmula usada hoy

def cosine_tfidf(query_tf, doc_tf, idf):
    qv = {t: query_tf[t] * idf.get(t, 1.0) for t in query_tf}
    dv = {t: doc_tf.get(t, 0) * idf.get(t, 1.0) for t in doc_tf}
    dot = sum(qv[t] * dv.get(t, 0.0) for t in qv)
    qn = math.sqrt(sum(v*v for v in qv.values())) or 1.0
    dn = math.sqrt(sum(v*v for v in dv.values())) or 1.0
    return dot / (qn * dn)
```
> **CLAVE:** la fórmula de IDF y el coseno deben ser IDÉNTICOS a los de `docs_rag.search` (ver `docs_rag.py:276-300`) y los otros motores. Si difieren entre motores, `lexical_core` provee variantes parametrizadas (p.ej. `idf_variant="log_smooth"`) y cada adaptador elige la suya. **No se elige "la mejor": se replica cada una.**

**Tests PRIMERO — archivo:** `backend/tests/test_plan115_lexical_core.py`: pruebas unitarias puras de `tokenize`/`term_frequencies`/`inverse_doc_frequencies`/`cosine_tfidf` (valores conocidos).

**Comando:** `venv/Scripts/python.exe -m pytest tests/test_plan115_lexical_core.py -q`

**Criterio BINARIO:** verdes. **Trabajo del operador:** ninguno.

---

### F2 — Migrar `docs_rag.py` al núcleo (golden verde)

**Objetivo (1 frase).** Reemplazar el TF-IDF interno de `docs_rag` por llamadas a `lexical_core`, preservando `search()` byte-idéntico. **Valor:** primer motor consolidado, verificado por su golden.

**Archivo a editar:** `backend/services/docs_rag.py` — reemplazar `_tokenize`/`_compute_tf`/cálculo de IDF/coseno por `lexical_core` con la `TokenizeOptions` que replique el tokenizer actual (ajustar `pattern`/`min_len`/`stopwords` hasta que el golden de F0 pase). Preservar la cache `_IdfCache` (envolver el `inverse_doc_frequencies` del núcleo).

**Test:** el golden `test_plan115_golden_docs_rag.py` (de F0) debe pasar **sin cambios** contra el código refactorizado.

**Comando:** `venv/Scripts/python.exe -m pytest tests/test_plan115_golden_docs_rag.py tests/test_plan112_search_hybrid.py -q`

**Criterio BINARIO:** golden verde + los tests del 112 (si ya está) siguen verdes.

**Trabajo del operador:** ninguno.

---

### F3 — Migrar `rag_retriever.py` al núcleo (golden verde)

**Objetivo (1 frase).** Igual que F2 para `rag_retriever`. **Valor:** segundo motor consolidado.

**Archivo a editar:** `backend/services/rag_retriever.py` — usar `lexical_core` con su `TokenizeOptions`. Preservar su firma pública (la usa `context_enrichment.py`).

**Test:** golden `test_plan115_golden_rag_retriever.py` verde sin cambios; correr también los tests del plan 64 si existen.

**Comando:** `venv/Scripts/python.exe -m pytest tests/test_plan115_golden_rag_retriever.py -q`

**Criterio BINARIO:** golden verde.

**Trabajo del operador:** ninguno.

---

### F4 — Migrar `memory_store.py` al núcleo (golden verde)

**Objetivo (1 frase).** Igual para el TF-IDF de `memory_store.py:999-1014`. **Valor:** tercer motor consolidado; duplicación eliminada.

**Archivo a editar:** `backend/services/memory_store.py` — usar `lexical_core` con su `TokenizeOptions` (replicar el tokenizer de `embeddings.py:55` que hoy comparte). Preservar la API pública de memoria.

**Test:** golden `test_plan115_golden_memory_store.py` verde sin cambios; correr tests de memoria existentes.

**Comando:** `venv/Scripts/python.exe -m pytest tests/test_plan115_golden_memory_store.py -q`

**Criterio BINARIO:** golden verde.

**Trabajo del operador:** ninguno.

---

### F5 — Cierre: no-regresión global y DoD

**Acciones:**
1. Registrar los tests nuevos en `run_harness_tests.sh` y `.ps1`.
2. No-regresión (desde `Stacky Agents/backend`):
   ```
   venv/Scripts/python.exe -m pytest tests/test_plan115_lexical_core.py tests/test_plan115_golden_docs_rag.py tests/test_plan115_golden_rag_retriever.py tests/test_plan115_golden_memory_store.py -q
   ```
3. Confirmar por lectura del diff que `rag_retriever.py`, `docs_rag.py` y `memory_store.py` ya **no** definen su propio TF-IDF (importan `lexical_core`).

**Criterio BINARIO global (DoD):**
- [ ] Los 3 goldens (capturados en F0 contra el código viejo) pasan IGUAL contra el código refactorizado.
- [ ] `lexical_core.py` es el único lugar con la matemática TF-IDF; los 3 motores la importan.
- [ ] Ningún endpoint/payload/flag cambió; cero deps nuevas.
- [ ] Los tests preexistentes de docs_rag / plan 64 / memoria siguen verdes.

---

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Cambiar sutilmente un score y degradar el retrieval. | Goldens capturados ANTES (F0) que fijan valores numéricos exactos; cada migración debe pasarlos sin editarlos. |
| Tokenizers realmente distintos entre motores. | `TokenizeOptions` parametriza (pattern/min_len/stopwords) para REPLICAR cada uno; no se unifica el comportamiento, solo el código. |
| Perder una optimización (cache IDF de docs_rag). | Se preserva en el adaptador (envolviendo el núcleo), no en el núcleo. |
| Refactor que se mezcla con features de 112. | Este plan va DESPUÉS del 112; goldens del 112 se corren en F2 para confirmar que sigue verde. |
| Un motor no migra limpio. | Cada motor es una fase independiente y reversible; se puede dejar 1 sin migrar sin afectar a los otros. |

---

## 7. Fuera de scope

- Mejorar la calidad del retrieval (esto es refactor, no feature).
- Migrar a embeddings o unificar el comportamiento de los tokenizers.
- Llevar el híbrido (112) a `rag_retriever`/`memory_store` (posible plan futuro, no acá).
- Tocar `lexical_core` para agregar variantes no usadas por ningún motor.

---

## 8. Glosario (términos para modelos menores)

- **TF-IDF:** term-frequency × inverse-document-frequency; puntaje léxico clásico.
- **Coseno:** similitud entre dos vectores TF-IDF.
- **Golden byte-idéntico:** test que fija la salida exacta actual y exige que no cambie tras el refactor.
- **Adaptador:** capa fina en cada motor que llama al núcleo con su política de tokenización.
- **`TokenizeOptions`:** parámetros que hacen que el núcleo reproduzca el tokenizer de cada motor.
- **Refactor puro:** cambia el código, no el comportamiento observable.
- **venv del repo:** `Stacky Agents/backend/venv` (Python 3.13); pytest por archivo.

---

## 9. Orden de implementación (secuencial)

1. **F0** — capturar los 3 goldens contra el código actual.
2. **F1** — crear `lexical_core.py` + tests unitarios.
3. **F2** — migrar `docs_rag.py` (golden verde).
4. **F3** — migrar `rag_retriever.py` (golden verde).
5. **F4** — migrar `memory_store.py` (golden verde).
6. **F5** — cierre, no-regresión, DoD.

---

## 10. Definición de Hecho (DoD) — resumen binario

Hecho cuando: (a) los 3 goldens capturados en F0 pasan idénticos contra el código refactorizado; (b) `lexical_core.py` concentra toda la matemática TF-IDF y los tres motores lo importan en vez de duplicarla; (c) ningún endpoint, payload, flag o dependencia cambió; (d) los tests preexistentes de docs_rag, plan 64 y memoria siguen verdes; (e) el diff confirma que ya no hay TF-IDF duplicado en los tres servicios.
