# Plan 253 — Concurrencia SQLite: fin del `database table is locked`

**Estado:** PROPUESTO v1
**Serie:** Robustez desde los logs (253-258). Este es el plan **#1 por retorno**: es el único hallazgo de la auditoría que hoy, 2026-07-26, está **destruyendo trabajo del agente en cada arranque del backend**.
**Fuente:** auditoría de ~16 MB de logs reales de `Stacky Agents/backend/data/logs/` + inspección de la DB de runtime.

---

## 1. Objetivo y KPI

Eliminar la clase entera de fallos `sqlite3.OperationalError: database table is locked` poniendo la base de runtime en **WAL**, serializando la migración de arranque contra los daemons, dándole **reintento con backoff** al `output_watcher` y al sink de `SystemLog`, y **purgando automáticamente** las 367.532 filas de `system_logs` que hoy inflan la DB a 148 MB.

| KPI | Hoy (medido) | Meta |
|---|---|---|
| `database table is locked` por arranque del backend | **2 a 6** (72 el 2026-07-26) | **0** |
| Artefactos de agente descartados por lock en el primer scan | 1 por carpeta pendiente, en todo arranque | **0** |
| `syslog failed to persist batch of N events` | 4 (07-16, 07-18) | **0** |
| Filas en `system_logs` | **367.532** | **< 40.000** (retención real de 90 días) |
| Tamaño de `backend/data/stacky_agents.db` | **148.529.152 bytes** | **< 40 MB** tras el primer `VACUUM` |
| `journal_mode` de la DB de runtime | `delete` | `wal` |

---

## 2. Evidencia real (anclaje anti-alucinación)

Todo lo de abajo salió de correr greps sobre los logs; **firma + conteo + archivo de log + fecha**.

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

**El patrón es determinístico y se repite en todos los arranques.** Extracto literal de `stacky-2026-07-26.log`, líneas 42-60:

```
2026-07-26 00:24:45 INFO [stacky_agents.app] output watcher armed (interval=3.0s)
2026-07-26 00:24:45 INFO [stacky.output_watcher] output watcher started (dir=C:\desarrollo\GIT\RS\RSPACIFICO\Agentes\outputs interval=3.0s, ...)
2026-07-26 00:24:48 INFO [stacky.output_watcher] output_watcher: dir vigilado → ...\Agentes\outputs (existe=True)
2026-07-26 00:24:48 ERROR [stacky.output_watcher] output_watcher: error procesando ...\Agentes\outputs\122: (sqlite3.OperationalError) database table is locked: tickets
[SQL: SELECT tickets.id AS tickets_id, ... FROM tickets WHERE tickets.ado_id = ? LIMIT ? OFFSET ?]
[parameters: (122, 1, 0)]
```

Y otra vez, idéntico, en el arranque de las 02:00 del mismo día:

```
2026-07-26 02:00:35 INFO [stacky_agents.app] output watcher armed (interval=3.0s)
2026-07-26 02:00:38 ERROR [stacky.output_watcher] output_watcher: error procesando ...\outputs\122: (sqlite3.OperationalError) database table is locked: tickets
2026-07-26 02:00:38 ERROR [stacky.output_watcher] output_watcher: error procesando ...\outputs\160: (sqlite3.OperationalError) database table is locked: tickets
```

**El delta es siempre 3 segundos = exactamente un `interval` del watcher.** El watcher arranca, hace su primer `scan_once()` a los 3 s, y choca con la migración de arranque que todavía tiene la tabla tomada.

Traceback agregado de `stacky-2026-07-26.log` (`grep -A3 Traceback` + normalización):

```
24  File "...\backend\services\output_watcher.py", line N, in scan_once
24  File "...\backend\.venv\Lib\site-packages\sqlalchemy\engine\base.py", line N, in _exec_single_context
```

y el tipo de excepción:

```
24 sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) database table is locked: tickets
```

### E2 — La causa raíz, en tres piezas verificadas en el árbol

**(a) La DB de runtime NO está en WAL.** Medido con `PRAGMA journal_mode` sobre `Stacky Agents/backend/data/stacky_agents.db`:

```
journal_mode: ('delete',)
```

En modo `delete` (rollback journal) **un escritor bloquea a todos los lectores**. En WAL, lector y escritor coexisten. `Stacky Agents/backend/db.py` no ejecuta ningún `PRAGMA journal_mode` (0 hits de `journal_mode` y de `WAL` en el archivo).

**(b) La migración de arranque hace DDL destructivo sobre `tickets` mientras el watcher ya escanea.**

