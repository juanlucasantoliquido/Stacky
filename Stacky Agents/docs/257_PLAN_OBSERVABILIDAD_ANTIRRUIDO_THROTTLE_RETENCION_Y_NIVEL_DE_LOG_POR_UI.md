# Plan 257 — Observabilidad antirruido: throttle, retención y nivel de log desde la UI

**Estado:** PROPUESTO v1
**Serie:** Robustez desde los logs (253-258). Plan **#5 por retorno**.
**Fuente:** auditoría de ~16 MB de logs reales de `Stacky Agents/backend/data/logs/`.

> Los 14 logs auditados suman ~16 MB, y **una sola firma repetida** se come el 71 % de los warnings del peor día. El ruido no es un problema estético: es la razón por la que los tres bugs del plan 255 sobrevivieron días sin que nadie los viera. Y el mecanismo de throttle **ya está escrito en el repo, con cero call-sites en producción**.

---

## 1. Objetivo y KPI

Que un log de Stacky sea legible por un humano: throttle real sobre las firmas repetidas, rotación por tamaño además de por día, purga que corra de verdad, y el nivel de log configurable **desde la UI** — hoy es la única pieza de configuración del operador que solo se puede cambiar editando un `.env` y reiniciando, lo que viola el riel de "toda config por UI".

| KPI | Hoy (medido) | Meta |
|---|---|---|
| Warnings del día dominados por una sola firma | **829 de 1173 = 71 %** (`stacky-2026-07-15.log`) | **≤ 10 %** por firma |
| Ocurrencias de la firma más repetida | **1016** en 2 días | **≤ 60** (1 cada 60 s con contador acumulado) |
| Call-sites de `log_throttled` en producción | **0** (la función existe y nadie la usa) | **≥ 12** |
| Tamaño del log de un día | **4.451.357 bytes** (`07-16`) | **≤ 1 MB** típico; rotación dura a 20 MB |
| Purga de logs viejos que corre de verdad | **No** (solo al cruzar medianoche con el proceso vivo) | **Sí**, al arrancar y cada 6 h |
| `LOG_LEVEL` cambiable desde la UI | **No** (env-only + reinicio) | **Sí**, en caliente, sin reiniciar |
| Firmas repetidas con contador acumulado ("×N desde …") | **0** | **100 %** de las throttled |

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

**Las 4 firmas que producen el ruido** (agregado `grep -oh "WARNING .\{0,130\}"` + normalización de números, sobre los 14 logs):

| Ocurrencias | Firma | Días |
|---|---|---|
| **854** | `[services.ado_edit_learning] sweep_recent_runs: error general: cannot import name 'Execution' from 'models' (C:\desa…` | 07-15 |
| **621** | `[app] preflight: outputs_dir NO existe (C:\desarrollo\GIT\RS\Agentes\outputs) — el output_watcher no encontrará arti…` | 07-12 a 07-17 |
| **162** | la misma de `ado_edit_learning`, con el otro prefijo de ruta (`N:\GIT\…`) | 07-16 |
| **118** | `[stacky.config] agents_dir configurado para el proyecto activo no existe o no es carpeta: C:/desarrollo/…` | 07-14 a **07-26** |
| **107** | `[api.tickets] autopublish_epic_from_run: grounding_warnings=['epic_grounding_low: la épica no cita módulos/procesos…` | 07-15 |
| **50** | `[harness.resume] harness.resume.resolve falló (arranque en frío): Query.filter() being called on a Query which already has LIMIT…` | 07-17 a **07-26** |

**854 + 162 = 1016** ocurrencias de **una sola firma**. En `stacky-2026-07-15.log`, 829 de sus 1.173 warnings son esa firma: **el 71 % del ruido de warnings de ese día es un solo mensaje repetido**.

Series temporales de las dos firmas que siguen **vivas**:

`agents_dir configurado ... no existe`: 07-14=41, 07-15=58, 07-16=2, 07-17=7, 07-18=2, 07-19=1, 07-20=1, 07-21=1, 07-23=1, 07-25=3, **07-26=1**.
`preflight: outputs_dir NO existe`: 07-12=237, 07-13=69, 07-14=217, 07-15=98, 07-17=3 → apagada, pero el mecanismo que la dejó repetirse 237 veces en un día sigue intacto.

### E2 — El throttle existe y nadie lo usa

`Stacky Agents/backend/services/log_throttle.py`:

