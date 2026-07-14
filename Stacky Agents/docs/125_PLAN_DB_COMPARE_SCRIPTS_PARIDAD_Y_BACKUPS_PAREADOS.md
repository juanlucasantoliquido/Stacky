# Plan 125 — Comparador de BD entre ambientes (serie 122–126, parte 4/5): scripts de paridad + backups pareados 1:1

**Estado:** CRITICADO — APROBADO-CON-CAMBIOS (v1.1 → v2, 2026-07-14, juez `StackyArchitectaUltraEficientCode`) + IMPLEMENTADO COMPLETO 2026-07-14 (rama `plan-125-dbcompare-scripts`): F0-F6 verdes (152 tests backend combinados 125+122+123; 16 vitest frontend; tsc 0). El GAP original de F5/F3-wrapper/F6-UI (Planes 122/123 ausentes al momento de criticar) se CERRÓ el mismo día: el operador mergeó Plan 122 (núcleo) y Plan 123 completo (F1-F5) a `main`; tras `git merge main` en este worktree, `services.dbcompare_runs`/`dbcompare_snapshot`/`api/db_compare.py` quedaron disponibles de verdad y se completó la integración real. El Plan 124 (UI inmersiva de corridas) sigue sin implementar — F6 monta `ScriptsPanel` con un input manual de `run_id` en vez de un selector visual de corridas, documentado como alcance mínimo honesto (ver F6).
**Serie:** 122 (núcleo) → 123 (motor de diff) → 124 (UI inmersiva) → **125 (scripts de paridad + backups)** → 126 (paridad de datos)
**Dependencias:** Planes 122 y 123 — **contrato CONGELADO EN PAPEL** (§F1/§F3 de 122, §F1/§F2 de 123), pero el CÓDIGO puede no estar mergeado a `main` todavía cuando se implemente este plan (desarrollo con múltiples worktrees en paralelo — ver C1). Este plan NO asume código de 122/123 presente: **F0 (nueva)** lo verifica en runtime, y F1/F2/F4 son puros y se testean con fixtures dict propias sin importar nada de 122/123. Solo F3 (wrapper por `run_id`), F5 (API) y F6 (montaje en `DbComparePage`) requieren integración real; si al implementar no existen los módulos de 122/123/124, esas fases se documentan como GAP explícito (ver F0) — no se inventa infraestructura ajena en su lugar. El Plan 124 es recomendable pero NO bloqueante.
**Ortogonal a:** Planes 116/119/120/121.

> Este documento está redactado para que un MODELO MENOR (Haiku, Codex CLI o GitHub
> Copilot Pro) lo implemente SIN inferir nada. Los templates SQL de este doc son LITERALES:
> se implementan carácter a carácter (los tests golden lo verifican). Prohibido desviarse
> de los nombres exactos.

## Changelog v1.1 → v2 (crítica adversarial)

- **[C1 – IMPORTANTE]** "Dependencias" afirmaba "122 y 123 IMPLEMENTADOS" sin matiz. Verificado empíricamente en el worktree de implementación real: CERO código de `dbcompare` existía (122 en rama hermana no mergeada; 123 seguía PROPUESTO v1.1, ni criticado). Fix: dependencia reformulada como "papel, no código" + **F0 nueva** (preflight que detecta qué módulos existen y gatea F3/F5/F6 sin bloquear F1/F2/F4).
- **[C2 – IMPORTANTE]** Faltaba el símbolo que traduce el SchemaDiff v1 real de doc 123 (anidado `items[] → changes[]`, con `schema`/`name`/`object_type` SOLO en el item padre) al modelo plano que la tabla de F2 asume (`item: dict` con `kind` uniforme). Fix: nueva función `flatten_diff` en F2 con contrato exacto + tests golden. Si el contrato final de 123 difiere en el nombre de algún campo, ajustar SOLO `flatten_diff` (no rediseñar F2).
- **[C3 – IMPORTANTE]** Celda de la tabla F2 para `unique_removed` se contradecía a sí misma ("no (unique_removed **sí**...)"). Fix: redactada sin ambigüedad.
- **[C4 – IMPORTANTE]** `generate_parity_bundle` corría el assert de invariante KPI-1 "al final", permitiendo persistir archivos parciales si dispara a mitad de escritura — contradice la propia garantía ("nunca se persiste un bundle inválido"). Fix: construir todo en memoria, validar, y RECIÉN ENTONCES escribir vía `<run_id>.tmp/` + `os.replace` (mismo patrón atómico de doc 123 §F2).
- **[C5 – MENOR]** F5 decía "mismo blueprint" sin nombrar el símbolo Flask exacto. Fix: nombre exacto + regla de no crear un blueprint paralelo si falta.
- **[C6 – MENOR]** F7 exige "sin fallos nuevos" en `test_smoke.py` sin método de comparación. Fix: capturar baseline antes de tocar código, diff de nombres de test fallidos.
- **[ADICIÓN ARQUITECTO]** F0 nueva: preflight de dependencias determinista y testeado que desbloquea implementar F1/F2/F4 de forma aislada (TDD real, sin BD, sin código de 122/123) y documenta como GAP explícito lo que F3/F5/F6 no puedan completar — sin bloquear todo el plan ni que un modelo menor tenga que adivinar qué hacer.

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

