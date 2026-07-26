# Plan 258 — Telemetría veraz: ledgers sin fixtures ni ciclos abiertos

**Estado:** PROPUESTO v1
**Serie:** Robustez desde los logs (253-258). Plan **#6 por retorno** y **cierre de la serie**.
**Fuente:** auditoría de los 6 ledgers JSONL de runtime + los logs de aplicación.

> La auditoría abrió los ledgers JSONL que deberían darle al operador visibilidad de lo que la UI no muestra. Resultado: **`ci_runs.jsonl` tiene 8 de 8 líneas de fixture de test**, **`env_applies.jsonl` tiene 10 de 10 líneas escritas por pytest**, y el mock `"DB exploded"` de un archivo de test aparece **9 veces en el log de la aplicación del operador**. La telemetría de Stacky hoy no es una fuente de verdad: es un archivo mezclado.

---

## 1. Objetivo y KPI

Que todo evento de telemetría sea **trazable a su origen** (producción vs test), que ningún ciclo quede abierto para siempre, y que los tests no puedan volver a escribir en los archivos del operador.

| KPI | Hoy (medido) | Meta |
|---|---|---|
| Líneas de fixture de test en `ci_runs.jsonl` | **8 de 8 = 100 %** | **0** |
| Líneas escritas por pytest en `env_applies.jsonl` | **10 de 10 = 100 %** | **0** |
| Eventos con el ciclo sin cerrar en `ci_runs.jsonl` (`last_status=null`) | **8 de 8 = 100 %** | **0** eventos > 24 h sin cerrar |
| Mensajes de mock de test en el log de la app | **13** (`DB exploded` ×9, `test_reaper` ×4) | **0** |
| Ledgers con campo de procedencia (`env`) | **0 de 6** | **6 de 6** |
| Ledgers con esquema validado al escribir | **0 de 6** | **6 de 6** |

---

## 2. Evidencia real (anclaje anti-alucinación)

### E1 — `ci_runs.jsonl`: 100 % fixture y 100 % ciclo abierto

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

**Dos defectos independientes en un archivo de 8 líneas:**

1. **Contaminación total.** `"project": "myproject"`, `"sha": "newsha"`, `"web_url": "http://gitlab/p/42"` — son valores de fixture. Ningún proyecto real del operador se llama `myproject` (los reales son `RSPACIFICO`, `RSSICREA`, `RIPLEY`). El archivo **no contiene ni un evento real**.
2. **Ciclo nunca cerrado.** `last_status: null` y `finished_at: null` en **8 de 8**. El ledger registra el disparo de una pipeline y **nunca** el desenlace. Un panel de CI alimentado por esto mostraría 8 pipelines eternamente "en curso".

### E2 — `env_applies.jsonl`: escrito íntegramente por pytest

10 líneas, 4.422 bytes. `grep -c "pytest"` → **10**. **Las 10.** Primera línea literal:

```json
{"root": "C:\\Users\\juanluca\\AppData\\Local\\Temp\\pytest-of-juanluca\\pytest-1877\\test_f4_apply_creates_and_repo0",
 "server_alias": null, "paths": ["IN_", "productivas", "salida"], "paths_truncated": false,
 "fingerprint": "c6cb5b63c18e02f29202c0b9f0b51b1a245a537255d1663792ce3688706832ae",
 "sandbox_active": false, "result_ok": true, "created_count": 3, "ignored_count": 0, ...}
```

El `root` apunta a `pytest-of-juanluca\pytest-1877\test_f4_apply_creates_and_repo0`: un directorio temporal de pytest. **El ledger de aplicación de entornos del operador contiene exclusivamente corridas de test.** Nótese `"result_ok": true`: si un panel contara éxitos, reportaría 10 aplicaciones exitosas que nunca ocurrieron.

### E3 — Los tests escriben en el log de la aplicación

Firma en los logs de la app:

```
9 ERROR [stacky_agents.adaptive_selector] _load_last_project_confidence: error inesperado: DB exploded
```

Serie: `stacky-2026-07-12.log`=6, `stacky-2026-07-14.log`=1, `stacky-2026-07-15.log`=2.

**`"DB exploded"` es un string de mock que existe en un solo lugar del repo:**

```python
# Stacky Agents/backend/tests/test_adaptive_selector_wiring.py:260
        sess.query.side_effect = RuntimeError("DB exploded")
```

Un `RuntimeError` inventado por un test aparece **9 veces como `ERROR` en el log de producción** del operador. Cualquiera que audite ese log va a investigar un fallo de base de datos que nunca existió.

