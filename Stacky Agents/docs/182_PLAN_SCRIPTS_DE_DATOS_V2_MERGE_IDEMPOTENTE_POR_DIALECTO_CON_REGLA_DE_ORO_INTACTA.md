# Plan 182 — Scripts de datos v2: MERGE idempotente por dialecto, con REGLA DE ORO intacta

**Estado:** PROPUESTO (v1, 2026-07-18, autor Fable 5 vía `proponer-plan-stacky`).

**Serie:** Comparador de BD — capa 7 (calidad del artefacto de migración). Cierra el diferido técnico de 126 §6 ("MERGE statements en scripts de datos"), re-diferido por 176 §6. Relación con 157/176/178-181: §2bis (única colisión real: 176 F3, declarada con guía de composición).

---

## 1. Título, objetivo y KPIs

### 1.1 Objetivo (1 frase)

Elevar el artefacto más crítico del comparador — el SQL de paridad de datos que el operador revisa y ejecuta contra la BD del cliente — a sincronización IDEMPOTENTE y set-based: un `MERGE` por tabla (upsert por dialecto) para las filas faltantes, `UPDATE` con guard anti-no-op NULL-safe para las filas que difieren, y `DELETE` por PK exactamente como hoy — de modo que re-ejecutar un script (entero o a medias) sea SIEMPRE seguro y convergente, con el bundle byte-idéntico a main cuando la flag está OFF.

### 1.2 El diseño está FORZADO por el shape real del DataDiff (evidencia)

Dos hechos verificados del motor definen qué puede y qué no puede ser un MERGE:

1. `only_source` y `only_target` traen FILAS COMPLETAS (dict columna→valor para TODAS las `columns`, `services/dbcompare_data.py:177-178`) ⇒ el MERGE de inserción es posible y completo.
2. `changed` trae SOLO el `pk` y las `cells` de las columnas QUE DIFIEREN (`services/dbcompare_data.py:182-188`) ⇒ NO existe la fila fuente completa para armar el `USING` de un MERGE de update. Por eso los cambios de filas existentes se emiten como `UPDATE` por PK (como hoy) pero ganando guard de no-op NULL-safe — idempotencia observable sin inventar datos ni tocar el contrato DataDiff v1.

### 1.3 KPIs binarios

| KPI | Criterio binario | Cómo se verifica |
|---|---|---|
| KPI-1 | **BLOQUEANTE — OFF byte-idéntico:** con `STACKY_DB_COMPARE_DATA_MERGE_ENABLED=false` (y también llamando `emit_data_scripts`/`generate_parity_bundle_from_diff` sin los kwargs nuevos), las piezas y el bundle son BYTE-idénticos a main: mismos actions (`data_insert`/`data_update`/`data_delete`), mismos SQL, mismos archivos. | `tests/test_plan182_data_merge_bundle.py::test_off_byte_identico` |
| KPI-2 | Golden MERGE sqlserver: con merge ON, la pieza `data_merge` de una tabla con 2 filas `only_source` es EXACTAMENTE el `MERGE INTO ... USING (VALUES ...) ... WHEN MATCHED AND EXISTS (... EXCEPT ...) THEN UPDATE ... WHEN NOT MATCHED BY TARGET THEN INSERT ...;` de la regla §4.1. | `tests/test_plan182_data_merge_emitters.py::test_golden_merge_sqlserver` |
| KPI-3 | Golden MERGE oracle (`USING (SELECT ... FROM dual UNION ALL ...)`, update-guard con `DECODE`) y golden sqlite (`INSERT ... ON CONFLICT(pk) DO UPDATE SET ... WHERE ... IS NOT ...;`, UNA línea por fila) según §4.2/§4.3. | `tests/test_plan182_data_merge_emitters.py::test_golden_merge_oracle` / `::test_golden_merge_sqlite_una_linea` |
| KPI-4 | **Prueba reina — idempotencia E2E en sqlite:** ejecutar el script de datos DOS veces contra una BD sqlite real deja la tabla idéntica y sin error; y tras ALTERAR a mano una fila ya sincronizada, una TERCERA ejecución la repara (converge al valor del origen). | `tests/test_plan182_data_merge_e2e_sqlite.py::test_doble_ejecucion_y_reparacion` |
| KPI-5 | **Test negativo — la trampa del BY SOURCE:** ningún SQL emitido contiene `NOT MATCHED BY SOURCE` (en ningún dialecto); los borrados son EXCLUSIVAMENTE `DELETE` por PK de `only_target`, idénticos a main. | `tests/test_plan182_data_merge_emitters.py::test_jamas_by_source_delete` |
| KPI-6 | REGLA DE ORO intacta y EXTENDIDA: el assert del invariante de pareo (`dbcompare_scripts.py:896-902`) queda verde SIN ediciones de su lógica, y el action nuevo `data_merge` ENTRA en `_DATA_DML_KINDS` (`:673`) ⇒ una entry `data_merge` sin `backup_file` hace `raise` (probado). | `tests/test_plan182_data_merge_bundle.py::test_invariante_pareo_exige_backup_para_merge` |
| KPI-7 | UPDATE anti-no-op: con merge ON, re-ejecutar la pieza `data_update` sobre una fila YA igualada no re-escribe (guard NULL-safe); el golden contiene el guard por dialecto y el E2E sqlite lo demuestra con un contador de cambios (`total_changes`). | `tests/test_plan182_data_merge_emitters.py::test_update_guard_por_dialecto` + E2E |
| KPI-8 | Suite preexistente verde según perímetro (§9): `tests/test_plan126_dbcompare_data_scripts.py`, `tests/test_plan125_dbcompare_bundle.py`, `tests/test_plan125_dbcompare_scripts_api.py`, `tests/test_plan126_dbcompare_data_diff.py`, `tests/test_plan125_dbcompare_flatten.py` POR ARCHIVO, SIN editar ninguno. | comandos de F4 |

