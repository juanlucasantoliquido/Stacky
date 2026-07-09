"""api/devops_agent.py — Conversaciones del agente DevOps (Plan 90).

url_prefix="/devops/agent" → rutas /api/devops/agent/... (NO poner /api/ en el
prefix; mismo gotcha C2 del plan 73).
"""
import json

from flask import Blueprint, jsonify, request

import config as _config

bp = Blueprint("devops_agent", __name__, url_prefix="/devops/agent")

_CLI_RUNTIMES = ("claude_code_cli", "codex_cli")
_EFFORTS = {"low", "medium", "high", "xhigh", "max"}
_CONVERSATION_ADO_ID = -2


def _flag_off() -> bool:
    return not getattr(_config.config, "STACKY_DEVOPS_AGENT_ENABLED", False)


def _current_user() -> str:
    # Mismo header sin validar que usa el resto de la app (mono-operador).
    # C2 (v2): importar del ORIGEN canónico api._helpers (api/_helpers.py:4).
    from api._helpers import current_user
    return current_user()


def _chat_meta(ticket) -> dict:
    """Plan 108 F3 — description es JSON {"kind":"devops_chat","server_alias":str}
    o {}. Tolerante (duplicado adrede de api/devops_remote_console.py:_conv_meta
    para no crear import circular devops_agent <-> devops_remote_console)."""
    if not ticket or not ticket.description:
        return {}
    try:
        return json.loads(ticket.description) if isinstance(ticket.description, str) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _validate_remote_target(server_alias: str):
    """Plan 108 F3 — None si OK; (json_response, status) si no. Gates: flag 108
    + servers 91 + consola 105 + alias existente en el registro."""
    cfg = _config.config
    if not getattr(cfg, "STACKY_DEVOPS_REMOTE_TARGET_ENABLED", False):
        return jsonify({"ok": False, "error": "remote_target_disabled"}), 400
    if not getattr(cfg, "STACKY_DEVOPS_SERVERS_ENABLED", False) or \
       not getattr(cfg, "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", False):
        return jsonify({"ok": False, "error": "remote_target_requires_servers_and_console"}), 409
    from services.server_registry import get_server
    try:
        get_server(server_alias)
    except Exception:
        return jsonify({"ok": False, "error": "server_not_found"}), 404
    return None


@bp.post("/conversations")
def start_conversation():
    if _flag_off():
        return jsonify({"error": "devops_agent_disabled"}), 404
    body = request.get_json(silent=True) or {}
    project = (body.get("project") or "").strip()
    message = (body.get("message") or "").strip()
    if not project or not message:
        return jsonify({"ok": False, "error": "project y message son obligatorios"}), 400
    runtime = (body.get("runtime") or "claude_code_cli").strip()
    if runtime not in _CLI_RUNTIMES:
        return jsonify({
            "ok": False,
            "error": "devops_chat_requires_cli_runtime",
            "detail": (
                f"El chat DevOps requiere runtime CLI {_CLI_RUNTIMES}; recibido "
                f"{runtime!r}. Para GitHub Copilot usa el flujo interactivo de "
                "VS Code existente (open_chat)."
            ),
        }), 400

    # Plan 108 F3 — anclaje remoto opt-in: server_alias ausente ⇒ byte-compat total.
    server_alias = (body.get("server_alias") or "").strip() or None
    if server_alias:
        err = _validate_remote_target(server_alias)
        if err:
            return err

    # Cap de modelo SIN Opus (guardarraíl 11).
    from services import llm_router as _llm_router
    model_raw = (body.get("model") or "").strip()
    model_override = _llm_router.clamp_model(model_raw) if model_raw else None
    effort_raw = (body.get("effort") or "").strip().lower()
    effort_override = effort_raw if effort_raw in _EFFORTS else None

    from db import session_scope
    from models import Ticket
    title = f"[Stacky] DevOps Chat — {message[:60]}"
    with session_scope() as session:
        # C1 (v2) + HALLAZGO impl (backfill): la 2ª conversación del mismo proyecto
        # NO puede dejar external_id=NULL, porque db._backfill_multi_project_ticket_columns
        # (db.py:158-196) rellena external_id = COALESCE(external_id, ado_id) en cada
        # init_db() ⇒ dos conversaciones NULL del mismo proyecto terminarían ambas en
        # external_id=-2 y colisionarían en el UNIQUE ux_tickets_stacky_tracker_external
        # (stacky_project_name, tracker_type, external_id). Fix mínimo fiel a la
        # intención del plan (N conversaciones conviven): sellar external_id con un
        # valor negativo ÚNICO por conversación (-ticket.id). Negativo ⇒ nunca choca
        # con ADO ids reales (positivos); único ⇒ nunca choca entre conversaciones; y
        # al no ser NULL, el backfill lo respeta (COALESCE + el continue de db.py:175).
        # Discriminador de identidad sigue siendo ado_id=-2 (sin unique).
        ticket = Ticket(
            ado_id=_CONVERSATION_ADO_ID,
            project=project,
            stacky_project_name=project,
            title=title,
            work_item_type="Task",
            ado_state="Active",
            # Plan 108 F3 — sellar la conversación al servidor (si hay anclaje).
            description=(
                json.dumps({"kind": "devops_chat", "server_alias": server_alias})
                if server_alias else None
            ),
        )
        session.add(ticket)
        session.flush()  # asigna ticket.id
        ticket.external_id = -ticket.id  # único, negativo, no-NULL ⇒ backfill lo respeta
        session.flush()
        conversation_id = ticket.id

    # Plan 108 F3 — envolver con el contrato de consola remota SOLO si hay anclaje.
    if server_alias:
        from services.remote_console_prompt import build_console_prompt
        message = build_console_prompt(
            server_alias, request.host_url.rstrip("/"), message, conversation_id,
            write_enabled=False,
        )

    execution_id, launch_error = _launch_turn(
        conversation_id=conversation_id,
        project=project,
        message=message,
        runtime=runtime,
        model_override=model_override,
        effort_override=effort_override,
    )
    if launch_error is not None:
        return launch_error
    return jsonify({
        "ok": True,
        "conversation_id": conversation_id,
        "execution_id": execution_id,
        "runtime": runtime,
        "server_alias": server_alias,
    }), 202


