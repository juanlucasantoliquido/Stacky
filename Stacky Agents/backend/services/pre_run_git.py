from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from config import config

# Contención del pre-run git: solo el fetch/merge toca .git/index.lock. Usamos
# un lock por-repo (en proceso; el backend es un único proceso multihilo) y un
# cache corto del último fetch (keyed por HEAD) para que la 2ª ejecución reuse
# en vez de errorear o colgar.
_FETCH_REUSE_WINDOW_SECONDS = 30.0
_repo_locks: dict[str, threading.Lock] = {}
_repo_locks_guard = threading.Lock()
_recent_fetch: dict[str, tuple[str, list, float]] = {}


def _repo_lock(repo_root: str) -> threading.Lock:
    with _repo_locks_guard:
        lock = _repo_locks.get(repo_root)
        if lock is None:
            lock = threading.Lock()
            _repo_locks[repo_root] = lock
        return lock


@dataclass
class GitStep:
    name: str
    ok: bool
    command: list[str]
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    skipped: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "ok": self.ok,
            "command": self.command,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": self.duration_ms,
            "skipped": self.skipped,
        }


@dataclass
class PullCheckResult:
    ok: bool
    enabled: bool
    required: bool
    policy: str
    workspace_root: str | None
    repo_root: str | None = None
    branch: str | None = None
    upstream: str | None = None
    dirty: bool = False
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    steps: list[GitStep] = field(default_factory=list)
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "enabled": self.enabled,
            "required": self.required,
            "policy": self.policy,
            "workspace_root": self.workspace_root,
            "repo_root": self.repo_root,
            "branch": self.branch,
            "upstream": self.upstream,
            "dirty": self.dirty,
            "warnings": self.warnings,
            "errors": self.errors,
            "steps": [s.to_dict() for s in self.steps],
            "duration_ms": self.duration_ms,
        }


