"""patch_uimap_ado120.py — Adds ADO-120 aliases to FrmDetalleClie.aspx UI map."""
import json
from pathlib import Path

path = Path(__file__).parent / "cache" / "ui_maps" / "FrmDetalleClie.aspx.json"

with open(path, encoding="utf-8") as f:
    d = json.load(f)

existing = {e.get("alias_semantic") for e in d.get("elements", [])}

new_elements = [
    {
        "alias_semantic": "tab_obligaciones",
        "kind": "a",
        "role": "tab",
        "label": "Datos Generales",
        "asp_id": "TabControl_tabGenerales",
        "input_type": None,
        "data_testid": None,
        "class_list": ["ais-tab"],
        "selector_recommended": "#c_TabControl a:has-text('Datos Generales')",
        "selector": "#c_TabControl a:has-text('Datos Generales')",
        "robustness": "medium",
        "locator_strategy": "text",
        "is_visible": True,
        "is_interactive": True,
        "is_decorative": False,
        "confidence": 0.80,
        "fallback_selectors": ["a:has-text('Datos Generales')"],
        "position": {"x": 0, "y": 60},
        "text": "Datos Generales",
        "warning": "GridObligaciones is inside tabGenerales (default first tab); ADO-120"
    },
    {
        "alias_semantic": "OGFECPASAJEJUD",
        "kind": "th",
        "role": "columnheader",
        "label": "Fecha de ingreso judicial",
        "asp_id": None,
        "input_type": None,
        "data_testid": None,
        "class_list": ["AISGridHeader"],
        "selector_recommended": "#c_GridObligaciones th:has-text('Fecha')",
        "selector": "#c_GridObligaciones th:has-text('Fecha')",
        "robustness": "medium",
        "locator_strategy": "text",
        "is_visible": False,
        "is_interactive": False,
        "is_decorative": False,
        "confidence": 0.85,
        "fallback_selectors": ["th:has-text('Fecha de ingreso')"],
        "position": {"x": 0, "y": 0},
        "text": "Fecha de ingreso judicial",
        "warning": "ADO-120 CA-01: should NOT appear after RF-007 — use invisible oracle"
    },
]

added = []
for el in new_elements:
    alias = el["alias_semantic"]
    if alias not in existing:
        d["elements"].append(el)
        added.append(alias)
    else:
        print(f"  SKIP (already exists): {alias}")

with open(path, "w", encoding="utf-8") as f:
    json.dump(d, f, ensure_ascii=False, indent=2)

print(f"OK — added {added}. Total elements: {len(d['elements'])}")