- `Stacky Agents/backend/db.py:133` → `_rebuild_tickets_table_if_needed(conn)`
- `Stacky Agents/backend/db.py:200` → `def _rebuild_tickets_table_if_needed(conn) -> None:`
- `Stacky Agents/backend/db.py:268` → `conn.execute(text("DROP TABLE tickets"))`
- `Stacky Agents/backend/db.py:269` → `conn.execute(text("ALTER TABLE tickets__new RENAME TO tickets"))`

`DROP TABLE` / `ALTER TABLE ... RENAME` toman lock exclusivo. El watcher es un thread daemon arrancado en `Stacky Agents/backend/services/output_watcher.py:179`, y su `scan_once` (`output_watcher.py:210`) lee `tickets` en `output_watcher.py:303-304` y `output_watcher.py:514-515`.

**(c) `busy_timeout` NO salva este caso, y esto es la trampa técnica del plan.** El engine se crea sin `timeout` explícito:

```python
# Stacky Agents/backend/db.py:19-31
if config.DATABASE_URL.startswith("sqlite"):
    _connect_args["check_same_thread"] = False
...
engine = create_engine(
    _effective_url, echo=False, future=True,
    connect_args=_connect_args,      # solo check_same_thread; SIN timeout
)
```

y hay **0 hits de `busy_timeout`** en todo el backend (excluyendo `.venv`).

**Pero el punto fino es otro:** el error es `database table is locked` = **`SQLITE_LOCKED`**, no `database is locked` = `SQLITE_BUSY`. `busy_timeout` **solo reintenta `SQLITE_BUSY`**; `SQLITE_LOCKED` retorna de inmediato. Por eso **subir el timeout no arregla nada por sí solo**: hace falta WAL + serializar el arranque + reintento explícito en el llamador. Quien implemente esto debe entender esta distinción o va a "arreglar" el bug sin arreglarlo.

### E3 — El mismo lock rompe el sink de logs de la UI

```
4 ERROR [stacky.syslog] syslog failed to persist batch of 1 events
```
(3 en `stacky-2026-07-16.log`, 1 en `stacky-2026-07-18.log`). Contexto literal de `stacky-2026-07-16.log`:

```
2026-07-16 01:23:14 ERROR [stacky.syslog] syslog failed to persist batch of 1 events
Traceback (most recent call last):
  File "...\.venv\Lib\site-packages\sqlalchemy\engine\base.py", line 1967, in _exec_single_context
```

Mismo `_exec_single_context`: eventos de log del operador **perdidos para siempre** por contención de SQLite.

### E4 — La DB creció a 148 MB porque la purga existe pero nadie la llama

Conteo real de filas por tabla en `backend/data/stacky_agents.db`:

| Filas | Tabla |
|---|---|
| **367.532** | `system_logs` |
| 15.220 | `execution_logs` |
| 1.921 | `ticket_state_history` |
| 266 | `tickets` |
| 211 | `ticket_status_events` |
| 167 | `agent_executions` |

`system_logs` es el **99,3 %** de las filas. Tamaño del archivo: `148.529.152` bytes (`page_count=36263 * page_size=4096` reporta 148 MB). El deploy, que se usa menos, pesa `12.038.144` bytes: la diferencia es puro `system_logs`.

Y la purga **ya está escrita, solo que huérfana**:

- `Stacky Agents/backend/services/stacky_logger.py:36` → comentario literal: `Call logger.purge_old_logs() periodically or via DELETE /api/logs/purge.`
- `Stacky Agents/backend/services/stacky_logger.py:62` → `RETENTION_DAYS = int(os.getenv("SYSLOG_RETENTION_DAYS", "90"))`
- `Stacky Agents/backend/services/stacky_logger.py:454` → `def purge_old_logs(self, days: int = RETENTION_DAYS) -> int:`

Nadie la llama periódicamente. La retención de 90 días es **declarativa, no efectiva**. Cada `INSERT` a una tabla de 367 K filas en modo `delete` prolonga la ventana de lock que mata al watcher: E4 **causa** E1.

### E5 — Cero mitigación en el llamador

En `Stacky Agents/backend/services/output_watcher.py`: **0 hits** de `retry`, `backoff`, `sleep`, `OperationalError`. Los únicos handlers son `except Exception` genéricos en `output_watcher.py:240-242` y `output_watcher.py:261-263`, que hacen `logger.exception` + `stats.errors += 1` y **descartan el round completo**. Como el fallo impide cachear el mtime, el archivo se reintenta en el siguiente poll → **loop de fallos en vez de recuperación**.

---

## 3. Principios y guardarraíles (obligatorios)

