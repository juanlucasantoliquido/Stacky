"""doc_graph.py — Grafo documental READ-ONLY (Plan 109).

Parsea aristas entre notas markdown y hacia archivos de código, sobre las
fuentes que doc_indexer ya resuelve. NO escribe nada. NO usa LLM. NO hace
retrieval (los 3 motores TF-IDF existentes no se tocan ni se duplican).
"""
from __future__ import annotations

import os
import posixpath
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from services import doc_indexer

# (a) Links markdown a .md: [texto](ruta.md) o [texto](ruta.md#ancla)
#     Se ignoran destinos http(s):// y mailto:.
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s#]+\.md)(?:#[^)]*)?\)", re.IGNORECASE)

# (b) Wikilinks: [[nombre]] o [[nombre|alias]] (nombre sin | ni ]] ; alias libre)
_WIKILINK_RE = re.compile(r"\[\[([^\]\|\n]+?)(?:\|[^\]\n]*)?\]\]")

# (C1) Bloques de código fenced: ``` ... ``` (o ~~~). Se ELIMINAN antes de
#      parsear links md y wikilinks (ejemplos de código no son aristas).
#      parse_code_refs NO los elimina: las refs a código legítimas suelen
#      escribirse en backticks (inline o fenced) y son justamente lo que se busca.
_FENCED_BLOCK_RE = re.compile(r"^(```|~~~).*?^\1\s*$", re.MULTILINE | re.DOTALL)


def _strip_fenced_blocks(text: str) -> str:
    """Reemplaza cada bloque fenced por '\n' (preserva el resto del texto).
    Fence sin cerrar: se elimina desde el fence hasta el final del texto."""
    stripped = _FENCED_BLOCK_RE.sub("\n", text or "")
    # fence abierto sin cierre → cortar desde ahí
    open_fence = re.search(r"^(```|~~~)", stripped, re.MULTILINE)
    if open_fence:
        stripped = stripped[: open_fence.start()]
    return stripped


# (c) Referencias a código: rutas con al menos un '/' y extensión de código,
#     opcionalmente con ':NNN' de línea; o 'archivo.ext:NNN' sin directorio.
_CODE_EXTS = r"(?:py|ts|tsx|js|jsx|cs|sql|ps1|sh|bat|ya?ml|json|toml|css|html)"
_CODE_PATH_RE = re.compile(
    r"(?<![\w/\\])((?:[\w.\-]+[/\\])+[\w.\-]+\." + _CODE_EXTS + r")(?::\d+)?\b"
)
_CODE_FILELINE_RE = re.compile(
    r"(?<![\w/\\])([\w.\-]+\." + _CODE_EXTS + r"):\d+\b"
)


def parse_markdown_links(text: str) -> list[str]:
    """Destinos .md de links estándar, en orden de aparición, sin duplicados.
    Excluye http(s)://, mailto: y rutas absolutas (C:\\..., /...). Devuelve la
    ruta tal como está escrita, con backslashes normalizados a '/'.
    Ignora links dentro de bloques fenced (C1). Limitación documentada (C8):
    destinos con espacios o %20 NO matchean (regex excluye whitespace)."""
    out: list[str] = []
    for m in _MD_LINK_RE.finditer(_strip_fenced_blocks(text)):
        target = m.group(1).replace("\\", "/").strip()
        low = target.lower()
        if low.startswith(("http://", "https://", "mailto:")):
            continue
        if low.startswith("/") or re.match(r"^[a-z]:", low):
            continue  # absolutas: fuera (anti-traversal; solo relativas)
        if target and target not in out:
            out.append(target)
    return out


def parse_wikilinks(text: str) -> list[str]:
    """Nombres de wikilinks (sin alias), trimmed, sin duplicados, orden de aparición.
    '[[Nota Motor|el motor]]' -> 'Nota Motor'. Ignora vacíos ('[[]]').
    Ignora wikilinks dentro de bloques fenced (C1)."""
    out: list[str] = []
    for m in _WIKILINK_RE.finditer(_strip_fenced_blocks(text)):
        name = m.group(1).strip()
        if name and name not in out:
            out.append(name)
    return out


