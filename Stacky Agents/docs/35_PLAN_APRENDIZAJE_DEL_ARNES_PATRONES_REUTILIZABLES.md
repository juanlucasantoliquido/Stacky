# 35 — Plan Aprendizaje del Arnés: convertir las señales de verificación que hoy se descartan en patrones persistentes y reutilizables que amplifican al operador, sin sacarlo del lazo

**Fecha original:** 2026-06-16 · **Revisión v2:** 2026-08-01
**Versión:** **v1 -> v2** (reescritura contra el código real; v1 no era implementable)
**Estado:** PROPUESTO — MEJORADO (v1 RECHAZADO por 7 bloqueantes; v2 corrige los 7 — ver la tabla de §13)
**Autor:** StackyArchitectaUltraEficientCode
**Predecesores directos (motor + verificación):** `docs/27` (contexto/retrieval/routing/caché), `docs/28` (lifecycle/telemetría), `docs/29` (criterios + few-shot + repair semántico), `docs/30` (verificación determinista de existencia), `docs/31` (verificación ejecutable del entregable), `docs/32` (contrato de aceptación pre-run).
**Predecesores de método:** `docs/26` (memoria configurable), memoria colaborativa (Fase A-E + hardening), `docs/33` (flags 100% configurables por UI), `docs/34` (Client Profile).
**Audiencia:** dev agéntico junior (Haiku, Codex CLI, GitHub Copilot Pro). Cada fase es autocontenida: objetivo en 1 frase, archivos EXACTOS, símbolos EXACTOS, pseudocódigo que **compila contra la firma real**, tests primero con comando exacto, criterio de aceptación binario y satisfacible, flag con default justificado, impacto por runtime y línea de "trabajo del operador".

---

## CHANGELOG v1 -> v2 (qué cambió y qué hallazgo lo motivó)

| # | Cambio | Hallazgo |
|---|---|---|
| 1 | **F1 cambia de seam: `finalize_run` -> `ticket_status.register_post_hook`.** La afirmación "`finalize_run` es el seam común a los 3 runtimes" era FALSA (1 de 3). | **C1** |
| 2 | El diff de F1 se reescribe contra la firma real del post-hook y lee la metadata **ya persistida** desde la DB (no un patch sin fusionar). | **C2** |
| 3 | F2: `Block(name=, priority=, text=)` **no existe** -> bloques son `dict` con clave `"id"`; la prioridad se registra en `_BLOCK_PRIORITY`. | **C3** |
| 4 | Prioridad del bloque **45**, NO 50: 50 es `_DEFAULT_PRIORITY` y hacía el test un falso verde estructural. | **C3** |
| 5 | Comando de tests: `backend/.venv` (py3.13.5, roto) -> **`backend/venv`** (py3.11.9) en las 5 fases. | **C4** |
| 6 | Flags: los 2 booleanos pasan de **OFF a ON** con justificación escrita ítem por ítem; se declara `default=` y `_CURATED_DEFAULTS_ON`. | **C5** |
| 7 | Se agrega como trabajo explícito el registro en **`_CATEGORY_KEYS`** (se reusa la categoría existente `contexto_memoria`; no se crea grupo nuevo). | **C6** |
| 8 | `persist_pattern` pasa el argumento obligatorio **`type="pattern"`**, que v1 omitía (`TypeError`). | **C7** |
| 9 | `confidence` va a la **columna nativa** y `occurrences` se deriva de **`revision_count`**: se filtra en SQL, no deserializando en Python en el camino caliente. | **C8**, **C9** |
| 10 | El "detector de secretos de la memoria colaborativa" **no existe**: el símbolo real es `redact_secrets` en `services/pr_review_sanitize.py`. | **C10** |
| 11 | Se agrega gate anti-"construido y jamás cableado": el registro en `app.py` es criterio de aceptación. | **C11**, **[ADICIÓN ARQUITECTO 2]** |
| 12 | Todos los anclajes re-anclados **por símbolo**; los 10 `archivo:línea` desviados/off-by-one, corregidos. | **C12** |
| 13 | Criterio sobre `test_harness_flags.py` pasa a **delta** (tiene 4 rojos preexistentes ajenos). | **C13** |
| 14 | Todo criterio binario exige el **conteo `N passed`** (pytest `-k` sin match da exit 0). | **C14** |
| 15 | Se nombran los 3 archivos de test nuevos y su registro en **los DOS ratchets**; los tests de flags/health reusan archivos ya registrados. | **C15** |
| 16 | Se corrige la afirmación de prioridades: no existe bloque "grounding" y `acceptance-criteria` es **74** (podable). | **C16** |
| 17 | `status="dismissed"` **no existe** en `ALL_STATUSES` -> se usa **`"rejected"`**. | **C17** |
| 18 | Se agrega **F1.0 (calibración contra metadata real)** antes de escribir el extractor. | **[ADICIÓN ARQUITECTO 1]** |
| 19 | Se declara el **CORTE en 2 tandas** (F0+F1+F3 / F2+F4). | **C20** |

---

## 0. Cómo leer este plan (regla de anclajes)

**Los `archivo:línea` caducan.** En este repo el ratio de supervivencia de un anclaje a ~2 meses es de **1 en 21**. Por eso **todo anclaje de este plan es por SÍMBOLO**: "la función `X` en `services/Y.py`". Los números de línea que aparecen son orientativos y **medidos el 2026-08-01**; si no coinciden, manda el símbolo. Antes de editar, localizá el símbolo con `grep -n "def <simbolo>" <archivo>`.

**Tesis (innegociable):** los planes 27-32 construyeron un motor que piensa mejor, no se ahoga, cumple el encargo, está anclado a la realidad y deriva un contrato ejecutable antes de trabajar. Toda esa maquinaria emite, en cada run, **señales de altísimo valor**: qué criterio falló, qué finding determinista saltó, qué repair lo arregló, cuántos reintentos costó. **Esas señales mueren al terminar el run.** El run N+1 del mismo proyecto y tipo de ticket re-tropieza con el mismo fallo y re-paga el mismo repair. El operador, además, **no ve** qué falla recurrentemente: revisa cada `needs_review` aislado. Este plan cierra el séptimo lado: **cosechar** las señales que 29-32 ya producen, **agregarlas en patrones**, **persistirlas reusando la memoria colaborativa**, **reinyectarlas como pista barata** y **mostrarlas al operador**.

**"Aprendizaje" NO significa "autonomía" (regla 11, [[human-in-the-loop-fundamental]]):** el sistema **observa, agrega y propone**; nunca decide ni aplica solo. Un patrón se inyecta como **pista podable de prioridad media** (nunca pisa criterios ni contrato), y todo insight es **lectura** + confirmar/descartar. Stacky no reabre tickets, no relanza runs, no transiciona estados. Cada fase trae su línea "Por qué NO viola regla 11".

**Calidad nunca se sacrifica:** todos los mecanismos son aditivos y degradables. La cosecha es **pasiva y post-run**. La reinyección es podable: bajo presión de budget se descarta **antes** que criterios/contrato. Si un patrón es ruidoso, su `confidence` cae y deja de inyectarse; el operador lo descarta de por vida.

---

## 1. Relación con los planes previos (qué reusa, qué NO re-implementa)

Todos los anclajes de esta sección fueron **verificados el 2026-08-01**.

- **REUSA, no re-implementa:**
  - **`services/memory_store.py`** como sustrato de persistencia: `save_observation`, `upsert_by_topic_key`, `search`, `list_observations`, `set_status`, modelo `StackyMemoryObservation`. Un patrón es **una observación más** con `scope` reservado; **cero tabla nueva**.
  - **`harness/telemetry.py`**: `RunTelemetry` y `persist`. `persist(execution_id, t)` escribe `metadata["harness_telemetry"]` en la fila `AgentExecution`. **Ese es el sustrato que F1 lee.**
  - **Chokepoint post-run: `on_execution_end` + `register_post_hook` en `services/ticket_status.py`.** (v1 usaba `finalize_run`; ver C1.)
  - **`services/context_enrichment.py`**: `enrich_blocks`, el mapa `_BLOCK_PRIORITY`, la función `_block_priority` y el umbral `_HIGH_PRIORITY_THRESHOLD`. La reinyección es **un dict más** en la lista de bloques.
  - **Redacción de secretos: `redact_secrets` en `services/pr_review_sanitize.py`.** (v1 citaba un detector inexistente; ver C10.)
  - **Salud / KPIs**: `compute_health` y `by_project` en `services/harness_health.py` + `api/diag.py`.
  - **Flags por UI**: `FlagSpec` y `FLAG_REGISTRY` en `services/harness_flags.py` + `api/harness_flags.py` -> `HarnessFlagsPanel`.