---

## 2. Por qué ahora / gap

1. **Es el último diferido técnico declarado de la serie**: 126 §6 difirió "MERGE statements"; 176 §6 lo re-difirió. 178-181 cubrieron radar, fidelidad, puente al repo y masking; el artefacto ejecutable — el SQL que efectivamente corre contra la BD del cliente — sigue siendo v1.
2. **Qué duele hoy (con evidencia)**: los scripts actuales ya son idempotentes FILA a FILA en la inserción (`IF NOT EXISTS`/`WHERE NOT EXISTS`, `dbcompare_scripts.py:600-614`), pero (a) el `UPDATE` NO tiene guard de diferencia (`:638`): re-ejecutarlo re-escribe valores idénticos — updates no-op que disparan triggers, tocan `last_modified` y meten locks innecesarios en tablas de parámetros productivas; (b) la inserción son N statements sueltos: un corte a mitad de archivo deja la tabla a medias y el operador debe releer qué entró; el upsert set-based por tabla converge solo al re-ejecutar; (c) si una fila insertada en la corrida anterior fue modificada después en el destino, el `INSERT` con guarda la SALTEA en silencio — el MERGE con `WHEN MATCHED AND <difiere>` la repara.
3. **Onboarding nulo**: mismo botón "Generar scripts"; el bundle sale mejor. Cero pasos nuevos, cero config nueva.
4. **Claim negativo (con comando)**: no existe hoy ningún emisor MERGE/upsert en el comparador — `grep -l "MERGE INTO|ON CONFLICT"` sobre `backend/**/dbcompare*.py` → **0 archivos**; el grep amplio de `MERGE|ON CONFLICT` sobre `backend/` solo devuelve usos ajenos al comparador (comentarios de config del plan 95, `client_profile.py` GET→merge→PUT de perfiles, memoria de agentes) — ninguno emite SQL.

---

## 2bis. Relación con 157 / 176 / 178 / 179 / 180 / 181

| Plan | Archivos que toca | Intersección con 182 |
|---|---|---|
| 157 / 178 / 179 / 180 / 181 | (sus listas ya declaradas en la serie: config UX; watch/baseline+app.py+runs kwarg; snapshot/diff; repo bridge; masking+get_run_route+DataParitySection) | NINGUNA — el 182 NO toca `api/db_compare.py`, ni frontend, ni snapshot/diff/data/runs |
| 176 (triage/gates) | `api/db_compare.py`, `DbComparePage.tsx`, `SummaryHero.tsx`, `endpoints.ts`, `DataParitySection.tsx`, y **F3: `excluded_keys` que filtra piezas/filas ANTES de emitir, con params nuevos a `generate_parity_bundle`/`_from_diff`** | `services/dbcompare_scripts.py` (mismo archivo, funciones `emit_data_scripts`/`generate_parity_bundle_from_diff`/`generate_parity_bundle`) |
| **182 (este)** | EDITADOS: `services/dbcompare_scripts.py` (emisor + wiring + 1 constante), `services/harness_flags.py`, `config.py`, `tests/test_harness_flags_requires.py`, runners sh/ps1. NUEVOS: 3 archivos de tests. **Nada más: cero frontend, cero API, cero módulos nuevos de runtime** | — |

**Guía de composición con 176 F3 (declarada honestamente):** ambos planes agregan kwargs ADITIVOS con default inocuo a las mismas firmas (`176: excluded_keys=None` filtra QUÉ se emite; `182: data_merge_mode=False` cambia CÓMO se emite lo que quedó). Son composables por diseño: filtrar → emitir. Orden de merge recomendado: el que llegue segundo resuelve un conflicto de firma trivial conservando AMBOS kwargs (orden alfabético) y ejecuta los tests de AMBOS planes por archivo como verificación post-merge (`test_plan176_*` + `test_plan182_*`). Ninguno de los dos toca la lógica interna del otro: `excluded_keys` opera antes del branch `merge_mode`.

---

## 3. Principios y guardarraíles

