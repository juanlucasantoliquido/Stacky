# Plan 126 — Comparador de BD entre ambientes (serie 122–126, parte 5/5): paridad de DATOS de tablas de parámetros

**Estado:** PROPUESTO (v1, 2026-07-12)
**Serie:** 122 (núcleo) → 123 (motor de diff) → 124 (UI inmersiva) → 125 (scripts + backups) → **126 (paridad de datos)**
**Dependencias:** Planes 122, 123 y 125 IMPLEMENTADOS (snapshots con PK por tabla, runs, bundle con manifest v1). Plan 124 recomendable (la UI de este plan vive en el drill-down y en la tab Scripts).
**Ortogonal a:** Planes 116/119/120/121.

> Este documento está redactado para que un MODELO MENOR (Haiku, Codex CLI o GitHub
> Copilot Pro) lo implemente SIN inferir nada. Los templates SQL y las reglas de
> normalización son LITERALES y se verifican con tests golden. Prohibido desviarse de
> los nombres exactos.

---

## 1. Objetivo + KPI

El esquema puede ser idéntico y los ambientes seguir comportándose distinto: en el
producto RS la conducta vive en **tablas de parámetros** (catálogos chicos tipo RTABL /
RIDIOMA / catálogos de procesos). El operador lo dijo explícito: *"tablas que se van a
pisar o modificar"* — eso es DATOS, no solo DDL. Este plan cierra la serie agregando:

1. **Diff de datos por PK** para tablas elegidas por el operador (con caps duros de filas),
   ejecutado threaded dentro del run existente, con SELECTs generados internamente que
   ADEMÁS pasan por `validate_select_only` (`services/db_query.py:97`) antes de ejecutarse
   (cinturón y tiradores: nada que no sea SELECT puede llegar al motor).
2. **Scripts DML de paridad** (INSERT faltantes, UPDATE difieren, DELETE sobrantes —
   estos últimos en `09_destructivo/`) integrados al bundle del 125 bajo `03_datos/`,
   **con backup de datos pareado por CADA tabla que reciba DML** (misma regla de oro).
3. **Grid visual de diferencias de datos** en el drill-down (celdas resaltadas).
4. Dos flags nuevas UI default OFF que gatean todo esto.

**KPIs (binarios):**

- **KPI-1 (correctitud):** con dos sqlite sembradas con la misma tabla (`PARAMS`) y filas
  divergentes conocidas, `diff_table_data` devuelve EXACTAMENTE 1 only_source, 1
  only_target y 1 changed con la celda correcta — test F2.
- **KPI-2 (seguridad):** todo SQL que `dbcompare_data` manda al motor pasó por
  `validate_select_only` (assert interno + test que monkeypatchea el validador y cuenta).
- **KPI-3 (regla de oro):** toda tabla presente en `03_datos/` tiene su backup en
  `01_backups/` (extensión del invariante del manifest 125; test F3).

## 2. Por qué ahora / gap que cierra

- Con 122–125 el operador iguala ESTRUCTURA; el drift de comportamiento del producto RS
  vive en los DATOS de parámetros (doctrina conocida del ecosistema: catálogo de procesos,
  `RTABL`, `RIDIOMA`). Sin esto, "paridad de ambientes" queda a mitad de camino.
- El pedido original menciona explícitamente el pisado de tablas: pisar = DML. El backup
  pareado de datos es la mitad de la promesa de la serie.

## 3. Principios y guardarraíles

1. **Opt-in doble:** flag hija `STACKY_DB_COMPARE_DATA_DIFF_ENABLED` default OFF además
   del master. Sin ella, NADA de datos se lee (ni endpoints ni UI).
2. **Caps duros:** `STACKY_DB_COMPARE_DATA_MAX_ROWS` (default 5000) por tabla y lado;
   tabla que excede → resultado `truncated: true` y aviso UI; máx 20 tablas por corrida
   (constante `_MAX_TABLES_PER_DATA_DIFF = 20`).
3. **Solo tablas con PK:** sin PK en el snapshot → no comparable (la UI lo explica);
   jamás heurísticas de matching sin clave.