- **Frontera con 29:** el 29 **deriva** criterios por LLM en cada run. El 35 **no deriva nada**: cosecha **cuáles fallaron**. Disjuntos.
- **Frontera con 31/32:** 31 ejecuta verificadores, 32 deriva el contrato. El 35 cosecha el **resultado**. Disjuntos.
- **Frontera con 27:** el 27 decide qué **documento** entra por similitud. El 35 inyecta **patrones de fallo/remedio** del arnés. Coexisten con prioridades separadas.
- **Frontera con 26 / memoria colaborativa:** esos capturan **conocimiento de dominio**; el 35 captura **conocimiento del proceso de verificación**, con `scope` reservado.
- **SUBSUME / REEMPLAZA:** nada.

---

## 2. Qué NO es este plan (anti-scope explícito)

1. **No es autonomía.** No relanza runs, no reabre tickets, no transiciona estados, no aplica parches solo.
2. **No agrega RBAC ni multi-usuario.** Mono-operador sin auth real ([[stacky-no-auth-substrate]]): `current_user` es un header sin validar y **403 significa flag apagada, no permiso**. Los patrones son por-proyecto, nunca por-usuario.
3. **No crea un store nuevo.** `memory_store` con `scope="harness_pattern"`. Cero tabla, cero migración, cero dep nueva, cero FTS5.
4. **No deriva criterios ni contratos.** Solo **lee** lo que 29-32 ya escribieron.
5. **No cambia QUÉ/CUÁNDO se publica al tracker.** La cosecha es solo-lectura sobre una ejecución terminada.
6. **No re-implementa telemetría, gate, repair ni ranking de contexto.**
7. **No degrada el run cuando un patrón es ruidoso.** La pista es podable; en el peor caso se descarta.
8. **No mantiene contadores a mano que el store ya lleva.** `occurrences` sale de `revision_count`; `confidence` es columna nativa. (C8.)

---

## 3. Diagnóstico: dónde mueren hoy las señales (evidencia verificada 2026-08-01)

| # | Debilidad | Evidencia (por símbolo) | Impacto |
|---|---|---|---|
| **D1** | Las señales de gate/repair/verificadores **no se agregan más allá del run**. `persist` (`harness/telemetry.py`) las deja en `metadata["harness_telemetry"]` de la ejecución, pero **nadie las lee después**. | `persist` en `harness/telemetry.py`; `finalize_run` en `harness/post_run.py` | Cada run del mismo patrón re-tropieza y re-paga el mismo repair. |
| **D2** | **No hay reinyección de "lo que suele fallar".** `enrich_blocks` (`services/context_enrichment.py`) inyecta repo/memoria/criterios, pero **ningún bloque** trae el historial de fallos del propio arnés. | `enrich_blocks`, `_BLOCK_PRIORITY` | El agente re-comete errores que el arnés ya vio y arregló. |
| **D3** | **El operador ve incidentes sueltos, no patrones.** `compute_health` agrega costo/fiabilidad por runtime y proyecto, pero no "este fallo apareció N veces". | `compute_health`, `by_project` en `services/harness_health.py` | No puede priorizar la causa raíz que más cuesta. |
| **D4** | **Los repairs exitosos no dejan rastro reutilizable.** `harness/run_repair.py`, `harness/criteria_repair.py`, `harness/exec_repair.py` arreglan en el run; el diagnóstico que funcionó no se guarda. | los 3 módulos de repair | Se re-descubre el mismo remedio gastando un pase correctivo evitable. |

**Lectura central:** el sustrato ya existe y es sólido. El valor del 35 no es construir un store: es **(a) cosechar**, **(b) agregar con confianza**, **(c) reinyectar barato** y **(d) mostrar al operador**.

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
   - `on_execution_end`: transversal a los 3, con ~15 call sites -> se usa vía **`register_post_hook`** (punto único de registro).
2. **Cero trabajo extra al operador:** invisible o configurable desde la UI. Sin pasos manuales nuevos.
3. **Human-in-the-loop innegociable:** observar/agregar/proponer, nunca decidir/aplicar. Regla 11.
4. **Mono-operador sin auth real:** nada de RBAC.
5. **No degradar performance/seguridad/estabilidad/DX.** Cero deps, cero FTS5, cero tabla nueva. **El costo por run del camino caliente debe estar acotado y testeado** (guardarraíl 9).
6. **Flag nuevo -> `config.py` + `FLAG_REGISTRY` + `_CATEGORY_KEYS` en la MISMA fase que lo introduce.** Registrar una flag son **seis lugares**, no uno:
   1. `backend/config.py` (el default **efectivo**),
   2. `FLAG_REGISTRY` en `services/harness_flags.py`,
   3. **`_CATEGORY_KEYS`** en `services/harness_flags.py` (si falta, el test `test_every_registry_flag_is_categorized` rompe CI a propósito — Plan 63),
   4. `_CURATED_DEFAULTS_ON` si se declara `default=`,
   5. `backend/.env.example`,
   6. el test de registro en `backend/tests/test_harness_flags.py`.
   **Ojo:** una flag `env_only=True` **no** obtiene default por estar en el registry; si no está en `config.py`, un consumidor con `getattr(config, "X", False)` se lleva el default del `getattr` y la flag queda **inerte aunque registrada**.
7. **Default de flag nuevo = ON**, salvo que se justifique por escrito con una de estas dos categorías: **(A)** quema tokens **en reposo** (loop/daemon/barrido/polling que llama a un modelo sin que el operador pida nada); **(B)** escribe en un sistema **real del operador**, destruye datos, o le saca la decisión. *"Retro-compat byte-idéntica"*, *"default seguro"* y *"para no cambiar el comportamiento actual"* **NO son justificaciones válidas** (ver §4-bis).
8. **Suite contaminada -> validar POR ARCHIVO** con el intérprete que **anda**. `pytest tests` completo **no es un veredicto**. `pytest -k` sin match da **exit 0** -> todo criterio exige el **conteo `N passed`**.
9. **Costo por run acotado:** cualquier lectura en el camino caliente de `enrich_blocks` filtra y limita **en SQL**, nunca deserializando N filas en Python.

> ### Comando base de tests (CORREGIDO — C4)
> `backend/.venv` es **Python 3.13.5**, el intérprete con el pin `pywin32==306` roto que el propio plan v1 declaraba inservible mientras lo usaba en los 5 comandos. El que **anda** es `backend/venv` (**Python 3.11.9**).
> ```powershell
> cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
> & "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/venv/Scripts/python.exe" -m pytest "tests/<ARCHIVO>" -q
> ```
> La ruta contiene **espacios**: siempre entre comillas. **Nunca** correr la suite completa.

---

## 4-bis. Decisión de defaults de flags (justificación escrita — C5)

| Flag | Tipo | Default v1 | **Default v2** | Justificación |
|---|---|---|---|---|
| `HARNESS_LEARNING_HARVEST_ENABLED` | bool | OFF | **ON** | **No es (A):** no hay loop ni daemon; corre **una vez, post-run, de una ejecución que el operador ya pidió**, y no llama a ningún modelo (extracción determinista stdlib). **No es (B):** escribe en la **memoria interna de Stacky** (`memory_store`), no en ADO/GitLab ni en ningún sistema del operador, y no le saca ninguna decisión. |
| `HARNESS_LEARNING_INJECT_ENABLED` | bool | OFF | **ON** | **No es (A):** no prefetchea ni consulta un modelo en reposo; solo agrega texto al prompt de un run **que el operador ya pidió**. **No es (B):** no escribe nada en ningún sistema; el bloque es podable y de prioridad media. |
| `HARNESS_LEARNING_INJECT_MAX` | int | 5 | **5** | Numérica: no es ON/OFF, tiene valor default. Techo de pistas por run. |
| `HARNESS_LEARNING_INJECT_MIN_CONF` | float | 0.5 | **0.5** | Numérica. Confianza mínima para inyectar. |

**Consecuencia obligatoria de default ON:** las 2 booleanas se declaran con `default=True` en su `FlagSpec` **y** deben agregarse a **`_CURATED_DEFAULTS_ON`** en `services/harness_flags.py`; sin eso, el test `test_default_known_only_for_curated` pasa de verde a rojo. El default **efectivo** lo fija `backend/config.py`, no el registry.

