# Plan 253 — Concurrencia SQLite: fin del `database table is locked`

**Estado:** CRITICADO v2
**Versión:** v1 -> v2 (juez adversarial, 2026-07-26). Veredicto de v1: **RECHAZADO** — 6 bloqueantes.
**Serie:** Robustez desde los logs (253-258). Este es el plan **#1 por retorno**: es el único hallazgo de la auditoría que hoy, 2026-07-26, está **destruyendo trabajo del agente en cada arranque del backend**.
**Fuente:** auditoría de ~16 MB de logs reales de `Stacky Agents/backend/data/logs/` + inspección de la DB de runtime + **mediciones nuevas en el venv del repo (v2)**.

> **Namespace de la serie.** Este plan es dueño de: `backend/db.py`, `backend/services/db_maintenance.py` (nuevo),
> `backend/services/maintenance.py` (nuevo), `backend/services/confirm_token.py` (nuevo),
> `backend/services/stacky_logger.py`, `backend/services/db_backup.py`, y del loop compartido
> `_maintenance_loop` (thread `stacky-maintenance`) en `backend/app.py`.
> **No** toca `services/local_file_logging.py` (dueño: plan 257), ni los ledgers JSONL (dueño: 258),
> ni `services/output_watcher.py` más allá de la barrera de F3 y los 2 call-sites de F4 (la cuarentena de intake es del 256).
>
> **Alias de fase para los planes hermanos:** el helper compartido `backend/services/confirm_token.py` se especifica en **F6** de esta v2.
> El plan **254** lo referencia como "plan 253 F5" (`254_...md:870`), numeración de la v1 de este documento. **Es el mismo módulo y la misma ruta**;
> vale la referencia por **ruta**, no por número de fase. Los planes **256 F4** y **258 F4** lo importan (8 menciones cada uno, verificado): no lo reimplementan.

---

## 0. CHANGELOG v1 -> v2

Cada bullet cierra un hallazgo de la crítica (IDs C1..C20 en §10).

- **[C1]** Se eliminó `_env_bool(...)` de todos los snippets: **no existe en `backend/config.py`** (0 hits). Se usa el idioma real de la casa. v1 dejaba el backend **muerto al importar `config`**.
- **[C2]** **La barrera de v1 apuntaba al escritor equivocado.** Medido: `init_db()` corre en `app.py:369` y **termina** antes de que el watcher arranque en `app.py:522`, en el mismo hilo. El escritor real es `_startup_sync(logger)` en `app.py:554`. La barrera pasa a ser de **escrituras de arranque**, no de esquema.
- **[C3]** Se eliminó `config.STACKY_TEST_MODE` (**no existe**). El mecanismo de "barrera armada" hace innecesario cualquier escape hatch de test-mode.
- **[C4]** Medido: bajo pytest la DB es `file:stacky_shared_mem?mode=memory&cache=shared&uri=true` y `PRAGMA journal_mode=WAL` devuelve **`memory`**. El test 1 de v1 era **imposible de poner en verde sin gamearlo** y el fallback de v1 escupía un warning falso en **cada** conexión. Ahora hay 4 estados explícitos (`ok` / `in_memory` / `rejected` / `disabled`) y el test corre sobre DB de **archivo**.
- **[C5]** `run_with_retry` ya **no** envuelve `session.query(...)`: envuelve la **unidad de trabajo completa** (una `session_scope()` fresca por intento). Reintentar dentro de la misma Session abortada es un defecto de diseño real.
- **[C6]** Medido: `DELETE ... LIMIT` da `near "limit": syntax error` en este SQLite. El lote se hace con `id IN (SELECT id ... LIMIT :n)`. Y el retry de v1 sobre `purge_old_logs` **nunca se disparaba**: el método se traga la excepción (`stacky_logger.py:468`).
- **[C7]** WAL rompía en silencio el backup semanal que **ya existe** (`services/db_backup.py:62` usa `shutil.copy2`, que deja fuera el sidecar `-wal`). v1 apuntaba el riesgo a `Prepare-Publication.ps1`, donde medí **0 hits** de la DB.
- **[C8]** Nueva **F1 completa** con los **6 lugares** del cableado de flags (v1 tenía 2). Incluye `PLAIN_HELP`, `_CATEGORY_KEYS`, `_CURATED_DEFAULTS_ON` y `_FROZEN_BOUNDS`.
- **[C9]** `synchronous=NORMAL` dejó de entrar de contrabando: es su propia flag **default OFF** con la excepción dura citada (reduce durabilidad).
- **[C10]** El conteo de flags de v1 mentía ("6" declaradas, 8 introducidas). v2 tiene una **tabla única** de **9 flags**, todas con prefijo `STACKY_`, con retrocompatibilidad de la env var histórica `SYSLOG_RETENTION_DAYS`.
- **[C11]** `confirm_token` pasa a ser `backend/services/confirm_token.py` **compartido**, declarado reusable por los planes **256 F4** y **258 F4**. Y se corrigió la afirmación falsa de v1: **no existe** pausa del output_watcher en `api/diag.py`.
- **[C12]** `_syslog_purge_loop` → **`_maintenance_loop`** (thread `stacky-maintenance`) con registro de tareas, para que el 257 F2 cuelgue su purga sin crear otro daemon.
- **[C13]** La compactación reusa `services/db_backup.py` y **su convención de nombre** (`stacky_agents-YYYYMMDD.db`); el nombre con timestamp de v1 rompía el pruning y hacía crecer los backups sin techo.
- **[C14]** El alta en el ratchet ahora cubre **`.sh` y `.ps1`** (sintaxis distinta, verificada). Windows es la plataforma del operador.
- **[C15]** Los criterios "grep sobre el log" dejaron de ser el único criterio: hay test determinista de la carrera + estado consultable.
- **[C16]** Nueva **F8**: registra la huella en `docs/sistema/error_fingerprints.json` (72 ocurrencias en un día y 0 huella).
- **[C17]** Un solo detector de "es SQLite" (`db_backup.sqlite_db_path()`), expuesto en el health.
- **[C18]** Documentado y medido: **`create_app()` corre DOS veces por arranque**, lo que duplica los escritores concurrentes.
- **[C19]** Se reemplazaron las frases vagas por `archivo:línea` + símbolo exacto.
- **[C20]** Declarado que el índice `ix_syslog_timestamp` **ya existe** (`models.py:457`), para que nadie agregue uno duplicado.
- **[ADICIÓN ARQUITECTO]** Nueva **F7**: guard de concurrencia **consultable** en `/api/diag/health` (bloque `db_runtime`). El operador ve si el fix está VIVO en su máquina en vez de asumirlo.

---

## 1. Objetivo y KPI

Eliminar la clase entera de fallos `sqlite3.OperationalError: database table is locked` poniendo la base de runtime en **WAL**, serializando **la fase de escritura del arranque** contra los daemons, dándole **reintento por unidad de trabajo** al `output_watcher` y al sink de `SystemLog`, y **purgando automáticamente** las 367.532 filas de `system_logs` que hoy inflan la DB a 148 MB.

| KPI | Hoy (medido) | Meta | Cómo se verifica (v2) |
|---|---|---|---|
| `database table is locked` por arranque | **2 a 6** (72 el 2026-07-26) | **0** | test determinista F0.3 + `db_runtime.lock_stats.exhausted == 0` en el health |
| Artefactos de agente descartados por lock en el primer scan | 1 por carpeta pendiente, en todo arranque | **0** | test F3.2 (round omitido **no** cachea mtime) |
| `syslog failed to persist batch of N events` | 4 (07-16, 07-18) | **0** | test F4.4 + `lock_stats.recovered` visible |
| Filas en `system_logs` | **367.532** | **< 40.000** | `db_runtime.syslog_rows` en el health |
| Tamaño de `backend/data/stacky_agents.db` | **148.529.152 bytes** | **< 40 MB** tras el primer `VACUUM` | `db_runtime.db_size_bytes` |
| `journal_mode` de la DB de runtime | `delete` | `wal` | `db_runtime.journal_mode_effective` |
| Estado de la concurrencia consultable por el operador | **no existe** | 1 bloque JSON | `GET /api/diag/health` → `db_runtime` |

> **Cambio de filosofía respecto de v1:** v1 medía el éxito con `grep` manual sobre logs. Un KPI que exige que el operador levante el backend y grepee **no es un criterio binario**. En v2 cada KPI tiene un test o un campo consultable.

---

## 2. Evidencia real (anclaje anti-alucinación)

E1-E5 son de v1 y **se conservan íntegras** (evidencia real medida). E6-E10 son mediciones **nuevas de v2** que cambian el diseño.

### E1 — El lock, y su patrón determinístico

Firma agregada (`grep -oh "ERROR .\{0,150\}"` + normalización de números sobre los 14 logs):

```
24 ERROR [stacky.output_watcher] output_watcher: error procesando C:\desarrollo\GIT\RS\RSPACIFICO\Agentes\outputs\N: (sqlite3.OperationalError) database tabl...
 2 ERROR [stacky.output_watcher] output_watcher: error procesando C:\desarrollo\GIT\RS\Agentes\outputs\N: (sqlite3.OperationalError) no such table: tickets
 1 ERROR [stacky.output_watcher] output_watcher: error procesando ...: (sqlite3.OperationalError) database table is locked
```

Serie temporal de la firma `database table is locked` (conteo de líneas por archivo de log):

| Log | Ocurrencias |
|---|---|
| `stacky-2026-07-12.log` | 8 |
| `stacky-2026-07-15.log` | 7 |
| **`stacky-2026-07-26.log`** | **72** ← HOY, y es el pico histórico |

Y `stacky-2026-07-16.log` aporta 6 de la variante `no such table: tickets` — misma causa raíz, capturada un instante antes en la migración.

**El patrón es determinístico y se repite en todos los arranques.** Extracto literal de `stacky-2026-07-26.log`:

```
2026-07-26 00:24:45 INFO [stacky_agents.app] output watcher armed (interval=3.0s)
2026-07-26 00:24:45 INFO [stacky.output_watcher] output watcher started (dir=C:\desarrollo\GIT\RS\RSPACIFICO\Agentes\outputs interval=3.0s, ...)
2026-07-26 00:24:48 INFO [stacky.output_watcher] output_watcher: dir vigilado → ...\Agentes\outputs (existe=True)
2026-07-26 00:24:48 ERROR [stacky.output_watcher] output_watcher: error procesando ...\Agentes\outputs\122: (sqlite3.OperationalError) database table is locked: tickets
[SQL: SELECT tickets.id AS tickets_id, ... FROM tickets WHERE tickets.ado_id = ? LIMIT ? OFFSET ?]
[parameters: (122, 1, 0)]
```

**El delta es siempre 3 segundos = exactamente un `interval` del watcher.**

Traceback agregado y tipo de excepción:

```
24  File "...\backend\services\output_watcher.py", line N, in scan_once
24  File "...\backend\.venv\Lib\site-packages\sqlalchemy\engine\base.py", line N, in _exec_single_context
24 sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) database table is locked: tickets
```

### E2 — La causa raíz, en tres piezas verificadas en el árbol

**(a) La DB de runtime NO está en WAL.** Medido con `PRAGMA journal_mode` sobre `Stacky Agents/backend/data/stacky_agents.db`:

```
journal_mode: ('delete',)
```

En modo `delete` (rollback journal) **un escritor bloquea a todos los lectores**. `Stacky Agents/backend/db.py` no ejecuta ningún `PRAGMA journal_mode` (0 hits de `journal_mode` y de `WAL`).

**(b) Hay DDL destructivo de arranque sobre `tickets`.**

- `Stacky Agents/backend/db.py:133` → `_rebuild_tickets_table_if_needed(conn)`
- `Stacky Agents/backend/db.py:200` → `def _rebuild_tickets_table_if_needed(conn) -> None:`
- `Stacky Agents/backend/db.py:268` → `conn.execute(text("DROP TABLE tickets"))`
- `Stacky Agents/backend/db.py:269` → `conn.execute(text("ALTER TABLE tickets__new RENAME TO tickets"))`

> **CORRECCIÓN v2 (C2):** este DDL **NO** es el escritor que produce el error de E1. Ver **E6**.

**(c) `busy_timeout` NO salva este caso, y esto es la trampa técnica del plan.** El engine se crea sin `timeout` explícito:

```python
# Stacky Agents/backend/db.py:19-31
if config.DATABASE_URL.startswith("sqlite"):
    _connect_args["check_same_thread"] = False
    if config.DATABASE_URL == "sqlite:///:memory:":
        _effective_url = "sqlite:///file:stacky_shared_mem?mode=memory&cache=shared&uri=true"

engine = create_engine(
    _effective_url, echo=False, future=True,
    connect_args=_connect_args,      # solo check_same_thread; SIN timeout
)
```

y hay **0 hits de `busy_timeout`** en todo el backend (excluyendo `.venv`).

**Pero el punto fino es otro:** el error es `database table is locked` = **`SQLITE_LOCKED`**, no `database is locked` = **`SQLITE_BUSY`**. `busy_timeout` **solo reintenta `SQLITE_BUSY`**; `SQLITE_LOCKED` retorna de inmediato. Subir el timeout no arregla nada por sí solo. Quien implemente esto debe entender esta distinción o va a "arreglar" el bug sin arreglarlo.

### E3 — El mismo lock rompe el sink de logs de la UI

```
4 ERROR [stacky.syslog] syslog failed to persist batch of 1 events
```
(3 en `stacky-2026-07-16.log`, 1 en `stacky-2026-07-18.log`). Mismo `_exec_single_context`: eventos de log del operador **perdidos para siempre** por contención de SQLite.

### E4 — La DB creció a 148 MB porque la purga existe pero nadie la llama

| Filas | Tabla |
|---|---|
| **367.532** | `system_logs` |
| 15.220 | `execution_logs` |
| 1.921 | `ticket_state_history` |
| 266 | `tickets` |
| 211 | `ticket_status_events` |
| 167 | `agent_executions` |

