"""api/evolution_knowledge.py — Plan 170: flywheel de conocimiento (contratos §4.8-§4.10).

Tercer blueprint del prefijo `/evolution` (mismo patrón que 168/169: Flask permite N
blueprints con el mismo prefijo y nombres distintos). `/knowledge/health` responde
SIEMPRE 200; el resto está gateado por `_knowledge_enabled()` (CENTER && FLYWHEEL) →
404 `knowledge_disabled` con OFF. Imports de services LAZY dentro de cada handler.

El endpoint de vista previa es DRY-RUN puro: no altera contadores de uso (los
registros viven SOLO en el injector F3 de context_enrichment).
"""
from flask import Blueprint, jsonify, request

from config import config as _cfg  # G1

bp = Blueprint("evolution_knowledge", __name__, url_prefix="/evolution")


# --------------------------------------------------------------------------- #
# Gate compuesto (§4.6)
# --------------------------------------------------------------------------- #
def _knowledge_enabled() -> bool:
    return bool(getattr(_cfg, "STACKY_EVOLUTION_CENTER_ENABLED", False)) and \
        bool(getattr(_cfg, "STACKY_KNOWLEDGE_FLYWHEEL_ENABLED", False))


def _disabled_resp():
    return jsonify({
        "ok": False, "error": "knowledge_disabled",
        "message": "El flywheel de conocimiento está deshabilitado (STACKY_KNOWLEDGE_FLYWHEEL_ENABLED).",
    }), 404


@bp.before_request
def _gate():
    if request.path.endswith("/knowledge/health"):
        return None
    if not _knowledge_enabled():
        return _disabled_resp()
    return None


def _max_lessons() -> int:
    try:
        return int(getattr(_cfg, "STACKY_KNOWLEDGE_MAX_LESSONS", 200))
    except (TypeError, ValueError):
        return 200


def _top_n() -> int:
    try:
        return max(1, min(10, int(getattr(_cfg, "STACKY_KNOWLEDGE_INJECT_TOP_N", 3))))
    except (TypeError, ValueError):
        return 3


def _max_chars() -> int:
    try:
        return max(500, min(20000, int(getattr(_cfg, "STACKY_KNOWLEDGE_INJECT_MAX_CHARS", 4000))))
    except (TypeError, ValueError):
        return 4000


def _emsg(exc) -> str:
    return str(exc.args[0]) if getattr(exc, "args", None) else str(exc)


# --------------------------------------------------------------------------- #
# Health (siempre 200)
# --------------------------------------------------------------------------- #
@bp.get("/knowledge/health")
def health():
    return jsonify({
        "ok": True,
        "flag_enabled": _knowledge_enabled(),
        "injection_enabled": bool(getattr(_cfg, "STACKY_KNOWLEDGE_INJECTION_ENABLED", False)),
        "llm_configured": bool(getattr(_cfg, "LOCAL_LLM_ENDPOINT", "")),
    })


# --------------------------------------------------------------------------- #
# Lecciones
# --------------------------------------------------------------------------- #
@bp.get("/knowledge/lessons")
def list_lessons():
    from services import knowledge_store as ks
    include_retired = request.args.get("include_retired") == "true"
    lessons = ks.list_lessons(include_retired=include_retired)
    cap = _max_lessons()
    active = sum(1 for l in lessons if l.get("active"))
    return jsonify({"ok": True, "lessons": lessons, "cap": cap, "over_cap": active > cap})


@bp.patch("/knowledge/lessons/<lid>")
def patch_lesson(lid):
    from services import knowledge_store as ks
    body = request.get_json(silent=True) or {}
    if (not isinstance(body, dict) or not body
            or any(k not in ("title", "scope") for k in body)):
        return jsonify({"ok": False, "error": "invalid_payload"}), 400
    try:
        ks.patch_meta(lid, **body)
    except KeyError:
        return jsonify({"ok": False, "error": "lesson_not_found"}), 404
    except ValueError:
        return jsonify({"ok": False, "error": "invalid_payload"}), 400
    lesson = ks.get_lesson(lid)
    return jsonify({"ok": True, "lesson": lesson})