- **Human-in-the-loop:** el `VACUUM` y la purga inicial retroactiva son **destructivos/irreversibles** → van detrás de confirmación explícita del operador en la UI. La purga *incremental* por retención no lo es y va automática.
- **Mono-operador sin auth:** no se introduce ningún permiso, rol ni chequeo de identidad.
- **Paridad de 3 runtimes:** este plan es de infraestructura de datos, por debajo del runtime. Codex CLI, Claude Code CLI y GitHub Copilot Pro se benefician **idénticamente** y ninguno se toca. F1 declara el fallback para el caso de que el filesystem no soporte WAL.
- **Cero trabajo extra al operador:** F0-F3 son invisibles y automáticas. Lo único visible es un botón nuevo *"Compactar base"* que el operador usa **si quiere**.
- **No degradar:** WAL es más rápido, no más lento. Todo cambio es backward-compatible: una DB en WAL la sigue abriendo cualquier SQLite ≥ 3.7.
- **Flags nuevas default ON**, salvo la de compactación destructiva (default OFF, cita la excepción dura #2).
- **Toda flag configurable desde la UI**, no solo por env var.

---

## 4. Fases

### F0 — Test que reproduce el lock (rojo primero)

**Objetivo:** dejar en el arnés una prueba que hoy falla por la misma razón que los logs, para que el fix no pueda ser un falso verde.

**Archivo a crear:** `Stacky Agents/backend/tests/test_plan253_sqlite_concurrency.py`

**Casos exactos:**

1. `test_journal_mode_is_wal_after_init` — abre el engine de `db.py` y asserta `PRAGMA journal_mode == "wal"`. **Hoy falla** (devuelve `delete`).
2. `test_busy_timeout_is_configured` — asserta que `PRAGMA busy_timeout >= 15000`. **Hoy falla** (no se configura).
3. `test_reader_survives_concurrent_writer` — con una DB temporal: thread A abre transacción de escritura sobre `tickets` y duerme 0,5 s; thread B lee `tickets`. Asserta que B **no** levanta `OperationalError`. **Hoy falla** en modo `delete`.
4. `test_ddl_migration_does_not_race_with_daemons` — asserta que el símbolo nuevo `db.wait_for_schema_ready(timeout_s=...)` existe y que devuelve `True` después de `init_db()`. **Hoy falla** (no existe).
5. `test_run_with_retry_reintenta_solo_operational_error` — el helper nuevo `db.run_with_retry` reintenta ante `OperationalError` con mensaje `locked`, y **NO** reintenta ante `ValueError` (lo re-lanza al primer intento). Verifica el conteo de intentos con un contador.

**Registro obligatorio en el ratchet:** agregar la línea `tests/test_plan253_sqlite_concurrency.py` a `HARNESS_TEST_FILES` en `Stacky Agents/backend/scripts/run_harness_tests.sh`, o `test_harness_ratchet_meta.py` se pone rojo (ver `Stacky Agents/backend/tests/test_harness_ratchet_meta.py:13`).

**Comando exacto:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan253_sqlite_concurrency.py -v
```

**Criterio binario:** los 5 tests existen y **fallan** (o erran por símbolo faltante) antes de F1. Si alguno pasa antes de F1, el test está mal escrito.

**Flag:** ninguna (es test).
**Impacto por runtime:** ninguno. **Trabajo del operador: ninguno.**

---

### F1 — WAL + `busy_timeout` en el engine

**Objetivo:** que un escritor deje de bloquear a los lectores.

**Archivo a editar:** `Stacky Agents/backend/db.py` (zona de creación del engine, `db.py:19-31`).

**Cambio exacto:** agregar `timeout` a `connect_args` y un listener `PRAGMA` que corra en **cada** conexión nueva del pool:

```python
# db.py — dentro del bloque `if config.DATABASE_URL.startswith("sqlite"):`
_connect_args["check_same_thread"] = False
_connect_args["timeout"] = config.SQLITE_BUSY_TIMEOUT_MS / 1000.0   # NUEVO

# ... después de create_engine(...) ...
from sqlalchemy import event

@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _rec):
    """Plan 253 F1 — WAL + busy_timeout en TODA conexión del pool."""
    if not config.DATABASE_URL.startswith("sqlite"):
        return
    cur = dbapi_conn.cursor()
    try:
        if config.SQLITE_WAL_ENABLED:
            cur.execute("PRAGMA journal_mode=WAL")
            mode = (cur.fetchone() or [""])[0]
            if str(mode).lower() != "wal":
                # Fallback explícito: filesystem de red / share que no soporta WAL.
                logger.warning(
                    "sqlite: WAL rechazado por el filesystem (journal_mode=%s) — "
                    "se sigue en modo %s con busy_timeout=%dms", mode, mode,
                    config.SQLITE_BUSY_TIMEOUT_MS)
        cur.execute(f"PRAGMA busy_timeout={int(config.SQLITE_BUSY_TIMEOUT_MS)}")
        cur.execute("PRAGMA synchronous=NORMAL")
    finally:
        cur.close()