def run_pull_check(
    workspace_root: str | None,
    *,
    enabled: bool | None = None,
    required: bool | None = None,
    fetch: bool | None = None,
    timeout_seconds: int | None = None,
    project: str | None = None,
    auth_header: str | None = None,
    log: Callable[[str, str], None] | None = None,
) -> PullCheckResult:
    started = time.monotonic()
    enabled = config.STACKY_PRE_RUN_GIT_PULL_ENABLED if enabled is None else bool(enabled)
    required = config.STACKY_PRE_RUN_GIT_PULL_REQUIRED if required is None else bool(required)
    policy = config.STACKY_PRE_RUN_GIT_WORKSPACE_POLICY or "fetch_only_warn"
    timeout_seconds = timeout_seconds or config.STACKY_PRE_RUN_GIT_TIMEOUT_SECONDS
    should_fetch = enabled if fetch is None else bool(fetch)
    # Auth ADO no interactiva para las ops de red (reusa el PAT DPAPI vía
    # ado_client). Sin esto, un fetch contra un repo ADO privado fallaría/colgaría.
    if auth_header is None and project:
        auth_header = _resolve_auth_header_for_project(project)

    result = PullCheckResult(
        ok=True,
        enabled=enabled,
        required=required,
        policy=policy,
        workspace_root=workspace_root,
    )

    if not workspace_root:
        result.warnings.append("workspace_root no configurado; se omite pre-run git")
        return _finish(result, started)

    cwd = Path(workspace_root).expanduser()
    if not cwd.exists():
        result.ok = not required
        result.errors.append(f"workspace_root no existe: {cwd}") if required else result.warnings.append(
            f"workspace_root no existe: {cwd}"
        )
        return _finish(result, started)

    def emit(level: str, message: str) -> None:
        if log is not None:
            log(level, message)

    show_top = _run_git(cwd, ["rev-parse", "--show-toplevel"], timeout_seconds)
    result.steps.append(show_top)
    if not show_top.ok:
        if required:
            result.errors.append("workspace no es un repositorio git")
            result.ok = False
        else:
            result.warnings.append("workspace no es un repositorio git")
        return _finish(result, started)
    result.repo_root = show_top.stdout.strip()
    repo = Path(result.repo_root)
    emit("info", f"git repo: {result.repo_root}")

    branch = _run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"], timeout_seconds)
    result.steps.append(branch)
    if branch.ok:
        result.branch = branch.stdout.strip()
    else:
        result.warnings.append("no se pudo resolver branch actual")

    upstream = _run_git(repo, ["rev-parse", "--abbrev-ref", "@{u}"], timeout_seconds)
    result.steps.append(upstream)
    if upstream.ok:
        result.upstream = upstream.stdout.strip()
    else:
        result.warnings.append("branch sin upstream configurado")
        if required and policy == "ff_only_block_on_dirty":
            result.ok = False
            result.errors.append("branch sin upstream y pre-run requerido")
            return _finish(result, started)

    status = _run_git(repo, ["status", "--porcelain"], timeout_seconds)
    result.steps.append(status)
    if status.ok:
        result.dirty = bool(status.stdout.strip())
        if result.dirty:
            result.warnings.append("working tree sucio")
            if required and policy == "ff_only_block_on_dirty":
                result.ok = False
                result.errors.append("working tree sucio y policy bloqueante")
                return _finish(result, started)
    else:
        result.warnings.append("no se pudo leer git status")

    if not should_fetch:
        result.steps.append(
            GitStep(
                name="fetch",
                ok=True,
                command=["git", "fetch", "--prune"],
                skipped=True,
                stdout="fetch omitido: STACKY_PRE_RUN_GIT_PULL_ENABLED=false",
            )
        )
        return _finish(result, started)

    # Solo el fetch/merge necesita exclusión mutua (toca .git/index.lock). Los
    # pasos read-only previos no. Esperamos el lock hasta lock_wait; si no se
    # obtiene, reusamos un fetch reciente (mismo HEAD, ventana ~30s) o lo
    # omitimos de forma no bloqueante en vez de errorear.
    head_step = _run_git(repo, ["rev-parse", "HEAD"], timeout_seconds)
    head_sha = head_step.stdout.strip() if head_step.ok else ""

    lock = _repo_lock(result.repo_root)
    lock_wait = max(0.0, float(config.STACKY_PRE_RUN_GIT_LOCK_WAIT_SECONDS))
    if not lock.acquire(timeout=lock_wait):
        cached = _recent_fetch.get(result.repo_root)
        if (
            cached
            and cached[0] == head_sha
            and (time.monotonic() - cached[2]) <= _FETCH_REUSE_WINDOW_SECONDS
        ):
            result.warnings.append(
                "otra ejecución está actualizando el workspace; se reusa el fetch reciente"
            )
            result.steps.extend(cached[1])
        else:
            result.warnings.append(
                "pre-run git ocupado por otra ejecución; fetch omitido (no bloqueante)"
            )
        return _finish(result, started)

    fetch_steps: list[GitStep] = []
    try:
        _recover_stale_git_locks(repo, timeout_seconds)

        fetch_step = _run_git(repo, ["fetch", "--prune"], timeout_seconds, auth_header=auth_header)
        fetch_steps.append(fetch_step)
        result.steps.append(fetch_step)
        if not fetch_step.ok:
            msg = "git fetch --prune fallo en modo no interactivo"
            result.warnings.append(msg)
            if required:
                result.ok = False
                result.errors.append(msg)
                return _finish(result, started)

        if policy == "ff_only_block_on_dirty" and result.upstream:
            merge_step = _run_git(repo, ["merge", "--ff-only", "@{u}"], timeout_seconds, auth_header=auth_header)
            fetch_steps.append(merge_step)
            result.steps.append(merge_step)
            if not merge_step.ok:
                msg = "git merge --ff-only fallo"
                result.warnings.append(msg)
                if required:
                    result.ok = False
                    result.errors.append(msg)
    finally:
        _recent_fetch[result.repo_root] = (head_sha, fetch_steps, time.monotonic())
        lock.release()

    return _finish(result, started)


