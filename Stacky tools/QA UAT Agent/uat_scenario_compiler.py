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

_TOOL_VERSION = "1.0.0"

# Screens supported in MVP (from SPEC §6)
_SUPPORTED_SCREENS = frozenset({
    "FrmAgenda.aspx",
    "FrmDetalleLote.aspx",
    "FrmGestion.aspx",
    "Login.aspx",
})

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
    verbose: bool = False,
) -> dict:
    """Core logic — callable from tests without subprocess."""
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
        spec = _compile_scenario(pid, desc, datos, esperado, ticket_id, verbose=verbose)
        if spec is None:
            out_of_scope.append({
                "id": pid,
                "razon": "INCOMPLETE_SCENARIO",
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
    ticket_id: int, verbose: bool = False,
) -> Optional[dict]:
    """
    Compile a single P0N item into a ScenarioSpec.
    Tries LLM first, falls back to heuristics.
    """
    # Try LLM compilation
    spec = _compile_via_llm(pid, desc, datos, esperado, ticket_id, verbose=verbose)
    if spec:
        return spec

    # Fallback: heuristic extraction
    return _compile_via_heuristic(pid, desc, datos, esperado, ticket_id)


def _compile_via_llm(
    pid: str, desc: str, datos: str, esperado: str,
    ticket_id: int, verbose: bool = False,
) -> Optional[dict]:
    """Attempt to compile via LLM (gpt-4.1-mini). Return None on failure."""
    try:
        from llm_client import call_llm, LLMError

        system_prompt = """You are a QA automation engineer converting test plan items to structured test specs.
Given a test case description, extract a structured ScenarioSpec JSON.
Respond ONLY with valid JSON, no explanations.

The JSON must have:
- "pantalla": one of ["FrmAgenda.aspx","FrmDetalleLote.aspx","FrmGestion.aspx","Login.aspx"]
- "precondiciones": list of strings
- "pasos": list of {"accion": "<navigate|click|fill|select|wait_networkidle|wait_visible>", "target": "<alias>", "valor": <str|null>}
- "oraculos": list of {"tipo": "<equals|contains_literal|count_gt|count_eq|visible|invisible|state>", "target": "<alias>", "valor": <str|null>}
- "datos_requeridos": list of {"tabla": "<str>", "filtro": "<str>"}

Use semantic alias names like: btn_buscar, select_empresa, grid_agenda_aut, msg_lista_vacia, input_fecha_desde.
pasos must have at least 1 item. oraculos must have at least 1 item.
"""
        user_prompt = (
            f"Test case {pid}: {desc}\n"
            f"Test data: {datos or 'none'}\n"
            f"Expected: {esperado or 'not specified'}"
        )
        result = call_llm(
            model="gpt-4.1-mini",
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