4. **Read-only real:** solo SELECTs generados por Stacky + validados con
   `validate_select_only`; los scripts DML son ARTEFACTOS (nunca se ejecutan desde Stacky).
5. **Gotcha flags (obligatorio):** las `requires` de AMBAS flags nuevas apuntan al MASTER
   `STACKY_DB_COMPARE_ENABLED` (profundidad 1; NO encadenar a la flag hija — aprendizaje
   Plan 104 R4). Sin `default=False` explícito en la bool (gotcha Plan 63).
6. **Runtimes:** feature de panel; N/A por runtime. **Operador:** opt-in (default off).

## 4. Fases

### F0 — Flags + config

**Archivos a editar:** `Stacky Agents/backend/services/harness_flags.py`, `Stacky Agents/backend/config.py`.

**FlagSpecs exactas (grupo `global`; categoría `comparador_bd` en el mapa categoría→keys):**
```python
FlagSpec(
    key="STACKY_DB_COMPARE_DATA_DIFF_ENABLED",
    type="bool",
    label="Comparador BD: paridad de datos",
    description="Permite comparar DATOS de tablas de parámetros por PK y generar scripts DML + backups. OFF = solo esquema.",
    group="global",
    requires="STACKY_DB_COMPARE_ENABLED",
),
FlagSpec(
    key="STACKY_DB_COMPARE_DATA_MAX_ROWS",
    type="int",
    label="Comparador BD: máx. filas por tabla (datos)",
    description="Cap duro de filas leídas por tabla y por lado en el diff de datos; excedente = resultado truncado.",
    group="global",
    default=5000,
    requires="STACKY_DB_COMPARE_ENABLED",
    min_value=100,
    max_value=200000,
),
```
**Config (idiomas de `config.py:964` bool y `config.py:591` int):**
`STACKY_DB_COMPARE_DATA_DIFF_ENABLED` default `"false"`, `STACKY_DB_COMPARE_DATA_MAX_ROWS` default `"5000"`.

**Tests PRIMERO:** `tests/test_plan126_dbcompare_data_flags.py` — declaración, defaults,
bounds, `requires` == master EXACTO (ambas), categoría.

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan126_dbcompare_data_flags.py tests/test_harness_flags.py -q`

**Criterio binario:** verdes sin regresión de la suite de flags.

### F1 — Literales SQL y normalización: `services/dbcompare_sqlvalues.py`

**Objetivo:** una única fuente de verdad para (a) normalizar valores leídos para comparar y (b) renderizar literales SQL por dialecto para los scripts DML.

**Archivo a crear:** `Stacky Agents/backend/services/dbcompare_sqlvalues.py`

**Símbolos y reglas EXACTAS:**
```python
def normalize_value(v) -> str | None
# None → None
# bool → "1"/"0"
# int → str(v)
# float/Decimal → repr canónico: format(v, "f") con strip de ceros a la derecha y de "." final ("1.500"→"1.5", "2.0"→"2")
# datetime/date/time → isoformat() con " " en lugar de "T" para datetime
# bytes → "0x" + hex().upper() de los primeros 16 bytes + f"...({len} bytes)" si len>16
# str → tal cual (SIN trim: los espacios son diferencia real)
# otro → str(v)

def sql_literal(v, dialect: str) -> str
# None → "NULL"
# bool → "1"/"0"
# int/float/Decimal → str/format canónico (sin comillas)
# str → "'" + v.replace("'", "''") + "'"   (para oracle además: si contiene chr(0) → error explícito)
# datetime: sqlserver → "CONVERT(DATETIME2, '<YYYY-MM-DDTHH:MM:SS.ffffff>', 126)"
#           oracle    → "TO_TIMESTAMP('<YYYY-MM-DD HH:MM:SS.ffffff>', 'YYYY-MM-DD HH24:MI:SS.FF6')"
#           sqlite    → "'<YYYY-MM-DD HH:MM:SS>'"
# date:     sqlserver → "CONVERT(DATE, '<YYYY-MM-DD>', 23)" | oracle → "TO_DATE('<YYYY-MM-DD>','YYYY-MM-DD')" | sqlite → "'<YYYY-MM-DD>'"
# bytes:    sqlserver → "0x<HEX>" | oracle → "HEXTORAW('<HEX>')" | sqlite → "X'<HEX>'"
```

**Tests PRIMERO:** `tests/test_plan126_dbcompare_sqlvalues.py` — golden por regla (≥12 casos,
incluye `2.0→"2"`, `1.500→"1.5"`, comilla simple doblada, datetime por dialecto, bytes largos).

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan126_dbcompare_sqlvalues.py -q`

