"""
api/docs.py — Blueprint Flask para /api/docs (Feature #3 DocTree)
=================================================================

Endpoints:
    GET /api/docs/sources → fuentes docs seleccionables
    GET /api/docs/index   → árbol indexado de documentos
    GET /api/docs/content?path=<relpath> → contenido raw de un documento

Seguridad: path traversal bloqueado en doc_indexer.read_content().
Cache: 5 min en memoria (TTL gestionado por doc_indexer).

Observabilidad (stacky_logger):
    docs_index_built     — cuando se construye el índice (no desde cache)
    docs_content_served  — cuando se sirve contenido
    docs_path_traversal_blocked — cuando se bloquea un path sospechoso
"""
from __future__ import annotations

import time

from flask import Blueprint, jsonify, request

from services import doc_indexer
from services.stacky_logger import logger
from config import config

bp = Blueprint("docs", __name__, url_prefix="/docs")


def _get_vscode_prompts_dir() -> str | None:
    """Lee VSCODE_PROMPTS_DIR desde config (puede estar vacío o no configurado)."""
    val = getattr(config, "VSCODE_PROMPTS_DIR", None)
    return val if val else None


def _get_project_param() -> str | None:
    project = request.args.get("project", "").strip()
    return project or None


def _get_source_param() -> str:
    return request.args.get("source_id", "").strip() or doc_indexer.STACKY_SOURCE_ID


def _is_project_source(source_id: str) -> bool:
    return source_id.startswith(doc_indexer.PROJECT_DOC_SOURCE_PREFIX)


# ── GET /api/docs/sources ─────────────────────────────────────────────────────

@bp.get("/sources")
def get_doc_sources():
    """
    Devuelve las fuentes de documentación seleccionables para el proyecto activo.
    """
    payload = doc_indexer.list_doc_sources(project_name=_get_project_param())
    payload["graph_enabled"] = bool(getattr(config, "STACKY_DOCS_GRAPH_ENABLED", False))  # Plan 109
    payload["documenter_enabled"] = bool(getattr(config, "STACKY_DOCS_DOCUMENTER_ENABLED", False))  # Plan 113
    payload["staleness_enabled"] = bool(getattr(config, "STACKY_DOCS_STALENESS_ENABLED", False))  # Plan 114
    payload["graph_explorer_enabled"] = bool(getattr(config, "STACKY_DOCS_GRAPH_EXPLORER_ENABLED", False))  # Plan 268
    # Plan 284 — la nota del operador y su tope viajan desde el backend (C18):
    # el maxLength del textarea NO se hardcodea contra una flag configurable.
    payload["operator_note_enabled"] = bool(getattr(config, "STACKY_DOCS_OPERATOR_NOTE_ENABLED", False))
    payload["operator_note_max_chars"] = int(getattr(config, "STACKY_DOCS_OPERATOR_NOTE_MAX_CHARS", 4000))
    return jsonify(payload)


# ── GET /api/docs/index ───────────────────────────────────────────────────────