`system_logs` es el **99,3 %** de las filas. Tamaño del archivo: `148.529.152` bytes. El deploy pesa `12.038.144` bytes: la diferencia es puro `system_logs`.

La purga **ya está escrita, solo que huérfana**:

- `Stacky Agents/backend/services/stacky_logger.py:36` → `Call logger.purge_old_logs() periodically or via DELETE /api/logs/purge.`
- `Stacky Agents/backend/services/stacky_logger.py:62` → `RETENTION_DAYS = int(os.getenv("SYSLOG_RETENTION_DAYS", "90"))`
- `Stacky Agents/backend/services/stacky_logger.py:454` → `def purge_old_logs(self, days: int = RETENTION_DAYS) -> int:`

La retención de 90 días es **declarativa, no efectiva**. E4 **causa** E1.

### E5 — Cero mitigación en el llamador

En `Stacky Agents/backend/services/output_watcher.py`: **0 hits** de `retry`, `backoff`, `sleep`, `OperationalError`. Los únicos handlers son `except Exception` genéricos en `output_watcher.py:240-242` y `output_watcher.py:261-263`, que hacen `logger.exception` + `stats.errors += 1` y **descartan el round completo**. Como el fallo impide cachear el mtime, el archivo se reintenta en el siguiente poll → **loop de fallos en vez de recuperación**.

---

### E6 (v2, MEDIDO) — El escritor que toma el lock es `_startup_sync`, NO el DDL de `init_db()`

Orden real en `Stacky Agents/backend/app.py`:

| Línea | Qué pasa | Hilo |
|---|---|---|
| `app.py:369` | `init_db()` — **DDL, termina acá** | hilo de `create_app` |
| `app.py:522` | `start_output_watcher(poll_interval=3.0)` — nace el thread lector | crea thread daemon |
| `app.py:546-556` | `if _is_test_mode(): _startup_purge_only(logger)` / `else: _startup_sync(logger)` | hilo de `create_app` |

El DDL ya **terminó** ~3 segundos antes de que el watcher haga su primer scan. Prueba en el log del 2026-07-26:

```
línea  38: 2026-07-26 00:24:45 INFO  [stacky_agents.app]    output watcher armed (interval=3.0s)
línea  42: 2026-07-26 00:24:48 ERROR [stacky.output_watcher] ... database table is locked: tickets
línea 160: 2026-07-26 00:24:48 INFO  [stacky_agents.app]    sync ADO ok: project=Strategist_Pacifico fetched=176 created=176 updated=0 removed=0
```

**El error (línea 42) y el `sync ADO ok` (línea 160) caen en el MISMO segundo.** El escritor es `_startup_sync`: 176 INSERTs en una transacción, arrancada **después** de armar el watcher.

**Consecuencia de diseño:** una barrera liberada al final de `init_db()` (lo que pedía v1) ya estaría en `True` desde hace ~3 s cuando el watcher espera → **no-op**, el bug sobrevive intacto, y el plan se cerraría en falso verde. La barrera tiene que liberarse **después de `_startup_sync`**.

### E7 (v2, MEDIDO) — Bajo pytest, `journal_mode` NUNCA puede ser `wal`

`os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")` está al tope de ~100 archivos de `backend/tests/` (p. ej. `tests/test_ado_blocker_block.py:11`), y `db.py:21-24` lo remapea a `file:stacky_shared_mem?mode=memory&cache=shared&uri=true`.

Medición literal con el intérprete del repo (`backend/.venv/Scripts/python.exe`, Python 3.13.5, SQLite 3.49.1):

```
memoria compartida -> PRAGMA journal_mode=WAL devuelve: ('memory',)
  PRAGMA busy_timeout=15000 -> (15000,)   [SÍ aplica]
archivo real       -> PRAGMA journal_mode=WAL devuelve: ('wal',)
  PRAGMA synchronous (default)            -> (2,)  = FULL
  sidecars tras commit: ['t.db', 't.db-shm', 't.db-wal']
```

Tres consecuencias: (i) el test 1 de v1 era **inverificable** salvo gameándolo; (ii) el `else` de v1 loguearía "WAL rechazado por el filesystem" en **cada conexión de cada test** y misatribuiría la causa; (iii) `busy_timeout` sí es testeable en memoria.

### E8 (v2, MEDIDO) — WAL rompe el backup semanal que ya existe

`Stacky Agents/backend/services/db_backup.py:62` → `shutil.copy2(source, target)`.
Con WAL, lo commiteado vive en `stacky_agents.db-wal` hasta el checkpoint. Copiar solo el `.db` produce un **backup silenciosamente incompleto** desde el primer día del fix.

Además, `deployment/Prepare-Publication.ps1` tiene **0 hits** de `stacky_agents.db`, `*.db` y `-wal`: **no copia la DB**. El riesgo que v1 puso ahí estaba mal dirigido.

### E9 (v2, MEDIDO) — `DELETE ... LIMIT` no compila en este SQLite

```
DELETE-LIMIT: NOT SUPPORTED -> near "limit": syntax error
```
(`PRAGMA compile_options` no incluye `ENABLE_UPDATE_DELETE_LIMIT`.)
El "borrar en lotes de 5.000" de v1 no era implementable como estaba escrito.

Nota complementaria **(C20)**: el índice **ya existe** — `models.py:457` → `Index("ix_syslog_timestamp", "timestamp")`, y `purge_old_logs` filtra por `SystemLog.timestamp` (`stacky_logger.py:464`). **No agregar un índice nuevo.**

### E10 (v2, MEDIDO) — `create_app()` corre DOS veces por arranque

En `stacky-2026-07-26.log`, el bloque completo de arranque aparece dos veces con 4 segundos de diferencia:

```
línea  33: 00:24:45 INFO [stacky.demo_seed] demo seed: created=3 existed=0
línea  38: 00:24:45 INFO [stacky_agents.app] output watcher armed (interval=3.0s)
...
línea 167: 00:24:49 INFO [stacky.demo_seed] demo seed: created=0 existed=3
línea 170: 00:24:49 INFO [stacky_agents.app] output watcher armed (interval=3.0s)
```

Dos `create_app()` = dos `_startup_sync` = **el doble de escritores concurrentes**. Explica que 07-26 tenga 72 ocurrencias y no 6. El diseño de la barrera (F3) tiene que sobrevivir a esto **por construcción**, no por suerte.

---

## 3. Principios y guardarraíles (obligatorios)

- **Human-in-the-loop:** el `VACUUM` y la purga retroactiva son **destructivos/irreversibles** → van detrás de confirmación explícita del operador en la UI, con el conteo exacto a la vista. La purga *incremental* por retención no lo es y va automática.
- **Mono-operador sin auth:** no se introduce ningún permiso, rol ni chequeo de identidad. El `confirm_token` de F6 **no es seguridad**: es un interlock anti-clic-accidental que transporta el conteo exacto que se le mostró al operador. Decirlo en el docstring del módulo.
- **Paridad de 3 runtimes:** este plan es de infraestructura de datos, por debajo del runtime. Codex CLI, Claude Code CLI y GitHub Copilot Pro se benefician **idénticamente** y ninguno se toca — ni un archivo de `services/*_cli_runner.py` ni de `copilot_bridge.py` aparece en el plan. **Fallback explícito:** si el filesystem rechaza WAL, los tres siguen funcionando exactamente como hoy (modo `delete` + `busy_timeout` + reintento), sin excepción y con el estado visible en el health.
- **Cero trabajo extra al operador:** F1-F5 y F7-F8 son invisibles y automáticas. Lo único visible es un botón *"Compactar base"* que el operador usa **si quiere**.
- **No degradar:** WAL es más rápido, no más lento. Todo cambio es backward-compatible: una DB en WAL la sigue abriendo cualquier SQLite ≥ 3.7. La **única** degradación posible (durabilidad ante corte de energía) está aislada en una flag **default OFF** (§4).
- **Flags default ON**, salvo las 2 que citan excepción dura explícita (§4).
- **Toda flag configurable desde la UI** — y en v2 eso significa los **6 lugares** de F1, no solo el atributo en `Config`.
- **Reusar lo existente:** `services/db_backup.py` (backup + pruning + convención de nombre), `services/log_throttle.py` (`log_throttled`), `services/error_fingerprints.py` (huella), `models.py:457` (índice ya presente). Nada de reimplementar.

---

## 4. Tabla ÚNICA de flags (contrato congelado) — **9 flags** [C10]

Todas con prefijo `STACKY_`, el de la casa (verificado contra `FLAG_REGISTRY`).

| # | Key | Tipo | Default | Categoría (`_CATEGORY_KEYS`) | `min`/`max` | Justificación del default |
|---|---|---|---|---|---|---|
| 1 | `STACKY_SQLITE_WAL_ENABLED` | bool | **ON** | `base_datos` | — | No cae en ninguna excepción dura: no bypasea revisión humana, no es destructiva, no exige prerequisito (WAL es nativo desde SQLite 3.7) y no baja seguridad. Kill-switch de emergencia. |
| 2 | `STACKY_SQLITE_BUSY_TIMEOUT_MS` | int | **15000** | `base_datos` | 0 / 120000 | Tuning numérico. 0 = comportamiento actual. |
| 3 | `STACKY_SQLITE_SYNCHRONOUS_NORMAL_ENABLED` | bool | **OFF** | `base_datos` | — | **Excepción dura (4): reduce seguridad/durabilidad.** Con WAL, `synchronous=NORMAL` puede perder la última transacción commiteada ante corte de energía. Medido: el default de SQLite es `2` (FULL). [C9] |
| 4 | `STACKY_STARTUP_WRITE_BARRIER_WAIT_S` | float | **30.0** | `fiabilidad_ciclo_vida` | 0 / 300 | Tuning numérico. 0 = sin espera (comportamiento actual). |
| 5 | `STACKY_SQLITE_LOCK_RETRY_ENABLED` | bool | **ON** | `fiabilidad_ciclo_vida` | — | Ninguna excepción dura aplica. |
| 6 | `STACKY_SYSLOG_AUTO_PURGE_ENABLED` | bool | **ON** | `observabilidad_notif` | — | Borra solo lo que la retención declarada de 90 días **ya** consideraba descartable. No es "destructiva" en el sentido del riel: hace efectiva una política existente. |
| 7 | `STACKY_SYSLOG_PURGE_INTERVAL_S` | int | **21600** (6 h) | `observabilidad_notif` | 300 / 604800 | Tuning numérico. |
| 8 | `STACKY_SYSLOG_RETENTION_DAYS` | int | **90** | `observabilidad_notif` | 1 / 3650 | Igual al valor histórico. **Retrocompat obligatoria:** se lee `STACKY_SYSLOG_RETENTION_DAYS` y, si no está, la env var histórica `SYSLOG_RETENTION_DAYS` (documentada en `stacky_logger.py:35`), y recién después el default. |
| 9 | `STACKY_DB_COMPACT_ENABLED` | bool | **OFF** | `base_datos` | — | **Excepción dura (2): destructiva/irreversible.** Borra filas históricas y reescribe el archivo de la DB del operador. |

**Regla dura de conteo:** el DoD verifica `9`. Si una fase agrega una flag más, se actualiza esta tabla **y** el número del DoD en el mismo commit.

---

## 5. Fases

### F0 — Tests que reproducen el problema (rojo primero)

**Objetivo:** dejar en el arnés pruebas que hoy fallan por la misma razón que los logs, para que el fix no pueda ser un falso verde.

**Archivo a crear:** `Stacky Agents/backend/tests/test_plan253_sqlite_concurrency.py`

Primera línea ejecutable del archivo, como el resto del arnés:
```python
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
```

**Casos exactos (7):**

| # | Nombre | Qué asserta | Por qué hoy falla |
|---|---|---|---|
| 1 | `test_apply_sqlite_pragmas_pone_wal_en_db_de_archivo` | Sobre una DB **de archivo** en `tmp_path`, `db.apply_sqlite_pragmas(conn)` devuelve `{"journal_mode": "wal", ...}`. | El símbolo no existe. **No usar el engine global: bajo pytest es in-memory y devuelve `memory` — ver E7.** |
| 2 | `test_apply_sqlite_pragmas_reporta_in_memory_sin_warning` | Sobre `file:stacky_shared_mem?mode=memory&cache=shared&uri=true`, el estado devuelto es `wal_status == "in_memory"` (**no** `"rejected"`). | El símbolo no existe. Blinda C4. |
| 3 | `test_busy_timeout_efectivo_en_el_engine_global` | `engine.raw_connection()` → `PRAGMA busy_timeout` ≥ 15000. | Hoy devuelve el default de SQLite. Medido: **sí** aplica en memoria. |
| 4 | `test_lector_sobrevive_a_escritor_concurrente` | DB de **archivo** en `tmp_path`: thread A abre transacción de escritura sobre una tabla y duerme 0,5 s; thread B lee. B **no** levanta `OperationalError`. | Falla en modo `delete`. |
| 5 | `test_barrera_de_escrituras_de_arranque_existe_y_se_libera` | `db.arm_startup_writes()` → `db.wait_for_startup_writes(0.05) is False`; tras `db.mark_startup_writes_done()` → `True`. | Los símbolos no existen. |
| 6 | `test_barrera_no_armada_devuelve_true_inmediato` | Sin `arm_startup_writes()`, `wait_for_startup_writes(0.05) is True` y tarda < 0,02 s. | El símbolo no existe. Blinda el proceso empaquetado, el scan ad-hoc y los tests que no llaman `create_app`. |
| 7 | `test_run_with_retry_reintenta_solo_lock_y_solo_unidades_completas` | `db.run_with_retry` reintenta ante `OperationalError` con mensaje `locked` contando intentos con un contador; re-lanza `ValueError` en el **primer** intento. | El símbolo no existe. |

**Registro obligatorio en el ratchet — LOS DOS ARCHIVOS [C14]:**