**Criterio binario:** golden verdes.

### F2 — Diff de datos por PK: `services/dbcompare_data.py`

**Objetivo:** comparar filas de una tabla entre dos ambientes, con caps, orden por PK y validación SELECT-only.

**Archivo a crear:** `Stacky Agents/backend/services/dbcompare_data.py`

**Símbolos exactos:**
```python
_MAX_TABLES_PER_DATA_DIFF = 20

class DbCompareDataError(RuntimeError): ...

def build_select(schema: str, table: str, columns: list[str], pk_cols: list[str], dialect: str, max_rows: int) -> str
# columnas e identificadores SIEMPRE via dbcompare_sqlnames.qualified/quote_ident (Plan 125 F1)
# sqlserver → "SELECT TOP (<max_rows+1>) <cols> FROM <q> ORDER BY <pk_cols>"
# oracle    → "SELECT <cols> FROM (SELECT <cols> FROM <q> ORDER BY <pk_cols>) WHERE ROWNUM <= <max_rows+1>"
# sqlite    → "SELECT <cols> FROM <q> ORDER BY <pk_cols> LIMIT <max_rows+1>"
# el +1 detecta truncamiento sin contar toda la tabla.

def fetch_rows(engine, sql: str) -> list[tuple]
# assert validate_select_only(sql).ok  ← KPI-2; si no ok → DbCompareDataError (nunca ejecuta)
# ejecuta con sqlalchemy.text(sql) y devuelve filas crudas.

def diff_table_data(source_alias: str, target_alias: str, schema: str, table: str,
                    *, engines: tuple | None = None, max_rows: int | None = None) -> dict
# engines inyectable para tests (par de Engine sqlite); max_rows default = Config.STACKY_DB_COMPARE_DATA_MAX_ROWS
# 1) pk_cols y columns desde el ÚLTIMO snapshot del ORIGEN (dbcompare_snapshot.latest_snapshot);
#    sin PK → DbCompareDataError("la tabla <t> no tiene PK; no comparable")
#    (columnas = intersección origen∩destino por nombre; las no comunes se listan en "columns_skipped")
# 2) leer ambos lados (fetch_rows) → dicts {pk_tuple: {col: normalize_value(v)}}
# 3) DataDiff v1:
#    {"version":1, "schema":..., "table":..., "pk_cols":[...], "columns":[...], "columns_skipped":[...],
#     "only_source":[{pk_cols+cols normalizados}...], "only_target":[...],
#     "changed":[{"pk":{...}, "cells":{col:{"source":..,"target":..}} }...],
#     "row_counts":{"source":n,"target":n}, "truncated": bool, "identical": bool}
#    listas ordenadas por pk_tuple; changed solo con celdas realmente distintas.

def run_data_diff(run_id: str, tables: list[dict]) -> None
# tables = [{"schema":..,"table":..}]; len>20 → DbCompareDataError
# threaded (daemon), igual doctrina 123 §F2: lock por run_id (set _ACTIVE_DATA_RUNS),
# escribe en el archivo del run: run["data_diff"] = {"status":"running|done|error",
#   "phase": "tabla i/N: <schema.table>", "tables": {"<schema.table>": DataDiff|{"error":..}},
#   "started_at","finished_at","error"} (escritura atómica tmp+os.replace).
```

**Tests PRIMERO:** `tests/test_plan126_dbcompare_data_diff.py`
- Fixture: dos sqlite tmp con `CREATE TABLE PARAMS (ID INTEGER PRIMARY KEY, NOMBRE TEXT, VALOR REAL)`;
  origen filas (1,'A',1.5),(2,'B',2.0),(3,'C',3.0); destino (1,'A',1.5),(2,'B-mod',2.0),(4,'D',4.0).
