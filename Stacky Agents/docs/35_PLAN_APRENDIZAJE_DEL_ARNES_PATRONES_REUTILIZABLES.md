# 35 — Plan Aprendizaje del Arnés: convertir las señales de verificación que hoy se descartan en patrones persistentes y reutilizables que amplifican al operador, sin sacarlo del lazo

**Fecha original:** 2026-06-16 · **Revisión v2:** 2026-08-01 · **Revisión v3:** 2026-08-01
**Versión:** **v2 -> v3** (incorpora las DOS decisiones de diseño del operador + 7 bloqueantes mecánicos)
**Estado:** PROPUESTO — MEJORADO v3 (v1 RECHAZADO por 7 bloqueantes; v2 RECHAZADO por 6 bloqueantes + 2 preguntas de diseño abiertas; v3 cierra las dos preguntas por decisión del operador y corrige los 7 defectos mecánicos — ver §14)
**Autor:** StackyArchitectaUltraEficientCode
**Predecesores directos (motor + verificación):** `docs/27` (contexto/retrieval/routing/caché), `docs/28` (lifecycle/telemetría), `docs/29` (criterios + few-shot + repair semántico), `docs/30` (verificación determinista de existencia), `docs/31` (verificación ejecutable del entregable), `docs/32` (contrato de aceptación pre-run).
**Predecesores de método:** `docs/26` (memoria configurable), memoria colaborativa (Fase A-E + hardening), `docs/33` (flags 100% configurables por UI), `docs/34` (Client Profile).
**Audiencia:** dev agéntico junior (Haiku, Codex CLI, GitHub Copilot Pro). Cada fase es autocontenida: objetivo en 1 frase, archivos EXACTOS, símbolos EXACTOS, pseudocódigo que **compila contra la firma real**, tests primero con comando exacto, criterio de aceptación binario y satisfacible, flag con default justificado, impacto por runtime y línea de "trabajo del operador".

---

## CHANGELOG v2 -> v3 (qué cambió y qué lo motivó)

| # | Cambio | Origen |
|---|---|---|
| 1 | **`confidence` se filtra EN PYTHON, no en SQL.** `list_observations` (firma real `services/memory_store.py:822-829`) **no acepta** filtro de confianza; armar una query propia habría duplicado el motor de acceso. Se trae el conjunto acotado por `project+scope+status` y se filtra en memoria. | **Decisión (a) del operador** |
| 2 | **El guardarraíl 9 y el criterio C9 se REESCRIBEN** para decir lo que la implementación hace. La v2 exigía "filtrar en SQL" y la implementación no puede: un criterio que la implementación viola es un falso rojo garantizado. | **Decisión (a)** — consecuencia obligatoria |
| 3 | **Desvío declarado del `limit`:** `list_observations` ordena por `updated_at desc` y **después** aplica `.limit()` -> recorta por **recencia**, no por confianza. Un patrón muy bueno pero viejo puede quedar fuera de la ventana. Se fija `_PATTERN_SCAN_LIMIT = 500` y se declara el desvío en §13. | **Decisión (a)** — consecuencia medida |
| 4 | **`compute_confidence` se mantiene on-read en F3** (ya no hay razón para adelantarlo: con el filtro en Python el valor calculado es el que manda). | **Decisión (a)** |
| 5 | **El descarte del operador es de POR VIDA, con guard propio en `persist_pattern`.** Antes de upsertear, si ya existe una observación con ese `topic_key` en estado `rejected`, no se re-crea ni se reactiva. El guard **no** va en `memory_store` (no se rompe el contrato genérico para otros consumidores). | **Decisión (b) del operador** |
| 6 | **Gate anti-falso-verde estructural de (b):** el test que lo prueba **cosecha, descarta y VUELVE A COSECHAR** con el mismo camino de producción. Un test que fabrica la fila a mano no prueba el guard. | **Decisión (b)** — consecuencia |
| 7 | **Los tests se numeran POR ARCHIVO, no globalmente.** El criterio "23 passed" de F3 en v2 era aritméticamente imposible: F0 aporta 8 + F1 aporta 8 (el 9º de F1 va a otro archivo) + F3 aportaba 6 = **22**, no 23. | **B1** |
| 8 | **`test_harness_flags.py` NO tiene rojos preexistentes: da `56 passed, 0 failed` (medido 2026-08-01).** Los 4 fallos ajenos son de `test_harness_flags_help.py`, otro archivo. El criterio **delta** de v2 sobre ese archivo se reemplaza por un criterio **absoluto** `59 passed, 0 failed`. | **B7 (nuevo, verificado)** |
| 9 | **El diff de F2 se reescribe contra los nombres REALES de `enrich_blocks`:** son `project_name` y `ticket_title` **sin guion bajo**, y **`ticket_type` no existe en ninguna forma**. El de v2, rotulado "Diff que de verdad compila", daba `NameError` en el camino caliente de los 3 runtimes. | **B5** |
| 10 | **`Ticket.type` no existe: es `work_item_type`** (`backend/models.py:55`), con `local_work_item_type` (`:61`) como fallback local. El `getattr(ticket,"type",None)` de v2 devolvía `None` **siempre, en silencio**, dejando ciega a `classify_ticket_kind`. | **B6** |
| 11 | **Las 4 flags pasan a prefijo `STACKY_`.** El meta-test anti-drift `tests/test_flags_env_read_meta.py:17-19` escanea **solo** `os.getenv("STACKY_...")`: una flag `HARNESS_LEARNING_*` se **auto-excluía del guard**. | **B-extra, verificado** |
| 12 | **F1.0 EJECUTADA, no prometida.** La calibración contra la DB viva (solo lectura, 201 filas con metadata sobre 217 ejecuciones) está en §3-bis con conteos reales. Los 4 `signal_kind` tienen extractor contra claves **observadas**; ninguno queda en `xfail`. | **[EJECUCIÓN ARQUITECTO]** |

---

## 0. Cómo leer este plan (regla de anclajes)

**Los `archivo:línea` caducan.** En este repo el ratio de supervivencia de un anclaje a ~2 meses es de **1 en 21**. Por eso **todo anclaje de este plan es por SÍMBOLO**: "la función `X` en `services/Y.py`". Los números de línea son orientativos y **medidos el 2026-08-01**; si no coinciden, manda el símbolo. Antes de editar, localizá el símbolo con `grep -n "def <simbolo>" <archivo>`.

**Tesis (innegociable):** los planes 27-32 construyeron un motor que piensa mejor, no se ahoga, cumple el encargo, está anclado a la realidad y deriva un contrato ejecutable antes de trabajar. Toda esa maquinaria emite, en cada run, **señales de altísimo valor**: qué criterio falló, qué precondición saltó, qué repair lo arregló, con qué modo de fallo terminó. **Esas señales mueren al terminar el run.** El run N+1 del mismo proyecto y tipo de ticket re-tropieza con el mismo fallo y re-paga el mismo repair. El operador, además, **no ve** qué falla recurrentemente: revisa cada `needs_review` aislado. Este plan cierra el séptimo lado: **cosechar** las señales que 29-32 ya producen, **agregarlas en patrones**, **persistirlas reusando la memoria colaborativa**, **reinyectarlas como pista barata** y **mostrarlas al operador**.

**"Aprendizaje" NO significa "autonomía" (regla 11, human-in-the-loop):** el sistema **observa, agrega y propone**; nunca decide ni aplica solo. Un patrón se inyecta como **pista podable de prioridad media** (nunca pisa criterios ni contrato), y todo insight es **lectura** + confirmar/descartar. Stacky no reabre tickets, no relanza runs, no transiciona estados. Cada fase trae su línea "Por qué NO viola regla 11".

**El descarte del operador es de POR VIDA (decisión (b)).** Si el operador marca un patrón como descartado, la cosecha **no lo resucita**: ni lo re-crea ni lo reactiva, aunque la señal vuelva a aparecer 100 veces. Es la garantía que convierte "confirmar/descartar" de un gesto cosmético en una decisión con consecuencias.

**Calidad nunca se sacrifica:** todos los mecanismos son aditivos y degradables. La cosecha es **pasiva y post-run**. La reinyección es podable: bajo presión de budget se descarta **antes** que criterios/contrato. Si un patrón es ruidoso, su `confidence` cae y deja de inyectarse; el operador lo descarta de por vida.

---

## 1. Relación con los planes previos (qué reusa, qué NO re-implementa)

Todos los anclajes de esta sección fueron **verificados el 2026-08-01**.

- **REUSA, no re-implementa:**
  - **`services/memory_store.py`** como sustrato de persistencia: `upsert_by_topic_key`, `list_observations`, `set_status`, `get`, modelo `StackyMemoryObservation`. Un patrón es **una observación más** con `scope` reservado; **cero tabla nueva**.
  - **Chokepoint post-run: `on_execution_end` + `register_post_hook` en `services/ticket_status.py`.** (v1 usaba `finalize_run`; ver §F1/C1.)
  - **`services/context_enrichment.py`**: `enrich_blocks`, el mapa `_BLOCK_PRIORITY`, la función `_block_priority` y el umbral `_HIGH_PRIORITY_THRESHOLD`. La reinyección es **un dict más** en la lista de bloques.
  - **Redacción de secretos: `redact_secrets` en `services/pr_review_sanitize.py`.** (v1 citaba un detector inexistente.)
  - **Salud / KPIs**: `compute_health` en `services/harness_health.py` + `api/diag.py`.
  - **Flags por UI**: `FlagSpec` y `FLAG_REGISTRY` en `services/harness_flags.py` + `api/harness_flags.py` -> `HarnessFlagsPanel`.
- **Frontera con 29:** el 29 **deriva** criterios por LLM en cada run. El 35 **no deriva nada**: cosecha **cuáles fallaron**. Disjuntos.
- **Frontera con 31/32:** 31 ejecuta verificadores, 32 deriva el contrato. El 35 cosecha el **resultado**. Disjuntos.
- **Frontera con 27:** el 27 decide qué **documento** entra por similitud. El 35 inyecta **patrones de fallo/remedio** del arnés. Coexisten con prioridades separadas.
- **Frontera con 26 / memoria colaborativa:** esos capturan **conocimiento de dominio**; el 35 captura **conocimiento del proceso de verificación**, con `scope` reservado.
- **SUBSUME / REEMPLAZA:** nada.

---

## 2. Qué NO es este plan (anti-scope explícito)

1. **No es autonomía.** No relanza runs, no reabre tickets, no transiciona estados, no aplica parches solo.
2. **No agrega RBAC ni multi-usuario.** Mono-operador sin auth real: `current_user` es un header sin validar y **403 significa flag apagada, no permiso**. Los patrones son por-proyecto, nunca por-usuario.
3. **No crea un store nuevo.** `memory_store` con `scope="harness_pattern"`. Cero tabla, cero migración, cero dep nueva, cero FTS5.
4. **No modifica `memory_store`.** El guard del descarte de por vida (decisión (b)) vive en `persist_pattern`, **no** en el store: `upsert_by_topic_key` es genérico y lo consumen otros servicios.
5. **No deriva criterios ni contratos.** Solo **lee** lo que 29-32 ya escribieron.
6. **No cambia QUÉ/CUÁNDO se publica al tracker.** La cosecha es solo-lectura sobre una ejecución terminada.
7. **No re-implementa telemetría, gate, repair ni ranking de contexto.**
8. **No degrada el run cuando un patrón es ruidoso.** La pista es podable; en el peor caso se descarta.
9. **No mantiene contadores a mano que el store ya lleva.** `occurrences` sale de `revision_count`.

