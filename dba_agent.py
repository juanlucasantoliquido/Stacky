"""
dba_agent.py — Y-04: Stage condicional DBA Especialista.

Cuando el análisis PM detecta que un ticket requiere cambios Oracle significativos,
se inserta un agente DBA entre PM y DEV que genera DB_SOLUTION.sql validado.

DEV recibe DB_SOLUTION.sql listo y solo conecta el C# — sin pensar en Oracle.
"""

import logging
import os
import re

logger = logging.getLogger("stacky.dba_agent")

# Señales que indican un ticket con alta carga Oracle
_DB_KEYWORDS = [
    r"\bSP_\w+", r"\bRST[A-Z]+_\w*", r"\bRPL[A-Z]+_\w*",
    r"\bRIDIOMA\b", r"\bRCONTROLES\b", r"\bALL_TAB_COLUMNS\b",
    r"\bINSERT\s+INTO\b", r"\bALTER\s+TABLE\b", r"\bCREATE\s+(TABLE|INDEX|SEQUENCE)\b",
    r"\bnueva\s+columna\b", r"\bnuevo\s+campo\b", r"\bnueva\s+tabla\b",
    r"\bsecuencia\b", r"\bíndice\b", r"\bconstraint\b",
    r"\bmigración\b", r"\bmigration\b", r"\bddl\b", r"\bdml\b",
]

_DB_SCORE_THRESHOLD = 3  # número de señales para considerar Oracle-heavy


def score_db_load(ticket_folder: str, ticket_id: str) -> int:
    """
    Analiza el INC-{id}.md y el ANALISIS_TECNICO.md para detectar carga Oracle.
    Retorna un score (0+): mayor score = más carga Oracle.
    """
    score = 0
    files_to_check = [
        os.path.join(ticket_folder, f"INC-{ticket_id}.md"),
        os.path.join(ticket_folder, "ANALISIS_TECNICO.md"),
        os.path.join(ticket_folder, "ARQUITECTURA_SOLUCION.md"),
    ]
    combined_text = ""
    for fpath in files_to_check:
        if os.path.exists(fpath):
            try:
                combined_text += open(fpath, encoding="utf-8").read()
            except Exception:
                pass

    for pattern in _DB_KEYWORDS:
        if re.search(pattern, combined_text, re.IGNORECASE):
            score += 1

    return score


def is_dba_required(ticket_folder: str, ticket_id: str,
                    threshold: int = None) -> bool:
    """
    Retorna True si el ticket requiere el stage DBA.
    threshold: override del umbral (default: _DB_SCORE_THRESHOLD).
    """
    th = threshold if threshold is not None else _DB_SCORE_THRESHOLD
    score = score_db_load(ticket_folder, ticket_id)
    logger.debug("[DBA] Ticket %s — DB score: %d (threshold: %d)", ticket_id, score, th)
    return score >= th


def get_dba_agent_name(agents: dict) -> str:
    """Retorna el nombre del agente DBA configurado, o el agente DEV como fallback."""
    return agents.get("dba", agents.get("dev", "DevStack3"))
