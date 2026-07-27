# Plan 257 — Observabilidad antirruido: throttle, retención y nivel de log desde la UI

**Estado:** CRITICADO v2
**Versión:** v1 -> v2 (juez adversarial, 2026-07-26). Veredicto de v1: **RECHAZADO** (5 bloqueantes).
**Serie:** Robustez desde los logs (253-258). Plan **#5 por retorno**.
**Fuente:** auditoría de ~16 MB de logs reales de `Stacky Agents/backend/data/logs/`.

> Los 14 logs auditados suman ~16 MB, y **una sola firma repetida** se come el 71 % de los warnings del peor día. El ruido no es un problema estético: es la razón por la que los tres bugs del plan 255 sobrevivieron días sin que nadie los viera. Y el mecanismo de throttle **ya está escrito en el repo, con cero call-sites en producción**.

---

## 0. CHANGELOG v1 -> v2

Todo lo de abajo se verificó abriendo el archivo real y contando líneas. Cada bullet cierra un hallazgo de la crítica.

- **C1 (BLOQUEANTE) — `_env_bool` no existe en `config.py`.** v1 escribía `LOG_THROTTLE_ENABLED = _env_bool("LOG_THROTTLE_ENABLED", True)`. `grep -rn "_env_bool" backend/` da 3 hits y **los 3 están en `services/memory_git_sync.py`** (def en `:1057`). Al ser una asignación en el cuerpo de `class Config`, el `NameError` explota **en import time** y `db.py:5` / `app.py:34` hacen `from config import config` ⇒ **backend muerto al arrancar**. v2 usa el idioma real de la casa: `os.getenv("X", "true").strip().lower() == "true"`.
- **C2 (BLOQUEANTE) — la llamada a `log_throttled` de v1 no compila.** Firma REAL (`services/log_throttle.py:30`): `log_throttled(key, logger, level: int, msg, *args, min_interval_s: float = 60.0)`. v1 escribía `log_throttled(logger, "warning", key=..., min_interval_s=300, msg=..., outputs_dir)`: primer posicional cambiado, `level` como string en vez de int de `logging`, y un **posicional después de keywords = `SyntaxError`**. v2 trae la firma correcta y un ejemplo copiable.
- **C3 (BLOQUEANTE) — la firma de log destruía el `levelno`.** v1 hacía `base = f"{name}|{levelno}|{msg}"` y después `re.sub(r"\d+", "N", base)` ⇒ `30` → `N`: WARNING e INFO del mismo logger colapsaban en la misma firma. v2 normaliza **solo el tramo del mensaje** y concatena `name|levelno` después.
- **C4 (BLOQUEANTE) — el filtro en un solo handler no cubre los otros dos sumideros.** El root logger tiene ≥3 handlers: el `StreamHandler` de `logging.basicConfig` (`app.py:365`), `_DailyStackyFileHandler` (`local_file_logging.py:176`) y `_SystemLogHandler` (`console_log_handler.py:85`, **persiste cada record en la tabla `SystemLog`**). Con el filtro solo en el archivo, las mismas 1016 repeticiones seguían escribiendo 1016 filas en `system_logs` — el volumen exacto que el plan 253 tiene que purgar. v2 instala **una instancia compartida en todos los handlers del root**, con memo por record para no contar N veces.
- **C5 (BLOQUEANTE) — el resumen `×N` sólo salía si la firma volvía a aparecer.** Un loop que termina (el caso REAL: `preflight: outputs_dir` = 237 el 07-12 y después se apagó) perdía el conteo final. v1 afirmaba "la información no se pierde": era falso. → **[ADICIÓN ARQUITECTO] F1-ter: flush determinista** (§4).
- **C6 — el conteo de flags estaba mal:** v1 decía "5 flags nuevas" y creaba **8**. v2 cuenta 8, las nombra una por una y las registra.
- **C7 — "exponer las flags en la UI" no estaba especificado.** v2 agrega **F5**, la fase de alta de flags con los **7** lugares del cableado real (`Config`, `FlagSpec`, `_CATEGORY_KEYS`, `_CURATED_DEFAULTS_ON`, `requires`+`_REQUIRES_MAP_FROZEN`, **`PLAIN_HELP`** y **`_FROZEN_BOUNDS`**). El 6.º es el que más se olvida: `tests/test_harness_flags_help.py:32` exige cobertura **100 %** de `FLAG_REGISTRY` en `PLAIN_HELP`, y como ese archivo ya tiene 4 rojos ajenos, el rojo propio pasa desapercibido.
- **C8 — riesgo de ciclo de import.** `local_file_logging.py` hoy importa **solo** `runtime_paths` + stdlib, y `config.py:37` importa `services.log_throttle` con el comentario literal `# lazy: evita ciclo de import`. v2 prohíbe `from config import config` a nivel módulo en `local_file_logging.py`: lectura **lazy en call time** con `getattr(cfg, "X", default)`.
- **C9 — `test_purga_corre_al_arrancar` era frágil.** `install_file_log_handler` devuelve `None` y tiene `if _installed: return` (`:160-162`): si otro test ya instaló, la llamada es un no-op y el test pasa/falla según el ORDEN. v2 exige fixture de reset explícito y assert sobre el retorno de `purge_old_logs`.
- **C10 — el sitio de `agents_dir` estaba mal ubicado y ya estaba cableado.** No es `services/config.py` (archivo inexistente): es `backend/config.py:39`, y **ya usa `log_state_change`**. v2 lo saca de la lista de "cablear" y explica por qué se repite igual (§2.5, límite in-process).
- **C11 — KPI contradictorio:** §1 pedía "≥ 12 call-sites", F1-bis cableaba 6, el DoD decía "≥ 6". v2 deja **un solo número** y lo reformula como cobertura de firmas, no como conteo.
- **C12 — doble fuente de verdad de `LOG_MAX_BYTES` / `LOG_MAX_PARTS_PER_DAY`** (snippet con `os.getenv` suelto vs. prosa con `config.`), el mismo pecado que el plan denunciaba. v2: fuente única `config`, lectura lazy.
- **C13 — el Cambio 3 de F2 estaba incompleto.** Arreglar solo el glob no alcanza: `_date_from_log_name` (`:228`) hace `strptime("2026-06-01.3", "%Y-%m-%d")` → `ValueError` → `None`, y `purge_old_logs:189` hace `if day is None ... continue`. **Hay que tocar las dos cosas.** Y `recent_log_files:206` usa el mismo helper ⇒ si no se arregla, el ZIP de `GET /api/diag/logs/export` (`api/diag.py:477`) **deja de incluir las partes rotadas** (regresión silenciosa).
- **C14 — F4 tenía dos escritores del `.env` y un hot-apply mudo.** v2 declara `LOG_LEVEL` **NO-FlagSpec** y con un solo camino de escritura.
- **C15 — `apply_log_level` vs `basicConfig`.** v2 especifica que toca el **logger raíz** y no los handlers, y que valida antes (porque `getattr(logging, "TRACE", logging.INFO)` devuelve INFO en silencio).
- **C16 — prefijo de flags.** v2 usa `STACKY_LOG_*` / `STACKY_UI_LOG_NOISE_CARD_ENABLED`. `LOG_LEVEL` se conserva sin prefijo por retro-compat (ya está en `.env.example:16` y `README.md:30`).
- **C17 — mutar `record.msg`.** v2 fija el prefijo **ASCII puro** (`[x99 repeticiones en 60s]`) y explica por qué (consola Windows cp437 no tiene `×`), y prohíbe cualquier prefijo con `%`.
- **C18 — `_SIG_PATH_RE` solo matchea rutas con letra de unidad.** v2 suma UNC y POSIX y documenta el corte a 200 chars como limitación con test.
- **C19 — "0 lecturas de disco" no era criterio binario.** v2 lo baja a monkeypatch concreto de `Path.open`/`Path.glob`.
- **C20 — el comando de vitest no corría.** `src/**/__tests__/...` no se expande en PowerShell, y el archivo se llamaba `planN257` (N de más). Verificado además que `@testing-library/react` y `jsdom` **NO** están en `frontend/package.json` (solo `vitest ^4.1.9`) ⇒ el test es de **módulo puro `.ts`**, nunca de render. `rawGet` **sí** existe hoy (`src/api/client.ts:93`).
- **C21 — el ratchet son DOS listas.** `HARNESS_TEST_FILES=(` en `scripts/run_harness_tests.sh:20` (sin comillas, sin coma) **y** `$HarnessTestFiles = @(` en `scripts/run_harness_tests.ps1:13` (con comillas dobles y coma). Sintaxis distinta: una receta uniforme rompe el `.ps1`.
- **C22 — faltaba la huella de regresión.** v2 agrega la entrada en `docs/sistema/error_fingerprints.json` (F6).
- **C23 — interacción real con el plan 255 que v1 no veía.** El 255 sube `harness/resume.py:136-138` y `ado_edit_learning.py:322-323` a `logger.error` (`docs/255...:334` y `:228-231`). Como F1 exime `levelno >= ERROR`, **esas dos firmas dejan de ser throttleables**. Es correcto por diseño, pero cambia el KPI. Declarado en §2.5 y §8.
- **C24 — el loop del 253 no tenía nombre.** Congelado: **`_maintenance_loop`**, thread **`stacky-maintenance`**. Verificado que hoy **no existe** (`grep -rn "_maintenance_loop" backend/` = 0 hits) y que el 253 **v1** lo llamaba `_syslog_purge_loop`: sin nombre congelado se crean **dos** daemons.

---

## 1. Objetivo y KPI

Que un log de Stacky sea legible por un humano: throttle real sobre las firmas repetidas, rotación por tamaño además de por día, purga que corra de verdad, y el nivel de log configurable **desde la UI** — hoy es la única pieza de configuración del operador que solo se puede cambiar editando un `.env` y reiniciando, lo que viola el riel de "toda config por UI".

| KPI | Hoy (medido) | Meta | Depende de |
|---|---|---|---|
| Warnings de un **mismo proceso** dominados por una sola firma | **829 de 1173 = 71 %** (`stacky-2026-07-15.log`) | **≤ 10 %** por firma | F1 |
| Ocurrencias **por proceso** de la firma más repetida | **1016** en 2 días | **≤ 60** (1 cada 60 s + contador acumulado) | F1 · ver §2.5 |
| Repeticiones silenciadas que quedan **sin contabilizar** | n/a (no hay throttle) | **0** — invariante duro | **F1-ter** |
| Call-sites de `log_throttled` en producción | **0** (la función existe y nadie la usa) | **6**, uno por cada firma medida que sigue viva | F1-bis |
| Tamaño del log de un día | **4.451.357 bytes** (`07-16`) | **≤ 1 MB** típico; rotación dura a 20 MB | F2 |
| Purga de logs viejos que corre de verdad | **No** (solo al cruzar medianoche con el proceso vivo) | **Sí**, al arrancar y cada 6 h | F2 |
| Filas nuevas en `system_logs` por firma repetida | 1 por repetición (sin techo) | throttleadas igual que el archivo | **F1 (C4)** |
| `LOG_LEVEL` cambiable desde la UI | **No** (env-only + reinicio) | **Sí**, en caliente, sin reiniciar | F4 |

