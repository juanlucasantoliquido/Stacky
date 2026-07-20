"""Plan 178 — Vigía de drift programado (Watch v1 + DriftEvent v1 + sweep).

Read-only por construcción: el vigía SOLO invoca dbcompare_runs.create_run()
(snapshot de esquema + diff del motor 122/123). Jamás compara datos (126),
jamás genera scripts (125), jamás publica fuera de la máquina.

Aprobación humana explícita: cada watch nace del click "Vigilar este par" del
operador (excepción dura 3: credenciales/conectividad a BD del cliente no
garantizadas en una instalación default — y se evita la sorpresa de conexiones
no pedidas). Sin ese click, este módulo no abre ninguna conexión.

Semántica CERRADA de DriftEvent kinds (F3):
- drift_new: primera cosecha con items>0, o transición 0→>0.
- drift_worse: sube danger, o sube warn (con items>0 antes y después). Subas
  solo de info NO emiten (anti-ruido).
- drift_cleared: transición >0→0 (paridad recuperada).
- watch_error: run del vigía terminó en error / quedó stale / aliases inválidos.
  Un run fallido emite este evento EXACTAMENTE una vez (cosecha idempotente por
  last_harvested_run_id, fix C1).
- baseline_violation: definido en F4 (_check_baselines_for_run).
"""
from __future__ import annotations

import json
import os
import threading
import zlib
from datetime import datetime, timezone
from pathlib import Path

from runtime_paths import data_dir

_WATCH_DIRNAME = "db_compare/watch"
WATCH_VERSION = 1
_IO_LOCK = threading.Lock()

_BACKOFF_CAP_MIN = 1440  # 24 h
_EVENTS_CAP = 200
_EVENT_KINDS = ("drift_new", "drift_worse", "drift_cleared", "baseline_violation", "watch_error")


class DbCompareWatchError(RuntimeError):
    """Watch inválido (aliases inexistentes, par duplicado, watch_id desconocido)."""


def _watch_dir() -> Path:
    d = data_dir() / _WATCH_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _watches_path() -> Path:
    return _watch_dir() / "watches.json"


def _events_path() -> Path:
    return _watch_dir() / "events.json"


def _write_json_atomic(path: Path, payload: dict) -> None:
    # Patrón tmp + os.replace (mismo espíritu que _write_bundle_atomic,
    # services/dbcompare_scripts.py): nunca queda un JSON parcial.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(path))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def watch_id_for(source_alias: str, target_alias: str) -> str:
    return f"{source_alias}__{target_alias}"


# --------------------------------------------------------------------------
# CRUD de watches (Plan 178 F1) — escritura atómica.
# --------------------------------------------------------------------------

def list_watches() -> list[dict]:
    path = _watches_path()
    if not path.exists():
        return []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return list(doc.get("watches") or [])


def _save_watches(watches: list[dict]) -> None:
    _write_json_atomic(_watches_path(), {"version": WATCH_VERSION, "watches": watches})


def upsert_watch(source_alias: str, target_alias: str, *, enabled: bool) -> dict:
    # El click "Vigilar este par" ES la aprobación humana explícita para que Stacky
    # se conecte periódicamente en background a ESE par (y solo a ese). Excepción
    # dura 3: credenciales/conectividad a la BD del cliente no están garantizadas
    # en una instalación default; sin este click no se abre ninguna conexión.
    from services import dbcompare_registry
    if source_alias == target_alias:
        raise DbCompareWatchError("origen y destino no pueden ser el mismo ambiente")
    if "__" in source_alias or "__" in target_alias:
        # Fix C9: el watch_id usa "__" como separador; un alias que lo contenga
        # haría ambiguo el id ("A__B"+"C" vs "A"+"B__C").
        raise DbCompareWatchError("aliases con '__' no son vigilables (separador reservado)")
    if dbcompare_registry.get_environment(source_alias) is None:
        raise DbCompareWatchError(f"ambiente desconocido: '{source_alias}'")
    if dbcompare_registry.get_environment(target_alias) is None:
        raise DbCompareWatchError(f"ambiente desconocido: '{target_alias}'")
    wid = watch_id_for(source_alias, target_alias)
    with _IO_LOCK:
        watches = list_watches()
        existing = next((w for w in watches if w["watch_id"] == wid), None)
        if existing is None:
            existing = {
                "watch_id": wid,
                "source_alias": source_alias,
                "target_alias": target_alias,
                "enabled": enabled,
                "created_at": _iso(_now()),
                "last_attempt_at": None,
                "last_run_id": None,
                "last_done_run_id": None,
                "last_harvested_run_id": None,
                "last_summary": None,
                "consecutive_errors": 0,
            }
            watches.append(existing)
        else:
            existing["enabled"] = enabled
        _save_watches(watches)
    return dict(existing)


