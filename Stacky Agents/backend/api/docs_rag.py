"""API Blueprint: /api/docs-rag

Endpoints para indexacion y chat RAG sobre documentacion Markdown del proyecto.

  POST  /api/docs-rag/index   -- Indexa los .md del proyecto activo o indicado.
  GET   /api/docs-rag/stats   -- Estadisticas del indice del proyecto.
  POST  /api/docs-rag/search  -- Busca chunks relevantes (debugging/preview).
  POST  /api/docs-rag/chat    -- Chat con contexto RAG inyectado automaticamente.

Portado desde WS2 (2026-05-24) -- P1.1.
Adaptaciones WS1:
  - _read_agent_system_prompt sustituida por vscode_agents.get_agent_by_filename
    (mismo patron que api/chat.py portado en Sprint 2).
  - config.AUTONOMOUS_WORKSPACE_DIR no existe en WS1 -- se usa None como fallback.
  - Blueprint registrado en api/__init__.py.
"""

from __future__ import annotations

import logging

from flask import Blueprint, abort, jsonify, request

from config import config
from project_manager import get_active_project, get_project_config
from services.docs_rag import DocHit, get_stats, index_project, search

logger = logging.getLogger(__name__)

bp = Blueprint("docs_rag", __name__, url_prefix="/docs-rag")

_DEFAULT_AGENT = "DocConsultor.agent.md"
_DEFAULT_TOP_K = 5
_MAX_CONTEXT_CHARS = 40_000   # ~10k tokens de contexto documental


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_agent_system_prompt(agent_filename: str) -> str:
    """Lee el system_prompt del archivo .agent.md del agente.

    Usa vscode_agents (WS1) en lugar de la funcion interna de WS2.
    Retorna string vacio si no se encuentra el agente.
    """
    try:
        from services import vscode_agents
        agent = vscode_agents.get_agent_by_filename(
            prompts_dir=config.VSCODE_PROMPTS_DIR or "",
            filename=agent_filename,
        )
        if agent is None:
            return ""
        return agent.system_prompt or ""
    except Exception as exc:
        logger.warning("docs_rag: cannot read system prompt for %s: %s", agent_filename, exc)
        return ""


def _resolve_project(project_name: str | None) -> tuple[str, dict]:
    """Retorna (nombre, config) del proyecto. Usa el activo si no se indica."""
    name = project_name or get_active_project()
    if not name:
        abort(400, "No hay proyecto activo. Indica project_name.")
    cfg = get_project_config(name)
    if not cfg:
        abort(404, f"Proyecto '{name}' no encontrado.")
    return name, cfg


