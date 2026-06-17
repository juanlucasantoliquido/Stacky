"""G0.1 — Gate de precondiciones determinista antes de lanzar el run.

check(ticket, runtime, project) -> PreflightResult

Predicados duros (cualquiera falla → bloquea con metadata["precondition_failure"]):
  - outputs_dir existe y es escribible
  - repo presente si el runtime lo requiere
  - PAT presente si auto-create de tasks está habilitado
  - binario/CLI del runtime resolvible

Predicados blandos → PreflightResult.warnings, no bloquean.

El gate solo corre si STACKY_RUN_PREFLIGHT_GATE_ENABLED=true.
Con flag OFF: check() devuelve ok=True siempre (byte-idéntico).
"""
from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("stacky.services.run_preflight")

# Runtimes que exigen un repo git local para operar.
_RUNTIMES_REQUIRING_REPO = {"claude_code_cli", "codex_cli"}

# Runtimes con binario explícito que debe ser resolvible.
_RUNTIME_BINS: dict[str, str] = {
    "claude_code_cli": "CLAUDE_CODE_CLI_BIN",
    "codex_cli": "CODEX_CLI_BIN",
}


@dataclass
class PreflightResult:
    ok: bool
    warnings: list[str] = field(default_factory=list)
    # Si not ok: describe el primer predicado duro fallido.
    failure_check: str | None = None
    failure_detail: str | None = None

    def to_metadata(self) -> dict[str, Any]:
        """Genera el parche de metadata['precondition_failure'] si not ok."""
        if self.ok:
            return {}
        return {
            "precondition_failure": {
                "check": self.failure_check,
                "detail": self.failure_detail,
            }
        }


def check(
    *,
    ticket: Any,
    runtime: str,
    project: str | None = None,
) -> PreflightResult:
    """Verifica precondiciones del run antes del spawn.

    Args:
        ticket: objeto Ticket (o dict con campos compatibles: .project o ["project"]).
        runtime: "claude_code_cli" | "codex_cli" | "github_copilot" | ...
        project: nombre del proyecto Stacky (override; si None se toma de ticket).

    Returns:
        PreflightResult con ok=True si todo está bien, ok=False con el check
        duro fallido si hay algún problema bloqueante.
    """
    try:
        from config import config as _config
        enabled = _config.STACKY_RUN_PREFLIGHT_GATE_ENABLED
    except Exception:  # noqa: BLE001
        enabled = os.getenv("STACKY_RUN_PREFLIGHT_GATE_ENABLED", "false").lower() in (
            "1", "true", "yes"
        )

    if not enabled:
        return PreflightResult(ok=True)

    warnings: list[str] = []

    # ── Predicado duro 1: outputs_dir existe y es escribible ──────────────────
    outputs_dir = _resolve_outputs_dir(ticket, project)
    if outputs_dir is None:
        return PreflightResult(
            ok=False,
            failure_check="outputs_dir_missing",
            failure_detail="No se pudo resolver el directorio de outputs del agente.",
        )
    if not outputs_dir.exists():
        return PreflightResult(
            ok=False,
            failure_check="outputs_dir_missing",
            failure_detail=f"outputs_dir no existe: {outputs_dir}",
        )
    if not _is_writable(outputs_dir):
        return PreflightResult(
            ok=False,
            failure_check="outputs_dir_not_writable",
            failure_detail=f"outputs_dir no es escribible: {outputs_dir}",
        )

    # ── Predicado duro 2: repo presente si el runtime lo requiere ─────────────
    if runtime in _RUNTIMES_REQUIRING_REPO:
        repo_root = _resolve_repo_root(ticket, project)
        if repo_root is None:
            return PreflightResult(
                ok=False,
                failure_check="repo_missing",
                failure_detail=(
                    f"El runtime '{runtime}' requiere un repositorio git local, "
                    "pero no se pudo resolver repo_path para el ticket/proyecto."
                ),
            )
        if not (repo_root / ".git").exists() and not _is_git_root(repo_root):
            # Advertencia blanda si existe el directorio pero sin .git
            warnings.append(f"repo_root '{repo_root}' no parece un repositorio git")

    # ── Predicado duro 3: PAT presente si auto-create está habilitado ─────────
    auto_create_on = os.getenv(
        "STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS", "true"
    ).lower() not in ("false", "0", "no", "off")
    if auto_create_on:
        ado_pat = os.getenv("ADO_PAT", "").strip()
        if not ado_pat:
            # Intentar también desde config
            try:
                from config import config as _cfg2
                ado_pat = (_cfg2.ADO_PAT or "").strip()
            except Exception:  # noqa: BLE001
                pass
        if not ado_pat:
            return PreflightResult(
                ok=False,
                failure_check="ado_pat_missing",
                failure_detail=(
                    "ADO_PAT no está configurado y el auto-create de tasks está "
                    "habilitado (STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS=true)."
                ),
            )

    # ── Predicado duro 4: binario del runtime resolvible ──────────────────────
    bin_env_key = _RUNTIME_BINS.get(runtime)
    if bin_env_key:
        bin_name = _get_runtime_bin(bin_env_key, runtime)
        if not _binary_resolvable(bin_name):
            return PreflightResult(
                ok=False,
                failure_check="runtime_binary_missing",
                failure_detail=f"Binario del runtime '{runtime}' no resolvible: '{bin_name}'",
            )

    return PreflightResult(ok=True, warnings=warnings)