- **Doctrina de la serie**: Stacky GENERA scripts; el operador los revisa y ejecuta. Este plan NO ejecuta nada (la prueba reina E2E ejecuta SQL solo DENTRO de un test, contra sqlite del carril `test-*`).
- **Contratos congelados intactos**: Manifest v1 — el FORMATO no cambia (mismas keys de entry `:881-894`; `data_merge` es un VALOR nuevo del campo `action`, no un cambio de formato; README `:696-702` y zip `:932-939` son agnósticos al action). Reglas de `dbcompare_sqlvalues` — intactas y REUSADAS: todo literal sale de `sql_literal_from_normalized(normalized, col_type, dialect)` (`dbcompare_sqlvalues.py:119-139`), incluido su `SqlLiteralError` para binarios truncados (mismo manejo que hoy: la fila cae a comentario `-- BYTES TRUNCADOS`, `dbcompare_scripts.py:557,595-597`). DataDiff v1 — intacto (el diseño se adapta a su shape, §1.2). REGLA DE ORO — intacta y extendida (KPI-6).
- **HITL**: sin cambios — el bundle sigue siendo un artefacto para revisión humana; el header sigue diciendo "NO EJECUTADO por Stacky" (`render_header`, `dbcompare_scripts.py:162-170`).
- **Mono-operador sin auth real**: nada de RBAC.
- **3 runtimes**: feature de motor backend puro (sin LLM, sin UI): idéntica en Codex CLI, Claude Code CLI y GitHub Copilot Pro.
- **No degradar**: OFF ⇒ byte-idéntico (KPI-1). ON ⇒ mismo costo de generación (recorre las mismas filas una vez).
- **Flag**: `STACKY_DB_COMPARE_DATA_MERGE_ENABLED`, bool, **default ON** — mejora invisible del ARTEFACTO GENERADO: nada se ejecuta solo, el operador sigue revisando y ejecutando; no conecta, no publica, no escribe fuera del bundle ⇒ NINGUNA de las 4 excepciones duras aplica. Registro completo: `_CURATED_DEFAULTS_ON` (`harness_flags.py:310`), `_CATEGORY_KEYS["comparador_bd"]` (`:320-324`), `requires="STACKY_DB_COMPARE_ENABLED"` (plano, profundidad 1 — jamás encadenar a la hija `STACKY_DB_COMPARE_DATA_DIFF_ENABLED`), arista en `_REQUIRES_MAP_FROZEN` (`tests/test_harness_flags_requires.py:120,183-185`), default efectivo en `config.py` (idioma de `:119-133`), `harness_defaults.env` regenerado por `scripts/export_harness_defaults.py`.
- **Dónde se decide el modo (clave de compatibilidad)**: la flag se lee EXCLUSIVAMENTE en el wrapper `generate_parity_bundle` (`dbcompare_scripts.py:952-981`, el único camino que usa la API real `:274`); las funciones `emit_data_scripts` y `generate_parity_bundle_from_diff` ganan kwargs con default `False` y NO leen config. Así los tests preexistentes — que llaman ambas funciones DIRECTO sin kwargs (verificado: `test_plan126_dbcompare_data_scripts.py:44,62,74,86,94,117` para el emisor y `:167-169,182-184,195-196` para el bundle) — quedan byte-idénticos POR FIRMA, sin editarlos y sin pins de flag (lección del juicio 179).
- **Tests por archivo** con `./venv/Scripts/python.exe` (fallback `./.venv/Scripts/python.exe`) desde `Stacky Agents/backend`; los 3 `tests/test_plan182_*.py` registrados en `HARNESS_TEST_FILES` (`run_harness_tests.sh:20` + espejo `.ps1`).

### 3.1 La trampa del BY SOURCE DELETE — resolución explícita

`WHEN NOT MATCHED BY SOURCE THEN DELETE` NO se emite JAMÁS, en ningún dialecto, ni acotado. Razón dura con evidencia: el data-diff está DOBLEMENTE acotado — por cap de filas con detección de truncamiento (`max_rows + 1`, `dbcompare_data.py:54`, truncado en `:152-154`) y por selección manual de ≤20 tablas (`:25`) — de modo que "no está en el USING" NUNCA implica "no debe existir en el destino": un BY SOURCE DELETE (aun con `AND T.pk IN (...)`) es innecesario si se enumeran los PK (eso YA es el DELETE explícito) y catastrófico si no. Los borrados siguen siendo EXCLUSIVAMENTE los `DELETE` por PK de `only_target` (filas que el diff SÍ comparó y encontró sobrantes), idénticos a main (`dbcompare_scripts.py:644-651`), destructivos, en `09_destructivo/` y con backup pareado. KPI-5 lo prueba en negativo.

---

## 4. Reglas de emisión por dialecto (merge ON)

Notación: `q` = tabla calificada (`sqlnames.qualified`), `pk_cols`, `columns` y `column_types` del DataDiff (`dbcompare_data.py:197-211`); TODO literal via `sql_literal_from_normalized(row[col], column_types.get(col, ""), dialect)`; filas de `only_source` ordenadas por `_sort_key_row` (determinismo, igual que hoy `:586`); columnas no-PK = `[c for c in columns if c not in pk_cols]`. Si una fila lanza `SqlLiteralError` ⇒ línea `-- BYTES TRUNCADOS: completar a mano -- fila PK=...` (idéntico a hoy) y la fila queda FUERA del VALUES/UNION.

### 4.1 sqlserver — pieza `data_merge` (reemplaza a `data_insert` con merge ON)

```sql
MERGE INTO [dbo].[PARAMS] AS T
USING (VALUES
  (1, 'A', 10),
  (3, 'C', 30)
) AS S ([ID], [NOMBRE], [VALOR])
ON (T.[ID] = S.[ID])
WHEN MATCHED AND EXISTS (SELECT S.[NOMBRE], S.[VALOR] EXCEPT SELECT T.[NOMBRE], T.[VALOR])
  THEN UPDATE SET T.[NOMBRE] = S.[NOMBRE], T.[VALOR] = S.[VALOR]
WHEN NOT MATCHED BY TARGET
  THEN INSERT ([ID], [NOMBRE], [VALOR]) VALUES (S.[ID], S.[NOMBRE], S.[VALOR]);
```

- `ON` = AND de igualdad por cada PK col. Guard del MATCHED = `EXISTS (SELECT S.<no-pk> EXCEPT SELECT T.<no-pk>)` — idiom NULL-safe de T-SQL (trata NULL=NULL como iguales). Caso borde: tabla SOLO-PK (sin columnas no-PK) ⇒ se omite la cláusula WHEN MATCHED entera (no hay nada que actualizar).
- Semántica: primera ejecución inserta las filas faltantes; re-ejecución no hace nada; si una fila sincronizada fue alterada en el destino después, la repara. El WHEN MATCHED solo puede tocar filas cuyos PK están LITERALMENTE enumerados en el VALUES (las `only_source` del diff) — alcance acotado por construcción.

