# Plan 115 — Consolidación de los 3 motores TF-IDF en un núcleo léxico compartido (refactor puro, cero cambio de comportamiento)

> **Estado:** CRITICADO v2 — 2026-07-10 (v1 → v2 por `criticar-y-mejorar-plan`)
> **Veredicto del juez:** APROBADO-CON-CAMBIOS (C1-C3 IMPORTANTES resueltos en esta v2; sin bloqueantes)
>
> **CHANGELOG v1 → v2:**
> - **C1 (IMPORTANTE, el más grave):** el pseudocódigo de `lexical_core.term_frequencies` devuelve CONTEOS crudos (`dict(Counter(tokens))`), que es exactamente lo que hoy usan `docs_rag.py` y `memory_store.py` — pero `rag_retriever.py._tf` (rag_retriever.py:36-41) usa **frecuencia RELATIVA** (`count / len(tokens)`), no cruda. Si `rag_retriever` migra llamando a `term_frequencies` tal cual, TODOS sus scores cambian y el golden de F3 revienta de entrada — el propio DoD del plan ("byte-idéntico") se auto-viola. Fix: `lexical_core` gana un segundo helper `normalized_term_frequencies(tokens) -> dict[str, float]` (= `term_frequencies` dividido por `len(tokens)`); el adaptador de F3 usa ESE, los de F2/F4 usan `term_frequencies` (crudo). Documentado literal en F1 y F3.
> - **C2 (IMPORTANTE):** "preservar la cache `_IdfCache`" (F2) y "preservar la API pública de memoria" (F4) eran instrucciones de alto nivel sin mecanismo. Especificado literal: cada adaptador mantiene SU PROPIO dict/objeto de cache tal como existe hoy (`_idf_caches`/`_get_idf` en docs_rag.py:205-230 sin tocar su forma ni TTL) y solo reemplaza el CUERPO del cálculo (el `for`/`math.log`) por una llamada a `lexical_core.inverse_doc_frequencies`; la cache en sí no se mueve al núcleo.
> - **C3 (IMPORTANTE):** F2 corre `tests/test_plan112_search_hybrid.py` incondicionalmente — si el plan 112 todavía no está implementado en el checkout, ese comando falla por `ERROR: file not found`, no por regresión real, y un modelo menor lo interpretaría como que el propio refactor está roto. Fix: F2 usa el mismo patrón condicional que ya usa F3 ("si el archivo existe, correrlo también; si no, omitirlo sin que cuente como fallo") — instrucción literal con `test -f`/`Test-Path` según el runtime.
> - **C4 (MENOR):** corrección de precisión — la intro decía "tokenizers ligeramente distintos" en los 3 motores; en realidad `memory_store.py` NO tiene tokenizer propio: importa `_tokenize` de `services/embeddings.py:42-43` (memory_store.py:55), que es el MISMO regex de 3+ caracteres que usa `docs_rag.py` (docs_rag.py:34). Solo hay 2 políticas de tokenización distintas hoy (rag_retriever vs. embeddings/docs_rag/memory_store), no 3. No cambia ninguna fase, solo la precisión del diagnóstico.
> - **[ADICIÓN ARQUITECTO]:** el punto 3 de F5 ("confirmar por lectura del diff que ya no definen su propio TF-IDF") queda como inspección manual — se agrega un meta-test automático `test_plan115_no_duplicate_math.py` que hace `grep`-like sobre los 3 archivos (`re.search(r"math\.log\(", contenido)` fuera de `lexical_core.py`) y falla si alguno todavía calcula IDF por su cuenta. Convierte un ítem de checklist humano en un binario verificable, sin costo ni riesgo (solo lee archivos).
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

def term_frequencies(tokens: list[str]) -> dict[str, int]:
    """Conteos CRUDOS. Usan esto docs_rag y memory_store (hoy también crudo)."""
    return dict(Counter(tokens))

