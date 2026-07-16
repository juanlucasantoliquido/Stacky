# 145 — Higiene y observabilidad de logs: 404 pipeline/status, strip ANSI, aislar pytest, helper de dedup/rate-limit

- **Estado:** IMPLEMENTADO F0..F5 (2026-07-16) · CRITICADO v1→v2 previo: APROBADO-CON-CAMBIOS
- **Fecha:** 2026-07-15
- **Autor:** StackyArchitectaUltraEficientCode (perfil: normal, heredado de Opus 4.8)
- **Serie:** 144–149 (derivada de `docs/reportes/2026-07-15_AUDITORIA_LOGS_deploy_vs_dev.md`)
- **Cubre de la auditoría:** ruido 404 `GET /api/v1/pipeline/status` (Sección 5, "único gran problema compartido"), ANSI en archivo (Sección 6 punto 11 / Resumen "6.590/día"), **V7** (log contaminado por pytest, §4.V7 `[V]`), y **provee el helper de dedup/rate-limit** (Sección 6 punto 13) que **147** y **148** pueden **migrar opcionalmente** para sus warnings residuales (ambos son **auto-contenidos** y NO bloquean en 145 — ver §CHANGELOG C1).
- **NO cubre (cross-ref, causas raíz en otros planes):** outputs_dir/repo_root → **147**; PAT ADO y Jira → **148**; import `Execution`, SQLite ledger, re-deploy fallback → **146**; trust/stall/estados terminales → **144**.

### CHANGELOG v1 → v2 (crítica adversarial + arquitecto)

- **C1 [IMPORTANTE — coherencia de serie]:** v1 afirmaba que "147 y 148 **consumen/dependen** de F0" y que "**145 va antes** de 147/148 en el orden global". **Falso contra los docs hermanos:** `147` (§ cross-ref línea 287 y R6 línea 531) declara ser **auto-contenido** (throttle + downgrade a INFO propios), que la migración al helper de 145 es "**nota futura, no dependencia dura**", y que **147 se implementa ANTES que 145**; `148` (R7 línea 629) dice "**el breaker ES el dedup… no depende de 145**". v2 **invierte la dirección declarada**: F0 queda **disponible para migración OPCIONAL**; 145 no reclama precedencia ni dependencia entrante. El **contrato F0 sí es suficiente** para esa migración (el `level` es parámetro → 147 puede loguear INFO/WARNING; el `state` admite tupla → 147 keyea por `(od_exists, active_present)`).
- **C2 [MEDIA — DX/observabilidad, tercer sink ignorado]:** v1 afirmaba "solo afecta **el archivo**; **consola intacta**", como si el único otro sink fuera la consola con color. **Incompleto:** existe un **tercer sink**, `_SystemLogHandler` (`services/console_log_handler.py:25`, persiste `self.format(record)` en `SystemLog.context_json`, `:61/:68` `[V]`), que alimenta el **visor System Log de la UI** — la superficie diagnóstica real del mono-operador. Como F1 (ANSI) y F3 (filtro access-log) son **handler-scoped al archivo**, la DB/UI **seguía** recibiendo ANSI crudo y el flood de `pipeline/status`. v2 **extiende el strip ANSI al `_SystemLogHandler`** (**[ADICIÓN ARQUITECTO]**, F1 paso 4) y **documenta explícitamente** la decisión sobre el flood de access-log en DB. **Nota:** el dedup F0/F4 es **source-level** (decide si se llama a `logger.warning`), así que **sí** cubre los 3 sinks; la asimetría es solo de F1/F3.
- **C3 [MEDIA — TDD/precisión para modelos menores]:** los tests de F0/F4 no fijaban el `level` capturado ni `caplog.set_level(...)`. Un record a INFO con el root en WARNING (default) se **descarta antes de llegar al handler de caplog** → 0 registros → **falso rojo**. v2 pinnea nivel y logger de captura en cada test.
- **C4 [MEDIA — higiene de tests en Windows]:** los tests de F1/F2 hacían solo `local_file_logging._installed=False` en cleanup, dejando el `_DailyStackyFileHandler` **adjunto al root** y el **stream abierto** → en Windows el teardown de `tmp_path` falla al `unlink` un `.log` con FD abierto (PermissionError). v2 exige capturar el handler y `root.removeHandler(h); h.close()` en cleanup.
- **[ADICIÓN ARQUITECTO]:** (a) strip ANSI también en el sink SystemLog/UI (C2); (b) `services/log_throttle.py` congela su superficie pública con `__all__` + docstring "CONTRATO CONGELADO — migración opcional de 147/148", para que los consumidores tengan un contrato estable e inequívoco.
- Anexo de anchors ampliado (`console_log_handler.py:25/61/68`, verificación de que `STACKY_TEST_MODE` no existe hoy en el código, no hay `conftest.py` en `backend/tests/`, ningún test lee `data/logs/` sin `base_dir`).

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** Devolverle a los logs de Stacky su valor diagnóstico. Hoy los archivos `stacky-YYYY-MM-DD.log` están ahogados por tres clases de ruido de altísimo volumen que esconden los fallos reales: (a) un cliente externo/legacy que pollea `GET /api/v1/pipeline/status` — ruta que **no existe** en el repo — generando **10.687 404 en DEPLOY y 12.094 en DEV**; (b) códigos de color **ANSI** (`\x1b[33m…\x1b[0m`) persistidos al archivo (**6.590 en un solo día de DEPLOY**); y (c) las corridas de **pytest** escribiendo al **mismo** archivo diario que el server local (**91 de 102 tracebacks — 89% — son de tests**). Este plan silencia las tres fuentes de ruido de forma invisible y backward-compatible, y entrega un **helper transversal de logging con dedup/rate-limit** (`log_state_change` / `log_throttled` / `warn_once`) que colapsa los warnings de preflight repetidos por ciclo (outputs_dir 4.761×, PAT 975×, Jira 448×, agents_dir 149×) a **una línea por cambio de estado**. Los planes 147 y 148 arreglan las **causas raíz** de esos warnings y son **auto-contenidos** (147: throttle+downgrade a INFO propios; 148: circuit-breaker persistido como dedup); **pueden migrar OPCIONALMENTE** a este helper más adelante, pero **no dependen** de 145 ni bloquean en él (ver C1 del CHANGELOG). 145 provee el helper —como primitiva reutilizable de calidad— y lo aplica como referencia al único warning que no es propiedad de otro plan (**agents_dir**, D7).

**KPI / impacto esperado (medible sobre un día de log real):**
- 404 de `pipeline/status` en el archivo diario: **de ~11k–12k/día → 0** (ruta shim 200 + filtro de access-log). Verificable con `grep -c "v1/pipeline/status" stacky-<hoy>.log`.
- Secuencias ANSI en el archivo diario: **de 6.590/día → 0**. Verificable con `grep -c $'\x1b\\[' stacky-<hoy>.log`. **Además** (ADICIÓN C2), 0 ANSI nuevos en la tabla `SystemLog` (→ visor System Log de la UI): verificable con un `SELECT count(*) FROM system_logs WHERE context_json LIKE '%'||char(27)||'%'` que deja de crecer.
- Tracebacks de pytest en `backend/data/logs/`: **de 91/102 → 0** (los tests escriben a `%TEMP%/stacky-test-logs/`). Verificable con `grep -c "pytest-of-" backend/data/logs/stacky-<hoy>.log`.
- Warning `agents_dir` (D7) en el archivo: **de 149/día → ≤2/día** (1 por cambio de estado). Verificable por conteo.
- Helper reutilizable disponible para 147/148 (0 duplicación de la lógica de dedup).

