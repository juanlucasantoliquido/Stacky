# Plan 123 — Comparador de BD entre ambientes (serie 122–126, parte 2/5): motor de diff, severidades y corridas comparativas

**Estado:** PROPUESTO (v1, 2026-07-12)
**Serie:** 122 (núcleo) → **123 (motor de diff)** → 124 (UI inmersiva) → 125 (scripts de paridad + backups) → 126 (paridad de datos)
**Dependencias:** Plan 122 IMPLEMENTADO (registro `services/dbcompare_registry.py`, engine `services/dbcompare_engine.py`, snapshot v1 `services/dbcompare_snapshot.py`, blueprint `api/db_compare.py`). Este plan NO arranca si el 122 no está verde.
**Ortogonal a:** Planes 116/119/120/121.

> Este documento está redactado para que un MODELO MENOR (Haiku, Codex CLI o GitHub
> Copilot Pro) lo implemente SIN inferir nada. Toda afirmación sobre código existente
> cita `archivo:línea` verificada el 2026-07-12 (rama `main`); los símbolos del Plan 122
> se citan por su contrato congelado en `docs/122_PLAN_*.md` §4. Prohibido desviarse de
> los nombres exactos.

---

## 1. Objetivo + KPI

Con los snapshots v1 del Plan 122 como insumo, este plan construye el **cerebro** del
comparador: una función pura y determinista que dado (snapshot origen, snapshot destino)
produce un **SchemaDiff v1** — lista tipada de diferencias con severidad (`info | warn |
danger`), resumen con contadores y **parity score** — más las **corridas comparativas**
persistidas (threaded, con lock por par y marcador stale) y un **export Markdown**
determinista del resumen detallado. Sin UI nueva (la sección inmersiva es el Plan 124);
todo queda consumible por API.

**Semántica de dirección (congelada para toda la serie):** el **origen es la referencia**
(source of truth) y el **destino es el ambiente a alinear**. `added` = existe en origen y
falta en destino (la paridad lo CREARÁ en destino); `removed` = existe en destino y no en
origen (la paridad lo DROPEARÁ del destino → destructivo).

**KPIs (binarios):**

- **KPI-1 (determinismo):** `diff_snapshots(a, b)` llamado dos veces produce JSON
  byte-idéntico (`json.dumps(..., sort_keys=True)` iguales) — test F1.
- **KPI-2 (severidad correcta):** un fixture con una tabla dropeada, una columna con tipo
  cambiado y un índice nuevo produce EXACTAMENTE `danger=2, warn=1` en
  `summary.by_severity` — test F1.
- **KPI-3 (corrida e2e):** `POST /api/db-compare/compare` con dos ambientes sqlite
  sembrados → 202 con `run_id`, y en <5s `GET /runs/<id>` devuelve `status="done"` con
  diff y `parity_score` — test F3.

## 2. Por qué ahora / gap que cierra

- El Plan 122 deja snapshots persistidos pero **nada los compara**: el valor del pedido
  del operador ("comparador … mostrando resumen de lo encontrado detallado") empieza acá.
- Los planes 125 (scripts de paridad + backups) y 126 (datos) consumen el `SchemaDiff v1`
  tal cual se congela en este documento; definirlo bien acá evita retrabajo en 3 planes.
- El patrón de corridas threaded con lock y stale-marker ya es doctrina de la casa
  (Plan 120: 1 thread por orden, guard A1 stale-running); se replica idéntico en dominio BD.

## 3. Principios y guardarraíles

1. **Función de diff PURA:** `diff_snapshots` no toca red, disco ni config — entra JSON,
   sale JSON. Toda la lógica testeable sin BD.
2. **Mismo motor o error:** si `source.engine != target.engine` → `DbCompareDiffError`
   (mensaje en español). Nada de comparaciones cross-engine silenciosas.
3. **Determinismo total:** items ordenados por `(object_type, schema, name)`; changes
   ordenados por `kind`; sin timestamps dentro del diff (van en el run).
4. **1 corrida por par:** dos corridas simultáneas del mismo par (en cualquier orden) →
   409. Threads daemon; el run persiste su estado en disco (no en memoria).
5. **Sin credenciales en runs:** los archivos de run guardan aliases e ids de snapshot,
   jamás passwords ni URLs de conexión.
6. **Flags:** este plan NO crea flags nuevas; todo gatea con el master
   `STACKY_DB_COMPARE_ENABLED` (Plan 122 F0). Cero trabajo del operador.
7. **Runtimes:** feature de panel; impacto por runtime N/A (idéntico con los 3).

## 4. Fases

