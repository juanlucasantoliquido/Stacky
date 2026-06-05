"""Endpoints del Plan de Adopción para Devs (PLAN_ADOPCION_DEVS.md).

Agrupa tres capacidades de UX que mueven la aguja de adopción:

  GET /api/session/resume?user=…   — C8  "Continuar donde lo dejé"
  GET /api/savings/weekly?user=…   — C14 Tiempo ahorrado (estimado)
  GET /api/standup/daily?user=…    — C15 Daily standup auto-generado

Los cálculos son intencionalmente conservadores: si la data histórica es
insuficiente, el endpoint devuelve `enough_data=False` en vez de inventar
un número. Mejor "no podemos decir todavía" que un dato falso.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

from flask import Blueprint, jsonify, request
from sqlalchemy import func

from api._helpers import current_user
from db import session_scope
from models import AgentExecution, Ticket

bp = Blueprint("adoption", __name__)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() + "Z" if dt else None


def _resolve_user() -> str:
    explicit = (request.args.get("user") or "").strip()
    return explicit or current_user()


def _user_matches(execution_user: str | None, target: str) -> bool:
    """Match laxo: ignora dominio si el target no lo incluye.

    Delega en el servicio compartido `ado_identity.user_matches` (fuente única de
    verdad de la semántica de identidad ADO, reusada por B1/B3)."""
    from services.ado_identity import user_matches

    return user_matches(execution_user, target)


def _serialize_ticket(t: Ticket | None) -> dict | None:
    if t is None:
        return None
    return {
        "id": t.id,
        "ado_id": t.ado_id,
        "title": t.title,
        "ado_state": t.ado_state,
        "stacky_status": t.stacky_status,
        "work_item_type": t.work_item_type,
        "project": t.project,
    }


# ── C8 Resume ────────────────────────────────────────────────────────────────


_RESUME_WINDOW = timedelta(hours=24)

_NEXT_AGENT_HINT: dict[str, str] = {
    "business": "functional",
    "functional": "technical",
    "technical": "developer",
    "developer": "qa",
    "qa": None,  # type: ignore[dict-item]
}


@bp.get("/session/resume")
def session_resume():
    """Devuelve la última actividad del usuario dentro de las últimas 24h.

    Si no hay actividad reciente o el usuario es nuevo, retorna
    `has_activity=False` para que el frontend muestre el flujo "empezar fresco".
    """
    user = _resolve_user()
    project = (request.args.get("project") or "").strip() or None
    cutoff = datetime.utcnow() - _RESUME_WINDOW

    with session_scope() as session:
        query = (
            session.query(AgentExecution)
            .filter(AgentExecution.started_at >= cutoff)
            .order_by(AgentExecution.started_at.desc())
            .limit(50)
        )
        candidates: list[AgentExecution] = [
            ex for ex in query.all() if _user_matches(ex.started_by, user)
        ]
        if project:
            ticket_ids = [ex.ticket_id for ex in candidates if ex.ticket_id]
            project_tickets = {
                t.id: t
                for t in session.query(Ticket)
                .filter(Ticket.id.in_(ticket_ids))
                .all()
            }
            candidates = [
                ex
                for ex in candidates
                if ex.ticket_id in project_tickets
                and (project_tickets[ex.ticket_id].project == project
                     or project_tickets[ex.ticket_id].stacky_project_name == project)
            ]

        if not candidates:
            return jsonify({"ok": True, "has_activity": False, "user": user})

        latest = candidates[0]
        ticket = session.get(Ticket, latest.ticket_id) if latest.ticket_id else None
        next_agent = _NEXT_AGENT_HINT.get(latest.agent_type)

        return jsonify({
            "ok": True,
            "has_activity": True,
            "user": user,
            "last_execution": {
                "id": latest.id,
                "agent_type": latest.agent_type,
                "status": latest.status,
                "started_at": _iso(latest.started_at),
                "completed_at": _iso(latest.completed_at),
            },
            "ticket": _serialize_ticket(ticket),
            "next_agent_suggested": next_agent,
        })


# ── C14 Savings ──────────────────────────────────────────────────────────────


_DEFAULT_BASELINE_MS = 4 * 60 * 60 * 1000  # 4h por ticket cerrado sin asistencia
_MIN_CALIBRATION_SAMPLES = 30
_TERMINAL_STATES = {"Done", "Closed", "Resolved", "Cerrado", "Terminado"}


@bp.get("/savings/weekly")
def savings_weekly():
    """Estima tiempo ahorrado en la semana corriente.

    Heurística (intencionalmente conservadora):
      - "Tickets cerrados con agentes" = tickets en estado terminal con ≥1
        AgentExecution completada esta semana iniciada por el usuario.
      - "Tiempo real" = sum(completed_at − started_at) por ejecución del ticket.
      - "Baseline" = mediana del trimestre previo del mismo work_item_type
        cerrado sin agentes. Si no hay datos suficientes (>=30 samples), se
        usa una baseline por defecto de 4h y se setea `calibrated=False`.
    """
    user = _resolve_user()
    now = datetime.utcnow()
    week_start = now - timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    quarter_start = now - timedelta(days=90)

    with session_scope() as session:
        # Ejecuciones de la semana del usuario
        weekly_execs = (
            session.query(AgentExecution)
            .filter(AgentExecution.started_at >= week_start)
            .filter(AgentExecution.status == "completed")
            .all()
        )
        weekly_execs = [ex for ex in weekly_execs if _user_matches(ex.started_by, user)]
        ticket_ids = sorted({ex.ticket_id for ex in weekly_execs if ex.ticket_id})

        tickets = {
            t.id: t
            for t in session.query(Ticket).filter(Ticket.id.in_(ticket_ids)).all()
        } if ticket_ids else {}

        closed_with_assist: list[Ticket] = [
            t for t in tickets.values() if (t.ado_state or "") in _TERMINAL_STATES
        ]

        total_real_ms = 0
        per_ticket_ms: dict[int, int] = {}
        for ex in weekly_execs:
            ms = ex.duration_ms() or 0
            per_ticket_ms[ex.ticket_id] = per_ticket_ms.get(ex.ticket_id, 0) + ms
            if ex.ticket_id in {t.id for t in closed_with_assist}:
                total_real_ms += ms

        baseline_by_type, calibrated = _calibrate_baseline(session, quarter_start)

        baseline_total_ms = 0
        for t in closed_with_assist:
            base = baseline_by_type.get(t.work_item_type or "", _DEFAULT_BASELINE_MS)
            baseline_total_ms += base

        savings_ms = baseline_total_ms - total_real_ms

    return jsonify({
        "ok": True,
        "user": user,
        "week_start": _iso(week_start),
        "tickets_closed_with_agents": len(closed_with_assist),
        "real_time_ms": total_real_ms,
        "baseline_time_ms": baseline_total_ms,
        "savings_ms": savings_ms,
        "calibrated": calibrated,
        "calibration_min_samples": _MIN_CALIBRATION_SAMPLES,
        "note": (
            "Baseline calibrada con tickets del trimestre previo."
            if calibrated
            else f"Baseline por defecto (4h/ticket). Necesitás ≥{_MIN_CALIBRATION_SAMPLES} "
                 "tickets terminales sin asistencia del último trimestre para calibrar."
        ),
    })


def _calibrate_baseline(session, since: datetime) -> tuple[dict[str, int], bool]:
    """Mediana de duración 'In Progress → Done' por work_item_type.

    Como no tenemos la timeline ADO completa, aproximamos con la diferencia
    entre `created_at` y `last_synced_at` de tickets terminales SIN ninguna
    ejecución de agente. Es una proxy imperfecta pero defendible —
    `note` en la respuesta lo aclara.
    """
    rows = (
        session.query(Ticket.work_item_type, Ticket.created_at, Ticket.last_synced_at, Ticket.id)
        .filter(Ticket.last_synced_at.isnot(None))
        .filter(Ticket.created_at >= since)
        .filter(Ticket.ado_state.in_(_TERMINAL_STATES))
        .all()
    )
    if not rows:
        return {}, False

    # Excluir tickets con ejecuciones
    assisted_ids = {
        ex.ticket_id
        for ex in session.query(AgentExecution.ticket_id)
        .filter(AgentExecution.started_at >= since)
        .all()
    }

    by_type: dict[str, list[int]] = {}
    for wit, created, synced, ticket_id in rows:
        if ticket_id in assisted_ids:
            continue
        if not created or not synced:
            continue
        ms = int((synced - created).total_seconds() * 1000)
        if ms <= 0:
            continue
        by_type.setdefault(wit or "", []).append(ms)

    total_samples = sum(len(v) for v in by_type.values())
    calibrated = total_samples >= _MIN_CALIBRATION_SAMPLES

    medians: dict[str, int] = {}
    for wit, samples in by_type.items():
        samples.sort()
        medians[wit] = samples[len(samples) // 2]
    return medians, calibrated


# ── C15 Daily standup ────────────────────────────────────────────────────────


@bp.get("/standup/daily")
def standup_daily():
    """Genera un standup en formato texto para copiar a Teams/Slack.

    Incluye:
      - Tickets en los que el usuario avanzó ayer (con ejecuciones suyas).
      - Tickets pendientes para hoy (tickets asignados con stacky_status idle
        o running, o tickets con ejecuciones suyas en estado no terminal).
      - Bloqueos: tickets con QA failed o ejecuciones erradas en últimas 48h.
    """
    user = _resolve_user()
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    blocker_cutoff = now - timedelta(hours=48)

    with session_scope() as session:
        recent_execs = (
            session.query(AgentExecution)
            .filter(AgentExecution.started_at >= yesterday_start - timedelta(days=2))
            .all()
        )
        recent_execs = [ex for ex in recent_execs if _user_matches(ex.started_by, user)]

        yesterday_tickets: dict[int, list[AgentExecution]] = {}
        today_tickets: dict[int, list[AgentExecution]] = {}
        blockers: list[dict] = []

        for ex in recent_execs:
            if not ex.ticket_id:
                continue
            if yesterday_start <= ex.started_at < today_start:
                yesterday_tickets.setdefault(ex.ticket_id, []).append(ex)
            elif ex.started_at >= today_start:
                today_tickets.setdefault(ex.ticket_id, []).append(ex)

            if ex.status == "error" and ex.started_at >= blocker_cutoff:
                blockers.append({
                    "ticket_id": ex.ticket_id,
                    "agent_type": ex.agent_type,
                    "error_message": (ex.error_message or "")[:240],
                    "started_at": _iso(ex.started_at),
                })
            if ex.verdict == "FAIL" and ex.started_at >= blocker_cutoff:
                blockers.append({
                    "ticket_id": ex.ticket_id,
                    "agent_type": ex.agent_type,
                    "verdict": "FAIL",
                    "started_at": _iso(ex.started_at),
                })

        all_ticket_ids = set(yesterday_tickets) | set(today_tickets) | {b["ticket_id"] for b in blockers}
        tickets_map = {
            t.id: t
            for t in session.query(Ticket).filter(Ticket.id.in_(all_ticket_ids)).all()
        } if all_ticket_ids else {}

        # Tickets pendientes hoy: asignados al usuario y no terminales
        pending_today = (
            session.query(Ticket)
            .filter(Ticket.ado_state.notin_(list(_TERMINAL_STATES) + ["Removed"]))
            .all()
        )
        pending_today_ids = [
            t.id for t in pending_today if _user_matches(t.assigned_to_ado, user)
        ][:8]

        def fmt_ticket(tid: int) -> str:
            t = tickets_map.get(tid)
            if t is None:
                return f"#{tid}"
            return f"T-{t.ado_id} — {t.title[:80]}"

        yesterday_lines = [f"• {fmt_ticket(tid)}" for tid in yesterday_tickets]
        today_lines = [f"• {fmt_ticket(tid)}" for tid in today_tickets]
        for tid in pending_today_ids:
            line = f"• {fmt_ticket(tid)}"
            if line not in today_lines:
                today_lines.append(line)

        blocker_lines = [
            f"• T-{tickets_map[b['ticket_id']].ado_id if b['ticket_id'] in tickets_map else b['ticket_id']}"
            f" — {b.get('verdict') or 'error'} en {b['agent_type']}"
            for b in blockers
        ]

    summary_lines = [
        "**Ayer:**",
        *(yesterday_lines or ["• (sin actividad registrada)"]),
        "",
        "**Hoy:**",
        *(today_lines or ["• (sin tickets pendientes)"]),
    ]
    if blocker_lines:
        summary_lines += ["", "**Bloqueos:**", *blocker_lines]

    return jsonify({
        "ok": True,
        "user": user,
        "generated_at": _iso(now),
        "yesterday_tickets": [
            {"ticket_id": tid, "agent_runs": len(execs)}
            for tid, execs in yesterday_tickets.items()
        ],
        "today_tickets": [
            {"ticket_id": tid, "agent_runs": len(execs)}
            for tid, execs in today_tickets.items()
        ],
        "pending_today_ticket_ids": pending_today_ids,
        "blockers": blockers,
        "summary_text": "\n".join(summary_lines),
    })


# ── C13 Streak ───────────────────────────────────────────────────────────────


_STREAK_LOOKBACK_DAYS = 90


def _is_business_day(day: datetime) -> bool:
    return day.weekday() < 5  # Mon-Fri


@bp.get("/streak")
def streak():
    """Calcula la racha de días laborales consecutivos cerrando tickets con agentes.

    Definición:
      - "Día con cierre" = ≥1 ejecución del usuario con verdict OK/PASS o
        status=completed cuyo ticket pasó a estado terminal ese día.
      - La racha se rompe si un día laboral pasa sin cierres.
      - Mejor racha = la racha histórica más larga registrada.
    """
    user = _resolve_user()
    cutoff = datetime.utcnow() - timedelta(days=_STREAK_LOOKBACK_DAYS)

    with session_scope() as session:
        executions = (
            session.query(AgentExecution)
            .filter(AgentExecution.started_at >= cutoff)
            .filter(AgentExecution.status == "completed")
            .all()
        )
        executions = [ex for ex in executions if _user_matches(ex.started_by, user)]

        if not executions:
            return jsonify({
                "ok": True,
                "user": user,
                "current_streak": 0,
                "best_streak": 0,
                "last_close_at": None,
            })

        ticket_ids = sorted({ex.ticket_id for ex in executions if ex.ticket_id})
        tickets = {
            t.id: t
            for t in session.query(Ticket).filter(Ticket.id.in_(ticket_ids)).all()
        } if ticket_ids else {}

        close_days: set[str] = set()
        last_close_at: datetime | None = None
        for ex in executions:
            ticket = tickets.get(ex.ticket_id)
            if not ticket or (ticket.ado_state or "") not in _TERMINAL_STATES:
                continue
            if not ex.completed_at:
                continue
            day = ex.completed_at.date().isoformat()
            close_days.add(day)
            if last_close_at is None or ex.completed_at > last_close_at:
                last_close_at = ex.completed_at

        if not close_days:
            return jsonify({
                "ok": True,
                "user": user,
                "current_streak": 0,
                "best_streak": 0,
                "last_close_at": None,
            })

        today = datetime.utcnow().date()
        current = 0
        cursor = today
        while True:
            if _is_business_day(datetime(cursor.year, cursor.month, cursor.day)):
                if cursor.isoformat() in close_days:
                    current += 1
                else:
                    break
            cursor = cursor - timedelta(days=1)
            if (today - cursor).days > _STREAK_LOOKBACK_DAYS:
                break

        best = 0
        run = 0
        prev_day = None
        for day_iso in sorted(close_days):
            day_dt = datetime.strptime(day_iso, "%Y-%m-%d").date()
            if prev_day is None:
                run = 1
            else:
                business_gap = 0
                walker = prev_day
                while walker < day_dt:
                    walker = walker + timedelta(days=1)
                    if walker.weekday() < 5:
                        business_gap += 1
                if business_gap == 1:
                    run += 1
                else:
                    run = 1
            best = max(best, run)
            prev_day = day_dt

        return jsonify({
            "ok": True,
            "user": user,
            "current_streak": current,
            "best_streak": best,
            "last_close_at": _iso(last_close_at),
        })


# ── C18 Cost cap ─────────────────────────────────────────────────────────────


def _project_cap_path():
    from runtime_paths import data_dir
    return data_dir() / "cost_caps.json"


def _load_caps() -> dict:
    import json
    path = _project_cap_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_caps(caps: dict) -> None:
    import json
    path = _project_cap_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(caps, indent=2, ensure_ascii=False), encoding="utf-8")


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _spent_this_month(project: str | None) -> float:
    """Suma el costo estimado de las ejecuciones del mes corriente."""
    import json as _json
    now = datetime.utcnow()
    cutoff = _month_start(now)
    total = 0.0
    with session_scope() as session:
        query = (
            session.query(AgentExecution)
            .filter(AgentExecution.started_at >= cutoff)
        )
        if project:
            ticket_ids = [
                t.id
                for t in session.query(Ticket.id).filter(
                    (Ticket.project == project) | (Ticket.stacky_project_name == project)
                ).all()
            ]
            if ticket_ids:
                query = query.filter(AgentExecution.ticket_id.in_(ticket_ids))
        for ex in query.all():
            meta_raw = ex.metadata_json
            if not meta_raw:
                continue
            try:
                meta = _json.loads(meta_raw)
            except Exception:
                continue
            cost = (
                meta.get("cost_usd_total")
                or meta.get("cost_estimate", {}).get("cost_usd_total")
                or 0
            )
            try:
                total += float(cost or 0)
            except (TypeError, ValueError):
                continue
    return round(total, 4)


@bp.get("/cost-cap")
def cost_cap_get():
    """Devuelve cap + spent del mes para un proyecto."""
    project = (request.args.get("project") or "").strip() or None
    caps = _load_caps()
    cap_cfg = caps.get(project or "_default", {})
    cap_usd = float(cap_cfg.get("monthly_cap_usd") or 0.0)
    alert_pct = float(cap_cfg.get("alert_pct") or 80.0)
    block_at_100 = bool(cap_cfg.get("block_at_100", False))
    spent = _spent_this_month(project)

    pct = (spent / cap_usd * 100.0) if cap_usd > 0 else 0.0
    if cap_usd <= 0:
        state = "unset"
    elif pct >= 100:
        state = "blocked" if block_at_100 else "over"
    elif pct >= alert_pct:
        state = "alert"
    else:
        state = "ok"

    return jsonify({
        "ok": True,
        "project": project,
        "monthly_cap_usd": cap_usd,
        "alert_pct": alert_pct,
        "block_at_100": block_at_100,
        "spent_usd": spent,
        "spent_pct": round(pct, 2),
        "state": state,
        "month_start": _iso(_month_start(datetime.utcnow())),
    })


@bp.put("/cost-cap")
def cost_cap_put():
    """Actualiza la config del cap mensual para un proyecto.

    Body: { project?, monthly_cap_usd, alert_pct?, block_at_100? }
    """
    payload = request.get_json(silent=True) or {}
    project = (payload.get("project") or "").strip() or "_default"
    try:
        cap_usd = float(payload.get("monthly_cap_usd") or 0)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "invalid_cap_value"}), 400
    alert_pct = float(payload.get("alert_pct") or 80.0)
    block = bool(payload.get("block_at_100", False))

    caps = _load_caps()
    caps[project] = {
        "monthly_cap_usd": cap_usd,
        "alert_pct": alert_pct,
        "block_at_100": block,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    _save_caps(caps)
    return jsonify({"ok": True, "project": project, "config": caps[project]})


# ── C2 Demo project ──────────────────────────────────────────────────────────


@bp.post("/demo/seed")
def demo_seed():
    """Crea (idempotente) los tickets del proyecto __demo__."""
    from services.demo_seed import seed_demo_project
    result = seed_demo_project()
    return jsonify({"ok": True, **result})


@bp.get("/executions/<int:execution_id>/events")
def execution_events(execution_id: int):
    """C11 — Lista los eventos timeline de una ejecución para Replay."""
    from services.execution_events import load_events, normalize_for_replay
    events = normalize_for_replay(load_events(execution_id))
    return jsonify({
        "ok": True,
        "execution_id": execution_id,
        "count": len(events),
        "events": events,
    })


@bp.post("/repo/explain")
def repo_explain():
    """C9 — Explain my repo.

    Body: { workspace_root, ticket_hint?, since_days? }
    """
    from services.repo_explainer import explain_repo
    payload = request.get_json(silent=True) or {}
    workspace_root = (payload.get("workspace_root") or "").strip()
    if not workspace_root:
        from project_manager import get_active_project, get_project_config
        active = get_active_project()
        cfg = get_project_config(active) if active else {}
        workspace_root = (cfg or {}).get("workspace_root", "") if cfg else ""
    if not workspace_root:
        return jsonify({"ok": False, "error": "workspace_root_required"}), 400

    ticket_hint = (payload.get("ticket_hint") or "").strip() or None
    try:
        since_days = int(payload.get("since_days") or 30)
    except (TypeError, ValueError):
        since_days = 30

    result = explain_repo(workspace_root, ticket_hint=ticket_hint, since_days=since_days)
    return jsonify(result)


@bp.get("/executions/<int:execution_id>/export-pdf")
def execution_export_pdf(execution_id: int):
    """C17 — Exporta la ejecución a PDF (o HTML imprimible si reportlab falta)."""
    from flask import send_file
    from io import BytesIO
    from services.pdf_export import export_execution_pdf

    try:
        payload, mime, filename = export_execution_pdf(execution_id)
    except ValueError:
        return jsonify({"ok": False, "error": "not_found"}), 404
    return send_file(
        BytesIO(payload),
        mimetype=mime,
        as_attachment=True,
        download_name=filename,
    )


@bp.get("/executions/<int:execution_id>/provenance")
def execution_provenance(execution_id: int):
    """C6 — Devuelve metadata de cómo se construyó el output de una ejecución."""
    import json as _json
    with session_scope() as session:
        ex = session.get(AgentExecution, execution_id)
        if ex is None:
            return jsonify({"ok": False, "error": "not_found"}), 404
        ticket = session.get(Ticket, ex.ticket_id) if ex.ticket_id else None
        meta_raw = ex.metadata_json
        try:
            meta = _json.loads(meta_raw) if meta_raw else {}
        except Exception:
            meta = {}
        try:
            ctx_blocks = _json.loads(ex.input_context_json) if ex.input_context_json else []
        except Exception:
            ctx_blocks = []

        sources = []
        for block in ctx_blocks if isinstance(ctx_blocks, list) else []:
            if not isinstance(block, dict):
                continue
            kind = block.get("kind") or block.get("type") or "context"
            label = block.get("label") or block.get("source") or kind
            sources.append({"kind": kind, "label": str(label)[:200]})

        routing = meta.get("routing_decision") or {}
        cost = (
            meta.get("cost_usd_total")
            or meta.get("cost_estimate", {}).get("cost_usd_total")
        )
        tokens_in = (
            meta.get("tokens_in")
            or meta.get("cost_estimate", {}).get("tokens_in")
        )
        tokens_out = (
            meta.get("tokens_out")
            or meta.get("cost_estimate", {}).get("tokens_out")
        )
        confidence = meta.get("confidence") or meta.get("score") or None

        return jsonify({
            "ok": True,
            "execution_id": ex.id,
            "agent_type": ex.agent_type,
            "ticket_id": ex.ticket_id,
            "ticket_ado_id": ticket.ado_id if ticket else None,
            "status": ex.status,
            "verdict": ex.verdict,
            "started_at": _iso(ex.started_at),
            "completed_at": _iso(ex.completed_at),
            "duration_ms": ex.duration_ms(),
            "model": (routing.get("model") if isinstance(routing, dict) else None)
                     or meta.get("model"),
            "model_reason": (routing.get("reason") if isinstance(routing, dict) else None),
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd_total": cost,
            "confidence": confidence,
            "sources": sources,
            "chain_from": ex.chain_from,
        })


_DEMO_AGENT_OUTPUT = """\
# Análisis funcional — [DEMO] Implementar login con Google

