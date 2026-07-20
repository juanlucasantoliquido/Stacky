"""Plan 178 — API del radar de ambientes. Blueprint SEPARADO de api/db_compare.py
para minimizar colisión de merge con el plan 176 (que edita ese archivo).

Gate doble: master 122 + radar 178. OFF (cualquiera) => 403 en TODO (este
blueprint no tiene /health propio; el health del comparador ya existe).
"""
from flask import Blueprint, jsonify, request

import config as _config
from services import dbcompare_baseline, dbcompare_registry, dbcompare_runs, dbcompare_watch

bp = Blueprint("db_compare_watch", __name__, url_prefix="/db-compare")


def _require_radar_enabled():
    # Idioma de api/db_compare.py — la instancia de flags es config.config,
    # NO el módulo (gotcha conocido: getattr(config, FLAG) da default y mata el OFF).
    if not getattr(_config.config, "STACKY_DB_COMPARE_ENABLED", False):
        return jsonify({"ok": False, "error": "Comparador de BD deshabilitado (STACKY_DB_COMPARE_ENABLED)."}), 403
    if not getattr(_config.config, "STACKY_DB_COMPARE_RADAR_ENABLED", False):
        return jsonify({"ok": False, "error": "Radar de ambientes deshabilitado (STACKY_DB_COMPARE_RADAR_ENABLED)."}), 403
    return None


@bp.get("/watches")
def list_watches_route():
    gate = _require_radar_enabled()
    if gate is not None:
        return gate
    return jsonify({"ok": True, "watches": dbcompare_watch.list_watches()})


@bp.post("/watches")
def upsert_watch_route():
    gate = _require_radar_enabled()
    if gate is not None:
        return gate
    data = request.get_json(silent=True) or {}
    source = str(data.get("source_alias") or "").strip()
    target = str(data.get("target_alias") or "").strip()
    if not source or not target:
        return jsonify({"ok": False, "error": "source_alias y target_alias son obligatorios"}), 400
    try:
        watch = dbcompare_watch.upsert_watch(source, target, enabled=bool(data.get("enabled", True)))
    except dbcompare_watch.DbCompareWatchError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "watch": watch})


@bp.delete("/watches/<watch_id>")
def delete_watch_route(watch_id):
    gate = _require_radar_enabled()
    if gate is not None:
        return gate
    if not dbcompare_watch.delete_watch(watch_id):
        return jsonify({"ok": False, "error": "watch desconocido"}), 404
    return jsonify({"ok": True})


@bp.get("/watch/events")
def list_events_route():
    gate = _require_radar_enabled()
    if gate is not None:
        return gate
    try:
        limit = int(request.args.get("limit", 50))
    except (TypeError, ValueError):
        limit = 50
    unread_only = str(request.args.get("unread_only", "false")).strip().lower() in ("1", "true", "yes")
    events = dbcompare_watch.list_events(limit, unread_only=unread_only)
    return jsonify({"ok": True, "events": events, "unread_count": dbcompare_watch.unread_count()})


@bp.post("/watch/events/mark-read")
def mark_events_read_route():
    gate = _require_radar_enabled()
    if gate is not None:
        return gate
    data = request.get_json(silent=True) or {}
    if data.get("all"):
        changed = dbcompare_watch.mark_events_read(None)
    else:
        ids = data.get("event_ids")
        if not isinstance(ids, list) or not ids:
            return jsonify({"ok": False, "error": "event_ids (lista no vacía) o all=true"}), 400
        changed = dbcompare_watch.mark_events_read([str(i) for i in ids])
    return jsonify({"ok": True, "changed": changed})


@bp.get("/baselines")
def list_baselines_route():
    gate = _require_radar_enabled()
    if gate is not None:
        return gate
    return jsonify({"ok": True, "baselines": dbcompare_baseline.list_baselines()})


@bp.post("/environments/<alias>/baseline")
def pin_baseline_route(alias):
    gate = _require_radar_enabled()
    if gate is not None:
        return gate
    data = request.get_json(silent=True) or {}
    snapshot_id = str(data.get("snapshot_id") or "").strip()
    if not snapshot_id:
        return jsonify({"ok": False, "error": "snapshot_id es obligatorio"}), 400
    try:
        baseline = dbcompare_baseline.pin_baseline(alias, snapshot_id, note=str(data.get("note") or ""))
    except dbcompare_baseline.DbCompareBaselineError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "baseline": baseline})


@bp.delete("/environments/<alias>/baseline")
def unpin_baseline_route(alias):
    gate = _require_radar_enabled()
    if gate is not None:
        return gate
    if not dbcompare_baseline.unpin_baseline(alias):
        return jsonify({"ok": False, "error": "no había baseline pinneado"}), 404
    return jsonify({"ok": True})


@bp.get("/baseline-diff/<alias>")
def baseline_diff_route(alias):
    gate = _require_radar_enabled()
    if gate is not None:
        return gate
    try:
        diff = dbcompare_baseline.baseline_diff(alias)
    except dbcompare_baseline.DbCompareBaselineError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "diff": diff})


@bp.get("/radar")
def radar_route():
    gate = _require_radar_enabled()
    if gate is not None:
        return gate
    environments = dbcompare_registry.list_environments()
    watches = {w["watch_id"]: w for w in dbcompare_watch.list_watches()}
    baselines = {b["alias"]: b for b in dbcompare_baseline.list_baselines()}
    latest_by_pair: dict = {}
    for meta in dbcompare_runs.list_runs(200):
        if meta.get("status") != "done" or not meta.get("summary"):
            continue
        key = f"{meta['source_alias']}__{meta['target_alias']}"
        if key not in latest_by_pair or (meta.get("finished_at") or "") > (latest_by_pair[key].get("finished_at") or ""):
            latest_by_pair[key] = meta
    cells = []
    for key, meta in latest_by_pair.items():
        sev = (meta["summary"] or {}).get("by_severity") or {}
        state = "green"
        if int(sev.get("danger") or 0) > 0:
            state = "red"
        elif int(sev.get("warn") or 0) + int(sev.get("info") or 0) > 0:
            state = "amber"
        cells.append({
            "source_alias": meta["source_alias"], "target_alias": meta["target_alias"],
            "state": state, "by_severity": sev,
            "parity_score": (meta["summary"] or {}).get("parity_score"),
            "run_id": meta["run_id"], "finished_at": meta.get("finished_at"),
            "initiated_by": meta.get("initiated_by", "operator"),
            "watched": key in watches and watches[key].get("enabled", False),
        })
    return jsonify({
        "ok": True,
        "environments": [{"alias": e["alias"], "engine": e["engine"], "has_baseline": e["alias"] in baselines} for e in environments],
        "cells": cells,          # pares SIN celda => estado "gray" (sin datos) en la UI
        "watches": list(watches.values()),
        "unread_events": dbcompare_watch.unread_count(),
    })
