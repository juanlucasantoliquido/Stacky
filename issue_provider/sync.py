"""
issue_provider.sync — Sincroniza tickets remotos al filesystem local.

Escribe el mismo layout que ya consumía Stacky:

    projects/<NAME>/tickets/<estado>/<ticket_id>/
        INC-<id>.md               — metadata + descripción + notas
        INCIDENTE.md              — placeholder PM
        ANALISIS_TECNICO.md       — placeholder PM
        ARQUITECTURA_SOLUCION.md  — placeholder PM
        TAREAS_DESARROLLO.md      — placeholder PM (Dev consume)
        QUERIES_ANALISIS.sql      — placeholder PM
        NOTAS_IMPLEMENTACION.md   — placeholder PM

El archivo `state/seen_tickets.json` se reutiliza con la misma semántica:
    { "tickets": { "<id>": { "estado_normalizado": "asignada",
                             "titulo": "...", "processed_at": "ISO" } },
      "last_run": "ISO" }

Detecta cambios de estado y mueve la carpeta del ticket a la nueva
carpeta {estado}/ cuando el work item cambia de estado en ADO.
Notifica al pipeline state cuando detecta cambios significativos.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

from .base import IssueProvider
from .factory import get_provider, load_tracker_config
from .types import TicketDetail

logger = logging.getLogger("stacky.issue.sync")

# Conjunto canónico de buckets de estado que Stacky maneja. Si el mapping
# del provider devuelve otro, queda como literal y se crea la subcarpeta.
_STATE_BUCKETS = {"asignada", "aceptada", "resuelta", "completada", "archivada"}

# Archivos PM generados como placeholder (idéntico al que ya creaba el scraper).
_PM_PLACEHOLDERS: dict[str, str] = {
    "INCIDENTE.md": """# Incidente — {ticket_id}

**Título:** {title}
**Tipo:** {work_item_type}
**Severidad:** {severity}
**Prioridad:** {priority}
**Categoría:** {category}
**URL:** {ticket_url}

## Impacto de negocio

_A completar por PM_

## Resumen ejecutivo

_A completar por PM_
""",
    "ANALISIS_TECNICO.md": """# Análisis técnico — {ticket_id}

## Causa raíz

_A completar por PM_

## Componentes afectados

_A completar por PM_

## Flujo actual vs. esperado

_A completar por PM_
""",
    "ARQUITECTURA_SOLUCION.md": """# Arquitectura de la solución — {ticket_id}

## Cambios propuestos

_A completar por PM_

## Archivos a modificar

_A completar por PM_
""",
    "TAREAS_DESARROLLO.md": """# Tareas de desarrollo — {ticket_id}

## Estado: PENDIENTE

_A completar por PM_

| # | Tarea | Archivos | Criterios de aceptación | Estado |
|---|-------|----------|-------------------------|--------|
| 1 | _A completar por PM_ | | | PENDIENTE |
""",
    "QUERIES_ANALISIS.sql": """-- Queries de análisis — Ticket {ticket_id}
-- Generado: {generated_at}

-- _A completar por PM_
""",
    "NOTAS_IMPLEMENTACION.md": """# Notas de implementación — {ticket_id}

## Convenciones críticas

_A completar por PM_

## Advertencias

_A completar por PM_

## Dependencias

_A completar por PM_
""",
}

_INC_MD_TEMPLATE = """---
ticket_id: "{ticket_id}"
titulo: "{title_esc}"
tracker: "{tracker_name}"
tracker_id: "{ticket_id}"
tracker_state: "{state_raw}"
estado_normalizado: "{state_normalized}"
tipo: "{work_item_type}"
severity: "{severity}"
priority: "{priority}"
assignee: "{assignee_esc}"
last_modified: "{last_modified}"
url: "{ticket_url}"
area_path: "{area_path_esc}"
iteration_path: "{iteration_path_esc}"
tags: "{tags_esc}"
generated_at: "{generated_at}"
---

# {title}

## Metadatos

- **Tipo:** {work_item_type}
- **Estado remoto:** `{state_raw}` → bucket Stacky: `{state_normalized}`
- **Asignado a:** {assignee}
- **Prioridad:** {priority}
- **Severidad:** {severity}
- **Área:** `{area_path}`
- **Iteración:** `{iteration_path}`
- **Tags:** {tags}
- **URL:** {ticket_url}

## Descripción

{description}

## Criterios de aceptación / Información adicional

{additional_info}

## Pasos para reproducir

{reproduction_steps}

## Historial de comentarios

{comments_block}

## Adjuntos

