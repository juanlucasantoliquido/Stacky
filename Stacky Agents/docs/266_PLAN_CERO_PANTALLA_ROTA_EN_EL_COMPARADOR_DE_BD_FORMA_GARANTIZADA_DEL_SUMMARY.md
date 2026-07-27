# Plan 266 — Cero pantalla rota en el Comparador de BD: forma garantizada del `summary`

**Estado:** PROPUESTO v1
**Fecha:** 2026-07-27
**Rama sugerida:** `feat/plan-266-summary-shape`
**Serie:** independiente (cierra una incidencia REAL reportada por el operador)

---

## 1. Objetivo y KPI

Eliminar de raíz la clase de bug que hoy rompe una pestaña entera del Comparador de BD: la UI
lee campos anidados del `summary` de una corrida (`by_severity`, `by_action`, `by_object_type`)
asumiendo que **siempre** están, mientras que el backend persiste cada corrida como JSON suelto
en disco **sin normalizar ni versionar** y ya se defiende de esa ausencia en cinco lugares
distintos. El plan introduce un único módulo puro de normalización en el frontend
(`summaryShape.ts`), lo adopta en los **8 accesos profundos sin guarda** que existen hoy,
endurece el **borde de lectura** del backend (`dbcompare_runs.list_runs`/`get_run`) para que
ningún payload salga con el `summary` a medio formar, planta un **centinela quirúrgico** que
impide que el patrón vuelva, y convierte el `PageErrorBoundary` de "un mensaje suelto" en un
diagnóstico accionable (superficie + componente + stack copiable en 1 click).

### KPI (medibles, con el comando que los verifica)

| # | KPI | Medición | Comando |
|---|-----|----------|---------|
| KPI-1 | Accesos profundos sin guarda en `frontend/src/components/dbcompare/**`: **8 → 0** | censo del centinela F4 | `npx vitest run src/__tests__/dbcompareSummaryShapeRatchet.test.ts` |
| KPI-2 | Una corrida con `summary` sin `by_severity` **no lanza**: radar, timeline y hero renderizan ceros | tests puros F0 | `npx vitest run src/components/dbcompare/__tests__/summaryShapeCrash.test.ts` |
| KPI-3 | 100% de los runs `status=done` devueltos por `list_runs`/`get_run` traen los 3 mapas completos con enteros | test backend F0/F3 | `.venv\Scripts\python.exe -m pytest tests/test_plan266_summary_shape.py -q` |
| KPI-4 | El fallback del boundary pasa de 1 dato (mensaje) a 4 (superficie, componente, mensaje, stack copiable) | test puro F5 | `npx vitest run src/components/__tests__/errorBoundaryDiagnostics.test.ts` |
| KPI-5 | Gate de tipos verde con todos los cambios | `tsc --noEmit` | `npm run build` (en `Stacky Agents/frontend`) |

---

## 2. Por qué ahora — la incidencia real y la clase de bug

### 2.1 La incidencia (textual, reportada por el operador en el Comparador de BD)

```
Esta pestaña falló al renderizar
Cannot read properties of undefined (reading 'danger')
El resto de la aplicación sigue funcionando. Podés reintentar o cambiar de pestaña.
```

Ese texto no es un error del backend: sale del boundary por página.
`Stacky Agents/frontend/src/components/PageErrorBoundary.tsx:60` renderiza
`Esta pestaña falló al renderizar`, `:62` muestra `this.state.error?.message` (de ahí sale el
`Cannot read properties of undefined (reading 'danger')`) y `:65` el aviso
`El resto de la aplicación sigue funcionando…`. Es decir: **un `throw` en el RENDER de un
componente del Comparador de BD**.

### 2.2 La causa raíz #1 — auto-evidente por inconsistencia interna del mismo archivo

`Stacky Agents/frontend/src/components/dbcompare/radarLogic.ts:60`:

```ts
const sev = r.summary!.by_severity;   // :60
return {
  t: r.finished_at || "",
  danger: sev.danger || 0,            // :63  <-- "Cannot read properties of undefined (reading 'danger')"
```

El filtro previo (`radarLogic.ts:56`) solo comprueba `!!r.summary`, **no** que traiga
`by_severity`. Si un `CompareRun` tiene `summary` truthy pero sin `by_severity`, `sev` es
`undefined` y `sev.danger` lanza **exactamente** el mensaje reportado.

Que el campo PUEDE faltar lo prueba **el mismo archivo**, que ya se defiende dos veces:

- `radarLogic.ts:31` → `const sev = cell.by_severity || { info: 0, warn: 0, danger: 0 };`
- `radarLogic.ts:104` → idéntico.

`trendSeries()` (`radarLogic.ts:45-68`) es la única que no se defiende, y es la que corre en el
render: `EnvironmentRadar.tsx:152` → `const trend = selected ? trendSeries(runs, selected.source, selected.target) : [];`

### 2.3 La clase de bug — censo COMPLETO de los 8 accesos profundos sin guarda

Verificado línea por línea (2026-07-27) sobre `frontend/src/components/dbcompare/`:

| # | Archivo:línea | Expresión hoy | Mensaje que produce si falta el mapa |
|---|---------------|---------------|--------------------------------------|
| 1 | `radarLogic.ts:60` | `const sev = r.summary!.by_severity;` (+ `sev.danger` en `:63`) | `reading 'danger'` |
| 2 | `RunsTimeline.tsx:37` | `run.summary.by_severity.danger` (guardado SOLO por `run.summary &&` en `:35`) | `reading 'danger'` |
| 3 | `RunsTimeline.tsx:38` | `run.summary.by_severity.warn` / `.info` | `reading 'warn'` |
| 4 | `EnvironmentRadar.tsx:144` | `const sev = r.diff.summary.by_severity;` (+ `${sev.danger}` en `:146`) | `reading 'danger'` |
| 5 | `EnvironmentRadar.tsx:215` | `(cell.by_severity.danger \|\| 0) + (cell.by_severity.warn \|\| 0)` | `reading 'danger'` |
| 6 | `SummaryHero.tsx:145` | `summary.by_object_type[t]` con `t ∈ {table,view,sequence}` | `reading 'table'` |
| 7 | `svgMath.ts:43` | `diff.summary.by_severity[severity]` con `SEVERITY_ORDER = ["danger","warn","info"]` (`svgMath.ts:39`) | `reading 'danger'` |
| 8 | `svgMath.ts:47` | `diff.summary.by_action[action]` con `ACTION_ORDER = ["added","removed","changed"]` (`svgMath.ts:40`) | `reading 'added'` |

`svgMath.severityCounters/actionCounters` se llaman en el render de `SummaryHero.tsx:83`,
`:84`, `:116` y `:130` — o sea que el hero del resultado también rompe la pestaña entera.

**Corrección al dossier de entrada:** `EnvironmentRadar.tsx:215` es un acceso crudo real, pero
el par `radarLogic.ts:31` / `:104` **sí** está guardado (ambos con `|| {info,warn,danger}`); no
se cuentan como violaciones, se migran igual para unificar el criterio (y porque hoy no
protegen contra valores **no numéricos**, solo contra el mapa ausente).

### 2.4 Por qué el dato puede venir incompleto (origen backend, verificado)

- Las corridas se persisten como **JSON suelto en disco, sin versión de esquema ni
  normalización de lectura**: `backend/services/dbcompare_runs.py:68` (`_write_run`),
  `:109` (`_read_run`), y `list_runs()` en `:326-340`, que hace
  `_runs_dir().glob("*.json")` y devuelve el JSON **tal cual** (solo saca `diff`/`data_diff`
  en `:336`). Un run escrito por una versión anterior, a medio escribir, o traído de otra
  máquina entra a la UI con la forma que tenga.
- El run **nace** con `"summary": None` (`dbcompare_runs.py:265`) y recién en el éxito se
  setea completo (`:304` → `summary=diff["summary"]`). Una corrida interrumpida queda con
  formas intermedias.
- El **backend ya se defiende** de la falta de `by_severity` en cinco lugares — la prueba
  más dura de que el hueco es real y conocido:
  - `backend/services/dbcompare_watch.py:226` → `sev = (summary or {}).get("by_severity") or {}`
  - `backend/services/dbcompare_watch.py:238-239` → `prev.get("by_severity") or {}` / `new_summary.get("by_severity") or {}`
  - `backend/services/dbcompare_watch.py:397` → `... or {"info": 0, "warn": 0, "danger": 0}`
  - `backend/api/db_compare_watch.py:153` → `sev = (meta["summary"] or {}).get("by_severity") or {}` —
    y este emite `by_severity: {}` (dict **vacío**) hacia la celda del radar en `:161`, que es
    exactamente la forma que revienta `EnvironmentRadar.tsx:215`.