def delete_watch(watch_id: str) -> bool:
    with _IO_LOCK:
        watches = list_watches()
        remaining = [w for w in watches if w["watch_id"] != watch_id]
        if len(remaining) == len(watches):
            return False
        _save_watches(remaining)
    return True


def _update_watch(watch_id: str, **fields) -> None:
    with _IO_LOCK:
        watches = list_watches()
        for w in watches:
            if w["watch_id"] == watch_id:
                w.update(fields)
                break
        _save_watches(watches)


# --------------------------------------------------------------------------
# DriftEvent v1 (Plan 178 F3) — detección de transiciones y avisos locales.
# --------------------------------------------------------------------------

def list_events(limit: int = 50, *, unread_only: bool = False) -> list[dict]:
    path = _events_path()
    if not path.exists():
        return []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    events = list(doc.get("events") or [])
    if unread_only:
        events = [e for e in events if not e.get("read")]
    events.sort(key=lambda e: e.get("created_at") or "", reverse=True)
    return events[: max(0, min(int(limit), _EVENTS_CAP))]


def unread_count() -> int:
    return len(list_events(_EVENTS_CAP, unread_only=True))


def _append_event(kind: str, *, watch: dict | None, run_id: str | None, detail: dict) -> dict:
    if kind not in _EVENT_KINDS:
        # Fix C8: NO usar assert (desaparece bajo python -O).
        raise ValueError(f"DriftEvent kind desconocido: '{kind}'")
    now = _now()
    base_id = f"evt_{now:%Y%m%dT%H%M%SZ}_{(watch or {}).get('watch_id') or detail.get('alias') or 'global'}"
    with _IO_LOCK:
        events = list_events(_EVENTS_CAP)
        event_id, n = base_id, 1
        while any(e["event_id"] == event_id for e in events):
            n += 1
            event_id = f"{base_id}_{n}"
        event = {
            "event_id": event_id,
            "kind": kind,
            "watch_id": (watch or {}).get("watch_id"),
            "source_alias": (watch or {}).get("source_alias"),
            "target_alias": (watch or {}).get("target_alias"),
            "run_id": run_id,
            "created_at": _iso(now),
            "read": False,
            "detail": detail,
        }
        events.insert(0, event)
        _write_json_atomic(_events_path(), {"version": 1, "events": events[:_EVENTS_CAP]})
    return event


def mark_events_read(event_ids: list[str] | None = None) -> int:
    """event_ids=None => marcar TODOS. Retorna cuántos cambió."""
    with _IO_LOCK:
        events = list_events(_EVENTS_CAP)
        changed = 0
        for e in events:
            if not e.get("read") and (event_ids is None or e["event_id"] in event_ids):
                e["read"] = True
                changed += 1
        if changed:
            _write_json_atomic(_events_path(), {"version": 1, "events": events})
    return changed


def _items_count(summary: dict) -> int:
    sev = (summary or {}).get("by_severity") or {}
    return int(sev.get("info") or 0) + int(sev.get("warn") or 0) + int(sev.get("danger") or 0)


def _emit_transition_events(watch: dict, run: dict, new_summary: dict) -> None:
    prev = watch.get("last_summary")
    new_n = _items_count(new_summary)
    if prev is None:
        if new_n > 0:
            _append_event("drift_new", watch=watch, run_id=run["run_id"], detail=new_summary)
        return
    prev_n = _items_count(prev)
    prev_sev = prev.get("by_severity") or {}
    new_sev = new_summary.get("by_severity") or {}
    if prev_n == 0 and new_n > 0:
        _append_event("drift_new", watch=watch, run_id=run["run_id"], detail=new_summary)
    elif prev_n > 0 and new_n == 0:
        _append_event("drift_cleared", watch=watch, run_id=run["run_id"], detail=new_summary)
    elif int(new_sev.get("danger") or 0) > int(prev_sev.get("danger") or 0) or int(new_sev.get("warn") or 0) > int(prev_sev.get("warn") or 0):
        _append_event("drift_worse", watch=watch, run_id=run["run_id"], detail=new_summary)
    # info-only sube: silencio deliberado (anti-ruido).


