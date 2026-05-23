"""Servicio que busca tickets ADO con título similar al actual.

Usado para inyectar el context block `ado-similar-tickets` cuando los
agentes TechnicalAnalyst o AnalistaFuncional analizan un ticket. El bloque
contiene tickets con título "parecido" para que el agente no proponga
crear duplicados en su análisis.

Implementación:
  - Extrae keywords del título del ticket actual (filtra stopwords y
    fragmentos < 4 chars).
  - Construye WIQL con CONTAINS de la keyword más distintiva (o un OR de
    varias) excluyendo el ticket actual.
  - Limita resultados a 10 más recientes.

Defensivo:
  - Si AdoClient no está configurado o falla → retorna [].
  - Si el título es muy genérico (sin keywords útiles) → retorna [].
  - No propaga excepciones al caller (agent_runner).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable

logger = logging.getLogger("stacky.similar_tickets")

SIMILAR_BLOCK_ID = "ado-similar-tickets"
MAX_RESULTS = 10
MIN_KEYWORD_LENGTH = 4

# Stopwords ES + EN comunes en títulos de tickets técnicos. No son exhaustivas
# (sólo las que típicamente generan ruido en búsquedas WIQL CONTAINS).
_STOPWORDS = frozenset({
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    "de", "del", "al", "a", "ante", "con", "contra", "desde", "en", "entre",
    "hacia", "hasta", "para", "por", "segun", "según", "sin", "sobre", "tras",
    "y", "o", "u", "ni", "que", "porque", "como", "donde", "cuando",
    "es", "son", "ser", "estar", "esta", "este", "esto", "estos", "estas",
    "the", "and", "or", "with", "from", "for", "of", "in", "on", "to", "by",
    "ado", "task", "bug", "rf", "ep", "ca",  # convencionales que no aportan
})


@dataclass
class SimilarTicket:
    ado_id: int
    title: str
    state: str
    work_item_type: str
    url: str

    def to_dict(self) -> dict:
        return {
            "ado_id": self.ado_id,
            "title": self.title,
            "state": self.state,
            "work_item_type": self.work_item_type,
            "url": self.url,
        }


def extract_keywords(title: str) -> list[str]:
    """Tokeniza el título y filtra stopwords + fragmentos cortos.

    Retorna una lista ordenada por longitud descendente — las palabras más
    largas suelen ser las más distintivas (nombres de tablas, pantallas, etc.).
    """
    if not title:
        return []
    # Separar por espacios y signos de puntuación comunes
    tokens = re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ_][\w_]*", title)
    keywords: list[str] = []
    seen: set[str] = set()
    for tok in tokens:
        low = tok.lower()
        if len(low) < MIN_KEYWORD_LENGTH:
            continue
        if low in _STOPWORDS:
            continue
        if low in seen:
            continue
        seen.add(low)
        keywords.append(tok)
    # Las palabras más largas primero (suelen ser nombres técnicos)
    keywords.sort(key=lambda t: (-len(t), t.lower()))
    return keywords


def find_similar_tickets(
    *,
    current_ado_id: int | None,
    current_title: str,
    project: str,
    project_name: str | None = None,
    top_keywords: int = 3,
    max_results: int = MAX_RESULTS,
) -> list[SimilarTicket]:
    """Busca tickets ADO con título similar al del ticket actual.

    Args:
        current_ado_id: ado_id del ticket actual — se excluye de resultados.
        current_title: título del ticket actual — usado para extraer keywords.
        project: nombre del proyecto ADO (`Strategist_Pacifico` por default).
        top_keywords: cuántas keywords distintivas usar en WIQL OR.
        max_results: límite de tickets retornados.

    Returns:
        Lista de SimilarTicket (vacía si no hay match, error, o keywords
        insuficientes). Nunca propaga excepciones.
    """
    keywords = extract_keywords(current_title)
    if not keywords:
        logger.debug("similar_tickets: title %r sin keywords útiles", current_title)
        return []

    selected = keywords[:top_keywords]
    wiql = _build_wiql(
        project=project,
        keywords=selected,
        exclude_id=current_ado_id,
        max_results=max_results,
    )

    try:
        from services.project_context import build_ado_client

        client = build_ado_client(project_name=project_name, tracker_project=project)
    except Exception as exc:
        logger.warning("similar_tickets: AdoClient no disponible: %s", exc)
        return []

    try:
        rows = client.fetch_open_work_items(wiql=wiql)
    except Exception as exc:
        logger.warning("similar_tickets: WIQL query falló: %s", exc)
        return []

    out: list[SimilarTicket] = []
    for row in rows[:max_results]:
        fields = row.get("fields") or {}
        ado_id = row.get("id")
        if ado_id is None or ado_id == current_ado_id:
            continue
        try:
            url = client.work_item_url(int(ado_id))
        except Exception:
            url = ""
        out.append(SimilarTicket(
            ado_id=int(ado_id),
            title=str(fields.get("System.Title") or ""),
            state=str(fields.get("System.State") or ""),
            work_item_type=str(fields.get("System.WorkItemType") or ""),
            url=url,
        ))
    return out


def build_similar_tickets_block(
    *,
    current_ado_id: int | None,
    current_title: str,
    project: str,
    project_name: str | None = None,
) -> dict | None:
    """Construye el context block `ado-similar-tickets` o None si no hay match."""
    similars = find_similar_tickets(
        current_ado_id=current_ado_id,
        current_title=current_title,
        project=project,
        project_name=project_name,
    )
    if not similars:
        return None

    content_lines = [
        f"Tickets ADO con título similar al del ticket actual (ADO-{current_ado_id}).",
        "Si vas a proponer crear un ticket nuevo, revisá esta lista primero —",
        "si alguno coincide en alcance, NO propongas crearlo; referenciá el existente.",
        "",
    ]
    for t in similars:
        content_lines.append(
            f"- ADO-{t.ado_id} [{t.work_item_type} / {t.state}] {t.title} → {t.url}"
        )

    return {
        "kind": "text",
        "id": SIMILAR_BLOCK_ID,
        "title": f"Tickets similares en ADO para ADO-{current_ado_id}",
        "content": "\n".join(content_lines),
        "metadata": {
            "count": len(similars),
            "tickets": [t.to_dict() for t in similars],
        },
    }


def inject_into_blocks(
    raw_blocks: list[dict] | None,
    *,
    current_ado_id: int | None,
    current_title: str,
    project: str,
    project_name: str | None = None,
) -> tuple[list[dict], dict | None]:
    """Idempotente: si ya hay un bloque con id `ado-similar-tickets`, no re-inyecta.

    Retorna (blocks_actualizados, info_diagnóstico_o_None).
    """
    blocks = list(raw_blocks or [])
    existing_ids = {b.get("id") for b in blocks if isinstance(b, dict)}
    if SIMILAR_BLOCK_ID in existing_ids:
        return blocks, {"skipped": "already_present"}

    block = build_similar_tickets_block(
        current_ado_id=current_ado_id,
        current_title=current_title,
        project=project,
        project_name=project_name,
    )
    if block is None:
        return blocks, None

    blocks.append(block)
    return blocks, {
        "injected": True,
        "count": block["metadata"]["count"],
    }


# ── Helpers ──────────────────────────────────────────────────────────────────


def _build_wiql(
    *, project: str, keywords: list[str], exclude_id: int | None, max_results: int
) -> str:
    """Construye un WIQL que busca por título conteniendo cualquiera de las keywords.

    Escapamos las comillas simples duplicándolas (convención WIQL).
    """
    title_clauses = " OR ".join(
        f"[System.Title] CONTAINS '{_escape_wiql(kw)}'" for kw in keywords
    )
    wiql = (
        "SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType] "
        "FROM workitems "
        f"WHERE [System.TeamProject] = '{_escape_wiql(project)}' "
        f"  AND ({title_clauses})"
    )
    if exclude_id is not None:
        wiql += f"  AND [System.Id] <> {int(exclude_id)}"
    wiql += "  ORDER BY [System.ChangedDate] DESC"
    return wiql


def _escape_wiql(value: str) -> str:
    """Escapa comillas simples para WIQL (duplicado standard SQL)."""
    return value.replace("'", "''")
