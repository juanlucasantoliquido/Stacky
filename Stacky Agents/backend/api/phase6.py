"""
Endpoints fase 6 (cierre del catálogo):
- FA-41 /api/egress/policies
- FA-48 /api/agents/refine        (chain N pasos)
- FA-49 /api/agents/explore       (parallel N variantes)
- FA-51 /api/macros               (CRUD + run)
- FA-29 /api/ci/failure-webhook   (recepción)
- FA-28 /api/pr/review-webhook    (recepción)
- FA-01 /api/retrieval/top-k
- FA-02 /api/live-db/select       (ejecuta SELECT)
- FA-17 /api/typecheck/output     (verifica código del output)
- FA-27 /api/slash/stacky         (slash commands)
"""
from flask import Blueprint, abort, jsonify, request

from db import session_scope
from models import AgentExecution
from services import (
    egress_policies, embeddings, live_db, macros, parallel_runs,
    slash_commands, typecheck,
)
from ._helpers import current_user

bp = Blueprint("phase6", __name__, url_prefix="")


# ── FA-41 — egress policies ──────────────────────────────────

@bp.get("/egress/policies")
def list_egress():
    project = request.args.get("project")
    return jsonify(egress_policies.list_all(project=project))


@bp.post("/egress/policies")
def create_egress():
    p = request.get_json(force=True, silent=True) or {}
    if not p.get("data_class"):
        abort(400, "data_class required")
    pid = egress_policies.create(
        data_class=p["data_class"],
        allowed_llms=p.get("allowed_llms") or [],
        action=p.get("action", "block"),
        project=p.get("project"),
        created_by=current_user(),
    )
    return jsonify({"id": pid}), 201


@bp.delete("/egress/policies/<int:pid>")
def delete_egress(pid: int):
    if not egress_policies.deactivate(pid):
        abort(404)
    return jsonify({"ok": True})


@bp.post("/egress/check")
def check_egress():
    p = request.get_json(force=True, silent=True) or {}
    decision = egress_policies.check(
        project=p.get("project"),
        model=p.get("model", "claude-sonnet-4-6"),
        context_text=p.get("context_text", ""),
    )
    return jsonify(decision.to_dict())


# ── FA-48 — refinement chain ─────────────────────────────────

@bp.post("/agents/refine")
def refine_endpoint():
    p = request.get_json(force=True, silent=True) or {}
    chain = parallel_runs.chain_refinement(
        agent_type=p["agent_type"],
        ticket_id=int(p["ticket_id"]),
        context_blocks=p.get("context_blocks") or [],
        user=current_user(),
        template=p.get("template", "default"),
        custom_prompts=p.get("custom_prompts"),
    )
    return jsonify({
        "execution_ids": chain.execution_ids,
        "prompts": chain.prompts,
        "first_execution_id": chain.final_execution_id,
    })


# ── FA-49 — parallel exploration ─────────────────────────────

@bp.post("/agents/explore")
def explore_endpoint():
    p = request.get_json(force=True, silent=True) or {}
    run = parallel_runs.parallel_explore(
        agent_type=p["agent_type"],
        ticket_id=int(p["ticket_id"]),
        context_blocks=p.get("context_blocks") or [],
        user=current_user(),
        variants=p.get("variants"),
    )
    return jsonify(run.to_dict())


# ── FA-51 — macros DSL ───────────────────────────────────────

@bp.get("/macros")
def list_macros_route():
    project = request.args.get("project")
    return jsonify(macros.list_all(project=project))


@bp.post("/macros")
def create_macro_route():
    p = request.get_json(force=True, silent=True) or {}
    try:
        mid = macros.create(
            slug=p.get("slug") or "",
            name=p.get("name") or "",
            description=p.get("description", ""),
            definition=p.get("definition") or {},
            project=p.get("project"),
            owner=current_user(),
        )
    except ValueError as e:
        abort(400, str(e))
    return jsonify({"id": mid}), 201


@bp.delete("/macros/<int:mid>")
def delete_macro_route(mid: int):
    if not macros.deactivate(mid):
        abort(404)
    return jsonify({"ok": True})


@bp.post("/macros/<int:mid>/run")
def run_macro_route(mid: int):
    p = request.get_json(force=True, silent=True) or {}
    try:
        result = macros.run(
            macro_id=mid,
            ticket_id=int(p["ticket_id"]),
            user=current_user(),
            initial_context=p.get("context_blocks") or [],
        )
    except ValueError as e:
        abort(404, str(e))
    return jsonify(result)


# ── FA-29 — CI failure webhook ───────────────────────────────

