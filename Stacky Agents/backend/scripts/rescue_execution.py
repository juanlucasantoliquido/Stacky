"""
scripts/rescue_execution.py — P0 Rescate de ejecuciones huérfanas.

Cierra una AgentExecution en estado 'running' que quedó huérfana,
publica el HTML asociado en ADO y transiciona el estado del ticket.
Equivalente operacional al gateway agent-completion (P1) con
completion_source='rescue'.

Uso:
    python -m scripts.rescue_execution \\
        --ado-id 149 \\
        --execution-id 44 \\
        --html-path "Agentes/outputs/149/comment.html" \\
        --reason "Rescate EP-013 ejecución huérfana" \\
        --dry-run

    python -m scripts.rescue_execution \\
        --ado-id 149 \\
        --execution-id 44 \\
        --html-path "Agentes/outputs/149/comment.html" \\
        --reason "Rescate EP-013 ejecución huérfana" \\
        --apply --user-email operador@example.com

Flags:
    --dry-run    (default) Imprime el plan completo sin escribir en DB ni ADO.
    --apply      Ejecuta contra DB y ADO reales. Requiere confirmación por stdin.
    --yes        Omite confirmación interactiva (queda registrado en audit).
    --user-email Identidad del operador para trazabilidad en audit.

Salida:
    JSON al stdout (éxito o error con error.code).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

# ── Bootstrap de sys.path ─────────────────────────────────────────────────────
# Permite ejecutar como `python -m scripts.rescue_execution` desde backend/
# o como script directo.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

# ── Constantes ────────────────────────────────────────────────────────────────

ACTIVE_STATUSES = {"running", "queued"}
TERMINAL_STATUS = "completed"
COMPLETION_SOURCE = "rescue"


# ── Resultado tipado ──────────────────────────────────────────────────────────


def _ok(data: dict[str, Any]) -> dict:
    return {"ok": True, **data}


def _err(code: str, message: str, detail: dict | None = None) -> dict:
    r: dict[str, Any] = {"ok": False, "error": {"code": code, "message": message}}
    if detail:
        r["error"]["detail"] = detail
    return r


# ── Pasos del plan ────────────────────────────────────────────────────────────


def _step_validate_html(ado_id: int, html_path: str) -> dict:
    """Paso 1: Validar HTML con agent_html_output.read_and_validate."""
    from services import agent_html_output as html_io

    try:
        output = html_io.read_and_validate(ado_id, hint=html_path or None)
        import hashlib
        sha256 = hashlib.sha256(output.html.encode("utf-8")).hexdigest()
        return {
            "ok": True,
            "path": str(output.path),
            "size_bytes": output.size_bytes,
            "sha256": sha256,
            "meta": output.meta,
        }
    except html_io.ValidationError as exc:
        return {"ok": False, "error_code": exc.code, "error_message": exc.message}


def _step_load_execution(execution_id: int, ado_id: int) -> dict:
    """Paso 2: Cargar AgentExecution y verificar estado/pertenencia."""
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        exec_row = session.get(AgentExecution, execution_id)
        if exec_row is None:
            return {
                "ok": False,
                "error_code": "EXECUTION_NOT_FOUND",
                "error_message": f"AgentExecution id={execution_id} no existe",
            }

        ticket = session.get(Ticket, exec_row.ticket_id)
        if ticket is None:
            return {
                "ok": False,
                "error_code": "TICKET_NOT_FOUND",
                "error_message": f"Ticket id={exec_row.ticket_id} no existe",
            }

        if getattr(ticket, "ado_id", None) != ado_id:
            return {
                "ok": False,
                "error_code": "EXECUTION_ADO_MISMATCH",
                "error_message": (
                    f"AgentExecution {execution_id} pertenece a ticket con ado_id="
                    f"{ticket.ado_id}, no {ado_id}"
                ),
            }

        current_status = exec_row.status
        if current_status not in ACTIVE_STATUSES:
            return {
                "ok": False,
                "error_code": "EXECUTION_STATE_INVALID",
                "error_message": (
                    f"AgentExecution {execution_id} está en estado '{current_status}', "
                    f"se esperaba uno de {sorted(ACTIVE_STATUSES)}"
                ),
                "current_status": current_status,
            }

        return {
            "ok": True,
            "execution_id": exec_row.id,
            "ticket_id": ticket.id,
            "ado_id": ado_id,
            "agent_type": exec_row.agent_type,
            "current_status": current_status,
            "current_html_output_path": exec_row.html_output_path,
            "started_by": exec_row.started_by,
            "started_at": exec_row.started_at.isoformat() if exec_row.started_at else None,
        }


def _step_check_existing_publish(execution_id: int, sha256: str) -> dict:
    """Verificar idempotencia: si ya existe AgentHtmlPublish para esta exec+hash."""
    from db import session_scope
    from services.ado_publisher import AgentHtmlPublish

    with session_scope() as session:
        existing = (
            session.query(AgentHtmlPublish)
            .filter(
                AgentHtmlPublish.execution_id == execution_id,
                AgentHtmlPublish.html_sha256 == sha256,
                AgentHtmlPublish.status == "ok",
            )
            .first()
        )
        if existing is not None:
            return {
                "already_published": True,
                "publish_record_id": existing.id,
                "published_at": existing.published_at.isoformat(),
            }
        return {"already_published": False}


def _step_determine_ado_transition(ticket_id: int, agent_type: str) -> dict:
    """Determinar la transición de estado ADO que se realizará."""
    # En P0 no existe workflow.json (eso es P3). Usamos la lógica actual:
    # on_execution_end → set_status(completed) que actualiza stacky_status.
    # La transición real de ADO state (ej. Active → Resolved) la hace el
    # post_hook de ado_publisher si está registrado, o el agente era quien
    # lo hacía. En P0 actualizamos stacky_status y publicamos el HTML.
    # No modificamos ado_state de ADO en forma adicional — eso es P3.
    return {
        "stacky_status_transition": {
            "from": "running (o cualquier estado activo)",
            "to": "completed",
        },
        "ado_state_transition": {
            "note": (
                "En P0 no se modifica ado_state de ADO directamente. "
                "La publicación del comentario HTML ocurre via publish_from_execution. "
                "La transición declarativa de estado ADO es responsabilidad de P3 (workflow.json)."
            ),
        },
        "ticket_id": ticket_id,
        "agent_type": agent_type,
    }


# ── Dry-run ───────────────────────────────────────────────────────────────────


def run_dry_run(
    ado_id: int,
    execution_id: int,
    html_path: str,
    reason: str,
    user_email: str,
    correlation_id: str,
) -> dict:
    """Genera y devuelve el plan completo sin escribir nada."""
    plan_steps: list[dict] = []
    warnings: list[str] = []

    # Paso 1: Validar HTML
    html_result = _step_validate_html(ado_id, html_path)
    plan_steps.append({
        "step": 1,
        "name": "validate_html",
        "description": f"Validar HTML en '{html_path}' para ADO-{ado_id}",
        "result": html_result,
    })
    if not html_result["ok"]:
        return {
            "ok": False,
            "mode": "dry_run",
            "correlation_id": correlation_id,
            "blocked_at_step": 1,
            "error": {
                "code": html_result["error_code"],
                "message": html_result["error_message"],
            },
            "plan": plan_steps,
        }

    sha256 = html_result["sha256"]

    # Paso 2: Cargar y validar ejecución
    exec_result = _step_load_execution(execution_id, ado_id)
    plan_steps.append({
        "step": 2,
        "name": "load_and_lock_execution",
        "description": (
            f"SELECT AgentExecution id={execution_id} — verificar estado activo "
            f"y pertenencia a ADO-{ado_id}"
        ),
        "result": exec_result,
    })
    if not exec_result["ok"]:
        return {
            "ok": False,
            "mode": "dry_run",
            "correlation_id": correlation_id,
            "blocked_at_step": 2,
            "error": {
                "code": exec_result["error_code"],
                "message": exec_result["error_message"],
            },
            "plan": plan_steps,
        }

    ticket_id = exec_result["ticket_id"]
    agent_type = exec_result["agent_type"]

    # Paso 3: Persistir html_output_path
    plan_steps.append({
        "step": 3,
        "name": "persist_html_output_path",
        "description": (
            f"UPDATE AgentExecution id={execution_id} "
            f"SET html_output_path='{html_path}'"
        ),
        "dry_run": True,
        "would_set": html_path,
    })

    # Paso 4: Cerrar ejecución como completed
    plan_steps.append({
        "step": 4,
        "name": "close_execution",
        "description": (
            f"UPDATE AgentExecution id={execution_id} "
            f"SET status='completed', completed_at=<now>"
        ),
        "dry_run": True,
        "current_status": exec_result["current_status"],
        "target_status": TERMINAL_STATUS,
    })

    # Paso 5: Verificar idempotencia y publicar HTML
    publish_check = _step_check_existing_publish(execution_id, sha256)
    if publish_check["already_published"]:
        warnings.append(
            f"AgentHtmlPublish record_id={publish_check['publish_record_id']} "
            f"ya existe para (execution_id={execution_id}, sha256={sha256[:12]}...). "
            "El --apply hará skip (idempotente, no duplicará el comentario ADO)."
        )
    plan_steps.append({
        "step": 5,
        "name": "publish_from_execution",
        "description": f"ado_publisher.publish_from_execution({execution_id}, triggered_by='rescue')",
        "dry_run": True,
        "html_sha256": sha256,
        "html_path": html_result["path"],
        "html_size_bytes": html_result["size_bytes"],
        "already_published": publish_check["already_published"],
        "would_publish_to_ado_id": ado_id,
        "note": (
            "Si ya_published=True, el publisher hará skip sin republicar. "
            "Si ya_published=False, publicará el comentario HTML en ADO."
        ),
    })

    # Paso 6: on_execution_end → stacky_status transition
    transition = _step_determine_ado_transition(ticket_id, agent_type)
    plan_steps.append({
        "step": 6,
        "name": "on_execution_end",
        "description": (
            f"ticket_status.on_execution_end(ticket_id={ticket_id}, "
            f"execution_id={execution_id}, final_status='completed', "
            f"agent_type='{agent_type}')"
        ),
        "dry_run": True,
        "transition": transition,
    })

    # Paso 7: AuditEntry seal + RescueEvent
    plan_steps.append({
        "step": 7,
        "name": "audit_event",
        "description": (
            f"audit_chain.seal({execution_id}) + "
            f"SystemLog(source='rescue', action='rescue.completed', "
            f"kind='{COMPLETION_SOURCE}')"
        ),
        "dry_run": True,
        "correlation_id": correlation_id,
        "user_email": user_email,
        "reason": reason,
        "completion_source": COMPLETION_SOURCE,
    })

    return {
        "ok": True,
        "mode": "dry_run",
        "correlation_id": correlation_id,
        "ado_id": ado_id,
        "execution_id": execution_id,
        "html_path": html_result["path"],
        "html_sha256": sha256,
        "ticket_id": ticket_id,
        "agent_type": agent_type,
        "warnings": warnings,
        "plan": plan_steps,
        "human_action_required": (
            "Revisar el plan anterior y ejecutar con --apply para aplicar el rescate."
        ),
    }


# ── Apply ─────────────────────────────────────────────────────────────────────


def run_apply(
    ado_id: int,
    execution_id: int,
    html_path: str,
    reason: str,
    user_email: str,
    correlation_id: str,
    confirmed_via_stdin: bool,
) -> dict:
    """Ejecuta el rescate contra DB y ADO reales."""
    steps_executed: list[dict] = []
    now = datetime.utcnow()

    # ── 1. Validar HTML ───────────────────────────────────────────────────────
    html_result = _step_validate_html(ado_id, html_path)
    steps_executed.append({"step": 1, "name": "validate_html", "result": html_result})
    if not html_result["ok"]:
        return _err(
            html_result["error_code"],
            html_result["error_message"],
            detail={"step": 1, "steps_executed": steps_executed},
        )

    sha256 = html_result["sha256"]

    # ── 2. Cargar ejecución ───────────────────────────────────────────────────
    exec_result = _step_load_execution(execution_id, ado_id)
    steps_executed.append({"step": 2, "name": "load_execution", "result": exec_result})
    if not exec_result["ok"]:
        return _err(
            exec_result["error_code"],
            exec_result["error_message"],
            detail={"step": 2, "steps_executed": steps_executed},
        )

    ticket_id = exec_result["ticket_id"]
    agent_type = exec_result["agent_type"]

    # ── 3+4. SELECT FOR UPDATE + persistir html_output_path + cerrar ejecución ─
    # SQLite no soporta FOR UPDATE literal, pero la transacción única + WAL
    # garantiza atomicidad en el contexto de este script de rescate.
    try:
        from db import session_scope
        from models import AgentExecution

        with session_scope() as session:
            exec_row = session.get(AgentExecution, execution_id)
            if exec_row is None:
                return _err(
                    "EXECUTION_DISAPPEARED",
                    f"AgentExecution {execution_id} desapareció entre validación y apply",
                )

            # Re-verificar estado (puede haber cambiado entre dry-run y apply)
            if exec_row.status not in ACTIVE_STATUSES:
                return _err(
                    "EXECUTION_STATE_CHANGED",
                    (
                        f"AgentExecution {execution_id} ya no está en estado activo: "
                        f"'{exec_row.status}'. Posiblemente ya fue cerrada."
                    ),
                    detail={"current_status": exec_row.status},
                )

            # Paso 3: persistir html_output_path
            exec_row.html_output_path = html_path
            steps_executed.append({
                "step": 3,
                "name": "persist_html_output_path",
                "set": html_path,
                "ok": True,
            })

            # Paso 4: cerrar ejecución
            exec_row.status = TERMINAL_STATUS
            exec_row.completed_at = now
            steps_executed.append({
                "step": 4,
                "name": "close_execution",
                "status_set": TERMINAL_STATUS,
                "completed_at": now.isoformat(),
                "ok": True,
            })
            # La sesión hace commit al salir del with

    except Exception as exc:
        return _err(
            "DB_ERROR",
            f"Error al cerrar ejecución: {type(exc).__name__}: {exc}",
            detail={"step": "3-4", "steps_executed": steps_executed},
        )

    # ── 5. publish_from_execution ─────────────────────────────────────────────
    try:
        from services.ado_publisher import publish_from_execution
        pub_result = publish_from_execution(
            execution_id,
            triggered_by=COMPLETION_SOURCE,
        )
        steps_executed.append({
            "step": 5,
            "name": "publish_from_execution",
            "ok": pub_result.ok,
            "status": pub_result.status,
            "reason": pub_result.reason,
            "html_sha256": pub_result.html_sha256,
            "ado_id": pub_result.ado_id,
            "record_id": pub_result.record_id,
        })
        if not pub_result.ok:
            # La ejecución ya se cerró en DB. La publicación falló pero no
            # revertimos — el estado correcto en DB permite reintentar.
            return _err(
                "PUBLISH_FAILED",
                f"Ejecución cerrada pero publicación falló: {pub_result.reason}",
                detail={"step": 5, "publish_result": pub_result.reason,
                        "steps_executed": steps_executed,
                        "note": (
                            "La ejecución quedó cerrada en DB. "
                            "Reintentar publicación con el publisher directamente."
                        )},
            )
    except Exception as exc:
        return _err(
            "PUBLISH_ERROR",
            f"Excepción al publicar: {type(exc).__name__}: {exc}",
            detail={"step": 5, "steps_executed": steps_executed},
        )

    # ── 6. on_execution_end → transición stacky_status ───────────────────────
    try:
        from services import ticket_status as ts
        ts.on_execution_end(
            ticket_id=ticket_id,
            execution_id=execution_id,
            final_status=TERMINAL_STATUS,
            agent_type=agent_type,
        )
        steps_executed.append({
            "step": 6,
            "name": "on_execution_end",
            "ticket_id": ticket_id,
            "final_status": TERMINAL_STATUS,
            "agent_type": agent_type,
            "ok": True,
        })
    except Exception as exc:
        # No fatal: la ejecución y publicación ya se completaron.
        steps_executed.append({
            "step": 6,
            "name": "on_execution_end",
            "ok": False,
            "warning": f"on_execution_end falló (no crítico): {exc}",
        })

    # ── 7. AuditEntry (seal) + RescueEvent en SystemLog ──────────────────────
    audit_node_hash: str | None = None
    try:
        from services.audit_chain import seal as audit_seal
        audit_node_hash = audit_seal(execution_id)
        steps_executed.append({
            "step": 7,
            "name": "audit_chain_seal",
            "node_hash": audit_node_hash,
            "ok": True,
        })
    except Exception as exc:
        steps_executed.append({
            "step": 7,
            "name": "audit_chain_seal",
            "ok": False,
            "warning": f"audit_chain.seal falló (no crítico): {exc}",
        })

    # Evento de rescate en SystemLog
    try:
        from db import session_scope
        from models import SystemLog
        import json as _json

        with session_scope() as session:
            rescue_event = SystemLog(
                level="INFO",
                source="rescue_execution",
                action="rescue.completed",
                execution_id=execution_id,
                ticket_id=ticket_id,
                user=user_email,
                request_id=correlation_id,
                context_json=_json.dumps({
                    "ado_id": ado_id,
                    "kind": COMPLETION_SOURCE,
                    "reason": reason,
                    "html_path": html_path,
                    "html_sha256": sha256,
                    "confirmed_via_stdin": confirmed_via_stdin,
                    "completion_source": COMPLETION_SOURCE,
                    "publish_status": pub_result.status,
                    "publish_record_id": pub_result.record_id,
                    "audit_node_hash": audit_node_hash,
                }, ensure_ascii=False),
                tags_json=_json.dumps(["rescue", "p0", COMPLETION_SOURCE]),
            )
            session.add(rescue_event)
        steps_executed.append({
            "step": 7,
            "name": "rescue_audit_event",
            "kind": COMPLETION_SOURCE,
            "user_email": user_email,
            "correlation_id": correlation_id,
            "ok": True,
        })
    except Exception as exc:
        steps_executed.append({
            "step": 7,
            "name": "rescue_audit_event",
            "ok": False,
            "warning": f"SystemLog rescue event falló (no crítico): {exc}",
        })

    # ── Resultado final ───────────────────────────────────────────────────────
    return _ok({
        "mode": "apply",
        "correlation_id": correlation_id,
        "ado_id": ado_id,
        "execution_id": execution_id,
        "ticket_id": ticket_id,
        "agent_type": agent_type,
        "execution_status_now": TERMINAL_STATUS,
        "completed_at": now.isoformat(),
        "html_sha256": sha256,
        "publish_status": pub_result.status,
        "publish_record_id": pub_result.record_id,
        "audit_node_hash": audit_node_hash,
        "completion_source": COMPLETION_SOURCE,
        "user_email": user_email,
        "reason": reason,
        "steps_executed": steps_executed,
    })


# ── CLI ───────────────────────────────────────────────────────────────────────


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="rescue_execution",
        description="Rescata una AgentExecution huérfana: cierra, publica en ADO y audita.",
    )
    parser.add_argument("--ado-id", type=int, required=True, help="ADO work item ID")
    parser.add_argument("--execution-id", type=int, required=True, help="AgentExecution.id")
    parser.add_argument(
        "--html-path",
        default="",
        help="Path relativo al repo root del HTML (default: convención canónica)",
    )
    parser.add_argument("--reason", default="Rescate manual de ejecución huérfana")
    parser.add_argument(
        "--user-email",
        default=os.getenv("STACKY_USER_EMAIL", "operador@stacky"),
        help="Email del operador para trazabilidad",
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="(default) Imprime el plan sin escribir nada",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Ejecuta el rescate contra DB y ADO reales",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        default=False,
        help="Omite confirmación interactiva (requiere --apply)",
    )

    args = parser.parse_args(argv)

    # Si se pasó --apply, dry_run debe ser False
    if args.apply:
        args.dry_run = False
    else:
        args.dry_run = True

    return args


def _confirm_apply(ado_id: int, execution_id: int) -> bool:
    """Solicita confirmación explícita por stdin. Retorna True si confirmado."""
    expected = f"APLICAR ADO-{ado_id}"
    print(
        f"\n[RESCUE] Vas a ejecutar --apply sobre ADO-{ado_id} / execution_id={execution_id}.",
        file=sys.stderr,
    )
    print(
        f"[RESCUE] Esto escribirá en la base de datos y publicará en ADO REAL.",
        file=sys.stderr,
    )
    print(
        f"[RESCUE] Escribe '{expected}' para confirmar (o cualquier otra cosa para cancelar):",
        file=sys.stderr,
    )
    try:
        response = input().strip()
    except (EOFError, KeyboardInterrupt):
        return False
    return response == expected


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada principal. Devuelve exit code."""
    args = _parse_args(argv)
    correlation_id = str(uuid.uuid4())

    # Configurar DATABASE_URL si no está seteada
    os.environ.setdefault("DATABASE_URL", "sqlite:///data/stacky_agents.db")

    # Inicializar DB
    try:
        from db import init_db
        init_db()
    except Exception as exc:
        result = _err("DB_INIT_ERROR", f"No se pudo inicializar la DB: {exc}")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1

    if args.dry_run:
        result = run_dry_run(
            ado_id=args.ado_id,
            execution_id=args.execution_id,
            html_path=args.html_path,
            reason=args.reason,
            user_email=args.user_email,
            correlation_id=correlation_id,
        )
    else:
        # --apply: confirmar salvo --yes
        confirmed_via_stdin = False
        if not args.yes:
            if not _confirm_apply(args.ado_id, args.execution_id):
                result = _err(
                    "APPLY_CANCELLED",
                    "Aplicación cancelada por el operador (confirmación no recibida)",
                )
                print(json.dumps(result, indent=2, ensure_ascii=False))
                return 1
            confirmed_via_stdin = True
        else:
            print(
                f"[RESCUE] --yes pasado: omitiendo confirmación interactiva "
                f"(queda registrado en AuditEvent).",
                file=sys.stderr,
            )

        result = run_apply(
            ado_id=args.ado_id,
            execution_id=args.execution_id,
            html_path=args.html_path,
            reason=args.reason,
            user_email=args.user_email,
            correlation_id=correlation_id,
            confirmed_via_stdin=confirmed_via_stdin,
        )

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