---

## 3. Diagnóstico: dónde mueren hoy las señales (evidencia verificada 2026-08-01)

| # | Debilidad | Evidencia (por símbolo) | Impacto |
|---|---|---|---|
| **D1** | Las señales de criterios/precondición/repair **no se agregan más allá del run**. Quedan en `metadata` de la ejecución y **nadie las lee después**. | `metadata_dict` en `models.py`; `persist` en `harness/telemetry.py` | Cada run del mismo patrón re-tropieza y re-paga el mismo repair. |
| **D2** | **No hay reinyección de "lo que suele fallar".** `enrich_blocks` inyecta repo/memoria/criterios, pero **ningún bloque** trae el historial de fallos del propio arnés. | `enrich_blocks`, `_BLOCK_PRIORITY` | El agente re-comete errores que el arnés ya vio y arregló. |
| **D3** | **El operador ve incidentes sueltos, no patrones.** `compute_health` agrega costo/fiabilidad por runtime y proyecto, pero no "este fallo apareció N veces". | `compute_health` en `services/harness_health.py` | No puede priorizar la causa raíz que más cuesta. |
| **D4** | **Los repairs exitosos no dejan rastro reutilizable.** `criteria_repair` deja `recovered` en la metadata del run y ahí muere. | `metadata["criteria_repair"]` | Se re-descubre el mismo remedio gastando un pase correctivo evitable. |

**Lectura central:** el sustrato ya existe y es sólido. El valor del 35 no es construir un store: es **(a) cosechar**, **(b) agregar con confianza**, **(c) reinyectar barato** y **(d) mostrar al operador**.

---

## 3-bis. F1.0 — CALIBRACIÓN EJECUTADA contra la metadata REAL (no prometida)

> **Esta sección no es una promesa de calibrar: es el resultado de haberla corrido.** Se ejecutó el 2026-08-01 contra `backend/data/stacky_agents.db` abierta en modo **solo lectura** (`sqlite3.connect("file:...?mode=ro", uri=True)`), sin importar la app, sin escribir una sola página. **217 ejecuciones totales, 201 con `metadata_json` no vacío.**

**Regla dura que esto hace cumplible:** está **prohibido** escribir en un extractor un nombre de clave de metadata que no aparezca en esta tabla. Un extractor contra una clave inexistente devuelve 0 patrones **en silencio** — el peor falso verde posible, porque todos los tests con mocks pasarían igual.

### Claves-señal OBSERVADAS (conteo sobre 201 filas)

| Clave top-level | Tipo | Filas | Shape real medido | `signal_kind` que alimenta |
|---|---|---|---|---|
| `failure_kind` | `str` | **71** | Valores distintos observados: `"crash"` (57), `"contract_failed"` (14) | `run_failure` |
| `criteria_repair` | `dict` | 6 | `{"attempted": bool, "unmet_before": [str,...], "recovered": bool\|null}` | `criterion_fail` (uno por ítem) + `repair_success` |
| `precondition_failure` | `dict` | 23 | `{"check": str, "detail": str}` — ej. `check="ado_pat_missing"` | `contract_fail` |
| `validation_playbook` | `dict` | 21 | `{"status": str, "steps": [], "sources": [], "confidence": float, "degraded_reason": str}` — ej. `status="degraded"`, `degraded_reason="no_grounding"` | `verifier_fail` |
| `autocorrect` | `dict` | 69 | `{"attempts": int, "max_retries": int, "last_action": str, "last_errors": []}` — `last_action` ∈ {`"ok"`, `"no_artifacts"`, ...} | `repair_success` (si `attempts>0` y `last_action=="ok"`) |
| `contract_score` | `int` | 23 | escalar 0-100 (valores vistos: 100, 71, 54) | contexto de `contract_fail` |
| `harness_telemetry` | `dict` | 61 | `{runtime, session_id, num_turns, total_cost_usd, input_tokens, output_tokens, cache_read_tokens, cost_estimated}` | **NINGUNO** |

### Dos hallazgos que cambian el plan

1. **`harness_telemetry` NO sirve para cosechar.** La v2 lo declaraba "el sustrato que F1 lee" (§1). **Es falso:** `RunTelemetry.to_dict()` (`harness/telemetry.py:40-50`) emite **solo** tokens, costo, turnos y `session_id`. **Cero señales de verificación.** Un extractor apuntado ahí habría devuelto 0 patrones para siempre, con toda la suite en verde. Las señales viven en claves **hermanas** de `metadata`, no adentro de `harness_telemetry`.
2. **Los 4 `signal_kind` tienen extractor real; ninguno queda `xfail`.** La v2 preveía la posibilidad de declarar un `signal_kind` sin extractor. No hace falta: las 4 familias existen en datos reales.

### Fixture congelado

`backend/tests/fixtures/harness_metadata_sample.json` — muestras reales de las 5 claves-señal, **con `redact_secrets` aplicado** y sin valores de negocio identificables. Es la fuente de verdad de los tests de extracción: si el shape del productor cambia, el test rompe.

---

## 4. Objetivos medibles y KPIs

| KPI | Definición | Baseline | Objetivo |
|---|---|---|---|
| **K1 — Tasa de repair repetido** | % de runs cuyo fallo ya apareció ≥1 vez en el mismo proyecto+tipo de ticket en 30 días | n/d | medible y decreciente |
| **K2 — Cobertura de patrones** | nº de patrones con `confidence` ≥ umbral, por proyecto | 0 | creciente y reportado |
| **K3 — Δ reintentos por run** | reintentos de repair con inyección ON vs OFF sobre runs del mismo patrón | n/d | decreciente |
| **K4 — Δ tokens de re-derivación** | tokens gastados re-derivando lo que un patrón ya sabía | n/d | decreciente |
| **K5 — Insight accionable** | nº de patrones que el operador confirma/descarta | 0 | ratio sano |

Se exponen en la **DiagnosticsPage existente** (`frontend/src/pages/DiagnosticsPage.tsx`) vía `harness_health`/`api/diag.py`. Sin UI de métricas nueva.

---

## Principios y guardarraíles (vinculantes en todas las fases)

1. **3 runtimes con paridad — verificado, no asumido.** Un seam solo se declara "común a los 3" **después** de contar sus llamadores de producción. Medición 2026-08-01:
   - `finalize_run`: **1 de 3** (solo `services/codex_cli_runner.py`). **NO es un seam de paridad.**
   - `enrich_blocks`: **3 de 3** (`agent_runner.py`, `services/claude_code_cli_runner.py`, `services/codex_cli_runner.py`). **SÍ lo es.**
   - `on_execution_end`: transversal a los 3 -> se usa vía **`register_post_hook`** (punto único de registro, con **7 registros de producción** vigentes).
2. **Cero trabajo extra al operador:** invisible o configurable desde la UI. Sin pasos manuales nuevos.
3. **Human-in-the-loop innegociable:** observar/agregar/proponer, nunca decidir/aplicar. Regla 11. **Y el descarte del operador es definitivo** (decisión (b)).
4. **Mono-operador sin auth real:** nada de RBAC.
5. **No degradar performance/seguridad/estabilidad/DX.** Cero deps, cero FTS5, cero tabla nueva.
6. **Flag nuevo -> `config.py` + `FLAG_REGISTRY` + `_CATEGORY_KEYS` en la MISMA fase que lo introduce.** Registrar una flag son **seis lugares**, no uno:
   1. `backend/config.py` (el default **efectivo**),
   2. `FLAG_REGISTRY` en `services/harness_flags.py`,
   3. **`_CATEGORY_KEYS`** en `services/harness_flags.py` (si falta, `test_every_registry_flag_is_categorized` rompe CI a propósito — Plan 63),
   4. **`_CURATED_DEFAULTS_ON` en `backend/tests/test_harness_flags.py`** (ojo: vive en `tests/`, **no** en `services/harness_flags.py`, y `test_default_known_only_for_curated` compara por **IGUALDAD** de conjuntos),
   5. `backend/.env.example`,
   6. el test de registro en `backend/tests/test_harness_flags.py`.
   **Ojo:** una flag `env_only=True` **no** obtiene default por estar en el registry; si no está en `config.py`, un consumidor con `getattr(config, "X", False)` se lleva el default del `getattr` y la flag queda **inerte aunque registrada**.
7. **Toda flag nueva lleva prefijo `STACKY_`.** No es cosmético: el meta-test anti-drift `tests/test_flags_env_read_meta.py` compila `os\.(getenv|environ\.get)\(\s*['"](STACKY_[A-Z0-9_]+)['"]\s*,` — una flag sin ese prefijo **se auto-excluye del guard** que detecta lecturas de env con default divergente. `HARNESS_LEARNING_*` (v2) era invisible para el guard; `STACKY_HARNESS_LEARNING_*` no lo es.
8. **Default de flag nuevo = ON**, salvo justificación escrita por una de dos categorías: **(A)** quema tokens **en reposo** (loop/daemon/barrido/polling que llama a un modelo sin que el operador pida nada); **(B)** escribe en un sistema **real del operador**, destruye datos, o le saca la decisión. *"Retro-compat byte-idéntica"*, *"default seguro"* y *"para no cambiar el comportamiento actual"* **NO son justificaciones válidas** (ver §4-bis).
9. **Reusar la categoría de flags existente.** Un `group=` nuevo sin su entrada en `_CATEGORY_KEYS` deja el CI rojo a propósito. Se usa **`contexto_memoria`**, que ya existe.
10. **Suite contaminada -> validar POR ARCHIVO** con el intérprete que **anda**. `pytest tests` completo **no es un veredicto**. `pytest -k` sin match da **exit 0** -> todo criterio exige el **conteo `N passed`**.
11. **Costo por run acotado — REESCRITO por la decisión (a).** El camino caliente de `enrich_blocks` ejecuta **exactamente una query** (`list_observations`, ya acotada por `project+scope+status` y con `LIMIT`) y filtra por confianza **en Python** sobre ese conjunto ya acotado. **Prohibido** hacer N queries, prohibido iterar sin `limit`, y prohibido armar SQL propio duplicando el motor de acceso del store. El techo por run es: *1 query + a lo sumo `_PATTERN_SCAN_LIMIT` deserializaciones*.

> ### Comando base de tests
> `backend/.venv` es **Python 3.13.5** y está roto. El que **anda** es `backend/venv` (**Python 3.11.9**).
> ```powershell
> cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
> & "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/venv/Scripts/python.exe" -m pytest "tests/<ARCHIVO>" -q
> ```
> La ruta contiene **espacios**: siempre entre comillas. **Nunca** correr la suite completa.