# --------------------------------------------------------------------------- #
# Cosecha
# --------------------------------------------------------------------------- #
def _run_harvest(fn, *, wrap=None):
    from services.knowledge_harvest import DuplicateSuspect
    try:
        result = fn()
        payload = wrap(result) if wrap else {"ok": True, **result}
        return jsonify(payload), 201
    except DuplicateSuspect as exc:
        return jsonify({
            "ok": False, "error": "duplicate_suspect",
            "message": "Ya existe una lección muy similar.",
            "duplicates": exc.similars,
        }), 409
    except KeyError as exc:
        return jsonify({"ok": False, "error": _emsg(exc)}), 404
    except ValueError as exc:
        msg = _emsg(exc)
        if msg.startswith("incident_not_harvestable"):
            return jsonify({"ok": False, "error": "incident_not_harvestable", "message": msg}), 409
        if msg.startswith("lesson_outcome_invalido"):
            return jsonify({"ok": False, "error": "lesson_outcome_invalido", "message": msg}), 409
        if msg.startswith("invalid_payload"):
            return jsonify({"ok": False, "error": "invalid_payload", "message": msg}), 400
        if msg == "case_already_exists":
            return jsonify({"ok": False, "error": "case_already_exists"}), 409
        if msg == "lesson_not_active":
            return jsonify({"ok": False, "error": "lesson_not_active"}), 409
        return jsonify({"ok": False, "error": "invalid_payload", "message": msg}), 400
    except RuntimeError as exc:
        msg = _emsg(exc)
        if msg == "optimizer_unavailable":
            return jsonify({"ok": False, "error": "optimizer_unavailable"}), 409
        return jsonify({"ok": False, "error": msg}), 500


@bp.post("/knowledge/harvest/from-incident")
def harvest_from_incident():
    from services import knowledge_harvest as kh
    body = request.get_json(silent=True) or {}
    return _run_harvest(lambda: kh.harvest_from_incident(
        str(body.get("incident_id") or ""), force=bool(body.get("force"))))


@bp.post("/knowledge/harvest/from-optimizer-lesson")
def harvest_from_optimizer_lesson():
    from services import knowledge_harvest as kh
    body = request.get_json(silent=True) or {}
    return _run_harvest(lambda: kh.harvest_from_optimizer_lesson(
        str(body.get("lesson_id") or ""), force=bool(body.get("force"))))


@bp.post("/knowledge/harvest/manual")
def harvest_manual():
    from services import knowledge_harvest as kh
    body = request.get_json(silent=True) or {}
    return _run_harvest(lambda: kh.harvest_manual(
        str(body.get("title") or ""), str(body.get("body") or ""),
        scope=body.get("scope"), force=bool(body.get("force"))))


@bp.post("/knowledge/lessons/<lid>/to-eval-case")
def to_eval_case(lid):
    from services import knowledge_harvest as kh
    return _run_harvest(lambda: kh.lesson_to_eval_case(lid),
                        wrap=lambda case: {"ok": True, "case": case})


# --------------------------------------------------------------------------- #
# Candidatas
# --------------------------------------------------------------------------- #
def _dev_run_tracker_ids() -> set[str]:
    try:
        from db import session_scope
        from models import AgentExecution, Ticket
        with session_scope() as s:
            rows = (
                s.query(Ticket.ado_id)
                .join(AgentExecution, AgentExecution.ticket_id == Ticket.id)
                .filter(AgentExecution.agent_type == "incident_dev",
                        AgentExecution.status == "completed")
                .distinct().all()
            )
            return {str(r[0]) for r in rows}
    except Exception:  # noqa: BLE001
        return set()


@bp.get("/knowledge/harvest/candidates")
def harvest_candidates():
    from services import incident_store, knowledge_store as ks
    try:
        published = [i for i in incident_store.list_incidents()
                     if i.get("status") == "publicada"]
    except Exception:  # noqa: BLE001
        published = []
    harvested = ks.harvested_incident_ids()
    dev_ids = _dev_run_tracker_ids()
    incidents = []
    for i in published:
        tid = i.get("tracker_id")
        incidents.append({
            "incident_id": i.get("id"), "title": i.get("title"),
            "created_at": i.get("created_at"),
            "has_dev_run": (str(tid) in dev_ids) if tid else False,
            "already_harvested": i.get("id") in harvested,
        })
    incidents.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    incidents.sort(key=lambda x: x["already_harvested"])  # no cosechadas primero

    optimizer_lessons = []
    try:
        from services import evolution_optimizer_store as eos
        harvested_opt = ks.harvested_optimizer_lesson_ids()
        for l in eos.read_lessons_tail(limit=50):
            if l.get("outcome") != "mejoro":
                continue
            optimizer_lessons.append({
                "lesson_id": l.get("id"), "run_id": l.get("run_id"),
                "aspect_key": l.get("aspect_key"), "text": l.get("text"),
                "delta": l.get("delta"),
                "already_harvested": l.get("id") in harvested_opt,
            })
    except Exception:  # noqa: BLE001 — sin Plan 169
        optimizer_lessons = []
    return jsonify({"ok": True, "incidents": incidents,
                    "optimizer_lessons": optimizer_lessons})


