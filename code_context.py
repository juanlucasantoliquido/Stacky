"""
code_context.py — Auto-detección de archivos relevantes para un ticket.

Analiza el INC-{id}.md y los archivos PM del ticket para extraer keywords técnicos
(nombres de clases, métodos, tablas Oracle, formularios), busca esos keywords en el
codebase y retorna las rutas de archivos más relevantes.

Se inyecta en los prompts de PM y Dev para que los agentes lleguen con referencias
directas al código afectado — sin tener que buscarlo de cero.

Uso:
    from code_context import build_code_context_section
    context = build_code_context_section(ticket_folder, workspace_root)
    # → string Markdown con tabla de archivos relevantes + snippets
"""

import os
import re
from pathlib import Path

# ── Extensiones de código a indexar ──────────────────────────────────────────
_CODE_EXTENSIONS = {".cs", ".sql", ".js", ".aspx", ".config"}
_TEXT_EXTENSIONS = {".cs", ".sql", ".js", ".aspx", ".config", ".md", ".json"}

# ── Directorios a ignorar siempre ─────────────────────────────────────────────
_IGNORE_DIRS = {
    "bin", "obj", "node_modules", ".git", ".svn", "__pycache__",
    "packages", "TestResults", "migrations", "archivado",
}

# ── Regex de extracción de keywords desde el texto del ticket ────────────────
_KW_PATTERNS = [
    # Clases C# (PascalCase, ≥2 palabras combinadas)
    r'\b(Frm[A-Z][a-zA-Z]{3,})\b',
    r'\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b',
    # Métodos típicos del proyecto
    r'\b((?:Get|Set|Load|Save|Update|Delete|Create|Build|Cargar|Guardar)[A-Z][a-zA-Z]{2,})\b',
    # Tablas Oracle (mayúsculas, 3+ chars, puede tener guión bajo)
    r'\b([A-Z]{2,}[A-Z_]{1,}[A-Z])\b',
    # Identificadores entre backticks
    r'`([^`\n]{3,40})`',
    # Nombres de archivo .cs / .aspx mencionados en texto
    r'\b(\w+\.(?:cs|aspx|aspx\.cs|sql))\b',
    # Siglas de módulos propios (RIDIOMA, RSFac, RSModel, etc.)
    r'\b(RS(?:Fac|Model|Serv|Marcadores)\.\w+)\b',
]

# Cuántos hits de una keyword en el mismo archivo antes de contar como duplicado
_MIN_HITS = 1
# Máximo de archivos a incluir en el contexto
_MAX_FILES = 8
# Máximo de líneas de snippet por archivo
_SNIPPET_LINES = 6


def _extract_keywords(text: str) -> list[str]:
    """
    Extrae keywords técnicos únicos del texto de un ticket.
    Filtra palabras genéricas y muy cortas.
    """
    _STOP_WORDS = {
        "string", "object", "class", "void", "return", "true", "false", "null",
        "select", "from", "where", "inner", "join", "group", "order", "left",
        "right", "insert", "update", "delete", "create", "table", "index",
        "completar", "placeholder", "ticket", "mantis", "error", "descripcion",
        "incidente", "analisis", "tecnico", "arquitectura", "solucion", "tareas",
        "notas", "implementacion", "queries", "pendiente", "generado", "fecha",
    }

    found = set()
    for pattern in _KW_PATTERNS:
        for m in re.finditer(pattern, text):
            kw = m.group(1).strip()
            if len(kw) < 3:
                continue
            if kw.lower() in _STOP_WORDS:
                continue
            found.add(kw)

    return list(found)


def _read_ticket_text(ticket_folder: str, ticket_id: str) -> str:
    """Lee los archivos de análisis del ticket para extraer keywords."""
    files_to_read = [
        f"INC-{ticket_id}.md",
        "INCIDENTE.md",
        "ANALISIS_TECNICO.md",
        "TAREAS_DESARROLLO.md",
    ]
    parts = []
    for fname in files_to_read:
        fpath = os.path.join(ticket_folder, fname)
        if os.path.exists(fpath):
            try:
                with open(fpath, encoding="utf-8", errors="replace") as fh:
                    parts.append(fh.read(4000))  # 4KB por archivo es más que suficiente
            except Exception:
                pass
    return "\n".join(parts)