---

## 4-bis. Decisión de defaults de flags (justificación escrita)

| Flag | Tipo | **Default v3** | Justificación |
|---|---|---|---|
| `STACKY_HARNESS_LEARNING_HARVEST_ENABLED` | bool | **ON** | **No es (A):** no hay loop ni daemon; corre **una vez, post-run, de una ejecución que el operador ya pidió**, y no llama a ningún modelo (extracción determinista stdlib). **No es (B):** escribe en la **memoria interna de Stacky** (`memory_store`), no en ADO/GitLab ni en ningún sistema del operador, y no le saca ninguna decisión. |
| `STACKY_HARNESS_LEARNING_INJECT_ENABLED` | bool | **ON** | **No es (A):** no prefetchea ni consulta un modelo en reposo; solo agrega texto al prompt de un run **que el operador ya pidió**. **No es (B):** no escribe nada en ningún sistema; el bloque es podable y de prioridad media. |
| `STACKY_HARNESS_LEARNING_INJECT_MAX` | int | **5** | Numérica: no es ON/OFF. Techo de pistas por run. |
| `STACKY_HARNESS_LEARNING_INJECT_MIN_CONF` | float | **0.5** | Numérica. Confianza mínima para inyectar. |

**Consecuencia obligatoria de default ON:** las **2 booleanas** se declaran con `default=True` en su `FlagSpec` **y** deben agregarse a **`_CURATED_DEFAULTS_ON` en `backend/tests/test_harness_flags.py`**; sin eso, `test_default_known_only_for_curated` pasa de verde a rojo (compara por igualdad de conjuntos). Las **2 numéricas NO** se agregan a ese set y **NO** declaran `default=` en la `FlagSpec`: el helper `default_is_known` marca conocida a **toda** spec con `default is not None`, así que declarar `default=5` en la int la metería en `known_keys` y rompería la igualdad. El default **efectivo** de las 4 lo fija `backend/config.py`.

> **Riesgo asumido y su mitigación:** con `INJECT_ENABLED=ON` desde el día 1, un patrón espurio podría inyectarse. Mitigación estructural: se exige `confidence ≥ 0.5`, y un patrón visto **una sola vez** queda en `0.2` -> **no se inyecta hasta acumular ≥3 ocurrencias**. En la práctica el sistema arranca silencioso y se enciende solo cuando hay evidencia. El operador puede apagarlo desde la UI en cualquier momento, y descartar un patrón lo mata **para siempre** (decisión (b)).

---

## FASE F0 — Sustrato: tipo de patrón + persistencia en la memoria existente

**Objetivo (1 frase):** definir `HarnessPattern` y su persistencia reutilizando `memory_store`, con `scope` reservado, redacción de secretos y **el guard del descarte de por vida**.

**Archivos:**
- CREAR `backend/services/harness_learning.py`.
- (Sin cambios en `config.py`/`harness_flags.py`: F0 no introduce flags.)

**Contratos reales que F0 debe respetar (verificados 2026-08-01):**

```python
# services/memory_store.py — firmas REALES, keyword-only. `type` es OBLIGATORIO.
upsert_by_topic_key(*, project: str, type: str, title: str, content: str,
                    scope: str = "project", topic_key: str, status: str = "active",
                    confidence: float | None = None, source_kind=None,
                    source_execution_id=None, source_ticket_id=None, source_ado_id=None,
                    source_agent_type=None, author_email=None, author_role=None,
                    tags=None, expires_at=None, review_after=None) -> str
# docstring: "Upsert por `topic_key`. Incrementa `revision_count` si ya existía."

list_observations(*, project=None, status=None, scope=None, type=None, limit=200) -> list[dict]
#   NO acepta filtro de confianza.  Ordena por updated_at DESC y RECIÉN AHÍ aplica .limit()
set_status(memory_id: str, status: str) -> bool
INJECT_SCOPES  = ("project", "team", "global")       # ALLOWLIST de inyección
ALL_STATUSES   = ("draft","active","needs_review","superseded","rejected","quarantined","deleted")
```

**Cuatro decisiones de sustrato:**

1. **`type="pattern"`** — es obligatorio y v1 lo omitía (`TypeError`). Está en `INJECTABLE_TYPES` y **no** en `RESERVED_TYPES`.
2. **`scope="harness_pattern"`** — 15 chars, entra en la columna `String(20)`. No se valida contra enum. Y como `INJECT_SCOPES` es **allowlist** `("project","team","global")`, un patrón **jamás** entra a la inyección de dominio (test T6).
3. **`occurrences` NO se serializa**: se **deriva de `revision_count`** (el store lo incrementa solo, de forma atómica; llevarlo a mano exige un read-modify-write con condición de carrera).
4. **`confidence` se pasa a la columna nativa** al persistir, pero **el valor que manda es el recalculado on-read** (F3). La columna es informativa para la UI de F4; el filtro nunca la lee (decisión (a)).

### Decisión (b) — el guard del descarte de por vida vive ACÁ

`upsert_by_topic_key` **pisa `status` y `confidence` incondicionalmente** (`memory_store.py:564-569`); su único guard es no degradar `active` -> `draft`. Es decir: **sin un guard propio, una re-cosecha resucita un patrón `rejected`**, y el "descarte de por vida" que este plan promete en §0, §6 y F3 sería una mentira de manual.

El guard **no** va en `memory_store`: `upsert_by_topic_key` es genérico y lo consumen otros servicios; cambiar su semántica para un solo caller rompería el contrato compartido. Va en `persist_pattern`, que es el único escritor de patrones.

**Símbolos a crear en `services/harness_learning.py`:**

```python
HARNESS_PATTERN_SCOPE = "harness_pattern"   # scope reservado; fuera de INJECT_SCOPES por construcción
HARNESS_PATTERN_TYPE  = "pattern"           # type obligatorio del store
PATTERN_STATUS_ACTIVE    = "active"         # de ALL_STATUSES
PATTERN_STATUS_DISMISSED = "rejected"       # "dismissed" NO existe en ALL_STATUSES
_PATTERN_SCAN_LIMIT = 500                   # ventana de escaneo; ver desvío D-1 en §13

@dataclass(frozen=True)
class HarnessPattern:
    project: str
    agent_type: str      # "functional" | "technical" | "developer" | "qa" | "unknown"
    ticket_kind: str     # "bug" | "feature" | "task" | "unknown"
    signal_kind: str     # "criterion_fail" | "verifier_fail" | "contract_fail"
                         # | "repair_success" | "run_failure"
    signal_key: str      # id estable del fallo (normalizado + hash corto)
    remedy_hint: str     # texto corto redactado (puede ser "")
    occurrences: int     # DERIVADO de revision_count al leer; no se escribe a mano
    confidence: float    # recalculado on-read (F3)
    last_seen: str       # ISO

def normalize_signal_key(raw: str) -> str: ...     # estabiliza y acota (ver abajo)
def pattern_topic_key(p: HarnessPattern) -> str: ...
def is_dismissed_topic(project: str, topic_key: str) -> bool: ...   # guard de (b)
def persist_pattern(p: HarnessPattern) -> str: ...
def list_patterns(project: str, *, agent_type=None, ticket_kind=None,
                  min_confidence: float = 0.0, limit: int = 50) -> list[HarnessPattern]: ...
```

**`normalize_signal_key` — por qué existe:** los criterios reales que trae `criteria_repair.unmet_before` son textos de **hasta ~250 caracteres** (medido en §3-bis: `"CA-01: Cliente con SCOBLIGACION cargado abre pestaña Scoring columna Obligación aparece inmediatamente después de..."`). El `topic_key` va a una columna `String(200)` y se compone de 5 campos. Sin normalizar, el key sería inestable (espacios, mayúsculas) y desbordaría. Regla: minúsculas, colapsar whitespace, truncar a 60 chars, y **anexar los primeros 8 hex de un `sha1` del texto normalizado completo** para desambiguar dos criterios con el mismo prefijo. Determinista, sin deps.

**Pseudocódigo de `persist_pattern` (compila contra la firma real):**

```python
from services.pr_review_sanitize import redact_secrets   # símbolo REAL

def persist_pattern(p: HarnessPattern) -> str:
    if not (p.project or "").strip():
        return ""                                   # caso borde: project vacío -> no persiste
    safe = replace(p,
                   remedy_hint=redact_secrets(p.remedy_hint or ""),
                   signal_key=redact_secrets(p.signal_key or ""))
    topic = pattern_topic_key(safe)
    # ── Decisión (b): descarte de POR VIDA ────────────────────────────────
    # upsert_by_topic_key pisa `status` sin condición: sin este guard, una
    # re-cosecha resucitaría un patrón que el operador ya descartó.
    if is_dismissed_topic(safe.project, topic):
        return ""
    payload = json.dumps({                          # SIN occurrences ni confidence
        "agent_type": safe.agent_type, "ticket_kind": safe.ticket_kind,
        "signal_kind": safe.signal_kind, "signal_key": safe.signal_key,
        "remedy_hint": safe.remedy_hint, "last_seen": safe.last_seen,
    }, sort_keys=True, ensure_ascii=False)
    return memory_store.upsert_by_topic_key(
        project=safe.project,
        type=HARNESS_PATTERN_TYPE,
        title=safe.signal_key[:120] or "(sin clave)",
        content=payload,
        scope=HARNESS_PATTERN_SCOPE,
        topic_key=topic,
        status=PATTERN_STATUS_ACTIVE,
        confidence=safe.confidence,                 # columna nativa (informativa)
        source_agent_type=safe.agent_type,
    )
```

**`is_dismissed_topic` — implementación (sin tocar `memory_store`):**
```python
def is_dismissed_topic(project: str, topic_key: str) -> bool:
    rows = memory_store.list_observations(
        project=project, scope=HARNESS_PATTERN_SCOPE,
        status=PATTERN_STATUS_DISMISSED, limit=_PATTERN_SCAN_LIMIT,
    )
    return any((r.get("topic_key") or "") == topic_key for r in rows)
```
`to_dict()` expone `topic_key`, así que la comparación es exacta y no requiere schema nuevo.

> **Nota sobre `redact_secrets`:** devuelve el texto con `_MASK = "***REDACTED***"` sustituido, y además enmascara **emails** (PII). **No existe** ningún `contains_secret(...)` en el repo. Se llama **incondicionalmente** (es idempotente sobre texto limpio), sin predicado previo.

**`list_patterns` — filtrado en PYTHON (decisión (a)):** llama `list_observations(project=..., scope=HARNESS_PATTERN_SCOPE, status="active", limit=_PATTERN_SCAN_LIMIT)` — **una sola query**, ya acotada por el store — y **en memoria** recalcula `confidence` con `compute_confidence(revision_count, days_since(updated_at))` (F3), filtra `>= min_confidence`, filtra por `agent_type`/`ticket_kind` si vienen, ordena por confianza descendente y recorta a `limit`. `occurrences` sale de `revision_count`.