### 4.2 oracle — pieza `data_merge`

```sql
MERGE INTO "DBO"."PARAMS" T
USING (
  SELECT 1 AS "ID", 'A' AS "NOMBRE", 10 AS "VALOR" FROM dual
  UNION ALL
  SELECT 3, 'C', 30 FROM dual
) S
ON (T."ID" = S."ID")
WHEN MATCHED THEN UPDATE SET T."NOMBRE" = S."NOMBRE", T."VALOR" = S."VALOR"
  WHERE DECODE(T."NOMBRE", S."NOMBRE", 1, 0) = 0 OR DECODE(T."VALOR", S."VALOR", 1, 0) = 0
WHEN NOT MATCHED THEN INSERT ("ID", "NOMBRE", "VALOR") VALUES (S."ID", S."NOMBRE", S."VALOR");
```

- Oracle no tiene BY SOURCE (irrelevante: no lo usamos en ningún dialecto). Guard NULL-safe = `DECODE(T.c, S.c, 1, 0) = 0` por columna no-PK, unidos con OR (DECODE considera NULL==NULL). Tabla solo-PK ⇒ sin cláusula WHEN MATCHED.

### 4.3 sqlite (carril `test-*`) — pieza `data_merge`, UNA LÍNEA POR FILA

```sql
INSERT INTO "main"."PARAMS" ("ID", "NOMBRE", "VALOR") VALUES (1, 'A', 10) ON CONFLICT("ID") DO UPDATE SET "NOMBRE" = excluded."NOMBRE", "VALOR" = excluded."VALOR" WHERE "PARAMS"."NOMBRE" IS NOT excluded."NOMBRE" OR "PARAMS"."VALOR" IS NOT excluded."VALOR";
```

- Cada fila es UN statement COMPLETO en UNA sola línea física — regla de formato OBLIGATORIA para que el patrón de ejecución por línea del E2E preexistente (`test_plan126_dbcompare_data_scripts.py:122-125`: `splitlines()` + skip de `--`) funcione igual con la pieza nueva. Guard NULL-safe = `IS NOT` (null-safe en SQLite). `ON CONFLICT ... DO UPDATE` requiere SQLite ≥ 3.24 (2018) — el sqlite3 embebido de Python 3.13 lo supera con holgura. Tabla solo-PK ⇒ `ON CONFLICT("ID") DO NOTHING`.

### 4.4 Pieza `data_update` v2 (filas `changed`) — mismo action, guard anti-no-op

Con merge ON, cada `UPDATE` gana el guard NULL-safe del dialecto ADEMÁS del WHERE por PK (hoy: `:622-642` sin guard):

- sqlserver: `UPDATE [dbo].[PARAMS] SET [NOMBRE] = 'B-mod' WHERE [ID] = 2 AND EXISTS (SELECT 'B-mod' EXCEPT SELECT [NOMBRE]);`
- oracle: `... WHERE "ID" = 2 AND DECODE("NOMBRE", 'B-mod', 1, 0) = 0;`
- sqlite: `... WHERE "ID" = 2 AND "NOMBRE" IS NOT 'B-mod';`

(el guard usa los MISMOS literales del SET — cero datos nuevos; multi-columna: los pares columna/literal de las `cells` de esa fila). Con merge OFF: byte-idéntico a hoy.

### 4.5 Pieza `data_delete` — INTACTA

Byte-idéntica a main con ON y con OFF (`:644-651`). Es la resolución de la trampa §3.1.

### 4.6 Advertencia de truncamiento

Si `data_diff["truncated"]` es `true` (`dbcompare_data.py:209`), con merge ON TODAS las piezas `data_*` de esa tabla anteponen la línea:
`-- ATENCION: el diff de datos fue TRUNCADO por el cap de filas; este script cubre SOLO las filas comparadas.`
(con OFF no se agrega nada — byte-idéntico). No se toca `render_header` (`:162-170`): la línea va DENTRO del `sql` de la pieza.

### 4.7 Metadata de las piezas

- `data_merge`: `action="data_merge"`, `object_type="table"`, `destructive=False`, `modifies_table=True` ⇒ archivo `03_datos/{seq:03d}_data_merge_{schema}_{tabla}.sql` vía `sqlnames.script_filename` (`dbcompare_sqlnames.py:53`, sin cambios — kind es un string libre). El WHEN MATCHED puede modificar filas re-divergidas: por eso `data_merge` ENTRA en `_DATA_DML_KINDS` (`dbcompare_scripts.py:673`) y el invariante `:896-902` EXIGE su `backup_file` (que el caller ya asigna por tabla ANTES de las piezas, `:859-866`) — la REGLA DE ORO cubre el riesgo.
- `data_update`/`data_delete`: metadata idéntica a hoy.

---

## 5. Fases

Orden estricto: F0 → F1 → F2 → F3 → F4. TDD en cada una.

---

### F0 — Flag, config y arista

**Objetivo:** registrar `STACKY_DB_COMPARE_DATA_MERGE_ENABLED` (default ON) sin comportamiento nuevo.

**Archivos a editar:** los 4 de registro con el idioma exacto de la serie (§3): `harness_flags.py` (FlagSpec bool `default=True` + `_CURATED_DEFAULTS_ON` + `_CATEGORY_KEYS["comparador_bd"]`), `config.py` (`"true"` default), `test_harness_flags_requires.py` (arista a `STACKY_DB_COMPARE_ENABLED`), runners sh+ps1 (los 3 tests nuevos). Regenerar `harness_defaults.env` por script.

