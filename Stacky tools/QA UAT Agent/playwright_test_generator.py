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
import os
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
_TOOL_VERSION = "1.3.0"
# 1.3.0 = Recording-to-Replay (Fase 8) — playbook-aware generation.
#   Before falling through to UI-map lookup + LLM-generated steps, the
#   generator checks cache/playbooks/ for a playbook whose goal_slug or
#   target_screen matches the scenario's pantalla / goal_action. When found,
#   the spec is rendered directly from the playbook's navigation_steps +
#   action_steps + parameterizable_fields — no BLOCKED for missing selectors.
# 1.2.0 = Fase 8 — discovered_selectors fallback.
_DEFAULT_TEMPLATE = Path(__file__).resolve().parent / "templates" / "playwright_test.spec.ts.j2"
_DISCOVERED_SELECTORS_PATH = Path(__file__).resolve().parent / "cache" / "discovered_selectors.json"
_PLAYBOOKS_DIR = Path(__file__).resolve().parent / "cache" / "playbooks"


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
        detect_screen_errors=args.detect_screen_errors,
        detect_screen_errors_vision=args.detect_screen_errors_vision,
        discovered_selectors_path=(
            None if not args.discovered_selectors or args.discovered_selectors.lower() == "none"
            else Path(args.discovered_selectors)
        ),
        verbose=args.verbose,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("ok") else 1)