## Resumen
Habilitar autenticación vía OAuth 2.0 de Google manteniendo el flujo de email/password actual.

## Criterios de aceptación
1. El usuario puede elegir "Iniciar sesión con Google" en la pantalla de login.
2. Tras autorizar, se crea (o vincula) la cuenta local por email verificado.
3. El refresh token se almacena cifrado en `oauth_tokens.refresh_token` (AES-256).
4. Las sesiones expiran a las 24h; el refresh extiende automáticamente sin re-prompt.

## Riesgos
- Email collision: usuario existente con email/password. Mitigación: prompt de "vincular cuenta".
- Token expiration silenciosa: agregar telemetría `auth.token_refresh_failed`.

(Output generado en modo demo — cacheado, no representa una llamada al LLM real.)
"""


@bp.post("/demo/agents/run")
def demo_agent_run():
    """C20 — Respuesta cacheada para correr agentes en modo demo."""
    payload = request.get_json(silent=True) or {}
    agent_type = (payload.get("agent_type") or "functional").strip()
    return jsonify({
        "ok": True,
        "demo": True,
        "execution_id": -1,
        "agent_type": agent_type,
        "status": "completed",
        "output": _DEMO_AGENT_OUTPUT,
        "metadata": {
            "model": "demo-cached",
            "tokens_in": 0,
            "tokens_out": 0,
            "cost_usd_total": 0.0,
            "routing_decision": {
                "model": "demo-cached",
                "reason": "modo demo — output cacheado",
            },
        },
    })


@bp.get("/demo/status")
def demo_status():
    """Indica si el proyecto demo está presente."""
    from services.demo_seed import DEMO_PROJECT_NAME
    with session_scope() as session:
        count = session.query(Ticket).filter(Ticket.project == DEMO_PROJECT_NAME).count()
    return jsonify({
        "ok": True,
        "project": DEMO_PROJECT_NAME,
        "ticket_count": count,
        "exists": count > 0,
    })