1. `Stacky Agents/backend/scripts/run_harness_tests.sh` → dentro de `HARNESS_TEST_FILES=(` (arranca en la línea 20). Sintaxis **sin comillas y sin coma**:
   ```
     tests/test_plan253_sqlite_concurrency.py
   ```
2. `Stacky Agents/backend/scripts/run_harness_tests.ps1` → misma lista, sintaxis **con comillas y coma** (ver el bloque de las líneas 690-723):
   ```
     "tests/test_plan253_sqlite_concurrency.py",
   ```

> **Gotcha verificado:** las dos listas usan sintaxis DISTINTA. Copiar la del `.sh` al `.ps1` rompe el script de PowerShell — que es el que corre el operador en Windows. Hay tests que verifican el `.ps1` (`tests/test_plan251_env_matrix_flag.py:70`, `tests/test_plan80_ratchet_byteidentical.py:83`).

**Comando exacto:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan253_sqlite_concurrency.py -v
```

**Criterio binario:** los **7** tests existen y **fallan** (o erran por símbolo faltante) antes de F2. Si alguno pasa antes de F2, el test está mal escrito.

**Flag:** ninguna. **Impacto por runtime:** ninguno. **Trabajo del operador: ninguno.**

---

### F1 — Cableado completo de las 9 flags: los **6 lugares** [C8, C10]

**Objetivo:** que las 9 flags de §4 **aparezcan de verdad** en la UI. Declarar el atributo en `config.py` **no alcanza**: la UI se alimenta de `services/harness_flags.py`, no de `config.py`.

> **Por qué es una fase propia y va antes del comportamiento:** v1 decía "configurable desde UI: sí — se registra en el panel de flags (categoría `infraestructura`)". Esa categoría **no existe** (las reales están en `FLAG_CATEGORIES`, `harness_flags.py:53-118`) y faltaban 4 de los 6 lugares. Un modelo menor habría escrito el atributo, visto los tests verdes en su archivo, y entregado una flag invisible.

#### Lugar 1 — atributo en `class Config` (`backend/config.py`, la clase arranca en `config.py:60`)

**PROHIBIDO `_env_bool`: no existe en este archivo (0 hits).** Idioma literal de la casa:

```python
    # ── Plan 253 — concurrencia SQLite ──────────────────────────────────────
    STACKY_SQLITE_WAL_ENABLED: bool = os.getenv(
        "STACKY_SQLITE_WAL_ENABLED", "true").lower() in ("1", "true", "yes")
    STACKY_SQLITE_BUSY_TIMEOUT_MS: int = int(os.getenv("STACKY_SQLITE_BUSY_TIMEOUT_MS", "15000"))
    STACKY_SQLITE_SYNCHRONOUS_NORMAL_ENABLED: bool = os.getenv(
        "STACKY_SQLITE_SYNCHRONOUS_NORMAL_ENABLED", "false").lower() in ("1", "true", "yes")
    STACKY_STARTUP_WRITE_BARRIER_WAIT_S: float = float(
        os.getenv("STACKY_STARTUP_WRITE_BARRIER_WAIT_S", "30"))
    STACKY_SQLITE_LOCK_RETRY_ENABLED: bool = os.getenv(
        "STACKY_SQLITE_LOCK_RETRY_ENABLED", "true").lower() in ("1", "true", "yes")
    STACKY_SYSLOG_AUTO_PURGE_ENABLED: bool = os.getenv(
        "STACKY_SYSLOG_AUTO_PURGE_ENABLED", "true").lower() in ("1", "true", "yes")
    STACKY_SYSLOG_PURGE_INTERVAL_S: int = int(os.getenv("STACKY_SYSLOG_PURGE_INTERVAL_S", "21600"))
    # Retrocompat: la env var histórica SYSLOG_RETENTION_DAYS (stacky_logger.py:35) sigue valiendo.
    STACKY_SYSLOG_RETENTION_DAYS: int = int(
        os.getenv("STACKY_SYSLOG_RETENTION_DAYS")
        or os.getenv("SYSLOG_RETENTION_DAYS")
        or "90"
    )
    STACKY_DB_COMPACT_ENABLED: bool = os.getenv(
        "STACKY_DB_COMPACT_ENABLED", "false").lower() in ("1", "true", "yes")
```

> **Gotcha del repo, obligatorio:** los consumidores hacen `from config import config` — la **instancia**, no el módulo (verificado: `db.py:5`, `app.py:34`). Leer el atributo del **módulo** devuelve el default y mata la rama OFF. Todo snippet de este plan usa `config.X` habiendo importado `from config import config`.

#### Lugar 2 — `FlagSpec` en `backend/services/harness_flags.py` (tupla `FLAG_REGISTRY`, arranca en `harness_flags.py:443`)

Una entrada por flag. Ejemplo literal de la #1 y la #2 (las 7 restantes siguen el mismo molde; para las int declarar `min_value`/`max_value` de §4):

```python
    # ── Plan 253 — concurrencia SQLite y mantenimiento de la base ───────────
    FlagSpec(
        key="STACKY_SQLITE_WAL_ENABLED",
        type="bool",
        label="Base de datos: lectura y escritura simultáneas",
        description=(
            "Plan 253 — Pone la base de runtime en WAL: un escritor deja de bloquear a los "
            "lectores. Si el sistema de archivos lo rechaza, se sigue en el modo anterior "
            "con espera por lock y el estado queda visible en /api/diag/health."
        ),
        group="database",
        default=True,
        restart_required=True,   # el listener se ata al engine en el import de db.py
    ),
    FlagSpec(
        key="STACKY_SQLITE_BUSY_TIMEOUT_MS",
        type="int",
        label="Base de datos: espera máxima ante bloqueo (ms)",
        description="Plan 253 — Milisegundos que se espera si la base está tomada. 0 = sin espera.",
        group="database",
        min_value=0,
        max_value=120000,
        restart_required=True,
    ),
```

#### Lugar 3 — `_CATEGORY_KEYS` (`harness_flags.py:120`)

Agregar cada key a la tupla de su categoría según §4. **No inventar categorías**; las existentes relevantes son:

```python
    "base_datos": (
        "STACKY_DB_READONLY_DIRECTIVE_ENABLED", "STACKY_ADO_READ_CACHE_TTL_SEC",
        # Plan 253
        "STACKY_SQLITE_WAL_ENABLED", "STACKY_SQLITE_BUSY_TIMEOUT_MS",
        "STACKY_SQLITE_SYNCHRONOUS_NORMAL_ENABLED", "STACKY_DB_COMPACT_ENABLED",
    ),
```
(`harness_flags.py:341-345` hoy). Análogo en `"fiabilidad_ciclo_vida"` (`:277`) para las #4 y #5, y en `"observabilidad_notif"` (`:289`) para las #6, #7 y #8.

Si falta la categorización, el meta-test de categorías se pone **rojo**.

#### Lugar 4 — `PLAIN_HELP` en `backend/services/harness_flags_help.py`

`tests/test_harness_flags_help.py:32` exige cobertura **100 %** de `FLAG_REGISTRY`. Las reglas literales del test (verificadas):

- `on_effect` y `off_effect` **deben empezar con `"Si "`** — **sin tilde** (`test_plain_help_on_off_start_with_si`, línea 56).
- `what` entre 10 y 200 chars; `on_effect`/`off_effect` ≤ 240; `example` ≤ 300; ningún campo vacío.
- Prohibidas (también en plural) las 15 palabras de `JARGON_DENYLIST` (línea 17): **MCP, TF-IDF, LLM, stdin, stdout, endpoint, frontmatter, prompt, token, regex, backend, frontend, gate, hook, runtime**.
- Prohibido citar keys `SCREAMING_SNAKE` y prohibido referirse a fases (`\bF\d`).

Entradas listas para copiar (ya validadas contra las 4 reglas):

```python
    "STACKY_SQLITE_WAL_ENABLED": PlainHelp(
        what="Permite que la aplicación lea y escriba en su base al mismo tiempo, sin que una cosa trabe la otra.",
        on_effect="Si la activás: mientras algo se guarda, el resto de la aplicación puede seguir leyendo sin fallar.",
        off_effect="Si la apagás: se vuelve al comportamiento anterior, donde guardar bloquea a quien está leyendo.",
        example="Como una caja registradora que sigue atendiendo mientras se imprime el ticket anterior.",
    ),
    "STACKY_SQLITE_BUSY_TIMEOUT_MS": PlainHelp(
        what="Cuántos milisegundos espera la aplicación cuando su base está ocupada, antes de dar error.",
        on_effect="Si le ponés un número más alto: se aguantan esperas más largas en vez de fallar enseguida.",
        off_effect="Si lo ponés en cero: ante una base ocupada se falla de inmediato, como antes.",
        example="Como esperar unos segundos en la fila en vez de irte apenas ves gente.",
    ),
    "STACKY_SQLITE_SYNCHRONOUS_NORMAL_ENABLED": PlainHelp(
        what="Acelera el guardado a cambio de poder perder lo último guardado si se corta la luz de golpe.",
        on_effect="Si la activás: guardar es más rápido, pero un corte abrupto puede perder la última operación.",
        off_effect="Si la apagás: cada guardado se confirma en disco antes de seguir. Es lo recomendado.",
        example="Como elegir entre guardar el documento cada vez o dejarlo para el final.",
    ),
    "STACKY_STARTUP_WRITE_BARRIER_WAIT_S": PlainHelp(
        what="Cuántos segundos esperan las tareas de fondo a que termine la carga inicial antes de empezar a trabajar.",
        on_effect="Si le ponés segundos: las tareas de fondo arrancan recién cuando la carga inicial terminó.",
        off_effect="Si lo ponés en cero: las tareas de fondo arrancan de una, como antes, y pueden chocar con la carga.",
        example="Como esperar a que terminen de acomodar la mercadería antes de abrir la puerta al público.",
    ),
    "STACKY_SQLITE_LOCK_RETRY_ENABLED": PlainHelp(
        what="Vuelve a intentar una operación sobre la base cuando falló solo porque estaba ocupada.",
        on_effect="Si la activás: una operación que falló por base ocupada se reintenta sola y no se pierde trabajo.",
        off_effect="Si la apagás: la operación se descarta al primer choque, como pasaba antes.",
        example="Como volver a llamar cuando da ocupado, en vez de darlo por perdido.",
    ),
    "STACKY_SYSLOG_AUTO_PURGE_ENABLED": PlainHelp(
        what="Borra solo el historial de actividad más viejo que el plazo de conservación que elegiste.",
        on_effect="Si la activás: cada tanto se borra el historial vencido y la base deja de crecer sin control.",
        off_effect="Si la apagás: el historial se acumula para siempre y la base sigue creciendo.",
        example="Como tirar los recibos de hace más de dos años en vez de guardarlos todos.",
    ),
    "STACKY_SYSLOG_PURGE_INTERVAL_S": PlainHelp(
        what="Cada cuántos segundos se revisa si hay historial vencido para borrar.",
        on_effect="Si le ponés un número más chico: se limpia más seguido y de a menos cantidad por vez.",
        off_effect="Si le ponés un número más grande: se limpia con menos frecuencia y de a más por vez.",
        example="Como pasar a ordenar el archivo cada seis horas en lugar de una vez por semana.",
    ),
    "STACKY_SYSLOG_RETENTION_DAYS": PlainHelp(
        what="Cuántos días se conserva el historial de actividad antes de que se pueda borrar.",
        on_effect="Si le ponés más días: se guarda más historial y la base ocupa más lugar.",
        off_effect="Si le ponés menos días: se guarda menos historial y la base ocupa menos lugar.",
        example="Como decidir si guardás las facturas tres meses o tres años.",
    ),
    "STACKY_DB_COMPACT_ENABLED": PlainHelp(
        what="Habilita el botón que comprime la base para recuperar el espacio que dejaron los datos borrados.",
        on_effect="Si la activás: aparece el botón para comprimir. Nada se comprime hasta que vos lo confirmes.",
        off_effect="Si la apagás: el botón no aparece y la base nunca se comprime.",
        example="Como habilitar el botón de vaciar la papelera, que igual te pregunta antes de vaciarla.",
    ),
```

#### Lugar 5 — `_CURATED_DEFAULTS_ON` en `backend/tests/test_harness_flags.py:467`

Toda `FlagSpec` con `default=True` **debe** estar en ese set o `test_default_known_only_for_curated` se pone **rojo**. Agregar exactamente las 4 flags ON:

```python
    # ── Plan 253 — concurrencia SQLite y purga por retención ──
    # STACKY_SQLITE_SYNCHRONOUS_NORMAL_ENABLED y STACKY_DB_COMPACT_ENABLED NO van:
    # son default OFF por excepción dura (durabilidad / destructiva).
    "STACKY_SQLITE_WAL_ENABLED",
    "STACKY_SQLITE_LOCK_RETRY_ENABLED",
    "STACKY_SYSLOG_AUTO_PURGE_ENABLED",
```

> Nota: las 4 flags int/float (#2, #4, #7, #8) **no** llevan `default=True` (no son bool), así que no van a este set.
> Con `STACKY_SQLITE_WAL_ENABLED`, `STACKY_SQLITE_LOCK_RETRY_ENABLED` y `STACKY_SYSLOG_AUTO_PURGE_ENABLED` quedan **3** altas.

#### Lugar 6 — `_FROZEN_BOUNDS` en `backend/tests/test_harness_flags_bounds.py:149`

`test_bounds_map_is_frozen` (línea 182-190) compara con **igualdad exacta**:
```python
actual = {s.key: (s.min_value, s.max_value) for s in FLAG_REGISTRY
          if s.min_value is not None or s.max_value is not None}
