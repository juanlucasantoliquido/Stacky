# Plan 126 — Comparador de BD entre ambientes (serie 122–126, parte 5/5): paridad de DATOS de tablas de parámetros

**Estado:** CRITICADO (v2, 2026-07-14 — juez StackyArchitectaUltraEficientCode, veredicto APROBADO-CON-CAMBIOS; ver CHANGELOG v1.1→v2 debajo)
**Serie:** 122 (núcleo) → 123 (motor de diff) → 124 (UI inmersiva) → 125 (scripts + backups) → **126 (paridad de datos)**
**Dependencias:** Planes 122, 123 y 125 IMPLEMENTADOS (snapshots con PK por tabla, runs, bundle con manifest v1). Plan 124 recomendable (la UI de este plan vive en el drill-down y en la tab Scripts).
**Ortogonal a:** Planes 116/119/120/121.

## CHANGELOG v1.1 → v2 (crítica adversarial, 2026-07-14)

Veredicto: **APROBADO-CON-CAMBIOS** (5 BLOQUEANTES + 2 IMPORTANTES + 1 MENOR, TODOS corregidos in place abajo; 0 hallazgos sin resolver). Fixes aplicados:

- **[FIX C1 — BLOQUEANTE]** F0 no daba de alta las 2 aristas nuevas en `_REQUIRES_MAP_FROZEN` (`tests/test_harness_flags_requires.py`) ni corría ese archivo — `test_requires_map_is_frozen` habría fallado con "Extras" apenas se declararan las FlagSpec (mismo bug que plan 122 pre-fix). Corregido: paso explícito + archivo agregado al comando de F0 y F6.
- **[FIX C2 — BLOQUEANTE]** `STACKY_DB_COMPARE_DATA_MAX_ROWS` con `default=5000` explícito en un `FlagSpec` `type="int"` colisiona con el ratchet `_CURATED_DEFAULTS_ON` (`default_is_known()` es type-agnostic: `spec.default is not None`). Un escaneo AST de `harness_flags.py` confirma CERO precedentes de flags int/float con `default=` explícito — el idioma real (`STACKY_CONTEXT_BUDGET_TOKENS`) es dejar `default=None` (implícito) y poner el valor sugerido SOLO en `description` + `os.getenv(..., "5000")` de `config.py`. Corregido: se retira `default=5000` del FlagSpec.
- **[FIX C3 — BLOQUEANTE]** F2 `diff_table_data` era contradictorio: decía "columns desde el snapshot del ORIGEN" y en el mismo bullet "columnas = intersección origen∩destino" sin decir de dónde sale el snapshot del destino ni qué pasa si la tabla no existe en destino o el PK del origen no está en la intersección — ambigüedad que el propio plan promete evitar y que amenaza KPI-1 directamente (RCONTROLES/RMODULOS/RIDIOMA pueden diferir en columnas entre DEV/TEST). Corregido: algoritmo literal de 5 pasos.
- **[FIX C4 — BLOQUEANTE]** F2 nunca especificaba cómo resolver `engines=None` en producción (a diferencia de `take_snapshot` del 122, que sí documenta el fallback a `dbcompare_engine.open_engine(alias)`). Corregido: línea explícita agregada.
- **[FIX C5 — BLOQUEANTE]** F5 asumía que F4 suma `data_diff_enabled: bool` a `GET /health`, pero la tabla de endpoints de F4 nunca lo declaraba — implementado literalmente, el picker de F5 queda ciego. Corregido: quinta fila agregada a la tabla de F4 + test nombrado.
- **[FIX C6 — IMPORTANTE]** F4 conflacía ">20 tablas" y "run no done" bajo la misma etiqueta "400/409" sin decir qué código corresponde a cada causa, y "run no done" no tenía test nombrado. Corregido: códigos explícitos + test agregado.
- **[FIX C7 — IMPORTANTE]** F0 no decía cómo extender la tupla `"comparador_bd"` que crea el 122 (edición vs creación). Corregido: instrucción literal.
- **[FIX C8 — MENOR]** F3 no repetía que los nombres de columna en `<cols>` deben pasar por `dbcompare_sqlnames.quote_ident` (se infería por continuidad con 125). Corregido: línea explícita.
- **[ADICIÓN ARQUITECTO]** `GET /runs/<run_id>/data-candidates` ahora expone `row_count_source`/`row_count_target` (best-effort, `SELECT COUNT(*)` validado igual que cualquier otro SELECT del plan) para que el operador vea el TAMAÑO de cada tabla candidata ANTES de elegir cuáles diffear — ataca directo el riesgo #1 de la tabla de riesgos ("tabla de parámetros resulta enorme") sin agregar ningún paso manual (es un campo informativo más en un endpoint ya opt-in) y sin reinventar nada (reusa el mismo engine/validador de F2).

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
- Caso real ya corrido a mano (2026-07-12, `Compare-DevTestDatabase.ps1` con
  `-DataCompareTables RCONTROLES, RMODULOS, RIDIOMA` — ver doc 122 §2-bis): la comparación
  fila-por-fila por PK real de esas 3 tablas de parámetros fue exactamente lo que destrabó
  el replay DEV→TEST de RSPACIFICO. Este plan productiza ese flujo validado.
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
    description="Cap duro de filas leídas por tabla y por lado en el diff de datos; excedente = resultado truncado. Default 5000.",
    group="global",
    requires="STACKY_DB_COMPARE_ENABLED",
    min_value=100,
    max_value=200000,
),
```
**[FIX C2 — BLOQUEANTE, obligatorio]** NO pasar `default=5000` (ni ningún numérico) al `FlagSpec`
de `STACKY_DB_COMPARE_DATA_MAX_ROWS`. `default_is_known()` (`services/harness_flags.py:2752`) es
`spec.default is not None` — type-agnostic, NO solo para bools. `_CURATED_DEFAULTS_ON`
(`tests/test_harness_flags.py:465`) es, por su propio docstring, "la lista de defaults ON
curados" para `spec.default=True`; un escaneo AST de `services/harness_flags.py` confirma CERO
`FlagSpec` int/float con `default=` explícito en todo el archivo. El idioma real para sugerir un
valor es dejar `default=None` (implícito, se omite el kwarg) y poner el número SOLO en
`description` (arriba) y en el `os.getenv(..., "5000")` de `config.py` (abajo) — mismo patrón que
`STACKY_CONTEXT_BUDGET_TOKENS` (`services/harness_flags.py:379-386`, "default 25000" solo en texto).
Pasar `default=5000` rompería `test_default_known_only_for_curated` con un "Extra (no curada)".

**Config (idiomas de `config.py:964` bool y `config.py:591` int):**
`STACKY_DB_COMPARE_DATA_DIFF_ENABLED` default `"false"`, `STACKY_DB_COMPARE_DATA_MAX_ROWS` default `"5000"`.

**[FIX C1 — BLOQUEANTE, obligatorio]** En `Stacky Agents/backend/tests/test_harness_flags_requires.py`,
dentro de `_REQUIRES_MAP_FROZEN` (línea ~120-181), agregar las 2 aristas nuevas junto a las demás
(estilo `# Plan NNN`):
```python
    "STACKY_DB_COMPARE_DATA_DIFF_ENABLED": "STACKY_DB_COMPARE_ENABLED",  # Plan 126
    "STACKY_DB_COMPARE_DATA_MAX_ROWS": "STACKY_DB_COMPARE_ENABLED",  # Plan 126
```
**Por qué es obligatorio:** `test_requires_map_is_frozen` (mismo archivo) hace
`actual == _REQUIRES_MAP_FROZEN` (igualdad EXACTA sobre TODAS las `FlagSpec` con `requires`
no-nulo, de cualquier tipo). Sin esto, declarar las 2 `FlagSpec` de arriba rompe ese test
inmediatamente (mismo bug que Plan 122 pre-fix).