**Advertencia de honestidad sobre el KPI (C10/C23):** las dos firmas que hoy siguen vivas (`agents_dir configurado…` y `preflight: outputs_dir…`) se emiten **una vez por arranque de proceso**, no en un loop — `_log_completion_preflight` está definido en `app.py:306` y se llama **una sola vez** en `app.py:544`. 237 ocurrencias en un día son ~237 arranques (reloader de dev), no un bucle. **Un throttle en memoria no puede agrupar mensajes de procesos distintos.** Para esas dos firmas el KPI se mide **por proceso**, y la reducción real la dan F2 (rotación/purga) y F3 (visibilidad), no F1. Decirlo acá es preferible a prometer un número inalcanzable.

---

## 2. Evidencia real (anclaje anti-alucinación)

### E1 — El volumen y su concentración

Conteo por nivel y por día (`grep -c` sobre cada archivo de `Stacky Agents/backend/data/logs/`):

| Log | Bytes | ERROR | WARNING | Traceback |
|---|---|---|---|---|
| `stacky-2026-07-12.log` | 94.405 | 11 | 282 | 8 |
| `stacky-2026-07-13.log` | 14.697 | 0 | 69 | 0 |
| `stacky-2026-07-14.log` | 618.117 | 11 | 264 | 5 |
| **`stacky-2026-07-15.log`** | **2.645.456** | 32 | **1.173** | 40 |
| **`stacky-2026-07-16.log`** | **4.451.357** | 8 | 311 | 10 |
| `stacky-2026-07-17.log` | 2.142.576 | 8 | 43 | 2 |
| **`stacky-2026-07-18.log`** | **3.618.590** | 21 | 30 | 2 |
| `stacky-2026-07-19.log` | 91.500 | 2 | 6 | 0 |
| `stacky-2026-07-20.log` | 345.076 | 5 | 29 | 0 |
| `stacky-2026-07-21.log` | 736.631 | 12 | 37 | 0 |
| `stacky-2026-07-22.log` | 382.386 | 5 | 11 | 0 |
| `stacky-2026-07-23.log` | 496.301 | 5 | 24 | 0 |
| `stacky-2026-07-25.log` | 226.211 | 11 | 26 | 2 |
| `stacky-2026-07-26.log` | 391.363 | 30 | 16 | 55 |

**Las firmas que producen el ruido** (agregado `grep -oh "WARNING .\{0,130\}"` + normalización de números, sobre los 14 logs). La columna "Sitio" está verificada con `grep -n` **hoy**:

| Ocurrencias | Firma | Días | Sitio verificado |
|---|---|---|---|
| **854** | `[services.ado_edit_learning] sweep_recent_runs: error general: cannot import name 'Execution' from 'models' (C:\desa…` | 07-15 | `services/ado_edit_learning.py:323` |
| **621** | `[app] preflight: outputs_dir NO existe (C:\desarrollo\GIT\RS\Agentes\outputs) — el output_watcher no encontrará arti…` | 07-12 a 07-17 | `app.py:339` (dentro de `_log_completion_preflight`, def `:306`) |
| **162** | la misma de `ado_edit_learning`, con el otro prefijo de ruta (`N:\GIT\…`) | 07-16 | ídem `:323` |
| **118** | `[stacky.config] agents_dir configurado para el proyecto activo no existe o no es carpeta: C:/desarrollo/…` | 07-14 a **07-26** | `backend/config.py:39` — **ya throttleado** con `log_state_change` |
| **107** | `[api.tickets] autopublish_epic_from_run: grounding_warnings=['epic_grounding_low: la épica no cita módulos/procesos…` | 07-15 | `api/tickets.py:6798` |
| **50** | `[harness.resume] harness.resume.resolve falló (arranque en frío): Query.filter() being called on a Query which already has LIMIT…` | 07-17 a **07-26** | `harness/resume.py:137` |
| **25** | `output_watcher mode_a: corrigiendo epic dir mal nombrado …` | varios | `services/output_watcher.py:470` |

**854 + 162 = 1016** ocurrencias de **una sola firma**. En `stacky-2026-07-15.log`, 829 de sus 1.173 warnings son esa firma: **el 71 % del ruido de warnings de ese día es un solo mensaje repetido**.

Series temporales de las dos firmas que siguen **vivas**:

`agents_dir configurado ... no existe`: 07-14=41, 07-15=58, 07-16=2, 07-17=7, 07-18=2, 07-19=1, 07-20=1, 07-21=1, 07-23=1, 07-25=3, **07-26=1**.
`preflight: outputs_dir NO existe`: 07-12=237, 07-13=69, 07-14=217, 07-15=98, 07-17=3 → apagada, pero el mecanismo que la dejó repetirse 237 veces en un día sigue intacto.

### E2 — El throttle existe y nadie lo usa

`Stacky Agents/backend/services/log_throttle.py` — **contrato congelado (Plan 145 F0)**, `__all__ = ["log_state_change", "log_throttled", "warn_once", "reset"]`:

```python
log_state_change(key: str, state, logger: logging.Logger, level: int, msg: str, *args) -> bool   # :20
log_throttled(key: str, logger: logging.Logger, level: int, msg: str, *args,
              min_interval_s: float = 60.0) -> bool                                              # :30
warn_once(key: str, logger: logging.Logger, msg: str, *args) -> bool                             # :42
reset(key: str | None = None) -> None                                                            # :47
```

**Único consumidor real en todo el backend:** `Stacky Agents/backend/config.py:39`, y usa `log_state_change`, no `log_throttled`.

**`log_throttled` tiene CERO call-sites en producción.** La herramienta que hubiera evitado las 1016 repeticiones está escrita, testeada y sin usar. Este plan no la inventa: la **cablea**.

Hay además dedup ad-hoc, hecho a mano en un solo módulo, que prueba que el problema es conocido:
- `Stacky Agents/backend/services/ado_edit_ledger.py:28` → `_SQLITE_WARN_STATE`
- `Stacky Agents/backend/services/ado_edit_ledger.py:47` → `_warn_sqlite_unavailable`, con ventana de 300 s

Y el único `logging.Filter` del sistema es de **supresión**, no de dedup:
- `Stacky Agents/backend/services/local_file_logging.py:93` → `_AccessLogNoiseFilter`
- instalado en `local_file_logging.py:175`, paths por default en `local_file_logging.py:68`

### E3 — Rotación y retención: declaradas, no efectivas

Configuración del logging:
- `app.py:365` → `logging.basicConfig(level=getattr(logging, config.LOG_LEVEL, logging.INFO))`
- `app.py:366` → `install_file_log_handler()`
- `app.py:370` → `install_console_log_handler()` (**después** de `init_db()`)
- `app.py:371` → `install_shutdown_hook()` (plan 163 F3)
- `services/local_file_logging.py:154` → `install_file_log_handler(*, base_dir=None, retention_days=LOG_RETENTION_DAYS) -> None`
- `services/local_file_logging.py:111` → handler propio `_DailyStackyFileHandler`
- `services/local_file_logging.py:148` → nombre `stacky-{today:%Y-%m-%d}.log`

No hay `dictConfig`, ni `RotatingFileHandler`, ni `TimedRotatingFileHandler`.

**Dos defectos concretos:**

1. **Rotación solo por día, no por tamaño.** El log de un día puede crecer sin techo. Medido: `stacky-2026-07-16.log` = **4,45 MB** en un día.
2. **La purga casi nunca corre.** `local_file_logging.py:36` → `LOG_RETENTION_DAYS = 14`; el purgado se dispara en `local_file_logging.py:151` (`purge_old_logs`, def en `:180`) **solo al rotar de día o al abrir el stream**. En un proceso que arranca y se apaga el mismo día — el caso normal del operador — **nunca corre**. La retención de 14 días es declarativa.

### E4 — `LOG_LEVEL` es la única config del operador que la UI no toca

- `config.py:62` → `LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")`.
- Documentada en `backend/.env.example:16` y `backend/README.md:30`.
- **No aparece** en `api/global_config.py` (`_MANAGED_KEYS`, `:41-82`) ni en el frontend. Verificado.

Para bajar a `DEBUG` y diagnosticar algo, el operador tiene que editar `backend/.env` y **reiniciar el backend** — perdiendo, de paso, cualquier corrida en vuelo. Eso viola el riel duro de Stacky: *toda flag/config del operador debe ser activable y configurable desde la UI; solo los kill-switches internos pueden ser env-only*. `LOG_LEVEL` no es un kill-switch interno: es una herramienta de diagnóstico del operador.

Otras env-only relacionadas, todas sin UI: `STACKY_LOG_STRIP_ANSI` (`local_file_logging.py:53`), `STACKY_ACCESS_LOG_SUPPRESS` (`:82`), `STACKY_ACCESS_LOG_SUPPRESS_PATHS` (`:86`), `SYSLOG_RETENTION_DAYS` (`services/stacky_logger.py:62`).

### E5 — [v2] El root logger tiene TRES sumideros, no uno

Verificado abriendo los archivos:

| Handler | Dónde se crea | Qué hace | Nivel propio |
|---|---|---|---|
| `StreamHandler` de `basicConfig` | `app.py:365` | consola del operador | hereda del raíz |
| `_DailyStackyFileHandler` | `local_file_logging.py:176` | `data/logs/stacky-*.log` | `logging.DEBUG` (`:115`) |
| `_SystemLogHandler` | `console_log_handler.py:85` | **fila en la tabla `SystemLog`** vía queue + worker | `logging.DEBUG` (`:29`) |

Esto es lo que invalida el diseño de v1 (C4): `handler.addFilter(...)` sobre uno solo deja los otros dos inundados. Y `logging.getLogger().addFilter(...)` **tampoco sirve**: en CPython, `Logger.handle()` evalúa los filtros **del logger que emite**, y `callHandlers()` recorre los ancestros llamando sus **handlers**, no sus filtros. Un filtro en el logger raíz solo ve los records logueados directamente en el raíz — casi ninguno.

⇒ **La única forma correcta es una instancia de filtro compartida, agregada a todos los handlers del raíz.** Ver F1.

### E6 — [v2] Sustrato de flags: la UI NO se alimenta de `config.py`

`api/harness_flags.py` importa `FLAG_REGISTRY`, `read_current`, `list_categories`, `apply_updates`, `_REGISTRY_INDEX` de `services/harness_flags.py`. Campos de `FlagSpec` (`services/harness_flags.py:21-42`): `key, type, label, description, group, pair, env_only, default, requires, min_value, max_value, restart_required, reserved, reserved_reason`. Categorías vía `CategorySpec` / `FLAG_CATEGORIES` (`:53`), índice en `_CATEGORY_KEYS` (`:120`).

El hot-apply de `api/harness_flags.py:156-165` hace `setattr(config, key, val)` — **no ejecuta ningún efecto secundario**. Esto es exactamente por qué `LOG_LEVEL` **no** puede ser una `FlagSpec` (C14): la UI diría "aplicado" y `logging` no cambiaría.

---

## 3. Principios y guardarraíles (obligatorios)