@bp.post("/ci/failure-webhook")
def ci_webhook():
    """Recibe payload de CI y dispara el DebugAgent.
    Payload esperado:
      { ticket_ado_id, build_log, commit_sha, failed_tests: [...] }
    """
    import agent_runner
    from models import Ticket

    p = request.get_json(force=True, silent=True) or {}
    ado_id = p.get("ticket_ado_id")
    if not ado_id:
        abort(400, "ticket_ado_id required")

    with session_scope() as session:
        t = session.query(Ticket).filter_by(ado_id=int(ado_id)).first()
        if t is None:
            # Auto-crear ticket placeholder si no existe
            t = Ticket(
                ado_id=int(ado_id), project=p.get("project", "RSPacifico"),
                title=f"CI failure ADO-{ado_id}", ado_state="To Do",
            )
            session.add(t); session.flush()
        ticket_id = t.id

    blocks = [
        {"id": "build-log", "kind": "auto", "title": "Build log",
         "content": (p.get("build_log") or "")[:20000]},
    ]
    if p.get("failed_tests"):
        blocks.append({
            "id": "failed-tests", "kind": "auto", "title": "Tests fallidos",
            "content": "\n".join(f"- {t}" for t in p["failed_tests"]),
        })
    if p.get("commit_sha"):
        blocks.append({
            "id": "commit", "kind": "auto", "title": "Commit",
            "content": f"SHA: {p['commit_sha']}\nDiff:\n{p.get('commit_diff','')[:5000]}",
        })

    eid = agent_runner.run_agent(
        agent_type="debug",
        ticket_id=ticket_id,
        context_blocks=blocks,
        user="ci-bot",
    )
    return jsonify({"execution_id": eid, "status": "running"})


# ── FA-28 — PR review webhook ────────────────────────────────

@bp.post("/pr/review-webhook")
def pr_review_webhook():
    """Triggered by ADO Repos / GitHub when reviewer mentions @stacky-bot.
    Payload: { pr_id, ticket_ado_id, diff, description }
    """
    import agent_runner
    from models import Ticket

    p = request.get_json(force=True, silent=True) or {}
    ado_id = p.get("ticket_ado_id")
    if not ado_id:
        abort(400, "ticket_ado_id required")

    with session_scope() as session:
        t = session.query(Ticket).filter_by(ado_id=int(ado_id)).first()
        if t is None:
            abort(404, f"ticket ADO-{ado_id} not found")
        ticket_id = t.id

    blocks = [
        {"id": "pr-diff", "kind": "auto", "title": f"PR #{p.get('pr_id', '?')} — diff",
         "content": (p.get("diff") or "")[:30000]},
        {"id": "pr-description", "kind": "auto", "title": "PR description",
         "content": p.get("description", "")},
    ]

    eid = agent_runner.run_agent(
        agent_type="pr_review",
        ticket_id=ticket_id,
        context_blocks=blocks,
        user="pr-bot",
    )
    return jsonify({"execution_id": eid, "status": "running"})


# ── FA-01 — retrieval top-k ──────────────────────────────────

@bp.post("/retrieval/top-k")
def retrieval_topk():
    p = request.get_json(force=True, silent=True) or {}
    query = p.get("query") or p.get("query_text") or ""
    if not query:
        abort(400, "query required")
    hits = embeddings.top_k(
        query_text=query,
        agent_type=p.get("agent_type"),
        exclude_ticket_id=p.get("exclude_ticket_id"),
        only_approved=p.get("only_approved", True),
        k=int(p.get("k", 5)),
    )
    return jsonify([h.to_dict() for h in hits])


@bp.post("/retrieval/reindex")
def retrieval_reindex():
    count = embeddings.reindex_all()
    return jsonify({"reindexed": count})


# ── FA-02 — live BD ──────────────────────────────────────────

@bp.post("/live-db/select")
def live_db_select():
    p = request.get_json(force=True, silent=True) or {}
    sql = p.get("sql") or ""
    if not sql:
        abort(400, "sql required")
    result = live_db.execute_select(
        sql=sql,
        project=p.get("project"),
        max_rows=int(p.get("max_rows", 10)),
        apply_pii_mask=p.get("apply_pii_mask", True),
    )
    return jsonify(result.to_dict())


@bp.post("/live-db/block")
def live_db_block():
    p = request.get_json(force=True, silent=True) or {}
    sql = p.get("sql") or ""
    if not sql:
        abort(400, "sql required")
    block = live_db.build_context_block(
        sql=sql, project=p.get("project"), max_rows=int(p.get("max_rows", 10))
    )
    return jsonify(block)


# ── FA-17 — typecheck ────────────────────────────────────────

@bp.post("/typecheck/output")
def typecheck_output():
    p = request.get_json(force=True, silent=True) or {}
    exec_id = p.get("execution_id")
    output = p.get("output", "")
    if exec_id and not output:
        with session_scope() as session:
            row = session.get(AgentExecution, int(exec_id))
            if row is None:
                abort(404)
            output = row.output or ""
    if not output:
        abort(400, "output or execution_id required")
    results = typecheck.check_output(output)
    return jsonify({
        "blocks_checked": len(results),
        "any_failed": any(not r.passed for r in results),
        "results": [r.to_dict() for r in results],
    })


# ── FA-27 — Slack/Teams slash ────────────────────────────────

@bp.post("/slash/stacky")
def slash_endpoint():
    """
    Recibe payload Slack-compatible. Header X-Stacky-Slash-Token = SLASH_TOKEN.
    Body (form): text=<command>, user_name=<sender>
    """
    token = request.headers.get("X-Stacky-Slash-Token")
    if not slash_commands.verify_token(token):
        abort(401, "invalid token")
    text = request.form.get("text") or (
        (request.get_json(silent=True) or {}).get("text", "")
    )
    user = request.form.get("user_name") or "slash-user"
    response = slash_commands.handle(text, user=user)
    return jsonify(response.to_dict())