```

**Símbolos nuevos exactos en `Stacky Agents/backend/config.py`** (dentro de `class Config`, que arranca en `config.py:60`):

```python
SQLITE_WAL_ENABLED = _env_bool("SQLITE_WAL_ENABLED", True)
SQLITE_BUSY_TIMEOUT_MS = int(os.getenv("SQLITE_BUSY_TIMEOUT_MS", "15000"))
```

**Nota para quien implemente:** WAL **no** cubre `SQLITE_LOCKED` por DDL. F1 es necesaria pero **no suficiente**; F2 y F3 completan el fix. No cerrar el plan en F1.

**Casos borde:**
- Filesystem que no soporta WAL (share de red): el `PRAGMA` devuelve el modo viejo en vez de fallar → se loguea el warning y se continúa. **No se levanta excepción nunca.**
- `DATABASE_URL` no-SQLite: el listener retorna sin hacer nada.
- DB ya en WAL: el `PRAGMA` es idempotente.

**Tests:** `test_journal_mode_is_wal_after_init`, `test_busy_timeout_is_configured`, `test_reader_survives_concurrent_writer` de F0 pasan a **verde**.

**Criterio binario:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan253_sqlite_concurrency.py -k "wal or busy or reader" -v
```
3 verdes, y
```
.venv\Scripts\python.exe -c "import sqlite3;print(sqlite3.connect('data/stacky_agents.db').execute('pragma journal_mode').fetchone())"
```
imprime `('wal',)` tras un arranque del backend.

**Flag:** `SQLITE_WAL_ENABLED`, **default ON**. No cae en ninguna de las 4 excepciones duras: no bypasea revisión humana, no es destructiva, no requiere prerequisito nuevo (WAL es nativo de SQLite desde 3.7 / Python 3.x), y no reduce seguridad. Es un kill-switch de emergencia por si un filesystem exótico se porta mal.
**Configurable desde UI:** sí — se registra en el panel de flags (categoría `infraestructura`) y en `Stacky Agents/backend/api/global_config.py`.

**Impacto por runtime:** ninguno de los 3 se toca; los 3 dejan de perder artefactos por igual.
**Trabajo del operador: ninguno.**

---

### F2 — Serializar la migración de arranque contra los daemons

**Objetivo:** que ningún daemon toque `tickets` antes de que el DDL de arranque termine. Esto es lo que mata al `SQLITE_LOCKED` que WAL no cubre.

**Archivos a editar:**
1. `Stacky Agents/backend/db.py` — agregar la barrera.
2. `Stacky Agents/backend/services/output_watcher.py` — esperarla antes del primer scan.

**Símbolos nuevos exactos en `db.py`:**

```python
import threading
_SCHEMA_READY = threading.Event()          # módulo-level, junto al engine

def wait_for_schema_ready(timeout_s: float = 30.0) -> bool:
    """Plan 253 F2 — bloquea hasta que el DDL de arranque terminó.

    Devuelve True si el esquema está listo, False si expiró el timeout.
    NUNCA levanta: un timeout degrada al comportamiento actual (intentar y
    reintentar), no cuelga el proceso.
    """
    return _SCHEMA_READY.wait(timeout=timeout_s)

def mark_schema_ready() -> None:
    _SCHEMA_READY.set()
```

`mark_schema_ready()` se llama **al final** de `init_db()`, después de `_rebuild_tickets_table_if_needed(conn)` (`db.py:133`) y de cualquier otro DDL, en un `finally` para que un fallo de migración no deje a los daemons colgados 30 s.

**Cambio en `output_watcher.py`:** al principio de `scan_once` (`output_watcher.py:210`):

```python
def scan_once(self) -> dict:
    """Una pasada manual. Retorna dict con counts del round."""
    from db import wait_for_schema_ready
    if not wait_for_schema_ready(timeout_s=config.SQLITE_SCHEMA_WAIT_S):
        logger.warning(
            "output_watcher: esquema no listo tras %ss — se omite este round "
            "SIN marcar los artefactos como procesados",
            config.SQLITE_SCHEMA_WAIT_S)
        self.stats.skipped_not_ready = getattr(self.stats, "skipped_not_ready", 0) + 1
        return {"skipped_schema_not_ready": True}
    self.stats.scans += 1
    ...
```

**Símbolo nuevo en `config.py`:** `SQLITE_SCHEMA_WAIT_S = float(os.getenv("SQLITE_SCHEMA_WAIT_S", "30"))`

**Regla dura:** al omitir el round **NO** se cachea el mtime ni se marca nada como procesado. El artefacto se procesa en el poll siguiente, íntegro. Ese es justamente el bug que hoy pierde trabajo.