- **Nunca perder la primera ocurrencia ni el conteo.** El throttle **no** descarta información: emite la primera de inmediato, silencia las repeticiones, y **el conteo se emite siempre** — por piggyback si la firma vuelve, y por **flush determinista (F1-ter)** si no vuelve. Un throttle que borre el rastro sería un falso verde nuevo.
- **`ERROR` y `CRITICAL` nunca se throttlean por default.** Solo `WARNING`, `INFO` y `DEBUG`.
- **Human-in-the-loop:** el cambio de `LOG_LEVEL` en caliente es una acción del operador, explícita, desde la UI. La purga respeta la retención que el operador configura. Ningún borrado corre sin que la retención sea la que él fijó.
- **Mono-operador sin auth.** Ningún endpoint nuevo asume identidad ni rol.
- **Paridad de 3 runtimes con fallback:** el logging es infraestructura transversal. Codex CLI, Claude Code CLI y Copilot Pro loguean por el mismo root logger y los mismos 3 handlers; un cambio los cubre a los 3, sin código por runtime. **Fallback:** si el filtro falla internamente, `filter()` devuelve `True` (fail-open) ⇒ el peor caso es el comportamiento de hoy, nunca menos logging que hoy.
- **Cero trabajo extra al operador:** F1/F1-bis/F1-ter/F2/F3 son invisibles. F4 le **quita** trabajo.
- **No degradar:** el throttle es un dict en memoria con cota y un memo por record. La rotación por tamaño solo actúa en el caso patológico. Con toda flag OFF el comportamiento es **byte-idéntico** al de hoy.
- **Backward-compatible:** `install_file_log_handler`, `purge_old_logs` y `recent_log_files` conservan su firma pública actual salvo parámetros **nuevos con default** (ver frontera con el 258 en §8).
- **Reusar lo existente:** `log_throttle.py` (contrato congelado), `_AccessLogNoiseFilter` como patrón de filtro, `lifecycle_log.install_shutdown_hook` como gancho de apagado, `_maintenance_loop` del 253, `_read_env`/`_write_env` de `global_config`, `error_fingerprints.json`.
- **Flags default ON**, ninguna cae en las 4 excepciones duras. Prefijo `STACKY_` (excepto `LOG_LEVEL`, preexistente).
- **Toda flag configurable desde la UI** — F5 es la fase que lo hace de verdad, no una línea suelta.

---

## 4. Fases

### F0 — Tests del throttle y de la rotación (rojo primero)

**Archivo a crear:** `Stacky Agents/backend/tests/test_plan257_log_antirruido.py`

**Registrar en LAS DOS listas del ratchet (C21) — la sintaxis es distinta:**

1. `Stacky Agents/backend/scripts/run_harness_tests.sh`, bloque `HARNESS_TEST_FILES=(` (`:20`) — **sin comillas y sin coma**:
   ```
     tests/test_plan257_log_antirruido.py
   ```
2. `Stacky Agents/backend/scripts/run_harness_tests.ps1`, bloque `$HarnessTestFiles = @(` (`:13`) — **con comillas dobles y coma**:
   ```
     "tests/test_plan257_log_antirruido.py",
   ```

Lo exige `tests/test_harness_ratchet_meta.py` (parsea el `.sh`, `_SCRIPT` en `:13`) y `tests/test_plan76_ratchet_byteidentical.py:83`.

**Fixture obligatoria (cierra C9):**

```python
import logging
import pytest
from services import local_file_logging as lfl


@pytest.fixture
def handler_limpio():
    """Reset REAL del singleton: el guard `if _installed: return` (lfl.py:162)
    convierte una segunda instalación en no-op y hace que los tests de purga
    pasen o fallen según el ORDEN de la suite."""
    root = logging.getLogger()
    previos = list(root.handlers)
    lfl._installed = False
    yield
    for h in list(root.handlers):
        if h not in previos:
            root.removeHandler(h)
            h.close()
    lfl._installed = False
```

**Casos exactos (13):**

| # | Nombre | Qué fija |
|---|---|---|
| 1 | `test_throttle_emite_la_primera_y_silencia_las_repeticiones` | 100 llamadas, misma firma, misma ventana → **1** registro emitido |
| 2 | `test_throttle_emite_resumen_con_conteo_al_reaparecer` | tras la ventana, el registro que pasa contiene `x99` (piggyback) |
| 3 | `test_flush_emite_el_conteo_aunque_la_firma_no_vuelva` | **F1-ter.** 99 silenciadas + `flush_pending("test")` → 1 registro con `x99`. **Sin este test, C5 sigue abierto.** |
| 4 | `test_throttle_no_afecta_firmas_distintas` | 3 firmas distintas → 3 registros |
| 5 | `test_throttle_nunca_silencia_error_ni_critical` | 100 `ERROR` misma firma → **100** registros. **Invariante crítico.** |
| 6 | `test_firma_distingue_niveles` | **C3.** Un `INFO` y un `WARNING` del mismo logger con el mismo template → **2** firmas distintas |
| 7 | `test_throttle_cota_de_memoria` | 2000 firmas distintas → el dict no supera `STACKY_LOG_THROTTLE_MAX_SIGNATURES`, y las excedentes **pasan** (fail-open) |
| 8 | `test_firma_normaliza_numeros_y_rutas` | `"ticket 123 en C:\a"` y `"ticket 456 en C:\b"` comparten firma; también `\\srv\share\x` y `/var/log/x` |
| 9 | `test_una_sola_instancia_en_todos_los_handlers_no_cuenta_de_mas` | **C4.** 3 handlers con la MISMA instancia; 10 repeticiones → `suppressed == 9`, no 27 |
| 10 | `test_rotacion_por_tamano_abre_archivo_nuevo` | con `STACKY_LOG_MAX_BYTES=1024`, escribir 2 KB genera `stacky-YYYY-MM-DD.1.log` |
| 11 | `test_purga_corre_al_arrancar` | usa `handler_limpio` + `base_dir=tmp_path`; un log de 30 días se borra sin esperar medianoche; **assert sobre el retorno de `purge_old_logs`**, no solo sobre el efecto |
| 12 | `test_purga_respeta_retention_days_de_config` | la fuente de verdad es `config`, no la constante del módulo |
| 13 | `test_purga_matchea_partes_numeradas` | **C13.** `stacky-2026-06-01.3.log` viejo se borra (glob **y** `_date_from_log_name`) |

**Comando exacto:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan257_log_antirruido.py -v
```

**Criterio binario:** los 13 existen y **los 13 fallan** antes de F1/F1-ter/F2, por `ImportError`/`AttributeError` de símbolos que todavía no existen — no por assert. Correr **por archivo** (la suite completa contamina; gotcha conocido del repo).

**Flag:** ninguna. **Trabajo del operador: ninguno.**

---

### F1 — Un `logging.Filter` que throttlea de verdad, en los TRES sumideros

**Objetivo:** matar el ruido en la **frontera del logging**, no en 1244 call-sites — y en **todos** los handlers, no en uno.

**Decisión de diseño (corregida en v2, C4):** se crea **UNA** instancia de `_ThrottleFilter` y se agrega a **todos los handlers del logger raíz**. Un filtro en el logger raíz NO sirve (ver E5). Compartir la instancia es lo que hace que el contador sea único; el memo por record es lo que evita contar 3 veces el mismo mensaje.

**Archivo a editar:** `Stacky Agents/backend/services/local_file_logging.py` — junto al `_AccessLogNoiseFilter` existente (`:93`).

**Símbolos nuevos exactos:**

```python
# services/local_file_logging.py  (agregar imports: time, logging ya está)

# Orden importa: primero rutas (que contienen dígitos), después números sueltos.
_SIG_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]|\\\\[^\s'\"\\]+[\\/]|/(?:home|var|tmp|usr|etc)/)[^\s'\"]*"
)
_SIG_NUM_RE = re.compile(r"\d+")
_SIG_MSG_MAX = 200

# ASCII puro a propósito (C17): el StreamHandler de consola en Windows puede
# estar en cp437, donde U+00D7 ("x" de multiplicar) no existe y lanzaria
# UnicodeEncodeError DENTRO del logging. Y sin ningun "%" : el prefijo se
# antepone a un template que todavia no fue formateado con record.args.
_SUMMARY_PREFIX = "[x{count} repeticiones en {window:.0f}s] "


def _log_signature(record: logging.LogRecord) -> str:
    """Firma estable de un mensaje.

    C3: la normalizacion se aplica SOLO al tramo del mensaje. `name` y
    `levelno` se concatenan DESPUES, para que `\\d+` no convierta el 30 de
    WARNING en "N" y colapse WARNING con INFO.
    """
    raw = record.msg if isinstance(record.msg, str) else str(record.msg)
    body = raw[:_SIG_MSG_MAX]
    body = _SIG_PATH_RE.sub("<PATH>", body)
    body = _SIG_NUM_RE.sub("N", body)
    return f"{record.name}|{record.levelno}|{body}"


class _ThrottleFilter(logging.Filter):
    """Plan 257 F1 — deja pasar la primera ocurrencia de cada firma y silencia
    las repeticiones dentro de `window_s`. El conteo acumulado se emite SIEMPRE:
    por piggyback cuando la firma reaparece, o por `flush_pending()` (F1-ter).

    NUNCA throttlea ERROR ni CRITICAL (levelno >= logging.ERROR).
    UNA sola instancia se comparte entre TODOS los handlers del root logger.
    """

    def __init__(self, *, window_s: float, max_sigs: int) -> None: ...

    def filter(self, record: logging.LogRecord) -> bool: ...
    def snapshot(self) -> list[dict]: ...                     # F3, read-only, NO resetea
    def flush_pending(self, reason: str) -> int: ...          # F1-ter, devuelve firmas emitidas
```

**Comportamiento exacto:**

| Situación | Resultado |
|---|---|
| Ya se decidió para este record (memo `record._stacky_throttle_decision`) | devuelve la decisión guardada, **sin volver a contar** |
| `levelno >= logging.ERROR` | **siempre pasa**, sin contar, sin memo |
| Primera vez que se ve la firma | **pasa** (`return True`), `first_seen = last_seen = now` |
| Repetición dentro de la ventana | **se silencia** (`return False`), `suppressed += 1`, `last_seen = now` |
| Primera repetición **después** de la ventana, con `suppressed > 0` | pasa; se prefija `_SUMMARY_PREFIX` al template; `suppressed = 0` |
| Primera repetición después de la ventana, con `suppressed == 0` | pasa, sin prefijo |
| Más de `max_sigs` firmas distintas | las nuevas **pasan** sin throttlear (fail-open: preferimos ruido a silencio) |
| Cualquier excepción interna | `return True` (fail-open) |

**El memo (C4, obligatorio):**

```python
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            cached = getattr(record, "_stacky_throttle_decision", None)
            if cached is not None:
                return cached
            decision = self._decide(record)     # aca vive TODO el conteo, una vez
            record._stacky_throttle_decision = decision
            return decision
        except BaseException:                   # noqa: BLE001 — jamas tumbar el logging
            return True
```

Sin el memo, la misma instancia en 3 handlers contaría 3 veces y el resumen diría `x297` en vez de `x99`. El caso 9 de F0 lo fija.

**Mutación del template (C17):** solo se antepone `_SUMMARY_PREFIX` a `record.msg` cuando `isinstance(record.msg, str)`. El prefijo no contiene `%`, así que el `record.args` posterior sigue formateando bien. Se acepta explícitamente que la mutación es visible en los 3 handlers — eso es **deseable**: el `xN` aparece también en consola.

**Instalación — un único punto (`install_throttle_filter`), llamado DESPUÉS de que los 3 handlers existan:**

```python
# services/local_file_logging.py
_throttle_filter: "_ThrottleFilter | None" = None


def get_throttle_filter() -> "_ThrottleFilter | None":
    """Instancia viva (o None si la flag esta OFF). La consume el endpoint de F3
    y el flush de F1-ter. No instala nada."""
    return _throttle_filter


