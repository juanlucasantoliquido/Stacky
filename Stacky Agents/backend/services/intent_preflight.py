"""Plan 41 — Pre-vuelo de Intención.

Antes de gastar un run completo, Stacky genera una pasada corta que declara
"esto entendí y así lo haría" (IntentBrief). El operador lo aprueba/corrige.
Todo gobernado por flags default OFF → con OFF, comportamiento byte-idéntico.

F0: contrato (dataclasses + (de)serialización tolerante).
F1: generador con runtime inyectado (invoke_short_llm) + fallback explícito.
F2: ranking de supuestos + derivación de preguntas de alto ROI (determinista).
F3: bloque de correcciones del operador (máxima prioridad).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace

PREFLIGHT_VERSION = "1"

CORRECTIONS_BLOCK_ID = "operator-corrections"

_IMPACT_ORDER = {"high": 0, "medium": 1, "low": 2}


class PreflightRuntimeUnavailable(Exception):
    """El runtime elegido no puede ejecutar la pasada corta del pre-vuelo."""


@dataclass(frozen=True)
class IntentAssumption:
    text: str
    impact: str  # "high" | "medium" | "low"
    needs_confirmation: bool


@dataclass(frozen=True)
class IntentBrief:
    objective: str
    deliverables: list[str]
    assumptions: list[IntentAssumption]
    open_questions: list[str]
    areas: list[str]
    confidence: float
    version: str = PREFLIGHT_VERSION


def _clamp01(value) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, v))


def _safe_json_loads(raw: str | None):
    """Parsea JSON tolerando fences ```json y texto antes/después. None si no hay JSON."""
    if not raw or not str(raw).strip():
        return None
    text = str(raw).strip()
    # Quitar fences markdown si los hay.
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass
    # Último intento: extraer el primer objeto {...} balanceado de forma laxa.
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except (ValueError, TypeError):
            return None
    return None


def from_model_json(raw: str | None) -> IntentBrief:
    """Parsea la salida del modelo a IntentBrief, tolerante a campos faltantes.

    raw vacío/no-JSON → IntentBrief con confidence 0.0 (fuerza revisión humana).
    NUNCA lanza.
    """
    data = _safe_json_loads(raw)
    if not isinstance(data, dict):
        return IntentBrief(
            objective="", deliverables=[], assumptions=[],
            open_questions=[], areas=[], confidence=0.0,
        )
    assumptions = [
        IntentAssumption(
            text=str(a.get("text", "")),
            impact=a.get("impact") if a.get("impact") in ("high", "medium", "low") else "medium",
            needs_confirmation=bool(a.get("needs_confirmation", False)),
        )
        for a in (data.get("assumptions") or [])
        if isinstance(a, dict) and a.get("text")
    ]
    return IntentBrief(
        objective=(data.get("objective") or "").strip(),
        deliverables=[d for d in (data.get("deliverables") or []) if d],
        assumptions=assumptions,
        open_questions=[q for q in (data.get("open_questions") or []) if q],
        areas=[s for s in (data.get("areas") or []) if s],
        confidence=_clamp01(data.get("confidence", 0.5)),
    )


def to_payload(brief: IntentBrief) -> dict:
    """Serializa a dict JSON-safe para el frontend, redactando secretos."""
    from services import pii_masker

    def _r(s: str) -> str:
        return pii_masker.redact_irreversible(s or "")

    return {
        "objective": _r(brief.objective),
        "deliverables": [_r(d) for d in brief.deliverables],
        "assumptions": [
            {"text": _r(a.text), "impact": a.impact, "needs_confirmation": a.needs_confirmation}
            for a in brief.assumptions
        ],
        "open_questions": [_r(q) for q in brief.open_questions],
        "areas": [_r(s) for s in brief.areas],
        "confidence": brief.confidence,
        "version": brief.version,
    }


# ── F1 — Generador del pre-vuelo ──────────────────────────────────────────────

PREFLIGHT_SYSTEM_PROMPT = (
    "Sos el módulo de Pre-vuelo de Intención de Stacky. NO resuelvas la tarea. "
    "Tu único trabajo es DECLARAR brevemente qué entendiste del pedido y cómo lo "
    "abordarías, para que el operador confirme antes de gastar un run completo. "
    "Devolvé EXCLUSIVAMENTE un JSON con las claves: objective (str), deliverables "
    "(list[str]), assumptions (list de {text, impact in [high,medium,low], "
    "needs_confirmation bool}), open_questions (list[str] — SOLO preguntas de alto "
    "impacto y baratas de responder; si todo está claro, lista vacía), areas "
    "(list[str] — archivos/módulos/datos/procesos que tocarías; nombrá procesos "
    "batch concretos, nunca 'el batch'), confidence (float 0..1). Sé conciso. "
    "NO incluyas secretos, contraseñas ni tokens."
)


def _build_user_prompt(brief_text: str, context_summary: str) -> str:
    parts = ["## Brief del operador\n" + brief_text.strip()]
    if (context_summary or "").strip():
        parts.append("## Contexto del proyecto (resumen)\n" + context_summary.strip())
    parts.append(
        "Devolvé SOLO el JSON del Brief de Intención (sin texto adicional)."
    )
    return "\n\n".join(parts)


def generate_intent_brief(
    *,
    brief_text: str,
    context_summary: str,
    runtime: str,
    project_name: str | None,
    invoke_short_llm,
    log,
) -> IntentBrief | None:
    """Genera el IntentBrief con una pasada corta. None si no se puede (fallback)."""
    if not (brief_text or "").strip():
        return None
    user_prompt = _build_user_prompt(brief_text, context_summary)
    try:
        raw = invoke_short_llm(PREFLIGHT_SYSTEM_PROMPT, user_prompt, runtime, project_name)
    except PreflightRuntimeUnavailable as exc:
        log(f"[preflight] runtime '{runtime}' no disponible para pre-vuelo: {exc}")
        return None
    except Exception as exc:  # noqa: BLE001 — best-effort, nunca rompe el flujo
        log(f"[preflight] fallo generando intent brief: {exc}")
        return None
    return from_model_json(raw)


# ── F2 — Ranking de supuestos + preguntas de alto ROI (determinista) ──────────

def derive_open_questions(
    assumptions: list[IntentAssumption], existing: list[str]
) -> list[str]:
    """Por cada supuesto high-impact con needs_confirmation, agrega una pregunta."""
    out = list(existing)
    seen = {q.strip().lower() for q in existing}
    for a in assumptions:
        if a.impact == "high" and a.needs_confirmation:
            q = f"¿Confirmás que: {a.text}?"
            if q.strip().lower() not in seen:
                out.append(q)
                seen.add(q.strip().lower())
    return out


def rank_and_flag(brief: IntentBrief) -> IntentBrief:
    """Ordena assumptions por impacto (high primero) y deriva preguntas. Determinista."""
    ranked = sorted(brief.assumptions, key=lambda a: _IMPACT_ORDER.get(a.impact, 1))
    questions = derive_open_questions(ranked, brief.open_questions)
    return replace(brief, assumptions=ranked, open_questions=questions)


# ── F3 — Bloque de correcciones del operador (máxima prioridad) ───────────────

def build_corrections_block(corrections: str) -> list:
    """Devuelve [1 context block] de máxima prioridad con las correcciones del operador.

    Redacta secretos por si el operador pegó algo sensible. id=operator-corrections
    está registrado con prioridad máxima en context_enrichment._BLOCK_PRIORITY.
    """
    from services import pii_masker

    safe = pii_masker.redact_irreversible(corrections.strip())
    text = (
        "### Correcciones del operador (OBLIGATORIO, mandan sobre supuestos)\n" + safe
    )
    return [{
        "id": CORRECTIONS_BLOCK_ID,
        "kind": "text",
        "title": "Correcciones del operador",
        "content": text,
    }]
