"""
doc_indexer.py — Indexador de documentación para DocTree (Feature #3)
=====================================================================

Escanea tres raíces whitelistadas dentro de Stacky Agents y devuelve un árbol
de documentos con headings H1/H2 extraídos de los primeros 4KB de cada archivo.

Raíces:
    1. STACKY_AGENTS_ROOT/docs/          → "Documentación Técnica"
    2. STACKY_AGENTS_ROOT/*.md (raíz)    → "Roadmaps y Notas"
    3. config.VSCODE_PROMPTS_DIR/*.agent.md → "Agentes (.agent.md)"

Seguridad:
    - read_content() resuelve el path real y verifica que esté dentro de
      una raíz permitida antes de leer. Path traversal → ValueError.
    - Excludes hardcodeados: node_modules/, .venv/, __pycache__/, *.db, .git/, data/

Cache:
    - TTL de 5 minutos en variable de módulo (_cache).
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

# ── Rutas ──────────────────────────────────────────────────────────────────────

# backend/ → Stacky Agents/
STACKY_AGENTS_ROOT: Path = Path(__file__).resolve().parents[1]

# ── Excludes ──────────────────────────────────────────────────────────────────

_EXCLUDE_DIRS: set[str] = {
    "node_modules",
    ".venv",
    "__pycache__",
    ".git",
    "data",
}

_EXCLUDE_EXTENSIONS: set[str] = {".db"}

# ── Cache en memoria ──────────────────────────────────────────────────────────

_CACHE_TTL_SECONDS = 300  # 5 minutos
_cache: tuple[float, dict] | None = None  # (timestamp, index_dict)


# ── Helpers internos ──────────────────────────────────────────────────────────

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


def _make_node(file_path: Path, rel_path: str) -> dict[str, Any]:
    """Construye un nodo de documento."""
    try:
        size = file_path.stat().st_size
    except OSError:
        size = 0
    return {
        "id": f"doc:{rel_path}",
        "label": file_path.name,
        "path": rel_path,
        "size_bytes": size,
        "headings": _extract_headings(file_path),
    }


# ── Construcción del índice ───────────────────────────────────────────────────

def _index_technical_docs() -> list[dict[str, Any]]:
    """Indexa STACKY_AGENTS_ROOT/docs/ de forma recursiva."""
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
    note es None si indexó correctamente, o un string explicativo si no.
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
        # Para agentes, la ruta relativa usa el nombre del archivo directamente
        # ya que el directorio de prompts es externo a STACKY_AGENTS_ROOT
        rel = f"agents/{file_path.name}"
        node = _make_node(file_path, rel)
        # Guardamos la ruta absoluta real para poder leerla luego
        node["_absolute_path"] = str(file_path)
        nodes.append(node)
    return nodes, None


# ── API pública ───────────────────────────────────────────────────────────────

def build_index(vscode_prompts_dir: str | None = None) -> dict[str, Any]:
    """
    Construye (o retorna desde cache) el índice completo de documentación.

    Args:
        vscode_prompts_dir: Ruta al directorio de prompts de VS Code.
                            Si None, la sección Agentes queda vacía con nota.

    Returns:
        {
            "indexed_at": "<iso>",
            "roots": [
                {"id": "technical-docs", "label": "...", "children": [...]},
                {"id": "agents", "label": "...", "children": [...], "note": null | "..."},
                {"id": "roadmaps", "label": "...", "children": [...]},
            ]
        }
    """
    global _cache

    now = time.monotonic()
    if _cache is not None:
        cached_at, cached_index = _cache
        if now - cached_at < _CACHE_TTL_SECONDS:
            return cached_index

    tech_docs = _index_technical_docs()
    roadmaps = _index_roadmaps()
    agents, agents_note = _index_agents(vscode_prompts_dir)

    from datetime import datetime, timezone
    indexed_at = datetime.now(timezone.utc).isoformat()

    agents_root: dict[str, Any] = {
        "id": "agents",
        "label": "Agentes (.agent.md)",
        "children": agents,
    }
    if agents_note:
        agents_root["note"] = agents_note

    index = {
        "indexed_at": indexed_at,
        "roots": [
            {
                "id": "technical-docs",
                "label": "Documentación Técnica",
                "children": tech_docs,
            },
            agents_root,
            {
                "id": "roadmaps",
                "label": "Roadmaps y Notas",
                "children": roadmaps,
            },
        ],
    }

    _cache = (now, index)
    return index


def invalidate_cache() -> None:
    """Invalida el cache de índice (útil para tests y forzar re-scan)."""
    global _cache
    _cache = None


def _resolve_allowed_roots(vscode_prompts_dir: str | None) -> list[Path]:
    """
    Devuelve la lista de directorios raíz permitidos para lectura de contenido.
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
    Lee el contenido de un documento validando que esté dentro de las raíces
    whitelistadas (anti path traversal).

    Args:
        path: Ruta relativa tal como la devuelve el índice (ej: "docs/00_VISION.md"
              o "agents/DevPacifico.agent.md").
        vscode_prompts_dir: Directorio de prompts de VS Code (para agentes).

    Returns:
        Contenido del archivo como string UTF-8.

    Raises:
        ValueError: Si el path intenta salir de las raíces permitidas.
        FileNotFoundError: Si el archivo no existe.
    """
    if not path or ".." in path.replace("\\", "/"):
        raise ValueError(f"path_traversal_blocked: {path!r}")

    allowed_roots = _resolve_allowed_roots(vscode_prompts_dir)

    # Caso especial para agentes: el path tiene prefijo "agents/"
    if path.startswith("agents/"):
        agent_filename = path[len("agents/"):]
        if vscode_prompts_dir:
            candidate = (Path(vscode_prompts_dir) / agent_filename).resolve()
            if not any(
                str(candidate).startswith(str(root)) for root in allowed_roots
            ):
                raise ValueError(f"path_traversal_blocked: {path!r}")
            if not candidate.is_file():
                raise FileNotFoundError(f"not_found: {path!r}")
            return candidate.read_text(encoding="utf-8")
        raise FileNotFoundError(f"not_found: {path!r}")

    # Para docs/ y roadmaps: resolver relativo a STACKY_AGENTS_ROOT
    candidate = (STACKY_AGENTS_ROOT / path).resolve()

    # Verificar que el path resuelto esté dentro de al menos una raíz permitida
    candidate_str = str(candidate)
    allowed = any(
        candidate_str.startswith(str(root))
        for root in allowed_roots
    )
    if not allowed:
        raise ValueError(f"path_traversal_blocked: {path!r}")

    if not candidate.is_file():
        raise FileNotFoundError(f"not_found: {path!r}")

    return candidate.read_text(encoding="utf-8")