def normalized_term_frequencies(tokens: list[str]) -> dict[str, float]:
    """(C1) Frecuencia RELATIVA (count / total). Usa esto rag_retriever: su
    `_tf` actual (rag_retriever.py:36-41) divide por len(tokens), NO usa
    conteos crudos. Migrar rag_retriever con `term_frequencies` (crudo) en vez
    de esta función CAMBIA todos sus scores y revienta el golden de F3."""
    n = len(tokens)
    if n == 0:
        return {}
    counts = term_frequencies(tokens)
    return {term: c / n for term, c in counts.items()}

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

**Tests PRIMERO — archivo:** `backend/tests/test_plan115_lexical_core.py`: pruebas unitarias puras de `tokenize`/`term_frequencies`/`normalized_term_frequencies`/`inverse_doc_frequencies`/`cosine_tfidf` (valores conocidos). **(C1)** incluir `test_normalized_term_frequencies_divides_by_length` (p.ej. tokens `["a","a","b"]` → `{"a": 2/3, "b": 1/3}`) y `test_term_frequencies_stays_raw_counts` (mismos tokens → `{"a": 2, "b": 1}`) para dejar la diferencia fijada por test, no solo por docstring.

**Comando:** `venv/Scripts/python.exe -m pytest tests/test_plan115_lexical_core.py -q`

**Criterio BINARIO:** verdes. **Trabajo del operador:** ninguno.

---

### F2 — Migrar `docs_rag.py` al núcleo (golden verde)

**Objetivo (1 frase).** Reemplazar el TF-IDF interno de `docs_rag` por llamadas a `lexical_core`, preservando `search()` byte-idéntico. **Valor:** primer motor consolidado, verificado por su golden.

**Archivo a editar:** `backend/services/docs_rag.py` — reemplazar `_tokenize`/cálculo de IDF/coseno por `lexical_core` con la `TokenizeOptions` que replique el tokenizer actual (ajustar `pattern`/`min_len`/`stopwords` hasta que el golden de F0 pase). Usar `lexical_core.term_frequencies` (CRUDO — docs_rag ya usa conteos crudos vía `Counter`, C1 no aplica acá). **(C2) Preservar `_get_idf`/`_idf_caches` literal:** `_get_idf` (docs_rag.py:209-230) NO se borra ni se mueve al núcleo; solo su cuerpo interno (el `for`/`math.log`) pasa a llamar `lexical_core.inverse_doc_frequencies(token_sets)` en vez de calcularlo a mano. El dict `_idf_caches` y el TTL de 300 s quedan exactamente donde están.

**Test:** el golden `test_plan115_golden_docs_rag.py` (de F0) debe pasar **sin cambios** contra el código refactorizado.

**Comando:**
```
venv/Scripts/python.exe -m pytest tests/test_plan115_golden_docs_rag.py -q
```
**(C3)** Si `Stacky Agents/backend/tests/test_plan112_search_hybrid.py` YA existe en el checkout (el plan 112 fue implementado), correrlo también en el mismo comando; si el archivo no existe, NO correrlo — su ausencia no es un fallo de este plan.

**Criterio BINARIO:** golden verde (+ los tests del 112 verdes, solo si el archivo existe).

**Trabajo del operador:** ninguno.

---

### F3 — Migrar `rag_retriever.py` al núcleo (golden verde)

**Objetivo (1 frase).** Igual que F2 para `rag_retriever`. **Valor:** segundo motor consolidado.

**Archivo a editar:** `backend/services/rag_retriever.py` — usar `lexical_core` con su `TokenizeOptions`. **(C1) OBLIGATORIO:** `_tf` (rag_retriever.py:36-41) usa frecuencia RELATIVA (`count/n`, no cruda) → el adaptador debe llamar `lexical_core.normalized_term_frequencies`, **NUNCA** `lexical_core.term_frequencies` (que daría conteos crudos y cambiaría todos los scores). El resto (`_build_idf`→`inverse_doc_frequencies`, `_cosine`→`cosine_tfidf`) sí puede usar las funciones "crudas" del núcleo porque ya reciben vectores ponderados. Preservar la firma pública (la usa `context_enrichment.py`).

**Test:** golden `test_plan115_golden_rag_retriever.py` verde sin cambios; correr también los tests del plan 64 si existen.