> **Riesgo asumido y su mitigación:** con `INJECT_ENABLED=ON` desde el día 1, un patrón espurio podría inyectarse. Mitigación estructural: F3 exige `confidence ≥ 0.5`, y un patrón visto **una sola vez** queda en `0.2` -> **no se inyecta hasta acumular ≥3 ocurrencias**. En la práctica el sistema arranca silencioso y se enciende solo cuando hay evidencia. El operador puede apagarlo desde la UI en cualquier momento.

---

## FASE F0 — Sustrato: tipo de patrón + persistencia en la memoria existente

**Objetivo (1 frase):** definir `HarnessPattern` y su persistencia reutilizando `memory_store`, con `scope` reservado, **columnas nativas** para confianza/ocurrencias y redacción de secretos.

**Archivos:**
- CREAR `backend/services/harness_learning.py`.
- (Sin cambios en `config.py`/`harness_flags.py` en esta fase: F0 no introduce flags.)

**Contratos reales que F0 debe respetar (verificados 2026-08-01):**

```python
# services/memory_store.py — firma REAL, keyword-only. `type` es OBLIGATORIO (C7).
upsert_by_topic_key(*, project: str, type: str, title: str, content: str,
                    scope: str = "project", topic_key: str, status: str = "active",
                    confidence: float | None = None, source_kind=None,
                    source_execution_id=None, source_ticket_id=None, source_ado_id=None,
                    source_agent_type=None, author_email=None, author_role=None,
                    tags=None, expires_at=None, review_after=None) -> str
# docstring: "Upsert por `topic_key`. Incrementa `revision_count` si ya existía."

list_observations(*, project=..., scope: str | None = None, status=..., ...)
set_status(memory_id: str, status: str) -> bool
INJECT_SCOPES  = ("project", "team", "global")       # ALLOWLIST de inyección
ALL_STATUSES   = ("draft","active","needs_review","superseded","rejected","quarantined","deleted")
```

**Tres decisiones que v1 dejó abiertas o resolvió mal:**

1. **`type="pattern"`** — es obligatorio y v1 lo omitía (`TypeError`). Se usa `"pattern"`, que está en `INJECTABLE_TYPES` y **no** en `RESERVED_TYPES` (los tipos del canal SYSTEM). El `type` no se valida contra un enum, pero elegir uno fuera de taxonomía rompería la UI de memoria.
2. **`scope="harness_pattern"`** — 15 chars, entra en la columna `String(20)`. **No se valida** contra enum, así que no requiere schema nuevo. Y como `INJECT_SCOPES` es una **allowlist** `("project","team","global")`, un patrón **jamás** entra a la inyección de dominio (ver F0 test 6).
3. **`occurrences` y `confidence` NO se serializan en el JSON** (C8): `occurrences` se **deriva de `revision_count`** (el store lo incrementa solo, de forma atómica; llevarlo a mano exige un read-modify-write con condición de carrera) y `confidence` va a la **columna nativa** (si se entierra en el JSON, `list_patterns(min_confidence=...)` tendría que deserializar TODAS las observaciones del proyecto en Python **dentro del camino caliente de `enrich_blocks`**).

**Símbolos a crear en `services/harness_learning.py`:**

```python
HARNESS_PATTERN_SCOPE = "harness_pattern"   # scope reservado; fuera de INJECT_SCOPES por construcción
HARNESS_PATTERN_TYPE  = "pattern"           # type obligatorio del store (C7)
PATTERN_STATUS_ACTIVE    = "active"         # de ALL_STATUSES
PATTERN_STATUS_DISMISSED = "rejected"       # C17: "dismissed" NO existe en ALL_STATUSES

@dataclass(frozen=True)
class HarnessPattern:
    project: str
    agent_type: str      # "functional" | "technical" | "developer" | "qa" | "unknown"
    ticket_kind: str     # "bug" | "feature" | "task" | "unknown"
    signal_kind: str     # "criterion_fail" | "verifier_fail" | "contract_fail" | "repair_success"
    signal_key: str      # id estable del fallo
    remedy_hint: str     # texto corto redactado (puede ser "")
    occurrences: int     # DERIVADO de revision_count al leer; no se escribe a mano
    confidence: float    # columna nativa; se recalcula al leer (F3)
    last_seen: str       # ISO

def pattern_topic_key(p: HarnessPattern) -> str:
    return f"{p.project}|{p.agent_type}|{p.ticket_kind}|{p.signal_kind}|{p.signal_key}"

def persist_pattern(p: HarnessPattern) -> str: ...
def list_patterns(project: str, *, agent_type=None, ticket_kind=None,
                  min_confidence: float = 0.0, limit: int = 50) -> list[HarnessPattern]: ...
def register(register_post_hook) -> None: ...   # F1 — cableado
```

**Pseudocódigo de `persist_pattern` (compila contra la firma real):**

```python
from services.pr_review_sanitize import redact_secrets   # C10 — símbolo REAL

def persist_pattern(p: HarnessPattern) -> str:
    if not (p.project or "").strip():
        return ""                                   # caso borde: project vacío -> no persiste
    safe = replace(p,
                   remedy_hint=redact_secrets(p.remedy_hint or ""),
                   signal_key=redact_secrets(p.signal_key or ""))
    payload = json.dumps({                          # SIN occurrences ni confidence (C8)
        "agent_type": safe.agent_type, "ticket_kind": safe.ticket_kind,
        "signal_kind": safe.signal_kind, "signal_key": safe.signal_key,
        "remedy_hint": safe.remedy_hint, "last_seen": safe.last_seen,
    }, sort_keys=True, ensure_ascii=False)
    return memory_store.upsert_by_topic_key(
        project=safe.project,
        type=HARNESS_PATTERN_TYPE,                  # C7 — obligatorio
        title=safe.signal_key[:120] or "(sin clave)",
        content=payload,
        scope=HARNESS_PATTERN_SCOPE,
        topic_key=pattern_topic_key(safe),
        status=PATTERN_STATUS_ACTIVE,
        confidence=safe.confidence,                 # columna NATIVA
        source_agent_type=safe.agent_type,
    )
```

> **Nota sobre `redact_secrets`:** devuelve el texto con `_MASK = "***REDACTED***"` sustituido. **No existe** ningún `contains_secret(...)` en el repo — v1 lo inventaba. Se llama **incondicionalmente** (es idempotente sobre texto limpio), sin predicado previo.

**`list_patterns` — filtrado en SQL, no en Python (C9):** consulta `list_observations(project=..., scope=HARNESS_PATTERN_SCOPE, status="active")` filtrando `confidence >= min_confidence` **en la query** y aplicando `limit`. Deserializa **solo** las filas que ya pasaron el filtro. `occurrences` se lee de `revision_count` de la fila.

**Tests PRIMERO** — `backend/tests/test_harness_learning.py` (**archivo nuevo**; registrar en los 2 ratchets, ver §12):
1. `test_pattern_topic_key_is_stable` — misma tupla -> misma key; distinto `signal_key` -> distinta.
2. `test_persist_is_idempotent_by_topic_key` — persistir 2 veces **no** crea 2 observaciones.
3. `test_persist_increments_revision_count` — el 2º persist deja `revision_count == 2` (prueba que `occurrences` es derivable y **no** se lleva a mano).
4. `test_persist_redacts_secrets` — un `remedy_hint` con un token tipo PAT se guarda con `"***REDACTED***"` y **sin** el valor original.
5. `test_persist_passes_required_type` — la observación persistida tiene `type == "pattern"` (gate anti-`TypeError`, C7).
6. **`test_harness_pattern_scope_is_never_injected`** — se persiste un patrón y se llama `memory_store.get_context_for_run(...)` con sus defaults: el contenido del patrón **no aparece**. *Fija como contrato lo que hoy es solo un default:* `INJECT_SCOPES` es allowlist y `harness_pattern` queda afuera por construcción. (C19.)
7. `test_confidence_is_a_native_column` — tras persistir con `confidence=0.8`, la fila tiene `confidence == 0.8` (no enterrado en el JSON).
8. `test_empty_project_is_not_persisted` — `project=""` -> `""` y cero filas.

**Comando exacto:**
```powershell
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/venv/Scripts/python.exe" -m pytest "tests/test_harness_learning.py" -q
```

**Criterio de aceptación BINARIO:** la corrida imprime **`8 passed`** (el conteo es parte del criterio — C14) y `0 failed`. Cero cambios de schema en `memory_store`.

