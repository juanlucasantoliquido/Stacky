"""
uat_scenario_compiler.py — Compile P0N items into ScenarioSpec list.

SPEC: SPEC/uat_scenario_compiler.md
CLI:
    python uat_scenario_compiler.py [--input <path>] [--ticket <id>] [--scope screen=<name>] [--verbose]
    python uat_ticket_reader.py --ticket 70 | python uat_scenario_compiler.py

Output: JSON to stdout following scenario_spec.schema.json
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.scenario_compiler")

# v1.2.0 — Fase 1 Agenda-expert refactor. The hardcoded `_SUPPORTED_SCREENS`
# frozenset and the hardcoded filter-keyword list inside
# `_postprocess_compiled_spec` were duplicated across multiple modules;
# both now read from `agenda_screens` + `agenda_glossary` so adding a new
# screen / domain term is a one-file change. Behaviour preserved.
#
# v1.1.0 — accepts the enriched UI map (kind, input_type, is_decorative,
# class_list, accessible_name) and forwards a structured hint catalog to the
# LLM so it stops choosing decorative layout labels (input-field-label) as
# runtime-message oracles. Adds a post-LLM validator that reroutes scenarios
# whose oracles target decorative elements to out_of_scope.
_TOOL_VERSION = "1.2.0"

# Screens supported in MVP — single source of truth in `agenda_screens.py`.
# Re-exported under the legacy `_SUPPORTED_SCREENS` name so existing
# in-module references and any downstream consumer that imported it keep
# working without modification.
from agenda_screens import SUPPORTED_SCREENS as _SUPPORTED_SCREENS

# Domain glossary lookup — used both to enrich the LLM system prompt and to
# drive the heuristic filter-scenario detector in `_postprocess_compiled_spec`.
import agenda_glossary

# Actions supported in ScenarioSpec
_SUPPORTED_ACTIONS = frozenset({
    "navigate", "click", "fill", "select", "wait_networkidle", "wait_visible"
})

# Placeholder patterns that indicate incomplete scenario
_PLACEHOLDER_RE = re.compile(
    r'\[completar\]|\.{3}|\bTBD\b|\[TODO\]|\bPENDIENTE\b', re.IGNORECASE
)

# Action keyword maps for heuristic extraction
_ACTION_KEYWORDS = {
    "click": ["hacer click", "click", "presionar", "pulsar", "seleccionar botón"],
    "fill": ["ingresar", "escribir", "completar", "llenar", "tipear"],
    "select": ["seleccionar", "elegir", "cambiar", "escoger"],
    "navigate": ["navegar", "ir a", "abrir", "acceder"],
}
_ORACLE_KEYWORDS = {
    "visible": ["debe aparecer", "se muestra", "visible", "debe estar visible"],
    "invisible": ["no debe aparecer", "no se muestra", "no visible", "oculto"],
    "equals": ["debe ser exactamente", "igual a", "debe mostrar"],
    "contains_literal": ["debe contener", "contiene", "incluye"],
    "count_gt": ["más de", "al menos", "mayor que", "mayor a"],
    "count_eq": ["exactamente", "igual a"],
}

# Performance/load test keywords → out of scope
_OUT_OF_SCOPE_KEYWORDS = re.compile(
    r'\bperformance\b|\bcarga\b|\bvelocidad\b|\brespuesta\s*en\s*menos\b|\bms\b|\bsegundos\b',
    re.IGNORECASE,
)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr,
                            format="%(levelname)s %(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    # Read input
    if args.input:
        try:
            ticket_json = json.loads(Path(args.input).read_text(encoding="utf-8"))
        except Exception as exc:
            _exit_err("invalid_input_json", f"Cannot read {args.input}: {exc}")
            return
    elif args.ticket:
        evidence_path = Path(__file__).resolve().parent / "evidence" / str(args.ticket) / "ticket.json"
        if not evidence_path.is_file():
            _exit_err("invalid_input_json", f"No ticket.json at {evidence_path}. Run uat_ticket_reader first.")
            return
        ticket_json = json.loads(evidence_path.read_text(encoding="utf-8"))
    else:
        # Read from stdin
        try:
            ticket_json = json.loads(sys.stdin.read())
        except json.JSONDecodeError as exc:
            _exit_err("invalid_input_json", f"stdin is not valid JSON: {exc}")
            return

    scope_screen = None
    if args.scope and args.scope.startswith("screen="):
        scope_screen = args.scope.split("=", 1)[1].strip()

    result = run(ticket_json=ticket_json, scope_screen=scope_screen, verbose=args.verbose)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("ok") else 1)


def run(
    ticket_json: dict,
    scope_screen: Optional[str] = None,
    ui_aliases: Optional[list] = None,
    ui_elements: Optional[list] = None,
    verbose: bool = False,
) -> dict:
    """Core logic — callable from tests without subprocess.

    `ui_elements`: optional list of element dicts from the UI map (schema 1.1+):
    [{"alias_semantic", "kind", "role", "input_type", "is_decorative",
      "label", "class_list"}, ...]. When provided, the compiler hands this
    structured catalog to the LLM and runs a post-validation pass that
    reroutes scenarios whose oracles target decorative elements
    (input-field-label, page-title, etc) to `out_of_scope_items` with
    `razon=ORACLE_TARGETS_DECORATIVE_LAYOUT`. Without it, falls back to
    pre-1.1 behaviour (alias-only hints, no decorative validation).
    """
    started = time.time()

    if not isinstance(ticket_json, dict) or not ticket_json.get("ok"):
        return _err("invalid_input_json", "Input must be a valid uat_ticket.json with ok=true")

    plan_pruebas = ticket_json.get("plan_pruebas") or []
    if not plan_pruebas:
        return _err("no_test_plan_in_ticket", "plan_pruebas is empty")

    ticket_id = (ticket_json.get("ticket") or {}).get("id", 0)

    scenarios = []
    out_of_scope = []

    for item in plan_pruebas:
        if not isinstance(item, dict):
            continue
        pid = item.get("id", "")
        desc = item.get("descripcion", "")
        datos = item.get("datos", "")
        esperado = item.get("esperado", "")

        # Check out of scope (performance/load)
        if _OUT_OF_SCOPE_KEYWORDS.search(desc + " " + esperado):
            out_of_scope.append({
                "id": pid,
                "razon": "OUT_OF_SCOPE_NEEDS_HUMAN",
                "descripcion": desc,
            })
            continue

        # Check for placeholders
        if _PLACEHOLDER_RE.search(desc + " " + (datos or "") + " " + (esperado or "")):
            out_of_scope.append({
                "id": pid,
                "razon": "PLACEHOLDER_DETECTED",
                "descripcion": desc,
            })
            continue

        # Try to compile the scenario
        spec = _compile_scenario(
            pid, desc, datos, esperado, ticket_id,
            ui_aliases=ui_aliases, ui_elements=ui_elements, verbose=verbose,
        )
        if spec is None:
            out_of_scope.append({
                "id": pid,
                "razon": "INCOMPLETE_SCENARIO",
                "descripcion": desc,
            })
            continue

        spec = _postprocess_compiled_spec(spec, desc, esperado)

        # Guard against placeholders leaking from LLM output (e.g.
        # "<expected_count>") which later produce invalid TypeScript tests.
        serialized_spec = json.dumps(spec, ensure_ascii=False)
        if _PLACEHOLDER_RE.search(serialized_spec) or re.search(r'<[^>]+>', serialized_spec):
            out_of_scope.append({
                "id": pid,
                "razon": "PLACEHOLDER_DETECTED",
                "descripcion": desc,
            })
            continue

        # Filter by scope
        if scope_screen and spec["pantalla"] != scope_screen:
            continue

        # Validate screen is supported
        if spec["pantalla"] not in _SUPPORTED_SCREENS:
            out_of_scope.append({
                "id": pid,
                "razon": "SCREEN_NOT_SUPPORTED",
                "descripcion": desc,
            })
            continue

        # Decorative-target validation (M2): reject scenarios whose oracles
        # point at layout labels. Without this guard the LLM frequently
        # picks `panel_*_label` divs as targets for `visible/invisible`
        # which is a class of false-FAIL.
        if ui_elements:
            decorative_violation = _find_decorative_oracle_targets(spec, ui_elements)
            if decorative_violation:
                out_of_scope.append({
                    "id": pid,
                    "razon": "ORACLE_TARGETS_DECORATIVE_LAYOUT",
                    "descripcion": desc,
                    "details": decorative_violation,
                })
                continue

        scenarios.append(spec)

    if not scenarios and not out_of_scope:
        return _err("all_scenarios_out_of_scope", "All P0N items were discarded")

    # Persist to evidence dir
    if ticket_id:
        _persist(ticket_id, scenarios, out_of_scope)

    return {
        "ok": True,
        "ticket_id": ticket_id,
        "compiled": len(scenarios),
        "out_of_scope": len(out_of_scope),
        "scenarios": scenarios,
        "out_of_scope_items": out_of_scope,
        "meta": {
            "tool": "uat_scenario_compiler",
            "version": _TOOL_VERSION,
            "duration_ms": int((time.time() - started) * 1000),
        },
    }


# ── Scenario compilation ───────────────────────────────────────────────────────

def _compile_scenario(
    pid: str, desc: str, datos: str, esperado: str,
    ticket_id: int, ui_aliases: Optional[list] = None,
    ui_elements: Optional[list] = None, verbose: bool = False,
) -> Optional[dict]:
    """
    Compile a single P0N item into a ScenarioSpec.
    Tries LLM first, falls back to heuristics.
    """
    # Try LLM compilation
    spec = _compile_via_llm(
        pid, desc, datos, esperado, ticket_id,
        ui_aliases=ui_aliases, ui_elements=ui_elements, verbose=verbose,
    )
    if spec:
        return spec

    # Fallback: heuristic extraction
    return _compile_via_heuristic(pid, desc, datos, esperado, ticket_id)


def _compile_via_llm(
    pid: str, desc: str, datos: str, esperado: str,
    ticket_id: int, ui_aliases: Optional[list] = None,
    ui_elements: Optional[list] = None, verbose: bool = False,
) -> Optional[dict]:
    """Attempt to compile via LLM. Return None on failure."""
    try:
        from llm_client import call_llm, LLMError

        # Build alias hint catalog. With ui_elements (UI map ≥1.1) we ship
        # structured per-alias metadata so the LLM picks oracles that match
        # the kind/role of each target. Without it, fall back to the legacy
        # alias-only list.
        if ui_elements:
            alias_instruction = _build_ui_elements_hint(ui_elements)
        elif ui_aliases:
            alias_list = ", ".join(sorted(ui_aliases))
            alias_instruction = (
                f"\nIMPORTANT: You MUST use ONLY these exact alias names from the UI map (do not invent new ones):\n"
                f"{alias_list}\n"
                "If the test step requires an element not in this list, use the closest available alias "
                "or omit the step and mark it in precondiciones as 'SELECTOR_NOT_FOUND'."
            )
        else:
            alias_instruction = (
                "\nUse semantic alias names like: btn_buscar, select_empresa, grid_agenda_aut, "
                "msg_lista_vacia, input_fecha_desde."
            )

        # Inject Agenda domain glossary so the LLM understands business terms
        # (lote, póliza, RUC, débito automático…) without relying on training
        # priors. Falls back to "" when no glossary is loaded — caller is
        # robust to an empty block.
        try:
            glossary_block = agenda_glossary.domain_terms_for_prompt(
                # We don't know the screen yet at this layer (the LLM picks
                # `pantalla` itself), so emit the full catalogue.
                screen=None,
            )
        except Exception as exc:  # noqa: BLE001 — never block compile on prompt build
            logger.debug("Glossary prompt build failed, continuing without: %s", exc)
            glossary_block = ""

        system_prompt = f"""You are a QA automation engineer converting test plan items to structured test specs.