**Casos borde:**
- Migración que falla: el `finally` setea el evento igual → los daemons siguen con el comportamiento de hoy en vez de colgarse.
- `scan_once` invocado desde el endpoint manual `output_watcher_scan_now` (`Stacky Agents/backend/api/diag.py`): mismo path, misma espera. Consistente.
- Tests que usan una DB in-memory sin `init_db()`: la barrera expiraría. Por eso el modo test (`STACKY_TEST_MODE`) debe llamar `mark_schema_ready()` en el fixture de DB, o `wait_for_schema_ready` debe devolver `True` inmediato cuando `config.STACKY_TEST_MODE` está activo. **Implementar la segunda opción**, es la que no obliga a tocar cada fixture.

**Tests:** `test_ddl_migration_does_not_race_with_daemons` de F0 pasa a verde. Sumar:
- `test_scan_once_omite_round_si_esquema_no_listo` — con el evento sin setear y `SQLITE_SCHEMA_WAIT_S=0.1`, `scan_once` devuelve `{"skipped_schema_not_ready": True}` y **no** incrementa `stats.scans`.
- `test_scan_once_no_cachea_mtime_al_omitir` — tras un round omitido, el mismo archivo se vuelve a intentar en el round siguiente.

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan253_sqlite_concurrency.py -v
```
todo verde, **y** el arranque del backend ya no produce ninguna línea `database table is locked` (verificable con `grep -c "database table is locked"` sobre el log del día, que debe dar `0`).

**Flag:** ninguna nueva de comportamiento; `SQLITE_SCHEMA_WAIT_S` es un tuning numérico expuesto en la UI.
**Impacto por runtime:** ninguno.
**Trabajo del operador: ninguno.**

---

### F3 — Reintento con backoff donde el lock duele

**Objetivo:** que un lock transitorio (los que WAL no elimina: DDL, checkpoint, `VACUUM`) no descarte trabajo.

**Archivo a editar:** `Stacky Agents/backend/db.py` (helper nuevo) y **3 call-sites**.

**Símbolo nuevo exacto en `db.py`:**

```python
_LOCK_MARKERS = ("database is locked", "database table is locked")

def run_with_retry(fn, *, attempts: int = 3, base_delay_s: float = 0.25,
                   label: str = ""):
    """Plan 253 F3 — reintenta `fn()` ante lock de SQLite, con backoff.

    Reintenta SOLO si es OperationalError cuyo mensaje contiene un marcador de
    lock. Cualquier otra excepción se re-lanza en el primer intento (no se
    enmascaran bugs). Tras agotar los intentos, re-lanza la última.
    """
    from sqlalchemy.exc import OperationalError
    last = None
    for i in range(attempts):
        try:
            return fn()
        except OperationalError as exc:
            msg = str(exc).lower()
            if not any(m in msg for m in _LOCK_MARKERS):
                raise
            last = exc
            if i < attempts - 1:
                time.sleep(base_delay_s * (2 ** i))   # 0.25s, 0.5s
                logger.warning("db lock en %s — reintento %d/%d",
                               label or "operación", i + 2, attempts)
    raise last
