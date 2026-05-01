"""
subsystem_classifier.py — Y-03: Clasifica el subsistema (OnLine/Batch/BD/Integración)
de un ticket ANTES de lanzar PM, para inyectarlo como contexto inicial.

Usa señales en el texto del INC-{id}.md para determinar la capa destino.
Sin IA — clasificación local por keywords y patrones.
"""

import os
import re
from typing import NamedTuple


class SubsystemResult(NamedTuple):
    subsystem: str           # "OnLine", "Batch", "BD", "Integracion", "mix", "unknown"
    confidence: str          # "alta", "media", "baja"
    signals: list            # lista de señales detectadas
    workspace_hint: str      # ruta sugerida para empezar a buscar (relativa al trunk)


# ── Señales por subsistema ────────────────────────────────────────────────────

_SIGNALS_ONLINE = [
    r"\.aspx", r"\bFrm[A-Z]", r"\bbtn[A-Z]\w+_Click\b", r"\bGridView\b",
    r"\bAISGridView\b", r"\bAgendaWeb\b", r"\bpantalla\b", r"\bgrilla\b",
    r"\bformulario\b", r"\binterfaz\b", r"\bIIS\b", r"\bWebForms?\b",
    r"\bcode[- ]?behind\b", r"\baspx\.cs\b", r"\bOnLine\b",
]

_SIGNALS_BATCH = [
    r"\bservicio\b", r"\btarea programada\b", r"\bjob\b", r"\bproceso batch\b",
    r"\b\.exe\b", r"\bWindows Service\b", r"\BBatch\b", r"\bRSAg\b",
    r"\bmotor\b", r"\borquestador\b", r"\bprocesamiento\b", r"\bscheduler\b",
    r"\bdaemon\b", r"\bcorrida\b", r"\bRSProc\b", r"\bRSExtrae\b",
    r"\bcronos?\b", r"\btask\b",
]

_SIGNALS_BD = [
    r"\bSP_\w+", r"\bRST[A-Z]+_\w+", r"\bRPL[A-Z]+_\w+",
    r"\bINSERT\b", r"\bUPDATE\b", r"\bDELETE\b", r"\bALTER\b", r"\bCREATE\b",
    r"\bmigration\b", r"\btabla\b", r"\bcolumna\b", r"\bisquema\b", r"\bschema\b",
    r"\bOracle\b", r"\bsequencia\b", r"\bíndice\b", r"\bconstraints?\b",
    r"\bRIDIOMA\b", r"\bRCONTROLES\b", r"\bRL_\w+", r"\bDAL\b",
]

_SIGNALS_INTEGRACION = [
    r"\bGenesys\b", r"\bSFTP\b", r"\bwebservice\b", r"\bAPI\b",
    r"\bintegración\b", r"\bmiddleware\b", r"\bendpoint\b", r"\bsoap\b",
    r"\brest\b", r"\bwsdl\b", r"\bws_\b", r"\bX[mM][lL]\b",
    r"\bFTP\b", r"\bInterfaz[^G]", r"\binterfaz externa\b",
]

_WORKSPACE_HINTS = {
    "OnLine":      "OnLine/AgendaWeb/",
    "Batch":       "Batch/",
    "BD":          "BD/",
    "Integracion": "OnLine/RSXxx/ o Batch/RSXxx/",
    "mix":         "Múltiples subsistemas — revisar señales",
    "unknown":     "Desconocido — analizar manualmente",
}


def _count_signals(text: str, patterns: list) -> list:
    """Retorna lista de señales encontradas en el texto."""
    found = []
    text_lower = text
    for pat in patterns:
        matches = re.findall(pat, text_lower, re.IGNORECASE)
        if matches:
            found.extend(matches[:2])  # máximo 2 ocurrencias por patrón
    return list(dict.fromkeys(found))  # deduplicar preservando orden


def classify_ticket(ticket_folder: str, ticket_id: str) -> SubsystemResult:
    """
    Analiza el INC-{id}.md del ticket y clasifica el subsistema.
    Retorna SubsystemResult con subsystem, confidence, signals y workspace_hint.
    """
    inc_file = os.path.join(ticket_folder, f"INC-{ticket_id}.md")
    if not os.path.exists(inc_file):
        # Intentar INC_{ticket_id}.md como alternativa
        inc_file_alt = os.path.join(ticket_folder, f"INC_{ticket_id}.md")
        if os.path.exists(inc_file_alt):
            inc_file = inc_file_alt
        else:
            return SubsystemResult("unknown", "baja", [], _WORKSPACE_HINTS["unknown"])

    try:
        text = open(inc_file, encoding="utf-8").read()
    except Exception:
        return SubsystemResult("unknown", "baja", [], _WORKSPACE_HINTS["unknown"])

    online_signals      = _count_signals(text, _SIGNALS_ONLINE)
    batch_signals       = _count_signals(text, _SIGNALS_BATCH)
    bd_signals          = _count_signals(text, _SIGNALS_BD)
    integracion_signals = _count_signals(text, _SIGNALS_INTEGRACION)

    scores = {
        "OnLine":      len(online_signals),
        "Batch":       len(batch_signals),
        "BD":          len(bd_signals),
        "Integracion": len(integracion_signals),
    }

    total = sum(scores.values())
    if total == 0:
        return SubsystemResult("unknown", "baja", [], _WORKSPACE_HINTS["unknown"])

    # Determinar ganador
    winner = max(scores, key=scores.get)
    winner_score = scores[winner]

    # Señales del ganador
    signals_map = {
        "OnLine":      online_signals,
        "Batch":       batch_signals,
        "BD":          bd_signals,
        "Integracion": integracion_signals,
    }
    winner_signals = signals_map[winner]

    # Detectar "mix": si hay 2+ subsistemas con score >= 2
    strong = [s for s, sc in scores.items() if sc >= 2]
    if len(strong) >= 2:
        all_signals = online_signals + batch_signals + bd_signals + integracion_signals
        return SubsystemResult("mix", "media", all_signals[:8], _WORKSPACE_HINTS["mix"])

    # Confianza basada en porcentaje del total
    ratio = winner_score / total if total > 0 else 0
    if ratio >= 0.7 and winner_score >= 2:
        confidence = "alta"
    elif ratio >= 0.5 or winner_score >= 2:
        confidence = "media"
    else:
        confidence = "baja"

    return SubsystemResult(
        winner,
        confidence,
        winner_signals[:6],
        _WORKSPACE_HINTS[winner],
    )


def format_for_prompt(result: SubsystemResult) -> str:
    """
    Formatea el resultado para inyectar al inicio del prompt PM.
    Retorna string listo para concatenar.
    """
    if result.subsystem == "unknown":
        return ""

    signals_str = ", ".join(result.signals[:5]) if result.signals else "—"
    return (
        f"SUBSISTEMA DETECTADO: **{result.subsystem}** "
        f"(confianza: {result.confidence} — señales: {signals_str})\n"
        f"Workspace hint: `{result.workspace_hint}`\n"
    )