- `test_kpi1_exacto` — only_source={3}, only_target={4}, changed={2: NOMBRE 'B'→'B-mod'}.
- `test_truncated_con_cap` — max_rows=2 → truncated true.
- `test_sin_pk_error_claro`.
- `test_kpi2_validador_siempre` — monkeypatch contador sobre `validate_select_only`; tras un diff, llamadas == SELECTs ejecutados.
- `test_run_data_diff_thread_y_lock` — cached run + sqlite; polling hasta done; segundo lanzamiento simultáneo → error busy.
- `test_build_select_golden_por_dialecto` (3 strings literales).

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan126_dbcompare_data_diff.py -q`

**Criterio binario:** todos verdes (KPI-1 y KPI-2 demostrados).

### F3 — Scripts DML + backup pareado: extensión del bundle 125

**Objetivo:** materializar la paridad de datos como scripts, integrada al bundle y a su invariante.

**Archivo a editar:** `Stacky Agents/backend/services/dbcompare_scripts.py` (Plan 125).

**Símbolos exactos (agregar):**
```python
def emit_data_scripts(data_diff: dict, dialect: str, ts: str, target_alias: str) -> list[ScriptPiece]
# por tabla con only_source/changed/only_target no vacíos:
#   1 ScriptPiece INSERT  (action="data_insert",  destructive=False, modifies_table=True):
#     por fila de only_source: "INSERT INTO <q> (<cols>) VALUES (<sql_literal(...)>);" (una línea por fila, orden PK)
#   1 ScriptPiece UPDATE  (action="data_update",  destructive=True,  modifies_table=True):
#     por fila changed: "UPDATE <q> SET <col> = <lit>[, ...] WHERE <pk_col> = <lit>[ AND ...];"
#   1 ScriptPiece DELETE  (action="data_delete",  destructive=True,  modifies_table=True):
#     por fila only_target: "DELETE FROM <q> WHERE <pk> = <lit>;"  → va a 09_destructivo/
# encabezado de cada archivo: mismo del 125 §F2 + "-- Fuente de valores: snapshot de datos <ts> — verificá vigencia antes de ejecutar."
# NOTA: los literales salen de los valores NORMALIZADOS del DataDiff v1 (contrato asumido:
# la normalización de F1 es reversible a literal para los tipos soportados; bytes truncados
# (">16 bytes") → fila completa comentada con "-- BYTES TRUNCADOS: completar a mano").
```
- `generate_parity_bundle(run_id)` (125 §F3) se extiende: si `run["data_diff"]["status"]=="done"`,
  agrega `03_datos/` con numeración 301+ para insert/update y 9xx para delete, y **por cada
  tabla con CUALQUIER pieza DML agrega su backup de datos** (mismo emitter y dedupe del 125
  §F2) en `01_backups/`. El invariante del manifest (KPI-1 del 125) cubre ahora también
  las entries `data_*` (KPI-3 de este plan) — es el MISMO assert, sin rama nueva.
- README del bundle suma sección `Datos` con contadores por tabla.

**Tests PRIMERO:** `tests/test_plan126_dbcompare_data_scripts.py`
- `test_insert_update_delete_golden_sqlserver` / `..._oracle` (strings literales, filas ordenadas por PK),
- `test_delete_va_a_destructivo`,
- `test_kpi3_backup_por_tabla_con_dml` (manifest: entries data_* → tabla tiene backup en 01_backups/),
- `test_bytes_truncados_comenta_fila`,
- `test_bundle_sin_data_diff_no_crea_03_datos` (backward-compat con 125).

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan126_dbcompare_data_scripts.py -q`

**Criterio binario:** golden + invariante verdes.

### F4 — API + gate doble

**Archivo a editar:** `Stacky Agents/backend/api/db_compare.py`.

**Gate adicional:** helper `_require_data_enabled()` — 403 si
`not Config.STACKY_DB_COMPARE_DATA_DIFF_ENABLED` (además del `_require_enabled()` master).