def parse_code_refs(text: str) -> list[str]:
    """Rutas de código referidas en el texto, normalizadas ('\\'->'/', sin ':NNN',
    sin './' inicial), sin duplicados, orden de aparición. Matchea:
      - 'backend/services/foo.py' y 'backend\\services\\foo.py:123'
      - 'foo.py:123' (archivo con línea, sin directorio)
    NO matchea 'foo.py' pelado sin '/' ni ':NNN' (demasiado ruido)."""
    out: list[str] = []
    for regex in (_CODE_PATH_RE, _CODE_FILELINE_RE):
        for m in regex.finditer(text or ""):
            ref = m.group(1).replace("\\", "/")
            ref = re.sub(r"^\./", "", ref)
            if ref and ref not in out:
                out.append(ref)
    return out


# ── F2 — build_graph: nodos, aristas, backlinks, huérfanas + cache por mtime ──

_MAX_NOTES = 2000            # límite duro de notas a procesar
_MAX_FILE_BYTES = 2_000_000  # archivos más grandes se saltean (node igual, sin out-edges)
_GRAPH_TTL_SECONDS = 60      # re-chequeo de mtimes como mucho 1 vez por minuto
_MAX_CACHE_ENTRIES = 8       # (C6) tope de payloads cacheados; al superarlo se
                             # elimina la entrada con built_at más viejo

# cache: key -> (built_at_monotonic, fingerprint, payload)
# fingerprint = (n_files, max_mtime_ns, total_size) sobre la lista de archivos
# escaneados. (C3) Si os.stat lanza OSError para un abs_path, ese archivo igual
# cuenta en n_files y aporta mtime_ns=0 y size=0 a max/sum.
_graph_cache: dict[tuple, tuple[float, tuple, dict]] = {}


def invalidate_graph_cache() -> None:
    """Para tests y para forzar re-scan."""
    _graph_cache.clear()


def _read_text(path: Path) -> str:
    """Lectura de una nota. Punto único de I/O (los tests lo cuentan/patchean)."""
    return Path(path).read_text(encoding="utf-8", errors="replace")


def _iter_file_nodes(roots):
    """Recorre recursivamente roots/children juntando nodos kind=='file'."""
    for node in roots or []:
        if not isinstance(node, dict):
            continue
        if node.get("kind") == "file":
            yield node
        children = node.get("children")
        if children:
            yield from _iter_file_nodes(children)


def _code_exists(ref: str, workspace_root: str | None) -> bool:
    try:
        if workspace_root and (Path(workspace_root) / ref).is_file():
            return True
        if (doc_indexer.STACKY_AGENTS_ROOT / ref).is_file():
            return True
    except OSError:
        return False
    return False


def _enumerate_note_files(project_name, vscode_prompts_dir, sources):
    """Devuelve lista determinística de (source_id, rel_path_posix, abs_path: Path)."""
    note_files: list[tuple[str, str, Path]] = []
    for src in sources:
        sid = src.get("id")
        kind = src.get("kind")
        if kind == "stacky":
            try:
                index = doc_indexer.build_index(vscode_prompts_dir)
            except Exception:
                index = {"roots": []}
            for node in _iter_file_nodes(index.get("roots", [])):
                rel = (node.get("path") or "").replace("\\", "/")
                abs_path = node.get("_absolute_path")
                abs_path = Path(abs_path) if abs_path else (doc_indexer.STACKY_AGENTS_ROOT / rel)
                note_files.append((sid, rel, abs_path))
        elif kind == "project-docs":
            try:
                idx = doc_indexer.build_project_docs_index(project_name, source_id=sid)
            except Exception:
                idx = {"roots": []}
            base = Path(src.get("absolute_path") or ".")
            for node in _iter_file_nodes(idx.get("roots", [])):
                rel = (node.get("path") or "").replace("\\", "/")
                note_files.append((sid, rel, base / rel))
        if len(note_files) >= _MAX_NOTES:
            break
    return note_files[:_MAX_NOTES]