### F1 — Núcleo puro: `services/dbcompare_diff.py`

**Objetivo:** producir el SchemaDiff v1 determinista con severidades desde dos snapshots v1.

**Archivo a crear:** `Stacky Agents/backend/services/dbcompare_diff.py`

**Símbolos exactos:**
```python
DIFF_VERSION = 1
SEVERITIES = ("info", "warn", "danger")

class DbCompareDiffError(RuntimeError): ...

def diff_snapshots(source: dict, target: dict) -> dict   # → SchemaDiff v1
def classify_severity(kind: str) -> str                  # tabla cerrada de abajo; kind desconocido → "warn"
def summarize(items: list[dict], objects_total: int, objects_unchanged: int) -> dict
```

**Contrato SchemaDiff v1 (congelado para la serie):**
```json
{
  "version": 1,
  "engine": "sqlserver",
  "source": {"alias": "...", "snapshot_id": "...", "content_hash": "..."},
  "target": {"alias": "...", "snapshot_id": "...", "content_hash": "..."},
  "items": [
    {
      "object_type": "table|view|sequence",
      "schema": "dbo", "name": "CLIENTES",
      "action": "added|removed|changed",
      "severity": "info|warn|danger",
      "changes": [ {"kind": "...", "severity": "...", "detail": {}} ]
    }
  ],
  "summary": {
    "by_severity": {"info": 0, "warn": 0, "danger": 0},
    "by_action": {"added": 0, "removed": 0, "changed": 0},
    "by_object_type": {"table": 0, "view": 0, "sequence": 0},
    "objects_total": 0, "objects_unchanged": 0,
    "parity_score": 100.0
  }
}
```
- Objetos `unchanged` NO emiten item (solo cuentan en summary).
- `severity` del item = máxima de sus `changes` (`danger > warn > info`); para
  `added/removed` la severidad sale de la tabla (kind `table_added`, etc.) y `changes=[]`.
- `parity_score = round(100.0 * objects_unchanged / objects_total, 1)`; si
  `objects_total == 0` → `100.0`.
- `detail` por kind (mínimo): columnas → `{"column": name, "source": {...}, "target": {...}}`
  con los sub-dicts de columna del snapshot; índices/constraints → `{"name", "source", "target"}`;
  vistas → `{"source_sha256", "target_sha256"}`.

**Tabla CERRADA de kinds y severidades (implementar como dict module-level `_KIND_SEVERITY`):**

| kind | severidad | disparo (comparando origen vs destino) |
|---|---|---|
| `table_added` | warn | tabla en origen, falta en destino |
| `table_removed` | danger | tabla en destino, no en origen (paridad = DROP) |
| `column_added` | warn | columna en origen falta en destino |
| `column_removed` | danger | columna sobra en destino |
| `column_type_changed` | danger | `type` distinto (comparación de strings EXACTA, ya vienen `upper()` del snapshot) |
| `column_nullable_relaxed` | warn | origen `nullable=True`, destino `False` (destino se relaja) |
| `column_nullable_tightened` | danger | origen `nullable=False`, destino `True` (paridad endurece → riesgo con datos existentes) |
| `column_default_changed` | info | `default` distinto |
| `column_autoincrement_changed` | warn | `autoincrement` distinto |
| `pk_changed` | danger | `primary_key.columns` distinto (comparar listas ordenadas) |
| `fk_added` / `fk_removed` / `fk_changed` | warn / warn / warn | FKs por clave `(name or columns-tuple)` |
| `index_added` / `index_removed` / `index_changed` | warn / warn / warn | índices por `name`; changed = columns o unique distintos |
| `unique_added` / `unique_removed` | warn / warn | unique constraints por `name` |
| `check_added` / `check_removed` / `check_changed` | warn / warn / warn | checks por `name`; changed = `sqltext` distinto |
| `view_added` / `view_removed` | warn / warn | vistas por nombre |
| `view_definition_changed` | warn | `definition_sha256` distinto (si alguno es `None` → kind `view_definition_changed` con `detail.unverifiable=true`) |
| `sequence_added` / `sequence_removed` | info / warn | secuencias por nombre |

**Pseudocódigo del recorrido (nivel tabla):**
```python
for schema in sorted(union(source.schemas, target.schemas)):
    s_tables, t_tables = source.schemas.get(schema, {}).get("tables", {}), target...
    for name in sorted(union): 
        if name not in t_tables: item(table, added)
        elif name not in s_tables: item(table, removed)
        else:
            changes = _diff_table(s_tables[name], t_tables[name])  # aplica la tabla de kinds
            if changes: item(table, changed, changes) else objects_unchanged += 1
    # ídem views (added/removed/definition_changed) y sequences (added/removed)
```
- Columnas se matchean por `name` (case-sensitive tal cual snapshot); el ORDEN ordinal NO
  genera diff (decisión v1: orden de columnas no es diferencia de paridad).
