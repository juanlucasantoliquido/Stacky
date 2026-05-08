"""
FA-05 — Git context awareness.

Para los archivos relacionados al ticket, devolvemos:
- Últimos N commits que los tocaron (autor, fecha, hash, subject).
- PRs / branches activos sobre los mismos archivos (si está disponible vía git remote).
- Blame por método (Fase 4+; ahora sólo hint).

Diseño: subprocess sobre `git` en el repo configurado por env
(`GIT_REPO_ROOT`, default = parent del backend = workspace de RSPacifico).
Cache 5min por archivo+commit-of-HEAD para no spammear git en cada Run.
"""
from __future__ import annotations

import os
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class CommitInfo:
    sha: str
    author: str
    date: str
    subject: str
    files: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FileContext:
    path: str
    last_commits: list[CommitInfo]
    last_modified_by: str | None
    last_modified_at: str | None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "last_commits": [c.to_dict() for c in self.last_commits],
            "last_modified_by": self.last_modified_by,
            "last_modified_at": self.last_modified_at,
            "error": self.error,
        }


def _repo_root() -> Path:
    explicit = os.getenv("GIT_REPO_ROOT")
    if explicit:
        return Path(explicit)
    # default: subir tres niveles desde backend/services hasta el workspace
    return Path(__file__).resolve().parents[3]


def _git(args: list[str], cwd: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", *args],
            cwd=str(cwd),
            stderr=subprocess.STDOUT,
            timeout=8,
        )
        return out.decode("utf-8", errors="replace")
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(exc.output.decode("utf-8", errors="replace")) from exc
    except subprocess.TimeoutExpired:
        raise RuntimeError("git timeout") from None


# ---------------------------------------------------------------------------
# Cache simple por (file, head_sha)
# ---------------------------------------------------------------------------
_CACHE: dict[str, tuple[float, FileContext]] = {}
_TTL = 300.0  # 5 min


def _head_sha(repo: Path) -> str:
    try:
        return _git(["rev-parse", "HEAD"], repo).strip()
    except Exception:
        return ""


def file_context(path: str, *, n_commits: int = 5) -> FileContext:
    repo = _repo_root()
    head = _head_sha(repo)
    key = f"{head}::{path}::{n_commits}"
    now = time.time()
    cached = _CACHE.get(key)
    if cached and (now - cached[0]) < _TTL:
        return cached[1]

    if not (repo / path).exists():
        ctx = FileContext(path=path, last_commits=[], last_modified_by=None,
                          last_modified_at=None, error="file not found in repo")
        _CACHE[key] = (now, ctx)
        return ctx

    try:
        # log con formato controlado
        fmt = "%H%x1f%an%x1f%aI%x1f%s"
        raw = _git(["log", f"-n{n_commits}", "--pretty=format:" + fmt, "--", path], repo)
        commits: list[CommitInfo] = []
        for line in raw.strip().splitlines():
            parts = line.split("\x1f")
            if len(parts) >= 4:
                commits.append(CommitInfo(
                    sha=parts[0][:10],
                    author=parts[1],
                    date=parts[2],
                    subject=parts[3],
                    files=[path],
                ))
        last_by = commits[0].author if commits else None
        last_at = commits[0].date if commits else None
        ctx = FileContext(
            path=path,
            last_commits=commits,
            last_modified_by=last_by,
            last_modified_at=last_at,
        )
    except Exception as exc:  # noqa: BLE001
        ctx = FileContext(
            path=path, last_commits=[], last_modified_by=None,
            last_modified_at=None, error=str(exc)[:200],
        )
    _CACHE[key] = (now, ctx)
    return ctx


def context_for_files(paths: list[str], *, n_commits: int = 3) -> list[FileContext]:
    return [file_context(p, n_commits=n_commits) for p in paths]


def build_context_block(paths: list[str], *, n_commits: int = 3) -> dict | None:
    """ContextBlock listo para inyectar al editor."""
    if not paths:
        return None
    contexts = context_for_files(paths, n_commits=n_commits)
    contexts = [c for c in contexts if c.last_commits or c.error]
    if not contexts:
        return None

    lines: list[str] = []
    for ctx in contexts:
        lines.append(f"### {ctx.path}")
        if ctx.error:
            lines.append(f"  - _error_: {ctx.error}")
            continue
        if ctx.last_modified_by:
            lines.append(f"  - última modif: **{ctx.last_modified_by}** · {ctx.last_modified_at}")
        for c in ctx.last_commits[:n_commits]:
            lines.append(f"  - `{c.sha}` {c.author} — {c.subject}")
        lines.append("")

    return {
        "id": "git-context-auto",
        "kind": "auto",
        "title": f"Contexto Git ({len(contexts)} archivo{'s' if len(contexts) != 1 else ''})",
        "content": "\n".join(lines).strip(),
        "source": {"type": "git", "files": [c.path for c in contexts]},
    }
