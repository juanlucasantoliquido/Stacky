"""playbook_curator.py — Valida y promueve grabaciones a playbooks (Plan 214 F1).

Envuelve `session_to_playbook.run()` con una validación estructural: una
grabación solo se promueve a playbook si el JSON resultante trae las claves
portantes que el replay necesita. Determinista, sin dependencias nuevas
(la validación es por presencia de claves, no por jsonschema).

DESVÍO DOCUMENTADO DEL PLAN 214 F1 (bug del plan, corregido al construir)
------------------------------------------------------------------------
El plan ordenaba validar contra `required` de `schemas/Playbook.schema.json`.
Verificado contra el árbol (2026-07-26): ese `required` incluye `playbook_id` y
`arrival_assertions`, que `session_to_playbook.run()` NUNCA emite
(session_to_playbook.py:202-215) y que NINGUNO de los playbooks del `cache/`
tiene. Aplicar la regla al pie de la letra habría renombrado el 100% de la KB
viva a `.rejected.json` — es decir, la fase que existe para HACER CRECER la KB
la habría destruido.

Criterio implementado: se valida el contrato EFECTIVO del productor
(`_REQUIRED_KEYS`, la intersección entre lo que el schema exige y lo que el
conversor realmente escribe) y la diferencia contra el schema se REPORTA como
`schema_drift` — visible, nunca silenciada, nunca destructiva.

CLI:
    python playbook_curator.py --session evidence/recordings/latest
    python playbook_curator.py --session evidence/recordings/latest --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import session_to_playbook

_TOOL_ROOT = Path(__file__).resolve().parent
_SCHEMA_PATH = _TOOL_ROOT / "schemas" / "Playbook.schema.json"

logger = logging.getLogger(__name__)

# Contrato EFECTIVO: claves que el schema exige Y que session_to_playbook emite.
# Si falta una de estas, el playbook es irreplayable => se rechaza.
_REQUIRED_KEYS = (
    "schema_version",
    "goal_slug",
    "target_screen",
    "navigation_steps",
    "action_steps",
)


def schema_required_keys(schema_path: Path | None = None) -> list[str]:
    """`required` declarado por Playbook.schema.json. [] si no se puede leer."""
    path = Path(schema_path) if schema_path else _SCHEMA_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    req = data.get("required")
    return [k for k in req if isinstance(k, str)] if isinstance(req, list) else []


def validate_playbook(playbook: dict, schema_path: Path | None = None) -> dict:
    """Valida un playbook YA cargado. Puro, nunca lanza.

    {"ok": bool, "missing": [...], "schema_drift": [...]}
      missing      → claves del contrato efectivo ausentes (motivo de rechazo)
      schema_drift → claves que el schema exige pero el productor no emite
                     (informativo: NO rechaza, ver el desvío documentado arriba)
    """
    if not isinstance(playbook, dict):
        return {"ok": False, "missing": list(_REQUIRED_KEYS), "schema_drift": []}
    missing = [k for k in _REQUIRED_KEYS if k not in playbook]
    drift = [k for k in schema_required_keys(schema_path)
             if k not in playbook and k not in missing]
    return {"ok": not missing, "missing": missing, "schema_drift": drift}


def validate_playbook_file(path: Path, schema_path: Path | None = None) -> dict:
    """Valida el playbook en disco. Si es inválido lo renombra a `.rejected.json`.

    Nunca lanza. El renombrado es el mecanismo de cuarentena: el archivo no se
    borra (queda auditable), pero deja de contar como playbook usable.
    """
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        rejected = _quarantine(path)
        return {"ok": False, "error": "playbook_unreadable", "message": str(exc)[:300],
                "missing": [], "schema_drift": [], "rejected_path": rejected}

    res = validate_playbook(data, schema_path)
    if res["ok"]:
        return {"ok": True, "playbook_path": str(path),
                "missing": [], "schema_drift": res["schema_drift"]}

    rejected = _quarantine(path)
    return {"ok": False, "error": "playbook_schema_invalid",
            "missing": res["missing"], "schema_drift": res["schema_drift"],
            "rejected_path": rejected}


def _quarantine(path: Path) -> str | None:
    """Renombra <slug>.json → <slug>.rejected.json. Nunca lanza."""
    try:
        target = path.with_suffix("").with_suffix(".rejected.json") \
            if path.suffix == ".json" else Path(str(path) + ".rejected.json")
        if target.exists():
            target.unlink()
        path.rename(target)
        logger.warning("playbook_curator: playbook rechazado → %s", target)
        return str(target)
    except Exception:  # noqa: BLE001
        return None


def curate(session_dir: Path, dry_run: bool = True) -> dict:
    """Convierte una grabación en playbook y lo valida antes de dejarlo promovido.

    dry_run=True  → NO escribe nada; devuelve validated=False (no hay archivo que validar).
    dry_run=False → escribe vía session_to_playbook.run() y valida el resultado;
                    si es inválido, lo pone en cuarentena y devuelve ok=False.
    """
    session_dir = Path(session_dir)
    try:
        result = session_to_playbook.run(session_dir, dry_run=dry_run, verbose=False)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": "session_to_playbook_failed",
                "message": str(exc)[:300], "validated": False, "dry_run": dry_run}

    if not isinstance(result, dict) or not result.get("ok"):
        out = dict(result) if isinstance(result, dict) else {}
        out.setdefault("ok", False)
        out.setdefault("error", "session_to_playbook_failed")
        out["validated"] = False
        out["dry_run"] = dry_run
        return out

    if dry_run:
        return {"ok": True, "dry_run": True, "validated": False,
                "playbook_path": result.get("playbook_path"),
                "goal_slug": result.get("goal_slug")}

    written = Path(result.get("playbook_path") or "")
    validation = validate_playbook_file(written)
    if not validation["ok"]:
        return {**validation, "validated": False, "dry_run": False,
                "goal_slug": result.get("goal_slug")}

    return {"ok": True, "validated": True, "dry_run": False,
            "playbook_path": str(written),
            "goal_slug": result.get("goal_slug"),
            "schema_drift": validation.get("schema_drift", [])}


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Valida y promueve una grabación a playbook (Plan 214 F1).")
    p.add_argument("--session", required=True,
                   help="Directorio de la grabación (con session.json). "
                        "Usá evidence/recordings/latest para la última.")
    p.add_argument("--dry-run", action="store_true",
                   help="No escribe el playbook; solo simula la conversión.")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )
    res = curate(Path(args.session), dry_run=args.dry_run)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
