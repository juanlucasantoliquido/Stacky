"""C17 — Audit-grade PDF export para una ejecución.

Genera un documento autocontenido con header (proyecto, ticket, agente, modelo,
timestamp, hash HMAC), prompt + output, y citaciones.

Estrategia "graceful":
  - Si `reportlab` está disponible, se renderiza PDF "de verdad".
  - Si no, se devuelve un HTML que el browser puede imprimir a PDF con Ctrl+P,
    para no introducir dependencia obligatoria en el deployment.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import json
import logging
import os
from datetime import datetime
from io import BytesIO
from pathlib import Path

logger = logging.getLogger("stacky.pdf_export")


def _execution_hash(execution_id: int, output: str | None) -> str:
    secret = os.getenv("STACKY_AUDIT_HMAC_KEY", "stacky-default-not-secure").encode()
    payload = f"{execution_id}|{output or ''}".encode()
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()[:16]


def _gather(execution_id: int) -> dict:
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        ex = session.get(AgentExecution, execution_id)
        if ex is None:
            raise ValueError(f"execution {execution_id} not found")
        ticket = session.get(Ticket, ex.ticket_id) if ex.ticket_id else None
        try:
            meta = json.loads(ex.metadata_json) if ex.metadata_json else {}
        except Exception:
            meta = {}
        try:
            ctx_blocks = json.loads(ex.input_context_json) if ex.input_context_json else []
        except Exception:
            ctx_blocks = []
        return {
            "execution_id": ex.id,
            "agent_type": ex.agent_type,
            "status": ex.status,
            "verdict": ex.verdict,
            "started_at": ex.started_at.isoformat() if ex.started_at else None,
            "completed_at": ex.completed_at.isoformat() if ex.completed_at else None,
            "started_by": ex.started_by,
            "output": ex.output or "",
            "metadata": meta,
            "context_blocks": ctx_blocks,
            "ticket": (
                {
                    "ado_id": ticket.ado_id,
                    "title": ticket.title,
                    "project": ticket.project,
                    "ado_state": ticket.ado_state,
                }
                if ticket
                else None
            ),
        }


def _html_template(data: dict, signature: str) -> str:
    ticket = data["ticket"] or {}
    sources_html = "".join(
        f"<li>{html.escape(str(b.get('kind') or 'context'))}: "
        f"{html.escape(str(b.get('label') or b.get('source') or '')[:200])}</li>"
        for b in data["context_blocks"]
        if isinstance(b, dict)
    ) or "<li>(no se registraron fuentes)</li>"

    meta = data["metadata"] or {}
    model = meta.get("model") or (meta.get("routing_decision", {}) or {}).get("model") or "—"

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Stacky Audit — Exec #{data['execution_id']}</title>
<style>
  body {{ font-family: Georgia, serif; max-width: 720px; margin: 32px auto; padding: 0 20px; color: #222; }}
  h1, h2 {{ font-family: Helvetica, Arial, sans-serif; }}
  .meta {{ background: #f6f6f6; padding: 14px 18px; border-radius: 4px; font-size: 13px; }}
  .meta dt {{ font-weight: 700; display: inline-block; min-width: 110px; }}
  pre {{ background: #f1f1f1; padding: 12px; border-radius: 4px; white-space: pre-wrap; font-size: 12px; }}
  hr {{ border: none; border-top: 1px solid #ccc; margin: 24px 0; }}
  .hash {{ font-family: monospace; font-size: 11px; color: #666; }}
</style>
</head>
<body>
  <h1>Stacky Agents — Audit Record</h1>
  <div class="meta">
    <p><dt>Proyecto:</dt> {html.escape(str(ticket.get('project') or '—'))}</p>
    <p><dt>Ticket:</dt> T-{html.escape(str(ticket.get('ado_id') or '—'))} — {html.escape(str(ticket.get('title') or ''))}</p>
    <p><dt>Agente:</dt> {html.escape(data['agent_type'])}</p>
    <p><dt>Modelo:</dt> {html.escape(str(model))}</p>
    <p><dt>Estado:</dt> {html.escape(str(data['status']))}{(" / verdict=" + html.escape(str(data['verdict']))) if data['verdict'] else ""}</p>
    <p><dt>Inició:</dt> {html.escape(str(data['started_at'] or '—'))}</p>
    <p><dt>Terminó:</dt> {html.escape(str(data['completed_at'] or '—'))}</p>
    <p><dt>Operador:</dt> {html.escape(str(data['started_by']))}</p>
    <p><dt>Hash HMAC:</dt> <span class="hash">{signature}</span></p>
  </div>

  <hr/>
  <h2>Output del agente</h2>
  <pre>{html.escape(data['output'])}</pre>

  <hr/>
  <h2>Fuentes citadas</h2>
  <ul>{sources_html}</ul>

  <hr/>
  <p style="font-size: 11px; color: #777;">
    Documento generado por Stacky Agents · {datetime.utcnow().isoformat()}Z<br>
    El hash HMAC permite verificar la integridad de este registro contra la cadena de auditoría
    almacenada en la instancia local.
  </p>
</body>
</html>
"""


def export_execution_pdf(execution_id: int) -> tuple[bytes, str, str]:
    """Devuelve (bytes, mime_type, suggested_filename)."""
    data = _gather(execution_id)
    signature = _execution_hash(execution_id, data["output"])

    try:
        from reportlab.lib.pagesizes import A4  # type: ignore
        from reportlab.lib.styles import getSampleStyleSheet  # type: ignore
        from reportlab.platypus import (  # type: ignore
            SimpleDocTemplate, Paragraph, Spacer, Preformatted, PageBreak,
        )
    except ImportError:
        # Fallback: HTML imprimible.
        html_str = _html_template(data, signature)
        return (
            html_str.encode("utf-8"),
            "text/html",
            f"stacky-audit-{execution_id}.html",
        )

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=f"Stacky Audit #{execution_id}")
    styles = getSampleStyleSheet()
    flow = [
        Paragraph(f"<b>Stacky Agents — Audit Record</b>", styles["Title"]),
        Spacer(1, 12),
        Paragraph(
            f"<b>Proyecto:</b> {html.escape(str((data['ticket'] or {}).get('project') or '—'))}",
            styles["Normal"],
        ),
        Paragraph(
            f"<b>Ticket:</b> T-{(data['ticket'] or {}).get('ado_id') or '—'} — "
            f"{html.escape(str((data['ticket'] or {}).get('title') or ''))}",
            styles["Normal"],
        ),
        Paragraph(f"<b>Agente:</b> {html.escape(data['agent_type'])}", styles["Normal"]),
        Paragraph(f"<b>Operador:</b> {html.escape(str(data['started_by']))}", styles["Normal"]),
        Paragraph(f"<b>Inicio:</b> {data['started_at'] or '—'}", styles["Normal"]),
        Paragraph(f"<b>Fin:</b> {data['completed_at'] or '—'}", styles["Normal"]),
        Paragraph(f"<b>Hash:</b> {signature}", styles["Normal"]),
        Spacer(1, 12),
        Paragraph("<b>Output</b>", styles["Heading3"]),
        Preformatted(data["output"][:20_000] or "(sin output)", styles["Code"]),
    ]
    doc.build(flow)
    return buf.getvalue(), "application/pdf", f"stacky-audit-{execution_id}.pdf"