@bp.get("/index")
def get_docs_index():
    """
    Devuelve el árbol completo de documentos indexados.

    Response 200:
    {
        "ok": true,
        "indexed_at": "2026-05-19T10:00:00Z",
        "roots": [ { "id": ..., "label": ..., "children": [...] }, ... ]
    }
    """
    t0 = time.monotonic()

    vscode_dir = _get_vscode_prompts_dir()
    project = _get_project_param()
    source_id = _get_source_param()

    try:
        if _is_project_source(source_id):
            index = doc_indexer.build_project_docs_index(
                project_name=project,
                source_id=source_id,
            )
        else:
            index = doc_indexer.build_index(vscode_prompts_dir=vscode_dir)
    except FileNotFoundError:
        return jsonify({
            "ok": False,
            "error": "doc_source_not_found",
            "message": "La fuente de documentación seleccionada no está disponible.",
        }), 404

    duration_ms = round((time.monotonic() - t0) * 1000)

    # Contar archivos totales
    def count_files(nodes):
        total = 0
        for node in nodes:
            if node.get("kind") == "folder":
                total += count_files(node.get("children", []))
            else:
                total += 1
        return total

    file_count = sum(count_files(root.get("children", [])) for root in index.get("roots", []))

    # Plan 284 F1.4 — resumen por clase documental. Con la flag OFF queda {}.
    def _collect_file_paths(nodes, acc):
        for node in nodes:
            if node.get("kind") == "folder":
                _collect_file_paths(node.get("children", []), acc)
            else:
                acc.append(str(node.get("path") or ""))
        return acc

    class_summary: dict = {}
    try:
        if bool(getattr(config, "STACKY_DOCS_TAXONOMY_ENABLED", False)):
            from services import doc_taxonomy
            _paths: list[str] = []
            for _root in index.get("roots", []):
                _collect_file_paths(_root.get("children", []), _paths)
            class_summary = doc_taxonomy.summarize_classes(_paths)
    except Exception:
        class_summary = {}

    logger.info(
        "docs_api",
        "docs_index_built",
        file_count=file_count,
        duration_ms=duration_ms,
        source_id=index.get("source_id"),
    )

    return jsonify({
        "ok": True,
        "indexed_at": index["indexed_at"],
        "source_id": index.get("source_id", source_id),
        "active_project": index.get("active_project"),
        "workspace_root": index.get("workspace_root"),
        "roots": index["roots"],
        "class_summary": class_summary,  # Plan 284 F1.4
    })


# ── GET /api/docs/content ─────────────────────────────────────────────────────

@bp.get("/content")
def get_doc_content():
    """
    Retorna el contenido raw de un documento validado.

    Query params:
        path: ruta relativa (ej: "docs/00_VISION.md")

    Response 200: { "ok": true, "path": "...", "content": "...", "encoding": "utf-8" }
    Response 400: { "ok": false, "error": "path_traversal_blocked", "message": "..." }
    Response 404: { "ok": false, "error": "not_found", "message": "..." }
    """
    path = request.args.get("path", "").strip()

    if not path:
        return jsonify({
            "ok": False,
            "error": "missing_param",
            "message": "El parámetro 'path' es requerido.",
        }), 400

    vscode_dir = _get_vscode_prompts_dir()
    project = _get_project_param()
    source_id = _get_source_param()

    try:
        if _is_project_source(source_id):
            content = doc_indexer.read_project_doc_content(
                path,
                project_name=project,
                source_id=source_id,
            )
        else:
            content = doc_indexer.read_content(path, vscode_prompts_dir=vscode_dir)
    except ValueError as exc:
        attempted = str(exc)
        logger.warning(
            "docs_api",
            "docs_path_traversal_blocked",
            attempted_path=path,
            detail=attempted,
        )
        return jsonify({
            "ok": False,
            "error": "path_traversal_blocked",
            "message": "La ruta solicitada está fuera del directorio permitido.",
        }), 400
    except FileNotFoundError:
        return jsonify({
            "ok": False,
            "error": "not_found",
            "message": "Documento no encontrado.",
        }), 404

    try:
        size_bytes = len(content.encode("utf-8"))
    except Exception:
        size_bytes = len(content)

    logger.info(
        "docs_api",
        "docs_content_served",
        path=path,
        size_bytes=size_bytes,
    )

    return jsonify({
        "ok": True,
        "path": path,
        "source_id": source_id,
        "content": content,
        "encoding": "utf-8",
    })


# ── GET /api/docs/graph ──────────────────────────────────────────────────────