---

## 2. Por qué ahora / gap que cierra

La auditoría (§5) concluye: *"el único gran problema compartido y de altísimo volumen es el 404 de `pipeline/status` y la higiene de logs (ANSI + warnings repetidos sin dedup)"*. Es el ítem #2 del TOP priorizado (§7) por **ROI enorme / esfuerzo bajo**: 22.000+ líneas de ruido/día ocultan fallos reales. Además, el gap de **observabilidad de tests** (V7 `[V]`) hace que el log de DEV sea poco confiable para diagnóstico. Ninguna de estas tres higienes está implementada hoy:

- **404:** `grep` de `v1/pipeline/status` en `backend/**`, `frontend/src`, `vscode_extension` → **0 coincidencias en código** (solo aparece en los propios `.log` y en backups `.db`). `[V]` La ruta no existe; el poller es externo/legacy o un bundle minificado fuera del repo.
- **ANSI:** el `_DailyStackyFileHandler` (`backend/services/local_file_logging.py:23`) usa un `logging.Formatter` plano (líneas 77–82) que persiste el `record` **tal cual**, incluidos los colores que werkzeug inyecta en la línea de request. `[V]`
- **pytest:** no existe `conftest.py` en `backend/` ni en `backend/tests/` (solo el de PyInstaller). `[V]` `install_file_log_handler()` (`local_file_logging.py:66`) siempre resuelve a `data/logs/`, así que pytest escribe ahí igual que el server.
- **dedup:** no hay ningún helper de logging con estado; cada `logger.warning(...)` de preflight dispara en cada ciclo.

**Orden en la serie (reconciliado en v2, C1).** El helper **no** es una dependencia dura de 147/148: sus docs los declaran auto-contenidos (147 R6 línea 531: *"la migración al helper de dedup de 145 es una nota futura, no una dependencia dura"*; 148 R7 línea 629: *"el breaker es el mecanismo de dedup… no depende de 145"*) y 147 asume incluso implementarse **antes**. Por lo tanto **el orden entre 145 y 147/148 es libre**: 145 no reclama precedencia. Lo único que 145 garantiza es que, cuando 147/148 **quieran** migrar, el contrato F0 (§F0) ya está **congelado** y es suficiente (level parametrizable, state tupleable).

---

## 3. Principios y guardarrailes (codificados por fase)

1. **Paridad de 3 runtimes (Codex CLI / Claude Code CLI / GitHub Copilot Pro):** **todos** los cambios de este plan viven en la capa **Flask + logging + test-infra**, por **debajo** de la selección de runtime. Aplican **idénticos** a los 3 runtimes: ninguno de estos fixes toca `claude_code_cli_runner.py`, `codex_cli_runner.py` ni el bridge de Copilot. No hay concepto runtime-específico aquí (a diferencia de trust/stall del 144). Cada fase lo declara explícitamente en "Impacto por runtime".
2. **Cero trabajo al operador:** todo es invisible/automático, default ON, backward-compatible. No hay ninguna de las 4 excepciones duras: no bypasea revisión humana, no es destructivo/irreversible, no requiere prerequisito nuevo (ni credenciales, ni servicio, ni catálogo), y **no reduce seguridad** (solo suprime el access-log de UNA ruta no-op conocida; los 404 reales y todo el resto de access-log siguen visibles). Cada fase cierra con "Trabajo del operador: ninguno".
3. **Human-in-the-loop:** no se agrega autonomía. El shim de `pipeline/status` es un endpoint pasivo read-only; el dedup solo cambia la **frecuencia** de un log, nunca oculta un cambio de estado.
4. **Mono-operador sin auth:** el shim no introduce auth/roles; devuelve un payload estático mínimo sin datos sensibles.
5. **No degradar (perf/seguridad/estabilidad/DX) + reusar lo existente:** hay **tres sinks** de logging en el root (verificado, C2): (i) el `StreamHandler` de `basicConfig` → **consola/terminal real** (mantiene color → DX de terminal intacta); (ii) el `_DailyStackyFileHandler` → **archivo** `.log`; (iii) el `_SystemLogHandler` (`services/console_log_handler.py:25`) → tabla **`SystemLog` de la DB**, que alimenta el **visor System Log de la UI**. El **filtro de access-log** (F3) corre solo en el sink de archivo (consola y DB intactas por diseño — ver decisión documentada en F3). El **strip ANSI** (F1) corre en el sink de **archivo Y en el sink SystemLog/UI** (ambos son superficies diagnósticas donde el ESC crudo es basura; el terminal real conserva color). El **dedup** (F0/F4) actúa a **nivel de fuente** (`logger.warning`), antes de cualquier handler, por lo que reduce el volumen en los **tres** sinks por igual. El helper de dedup reusa `logging` stdlib (thread-safe, sin dependencias nuevas).

### 3.1 Decisión de flags (patrón del repo)

Ningún cambio de este plan introduce una **harness flag** de `FLAG_REGISTRY`. Todos los interruptores son **kill-switches internos env-only con default ON**, exactamente como los precedentes ya presentes en el repo: `STACKY_DEMO_SEED_ENABLED` (`app.py:233`) y `STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS` (`app.py:171`), ambos leídos con `os.getenv(..., "true")` sin FlagSpec. **Justificación (obligatoria):**
- No son features opt-in: son **higiene grado-bugfix** (ANSI/pytest/404 son ruido objetivamente indeseado). La regla del repo dice que un fix de bug verificado **no** necesita flag; le agregamos un kill-switch env-only solo para reversibilidad de emergencia.
- **No exponen ningún valor que el operador deba configurar** (no hay umbrales, backoff ni endpoints que tunear en la UI). La regla dura "todo valor configurable por el operador va por UI" **no aplica** porque no hay tal valor. El intervalo/estado del helper de dedup son constantes de código, no perillas de operador.
- Por lo tanto **no** entran en `FLAG_REGISTRY` y **no** requieren el patrón triple (`FlagSpec default=True` + `_CURATED_DEFAULTS_ON` en `backend/tests/test_harness_flags.py:467` + `config.py "true"`). Meterlos ahí rompería el modelo (son plumbing, no configuración de arnés).
- **No se regenera** `deployment/export_harness_defaults.py` / `harness_defaults.env` (no hay flags de arnés nuevas).

Env-vars introducidas (todas default ON, env-only, documentadas en F5):
| Env var | Default | Efecto | Fase |
|---|---|---|---|
| `STACKY_LOG_STRIP_ANSI` | `true` | Strip ANSI en el FileHandler de archivo | F1 |
| `STACKY_TEST_MODE` | (lo setea `conftest.py`) | Redirige el FileHandler default a `%TEMP%/stacky-test-logs/` | F2 |
| `STACKY_PIPELINE_STATUS_SHIM` | `true` | Habilita la ruta shim `GET /api/v1/pipeline/status` (200) | F3 |
| `STACKY_ACCESS_LOG_SUPPRESS` | `true` | Filtra del archivo el access-log de rutas ruidosas conocidas | F3 |
| `STACKY_ACCESS_LOG_SUPPRESS_PATHS` | `""` | (opcional) paths extra a suprimir, CSV; el default ya incluye `pipeline/status` | F3 |

