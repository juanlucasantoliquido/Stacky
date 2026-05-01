"""
Endpoints de Fase 5:
- FA-36  POST /api/agents/speculate, GET /api/agents/speculate/:id, DELETE ...
- FA-47  POST /api/executions/:id/critique
- FA-40  POST /api/admin/erase (GDPR right-to-be-forgotten)
- FA-39  GET /api/audit/:ticket_id/chain, POST /api/audit/:exec_id/seal
- FA-08  CRUD /api/constraints
- FA-10  GET/POST /api/users/:email/style-profile
"""
from flask import Blueprint, abort, jsonify, request

from db import session_scope
from models import AgentExecution
from services import audit_chain, constraints, speculative, style_memory
from ._helpers import current_user

bp = Blueprint("phase5", __name__, url_prefix="")


# ── FA-36 — speculative pre-execution ───────────────────────

@bp.post("/agents/speculate")
def speculate():
    p = request.get_json(force=True, silent=True) or {}
    agent_type = p.get("agent_type")
    ticket_id = p.get("ticket_id")
    context_blocks = p.get("context_blocks") or []
    if not agent_type or not ticket_id:
        abort(400, "agent_type and ticket_id required")
    spec_id = speculative.start(
        agent_type=agent_type,
        ticket_id=int(ticket_id),
        context_blocks=context_blocks,
        started_by=current_user(),
    )
    return jsonify({"spec_id": spec_id, "status": "running"})


@bp.get("/agents/speculate/<int:spec_id>")
def get_spec(spec_id: int):
    result = speculative.get(spec_id)
    if result is None:
        abort(404)
    return jsonify(result)


@bp.delete("/agents/speculate/<int:spec_id>")
def cancel_spec(spec_id: int):
    speculative.cancel(spec_id)
    return jsonify({"ok": True})


@bp.post("/agents/speculate/claim")
def claim_spec():
    """Intenta reclamar un spec completado con el mismo context hash."""
    p = request.get_json(force=True, silent=True) or {}
    agent_type = p.get("agent_type")
    context_blocks = p.get("context_blocks") or []
    if not agent_type:
        abort(400)
    result = speculative.claim(agent_type=agent_type, context_blocks=context_blocks)
    return jsonify({"found": result is not None, "spec": result})


# ── FA-47 — critique ─────────────────────────────────────────

@bp.post("/executions/<int:exec_id>/critique")
def critique(exec_id: int):
    from agents.critic import CriticAgent

    with session_scope() as session:
        row = session.get(AgentExecution, exec_id)
        if row is None:
            abort(404)
        output = row.output or ""

    if not output:
        abort(400, "execution has no output to critique")

    critic = CriticAgent()
    critique_blocks = [
        {"id": "output-to-critique", "kind": "auto",
         "title": "Output a revisar", "content": output}
    ]

    def noop(*a, **k): pass

    result = critic.run(critique_blocks, log=noop)
    return jsonify({
        "execution_id": exec_id,
        "critique": result.output,
        "output_format": result.output_format,
    })


# ── FA-39 — audit chain ──────────────────────────────────────

@bp.get("/audit/<int:ticket_id>/chain")
def verify_audit_chain(ticket_id: int):
    result = audit_chain.verify_chain(ticket_id)
    return jsonify(result.to_dict())


@bp.post("/audit/<int:exec_id>/seal")
def seal_audit(exec_id: int):
    node_hash = audit_chain.seal(exec_id)
    if node_hash is None:
        abort(404, "execution not found")
    return jsonify({"execution_id": exec_id, "node_hash": node_hash})


# ── FA-40 — GDPR right-to-be-forgotten ──────────────────────