**Tests PRIMERO** — `backend/tests/test_harness_learning.py` (**archivo nuevo**; registrar en los 2 ratchets, §12). **Numerados por ARCHIVO: F0 aporta T1..T8.**

| # | Test | Qué fija |
|---|---|---|
| T1 | `test_pattern_topic_key_is_stable` | misma tupla -> misma key; distinto `signal_key` -> distinta |
| T2 | `test_persist_is_idempotent_by_topic_key` | persistir 2 veces **no** crea 2 observaciones |
| T3 | `test_persist_increments_revision_count` | el 2º persist deja `revision_count == 2` (prueba que `occurrences` es derivable) |
| T4 | `test_persist_redacts_secrets` | un `remedy_hint` con un token tipo PAT se guarda con `"***REDACTED***"` y **sin** el valor original |
| T5 | `test_persist_passes_required_type` | la observación persistida tiene `type == "pattern"` (gate anti-`TypeError`) |
| T6 | `test_harness_pattern_scope_is_never_injected` | se persiste un patrón y `get_context_for_run(...)` con sus defaults **no** lo devuelve. Fija como contrato lo que hoy es solo un default |
| T7 | `test_normalize_signal_key_bounds_topic_key` | un criterio de 250 chars produce un `topic_key` ≤ 200 y estable entre corridas |
| T8 | `test_empty_project_is_not_persisted` | `project=""` -> `""` y cero filas |

**Comando exacto:**
```powershell
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/venv/Scripts/python.exe" -m pytest "tests/test_harness_learning.py" -q
```

**Criterio de aceptación BINARIO:** la corrida imprime **`8 passed`** y `0 failed`. Cero cambios de schema en `memory_store`.

**Flag + default:** ninguna (estructura inerte).
**Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.
**Por qué NO viola regla 11:** define un tipo y una forma de guardar; no decide ni actúa.
**Salvaguarda de calidad:** redacción e idempotencia testeadas; T6 impide contaminar la memoria de dominio.

---

## FASE F1 — Cosecha pasiva post-run (harvest) en el chokepoint transversal

**Objetivo (1 frase):** al terminar **cualquier** ejecución en **cualquiera de los 3 runtimes**, leer la metadata ya persistida y guardar los fallos/remedios como patrones, sin alterar el run.

### C1 — Por qué el seam es `register_post_hook` y no `finalize_run` (medición, no opinión)

v1 afirmaba **cuatro veces** que `finalize_run` era "el seam post-run común a los 3 runtimes". **Es falso.** Llamadores de producción de `finalize_run` (excluyendo `tests/` y su propio módulo), medidos el 2026-08-01:

| Runtime | ¿Llama `finalize_run`? | ¿Llama `on_execution_end`? |
|---|---|---|
| Codex CLI (`services/codex_cli_runner.py`) | **SÍ** — único llamador real (`:1045`) | **SÍ** (`:363`) |
| Claude Code CLI (`services/claude_code_cli_runner.py`) | **NO** | **SÍ** (`:706`) |
| GitHub Copilot (`agent_runner.py`) | **NO** | **SÍ** (`:839`) |

Implementar F1 sobre `finalize_run` habría dejado la cosecha corriendo en **1 de 3 runtimes**, rompiendo un riel duro del producto, con un DoD que declaraba paridad -> **falso verde de manual**.

**Seam correcto:** `on_execution_end` en `services/ticket_status.py`, con registro por el punto único `register_post_hook` (`:377`), que ya tiene **7 registros de producción** (6 en `app.py:1033-1051`, 1 en `services/pipeline_orchestrator.py:234`).

**Tres ventajas estructurales del seam elegido:**
1. **Punto único de registro** (`register`), no 15 ediciones de call site.
2. **La garantía "nunca rompe el run" ya está construida:** `_run_post_hooks` (`:395-400`) envuelve cada hook en `try/except` y solo loguea (`"post_hook '%s' falló"`). No hay que confiar en que el autor recuerde el try/except.
3. **La metadata ya está persistida en la DB** cuando corre el hook (a diferencia de `PostRunResult.metadata_patch`, que es un patch **todavía sin fusionar**).

**Archivos a editar (F1):**
- EDITAR `backend/services/harness_learning.py` — agregar `classify_ticket_kind`, `_extract_signals`, `harvest_from_execution`, `register`.
- EDITAR `backend/app.py` — **cablear el hook** junto a los registros existentes.
- EDITAR `backend/config.py` — `STACKY_HARNESS_LEARNING_HARVEST_ENABLED` (default `true`).
- EDITAR `backend/services/harness_flags.py` — `FlagSpec` + `_CATEGORY_KEYS["contexto_memoria"]`.
- EDITAR `backend/tests/test_harness_flags.py` — `_CURATED_DEFAULTS_ON` + test de registro.
- EDITAR `backend/.env.example`.
- CREAR `backend/tests/fixtures/harness_metadata_sample.json` (§3-bis).

**Símbolos a crear (firma alineada al contrato real del hook):**

```python
def classify_ticket_kind(ticket_title: str, work_item_type: str | None) -> str:
    """Heurística barata stdlib -> "bug"|"feature"|"task"|"unknown". Sin LLM.
       OJO: el 2º parámetro es el WORK ITEM TYPE del tracker, no un `Ticket.type`
       (que NO existe en el modelo)."""

def _extract_signals(md: dict) -> list[tuple[str, str, str]]:
    """(signal_kind, signal_key, remedy_hint) por cada señal de la metadata.
       SOLO lee las claves OBSERVADAS en §3-bis. Nunca lanza."""

def harvest_from_execution(*, ticket_id: int, execution_id: int, final_status: str,
                           agent_type: str | None = None, error: str | None = None,
                           **kwargs) -> int:
    """Post-hook. Firma EXACTA que exige register_post_hook (docstring del registrador):
       fn(*, ticket_id, execution_id, final_status, agent_type, error, **kwargs)
    `**kwargs` es obligatorio: el chokepoint puede pasar claves adicionales.
    Devuelve nº de patrones persistidos. Best-effort."""

def register(register_post_hook) -> None:
    """Idioma de cableado del repo (mismo que services/epic_autopublish.py:355)."""
    register_post_hook(harvest_from_execution)
```

**Extractores — mapa clave OBSERVADA -> señal (ninguna clave inventada):**

| Clave de metadata | Condición | `signal_kind` | `signal_key` | `remedy_hint` |
|---|---|---|---|---|
| `criteria_repair.unmet_before` | lista no vacía | `criterion_fail` | cada ítem, normalizado | `""` |
| `criteria_repair` | `recovered is True` | `repair_success` | `"criteria_repair"` | `"el pase correctivo de criterios recuperó el run"` |
| `precondition_failure` | `check` no vacío | `contract_fail` | `check` | `detail` (redactado) |
| `validation_playbook` | `status != "ok"` | `verifier_fail` | `degraded_reason` o `status` | `""` |
| `autocorrect` | `attempts > 0` y `last_action == "ok"` | `repair_success` | `"autocorrect"` | `""` |
| `failure_kind` | str no vacío | `run_failure` | el valor (`crash` / `contract_failed`) | `""` |

**Pseudocódigo de `harvest_from_execution` (compila contra el contrato real):**

```python
def harvest_from_execution(*, ticket_id, execution_id, final_status,
                           agent_type=None, error=None, **kwargs) -> int:
    if not getattr(config.config, "STACKY_HARNESS_LEARNING_HARVEST_ENABLED", True):
        return 0
    with session_scope() as session:                       # lectura de la fila YA persistida
        row = session.get(AgentExecution, execution_id)
        if row is None:
            return 0
        md = row.metadata_dict or {}
        ticket = session.get(Ticket, ticket_id)
        # TODOS los escalares se capturan DENTRO de la sesión: afuera el objeto
        # queda detached y cualquier acceso da DetachedInstanceError.
        project      = getattr(ticket, "stacky_project_name", "") or ""
        ticket_title = getattr(ticket, "title", "") or ""
        # `Ticket.type` NO EXISTE. Los campos reales son `work_item_type`
        # (models.py:55) y `local_work_item_type` (models.py:61).
        wi_type      = (getattr(ticket, "work_item_type", None)
                        or getattr(ticket, "local_work_item_type", None))
    kind = classify_ticket_kind(ticket_title, wi_type)
    n = 0
    for signal_kind, signal_key, remedy in _extract_signals(md):
        if persist_pattern(HarnessPattern(
                project=project, agent_type=(agent_type or "unknown"), ticket_kind=kind,
                signal_kind=signal_kind, signal_key=signal_key, remedy_hint=remedy,
                occurrences=1, confidence=0.0,   # F3 recalcula al leer
                last_seen=datetime.utcnow().date().isoformat())):
            n += 1
    return n
```

**Cableado en `backend/app.py` (OBLIGATORIO — sin esto la fase no existe):** junto a los registros ya presentes (`epic_autopublish.register(...)` y hermanos, `app.py:1033-1051`):

```python
from services import harness_learning
harness_learning.register(ticket_status.register_post_hook)
```

**Casos borde:**
- Metadata sin señales -> 0 patrones, sin error.
- `repair_success` sin diagnóstico legible -> `remedy_hint=""` (patrón válido).
- Flag OFF -> `return 0` en la primera línea; ningún efecto.
- Ejecución inexistente / ticket borrado -> 0, sin excepción.
- **Patrón previamente descartado -> `persist_pattern` devuelve `""` y no cuenta** (decisión (b)).
- Excepción inesperada -> la absorbe `_run_post_hooks` y la loguea; **el run nunca se cae**.

**Tests PRIMERO** — agregar a `backend/tests/test_harness_learning.py`. **F1 aporta T9..T16.**

| # | Test | Qué fija |
|---|---|---|
| T9 | `test_harvest_extracts_criterion_fail` | usando el **fixture real** de §3-bis |
| T10 | `test_harvest_extracts_repair_success_with_hint` | `remedy_hint` no vacío |
| T11 | `test_harvest_is_noop_without_signals` | metadata `{}` -> 0, sin excepción |
| T12 | `test_harvest_never_raises` | metadata corrupta -> no propaga |
| T13 | `test_classify_ticket_kind_uses_work_item_type` | `work_item_type="Bug"` -> `"bug"`. *Gate de B6: con el `Ticket.type` inexistente de v2 este test falla* |
| T14 | `test_flag_off_does_not_harvest` | flag OFF -> 0 y cero escrituras |
| T15 | `test_harvest_signature_matches_post_hook_contract` | por `inspect.signature`: acepta exactamente `ticket_id, execution_id, final_status, agent_type, error` como keyword y tiene `**kwargs`. *Gate contra el defecto que mató a v1: firma imaginada* |
| T16 | `test_hook_is_registered_in_app` | parsea `backend/app.py` por **AST** y exige la llamada `harness_learning.register(...)`. *Gate anti-"construido y jamás cableado"* |