**Tests PRIMERO — `tests/test_plan182_data_merge_bundle.py` (bloque flags):** `test_flag_registrada_bool_on_requires_master`, `test_flag_en_categoria`, `test_config_default_on`.
**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan182_data_merge_bundle.py -q` (+ `tests/test_harness_flags.py`, `tests/test_harness_flags_requires.py`).
**Criterio (binario):** 3 nuevos + 2 preexistentes verdes.
**Flag:** la propia (sin efecto). **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F1 — Emisor v2: `data_merge` + update-guard (funciones puras, goldens)

**Objetivo:** `emit_data_scripts` gana el modo merge detrás de un kwarg con default `False`, con emisión determinista por dialecto según §4.

**Archivo a editar:** `services/dbcompare_scripts.py`:

1. Firma: `def emit_data_scripts(data_diff: dict, dialect: str, ts: str, target_alias: str, *, merge_mode: bool = False) -> list["ScriptPiece"]:` (`:568`). Con `merge_mode=False` el cuerpo actual corre SIN NINGÚN CAMBIO (byte-idéntico — KPI-1 y perímetro de tests §9).
2. Con `merge_mode=True`:
   - `only_source` ⇒ UNA pieza `data_merge` según §4.1/4.2/4.3 (en vez de la pieza `data_insert`). Filas ordenadas por `_sort_key_row` (`:577-578`); filas con `SqlLiteralError` fuera del VALUES y anotadas como comentario (§4).
   - `changed` ⇒ pieza `data_update` con guard §4.4 (mismo action).
   - `only_target` ⇒ pieza `data_delete` IDÉNTICA (mismo código, sin branch).
   - `data_diff.get("truncated")` ⇒ prefijo §4.6 en las piezas emitidas.
   - Dialecto desconocido ⇒ `raise DbCompareRunError` (idioma de `:615-616`).
3. Helpers nuevos privados y puros: `_merge_statement_sqlserver(...)`, `_merge_statement_oracle(...)`, `_merge_lines_sqlite(...)`, `_update_guard(dialect, cells, column_types) -> str` — cada uno recibe SOLO datos ya extraídos del DataDiff (sin config, sin disco).
4. Constante: `_DATA_DML_KINDS = {"data_insert", "data_update", "data_delete", "data_merge"}` (`:673` — edición de 1 línea; el invariante `:896-902` NO se toca y pasa a exigir backup para `data_merge` automáticamente vía `_REQUIRES_RESGUARDO_KINDS` `:674`).

**Tests PRIMERO — `tests/test_plan182_data_merge_emitters.py`** (fixtures dict a mano, mismo `_data_diff()` de estilo que el test del 126):
- `test_golden_merge_sqlserver` (KPI-2): SQL exacto §4.1 (assert de igualdad de string completo).
- `test_golden_merge_oracle` (KPI-3): SQL exacto §4.2.
- `test_golden_merge_sqlite_una_linea` (KPI-3): SQL exacto §4.3 Y `"\n" not in <cada statement>` (regla de 1 línea).
- `test_update_guard_por_dialecto` (KPI-7): los 3 goldens de §4.4.
- `test_jamas_by_source_delete` (KPI-5): para los 3 dialectos, `"NOT MATCHED BY SOURCE" not in` ningún `sql` emitido; y la pieza `data_delete` es EXACTAMENTE la de main (comparar contra `emit_data_scripts(..., merge_mode=False)`).
- `test_default_false_byte_identico` (KPI-1, nivel emisor): `emit_data_scripts(diff, d, TS, "TEST") == emit_data_scripts(diff, d, TS, "TEST", merge_mode=False)` y ambos == resultado actual (los goldens v1 del test 126 siguen siendo válidos — no se re-assertan acá, se corren en F4).
- `test_tabla_solo_pk_sin_when_matched`: sqlserver/oracle omiten WHEN MATCHED; sqlite emite `DO NOTHING`.
- `test_bytes_truncados_fila_fuera_del_values`: fila con binario truncado ⇒ comentario y VALUES sin esa fila.
- `test_truncated_prefija_advertencia`: `truncated: true` ⇒ primera línea §4.6 en `data_merge`/`data_update`/`data_delete`; `false` ⇒ ausente.

**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan182_data_merge_emitters.py -q`
**Criterio (binario):** 9 tests verdes; `git diff` de `dbcompare_scripts.py` no toca `_guard_conds`, `render_header`, `emit_parity`, `emit_resguardo` ni el assert `:896-902`.
**Flag:** sin lectura de config en el emisor (kwarg puro). **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F2 — Wiring del bundle: kwargs aditivos + resolución de flag en el wrapper

**Objetivo:** el camino real de la API genera el bundle v2 con la flag ON y byte-idéntico con OFF.

**Archivo a editar:** `services/dbcompare_scripts.py`:

1. `generate_parity_bundle_from_diff(..., data_diff: dict | None = None, data_merge_mode: bool = False)` — kwarg aditivo; el único cambio interno es pasar `merge_mode=data_merge_mode` en la llamada a `emit_data_scripts` (`:853`). Nada más cambia (backup pareado `:859-866`, ruteo 03_datos/09_destructivo `:868-875`, entries `:881-894`, invariante `:896-902`, manifest `:904-918` intactos).
2. `generate_parity_bundle(run_id)` (`:952-981`) — el ÚNICO lector de la flag:
   ```python
   import config as _config
   merge_on = bool(getattr(_config.config, "STACKY_DB_COMPARE_DATA_MERGE_ENABLED", False))
   return generate_parity_bundle_from_diff(
       run["diff"], run_id, source_snapshot, target_snapshot, run["engine"],
       data_diff=run.get("data_diff"), data_merge_mode=merge_on,
   )
   ```
   (el dialecto sigue siendo `run["engine"]`, `:979` — mismo motor en ambos lados, garantizado por `create_run`, `dbcompare_runs.py:140-143`).

