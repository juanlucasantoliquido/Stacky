"""I3.3 — Asesor de caps de contexto por telemetría.

Produce SUGERENCIAS (nunca escribe). El operador las aplica manualmente
editando `STACKY_MEMORY_CAPS_JSON` (M0.1).

API pública:
  - `suggest_caps(project, days=30) -> dict`
      {agent_type: {current_cap, suggested_cap, rationale, sample_size}}

Heurística (transparente):
  - Si runs con MÁS contexto NO mejoran contract_score/confidence respecto
    a runs con MENOS contexto → sugerir bajar el cap (10..20%).
  - Si runs con MENOS contexto tienen MAYOR tasa de needs_review → sugerir
    subir el cap (10..20%).
  - `sample_size < 5` → no sugerir para ese agente (evidencia insuficiente).
  - Flags: `STACKY_CAPS_ADVISOR_ENABLED` (bool, default false).

CRÍTICO: esta función NUNCA escribe nada. El test verifica que ningún setter
sea invocado (ver test_caps_advisor.py).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger("stacky.context_caps_advisor")

# Umbral mínimo de muestras para generar sugerencia.
MIN_SAMPLE_SIZE = 5
# Factor de cambio para las sugerencias (±20%).
_CHANGE_FACTOR = 0.20


def _parse_meta(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _get_input_tokens(md: dict) -> int | None:
    """Extrae input_tokens de harness_telemetry o None."""
    telem = md.get("harness_telemetry")
    if isinstance(telem, dict):
        v = telem.get("input_tokens")
        if v is not None:
            try:
                return int(v)
            except (TypeError, ValueError):
                pass
    return None


def _get_quality(md: dict) -> tuple[int | None, int | None]:
    """Retorna (contract_score 0-100, confidence 0-100)."""
    cs = md.get("contract_score")
    conf = md.get("confidence")
    if isinstance(conf, dict):
        conf = conf.get("overall")
    try:
        cs = int(cs) if cs is not None else None
    except (TypeError, ValueError):
        cs = None
    try:
        conf = int(conf) if conf is not None else None
    except (TypeError, ValueError):
        conf = None
    return cs, conf


def _current_cap(agent_type: str) -> int:
    """Cap actual de memorias para el agente (max_memorias)."""
    try:
        from services.memory_store import _AGENT_CAPS, _DEFAULT_CAP
        caps = _AGENT_CAPS
        key = (agent_type or "").strip().lower()
        cap, _ = caps.get(key, _DEFAULT_CAP)
        # M0.1 — override vía env var
        import os
        raw_override = (os.getenv("STACKY_MEMORY_CAPS_JSON") or "").strip()
        if raw_override:
            try:
                override = json.loads(raw_override)
                if isinstance(override, dict) and key in override:
                    v = override[key]
                    if isinstance(v, (list, tuple)) and len(v) >= 1:
                        cap = int(v[0])
            except Exception:
                pass
        return cap
    except Exception:
        return 10  # default safe


def suggest_caps(project: str, days: int = 30) -> dict[str, dict]:
    """Analiza telemetría y sugiere caps de memoria por agente.

    Nunca escribe. Devuelve:
      {
        agent_type: {
          "current_cap": int,
          "suggested_cap": int | None,  # None si no hay evidencia suficiente
          "rationale": str,
          "sample_size": int,
        }
      }
    """
    try:
        from db import session_scope
        from models import AgentExecution, Ticket
    except ImportError:
        return {}

    since = datetime.utcnow() - timedelta(days=max(1, days))

    # Leer executions del proyecto en la ventana
    rows: list[tuple[str, int, str, dict]] = []
    try:
        with session_scope() as sess:
            execs = (
                sess.query(AgentExecution)
                .join(Ticket, Ticket.id == AgentExecution.ticket_id)
                .filter(
                    AgentExecution.started_at >= since,
                    Ticket.stacky_project_name == project,
                )
                .all()
            )
            for ex in execs:
                agent_type = ex.agent_type or "unknown"
                status = ex.status or ""
                md = _parse_meta(ex.metadata_json)
                rows.append((agent_type, ex.id, status, md))
    except Exception as e:
        logger.warning("suggest_caps: error leyendo DB: %s", e)
        return {}

    if not rows:
        return {}

    # Agrupar por agent_type
    by_agent: dict[str, list[tuple[int, str, dict]]] = {}
    for agent_type, exec_id, status, md in rows:
        by_agent.setdefault(agent_type, []).append((exec_id, status, md))

    result: dict[str, dict] = {}
    for agent_type, execs_for_agent in by_agent.items():
        sample_size = len(execs_for_agent)
        current_cap = _current_cap(agent_type)

        if sample_size < MIN_SAMPLE_SIZE:
            result[agent_type] = {
                "current_cap": current_cap,
                "suggested_cap": None,
                "rationale": f"Evidencia insuficiente ({sample_size} < {MIN_SAMPLE_SIZE} muestras).",
                "sample_size": sample_size,
            }
            continue

        # Extraer métricas por run
        metrics: list[dict] = []
        for _exec_id, status, md in execs_for_agent:
            input_tok = _get_input_tokens(md) or 0
            cs, conf = _get_quality(md)
            is_needs_review = status == "needs_review"
            metrics.append({
                "input_tokens": input_tok,
                "contract_score": cs,
                "confidence": conf,
                "needs_review": is_needs_review,
            })

        # Separar en mitad "corta" y mitad "larga" por input_tokens
        sorted_by_ctx = sorted(metrics, key=lambda m: m["input_tokens"])
        mid = len(sorted_by_ctx) // 2
        short_half = sorted_by_ctx[:mid]
        long_half = sorted_by_ctx[mid:]

        def _avg_score(group: list[dict]) -> float | None:
            scores = [
                m["contract_score"] for m in group
                if m["contract_score"] is not None
            ]
            if not scores:
                return None
            return sum(scores) / len(scores)

        def _needs_review_rate(group: list[dict]) -> float:
            if not group:
                return 0.0
            return sum(1 for m in group if m["needs_review"]) / len(group)

        short_score = _avg_score(short_half)
        long_score = _avg_score(long_half)
        short_nr = _needs_review_rate(short_half)
        long_nr = _needs_review_rate(long_half)

        suggested_cap: int | None = None
        rationale = "Sin cambio recomendado (métricas similares entre contextos cortos y largos)."

        if short_score is not None and long_score is not None:
            diff = long_score - short_score
            if diff < 2:
                # Más contexto no mejora la calidad → sugerir reducir cap
                new_cap = max(1, round(current_cap * (1 - _CHANGE_FACTOR)))
                if new_cap != current_cap:
                    suggested_cap = new_cap
                    rationale = (
                        f"Más contexto (tokens largos) no mejora contract_score "
                        f"({long_score:.1f} vs cortos {short_score:.1f}). "
                        f"Sugerencia: bajar cap de {current_cap} a {new_cap}."
                    )
        if suggested_cap is None and short_nr > long_nr + 0.1:
            # Contexto corto → más needs_review → sugerir subir cap
            new_cap = round(current_cap * (1 + _CHANGE_FACTOR))
            if new_cap != current_cap:
                suggested_cap = new_cap
                rationale = (
                    f"Runs con contexto corto tienen mayor tasa de needs_review "
                    f"({short_nr:.0%} vs largos {long_nr:.0%}). "
                    f"Sugerencia: subir cap de {current_cap} a {new_cap}."
                )

        result[agent_type] = {
            "current_cap": current_cap,
            "suggested_cap": suggested_cap,
            "rationale": rationale,
            "sample_size": sample_size,
        }

    return result