Y en `backend/tests/test_harness_flags.py` (**archivo ya registrado en ambos ratchets**):
- `test_harness_learning_harvest_flag_registered` — la key está en `FLAG_REGISTRY`, en `_CATEGORY_KEYS["contexto_memoria"]` y con `default=True`; y la key está en `_CURATED_DEFAULTS_ON`.

**Comando exacto:**
```powershell
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/venv/Scripts/python.exe" -m pytest "tests/test_harness_learning.py" -q
& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/venv/Scripts/python.exe" -m pytest "tests/test_harness_flags.py" -q
```

**Criterio de aceptación BINARIO:**
- `tests/test_harness_learning.py` imprime **`16 passed`**, `0 failed`.
- `tests/test_harness_flags.py` imprime **`57 passed`**, `0 failed`. **Criterio ABSOLUTO, no delta.** Baseline medido el 2026-08-01 **antes** de tocar el archivo: **`56 passed, 0 failed`**. La v2 afirmaba que este archivo tenía 4 rojos preexistentes y por eso pedía criterio delta: **es falso**, esos 4 fallos son de `test_harness_flags_help.py`, otro archivo, que este plan **no toca y no arregla**.

**Flag + default:** `STACKY_HARNESS_LEARNING_HARVEST_ENABLED` (bool, **ON** — §4-bis), en los 6 lugares del guardarraíl 6.

**Impacto por runtime (medido, no asumido):** los 3 runtimes llaman `on_execution_end` -> los tres disparan el hook. **Fallback:** si un runtime no escribió alguna señal, se extraen las que estén.

**Trabajo del operador:** ninguno.
**Por qué NO viola regla 11:** lee y guarda; no decide, no actúa sobre el ticket, no publica. **Y respeta el descarte del operador de por vida.**
**Salvaguarda de calidad:** best-effort por construcción; flag OFF -> `return 0` inmediato; el fixture de §3-bis impide extractores contra claves inventadas.

---

## FASE F3 — Confianza, decaimiento y supresión de ruido

> Va **antes** que F2: F2 no debe inyectar sin el filtro de confianza. El orden F0 -> F1 -> F3 -> F2 -> F4 se mantiene.

**Objetivo (1 frase):** calcular `confidence` por ocurrencias + recencia y dejar de inyectar patrones rancios o descartados por el operador.

**Archivos:** EDITAR `backend/services/harness_learning.py`.

**Símbolos:**
```python
def compute_confidence(occurrences: int, days_since_last_seen: int) -> float:
    """Determinista, sin LLM, sin deps.
       base  = min(1.0, occurrences / 5.0)
       decay = 0.5 ** (days_since_last_seen / 30.0)     # half-life 30 días
       return round(base * decay, 3)"""

def is_suppressed(pattern_status: str) -> bool:
    return pattern_status == PATTERN_STATUS_DISMISSED    # "rejected"
```

**Por qué no es `"dismissed"`:** `ALL_STATUSES` en `services/memory_store.py:66-74` es `("draft","active","needs_review","superseded","rejected","quarantined","deleted")`. **`"dismissed"` no existe.** `set_status` no valida (asigna el string tal cual), así que v1 habría "funcionado" mientras metía un estado fuera de taxonomía, invisible para todo consumidor que itere `ALL_STATUSES`. Se usa **`"rejected"`**, cuya semántica es exactamente "el operador lo descartó".

**Dónde se aplica (decisión (a)):** `compute_confidence` se llama **on-read**, dentro de `list_patterns`, sobre el conjunto ya traído por la única query. **No** se escribe de vuelta a la columna: el valor calculado es el que gobierna el filtro, y persistirlo agregaría una escritura al camino caliente sin ganar nada.

**Casos borde (con los números reales de la fórmula):**
- 1 ocurrencia hoy -> `0.2` < 0.5 -> **no se inyecta**.
- 3 ocurrencias hoy -> `0.6` ≥ 0.5 -> se inyecta.
- 6 ocurrencias hace 120 días -> `1.0 * 0.5**4 = 0.063` -> rancio, no se inyecta.
- Patrón `rejected` -> excluido siempre, **y nunca resucita** (decisión (b)).

**Tests PRIMERO** — agregar a `backend/tests/test_harness_learning.py`. **F3 aporta T17..T23.**

| # | Test | Qué fija |
|---|---|---|
| T17 | `test_confidence_grows_with_occurrences` | monotonía |
| T18 | `test_confidence_decays_with_age` | half-life |
| T19 | `test_single_occurrence_below_default_threshold` | valor exacto `0.2 < 0.5` |
| T20 | `test_three_occurrences_reach_threshold` | `0.6 >= 0.5`; fija el punto de encendido y sostiene el riesgo asumido de §4-bis |
| T21 | `test_dismissed_pattern_is_never_listed` | un patrón en `"rejected"` no aparece en `list_patterns` |
| T22 | `test_dismissed_status_is_in_all_statuses` | `PATTERN_STATUS_DISMISSED in memory_store.ALL_STATUSES` |
| T23 | **`test_dismissed_pattern_is_not_resurrected_by_reharvest`** | **Gate de la decisión (b), y el único test del plan que prueba el mecanismo entero de punta a punta.** Cosecha con `harvest_from_execution` (camino de producción), descarta con `set_status(..., "rejected")`, **vuelve a cosechar la MISMA ejecución**, y asserta que (1) la fila sigue en `"rejected"`, (2) `revision_count` **no** creció, y (3) `list_patterns` sigue sin devolverla. *Un test que fabrique la fila a mano no prueba nada de esto: el defecto vive en el camino, no en el dato.* |

**Comando exacto:** el de F0/F1 sobre `tests/test_harness_learning.py`.
**Criterio de aceptación BINARIO:** imprime **`23 passed`**, `0 failed`. *(8 de F0 + 8 de F1 + 7 de F3 = 23, contados **en este archivo**. El test de flags de F1 vive en `test_harness_flags.py` y no cuenta acá — el criterio "23 passed" de la v2 sumaba mal por contar los tests globalmente.)*

**Flag + default:** sin flag propio (gobernado por `STACKY_HARNESS_LEARNING_INJECT_MIN_CONF`).
**Impacto por runtime:** ninguno directo.
**Trabajo del operador:** ninguno (salvo el descarte opcional de F4).
**Por qué NO viola regla 11:** matemática determinista que **respeta y amplifica** el descarte del operador.
**Salvaguarda de calidad:** el ruido se autoextingue por decay. Mide K2.

---

## FASE F2 — Reinyección como pista barata (bloque podable de prioridad media)

**Objetivo (1 frase):** inyectar un bloque corto "fallos conocidos y su remedio" en runs del mismo patrón, podable antes que criterios y contrato.

### C3 — Por qué el pseudocódigo de v1 era ficción

v1 escribía `blocks.append(Block(name=..., priority=..., text=...))`. **`Block` no existe.** En el código real los bloques son **`dict`**:

```python
# services/context_enrichment.py — firma REAL
enrich_blocks(*, ticket_id: int | None, agent_type: str, raw_blocks: list[dict] | None,
              project_ctx: Any = None, log: LogFn | None = None) -> tuple[list[dict], dict | None]
# adentro:  blocks: list[dict] = list(raw_blocks or [])
# forma real de un bloque (ej. client-profile):
{"kind": "text", "id": "client-profile", "title": "...", "content": "..."}
```

La **prioridad no es un campo del bloque**: sale del mapa `_BLOCK_PRIORITY` vía `_block_priority(block)`, que hace `_BLOCK_PRIORITY.get(block.get("id") or "")`. Declarar `HARNESS_PATTERN_BLOCK_PRIORITY = 50` en `harness_learning.py` habría creado una **fuente de verdad duplicada que el motor ignora**.

### C3-bis — El falso verde estructural de la prioridad 50 (lo mejor del documento: NO tocar)

`_DEFAULT_PRIORITY = 50` en `services/context_enrichment.py:397`. Un bloque **no registrado** en `_BLOCK_PRIORITY` recibe **50 por accidente**. El test de v1 (`test_block_priority_is_below_criteria`, que comparaba una constante del propio módulo) **habría pasado en verde sin que nada estuviera cableado** — el falso verde perfecto: prueba una constante que el motor no consulta.

**Triple corrección, vigente:**
1. La prioridad se registra en **`_BLOCK_PRIORITY`**, la única fuente de verdad.
2. El valor es **45**, NO 50, precisamente para que sea **distinguible de `_DEFAULT_PRIORITY`**. Si el registro se olvida, `_block_priority` devuelve 50 y el test **falla**. Con 50 el test no puede distinguir "registrado" de "olvidado".
3. El test se corre **contra `_block_priority({"id": "harness-patterns"})`**, nunca contra una constante local.

### C16 — Mapa real de prioridades (verificado 2026-08-01)

Con `_HIGH_PRIORITY_THRESHOLD = 75`:

| Bloque | Prioridad | | Bloque | Prioridad |
|---|---|---|---|---|
| `operator-corrections` | 110 | | `operator_note` | 76 |
| `run-directive` | 105 | | `acceptance-contract` | 76 |
| `ado-epic-structured` | 100 | | **`acceptance-criteria`** | **74** |
| `client-profile` | 95 | | `filesystem-artifacts-status` | 70 |
| `ado-blocker` | 90 | | `glossary-auto` | 60 |
| `rejection-lessons` | 82 | | `few-shot-approved` | 55 |
| `stacky-memory` | 80 | | **`harness-patterns` (nuevo)** | **45** |
| `evolution-lessons` | 79 | | `ado-similar-tickets` | 40 |
| `modal_user_input` / `process-catalog` | 78 | | `ado-comments` | 30 |
| `process-discipline` | 77 | | `ado-attachments` | 25 |

**Dos correcciones de hecho respecto de v1:** (a) **no existe** ningún bloque llamado `grounding`; (b) **`acceptance-criteria` vale 74, por debajo del umbral 75** — o sea los criterios de aceptación **también son podables**. La afirmación correcta es: *`harness-patterns` (45) se poda antes que todos los bloques de contrato, criterios y grounding-equivalentes, y antes también que `few-shot-approved` (55); solo sobrevive por encima del contexto ADO barato (40/30/25).*

**Archivos a editar:**
- EDITAR `backend/services/context_enrichment.py` — `"harness-patterns": 45` en `_BLOCK_PRIORITY` **y** el append del bloque dentro de `enrich_blocks`.
- EDITAR `backend/services/harness_learning.py` — `build_pattern_hint_block`.
- EDITAR `backend/config.py` — las 3 keys.
- EDITAR `backend/services/harness_flags.py` — 3 `FlagSpec` + `_CATEGORY_KEYS`.
- EDITAR `backend/tests/test_harness_flags.py` — `_CURATED_DEFAULTS_ON` (solo la bool) + test de registro.
- EDITAR `backend/.env.example`.

