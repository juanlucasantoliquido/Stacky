# Plan 258 — Telemetría veraz: ledgers sin fixtures ni ciclos abiertos

**Estado:** CRITICADO v2
**Versión:** v1 -> v2 (juez adversarial + súper arquitecto)
**Serie:** Robustez desde los logs (253-258). Plan **#6 por retorno** y **cierre de la serie**.
**Fuente:** auditoría de los ledgers JSONL de runtime + los logs de aplicación, **re-verificada contra el árbol de trabajo**.

> La auditoría abrió los ledgers JSONL que deberían darle al operador visibilidad de lo que la UI no muestra. Resultado confirmado: **`ci_runs.jsonl` tiene 8 de 8 líneas de fixture de test** y **`env_applies.jsonl` tiene 10 de 10 líneas escritas por pytest**. La telemetría de Stacky hoy no es una fuente de verdad: es un archivo mezclado.
>
> **Corrección de v1:** la contaminación del **log de la aplicación** ya está **cerrada** desde el 2026-07-16 (plan 145). El v1 la presentaba como agujero vivo y proponía una F5 que habría **regresado** ese fix y puesto dos tests en rojo. Ver CHANGELOG C1.

---

## 0. CHANGELOG v1 -> v2

Hallazgos del juez resueltos en esta versión:

- **C1 (BLOQUEANTE) — F5 estaba escrita contra una foto vieja del repo.** `install_file_log_handler` **ya aísla** el log en test-mode desde el plan 145 (commit `f00f161f`, **2026-07-16 02:05:19 -0300**): `services/local_file_logging.py:165` hace `base_dir = _test_logs_dir() if _test_mode() else logs_dir()`. Las 13 líneas contaminadas son **todas anteriores** a ese commit. El cambio propuesto por el v1 (`def install_file_log_handler(*, force: bool = False) -> bool` con `return False`) **cambiaba firma, tipo de retorno y contrato**, y ponía **ROJOS** los dos tests de `tests/test_plan145_pytest_log_isolation.py`. **F5 reescrita**: sin tocar la firma, reducida a guard de conftest + test de regresión con ventana de fecha.
- **C2 (BLOQUEANTE) — F3 reinventaba una función que existe y ya está cableada.** `close_ci_run` es, en la práctica, `ci_run_ledger.update_run_status` (`services/ci_run_ledger.py:103`), **ya enganchada al poller de CI** en `api/ci.py:206-218` bajo `STACKY_CI_RUN_LEDGER_ENABLED` (default **`true`**, `config.py:1647`). **F3 reescrita**: reusa `update_run_status`, corrige su bug real de reconciliación y aporta solo lo que falta (huérfanos + endpoint).
- **C3 (BLOQUEANTE) — la premisa "el ledger es append-only" es falsa en este repo.** `append_run` (`ci_run_ledger.py:71-81`) hace *leer todo -> append -> reescribir todo* con `_write_rows` (`:50-58`, `tmp.replace(path)`) bajo `_LOCK`, y aplica retención `MAX_ROWS = 500`. `env_apply_ledger` calca el patrón. Y el "ledger de publicación" que el v1 citaba como precedente **no es JSONL**: `services/publish_ledger.py` es **DB-backed**. **F1/F3 reescritas** sobre el mecanismo real.
- **C4 (BLOQUEANTE) — el campo `env` se perdía en silencio.** `_clean_entry` (`ci_run_ledger.py:60-68`) es una **ALLOWLIST estricta**: `out = {k: entry.get(k) for k in ENTRY_FIELDS}`. `ENTRY_FIELDS` (`:23-26`) no tiene `env` ni `schema_version` -> el writer los **descarta**. El KPI "procedencia 0 -> 6" era inalcanzable. **F1 reescrita**: extender `ENTRY_FIELDS` por ledger, preservando el guard anti-secretos.
- **C5 (BLOQUEANTE) — `config.STACKY_TEST_MODE` no existe.** 0 ocurrencias en `backend/config.py`. El idioma real es `os.getenv("STACKY_TEST_MODE", "").lower() in {"1","true","yes"}`, replicado por módulo (`local_file_logging.py:61`, `error_fingerprints.py:59`, `lifecycle_log.py:46`, `output_watcher.py:986`). El v1 citaba `local_file_logging.py:61` como si fuera un atributo de `Config`, y es una **función**. **Corregido en F1 y F5.**
- **C6 (BLOQUEANTE) — el inventario de ledgers no cerraba.** `LEDGER_NAMES` tenía 6 nombres: uno (`publish_ledger`) **no es JSONL**, otro (`telemetry_harvest`) **nunca se escribe** por un `NameError` vivo (`services/telemetry_harvest.py:503` usa `data_dir()` sin importarlo; es el bug (C) del **plan 255**), y **faltaba `build_runs.jsonl`** (existe, 4.975 bytes, escrito por `services/solution_builder.py`). **Inventario reconciliado en E4 y F1.**
- **C7 (IMPORTANTE) — `read_events(..., env="prod")` por default ocultaba datos reales.** Con toda la historia en `unknown`, el default `prod` escondía **436 líneas** de `config_transfer_events` y **9** de `db_query_audit`. **Default cambiado a `("prod","unknown")`**; `env="prod"` pasa a ser opt-in explícito.
- **C8 (IMPORTANTE) — contradicción interna F1 vs F3.** `REQUIRED_KEYS["ci_runs"]` exigía `triggered_at`, que una línea de cierre no tiene: el validador de F1 habría rechazado la línea de cierre de F3. **Disuelto**: ya no hay línea de cierre (C2); y `REQUIRED_KEYS` se valida **por `event_type`**.
- **C9 (IMPORTANTE) — `_TEST_MARKERS` por substring global era agresivo.** `"pytest-"`, `"test_reaper"`, `"DB exploded"` pueden aparecer en texto libre legítimo (una `query` auditada, una ruta, un título de ticket); `"newsha"`/`"myproject"` son de **un** fixture y no generalizan. **Reescrito**: inferencia **por campo** con reglas nombradas, no substring sobre cualquier valor.
- **C10 (IMPORTANTE) — la "escritura atómica de una línea < 4 KB" no es garantía**, y además **degradaba** lo que ya existe: migrar a un `write()` de append habría tirado la retención `MAX_ROWS` y la allowlist anti-secretos. **Eliminada**: se reusa `tmp + replace` bajo `_LOCK`, que ya es atómico de verdad.
- **C11 (IMPORTANTE) — `orphan_ci_runs(older_than_h=24)` arrancaba reportando 8 huérfanos que son fixtures.** **Resuelto**: los huérfanos se calculan **solo sobre `env="prod"`**.
- **C12 (IMPORTANTE) — KPI dependiente de otro plan.** "6 de 6 ledgers validados" incluía `telemetry_harvest`, roto por el 255. **KPI re-basado a los 5 ledgers JSONL reales y en scope.**
- **C13 (IMPORTANTE) — el criterio "correr la suite completa" choca con el gotcha de la casa** (contaminación cross-file: los tests se corren **por archivo**). **Precisado**: el gate de estanqueidad se corre con el runner del arnés (`scripts/run_harness_tests.sh`), que ya itera por archivo.
- **C14 (MENOR) — ambigüedad body-vs-default en la purga.** **Resuelto**: el endpoint exige `dry_run` explícito en el body; ausente = `true`.
- **C15 (MENOR) — el conteo de flags no cerraba** ("4 flags nuevas" pero 5 perillas, sin prefijo `STACKY_`, y sin alta en la UI). **Resuelto**: 6 perillas nombradas con prefijo de la casa y **fase F6 nueva** con el cableado completo (Config + `FlagSpec` + categoría existente + `_CURATED_DEFAULTS_ON` + `_REQUIRES_MAP_FROZEN`).
- **C16 (MENOR) — `confirm_token` no existe** (0 implementaciones). **Resuelto**: se **reusa** `backend/services/confirm_token.py`, cuyo dueño es el **plan 253 F5**. Dependencia declarada.
- **C17 (MENOR) — sin huella de regresión.** Se agrega entrada en `docs/sistema/error_fingerprints.json`.
- **[ADICIÓN ARQUITECTO]** — **F7: guard de estanqueidad del arnés.** Ver §4 F7.

---

## 1. Objetivo y KPI

Que todo evento de telemetría sea **trazable a su origen** (producción vs test), que ningún ciclo de CI real quede abierto para siempre, y que los tests no puedan escribir en los archivos del operador.

| KPI | Hoy (medido) | Meta |
|---|---|---|
| Líneas de fixture de test en `ci_runs.jsonl` | **8 de 8 = 100 %** | **0** |
| Líneas escritas por pytest en `env_applies.jsonl` | **10 de 10 = 100 %** | **0** |
| Ledgers JSONL en scope con campo de procedencia (`env`) | **0 de 5** | **5 de 5** |
| Ledgers JSONL en scope con esquema validado al escribir | **0 de 5** | **5 de 5** |
| Artefactos de runtime del operador modificados por una corrida del arnés | **no medido** (hoy nadie lo verifica) | **0, verificado por gate** |
| Corridas de CI **reales** (`env="prod"`) sin cierre > 24 h | **0 de 0** (no hay ni una real) | **0**, y visibles en el reporte |
| Mensajes de mock de test en el log de la app **posteriores al 2026-07-16** | **0** (ya cerrado por plan 145) | **0**, con test de regresión que lo blinda |