def install_throttle_filter() -> bool:
    """Plan 257 F1 — agrega UNA instancia compartida a todos los handlers del
    root logger. Idempotente. Devuelve True si quedo instalada."""
    global _throttle_filter
    from config import config as cfg          # C8: lazy, NUNCA a nivel de modulo
    if not getattr(cfg, "STACKY_LOG_THROTTLE_ENABLED", True):
        return False
    with _install_lock:
        if _throttle_filter is not None:
            return True
        flt = _ThrottleFilter(
            window_s=float(getattr(cfg, "STACKY_LOG_THROTTLE_WINDOW_S", 60.0)),
            max_sigs=int(getattr(cfg, "STACKY_LOG_THROTTLE_MAX_SIGNATURES", 1000)),
        )
        for h in logging.getLogger().handlers:
            h.addFilter(flt)
        _throttle_filter = flt
        return True
```

**Ciclo de import (C8) — regla dura:** `local_file_logging.py` hoy importa **solo** `runtime_paths` y stdlib. `config.py:37` importa `services.log_throttle` con el comentario literal `# lazy: evita ciclo de import`. Por lo tanto: **prohibido** `from config import config` a nivel módulo en `local_file_logging.py`. Siempre dentro de la función, y siempre con `getattr(cfg, "X", default)` para que un `config` a medio inicializar no rompa el arranque.

**Call-site en `app.py`** — una línea, después de `install_console_log_handler()` (`:370`), que es donde ya existen los 3 handlers:

```python
    install_console_log_handler()
    from services.local_file_logging import install_throttle_filter
    install_throttle_filter()          # Plan 257 F1 — 1 instancia en los 3 handlers
```

**Casos borde:**
- `record.msg` que no es `str` (un objeto): `_log_signature` hace `str(record.msg)`; el prefijo de resumen **no** se aplica (se pierde solo el adorno, nunca el conteo — el `snapshot()` de F3 lo sigue viendo).
- Mensajes con f-string sin template: el número queda embebido → `_SIG_NUM_RE` los agrupa igual.
- `exc_info` presente: el traceback **no** entra en la firma. Como los tracebacks vienen casi siempre con `ERROR`, quedan exentos por nivel.
- Reentrada: `filter()` **no loguea nunca**. El único código que loguea es `flush_pending()`, y se invoca desde fuera del pipeline de logging (F1-ter).
- Multithread: `threading.Lock` de grano fino sobre el dict. 1016 mensajes/día no justifican optimizar, y un conteo mal contado sería una mentira en el log.
- Limitación conocida y documentada (C18): dos mensajes que difieren **después** del char 200 colapsan en la misma firma; `_SIG_PATH_RE` cubre unidad Windows, UNC y los prefijos POSIX comunes, no rutas relativas.

**Tests:** casos 1, 2, 4, 5, 6, 7, 8, 9 de F0 a verde.

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan257_log_antirruido.py -k "throttle or firma or handlers" -v
```
8 verdes.

**Flag:** `STACKY_LOG_THROTTLE_ENABLED`, **default ON**. Sin excepción dura: no bypasea revisión humana (preserva primera ocurrencia + conteo), no es destructiva, sin prerequisito, no reduce seguridad. Alta en la UI: **F5**.
**Impacto por runtime:** transversal, los 3 igual, con fail-open como fallback.
**Trabajo del operador: ninguno.**

---

### F1-bis — Cablear `log_throttled` en los sitios probados (con la firma REAL)

**Objetivo:** defensa en profundidad donde el bucle es del propio código, y darle su primer uso en producción a una función que llevaba cero call-sites.

**LA FIRMA (C2) — copiala de acá, no la inventes:**

```python
log_throttled(key: str, logger: logging.Logger, level: int, msg: str, *args,
              min_interval_s: float = 60.0) -> bool
```

`key` es el **primer posicional**. `level` es un **int de `logging`** (`logging.WARNING`), no el string `"warning"`. Los `*args` del formateo van **antes** de cualquier keyword; un posicional después de un keyword es `SyntaxError` y deja el módulo entero sin importar.

**Cambio tipo — correcto y copiable:**

```python
from services.log_throttle import log_throttled   # import a nivel de modulo: log_throttle
                                                  # no importa nada del repo (ver su docstring)
...
log_throttled(
    "app.preflight_outputs_dir_missing",   # key (1er posicional)
    logger,                                # logger (2do posicional)
    logging.WARNING,                       # level: INT, no "warning"
    "preflight: proyecto activo '%s' pero outputs_dir NO existe (%s) — el "
    "output_watcher no encontrara artifacts. Revisa workspace_root / STACKY_REPO_ROOT.",
    active, od,                            # *args del formateo, ANTES del keyword
    min_interval_s=300.0,
)
```

**Los 5 sitios a cablear** (verificados con `grep -n` hoy). Ventana 300 s: son condiciones de estado, no eventos.

| # | Sitio verificado | Firma | Key propuesta |
|---|---|---|---|
| 1 | `services/ado_edit_learning.py:323` | `sweep_recent_runs: error general` | `ado_edit_learning.sweep_error_general` |
| 2 | `app.py:339` | `preflight: outputs_dir NO existe` | `app.preflight_outputs_dir_missing` |
| 3 | `api/tickets.py:6798` | `autopublish_epic_from_run: grounding_warnings=` | `tickets.autopublish_grounding_warnings` |
| 4 | `harness/resume.py:137` | `resolve falló (arranque en frío)` | `harness.resume_resolve_failed` |
| 5 | `services/output_watcher.py:470` | `corrigiendo epic dir mal nombrado` | `output_watcher.epic_dir_rename` |

**El sexto NO se cablea (C10).** v1 listaba `services/config.py` / `stacky.config` para el `agents_dir configurado…`. Ese archivo **no existe**: es `backend/config.py:39`, y **ya está throttleado** con `log_state_change("config.agents_dir_invalid", str(raw), …)`. Se repite 118 veces porque el state (el path malo) cambia y porque el dict es de proceso: cada reinicio lo resetea. Cablear `log_throttled` encima **no baja el conteo** y rompería el dedup por estado que ya funciona. **Dejarlo como está.**

**Frontera con el plan 255 (C23) — orden obligatorio:** el 255 es dueño de `harness/resume.py` y de los niveles de log de `services/ado_edit_learning.py:319-325`. **El 255 va PRIMERO**: arregla la causa y fija el nivel. Recién después F1-bis cablea el throttle **sobre el nivel ya corregido**. Consecuencia que hay que aceptar de frente: si el 255 sube esos dos `except` a `logger.error`, **F1 los exime del throttle por nivel** (invariante «ERROR nunca se silencia»). Eso es correcto — un error estructural en loop debe gritar — pero significa que los dos sitios #1 y #4 quedan cubiertos por `log_throttled` (que sí respeta su intervalo, sea cual sea el nivel) y **no** por el filtro de F1. Los dos mecanismos son complementarios justamente por esto.

**Tests** (en `test_plan257_log_antirruido.py`):
- `test_los_5_sitios_usan_log_throttled` — verificación estructural con AST, no regex: `ast.parse` de los 5 archivos, buscar un `ast.Call` cuyo `func` resuelva a `log_throttled` con **≥ 4 argumentos posicionales**. Detecta la firma mal escrita, que un `grep` no ve.
- `test_log_throttled_tiene_call_sites_en_produccion` — asserta ≥ 5 call-sites fuera de `tests/`. Convierte "función huérfana" en un invariante testeado.
- `test_config_agents_dir_sigue_usando_log_state_change` — **guardia anti-regresión de C10**: `backend/config.py` debe seguir llamando `log_state_change`, no `log_throttled`.

**Criterio binario:** 3 verdes, y
```
grep -rn "log_throttled" --include=*.py services/ api/ harness/ app.py | grep -v "^tests/" | wc -l
```
devuelve **≥ 6** (5 call-sites + 1 import por archivo mínimo; el número que importa es que el test de AST cuente 5 llamadas válidas).

**Flag:** ninguna nueva (`log_throttled` respeta su propio intervalo).
**Trabajo del operador: ninguno.**

---

### F1-ter — [ADICIÓN ARQUITECTO] Flush determinista: ninguna repetición silenciada queda sin contabilizar

**El agujero que cierra (C5).** v1 emitía el resumen `xN` **solo cuando la firma volvía a aparecer**. Los datos reales muestran que ese es justamente el caso que no pasa: `preflight: outputs_dir` hizo 237 ocurrencias el 07-12 y después se apagó; `sweep_recent_runs` hizo 854 el 07-15 y se apagó. Con el diseño de v1, esos conteos **nunca se emiten** y el log queda diciendo "1 ocurrencia" de algo que pasó 854 veces. Eso no es agrupar: es **perder**, y es exactamente el falso verde que el propio plan dice querer evitar. El DoD «las repeticiones silenciadas se reportan con conteo» era inalcanzable.

**El invariante que se agrega, y que un test verifica:**

> `suprimidas_totales == sum(xN emitidos) + pendientes_visibles_en_/api/diag/logs/noise`
>
> Es decir: **toda repetición silenciada está contabilizada en algún lado, siempre.** Cero pérdida.

**Símbolo nuevo:**

```python
# services/local_file_logging.py
def flush_throttle_pending(reason: str) -> int:
    """Plan 257 F1-ter — emite UN registro de resumen por cada firma con
    suppressed > 0 y resetea su contador. Devuelve cuantas firmas se emitieron.

    NUNCA se llama desde dentro de filter() (seria reentrada). Se llama desde
    los 3 disparadores de abajo, todos fuera del pipeline de logging.
    """
```

Cada registro de resumen se emite con `logger.log(level, ...)` sobre el logger original de la firma, y se marca `record._stacky_throttle_decision = True` vía un `logging.LoggerAdapter`/`extra` para que el propio filtro **lo deje pasar sin volver a contarlo**.

**Los tres disparadores — todos reusan mecanismos que YA existen:**

1. **Apagado del proceso.** `services/lifecycle_log.py` ya registra `atexit` + `SIGTERM`/`SIGINT` en `install_shutdown_hook()` (`:49`, `atexit.register` en `:61`), y ya lo llama `app.py:371`. Se agrega el flush **antes** de `log_shutdown(...)`, para que el resumen entre al log del día. Es el disparador que salva el caso "el loop terminó y el proceso se apagó".
   - Nota: `lifecycle_log` es **NO-OP bajo `STACKY_TEST_MODE`** (`:44`/`:52`), así que pytest no queda con hooks colgados. El test del flush llama `flush_throttle_pending()` directo.
2. **Periódico.** Tarea registrada en **`_maintenance_loop`** (F2), cada `STACKY_LOG_THROTTLE_FLUSH_S` (default 300 s). Es el disparador que salva el caso "el proceso vive días y la firma no vuelve".
3. **Bajo demanda, sin destruir evidencia.** `GET /api/diag/logs/noise` (F3) llama a **`snapshot()`**, que es **read-only y NO resetea** los contadores. La UI nunca borra el rastro; solo lo mira.

**Casos borde:**
- Flush con cero pendientes: no emite nada, devuelve `0`. Silencio absoluto cuando todo está limpio.
- Flush concurrente con `filter()`: mismo `Lock`; el snapshot de firmas a emitir se toma **dentro** del lock y el `logger.log` se hace **fuera** (mismo patrón que `log_throttle.py:26`, que ya loguea fuera del lock a propósito).
- El flush corre después de que el handler de archivo cerró su stream: `atexit` corre antes de `logging.shutdown()` en el orden normal de CPython; si aun así el stream estuviera cerrado, `handleError` lo traga y **el conteo igual quedó en `system_logs`** por el otro handler. Doble red.

**Tests:** caso 3 de F0, más:
- `test_flush_no_emite_nada_sin_pendientes`
- `test_flush_resetea_el_contador_y_no_duplica` — dos flushes seguidos → el segundo emite 0.
- `test_snapshot_no_resetea` — `snapshot()` dos veces devuelve el mismo `suppressed`.
- `test_invariante_cero_perdida` — 500 repeticiones de 3 firmas, un flush, y `sum(xN emitidos) + snapshot_pendientes == 500 - 3` (las 3 primeras pasaron).

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan257_log_antirruido.py -k "flush or snapshot or invariante" -v
```
5 verdes. **`test_invariante_cero_perdida` es el que convierte "agrupar" en "no perder".**

