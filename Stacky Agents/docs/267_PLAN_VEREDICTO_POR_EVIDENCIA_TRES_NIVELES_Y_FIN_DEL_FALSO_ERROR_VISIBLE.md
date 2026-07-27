# Plan 267 — Veredicto por evidencia: tres niveles y fin del falso error VISIBLE

> **Estado:** PROPUESTO v1
> **Autor:** StackyArchitectaUltraEficientCode
> **Fecha:** 2026-07-27
> **Depende de:** Plan 254 (IMPLEMENTADO, commit `92e593f2`). Este plan **se apoya** en 254, **no lo reemplaza** ni lo duplica.
> **Numeración:** verificada con `ls "Stacky Agents/docs"` — el máximo era 266 (con colisión: existen `266_PLAN_CATALOGO_UNICO_DE_ACCIONES_DEVOPS_...md` y `266_PLAN_CERO_PANTALLA_ROTA_EN_EL_COMPARADOR_DE_BD_...md`). **267 estaba libre.**

---

## 1. Objetivo e impacto

### Objetivo

El plan 254 clasificó **por qué terminó** una corrida mirando únicamente señales del **proceso** (código de salida, watchdog, reaper, marcadores de cuota). Este plan agrega la dimensión que falta y que el operador pidió textualmente: **si el proceso produjo resultados y cumplió su objetivo**. Para eso introduce una capa PURA de **veredicto por evidencia** que combina el `outcome_reason` ya existente con un conjunto de **señales de evidencia read-only** (entregable en disco, comentario publicado en el tracker, commit/PR abierto, gate de aceptación, verificación de ejecución) y produce un veredicto de **tres niveles** — **éxito / advertencia / error real** — con su causa y con la **lista explícita de evidencias presentes, ausentes y desconocidas**, para que el operador vea POR QUÉ. Ese veredicto se propaga a la **fila** de las listas (no solo al drawer de detalle), con filtro por nivel, y la reconciliación de 254 F5 deja de ser un contador mudo: pasa a ofrecer al humano un camino HITL para corregir un falso rojo concreto.

**El veredicto NUNCA cambia un estado por su cuenta.** Es una **dimensión separada** del `stacky_status`: se calcula **en tiempo de lectura**, no escribe una sola fila, y tiene un invariante duro codificado en test — **un run cuyo estado es `error` jamás puede recibir veredicto `exito`**, con ninguna combinación de evidencia. La única forma de convertir un rojo en verde sigue siendo un click del operador.

### KPI / impacto esperado

> **Anti-alucinación:** no se inventa el valor "hoy". La columna "hoy" se **mide** ejecutando el comando indicado **antes de tocar una línea** (paso 0 de F0) y se anota en este mismo documento. Un plan que declare un número sin haberlo corrido está mintiendo.

| # | KPI | Hoy (medir en F0 paso 0) | Meta | Cómo se mide (comando exacto) |
|---|---|---|---|---|
| K1 | Corridas terminadas en `error` que SÍ tienen evidencia de entrega (el falso error visible) | `SIN MEDIR` | Visible al 100% con veredicto `advertencia` + causa `falso_rojo_probable`, y **0** de ellas presentadas al operador como un rojo plano | `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -c "import run_verdict_kpi"` — implementado en F8 como `services/run_verdict.py::count_by_level(days=30)` |
| K2 | Degradaciones `completed`→`error` en 30 días (KPI heredado del 254) | `SIN MEDIR` | No sube (este plan no toca el cierre) | `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -c "from services.error_fingerprints import count_falso_rojo_downgrades; print(count_falso_rojo_downgrades(30))"` — función real en `backend/services/error_fingerprints.py:50` |
| K3 | Niveles visibles en la **fila** de una lista de corridas | **1 dimensión** (`status` crudo vía `runStatusTone`, `frontend/src/pages/ExecutionHistoryPage.tsx:633`) | **2 dimensiones**: estado + veredicto de 3 niveles | Lectura del archivo: `grep -c "verdictTone" frontend/src/pages/ExecutionHistoryPage.tsx` ≥ 1 |
| K4 | Items de reconciliación con camino HITL desde la UI | **0** (`RunReconciliationCard.tsx` renderiza solo contadores por `by_kind`, líneas 94-102; nunca renderiza `items`) | 100% de los items `red_with_delivered_work` con botón de corrección | `grep -c "items.map" frontend/src/components/RunReconciliationCard.tsx` ≥ 1 |
| K5 | Colectores de evidencia que pueden colgar una request | **N/A (no existen)** | **0**: todo colector tiene tope de tiempo y degrada a `None` (desconocido) | `.venv\Scripts\python.exe -m pytest tests/test_plan267_run_evidence.py -v` (test `test_colector_lento_degrada_a_desconocido`) |

---

## 2. Por qué ahora / el gap que cierra

El plan 254 dejó construido y **verificado en el árbol** (leído para este documento, no recordado):

- `backend/services/run_outcome.py` — módulo PURO con `OUTCOME_REASONS` (9 reasons, líneas 13-23), `classify_outcome_reason(...)` (línea 55) con orden de precedencia numerado en el docstring (líneas 71-83), `is_operator_actionable(reason)` (línea 104), `outcome_reason_to_status(reason)` (línea 113) → `{completed, needs_review, error}` vía `_REASON_TO_STATUS` (líneas 34-44).
- `backend/services/run_reconciliation.py` — chequeo read-only estado-vs-evidencia con `DISCREPANCY_KINDS` (línea 28), `evaluate()` PURA (línea 72), `scan_recent()` (línea 168) y `summarize()` (línea 217).
- `backend/services/status_vocabulary.py` — `TERMINAL_STATUSES` (línea 11), `NON_TERMINAL_TICKET_STATUSES` (línea 14), `VALID_TICKET_STATUSES` (línea 18).
- `backend/services/ticket_status.py` — `set_status(...)` con `guard_downgrade: bool = False` (línea 152) y la marca `blocked_downgrade` (línea 183); `on_execution_end(...)` (línea 293) que activa el guard leyendo `STACKY_TICKET_STATUS_NO_DOWNGRADE_ENABLED` (líneas 341-342).
- `frontend/src/utils/outcomeReason.ts` — `OutcomeTone` (línea 12), `OUTCOME_REASON_LABELS` (línea 22), `describeOutcomeReason()` (línea 62), `dirtyCloseNotice()` (línea 86).
- Tests: `backend/tests/test_plan254_falso_rojo.py`, `test_plan254_outcome_reason.py`, `test_plan254_reconciliation.py`, `test_plan254_stream_drain.py` (los 4 registrados en el arnés, ver §3.7).

### Los 3 gaps — VERIFICADOS uno por uno contra el árbol

**GAP 1 — CONFIRMADO. `classify_outcome_reason` no consulta evidencia de entregable.**
Su firma completa (`backend/services/run_outcome.py:55-65`) acepta exactamente 8 parámetros: `return_code`, `result_ok_seen`, `stall_fired`, `stderr_excerpt`, `last_result_text`, `ticket_already_terminal`, `reaper_kind`, `preflight_block`. **Ninguno** es evidencia de entregable: no hay artefactos en disco, ni comentario publicado, ni commit/PR, ni gate de aceptación. Los 4 call-sites reales confirman que solo se le pasan señales de proceso: `agent_runner.py:1117`, `services/agent_completion.py:67`, `services/codex_cli_runner.py:755`, `services/claude_code_cli_runner.py:1865`. El más elocuente es `agent_completion.py:66-71`, que **sintetiza** `return_code=0 if payload.status == "completed" else 1` — es decir, en el camino de auto-reporte el "código de salida" es una ficción derivada de lo que el propio agente dijo. **Diagnóstico del orquestador: correcto.**

**GAP 2 — CONFIRMADO, y peor de lo enunciado.** `frontend/src/utils/outcomeReason.ts` tiene exactamente **dos** consumidores en todo el frontend: `components/ExecutionDetailDrawer.tsx:18` (el drawer) y su propio test `utils/__tests__/plan254OutcomeReason.test.ts:6`. **Ninguna lista lo importa.** Además:
- `pages/ExecutionHistoryPage.tsx:633` pinta la fila con `runStatusTone(item.status)` / `runStatusLabel(item.status)` de `utils/runStatus.ts`, que mapea el status crudo a 5 tonos (`"success" | "warning" | "danger" | "info" | "neutral"`, `utils/runStatus.ts:1`) — **una sola dimensión**, sin causa ni evidencia.
- `pages/TicketBoard.tsx` no tiene módulo puro de estado: los colores son un dict inline `ADO_STATE_COLORS` (`pages/TicketBoard.tsx:82`) y un helper local no exportado `stateColor()` (`pages/TicketBoard.tsx:103`), pintados con estilo inline en `pages/TicketBoard.tsx:496-499`.
- `pages/IncidentInboxPage.tsx:503` dibuja `item.ado_state` como badge crudo, sin tono.

**GAP 3 — CONFIRMADO.** `backend/services/run_reconciliation.py` es read-only por diseño explícito (docstring líneas 7-13: *"No cambia ningún estado. No reintenta, no publica, no decide. Lista."*) y su `summarize()` (línea 217) **sí** devuelve `items` con `execution_id`/`ticket_id`/`kind`/`detail`. Pero la UI **tira esa lista a la basura**: `frontend/src/components/RunReconciliationCard.tsx` solo itera `report.by_kind` (líneas 95-101) para mostrar contadores. `items` **nunca se renderiza** y no hay ningún botón de acción. El operador sabe que hay 7 falsos rojos y no tiene forma de tocar ninguno.

### Corrección al diagnóstico recibido

El brief del orquestador indicaba que el dueño del desenlace de Copilot vive en `agent_runner.py:1015/1040/1067`. **Las líneas reales hoy son `agent_runner.py:1029`, `:1055` y `:1082`** (los tres `_ts.on_execution_end(...)` con `final_status="completed"`, `"cancelled"` y `"error"` respectivamente). Lo que **sí** se confirma literalmente es que `backend/copilot_bridge.py` tiene **0 ocurrencias** de `final_status` (`grep -c final_status copilot_bridge.py` = 0), tal como lo documenta el propio comentario en `agent_runner.py:1104`. Se corrige el anclaje aquí para que nadie implemente contra la línea equivocada.

**Consecuencia arquitectónica de ese dato:** este plan **no toca ningún sitio de cierre**. El veredicto se calcula **en tiempo de lectura** (cuando se sirve el payload), no en el cierre. Por eso la paridad de los 3 runtimes es **estructural, no negociada**: los tres escriben `AgentExecution`, y de ahí lee el veredicto. Ver §4, principio P3.

---

## 3. Evidencia real (anclaje anti-alucinación)

Toda ruta es relativa a `Stacky Agents/`. Todo símbolo fue abierto y leído.

### 3.1 Módulos del 254 que se REUSAN (no se reescriben)

| Símbolo | Ubicación | Qué aporta al 267 |
|---|---|---|
| `OUTCOME_REASONS` (9 tuplas) | `backend/services/run_outcome.py:13` | Entrada del veredicto |
| `outcome_reason_to_status(reason)` | `backend/services/run_outcome.py:113` | Deriva el **nivel base** del veredicto |
| `is_operator_actionable(reason)` | `backend/services/run_outcome.py:104` | Ya expuesto en el payload (`api/executions.py:85`) |
| `VALID_TICKET_STATUSES` | `backend/services/status_vocabulary.py:18` | Vocabulario congelado; **el 267 NO agrega estados** |
| `DISCREPANCY_KINDS` / `summarize()` | `backend/services/run_reconciliation.py:28` / `:217` | Base del HITL de F6 |
| `OutcomeTone` | `frontend/src/utils/outcomeReason.ts:12` | Tipo de tono **reusado**, no redefinido |
| `describeOutcomeReason()` | `frontend/src/utils/outcomeReason.ts:62` | Etiqueta de la causa en el drawer |

### 3.2 Fuentes de evidencia — todas existen y todas son de solo lectura

| Señal | Fuente verificada | Anclaje |
|---|---|---|
| `entregable_presente` | Columna `AgentExecution.html_output_path` (String 500) y columna `AgentExecution.output` (Text) | `backend/models.py:272` y `backend/models.py:258` |
| `publicado_en_tracker` | Tabla `agent_html_publish`, modelo `AgentHtmlPublish` con `execution_id` (`:135`), `status` ∈ `ok/skipped/failed` (`:144`) y `comment_id` (`:153`) | `backend/services/ado_publisher.py:122-154` |
| `cambio_en_repo` | Sidecar JSON por ejecución leído con `get_intent(execution_id)`; campos escritos por `mark_intent(...)`: `pr_id, pr_url, branch, status, error, files_committed, origin` | `backend/services/incident_dev_pr.py:213` (lector), `:223-228` (escritor, docstring con los campos), `:199` (ruta `data_dir()/incident_dev_pr/{execution_id}.json`) |
| `gate_aceptacion_ok` | Columna `AgentExecution.contract_result_json` + property `contract_result` | `backend/models.py:261` y `backend/models.py:309` |
| `verificacion_ok` | Clave dentro de `AgentExecution.metadata_json` (property `metadata_dict`) | `backend/models.py:301`; el productor es `services/exec_verification.py::verify()` (`:522`) que serializa con `_serialize_report()` (`:642`) |