{attachments_block}
"""


def sync_tickets(
    project_name: str,
    force: bool = False,
    limit: int | None = None,
) -> dict:
    """
    Entry point — reemplazo del scraper cuando el
    tracker activo usa un provider nativo.

    Devuelve resumen:
        { "fetched": N, "new": N, "updated": N, "moved": N, "errors": [...] }

    Si no hay provider nativo, retorna un error.
    que el caller delegue en run_scraper() (que usa Playwright y requiere
    flujo distinto).
    """
    cfg = load_tracker_config(project_name)
    if not cfg:
        raise RuntimeError("No hay configuración de issue_tracker.")

    if not cfg.get("type", ""):
        return {
            "fetched": 0, "new": 0, "updated": 0, "moved": 0,
            "error": "No tracker type configured",
            "errors": [],
        }

    provider = get_provider(project_name, override_config=cfg)
    ok, why = provider.is_available()
    if not ok:
        raise RuntimeError(f"Provider '{provider.name}' no disponible: {why}")

    # Resolver paths del proyecto
    from project_manager import get_project_paths
    paths = get_project_paths(project_name)
    tickets_base = Path(paths["tickets"])
    tickets_base.mkdir(parents=True, exist_ok=True)
    state_path = Path(paths["base"]) / "state" / "seen_tickets.json"
    state = _load_seen_state(state_path)

    summary = {"fetched": 0, "new": 0, "updated": 0, "moved": 0, "errors": []}

    tickets = provider.fetch_open_tickets()
    if limit:
        tickets = tickets[:limit]
    summary["fetched"] = len(tickets)
    logger.info("[%s] %d work items abiertos", provider.name, len(tickets))

    for t in tickets:
        try:
            # Mover carpeta si cambió el bucket de estado
            previous_entry = (state.get("tickets") or {}).get(t.id) or {}
            previous_bucket = previous_entry.get("estado_normalizado")
            if previous_bucket and previous_bucket != t.state_normalized:
                if _move_ticket_folder(tickets_base, previous_bucket,
                                        t.state_normalized, t.id):
                    summary["moved"] += 1

            is_new = t.id not in (state.get("tickets") or {})
            if not is_new and not force:
                # ¿Cambió last_modified? Si no, no re-escribimos el INC.
                prev_lm = previous_entry.get("last_modified", "")
                folder_check = _ticket_folder(tickets_base, t.state_normalized, t.id)
                if prev_lm == t.last_modified and folder_check.exists():
                    continue

            detail = provider.fetch_ticket_detail(t.id)
            folder = _ticket_folder(tickets_base, t.state_normalized, t.id)
            folder.mkdir(parents=True, exist_ok=True)
            _write_inc_md(folder, detail, provider.name)
            _write_placeholders(folder, detail)
            summary["new" if is_new else "updated"] += 1

            state.setdefault("tickets", {})[t.id] = {
                "estado_normalizado": t.state_normalized,
                "estado_raw":         t.state_raw,
                "titulo":             t.title,
                "last_modified":      t.last_modified,
                "processed_at":       datetime.now().isoformat(),
                "url":                t.url,
            }
        except Exception as e:
            logger.warning("Error procesando ticket %s: %s", t.id, e)
            summary["errors"].append({"ticket_id": t.id, "error": str(e)[:200]})

    state["last_run"] = datetime.now().isoformat()
    _save_seen_state(state_path, state)
    logger.info("Sync terminado: %s", summary)
    return summary


# ── helpers ───────────────────────────────────────────────────────────────

def _load_seen_state(path: Path) -> dict:
    if not path.exists():
        return {"tickets": {}, "last_run": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("seen_tickets.json ilegible (%s) — re-creando", e)
        return {"tickets": {}, "last_run": None}
    if "tickets" not in data:
        data = {"tickets": {}, "last_run": data.get("last_run")}
    return data


def _save_seen_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    os.replace(tmp, path)


def _ticket_folder(base: Path, bucket: str, ticket_id: str) -> Path:
    safe_bucket = bucket if bucket in _STATE_BUCKETS else (bucket or "asignada")
    return base / safe_bucket / str(ticket_id)


def _move_ticket_folder(base: Path, prev: str, new: str, ticket_id: str) -> bool:
    src = base / prev / str(ticket_id)
    dst = base / new / str(ticket_id)
    if not src.exists() or src == dst:
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        # Colisión improbable: merge conservador — preservar artefactos existentes
        logger.info("Ticket %s ya existe en nuevo bucket %s — skip move", ticket_id, new)
        return False
    shutil.move(str(src), str(dst))
    logger.info("Ticket %s movido: %s → %s", ticket_id, prev, new)
    return True


def _write_inc_md(folder: Path, detail: TicketDetail, tracker_name: str) -> None:
    t = detail.ticket
    body = _INC_MD_TEMPLATE.format(
        ticket_id=t.id,
        title=_safe(t.title) or f"Ticket #{t.id}",
        title_esc=_yaml_escape(t.title),
        tracker_name=tracker_name,
        state_raw=_safe(t.state_raw),
        state_normalized=_safe(t.state_normalized),
        work_item_type=_safe(t.category),
        severity=_safe(t.severity),
        priority=str(t.priority) if t.priority is not None else "",
        assignee=_safe(t.assignee),
        assignee_esc=_yaml_escape(t.assignee),
        last_modified=_safe(t.last_modified),
        ticket_url=_safe(t.url),
        area_path=_safe(str(detail.extra.get("area_path", ""))),
        area_path_esc=_yaml_escape(str(detail.extra.get("area_path", ""))),
        iteration_path=_safe(str(detail.extra.get("iteration_path", ""))),
        iteration_path_esc=_yaml_escape(str(detail.extra.get("iteration_path", ""))),
        tags=_safe(str(detail.extra.get("tags", ""))),
        tags_esc=_yaml_escape(str(detail.extra.get("tags", ""))),
        generated_at=datetime.now().isoformat(),
        description=_html_to_md(detail.description) if detail.description_is_html else (detail.description or "_sin descripción_"),
        additional_info=_html_to_md(detail.additional_info) if detail.description_is_html else (detail.additional_info or "_sin criterios de aceptación_"),
        reproduction_steps=_html_to_md(detail.reproduction_steps) if detail.description_is_html else (detail.reproduction_steps or "_sin pasos para reproducir_"),
        comments_block=_comments_to_md(detail.comments) or "_sin comentarios_",
        attachments_block=_attachments_to_md(detail.attachments) or "_sin adjuntos_",
    )
    (folder / f"INC-{t.id}.md").write_text(body, encoding="utf-8")


def _write_placeholders(folder: Path, detail: TicketDetail) -> None:
    t = detail.ticket
    ctx = {
        "ticket_id":     t.id,
        "title":         _safe(t.title) or f"Ticket #{t.id}",
        "work_item_type": _safe(t.category),
        "severity":      _safe(t.severity) or "-",
        "priority":      str(t.priority) if t.priority is not None else "-",
        "category":      _safe(detail.extra.get("tags", "")) or "-",
        "ticket_url":    _safe(t.url),
        "generated_at":  datetime.now().isoformat(),
    }
    for fname, template in _PM_PLACEHOLDERS.items():
        target = folder / fname
        # No sobrescribir si ya existe — preserva el trabajo del PM/Dev/QA
        if target.exists():
            continue
        try:
            target.write_text(template.format(**ctx), encoding="utf-8")
        except Exception as e:
            logger.warning("No se pudo escribir %s: %s", target, e)


def _comments_to_md(comments) -> str:
    if not comments:
        return ""
    out = []
    for c in comments:
        out.append(f"### {c.author or 'Anónimo'} — {c.created_at}\n")
        out.append(_html_to_md(c.body) if c.is_html else c.body)
        out.append("\n")
    return "\n".join(out)


def _attachments_to_md(attachments) -> str:
    if not attachments:
        return ""
    lines = []
    for a in attachments:
        size_kb = (a.size_bytes / 1024.0) if a.size_bytes else 0
        lines.append(f"- `{a.filename}` ({size_kb:.1f} KB) — {a.url}")
    return "\n".join(lines)


def _safe(s) -> str:
    if s is None:
        return ""
    return str(s).replace("\r", "").strip()


def _yaml_escape(s) -> str:
    return _safe(s).replace('"', '\\"')


# ── conversión HTML → Markdown liviana ─────────────────────────────────

_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_P_RE = re.compile(r"</p>", re.IGNORECASE)
_LI_RE = re.compile(r"<li[^>]*>", re.IGNORECASE)
_LI_CLOSE_RE = re.compile(r"</li>", re.IGNORECASE)
_H_RE = re.compile(r"<h([1-6])[^>]*>(.*?)</h\1>", re.IGNORECASE | re.DOTALL)
_STRONG_RE = re.compile(r"<(strong|b)[^>]*>(.*?)</\1>", re.IGNORECASE | re.DOTALL)
_EM_RE = re.compile(r"<(em|i)[^>]*>(.*?)</\1>", re.IGNORECASE | re.DOTALL)
_CODE_RE = re.compile(r"<code[^>]*>(.*?)</code>", re.IGNORECASE | re.DOTALL)
_ENTITIES = [
    ("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
    ("&quot;", '"'), ("&#39;", "'"),
]


def _html_to_md(html: str) -> str:
    """
    Conversión liviana de HTML (típico de ADO System.Description) a Markdown
    legible. No pretende ser exhaustiva — solo mejorar legibilidad del INC.md.
    """
    if not html:
        return ""
    s = html
    s = _H_RE.sub(lambda m: f"\n\n{'#' * int(m.group(1))} {m.group(2).strip()}\n\n", s)
    s = _STRONG_RE.sub(lambda m: f"**{m.group(2).strip()}**", s)
    s = _EM_RE.sub(lambda m: f"*{m.group(2).strip()}*", s)
    s = _CODE_RE.sub(lambda m: f"`{m.group(1).strip()}`", s)
    s = _BR_RE.sub("\n", s)
    s = _P_RE.sub("\n\n", s)
    s = _LI_RE.sub("- ", s)
    s = _LI_CLOSE_RE.sub("\n", s)
    s = _TAG_RE.sub("", s)
    for k, v in _ENTITIES:
        s = s.replace(k, v)
    # Compactar líneas en blanco
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()
