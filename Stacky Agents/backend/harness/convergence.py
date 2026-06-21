"""Plan 58 — Bucle de convergencia de calidad determinista.

PURO: sin LLM, sin red, sin reloj, sin disco, sin datos personales. Toda la
interacción con el mundo entra por callables inyectados (send_fn, reextract_fn,
evaluate_fn). Determinismo total dado el mismo input.

Reusa el VEREDICTO de harness.epic_gate.evaluate_epic_gate (via evaluate_fn) y
el PATRÓN de services.acceptance_gate.attempt_acceptance_repair (send_fn +
supports_resume + budget). NO genera contenido por sí mismo.
"""
from __future__ import annotations

from typing import Callable, NamedTuple

from harness.capabilities import CAPABILITIES
from harness.epic_gate import GateDecision, GateVerdict


class ConvergenceResult(NamedTuple):
    converged: bool            # True si el último veredicto fue PASS
    iterations: int            # nº de PASES CORRECTIVOS efectivamente enviados
    final_decision: str        # GateDecision.value del último veredicto
    stop_reason: str           # ver constantes STOP_* abajo
    defects_first: list        # _all_defects del PRIMER veredicto (sorted)
    defects_last: list         # _all_defects del ÚLTIMO veredicto (sorted)
    global_budget_spent: int   # nº de envíos consumidos del cap compartido (== iterations)


# stop_reason canónicos (strings estables para telemetría/tests):
STOP_CONVERGED = "converged"
STOP_BUDGET_EXHAUSTED = "budget_exhausted"
STOP_BUDGET_REACHED_GLOBAL = "budget_reached_global"  # C2: cap compartido agotado
STOP_NO_RESUME = "degraded_no_resume"
STOP_NEEDS_REVIEW = "needs_review_terminal"
STOP_NO_PROGRESS = "no_progress"
STOP_DISABLED = "disabled"
STOP_SEND_FAILED = "send_failed"


def _all_defects(verdict: GateVerdict) -> list:
    """C3 — combina structural_defects + regression_defects (plan 56) sorted.

    El anti-loop debe ver TODOS los defectos reparables; comparar solo
    structural_defects declararía 'sin progreso' falsamente si el pase movió
    un regression_defect. GateVerdict.regression_defects existe (epic_gate.py:31).
    """
    return sorted(list(verdict.structural_defects) + list(verdict.regression_defects))


