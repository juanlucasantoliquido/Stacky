"""tools/migrar_mantis_gitlab/migrator_mg_report.py — Plan 217 F7b (§14 +
[ADICIÓN ARQUITECTO 2]).

`generate_report` produce el reporte final de una corrida (Markdown y/o
JSON, según `formats`) a partir de `MgVerificationResult`
(`migrator_mg_verify.py`) y `MgExecutionResult` (`migrator_mg_executor.py`).

Redacción de PII (§15 + [ADICIÓN ARQUITECTO 2]): el redact aplica al
**REPORTE** (subproducto que se comparte/adjunta fácilmente), NO a la
migración en sí, que preserva fidelidad de datos por diseño (la migración
real a GitLab escribe nombres/usuarios tal cual, eso es intencional y está
fuera de alcance de este batch — ver §15.2 del plan). El reporte, en
cambio, es el artefacto que este batch SÍ puede proteger sin degradar la
migración.

NOTA DE IMPRECISIÓN DEL PLAN (documentada, no oculta): el batch pide que el
resumen ejecutivo incluya "N comentarios / N adjuntos" desglosados por
separado, pero `MgExecutionResult.applied` (`migrator_mg_executor.py:48-52`)
es un contador COMBINADO de `create_item`+`post_comment`+`upload_attachment`
(cada `_apply_*` hace `result.applied += 1` sin discriminar tipo) — no hay
forma de recuperar el desglose por tipo desde ahí sin tocar
`migrator_mg_executor.py` (prohibido en este batch). Se reporta el total
combinado (documentado como tal en el propio reporte, nunca oculto) más el
desglose por tipo de las FALLAS (`execution.failed` sí trae `op_kind` por
entrada). Para "N relaciones" (tampoco trackeado por `MgExecutionResult`,
ya que `create_issue_link` es una segunda pasada aparte —
`migrator_mg_executor._APPLICABLE_OP_KINDS`—) se agrega el parámetro
opcional `relationships` (shape de `migrator_mg_links.migrate_relationships`),
default `None` -> `[]`, para no inventar un dato que el pipeline no provee
todavía por esta vía.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .migrator_mg_executor import MgExecutionResult
    from .migrator_mg_verify import MgVerificationResult

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

# §6 del plan: información que NO es representable nativamente en GitLab y
# queda documentada como limitación de origen — texto fijo, no se detecta
# dinámicamente (mandato del batch).
_INFO_NO_MIGRADA_FIJA: "list[dict]" = [
    {
        "item": "Autoría real de issues/comentarios",
        "razon": "GitLab asigna el author al dueño del token salvo modo sudo (solo PAT admin)",
        "mitigacion": "modo sudo si hay PAT admin; si no, bloque de metadata '> Autor original (Mantis): {nombre} — {fecha}'",
    },
    {
        "item": "Fecha de creación real (date_submitted)",
        "razon": "created_at vía API pública requiere permisos de administrador de instancia, no garantizado",
        "mitigacion": "se intenta setear si el token lo permite; si no, se conserva en el bloque de metadata",
    },
    {
        "item": "Historial de auditoría completo (bug_history)",
        "razon": "ni Mantis (sin plugin) ni GitLab exponen/aceptan inyectar ese historial estructurado",
        "mitigacion": "se preserva lo que ya narran las notas/bugnotes existentes; si no hay, se declara NO MIGRADO — limitación de origen",
    },
    {
        "item": "Campos personalizados (custom_fields)",
        "razon": "GitLab no tiene campos custom por proyecto para issues estándar (salvo Premium reciente, no garantizado)",
        "mitigacion": "tabla Markdown en bloque '## Campos personalizados (Mantis)' al final de la descripción",
    },
]


def _mask_email_match(match: "re.Match") -> str:
    email = match.group(0)
    local, _, domain = email.partition("@")
    first = local[0] if local else ""
    return f"{first}***@{domain}"


def _mask_emails_in_text(text: str) -> str:
    return _EMAIL_RE.sub(_mask_email_match, text or "")


def _redact_user_fallback_row(row: dict) -> dict:
    """§15 [ADICIÓN 2]: enmascara email (`a***@dominio`) y colapsa
    `full_name` a solo el username (se elimina la columna, el username ya
    está en `mantis_username`/`username`)."""
    out = dict(row)
    if out.get("email"):
        out["email"] = _mask_emails_in_text(out["email"])
    out.pop("full_name", None)
    return out


def _redact_payload(payload: dict) -> dict:
    redacted = dict(payload)
    redacted["users_fallback"] = [_redact_user_fallback_row(r) for r in payload.get("users_fallback", [])]
    return redacted


def _slugify_project_path(project_path: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", (project_path or "").strip("/")) or "proyecto"


def _build_report_payload(
    verification: "MgVerificationResult",
    execution: "MgExecutionResult",
    *,
    run_id: str,
    project_path: str,
    dry_run: bool,
    relationships: list[dict],
) -> dict:
    failed_by_kind: dict[str, int] = {}
    for item in execution.failed:
        kind = item.get("op_kind", "desconocido")
        failed_by_kind[kind] = failed_by_kind.get(kind, 0) + 1

    relationships_by_status: dict[str, int] = {}
    for rel in relationships:
        status = rel.get("status", "desconocido")
        relationships_by_status[status] = relationships_by_status.get(status, 0) + 1

    advertencias_total = (
        len(verification.duplicate_markers)
        + len(verification.sample_mismatches)
        + len(verification.unmapped_fallbacks_used)
        + len(verification.users_fallback)
        + len(verification.attachments_skipped)
    )

    return {
        "run_id": run_id,
        "project_path": project_path,
        "dry_run": dry_run,
        "summary": {
            "issues_migrados": verification.total_migrated,
            "issues_origen": verification.total_origin,
            "gap_conteo": verification.count_gap,
            "operaciones_aplicadas_total": execution.applied,
            "operaciones_salteadas_idempotencia": execution.skipped,
            "operaciones_fallidas_total": len(execution.failed),
            "operaciones_fallidas_por_tipo": failed_by_kind,
            "issues_huerfanos_sin_padre_resuelto": len(execution.orphaned),
            "relaciones_total": len(relationships),
            "relaciones_por_estado": relationships_by_status,
            "advertencias_total": advertencias_total,
            "verificacion_aprobada": verification.passed,
        },
        "unmapped_fallbacks_used": list(verification.unmapped_fallbacks_used),
        "users_fallback": list(verification.users_fallback),
        "attachments_skipped": list(verification.attachments_skipped),
        "duplicate_markers": list(verification.duplicate_markers),
        "sample_mismatches": list(verification.sample_mismatches),
        "info_no_migrada": list(_INFO_NO_MIGRADA_FIJA),
    }


def _render_table(rows: "list[dict]", columns: "list[tuple[str, str]]") -> str:
    if not rows:
        return "_Ninguno._"
    header = "| " + " | ".join(label for _, label in columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| " + " | ".join("" if row.get(key) is None else str(row.get(key)) for key, _ in columns) + " |"
        for row in rows
    ]
    return "\n".join([header, sep, *body])


def _render_users_fallback_table(rows: "list[dict]", *, redact_pii: bool) -> str:
    columns = [("mantis_username", "Usuario Mantis")]
    if not redact_pii:
        columns.append(("full_name", "Nombre completo"))
    columns.append(("email", "Email"))
    columns.append(("fallback", "Fallback aplicado"))
    return _render_table(rows, columns)


def _render_markdown(payload: dict, *, redact_pii: bool) -> str:
    prefix = "[SIMULACRO] " if payload.get("dry_run") else ""
    s = payload["summary"]
    lines = [
        f"# {prefix}Reporte de migración Mantis -> GitLab",
        "",
        f"- **Proyecto destino:** `{payload['project_path']}`",
        f"- **Run ID:** `{payload['run_id']}`",
    ]
    if payload.get("dry_run"):
        lines += [
            "",
            "> **[SIMULACRO]** — corrida en modo dry-run: ninguna escritura real "
            "se realizó contra GitLab (§10 del plan). Este reporte NUNCA debe "
            "confundirse con un resultado real.",
        ]
    lines += [
        "",
        "## Resumen ejecutivo",
        f"- Issues migrados: **{s['issues_migrados']}** / {s['issues_origen']} en origen (gap: {s['gap_conteo']})",
        f"- Operaciones aplicadas (issues+comentarios+adjuntos, contador combinado — "
        f"MgExecutionResult no discrimina por tipo): **{s['operaciones_aplicadas_total']}**",
        f"- Operaciones salteadas por idempotencia: {s['operaciones_salteadas_idempotencia']}",
        f"- Operaciones fallidas: {s['operaciones_fallidas_total']} {s['operaciones_fallidas_por_tipo']}",
        f"- Issues huérfanos (padre no resuelto todavía): {s['issues_huerfanos_sin_padre_resuelto']}",
        f"- Relaciones: {s['relaciones_total']} {s['relaciones_por_estado']}",
        f"- Advertencias totales: {s['advertencias_total']}",
        f"- Verificación (`verify`): {'APROBADA' if s['verificacion_aprobada'] else 'CON HALLAZGOS'}",
        "",
        "## Valores sin mapeo explícito (`_unmapped_fallback` usado)",
        _render_table(
            payload["unmapped_fallbacks_used"],
            [("mantis_issue_id", "Issue Mantis"), ("field", "Campo"), ("value", "Valor original"), ("fallback_used", "Fallback usado")],
        ),
        "",
        "## Usuarios caídos a `default_fallback` (autoría preservada)",
        _render_users_fallback_table(payload["users_fallback"], redact_pii=redact_pii),
        "",
        "## Adjuntos saltados por tamaño",
        _render_table(
            payload["attachments_skipped"],
            [("mantis_issue_id", "Issue Mantis"), ("filename", "Archivo"), ("size_mb", "Tamaño (MB)")],
        ),
        "",
        "## Información NO migrada (limitación de origen, §6 del plan)",
    ]
    for item in payload["info_no_migrada"]:
        lines.append(f"- **{item['item']}**: {item['razon']} -> {item['mitigacion']}")

    lines += ["", "## Markers duplicados detectados (§8.2.2)"]
    if payload["duplicate_markers"]:
        lines += [f"- {m}" for m in payload["duplicate_markers"]]
    else:
        lines.append("_Ninguno._")

    lines += ["", "## Diferencias campo a campo (muestreo de verificación, §8.2.4)"]
    if payload["sample_mismatches"]:
        for mm in payload["sample_mismatches"]:
            lines.append(f"### Issue Mantis {mm['mantis_issue_id']} (GitLab #{mm['gitlab_iid']})")
            for fd in mm["mismatches"]:
                lines.append(f"- `{fd['field']}`: esperado=`{fd['expected']}` vs real=`{fd['actual']}`")
    else:
        lines.append("_Ninguna._")

    lines.append("")
    return "\n".join(lines)


def generate_report(
    verification: "MgVerificationResult",
    execution: "MgExecutionResult",
    *,
    run_id: str,
    project_path: str,
    formats: "list[str]",
    output_dir: str,
    dry_run: bool = False,
    redact_pii: bool = True,
    relationships: "Optional[list[dict]]" = None,
) -> "dict[str, str]":
    """Genera el reporte final (§14 del plan) en los formatos pedidos
    (`"markdown"`/`"json"` en `formats`). Devuelve `{"markdown": ruta,
    "json": ruta}` con solo las claves de los formatos generados."""
    relationships = relationships or []
    reports_dir = Path(output_dir) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    slug = _slugify_project_path(project_path)

    payload = _build_report_payload(
        verification,
        execution,
        run_id=run_id,
        project_path=project_path,
        dry_run=dry_run,
        relationships=relationships,
    )
    if redact_pii:
        payload = _redact_payload(payload)

    paths: dict[str, str] = {}

    if "markdown" in formats:
        md_path = reports_dir / f"{slug}_{run_id}.md"
        md_path.write_text(_render_markdown(payload, redact_pii=redact_pii), encoding="utf-8")
        paths["markdown"] = str(md_path)

    if "json" in formats:
        json_path = reports_dir / f"{slug}_{run_id}.json"
        json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        paths["json"] = str(json_path)

    return paths


__all__ = ["generate_report"]