**Flag + default:** ninguna (estructura inerte).
**Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.
**Por qué NO viola regla 11:** define un tipo y una forma de guardar; no decide ni actúa.
**Salvaguarda de calidad:** redacción e idempotencia testeadas; el test 6 impide contaminar la memoria de dominio.

---

## FASE F1 — Cosecha pasiva post-run (harvest) en el chokepoint transversal

**Objetivo (1 frase):** al terminar **cualquier** ejecución en **cualquiera de los 3 runtimes**, leer la metadata ya persistida y guardar los fallos/remedios como patrones, sin alterar el run.

### C1 — Por qué el seam cambia respecto de v1 (medición, no opinión)

v1 afirmaba **cuatro veces** que `finalize_run` era "el seam post-run común a los 3 runtimes". **Es falso.** Llamadores de producción de `finalize_run` (excluyendo `tests/` y su propio módulo), medidos el 2026-08-01:

| Runtime | ¿Llama `finalize_run`? |
|---|---|
| Codex CLI (`services/codex_cli_runner.py`) | **SÍ** — único llamador real |
| Claude Code CLI (`services/claude_code_cli_runner.py`) | **NO** |
| GitHub Copilot (`agent_runner.py`) | **NO** |

Implementar F1 como estaba escrito habría dejado la cosecha corriendo en **1 de 3 runtimes**, rompiendo un riel duro del producto, con un DoD que declaraba paridad -> **falso verde de manual**.

**Seam correcto:** `on_execution_end` en `services/ticket_status.py`, invocado por los 3 runtimes (~15 call sites entre `agent_runner.py`, `services/claude_code_cli_runner.py`, `services/agent_completion.py`, `services/agent_completion_internal.py` y `api/executions.py`). **No se editan los 15 call sites:** se usa el punto único `register_post_hook`.

**Tres ventajas estructurales del seam elegido:**
1. **Punto único de registro** (`register`), no 15 ediciones.
2. **La garantía "nunca rompe el run" ya está construida:** `_run_post_hooks` envuelve cada hook en `try/except` y solo loguea (`"post_hook '%s' falló"`). No hay que confiar en que el autor recuerde el try/except.
3. **Resuelve la dependencia temporal de C2:** en el post-hook la metadata **ya está persistida en la DB**.

### C2 — Por qué el diff de v1 no compilaba

La firma real de `finalize_run` (`harness/post_run.py`) es keyword-only:
`finalize_run(*, runtime, agent_type, output_text, ado_id=None, gate_enabled=False, log=None, workspace=None, changed_files=None, run_id=None, exec_send_fn=None) -> PostRunResult`.
El diff de v1 pasaba `project=`, `ticket_title=`, `ticket_type=`, `telemetry_md=` y `result=post_run_result`: **ninguno de esos nombres existe** en ese scope. Además `PostRunResult` expone solo `status_suggestion, contract_score, contract_passed, contract_failures, confidence_overall, metadata_patch, artifacts`, y **`metadata_patch` es un patch todavía NO fusionado** con la metadata de la ejecución -> la "telemetría ya persistida" que v1 quería leer **no existía en ese instante**. En el post-hook sí existe: `persist` en `harness/telemetry.py` ya escribió `metadata["harness_telemetry"]` en la fila `AgentExecution`.

### [ADICIÓN ARQUITECTO 1] — F1.0: calibrar el extractor contra metadata REAL antes de escribirlo

**Problema que ataca:** v1 murió tres veces por el mismo mecanismo — pseudocódigo escrito contra una firma **imaginada** (C2, C3, C7). El extractor de señales es el próximo candidato: nadie sabe de memoria qué claves exactas trae `metadata["harness_telemetry"]`.

**F1.0 es un paso obligatorio y bloqueante de F1:**
1. **Solo lectura** sobre la DB de desarrollo: seleccionar 3-5 ejecuciones terminadas recientes y volcar las **claves** (no los valores sensibles) de `metadata_dict`.
2. Guardar el resultado como fixture congelado `backend/tests/fixtures/harness_metadata_sample.json`, **con secretos redactados** vía `redact_secrets`.
3. **Recién entonces** escribir `_SIGNAL_EXTRACTORS` contra las claves **observadas**.
4. Si una señal de 29/31/32 **no aparece** en ninguna muestra, el plan lo declara explícitamente: ese `signal_kind` queda **sin extractor** y su test se marca `xfail` con motivo, en vez de inventar la clave.

**Regla dura:** está **prohibido** escribir un nombre de clave de metadata que no aparezca en el fixture. Un extractor contra una clave inexistente devuelve 0 patrones **en silencio** — el peor falso verde posible, porque todos los tests con mocks pasarían.

**Archivos a editar (F1):**
- EDITAR `backend/services/harness_learning.py` — agregar `classify_ticket_kind`, `harvest_from_execution`, `register`.
- EDITAR `backend/app.py` — **cablear el hook** junto a los registros existentes (ver abajo).
- EDITAR `backend/config.py` — `HARNESS_LEARNING_HARVEST_ENABLED = True`.
- EDITAR `backend/services/harness_flags.py` — `FlagSpec` + `_CATEGORY_KEYS` + `_CURATED_DEFAULTS_ON`.
- EDITAR `backend/.env.example`.
- CREAR `backend/tests/fixtures/harness_metadata_sample.json` (F1.0).

**Símbolos a crear (firma alineada al contrato real del hook):**

```python
def classify_ticket_kind(ticket_title: str, ticket_type: str | None) -> str:
    """Heurística barata stdlib -> "bug"|"feature"|"task"|"unknown". Sin LLM."""

def harvest_from_execution(*, ticket_id: int, execution_id: int, final_status: str,
                           agent_type: str | None = None, error: str | None = None,
                           **kwargs) -> int:
    """Post-hook. Firma EXACTA que exige register_post_hook (ver docstring del registrador):
       fn(*, ticket_id, execution_id, final_status, agent_type, error, **kwargs)
    `**kwargs` es obligatorio: el chokepoint puede pasar claves adicionales.
    Devuelve nº de patrones persistidos. Best-effort."""

def register(register_post_hook) -> None:
    """Idioma de cableado del repo (mismo que services/epic_autopublish.py)."""
    register_post_hook(harvest_from_execution)
```

**Pseudocódigo de `harvest_from_execution` (compila contra el contrato real):**

```python
def harvest_from_execution(*, ticket_id, execution_id, final_status,
                           agent_type=None, error=None, **kwargs) -> int:
    if not config.HARNESS_LEARNING_HARVEST_ENABLED:
        return 0
    with session_scope() as session:                       # lectura de la fila YA persistida
        row = session.get(AgentExecution, execution_id)
        if row is None:
            return 0
        md = row.metadata_dict or {}                       # incluye "harness_telemetry" (persist)
        ticket = session.get(Ticket, ticket_id)
        project      = getattr(ticket, "stacky_project_name", "") or ""
        ticket_title = getattr(ticket, "title", "") or ""
        ticket_type  = getattr(ticket, "type", None)
    kind = classify_ticket_kind(ticket_title, ticket_type)
    n = 0
    for signal_kind, signal_key, remedy in _extract_signals(md):   # claves del fixture F1.0
        if persist_pattern(HarnessPattern(
                project=project, agent_type=(agent_type or "unknown"), ticket_kind=kind,
                signal_kind=signal_kind, signal_key=signal_key, remedy_hint=remedy,
                occurrences=1, confidence=0.0,   # F3 recalcula al leer
                last_seen=datetime.utcnow().date().isoformat())):
            n += 1
    return n
```

**Cableado en `backend/app.py` (OBLIGATORIO — sin esto la fase no existe):** junto a los registros ya presentes (`epic_autopublish.register(ticket_status.register_post_hook)` y hermanos):

```python
from services import harness_learning
harness_learning.register(ticket_status.register_post_hook)
```

**Casos borde:**
- Metadata sin señales de 29-32 -> 0 patrones, sin error.
- `repair_success` sin diagnóstico legible -> `remedy_hint=""` (patrón válido).
- Flag OFF -> `return 0` en la primera línea; ningún efecto.
- Ejecución inexistente / ticket borrado -> 0, sin excepción.
- Excepción inesperada -> la absorbe `_run_post_hooks` y la loguea; **el run nunca se cae**.

