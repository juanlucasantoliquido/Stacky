"""api/plans_board.py — Plan 128: tablero de evolución de planes (solo lectura).

`/health` responde siempre 200 (patrón Plan 87) e incluye `next_free_number`
SIN gate de flag (cómputo barato, un solo iterdir()) — ver "[v2 ADICIÓN
ARQUITECTO]" en docs/128_PLAN_TABLERO_EVOLUCION_PLANES.md. `/list` y
`/detail/<n>` sí están gateados por STACKY_PLANS_BOARD_ENABLED (404 con OFF).
"""
from flask import Blueprint, jsonify, request

from config import config

bp = Blueprint("plans_board", __name__, url_prefix="/plans-board")


def _enabled() -> bool:
    return bool(getattr(config, "STACKY_PLANS_BOARD_ENABLED", False))


def _disabled_resp():
    return (
        jsonify(
            {
                "ok": False,
                "error": "plans_board_disabled",
                "message": "El tablero de planes está deshabilitado (STACKY_PLANS_BOARD_ENABLED).",
            }
        ),
        404,
    )


@bp.get("/health")
def plans_board_health():
    # [v2 ADICIÓN ARQUITECTO] next_free_number va SIEMPRE, sin gate de flag: cómputo barato
    # (un iterdir(), sin ledger/git) que cierra el anti-colisión aunque el tablero esté OFF.
    from services import plans_board  # import lazy (patrón Plan 109, api/docs.py:224)

    docs_dir = plans_board.docs_dir_default()
    # Plan 237 F3: el número propuesto saltea los reservados por docs/_roadmap/.
    next_n = plans_board.next_free_number_effective(docs_dir) if docs_dir.exists() else None
    # Plan 237 F7: los duplicados llegan AUNQUE el tablero esté apagado.
    dups = plans_board.plan_number_duplicates(docs_dir) if docs_dir.exists() else []
    return jsonify(
        {
            "ok": True,
            "flag_enabled": _enabled(),
            "next_free_number": next_n,
            "duplicates": dups,
        }
    )


@bp.get("/list")
def plans_board_list():
    if not _enabled():
        return _disabled_resp()
    from services import plans_board  # import lazy (patrón Plan 109, api/docs.py:224)

    refresh = request.args.get("refresh", "").strip() == "1"
    return jsonify(plans_board.get_board_cached(refresh=refresh))


@bp.get("/detail/<int:number>")
def plans_board_detail(number: int):
    if not _enabled():
        return _disabled_resp()
    from services import plans_board

    payload = plans_board.get_detail(number)
    if payload is None:
        return jsonify({"ok": False, "error": "plan_not_found"}), 404
    return jsonify(payload)


# ── Plan 196 — acciones HITL del pipeline de planes (rutas ADITIVAS) ─────────


def _actions_enabled() -> bool:
    return _enabled() and bool(
        getattr(config, "STACKY_PLANS_PIPELINE_ACTIONS_ENABLED", False)
    )


def _actions_disabled_resp():
    return (
        jsonify(
            {
                "ok": False,
                "error": "plans_pipeline_disabled",
                "message": (
                    "Las acciones del pipeline de planes están deshabilitadas "
                    "(STACKY_PLANS_PIPELINE_ACTIONS_ENABLED)."
                ),
            }
        ),
        404,
    )


