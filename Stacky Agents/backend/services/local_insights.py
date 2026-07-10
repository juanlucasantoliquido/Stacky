"""services/local_insights.py — Plan 117. Insights locales de ejecuciones (IA local, Plan 106).

Núcleo puro (F1): elegibilidad, construcción de prompts, parseo defensivo.
Capa con efectos (F2): persistencia + sweep de fondo. Narrativa del digest (F5).
La llamada al LLM ocurre SIEMPRE fuera de session_scope (no retiene locks de DB).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import requests  # health-gate A1 (F2); dep ya presente en el backend

INSIGHT_KEY = "local_insight"

# Anti-recursión: ejecuciones producidas por el propio modelo local jamás se anotan.
EXCLUDED_AGENT_TYPES = frozenset({
    "local_llm_analyzer",
    "local_llm_pipeline_suggester",
    "local_llm_playground",
    "pr_review_local",
    "local_insights",
})

# Estados que ganan insight. "cancelled" queda FUERA.
TERMINAL_INSIGHT_STATUSES = frozenset({"completed", "error", "needs_review"})

# Caps del contrato §4.
TLDR_MAX = 400
LABEL_MAX = 40
LABELS_MAX_COUNT = 5
TRIAGE_FIELD_MAX = 500
ERROR_MAX = 300
NARRATIVE_MAX = 1200

# Truncado de inputs al prompt.
OUTPUT_HEAD_CHARS = 3000
OUTPUT_TAIL_CHARS = 3000
INPUT_CONTEXT_MAX = 1500

HITL_RULES = (
    "\n\nREGLA ABSOLUTA (HITL):\n"
    "- NUNCA ejecutes comandos.\n"
    "- NUNCA edites archivos.\n"
    "- NUNCA commitees cambios.\n"
    "- NUNCA sugieras comandos que muten el estado del repo.\n"
    "- Solo analizá, explicá y proponé; el operador humano decide qué aplicar.\n"
)


# ── F1 — funciones puras ──────────────────────────────────────────────────────

def truncate_middle(text: str, head: int = OUTPUT_HEAD_CHARS, tail: int = OUTPUT_TAIL_CHARS) -> str:
    text = text or ""
    if len(text) <= head + tail + 40:
        return text
    return text[:head] + "\n... [recortado] ...\n" + text[-tail:]


def execution_view(row) -> dict:
    """Dict mínimo del dominio desde una fila AgentExecution (único punto que toca el ORM)."""
    md = {}
    try:
        md = row.metadata_dict or {}
    except Exception:
        md = {}
    return {
        "id": getattr(row, "id", None),
        "agent_type": getattr(row, "agent_type", "") or "",
        "status": getattr(row, "status", "") or "",
        "error_message": getattr(row, "error_message", "") or "",
        "output": getattr(row, "output", "") or "",
        "input_context_json": getattr(row, "input_context_json", "") or "",
        "started_at": getattr(row, "started_at", None),
        "completed_at": getattr(row, "completed_at", None),
        "metadata": md,
    }


def is_eligible(view: dict) -> tuple[bool, str]:
    if view.get("status") not in TERMINAL_INSIGHT_STATUSES:
        return (False, "status_not_terminal")
    agent_type = view.get("agent_type") or ""
    if agent_type in EXCLUDED_AGENT_TYPES or agent_type.startswith("local_llm_"):
        return (False, "agent_type_excluded")
    if (view.get("metadata") or {}).get("backend") == "local_llm":
        return (False, "local_llm_backend_excluded")
    return (True, "ok")


def should_sweep(view: dict) -> tuple[bool, str]:
    ok, reason = is_eligible(view)
    if not ok:
        return (False, reason)
    if INSIGHT_KEY in (view.get("metadata") or {}):
        return (False, "already_has_insight")
    return (True, "ok")


def _duration_secs(view: dict):
    s, c = view.get("started_at"), view.get("completed_at")
    if s and c:
        try:
            return round((c - s).total_seconds())
        except Exception:
            return None
    return None


def build_insight_prompt(view: dict) -> tuple[str, str]:
    system = ("Sos un ingeniero senior que audita ejecuciones de agentes de IA. Tu ÚNICA tarea "
              "es resumir y diagnosticar en JSON estricto." + HITL_RULES)
    md = view.get("metadata") or {}
    dur = _duration_secs(view)
    parts = [
        "== EJECUCIÓN ==",
        f"id: {view.get('id')}",
        f"agent_type: {view.get('agent_type')}",
        f"status: {view.get('status')}",
        f"duracion_seg: {dur if dur is not None else 'desconocida'}",
        f"runtime: {md.get('runtime') or 'desconocido'}",
        "",
        "== CONTEXTO DE ENTRADA (recortado) ==",
        (view.get("input_context_json") or "")[:INPUT_CONTEXT_MAX],
        "",
        "== OUTPUT (recortado) ==",
        truncate_middle(view.get("output") or ""),
    ]
    if view.get("status") != "completed":
        parts += ["", "== ERROR ==", (view.get("error_message") or "")[:2000]]
    parts += [
        "",
        ('Respondé EXCLUSIVAMENTE con un objeto JSON (sin markdown) con las keys: '
         '{"tldr": "resumen en castellano de 1-3 líneas", "labels": ["hasta 5 etiquetas cortas"], '
         '"risk": "low|medium|high", "probable_cause": "...", "evidence": "...", "next_step": "..."}. '
         'Si el status es completed, poné null en probable_cause, evidence y next_step.'),
    ]
    return system, "\n".join(parts)


def _strip_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def parse_insight_response(text: str) -> dict:
    raw = _strip_fences(text)
    try:
        data = json.loads(raw)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"json_parse_error: {e}")
    if not isinstance(data, dict):
        raise ValueError("json_parse_error: not an object")

    tldr = data.get("tldr")
    if not isinstance(tldr, str) or not tldr.strip():
        raise ValueError("tldr_missing")
    tldr = tldr.strip()[:TLDR_MAX]

    labels_raw = data.get("labels")
    labels: list[str] = []
    if isinstance(labels_raw, list):
        for item in labels_raw:
            if isinstance(item, str) and item.strip():
                labels.append(item.strip()[:LABEL_MAX])
            if len(labels) >= LABELS_MAX_COUNT:
                break

    risk = data.get("risk")
    if risk not in ("low", "medium", "high"):
        risk = "low"

    def _triage(key):
        v = data.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()[:TRIAGE_FIELD_MAX]
        return None

    return {
        "tldr": tldr,
        "labels": labels,
        "risk": risk,
        "probable_cause": _triage("probable_cause"),
        "evidence": _triage("evidence"),
        "next_step": _triage("next_step"),
    }


def make_insight_metadata(parsed: dict, *, model: str, attempts: int) -> dict:
    return {
        **parsed,
        "state": "done",
        "model": model,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "attempts": attempts,
    }


def build_digest_narrative_prompt(digest: dict) -> tuple[str, str]:
    system = ("Sos un analista técnico. Narrás métricas de ejecuciones de agentes en castellano claro, "
              "sin inventar datos." + HITL_RULES)
    payload = {
        "totals": digest.get("totals", {}),
        "by_agent_type": digest.get("by_agent_type", {}),
        "by_runtime": digest.get("by_runtime", {}),
        "top_failures": digest.get("top_failures", []),
        "highlights": digest.get("highlights", []),
    }
    user = (json.dumps(payload, ensure_ascii=False) +
            "\n\nEscribí un resumen narrativo de entre 5 y 8 líneas, en texto plano (sin markdown, "
            "sin listas), mencionando totales, tasa de éxito, el agente más activo y las fallas más "
            "repetidas si las hay. No inventes números que no estén en los datos.")
    return system, user


# ── F2 — persistencia + sweep ─────────────────────────────────────────────────

def _local_llm_reachable(timeout: float = 3.0) -> bool:
    """[A1] Ping barato GET {base}/v1/models antes de cada ciclo (patrón local_health_route)."""
    import config as _config
    endpoint = getattr(_config.config, "LOCAL_LLM_ENDPOINT", "")
    if not endpoint:
        return False
    base = endpoint.split("/v1/")[0] if "/v1/" in endpoint else endpoint
    try:
        return requests.get(f"{base}/v1/models", timeout=timeout).status_code == 200
    except requests.RequestException:
        return False


def pick_candidates(session, *, lookback_days: int, limit: int) -> list:
    """Filas terminadas recientes sin insight, más recientes primero (C3 exclusión en SQL)."""
    from sqlalchemy import or_
    from models import AgentExecution

    cutoff = datetime.utcnow() - timedelta(days=max(1, lookback_days))
    rows = (
        session.query(AgentExecution)
        .filter(AgentExecution.status.in_(sorted(TERMINAL_INSIGHT_STATUSES)))
        .filter(AgentExecution.completed_at.isnot(None))
        .filter(AgentExecution.started_at >= cutoff)
        .filter(~AgentExecution.agent_type.in_(sorted(EXCLUDED_AGENT_TYPES)))  # C3
        .filter(~AgentExecution.agent_type.like("local_llm_%"))                # C3
        .filter(or_(
            AgentExecution.metadata_json.is_(None),
            ~AgentExecution.metadata_json.contains('"local_insight"'),
        ))
        .order_by(AgentExecution.completed_at.desc())
        .limit(max(1, limit) * 4)
        .all()
    )
    keep = [r for r in rows if should_sweep(execution_view(r))[0]]
    return keep[: max(1, limit)]


def _write_insight(execution_id: int, insight: dict) -> None:
    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            return
        md = row.metadata_dict or {}
        md[INSIGHT_KEY] = insight
        row.metadata_dict = md


def _failed_insight(error: Exception, *, attempts: int, model: str) -> dict:
    return {
        "state": "failed",
        "error": str(error)[:ERROR_MAX],
        "attempts": attempts,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "model": model,
    }


def generate_insight_for_execution(
    execution_id: int,
    *,
    force: bool = False,
    persist_bridge_failures: bool = True,
) -> dict:
    """Genera y persiste el insight de UNA ejecución. Nunca lanza: devuelve {"ok": bool, ...}."""
    import config as _config
    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            return {"ok": False, "error": "execution_not_found"}
        view = execution_view(row)

    eligible, reason = is_eligible(view)
    if not eligible:
        return {"ok": False, "error": "insight_excluded", "reason": reason}
    existing = view["metadata"].get(INSIGHT_KEY)
    if existing and not force:
        return {"ok": True, "insight": existing, "cached": True}

    prev_attempts = int((existing or {}).get("attempts") or 0)
    system, user = build_insight_prompt(view)
    model_cfg = getattr(_config.config, "LOCAL_LLM_MODEL", "")

    from copilot_bridge import invoke_local_llm
    try:
        resp = invoke_local_llm(
            agent_type="local_insights",
            system=system,
            user=user,
            on_log=lambda level, msg: None,
            execution_id=execution_id,
        )
    except Exception as e:  # noqa: BLE001 — BRIDGE (transitorio), C2
        if not persist_bridge_failures:
            return {"ok": False, "error": "bridge_failed", "transient": True,
                    "detail": str(e)[:ERROR_MAX]}
        insight = _failed_insight(e, attempts=prev_attempts + 1, model=model_cfg)
        _write_insight(execution_id, insight)
        return {"ok": False, "error": "generation_failed", "insight": insight}

    try:
        parsed = parse_insight_response(resp.text)
    except ValueError as e:  # PARSEO (determinista) → SIEMPRE persiste failed, C2
        insight = _failed_insight(e, attempts=prev_attempts + 1, model=model_cfg)
        _write_insight(execution_id, insight)
        return {"ok": False, "error": "generation_failed", "insight": insight}

    insight = make_insight_metadata(
        parsed,
        model=(getattr(resp, "metadata", None) or {}).get("model") or model_cfg,
        attempts=prev_attempts + 1,
    )
    _write_insight(execution_id, insight)
    return {"ok": True, "insight": insight}


def run_sweep_once() -> int:
    """Un ciclo del barrido. Devuelve cuántas ejecuciones quedaron anotadas OK."""
    import config as _config
    from db import session_scope

    cfg = _config.config
    if not getattr(cfg, "STACKY_LOCAL_INSIGHTS_ENABLED", False):
        return 0
    if not getattr(cfg, "LOCAL_LLM_ENABLED", False):
        return 0
    if not getattr(cfg, "LOCAL_LLM_ENDPOINT", ""):
        return 0
    if not _local_llm_reachable():   # [A1]
        return 0
    limit = max(1, int(getattr(cfg, "STACKY_LOCAL_INSIGHTS_MAX_PER_CYCLE", 3)))
    lookback = max(1, int(getattr(cfg, "STACKY_LOCAL_INSIGHTS_LOOKBACK_DAYS", 7)))

    with session_scope() as session:
        candidate_ids = [r.id for r in pick_candidates(session, lookback_days=lookback, limit=limit)]

    done = 0
    for eid in candidate_ids:
        result = generate_insight_for_execution(eid, persist_bridge_failures=False)
        if result.get("ok"):
            done += 1
        elif result.get("transient"):
            break   # C2 — modelo caído a mitad de ciclo: abortar sin quemar el resto
    return done


# ── F5 — narrativa del digest ─────────────────────────────────────────────────

def narrate_digest(digest: dict) -> str:
    """Narra el digest (compose_digest) con el modelo local. Lanza si el bridge falla."""
    from copilot_bridge import invoke_local_llm

    system, user = build_digest_narrative_prompt(digest)
    resp = invoke_local_llm(
        agent_type="local_insights",
        system=system,
        user=user,
        on_log=lambda level, msg: None,
        execution_id=None,
    )
    return (resp.text or "").strip()[:NARRATIVE_MAX]
