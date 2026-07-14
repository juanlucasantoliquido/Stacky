"""services/dbcompare_runs.py — Plan 123 F2: corridas comparativas del Comparador de BD.

Orquesta snapshot(origen) -> snapshot(destino) -> diff en un thread por corrida, con
lock por par de ambientes, persistencia por archivo (data_dir()/db_compare/runs/) y
marcador stale para runs huérfanos (>30 min running).

Ver Stacky Agents/docs/123_PLAN_DB_COMPARE_MOTOR_DIFF_SEVERIDADES_Y_CORRIDAS.md §F2/§F4.

NOTA (fix C2, crítica v2 del plan 123): el par se registra en _ACTIVE_PAIRS de forma
ATÓMICA, bajo _ACTIVE_LOCK, dentro de create_run() — ANTES de lanzar el thread de fondo.
Registrarlo recién dentro de _execute_run() dejaría una ventana de carrera entre dos
POST /compare casi simultáneos del mismo par.

NOTA (fix C5, crítica v2 del plan 123): _scrub() es siempre best-effort — si no puede
resolver la credencial de un alias (p.ej. el ambiente fue borrado a mitad de la corrida),
igual devuelve un string sin lanzar. Si _scrub lanzara, el run nunca llegaría a
status="error" y quedaría "running" para siempre.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone

from runtime_paths import data_dir
from services import dbcompare_diff, dbcompare_registry, dbcompare_snapshot

_RUNS_DIRNAME = "db_compare/runs"
_STALE_AFTER_SEC = 1800
_MAX_RUNS_KEPT = 100

_ACTIVE_PAIRS: set = set()
_ACTIVE_LOCK = threading.Lock()


class DbCompareBusyError(RuntimeError):
    """Ya hay una corrida activa para ese par de ambientes."""


class DbCompareRunError(RuntimeError):
    """La corrida no puede iniciarse o completarse."""


# --------------------------------------------------------------------------
# Persistencia
# --------------------------------------------------------------------------

def _runs_dir():
    d = data_dir() / _RUNS_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _run_path(run_id: str):
    return _runs_dir() / f"{run_id}.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def _write_run(run: dict) -> None:
    path = _run_path(run["run_id"])
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(run, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _read_run(run_id: str) -> dict | None:
    path = _run_path(run_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _update(run_id: str, **fields) -> None:
    run = _read_run(run_id)
    if run is None:
        return
    run.update(fields)
    _write_run(run)


def _is_stale(run: dict) -> bool:
    if run.get("status") != "running":
        return False
    started = datetime.fromisoformat(run["started_at"].replace("Z", "+00:00"))
    return (_now() - started).total_seconds() > _STALE_AFTER_SEC


# --------------------------------------------------------------------------
# Scrub de credenciales (best-effort, nunca lanza — [FIX C5])
# --------------------------------------------------------------------------

def _scrub(text_: str, source_alias: str, target_alias: str) -> str:
    result = text_
    for alias in (source_alias, target_alias):
        try:
            cred = dbcompare_registry.get_credential(alias)
        except Exception:  # noqa: BLE001 — un fallo al resolver la credencial NUNCA debe
            continue        # impedir que el run llegue a status="error".
        password = (cred or {}).get("password")
        if password and password in result:
            result = result.replace(password, "***")
    return result


# --------------------------------------------------------------------------
# Corridas
# --------------------------------------------------------------------------

def _resolve_snapshot(alias: str, mode: str) -> dict:
    if mode == "fresh":
        return dbcompare_snapshot.take_snapshot(alias)
    snap = dbcompare_snapshot.latest_snapshot(alias)
    if snap is None:
        raise DbCompareRunError(f"sin snapshot cacheado de '{alias}'; tomá uno o usá modo fresco")
    return snap


def create_run(source_alias: str, target_alias: str, *, mode: str = "fresh") -> dict:
    if mode not in ("fresh", "cached"):
        raise DbCompareRunError(f"modo desconocido: '{mode}' (fresh|cached)")

    source_env = dbcompare_registry.get_environment(source_alias)
    target_env = dbcompare_registry.get_environment(target_alias)
    if source_env is None:
        raise DbCompareRunError(f"ambiente desconocido: '{source_alias}'")
    if target_env is None:
        raise DbCompareRunError(f"ambiente desconocido: '{target_alias}'")
    if source_env["engine"] != target_env["engine"]:
        raise DbCompareRunError(
            f"los ambientes tienen motores distintos: {source_env['engine']} vs {target_env['engine']}."
        )

    pair = frozenset({source_alias, target_alias})
    # [FIX C2] registro atómico bajo lock, ANTES de escribir el run o lanzar el thread.
    with _ACTIVE_LOCK:
        if pair in _ACTIVE_PAIRS:
            raise DbCompareBusyError(f"ya hay una corrida activa para {source_alias} vs {target_alias}")
        _ACTIVE_PAIRS.add(pair)

    started = _now()
    run_id = f"run_{started:%Y%m%dT%H%M%SZ}_{source_alias}_vs_{target_alias}"
    run = {
        "run_id": run_id,
        "source_alias": source_alias, "target_alias": target_alias,
        "engine": source_env["engine"],
        "mode": mode, "status": "running", "phase": "queued",
        "started_at": _iso(started), "finished_at": None, "duration_ms": 0,
        "source_snapshot_id": None, "target_snapshot_id": None,
        "summary": None, "diff": None, "error": None,
    }
    try:
        _write_run(run)
        threading.Thread(
            target=_execute_run,
            args=(run_id, source_alias, target_alias, mode, pair),
            daemon=True,
        ).start()
    except Exception:
        with _ACTIVE_LOCK:
            _ACTIVE_PAIRS.discard(pair)
        raise

    prune_runs()
    return run


def _execute_run(run_id, source_alias, target_alias, mode, pair) -> None:
    start_monotonic = time.monotonic()
    try:
        _update(run_id, phase="snapshot_source")
        snap_s = _resolve_snapshot(source_alias, mode)
        _update(run_id, source_snapshot_id=snap_s.get("id"))

        _update(run_id, phase="snapshot_target")
        snap_t = _resolve_snapshot(target_alias, mode)
        _update(run_id, target_snapshot_id=snap_t.get("id"))

        _update(run_id, phase="diff")
        diff = dbcompare_diff.diff_snapshots(snap_s, snap_t)

        duration_ms = int((time.monotonic() - start_monotonic) * 1000)
        _update(
            run_id, status="done", phase="done", diff=diff, summary=diff["summary"],
            finished_at=_iso(_now()), duration_ms=duration_ms,
        )
    except Exception as exc:  # noqa: BLE001 — cualquier fallo de snapshot/diff termina el run en error
        duration_ms = int((time.monotonic() - start_monotonic) * 1000)
        message = _scrub(str(exc), source_alias, target_alias)
        _update(run_id, status="error", error=message, finished_at=_iso(_now()), duration_ms=duration_ms)
    finally:
        with _ACTIVE_LOCK:
            _ACTIVE_PAIRS.discard(pair)


def get_run(run_id: str) -> dict | None:
    run = _read_run(run_id)
    if run is None:
        return None
    if _is_stale(run):
        run = dict(run)
        run["stale"] = True
    return run


def list_runs(limit: int = 50) -> list[dict]:
    limit = max(0, min(int(limit), 200))
    runs = []
    for path in _runs_dir().glob("*.json"):
        if path.suffix == ".tmp":
            continue
        try:
            run = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        meta = {k: v for k, v in run.items() if k != "diff"}
        meta["stale"] = _is_stale(run)
        runs.append(meta)
    runs.sort(key=lambda r: r.get("started_at") or "", reverse=True)
    return runs[:limit]


def prune_runs() -> int:
    paths = sorted(_runs_dir().glob("*.json"), key=lambda p: p.stat().st_mtime)
    excess = len(paths) - _MAX_RUNS_KEPT
    removed = 0
    if excess > 0:
        for path in paths[:excess]:
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    return removed