@bp.post("/actions/run")
def plans_pipeline_run():
    """Plan 196 §4.2 — lanza UNA etapa del pipeline como corrida one-shot
    claude_code_cli. Orden de validación congelado; espejo de
    api/agents.py run_incident para el lanzamiento."""
    if not _actions_enabled():
        return _actions_disabled_resp()

    from services import plans_board, plans_pipeline

    payload = request.get_json(force=True, silent=True) or {}

    runtime_raw = (payload.get("runtime") or "claude_code_cli").strip()
    if runtime_raw != "claude_code_cli":
        return jsonify({
            "ok": False, "error": "runtime_not_supported",
            "supported": ["claude_code_cli"],
        }), 409

    action = (payload.get("action") or "").strip()
    if action not in plans_pipeline._ACTION_COMMANDS:
        return jsonify({"ok": False, "error": "invalid_action"}), 400

    root = plans_board.repo_root()
    if root is None:
        return jsonify({
            "ok": False, "error": "repo_not_available",
            "message": (
                "No hay repo git de Stacky en esta instalación; las acciones "
                "del pipeline requieren el repo de desarrollo."
            ),
        }), 409

    skill_file = plans_pipeline.skill_file_for(action, root)
    if not skill_file.exists():
        return jsonify({
            "ok": False, "error": "skills_not_found",
            "skill": skill_file.parent.name,
        }), 409

    plan_number = payload.get("plan_number")
    plan_number_str: str | None = None
    if action != "proponer":
        try:
            plan_number = int(plan_number)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "plan_not_found"}), 404
        board = plans_board.get_board_cached(refresh=True)
        cards = [c for c in board["plans"] if c["number"] == plan_number]
        if not cards:
            return jsonify({"ok": False, "error": "plan_not_found"}), 404
        card = cards[0]
        ledger_info = card.get("ledger") or {}
        allowed = plans_pipeline.allowed_actions_for(
            card["estado"], ledger_info.get("doc_drift")
        )
        if action not in allowed:
            return jsonify({
                "ok": False, "error": "action_not_allowed_for_estado",
                "estado": card["estado"], "allowed": list(allowed),
            }), 409
        plan_number_str = card["number_str"]
    else:
        plan_number = None

    prompt_line = plans_pipeline.build_action_prompt(
        action, plan_number_str, payload.get("idea")
    )

    # modelo/effort: clamps EXISTENTES (espejo run_incident, api/agents.py)
    from api.agents import _clamp_effort_for_model
    from services import llm_router as _llm_router

    _model_raw = (payload.get("model") or "").strip()
    model_override = _llm_router.clamp_model(_model_raw, allow_opus=True) if _model_raw else None
    _effort_raw = (payload.get("effort") or "").strip().lower()
    effort_override = _effort_raw if _effort_raw in {"low", "medium", "high", "xhigh", "max"} else "high"
    effort_override = _clamp_effort_for_model(effort_override, model_override)

    import agent_runner
    from api._helpers import current_user  # C6 — definición real
    from db import session_scope
    from models import AgentExecution, Ticket
    from services.plans_pipeline_context import ensure_plans_pipeline_agent_file

    ensure_plans_pipeline_agent_file()

    with plans_pipeline._LAUNCH_LOCK:
        running_id = plans_pipeline.find_running_pipeline_execution()
        if running_id is not None:
            return jsonify({
                "ok": False, "error": "pipeline_action_already_running",
                "execution_id": running_id,
            }), 409

        # C9 — pool ticket + lanzamiento bajo el MISMO try: con DB rota
        # responde 502 agent_launch_failed, nunca 500 genérico.
        try:
            with session_scope() as session:
                pool_ticket = (
                    session.query(Ticket)
                    .filter_by(ado_id=plans_pipeline.PLANS_PIPELINE_ADO_ID, project="default")
                    .first()
                )
                if pool_ticket is None:
                    pool_ticket = Ticket(
                        ado_id=plans_pipeline.PLANS_PIPELINE_ADO_ID,
                        external_id=plans_pipeline.PLANS_PIPELINE_ADO_ID,
                        project="default",
                        stacky_project_name="default",
                        title="Plans Pipeline Pool Ticket",
                        work_item_type="Task",
                        ado_state="Active",
                    )
                    session.add(pool_ticket)
                    session.flush()
                pool_ticket_id = pool_ticket.id

            context_blocks = [{
                "id": "plans-pipeline-command",
                "kind": "raw-conversation",
                "title": "Skill del pipeline a ejecutar",
                "content": prompt_line,
                "source": {"type": "plans_board_action", "action": action,
                           "plan_number": plan_number},
            }]

            execution_id = agent_runner.run_agent(
                agent_type="plans_pipeline",
                ticket_id=pool_ticket_id,
                context_blocks=context_blocks,
                user=current_user(),
                runtime="claude_code_cli",
                vscode_agent_filename="PlansPipeline.agent.md",
                project_name=None,
                use_few_shot=False,
                use_anti_patterns=False,
                model_override=model_override,
                effort_override=effort_override,
                workspace_root_override=str(root),
            )
        except Exception as exc:  # noqa: BLE001 — nunca 500 genérico (patrón Plan 39 B1)
            return jsonify({
                "ok": False, "error": "agent_launch_failed", "message": str(exc),
            }), 502

    # metadata best-effort (§4.7) — fuera del lock, nunca bloquea la respuesta
    try:
        with session_scope() as _s:
            _ex = _s.get(AgentExecution, execution_id)
            if _ex is not None:
                _md = dict(_ex.metadata_dict or {})
                _md["plans_pipeline"] = {
                    "action": action, "plan_number": plan_number,
                    "model": model_override, "effort": effort_override,
                    "prompt_line": prompt_line,
                }
                _ex.metadata_dict = _md
    except Exception:  # noqa: BLE001
        pass

    return jsonify({
        "ok": True, "execution_id": execution_id,
        "status": "running", "prompt_line": prompt_line,
    }), 202


