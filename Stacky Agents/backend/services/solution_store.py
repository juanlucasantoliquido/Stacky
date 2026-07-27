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


# ── Plan 215 F3 (ADITIVO) — altas manuales y re-scan que las preserva ───────
#
# NOTA de implementación (desvío consciente del doc 215): el doc normalizaba la
# key del documento con os.path.normpath(workspace_root), pero `rescan_and_save`
# y `load_catalog` del Plan 201 la usan CRUDA. Normalizar solo acá crearía DOS
# buckets para el mismo workspace y las altas manuales quedarían invisibles para
# el resto del catálogo. Se usa la key cruda; el normpath se aplica SOLO a la
# comparación de rutas (commonpath / dedupe).
def add_manual_solution(workspace_root: str, sln_path: str) -> dict:
    """Agrega una .sln al catálogo con origin="manual". ValueError con razón legible."""
    import os

    from services.solution_scanner import scan_single_solution

    key = workspace_root or ""
    root = os.path.normpath(key)
    target = os.path.normpath(os.path.abspath(sln_path or ""))
    # C7 — commonpath lanza ValueError con drives distintos en Windows y compara
    # case-sensitive: normcase + try/except con rechazo legible.
    try:
        inside = bool(key) and os.path.commonpath(
            [os.path.normcase(root), os.path.normcase(target)]
        ) == os.path.normcase(root)
    except ValueError:
        inside = False
    if not inside:
        raise ValueError("La ruta debe estar dentro del workspace del proyecto activo")
    with _LOCK:
        doc = _load_doc()
        block = doc.get(key)
        if not isinstance(block, dict):
            block = {"scanned_at": None, "truncated": False, "solutions": []}
        existing = [s for s in (block.get("solutions") or []) if isinstance(s, dict)]
        if any(
            os.path.normcase(s.get("sln_path", "")) == os.path.normcase(target)
            for s in existing
        ):
            block["solutions"] = existing
            return block  # idempotente: ya está
        entry = scan_single_solution(target, existing_slugs=[s.get("slug") for s in existing])
        if entry is None:
            raise ValueError("La ruta no es un archivo .sln legible")
        entry["tracked"] = _is_deployable(entry)
        entry["origin"] = "manual"
        existing.append(entry)
        existing.sort(key=lambda s: s.get("sln_path", ""))
        block["solutions"] = existing
        doc[key] = block
        _save_doc(doc)
        return block


def rescan_preserving_manual(workspace_root: str) -> dict:
    """rescan_and_save (201) + re-anexa las manuales cuyo .sln sigue existiendo."""
    import os

    if not workspace_root:
        return dict(_EMPTY_BLOCK)
    with _LOCK:
        prev = [
            s for s in ((_load_doc().get(workspace_root) or {}).get("solutions") or [])
            if isinstance(s, dict)
        ]
    manual_prev = [
        s for s in prev
        if s.get("origin") == "manual" and os.path.exists(s.get("sln_path", ""))
    ]
    block = rescan_and_save(workspace_root)  # 201 F2, intacto
    found = {os.path.normcase(s.get("sln_path", "")) for s in block.get("solutions", [])}
    for m in manual_prev:
        if os.path.normcase(m.get("sln_path", "")) not in found:
            block = add_manual_solution(workspace_root, m["sln_path"])
    return block