def _build_context_block(hits: list[DocHit]) -> str:
    """Construye el bloque de contexto documental para inyectar en el system prompt.

    Agrupa los hits por fichero para que el LLM vea el contenido completo
    de cada fichero relevante en un bloque continuo.
    """
    if not hits:
        return ""

    # Agrupar por fichero preservando el orden de primera aparicion
    from collections import OrderedDict
    file_hits: OrderedDict[str, list[DocHit]] = OrderedDict()
    for h in hits:
        file_hits.setdefault(h.file_path, []).append(h)

    lines = ["## CONTEXTO DOCUMENTACION (ficheros relevantes)\n"]
    total_chars = 0

    for file_path, file_chunks in file_hits.items():
        if total_chars >= _MAX_CONTEXT_CHARS:
            break
        file_block_lines = [f"### {file_path}\n"]
        for h in file_chunks:
            if total_chars >= _MAX_CONTEXT_CHARS:
                file_block_lines.append("...[contexto truncado por limite]")
                break
            snippet = h.chunk_text
            remaining = _MAX_CONTEXT_CHARS - total_chars
            if len(snippet) > 2500:
                snippet = snippet[:2500] + "\n...[fragmento truncado]"
            if len(snippet) > remaining:
                snippet = snippet[:remaining] + "\n...[contexto truncado por limite]"
            file_block_lines.append(snippet)
            total_chars += len(snippet) + 5
        lines.append("\n".join(file_block_lines) + "\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@bp.post("/index")
def route_index():
    """Indexa los ficheros .md del proyecto.

    Body JSON (todos opcionales):
      project_name  -- Nombre del proyecto. Si no se indica, usa el activo.
      docs_subpath  -- Subdirectorio relativo al workspace_root. Default: "docs".
    """
    body = request.get_json(silent=True) or {}
    name, cfg = _resolve_project(body.get("project_name"))
    workspace_root = cfg.get("workspace_root", "")
    if not workspace_root:
        return jsonify({"ok": False, "error": "El proyecto no tiene workspace_root configurado."}), 400

    docs_subpath = body.get("docs_subpath") or "docs"

    try:
        result = index_project(name, workspace_root, docs_subpath)
    except Exception as exc:
        logger.error("docs_rag index error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500

    return jsonify({"ok": True, "project_name": name, **result})


@bp.get("/stats")
def route_stats():
    """Retorna estadisticas del indice del proyecto.

    Query params:
      project_name -- Opcional. Usa el activo si no se indica.
    """
    name, _ = _resolve_project(request.args.get("project_name"))
    try:
        stats = get_stats(name)
    except Exception as exc:
        logger.error("docs_rag stats error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True, "project_name": name, **stats})


@bp.post("/search")
def route_search():
    """Busca chunks relevantes para una query (util para debugging/preview).

    Body JSON:
      query         -- Texto a buscar (requerido).
      project_name  -- Opcional.
      top_k         -- Numero de resultados. Default 5.
    """
    body = request.get_json(silent=True) or {}
    query = (body.get("query") or "").strip()
    if not query:
        abort(400, "El campo 'query' es requerido.")

    name, _ = _resolve_project(body.get("project_name"))
    top_k = int(body.get("top_k") or _DEFAULT_TOP_K)

    try:
        hits = search(name, query, top_k=top_k)
    except Exception as exc:
        logger.error("docs_rag search error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500

    return jsonify({
        "ok": True,
        "project_name": name,
        "query": query,
        "hits": [h.to_dict() for h in hits],
    })


@bp.post("/chat")
def route_chat():
    """Chat RAG -- responde preguntas usando el indice documental como contexto.

    Body JSON:
      messages       -- Lista de mensajes [{role, content}] (requerido, >= 1).
      project_name   -- Opcional. Usa el activo si no se indica.
      agent_filename -- Opcional. Default: DocConsultor.agent.md.
      model          -- Opcional. Default del config.
      top_k          -- Fragmentos a inyectar. Default 5.
      workspace_dir  -- Opcional. Usado por el backend vscode_bridge.
    """
    body = request.get_json(silent=True) or {}
    messages: list[dict] = body.get("messages") or []
    if not messages:
        abort(400, "El campo 'messages' es requerido y no puede estar vacio.")

    # Ultima pregunta del usuario
    user_msgs = [m for m in messages if m.get("role") == "user"]
    if not user_msgs:
        abort(400, "No hay mensajes de usuario en 'messages'.")
    last_query = (user_msgs[-1].get("content") or "").strip()

    name, _ = _resolve_project(body.get("project_name"))
    agent_filename = body.get("agent_filename") or _DEFAULT_AGENT
    model = body.get("model") or config.COPILOT_MODEL
    top_k = int(body.get("top_k") or _DEFAULT_TOP_K)
    # config.AUTONOMOUS_WORKSPACE_DIR no existe en WS1; fallback a None
    workspace_dir = body.get("workspace_dir") or getattr(config, "AUTONOMOUS_WORKSPACE_DIR", None)

    # 1. Recuperar fragmentos relevantes
    try:
        hits = search(name, last_query, top_k=top_k)
    except Exception as exc:
        logger.error("docs_rag chat search error: %s", exc, exc_info=True)
        hits = []

    # 2. Leer system prompt base del agente (patron WS1: vscode_agents)
    base_system = _read_agent_system_prompt(agent_filename)

    # 3. Inyectar contexto documental al system prompt
    context_block = _build_context_block(hits)
    if context_block:
        system = (
            f"{base_system}\n\n---\n\n{context_block}\n\n---\n\n"
            "**INSTRUCCION:** Los encabezados `###` del bloque de contexto son rutas de ficheros "
            "internas. NO las menciones ni cites en tu respuesta salvo que el usuario te pida "
            "explicitamente las fuentes."
        )
    else:
        system = base_system
        if not hits:
            system += (
                "\n\n---\n\n**NOTA:** No hay documentacion indexada para este proyecto. "
                "Indica al usuario que primero debe indexar la documentacion usando el boton correspondiente."
            )
        else:
            system += (
                "\n\n---\n\n**NOTA:** Se encontraron documentos relevantes pero no pudieron "
                "incluirse por limitaciones de contexto. Indica al usuario que reformule su "
                "pregunta de forma mas especifica."
            )

    logs: list[str] = []

    def on_log(level: str, msg: str) -> None:
        logs.append(f"[{level}] {msg}")
        logger.debug("docs_rag chat [%s] %s", level, msg)

    backend = (getattr(config, "LLM_BACKEND", None) or "mock").lower()

    # 4. Llamar al LLM (mismo patron que /api/chat/turn)
    try:
        import copilot_bridge
        from api.chat import _messages_to_prose  # type: ignore[attr-defined]

        if backend in ("vscode_bridge", "copilot"):
            history_text = _messages_to_prose(messages)
            if backend == "vscode_bridge":
                result = copilot_bridge._invoke_vscode_bridge(
                    agent_type="custom",
                    system=system,
                    user=history_text,
                    on_log=on_log,
                    execution_id=None,
                    model=model,
                )
            else:
                result = copilot_bridge.invoke(
                    agent_type="custom",
                    system=system,
                    user=history_text,
                    on_log=on_log,
                    model=model,
                )
        else:
            result = copilot_bridge._invoke_mock(
                agent_type="custom",
                on_log=on_log,
                execution_id=None,
                model=model,
            )

        meta = result.metadata or {}
        return jsonify({
            "ok": True,
            "text": result.text,
            "sources": [
                {"file_path": h.file_path, "section": h.section_heading, "score": round(h.score, 3)}
                for h in hits
            ],
            "chunks_used": len(hits),
            "model_used": meta.get("model") or model,
            "logs": logs,
        })

    except copilot_bridge.CancelledError:
        abort(409, "cancelled")
    except Exception as exc:
        logger.error("docs_rag chat llm error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc), "logs": logs}), 500
