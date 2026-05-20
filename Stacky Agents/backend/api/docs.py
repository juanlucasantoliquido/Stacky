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
    return jsonify(doc_indexer.list_doc_sources(project_name=_get_project_param()))


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