def run_convergence_loop(
    *,
    enabled: bool,
    runtime: str,
    max_iterations: int,
    initial_verdict: GateVerdict,
    build_repair_message: Callable[[GateVerdict], str],
    send_fn: Callable[[str], object] | None,
    reextract_and_evaluate_fn: Callable[[], GateVerdict],
) -> ConvergenceResult:
    """Ejecuta el lazo determinista de convergencia de calidad.

    Reglas deterministas (en orden ESTRICTO):
      1. Si not enabled -> STOP_DISABLED (defensa; el caller no debería llamar con OFF).
      2. Si initial PASS -> converged=True, iterations=0, STOP_CONVERGED.
      3. Si initial NEEDS_REVIEW -> converged=False, iterations=0, STOP_NEEDS_REVIEW.
      4. runtime sin supports_resume o send_fn=None -> STOP_NO_RESUME, iterations=0.
      4b. max_iterations <= 0 -> STOP_BUDGET_REACHED_GLOBAL, iterations=0 (C2).
      5. Bucle while sent < cap and decision==REPAIR.
      6. Devolver ConvergenceResult completo.

    NUNCA lanza: cualquier excepción de send_fn → STOP_SEND_FAILED.
    """
    defects_start = _all_defects(initial_verdict)
    sent = 0

    try:
        # Regla 1: flag OFF (defensa)
        if not enabled:
            return ConvergenceResult(
                converged=(initial_verdict.decision == GateDecision.PASS),
                iterations=0,
                final_decision=initial_verdict.decision.value,
                stop_reason=STOP_DISABLED,
                defects_first=defects_start,
                defects_last=defects_start,
                global_budget_spent=0,
            )

        # Regla 2: ya convergió
        if initial_verdict.decision == GateDecision.PASS:
            return ConvergenceResult(
                converged=True,
                iterations=0,
                final_decision=GateDecision.PASS.value,
                stop_reason=STOP_CONVERGED,
                defects_first=defects_start,
                defects_last=defects_start,
                global_budget_spent=0,
            )

        # Regla 3: no reparable inline
        if initial_verdict.decision == GateDecision.NEEDS_REVIEW:
            return ConvergenceResult(
                converged=False,
                iterations=0,
                final_decision=GateDecision.NEEDS_REVIEW.value,
                stop_reason=STOP_NEEDS_REVIEW,
                defects_first=defects_start,
                defects_last=defects_start,
                global_budget_spent=0,
            )

        # Regla 4: runtime sin resume o send_fn inexistente
        cap_rt = CAPABILITIES.get(runtime)
        if cap_rt is None or not cap_rt.supports_resume or send_fn is None:
            return ConvergenceResult(
                converged=False,
                iterations=0,
                final_decision=initial_verdict.decision.value,
                stop_reason=STOP_NO_RESUME,
                defects_first=defects_start,
                defects_last=defects_start,
                global_budget_spent=0,
            )

        # Regla 4b: cap compartido agotado (C2)
        if max_iterations <= 0:
            return ConvergenceResult(
                converged=False,
                iterations=0,
                final_decision=initial_verdict.decision.value,
                stop_reason=STOP_BUDGET_REACHED_GLOBAL,
                defects_first=defects_start,
                defects_last=defects_start,
                global_budget_spent=0,
            )

        # Regla 5: bucle de convergencia
        cap = max_iterations
        current = initial_verdict
        stop_reason = STOP_BUDGET_EXHAUSTED

        while sent < cap and current.decision == GateDecision.REPAIR:
            msg = build_repair_message(current)
            try:
                ok = send_fn(msg)
            except Exception:  # noqa: BLE001
                stop_reason = STOP_SEND_FAILED
                break
            if not ok:
                stop_reason = STOP_SEND_FAILED
                break
            sent += 1
            nxt = reextract_and_evaluate_fn()
            if nxt.decision == GateDecision.PASS:
                current = nxt
                stop_reason = STOP_CONVERGED
                break
            if nxt.decision == GateDecision.NEEDS_REVIEW:
                current = nxt
                stop_reason = STOP_NEEDS_REVIEW
                break
            if _all_defects(nxt) == _all_defects(current):
                current = nxt
                stop_reason = STOP_NO_PROGRESS
                break
            current = nxt  # siguió REPAIR con defectos distintos

        # Regla 6: resultado final
        return ConvergenceResult(
            converged=(current.decision == GateDecision.PASS),
            iterations=sent,
            final_decision=current.decision.value,
            stop_reason=stop_reason,
            defects_first=defects_start,
            defects_last=_all_defects(current),
            global_budget_spent=sent,
        )

    except Exception:  # noqa: BLE001
        return ConvergenceResult(
            converged=False,
            iterations=sent,
            final_decision=initial_verdict.decision.value,
            stop_reason=STOP_SEND_FAILED,
            defects_first=defects_start,
            defects_last=defects_start,
            global_budget_spent=sent,
        )


def build_convergence_payload(conv: ConvergenceResult) -> dict:
    """Helper PURA que serializa un ConvergenceResult al dict de metadata."""
    return {
        "attempted": conv.iterations > 0,
        "converged": conv.converged,
        "iterations": conv.iterations,
        "final_decision": conv.final_decision,
        "stop_reason": conv.stop_reason,
        "defects_first": list(conv.defects_first),
        "defects_last": list(conv.defects_last),
        "global_budget_spent": conv.global_budget_spent,
    }


def should_use_convergence_loop(
    *,
    convergence_enabled: bool,
    epic_repair_enabled: bool,
) -> bool:
    """Decide si el runner debe usar el bucle de convergencia."""
    return convergence_enabled and epic_repair_enabled