### F0 — [ADICIÓN ARQUITECTO] Preflight de dependencias: `services/dbcompare_deps_preflight.py`

**Objetivo:** verificar en runtime, de forma determinista, qué módulos de 122/123/124 existen
en ESTE checkout antes de tocar F3/F5/F6 — sin bloquear F1/F2/F4 (puros, no dependen de nada).

**Archivo a crear:** `Stacky Agents/backend/services/dbcompare_deps_preflight.py`

**Símbolos exactos:**
```python
REQUIRED_MODULES = {
    "diff_engine": "services.dbcompare_diff",      # Plan 123 F1: diff_snapshots
    "runs_store": "services.dbcompare_runs",        # Plan 123 F2: get_run/list_runs
    "api_blueprint": "api.db_compare",              # Plan 122 F4 / 123 F3: blueprint Flask
}

def check_dependencies() -> dict
# usa importlib.util.find_spec(module) is not None por cada entrada — SIN import real
# (evita romper el arranque si el módulo está a medio escribir).
# → {"diff_engine": bool, "runs_store": bool, "api_blueprint": bool, "all_present": bool}

def require_or_gap(component: str) -> None
# si check_dependencies()[component] es False: no lanza excepción — el CALLER (F3/F5) decide
# qué hacer (ver regla abajo). Esta función solo documenta la intención; el chequeo real
# lo hace cada fase con check_dependencies() al inicio de su implementación.
```

**Regla de uso (aplica a F3/F5/F6, NO a F1/F2/F4):**
- Antes de implementar F3 (wrapper `generate_parity_bundle(run_id)`), F5 (API) o F6 (montaje
  en `DbComparePage`), correr `check_dependencies()`. Si el componente requerido es `False`:
  NO inventar un módulo placeholder ni un blueprint paralelo. Implementar y testear la parte
  PURA de esa fase que no requiere el módulo ausente (ver notas puntuales en F3/F5/F6), dejar
  el resto sin tocar, y reportarlo como GAP explícito en el resumen de la implementación
  (qué falta, qué módulo/símbolo se esperaba, y que NO es un bug de este plan sino una
  dependencia de otro plan en curso).
- Esto es infraestructura de gating, no funcionalidad de negocio: no agrega flags, no requiere
  configuración del operador, no tiene impacto de runtime (N/A, panel backend).

**Tests PRIMERO:** `tests/test_plan125_dbcompare_preflight.py`
- `test_check_dependencies_reporta_bool_por_componente` (monkeypatch `importlib.util.find_spec`
  para simular presente/ausente por módulo, sin importar nada real),
- `test_all_present_true_solo_si_los_tres_estan`,
- `test_no_importa_el_modulo_real` (espía sobre `find_spec`; nunca se llama `importlib.import_module`).

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan125_dbcompare_preflight.py -q`

**Criterio binario:** todos verdes. **Flag:** ninguna. **Runtimes:** N/A. **Operador:** ninguno.

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
# CONVENCIÓN DEL OPERADOR (Backup-TestTables.ps1 y backups manuales preexistentes en TEST:
# IN_CLIE_BAK, RCLIE_BAK, ... — ver doc 122 §2-bis): sufijo "_BAK_" + timestamp.
# ts = "yyyymmdd_HHMMSS" (15 chars, UTC). candidato = f"{table}_BAK_{ts}"   # sufijo fijo: 20 chars
# si len(candidato) <= max_len → candidato
# si no: hash6 = sha256(table.encode()).hexdigest()[:6].upper()
#        head = table[: max_len - 14]
#        candidato = f"{head}_BAK{hash6}{ts[4:8]}"   # "_BAK" + hash6 + MMDD = 14 chars fijos de sufijo
# determinista: mismo (table, ts, max_len) → mismo nombre. Test golden fija ambos caminos.

def script_filename(seq: int, kind: str, schema: str, name: str) -> str
# f"{seq:03d}_{kind}_{schema}_{name}.sql" con schema/name pasados por _slug():
# _slug = re.sub(r"[^A-Za-z0-9_-]", "_", texto)[:60]
```