**Tests PRIMERO — completar `tests/test_plan182_data_merge_bundle.py`** (fixture `_isolated_data_dir` idéntico al del 126 `:144-147`):
- `test_off_byte_identico` (KPI-1, BLOQUEANTE): mismo input que `test_kpi3_backup_por_tabla_con_dml` del 126; generar bundle vía `generate_parity_bundle_from_diff(...)` SIN kwarg y CON `data_merge_mode=False` ⇒ manifests y contenido de TODOS los archivos byte-idénticos entre sí (y actions == {data_insert, data_update, data_delete}).
- `test_on_emite_data_merge_en_03_datos`: con `data_merge_mode=True` ⇒ entry `data_merge` con `file.startswith("03_datos/")`, `destructive is False`, `backup_file is not None`; NO existe entry `data_insert`; `data_update` y `data_delete` presentes.
- `test_invariante_pareo_exige_backup_para_merge` (KPI-6): construir entries con un `data_merge` sin backup (monkeypatch de `_render_data_backup` para simular ausencia, o invocar la validación con una entry fabricada) ⇒ `DbCompareRunError` con el mensaje del invariante.
- `test_wrapper_lee_flag`: monkeypatch `config.config.STACKY_DB_COMPARE_DATA_MERGE_ENABLED` True/False + run sembrado con data_diff ⇒ el manifest trae `data_merge` sii ON (esto prueba el punto ÚNICO de lectura de flag).
- `test_visor_sirve_data_merge_sin_cambios` (perímetro): con ON, `GET /runs/<id>/scripts/file?path=03_datos/..._data_merge_...sql` responde 200 — la allowlist deriva del manifest (`api/db_compare.py:294-302`) y NO se editó.

**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan182_data_merge_bundle.py -q`
**Criterio (binario):** los 5 + 3 de F0 verdes; `api/db_compare.py` SIN diff.
**Flag:** resuelta SOLO en el wrapper. **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F3 — Prueba reina: idempotencia E2E en sqlite

**Objetivo:** demostrar con ejecución REAL que el script converge y es re-ejecutable.

**Test PRIMERO — `tests/test_plan182_data_merge_e2e_sqlite.py`** (patrón del E2E preexistente `test_plan126_dbcompare_data_scripts.py:117-136`: engine sqlite en memoria/archivo tmp, ejecutar el `sql` línea por línea salteando `--`):
- `test_doble_ejecucion_y_reparacion` (KPI-4):
  1. Crear tabla `PARAMS(ID INTEGER PRIMARY KEY, NOMBRE TEXT, VALOR INTEGER)` en sqlite y sembrar el DESTINO con 1 fila preexistente.
  2. DataDiff fixture: 2 filas `only_source` (completas), 1 `changed` (cells de NOMBRE), 0 `only_target`.
  3. `emit_data_scripts(diff, "sqlite", TS, "TEST", merge_mode=True)` ⇒ ejecutar `data_merge` + `data_update` (línea por línea).
  4. Asserts tras 1ª ejecución: las 2 filas insertadas existen con los valores del origen; la fila changed tiene el valor target del origen.
  5. 2ª ejecución completa: sin excepción; snapshot de la tabla (SELECT * ordenado) IDÉNTICO al de la 1ª; y `conn.total_changes` NO crece durante la 2ª pasada (anti-no-op observable, KPI-7).
  6. ALTERAR a mano una de las filas insertadas (`UPDATE PARAMS SET NOMBRE='hackeado' WHERE ID=3`); 3ª ejecución ⇒ la fila vuelve al valor del origen (reparación por WHEN MATCHED/DO UPDATE).
- `test_null_safety_e2e`: fila `only_source` con `NOMBRE = NULL` ⇒ doble ejecución sin error y sin cambios en la 2ª (el `IS NOT` trata NULL==NULL).
- `test_delete_intacto_e2e`: DataDiff con 1 `only_target` ⇒ la pieza `data_delete` ejecutada 2 veces deja 0 filas y no falla.

**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan182_data_merge_e2e_sqlite.py -q`
**Criterio (binario):** 3 tests verdes.
**Flag:** N/A (el test pasa `merge_mode=True` explícito). **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F4 — Cierre: perímetro, no-regresión y DoD

**Acciones:**
1. Registro de los 3 tests en ambos runners (grep de verificación).
2. Correr POR ARCHIVO, SIN editar ninguno: `tests/test_plan126_dbcompare_data_scripts.py`, `tests/test_plan125_dbcompare_bundle.py`, `tests/test_plan125_dbcompare_scripts_api.py`, `tests/test_plan126_dbcompare_data_diff.py`, `tests/test_plan125_dbcompare_flatten.py`, `tests/test_harness_flags.py`, `tests/test_harness_flags_requires.py` + los 3 nuevos.
3. `"./venv/Scripts/python.exe" -m compileall services/dbcompare_scripts.py` limpio.
4. Smoke manual documentado en el PR (BD real sqlserver): correr un compare con data-diff, generar scripts con la flag ON ⇒ `03_datos/` contiene `NNN_data_merge_...sql` con el MERGE §4.1; el visor lo muestra; ejecutar el bundle en el ambiente de prueba DOS veces ⇒ segunda pasada reporta 0 filas afectadas; apagar la flag por UI y regenerar ⇒ layout v1 (`data_insert`).