- La forma canónica la produce `backend/services/dbcompare_diff.py:321-337` (`summarize()`,
  con `by_severity = {"info": 0, "warn": 0, "danger": 0}` en `:322`).

**Conclusión:** el frontend confía en un contrato que el backend nunca garantizó. Se arregla
en los dos lados (el backend deja de emitir formas parciales; el frontend deja de asumir), y
se planta un centinela para que el patrón no vuelva por un archivo nuevo.

### 2.5 El gap secundario: el boundary no dice nada útil

`PageErrorBoundary.componentDidCatch` (`:30-43`) recibe `info: React.ErrorInfo` —que trae el
`componentStack`— y **lo descarta**: solo lo manda a `console.error` (`:32`) y publica en el
Centro de Actividad un `body: String(error?.message || error)` (`:40`), sin nombre de
componente ni superficie. El operador ve `Cannot read properties of undefined (reading
'danger')` y no tiene forma de saber **qué** componente ni **qué** pestaña. Esto costó una
sesión entera de investigación para esta incidencia; es deuda de diagnóstico, no cosmética.

---

## 3. Principios y guardarraíles

1. **El arreglo del crash NO va detrás de una flag.** Una flag que pueda re-habilitar un
   `throw` en el render es absurda. F1/F2/F5 son incondicionales. La única flag nueva gatea el
   cambio de **forma del payload** del backend (F3), que sí es un cambio de contrato observable
   y merece kill-switch auditable.
2. **Defensa en profundidad, no sustitución.** El backend normaliza y el frontend igual
   normaliza. Un payload que venga de una versión vieja del backend, de un `localStorage`, o
   de un `fetch` a mano sigue sin poder romper la pantalla.
3. **Normalización solo-lectura, en memoria.** No se reescribe ni migra ningún JSON de corridas
   del operador en disco. (Ver §6, Fuera de scope.)
4. **`summary: null` se conserva como `null`.** Un run `running` legítimamente no tiene summary;
   convertirlo en `{}` con ceros haría que `RunsTimeline.tsx:35` y `db_compare_watch.py:146`
   muestren/cuenten "0 danger" para corridas que todavía no compararon nada. Eso sería mentir.
5. **Toda la lógica testeable vive en `.ts` puros.** El repo **no tiene RTL ni jsdom**
   (restricción estructural conocida; ver la nota en
   `frontend/src/components/__tests__/PageErrorBoundary.test.tsx:1-8`). Ningún test de este plan
   renderiza React. Patrón de la casa a copiar: `radarLogic.ts` + `radarLogic.test.ts`,
   `maskingLogic.ts` + `maskingLogic.test.ts`.
6. **Backward-compatible.** El payload solo **agrega** claves faltantes; nunca quita ni renombra.
   El título `Esta pestaña falló al renderizar` del boundary NO se toca
   (`frontend/src/components/__tests__/PageErrorBoundary.test.tsx:29` lo asserta).
7. **Cero trabajo para el operador.** Nada que configurar, nada que aprobar, nada que migrar.
8. **Centinela quirúrgico, no masivo.** Precedente doloroso de la casa: un centinela por regex
   destructivo ya rompió el motor de flags. El de F4 tiene un patrón determinable, una lista de
   exenciones explícita y controles negativos con fixtures (§F4.4 prueba por qué no puede tener
   falsos positivos masivos).
9. **Este documento vive en `Stacky Agents/docs/`, FUERA del alcance del centinela** (que solo
   escanea `frontend/src/components/dbcompare/`), así que la prosa de acá no puede disparar el
   gate. Gotcha recurrente de la casa: un comentario que contiene su propia cadena prohibida.

---

## 4. Fases

Convención de comandos:
- Backend: desde `Stacky Agents/backend`, intérprete `.venv\Scripts\python.exe` (venv py3.13).
  **Correr SIEMPRE por archivo** (contaminación de suite conocida).
- Frontend: desde `Stacky Agents/frontend`, `npx vitest run <ruta>`.
  **Correr SIEMPRE por archivo** (contaminación cross-file conocida).

---

### F0 — Reproducción: los rojos que hoy prueban el bug

**Objetivo (1 frase):** dejar por escrito, en dos tests que HOY fallan, el crash exacto que
reportó el operador y el payload parcial que lo origina.
**Valor:** sin esto el plan no prueba nada; con esto, cualquier regresión futura vuelve a dar rojo.

#### F0.1 — Frontend (rojo por `throw`)

**Archivo nuevo:** `Stacky Agents/frontend/src/components/dbcompare/__tests__/summaryShapeCrash.test.ts`

Casos (los 4 primeros deben lanzar HOY):

| Caso | Entrada | Aserción |
|------|---------|----------|
| `trendSeries no lanza con summary sin by_severity` | `runs = [runFixture({ summary: { parity_score: 91.7 } })]`, par `("DEV","QA")` | `expect(() => trendSeries(runs, "DEV", "QA")).not.toThrow()` y el punto resultante es `{ t, danger: 0, warn: 0, info: 0 }` |
| `severityCounters no lanza con summary sin by_severity` | `diff = { summary: { parity_score: 91.7 } } as unknown as SchemaDiff` | `not.toThrow()` y `[{danger:0},{warn:0},{info:0}]` (en el orden de `SEVERITY_ORDER`) |
| `actionCounters no lanza con summary sin by_action` | idem | `not.toThrow()` y los 3 en 0 |
| `severityCounters tolera by_severity vacío` | `summary.by_severity = {}` (la forma que emite `api/db_compare_watch.py:153`) | los 3 contadores en 0 |
| `trendSeries sigue devolviendo los valores reales cuando el summary está completo` | run `done` con `by_severity: {info:1, warn:2, danger:3}` | `[{ t: "...", danger: 3, warn: 2, info: 1 }]` — **control positivo: sin esto el fix podría devolver ceros siempre y el test seguiría verde** |

Helper del fixture (escribirlo en el propio archivo de test, sin dependencias nuevas):

```ts
function runFixture(over: Record<string, unknown>): CompareRun {
  return {
    run_id: "run_x", source_alias: "DEV", target_alias: "QA", engine: "sqlserver",
    mode: "fresh", status: "done", phase: "done",
    started_at: "2026-07-27T10:00:00Z", finished_at: "2026-07-27T10:01:00Z",
    duration_ms: 60000, source_snapshot_id: "s1", target_snapshot_id: "s2",
    summary: null, diff: null, error: null,
    ...over,
  } as unknown as CompareRun;
}
```

**Comando:**
`npx vitest run src/components/dbcompare/__tests__/summaryShapeCrash.test.ts`

**Criterio de aceptación (binario, EN ESTA FASE):** el comando falla y el output contiene
literalmente `Cannot read properties of undefined (reading 'danger')`. Si no aparece ese texto,
el test NO reproduce la incidencia y hay que corregirlo antes de seguir.

#### F0.2 — Backend (rojo por forma del payload)

**Archivo nuevo:** `Stacky Agents/backend/tests/test_plan266_summary_shape.py`

Setup común (sin Flask, sin DB — este test **no** importa `app`, así que no toca la base viva):

```python
import json
import pytest
from services import dbcompare_runs

def _run_dict(run_id, **over):
    base = {
        "run_id": run_id, "source_alias": "DEV", "target_alias": "QA",
        "engine": "sqlserver", "initiated_by": "operator", "mode": "fresh",
        "status": "done", "phase": "done",
        "started_at": "2026-07-27T10:00:00Z", "finished_at": "2026-07-27T10:01:00Z",
        "duration_ms": 60000, "source_snapshot_id": "s1", "target_snapshot_id": "s2",
        "summary": None, "diff": None, "error": None,
    }
    base.update(over)
    return base

@pytest.fixture
def runs_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(dbcompare_runs, "_runs_dir", lambda: tmp_path)
    return tmp_path

def _write(runs_dir, run):
    (runs_dir / f"{run['run_id']}.json").write_text(
        json.dumps(run, ensure_ascii=False), encoding="utf-8")
```

Casos:

| Test | Entrada en disco | Aserción |
|------|------------------|----------|
| `test_list_runs_completa_by_severity_faltante` | `summary={"parity_score": 91.7}` | `list_runs()[0]["summary"]["by_severity"] == {"info": 0, "warn": 0, "danger": 0}` |
| `test_list_runs_completa_by_action_y_by_object_type` | idem | ambos mapas completos con las 3 claves canónicas en 0 |
| `test_list_runs_completa_claves_parciales` | `by_severity={"danger": 3}` | `{"info": 0, "warn": 0, "danger": 3}` |
| `test_list_runs_coerce_valores_no_numericos` | `by_severity={"danger": "3", "warn": None, "info": -1}` | `{"info": 0, "warn": 0, "danger": 3}` (todos `int`) |
| `test_list_runs_preserva_summary_none` | `summary=None`, `status="running"` | `list_runs()[0]["summary"] is None` (**NO** un dict de ceros) |
| `test_get_run_normaliza_igual_que_list_runs` | `summary={"parity_score": 91.7}` | `get_run("r1")["summary"]["by_severity"] == {"info":0,"warn":0,"danger":0}` |
| `test_list_runs_no_altera_summary_completo` | summary canónico de `dbcompare_diff.summarize` | el dict sale **igual** (control positivo: la normalización no puede pisar datos buenos) |
| `test_list_runs_no_reescribe_el_archivo_en_disco` | `summary={"parity_score": 91.7}` | tras `list_runs()`, el contenido del `.json` sigue byte-idéntico (`path.read_bytes()` antes == después) |

**Comando:**
`.venv\Scripts\python.exe -m pytest tests/test_plan266_summary_shape.py -q`

**Criterio de aceptación (binario, EN ESTA FASE):** el comando falla con al menos 6 tests en
rojo por `KeyError`/`AssertionError` sobre `by_severity`. Los dos controles positivos
(`no_altera_summary_completo`, `no_reescribe_el_archivo_en_disco`) deben salir **verdes ya
hoy** — si alguno sale rojo, el fixture está mal armado.

**Flag que la protege:** ninguna (son tests).
**Impacto por runtime (Codex / Claude Code / Copilot):** neutro/idéntico en los 3 — es
frontend/backend de la app; el runtime solo implementa, no participa en la ejecución. Sin fallback necesario.
**Trabajo del operador:** ninguno.

---

### F1 — `summaryShape.ts`: el módulo puro de normalización

**Objetivo (1 frase):** una única fuente de verdad, testeada, que convierte cualquier cosa en
un `summary` con forma canónica y valores numéricos.
**Valor:** los 8 puntos de render dejan de tener cada uno su propia (o ninguna) defensa.

**Archivo nuevo:** `Stacky Agents/frontend/src/components/dbcompare/summaryShape.ts`

**API EXACTA (nombres congelados — el centinela de F4 depende de ellos):**

```ts
// Plan 266 — Forma garantizada del summary del Comparador de BD.
// ÚNICA fuente de verdad: ningún componente de dbcompare/ puede leer by_severity /
// by_action / by_object_type sin pasar por acá (lo verifica el ratchet
// src/__tests__/dbcompareSummaryShapeRatchet.test.ts).
//
// NOTA DE IMPLEMENTACIÓN (no cosmética): este módulo lee las claves con corchetes y
// literal de string — src["by_severity"] — y NUNCA con punto. Así el archivo no
// contiene el patrón que su propio ratchet prohíbe y no necesita estar en su allowlist.
import type { Severity, DiffAction, ObjectType, DiffSummary } from "./dbcompareTypes";

export const EMPTY_BY_SEVERITY: Record<Severity, number>;
export const EMPTY_BY_ACTION: Record<DiffAction, number>;
export const EMPTY_BY_OBJECT_TYPE: Record<ObjectType, number>;

export function toCount(value: unknown): number;
export function toScore(value: unknown): number;
export function safeBySeverity(raw: unknown): Record<Severity, number>;
export function safeByAction(raw: unknown): Record<DiffAction, number>;
export function safeByObjectType(raw: unknown): Record<ObjectType, number>;
export function safeSummary(raw: unknown): DiffSummary;
```

**Semántica de cada símbolo (sin ambigüedad):**

- `EMPTY_BY_SEVERITY = { info: 0, warn: 0, danger: 0 }` (orden de claves irrelevante).
  `EMPTY_BY_ACTION = { added: 0, removed: 0, changed: 0 }`.
  `EMPTY_BY_OBJECT_TYPE = { table: 0, view: 0, sequence: 0 }`.
  Declarados con `Object.freeze(...)` para que nadie los mute por accidente; las funciones
  **devuelven objetos nuevos**, nunca la constante.
- `toCount(value)` → entero `>= 0`. Reglas, en orden:
  `number` → se usa; `string` → `Number(value)`; cualquier otro tipo (incl. `null`,
  `undefined`, `boolean`, objeto, array) → `NaN`. Si el resultado no es finito o es `< 0` →
  `0`. Si no, `Math.floor(n)`.
- `toScore(value)` → número con 1 decimal, clampeado a `[0, 100]`. Misma coerción que
  `toCount`; no finito → `0`; luego `Math.min(100, Math.max(0, Math.round(n * 10) / 10))`.
  (Se separa de `toCount` porque `parity_score` es un float — `dbcompare_diff.py:329` hace
  `round(..., 1)` — y `Math.floor` lo corrompería.)
- `safeBySeverity(raw)` → `{ info, warn, danger }` con `toCount` en cada clave, leyendo de
  `raw` si es un objeto no-null, y de `{}` en cualquier otro caso.
  Ídem `safeByAction` (added/removed/changed) y `safeByObjectType` (table/view/sequence).
- `safeSummary(raw)` → `DiffSummary` **completo**:
  `by_severity`/`by_action`/`by_object_type` vía las 3 funciones anteriores,
  `objects_total` y `objects_unchanged` vía `toCount`, `parity_score` vía `toScore`.

**Implementación de referencia (pseudocódigo ejecutable):**

```ts
function asRecord(raw: unknown): Record<string, unknown> {
  return raw !== null && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
}

export function toCount(value: unknown): number {
  const n = typeof value === "number" ? value
          : typeof value === "string" ? Number(value)
          : NaN;
  if (!Number.isFinite(n) || n < 0) return 0;
  return Math.floor(n);
}

export function safeBySeverity(raw: unknown): Record<Severity, number> {
  const src = asRecord(raw);
  return { info: toCount(src["info"]), warn: toCount(src["warn"]), danger: toCount(src["danger"]) };
}

export function safeSummary(raw: unknown): DiffSummary {
  const src = asRecord(raw);
  return {
    by_severity: safeBySeverity(src["by_severity"]),
    by_action: safeByAction(src["by_action"]),
    by_object_type: safeByObjectType(src["by_object_type"]),
    objects_total: toCount(src["objects_total"]),
    objects_unchanged: toCount(src["objects_unchanged"]),
    parity_score: toScore(src["parity_score"]),
  };
}
```

**Tests PRIMERO.** Archivo nuevo:
`Stacky Agents/frontend/src/components/dbcompare/summaryShape.test.ts`
(sibling del módulo, patrón exacto de `radarLogic.test.ts` / `maskingLogic.test.ts`).

Casos borde obligatorios (uno por fila, sin agrupar):

| Entrada a `safeBySeverity` | Salida esperada |
|---|---|
| `undefined` | `{info:0, warn:0, danger:0}` |
| `null` | `{info:0, warn:0, danger:0}` |
| `{}` | `{info:0, warn:0, danger:0}` |
| `{ danger: 3 }` (parcial) | `{info:0, warn:0, danger:3}` |
| `{ danger: "3" }` (string numérico) | `{info:0, warn:0, danger:3}` |
| `{ danger: "abc" }` | `{info:0, warn:0, danger:0}` |
| `{ danger: -5 }` | `{info:0, warn:0, danger:0}` |
| `{ danger: 2.9 }` | `{info:0, warn:0, danger:2}` |
| `{ danger: NaN }` / `{ danger: Infinity }` | `{info:0, warn:0, danger:0}` |
| `{ danger: true }` | `{info:0, warn:0, danger:0}` |
| `42` (no objeto) | `{info:0, warn:0, danger:0}` |
| `"texto"` | `{info:0, warn:0, danger:0}` |
| `[1, 2, 3]` | `{info:0, warn:0, danger:0}` |
| `{ danger: 3, extra: 9 }` | `{info:0, warn:0, danger:3}` (la clave extra se descarta) |
| `{ info: 1, warn: 2, danger: 3 }` | `{info:1, warn:2, danger:3}` (**control positivo**) |

Más:
- `toScore`: `91.7 → 91.7`; `"91.7" → 91.7`; `120 → 100`; `-3 → 0`; `undefined → 0`;
  `91.74 → 91.7`; `null → 0`.