- `log_throttle.py:20` → `log_state_change`
- `log_throttle.py:30` → `log_throttled(..., min_interval_s=60)`
- `log_throttle.py:42` → `warn_once`

**Único consumidor real en todo el backend:** `Stacky Agents/backend/config.py:37`, y usa `log_state_change`, no `log_throttled`.

**`log_throttled` tiene CERO call-sites en producción.** La herramienta que hubiera evitado las 1016 repeticiones está escrita, testeada y sin usar. Este plan no la inventa: la **cablea**.

Hay además dedup ad-hoc, hecho a mano en un solo módulo, que prueba que el problema es conocido:
- `Stacky Agents/backend/services/ado_edit_ledger.py:28` → `_SQLITE_WARN_STATE`
- `Stacky Agents/backend/services/ado_edit_ledger.py:47` → `_warn_sqlite_unavailable`, con ventana de 300 s

Y el único `logging.Filter` del sistema es de **supresión**, no de dedup:
- `Stacky Agents/backend/services/local_file_logging.py:93` → `_AccessLogNoiseFilter`
- instalado en `local_file_logging.py:175`, paths por default en `local_file_logging.py:68`

### E3 — Rotación y retención: declaradas, no efectivas

Configuración del logging:
- `Stacky Agents/backend/app.py:365` → `logging.basicConfig(level=getattr(logging, config.LOG_LEVEL, logging.INFO))`
- `Stacky Agents/backend/app.py:366` → `install_file_log_handler()`
- `Stacky Agents/backend/services/local_file_logging.py:154` → `install_file_log_handler`
- `Stacky Agents/backend/services/local_file_logging.py:111` → handler propio `_DailyStackyFileHandler`
- `Stacky Agents/backend/services/local_file_logging.py:148` → nombre `stacky-{today:%Y-%m-%d}.log`

No hay `dictConfig`, ni `RotatingFileHandler`, ni `TimedRotatingFileHandler`.

**Dos defectos concretos:**

1. **Rotación solo por día, no por tamaño.** El log de un día puede crecer sin techo. Medido: `stacky-2026-07-16.log` = **4,45 MB** en un día. Un día malo con un loop de warnings puede llenar el disco.
2. **La purga casi nunca corre.** `local_file_logging.py:36` → `LOG_RETENTION_DAYS = 14`; el purgado se dispara en `local_file_logging.py:151` (`purge_old_logs`, def en `:180`) **solo al rotar de día o al abrir el stream**. En un proceso que arranca y se apaga el mismo día — el caso normal del operador — **nunca corre**. La retención de 14 días es declarativa.

### E4 — `LOG_LEVEL` es la única config del operador que la UI no toca

- `Stacky Agents/backend/config.py:62` → `LOG_LEVEL`, default `"INFO"`.
- Documentada en `Stacky Agents/backend/.env.example:16` y `Stacky Agents/backend/README.md:30`.
- **No aparece** en `Stacky Agents/backend/api/global_config.py` ni en el frontend.

Para bajar a `DEBUG` y diagnosticar algo, el operador tiene que editar `backend/.env` y **reiniciar el backend** — perdiendo, de paso, cualquier corrida en vuelo. Eso viola el riel duro de Stacky: *toda flag/config del operador debe ser activable y configurable desde la UI; solo los kill-switches internos pueden ser env-only*. `LOG_LEVEL` no es un kill-switch interno: es una herramienta de diagnóstico del operador.

Otras env-only relacionadas, todas sin UI: `STACKY_LOG_STRIP_ANSI` (`local_file_logging.py:53`), `STACKY_ACCESS_LOG_SUPPRESS` (`:82`), `STACKY_ACCESS_LOG_SUPPRESS_PATHS` (`:86`), `SYSLOG_RETENTION_DAYS` (`services/stacky_logger.py:62`).

---

## 3. Principios y guardarraíles (obligatorios)