@bp.post("/admin/erase")
def erase_pii():
    """
    Enmascara PII en outputs históricos para un user_email o customer keyword.
    Preserva estructura. Registra la operación.
    """
    p = request.get_json(force=True, silent=True) or {}
    target = p.get("user_email") or p.get("customer_keyword")
    if not target:
        abort(400, "user_email or customer_keyword required")

    import re
    from services import pii_masker

    erased_count = 0
    with session_scope() as session:
        # Solo ejecutar en execs del user si es email
        q = session.query(AgentExecution)
        if "@" in target:
            q = q.filter(AgentExecution.started_by == target)
        rows = q.filter(AgentExecution.output.isnot(None)).all()
        for row in rows:
            output = row.output or ""
            masked, mp = pii_masker.mask_text(output)
            if mp:
                row.output = masked
                erased_count += 1

    return jsonify({
        "ok": True,
        "target": target,
        "executions_redacted": erased_count,
        "erased_at": __import__("datetime").datetime.utcnow().isoformat(),
    })


# ── FA-08 — project constraints ──────────────────────────────

@bp.get("/constraints")
def list_constraints():
    project = request.args.get("project")
    return jsonify(constraints.list_all(project=project))


@bp.post("/constraints")
def create_constraint():
    p = request.get_json(force=True, silent=True) or {}
    trigger = p.get("trigger_keywords") or []
    text = p.get("constraint_text") or ""
    if not trigger or not text:
        abort(400, "trigger_keywords and constraint_text required")
    cid = constraints.create(
        project=p.get("project"),
        trigger_keywords=trigger if isinstance(trigger, list) else [trigger],
        constraint_text=text,
        agent_types=p.get("agent_types"),
        priority=int(p.get("priority", 5)),
        created_by=current_user(),
    )
    return jsonify({"id": cid}), 201


@bp.delete("/constraints/<int:cid>")
def deactivate_constraint(cid: int):
    if not constraints.deactivate(cid):
        abort(404)
    return jsonify({"ok": True})


# ── FA-10 — personal style profile ───────────────────────────

@bp.get("/users/<user_email>/style-profile")
def get_style_profile(user_email: str):
    from services.style_memory import get_profile
    agent_type = request.args.get("agent_type", "technical")
    p = get_profile(user_email, agent_type)
    if p is None:
        return jsonify(None)
    return jsonify(p.to_dict())


@bp.post("/users/<user_email>/style-profile/compute")
def compute_style_profile(user_email: str):
    agent_type = (request.get_json(silent=True) or {}).get("agent_type", "technical")
    result = style_memory.compute_profile(user_email, agent_type)
    if result is None:
        return jsonify({"ok": False, "reason": "not enough approved outputs (need >= 3)"})
    return jsonify({"ok": True, "profile": result})


# ── FA-18 — auto-execute SELECTs del output ──────────────────

@bp.post("/executions/<int:exec_id>/run-selects")
def run_selects(exec_id: int):
    """
    Detecta bloques ```sql en el output y los ejecuta en modo read-only
    contra la BD de proyecto (si está configurada). Devuelve resultados inline.
    En modo mock devuelve filas dummy.
    """
    import re
    from config import config

    with session_scope() as session:
        row = session.get(AgentExecution, exec_id)
        if row is None:
            abort(404)
        output = row.output or ""

    sql_blocks = re.findall(r"```sql\n([\s\S]*?)```", output, re.IGNORECASE)
    if not sql_blocks:
        return jsonify({"queries": [], "message": "No SQL blocks found in output."})

    results: list[dict] = []
    for i, sql in enumerate(sql_blocks[:5]):  # max 5
        sql_clean = sql.strip()
        # Solo SELECT
        if not re.match(r"^\s*(SELECT|WITH)\s", sql_clean, re.IGNORECASE):
            results.append({"index": i, "sql": sql_clean[:200], "error": "only SELECT allowed"})
            continue

        if config.LLM_BACKEND == "mock":
            results.append({
                "index": i,
                "sql": sql_clean[:200],
                "rows": [{"col1": "mock_value_1", "col2": 42},
                         {"col1": "mock_value_2", "col2": 99}],
                "row_count": 2,
                "from_mock": True,
            })
        else:
            # Producción: conectar al proyecto DB (configurable en project settings)
            results.append({
                "index": i,
                "sql": sql_clean[:200],
                "error": "Project DB not configured (set PROJECT_DB_URL in settings)",
            })

    return jsonify({"queries": results, "total_found": len(sql_blocks)})
