"""local_file_logging.py — FileHandler diario de Stacky (data/logs/stacky-*.log).

Env-vars kill-switch introducidas por el Plan 145 (higiene/observabilidad de
logs), todas env-only con default ON (patrón `STACKY_DEMO_SEED_ENABLED` /
`STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS`, sin FlagSpec de arnés — ver
docs/145_PLAN_HIGIENE_OBSERVABILIDAD_LOGS_404_ANSI_DEDUP_PYTEST.md §3.1):

- `STACKY_LOG_STRIP_ANSI` (default "true"): elimina secuencias ANSI del
  FileHandler de archivo y del sink SystemLog/UI (console_log_handler.py).
  `=false` restaura el formatter plano previo.
- `STACKY_TEST_MODE` (la setea `backend/tests/conftest.py`, no el operador):
  redirige el FileHandler default (sin `base_dir` explícito) a
  `%TEMP%/stacky-test-logs/` para que pytest no escriba en `data/logs/`.
- `STACKY_PIPELINE_STATUS_SHIM` (default "true"): habilita la ruta shim
  `GET /api/v1/pipeline/status` (200 estable); `=false` vuelve al 404 real.
- `STACKY_ACCESS_LOG_SUPPRESS` (default "true"): filtra del archivo el
  access-log de werkzeug de rutas ruidosas conocidas (default: solo
  `pipeline/status`). `=false` restaura el access-log completo.
- `STACKY_ACCESS_LOG_SUPPRESS_PATHS` (default ""): CSV de paths extra a
  suprimir del access-log de archivo, además del default.
"""
from __future__ import annotations

import io
import logging
import os
import re
import tempfile
import threading
import time
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from runtime_paths import data_dir

LOG_RETENTION_DAYS = 14
EXPORT_DAYS = 3

_install_lock = threading.Lock()
_installed = False

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

_module_logger = logging.getLogger("stacky.local_file_logging")


class _AnsiStrippingFormatter(logging.Formatter):
    """Igual que logging.Formatter pero elimina secuencias ANSI del resultado."""

    def format(self, record: logging.LogRecord) -> str:
        return _ANSI_RE.sub("", super().format(record))


def _strip_ansi_enabled() -> bool:
    return os.getenv("STACKY_LOG_STRIP_ANSI", "true").lower() != "false"


def logs_dir() -> Path:
    return data_dir() / "logs"


def _test_mode() -> bool:
    return os.getenv("STACKY_TEST_MODE", "").lower() in {"1", "true", "yes"}


def _test_logs_dir() -> Path:
    return Path(tempfile.gettempdir()) / "stacky-test-logs"


_DEFAULT_SUPPRESSED_PATHS = (
    "/api/v1/pipeline/status",
    # Plan 156 F5 — pollers 200 de no-op que dominaban el access-log del deploy.
    # NO se agrega "/api/executions" desnudo: filter() hace `p in message`, y
    # eso sobre-suprimiría /api/executions/history y /api/executions/<id>. Solo
    # el endpoint nuevo (unico poller de executions que queda tras F2).
    "/api/diag/local",
    "/api/cost-cap",
    "/api/streak",
    "/api/executions/summary",
)


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


# ── Plan 257 — lectura LAZY de la configuracion (C8/C12) ─────────────────────
# Fuente UNICA: `config`. La lectura es SIEMPRE en call time y con
# getattr(cfg, "X", default): este modulo hoy importa solo runtime_paths + stdlib
# y `config.py` importa services.log_throttle con el comentario literal
# "# lazy: evita ciclo de import". PROHIBIDO `from config import config` a nivel
# de modulo aca, y PROHIBIDO dejar os.getenv sueltos para estos limites.


def _cfg(key: str, default):
    try:
        from config import config as cfg

        return getattr(cfg, key, default)
    except Exception:  # noqa: BLE001 — el logging jamas se cae por leer config
        return default


def _size_rotation_enabled() -> bool:
    return bool(_cfg("STACKY_LOG_SIZE_ROTATION_ENABLED", True))


def _max_log_bytes() -> int:
    try:
        return int(_cfg("STACKY_LOG_MAX_BYTES", 20 * 1024 * 1024))
    except (TypeError, ValueError):
        return 20 * 1024 * 1024


def _max_parts_per_day() -> int:
    try:
        return int(_cfg("STACKY_LOG_MAX_PARTS_PER_DAY", 10))
    except (TypeError, ValueError):
        return 10


