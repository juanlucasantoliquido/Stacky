"""Plan 131 F6 — Doc del incidente + aristas en el grafo documental (§4.5).

Escribe un `.md` bajo `STACKY_AGENTS_ROOT/docs/incidencias/` (o el fallback de
`data_dir()/incident_docs` si `docs/` no existe — deploy congelado) que el
grafo documental (Plan 109/111) indexa automáticamente: el wikilink
`[[INDICE_INCIDENCIAS]]` da la arista doc→doc y las rutas de código en texto
plano de "Archivos probables" dan las aristas doc→código
(`services/doc_graph.py:parse_code_refs`).
"""
from __future__ import annotations

import re
from pathlib import Path

from services import doc_indexer

INCIDENTS_DOC_DIRNAME = "incidencias"
INDEX_NAME = "INDICE_INCIDENCIAS.md"


def _slugify(title: str) -> str:
    text = (title or "").lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text).strip("-")
    return text[:60] or "incidente"


def resolve_docs_root() -> Path:
    """`STACKY_AGENTS_ROOT/docs` si existe; si no, `data_dir()/incident_docs`
    (deploy congelado sin docs/ — el llamador debe avisar 'fuera del grafo')."""
    docs_root = doc_indexer.STACKY_AGENTS_ROOT / "docs"
    if docs_root.is_dir():
        return docs_root
    from runtime_paths import data_dir
    fallback = data_dir() / "incident_docs"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


_PROBABLE_FILES_SECTION_RE = re.compile(
    r"ARCHIVOS Y MODULOS PROBABLES.*?<ul>(.*?)</ul>", re.IGNORECASE | re.DOTALL,
)
_LIST_ITEM_RE = re.compile(r"<li>(.*?)</li>", re.IGNORECASE | re.DOTALL)


def _extract_probable_files(html: str) -> list[str]:
    """Rutas de código de la sección ARCHIVOS Y MODULOS PROBABLES (§4.3),
    una por <li>, texto plano (sin la razón tras el separador ' — ')."""
    m = _PROBABLE_FILES_SECTION_RE.search(html or "")
    if not m:
        return []
    out: list[str] = []
    for item in _LIST_ITEM_RE.findall(m.group(1)):
        plain = re.sub(r"<[^>]+>", " ", item).strip()
        token = re.split(r"\s+[—-]\s+", plain, maxsplit=1)[0].strip()
        if token:
            out.append(token)
    return out


def _append_to_index(incidents_dir: Path, tracker_id: str, slug: str, title: str, fecha: str) -> None:
    """Crea `INDICE_INCIDENCIAS.md` si falta; append idempotente por marker."""
    index_path = incidents_dir / INDEX_NAME
    marker = f"[[INC-{tracker_id}_{slug}]]"
    existing = index_path.read_text(encoding="utf-8") if index_path.exists() else (
        "# Índice de Incidencias\n\n"
    )
    if marker in existing:
        return
    line = f"- {marker} — {title} — {fecha} — tracker#{tracker_id}\n"
    index_path.write_text(existing + line, encoding="utf-8", newline="")


def write_incident_doc(incident: dict, title: str, html: str, related: dict) -> str | None:
    """Plantilla LITERAL §4.5. SIEMPRE best-effort: cualquier excepción → None
    (la publicación ya hecha en el tracker nunca se revierte por esto)."""
    try:
        docs_root = resolve_docs_root()
        incidents_dir = docs_root / INCIDENTS_DOC_DIRNAME
        incidents_dir.mkdir(parents=True, exist_ok=True)

        tracker_id = str(incident.get("tracker_id") or "")
        slug = _slugify(title)
        doc_path = incidents_dir / f"INC-{tracker_id}_{slug}.md"

        probable_files = _extract_probable_files(html)
        epic_id = incident.get("epic_id")
        fecha = (incident.get("created_at") or "")[:10]
        confidence = (related or {}).get("confidence")
        confidence_txt = f" (confianza {confidence}%)" if confidence is not None else ""
        epic_line = (
            f"Épica relacionada: {epic_id}{confidence_txt}"
            if epic_id is not None else "Sin épica relacionada"
        )
        tracker_url = incident.get("tracker_url") or ""
        execution_id = incident.get("execution_id")

        lines = [
            "---",
            "tipo: incidencia",
            f"incident_id: {incident.get('id', '')}",
        ]
        if execution_id is not None:
            lines.append(f"execution_id: {execution_id}")
        lines += [
            f"tracker_id: {tracker_id}",
            f"work_item_type: {incident.get('work_item_type') or 'Issue'}",
            f"epica: {epic_id if epic_id is not None else ''}",
            f"estado: {incident.get('status', '')}",
            f"fecha: {fecha}",
            "origen: stacky-incident-resolver",
            "---",
            "",
            f"# INC-{tracker_id} — {title}",
            "",
            f"> Issue: {tracker_url} · {epic_line}",
            "",
            html.strip(),
            "",
            "## Relacionados",
            "",
            "- [[INDICE_INCIDENCIAS]]",
        ]
        if probable_files:
            lines.append("- Archivos probables (aristas a código):")
            lines.extend(probable_files)

        doc_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")

        _append_to_index(incidents_dir, tracker_id, slug, title, fecha)

        from services.doc_graph import invalidate_graph_cache
        invalidate_graph_cache()

        return str(doc_path.resolve())
    except Exception:  # noqa: BLE001 — best-effort, nunca revierte la publicación
        return None