@bp.post("/conversations/<int:conversation_id>/message")
def send_message(conversation_id: int):
    if _flag_off():
        return jsonify({"error": "devops_agent_disabled"}), 404
    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return jsonify({"ok": False, "error": "message es obligatorio"}), 400

    from db import session_scope
    from models import AgentExecution, Ticket
    with session_scope() as session:
        ticket = session.query(Ticket).filter_by(
            id=conversation_id, ado_id=_CONVERSATION_ADO_ID
        ).first()
        if ticket is None:
            return jsonify({"ok": False, "error": "conversation_not_found"}), 404
        project = ticket.stacky_project_name or ticket.project
        # Plan 108 F3 — server_alias sellado en la conversación (si la tiene).
        server_alias = _chat_meta(ticket).get("server_alias")
        last = (
            session.query(AgentExecution)
            .filter(AgentExecution.ticket_id == conversation_id)
            .filter(AgentExecution.agent_type == "devops")
            .order_by(AgentExecution.id.desc())
            .first()
        )
        last_id = last.id if last is not None else None
        last_status = last.status if last is not None else None
        last_md = dict(last.metadata_dict or {}) if last is not None else {}

    # 1) Camino VIVO: proceso corriendo con stdin abierto → send_input existente.
    if last_id is not None and last_status == "running":
        runtime = last_md.get("runtime")
        try:
            if runtime == "claude_code_cli":
                from services.claude_code_cli_runner import send_input
            else:
                from services.codex_cli_runner import send_input
            result = send_input(last_id, message, user=_current_user())
            return jsonify({
                "ok": True,
                "mode": result.get("mode", "stdin"),
                "execution_id": last_id,
            })
        except (RuntimeError, ValueError):
            pass  # stdin cerrado / sesión no disponible → camino 2

    # 2) Camino DURMIENTE: nuevo run sobre el MISMO ticket. La continuidad la aporta
    #    harness.resume.resolve dentro del runner (--resume / codex exec resume) si
    #    las flags CLAUDE_CODE_CLI_RESUME_* / CODEX_CLI_RESUME_* están ON.
    #    C5 (v2): last_md.get("model_override") es degradación segura si falta la key
    #    (run_agent usa su default capeado, nunca Opus por guardarraíl 11).
    # Plan 108 F3 (C3 v2): conversación sellada + flag 108 OFF ⇒ 409 EXPLÍCITO.
    # NUNCA lanzar el turno sin contrato (degradación silenciosa a ejecución local
    # es EXACTAMENTE el bug que este plan arregla).
    if server_alias:
        if not getattr(_config.config, "STACKY_DEVOPS_REMOTE_TARGET_ENABLED", False):
            return jsonify({
                "ok": False,
                "error": "remote_target_disabled_for_sealed_conversation",
            }), 409
        from services.remote_console_prompt import build_console_prompt
        message = build_console_prompt(
            server_alias, request.host_url.rstrip("/"), message, conversation_id,
            write_enabled=False,
        )

    execution_id, launch_error = _launch_turn(
        conversation_id=conversation_id,
        project=project,
        message=message,
        runtime=last_md.get("runtime") or "claude_code_cli",
        model_override=last_md.get("model_override"),
        effort_override=None,
    )
    if launch_error is not None:
        return launch_error
    return jsonify({"ok": True, "mode": "new_run", "execution_id": execution_id}), 202