---

## 4. Fases

> **Entorno de tests (verificado):** venv real = `backend/.venv`. No hay `pytest.ini`/`pyproject.toml`/`setup.cfg` → correr **por archivo** desde la raíz del repo `N:/GIT/RS/STACKY/Stacky/Stacky Agents`. Los tests hacen su propio `sys.path.insert(0, backend)` (ver `backend/tests/test_plan79_flag.py:12`), por eso corren desde la raíz. Comando canónico por archivo:
> ```
> backend/.venv/Scripts/python.exe -m pytest backend/tests/<archivo>.py -q
> ```
> **TDD:** en cada fase se escribe primero el test (rojo), luego el código (verde). Todos los tests de este plan van nombrados `test_plan145_*.py` para trazabilidad.

---

### F0 — Helper de logging con dedup/rate-limit (fundación; consumido por 147/148)

**Objetivo (1 frase).** Crear un módulo stdlib-only `services/log_throttle.py` que loguee **una vez por cambio de estado** (o a lo sumo una vez por intervalo), reutilizable por cualquier warning repetitivo.

**Valor.** Es la primitiva que colapsa 4.761/975/448/149 warnings/día a ~1 por cambio de estado, sin duplicar lógica en cada call-site. En 145 se aplica a **agents_dir** (F4); 147/148 **pueden** migrar a ella opcionalmente (no dependen — C1).

**Archivo a crear:** `backend/services/log_throttle.py`

**Contrato congelado (C1/ADICIÓN).** La superficie pública queda **congelada** para consumidores opcionales (147/148): módulo con `__all__ = ["log_state_change", "log_throttled", "warn_once", "reset"]` y docstring de cabecera: `"""CONTRATO CONGELADO (Plan 145 F0). Helper stdlib-only de logging con dedup por cambio de estado / rate-limit por intervalo. Consumido en 145 (agents_dir) y disponible para MIGRACIÓN OPCIONAL de 147 (outputs_dir) y 148 (breaker). No importar nada del repo (evita ciclos)."""`. Cambiar firmas rompería a los consumidores → cualquier cambio futuro es aditivo.

**API exacta (nombres congelados):**
- `log_state_change(key: str, state, logger: logging.Logger, level: int, msg: str, *args) -> bool` — loguea `msg % args` a `level` **solo si** `state` difiere del último estado logueado bajo `key`. Devuelve `True` si logueó, `False` si suprimió. Si el estado vuelve a cambiar (p.ej. dir aparece→desaparece), re-loguea.
- `log_throttled(key: str, logger, level: int, msg: str, *args, min_interval_s: float = 60.0) -> bool` — loguea a lo sumo una vez cada `min_interval_s` segundos por `key` (usa `time.monotonic`).
- `warn_once(key: str, logger, msg: str, *args) -> bool` — conveniencia: WARNING exactamente una vez por proceso por `key` (`= log_state_change(key, True, logger, WARNING, ...)`).
- `reset(key: str | None = None) -> None` — hook de test: limpia estado (todo o una key).

**Pseudocódigo ilustrativo:**
```python
# backend/services/log_throttle.py
"""CONTRATO CONGELADO (Plan 145 F0). Helper stdlib-only de logging con dedup por
cambio de estado / rate-limit por intervalo. Consumido en 145 (agents_dir) y
disponible para MIGRACIÓN OPCIONAL de 147 (outputs_dir) y 148 (breaker).
No importar nada del repo (evita ciclos)."""
from __future__ import annotations
import logging, threading, time
from typing import Any

__all__ = ["log_state_change", "log_throttled", "warn_once", "reset"]

_lock = threading.Lock()
_last_state: dict[str, Any] = {}
_last_time: dict[str, float] = {}
_NEVER = object()  # sentinel "nunca logueado"

def log_state_change(key, state, logger, level, msg, *args) -> bool:
    with _lock:
        if _last_state.get(key, _NEVER) == state:
            return False
        _last_state[key] = state
    logger.log(level, msg, *args)   # fuera del lock: no bloquear en I/O
    return True

def log_throttled(key, logger, level, msg, *args, min_interval_s: float = 60.0) -> bool:
    now = time.monotonic()
    with _lock:
        last = _last_time.get(key)
        if last is not None and (now - last) < min_interval_s:
            return False
        _last_time[key] = now
    logger.log(level, msg, *args)
    return True

def warn_once(key, logger, msg, *args) -> bool:
    return log_state_change(key, True, logger, logging.WARNING, msg, *args)

def reset(key=None) -> None:
    with _lock:
        if key is None:
            _last_state.clear(); _last_time.clear()
        else:
            _last_state.pop(key, None); _last_time.pop(key, None)
```
**Casos borde:** `state` debe ser hasheable/comparable por `==` (bool, str, int, tuple). El `logger.log` se hace **fuera** del lock para no serializar el I/O. `reset()` es solo para tests (no se llama en producción).

**Tests PRIMERO — archivo:** `backend/tests/test_plan145_log_throttle.py` (usa la fixture `caplog`)

> **Precisión de captura (C3, obligatoria para evitar falso rojo):** cada test usa un logger **nombrado y propagante** `lg = logging.getLogger("test145.throttle")` y **fija el nivel de captura** con `caplog.set_level(logging.INFO, logger="test145.throttle")` **antes** de llamar al helper (si no, un record a INFO con el root en WARNING se descarta antes de llegar al handler de `caplog` → 0 registros → falso rojo). Los asserts cuentan `[r for r in caplog.records if r.name == "test145.throttle"]`. Todos los helpers loguean con el `level`/logger que el test pasa explícitamente.
- `test_log_state_change_logs_first_then_suppresses_same_state`: `caplog.set_level(INFO, "test145.throttle")`; dos llamadas `log_state_change("k", "S", lg, logging.INFO, "msg")` → 1 solo registro; la 2ª devuelve `False`.
- `test_log_state_change_relogs_on_change`: `state="A"`, luego `state="B"` (mismo key/level INFO) → 2 registros.
- `test_log_throttled_rate_limits`: monkeypatch `time.monotonic` (0.0 luego 10.0 con `min_interval_s=60`) → 1 registro; avanzar a 100.0 → 2º registro (captura a INFO).
- `test_warn_once_logs_exactly_once`: 3 llamadas misma key → 1 registro nivel WARNING (captura a WARNING, default OK).
- `test_reset_clears_state`: loguear, `reset(key)`, volver a loguear → 2 registros.
- `test_public_surface_frozen` (C1/ADICIÓN): `assert set(log_throttle.__all__) == {"log_state_change","log_throttled","warn_once","reset"}` (centinela de contrato para 147/148).

**Comando:** `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_plan145_log_throttle.py -q`

**Criterio de aceptación (binario):** el comando anterior sale **verde (6 passed)**.

**Flag:** ninguna (librería pura; no cambia comportamiento hasta que un call-site la use).
**Impacto por runtime:** N/A — módulo de logging runtime-agnóstico; idéntico en los 3. Fallback: si el import fallara, los call-sites lo importan lazy (F4) y degradan al `logger.warning` directo.
**Trabajo del operador:** ninguno.

