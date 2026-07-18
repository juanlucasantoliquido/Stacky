"""Plan 167 F3 — Ciclo MAPE on-demand.

Monitor→Analyze→Plan (Execute vive en F2, gateado por humano). Lee SOLO
telemetría existente (costos/ejecuciones/incidencias/tablero de planes),
aplica las reglas deterministas R-A1..R-A4, opcionalmente pule la redacción
con el LLM local dentro de un presupuesto de tokens, y persiste la corrida.
El LLM redacta, NUNCA decide: la señal determinista decide QUÉ.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from config import config as _cfg  # G1
from services import evolution_apply as ap
from services import evolution_store as store

_CYCLE_LOCK = threading.Lock()  # single-flight
_WINDOW_DAYS = 14
# C4 — agent_runner marca AMBOS status en fallos reales (p.ej. "failed" y "error").
_ERROR_STATUSES = ("error", "failed")
_INCIDENT_TERMINAL = ("publicada", "error")

_ANALYZE_SYSTEM = (
    "Sos el redactor del Centro de Evolución de Stacky. Recibís señales de telemetría "
    "y una lista de borradores de propuesta ya decididos por reglas deterministas. "
    "Tu ÚNICA tarea es mejorar title y rationale de cada borrador (más claros, "
    "específicos y accionables, en castellano). Respondé SOLO JSON con el shape "
    '{"proposals": [{"index": <int>, "title": "...", "rationale": "..."}]}. '
    "PROHIBIDO crear, eliminar o reordenar borradores."
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _parse_iso(value) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:  # noqa: BLE001
        return None


# ── Monitor ─────────────────────────────────────────────────────────────────
def collect_signals() -> dict:
    """Shape EXACTO §4.6. Cada fuente en su propio try/except: una fuente caída
    produce su clave con {"error": <msg>} y el ciclo sigue."""
    signals: dict = {"generated_at": _now_iso(), "window_days": _WINDOW_DAYS}

    # executions + costs (UNA sola query a cost_analytics).
    try:
        from services import cost_analytics as ca

        records = ca.load_records(ca.CostFilters(days=_WINDOW_DAYS))
        by_agent: dict = {}
        by_model: dict = {}
        total_usd = 0.0
        for r in records:
            at = r.agent_type or "desconocido"
            slot = by_agent.setdefault(at, {"total": 0, "errors": 0})
            slot["total"] += 1
            if (r.status or "") in _ERROR_STATUSES:
                slot["errors"] += 1
            usd = float(r.row.cost_usd or 0.0) if ca._billable(r.row.cost_kind) else 0.0
            total_usd += usd
            model = r.row.model or "desconocido"
            by_model[model] = by_model.get(model, 0.0) + usd
        for slot in by_agent.values():
            slot["error_rate"] = round(slot["errors"] / slot["total"], 6) if slot["total"] else 0.0
        top_model = None
        top_share = 0.0
        if by_model and total_usd > 0:
            top_model = max(by_model, key=lambda k: by_model[k])
            top_share = round(by_model[top_model] / total_usd, 6)
        signals["executions"] = {"total": len(records), "by_agent_type": by_agent}
        signals["costs"] = {
            "total_usd": round(total_usd, 6), "by_model": by_model,
            "top_model": top_model, "top_model_share": top_share,
        }
    except Exception as exc:  # noqa: BLE001
        signals["executions"] = {"error": str(exc)}
        signals["costs"] = {"error": str(exc)}

    # incidents
    try:
        from services import incident_store

        items = incident_store.list_incidents()
        now = datetime.now(timezone.utc)
        non_terminal = 0
        stale = 0
        for it in items:
            status = it.get("status") or ""
            if status not in _INCIDENT_TERMINAL:
                non_terminal += 1
                created = _parse_iso(it.get("created_at"))
                if created is not None and (now - created) > timedelta(hours=48):
                    stale += 1
        signals["incidents"] = {"total": len(items), "non_terminal": non_terminal, "stale_48h": stale}
    except Exception as exc:  # noqa: BLE001
        signals["incidents"] = {"error": str(exc)}

    # plans
    try:
        from services import plans_board

        board = plans_board.get_board_cached()
        totals = board.get("totals") or {}
        cards = board.get("plans") or []
        drift = sum(1 for c in cards if (c.get("ledger") or {}).get("doc_drift") is True)
        signals["plans"] = {
            "total": totals.get("total", 0),
            "propuestos": totals.get("PROPUESTO", 0),
            "criticados": totals.get("CRITICADO", 0),
            "drift": drift,
            "unpushed": totals.get("unpushed", 0),
            "next_free_number": board.get("next_free_number") or 0,
        }
    except Exception as exc:  # noqa: BLE001
        signals["plans"] = {"error": str(exc)}

    return signals


# ── Analyze (reglas deterministas §4.6) ─────────────────────────────────────
def _stale_incidents_summary() -> str:
    lines: list[str] = []
    try:
        from services import incident_store

        for it in incident_store.list_incidents():
            if (it.get("status") or "") not in _INCIDENT_TERMINAL:
                lines.append(
                    f"- {it.get('id')} · {it.get('title') or '(sin título)'} · {it.get('status')}"
                )
    except Exception:  # noqa: BLE001
        pass
    body = "\n".join(lines) if lines else "(sin detalle disponible)"
    return "Incidencias sin cierre (>48 h):\n" + body


def analyze(signals: dict) -> list[dict]:
    specs: list[dict] = []

    ex = signals.get("executions")
    if isinstance(ex, dict) and "error" not in ex:
        worst = None
        for agent_type, slot in (ex.get("by_agent_type") or {}).items():
            total = slot.get("total", 0)
            rate = slot.get("error_rate", 0.0)
            if rate >= 0.3 and total >= 5:
                if worst is None or rate > worst[1].get("error_rate", 0.0):
                    worst = (agent_type, slot)
        if worst is not None:
            agent_type, slot = worst
            specs.append({
                "aspect_id": "agent_prompts", "artifact_type": "free_text",
                "title": (f"Revisar prompt/flujo del agente {agent_type}: "
                          f"{slot.get('errors', 0)}/{slot.get('total', 0)} ejecuciones con error en 14 días"),
                "rationale": ("La tasa de error de este agente supera el umbral (30% en 14 días). "
                              "Revisar su .agent.md o su flujo para reducir fallos."),
                "evidence": ["R-A1", f"{agent_type}: {slot.get('errors', 0)}/{slot.get('total', 0)}"],
                "proposed_content": None,
            })

    costs = signals.get("costs")
    if isinstance(costs, dict) and "error" not in costs:
        share = costs.get("top_model_share", 0.0)
        total_usd = costs.get("total_usd", 0.0)
        top_model = costs.get("top_model")
        if share >= 0.6 and total_usd >= 1.0:
            pct = round(share * 100)
            specs.append({
                "aspect_id": "config_flags_models", "artifact_type": "free_text",
                "title": (f"Concentración de costo: {top_model} explica {pct}% del gasto de 14 días "
                          "— evaluar modelo/effort más económico para tareas mecánicas"),
                "rationale": ("Un solo modelo concentra la mayor parte del gasto. Evaluar rutear "
                              "las tareas mecánicas a un modelo/effort más económico."),
                "evidence": ["R-A2", f"{top_model}={pct}% de USD {total_usd}"],
                "proposed_content": None,
            })

    inc = signals.get("incidents")
    if isinstance(inc, dict) and "error" not in inc:
        stale = inc.get("stale_48h", 0)
        if stale >= 3:
            specs.append({
                "aspect_id": "knowledge_rag", "artifact_type": "knowledge_note",
                "title": (f"Lección: hay {stale} incidencias sin cierre hace más de 48 h "
                          "— documentar el patrón de bloqueo detectado"),
                "rationale": ("Varias incidencias no terminales llevan más de 48 h abiertas. "
                              "Documentar el patrón de bloqueo como lección de conocimiento."),
                "evidence": ["R-A3", f"stale_48h={stale}"],
                "proposed_content": _stale_incidents_summary(),
            })

    plans = signals.get("plans")
    if isinstance(plans, dict) and "error" not in plans:
        drift = plans.get("drift", 0)
        if drift >= 1:
            specs.append({
                "aspect_id": "stacky_codebase", "artifact_type": "free_text",
                "title": (f"{drift} plan(es) con drift doc-vs-aprobación en el Tablero de Planes "
                          "— corresponde re-supervisar"),
                "rationale": ("Hay planes cuyo documento cambió respecto de la aprobación registrada. "
                              "Corresponde re-supervisarlos en el Tablero de Planes."),
                "evidence": ["R-A4", f"drift={drift}"],
                "proposed_content": None,
            })

    return specs


# ── Plan / enriquecimiento LLM ──────────────────────────────────────────────
def enrich_with_llm(draft_specs: list[dict], signals: dict) -> tuple[list[dict], dict]:
    info = {"llm_used": False, "llm_error": None, "tokens_est_in": 0,
            "tokens_est_out": 0, "signals_truncated": False}
    if not draft_specs:
        return draft_specs, info

    budget = int(getattr(_cfg, "STACKY_EVOLUTION_CYCLE_TOKEN_BUDGET", 20000))
    drafts_payload = [
        {"index": i, "title": s["title"], "rationale": s["rationale"]}
        for i, s in enumerate(draft_specs)
    ]
    user = json.dumps({"signals": signals, "drafts": drafts_payload}, ensure_ascii=False)
    if _estimate_tokens(user) > budget:
        user = user[: budget * 4] + "[TRUNCADO_POR_PRESUPUESTO]"  # C8
        info["signals_truncated"] = True
    info["tokens_est_in"] = _estimate_tokens(user)

    try:
        from copilot_bridge import invoke_local_llm

        resp = invoke_local_llm(
            agent_type="evolution_analyze", system=_ANALYZE_SYSTEM, user=user,
            on_log=lambda level, msg: None, execution_id=None, model=None,
        )
    except Exception as exc:  # noqa: BLE001 — DEGRADACIÓN DECLARADA (RuntimeError, timeout, etc.)
        info["llm_used"] = False
        info["llm_error"] = str(exc)
        return draft_specs, info

    info["llm_used"] = True
    text = resp.text or ""
    info["tokens_est_out"] = _estimate_tokens(text)
    try:
        start = text.find("{")
        parsed = json.loads(text[start:]) if start >= 0 else None
        for u in (parsed or {}).get("proposals") or []:
            idx = u.get("index")
            if isinstance(idx, int) and 0 <= idx < len(draft_specs):
                if u.get("title"):
                    draft_specs[idx]["title"] = u["title"]
                if u.get("rationale"):
                    draft_specs[idx]["rationale"] = u["rationale"]
    except Exception:  # noqa: BLE001 — parse tolerante: specs sin tocar
        pass
    return draft_specs, info


# ── run_cycle ───────────────────────────────────────────────────────────────
def _error_record(cid: str, started: str, exc: Exception) -> dict:
    return {
        "id": cid, "started_at": started, "finished_at": _now_iso(),
        "status": "error", "error": str(exc), "aspects": [],
        "signals": {}, "signals_truncated": False,
        "rules_fired": [], "proposal_ids": [], "skipped_duplicate_rules": [],
        "llm_used": False, "llm_error": None, "tokens_est_in": 0, "tokens_est_out": 0,
    }


def run_cycle(*, aspects: list[str] | None = None, use_llm: bool = True) -> dict:
    if store.evolution_hard_disabled():  # A1
        raise RuntimeError("evolution_hard_disabled")
    if not _CYCLE_LOCK.acquire(blocking=False):
        raise RuntimeError("cycle_already_running")
    cid = "cyc-" + uuid4().hex
    started = _now_iso()
    try:
        try:
            store.ensure_seed_aspects()
            signals = collect_signals()
            specs = analyze(signals)
            if aspects:
                wanted = set(aspects)
                specs = [s for s in specs if s["aspect_id"] in wanted]
            info = {"llm_used": False, "llm_error": None, "tokens_est_in": 0,
                    "tokens_est_out": 0, "signals_truncated": False}
            if use_llm:
                specs, info = enrich_with_llm(specs, signals)

            # C5 — dedup contra propuestas abiertas por (aspect_id, evidence[0]).
            open_props = [p for p in store.list_proposals()
                          if p.get("status") in ("draft", "pending_review")]
            open_keys = {
                (p.get("aspect_id"), (p.get("evidence") or [None])[0]) for p in open_props
            }
            rules_fired: list[str] = []
            proposal_ids: list[str] = []
            skipped: list[str] = []
            for s in specs:
                rule_id = s["evidence"][0]
                key = (s["aspect_id"], rule_id)
                if key in open_keys:
                    skipped.append(rule_id)
                    continue
                created = store.create_proposal(
                    aspect_id=s["aspect_id"], title=s["title"], rationale=s["rationale"],
                    origin="mape", artifact_type=s["artifact_type"],
                    proposed_content=s.get("proposed_content"),
                    evidence=s["evidence"], initial_status="draft", cycle_id=cid, actor="mape",
                )
                rules_fired.append(rule_id)
                proposal_ids.append(created["id"])
                open_keys.add(key)
                ap.maybe_auto_apply(created)  # no-op salvo flag HOTL ON

            record = {
                "id": cid, "started_at": started, "finished_at": _now_iso(),
                "status": "completed", "error": None,
                "aspects": list(aspects) if aspects else [a["id"] for a in store.list_aspects()],
                "signals": signals, "signals_truncated": info["signals_truncated"],
                "rules_fired": rules_fired, "proposal_ids": proposal_ids,
                "skipped_duplicate_rules": skipped,
                "llm_used": info["llm_used"], "llm_error": info["llm_error"],
                "tokens_est_in": info["tokens_est_in"], "tokens_est_out": info["tokens_est_out"],
            }
            store.append_cycle(record)
            store.append_ledger({"event": "cycle", "cycle_id": cid, "actor": "mape",
                                 "note": f"rules_fired={rules_fired}"})
            return record
        except Exception as exc:  # noqa: BLE001 — persistir el error y devolverlo (no re-raise)
            record = _error_record(cid, started, exc)
            try:
                store.append_cycle(record)
            except Exception:  # noqa: BLE001
                pass
            return record
    finally:
        _CYCLE_LOCK.release()