Given a test case description, extract a structured ScenarioSpec JSON.
Respond ONLY with valid JSON, no explanations.

The JSON must have:
- "pantalla": one of ["FrmAgenda.aspx","FrmDetalleLote.aspx","FrmGestion.aspx","Login.aspx"]
- "precondiciones": list of strings
- "pasos": list of {{"accion": "<navigate|click|fill|select|wait_networkidle|wait_visible>", "target": "<alias>", "valor": <str|null>}}
- "oraculos": list of {{"tipo": "<equals|contains_literal|count_gt|count_eq|visible|invisible|state|page_contains_text|page_not_contains_text|select_value_is>", "target": "<alias>", "valor": <str|null>}}
- "datos_requeridos": list of {{"tabla": "<str>", "filtro": "<str>"}}

Oracle selection rules (HARD CONSTRAINTS — violating them will cause the scenario to be rejected):
- For checking the value selected in a <select>, use tipo='select_value_is' with target=<select_alias> and valor='<expected option text/value>'. NEVER use tipo='visible' on a select to mean 'value=Todos'.
- For asserting a runtime message text appears or disappears, prefer tipo='page_contains_text' / 'page_not_contains_text' with valor=<exact message>. Use 'visible'/'invisible' on a specific alias ONLY when you have a stable, NON-decorative element id for that message (e.g. msg_lista_vacia, msg_validacion).
- NEVER target an element marked is_decorative=true (a layout label, page title, section heading) for visible/invisible/equals/contains_literal — these elements are permanent layout text, not runtime messages, and will trivially pass or trivially fail regardless of product state.
- For grid/result-count oracles use count_gt or count_eq with the grid alias; do NOT use visible on the grid for "should have results".

