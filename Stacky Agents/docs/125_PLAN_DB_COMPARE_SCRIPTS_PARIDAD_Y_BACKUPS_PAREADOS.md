# Plan 125 — Comparador de BD entre ambientes (serie 122–126, parte 4/5): scripts de paridad + backups pareados 1:1

**Estado:** PROPUESTO (v1, 2026-07-12)
**Serie:** 122 (núcleo) → 123 (motor de diff) → 124 (UI inmersiva) → **125 (scripts de paridad + backups)** → 126 (paridad de datos)
**Dependencias:** Planes 122 y 123 IMPLEMENTADOS (SchemaDiff v1 y runs, contratos congelados en doc 123 §F1/§F2). El Plan 124 es recomendable pero NO bloqueante (la UI de este plan agrega una tab a `DbComparePage.tsx`; si el 124 no está, se monta igual sobre la página del 122).
**Ortogonal a:** Planes 116/119/120/121.

> Este documento está redactado para que un MODELO MENOR (Haiku, Codex CLI o GitHub
> Copilot Pro) lo implemente SIN inferir nada. Los templates SQL de este doc son LITERALES:
> se implementan carácter a carácter (los tests golden lo verifican). Prohibido desviarse
> de los nombres exactos.

---

## 1. Objetivo + KPI

Pedido textual del operador: *"generación de scripts de paridad … también genera scripts
de backup de las tablas que se van a pisar o modificar"*. Este plan convierte un run
`done` (SchemaDiff v1) en un **bundle descargable de scripts SQL**, en el dialecto del
motor del par, con una **regla dura de emparejamiento**:

> **REGLA DE ORO (invariante testeada):** ningún script de paridad que modifique o pise
> una tabla existe sin su script de RESGUARDO pareado 1:1 — backup de DATOS si la acción
> puede perder datos, y/o rollback DDL si la acción es reversible estructuralmente.

Stacky **genera y muestra; JAMÁS ejecuta**: no existe ningún endpoint que corra estos
scripts contra una BD (human-in-the-loop innegociable, doctrina de toda la serie y
mismo patrón `prohibited_runtime_must_emit_sql` de `services/db_query.py:20-23`).

**KPIs (binarios):**

- **KPI-1 (emparejamiento):** para TODO item del manifest con `destructive=true` o
  `modifies_table=true`, `backup_file` o `rollback_file` es no-nulo — test F3 sobre un
  fixture que cubre todas las acciones.
- **KPI-2 (dialecto exacto):** los emitters producen los templates literales de §F2
  (tests golden por motor).
- **KPI-3 (orden seguro):** con FKs `hija→padre`, el `CREATE TABLE padre` precede a
  `CREATE TABLE hija` y el `DROP TABLE hija` precede a `DROP TABLE padre` — test F4.

## 2. Por qué ahora / gap que cierra

- Los planes 122–124 permiten VER el drift; este plan permite ACTUAR sobre él sin salir
  del lazo humano: el operador baja el bundle, revisa, ejecuta backup primero y paridad
  después, en su herramienta (SSMS / SQL Developer).
- El emparejamiento backup↔paridad es exactamente la parte del pedido que evita el
  incidente clásico ("pisé la tabla sin resguardo"); codificarlo como invariante testeada
  es el valor diferencial del plan.

## 3. Principios y guardarraíles

1. **Generación pura:** los emitters son funciones string→string sin tocar BD (testeables
   como golden). La única I/O es persistir el bundle bajo `data_dir()`.
2. **Dirección única v1:** `align_target` (llevar DESTINO a paridad con ORIGEN, semántica
   congelada en doc 123 §1). Para invertir: correr la comparación al revés. Sin flags de
   dirección mágicas.
3. **Destructivo = explícito:** todo DROP/DELETE va en archivos con prefijo `9xx_destructivo_`
   al FINAL del orden, con encabezado de advertencia; nunca mezclado con lo aditivo.
