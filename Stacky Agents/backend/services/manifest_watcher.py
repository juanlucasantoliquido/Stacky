"""Manifest watcher: cierra ejecuciones huérfanas usando MANIFEST.json del run.

El watcher polea `backend/data/codex_runs/<execution_id>/MANIFEST.json` y, si
encuentra un manifest terminal (status in {completed, error, cancelled}) mientras
la AgentExecution sigue marcada como `running` o `queued`, dispara el cierre del
lifecycle (mark terminal + on_execution_end).

Es naturalmente idempotente: la segunda pasada ve la execution ya cerrada y no
hace nada. Mantenemos también un cache (path, mtime) en memoria para skipear el
parseo cuando el manifest no cambió.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Iterable

import log_streamer
from db import session_scope
from models import AgentExecution
from services import ticket_status

logger = logging.getLogger("stacky.manifest_watcher")

MANIFEST_FILENAME = "MANIFEST.json"
HEARTBEAT_FILENAME = "heartbeat.json"
MANIFEST_SCHEMA_VERSION = "1"

TERMINAL_STATUSES = frozenset({"completed", "error", "cancelled"})
ACTIVE_STATUSES = frozenset({"running", "queued"})


# ── Helpers públicos ──────────────────────────────────────────────────────────


def default_runs_dir() -> Path:
    """Directorio canónico de runs: backend/data/codex_runs/."""
    return Path(__file__).resolve().parents[1] / "data" / "codex_runs"


def write_manifest(
    run_dir: Path,
    *,
    run_id: int,
    agent_type: str | None,
    status: str,
    exit_code: int | None = None,
    error_message: str | None = None,
    artifacts: list[dict] | None = None,
    signals: dict | None = None,
    extra: dict | None = None,
) -> Path:
    """Escribe MANIFEST.json en run_dir. Idempotente: sobreescribe si ya existe."""
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "agent_type": agent_type,
        "status": status,
        "written_at": datetime.utcnow().isoformat() + "Z",
        "artifacts": artifacts or [],
        "signals": signals or {},
        "exit_code": exit_code,
        "error_message": error_message,
    }
    if extra:
        manifest["extra"] = extra

    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / MANIFEST_FILENAME
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path


def write_heartbeat(
    run_dir: Path,
    *,
    execution_id: int,
    pid: int | None,
    phase: str | None = None,
) -> Path:
    """Escribe heartbeat.json. El reconciler de Fase 4 lo consume."""
    payload = {
        "execution_id": execution_id,
        "last_activity_ts": datetime.utcnow().isoformat() + "Z",
        "pid": pid,
        "phase": phase,
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / HEARTBEAT_FILENAME
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return path


# ── Watcher ───────────────────────────────────────────────────────────────────


class ManifestWatcher:
    """Polling watcher de MANIFEST.json terminales.

    Una vez arrancado, recorre `runs_dir` cada `poll_interval` segundos y procesa
    los manifests cuyo (path, mtime) cambió desde la última ronda. Si encuentra
    un manifest terminal mientras la execution está activa en DB, dispara el
    cierre del lifecycle.
    """

    def __init__(self, runs_dir: Path, *, poll_interval: float = 2.0) -> None:
        self.runs_dir = Path(runs_dir)
        self.poll_interval = float(poll_interval)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # cache de (path -> mtime_ns) ya procesados para no re-parsear basura
        self._seen: dict[str, int] = {}

    # — Lifecycle —

    def start(self) -> threading.Thread:
        if self._thread is not None and self._thread.is_alive():
            return self._thread
        self._stop.clear()

        def _loop() -> None:
            logger.info(
                "manifest watcher started (runs_dir=%s interval=%.1fs)",
                self.runs_dir,
                self.poll_interval,
            )
            while not self._stop.wait(timeout=self.poll_interval):
                try:
                    self.scan_once()
                except Exception as exc:  # noqa: BLE001
                    logger.exception("manifest watcher scan failed: %s", exc)
            logger.info("manifest watcher stopped")

        self._thread = threading.Thread(
            target=_loop, daemon=True, name="stacky-manifest-watcher"
        )
        self._thread.start()
        return self._thread

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
        self._stop.clear()

    # — Scan —

    def scan_once(self) -> int:
        """Una pasada sobre runs_dir. Retorna cantidad de manifests procesados."""
        if not self.runs_dir.exists():
            return 0
        processed = 0
        for manifest_path in self._iter_manifest_paths():
            try:
                if self._process_manifest(manifest_path):
                    processed += 1
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "manifest watcher: error procesando %s: %s", manifest_path, exc
                )
        return processed

    def _iter_manifest_paths(self) -> Iterable[Path]:
        for entry in self.runs_dir.iterdir():
            if not entry.is_dir():
                continue
            manifest = entry / MANIFEST_FILENAME
            if manifest.is_file():
                yield manifest

    def _process_manifest(self, manifest_path: Path) -> bool:
        try:
            mtime_ns = manifest_path.stat().st_mtime_ns
        except OSError:
            return False

        key = str(manifest_path)
        if self._seen.get(key) == mtime_ns:
            return False

        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("manifest watcher: manifest inválido en %s: %s", manifest_path, exc)
            # No marcar como visto: queremos re-intentar si el archivo se completa
            return False

        if not isinstance(data, dict):
            logger.warning("manifest watcher: payload no es dict en %s", manifest_path)
            self._seen[key] = mtime_ns
            return False

        status = data.get("status")
        run_id = data.get("run_id")
        if not isinstance(run_id, int) or status not in TERMINAL_STATUSES:
            # Manifest aún no es terminal (o está incompleto): no actuamos pero
            # tampoco lo marcamos seen para volver a leerlo cuando cambie.
            return False

        applied = self._close_if_orphan(run_id=run_id, manifest=data)
        # Una vez procesado un manifest terminal lo marcamos seen para no repetir
        # la consulta a DB en cada ciclo.
        self._seen[key] = mtime_ns
        return applied

    def _close_if_orphan(self, *, run_id: int, manifest: dict) -> bool:
        """Si la execution sigue activa en DB, cierra el lifecycle. Retorna True si actuó."""
        final_status: str = manifest["status"]
        error_message = manifest.get("error_message")

        ticket_id: int | None = None
        agent_type: str | None = None

        with session_scope() as session:
            exec_row = session.get(AgentExecution, run_id)
            if exec_row is None:
                logger.debug("manifest watcher: execution_id=%s no existe en DB", run_id)
                return False
            if exec_row.status not in ACTIVE_STATUSES:
                # Ya cerrada por el runner. Nada que hacer.
                return False

            exec_row.status = final_status
            if exec_row.completed_at is None:
                exec_row.completed_at = datetime.utcnow()
            if final_status == "error" and error_message and not exec_row.error_message:
                exec_row.error_message = error_message
            # marcar source para forense
            if hasattr(exec_row, "completion_source") and not exec_row.completion_source:
                exec_row.completion_source = "manifest_watcher"

            ticket_id = exec_row.ticket_id
            agent_type = exec_row.agent_type

        logger.info(
            "manifest watcher: closed execution_id=%s status=%s (orphan recovered)",
            run_id,
            final_status,
        )
        try:
            log_streamer.push(
                run_id,
                "info",
                f"manifest watcher: cerrada ejecución huérfana → {final_status}",
                group="watcher",
            )
            log_streamer.close(run_id)
        except Exception:
            logger.debug("manifest watcher: log_streamer push/close falló (no crítico)")

        if ticket_id is not None:
            try:
                ticket_status.on_execution_end(
                    ticket_id=ticket_id,
                    execution_id=run_id,
                    final_status=final_status,
                    agent_type=agent_type,
                    error=error_message if final_status == "error" else None,
                )
            except Exception:
                logger.exception(
                    "manifest watcher: on_execution_end falló para execution_id=%s", run_id
                )
        return True


# ── Singleton global para wiring desde app.py ─────────────────────────────────


_GLOBAL_LOCK = threading.Lock()
_GLOBAL_WATCHER: ManifestWatcher | None = None


def start_manifest_watcher(
    runs_dir: Path | None = None,
    *,
    poll_interval: float = 2.0,
) -> ManifestWatcher:
    """Arranca (o retorna) el watcher singleton. Idempotente."""
    global _GLOBAL_WATCHER
    with _GLOBAL_LOCK:
        if _GLOBAL_WATCHER is not None and _GLOBAL_WATCHER._thread and _GLOBAL_WATCHER._thread.is_alive():
            return _GLOBAL_WATCHER
        watcher = ManifestWatcher(
            runs_dir=runs_dir or default_runs_dir(),
            poll_interval=poll_interval,
        )
        watcher.start()
        _GLOBAL_WATCHER = watcher
        return watcher


def stop_manifest_watcher() -> None:
    """Detiene el watcher singleton si está corriendo."""
    global _GLOBAL_WATCHER
    with _GLOBAL_LOCK:
        watcher = _GLOBAL_WATCHER
        _GLOBAL_WATCHER = None
    if watcher is not None:
        watcher.stop()
