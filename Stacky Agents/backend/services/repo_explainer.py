"""C9 — "Explain my repo" capability.

Implementación práctica del agente Explain Repo: analiza estructura, git log y
glosario para producir un mapa mental del repositorio (texto + Mermaid).

Se expone como servicio independiente (no como agente formal en `agents/`)
para evitar el costo de registrarlo en todo el pipeline; un endpoint dedicado
en `api/adoption.py::repo_explain` lo invoca on-demand.
"""
from __future__ import annotations

import logging
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

logger = logging.getLogger("stacky.repo_explainer")

_IGNORED_DIRS = {
    ".git", "node_modules", "__pycache__", "dist", "build", "bin", "obj",
    ".vs", ".idea", ".vscode", "venv", ".venv", "packages",
}
_RELEVANT_EXTENSIONS = {
    ".py", ".cs", ".ts", ".tsx", ".js", ".jsx", ".vb", ".sql",
    ".java", ".go", ".rs", ".rb", ".php", ".html", ".css",
}


def explain_repo(workspace_root: str | Path, *, ticket_hint: str | None = None,
                 since_days: int = 30) -> dict:
    """Devuelve un dict con mapa del repo + Mermaid + archivos hot."""
    root = Path(workspace_root).resolve()
    if not root.exists():
        return {"ok": False, "error": "workspace_not_found", "workspace_root": str(root)}

    modules = _detect_modules(root)
    hot_files, top_authors_by_path = _git_hotspots(root, since_days=since_days)
    cold_dirs = _detect_cold_dirs(root, since_days=since_days)
    mermaid = _build_mermaid(modules)

    relevant_for_ticket: list[dict] = []
    if ticket_hint:
        relevant_for_ticket = _relevant_files_for_ticket(hot_files, ticket_hint)

    return {
        "ok": True,
        "workspace_root": str(root),
        "since_days": since_days,
        "summary": {
            "modules": len(modules),
            "hot_files": len(hot_files),
            "cold_dirs": len(cold_dirs),
        },
        "modules": [
            {
                "path": m["path"],
                "commits_last_period": m["commits"],
                "top_author": m["top_author"],
                "is_hot": m["commits"] >= 5,
            }
            for m in modules
        ],
        "hot_files": hot_files[:25],
        "cold_dirs": cold_dirs[:25],
        "mermaid": mermaid,
        "relevant_for_ticket": relevant_for_ticket,
    }


def _detect_modules(root: Path) -> list[dict]:
    """Detecta directorios "módulo": primer nivel con archivos de código."""
    results: list[dict] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name in _IGNORED_DIRS or child.name.startswith("."):
            continue
        rel = child.relative_to(root).as_posix()
        commits, top_author = _git_commits_for_path(root, rel)
        if commits == 0 and not _has_code_files(child):
            continue
        results.append({
            "path": rel,
            "commits": commits,
            "top_author": top_author,
        })
    results.sort(key=lambda m: m["commits"], reverse=True)
    return results


def _has_code_files(path: Path) -> bool:
    try:
        for p in path.rglob("*"):
            if any(part in _IGNORED_DIRS for part in p.parts):
                continue
            if p.is_file() and p.suffix.lower() in _RELEVANT_EXTENSIONS:
                return True
    except OSError:
        return False
    return False


def _git(root: Path, *args: str, timeout: int = 10) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if completed.returncode != 0:
            return ""
        return completed.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def _git_commits_for_path(root: Path, rel_path: str) -> tuple[int, str | None]:
    raw = _git(root, "log", "--since=30 days ago", "--format=%an", "--", rel_path)
    authors = [line.strip() for line in raw.splitlines() if line.strip()]
    if not authors:
        return 0, None
    top = Counter(authors).most_common(1)[0][0]
    return len(authors), top


def _git_hotspots(root: Path, *, since_days: int) -> tuple[list[dict], dict[str, str]]:
    since_arg = f"--since={since_days} days ago"
    raw = _git(root, "log", since_arg, "--name-only", "--format=---%n%an")
    if not raw:
        return [], {}

    file_counts: Counter[str] = Counter()
    file_authors: defaultdict[str, Counter[str]] = defaultdict(Counter)
    current_author: str | None = None
    for line in raw.splitlines():
        line = line.strip()
        if line == "---":
            current_author = None
            continue
        if current_author is None:
            current_author = line
            continue
        if not line:
            continue
        suffix = Path(line).suffix.lower()
        if suffix and suffix not in _RELEVANT_EXTENSIONS:
            continue
        file_counts[line] += 1
        file_authors[line][current_author] += 1

    hot = [
        {
            "path": path,
            "commits": count,
            "top_author": file_authors[path].most_common(1)[0][0] if file_authors[path] else None,
        }
        for path, count in file_counts.most_common(50)
        if count >= 2
    ]
    top_authors_by_path = {
        path: ctr.most_common(1)[0][0] for path, ctr in file_authors.items() if ctr
    }
    return hot, top_authors_by_path


def _detect_cold_dirs(root: Path, *, since_days: int) -> list[dict]:
    """Directorios con código que no recibieron commits en el período."""
    raw = _git(root, "log", f"--since={since_days * 4} days ago", "--name-only", "--format=")
    touched = {line.strip() for line in raw.splitlines() if line.strip()}

    recent_raw = _git(root, "log", f"--since={since_days} days ago", "--name-only", "--format=")
    recently_touched = {line.strip() for line in recent_raw.splitlines() if line.strip()}

    cold: list[dict] = []
    for child in root.rglob("*"):
        if any(p in _IGNORED_DIRS for p in child.parts):
            continue
        if not child.is_dir():
            continue
        rel = child.relative_to(root).as_posix()
        rel_files = [f for f in touched if f.startswith(rel + "/")]
        recent_files = [f for f in recently_touched if f.startswith(rel + "/")]
        if rel_files and not recent_files:
            cold.append({"path": rel, "last_touched_files": rel_files[:3]})
        if len(cold) >= 30:
            break
    return cold


def _build_mermaid(modules: list[dict]) -> str:
    """Construye un diagrama Mermaid simple con los módulos hot."""
    if not modules:
        return "graph LR\n  empty[Sin módulos detectados]"
    lines = ["graph LR"]
    for m in modules[:8]:
        node_id = re.sub(r"[^a-zA-Z0-9]", "_", m["path"]) or "root"
        style = "[[" + m["path"] + "]]" if m["commits"] >= 5 else "[" + m["path"] + "]"
        lines.append(f"  {node_id}{style}")
    return "\n".join(lines)


def _relevant_files_for_ticket(hot_files: list[dict], ticket_hint: str) -> list[dict]:
    """Marca archivos hot que contienen términos del ticket en su path."""
    terms = [t.lower() for t in re.findall(r"[a-zA-Z]{3,}", ticket_hint)][:8]
    if not terms:
        return []
    matches: list[dict] = []
    for f in hot_files:
        path_lower = f["path"].lower()
        hits = [t for t in terms if t in path_lower]
        if hits:
            matches.append({**f, "matched_terms": hits})
    return matches[:15]
