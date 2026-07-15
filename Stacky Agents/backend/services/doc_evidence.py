"""Plan 137 — Evidencia determinista para el Documentador (v2).

Módulo sin dependencia del LLM: da al Documentador evidencia real de código
(árbol + símbolos con línea) y verifica citas `archivo:línea` contra el
filesystem real. Nunca lanza hacia el pipeline que lo invoca (best-effort:
captura y degrada a vacío/False ante cualquier error).
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_SYMBOL_PATTERNS: dict[str, str] = {
    ".py":  r"^(?:async\s+def|def|class)\s+\w+",
    ".ts":  r"^export\s+(?:async\s+)?(?:function|class|const|interface|type)\s+\w+",
    ".tsx": r"^export\s+(?:async\s+)?(?:function|class|const|interface|type)\s+\w+",
    ".js":  r"^(?:export\s+)?(?:async\s+)?(?:function|class|const)\s+\w+",
    ".cs":  r"^\s*(?:public|internal|protected|private)\s+.*(?:class|interface|void|Task|string|int|bool)\s+\w+",
    ".ps1": r"^function\s+[\w-]+",
}

_EXCLUDED_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv",
                  "dist", "build", ".stacky-docs-proposed"}


def extract_symbols(rel_path: str, content: str) -> list[str]:
    """Devuelve ["<rel_path>:<lineno> <línea recortada a 120 chars>"] por cada
    match del patrón de la extensión. Extensión sin patrón → []. Nunca lanza."""
    try:
        ext = Path(rel_path).suffix.lower()
        pattern = _SYMBOL_PATTERNS.get(ext)
        if not pattern:
            return []
        regex = re.compile(pattern)
        out: list[str] = []
        for i, line in enumerate(content.splitlines(), start=1):
            if regex.match(line):
                snippet = line.strip()[:120]
                out.append(f"{rel_path}:{i} {snippet}")
        return out
    except Exception as exc:
        logger.warning("doc_evidence: extract_symbols falló para %s: %s", rel_path, exc)
        return []


def build_module_evidence(workspace_root: str, module: str, *,
                          max_files: int = 30, max_chars: int = 12000) -> str:
    """Evidencia determinista de un módulo: árbol + símbolos con línea real.
    Nunca lanza (best-effort: degrada a "")."""
    try:
        root = Path(workspace_root)
        base = root if module == "<repo>" else root / module
        if not base.is_dir():
            return ""

        allowed_exts = set(_SYMBOL_PATTERNS) | {".md"}
        rel_paths: list[str] = []
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in _EXCLUDED_DIRS)
            for fn in sorted(filenames):
                if Path(fn).suffix.lower() not in allowed_exts:
                    continue
                abs_path = Path(dirpath) / fn
                try:
                    rel = abs_path.relative_to(root).as_posix()
                except ValueError:
                    continue
                rel_paths.append(rel)
                if len(rel_paths) >= max_files:
                    break
            if len(rel_paths) >= max_files:
                break

        if not rel_paths:
            return ""

        tree_lines = ["ARBOL:"] + rel_paths
        symbol_lines = ["SIMBOLOS:"]
        for rel in rel_paths:
            try:
                text = (root / rel).read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            symbol_lines.extend(extract_symbols(rel, text))

        out = "\n".join(tree_lines) + "\n" + "\n".join(symbol_lines)
        if len(out) > max_chars:
            suffix = "\n[...evidencia truncada]"
            out = out[: max_chars - len(suffix)] + suffix
        return out
    except Exception as exc:
        logger.warning("doc_evidence: build_module_evidence falló para %s/%s: %s",
                        workspace_root, module, exc)
        return ""


_CITATION_RE = re.compile(r"(?P<path>[\w][\w./\\-]*\.[A-Za-z0-9]{1,5}):(?P<line>\d{1,6})")

# C3 — solo extensiones citables reales; sin esto, URLs/puertos/versiones
# ("x.com:8080", "1.0.73:12") caen en `bad` y desacreditan el chip de citas.
_CITABLE_EXTS: frozenset[str] = frozenset(_SYMBOL_PATTERNS) | frozenset(
    {".md", ".json", ".yaml", ".yml", ".toml", ".css", ".html", ".sql", ".env", ".txt"})


def extract_citations(text: str) -> list[tuple[str, int]]:
    """Todos los pares (path_normalizado_posix, línea) que matchean _CITATION_RE
    en text, filtrando (C3): (a) extensión fuera de _CITABLE_EXTS; (b) matches
    precedidos inmediatamente por "://" o "//" (URLs). Deduplicados preservando
    orden. Nunca lanza."""
    try:
        out: list[tuple[str, int]] = []
        seen: set[tuple[str, int]] = set()
        for m in _CITATION_RE.finditer(text):
            path = m.group("path")
            ext = Path(path).suffix.lower()
            if ext not in _CITABLE_EXTS:
                continue
            start = m.start("path")
            prefix = text[max(0, start - 3):start]
            if prefix.endswith("://") or prefix.endswith("//"):
                continue
            norm_path = path.replace("\\", "/")
            line = int(m.group("line"))
            key = (norm_path, line)
            if key in seen:
                continue
            seen.add(key)
            out.append(key)
        return out
    except Exception as exc:
        logger.warning("doc_evidence: extract_citations falló: %s", exc)
        return []


def verify_citations(text: str, workspace_root: str) -> dict:
    """{"total": N, "ok": M, "bad": ["path:line", ...]} donde una cita es ok si
    Path(workspace_root)/path existe como archivo Y (línea == 0 o línea <=
    cantidad de líneas del archivo). workspace_root vacío/inexistente →
    {"total": N, "ok": 0, "bad": [todas]}. Nunca lanza."""
    try:
        citations = extract_citations(text)
        total = len(citations)
        ok = 0
        bad: list[str] = []
        root = Path(workspace_root) if workspace_root else None
        root_valid = bool(root and root.is_dir())
        for path, line in citations:
            label = f"{path}:{line}"
            if not root_valid:
                bad.append(label)
                continue
            target = root / path
            if not target.is_file():
                bad.append(label)
                continue
            if line == 0:
                ok += 1
                continue
            try:
                n_lines = len(target.read_text(encoding="utf-8", errors="ignore").splitlines())
            except Exception:
                bad.append(label)
                continue
            if line <= n_lines:
                ok += 1
            else:
                bad.append(label)
        return {"total": total, "ok": ok, "bad": bad}
    except Exception as exc:
        logger.warning("doc_evidence: verify_citations falló: %s", exc)
        return {"total": 0, "ok": 0, "bad": []}
