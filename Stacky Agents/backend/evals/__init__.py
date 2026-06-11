"""F3.1 — Eval harness por agente con golden set.

Por cada agent_type activo, un golden set de outputs congelados + assertions
(contract score mínimo, passed). El juez barato es `contract_validator`
(reusa los contratos ya definidos por agente). Sin LLM, determinístico.

Uso:
    python -m evals run <agent_type>     # corre el golden set de un agente
    python -m evals run all              # corre todos
    python -m evals list                 # lista golden sets disponibles

Gate sugerido (no bloqueante al inicio): correr esto al editar un .agent.md
para detectar regresiones antes de producción (B8).
"""
from __future__ import annotations

from .golden_runner import (
    GoldenCase,
    GoldenResult,
    list_agents,
    load_golden_set,
    run_agent,
    run_all,
)

__all__ = [
    "GoldenCase",
    "GoldenResult",
    "list_agents",
    "load_golden_set",
    "run_agent",
    "run_all",
]