{alias_instruction}
pasos must have at least 1 item. oraculos must have at least 1 item.

{glossary_block}"""
        user_prompt = (
            f"Test case {pid}: {desc}\n"
            f"Test data: {datos or 'none'}\n"
            f"Expected: {esperado or 'not specified'}"
        )
        result = call_llm(
            model="gpt-4o-mini",
            system=system_prompt,
            user=user_prompt,
            max_tokens=512,
        )
        raw = result["text"].strip()
        raw = re.sub(r'^```[a-z]*\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)
        parsed = json.loads(raw)

        # Validate required fields
        if not parsed.get("pasos") or not parsed.get("oraculos"):
            return None
        # Check for placeholders in LLM output
        flat = json.dumps(parsed)
        if _PLACEHOLDER_RE.search(flat):
            return None

        pantalla = parsed.get("pantalla", "FrmAgenda.aspx")

        return {
            "scenario_id": pid,
            "ticket_id": ticket_id,
            "pantalla": pantalla,
            "titulo": desc,
            "precondiciones": parsed.get("precondiciones", []),
            "pasos": [_normalize_step(s) for s in parsed["pasos"]],
            "oraculos": [_normalize_oracle(o) for o in parsed["oraculos"]],
            "datos_requeridos": parsed.get("datos_requeridos", []),
            "origen": {"ticket_section": "plan_pruebas", "item_id": pid},
        }
    except Exception as exc:
        logger.debug("LLM compile failed for %s: %s", pid, exc)
        return None


# Oracle types that the M2 validator considers "anchored on a specific UI
# element" — these are the ones that, when targeted at a decorative layout
# label, produce false-FAIL or false-PASS verdicts.
_ANCHORED_ORACLE_TYPES = frozenset({
    "visible", "invisible", "equals", "contains_literal", "contains_semantic",
})


def _build_ui_elements_hint(ui_elements: list) -> str:
    """Build a structured per-alias hint block for the LLM system prompt.

    Each line declares: alias, kind, role, input_type, is_decorative, label.
    The LLM uses this to pick oracle types that match each target's nature
    (e.g. select_value_is for selects, page_contains_text instead of
    visible-on-decorative-label).

    Returned string includes the hard whitelist instruction and an
    enumerated list of aliases tagged decorative so the LLM can avoid them.
    """
    lines: list = []
    decorative_aliases: list = []
    for el in ui_elements:
        alias = el.get("alias_semantic")
        if not alias:
            continue
        kind = el.get("kind") or "?"
        role = el.get("role") or ""
        itype = el.get("input_type") or ""
        is_dec = bool(el.get("is_decorative"))
        label = (el.get("label") or el.get("accessible_name") or "")[:40]
        line = (
            f"- {alias}: kind={kind}"
            + (f" role={role}" if role else "")
            + (f" input_type={itype}" if itype else "")
            + (" is_decorative=true" if is_dec else "")
            + (f" label={label!r}" if label else "")
        )
        lines.append(line)
        if is_dec:
            decorative_aliases.append(alias)
    catalog = "\n".join(lines)
    out = (
        "\nUI MAP CATALOG (USE ONLY THESE aliases, do not invent new ones):\n"
        f"{catalog}\n"
    )
    if decorative_aliases:
        out += (
            "\nDECORATIVE LAYOUT ELEMENTS (NEVER use as oracle target for "
            "visible/invisible/equals/contains_literal — these are permanent "
            "layout titles, not runtime messages): "
            + ", ".join(sorted(decorative_aliases))
            + ".\n"
        )
    return out


def _find_decorative_oracle_targets(spec: dict, ui_elements: list) -> Optional[dict]:
    """Return details if any oracle in `spec` targets a decorative element
    using an anchored oracle type, else None.

    Format:
      {"oracle_index": 0, "target": "panel_x", "tipo": "invisible",
       "alias_kind": "div"}
    """
    decorative_aliases: dict = {}
    for el in ui_elements:
        alias = el.get("alias_semantic")
        if alias and el.get("is_decorative"):
            decorative_aliases[alias] = el
    if not decorative_aliases:
        return None
    for idx, oracle in enumerate(spec.get("oraculos") or []):
        target = oracle.get("target", "")
        tipo = oracle.get("tipo", "")
        if tipo in _ANCHORED_ORACLE_TYPES and target in decorative_aliases:
            el = decorative_aliases[target]
            return {
                "oracle_index": idx,
                "target": target,
                "tipo": tipo,
                "alias_kind": el.get("kind"),
                "label": el.get("label"),
            }
    return None


def _compile_via_heuristic(
    pid: str, desc: str, datos: str, esperado: str, ticket_id: int
) -> Optional[dict]:
    """Heuristic fallback for scenario compilation."""
    lower_desc = (desc + " " + esperado).lower()
    lower_datos = (datos or "").lower()

    # Detect screen
    pantalla = "FrmAgenda.aspx"
    if "detallelote" in lower_desc or "detalle de lote" in lower_desc:
        pantalla = "FrmDetalleLote.aspx"
    elif "gestion" in lower_desc or "gestión" in lower_desc:
        pantalla = "FrmGestion.aspx"

    # Build basic pasos
    pasos = [
        {"accion": "navigate", "target": pantalla, "valor": None},
    ]

    # Detect filter operations
    if any(kw in lower_datos for kw in ("empresa=", "empresa =")):
        pasos.append({"accion": "select", "target": "select_empresa", "valor": _extract_value(datos, "empresa")})
    if any(kw in lower_datos for kw in ("tipo_lote=", "tiplo=", "tipo lote")):
        pasos.append({"accion": "select", "target": "select_tipo_lote", "valor": _extract_value(datos, "tipo_lote")})
    if any(kw in lower_datos for kw in ("fecha_desde=", "fecha desde")):
        pasos.append({"accion": "fill", "target": "input_fecha_desde", "valor": _extract_value(datos, "fecha_desde")})

    pasos.append({"accion": "click", "target": "btn_buscar", "valor": None})

    # Build basic oraculos
    oraculos = []
    if "no hay" in lower_desc or "sin resultado" in lower_desc or "lista vacía" in lower_desc:
        oraculos.append({"tipo": "visible", "target": "msg_lista_vacia", "valor": None})
        oraculos.append({"tipo": "count_eq", "target": "grid_agenda_aut", "valor": "0"})
    else:
        oraculos.append({"tipo": "count_gt", "target": "grid_agenda_aut", "valor": "0"})

    if not oraculos:
        return None

    # Preconditions
    precondiciones = ["Login como PABLO"]
    if datos:
        precondiciones.append(f"Datos requeridos: {datos[:80]}")

    # Data required
    datos_requeridos = []
    empresa_val = _extract_value(datos, "empresa")
    if empresa_val:
        datos_requeridos.append({"tabla": "RAGEN", "filtro": f"OGEMPRESA='{empresa_val}'"})

    return {
        "scenario_id": pid,
        "ticket_id": ticket_id,
        "pantalla": pantalla,
        "titulo": desc,
        "precondiciones": precondiciones,
        "pasos": pasos,
        "oraculos": oraculos,
        "datos_requeridos": datos_requeridos,
        "origen": {"ticket_section": "plan_pruebas", "item_id": pid},
    }


def _postprocess_compiled_spec(spec: dict, desc: str, esperado: str) -> dict:
    """Fix common LLM mis-mappings for Agenda filter scenarios.

    Current production issue: LLM maps filter execution to `link_btnnext`
    (Avanzar) instead of the filter action button (`link_c_btnok` / Filtrar).

    Filter-keyword detection and the misroute mapping read from
    `agenda_glossary` so the catalogue can grow without code changes. If the
    glossary load fails (corrupt JSON, missing file) we fall back to a
    minimal hardcoded set that preserves the previous behaviour.
    """
    pantalla = str(spec.get("pantalla", ""))
    if pantalla != "FrmAgenda.aspx":
        return spec

    # Pull the screen-specific keyword set + filter input aliases + misroute
    # map from the glossary. `glossary_for_screen` returns a benign empty
    # view when the screen is not catalogued, which is the safe default.
    screen_glossary = agenda_glossary.glossary_for_screen("FrmAgenda.aspx")
    filter_keywords = screen_glossary.get("filter_keywords") or []
    if not filter_keywords:
        # Hard fallback — keep the legacy literal list so a glossary load
        # failure never silently disables the post-processor.
        filter_keywords = [
            "filtro", "buscar", "búsqueda", "debito", "débito",
            "corredor", "nombre de cliente", "ruc", "campos",
        ]

    filter_input_aliases = set(
        screen_glossary.get("filter_input_aliases") or [
            "select_debito_auto", "input_corredor",
            "input_nombre_cliente", "input_ruc",
        ]
    )
    filter_action_button = (
        screen_glossary.get("filter_action_button") or "link_c_btnok"
    )
    common_misroutes = (
        screen_glossary.get("common_misroutes")
        or {"link_btnnext": "link_c_btnok"}
    )

    lower_ctx = f"{desc} {esperado}".lower()
    is_filter_scenario = any(
        str(token).lower() in lower_ctx for token in filter_keywords
    )
    if not is_filter_scenario:
        return spec

    pasos = []
    has_filter_input = False
    has_filter_click = False

    for step in spec.get("pasos", []):
        s = dict(step)
        accion = str(s.get("accion", ""))
        target = str(s.get("target", ""))

        if accion in {"fill", "select"} and target in filter_input_aliases:
            has_filter_input = True

        if accion == "click" and target in common_misroutes:
            # Rewrite well-known LLM mis-mappings (e.g. link_btnnext → the
            # filter button alias). The glossary owns the correction map.
            s["target"] = common_misroutes[target]
            has_filter_click = True
        elif accion == "click" and target == filter_action_button:
            has_filter_click = True

        pasos.append(s)

    # If the scenario edits filters but never clicks the filter action button,
    # append it explicitly.
    if has_filter_input and not has_filter_click:
        pasos.append({
            "accion": "click",
            "target": filter_action_button,
            "valor": None,
        })

    spec["pasos"] = pasos
    return spec


def _extract_value(datos: str, key: str) -> Optional[str]:
    """Extract value from datos string like 'empresa=0001, tipo_lote=CRED'."""
    if not datos:
        return None
    pattern = re.compile(
        rf'{re.escape(key)}\s*[=:]\s*([^\s,;]+)', re.IGNORECASE
    )
    m = pattern.search(datos)
    return m.group(1).strip() if m else None


def _normalize_step(step: dict) -> dict:
    return {
        "accion": str(step.get("accion", "click")),
        "target": str(step.get("target", "")),
        "valor": step.get("valor"),
    }


def _normalize_oracle(oracle: dict) -> dict:
    return {
        "tipo": str(oracle.get("tipo", "visible")),
        "target": str(oracle.get("target", "")),
        "valor": oracle.get("valor"),
    }


# ── Persistence ────────────────────────────────────────────────────────────────

def _persist(ticket_id: int, scenarios: list, out_of_scope: list) -> None:
    evidence_dir = Path(__file__).resolve().parent / "evidence" / str(ticket_id)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = evidence_dir / "scenarios.json"
    data = {
        "ok": True,
        "ticket_id": ticket_id,
        "compiled": len(scenarios),
        "out_of_scope": len(out_of_scope),
        "scenarios": scenarios,
        "out_of_scope_items": out_of_scope,
    }
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not persist scenarios.json: %s", exc)


# ── Utilities ─────────────────────────────────────────────────────────────────

def _err(code: str, message: str) -> dict:
    return {"ok": False, "error": code, "message": message}


def _exit_err(code: str, message: str) -> None:
    print(json.dumps({"ok": False, "error": code, "message": message}))
    sys.exit(1)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="uat_scenario_compiler — Compile P0N items into ScenarioSpec list"
    )
    parser.add_argument("--input", type=str, default=None,
                        help="Path to ticket.json (default: stdin)")
    parser.add_argument("--ticket", type=int, default=None,
                        help="Ticket ID to read from evidence/<id>/ticket.json")
    parser.add_argument("--scope", type=str, default=None,
                        help="Filter by screen: screen=FrmAgenda.aspx")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
