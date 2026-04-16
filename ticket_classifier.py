"""
ticket_classifier.py — M-07: Scoring de complejidad de ticket (pre-triaje).

Analiza INC-{id}.md localmente (sin IA) y clasifica el ticket en:
  simple   → 1 componente, descripción corta, sin adjuntos complejos
  medio    → 2-3 componentes, bug reproducible, adjuntos simples
  complejo → múltiples sistemas, DB+OnLine+Batch, adjuntos complejos

Con el score se ajustan automáticamente:
  - timeout_pm_minutes: simple=20, medio=45, complejo=90
  - prompt de PM: instrucciones adaptadas
  - activación de deliberación multi-agente (G-08) para complejos

Uso:
    from ticket_classifier import classify_ticket, TicketScore
    score = classify_ticket(ticket_folder, ticket_id)
    timeout = score.recommended_pm_timeout
"""

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("mantis.classifier")

# ── Señales de complejidad ────────────────────────────────────────────────────

# Keywords que aumentan el score de complejidad
_COMPLEX_SIGNALS = {
    # Multi-sistema
    "batch":          3,
    "online":         1,
    "reporte":        2,
    "web service":    3,
    "integración":    3,
    "webservice":     3,
    "servicio ext":   3,
    # DB avanzado
    "rendimiento":    3,
    "performance":    3,
    "lentitud":       3,
    "timeout":        2,
    "deadlock":       4,
    "índice":         2,
    "partición":      3,
    "migración":      4,
    "stored proc":    2,
    # Impacto amplio
    "todos los":      3,
    "todos los regist": 3,
    "masivo":         3,
    "producción":     2,
    "bloqueante":     2,
    "crítico":        2,
    "cliente esc":    3,
    # Multi-módulo
    "frm":            1,   # cada form menciona +1
    "dal_":           1,
    "bll_":           1,
}

_SIMPLE_SIGNALS = {
    "label":          -2,
    "texto":          -1,
    "mensaje":        -1,
    "typo":           -3,
    "ortografía":     -3,
    "color":          -2,
    "título":         -2,
    "botón":          -1,
    "campo vacío":    -1,
    "validación simple": -2,
}

# Timeouts recomendados por complejidad (minutos)
_TIMEOUTS = {
    "simple":   {"pm": 20,  "dev": 45,  "tester": 25},
    "medio":    {"pm": 45,  "dev": 90,  "tester": 45},
    "complejo": {"pm": 90,  "dev": 150, "tester": 60},
}


@dataclass
class TicketScore:
    ticket_id:     str
    complexity:    str    # "simple" | "medio" | "complejo"
    score:         int
    signals:       list[str]
    word_count:    int
    attachment_count: int
    component_count:  int

    @property
    def recommended_pm_timeout(self) -> int:
        return _TIMEOUTS[self.complexity]["pm"]

    @property
    def recommended_dev_timeout(self) -> int:
        return _TIMEOUTS[self.complexity]["dev"]

    @property
    def recommended_tester_timeout(self) -> int:
        return _TIMEOUTS[self.complexity]["tester"]

    @property
    def should_use_multi_agent(self) -> bool:
        """True si se recomienda deliberación multi-agente (G-08)."""
        return self.complexity == "complejo"

    def summary(self) -> str:
        return (f"Ticket #{self.ticket_id}: {self.complexity.upper()} "
                f"(score={self.score}, palabras={self.word_count}, "
                f"adjuntos={self.attachment_count}, componentes={self.component_count})")


def classify_ticket(ticket_folder: str, ticket_id: str) -> TicketScore:
    """
    Clasifica el ticket y retorna un TicketScore.
    Lee INC-{ticket_id}.md para el análisis.
    """
    inc_path = os.path.join(ticket_folder, f"INC-{ticket_id}.md")
    content  = ""
    try:
        content = Path(inc_path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        pass

    content_lower = content.lower()
    signals       = []
    score         = 0

    # Contar palabras de la descripción
    word_count = len(content.split())

    # Score por longitud
    if word_count > 400:
        score += 4; signals.append(f"descripción larga ({word_count} palabras)")
    elif word_count > 200:
        score += 2
    elif word_count < 80:
        score -= 2; signals.append("descripción corta")

    # Signals de complejidad
    for kw, pts in _COMPLEX_SIGNALS.items():
        occurrences = content_lower.count(kw)
        if occurrences > 0:
            effective = min(occurrences, 3) * pts  # cap en 3 ocurrencias
            score    += effective
            signals.append(f"'{kw}' ×{occurrences}")

    # Signals de simplicidad
    for kw, pts in _SIMPLE_SIGNALS.items():
        if kw in content_lower:
            score    += pts
            signals.append(f"'{kw}' (simple)")

    # Contar componentes distintos mencionados
    component_patterns = [
        r'\bFrm[A-Z]\w+\b',          # formularios
        r'\bDAL_\w+\b',               # DAL classes
        r'\bBLL_\w+\b',               # BLL classes
        r'\bBatch\w+\b',              # batch processes
        r'\bWebService\w*\b',         # web services
        r'\bReport\w+\b',             # reportes
        r'\bRST\w{3,}\b',             # tablas RSTRP
    ]
    components = set()
    for pat in component_patterns:
        matches = re.findall(pat, content)
        components.update(matches)
    component_count = len(components)
    score += component_count * 2
    if component_count >= 4:
        signals.append(f"{component_count} componentes distintos")

    # Contar adjuntos
    attachment_count = len(re.findall(
        r'adjunto|attachment|screenshot|captura|\.png|\.jpg|\.xlsx|\.docx',
        content_lower
    ))
    score += attachment_count
    if attachment_count >= 3:
        signals.append(f"{attachment_count} adjuntos mencionados")

    # Severidad desde Mantis
    if re.search(r'bloqueante|bloquea producción', content_lower):
        score += 5; signals.append("severidad bloqueante")
    elif re.search(r'crítica?|critical', content_lower):
        score += 3; signals.append("severidad crítica")

    # Historial de notas largo
    note_count = len(re.findall(r'(?:nota|note|comentario)\s*#?\d+', content_lower))
    if note_count >= 5:
        score += 3; signals.append(f"{note_count} notas en historial")

    # Clasificar
    if score <= 4:
        complexity = "simple"
    elif score <= 12:
        complexity = "medio"
    else:
        complexity = "complejo"

    result = TicketScore(
        ticket_id=ticket_id,
        complexity=complexity,
        score=score,
        signals=signals[:10],
        word_count=word_count,
        attachment_count=attachment_count,
        component_count=component_count,
    )
    logger.info("[CLASSIFIER] %s", result.summary())
    return result