---

### F1 — Strip ANSI en el FileHandler diario

**Objetivo (1 frase).** Que el `_DailyStackyFileHandler` escriba texto **sin secuencias ANSI** al `.log`, conservando los colores en la consola.

**Valor.** Elimina 6.590 secuencias/día del archivo; los `.log` vuelven a ser grep-eables y legibles. Con la ADICIÓN (paso 4), también limpia el **visor System Log de la UI** (sink DB).

**Archivos a editar:** `backend/services/local_file_logging.py` (formatter + primitiva) y `backend/services/console_log_handler.py` (aplicar el mismo strip al sink SystemLog/UI — paso 4).

**Cambios exactos:**
1. Imports arriba: agregar `import os` y `import re`.
2. Agregar constante + formatter + gate:
```python
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

class _AnsiStrippingFormatter(logging.Formatter):
    """Igual que logging.Formatter pero elimina secuencias ANSI del resultado."""
    def format(self, record: logging.LogRecord) -> str:
        return _ANSI_RE.sub("", super().format(record))

def _strip_ansi_enabled() -> bool:
    return os.getenv("STACKY_LOG_STRIP_ANSI", "true").lower() != "false"
```
3. En `install_file_log_handler` (línea ~77), reemplazar la construcción del formatter:
```python
# ANTES:
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
# DESPUÉS:
fmt_cls = _AnsiStrippingFormatter if _strip_ansi_enabled() else logging.Formatter
handler.setFormatter(fmt_cls("%(asctime)s %(levelname)s [%(name)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
```
4. **[ADICIÓN ARQUITECTO — strip ANSI también en el sink SystemLog/UI (C2)].** El `_SystemLogHandler` (`services/console_log_handler.py:25`) persiste `self.format(record)` en `SystemLog.context_json` (`:61`, `:68` `[V]`) con un `logging.Formatter` plano (`:83`), así que **el visor System Log de la UI muestra las secuencias ANSI como basura**. Aplicar el **mismo** strip ahí, reutilizando la clase de `local_file_logging` (import lazy para no crear ciclo) y **gateado por la misma env-var** `STACKY_LOG_STRIP_ANSI`:
```python
# services/console_log_handler.py, dentro de install_console_log_handler(), reemplazar
# el formatter plano (línea ~83) por:
from services.local_file_logging import _AnsiStrippingFormatter, _strip_ansi_enabled  # lazy
fmt_cls = _AnsiStrippingFormatter if _strip_ansi_enabled() else logging.Formatter
handler.setFormatter(fmt_cls("%(asctime)s [%(name)s] %(message)s"))
```
Esto **no** toca el sink de terminal real (que conserva color) ni cambia el formato del System Log salvo por quitar el ESC. Reusa la primitiva de F1 (0 duplicación).
**Casos borde:** el strip toca **el archivo `.log` y el sink SystemLog/UI**; el `StreamHandler` de `basicConfig` (terminal real) queda con colores → DX de terminal intacta. El regex `\x1b\[[0-9;]*m` cubre SGR (color/reset); no toca datos legítimos (los `[stacky.xxx]` de nombre de logger no llevan `\x1b`). El `_AnsiStrippingFormatter.format` opera sobre la **cadena de salida** de `super().format()`, **no** muta `record.message`, así que cada handler formatea el mismo record de forma independiente (el terminal sigue viendo color).

**Tests PRIMERO — archivo:** `backend/tests/test_plan145_ansi_strip.py`

> **Cleanup obligatorio (C4, Windows).** El test de integración debe **remover y cerrar** el handler que agregó, no solo resetear el flag, o el teardown de `tmp_path` fallará al `unlink` un `.log` con FD abierto:
> ```python
> import logging, local_file_logging as lfl
> root = logging.getLogger()
> before = set(root.handlers)
> lfl._installed = False
> lfl.install_file_log_handler(base_dir=tmp_path)
> try:
>     ... # emitir y assert
> finally:
>     for h in set(root.handlers) - before:
>         root.removeHandler(h); h.close()
>     lfl._installed = False
> ```
- `test_formatter_strips_ansi`: construir un `LogRecord` con `msg='\x1b[33mGET /x HTTP/1.1\x1b[0m'`; `_AnsiStrippingFormatter(...).format(record)` **no** contiene `\x1b` y **sí** contiene `GET /x HTTP/1.1`.
- `test_plain_formatter_keeps_ansi_when_disabled`: con `monkeypatch.setenv("STACKY_LOG_STRIP_ANSI","false")`, `_strip_ansi_enabled()` es `False` (y `logging.Formatter` conserva ANSI).
- `test_file_handler_writes_clean_line` (integración): con el patrón de cleanup de arriba, `install_file_log_handler(base_dir=tmp_path)`, emitir un record ANSI vía `logging.getLogger("werkzeug").info('\x1b[33m...\x1b[0m')`, `h.close()` para flushear, leer `tmp_path/stacky-<hoy>.log` y assert que **no** hay `\x1b`.
- `test_format_does_not_mutate_record` (C2): formatear el mismo `LogRecord` ANSI con `_AnsiStrippingFormatter` y luego con `logging.Formatter`; el segundo resultado **sí** conserva `\x1b` (prueba que el strip no muta el record → el terminal real mantiene color).
- `test_systemlog_handler_uses_stripping_formatter` (ADICIÓN, C2): tras `install_console_log_handler()`, el `formatter` del `_SystemLogHandler` instalado es instancia de `_AnsiStrippingFormatter` cuando `STACKY_LOG_STRIP_ANSI` no es `false`. (Cleanup análogo: remover el handler agregado.)

**Comando:** `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_plan145_ansi_strip.py -q`

**Criterio de aceptación (binario):** verde (5 passed) **y** en la corrida el archivo tmp no contiene `\x1b`.

**Flag:** `STACKY_LOG_STRIP_ANSI` (env-only, default ON — ver §3.1).
**Impacto por runtime:** idéntico en los 3 (capa de logging). Fallback: `STACKY_LOG_STRIP_ANSI=false` restaura el comportamiento previo exacto.
**Trabajo del operador:** ninguno.

---

### F2 — Aislar el logging de pytest (V7)

**Objetivo (1 frase).** Que las corridas de pytest **nunca** escriban en `backend/data/logs/`, redirigiendo el FileHandler default a un directorio temporal cuando `STACKY_TEST_MODE` está activo.

**Valor.** Cierra V7 `[V]`: el log operativo de DEV deja de tener 89% de tracebacks sembrados por tests; vuelve a ser confiable para diagnóstico real.

**Archivos:**
- Editar `backend/services/local_file_logging.py`
- Crear `backend/tests/conftest.py` (no existe hoy `[V]`)

