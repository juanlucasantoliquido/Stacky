"""services/deploy_store.py — Plan 120 F3. Persistencia del Centro de Despliegues.

CRUD de apps desplegables (`deploy_apps.json`) + ledger append-only
(`deploy_ledger.jsonl`) + locks en memoria anti-concurrencia por (app_id,
target). Mismo patrón de tolerancia a JSON corrupto que
`server_registry._load` (degradar a vacío, nunca crash) y el mismo
`threading.Lock` de módulo protege TAMBIÉN el ledger (C6 v2): dos ÓRDENES
concurrentes corren en threads distintos (F4) y sin lock el
leer-mapear-reescribir de `update_ledger_entry` pierde líneas.
"""
from __future__ import annotations

import json
import logging
import secrets
import threading
from datetime import datetime, timezone

from runtime_paths import data_dir
from services.deploy_planner import validate_app

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()  # protege apps.json Y el ledger (C6 v2)
_RUN_LOCKS: set[tuple[str, str]] = set()  # (app_id, target) actualmente corriendo


def _apps_path():
    return data_dir() / "deploy_apps.json"


def _ledger_path():
    return data_dir() / "deploy_ledger.jsonl"


# ── apps CRUD ────────────────────────────────────────────────────────────────

def _load_apps() -> list[dict]:
    path = _apps_path()
    try:
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            logger.warning("deploy_apps.json no es una lista; se ignora")
            return []
        return [a for a in data if isinstance(a, dict)]
    except Exception as exc:  # noqa: BLE001 — JSON corrupto: degradar a vacío
        logger.warning("deploy_apps.json inválido (%s); se ignora", type(exc).__name__)
        return []


def _save_apps(apps: list[dict]) -> None:
    path = _apps_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(apps, indent=2, ensure_ascii=False), encoding="utf-8")


def list_apps() -> list[dict]:
    return sorted(_load_apps(), key=lambda a: a.get("id", ""))


def get_app(app_id: str) -> dict | None:
    for a in _load_apps():
        if a.get("id") == app_id:
            return a
    return None


def upsert_app(app: dict) -> dict:
    errors = validate_app(app)
    if errors:
        raise ValueError("; ".join(errors))
    with _LOCK:
        apps = _load_apps()
        app_id = app["id"]
        existing_idx = next((i for i, a in enumerate(apps) if a.get("id") == app_id), None)
        if existing_idx is None:
            apps.append(app)
        else:
            apps[existing_idx] = app
        _save_apps(apps)
    return app


def delete_app(app_id: str) -> bool:
    with _LOCK:
        apps = _load_apps()
        remaining = [a for a in apps if a.get("id") != app_id]
        if len(remaining) == len(apps):
            return False
        _save_apps(remaining)
    return True


# ── ledger (append-only) ────────────────────────────────────────────────────

def _load_ledger_lines() -> list[dict]:
    path = _ledger_path()
    if not path.exists():
        return []
    rows = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            rows.append(json.loads(raw))
        except Exception:  # noqa: BLE001 — línea corrupta: se salta
            continue
    return rows


def _save_ledger_lines(rows: list[dict]) -> None:
    path = _ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    path.write_text(text + ("\n" if rows else ""), encoding="utf-8")


def append_ledger(entry: dict) -> None:
    with _LOCK:
        path = _ledger_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def update_ledger_entry(run_id: str, patch: dict) -> None:
    """Reescribe la línea del run_id (leer TODO → mapear → escribir). El
    archivo es chico y mono-operador; el Lock de módulo (C6 v2) evita
    pérdida de líneas cuando dos órdenes concurrentes (F4, threads
    distintos) actualizan entries a la vez."""
    with _LOCK:
        rows = _load_ledger_lines()
        found = False
        for row in rows:
            if row.get("run_id") == run_id:
                row.update(patch)
                found = True
        if found:
            _save_ledger_lines(rows)


def read_ledger(app_id: str | None = None, target: str | None = None, limit: int = 100) -> list[dict]:
    """Más recientes primero. Tolerante a líneas corruptas (ya filtradas en
    _load_ledger_lines)."""
    with _LOCK:
        rows = _load_ledger_lines()
    if app_id is not None:
        rows = [r for r in rows if r.get("app_id") == app_id]
    if target is not None:
        rows = [r for r in rows if r.get("target") == target]
    rows.reverse()
    return rows[:limit]


# ── locks anti-concurrencia por (app_id, target) ────────────────────────────

def acquire_run_lock(app_id: str, target: str) -> str | None:
    key = (app_id, target)
    with _LOCK:
        if key in _RUN_LOCKS:
            return None
        _RUN_LOCKS.add(key)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"dr-{ts}-{secrets.token_hex(2)}"


def release_run_lock(app_id: str, target: str) -> None:
    key = (app_id, target)
    with _LOCK:
        _RUN_LOCKS.discard(key)


def is_locked(app_id: str, target: str | None = None) -> bool:
    """True si hay AL MENOS un run activo para la app (target=None) o para
    el (app_id, target) exacto. Usado por el guard 409 de DELETE /apps/<id>."""
    with _LOCK:
        if target is not None:
            return (app_id, target) in _RUN_LOCKS
        return any(a == app_id for a, _t in _RUN_LOCKS)


# ── derivados del ledger ────────────────────────────────────────────────────

def last_success_version(app_id: str, target: str) -> str | None:
    for row in read_ledger(app_id=app_id, target=target, limit=1000):
        if row.get("action") == "deploy" and row.get("status") == "success":
            return row.get("version_id")
        if row.get("action") == "rollback" and row.get("status") == "success":
            return row.get("version_id")
    return None


def retained_versions(app_id: str, target: str, n: int = 10) -> list[str]:
    """Versiones `success` retenidas, más recientes primero, sin duplicados."""
    seen: list[str] = []
    for row in read_ledger(app_id=app_id, target=target, limit=1000):
        if row.get("status") != "success":
            continue
        vid = row.get("version_id")
        if vid and vid not in seen:
            seen.append(vid)
        if len(seen) >= n:
            break
    return seen