def _run_git(
    cwd: Path,
    args: list[str],
    timeout_seconds: int,
    *,
    auth_header: str | None = None,
) -> GitStep:
    # `-c credential.helper=` SIEMPRE (deshabilita GCM aunque no haya PAT, así no
    # cuelga en un prompt) y `-c core.longpaths=true` (rutas profundas en Windows).
    # El PAT va por `http.extraheader` solo si hay auth_header (ops de red).
    config_args = ["-c", "credential.helper=", "-c", "core.longpaths=true"]
    if auth_header:
        config_args += ["-c", f"http.extraheader=Authorization: {auth_header}"]
    cmd = ["git", *config_args, *args]
    logged_cmd = _redact_command(cmd)
    started = time.monotonic()
    env = os.environ.copy()
    env.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "Never",
            "GIT_ASKPASS": "",
            "SSH_ASKPASS": "",
        }
    )
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        return GitStep(
            name=args[0],
            ok=proc.returncode == 0,
            command=logged_cmd,
            stdout=(proc.stdout or "").strip(),
            stderr=(proc.stderr or "").strip(),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except subprocess.TimeoutExpired as exc:
        return GitStep(
            name=args[0],
            ok=False,
            command=logged_cmd,
            stdout=(exc.stdout or "").strip() if isinstance(exc.stdout, str) else "",
            stderr=f"timeout after {timeout_seconds}s",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except OSError as exc:
        return GitStep(
            name=args[0],
            ok=False,
            command=logged_cmd,
            stderr=str(exc),
            duration_ms=int((time.monotonic() - started) * 1000),
        )


def _redact_command(cmd: list[str]) -> list[str]:
    """Enmascara el valor de http.extraheader para no filtrar el PAT a logs/SSE."""
    out: list[str] = []
    for part in cmd:
        if part.startswith("http.extraheader=Authorization:"):
            out.append("http.extraheader=Authorization: <redacted>")
        else:
            out.append(part)
    return out


def _recover_stale_git_locks(repo: Path, timeout_seconds: int) -> None:
    """Best-effort: limpia lockfiles git stale y poda worktrees colgados.

    En Windows no hay un check de PID confiable cross-process, así que tratamos
    como stale los lockfiles cuya antigüedad supera el timeout de la operación
    (un git real ya habría terminado o expirado). Se corre con el lock por-repo
    tomado, así no compite con otro fetch de este mismo proceso. Nunca levanta
    excepción: el recovery no debe romper el pre-run.
    """
    try:
        git_dir = repo / ".git"
        if not git_dir.is_dir():
            return
        cutoff = max(int(timeout_seconds), 1)
        now = time.time()
        for name in ("index.lock", "HEAD.lock"):
            lock_path = git_dir / name
            try:
                if lock_path.exists() and (now - lock_path.stat().st_mtime) > cutoff:
                    lock_path.unlink()
            except OSError:
                pass
        _run_git(repo, ["worktree", "prune"], timeout_seconds)
    except Exception:  # noqa: BLE001
        pass


def _resolve_auth_header_for_project(project: str) -> str | None:
    """Resuelve el header Basic del PAT DPAPI del proyecto (no interactivo).

    Mismo patrón que memory_git_sync; se mantiene local para no acoplar Fase C
    con Fase E. Cualquier fallo degrada a None (fetch sin PAT, pero siempre con
    credential.helper= vacío → no cuelga).
    """
    try:
        from services.ado_client import _resolve_auth_header
        from services.project_context import resolve_project_context

        ctx = resolve_project_context(project_name=project)
        return _resolve_auth_header(ctx.auth_path if ctx else None)
    except Exception:  # noqa: BLE001
        return None


def _finish(result: PullCheckResult, started: float) -> PullCheckResult:
    result.duration_ms = int((time.monotonic() - started) * 1000)
    if result.errors:
        result.ok = False
    return result
