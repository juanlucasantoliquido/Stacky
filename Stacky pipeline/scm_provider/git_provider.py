"""
scm_provider.git_provider — Git para Stacky (incluye Azure DevOps Repos).

Características clave:
  - Detecta automáticamente si el remoto apunta a `dev.azure.com` y deja
    metadata útil en `RepoInfo` para correlacionar con work items.
  - Usa trailers `AB#<id>` en mensajes de commit para asociar commits a work
    items de ADO (convención nativa — al hacer push, ADO linkea el commit).
  - Subprocess-only, sin dependencias externas.

Uso típico asociado a un work item:

    scm = GitProvider()
    scm.add(workspace, ["path/a.cs"])
    scm.commit(workspace, "[#12345] corrige cálculo X",
               files=["path/a.cs"], work_item_id="12345")
    scm.push(workspace)
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

from .base import ChangedFile, CommitResult, RepoInfo, ScmProvider

logger = logging.getLogger("stacky.scm.git")

_GIT_SEARCH_PATHS = [
    r"C:\Program Files\Git\bin\git.exe",
    r"C:\Program Files\Git\cmd\git.exe",
    r"C:\Program Files (x86)\Git\bin\git.exe",
]

_git_exe: str | None = None


def _find_git() -> str:
    global _git_exe
    if _git_exe:
        return _git_exe
    found = shutil.which("git")
    if found:
        _git_exe = found
        return _git_exe
    for candidate in _GIT_SEARCH_PATHS:
        if Path(candidate).is_file():
            _git_exe = candidate
            return _git_exe
    raise FileNotFoundError(
        "git no se encontró. Instale Git for Windows o agréguelo al PATH."
    )


def _run(ws: str, args: list[str], timeout: int = 60,
         check: bool = False) -> subprocess.CompletedProcess:
    exe = _find_git()
    return subprocess.run(
        [exe, *args],
        cwd=ws,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=check,
    )


# Cache toplevel por workspace (se resuelve una vez vía rev-parse --show-toplevel)
_TOPLEVEL_CACHE: dict[str, str] = {}


def _repo_toplevel(ws: str) -> str:
    """Devuelve el directorio raíz del repo git.

    Cuando `workspace_root` apunta a un subdir (ej: `trunk/`) pero el `.git/`
    está en un ancestor, `git status --porcelain` devuelve paths relativos al
    toplevel (no al cwd). Para que `git add`/`git commit -- <path>` matcheen
    esos paths, hay que correr los comandos desde el toplevel.
    """
    if ws in _TOPLEVEL_CACHE:
        return _TOPLEVEL_CACHE[ws]
    try:
        r = _run(ws, ["rev-parse", "--show-toplevel"], timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            top = r.stdout.strip()
            _TOPLEVEL_CACHE[ws] = top
            return top
    except Exception:
        pass
    return ws


class GitProvider(ScmProvider):
    """Git SCM, compatible con Azure DevOps Repos."""

    name = "git"

    # ── Discovery ────────────────────────────────────────────────────────

    def is_available(self, workspace: str) -> tuple[bool, str]:
        if not workspace or not os.path.isdir(workspace):
            return False, f"workspace inexistente: {workspace}"
        try:
            r = _run(workspace, ["rev-parse", "--is-inside-work-tree"], timeout=10)
        except FileNotFoundError as e:
            return False, str(e)
        except Exception as e:
            return False, f"git error: {e}"
        if r.returncode != 0 or r.stdout.strip() != "true":
            return False, f"workspace no es repo git: {workspace}"
        return True, ""

    # ── Info ─────────────────────────────────────────────────────────────

    def info(self, workspace: str) -> RepoInfo:
        url      = self._read("remote", "get-url", "origin", ws=workspace)
        branch   = self._read("rev-parse", "--abbrev-ref", "HEAD", ws=workspace)
        revision = self._read("rev-parse", "HEAD", ws=workspace)
        return RepoInfo(
            kind="git",
            url=url,
            branch=branch,
            revision=revision,
            workspace=os.path.abspath(workspace),
        )

    def is_azure_devops(self, workspace: str) -> bool:
        info = self.info(workspace)
        return "dev.azure.com" in (info.url or "") or "visualstudio.com" in (info.url or "")

    # ── Status / diff ────────────────────────────────────────────────────

    def status(self, workspace: str) -> list[ChangedFile]:
        # Correr desde el toplevel para que los paths sean repo-root-relative
        # y coincidan con lo que después acepta `git add`.
        top = _repo_toplevel(workspace)
        r = _run(top, ["status", "--porcelain=v1", "-uall"])
        out: list[ChangedFile] = []
        if r.returncode != 0:
            logger.warning("git status falló: %s", r.stderr[:200])
            return out
        for line in r.stdout.splitlines():
            # formato: "XY path" donde X = index, Y = worktree
            if len(line) < 3:
                continue
            x, y = line[0], line[1]
            path = line[3:].strip()
            # Git escapa paths con espacios/especiales entre comillas dobles.
            if len(path) >= 2 and path.startswith('"') and path.endswith('"'):
                path = path[1:-1]
            status = _porcelain_status(x, y)
            out.append(ChangedFile(path=path, status=status, summary=line))
        return out

    def diff(self, workspace: str, full: bool = False, paths: list[str] | None = None) -> str:
        args = ["diff"]
        if not full:
            args.append("--stat")
        # Incluye staged + no staged
        args.append("HEAD")
        if paths:
            args.append("--")
            args.extend(paths)
        r = _run(workspace, args, timeout=120)
        return r.stdout if r.returncode == 0 else f"[git diff error] {r.stderr[:300]}"

    # ── Staging / commit / push ──────────────────────────────────────────

    def add(self, workspace: str, paths: list[str]) -> tuple[bool, str]:
        """Devuelve (ok, error_stderr). Antes devolvía solo bool — ahora expone el
        stderr para que el caller pueda surface-arlo."""
        if not paths:
            return True, ""
        # Correr desde toplevel: paths vienen repo-root-relative (de `status()`).
        top = _repo_toplevel(workspace)
        r = _run(top, ["add", "--", *paths])
        if r.returncode != 0:
            err = (r.stderr or r.stdout)[:500]
            logger.warning("git add falló: %s", err)
            return False, err
        return True, ""

    def commit(
        self,
        workspace: str,
        message: str,
        files: list[str] | None = None,
        work_item_id: str | None = None,
    ) -> CommitResult:
        """
        Commit con mensaje enriquecido:
          - Si `work_item_id` viene, se agrega trailer `AB#<id>` para que ADO
            linkee el commit al work item al hacer push.
          - Se respeta hooks existentes (no usa --no-verify).
        """
        if not message.strip():
            return CommitResult(ok=False, error="mensaje vacío")

        if files:
            ok, err = self.add(workspace, files)
            if not ok:
                return CommitResult(
                    ok=False, message=message, files=files,
                    error=f"git add falló: {err}",
                )

        full_msg = message.rstrip() + "\n"
        if work_item_id and f"AB#{work_item_id}" not in message:
            full_msg += f"\nAB#{work_item_id}\n"

        args = ["commit", "-m", full_msg]
        # Cuando se especifican archivos, commitear SOLO esos paths para no
        # arrastrar cambios stageados previamente sin relación al ticket.
        if files:
            args.append("--")
            args.extend(files)
        # Correr desde toplevel para consistencia con add() / status().
        top = _repo_toplevel(workspace)
        r = _run(top, args, timeout=120)
        if r.returncode != 0:
            return CommitResult(
                ok=False, message=message, files=files or [],
                error=(r.stderr or r.stdout)[:500],
            )
        # Recuperar hash
        sha = self._read("rev-parse", "HEAD", ws=top)
        return CommitResult(
            ok=True, revision=sha, message=message, files=files or [], error="",
        )

    def push(self, workspace: str, remote: str = "origin",
             branch: str | None = None) -> tuple[bool, str]:
        branch = branch or self.current_branch(workspace) or "HEAD"
        args = ["push", remote, branch]
        r = _run(workspace, args, timeout=180)
        if r.returncode != 0:
            return False, (r.stderr or r.stdout)[:500]
        return True, r.stdout[:500]

    # ── Meta ─────────────────────────────────────────────────────────────

    def current_branch(self, workspace: str) -> str:
        return self._read("rev-parse", "--abbrev-ref", "HEAD", ws=workspace)

    def log(self, workspace: str, limit: int = 10) -> list[dict]:
        fmt = "%H%x09%an%x09%ai%x09%s"
        r = _run(workspace, ["log", f"-{int(limit)}", f"--pretty=format:{fmt}"])
        if r.returncode != 0:
            return []
        out: list[dict] = []
        for line in r.stdout.splitlines():
            parts = line.split("\t", 3)
            if len(parts) == 4:
                out.append({
                    "sha": parts[0], "author": parts[1],
                    "date": parts[2], "subject": parts[3],
                })
        return out

    def _read(self, *args: str, ws: str) -> str:
        r = _run(ws, list(args))
        return r.stdout.strip() if r.returncode == 0 else ""


def _porcelain_status(x: str, y: str) -> str:
    """Convierte flags de porcelain v1 a letras simples Stacky usa."""
    if x == "?" and y == "?":
        return "?"
    if "A" in (x, y):
        return "A"
    if "D" in (x, y):
        return "D"
    if "M" in (x, y) or "R" in (x, y) or "C" in (x, y):
        return "M"
    return (x + y).strip() or "M"


# ── Helpers expuestos para consumidores externos ─────────────────────────

_ADO_URL_RE = re.compile(
    r"https?://(?P<host>dev\.azure\.com|[\w-]+\.visualstudio\.com)/"
    r"(?P<org>[\w-]+)/(?:(?P<proj>[\w%. -]+)/)?_git/(?P<repo>[\w%. -]+)",
    re.IGNORECASE,
)


def parse_ado_remote(url: str) -> dict | None:
    """
    Descompone un remote git de ADO en sus partes. Retorna None si no matchea.

    Ejemplo:
        https://dev.azure.com/UbimiaPacifico/Strategist_Pacifico/_git/RSPacifico
        → {"org":"UbimiaPacifico","project":"Strategist_Pacifico","repo":"RSPacifico"}
    """
    if not url:
        return None
    m = _ADO_URL_RE.search(url)
    if not m:
        return None
    return {
        "host":    m.group("host"),
        "org":     m.group("org"),
        "project": m.group("proj") or "",
        "repo":    m.group("repo"),
    }