- **Nunca perder la primera ocurrencia ni el conteo.** El throttle **no** descarta información: emite la primera de inmediato, silencia las repeticiones, y al cerrar la ventana emite un resumen `×N desde HH:MM:SS`. Un throttle que borre el rastro sería un falso verde nuevo.
- **`ERROR` y `CRITICAL` nunca se throttlean por default.** Solo `WARNING`, `INFO` y `DEBUG`. Un error repetido 100 veces es una señal de que algo está en loop, y esa señal se preserva.
- **Human-in-the-loop:** el cambio de `LOG_LEVEL` en caliente es una acción del operador, explícita, desde la UI. La purga de logs viejos respeta la retención que el operador configura.
- **Mono-operador sin auth.**
- **Paridad de 3 runtimes:** el logging es infraestructura transversal. Codex CLI, Claude Code CLI y Copilot Pro loguean por el mismo handler; un cambio los cubre a los 3. Ningún cambio por runtime.
- **Cero trabajo extra al operador:** F1-F3 son invisibles. F4 le **quita** trabajo (deja de editar `.env` y reiniciar).
- **No degradar:** el throttle es un dict en memoria con cota. La rotación por tamaño solo actúa en el caso patológico.
- **Flags default ON**, ninguna cae en las 4 excepciones duras.
- **Toda flag configurable desde la UI** — que es, literalmente, el objetivo de F4.

---

## 4. Fases

### F0 — Tests del throttle y de la rotación (rojo primero)

**Archivo a crear:** `Stacky Agents/backend/tests/test_plan257_log_antirruido.py`
**Registrar en:** `HARNESS_TEST_FILES` de `Stacky Agents/backend/scripts/run_harness_tests.sh`.

**Casos exactos:**

1. `test_throttle_emite_la_primera_y_silencia_las_repeticiones` — 100 llamadas con la misma firma en la misma ventana → **1** registro emitido.
2. `test_throttle_emite_resumen_con_conteo_al_cerrar_ventana` — tras la ventana, un registro que contiene `×99`. **La información no se pierde.**
3. `test_throttle_no_afecta_firmas_distintas` — 3 firmas distintas → 3 registros.
4. `test_throttle_nunca_silencia_error_ni_critical` — 100 `ERROR` con la misma firma → **100** registros. **Invariante crítico.**
5. `test_throttle_cota_de_memoria` — 2000 firmas distintas no hacen crecer el dict más allá del máximo configurado.
6. `test_firma_normaliza_numeros_y_rutas` — `"ticket 123 en C:\a"` y `"ticket 456 en C:\b"` comparten firma (para que un mensaje con id variable se throttlee de verdad).
7. `test_rotacion_por_tamano_abre_archivo_nuevo` — con `LOG_MAX_BYTES=1024`, escribir 2 KB genera `stacky-YYYY-MM-DD.1.log`.
8. `test_purga_corre_al_arrancar` — con un log de 30 días, `install_file_log_handler()` lo borra sin esperar el cruce de medianoche.
9. `test_purga_respeta_retention_days_de_config` — la fuente de verdad es `config`, no la constante del módulo.

**Comando exacto:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan257_log_antirruido.py -v
```

**Criterio binario:** los 9 existen; 1-7 y 9 **fallan** antes de F1/F2 (el throttle no está cableado, la rotación por tamaño no existe, la purga no corre al arrancar).

**Flag:** ninguna. **Trabajo del operador: ninguno.**

---

### F1 — Un `logging.Filter` que throttlea de verdad

**Objetivo:** matar el ruido en la **frontera del logging**, no en 1244 call-sites.

**Decisión de diseño clave:** en vez de reemplazar 1016 llamadas a `logger.warning` por `log_throttled`, se instala un **`logging.Filter`** en el handler. Así **toda** firma repetida queda cubierta, incluidas las que no conocemos todavía. Es la diferencia entre parchear 6 síntomas y cerrar la clase entera de problema.

**Archivo a editar:** `Stacky Agents/backend/services/local_file_logging.py` — junto al `_AccessLogNoiseFilter` existente (`:93`), instalado en `:175`.

**Símbolos nuevos exactos:**

```python
# services/local_file_logging.py
_SIG_NUM_RE = re.compile(r"\d+")
_SIG_PATH_RE = re.compile(r"[A-Za-z]:[\\/][^\s'\"]+")

def _log_signature(record: logging.LogRecord) -> str:
    """Firma estable de un mensaje: logger + nivel + template con números y
    rutas normalizados. `record.msg` (el template, NO el mensaje formateado)
    ya agrupa la mayoría; se normaliza lo que quede.
    """
    base = f"{record.name}|{record.levelno}|{str(record.msg)[:200]}"
    base = _SIG_PATH_RE.sub("<PATH>", base)
    return _SIG_NUM_RE.sub("N", base)

class _ThrottleFilter(logging.Filter):
    """Plan 257 F1 — deja pasar la primera ocurrencia de cada firma y silencia
    las repeticiones dentro de `window_s`. Al cerrar la ventana emite UN
    registro de resumen con el conteo acumulado.

    NUNCA throttlea ERROR ni CRITICAL (levelno >= logging.ERROR).
    """
    def __init__(self, *, window_s: float, max_sigs: int, min_level: int): ...
    def filter(self, record: logging.LogRecord) -> bool: ...