4. **Identificadores seguros:** SIEMPRE quoted (`[x]` / `"X"`); nombres de backup con
   truncado determinista por límite del motor.
5. **Sin ejecución:** cero endpoints que ejecuten; el bundle es artefacto de disco + zip.
6. **Flags:** ninguna nueva; gatea con el master `STACKY_DB_COMPARE_ENABLED` (122 F0).
7. **Runtimes:** feature de panel; N/A por runtime. **Operador:** cero trabajo nuevo
   obligatorio (el bundle se genera solo si él lo pide con un click).

## 4. Fases

### F1 — Helpers de identificadores y nombres de backup: `services/dbcompare_sqlnames.py`

**Objetivo:** una sola fuente de verdad para quoting y naming, con truncado determinista.

**Archivo a crear:** `Stacky Agents/backend/services/dbcompare_sqlnames.py`

**Símbolos exactos:**
```python
IDENT_MAX = {"sqlserver": 128, "oracle": 128, "sqlite": 128}
# Nota Oracle: 128 vale para 12.2+; si el operador corre 11g/12.1 (límite 30) el nombre
# truncado igual funciona porque el algoritmo de abajo permite forzar max_len=30 por
# parámetro. La UI no expone esto en v1; el generador usa IDENT_MAX del motor.

def quote_ident(name: str, dialect: str) -> str
# sqlserver → "[" + name.replace("]", "]]") + "]"
# oracle    → '"' + name.upper().replace('"', '""') + '"'
# sqlite    → '"' + name.replace('"', '""') + '"'

def qualified(schema: str, name: str, dialect: str) -> str   # quote_ident(schema) + "." + quote_ident(name)

def backup_table_name(table: str, ts: str, max_len: int) -> str
# ts = "yyyymmddHHMM" (12 chars, UTC). candidato = f"{table}_BKP{ts}"
# si len(candidato) <= max_len → candidato
# si no: hash6 = sha256(table.encode()).hexdigest()[:6].upper()
#        head = table[: max_len - 12 - 7]   # 12 = len("_BKP"+hash6+ts[-8:])... NO: fórmula cerrada abajo
#        candidato = f"{head}_BKP{hash6}{ts[4:8]}"  # _BKP + 6 hash + MMDD = 14 chars fijos de sufijo
#        head = table[: max_len - 14]
# determinista: mismo (table, ts, max_len) → mismo nombre. Test golden fija ambos caminos.

def script_filename(seq: int, kind: str, schema: str, name: str) -> str
# f"{seq:03d}_{kind}_{schema}_{name}.sql" con schema/name pasados por _slug():
# _slug = re.sub(r"[^A-Za-z0-9_-]", "_", texto)[:60]
```

**Tests PRIMERO:** `tests/test_plan125_dbcompare_sqlnames.py`
- `test_quote_sqlserver_escapa_corchete` (`ab]c` → `[ab]]c]`), `test_quote_oracle_upper_y_comillas`,
- `test_backup_name_corto_golden` (`CLIENTES`, ts `202607121400`, 128 → `CLIENTES_BKP202607121400`),
- `test_backup_name_truncado_golden` (tabla de 40 chars con max_len=30 → valor literal fijado en el test),
- `test_backup_name_determinista`, `test_script_filename_slug`.

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan125_dbcompare_sqlnames.py -q`

**Criterio binario:** todos verdes.

### F2 — Emitters de paridad y resguardo por dialecto: `services/dbcompare_scripts.py` (parte 1)

**Objetivo:** por cada `DiffItem`/`change` del SchemaDiff v1, emitir el SQL de paridad y su resguardo, según esta tabla CERRADA.

**Archivo a crear:** `Stacky Agents/backend/services/dbcompare_scripts.py`

**Símbolos exactos (parte 1):**
```python
class ScriptPiece(TypedDict):
    action: str            # kind del diff (p.ej. "table_added") o "table_backup"/"rollback_..."
    object_type: str; schema: str; name: str
    sql: str
    destructive: bool      # True si puede perder datos u objetos (DROP TABLE/COLUMN, ALTER type, NOT NULL)
    modifies_table: bool   # True si toca una tabla existente en destino

