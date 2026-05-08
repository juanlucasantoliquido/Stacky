"""
scm_provider.base — ABC para proveedores de control de fuentes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ChangedFile:
    """Un archivo con cambios locales pendientes."""
    path: str                     # ruta relativa al workspace
    status: str                   # "M" modified, "A" added, "D" deleted, "?" untracked
    summary: str = ""             # descripción humana opcional


@dataclass
class CommitResult:
    """Resultado de un commit."""
    ok: bool
    revision: str = ""            # hash del commit
    message: str = ""
    files: list[str] = field(default_factory=list)
    error: str = ""


@dataclass
class RepoInfo:
    """Metadata del repo en el workspace."""
    kind: str = ""                # "git"
    url: str = ""                 # remote url / repository URL
    branch: str = ""              # git branch
    revision: str = ""            # commit hash
    workspace: str = ""           # path absoluto


class ScmProvider(ABC):
    """
    Contrato mínimo que debe cumplir cualquier SCM usado por Stacky.
    Todas las operaciones son síncronas y usan subprocess por debajo.
    """

    name: str = ""

    def __init__(self, config: dict | None = None):
        self._config = config or {}

    @abstractmethod
    def is_available(self, workspace: str) -> tuple[bool, str]:
        """(True,'') si hay binario y el workspace es un repo válido."""

    @abstractmethod
    def info(self, workspace: str) -> RepoInfo:
        """Información del repo."""

    @abstractmethod
    def status(self, workspace: str) -> list[ChangedFile]:
        """Cambios locales pendientes."""

    @abstractmethod
    def diff(self, workspace: str, full: bool = False, paths: list[str] | None = None) -> str:
        """Diff de cambios locales."""

    @abstractmethod
    def add(self, workspace: str, paths: list[str]) -> tuple[bool, str]:
        """Agrega archivos al staging (git add). Devuelve (ok, error_stderr)."""

    @abstractmethod
    def commit(
        self,
        workspace: str,
        message: str,
        files: list[str] | None = None,
    ) -> CommitResult:
        """Commit atómico. Si `files` es None, incluye todo lo staged."""

    def push(self, workspace: str, remote: str = "origin",
             branch: str | None = None) -> tuple[bool, str]:
        """Push al remoto (solo Git). Default: no-op para SCMs sin remoto."""
        return True, ""

    def log(self, workspace: str, limit: int = 10) -> list[dict]:
        """Historial de commits. Default vacío."""
        return []

    def current_branch(self, workspace: str) -> str:
        """Default: vacío para SCMs sin ramas."""
        return ""