**Tests PRIMERO** — agregar a `backend/tests/test_harness_learning.py`:
9. `test_harvest_extracts_criterion_fail` — usando el **fixture real** de F1.0.
10. `test_harvest_extracts_repair_success_with_hint` — `remedy_hint` no vacío.
11. `test_harvest_is_noop_without_signals` — metadata `{}` -> 0, sin excepción.
12. `test_harvest_never_raises` — metadata corrupta -> no propaga.
13. `test_classify_ticket_kind` — títulos representativos -> categoría correcta.
14. `test_flag_off_does_not_harvest` — flag OFF -> 0 y cero escrituras.
15. **`test_harvest_signature_matches_post_hook_contract`** — por `inspect.signature`, `harvest_from_execution` acepta exactamente `ticket_id, execution_id, final_status, agent_type, error` como keyword y tiene `**kwargs`. *Gate contra el defecto que mató a v1: firma imaginada.*
16. **`test_hook_is_registered_in_app`** — parsea `backend/app.py` por **AST** y exige la llamada `harness_learning.register(...)`. *Ver [ADICIÓN ARQUITECTO 2].*

Y en `backend/tests/test_harness_flags.py` (**archivo ya registrado en ambos ratchets** — C15):
17. `test_harness_learning_harvest_flag_registered` — la key está en `FLAG_REGISTRY`, en `_CATEGORY_KEYS` y con `default=True`.

**Comando exacto:**
```powershell
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/venv/Scripts/python.exe" -m pytest "tests/test_harness_learning.py" -q
& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/venv/Scripts/python.exe" -m pytest "tests/test_harness_flags.py" -q
```

**Criterio de aceptación BINARIO (satisfacible — C13):**
- `tests/test_harness_learning.py` imprime **`16 passed`**, `0 failed`.
- `tests/test_harness_flags.py`: **criterio DELTA, no absoluto.** Este archivo tiene **4 fallos preexistentes ajenos** (rojo de fábrica); exigir "pasa" sería insatisfacible. El criterio es: **(a)** el test nuevo `test_harness_learning_harvest_flag_registered` **aparece en la lista de passed**, y **(b)** el nº de `failed` **no crece** respecto de la corrida base tomada **antes** de tocar el archivo. Registrar ambos conteos en el PR.

**Flag + default:** `HARNESS_LEARNING_HARVEST_ENABLED` (bool, **ON** — justificación en §4-bis), en los 6 lugares del guardarraíl 6.

**Impacto por runtime (medido, no asumido):** Codex CLI, Claude Code CLI y Copilot llaman los tres a `on_execution_end` -> los tres disparan el hook. **Fallback:** si un runtime no escribió alguna señal, se extraen las que estén.

**Trabajo del operador:** ninguno.
**Por qué NO viola regla 11:** lee y guarda; no decide, no actúa sobre el ticket, no publica.
**Salvaguarda de calidad:** best-effort por construcción (`_run_post_hooks` absorbe); flag OFF -> `return 0` inmediato; el fixture de F1.0 impide extractores contra claves inventadas.

---

## FASE F3 — Confianza, decaimiento y supresión de ruido

> Va **antes** que F2 (como en v1): F2 no debe inyectar sin el filtro de confianza. El orden F0 -> F1 -> F3 -> F2 -> F4 es correcto y se mantiene.

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
    return pattern_status == PATTERN_STATUS_DISMISSED    # "rejected" (C17)
```

**C17 — por qué no es `"dismissed"`:** `ALL_STATUSES` en `services/memory_store.py` es `("draft","active","needs_review","superseded","rejected","quarantined","deleted")`. **`"dismissed"` no existe.** `set_status` no valida (asigna el string tal cual), así que v1 habría "funcionado" mientras metía un estado fuera de taxonomía, invisible para todo consumidor que itere `ALL_STATUSES`. Se usa **`"rejected"`**, cuya semántica es exactamente "el operador lo descartó".

**Integración con `list_patterns` (F0):** filtra `status == "active"` en SQL y recalcula `confidence` **on-read** con `compute_confidence` (no escribe). `occurrences` sale de `revision_count`.

**Casos borde (con los números reales de la fórmula):**
- 1 ocurrencia hoy -> `0.2` < 0.5 -> **no se inyecta**.
- 3 ocurrencias hoy -> `0.6` ≥ 0.5 -> se inyecta.
- 6 ocurrencias hace 120 días -> `1.0 * 0.5**4 = 0.063` -> rancio, no se inyecta.
- Patrón `rejected` -> excluido siempre.

**Tests PRIMERO** — agregar a `backend/tests/test_harness_learning.py`:
18. `test_confidence_grows_with_occurrences`.
19. `test_confidence_decays_with_age`.
20. `test_single_occurrence_below_default_threshold` — asserta el valor exacto `0.2 < 0.5`.
21. `test_three_occurrences_reach_threshold` — asserta `0.6 >= 0.5` (fija el punto de encendido; sostiene el riesgo asumido de §4-bis).
22. `test_dismissed_pattern_is_never_listed` — un patrón en `"rejected"` no aparece en `list_patterns`.
23. `test_dismissed_status_is_in_all_statuses` — `PATTERN_STATUS_DISMISSED in memory_store.ALL_STATUSES`. *Gate contra C17.*

**Comando exacto:** el de F0/F1 sobre `tests/test_harness_learning.py`.
**Criterio de aceptación BINARIO:** imprime **`23 passed`**, `0 failed`.

**Flag + default:** sin flag propio (gobernado por `HARNESS_LEARNING_INJECT_MIN_CONF`).
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

La **prioridad no es un campo del bloque**: sale del mapa `_BLOCK_PRIORITY` vía `_block_priority(block)`, que hace `_BLOCK_PRIORITY.get(block.get("id") or "")`. Por lo tanto, declarar `HARNESS_PATTERN_BLOCK_PRIORITY = 50` en `harness_learning.py` habría creado una **fuente de verdad duplicada que el motor ignora**.

### C3-bis — El falso verde estructural de la prioridad 50

`_DEFAULT_PRIORITY = 50` en `services/context_enrichment.py`. Un bloque **no registrado** en `_BLOCK_PRIORITY` recibe **50 por accidente**. El test de v1 (`test_block_priority_is_below_criteria`, que comparaba una constante del propio módulo) **habría pasado en verde sin que nada estuviera cableado** — el falso verde perfecto: prueba una constante que el motor no consulta.

**Doble corrección:**
1. La prioridad se registra en **`_BLOCK_PRIORITY`**, la única fuente de verdad.
2. El valor es **45**, NO 50, precisamente para que sea **distinguible de `_DEFAULT_PRIORITY`**. Si el registro se olvida, `_block_priority` devuelve 50 y el test **falla**. Con 50 el test no puede distinguir "registrado" de "olvidado".
3. El test se corre **contra `_block_priority({"id": "harness-patterns"})`**, nunca contra una constante local.

### C16 — La afirmación de prioridades de v1 era falsa

v1 decía que la pista se poda "antes que criterios/contrato/grounding (>=75)". Mapa **real** de `_BLOCK_PRIORITY` (2026-08-01), con `_HIGH_PRIORITY_THRESHOLD = 75`:

| Bloque | Prioridad | | Bloque | Prioridad |
|---|---|---|---|---|
| `operator-corrections` | 110 | | `acceptance-contract` | 76 |
| `run-directive` | 105 | | **`acceptance-criteria`** | **74** |
| `ado-epic-structured` | 100 | | `filesystem-artifacts-status` | 70 |
| `client-profile` | 95 | | `glossary-auto` | 60 |
| `ado-blocker` | 90 | | `few-shot-approved` | 55 |
| `rejection-lessons` | 82 | | **`harness-patterns` (nuevo)** | **45** |
| `stacky-memory` | 80 | | `ado-similar-tickets` | 40 |
| `evolution-lessons` | 79 | | `ado-comments` | 30 |
| `modal_user_input` / `process-catalog` | 78 | | `ado-attachments` | 25 |
| `process-discipline` | 77 | | `operator_note` | 76 |

**Dos correcciones de hecho:** (a) **no existe** ningún bloque llamado `grounding`; (b) **`acceptance-criteria` vale 74, por debajo del umbral 75** — o sea los criterios de aceptación **también son podables**. La afirmación correcta es: *`harness-patterns` (45) se poda antes que todos los bloques de contrato, criterios y grounding-equivalentes, y antes también que `few-shot-approved` (55); solo sobrevive por encima de los bloques de contexto ADO barato (40/30/25).*

**Archivos a editar:**
- EDITAR `backend/services/context_enrichment.py` — agregar `"harness-patterns": 45` a `_BLOCK_PRIORITY` **y** el append del bloque dentro de `enrich_blocks`.
- EDITAR `backend/services/harness_learning.py` — agregar `build_pattern_hint_block`.
- EDITAR `backend/config.py` — las 3 keys.
- EDITAR `backend/services/harness_flags.py` — 3 `FlagSpec` + `_CATEGORY_KEYS` + `_CURATED_DEFAULTS_ON` para el bool.
- EDITAR `backend/.env.example`.

**Símbolos:**
```python
# services/harness_learning.py
HARNESS_PATTERN_BLOCK_ID = "harness-patterns"   # clave "id" del dict (NO "name")