assert actual == _FROZEN_BOUNDS
```
⇒ toda flag que declare `min_value` o `max_value` **debe** estar en el mapa. Agregar:
```python
    # Plan 253
    "STACKY_SQLITE_BUSY_TIMEOUT_MS": (0, 120000),
    "STACKY_STARTUP_WRITE_BARRIER_WAIT_S": (0, 300),
    "STACKY_SYSLOG_PURGE_INTERVAL_S": (300, 604800),
    "STACKY_SYSLOG_RETENTION_DAYS": (1, 3650),
```
**Regla de higiene:** ese mapa arrastra deuda ajena. Agregá **solo** tus 4 líneas; no "arregles" las que ya estaban.

#### Test de la fase

**Archivo a crear:** `Stacky Agents/backend/tests/test_plan253_flags_ui.py` (alta en el ratchet `.sh` **y** `.ps1`).

| # | Nombre | Assert |
|---|---|---|
| 1 | `test_las_9_flags_estan_en_el_registry` | Las 9 keys de §4 ∈ `{s.key for s in FLAG_REGISTRY}`. |
| 2 | `test_las_9_flags_tienen_categoria` | Ninguna cae en `"otros"`; cada una está en la categoría de §4. |
| 3 | `test_las_9_flags_tienen_ayuda_llana` | Las 9 ∈ `PLAIN_HELP`. |
| 4 | `test_defaults_on_declarados_son_exactamente_tres` | `{s.key for s in FLAG_REGISTRY if s.key.startswith(("STACKY_SQLITE","STACKY_SYSLOG","STACKY_DB_COMPACT","STACKY_STARTUP_WRITE")) and s.default is True}` == las 3 de §4. |
| 5 | `test_config_expone_los_9_atributos` | `from config import config` → `hasattr(config, k)` para las 9. |
| 6 | `test_retention_days_respeta_env_var_historica` | Con `SYSLOG_RETENTION_DAYS=7` y sin la nueva, `Config` resuelve 7. |

**Comando exacto:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan253_flags_ui.py tests/test_harness_flags.py tests/test_harness_flags_bounds.py -v
```

**Criterio binario:** `tests/test_plan253_flags_ui.py` **6 verdes**; `tests/test_harness_flags.py` **sin regresiones** respecto de su estado previo (guardar el conteo PASS/FAIL **antes** de tocar nada y comparar). `tests/test_harness_flags_help.py` tiene **4 fallos ajenos preexistentes**: validar que tus 9 keys no aparezcan en el mensaje de fallo, no que el archivo esté verde.

**Impacto por runtime:** ninguno. **Trabajo del operador: ninguno** (todos los defaults reproducen o mejoran lo de hoy).

---

### F2 — PRAGMAs de concurrencia, estado efectivo y backup a prueba de WAL [C4, C7, C9, C17]

**Objetivo:** que un escritor deje de bloquear a los lectores, **reportando el estado real** en vez de asumirlo, y sin romper el backup que ya existe.

**Archivos a editar:** `Stacky Agents/backend/db.py` (zona del engine, `db.py:19-31`) y `Stacky Agents/backend/services/db_backup.py`.

#### F2.a — función pura + listener

```python
# db.py — arriba, junto a los imports
import logging
import threading
import time
from sqlalchemy import event

logger = logging.getLogger("stacky.db")

# Plan 253 — estado EFECTIVO de la concurrencia, leído de vuelta del motor.
# Lo consume el guard de /api/diag/health. Nunca se "asume": siempre se relee.
_CONCURRENCY_STATE: dict = {
    "journal_mode_effective": None,
    "wal_status": "unknown",     # ok | in_memory | rejected | disabled | not_sqlite
    "busy_timeout_ms": None,
    "synchronous": None,
    "last_applied_at": None,
}
_IS_SQLITE = _effective_url.startswith("sqlite")
_IS_MEMORY_DB = "mode=memory" in _effective_url or _effective_url.endswith(":memory:")


def apply_sqlite_pragmas(dbapi_conn) -> dict:
    """Plan 253 F2 — aplica los PRAGMA de concurrencia a UNA conexión sqlite3 cruda.

    Devuelve el estado EFECTIVO releído del motor (no lo que pedimos).
    NUNCA levanta: cualquier fallo degrada al comportamiento de hoy.
    """
    state = {"journal_mode_effective": None, "wal_status": "disabled",
             "busy_timeout_ms": None, "synchronous": None,
             "last_applied_at": time.time()}
    cur = dbapi_conn.cursor()
    try:
        if config.STACKY_SQLITE_WAL_ENABLED:
            cur.execute("PRAGMA journal_mode=WAL")
            mode = str((cur.fetchone() or [""])[0]).lower()
            state["journal_mode_effective"] = mode
            if mode == "wal":
                state["wal_status"] = "ok"
            elif mode == "memory":
                # Base en memoria (tests / DB compartida en RAM). NO es un rechazo
                # del filesystem: WAL no aplica por definición. Medido: devuelve 'memory'.
                state["wal_status"] = "in_memory"
            else:
                state["wal_status"] = "rejected"
        else:
            cur.execute("PRAGMA journal_mode")
            state["journal_mode_effective"] = str((cur.fetchone() or [""])[0]).lower()
            state["wal_status"] = "disabled"

        cur.execute(f"PRAGMA busy_timeout={int(config.STACKY_SQLITE_BUSY_TIMEOUT_MS)}")
        cur.execute("PRAGMA busy_timeout")
        state["busy_timeout_ms"] = (cur.fetchone() or [None])[0]

        if config.STACKY_SQLITE_SYNCHRONOUS_NORMAL_ENABLED:
            cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA synchronous")
        state["synchronous"] = (cur.fetchone() or [None])[0]
    except Exception:  # noqa: BLE001 — la concurrencia jamás impide abrir la base
        logger.warning("sqlite: no se pudieron aplicar los PRAGMA de concurrencia", exc_info=True)
    finally:
        cur.close()
    return state


if _IS_SQLITE:
    @event.listens_for(engine, "connect")
    def _sqlite_on_connect(dbapi_conn, _rec):
        """Plan 253 F2 — PRAGMA en TODA conexión nueva del pool."""
        st = apply_sqlite_pragmas(dbapi_conn)
        _CONCURRENCY_STATE.update(st)
        if st["wal_status"] == "rejected":
            from services.log_throttle import log_throttled
            log_throttled(
                "db.wal_rejected", logger, logging.WARNING,
                "sqlite: el sistema de archivos rechazó WAL (journal_mode=%s); "
                "se sigue en ese modo con espera por lock de %d ms",
                st["journal_mode_effective"], int(config.STACKY_SQLITE_BUSY_TIMEOUT_MS),
                min_interval_s=300.0,
            )


def sqlite_concurrency_state() -> dict:
    """Plan 253 F2 — copia del estado efectivo, para el guard de salud."""
    return dict(_CONCURRENCY_STATE)
```

> **Por qué `log_throttled` y no `logger.warning`:** el listener corre en **cada** conexión del pool. Un `warning` pelado inundaría el log — exactamente el ruido que el plan 257 viene a matar. `services/log_throttle.py:30` → `log_throttled(key, logger, level, msg, *args, min_interval_s=60.0)`.

#### F2.b — backup a prueba de WAL [C7]

`services/db_backup.py:62` usa `shutil.copy2(source, target)`. Con WAL eso produce un backup **incompleto**. Reemplazar **solo esa línea** por una copia consistente con la API de SQLite:

```python
# db_backup.py — reemplaza `shutil.copy2(source, target)` en ensure_weekly_backup()
    import sqlite3
    src_conn = sqlite3.connect(str(source))
    try:
        dst_conn = sqlite3.connect(str(target))
        try:
            src_conn.backup(dst_conn)      # consistente: consolida el WAL en el destino
        finally:
            dst_conn.close()
    finally:
        src_conn.close()
```

**No** cambiar `backups_dir()`, ni `_BACKUP_RE`, ni `prune_old_backups`, ni el nombre `stacky_agents-YYYYMMDD.db`. El import de `shutil` puede quedar si otro símbolo lo usa; si queda huérfano, quitarlo.

#### Casos borde

- **Base en memoria** (tests, `db.py:21-24`): `wal_status = "in_memory"`, sin warning. Medido: `PRAGMA journal_mode=WAL` → `memory`.
- **Filesystem que no soporta WAL** (share de red): el `PRAGMA` devuelve el modo viejo en vez de fallar → `wal_status = "rejected"`, warning **throttleado** cada 5 min, y se continúa. **No se levanta excepción nunca.**
- **`DATABASE_URL` no-SQLite:** el listener ni se registra (`_IS_SQLITE`).
- **DB ya en WAL:** el `PRAGMA` es idempotente (WAL es persistente **en el archivo**, no por conexión).
- **Sidecars `-wal` / `-shm`:** quedan junto al `.db`. El backup de F2.b los consolida. `deployment/Prepare-Publication.ps1` **no copia la DB** (medido: 0 hits) → nada que cambiar ahí.

#### Tests

Los casos 1, 2, 3 y 4 de F0 pasan a **verde**. Sumar en `tests/test_plan253_sqlite_concurrency.py`:
- `test_backup_semanal_conserva_lo_commiteado_en_wal` — DB de archivo en WAL, commit, `ensure_weekly_backup()` monkeypatcheando `sqlite_db_path`/`backups_dir` a `tmp_path`, abrir el backup y verificar que la fila **está**. Con `shutil.copy2` este test es **rojo**.
- `test_synchronous_normal_es_opt_in` — con la flag OFF, `PRAGMA synchronous` devuelve `2`; con la flag ON, `1`.

**Criterio binario:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan253_sqlite_concurrency.py -v
```
todos verdes salvo los 3 de la barrera y el retry (F3/F4). Y, tras un arranque real del backend:
```
.venv\Scripts\python.exe -c "import sqlite3;print(sqlite3.connect('data/stacky_agents.db').execute('pragma journal_mode').fetchone())"
```
imprime `('wal',)`.

**Nota para quien implemente:** WAL **no** cubre `SQLITE_LOCKED` por DDL ni la contención de una transacción larga como la de E6. F2 es necesaria pero **no suficiente**. F3 y F4 completan el fix. **No cerrar el plan en F2.**

**Flags:** #1, #2, #3 de §4. **Impacto por runtime:** ninguno de los 3 se toca. **Trabajo del operador: ninguno.**

---

### F3 — Barrera de **escrituras de arranque** (no de esquema) [C2, C3]

**Objetivo:** que ningún daemon toque `tickets` mientras la fase de escritura del arranque está en curso. Esto es lo que mata el `SQLITE_LOCKED` que WAL no cubre.

> **Corrección central respecto de v1.** v1 liberaba la barrera al final de `init_db()`. Medido (E6): `init_db()` termina en `app.py:369`, el watcher nace en `app.py:522` y el escritor real (`_startup_sync`, 176 INSERTs) corre en `app.py:554`. Una barrera liberada en `init_db()` es un **no-op**: ya estaría abierta ~3 s antes del primer scan y el bug sobreviviría con el plan "implementado".

**Archivos a editar:** `backend/db.py`, `backend/app.py`, `backend/services/output_watcher.py`.

#### F3.a — la barrera, en `db.py`

```python
# db.py — junto al engine
_STARTUP_WRITES_DONE = threading.Event()
_BARRIER_ARMED = threading.Event()


def arm_startup_writes() -> None:
    """Plan 253 F3 — declara que empieza la fase de escritura del arranque.

    Se llama UNA vez por create_app(). Es idempotente y re-armable: si
    create_app() corre dos veces (medido: pasa), la segunda vuelve a cerrar la
    barrera mientras el segundo arranque escribe. Eso es lo correcto.
    """
    _BARRIER_ARMED.set()
    _STARTUP_WRITES_DONE.clear()


def mark_startup_writes_done() -> None:
    """Plan 253 F3 — libera la barrera. Va SIEMPRE en un finally."""
    _STARTUP_WRITES_DONE.set()


def wait_for_startup_writes(timeout_s: float = 30.0) -> bool:
    """Plan 253 F3 — bloquea hasta que la fase de escritura del arranque terminó.

    Devuelve True si se puede trabajar, False si expiró el timeout.
    NUNCA levanta. Si la barrera nunca se armó (proceso empaquetado sin
    create_app, scan ad-hoc del panel de diagnóstico, tests que instancian el
    watcher a mano) devuelve True INMEDIATAMENTE: sin armado no hay escritor
    de arranque contra el cual esperar. Esto elimina cualquier riesgo de que un
    daemon quede esperando 30 s por una barrera que nadie va a abrir.
    """
    if not _BARRIER_ARMED.is_set():
        return True
    if timeout_s <= 0:
        return _STARTUP_WRITES_DONE.is_set()
    return _STARTUP_WRITES_DONE.wait(timeout=timeout_s)


def startup_writes_state() -> dict:
    """Plan 253 F3 — para el guard de salud."""
    return {"armed": _BARRIER_ARMED.is_set(), "done": _STARTUP_WRITES_DONE.is_set()}
```

> **Por qué NO se usa un escape hatch de test-mode:** v1 proponía `config.STACKY_TEST_MODE`, símbolo que **no existe** (el idioma real es `os.getenv("STACKY_TEST_MODE","").lower() in {...}`, ver `app.py:379`, `services/local_file_logging.py:61`). El mecanismo de **armado** cubre el caso de los tests sin depender de ninguna variable: los tests que no llaman `create_app()` nunca arman la barrera y no esperan nada; los que sí la llaman pasan por el `finally` de F3.b. Un mecanismo, no dos.

#### F3.b — los 2 puntos exactos en `app.py`

1. **Armar**, inmediatamente **antes** de `init_db()` (`app.py:369`):
```python
    from db import arm_startup_writes, mark_startup_writes_done
    arm_startup_writes()          # Plan 253 F3 — cierra la barrera antes del primer write
    init_db()