@bp.get("/conversations")
def list_conversations():
    if _flag_off():
        return jsonify({"error": "devops_agent_disabled"}), 404
    project = (request.args.get("project") or "").strip() or None

    # C3 (v2): resume_enabled se calcula ANTES del loop para derivar la señal honesta
    # por-conversación. project_enabled con project=None y allowlist no vacía devuelve
    # False (conservador — avisa de más, nunca de menos).
    from config import config as _cfg
    from services.cli_feature_flags import project_enabled
    resume_enabled = project_enabled(
        enabled=getattr(_cfg, "CLAUDE_CODE_CLI_RESUME_ENABLED", False),
        projects_csv=getattr(_cfg, "CLAUDE_CODE_CLI_RESUME_PROJECTS", ""),
        project_name=project,
    )

    from db import session_scope
    from models import AgentExecution, Ticket
    items = []
    with session_scope() as session:
        q = session.query(Ticket).filter(Ticket.ado_id == _CONVERSATION_ADO_ID)
        if project:
            q = q.filter(Ticket.stacky_project_name == project)
        tickets = q.order_by(Ticket.id.desc()).limit(50).all()
        for t in tickets:
            last = (
                session.query(AgentExecution)
                .filter(AgentExecution.ticket_id == t.id)
                .filter(AgentExecution.agent_type == "devops")
                .order_by(AgentExecution.id.desc())
                .first()
            )
            last_status = last.status if last else None
            server_alias_val = _chat_meta(t).get("server_alias")
            item = {
                "conversation_id": t.id,
                "title": t.title,
                "project": t.stacky_project_name,
                "last_execution_id": last.id if last else None,
                "last_status": last_status,
                "last_runtime": (last.metadata_dict or {}).get("runtime") if last else None,
                "started_at": t.created_at.isoformat() if getattr(t, "created_at", None) else None,
                # Plan 108 F3 — servidor al que quedó sellada la conversación (None si no).
                "server_alias": server_alias_val,
                # [ADICIÓN ARQUITECTO v2] Señal HONESTA por-conversación (C3): continuar
                # SOLO conserva el hilo si (a) el resume está activo para el proyecto Y
                # (b) el último turno terminó "completed" (harness/resume.py:96).
                "continuable_with_memory": bool(
                    resume_enabled and last_status == "completed"
                ),
            }
            # [ADICIÓN ARQUITECTO v2] Verificación HITL barata del anclaje: cuántos
            # comandos remotos de ESTA conversación quedaron auditados (Plan 105). Degrada
            # a None si la auditoría falla — el listado JAMÁS se cae por esto. Conversaciones
            # sin alias: la key queda AUSENTE (no aplica).
            if server_alias_val:
                try:
                    from services.remote_exec import read_audit
                    audit_rows = read_audit(server_alias_val, limit=500)
                    item["audited_remote_commands"] = sum(
                        1 for row in audit_rows
                        if row.get("kind") == "exec" and row.get("conversation_id") == t.id
                    )
                except Exception:
                    item["audited_remote_commands"] = None
            items.append(item)

    return jsonify({"conversations": items, "resume_enabled": resume_enabled})


def _launch_turn(
    *,
    conversation_id: int,
    project: str | None,
    message: str,
    runtime: str,
    model_override: str | None,
    effort_override: str | None,
):
    """Lanza un turno como ejecución nueva. Retorna (execution_id, None) o
    (None, respuesta_de_error_flask)."""
    import agent_runner
    context_blocks = [{
        "id": "devops-chat",
        "kind": "raw-conversation",
        "title": "Mensaje del operador (chat DevOps)",
        "content": message,
        "source": {"type": "devops_panel"},
    }]
    try:
        execution_id = agent_runner.run_agent(
            agent_type="devops",
            ticket_id=conversation_id,
            context_blocks=context_blocks,
            user=_current_user(),
            runtime=runtime,
            vscode_agent_filename="DevOpsAgent.agent.md",
            project_name=project,
            use_few_shot=False,
            use_anti_patterns=False,
            model_override=model_override,
            effort_override=effort_override,
            work_item_type="Task",
        )
    except agent_runner.UnknownAgentError:
        return None, (jsonify({"ok": False, "error": "devops_agent_not_registered"}), 500)
    except Exception as exc:  # noqa: BLE001 — patrón run_brief (api/agents.py:782-792)
        return None, (jsonify({
            "ok": False, "error": "agent_launch_failed", "message": str(exc),
        }), 502)

    # Trazabilidad best-effort (patrón plan 53). C4 (v2): la IDENTIDAD de la
    # conversación NO depende de este sello (race con el thread de run_agent).
    # La identidad race-free es (ticket.ado_id == -2) AND (execution.agent_type ==
    # "devops"); devops_chat es solo un flag informativo.
    try:
        from db import session_scope
        from models import AgentExecution
        with session_scope() as s:
            ex = s.get(AgentExecution, execution_id)
            if ex is not None:
                md = dict(ex.metadata_dict or {})
                md["devops_chat"] = True
                md["devops_conversation_ticket_id"] = conversation_id
                ex.metadata_dict = md
    except Exception:
        pass  # trazabilidad opcional, nunca bloquea el turno
    return execution_id, None