def run(
    scenarios_path: Path,
    ui_maps_dir: Path,
    out_dir: Path,
    template_path: Optional[Path] = None,
    detect_screen_errors: bool = False,
    detect_screen_errors_vision: bool = False,
    discovered_selectors_path: Optional[Path] = None,
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

    # Load screen-error detector JS only when the feature is enabled. Keeps
    # the dependency explicit and avoids importing the module in legacy runs.
    screen_error_detector_js = ""
    aspnet_exception_detector_js = ""
    if detect_screen_errors:
        try:
            from screen_error_detector import render_dom_detector_js, render_aspnet_exception_detector_js
            screen_error_detector_js = render_dom_detector_js()
            aspnet_exception_detector_js = render_aspnet_exception_detector_js()
        except Exception as exc:
            logger.warning(
                "Could not render DOM detector JS — falling back to disabled: %s",
                exc,
            )
            detect_screen_errors = False
            detect_screen_errors_vision = False

    out_dir.mkdir(parents=True, exist_ok=True)
    # Ensure deterministic runs: remove stale specs from previous executions.
    # This prevents duplicate/non-ASCII leftovers from being re-executed.
    for stale_spec in out_dir.glob("*.spec.ts"):
        try:
            stale_spec.unlink()
        except OSError:
            logger.warning("Could not remove stale spec: %s", stale_spec)

    ticket_id = scenarios_data.get("ticket_id", 0)

    # Fase 8 — load discovered_selectors cache once for the whole run.
    # Override path is injected by tests; production uses the default.
    _disc_path = discovered_selectors_path or _DISCOVERED_SELECTORS_PATH
    discovered_by_screen = _load_discovered_selectors(_disc_path)

    # Fase 8 — load playbooks index once for the whole run.
    playbook_index = _load_playbooks(_PLAYBOOKS_DIR)

    # Fase 2 — load resolved_values.json if present alongside scenarios.json.
    # Maps TABLA_COLUMNA keys to resolved DB values for injection as RESOLVED.* constants.
    _resolved_values = _load_resolved_values(scenarios_path.parent)

    results = []
    generated_count = 0
    blocked_count = 0

    # Fetch guardrails from env — these are evaluated ONCE per generator run.
    _require_playbook    = os.environ.get("QA_UAT_REQUIRE_PLAYBOOK", "true").lower() in ("1", "true", "yes")
    _allow_llm_nav       = os.environ.get("QA_UAT_ALLOW_LLM_NAVIGATION", "false").lower() in ("1", "true", "yes")
    _allow_ui_discovery  = os.environ.get("QA_UAT_ALLOW_UI_DISCOVERY", "false").lower() in ("1", "true", "yes")

    for scenario in scenarios_data["scenarios"]:
        sid = scenario.get("scenario_id", "UNK")
        pantalla = scenario.get("pantalla") or ""

        # RULE: pantalla must be explicitly declared — no FrmAgenda.aspx fallback.
        if not pantalla:
            blocked_count += 1
            results.append({
                "scenario_id": sid,
                "status": "blocked",
                "reason": "UNKNOWN_TARGET_SCREEN",
                "message": (
                    "No se pudo determinar la pantalla objetivo. "
                    "Definí playbook_id o target_screen en el escenario."
                ),
                "missing": [],
            })
            continue

        # Fase 3 — Playbook check BEFORE UI map load.
        # A playbook provides its own selectors; the UI map is only needed as fallback.
        # This prevents false UI_MAP_NOT_FOUND blocks when a valid playbook exists.
        playbook = _match_playbook(scenario, playbook_index)

        # RULE: When QA_UAT_REQUIRE_PLAYBOOK=true and no playbook is found,
        # block immediately. Do not fall through to UI-map / LLM navigation.
        if _require_playbook and not playbook:
            blocked_count += 1
            results.append({
                "scenario_id": sid,
                "status": "blocked",
                "reason": "MISSING_PLAYBOOK",
                "message": (
                    f"No existe playbook determinístico para el escenario '{sid}' "
                    f"(pantalla={pantalla}). "
                    "Grabá el camino humano y guardalo en cache/playbooks/ antes de reintentar."
                ),
                "missing": [],
            })
            continue

        if playbook:
            logger.debug(
                "playwright_test_generator: using playbook %r for scenario %s",
                playbook.get("goal_slug"), sid,
            )
            pb_result = _render_from_playbook(playbook, scenario, out_dir, template_path, template)
            results.append(pb_result)
            if pb_result.get("status") == "generated":
                generated_count += 1
            else:
                blocked_count += 1
            continue

        # No playbook — fall through to UI map validation.
        # Load UI map for this screen.
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

        # Augment selector_map with discovered_selectors for this screen before
        # missing-selector check. Keeps track of which aliases were resolved from
        # the cache so the result can flag them.
        discovered_aliases = _merge_discovered_selectors(
            selector_map, discovered_by_screen, pantalla
        )

        # Validate all targets exist in UI map (or discovered cache)
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
                detect_screen_errors=detect_screen_errors,
                detect_screen_errors_vision=detect_screen_errors_vision,
                screen_error_detector_js=screen_error_detector_js,
                aspnet_exception_detector_js=aspnet_exception_detector_js,
                # Fase 2: resolved values from precondition_parser pipeline
                resolved_values=_resolved_values.get(sid, _resolved_values),
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
            "discovered_selectors_used": discovered_aliases,
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
            "discovered_selectors_file": str(_disc_path) if _disc_path.is_file() else None,
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


def _load_discovered_selectors(path: Path) -> dict[str, dict[str, str]]:
    """Load cache/discovered_selectors.json and return by_screen index.

    Returns {} when the file doesn't exist or is malformed — caller treats
    this as "no cache available" and proceeds with the static UI map only.

    Schema expected:
        { "by_screen": { "Screen.aspx": { "alias": "css_selector", ... } } }
    """
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("by_screen") or {}
    except Exception as exc:
        logger.warning("playwright_test_generator: cannot load discovered_selectors %s: %s", path, exc)
        return {}


# ── Fase 2: resolved_values loader ───────────────────────────────────────────

def _load_resolved_values(evidence_dir: Path) -> dict:
    """
    Busca resolved_values.json en el directorio de evidencia del ticket.
    Puede estar en:
      - evidence_dir/resolved_values.json       (nivel ticket, para todos los escenarios)
      - evidence_dir/<scenario_id>/resolved_values.json  (por escenario)

    Retorna un dict con dos niveles:
      {
        "_global": {"TABLA_COLUMNA": "value", ...},           # nivel ticket
        "<scenario_id>": {"TABLA_COLUMNA": "value", ...},     # por escenario (override global)
      }

    Cuando se pasa a template.render(), se usa _resolved_values.get(sid, _resolved_values)
    para que el template reciba el dict aplanado correcto para cada escenario.
    """
    merged: dict = {}

    # Nivel global (al lado de scenarios.json)
    global_path = evidence_dir / "resolved_values.json"
    if global_path.is_file():
        try:
            data = json.loads(global_path.read_text(encoding="utf-8"))
            # resolved_values.json puede tener formato:
            #   {"scenario_id": "...", "values": {"TABLA_COLUMNA": "v"}}
            # o flat: {"TABLA_COLUMNA": "v"}
            if "values" in data:
                merged["_global"] = data["values"]
            else:
                merged["_global"] = {k: v for k, v in data.items() if not k.startswith("_")}
        except Exception as exc:
            logger.debug("playwright_test_generator: cannot parse %s: %s", global_path, exc)

    # Nivel por escenario (subdirectorio)
    for child in evidence_dir.iterdir() if evidence_dir.is_dir() else []:
        if not child.is_dir():
            continue
        rv_path = child / "resolved_values.json"
        if not rv_path.is_file():
            continue
        try:
            data = json.loads(rv_path.read_text(encoding="utf-8"))
            sid = child.name
            if "values" in data:
                merged[sid] = {**merged.get("_global", {}), **data["values"]}
            else:
                merged[sid] = {**merged.get("_global", {}), **{k: v for k, v in data.items() if not k.startswith("_")}}
        except Exception as exc:
            logger.debug("playwright_test_generator: cannot parse %s: %s", rv_path, exc)

    return merged


# ── Fase 8: Playbook-aware generation ────────────────────────────────────────

def _load_playbooks(playbooks_dir: Path) -> dict[str, dict]:
    """Load all playbooks from cache/playbooks/ keyed by goal_slug.

    Also builds a secondary index: target_screen → [playbook, ...]
    Returns a dict with keys "by_slug" and "by_screen".
    """
    index: dict = {"by_slug": {}, "by_screen": {}}
    if not playbooks_dir.is_dir():
        return index
    for pb_file in sorted(playbooks_dir.glob("*.json")):
        try:
            # Use utf-8-sig to handle BOM written by tools like PowerShell
            pb = json.loads(pb_file.read_text(encoding="utf-8-sig"))
            slug = pb.get("goal_slug", pb_file.stem)
            index["by_slug"][slug] = pb
            screen = pb.get("target_screen", "")
            if screen:
                index["by_screen"].setdefault(screen, []).append(pb)
        except Exception as exc:
            logger.debug("playwright_test_generator: skipping playbook %s: %s", pb_file, exc)
    return index


def _match_playbook(scenario: dict, playbook_index: dict) -> Optional[dict]:
    """Find the best playbook for a scenario.

    Matching order (highest priority first):
    1. scenario.goal_action matches playbook.goal_slug exactly
    2. scenario.pantalla matches playbook.target_screen (first playbook wins)
    3. Keywords from scenario.titulo match playbook.goal_slug

    Returns None if no match found.
    """
    goal_action = (scenario.get("goal_action") or "").strip().lower()
    pantalla = (scenario.get("pantalla") or "").strip()
    titulo = (scenario.get("titulo") or "").strip().lower()

    by_slug = playbook_index.get("by_slug", {})
    by_screen = playbook_index.get("by_screen", {})

    # 1. Direct goal_action match
    if goal_action and goal_action in by_slug:
        return by_slug[goal_action]

    # 2. Screen match
    if pantalla and pantalla in by_screen:
        return by_screen[pantalla][0]

    # 3. Keyword match against slug
    if titulo:
        titulo_words = set(re.sub(r'[^a-z0-9\s]', '', titulo).split())
        best_pb = None
        best_score = 0
        for slug, pb in by_slug.items():
            slug_words = set(slug.replace('_', ' ').split())
            score = len(titulo_words & slug_words)
            if score > best_score:
                best_score = score
                best_pb = pb
        if best_score >= 2:
            return best_pb

    return None


def _render_from_playbook(
    playbook: dict,
    scenario: dict,
    out_dir: Path,
    template_path: Path,
    template,  # Jinja2 Template object
) -> dict:
    """Generate a .spec.ts from a playbook, bypassing UI-map lookup.

    Resolves parameterizable_fields from scenario.datos (provided by the
    intent_parser / scenario compiler). Fields with source=infer_unique get
    auto-generated values; source=infer_numeric use the playbook default.

    Returns a result dict (same schema as the normal generation path).
    """
    sid = scenario.get("scenario_id", "UNK")
    pantalla = playbook.get("target_screen") or scenario.get("pantalla") or ""
    if not pantalla:
        return {
            "scenario_id": sid,
            "status": "blocked",
            "reason": "UNKNOWN_TARGET_SCREEN",
            "message": (
                "El playbook no declara target_screen y el escenario no declara pantalla. "
                "Definí target_screen en el playbook antes de reintentar."
            ),
            "missing": [],
        }

    # Resolve parameter values from scenario.datos
    raw_datos = scenario.get("datos", "") or ""
    data_map = _parse_datos(raw_datos)

    resolved_fields: dict[str, str] = {}
    for param_key, meta in playbook.get("parameterizable_fields", {}).items():
        source = meta.get("source", "provided")
        default_val = meta.get("default", "")

        if source == "provided":
            # Try to find the value in scenario.datos
            val = data_map.get(param_key, "")
            if not val:
                # Try case-insensitive search
                val = next((v for k, v in data_map.items() if k.upper() == param_key.upper()), "")
            resolved_fields[param_key] = val or default_val or f"QA_{param_key}"
        elif source == "infer_unique":
            import uuid as _uuid
            resolved_fields[param_key] = f"QA_{_uuid.uuid4().hex[:8].upper()}"
        elif source == "infer_numeric":
            resolved_fields[param_key] = default_val or "100"
        elif source == "bd_query":
            # BD not available at generation time — use default and note it
            resolved_fields[param_key] = default_val or f"BD_{param_key}"
        else:
            resolved_fields[param_key] = data_map.get(param_key, default_val or "")

    # Build spec pasos from playbook action_steps + navigation_steps
    nav_steps = playbook.get("navigation_steps", [])
    action_steps = playbook.get("action_steps", [])
    all_steps = nav_steps + action_steps

    # Convert playbook steps to ScenarioSpec-style pasos for template
    pasos_for_template = _playbook_steps_to_pasos(all_steps, resolved_fields)

    # Fase 3 — Validate: no action-requiring steps with empty selectors.
    # An empty selector in a playbook step means the playbook was recorded
    # incompletely. Block before emitting TypeScript — an empty selector would
    # cause a Playwright "strict mode violation" that looks like a product defect.
    _ACTIONS_NEEDING_SELECTOR = {
        "click", "fill", "wait_visible", "check", "check_checkbox",
        "double_click", "hover", "select",
    }
    empty_selector_steps = [
        paso for paso in pasos_for_template
        if paso.get("accion") in _ACTIONS_NEEDING_SELECTOR
        and not (paso.get("target") or "").strip()
    ]
    if empty_selector_steps:
        return {
            "scenario_id": sid,
            "status": "blocked",
            "reason": "MISSING_PLAYBOOK_SELECTOR",
            "message": (
                f"Playbook {playbook.get('goal_slug')!r} tiene {len(empty_selector_steps)} paso(s) "
                "sin selector CSS. Completá el playbook en cache/playbooks/ antes de reintentar."
            ),
            "missing": [
                f"step[accion={p.get('accion')}].selector"
                for p in empty_selector_steps
            ],
        }

    # Build a synthetic ui_map so the template's {{ ui_map[step.target] }}
    # resolves correctly.  We replace each raw CSS selector with a stable
    # alias ("pb_step_N") and map that alias to the safe selector (inner
    # double-quotes converted to single-quotes so the selector can be placed
    # inside a TypeScript double-quoted string without escaping).
    synthetic_ui_map: dict[str, str] = {}
    aliased_pasos: list[dict] = []
    for i, paso in enumerate(pasos_for_template):
        accion = paso.get("accion", "")
        selector = paso.get("target", "")
        if accion in ("click", "fill", "wait_visible", "check", "check_checkbox", "double_click", "hover", "select") and selector:
            alias = f"pb_step_{i}"
            safe_sel = selector.replace('"', "'")  # a:has-text("X") → a:has-text('X')
            synthetic_ui_map[alias] = safe_sel
            aliased_pasos.append({**paso, "target": alias})
        else:
            aliased_pasos.append(paso)

    sid_slug = _slugify(scenario.get("titulo", sid))
    filename = f"{sid}_{sid_slug}.spec.ts"
    spec_path = out_dir / filename

    # Oracles: keep only those whose target resolves in synthetic_ui_map,
    # OR those that don't need a selector (page_contains_text / page_not_contains_text).
    _selector_free_types = ("page_contains_text", "page_not_contains_text")
    filtered_oraculos = [
        o for o in (scenario.get("oraculos") or [])
        if o.get("tipo") in _selector_free_types or o.get("target") in synthetic_ui_map
    ]

    try:
        rendered = template.render(
            ticket_id=scenario.get("ticket_id", -1),
            scenario_id=sid,
            titulo=scenario.get("titulo", playbook.get("goal_label", "")),
            pantalla=pantalla,
            precondiciones=scenario.get("precondiciones", []),
            pasos=aliased_pasos,
            oraculos=filtered_oraculos,
            datos_requeridos=scenario.get("datos_requeridos", []),
            ui_map=synthetic_ui_map,
            detect_screen_errors=False,
            detect_screen_errors_vision=False,
            screen_error_detector_js="",
            aspnet_exception_detector_js="",
        )
    except Exception as exc:
        return {
            "scenario_id": sid,
            "status": "blocked",
            "reason": "PLAYBOOK_RENDER_FAILED",
            "missing": [],
            "details": str(exc),
        }

    _check_no_hardcoded_creds(rendered, sid)
    spec_path.write_text(rendered, encoding="utf-8")

    return {
        "scenario_id": sid,
        "status": "generated",
        "path": str(spec_path),
        "playbook_used": playbook.get("goal_slug"),
        "resolved_fields": list(resolved_fields.keys()),
        "used_selectors": [],
        "unresolved_selectors": [],
        "discovered_selectors_used": [],
    }


def _parse_datos(datos_str: str) -> dict[str, str]:
    """Parse 'KEY=value, KEY2=value2' datos string into a dict."""
    result: dict[str, str] = {}
    if not datos_str:
        return result
    for part in re.split(r'[,;]\s*', datos_str):
        if '=' in part:
            k, _, v = part.partition('=')
            result[k.strip()] = v.strip()
    return result


def _playbook_steps_to_pasos(steps: list[dict], resolved_fields: dict[str, str]) -> list[dict]:
    """Convert playbook action_steps to template-compatible pasos dicts."""
    pasos = []
    for step in steps:
        action = step.get("action", "")
        selector = step.get("selector", "")
        if not action:
            continue
        if action == "goto":
            pasos.append({"accion": "navigate", "target": step.get("screen", ""), "valor": ""})
        elif action == "click":
            pasos.append({"accion": "click", "target": selector, "valor": ""})
        elif action == "fill":
            field_key = step.get("field", "")
            val = resolved_fields.get(field_key, step.get("valor", ""))
            pasos.append({"accion": "fill", "target": selector, "valor": val})
        elif action == "check":
            pasos.append({"accion": "check_checkbox", "target": selector, "valor": "true"})
        elif action == "uncheck":
            pasos.append({"accion": "check_checkbox", "target": selector, "valor": "false"})
        elif action == "waitFor":
            timeout_ms = step.get("timeout_ms", 10000)
            pasos.append({"accion": "wait_visible", "target": selector, "valor": "", "timeout_ms": timeout_ms})
        elif action == "select":
            field_key = step.get("field", "")
            val = resolved_fields.get(field_key, step.get("valor", ""))
            pasos.append({"accion": "select", "target": selector, "valor": val})
        elif action == "wait":
            pasos.append({"accion": "wait_networkidle", "target": "", "valor": ""})
        # skip _note-only steps
    return pasos


def _merge_discovered_selectors(
    selector_map: dict,
    discovered_by_screen: dict[str, dict[str, str]],
    screen: str,
) -> list[str]:
    """Add selectors from the discovered cache into selector_map (in-place).

    Merge policy: discovered entries do NOT overwrite existing UI-map entries
    (the curated UI map is always more reliable). Only MISSING aliases get
    filled in.

    Returns the list of alias names that were actually added from the cache
    so the caller can surface them in the result for operator awareness.
    """
    screen_selectors = discovered_by_screen.get(screen) or {}
    added: list[str] = []
    for alias, selector in screen_selectors.items():
        if alias and selector and alias not in selector_map:
            selector_map[alias] = selector
            added.append(alias)
    if added:
        logger.info(
            "playwright_test_generator: resolved %d selector(s) from discovered cache for %s: %s",
            len(added), screen, added,
        )
    return added


# ── Sprint 5.5: Grid precheck injection ───────────────────────────────────────

def generate_grid_precheck_typescript(
    scenario_id: str,
    ticket_id: int,
    screen: str,
    grid_alias: str,
    grid_selector: str,
    timeout_ms: Optional[int] = None,
    out_path: Optional[str] = None,
) -> str:
    """
    Sprint 5.5 — Generate a TypeScript snippet that performs a grid precheck
    before the spec attempts to interact with a grid element.

    The generated code:
    1. Checks grid selector visibility within timeout_ms.
    2. If invisible → writes nav_precheck_result.json with BLOCKED/NAV/SELECTOR_NOT_FOUND.
    3. If visible but row_count==0 → writes BLOCKED/DATA/GRID_EMPTY.
    4. If visible and rows exist → writes PASS and continues.

    The file nav_precheck_result.json is read by _collect_nav_precheck_events()
    in uat_test_runner.py after all specs finish.

    Parameters
    ----------
    scenario_id : str
        Scenario ID (e.g. "P01" or "RF-008-CA-01").
    ticket_id : int
        ADO work item ID.
    screen : str
        Screen filename (e.g. "FrmDetalleClie.aspx").
    grid_alias : str
        UI map alias for the grid element (e.g. "GridObligaciones").
    grid_selector : str
        CSS selector for the grid (e.g. "#GridObligaciones").
    timeout_ms : int | None
        Timeout for grid visibility check. Reads QA_UAT_GRID_TIMEOUT_MS at runtime if None.
    out_path : str | None
        Override output path for nav_precheck_result.json (for testing).

    Returns
    -------
    str
        TypeScript code snippet to inject at the start of the test body.
    """
    _default_timeout = timeout_ms if timeout_ms is not None else 5000
    _out_path = out_path or f"evidence/{ticket_id}/{scenario_id}/nav_precheck_result.json"
    _safe_selector = grid_selector.replace("'", "\\'")
    _safe_alias = grid_alias.replace("'", "\\'")
    _safe_screen = screen.replace("'", "\\'")
    _safe_sid = scenario_id.replace("'", "\\'")

    snippet = f"""
  // ── Sprint 5.5: Grid precheck — generated by playwright_test_generator.py ──
  // Checks that {grid_alias} is visible and has at least 1 row before proceeding.
  // Result written to {_out_path} for uat_test_runner.py to pick up.
  {{
    const _gridTimeout = Number(process.env.QA_UAT_GRID_TIMEOUT_MS ?? {_default_timeout});
    const _gridSelector = '{_safe_selector}';
    const _precheck = {{
      scenario_id: '{_safe_sid}',
      ticket_id: {ticket_id},
      screen: '{_safe_screen}',
      target_alias: '{_safe_alias}',
      selector: _gridSelector,
      timeout_ms: _gridTimeout,
      visible: false,
      row_count: 0,
      decision: 'BLOCKED',
      category: null as string | null,
      reason: null as string | null,
    }};
    try {{
      const _gridLocator = page.locator(_gridSelector);
      const _gridVisible = await _gridLocator.isVisible({{ timeout: _gridTimeout }}).catch(() => false);
      _precheck.visible = _gridVisible;
      if (!_gridVisible) {{
        _precheck.decision = 'BLOCKED';
        _precheck.category = 'NAV';
        _precheck.reason = 'SELECTOR_NOT_FOUND';
      }} else {{
        const _rows = await _gridLocator.locator('tr').count().catch(() => 0);
        _precheck.row_count = _rows;
        if (_rows === 0) {{
          _precheck.decision = 'BLOCKED';
          _precheck.category = 'DATA';
          _precheck.reason = 'GRID_EMPTY';
        }} else {{
          _precheck.decision = 'PASS';
          _precheck.category = null;
          _precheck.reason = null;
        }}
      }}
    }} catch (_precheckErr: any) {{
      _precheck.decision = 'BLOCKED';
      _precheck.category = 'NAV';
      _precheck.reason = 'SELECTOR_NOT_FOUND';
    }}
    // Write precheck result for uat_test_runner.py
    const _precheckDir = path.dirname('{_out_path}');
    if (!fs.existsSync(_precheckDir)) {{ fs.mkdirSync(_precheckDir, {{ recursive: true }}); }}
    fs.writeFileSync('{_out_path}', JSON.stringify(_precheck, null, 2), 'utf-8');
    if (_precheck.decision === 'BLOCKED') {{
      test.skip(true, `nav_precheck: ${{_precheck.reason}} for ${{_gridSelector}}`);
    }}
  }}
  // ── End grid precheck ────────────────────────────────────────────────────────
"""
    return snippet


def detect_grid_in_scenario(scenario: dict, ui_map: dict) -> Optional[dict]:
    """
    Sprint 5.5 — Detect if a scenario has a grid element that needs a precheck.

    Returns dict with grid_alias and grid_selector if found, else None.
    Looks at:
    1. scenario.grids[] field (explicit grid declarations)
    2. pasos with accion="wait_grid" or target matching "Grid*"
    3. ui_map aliases whose names contain "Grid" or "grid"
    """
    # 1. Explicit grids field
    grids = scenario.get("grids") or []
    if grids:
        first = grids[0] if isinstance(grids[0], dict) else {"alias": str(grids[0])}
        alias = first.get("alias") or first.get("name") or str(grids[0])
        selector = first.get("selector") or ui_map.get(alias) or f"#{alias}"
        return {"alias": alias, "selector": selector}

    # 2. Pasos with grid actions
    for paso in (scenario.get("pasos") or []):
        target = paso.get("target", "")
        accion = paso.get("accion", "")
        if accion in ("wait_grid", "check_grid"):
            selector = ui_map.get(target) or f"#{target}"
            return {"alias": target, "selector": selector}
        if target and "grid" in target.lower():
            selector = ui_map.get(target) or f"#{target}"
            return {"alias": target, "selector": selector}

    # 3. UI map aliases containing "Grid"
    for alias, selector in ui_map.items():
        if "grid" in alias.lower() or "Grid" in alias:
            return {"alias": alias, "selector": selector}

    return None


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
    parser.add_argument(
        "--detect-screen-errors", action="store_true",
        dest="detect_screen_errors",
        help="Inject in-flight DOM error detection after each interactive "
             "step. The generated spec.ts will fail the step when a known "
             "validation/error pattern appears on screen.",
    )
    parser.add_argument(
        "--detect-screen-errors-vision", action="store_true",
        dest="detect_screen_errors_vision",
        help="Additionally call a vision-LLM detector via "
             "QA_UAT_VISION_DETECTOR_URL after each step. Implies "
             "--detect-screen-errors.",
    )
    parser.add_argument(
        "--discovered-selectors", default=None, dest="discovered_selectors",
        help="Path to cache/discovered_selectors.json. Defaults to the cache/ "
             "directory next to this script. Pass 'none' to disable the lookup.",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    # vision implies the base flag
    if args.detect_screen_errors_vision:
        args.detect_screen_errors = True
    return args


if __name__ == "__main__":
    main()
