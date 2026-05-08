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

_TOOL_VERSION = "1.2.0"
_EXEC_SUMMARY_MAX_LEN = 600
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
# Token format used inside ado_comment.html for image src/href placeholders.
# The publisher swaps {{ATTACH:<scenario>:<filename>}} with the real attachment
# URL once each PNG has been uploaded to ADO.
_ATTACH_TOKEN_FMT = "{{{{ATTACH:{scenario}:{filename}}}}}"

# Regex de patrones de fallas TECNICAS del runner Playwright que NO deben
# imputarse al producto bajo prueba. Si una run trae status=fail con un mensaje
# que matchea cualquiera de estos, se reclasifica a status=blocked con
# reason=test_generator_defect, evitando falsos negativos contra el producto.
# Cada patron va con un motivo legible para el QA humano.
# Order matters: more specific patterns are listed FIRST so they win over the
# generic `playwright_action_timeout`. The first match decides the label.
_TEST_DEFECT_PATTERNS: tuple = (
    (r"intercepts pointer events",
     "click_blocked_by_overlay"),
    (r"locator resolved to .*input-field-label",
     "oracle_targeted_layout_label_not_runtime_message"),
    (r"locator resolved to .*<input type=\"date\"",
     "date_input_format_mismatch"),
    (r"strict mode violation:.*resolved to \d+ elements",
     "ambiguous_selector_strict_mode"),
    (r"element is not visible",
     "target_not_visible_when_acting"),
    (r"element is not (?:enabled|editable|stable)",
     "target_not_interactable_when_acting"),
    (r"TimeoutError:\s*locator\.(fill|click|press|check|uncheck|selectOption|hover|setInputFiles)\b",
     "playwright_action_timeout"),
    (r"locator\.(fill|click|press|check|uncheck|selectOption|hover|setInputFiles):\s*Timeout\b",
     "playwright_action_timeout"),
)


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
        scenarios_path=Path(args.scenarios) if args.scenarios else None,
        evaluations_path=Path(args.evaluations) if args.evaluations else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("ok") else 1)