### 3.3 Metadata de ejecución ya poblada por el 254 (se lee, no se escribe)

`run_reconciliation.scan_recent()` demuestra qué claves existen en `AgentExecution.metadata_dict`: `exit_code` (`backend/services/run_reconciliation.py:195`), `finalized_after_result` (`:202`), `outcome_reason` (`:209`), `drain_timed_out` (`:212`).

### 3.4 Punto de inyección del payload de ejecuciones

`backend/api/executions.py:65` — `_with_outcome(d, dirty_ids)` es la función que ya promueve `outcome_reason` (`:81`) y `outcome_actionable` (`:85`) al nivel superior del payload, gateada por `_outcome_badge_enabled()` (`:28`). El patrón anti-N+1 ya existe: `_dirty_close_execution_ids(session, execution_ids)` (`:35`) resuelve **todo el lote en UNA query** (`:48-53`). **F2 sigue exactamente ese patrón.**

### 3.5 Superficies de UI

| Superficie | Archivo:línea | Qué hay hoy |
|---|---|---|
| Fila del historial de ejecuciones | `frontend/src/pages/ExecutionHistoryPage.tsx:633` | `<StatusChip tone={runStatusTone(item.status)}>` |
| Filtro de estado del historial | `frontend/src/pages/ExecutionHistoryPage.tsx:400-401` | select por `filters.status` |
| Import de `runStatus` | `frontend/src/pages/ExecutionHistoryPage.tsx:30` | `runStatusTone, runStatusLabel` |
| Fila de la bandeja de incidencias | `frontend/src/pages/IncidentInboxPage.tsx:488` | `<div className={styles.row}>`; badges en `:503-507` |
| Endpoint de la bandeja | `backend/api/incident_inbox.py:160-164` | Arma `items` desde `t.to_dict()`; comentario explícito en `:149`: *"Sin N+1: NO se consulta AgentExecution"* |
| Card de reconciliación | `frontend/src/components/RunReconciliationCard.tsx:94-102` | Solo `by_kind`; `items` sin usar |
| Cliente HTTP de reconciliación | `frontend/src/api/endpoints.ts:3167-3175` | `RunReconciliation.get()` con `fetch` crudo (no `api.get`, porque lanza en non-2xx) |
| Drawer de detalle | `frontend/src/components/ExecutionDetailDrawer.tsx:80` y `:85` | Ya consume `describeOutcomeReason` y `dirtyCloseNotice` |

### 3.6 Endpoint HITL que se REUSA (y el que está PROHIBIDO usar)

- **SE USA:** `PATCH /api/tickets/<int:ticket_id>/stacky-status` — `backend/api/tickets.py:1165`. Su cuerpo es `{ "status": ..., "reason": ... }` (`:1169-1170`), toma el usuario de `X-User-Email` (`:1178`) y llama **directamente** `ts.set_status(...)` (`:1189-1194`) **sin** `guard_downgrade` (queda en su default `False`, `services/ticket_status.py:152`) y **sin** publicar nada ni correr post-hooks.
- **PROHIBIDO:** `PATCH /api/tickets/by-ado/<int:ado_id>/stacky-status` — `backend/api/tickets.py:1204`. Ese camino **SÍ publica en ADO** (`backend/api/tickets.py:1406` `publish.succeeded`) y **SÍ puede cambiar el estado del work item en ADO** (`:1495` `ado state changed`). Usarlo convertiría una corrección local en una escritura en el tracker real del operador. **Un modelo menor NO debe confundir estos dos endpoints.**

### 3.7 Receta REAL de alta de flag (verificada, no recordada) — "RECETA-FLAG"

Toda flag nueva se da de alta en **5 lugares de código + 2 archivos de arnés**. Saltarse cualquiera deja un test ROJO.

| # | Archivo | Qué agregar | Anclaje del patrón a copiar |
|---|---|---|---|
| 1 | `backend/config.py` | `STACKY_X: bool = os.getenv("STACKY_X", "true").lower() in ("1", "true", "yes")` | `backend/config.py:2072-2073` |
| 2 | `backend/services/harness_flags.py` | Un `FlagSpec(key=..., type="bool", label=..., description=..., group="global", default=True)` en el registro | `backend/services/harness_flags.py:5213-5224` |
| 3 | `backend/services/harness_flags.py` | La key dentro de la tupla de la categoría en `_CATEGORY_KEYS` (dict declarado en `:120`) | `backend/services/harness_flags.py:324` (categoría `observabilidad_notif`) |
| 4 | `backend/services/harness_flags_help.py` | Una entrada `PlainHelp(what=..., on_effect=..., off_effect=..., example=...)` en el dict `PLAIN_HELP` | `backend/services/harness_flags_help.py:1789-1794` |
| 5 | `backend/tests/test_harness_flags.py` | La key dentro del set `_CURATED_DEFAULTS_ON` | `backend/tests/test_harness_flags.py:520-523` |
| 6 | `backend/scripts/run_harness_tests.sh` | La ruta del test nuevo, **sin comillas y sin coma**, dentro del array bash | `backend/scripts/run_harness_tests.sh:849-852` |
| 7 | `backend/scripts/run_harness_tests.ps1` | La ruta del test nuevo, **con comillas dobles y con coma** (salvo el último elemento), dentro del array PowerShell | `backend/scripts/run_harness_tests.ps1:762-765` |

**Topes duros del texto de `PlainHelp`** (test real `backend/tests/test_harness_flags_help.py:47-50`):
- `what` ≥ 10 y ≤ **200** caracteres.
- `on_effect` ≤ **240** caracteres.
- `off_effect` ≤ **240** caracteres.

**Regla dura sobre `requires`:** **ninguna** flag de este plan declara `requires=`. Motivo verificado: `backend/tests/test_harness_flags_requires.py:316` compara el mapa **completo** por igualdad (`assert actual == _REQUIRES_MAP_FROZEN`, mapa congelado en `:120`), así que declarar un `requires` obliga a editar también ese archivo o el test queda rojo. Las dependencias entre flags de este plan se resuelven **en código** (una función lee las dos flags), no en el registro. Ver F2 paso 3.

### 3.8 Gotchas del repo que este plan respeta

1. **Tests de backend por archivo.** `SQLITE_LOCKED` bajo pytest con shared cache es flaky. Cada comando de aceptación de este plan nombra **un solo archivo**.
2. **`@testing-library/react` y `jsdom` NO están instalados** (`frontend/package.json` devDependencies: solo `@types/react`, `@types/react-dom`, `@vitejs/plugin-react`, `typescript`, `vite`, `vitest@^4.1.9`). Toda lógica de UI de este plan va en módulos `.ts` **puros**; el render NO se testea.
3. **Vitest se corre por archivo** con `npx vitest run <ruta>` (no hay script `test` en `frontend/package.json`; la contaminación cross-file está documentada).
4. **Ratchet de cero inline-style en `.tsx` nuevos.** Este plan **no crea ningún `.tsx` nuevo**: edita tres `.tsx` existentes y todo estilo va por CSS Module.
5. **Se lee la INSTANCIA `config.config`, nunca el módulo.** Patrón obligatorio: `import config as _config` + `getattr(_config.config, "STACKY_X", True)` (ver `backend/api/executions.py:30-32`).

---

## 4. Principios y guardarraíles

- **P1 — Prohibido crear un falso VERDE nuevo.** Invariante `I1`, codificado en test: para **toda** combinación de evidencia, si el estado terminal del run es `error`, el nivel del veredicto **nunca** es `exito`. El techo al que puede subir un rojo es `advertencia` ("probable falso rojo, revisalo"). Esto es la lección C6 del 254 llevada a código ejecutable.
- **P2 — La ignorancia nunca mejora el veredicto.** Invariante `I2`, codificado en test: una señal `None` (desconocida) produce un nivel **igual o peor** que la misma señal en `False`. Nunca mejor. Si una fuente no está disponible, el veredicto degrada; jamás fabrica confianza.
- **P3 — Lectura, no cierre.** El veredicto se computa **en tiempo de lectura del payload**, no en el sitio de cierre. Consecuencias: (a) paridad de los 3 runtimes gratis, porque los tres escriben `AgentExecution` y de ahí lee el veredicto; (b) cero riesgo de regresión sobre el cierre que 254 acaba de estabilizar; (c) backward-compatible por construcción — nada existente cambia de forma.
- **P4 — Solo lectura absoluta en los colectores.** Ningún colector escribe, crea, mueve ni borra. Todos tienen tope de tiempo y degradan a `None`. Un colector que falla **jamás** rompe el listado.
- **P5 — El veredicto es una DIMENSIÓN SEPARADA, no un estado.** `status_vocabulary.py` **no se toca**: no se agrega ni un estado. El payload gana una clave nueva `verdict`; `stacky_status` sigue significando exactamente lo mismo que ayer.
- **P6 — Human-in-the-loop innegociable.** Stacky nunca cambia un estado terminal a partir del veredicto. La única corrección la dispara el humano con un click, contra un endpoint que **no publica en ningún sistema externo** (§3.6).
- **P7 — Cero trabajo para el operador.** Todo es invisible y automático. Las 5 flags nacen **ON**. No hay ni una decisión nueva que tomar para que el sistema mejore.
- **P8 — Sin autonomía proactiva.** Nada de este plan corre en un loop, daemon, barrido ni polling. Todo se computa cuando el operador ya estaba pidiendo esos datos.

---

## 5. Fases

### F0 — Capa PURA de veredicto (`run_verdict.py`)

**Objetivo (1 frase):** Un módulo puro que, dado el `outcome_reason` del 254 más un conjunto de señales tri-estado de evidencia, devuelve un veredicto de 3 niveles con su causa y el detalle de qué evidencia hay y qué falta.

**Valor:** Es el corazón del plan. Sin él, "diferenciar errores reales de falsos positivos" queda en prosa. Puro ⇒ testeable sin base, sin red y sin runtime.

**Paso 0 (obligatorio, antes de escribir código):** medir el KPI K2 y anotarlo en la tabla de §1:
```
cd "Stacky Agents/backend"
.venv\Scripts\python.exe -c "from services.error_fingerprints import count_falso_rojo_downgrades; print(count_falso_rojo_downgrades(30))"
```

