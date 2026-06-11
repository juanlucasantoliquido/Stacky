"""H6.3 — Gate suave de evals al guardar un agente.

Expone dos funciones:
- run_evals_for_agent_type(agent_type) → str | None
  Corre el golden set del tipo dado. Retorna None si todo OK o no hay goldens.
  Retorna un string de warning si algún golden falla.

- run_evals_for_agent_type_async(agent_type) → None
  Lanza lo anterior en un thread daemon. No bloquea.

El caller (endpoint de guardado) llama a la versión async y adjunta el resultado
en la respuesta como `evals_warning`. El guardado NUNCA se bloquea.
"""
from __future__ import annotations

import logging
import threading

from evals import golden_runner

logger = logging.getLogger("stacky_agents.evals.eval_gate")


def run_evals_for_agent_type(agent_type: str) -> str | None:
    """Corre el golden set del agent_type. Thread-safe, sin efectos secundarios.

    Retorna
    -------
    None
        Si no hay golden set para el tipo o todos los casos pasan.
    str
        Mensaje de warning con los casos fallidos (para incluir en la respuesta
        del endpoint o loguear como warning).
    """
    try:
        results = golden_runner.run_agent(agent_type)
    except Exception as exc:
        logger.warning("eval_gate: error corriendo goldens de '%s': %s", agent_type, exc)
        return f"Error al correr evals de '{agent_type}': {exc}"

    if not results:
        return None  # sin golden set = sin gate

    failures = [r for r in results if not r.ok]
    if not failures:
        return None

    lines = [f"[eval-gate] {len(failures)} golden(s) fallaron para agent_type='{agent_type}':"]
    for r in failures:
        detail = "; ".join(r.reasons) if r.reasons else "sin razón"
        lines.append(f"  FAIL {r.case.name}: {detail}")
    return "\n".join(lines)


def run_evals_for_agent_type_async(agent_type: str) -> None:
    """Lanza run_evals_for_agent_type en un thread daemon. No bloquea.

    El resultado se loguea como warning si hay fallos. El caller puede ignorar
    el thread por completo: el guardado ya completó antes de que esto corra.
    """
    def _run() -> None:
        warning = run_evals_for_agent_type(agent_type)
        if warning:
            logger.warning(warning)
        else:
            logger.debug(
                "eval_gate: todos los goldens OK para agent_type='%s'", agent_type
            )

    t = threading.Thread(target=_run, daemon=True, name=f"eval-gate-{agent_type}")
    t.start()