def build_graph(project_name: str | None = None,
                vscode_prompts_dir: str | None = None) -> dict:
    """Construye el grafo documental read-only (contrato §4.1 del plan 109).

    Determinístico salvo `generated_at` (timestamp). Cache en memoria con TTL +
    fingerprint por mtime/size para no re-parsear sin cambios.
    """
    sources_info = doc_indexer.list_doc_sources(project_name)
    active_project = sources_info.get("active_project")
    workspace_root = sources_info.get("workspace_root")
    sources = sources_info.get("sources", []) or []
    source_ids = [s.get("id") for s in sources]

    cache_key = ("graph", active_project or "", tuple(sorted(source_ids)),
                 vscode_prompts_dir or "")
    now = time.monotonic()

    cached = _graph_cache.get(cache_key)
    # Dentro del TTL: devolver cache SIN computar fingerprint (ni leer).
    if cached is not None and (now - cached[0]) < _GRAPH_TTL_SECONDS:
        return cached[2]

    # TTL vencido (o sin cache): enumerar + fingerprint.
    note_files = _enumerate_note_files(project_name, vscode_prompts_dir, sources)
    n_files = len(note_files)
    max_mtime_ns = 0
    total_size = 0
    size_by_path: dict[Path, int] = {}
    for (_sid, _rel, abs_path) in note_files:
        try:
            st = os.stat(abs_path)
            max_mtime_ns = max(max_mtime_ns, st.st_mtime_ns)
            total_size += st.st_size
            size_by_path[abs_path] = st.st_size
        except OSError:
            size_by_path[abs_path] = 0
    fingerprint = (n_files, max_mtime_ns, total_size)

    if cached is not None and cached[1] == fingerprint:
        # sin cambios: refrescar built_at y servir cache (sin re-parsear).
        _graph_cache[cache_key] = (now, fingerprint, cached[2])
        return cached[2]

    payload = _build_payload(note_files, size_by_path, sources, active_project,
                             workspace_root)

    _graph_cache[cache_key] = (now, fingerprint, payload)
    if len(_graph_cache) > _MAX_CACHE_ENTRIES:
        oldest = min(_graph_cache.items(), key=lambda kv: kv[1][0])[0]
        del _graph_cache[oldest]
    return payload


def _serialize_node(node: dict) -> dict:
    return {
        "id": node["id"], "kind": node["kind"], "label": node["label"],
        "path": node["path"], "source_id": node["source_id"],
        "in_degree": node["in_degree"], "out_degree": node["out_degree"],
        "has_frontmatter": node["has_frontmatter"], "exists": node["exists"],
    }