- FKs sin `name` (None) se matchean por tupla `(tuple(columns), referred_table, tuple(referred_columns))`.

**Tests PRIMERO:** `tests/test_plan123_dbcompare_diff.py` (fixtures: dicts snapshot v1 inline mínimos, SIN BD)
- `test_identicos_score_100_sin_items`
- `test_tabla_added_removed_severidades` (added→warn, removed→danger)
- `test_columna_tipo_nullable_default` (danger/danger/info según tabla; relaxed vs tightened ambos sentidos)
- `test_pk_e_indices`
- `test_view_sha_y_unverifiable`
- `test_engines_distintos_lanza`
- `test_determinismo_json_byte_identico` (KPI-1)
- `test_kpis_summary_exactos` (KPI-2: fixture con danger=2, warn=1)

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan123_dbcompare_diff.py -q`

**Criterio binario:** 8 tests verdes.

**Flag:** ninguna (módulo puro). **Runtimes:** N/A. **Operador:** ninguno.

### F2 — Corridas comparativas: `services/dbcompare_runs.py`

**Objetivo:** orquestar snapshot(origen) → snapshot(destino) → diff en un thread por corrida, con lock por par, persistencia por archivo y marcador stale.

**Archivo a crear:** `Stacky Agents/backend/services/dbcompare_runs.py`

**Símbolos exactos:**
```python
_RUNS_DIRNAME = "db_compare/runs"          # data_dir()/db_compare/runs/<run_id>.json
_STALE_AFTER_SEC = 1800                    # 30 min (doctrina Plan 120 A1)
_MAX_RUNS_KEPT = 100                       # prune FIFO al crear

class DbCompareBusyError(RuntimeError): ...   # par ya corriendo
class DbCompareRunError(RuntimeError): ...

_ACTIVE_PAIRS: set[frozenset] = set()      # {frozenset({src, dst})}
_ACTIVE_LOCK = threading.Lock()

def create_run(source_alias: str, target_alias: str, *, mode: str = "fresh") -> dict
    # mode ∈ {"fresh", "cached"}; valida ambientes existentes y MISMO engine (si no → DbCompareRunError)
    # par activo → DbCompareBusyError
    # escribe run inicial {status:"running", phase:"queued"} y lanza threading.Thread(
    #   target=_execute_run, args=(run_id, source_alias, target_alias, mode), daemon=True).start()
    # devuelve el run inicial.

def _execute_run(run_id, source_alias, target_alias, mode) -> None
    # try:
    #   _update(run_id, phase="snapshot_source"); snap_s = _resolve_snapshot(source_alias, mode)
    #   _update(run_id, phase="snapshot_target"); snap_t = _resolve_snapshot(target_alias, mode)
    #   _update(run_id, phase="diff"); diff = dbcompare_diff.diff_snapshots(snap_s, snap_t)
    #   _update(run_id, status="done", phase="done", diff=diff, finished_at=utcnow, duration_ms=...)
    # except Exception as exc:
    #   _update(run_id, status="error", error=_scrub(str(exc)), finished_at=...)
    # finally: liberar el par de _ACTIVE_PAIRS bajo _ACTIVE_LOCK

def _resolve_snapshot(alias, mode) -> dict
    # "fresh" → dbcompare_snapshot.take_snapshot(alias)
    # "cached" → dbcompare_snapshot.latest_snapshot(alias) o DbCompareRunError("sin snapshot cacheado de <alias>; tomá uno o usá modo fresco")

def get_run(run_id: str) -> dict | None
    # lee el archivo; si status=="running" y (utcnow - started_at) > _STALE_AFTER_SEC → agrega "stale": true (solo lectura, no muta el archivo)