**Endpoints exactos:**
| Método y ruta | Comportamiento |
|---|---|
| `GET /runs/<run_id>/data-candidates` | tablas comparables del run: desde el diff+snapshot origen, lista `{schema, table, has_pk, estimated_columns, comparable: bool, reason}`; ordenada, `comparable=false` si sin PK |
| `POST /runs/<run_id>/data-diff` | body `{tables: [{schema, table}]}` → `run_data_diff`; 202 `{ok}`; >20 tablas o run no done → 400/409; busy → 409 |
| `GET /runs/<run_id>` (existente) | ya devuelve `run["data_diff"]` cuando existe (sin cambios de código: el run file lo contiene) |
| `POST /runs/<run_id>/scripts` (existente 125) | ahora incluye `03_datos/` si data_diff done (sin firma nueva) |

**Tests PRIMERO:** `tests/test_plan126_dbcompare_data_api.py`
- `test_flag_hija_off_403_aunque_master_on`, `test_candidates_lista_y_reason_sin_pk`,
- `test_data_diff_202_polling_done_sqlite`, `test_mas_de_20_tablas_400`, `test_busy_409`.

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan126_dbcompare_data_api.py -q`

**Criterio binario:** todos verdes.

### F5 — UI: selector de tablas + grid de diferencias de datos

**Archivos a crear en `Stacky Agents/frontend/src/components/dbcompare/`:**
- `dataDiffLogic.ts` (puro):
```ts
export interface DataGridRow { pk: string; kind: "only_source"|"only_target"|"changed";
                               cells: {col: string; source: string | null; target: string | null; changed: boolean}[] }