def build_pattern_hint_block(*, project: str, agent_type: str, ticket_title: str,
                             ticket_type: str | None, max_patterns: int = 5,
                             min_confidence: float = 0.5) -> dict | None:
    """Devuelve un BLOQUE dict listo para blocks.append(), o None si no hay patrones."""
```

**Diff que de verdad compila, en `enrich_blocks`:**
```python
# --- F2: bloque de patrones aprendidos (hint podable, prioridad 45) ---
if config.HARNESS_LEARNING_INJECT_ENABLED:
    try:
        _hint = harness_learning.build_pattern_hint_block(
            project=_project_name, agent_type=agent_type,
            ticket_title=_ticket_title, ticket_type=_ticket_type,
            max_patterns=config.HARNESS_LEARNING_INJECT_MAX,
            min_confidence=config.HARNESS_LEARNING_INJECT_MIN_CONF,
        )
        if _hint:
            blocks.append(_hint)          # dict; la prioridad la resuelve _BLOCK_PRIORITY
    except Exception as _exc:             # nunca tumbar el camino caliente
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

### C9 — Presupuesto de costo del camino caliente (obligatorio)

`enrich_blocks` corre en **cada run de los 3 runtimes**. Reglas duras:
- `list_patterns` ejecuta **una sola query**, con `WHERE project=? AND scope=? AND status='active' AND confidence >= ?` y **`LIMIT max_patterns`**. Prohibido traer todas las observaciones y filtrar en Python.
- El bloque tiene **techo de caracteres** (`max_patterns` × ~200 chars).
- Sin patrones -> `None` -> **cero costo adicional**.

**Casos borde:** sin patrones -> `None`, no se agrega bloque; budget ajustado -> se poda antes que contrato/criterios; flag OFF -> `enrich_blocks` idéntico a hoy; excepción -> se loguea y el run sigue.

**Tests PRIMERO** — `backend/tests/test_harness_learning_inject.py` (**archivo nuevo**; registrar en los 2 ratchets):
1. `test_hint_block_lists_top_patterns_by_confidence` — con 8 patrones inyecta los 5 de mayor confianza.
2. `test_hint_block_filters_by_agent_and_ticket_kind`.
3. `test_no_patterns_returns_none` — `None`, no bloque vacío.
4. **`test_block_priority_is_registered_in_the_engine`** — `_block_priority({"id": "harness-patterns"}) == 45` **y** `!= _DEFAULT_PRIORITY`. *Anti-falso-verde C3-bis: si el registro se olvida, este test falla.*
5. **`test_block_priority_is_below_acceptance_criteria`** — `_block_priority({"id":"harness-patterns"}) < _BLOCK_PRIORITY["acceptance-criteria"]` (45 < 74), consultando el **mapa del motor**, no una constante local.
6. `test_block_shape_is_a_dict_with_id` — el bloque tiene claves `kind/id/title/content` y **no** es un objeto `Block`.
7. `test_flag_off_no_block` — flag OFF -> `enrich_blocks` no agrega `harness-patterns`.
8. **`test_list_patterns_runs_one_query`** — contando queries (o con `limit` observado), `build_pattern_hint_block` no escala con el nº de observaciones del proyecto. *Gate de C9.*
9. **`test_enrich_blocks_calls_the_builder`** — por AST o por spy: `context_enrichment` **referencia** `build_pattern_hint_block`. *Gate anti-"construido y jamás cableado".*

Y en `backend/tests/test_harness_flags.py` (ya registrado): `test_harness_learning_inject_flags_registered` — las 3 keys en `FLAG_REGISTRY` + `_CATEGORY_KEYS`, con tipos `bool`/`int`/`float`.

**Comando exacto:**
```powershell
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/venv/Scripts/python.exe" -m pytest "tests/test_harness_learning_inject.py" -q
```
**Criterio de aceptación BINARIO:** imprime **`9 passed`**, `0 failed`. Más el criterio **delta** sobre `test_harness_flags.py` (igual que F1).

**Flag + default:** `HARNESS_LEARNING_INJECT_ENABLED` (bool, **ON** — §4-bis); `HARNESS_LEARNING_INJECT_MAX` (int, 5); `HARNESS_LEARNING_INJECT_MIN_CONF` (float, 0.5).

**Impacto por runtime (medido):** `enrich_blocks` tiene **paridad real 3/3** — `agent_runner.py` (Copilot), `services/claude_code_cli_runner.py`, `services/codex_cli_runner.py`. *Ironía del v1: la fase que vendía paridad garantizada (F1) era la que no la tenía, y esta, que la tiene de verdad, no la reclamaba.*

**Trabajo del operador:** ninguno.
**Por qué NO viola regla 11:** es una pista explícitamente "no obligatoria"; no fuerza conducta ni decide. El título del bloque lo dice literalmente.
**Salvaguarda de calidad:** podable y de prioridad 45; nunca desplaza contrato ni criterios. Mide K3/K4.

---

## FASE F4 — Visibilidad para el operador (lectura + confirmar/descartar)

**Objetivo (1 frase):** mostrar los patrones aprendidos en la DiagnosticsPage existente, solo lectura más confirmar/descartar.

**Archivos a editar (rutas exactas — v1 usaba una elipsis ambigua):**
- EDITAR `backend/api/diag.py` — `GET /api/diag/harness-patterns?project=...`, `POST /api/diag/harness-patterns/<id>/dismiss`, `POST .../confirm`.
- EDITAR `backend/services/harness_health.py` — en `compute_health`/`by_project`, contadores `patterns_total`, `patterns_high_conf`, `repeated_failure_rate` (K1). Solo lectura.
- EDITAR **`frontend/src/pages/DiagnosticsPage.tsx`** (+ `DiagnosticsPage.module.css` si hace falta) — tarjeta `HarnessPatternsCard`. Sin librería nueva.

> **Riel de arquitectura:** `services/` **nunca** importa de `api/`. `harness_learning` no puede importar `api/diag.py`; la dependencia va en un solo sentido (`api/diag.py` -> `services/harness_learning.py`).

**`FlagSpec` — referencia canónica de los 4 flags (registrados en F1/F2, NO en F4):**
```python
FlagSpec(key="HARNESS_LEARNING_HARVEST_ENABLED", type="bool",
         label="Aprendizaje del arnés: cosechar (F1)",
         description="35.F1 — Post-run cosecha fallos/remedios como patrones. Pasivo, sin LLM.",
         group="contexto_memoria", default=True),
FlagSpec(key="HARNESS_LEARNING_INJECT_ENABLED", type="bool",
         label="Aprendizaje del arnés: reinyectar (F2)",
         description="35.F2 — Inyecta pistas de fallos conocidos (podables, prioridad 45).",
         group="contexto_memoria", default=True),
FlagSpec(key="HARNESS_LEARNING_INJECT_MAX", type="int",
         label="Máx. patrones por run",
         description="35.F2 — Cuántas pistas como máximo inyectar (default 5).",
         group="contexto_memoria", default=5),
FlagSpec(key="HARNESS_LEARNING_INJECT_MIN_CONF", type="float",
         label="Confianza mínima de pista",
         description="35.F2/F3 — Solo inyecta patrones con confidence >= este valor (default 0.5).",
         group="contexto_memoria", default=0.5),
```

### C6 — El grupo nuevo rompía un gate existente

v1 declaraba `group="harness_learning"`. En `services/harness_flags.py` hay un comentario literal: *"toda flag nueva debe agregarse también a `_CATEGORY_KEYS` (arriba) o el test `test_every_registry_flag_is_categorized` rompe CI a propósito (Plan 63)"*. v1 **no menciona `_CATEGORY_KEYS` ni `FLAG_CATEGORIES` en ninguna fase** -> implementarlo tal cual deja **el CI rojo**. Además `harness_learning` no existe como grupo hoy.

**Decisión v2 — reusar, no crear:** se usa la categoría **`contexto_memoria`**, que ya existe y cuyo `CategorySpec` se describe como *"Qué información recibe el agente: presupuesto/dedup/rerank de contexto, memoria colaborativa, skills, few-shot, catálogo"* — encaje semántico exacto. **Trabajo concreto:** agregar las 4 keys a la tupla `_CATEGORY_KEYS["contexto_memoria"]` en `services/harness_flags.py`. **No** se crea un `CategorySpec` nuevo, con lo que no se toca el orden ni el tiering del panel.

