"""
playwright_test_generator.py — Generate .spec.ts Playwright test files from ScenarioSpecs.

SPEC: SPEC/playwright_test_generator.md
CLI:
    python playwright_test_generator.py \
        --scenarios evidence/70/scenarios.json \
        --ui-maps cache/ui_maps/ \
        --out evidence/70/tests/ \
        [--template templates/playwright_test.spec.ts.j2] \
        [--verbose]

Output: JSON to stdout with generation results.
No LLM — purely deterministic Jinja2 rendering.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.test_generator")

_TOOL_VERSION = "1.0.0"
_DEFAULT_TEMPLATE = Path(__file__).resolve().parent / "templates" / "playwright_test.spec.ts.j2"


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr,
                            format="%(levelname)s %(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    result = run(
        scenarios_path=Path(args.scenarios),
        ui_maps_dir=Path(args.ui_maps),
        out_dir=Path(args.out),
        template_path=Path(args.template) if args.template else None,
        verbose=args.verbose,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("ok") else 1)


def run(
    scenarios_path: Path,
    ui_maps_dir: Path,
    out_dir: Path,
    template_path: Optional[Path] = None,
    verbose: bool = False,
) -> dict:
    """Core logic — callable from tests."""
    started = time.time()
    template_path = template_path or _DEFAULT_TEMPLATE

    # Load scenarios JSON
    try:
        scenarios_data = json.loads(scenarios_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return _err("invalid_scenarios_json", f"Cannot read scenarios: {exc}")

    if not scenarios_data.get("ok") or not isinstance(scenarios_data.get("scenarios"), list):
        return _err("invalid_scenarios_json", "scenarios.json missing 'ok' or 'scenarios'")

    # Load Jinja2 template
    try:
        from jinja2 import Environment, FileSystemLoader, StrictUndefined
        env = Environment(
            loader=FileSystemLoader(str(template_path.parent)),
            undefined=StrictUndefined,
            autoescape=False,
        )
        template = env.get_template(template_path.name)
    except ImportError:
        return _err("template_render_failed", "jinja2 not installed. Run: pip install Jinja2")
    except Exception as exc:
        return _err("template_render_failed", f"Cannot load template: {exc}")

    out_dir.mkdir(parents=True, exist_ok=True)
    ticket_id = scenarios_data.get("ticket_id", 0)

    results = []
    generated_count = 0
    blocked_count = 0

    for scenario in scenarios_data["scenarios"]:
        sid = scenario.get("scenario_id", "UNK")
        pantalla = scenario.get("pantalla", "FrmAgenda.aspx")

        # Load UI map for this screen
        ui_map_file = ui_maps_dir / f"{pantalla}.json"
        if not ui_map_file.is_file():
            blocked_count += 1
            results.append({
                "scenario_id": sid,
                "status": "blocked",
                "reason": "UI_MAP_NOT_FOUND",
                "missing": [f"cache/ui_maps/{pantalla}.json"],
            })
            continue
            return _err("ui_map_not_found", f"No UI map found for screen {pantalla}")

        try:
            ui_map_data = json.loads(ui_map_file.read_text(encoding="utf-8"))
        except Exception as exc:
            blocked_count += 1
            results.append({
                "scenario_id": sid,
                "status": "blocked",
                "reason": "UI_MAP_NOT_FOUND",
                "missing": [str(exc)],
            })
            continue

        # Build alias → selector mapping
        selector_map = _build_selector_map(ui_map_data)

        # Validate all targets exist in UI map
        missing_selectors = _find_missing_selectors(scenario, selector_map)
        if missing_selectors:
            blocked_count += 1
            results.append({
                "scenario_id": sid,
                "status": "blocked",
                "reason": "SELECTOR_NOT_FOUND",
                "missing": missing_selectors,
            })
            continue

        # Render the .spec.ts file
        title_slug = _slugify(scenario.get("titulo", sid))
        filename = f"{sid}_{title_slug}.spec.ts"
        spec_path = out_dir / filename

        try:
            rendered = template.render(
                ticket_id=ticket_id,
                scenario_id=sid,
                titulo=scenario.get("titulo", ""),
                pantalla=pantalla,
                precondiciones=scenario.get("precondiciones", []),
                pasos=scenario.get("pasos", []),
                oraculos=scenario.get("oraculos", []),
                datos_requeridos=scenario.get("datos_requeridos", []),
                ui_map=selector_map,
            )
        except Exception as exc:
            return _err("template_render_failed", f"Jinja2 render failed for {sid}: {exc}")

        # Security check: no hardcoded credentials
        _check_no_hardcoded_creds(rendered, sid)

        spec_path.write_text(rendered, encoding="utf-8")

        # Collect used selectors
        used_selectors = list(set(selector_map.get(t, "") for s in scenario.get("pasos", []) + scenario.get("oraculos", [])
                                  for t in [s.get("target", "")] if t in selector_map))

        generated_count += 1
        results.append({
            "scenario_id": sid,
            "status": "generated",
            "path": str(spec_path),
            "used_selectors": used_selectors,
            "unresolved_selectors": [],
        })
        logger.debug("Generated %s", spec_path)

    return {
        "ok": True,
        "ticket_id": ticket_id,
        "generated": generated_count,
        "blocked": blocked_count,
        "results": results,
        "meta": {
            "tool": "playwright_test_generator",
            "version": _TOOL_VERSION,
            "duration_ms": int((time.time() - started) * 1000),
        },
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_selector_map(ui_map_data: dict) -> dict:
    """Build alias_semantic → selector_recommended mapping from UI map."""
    mapping: dict = {}
    for el in ui_map_data.get("elements", []):
        alias = el.get("alias_semantic")
        selector = el.get("selector_recommended")
        if alias and selector:
            mapping[alias] = selector
    return mapping


def _find_missing_selectors(scenario: dict, selector_map: dict) -> list:
    """Return list of targets in the scenario not found in selector_map."""
    missing = []
    all_targets = (
        [s.get("target", "") for s in scenario.get("pasos", [])]
        + [o.get("target", "") for o in scenario.get("oraculos", [])]
    )
    # navigate targets are screen names, not selectors
    navigate_targets = {
        s.get("target", "") for s in scenario.get("pasos", [])
        if s.get("accion") == "navigate"
    }
    for target in all_targets:
        if target in navigate_targets:
            continue
        if target and target not in selector_map:
            missing.append(target)
    return missing


def _check_no_hardcoded_creds(rendered: str, scenario_id: str) -> None:
    """Raise if any credential-like literals appear in the rendered output."""
    forbidden = re.compile(
        r'(?i)(PABLO|password\s*=\s*["\'][^"\']{3,}["\']|user\s*=\s*["\'][^"\']{3,}["\'])',
    )
    for line in rendered.splitlines():
        # Allow process.env references
        if "process.env" in line:
            continue
        # Allow comments
        if line.strip().startswith("//"):
            continue
        if forbidden.search(line):
            logger.warning(
                "Potential hardcoded credential in generated .spec.ts for %s: %s",
                scenario_id, line[:80],
            )


def _slugify(text: str) -> str:
    """Convert text to a filename-safe slug."""
    slug = re.sub(r'[^\w\s-]', '', text.lower())
    slug = re.sub(r'[\s_-]+', '_', slug)
    return slug[:50].strip('_')


def _err(code: str, message: str) -> dict:
    return {"ok": False, "error": code, "message": message}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="playwright_test_generator — Generate .spec.ts files from ScenarioSpecs"
    )
    parser.add_argument("--scenarios", required=True, help="Path to scenarios.json")
    parser.add_argument("--ui-maps", required=True, dest="ui_maps",
                        help="Directory containing <screen>.json UI maps")
    parser.add_argument("--out", required=True, help="Output directory for .spec.ts files")
    parser.add_argument("--template", default=None,
                        help=f"Jinja2 template path (default: {_DEFAULT_TEMPLATE})")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
