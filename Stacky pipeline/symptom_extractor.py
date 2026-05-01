"""
symptom_extractor.py — Extrae síntomas reales del incidente para generar test cases QA.

Lee el contenido del INC + comentarios ADO y extrae:
- Trigger (qué acción causa el error)
- Observed behavior (qué pasa realmente)
- Expected behavior (qué debería pasar)
- Reproduction steps (pasos para reproducir)

Estos síntomas se inyectan en el prompt QA para generar test cases que
realmente reproducen el bug reportado.

Uso:
    from symptom_extractor import SymptomExtractor
    extractor = SymptomExtractor()
    symptoms = extractor.extract(inc_content, ado_comments)
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("stacky.symptom_extractor")


@dataclass
class Symptom:
    """A single extracted symptom from the incident description."""
    type: str  # "trigger", "observed_behavior", "expected_behavior", "reproduction_steps"
    text: str
    source: str = "inc"  # "inc" or "ado_comment"
    confidence: str = "medium"  # "high", "medium", "low"


SYMPTOM_PATTERNS = [
    (r"error\s+(?:al|cuando|en)\s+(.+?)[\.\n]", "trigger"),
    (r"falla\s+(?:al|cuando|en)\s+(.+?)[\.\n]", "trigger"),
    (r"no\s+(?:permite|deja|funciona|carga|guarda|muestra)\s+(.+?)[\.\n]", "trigger"),
    (r"(?:aparece|muestra|despliega|sale)\s+(?:un\s+)?(?:error|mensaje|alerta)\s+(.+?)[\.\n]", "observed_behavior"),
    (r"(?:se\s+muestra|se\s+ve|aparece)\s+(.+?)[\.\n]", "observed_behavior"),
    (r"debería\s+(.+?)[\.\n]", "expected_behavior"),
    (r"esperado[:\s]+(.+?)[\.\n]", "expected_behavior"),
    (r"resultado\s+esperado[:\s]+(.+?)[\.\n]", "expected_behavior"),
    (r"pasos\s+para\s+reproducir[:\s]*\n(.*?)(?:\n\n|\Z)", "reproduction_steps"),
    (r"pasos[:\s]*\n(.*?)(?:\n\n|\Z)", "reproduction_steps"),
    (r"(?:reproducción|reproducir)[:\s]*\n(.*?)(?:\n\n|\Z)", "reproduction_steps"),
]

# Patterns that indicate high confidence
HIGH_CONFIDENCE_MARKERS = [
    r"pasos\s+para\s+reproducir",
    r"resultado\s+esperado",
    r"resultado\s+actual",
    r"precondiciones",
]


class SymptomExtractor:
    """Extracts symptoms from incident reports and ADO comments."""

    def extract(
        self,
        inc_content: str,
        ado_comments: Optional[list[str]] = None,
    ) -> list[Symptom]:
        """
        Extract symptoms from incident content and ADO comments.

        Args:
            inc_content: Content of the INC-*.md file
            ado_comments: List of ADO comment texts (optional)

        Returns:
            List of Symptom objects sorted by type
        """
        symptoms = []

        # Extract from INC content
        symptoms.extend(self._extract_from_text(inc_content, source="inc"))

        # Extract from ADO comments
        if ado_comments:
            for comment in ado_comments:
                symptoms.extend(
                    self._extract_from_text(comment, source="ado_comment")
                )

        # Deduplicate similar symptoms
        symptoms = self._deduplicate(symptoms)

        # Sort by type priority
        type_order = {
            "reproduction_steps": 0,
            "trigger": 1,
            "observed_behavior": 2,
            "expected_behavior": 3,
        }
        symptoms.sort(key=lambda s: type_order.get(s.type, 99))

        logger.info("Extracted %d symptoms (%s)",
                     len(symptoms),
                     ", ".join(f"{s.type}:{s.confidence}" for s in symptoms[:5]))
        return symptoms

    def build_qa_injection_block(
        self,
        symptoms: list[Symptom],
        max_symptoms: int = 10,
    ) -> str:
        """
        Build a markdown block from extracted symptoms for injection into QA prompt.

        Returns empty string if no symptoms found.
        """
        if not symptoms:
            return ""

        lines = [
            "## Síntomas extraídos del incidente (para diseño de test cases)",
            "",
        ]

        type_labels = {
            "trigger": "🎯 Trigger (acción que causa el error)",
            "observed_behavior": "👁️ Comportamiento observado",
            "expected_behavior": "✅ Comportamiento esperado",
            "reproduction_steps": "📋 Pasos para reproducir",
        }

        current_type = None
        count = 0
        for symptom in symptoms[:max_symptoms]:
            if symptom.type != current_type:
                current_type = symptom.type
                label = type_labels.get(current_type, current_type)
                lines.append(f"### {label}")

            lines.append(f"- {symptom.text}")
            count += 1

        lines.append("")
        lines.append(
            "**INSTRUCCIÓN:** Diseñá casos de prueba que REPRODUZCAN estos síntomas "
            "exactos. No generes casos genéricos."
        )

        return "\n".join(lines)

    def _extract_from_text(self, text: str, source: str) -> list[Symptom]:
        """Extract symptoms from a single text block."""
        symptoms = []
        has_high_confidence = any(
            re.search(p, text, re.IGNORECASE) for p in HIGH_CONFIDENCE_MARKERS
        )

        for pattern, symptom_type in SYMPTOM_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE | re.DOTALL):
                extracted = match.group(1).strip()
                if len(extracted) < 5:
                    continue  # too short to be meaningful
                if len(extracted) > 500:
                    extracted = extracted[:500]  # cap long matches

                confidence = "high" if has_high_confidence else "medium"
                symptoms.append(Symptom(
                    type=symptom_type,
                    text=extracted,
                    source=source,
                    confidence=confidence,
                ))

        return symptoms

    def _deduplicate(self, symptoms: list[Symptom]) -> list[Symptom]:
        """Remove near-duplicate symptoms (same type + similar text)."""
        seen = set()
        unique = []
        for s in symptoms:
            key = (s.type, s.text[:50].lower())
            if key not in seen:
                seen.add(key)
                unique.append(s)
        return unique