def list_runs(limit: int = 50) -> list[dict]   # metadatos SIN diff: run_id, aliases, engine, status, phase, stale, started_at, finished_at, duration_ms, summary (si done)
def prune_runs() -> int
```

**Formato del run (archivo JSON):**
```json
{
  "run_id": "run_20260712T140000Z_PACIFICO-DEV_vs_PACIFICO-PROD",
  "source_alias": "...", "target_alias": "...", "engine": "sqlserver",
  "mode": "fresh", "status": "running|done|error", "phase": "queued|snapshot_source|snapshot_target|diff|done",
  "started_at": "...Z", "finished_at": "...Z|null", "duration_ms": 0,
  "source_snapshot_id": "...|null", "target_snapshot_id": "...|null",
  "summary": { ...copia de diff.summary cuando done... },
  "diff": { ...SchemaDiff v1 completo cuando done... },
  "error": null
}
```
- `run_id = f"run_{utcnow:%Y%m%dT%H%M%SZ}_{source_alias}_vs_{target_alias}"` (aliases ya
  validados por regex del Plan 122 → filename-safe).
- `_scrub(texto)`: por cada ambiente del par, si su password (via
  `dbcompare_registry.get_credential`) aparece en el texto → reemplazar por `"***"`.
- Escrituras atómicas: escribir a `<run_id>.json.tmp` + `os.replace`.

**Tests PRIMERO:** `tests/test_plan123_dbcompare_runs.py`
- Setup: 2 ambientes `test-a`/`test-b` sqlite (archivos tmp con DDL divergente) + snapshots
  pre-sembrados con `take_snapshot(alias, engine=<sqlite engine>)` → correr `mode="cached"`
  (NO necesita conexión real en el thread).
- `test_run_cached_done_con_diff` — polling con `time.sleep(0.05)` máx 5s hasta `done`; summary coherente.
- `test_run_fresh_sqlite_done` — ambientes sqlite reales (F2 del 122 soporta engine sqlite por alias `test-*`).
- `test_par_activo_409` — simular par en `_ACTIVE_PAIRS` → `DbCompareBusyError` (y en ambos órdenes del par).
- `test_error_scrubbed` — monkeypatch `take_snapshot` que lanza con el password en el mensaje → run error sin password.
- `test_stale_marker` — run file sembrado con `started_at` viejo y `status=running` → `get_run` agrega `stale: true`.
- `test_prune_runs`

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan123_dbcompare_runs.py -q`

**Criterio binario:** todos verdes sin drivers externos.

**Flag:** master (via API). **Runtimes:** N/A. **Operador:** ninguno.

### F3 — API de comparación en `api/db_compare.py`

**Objetivo:** exponer corridas por HTTP (arranque 202, polling, listado) con el gate del master.

**Archivo a editar:** `Stacky Agents/backend/api/db_compare.py` (creado en Plan 122 F4; se
agregan endpoints al MISMO blueprint, mismo helper `_require_enabled`).

**Endpoints exactos (bajo `/api/db-compare`):**
| Método y ruta | Comportamiento |
|---|---|
| `POST /compare` | body `{source_alias, target_alias, mode?: "fresh"\|"cached"}` → `create_run`; 202 `{ok, run: <metadatos>}`; `DbCompareBusyError` → 409; `DbCompareRunError`/ValueError → 400 |
| `GET /runs` | `{ok, runs: list_runs(limit=?limit≤200 default 50)}` |
| `GET /runs/<run_id>` | run completo (CON diff si done) / 404 |
| `GET /runs/<run_id>/export.md` | 200 `text/markdown; charset=utf-8` + header `Content-Disposition: attachment; filename="<run_id>.md"`; 409 si el run no está `done` |

**Tests PRIMERO:** `tests/test_plan123_dbcompare_api.py`
- `test_compare_202_y_polling_done` (sqlite cached, igual que F2)
- `test_compare_par_activo_409`
- `test_compare_engines_distintos_400`
- `test_runs_lista_sin_diff` (los metadatos NO incluyen la key `diff`)
- `test_export_md_headers_y_404_409`
- `test_flag_off_403` (todos los endpoints nuevos)

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan123_dbcompare_api.py -q`

**Criterio binario:** todos verdes.

**Flag:** `STACKY_DB_COMPARE_ENABLED`. **Runtimes:** N/A. **Operador:** ninguno.

### F4 — Export Markdown determinista: `export_markdown(run)`

**Objetivo:** resumen detallado portable (pegable en un ticket/wiki) generado desde el run.

**Archivo:** agregar a `Stacky Agents/backend/services/dbcompare_runs.py`:
```python
def export_markdown(run: dict) -> str
```

**Formato EXACTO (orden fijo, sin timestamps de generación — determinista por run):**
```markdown
# Comparación de BD: <source_alias> → <target_alias>

- **Motor:** <engine> | **Corrida:** <run_id>
- **Snapshots:** origen `<source_snapshot_id>` (`<hash8>`) · destino `<target_snapshot_id>` (`<hash8>`)
- **Parity score:** <parity_score>% (<objects_unchanged>/<objects_total> objetos sin diferencias)