**Cambios exactos en `local_file_logging.py`:**
1. Import arriba: `import tempfile` (ya tendrá `import os` de F1).
2. Agregar helpers:
```python
def _test_mode() -> bool:
    return os.getenv("STACKY_TEST_MODE", "").lower() in {"1", "true", "yes"}

def _test_logs_dir() -> Path:
    return Path(tempfile.gettempdir()) / "stacky-test-logs"
```
3. En `install_file_log_handler`, resolver `base_dir` respetando test-mode **solo cuando no se pasó base_dir explícito**:
```python
def install_file_log_handler(*, base_dir: Path | None = None, retention_days: int = LOG_RETENTION_DAYS) -> None:
    global _installed
    with _install_lock:
        if _installed:
            return
        if base_dir is None:
            base_dir = _test_logs_dir() if _test_mode() else logs_dir()
        handler = _DailyStackyFileHandler(base_dir, retention_days)
        ...
```
**Casos borde:** si un test pasa `base_dir=` explícito (como en F1/F2 integración), ese path **gana** (para poder ejercitar el handler). Solo la instalación **default** (la que dispara `create_app`) se redirige a tmp bajo test-mode. Producción: `STACKY_TEST_MODE` no está seteado → sigue en `data/logs/` (idéntico a hoy).

**Contenido exacto de `backend/tests/conftest.py`:**
```python
"""Aísla el logging de pytest (Plan 145 / V7): setea STACKY_TEST_MODE antes de
que cualquier módulo de app importe/instale el FileHandler, para que los tests
no escriban en backend/data/logs/. También asegura backend/ en sys.path."""
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

os.environ.setdefault("STACKY_TEST_MODE", "1")
```
**Por qué `backend/tests/conftest.py` (y no `backend/conftest.py`):** pytest **siempre** colecta el `conftest.py` del directorio del test que corre. Como los tests viven en `backend/tests/` y se ejecutan por archivo (`pytest backend/tests/test_X.py`), este conftest se importa **antes** que el módulo de test → `STACKY_TEST_MODE` queda seteado antes de cualquier `create_app`. `setdefault` respeta un valor explícito del operador (no pisa).

**Tests PRIMERO — archivo:** `backend/tests/test_plan145_pytest_log_isolation.py`

> **Cleanup (C4):** todos los tests que instalan usan el patrón `before/removeHandler+close/_installed=False` de F1 (no dejar FD abiertos → teardown de `tmp_path` limpio en Windows).
- `test_conftest_sets_test_mode`: `assert os.environ.get("STACKY_TEST_MODE")` es truthy (prueba que el conftest corrió).
- `test_install_redirects_to_tmp_under_test_mode`: con `STACKY_TEST_MODE=1`, `install_file_log_handler()` (sin base_dir), emitir un log, y assert que se creó `stacky-<hoy>.log` bajo `_test_logs_dir()` y **no** bajo `logs_dir()`. Cleanup: remover+cerrar handler, `_installed=False`.
- `test_explicit_base_dir_wins`: `install_file_log_handler(base_dir=tmp_path)`, log, assert archivo en `tmp_path` (el path explícito gana aunque test-mode esté activo). Cleanup: remover+cerrar handler, `_installed=False`.

**Comando:** `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_plan145_pytest_log_isolation.py -q`

**Criterio de aceptación (binario):** verde (3 passed). Verificación manual complementaria: tras correr cualquier suite, `grep -c "pytest-of-" backend/data/logs/stacky-<hoy>.log` no crece por nuevas corridas (las nuevas líneas van a `%TEMP%/stacky-test-logs/`).

**Flag:** `STACKY_TEST_MODE` (seteada por `conftest.py`; env-only). No es harness flag (test-infra).
**Impacto por runtime:** N/A (infra de tests, no toca runtimes). Producción sin `STACKY_TEST_MODE` = comportamiento idéntico al actual.
**Trabajo del operador:** ninguno.

---

### F3 — Silenciar el 404 de `pipeline/status`: ruta shim + filtro de access-log

**Objetivo (1 frase).** Eliminar el ruido de `GET /api/v1/pipeline/status` respondiendo un **200 estable** (backward-compatible) y filtrando del archivo el access-log de esa ruta no-op.

**Valor.** Corta 10.687+12.094 líneas de ruido/día que esconden 404 reales. Es el ítem #1 de higiene (§5 del reporte).

**Decisión de diseño (ambas opciones documentadas, se elige la robusta):**
- **Opción A — identificar/eliminar el poller:** *rechazada como acción principal*. El cliente **no está en el repo** (`grep` de `v1/pipeline/status` en `backend/**`, `frontend/src`, `vscode_extension` = 0 `[V]`); es externo/legacy o un bundle minificado fuera de nuestro control. No podemos removerlo desde nuestro código; dejarlo 404 no arregla el ruido.
- **Opción B — ruta shim 200 + filtro de access-log:** *elegida*. Agregar la ruta **no rompe nada** (era 404, ahora 200); convierte el 404 en un 200 estable sin datos sensibles, y el filtro de access-log evita que el 200 (o cualquier residual) inunde el **archivo**. Es la más robusta y backward-compatible, y funciona aunque el poller nunca se actualice. Defensa en profundidad: aun con el shim apagado, el filtro por sí solo mantiene limpio el archivo.

**Archivos a editar:**
- `backend/api/__init__.py` (agregar la ruta shim, junto a `health` en línea 115)
- `backend/services/local_file_logging.py` (filtro de access-log)

**Cambio en `backend/api/__init__.py` (tras la ruta `health`, ~línea 117):**
```python
@api_bp.get("/v1/pipeline/status")
def pipeline_status_shim():
    """Plan 145 — shim de compatibilidad. La ruta real nunca existió; un cliente
    externo/legacy (fuera del repo) la pollea ~11k-12k/día generando ruido 404.
    Respondemos un 200 estable y neutro para silenciarlo. Kill-switch:
    STACKY_PIPELINE_STATUS_SHIM=false vuelve a 404."""
    import os
    from flask import abort
    if os.getenv("STACKY_PIPELINE_STATUS_SHIM", "true").lower() == "false":
        abort(404)
    return {"status": "unknown",
            "detail": "compatibility shim — no pipeline status is tracked at this endpoint"}, 200
```
**Casos borde:** el payload es estático y honesto (`status: "unknown"`) — no miente un pipeline "ok"/"running". Con el kill-switch en `false` se restaura el 404 exacto de hoy. La ruta queda bajo el prefix `/api` de `api_bp` (`api/__init__.py:58`) → path efectivo `/api/v1/pipeline/status`, que es el que el poller pega `[V]`.

**Cambio en `backend/services/local_file_logging.py` (filtro de access-log, solo archivo):**
```python
_DEFAULT_SUPPRESSED_PATHS = ("/api/v1/pipeline/status",)

def _access_log_suppress_enabled() -> bool:
    return os.getenv("STACKY_ACCESS_LOG_SUPPRESS", "true").lower() != "false"

def _suppressed_paths() -> tuple[str, ...]:
    extra = os.getenv("STACKY_ACCESS_LOG_SUPPRESS_PATHS", "").strip()
    paths = list(_DEFAULT_SUPPRESSED_PATHS)
    if extra:
        paths += [p.strip() for p in extra.split(",") if p.strip()]
    return tuple(paths)

class _AccessLogNoiseFilter(logging.Filter):
    """Descarta del FileHandler los access-logs de werkzeug de rutas ruidosas
    conocidas (no-op pollers). No toca otros loggers ni la consola."""
    def __init__(self, paths: tuple[str, ...]) -> None:
        super().__init__()
        self._paths = paths
    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "werkzeug":
            return True
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001
            return True
        return not any(p in message for p in self._paths)
```
Y en `install_file_log_handler`, tras `handler.setFormatter(...)`:
```python
if _access_log_suppress_enabled():
    handler.addFilter(_AccessLogNoiseFilter(_suppressed_paths()))
```
**Casos borde:** el filtro solo mira records del logger `werkzeug` (los access-logs) y solo la ruta exacta suprimida; **cualquier otro 404 real y todo el resto del access-log siguen escribiéndose**. Se aplica al handler de **archivo** únicamente (consola intacta). Es aditivo al shim: si el shim está ON, la ruta es 200 y el filtro igual la descarta del archivo (no queremos 11k líneas 200/día tampoco).