- `safeSummary(undefined)` devuelve el objeto completo con los 6 campos y los 3 mapas llenos de ceros.
- `safeSummary` no muta la entrada: `const src = {...}; safeSummary(src); expect(src).toEqual(copia)`.
- `safeBySeverity(EMPTY_BY_SEVERITY) !== EMPTY_BY_SEVERITY` (devuelve objeto nuevo).
- `safeByAction` y `safeByObjectType`: al menos los casos `undefined`, `{}`, parcial, completo.

**Comando:** `npx vitest run src/components/dbcompare/summaryShape.test.ts`
**Criterio de aceptación (binario):** el comando termina en `0 failed` con **≥ 28 tests**.
**Flag:** ninguna — es un módulo puro nuevo, sin efecto observable hasta F2. Un módulo detrás de
flag sería código muerto.
**Impacto por runtime:** neutro/idéntico en los 3.
**Trabajo del operador:** ninguno.

---

### F2 — Adopción en los 8 puntos de render (el fix del crash)

**Objetivo (1 frase):** que ningún componente de `dbcompare/` vuelva a leer un mapa del summary
sin pasar por `summaryShape.ts`.
**Valor:** cierra la incidencia reportada; F0.1 pasa a verde.

**Regla de estilo obligatoria (la exige el centinela de F4):** siempre **bindear a un local**
en la misma línea que la llamada al normalizador, y recién después leer la propiedad.

```ts
const sev = safeSummary(run.summary).by_severity;   // OK — la línea contiene safeSummary(
{sev.danger}                                        // OK — `sev` ya es un Record completo
```

```ts
{safeSummary(run.summary).by_severity.danger}       // PROHIBIDO por estilo aunque sea seguro:
                                                    // encadenar hace ilegible el censo
```

**Edición 1 — `frontend/src/components/dbcompare/radarLogic.ts`**

- Agregar al tope: `import { safeBySeverity, safeSummary } from "./summaryShape";`
- `:31` → `const sev = safeBySeverity(cell.by_severity);` (reemplaza el `|| {…}` ad-hoc)
- `:60` → `const sev = safeSummary(r.summary).by_severity;` y **borrar el `!`** de `r.summary!`
- `:104` → `const sev = safeBySeverity(cell.by_severity);`
- El filtro de `:56` (`!!r.summary`) se **conserva**: una corrida sin summary sigue sin generar
  punto de tendencia (principio §3.4).

**Edición 2 — `frontend/src/components/dbcompare/RunsTimeline.tsx`**

Convertir el cuerpo del `.map` (`:23`) de expresión a bloque y bindear antes del JSX:

```tsx
{sorted.map((run) => {
  const sum = safeSummary(run.summary);
  const sev = sum.by_severity;
  return (
    <div key={run.run_id} ...>
      ...
      {run.summary && (
        <div className={styles.recency}>
          {sum.parity_score}% · 🔴{sev.danger} 🟠{sev.warn} 🔵{sev.info}
        </div>
      )}
      ...
    </div>
  );
})}
```

El guard `{run.summary && (…)}` de `:35` se **conserva** tal cual (§3.4).
Import nuevo: `import { safeSummary } from "./summaryShape";`

**Edición 3 — `frontend/src/components/dbcompare/EnvironmentRadar.tsx`**

- Agregar `safeBySeverity, safeSummary` al import (el archivo ya importa de `./radarLogic`;
  agregar una línea nueva `import { safeBySeverity, safeSummary } from "./summaryShape";`).
- `:144-147`, dentro de `showBaselineDiff`:

```ts
const sum = safeSummary(r.diff?.summary);
const sev = sum.by_severity;
setBaselineDiffText(
  `Drift vs baseline de ${alias}: ${sev.danger} danger / ${sev.warn} warn / ${sev.info} info (paridad ${sum.parity_score})`,
);
```

- `:215`: dentro del bloque del `.map` de columnas (que ya es un bloque, `:194-218`), justo
  **después** del `if (cell === null) return (…)` de `:200-206`, agregar:

```ts
const sevCell = safeBySeverity(cell.by_severity);
```

y reemplazar `:215` por `{sevCell.danger + sevCell.warn}`.

**Edición 4 — `frontend/src/components/dbcompare/svgMath.ts`**

```ts
import { safeByAction, safeBySeverity } from "./summaryShape";

export function severityCounters(diff: SchemaDiff): { severity: Severity; count: number }[] {
  const sev = safeBySeverity(diff.summary?.by_severity);
  return SEVERITY_ORDER.map((severity) => ({ severity, count: sev[severity] }));
}

export function actionCounters(diff: SchemaDiff): { action: DiffAction; count: number }[] {
  const act = safeByAction(diff.summary?.by_action);
  return ACTION_ORDER.map((action) => ({ action, count: act[action] }));
}
```

Nota: `diff.summary` está tipado no-nullable, pero el `?.` es TypeScript legal y es
precisamente la defensa contra el payload real que no respeta el tipo. No lo saques.

**Edición 5 — `frontend/src/components/dbcompare/SummaryHero.tsx`**

- Import nuevo: `import { safeSummary } from "./summaryShape";`
- Después del guard `if (!diff || !summary) return null;` (`:65`), reemplazar `:67`:

```ts
const sum = safeSummary(summary);
const score = sum.parity_score;
const objTypes = sum.by_object_type;
```

- `:145` → `.map((t) => \`${objTypes[t]} ${OBJECT_TYPE_LABEL[t]}\`)`
- `:147` → `{sum.objects_unchanged} sin diferencias`

**Tests:** los de F0.1 (que pasan de rojo a verde) más un caso nuevo en el mismo archivo:

| Test | Aserción |
|---|---|
| `EnvironmentRadar: celda con by_severity vacío suma 0` | `safeBySeverity({}).danger + safeBySeverity({}).warn === 0` (cubre la forma que emite `api/db_compare_watch.py:153`) |

**Comandos (los 4, por archivo):**
```
npx vitest run src/components/dbcompare/__tests__/summaryShapeCrash.test.ts
npx vitest run src/components/dbcompare/radarLogic.test.ts
npx vitest run src/components/dbcompare/__tests__/svgMath.test.ts
npx vitest run src/components/dbcompare/__tests__/runHistory.test.ts
```

**Criterio de aceptación (binario):** los 4 comandos terminan en `0 failed`, y el primero —que
antes fallaba con `reading 'danger'`— ahora pasa. Los tests existentes de `svgMath` y
`radarLogic` NO cambian: si alguno hay que tocarlo, el fix cambió comportamiento y hay que
revisarlo.

**Flag:** ninguna (ver §3.1). **Impacto por runtime:** neutro/idéntico en los 3.
**Trabajo del operador:** ninguno.

---

### F3 — Borde de lectura del backend: ningún payload sale a medio formar

**Objetivo (1 frase):** normalizar el `summary` en memoria en las **dos** funciones por las que
salen todos los runs, sin tocar un solo byte del disco.
**Valor:** el radar, la lista y el detalle dejan de emitir formas parciales; F0.2 pasa a verde.

**Archivo:** `Stacky Agents/backend/services/dbcompare_runs.py`

**Función nueva** (colocarla junto a `_is_stale`, después de `dbcompare_runs.py:131`):

```python
_CANON_BY_SEVERITY = ("info", "warn", "danger")
_CANON_BY_ACTION = ("added", "removed", "changed")
_CANON_BY_OBJECT_TYPE = ("table", "view", "sequence")


def _count(value) -> int:
    """Entero >= 0. Cualquier cosa que no sea un número usable cuenta como 0."""
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return 0
    return n if n > 0 else 0


def _normalize_summary(summary):
    """Plan 266 — forma canónica del summary, SOLO EN MEMORIA.

    `None` se preserva como `None`: una corrida `running` no tiene resumen y
    fabricar ceros haría que la UI muestre '0 danger' para algo que todavía no
    comparó nada (mentira, no defensa).
    """
    if not isinstance(summary, dict):
        return None if summary is None else summary
    out = dict(summary)
    for key, canon in (
        ("by_severity", _CANON_BY_SEVERITY),
        ("by_action", _CANON_BY_ACTION),
        ("by_object_type", _CANON_BY_OBJECT_TYPE),
    ):
        src = out.get(key)
        src = src if isinstance(src, dict) else {}
        out[key] = {k: _count(src.get(k)) for k in canon}
    return out
```

**Cableado (2 puntos, ambos gateados por la flag):**

1. `get_run` (`dbcompare_runs.py:316-323`) — antes del `return run`:

```python
def get_run(run_id: str) -> dict | None:
    run = _read_run(run_id)
    if run is None:
        return None
    if _is_stale(run):
        run = dict(run)
        run["stale"] = True
    if getattr(_config.config, "STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED", True):
        run = dict(run)
        run["summary"] = _normalize_summary(run.get("summary"))
    return run
```

2. `list_runs` (`dbcompare_runs.py:326-340`) — después de armar `meta` en `:336`:

```python
        meta["stale"] = _is_stale(run)
        if getattr(_config.config, "STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED", True):
            meta["summary"] = _normalize_summary(meta.get("summary"))
        runs.append(meta)
```

**Import de config:** usar el patrón de la casa `import config as _config` + lectura por
`getattr(_config.config, …)` — **la instancia `_config.config`, nunca el módulo** (gotcha
conocido: `getattr` del módulo devuelve el default y mata la rama OFF). Si
`dbcompare_runs.py` todavía no importa config, agregar `import config as _config` con los
imports del tope del archivo.

**Efecto colateral BUENO y verificado:** `backend/api/db_compare_watch.py:145` alimenta las
celdas del radar desde `dbcompare_runs.list_runs(200)`, y en `:153` hace
`(meta["summary"] or {}).get("by_severity") or {}`. Con la normalización en `list_runs`, ese
`or {}` deja de dispararse y la celda ya nunca lleva `by_severity: {}`.
**`api/db_compare_watch.py` NO se modifica** en este plan.

**Flag nueva — CINCO lugares de cableado obligatorios (1 a 5) + un sexto lugar donde
explícitamente NO se cablea (6):**

| # | Archivo | Qué agregar |
|---|---|---|
| 1 | `Stacky Agents/backend/config.py`, junto al bloque DB Compare (después de `:203`) | ver bloque de abajo |
| 2 | `Stacky Agents/backend/services/harness_flags.py`, en `FLAG_REGISTRY` (junto al `FlagSpec` de `STACKY_DB_COMPARE_MASKING_ENABLED`, `harness_flags.py:4196-4204`) | `FlagSpec` con `default=True` y `requires="STACKY_DB_COMPARE_ENABLED"` |
| 3 | `Stacky Agents/backend/services/harness_flags.py`, en `_CATEGORY_KEYS["capacidades_optin"]` (junto a `harness_flags.py:447`) | la key |
| 4 | `Stacky Agents/backend/tests/test_harness_flags.py`, en `_CURATED_DEFAULTS_ON` (`test_harness_flags.py:467`) | la key |
| 5 | `Stacky Agents/backend/services/harness_flags_help.py`, en `PLAIN_HELP` (`harness_flags_help.py:25`) | entrada `PlainHelp(what=…, on_effect=…, off_effect=…, example=…)` |
| 6 | — | **NO** se agrega campo a `GET /api/db-compare/health` (`backend/api/db_compare.py:71-91`): esta flag no gatea nada del frontend. Agregarlo sería ruido. |

`config.py`:

```python
    # ── Plan 266 — Forma garantizada del summary de las corridas ─────────────
    # Default ON: normalización SOLO-LECTURA y en memoria del summary que sale por
    # list_runs/get_run. No escribe disco, no toca ningún sistema del operador, no
    # llama a ningún modelo: no cae en (A) quema de tokens en reposo ni en (B)
    # escritura en sistema real ⇒ ON. Curada en _CURATED_DEFAULTS_ON.
    # OFF = payload byte-idéntico a antes del plan 266 (kill-switch auditable).
    STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED: bool = os.getenv(
        "STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED", "true"
    ).strip().lower() == "true"
```

`PLAIN_HELP` (respetar los topes de `harness_flags_help.py:18-22`: `what`/`on_effect`/
`off_effect` ≤ 240 caracteres, `example` ≤ 300):

```python
    "STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED": PlainHelp(
        what="Controla si el Comparador de BD completa los contadores faltantes del resumen de una comparación antes de mandárselos a la pantalla.",
        on_effect="Si la activás: una comparación vieja o interrumpida se ve con contadores en cero en vez de romper la pestaña.",
        off_effect="Si la apagás: el resumen viaja tal cual está guardado y una comparación incompleta puede romper la pestaña del Comparador.",
        example="Abrís una comparación hecha con una versión anterior de Stacky: con esto activado ves 0 danger / 0 warn / 0 info; apagado, la pestaña muestra el cartel rojo de error.",
    ),
```

**Tests:** los de F0.2 pasan a verde. Agregar en el mismo archivo:

| Test | Aserción |
|---|---|
| `test_flag_off_deja_el_payload_crudo` | con `monkeypatch.setattr(config.config, "STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED", False)`, `list_runs()[0]["summary"] == {"parity_score": 91.7}` (sin claves agregadas) |
| `test_flag_registrada_default_on` | `harness_flags._REGISTRY_INDEX["STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED"].default is True` y `harness_flags.categorize("STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED") == "capacidades_optin"` |