## Resumen
| Severidad | Cantidad |
|---|---|
| 🔴 danger | n |
| 🟠 warn | n |
| 🔵 info | n |

| Acción | Cantidad |
(added/removed/changed)

## Diferencias (danger primero)
### 🔴 danger
- `dbo.CLIENTES` (table, changed): column_type_changed [DIRECCION], column_removed [FAX]
### 🟠 warn
- ...
### 🔵 info
- ...
```
- Items dentro de cada severidad ordenados por `(object_type, schema, name)`.
- Por item `changed`: lista de `kind [nombre-de-columna/índice si aplica]` separados por coma.
- `<hash8>` = primeros 8 chars del `content_hash`.
- Secciones de severidad sin items se omiten completas.

**Tests PRIMERO:** `tests/test_plan123_dbcompare_export.py`
- `test_export_contiene_lineas_exactas` (fixture run done → asserts de líneas literales:
  título, fila `| 🔴 danger | 2 |`, bullet de la tabla con kinds)
- `test_export_determinista` (dos llamadas → strings idénticos)
- `test_export_omite_secciones_vacias`

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan123_dbcompare_export.py -q`

**Criterio binario:** 3 tests verdes.

**Flag:** master (via endpoint F3). **Runtimes:** N/A. **Operador:** ninguno.

### F5 — No-regresión y cierre

**Comandos:**
```
cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan123_dbcompare_diff.py tests/test_plan123_dbcompare_runs.py tests/test_plan123_dbcompare_api.py tests/test_plan123_dbcompare_export.py -q
cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan122_dbcompare_flags.py tests/test_plan122_dbcompare_registry.py tests/test_plan122_dbcompare_engine.py tests/test_plan122_dbcompare_snapshot.py tests/test_plan122_dbcompare_api.py tests/test_smoke.py -q
```
**Criterio binario:** suites 123 verdes; suites 122 y smoke sin fallos nuevos.

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Snapshot fresco lento en BD grande bloquea el request | El compare es 202 + thread; el request nunca espera la reflection. |
| Proceso muere con run `running` | Marcador `stale` a los 30 min en lectura (doctrina Plan 120 A1); la UI 124 lo mostrará como abandonado. |
| Dos comparaciones concurrentes del mismo par pisándose | `_ACTIVE_PAIRS` + lock, 409 con mensaje claro (1 thread por orden, doctrina Plan 120). |
| Diff gigante en `GET /runs` | Listado devuelve metadatos+summary; el diff completo solo en `GET /runs/<id>`. |
| Falsos positivos por strings de tipo distintos entre versiones del mismo motor | Comparación v1 es textual y honesta; el item muestra ambos strings en `detail`. Normalizaciones finas quedan para una v2 si el uso real las pide (no inventar ahora). |

## 6. Fuera de scope

- UI (wizard, gauges, treemap, drill-down) → **Plan 124** (consume `/compare`, `/runs`).
- Scripts de paridad y backups → **Plan 125** (consume SchemaDiff v1 congelado acá).
- Diff de DATOS → **Plan 126**.
- Comparación cross-engine; normalización semántica de tipos; scheduling periódico de corridas.

## 7. Glosario

- **SchemaDiff v1:** contrato JSON de este doc §F1; congelado para los planes 124–126.
- **Parity score:** % de objetos idénticos sobre el total comparado (tablas+vistas+secuencias).
- **Corrida (run):** ejecución snapshot→snapshot→diff persistida en `data/db_compare/runs/`.
- **Stale:** run `running` con >30 min — casi seguro huérfano de un backend reiniciado.
- **fresh/cached:** tomar snapshots nuevos vs reusar el último persistido por ambiente.

## 8. Orden de implementación

1. F1 diff puro + tests (congela el contrato).
2. F2 runs + tests.
3. F3 API + tests.
4. F4 export + tests.
5. F5 no-regresión.

## 9. Definición de Hecho (DoD)

- [ ] `diff_snapshots` pura, determinista, con la tabla de kinds/severidades EXACTA de §F1.
- [ ] KPI-1/2/3 demostrados por los tests nombrados.
- [ ] Corridas threaded con lock por par, stale-marker, scrub de credenciales y prune.
- [ ] Endpoints `/compare`, `/runs`, `/runs/<id>`, `/runs/<id>/export.md` con gate del master y códigos 202/400/403/404/409 exactos.
- [ ] Export Markdown determinista con el formato literal de §F4.
- [ ] 4 archivos de test del plan verdes con los comandos exactos; suites del 122 sin fallos nuevos.
- [ ] Ningún endpoint nuevo ejecuta DDL/DML; los runs no contienen credenciales.
