"""
ado_context.py — Enriquecimiento automático de contexto vía Azure DevOps.

Inyecta automáticamente al contexto del agente (es decir, al payload que se
envía al chat de Copilot) los siguientes ContextBlocks derivados del work item:

  - Comentarios del ticket (fetch_comments)
  - Adjuntos del ticket (fetch_attachments): metadatos + contenido de texto
    (cuando es texto pequeño)

Los bloques se agregan al final del contexto existente, no reemplazan nada.
Si ADO no está disponible o el ticket no tiene comentarios/adjuntos, devuelve
el contexto sin cambios y deja log de warning.

Política de agentes enriquecidos
--------------------------------
Por defecto, **todos los agentes registrados** reciben el enriquecimiento. Esto
asegura que el contexto que llega al chat sea siempre completo (no quedan
huecos por tipo de agente).

Configurable vía variable de entorno:
  ADO_CONTEXT_ENRICH_AGENTS

  - "" o no seteada → todos los agentes
  - "all" / "*"     → todos los agentes
  - "none" / "off"  → desactivado completamente
  - "technical,developer,qa" → lista CSV de agent.type permitidos

Configurable vía variable de entorno (límites de descarga):
  ADO_CONTEXT_ATTACH_MAX_TEXT_FILES   (default 5)
    Tope de adjuntos de texto cuyo contenido se descarga e incluye en el
    prompt. Los demás se listan solo como metadata (nombre + URL + tamaño).

Trazabilidad
------------
La función `enrich(...)` retorna la lista de bloques actualizada **y** un dict
opcional `stats` por canal lateral (vía el callable `log`) cuando el caller lo
pasa. Los counts (#comentarios, #adjuntos, #texto-descargado) quedan también
expuestos en los logs.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Iterable

logger = logging.getLogger("stacky_agents.ado_context")

# Lista por defecto: todos los agentes que reciben enriquecimiento ADO.
# Si se prefiere un subconjunto, setear ADO_CONTEXT_ENRICH_AGENTS.
_DEFAULT_ENRICHED_AGENTS = frozenset({
    "business",
    "functional",
    "technical",
    "developer",
    "qa",
    "debug",
    "pr-review",
    "custom",
})

# Mapa simple extensión → mime_type, suficiente para los tipos que ADO suele
# adjuntar en tickets (capturas, docs, logs). No es autoritativo: cuando el
# AdoClient pueda devolver `mime_type` directamente, ese valor gana.
_EXT_TO_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".html": "text/html",
    ".htm": "text/html",
    ".xml": "application/xml",
    ".json": "application/json",
    ".csv": "text/csv",
    ".log": "text/plain",
    ".cs": "text/x-csharp",
    ".vb": "text/x-vb",
    ".sql": "application/sql",
    ".py": "text/x-python",
    ".js": "application/javascript",
    ".ts": "application/typescript",
    ".doc": "application/msword",
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    ".xls": "application/vnd.ms-excel",
    ".xlsx": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ),
    ".zip": "application/zip",
}


def _env_csv(name: str) -> list[str] | None:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return None
    return [x.strip().lower() for x in raw.split(",") if x.strip()]


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        logger.warning("ado_context — %s='%s' no es int, usando default %d", name, raw, default)
        return default


def is_enrichment_enabled(agent_type: str) -> bool:
    """Decide si un agent_type debe recibir enriquecimiento ADO según env y default."""
    csv = _env_csv("ADO_CONTEXT_ENRICH_AGENTS")
    if csv is None:
        return agent_type in _DEFAULT_ENRICHED_AGENTS
    if any(x in {"all", "*"} for x in csv):
        return True
    if any(x in {"none", "off", "false", "0"} for x in csv):
        return False
    return agent_type.lower() in set(csv)


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


def _guess_mime(name: str, hint: str | None = None) -> str | None:
    """Retorna mime_type a partir de un hint explícito o de la extensión del archivo."""
    if hint:
        h = hint.strip()
        if h:
            return h
    if not name or "." not in name:
        return None
    ext = "." + name.rsplit(".", 1)[-1].lower()
    return _EXT_TO_MIME.get(ext)


def _format_size(size: int) -> str:
    if not size:
        return "tamaño desconocido"
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def construir_bloques_de_comentarios(
    raw_comments: list[dict], *, titulo: str, sello: str | None = None,
) -> tuple[list[dict], int]:
    """Plan 289 F5 — Arma los bloques de comentarios. UNICO armador, los 2 trackers.

    Entrada: comentarios en forma canonica {author, date, text[, is_html]}.
      - `is_html` AUSENTE significa True (camino ADO: byte-identico a antes del plan).
      - `is_html=False` (camino GitLab, Markdown) SALTEA _html_to_text: pasarle
        Markdown al parser de HTML borra fragmentos como `List<int>`.

    `sello` (Plan 289 v2, [ADICION ARQUITECTO] 2) es una linea de procedencia que se
    antepone al contenido: de que tracker vienen, cuantos de cuantos son y en que
    sentido estan ordenados. AUSENTE por defecto => el camino ADO queda BYTE-IDENTICO.
    Existe porque `enrich` filtra las claves de `stats` por whitelist (§4.10): el
    sello es la unica declaracion que sobrevive hasta el prompt del agente pase lo
    que pase con la metadata.

    Devuelve (bloques, cantidad_de_comentarios_renderizados). Los bloques salen en el
    mismo orden que antes: ado-blocker (si hay) primero, ado-comments despues.

    Plan 289 F5 — todo el texto pasa por mask_token_values ANTES de entrar al bloque.
    Es un endurecimiento DELIBERADO que tambien alcanza a Azure DevOps.
    """
    from services.secret_masking import mask_token_values

    if not raw_comments:
        return [], 0

    def _texto(c: dict) -> str:
        crudo = c.get("text") or ""
        limpio = _html_to_text(crudo) if c.get("is_html", True) else crudo.strip()
        return mask_token_values(limpio)

    bloques: list[dict] = []

    # ── ado-blocker (Plan 133 F3) — se detecta ANTES para que quede primero.
    #    CERO fetch extra: reusa la misma lista.
    try:
        from config import config as _config

        if getattr(_config, "STACKY_ADO_BLOCKER_BLOCK_ENABLED", False):
            from services.business_preflight import BLOCKER_MARKER  # lazy: evita ciclos

            con_marca = [c for c in raw_comments if BLOCKER_MARKER in _texto(c)]
            if con_marca:
                bloqueante = max(con_marca, key=lambda c: (c.get("date") or ""))
                bloques.append({
                    "kind": "text",
                    "id": "ado-blocker",
                    "title": "🚫 Bloqueante técnico detectado (server-side)",
                    "content": (
                        f"Autor: {bloqueante.get('author', '?')}\n"
                        f"Fecha: {bloqueante.get('date', '')}\n\n"
                        f"{_texto(bloqueante)}"
                    ),
                    "priority": "high",
                })
    except Exception as e:  # noqa: BLE001 — best-effort, nunca bloquea el enrich
        logger.warning("ado_context — detección de ado-blocker falló: %s", e)

    lineas: list[str] = []
    for c in raw_comments:
        texto = _texto(c)
        if not texto:
            continue
        lineas.append(f"**{c.get('author', '?')}** ({c.get('date', '')}):\n{texto}")

    if lineas:
        cuerpo = "\n\n---\n\n".join(lineas)
        if sello:                                   # v2, [ADICION ARQUITECTO] 2
            cuerpo = f"_({sello})_\n\n{cuerpo}"
        bloques.append({
            "kind": "text",
            "id": "ado-comments",
            "title": titulo,
            "content": cuerpo,
        })
    return bloques, len(lineas)


def _bloques_por_proveedor(
    *, item_id: int, project_name: str | None, stats: dict,
) -> tuple[list[dict], dict]:
    """Plan 289 F6 — rama no-ADO: comentarios por la costura de proveedor.

    Los ADJUNTOS quedan fuera a proposito (§6.1 del plan 289): el proveedor de
    GitLab no descarga contenido, solo saca links por regex de la descripcion
    (gitlab_provider.py:526-542). `attachments_count` se queda en 0 y se DECLARA
    el motivo, para que un 0 no se confunda con un fallo.
    """
    from services import tracker_context

    comentarios, cstats = tracker_context.fetch_comentarios_normalizados(
        project_name=project_name, item_id=item_id,
    )
    # v2, [ADICION ARQUITECTO] 2 — el sello viaja DENTRO del bloque, no solo en stats:
    # `enrich` filtra stats por whitelist (§4.10) pero el content llega intacto al prompt.
    total = cstats.get("comments_total_disponibles", len(comentarios))
    sello = (
        f"GitLab · {len(comentarios)} de {total} comentarios (los mas recientes)"
        if cstats.get("comments_truncated")
        else f"GitLab · {len(comentarios)} comentarios"
    ) + ", del mas antiguo al mas reciente"
    bloques, cantidad = construir_bloques_de_comentarios(
        comentarios, titulo="Comentarios del ticket (GitLab)", sello=sello,
    )
    stats["comments_count"] = cantidad
    stats["comments_truncated"] = cstats.get("comments_truncated", False)
    stats["errors"].extend(cstats.get("errors") or [])
    stats["attachments_skipped_reason"] = "provider_sin_descarga_de_adjuntos"
    return bloques, stats


def build_ado_context_blocks(
    ado_id: int,
    *,
    max_text_attachments: int | None = None,
    project_name: str | None = None,
    tracker_project: str | None = None,
    ticket=None,
) -> tuple[list[dict], dict]:
    """Construye los context blocks con comentarios y adjuntos de un work item ADO.

    Devuelve `(blocks, stats)`:
      - blocks: lista de ContextBlocks listos para concatenar al prompt.
      - stats: dict con conteos para trazabilidad y metadata.

    Si hay error de config/API, devuelve ([], stats_zeros) silenciosamente
    (no bloquea la ejecución del agente).
    """
    stats: dict = {
        "comments_count": 0,
        "attachments_count": 0,
        "attachments_text_inlined": 0,
        "errors": [],
    }

    # ── Plan 289 F6 — dispatcher por tracker. ADITIVO: si el proyecto es ADO
    #    (o la flag esta apagada) el resto de la funcion corre BYTE-IDENTICO.
    #    PROHIBIDO decidir leyendo la columna `tracker_type` del ticket: esa
    #    columna miente (Plan 281/286) y ademas el DoD del 289 la censa por grep,
    #    asi que ni siquiera se la nombra aca. Se pregunta al helper del Plan 286.
    try:
        from config import config as _cfg289

        if getattr(_cfg289, "STACKY_TRACKER_CONTEXT_ENABLED", True):
            from services.project_context import (
                tracker_efectivo_de_ticket,
                tracker_is_azure_devops,
            )

            if ticket is not None:
                _tracker = tracker_efectivo_de_ticket(ticket)
                _es_ado = _tracker == "azure_devops"
            else:
                # Sin ticket no hay a quien preguntarle la precedencia completa;
                # el resolvedor canonico por nombre de proyecto alcanza y conserva
                # el fail-closed a ADO del Plan 281 (project_context.py:64-65).
                _es_ado = tracker_is_azure_devops(project_name)

            if not _es_ado:
                return _bloques_por_proveedor(
                    item_id=ado_id, project_name=project_name, stats=stats,
                )
    except Exception as e:  # noqa: BLE001 — el dispatcher NUNCA tumba el enrich
        logger.warning("ado_context — dispatcher por tracker falló: %s", e)
        stats["errors"].append(f"tracker_dispatch_failed: {e}")

    try:
        from services.project_context import build_ado_client

        client = build_ado_client(
            project_name=project_name,
            tracker_project=tracker_project,
            ticket=ticket,
        )
    except Exception as e:
        logger.warning("ado_context — no se pudo instanciar AdoClient: %s", e)
        stats["errors"].append(f"ado_client_init_failed: {e}")
        return [], stats

    if max_text_attachments is None:
        max_text_attachments = _env_int("ADO_CONTEXT_ATTACH_MAX_TEXT_FILES", 5)

    blocks: list[dict] = []

    # ── Comentarios ──────────────────────────────────────────────────────────
    try:
        raw_comments = client.fetch_comments(ado_id, top=30)
        nuevos, cantidad = construir_bloques_de_comentarios(
            raw_comments, titulo="Comentarios ADO del ticket",
        )
        blocks.extend(nuevos)
        stats["comments_count"] = cantidad
    except Exception as e:
        logger.warning("ado_context — fetch_comments(%s) falló: %s", ado_id, e)
        stats["errors"].append(f"fetch_comments_failed: {e}")

    # ── Adjuntos ─────────────────────────────────────────────────────────────
    try:
        attachments = client.fetch_attachments(ado_id)
        if attachments:
            attach_lines: list[str] = []
            text_blocks: list[dict] = []
            text_inlined = 0

            for att in attachments:
                name = att.get("name") or "(sin nombre)"
                size = int(att.get("size") or 0)
                url = att.get("url") or ""
                text_content = att.get("text_content")
                mime_hint = att.get("mime_type") or att.get("mimeType")
                mime = _guess_mime(name, mime_hint)

                # Línea de metadata en el bloque índice (Markdown legible para
                # el LLM y trazable para el operador).
                size_str = _format_size(size)
                meta_parts = [f"**{name}**", size_str]
                if mime:
                    meta_parts.append(f"`{mime}`")
                line = "- " + "  ·  ".join(meta_parts)
                if url:
                    line += f"\n  {url}"
                attach_lines.append(line)

                # Inline del contenido textual con tope configurable
                if text_content and text_inlined < max_text_attachments:
                    text_blocks.append({
                        "kind": "text",
                        "id": f"ado-attachment-{name}",
                        "title": f"Adjunto ADO: {name}",
                        "content": text_content.strip(),
                    })
                    text_inlined += 1

            if attach_lines:
                stats["attachments_count"] = len(attach_lines)
                stats["attachments_text_inlined"] = text_inlined
                blocks.append({
                    "kind": "text",
                    "id": "ado-attachments-index",
                    "title": "Adjuntos ADO del ticket",
                    "content": "\n".join(attach_lines),
                })
            blocks.extend(text_blocks)
    except Exception as e:
        logger.warning("ado_context — fetch_attachments(%s) falló: %s", ado_id, e)
        stats["errors"].append(f"fetch_attachments_failed: {e}")

    return blocks, stats


def enrich(
    ticket_id: int,
    agent_type: str,
    existing_blocks: list[dict],
    ado_id: int,
    log=None,
    *,
    return_stats: bool = False,
    project_name: str | None = None,
    tracker_project: str | None = None,
    ticket=None,
) -> list[dict] | tuple[list[dict], dict]:
    """Punto de entrada principal llamado por agent_runner.

    Retorna los existing_blocks con los bloques ADO appended al final.
    Si el agente no recibe enriquecimiento (según env / default) o hay error,
    devuelve los blocks sin cambios.

    Si `return_stats=True`, devuelve `(blocks, stats)` para que el caller
    persista los contadores en metadata.
    """
    stats: dict = {
        "comments_count": 0,
        "attachments_count": 0,
        "attachments_text_inlined": 0,
        "skipped": False,
        "skipped_reason": None,
        "errors": [],
    }

    if not is_enrichment_enabled(agent_type):
        stats["skipped"] = True
        stats["skipped_reason"] = "agent_not_in_enrich_list"
        if log:
            log("info", f"ado_context — agente '{agent_type}' no enriquecido (ADO_CONTEXT_ENRICH_AGENTS)")
        return (list(existing_blocks), stats) if return_stats else list(existing_blocks)

    # Idempotencia: si ya hay bloques ADO, no re-inyectar.
    existing_ids = {b.get("id") for b in (existing_blocks or []) if isinstance(b, dict)}
    if "ado-comments" in existing_ids or "ado-attachments-index" in existing_ids:
        stats["skipped"] = True
        stats["skipped_reason"] = "already_enriched"
        if log:
            log("info", "ado_context — bloques ADO ya presentes, omitiendo enriquecimiento")
        return (list(existing_blocks), stats) if return_stats else list(existing_blocks)

    if log:
        log("info", f"ado_context — enriqueciendo con comentarios y adjuntos ADO ({ado_id})")

    ado_blocks, build_stats = build_ado_context_blocks(
        ado_id,
        project_name=project_name,
        tracker_project=tracker_project,
        ticket=ticket,
    )
    stats.update({
        "comments_count": build_stats.get("comments_count", 0),
        "attachments_count": build_stats.get("attachments_count", 0),
        "attachments_text_inlined": build_stats.get("attachments_text_inlined", 0),
        "errors": build_stats.get("errors", []),
    })
    # Plan 289 F6.3 — las claves del camino por proveedor NO estaban en la whitelist
    # de arriba y se perdian en silencio: el operador veia comments_count=0 sin motivo
    # y attachments_count=0 sin saber que el proveedor no descarga adjuntos.
    # Se copian solo si el productor las puso: en el camino ADO no existen y el
    # metadata queda BYTE-IDENTICO al de antes del plan.
    for _clave in ("comments_truncated", "comments_total_disponibles",
                   "attachments_skipped_reason"):
        if _clave in build_stats:
            stats[_clave] = build_stats[_clave]

    if log and (ado_blocks or stats["errors"]):
        log(
            "info",
            (
                f"ado_context — {stats['comments_count']} comentarios, "
                f"{stats['attachments_count']} adjuntos "
                f"({stats['attachments_text_inlined']} con texto inline)"
            ),
        )
        if stats["errors"]:
            log("warn", f"ado_context — errores no fatales: {stats['errors']}")

    out = list(existing_blocks) + ado_blocks
    return (out, stats) if return_stats else out