**Decisión de scope sobre el sink DB/UI (C2).** El filtro de access-log es **file-only por diseño**; el sink `_SystemLogHandler`→`SystemLog` (UI) **NO** se filtra en F3. Razón: (a) el shim convierte el 404 en **200**, que ya no es un "error" que confunda en el visor; (b) filtrar `werkzeug` dentro del `_SystemLogHandler` requeriría replicar el `Filter` en otro handler y arriesgar ocultar access-logs útiles del visor; (c) el **volumen** en la DB de este poller se ataca mejor en la causa (poller externo) o con retención de `SystemLog`, fuera del alcance de 145. Se documenta como límite **explícito** (v1 lo omitía). Si el flood de `pipeline/status` en el visor molestara, es un follow-up de una línea (agregar `_AccessLogNoiseFilter` al `_SystemLogHandler`), no un cambio de contrato.

**Tests PRIMERO — archivo:** `backend/tests/test_plan145_pipeline_status_shim.py`
- `test_shim_returns_200_by_default`: construir app mínima `app = Flask(__name__); from api import api_bp; app.register_blueprint(api_bp)`; `client.get("/api/v1/pipeline/status")` → `status_code == 200` y `resp.get_json()["status"] == "unknown"`.
- `test_shim_disabled_returns_404`: `monkeypatch.setenv("STACKY_PIPELINE_STATUS_SHIM","false")` → mismo GET → `404`.
- `test_access_filter_drops_noisy_werkzeug_record`: `rec = logging.LogRecord("werkzeug", INFO, "", 0, '... "GET /api/v1/pipeline/status?project=X HTTP/1.1" 404 -', None, None)`; `_AccessLogNoiseFilter(_suppressed_paths()).filter(rec) is False`.
- `test_access_filter_keeps_other_paths`: mismo filtro con una línea `"GET /api/health HTTP/1.1" 200` → `True`.
- `test_access_filter_ignores_non_werkzeug`: record de logger `stacky.config` con la ruta en el texto → `True` (solo se filtra werkzeug).

**Comando:** `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_plan145_pipeline_status_shim.py -q`

**Criterio de aceptación (binario):** verde (5 passed).

**Flag:** `STACKY_PIPELINE_STATUS_SHIM` (default ON) + `STACKY_ACCESS_LOG_SUPPRESS` (default ON), env-only (§3.1).
**Impacto por runtime:** idéntico en los 3 (routing Flask + logging). Fallback: apagar cualquiera de las dos env-vars restaura el comportamiento previo (404 + access-log completo).
**Trabajo del operador:** ninguno.

---

### F4 — Aplicar el helper de dedup al warning `agents_dir` (D7) + cross-ref 147/148

**Objetivo (1 frase).** Demostrar el helper de F0 end-to-end aplicándolo al warning de `agents_dir` (D7, 149×/día) — el único warning de preflight **no** propiedad de otro plan — colapsándolo a 1 por cambio de estado.

**Valor.** Cierra el residual D7 (agents_dir) y valida el helper con una integración real, sin invadir el alcance de 147 (outputs_dir) ni 148 (PAT/Jira). Deja el patrón listo para que 147/148 lo repliquen.

**Archivo a editar:** `backend/config.py` — función `_project_agents_dir_if_configured()` (línea 20; warning en líneas 37–41 `[V]`).

**Cambio exacto:** reemplazar el `_config_logger.warning(...)` directo por `log_state_change` keyeado por el path inválido (import **lazy** dentro de la función para evitar cualquier ciclo de import, ya que `config.py` se importa muy temprano):
```python
    candidate = Path(raw).expanduser()
    if candidate.is_dir():
        return candidate.resolve()

    from services.log_throttle import log_state_change  # lazy: evita ciclo de import
    log_state_change(
        "config.agents_dir_invalid",          # key
        str(raw),                              # state: re-loguea si cambia el path malo
        _config_logger,
        logging.WARNING,
        "agents_dir configurado para el proyecto activo no existe o no es carpeta: %s. "
        "Uso la fuente canónica de Stacky Agents.",
        raw,
    )
    return None
```
**Casos borde:** si el operador arregla el path (pasa a existir), no se entra a la rama (0 logs). Si configura **otro** path inválido, el `state` cambia y re-loguea 1 vez (correcto). El import lazy garantiza que si `log_throttle` fallara al importar, se puede degradar (ver fallback abajo); pero al ser stdlib-only no debería fallar.

**Cross-ref explícito (dejar constancia en el doc, no tocar esos archivos):**
- **147** wrappea sus warnings residuales de `outputs_dir` (`app.py:163-168`, 4.761×) con `log_state_change("preflight.outputs_dir", od_exists, ...)` **después** de arreglar la causa raíz de la resolución de rutas. 145 **no** toca `app.py:163-168`.
- **148** wrappea `PAT ADO expirado` (V3, 975×) y `sync Jira saltado` (`app.py:82`, 448×) con `log_state_change`/`warn_once` **después** de agregar backoff/circuit-breaker. 145 **no** toca `app.py:82` ni el sync ADO.
- 145 solo aplica el helper a **agents_dir** (D7), que ningún otro plan de la serie reclama.

**Tests PRIMERO — archivo:** `backend/tests/test_plan145_agents_dir_dedup.py`

> **Captura (C3):** el warning real sale por el logger `stacky.config` a nivel WARNING, que el root captura por default; aun así, fijar `caplog.set_level(logging.WARNING, logger="stacky.config")` para robustez. Como `config.py` importa `get_active_project`/`get_project_config` **lazy dentro** de la función (`config.py:22`), monkeypatchear `project_manager.get_active_project`/`get_project_config` funciona (se resuelven en tiempo de llamada). `import services.log_throttle as log_throttle` para `reset()`.
- `test_agents_dir_invalid_logs_once_for_same_path`: `log_throttle.reset()`; monkeypatch `project_manager.get_active_project` → un proyecto y `get_project_config` → `{"agents_dir": "Z:/no/existe"}`; llamar `config._project_agents_dir_if_configured()` **dos veces**; assert exactamente **1** registro `stacky.config`/WARNING con "agents_dir configurado".
- `test_agents_dir_relogs_on_different_path`: `reset()`; primera llamada con `Z:/no/existe`, segunda con `Q:/otro/malo` → **2** registros.
- `test_agents_dir_valid_logs_nothing`: config con `agents_dir` = un `tmp_path` real (existe) → función devuelve el path resuelto, **0** warnings.

**Comando:** `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_plan145_agents_dir_dedup.py -q`