> **Nota de honestidad sobre el KPI de ciclos abiertos.** El v1 afirmaba "8 de 8 eventos con el ciclo sin cerrar" como un defecto de diseño. Es un artefacto de la contaminación: **las 8 líneas son fixtures que nunca pasaron por el poller**. No hay evidencia de que una corrida **real** haya quedado sin cerrar, porque **no hay ni una corrida real en el ledger**. El cierre ya existe y ya está cableado (C2). Lo que falta de verdad es **visibilidad** de huérfanos, no el mecanismo de cierre.

---

## 2. Evidencia real (anclaje anti-alucinación)

### E1 — `ci_runs.jsonl`: 100 % fixture

Contenido **completo** del archivo (8 líneas, 2.026 bytes), parseado línea por línea:

| # | project | pipeline_id | last_status | finished_at | web_url |
|---|---|---|---|---|---|
| 1 | `myproject` | 42 | `None` | `None` | `http://gitlab/p/42` |
| 2 | `myproject` | 42 | `None` | `None` | `http://gitlab/p/42` |
| 3 | `myproject` | 42 | `None` | `None` | `http://gitlab/p/42` |
| 4 | `myproject` | 7 | `None` | `None` | *(vacío)* |
| 5 | `myproject` | 42 | `None` | `None` | `http://gitlab/p/42` |
| 6 | `myproject` | 42 | `None` | `None` | `http://gitlab/p/42` |
| 7 | `myproject` | 42 | `None` | `None` | `http://gitlab/p/42` |
| 8 | `myproject` | 7 | `None` | `None` | *(vacío)* |

Primera línea literal:

```json
{"project": "myproject", "tracker_type": "gitlab", "ref": "develop", "sha": "newsha",
 "pipeline_id": "42", "web_url": "http://gitlab/p/42",
 "triggered_at": "2026-07-20T21:40:38.076369+00:00", "source": "stacky",
 "last_status": null, "finished_at": null}
```

**Contaminación total.** `"project": "myproject"`, `"sha": "newsha"`, `"web_url": "http://gitlab/p/42"` son valores de fixture. Ningún proyecto real del operador se llama `myproject` (los reales son `RSPACIFICO`, `RSSICREA`, `RIPLEY`). El archivo **no contiene ni un evento real**.

**Sobre `last_status: null` en 8 de 8:** es **consecuencia** de lo anterior, no un defecto independiente. El cierre lo escribe `update_run_status` desde el poller (`api/ci.py:212`); estas 8 líneas las insertó un test que nunca corrió el poller. Corregido respecto del v1, que lo contaba como segundo defecto.

### E2 — `env_applies.jsonl`: escrito íntegramente por pytest

10 líneas, 4.422 bytes. `grep -c "pytest"` -> **10**. **Las 10.** Primera línea literal:

```json
{"root": "C:\\Users\\juanluca\\AppData\\Local\\Temp\\pytest-of-juanluca\\pytest-1877\\test_f4_apply_creates_and_repo0",
 "server_alias": null, "paths": ["IN_", "productivas", "salida"], "paths_truncated": false,
 "fingerprint": "c6cb5b63c18e02f29202c0b9f0b51b1a245a537255d1663792ce3688706832ae",
 "sandbox_active": false, "result_ok": true, "created_count": 3, "ignored_count": 0, ...}
```

El `root` apunta a `pytest-of-juanluca\pytest-1877\test_f4_apply_creates_and_repo0`: un directorio temporal de pytest. **El ledger de aplicación de entornos del operador contiene exclusivamente corridas de test.** Nótese `"result_ok": true`: si un panel contara éxitos, reportaría 10 aplicaciones exitosas que nunca ocurrieron.

Este es el **agujero vivo real** del plan, y el `root` con prefijo de tmpdir es una señal **por campo**, limpia y no ambigua (base de la inferencia de F2).

### E3 — Los tests escribieron en el log de la aplicación **hasta el 2026-07-16, y ya no**

Firma en los logs de la app:

```
9 ERROR [stacky_agents.adaptive_selector] _load_last_project_confidence: error inesperado: DB exploded
```

Serie: `stacky-2026-07-12.log`=6, `stacky-2026-07-14.log`=1, `stacky-2026-07-15.log`=2.

`"DB exploded"` es un string de mock que existe en un solo lugar del repo:

```python
# Stacky Agents/backend/tests/test_adaptive_selector_wiring.py:260
        sess.query.side_effect = RuntimeError("DB exploded")
```

Lo mismo con el reaper (`trigger="test_reaper"`, `tests/test_cutover_p5.py:505`), 4 ocurrencias, **todas en `stacky-2026-07-16.log`**, con estos timestamps:

```
2026-07-16 01:23:19 WARNING [stacky.ticket_status] reaper[test_reaper] ...
2026-07-16 01:25:54 WARNING [stacky.ticket_status] reaper[test_reaper] ...
2026-07-16 01:26:26 WARNING [stacky.ticket_status] reaper[test_reaper] ...
2026-07-16 01:43:26 WARNING [stacky.ticket_status] reaper[test_reaper] ...
```

**El dato que cambia el plan:** el fix del plan 145 se commiteó el **2026-07-16 a las 02:05:19 -0300** (`f00f161f`). Las 4 líneas de `test_reaper` son de **01:23 a 01:43**, es decir **entre 22 y 42 minutos ANTES** del fix. Y el código de hoy dice:

```python
# Stacky Agents/backend/services/local_file_logging.py:154-165
def install_file_log_handler(
    *,
    base_dir: Path | None = None,
    retention_days: int = LOG_RETENTION_DAYS,
) -> None:
    """Install a single daily local file log handler on the root logger."""
    global _installed
    with _install_lock:
        if _installed:
            return
        if base_dir is None:
            base_dir = _test_logs_dir() if _test_mode() else logs_dir()
```

con `_test_logs_dir()` (`:64`) = `Path(tempfile.gettempdir()) / "stacky-test-logs"`.

**Conclusión honesta: las 13 ocurrencias (9 + 4) son 13 de 13 anteriores al fix. Hay logs del 07-16 al 07-26 — diez días — con cero contaminación. El agujero del log está CERRADO.** Lo que corresponde no es abrirlo de nuevo con un gate distinto, sino **blindarlo con un test de regresión** para que no vuelva. Ver F5.

### E4 — Inventario real de ledgers (reconciliado)

**En scope** (JSONL bajo `backend/data/`, con writer identificado):

| Archivo | Writer | Líneas | Bytes | Estado |
|---|---|---|---|---|
| `data/ci_runs.jsonl` | `services/ci_run_ledger.py:30` | 8 | 2.026 | **100 % fixture** |
| `data/env_applies.jsonl` | `services/env_apply_ledger.py:36` | 10 | 4.422 | **100 % pytest** |
| `data/db_query_audit.jsonl` | `services/db_query.py:45` | 9 | 4.157 | 9/9 `result: "would_execute"`. **Correcto** (la flag está OFF por diseño), pero sin campo que distinga dry-run de real más allá de ese valor. |
| `data/config_transfer_events.jsonl` | `services/config_transfer.py` | 436 | 140.797 | **LIMPIO.** `grep -c "pytest\|myproject\|test_"` -> **0**. Datos reales desde 2026-06-19. Modelo a replicar. |
| `data/build_runs.jsonl` | `services/solution_builder.py` | — | 4.975 | **Omitido por completo en el v1.** Plan 201 (Taller de Compilación). Sin auditar; entra al inventario y al guard de F7. |

**Fuera de scope de migración, con motivo:**

| Ítem | Motivo |
|---|---|
| `services/publish_ledger.py` | **No es un JSONL.** Es DB-backed (`try_acquire` / `mark_posted` / `snapshot_stuck`). El v1 lo listaba en `LEDGER_NAMES` con `REQUIRED_KEYS` inventadas. |
| `telemetry_harvest.jsonl` | **Nunca se escribe.** `services/telemetry_harvest.py:503` hace `Path(data_dir()) / "telemetry_harvest.jsonl"` y `data_dir` **no está importado** en el módulo (imports en `:21-28`) -> `NameError`. **Dueño del fix: plan 255 (bug C).** Dependencia declarada, no invasión. |
| `data/db_compare/sql_exec_ledger.jsonl` | `services/sql_exec_ledger.py:26`. Subdirectorio propio, dominio DB Compare. Entra al **guard de F7** (que barre el árbol) pero no a la migración. |
| `ado_edit_learned.jsonl` | `services/ado_edit_ledger.py:81`. El archivo **no existe todavía**. Entra al guard de F7. |
| `services/pipeline_audit_suppressions.py` | Ledger del **plan 248**. No se toca. |
| `Stacky tools/QA UAT Agent/data/run_metrics.jsonl` | 181 líneas, herramienta separada con su propio ciclo. |