def _build_payload(note_files, size_by_path, sources, active_project,
                   workspace_root) -> dict:
    notes: dict[str, dict] = {}
    notes_by_source: dict[str, dict[str, str]] = {}
    name_index: dict[str, tuple[str, str, str]] = {}  # base -> (rel, sid, node_id)

    # Paso 1 — crear nodos de notas + índice de nombres (para wikilinks).
    for (sid, rel, abs_path) in note_files:
        node_id = f"note:{sid}:{rel}"
        if node_id in notes:
            continue
        notes[node_id] = {
            "id": node_id, "kind": "note", "label": posixpath.basename(rel) or rel,
            "path": rel, "source_id": sid, "in_degree": 0, "out_degree": 0,
            "has_frontmatter": False, "exists": True,
            "_abs": abs_path, "_size": size_by_path.get(abs_path, 0),
        }
        notes_by_source.setdefault(sid, {})[rel] = node_id
        base = posixpath.splitext(posixpath.basename(rel))[0].lower()
        cand = (rel, sid, node_id)
        existing = name_index.get(base)
        if existing is None or (rel, sid) < (existing[0], existing[1]):
            name_index[base] = cand

    extra_nodes: dict[str, dict] = {}
    edges_set: set[tuple[str, str, str]] = set()

    def ensure_missing(name_lower: str) -> str:
        nid = f"missing:{name_lower}"
        if nid not in extra_nodes:
            extra_nodes[nid] = {
                "id": nid, "kind": "missing", "label": name_lower,
                "path": name_lower, "source_id": "", "in_degree": 0,
                "out_degree": 0, "has_frontmatter": False, "exists": False,
            }
        return nid

    def ensure_code(ref: str) -> str:
        nid = f"code:{ref}"
        if nid not in extra_nodes:
            extra_nodes[nid] = {
                "id": nid, "kind": "code", "label": posixpath.basename(ref) or ref,
                "path": ref, "source_id": "", "in_degree": 0, "out_degree": 0,
                "has_frontmatter": False,
                "exists": _code_exists(ref, workspace_root),
            }
        return nid

    # Paso 2 — leer y parsear cada nota, resolver aristas.
    for node_id, node in notes.items():
        abs_path = node["_abs"]
        size = node["_size"]
        content = ""
        if size <= _MAX_FILE_BYTES:
            try:
                content = _read_text(abs_path)
            except OSError:
                content = ""
        node["has_frontmatter"] = bool(content) and content.lstrip().startswith("---")
        sid = node["source_id"]
        rel = node["path"]

        for target in parse_markdown_links(content):
            resolved = posixpath.normpath(
                posixpath.join(posixpath.dirname(rel), target))
            if resolved.startswith(".."):
                continue  # escape de la fuente
            tgt = notes_by_source.get(sid, {}).get(resolved)
            if tgt is None:
                tgt = ensure_missing(
                    posixpath.splitext(posixpath.basename(resolved))[0].lower())
            edges_set.add((node_id, tgt, "md"))

        for name in parse_wikilinks(content):
            base = posixpath.splitext(name)[0].lower()
            entry = name_index.get(base)
            tgt = entry[2] if entry else ensure_missing(base)
            edges_set.add((node_id, tgt, "wikilink"))

        for ref in parse_code_refs(content):
            edges_set.add((node_id, ensure_code(ref), "code_ref"))

    # Paso 3 — grados y huérfanas.
    all_nodes = {**notes, **extra_nodes}
    for (s, t, _k) in edges_set:
        if s in all_nodes:
            all_nodes[s]["out_degree"] += 1
        if t in all_nodes:
            all_nodes[t]["in_degree"] += 1

    orphans = sorted(
        nid for nid, n in notes.items()
        if n["in_degree"] == 0 and n["out_degree"] == 0)

    nodes_out = [_serialize_node(all_nodes[nid]) for nid in sorted(all_nodes)]
    edges_out = [{"source": s, "target": t, "kind": k}
                 for (s, t, k) in sorted(edges_set)]

    code_count = sum(1 for n in extra_nodes.values() if n["kind"] == "code")
    missing_count = sum(1 for n in extra_nodes.values() if n["kind"] == "missing")
    edges_md = sum(1 for e in edges_set if e[2] == "md")
    edges_wiki = sum(1 for e in edges_set if e[2] == "wikilink")
    edges_code = sum(1 for e in edges_set if e[2] == "code_ref")

    source_meta = [
        {"id": s.get("id"), "kind": s.get("kind"), "label": s.get("label"),
         "relative_path": s.get("relative_path"),
         "absolute_path": s.get("absolute_path")}
        for s in sources
    ]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "active_project": active_project,
        "sources": source_meta,
        "nodes": nodes_out,
        "edges": edges_out,
        "orphans": orphans,
        "stats": {
            "notes": len(notes), "code_refs": code_count, "missing": missing_count,
            "edges_md": edges_md, "edges_wikilink": edges_wiki,
            "edges_code_ref": edges_code, "orphans": len(orphans),
            "sources": len(source_meta),
        },
        "doc_health": classify_doc_health(nodes_out, edges_out, workspace_root),
    }


# ── F3 — Clasificador determinístico de salud documental ─────────────────────

_CODE_MODULE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".cs", ".sql"}
_MAX_MODULE_SCAN_ENTRIES = 500  # tope de entradas listadas por módulo (performance)