**Tests PRIMERO:** `tests/test_plan125_dbcompare_sqlnames.py`
- `test_quote_sqlserver_escapa_corchete` (`ab]c` → `[ab]]c]`), `test_quote_oracle_upper_y_comillas`,
- `test_backup_name_corto_golden` (`CLIENTES`, ts `20260712_140000`, 128 → `CLIENTES_BAK_20260712_140000`),
- `test_backup_name_truncado_golden` (tabla de 40 chars con max_len=30 → valor literal fijado en el test),
- `test_backup_name_determinista`, `test_script_filename_slug`.

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan125_dbcompare_sqlnames.py -q`

**Criterio binario:** todos verdes.

### F2 — Emitters de paridad y resguardo por dialecto: `services/dbcompare_scripts.py` (parte 1)

**Objetivo:** por cada pieza APLANADA del SchemaDiff v1, emitir el SQL de paridad y su resguardo, según esta tabla CERRADA.

**Archivo a crear:** `Stacky Agents/backend/services/dbcompare_scripts.py`

**[FIX C2 — IMPORTANTE] `flatten_diff`: traduce el SchemaDiff v1 real (doc 123 §F1, anidado
`items[] → changes[]`, con `schema`/`name`/`object_type` SOLO en el item padre) al modelo
plano `item: dict` con `kind` uniforme que asume la tabla de abajo. Sin esta función un
implementador tendría que ADIVINAR cómo combinar item padre + change hijo — queda prohibido
inferir, el contrato es este:**
```python
def flatten_diff(diff: dict) -> list[dict]
# Recorre diff["items"] en orden. Por cada item:
#   - si item["action"] in ("added", "removed"): 1 pieza
#       {"kind": f'{item["object_type"]}_{item["action"]}',   # ej. "table_added", "view_removed"
#        "object_type": item["object_type"], "schema": item["schema"], "name": item["name"],
#        "detail": {}}
#   - si item["action"] == "changed": por cada c en item["changes"] (en orden), 1 pieza
#       {"kind": c["kind"], "object_type": item["object_type"], "schema": item["schema"],
#        "name": item["name"], "detail": c["detail"]}
# Determinista: mismo orden que diff["items"]/diff["items"][i]["changes"].
# El "item: dict" que reciben emit_parity/emit_resguardo de acá en más ES una pieza aplanada
# (tiene siempre kind/object_type/schema/name/detail), NUNCA un item ni un change crudos.
```

**Símbolos exactos (parte 1):**
```python
class ScriptPiece(TypedDict):
    action: str            # kind del diff (p.ej. "table_added") o "table_backup"/"rollback_..."
    object_type: str; schema: str; name: str
    sql: str
    destructive: bool      # True si puede perder datos u objetos (DROP TABLE/COLUMN, ALTER type, NOT NULL)
    modifies_table: bool   # True si toca una tabla existente en destino

