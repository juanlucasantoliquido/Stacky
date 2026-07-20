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
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

from runtime_paths import data_dir

LOG_RETENTION_DAYS = 14
EXPORT_DAYS = 3

_install_lock = threading.Lock()
_installed = False

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


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


class _DailyStackyFileHandler(logging.Handler):
    """Writes Python logs to data/logs/stacky-YYYY-MM-DD.log."""

    def __init__(self, base_dir: Path, retention_days: int = LOG_RETENTION_DAYS) -> None:
        super().__init__(level=logging.DEBUG)
        self.base_dir = base_dir
        self.retention_days = retention_days
        self._current_day: date | None = None
        self._stream = None

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

    def _ensure_stream(self) -> None:
        today = date.today()
        if self._stream is not None and self._current_day == today:
            return

        self.base_dir.mkdir(parents=True, exist_ok=True)
        if self._stream is not None:
            self._stream.close()

        path = self.base_dir / f"stacky-{today:%Y-%m-%d}.log"
        self._stream = path.open("a", encoding="utf-8")
        self._current_day = today
        purge_old_logs(self.base_dir, self.retention_days)


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


def purge_old_logs(base_dir: Path | None = None, retention_days: int = LOG_RETENTION_DAYS) -> int:
    base = base_dir or logs_dir()
    if not base.exists():
        return 0

    cutoff = date.today() - timedelta(days=retention_days)
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
    stem = path.stem
    prefix = "stacky-"
    if not stem.startswith(prefix):
        return None
    try:
        return datetime.strptime(stem[len(prefix):], "%Y-%m-%d").date()
    except ValueError:
        return None
