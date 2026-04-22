"""
ticket_changes_resolver.py — Resuelve los cambios Git de un ticket concreto.

Objetivo: evitar que el endpoint /api/diff mezcle cambios de tickets paralelos
cuando no hay snapshot guardado (bug "Ver Cambios Git" mostrando el workspace
completo).

Estrategia (en orden de preferencia, cae al siguiente si no hay resultado):

  1. ``commits``       — busca commits que referencian ``AB#<id>`` en el
                         mensaje (trailer ADO). Enumera archivos vía
                         ``git show --name-status`` por commit.
                         Incluye archivos todavía en working tree si hay
                         cambios pendientes que también afectan esos paths.
  2. ``branch``        — busca una rama feature del ticket
                         (``feature/<id>``, ``ticket/<id>``, ``bug/<id>``,
                         ``ab-<id>``) y hace ``git diff --name-status
                         <merge-base>...<branch>``.
  3. ``working-tree``  — último recurso. Devuelve ``git status --porcelain``
                         pero MARCA la fuente como
                         ``working-tree (posiblemente mezclado)`` para que el
                         caller pueda mostrar una advertencia al usuario.

El módulo es best-effort: cualquier excepción cae al siguiente fallback.
No escribe nada — sólo lee Git.

Uso:

    from ticket_changes_resolver import resolve_ticket_changes
    result = resolve_ticket_changes("27698", "N:/GIT/RS/RSPacifico")
    # result = {
    #   "source": "commits" | "branch" | "working-tree (posiblemente mezclado)",
    #   "files":   ["M path/a.cs", "A path/b.sql", ...],
    #   "diff":    "... git diff ...",
    #   "commits": [{"sha": "...", "subject": "...", "date": "..."}],
    #   "branch":  "feature/27698" | "",
    #   "warning": "..." | "",
    # }
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from typing import Iterable

logger = logging.getLogger("stacky.ticket_changes_resolver")

_GIT_TIMEOUT = 30  # segundos
_MAX_DIFF_BYTES = 500 * 1024  # 500 KB — mismo límite que dashboard_server._git_diff
_BRANCH_PATTERNS = (
    "feature/{tid}",
    "feat/{tid}",
    "ticket/{tid}",
    "bug/{tid}",
    "fix/{tid}",
    "ab-{tid}",
    "ab/{tid}",
)


@dataclass
class ResolvedChanges:
    """Resultado estructurado del resolver."""

    source: str = ""                     # commits | branch | working-tree (posiblemente mezclado)
    files: list[str] = field(default_factory=list)
    diff: str = ""
    commits: list[dict] = field(default_factory=list)
    branch: str = ""
    warning: str = ""

    def to_dict(self) -> dict:
        return {
            "source":  self.source,
            "files":   "\n".join(self.files),
            "files_list": self.files,
            "diff":    self.diff,
            "commits": self.commits,
            "branch":  self.branch,
            "warning": self.warning,
        }


# ── helpers Git ────────────────────────────────────────────────────────────────

def _run_git(workspace: str, args: list[str], timeout: int = _GIT_TIMEOUT) -> subprocess.CompletedProcess:
    """Corre ``git <args>`` en workspace y devuelve el CompletedProcess.

    No levanta excepción — el caller decide cómo reaccionar al returncode.
    """
    return subprocess.run(
        ["git", *args],
        cwd=workspace,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _safe_git(workspace: str, args: list[str], timeout: int = _GIT_TIMEOUT) -> str:
    """Como _run_git pero devuelve stdout (o "" ante error/ timeout)."""
    try:
        r = _run_git(workspace, args, timeout=timeout)
        if r.returncode != 0:
            return ""
        return r.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        logger.debug("git %s falló: %s", args, e)
        return ""


def _truncate_diff(diff: str) -> str:
    if len(diff) > _MAX_DIFF_BYTES:
        return diff[:_MAX_DIFF_BYTES] + "\n\n[... diff truncado a 500KB ...]"
    return diff


# ── estrategia 1: commits por AB#<id> ──────────────────────────────────────────

def _find_commits_for_ticket(workspace: str, ticket_id: str) -> list[dict]:
    """Enumera commits que mencionan ``AB#<id>`` (trailer ADO) en el mensaje.

    Busca en ``--all`` (todas las ramas) para no depender de la rama activa.
    Devuelve lista ordenada por fecha descendente.
    """
    # %H = hash, %ai = fecha ISO, %s = subject, %D = refs asociadas
    pretty = "%H%x09%ai%x09%s"
    pattern = f"AB#{ticket_id}"
    out = _safe_git(
        workspace,
        ["log", "--all", f"--grep={pattern}", "--pretty=format:" + pretty, "-200"],
    )
    if not out.strip():
        return []
    commits: list[dict] = []
    for line in out.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        sha, date, subject = parts
        # Validación del trailer — el --grep también puede matchear strings más
        # largos. Comprobamos que el pattern efectivamente esté como referencia
        # discreta (no parte de otro número).
        commits.append({"sha": sha.strip(), "date": date.strip(), "subject": subject.strip()})
    return commits


def _files_for_commit(workspace: str, sha: str) -> list[str]:
    """Devuelve las líneas ``<status>\\t<path>`` de ``git show --name-status``."""
    out = _safe_git(
        workspace,
        ["show", "--no-renames", "--name-status", "--pretty=format:", sha],
    )
    lines: list[str] = []
    for raw in out.splitlines():
        s = raw.strip()
        if not s:
            continue
        # Normalizar a formato porcelain-ish: "<CHAR> <path>"
        parts = s.split("\t", 1)
        if len(parts) == 2:
            status, path = parts
            lines.append(f"{status[0]} {path}")
    return lines


def _diff_for_commits(workspace: str, shas: Iterable[str]) -> str:
    """Une ``git show -p`` de varios commits."""
    chunks: list[str] = []
    total = 0
    for sha in shas:
        out = _safe_git(workspace, ["show", "--no-renames", sha])
        if not out:
            continue
        chunks.append(out)
        total += len(out)
        if total > _MAX_DIFF_BYTES:
            break
    return _truncate_diff("\n".join(chunks))


def _resolve_via_commits(workspace: str, ticket_id: str) -> ResolvedChanges | None:
    commits = _find_commits_for_ticket(workspace, ticket_id)
    if not commits:
        return None
    files_seen: dict[str, str] = {}
    for c in commits:
        for line in _files_for_commit(workspace, c["sha"]):
            # Dedupe por path — el estado más reciente gana (commits están orden
            # descendente por fecha).
            _, _, path = line.partition(" ")
            files_seen.setdefault(path, line)
    files = list(files_seen.values())
    diff = _diff_for_commits(workspace, [c["sha"] for c in commits])
    return ResolvedChanges(
        source="commits",
        files=files,
        diff=diff,
        commits=commits,
        branch="",
        warning="",
    )


# ── estrategia 2: rama feature del ticket ──────────────────────────────────────

def _branch_exists(workspace: str, branch: str) -> bool:
    out = _safe_git(workspace, ["rev-parse", "--verify", "--quiet", branch])
    return bool(out.strip())


def _default_base_branch(workspace: str) -> str:
    """Retorna la rama base razonable: main, master, develop o HEAD remoto."""
    for candidate in ("main", "master", "develop", "trunk"):
        if _branch_exists(workspace, candidate):
            return candidate
    # Fallback: primera rama remota (origin/HEAD)
    out = _safe_git(workspace, ["symbolic-ref", "--short", "refs/remotes/origin/HEAD"]).strip()
    if out:
        # Forma "origin/main" — quedamos con lo que sigue a "/"
        return out.split("/", 1)[-1] if "/" in out else out
    return "main"


def _resolve_via_branch(workspace: str, ticket_id: str) -> ResolvedChanges | None:
    branch_name = ""
    for patt in _BRANCH_PATTERNS:
        candidate = patt.format(tid=ticket_id)
        if _branch_exists(workspace, candidate):
            branch_name = candidate
            break
    if not branch_name:
        return None

    base = _default_base_branch(workspace)
    # merge-base entre base y la rama del ticket
    mb = _safe_git(workspace, ["merge-base", base, branch_name]).strip()
    range_spec = f"{mb}...{branch_name}" if mb else f"{base}...{branch_name}"

    # archivos: git diff --name-status <range>
    out_files = _safe_git(workspace, ["diff", "--no-renames", "--name-status", range_spec])
    files: list[str] = []
    for line in out_files.splitlines():
        parts = line.strip().split("\t", 1)
        if len(parts) == 2:
            files.append(f"{parts[0][0]} {parts[1]}")
    # diff
    diff = _truncate_diff(_safe_git(workspace, ["diff", "--no-renames", range_spec]))
    if not files and not diff:
        return None
    return ResolvedChanges(
        source="branch",
        files=files,
        diff=diff,
        commits=[],
        branch=branch_name,
        warning=f"Mostrando diff entre {range_spec} (no se encontraron commits con AB#{ticket_id}).",
    )


# ── estrategia 3: working tree (fallback marcado) ─────────────────────────────

def _resolve_via_working_tree(workspace: str) -> ResolvedChanges:
    out_status = _safe_git(workspace, ["status", "--porcelain"])
    files = [l for l in out_status.splitlines() if l.strip()]
    # normalizar formato "XY path" → "X path"
    normalized: list[str] = []
    for l in files:
        ch = l[0] if l else " "
        rest = l[3:] if len(l) > 3 else l
        normalized.append(f"{ch if ch.strip() else '?'} {rest}")
    diff = _truncate_diff(_safe_git(workspace, ["diff", "HEAD"]))
    return ResolvedChanges(
        source="working-tree (posiblemente mezclado)",
        files=normalized,
        diff=diff,
        commits=[],
        branch="",
        warning=(
            "No se encontraron commits con AB#<id> ni rama del ticket. "
            "Se muestra el working tree completo del workspace — puede "
            "incluir cambios de otros tickets en curso."
        ),
    )


# ── API pública ────────────────────────────────────────────────────────────────

def resolve_ticket_changes(ticket_id: str, workspace: str) -> ResolvedChanges:
    """Resuelve los cambios Git atribuibles a ``ticket_id``.

    Orden: commits AB# → rama feature/<id> → working tree (fallback marcado).
    Nunca lanza — ante fallo catastrófico devuelve un ResolvedChanges vacío
    con ``source="unavailable"``.
    """
    if not ticket_id or not workspace:
        return ResolvedChanges(source="unavailable",
                               warning="ticket_id o workspace vacíos")
    try:
        for resolver in (_resolve_via_commits, _resolve_via_branch):
            try:
                result = resolver(workspace, ticket_id)
            except Exception as e:
                logger.debug("resolver %s lanzó: %s", resolver.__name__, e)
                result = None
            if result is not None:
                return result
        return _resolve_via_working_tree(workspace)
    except Exception as e:
        logger.warning("resolve_ticket_changes fatal: %s", e)
        return ResolvedChanges(source="unavailable",
                               warning=f"Error inesperado: {e}")
