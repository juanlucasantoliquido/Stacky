"""
focused_ado120_publisher.py - canonical handoff step for the focused ADO-120 spec.

It converts the standalone Playwright evidence directory into the same
ado_comment.html + dossier.json contract consumed by Stacky handoff.
ADO comments are published only by Stacky Agents backend; ADO state changes
and DB DML remain out of scope.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from stacky_handoff import export_stacky_handoff

_TOOL_ROOT = Path(__file__).resolve().parent
_MARKER_TEMPLATE = '<!-- stacky-qa-uat:run id="{run_id}" hash="{comment_hash}" -->'


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-")


def main() -> None:
    args = _parse_args()
    result = run(
        evidence_dir=Path(args.evidence_dir),
        ticket_id=args.ticket_id,
        mode=args.mode,
        verbose=args.verbose,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("ok") else 1)


def run(
    *,
    evidence_dir: Path,
    ticket_id: int = 120,
    mode: str = "auto",
    verbose: bool = False,
) -> dict:
    started = time.time()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    summary_path = evidence_dir / "summary.json"
    if not summary_path.is_file():
        return {"ok": False, "error": "missing_summary", "message": str(summary_path)}

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    pngs = sorted(evidence_dir.glob("*.png"))
    run_id = os.environ.get("QA_UAT_RUN_ID") or _clean_id(evidence_dir.name)
    scenario_id = "ADO-120-RF-007-OBLIGACIONES"
    data_readiness = _load_json(evidence_dir / "data_readiness.json") or {}
    missing_batch = _missing_batch_fields(summary)
    if missing_batch and not data_readiness:
        data_readiness = {
            "status": "BLOCKED_DATA",
            "missing_batch_fields": missing_batch,
            "message": "QA client has structural RF-007 columns but incomplete batch values.",
        }
        (evidence_dir / "data_readiness.json").write_text(
            json.dumps(data_readiness, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    verdict = "PASS" if not missing_batch else "BLOCKED"
    comment_body = _render_comment_body(
        ticket_id=ticket_id,
        run_id=run_id,
        scenario_id=scenario_id,
        summary=summary,
        pngs=pngs,
        verdict=verdict,
        data_readiness=data_readiness,
    )
    comment_hash = sha256(comment_body.encode("utf-8")).hexdigest()
    html_content = _MARKER_TEMPLATE.format(run_id=run_id, comment_hash=comment_hash) + "\n" + comment_body
    (evidence_dir / "ado_comment.html").write_text(html_content, encoding="utf-8")

    dossier = {
        "ok": True,
        "schema_version": "qa-uat-dossier/1.1",
        "run_id": run_id,
        "ticket_id": ticket_id,
        "ticket_title": "ADO-120 RF-007 - Lista de Obligaciones",
        "screen": "FrmDetalleClie.aspx",
        "verdict": verdict,
        "context": {
            "environment": os.environ.get("STACKY_ENV", "qa"),
            "agent_version": "focused_ado120_publisher/1.0",
            "total": 1,
            "pass": 1 if verdict == "PASS" else 0,
            "fail": 0,
            "blocked": 1 if verdict == "BLOCKED" else 0,
            "not_tested": 0,
        },
        "scenarios": [{
            "scenario_id": scenario_id,
            "titulo": "Validacion estructural de columnas RF-007 en obligaciones",
            "status": "pass" if verdict == "PASS" else "blocked",
            "duration_ms": 0,
            "artifacts": {"screenshots": [str(p) for p in pngs]},
            "steps": [
                {
                    "screenshot_name": p.name,
                    "screenshot_path": str(p),
                    "step_index": idx,
                    "description": p.stem.replace("_", " "),
                    "description_source": "deterministic",
                    "attachment_token": f"{{{{ATTACH:{scenario_id}:{p.name}}}}}",
                }
                for idx, p in enumerate(pngs)
            ],
        }],
        "failures": [],
        "coverage_gaps": [{
            "scenario_id": scenario_id,
            "reason": "BLOCKED_DATA",
            "missing_batch_fields": missing_batch,
        }] if missing_batch else [],
        "recommendation_for_human_qa": _recommendations(missing_batch),
        "next_steps": _next_steps(missing_batch),
        "generated_at": _now(),
        "comment_hash": comment_hash,
        "paths": {
            "ado_comment_html": str(evidence_dir / "ado_comment.html"),
            "dossier_json": str(evidence_dir / "dossier.json"),
        },
        "meta": {
            "tool": "focused_ado120_publisher",
            "duration_ms": int((time.time() - started) * 1000),
        },
    }
    (evidence_dir / "dossier.json").write_text(
        json.dumps(dossier, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if mode == "dry-run":
        handoff_result = {
            "ok": True,
            "publish_state": "dry-run",
            "ticket_id": ticket_id,
            "html_output_path": None,
            "output_dir": None,
            "attachments_count": len(pngs),
            "message": "DRY-RUN: generated local dossier only; no Stacky output handoff.",
        }
    else:
        handoff_result = export_stacky_handoff(
            ticket_id=ticket_id,
            dossier_path=evidence_dir / "dossier.json",
            html_path=evidence_dir / "ado_comment.html",
            source="focused_ado120_publisher",
        )
    handoff_result["mode"] = "dry-run" if mode == "dry-run" else "stacky_handoff"
    handoff_result["focused_run"] = {
        "evidence_dir": str(evidence_dir),
        "canonical_comment": str(evidence_dir / "ado_comment.html"),
        "mode": handoff_result["mode"],
        "data_readiness": data_readiness,
    }
    return handoff_result


def _render_comment_body(
    *,
    ticket_id: int,
    run_id: str,
    scenario_id: str,
    summary: dict,
    pngs: list[Path],
    verdict: str,
    data_readiness: dict,
) -> str:
    fields = summary.get("first_row_values") or {}
    columns = (summary.get("assertions") or {}).get("new_columns_present") or []
    status_label = "PASS" if verdict == "PASS" else "BLOCKED DATA"
    rows = "\n".join(
        f"<tr><td>{html.escape(str(c.get('key', '')))}</td>"
        f"<td>{html.escape(str(c.get('text', c.get('label', ''))))}</td>"
        f"<td>{html.escape(str(fields.get(c.get('key'), '')))}</td></tr>"
        for c in columns
    )
    shots = "\n".join(
        f'<p><img src="{{{{ATTACH:{scenario_id}:{p.name}}}}}" '
        f'alt="{html.escape(p.name)}" style="max-width: 720px; border: 1px solid #ddd;" /></p>'
        for p in pngs
    )
    blocked = ""
    missing = data_readiness.get("missing_batch_fields") or []
    if missing:
        blocked = (
            "<p><strong>Bloqueo de datos:</strong> el cliente QA usado no tiene "
            "valores batch completos para "
            f"<code>{html.escape(', '.join(missing))}</code>. "
            "Seleccionar QA_UAT_ADO120_CLCOD con batch completo o poblar datos QA "
            "antes de cerrar el ticket.</p>"
        )
    return f"""