def emit_parity(item: dict, source_schema_obj: dict, target_schema_obj: dict, dialect: str, ts: str) -> list[ScriptPiece]
# item = una pieza aplanada de flatten_diff (kind/object_type/schema/name/detail)
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
| `fk_removed` / `check_removed` | `ALTER TABLE <q> DROP CONSTRAINT <n>;` | ídem | no / sí |
| `unique_removed` | `ALTER TABLE <q> DROP CONSTRAINT <n>;` | ídem | **[FIX C3] sí** (toca datos indirectamente: pierde la garantía de unicidad; requiere backup de datos igual que `pk_changed`, ver reglas de resguardo abajo) / sí |
| `fk_changed` / `check_changed` / `index_changed` | NO llegan del diff v1.1 (doc 123: los cambios de firma se reportan como `*_removed` + `*_added`, ya cubiertos arriba); si un diff futuro los emitiera: pieza DROP + pieza ADD/CREATE (dos ScriptPiece) | ídem | no / sí |
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
  **backup de datos de la tabla** (1 solo por tabla por bundle, dedupe por `(schema, tabla)`),
  CON VERIFICACIÓN DE COUNTS EMBEBIDA (doctrina Backup-TestTables.ps1: reporta OK solo si
  origen==backup; acá la verificación viaja DENTRO del script generado). Templates literales:
  - sqlserver:
    ```sql
    SELECT * INTO <q_schema>.[<bkp>] FROM <q>;
    IF (SELECT COUNT(*) FROM <q_schema>.[<bkp>]) <> (SELECT COUNT(*) FROM <q>)
        THROW 50001, 'BACKUP INCOMPLETO: counts no coinciden para <schema>.<tabla> - NO CONTINUAR con la paridad', 1;
    ```
    (SELECT INTO falla solo si `<bkp>` ya existe → nunca pisa un backup previo, mismo fail-safe del script del operador.)
  - oracle:
    ```sql
    CREATE TABLE <q_schema>."<BKP>" AS SELECT * FROM <q>;
    DECLARE v_src NUMBER; v_bak NUMBER;
    BEGIN
      SELECT COUNT(*) INTO v_src FROM <q>;
      SELECT COUNT(*) INTO v_bak FROM <q_schema>."<BKP>";
      IF v_src <> v_bak THEN
        RAISE_APPLICATION_ERROR(-20001, 'BACKUP INCOMPLETO: counts no coinciden para <schema>.<tabla> - NO CONTINUAR con la paridad');
      END IF;
    END;
    /
    ```
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

