"""
FA-35 — Confidence scoring del output.

Estimación heurística de la confianza del agente en su propio output.
Basada en señales del texto: hedge phrases, TODOs, presencia de "no sé",
densidad de números/citas, completitud frente al contrato.

Cuando se integre el LLM real, esto se reemplaza por self-reported confidence
que pide el system prompt al agente. Por ahora: análisis post-hoc del texto.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Frases que bajan confianza significativamente
_HEDGE_PHRASES = [
    "no estoy seguro",
    "creo que",
    "podría ser",
    "tal vez",
    "quizás",
    "probablemente",
    "me parece",
    "asumo que",
    "supongo que",
    "no puedo determinar",
    "requeriría más información",
    "no tengo acceso",
    "TBD",
    "TODO",
    "FIXME",
    "[PENDIENTE",
]

# Señales de baja calidad
_LOW_QUALITY_SIGNALS = [
    r"\b(lorem ipsum|placeholder|dummy)\b",
    r"\?\s*\?",  # múltiples interrogaciones seguidas
    r"\.{4,}",   # 4+ puntos suspensivos
]


@dataclass
class ConfidenceResult:
    overall: int            # 0-100
    sections: dict[str, int]  # title → score
    signals: list[str]      # señales detectadas

    def to_dict(self) -> dict:
        return {
            "overall": self.overall,
            "sections": self.sections,
            "signals": self.signals,
        }


def _split_sections(output: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_title = "preamble"
    current_lines: list[str] = []
    for line in output.split("\n"):
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            if current_lines:
                sections.append((current_title, "\n".join(current_lines)))
            current_title = m.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_title, "\n".join(current_lines)))
    return sections


def _score_section(text: str) -> tuple[int, list[str]]:
    if not text or len(text.strip()) < 30:
        return 40, ["section_too_short"]

    score = 100
    signals: list[str] = []
    text_lower = text.lower()

    # Hedge phrases (cada ocurrencia: -8)
    for phrase in _HEDGE_PHRASES:
        count = text_lower.count(phrase.lower())
        if count > 0:
            score -= 8 * count
            signals.append(f"hedge:{phrase}({count})")

    # Low quality signals (cada match: -15)
    for pattern in _LOW_QUALITY_SIGNALS:
        if re.search(pattern, text, re.IGNORECASE):
            score -= 15
            signals.append(f"low_quality:{pattern}")

    # Bonus por tablas, código, citaciones, TUs
    if "|" in text and "---" in text:
        score += 5  # tabla markdown
    if "```" in text:
        score += 3  # bloque de código
    if re.search(r"\.[a-z]{1,4}:\d+\b", text):
        score += 5  # citaciones file:line
    if re.search(r"\bTU[-\s]?\d{3,}\b", text):
        score += 3  # menciona TU específico
    if re.search(r"\bADO[-\s]?\d{3,}\b", text):
        score += 2

    return max(0, min(100, score)), signals


def score(output: str) -> ConfidenceResult:
    if not output or not output.strip():
        return ConfidenceResult(overall=0, sections={}, signals=["empty_output"])

    section_scores: dict[str, int] = {}
    all_signals: list[str] = []
    for title, body in _split_sections(output):
        s, sigs = _score_section(body)
        section_scores[title] = s
        for sig in sigs:
            all_signals.append(f"{title}: {sig}")

    if section_scores:
        avg = int(sum(section_scores.values()) / len(section_scores))
    else:
        avg = 50

    return ConfidenceResult(
        overall=avg,
        sections=section_scores,
        signals=all_signals[:20],  # cap
    )