@bp.get("/actions/runs")
def plans_pipeline_runs():
    """Plan 196 §4.4 — historial de corridas del pipeline (sin pollers: el
    frontend refresca a demanda)."""
    if not _actions_enabled():
        return _actions_disabled_resp()

    from db import session_scope
    from models import AgentExecution
    from services import plans_pipeline

    try:
        limit = min(max(int(request.args.get("limit", "20")), 1), 50)
    except ValueError:
        limit = 20

    with session_scope() as s:
        rows = (
            s.query(AgentExecution)
            .filter(AgentExecution.agent_type == plans_pipeline.PLANS_PIPELINE_AGENT_TYPE)
            .order_by(AgentExecution.id.desc())
            .limit(limit)
            .all()
        )
        runs = [plans_pipeline.serialize_run(r) for r in rows]

    running_id = plans_pipeline.find_running_pipeline_execution()
    return jsonify({
        "ok": True,
        "busy": running_id is not None,
        "running_execution_id": running_id,
        "working_tree": plans_pipeline.working_tree_status(),
        "runs": runs,
    })


# ── Plan 263 — normalización de estado con evidencia (rutas ADITIVAS) ────────
# `config` YA ES LA INSTANCIA (from config import config, :10): getattr(config,
# "<KEY>", <default>) es el patrón vigente en este módulo — NUNCA repetir el
# nombre del módulo dos veces encadenado (ese patrón es de OTROS módulos que
# hacen `import config` a secas, no de este archivo).


def _normalize_preview_enabled() -> bool:
    # Espejo EXACTO de _actions_enabled() (arriba). Default True: la flag es ON.
    return _enabled() and bool(
        getattr(config, "STACKY_PLANS_NORMALIZE_PREVIEW_ENABLED", True)
    )


def _normalize_apply_enabled() -> bool:
    # Candado 0 (patrón Plan 250, api/pipeline_editor.py): las TRES flags acá, NO
    # se confía en `requires` (metadata para la UI, no la evalúa ningún runner).
    # Esto materializa "APPLY exige PREVIEW". Default False: la flag nace OFF.
    return _normalize_preview_enabled() and bool(
        getattr(config, "STACKY_PLANS_NORMALIZE_APPLY_ENABLED", False)
    )


def _normalize_disabled_resp():
    return (
        jsonify({
            "ok": False,
            "error": "plans_normalize_disabled",
            "message": (
                "La normalización de estados está deshabilitada "
                "(STACKY_PLANS_NORMALIZE_PREVIEW_ENABLED / "
                "STACKY_PLANS_NORMALIZE_APPLY_ENABLED)."
            ),
        }),
        404,
    )


@bp.get("/normalize/preview")          # ruta final: /api/plans-board/normalize/preview
def plans_normalize_preview():
    if not _normalize_preview_enabled():
        return _normalize_disabled_resp()
    from services import plans_board, plans_estado_migration      # import lazy (patrón :36)

    return jsonify(
        plans_estado_migration.preview_estado_migration(plans_board.docs_dir_default())
    )


@bp.post("/normalize/apply")           # ruta final: /api/plans-board/normalize/apply
def plans_normalize_apply():
    if not _normalize_apply_enabled():
        return _normalize_disabled_resp()

    from services import plans_board, plans_estado_migration

    body = request.get_json(force=True, silent=True) or {}

    if body.get("confirm") is not True:
        return jsonify({"ok": False, "error": "confirm_required"}), 400

    items = body.get("items")
    if not isinstance(items, list) or not items:
        return jsonify({"ok": False, "error": "items_required"}), 400
    if any(not isinstance(it, dict) or not it.get("sha256_visto") for it in items):
        return jsonify({"ok": False, "error": "sha256_visto_required"}), 400

    dry_run = bool(body.get("dry_run", False))
    result = plans_estado_migration.apply_estado_migration(
        plans_board.docs_dir_default(), items, dry_run=dry_run
    )
    return jsonify(result)


@bp.get("/commits/<int:number>")
def plans_board_commits(number: int):
    """Plan 196 §4.6 — commits recientes del doc del plan (git log read-only)."""
    if not _enabled():
        return _disabled_resp()

    from services import plans_board, plans_pipeline

    detail = plans_board.get_detail(number)
    if detail is None:
        return jsonify({"ok": False, "error": "plan_not_found"}), 404

    commits = plans_pipeline.recent_commits_for_doc(detail["plan"]["filename"])
    if commits is None:
        return jsonify({"ok": True, "git_available": False, "commits": []})
    return jsonify({"ok": True, "git_available": True, "commits": commits})
