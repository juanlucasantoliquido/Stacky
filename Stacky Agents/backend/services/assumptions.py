"""Plan 213 F0 — Vocabulario canónico del supuesto y su parser determinista.

Un analista que no puede confirmar un dato tiene dos salidas honestas: asumirlo
declarándolo, o pedirlo explícitamente. Hoy elige una tercera —dejar el ticket
esperando— y el pipeline se frena. Este módulo define cómo se escribe cada una
de las dos salidas buenas y cómo se leen desde código.

    [SUPUESTO: <afirmación> | base: <evidencia o "sin respaldo"> | impacto: alto|medio|bajo]
    [PENDIENTE: <dato duro imposible de inferir> | necesito: <qué exactamente>]

El parser es deliberadamente tolerante: un LLM puede olvidarse la mitad de las
etiquetas, y eso no puede romper un run. Lo que NO es tolerante es la regla de
impacto: un supuesto sin base declarada es alto, siempre.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from config import config
from services.intent_preflight import _IMPACT_ORDER, IntentAssumption

__all__ = [
    "AssumptionReport",
    "parse",
    "to_metadata",
    "strip_canonical_marks",
    "TEXT_MAX",
    "BASIS_MAX",
    "BLOCKED_MARKER",
]

# Un supuesto desbordado no puede inflar metadata_json, el panel ni el board.
TEXT_MAX = 500
BASIS_MAX = 300

# La frase que hoy usa el Analista Técnico para frenar el ticket sin decir qué
# necesita. Detectarla es el KPI-1 del plan.
BLOCKED_MARKER = "consulta técnica (pre-bloqueo)"

_ASSUMPTION_RE = re.compile(
    r"\[SUPUESTO:\s*(?P<text>[^|\]]+?)"
    r"(?:\s*\|\s*base:\s*(?P<basis>[^|\]]*))?"
    r"(?:\s*\|\s*impacto:\s*(?P<impact>alto|medio|bajo))?"
    r"\s*\]",
    re.IGNORECASE,
)
_PENDING_RE = re.compile(
    r"\[PENDIENTE:\s*(?P<text>[^|\]]+?)"
    r"(?:\s*\|\s*necesito:\s*(?P<needs>[^|\]]*))?\s*\]",
    re.IGNORECASE,
)

_IMPACT_ES = {"alto": "high", "medio": "medium", "bajo": "low"}


@dataclass(frozen=True)
class AssumptionReport:
    assumptions: tuple[IntentAssumption, ...]   # ordenadas: alto → medio → bajo
    pending: tuple[dict, ...]                   # [{"text": ..., "needs": ...}]
    unbased_count: int
    overload: bool                              # supera el techo configurado
    marks_ok: bool                              # hay al menos un marcador canónico
    blocked_without_pending: bool               # frenó el ticket sin decir qué necesita


def _truncate(value: str, limit: int) -> str:
    value = (value or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def _normalize(text: str) -> str:
    """HTML→texto si hace falta: el Analista Técnico escribe comment.html.

    Sin esto el parser no ve NADA de lo que produce ese agente.
    """
    if "<" in text and ">" in text:
        try:
            from services.ado_context import _html_to_text

            return _html_to_text(text)
        except Exception:  # noqa: BLE001 — un HTML raro no puede tumbar el run
            return text
    return text


def _impact_for(basis: str, declarado: str | None) -> str:
    if declarado:
        return _IMPACT_ES.get(declarado.strip().lower(), "medium")
    # Regla dura: sin base declarada, el supuesto es alto. Es lo que obliga al
    # agente a citar evidencia si no quiere que todo requiera confirmación.
    return "medium" if basis else "high"


def _max_per_run() -> int:
    try:
        return int(getattr(config, "STACKY_ASSUMPTION_MAX_PER_RUN", 10) or 10)
    except (TypeError, ValueError):
        return 10


def parse(output: str | None) -> AssumptionReport:
    """Lee supuestos y pendientes de la salida de un agente. NUNCA lanza."""
    if not output:
        return AssumptionReport((), (), 0, False, False, False)

    texto = _normalize(str(output))

    supuestos: list[IntentAssumption] = []
    vistos: set[str] = set()
    for m in _ASSUMPTION_RE.finditer(texto):
        raw_text = _truncate(m.group("text") or "", TEXT_MAX)
        if not raw_text:
            continue
        clave = raw_text.lower()
        if clave in vistos:
            continue
        vistos.add(clave)
        basis = _truncate(m.group("basis") or "", BASIS_MAX)
        impacto = _impact_for(basis, m.group("impact"))
        supuestos.append(IntentAssumption(
            text=raw_text,
            impact=impacto,
            needs_confirmation=(impacto == "high"),
            basis=basis,
        ))

    pendientes: list[dict] = []
    vistos_p: set[str] = set()
    for m in _PENDING_RE.finditer(texto):
        raw_text = _truncate(m.group("text") or "", TEXT_MAX)
        if not raw_text:
            continue
        clave = raw_text.lower()
        if clave in vistos_p:
            continue
        vistos_p.add(clave)
        pendientes.append({
            "text": raw_text,
            "needs": _truncate(m.group("needs") or "", BASIS_MAX),
        })

    supuestos.sort(key=lambda a: _IMPACT_ORDER.get(a.impact, 1))

    return AssumptionReport(
        assumptions=tuple(supuestos),
        pending=tuple(pendientes),
        unbased_count=sum(1 for a in supuestos if not a.basis),
        overload=len(supuestos) > _max_per_run(),
        marks_ok=bool(supuestos or pendientes),
        blocked_without_pending=(
            BLOCKED_MARKER in texto.lower() and not pendientes
        ),
    )


def to_metadata(report: AssumptionReport) -> dict:
    """Bloque listo para fusionar en metadata_patch. Contrato congelado.

    `status` nace SIEMPRE en "pending": solo el operador lo mueve a confirmed o
    corrected. Un agente no se autoconfirma sus propios supuestos.
    """
    return {
        "assumptions": {
            "items": [
                {
                    "text": a.text,
                    "basis": a.basis,
                    "impact": a.impact,
                    "needs_confirmation": a.needs_confirmation,
                    "status": "pending",
                }
                for a in report.assumptions
            ],
            "pending": [dict(p) for p in report.pending],
            "total": len(report.assumptions),
            "unbased_count": report.unbased_count,
            "overload": report.overload,
            "marks_ok": report.marks_ok,
            "blocked_without_pending": report.blocked_without_pending,
        }
    }


def apply_to_metadata(
    agent_type: str,
    output_text: str,
    metadata: dict,
    log=None,
) -> str | None:
    """Plan 213 F4 — Fusiona los supuestos del output en `metadata`, in-place.

    Muta con .update(): jamás reasigna el dict, porque convive con los bloques
    que escriben los planes 210/211 en la misma metadata.

    Devuelve "needs_review" solo si hay overload (un análisis mayormente supuesto
    necesita ojos humanos); None en cualquier otro caso. No-op si la flag está
    OFF o el agente no está en la allowlist. NUNCA lanza.
    """
    try:
        from harness.run_contract import applies_to

        if not applies_to(agent_type or ""):
            return None

        report = parse(output_text or "")
        metadata.update(to_metadata(report))
        return "needs_review" if report.overload else None
    except Exception as exc:  # noqa: BLE001 — nunca puede tumbar un run
        if log:
            try:
                log("warn", f"supuestos: no se pudieron persistir ({exc})")
            except Exception:  # noqa: BLE001
                pass
        return None


def strip_canonical_marks(text: str | None) -> str:
    """Quita los marcadores del texto, dejando el resto intacto.

    Lo usa el scoring: un supuesto declarado no debe leerse como evasión.
    """
    if not text:
        return ""
    sin_supuestos = _ASSUMPTION_RE.sub("", str(text))
    return _PENDING_RE.sub("", sin_supuestos)
