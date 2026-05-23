from __future__ import annotations

import io
import logging
import threading
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

from runtime_paths import data_dir

LOG_RETENTION_DAYS = 14
EXPORT_DAYS = 3

_install_lock = threading.Lock()
_installed = False


def logs_dir() -> Path:
    return data_dir() / "logs"


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
        handler = _DailyStackyFileHandler(base_dir or logs_dir(), retention_days)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [%(name)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
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