**Comandos:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan266_summary_shape.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q
```
El segundo verifica los pares `_CURATED_DEFAULTS_ON` ↔ `default=True` y la categorización
(`test_harness_flags.py:965-983`).

**Criterio de aceptación (binario):** ambos comandos en `0 failed`.
**Nota de entorno:** `tests/test_harness_flags_help.py` tiene **4 fallos ajenos preexistentes**;
NO se corren como gate de este plan. Para validar solo la entrada nueva:
`.venv\Scripts\python.exe -m pytest tests/test_harness_flags_help.py -q -k SUMMARY_SHAPE`

**Flag:** `STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED` — **default ON**.
**Impacto por runtime:** neutro/idéntico en los 3.
**Trabajo del operador:** ninguno (opt-out disponible en la UI de flags, default ON).

---

### F4 — Centinela: el patrón no vuelve por la puerta de atrás

**Objetivo (1 frase):** un ratchet que falla si alguien vuelve a leer `by_severity` /
`by_action` / `by_object_type` sin pasar por `summaryShape.ts`.
**Valor:** F2 arregla los 8 casos de hoy; F4 arregla el caso 9 que todavía no existe.

**Archivo nuevo:** `Stacky Agents/frontend/src/__tests__/dbcompareSummaryShapeRatchet.test.ts`
(mismo directorio y patrón que los 8 ratchets de frontend ya existentes; el más cercano es
`devopsPollingRatchet.test.ts`, del que se copia la estructura de censo + controles negativos).

#### F4.1 — Alcance EXACTO

- Raíz: `frontend/src/components/dbcompare/`, **recursivo**.
- Extensiones: `.ts` y `.tsx`.
- Excluidos: cualquier ruta que matchee `/\.test\.tsx?$/` o que contenga un segmento
  `__tests__`.
- `ALLOWLIST: string[] = []` — **vacía a propósito y verificado**: el único archivo que
  legítimamente toca esas claves es `summaryShape.ts`, y está escrito con corchetes y literal
  de string (`src["by_severity"]`), forma que **no** matchea ninguna de las dos reglas.

#### F4.2 — Las DOS reglas (una sola no alcanza)

```ts
// R1 — acceso profundo: el mapa leído como objeto, con punto o con corchete.
const R1 = /by_(severity|action|object_type)\s*[.[]/;

// R2 — lectura directa del contenedor: el mapa sacado de `.summary` (con o sin `!`).
const R2 = /\.summary\s*!?\s*\.by_(severity|action|object_type)/;

// EXENCIÓN (misma línea): la lectura pasa por el normalizador.
const EXENTO = ["safeSummary(", "safeBySeverity(", "safeByAction(", "safeByObjectType("];
```

R1 sola **no alcanza**: `radarLogic.ts:60` es `const sev = r.summary!.by_severity;` — después
del identificador viene `;`, no `.` ni `[`, así que R1 no lo ve. Y ese es justamente el
crash reportado. R2 lo caza.
R2 sola **tampoco**: `EnvironmentRadar.tsx:215` es `cell.by_severity.danger` — no hay
`.summary` en la línea. R1 lo caza.

Una línea es violación si matchea R1 **o** R2 **y** no contiene ninguna cadena de `EXENTO`.

#### F4.3 — Tests del archivo

| # | Test | Aserción |
|---|------|----------|
| 1 | `no hay accesos profundos sin guarda en dbcompare/` | `censo()` devuelve `[]` |
| 2 | `el detector encuentra las 8 formas históricas` | contra el fixture de F4.4, `violaciones(FIXTURE_HISTORICO)` tiene **8** entradas |
| 3 | `R2 caza el non-null assertion` | `violaciones('const sev = r.summary!.by_severity;')` → 1 |
| 4 | `R1 caza el acceso con punto` | `violaciones('{cell.by_severity.danger}')` → 1 |
| 5 | `R1 caza el acceso computado` | `violaciones('summary.by_object_type[t]')` → 1 |
| 6 | `la forma normalizada NO es violación` | `violaciones('const sev = safeSummary(run.summary).by_severity;')` → 0 |
| 7 | `la declaración de tipo NO es violación` | `violaciones('  by_severity: Record<Severity, number>;')` → 0 |
| 8 | `el literal de objeto NO es violación` | `violaciones('by_severity: { info: 0, warn: 0, danger: 0 },')` → 0 |
| 9 | `la lectura por corchete con literal de string NO es violación` | `violaciones('const src = raw["by_severity"];')` → 0 |
| 10 | `el guard con \|\| NO es violación` | `violaciones('const sev = cell.by_severity \|\| EMPTY_BY_SEVERITY;')` → 0 |
| 11 | `la ALLOWLIST está vacía` | `expect(ALLOWLIST).toEqual([])` |
| 12 | `el censo mira al menos 12 archivos` | `archivos().length >= 12` — control anti-censo-vacío: si un refactor mueve la carpeta, el test 1 pasaría trivialmente |

El test 2 usa este fixture, **copia textual de las 8 líneas de la §2.3 antes de F2**, embebido
como string en el archivo de test (no como archivo aparte):

```ts
const FIXTURE_HISTORICO = [
  'const sev = r.summary!.by_severity;',                                       // radarLogic.ts:60
  '{run.summary.by_severity.danger}',                                          // RunsTimeline.tsx:37
  '{run.summary.by_severity.warn} {run.summary.by_severity.info}',             // RunsTimeline.tsx:38
  'const sev = r.diff.summary.by_severity;',                                   // EnvironmentRadar.tsx:144
  '{(cell.by_severity.danger || 0) + (cell.by_severity.warn || 0)}',           // EnvironmentRadar.tsx:215
  '.map((t) => `${summary.by_object_type[t]} ${OBJECT_TYPE_LABEL[t]}`)',       // SummaryHero.tsx:145
  'return SEVERITY_ORDER.map((s) => ({ s, count: diff.summary.by_severity[s] }));', // svgMath.ts:43
  'return ACTION_ORDER.map((a) => ({ a, count: diff.summary.by_action[a] }));',     // svgMath.ts:47
].join('\n');
```

Esto reemplaza al "ROJO primero" que este archivo no puede tener (F2 ya limpió el censo cuando
llega F4): el detector se prueba contra el bug real, no contra un caso inventado.

#### F4.4 — Por qué NO puede tener falsos positivos masivos (justificación exigida)

1. **R1 exige el identificador pegado a `.` o `[`.** Eso es, por construcción, la forma de
   *desreferenciar el mapa*. Las formas benignas no matchean, y están verificadas en el árbol
   actual:
   - declaración de tipo: `dbcompareTypes.ts:106-108` (`by_severity: Record<Severity, number>;`)
     y `radarTypes.ts:16` / `:31` → después del identificador viene `:` ⇒ **no matchea**.
   - literal de objeto: `radarLogic.ts:31` (`|| { info: 0, warn: 0, danger: 0 }`) ⇒ el
     identificador está antes del `||`, seguido de espacio ⇒ **no matchea**.
   - lectura guardada: `cell.by_severity || …` ⇒ el punto está **antes**, no después ⇒ **no matchea**.
2. **R2 exige `.summary` y `.by_*` contiguos** (solo espacios o `!` en el medio). La forma
   normalizada `safeSummary(r.summary).by_severity` tiene un `)` entre medio ⇒ **no matchea**
   (y además está exenta por nombre).
3. **El alcance es una sola carpeta de producto**, no `src/**`. Nada del motor de flags, del
   runtime, ni del resto de la UI entra al censo. (Precedente: un centinela textual masivo ya
   rompió el motor de flags en esta casa. Este no puede: no lo mira.)
4. **La exención es por nombre de función, no por comentario ni por `eslint-disable`.** No se
   puede silenciar escribiendo prosa; hay que llamar al normalizador de verdad.
5. **El archivo del ratchet vive en `frontend/src/__tests__/`, fuera del alcance escaneado**, así
   que sus propias regex y su fixture no se auto-detectan. Gotcha de la casa evitado por diseño.
6. **Riesgo residual asumido y declarado:** un comentario o un string dentro de
   `frontend/src/components/dbcompare/**` que contenga literalmente `by_severity.` daría rojo.
   Es aceptable y **deseable**: el arreglo es reescribir la prosa (p. ej. "el mapa `by_severity`"),
   nunca aflojar el gate.

**Comando:** `npx vitest run src/__tests__/dbcompareSummaryShapeRatchet.test.ts`
**Criterio de aceptación (binario):** `0 failed`, 12 tests.
**Flag:** ninguna (un test no se gatea).
**Impacto por runtime:** neutro/idéntico en los 3.
**Trabajo del operador:** ninguno.

---

### F5 — `PageErrorBoundary` accionable: superficie, componente y stack copiable

**Objetivo (1 frase):** que el próximo error de render diga **dónde** pasó, no solo **qué** dijo.
**Valor:** esta incidencia costó una investigación completa porque el cartel solo traía el mensaje.

#### F5.1 — Módulo puro nuevo (lo testeable)

**Archivo nuevo:** `Stacky Agents/frontend/src/components/errorBoundaryDiagnostics.ts`

```ts
// Plan 266 F5 — Lógica pura del diagnóstico del boundary (testeable sin RTL/jsdom).

/** Primer componente del componentStack de React. `null` si no se puede extraer. */
export function firstComponentFromStack(stack: string | null | undefined): string | null;

/** Texto determinista para el portapapeles. Sin timestamps implícitos: el reloj entra por parámetro. */
export function buildDiagnosticText(input: {
  surface: string;
  message: string;
  componentName: string | null;
  stack: string | null;
  iso: string;
}): string;

/** Línea corta para el Centro de Actividad. */
export function buildActivityBody(surface: string, componentName: string | null, message: string): string;
```

Semántica:

- `firstComponentFromStack`: toma la **primera** línea que matchee
  `/^\s*(?:at|in)\s+([A-Za-z0-9_$.]+)/m` y devuelve el grupo 1. Si `stack` es
  `null`/`undefined`/`""` o ninguna línea matchea → `null`.
  Casos: `"\n    in RunsTimeline (at DbComparePage.tsx:81)"` → `"RunsTimeline"`;
  `"    at SummaryHero\n    at DbComparePage"` → `"SummaryHero"`;
  `"basura sin formato"` → `null`; `""` → `null`; `undefined` → `null`.
- `buildActivityBody`: `"<surface> · <componentName>: <message>"`; si `componentName` es
  `null` → `"<surface>: <message>"`. Nunca lanza; `message` vacío → `"error desconocido"`.
- `buildDiagnosticText`: exactamente estas 5 líneas, en este orden, unidas con `\n`:
  ```
  Stacky — error de render
  Superficie: <surface>
  Componente: <componentName ?? "desconocido">
  Mensaje: <message>
  Cuándo: <iso>
  ```
  seguidas de `"\n\nStack:\n" + stack` **solo si** `stack` es un string no vacío.
  Determinista: mismos argumentos ⇒ mismo string (por eso `iso` entra por parámetro y no
  se llama a `new Date()` adentro).

**Archivo de test nuevo:**
`Stacky Agents/frontend/src/components/__tests__/errorBoundaryDiagnostics.test.ts`
Casos: los 5 de `firstComponentFromStack`, los 3 de `buildActivityBody` (con y sin componente,
mensaje vacío), y 3 de `buildDiagnosticText` (con stack, sin stack, con `componentName: null`).
Mínimo **11 tests**.

**Comando:** `npx vitest run src/components/__tests__/errorBoundaryDiagnostics.test.ts`

#### F5.2 — Cambios en `PageErrorBoundary.tsx`

**Archivo:** `Stacky Agents/frontend/src/components/PageErrorBoundary.tsx`

- `Props` (`:12-16`): agregar `surface?: string;` — **opcional**, para no romper ninguno de los
  14 call-sites de `App.tsx`. La superficie efectiva es `this.props.surface ?? this.props.resetKey`
  (el `resetKey` ya es el tab activo, ver el comentario de `:13`).
- `State` (`:18-21`): agregar `componentName: string | null;` y `stack: string | null;`
  (inicializados en `null` en `:24` y reseteados en `:47` y `:52`).
- `componentDidCatch` (`:30-43`):
  ```ts
  const stack = info?.componentStack ?? null;
  const componentName = firstComponentFromStack(stack);
  this.setState({ componentName, stack });
  // console.error se conserva tal cual (:32)
  publishActivity({
    key: `error:${Date.now()}`,
    kind: "error",
    severity: "error",
    title: "Error en la UI",
    body: buildActivityBody(this.props.surface ?? this.props.resetKey, componentName, String(error?.message || error)),
    ts: Date.now(),
  });
  ```
  `body` sigue siendo un `string` ⇒ el contrato de `publishActivity` no cambia.
- `render()` (`:55-72`) — **el `<h2>` de `:60` NO se toca** (lo asserta
  `components/__tests__/PageErrorBoundary.test.tsx:29`), y el `<p>` del mensaje de `:61-63`
  tampoco (lo asserta `:30`). Se **agrega**, entre el `<p>` del hint (`:64-66`) y el botón
  Reintentar (`:67-69`):

  ```tsx
  <p className={styles.origin}>
    {this.props.surface ?? this.props.resetKey}
    {this.state.componentName ? ` · ${this.state.componentName}` : ""}
  </p>
  {this.state.stack && (
    <details className={styles.details}>
      <summary>Detalle técnico</summary>
      <pre className={styles.stack}>{this.state.stack}</pre>
    </details>
  )}
  ```

  y, junto al botón Reintentar:

  ```tsx
  <button type="button" className={styles.secondaryAction} onClick={this.handleCopy}>
    ⧉ Copiar diagnóstico
  </button>
  ```

  con

  ```ts
  handleCopy = (): void => {
    void navigator.clipboard?.writeText(
      buildDiagnosticText({
        surface: this.props.surface ?? this.props.resetKey,
        message: String(this.state.error?.message || this.state.error || ""),
        componentName: this.state.componentName,
        stack: this.state.stack,
        iso: new Date().toISOString(),
      }),
    );
  };
  ```

  El nombre `Copiar diagnóstico` **no colisiona** con el `getByRole("button", { name: /reintentar/i })`
  de `PageErrorBoundary.test.tsx:46`.

- **CSS:** agregar las clases `origin`, `details`, `stack` y `secondaryAction` a
  `Stacky Agents/frontend/src/components/PageErrorBoundary.module.css`.
  **CERO estilos inline** (`style={{…}}`): el `uiDebtRatchet` tiene alcance 0 en archivos
  tocados y lo rechazaría. `.stack` debe llevar `overflow: auto; max-height: 40vh;
  white-space: pre-wrap; word-break: break-word;` para que un stack largo no reviente el layout.

**Comandos:**
```
npx vitest run src/components/__tests__/errorBoundaryDiagnostics.test.ts
npx vitest run src/__tests__/uiDebtRatchet.test.ts
```

**Criterio de aceptación (binario):** ambos en `0 failed`, y
`grep -c "Esta pestaña falló al renderizar" src/components/PageErrorBoundary.tsx` = 1.

**Flag:** ninguna. Es diagnóstico **solo-lectura** de un error que ya ocurrió; la regla de la
casa dice que leer/mostrar/avisar va ON, y acá el "ON" es incondicional porque el fallback ya
existe y solo se enriquece.
**Impacto por runtime:** neutro/idéntico en los 3.
**Trabajo del operador:** ninguno (el botón está ahí cuando lo necesita; no hay nada que activar).

---

### F6 — Cierre: registro en el arnés y gates globales

**Objetivo (1 frase):** que el test backend nuevo quede bajo el arnés y que el árbol compile.
**Valor:** sin el registro, el meta-test del ratchet queda rojo y la cobertura se encoge en silencio.

1. **Registrar el test backend en el arnés** — `tests/test_plan266_summary_shape.py` va agregado
   a `HARNESS_TEST_FILES` en **`Stacky Agents/backend/scripts/run_harness_tests.sh`**
   (es el archivo que parsea el meta-test: `backend/tests/test_harness_ratchet_meta.py:13`
   → `_SCRIPT = _BACKEND / "scripts" / "run_harness_tests.sh"`, y `:21` acepta solo líneas que
   sean exactamente `tests/….py`).
   **Y también** en `Stacky Agents/backend/scripts/run_harness_tests.ps1`, que existe y debe
   quedar en sincronía. **Ojo:** los dos archivos tienen **sintaxis distinta** (Bash vs
   PowerShell); copiar la línea del `.sh` al `.ps1` tal cual rompe el `.ps1`. Mirar cómo está
   declarada la lista en cada uno y seguir su forma.
   **NO** usar `harness_ratchet_allowlist.txt`: la allowlist es deuda y solo puede bajar
   (`test_harness_ratchet_meta.py:69-76`).

2. **Gate de tipos y build:**
   ```
   npm run build     # desde Stacky Agents/frontend → tsc --noEmit && vite build
   ```

3. **Suite de verificación de la fase (correr por archivo, en este orden):**
   ```
   # backend (desde Stacky Agents/backend)
   .venv\Scripts\python.exe -m pytest tests/test_plan266_summary_shape.py -q
   .venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q
   .venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q

   # frontend (desde Stacky Agents/frontend)
   npx vitest run src/components/dbcompare/summaryShape.test.ts
   npx vitest run src/components/dbcompare/__tests__/summaryShapeCrash.test.ts
   npx vitest run src/components/dbcompare/radarLogic.test.ts
   npx vitest run src/components/dbcompare/__tests__/svgMath.test.ts
   npx vitest run src/components/__tests__/errorBoundaryDiagnostics.test.ts
   npx vitest run src/__tests__/dbcompareSummaryShapeRatchet.test.ts
   npx vitest run src/__tests__/uiDebtRatchet.test.ts
   npm run build
   ```

**Criterio de aceptación (binario):** los 11 comandos en verde. Si `uiDebtRatchet` o
`test_harness_flags` fallan por deuda **ajena** preexistente, hay que demostrarlo con un
worktree en el commit base — no argumentarlo. (`test_harness_flags_help.py` tiene 4 fallos
ajenos conocidos y NO es gate de este plan; ver F3.)

**Flag:** ninguna. **Impacto por runtime:** neutro/idéntico en los 3.
**Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Mitigación (verificable) |
|---|--------|--------------|--------------------------|
| R1 | La normalización enmascara un bug real del backend (una corrida que sí debía tener contadores muestra ceros) | media | El backend **no** deja de emitir lo que tiene: solo rellena claves faltantes. Los ceros aparecen exactamente donde antes había un crash. El control positivo `test_list_runs_no_altera_summary_completo` prueba que un summary bueno pasa intacto. |
| R2 | Convertir `summary: null` en `{}` con ceros haría que corridas `running` muestren "0 danger" | alta si se implementa mal | Explícito en §3.4 y cubierto por `test_list_runs_preserva_summary_none`. Los guards `run.summary &&` (`RunsTimeline.tsx:35`) y `if (!diff \|\| !summary) return null` (`SummaryHero.tsx:65`) se conservan textualmente. |
| R3 | El centinela da falsos positivos y bloquea trabajo ajeno | baja | Alcance de una sola carpeta, dos regex determinables, exención por nombre de función, 10 controles con fixtures. Justificación completa en §F4.4. |
| R4 | Una línea de prosa/comentario dentro de `dbcompare/` dispara el gate | baja | Documentado en §F4.4 punto 6. El arreglo es reescribir la prosa (`el mapa \`by_severity\``), NUNCA aflojar el gate. Gotcha recurrente de la casa. |
| R5 | `tsc` se queja del `?.` sobre `diff.summary` (tipado no-nullable) | baja | TypeScript **permite** `?.` sobre tipos no-nullables (no es error, a lo sumo una regla de lint). El gate es `npm run build`; si apareciera, la respuesta es agregar la regla al eslint-ignore, no sacar la defensa. |
| R6 | La flag nueva rompe `test_harness_flags` por drift de `_CURATED_DEFAULTS_ON` | alta si se olvida un lugar | Los **5 lugares** de cableado están tabulados en F3 y el gate es `test_harness_flags.py` (`:965-983` verifica el par exacto `default=True` ⇔ pertenencia al set). Una flag default-**ON** SÍ declara `default=True`; la trampa inversa (una flag OFF que declara `default=False`) no aplica acá. |
| R7 | El test backend corre contra la base VIVA del operador | baja | `test_plan266_summary_shape.py` **no importa `app`** ni llama a `create_app()`; solo `services.dbcompare_runs`, con `_runs_dir` monkeypatcheado a `tmp_path`. Verificable: el archivo no contiene la cadena `create_app`. |
| R8 | Un ratchet por AST/regex congela NOMBRES y se puede evadir renombrando | media | Asumido: si alguien crea `safeSummary2(`, el gate lo caza (no está en `EXENTO`). Si crea otro normalizador legítimo, tiene que agregarlo a `EXENTO` en el diff, que es exactamente la revisión que queremos forzar. |
| R9 | `PageErrorBoundary.test.tsx` sigue sin poder correr (falta RTL/jsdom) | certeza | Preexistente y documentado en el propio archivo (`:1-8`). Por eso toda la lógica nueva de F5 vive en `errorBoundaryDiagnostics.ts` (puro, corre hoy) y el componente solo cablea. El gate real del componente es `npm run build` + smoke visual. |

---

## 6. Fuera de scope (explícito)

1. **Reescribir o migrar en disco los JSON de corridas viejas del operador.** Sería categoría
   **(B)** de la regla de flags (escribe en datos reales del operador y es irreversible), y
   tendría que nacer **OFF** con su propia flag. **No se propone.** La normalización de este
   plan es 100% en memoria, y `test_list_runs_no_reescribe_el_archivo_en_disco` lo prueba
   byte a byte.
2. **`backend/services/dbcompare_watch.py:293`**, que escribe `by_severity` posiblemente `None`
   dentro del payload de un evento de drift. Verificado: **ningún componente del frontend lee
   ese campo** (el censo de `by_severity` en `frontend/src/` no toca `DriftEventsPanel.tsx`).
   No hay bug observable ⇒ no se toca. Si algún día se renderiza, la regla del centinela lo
   obliga a pasar por `safeBySeverity`.
3. **`backend/api/db_compare_watch.py`.** No se modifica: la normalización en `list_runs`
   (F3) ya elimina el `by_severity: {}` que emitía en `:161`, porque `:153` lee de
   `dbcompare_runs.list_runs(200)` (`:145`).
4. **Versionar el esquema de los runs en disco** (`"schema_version": N` + migrador). Es la
   solución estructural completa y es un plan aparte, más caro. Este plan cierra la incidencia
   con la normalización de borde, que es el 100% del beneficio al 10% del costo.
5. **Instalar RTL/jsdom** para poder correr los tests de componente. Gap estructural del repo,
   ajeno a esta incidencia.
6. **Cambiar el copy del boundary** (`Esta pestaña falló al renderizar`, `El resto de la
   aplicación sigue funcionando…`). Se conservan textualmente.

---

## 7. Glosario, orden de implementación y DoD

### 7.1 Glosario

| Término | Significado en este plan |
|---|---|
| **summary** | El objeto `DiffSummary` de una corrida: `by_severity`, `by_action`, `by_object_type`, `objects_total`, `objects_unchanged`, `parity_score`. Contrato en `frontend/src/components/dbcompare/dbcompareTypes.ts:105-112`; productor canónico en `backend/services/dbcompare_diff.py:321-337`. |
| **forma canónica** | Los 3 mapas presentes con **todas** sus claves y valores enteros `>= 0`. |
| **acceso profundo sin guarda** | Leer una clave de uno de los 3 mapas sin haber garantizado que el mapa existe. Las 8 instancias de hoy están en §2.3. |
| **borde de lectura** | Las funciones por las que un run sale del backend hacia cualquier consumidor: `dbcompare_runs.list_runs` y `dbcompare_runs.get_run`. |
| **centinela / ratchet** | Test que falla si un patrón prohibido reaparece. No es una foto del estado actual: caza al archivo nuevo. |
| **defensa en profundidad** | Backend y frontend normalizan por separado; ninguno confía en el otro. |
| **flag default ON** | Nace encendida. Solo nace OFF si (A) quema tokens en reposo o (B) escribe en un sistema real del operador. La única flag de este plan no cae en ninguna ⇒ **ON**. |

### 7.2 Orden de implementación (estricto)

1. **F0.1** — test frontend de reproducción. Confirmar que da **ROJO** con
   `Cannot read properties of undefined (reading 'danger')`.
2. **F0.2** — test backend de reproducción. Confirmar **ROJO** (≥6 fallos) y los 2 controles
   positivos en verde.
3. **F1** — `summaryShape.ts` + `summaryShape.test.ts`. Verde (≥28 tests).
4. **F2** — adopción en `radarLogic.ts`, `RunsTimeline.tsx`, `EnvironmentRadar.tsx`,
   `svgMath.ts`, `SummaryHero.tsx`. **F0.1 pasa a verde.**
5. **F3** — `_normalize_summary` + cableado en `list_runs`/`get_run` + flag en los 6 lugares.
   **F0.2 pasa a verde.** La flag se cablea en los 5 lugares obligatorios de la tabla de F3
   (el ítem 6 de esa tabla es un "no se toca", no un cableado).
6. **F4** — centinela `dbcompareSummaryShapeRatchet.test.ts`. Verde (12 tests).
7. **F5** — `errorBoundaryDiagnostics.ts` + tests + cableado en `PageErrorBoundary.tsx` + CSS.
8. **F6** — registro en `run_harness_tests.sh` **y** `.ps1`, `npm run build`, suite de cierre.

### 7.3 Definición de Hecho (DoD global) — binaria

- [ ] `npx vitest run src/components/dbcompare/__tests__/summaryShapeCrash.test.ts` → `0 failed`
      (y antes de F2 fallaba con `reading 'danger'`).
- [ ] `npx vitest run src/components/dbcompare/summaryShape.test.ts` → `0 failed`, ≥28 tests.
- [ ] `npx vitest run src/__tests__/dbcompareSummaryShapeRatchet.test.ts` → `0 failed`, 12 tests,
      censo = `[]` y el fixture histórico detecta **8**.
- [ ] `npx vitest run src/components/__tests__/errorBoundaryDiagnostics.test.ts` → `0 failed`, ≥11 tests.
- [ ] `npx vitest run src/components/dbcompare/radarLogic.test.ts` y
      `npx vitest run src/components/dbcompare/__tests__/svgMath.test.ts` → `0 failed`,
      **sin haber modificado esos archivos de test**.
- [ ] `npx vitest run src/__tests__/uiDebtRatchet.test.ts` → `0 failed` (o rojo ajeno probado
      con worktree en el commit base).
- [ ] `.venv\Scripts\python.exe -m pytest tests/test_plan266_summary_shape.py -q` → `0 failed`.
- [ ] `.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q` → `0 failed`.
- [ ] `.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q` → `0 failed`.
- [ ] `npm run build` (`tsc --noEmit && vite build`) → exit 0.
- [ ] `STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED` presente en los 5 lugares de F3
      (`config.py`, `FLAG_REGISTRY`, `_CATEGORY_KEYS`, `_CURATED_DEFAULTS_ON`, `PLAIN_HELP`)
      con `default=True` y `requires="STACKY_DB_COMPARE_ENABLED"`.
- [ ] `tests/test_plan266_summary_shape.py` figura en `HARNESS_TEST_FILES` de
      `backend/scripts/run_harness_tests.sh` **y** en `backend/scripts/run_harness_tests.ps1`,
      y **no** en `backend/tests/harness_ratchet_allowlist.txt`.
- [ ] `PageErrorBoundary.tsx` conserva textual `Esta pestaña falló al renderizar` y
      `El resto de la aplicación sigue funcionando`.
- [ ] **Smoke visual (HITL, lo hace el operador):** abrir el Comparador de BD con al menos una
      corrida vieja/incompleta en `data/…/runs/` y confirmar que (a) la pestaña renderiza,
      (b) el radar/timeline/hero muestran ceros donde falta el dato, (c) forzando un error de
      render el cartel muestra superficie + componente y el botón "Copiar diagnóstico" copia
      las 5 líneas + stack.
- [ ] Ningún archivo de corridas en disco fue modificado por la app durante el smoke
      (comparar `Get-FileHash` antes/después de la carpeta de runs).

---

### Nota de paridad de runtimes (Codex CLI / Claude Code CLI / GitHub Copilot Pro)

Este plan es **íntegramente frontend React + backend Flask**: no toca el selector de runtime,
ni `agent_runner`, ni prompts, ni el transporte de ninguno de los 3 CLIs. El impacto es
**neutro/idéntico en los tres**, y no requiere fallback porque no hay capacidad diferencial en
juego. Los 3 runtimes pueden **implementarlo** sin degradación: todas las fases son ediciones
de archivos con tests deterministas, sin dependencias nuevas, sin red y sin herramientas
exclusivas de un runtime.