Lo mismo con el reaper:

```
4 WARNING [stacky.ticket_status] reaper[test_reaper]: exec_id=1 ticket_id=1 timed_out after N min
```

El trigger `"test_reaper"` viene de:

```python
# Stacky Agents/backend/tests/test_cutover_p5.py:505
    details = recover_stale_running_tickets(trigger="test_reaper")
```

Y los `exec_id`/`ticket_id` valen **1** — ids de fixture. Aparecen mezclados con los reaper reales (`reaper[timeout_guardian]` ×11, `reaper[manual]` ×8) sobre tickets de verdad. **El operador no puede distinguir cuál barrida fue real.**

Existe una variable para esto: `STACKY_TEST_MODE` (`Stacky Agents/backend/services/local_file_logging.py:61`). **No está gateando estas escrituras.**

### E4 — El resto del inventario, con honestidad

| Ledger | Líneas | Bytes | Estado |
|---|---|---|---|
| `backend/data/ci_runs.jsonl` | 8 | 2.026 | **100 % fixture, 100 % ciclo abierto** |
| `backend/data/env_applies.jsonl` | 10 | 4.422 | **100 % pytest** |
| `backend/data/db_query_audit.jsonl` | 9 | 4.157 | 9/9 `result: "would_execute"` — nada se ejecutó de verdad. **Correcto** (la flag está OFF por diseño), pero sin campo que distinga dry-run de real más allá de ese valor. |
| `backend/data/config_transfer_events.jsonl` | 436 | 140.797 | **LIMPIO.** `grep -c "pytest\|myproject\|test_"` → **0**. Datos reales desde 2026-06-19. Es el único ledger sano y sirve de **modelo** para los demás. |
| `DeployStackyAgents/data/db_query_audit.jsonl` | 2 | 875 | Real (`RSPACIFICO`, ticket 377), ambas `would_execute`. |
| `Stacky tools/QA UAT Agent/data/run_metrics.jsonl` | 181 | 136.158 | Datos desde 2026-05-09. No auditado en profundidad; **fuera del alcance de este plan** (herramienta separada). |

**Que `config_transfer_events.jsonl` esté limpio con 436 líneas prueba que el problema no es estructural del formato JSONL, sino de **qué ledgers gatean la escritura en test-mode y cuáles no**. Hay un patrón correcto en el repo: hay que replicarlo.

---

## 3. Principios y guardarraíles (obligatorios)

