"""
FA-09 — RIDIOMA / project glossary auto-injection.

Detecta términos de dominio (RIDIOMA, RTABL, RPARAM, módulos internos,
acrónimos) en el contexto del operador y produce un bloque [auto] glossary
que se inyecta antes de mandar al agente.

Fase 1: keyword + regex sobre un diccionario inline.
Fase 4 (FA-15): glossary auto-build aprende términos de outputs aprobados.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

# ---------------------------------------------------------------------------
# Diccionario base — términos del proyecto Pacífico que el agente debería saber
# ---------------------------------------------------------------------------

GLOSSARY: dict[str, str] = {
    "RIDIOMA": (
        "Tabla maestra de literales / mensajes traducibles del sistema. "
        "Las nuevas entradas SIEMPRE se agregan al final del archivo "
        "`trunk/BD/1 - Inicializacion BD/600804 - Inserts RIDIOMA.sql` "
        "— nunca se crean archivos .sql nuevos."
    ),
    "RTABL": (
        "Tabla maestra de tablas paramétricas. Convención: una RTABL por tipo "
        "de catálogo (estados, tipos de cobranza, monedas, etc.)."
    ),
    "RPARAM": (
        "Tabla maestra de parámetros del sistema. Cada parámetro tiene clave + "
        "valor + scope (global / empresa / sucursal)."
    ),
    "ADO": "Azure DevOps — donde viven los tickets de Pacífico (Org: UbimiaPacifico).",
    "Epic": "Tipo de work item ADO con bloques RF-XXX en su descripción HTML.",
    "RF": (
        "Requerimiento Funcional. Identificado como `RF-XXX` dentro de la "
        "descripción de un Epic. Cada RF se convierte en una Task."
    ),
    "TU": (
        "Test Unitario. Identificado como `TU-XXX`. Definido por el Analista "
        "Técnico, ejecutado por el Developer hasta 100% de cobertura."
    ),
    "OnLine": "Capa transaccional del sistema (`trunk/OnLine/`). Procesa pedidos en tiempo real.",
    "Batch": "Capa de procesos masivos (`trunk/Batch/`). Corre en ventanas programadas.",
    "Pacifico.Common": (
        "Librería compartida en `trunk/lib/Pacifico.Common/` con utilidades "
        "transversales (logging, retry policies, formatters)."
    ),
    "Cobranza": "Módulo de gestión de cobros y deudas — el de mayor volumen del producto.",
    "Agenda": "Módulo de planificación de visitas / contactos con el deudor.",
    "PAT": "Personal Access Token — credencial de acceso a la API de ADO.",
    "Strategist_Pacifico": "Nombre del proyecto en ADO.",
}

# Aliases / variantes (todo lower, mapean al término canónico de GLOSSARY).
ALIASES: dict[str, str] = {
    "ridioma": "RIDIOMA",
    "rtabl": "RTABL",
    "rparam": "RPARAM",
    "ado": "ADO",
    "azure devops": "ADO",
    "epic": "Epic",
    "epico": "Epic",
    "épico": "Epic",
    "rf": "RF",
    "tu": "TU",
    "online": "OnLine",
    "on line": "OnLine",
    "on-line": "OnLine",
    "batch": "Batch",
    "pacifico.common": "Pacifico.Common",
    "pacifico common": "Pacifico.Common",
    "cobranza": "Cobranza",
    "cobranzas": "Cobranza",
    "agenda": "Agenda",
    "pat": "PAT",
    "strategist_pacifico": "Strategist_Pacifico",
    "strategist": "Strategist_Pacifico",
}

# Patrón general para detectar `RF-XXX`, `TU-XXX`, `ADO-XXXX` en texto.
_REF_PATTERN = re.compile(r"\b(RF|TU|ADO)[-\s]?\d{2,}\b", re.IGNORECASE)


@dataclass
class DetectedTerm:
    term: str  # canónico
    definition: str
    occurrences: int

    def to_dict(self) -> dict:
        return {
            "term": self.term,
            "definition": self.definition,
            "occurrences": self.occurrences,
        }


def detect_terms(texts: Iterable[str]) -> list[DetectedTerm]:
    """
    Recibe textos heterogéneos (título, descripción, bloques) y devuelve
    los términos del glossary que aparecen, ordenados por relevancia.
    """
    text = "\n".join(t for t in texts if t).lower()
    if not text:
        return []

    counts: dict[str, int] = {}

    # Busqueda por alias
    for alias, canonical in ALIASES.items():
        if not alias:
            continue
        # Aliases con espacios: usar substring; sin espacios: usar word-boundary.
        if " " in alias:
            count = text.count(alias)
        else:
            pattern = rf"\b{re.escape(alias)}\b"
            count = len(re.findall(pattern, text))
        if count > 0:
            counts[canonical] = counts.get(canonical, 0) + count

    # Refs explícitas (RF-XXX, TU-XXX, ADO-XXXX) cuentan como menciones de RF/TU/ADO.
    for match in _REF_PATTERN.finditer(text):
        kind = match.group(1).upper()
        if kind in GLOSSARY:
            counts[kind] = counts.get(kind, 0) + 1

    detected = [
        DetectedTerm(term=term, definition=GLOSSARY[term], occurrences=counts[term])
        for term in counts
        if term in GLOSSARY
    ]
    detected.sort(key=lambda d: d.occurrences, reverse=True)
    return detected


def build_glossary_block(texts: Iterable[str], max_terms: int = 10) -> dict | None:
    """
    Devuelve un ContextBlock listo para inyectar en `input_context`,
    o None si no se detectaron términos.

    Compatible con el shape esperado por el frontend (kind=auto).
    """
    detected = detect_terms(texts)[:max_terms]
    if not detected:
        return None

    body_lines = [
        f"- **{d.term}**: {d.definition}" for d in detected
    ]
    content = "\n".join(body_lines)

    return {
        "id": "glossary-auto",
        "kind": "auto",
        "title": f"Glosario detectado ({len(detected)} término{'s' if len(detected) != 1 else ''})",
        "content": content,
        "source": {
            "type": "glossary",
            "terms": [d.term for d in detected],
        },
    }
