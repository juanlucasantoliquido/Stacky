"""Plan 178 F4 — Baseline v1: snapshot pinneado como estado bendecido de un alias.

100% local: pin/unpin/diff operan sobre snapshots YA persistidos
(data_dir()/db_compare/snapshots/, services/dbcompare_snapshot.py). NUNCA abre
conexión a BD (KPI-6).

AUTOCONTENIDO (fix C2 / KPI-8): el motor poda snapshots con
_MAX_SNAPSHOTS_PER_ALIAS=20 (dbcompare_snapshot.py) y el vigía genera ~24
snapshots/día por alias vigilado ⇒ el snapshot original del baseline muere en
<1 día. Por eso pin_baseline COPIA el Snapshot v1 completo a
baselines/<alias>.snapshot.json y toda resolución cae a esa copia si el
original ya no existe. "broken" solo si faltan AMBOS.

NOTA de diseño (fix C7): este módulo duplica 3 helpers triviales
(_write_json_atomic/_now/_iso) en lugar de importarlos de dbcompare_watch:
8 líneas duplicadas valen más que acoplarse a privados de otro módulo.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from runtime_paths import data_dir

_BASELINES_DIRNAME = "db_compare/baselines"
BASELINE_VERSION = 1
_IO_LOCK = threading.Lock()


class DbCompareBaselineError(RuntimeError):
    """Pin inválido (snapshot inexistente o de otro alias)."""


def _baselines_dir() -> Path:
    d = data_dir() / _BASELINES_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _baseline_path(alias: str) -> Path:
    return _baselines_dir() / f"{alias}.json"


def _snapshot_copy_path(alias: str) -> Path:
    return _baselines_dir() / f"{alias}.snapshot.json"


def _write_json_atomic(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(path))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def get_baseline(alias: str) -> dict | None:
    path = _baseline_path(alias)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_baseline_snapshot(alias: str) -> dict | None:
    """Snapshot v1 del baseline del alias: primero el original del motor
    (load_snapshot), después la copia autocontenida. None si faltan ambos."""
    from services import dbcompare_snapshot
    baseline = get_baseline(alias)
    if baseline is None:
        return None
    snap = dbcompare_snapshot.load_snapshot(baseline.get("snapshot_id") or "")
    if snap is not None:
        return snap
    copy_path = _snapshot_copy_path(alias)
    if not copy_path.exists():
        return None
    try:
        return json.loads(copy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def list_baselines() -> list[dict]:
    out = []
    for path in sorted(_baselines_dir().glob("*.json")):
        if path.name.endswith(".snapshot.json"):
            continue  # las copias autocontenidas no son baselines
        b = get_baseline(path.stem)
        if b is not None:
            b = dict(b)
            b["broken"] = load_baseline_snapshot(b.get("alias") or path.stem) is None
            out.append(b)
    return out


def pin_baseline(alias: str, snapshot_id: str, *, note: str = "") -> dict:
    from services import dbcompare_snapshot
    snap = dbcompare_snapshot.load_snapshot(snapshot_id)
    if snap is None:
        raise DbCompareBaselineError(f"snapshot desconocido: '{snapshot_id}'")
    if snap.get("alias") != alias:
        raise DbCompareBaselineError(f"el snapshot '{snapshot_id}' no pertenece al ambiente '{alias}'")
    doc = {
        "version": BASELINE_VERSION,
        "alias": alias,
        "snapshot_id": snapshot_id,
        "pinned_at": _iso(_now()),
        "note": (note or "")[:200],
        "last_alerted_content_hash": None,
    }
    with _IO_LOCK:
        _write_json_atomic(_snapshot_copy_path(alias), snap)  # copia AUTOCONTENIDA (fix C2)
        _write_json_atomic(_baseline_path(alias), doc)
    return doc


def unpin_baseline(alias: str) -> bool:
    with _IO_LOCK:
        path = _baseline_path(alias)
        existed = path.exists()
        if existed:
            path.unlink()
        copy_path = _snapshot_copy_path(alias)
        if copy_path.exists():
            copy_path.unlink()
    return existed


def mark_alerted(alias: str, content_hash: str) -> None:
    """API pública para el dedup de baseline_violation (fix C7: el sweep NO
    toca privados de este módulo)."""
    with _IO_LOCK:
        baseline = get_baseline(alias)
        if baseline is None:
            return
        baseline["last_alerted_content_hash"] = content_hash
        _write_json_atomic(_baseline_path(alias), baseline)


def baseline_diff(alias: str) -> dict:
    """SchemaDiff v1 (reuso puro de diff_snapshots, services/dbcompare_diff.py)
    entre el baseline pinneado (ORIGEN, original o copia autocontenida) y el
    último snapshot persistido del alias (DESTINO). Efímero: NO se persiste
    como run. Sin conexiones (KPI-6)."""
    from services import dbcompare_diff, dbcompare_snapshot
    baseline = get_baseline(alias)
    if baseline is None:
        raise DbCompareBaselineError(f"'{alias}' no tiene baseline pinneado")
    base_snap = load_baseline_snapshot(alias)
    if base_snap is None:
        raise DbCompareBaselineError(f"el snapshot del baseline ya no existe (ni la copia): '{baseline['snapshot_id']}'")
    current = dbcompare_snapshot.latest_snapshot(alias)
    if current is None:
        raise DbCompareBaselineError(f"'{alias}' no tiene ningún snapshot; tomá uno primero")
    return dbcompare_diff.diff_snapshots(base_snap, current)