**Criterio (binario):** puntos 1-3 verdes; punto 4 documentado.
**Trabajo del operador:** ninguno.

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Impacto | Mitigación |
|---|---|---|---|
| R1 | La trampa del BY SOURCE DELETE (borrar filas fuera del alcance comparado) | Pérdida de datos del cliente | RESUELTA POR DISEÑO (§3.1): jamás se emite BY SOURCE; borrados = DELETE por PK de `only_target`, idénticos a main; KPI-5 en negativo |
| R2 | NULL-safety del guard (falso "difiere" o falso "igual" con NULL) | Updates no-op o filas sin reparar | Idioms NULL-safe POR DIALECTO con golden cada uno (§4: EXISTS/EXCEPT, DECODE, IS NOT) + E2E `test_null_safety_e2e` |
| R3 | Tablas sin PK | MERGE sin ON posible | NO APLICA por el motor: `diff_table_data` rechaza tablas sin PK ANTES de diffear (`dbcompare_data.py:117-118`) — regla heredada, ninguna pieza de datos existe para ellas |
| R4 | Diff truncado por cap ⇒ sincronización parcial percibida como total | Operador cree que la tabla quedó igualada | Advertencia §4.6 en el propio script cuando `truncated` es true (dato ya presente en el DataDiff, `dbcompare_data.py:209`) — visible en la revisión HITL |
| R5 | Tests preexistentes fijan el layout/SQL v1 | Suite roja el día 1 | RESUELTO POR FIRMA (lección 179/§3): defaults `False` en ambas funciones; los tests llaman sin kwargs (evidencia `:44-117` y `:167-196`) ⇒ byte-idéntico sin editarlos; KPI-1 lo sella |
| R6 | Colisión con 176 F3 en `dbcompare_scripts.py` | Conflicto de firma | Kwargs aditivos con default inocuo en ambos planes; guía de composición §2bis (conservar ambos, correr tests de ambos post-merge) |
| R7 | El WHEN MATCHED del `data_merge` modifica filas existentes (re-divergidas) siendo `destructive=False` | Cambio de datos sin ir a 09_destructivo | Alcance acotado por construcción (solo PK enumerados en el VALUES) + backup pareado OBLIGATORIO: `data_merge` entra a `_DATA_DML_KINDS` y el invariante `:896-902` lo exige (KPI-6); el README del bundle ya ordena backups primero (`:687-690`) |
| R8 | `ON CONFLICT` no soportado por sqlite viejo | E2E frágil | Requiere SQLite ≥ 3.24 (2018); el sqlite3 embebido de Python 3.13 (carril de tests del repo) lo supera; anotado en §4.3 |
| R9 | Sesión paralela ocupa el número 182 | Colisión de numeración (precedente 171) | Número recalculado listando `docs/` inmediatamente antes del Write; renumerar antes de commitear si aparece otro 182 |
| R10 | Un MERGE gigante (miles de filas en VALUES) difícil de revisar | Revisión HITL pesada | El volumen es EL MISMO que hoy reparte en N INSERTs (cap `STACKY_DB_COMPARE_DATA_MAX_ROWS`, `config.py:131-133`); el MERGE lo hace más legible (una tabla = un statement); sin cap nuevo |

---

## 7. Fuera de scope (diferidos explícitos)

- **Ejecutar scripts**: NUNCA — doctrina de la serie; la ejecución E2E existe SOLO dentro del test sqlite.
- **MERGE de esquema (DDL)**: fuera — esto es exclusivamente DML de datos (las piezas de `emit_parity` DDL no se tocan).
- **Retoques al triage (176)**: nada de este plan depende ni modifica el triage; la composición está declarada en §2bis.
- **Fila fuente completa en `changed`** (habilitaría MERGE también para updates): requeriría campo aditivo en el DataDiff y engordaría el run persistido; diferido con la evidencia de §1.2 — si algún día se hace, es una extensión aditiva de `dbcompare_data.py` con su propio plan.
- **Transacciones explícitas / SET XACT_ABORT en el script**: diferido — el bundle actual no las emite en DML v1 y agregarlas es una decisión de formato del artefacto que merece discusión propia con el operador.
- **Batching de VALUES por tamaño (p.ej. 1000 filas por MERGE)**: diferido; el cap global de filas ya acota (R10).

---

## 8. Glosario, orden de implementación y DoD global

### Glosario

- **`data_merge`**: pieza nueva (un statement upsert set-based por tabla) que reemplaza a `data_insert` cuando el modo merge está activo.
- **Modo merge (`merge_mode`/`data_merge_mode`)**: kwargs aditivos con default `False`; la flag los activa SOLO en el wrapper real.
- **Guard anti-no-op**: condición NULL-safe que evita re-escribir valores idénticos (idiom por dialecto, §4).
- **Trampa BY SOURCE**: emitir `WHEN NOT MATCHED BY SOURCE THEN DELETE` sobre un diff acotado — prohibida (§3.1).
- **REGLA DE ORO**: todo DML de datos exige backup pareado 1:1 por tabla (invariante `dbcompare_scripts.py:896-902`).
- **Prueba reina**: el E2E sqlite de doble ejecución + reparación (KPI-4).

### Orden de implementación (estricto)

