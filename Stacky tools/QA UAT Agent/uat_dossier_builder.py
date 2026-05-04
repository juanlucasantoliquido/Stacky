"""
uat_dossier_builder.py — Build UAT evidence dossier from runner output.

SPEC: SPEC/uat_dossier_builder.md
CLI:
    python uat_dossier_builder.py \
        --runner-output evidence/70/runner_output.json \
        --ticket evidence/70/ticket.json \
        --out evidence/70/ \
        [--verbose]

Output: JSON to stdout. Also writes:
  - evidence/<ticket>/dossier.json
  - evidence/<ticket>/DOSSIER_UAT.md
  - evidence/<ticket>/ado_comment.html

Uses LLM (gpt-4.1) for executive_summary and recommendations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.dossier_builder")

_TOOL_VERSION = "1.0.0"
_EXEC_SUMMARY_MAX_LEN = 600
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr,
                            format="%(levelname)s %(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    result = run(
        runner_output_path=Path(args.runner_output),
        ticket_path=Path(args.ticket),
        out_dir=Path(args.out),
        verbose=args.verbose,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("ok") else 1)


def run(
    runner_output_path: Path,
    ticket_path: Path,
    out_dir: Path,
    verbose: bool = False,
) -> dict:
    """Core logic — callable from tests without subprocess."""
    started = time.time()

    # Load runner output
    try:
        runner_data = json.loads(runner_output_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return _err("missing_artifact", f"Cannot read runner_output.json: {exc}")

    if not runner_data.get("ok"):
        return _err("missing_artifact", "runner_output.json has ok=false")

    # Load ticket data
    try:
        ticket_data = json.loads(ticket_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return _err("missing_artifact", f"Cannot read ticket.json: {exc}")

    ticket_id = runner_data.get("ticket_id", 0)
    ticket_obj = ticket_data.get("ticket") or {}
    ticket_title = ticket_obj.get("title", f"Ticket #{ticket_id}")

    # Compute verdict
    runs = runner_data.get("runs", [])
    verdict = _compute_verdict(runs)

    # Generate executive summary via LLM
    executive_summary = _generate_executive_summary(
        ticket_title=ticket_title,
        verdict=verdict,
        runs=runs,
        verbose=verbose,
    )

    # Build failures list
    failures = [
        run for run in runs
        if run.get("status") != "pass"
    ]

    # Build recommendations
    recommendations = _generate_recommendations(
        verdict=verdict,
        failures=failures,
        runs=runs,
        verbose=verbose,
    )

    # Compute run ID (UUID v4 format)
    import uuid
    run_id = str(uuid.uuid4())

    # Detect primary screen from runs
    scenarios_data_raw = ticket_data.get("plan_pruebas") or []
    screen = "FrmAgenda.aspx"  # default
    for run in runs:
        spec_file = run.get("spec_file", "")
        if "FrmDetalleLote" in spec_file:
            screen = "FrmDetalleLote.aspx"
            break
        elif "FrmGestion" in spec_file:
            screen = "FrmGestion.aspx"
            break

    # Build context block (schema-required fields)
    context = {
        "environment": os.environ.get("STACKY_ENV", "qa"),
        "agent_version": _TOOL_VERSION,
        "total": runner_data.get("total", 0),
        "pass": runner_data.get("pass", 0),
        "fail": runner_data.get("fail", 0),
        "blocked": runner_data.get("blocked", 0),
    }

    # Build dossier JSON (schema-compliant)
    dossier: dict = {
        "ok": True,
        "schema_version": "qa-uat-dossier/1.0",
        "run_id": run_id,
        "ticket_id": ticket_id,
        "ticket_title": ticket_title,
        "screen": screen,
        "verdict": verdict,
        "executive_summary": executive_summary[:_EXEC_SUMMARY_MAX_LEN],
        "context": context,
        "scenarios": [_format_scenario_result(r) for r in runs],
        "failures": [_format_failure(r) for r in failures],
        "recommendation_for_human_qa": recommendations,
        "next_steps": _next_steps(verdict),
        "generated_at": _now_iso(),
        "meta": {
            "tool": "uat_dossier_builder",
            "version": _TOOL_VERSION,
            "duration_ms": 0,  # updated at end
        },
    }

    # Load Jinja2
    try:
        from jinja2 import Environment, FileSystemLoader, StrictUndefined
        env = Environment(
            loader=FileSystemLoader(str(_TEMPLATES_DIR)),
            undefined=StrictUndefined,
            autoescape=False,
        )
    except ImportError:
        return _err("template_render_failed", "jinja2 not installed")

    out_dir.mkdir(parents=True, exist_ok=True)

    # Render DOSSIER_UAT.md
    try:
        md_template = env.get_template("dossier.md.j2")
        md_content = md_template.render(**dossier)
    except Exception as exc:
        return _err("template_render_failed", f"dossier.md.j2 render failed: {exc}")

    md_path = out_dir / "DOSSIER_UAT.md"
    md_path.write_text(md_content, encoding="utf-8")

    # Render ado_comment.html
    try:
        html_template = env.get_template("ado_comment.html.j2")
        html_content_no_marker = html_template.render(
            **{**dossier, "comment_hash": "placeholder"}
        )
        # Compute hash of content *before* inserting the idempotence marker
        comment_hash = _sha256_hex(html_content_no_marker)
        html_content = html_template.render(
            **{**dossier, "comment_hash": comment_hash}
        )
    except Exception as exc:
        return _err("template_render_failed", f"ado_comment.html.j2 render failed: {exc}")

    html_path = out_dir / "ado_comment.html"
    html_path.write_text(html_content, encoding="utf-8")

    # Optionally post-process HTML for ADO compatibility
    html_content = _postprocess_for_ado(html_content)

    # Update timing and persist dossier.json
    dossier["meta"]["duration_ms"] = int((time.time() - started) * 1000)
    dossier["comment_hash"] = comment_hash
    dossier["paths"] = {
        "dossier_md": str(md_path),
        "ado_comment_html": str(html_path),
    }

    dossier_path = out_dir / "dossier.json"
    dossier_path.write_text(json.dumps(dossier, ensure_ascii=False, indent=2), encoding="utf-8")

    return dossier


# ── Verdict ────────────────────────────────────────────────────────────────────

def _compute_verdict(runs: list) -> str:
    """
    PASS   — all runs pass
    FAIL   — at least one fail, no blocked
    BLOCKED — all non-pass are blocked (no fail)
    MIXED  — has both fail and blocked
    """
    if not runs:
        return "BLOCKED"
    statuses = [r.get("status") for r in runs]
    has_fail = any(s == "fail" for s in statuses)
    has_blocked = any(s == "blocked" for s in statuses)
    all_pass = all(s == "pass" for s in statuses)

    if all_pass:
        return "PASS"
    if has_fail and has_blocked:
        return "MIXED"
    if has_fail:
        return "FAIL"
    return "BLOCKED"


# ── LLM narrative ─────────────────────────────────────────────────────────────

def _generate_executive_summary(
    ticket_title: str,
    verdict: str,
    runs: list,
    verbose: bool = False,
) -> str:
    """Generate exec summary via LLM, fallback to template string."""
    fails = [r for r in runs if r.get("status") != "pass"]
    fail_ids = ", ".join(r.get("scenario_id", "") for r in fails)
    total = len(runs)
    passed = sum(1 for r in runs if r.get("status") == "pass")

    try:
        from llm_client import call_llm, LLMError
        prompt = (
            f"Ticket: {ticket_title}\n"
            f"Verdict: {verdict}\n"
            f"Total scenarios: {total}, passed: {passed}, issues: {len(fails)}\n"
            f"Failed/blocked scenarios: {fail_ids or 'none'}\n"
            "Write a concise UAT executive summary in Spanish, max 600 chars. "
            "Professional tone. No markdown formatting."
        )
        result = call_llm(
            model="gpt-4.1",
            system="You are a QA UAT analyst writing concise executive summaries.",
            user=prompt,
            max_tokens=200,
        )
        return result["text"].strip()[:_EXEC_SUMMARY_MAX_LEN]
    except Exception as exc:
        logger.debug("LLM exec summary failed, using fallback: %s", exc)
        if verdict == "PASS":
            return (
                f"Todos los {total} escenarios de la prueba UAT para '{ticket_title}' "
                f"pasaron exitosamente. No se detectaron defectos."
            )
        else:
            return (
                f"Se ejecutaron {total} escenarios UAT para '{ticket_title}'. "
                f"Resultado: {verdict}. "
                f"Escenarios con problemas: {fail_ids or 'ninguno'}. "
                f"Se requiere revisión humana de los ítems marcados."
            )[:_EXEC_SUMMARY_MAX_LEN]


def _generate_recommendations(
    verdict: str,
    failures: list,
    runs: list,
    verbose: bool = False,
) -> list:
    """Generate human recommendations via LLM, fallback to heuristics."""
    if not failures:
        return ["Todos los escenarios pasaron. Proceder con aprobación del QA humano."]

    fail_text = json.dumps(
        [{"id": r.get("scenario_id"), "status": r.get("status"),
          "failures": r.get("assertion_failures", [r.get("reason", "")])}
         for r in failures],
        ensure_ascii=False,
    )[:1000]

    try:
        from llm_client import call_llm, LLMError
        result = call_llm(
            model="gpt-4.1",
            system="You are a QA analyst. Reply ONLY with a JSON array of Spanish recommendation strings.",
            user=(
                f"Verdict: {verdict}\nFailures:\n{fail_text}\n\n"
                "List 2-4 concrete recommendations for the human QA."
            ),
            max_tokens=300,
        )
        raw = result["text"].strip()
        raw = re.sub(r'^```[a-z]*\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(r) for r in parsed]
    except Exception as exc:
        logger.debug("LLM recommendations failed: %s", exc)

    # Fallback heuristic
    recs = []
    for r in failures:
        sid = r.get("scenario_id", "")
        reason = r.get("reason") or ""
        afs = r.get("assertion_failures", [])
        if reason == "RUNTIME_ERROR":
            recs.append(f"[{sid}] Error de ejecución — verificar entorno (Node, Playwright, env vars).")
        elif afs:
            first = afs[0].get("message", "")[:100]
            recs.append(f"[{sid}] Fallo de aserción: {first}")
        else:
            recs.append(f"[{sid}] Revisar manualmente — status: {r.get('status')}")
    return recs


# ── Formatting ────────────────────────────────────────────────────────────────

def _format_scenario_result(run: dict) -> dict:
    return {
        "scenario_id": run.get("scenario_id"),
        "titulo": run.get("scenario_id", ""),  # titel comes from scenario_id; full title from scenarios data if available
        "status": run.get("status"),
        "duration_ms": run.get("duration_ms", 0),
        "artifacts": run.get("artifacts", {}),
        "assertion_failures": run.get("assertion_failures", []),
    }


def _format_failure(run: dict) -> dict:
    """Format a failure for schema compliance — requires scenario_id, titulo, message."""
    afs = run.get("assertion_failures", [])
    first_af = afs[0] if afs else {}
    reason = run.get("reason", "")
    message = (
        first_af.get("message") or reason or
        f"Scenario {run.get('scenario_id')} failed with status {run.get('status')}"
    )
    result: dict = {
        "scenario_id": run.get("scenario_id"),
        "titulo": run.get("scenario_id", ""),
        "message": str(message)[:300],
    }
    if first_af.get("expected"):
        result["expected"] = str(first_af["expected"])[:100]
    if first_af.get("actual"):
        result["actual"] = str(first_af["actual"])[:100]
    artifacts = run.get("artifacts", {})
    if artifacts.get("trace"):
        result["trace_path"] = artifacts["trace"]
    if artifacts.get("screenshots"):
        result["screenshot_path"] = artifacts["screenshots"][0]
    return result


def _next_steps(verdict: str) -> list:
    if verdict == "PASS":
        return [
            "Comunicar resultado al Tech Lead y PM.",
            "Adjuntar evidencia al ticket ADO.",
            "Cerrar sprint item si aplica.",
        ]
    elif verdict == "FAIL":
        return [
            "Revisar los escenarios fallidos con el desarrollador.",
            "Crear bug tickets para cada fallo confirmado.",
            "Planificar re-ejecución tras correcciones.",
        ]
    elif verdict == "BLOCKED":
        return [
            "Resolver bloqueos de entorno antes de re-ejecutar.",
            "Verificar configuración de env vars y base de datos.",
        ]
    else:  # MIXED
        return [
            "Separar fallos de bloqueos para tratamiento diferencial.",
            "Resolver bloqueos de entorno.",
            "Crear bugs para los escenarios fallidos.",
        ]


# ── ADO HTML postprocessing ────────────────────────────────────────────────────

def _postprocess_for_ado(html: str) -> str:
    """Apply ADO-specific HTML post-processing if available."""
    try:
        # The postprocessor is in a sibling package
        import importlib.util
        pp_path = (
            Path(__file__).resolve().parent.parent.parent
            / "Stacky pipeline" / "ado_html_postprocessor.py"
        )
        if pp_path.is_file():
            spec = importlib.util.spec_from_file_location("ado_html_postprocessor", pp_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod.md_to_ado_html(html)
    except Exception as exc:
        logger.debug("ADO HTML postprocessor unavailable: %s", exc)
    return html


# ── Utilities ─────────────────────────────────────────────────────────────────

def _sha256_hex(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    import datetime
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _err(code: str, message: str) -> dict:
    return {"ok": False, "error": code, "message": message}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="uat_dossier_builder — Build UAT evidence dossier"
    )
    parser.add_argument("--runner-output", required=True, dest="runner_output",
                        help="Path to runner_output.json")
    parser.add_argument("--ticket", required=True, help="Path to ticket.json")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