**Flag:** `STACKY_LOG_THROTTLE_FLUSH_S` (int, segundos; `0` = solo flush al apagar). Default **300**.
**Trabajo del operador: ninguno.**

---

### F2 — Rotación por tamaño y purga que corre de verdad

**Objetivo:** que el disco no se llene y que la retención de 14 días sea real.

**Archivo a editar:** `services/local_file_logging.py` — `_DailyStackyFileHandler` (`:111`), `install_file_log_handler` (`:154`), `purge_old_logs` (`:180`), `_date_from_log_name` (`:228`).

**Cambio 1 — rotación por tamaño.** `_DailyStackyFileHandler` gana un techo. Al superar `STACKY_LOG_MAX_BYTES`, cierra el stream y abre `stacky-YYYY-MM-DD.<n>.log` con `n` incremental. Al pasar `STACKY_LOG_MAX_PARTS_PER_DAY`, **deja de rotar** y sigue escribiendo en la última parte, con **un** `logger.error` de aviso (vía `warn_once` de `log_throttle.py:42`, que ya garantiza exactamente-una-vez-por-proceso). Nunca deja de loguear: perder logs por exceso de logs sería el peor de los mundos.

**Fuente única (C12):** los tres valores viven en `class Config` y se leen **lazy en call time** con `getattr(cfg, "X", default)`. **Prohibido** dejar `os.getenv` sueltos en `local_file_logging.py` para estos tres — es el mismo pecado que el plan denuncia. La constante `LOG_RETENTION_DAYS = 14` (`:36`) **se conserva** como default del parámetro (backward-compat de la firma pública), pero el handler resuelve el valor efectivo desde `config`.

**Cambio 2 — purga al arrancar y periódica:**
- Llamar `purge_old_logs()` dentro de `install_file_log_handler` (`:154`), es decir **al arrancar**, no solo al rotar.
- Registrar la purga como tarea de **`_maintenance_loop`** (ver §8, frontera con el 253). **Un solo loop de mantenimiento** para la purga de `system_logs` (253), la purga de logs de archivo (257 F2) y el flush del throttle (257 F1-ter). No crear un daemon nuevo.

**Cambio 3 — el purgado debe ver las partes numeradas. SON DOS COSAS, no una (C13):**

```python
# (a) el glob
for path in base.glob("stacky-*.log"):        # ya matchea "stacky-2026-06-01.3.log": el
                                              # comodin cubre el ".3". El glob NO es el problema.

# (b) el parser — ACA esta el bug real
def _date_from_log_name(path: Path) -> date | None:
    stem = path.stem                          # "stacky-2026-06-01.3"
    ...
    return datetime.strptime(stem[len(prefix):], "%Y-%m-%d").date()   # ValueError -> None
```

Y `purge_old_logs:189` hace `if day is None or day >= cutoff: continue` ⇒ **la parte numerada se salta igual aunque el glob la encuentre**. El fix es en `_date_from_log_name`: quedarse con los primeros 10 chars de la fecha (`stem[len(prefix):len(prefix)+10]`) y validar que lo que sobre sea vacío o `.` + dígitos.

**Regresión a evitar:** `recent_log_files` (`:199`) usa **el mismo** `_date_from_log_name`. Si no se arregla, `GET /api/diag/logs/export` (`api/diag.py:477` → `build_logs_zip`) **excluye del ZIP las partes rotadas** y el operador se lleva un export incompleto sin enterarse. El fix en el helper cubre las dos rutas de una vez; hay test para las dos.

**Casos borde:**
- Archivo tomado por otro proceso (Windows): el `except OSError: continue` de `:194` ya cubre `PermissionError`. Verificado. No abortar la purga entera por uno.
- Reloj del sistema hacia atrás: la purga compara por la **fecha del nombre**, no por `mtime` (verificado en `:188`); una fecha futura simplemente no cae bajo el cutoff. *(v1 decía "compara por mtime" — era incorrecto.)*
- Rotación en el instante del cruce de medianoche: la rotación por día tiene prioridad sobre la de tamaño (el nombre del día manda), y el contador de partes se reinicia en 0.

**Tests:** casos 10, 11, 12, 13 de F0 a verde. Sumar:
- `test_rotacion_respeta_max_parts_y_no_deja_de_loguear` — con `STACKY_LOG_MAX_PARTS_PER_DAY=2`, la tercera rotación **sigue escribiendo** en la parte 2.
- `test_purga_ignora_archivo_tomado_y_sigue`
- `test_recent_log_files_incluye_partes_numeradas` — **guardia anti-regresión del export**.
- `test_date_from_log_name_parsea_partes` — unitario del helper: `stacky-2026-06-01.log` y `stacky-2026-06-01.3.log` → misma fecha; `stacky-basura.log` → `None`.

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan257_log_antirruido.py -k "rotacion or purga or recent or date_from" -v
```
8 verdes. Y `ls data/logs/` tras un arranque no muestra archivos de más de 14 días.

**Flags:** `STACKY_LOG_SIZE_ROTATION_ENABLED` (**default ON**), `STACKY_LOG_MAX_BYTES` (int, default `20971520`), `STACKY_LOG_MAX_PARTS_PER_DAY` (int, default `10`), `STACKY_LOG_RETENTION_DAYS` (int, default `14`). Ninguna cae en las 4 excepciones duras: rotar no borra nada, y borrar es la purga, que respeta la retención que el operador configura.
**Impacto por runtime:** transversal.
**Trabajo del operador: ninguno.**

---

### F3 — Panel de firmas ruidosas

**Objetivo:** que el operador vea qué está inundando su log, sin abrir un archivo de 4 MB.

**Archivos a editar:**
1. `Stacky Agents/backend/api/diag.py` — `GET /api/diag/logs/noise`. El blueprint es `Blueprint("diag", __name__, url_prefix="/diag")` (`api/diag.py:40`), registrado bajo `api_bp` en `api/__init__.py:111`; el patrón a copiar es `@bp.get("/logs/export")` (`:477`). ⇒ la ruta se declara como `@bp.get("/logs/noise")`.
2. Frontend: `Stacky Agents/frontend/src/pages/DiagnosticsPage.tsx` — tarjeta ***"Firmas de log más repetidas"***. (Nombre reservado para este plan; ver §8.)

**Contrato del endpoint (exacto).** El reporte sale de `get_throttle_filter().snapshot()` de F1, que ya tiene los contadores en memoria. **Cero costo extra**: no se re-parsea ningún archivo. `snapshot()` es **read-only**: no resetea (F1-ter).

```json
{
  "enabled": true,
  "window_s": 60,
  "flush_interval_s": 300,
  "signatures": [
    {"signature": "stacky.config|30|agents_dir configurado para el proyecto activo no existe...",
     "logger": "stacky.config", "level": "WARNING",
     "count": 118, "suppressed": 112,
     "first_seen": "2026-07-26T09:10:00Z", "last_seen": "2026-07-26T15:40:00Z"}
  ]
}
```

Con la flag OFF o sin filtro instalado: `{"enabled": false, "signatures": []}` y HTTP **200** (no 404, no 500 — un panel de diagnóstico no debe romperse porque una flag esté apagada).

Notar que en `signature` el `30` **queda intacto**: es el `levelno`, y la normalización de `\d+` solo se aplica al tramo del mensaje (C3). El JSON de ejemplo de v1 ya mostraba el `30` sin normalizar y contradecía su propio snippet.

**Tarjeta en la UI:** top 10 por `suppressed`, con el nombre del logger y el conteo. Si `signatures` está vacío, **no se renderiza** (sin ruido visual cuando todo está limpio).

**Valor concreto:** con esta tarjeta, las 1016 ocurrencias del `ImportError` de `ado_edit_learning` habrían sido visibles el primer día, en la primera fila de la tabla, en vez de sobrevivir dos días escondidas entre miles de líneas.

**Tests backend:** `Stacky Agents/backend/tests/test_plan257_log_noise_api.py` (**registrar en las DOS listas del ratchet**, misma receta que F0):
- `test_endpoint_devuelve_firmas_ordenadas_por_suppressed`
- `test_endpoint_vacio_cuando_no_hubo_throttle` — 200 con `signatures: []`.
- `test_endpoint_200_con_flag_off` — `enabled: false`, 200.
- `test_endpoint_no_reparsea_archivos` — **criterio implementable (C19)**: `monkeypatch.setattr(pathlib.Path, "open", boom)` y `monkeypatch.setattr(pathlib.Path, "glob", boom)` donde `boom` lanza `AssertionError`; el endpoint debe responder 200. Nada de "mockear el filesystem".
- `test_endpoint_no_resetea_contadores` — dos GET seguidos devuelven el mismo `suppressed`.

**Test frontend:** `Stacky Agents/frontend/src/components/__tests__/logNoiseModel.test.ts` — **módulo puro `.ts`**, no de render. Verificado: `frontend/package.json` tiene `vitest ^4.1.9` y **no** tiene `@testing-library/react` ni `jsdom` ⇒ un test de render no puede correr (C20). Se testea la función pura `buildLogNoiseRows(payload)`:
- `test_devuelve_vacio_sin_firmas`
- `test_ordena_por_suppressed_y_corta_en_10`

Para leer un no-2xx del endpoint usar `rawGet` (`frontend/src/api/client.ts:93`), **no** `api.get`, que lanza excepción en non-2xx.

**Criterio binario:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan257_log_noise_api.py -v

cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/components/__tests__/logNoiseModel.test.ts
```
5 + 2 verdes. Vitest **por archivo y con ruta concreta** (el glob `src/**/...` no se expande en PowerShell, y la corrida completa contamina cross-file).

**Flag:** `STACKY_UI_LOG_NOISE_CARD_ENABLED`, **default ON**. Sin excepción dura.
**Impacto por runtime:** UI común.
**Trabajo del operador: ninguno.**

---

### F4 — `LOG_LEVEL` desde la UI, en caliente

**Objetivo:** cerrar la violación del riel de configuración. Es la única config del operador que hoy exige editar un `.env` y reiniciar.

**Archivos a editar:**
1. `Stacky Agents/backend/api/global_config.py` — agregar `"LOG_LEVEL"` a `_MANAGED_KEYS` (`:41-82`) y el hook de aplicación en el `PUT`.
2. `Stacky Agents/backend/services/local_file_logging.py` — `apply_log_level`.
3. Frontend, panel de configuración global — selector.

**Decisión de arquitectura (C14): `LOG_LEVEL` NO es una `FlagSpec`, y se declara así explícitamente.** Razón verificada: el hot-apply de la UI de flags (`api/harness_flags.py:156-165`) solo hace `setattr(config, key, val)` — **no ejecuta efectos secundarios**. Si `LOG_LEVEL` fuera una `FlagSpec`, la UI reportaría "aplicado" y `logging` **no cambiaría**: un falso verde nuevo, que es justo lo que esta serie viene a matar. Por eso `LOG_LEVEL` va por **un único camino**, `api/global_config.py`, que es el que llama `apply_log_level`.