@bp.get("/graph")
def get_docs_graph():
    """Plan 109 — Grafo documental read-only del proyecto activo/indicado.

    Query params: project (opcional, igual semántica que /index);
                  refresh=1 (opcional, [ADICIÓN ARQUITECTO]: invalida la cache
                  y fuerza re-scan antes de construir — read-only igual).
    404 {"ok": false, "error": "docs_graph_disabled"} si la flag está OFF.
    """
    if not bool(getattr(config, "STACKY_DOCS_GRAPH_ENABLED", False)):
        return jsonify({"ok": False, "error": "docs_graph_disabled",
                        "message": "El grafo de documentación está desactivado.",
                        "detail": {"flag": "STACKY_DOCS_GRAPH_ENABLED"}}), 404

    t0 = time.monotonic()
    from services import doc_graph  # import lazy: no cargar el módulo si la flag está OFF
    if request.args.get("refresh", "").strip() == "1":  # [ADICIÓN ARQUITECTO]
        doc_graph.invalidate_graph_cache()
    try:
        graph = doc_graph.build_graph(
            project_name=_get_project_param(),
            vscode_prompts_dir=_get_vscode_prompts_dir(),
        )
    except Exception as exc:  # nunca 500 sin log estructurado
        logger.warning("docs_api", "docs_graph_failed", detail=str(exc))
        # (C7) el detalle queda en el log; al cliente va un mensaje genérico
        return jsonify({"ok": False, "error": "docs_graph_failed",
                        "message": "No se pudo construir el grafo documental. Ver logs (docs_graph_failed)."}), 500

    # Plan 114 — Doctor de staleness (solo con flag ON). Con flag OFF el payload
    # es byte-idéntico al del plan 109 (no se importa ni se llama nada).
    if bool(getattr(config, "STACKY_DOCS_STALENESS_ENABLED", False)):
        try:
            import copy
            from services import doc_staleness  # import lazy: solo con la flag ON
            from services import doc_indexer
            repo_root = doc_indexer.list_doc_sources(_get_project_param()).get("workspace_root")
            if repo_root:
                graph = copy.deepcopy(graph)  # (C1) build_graph devuelve el objeto CACHEADO del 109;
                                              # anotar sin copiar contaminaría la cache y una request
                                              # posterior con flag OFF serviría los campos stale.
                graph = doc_staleness.annotate_staleness(graph, str(repo_root))
        except Exception as exc:  # degradación segura: nunca rompe el grafo
            logger.warning("docs_api", "docs_staleness_failed", detail=str(exc))

    logger.info("docs_api", "docs_graph_built",
                nodes=len(graph.get("nodes", [])), edges=len(graph.get("edges", [])),
                duration_ms=round((time.monotonic() - t0) * 1000),
                doc_health=(graph.get("doc_health") or {}).get("status"))
    return jsonify({"ok": True, **graph})


# ── Plan 113 — Documentador 1-click (gateado por STACKY_DOCS_DOCUMENTER_ENABLED) ─

def _documenter_enabled() -> bool:
    return bool(getattr(config, "STACKY_DOCS_DOCUMENTER_ENABLED", False))


@bp.post("/documenter/run")
def documenter_run():
    """Lanza el pipeline del Documentador en background. 1-click, sin formularios.

    Body (todo opcional): {project?, runtime?}. 404 si la flag está OFF; 409 si ya
    hay un run activo.
    """
    if not _documenter_enabled():
        return jsonify({"ok": False, "error": "documenter_disabled"}), 404
    body = request.get_json(silent=True) or {}
    from project_manager import get_active_project
    project = (body.get("project") or "").strip() or get_active_project()
    if not project:
        return jsonify({"ok": False, "error": "no_active_project"}), 400
    runtime = (body.get("runtime") or "claude_code_cli").strip()
    # Plan 284 F2.3 — nota libre del operador. Se TRUNCA, no se rechaza por largo:
    # un 400 por nota larga es trabajo extra para el operador. El 400 queda sólo
    # para tipo inválido.
    operator_note = ""
    if bool(getattr(config, "STACKY_DOCS_OPERATOR_NOTE_ENABLED", False)):
        raw_note = body.get("operator_note")
        if raw_note is not None and not isinstance(raw_note, str):
            return jsonify({"ok": False, "error": "operator_note_invalid",
                            "message": "La nota debe ser texto."}), 400
        max_chars = int(getattr(config, "STACKY_DOCS_OPERATOR_NOTE_MAX_CHARS", 4000))
        operator_note = (raw_note or "").strip()[:max_chars]
    from services import doc_documenter
    try:
        run_id = doc_documenter.start_documenter_run(
            project, runtime, operator_note=operator_note)
    except doc_documenter.DocumenterBusy:
        return jsonify({"ok": False, "error": "documenter_busy"}), 409
    return jsonify({"ok": True, "run_id": run_id})


