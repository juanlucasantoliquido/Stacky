"""I0.2 — Cómputo consistente de fingerprint_complexity para los 3 runtimes.

Helper puro y determinístico (sin LLM) que clasifica el encargo en:
  "S" | "M" | "L" | "XL"

Heurística basada en:
  - longitud total del título + descripción (chars)
  - número de bullets/criterios en la descripción (líneas con guión o asterisco)
  - número de bloques de contexto
  - tamaño total estimado de bloques (tokens ~ chars // 4)
  - presencia de palabras-señal de complejidad alta

No tiene efectos secundarios; no lee config; es determinística.
"""
from __future__ import annotations

import re

# Palabras-señal que indican complejidad elevada (match case-insensitive)
_SIGNAL_WORDS = frozenset([
    "migración", "migration",
    "refactor", "refactoring", "refactorización",
    "integración", "integration",
    "reestructuración", "reestructurar",
    "arquitectura", "architecture",
    "redesign", "rediseño",
    "multietapa", "multi-etapa",
    "sincronización", "synchronization",
    "autenticación", "authentication",
    "autorización", "authorization",
    "performance", "optimización",
    "concurrencia", "concurrency",
    "seguridad", "security",
    "escalabilidad", "scalability",
])

# Número de tokens estimados por bloque de contexto (por sus chars de content)
def _block_token_estimate(blocks: list[dict]) -> int:
    """Estimación rápida de tokens totales de los bloques (chars // 4)."""
    total = 600  # framing overhead
    for b in blocks:
        total += len((b.get("content") or "")) // 4
        for it in (b.get("items") or []):
            if it.get("selected"):
                total += len(it.get("label", "")) // 4
    return total


def estimate_complexity(
    *,
    agent_type: str,
    ticket_title: str,
    ticket_description: str,
    blocks: list[dict],
) -> str:
    """Devuelve "S" | "M" | "L" | "XL" — heurística determinística sin LLM.

    Criterios acumulativos (cada uno puede subir la clasificación, nunca bajar):
      - longitud de texto (título + descripción)
      - número de bullets/criterios (líneas con guión/asterisco/número)
      - número de bloques de contexto
      - tokens estimados totales de bloques
      - presencia de palabras-señal
    """
    title = ticket_title or ""
    desc = ticket_description or ""
    full_text = (title + " " + desc).lower()

    total_chars = len(title) + len(desc)

    # Contar bullets: líneas que empiezan con -, *, o número seguido de punto
    bullet_pattern = re.compile(r"^\s*(?:[-*]|\d+\.)\s+", re.MULTILINE)
    n_bullets = len(bullet_pattern.findall(desc))

    n_blocks = len(blocks)
    estimated_tokens = _block_token_estimate(blocks)

    # Detectar palabras-señal
    has_signal = any(word in full_text for word in _SIGNAL_WORDS)

    # --- Sistema de puntos ---
    # Cada dimensión aporta puntos; sumamos y clasificamos.
    # Umbrales calibrados para que:
    #   S  = score 0-1  (trabajo puntual, breve)
    #   M  = score 2-3  (trabajo acotado, descripción media)
    #   L  = score 4-7  (trabajo con múltiples criterios / bloques grandes)
    #   XL = score >= 8 (rediseño / migración / muchos contextos grandes)
    score = 0

    # Longitud de texto (título + descripción)
    if total_chars > 600:
        score += 3
    elif total_chars > 200:
        score += 2
    elif total_chars > 80:
        score += 1

    # Bullets / criterios de aceptación
    if n_bullets >= 8:
        score += 3
    elif n_bullets >= 4:
        score += 2
    elif n_bullets >= 2:
        score += 1

    # Bloques de contexto (más bloques = más scope)
    if n_blocks >= 8:
        score += 4
    elif n_blocks >= 4:
        score += 3
    elif n_blocks >= 2:
        score += 1

    # Tokens estimados totales de bloques
    if estimated_tokens >= 15_000:
        score += 4
    elif estimated_tokens >= 4_000:
        score += 3
    elif estimated_tokens >= 1_200:
        score += 1

    # Palabras-señal de complejidad alta
    if has_signal:
        score += 2

    # Clasificación
    if score >= 8:
        return "XL"
    if score >= 4:
        return "L"
    if score >= 2:
        return "M"
    return "S"