**Símbolos:**
```python
# services/harness_learning.py
HARNESS_PATTERN_BLOCK_ID = "harness-patterns"   # clave "id" del dict (NO "name")

def build_pattern_hint_block(*, project: str, agent_type: str, ticket_title: str,
                             work_item_type: str | None, max_patterns: int = 5,
                             min_confidence: float = 0.5) -> dict | None:
    """Devuelve un BLOQUE dict listo para blocks.append(), o None si no hay patrones."""
```

### B5 — El diff de v2, rotulado "Diff que de verdad compila", NO compilaba

v2 escribía `_project_name`, `_ticket_title` y `_ticket_type`. **Los tres nombres son inexistentes** en el scope de `enrich_blocks`:
- el real es **`project_name`** (`services/context_enrichment.py:93`), **sin** guion bajo;
- el real es **`ticket_title`** (`:90`), **sin** guion bajo;
- **`ticket_type` no existe en ninguna forma.** Los escalares capturados dentro del `session_scope` son exactamente `ticket_ado_id`, `ticket_project`, `ticket_title`, `ticket_description` (`:80-91`).

Aplicado tal cual, el resultado es un **`NameError` en el camino caliente de los 3 runtimes**. Y como el tipo de work item **sí** hace falta para filtrar por `ticket_kind`, hay que **capturarlo dentro de la sesión** (afuera el objeto está detached -> `DetachedInstanceError`).

**Diff REAL de F2 — dos ediciones en `enrich_blocks`:**

```python
# (1) dentro del `with session_scope() as _sess:` que ya existe, junto a los otros escalares
        if ticket_obj is not None:
            ticket_ado_id = ticket_obj.ado_id
            ticket_project = ticket_obj.project
            ticket_title = ticket_obj.title
            ticket_description = ticket_obj.description
            # Plan 35 F2 — el tipo se captura DENTRO de la sesión: afuera el objeto
            # está detached. `Ticket.type` no existe; los campos reales son
            # work_item_type (models.py:55) y local_work_item_type (:61).
            ticket_work_item_type = ticket_obj.work_item_type or ticket_obj.local_work_item_type
```

```python
# (2) antes del dedup/budget (queda podable), usando los nombres REALES
    # --- Plan 35 F2: bloque de patrones aprendidos (hint podable, prioridad 45) ---
    if getattr(_cfg35, "STACKY_HARNESS_LEARNING_INJECT_ENABLED", True):
        try:
            from services import harness_learning as _hl
            _hint = _hl.build_pattern_hint_block(
                project=project_name or "", agent_type=agent_type,
                ticket_title=ticket_title or "",
                work_item_type=ticket_work_item_type,
                max_patterns=getattr(_cfg35, "STACKY_HARNESS_LEARNING_INJECT_MAX", 5),
                min_confidence=getattr(_cfg35, "STACKY_HARNESS_LEARNING_INJECT_MIN_CONF", 0.5),
            )
            if _hint:
                blocks.append(_hint)      # dict; la prioridad la resuelve _BLOCK_PRIORITY
        except Exception as _exc:         # nunca tumbar el camino caliente
            log("warn", f"harness-patterns no disponible (continuando): {_exc}")
```

Y en `_BLOCK_PRIORITY`:
```python
    "few-shot-approved": 55,
    "harness-patterns": 45,      # Plan 35 F2 — pista aprendida, podable antes que criterios
    "ado-similar-tickets": 40,
```

El bloque que devuelve `build_pattern_hint_block` respeta la forma real:
```python
{"kind": "text", "id": "harness-patterns",
 "title": "Fallos recurrentes en este tipo de ticket (pistas, no obligatorias)",
 "content": "- [criterion_fail] X suele fallar; remedio que funcionó: Y\n- ..."}
```

### C9 (REESCRITO por la decisión (a)) — Presupuesto de costo del camino caliente

`enrich_blocks` corre en **cada run de los 3 runtimes**. Reglas duras **vigentes**:
- `list_patterns` ejecuta **exactamente una llamada** a `list_observations`, ya acotada por `project + scope + status='active'` y con `LIMIT _PATTERN_SCAN_LIMIT`. **Prohibido** hacer N queries, prohibido llamar sin `limit`, prohibido armar SQL propio duplicando el motor de acceso del store.
- El filtro por confianza es **en Python** sobre ese conjunto ya acotado (decisión (a)). El techo por run es *1 query + ≤ `_PATTERN_SCAN_LIMIT` deserializaciones*, no *N filas del proyecto*.
- El bloque tiene **techo de caracteres** (`max_patterns` × ~200 chars).
- Sin patrones -> `None` -> **cero costo adicional**.

**Casos borde:** sin patrones -> `None`, no se agrega bloque; budget ajustado -> se poda antes que contrato/criterios; flag OFF -> `enrich_blocks` idéntico a hoy; excepción -> se loguea y el run sigue.

**Tests PRIMERO** — `backend/tests/test_harness_learning_inject.py` (**archivo nuevo**; registrar en los 2 ratchets). **Numerados por ARCHIVO: I1..I9.**

| # | Test | Qué fija |
|---|---|---|
| I1 | `test_hint_block_lists_top_patterns_by_confidence` | con 8 patrones inyecta los 5 de mayor confianza |
| I2 | `test_hint_block_filters_by_agent_and_ticket_kind` | segmentación |
| I3 | `test_no_patterns_returns_none` | `None`, no bloque vacío |
| I4 | **`test_block_priority_is_registered_in_the_engine`** | `_block_priority({"id":"harness-patterns"}) == 45` **y** `!= _DEFAULT_PRIORITY`. *Anti-falso-verde C3-bis* |
| I5 | **`test_block_priority_is_below_acceptance_criteria`** | `< _BLOCK_PRIORITY["acceptance-criteria"]` (45 < 74), consultando el **mapa del motor** |
| I6 | `test_block_shape_is_a_dict_with_id` | claves `kind/id/title/content`; **no** es un objeto `Block` |
| I7 | `test_flag_off_no_block` | flag OFF -> `enrich_blocks` no agrega `harness-patterns` |
| I8 | **`test_list_patterns_runs_one_query`** | contando llamadas a `list_observations`: `build_pattern_hint_block` hace **1**, y no escala con el nº de observaciones. *Gate de C9 reescrito* |
| I9 | **`test_enrich_blocks_calls_the_builder`** | por AST: `context_enrichment` **referencia** `build_pattern_hint_block`. *Gate anti-"construido y jamás cableado"* |

Y en `backend/tests/test_harness_flags.py` (ya registrado): `test_harness_learning_inject_flags_registered` — las 3 keys en `FLAG_REGISTRY` + `_CATEGORY_KEYS`, con tipos `bool`/`int`/`float`.

**Comando exacto:**
```powershell
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/venv/Scripts/python.exe" -m pytest "tests/test_harness_learning_inject.py" -q
```
**Criterio de aceptación BINARIO:** `tests/test_harness_learning_inject.py` imprime **`9 passed`**, `0 failed`; `tests/test_harness_flags.py` imprime **`58 passed`**, `0 failed` (57 tras F1 + 1). Criterio **absoluto**, no delta.

**Flag + default:** `STACKY_HARNESS_LEARNING_INJECT_ENABLED` (bool, **ON**); `STACKY_HARNESS_LEARNING_INJECT_MAX` (int, 5); `STACKY_HARNESS_LEARNING_INJECT_MIN_CONF` (float, 0.5).

**Impacto por runtime (medido):** `enrich_blocks` tiene **paridad real 3/3** — `agent_runner.py`, `services/claude_code_cli_runner.py`, `services/codex_cli_runner.py`. *Ironía de v1: la fase que vendía paridad garantizada (F1) era la que no la tenía, y esta, que la tiene de verdad, no la reclamaba.*

**Trabajo del operador:** ninguno.
**Por qué NO viola regla 11:** es una pista explícitamente "no obligatoria"; no fuerza conducta ni decide. El título del bloque lo dice literalmente.
**Salvaguarda de calidad:** podable y de prioridad 45; nunca desplaza contrato ni criterios. Mide K3/K4.

---

## FASE F4 — Visibilidad para el operador (lectura + confirmar/descartar)

**Objetivo (1 frase):** mostrar los patrones aprendidos en la DiagnosticsPage existente, solo lectura más confirmar/descartar.

**Archivos a editar:**
- EDITAR `backend/api/diag.py` — `GET /api/diag/harness-patterns?project=...`, `POST /api/diag/harness-patterns/<id>/dismiss`, `POST .../confirm`.
- EDITAR `backend/services/harness_health.py` — contadores `patterns_total`, `patterns_high_conf`. Solo lectura.
- EDITAR **`frontend/src/pages/DiagnosticsPage.tsx`** — tarjeta de patrones. Sin librería nueva.

> **Riel de arquitectura:** `services/` **nunca** importa de `api/`. `harness_learning` no puede importar `api/diag.py`; la dependencia va en un solo sentido (`api/diag.py` -> `services/harness_learning.py`).

**`FlagSpec` — referencia canónica de las 4 flags (registradas en F1/F2, NO en F4):**
```python
FlagSpec(key="STACKY_HARNESS_LEARNING_HARVEST_ENABLED", type="bool",
         label="Aprendizaje del arnés: cosechar (F1)",
         description="35.F1 — Post-run cosecha fallos/remedios como patrones. Pasivo, sin LLM.",
         group="contexto_memoria", default=True),
FlagSpec(key="STACKY_HARNESS_LEARNING_INJECT_ENABLED", type="bool",
         label="Aprendizaje del arnés: reinyectar (F2)",
         description="35.F2 — Inyecta pistas de fallos conocidos (podables, prioridad 45).",
         group="contexto_memoria", default=True),
FlagSpec(key="STACKY_HARNESS_LEARNING_INJECT_MAX", type="int",
         label="Máx. patrones por run",
         description="35.F2 — Cuántas pistas como máximo inyectar (default 5).",
         group="contexto_memoria"),          # SIN default=: rompería _CURATED_DEFAULTS_ON
FlagSpec(key="STACKY_HARNESS_LEARNING_INJECT_MIN_CONF", type="float",
         label="Confianza mínima de pista",
         description="35.F2/F3 — Solo inyecta patrones con confidence >= este valor (default 0.5).",
         group="contexto_memoria"),          # SIN default=: idem
```

### C6 — El grupo nuevo rompía un gate existente

v1 declaraba `group="harness_learning"`. En `services/harness_flags.py` hay un comentario literal: *"toda flag nueva debe agregarse también a `_CATEGORY_KEYS` (arriba) o el test `test_every_registry_flag_is_categorized` rompe CI a propósito (Plan 63)"*. **Decisión: reusar `contexto_memoria`**, que ya existe (`CategorySpec` en `harness_flags.py:58`) y cuya descripción — *"Qué información recibe el agente: presupuesto/dedup/rerank de contexto, memoria colaborativa, skills, few-shot, catálogo"* — encaja exactamente. **Trabajo concreto:** agregar las 4 keys a la tupla `_CATEGORY_KEYS["contexto_memoria"]` (`harness_flags.py:133`). **No** se crea un `CategorySpec` nuevo, con lo que no se toca el orden ni el tiering del panel.