def _effective_retention_days(explicit: int = LOG_RETENTION_DAYS) -> int:
    """Retencion efectiva. Si el llamador pidio un valor DISTINTO del default de
    la firma publica, ese manda (retro-compat); si no, la fuente de verdad es
    `config.STACKY_LOG_RETENTION_DAYS`."""
    if explicit != LOG_RETENTION_DAYS:
        return int(explicit)
    try:
        return int(_cfg("STACKY_LOG_RETENTION_DAYS", LOG_RETENTION_DAYS))
    except (TypeError, ValueError):
        return LOG_RETENTION_DAYS


def _effective_logs_dir() -> Path:
    """El mismo directorio que usa el handler instalado sin `base_dir` explicito."""
    return _test_logs_dir() if _test_mode() else logs_dir()


# ── Plan 257 F1 — throttle de firmas repetidas en los TRES sumideros ─────────
# Orden importa: primero rutas (que contienen digitos), despues numeros sueltos.
_SIG_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]|\\\\[^\s'\"\\]+[\\/]|/(?:home|var|tmp|usr|etc)/)[^\s'\"]*"
)
_SIG_NUM_RE = re.compile(r"\d+")
_SIG_MSG_MAX = 200

# ASCII puro a proposito (C17): el StreamHandler de consola en Windows puede
# estar en cp437, donde U+00D7 (el signo de multiplicar) no existe y lanzaria
# UnicodeEncodeError DENTRO del logging. Y sin ningun "%": el prefijo se
# antepone a un template que todavia no fue formateado con record.args.
_SUMMARY_PREFIX = "[x{count} repeticiones en {window:.0f}s] "
_DECISION_ATTR = "_stacky_throttle_decision"


def _log_signature(record: logging.LogRecord) -> str:
    """Firma estable de un mensaje.

    C3: la normalizacion se aplica SOLO al tramo del mensaje. `name` y `levelno`
    se concatenan DESPUES, para que `\\d+` no convierta el 30 de WARNING en "N"
    y colapse WARNING con INFO.
    """
    raw = record.msg if isinstance(record.msg, str) else str(record.msg)
    body = raw[:_SIG_MSG_MAX]
    body = _SIG_PATH_RE.sub("<PATH>", body)
    body = _SIG_NUM_RE.sub("N", body)
    return f"{record.name}|{record.levelno}|{body}"


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