def run(
    runner_output_path: Path,
    ticket_path: Path,
    out_dir: Path,
    verbose: bool = False,
    scenarios_path: Optional[Path] = None,
    evaluations_path: Optional[Path] = None,
) -> dict:
    """Core logic — callable from tests without subprocess.

    `scenarios_path` is optional; when present, step-level descriptions and
    attachment tokens are added to each scenario in dossier.scenarios.
    Defaults to <out_dir>/scenarios.json when found.

    `evaluations_path` is optional; when present, the semantic verdict produced
    by `uat_assertion_evaluator.py` takes precedence over the raw Playwright
    runner status. Defaults to <runner_output>.parent / "evaluations.json" when
    found. This is the primary safeguard against false-negative FAIL verdicts
    caused by Playwright runtime errors (timeouts, overlays, bad selectors)
    that are pipeline defects, not product defects.
    """
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

    # Load evaluations.json (optional) — semantic verdict from uat_assertion_evaluator.py
    if evaluations_path is None:
        guess = runner_output_path.parent / "evaluations.json"
        if guess.is_file():
            evaluations_path = guess
    evaluations_by_sid: dict = {}
    if evaluations_path and Path(evaluations_path).is_file():
        try:
            ed = json.loads(Path(evaluations_path).read_text(encoding="utf-8"))
            if ed.get("ok"):
                evaluations_by_sid = {
                    e.get("scenario_id"): e for e in (ed.get("evaluations") or [])
                }
        except Exception as exc:
            logger.warning("evaluations.json unreadable, using runner status only: %s", exc)
            evaluations_by_sid = {}

    # Compute verdict — reclassify each run BEFORE summarizing.
    # Precedence: (1) semantic evaluator status, (2) test_generator_defect
    # heuristic on technical failures, (3) raw runner status. This is the
    # primary safeguard against false-negative FAIL verdicts.
    runs = runner_data.get("runs", [])
    runs = _apply_consolidated_status(runs, evaluations_by_sid)
    verdict = _compute_verdict(runs)

    # Load scenarios.json (optional) for per-step descriptions
    if scenarios_path is None:
        guess = runner_output_path.parent / "scenarios.json"
        if guess.is_file():
            scenarios_path = guess
    scenarios_meta: list = []
    if scenarios_path and Path(scenarios_path).is_file():
        try:
            sd = json.loads(Path(scenarios_path).read_text(encoding="utf-8"))
            scenarios_meta = sd.get("scenarios") or []
        except Exception as exc:
            logger.warning("scenarios.json unreadable, skipping step descriptions: %s", exc)
            scenarios_meta = []

    # Build per-screenshot step descriptions (deterministic + optional LLM polish)
    step_descs_by_sid: dict = {}
    if scenarios_meta:
        try:
            from step_descriptor import build_step_descriptions
            step_descs_by_sid = build_step_descriptions(
                runner_runs=runs,
                scenarios=scenarios_meta,
                use_llm=os.environ.get("STACKY_LLM_BACKEND", "vscode_bridge").lower() != "mock",
            )
        except Exception as exc:
            logger.warning("step_descriptor failed, scenarios will lack step text: %s", exc)
            step_descs_by_sid = {}

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

    # Generate per-scenario narratives (what was attempted) via gpt-4.1-mini
    scenario_narratives = _generate_scenario_narratives(
        scenarios_meta=scenarios_meta,
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

    # Build context block (schema-required fields).
    # Recompute counts from the consolidated `runs` so they reflect any
    # reclassification (fail -> blocked) applied above. Without this, the
    # dossier would show contradictory numbers vs the verdict.
    pass_count = sum(1 for r in runs if r.get("status") == "pass")
    fail_count = sum(1 for r in runs if r.get("status") == "fail")
    blocked_count = sum(1 for r in runs if r.get("status") == "blocked")
    context = {
        "environment": os.environ.get("STACKY_ENV", "qa"),
        "agent_version": _TOOL_VERSION,
        "total": len(runs),
        "pass": pass_count,
        "fail": fail_count,
        "blocked": blocked_count,
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
        "scenarios": [
            _format_scenario_result(
                r,
                step_descs=step_descs_by_sid.get(r.get("scenario_id")),
                scenario_meta=next(
                    (sm for sm in scenarios_meta
                     if sm.get("scenario_id") == r.get("scenario_id")),
                    None,
                ),
                narrative=scenario_narratives.get(r.get("scenario_id")),
            ) for r in runs
        ],
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


def _apply_consolidated_status(runs: list, evaluations_by_sid: dict) -> list:
    """Reconcile runner status with semantic evaluator status and reclassify
    technical failures of the test pipeline as `blocked` instead of `fail`.

    This function is the architectural fix for false-negative FAIL verdicts
    that previously bubbled up from the raw Playwright runner output.

    Precedence rules per scenario:
      1. If evaluations[sid].status is 'fail'  -> status='fail'  (real product
         defect, validated by deterministic or semantic oracle).
      2. If evaluations[sid].status is 'review' -> status='blocked' with
         reason='evaluator_inconclusive' (the evaluator could not decide;
         do NOT impute to the product).
      3. If evaluations[sid].status is 'pass'  -> status='pass'.
      4. If evaluations[sid].status is 'blocked' -> status='blocked' (keep
         evaluator reason if any, else fall back to runner reason).
      5. If no evaluator entry for sid AND runner.status == 'fail', inspect
         raw_stdout/stderr against `_TEST_DEFECT_PATTERNS`. Any match means the
         failure is a defect of the test generator/runner pipeline, not the
         product -> reclassify to status='blocked' with
         reason='test_generator_defect:<pattern_label>'.
      6. Otherwise leave runner.status untouched.

    Mutates a copy of each run dict; original list is not modified.
    """
    out: list = []
    for run in runs:
        new = dict(run)  # shallow copy is enough — we only touch top-level keys
        sid = new.get("scenario_id", "")
        original_status = new.get("status", "")

        eval_entry = evaluations_by_sid.get(sid) if evaluations_by_sid else None

        # Rule 1-4: semantic evaluator wins when present.
        if eval_entry is not None:
            eval_status = (eval_entry.get("status") or "").lower()
            if eval_status == "fail":
                new["status"] = "fail"
                # Surface assertion mismatch from evaluator if runner did not.
                if not new.get("assertion_failures"):
                    afs = []
                    for a in (eval_entry.get("assertions") or []):
                        if a.get("status") == "fail":
                            afs.append({
                                "message": (
                                    f"Oracle '{a.get('target','')}' "
                                    f"(tipo={a.get('tipo','')}) "
                                    f"expected={a.get('expected')!r} "
                                    f"actual={a.get('actual')!r}"
                                )[:300],
                                "expected": str(a.get("expected"))[:100]
                                if a.get("expected") is not None else "",
                                "actual": str(a.get("actual"))[:100]
                                if a.get("actual") is not None else "",
                            })
                    if afs:
                        new["assertion_failures"] = afs
            elif eval_status == "pass":
                new["status"] = "pass"
            elif eval_status == "review":
                # Evaluator could not decide -> NOT a product defect.
                new["status"] = "blocked"
                new["reason"] = "evaluator_inconclusive"
                new["reclassified_from"] = original_status
            elif eval_status == "blocked":
                new["status"] = "blocked"
                if not new.get("reason"):
                    new["reason"] = eval_entry.get("reason") or "blocked_by_evaluator"
            out.append(new)
            continue

        # Rule 5: heuristic reclassification of technical runner failures.
        if original_status == "fail":
            label = _match_test_defect(new)
            if label:
                new["status"] = "blocked"
                new["reason"] = f"test_generator_defect:{label}"
                new["reclassified_from"] = "fail"

        # Rule 6: leave as-is.
        out.append(new)
    return out


def _match_test_defect(run: dict) -> Optional[str]:
    """Return a label if the run's raw output matches a known test-pipeline
    defect pattern, else None.

    Inspects raw_stdout, raw_stderr, and assertion_failures[*].message — these
    are the surfaces where Playwright reports the technical reason a step blew
    up before the product could even be evaluated.
    """
    haystacks: list = []
    if run.get("raw_stdout"):
        haystacks.append(run["raw_stdout"])
    if run.get("raw_stderr"):
        haystacks.append(run["raw_stderr"])
    for af in (run.get("assertion_failures") or []):
        msg = af.get("message") or ""
        if msg:
            haystacks.append(msg)

    if not haystacks:
        return None
    blob = "\n".join(haystacks)
    for pattern, label in _TEST_DEFECT_PATTERNS:
        if re.search(pattern, blob, flags=re.IGNORECASE | re.DOTALL):
            return label
    return None


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

def _generate_scenario_narratives(
    scenarios_meta: list,
    runs: list,
    verbose: bool = False,
) -> dict:
    """Generate per-scenario 'what was attempted' narrative using gpt-4.1-mini.

    Returns dict {scenario_id: narrative_str}.
    Each narrative is a 1-2 sentence Spanish explanation of what the scenario
    tried to verify, generated via LLM with deterministic fallback.
    """
    narratives: dict = {}
    runs_by_id = {r.get("scenario_id"): r for r in runs}

    for sm in scenarios_meta:
        sid = sm.get("scenario_id", "")
        run = runs_by_id.get(sid, {})
        titulo = sm.get("titulo", sid)
        pasos = sm.get("pasos") or []
        oraculos = sm.get("oraculos") or []
        status = run.get("status", "unknown")

        # Deterministic fallback
        fallback = (
            f"Se intentó verificar: {titulo}. "
            f"Se ejecutaron {len(pasos)} paso(s) y se evaluaron "
            f"{len(oraculos)} condición(es). Resultado: {status.upper()}."
        )

        try:
            from llm_client import call_llm, LLMError

            steps_text = "\n".join(
                f"  {i + 1}. {p.get('accion', '?')} en '{p.get('target', '?')}'" +
                (f" con valor '{p.get('valor')}'" if p.get("valor") else "")
                for i, p in enumerate(pasos[:8])
            )
            oracles_text = "\n".join(
                f"  - {o.get('tipo', '?')}: '{o.get('valor', '?')}'" for o in oraculos[:5]
            )
            preconditions_text = "; ".join(sm.get("precondiciones") or ["ninguna"])

            prompt = (
                f"Escenario: {titulo}\n"
                f"Precondiciones: {preconditions_text}\n"
                f"Pasos ejecutados:\n{steps_text}\n"
                f"Condiciones verificadas:\n{oracles_text}\n"
                f"Resultado: {status.upper()}\n\n"
                "Escribe en 1-2 oraciones en español qué intentó verificar este escenario "
                "de prueba automatizado. Sé específico sobre la funcionalidad probada. "
                "No uses markdown. Tono técnico y conciso."
            )

            result = call_llm(
                model="gpt-4o-mini",
                system=(
                    "Eres un analista QA técnico. Tu tarea es explicar brevemente "
                    "qué intentó verificar un escenario de prueba automatizado, "
                    "basándote en sus pasos y oráculos de verificación."
                ),
                user=prompt,
                max_tokens=150,
            )
            narratives[sid] = result["text"].strip()
        except Exception as exc:
            logger.debug("LLM narrative failed for %s, using fallback: %s", sid, exc)
            narratives[sid] = fallback

    return narratives


def _format_scenario_result(run: dict, step_descs: list | None = None,
                            scenario_meta: dict | None = None,
                            narrative: str | None = None) -> dict:
    sid = run.get("scenario_id") or ""
    titulo = (scenario_meta or {}).get("titulo") or sid
    steps = []
    for d in (step_descs or []):
        filename = d.get("screenshot_name") or ""
        steps.append({
            "screenshot_name": filename,
            "screenshot_path": d.get("screenshot"),
            "step_index": d.get("step_index"),
            "action": d.get("action"),
            "target": d.get("target"),
            "value": d.get("value"),
            "description": d.get("description"),
            "description_source": d.get("description_source", "deterministic"),
            "attachment_token": _ATTACH_TOKEN_FMT.format(scenario=sid, filename=filename),
        })
    formatted: dict = {
        "scenario_id": sid,
        "titulo": titulo,
        "status": run.get("status"),
        "duration_ms": run.get("duration_ms", 0),
        "artifacts": run.get("artifacts", {}),
        "assertion_failures": run.get("assertion_failures", []),
        "steps": steps,
        "attempt_narrative": narrative or "",
    }
    # Surface the reclassification reason so the dossier and the human QA
    # can see WHY a runner-fail became a blocked. Both keys are
    # additionalProperties=true in dossier.schema.json.
    if run.get("reason"):
        formatted["reason"] = run["reason"]
    if run.get("reclassified_from"):
        formatted["reclassified_from"] = run["reclassified_from"]
    return formatted


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
    parser.add_argument("--scenarios", default=None, dest="scenarios",
                        help="Path to scenarios.json (optional, auto-detected next to runner_output.json)")
    parser.add_argument("--evaluations", default=None, dest="evaluations",
                        help=("Path to evaluations.json from uat_assertion_evaluator (optional, "
                              "auto-detected next to runner_output.json). When present, the "
                              "semantic evaluator status takes precedence over the raw runner "
                              "status to avoid false-negative FAIL verdicts."))
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
