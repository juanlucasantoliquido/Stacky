"""Plan 284 — Clasificación determinista de documentos (plan vs proyecto).

Módulo PURO: sin I/O, sin DB, sin LLM. Clasifica por la forma del path.
"""
from __future__ import annotations

import re

# Clases posibles. Orden estable, usado por la UI para agrupar.
DOC_CLASS_PLAN = "plan"        # Stacky Agents/docs/NN_PLAN_*.md y hermanos numerados
DOC_CLASS_SYSTEM = "system"    # docs/sistema/*.md — documentación canónica del proyecto
DOC_CLASS_PROJECT = "project"  # el resto de la doc del proyecto documentado
DOC_CLASS_AGENT = "agent"      # *.agent.md
DOC_CLASS_OTHER = "other"

DOC_CLASSES: tuple[str, ...] = (
    DOC_CLASS_PLAN, DOC_CLASS_SYSTEM, DOC_CLASS_PROJECT, DOC_CLASS_AGENT, DOC_CLASS_OTHER,
)

# NN_ con 2 o 3 dígitos SEGUIDO DE UNA PALABRA CLAVE DE PLAN.
#
# OJO — el prefijo numérico solo NO alcanza y clasificar por `^\d{2,3}_` a secas
# es un BUG MEDIDO: en este mismo repo, `00_VISION.md`, `02_ARCHITECTURE.md` y
# `03_DATA_MODEL.md` son documentación DEL PROYECTO y caerían como "plan"
# (medido 2026-08-01: 257 falsos "plan" con la regla laxa vs 240 con esta).
# La secuencia NN_ es compartida entre planes, incidentes y checklists, pero
# también la usan documentos de producto. Por eso: prefijo + palabra clave.
_NUMBERED_DOC_RE = re.compile(
    r"^\d{2,3}_(plan|incidente|checklist|auditoria|postmortem)_", re.IGNORECASE
)


def classify_doc_path(rel_path: str) -> str:
    """Clase de un documento a partir de su path relativo POSIX. Nunca lanza.

    Reglas EXACTAS, evaluadas en este orden (la primera que matchea gana):
      1. basename termina en ".agent.md"                      -> "agent"
      2. el path contiene el segmento de carpeta "sistema"    -> "system"
      3. basename matchea _NUMBERED_DOC_RE (NN_ + palabra)    -> "plan"
      4. basename termina en ".md"                            -> "project"
      5. cualquier otra cosa                                  -> "other"
    """
    try:
        norm = (rel_path or "").replace("\\", "/").strip().lower()
        if not norm:
            return DOC_CLASS_OTHER
        basename = norm.rsplit("/", 1)[-1]
        if basename.endswith(".agent.md"):
            return DOC_CLASS_AGENT
        if "sistema" in norm.split("/")[:-1]:
            return DOC_CLASS_SYSTEM
        if _NUMBERED_DOC_RE.match(basename):
            return DOC_CLASS_PLAN
        if basename.endswith(".md"):
            return DOC_CLASS_PROJECT
        return DOC_CLASS_OTHER
    except Exception:
        return DOC_CLASS_OTHER


def is_plan_doc(rel_path: str) -> bool:
    """True si el documento es un plan/checklist/incidente numerado."""
    return classify_doc_path(rel_path) == DOC_CLASS_PLAN


def summarize_classes(rel_paths: list[str]) -> dict[str, int]:
    """{clase: cantidad} sobre una lista de paths. Incluye TODAS las claves de
    DOC_CLASSES con 0 si no aparecen (forma garantizada para la UI)."""
    out = {c: 0 for c in DOC_CLASSES}
    for p in rel_paths or []:
        out[classify_doc_path(p)] += 1
    return out
