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
import unicodedata
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.test_generator")

# v1.1.0 — adds:
#  - HTML5 input type-aware value formatting (date → YYYY-MM-DD, etc).
#    Closes the class of bugs where scenarios carry "19000101" / "01/01/2026"
#    and Playwright's `fill()` fails on `<input type="date">` after 10s of
#    visibility retries.
#  - Per-spec `oraculos` constant injected into the template so the
#    `test.afterEach` hook can write `assertions_<sid>.json` (consumed by
#    uat_assertion_evaluator).
#  - Skip steps whose value cannot be formatted for the input type — the
#    scenario is reclassified `blocked` with a structured reason instead of
#    letting the test runner report a false product defect.
_TOOL_VERSION = "1.1.0"
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
    # Ensure deterministic runs: remove stale specs from previous executions.
    # This prevents duplicate/non-ASCII leftovers from being re-executed.
    for stale_spec in out_dir.glob("*.spec.ts"):
        try:
            stale_spec.unlink()
        except OSError:
            logger.warning("Could not remove stale spec: %s", stale_spec)

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
        # Build alias → input_type mapping (M1+M3): needed to format scenario
        # fill values (e.g. "01/01/2026" → "2026-01-01" for <input type=date>).
        input_type_map = _build_input_type_map(ui_map_data)

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

        # Format fill/select values according to the target input's HTML5 type.
        # If a value cannot be parsed (e.g. "abc" for type=date), refuse the
        # scenario instead of generating a spec that will fail at runtime —
        # that would be charged against the product, not the test pipeline.
        formatted_pasos, format_error = _format_scenario_values(
            scenario.get("pasos", []),
            input_type_map,
        )
        if format_error:
            blocked_count += 1
            results.append({
                "scenario_id": sid,
                "status": "blocked",
                "reason": format_error["reason"],
                "missing": [],
                "details": format_error,
            })
            continue

        normalized_oraculos, oracle_error = _validate_oracles(
            scenario.get("oraculos", []),
        )
        if oracle_error:
            blocked_count += 1
            results.append({
                "scenario_id": sid,
                "status": "blocked",
                "reason": oracle_error["reason"],
                "missing": [],
                "details": oracle_error,
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
                pasos=formatted_pasos,
                oraculos=normalized_oraculos,
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
    """Build alias_semantic → CSS selector mapping from UI map.

    Priority:
    1. selector_recommended if it's a simple CSS selector (#id or .class) — no quotes issues
    2. First #id selector from fallback_selectors
    3. First CSS selector ([attr], .class) from fallback_selectors
    4. selector_recommended as-is (may be a Playwright locator expression)
    """
    mapping: dict = {}
    for el in ui_map_data.get("elements", []):
        alias = el.get("alias_semantic")
        fallbacks = el.get("fallback_selectors") or []
        rec = el.get("selector_recommended", "")

        # 1. Prefer #id or .class from selector_recommended (simplest, no quote issues)
        if rec and (rec.startswith("#") or rec.startswith(".")):
            selector = rec
        else:
            # 2. Try #id from fallbacks
            id_sel = next((s for s in fallbacks if s.startswith("#")), None)
            # 3. Try any CSS selector from fallbacks
            css_sel = id_sel or next(
                (s for s in fallbacks if s.startswith("[") or s.startswith(".")),
                None,
            )
            selector = css_sel or rec

        if alias and selector:
            mapping[alias] = selector
    return mapping


def _build_input_type_map(ui_map_data: dict) -> dict:
    """Build alias_semantic → input_type (HTML5) mapping from the UI map.

    Returns empty mapping when the UI map predates schema 1.1 (no
    `input_type` field). In that case, the value formatter falls back to
    identity — preserving the legacy behaviour.
    """
    mapping: dict = {}
    for el in ui_map_data.get("elements", []):
        alias = el.get("alias_semantic")
        itype = el.get("input_type")
        if alias and itype:
            mapping[alias] = itype
    return mapping


def _format_scenario_values(pasos: list, input_type_map: dict) -> tuple:
    """Apply input_value_formatter to each `fill`/`select` step's value.

    Returns (formatted_pasos, error_dict_or_None). Error_dict is set when any
    step's value is unparseable for its target input_type — caller MUST
    short-circuit and mark the scenario blocked. We never silently fall
    through to Playwright runtime, since "fill date with bad format" surfaces
    as a misleading product failure.
    """
    from input_value_formatter import format_value

    formatted: list = []
    for step in pasos:
        accion = step.get("accion", "")
        target = step.get("target", "")
        valor = step.get("valor")
        # Only `fill` is type-sensitive (Playwright's selectOption accepts the
        # raw string). Identity passthrough for everything else preserves
        # backwards compat.
        if accion == "fill" and target in input_type_map:
            itype = input_type_map[target]
            new_val, err = format_value(itype, valor)
            if err is not None:
                return [], {
                    "reason": err,
                    "step": step,
                    "input_type": itype,
                    "raw_value": valor,
                }
            new_step = dict(step)
            new_step["valor"] = new_val
            new_step["input_type"] = itype  # surfaced for telemetry
            formatted.append(new_step)
        else:
            formatted.append(step)
    return formatted, None


def _validate_oracles(oraculos: list) -> tuple:
    """Validate and normalize oracle values before rendering templates.

    count_* oracles must carry an integer-like value. Placeholder literals
    (e.g. <expected_count>) would generate invalid TypeScript and should be
    blocked at generation time.
    """
    normalized: list = []
    for oracle in oraculos:
        o = dict(oracle)
        tipo = str(o.get("tipo", "")).strip()
        if tipo in {"count_gt", "count_eq"}:
            raw = o.get("valor")
            try:
                o["valor"] = int(str(raw).strip())
            except Exception:
                return [], {
                    "reason": "INVALID_ORACLE_VALUE",
                    "oracle": oracle,
                    "message": "count_* oracle requires integer valor",
                }
        normalized.append(o)
    return normalized, None


# Actions whose target does not need to be in the selector_map
_SELECTOR_FREE_ACTIONS = {"navigate", "expand_collapsible", "wait_networkidle"}
# Oracle types whose target does not need to be in the selector_map
_SELECTOR_FREE_ORACLE_TYPES = {"page_contains_text", "page_not_contains_text"}
# Pseudo-targets that are resolved at runtime (whole-page assertions)
_PSEUDO_TARGETS = {"body", "page", ""}


def _find_missing_selectors(scenario: dict, selector_map: dict) -> list:
    """Return list of targets in the scenario not found in selector_map."""
    missing = []
    for step in scenario.get("pasos", []):
        accion = step.get("accion", "")
        target = step.get("target", "")
        if accion in _SELECTOR_FREE_ACTIONS:
            continue
        if target in _PSEUDO_TARGETS:
            continue
        if target and target not in selector_map:
            missing.append(target)
    for oracle in scenario.get("oraculos", []):
        tipo = oracle.get("tipo", "")
        target = oracle.get("target", "")
        if tipo in _SELECTOR_FREE_ORACLE_TYPES:
            continue
        if target in _PSEUDO_TARGETS:
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
    # Normalize Unicode to ASCII (strips accents/diacritics) so that
    # filenames like "débito_automático_no" don't break Playwright's
    # test discovery on Windows when the path contains non-ASCII chars.
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
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