# ── Helpers privados ──────────────────────────────────────────────────────────


def _resolve_outputs_dir(ticket: Any, project: str | None) -> Path | None:
    """Intenta resolver el directorio de outputs del agente."""
    # Desde ticket.project_config o rutas conocidas del operador.
    try:
        from runtime_paths import data_dir
        # El operador almacena outputs bajo data_dir o una ruta de proyecto.
        # Si el ticket trae un project_path, usarlo; sino fallback a data_dir.
        proj = _ticket_project(ticket, project)
        if proj:
            try:
                from project_manager import get_project_config
                cfg = get_project_config(proj) or {}
                outputs = cfg.get("outputs_dir") or cfg.get("output_dir") or ""
                if outputs:
                    return Path(outputs).expanduser()
            except Exception:  # noqa: BLE001
                pass
        return data_dir()
    except Exception:  # noqa: BLE001
        pass
    # Fallback: directorio de trabajo actual.
    return Path.cwd()


def _resolve_repo_root(ticket: Any, project: str | None) -> Path | None:
    """Intenta resolver el repo_path del proyecto."""
    try:
        proj = _ticket_project(ticket, project)
        if proj:
            from project_manager import get_project_config
            cfg = get_project_config(proj) or {}
            repo = cfg.get("repo_path") or cfg.get("repo") or ""
            if repo:
                return Path(repo).expanduser()
    except Exception:  # noqa: BLE001
        pass
    return None


def _ticket_project(ticket: Any, override: str | None) -> str | None:
    if override:
        return override
    if ticket is None:
        return None
    if hasattr(ticket, "project"):
        return ticket.project
    if isinstance(ticket, dict):
        return ticket.get("project")
    return None


def _is_writable(path: Path) -> bool:
    return os.access(path, os.W_OK)


def _is_git_root(path: Path) -> bool:
    """Verifica .git en el directorio o como archivo (worktree)."""
    git_entry = path / ".git"
    return git_entry.exists()


def _get_runtime_bin(env_key: str, runtime: str) -> str:
    """Obtiene el nombre del binario desde config o env."""
    try:
        from config import config as _cfg
        val = getattr(_cfg, env_key, None)
        if val:
            return str(val)
    except Exception:  # noqa: BLE001
        pass
    defaults = {"CLAUDE_CODE_CLI_BIN": "claude", "CODEX_CLI_BIN": "codex"}
    return os.getenv(env_key, defaults.get(env_key, runtime))


def _binary_resolvable(bin_name: str) -> bool:
    """True si el binario existe en PATH o como ruta absoluta."""
    if os.path.isabs(bin_name):
        return Path(bin_name).is_file()
    return shutil.which(bin_name) is not None