**Sobre los dos escritores del `.env`:** verificado que `api/global_config.py:38` y `api/harness_flags.py:29` apuntan al **mismo** `backend_root()/.env`, y ambos hacen merge preservando las demás claves (el comentario de `global_config.py:36` lo dice literal: *"el que escribe harness_flags.py"*). No hay clobber por diseño; el riesgo residual es una carrera read-modify-write si el operador guarda las dos pantallas en el mismo instante. Se acepta (mono-operador) y se documenta. Lo que **no** se acepta es que `LOG_LEVEL` tenga dos escritores: por eso no se registra como FlagSpec.

**Símbolo nuevo exacto:**

```python
# services/local_file_logging.py
_VALID_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def apply_log_level(level_name: str) -> dict:
    """Plan 257 F4 — cambia el nivel del logger RAIZ en caliente, sin reiniciar.

    Devuelve {'ok': bool, 'previous': str, 'current': str, 'error': str|None}.
    Valida contra _VALID_LEVELS ANTES de tocar nada: con un nivel invalido
    devuelve ok=False y NO modifica el logging.

    Toca UNICAMENTE logging.getLogger().setLevel(). NO toca el nivel de los
    handlers: los dos handlers de Stacky se construyen con level=DEBUG
    (local_file_logging.py:115, console_log_handler.py:29) justamente para que
    el umbral efectivo lo gobierne el logger raiz.
    """
```

**Por qué validar antes es obligatorio (C15):** `logging.basicConfig(level=getattr(logging, config.LOG_LEVEL, logging.INFO))` (`app.py:365`) usa `getattr` con default, así que un `"TRACE"` cae en INFO **en silencio**. `apply_log_level` no puede repetir ese patrón: el operador pide `400`, no un INFO mudo. Además `basicConfig` **solo actúa la primera vez** — no sirve para cambiar el nivel después; hay que llamar `setLevel` directo.

**El `PUT /api/global-config` con `LOG_LEVEL`:**
1. Valida contra `_VALID_LEVELS`; si no está, **`400`** y **no cambia nada** (ni `.env` ni logging).
2. Llama `apply_log_level(...)` → efecto **inmediato**.
3. Persiste en `backend/.env` con el `_write_env` que el módulo ya tiene.
4. Loguea el cambio a nivel `WARNING` **con el nivel viejo y el nuevo**, marcando el record con `extra={"_stacky_throttle_decision": True}` para que **quede exento del throttle** (es un evento único de auditoría). Se emite **antes** de aplicar el nivel nuevo, para que subir a `ERROR` no oculte su propio registro de auditoría.

**Selector en la UI:** dropdown con los 5 niveles, en la sección de configuración global. Con una advertencia visible al elegir `DEBUG`: *"DEBUG genera mucho volumen. Acordate de volver a INFO."*

**Casos borde (todos con test):**
- Nivel inválido (`"TRACE"`, `""`, `None`, minúsculas): `400`, nada cambia. (Aceptar `"debug"` normalizando a mayúsculas es opcional; si se acepta, hay test.)
- Bajar a `DEBUG` con el throttle activo: el throttle es lo que hace `DEBUG` usable. F1 y F2 son **prerequisitos** y por eso van antes en el orden.
- El `.env` no escribible: el cambio en caliente **se aplica** igual, y se responde `ok=True` con `"persisted": false` y un mensaje claro de que no sobrevive al reinicio. **No fallar el pedido entero por no poder persistir.**
- Subir a `ERROR` y perder los `WARNING` de diagnóstico: es la decisión del operador; el selector es explícito.

**Tests:** `Stacky Agents/backend/tests/test_plan257_log_level_ui.py` (**registrar en las DOS listas del ratchet**):
- `test_put_log_level_valido_cambia_en_caliente` — un `logger.debug` que antes no se emitía, ahora sí.
- `test_put_log_level_invalido_devuelve_400_y_no_cambia_nada`
- `test_put_log_level_persiste_en_env`
- `test_put_log_level_env_no_escribible_aplica_igual_con_persisted_false`
- `test_cambio_de_nivel_se_audita_y_no_se_throttlea`
- `test_get_global_config_incluye_log_level`
- `test_log_level_no_esta_en_flag_registry` — **guardia de C14**: asserta que `"LOG_LEVEL" not in {f.key for f in FLAG_REGISTRY}`, para que nadie lo registre después y reintroduzca el hot-apply mudo.

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan257_log_level_ui.py -v
```
7 verdes. Y manualmente: cambiar a `DEBUG` desde la UI hace aparecer líneas `DEBUG` en el log **sin reiniciar**.

**Flag:** ninguna nueva — `LOG_LEVEL` **es** la configuración. Ponerla detrás de una flag sería absurdo.
**Impacto por runtime:** los 3 loguean por el mismo logger raíz; el cambio los afecta a los 3 por igual, en caliente.
**Trabajo del operador:** **menos** que hoy. Deja de editar `.env` y reiniciar.

---

### F5 — [v2, cierra C6/C7] Alta REAL de las 8 flags en la UI

**Por qué es una fase y no una línea.** El atributo en `config.py` **no basta**: la UI de flags no lee `config.py`, lee `FLAG_REGISTRY` de `services/harness_flags.py` (E6). v1 despachaba esto con «Exponer las 5 flags nuevas en el panel de flags y en `api/global_config.py`» — número equivocado, mecanismo equivocado, y cero de los pasos reales.

**Las 8 flags (C6), con prefijo `STACKY_` (C16):**

| # | Key | Tipo | Default | Fase | `restart_required` |
|---|---|---|---|---|---|
| 1 | `STACKY_LOG_THROTTLE_ENABLED` | bool | **True** | F1 | **True** — se consume una sola vez en `install_throttle_filter()` desde `create_app` |
| 2 | `STACKY_LOG_THROTTLE_WINDOW_S` | float | 60.0 | F1 | **True** — se pasa al constructor del filtro |
| 3 | `STACKY_LOG_THROTTLE_MAX_SIGNATURES` | int | 1000 | F1 | **True** — ídem |
| 4 | `STACKY_LOG_THROTTLE_FLUSH_S` | int | 300 | F1-ter | False — la lee el `_maintenance_loop` en cada vuelta |
| 5 | `STACKY_LOG_SIZE_ROTATION_ENABLED` | bool | **True** | F2 | False — se lee lazy en cada `_ensure_stream` |
| 6 | `STACKY_LOG_MAX_BYTES` | int | 20971520 | F2 | False — ídem |
| 7 | `STACKY_LOG_MAX_PARTS_PER_DAY` | int | 10 | F2 | False — ídem |
| 8 | `STACKY_UI_LOG_NOISE_CARD_ENABLED` | bool | **True** | F3 | False |

`LOG_LEVEL` **no** entra en esta tabla: va por `api/global_config.py` (F4, C14).

**Los 7 lugares del cableado — receta literal, todos obligatorios.** (La receta corta que circula dice "5 lugares"; verificado hoy que son **7** cuando la flag declara `min_value`/`max_value`, y **6** en el caso mínimo. Faltarle uno pone un archivo en rojo.)

1. **`Stacky Agents/backend/config.py`**, dentro de `class Config`, con el idioma real de la casa (C1). **Nunca `_env_bool`:**
   ```python
   # ── Plan 257 — Observabilidad antirruido (throttle / rotacion / purga) ──
   # Default ON: el throttle preserva la primera ocurrencia y el conteo (nunca
   # borra), no es destructivo, no bypasea revision humana, no tiene prerequisito
   # externo y no reduce seguridad ⇒ ninguna de las 4 excepciones duras aplica.
   STACKY_LOG_THROTTLE_ENABLED: bool = os.getenv(
       "STACKY_LOG_THROTTLE_ENABLED", "true"
   ).strip().lower() == "true"
   STACKY_LOG_THROTTLE_WINDOW_S: float = float(os.getenv("STACKY_LOG_THROTTLE_WINDOW_S", "60"))
   STACKY_LOG_THROTTLE_MAX_SIGNATURES: int = int(os.getenv("STACKY_LOG_THROTTLE_MAX_SIGNATURES", "1000"))
   STACKY_LOG_THROTTLE_FLUSH_S: int = int(os.getenv("STACKY_LOG_THROTTLE_FLUSH_S", "300"))
   STACKY_LOG_SIZE_ROTATION_ENABLED: bool = os.getenv(
       "STACKY_LOG_SIZE_ROTATION_ENABLED", "true"
   ).strip().lower() == "true"
   STACKY_LOG_MAX_BYTES: int = int(os.getenv("STACKY_LOG_MAX_BYTES", str(20 * 1024 * 1024)))
   STACKY_LOG_MAX_PARTS_PER_DAY: int = int(os.getenv("STACKY_LOG_MAX_PARTS_PER_DAY", "10"))
   STACKY_LOG_RETENTION_DAYS: int = int(os.getenv("STACKY_LOG_RETENTION_DAYS", "14"))
   STACKY_UI_LOG_NOISE_CARD_ENABLED: bool = os.getenv(
       "STACKY_UI_LOG_NOISE_CARD_ENABLED", "true"
   ).strip().lower() == "true"
   ```
   *(Son 9 atributos porque `STACKY_LOG_RETENTION_DAYS` reemplaza la constante del módulo; en la UI se expone también, con lo cual el panel muestra 9 controles. La tabla de arriba lista 8 flags "nuevas de comportamiento" + esta de retención = 9 entradas de registry. Contar 9, no 5.)*

2. **`Stacky Agents/backend/services/harness_flags.py`** — una `FlagSpec` por key en `FLAG_REGISTRY`, con `group="global"`, `label`/`description` **en español**, `min_value`/`max_value` donde aplique (p. ej. `STACKY_LOG_MAX_BYTES` con `min_value=65536`), y `restart_required` según la tabla.

3. **`Stacky Agents/backend/services/harness_flags.py`, `_CATEGORY_KEYS` (`:120`)** — las 9 keys van a una categoría **EXISTENTE**. La correcta es **`observabilidad_notif`** (`:79`, *"KPIs en harness-health, historial, footer ADO, webhooks, notificaciones, telemetría en vivo, salud operativa, pipelines, trazabilidad"*), salvo `STACKY_UI_LOG_NOISE_CARD_ENABLED`, que va a **`interfaz_ui`** (`:109`). **No crear categorías nuevas.** Sin esto, el meta-test de categorización se pone rojo.

4. **`Stacky Agents/backend/tests/test_harness_flags.py`, `_CURATED_DEFAULTS_ON` (`:467`)** — las **3** keys con `default=True` (`STACKY_LOG_THROTTLE_ENABLED`, `STACKY_LOG_SIZE_ROTATION_ENABLED`, `STACKY_UI_LOG_NOISE_CARD_ENABLED`) van al set, con un comentario `# ── Plan 257 — …`. Sin esto, `test_default_known_only_for_curated` se pone **rojo**. Las de tipo int/float **no** llevan `default=True` y **no** van al set.

5. **`requires` + `_REQUIRES_MAP_FROZEN`** — en la `FlagSpec`: `STACKY_LOG_THROTTLE_WINDOW_S`, `..._MAX_SIGNATURES` y `..._FLUSH_S` declaran `requires="STACKY_LOG_THROTTLE_ENABLED"`; `STACKY_LOG_MAX_BYTES` y `..._MAX_PARTS_PER_DAY` declaran `requires="STACKY_LOG_SIZE_ROTATION_ENABLED"`. **Profundidad 1** (regla R4): ninguna de esas dos maestras declara `requires` a su vez, o la cadena queda prohibida. Y la arista tiene que existir además en **`_REQUIRES_MAP_FROZEN`**, que vive en `Stacky Agents/backend/tests/test_harness_flags_requires.py:120` (lo consume también `tests/test_fitness_flags.py:10`). Agregar **solo** las 5 aristas propias: ese mapa arrastra deuda ajena (~19 keys foráneas ya rojas) y **no** hay que intentar arreglarla acá.

