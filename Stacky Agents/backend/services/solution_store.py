"""Plan 201 F2 — Persistencia del catálogo de soluciones + selección del operador.

Guarda dónde vive cada `.sln` del workspace y cuáles tildó el operador. Re-escanear
es idempotente y **respeta la decisión humana**: un slug que el operador destildó
NUNCA se re-tilda solo.

Un slug nuevo (jamás visto) arranca tildado solo si la solución es desplegable
(tiene algún proyecto web/console/service). Es un default reversible con un click,
y no dispara ningún build: compilar sigue siendo una acción explícita.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone

from runtime_paths import data_dir
from services.solution_scanner import scan_solutions_ex

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_DEPLOYABLE_TYPES = {"web", "console", "service"}

_EMPTY_BLOCK = {"scanned_at": None, "truncated": False, "solutions": []}


def store_path():
    return data_dir() / "build_solutions.json"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


def _load_doc() -> dict:
    path = store_path()
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            logger.warning("build_solutions.json no es un objeto; se ignora")
            return {}
        return data
    except Exception as exc:  # noqa: BLE001 — JSON corrupto: degradar a vacío
        logger.warning("build_solutions.json inválido (%s); se ignora", type(exc).__name__)
        return {}


def _save_doc(doc: dict) -> None:
    path = store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")


def _is_deployable(sol: dict) -> bool:
    return any(p.get("type") in _DEPLOYABLE_TYPES for p in sol.get("projects", []) or [])


def rescan_and_save(workspace_root: str) -> dict:
    """Re-escanea el workspace y persiste el catálogo. Devuelve el bloque guardado."""
    if not workspace_root:
        return dict(_EMPTY_BLOCK)
    meta = scan_solutions_ex(workspace_root)
    fresh = meta["solutions"]
    with _LOCK:
        doc = _load_doc()
        prev = (doc.get(workspace_root) or {}).get("solutions") or []
        prev_by_slug = {s.get("slug"): s for s in prev if isinstance(s, dict)}
        for sol in fresh:
            previo = prev_by_slug.get(sol["slug"])
            if previo is not None:
                # La decisión del operador manda, tildada O destildada.
                sol["tracked"] = bool(previo.get("tracked"))
            else:
                sol["tracked"] = _is_deployable(sol)
        doc[workspace_root] = {
            "scanned_at": _utcnow_iso(),
            "truncated": bool(meta["truncated"]),
            "solutions": fresh,
        }
        _save_doc(doc)
        return doc[workspace_root]


def load_catalog(workspace_root: str) -> dict:
    """Bloque persistido del workspace, o el bloque vacío si nunca se escaneó."""
    if not workspace_root:
        return dict(_EMPTY_BLOCK)
    block = _load_doc().get(workspace_root)
    if not isinstance(block, dict):
        return dict(_EMPTY_BLOCK)
    return {
        "scanned_at": block.get("scanned_at"),
        "truncated": bool(block.get("truncated", False)),
        "solutions": [s for s in (block.get("solutions") or []) if isinstance(s, dict)],
    }


def set_tracked(workspace_root: str, slug: str, tracked: bool) -> dict:
    """Tilda/destilda una solución. Slug inexistente = no-op (nunca lanza)."""
    if not workspace_root:
        return dict(_EMPTY_BLOCK)
    with _LOCK:
        doc = _load_doc()
        block = doc.get(workspace_root)
        if not isinstance(block, dict):
            return dict(_EMPTY_BLOCK)
        cambio = False
        for sol in block.get("solutions") or []:
            if isinstance(sol, dict) and sol.get("slug") == slug:
                sol["tracked"] = bool(tracked)
                cambio = True
                break
        if cambio:
            _save_doc(doc)
        return block


def tracked_solutions(workspace_root: str) -> list:
    return [s for s in load_catalog(workspace_root)["solutions"] if s.get("tracked")]