```

2. **Liberar**, envolviendo el bloque `app.py:546-556` en un `try/finally`:
```python
    try:
        if _is_test_mode():
            _startup_purge_only(logger)
        else:
            _startup_sync(logger)
            _plan158_maybe_backfill_claude_model(logger)
            _plan199_maybe_autoscan_harvest(logger)
    finally:
        # Plan 253 F3 — la barrera se abre SIEMPRE, aunque el sync falle:
        # un arranque roto degrada al comportamiento de hoy, no cuelga daemons.
        mark_startup_writes_done()
```

#### F3.c — el consumidor, en `output_watcher.py:210`

Reemplazar el cuerpo inicial de `scan_once` (hoy la línea 212 es `self.stats.scans += 1`):

```python
    def scan_once(self) -> dict:
        """Una pasada manual. Retorna dict con counts del round."""
        from config import config
        from db import wait_for_startup_writes
        if not wait_for_startup_writes(timeout_s=config.STACKY_STARTUP_WRITE_BARRIER_WAIT_S):
            logger.warning(
                "output_watcher: la carga inicial sigue en curso tras %.1fs — se omite este "
                "round SIN marcar los artefactos como procesados",
                config.STACKY_STARTUP_WRITE_BARRIER_WAIT_S)
            self.stats.skipped_not_ready = getattr(self.stats, "skipped_not_ready", 0) + 1
            return {"skipped_startup_writes_pending": True}
        self.stats.scans += 1
        ...
```

**Regla dura:** al omitir el round **NO** se cachea el mtime (`self._seen_a` / `self._seen_b`) ni se marca nada como procesado. El artefacto se procesa íntegro en el poll siguiente. Ese es justamente el bug que hoy pierde trabajo.

#### Casos borde

- **Migración o sync que falla:** el `finally` abre la barrera igual → los daemons siguen con el comportamiento de hoy en vez de colgarse.
- **`create_app()` dos veces** (medido, E10): el segundo `arm_startup_writes()` vuelve a cerrar la barrera mientras el segundo `_startup_sync` escribe. El watcher del primer arranque espera. **Correcto por construcción.**
- **Sin deadlock posible:** `wait_for_startup_writes` la llama **solo** el thread del watcher, nunca el hilo que corre `init_db()`/`_startup_sync` (que es el de `create_app`). Verificado en el orden de `app.py`.
- **Scan manual** desde `POST /api/diag/output-watcher/scan-now` (`api/diag.py:139-165`): mismo path, misma espera. Si el arranque terminó, la espera es de microsegundos.
- **Proceso empaquetado (`DeployStackyAgents`):** entra por `create_app()` igual que el dev, así que arma y libera igual. Si algún entrypoint no pasara por `create_app()`, la barrera nunca se arma y `wait_for_startup_writes` devuelve `True` inmediato.

#### Tests

Los casos 5 y 6 de F0 pasan a verde. Sumar en `tests/test_plan253_sqlite_concurrency.py`:
- `test_scan_once_omite_round_si_el_arranque_escribe` — con la barrera armada y `STACKY_STARTUP_WRITE_BARRIER_WAIT_S=0.1`, `scan_once()` devuelve `{"skipped_startup_writes_pending": True}` y **no** incrementa `stats.scans`.
- `test_scan_once_no_cachea_mtime_al_omitir` — tras un round omitido, `self._seen_b` sigue vacío y el mismo archivo se reintenta en el round siguiente.
- `test_carrera_real_de_arranque` — **el test que reproduce E6**: DB de **archivo**; hilo A arma la barrera, abre una transacción e inserta 200 filas en `tickets` durmiendo 0,3 s antes del commit, y libera en un `finally`; hilo B llama `scan_once()`. Assert: B **no** deja `stats.errors > 0`. Sin F3, es rojo.

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan253_sqlite_concurrency.py -v
```
verde. **Y** un arranque real del backend deja `grep -c "database table is locked"` sobre el log del día en `0` (criterio secundario, manual — el primario es el test).

**Flag:** #4 de §4. **Impacto por runtime:** ninguno. **Trabajo del operador: ninguno.**

---

### F4 — Reintento por **unidad de trabajo** (no por query) [C5]

**Objetivo:** que un lock transitorio (los que WAL no elimina: DDL, checkpoint, `VACUUM`, transacción larga) no descarte trabajo.

> **Corrección central respecto de v1.** v1 mandaba envolver `session.query(...)`. Eso **no puede funcionar**: el call-site real está **dentro** de `with session_scope() as session:` y `session_scope` (`db.py:302-312`) hace `rollback()` + `raise` y `close()` en el `finally`. Reintentar el query deja la Session con la transacción abortada y ya cerrada. **Se reintenta la transacción completa, nunca la query.**

**Archivo a editar:** `backend/db.py` (helper) y **3 call-sites**.

#### F4.a — el helper, en `db.py`

```python
# db.py
_LOCK_MARKERS = ("database is locked", "database table is locked")
_LOCK_STATS = {"retried": 0, "recovered": 0, "exhausted": 0}
_LOCK_STATS_LOCK = threading.Lock()


def lock_stats() -> dict:
    """Plan 253 F4 — contadores acumulados, para el guard de salud."""
    with _LOCK_STATS_LOCK:
        return dict(_LOCK_STATS)


def run_with_retry(fn, *, attempts: int = 3, base_delay_s: float = 0.25, label: str = ""):
    """Plan 253 F4 — reintenta una UNIDAD DE TRABAJO COMPLETA ante lock de SQLite.

    `fn` DEBE abrir su propia sesión/transacción en cada invocación (típicamente
    un `with session_scope() as session:` adentro). PROHIBIDO pasarle una lambda
    que use una Session ya abierta: tras un OperationalError esa Session queda
    con la transacción abortada y cerrada por el finally de session_scope.

    Reintenta SOLO si es OperationalError cuyo mensaje contiene un marcador de
    lock. Cualquier otra excepción se re-lanza en el primer intento (no se
    enmascaran bugs). Tras agotar los intentos, re-lanza la última.
    Con la flag apagada, ejecuta fn() una sola vez.
    """
    from sqlalchemy.exc import OperationalError
    if not config.STACKY_SQLITE_LOCK_RETRY_ENABLED:
        return fn()
    last = None
    for i in range(attempts):
        try:
            result = fn()
            if i > 0:
                with _LOCK_STATS_LOCK:
                    _LOCK_STATS["recovered"] += 1
            return result
        except OperationalError as exc:
            msg = str(getattr(exc, "orig", None) or exc).lower()
            if not any(m in msg for m in _LOCK_MARKERS):
                raise
            last = exc
            if i < attempts - 1:
                with _LOCK_STATS_LOCK:
                    _LOCK_STATS["retried"] += 1
                time.sleep(base_delay_s * (2 ** i))   # 0.25s, 0.5s
                logger.warning("db lock en %s — reintento %d/%d",
                               label or "operación", i + 2, attempts)
    with _LOCK_STATS_LOCK:
        _LOCK_STATS["exhausted"] += 1
    raise last
```

#### F4.b — los 3 call-sites exactos

**1. `services/output_watcher.py:303-304`** — `_process_mode_b`. Es **el query literal del traceback de los logs**. El bloque `with session_scope() as session:` que arranca en la línea 303 se extrae a una función anidada y se invoca vía el helper:

```python
        # ── Consultar DB ──────────────────────────────────────────────────────
        from db import run_with_retry

        def _unit():
            with session_scope() as session:
                ticket = session.query(Ticket).filter(Ticket.ado_id == ado_id).first()
                ...   # el cuerpo actual del `with`, SIN cambios de lógica
        run_with_retry(_unit, label="output_watcher.mode_b")
```
**Regla:** los `return` internos del bloque actual pasan a ser `return` de `_unit()`; si el llamador los necesitaba para cortar, `_unit()` devuelve un centinela y el llamador decide. **No cambiar la lógica**, solo el envoltorio.

**2. `services/output_watcher.py:514-515`** — el equivalente en `_process_mode_a` (`with session_scope() as session:` en la línea 514, `session.query(Ticket).filter(Ticket.ado_id == effective_epic_ado_id)` en la 515). Mismo patrón, `label="output_watcher.mode_a"`.

**3. `services/stacky_logger.py:373-423`** — `_persist_batch`. El `with session_scope() as session:` de la línea 379 se envuelve **por dentro** del `try` existente, **antes** del `except Exception` de la línea 422:

```python
    def _persist_batch(self, events: list[LogEvent]) -> None:
        from db import run_with_retry, session_scope
        from models import SystemLog

        def _unit():
            with session_scope() as session:
                for evt in events:
                    ...   # el cuerpo actual, sin cambios
        try:
            run_with_retry(_unit, label="syslog.persist_batch")
        except Exception:
            if not self._requeue_once(events):
                _std.exception("syslog failed to persist batch of %d events", len(events))
```

`_requeue_once(events) -> bool`: método nuevo en `_StackyLogger`. Reencola **una sola vez** los eventos en `self._q` (la `queue.Queue` de la clase, `QUEUE_MAX = 10_000`, `stacky_logger.py:59`) marcándolos con un atributo `_requeued = True`; si el evento ya venía marcado, devuelve `False` y el batch se descarta con el `_std.exception` de siempre. Si la cola está llena, devuelve `False` (no bloquear el writer).

**Anti-recursión obligatoria:** `stacky_logger` alimenta el log; su propio reintento **no** debe loguear a través de sí mismo. Usar el logger stdlib directo — el archivo ya tiene el patrón `_std` (`stacky_logger.py:53`, usado en `:330`, `:423`, `:469`).

#### Tests

El caso 7 de F0 pasa a verde. Sumar:
- `test_run_with_retry_agota_y_relanza` — 3 intentos fallidos → levanta `OperationalError` y `lock_stats()["exhausted"] == 1`.
- `test_run_with_retry_no_reintenta_valueerror` — exactamente 1 invocación de `fn`.
- `test_run_with_retry_respeta_flag_off` — con `STACKY_SQLITE_LOCK_RETRY_ENABLED=False`, exactamente 1 invocación aunque el error sea de lock.
- `test_run_with_retry_abre_sesion_nueva_por_intento` — `fn` cuenta invocaciones y registra el `id()` de la sesión: los ids son **distintos** entre intentos. Blinda C5 contra una futura regresión a "envolver el query".
- `test_syslog_reencola_batch_antes_de_descartar` — un batch que falla una vez se persiste en el segundo intento; el conteo de eventos perdidos queda en 0.

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan253_sqlite_concurrency.py tests/test_stacky_logger.py -v
```
verde. `tests/test_stacky_logger.py` ya existe (`:266` ejercita `purge_old_logs(days=90)`) y **no debe regresar**.

**Flag:** #5 de §4. **Impacto por runtime:** ninguno. **Trabajo del operador: ninguno.**

---

### F5 — Loop de mantenimiento **compartido** + purga en lotes [C6, C12]

**Objetivo:** hacer **efectiva** la retención de 90 días que hoy es solo declarativa, sobre un punto de extensión que los planes hermanos puedan reusar.

> **Contrato para la serie 253-258:** este plan crea **un solo** daemon de mantenimiento. El plan **257 F2** cuelga ahí su purga de logs de archivo llamando a `register_maintenance_task(...)`; **no** debe crear otro thread. El 258 puede hacer lo mismo.

**Archivos:** `backend/services/maintenance.py` (**nuevo**), `backend/services/db_maintenance.py` (**nuevo**), `backend/services/stacky_logger.py`, `backend/api/logs.py`, `backend/app.py`.

#### F5.a — el registro de tareas (`services/maintenance.py`, nuevo)

Módulo **puro**: no toca Flask ni disco.

```python
"""Plan 253 F5 — registro de tareas periódicas de mantenimiento.

Punto de extensión COMPARTIDO. El loop vive en app.py (_maintenance_loop,
thread "stacky-maintenance"); acá solo se declara QUÉ correr y CADA CUÁNTO.
Los planes hermanos (257 F2 y siguientes) registran acá en vez de crear
daemons nuevos.
"""
from dataclasses import dataclass
from typing import Callable

@dataclass(frozen=True)
class MaintenanceTask:
    name: str                      # slug estable, aparece en el log y en el health
    interval_s: Callable[[], int]  # LAZY: se relee cada vuelta (la UI puede cambiarlo en caliente)
    enabled: Callable[[], bool]    # LAZY: idem para la flag
    run: Callable[[], int]         # devuelve "unidades procesadas" (filas, archivos, lo que sea)

_TASKS: list[MaintenanceTask] = []

def register_maintenance_task(task: MaintenanceTask) -> None: ...
def iter_maintenance_tasks() -> tuple[MaintenanceTask, ...]: ...
def maintenance_state() -> dict:
    """{name: {"last_run_at": float|None, "last_count": int, "last_error": str|None}}"""
def note_run(name: str, count: int, error: str | None = None) -> None: ...
```

**`interval_s` y `enabled` son callables a propósito:** leer `config.X` en tiempo de registro congelaría el valor y la flag de la UI no aplicaría hasta reiniciar. Es el mismo gotcha del `default` de argumento de `RETENTION_DAYS` (E4/C).

#### F5.b — el loop, en `app.py`

Mismo patrón que `_digest_loop` (`app.py:576`) y `_memory_review_sweep_loop` (`app.py:596`). **Nombre obligatorio `_maintenance_loop`, thread `stacky-maintenance`.**

```python
def _maintenance_loop():
    """Plan 253 F5 — único daemon de mantenimiento periódico del backend.

    Punto de extensión: las tareas se registran con
    services.maintenance.register_maintenance_task(). NO agregar threads nuevos.
    """
    from services.maintenance import iter_maintenance_tasks, note_run
    import time as _time
    _next: dict[str, float] = {}
    while True:
        _time.sleep(30.0)                      # tick fijo; el intervalo real es por tarea
        now = _time.monotonic()
        for task in iter_maintenance_tasks():
            try:
                if not task.enabled():
                    continue
                due = _next.get(task.name, 0.0)
                if now < due:
                    continue
                _next[task.name] = now + max(30, int(task.interval_s()))
                count = task.run()
                note_run(task.name, count)
                if count:
                    logger.info("mantenimiento %s: %d unidades procesadas", task.name, count)
            except Exception as exc:           # noqa: BLE001 — jamás mata el daemon
                note_run(task.name, 0, error=str(exc))
                logger.exception("mantenimiento %s: fallo no fatal", task.name)