**Comando:** `venv/Scripts/python.exe -m pytest tests/test_plan115_golden_rag_retriever.py -q`

**Criterio BINARIO:** golden verde.

**Trabajo del operador:** ninguno.

---

### F4 — Migrar `memory_store.py` al núcleo (golden verde)

**Objetivo (1 frase).** Igual para el TF-IDF de `memory_store.py:999-1014`. **Valor:** tercer motor consolidado; duplicación eliminada.

**Archivo a editar:** `backend/services/memory_store.py` — usar `lexical_core` con su `TokenizeOptions` (replicar el tokenizer de `embeddings.py:42-43`, que hoy YA comparte vía `from services.embeddings import _tokenize`, memory_store.py:55 — C4: no son 3 tokenizers distintos, memory_store nunca tuvo uno propio). Usar `lexical_core.term_frequencies` (CRUDO — memory_store ya usa `Counter` sin normalizar, igual que docs_rag; C1 no aplica acá, solo a rag_retriever). Preservar la API pública de memoria; el cálculo de IDF en memoria (memory_store.py:1004) no tiene cache propia hoy — no se le agrega una.

**Test:** golden `test_plan115_golden_memory_store.py` verde sin cambios; correr tests de memoria existentes.

**Comando:** `venv/Scripts/python.exe -m pytest tests/test_plan115_golden_memory_store.py -q`

**Criterio BINARIO:** golden verde.

**Trabajo del operador:** ninguno.

---

### F5 — Cierre: no-regresión global y DoD

**Acciones:**
1. Registrar los tests nuevos en `run_harness_tests.sh` y `.ps1` — incluyendo el meta-test de la adición arquitecto (punto 3).
2. No-regresión (desde `Stacky Agents/backend`):
   ```
   venv/Scripts/python.exe -m pytest tests/test_plan115_lexical_core.py tests/test_plan115_golden_docs_rag.py tests/test_plan115_golden_rag_retriever.py tests/test_plan115_golden_memory_store.py tests/test_plan115_no_duplicate_math.py -q
   ```
3. **[ADICIÓN ARQUITECTO]** Crear `backend/tests/test_plan115_no_duplicate_math.py`: automatiza lo que v1 dejaba como "lectura manual del diff". Para cada uno de `services/rag_retriever.py`, `services/docs_rag.py`, `services/memory_store.py`: leer el archivo como texto y assert (a) `"from services import lexical_core" in contenido` o `"from services.lexical_core import" in contenido` (importa el núcleo); (b) `re.search(r"math\.log\(", contenido)` es `None` (ya no calcula IDF a mano — la única ocurrencia de `math.log` para IDF debe vivir en `lexical_core.py`, verificado con un 4º assert sobre ESE archivo que SÍ debe contenerlo).

**Criterio BINARIO global (DoD):**
- [ ] Los 3 goldens (capturados en F0 contra el código viejo) pasan IGUAL contra el código refactorizado.
- [ ] `lexical_core.py` es el único lugar con la matemática TF-IDF; los 3 motores la importan (verificado automáticamente, no solo por lectura — adición arquitecto).
- [ ] `rag_retriever.py` usa `normalized_term_frequencies` (frecuencia relativa); `docs_rag.py`/`memory_store.py` usan `term_frequencies` (crudo) — la distinción C1 respetada y fijada por test.
- [ ] Ningún endpoint/payload/flag cambió; cero deps nuevas.
- [ ] Los tests preexistentes de docs_rag / plan 64 / memoria siguen verdes.

---

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Cambiar sutilmente un score y degradar el retrieval. | Goldens capturados ANTES (F0) que fijan valores numéricos exactos; cada migración debe pasarlos sin editarlos. |
| **(C1)** Migrar `rag_retriever` con TF crudo en vez de normalizado (cambiaría TODOS sus scores). | `lexical_core` expone `normalized_term_frequencies` además de `term_frequencies`; F3 exige literal cuál usar; 2 tests unitarios en F1 fijan la diferencia. |
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