def emit_parity(item: dict, source_schema_obj: dict, target_schema_obj: dict, dialect: str, ts: str) -> list[ScriptPiece]
def emit_resguardo(piece: ScriptPiece, source_schema_obj: dict, target_schema_obj: dict, dialect: str, ts: str) -> list[ScriptPiece]
def render_create_table(schema: str, name: str, table: dict, dialect: str) -> str
def render_column_def(col: dict, dialect: str) -> str
```

**Tabla de acciones → SQL (templates LITERALES; `<...>` se reemplaza, el resto es fijo):**

| kind | SQL Server | Oracle | destructive / modifies |
|---|---|---|---|
| `table_added` | `render_create_table` + `CREATE INDEX` por índice + `ALTER TABLE <q> ADD CONSTRAINT <fk>` por FK (piezas separadas) | ídem sintaxis Oracle | no / no |
| `table_removed` | `DROP TABLE <q>;` | `DROP TABLE <q>;` | **sí** / sí |
| `column_added` | `ALTER TABLE <q> ADD <col_def>;` — si origen es NOT NULL sin default: emitir `NULL` + línea `-- AJUSTAR: en el origen esta columna es NOT NULL sin default; completá los datos y endurecé después.` | `ALTER TABLE <q> ADD (<col_def>);` misma regla | no / sí |
| `column_removed` | `ALTER TABLE <q> DROP COLUMN <c>;` | `ALTER TABLE <q> DROP COLUMN <c>;` | **sí** / sí |
| `column_type_changed` | `ALTER TABLE <q> ALTER COLUMN <c> <tipo_origen> <NULL\|NOT NULL>;` | `ALTER TABLE <q> MODIFY (<c> <tipo_origen>);` | **sí** / sí |
| `column_nullable_*` | mismo `ALTER ... ALTER COLUMN` con tipo actual del ORIGEN | `ALTER TABLE <q> MODIFY (<c> <NULL\|NOT NULL>);` | tightened **sí**, relaxed no / sí |
| `column_default_changed` | bloque literal §abajo (drop default dinámico + `ADD CONSTRAINT DF_<t>_<c> DEFAULT <expr> FOR <c>`) | `ALTER TABLE <q> MODIFY (<c> DEFAULT <expr>);` | no / sí |
| `pk_changed` | `ALTER TABLE <q> DROP CONSTRAINT <pk_dest>;` + `ALTER TABLE <q> ADD CONSTRAINT <pk_src_name_o_PK_tabla> PRIMARY KEY (<cols>);` | ídem | **sí** / sí |
| `fk_added` / `unique_added` / `check_added` | `ALTER TABLE <q> ADD CONSTRAINT <n> FOREIGN KEY (<cols>) REFERENCES <q_ref> (<cols_ref>);` / `... UNIQUE (<cols>);` / `... CHECK (<sqltext>);` | ídem | no / sí |
| `fk_removed` / `unique_removed` / `check_removed` | `ALTER TABLE <q> DROP CONSTRAINT <n>;` | ídem | no (unique_removed **sí** según tabla 123) / sí |
| `fk_changed` / `check_changed` / `index_changed` | pieza DROP + pieza ADD/CREATE (dos ScriptPiece) | ídem | no / sí |
| `index_added` | `CREATE [UNIQUE ]INDEX <n> ON <q> (<cols>);` | ídem | no / no |
| `index_removed` | `DROP INDEX <n_q> ON <q>;` | `DROP INDEX <n_q>;` | no / sí |
| `view_added` / `view_definition_changed` | `CREATE OR ALTER VIEW <q> AS`\n`<definition>` — si `definition` es None → TODO el script comentado con `-- DEFINICIÓN NO CAPTURADA EN SNAPSHOT; completar a mano` | `CREATE OR REPLACE VIEW <q> AS ...` misma regla | no / no |
| `view_removed` | `DROP VIEW <q>;` | `DROP VIEW <q>;` | no / no |
| `sequence_added` | `CREATE SEQUENCE <q> START WITH 1; -- START WITH no capturado en snapshot v1` | ídem | no / no |
| `sequence_removed` | `DROP SEQUENCE <q>;` | `DROP SEQUENCE <q>;` | no / no |

Bloque SQL Server `column_default_changed` (LITERAL):
```sql
DECLARE @df sysname;
SELECT @df = dc.name FROM sys.default_constraints dc
JOIN sys.columns c ON c.default_object_id = dc.object_id
WHERE dc.parent_object_id = OBJECT_ID(N'<schema>.<tabla>') AND c.name = N'<columna>';
IF @df IS NOT NULL EXEC(N'ALTER TABLE <q> DROP CONSTRAINT [' + @df + N']');
ALTER TABLE <q> ADD CONSTRAINT [DF_<tabla>_<columna>] DEFAULT <expr> FOR [<columna>];
```

**Reglas de resguardo (`emit_resguardo`):**
- Pieza con `destructive=true` que toca DATOS (`table_removed`, `column_removed`,
  `column_type_changed`, `column_nullable_tightened`, `pk_changed`, `unique_removed`) →
  **backup de datos de la tabla** (1 solo por tabla por bundle, dedupe por `(schema, tabla)`):
  - sqlserver: `SELECT * INTO <q_schema>.[<bkp>] FROM <q>;`
  - oracle: `CREATE TABLE <q_schema>."<BKP>" AS SELECT * FROM <q>;`
  - `<bkp> = backup_table_name(tabla, ts, IDENT_MAX[dialect])` (F1).
- Pieza que DROPea o cambia un objeto reconstruible (`index_removed`, `fk_removed`,
  `unique_removed`, `check_removed`, `view_removed`, `*_changed` estructurales,
  `table_removed`, `pk_changed`) → **rollback DDL**: el CREATE/ADD equivalente generado
  desde el snapshot DESTINO (el objeto que hoy existe), con encabezado
  `-- ROLLBACK: recrea el objeto tal como existía en <target_alias> el <ts>`.
  Para `table_removed` el rollback es `render_create_table` del destino + nota
  `-- Los DATOS se restauran desde la tabla de backup pareada.`
- Piezas aditivas puras (`table_added`, `column_added`, `index_added`, `fk_added`, vistas,
  secuencias) → sin backup (nada se pisa); el manifest lo deja explícito con `backup_file: null`.

**Encabezado obligatorio de CADA archivo .sql generado (LITERAL):**
```sql
-- Generado por Stacky · Comparador de BD (plan 125) · NO EJECUTADO por Stacky.
-- Corrida: <run_id> · Origen: <source_alias> · Destino: <target_alias> · Motor: <dialect>
-- ORDEN: ejecutar SIEMPRE los backups (01_...) antes que la paridad (2xx/9xx).
```
(+ para `9xx_destructivo_*`: `-- ⚠ DESTRUCTIVO: revisá el backup pareado ANTES de ejecutar.`)

**Tests PRIMERO:** `tests/test_plan125_dbcompare_emitters_sqlserver.py` y
`tests/test_plan125_dbcompare_emitters_oracle.py`
- 1 test golden por kind de la tabla (string EXACTO, incluyendo el bloque default dinámico),
- `test_column_added_notnull_sin_default_comenta`,
- `test_view_sin_definicion_todo_comentado`,
- `test_backup_dedupe_por_tabla`.

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan125_dbcompare_emitters_sqlserver.py tests/test_plan125_dbcompare_emitters_oracle.py -q`

