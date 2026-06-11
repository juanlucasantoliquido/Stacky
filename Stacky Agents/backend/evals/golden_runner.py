"""F3.1 — Golden-set runner para agentes Stacky.

Cada golden set vive en `evals/agents/<agent_type>/*.json` con el shape:

    {
      "name": "developer_happy_path",
      "agent_type": "developer",
      "output": "<texto del output del agente, congelado>",
      "expect": {
        "min_score": 80,          # contract score mínimo (0-100)
        "must_pass": true,        # contract_result.passed esperado
        "no_warnings": false      # opcional: exigir 0 warnings
      }
    }

El juez es `contract_validator.validate` — barato, determinístico, sin LLM.
No bloquea por defecto: devuelve resultados que el caller decide cómo usar.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import contract_validator

_AGENTS_DIR = Path(__file__).resolve().parent / "agents"


@dataclass
class GoldenCase:
    name: str
    agent_type: str
    output: str
    expect: dict
    source: Path | None = None


@dataclass
class GoldenResult:
    case: GoldenCase
    score: int
    passed_contract: bool
    ok: bool                      # ¿cumplió TODAS las assertions del golden?
    reasons: list[str] = field(default_factory=list)  # por qué falló (si falló)

    def to_dict(self) -> dict:
        return {
            "name": self.case.name,
            "agent_type": self.case.agent_type,
            "score": self.score,
            "passed_contract": self.passed_contract,
            "ok": self.ok,
            "reasons": self.reasons,
        }


def list_agents() -> list[str]:
    """agent_types que tienen golden set."""
    if not _AGENTS_DIR.exists():
        return []
    return sorted(p.name for p in _AGENTS_DIR.iterdir() if p.is_dir())


def load_golden_set(agent_type: str) -> list[GoldenCase]:
    """Carga los casos congelados de un agente."""
    agent_dir = _AGENTS_DIR / agent_type
    if not agent_dir.exists():
        return []
    cases: list[GoldenCase] = []
    for fixture in sorted(agent_dir.glob("*.json")):
        data = json.loads(fixture.read_text(encoding="utf-8"))
        cases.append(
            GoldenCase(
                name=data.get("name", fixture.stem),
                agent_type=data.get("agent_type", agent_type),
                output=data["output"],
                expect=data.get("expect", {}),
                source=fixture,
            )
        )
    return cases


def _evaluate(case: GoldenCase) -> GoldenResult:
    result = contract_validator.validate(case.agent_type, case.output)
    reasons: list[str] = []

    min_score = case.expect.get("min_score")
    if min_score is not None and result.score < min_score:
        reasons.append(f"score {result.score} < min_score {min_score}")

    must_pass = case.expect.get("must_pass")
    if must_pass is not None and result.passed != must_pass:
        reasons.append(f"passed={result.passed}, esperado {must_pass}")

    if case.expect.get("no_warnings") and result.warnings:
        reasons.append(f"{len(result.warnings)} warning(s) inesperado(s)")

    return GoldenResult(
        case=case,
        score=result.score,
        passed_contract=result.passed,
        ok=not reasons,
        reasons=reasons,
    )


def run_agent(agent_type: str) -> list[GoldenResult]:
    """Corre el golden set de un agente. Lista vacía si no hay golden set."""
    return [_evaluate(c) for c in load_golden_set(agent_type)]


def run_all() -> dict[str, list[GoldenResult]]:
    """Corre todos los golden sets disponibles."""
    return {agent: run_agent(agent) for agent in list_agents()}