# --------------------------------------------------------------------------- #
# Overview (§4.10) — cada fuente en su propio try/except
# --------------------------------------------------------------------------- #
@bp.get("/knowledge/overview")
def overview():
    from services import knowledge_store as ks
    cap = _max_lessons()

    try:
        all_lessons = ks.list_lessons(include_retired=True)
    except Exception:  # noqa: BLE001
        all_lessons = []
    actives = [l for l in all_lessons if l.get("active")]
    retired = [l for l in all_lessons if not l.get("active")]
    lessons_kpi = {"active": len(actives), "retired": len(retired),
                   "cap": cap, "over_cap": len(actives) > cap}

    # coverage
    try:
        from agents import registry
        types = list(registry.keys())
        counts = {t: 0 for t in types}
        for l in actives:
            ats = (l.get("scope") or {}).get("agent_types") or []
            if not ats:
                for t in counts:
                    counts[t] += 1
            else:
                for t in ats:
                    counts[t] = counts.get(t, 0) + 1
        coverage = {
            "agents_total": len(types),
            "agents_with_lessons": sum(1 for t in types if counts.get(t, 0) > 0),
            "by_agent_type": {t: counts.get(t, 0) for t in types},
        }
    except Exception:  # noqa: BLE001
        coverage = {"agents_total": 0, "agents_with_lessons": 0, "by_agent_type": {}}

    # flywheel
    flywheel = {"incidents_published": 0, "incidents_harvested": 0,
                "eval_cases_from_incidents": 0, "eval_cases_from_lessons": 0,
                "optimizer_lessons_mejoro": 0, "optimizer_lessons_promoted": 0}
    try:
        from services import incident_store
        flywheel["incidents_published"] = sum(
            1 for i in incident_store.list_incidents() if i.get("status") == "publicada")
        flywheel["incidents_harvested"] = len(ks.harvested_incident_ids())
    except Exception:  # noqa: BLE001
        pass
    try:
        from evals import case_store
        cases = case_store.list_cases()
        flywheel["eval_cases_from_incidents"] = sum(1 for c in cases if c.get("origin") == "incident")
        flywheel["eval_cases_from_lessons"] = sum(1 for c in cases if c.get("origin") == "lesson")
    except Exception:  # noqa: BLE001
        pass
    try:
        from services import evolution_optimizer_store as eos
        flywheel["optimizer_lessons_mejoro"] = sum(
            1 for l in eos.read_lessons_tail(limit=200) if l.get("outcome") == "mejoro")
        flywheel["optimizer_lessons_promoted"] = len(ks.harvested_optimizer_lesson_ids())
    except Exception:  # noqa: BLE001
        pass

    # usage
    try:
        total = sum(int(l.get("usage_count") or 0) for l in actives)
        never = sum(1 for l in actives if int(l.get("usage_count") or 0) == 0)
        top = sorted(actives, key=lambda l: int(l.get("usage_count") or 0), reverse=True)[:3]
        usage = {"injections_total": total, "never_injected": never,
                 "top": [{"lesson_id": l["lesson_id"], "title": l.get("title") or "",
                          "usage_count": int(l.get("usage_count") or 0)} for l in top]}
    except Exception:  # noqa: BLE001
        usage = {"injections_total": 0, "never_injected": 0, "top": []}

    # fitness_knowledge (correlación honesta)
    try:
        from evals import case_store
        runs = [r for r in case_store.read_runs_tail(aspect_key="knowledge_rag", limit=200)
                if r.get("trigger") != "candidate" and r.get("score") is not None]
        if runs:
            latest = runs[0]["score"]        # tail: newest first
            baseline = runs[-1]["score"]     # oldest del tail
            fitness_knowledge = {
                "latest_score": latest, "baseline_score": baseline,
                "delta": round(float(latest) - float(baseline), 4), "runs": len(runs)}
        else:
            fitness_knowledge = {"latest_score": None, "baseline_score": None,
                                 "delta": None, "runs": 0}
    except Exception:  # noqa: BLE001
        fitness_knowledge = {"latest_score": None, "baseline_score": None,
                             "delta": None, "runs": 0}

    try:
        retire = ks.retire_suggestions()
    except Exception:  # noqa: BLE001
        retire = []

    return jsonify({
        "ok": True, "lessons": lessons_kpi, "coverage": coverage,
        "flywheel": flywheel, "usage": usage,
        "fitness_knowledge": fitness_knowledge, "retire_suggestions": retire,
    })


# --------------------------------------------------------------------------- #
# Vista previa de inyección (ADICIÓN ARQUITECTO) — DRY-RUN, sin registrar uso
# --------------------------------------------------------------------------- #
@bp.get("/knowledge/injection-preview")
def injection_preview():
    from services import knowledge_store as ks
    agent_type = request.args.get("agent_type") or None
    project = request.args.get("project") or None
    query = request.args.get("query") or None
    matched = ks.active_lessons_for(agent_type, project)
    block = ks.build_lessons_block(matched, query=query, top_n=_top_n(),
                                   max_chars=_max_chars())
    return jsonify({"ok": True, "block": block, "matched_count": len(matched)})