**Archivo a crear:** `Stacky Agents/backend/services/run_verdict.py`
**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan267_run_verdict.py`

**Contenido EXACTO del módulo (nombres congelados):**

```python
"""Plan 267 F0 — veredicto por evidencia. Módulo PURO.

Sin DB, sin red, sin disco, sin imports de `db`/`models`. Se testea solo.

El plan 254 respondió "POR QUÉ terminó así" mirando el proceso. Este módulo
responde la otra mitad que pidió el operador: "¿produjo resultados y cumplió
su objetivo?". El veredicto es una DIMENSIÓN SEPARADA de `stacky_status`: no
es un estado nuevo y NUNCA cambia uno.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Los 3 niveles, de mejor a peor. Cerrado: no se agregan niveles.
VERDICT_LEVELS = ("exito", "advertencia", "error_real")

# Causa del veredicto. Cerrado. Toda causa mapea a exactamente un nivel.
VERDICT_CAUSES = (
    "cierre_limpio_con_entrega",           # exito
    "verde_sin_evidencia",                 # advertencia
    "evidencia_indeterminada",             # advertencia
    "cierre_sucio_pendiente_de_revision",  # advertencia
    "falso_rojo_probable",                 # advertencia  ← el caso que pidió el operador
    "espera_cuota",                        # advertencia
    "error_sin_entrega_suficiente",        # error_real
    "bloqueado_antes_de_empezar",          # error_real
)

# Nombres de las señales de evidencia. Cerrado y ORDENADO (el orden se usa para
# serializar las listas presentes/ausentes/desconocidas de forma determinista).
EVIDENCE_SIGNALS = (
    "publicado_en_tracker",
    "cambio_en_repo",
    "gate_aceptacion_ok",
    "verificacion_ok",
    "entregable_presente",
)

# Peso de cada señal. Las 3 "fuertes" valen 2 porque son objetivas y externas al
# propio agente (una fila en agent_html_publish, un PR abierto, un gate que
# corrió). Las 2 "débiles" valen 1: un archivo en disco o una verificación
# pueden ser parciales.
_PESO = {
    "publicado_en_tracker": 2,
    "cambio_en_repo": 2,
    "gate_aceptacion_ok": 2,
    "verificacion_ok": 1,
    "entregable_presente": 1,
}
UMBRAL_ENTREGA = 2  # fuerza mínima para considerar que "produjo resultados"

# Nivel base derivado del estado terminal. `cancelled` es advertencia: el humano
# lo cortó, no es un fallo del sistema.
_STATUS_TO_BASE = {
    "completed": "exito",
    "needs_review": "advertencia",
    "cancelled": "advertencia",
    "error": "error_real",
}

_CAUSE_TO_LEVEL = {
    "cierre_limpio_con_entrega": "exito",
    "verde_sin_evidencia": "advertencia",
    "evidencia_indeterminada": "advertencia",
    "cierre_sucio_pendiente_de_revision": "advertencia",
    "falso_rojo_probable": "advertencia",
    "espera_cuota": "advertencia",
    "error_sin_entrega_suficiente": "error_real",
    "bloqueado_antes_de_empezar": "error_real",
}


@dataclass(frozen=True)
class EvidenceSignals:
    """Tri-estado por señal: True=presente, False=ausente, None=DESCONOCIDA.

    `None` es un valor de primera clase: significa "no pude mirar". Nunca se
    convierte en False silenciosamente (eso sería inventar evidencia negativa)
    ni en True (eso sería inventar un verde)."""

    publicado_en_tracker: bool | None = None
    cambio_en_repo: bool | None = None
    gate_aceptacion_ok: bool | None = None
    verificacion_ok: bool | None = None
    entregable_presente: bool | None = None

    def get(self, name: str) -> bool | None:
        return getattr(self, name, None)


@dataclass(frozen=True)
class RunVerdict:
    level: str                       # ∈ VERDICT_LEVELS
    cause: str                       # ∈ VERDICT_CAUSES
    strength: int                    # fuerza de entrega acumulada
    present: tuple[str, ...] = ()    # señales True, en orden de EVIDENCE_SIGNALS
    absent: tuple[str, ...] = ()     # señales False
    unknown: tuple[str, ...] = ()    # señales None

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "cause": self.cause,
            "strength": self.strength,
            "present": list(self.present),
            "absent": list(self.absent),
            "unknown": list(self.unknown),
        }


def delivery_strength(signals: EvidenceSignals) -> int:
    """Suma los pesos de las señales PRESENTES. `None` y `False` suman 0.

    Que None y False sumen igual es deliberado: la ignorancia no puede sumar
    confianza (principio P2)."""
    return sum(_PESO[name] for name in EVIDENCE_SIGNALS if signals.get(name) is True)


def evaluate_verdict(
    *,
    ticket_status: str,
    outcome_reason: str | None = None,
    signals: EvidenceSignals | None = None,
) -> RunVerdict:
    """Devuelve exactamente un RunVerdict. Puro y determinístico.

    ORDEN DE PRECEDENCIA OBLIGATORIO — se evalúa en este orden y se devuelve en
    el PRIMER match. Sin este orden, dos reglas pueden matchear y el resultado
    es ambiguo para un modelo menor.

      1. outcome_reason == "preflight_blocked"        → bloqueado_antes_de_empezar (error_real)
      2. outcome_reason == "quota_exhausted"          → espera_cuota (advertencia)
      3. base == "error_real" y fuerza >= UMBRAL      → falso_rojo_probable (advertencia)
      4. base == "error_real"                         → error_sin_entrega_suficiente (error_real)
      5. base == "advertencia"                        → cierre_sucio_pendiente_de_revision
      6. base == "exito" y fuerza >= UMBRAL           → cierre_limpio_con_entrega (exito)
      7. base == "exito" y hay alguna señal None      → evidencia_indeterminada (advertencia)
      8. base == "exito" (resto)                      → verde_sin_evidencia (advertencia)

    Nota sobre 6 antes de 7: si ya hay UMBRAL de evidencia PRESENTE, una señal
    desconocida al lado no borra la evidencia que sí está. No fabrica un verde
    porque el base ya era verde (regla 6 es inalcanzable desde un estado rojo).

    Un `ticket_status` desconocido cae a base "advertencia" (nunca a un verde).
    """
    sig = signals or EvidenceSignals()
    base = _STATUS_TO_BASE.get((ticket_status or "").strip(), "advertencia")
    fuerza = delivery_strength(sig)

    present = tuple(n for n in EVIDENCE_SIGNALS if sig.get(n) is True)
    absent = tuple(n for n in EVIDENCE_SIGNALS if sig.get(n) is False)
    unknown = tuple(n for n in EVIDENCE_SIGNALS if sig.get(n) is None)

    if outcome_reason == "preflight_blocked":
        cause = "bloqueado_antes_de_empezar"
    elif outcome_reason == "quota_exhausted":
        cause = "espera_cuota"
    elif base == "error_real" and fuerza >= UMBRAL_ENTREGA:
        cause = "falso_rojo_probable"
    elif base == "error_real":
        cause = "error_sin_entrega_suficiente"
    elif base == "advertencia":
        cause = "cierre_sucio_pendiente_de_revision"
    elif fuerza >= UMBRAL_ENTREGA:
        cause = "cierre_limpio_con_entrega"
    elif unknown:
        cause = "evidencia_indeterminada"
    else:
        cause = "verde_sin_evidencia"

    return RunVerdict(
        level=_CAUSE_TO_LEVEL[cause],
        cause=cause,
        strength=fuerza,
        present=present,
        absent=absent,
        unknown=unknown,
    )
```

> **Nota de diseño para el implementador:** la regla 5 (`base == "advertencia"`) captura `needs_review` y `cancelled`. Si el `outcome_reason` era `dirty_exit_after_work` o `stall_after_work`, el 254 ya mapeó el estado a `needs_review` (`services/run_outcome.py:36,38`), así que llegan acá y reciben `cierre_sucio_pendiente_de_revision`. **No** hay que replicar esa lógica.

**Tests PRIMERO — `backend/tests/test_plan267_run_verdict.py`**, casos exactos:

| Test | Qué prueba |
|---|---|
| `test_todo_nivel_pertenece_al_vocabulario` | Barre `itertools.product` sobre `(True, False, None)^5` × los 4 estados de `_STATUS_TO_BASE` + `"basura"` × los 9 `OUTCOME_REASONS` + `None`; asegura `v.level in VERDICT_LEVELS` y `v.cause in VERDICT_CAUSES` **siempre**. Nunca `None`, nunca `KeyError`. |
| `test_I1_un_error_jamas_recibe_exito` | **INVARIANTE DURO.** Sobre la misma grilla, con `ticket_status="error"`, asegura `v.level != "exito"` en el 100% de los casos. |
| `test_I2_desconocido_nunca_mejora` | Para cada señal `s` y cada estado base, compara `evaluate_verdict(signals=... s=None ...)` contra `... s=False ...`: el índice del nivel en `VERDICT_LEVELS` con `None` debe ser **≥** (igual o peor) que con `False`. |
| `test_falso_rojo_probable_con_publicacion` | `ticket_status="error"`, `publicado_en_tracker=True` → `cause == "falso_rojo_probable"`, `level == "advertencia"`, `strength == 2`. |
| `test_falso_rojo_probable_con_dos_debiles` | `ticket_status="error"`, `verificacion_ok=True`, `entregable_presente=True` → `strength == 2` → `falso_rojo_probable`. |
| `test_error_con_una_sola_debil_sigue_siendo_error` | `ticket_status="error"`, solo `entregable_presente=True` → `strength == 1` → `cause == "error_sin_entrega_suficiente"`, `level == "error_real"`. |
| `test_preflight_gana_sobre_toda_evidencia` | `outcome_reason="preflight_blocked"` con las 5 señales en `True` → sigue siendo `bloqueado_antes_de_empezar` / `error_real`. Prueba la precedencia 1. |
| `test_cuota_gana_sobre_error` | `ticket_status="error"`, `outcome_reason="quota_exhausted"` → `espera_cuota` / `advertencia`. |
| `test_verde_sin_evidencia_es_advertencia` | `ticket_status="completed"`, las 5 señales en `False` → `verde_sin_evidencia` / `advertencia`. |
| `test_verde_con_desconocidas_es_advertencia` | `ticket_status="completed"`, las 5 en `None` → `evidencia_indeterminada` / `advertencia`. |
| `test_verde_con_entrega_es_exito` | `ticket_status="completed"`, `publicado_en_tracker=True` → `cierre_limpio_con_entrega` / `exito`. |
| `test_needs_review_es_advertencia` | `ticket_status="needs_review"` con cualquier evidencia → `cierre_sucio_pendiente_de_revision` / `advertencia`. |
| `test_listas_present_absent_unknown_particionan` | Para cualquier entrada, `set(present) | set(absent) | set(unknown) == set(EVIDENCE_SIGNALS)` y las tres son disjuntas. |
| `test_causa_mapea_a_un_solo_nivel` | `set(_CAUSE_TO_LEVEL) == set(VERDICT_CAUSES)` y todo valor ∈ `VERDICT_LEVELS`. |
| `test_no_agrega_estados_al_vocabulario` | Importa `status_vocabulary.VALID_TICKET_STATUSES` y asegura que **ningún** `VERDICT_LEVEL` está adentro (son dimensiones distintas y no deben confundirse). |

**Comando de aceptación (BINARIO):**
```
cd "Stacky Agents/backend"
.venv\Scripts\python.exe -m pytest tests/test_plan267_run_verdict.py -v
```
**Criterio:** 15/15 verdes. Cero fallos.

**Flag que la protege:** `STACKY_RUN_VERDICT_ENABLED` — **default ON**. Sin excepción: es un módulo puro que calcula en memoria y no escribe nada, no llama a ningún modelo y no corre en reposo. Alta completa según **RECETA-FLAG** (§3.7), categoría `observabilidad_notif`.

**Impacto por runtime:** ninguno. Es un módulo puro sin dependencia de runtime. Codex / Claude Code / Copilot: idéntico.
**Trabajo del operador:** ninguno.

---

### F1 — Colectores de evidencia read-only (`run_evidence.py`)

**Objetivo (1 frase):** Un módulo que arma `EvidenceSignals` para un lote de ejecuciones leyendo **solo** fuentes ya existentes, con tope de tiempo, sin N+1 y degradando a `None` ante cualquier problema.

**Valor:** Es lo que convierte el veredicto de F0 en algo que refleja la realidad del operador.

**Archivo a crear:** `Stacky Agents/backend/services/run_evidence.py`
**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan267_run_evidence.py`

**API pública EXACTA:**

```python
"""Plan 267 F1 — colectores de evidencia. SOLO LECTURA, con tope de tiempo.

Rieles duros:
- No escribe, no crea, no borra, no mueve. Ni una fila, ni un archivo.
- Sin red: no llama a la API de ADO ni de GitLab. La evidencia de publicación
  sale de la tabla local `agent_html_publish`, que ya es el registro de lo que
  Stacky publicó (services/ado_publisher.py:122).
- Sin N+1: `collect_for_executions` resuelve TODO el lote con 3 queries fijas.
- Ante cualquier fallo la señal queda en None (desconocida), NUNCA en False y
  NUNCA en True. Un colector jamás rompe el listado que lo llama.
- Sin autonomía: nadie lo llama en un loop. Se invoca cuando el operador ya
  estaba pidiendo el listado.