- **Human-in-the-loop:** la limpieza de las líneas contaminadas es **destructiva** → detrás de confirmación explícita con el conteo a la vista. Stacky no borra datos del operador por su cuenta, ni siquiera datos que sabe que son basura.
- **No borrar por default, marcar.** F2 **no** elimina las líneas viejas: les agrega procedencia inferida. El borrado es opt-in (F4). Es más seguro marcar que borrar, y preserva la posibilidad de auditar.
- **Mono-operador sin auth.**
- **Paridad de 3 runtimes:** los ledgers son transversales. Ninguno es específico de un runtime; el gate de test-mode y el campo de procedencia aplican igual a los 3.
- **Cero trabajo extra al operador:** F0-F3 son invisibles. F4 es un botón opcional.
- **No degradar:** el campo `env` es **aditivo**. Un lector viejo que ignore campos desconocidos sigue funcionando. Ningún consumidor existente se rompe.
- **Flags default ON** salvo la de limpieza destructiva (excepción dura #2).
- **Toda flag configurable desde la UI.**

---

## 4. Fases

### F0 — Tests que prueban la contaminación

**Archivo a crear:** `Stacky Agents/backend/tests/test_plan258_ledger_veracidad.py`
**Registrar en:** `HARNESS_TEST_FILES` de `Stacky Agents/backend/scripts/run_harness_tests.sh`.

**Casos exactos:**

1. `test_append_en_test_mode_no_escribe_el_ledger_real` — con `STACKY_TEST_MODE` activo, un append a `ci_runs.jsonl` **no** toca el archivo de `backend/data/`. **Hoy falla.**
2. `test_append_en_test_mode_escribe_ruta_aislada` — en test-mode el ledger va a un `tmp_path`, no a `backend/data/`.
3. `test_todo_evento_lleva_campo_env` — todo evento nuevo tiene `env` ∈ `{"prod","test"}`. **Hoy falla** (el campo no existe).
4. `test_ledger_valida_esquema_al_escribir` — un evento sin las claves obligatorias es rechazado y **no** se escribe. **Hoy falla.**
5. `test_ci_run_se_cierra_con_last_status` — tras `close_ci_run(pipeline_id, status)`, la línea tiene `last_status` y `finished_at` no nulos. **Hoy falla** (no existe la función).
6. `test_ci_runs_huerfanos_se_detectan` — un evento de > 24 h con `last_status=null` aparece en el reporte de huérfanos. **Hoy falla.**
7. `test_lector_ignora_campos_desconocidos` — una línea con una clave futura no rompe el lector (blinda la compatibilidad hacia adelante).

**Comando exacto:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan258_ledger_veracidad.py -v
```

**Criterio binario:** los 7 existen; 1, 3, 4, 5, 6 **fallan** antes de F1.

**Flag:** ninguna. **Trabajo del operador: ninguno.**

---

### F1 — Un solo portero para los 6 ledgers

**Objetivo:** que ningún ledger pueda escribirse desde un test en el archivo del operador, y que todo evento declare su procedencia.

**Archivo a crear:** `Stacky Agents/backend/services/ledger_writer.py` — la puerta única.

**Símbolos nuevos exactos:**

```python
LEDGER_NAMES = ("ci_runs", "config_transfer_events", "db_query_audit",
                "env_applies", "telemetry_harvest", "publish_ledger")

REQUIRED_KEYS = {
    "ci_runs": ("project", "tracker_type", "pipeline_id", "triggered_at"),
    "env_applies": ("root", "fingerprint", "applied_at"),
    "db_query_audit": ("ts", "project", "actor", "result"),
    "config_transfer_events": ("ts", "action", "project", "result"),
    "telemetry_harvest": ("ts", "execution_id"),
    "publish_ledger": ("ts", "ado_id"),
}

def ledger_path(name: str) -> Path:
    """Ruta del ledger `name`. En test-mode devuelve una ruta AISLADA bajo
    el tmpdir del proceso, NUNCA backend/data/.
    """

def append_event(name: str, event: dict, *, allow_incomplete: bool = False) -> bool:
    """Escribe UNA línea JSON en el ledger `name`.

    - Inyecta `env` = 'test' si config.STACKY_TEST_MODE else 'prod'.
    - Inyecta `schema_version` si falta.
    - Valida REQUIRED_KEYS: si falta alguna, NO escribe y loguea a error
      (salvo allow_incomplete=True).
    - Escritura atómica: una sola llamada write() con la línea completa + '\n'.
    Devuelve True si escribió.
    """

def read_events(name: str, *, env: str | None = "prod") -> list[dict]:
    """Lee el ledger filtrando por procedencia. `env=None` devuelve todo.

    Las líneas SIN campo `env` (históricas) se tratan según
    `infer_env_for_legacy_line` (F2). Ignora claves desconocidas.
    """
```

**Regla clave — el filtro por default es `env="prod"`:** cualquier consumidor que hoy lee un ledger crudo pasa a leer solo eventos de producción **sin cambiar su código**, apenas migre a `read_events`. Ese default es lo que hace el fix efectivo en vez de teórico.

**Aislamiento en test-mode:** `ledger_path` consulta `config.STACKY_TEST_MODE` (ya existe, `services/local_file_logging.py:61`) y devuelve `Path(tempfile.gettempdir()) / f"stacky-test-ledgers/{name}.jsonl"`. Los tests que **quieran** verificar el contenido usan `ledger_path` y encuentran su archivo aislado. **Cero cambios en los asserts** de los tests existentes que ya usan la ruta a través de la función.

**Migración de los call-sites:** los 6 ledgers pasan a escribir por `append_event`. El ledger que ya funciona bien (`config_transfer_events`, 436 líneas limpias) migra **último** y sirve de test de regresión: si después de migrar sigue igual de limpio, la puerta está bien hecha.

**Casos borde:**
- Ledger que se escribe desde un thread daemon durante el teardown de pytest: `STACKY_TEST_MODE` sigue activo → va al archivo aislado. **Este es el mecanismo exacto por el que se contaminó `env_applies.jsonl`.**
- Evento incompleto en un path legítimo: `allow_incomplete=True` explícito en el call-site, nunca por default.
- Escritura concurrente desde dos threads: una sola llamada `write()` con la línea completa. En Windows, un `write` de < 4 KB a un archivo abierto en modo append es atómico en la práctica; documentar el límite y truncar campos largos antes de escribir.
- Disco lleno: `append_event` devuelve `False` y loguea a `error`. **No levanta** (un ledger no debe tumbar la operación que audita).

**Tests:** casos 1, 2, 3, 4, 7 de F0 a verde.

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan258_ledger_veracidad.py -k "test_mode or env or esquema or desconocidos" -v
```
5 verdes. **Y la prueba dura:** correr la suite completa del arnés y verificar que `backend/data/env_applies.jsonl` **no crece ni una línea**:
```
wc -l < data/env_applies.jsonl   # antes y después: mismo número
```

**Flag:** `LEDGER_STRICT_SCHEMA_ENABLED`, **default ON**. Sin excepción dura: no bypasea revisión, no es destructiva (rechazar una escritura inválida no borra nada), sin prerequisito, no reduce seguridad.
**Impacto por runtime:** transversal.
**Trabajo del operador: ninguno.**

---

### F2 — Procedencia de lo histórico, sin borrar nada

**Objetivo:** que las 18 líneas contaminadas ya existentes queden **marcadas**, no eliminadas.

**Archivo a editar:** `Stacky Agents/backend/services/ledger_writer.py`.

**Símbolo nuevo exacto:**

```python
_TEST_MARKERS = (
    "pytest-of-", "pytest-", "/tmp/pytest", "myproject", "newsha",
    "http://gitlab/p/", "DB exploded", "test_reaper", "localhost/p/",
)

def infer_env_for_legacy_line(event: dict) -> str:
    """Plan 258 F2 — procedencia de una línea SIN campo `env`.

    Devuelve 'test' si algún valor string del evento contiene un marcador
    inequívoco de fixture; 'unknown' en caso contrario.

    NUNCA devuelve 'prod' por inferencia: una línea histórica sin marca es
    'unknown', no 'prod'. Afirmar procedencia sin evidencia sería inventar
    datos, que es exactamente el problema que este plan resuelve.
    """
```

**Esa última regla es el corazón de la fase.** Es tentador asumir que lo no-marcado es producción; sería adivinar. `unknown` es honesto y el operador puede filtrar por `env in ("prod","unknown")` si quiere ver todo.

**Aplicación de los marcadores a la evidencia medida:**

| Ledger | Líneas | Inferencia esperada |
|---|---|---|
| `ci_runs.jsonl` | 8 | **8 → `test`** (`myproject`, `newsha`, `http://gitlab/p/`) |
| `env_applies.jsonl` | 10 | **10 → `test`** (`pytest-of-`) |
| `db_query_audit.jsonl` | 9 | 9 → `unknown` (sin marcador; son reales pero no verificable por marca) |
| `config_transfer_events.jsonl` | 436 | 436 → `unknown` (limpio, sin marcador de test) |

**Nota importante:** `db_query_audit` y `config_transfer_events` quedan en `unknown`, no en `prod`. Eso es correcto y deliberado. Los eventos **nuevos** (post-F1) llevan `env` explícito, y con el tiempo `unknown` se extingue solo. No se reescribe la historia.

**Casos borde:**
- Un proyecto real que se llamara `myproject`: falso positivo. Documentar los marcadores en el docstring y hacerlos **configurables** vía `config.LEDGER_TEST_MARKERS` para que el operador pueda quitar uno si le molesta.
- Marcador dentro de un campo de texto libre legítimo (p. ej. una `query` de auditoría que mencione `pytest`): por eso el marcado **no borra**; solo etiqueta.
- Evento con `env` ya presente: `infer_env_for_legacy_line` **no se llama**. El campo explícito siempre gana.

**Tests:** en `test_plan258_ledger_veracidad.py`:
- `test_infer_env_detecta_pytest_root` — la línea real de `env_applies.jsonl` → `test`.
- `test_infer_env_detecta_myproject_fixture` — la línea real de `ci_runs.jsonl` → `test`.
- `test_infer_env_nunca_devuelve_prod` — invariante: sobre 100 eventos arbitrarios, ninguno da `prod`.
- `test_infer_env_no_se_llama_si_env_presente`
- `test_read_events_prod_excluye_test_y_unknown`
- `test_read_events_env_none_devuelve_todo`

**Criterio binario:** 6 verdes. Y `read_events("ci_runs")` con el default `env="prod"` devuelve **lista vacía** — que es la verdad: no hay ni un evento real de CI.

**Flag:** `LEDGER_LEGACY_INFERENCE_ENABLED`, **default ON**. Sin excepción dura (solo etiqueta en memoria al leer; **no modifica los archivos**).
**Impacto por runtime:** transversal.
**Trabajo del operador: ninguno.**

---

### F3 — Cerrar el ciclo de `ci_runs` y detectar huérfanos

**Objetivo:** que un evento con `last_status=null` deje de ser el estado final permanente.

**Archivos a editar:**
1. `Stacky Agents/backend/services/ci_run_ledger.py` (el módulo que escribe `ci_runs.jsonl`).
2. `Stacky Agents/backend/api/diag.py` — reporte de huérfanos.

**Símbolos nuevos exactos:**

```python
def close_ci_run(pipeline_id: str, *, project: str, last_status: str,
                 finished_at: str | None = None) -> bool:
    """Plan 258 F3 — cierra un evento de CI: escribe una línea NUEVA de cierre
    con `event_type='close'`, sin reescribir la de disparo.

    El ledger es append-only: reescribir líneas es una fuente de corrupción.
    El lector reconcilia disparo + cierre por pipeline_id.
    """

def orphan_ci_runs(*, older_than_h: float = 24.0) -> list[dict]:
    """Eventos de disparo sin cierre con más de `older_than_h` horas.
    Lo que el operador necesita saber: 'esta pipeline se disparó y nunca supimos
    cómo terminó'.
    """
```

**Decisión de diseño (append-only):** cerrar un run **no** reescribe la línea original; agrega una línea de cierre. Reescribir un JSONL in place implica leer todo, modificar y reescribir — y una interrupción a mitad de camino corrompe el archivo entero. El lector reconcilia. Este es el mismo criterio del ledger de publicación que ya existe en el repo.

**Cableado del cierre:** engancharlo al poller de estado de CI que ya existe (el que produce `ado-pipeline-status falló para ticket N` en los logs, `api/tickets.py`). Cuando ese poller obtiene un estado terminal, llama `close_ci_run`. **No crear un poller nuevo.**

**Casos borde:**
- Cierre de un `pipeline_id` que nunca se disparó (evento huérfano inverso): se escribe igual con `"orphan_close": true`. Perder información no es opción.
- Dos cierres del mismo `pipeline_id`: el lector toma el **último** por `finished_at`. Documentado.
- `pipeline_id` que se repite entre proyectos: la clave de reconciliación es `(project, pipeline_id)`, no `pipeline_id` solo. En la evidencia medida hay `pipeline_id` 42 repetido 6 veces — con clave simple se reconciliarían mal.

**Reporte de huérfanos:** `GET /api/diag/ledgers/health` devuelve, por ledger: total de líneas, desglose por `env`, y para `ci_runs` la lista de huérfanos. Tarjeta en el panel de diagnóstico si hay algo que reportar.

**Tests:** casos 5 y 6 de F0 a verde. Sumar:
- `test_close_ci_run_no_reescribe_la_linea_original` — la línea de disparo queda byte-idéntica.
- `test_reconciliacion_por_project_y_pipeline_id` — mismo `pipeline_id` en dos proyectos no se cruza.
- `test_dos_cierres_gana_el_ultimo`
- `test_orphan_close_se_marca`
- `test_endpoint_ledgers_health_desglosa_por_env`

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan258_ledger_veracidad.py -v
```
todo verde, y `GET /api/diag/ledgers/health` reporta `ci_runs: {prod: 0, test: 8, unknown: 0, orphans: 0}` — **la verdad medible** sobre el estado actual.

**Flag:** `CI_RUN_LEDGER_CLOSE_ENABLED`, **default ON**. Sin excepción dura.
**Impacto por runtime:** el ledger de CI es del orquestador, común a los 3 runtimes. Para el proveedor GitLab y para ADO el cierre usa el `CIProvider` que ya existe; si un proveedor no expone estado terminal, el evento queda huérfano y **aparece en el reporte** en vez de desaparecer. Fallback explícito.
**Trabajo del operador: ninguno.**

---

### F4 — Limpieza asistida (HITL, la única pieza destructiva)

**Objetivo:** darle al operador la opción de purgar las 18 líneas de fixture, con el conteo a la vista.

**Archivos a editar:**
1. `Stacky Agents/backend/api/diag.py` — `POST /api/diag/ledgers/purge-test-lines`.
2. `Stacky Agents/backend/services/ledger_writer.py` — la función de purga.

**Símbolo nuevo exacto:**

```python
def purge_test_lines(name: str, *, confirm_token: str, dry_run: bool = True) -> dict:
    """Plan 258 F4 — elimina las líneas con env='test' (o inferido 'test').

    dry_run=True (DEFAULT) solo cuenta y devuelve un preview.
    Con dry_run=False exige confirm_token y hace backup previo del .jsonl
    a data/backups/<name>-<timestamp>.jsonl antes de reescribir.

    NUNCA toca líneas 'prod' ni 'unknown'.
    """
```

**Contrato HITL, no negociable:**
1. `dry_run=True` es el **default del parámetro**. Un llamador que olvide el argumento no borra nada.
2. `GET /api/diag/ledgers/health` emite el `confirm_token` (TTL 120 s) con el conteo exacto por ledger.
3. La UI muestra: *"Se eliminarán 8 líneas de fixture de ci_runs.jsonl y 10 de env_applies.jsonl. Las 436 de config_transfer_events y las 9 de db_query_audit (procedencia desconocida) NO se tocan. Se guarda una copia antes."*
4. Backup obligatorio previo. Si el backup falla, **se aborta**.
5. `unknown` **nunca** se purga. Solo lo probadamente `test`.

**Casos borde:**
- Ledger escribiéndose mientras se purga: tomar el lock del writer, o reescribir a un temporal y hacer `os.replace`. **Ojo con el gotcha conocido del repo:** `os.replace` en Windows falla si el archivo está abierto por otro handle. Cerrar el handle del writer antes, o reintentar con backoff.
- Ledger vacío o inexistente: `{"deleted": 0}`, sin error.
- Token expirado: `409`.

**Tests:** `Stacky Agents/backend/tests/test_plan258_ledger_purge.py` (agregar al ratchet):
- `test_purge_dry_run_es_el_default` — sin argumentos, no borra.
- `test_purge_sin_token_devuelve_409`
- `test_purge_hace_backup_antes`
- `test_purge_aborta_si_falla_el_backup` — el ledger queda intacto.
- `test_purge_nunca_borra_unknown_ni_prod`
- `test_purge_con_archivo_abierto_no_corrompe` — el gotcha de `os.replace` en Windows.
- `test_purge_ledger_inexistente_devuelve_cero`

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan258_ledger_purge.py -v
```
7 verdes.

**Flag:** `LEDGER_PURGE_ENABLED`, **default OFF**. Cita la **excepción dura #2: destructiva/irreversible** (elimina líneas de un archivo del operador). Se prende desde la UI cuando el operador quiera limpiar.
**Impacto por runtime:** transversal.
**Trabajo del operador:** opt-in, un clic, con el conteo exacto y un backup. Es la excepción justificada al "cero trabajo".

---

### F5 — Que los tests no vuelvan a escribir en el log del operador

**Objetivo:** cerrar el agujero de E3: los mocks de test dejando `ERROR` en el log de producción.

**Archivos a editar:**
1. `Stacky Agents/backend/services/local_file_logging.py` — gate en `install_file_log_handler` (`:154`).
2. `Stacky Agents/backend/tests/conftest.py` — refuerzo.

**Cambio exacto:** `install_file_log_handler` no instala el handler de archivo cuando `config.STACKY_TEST_MODE` está activo, salvo que se pida explícitamente:

```python
def install_file_log_handler(*, force: bool = False) -> bool:
    """... (docstring existente) ...

    Plan 258 F5 — en test-mode NO se instala el handler que escribe en
    backend/data/logs/: los tests no deben contaminar el log del operador.
    Un test que necesite verificar el archivo pasa force=True y una ruta tmp.
    """
    if config.STACKY_TEST_MODE and not force:
        return False
```

**Refuerzo en `conftest.py`:** un fixture `autouse` de sesión que asserta que ningún handler activo apunta a `backend/data/logs/`. Si aparece uno, el test **falla ruidosamente** en vez de contaminar en silencio.

**Prueba de regresión (la que cierra el hallazgo):**

```python
def test_suite_no_contamina_el_log_del_operador(tmp_path):
    """Plan 258 F5 — regresión del hallazgo real: 'DB exploded' (mock de
    tests/test_adaptive_selector_wiring.py:260) aparecía 9 veces en
    backend/data/logs/, y 'test_reaper' (tests/test_cutover_p5.py:505) 4 veces.
    """
    log_dir = Path(__file__).resolve().parents[1] / "data" / "logs"
    for f in log_dir.glob("stacky-*.log"):
        txt = f.read_text(encoding="utf-8", errors="replace")
        assert "DB exploded" not in txt, f"mock de test en {f.name}"
        assert "test_reaper" not in txt, f"trigger de test en {f.name}"
```

**Nota honesta para quien implemente:** este test **va a fallar** contra los logs históricos (07-12, 07-14, 07-15 tienen `DB exploded`; hay 4 `test_reaper`). Dos opciones válidas:
- **(a) recomendada:** el test escanea solo logs con fecha **posterior** a la implementación del plan. Verifica la regresión sin exigir borrar historia.
- **(b)** el operador purga los logs viejos con la retención de 14 días del plan 257 y el test pasa naturalmente.

**No** hacer que el test pase agregando los strings a una allowlist: eso sería gamear el gate.

**Casos borde:**
- Test que legítimamente verifica el logging a archivo: usa `force=True` + `tmp_path`.
- `STACKY_TEST_MODE` no seteado al correr pytest: el fixture `autouse` del `conftest.py` lo setea.
- Thread daemon que loguea durante el teardown: el handler ya no está instalado → no escribe.

**Tests:** en `test_plan258_ledger_veracidad.py`:
- `test_install_file_log_handler_no_instala_en_test_mode`
- `test_install_file_log_handler_con_force_si_instala`
- `test_conftest_asserta_que_no_hay_handler_al_log_real`
- `test_suite_no_contamina_el_log_del_operador` (variante (a), solo logs nuevos)

**Criterio binario:** 4 verdes. Y tras correr la suite del arnés, `wc -c` de los archivos de `backend/data/logs/` **no cambia**.

**Flag:** ninguna — es un gate de test, no runtime.
**Impacto por runtime:** ninguno (solo afecta al modo test).
**Trabajo del operador: ninguno.**

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| **Inferir `prod` sobre líneas históricas inventa datos** — riesgo #1 | `infer_env_for_legacy_line` **nunca** devuelve `prod`. Solo `test` (con marcador inequívoco) o `unknown`. Hay un test que lo blinda como invariante. |
| El filtro `env="prod"` por default oculta datos reales sin marca | Los históricos quedan `unknown`, y el operador puede pedir `env=None`. El reporte de F3 muestra el desglose completo por `env`. Los eventos nuevos llevan marca explícita, así que `unknown` se extingue. |
| Un proyecto real llamado `myproject` da falso positivo | El marcado **no borra**. Y los marcadores son configurables vía `config.LEDGER_TEST_MARKERS`. |
| La purga borra algo real | Solo toca `env == "test"` probado; `unknown` y `prod` intactos. `dry_run=True` es el default. Backup obligatorio. Token de confirmación. |
| `os.replace` falla en Windows con el archivo abierto | Gotcha conocido de este repo. Cerrar el handle del writer antes, y test dedicado (`test_purge_con_archivo_abierto_no_corrompe`). |
| Gatear el handler de log en test-mode rompe tests que verifican logging | `force=True` para esos casos. Y hay un gotcha conocido en este repo: gatear algo entero en test-mode puede regresar un bug viejo — por eso el gate es **solo** del handler de archivo, no del logging entero. |
| El test de regresión de logs falla por historia vieja | Documentado explícitamente: escanear solo logs posteriores a la implementación. **Prohibido** gamearlo con allowlist. |
| Migrar 6 ledgers a la puerta única rompe un consumidor | `config_transfer_events` (el limpio, 436 líneas) migra **último** y sirve de regresión. Los lectores ignoran campos desconocidos (test dedicado). |
| El ledger tumba la operación que audita | `append_event` devuelve `False` y loguea; **nunca** levanta. |

---

## 6. Fuera de scope

- `Stacky tools/QA UAT Agent/data/run_metrics.jsonl` (181 líneas): herramienta separada, con su propio ciclo. Se inventaría en E4 y no se toca.
- Migrar los ledgers JSONL a la DB SQLite. El formato append-only es correcto para esto; el problema era la procedencia, no el formato.
- Rediseñar el esquema de cada ledger. Solo se **agregan** campos (`env`, `schema_version`).
- El `system_logs` de la DB → **plan 253 F4**.
- El ruido del log de aplicación → **plan 257**.
- Los mocks que **deberían** poder loguear en sus propios tests: siguen pudiendo, con `force=True`.

---

## 7. Glosario

| Término | Significado |
|---|---|
| **Ledger** | Archivo append-only (una línea JSON por evento) que registra hechos del sistema para auditoría. Stacky tiene 6. |
| **JSONL** | *JSON Lines*: un objeto JSON por línea. Permite append sin releer el archivo. |
| **Fixture** | Dato inventado por un test (`myproject`, `newsha`, `http://gitlab/p/42`). No corresponde a nada real. |
| **Evento huérfano** | Un disparo sin su cierre: se registró el inicio y nunca el desenlace. 8 de 8 en `ci_runs.jsonl`. |
| **Procedencia (`env`)** | Campo nuevo: `prod` (operación real), `test` (corrida de test), `unknown` (histórico sin marca). |
| **`unknown`** | Procedencia honesta de una línea histórica sin marcador. **No** es `prod`: afirmarlo sería adivinar. |
| **`STACKY_TEST_MODE`** | Variable que indica que el proceso corre bajo test. Ya existe (`services/local_file_logging.py:61`); este plan la usa para aislar escrituras. |
| **Append-only** | Nunca reescribir líneas existentes; solo agregar. Evita corromper el archivo si el proceso se interrumpe. |
| **`dry_run`** | Modo que cuenta y muestra qué haría, sin hacerlo. Default de la purga. |
| **Excepción dura** | Una de las 4 razones para que una flag nazca OFF: bypasea revisión humana, destructiva, prerequisito no garantizado, reduce seguridad. |

---

## 8. Orden de implementación

1. **F0** — 7 tests, rojos. Registrar en `HARNESS_TEST_FILES`.
2. **F1** — `services/ledger_writer.py` (puerta única) + migrar 5 ledgers; **`config_transfer_events` al final** como regresión.
3. **Verificación dura:** correr la suite del arnés y confirmar que `env_applies.jsonl` **no crece**.
4. **F5** — gate del handler de log en test-mode + fixture `autouse` en `conftest.py`. **Se adelanta a F2/F3** porque es lo que detiene la contaminación en curso.
5. **F2** — `infer_env_for_legacy_line` + `read_events(env="prod")` por default.
6. **F3** — `close_ci_run` append-only + `orphan_ci_runs` + `GET /api/diag/ledgers/health` + tarjeta.
7. **F4** — purga asistida con `dry_run` default, token, backup y flag default OFF.
8. Exponer las 4 flags nuevas en el panel de flags y en `api/global_config.py`.
9. Verificación final: `GET /api/diag/ledgers/health` reporta el desglose por `env` de los 6 ledgers, y ningún ledger recibe líneas de test al correr el arnés.

**Nota de orden:** F5 va **antes** de F2/F3 aunque esté numerada después, porque detiene el sangrado. Está numerada al final para que las fases del eje "ledgers" queden contiguas.

---

## 9. Definición de Hecho (DoD)

- [ ] Correr la suite completa del arnés **no agrega ni una línea** a los ledgers de `backend/data/`.
- [ ] Correr la suite completa del arnés **no cambia el tamaño** de los archivos de `backend/data/logs/`.
- [ ] Los 6 ledgers escriben por `append_event` y todo evento nuevo lleva `env` y `schema_version`.
- [ ] Un evento sin sus claves obligatorias **no se escribe** y se loguea a `error`.
- [ ] `infer_env_for_legacy_line` **nunca** devuelve `prod` (invariante con test).
- [ ] `read_events("ci_runs")` con default `env="prod"` devuelve lista vacía (la verdad de hoy).
- [ ] `close_ci_run` agrega una línea de cierre **sin** reescribir la de disparo.
- [ ] La reconciliación usa `(project, pipeline_id)`, no `pipeline_id` solo.
- [ ] `GET /api/diag/ledgers/health` desglosa cada ledger por `env` y lista los huérfanos de CI.
- [ ] La purga tiene `dry_run=True` por default, exige token, hace backup y **nunca** borra `unknown` ni `prod`.
- [ ] `install_file_log_handler` no instala el handler de archivo en test-mode salvo `force=True`.
- [ ] El `conftest.py` falla ruidosamente si un handler apunta a `backend/data/logs/`.
- [ ] El test de regresión de `DB exploded` / `test_reaper` corre sobre logs posteriores a la implementación, **sin allowlist**.
- [ ] Los 2 archivos de test nuevos están en `HARNESS_TEST_FILES`.
- [ ] Las 4 flags nuevas se cambian **desde la UI**.
- [ ] Ningún consumidor existente de un ledger se rompió (los lectores ignoran campos desconocidos).
- [ ] Ningún test preexistente pasa a rojo (validar **por archivo**).