export function buildDataGridRows(d: DataDiff): DataGridRow[]     // orden: changed, only_source, only_target; pk como "col=val · col=val"
export function dataCounters(d: DataDiff): {inserts: number; updates: number; deletes: number}
export function candidateFilter(cands: DataCandidate[], text: string): DataCandidate[]
```
- `DataTablePicker.tsx` — modal desde botón `Comparar datos…` (visible en el hero cuando
  el run está done Y la flag hija está ON — la UI la lee del `/health` del 122, que en F4
  suma `data_diff_enabled: bool` al payload): lista de `data-candidates` con checkbox
  (deshabilitado si `comparable=false`, con `reason`), búsqueda, contador `N/20
  seleccionadas`, botón `Comparar datos` → POST + polling del run (reusa `useCompareRun`).
- `DataDiffGrid.tsx` — en el drill-down del objeto (Plan 124 F5) tab nueva `Datos` si el
  run tiene data_diff de esa tabla: contadores chips (`+N faltantes · ~N difieren · −N
  sobrantes`), banner ámbar si `truncated`, y tabla sticky-header de `DataGridRow`: fila
  changed muestra source/target apilados en la celda con `changed=true` resaltada
  (`--dbc-changed`); only_source fondo `--dbc-added`; only_target `--dbc-removed`
  (tokens del 124 §3.3). Paginado cliente de a 100 (patrón DiffList 124 F5).
- `endpoints.ts`: `DbCompare.dataCandidates(runId)`, `startDataDiff(runId, tables)`.

**Tests PRIMERO:** `frontend/src/components/dbcompare/__tests__/dataDiffLogic.test.ts`
- `buildDataGridRows` (fixture KPI-1: orden, kinds, celda changed exacta),
- `dataCounters`, `candidateFilter` (case-insensitive).

**Comando:** `cd "Stacky Agents/frontend" && npx vitest run src/components/dbcompare/__tests__/dataDiffLogic.test.ts` y `npx tsc --noEmit`

**Criterio binario:** vitest verde + tsc 0.

### F6 — No-regresión y cierre de la SERIE

**Comandos:**
```
cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan126_dbcompare_data_flags.py tests/test_plan126_dbcompare_sqlvalues.py tests/test_plan126_dbcompare_data_diff.py tests/test_plan126_dbcompare_data_scripts.py tests/test_plan126_dbcompare_data_api.py -q
cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan122_dbcompare_flags.py tests/test_plan122_dbcompare_registry.py tests/test_plan122_dbcompare_engine.py tests/test_plan122_dbcompare_snapshot.py tests/test_plan122_dbcompare_api.py tests/test_plan123_dbcompare_diff.py tests/test_plan123_dbcompare_runs.py tests/test_plan123_dbcompare_api.py tests/test_plan123_dbcompare_export.py tests/test_plan125_dbcompare_sqlnames.py tests/test_plan125_dbcompare_emitters_sqlserver.py tests/test_plan125_dbcompare_emitters_oracle.py tests/test_plan125_dbcompare_bundle.py tests/test_plan125_dbcompare_toposort.py tests/test_plan125_dbcompare_scripts_api.py tests/test_harness_flags.py tests/test_smoke.py -q
cd "Stacky Agents/frontend" && npx vitest run src/components/dbcompare/ && npx tsc --noEmit
```
**Criterio binario:** TODA la serie verde en un solo pase; smoke y flags sin fallos nuevos; tsc 0.

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Tabla "de parámetros" resulta enorme | Cap `+1` detecta truncamiento sin full scan; truncated visible en UI y en README del bundle; flag de máx. filas ajustable por UI. |
| Literales DML incorrectos para tipos exóticos | Tabla cerrada de `sql_literal` con golden tests; tipos no mapeados → fila comentada con motivo (nunca SQL silenciosamente inválido). |
| Precisión float/decimal en normalización | Regla canónica única (F1) aplicada a AMBOS lados: los falsos positivos por representación se anulan entre sí. |
| Operador ejecuta DELETE sin mirar | DELETEs solo en `09_destructivo/` + backup por tabla + banner HITL del 125. |
| Diff de datos en paralelo con otro del mismo run | Lock `_ACTIVE_DATA_RUNS` + 409 (doctrina 1-thread-por-orden). |
| PII en snapshots de datos dentro de runs/bundles | Los DataDiff viven en `data_dir()` local (mono-operador, sin egreso); el Plan 121 (centinela de egreso) cubre cualquier envío posterior a LLMs. Nota explícita en README del bundle. |

## 6. Fuera de scope

- MERGE statements (v2 si el uso real lo pide; INSERT/UPDATE/DELETE cubren la paridad).
- Comparación de datos SIN PK (heurísticas de matching) — rechazado por diseño.
- Sincronización automática o programada de datos; ejecución desde Stacky (prohibido).
- Enmascaramiento de PII en el grid (los datos nunca salen de la máquina; ver riesgo 6).
- Marcar tablas "de parámetros" persistentemente en el registro (v2; en v1 se eligen por corrida).

## 7. Glosario

- **Tabla de parámetros:** catálogo chico que define comportamiento del producto (RTABL, RIDIOMA, catálogos de procesos).
- **DataDiff v1:** contrato §F2 — filas only_source / only_target / changed por PK normalizada.
- **Normalización:** representación canónica de valores para comparar sin falsos positivos (F1).
- **Regla de oro:** invariante 125 extendida — DML sin backup pareado no puede persistirse.
- **Candidata:** tabla del run comparable a nivel datos (tiene PK y existe en ambos lados).

## 8. Orden de implementación

1. F0 flags + tests.
2. F1 sqlvalues + golden.
3. F2 data diff + thread + tests.
4. F3 scripts DML + bundle + invariante.
5. F4 API + gate doble.
6. F5 UI picker + grid.
7. F6 no-regresión de la serie completa.

## 9. Definición de Hecho (DoD)

- [ ] Ambas flags nuevas UI default OFF con `requires` al MASTER (gotcha 104 respetado).
- [ ] KPI-1/2/3 demostrados por tests nombrados (correctitud sqlite, validador siempre, backup pareado).
- [ ] SELECTs con cap +1, orden por PK y templates golden por dialecto; ningún SQL sin validar llega al motor.
- [ ] Bundle extiende 03_datos/ sin romper el contrato 125 (test backward-compat).
- [ ] Grid de datos con celdas resaltadas, truncated visible, picker con límite 20 y razones.
- [ ] Serie COMPLETA verde con los comandos de F6; tsc 0; smoke sin fallos nuevos.