```

**Comportamiento exacto:**

| Situación | Resultado |
|---|---|
| Primera vez que se ve la firma | **pasa** (`return True`) |
| Repetición dentro de la ventana | **se silencia** (`return False`), incrementa contador |
| Primera repetición **después** de la ventana | pasa, y su mensaje se **prefija** con `[×N en los últimos Ms] ` |
| `levelno >= logging.ERROR` | **siempre pasa**, sin contar |
| Más de `max_sigs` firmas distintas | las nuevas **pasan** sin throttlear (fail-open: preferimos ruido a silencio) |

**Símbolos nuevos exactos en `Stacky Agents/backend/config.py`** (dentro de `class Config`, `config.py:60`):

```python
LOG_THROTTLE_ENABLED = _env_bool("LOG_THROTTLE_ENABLED", True)
LOG_THROTTLE_WINDOW_S = float(os.getenv("LOG_THROTTLE_WINDOW_S", "60"))
LOG_THROTTLE_MAX_SIGNATURES = int(os.getenv("LOG_THROTTLE_MAX_SIGNATURES", "1000"))
```

**Instalación:** en `install_file_log_handler` (`local_file_logging.py:154`), junto al filtro existente:

```python
    if config.LOG_THROTTLE_ENABLED:
        handler.addFilter(_ThrottleFilter(
            window_s=config.LOG_THROTTLE_WINDOW_S,
            max_sigs=config.LOG_THROTTLE_MAX_SIGNATURES,
            min_level=logging.DEBUG,
        ))
```

**Casos borde:**
- `record.msg` con `%s` sin formatear: se usa el **template**, que es justamente lo que hace que `"ticket %s falló"` con 1016 ids distintos sea **una** firma. Este es el punto fino del diseño.
- Mensajes construidos con f-string (sin template): el número queda embebido → la normalización de `_SIG_NUM_RE` los agrupa igual.
- `exc_info` presente: el traceback **no** entra en la firma (si no, cada traceback con líneas distintas sería una firma nueva). Pero como los tracebacks vienen casi siempre con `ERROR`, quedan exentos por nivel.
- Reentrada: `filter()` **no debe loguear nunca**. Todo su cuerpo va en `try/except BaseException: return True` (fail-open).
- Multithread: el dict se protege con un `threading.Lock` de grano fino, o se usa un dict plano aceptando conteos aproximados. **Elegir el lock**: 1016 mensajes/día no justifican optimizar y un conteo mal contado sería una mentira en el log.

**Tests:** casos 1-6 de F0 a verde.

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan257_log_antirruido.py -k "throttle or firma" -v
```
6 verdes. Y en el log del día siguiente al deploy, ninguna firma supera 60 ocurrencias:
```
grep -oh "WARNING .\{0,130\}" data/logs/stacky-<hoy>.log | sed -E 's/[0-9]{2,}/N/g' | sort | uniq -c | sort -rn | head -1
```

**Flag:** `LOG_THROTTLE_ENABLED`, **default ON**. Sin excepción dura: no bypasea revisión humana (preserva primera ocurrencia + conteo), no es destructiva, sin prerequisito, no reduce seguridad.
**Configurable desde UI:** sí, con la ventana y el máximo de firmas.
**Impacto por runtime:** transversal, los 3 igual.
**Trabajo del operador: ninguno.**

---

### F1-bis — Cablear `log_throttled` en los 6 sitios probados

**Objetivo:** darle al filtro de F1 un refuerzo en los sitios donde el bucle es del propio código, y de paso darle uso a la función que llevaba cero call-sites.

**Los 6 sitios exactos** (los de la tabla de E1):

| Sitio | Firma | Ocurrencias |
|---|---|---|
| `services/ado_edit_learning.py:322-323` | `sweep_recent_runs: error general` | 1016 |
| `app.py` — el `preflight: outputs_dir NO existe` | 621 | |
| `services/config.py` / `stacky.config` — `agents_dir configurado ... no existe` | 118 | |
| `api/tickets.py` — `autopublish_epic_from_run: grounding_warnings=` | 107 | |
| `harness/resume.py:137` | `resolve falló (arranque en frío)` | 50 |
| `services/output_watcher.py` — `corrigiendo epic dir mal nombrado` | 25 | |