```

**Los 3 call-sites exactos a envolver:**

1. `Stacky Agents/backend/services/output_watcher.py:303-304` — el `session.query(Ticket).filter(Ticket.ado_id == ado_id)` de `_process_mode_b`. Es **el query literal que aparece en el traceback de los logs**.
2. `Stacky Agents/backend/services/output_watcher.py:514-515` — el equivalente en `_process_mode_a` (def en `output_watcher.py:402`).
3. `Stacky Agents/backend/services/stacky_logger.py` — el `flush` del batch que produce `syslog failed to persist batch of N events` (E3). Envolver el commit del batch. **Regla:** si tras 3 intentos falla, los eventos se **re-encolan** una vez en vez de descartarse; solo se descartan al segundo fracaso, y ahí se loguea a `error` con el conteo exacto.

**Anti-recursión obligatoria:** `stacky_logger` alimenta el log; su propio reintento **no** debe loguear a través de sí mismo. Usar el logger stdlib directo (el archivo ya tiene el patrón `_std.exception` en `stacky_logger.py:469`).

**Tests:** `test_run_with_retry_reintenta_solo_operational_error` de F0 pasa a verde. Sumar:
- `test_run_with_retry_agota_y_relanza` — 3 intentos fallidos → levanta `OperationalError`.
- `test_run_with_retry_no_reintenta_valueerror` — 1 solo intento.
- `test_syslog_reencola_batch_antes_de_descartar` — un batch que falla una vez se persiste en el segundo intento; el conteo de eventos perdidos queda en 0.

**Criterio binario:** `pytest tests/test_plan253_sqlite_concurrency.py -v` verde, y `grep -c "syslog failed to persist"` sobre el log del día siguiente al deploy da `0`.

**Flag:** `SQLITE_LOCK_RETRY_ENABLED`, **default ON**. No cae en excepciones duras (no bypasea revisión, no es destructiva, sin prerequisito, no baja seguridad).
**Impacto por runtime:** ninguno de los 3 cambia. **Trabajo del operador: ninguno.**

---

### F4 — Purga automática de `system_logs` (la que ya existe pero nadie llama)

**Objetivo:** hacer **efectiva** la retención de 90 días que hoy es solo declarativa, y con eso desinflar la DB y acortar la ventana de lock.

**Archivos a editar:**
1. `Stacky Agents/backend/app.py` — enganchar la purga a un loop ya existente.
2. `Stacky Agents/backend/config.py` — flag + intervalo.

**Cambio exacto:** `app.py` ya corre loops de mantenimiento (`_digest_loop`, `_memory_review_sweep_loop`). **Reusar ese patrón, no crear un daemon nuevo.** Agregar:

```python
def _syslog_purge_loop():
    """Plan 253 F4 — purga incremental de system_logs por retención."""
    from services.stacky_logger import get_logger
    while True:
        try:
            time.sleep(config.SYSLOG_PURGE_INTERVAL_S)
            if not config.SYSLOG_AUTO_PURGE_ENABLED:
                continue
            n = get_logger().purge_old_logs()      # stacky_logger.py:454
            if n:
                logger.info("syslog purge: %d filas eliminadas (retención %dd)",
                            n, config.SYSLOG_RETENTION_DAYS)
        except Exception:
            logger.exception("syslog purge loop: fallo no fatal")
```

**Símbolos nuevos exactos en `config.py`:**
```python
SYSLOG_AUTO_PURGE_ENABLED = _env_bool("SYSLOG_AUTO_PURGE_ENABLED", True)
SYSLOG_PURGE_INTERVAL_S = int(os.getenv("SYSLOG_PURGE_INTERVAL_S", "21600"))  # 6 h
SYSLOG_RETENTION_DAYS = int(os.getenv("SYSLOG_RETENTION_DAYS", "90"))
```

**Nota de deuda existente:** `stacky_logger.py:62` ya define `RETENTION_DAYS` leyendo `SYSLOG_RETENTION_DAYS`. **No duplicar la lectura**: `stacky_logger` debe pasar a leer `config.SYSLOG_RETENTION_DAYS` para que exista **una sola** fuente de verdad y la UI pueda cambiarla. Cuidado con el gotcha conocido del repo: el default efectivo es el de `config.py`, no el del módulo.

**Cota de seguridad:** la purga incremental **no** es destructiva en el sentido del riel (borra solo lo que la retención declarada ya consideraba descartable) → default ON. La purga **retroactiva** de las 367.532 filas históricas es otra cosa y va en F5.

**Casos borde:**
- Purga que corre mientras el watcher escanea: por eso F4 va **después** de F1/F3 (WAL + retry ya la absorben).
- `purge_old_logs` con lock: envolver en `run_with_retry(label="syslog purge")` de F3.
- Primera corrida sobre 367 K filas: borrar en **lotes de 5.000** con commit por lote, no en un `DELETE` monolítico que tomaría lock varios segundos. Esto es un requisito, no una sugerencia.

**Tests:** archivo `Stacky Agents/backend/tests/test_plan253_syslog_purge.py` (agregar al ratchet):
- `test_purge_borra_solo_lo_mas_viejo_que_retencion` — siembra filas de 100 y 10 días; solo se borra la de 100.
- `test_purge_en_lotes_no_excede_batch_size` — con 12.000 filas viejas y batch 5.000, se hacen 3 commits.
- `test_purge_respeta_flag_off` — con `SYSLOG_AUTO_PURGE_ENABLED=False`, 0 filas borradas.
- `test_retention_days_sale_de_config_no_del_modulo` — cambiar `config.SYSLOG_RETENTION_DAYS` cambia el comportamiento (blinda la fuente única).

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan253_syslog_purge.py -v
```
4 verdes, y tras 6 h de backend levantado `select count(*) from system_logs` bajó respecto del arranque.

**Flag:** `SYSLOG_AUTO_PURGE_ENABLED`, **default ON**, expuesta en UI junto a `SYSLOG_RETENTION_DAYS` (numérico) y `SYSLOG_PURGE_INTERVAL_S`.
**Impacto por runtime:** ninguno. **Trabajo del operador: ninguno.**

---

### F5 — Compactación asistida (HITL, la única pieza destructiva)