**Pseudocódigo de los endpoints:**
```
GET /api/diag/harness-patterns?project=P
    patterns = harness_learning.list_patterns(P, min_confidence=0.0, limit=200)
    -> [ {..., "id": memory_id} ] ordenado por confidence desc
POST .../<id>/dismiss : memory_store.set_status(id, "rejected") -> 200 | 404
POST .../<id>/confirm : memory_store.set_status(id, "active")   -> 200 | 404
```

> **Nota sobre `confirm` y la decisión (b):** `confirm` reactiva un patrón que el operador descartó **por acción explícita del propio operador**. Eso NO contradice el descarte de por vida: lo que la decisión (b) prohíbe es que **la cosecha automática** lo resucite. El operador siempre manda sobre su propia decisión anterior.

**Casos borde:** proyecto sin patrones -> lista vacía, la tarjeta muestra "sin patrones aún"; id inexistente -> `set_status` devuelve `False` -> **404**; flags OFF -> la tarjeta se muestra vacía y los endpoints siguen siendo lectura/estado.

**Tests PRIMERO** — `backend/tests/test_harness_learning_api.py` (**archivo nuevo**; registrar en los 2 ratchets). **Numerados por ARCHIVO: A1..A5.**

| # | Test | Qué fija |
|---|---|---|
| A1 | `test_list_endpoint_returns_patterns_sorted` | orden por confidence desc |
| A2 | `test_dismiss_sets_status_rejected` | y luego `list_patterns` lo excluye |
| A3 | `test_confirm_reactivates_pattern` | el operador puede revertir su propio descarte |
| A4 | `test_dismiss_unknown_id_returns_404` | contrato de error |
| A5 | `test_endpoints_never_mutate_tickets_or_publish` | ningún publisher/tracker invocado. *Gate de regla 11* |

En `backend/tests/test_harness_flags.py`: `test_harness_learning_group_complete` — las **4** keys en `FLAG_REGISTRY` con tipos `bool/bool/int/float` **y** en `_CATEGORY_KEYS`.
En `backend/tests/test_harness_health.py` (**ya registrado en ambos ratchets**): `test_health_reports_pattern_counts`.

**Comando exacto:**
```powershell
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/venv/Scripts/python.exe" -m pytest "tests/test_harness_learning_api.py" -q
& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/venv/Scripts/python.exe" -m pytest "tests/test_harness_health.py" -q
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend" ; npx tsc --noEmit
```

**Criterio de aceptación BINARIO:** `test_harness_learning_api.py` imprime **`5 passed`**, `0 failed`; `test_harness_flags.py` imprime **`59 passed`**, `0 failed`; `tsc` termina con **0 errores** (vitest/RTL no están instalados de forma confiable: el gate real del frontend es `tsc`); `test_harness_health.py` con **+1** sobre su baseline, `0 failed`.

**Flag + default:** los 4 de arriba. La tarjeta es **siempre de lectura**; los botones cambian el estado de un patrón, nunca lanzan acciones sobre el tracker ni sobre runs.
**Impacto por runtime:** ninguno (observabilidad).
**Trabajo del operador:** ninguno obligatorio; confirmar/descartar es un click opcional.
**Por qué NO viola regla 11:** lectura + cambio de estado de una *pista*. Ninguna acción decide trabajo, publica ni transiciona work items. A5 lo fija como contrato.

---

## 5. Mecanismos transversales (resumen)

- **Cosecha pasiva (F1):** post-hook en `on_execution_end` (3/3 runtimes); lee metadata **ya persistida**; el chokepoint absorbe excepciones.
- **Persistencia reusada (F0):** `memory_store`, `scope="harness_pattern"`, `type="pattern"`, `occurrences` = `revision_count`. Cero tabla nueva. **Guard de descarte de por vida en `persist_pattern`.**
- **Reinyección podable (F2):** dict con `"id": "harness-patterns"`, prioridad **45** registrada en `_BLOCK_PRIORITY`; **una sola query acotada + filtro en Python**.
- **Confianza + decay (F3):** half-life 30 días; 1 ocurrencia = 0.2 (no inyecta), 3 = 0.6 (inyecta); `rejected` manda **para siempre**.
- **Visibilidad (F4):** DiagnosticsPage + `harness_health`; confirmar/descartar como única interacción.

---

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Una pista aprendida sesga al agente hacia un error pasado. | Hint "no obligatorio", prioridad 45 podable, nunca pisa contrato/criterios; decay lo apaga; **el operador lo descarta de por vida y la cosecha no lo resucita** (guard de (b), test T23). |
| La cosecha rompe o ralentiza el run. | Post-hook envuelto por `_run_post_hooks` (try/except del propio chokepoint); flag OFF -> `return 0` inmediato. |
| **La inyección degrada el camino caliente de los 3 runtimes.** | **Una** llamada a `list_observations` con `LIMIT`, filtro en Python sobre el conjunto acotado, techo de chars, `None` si no hay patrones. I8 lo fija. |
| **Un patrón bueno pero viejo queda fuera de la ventana de escaneo.** | **Desvío ACEPTADO y declarado (D-1, §13):** `_PATTERN_SCAN_LIMIT = 500` con orden por recencia. Mitigado por el propio decay: un patrón fuera de las 500 observaciones más recientes del proyecto ya tendría confianza baja. |
| Un patrón filtra un secreto. | `redact_secrets` incondicional antes de persistir; testeado contra el `_MASK`. |
| **Contamina la memoria de dominio.** | **Verificado que NO se materializa:** la inyección usa una **allowlist** `INJECT_SCOPES = ("project","team","global")`; `harness_pattern` queda fuera por construcción. Igual se fija con T6, porque hoy es un *default* y nada impide que un llamador amplíe `inject_scopes`. |
| **El módulo se construye, pasa tests y nunca se cablea.** | Hay precedentes recientes en este repo. Gate: T16 (F1) e I9 (F2) exigen el **consumidor de producción**. |
| Asimetría entre runtimes. | Seams verificados 3/3 (`on_execution_end`, `enrich_blocks`), no asumidos. |
| **Un extractor apunta a una clave que no existe y cosecha 0 en silencio.** | §3-bis **ejecutada** contra 201 filas reales; los 6 extractores citan claves con conteo medido. `harness_telemetry` fue **descartada** por esta vía (no trae señales de verificación). |
| Ruido de patrones de baja señal. | `min_confidence` 0.5 + `max` 5 + decay + descarte definitivo del operador. |

---

## 7. Fuera de scope

- **Aplicar un remedio automáticamente** (re-prompt forzado, parche auto): choca con regla 11.
- **Aprendizaje cross-proyecto:** los patrones son por-proyecto.
- **Clasificación de `ticket_kind` por LLM:** heurística stdlib; subir solo con evidencia.
- **Editor visual de patrones** más allá de lista + confirmar/descartar.
- **Borrado físico de patrones rancios:** decay + `rejected` los neutralizan sin borrar.
- **Modificar `memory_store`** para soportar filtro por confianza o por `topic_key`: la decisión (a)/(b) resuelve ambos casos del lado del consumidor.
- **Huella de regresión en `docs/sistema/error_fingerprints.json`:** no se agrega en esta iteración (no hay un modo de fallo estable que registrar hasta tener F1 corriendo en vivo).

---

## 8. Glosario

- **Arnés (harness):** capa que envuelve cada ejecución (gate, repair, verificación, telemetría) — `backend/harness/`.
- **Señal de verificación:** dato que el arnés produce al verificar un entregable. **Vive en claves de `metadata` de la ejecución** (`criteria_repair`, `precondition_failure`, `validation_playbook`, `autocorrect`, `failure_kind`), **no** dentro de `harness_telemetry`.
- **Patrón (HarnessPattern):** agregación de una señal recurrente en un contexto (proyecto + agente + tipo de ticket).
- **Harvest:** leer las señales de un run terminado y persistirlas. Pasivo.
- **Reinyección (hint):** pista corta de fallos conocidos en el próximo run. Podable.
- **`on_execution_end` / `register_post_hook`:** el chokepoint post-run **real** de los 3 runtimes, en `services/ticket_status.py`.
- **`finalize_run`:** decide el verdict post-run **solo en Codex CLI**. **No** es un seam de paridad (1 de 3).
- **`enrich_blocks`:** seam de armado de contexto, **sí** común a los 3 runners.
- **`harness_telemetry`:** clave de metadata con **tokens/costo/turnos únicamente**. Descartada como fuente de cosecha en §3-bis.
- **Descarte de por vida:** un patrón en `"rejected"` no vuelve a crearse ni a reactivarse **por la cosecha automática**. Solo el operador puede revertirlo con `confirm`.
- **Falso verde:** test que pasa sin que la funcionalidad exista (p. ej. comparar una constante local que el motor no consulta, o fabricar una fila a mano en vez de recorrer el camino de producción).

---

## 9. Orden de implementación y corte en 2 tandas

**Orden (dependencias):** F0 -> F1 -> F3 -> F2 -> F4. F3 precede a F2 porque F2 no debe inyectar sin filtro de confianza.

- **TANDA A — "cosechar en sombra" (F0 + F1 + F3).** Deja el sistema **acumulando patrones sin inyectar nada**. Riesgo cercano a cero: no toca el camino caliente ni el prompt. Cierra con `tests/test_harness_learning.py` en **`23 passed`**, `tests/test_harness_flags.py` en **`57 passed`**, y el hook cableado en `app.py`.
- **TANDA B — "inyectar y mostrar" (F2 + F4).** Cierra con `tests/test_harness_learning_inject.py` en **`9 passed`**, `tests/test_harness_learning_api.py` en **`5 passed`**, `tests/test_harness_flags.py` en **`59 passed`** y `tsc` en 0.

> **Gate de entrada a la Tanda B (CORREGIDO):** la v2 lo enunciaba como *"que existan patrones con `confidence >= 0.5`"*, y eso era **inverificable leyendo la columna**: F1 persiste `confidence=0.0` y el valor real se calcula on-read. El gate correcto, satisfacible, es: **`list_patterns(project, min_confidence=0.5)` devuelve ≥1 patrón** para algún proyecto — o sea se consulta por la **función**, que aplica `compute_confidence`, y nunca por la columna.
>
> **Rollout:** `HARVEST_ENABLED` nace ON y acumula. `INJECT_ENABLED` nace ON pero es **inerte hasta que un patrón llega a 3 ocurrencias** (F3), así que el encendido es gradual por construcción, no por configuración.

---

## 10. Definición de Hecho (DoD global)

