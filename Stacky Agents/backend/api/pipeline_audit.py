"""api/pipeline_audit.py — Blueprint de la auditoria de pipelines. Plan 248 F5.

url_prefix="/pipeline-audit" -> ruta final /api/pipeline-audit/...
Guard de la flag PER-REQUEST (abort(404)), nunca gateado en el registro del blueprint.

READ-ONLY sobre el YAML: detecta, explica y propone. Lo unico que escribe en todo el
plan es una linea de supresion, y exige motivo escrito del operador.
"""
from __future__ import annotations

from flask import Blueprint, abort, jsonify, request

from services.cicd_audit_core import MODE_AUDIT, audit_yaml
from services.pipeline_audit_suppressions import (
    add_suppression,
    list_suppressions,
    remove_suppression,
)

bp = Blueprint("pipeline_audit", __name__, url_prefix="/pipeline-audit")

_PROVIDERS = ("ado", "gitlab")


def _guard():
    import config as _config  # noqa: PLC0415

    # GOTCHA: la INSTANCIA (_config.config), no el modulo: getattr del modulo devuelve el
    # default y el test flag-off pasaria en falso.
    if not getattr(_config.config, "STACKY_PIPELINE_AUDIT_ENABLED", False):
        abort(404)


@bp.post("/scan")
def scan_route():
    _guard()
    body = request.get_json(silent=True) or {}
    yaml_text = body.get("yaml")
    if not isinstance(yaml_text, str) or not yaml_text.strip():
        return jsonify({"error": "yaml_requerido",
                        "detail": "envia `yaml` (string no vacio)"}), 400
    provider = str(body.get("provider") or "ado")
    if provider not in _PROVIDERS:
        return jsonify({"error": "provider_no_soportado",
                        "detail": "provider debe ser uno de: %s" % ", ".join(_PROVIDERS)}), 400
    pipeline_key = body.get("pipeline_key")
    supresiones = list_suppressions(pipeline_key) if pipeline_key else []
    try:
        report = audit_yaml(
            yaml_text,
            provider=provider,
            mode=str(body.get("mode") or MODE_AUDIT),
            pipeline_key=pipeline_key,
            suppressions=supresiones,
        )
    except ValueError as exc:
        return jsonify({"error": "mode_invalido", "detail": str(exc)}), 400
    return jsonify(report.to_dict()), 200


@bp.get("/suppressions")
def list_suppressions_route():
    _guard()
    pipeline_key = request.args.get("pipeline_key") or None
    return jsonify({"items": list_suppressions(pipeline_key)}), 200


@bp.post("/suppress")
def suppress_route():
    _guard()
    body = request.get_json(silent=True) or {}
    try:
        add_suppression(body)
    except ValueError as exc:
        return jsonify({"error": "supresion_invalida", "detail": str(exc)}), 400
    return jsonify({"ok": True}), 201


@bp.delete("/suppress")
def unsuppress_route():
    _guard()
    body = request.get_json(silent=True) or {}
    removed = remove_suppression(
        str(body.get("pipeline_key") or ""),
        str(body.get("code") or ""),
        str(body.get("location") or ""),
    )
    return jsonify({"removed": bool(removed)}), 200