**Criterio binario:** golden tests verdes carácter a carácter (KPI-2).

### F3 — Bundle + manifest con emparejamiento: `services/dbcompare_scripts.py` (parte 2)

**Objetivo:** materializar el bundle ordenado en disco con manifest que fija el pareo 1:1.

**Símbolos exactos (parte 2):**
```python
_BUNDLES_DIRNAME = "db_compare/bundles"    # data_dir()/db_compare/bundles/<run_id>/
MANIFEST_VERSION = 1

def generate_parity_bundle(run_id: str) -> dict     # → manifest; DbCompareRunError si run no done
def load_manifest(run_id: str) -> dict | None
def bundle_zip_bytes(run_id: str) -> bytes          # zipfile en BytesIO con TODO el bundle
```

**Layout del bundle en disco:**
```
<run_id>/
  README.md            ← orden de ejecución + advertencias + pareos (render desde manifest)
  MANIFEST.json
  01_backups/001_table_backup_dbo_CLIENTES.sql
  01_backups/002_rollback_index_removed_dbo_IX_CLIENTES_DOC.sql
  02_paridad/201_table_added_dbo_NUEVA.sql
  02_paridad/202_column_added_dbo_CLIENTES.sql
  09_destructivo/901_column_removed_dbo_CLIENTES.sql
  09_destructivo/902_table_removed_dbo_VIEJA.sql
```
- Numeración: backups/rollbacks 001+, paridad no destructiva 201+, destructivos 901+
  (`script_filename` de F1 con el `seq` global de cada grupo).

