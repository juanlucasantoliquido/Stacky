"""api/pipeline_handoff.py — Blueprint del paquete de entrega. Plan 252 F4.

url_prefix="/pipeline-handoff" -> ruta final /api/pipeline-handoff/...
Guard de la flag PER-REQUEST (abort(404)) — nunca gateado en el registro del blueprint.

Este blueprint NO ejecuta nada fuera del proceso de Stacky. Solo arma y sirve archivos.
`POST /build` es HITL por construccion: corre solo cuando el operador clickea; no hay
scheduler, watcher ni hook que lo dispare.
"""
from __future__ import annotations

import os
from pathlib import Path

import config as _config
from flask import Blueprint, abort, jsonify, request, send_file

from services import pipeline_handoff_bundle as hb
from services.pipeline_capability_frontier import CATALOG_VERSION, evaluate_frontier

bp = Blueprint("pipeline_handoff", __name__, url_prefix="/pipeline-handoff")


def _guard():
    # la INSTANCIA, no el modulo: getattr del modulo devuelve el default y mata el
    # branch OFF (el test flag-off pasaria en falso).
    if not getattr(_config.config, "STACKY_PIPELINE_HANDOFF_BUNDLE_ENABLED", False):
        abort(404)


def _bool_arg(valor, default=False) -> bool:
    if valor is None:
        return default
    return str(valor).strip().lower() in ("1", "true", "yes")


@bp.get("/frontier")
def frontier_route():
    """Que puede y que no puede Stacky, resuelto contra ESTA maquina, ahora."""
    _guard()
    deploys = _bool_arg(request.args.get("deploys"), default=False)
    resuelto = evaluate_frontier(pipeline_deploys=deploys)
    return jsonify({
        "catalog_version": CATALOG_VERSION,
        "actions": [{"id": r.action.id, "label": r.action.label,
                     "effective": r.effective, "reason": r.action.reason,
                     "probe_detail": r.probe_detail,
                     "manual_instruction": r.action.manual_instruction}
                    for r in resuelto],
    }), 200


@bp.post("/build")
def build_route():
    _guard()
    body = request.get_json(silent=True) or {}
    pipeline_name = str(body.get("pipeline_name") or "").strip()
    provider = str(body.get("provider") or "").strip()
    yaml_files = body.get("yaml_files")
    if not pipeline_name:
        return jsonify({"error": "pipeline_name_requerido"}), 400
    if provider not in ("ado", "gitlab"):
        return jsonify({"error": "provider_no_soportado",
                        "detail": "provider debe ser 'ado' o 'gitlab'"}), 400
    if not isinstance(yaml_files, dict) or not yaml_files:
        return jsonify({"error": "yaml_files_requerido",
                        "detail": "un paquete sin archivos no es un paquete"}), 400
    script_files = body.get("script_files")
    if script_files is not None and not isinstance(script_files, dict):
        return jsonify({"error": "script_files_invalido"}), 400
    deploys = bool(body.get("pipeline_deploys"))

    try:
        inputs = hb.collect_inputs(
            body.get("spec") or {}, pipeline_name=pipeline_name, provider=provider,
            yaml_files={str(k): str(v) for k, v in yaml_files.items()},
            script_files={str(k): str(v) for k, v in (script_files or {}).items()},
            pipeline_deploys=deploys)
        resuelto = evaluate_frontier(pipeline_deploys=deploys)
        bundle_id, data, manifest = hb.build_bundle(inputs, resuelto)
    except hb.HandoffSecretError as e:
        # falla CERRADO: no se persiste nada y el operador ve por que
        return jsonify({"error": str(e)}), 409
    except hb.HandoffTooLargeError as e:
        return jsonify({"error": str(e)}), 413
    except hb.HandoffError as e:
        return jsonify({"error": str(e)}), 400

    hb.persist_bundle(bundle_id, data)
    hb.prune_bundles()          # best-effort: nunca aborta la respuesta
    hb.append_ledger(bundle_id, manifest)
    return jsonify({"bundle_id": bundle_id, "bytes": len(data),
                    "manifest": manifest}), 200


@bp.get("/<bundle_id>/download")
def download_route(bundle_id):
    _guard()
    path = hb.bundle_path(bundle_id)     # valida ^[0-9a-f]{16}$ ANTES de tocar el disco
    if path is None:
        abort(404)
    from runtime_paths import data_dir

    root = (Path(data_dir()) / "pipeline_handoff" / "bundles").resolve()
    target = Path(path).resolve()
    try:
        if os.path.commonpath([str(root), str(target)]) != str(root):
            abort(400)                    # defensa en profundidad
    except ValueError:
        abort(400)
    if not target.exists():
        abort(404)
    if target.stat().st_size > hb.MAX_BUNDLE_BYTES:
        abort(413)
    return send_file(str(target), mimetype="application/zip", as_attachment=True,
                     download_name="stacky-handoff-%s.zip" % bundle_id)