@bp.get("/documenter/status")
def documenter_status():
    """Estado del run (progreso, salud antes/después, rama, diff_stat). 404 si flag OFF."""
    if not _documenter_enabled():
        return jsonify({"ok": False, "error": "documenter_disabled"}), 404
    run_id = (request.args.get("run") or "").strip()
    from services import doc_documenter
    rec = doc_documenter.get_run(run_id)
    if rec is None:
        return jsonify({"ok": False, "error": "run_not_found"}), 404
    return jsonify({
        "ok": True, "run_id": run_id,
        "state": rec.get("state"), "current_mode": rec.get("current_mode"),
        # Tarea 2 (consola en vivo) — execution_id de la invocación en curso del
        # modo actual, o None si no hay ninguna corriendo ahora mismo. El
        # frontend lo usa para enganchar el CodexConsoleDock (mismo patrón que
        # DevOps/QA/AgentLaunchModal).
        "current_execution_id": rec.get("current_execution_id"),
        "written": rec.get("written"), "skipped": rec.get("skipped"),
        "health_before": rec.get("health_before"), "health_after": rec.get("health_after"),
        "branch": rec.get("branch"), "degraded": rec.get("degraded"),
        "diff_stat": rec.get("diff_stat", ""), "reason": rec.get("reason", ""),
        "error": rec.get("error"),
        # Plan 137 F5 — preview/citas por archivo + modos saltados por
        # short-circuit (F3). Con V2 OFF ambos quedan [] (KPI-6, sin romper
        # al frontend actual que los ignora).
        "files": rec.get("files", []),
        "modes_skipped": rec.get("modes_skipped", []),
        # Plan 284 — todas aditivas: con las flags OFF el backend no las llena
        # y el frontend actual las ignora sin romperse.
        "stages": rec.get("stages", []),
        "verdict": rec.get("verdict", ""),
        "radiography": rec.get("radiography", {}),
        "radiography_delta": rec.get("radiography_delta", {}),
        "ticket_mining": rec.get("ticket_mining", {}),
        "operator_note": rec.get("operator_note", ""),
    })


@bp.post("/documenter/stage/approve")
def documenter_stage_approve():
    """Plan 284 F5.3 — el operador aprueba (o cancela) pasar a IMPLEMENTAR.

    Body: {"run": "<run_id>", "approve": true|false, "keep_branch": true|false}
    404 si STACKY_DOCS_DOCUMENTER_ENABLED o STACKY_DOCS_PIPELINE_STAGES_ENABLED
        están OFF (capacidad desactivada, NO "permiso denegado": mono-operador).
    404 run_not_found si el run_id no existe (reinicio del backend).
    409 si el run no está en state == "awaiting_approval".
    200 {"ok": true, "state": "running"|"cancelled_by_operator"}
    """
    if not _documenter_enabled():
        return jsonify({"ok": False, "error": "documenter_disabled",
                        "message": "Capacidad desactivada."}), 404
    if not bool(getattr(config, "STACKY_DOCS_PIPELINE_STAGES_ENABLED", False)):
        return jsonify({"ok": False, "error": "pipeline_stages_disabled",
                        "message": "Capacidad desactivada."}), 404
    body = request.get_json(silent=True) or {}
    run_id = (body.get("run") or "").strip()
    approve = bool(body.get("approve"))
    keep_branch = body.get("keep_branch")
    keep_branch = True if keep_branch is None else bool(keep_branch)

    from services import doc_documenter
    rec = doc_documenter.get_run(run_id)
    if rec is None:
        return jsonify({"ok": False, "error": "run_not_found"}), 404
    if rec.get("state") != "awaiting_approval":
        return jsonify({"ok": False, "error": "run_not_awaiting_approval",
                        "state": rec.get("state")}), 409
    try:
        state = doc_documenter.resolve_stage_approval(
            run_id, approve=approve, keep_branch=keep_branch)
    except Exception as exc:
        logger.warning("docs_api", "stage_approve_failed", run_id=run_id, error=str(exc))
        return jsonify({"ok": False, "error": "approve_failed", "message": str(exc)}), 500
    return jsonify({"ok": True, "state": state})