**Que `config_transfer_events.jsonl` esté limpio con 436 líneas prueba que el problema no es estructural del formato JSONL, sino de qué ledgers pueden ser alcanzados por un test.** Hay un patrón correcto en el repo: hay que replicarlo.

### E5 — El mecanismo de escritura real (lo que el v1 no miró)

```python
# services/ci_run_ledger.py:19-26
MAX_ROWS = 500           # retención dura: al superar, se conservan los 500 más nuevos
_LOCK = threading.Lock()

ENTRY_FIELDS: tuple[str, ...] = (
    "project", "tracker_type", "ref", "sha", "pipeline_id",
    "web_url", "triggered_at", "source", "last_status", "finished_at",
)
```

```python
# services/ci_run_ledger.py:50-58
def _write_rows(rows: list[dict]) -> None:
    """Reescritura atómica: tmp + replace (mismo volumen)."""
    ...
    tmp.replace(path)
```

```python
# services/ci_run_ledger.py:60-64
def _clean_entry(entry: dict) -> dict:
    """Proyecta SOLO ENTRY_FIELDS; last_status/finished_at inicializados en None."""
    out = {k: entry.get(k) for k in ENTRY_FIELDS}
```

**Tres consecuencias duras para el diseño:**
1. Estos ledgers **no son append-only**: cada escritura reescribe el archivo entero, atómicamente, bajo lock, con retención. La atomicidad ya está resuelta y mejor de lo que proponía el v1.
2. La **allowlist** es un guard anti-secretos deliberado. Cualquier campo nuevo (`env`, `schema_version`) que no se agregue a `ENTRY_FIELDS` **se descarta en silencio**.
3. `tmp.replace(path)` es exactamente el gotcha `os.replace` de Windows (D11): **ya está en el camino caliente**. La purga de F4 debe reusar `_write_rows`, no inventar su propio replace.

---

## 3. Principios y guardarraíles (obligatorios)