```

Arranque, junto a los demás daemons de `create_app` (después de `app.py:556`), **sin flag propia** (el loop en sí no hace nada si no hay tareas habilitadas; una flag más sería ruido):

```python
    from services.db_maintenance import register_syslog_purge_task
    register_syslog_purge_task()
    threading.Thread(target=_maintenance_loop, name="stacky-maintenance", daemon=True).start()
```

> **Costo ocioso: cero tokens y cero red.** Un `sleep(30)` y una comparación de enteros. No pre-ejecuta nada, no llama a ningún modelo. Cumple la directiva de flags default ON.

#### F5.c — la purga en lotes (`services/db_maintenance.py`, nuevo)

```python
def purge_syslog_batched(*, days: int | None = None, batch_size: int = 5000,
                         max_batches: int = 200) -> int:
    """Plan 253 F5 — borra system_logs vencidos EN LOTES. Devuelve filas borradas.

    OJO (medido en este SQLite 3.49.1): `DELETE ... LIMIT` NO existe
    (`near "limit": syntax error`, sin ENABLE_UPDATE_DELETE_LIMIT). El lote se
    acota con una subconsulta por clave primaria.

    El índice ix_syslog_timestamp YA EXISTE (models.py:457): NO crear otro.
    """
    from datetime import datetime, timedelta
    from sqlalchemy import text
    from config import config
    from db import run_with_retry, session_scope

    days = config.STACKY_SYSLOG_RETENTION_DAYS if days is None else days
    cutoff = datetime.utcnow() - timedelta(days=days)
    total = 0
    for _ in range(max_batches):
        def _unit():
            with session_scope() as session:
                return session.execute(text(
                    "DELETE FROM system_logs WHERE id IN ("
                    "  SELECT id FROM system_logs WHERE timestamp < :cutoff LIMIT :n)"
                ), {"cutoff": cutoff, "n": batch_size}).rowcount
        deleted = run_with_retry(_unit, label="syslog.purge") or 0
        total += deleted
        if deleted < batch_size:
            break
    return total
```

`register_syslog_purge_task()` en el mismo módulo arma el `MaintenanceTask` con
`name="syslog_purge"`, `interval_s=lambda: config.STACKY_SYSLOG_PURGE_INTERVAL_S`,
`enabled=lambda: config.STACKY_SYSLOG_AUTO_PURGE_ENABLED`, `run=purge_syslog_batched`.

> **Por qué el retry va ADENTRO y no envolviendo `purge_old_logs` [C6]:** `stacky_logger.purge_old_logs` tiene un `except Exception: _std.exception(...); return 0` (`stacky_logger.py:468-470`). Envolverla desde afuera con `run_with_retry` **nunca vería** el `OperationalError` — el retry sería decorativo y el plan cerraría en falso verde.

#### F5.d — fuente única de la retención

`stacky_logger.py:454` evalúa `RETENTION_DAYS` **en tiempo de import** como default de argumento (`stacky_logger.py:62`). Cambiar la flag desde la UI **no** cambia ese default ya ligado. Cambio mínimo y backward-compatible:

```python
    def purge_old_logs(self, days: int | None = None) -> int:
        """Delete SystemLog rows older than `days` days. Returns count deleted.

        Plan 253 — days=None lee config.STACKY_SYSLOG_RETENTION_DAYS EN EL CUERPO,
        para que el valor de la UI aplique en caliente. Llamar con un int explícito
        sigue funcionando igual (api/logs.py:256, tests/test_stacky_logger.py:278).
        """
        from config import config
        if days is None:
            days = config.STACKY_SYSLOG_RETENTION_DAYS
        ...
```

Y **tercer lugar que v1 no vio:** `api/logs.py:24` importa `RETENTION_DAYS` a nivel de módulo y lo usa como default del endpoint en `api/logs.py:253`. Cambiar a:
```python
    days = request.args.get("days", default=config.STACKY_SYSLOG_RETENTION_DAYS, type=int)
```
`RETENTION_DAYS` **se conserva** en `stacky_logger.py:62` como alias deprecado (hay imports vivos) con un comentario `# Plan 253: deprecado, usar config.STACKY_SYSLOG_RETENTION_DAYS`.

> **Cuidado con el homónimo:** `services/local_file_logging.py:180` también define `purge_old_logs` — es la purga de **archivos** de log y es territorio del **plan 257**. No tocarla.

#### Casos borde

- Purga corriendo mientras el watcher escanea: por eso F5 va **después** de F2/F4 (WAL + retry ya la absorben) y va en lotes.
- Primera corrida sobre 367 K filas: `max_batches=200 × 5000 = 1.000.000` de techo por vuelta; con 327 K vencidas termina en ~66 lotes. Cada lote es su propia transacción corta.
- Cola de eventos vacía / nada vencido: `deleted == 0` en el primer lote → corta, sin log.
- Cambio de intervalo desde la UI: aplica en la vuelta siguiente (≤ 30 s) porque `interval_s` es lazy.

#### Tests

**Archivo a crear:** `Stacky Agents/backend/tests/test_plan253_syslog_purge.py` (alta en el ratchet `.sh` **y** `.ps1`).

| # | Nombre | Assert |
|---|---|---|
| 1 | `test_purge_borra_solo_lo_mas_viejo_que_retencion` | Siembra filas de 100 y de 10 días; solo se borra la de 100. |
| 2 | `test_purge_en_lotes_no_excede_batch_size` | Con 12.000 filas viejas y `batch_size=5000`, se hacen 3 pasadas y el total es 12.000. |
| 3 | `test_purge_no_usa_delete_limit` | El SQL emitido contiene `id IN (` y **no** matchea `DELETE FROM system_logs WHERE timestamp < ? LIMIT`. Blinda E9. |
| 4 | `test_purge_respeta_flag_off` | Con `STACKY_SYSLOG_AUTO_PURGE_ENABLED=False`, `task.enabled()` es `False` y el loop no la corre. |
| 5 | `test_retention_days_sale_de_config_no_del_modulo` | Cambiar `config.STACKY_SYSLOG_RETENTION_DAYS` cambia el comportamiento de `purge_old_logs()` sin argumento. |
| 6 | `test_purge_old_logs_con_dias_explicitos_sigue_funcionando` | `purge_old_logs(days=90)` se comporta como antes (backward-compat de `api/logs.py:256`). |
| 7 | `test_maintenance_task_registrada_una_sola_vez` | Dos `register_syslog_purge_task()` no duplican la tarea. |

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan253_syslog_purge.py -v
```
7 verdes. Y, en vivo, `db_runtime.syslog_rows` del health (F7) decrece entre dos consultas separadas por un intervalo de purga.

**Flags:** #6, #7, #8 de §4. **Impacto por runtime:** ninguno. **Trabajo del operador: ninguno.**

---

### F6 — Compactación asistida (HITL, la única pieza destructiva) [C11, C13]

**Objetivo:** darle al operador un botón para recuperar los ~110 MB que hoy ocupa el histórico, **sin que el sistema lo haga a sus espaldas**.

**Archivos:** `backend/services/confirm_token.py` (**nuevo**), `backend/services/db_maintenance.py`, `backend/api/diag.py`, `frontend/src/api/endpoints.ts`.

#### F6.a — `services/confirm_token.py` (nuevo, **compartido con 256 F4 y 258 F4**)

> **Reuso declarado:** medido, `confirm_token` tiene **0 implementaciones** en `services/` y `api/`. Los planes **256 F4** y **258 F4** describen el mismo interlock. Este módulo es el único; esos planes lo **importan**, no lo reimplementan.

> **No es seguridad.** Stacky es mono-operador sin login: `current_user` es un header sin validar y no hay 403 real. Esto es un **interlock anti-clic-accidental** que transporta el conteo exacto que se le mostró al operador, para que no pueda confirmar una cifra distinta de la que vio. Decirlo textual en el docstring del módulo, para que nadie lo confunda con un control de acceso.

```python
def issue_token(action: str, payload: dict, ttl_s: float = 120) -> str:
    """Emite un identificador efímero atado a (action, payload). En memoria del proceso."""

def consume_token(action: str, token: str) -> dict:
    """Devuelve el payload y lo invalida (un solo uso).
    Levanta ConfirmTokenError si no existe, ya se usó, venció o la acción no coincide."""

class ConfirmTokenError(Exception): ...
```
Diccionario en memoria + `threading.Lock`. Sin persistencia (si el backend se reinicia, el operador vuelve a pedir el diagnóstico — es lo correcto: el conteo cambió).

#### F6.b — `services/db_maintenance.py`

```python
def db_stats() -> dict:
    """{'path','size_bytes','wal_size_bytes','page_count','page_size','journal_mode',
        'rows_by_table': {...}, 'purgeable_rows': int, 'purgeable_before': iso,
        'estimated_reclaim_bytes': int}
    Usa db_backup.sqlite_db_path() como ÚNICO detector de 'es SQLite con archivo'."""

def compact_db(*, token: str, purge_retroactive: bool) -> dict:
    """VACUUM + (opcional) purga retroactiva. Exige un token de confirmación válido."""
```

**Contrato HITL, no negociable:**

1. `GET /api/diag/db/stats` devuelve el diagnóstico **y** un identificador de confirmación efímero (TTL 120 s) cuyo payload lleva `rows_to_delete`, `bytes_to_reclaim` y `cutoff_iso`.
2. La UI muestra el número real: *"Se eliminarán 327.481 filas de historial anteriores al 2026-04-27 y se recuperarán ~108 MB. Esto no se puede deshacer."*
3. `POST /api/diag/db/compact` **exige** ese identificador. Sin él, o vencido, o con `rows_to_delete` distinto del actual (± 5 %): **`409`** y no se toca nada.
4. **Backup previo obligatorio, reusando `services/db_backup.py`** [C13]: llamar a `ensure_weekly_backup()` (que en F2.b ya usa `Connection.backup()`) y, si esa semana ya existe uno, forzar uno nuevo con la **misma convención de nombre** `stacky_agents-YYYYMMDD.db` que entiende `_BACKUP_RE` (`db_backup.py:14`) y respeta `prune_old_backups(keep=4)`. **PROHIBIDO** inventar `stacky_agents-<timestamp>.db`: ese nombre no matchea `_date_from_backup` → el pruning nunca lo borraría y cada compactación dejaría 148 MB muertos para siempre.
   Si el backup falla, **se aborta** y no se compacta.
5. Orden exacto de la operación, documentado en el docstring de `compact_db`:
   1. validar el identificador; 2. `shutil.disk_usage` ≥ 2,2 × tamaño de la DB, si no → abortar con mensaje claro; 3. **detener el output_watcher**; 4. backup; 5. purga retroactiva en lotes (reusa `purge_syslog_batched`); 6. `PRAGMA wal_checkpoint(TRUNCATE)`; 7. `VACUUM` en una conexión aparte con `isolation_level=None` (no corre dentro de una transacción); 8. **reanudar el output_watcher**; 9. devolver el before/after.
   Los pasos 3 y 8 van en un `try/finally` para que un fallo del `VACUUM` no deje al watcher apagado.

> **Corrección de v1 [C11]:** v1 decía "pausar el output_watcher (ya existe el control en `api/diag.py`)". **Es falso**: en `api/diag.py` solo hay `POST /output-watcher/scan-now` (`:139`) y `GET /output-watcher/stats` (`:168`). Los símbolos que **sí** existen son `AdoOutputWatcher.stop()` (`output_watcher.py:201`) y `start_output_watcher(poll_interval=...)` (`output_watcher.py:179`), más `get_output_watcher()`. Usar esos, y si el watcher no estaba corriendo, no arrancarlo al final.

#### Casos borde

- Disco sin espacio para el backup + el temporal del `VACUUM` (~2× el tamaño): chequear **antes** y abortar con mensaje claro.
- `VACUUM` con WAL: el `wal_checkpoint(TRUNCATE)` del paso 6 es obligatorio; si no, el `-wal` sobrevive con contenido y el "espacio recuperado" que se le reporta al operador es mentira.
- DB no-SQLite o en memoria: `db_stats()` devuelve `{"available": False, "reason": ...}` y el endpoint responde `409`; no hay nada que compactar.
- Flag OFF: el endpoint responde `409 {"error": "compact_disabled"}` sin tocar nada.

#### Tests

**Archivo a crear:** `Stacky Agents/backend/tests/test_plan253_db_compact.py` (alta en el ratchet `.sh` **y** `.ps1`).

`test_compact_sin_confirmacion_devuelve_409` · `test_compact_con_confirmacion_vencida_devuelve_409` · `test_confirmacion_es_de_un_solo_uso` · `test_compact_hace_backup_antes_de_vacuum` · `test_compact_aborta_si_falla_el_backup` (el archivo original queda intacto) · `test_compact_aborta_si_no_hay_espacio_en_disco` · `test_compact_respeta_flag_off` · `test_backup_usa_la_convencion_de_nombre_existente` (el nombre matchea `db_backup._BACKUP_RE`) · `test_db_stats_reporta_journal_mode_y_filas_por_tabla`.

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan253_db_compact.py -v
```
9 verdes. Y manualmente: el botón muestra el conteo real antes de pedir confirmación.

**Flag:** #9 de §4, **default OFF**, **excepción dura (2): destructiva/irreversible**.
**Impacto por runtime:** ninguno. **Trabajo del operador:** opt-in explícito, un clic, con el número exacto a la vista. Es la excepción justificada al "cero trabajo".

---

### F7 — **[ADICIÓN ARQUITECTO]** Guard de concurrencia consultable en el health [C15, C17, C18]