<div style="font-family: Segoe UI, Arial, sans-serif; font-size: 13px;">
  <h2>QA UAT - ADO-{ticket_id} - {status_label}</h2>
  <p>Run: <code>{html.escape(run_id)}</code> | Cliente: <code>{html.escape(str(summary.get('clcod', '')))}</code></p>
  <p>Validacion estructural RF-007: columnas nuevas presentes, columna de ingreso judicial ausente y columnas nuevas solo lectura.</p>
  {blocked}
  <table style="border-collapse: collapse;" border="1" cellpadding="5">
    <thead><tr><th>Campo</th><th>Header UI</th><th>Valor primera fila</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <h3>Evidencias adjuntas</h3>
  {shots}
  <p><strong>Postura:</strong> comentario de evidencia preparado por QA UAT para publicación centralizada por Stacky. No cambia estado ADO ni ejecuta DML.</p>
</div>
""".strip()


def _missing_batch_fields(summary: dict) -> list[str]:
    values = summary.get("first_row_values") or {}
    required = ["OGCANAL", "OGMEDIOPAGO", "DESALDOFAVOR", "OGCUOTA", "OGMONTOCUOTA", "OGCORREDOR", "OGNROCUOTAS"]
    missing = []
    for key in required:
        value = str(values.get(key, "")).strip()
        if value in ("", "-", "0") and key not in {"OGNROCUOTAS"}:
            missing.append(key)
    return missing


def _recommendations(missing: list[str]) -> list[str]:
    if missing:
        return ["Usar QA_UAT_ADO120_CLCOD con datos batch completos antes de cerrar ADO-120."]
    return ["Evidencia estructural lista para revision QA."]


def _next_steps(missing: list[str]) -> list[str]:
    if missing:
        return ["Seleccionar o crear cliente QA con valores batch completos.", "Re-ejecutar ado120_obligaciones.spec.ts."]
    return ["Revisar evidencia adjunta en ADO."]


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    except Exception:
        return None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--ticket-id", type=int, default=120)
    parser.add_argument(
        "--mode",
        choices=["auto", "dry-run", "publish"],
        default="auto",
        help="dry-run keeps local files only; auto/publish write Stacky handoff artifacts.",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