**Tests PRIMERO:** `tests/test_plan125_dbcompare_emitters_sqlserver.py`,
`tests/test_plan125_dbcompare_emitters_oracle.py` y `tests/test_plan125_dbcompare_flatten.py`
- `test_flatten_diff_added_removed_sintetiza_kind` (item `action="added"` sin `changes` → 1 pieza `kind=f"{object_type}_added"`),
- `test_flatten_diff_changed_hereda_schema_name_del_item` (item `action="changed"` con 2 `changes` → 2 piezas, ambas con el `schema`/`name`/`object_type` del item padre),
- `test_flatten_diff_orden_preservado`,
- 1 test golden por kind de la tabla (string EXACTO, incluyendo el bloque default dinámico),
- `test_column_added_notnull_sin_default_comenta`,
- `test_view_sin_definicion_todo_comentado`,
- `test_backup_dedupe_por_tabla`,
- `test_backup_incluye_verificacion_counts` (golden: el THROW/RAISE_APPLICATION_ERROR está en el script, por dialecto),
- `test_unique_removed_es_destructive_true` (regresión del FIX C3).

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan125_dbcompare_flatten.py tests/test_plan125_dbcompare_emitters_sqlserver.py tests/test_plan125_dbcompare_emitters_oracle.py -q`

**Criterio binario:** golden tests verdes carácter a carácter (KPI-2).

### F3 — Bundle + manifest con emparejamiento: `services/dbcompare_scripts.py` (parte 2)

**Objetivo:** materializar el bundle ordenado en disco con manifest que fija el pareo 1:1.

**[NOTA C1 — gap conocido]** `generate_parity_bundle(run_id)` necesita cargar un run real vía
`services.dbcompare_runs.get_run(run_id)` (Plan 123 F2). Correr `dbcompare_deps_preflight.check_dependencies()["runs_store"]`
(F0) ANTES de implementar el wrapper: si es `False`, implementar y testear IGUAL la función
interna pura `_materialize_bundle(diff: dict, run_meta: dict) -> dict` (todo lo de abajo:
layout, numeración, manifest, invariante KPI-1, atomicidad) contra fixtures `diff` dict propias
(sin importar `dbcompare_runs`), y dejar `generate_parity_bundle(run_id)` como wrapper delgado
con `try: from services.dbcompare_runs import get_run except ImportError: raise DbCompareRunError(...)`
— reportar esto como GAP en el resumen final, NO simular ni inventar un `dbcompare_runs` propio.

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
- **[FIX C4 — IMPORTANTE] Invariante (KPI-1) y escritura ATÓMICA:** construir el manifest
  COMPLETO y el contenido de cada archivo .sql/README EN MEMORIA primero; recién con todo
  armado, correr el assert: toda entry con `destructive or modifies_table` tiene
  `backup_file or rollback_file`; si falla → `DbCompareRunError`, CERO bytes tocados en disco.
  Si pasa: escribir todo bajo `<_BUNDLES_DIRNAME>/<run_id>.tmp/` y recién al final
  `os.replace(tmp_dir, final_dir)` (mismo patrón atómico que `<run_id>.json.tmp` + `os.replace`
  de doc 123 §F2 para los runs). Así "nunca se persiste un bundle inválido" es una garantía
  real y no depende de dónde caiga el assert.
- Regenerar un bundle existente → borra el directorio del run y lo reescribe (idempotente).
- El `README.md` del bundle incluye SIEMPRE esta regla literal (doctrina del paso 0 de
  `Invoke-DevTestParityReplay.ps1`, ver doc 122 §2-bis):
  `🛑 Si CUALQUIER backup falla su verificación de counts: NO ejecutar NINGÚN script de paridad ni destructivo. Primero resolver el backup.`

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

**[NOTA C1 — gap conocido]** Correr `check_dependencies()["api_blueprint"]` (F0) antes de
tocar esta fase. Si es `False`, `api/db_compare.py` (con su blueprint Flask, esperado como
`db_compare_bp` por Plan 122 F4/123 F3) todavía no existe en este checkout: NO crear un
blueprint paralelo ni un archivo `api/db_compare.py` propio (colisionaría al mergear 122).
Implementar F5 completo QUEDA COMO GAP documentado en el resumen; los tests de F5 quedan
sin correr (no hay blueprint donde registrar las rutas) y se reporta explícitamente.

**[FIX C5 — MENOR] Endpoints exactos (mismo blueprint `db_compare_bp` de `api/db_compare.py`,
mismo `_require_enabled` — NO crear un blueprint nuevo, agregar rutas al existente):**
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

**[NOTA C1 — gap conocido]** `ScriptsPanel.tsx`/`SqlViewer.tsx` montan DENTRO de `DbComparePage`
(Plan 122 F5 / 124). Si ese componente no existe todavía en este checkout, esas dos piezas
quedan como GAP documentado (no se inventa una página contenedora). `scriptsLogic.ts` es PURO
(no importa nada de `DbComparePage` ni de la API) y se implementa y testea SIEMPRE, exista o
no el resto — es la parte de valor que no depende de 122/123/124.

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

**[FIX C6 — MENOR] Baseline antes de tocar código:** ANTES de la fase F1, correr
`.venv\Scripts\python.exe -m pytest tests/test_smoke.py -q` una vez y guardar la lista de
tests que fallan (si alguno) como baseline. Al cerrar F7, "sin fallos nuevos" significa: el
conjunto de tests fallidos después es subconjunto del baseline (comparar NOMBRES de test, no
conteo total — un test nuevo que falla por otra razón puede compensar uno que empieza a pasar
y esconder una regresión real si solo se compara el número).

**Comandos:**
```
cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan125_dbcompare_preflight.py tests/test_plan125_dbcompare_sqlnames.py tests/test_plan125_dbcompare_flatten.py tests/test_plan125_dbcompare_emitters_sqlserver.py tests/test_plan125_dbcompare_emitters_oracle.py tests/test_plan125_dbcompare_bundle.py tests/test_plan125_dbcompare_toposort.py tests/test_plan125_dbcompare_scripts_api.py -q
cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan122_dbcompare_api.py tests/test_plan123_dbcompare_api.py tests/test_smoke.py -q
cd "Stacky Agents/frontend" && npx vitest run src/components/dbcompare/ && npx tsc --noEmit
```
Si `test_plan122_dbcompare_api.py`/`test_plan123_dbcompare_api.py` no existen todavía en el
checkout (ver F0/C1), se omiten del comando (no es un fallo, es ausencia de archivo) y se
documenta en el resumen.

**Criterio binario:** suites 125 presentes verdes; 122/123/smoke sin fallos NUEVOS respecto al baseline; tsc 0.

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El operador ejecuta paridad sin backup | Numeración fuerza backups primero; README + banner UI + encabezado de cada .sql lo repiten; el pareo es visible en la tabla y en el SqlViewer split. |
| Tipos con sintaxis no portable entre versiones del motor | El tipo viene LITERAL del snapshot del mismo motor (str(col.type) del dialecto real); no traducimos tipos. |
| Nombre de backup colisiona (2 corridas casi simultáneas) | `ts` con segundos + regenerar borra el bundle previo del run; colisión entre runs distintos es imposible (directorio por run_id). En la BD real, si la tabla `_BAK_...` ya existe, `SELECT * INTO`/`CREATE TABLE AS` fallan ANTES de tocar datos (fail-safe correcto, mismo comportamiento que Backup-TestTables.ps1). |
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

0. F0 preflight de dependencias (nueva, [ADICIÓN ARQUITECTO]).
1. F1 sqlnames + tests golden.
2. F2 `flatten_diff` + emitters + tests golden por dialecto.
3. F3 bundle + manifest + invariante (atómico, FIX C4) — gap documentado si falta `dbcompare_runs`.
4. F4 toposort (tests dedicados).
5. F5 API — gap documentado si falta `api/db_compare.py`.
6. F6 UI tab Scripts — `scriptsLogic.ts` siempre; `ScriptsPanel`/`SqlViewer` gap documentado si falta `DbComparePage`.
7. F7 no-regresión (baseline, FIX C6).

## 9. Definición de Hecho (DoD)

- [x] F0 preflight determinista y testeado; no bloquea F1/F2/F4. (`services/dbcompare_deps_preflight.py`, 5/5 tests)
- [x] `flatten_diff` con contrato exacto y tests golden (FIX C2): traduce SchemaDiff v1 anidado al modelo plano de F2 sin ambigüedad. (5/5 tests)
- [x] Emitters literales por dialecto con golden tests (KPI-2), incluyendo casos comentados (view sin definición, NOT NULL sin default) y `unique_removed` destructive=true (FIX C3). (29 sqlserver + 26 oracle tests)
- [x] Invariante de pareo 1:1 implementada como assert PRE-escritura + escritura atómica por `.tmp` + `os.replace` (KPI-1, FIX C4): imposible persistir bundle inválido O parcial. (`generate_parity_bundle_from_diff`, 8/8 tests incl. `test_invariante_invalida_no_deja_archivos_parciales`)
- [x] Orden: backups → paridad → destructivos; FK-safe demostrado (KPI-3); ciclos degradan con warning explícito. (`order_table_pieces`, 6/6 tests)
- [x] Bundle en disco + manifest v1 + zip descargable — `generate_parity_bundle_from_diff` (pura, 8/8 tests). **Wrapper real `generate_parity_bundle(run_id)` IMPLEMENTADO** (gap cerrado tras `git merge main`): resuelve el run vía `services.dbcompare_runs.get_run` y los snapshots vía `services.dbcompare_snapshot.load_snapshot`. Allowlist anti-traversal (F5) **IMPLEMENTADA** en `GET /runs/<id>/scripts/file` (`test_file_allowlist_y_traversal_400`).
- [x] Tab Scripts: `scriptsLogic.ts` (puro, 9/9 vitest) + `ScriptsPanel.tsx`/`SqlViewer.tsx` **IMPLEMENTADOS** y montados en `DbComparePage.tsx` (gap cerrado). Punto de entrada: input manual de `run_id` (el selector visual de corridas es del Plan 124, no implementado — no se inventó ese alcance). Sin tests RTL (gap estructural preexistente del repo, `@testing-library/react`/jsdom no instalados); gate real: `tsc --noEmit` (0 errores).
- [x] F5 — API HTTP real en el blueprint existente `db_compare` (`api/db_compare.py`, sin blueprint paralelo, FIX C5): `POST/GET /runs/<id>/scripts`, `GET /runs/<id>/scripts/file` (allowlist), `GET /runs/<id>/scripts.zip`. 7/7 tests end-to-end reales (sqlite seed → snapshot → diff → run → bundle → descarga).
- [x] Archivos de test backend de F0-F5 + 2 vitest verdes (comandos exactos); smoke sin fallos NUEVOS respecto a baseline (FIX C6, baseline=4 passed, post=4 passed); tsc 0. Suite combinada 125+122+123: 152/152 backend verdes; frontend completo 286/286 tests reales verdes (12 archivos `.test.tsx` con error de resolución de módulo son el gap RTL/jsdom preexistente, ninguno de dbcompare).
- [x] Cero endpoints que ejecuten SQL generado (grep de la review: ningún `execute`/`connect`/`create_engine` en `dbcompare_scripts.py`).
- [x] GAP restante, documentado explícitamente: el selector visual de corridas (listado/estado/drill-down) es responsabilidad del **Plan 124** (sigue PROPUESTO v1, sin criticar) — F6 de este plan expone la funcionalidad completa vía `run_id` manual en vez de inventar esa UI. Hallazgo fuera de alcance reportado al operador (no corregido acá): `services/dbcompare_diff.py::_diff_columns` (Plan 123, ya mergeado) parece invertir los kinds `column_added`/`column_removed` respecto de su propio docstring de dirección origen→destino; no bloquea esta implementación (los tests de Plan 125 usan fixtures propias) pero afecta la corrección semántica de columnas agregadas/quitadas en runs reales.
