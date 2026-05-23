"""
doc_indexer.py - Indexador de documentacion para DocTree (Feature #3)
=====================================================================

Escanea documentacion markdown y devuelve un arbol navegable para el frontend.

Fuentes soportadas:
    1. Documentacion propia de Stacky Agents:
       - STACKY_AGENTS_ROOT/docs/
       - STACKY_AGENTS_ROOT/*.md
       - config.VSCODE_PROMPTS_DIR/*.agent.md
    2. Carpetas docs del proyecto activo:
       - workspace_root/docs
       - carpetas llamadas docs descubiertas cerca de workspace_root

Seguridad:
    - read_content() y read_project_doc_content() resuelven paths reales y
      verifican que el archivo permanezca dentro de una raiz permitida.
    - Path traversal, rutas absolutas y escapes de workspace se bloquean.
    - Excludes hardcodeados: node_modules/, .venv/, __pycache__/, *.db, .git/, data/

Cache:
    - TTL de 5 minutos por clave de fuente.
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# -- Rutas ---------------------------------------------------------------------

# backend/services/ -> Stacky Agents/
STACKY_AGENTS_ROOT: Path = Path(__file__).resolve().parents[2]

STACKY_SOURCE_ID = "stacky"
PROJECT_DOC_SOURCE_PREFIX = "project-docs:"

# -- Excludes ------------------------------------------------------------------

_EXCLUDE_DIRS: set[str] = {
    "node_modules",
    ".venv",
    "__pycache__",
    ".git",
    "data",
    "dist",
    "build",
}

_EXCLUDE_EXTENSIONS: set[str] = {".db"}

_PROJECT_DOC_DISCOVERY_MAX_DEPTH = 4
_PROJECT_DOC_DISCOVERY_MAX_SOURCES = 50

# -- Cache en memoria ----------------------------------------------------------

_CACHE_TTL_SECONDS = 300  # 5 minutos
_cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}


# -- Helpers internos ----------------------------------------------------------

def _anchor(text: str) -> str:
    """Convierte texto de heading a anchor GitHub-style."""
    return re.sub(r"[^a-z0-9\-]", "", text.lower().replace(" ", "-"))


def _extract_headings(path: Path) -> list[dict[str, Any]]:
    """Lee los primeros 4KB del archivo y extrae headings H1/H2."""
    try:
        raw = path.read_bytes()[:4096].decode("utf-8", errors="replace")
    except OSError:
        return []

    headings: list[dict[str, Any]] = []
    for line in raw.splitlines():
        m = re.match(r"^(#{1,2})\s+(.+)$", line.strip())
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            headings.append({"level": level, "text": text, "anchor": _anchor(text)})
    return headings


def _should_exclude(path: Path) -> bool:
    """Devuelve True si el path debe ser ignorado."""
    for part in path.parts:
        if part in _EXCLUDE_DIRS:
            return True
    if path.suffix in _EXCLUDE_EXTENSIONS:
        return True
    return False


def _is_relative_to(candidate: Path, root: Path) -> bool:
    """Compatibilidad clara para verificar contencion de paths."""
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _normalize_relative_path(path: str) -> str:
    """Normaliza una ruta relativa y bloquea intentos de traversal."""
    normalized = path.replace("\\", "/").strip()
    if (
        not normalized
        or normalized.startswith("/")
        or re.match(r"^[A-Za-z]:", normalized)
        or any(part in ("", "..") for part in normalized.split("/"))
    ):
        raise ValueError(f"path_traversal_blocked: {path!r}")
    return normalized


def _cache_get(key: tuple[Any, ...]) -> dict[str, Any] | None:
    now = time.monotonic()
    cached = _cache.get(key)
    if not cached:
        return None
    cached_at, cached_index = cached
    if now - cached_at < _CACHE_TTL_SECONDS:
        return cached_index
    _cache.pop(key, None)
    return None


def _cache_set(key: tuple[Any, ...], value: dict[str, Any]) -> dict[str, Any]:
    _cache[key] = (time.monotonic(), value)
    return value


def _make_node(
    file_path: Path,
    rel_path: str,
    *,
    source_id: str = STACKY_SOURCE_ID,
    display_path: str | None = None,
) -> dict[str, Any]:
    """Construye un nodo de documento."""
    try:
        size = file_path.stat().st_size
    except OSError:
        size = 0
    return {
        "id": f"doc:{source_id}:{rel_path}" if source_id != STACKY_SOURCE_ID else f"doc:{rel_path}",
        "kind": "file",
        "label": file_path.name,
        "path": rel_path,
        "display_path": display_path or rel_path,
        "source_id": source_id,
        "size_bytes": size,
        "headings": _extract_headings(file_path),
        "children": [],
    }


def _make_folder_node(label: str, rel_path: str, source_id: str, display_path: str) -> dict[str, Any]:
    """Construye un nodo carpeta para arboles recursivos."""
    return {
        "id": f"folder:{source_id}:{rel_path}",
        "kind": "folder",
        "label": label,
        "path": rel_path,
        "display_path": display_path,
        "source_id": source_id,
        "size_bytes": 0,
        "headings": [],
        "children": [],
    }


def _sort_tree(nodes: list[dict[str, Any]]) -> None:
    """Ordena carpetas primero y luego archivos alfabeticamente."""
    nodes.sort(key=lambda n: (0 if n.get("kind") == "folder" else 1, str(n.get("label", "")).lower()))
    for node in nodes:
        _sort_tree(node.get("children") or [])


def _insert_file_node(
    root_children: list[dict[str, Any]],
    rel_path: str,
    file_node: dict[str, Any],
    *,
    source_id: str,
    display_prefix: str,
) -> None:
    """Inserta un archivo dentro de un arbol de carpetas segun su ruta relativa."""
    parts = rel_path.split("/")
    current_children = root_children
    folder_parts: list[str] = []

    for folder_name in parts[:-1]:
        folder_parts.append(folder_name)
        folder_rel = "/".join(folder_parts)
        existing = next(
            (
                node
                for node in current_children
                if node.get("kind") == "folder" and node.get("path") == folder_rel
            ),
            None,
        )
        if existing is None:
            display_path = f"{display_prefix}/{folder_rel}" if display_prefix else folder_rel
            existing = _make_folder_node(folder_name, folder_rel, source_id, display_path)
            current_children.append(existing)
        current_children = existing["children"]

    current_children.append(file_node)


def _index_markdown_tree(root_dir: Path, *, source_id: str, display_prefix: str = "") -> list[dict[str, Any]]:
    """Indexa una raiz markdown como arbol de carpetas y archivos."""
    root = root_dir.resolve()
    if not root.is_dir():
        return []

    children: list[dict[str, Any]] = []
    for file_path in sorted(root.rglob("*.md")):
        if _should_exclude(file_path):
            continue
        resolved_file = file_path.resolve()
        if not _is_relative_to(resolved_file, root):
            continue
        rel = resolved_file.relative_to(root).as_posix()
        display_path = f"{display_prefix}/{rel}" if display_prefix else rel
        node = _make_node(
            resolved_file,
            rel,
            source_id=source_id,
            display_path=display_path,
        )
        _insert_file_node(
            children,
            rel,
            node,
            source_id=source_id,
            display_prefix=display_prefix,
        )

    _sort_tree(children)
    return children


def _count_files(nodes: list[dict[str, Any]]) -> int:
    total = 0
    for node in nodes:
        if node.get("kind") == "folder":
            total += _count_files(node.get("children") or [])
        else:
            total += 1
    return total


# -- Construccion del indice Stacky -------------------------------------------

def _index_technical_docs() -> list[dict[str, Any]]:
    """Indexa STACKY_AGENTS_ROOT/docs/ de forma recursiva y plana."""
    docs_dir = STACKY_AGENTS_ROOT / "docs"
    if not docs_dir.is_dir():
        return []

    nodes: list[dict[str, Any]] = []
    for file_path in sorted(docs_dir.rglob("*.md")):
        if _should_exclude(file_path):
            continue
        rel = file_path.relative_to(STACKY_AGENTS_ROOT).as_posix()
        nodes.append(_make_node(file_path, rel))
    return nodes


def _index_roadmaps() -> list[dict[str, Any]]:
    """Indexa *.md directamente en STACKY_AGENTS_ROOT (no recursivo)."""
    nodes: list[dict[str, Any]] = []
    for file_path in sorted(STACKY_AGENTS_ROOT.glob("*.md")):
        if _should_exclude(file_path):
            continue
        rel = file_path.relative_to(STACKY_AGENTS_ROOT).as_posix()
        nodes.append(_make_node(file_path, rel))
    return nodes


def _index_agents(vscode_prompts_dir: str | None) -> tuple[list[dict[str, Any]], str | None]:
    """
    Indexa *.agent.md desde VSCODE_PROMPTS_DIR.
    Devuelve (nodes, note).
    """
    if not vscode_prompts_dir:
        return [], "VSCODE_PROMPTS_DIR no configurado"

    prompts_dir = Path(vscode_prompts_dir)
    if not prompts_dir.is_dir():
        return [], f"Directorio de prompts no encontrado: {vscode_prompts_dir}"

    nodes: list[dict[str, Any]] = []
    for file_path in sorted(prompts_dir.glob("*.agent.md")):
        if _should_exclude(file_path):
            continue
        rel = f"agents/{file_path.name}"
        node = _make_node(file_path, rel)
        node["_absolute_path"] = str(file_path)
        nodes.append(node)
    return nodes, None


def build_index(vscode_prompts_dir: str | None = None) -> dict[str, Any]:
    """
    Construye (o retorna desde cache) el indice Stacky Agents.
    """
    cache_key = ("stacky", vscode_prompts_dir or "")
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    tech_docs = _index_technical_docs()
    roadmaps = _index_roadmaps()
    agents, agents_note = _index_agents(vscode_prompts_dir)

    agents_root: dict[str, Any] = {
        "id": "agents",
        "label": "Agentes (.agent.md)",
        "source_id": STACKY_SOURCE_ID,
        "children": agents,
    }
    if agents_note:
        agents_root["note"] = agents_note

    index = {
        "indexed_at": datetime.now(timezone.utc).isoformat(),
        "source_id": STACKY_SOURCE_ID,
        "roots": [
            {
                "id": "technical-docs",
                "label": "Documentación Técnica",
                "source_id": STACKY_SOURCE_ID,
                "children": tech_docs,
            },
            agents_root,
            {
                "id": "roadmaps",
                "label": "Roadmaps y Notas",
                "source_id": STACKY_SOURCE_ID,
                "children": roadmaps,
            },
        ],
    }

    return _cache_set(cache_key, index)


# -- Fuentes docs de proyecto --------------------------------------------------

def _project_manager():
    """Import lazy para evitar dependencias circulares durante tests."""
    from project_manager import get_active_project, get_project_config

    return get_active_project, get_project_config


def _workspace_from_project_config(project_cfg: dict[str, Any] | None) -> Path | None:
    if not project_cfg:
        return None
    workspace_root = str(project_cfg.get("workspace_root") or "").strip()
    if not workspace_root:
        return None
    try:
        path = Path(workspace_root).expanduser().resolve()
    except OSError:
        return None
    if not path.is_dir():
        return None
    return path


def _source_id_for_project_docs(relative_path: str) -> str:
    return f"{PROJECT_DOC_SOURCE_PREFIX}{relative_path}"


def _configured_project_doc_sources(project_cfg: dict[str, Any] | None) -> tuple[list[dict[str, Any]], str | None]:
    """Devuelve fuentes explícitas docs_paths si fueron configuradas."""
    if not project_cfg:
        return [], None

    docs_paths = project_cfg.get("docs_paths") or {}
    if not isinstance(docs_paths, dict):
        return [], None

    specs = (
        ("technical", "📐 Técnica"),
        ("functional", "📋 Funcional / Manual"),
    )
    sources: list[dict[str, Any]] = []
    for key, label in specs:
        raw_path = str(docs_paths.get(key) or "").strip()
        if not raw_path:
            continue
        try:
            resolved = Path(raw_path).expanduser().resolve()
        except OSError:
            resolved = Path(raw_path).expanduser().absolute()
        sources.append(
            {
                "id": _source_id_for_project_docs(key),
                "kind": "project-docs",
                "label": label,
                "relative_path": key,
                "display_prefix": label,
                "absolute_path": str(resolved),
                "project": project_cfg.get("name"),
                "workspace_root": project_cfg.get("workspace_root"),
                "configured": True,
                "docs_path_kind": key,
                "available": resolved.is_dir(),
            }
        )

    if not sources:
        return [], None
    return sources, None


def _discover_project_doc_sources(project_cfg: dict[str, Any] | None) -> tuple[list[dict[str, Any]], str | None]:
    """Descubre carpetas llamadas docs dentro del workspace del proyecto."""
    workspace = _workspace_from_project_config(project_cfg)
    if workspace is None:
        return [], "El proyecto activo no tiene workspace_root valido o accesible."

    seen: set[Path] = set()
    sources: list[dict[str, Any]] = []

    def add_source(path: Path) -> None:
        nonlocal sources
        try:
            resolved = path.resolve()
            rel = resolved.relative_to(workspace).as_posix()
        except (OSError, ValueError):
            return
        if resolved in seen or not resolved.is_dir():
            return
        seen.add(resolved)
        sources.append(
            {
                "id": _source_id_for_project_docs(rel),
                "kind": "project-docs",
                "label": rel,
                "relative_path": rel,
                "absolute_path": str(resolved),
                "project": project_cfg.get("name") if project_cfg else None,
                "workspace_root": str(workspace),
            }
        )

    preferred = workspace / "docs"
    if preferred.is_dir():
        add_source(preferred)

    for current, dirs, _files in os.walk(workspace):
        current_path = Path(current)
        try:
            rel_parts = current_path.resolve().relative_to(workspace).parts
        except (OSError, ValueError):
            dirs[:] = []
            continue

        dirs[:] = [
            d
            for d in dirs
            if d not in _EXCLUDE_DIRS and not d.startswith(".")
        ]

        if len(rel_parts) >= _PROJECT_DOC_DISCOVERY_MAX_DEPTH:
            dirs[:] = []
            continue

        if current_path.name.lower() == "docs" and current_path != workspace:
            add_source(current_path)
            dirs[:] = []

        if len(sources) >= _PROJECT_DOC_DISCOVERY_MAX_SOURCES:
            dirs[:] = []
            break

    if not sources:
        return [], f"No se encontro una carpeta docs dentro de {workspace}."
    return sources, None


def list_doc_sources(project_name: str | None = None) -> dict[str, Any]:
    """
    Lista fuentes seleccionables para la pantalla Docs.

    Incluye siempre la documentacion propia de Stacky y, si existe, las carpetas
    docs del workspace del proyecto seleccionado/activo.
    """
    get_active_project, get_project_config = _project_manager()
    active_project = project_name or get_active_project()
    project_cfg = get_project_config(active_project) if active_project else None

    stacky_source = {
        "id": STACKY_SOURCE_ID,
        "kind": "stacky",
        "label": "Stacky Agents",
        "relative_path": ".",
        "absolute_path": str(STACKY_AGENTS_ROOT.resolve()),
        "project": None,
        "workspace_root": str(STACKY_AGENTS_ROOT.resolve()),
    }

    project_sources, note = _configured_project_doc_sources(project_cfg)
    if not project_sources:
        project_sources, note = _discover_project_doc_sources(project_cfg)
    default_source_id = project_sources[0]["id"] if project_sources else STACKY_SOURCE_ID

    return {
        "ok": True,
        "active_project": active_project,
        "project_display_name": (project_cfg or {}).get("display_name") if project_cfg else None,
        "workspace_root": (project_cfg or {}).get("workspace_root") if project_cfg else None,
        "default_source_id": default_source_id,
        "sources": [stacky_source, *project_sources],
        "note": note,
    }


def _resolve_project_doc_source(
    project_name: str | None,
    source_id: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    sources_info = list_doc_sources(project_name)
    selected_source_id = source_id or sources_info["default_source_id"]
    for source in sources_info["sources"]:
        if source["id"] == selected_source_id and source["kind"] == "project-docs":
            return source, sources_info
    raise FileNotFoundError(f"doc_source_not_found: {selected_source_id!r}")


def build_project_docs_index(
    project_name: str | None = None,
    source_id: str | None = None,
) -> dict[str, Any]:
    """Construye un arbol recursivo para una carpeta docs de proyecto."""
    source, sources_info = _resolve_project_doc_source(project_name, source_id)
    selected_source_id = source["id"]
    cache_key = (
        "project-docs",
        sources_info.get("active_project") or "",
        selected_source_id,
        source.get("absolute_path") or "",
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    root_dir = Path(source["absolute_path"]).resolve()
    rel = source["relative_path"]
    display_prefix = source.get("display_prefix") or rel
    children = _index_markdown_tree(
        root_dir,
        source_id=selected_source_id,
        display_prefix=display_prefix,
    )
    file_count = _count_files(children)

    label_project = sources_info.get("project_display_name") or sources_info.get("active_project") or "Proyecto"
    root = {
        "id": "project-docs",
        "label": source.get("label") or f"{label_project} / {rel}",
        "source_id": selected_source_id,
        "path": rel,
        "display_path": display_prefix,
        "children": children,
    }
    if file_count == 0:
        root["note"] = "La carpeta seleccionada no contiene archivos .md."

    index = {
        "indexed_at": datetime.now(timezone.utc).isoformat(),
        "source_id": selected_source_id,
        "active_project": sources_info.get("active_project"),
        "workspace_root": sources_info.get("workspace_root"),
        "roots": [root],
    }
    return _cache_set(cache_key, index)


def read_project_doc_content(
    path: str,
    *,
    project_name: str | None = None,
    source_id: str | None = None,
) -> str:
    """Lee un markdown de una carpeta docs del proyecto seleccionado."""
    rel_path = _normalize_relative_path(path)
    source, _sources_info = _resolve_project_doc_source(project_name, source_id)
    root = Path(source["absolute_path"]).resolve()
    candidate = (root / rel_path).resolve()
    if not _is_relative_to(candidate, root):
        raise ValueError(f"path_traversal_blocked: {path!r}")
    if not candidate.is_file():
        raise FileNotFoundError(f"not_found: {path!r}")
    return candidate.read_text(encoding="utf-8")


# -- API publica legacy --------------------------------------------------------

def invalidate_cache() -> None:
    """Invalida el cache de indice (util para tests y forzar re-scan)."""
    _cache.clear()


def _resolve_allowed_roots(vscode_prompts_dir: str | None) -> list[Path]:
    """
    Devuelve la lista de directorios raiz permitidos para lectura de contenido.
    """
    roots = [
        (STACKY_AGENTS_ROOT / "docs").resolve(),
        STACKY_AGENTS_ROOT.resolve(),
    ]
    if vscode_prompts_dir:
        vp = Path(vscode_prompts_dir)
        if vp.is_dir():
            roots.append(vp.resolve())
    return roots


def read_content(path: str, vscode_prompts_dir: str | None = None) -> str:
    """
    Lee el contenido de un documento Stacky validando roots whitelistadas.
    """
    normalized_path = _normalize_relative_path(path)
    allowed_roots = _resolve_allowed_roots(vscode_prompts_dir)

    if normalized_path.startswith("agents/"):
        agent_filename = normalized_path[len("agents/"):]
        if vscode_prompts_dir:
            candidate = (Path(vscode_prompts_dir) / agent_filename).resolve()
            if not any(_is_relative_to(candidate, root) for root in allowed_roots):
                raise ValueError(f"path_traversal_blocked: {path!r}")
            if not candidate.is_file():
                raise FileNotFoundError(f"not_found: {path!r}")
            return candidate.read_text(encoding="utf-8")
        raise FileNotFoundError(f"not_found: {path!r}")

    candidate = (STACKY_AGENTS_ROOT / normalized_path).resolve()
    if not any(_is_relative_to(candidate, root) for root in allowed_roots):
        raise ValueError(f"path_traversal_blocked: {path!r}")

    if not candidate.is_file():
        raise FileNotFoundError(f"not_found: {path!r}")

    return candidate.read_text(encoding="utf-8")