**Objetivo:** darle al operador un botón para recuperar los ~110 MB que hoy ocupa el histórico, **sin que el sistema lo haga a sus espaldas**.

**Archivos a crear/editar:**
1. `Stacky Agents/backend/api/diag.py` — endpoint nuevo `POST /api/diag/db/compact`.
2. `Stacky Agents/backend/services/db_maintenance.py` — **archivo nuevo**, lógica pura.
3. Frontend: panel de diagnóstico existente — botón *"Compactar base"*.

**Símbolos nuevos exactos en `services/db_maintenance.py`:**
```python
def db_stats() -> dict:
    """{'path','size_bytes','page_count','page_size','journal_mode',
        'rows_by_table': {...}, 'purgeable_rows': int, 'estimated_reclaim_bytes': int}"""

def compact_db(*, confirm_token: str, purge_retroactive: bool) -> dict:
    """VACUUM + (opcional) purga retroactiva. Exige confirm_token válido."""
```

**Contrato HITL, no negociable:**
1. `GET /api/diag/db/stats` devuelve el diagnóstico **y** un `confirm_token` efímero (TTL 120 s) que describe exactamente qué se va a hacer (`rows_to_delete`, `bytes_to_reclaim`).
2. La UI muestra el número real: *"Se eliminarán 327.481 filas de system_logs anteriores al 2026-04-27 y se recuperarán ~108 MB. Esto no se puede deshacer."*
3. `POST /api/diag/db/compact` **exige** ese `confirm_token`. Sin token → `409` y no se toca nada.
4. Antes del `VACUUM`, copia de seguridad automática a `backend/data/backups/stacky_agents-<timestamp>.db` usando la API `sqlite3.Connection.backup()` (consistente, no `shutil.copy`). Si la copia falla, **se aborta** y no se compacta.

**Casos borde:**
- `VACUUM` toma lock exclusivo de toda la DB por segundos: el endpoint debe primero **pausar** el output_watcher (ya existe el control en `api/diag.py`), compactar, y reanudarlo. Documentar el orden exacto.
- Disco sin espacio para el backup + el temporal del `VACUUM` (necesita ~2× el tamaño): chequear `shutil.disk_usage` antes y abortar con mensaje claro si no alcanza.
- `VACUUM` no funciona dentro de una transacción: usar una conexión aparte con `isolation_level=None`.