**[FIX C7 — IMPORTANTE]** En el mapa categoría→keys (`services/harness_flags.py:251`, el 122 crea
`"comparador_bd": ("STACKY_DB_COMPARE_CONNECT_TIMEOUT_SEC",)`): EXTENDER esa misma tupla existente
agregando las 2 keys nuevas al final — `"comparador_bd": ("STACKY_DB_COMPARE_CONNECT_TIMEOUT_SEC",
"STACKY_DB_COMPARE_DATA_DIFF_ENABLED", "STACKY_DB_COMPARE_DATA_MAX_ROWS")` — NO crear una entrada
nueva ni un dict separado.

**Tests PRIMERO:** `tests/test_plan126_dbcompare_data_flags.py` — declaración, defaults (NO
`default_is_known` para el int; ver FIX C2), bounds, `requires` == master EXACTO (ambas), categoría.

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan126_dbcompare_data_flags.py tests/test_harness_flags.py tests/test_harness_flags_requires.py -q`

**Criterio binario:** verdes sin regresión de la suite de flags (incluye `test_requires_map_is_frozen`
y `test_default_known_only_for_curated`).

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
# engines inyectable SOLO para tests (par de Engine sqlite: (source_engine, target_engine)).
# [FIX C4] Si engines es None → resolver conexiones reales con
#   dbcompare_engine.open_engine(source_alias) y dbcompare_engine.open_engine(target_alias)
#   (mismo fallback que dbcompare_snapshot.take_snapshot, Plan 122 §F3).
# max_rows default = Config.STACKY_DB_COMPARE_DATA_MAX_ROWS
# [FIX C3] Algoritmo EXACTO de resolución de columnas (reemplaza la redacción ambigua v1):
#   1) src_snap = dbcompare_snapshot.latest_snapshot(source_alias); sin snapshot →
#      DbCompareDataError("sin snapshot de <source_alias>; tomá uno primero")
#   2) tgt_snap = dbcompare_snapshot.latest_snapshot(target_alias); sin snapshot →
#      DbCompareDataError("sin snapshot de <target_alias>; tomá uno primero")
#   3) si <schema>.<table> no está en las tablas de src_snap → DbCompareDataError("la tabla
#      <t> no existe en <source_alias>"); si no está en tgt_snap → DbCompareDataError("la
#      tabla <t> no existe en <target_alias>; no comparable")
#   4) pk_cols = PK de la tabla tal cual figura en src_snap (el PK del ORIGEN es la fuente de
#      verdad); sin PK → DbCompareDataError("la tabla <t> no tiene PK; no comparable")
#   5) columns = intersección por nombre entre las columnas de src_snap y tgt_snap (orden de
#      src_snap); columns_skipped = unión menos intersección, ordenada alfabéticamente; si
#      algún pk_col NO está en columns (el PK del origen no existe en destino) →
#      DbCompareDataError("el PK de <t> (<pk_cols>) no existe completo en <target_alias>")
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
- `test_columnas_interseccion_origen_destino` **[FIX C3]** — destino con una columna extra que
  origen no tiene → esa columna en `columns_skipped`, NUNCA en el SELECT del destino.
- `test_tabla_no_existe_en_destino_error_claro` **[FIX C3]** — tabla presente en snapshot de
  origen pero ausente en snapshot de destino → `DbCompareDataError` explícito, no crashea.
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
# [FIX C8] Todo identificador (nombre de tabla, schema, columna) en los templates SIEMPRE via
# dbcompare_sqlnames.qualified/quote_ident (Plan 125 F1) — igual que build_select en F2. Los
# VALORES (los <lit>) usan sql_literal (Plan 126 F1); nunca se concatenan strings crudos.
# por tabla con only_source/changed/only_target no vacíos:
#   1 ScriptPiece INSERT  (action="data_insert",  destructive=False, modifies_table=True):
#     por fila de only_source, INSERT IDEMPOTENTE con guarda por fila (doctrina items 9/10 de
#     Invoke-DevTestParityReplay.ps1, ver doc 122 §2-bis — reejecutar el script debe ser seguro):
#     sqlserver: "IF NOT EXISTS (SELECT 1 FROM <q> WHERE <pk_col> = <lit>[ AND ...]) INSERT INTO <q> (<cols>) VALUES (<sql_literal(...)>);"
#     oracle:    "INSERT INTO <q> (<cols>) SELECT <lits> FROM dual WHERE NOT EXISTS (SELECT 1 FROM <q> WHERE <pk_col> = <lit>[ AND ...]);"
#     sqlite (tests): "INSERT INTO <q> (<cols>) SELECT <lits> WHERE NOT EXISTS (SELECT 1 FROM <q> WHERE <pk_col> = <lit>[ AND ...]);"
#     (una pieza por fila, orden PK; UPDATE por PK y DELETE por PK ya son idempotentes por naturaleza)
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
- `test_insert_update_delete_golden_sqlserver` / `..._oracle` (strings literales, filas ordenadas por PK; el golden del INSERT INCLUYE la guarda NOT EXISTS),
- `test_insert_idempotente_reejecutable_sqlite` (e2e: aplicar el script de INSERT dos veces sobre la sqlite destino → mismo row count, sin error),
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
| `GET /runs/<run_id>/data-candidates` | tablas comparables del run: desde el diff+snapshot origen, lista `{schema, table, has_pk, estimated_columns, comparable: bool, reason, row_count_source, row_count_target}` (últimos 2 campos: `int \| null`, **[ADICIÓN ARQUITECTO]** ver abajo); ordenada, `comparable=false` si sin PK |
| `POST /runs/<run_id>/data-diff` | body `{tables: [{schema, table}]}` → `run_data_diff`; 202 `{ok}`; **[FIX C6]** `len(tables) > 20` → **400**; run del schema-diff no `status=="done"` → **409** (`{"error":"run no está done"}`); ya hay un data-diff `running` para ese `run_id` (busy) → **409** (`{"error":"data-diff ya en curso"}`) |
| `GET /runs/<run_id>` (existente) | ya devuelve `run["data_diff"]` cuando existe (sin cambios de código: el run file lo contiene) |
| `POST /runs/<run_id>/scripts` (existente 125) | ahora incluye `03_datos/` si data_diff done (sin firma nueva) |
| `GET /health` (existente, Plan 122) | **[FIX C5 — BLOQUEANTE]** suma el campo `data_diff_enabled: bool` = `Config.STACKY_DB_COMPARE_DATA_DIFF_ENABLED` al payload JSON existente (sin tocar los campos ya presentes) — F5 lo necesita para mostrar/ocultar el botón `Comparar datos…`; sin este campo el picker queda ciego aunque F4 esté implementado literalmente |

**[ADICIÓN ARQUITECTO]** `row_count_source`/`row_count_target` en `data-candidates`: por cada tabla
candidata, un `SELECT COUNT(*) FROM <qualified>` best-effort por lado (mismo `engine` que F2, MISMO
`validate_select_only` — KPI-2 se extiende naturalmente), timeout/error → `null` (nunca rompe el
endpoint). Objetivo: el operador ve el TAMAÑO real de cada tabla ANTES de tildarla en el picker de
F5 — ataca directo el riesgo #1 de la tabla de riesgos ("tabla de parámetros resulta enorme") sin
agregar ningún paso manual (campo informativo en un endpoint ya opt-in) y sin reinventar nada
(reusa engine + validador de F2). Test nombrado: `test_candidates_incluye_row_counts_best_effort`
(feliz) + `test_candidates_row_count_null_si_falla` (engine lanza excepción → `null`, no 500).

**Tests PRIMERO:** `tests/test_plan126_dbcompare_data_api.py`
- `test_flag_hija_off_403_aunque_master_on`, `test_candidates_lista_y_reason_sin_pk`,
- `test_candidates_incluye_row_counts_best_effort`, `test_candidates_row_count_null_si_falla` **[ADICIÓN ARQUITECTO]**,
- `test_data_diff_202_polling_done_sqlite`, `test_mas_de_20_tablas_400` **[FIX C6]**,
- `test_run_no_done_409` **[FIX C6]**, `test_busy_409`,
- `test_health_incluye_data_diff_enabled` **[FIX C5]**.

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
cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan122_dbcompare_flags.py tests/test_plan122_dbcompare_registry.py tests/test_plan122_dbcompare_engine.py tests/test_plan122_dbcompare_snapshot.py tests/test_plan122_dbcompare_api.py tests/test_plan123_dbcompare_diff.py tests/test_plan123_dbcompare_runs.py tests/test_plan123_dbcompare_api.py tests/test_plan123_dbcompare_export.py tests/test_plan125_dbcompare_sqlnames.py tests/test_plan125_dbcompare_emitters_sqlserver.py tests/test_plan125_dbcompare_emitters_oracle.py tests/test_plan125_dbcompare_bundle.py tests/test_plan125_dbcompare_toposort.py tests/test_plan125_dbcompare_scripts_api.py tests/test_harness_flags.py tests/test_harness_flags_requires.py tests/test_smoke.py -q
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

- [ ] Ambas flags nuevas UI default OFF con `requires` al MASTER (gotcha 104 respetado) Y registradas
      en `_REQUIRES_MAP_FROZEN` (`test_requires_map_is_frozen` verde) **[FIX C1]**.
- [ ] `STACKY_DB_COMPARE_DATA_MAX_ROWS` SIN `default=` explícito en el `FlagSpec` (valor sugerido solo
      en `description`/`config.py`); `test_default_known_only_for_curated` verde sin extras **[FIX C2]**.
- [ ] KPI-1/2/3 demostrados por tests nombrados (correctitud sqlite, validador siempre, backup pareado).
- [ ] `diff_table_data` resuelve columnas por intersección origen∩destino con ambos snapshots leídos
      explícitamente y errores claros si falta snapshot/tabla/PK-común **[FIX C3]**; `engines=None`
      resuelve por `dbcompare_engine.open_engine` **[FIX C4]**.
- [ ] SELECTs con cap +1, orden por PK y templates golden por dialecto; ningún SQL sin validar llega al motor.
- [ ] `GET /health` incluye `data_diff_enabled`; picker de F5 lo consume **[FIX C5]**.
- [ ] `POST /runs/<run_id>/data-diff` distingue 400 (>20 tablas) de 409 (run no done / busy) con tests
      nombrados para cada caso **[FIX C6]**.
- [ ] Bundle extiende 03_datos/ sin romper el contrato 125 (test backward-compat).
- [ ] Grid de datos con celdas resaltadas, truncated visible, picker con límite 20 y razones.
- [ ] `data-candidates` expone `row_count_source`/`row_count_target` best-effort **[ADICIÓN ARQUITECTO]**.
- [ ] Serie COMPLETA verde con los comandos de F6 (incluye `test_harness_flags_requires.py`); tsc 0;
      smoke sin fallos nuevos.