**Manifest (contrato v1):**
```json
{
  "version": 1, "run_id": "...", "generated_at": "...Z",
  "engine": "sqlserver", "source_alias": "...", "target_alias": "...",
  "entries": [
    {
      "seq": 201, "file": "02_paridad/201_...sql", "action": "column_added",
      "object_type": "table", "schema": "dbo", "name": "CLIENTES",
      "destructive": false, "modifies_table": true,
      "backup_file": "01_backups/001_...sql" | null,
      "rollback_file": "01_backups/002_...sql" | null
    }
  ],
  "counts": {"backups": 0, "parity": 0, "destructive": 0}
}
```
- **Invariante (KPI-1) implementada como assert final de `generate_parity_bundle`:**
  toda entry con `destructive or modifies_table` tiene `backup_file or rollback_file`;
  si no se cumple → excepción (nunca se persiste un bundle inválido).
- Regenerar un bundle existente → borra el directorio del run y lo reescribe (idempotente).

**Orden FK-safe (función interna `_ordered_pieces`):**
- Grafo de dependencia con las FKs del snapshot ORIGEN para creates (`table_added`):
  toposort padres→hijos (Kahn; empates por nombre ASC).
- Para drops (`table_removed`): toposort con FKs del snapshot DESTINO, hijos→padres.
- Ciclo detectado → orden alfabético del subconjunto cíclico + línea en README:
  `⚠ Ciclo de FKs detectado entre: <tablas>; revisá el orden manualmente.`

**Tests PRIMERO:** `tests/test_plan125_dbcompare_bundle.py`
- `test_bundle_layout_y_numeracion` (fixture diff con 1 kind de cada grupo → archivos exactos),
- `test_invariante_pareo_kpi1` (recorre manifest: toda entry destructiva/modificante pareada),
- `test_manifest_backup_null_en_aditivas`,
- `test_regenerar_idempotente`,
- `test_zip_contiene_todo` (namelist del zip == archivos del bundle).

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan125_dbcompare_bundle.py -q`

**Criterio binario:** todos verdes; KPI-1 demostrado.

### F4 — Orden seguro por FKs (tests dedicados)

**Objetivo:** blindar el toposort con casos reales.

**Tests PRIMERO:** `tests/test_plan125_dbcompare_toposort.py`
- `test_create_padre_antes_que_hija` (KPI-3),
- `test_drop_hija_antes_que_padre` (KPI-3),
- `test_cadena_tres_niveles`,
- `test_ciclo_cae_a_alfabetico_con_warning` (README contiene la línea literal de §F3).

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan125_dbcompare_toposort.py -q`

**Criterio binario:** 4 verdes.

### F5 — API del bundle en `api/db_compare.py`

**Objetivo:** generar/consultar/descargar por HTTP con el gate del master.