def _append_event_watch_error(watch: dict, run: dict) -> None:
    _append_event(
        "watch_error", watch=watch, run_id=run.get("run_id"),
        detail={"error": (run.get("error") or "corrida stale/desconocida")[:300]},
    )


# --------------------------------------------------------------------------
# Baseline hook (Plan 178 F4) — cero conexiones nuevas; solo API pública del
# módulo dbcompare_baseline (fix C7).
# --------------------------------------------------------------------------

def _check_baselines_for_run(watch: dict, run: dict) -> None:
    """Tras cosechar un run done del vigía: si alguno de los 2 aliases tiene
    baseline pinneado, diffear el snapshot RECIÉN tomado (ya en disco) contra el
    baseline. Cero conexiones nuevas. Dedup por content_hash del snapshot."""
    from services import dbcompare_baseline, dbcompare_diff, dbcompare_snapshot
    for alias, snap_key in (
        (watch["source_alias"], "source_snapshot_id"),
        (watch["target_alias"], "target_snapshot_id"),
    ):
        baseline = dbcompare_baseline.get_baseline(alias)
        if baseline is None:
            continue
        fresh = dbcompare_snapshot.load_snapshot(run.get(snap_key) or "")
        base_snap = dbcompare_baseline.load_baseline_snapshot(alias)
        if fresh is None or base_snap is None:
            continue
        fresh_hash = fresh.get("content_hash")
        if fresh_hash == base_snap.get("content_hash"):
            continue  # idéntico al baseline: sin violación
        if fresh_hash == baseline.get("last_alerted_content_hash"):
            continue  # ya avisado por ESTE estado exacto (dedup)
        try:
            diff = dbcompare_diff.diff_snapshots(base_snap, fresh)
        except dbcompare_diff.DbCompareDiffError:
            continue
        if _items_count(diff.get("summary") or {}) == 0:
            continue
        _append_event(
            "baseline_violation", watch=watch, run_id=run["run_id"],
            detail={
                "alias": alias,
                "baseline_snapshot_id": baseline["snapshot_id"],
                "by_severity": (diff.get("summary") or {}).get("by_severity"),
                "parity_score": (diff.get("summary") or {}).get("parity_score"),
            },
        )
        dbcompare_baseline.mark_alerted(alias, fresh_hash)


# --------------------------------------------------------------------------
# Sweep del vigía (Plan 178 F2) — determinista: el reloj se inyecta en tests.
# --------------------------------------------------------------------------

def _interval_minutes() -> int:
    import config as _config
    try:
        val = int(getattr(_config.config, "STACKY_DB_COMPARE_WATCH_INTERVAL_MIN", 60))
    except (TypeError, ValueError):
        val = 60
    return max(5, min(val, 1440))


def _max_runs_per_day() -> int:
    import config as _config
    try:
        val = int(getattr(_config.config, "STACKY_DB_COMPARE_WATCH_MAX_RUNS_PER_DAY", 48))
    except (TypeError, ValueError):
        val = 48
    return max(1, min(val, 100))


def _radar_enabled() -> bool:
    import config as _config
    return bool(getattr(_config.config, "STACKY_DB_COMPARE_ENABLED", False)) and bool(
        getattr(_config.config, "STACKY_DB_COMPARE_RADAR_ENABLED", False)
    )