**Cambio tipo** (usando lo que ya existe en `services/log_throttle.py:30`):

```python
from services.log_throttle import log_throttled
...
log_throttled(logger, "warning", key="preflight_outputs_dir_missing",
              min_interval_s=300,
              msg="preflight: outputs_dir NO existe (%s) — el output_watcher "
                  "no encontrará artefactos", outputs_dir)
```

**Regla:** F1 (el filtro) es la red general; F1-bis es defensa en profundidad para los 6 casos conocidos, con ventanas más largas (300 s) porque son condiciones de estado, no eventos.

**Nota sobre `harness/resume.py:137`:** el plan 255 **arregla la causa** de esas 50 ocurrencias. Cablear el throttle igual es correcto: si el bug volviera, no debe volver a inundar el log. Los dos planes son complementarios, no redundantes.

**Tests:** en `test_plan257_log_antirruido.py`:
- `test_los_6_sitios_usan_log_throttled` — grep programático: los 6 archivos importan `log_throttled` y lo llaman ≥ 1 vez. Verificación estructural.
- `test_log_throttled_tiene_call_sites_en_produccion` — asserta ≥ 6 call-sites fuera de `tests/`. Convierte "función huérfana" en un invariante testeado.

**Criterio binario:** 2 verdes + `grep -rc "log_throttled" services/ api/ harness/ app.py` da ≥ 6 fuera de tests.

**Flag:** ninguna nueva (`log_throttled` ya respeta su propio intervalo).
**Trabajo del operador: ninguno.**

---

### F2 — Rotación por tamaño y purga que corre de verdad

**Objetivo:** que el disco no se llene y que la retención de 14 días sea real.

**Archivo a editar:** `Stacky Agents/backend/services/local_file_logging.py` — `_DailyStackyFileHandler` (`:111`), `install_file_log_handler` (`:154`), `purge_old_logs` (`:180`).

**Cambio 1 — rotación por tamaño:** `_DailyStackyFileHandler` gana un techo. Al superar `config.LOG_MAX_BYTES`, cierra el stream y abre `stacky-YYYY-MM-DD.<n>.log` con `n` incremental.

```python
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", str(20 * 1024 * 1024)))  # 20 MB
LOG_MAX_PARTS_PER_DAY = int(os.getenv("LOG_MAX_PARTS_PER_DAY", "10"))
```

Al pasar `LOG_MAX_PARTS_PER_DAY`, **deja de rotar** y sigue escribiendo en la última parte, con un `logger.error` **una sola vez** avisando que se alcanzó el techo diario. Nunca deja de loguear: perder logs por exceso de logs sería el peor de los mundos.

**Cambio 2 — purga al arrancar y periódica:**
- Llamar `purge_old_logs()` dentro de `install_file_log_handler` (`:154`), es decir **al arrancar**, no solo al rotar.
- Engancharla al loop de mantenimiento de 6 h que el **plan 253 F4** introduce para `system_logs`. **Un solo loop de mantenimiento para las dos purgas** — no crear un daemon nuevo.
- `LOG_RETENTION_DAYS` (`local_file_logging.py:36`) pasa a leerse de `config.LOG_RETENTION_DAYS` para que la UI pueda cambiarlo. **Fuente única.** Cuidado con el gotcha conocido: el default efectivo es el de `config.py`, no el de la constante del módulo.

**Cambio 3 — el purgado debe ver las partes numeradas:** el glob de `purge_old_logs` (`:180`) tiene que matchear `stacky-*.log` **y** `stacky-*.<n>.log`, o las partes rotadas nunca se borran. Requisito, no sugerencia.

**Casos borde:**
- Archivo tomado por otro proceso (Windows): `purge_old_logs` ignora el `PermissionError` de ese archivo y sigue con los demás. No abortar la purga entera por uno.
- Reloj del sistema hacia atrás: la purga compara por `mtime`; una fecha futura simplemente no se borra.
- Rotación en el instante del cruce de medianoche: la rotación por día tiene prioridad sobre la de tamaño (el nombre del día es el que manda).

