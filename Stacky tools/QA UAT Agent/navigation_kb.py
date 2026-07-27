"""navigation_kb.py — Inventario determinista de la KB de navegación (Plan 214 F1).

Cruza las pantallas declaradas en `navigation_contracts.yml` contra los artefactos
que el agente realmente tiene para navegarlas: `cache/ui_maps/*.json` y
`cache/playbooks/*.json`.

Puro, sin red, sin LLM: idéntico en los 3 runtimes. NUNCA lanza — ante cualquier
error devuelve el inventario degradado (listas vacías, cobertura 0.0).

CLI:
    python navigation_kb.py --report
    python navigation_kb.py --report --json-out cache/kb_inventory.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except Exception:  # pragma: no cover - yaml es dependencia del pipeline
    yaml = None

_TOOL_ROOT = Path(__file__).resolve().parent


def load_contract_screens(contracts_path: Path | None = None) -> list[str]:
    """Claves top-level de navigation_contracts.yml que parezcan pantallas .aspx.

    Devuelve [] si el archivo no existe, si PyYAML no está o si no parsea.
    NUNCA lanza.
    """
    path = Path(contracts_path) if contracts_path else (_TOOL_ROOT / "navigation_contracts.yml")
    if yaml is None:
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 — YAML corrupto/ausente => inventario degradado
        return []
    if not isinstance(data, dict):
        return []
    return sorted(k for k in data.keys() if isinstance(k, str) and k.lower().endswith(".aspx"))


def _stems(directory: Path) -> list[str]:
    """Stems de los *.json de un directorio. Dir inexistente => []. NUNCA lanza."""
    try:
        return sorted(p.stem for p in directory.glob("*.json"))
    except Exception:  # noqa: BLE001
        return []


def kb_inventory(root: Path | None = None) -> dict:
    """Cruza pantallas declaradas x ui_maps x playbooks. Puro, sin red, nunca lanza.

    Contrato de salida (estable, consumido por GET /api/qa-uat/kb):
        ok, screens_declared, ui_maps, playbooks, playbooks_total,
        missing_ui_maps, coverage_pct
    """
    base = Path(root) if root else _TOOL_ROOT
    screens = load_contract_screens(base / "navigation_contracts.yml")
    ui_maps = _stems(base / "cache" / "ui_maps")
    playbooks = _stems(base / "cache" / "playbooks")
    missing_ui_maps = [s for s in screens if s not in ui_maps]
    covered = len(screens) - len(missing_ui_maps)
    coverage_pct = round(100.0 * covered / len(screens), 1) if screens else 0.0
    return {
        "ok": True,
        "screens_declared": screens,
        "ui_maps": ui_maps,
        "playbooks": playbooks,
        "playbooks_total": len(playbooks),
        "missing_ui_maps": missing_ui_maps,
        "coverage_pct": coverage_pct,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Inventario de la base de conocimiento de navegación (Plan 214 F1)."
    )
    p.add_argument("--report", action="store_true",
                   help="Imprime el inventario como JSON por stdout.")
    p.add_argument("--json-out", default="",
                   help="Además del stdout, escribe el inventario en esta ruta.")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    inv = kb_inventory()
    payload = json.dumps(inv, ensure_ascii=False, indent=2)
    if args.report or not args.json_out:
        print(payload)
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload, encoding="utf-8")
        print(f"navigation_kb: inventario escrito en {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