class _ThrottleFilter(logging.Filter):
    """Plan 257 F1 — deja pasar la primera ocurrencia de cada firma y silencia
    las repeticiones dentro de `window_s`. El conteo acumulado se emite SIEMPRE:
    por piggyback cuando la firma reaparece, o por `flush_pending()` (F1-ter).

    NUNCA throttlea ERROR ni CRITICAL (levelno >= logging.ERROR).
    UNA sola instancia se comparte entre TODOS los handlers del root logger; el
    memo por record evita que la misma emision se cuente N veces.
    """

    def __init__(self, *, window_s: float, max_sigs: int) -> None:
        super().__init__()
        self.window_s = float(window_s)
        self.max_sigs = int(max_sigs)
        self._lock = threading.Lock()
        self._sigs: dict[str, dict] = {}

    # -- decision -----------------------------------------------------------
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            cached = getattr(record, _DECISION_ATTR, None)
            if cached is not None:
                return bool(cached)
            decision = self._decide(record)
            setattr(record, _DECISION_ATTR, decision)
            return decision
        except BaseException:  # noqa: BLE001 — jamas tumbar el logging (fail-open)
            return True

    def _decide(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.ERROR:
            return True                      # invariante duro: nunca se silencia

        ahora = time.time()
        firma = _log_signature(record)
        with self._lock:
            entrada = self._sigs.get(firma)
            if entrada is None:
                if len(self._sigs) >= self.max_sigs:
                    return True              # fail-open: preferimos ruido a silencio
                self._sigs[firma] = {
                    "logger": record.name,
                    "levelno": record.levelno,
                    "count": 1,
                    "suppressed": 0,
                    "first_seen": ahora,
                    "last_seen": ahora,
                    "last_emitted": ahora,
                }
                return True
            entrada["count"] += 1
            entrada["last_seen"] = ahora
            if (ahora - entrada["last_emitted"]) < self.window_s:
                entrada["suppressed"] += 1
                return False
            pendientes = int(entrada["suppressed"])
            entrada["suppressed"] = 0
            entrada["last_emitted"] = ahora

        if pendientes > 0 and isinstance(record.msg, str):
            record.msg = (
                _SUMMARY_PREFIX.format(count=pendientes, window=self.window_s) + record.msg
            )
        return True

    # -- lectura (F3) -------------------------------------------------------
    def snapshot(self) -> list[dict]:
        """READ-ONLY: no resetea ningun contador. Ordenado por silenciadas."""
        with self._lock:
            filas = [
                {
                    "signature": firma,
                    "logger": e["logger"],
                    "level": logging.getLevelName(e["levelno"]),
                    "count": int(e["count"]),
                    "suppressed": int(e["suppressed"]),
                    "first_seen": _iso(e["first_seen"]),
                    "last_seen": _iso(e["last_seen"]),
                }
                for firma, e in self._sigs.items()
            ]
        filas.sort(key=lambda f: (-f["suppressed"], -f["count"], f["signature"]))
        return filas

    # -- flush determinista (F1-ter) ----------------------------------------
    def flush_pending(self, reason: str) -> int:
        """Emite UN registro de resumen por cada firma con suppressed > 0 y
        resetea su contador. Devuelve cuantas firmas se emitieron.

        NUNCA se llama desde dentro de filter() (seria reentrada). El snapshot
        se toma DENTRO del lock y el logger.log se hace FUERA (mismo patron que
        services/log_throttle.py, que loguea fuera del lock a proposito).
        """
        ahora = time.time()
        pendientes: list[tuple[str, dict]] = []
        with self._lock:
            for firma, e in self._sigs.items():
                if e["suppressed"] > 0:
                    pendientes.append((firma, dict(e)))
                    e["suppressed"] = 0
                    e["last_emitted"] = ahora

        for firma, e in pendientes:
            try:
                lg = logging.getLogger(e["logger"])
                prefijo = _SUMMARY_PREFIX.format(count=e["suppressed"], window=self.window_s)
                lg.log(
                    e["levelno"],
                    prefijo + "resumen de repeticiones silenciadas [%s] (motivo: %s)",
                    firma,
                    reason,
                    # El propio filtro lo deja pasar SIN volver a contarlo.
                    extra={_DECISION_ATTR: True},
                )
            except Exception:  # noqa: BLE001 — un resumen jamas rompe el apagado
                continue
        return len(pendientes)


_throttle_filter: "_ThrottleFilter | None" = None


def get_throttle_filter() -> "_ThrottleFilter | None":
    """Instancia viva (o None si la flag esta apagada / no se instalo todavia).
    La consumen el endpoint de F3 y el flush de F1-ter. No instala nada."""
    return _throttle_filter


def install_throttle_filter() -> bool:
    """Plan 257 F1 — agrega UNA instancia compartida a TODOS los handlers del
    root logger. Idempotente. Devuelve True si quedo instalada.

    Un filtro en el LOGGER raiz no sirve: CPython evalua los filtros del logger
    que emite, y callHandlers() recorre los ancestros llamando sus HANDLERS.
    """
    global _throttle_filter
    if not bool(_cfg("STACKY_LOG_THROTTLE_ENABLED", True)):
        return False
    with _install_lock:
        if _throttle_filter is not None:
            return True
        flt = _ThrottleFilter(
            window_s=float(_cfg("STACKY_LOG_THROTTLE_WINDOW_S", 60.0)),
            max_sigs=int(_cfg("STACKY_LOG_THROTTLE_MAX_SIGNATURES", 1000)),
        )
        for h in logging.getLogger().handlers:
            h.addFilter(flt)
        _throttle_filter = flt
        return True


def flush_throttle_pending(reason: str) -> int:
    """Plan 257 F1-ter — emite el conteo acumulado aunque la firma no vuelva.

    Tres disparadores, todos FUERA del pipeline de logging: el apagado del
    proceso (services/lifecycle_log.py), la tarea periodica del loop de
    mantenimiento compartido (plan 253) y nada mas. `snapshot()` NO resetea.
    """
    flt = _throttle_filter
    if flt is None:
        return 0
    return flt.flush_pending(reason)


def reset_throttle_filter() -> None:
    """Hook de test: desinstala la instancia compartida. No corre en produccion."""
    global _throttle_filter
    with _install_lock:
        flt = _throttle_filter
        if flt is not None:
            for h in logging.getLogger().handlers:
                h.removeFilter(flt)
        _throttle_filter = None


# ── Plan 257 F4 — nivel de log en caliente ──────────────────────────────────
_VALID_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def apply_log_level(level_name: str) -> dict:
    """Plan 257 F4 — cambia el nivel del logger RAIZ en caliente, sin reiniciar.

    Devuelve {'ok': bool, 'previous': str, 'current': str, 'error': str|None}.
    Valida contra _VALID_LEVELS ANTES de tocar nada: con un nivel invalido
    devuelve ok=False y NO modifica el logging (app.py usa
    `getattr(logging, X, logging.INFO)`, que se come un "TRACE" en silencio).

    Toca UNICAMENTE logging.getLogger().setLevel(). NO toca el nivel de los
    handlers: los dos handlers propios de Stacky se construyen con level=DEBUG
    justamente para que el umbral efectivo lo gobierne el logger raiz. Y
    `basicConfig` solo actua la primera vez: no sirve para cambiar el nivel.
    """
    raiz = logging.getLogger()
    previo = logging.getLevelName(raiz.level)
    nombre = str(level_name or "").strip().upper()
    if nombre not in _VALID_LEVELS:
        return {
            "ok": False,
            "previous": previo,
            "current": previo,
            "error": f"nivel de log invalido: {level_name!r}. Validos: {', '.join(_VALID_LEVELS)}",
        }
    raiz.setLevel(getattr(logging, nombre))
    return {"ok": True, "previous": previo, "current": nombre, "error": None}


class _DailyStackyFileHandler(logging.Handler):
    """Writes Python logs to data/logs/stacky-YYYY-MM-DD.log."""

    def __init__(self, base_dir: Path, retention_days: int = LOG_RETENTION_DAYS) -> None:
        super().__init__(level=logging.DEBUG)
        self.base_dir = base_dir
        self.retention_days = retention_days
        self._current_day: date | None = None
        self._stream = None
        # Plan 257 F2 — parte del dia en curso: 0 = stacky-YYYY-MM-DD.log,
        # n>0 = stacky-YYYY-MM-DD.<n>.log. Se reinicia al cruzar medianoche.
        self._part = 0
        self._parts_warned = False

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._ensure_stream()
            if self._stream is None:
                return
            self._stream.write(self.format(record) + "\n")
            self._stream.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        try:
            if self._stream is not None:
                self._stream.close()
        finally:
            self._stream = None
            super().close()

    def _part_path(self, day: date) -> Path:
        """Plan 257 F2 — la parte 0 conserva EXACTAMENTE el nombre de siempre."""
        if self._part <= 0:
            return self.base_dir / f"stacky-{day:%Y-%m-%d}.log"
        return self.base_dir / f"stacky-{day:%Y-%m-%d}.{self._part}.log"

    def _open_part(self, day: date) -> None:
        if self._stream is not None:
            try:
                self._stream.close()
            except OSError:
                pass
        self._stream = self._part_path(day).open("a", encoding="utf-8")

    def _ensure_stream(self) -> None:
        today = date.today()
        if self._stream is not None and self._current_day == today:
            self._maybe_rotate_by_size(today)
            return

        self.base_dir.mkdir(parents=True, exist_ok=True)
        if self._stream is not None:
            self._stream.close()

        # La rotacion por dia tiene prioridad sobre la de tamano: el nombre del
        # dia manda y el contador de partes se reinicia en 0.
        self._part = 0
        self._parts_warned = False
        self._open_part(today)
        self._current_day = today
        purge_old_logs(self.base_dir, _effective_retention_days(self.retention_days))

    def _maybe_rotate_by_size(self, today: date) -> None:
        """Plan 257 F2 — techo por tamano. Con la flag apagada es un no-op y el
        comportamiento del handler queda byte-identico al de siempre.

        Al llegar al techo de partes NO se deja de loguear: se sigue escribiendo
        en la ultima parte con un unico aviso. Perder logs por exceso de logs
        seria el peor de los mundos.
        """
        if not _size_rotation_enabled():
            return
        max_bytes = _max_log_bytes()
        if max_bytes <= 0:
            return
        try:
            if self._stream.tell() < max_bytes:
                return
        except (OSError, ValueError):
            return
        if self._part >= _max_parts_per_day():
            if not self._parts_warned:
                self._parts_warned = True
                from services.log_throttle import warn_once  # stdlib-only, sin ciclos

                warn_once(
                    "local_file_logging.max_parts_reached",
                    _module_logger,
                    "log del dia: se alcanzo el techo de partes (%d); se sigue "
                    "escribiendo en la ultima. Subi el maximo de partes o el "
                    "tamano por parte si necesitas mas detalle.",
                    self._part,
                )
            return
        self._part += 1
        self._open_part(today)


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
        handler = _DailyStackyFileHandler(base_dir, retention_days)
        fmt_cls = _AnsiStrippingFormatter if _strip_ansi_enabled() else logging.Formatter
        handler.setFormatter(
            fmt_cls(
                "%(asctime)s %(levelname)s [%(name)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        if _access_log_suppress_enabled():
            handler.addFilter(_AccessLogNoiseFilter(_suppressed_paths()))
        logging.getLogger().addHandler(handler)
        _installed = True

    # Plan 257 F2 — la purga corre AL ARRANCAR, no solo al cruzar medianoche.
    # En un proceso que arranca y se apaga el mismo dia (el caso normal del
    # operador) la retencion declarada nunca llegaba a aplicarse.
    purge_old_logs(base_dir, _effective_retention_days(retention_days))


def register_log_maintenance_tasks() -> None:
    """Plan 257 F2/F1-ter — cuelga la purga de archivos y el vaciado del contador
    de repeticiones del loop de mantenimiento COMPARTIDO del plan 253.

    NO crea un thread nuevo: el loop es UNO SOLO (`_maintenance_loop`, thread
    "stacky-maintenance"). `interval_s` y `enabled` son callables A PROPOSITO:
    leer config en tiempo de registro congelaria el valor y la flag de la UI no
    aplicaria hasta reiniciar.
    """
    from services.maintenance import MaintenanceTask, register_maintenance_task

    register_maintenance_task(MaintenanceTask(
        name="log_files_purge",
        interval_s=lambda: 21600,                      # 6 h, igual que la purga del historial
        enabled=lambda: True,
        run=lambda: purge_old_logs(_effective_logs_dir(), _effective_retention_days()),
    ))
    register_maintenance_task(MaintenanceTask(
        name="log_throttle_flush",
        interval_s=lambda: max(int(_cfg("STACKY_LOG_THROTTLE_FLUSH_S", 300) or 0), 30),
        # 0 = solo flush al apagar (sin tarea periodica).
        enabled=lambda: int(_cfg("STACKY_LOG_THROTTLE_FLUSH_S", 300) or 0) > 0
                        and get_throttle_filter() is not None,
        run=lambda: flush_throttle_pending("mantenimiento periodico"),
    ))


def purge_old_logs(base_dir: Path | None = None, retention_days: int = LOG_RETENTION_DAYS) -> int:
    base = base_dir or logs_dir()
    if not base.exists():
        return 0

    cutoff = date.today() - timedelta(days=_effective_retention_days(retention_days))
    deleted = 0
    for path in base.glob("stacky-*.log"):
        day = _date_from_log_name(path)
        if day is None or day >= cutoff:
            continue
        try:
            path.unlink()
            deleted += 1
        except OSError:
            continue
    return deleted


def recent_log_files(days: int = EXPORT_DAYS, base_dir: Path | None = None) -> list[Path]:
    base = base_dir or logs_dir()
    if not base.exists():
        return []

    cutoff = date.today() - timedelta(days=max(days - 1, 0))
    files: list[Path] = []
    for path in sorted(base.glob("stacky-*.log"), reverse=True):
        day = _date_from_log_name(path)
        if day is not None and day >= cutoff:
            files.append(path)
    return files


def build_logs_zip(days: int = EXPORT_DAYS, base_dir: Path | None = None) -> bytes:
    files = recent_log_files(days=days, base_dir=base_dir)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if not files:
            zf.writestr("README.txt", "No hay logs locales para el rango solicitado.\n")
        for path in files:
            zf.write(path, arcname=path.name)
    return buffer.getvalue()


def export_filename() -> str:
    return f"stacky-logs-{datetime.now():%Y%m%d-%H%M%S}.zip"


def _date_from_log_name(path: Path) -> date | None:
    """Fecha de un archivo de log, incluidas las partes numeradas (C13).

    `Path("stacky-2026-06-01.3.log").stem` es "stacky-2026-06-01.3": el
    strptime del nombre COMPLETO lanzaba ValueError y devolvia None, asi que
    `purge_old_logs` se saltaba la parte (aunque el glob si la encontraba) y
    `recent_log_files` la excluia del ZIP de exportacion. El fix en el helper
    cubre las DOS rutas de una vez.
    """
    stem = path.stem
    prefix = "stacky-"
    if not stem.startswith(prefix):
        return None
    resto = stem[len(prefix):]
    fecha_txt, sufijo = resto[:10], resto[10:]
    if sufijo and not (sufijo.startswith(".") and sufijo[1:].isdigit()):
        return None
    try:
        return datetime.strptime(fecha_txt, "%Y-%m-%d").date()
    except ValueError:
        return None