**Tests:** casos 7, 8, 9 de F0 a verde. Sumar:
- `test_rotacion_respeta_max_parts_y_no_deja_de_loguear` — con `LOG_MAX_PARTS_PER_DAY=2`, la tercera rotación **sigue escribiendo** en la parte 2.
- `test_purga_matchea_partes_numeradas` — un `stacky-2026-06-01.3.log` viejo se borra.
- `test_purga_ignora_archivo_tomado_y_sigue`

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan257_log_antirruido.py -k "rotacion or purga" -v
```
6 verdes. Y `ls data/logs/` tras un arranque no muestra archivos de más de 14 días.

**Flag:** `LOG_SIZE_ROTATION_ENABLED`, **default ON**. Sin excepción dura (rotar no borra nada; borrar es la purga, que respeta la retención que el operador configura).
**Impacto por runtime:** transversal.
**Trabajo del operador: ninguno.**

---

### F3 — Panel de firmas ruidosas

**Objetivo:** que el operador vea qué está inundando su log, sin abrir un archivo de 4 MB.

**Archivos a editar:**
1. `Stacky Agents/backend/api/diag.py` — `GET /api/diag/logs/noise`.
2. Frontend, panel de diagnóstico existente — tarjeta *"Firmas de log más repetidas"*.

**Contrato del endpoint (exacto):** el reporte sale del `_ThrottleFilter` de F1, que ya tiene los contadores en memoria. **Cero costo extra**: no se re-parsea ningún archivo.

```json
{
  "window_s": 60,
  "signatures": [
    {"signature": "stacky.config|30|agents_dir configurado para el proyecto activo no existe...",
     "logger": "stacky.config", "level": "WARNING",
     "count": 118, "suppressed": 112,
     "first_seen": "2026-07-26T09:10:00Z", "last_seen": "2026-07-26T15:40:00Z"}
  ]
}
```

**Tarjeta en la UI:** top 10 por `suppressed`, con el nombre del logger y el conteo. Si nada superó el throttle, **no se renderiza** (sin ruido visual cuando todo está limpio).

**Valor concreto:** con esta tarjeta, las 1016 ocurrencias del `ImportError` de `ado_edit_learning` habrían sido visibles el primer día, en la primera fila de la tabla, en vez de sobrevivir dos días escondidas entre miles de líneas.

**Tests:** en `Stacky Agents/backend/tests/test_plan257_log_noise_api.py` (agregar al ratchet):
- `test_endpoint_devuelve_firmas_ordenadas_por_suppressed`
- `test_endpoint_vacio_cuando_no_hubo_throttle`
- `test_endpoint_no_reparsea_archivos` — mock del filesystem: 0 lecturas de disco.

Frontend: `Stacky Agents/frontend/src/**/__tests__/planN257LogNoise.test.ts`
- `test_no_renderiza_sin_firmas`
- `test_muestra_top_10`

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan257_log_noise_api.py -v
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend" && npx vitest run src/**/__tests__/planN257LogNoise.test.ts
```
3 + 2 verdes. (Vitest **por archivo**.)

**Flag:** `UI_LOG_NOISE_CARD_ENABLED`, **default ON**. Sin excepción dura.
**Impacto por runtime:** UI común.
**Trabajo del operador: ninguno.**

---

### F4 — `LOG_LEVEL` desde la UI, en caliente

**Objetivo:** cerrar la violación del riel de configuración. Es la única config del operador que hoy exige editar un `.env` y reiniciar.

**Archivos a editar:**
1. `Stacky Agents/backend/api/global_config.py` — agregar `LOG_LEVEL` al `GET`/`PUT`.
2. `Stacky Agents/backend/services/local_file_logging.py` — función nueva para aplicar el nivel en caliente.
3. Frontend, panel de configuración global — selector.

**Símbolo nuevo exacto:**

```python
# services/local_file_logging.py
_VALID_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

def apply_log_level(level_name: str) -> dict:
    """Plan 257 F4 — cambia el nivel del logger raíz EN CALIENTE, sin reiniciar.

    Devuelve {'ok', 'previous', 'current'}. Rechaza niveles inválidos con
    ok=False y NO toca nada (nunca deja el logging en un estado indefinido).
    """
```

**El `PUT /api/global-config` con `LOG_LEVEL`:**
1. Valida contra `_VALID_LEVELS`; si no está, `400` y no cambia nada.
2. Llama `apply_log_level(...)` → efecto **inmediato**.
3. Persiste en `backend/.env` (mecanismo que `api/global_config.py` ya tiene con `_read_env`/`_write_env`) para que sobreviva al reinicio.
4. Loguea el cambio a nivel `WARNING` **con el nivel viejo y el nuevo**, y ese registro **está exento del throttle** (es un evento único de auditoría, y además queda registrado antes de que el nivel nuevo pudiera ocultarlo).