**Endpoints exactos (mismo blueprint, mismo `_require_enabled`):**
| Método y ruta | Comportamiento |
|---|---|
| `POST /runs/<run_id>/scripts` | `generate_parity_bundle`; 200 `{ok, manifest}`; run no done → 409; run inexistente → 404 |
| `GET /runs/<run_id>/scripts` | `load_manifest` → 200 / 404 si no generado aún |
| `GET /runs/<run_id>/scripts/file?path=<rel>` | contenido `text/plain; charset=utf-8`; SOLO paths presentes en el manifest o `README.md`/`MANIFEST.json` (allowlist contra path traversal; `..` → 400) |
| `GET /runs/<run_id>/scripts.zip` | `bundle_zip_bytes` con `Content-Type: application/zip` + `Content-Disposition: attachment; filename="dbcompare_<run_id>.zip"` |

**Tests PRIMERO:** `tests/test_plan125_dbcompare_scripts_api.py`
- `test_generar_y_leer_manifest`, `test_run_no_done_409`, `test_file_allowlist_y_traversal_400`,
- `test_zip_headers`, `test_flag_off_403`.

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan125_dbcompare_scripts_api.py -q`

**Criterio binario:** todos verdes.

### F6 — UI: tab "Scripts" pareada en la sección

**Objetivo:** ver, copiar y descargar los pares backup↔paridad sin ambigüedad, con la advertencia HITL siempre visible.

**Archivos a crear en `Stacky Agents/frontend/src/components/dbcompare/`:**
- `scriptsLogic.ts` (puro):
```ts
export interface ScriptPairRow { seq: number; file: string; action: string; objectLabel: string;
  destructive: boolean; backupFile: string | null; rollbackFile: string | null; grupo: "backup"|"paridad"|"destructivo" }