- **Human-in-the-loop:** la limpieza de las líneas contaminadas es **destructiva** -> detrás de confirmación explícita con el conteo a la vista. Stacky no borra datos del operador por su cuenta, ni siquiera datos que sabe que son basura.
- **No borrar por default, marcar.** F2 **no** elimina las líneas viejas: les agrega procedencia inferida. El borrado es opt-in (F4).
- **Reusar antes que construir.** Si el repo ya tiene el mecanismo (cierre de CI, escritura atómica, lock, retención, token HITL), se reusa. El v1 falló acá tres veces (C2, C3, C10, C16); el v2 lo pone como principio explícito y verificable: **toda función "nueva" de este plan debe venir con el grep que prueba que no existe.**
- **Mono-operador sin auth.**
- **Paridad de 3 runtimes:** los ledgers son transversales. Ninguno es específico de un runtime.
- **Cero trabajo extra al operador:** F0-F3 y F5-F7 son invisibles. F4 es un botón opcional.
- **No degradar:** el campo `env` es **aditivo**, y **no se toca** el mecanismo de escritura existente (lock, atomicidad, retención `MAX_ROWS`, allowlist anti-secretos). Un lector viejo que ignore campos desconocidos sigue funcionando.
- **Flags default ON** salvo la de limpieza destructiva (excepción dura #2).
- **Toda flag configurable desde la UI** (ver F6: no alcanza con el atributo en `config.py`).

### Fronteras vivas (serie 253-258, se critican en paralelo)

| Frontera | Dueño | Regla para el 258 |
|---|---|---|
| `services/local_file_logging.py` (throttle, rotación, purga, `LOG_LEVEL` en caliente) | **plan 257** | **No se modifica.** F5 solo agrega un guard en `tests/conftest.py` y un test de regresión. Cero cambios de firma. |
| `services/telemetry_harvest.py` y su `NameError` | **plan 255** | **Dependencia, no invasión.** `telemetry_harvest.jsonl` entra al inventario cuando el 255 lo arregle. |
| `backend/services/confirm_token.py` (`issue_token` / `consume_token`) | **plan 253 F5** | **Se reusa.** Prohibido reimplementar otro token. |
| `system_logs` de la DB | **plan 253 F4** | Fuera de scope. |
| Ledger de supresiones de auditoría de pipelines | **plan 248** | Fuera de scope. |
| Tarjeta de UI | **este plan** | *"Salud de ledgers"*. Tomadas: 255 = "Fallos silenciados", 256 = "Artefactos en cuarentena", 257 = "Firmas de log más repetidas". |

**Propiedad del 258:** `backend/services/ledger_writer.py` (nuevo), los `*_ledger.py` y los `.jsonl` de `backend/data/`, y los endpoints `GET /api/diag/ledgers/health` + `POST /api/diag/ledgers/purge-test-lines`.

---

## 4. Fases

### F0 — Tests que prueban la contaminación

**Archivo a crear:** `Stacky Agents/backend/tests/test_plan258_ledger_veracidad.py`
**Registrar en:** `HARNESS_TEST_FILES` de `Stacky Agents/backend/scripts/run_harness_tests.sh` (**única** fuente que exigen `tests/test_harness_ratchet_meta.py` y `tests/test_plan76_ratchet_byteidentical.py:83`). Sincronizar también `scripts/run_harness_tests.ps1`, **respetando que su sintaxis es distinta** (`.ps1` usa comillas + coma; `.sh` no).

**Casos exactos:**

1. `test_append_en_test_mode_no_escribe_el_ledger_real` — con `STACKY_TEST_MODE` activo, un append a `ci_runs.jsonl` **no** toca `backend/data/ci_runs.jsonl`. **Hoy falla.**
2. `test_append_en_test_mode_escribe_ruta_aislada` — en test-mode el ledger va a `Path(tempfile.gettempdir()) / "stacky-test-ledgers"`, no a `backend/data/`. **Hoy falla.**
3. `test_todo_evento_lleva_campo_env` — todo evento nuevo tiene `env` ∈ `{"prod","test"}`. **Hoy falla** (el campo no existe y además la allowlist lo descartaría).
4. `test_entry_fields_incluye_env` — regresión de C4: `ci_run_ledger.ENTRY_FIELDS` y `env_apply_ledger.ENTRY_FIELDS` contienen `"env"`. **Hoy falla.**
5. `test_ledger_valida_esquema_al_escribir` — un evento sin las claves obligatorias es rechazado y **no** se escribe. **Hoy falla.**
6. `test_orphan_ci_runs_solo_cuenta_prod` — un evento `env="test"` de hace 48 h **no** aparece como huérfano; uno `env="prod"` sí. **Hoy falla.**
7. `test_lector_ignora_campos_desconocidos` — una línea con una clave futura no rompe el lector.
8. `test_update_run_status_existe_y_esta_cableado` — **anti-regresión de C2**: `ci_run_ledger.update_run_status` es invocable y `api/ci.py` la importa. **Hoy pasa** (documenta lo que ya existe, para que nadie lo reimplemente).

**Comando exacto:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan258_ledger_veracidad.py -v
```

**Criterio binario:** los 8 existen; **1-6 fallan** antes de F1/F3; **7 y 8 pasan** desde el inicio.

**Flag:** ninguna. **Trabajo del operador: ninguno.**

---

### F1 — Un portero de validación y procedencia (sin tocar el mecanismo de escritura)

**Objetivo:** que ningún ledger pueda escribirse desde un test en el archivo del operador, y que todo evento declare su procedencia — **sin degradar** el lock, la atomicidad, la retención ni la allowlist que ya existen (E5).

**Archivo a crear:** `Stacky Agents/backend/services/ledger_writer.py` — capa de **validación + procedencia + ruta**. **No** es un mecanismo de escritura nuevo.

**Símbolos nuevos exactos:**

```python
# Inventario REAL verificado (ver E4). NO incluye publish_ledger (es DB-backed)
# ni telemetry_harvest (NameError vivo, dueño = plan 255).
LEDGER_NAMES = ("ci_runs", "env_applies", "db_query_audit",
                "config_transfer_events", "build_runs")

# Validación por (ledger, event_type). El default 'run' es el evento clásico.
REQUIRED_KEYS = {
    ("ci_runs", "run"):                  ("project", "tracker_type", "pipeline_id", "triggered_at"),
    ("env_applies", "run"):              ("root", "fingerprint"),
    ("db_query_audit", "run"):           ("ts", "project", "result"),
    ("config_transfer_events", "run"):   ("ts", "action", "project", "result"),
    ("build_runs", "run"):               ("ts",),
}


def _test_mode() -> bool:
    """Idioma de la casa, replicado por módulo (local_file_logging.py:61,
    error_fingerprints.py:59, lifecycle_log.py:46, output_watcher.py:986).
    NO existe config.STACKY_TEST_MODE — ver plan 258 C5.
    """
    import os
    return os.getenv("STACKY_TEST_MODE", "").lower() in {"1", "true", "yes"}


def ledger_path(name: str) -> Path:
    """Ruta del ledger `name`. En test-mode devuelve una ruta AISLADA bajo
    tempfile.gettempdir()/stacky-test-ledgers/, NUNCA backend/data/.
    Calca la receta del plan 145 para logs (local_file_logging.py:64-65).
    """


def stamp_event(name: str, event: dict, *, event_type: str = "run",
                allow_incomplete: bool = False) -> dict | None:
    """Valida y sella UN evento. NO escribe: devuelve el dict a persistir.

    - Inyecta `env` = 'test' si _test_mode() else 'prod'.
    - Inyecta `schema_version` si falta.
    - Valida REQUIRED_KEYS[(name, event_type)]: si falta alguna, devuelve None
      y loguea a error (salvo allow_incomplete=True).
    Devuelve None si el evento NO debe escribirse.
    """


def read_events(name: str, *, env: tuple[str, ...] | None = ("prod", "unknown")) -> list[dict]:
    """Lee el ledger filtrando por procedencia.

    DEFAULT ('prod','unknown'): NO oculta datos reales del operador — las 436
    líneas de config_transfer_events y las 9 de db_query_audit son históricas
    sin marca y DEBEN seguir visibles (plan 258 C7).
    env=None devuelve todo, incluido 'test'.
    Las líneas SIN campo `env` se clasifican con infer_env_for_legacy_line (F2).
    Ignora claves desconocidas.
    """
```

**Regla clave — el default de lectura NO oculta nada.** El v1 proponía `env="prod"` por default con el argumento de que "el consumidor migra sin cambiar su código". Ese default, combinado con la propia F2 (que deja **todo lo histórico en `unknown`**), habría hecho desaparecer **436 + 9 líneas reales** de la vista del operador. El default correcto es `("prod","unknown")`: excluye solo lo **probadamente** de test. Filtrar a `prod` puro es una decisión explícita del llamador.

**Aislamiento en test-mode:** `ledger_path` consulta `_test_mode()` (idioma real, C5) y devuelve `Path(tempfile.gettempdir()) / "stacky-test-ledgers" / f"{name}.jsonl"`.

**Migración de los call-sites — quirúrgica, tres cambios por ledger:**

1. En cada `*_ledger.py` (y `db_query.py`, `config_transfer.py`, `solution_builder.py`): la función de ruta pasa a delegar en `ledger_writer.ledger_path(name)`.
2. **Agregar `"env"` y `"schema_version"` a `ENTRY_FIELDS`** del ledger. **Sin esto el campo se descarta en silencio** (C4). Preserva el guard anti-secretos: la allowlist sigue siendo cerrada, solo crece en dos claves controladas.
3. En la función de append, sellar con `stamp_event(...)` antes de `_clean_entry`; si devuelve `None`, no escribir y salir sin lanzar.

**Lo que NO se toca (regla dura, C3/C10):** `_LOCK`, `_read_rows`, `_write_rows` (`tmp.replace`), `MAX_ROWS`, la semántica de la allowlist. Ya son correctos y más fuertes que lo que proponía el v1.

**Orden de migración:** `ci_runs` y `env_applies` primero (son los contaminados). `config_transfer_events` (el limpio, 436 líneas) migra **último** y sirve de test de regresión: si después de migrar sigue igual de limpio y con las 436 líneas legibles por default, la puerta está bien hecha.

**Casos borde:**
- Ledger escrito desde un thread daemon durante el teardown de pytest: `STACKY_TEST_MODE` sigue activo -> archivo aislado. **Este es el mecanismo exacto por el que se contaminó `env_applies.jsonl`.**
- Evento incompleto en un path legítimo: `allow_incomplete=True` explícito en el call-site, nunca por default.
- Disco lleno / error de escritura: el comportamiento existente ya es best-effort y **no lanza** (`env_apply_ledger` documenta "JAMÁS lanza al caller"). Se preserva.
- Un ledger cuyo writer no tiene allowlist (`db_query.py`, `config_transfer.py`, `solution_builder.py`): verificar caso por caso si hay proyección de campos antes de asumir que `env` sobrevive. **Grep obligatorio antes de editar.**

**Tests:** casos 1, 2, 3, 4, 5, 7 de F0 a verde.

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan258_ledger_veracidad.py -k "test_mode or env or esquema or desconocidos or entry_fields" -v
```
6 verdes. La verificación de estanqueidad se cubre en **F7**, no acá (ver C13).

**Flag:** `STACKY_LEDGER_STRICT_SCHEMA_ENABLED`, **default ON**. Sin excepción dura: no bypasea revisión, no es destructiva (rechazar una escritura inválida no borra nada), sin prerequisito, no reduce seguridad.
**Impacto por runtime:** transversal, idéntico en los 3.
**Trabajo del operador: ninguno.**

---

### F2 — Procedencia de lo histórico, sin borrar nada

**Objetivo:** que las 18 líneas contaminadas ya existentes queden **marcadas**, no eliminadas.

**Archivo a editar:** `Stacky Agents/backend/services/ledger_writer.py`.

**Símbolo nuevo exacto — inferencia POR CAMPO, no por substring global (C9):**

```python
# Reglas nombradas: (ledger_o_None, campo, predicado, motivo).
# NO se hace substring sobre cualquier valor string del evento: 'pytest',
# 'test_reaper' o 'DB exploded' pueden aparecer en texto libre legítimo
# (una query auditada, una ruta de proyecto, un título de ticket).
_TEST_RULES = (
    (None,        "root",        "startswith_tmpdir",  "root bajo el tmpdir de pytest"),
    (None,        "root",        "contains:pytest-of-", "root con directorio de pytest"),
    ("ci_runs",   "web_url",     "startswith:http://gitlab/p/", "web_url de fixture"),
    ("ci_runs",   "sha",         "equals:newsha",      "sha de fixture"),
    ("ci_runs",   "project",     "in:_FIXTURE_PROJECTS", "project de fixture"),
)

_FIXTURE_PROJECTS = ("myproject",)   # ampliable por config, ver flag de F6


def infer_env_for_legacy_line(name: str, event: dict) -> str:
    """Plan 258 F2 — procedencia de una línea SIN campo `env`.

    Devuelve 'test' solo si una regla de _TEST_RULES matchea en el CAMPO que
    la regla nombra; 'unknown' en caso contrario.

    NUNCA devuelve 'prod' por inferencia: una línea histórica sin marca es
    'unknown', no 'prod'. Afirmar procedencia sin evidencia sería inventar
    datos, que es exactamente el problema que este plan resuelve.
    """
```

**Dos reglas son el corazón de la fase.** (1) Nunca inferir `prod`: es tentador asumir que lo no-marcado es producción, y sería adivinar. (2) Nunca marcar por substring global: un `project` llamado `myproject` es evidencia; la palabra `pytest` dentro de una `query` auditada **no lo es**.

**Aplicación de las reglas a la evidencia medida:**

| Ledger | Líneas | Inferencia esperada | Regla que dispara |
|---|---|---|---|
| `ci_runs.jsonl` | 8 | **8 -> `test`** | `project in _FIXTURE_PROJECTS` + `sha == newsha` + `web_url` |
| `env_applies.jsonl` | 10 | **10 -> `test`** | `root` bajo tmpdir de pytest |
| `db_query_audit.jsonl` | 9 | 9 -> `unknown` | ninguna (son reales, pero no verificables por marca) |
| `config_transfer_events.jsonl` | 436 | 436 -> `unknown` | ninguna |
| `build_runs.jsonl` | por medir en F2 | a determinar | — |

**Nota importante:** `db_query_audit` y `config_transfer_events` quedan en `unknown`, no en `prod`. Eso es correcto y deliberado — y **por eso** el default de `read_events` es `("prod","unknown")` (C7): quedan visibles. Los eventos **nuevos** (post-F1) llevan `env` explícito, y `unknown` se extingue solo. No se reescribe la historia.

**Casos borde:**
- Un proyecto real llamado `myproject`: falso positivo. Mitigado por tres vías: el marcado **no borra**; la lista es configurable vía la flag CSV de F6; y la purga (F4) muestra el conteo antes de tocar nada.
- Marcador dentro de un campo de texto libre legítimo: **ya no puede ocurrir** — las reglas nombran el campo (C9).
- Evento con `env` ya presente: `infer_env_for_legacy_line` **no se llama**. El campo explícito siempre gana.

**Tests:** en `test_plan258_ledger_veracidad.py`:
- `test_infer_env_detecta_pytest_root` — la línea real de `env_applies.jsonl` -> `test`.
- `test_infer_env_detecta_fixture_ci_run` — la línea real de `ci_runs.jsonl` -> `test`.
- `test_infer_env_nunca_devuelve_prod` — invariante sobre 100 eventos arbitrarios.
- `test_infer_env_no_marca_por_substring_en_texto_libre` — **regresión de C9**: un evento de `db_query_audit` con `query = "SELECT * FROM pytest_runs"` -> `unknown`, **no** `test`.
- `test_infer_env_no_se_llama_si_env_presente`
- `test_read_events_default_incluye_unknown` — **regresión de C7**: `read_events("config_transfer_events")` devuelve las 436.
- `test_read_events_env_none_devuelve_todo`

**Criterio binario:** 7 verdes. Y `read_events("ci_runs", env=("prod",))` devuelve **lista vacía** — la verdad: no hay ni un evento real de CI.

**Flag:** `STACKY_LEDGER_LEGACY_INFERENCE_ENABLED`, **default ON**. Sin excepción dura (solo etiqueta en memoria al leer; **no modifica los archivos**).
**Impacto por runtime:** transversal.
**Trabajo del operador: ninguno.**

---

### F3 — Huérfanos de CI visibles (reusando el cierre que YA existe)

**Objetivo:** que una corrida de CI **real** que nunca reportó desenlace sea **visible**, en vez de desaparecer.

> **Corrección mayor respecto del v1 (C2/C3).** El v1 proponía crear `close_ci_run` con línea de cierre `event_type='close'` y decía "no existe la función" y "cablearlo al poller que ya existe". Ambas cosas ya estaban hechas por el **plan 191**:
>
> ```python
> # services/ci_run_ledger.py:103
> def update_run_status(pipeline_id: str, status: str, finished_at: str | None = None) -> bool:
> ```
> ```python
> # api/ci.py:206-218 — dentro del monitor de pipeline
> if getattr(_config.config, "STACKY_CI_RUN_LEDGER_ENABLED", False):
>     status = str((result or {}).get("status") or "").lower()
>     if status in ("success", "failed", "canceled", "skipped"):
>         from services.ci_run_ledger import update_run_status
>         update_run_status(str(pipeline_id), status, datetime.now(timezone.utc).isoformat())
> ```
> con `STACKY_CI_RUN_LEDGER_ENABLED` default **`true`** (`config.py:1647`).
>
> Además la línea de cierre append-only **habría roto** dos cosas: el conteo de los lectores viejos (dos líneas por run), y el propio validador de F1 (`REQUIRED_KEYS["ci_runs"]` exige `triggered_at`, que un cierre no tiene) — **contradicción interna** (C8).

**Lo que F3 aporta de verdad (tres cosas, ninguna duplicada):**

**(1) Corregir el bug real de reconciliación en `update_run_status`.** Hoy matchea **solo por `pipeline_id`**:

```python
# services/ci_run_ledger.py:111 — BUG: no filtra por project
idxs = [i for i, r in enumerate(rows) if str(r.get("pipeline_id")) == str(pipeline_id)]
```

Con `pipeline_id` 42 repitiéndose entre proyectos (y en la evidencia medida se repite **6 veces**), el cierre de un proyecto puede escribirse sobre la corrida de otro. **Fix:** agregar el parámetro `project` y reconciliar por `(project, pipeline_id)`, manteniendo compatibilidad hacia atrás (`project=None` conserva el comportamiento actual, con warning). Actualizar el call-site de `api/ci.py:212` para pasarlo.

**(2) Reporte de huérfanos, solo sobre producción (C11):**

```python
def orphan_ci_runs(*, older_than_h: float = 24.0, now: datetime | None = None) -> list[dict]:
    """Corridas de CI con env='prod' sin last_status y con más de `older_than_h`
    horas desde triggered_at. `now` es inyectable para que el test no dependa
    del reloj.

    Solo 'prod': las 8 líneas de fixture de hoy tienen todas > 24 h y
    contaminarían el reporte desde el minuto uno (plan 258 C11).
    """
```

**(3) Endpoint de salud:** `GET /api/diag/ledgers/health` (`Stacky Agents/backend/api/diag.py`) devuelve, por ledger: total de líneas, desglose por `env` (`prod`/`test`/`unknown`), y para `ci_runs` la lista de huérfanos `prod`. Tarjeta **"Salud de ledgers"** en el panel de diagnóstico, visible solo si hay algo que reportar.

**Casos borde:**
- Dos cierres del mismo `(project, pipeline_id)`: gana el más reciente por `triggered_at` (comportamiento actual, se preserva y se documenta).
- Cierre de un `pipeline_id` que nunca se disparó: `update_run_status` ya devuelve `False` como no-op silencioso. Se preserva; se cuenta en el reporte como `closes_sin_disparo`.
- Proveedor que no expone estado terminal: el evento queda huérfano y **aparece en el reporte** en vez de desaparecer. Fallback explícito, igual para ADO y GitLab vía el `CIProvider` existente.

**Tests:** casos 6 y 8 de F0 a verde. Sumar:
- `test_update_run_status_reconciliacion_por_project_y_pipeline_id` — **el bug real**: mismo `pipeline_id` en dos proyectos no se cruza.
- `test_update_run_status_sin_project_es_compatible` — backward-compat.
- `test_orphan_ci_runs_ignora_test_y_unknown`
- `test_orphan_ci_runs_now_inyectable`
- `test_endpoint_ledgers_health_desglosa_por_env`

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan258_ledger_veracidad.py -v
```
todo verde, y `GET /api/diag/ledgers/health` reporta `ci_runs: {prod: 0, test: 8, unknown: 0, orphans: 0}` — **la verdad medible** sobre el estado actual.

**Flag:** `STACKY_LEDGER_ORPHAN_REPORT_ENABLED`, **default ON**. (El v1 proponía `CI_RUN_LEDGER_CLOSE_ENABLED`: **descartada**, el cierre ya tiene su flag `STACKY_CI_RUN_LEDGER_ENABLED`, y una segunda flag para lo mismo sería una perilla muerta.)
**Impacto por runtime:** el ledger de CI es del orquestador, común a los 3.
**Trabajo del operador: ninguno.**

---

### F4 — Limpieza asistida (HITL, la única pieza destructiva)

**Objetivo:** darle al operador la opción de purgar las 18 líneas de fixture, con el conteo a la vista.

**Archivos a editar:**
1. `Stacky Agents/backend/api/diag.py` — `POST /api/diag/ledgers/purge-test-lines`.
2. `Stacky Agents/backend/services/ledger_writer.py` — la función de purga.

**Dependencia declarada:** el token HITL es `backend/services/confirm_token.py` (`issue_token(action, payload, ttl_s=120)` / `consume_token(action, token)`), **cuyo dueño es el plan 253 F5**. Hoy `confirm_token` tiene **0 implementaciones** en el repo. **Prohibido reimplementar otro token** (C16). Si el 253 no está implementado al llegar acá, F4 queda **bloqueada**, no se improvisa.

**Símbolo nuevo exacto:**

```python
def purge_test_lines(name: str, *, confirm_token: str, dry_run: bool = True) -> dict:
    """Plan 258 F4 — elimina las líneas con env='test' (o inferido 'test').

    dry_run=True (DEFAULT) solo cuenta y devuelve un preview.
    Con dry_run=False exige confirm_token (services/confirm_token.py, dueño
    plan 253 F5) y hace backup previo a data/ledger_backups/<name>-<ts>.jsonl.

    Reescribe usando el _write_rows del propio ledger (tmp + replace bajo _LOCK),
    NUNCA un replace propio: ese camino ya está resuelto y probado (plan 258 C3).

    NUNCA toca líneas 'prod' ni 'unknown'.
    """
```

**Contrato HITL, no negociable:**
1. `dry_run=True` es el **default del parámetro**. Un llamador que olvide el argumento no borra nada.
2. **En el endpoint manda el body** (C14): `POST` con `{"dry_run": false}` explícito es la **única** forma de borrar. Body ausente, campo ausente o no booleano -> `dry_run=true`. Documentado en el docstring del endpoint y con test.
3. `GET /api/diag/ledgers/health` emite el `confirm_token` (TTL 120 s) con el conteo exacto por ledger.
4. La UI muestra: *"Se eliminarán 8 líneas de fixture de ci_runs.jsonl y 10 de env_applies.jsonl. Las 436 de config_transfer_events y las 9 de db_query_audit (procedencia desconocida) NO se tocan. Se guarda una copia antes."*
5. Backup obligatorio previo. Si el backup falla, **se aborta**.
6. `unknown` **nunca** se purga. Solo lo probadamente `test`.

**Casos borde:**
- Ledger escribiéndose mientras se purga: se toma el `_LOCK` del ledger y se reusa su `_write_rows`. **Gotcha conocido del repo:** `tmp.replace(path)` en Windows falla si el archivo está abierto por otro handle — ya está en el camino caliente (E5), así que el fix es tomar el lock y reintentar con backoff, no inventar otro mecanismo.
- Ledger vacío o inexistente: `{"deleted": 0}`, sin error.
- Token expirado o ausente: `409`.
- Ledger sin `_LOCK` propio (`db_query.py`, `config_transfer.py`, `solution_builder.py`): verificar antes de purgarlo; si no tiene lock, la purga de ese ledger se declara **no soportada en v1** en vez de hacerla insegura.

**Tests:** `Stacky Agents/backend/tests/test_plan258_ledger_purge.py` (agregar al ratchet):
- `test_purge_dry_run_es_el_default` — sin argumentos, no borra.
- `test_endpoint_sin_dry_run_en_el_body_no_borra` — **regresión de C14**.
- `test_purge_sin_token_devuelve_409`
- `test_purge_hace_backup_antes`
- `test_purge_aborta_si_falla_el_backup` — el ledger queda intacto.
- `test_purge_nunca_borra_unknown_ni_prod`
- `test_purge_con_archivo_abierto_no_corrompe` — el gotcha de `tmp.replace` en Windows.
- `test_purge_ledger_inexistente_devuelve_cero`

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan258_ledger_purge.py -v
```
8 verdes.

**Flag:** `STACKY_LEDGER_PURGE_ENABLED`, **default OFF**. Cita la **excepción dura #2: destructiva/irreversible**. Se prende desde la UI cuando el operador quiera limpiar.
**Impacto por runtime:** transversal.
**Trabajo del operador:** opt-in, un clic, con el conteo exacto y un backup. Es la excepción justificada al "cero trabajo".

---

### F5 — Blindar (no reabrir) el aislamiento del log del operador

> **Fase completamente reescrita (C1).** El v1 proponía cambiar la firma de `install_file_log_handler` para que **no instalara** el handler en test-mode. Eso habría: (a) **regresado** el plan 145, que ya resolvió esto de una forma mejor — redirigir en vez de desinstalar, de modo que los tests **sí** tengan log, pero en `%TEMP%/stacky-test-logs/`; (b) **cambiado firma y tipo de retorno** (`-> None` pasa a `-> bool`, y desaparecían `base_dir` y `retention_days`); (c) puesto **ROJOS** los dos tests de `tests/test_plan145_pytest_log_isolation.py` —`test_install_redirects_to_tmp_under_test_mode` (`:20`) llama `install_file_log_handler()` y assertea `tmp_log.exists()`, que sería falso si la función retorna sin instalar; y `test_explicit_base_dir_wins` (`:45`) llama `install_file_log_handler(base_dir=tmp_path)`, que sería un `TypeError` con la firma propuesta; (d) **invadido** `services/local_file_logging.py`, que es del **plan 257**.

**Objetivo real:** el agujero está cerrado desde el 2026-07-16. Lo que falta es que **no se pueda reabrir en silencio**.

**Archivos a editar:**
1. `Stacky Agents/backend/tests/conftest.py` — **sumar** un guard (no reemplazar nada).
2. `Stacky Agents/backend/tests/test_plan258_ledger_veracidad.py` — test de regresión.

**Cero cambios en `services/local_file_logging.py`.** Frontera del 257.

**Guard en `conftest.py`:** el archivo ya hace `os.environ.setdefault("STACKY_TEST_MODE", "1")` (`:11`) e instala el guard de red del plan 154. **Se suma** un fixture `autouse` de sesión que, al finalizar, verifica que ningún `logging.Handler` activo apunte a `backend/data/logs/`. Si aparece uno, falla **ruidosamente** nombrando el handler, en vez de contaminar en silencio.

**Prueba de regresión con ventana de fecha:**

```python
def test_log_del_operador_sin_mocks_despues_del_fix_145():
    """Plan 258 F5 — regresión del hallazgo real: 'DB exploded'
    (tests/test_adaptive_selector_wiring.py:260) y 'test_reaper'
    (tests/test_cutover_p5.py:505) llegaron al log del operador HASTA el
    2026-07-16. El plan 145 (commit f00f161f, 2026-07-16 02:05:19 -0300) lo
    cerró redirigiendo el handler a %TEMP% (local_file_logging.py:165).

    Este test NO exige borrar la historia: escanea solo los logs con fecha
    POSTERIOR al fix. Si vuelve a aparecer un mock ahí, el aislamiento se rompió.
    """
    FIX_DATE = date(2026, 7, 16)
    log_dir = Path(__file__).resolve().parents[1] / "data" / "logs"
    for f in sorted(log_dir.glob("stacky-*.log")):
        try:
            day = date.fromisoformat(f.stem.replace("stacky-", ""))
        except ValueError:
            continue
        if day <= FIX_DATE:
            continue          # historia previa al fix: fuera de la ventana
        txt = f.read_text(encoding="utf-8", errors="replace")
        assert "DB exploded" not in txt, f"mock de test en {f.name}"
        assert "test_reaper" not in txt, f"trigger de test en {f.name}"
```

**Este test pasa HOY** contra los logs del 07-17 al 07-26 (verificado: cero ocurrencias). Es un candado, no una obra.

**Prohibido** hacerlo pasar con una allowlist de strings: eso sería gamear el gate.

**Casos borde:**
- Log del día del fix (`stacky-2026-07-16.log`): queda **fuera** de la ventana (`day <= FIX_DATE`), porque contiene las 4 líneas de `test_reaper` de las 01:23-01:43, anteriores al commit de las 02:05. Documentado en el docstring; no es una excepción arbitraria.
- Directorio de logs inexistente (checkout limpio): el `glob` devuelve vacío y el test pasa trivialmente. Aceptable: es un candado de regresión, no un KPI.
- Nombre de archivo no parseable: se saltea.

**Tests:**
- `test_log_del_operador_sin_mocks_despues_del_fix_145`
- `test_conftest_guard_detecta_handler_al_log_real` — se instala a mano un handler apuntando a `data/logs/` y se verifica que el guard lo detecta.
- `test_install_file_log_handler_conserva_su_firma` — **anti-regresión de C1**: `inspect.signature` tiene `base_dir` y `retention_days`, y el retorno es `None`. Impide que un implementador futuro "arregle" esto rompiendo el plan 145.

**Criterio binario:** 3 verdes, y `tests/test_plan145_pytest_log_isolation.py` **sigue en verde**:
```
.venv\Scripts\python.exe -m pytest tests/test_plan145_pytest_log_isolation.py -v
```

**Flag:** ninguna — es un gate de test, no runtime.
**Impacto por runtime:** ninguno (solo modo test).
**Trabajo del operador: ninguno.**

---

### F6 — Alta de las flags en la UI (fase obligatoria, faltaba en el v1)

**Objetivo:** que las perillas de este plan sean **configurables desde la UI**, no solo por env var. El v1 decía "exponer las 4 flags nuevas en el panel de flags" en un bullet del orden de implementación, sin decir dónde ni cómo — y **el atributo en `config.py` no alcanza**: la UI se alimenta de `services/harness_flags.py`, no de `config.py`.

**Inventario honesto de perillas — son 6, no 4 (C15):**

| Key (prefijo `STACKY_` de la casa) | Tipo | Default | Fase |
|---|---|---|---|
| `STACKY_LEDGER_STRICT_SCHEMA_ENABLED` | `bool` | **ON** | F1 |
| `STACKY_LEDGER_LEGACY_INFERENCE_ENABLED` | `bool` | **ON** | F2 |
| `STACKY_LEDGER_ORPHAN_REPORT_ENABLED` | `bool` | **ON** | F3 |
| `STACKY_LEDGER_PURGE_ENABLED` | `bool` | **OFF** (excepción dura #2) | F4 |
| `STACKY_LEDGER_TEST_MARKERS` | `csv` | `myproject` | F2 |
| `STACKY_HARNESS_AIRTIGHT_GUARD_ENABLED` | `bool` | **ON** | F7 |

**Los 6 lugares del cableado (obligatorios todos).** La receta clásica de la casa dice 5; **son 6**: falta `PLAIN_HELP`, verificado en `services/harness_flags_help.py:25`, que `tests/test_harness_flags_help.py` exige que cubra el **100 % de `FLAG_REGISTRY`**. Una `FlagSpec` sin su entrada de ayuda pone ese archivo en rojo.

1. **`backend/config.py`** — atributo por flag, con el idioma real del repo. **No existe `_env_bool`** en este archivo (0 ocurrencias); el idioma es:
   ```python
   STACKY_LEDGER_STRICT_SCHEMA_ENABLED: bool = os.getenv(
       "STACKY_LEDGER_STRICT_SCHEMA_ENABLED", "true"
   ).lower() in ("1", "true", "yes")
   ```
   Para la CSV: `STACKY_LEDGER_TEST_MARKERS: str = os.getenv("STACKY_LEDGER_TEST_MARKERS", "myproject")`.
   Los consumidores leen **la instancia**: `from config import config` y `config.STACKY_...` (nunca el módulo, que devolvería el default y mataría la rama OFF).
2. **`backend/services/harness_flags.py`** — un `FlagSpec` por perilla (campos: `key`, `type`, `label`, `description`, `group`, `default`, `restart_required`, y `requires` donde aplique). `type="csv"` para `STACKY_LEDGER_TEST_MARKERS` (el tipo ya existe: `harness_flags.py:23`, usado en `:564`, `:580`, `:596`, `:629`).
3. **Categoría** — usar una **existente**, no crear una nueva: **`observabilidad_notif`** ("Observabilidad y notificaciones", `harness_flags.py:79`). Registrar cada key en `_CATEGORY_KEYS`; sin esto el meta-test de categorización se pone rojo.
4. **`backend/tests/test_harness_flags.py:467`** — agregar las **4 keys con `default=True`** a `_CURATED_DEFAULTS_ON`. Toda `FlagSpec` con `default=True` debe estar ahí o `test_default_known_only_for_curated` se pone **ROJO**. `STACKY_LEDGER_PURGE_ENABLED` (OFF) **no** va.
5. **`_REQUIRES_MAP_FROZEN`** — declarar la única arista: `STACKY_LEDGER_PURGE_ENABLED` **requires** `STACKY_LEDGER_LEGACY_INFERENCE_ENABLED` (la purga necesita la inferencia para saber qué línea es `test`). **Profundidad 1**, que es lo que la regla R4 permite; prohibido encadenar.
6. **`backend/services/harness_flags_help.py:25`** — una entrada en `PLAIN_HELP` **por cada una de las 6 keys**. `tests/test_harness_flags_help.py` exige cobertura del **100 %** de `FLAG_REGISTRY`: sin esto, ese archivo se pone rojo por culpa de este plan. Cuidado con la denylist de palabras del validador de ayuda (incluye `backend` y `token`): redactar la ayuda en lenguaje de operador, no de implementador — p. ej. "archivo de registro" en vez de "ledger del backend", y "confirmación" en vez de "token".

**No regenerar `harness_defaults.env` a mano.** Si hiciera falta, se usa `deployment/export_harness_defaults.py`. Verificar antes si el archivo está congelado por deuda ajena.

**Tests:**
- `test_las_6_flags_del_258_estan_en_el_registry`
- `test_flags_del_258_tienen_categoria`
- `test_defaults_on_del_258_estan_curados`
- `test_purge_requires_inference`

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -v
.venv\Scripts\python.exe -m pytest tests/test_harness_flags_requires.py -v
```
Ambos verdes. **Nota:** `tests/test_harness_flags_help.py` tiene **4 fallos ajenos preexistentes**; validar la entrada propia aparte y **no** contarlos como regresión de este plan.

**Trabajo del operador: ninguno** (todo queda con default correcto; la UI es para cuando quiera cambiarlo).

---

### F7 — [ADICIÓN ARQUITECTO] Guard de estanqueidad del arnés

**El problema que resuelve.** Todo este plan persigue la contaminación **archivo por archivo y marcador por marcador**: `env_applies.jsonl` por el `root` de pytest, `ci_runs.jsonl` por `myproject`, el log por `DB exploded`. Eso es artesanal y no escala: el próximo ledger que alguien agregue (como `build_runs.jsonl`, que el v1 **ni siquiera vio**) vuelve a estar desprotegido, y nadie se entera hasta que alguien audita el archivo a mano seis meses después.

**El invariante único:** *una corrida del arnés no debe modificar ningún artefacto de runtime del operador.* Un solo enunciado, verificable, que cubre todos los archivos presentes y **futuros**.

**Archivo a crear:** `Stacky Agents/backend/tests/test_plan258_estanqueidad_arnes.py` (registrar en `HARNESS_TEST_FILES`).
**Archivo a crear:** `Stacky Agents/backend/scripts/airtight_snapshot.py` — helper de huellas, sin dependencias externas.

**Símbolos exactos:**

```python
# Rutas vigiladas: TODO artefacto de runtime del operador.
WATCHED_GLOBS = (
    "data/*.jsonl",
    "data/**/*.jsonl",       # incluye data/db_compare/sql_exec_ledger.jsonl
    "data/logs/*.log",
    "data/*.db",
)

def snapshot(root: Path) -> dict[str, tuple[int, str]]:
    """{ruta_relativa: (size_bytes, sha256)} de todo lo que matchea WATCHED_GLOBS.
    Archivo ausente = no aparece en el dict (su aparición TAMBIÉN es un cambio).
    """

def diff_snapshots(before: dict, after: dict) -> list[str]:
    """Lista legible de artefactos creados / modificados / borrados.
    Vacía = la corrida fue estanca.
    """
```

**Cómo se corre (esto resuelve C13).** El gotcha de la casa es que la suite **completa** contamina cross-file y hay que correr **por archivo** — y el runner del arnés (`backend/scripts/run_harness_tests.sh`) **ya itera por archivo**. Entonces el guard **no** es un test que corre dentro de pytest sobre la suite entera: es un **wrapper del runner**.

```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe scripts/airtight_snapshot.py --save   # huella ANTES
bash scripts/run_harness_tests.sh                              # el runner, por archivo
.venv\Scripts\python.exe scripts/airtight_snapshot.py --verify # huella DESPUÉS
```

`--verify` sale con **código 1** y **nombra cada artefacto contaminado** con su delta de bytes. Ese es el criterio binario, y es lo que habría atrapado `env_applies.jsonl` el primer día.

**Casos borde:**
- El operador tiene el backend **corriendo** mientras testea: el server escribe logs legítimamente y el guard daría falso positivo. Mitigación: `--verify` acepta `--ignore-globs` y **por default excluye `data/logs/*.log` del día en curso**, documentando por qué. Los `.jsonl` **no** se excluyen nunca: un ledger no debe crecer por una corrida de tests bajo ninguna circunstancia.
- Archivo nuevo creado por la corrida: cuenta como violación (es exactamente el caso de `ado_edit_learned.jsonl`, que hoy no existe).
- DB `.db` con WAL: se huellea también `-wal`/`-shm` si existen, o se documenta la exclusión. Verificar el `journal_mode` real antes de decidir (dato relevante del plan 253).
- Corrida en un checkout limpio sin `data/`: `snapshot` devuelve `{}` y `--verify` pasa.

**Tests** (en `test_plan258_estanqueidad_arnes.py`):
- `test_snapshot_detecta_modificacion` — se toca un `.jsonl` de prueba y el diff lo nombra.
- `test_snapshot_detecta_archivo_nuevo`
- `test_snapshot_detecta_borrado`
- `test_snapshot_vacio_si_nada_cambia` — **control negativo**: sin cambios, diff vacío. Sin este caso el guard podría estar siempre verde y nadie lo notaría.
- `test_verify_sale_con_codigo_1_y_nombra_el_archivo`

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan258_estanqueidad_arnes.py -v
```
5 verdes, **y** el ciclo `--save` / runner / `--verify` termina en **código 0** tras F1.

**Flag:** `STACKY_HARNESS_AIRTIGHT_GUARD_ENABLED`, **default ON**. Sin excepción dura (es un verificador read-only: huellea y compara, no modifica nada).
**Impacto por runtime:** ninguno en runtime; es infraestructura de test, común a los 3.
**Trabajo del operador: ninguno.**

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| **Reimplementar algo que ya existe** — el v1 lo hizo 3 veces (`close_ci_run`, escritura atómica, token HITL) | Principio explícito en §3: toda función "nueva" viene con el grep que prueba que no existe. F0 caso 8 lo blinda para `update_run_status`. |
| **Regresar el plan 145 al gatear el handler de log** | F5 **no toca** `local_file_logging.py`. `test_install_file_log_handler_conserva_su_firma` impide el cambio de firma, y `test_plan145_pytest_log_isolation.py` debe seguir verde como criterio binario. |
| El campo `env` se descarta en silencio por la allowlist | `ENTRY_FIELDS` se extiende explícitamente y hay un test dedicado (F0 caso 4). |
| Migrar a un `write()` de append degrada retención y allowlist | **No se migra el mecanismo.** Se preservan `_LOCK`, `_write_rows`, `MAX_ROWS` y la allowlist (§3, F1). |
| **Inferir `prod` sobre líneas históricas inventa datos** | `infer_env_for_legacy_line` **nunca** devuelve `prod`. Test de invariante. |
| **El filtro por default oculta datos reales del operador** | Default `("prod","unknown")`, no `"prod"`. Test de regresión con las 436 líneas. |
| Falso positivo por substring en texto libre | Inferencia **por campo** con reglas nombradas + test con `query = "SELECT * FROM pytest_runs"` -> `unknown`. |
| Un proyecto real llamado `myproject` | El marcado **no borra**; la lista es CSV configurable desde la UI; la purga muestra el conteo antes. |
| La purga borra algo real | Solo `env == "test"` probado; `unknown` y `prod` intactos. `dry_run=True` default **y** body explícito obligatorio. Backup. Token. |
| `tmp.replace` falla en Windows con el archivo abierto | Ya está en el camino caliente (E5). La purga reusa `_write_rows` bajo `_LOCK`, con test dedicado. |
| El reporte de huérfanos arranca lleno de fixtures | `orphan_ci_runs` filtra a `env="prod"`, y `now` es inyectable para que el test no dependa del reloj. |
| `telemetry_harvest` sigue roto y bloquea un KPI | Sacado del scope y del KPI. Dependencia del **plan 255** declarada. |
| `confirm_token` no existe todavía | Dependencia del **plan 253 F5** declarada. Si no está, **F4 se bloquea**; no se improvisa un token propio. |
| El guard de F7 da falso positivo con el backend corriendo | `--ignore-globs` + exclusión por default de los `.log` del día. Los `.jsonl` nunca se excluyen. |
| Correr la suite completa contamina cross-file | El guard es un **wrapper del runner** (`run_harness_tests.sh`), que ya corre por archivo. Nunca se pide "correr la suite completa" como criterio. |
| Un ledger sin lock propio no se puede purgar con seguridad | Se declara **no soportado en v1** para ese ledger, en vez de hacerlo inseguro. |

---

## 6. Fuera de scope

- `Stacky tools/QA UAT Agent/data/run_metrics.jsonl` (181 líneas): herramienta separada, con su propio ciclo.
- `services/publish_ledger.py`: **no es un JSONL**, es DB-backed.
- `services/telemetry_harvest.py` y su `NameError`: **plan 255**.
- `services/local_file_logging.py` (throttle, rotación, purga, `LOG_LEVEL`): **plan 257**.
- `services/pipeline_audit_suppressions.py`: **plan 248**.
- `data/db_compare/sql_exec_ledger.jsonl` y `ado_edit_learned.jsonl`: entran al guard de F7, **no** a la migración de F1.
- El `system_logs` de la DB: **plan 253 F4**.
- Migrar los ledgers JSONL a SQLite. El formato es correcto; el problema era la procedencia.
- Rediseñar el esquema de cada ledger. Solo se **agregan** campos (`env`, `schema_version`).

---

## 7. Glosario

| Término | Significado |
|---|---|
| **Ledger** | Archivo JSONL (una línea JSON por evento) que registra hechos del sistema para auditoría. En scope: **5**. |
| **JSONL** | *JSON Lines*: un objeto JSON por línea. |
| **Fixture** | Dato inventado por un test (`myproject`, `newsha`, `http://gitlab/p/42`). |
| **Evento huérfano** | Una corrida de CI **de producción** que se disparó y nunca reportó desenlace. Hoy: **0**, porque no hay corridas reales en el ledger. |
| **Procedencia (`env`)** | Campo nuevo: `prod` (operación real), `test` (corrida de test), `unknown` (histórico sin marca). |
| **`unknown`** | Procedencia honesta de una línea histórica sin marcador. **No** es `prod`, y **no** se oculta por default. |
| **ALLOWLIST (`ENTRY_FIELDS`)** | Tupla cerrada de campos persistibles por ledger. Lo que no está, se descarta al escribir. Guard anti-secretos. |
| **`STACKY_TEST_MODE`** | Env var que indica corrida bajo test. Se lee con `os.getenv(...)`, **no** es atributo de `Config`. |
| **Estanqueidad** | Propiedad de una corrida de tests que **no modifica** ningún artefacto de runtime del operador. Verificada por F7. |
| **`dry_run`** | Modo que cuenta y muestra qué haría, sin hacerlo. Default de la purga. |
| **Excepción dura** | Una de las 4 razones para que una flag nazca OFF: bypasea revisión humana, destructiva, prerequisito no garantizado, reduce seguridad. |

---

## 8. Orden de implementación

1. **F0** — 8 tests (6 rojos, 2 verdes). Registrar en `HARNESS_TEST_FILES` (`.sh`, y sincronizar `.ps1` con su sintaxis propia).
2. **F7 (parte 1)** — `scripts/airtight_snapshot.py` + `--save`. **Se adelanta**: da la línea base con la que se mide todo lo demás.
3. **F1** — `services/ledger_writer.py` + extender `ENTRY_FIELDS` + migrar `ci_runs` y `env_applies`; **`config_transfer_events` al final** como regresión.
4. **Verificación dura** — ciclo `--save` / `run_harness_tests.sh` / `--verify` en código 0.
5. **F5** — guard en `conftest.py` + test de regresión con ventana de fecha. **Verificar que `test_plan145_pytest_log_isolation.py` sigue verde.**
6. **F2** — `infer_env_for_legacy_line` por campo + `read_events` con default `("prod","unknown")`.
7. **F3** — fix de reconciliación `(project, pipeline_id)` en `update_run_status` + `orphan_ci_runs` + `GET /api/diag/ledgers/health` + tarjeta *"Salud de ledgers"*.
8. **F6** — alta de las 6 flags en los 5 lugares (Config + `FlagSpec` + `_CATEGORY_KEYS` + `_CURATED_DEFAULTS_ON` + `_REQUIRES_MAP_FROZEN`).
9. **F4** — purga asistida. **Bloqueada hasta que exista `services/confirm_token.py` (plan 253 F5).**
10. **F7 (parte 2)** — los 5 tests del guard + `--verify` en el flujo del arnés.
11. **Huella de regresión** — entrada en `docs/sistema/error_fingerprints.json` para "ledger del operador escrito por una corrida de test" (existe `backend/services/error_fingerprints.py`).
12. **Verificación final** — `GET /api/diag/ledgers/health` desglosa los 5 ledgers por `env`, y el guard de estanqueidad sale en 0.

**Nota de orden:** F5 se adelanta a F2/F3 aunque esté numerada después, porque es el candado del hallazgo ya cerrado y es barato. F7 se parte en dos porque su primera mitad (la huella base) es prerequisito de la verificación de F1. F4 va última por ser la única destructiva y la única con dependencia externa.

---

## 9. Definición de Hecho (DoD)

- [ ] El ciclo `--save` / `run_harness_tests.sh` / `--verify` sale en **código 0**: la corrida del arnés no modifica ningún `.jsonl`, `.log` ni `.db` del operador.
- [ ] Los 5 ledgers JSONL en scope escriben por `stamp_event` y todo evento nuevo lleva `env` y `schema_version`.
- [ ] `"env"` está en el `ENTRY_FIELDS` de cada ledger que tiene allowlist (si no, el campo se descarta en silencio).
- [ ] Un evento sin sus claves obligatorias **no se escribe** y se loguea a `error`.
- [ ] `infer_env_for_legacy_line` **nunca** devuelve `prod` (invariante con test) y **nunca** marca por substring en texto libre (test con `pytest` dentro de una `query`).
- [ ] `read_events` por default devuelve `prod` **y** `unknown`: las 436 líneas de `config_transfer_events` siguen visibles.
- [ ] `read_events("ci_runs", env=("prod",))` devuelve lista vacía (la verdad de hoy).
- [ ] `update_run_status` reconcilia por `(project, pipeline_id)`; llamarla sin `project` sigue funcionando.
- [ ] `orphan_ci_runs` solo cuenta `env="prod"` y acepta `now` inyectable.
- [ ] `GET /api/diag/ledgers/health` desglosa cada ledger por `env` y lista los huérfanos de CI.
- [ ] La purga tiene `dry_run=True` por default, **exige `dry_run` explícito en el body**, pide token, hace backup y **nunca** borra `unknown` ni `prod`.
- [ ] `install_file_log_handler` **conserva su firma** (`base_dir`, `retention_days`, `-> None`) y `tests/test_plan145_pytest_log_isolation.py` sigue **verde**.
- [ ] El test de regresión de `DB exploded` / `test_reaper` corre **solo sobre logs posteriores al 2026-07-16**, sin allowlist de strings.
- [ ] El `conftest.py` falla ruidosamente si un handler apunta a `backend/data/logs/`, **sin** reemplazar el `setdefault` ni el guard de red que ya están.
- [ ] Las **6** flags están en `config.py`, en `FlagSpec`, en una categoría **existente** (`observabilidad_notif`), en `PLAIN_HELP`, y las 4 con `default=True` están en `_CURATED_DEFAULTS_ON`.
- [ ] La arista `PURGE requires LEGACY_INFERENCE` está en `_REQUIRES_MAP_FROZEN` (profundidad 1).
- [ ] Las 6 flags se cambian **desde la UI**.
- [ ] Los **3** archivos de test nuevos están en `HARNESS_TEST_FILES` (`.sh`), con el `.ps1` sincronizado en su propia sintaxis.
- [ ] Ningún consumidor existente de un ledger se rompió (`devops_overview.py:475-476` y `api/ci.py:248` siguen leyendo bien).
- [ ] Ningún test preexistente pasa a rojo (validar **por archivo**; los 4 fallos de `test_harness_flags_help.py` son ajenos y preexistentes).
- [ ] Huella de regresión agregada en `docs/sistema/error_fingerprints.json`.