**Selector en la UI:** dropdown con los 5 niveles, en la sección de configuración global. Con una advertencia visible en `DEBUG`: *"DEBUG genera mucho volumen. Acordate de volver a INFO."*

**Casos borde (todos con test):**
- Nivel inválido (`"TRACE"`, `""`, `None`): `400`, nada cambia.
- Bajar a `DEBUG` con el throttle activo: el throttle es lo que hace `DEBUG` usable. Documentar la sinergia; F1 es **prerequisito** de F4 y por eso va antes en el orden.
- El `.env` no escribible: el cambio en caliente **se aplica** igual, y se responde `ok=True` con `"persisted": false` y un mensaje claro de que no sobrevive al reinicio. **No fallar el pedido entero por no poder persistir.**
- Subir a `ERROR` y perder los `WARNING` de diagnóstico: es la decisión del operador; el selector es explícito.

**Tests:** `Stacky Agents/backend/tests/test_plan257_log_level_ui.py` (agregar al ratchet):
- `test_put_log_level_valido_cambia_en_caliente` — un `logger.debug` que antes no se emitía, ahora sí.
- `test_put_log_level_invalido_devuelve_400_y_no_cambia_nada`
- `test_put_log_level_persiste_en_env`
- `test_put_log_level_env_no_escribible_aplica_igual_con_persisted_false`
- `test_cambio_de_nivel_se_audita_y_no_se_throttlea`
- `test_get_global_config_incluye_log_level`

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan257_log_level_ui.py -v
```
6 verdes. Y manualmente: cambiar a `DEBUG` desde la UI hace aparecer líneas `DEBUG` en el log **sin reiniciar**.

**Flag:** ninguna nueva — `LOG_LEVEL` **es** la configuración. Ponerla detrás de una flag sería absurdo.
**Impacto por runtime:** los 3 loguean por el mismo logger raíz; el cambio los afecta a los 3 por igual, en caliente.
**Trabajo del operador:** **menos** que hoy. Deja de editar `.env` y reiniciar.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| **El throttle esconde un problema real** — riesgo #1 | `ERROR`/`CRITICAL` **exentos** por default (test dedicado). La primera ocurrencia **siempre** pasa. El conteo acumulado se emite al cerrar la ventana. Y F3 muestra en la UI exactamente qué se está silenciando. Nada desaparece: se agrupa. |
| La firma agrupa mensajes que en realidad son distintos | La firma incluye logger + nivel + template. Dos mensajes distintos del mismo logger tienen templates distintos. El test `test_throttle_no_afecta_firmas_distintas` lo fija. |
| El filtro se vuelve un cuello de botella | Un `dict.get` + regex sobre 200 chars, con lock de grano fino. A 1016 mensajes/día el costo es despreciable. Medir con `test_throttle_overhead` si hiciera falta. |
| Reentrada: el filtro loguea y se llama a sí mismo | `filter()` **nunca** loguea; todo su cuerpo en `try/except BaseException: return True` (fail-open). |
| La rotación por tamaño deja de loguear al llegar al techo | Al superar `LOG_MAX_PARTS_PER_DAY` **sigue escribiendo** en la última parte. Test dedicado. |
| La purga borra logs que el operador necesitaba | Retención de 14 días, **configurable desde la UI**. Es la misma política declarada hoy; solo pasa a ser efectiva. |
| `DEBUG` desde la UI llena el disco | F1 (throttle) + F2 (rotación + purga) son prerequisitos y van **antes**. La UI avisa. Y la rotación por tamaño es el techo duro. |
| Cambiar `LOG_LEVEL` en caliente deja el logging inconsistente | `apply_log_level` valida **antes** de tocar; con nivel inválido no modifica nada. |
| Doble fuente de verdad de `LOG_RETENTION_DAYS` | F2 unifica en `config.py`, con test dedicado (`test_purga_respeta_retention_days_de_config`). |

---

## 6. Fuera de scope

- Enviar logs a un sistema externo (Loki, Seq, ELK). Stacky es mono-operador y local.
- Cambiar el formato de las líneas de log. Rompería cualquier grep que el operador ya tenga.
- Reescribir los 1244 `logger.*` del backend. F1 actúa en la frontera; F1-bis cablea los 6 probados.
- El `system_logs` de la DB y su purga → **plan 253 F4** (este plan **reusa** su loop de mantenimiento).
- Arreglar las **causas** de las firmas ruidosas: el `ImportError` de `ado_edit_learning` y el `resume` roto son del **plan 255**. Este plan hace que la próxima firma ruidosa sea **visible el primer día**.
- Los `except Exception: pass` → **plan 255**.

---

## 7. Glosario

| Término | Significado |
|---|---|
| **Firma de log** | Identificador estable de un mensaje: logger + nivel + template con números y rutas normalizados. Dos mensajes con la misma firma son "el mismo mensaje repetido". |
| **Throttle** | Emitir la primera ocurrencia y silenciar las repeticiones dentro de una ventana, **preservando el conteo**. No es descartar. |
| **`logging.Filter`** | Gancho estándar de Python que decide si un registro se emite. Actúa en la frontera, no en el call-site. |
| **Rotación por día** | Un archivo por fecha (`stacky-2026-07-26.log`). Lo que Stacky ya hace. |
| **Rotación por tamaño** | Abrir un archivo nuevo al superar N bytes (`stacky-2026-07-26.1.log`). Lo que falta. |
| **Retención** | Cuántos días de logs se conservan antes de borrarlos. Hoy 14, declarada pero no efectiva. |
| **Fail-open** | Ante un fallo interno del filtro, **dejar pasar** el mensaje. Preferimos ruido a silencio. |
| **`LOG_LEVEL`** | Umbral del logger raíz. Hoy env-only + reinicio; con F4, desde la UI y en caliente. |
| **Excepción dura** | Una de las 4 razones para que una flag nazca OFF: bypasea revisión humana, destructiva, prerequisito no garantizado, reduce seguridad. |

---

## 8. Orden de implementación

1. **F0** — 9 tests, rojos. Registrar en `HARNESS_TEST_FILES`.
2. **F1** — `_log_signature` + `_ThrottleFilter` + instalación en el handler + 3 flags. **Mayor retorno de la fase**: cierra la clase entera de ruido, incluidas las firmas futuras.
3. **F1-bis** — cablear `log_throttled` en los 6 sitios medidos (y darle su primer uso en producción).
4. **F2** — rotación por tamaño + purga al arrancar + enganche al loop de mantenimiento del **plan 253 F4** + fuente única de `LOG_RETENTION_DAYS`.
5. **F3** — endpoint de firmas ruidosas + tarjeta en el panel de diagnóstico.
6. **F4** — `LOG_LEVEL` en `api/global_config.py` + `apply_log_level` en caliente + selector en la UI. **Va último**: depende de que F1/F2 hagan `DEBUG` usable.
7. Exponer las 5 flags nuevas en el panel de flags y en `api/global_config.py`.
8. Verificación final: 24 h de operación normal y `grep | uniq -c | sort -rn | head -1` sobre el log del día no supera 60 ocurrencias de ninguna firma.

**Dependencia declarada:** F2 reusa el loop de mantenimiento del plan 253 F4. Si el 253 no está implementado, F2 crea el loop y el 253 lo reusa. **El loop es uno solo**, quien llegue primero lo crea.

---

## 9. Definición de Hecho (DoD)

- [ ] Ninguna firma de log supera **60** ocurrencias en un día de operación normal.
- [ ] La primera ocurrencia de cada firma **siempre** se emite.
- [ ] Las repeticiones silenciadas se reportan con conteo (`×N`) al cerrar la ventana.
- [ ] `ERROR` y `CRITICAL` **nunca** se throttlean (test dedicado).
- [ ] `log_throttled` tiene **≥ 6 call-sites en producción** (antes: 0), verificado por test.
- [ ] Existe rotación por tamaño y al llegar al techo de partes **no se deja de loguear**.
- [ ] `purge_old_logs` corre **al arrancar** y cada 6 h, y matchea las partes numeradas.
- [ ] `LOG_RETENTION_DAYS` se lee de `config.py` únicamente.
- [ ] `GET /api/diag/logs/noise` responde sin releer archivos de disco.
- [ ] La tarjeta de firmas ruidosas se ve en la UI y no se renderiza si está vacía.
- [ ] `LOG_LEVEL` se cambia **desde la UI, en caliente, sin reiniciar**, y persiste.
- [ ] Un `LOG_LEVEL` inválido devuelve `400` sin tocar el logging.
- [ ] El cambio de nivel se audita y **no** se throttlea.
- [ ] Los 3 archivos de test backend nuevos están en `HARNESS_TEST_FILES`.
- [ ] Las 5 flags nuevas se cambian **desde la UI**.
- [ ] `npx tsc --noEmit` limpio.
- [ ] Ningún test preexistente pasa a rojo (validar **por archivo**).