**Problema que resuelve:** v1 medía todo su éxito con `grep` manual sobre logs. El operador no tiene forma de saber **si el fix está vivo en SU máquina**: si su filesystem rechazó WAL, si el `busy_timeout` quedó en 0 porque alguien tocó la flag, si la barrera se armó, o si hubo locks que agotaron los reintentos. Un fix de concurrencia que no se puede consultar es un fix que se asume.

**Archivo a editar:** `Stacky Agents/backend/api/diag.py` — el endpoint `GET /health` ya existe (`diag.py:311`) y ya publica `warnings` (`diag.py:368`). **No se crea un endpoint nuevo.**

Agregar al payload:

```python
    # Plan 253 F7 — estado REAL de la concurrencia de la base de runtime.
    from db import lock_stats, sqlite_concurrency_state, startup_writes_state
    from services.db_backup import sqlite_db_path
    from services.maintenance import maintenance_state

    _db_path = sqlite_db_path()
    _conc = sqlite_concurrency_state()
    db_runtime = {
        "sqlite_file": str(_db_path) if _db_path else None,
        "db_size_bytes": _db_path.stat().st_size if _db_path and _db_path.exists() else None,
        "wal_size_bytes": (
            _wal.stat().st_size
            if _db_path and (_wal := _db_path.with_name(_db_path.name + "-wal")).exists()
            else 0
        ),
        "journal_mode_effective": _conc["journal_mode_effective"],
        "wal_status": _conc["wal_status"],          # ok | in_memory | rejected | disabled | not_sqlite
        "busy_timeout_ms": _conc["busy_timeout_ms"],
        "synchronous": _conc["synchronous"],
        "startup_writes": startup_writes_state(),   # {"armed": bool, "done": bool}
        "lock_stats": lock_stats(),                 # {"retried","recovered","exhausted"}
        "maintenance": maintenance_state(),
    }
```

y **enganchar las señales duras a la lista `warnings` que el endpoint ya tiene** (`diag.py:368`):

```python
    if db_runtime["wal_status"] == "rejected":
        warnings.append(
            "la base no pudo pasar a lectura/escritura simultánea en este disco "
            f"(quedó en '{db_runtime['journal_mode_effective']}'): puede haber "
            "errores de bloqueo bajo carga"
        )
    if (db_runtime["lock_stats"] or {}).get("exhausted", 0) > 0:
        warnings.append(
            f"{db_runtime['lock_stats']['exhausted']} operaciones se perdieron por "
            "bloqueo de la base pese a los reintentos"
        )
    if db_runtime["sqlite_file"] is None and str(config.DATABASE_URL).startswith("sqlite"):
        warnings.append(
            "la base figura como archivo pero no se pudo resolver su ruta: "
            "la copia de respaldo semanal no se está haciendo"
        )
```

> **El tercer warning nace de una discrepancia medida [C17]:** el log del 2026-07-26 (líneas 32 y 166) dice `db backup omitido: non_sqlite_database` en un entorno donde el error **es** `sqlite3.OperationalError`. Hoy hay **dos** detectores incompatibles: `db.py:19` usa `config.DATABASE_URL.startswith("sqlite")` y `db_backup.sqlite_db_path()` usa `make_url().get_backend_name()` descartando `:memory:` y `file:`. F7 hace visible la divergencia en vez de dejarla muda: si aparece ese warning, el operador **no tiene backups**.

**[C18] Contador de arranques.** Agregar en `app.py`, junto a `arm_startup_writes()`, un contador de módulo `_CREATE_APP_COUNT` que se incrementa en cada `create_app()`, y publicarlo como `db_runtime["create_app_count"]`. Medido (E10): hoy vale **2**. Si el operador lo ve en 2, sabe que tiene el doble de escritores concurrentes y que ese es un hallazgo a investigar aparte (fuera del scope de este plan, ver §7).

**Frontend (mínimo, sin lógica nueva):** extender el tipo del health en `frontend/src/api/endpoints.ts:3157` con el bloque `db_runtime` (opcional, `?`), y mostrarlo en el panel de diagnóstico existente como una lista de pares clave/valor de solo lectura. Sin gráficos, sin polling nuevo: el health ya se consulta.

**Tests.** Archivo a crear: `Stacky Agents/backend/tests/test_plan253_health_guard.py` (alta en el ratchet `.sh` **y** `.ps1`).

| # | Nombre | Assert |
|---|---|---|
| 1 | `test_health_expone_db_runtime` | `GET /api/diag/health` trae la clave `db_runtime` con las 10 subclaves. |
| 2 | `test_health_reporta_in_memory_bajo_pytest` | Bajo pytest, `wal_status == "in_memory"` (**no** `"rejected"`). Blinda C4 desde el otro lado. |
| 3 | `test_health_avisa_si_wal_fue_rechazado` | Monkeypatch del estado a `rejected` → aparece el warning en `warnings`. |
| 4 | `test_health_avisa_si_hubo_locks_agotados` | Con `exhausted=3`, aparece el warning con el número. |
| 5 | `test_health_no_rompe_si_la_base_no_es_sqlite` | Con `sqlite_db_path()` devolviendo `None`, responde 200 y `sqlite_file` es `None`. |
| 6 | `test_health_es_solo_lectura` | Dos llamadas seguidas no cambian `lock_stats` ni `startup_writes`. |

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan253_health_guard.py -v
```
6 verdes. Y, en vivo, `GET /api/diag/health` devuelve `db_runtime.wal_status == "ok"` en la máquina del operador.

**Flag:** ninguna (es diagnóstico de solo lectura, sin costo ocioso). **Impacto por runtime:** ninguno. **Trabajo del operador: ninguno** — al contrario, le da la respuesta que hoy no tiene.

---

### F8 — Huella de regresión + cierre [C16]

**Objetivo:** que esta clase de error, si vuelve, se detecte sola.

Existe el catálogo `Stacky Agents/docs/sistema/error_fingerprints.json` (schema `id`, `title`, `class`, `status`, `log_pattern`, `log_guarded`, `killed_by`, `killed_commit`, `date_resolved`, `guard_test`, `evidence`, `note`) y el escáner `services/error_fingerprints.py:51 run_boot_scan()`, que **ya corre en cada arranque** (`app.py:376`) y alarma si un patrón `status=resolved` reaparece en un log fresco. Una clase de error con **72 ocurrencias en un solo día** y **0 huella** es exactamente lo que ese catálogo existe para atrapar.

Agregar a `fingerprints`:

```json
    {
      "id": "sqlite_table_locked_startup",
      "title": "database table is locked: tickets durante el arranque",
      "class": "sqlite-contention",
      "status": "resolved",
      "log_pattern": "database table is locked",
      "log_guarded": true,
      "killed_by": "plan 253 (concurrencia SQLite)",
      "killed_commit": "<sha del commit de F3>",
      "date_resolved": "2026-07-26",
      "guard_test": "tests/test_plan253_sqlite_concurrency.py",
      "evidence": "backend/app.py:369,522,554; backend/db.py:19-31; backend/services/output_watcher.py:303,514; stacky-2026-07-26.log lineas 42 y 160",
      "note": "El escritor es _startup_sync (176 INSERT), no el DDL de init_db: init_db termina antes de que el watcher arranque."
    },
    {
      "id": "syslog_batch_persist_failed",
      "title": "syslog failed to persist batch por contencion de SQLite",
      "class": "sqlite-contention",
      "status": "resolved",
      "log_pattern": "syslog failed to persist batch",
      "log_guarded": true,
      "killed_by": "plan 253 (reintento por unidad de trabajo + reencolado)",
      "killed_commit": "<sha del commit de F4>",
      "date_resolved": "2026-07-26",
      "guard_test": "tests/test_plan253_sqlite_concurrency.py",
      "evidence": "backend/services/stacky_logger.py:373-423",
      "note": "El reintento va DENTRO de _persist_batch: envolver desde afuera no ve la excepcion."
    }