6. **`Stacky Agents/backend/services/harness_flags_help.py`, `PLAIN_HELP` (`:25`)** — **el lugar que más se olvida.** `tests/test_harness_flags_help.py:32 test_plain_help_covers_all_registry_keys` exige cobertura **100 %** de `FLAG_REGISTRY`: una `FlagSpec` sin entrada acá pone el archivo en rojo, y como ese archivo **ya tiene 4 fallos ajenos preexistentes**, es fácil no notar que el rojo nuevo es tuyo. Una entrada `PlainHelp(what, on_effect, off_effect, example)` por cada una de las 9 keys, con estas reglas **literales** del test:
   - `on_effect` y `off_effect` **empiezan con `"Si "` — SIN TILDE** (`:59-60`).
   - `what` 10..200 chars; `on_effect`/`off_effect` ≤ 240; `example` ≤ 300; ningún campo vacío.
   - `JARGON_DENYLIST` (`harness_flags_help.py:17`, match con plural opcional, ignorando mayúsculas): **MCP, TF-IDF, LLM, stdin, stdout, endpoint, frontmatter, prompt, token, regex, backend, frontend, gate, hook, runtime**. Para este plan las trampas son **"backend"**, **"gate"** y **"runtime"** — hablar de *"la aplicación"*, *"el archivo de registro"* y *"cada arranque"*.
   - Prohibido citar keys en `SCREAMING_SNAKE` y prohibido `\bF\d` (nada de "F1", "F2" en el texto de ayuda).
   - Validar **tu key** en el mensaje de fallo, no el archivo entero: `pytest tests/test_harness_flags_help.py -v 2>&1 | grep STACKY_LOG`.

7. **`Stacky Agents/backend/tests/test_harness_flags_bounds.py`, `_FROZEN_BOUNDS` (`:149`)** — obligatorio **si** declarás `min_value` o `max_value`. `test_bounds_map_is_frozen` (`:190`) compara con **igualdad exacta** contra `{s.key:(min,max) for s in FLAG_REGISTRY if min o max no son None}`. En este plan aplica a `STACKY_LOG_MAX_BYTES`, `STACKY_LOG_MAX_PARTS_PER_DAY`, `STACKY_LOG_THROTTLE_WINDOW_S`, `STACKY_LOG_THROTTLE_MAX_SIGNATURES`, `STACKY_LOG_THROTTLE_FLUSH_S` y `STACKY_LOG_RETENTION_DAYS`. Agregar **solo** tus líneas: el mapa ya arrastra deuda ajena. **Alternativa válida y más barata:** no declarar `min_value`/`max_value` en ninguna y ahorrarse este lugar por completo — la validación de rango la puede hacer el consumidor con un `max(1, valor)`. Si se elige esa vía, decirlo explícito en el commit para que nadie los agregue después "por prolijidad".