def _search_workspace(workspace_root: str, keywords: list[str],
                      ticket_folder: str) -> list[dict]:
    """
    Busca keywords en el codebase usando Python puro (sin subprocess/grep).
    Retorna lista de {path, keyword, line_num, snippet, hits} ordenada por hits desc.
    """
    results: dict[str, dict] = {}   # path → {keyword, hits, line_num, snippet}
    ws_path = Path(workspace_root)

    # Normalizar ticket_folder para excluirlo de la búsqueda
    ticket_abs = os.path.abspath(ticket_folder)

    # Limitar el walk a las carpetas de código relevantes (evita recorrer todo el trunk en red)
    _CODE_ROOTS = ["OnLine", "Batch", "BD", "BatchVC", "VB"]
    search_roots = []
    for cr in _CODE_ROOTS:
        candidate = os.path.join(workspace_root, cr)
        if os.path.isdir(candidate):
            search_roots.append(candidate)
    if not search_roots:
        search_roots = [workspace_root]  # fallback si no existe ninguna

    for search_root in search_roots:
        for root, dirs, files in os.walk(search_root):
            # Podar directorios a ignorar in-place (modifica dirs)
            dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]

            for fname in files:
                ext = Path(fname).suffix.lower()
                if ext not in _CODE_EXTENSIONS:
                    continue

                fpath = os.path.join(root, fname)
                # No buscar dentro de la carpeta del ticket
                if os.path.abspath(fpath).startswith(ticket_abs):
                    continue

                try:
                    with open(fpath, encoding="utf-8", errors="replace") as fh:
                        lines = fh.readlines()
                except Exception:
                    continue

                content = "".join(lines)

                for kw in keywords:
                    # Búsqueda case-insensitive pero exacta de palabra
                    pattern = re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE)
                    matches = list(pattern.finditer(content))
                    if len(matches) < _MIN_HITS:
                        continue

                    hit_count = len(matches)
                    if fpath not in results or results[fpath]["hits"] < hit_count:
                        # Encontrar el número de línea del primer match
                        first_pos  = matches[0].start()
                        line_num   = content[:first_pos].count("\n") + 1
                        start_line = max(0, line_num - 2)
                        end_line   = min(len(lines), line_num + _SNIPPET_LINES)
                        snippet    = "".join(lines[start_line:end_line]).rstrip()

                        results[fpath] = {
                            "path":     fpath,
                            "rel_path": str(Path(fpath).relative_to(ws_path)).replace("\\", "/"),
                            "keyword":  kw,
                            "hits":     hit_count,
                            "line_num": line_num,
                            "snippet":  snippet,
                        }

    # Ordenar por hits descendente, limitar a MAX_FILES
    sorted_results = sorted(results.values(), key=lambda r: r["hits"], reverse=True)
    return sorted_results[:_MAX_FILES]


def find_relevant_files(ticket_folder: str, ticket_id: str,
                        workspace_root: str) -> list[dict]:
    """
    API pública: retorna lista de archivos relevantes para el ticket.
    Cada elemento: {rel_path, keyword, hits, line_num, snippet}
    """
    text     = _read_ticket_text(ticket_folder, ticket_id)
    keywords = _extract_keywords(text)

    if not keywords:
        return []

    return _search_workspace(workspace_root, keywords, ticket_folder)