def _module_has_code(module_dir: Path) -> bool:
    """True si el módulo contiene >=1 archivo de código (scan cortado)."""
    seen = 0
    try:
        for dirpath, dirnames, filenames in os.walk(module_dir):
            dirnames[:] = [d for d in dirnames
                           if d not in doc_indexer._EXCLUDE_DIRS and not d.startswith(".")]
            for fn in filenames:
                if os.path.splitext(fn)[1].lower() in _CODE_MODULE_EXTS:
                    return True
                seen += 1
                if seen >= _MAX_MODULE_SCAN_ENTRIES:
                    return False
    except OSError:
        return False
    return False


def _uncovered_modules(edges: list[dict], workspace_root: str | None) -> list[str]:
    """Módulos de código de primer nivel sin ninguna arista code_ref que los cubra."""
    if not workspace_root:
        return []
    root = Path(workspace_root)
    try:
        if not root.is_dir():
            return []
        entries = sorted(p for p in root.iterdir() if p.is_dir())
    except OSError:
        return []
    covered: set[str] = set()
    for e in edges:
        if e.get("kind") == "code_ref":
            tgt = e.get("target", "") or ""
            path = tgt[len("code:"):] if tgt.startswith("code:") else tgt
            top = path.split("/", 1)[0]
            if top:
                covered.add(top)
    uncovered: list[str] = []
    for d in entries:
        name = d.name
        if name.startswith(".") or name in doc_indexer._EXCLUDE_DIRS:
            continue
        if not _module_has_code(d):
            continue
        if name not in covered:
            uncovered.append(name)
    return sorted(uncovered)


def classify_doc_health(nodes: list[dict], edges: list[dict],
                        workspace_root: str | None) -> dict:
    """Determinístico, sin LLM, NUNCA lanza. Solo considera notas de fuentes de
    PROYECTO (source_id startswith 'project-docs:'): la doc interna de Stacky no
    cuenta para la salud del proyecto del cliente."""
    try:
        project_notes = [
            n for n in nodes
            if n.get("kind") == "note"
            and str(n.get("source_id", "")).startswith(doc_indexer.PROJECT_DOC_SOURCE_PREFIX)
        ]
        wikilink_edges = sum(1 for e in edges if e.get("kind") == "wikilink")
        n_notes = len(project_notes)
        fm = sum(1 for n in project_notes if n.get("has_frontmatter"))
        frontmatter_ratio = (fm / n_notes) if n_notes else 0.0

        # Regla 1 — SIN_DOCS: cero notas de proyecto.
        if n_notes == 0:
            return {"status": "SIN_DOCS",
                    "reasons": ["El proyecto activo no tiene ninguna nota .md en sus fuentes de docs."],
                    "frontmatter_ratio": 0.0, "wikilink_edges": wikilink_edges,
                    "uncovered_modules": []}

        # Regla 2 — FORMATO_NO_OBSIDIAN: hay notas pero 0% frontmatter Y 0 wikilinks.
        if fm == 0 and wikilink_edges == 0:
            return {"status": "FORMATO_NO_OBSIDIAN",
                    "reasons": [f"{n_notes} notas sin frontmatter y sin ningún wikilink [[...]]."],
                    "frontmatter_ratio": 0.0, "wikilink_edges": 0,
                    "uncovered_modules": []}

        # Regla 3 — INCOMPLETA: módulos de código de primer nivel sin referencia.
        uncovered = _uncovered_modules(edges, workspace_root)
        if uncovered:
            return {"status": "INCOMPLETA",
                    "reasons": [f"{len(uncovered)} módulos de código de primer nivel sin ninguna "
                                f"nota que los referencie: {', '.join(uncovered)}"],
                    "frontmatter_ratio": round(frontmatter_ratio, 2),
                    "wikilink_edges": wikilink_edges,
                    "uncovered_modules": uncovered}

        # Regla 4 — SANA.
        return {"status": "SANA", "reasons": [],
                "frontmatter_ratio": round(frontmatter_ratio, 2),
                "wikilink_edges": wikilink_edges, "uncovered_modules": []}
    except Exception:
        # NUNCA lanza: ante basura, devolver un dict válido conservador.
        return {"status": "SANA", "reasons": [], "frontmatter_ratio": 0.0,
                "wikilink_edges": 0, "uncovered_modules": []}