- [ ] Cada flag está en **`config.py`** (default efectivo) **y** `FLAG_REGISTRY` **y** `_CATEGORY_KEYS` **y** `_CURATED_DEFAULTS_ON` (**solo** las 2 booleanas con `default=True`) **y** `.env.example` **y** su test — **en la misma fase que lo introduce**. Aparece en `HarnessFlagsPanel` sin tocar frontend.
- [ ] Las 4 flags llevan prefijo **`STACKY_`**, para no auto-excluirse del meta-test anti-drift.
- [ ] Los defaults siguen la regla vigente: **ON salvo justificación escrita por categoría (A) o (B)**. La justificación está en §4-bis, ítem por ítem.
- [ ] **Paridad verificada por conteo de llamadores, no declarada:** harvest vía `on_execution_end`/`register_post_hook` (**3/3**), reinyección vía `enrich_blocks` (**3/3**). Prohibido reintroducir la afirmación de que `finalize_run` es común a los 3 (es **1/3**).
- [ ] **Cableado real:** `app.py` registra el post-hook y `context_enrichment` referencia al builder — con test que lo verifica por AST. Ningún módulo queda construido-y-nunca-cableado.
- [ ] **Los extractores solo leen claves presentes en el fixture de §3-bis.** Ninguna clave inventada.
- [ ] **El descarte del operador es de por vida y está probado de punta a punta** (T23: cosecha -> descarta -> re-cosecha -> sigue `rejected`).
- [ ] Con los flags en **OFF**, `enrich_blocks` produce el mismo conjunto y orden de bloques que hoy, y el harvest no escribe nada.
- [ ] Cero tabla nueva, cero migración, cero dep npm/py, cero FTS5, **cero cambios en `memory_store.py`**.
- [ ] Secretos redactados con `redact_secrets` antes de persistir (test verde contra `"***REDACTED***"`).
- [ ] Harvest best-effort: nunca propaga excepción al run.
- [ ] Reinyección podable en **45**, registrada en `_BLOCK_PRIORITY`, verificada **contra `_block_priority`** y no contra una constante local.
- [ ] `scope="harness_pattern"` **no** entra a `get_context_for_run` (test verde).
- [ ] Costo del camino caliente acotado: **una** llamada a `list_observations` con `LIMIT` (test verde), filtro en Python.
- [ ] Toda interacción del operador es opcional y de lectura/estado; ninguna publica ni transiciona work items.
- [ ] Tests **por archivo** con `backend/venv` (py3.11.9), **numerados por archivo**. Cada criterio cita el **conteo `N passed`** y es **absoluto** (ningún archivo tocado por este plan tiene rojos preexistentes; medido).
- [ ] Los 3 archivos de test nuevos están registrados en **los DOS ratchets** (§12).
- [ ] `tsc --noEmit` en 0.

---

## 11. Decisiones cerradas por el operador (2026-08-01)

1. **`confidence` se filtra en Python.** No se toca `list_observations` ni se arma query propia. Se trae el conjunto acotado por `project+scope+status` y se filtra en memoria. Consecuencia obligatoria: el guardarraíl 11 y C9 se reescribieron; `compute_confidence` queda on-read en F3.
2. **El `rejected` se respeta con un guard en `persist_pattern`.** Descarte de por vida. El guard NO va en `memory_store`.
3. **Defaults ON de las dos booleanas** (§4-bis): aceptado; la inyección es inerte hasta 3 ocurrencias.
4. **Half-life de 30 días** (F3): se mantiene; revisable con datos de K2.

---

## 12. Gate anti-"construido y jamás cableado" + registro en ratchets

**El problema real que ataca:** en este repo hay precedentes recientes de módulos **construidos, testeados, en verde y jamás cableados**. El gate de "implementado" **no es "existe el símbolo"**, es **"existe un consumidor de producción"** (excluyendo `tests/`, el propio módulo y los baselines de ratchet). Con mocks, toda la suite de este plan puede quedar verde **sin que una sola línea corra en un run real**.

**Gate obligatorio (2 tests, T16 e I9):**
```python
# Parsea el archivo por AST y exige la llamada real, no un import.
def test_hook_is_registered_in_app():
    tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
    assert any(... "harness_learning" ... "register" ...), \
        "F1 no está cableada: app.py no registra el post-hook"
```
Se verifica **por AST y no por `grep`**, porque un `grep` cuenta también comentarios y strings; y se ancla **por símbolo** (`harness_learning` + `register`) y no por línea.

**Registro en los DOS ratchets:** un archivo de test nuevo debe declararse en `backend/scripts/run_harness_tests.ps1` **y** `backend/scripts/run_harness_tests.sh`, que tienen **sintaxis distinta** y **no admiten rutas con espacios** (estas no las tienen):

| Archivo nuevo | En `run_harness_tests.ps1` | En `run_harness_tests.sh` |
|---|---|---|
| `tests/test_harness_learning.py` | `  "tests/test_harness_learning.py",` | `  tests/test_harness_learning.py` |
| `tests/test_harness_learning_inject.py` | `  "tests/test_harness_learning_inject.py",` | `  tests/test_harness_learning_inject.py` |
| `tests/test_harness_learning_api.py` | `  "tests/test_harness_learning_api.py",` | `  tests/test_harness_learning_api.py` |

**Decisión de reuso:** los tests de **flags** van en `backend/tests/test_harness_flags.py` y los de **salud** en `backend/tests/test_harness_health.py`, **ambos ya registrados en los dos ratchets** (verificado 2026-08-01, `run_harness_tests.ps1:15-16` y `run_harness_tests.sh:22-23`). Así el plan usa **3 archivos nuevos** y ninguno de los tests de flags/health necesita trámite de ratchet.

---

## 13. Desvíos declarados

| ID | Desvío | Por qué se acepta | Cómo se mitiga |
|---|---|---|---|
| **D-1** | **El `limit` recorta por RECENCIA, no por confianza.** `list_observations` ordena por `updated_at DESC` y **después** aplica `.limit()`. Con el filtro de confianza en Python (decisión (a)), un patrón de alta confianza pero viejo puede quedar fuera de la ventana de `_PATTERN_SCAN_LIMIT = 500` y no inyectarse. | Es consecuencia directa de la decisión (a): filtrar en SQL habría exigido tocar `memory_store` o duplicar su motor de acceso, ambos vetados. El costo del desvío es un **falso negativo** (una pista buena que no se inyecta), no un falso positivo. | El decay de F3 hace que un patrón fuera de las 500 observaciones más recientes del proyecto ya tenga confianza baja: la ventana y el decay apuntan en la misma dirección. Si K2 muestra saturación de la ventana, el remedio es subir `_PATTERN_SCAN_LIMIT`, no cambiar el diseño. |
| **D-2** | **`is_dismissed_topic` hace una lectura extra** (una query a `list_observations` con `status="rejected"`) por cada patrón a persistir. | Está en el camino **post-run**, no en el caliente: corre una vez por ejecución terminada, nunca dentro del prompt. | El nº de señales por run es pequeño (≤ ~10 medido en §3-bis). Si creciera, la lectura se cachea por `(project, run)`. |
| **D-3** | **La columna `confidence` queda en `0.0`** en las filas cosechadas; el valor real se calcula on-read. | Escribirla exigiría un segundo `UPDATE` tras conocer el `revision_count` resultante del upsert. | La UI de F4 consume `list_patterns` (que recalcula), no la columna cruda. |

---

## 14. Trazabilidad de defectos corregidos

### v1 -> v2 (7 bloqueantes)

| ID | Defecto de v1 | Dónde se corrigió |
|---|---|---|
| C1 | `finalize_run` declarado seam de los 3 runtimes; es **1 de 3** | F1/C1, Principios 1, Glosario, DoD |
| C2 | El diff de F1 no compila; `metadata_patch` sin fusionar | F1 (pseudocódigo nuevo) |
| C3 | `Block(name=,priority=,text=)` no existe; prioridad 50 = falso verde | F2 (dict + `_BLOCK_PRIORITY` + 45) |
| C4 | Comandos apuntan a `backend/.venv` (py3.13.5, roto) | Comando base + las 5 fases |
| C5 | 4 flags en OFF contra la regla vigente | §4-bis |
| C6 | Grupo nuevo sin `_CATEGORY_KEYS` -> CI rojo | F4/C6 |
| C7 | `persist_pattern` omite el `type=` obligatorio -> `TypeError` | F0 |

### v2 -> v3 (6 bloqueantes + 1 verificado + 2 decisiones)

| ID | Severidad | Defecto de v2 | Dónde se corrige |
|---|---|---|---|
| **B1** | BLOQUEANTE | Criterio **"23 passed"** aritméticamente imposible: los tests estaban numerados **globalmente** y el 17 vive en otro archivo (8+8+6 = **22**) | F3 (numeración **por archivo**, 8+8+**7**=23) |
| **B2** | BLOQUEANTE | `list_observations` **no filtra por confianza** (firma real `memory_store.py:822-829`), pero el plan exigía filtrar en SQL | Decisión (a): §Guardarraíl 11, C9 reescrito, `list_patterns`, desvío **D-1** |
| **B3** | BLOQUEANTE | La cadena de `confidence` estaba rota punta a punta: F1 persistía `0.0`, F3 recalculaba sin escribir, F0 exigía `WHERE confidence >= 0.5` -> **nunca devolvía fila** | Decisión (a) + gate de Tanda B corregido en §9 (se consulta la **función**, no la columna) + desvío **D-3** |
| **B4** | BLOQUEANTE | `upsert_by_topic_key` **pisa `status` incondicionalmente** (`memory_store.py:564-569`): el "descarte de por vida" de §0/§6/F3 era falso | Decisión (b): `is_dismissed_topic` + guard en `persist_pattern` (F0) + gate **T23** |
| **B5** | BLOQUEANTE | El diff de F2, rotulado *"Diff que de verdad compila"*, usa `_project_name`/`_ticket_title`/`_ticket_type`: los dos primeros llevan **otro nombre** y el tercero **no existe** -> `NameError` en el camino caliente de los 3 runtimes | F2/B5 (diff real de 2 ediciones, captura del tipo **dentro** del `session_scope`) |
| **B6** | BLOQUEANTE | `Ticket.type` **no existe**: es `work_item_type` (`models.py:55`). `getattr(ticket,"type",None)` devolvía `None` **siempre y en silencio**, dejando ciega a `classify_ticket_kind` | F1 (pseudocódigo + firma de `classify_ticket_kind`) + gate **T13** |
| **B7** | IMPORTANTE | *(verificado en esta pasada)* v2 afirmaba que `test_harness_flags.py` tiene **4 rojos preexistentes** y pedía criterio **delta**. **Falso:** ese archivo da **`56 passed, 0 failed`**; los 4 rojos son de `test_harness_flags_help.py` | F1/F2/F4: criterios **absolutos** (57 / 58 / 59) |
| **B8** | IMPORTANTE | *(verificado en esta pasada)* Las flags `HARNESS_LEARNING_*` **se auto-excluían** del meta-test anti-drift, que solo escanea `STACKY_` | Guardarraíl 7 + las 4 keys renombradas |
| **B9** | IMPORTANTE | *(verificado en esta pasada)* §1 declaraba `harness_telemetry` como *"el sustrato que F1 lee"*. **No contiene ninguna señal de verificación** (solo tokens/costo/turnos) | §3-bis (calibración ejecutada) + Glosario |
