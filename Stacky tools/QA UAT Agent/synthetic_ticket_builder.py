"""
synthetic_ticket_builder.py — Convert a validated intent_spec into a ticket.json
compatible with uat_ticket_reader output.

Fase 1 of the QA UAT Agent free-form improvement plan.

The output is byte-for-byte equivalent to what uat_ticket_reader.run() returns
so that all downstream stages (compiler, generator, runner, dossier, publisher)
work without modification.  The synthetic ticket has id=-1 and state="FreeForm"
so it is clearly distinguishable from real ADO tickets in logs and evidence.

CLI:
    python synthetic_ticket_builder.py --intent-file intent_spec.json [--verbose]
    python synthetic_ticket_builder.py --intent-file intent_spec.json \\
        --data-file resolved_data.json [--out evidence/freeform/ticket.json]

Output: JSON to stdout (same schema as uat_ticket.schema.json)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.synthetic_ticket_builder")

_TOOL_VERSION = "1.0.0"
# Sentinel ticket_id for free-form runs — never clashes with real ADO ids.
_FREEFORM_TICKET_ID = -1


# ── Public API ────────────────────────────────────────────────────────────────

def run(
    intent_spec: dict,
    verbose: bool = False,
) -> dict:
    """Convert a validated intent_spec (from intent_parser) → ticket.json dict.

    Returns the same structure as uat_ticket_reader.run() with ok=True.
    The caller is responsible for persisting the result to evidence/<run_id>/ticket.json.
    """
    started = time.time()

    if not isinstance(intent_spec, dict):
        return _err("invalid_intent_spec", "intent_spec must be a dict")

    run_id = intent_spec.get("run_id", "freeform-unknown")
    intent_raw = intent_spec.get("intent_raw", "")
    goal_action = intent_spec.get("goal_action", "")
    entry_screen = intent_spec.get("entry_screen", "FrmAgenda.aspx")
    navigation_path = intent_spec.get("navigation_path") or [entry_screen]
    orchestrator_notes = intent_spec.get("orchestrator_notes", "")
    test_cases = intent_spec.get("test_cases") or []
    resolved_data = intent_spec.get("resolved_data") or {}

    # ── Free-form always executes 1 single end-to-end test case ─────────────
    # The orchestrator agent is instructed to generate exactly 1 test case (P01).
    # If more than 1 are present (older prompts / agent regression), keep only
    # the first and log a warning so the operator is aware.
    if len(test_cases) > 1:
        logger.warning(
            "synthetic_ticket_builder: intent_spec has %d test_cases — "
            "free-form mode runs 1 test only. Keeping P01, discarding P02+.",
            len(test_cases),
        )
        test_cases = test_cases[:1]

    # ── Build plan_pruebas[] from test_cases[] ───────────────────────────────
    plan_pruebas = []
    for case in test_cases:
        if not isinstance(case, dict):
            continue
        plan_pruebas.append({
            "id": case.get("id", f"P{len(plan_pruebas)+1:02d}"),
            "descripcion": case.get("descripcion", ""),
            "datos": case.get("datos", ""),
            "esperado": case.get("esperado", ""),
        })

    if not plan_pruebas:
        return _err("empty_test_cases", "intent_spec.test_cases is empty after conversion")

    # ── Build a rich analisis_tecnico text so the compiler can read it ────────
    # The compiler reads analisis_tecnico (free text) as a fallback context.
    # We include the navigation path and resolved data so the LLM has all context.
    nav_path_str = " → ".join(navigation_path)
    resolved_str = "\n".join(f"  {k}: {v}" for k, v in resolved_data.items()) or "  (ninguno)"
    notes_section = f"\n\nNotas del orquestador:\n{orchestrator_notes}" if orchestrator_notes else ""
    analisis_tecnico = (
        f"## Análisis Técnico (Free-Form QA — generado por UserInterfaceQAFreeForm)\n\n"
        f"**Intent**: {intent_raw}\n"
        f"**Acción objetivo**: {goal_action}\n"
        f"**Pantalla de entrada**: {entry_screen}\n"
        f"**Ruta de navegación**: {nav_path_str}\n\n"
        f"**Datos resueltos**:\n{resolved_str}"
        f"{notes_section}\n\n"
        f"## Plan de Pruebas\n\n"
        + _format_plan_as_text(plan_pruebas)
    )

    # ── Build the ticket dict — same schema as uat_ticket.schema.json ─────────
    ticket_json = {
        "ok": True,
        "ticket": {
            "id": _FREEFORM_TICKET_ID,
            "title": intent_raw or goal_action or "Free-Form QA Run",
            "state": "FreeForm",
            "type": "QA",
            "url": f"freeform://{run_id}",
        },
        "description_md": (
            f"**Run ID**: {run_id}\n"
            f"**Intent**: {intent_raw}\n"
            f"**Goal**: {goal_action}\n"
            f"**Entry screen**: {entry_screen}\n"
            f"**Navigation**: {nav_path_str}\n"
        ),
        "comments": [
            {
                "id": 1,
                "author": "UserInterfaceQAFreeForm",
                "date": _now_iso(),
                "text_md": analisis_tecnico,
                "role": "analisis_tecnico",
            }
        ],
        "analisis_tecnico": analisis_tecnico,
        "navigation_path": navigation_path,
        "plan_pruebas": plan_pruebas,
        "notas_qa": [
            f"Free-form run: {run_id}",
            f"Entry screen: {entry_screen}",
            f"Navigation path: {nav_path_str}",
        ],
        "adjuntos": [],
        "precondiciones_detected": _extract_preconditions(plan_pruebas, resolved_data),
        "meta": {
            "tool": "synthetic_ticket_builder",
            "version": _TOOL_VERSION,
            "run_id": run_id,
            "source": "freeform",
            "duration_ms": int((time.time() - started) * 1000),
        },
    }

    logger.debug(
        "synthetic_ticket_builder: run_id=%s plan_items=%d nav_steps=%d",
        run_id, len(plan_pruebas), len(navigation_path),
    )

    return ticket_json


# ── Internal helpers ─────────────────────────────────────────────────────────

def _format_plan_as_text(plan_pruebas: list) -> str:
    """Format plan_pruebas as the markdown table the compiler expects."""
    lines = []
    for item in plan_pruebas:
        pid = item.get("id", "P??")
        desc = item.get("descripcion", "")
        datos = item.get("datos", "")
        esperado = item.get("esperado", "")
        lines.append(f"**{pid}**: {desc}")
        if datos:
            lines.append(f"  Datos: {datos}")
        if esperado:
            lines.append(f"  Esperado: {esperado}")
        lines.append("")
    return "\n".join(lines)


def _extract_preconditions(plan_pruebas: list, resolved_data: dict) -> list:
    """Extract light preconditions list from plan_pruebas + resolved data."""
    precs = []
    for key, value in resolved_data.items():
        precs.append({
            "tipo": "resolved_data",
            "recurso": f"{key}={value}",
            "hint": f"Dato resuelto por orquestador: {key}={value}",
        })
    return precs


def _now_iso() -> str:
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")


def _err(code: str, message: str) -> dict:
    return {"ok": False, "error": code, "message": message}


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()
    if args.background:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr,
                            format="%(levelname)s %(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr,
                            format="%(levelname)s %(name)s: %(message)s")

    # Load intent_spec (optionally merge data_file first via intent_parser)
    from intent_parser import run as parser_run
    parser_result = parser_run(
        intent_file=Path(args.intent_file),
        data_file=Path(args.data_file) if args.data_file else None,
        verbose=not args.background,
    )
    if not parser_result.get("ok"):
        print(json.dumps(parser_result, ensure_ascii=False, indent=2))
        sys.exit(1)

    intent_spec = parser_result["intent_spec"]
    result = run(intent_spec=intent_spec, verbose=not args.background)

    if args.out and result.get("ok"):
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug("Wrote synthetic ticket.json to %s", out_path)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("ok") else 1)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build a synthetic ticket.json from an intent_spec.json."
    )
    p.add_argument("--intent-file", required=True,
                   help="Path to intent_spec.json.")
    p.add_argument("--data-file", default=None,
                   help="Optional resolved_data.json to merge.")
    p.add_argument("--out", default=None,
                   help="Write output to this path instead of only stdout.")
    p.add_argument("--background", action="store_true",
                   help="Background mode: suppress verbose logging.")
    return p.parse_args()


if __name__ == "__main__":
    main()