**Tests:** `Stacky Agents/backend/tests/test_plan253_db_compact.py` (agregar al ratchet):
- `test_compact_sin_token_devuelve_409`
- `test_compact_con_token_expirado_devuelve_409`
- `test_compact_hace_backup_antes_de_vacuum`
- `test_compact_aborta_si_falla_el_backup` — el archivo original queda intacto.
- `test_compact_aborta_si_no_hay_espacio_en_disco`
- `test_db_stats_reporta_journal_mode_y_filas_por_tabla`

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan253_db_compact.py -v
```
6 verdes. Y manualmente: el botón muestra el conteo real antes de pedir confirmación.

**Flag:** `DB_COMPACT_ENABLED`, **default OFF**. Cita la **excepción dura #2: destructiva/irreversible** (borra filas históricas y reescribe el archivo de la DB del operador). El operador la prende desde la UI cuando quiera compactar.
**Impacto por runtime:** ninguno; es mantenimiento de infraestructura.
**Trabajo del operador:** opt-in explícito, un clic, con el número exacto a la vista. Es la excepción justificada al "cero trabajo".

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| WAL no soportado por el filesystem (share de red, `N:\`) | F1 detecta que el `PRAGMA` no tomó, loguea warning y **sigue** con `busy_timeout`. Nunca levanta. |
| WAL deja archivos `-wal`/`-shm` que el empaquetado/backup no copia | Documentar en el plan y en `db_maintenance`: el backup usa `Connection.backup()`, que consolida el WAL. Verificar que `Prepare-Publication.ps1` no copie un `.db` sin su `-wal`. |
| `wait_for_schema_ready` cuelga un daemon 30 s si la migración falla | El `mark_schema_ready()` va en `finally`. Además el timeout **degrada** (devuelve `False`), no bloquea para siempre. |
| El retry enmascara un bug real | `run_with_retry` reintenta **solo** `OperationalError` con marcador de lock; todo lo demás se re-lanza en el primer intento. Hay un test dedicado. |
| La purga borra logs que el operador quería | Retención de 90 días, configurable desde la UI, y la purga retroactiva es opt-in con backup previo y conteo a la vista. |
| `VACUUM` corrompe la DB por corte de luz | Backup obligatorio previo vía `Connection.backup()`; si falla, se aborta. |
| Recursión de logging en el retry de `stacky_logger` | Usar el logger stdlib directo, patrón ya presente en `stacky_logger.py:469`. |

---

## 6. Fuera de scope

- Migrar a PostgreSQL o a cualquier motor cliente-servidor. Stacky es mono-operador; SQLite en WAL alcanza de sobra.
- Rediseñar el esquema de `system_logs` o particionarlo.
- Tocar `execution_logs` (15.220 filas, no es el problema).
- Las bases **del operador** que toca el comparador (`services/dbcompare_engine.py:109`, `services/live_db.py:104`): esas ya tienen su `connect_args={"timeout": ...}` y no son la DB de runtime de Stacky.
- Los `except Exception: pass` genéricos del backend: eso es el **plan 255**.

---

## 7. Glosario

| Término | Significado |
|---|---|
| **WAL** | *Write-Ahead Logging*, modo de journal de SQLite en el que lectores y un escritor coexisten sin bloquearse. |
| **`journal_mode=delete`** | Modo por defecto (rollback journal): un escritor **bloquea a todos los lectores**. Es el modo en que está hoy la DB. |
| **`SQLITE_BUSY`** | Error "database is locked": la DB está tomada. **Sí** lo reintenta `busy_timeout`. |
| **`SQLITE_LOCKED`** | Error "database **table** is locked": conflicto a nivel tabla, típicamente por DDL. **NO** lo reintenta `busy_timeout`. Es el error de los logs. |
| **`busy_timeout`** | Milisegundos que SQLite espera ante `SQLITE_BUSY` antes de rendirse. |
| **`VACUUM`** | Reescribe el archivo de la DB compactando el espacio libre. Toma lock exclusivo y necesita ~2× el tamaño en disco. |
| **output_watcher** | Daemon de Stacky que vigila `Agentes/outputs/` y convierte los artefactos que dejan los agentes en tickets/tasks. `services/output_watcher.py`. |
| **Ratchet del arnés** | Meta-test que exige que todo `tests/test_*.py` nuevo esté declarado en `HARNESS_TEST_FILES` de `backend/scripts/run_harness_tests.sh`. |
| **Excepción dura** | Una de las 4 razones por las que una flag puede nacer OFF en Stacky: bypasea revisión humana, es destructiva, requiere un prerequisito no garantizado, o reduce seguridad. |

---

## 8. Orden de implementación

1. **F0** — escribir los 5 tests y verlos **rojos**. Registrar el archivo en `HARNESS_TEST_FILES`.
2. **F1** — WAL + `busy_timeout` + flags en `config.py`. 3 tests a verde.
3. **F2** — barrera `wait_for_schema_ready` + espera en `scan_once`. Es la fase que mata el error de los logs.
4. **F3** — `run_with_retry` + los 3 call-sites (2 en `output_watcher.py`, 1 en `stacky_logger.py`).
5. **F4** — loop de purga incremental, en lotes de 5.000, con fuente única de `SYSLOG_RETENTION_DAYS`.
6. **F5** — endpoint + servicio de compactación con token de confirmación, backup previo y botón en la UI.
7. Exponer las 6 flags nuevas en el panel de flags y en `api/global_config.py`.
8. Verificación final: levantar el backend y confirmar `grep -c "database table is locked"` = **0** sobre el log del día.

---

## 9. Definición de Hecho (DoD)

- [ ] `PRAGMA journal_mode` sobre `backend/data/stacky_agents.db` devuelve `wal`.
- [ ] `PRAGMA busy_timeout` devuelve ≥ 15000.
- [ ] Un arranque completo del backend produce **0** líneas `database table is locked` en el log del día.
- [ ] **0** líneas `syslog failed to persist batch`.
- [ ] `wait_for_schema_ready` existe y `scan_once` la respeta; un round omitido **no** marca artefactos como procesados.
- [ ] `run_with_retry` reintenta solo locks y está aplicado en los 3 call-sites nombrados.
- [ ] La purga incremental corre sola y `select count(*) from system_logs` decrece.
- [ ] `SYSLOG_RETENTION_DAYS` se lee de `config.py` únicamente (un solo lugar).
- [ ] La compactación exige `confirm_token`, hace backup previo y muestra el conteo real antes de confirmar.
- [ ] Los 3 archivos de test nuevos están en `HARNESS_TEST_FILES` de `backend/scripts/run_harness_tests.sh`.
- [ ] Las 6 flags nuevas aparecen y se pueden cambiar **desde la UI**.
- [ ] Los 3 runtimes (Codex CLI, Claude Code CLI, Copilot Pro) siguen corriendo sin cambios en su código.
- [ ] Ningún test preexistente que pasaba antes pasa a rojo (validar **por archivo**, nunca la suite completa: contaminación cross-file conocida).
