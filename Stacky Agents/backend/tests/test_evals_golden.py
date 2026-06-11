"""F3.1 — Tests del golden-set eval harness.

Verifica: (1) el runner carga golden sets, (2) corre contract_validator como juez,
(3) detecta fallos cuando un output no cumple las assertions, (4) todos los golden
sets congelados del repo pasan (gate de no-regresión contra ediciones de .agent.md).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from evals import golden_runner  # noqa: E402
from evals.golden_runner import GoldenCase, _evaluate  # noqa: E402


def test_list_agents_finds_golden_sets():
    agents = golden_runner.list_agents()
    assert "qa" in agents
    assert "functional" in agents


def test_all_committed_golden_sets_pass():
    """Gate de no-regresión: ningún golden set del repo debe fallar."""
    grouped = golden_runner.run_all()
    assert grouped, "no se encontraron golden sets"
    failures = [
        (agent, r.case.name, r.reasons)
        for agent, results in grouped.items()
        for r in results
        if not r.ok
    ]
    assert not failures, f"golden sets fallidos: {failures}"


def test_runner_detects_min_score_violation():
    """Un output que no cumple el contrato debe marcar ok=False con razón."""
    bad = GoldenCase(
        name="qa_empty",
        agent_type="qa",
        output="no puedo determinar el resultado",  # sin VERDICT, frase de evasión
        expect={"min_score": 90, "must_pass": True},
    )
    res = _evaluate(bad)
    assert res.ok is False
    assert res.reasons


def test_runner_no_contract_for_unknown_agent_passes():
    """Agente sin contrato definido: contract_validator devuelve score 100, passed."""
    case = GoldenCase(
        name="unknown",
        agent_type="agente-inexistente",
        output="cualquier cosa",
        expect={"min_score": 100, "must_pass": True},
    )
    res = _evaluate(case)
    assert res.ok is True
    assert res.score == 100