def _jitter_seconds(watch_id: str, interval_min: int) -> int:
    """Jitter DETERMINISTA por par: 0..20% del intervalo, estable entre ticks.
    Distribuye pares sin aleatoriedad real (testeable sin seeds)."""
    span = max(1, (interval_min * 60) // 5)
    return zlib.crc32(watch_id.encode("utf-8")) % span


def _parse_iso(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _is_due(watch: dict, now: datetime, interval_min: int) -> bool:
    last = _parse_iso(watch.get("last_attempt_at"))
    if last is None:
        return True
    effective_min = min(interval_min * (2 ** int(watch.get("consecutive_errors") or 0)), _BACKOFF_CAP_MIN)
    due_at_sec = last.timestamp() + effective_min * 60 + _jitter_seconds(watch["watch_id"], interval_min)
    return now.timestamp() >= due_at_sec


def _runs_launched_today(now: datetime) -> int:
    from services import dbcompare_runs
    today = now.strftime("%Y-%m-%d")
    count = 0
    for meta in dbcompare_runs.list_runs(200):
        if meta.get("initiated_by", "operator") != "watch":
            continue
        if (meta.get("started_at") or "").startswith(today):
            count += 1
    return count


def _harvest_watch(watch: dict) -> None:
    """Cosecha el resultado del último run lanzado (dos tiempos: lanzar en un
    tick, leer el resultado en el siguiente). Actualiza backoff y emite eventos.

    IDEMPOTENTE POR RUN (fix C1): last_harvested_run_id marca el run ya
    cosechado — done, error o stale por igual. Sin este corte, un run en error
    se re-cosecharía en CADA tick de 60 s: consecutive_errors explotaría
    (~60/hora) y events.json se llenaría de watch_error duplicados."""
    from services import dbcompare_runs
    run_id = watch.get("last_run_id")
    if not run_id or run_id == watch.get("last_harvested_run_id"):
        return
    run = dbcompare_runs.get_run(run_id)
    if run is None:
        # El run fue borrado por la retención antes de poder cosecharlo:
        # marcar harvested para no reintentar por siempre.
        _update_watch(watch["watch_id"], last_harvested_run_id=run_id)
        return
    status = run.get("status")
    if status == "running" and not run.get("stale"):
        return  # sigue corriendo; nada que cosechar todavía
    if status == "error" or (status == "running" and run.get("stale")):
        _update_watch(
            watch["watch_id"],
            consecutive_errors=int(watch.get("consecutive_errors") or 0) + 1,
            last_harvested_run_id=run_id,
        )
        _append_event_watch_error(watch, run)
        return
    if status == "done":
        new_summary = {
            "by_severity": (run.get("summary") or {}).get("by_severity") or {"info": 0, "warn": 0, "danger": 0},
            "parity_score": (run.get("summary") or {}).get("parity_score", 100.0),
        }
        _emit_transition_events(watch, run, new_summary)
        _check_baselines_for_run(watch, run)
        _update_watch(
            watch["watch_id"],
            consecutive_errors=0,
            last_done_run_id=run_id,
            last_harvested_run_id=run_id,
            last_summary=new_summary,
        )


def run_watch_sweep_once(now: datetime | None = None) -> int:
    """Un tick del vigía. Retorna cuántas corridas LANZÓ (0 en no-op).
    Gates evaluados acá adentro (hot-apply, patrón plan 117)."""
    if not _radar_enabled():
        return 0
    watches = [w for w in list_watches() if w.get("enabled")]
    if not watches:
        return 0
    now = now or _now()
    interval_min = _interval_minutes()
    launched = 0
    from services import dbcompare_runs
    from services.dbcompare_runs import DbCompareBusyError, DbCompareRunError
    for watch in watches:
        _harvest_watch(watch)
    # Releer: la cosecha pudo actualizar backoff/last_summary/harvested.
    watches = [w for w in list_watches() if w.get("enabled")]
    budget = _max_runs_per_day() - _runs_launched_today(now)
    for watch in watches:
        if budget - launched <= 0:
            break
        if not _is_due(watch, now, interval_min):
            continue
        pending_id = watch.get("last_run_id")
        if pending_id and pending_id != watch.get("last_harvested_run_id"):
            run = dbcompare_runs.get_run(pending_id)
            if run is not None and run.get("status") == "running" and not run.get("stale"):
                continue  # aún corre: no encimar
        try:
            run = dbcompare_runs.create_run(
                watch["source_alias"], watch["target_alias"], mode="fresh", initiated_by="watch"
            )
        except DbCompareBusyError:
            continue  # lock del par ocupado: skip sin error
        except DbCompareRunError as exc:
            # alias borrado o motores distintos: deshabilitar y avisar
            _update_watch(watch["watch_id"], enabled=False)
            _append_event_watch_error(watch, {"run_id": None, "error": str(exc)})
            continue
        launched += 1
        _update_watch(watch["watch_id"], last_attempt_at=_iso(now), last_run_id=run["run_id"])
    return launched
