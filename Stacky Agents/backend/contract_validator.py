"""
N1 — Execution Contract Validator

Valida el output de un agente contra un contrato declarativo por tipo de agente.
Retorna un ContractResult con score 0–100, failures (errors) y warnings.

Contratos definidos inline en YAML-like dicts para Fase 1.
Fase 5+ exportarlos a archivos contracts/<agent>.yaml con el Agent SDK.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ContractFailure:
    rule: str
    message: str
    severity: str  # "error" | "warning"


@dataclass
class ContractResult:
    agent_type: str
    passed: bool
    score: int  # 0–100
    failures: list[ContractFailure] = field(default_factory=list)
    warnings: list[ContractFailure] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "agent_type": self.agent_type,
            "passed": self.passed,
            "score": self.score,
            "failures": [
                {"rule": f.rule, "message": f.message, "severity": f.severity}
                for f in self.failures
            ],
            "warnings": [
                {"rule": f.rule, "message": f.message, "severity": f.severity}
                for f in self.warnings
            ],
        }


# ---------------------------------------------------------------------------
# Contratos por agente
# ---------------------------------------------------------------------------
_CONTRACTS: dict[str, dict] = {
    "business": {
        "required_sections": ["RF-"],
        "required_patterns": [],
        "forbidden_phrases": [
            "no tengo información",
            "requeriría más contexto",
            "no puedo determinar",
        ],
        "min_word_count": 80,
    },
    "functional": {
        "required_sections": ["plan de pruebas", "cobertura"],
        "required_patterns": [
            r"(CUBRE|GAP|NUEVA FUNC)",
        ],
        "forbidden_phrases": [
            "no tengo información",
            "requeriría más contexto",
            "no puedo determinar",
        ],
        "min_word_count": 200,
    },
    "technical": {
        "required_sections": [
            "traducción funcional",
            "alcance de cambios",
            "plan de pruebas",
            "tests unitarios",
            "notas para el desarrollador",
        ],
        "required_patterns": [
            r"TU-\d{3}",        # al menos un marcador TU
            r"ADO-\d{3,}",      # referencia al ticket
        ],
        "forbidden_phrases": [
            "no tengo información",
            "no puedo determinar",
            "requeriría más contexto",
        ],
        "min_word_count": 400,
    },
    "developer": {
        "required_sections": [
            "trazabilidad",
            "tests unitarios",
            "verificaciones de bd",
            "compilación",
        ],
        "required_patterns": [
            r"ADO-\d{3,}.*\d{4}-\d{2}-\d{2}",  # comentario con fecha
            r"(PASS|FAIL)",
        ],
        "forbidden_phrases": [
            "no tengo información",
            "no puedo implementar",
        ],
        "min_word_count": 300,
    },
    "qa": {
        "required_sections": ["verdict"],
        "required_patterns": [
            r"(PASS|FAIL)",
        ],
        "forbidden_phrases": [
            "no puedo determinar",
            "requeriría más información",
        ],
        "min_word_count": 80,
    },
}

_EVASION_PHRASES = [
    "no tengo información suficiente",
    "necesitaría más información",
    "no es posible determinarlo",
    "no cuento con los datos",
]


def validate(agent_type: str, output: str) -> ContractResult:
    """Valida el output contra el contrato del agente. Retorna ContractResult."""
    contract = _CONTRACTS.get(agent_type)
    if contract is None:
        return ContractResult(agent_type=agent_type, passed=True, score=100)

    output_lower = output.lower()
    words = output.split()
    failures: list[ContractFailure] = []
    warnings: list[ContractFailure] = []

    total_rules = 0
    passed_rules: float = 0

    # 1. Secciones requeridas
    for section in contract.get("required_sections", []):
        total_rules += 1
        if section.lower() in output_lower:
            passed_rules += 1
        else:
            failures.append(
                ContractFailure(
                    rule="required_section",
                    message=f"Sección requerida no encontrada: '{section}'",
                    severity="error",
                )
            )

    # 2. Patrones requeridos
    for pattern in contract.get("required_patterns", []):
        total_rules += 1
        if re.search(pattern, output, re.IGNORECASE):
            passed_rules += 1
        else:
            failures.append(
                ContractFailure(
                    rule="required_pattern",
                    message=f"Patrón requerido no encontrado: {pattern}",
                    severity="error",
                )
            )

    # 3. Frases prohibidas (evasión)
    for phrase in contract.get("forbidden_phrases", []):
        total_rules += 1
        if phrase.lower() not in output_lower:
            passed_rules += 1
        else:
            warnings.append(
                ContractFailure(
                    rule="forbidden_phrase",
                    message=f"Frase de evasión detectada: '{phrase}'",
                    severity="warning",
                )
            )
            passed_rules += 0.5  # penalidad parcial

    # Frases de evasión globales
    for phrase in _EVASION_PHRASES:
        if phrase.lower() in output_lower:
            warnings.append(
                ContractFailure(
                    rule="evasion_phrase",
                    message=f"Posible evasión: '{phrase}'",
                    severity="warning",
                )
            )

    # 4. Mínimo de palabras
    min_words = contract.get("min_word_count", 0)
    if min_words > 0:
        total_rules += 1
        word_count = len(words)
        if word_count >= min_words:
            passed_rules += 1
        else:
            shortage = min_words - word_count
            ratio = word_count / min_words
            if ratio < 0.5:
                failures.append(
                    ContractFailure(
                        rule="min_word_count",
                        message=f"Output muy corto: {word_count} palabras (mínimo {min_words}). Faltan ~{shortage}.",
                        severity="error",
                    )
                )
            else:
                warnings.append(
                    ContractFailure(
                        rule="min_word_count",
                        message=f"Output corto: {word_count} palabras (mínimo recomendado {min_words}). Faltan ~{shortage}.",
                        severity="warning",
                    )
                )
            passed_rules += ratio

    score = int((passed_rules / total_rules) * 100) if total_rules > 0 else 100
    score = max(0, min(100, score))
    passed = len(failures) == 0 and score >= 70

    return ContractResult(
        agent_type=agent_type,
        passed=passed,
        score=score,
        failures=failures,
        warnings=warnings,
    )