def format_code_context(relevant_files: list[dict]) -> str:
    """
    Formatea el contexto de código como sección Markdown lista para inyectar
    en cualquier prompt de PM o Dev.
    """
    if not relevant_files:
        return ""

    lines = [
        "",
        "---",
        "",
        "## Contexto de código relevante (auto-detectado)",
        "",
        "Los siguientes archivos del codebase fueron encontrados como relevantes "
        "para esta incidencia:",
        "",
        "| Archivo | Keyword | Línea | Ocurrencias |",
        "|---------|---------|-------|-------------|",
    ]
    for r in relevant_files:
        lines.append(
            f"| `{r['rel_path']}` | `{r['keyword']}` | {r['line_num']} | {r['hits']} |"
        )

    lines.append("")
    lines.append("### Snippets")
    lines.append("")
    for r in relevant_files:
        lines.append(f"#### `{r['rel_path']}` (línea {r['line_num']})")
        lines.append("")
        ext = Path(r["rel_path"]).suffix.lstrip(".")
        lang = {"cs": "csharp", "sql": "sql", "js": "javascript",
                "aspx": "html"}.get(ext, "")
        lines.append(f"```{lang}")
        lines.append(r["snippet"])
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def extract_files_from_architecture(ticket_folder: str,
                                     workspace_root: str) -> list[dict]:
    """
    M-05: Extrae rutas de archivos mencionadas en ARQUITECTURA_SOLUCION.md.
    Estas son las rutas que PM identificó explícitamente — tienen prioridad
    sobre el análisis heurístico de keywords.

    Retorna lista de {rel_path, abs_path, exists} ordenada por aparición en el doc.
    """
    arq_path = os.path.join(ticket_folder, "ARQUITECTURA_SOLUCION.md")
    if not os.path.exists(arq_path):
        return []

    try:
        content = Path(arq_path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    ws_path = Path(workspace_root)
    found   = []
    seen    = set()

    # Patrones para detectar rutas de archivo en el texto
    path_patterns = [
        # Rutas absolutas Windows: N:\SVN\...
        r'[A-Z]:\\[^\s`\'"<>|\n]+\.(?:cs|aspx|aspx\.cs|vb|sql|config|js|html)',
        # Rutas relativas con carpetas: folder/subfolder/File.cs
        r'(?:[\w\-]+/)+[\w\-]+\.(?:cs|aspx|vb|sql|config|js)',
        # Solo nombre de archivo con extensión conocida (precedido de espacio o backtick)
        r'(?<![/\\])(?:`|\'|"|\s)([\w\-]+\.(?:cs|aspx|vb|sql|config))(?:`|\'|"|\s|$)',
        # Backtick inline: `Folder/File.cs`
        r'`([^`\n]{3,80}\.(?:cs|aspx|aspx\.cs|vb|sql|config|js))`',
    ]

    for pat in path_patterns:
        for m in re.finditer(pat, content, re.IGNORECASE):
            raw = (m.group(1) if m.lastindex else m.group(0)).strip().strip("`'\". ")
            if not raw or raw in seen:
                continue
            seen.add(raw)

            # Intentar resolver la ruta relativa al workspace
            candidates = [
                ws_path / raw,
                ws_path / raw.replace("\\", "/"),
                # Buscar solo por nombre base si no se resuelve por ruta completa
            ]
            resolved = None
            for candidate in candidates:
                if candidate.exists():
                    resolved = candidate
                    break

            # Si no se resolvió por ruta directa, buscar por nombre de archivo
            if resolved is None:
                basename = Path(raw).name
                if basename and len(basename) > 3:
                    _arch_roots = [ws_path / cr for cr in ["OnLine", "Batch", "BD", "BatchVC", "VB"] if (ws_path / cr).is_dir()] or [ws_path]
                    for sr in _arch_roots:
                        for root, dirs, files in os.walk(sr):
                            dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
                            if basename.lower() in [f.lower() for f in files]:
                                match_path = Path(root) / basename
                                if match_path.exists():
                                    resolved = match_path
                                    break
                        if resolved:
                            break

            rel = str(resolved.relative_to(ws_path)).replace("\\", "/") if resolved else raw
            found.append({
                "rel_path": rel,
                "abs_path": str(resolved) if resolved else "",
                "exists":   resolved is not None,
                "source":   "arquitectura",
            })

    return found[:12]  # máximo 12 archivos de arquitectura


def build_code_context_section(ticket_folder: str, ticket_id: str,
                                workspace_root: str) -> str:
    """
    Función de alto nivel: extrae keywords + rutas de ARQUITECTURA_SOLUCION.md,
    busca en el codebase, retorna la sección Markdown formateada.

    M-05: Prioriza rutas mencionadas explícitamente en ARQUITECTURA_SOLUCION.md
    sobre la detección heurística de keywords.

    Tiempo típico: 2-8 segundos dependiendo del tamaño del codebase.
    """
    try:
        # M-05: archivos mencionados explícitamente por PM en ARQUITECTURA_SOLUCION
        arch_files = extract_files_from_architecture(ticket_folder, workspace_root)

        # Heurística: keywords → búsqueda en codebase
        heuristic_files = find_relevant_files(ticket_folder, ticket_id, workspace_root)

        # Combinar: arch_files primero (más confiables), completar con heurística
        # Evitar duplicados por rel_path
        seen_paths = {f["rel_path"] for f in arch_files if f.get("exists")}
        combined   = [f for f in arch_files if f.get("exists")]
        for f in heuristic_files:
            if f["rel_path"] not in seen_paths:
                combined.append(f)
                seen_paths.add(f["rel_path"])

        combined = combined[:_MAX_FILES + 4]  # un poco más de espacio por tener 2 fuentes

        if not combined:
            return ""

        # Marcar origen en el formato
        for f in combined:
            if f.get("source") == "arquitectura":
                f["keyword"] = "★ ARQUITECTURA_SOLUCION"
            elif "keyword" not in f:
                f["keyword"] = "(heurístico)"

        return format_code_context(combined)
    except Exception as e:
        import logging
        logging.getLogger("mantis.code_context").warning(
            "Error buscando contexto de código para %s: %s", ticket_id, e
        )
        return ""
