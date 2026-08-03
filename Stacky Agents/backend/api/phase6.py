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
from services.project_context import resolve_project_context  # Plan 295 F9
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


# ── Plan 295 F9 — resolución del ticket de un webhook, SIN ambigüedad ────────

def _plan295_autocrear_habilitado() -> bool:
    import config

    return bool(getattr(config.config, "STACKY_WEBHOOK_TICKET_AUTOCREATE_ENABLED", True))


def _ado_id_del_payload(p: dict) -> int:
    """`ticket_ado_id` numérico, o `400` accionable. Antes un valor no numérico
    reventaba en `int()` y salía como 500."""
    crudo = p.get("ticket_ado_id")
    if not crudo:
        abort(400, "ticket_ado_id required")
    try:
        return int(crudo)
    except (TypeError, ValueError):
        abort(400, "ticket_ado_id debe ser numérico")


def _ticket_del_webhook(session, ado_id: int, payload: dict):
    """Plan 295 F9 — resuelve el ticket de un webhook entrante SIN ambigüedad.

    POR QUÉ EXISTE: `filter_by(ado_id=...)` pelado es un bug latente GARANTIZADO en
    GitLab. `ado_id` no es único (models.py:42; el único es la terna
    `(stacky_project_name, tracker_type, external_id)`, models.py:77-83) y en GitLab
    lleva el IID, que se repite entre proyectos (gitlab_sync.py:12-16). Dos proyectos
    GitLab con el issue #42 y el webhook macheaba el del proyecto equivocado -- y el
    DebugAgent corría sobre él.

    Stacky es MONO-OPERADOR: si el payload no nombra el proyecto, el proyecto activo
    es la respuesta correcta y honesta. NO se adivina por `ado_id`.

    Devuelve (ticket|None, ctx|None). NO crea nada: crear es decisión del llamador.
    """
    from sqlalchemy import and_, or_

    from models import Ticket

    # 1. ¿El payload nombra el proyecto? Se aceptan las DOS claves: la nueva,
    #    explícita, y la vieja `project`, que en la práctica trae el tracker_project.
    #    `resolve_project_context` acepta las dos formas (su docstring :381-386).
    nombrado = (payload.get("stacky_project") or payload.get("project") or "").strip() or None
    ctx = resolve_project_context(project_name=nombrado)   # sin nombre => proyecto ACTIVO

    if ctx is None:
        return None, None

    # 2. Filtro por PROYECTO, con la misma tolerancia que _ticket_project_filter
    #    de api/tickets.py:362-371: las filas viejas tienen stacky_project_name NULL
    #    y solo `project` (el tracker_project). Ignorar eso rompería los tickets
    #    ADO históricos, que es exactamente lo que este plan NO puede hacer.
    filtro_proyecto = or_(
        Ticket.stacky_project_name == ctx.stacky_project_name,
        and_(Ticket.stacky_project_name.is_(None), Ticket.project == ctx.tracker_project),
    )
    fila = (
        session.query(Ticket)
        .filter(Ticket.ado_id == ado_id)
        .filter(filtro_proyecto)
        .first()
    )
    return fila, ctx


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
    ado_id = _ado_id_del_payload(p)

    with session_scope() as session:
        t, ctx = _ticket_del_webhook(session, ado_id, p)
        if ctx is None:
            # Plan 295 F9 — sin proyecto resoluble no se puede saber A QUÉ proyecto
            # pertenece este ticket. Crear a ciegas era peor: metía un ticket con
            # project="RSPacifico" HARDCODEADO y sin tracker_type (=> default
            # azure_devops, models.py:49), o sea un ticket ADO sintético dentro de
            # un proyecto GitLab, que después el 286 tiene que adivinar.
            abort(409, "no hay proyecto activo ni el payload nombra uno: no se puede "
                       "resolver a qué proyecto pertenece este ticket")
        if t is None:
            if not _plan295_autocrear_habilitado():
                abort(404, f"no existe el ticket {ado_id} en el proyecto "
                           f"'{ctx.stacky_project_name}'")
            # Placeholder con la IDENTIDAD COMPLETA. Los tres campos que faltaban
            # (stacky_project_name, tracker_type, external_id) son los del índice
            # único de models.py:77-83: sin ellos el upsert del sync crea un DUPLICADO.
            t = Ticket(
                ado_id=ado_id,
                external_id=ado_id,
                project=ctx.tracker_project,
                stacky_project_name=ctx.stacky_project_name,
                tracker_type=ctx.tracker_type,
                title=f"Fallo de CI — ítem {ado_id}",
                ado_state="To Do",
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

    from services.runtime_capabilities import resolve_run_selection
    _sel = resolve_run_selection(runtime="github_copilot", project_name=None)
    eid = agent_runner.run_agent(
        agent_type="debug",
        ticket_id=ticket_id,
        context_blocks=blocks,
        user="ci-bot",
        model_override=_sel["model"],
        effort_override=_sel["effort"],
    )
    return jsonify({"execution_id": eid, "status": "running"})


# ── FA-28 — PR review webhook ────────────────────────────────

@bp.post("/pr/review-webhook")
def pr_review_webhook():
    """Recibe el aviso de una revisión de PR/MR y dispara el agente de revisión.

    Lo disparan Azure DevOps Repos, GitHub o GitLab (Merge Request) cuando un
    revisor menciona a @stacky-bot. Payload: { pr_id, ticket_ado_id, diff,
    description, stacky_project? }.

    `ticket_ado_id` conserva su nombre por compatibilidad con los webhooks ya
    configurados en los servidores del operador: en GitLab lleva el IID del issue.
    Plan 295 F9 — el match es por (ado_id + proyecto), NUNCA por ado_id solo: el iid
    se repite entre proyectos de GitLab.
    """
    import agent_runner

    p = request.get_json(force=True, silent=True) or {}
    ado_id = _ado_id_del_payload(p)

    with session_scope() as session:
        t, ctx = _ticket_del_webhook(session, ado_id, p)
        if ctx is None:
            abort(409, "no hay proyecto activo ni el payload nombra uno")
        if t is None:
            # NO auto-crea: este endpoint nunca lo hizo y no es el momento de empezar.
            abort(404, f"no existe el ticket {ado_id} en el proyecto "
                       f"'{ctx.stacky_project_name}'")
        ticket_id = t.id

    blocks = [
        {"id": "pr-diff", "kind": "auto", "title": f"PR #{p.get('pr_id', '?')} — diff",
         "content": (p.get("diff") or "")[:30000]},
        {"id": "pr-description", "kind": "auto", "title": "PR description",
         "content": p.get("description", "")},
    ]

    from services.runtime_capabilities import resolve_run_selection
    _sel = resolve_run_selection(runtime="github_copilot", project_name=None)
    eid = agent_runner.run_agent(
        agent_type="pr_review",
        ticket_id=ticket_id,
        context_blocks=blocks,
        user="pr-bot",
        model_override=_sel["model"],
        effort_override=_sel["effort"],
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
