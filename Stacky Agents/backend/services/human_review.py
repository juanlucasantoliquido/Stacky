"""F0 (plan 47) — Contrato del veredicto humano de una run.

PURO: no toca DB ni Flask. Solo constantes y construcción/validación del
bloque `human_review` que se guarda en AgentExecution.metadata_json.
"""
from __future__ import annotations

from datetime import datetime

# Veredictos humanos canónicos. "approved"/"rejected" son terminales;
# "approved_with_notes" = aprobada pero el operador dejó una observación.
# El endpoint legacy /approve usa "approved" y /discard usa "discarded";
# este módulo NORMALIZA al recibir ("discarded" → "rejected" en el bloque).
HUMAN_VERDICTS = ("approved", "rejected", "approved_with_notes")
LEGACY_VERDICTS_MAP = {"discarded": "rejected"}  # C1: normalización entrada → bloque

MAX_NOTE_CHARS = 2000  # C6: ~500 palabras; suficiente para criterio operativo sin saturar contexto

METADATA_KEY = "human_review"


def build_human_review(*, verdict: str, note: str | None, reviewed_by: str | None) -> dict:
    """Arma el bloque a persistir en metadata_json[METADATA_KEY]. Valida verdict y nota.

    Normaliza veredictos legacy ("discarded" → "rejected").
    """
    normalized_verdict = LEGACY_VERDICTS_MAP.get(verdict, verdict)
    if normalized_verdict not in HUMAN_VERDICTS:
        raise ValueError(
            f"verdict must be one of {HUMAN_VERDICTS} or {list(LEGACY_VERDICTS_MAP.keys())}"
        )
    note_clean = (note or "").strip()
    if len(note_clean) > MAX_NOTE_CHARS:
        raise ValueError(f"note exceeds {MAX_NOTE_CHARS} chars")
    if normalized_verdict == "approved_with_notes" and not note_clean:
        raise ValueError("approved_with_notes requires a non-empty note")
    return {
        "verdict": normalized_verdict,
        "note": note_clean or None,
        "reviewed_by": reviewed_by or None,
        "reviewed_at": datetime.utcnow().isoformat(),
    }