"""
from __future__ import annotations

COLLECTOR_BUDGET_S = 2.0   # presupuesto TOTAL del lote para las lecturas de disco

def collectors_enabled() -> bool: ...
    # Lee la INSTANCIA: getattr(_config.config, "STACKY_RUN_EVIDENCE_COLLECTORS_ENABLED", True)

def collect_for_executions(session, executions: list) -> dict[int, "EvidenceSignals"]: ...
    # Devuelve {execution_id: EvidenceSignals}. Con la flag OFF devuelve {}.

def _publish_ok_execution_ids(session, execution_ids: list[int]) -> set[int]: ...
def _signals_from_execution(ex, *, publicado: bool | None, presupuesto: "_Budget") -> "EvidenceSignals": ...
```

**Cómo se computa cada señal (pseudocódigo, sin ambigüedad):**

```
publicado_en_tracker:
    UNA query para todo el lote (patrón api/executions.py:48-53):
        SELECT execution_id FROM agent_html_publish
         WHERE execution_id IN (:ids) AND status = 'ok'
    → True  si el id está en el set
    → False si NO está Y la query corrió sin excepción
    → None  si la query lanzó (se captura y se loguea en debug)

cambio_en_repo:
    intent = incident_dev_pr.get_intent(ex.id)      # services/incident_dev_pr.py:213
    → None  si el presupuesto de tiempo ya se agotó (no se lee el disco)
    → False si get_intent devolvió None (no hay sidecar: este agente no toca repo)
    → True  si intent.get("pr_url") o intent.get("pr_id")
             o (intent.get("files_committed") or 0) > 0
    → False en cualquier otro caso con sidecar presente
    NOTA: get_intent ya captura OSError/ValueError y devuelve None (`:219-220`),
    así que no puede lanzar. La distinción None-por-presupuesto la lleva _Budget.

gate_aceptacion_ok:
    cr = ex.contract_result            # property, models.py:309
    → None  si cr es None (no hubo contrato: no se puede afirmar nada)
    → True  si cr.get("passed") is True o cr.get("status") == "passed"
    → False en el resto
    HIPÓTESIS DECLARADA (H1): que la clave sea "passed" NO está verificado en
    este documento. El test `test_gate_lee_ambas_formas_y_desconoce_el_resto`
    DISCRIMINA la hipótesis: prueba las 2 formas y prueba que una tercera forma
    (p.ej. {"resultado": "ok"}) devuelve False, no True. Si en el árbol la clave
    real fuera otra, el implementador la agrega a la condición y AL TEST — nunca
    adivina en silencio.

verificacion_ok:
    meta = ex.metadata_dict            # property, models.py:301
    v = meta.get("exec_verification") or meta.get("verification")
    → None  si v no es un dict
    → True  si v.get("ok") is True
    → False en el resto
    MISMA HIPÓTESIS DECLARADA (H2), mismo tratamiento: el test prueba las 2
    claves y prueba que una forma desconocida da None (no True).

entregable_presente:
    → True si (ex.output or "").strip() tiene más de 0 caracteres
    → si no, y ex.html_output_path no es vacío:
         → None si el presupuesto se agotó (no se toca el disco)
         → True si Path(html_output_path).is_file() y st_size > 0
         → False si no existe o mide 0 bytes
         → None si la llamada al filesystem lanzó OSError
    → False si no hay output ni html_output_path
```

**El presupuesto de tiempo (`_Budget`), explícito:**
```python
class _Budget:
    """Presupuesto TOTAL del lote, no por fila. Un lote de 200 ejecuciones no
    puede gastar 200 x timeout. `spent()` se consulta antes de CADA lectura de
    disco; agotado ⇒ la señal queda None (desconocida) y se sigue."""
    def __init__(self, seconds: float): self._deadline = time.monotonic() + seconds
    def exhausted(self) -> bool: return time.monotonic() >= self._deadline
```

**Tests PRIMERO — `backend/tests/test_plan267_run_evidence.py`** (usan objetos falsos con los mismos atributos; **no tocan la base real**):

| Test | Qué prueba |
|---|---|
| `test_flag_off_devuelve_dict_vacio` | Con `STACKY_RUN_EVIDENCE_COLLECTORS_ENABLED=False` en la instancia, `collect_for_executions` devuelve `{}` y **no hace ni una query** (se pasa un `session` que lanza si lo tocan). |
| `test_entregable_por_output_no_toca_disco` | `ex.output = "resultado"` → `entregable_presente is True` sin llamar a `Path.is_file` (monkeypatch que lanza). |
| `test_entregable_por_html_existente` | `tmp_path` con un archivo de >0 bytes → `True`. Archivo de 0 bytes → `False`. Ruta inexistente → `False`. |
| `test_entregable_oserror_es_desconocido` | `monkeypatch` de `Path.is_file` que lanza `OSError` → señal `None`, no `False`. |
| `test_colector_lento_degrada_a_desconocido` | `_Budget(0)` (presupuesto agotado desde el arranque) → todas las señales que requieren disco quedan `None` y la función **retorna**; nada cuelga. |
| `test_publicado_en_una_sola_query` | Un `session` falso que cuenta invocaciones: con 50 ejecuciones se hace **exactamente 1** query a `agent_html_publish`. |
| `test_publicado_query_que_lanza_es_desconocido` | El `session` falso lanza → todas las señales `publicado_en_tracker` quedan `None`, y las demás señales se siguen computando igual. |
| `test_cambio_en_repo_sin_sidecar_es_false` | `get_intent` monkeypatcheado a `None` → `False` (ausencia informada, no ignorancia). |
| `test_cambio_en_repo_con_pr_url_es_true` | `get_intent` → `{"pr_url": "https://..."}` → `True`. También con `{"files_committed": 3}`. |
| `test_gate_lee_ambas_formas_y_desconoce_el_resto` | **Discrimina H1.** `{"passed": True}` → `True`; `{"status": "passed"}` → `True`; `{"passed": False}` → `False`; `contract_result = None` → `None`; `{"resultado": "ok"}` → `False`. |
| `test_verificacion_lee_ambas_claves_y_desconoce_el_resto` | **Discrimina H2.** `{"exec_verification": {"ok": True}}` → `True`; `{"verification": {"ok": False}}` → `False`; metadata sin ninguna de las dos → `None`. |
| `test_no_escribe_nada` | El `session` falso hace que `add`, `merge`, `delete`, `commit` y `flush` lancen `AssertionError`; la corrida completa pasa sin tocarlos. |

**Comando de aceptación (BINARIO):**
```
cd "Stacky Agents/backend"
.venv\Scripts\python.exe -m pytest tests/test_plan267_run_evidence.py -v
```
**Criterio:** 12/12 verdes.

**Flag:** `STACKY_RUN_EVIDENCE_COLLECTORS_ENABLED` — **default ON**. Categoría `observabilidad_notif`. **No es excepción:** solo lee (una query local + `stat()` de archivos ya escritos), no llama a ningún modelo, no corre en reposo y no escribe nada. Es exactamente el caso que la regla de la casa manda dejar ON. Se separa de `STACKY_RUN_VERDICT_ENABLED` para que el operador pueda matar solo las lecturas de disco sin perder el veredicto (que degradaría a `evidencia_indeterminada`).

**Impacto por runtime:**
- **Claude Code CLI:** lee `AgentExecution` que el runner ya escribió (`services/claude_code_cli_runner.py:1865` deja `outcome_reason` en el metadata). Sin cambios en el runner.
- **Codex CLI:** ídem (`services/codex_cli_runner.py:755`). Sin cambios en el runner.
- **GitHub Copilot Pro:** `copilot_bridge.py` no cierra ejecuciones (**0 hits de `final_status`**, §2); el cierre lo hace `agent_runner.py:1029/1055/1082`, que también escribe la fila de `AgentExecution`. Por eso el colector funciona igual. **Fallback explícito:** si un runtime no produce alguna señal (p. ej. Copilot sin sidecar de PR), esa señal es `False` o `None` — nunca inventada — y el veredicto degrada a `advertencia` en vez de fabricar un verde.

**Trabajo del operador:** ninguno.

---

### F2 — Cablear el veredicto al payload de ejecuciones

**Objetivo (1 frase):** Que el payload que la UI ya consume traiga la clave `verdict` calculada en el lote, sin N+1 y sin cambiar ninguna clave existente.

**Valor:** Un solo punto de inyección alimenta el drawer, el historial y cualquier consumidor futuro.

**Archivo a editar:** `Stacky Agents/backend/api/executions.py`
**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan267_executions_payload.py`

**Diff ilustrativo (se agrega **debajo** de `_with_outcome`, sin tocar su cuerpo):**

```python
def _verdict_badge_enabled() -> bool:
    """Plan 267 F2 — kill-switch del veredicto en el payload. Se lee la INSTANCIA.

    Dependencia resuelta EN CÓDIGO, no con `requires=` en la FlagSpec (ver §3.7):
    el veredicto solo se sirve si están ON la flag de UI Y la del núcleo.
    """
    import config as _config  # noqa: PLC0415

    return (
        bool(getattr(_config.config, "STACKY_UI_RUN_VERDICT_BADGE_ENABLED", True))
        and bool(getattr(_config.config, "STACKY_RUN_VERDICT_ENABLED", True))
    )


def _verdicts_for_batch(session, executions: list) -> dict[int, dict]:
    """Plan 267 F2 — veredicto de TODO el lote. Read-only, sin N+1.

    Nunca lanza: cualquier fallo devuelve {} y el listado sale como antes.
    """
    if not _verdict_badge_enabled():
        return {}
    try:
        from services.run_evidence import collect_for_executions  # noqa: PLC0415
        from services.run_verdict import evaluate_verdict  # noqa: PLC0415

        signals_by_id = collect_for_executions(session, executions)
        out: dict[int, dict] = {}
        for ex in executions:
            ticket = getattr(ex, "ticket", None)
            estado = (getattr(ticket, "stacky_status", None) or ex.status or "idle")
            meta = ex.metadata_dict if isinstance(ex.metadata_dict, dict) else {}
            out[ex.id] = evaluate_verdict(
                ticket_status=estado,
                outcome_reason=meta.get("outcome_reason"),
                signals=signals_by_id.get(ex.id),
            ).to_dict()
        return out
    except Exception:  # noqa: BLE001 — enriquecer JAMÁS rompe el listado
        logger.debug("verdict 267 falló", exc_info=True)
        return {}


def _with_verdict(d: dict, verdicts: dict[int, dict]) -> dict:
    """Agrega `verdict` si hay uno. Con la flag OFF no agrega NINGUNA clave:
    la UI simplemente no dibuja el chip (sin hueco ni error)."""
    v = verdicts.get(d.get("id"))
    if v:
        d["verdict"] = v
    return d
```

**Puntos de llamada:** en `list_executions()` (`backend/api/executions.py:96`) y en el handler de detalle, **dentro del mismo `with session_scope()`** donde ya se calcula `dirty_ids`, agregar una línea `verdicts = _verdicts_for_batch(session, rows)` y aplicar `_with_verdict(_with_outcome(d, dirty_ids), verdicts)` en el armado de cada fila. **No se reordena ni se borra nada de lo que ya hace `_with_outcome`.**

**Forma EXACTA de la clave nueva en el payload:**
```json
"verdict": {
  "level": "advertencia",
  "cause": "falso_rojo_probable",
  "strength": 2,
  "present": ["publicado_en_tracker"],
  "absent": ["cambio_en_repo", "gate_aceptacion_ok"],
  "unknown": ["verificacion_ok", "entregable_presente"]
}
```

**Tests PRIMERO — `backend/tests/test_plan267_executions_payload.py`:**

| Test | Qué prueba |
|---|---|
| `test_flag_off_no_agrega_la_clave` | Con `STACKY_UI_RUN_VERDICT_BADGE_ENABLED=False`, `"verdict" not in payload` — **no** una clave con `None`. |
| `test_flag_nucleo_off_tambien_apaga` | Con `STACKY_RUN_VERDICT_ENABLED=False` y la de UI en ON, tampoco aparece la clave (dependencia en código). |
| `test_flag_on_agrega_la_clave_con_las_6_subclaves` | `set(payload["verdict"]) == {"level","cause","strength","present","absent","unknown"}`. |
| `test_colector_que_lanza_no_rompe_el_listado` | `collect_for_executions` monkeypatcheado a lanzar → la respuesta sigue siendo 200 y las claves del 254 (`outcome_reason`, `outcome_actionable`) **siguen presentes**. |
| `test_no_pisa_claves_del_254` | `outcome_reason` y `outcome_actionable` conservan exactamente el mismo valor con la flag del 267 en ON y en OFF. |
| `test_sin_n_mas_uno` | Con 30 ejecuciones se cuenta el número de queries emitidas; debe ser **constante** respecto a un lote de 3 (no crecer con el tamaño). |

**Comando de aceptación (BINARIO):**
```
cd "Stacky Agents/backend"
.venv\Scripts\python.exe -m pytest tests/test_plan267_executions_payload.py -v
```
**Criterio:** 6/6 verdes. Y sin regresión en el 254, validado **por archivo**:
```
.venv\Scripts\python.exe -m pytest tests/test_plan254_outcome_reason.py -v
.venv\Scripts\python.exe -m pytest tests/test_plan254_reconciliation.py -v
```

**Flag:** `STACKY_UI_RUN_VERDICT_BADGE_ENABLED` — **default ON**, categoría `observabilidad_notif`. Solo enriquece un payload de lectura.
**Impacto por runtime:** ninguno (P3: se calcula al leer). **Fallback:** con cualquiera de las dos flags OFF, el payload es **byte-idéntico** al de hoy.
**Trabajo del operador:** ninguno.

---

### F3 — Módulo PURO de presentación del veredicto (`runVerdict.ts`)

**Objetivo (1 frase):** Un `.ts` puro que traduce el veredicto a etiqueta en castellano llana, tono y explicación de la evidencia, reusando `OutcomeTone` del 254.

**Valor:** Toda la lógica de UI queda testeable con vitest; los `.tsx` solo consumen.

**Archivo a crear:** `Stacky Agents/frontend/src/utils/runVerdict.ts`
**Archivo de test a crear:** `Stacky Agents/frontend/src/utils/__tests__/plan267RunVerdict.test.ts`

**Por qué un módulo puro y no un test de render:** `@testing-library/react` y `jsdom` **no están instalados** en este repo (`frontend/package.json` devDependencies). Un test de vitest que renderice React **no es ejecutable acá**. Mismo criterio que `outcomeReason.ts` (ver su comentario de cabecera, líneas 2-6).

**Contenido EXACTO (nombres congelados):**

```typescript
// Plan 267 F3 — veredicto por evidencia → etiqueta + tono + explicación.
//
// Reusa OutcomeTone de outcomeReason.ts (254 F4): NO se define un tipo de tono
// nuevo. El veredicto es una DIMENSIÓN SEPARADA del estado, no un estado más.

import type { OutcomeTone } from "./outcomeReason";

export type VerdictLevel = "exito" | "advertencia" | "error_real";

export interface RunVerdictPayload {
  level: string;
  cause: string;
  strength?: number;
  present?: string[];
  absent?: string[];
  unknown?: string[];
}

export interface VerdictView {
  level: VerdictLevel;
  tone: OutcomeTone;      // "exito" | "atencion" | "espera" | "error"
  label: string;          // texto del chip de la fila, corto
  detail: string;         // una línea explicando la causa
  needsOperator: boolean; // true ⇒ merece un ojo humano
}

/** Los 3 niveles → tono + etiqueta corta de fila. */
export const VERDICT_LEVEL_VIEW: Record<VerdictLevel, { tone: OutcomeTone; label: string }> = {
  exito:       { tone: "exito",    label: "Terminó bien" },
  advertencia: { tone: "atencion", label: "Con advertencias" },
  error_real:  { tone: "error",    label: "Error real" },
};

/** Las 8 causas de VERDICT_CAUSES (services/run_verdict.py), ni una más ni una menos. */
export const VERDICT_CAUSE_DETAIL: Record<string, string> = {
  cierre_limpio_con_entrega: "Terminó sin errores y dejó resultados verificables.",
  verde_sin_evidencia: "Figura como terminado, pero no se encontró ningún resultado que lo respalde.",
  evidencia_indeterminada: "Figura como terminado, pero no se pudo comprobar si dejó resultados.",
  cierre_sucio_pendiente_de_revision: "Entregó trabajo pero el proceso cerró mal: convendría mirarlo.",
  falso_rojo_probable: "Figura como fallado, pero hay resultados: probablemente NO sea un error.",
  espera_cuota: "Se agotó la cuota del plan. No es un error del trabajo: hay que reintentar más tarde.",
  error_sin_entrega_suficiente: "Falló y no se encontraron resultados: requiere atención.",
  bloqueado_antes_de_empezar: "Se bloqueó antes de arrancar: nunca llegó a trabajar.",
};

/** Nombres humanos de EVIDENCE_SIGNALS (services/run_verdict.py). */
export const EVIDENCE_LABELS: Record<string, string> = {
  publicado_en_tracker: "comentario publicado en el tablero",
  cambio_en_repo: "cambios en el repositorio",
  gate_aceptacion_ok: "criterios de aceptación verificados",
  verificacion_ok: "verificación de la ejecución",
  entregable_presente: "archivo de resultado",
};

const NIVELES: VerdictLevel[] = ["exito", "advertencia", "error_real"];

/**
 * Traduce el veredicto. Un nivel o causa del futuro NO rompe la UI: cae a
 * "advertencia" con el texto crudo, nunca a `undefined` y NUNCA a "exito"
 * (un nivel desconocido jamás se presenta como éxito).
 */
export function describeVerdict(v: RunVerdictPayload | null | undefined): VerdictView | null {
  if (!v || !v.level) return null;
  const level: VerdictLevel = (NIVELES as string[]).includes(v.level)
    ? (v.level as VerdictLevel)
    : "advertencia";
  const view = VERDICT_LEVEL_VIEW[level];
  return {
    level,
    tone: view.tone,
    label: view.label,
    detail: VERDICT_CAUSE_DETAIL[v.cause] ?? v.cause,
    needsOperator: level !== "exito",
  };
}

/** Frase de evidencia para el detalle: qué se encontró y qué no. */
export function evidenceSummary(v: RunVerdictPayload | null | undefined): string {
  if (!v) return "";
  const nombre = (k: string) => EVIDENCE_LABELS[k] ?? k;
  const partes: string[] = [];
  if (v.present?.length) partes.push(`Se encontró: ${v.present.map(nombre).join(", ")}.`);
  if (v.absent?.length) partes.push(`No hay: ${v.absent.map(nombre).join(", ")}.`);
  if (v.unknown?.length) partes.push(`No se pudo comprobar: ${v.unknown.map(nombre).join(", ")}.`);
  return partes.join(" ");
}

/** Filtro por nivel para las listas. `null`/"" = sin filtro (devuelve todo). */
export function matchesVerdictLevel(
  v: RunVerdictPayload | null | undefined,
  filtro: string | null | undefined,
): boolean {
  if (!filtro) return true;
  const view = describeVerdict(v);
  if (!view) return false;   // sin veredicto no matchea un filtro explícito
  return view.level === filtro;
}
```

**Tests PRIMERO — `frontend/src/utils/__tests__/plan267RunVerdict.test.ts`:**

| Test | Qué prueba |
|---|---|
| `las 8 causas tienen texto` | `Object.keys(VERDICT_CAUSE_DETAIL).length === 8` y ninguno vacío. |
| `los 3 niveles tienen tono y etiqueta` | Cada `VerdictLevel` mapea a un tono ∈ `["exito","atencion","espera","error"]`. |
| `un nivel del futuro no se presenta como exito` | `describeVerdict({level:"nivel_del_futuro", cause:"x"})?.level === "advertencia"` y `tone === "atencion"`. |
| `una causa del futuro muestra el texto crudo` | `detail === "causa_rara"`, no `undefined`. |
| `null y undefined devuelven null` | `describeVerdict(null)`, `describeVerdict(undefined)`, `describeVerdict({level:""} as any)` → `null`. |
| `needsOperator es false solo en exito` | Recorre los 3 niveles. |
| `evidenceSummary nombra las 3 categorías` | Con `present`/`absent`/`unknown` poblados, el texto contiene "Se encontró", "No hay" y "No se pudo comprobar". |
| `evidenceSummary vacío no rompe` | `evidenceSummary({level:"exito",cause:"x"})` → `""`. |
| `matchesVerdictLevel sin filtro devuelve todo` | `matchesVerdictLevel(null, "")` → `true`. |
| `matchesVerdictLevel filtra por nivel` | `advertencia` matchea `"advertencia"` y no `"error_real"`. |
| `matchesVerdictLevel sin veredicto no matchea un filtro explícito` | `matchesVerdictLevel(null, "exito")` → `false`. |

**Comando de aceptación (BINARIO):**
```
cd "Stacky Agents/frontend"
npx vitest run src/utils/__tests__/plan267RunVerdict.test.ts
```
(Correr **por archivo**: la corrida completa de vitest tiene contaminación cross-file conocida en este repo.)
**Criterio:** 11/11 verdes. Y `npx tsc --noEmit` sin errores nuevos.

**Flag:** protegido por `STACKY_UI_RUN_VERDICT_BADGE_ENABLED` (F2): sin la clave `verdict` en el payload, `describeVerdict` devuelve `null` y no se dibuja nada.
**Impacto por runtime:** ninguno.
**Trabajo del operador:** ninguno.

---

### F4 — El veredicto en la FILA del historial de ejecuciones + filtro por nivel

**Objetivo (1 frase):** Que la fila del historial muestre **dos** dimensiones —estado y veredicto— y que el operador pueda filtrar por nivel de veredicto.

**Valor:** Cierra el GAP 2 en la superficie donde el operador mira las corridas. Hoy `ExecutionHistoryPage.tsx:633` pinta un solo chip.

**Archivos a editar:**
- `Stacky Agents/frontend/src/pages/ExecutionHistoryPage.tsx`
- `Stacky Agents/frontend/src/pages/ExecutionHistoryPage.module.css` (si no existe la clase del chip secundario; **cero estilo inline** por el ratchet de deuda de UI)
- `Stacky Agents/frontend/src/api/endpoints.ts` (agregar `verdict?: RunVerdictPayload` a la interfaz de la fila de ejecución; **campo opcional**, backward-compatible)

**Diff ilustrativo (fila, sobre `ExecutionHistoryPage.tsx:633`):**

```diff
+import { describeVerdict, matchesVerdictLevel } from "../utils/runVerdict";
...
   <td><StatusChip tone={runStatusTone(item.status)} size="sm">{runStatusLabel(item.status)}</StatusChip></td>
+  <td>
+    {(() => {
+      const v = describeVerdict(item.verdict);
+      if (!v) return null;
+      return (
+        <StatusChip tone={verdictChipTone(v.tone)} size="sm" title={v.detail}>
+          {v.label}
+        </StatusChip>
+      );
+    })()}
+  </td>
```

**Puente de tonos (va en `runVerdict.ts`, NO en el `.tsx`), para no acoplar `utils/` a `ui/`:**
```typescript
// `StatusChip` usa StatusTone ("success"|"warning"|"danger"|"info"|"neutral",
// utils/runStatus.ts:1). OutcomeTone es otro vocabulario. Este puente traduce.
export function verdictChipTone(tone: OutcomeTone): "success" | "warning" | "danger" | "neutral" {
  if (tone === "exito") return "success";
  if (tone === "error") return "danger";
  if (tone === "espera") return "neutral";
  return "warning";
}
```
> **Importante para el implementador:** la columna nueva exige agregar también su `<th>` en la cabecera de la tabla (buscar el `<thead>` del mismo archivo). Si se agrega un `<td>` sin `<th>`, la tabla queda desalineada.

**Filtro por nivel:** agregar un `<select>` junto al de estado (`ExecutionHistoryPage.tsx:400-401`) con opciones `""` (Todos) / `exito` / `advertencia` / `error_real`, guardado en el mismo objeto `filters` bajo la clave `verdict_level`, y **filtrado en cliente** con `matchesVerdictLevel(item.verdict, filters.verdict_level)` justo antes del `.map` de filas. Agregar `"verdict_level"` al array `urlFilterKeys` (`ExecutionHistoryPage.tsx:450`) para que el filtro viaje en la URL como los demás. **No** se toca el backend: el filtro es de presentación.

**Tests PRIMERO:** la lógica pura ya está cubierta por F3 (`matchesVerdictLevel`, `verdictChipTone`). Se **agrega** a `plan267RunVerdict.test.ts`:

| Test | Qué prueba |
|---|---|
| `verdictChipTone cubre los 4 tonos` | `exito→success`, `error→danger`, `espera→neutral`, `atencion→warning`. |
| `filtrar una lista por nivel` | Dado un array de 4 filas con veredictos distintos, `rows.filter(r => matchesVerdictLevel(r.verdict, "advertencia"))` devuelve exactamente las de advertencia. |

**Comando de aceptación (BINARIO):**
```
cd "Stacky Agents/frontend"
npx vitest run src/utils/__tests__/plan267RunVerdict.test.ts
npx tsc --noEmit
```
**Criterio:** 13/13 verdes y `tsc` sin errores nuevos. Además, gate de presencia:
```
grep -c "verdictChipTone" src/pages/ExecutionHistoryPage.tsx    # >= 1
grep -c "style={{" src/pages/ExecutionHistoryPage.tsx           # no debe AUMENTAR vs. HEAD
```

**Flag:** `STACKY_UI_RUN_VERDICT_BADGE_ENABLED` (la de F2). Con la flag OFF el payload no trae `verdict`, `describeVerdict` devuelve `null` y la celda queda vacía. **La columna y el filtro se renderizan igual** (una columna vacía no rompe la tabla); si se prefiere ocultar la columna entera, condicionarla a `rows.some(r => r.verdict)`.
**Impacto por runtime:** ninguno. **Fallback:** sin veredicto, la fila se ve exactamente como hoy.
**Trabajo del operador:** ninguno (el filtro es opcional y arranca en "Todos").

---

### F5 — El veredicto en la FILA de la bandeja de incidencias

**Objetivo (1 frase):** Que la bandeja de incidencias muestre el veredicto de la **última ejecución** de cada incidencia, sin romper la promesa de "sin N+1" que el endpoint ya declara.

**Valor:** Es la lista que el operador llama "incidencias". Hoy solo muestra `ado_state` crudo (`IncidentInboxPage.tsx:503`).

**Archivos a editar:**
- `Stacky Agents/backend/api/incident_inbox.py`
- `Stacky Agents/frontend/src/pages/IncidentInboxPage.tsx`
- `Stacky Agents/frontend/src/pages/IncidentInboxPage.module.css`
**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan267_inbox_verdict.py`

**Restricción heredada, no negociable:** `backend/api/incident_inbox.py:149` declara textualmente *"Sin N+1: NO se consulta AgentExecution ni pipeline_summary"*. Este plan **conserva** esa propiedad: se agrega **una sola** query extra para todo el lote.

**Pseudocódigo del backend (se inserta después de armar `rows`, antes del `for t in rows` de la línea 161):**

```python
def _last_execution_by_ticket(session, ticket_ids: list[int]) -> dict[int, "AgentExecution"]:
    """UNA query para todo el lote. Devuelve la ejecución más reciente por ticket.

    Sin N+1: se traen las ejecuciones de todos los tickets del lote ordenadas por
    started_at desc y se queda con la primera de cada ticket en memoria. El índice
    ix_exec_ticket_started (models.py:278) cubre exactamente este acceso.
    """
    if not ticket_ids:
        return {}
    from models import AgentExecution  # noqa: PLC0415
    filas = (
        session.query(AgentExecution)
        .filter(AgentExecution.ticket_id.in_(ticket_ids))
        .order_by(AgentExecution.ticket_id, AgentExecution.started_at.desc())
        .all()
    )
    out: dict[int, AgentExecution] = {}
    for ex in filas:
        out.setdefault(ex.ticket_id, ex)   # la primera de cada ticket es la más nueva
    return out


def _inbox_verdict_enabled() -> bool:
    import config as _config  # noqa: PLC0415
    return (
        bool(getattr(_config.config, "STACKY_INCIDENT_INBOX_VERDICT_ENABLED", True))
        and bool(getattr(_config.config, "STACKY_RUN_VERDICT_ENABLED", True))
    )
```

Y en el armado de items:
```python
verdicts = {}
if _inbox_verdict_enabled():
    try:
        ultimas = _last_execution_by_ticket(session, [t.id for t in rows])
        from services.run_evidence import collect_for_executions
        from services.run_verdict import evaluate_verdict
        señales = collect_for_executions(session, list(ultimas.values()))
        for tid, ex in ultimas.items():
            meta = ex.metadata_dict if isinstance(ex.metadata_dict, dict) else {}
            verdicts[tid] = evaluate_verdict(
                ticket_status=(getattr(ex, "ticket", None) and ex.ticket.stacky_status) or ex.status or "idle",
                outcome_reason=meta.get("outcome_reason"),
                signals=señales.get(ex.id),
            ).to_dict()
    except Exception:  # noqa: BLE001 — la bandeja JAMÁS se rompe por el veredicto
        logger.debug("verdict 267 en la bandeja falló", exc_info=True)
        verdicts = {}

for t in rows:
    payload = t.to_dict()
    payload["is_open"] = is_open_state(t.ado_state, closed)
    if t.id in verdicts:
        payload["verdict"] = verdicts[t.id]      # clave OPCIONAL: nunca se agrega vacía
    items.append(payload)
```

**Frontend:** en `IncidentInboxPage.tsx`, justo después del badge de `:504-506`, agregar:
```tsx
{(() => {
  const v = describeVerdict(item.verdict);
  return v ? <span className={styles.verdictBadge} data-tone={v.tone} title={v.detail}>{v.label}</span> : null;
})()}
```
y en el CSS Module una regla `.verdictBadge` con selectores `[data-tone="exito"|"atencion"|"espera"|"error"]`. **Cero estilo inline** (ratchet de deuda de UI).

**Tests PRIMERO — `backend/tests/test_plan267_inbox_verdict.py`:**

| Test | Qué prueba |
|---|---|
| `test_flag_off_la_bandeja_es_identica` | Con `STACKY_INCIDENT_INBOX_VERDICT_ENABLED=False`, ningún item tiene la clave `verdict` y el resto del payload es idéntico clave por clave. |
| `test_flag_on_agrega_verdict_solo_a_los_que_tienen_ejecucion` | Un ticket sin ejecuciones **no** recibe la clave. |
| `test_una_sola_query_extra` | Cuenta las queries del endpoint con 3 tickets y con 30: la diferencia debe ser **0** (no crece con el lote). |
| `test_ultima_ejecucion_es_la_mas_reciente` | Ticket con 3 ejecuciones de `started_at` distintos → el veredicto corresponde a la de `started_at` mayor. |
| `test_excepcion_en_el_veredicto_no_rompe_la_bandeja` | `evaluate_verdict` monkeypatcheado a lanzar → HTTP 200, `items` completos, sin clave `verdict`. |
| `test_no_se_agregan_estados_al_ticket` | El `stacky_status` de cada item es exactamente el mismo con la flag ON y OFF. |

**Comando de aceptación (BINARIO):**
```
cd "Stacky Agents/backend"
.venv\Scripts\python.exe -m pytest tests/test_plan267_inbox_verdict.py -v
.venv\Scripts\python.exe -m pytest tests/test_plan238_incident_inbox_api.py -v
```
**Criterio:** 6/6 verdes en el nuevo, y el del plan 238 **sin regresiones** (es el contrato de forma de la bandeja: `test_plan238_incident_inbox_api.py:147` verifica las claves obligatorias, que este plan **no quita**).
Además: `cd "Stacky Agents/frontend" && npx tsc --noEmit` sin errores nuevos.

**Flag:** `STACKY_INCIDENT_INBOX_VERDICT_ENABLED` — **default ON**, categoría `observabilidad_notif`. Solo lectura; una query indexada más por request que el operador ya estaba pidiendo.
**Impacto por runtime:** ninguno (lee `AgentExecution`, común a los 3). **Fallback:** una incidencia sin ejecuciones simplemente no muestra chip.
**Trabajo del operador:** ninguno.

---

### F6 — HITL: de "hay 7 falsos rojos" a "corregí este"

**Objetivo (1 frase):** Que la card de reconciliación liste los items concretos y ofrezca al operador un botón para corregir el estado de UNA incidencia, usando el endpoint que **no** publica en ningún sistema externo.

**Valor:** Cierra el GAP 3. Hoy el operador ve un número y no tiene camino.

**Archivos a editar:**
- `Stacky Agents/frontend/src/components/RunReconciliationCard.tsx`
- `Stacky Agents/frontend/src/components/RunReconciliationCard.module.css`
- `Stacky Agents/frontend/src/api/endpoints.ts`
**Archivo a crear (lógica pura):** `Stacky Agents/frontend/src/components/reconciliationActions.ts`
**Archivos de test a crear:** `Stacky Agents/frontend/src/components/reconciliationActions.test.ts` (colocado, como `incidentConsole.test.ts`) y `Stacky Agents/backend/tests/test_plan267_hitl_correccion.py`

**Regla dura del HITL (codificada en el módulo puro):**
```typescript
// Plan 267 F6 — qué acción ofrece cada discrepancia. PURO, sin fetch.
//
// RIEL DURO: Stacky NUNCA cambia un estado terminal por su cuenta. Este módulo
// solo decide QUÉ botón se ofrece; el cambio lo dispara un click del operador.
//
// RIEL DURO 2: la corrección va SIEMPRE a PATCH /api/tickets/{ticket_id}/stacky-status
// (backend/api/tickets.py:1165), que llama a ts.set_status y NO publica nada.
// Está PROHIBIDO usar /api/tickets/by-ado/{ado_id}/stacky-status
// (backend/api/tickets.py:1204) porque ese camino SÍ publica en ADO
// (backend/api/tickets.py:1406) y SÍ cambia el estado del work item (:1495).

export interface ReconciliationItem {
  execution_id: number;
  ticket_id: number;
  kind: string;
  detail: string;
}

export interface ItemAction {
  label: string;          // texto del botón
  targetStatus: string;   // stacky_status al que se movería
  confirm: string;        // texto de la confirmación explícita
  reason: string;         // se manda en el body como `reason`
}

/** Solo 2 de los 5 DISCREPANCY_KINDS tienen una corrección obvia y segura.
 *  Los otros 3 devuelven null: se listan para que el humano mire, sin botón. */
export function actionForItem(item: ReconciliationItem): ItemAction | null {
  if (item.kind === "red_with_delivered_work") {
    return {
      label: "Marcar como terminado",
      targetStatus: "completed",
      confirm: `La incidencia #${item.ticket_id} figura como fallada pero entregó trabajo. ¿La marcás como terminada?`,
      reason: `[267] corrección manual de falso rojo (execution ${item.execution_id})`,
    };
  }
  if (item.kind === "green_with_dirty_close") {
    return {
      label: "Marcar para revisión",
      targetStatus: "needs_review",
      confirm: `La incidencia #${item.ticket_id} figura como terminada sobre un cierre sucio. ¿La marcás para revisar?`,
      reason: `[267] cierre sucio confirmado por el operador (execution ${item.execution_id})`,
    };
  }
  return null;
}

/** La ruta EXACTA del endpoint permitido. Existe como función para que un
 *  test pueda asegurar que nadie escribió "by-ado" acá. */
export function correctionPath(ticketId: number): string {
  return `/api/tickets/${ticketId}/stacky-status`;
}
```

**En el `.tsx`:** debajo de la lista de contadores existente (`RunReconciliationCard.tsx:94-102`), agregar una lista de items (**cap de 25 filas** para no volcar 200 líneas en una card de diagnóstico) donde cada fila muestra `#ticket_id`, el `detail` y —si `actionForItem` devuelve algo— un `<Button size="sm">` que:
1. pide confirmación con el texto `action.confirm` (usa el `Dialog` canónico del repo; **no** `window.confirm`),
2. hace `PATCH` a `correctionPath(item.ticket_id)` con body `{ status: action.targetStatus, reason: action.reason }`,
3. al terminar vuelve a llamar `RunReconciliation.get()` para refrescar los contadores.

**Nota sobre el cliente HTTP:** usar `fetch` crudo o `rawPost`, **no** `api.patch`, porque el wrapper `api.*` **lanza** en cualquier respuesta non-2xx y una card de diagnóstico no debe romperse por eso. Mismo criterio que ya documenta `frontend/src/api/endpoints.ts:3168-3169` para `RunReconciliation.get()`.

**Tests PRIMERO — `frontend/src/components/reconciliationActions.test.ts`:**

| Test | Qué prueba |
|---|---|
| `red_with_delivered_work ofrece marcar terminado` | `targetStatus === "completed"` y el `confirm` contiene el número de ticket. |
| `green_with_dirty_close ofrece marcar para revisión` | `targetStatus === "needs_review"`. |
| `los otros 3 kinds no ofrecen acción` | `unclassified_outcome`, `drain_timeout`, `green_self_reported_only` → `null`. |
| `un kind del futuro no ofrece acción` | `actionForItem({kind:"kind_del_futuro",...})` → `null` (nunca un botón inventado). |
| `correctionPath nunca usa by-ado` | `expect(correctionPath(7)).toBe("/api/tickets/7/stacky-status")` y `expect(correctionPath(7)).not.toContain("by-ado")`. |
| `targetStatus siempre es un estado válido` | Los `targetStatus` de las 2 acciones ∈ `["completed","needs_review","error","cancelled","idle","running"]` (espejo de `VALID_TICKET_STATUSES`). |

**Tests PRIMERO — `backend/tests/test_plan267_hitl_correccion.py`:**

| Test | Qué prueba |
|---|---|
| `test_patch_por_ticket_id_no_publica` | `PATCH /api/tickets/<id>/stacky-status` con `{"status":"completed"}` → 200 y **cero** filas nuevas en `agent_html_publish`. **Es la prueba de que el HITL no escribe en el tracker real del operador.** |
| `test_patch_por_ticket_id_no_corre_post_hooks` | Se registra un post-hook que marca una bandera; tras el PATCH la bandera sigue en `False` (el guard y los hooks son de `on_execution_end`, no de `set_status`). |
| `test_correccion_queda_auditada` | Tras el PATCH existe un `TicketStatusEvent` con `changed_by` = el header `X-User-Email` (no `"system"`), lo que además hace que `run_reconciliation._self_reported_ticket_ids` lo vea como mano humana. |
| `test_estado_invalido_devuelve_400` | `{"status":"published"}` → 400 (`services/ticket_status.set_status` valida contra `VALID_TICKET_STATUSES`). |
| `test_flag_off_no_ofrece_hitl` | Con `STACKY_RUN_RECONCILIATION_HITL_ENABLED=False`, el payload de `/api/diag/run-reconciliation` **no** incluye la clave `hitl_enabled: true`, que es la que la card usa para decidir si dibuja botones. |

> **Nota:** F6 agrega al payload de `summarize()` una única clave nueva `"hitl_enabled": bool`. Es la forma de que la flag apague los botones **desde el backend**, sin que el frontend tenga que conocer flags.

**Comando de aceptación (BINARIO):**
```
cd "Stacky Agents/backend"
.venv\Scripts\python.exe -m pytest tests/test_plan267_hitl_correccion.py -v
.venv\Scripts\python.exe -m pytest tests/test_plan254_reconciliation.py -v

cd "Stacky Agents/frontend"
npx vitest run src/components/reconciliationActions.test.ts
npx tsc --noEmit
```
**Criterio:** 5/5 backend + 6/6 frontend verdes; el test del 254 sin regresiones; `tsc` limpio.

**Flag:** `STACKY_RUN_RECONCILIATION_HITL_ENABLED` — **default ON**, categoría `observabilidad_notif`.
**Justificación explícita del default ON** (porque es la única flag de este plan que habilita una escritura): la escritura la dispara **el humano** con un click y una confirmación, va a la **propia base de Stacky** (`stacky_status` + `TicketStatusEvent`), y el endpoint elegido **no publica en ADO/GitLab, no toca el repo, no corre DDL/DML en la BD del operador y no dispara post-hooks** — verificado en `backend/api/tickets.py:1188-1194`, que solo llama `ts.set_status`. Por lo tanto **no** cae en la excepción (B), que aplica a Stacky escribiendo **por su cuenta** en un sistema real del operador. Tampoco en la (A): no hay loop ni consumo de tokens. **Si el implementador se ve tentado de usar el endpoint `by-ado`, la flag pasaría a ser excepción (B) y default OFF — por eso está prohibido.**

**Impacto por runtime:** ninguno; opera sobre tickets, no sobre runners. **Fallback:** con la flag OFF la card queda exactamente como hoy (solo contadores).
**Trabajo del operador:** ninguno obligatorio. La corrección es una **oportunidad** que aparece solo cuando hay una discrepancia real; si no hay ninguna, la card sigue diciendo "0" y no pide nada.

---

### F7 — Alta completa de las 5 flags y registro en el arnés

**Objetivo (1 frase):** Que las 5 flags estén dadas de alta en los 5 lugares de código y los 6 archivos de test estén registrados en los 2 scripts del arnés, con un test que lo demuestre.

**Valor:** Sin esta fase, `test_default_known_only_for_curated` y el meta-test de registro de tests quedan ROJOS y el plan "funciona" con el arnés roto.

**Archivos a editar (los 7 de la RECETA-FLAG, §3.7):**
1. `Stacky Agents/backend/config.py`
2. `Stacky Agents/backend/services/harness_flags.py` (bloque `FlagSpec`)
3. `Stacky Agents/backend/services/harness_flags.py` (`_CATEGORY_KEYS["observabilidad_notif"]`)
4. `Stacky Agents/backend/services/harness_flags_help.py` (`PLAIN_HELP`)
5. `Stacky Agents/backend/tests/test_harness_flags.py` (`_CURATED_DEFAULTS_ON`)
6. `Stacky Agents/backend/scripts/run_harness_tests.sh`
7. `Stacky Agents/backend/scripts/run_harness_tests.ps1`

**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan267_flags.py`

**Las 5 flags, exactas:**

| Key | Tipo | Default | Categoría | Fase | ¿Excepción? |
|---|---|---|---|---|---|
| `STACKY_RUN_VERDICT_ENABLED` | bool | **ON** | `observabilidad_notif` | F0 | No |
| `STACKY_RUN_EVIDENCE_COLLECTORS_ENABLED` | bool | **ON** | `observabilidad_notif` | F1 | No |
| `STACKY_UI_RUN_VERDICT_BADGE_ENABLED` | bool | **ON** | `observabilidad_notif` | F2/F3/F4 | No |
| `STACKY_INCIDENT_INBOX_VERDICT_ENABLED` | bool | **ON** | `observabilidad_notif` | F5 | No |
| `STACKY_RUN_RECONCILIATION_HITL_ENABLED` | bool | **ON** | `observabilidad_notif` | F6 | No (justificación completa en F6) |

**Ninguna declara `requires=`** (motivo verificado en §3.7): así no hay que tocar `_REQUIRES_MAP_FROZEN` (`backend/tests/test_harness_flags_requires.py:120`), cuyo test compara el mapa completo por igualdad (`:316`).
**Ninguna es numérica**, así que ninguna toca `_FROZEN_BOUNDS` (`backend/tests/test_harness_flags_bounds.py:149`).

**Los 6 archivos de test a registrar en los 2 scripts del arnés:**
```
tests/test_plan267_run_verdict.py
tests/test_plan267_run_evidence.py
tests/test_plan267_executions_payload.py
tests/test_plan267_inbox_verdict.py
tests/test_plan267_hitl_correccion.py
tests/test_plan267_flags.py
```
- En `run_harness_tests.sh`: una línea por archivo, **sin comillas ni comas**, con un comentario de encabezado del plan (patrón `:847-852`).
- En `run_harness_tests.ps1`: una línea por archivo, **entre comillas dobles y separadas por coma** (patrón `:762-765`). **Cuidado:** el último elemento del array no lleva coma final.

**Textos de `PlainHelp` (ya dentro de los topes de `test_harness_flags_help.py:47-50`):**

```python
"STACKY_RUN_VERDICT_ENABLED": PlainHelp(
    what="Decide si una corrida terminó bien, terminó con advertencias o falló de verdad, mirando además si dejó resultados.",
    on_effect="Si la activás: cada corrida muestra un veredicto de tres niveles con la causa. No cambia ningún estado por su cuenta.",
    off_effect="Si la apagás: se sigue viendo solo el estado crudo, como antes, sin el veredicto ni la explicación.",
    example="Como el mecánico que además de decir 'no arranca' te dice si el auto igual llegó a destino.",
),
"STACKY_RUN_EVIDENCE_COLLECTORS_ENABLED": PlainHelp(
    what="Busca las pruebas de que una corrida dejó resultados: archivos, comentario publicado, cambios en el repositorio y controles pasados.",
    on_effect="Si la activás: el veredicto se apoya en pruebas concretas y te dice cuáles encontró y cuáles no.",
    off_effect="Si la apagás: el veredicto no puede comprobar nada y queda siempre en advertencia por falta de pruebas.",
    example="Como pedir el remito antes de dar por entregado un pedido.",
),
"STACKY_UI_RUN_VERDICT_BADGE_ENABLED": PlainHelp(
    what="Muestra el veredicto de tres niveles en la lista de corridas, no solo adentro del detalle.",
    on_effect="Si la activás: cada fila muestra si terminó bien, con advertencias o con un error real, y podés filtrar por eso.",
    off_effect="Si la apagás: la lista queda como antes, con el estado crudo y sin la columna de veredicto.",
    example="Como el semáforo de tres luces en vez de una lamparita que solo se prende o se apaga.",
),
"STACKY_INCIDENT_INBOX_VERDICT_ENABLED": PlainHelp(
    what="Muestra en la bandeja de incidencias el veredicto de la última corrida de cada una.",
    on_effect="Si la activás: ves de un vistazo qué incidencias necesitan atención de verdad y cuáles solo figuran mal.",
    off_effect="Si la apagás: la bandeja se ve igual que antes y hay que abrir cada incidencia para saberlo.",
    example="Como marcar en la lista del consultorio quién está grave y quién solo espera el alta.",
),
"STACKY_RUN_RECONCILIATION_HITL_ENABLED": PlainHelp(
    what="Te deja corregir a mano, desde la pantalla, el estado de una corrida que quedó mal marcada.",
    on_effect="Si la activás: aparece un botón para arreglar cada caso. Nada se corrige solo: siempre decidís vos y queda registrado.",
    off_effect="Si la apagás: seguís viendo cuántos casos hay mal marcados, pero no hay botón para corregirlos desde ahí.",
    example="Como el arqueo de caja que además te deja anotar el ajuste, pero solo si vos lo firmás.",
),
```

**Tests PRIMERO — `backend/tests/test_plan267_flags.py`** (patrón copiado de `backend/tests/test_evolution_flags.py:55,83`):

| Test | Qué prueba |
|---|---|
| `test_las_5_flags_estan_en_el_registro` | Cada key ∈ `FLAG_REGISTRY`. |
| `test_las_5_son_default_true` | `spec.default is True` para las 5. |
| `test_las_5_estan_categorizadas` | Cada key aparece en el aplanado de `_CATEGORY_KEYS.values()`. |
| `test_las_5_tienen_plain_help` | Cada key ∈ `PLAIN_HELP` de `services.harness_flags_help`. |
| `test_las_5_estan_curadas` | Cada key ∈ `tests.test_harness_flags._CURATED_DEFAULTS_ON`. |
| `test_las_5_estan_en_config` | `hasattr(config.config, key)` y el valor por defecto es `True`. |
| `test_ninguna_declara_requires` | `getattr(spec, "requires", None)` es falsy para las 5 (así `_REQUIRES_MAP_FROZEN` no cambia). |
| `test_los_6_tests_estan_en_los_dos_scripts` | Lee `scripts/run_harness_tests.sh` y `scripts/run_harness_tests.ps1` como texto y asegura que cada uno de los 6 nombres de archivo aparece en **ambos**. |

**Comando de aceptación (BINARIO):**
```
cd "Stacky Agents/backend"
.venv\Scripts\python.exe -m pytest tests/test_plan267_flags.py -v
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -v
.venv\Scripts\python.exe -m pytest tests/test_harness_flags_help.py -v
.venv\Scripts\python.exe -m pytest tests/test_harness_flags_requires.py -v
.venv\Scripts\python.exe -m pytest tests/test_harness_flags_bounds.py -v
```
**Criterio:** 8/8 verdes en el nuevo. En los otros 4: **cero fallos nuevos respecto a HEAD**.
> **Gotcha conocido y cómo tratarlo:** `test_harness_flags_help.py` tiene fallos ajenos preexistentes en este árbol. **No se argumenta "ya estaba rojo": se prueba.** Antes de tocar nada, correr esos 4 archivos y guardar la salida; después de F7, comparar. Si aparece un fallo que menciona una key de este plan, es propio y hay que arreglarlo; si menciona otra key, es ajeno y se documenta con el diff de salidas.

**Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno (todas ON de fábrica).

---

### F8 — KPI medido y cierre

**Objetivo (1 frase):** Que el plan pueda demostrar con un número que redujo el falso error visible, y no solo afirmarlo.

**Valor:** Es la lección del 254 F5 aplicada a sí mismo: sin medición, "creemos que lo arreglamos".

**Archivos a editar:**
- `Stacky Agents/backend/services/run_verdict.py` (agregar el contador; sigue siendo el único módulo que conoce el veredicto)
- `Stacky Agents/backend/api/diag.py` (extender el payload de `/run-reconciliation`, `:987-1016`)
- `Stacky Agents/frontend/src/components/RunReconciliationCard.tsx` (mostrar el conteo por nivel)
**Archivo de test:** se **amplía** `Stacky Agents/backend/tests/test_plan267_run_verdict.py` (no se crea uno nuevo: menos archivos que registrar en el arnés).

**Función a agregar (read-only, sin loop, bajo demanda):**
```python
def count_by_level(days: int = 30) -> dict:
    """Cuántas corridas terminadas de los últimos N días caen en cada nivel.

    READ-ONLY: no escribe una sola fila. Bajo demanda: NO corre en un loop ni en
    un daemon. Nunca lanza: ante cualquier fallo devuelve los 3 niveles en 0.

    Vive acá y no en un módulo nuevo para que `run_verdict.py` siga siendo el
    único dueño del vocabulario del veredicto. La parte pura (evaluate_verdict)
    no se contamina: esta función importa DB de forma perezosa, adentro.
    """
```
Devuelve exactamente:
```json
{"days": 30, "exito": 0, "advertencia": 0, "error_real": 0, "falso_rojo_probable": 0}
```
Declarando **siempre** las 4 claves aunque valgan 0 (mismo criterio que `run_reconciliation.summarize()`, `services/run_reconciliation.py:223`: *"un contador que desaparece cuando vale cero no sirve para mirar una tendencia"*).

**En `api/diag.py:1015`,** justo antes de `result["ok"] = True`, agregar:
```python
try:
    from services.run_verdict import count_by_level  # noqa: PLC0415
    result["verdict_counts"] = count_by_level(days=30)
except Exception:  # noqa: BLE001
    logger.debug("verdict_counts 267 falló", exc_info=True)
result["hitl_enabled"] = bool(getattr(_config.config, "STACKY_RUN_RECONCILIATION_HITL_ENABLED", True))
```

**Tests a agregar en `test_plan267_run_verdict.py`:**

| Test | Qué prueba |
|---|---|
| `test_count_by_level_declara_las_4_claves_siempre` | Con base vacía devuelve las 4 en 0, nunca un dict parcial. |
| `test_count_by_level_nunca_lanza` | Con `session_scope` monkeypatcheado a lanzar → las 4 claves en 0. |
| `test_count_by_level_no_escribe` | Sesión falsa cuyos `add/commit/flush` lanzan `AssertionError` → pasa. |

**Comando de aceptación (BINARIO):**
```
cd "Stacky Agents/backend"
.venv\Scripts\python.exe -m pytest tests/test_plan267_run_verdict.py -v
```
**Criterio:** 18/18 verdes (15 de F0 + 3 de F8). Y la medición final de K1, anotada en §1:
```
.venv\Scripts\python.exe -c "from services.run_verdict import count_by_level; print(count_by_level(30))"
```

**Flag:** `STACKY_RUN_VERDICT_ENABLED` (la de F0). Con ella OFF, `count_by_level` devuelve las 4 claves en 0 y la card no muestra la línea.
**Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Mitigación (concreta y verificable) |
|---|---|---|
| R1 | **Crear un falso VERDE nuevo** — el peor resultado posible; convertiría este plan en un retroceso. | Invariante `I1` codificado en `test_I1_un_error_jamas_recibe_exito`, que barre la grilla **completa** de combinaciones. Estructuralmente: la regla 6 (única que produce `exito`) es inalcanzable desde `base == "error_real"`. |
| R2 | **La ignorancia se lee como éxito** — una fuente caída hace parecer que todo entregó. | Invariante `I2` codificado. `None` suma 0 en `delivery_strength` (igual que `False`) y, en la rama verde, dispara `evidencia_indeterminada` (advertencia). Nunca mejora el nivel. |
| R3 | **Los colectores degradan la performance del listado** — lecturas de disco por fila. | `_Budget` es un presupuesto **TOTAL del lote** (`COLLECTOR_BUDGET_S = 2.0`), consultado antes de cada lectura; agotado ⇒ `None` y sigue. `publicado_en_tracker` es **1 query** para todo el lote. `test_publicado_en_una_sola_query` y `test_sin_n_mas_uno` lo prueban. La bandeja agrega **exactamente 1** query indexada (`ix_exec_ticket_started`, `models.py:278`), probado por `test_una_sola_query_extra`. |
| R4 | **Se rompe el listado si un colector falla.** | Todo el bloque de veredicto está envuelto en `try/except Exception` que degrada a `{}` y loguea en `debug`. Probado por `test_colector_que_lanza_no_rompe_el_listado` y `test_excepcion_en_el_veredicto_no_rompe_la_bandeja`. |
| R5 | **El implementador usa el endpoint `by-ado` y publica en el ADO real del operador.** | Prohibición escrita en 3 lugares del plan (§3.6, F6, comentario del módulo) + test `correctionPath nunca usa by-ado` + test backend `test_patch_por_ticket_id_no_publica` que cuenta filas en `agent_html_publish`. |
| R6 | **Hipótesis no probadas sobre la forma de `contract_result` y de la verificación** (H1 y H2). | **Declaradas como hipótesis** en F1, con tests que las **DISCRIMINAN**: se prueban las 2 formas plausibles y se prueba que una tercera forma devuelve `False`/`None` (no `True`). Si el árbol usa otra clave, el implementador la agrega a la condición **y al test**. |
| R7 | **Alta de flag incompleta** ⇒ `test_default_known_only_for_curated` rojo. | F7 lista los 7 archivos con el anclaje del patrón a copiar, y `test_plan267_flags.py` verifica los 5 lugares + los 2 scripts del arnés en 8 asserts. |
| R8 | **Rojos preexistentes ajenos** en `test_harness_flags_help.py` se atribuyen a este plan. | F7 obliga a capturar la salida de los 4 archivos de flags **antes** de tocar nada y comparar después. Si el fallo menciona una key ajena, se documenta con el diff; no se argumenta de memoria. |
| R9 | **Columna nueva sin `<th>`** desalinea la tabla del historial. | Nota explícita en F4 + gate `npx tsc --noEmit` y verificación visual manual (el render no es automatizable acá, ver §3.8 punto 2). |
| R10 | **Estilo inline en un `.tsx`** dispara el ratchet de deuda de UI. | El plan no crea ningún `.tsx` nuevo; los badges usan CSS Modules con `data-tone`. Gate: `grep -c "style={{"` no debe aumentar respecto a HEAD en los 3 `.tsx` editados. |
| R11 | **Contaminación cross-file de vitest** da un falso rojo/verde. | Todos los comandos de aceptación del frontend corren **un archivo por vez** con `npx vitest run <ruta>`. |
| R12 | **`SQLITE_LOCKED` bajo pytest** hace flaky un test de backend. | Todos los comandos corren **un archivo por vez**. Si un test de este plan resulta flaky, se corre 8-12 veces antes de declararlo verde. |
| R13 | **Regresión sobre el 254**, que acaba de estabilizar el cierre. | Este plan **no toca ningún sitio de cierre** (P3). F2 y F6 exigen correr `test_plan254_outcome_reason.py` y `test_plan254_reconciliation.py` sin regresiones. |

---

## 7. Fuera de scope (explícito)

1. **`pages/TicketBoard.tsx`** — no se toca. Tiene 1355 líneas, colores hardcodeados sin módulo puro (`:82`, `:103`) y una cola de trabajo ajena pendiente. Agregar el veredicto ahí es un plan aparte que primero debe extraer `stateColor()` a un `.ts` puro.
2. **Cambiar `status_vocabulary.py`** — no se agrega ni un estado. El veredicto es una dimensión separada (P5).
3. **Modificar `classify_outcome_reason`** — la firma del 254 (`services/run_outcome.py:55`) queda **intacta**. Agregarle parámetros rompería sus 4 call-sites y sus tests.
4. **Corrección automática de estados** — Stacky nunca corrige por su cuenta. Ni con un umbral, ni con "alta confianza", ni con un modo experto.
5. **Llamar a la API de ADO/GitLab para verificar la publicación** — la evidencia sale de la tabla local `agent_html_publish`. Nada de red en un colector.
6. **Un barrido periódico del veredicto** — nada corre en loop. Si algún día se quisiera, se engancharía al `_maintenance_loop` compartido del plan 253 F4, como ya documenta `run_reconciliation.py:11-13`; no se inventa otro loop.
7. **Reintentar corridas desde la card de reconciliación** — el HITL de F6 solo corrige el estado. Reintentar es otra capacidad, con otro riesgo.
8. **Tests de render de React** — imposible en este repo (§3.8 punto 2). La verificación visual es manual.

---

## 8. Glosario, orden de implementación y DoD

### Glosario

| Término | Significado en este plan |
|---|---|
| **`outcome_reason`** | Los 9 desenlaces del 254 (`services/run_outcome.py:13`). Responde **por qué terminó**. Señales del proceso. |
| **Veredicto** | Los 3 niveles del 267 (`exito` / `advertencia` / `error_real`). Responde **si cumplió su objetivo**. Combina el `outcome_reason` con evidencia. |
| **Señal de evidencia** | Uno de los 5 hechos de `EVIDENCE_SIGNALS`, tri-estado: `True` presente, `False` ausente, `None` **desconocida**. |
| **Fuerza de entrega** | Suma de pesos de las señales **presentes**. Umbral `UMBRAL_ENTREGA = 2`. |
| **Falso rojo** | Corrida con estado `error` que sí entregó trabajo. En el 267 recibe causa `falso_rojo_probable` y nivel `advertencia` — **nunca** `exito` automático. |
| **Nivel base** | Nivel derivado solo del estado terminal, antes de mirar evidencia (`_STATUS_TO_BASE`). |
| **HITL** | El humano decide y hace click. Stacky ofrece, nunca ejecuta por su cuenta. |

### Orden de implementación (dependencias estrictas)

```
F0 (puro, sin dependencias)
 └─ F1 (usa EvidenceSignals de F0)
     └─ F2 (usa F0 + F1)
         ├─ F3 (puro frontend; solo necesita la FORMA del payload de F2)
         │   └─ F4 (usa F3)
         └─ F5 (usa F0 + F1; independiente de F3/F4)
F6 (independiente de F0-F5: solo necesita el payload del 254 F5 que YA existe)
F7 (después de F0..F6: registra las 5 flags y los 6 tests)
F8 (después de F0 y F7)
```
**F6 se puede implementar en paralelo** con F0-F5 si conviene: no depende de la capa de veredicto, solo del `items` que `run_reconciliation.summarize()` **ya** devuelve hoy.

### Definición de Hecho (DoD) global

- [ ] Existe `backend/services/run_verdict.py`, **puro** (0 imports de `db`/`models` a nivel de módulo; el único import de DB es perezoso, dentro de `count_by_level`). Verificable: `grep -n "^from db\|^from models\|^import db" backend/services/run_verdict.py` → 0 hits.
- [ ] Existe `backend/services/run_evidence.py` y **no escribe nada**. Verificable: `test_no_escribe_nada` verde.
- [ ] **Invariante I1 verde:** ningún `error` recibe `exito` en la grilla completa (`test_I1_un_error_jamas_recibe_exito`).
- [ ] **Invariante I2 verde:** `None` nunca mejora el nivel (`test_I2_desconocido_nunca_mejora`).
- [ ] `status_vocabulary.py` **sin cambios**. Verificable: `git diff --stat -- backend/services/status_vocabulary.py` → vacío.
- [ ] `run_outcome.py` **sin cambios** de firma. Verificable: `git diff -- backend/services/run_outcome.py` → vacío.
- [ ] El payload de ejecuciones trae `verdict` con sus 6 subclaves con la flag ON, y **no trae la clave** con la flag OFF.
- [ ] La fila del historial muestra el chip de veredicto: `grep -c "verdictChipTone" frontend/src/pages/ExecutionHistoryPage.tsx` ≥ 1.
- [ ] La bandeja de incidencias muestra el chip: `grep -c "describeVerdict" frontend/src/pages/IncidentInboxPage.tsx` ≥ 1.
- [ ] La card de reconciliación renderiza items con acción: `grep -c "actionForItem" frontend/src/components/RunReconciliationCard.tsx` ≥ 1.
- [ ] El HITL usa **solo** el endpoint por `ticket_id`: `grep -c "by-ado" frontend/src/components/reconciliationActions.ts` = **0**.
- [ ] Las **5 flags** están en los 5 lugares con `default=True` (`test_plan267_flags.py` 8/8 verde).
- [ ] Los **6 archivos de test** están registrados en `run_harness_tests.sh` **y** en `run_harness_tests.ps1`.
- [ ] Los 6 archivos de test de backend corren **por archivo** y dan verde:
      `test_plan267_run_verdict.py` (18) · `test_plan267_run_evidence.py` (12) · `test_plan267_executions_payload.py` (6) · `test_plan267_inbox_verdict.py` (6) · `test_plan267_hitl_correccion.py` (5) · `test_plan267_flags.py` (8).
- [ ] Los 2 archivos de test de frontend corren **por archivo** y dan verde:
      `plan267RunVerdict.test.ts` (13) · `reconciliationActions.test.ts` (6).
- [ ] `cd "Stacky Agents/frontend" && npx tsc --noEmit` sin errores nuevos.
- [ ] **Sin regresiones del 254**, validado por archivo: `test_plan254_outcome_reason.py`, `test_plan254_reconciliation.py`, `test_plan254_falso_rojo.py`, `test_plan254_stream_drain.py`.
- [ ] **Sin regresiones del 238**: `test_plan238_incident_inbox_api.py` verde (contrato de forma de la bandeja).
- [ ] Los KPI K1 y K2 están **medidos y anotados** en la tabla de §1 (no "SIN MEDIR").
- [ ] Ningún estilo inline nuevo: `grep -c "style={{"` no aumenta en los 3 `.tsx` editados respecto a HEAD.
- [ ] **Cero autonomía nueva:** ningún loop, daemon, barrido ni polling agregado. Verificable: `git diff | grep -cE "while True|Thread\(|schedule|setInterval"` = 0.