**Pseudocódigo de los endpoints:**
```
GET /api/diag/harness-patterns?project=P
    patterns = harness_learning.list_patterns(P, min_confidence=0.0, limit=200)
    -> [ {..., "id": memory_id} ] ordenado por confidence desc
POST .../<id>/dismiss : memory_store.set_status(id, "rejected") -> 200 | 404   # C17
POST .../<id>/confirm : memory_store.set_status(id, "active")   -> 200 | 404
```

**Casos borde:** proyecto sin patrones -> lista vacía, la tarjeta muestra "sin patrones aún"; id inexistente -> `set_status` devuelve `False` -> **404**; flags OFF -> la tarjeta se muestra vacía y los endpoints siguen siendo lectura/estado.

**Tests PRIMERO** — `backend/tests/test_harness_learning_api.py` (**archivo nuevo**; registrar en los 2 ratchets):
1. `test_list_endpoint_returns_patterns_sorted` — orden por confidence desc.
2. `test_dismiss_sets_status_rejected` — y luego `list_patterns` lo excluye.
3. `test_confirm_reactivates_pattern`.
4. `test_dismiss_unknown_id_returns_404`.
5. `test_endpoints_never_mutate_tickets_or_publish` — se asserta que ningún publisher/tracker fue invocado. *Gate de regla 11.*

En `backend/tests/test_harness_flags.py` (ya registrado): `test_harness_learning_group_complete` — las **4** keys en `FLAG_REGISTRY` con tipos `bool/bool/int/float` **y** presentes en `_CATEGORY_KEYS`.
En `backend/tests/test_harness_health.py` (**ya registrado en ambos ratchets** — verificado): `test_health_reports_pattern_counts`.

**Comando exacto:**
```powershell
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/venv/Scripts/python.exe" -m pytest "tests/test_harness_learning_api.py" -q
& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/venv/Scripts/python.exe" -m pytest "tests/test_harness_health.py" -q
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend" ; npx tsc --noEmit
```

**Criterio de aceptación BINARIO:** `test_harness_learning_api.py` imprime **`5 passed`**; `tsc` termina con **0 errores** (vitest/RTL no están instalados de forma confiable: el gate real del frontend es `tsc`); criterio **delta** en `test_harness_flags.py` y `test_harness_health.py`.

**Flag + default:** los 4 de arriba. La tarjeta es **siempre de lectura**; los botones cambian el estado de un patrón, nunca lanzan acciones sobre el tracker ni sobre runs.
**Impacto por runtime:** ninguno (observabilidad).
**Trabajo del operador:** ninguno obligatorio; confirmar/descartar es un click opcional.
**Por qué NO viola regla 11:** lectura + cambio de estado de una *pista*. Ninguna acción decide trabajo, publica ni transiciona work items. El test 5 lo fija como contrato.

---

## 5. Mecanismos transversales (resumen)

- **Cosecha pasiva (F1):** post-hook en `on_execution_end` (3/3 runtimes); lee metadata **ya persistida**; el chokepoint absorbe excepciones.
- **Persistencia reusada (F0):** `memory_store`, `scope="harness_pattern"`, `type="pattern"`, `confidence` nativo, `occurrences` = `revision_count`. Cero tabla nueva.
- **Reinyección podable (F2):** dict con `"id": "harness-patterns"`, prioridad **45** registrada en `_BLOCK_PRIORITY`; una sola query acotada.
- **Confianza + decay (F3):** half-life 30 días; 1 ocurrencia = 0.2 (no inyecta), 3 = 0.6 (inyecta); `rejected` manda.
- **Visibilidad (F4):** DiagnosticsPage + `harness_health`; confirmar/descartar como única interacción.

---

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Una pista aprendida sesga al agente hacia un error pasado. | Hint "no obligatorio", prioridad 45 podable, nunca pisa contrato/criterios; decay lo apaga; el operador lo descarta de por vida. |
| La cosecha rompe o ralentiza el run. | Post-hook envuelto por `_run_post_hooks` (try/except del propio chokepoint); flag OFF -> `return 0` inmediato. |
| **La inyección degrada el camino caliente de los 3 runtimes.** | Una query con `LIMIT`, filtro en SQL, techo de chars, `None` si no hay patrones. Test 8 de F2 lo fija. |
| Un patrón filtra un secreto. | `redact_secrets` (símbolo real) incondicional antes de persistir; testeado contra el `_MASK`. |
| **Contamina la memoria de dominio.** | **No se materializa, y está verificado:** la inyección usa una **allowlist** `INJECT_SCOPES = ("project","team","global")`; `harness_pattern` queda fuera por construcción. Igual se fija con el test 6 de F0, porque hoy es un *default* y nada impide que un llamador amplíe `inject_scopes`. |
| **El módulo se construye, pasa tests y nunca se cablea.** | Hay precedentes recientes en este repo. Gate: tests 16 (F1) y 9 (F2) exigen el **consumidor de producción**. |
| Asimetría entre runtimes. | Seams verificados 3/3 (`on_execution_end`, `enrich_blocks`), no asumidos. |
| Ruido de patrones de baja señal. | `min_confidence` 0.5 + `max` 5 + decay + descarte del operador. |

---

## 7. Fuera de scope

- **Aplicar un remedio automáticamente** (re-prompt forzado, parche auto): choca con regla 11.
- **Aprendizaje cross-proyecto:** los patrones son por-proyecto.
- **Clasificación de `ticket_kind` por LLM:** heurística stdlib; subir solo con evidencia.
- **Editor visual de patrones** más allá de lista + confirmar/descartar.
- **Borrado físico de patrones rancios:** decay + `rejected` los neutralizan sin borrar.
- **Huella de regresión en `docs/sistema/error_fingerprints.json`:** no se agrega en esta iteración (no hay un modo de fallo estable que registrar hasta tener F1 corriendo en vivo). Reevaluar tras la primera semana con `HARVEST_ENABLED=ON`.

---

## 8. Glosario

- **Arnés (harness):** capa que envuelve cada ejecución (gate, repair, verificación, telemetría) — `backend/harness/`.
- **Señal de verificación:** dato que el arnés produce al verificar un entregable.
- **Patrón (HarnessPattern):** agregación de una señal recurrente en un contexto (proyecto + agente + tipo de ticket).
- **Harvest:** leer las señales de un run terminado y persistirlas. Pasivo.
- **Reinyección (hint):** pista corta de fallos conocidos en el próximo run. Podable.
- **Repair:** pase correctivo dentro del run (`harness/run_repair.py`, `criteria_repair.py`, `exec_repair.py`).
- **`on_execution_end` / `register_post_hook`:** el chokepoint post-run **real** de los 3 runtimes, en `services/ticket_status.py`. **Corrige el glosario de v1**, que atribuía ese rol a `finalize_run` (1 de 3).
- **`finalize_run`:** decide el verdict post-run **solo en Codex CLI** (`harness/post_run.py`). **No** es un seam de paridad.
- **`enrich_blocks`:** seam de armado de contexto, **sí** común a los 3 runners (`services/context_enrichment.py`).
- **`memory_store` / scope:** store de la memoria colaborativa; `scope` particiona observaciones. `INJECT_SCOPES` es **allowlist**.
- **Regla 11 / human-in-the-loop:** Stacky amplifica al operador, nunca lo reemplaza.
- **Falso verde:** test que pasa sin que la funcionalidad exista (p. ej. comparar una constante local que el motor no consulta).

---

## 9. Orden de implementación y CORTE en 2 tandas

**Orden (dependencias):** F0 -> F1 -> F3 -> F2 -> F4. Es el mismo de v1 y es correcto: F3 precede a F2 porque F2 no debe inyectar sin filtro de confianza.

### C20 — El plan es demasiado grande para una sola tanda

Toca 8 archivos de producción, 3 de test nuevos, 3 ya existentes, 2 ratchets, `config.py`, `.env.example` y el frontend. **Corte explícito, sin cambiar el número ni partir el archivo:**