export function buildScriptRows(manifest: Manifest): ScriptPairRow[]   // orden por seq; grupo derivado del prefijo de file
export function pairingBadge(row: ScriptPairRow): "backup"|"rollback"|"backup+rollback"|"sin resguardo (aditivo)"
```
- `ScriptsPanel.tsx` — dentro de `DbComparePage`, tab `Scripts` visible cuando el run está
  `done`: si no hay manifest → botón primario `Generar scripts de paridad + backups`
  (POST F5) con spinner; con manifest → banner fijo superior (LITERAL):
  `🛑 Stacky genera; VOS ejecutás. Orden: 1) backups → 2) paridad → 3) destructivos (revisados).`
  y tabla de `ScriptPairRow`: seq, objeto, acción, chip rojo `DESTRUCTIVO` si aplica,
  badge de pareo (de `pairingBadge`), acciones por fila: `Ver` (abre `SqlViewer`),
  `Copiar`, `Descargar`. Footer: `Descargar TODO (.zip)` → `scripts.zip` + contadores del
  manifest (`N backups · N paridad · N destructivos`).
- `SqlViewer.tsx` — modal con `<pre>` monoespaciada del contenido (fetch `scripts/file`),
  título = filename, botones `Copiar` y `Descargar`; si la fila tiene `backupFile`, el
  modal muestra AMBOS lados (split vertical): izquierda backup/rollback, derecha paridad —
  el pareo 1:1 literal en pantalla.
- `endpoints.ts`: `DbCompare.generateScripts(runId)`, `getManifest(runId)`,
  `scriptFileUrl(runId, path)`, `scriptsZipUrl(runId)`.

**Tests PRIMERO:** `frontend/src/components/dbcompare/__tests__/scriptsLogic.test.ts`
- `buildScriptRows` orden y grupos (fixture manifest con los 3 grupos),
- `pairingBadge` (4 casos exactos).

**Comando:** `cd "Stacky Agents/frontend" && npx vitest run src/components/dbcompare/__tests__/scriptsLogic.test.ts` y `npx tsc --noEmit`

**Criterio binario:** vitest verde + tsc 0.

### F7 — No-regresión y cierre

**Comandos:**
```
cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan125_dbcompare_sqlnames.py tests/test_plan125_dbcompare_emitters_sqlserver.py tests/test_plan125_dbcompare_emitters_oracle.py tests/test_plan125_dbcompare_bundle.py tests/test_plan125_dbcompare_toposort.py tests/test_plan125_dbcompare_scripts_api.py -q
cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan122_dbcompare_api.py tests/test_plan123_dbcompare_api.py tests/test_smoke.py -q
cd "Stacky Agents/frontend" && npx vitest run src/components/dbcompare/ && npx tsc --noEmit
```
**Criterio binario:** suites 125 verdes; 122/123/smoke sin fallos nuevos; tsc 0.

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El operador ejecuta paridad sin backup | Numeración fuerza backups primero; README + banner UI + encabezado de cada .sql lo repiten; el pareo es visible en la tabla y en el SqlViewer split. |
| Tipos con sintaxis no portable entre versiones del motor | El tipo viene LITERAL del snapshot del mismo motor (str(col.type) del dialecto real); no traducimos tipos. |
| Nombre de backup colisiona (2 corridas mismo minuto) | `ts` con minutos + regenerar borra el bundle previo del run; colisión entre runs distintos es imposible (directorio por run_id). En la BD real, si la tabla `_BKP...` ya existe el script falla ANTES de tocar datos (fail-safe correcto). |
| Path traversal en `scripts/file` | Allowlist estricta desde el manifest (test dedicado). |
| Vistas sin definición capturada | Script completo comentado + nota; nunca un CREATE VIEW vacío ejecutable. |
| Defaults SQL Server sin nombre de constraint en snapshot | Bloque dinámico literal de §F2 que resuelve el nombre en ejecución. |

## 6. Fuera de scope

- Scripts de paridad de DATOS (INSERT/UPDATE/DELETE) y sus backups → **Plan 126**
  (extiende este bundle con `03_datos/`).
- Ejecutar scripts desde Stacky (prohibido por diseño, toda la serie).
- Migraciones incrementales versionadas (tipo alembic/flyway) — esto es paridad puntual.
- Permisos/grants, particionamiento, estadísticas, triggers y SPs (fuera del snapshot v1).

## 7. Glosario

- **Bundle:** carpeta por run con README, MANIFEST y los .sql ordenados.
- **Pareo 1:1:** relación manifest `entry.backup_file/rollback_file` ↔ script de paridad.
- **Backup de datos:** copia física de la tabla (`SELECT * INTO` / `CREATE TABLE AS SELECT`).
- **Rollback DDL:** CREATE/ADD inverso generado desde el snapshot del DESTINO.
- **Destructivo:** acción que puede perder datos u objetos; vive en `09_destructivo/`.
- **align_target:** única dirección v1 — llevar el destino a paridad con el origen.

## 8. Orden de implementación

1. F1 sqlnames + tests golden.
2. F2 emitters + tests golden por dialecto.
3. F3 bundle + manifest + invariante.
4. F4 toposort (tests dedicados).
5. F5 API.
6. F6 UI tab Scripts.
7. F7 no-regresión.

## 9. Definición de Hecho (DoD)

- [ ] Emitters literales por dialecto con golden tests (KPI-2), incluyendo casos comentados (view sin definición, NOT NULL sin default).
- [ ] Invariante de pareo 1:1 implementada como assert + test (KPI-1): imposible persistir bundle inválido.
- [ ] Orden: backups → paridad → destructivos; FK-safe demostrado (KPI-3); ciclos degradan con warning explícito.
- [ ] Bundle en disco + manifest v1 + zip descargable; allowlist anti-traversal testeada.
- [ ] Tab Scripts con pareo visible, banner HITL literal, copiar/descargar por archivo y zip.
- [ ] 6 archivos de test backend + 1 vitest verdes (comandos exactos); 122/123/smoke sin fallos nuevos; tsc 0.
- [ ] Cero endpoints que ejecuten SQL generado (grep de la review: ningún `execute` sobre contenido de bundle).