F0 (flag) → F1 (emisor puro + goldens) → F2 (wiring bundle + flag en wrapper) → F3 (E2E) → F4 (cierre). Nada permutable.

### Definition of Done global

1. Los 8 KPIs de §1.3 verificados (KPI-1 es BLOQUEANTE).
2. Los 3 `tests/test_plan182_*.py` verdes POR ARCHIVO y registrados en ambos runners.
3. Los 7 archivos preexistentes de F4 punto 2 verdes SIN ediciones.
4. `harness_defaults.env` regenerado por script (flag nueva en `true`).
5. `git diff --stat` solo lista: `services/dbcompare_scripts.py`, `services/harness_flags.py`, `config.py`, `tests/test_harness_flags_requires.py`, los 2 runners y los 3 tests nuevos — en particular NO lista `api/db_compare.py`, `dbcompare_data.py`, `dbcompare_sqlvalues.py`, `dbcompare_sqlnames.py` ni NADA de frontend.
6. Smoke manual de F4 documentado en el PR.

---

## 9. PERÍMETRO enumerado (todas las superficies por las que scripts de datos llegan a un consumidor, con su sello)

| Superficie | Evidencia | Impacto del 182 | Sello |
|---|---|---|---|
| Emisor `emit_data_scripts` | `dbcompare_scripts.py:568-653` | branch `merge_mode` (default False) | goldens F1 + KPI-1 |
| Caller del bundle (`generate_parity_bundle_from_diff` → piezas → archivos) | `:850-894` (backup `:859-866`, ruteo 03_datos/09_destructivo `:868-875`, entries `:881-894`) | pasa `merge_mode`; ruteo intacto (`data_merge` no-destructivo → `03_datos/`) | tests F2 |
| Invariante REGLA DE ORO | `:896-902` + `_DATA_DML_KINDS :673` / `_REQUIRES_RESGUARDO_KINDS :674` | +1 kind en el set; lógica del assert INTACTA | KPI-6 |
| Wrapper real (API) | `:952-981` (dialecto = `run["engine"]` `:979`; único caller de la API: `api/db_compare.py:274`) | ÚNICO punto que lee la flag | `test_wrapper_lee_flag` |
| Manifest v1 | `:904-918` | formato intacto; `action` gana un valor | `test_on_emite_data_merge_en_03_datos` |
| README del bundle | `:681-702` (imprime `e['action']` tal cual) | sin cambios — agnóstico | no aplica (sin lógica por action) |
| Zip | `bundle_zip_bytes :932-939` (rglob, agnóstico a nombres) | sin cambios | no aplica |
| Visor de archivos + allowlist | `api/db_compare.py:294-302` (deriva 100% del manifest) + `read_bundle_file :942-949` | sin cambios — nombres nuevos entran solos por el manifest | `test_visor_sirve_data_merge_sin_cambios` |
| Nombres de archivo | `sqlnames.script_filename` (`dbcompare_sqlnames.py:53`, kind = string libre) | sin cambios | goldens F2 (path esperado) |
| Literales SQL | `sql_literal_from_normalized` (`dbcompare_sqlvalues.py:119-139`) + `SqlLiteralError` | REUSADO sin cambios | `test_bytes_truncados_fila_fuera_del_values` |
| Tests preexistentes que fijan SQL/layout v1 | `test_plan126_dbcompare_data_scripts.py` — goldens v1 del emisor (`:44-118`), E2E insert (`:117-136`), bundle directo (`:165-200`); `test_plan125_dbcompare_bundle.py` — layout DDL `09_destructivo` (`:77-89`, ajeno a datos) | VEREDICTO: fijan v1 llamando las funciones SIN kwargs ⇒ intactos por defaults `False`; el del 125 ni toca datos | KPI-8 (corridos en F4) |
| Export markdown del run | `dbcompare_runs.py:265-321` (no imprime scripts ni filas) | sin cambios | no aplica |
| Masking 181 (en papel) | su doctrina declara "scripts intactos" y no toca el bundle | sin interacción | no aplica |
| Triage 176 F3 (en papel) | filtra ANTES de emitir | composable (§2bis) | guía de merge |

---

**Changelog interno:** v1 (2026-07-18) — propuesta inicial.
Auto-consistencia KPI↔spec verificada: KPI-1↔los defaults `False` viven en las FIRMAS (`emit_data_scripts:merge_mode`, `from_diff:data_merge_mode`) y la flag se lee SOLO en el wrapper — el test compara además la llamada sin-kwarg vs kwarg False vs main; KPI-4↔el E2E usa el patrón de ejecución por línea del test preexistente (`:122-125`) y la regla §4.3 obliga 1 statement por línea en sqlite, así el script emitido ES ejecutable por ese patrón; KPI-5↔§3.1 prohíbe BY SOURCE en la spec de los 3 dialectos y `data_delete` queda byte-idéntica (mismo código sin branch); KPI-6↔`data_merge` entra a `_DATA_DML_KINDS` (:673) y el assert `:896-902` NO se edita — el backup existe siempre porque el caller lo asigna por tabla ANTES de las piezas (`:859-866`); KPI-7↔el guard §4.4 usa los MISMOS literales del SET (cero datos nuevos, consistente con §1.2 "cells solo trae columnas que difieren") y el E2E lo observa con `total_changes`; KPI-8↔perímetro §9 con veredicto por archivo (los goldens v1 del 126 llaman sin kwargs; el 125 no asserta datos); R7↔`destructive=False` es consistente con KPI-6 porque el invariante exige el backup por pertenencia al set, NO por el flag destructive (evidencia del propio diseño del 126 en el comentario `:663-672`).
