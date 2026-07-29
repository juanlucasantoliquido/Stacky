"""Plan 267 F3 — Contrato de propuesta de accion.

Calca el molde de services/intent_preflight.py:39-47 (IntentBrief) a proposito:
mismos campos de intencion (open_questions, confidence, version) sobre un objeto
que ademas nombra la ACCION. NO se inventa un contrato nuevo.

PURO: sin flask, sin IO, sin red, sin modelo. Este modulo solo ARMA la propuesta;
el matching vive en el endpoint y la ejecucion en el frontend.
"""
from __future__ import annotations

from dataclasses import dataclass

# v2 [C17]: el v1 importaba ademas get_action, ActionMatch, is_ambiguous y
# match_intent, y NO usaba ninguno.
from services.devops_action_catalog import DevOpsAction, param_of

PROPOSAL_VERSION = "1"

_IMPACT_LABEL = {"none": "sin impacto", "low": "impacto bajo", "high": "impacto alto"}

BLOCKED_NONE = ""
BLOCKED_NO_MATCH = "no_match"
BLOCKED_AMBIGUOUS = "ambiguous"
BLOCKED_MISSING_PARAMS = "missing_params"
BLOCKED_FLAG_OFF = "flag_off"
BLOCKED_AGENT_WRITE_DISABLED = "agent_write_disabled"

#: Los 6 estados que la consola de F6 tiene que saber pintar.
BLOCKED_REASONS = (
    BLOCKED_NONE,
    BLOCKED_NO_MATCH,
    BLOCKED_AMBIGUOUS,
    BLOCKED_MISSING_PARAMS,
    BLOCKED_FLAG_OFF,
    BLOCKED_AGENT_WRITE_DISABLED,
)


@dataclass(frozen=True)
class ProposalParam:
    name: str
    value: str
    source: str   # "operator" | "default" | "missing"


@dataclass(frozen=True)
class ActionProposal:
    action_id: str
    label: str
    summary: str
    section_id: str | None
    nav_path: str
    effect: str
    impact: str
    targets_environment: bool
    environment: str            # "" si la accion no apunta a un entorno
    params: list[ProposalParam]
    what_will_happen: str       # 1 frase determinista en castellano
    open_questions: list[str]   # 1 por param required faltante
    alternatives: list[str]     # action_ids alternativos si hubo ambiguedad
    confidence: float           # score del matcher, 0.0 .. 1.0
    needs_confirmation: bool    # SIEMPRE True si effect == "write"
    blocked_reason: str         # una de las constantes BLOCKED_*
    version: str = PROPOSAL_VERSION


def describe(action: DevOpsAction, environment: str) -> str:
    """Frase determinista de 'que va a pasar'. Sin modelo. NUNCA lanza."""
    donde = f"sobre el entorno {environment}" if environment else "sobre el proyecto activo"
    efecto = ("Escribe en un sistema real del operador."
              if action.effect == "write"
              else "Solo lectura: no cambia nada.")
    impacto = _IMPACT_LABEL.get(action.impact, action.impact)
    return f"{action.label} {donde}. {impacto}. {efecto}"


def build_proposal(
    action: DevOpsAction,
    supplied: dict,
    confidence: float,
    alternatives: list[str],
    agent_write_enabled: bool,
) -> ActionProposal:
    """Arma la propuesta. NO ejecuta nada. NUNCA lanza."""
    params: list[ProposalParam] = []
    missing: list[str] = []
    for p in action.params:
        raw = (supplied or {}).get(p.name)
        if raw is not None and str(raw).strip():
            params.append(ProposalParam(p.name, str(raw).strip(), "operator"))
        elif p.default:
            params.append(ProposalParam(p.name, p.default, "default"))
        else:
            params.append(ProposalParam(p.name, "", "missing"))
            if p.required:
                missing.append(p.name)

    env = ""
    if action.targets_environment:
        for pp in params:
            if pp.name == "environment" and pp.value:
                env = pp.value
                break

    blocked = BLOCKED_NONE
    if action.effect == "write" and not agent_write_enabled:
        blocked = BLOCKED_AGENT_WRITE_DISABLED
    elif missing:
        blocked = BLOCKED_MISSING_PARAMS

    return ActionProposal(
        action_id=action.id, label=action.label, summary=action.summary,
        section_id=action.section_id, nav_path=action.nav_path,
        effect=action.effect, impact=action.impact,
        targets_environment=action.targets_environment, environment=env,
        params=params, what_will_happen=describe(action, env),
        open_questions=[
            f"¿Qué valor uso para «{(param_of(action, n).label if param_of(action, n) else n)}»?"
            for n in missing
        ],
        alternatives=list(alternatives or []),
        confidence=round(float(confidence), 4),
        needs_confirmation=(action.effect == "write"),
        blocked_reason=blocked,
    )


def proposal_to_dict(p: ActionProposal) -> dict:
    """Serializacion 1:1, listas planas. json.dumps-able sin custom encoder."""
    return {
        "action_id": p.action_id,
        "label": p.label,
        "summary": p.summary,
        "section_id": p.section_id,
        "nav_path": p.nav_path,
        "effect": p.effect,
        "impact": p.impact,
        "targets_environment": p.targets_environment,
        "environment": p.environment,
        "params": [
            {"name": pp.name, "value": pp.value, "source": pp.source}
            for pp in p.params
        ],
        "what_will_happen": p.what_will_happen,
        "open_questions": list(p.open_questions),
        "alternatives": list(p.alternatives),
        "confidence": p.confidence,
        "needs_confirmation": p.needs_confirmation,
        "blocked_reason": p.blocked_reason,
        "version": p.version,
    }
