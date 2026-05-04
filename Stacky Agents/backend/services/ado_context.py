"""
ado_context.py — Enriquecimiento automático de contexto vía Azure DevOps.

Para los agentes TechnicalAgent y DeveloperAgent inyecta automáticamente:
  - Comentarios del ticket (fetch_comments)
  - Adjuntos del ticket (fetch_attachments): metadatos + contenido de texto

Los bloques se agregan al final del contexto existente, no reemplazan nada.
Si ADO no está disponible o el ticket no tiene comentarios/adjuntos, devuelve [].
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger("stacky_agents.ado_context")

# Agentes que reciben el enriquecimiento ADO automáticamente.
_ENRICHED_AGENTS = {"technical", "developer"}


def _html_to_text(html: str) -> str:
    """Convierte HTML a texto plano (misma lógica que ado_sync)."""
    if not html:
        return ""
    try:
        from html.parser import HTMLParser

        class _S(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self.parts: list[str] = []

            def handle_data(self, data: str) -> None:
                if data:
                    self.parts.append(data)

            def handle_starttag(self, tag, attrs) -> None:
                if tag in {"br", "p", "div", "li", "tr"}:
                    self.parts.append("\n")

            def handle_endtag(self, tag) -> None:
                if tag in {"p", "div", "li", "tr"}:
                    self.parts.append("\n")

        p = _S()
        p.feed(html)
        text = "".join(p.parts)
        return re.sub(r"\n{3,}", "\n\n", text).strip()
    except Exception:
        return re.sub(r"<[^>]+>", " ", html).strip()


def build_ado_context_blocks(ado_id: int) -> list[dict]:
    """Construye los context blocks con comentarios y adjuntos de un work item ADO.

    Devuelve lista de ContextBlocks listos para concatenar al prompt.
    Si hay error de config/API, devuelve [] silenciosamente (no bloquea la ejecución).
    """
    try:
        from services.ado_client import AdoClient, AdoConfigError
        client = AdoClient()
    except Exception as e:
        logger.warning("ado_context — no se pudo instanciar AdoClient: %s", e)
        return []

    blocks: list[dict] = []

    # ── Comentarios ──────────────────────────────────────────────────────────
    try:
        raw_comments = client.fetch_comments(ado_id, top=30)
        if raw_comments:
            lines: list[str] = []
            for c in raw_comments:
                text = _html_to_text(c.get("text") or "")
                if not text:
                    continue
                author = c.get("author", "?")
                date = c.get("date", "")
                lines.append(f"**{author}** ({date}):\n{text}")
            if lines:
                blocks.append({
                    "kind": "text",
                    "id": "ado-comments",
                    "title": "Comentarios ADO del ticket",
                    "content": "\n\n---\n\n".join(lines),
                })
    except Exception as e:
        logger.warning("ado_context — fetch_comments(%s) falló: %s", ado_id, e)

    # ── Adjuntos ─────────────────────────────────────────────────────────────
    try:
        attachments = client.fetch_attachments(ado_id)
        if attachments:
            attach_lines: list[str] = []
            text_blocks: list[dict] = []

            for att in attachments:
                name = att.get("name") or "(sin nombre)"
                size = att.get("size") or 0
                url = att.get("url") or ""
                text_content = att.get("text_content")

                # Línea de metadata en el bloque índice
                size_str = f"{size:,} bytes" if size else "tamaño desconocido"
                attach_lines.append(f"- **{name}** ({size_str})" + (f"  \n  {url}" if url else ""))

                # Si se pudo leer el contenido, crear un bloque separado
                if text_content:
                    text_blocks.append({
                        "kind": "text",
                        "id": f"ado-attachment-{name}",
                        "title": f"Adjunto ADO: {name}",
                        "content": text_content.strip(),
                    })

            if attach_lines:
                blocks.append({
                    "kind": "text",
                    "id": "ado-attachments-index",
                    "title": "Adjuntos ADO del ticket",
                    "content": "\n".join(attach_lines),
                })
            blocks.extend(text_blocks)
    except Exception as e:
        logger.warning("ado_context — fetch_attachments(%s) falló: %s", ado_id, e)

    return blocks


def enrich(
    ticket_id: int,
    agent_type: str,
    existing_blocks: list[dict],
    ado_id: int,
    log=None,
) -> list[dict]:
    """Punto de entrada principal llamado por agent_runner.

    Retorna los existing_blocks con los bloques ADO appended al final.
    Si el agente no es de los enriquecidos o hay error, devuelve los blocks sin cambios.
    """
    if agent_type not in _ENRICHED_AGENTS:
        return existing_blocks

    # Evitar inyectar si ya existe un bloque ado-comments (re-ejecución)
    existing_ids = {b.get("id") for b in existing_blocks if isinstance(b, dict)}
    if "ado-comments" in existing_ids or "ado-attachments-index" in existing_ids:
        if log:
            log("info", "ado_context — bloques ADO ya presentes, omitiendo enriquecimiento")
        return existing_blocks

    if log:
        log("info", f"ado_context — enriqueciendo con comentarios y adjuntos ADO ({ado_id})")

    ado_blocks = build_ado_context_blocks(ado_id)

    if ado_blocks and log:
        comment_block = next((b for b in ado_blocks if b.get("id") == "ado-comments"), None)
        attach_index = next((b for b in ado_blocks if b.get("id") == "ado-attachments-index"), None)
        n_comments = comment_block["content"].count("---") + 1 if comment_block else 0
        n_attachments = len([b for b in ado_blocks if str(b.get("id", "")).startswith("ado-attachment-")])
        log("info", f"ado_context — {n_comments} comentarios, {n_attachments} adjuntos con contenido")

    return list(existing_blocks) + ado_blocks