**Tests:** `Stacky Agents/backend/tests/test_plan257_flags.py` (**registrar en las DOS listas del ratchet**):
- `test_las_9_keys_estan_en_el_registry`
- `test_las_9_keys_estan_categorizadas` — presentes en el flat de `_CATEGORY_KEYS`, en `observabilidad_notif`/`interfaz_ui`.
- `test_defaults_on_estan_curados` — las 3 bool están en `_CURATED_DEFAULTS_ON`.
- `test_las_9_keys_tienen_plain_help` — presentes en `PLAIN_HELP`, con `on_effect`/`off_effect` empezando con `"Si "` y sin ninguna palabra del `JARGON_DENYLIST`.
- `test_requires_apunta_a_su_master_y_es_profundidad_1`
- `test_config_tiene_los_9_atributos` — `getattr(config, key)` no lanza para las 9.
- `test_restart_required_declarado_donde_corresponde`

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan257_flags.py -v
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -v
```
6 verdes + `test_harness_flags.py` **sin regresiones**. **Ojo:** `tests/test_harness_flags_help.py` tiene 4 fallos ajenos preexistentes; validar **tu** entrada aparte y no confundirlos con daño propio.

**Nota sobre `harness_defaults.env`:** ese archivo lo genera `deployment/export_harness_defaults.py` y está **PROHIBIDO editarlo a mano**. Si el arnés exige regenerarlo, correr el generador; si el archivo está pineado/parcial en este árbol, **no** regenerarlo por cuenta propia — es deuda ajena.

**Trabajo del operador: ninguno** (todas nacen con el valor correcto; puede cambiarlas desde la UI si quiere).

---

### F6 — [v2, cierra C22] Huella de regresión

**Archivo a editar:** `Stacky Agents/docs/sistema/error_fingerprints.json` (`schema_version: 1`; campos verificados: `id`, `title`, `class`, `status`, `log_pattern`, `log_guarded`, `killed_by`).

Agregar **dos** entradas con `status: "resolved"`, para que el smoke de huellas alarme si el patrón **reaparece** en un log fresco:

| `id` | `class` | `log_pattern` (regex) | `killed_by` |
|---|---|---|---|
| `log_signature_flood` | `log-noise-flood` | patrón de una misma firma de WARNING repetida >60 veces en un archivo | `plan 257 (throttle de firmas + flush determinista)` |
| `log_retention_not_effective` | `log-retention` | presencia de `stacky-*.log` con fecha anterior a la retención configurada | `plan 257 F2 (purga al arrancar + _maintenance_loop)` |

**Criterio binario:** `python -c "import json,pathlib; json.loads(pathlib.Path('docs/sistema/error_fingerprints.json').read_text(encoding='utf-8'))"` sale limpio y el archivo contiene los 2 `id` nuevos.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| **El throttle esconde un problema real** — riesgo #1 | `ERROR`/`CRITICAL` **exentos** por default (caso 5 de F0). La primera ocurrencia **siempre** pasa. El conteo acumulado se emite **siempre** (piggyback o flush, F1-ter) y el invariante de cero-pérdida tiene test propio. F3 muestra en la UI qué se está silenciando, sin resetear. Nada desaparece: se agrupa y se cuenta. |
| **El conteo se pierde si la firma no vuelve** (era real en v1) | **F1-ter**: flush por temporizador (`_maintenance_loop`), flush al apagar (`lifecycle_log.install_shutdown_hook`, ya existe) y `snapshot()` read-only en el endpoint. `test_invariante_cero_perdida`. |
| **El filtro cubre un handler y deja los otros inundados** (era real en v1) | Una instancia compartida en **todos** los handlers del raíz + memo por record. Casos 9 de F0. `system_logs` deja de recibir las repeticiones, lo que además ayuda al plan 253. |
| **La firma colapsa WARNING con INFO** (era real en v1) | `name`/`levelno` se concatenan **después** de normalizar. Caso 6 de F0. |
| **`NameError` al importar `config` deja el backend muerto** (era real en v1) | Idioma real de la casa; `test_config_tiene_los_9_atributos` importa `config` de verdad. |
| **Ciclo de import `config` ↔ `local_file_logging`** | Import **lazy en call time** + `getattr(cfg, "X", default)`. Prohibido a nivel módulo. Regla escrita en F1 y en F2. |
| **El snippet de `log_throttled` no compila** (era real en v1) | Firma real transcrita, ejemplo copiable, y `test_los_5_sitios_usan_log_throttled` valida con **AST** (≥4 posicionales), no con regex. |
| La firma agrupa mensajes que en realidad son distintos | La firma incluye logger + nivel + template. Limitación documentada: corte a 200 chars. Caso 4 y 8 de F0. |
| El filtro se vuelve un cuello de botella | Un `dict.get` + 2 regex sobre ≤200 chars, memoizado por record, con lock de grano fino. A 1016 mensajes/día el costo es despreciable. |
| Reentrada: el filtro loguea y se llama a sí mismo | `filter()` **nunca** loguea; todo su cuerpo en `try/except BaseException: return True`. El único que loguea es `flush_pending()`, invocado **fuera** del pipeline de logging, y sus records salen marcados para pasar sin contarse. |
| El prefijo `xN` rompe la consola de Windows | Prefijo **ASCII puro** (sin `×`, sin `%`). Razón escrita en el código. |
| La rotación por tamaño deja de loguear al llegar al techo | Al superar `STACKY_LOG_MAX_PARTS_PER_DAY` **sigue escribiendo** en la última parte, con un aviso `warn_once`. Test dedicado. |
| Las partes rotadas nunca se purgan | Fix en `_date_from_log_name`, no solo en el glob (C13). Caso 13 de F0. |
| **El export de logs deja de incluir las partes rotadas** | `recent_log_files` usa el mismo helper ⇒ el fix cubre las dos rutas. `test_recent_log_files_incluye_partes_numeradas`. |
| La purga borra logs que el operador necesitaba | Retención de 14 días, **configurable desde la UI** (F5). Es la misma política declarada hoy; solo pasa a ser efectiva. |
| `DEBUG` desde la UI llena el disco | F1 + F1-ter + F2 son prerequisitos y van **antes**. La UI avisa. La rotación por tamaño es el techo duro. |
| Cambiar `LOG_LEVEL` en caliente deja el logging inconsistente | `apply_log_level` valida **antes** de tocar; con nivel inválido no modifica nada. Solo toca el logger raíz. |
| **`LOG_LEVEL` con dos escritores del `.env` / hot-apply mudo** | `LOG_LEVEL` **no** es FlagSpec; un solo camino (`global_config`). `test_log_level_no_esta_en_flag_registry` congela la decisión. |
| Doble fuente de verdad de los límites de log | Todo en `config`, lectura lazy. La constante `LOG_RETENTION_DAYS` queda solo como default de firma (backward-compat). |
| Colisión con el plan 258 en `install_file_log_handler` | Ver §8. El dueño del handler es este plan; el 258 agrega `force=` **sin** cambiar el comportamiento default. |
| El test de purga da falso verde por orden de suite | Fixture `handler_limpio` con reset explícito de `_installed` + `base_dir=tmp_path` + assert sobre el retorno. |
| El ratchet queda a medias | **Dos** listas, con sintaxis distinta, escritas literal en F0. |

---

## 6. Fuera de scope

- Enviar logs a un sistema externo (Loki, Seq, ELK). Stacky es mono-operador y local.
- Cambiar el formato de las líneas de log. Rompería cualquier grep que el operador ya tenga. *(El prefijo `[xN …]` se antepone al mensaje, no altera el layout `%(asctime)s %(levelname)s [%(name)s] %(message)s`.)*
- Reescribir los 1244 `logger.*` del backend. F1 actúa en la frontera; F1-bis cablea los 5 medidos.
- Persistir el estado del throttle entre procesos. Es la única forma de agrupar las firmas de arranque (§1, §2.5) y **no se hace acá**: agregaría un archivo de estado y un modo de fallo nuevo para un beneficio marginal. Se declara la limitación en vez de fingir que no existe.
- El `system_logs` de la DB y su purga → **plan 253**. Este plan **reusa** su `_maintenance_loop` y, de yapa, le baja el caudal de entrada (C4).
- Arreglar las **causas** de las firmas ruidosas: el `ImportError` de `ado_edit_learning` y el `resume` roto son del **plan 255**. Este plan hace que la próxima firma ruidosa sea **visible el primer día**.
- Los `except Exception: pass` → **plan 255**.
- Los ledgers `.jsonl` y su aislamiento en test-mode → **plan 258**.

---

## 7. Glosario

| Término | Significado |
|---|---|
| **Firma de log** | Identificador estable de un mensaje: `logger|levelno|template` con números y rutas normalizados **solo en el tramo del template**. Dos mensajes con la misma firma son "el mismo mensaje repetido". |
| **Throttle** | Emitir la primera ocurrencia y silenciar las repeticiones dentro de una ventana, **preservando el conteo**. No es descartar. |
| **Flush determinista** | Emisión forzada del conteo acumulado, sin esperar a que la firma reaparezca. Los 3 disparadores: temporizador, apagado del proceso, y nunca desde `filter()`. |
| **Piggyback** | Emitir el conteo pegado al primer mensaje que vuelve a pasar tras la ventana. Es el camino barato; el flush es la red de seguridad. |
| **Memo por record** | Marca en el `LogRecord` que guarda la decisión del filtro, para que la misma instancia compartida entre N handlers no cuente N veces. |
| **`logging.Filter`** | Gancho estándar de Python que decide si un registro se emite. En un **handler** ve todos los records que llegan a ese handler; en un **logger** ve solo los que ese logger emite (por eso el filtro va en los handlers). |
| **Rotación por día** | Un archivo por fecha (`stacky-2026-07-26.log`). Lo que Stacky ya hace. |
| **Rotación por tamaño** | Abrir un archivo nuevo al superar N bytes (`stacky-2026-07-26.1.log`). Lo que falta. |
| **Retención** | Cuántos días de logs se conservan antes de borrarlos. Hoy 14, declarada pero no efectiva. |
| **Fail-open** | Ante un fallo interno del filtro, **dejar pasar** el mensaje. Preferimos ruido a silencio. |
| **`LOG_LEVEL`** | Umbral del logger raíz. Hoy env-only + reinicio; con F4, desde la UI y en caliente. **No es una FlagSpec**, a propósito. |
| **Excepción dura** | Una de las 4 razones para que una flag nazca OFF: bypasea revisión humana, destructiva, prerequisito no garantizado, reduce seguridad. |

---

## 8. Orden de implementación y fronteras

### Orden

| # | Fase | Por qué en ese lugar |
|---|---|---|
| 0 | **Plan 255** (ajeno) | Es dueño de `harness/resume.py` y de los niveles de `ado_edit_learning.py:319-325`. Arregla la causa y **fija el nivel**; F1-bis cablea después, sobre el nivel corregido. |
| 1 | **F0** | 13 tests, rojos. Registrar en **las dos** listas del ratchet. |
| 2 | **F5 (parcial: los 9 atributos de `config.py`)** | F1 y F2 leen `config` en call time; sin los atributos, `getattr` cae al default y los tests de flag no prueban nada. El resto de F5 (registry/categorías/curated) puede ir al final. |
| 3 | **F1** | `_log_signature` + `_ThrottleFilter` + `install_throttle_filter()` en los 3 handlers. **Mayor retorno**: cierra la clase entera de ruido, incluidas las firmas futuras, en archivo **y** en `system_logs`. |
| 4 | **F1-ter** | El flush. Va **inmediatamente** después de F1: sin él, F1 pierde conteos y el DoD no se puede cumplir. |
| 5 | **F1-bis** | Cablear `log_throttled` en los 5 sitios medidos. |
| 6 | **F2** | Rotación por tamaño + purga al arrancar + registro en `_maintenance_loop` + fuente única. |
| 7 | **F3** | Endpoint `/api/diag/logs/noise` + tarjeta. Consume `snapshot()` de F1. |
| 8 | **F4** | `LOG_LEVEL` en `api/global_config.py` + `apply_log_level` + selector. **Va último**: depende de que F1/F1-ter/F2 hagan `DEBUG` usable. |
| 9 | **F5 (resto)** | `FlagSpec` + `_CATEGORY_KEYS` + `_CURATED_DEFAULTS_ON` + `requires`. |
| 10 | **F6** | Huellas de regresión. |
| 11 | Verificación final | 24 h de operación normal; ninguna firma supera 60 ocurrencias **dentro de un mismo proceso**; y el snapshot del endpoint concilia con los `xN` del log. |

### Fronteras vivas (contratos congelados)

**Con el plan 253 — `_maintenance_loop` (C24).** El loop de mantenimiento de 6 h en `app.py` se llama **`_maintenance_loop`**, corre en un thread daemon llamado **`stacky-maintenance`**, y está diseñado como punto de extensión con tareas registradas. Verificado que **hoy no existe** (`grep -rn "_maintenance_loop" backend/` = 0 hits) y que el 253 **v1** lo llamaba `_syslog_purge_loop` — ese nombre está **superado**; usar `_maintenance_loop`. El patrón de daemon a copiar ya está en el repo: `_digest_loop` / `stacky-digest-daemon` (`app.py:576-588`) y `_memory_review_sweep_loop` (`app.py:596-609`).
- Si el 253 **ya está implementado**: F2 y F1-ter **registran sus tareas** en el loop existente. No crear un thread nuevo.
- Si el 253 **no está implementado**: F2 **crea** `_maintenance_loop` con ese nombre exacto y el 253 lo reusa.
- **El loop es UNO SOLO.** Quien llegue primero lo crea; el segundo registra.

**Con el plan 255 — niveles de log y `harness/resume.py`.** El 255 va **primero** (ver Orden). Interacción declarada: si el 255 sube `harness/resume.py:136-138` y `ado_edit_learning.py:322-323` a `logger.error`, **F1 los exime del throttle por nivel**. Es correcto y buscado; queda cubierto por `log_throttled` de F1-bis, que respeta su intervalo independientemente del nivel. **No** revertir el nivel del 255 para hacerlos throttleables.

**Con el plan 258 — `install_file_log_handler`.** El 258 F5 propone gatear `install_file_log_handler` en test-mode y cambiar su firma a `(*, force: bool = False) -> bool`. **El dueño de `local_file_logging.py` es este plan (257); el dueño del ledger es el 258.** Dos notas para quien implemente:
1. El aislamiento en test-mode **ya existe** desde el plan 145: `install_file_log_handler:165` hace `base_dir = _test_logs_dir() if _test_mode() else logs_dir()`, y `_test_logs_dir()` (`:64`) devuelve `%TEMP%/stacky-test-logs`. El handler **no escribe** en `backend/data/logs` bajo pytest. El gate del 258 F5 es defensa adicional, no un bug abierto.
2. `config.STACKY_TEST_MODE` **no existe** (verificado: `grep -n "STACKY_TEST_MODE" backend/config.py` = 0 hits). El idioma real es `os.getenv("STACKY_TEST_MODE","").lower() in {"1","true","yes"}`, encapsulado en `_test_mode()` (`:61`). Cualquier plan que escriba `config.STACKY_TEST_MODE` está escribiendo un `AttributeError`.
3. Si el 258 cambia la firma a `-> bool`, este plan es compatible: F2 no depende del retorno.

**Tarjetas de UI reservadas en la serie (para no colisionar):** 255 = "Fallos silenciados" · 256 = "Artefactos en cuarentena" · **257 = "Firmas de log más repetidas"** · 258 = "Salud de ledgers".

**Helper HITL:** si alguna acción de este plan necesitara confirmación explícita, el helper es `backend/services/confirm_token.py` (dueño: 253 F5). **Este plan no lo necesita**: no borra nada que el operador no haya configurado como retención.

---

## 9. Definición de Hecho (DoD)

**Comportamiento**
- [ ] Ninguna firma de log supera **60** ocurrencias **dentro de un mismo proceso** en un día de operación normal.
- [ ] La primera ocurrencia de cada firma **siempre** se emite.
- [ ] **Ninguna repetición silenciada queda sin contabilizar**: `sum(xN emitidos) + pendientes del snapshot == suprimidas totales`, verificado por `test_invariante_cero_perdida`.
- [ ] El resumen se emite también cuando la firma **no vuelve** (flush por temporizador y al apagar).
- [ ] `ERROR` y `CRITICAL` **nunca** se throttlean (test dedicado).
- [ ] El throttle aplica a **los 3 handlers** del root logger, con **una** instancia y sin contar de más.
- [ ] `log_throttled` tiene **5 call-sites en producción** (antes: 0), verificados con **AST** (firma correcta), no con grep.
- [ ] `backend/config.py` **sigue** usando `log_state_change` para `agents_dir` (no se degradó a `log_throttled`).
- [ ] Existe rotación por tamaño y al llegar al techo de partes **no se deja de loguear**.
- [ ] `purge_old_logs` corre **al arrancar** y en `_maintenance_loop`, y borra las partes numeradas (glob **y** `_date_from_log_name`).
- [ ] `recent_log_files` / el ZIP de `/api/diag/logs/export` **siguen incluyendo** las partes rotadas (sin regresión).
- [ ] Los límites de log se leen de `config` **únicamente** (cero `os.getenv` sueltos nuevos en `local_file_logging.py`).
- [ ] `GET /api/diag/logs/noise` responde **200** sin releer archivos de disco, y **no resetea** contadores.
- [ ] La tarjeta de firmas ruidosas se ve en la UI y no se renderiza si está vacía.
- [ ] `LOG_LEVEL` se cambia **desde la UI, en caliente, sin reiniciar**, y persiste.
- [ ] Un `LOG_LEVEL` inválido devuelve `400` sin tocar el logging.
- [ ] El cambio de nivel se audita **antes** de aplicarse y **no** se throttlea.
- [ ] `LOG_LEVEL` **no** está en `FLAG_REGISTRY` (guardia de C14).

**Cableado**
- [ ] Las **9** entradas de configuración están en `config.py`, en `FLAG_REGISTRY`, en `_CATEGORY_KEYS` (categorías **existentes**: `observabilidad_notif` / `interfaz_ui`), en **`PLAIN_HELP`** (cobertura 100 % obligatoria, `"Si "` sin tilde, sin jerga del denylist), y las **3** con `default=True` están en `_CURATED_DEFAULTS_ON`.
- [ ] Si alguna declara `min_value`/`max_value`, está en **`_FROZEN_BOUNDS`** (`tests/test_harness_flags_bounds.py:149`); si se decidió no declarar bounds, está escrito en el commit.
- [ ] `restart_required=True` declarado en las 3 que se consumen una sola vez en `create_app`.
- [ ] `requires` de profundidad 1, apuntando a su master.
- [ ] Los **4** archivos de test backend nuevos están en **`HARNESS_TEST_FILES`** (`run_harness_tests.sh`) **y** en **`$HarnessTestFiles`** (`run_harness_tests.ps1`), cada uno con su sintaxis.
- [ ] `docs/sistema/error_fingerprints.json` tiene las 2 huellas nuevas y sigue siendo JSON válido.
- [ ] `_maintenance_loop` es **uno solo** (no hay un `_syslog_purge_loop` conviviendo).

**Verificación**
- [ ] `npx tsc --noEmit` limpio.
- [ ] Vitest del archivo nuevo verde, corrido **por archivo y con ruta concreta**.
- [ ] Ningún test preexistente pasa a rojo (validar **por archivo**; los 4 rojos de `test_harness_flags_help.py` son ajenos y preexistentes).
- [ ] Con **todas** las flags nuevas en OFF, el comportamiento del logging es **byte-idéntico** al de hoy.