- **TANDA A — "cosechar en sombra" (F0 + F1 + F3).** Deja el sistema **acumulando patrones sin inyectar nada**. Riesgo cercano a cero: no toca el camino caliente ni el prompt. Permite medir **K2** con datos reales antes de decidir el resto. Cierra con `tests/test_harness_learning.py` en **`23 passed`** y el hook cableado en `app.py`.
- **TANDA B — "inyectar y mostrar" (F2 + F4).** Solo se arranca **con evidencia de la Tanda A** (que existan patrones con `confidence >= 0.5`). Si la Tanda A no produjo patrones, la Tanda B **no se implementa**: se investiga primero por qué la cosecha vino vacía (probable señal de que los extractores de F1.0 apuntan a claves que ese runtime no escribe).

> **Rollout:** `HARVEST_ENABLED` nace ON y acumula. `INJECT_ENABLED` nace ON pero es **inerte hasta que un patrón llega a 3 ocurrencias** (F3), así que el encendido es gradual por construcción, no por configuración.

---

## 10. Definición de Hecho (DoD global)

- [ ] Cada flag está en **`config.py`** (default efectivo) **y** `FLAG_REGISTRY` **y** `_CATEGORY_KEYS` **y** `_CURATED_DEFAULTS_ON` (para los `default=True`) **y** `.env.example` **y** su test — **en la misma fase que lo introduce**. Aparece en `HarnessFlagsPanel` sin tocar frontend.
- [ ] Los defaults siguen la regla vigente: **ON salvo justificación escrita por categoría (A) o (B)**. La justificación está en §4-bis, ítem por ítem.
- [ ] **Paridad verificada por conteo de llamadores, no declarada:** harvest vía `on_execution_end`/`register_post_hook` (**3/3**), reinyección vía `enrich_blocks` (**3/3**). Prohibido reintroducir la afirmación de que `finalize_run` es común a los 3 (es **1/3**).
- [ ] **Cableado real:** `app.py` registra el post-hook y `context_enrichment` referencia al builder — con test que lo verifica por AST. Ningún módulo queda construido-y-nunca-cableado.
- [ ] Con los flags en **OFF**, `enrich_blocks` produce el mismo conjunto y orden de bloques que hoy, y el harvest no escribe nada (tests de control verdes).
- [ ] Cero tabla nueva, cero migración, cero dep npm/py, cero FTS5.
- [ ] Secretos redactados con `redact_secrets` antes de persistir (test verde contra `"***REDACTED***"`).
- [ ] Harvest best-effort: nunca propaga excepción al run.
- [ ] Reinyección podable en **45**, registrada en `_BLOCK_PRIORITY`, verificada **contra `_block_priority`** y no contra una constante local.
- [ ] `scope="harness_pattern"` **no** entra a `get_context_for_run` (test verde).
- [ ] Costo del camino caliente acotado: una query con `LIMIT` (test verde).
- [ ] Toda interacción del operador es opcional y de lectura/estado; ninguna publica ni transiciona work items.
- [ ] Tests **por archivo** con `backend/venv` (py3.11.9). Cada criterio cita el **conteo `N passed`**. En archivos con rojos preexistentes, criterio **delta**.
- [ ] Los 3 archivos de test nuevos están registrados en **los DOS ratchets** (§12).
- [ ] `tsc --noEmit` en 0.
- [ ] KPIs K1-K5 expuestos por `harness_health`/`api/diag.py` en la DiagnosticsPage existente.

---

## 11. Decisiones abiertas (confirmación del operador)

1. **Defaults ON de las dos booleanas** (§4-bis): la regla vigente los exige ON y la justificación está escrita. **Confirmar** que el operador acepta que el aprendizaje quede activo desde el merge (recordando que la inyección es inerte hasta 3 ocurrencias).
2. **Half-life de 30 días** (F3): ¿adecuada al ritmo de los proyectos?
3. **Corte en 2 tandas** (§9): ¿se implementa la Tanda A sola y se decide la B con datos, o se pide todo junto?
4. **Granularidad de `ticket_kind`:** heurística `bug/feature/task/unknown`, ¿alcanza?

---

## 12. [ADICIÓN ARQUITECTO 2] — Gate anti-"construido y jamás cableado" + registro en ratchets

**El problema real que ataca:** en este repo hay precedentes recientes de módulos **construidos, testeados, en verde y jamás cableados**. El gate de "implementado" **no es "existe el símbolo"**, es **"existe un consumidor de producción"** (excluyendo `tests/`, el propio módulo y los baselines de ratchet). Con mocks, toda la suite de este plan puede quedar verde **sin que una sola línea corra en un run real**.

**Gate obligatorio (2 tests, ya listados como F1.16 y F2.9):**
```python
# Parsea el archivo por AST y exige la llamada real, no un import.
def test_hook_is_registered_in_app():
    tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
    assert any(... "harness_learning" ... "register" ...), \
        "F1 no está cableada: app.py no registra el post-hook"
```
Se verifica **por AST y no por `grep`**, porque un `grep` cuenta también comentarios y strings; y se ancla **por símbolo** (`harness_learning` + `register`) y no por línea.

**Registro en los DOS ratchets (C15):** un archivo de test nuevo debe declararse en `backend/scripts/run_harness_tests.ps1` **y** `backend/scripts/run_harness_tests.sh`, que tienen **sintaxis distinta** y **no admiten rutas con espacios** (estas no las tienen):

| Archivo nuevo | En `run_harness_tests.ps1` | En `run_harness_tests.sh` |
|---|---|---|
| `tests/test_harness_learning.py` | `  "tests/test_harness_learning.py",` | `  tests/test_harness_learning.py` |
| `tests/test_harness_learning_inject.py` | `  "tests/test_harness_learning_inject.py",` | `  tests/test_harness_learning_inject.py` |
| `tests/test_harness_learning_api.py` | `  "tests/test_harness_learning_api.py",` | `  tests/test_harness_learning_api.py` |

**Decisión de reuso (para no inflar el trámite):** los tests de **flags** van en `backend/tests/test_harness_flags.py` y los de **salud** en `backend/tests/test_harness_health.py`, **ambos ya registrados en los dos ratchets** (verificado 2026-08-01). Así el plan pasa de **4 archivos nuevos (v1)** a **3**, y ninguno de los tests de flags/health necesita trámite de ratchet.

---

## 13. Resumen de los defectos de v1 corregidos (trazabilidad)

| ID | Severidad | Defecto de v1 | Dónde se corrige |
|---|---|---|---|
| C1 | BLOQUEANTE | `finalize_run` declarado seam de los 3 runtimes; es **1 de 3** | F1 (seam nuevo), §Principios 1, Glosario, DoD |
| C2 | BLOQUEANTE | El diff de F1 no compila contra la firma real; `metadata_patch` sin fusionar | F1 (pseudocódigo nuevo) |
| C3 | BLOQUEANTE | `Block(name=,priority=,text=)` no existe; prioridad 50 = falso verde | F2 (dict + `_BLOCK_PRIORITY` + 45) |
| C4 | BLOQUEANTE | Comandos apuntan a `backend/.venv` (py3.13.5, roto) | Comando base + las 5 fases |
| C5 | BLOQUEANTE | 4 flags en OFF contra la regla vigente | §4-bis |
| C6 | BLOQUEANTE | Grupo nuevo sin `_CATEGORY_KEYS` -> CI rojo | F4 / C6 |
| C7 | BLOQUEANTE | `persist_pattern` omite el `type=` obligatorio -> `TypeError` | F0 |
| C8 | IMPORTANTE | `occurrences`/`confidence` a mano en el JSON | F0 (columnas nativas) |
| C9 | IMPORTANTE | Costo por run no acotado en el camino caliente | F2 / C9 + test |
| C10 | IMPORTANTE | "Detector de secretos de la memoria colaborativa" no existe | F0 (`redact_secrets`) |
| C11 | IMPORTANTE | Sin gate de consumidor de producción | §12 |
| C12 | IMPORTANTE | 10 anclajes desviados/off-by-one | Todo el doc, re-anclado por símbolo |
| C13 | IMPORTANTE | Criterio insatisfacible sobre `test_harness_flags.py` | F1/F2/F4 (criterio delta) |
| C14 | IMPORTANTE | Criterios sin conteo (`-k` sin match da exit 0) | Todos los criterios |
| C15 | IMPORTANTE | 4 archivos de test nuevos sin registro en ratchets | §12 |
| C16 | MENOR | "grounding >=75" falso; `acceptance-criteria` es 74 | F2 / C16 |
| C17 | MENOR | `status="dismissed"` fuera de `ALL_STATUSES` | F3 (`"rejected"`) |
| C19 | — | Riesgo de contaminación: **verificado que NO se materializa** | F0 test 6 + §6 |
| C20 | MENOR | Tamaño excesivo para una tanda | §9 (corte A/B) |