**Criterio de aceptación (binario):** verde (3 passed).

**Flag:** ninguna (higiene grado-bugfix sobre un warning existente; solo cambia la frecuencia, nunca oculta un cambio de estado — ver §3.1 justificación). Import lazy = degradación segura.
**Impacto por runtime:** idéntico en los 3 (resolución de `agents_dir` es común). Fallback: si se quisiera revertir, basta volver al `_config_logger.warning` directo (sin env-var; es una línea).
**Trabajo del operador:** ninguno.

---

### F5 — Consolidación: documentación de env-vars + verificación integral

**Objetivo (1 frase).** Dejar documentadas las env-vars kill-switch, confirmar que no se rompió nada existente, y verificar los KPIs.

**Archivos a editar:** ninguno de código nuevo. Documentar las 5 env-vars de §3.1 en el bloque de comentarios de `backend/services/local_file_logging.py` (docstring del módulo, arriba de todo) y en este plan (§3.1, ya hecho). **No** regenerar `harness_defaults.env` (no hay flags de arnés).

**Regresión (correr por archivo, cada uno debe seguir verde):**
- Suite de flags (asegurar que **no** rompimos el centinela, aunque no tocamos FLAG_REGISTRY):
  `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_harness_flags.py -q`
- Los 5 archivos nuevos de este plan (F0–F4), cada uno por separado (ver comandos por fase).
- Sanidad de import (no ciclos; incluye el sink SystemLog de la ADICIÓN):
  `backend/.venv/Scripts/python.exe -c "import sys,os; sys.path.insert(0,'backend'); import config, services.local_file_logging, services.console_log_handler, services.log_throttle; print('ok')"`

**Verificación de KPI (manual, tras un arranque real del backend en dev):**
1. Arrancar el backend, dejar correr el poller unos minutos.
2. `grep -c "v1/pipeline/status" backend/data/logs/stacky-<hoy>.log` → **0** (shim 200 + filtro).
3. `grep -c $'\x1b\\[' backend/data/logs/stacky-<hoy>.log` → **0** (ANSI stripped).
4. Correr un test cualquiera y confirmar `%TEMP%/stacky-test-logs/stacky-<hoy>.log` recibe las líneas de pytest, no `backend/data/logs/`.

**Criterio de aceptación (binario):** todos los comandos de regresión verdes **y** los 4 chequeos de KPI cumplen.

**Flag:** N/A.
**Impacto por runtime:** N/A.
**Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| R1 | El shim 200 confunde a un cliente que esperaba 404 para saber "no hay pipeline". | Baja | Bajo | El payload dice `status:"unknown"` (no miente "ok"); el cliente hoy ya tolera el 404 (sigue polleando). Kill-switch `STACKY_PIPELINE_STATUS_SHIM=false` revierte al 404 exacto. |
| R2 | El filtro de access-log oculta un 404 real de otra ruta. | Muy baja | Medio | El filtro matchea **solo** el path exacto `pipeline/status` y **solo** el logger `werkzeug`; cualquier otra ruta/logger pasa. Cubierto por `test_access_filter_keeps_other_paths` y `test_access_filter_ignores_non_werkzeug`. |
| R3 | `conftest.py` nuevo altera el rootdir/colección de pytest de otros tests. | Baja | Medio | El conftest solo setea env + sys.path (idempotente, `setdefault`); no define fixtures autouse ni hooks de colección. Regresión F5 corre suites existentes por archivo. |
| R4 | `STACKY_TEST_MODE` filtra a producción y manda logs a tmp. | Muy baja | Medio | En prod la env-var **no** está seteada (solo la pone el conftest de tests). `setdefault` respeta cualquier valor explícito. |
| R5 | Import de `log_throttle` en `config.py` genera ciclo (config se importa temprano). | Muy baja | Alto | Import **lazy** dentro de `_project_agents_dir_if_configured` + `log_throttle` es stdlib-only (no importa config ni nada del repo). Chequeo de ciclo en F5. |
| R6 | El strip ANSI borra datos legítimos que casualmente contienen `\x1b[`. | Muy baja | Bajo | El regex es SGR estándar (`\x1b\[[0-9;]*m`); los mensajes de Stacky no contienen bytes ESC salvo los colores de werkzeug/click. Solo afecta el archivo (consola intacta). |
| R7 | El helper de dedup mantiene estado global que crece sin límite. | Muy baja | Bajo | Las keys son un conjunto acotado y estable (nombres de warnings, no valores por request). `reset()` disponible para tests. |
| R8 | El strip ANSI en el `_SystemLogHandler` (ADICIÓN) crea un ciclo de import `console_log_handler` ↔ `local_file_logging`. | Muy baja | Medio | El import de `_AnsiStrippingFormatter`/`_strip_ansi_enabled` es **lazy dentro de `install_console_log_handler()`**; `local_file_logging` solo importa `runtime_paths` (no importa `console_log_handler`) → no hay ciclo. Cubierto por el chequeo de import de F5 (se agrega `services.console_log_handler`). |
| R9 | Otro test del mismo archivo se apoya en handlers que un test de F1/F2 dejó colgados. | Baja | Bajo | Cleanup C4 (remover+cerrar el handler agregado) elimina el leak; ademas evita `PermissionError` de Windows al limpiar `tmp_path`. |

---

## 6. Fuera de scope (lo hace otro plan de la serie)

- **Causa raíz** de `outputs_dir`/`repo_root` mal resueltos (V2/D8) → **147** (auto-contenido; puede migrar al helper de 145 opcionalmente, no depende).
- **Causa raíz** de PAT ADO expirado (V3), Jira sin credenciales (V8), 502 LLM local/ADO (D6), api-version connectionData (D9) → **148** (su circuit-breaker persistido ES su dedup; no depende de 145). 145 no toca `app.py:82` ni el sync ADO.
- **Filtrado del sink SystemLog/UI** para el access-log de `pipeline/status` y retención de la tabla `SystemLog` → follow-up (ver decisión de scope en F3); 145 sí limpia el ANSI de ese sink (ADICIÓN F1).
- Fix del import `Execution`→`AgentExecution` (V1, `ado_edit_learning.py:259`), `mkdir` del SQLite ledger (V5), re-deploy con `CLAUDE_CODE_CLI_MODEL_FALLBACK` (V4) → **146**.
- Trust de workspace (D1), stall watchdog (D2), reaper 120min (D3), unificación de estados terminales `needs_review` (D4) → **144**.
- `pending-task.json` inválido (D5) y excepciones no manejadas en endpoints (V6) → **149**.
- Rotación/compresión de logs por tamaño, envío a un sink externo (ELK/Grafana), telemetría estructurada `.jsonl` del runtime → no en esta serie.

---

## 7. Glosario, orden de implementación y DoD