@bp.get("/documenter/runs")
def documenter_runs():
    """Plan 137 F4 — Historial de corridas persistidas. 404 si el master 113
    está OFF; lista vacía si la V2 (persistencia) está OFF."""
    if not _documenter_enabled():
        return jsonify({"ok": False, "error": "documenter_disabled"}), 404
    from services import doc_documenter
    return jsonify({"ok": True, "runs": doc_documenter.list_runs()})


@bp.post("/staleness/fix")
def staleness_fix():
    """Plan 114 — Encola el Documentador (113) en modo ACTUALIZAR acotado a una nota.

    Body: {note_path}. 404 si STACKY_DOCS_STALENESS_ENABLED OFF o
    STACKY_DOCS_DOCUMENTER_ENABLED OFF (necesita el 113). 409 documenter_busy
    heredado del 113. runtime = mismo default que POST /documenter/run.
    """
    if not bool(getattr(config, "STACKY_DOCS_STALENESS_ENABLED", False)):
        return jsonify({"ok": False, "error": "staleness_disabled"}), 404
    if not _documenter_enabled():
        return jsonify({"ok": False, "error": "documenter_disabled"}), 404
    body = request.get_json(silent=True) or {}
    note_path = (body.get("note_path") or "").strip()
    if not note_path:
        return jsonify({"ok": False, "error": "note_path_required"}), 400
    from project_manager import get_active_project
    project = (body.get("project") or "").strip() or get_active_project()
    if not project:
        return jsonify({"ok": False, "error": "no_active_project"}), 400
    runtime = (body.get("runtime") or "claude_code_cli").strip()  # (C7) mismo default que /documenter/run
    from services import doc_documenter
    try:
        run_id = doc_documenter.start_documenter_run(
            project, runtime, only_note=note_path,
            forced_modes=[doc_documenter.DocumenterMode.ACTUALIZAR])
    except doc_documenter.DocumenterBusy:
        return jsonify({"ok": False, "error": "documenter_busy"}), 409
    return jsonify({"ok": True, "run_id": run_id})


@bp.post("/documenter/decide")
def documenter_decide():
    """Conserva (keep) o descarta (discard) la rama del run. 404 si flag OFF."""
    if not _documenter_enabled():
        return jsonify({"ok": False, "error": "documenter_disabled"}), 404
    body = request.get_json(silent=True) or {}
    run_id = (body.get("run") or "").strip()
    action = (body.get("action") or "").strip()
    if action not in ("keep", "discard"):
        return jsonify({"ok": False, "error": "invalid_action"}), 400
    from services import doc_documenter
    rec = doc_documenter.get_run(run_id)
    if rec is None:
        # (C6) tras un restart el registro se pierde: 404 con patrón de rama para limpieza manual.
        return jsonify({
            "ok": False, "error": "run_not_found",
            "message": ("Run desconocido (¿reinicio del backend?). Podés limpiar a mano "
                        "las ramas 'stacky/doc-*' con git branch -D."),
        }), 404
    target_root = rec.get("target_root")
    branch = rec.get("branch")
    if not branch or not target_root:
        return jsonify({"ok": False, "error": "no_branch",
                        "message": "El run no dejó una rama (modo carpeta-sombra)."}), 400
    if action == "keep":
        doc_documenter.keep_doc_branch(target_root, branch)
    else:
        doc_documenter.discard_doc_branch(target_root, branch)
    doc_documenter._update_run(run_id, state=f"decided_{action}")
    return jsonify({"ok": True, "action": action, "branch": branch})
