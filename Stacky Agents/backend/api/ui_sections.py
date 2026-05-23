"""
UI Sections Blueprint
=====================
Endpoints para administrar la visibilidad de las pestañas de navegación
principal del frontend.

Rutas:
    GET /api/ui-sections              — devuelve el estado actual
    PUT /api/ui-sections/<section>    — actualiza visibilidad de una sección
                                         opcional (pm / logs / docs)

Las secciones obligatorias (team, tickets, settings) no se pueden togglear:
cualquier intento devuelve 400.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from services.stacky_logger import logger as stacky_logger
from services.ui_sections_store import (
    ValidationError,
    get_sections,
    set_section_visible,
)

bp = Blueprint("ui_sections", __name__, url_prefix="/ui-sections")


@bp.get("")
def get_all():
    return jsonify({"ok": True, "sections": get_sections()})


@bp.put("/<section>")
def put_section(section: str):
    payload = request.get_json(force=True, silent=True) or {}
    visible = payload.get("visible")
    if not isinstance(visible, bool):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "validation_error",
                    "message": "El campo 'visible' es requerido y debe ser booleano.",
                }
            ),
            400,
        )

    try:
        sections = set_section_visible(section, visible)
    except ValidationError as exc:
        return (
            jsonify({"ok": False, "error": "validation_error", "message": str(exc)}),
            400,
        )

    stacky_logger.info(
        "ui_sections",
        "ui_section_toggled",
        section=section,
        visible=visible,
    )
    return jsonify({"ok": True, "sections": sections})