### Glosario (términos Stacky usados)
- **`_DailyStackyFileHandler`:** handler de logging (`services/local_file_logging.py:23`) que escribe a `data/logs/stacky-YYYY-MM-DD.log`.
- **`install_file_log_handler()`:** instala ese handler en el root logger (idempotente vía `_installed`); lo llama `create_app` en `app.py:190`.
- **Access-log de werkzeug:** las líneas `127.0.0.1 - - [...] "GET ... HTTP/1.1" <code>` emitidas por el logger `werkzeug`; propagan al root → al FileHandler.
- **Preflight:** chequeos al arranque/ciclo en `app.py` (`_log_completion_preflight`, etc.) que emiten warnings de configuración.
- **Kill-switch env-only:** env-var booleana default ON leída con `os.getenv(...,"true")`, sin FlagSpec de arnés (patrón `STACKY_DEMO_SEED_ENABLED`).
- **Shim:** ruta mínima de compatibilidad que responde estable para silenciar un cliente que no controlamos.
- **Runtime:** el backend de ejecución del agente (Codex CLI / Claude Code CLI / GitHub Copilot Pro); estos fixes son runtime-agnósticos.

### Orden de implementación (numerado)
1. **F0** — `services/log_throttle.py` + tests (fundación; sin dependencias).
2. **F1** — strip ANSI en `local_file_logging.py` + tests.
3. **F2** — `_test_mode`/redirect + `backend/tests/conftest.py` + tests.
4. **F3** — ruta shim en `api/__init__.py` + filtro access-log en `local_file_logging.py` + tests.
5. **F4** — aplicar `log_state_change` a `config.py` (agents_dir) + tests + cross-ref 147/148.
6. **F5** — documentación de env-vars + regresión + verificación de KPI.

> Nota de dependencia interna: F1, F2 y F3 tocan todas `local_file_logging.py`; implementarlas en orden evita conflictos de merge. F1 además toca `console_log_handler.py` (ADICIÓN). F4 depende de F0.
> Nota de orden **externo** (C1): 145 **no** tiene precedencia sobre 147/148 — ambos son auto-contenidos y no bloquean en 145. El orden numérico (145<147<148) es cómodo pero **no** obligatorio; 147 puede implementarse antes sin problema.

### Definición de Hecho (DoD) global
- [ ] `services/log_throttle.py` creado con `log_state_change`/`log_throttled`/`warn_once`/`reset` + `__all__` congelado; `test_plan145_log_throttle.py` verde (6).
- [ ] Strip ANSI activo por default en el FileHandler **y en el `_SystemLogHandler`/UI** (ADICIÓN C2); `test_plan145_ansi_strip.py` verde (5); archivo de log real sin `\x1b` y visor System Log sin `\x1b`.
- [ ] `backend/tests/conftest.py` creado; test-mode redirige a `%TEMP%/stacky-test-logs/`; `test_plan145_pytest_log_isolation.py` verde (3); pytest no escribe en `backend/data/logs/`.
- [ ] Ruta `GET /api/v1/pipeline/status` responde 200 estable; filtro de access-log activo; `test_plan145_pipeline_status_shim.py` verde (5); `grep v1/pipeline/status` sobre el log del día = 0.
- [ ] `config.py` usa `log_state_change` para el warning de agents_dir; `test_plan145_agents_dir_dedup.py` verde (3); cross-ref a 147/148 documentado.
- [ ] Regresión F5 verde (`test_harness_flags.py` + los 5 archivos nuevos, por archivo) y sin ciclos de import.
- [ ] 5 env-vars kill-switch documentadas; **no** se regeneró `harness_defaults.env`; **no** se agregó ninguna FlagSpec.
- [ ] Paridad confirmada: cambios en capa Flask/logging/test-infra → idénticos en Codex/Claude/Copilot.
- [ ] Trabajo del operador: ninguno; backward-compatible (todos los kill-switches default ON revierten con `=false`).

---

### Anexo — Anchors verificados contra el working tree (2026-07-15)

| Anchor | Estado | Nota |
|---|---|---|
| `services/local_file_logging.py:23` `_DailyStackyFileHandler`; `:66` `install_file_log_handler`; `:77-82` `logging.Formatter` plano | `[V]` | locus de F1/F2/F3 |
| `services/console_log_handler.py:25` `_SystemLogHandler`; `:61` `message=self.format(record)`; `:68` `context_json=message[:16000]`; `:76` `install_console_log_handler`; `:83` `logging.Formatter` plano | `[V]` | **tercer sink** (SystemLog DB→UI); locus de la ADICIÓN F1 paso 4 |
| `app.py:194` `install_console_log_handler()` (instala el tercer sink tras `install_file_log_handler` en `:190`) | `[V]` | confirma que hay 3 handlers en root |
| `STACKY_TEST_MODE` no aparece en ningún `.py` de `backend/` hoy | `[V]` | F2 lo introduce limpio (R4 sólido) |
| No existe `backend/tests/conftest.py` ni `backend/conftest.py` (glob confirma solo PyInstaller + `Stacky pipeline`/`QA UAT Agent`, ajenos) | `[V]` | F2 lo **crea** sin colisión |
| Ningún test en `backend/tests/**` invoca `install_file_log_handler()` sin `base_dir` ni lee `data/logs/` | `[V]` | el redirect de F2 no rompe suites existentes |
| `147` R6 (`:531`) + cross-ref (`:287`) = auto-contenido, "no dependencia dura", se implementa antes que 145; `148` R7 (`:629`) = "breaker es el dedup, no depende de 145" | `[V]` | base de C1 (dirección de dependencia invertida en v1) |
| `app.py:189` `logging.basicConfig(...)`; `:190` `install_file_log_handler()` | `[V]` | — |
| `app.py:82` `logger.warning("sync Jira saltado: %s", e)` | `[V]` | propiedad de **148** (no lo toca 145) |
| `app.py:163-168` warning `outputs_dir NO existe` | `[V]` | propiedad de **147** (no lo toca 145) |
| `config.py:20` `_project_agents_dir_if_configured`; `:37-41` warning agents_dir | `[V]` | locus de F4 (D7, sin dueño) |
| `api/__init__.py:58` `api_bp url_prefix="/api"`; `:115` ruta `health` | `[V]` | locus de F3 (shim junto a health) |
| grep `v1/pipeline/status` en `backend/**`, `frontend/src`, `vscode_extension` = 0 (solo logs + `.db`) | `[V]` | confirma que la ruta no existe: poller externo |
| No existe `backend/conftest.py` ni `backend/tests/conftest.py` (solo el de PyInstaller) | `[V]` | F2 lo **crea** |
| Sin `pytest.ini`/`pyproject.toml`/`setup.cfg`; venv = `backend/.venv`; tests hacen `sys.path.insert(0, backend)` | `[V]` | comando por archivo desde raíz del repo |
| `test_harness_flags.py:467` `_CURATED_DEFAULTS_ON`; `:700` `test_default_known_only_for_curated` | `[V]` | referencia de §3.1 (no se toca) |
| werkzeug logger sin config explícita → propaga al root → FileHandler captura el access-log con ANSI | `[V]` | evidencia: línea `"\x1b[33mGET /api/v1/pipeline/status...\x1b[0m" 404` en `data/logs/stacky-2026-07-05.log:597` |

**Anchors cross-ref de OTROS planes (verificados por exactitud del cross-ref, fuera del scope de 145):** `ado_edit_learning.py:259` `from models import Execution` `[V]` (→146); `config.py:216-218` `CLAUDE_CODE_CLI_MODEL_FALLBACK` `[V]` (→146; el reporte lo cita como `216-217`, el `os.getenv` abarca 216-218 — cosmético); `agent_completion.py:44` `TERMINAL_STATUSES` `[V]` (→144).