```

**Cuidado:** el archivo se lee con `json.loads` (`error_fingerprints.py:22`). Sin acentos ni caracteres de control en los valores, y validar con:
```
.venv\Scripts\python.exe -c "import json;print(len(json.load(open(r'..\docs\sistema\error_fingerprints.json',encoding='utf-8'))['fingerprints']))"
```

**Test:** `test_plan253_fingerprint_registrada` dentro de `tests/test_plan253_sqlite_concurrency.py` — `load_fingerprints()` contiene los 2 ids y ambos tienen `guard_test` apuntando a un archivo que **existe**.

**Criterio binario:** el comando de validación imprime un entero (JSON válido) y el test es verde.

**Flag:** ninguna. **Impacto por runtime:** ninguno. **Trabajo del operador: ninguno.**

---

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación | Fase |
|---|---|---|
| WAL no soportado por el filesystem (share de red, `N:\`) | El `PRAGMA` no toma → `wal_status="rejected"`, warning **throttleado** (no por conexión), se sigue con `busy_timeout` + retry. **Nunca levanta.** Y el operador lo VE en el health. | F2, F7 |
| **La DB en memoria de los tests no puede ser WAL** (medido: devuelve `memory`) | Estado propio `in_memory`, sin warning; los tests de WAL corren sobre DB de **archivo** en `tmp_path`. | F0, F2 |
| **WAL rompe el backup semanal existente** (`shutil.copy2` deja fuera el `-wal`) | F2.b reemplaza la copia por `sqlite3.Connection.backup()`, con test que hoy es rojo. | F2 |
| **`synchronous=NORMAL` reduce la durabilidad** ante corte de energía (medido: el default es FULL) | Flag propia **default OFF** con la excepción dura citada. Nunca se activa sola. | §4, F2 |
| **La barrera no protege del escritor real** si se libera en `init_db()` | Se libera después de `_startup_sync` (`app.py:546-556`), en un `finally`. Test `test_carrera_real_de_arranque` lo blinda. | F3 |
| `create_app()` corre dos veces y duplica los escritores | La barrera se **re-arma** en el segundo arranque por construcción; `create_app_count` queda visible en el health. | F3, F7 |
| Un daemon queda esperando una barrera que nadie abre | `wait_for_startup_writes` devuelve `True` inmediato si la barrera **nunca se armó**; y el `finally` la abre aunque el arranque falle. | F3 |
| **El retry enmascara un bug real** | Reintenta **solo** `OperationalError` con marcador de lock; todo lo demás se re-lanza en el primer intento. Test dedicado. | F4 |
| **El retry sobre una Session abortada** vuelve a fallar (`PendingRollbackError`) | `run_with_retry` exige que `fn` abra su **propia** sesión; hay un test que verifica que el `id()` de la sesión cambia entre intentos. | F4 |
| `DELETE ... LIMIT` no compila en este SQLite | Lote por subconsulta de clave primaria; test que prohíbe la sintaxis. | F5 |
| El retry de la purga nunca se dispara porque el método se traga la excepción | El retry va **dentro** de `purge_syslog_batched`, no envolviendo `purge_old_logs`. | F5 |
| La purga borra logs que el operador quería | Retención de 90 días configurable desde la UI; la purga **retroactiva** es opt-in con backup previo y conteo a la vista. | F5, F6 |
| El backup de la compactación crece sin techo | Reusa la convención `stacky_agents-YYYYMMDD.db` y `prune_old_backups(keep=4)`; test que verifica el match con `_BACKUP_RE`. | F6 |
| `VACUUM` corrompe la DB por corte de luz | Backup obligatorio previo vía `Connection.backup()`; si falla, se aborta. | F6 |
| El `VACUUM` reporta un ahorro falso porque el `-wal` sobrevive | `PRAGMA wal_checkpoint(TRUNCATE)` obligatorio antes del `VACUUM`. | F6 |
| El watcher queda apagado si el `VACUUM` falla | `stop()`/`start_output_watcher()` en `try/finally`. | F6 |
| Recursión de logging en el retry de `stacky_logger` | Logger stdlib directo (`_std`, `stacky_logger.py:53`), patrón ya presente. | F4 |
| El warning del listener inunda el log (corre en cada conexión) | `log_throttled(..., min_interval_s=300.0)`. | F2 |
| El `.ps1` del arnés queda stale y da falso verde en Windows | Alta en **las dos** listas, con su sintaxis literal. | F0..F7 |
| Una flag queda invisible en la UI | F1 cubre los **6** lugares con su propio test. | F1 |

---

## 7. Fuera de scope

- Migrar a PostgreSQL o a cualquier motor cliente-servidor. Stacky es mono-operador; SQLite en WAL alcanza de sobra.
- Rediseñar el esquema de `system_logs` o particionarlo. **Y no crear índices**: `ix_syslog_timestamp` ya existe (`models.py:457`).
- Tocar `execution_logs` (15.220 filas, no es el problema).
- **Investigar por qué `create_app()` corre dos veces** (E10). Este plan lo **mide y lo expone** en el health; corregirlo es otro plan. Cambiar el arranque acá sería scope creep sobre la pieza más riesgosa del backend.
- **Investigar por qué el backup semanal reporta `non_sqlite_database`** (E10, líneas 32 y 166). F7 lo hace visible con un warning; el diagnóstico es otro plan.
- Las bases **del operador** que toca el comparador (`services/dbcompare_engine.py:109`, `services/live_db.py:104`): ya tienen su `connect_args={"timeout": ...}` y no son la DB de runtime de Stacky.
- La purga de **archivos** de log (`services/local_file_logging.py:180`) y el nivel de log por UI: eso es el **plan 257**, que se cuelga del `_maintenance_loop` de F5.
- Los `except Exception: pass` genéricos del backend: eso es el **plan 255**.
- La cuarentena de artefactos rechazados del intake: eso es el **plan 256**.

---

## 8. Glosario

| Término | Significado |
|---|---|
| **WAL** | *Write-Ahead Logging*, modo de journal de SQLite en el que lectores y un escritor coexisten sin bloquearse. Es **persistente en el archivo**, no por conexión. |
| **`journal_mode=delete`** | Modo por defecto (rollback journal): un escritor **bloquea a todos los lectores**. Es el modo en que está hoy la DB. |
| **`journal_mode=memory`** | Lo que devuelve una base en RAM al pedirle WAL. **No es un rechazo del filesystem** (medido). |
| **`SQLITE_BUSY`** | Error "database is locked": la DB está tomada. **Sí** lo reintenta `busy_timeout`. |
| **`SQLITE_LOCKED`** | Error "database **table** is locked": conflicto a nivel tabla. **NO** lo reintenta `busy_timeout`. Es el error de los logs. |
| **`busy_timeout`** | Milisegundos que SQLite espera ante `SQLITE_BUSY` antes de rendirse. |
| **`synchronous`** | Cuán fuerte se sincroniza a disco. `FULL` (default, `2`) es durable; `NORMAL` (`1`) es más rápido y con WAL puede perder la última transacción ante corte de energía. |
| **`VACUUM`** | Reescribe el archivo de la DB compactando el espacio libre. Toma lock exclusivo y necesita ~2× el tamaño en disco. |
| **`wal_checkpoint(TRUNCATE)`** | Vuelca el contenido del `-wal` al `.db` y trunca el sidecar. Obligatorio antes de medir o compactar. |
| **Unidad de trabajo** | Una transacción completa (`with session_scope() as session: ...`). Es lo que se reintenta; **nunca** una query suelta dentro de una sesión ya abortada. |
| **Barrera de escrituras de arranque** | Evento que los daemons esperan mientras `create_app()` está escribiendo (`init_db` + `_startup_sync`). No es una barrera "de esquema". |
| **output_watcher** | Daemon que vigila `Agentes/outputs/` y convierte los artefactos que dejan los agentes en tickets/tasks. `services/output_watcher.py`. |
| **Ratchet del arnés** | Meta-test que exige que todo `tests/test_*.py` nuevo esté declarado en `HARNESS_TEST_FILES` de `backend/scripts/run_harness_tests.sh` **y** en la lista de `run_harness_tests.ps1`. Las dos listas tienen **sintaxis distinta**. |
| **Los 6 lugares** | Lo que hace falta para que una flag exista de verdad: `Config`, `FlagSpec`, `_CATEGORY_KEYS`, `PLAIN_HELP`, `_CURATED_DEFAULTS_ON`, `_FROZEN_BOUNDS`. |
| **Excepción dura** | Una de las 4 razones por las que una flag puede nacer OFF en Stacky: (1) bypasea revisión humana, (2) es destructiva, (3) requiere un prerequisito no garantizado, (4) reduce seguridad. |

---

## 9. Orden de implementación

1. **F0** — escribir los 7 tests y verlos **rojos**. Registrar el archivo en el ratchet `.sh` **y** `.ps1`.
2. **F1** — cablear las **9** flags en los **6** lugares. `tests/test_plan253_flags_ui.py` verde y `test_harness_flags.py` sin regresiones. *(Va antes que el comportamiento: todas las fases siguientes consumen `config.STACKY_*`.)*
3. **F2** — `apply_sqlite_pragmas` + listener + estado efectivo + backup con `Connection.backup()`.
4. **F3** — barrera de **escrituras de arranque** (armar antes de `init_db()` en `app.py:369`, liberar en el `finally` de `app.py:546-556`, esperar en `scan_once`). **Es la fase que mata el error de los logs.**
5. **F4** — `run_with_retry` por unidad de trabajo + los 3 call-sites (`output_watcher.py:303`, `output_watcher.py:514`, `stacky_logger.py:373`).
6. **F5** — `_maintenance_loop` compartido + purga en lotes por subconsulta + fuente única de la retención (3 archivos: `stacky_logger.py`, `api/logs.py`, `config.py`).
7. **F6** — `confirm_token` compartido + compactación HITL reusando `db_backup`.
8. **F7** — **[ADICIÓN ARQUITECTO]** bloque `db_runtime` en `/api/diag/health` + warnings + tipo en el frontend.
9. **F8** — 2 huellas en `error_fingerprints.json`.
10. Verificación final del §10.

**Dependencias duras:** F1 antes de F2..F6 (todas leen `config.STACKY_*`). F4 antes de F5 (la purga usa `run_with_retry`). F2 antes de F6 (la compactación usa el backup arreglado). F7 después de F2/F3/F4 (lee sus estados). F0 antes de todo.

---

## 10. Definición de Hecho (DoD)

**Comportamiento**
- [ ] `PRAGMA journal_mode` sobre `backend/data/stacky_agents.db` devuelve `wal` **o** el health reporta `wal_status="rejected"` con su warning visible (fallback declarado, no silencioso).
- [ ] `PRAGMA busy_timeout` devuelve ≥ 15000.
- [ ] `PRAGMA synchronous` devuelve `2` (FULL) con la flag en su default.
- [ ] Un arranque completo del backend produce **0** líneas `database table is locked` en el log del día.
- [ ] **0** líneas `syslog failed to persist batch`.
- [ ] `wait_for_startup_writes` existe, se libera **después** de `_startup_sync` y `scan_once` la respeta; un round omitido **no** marca artefactos como procesados.
- [ ] `run_with_retry` reintenta solo locks, abre **una sesión nueva por intento**, y está aplicado en los 3 call-sites nombrados.
- [ ] La purga incremental corre sola desde `_maintenance_loop` (thread `stacky-maintenance`) y `select count(*) from system_logs` decrece.
- [ ] `STACKY_SYSLOG_RETENTION_DAYS` se resuelve en **un** lugar (`config.py`), con retrocompat de `SYSLOG_RETENTION_DAYS`, y `api/logs.py` ya no usa el import congelado.
- [ ] La compactación exige confirmación, hace backup previo **con la convención de nombre existente**, hace `wal_checkpoint(TRUNCATE)` antes del `VACUUM` y muestra el conteo real antes de confirmar.
- [ ] El backup semanal usa `Connection.backup()` y un test prueba que conserva lo commiteado en el `-wal`.

**Cableado y arnés**
- [ ] Las **9** flags de §4 existen en los **6** lugares y se pueden cambiar **desde la UI**. El conteo del DoD y el de §4 coinciden.
- [ ] Las **3** flags bool con `default=True` están en `_CURATED_DEFAULTS_ON` (`tests/test_harness_flags.py:467`).
- [ ] Las **4** flags con `min_value`/`max_value` están en `_FROZEN_BOUNDS` (`tests/test_harness_flags_bounds.py:149`) y `test_bounds_map_is_frozen` es verde.
- [ ] Las **9** tienen entrada en `PLAIN_HELP` que respeta `"Si "` sin tilde, los límites de longitud y el `JARGON_DENYLIST`.
- [ ] Los **5** archivos de test nuevos están en `HARNESS_TEST_FILES` de `run_harness_tests.sh` **y** en la lista de `run_harness_tests.ps1`, cada uno con **su** sintaxis.

**Verificación y honestidad**
- [ ] `GET /api/diag/health` devuelve el bloque `db_runtime` con `wal_status`, `busy_timeout_ms`, `startup_writes`, `lock_stats`, `create_app_count` y `maintenance`.
- [ ] Las 2 huellas están en `docs/sistema/error_fingerprints.json` y el archivo sigue siendo JSON válido.
- [ ] Los 3 runtimes (Codex CLI, Claude Code CLI, Copilot Pro) siguen corriendo **sin un solo cambio en su código** — verificable: ningún archivo `*_cli_runner.py` ni `copilot_bridge.py` aparece en el diff.
- [ ] Ningún test preexistente que pasaba antes pasa a rojo (validar **por archivo**, nunca la suite completa: contaminación cross-file conocida). Guardar el PASS/FAIL de `test_harness_flags.py`, `test_harness_flags_bounds.py`, `test_harness_flags_help.py`, `test_stacky_logger.py` **antes** de empezar y comparar al final.
- [ ] Ningún resultado se declara verde sin pegar el output real de pytest.

---

## 11. Crítica v1 -> v2 (registro del juez)

Ranking por severidad. `[M]` = verificado con una medición hecha en este árbol el 2026-07-26.

| ID | Sev | Qué | Por qué importa | Fix aplicado |
|---|---|---|---|---|
| **C1** | BLOQUEANTE | F1/F4 usaban `_env_bool(...)` en `config.py` `[M: 0 hits]` | `NameError` al importar `config` → **el backend no arranca** | Idioma real de la casa (F1, lugar 1) |
| **C2** | BLOQUEANTE | La barrera se liberaba al final de `init_db()` `[M: init_db en app.py:369 termina antes de start_output_watcher en :522; el escritor real es _startup_sync en :554, log 07-26 líneas 42 y 160 en el mismo segundo]` | La barrera sería un **no-op** y el bug sobreviviría con el plan "implementado" | Barrera de **escrituras de arranque** liberada en el `finally` de `app.py:546-556` (F3) |
| **C3** | BLOQUEANTE | F2 usaba `config.STACKY_TEST_MODE` `[M: no existe; el idioma es os.getenv]` | `AttributeError` o rama muerta | Mecanismo de **armado**; ningún escape hatch de test-mode (F3.a) |
| **C4** | BLOQUEANTE | `test_journal_mode_is_wal_after_init` sobre el engine global `[M: en la DB compartida en RAM, PRAGMA journal_mode=WAL devuelve 'memory']` | Test inverificable → se gamea (`in ("wal","memory")`) = **falso verde**; y el fallback loguea un warning falso en cada conexión | Test sobre DB de archivo + 4 estados (`ok`/`in_memory`/`rejected`/`disabled`) (F0, F2) |
| **C5** | BLOQUEANTE | `run_with_retry` envolvía `session.query(...)` `[M: el call-site está dentro de `with session_scope()`, db.py:302-312 hace rollback+close]` | Reintentar sobre una Session abortada y cerrada **no puede funcionar** | Se reintenta la **unidad de trabajo**; test que verifica sesión nueva por intento (F4) |
| **C6** | BLOQUEANTE | Lotes con `DELETE ... LIMIT` `[M: near "limit": syntax error]` + retry sobre `purge_old_logs`, que se traga la excepción (`stacky_logger.py:468`) | El código no compila y el retry es decorativo | Lote por subconsulta de PK + retry **adentro** (F5.c) |
| **C7** | IMPORTANTE | WAL rompe el backup existente `[M: db_backup.py:62 usa shutil.copy2; WAL crea -wal y -shm]`; el riesgo apuntaba a `Prepare-Publication.ps1` `[M: 0 hits de la DB]` | Backups **silenciosamente incompletos** desde el día 1 = degradación | `Connection.backup()` + test rojo hoy (F2.b) |
| **C8** | IMPORTANTE | "Configurable desde UI" con 2 de 6 lugares; categoría `infraestructura` inexistente | Flags **invisibles** y 3 meta-tests en rojo | Fase F1 completa con los 6 lugares y su test |
| **C9** | IMPORTANTE | `synchronous=NORMAL` sin flag ni mención `[M: el default es FULL(2)]` | Reduce durabilidad de la memoria del operador = viola "no degradar" | Flag propia **default OFF** con excepción dura citada (§4) |
| **C10** | IMPORTANTE | Decía "6 flags", introducía 8; ninguna con prefijo `STACKY_` | Cierre en falso del DoD | Tabla única de **9** con prefijo y retrocompat (§4) |
| **C11** | IMPORTANTE | `confirm_token` inventado `[M: 0 hits]`, duplicado en 256/258; "pausa del watcher ya existe en api/diag.py" `[M: solo scan-now y stats]` | Triple implementación + instrucción imposible de seguir | `services/confirm_token.py` compartido; `stop()`/`start_output_watcher()` nombrados (F6) |
| **C12** | IMPORTANTE | `_syslog_purge_loop`, nombre demasiado específico | El 257 crearía otro daemon | `_maintenance_loop` + registro de tareas (F5) |
| **C13** | IMPORTANTE | Backup con nombre `stacky_agents-<timestamp>.db` | No matchea `_BACKUP_RE` (`db_backup.py:14`) → el pruning nunca borra → 148 MB por compactación, para siempre | Reusa `db_backup` y su convención (F6) |
| **C14** | IMPORTANTE | Ratchet solo en el `.sh` `[M: el .ps1 tiene su propia lista en :690-723, sintaxis distinta]` | Los tests nuevos **no corren** en Windows = falso verde en la plataforma del operador | Alta en ambos, con la sintaxis literal de cada uno (F0) |
| **C15** | IMPORTANTE | Criterios "binarios" que exigían levantar el backend y grepear | No son binarios ni reproducibles por un modelo menor | Test determinista de la carrera (F3) + estado consultable (F7) |
| **C16** | MENOR | Sin huella en `error_fingerprints.json` | 72 ocurrencias en un día sin guardián de regresión | F8 |
| **C17** | MENOR | Dos detectores de "es SQLite" incompatibles `[M: el log dice non_sqlite_database en un entorno con error sqlite3]` | Divergencia muda: el operador puede no tener backups y no enterarse | Detector único + warning en el health (F7) |
| **C18** | MENOR | `create_app()` corre **dos** veces `[M: log 07-26, bloques a las 00:24:45 y 00:24:49]` | Duplica los escritores; explica el pico de 72 | Documentado, `create_app_count` en el health, investigación fuera de scope (F7, §7) |
| **C19** | MENOR | "envolver el commit del batch", "re-encolan una vez", "el frontend: panel existente" | Un modelo menor tiene que **inferir** | `archivo:línea` + símbolo exacto en cada caso |
| **C20** | MENOR | No decía que el índice ya existe `[M: models.py:457]` | Riesgo de índice duplicado sobre 367 K filas | Declarado en E9 y en §7 |

**Veredicto de v1: RECHAZADO** — 6 bloqueantes (C1-C6), cualquiera de ellos suficiente por sí solo: C1 impide arrancar el backend, C2 y C5 hacen que el fix central no arregle nada, C3 y C6 no compilan o son inertes, C4 garantiza un falso verde. Esta v2 los cierra a todos.
