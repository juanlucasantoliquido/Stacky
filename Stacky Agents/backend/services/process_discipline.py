"""Disciplina de procesos: reutilizar por default, crear solo con instrucción explícita.

Funciones puras: sin estado global, sin red, sin LLM. Compatible con Python 3.10+ stdlib.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


# Palabras clave que indican INTENCIÓN EXPLÍCITA de crear algo nuevo
_CREATE_KEYWORDS = [
    "crear nuevo proceso",
    "crear nuevo batch",
    "nuevo proceso",
    "nuevo batch",
    "crear proceso",
    "proceso nuevo",
    "batch nuevo",
    "nueva interfaz",
    "nuevo modulo",
    "nuevo subproceso",
    "crear subproceso",
]

# Prefijos que NUNCA indican creación (son modificaciones o consultas)
_NO_CREATE_PREFIXES = [
    "modificar",
    "actualizar",
    "corregir",
    "fix",
    "agregar campo",
    "incorporar",
    "incorporación",
    "mejorar",
    "optimizar",
    "revisar",
    "analizar",
    "informe",
    "reporte",
]

# Stopwords para limpiar vocabulario antes de Jaccard (C5 — reduce ruido)
_STOPWORDS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "y",
    "o", "en", "para", "por", "con", "que", "se", "a", "al", "lo", "le",
    "es", "son", "como", "the", "a", "an", "of", "to", "in", "for", "and",
    "or", "que", "este", "esta", "esto", "su", "sus", "this", "is",
}


@dataclass(frozen=True)
class DisciplineDecision:
    """Resultado de analizar un ticket contra el catálogo de procesos.

    - action: "REUSE" o "CREATE"
    - process_name: nombre del proceso a reutilizar (si action=REUSE) o sugerido para crear (si action=CREATE)
    - reason: explicación breve para inyectar en el prompt
    - confidence: 0..1, cuán seguro estamos (para telemetría)
    - instruction_present: True si el ticket contiene instrucción explícita de crear
    """
    action: Literal["REUSE", "CREATE"]
    process_name: str | None
    reason: str
    confidence: float
    instruction_present: bool


def _tokenize(text: str) -> set[str]:
    """Tokeniza + lower + filtra stopwords (C5)."""
    words = re.findall(r"\b\w+\b", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}


def _contains_create_instruction(text: str) -> bool:
    """Detecta si el texto contiene una instrucción EXPLÍCITA de crear algo nuevo.

    Niega ante 'no', 'nunca', 'sin', 'evitar', 'prohibido', 'no vuelvas' (C5).
    """
    text_lower = text.lower()
    # Patrones de negación que invalidan la keyword de creación (C5 — expansión)
    # Ventana de 40 chars antes del keyword para capturar negaciones separadas
    # por palabras intermedias (ej. "nunca crees un nuevo proceso"). (C5 v2)
    _NEGATIONS = (
        r"no\b.{{0,40}}{kw}", r"nunca\b.{{0,40}}{kw}", r"sin\b.{{0,40}}{kw}",
        r"evitar\b.{{0,40}}{kw}", r"prohibido\b.{{0,40}}{kw}",
        r"no\s+vuelvas\s+a\s+.{{0,30}}{kw}",
    )
    for keyword in _CREATE_KEYWORDS:
        if keyword not in text_lower:
            continue
        negated = any(
            re.search(pat.format(kw=re.escape(keyword)), text_lower)
            for pat in _NEGATIONS
        )
        if not negated:
            return True
    return False


def _contains_no_create_prefix(text: str) -> bool:
    """Detecta si el texto empieza con prefijos que claramente NO son creación."""
    text_lower = text.lower().strip()
    for prefix in _NO_CREATE_PREFIXES:
        if text_lower.startswith(prefix):
            return True
    return False


def _find_best_match(
    query: str, process_catalog: list[dict],
    title: str = "",  # C5 v2 — boost cuando el kind del proceso aparece en el título
) -> tuple[str | None, float]:
    """Encuentra el proceso del catálogo más similar al query (Jaccard sobre tokens limpios).

    Returns:
        (process_name, similarity_score) donde similarity_score está en 0..1
    """
    if not process_catalog:
        return None, 0.0

    query_lower = query.lower()
    query_words = _tokenize(query_lower)
    if not query_words:
        return None, 0.0

    title_tokens = _tokenize(title.lower()) if title else set()
    best_name = None
    best_score = 0.0

    for proc in process_catalog:
        name = proc.get("name", "")
        purpose = proc.get("purpose", "")
        kind = proc.get("kind", "")

        proc_text = f"{name} {purpose} {kind}".lower()
        proc_words = _tokenize(proc_text)
        if not proc_words:
            continue

        intersection = query_words & proc_words
        union = query_words | proc_words
        score = len(intersection) / len(union) if union else 0.0

        # Boost si el nombre aparece literalmente en el query
        if name.lower() in query_lower:
            score = max(score, 0.8)

        # Boost si el kind del proceso aparece como token del título del ticket (C5 v2).
        # Ejemplo: kind="carga" + title="Carga de clientes" → score 0.5 (relevancia media-alta).
        if kind and kind.lower() in title_tokens:
            score = max(score, 0.5)

        if score > best_score:
            best_score = score
            best_name = name

    return best_name, best_score


def decide_process_action(
    title: str,
    description: str,
    process_catalog: list[dict] | None,
) -> DisciplineDecision:
    """Decide si REUTILIZAR un proceso existente o CREAR uno nuevo.

    Reglas:
    1. Si el ticket contiene instrucción EXPLÍCITA de crear ("crear nuevo proceso", etc.)
       Y NO empieza con prefijos de no-creación → CREATE.
    2. Si NO hay instrucción explícita Y hay un proceso con similitud >= 0.4 → REUSE ese proceso.
    3. Si NO hay instrucción explícita Y NO hay coincidencia → CREATE (porque no sabemos qué usar).
    4. Sin catálogo → CREATE con confianza 0 (fallback).
    """
    combined = f"{title} {description}"
    instruction_present = _contains_create_instruction(combined)
    no_create_prefix = _contains_no_create_prefix(combined)

    # Si empieza con "modificar", "fix", etc., no es creación aunque diga "proceso"
    if no_create_prefix:
        instruction_present = False

    # Caso 1: instrucción explícita de crear
    if instruction_present:
        return DisciplineDecision(
            action="CREATE",
            process_name=None,
            reason="El ticket contiene una instrucción explícita de crear un nuevo proceso o batch.",
            confidence=0.95,
            instruction_present=True,
        )

    # Caso 2: buscar mejor coincidencia en catálogo
    best_match, similarity = _find_best_match(combined, process_catalog or [], title=title)

    SIMILARITY_THRESHOLD = 0.4

    if best_match and similarity >= SIMILARITY_THRESHOLD:
        return DisciplineDecision(
            action="REUSE",
            process_name=best_match,
            reason=f"El catálogo ya contiene el proceso '{best_match}' que cubre la necesidad (similitud {similarity:.2f}).",
            confidence=similarity,
            instruction_present=False,
        )

    # Caso 3: no hay coincidencia clara y no hay instrucción explícita
    if process_catalog:
        return DisciplineDecision(
            action="CREATE",
            process_name=None,
            reason=f"No se encontró un proceso en el catálogo que coincida suficientemente (mejor similitud {similarity:.2f}). Solo crea un nuevo proceso si estás seguro de que no existe uno equivalente.",
            confidence=0.3,
            instruction_present=False,
        )

    # Caso 4: no hay catálogo (fallback)
    return DisciplineDecision(
        action="CREATE",
        process_name=None,
        reason="No hay catálogo de procesos configurado para este proyecto. Procede con tu criterio.",
        confidence=0.0,
        instruction_present=False,
    )


def build_discipline_block(decision: DisciplineDecision) -> str:
    """Construye el bloque de texto para inyectar en el prompt del agente."""
    if decision.action == "REUSE":
        return f"""## Disciplina de Procesos — Stacky

**ACCIÓN RECOMENDADA: REUTILIZAR proceso existente**

- Proceso a reutilizar: **{decision.process_name}**
- Razón: {decision.reason}
- Confianza: {decision.confidence:.0%}

**Instrucción para el agente:** Debes usar el proceso **{decision.process_name}** existente en la arquitectura. NO inventes un nuevo proceso. Si el ticket requiere modificaciones, explica cómo se ajustan en el proceso existente.

"""
    else:  # CREATE
        instruction = "**SÍ** crear un nuevo proceso" if decision.instruction_present else "Evaluar si es necesario crear"
        return f"""## Disciplina de Procesos — Stacky

**ACCIÓN RECOMENDADA: {instruction}**

- Razón: {decision.reason}
- Confianza: {decision.confidence:.0%}

**Instrucción para el agente:** Solo crea un nuevo proceso si (1) el ticket lo pide explícitamente O (2) estás seguro de que no existe un proceso equivalente en el catálogo. Si existe algo cercano, REUTILIZA antes de inventar.

"""
