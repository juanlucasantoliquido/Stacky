"""
services/repo_writer.py — Sub-puerto RepoWriter + fábrica get_repo_writer.

Plan 73 F4 — ISP: separado de CIProvider (Plan 71/72); no importa ningún símbolo de CIProvider (C4).
La fábrica REUSA la misma resolución por tracker_type que get_tracker_provider del Plan 65 (C8).
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class RepoWriter(Protocol):
    """Puerto mínimo para commitear un archivo en el repo del tracker activo."""
    name: str

    def commit_file(self, path: str, content: str, branch: str, message: str) -> dict:
        """Crea o actualiza 'path' con 'content' en 'branch'.
        Retorna dict con keys: sha, branch, path, web_url, status.
        status: 'create' | 'update' | 'unchanged'.
        Lanza TrackerApiError en errores de red/auth (C1: no compara status; lo propaga).
        """
        ...


# Tupla de métodos que debe tener un RepoWriter (usada en tests de structural conformance)
REPO_WRITER_METHODS = ("commit_file",)


def get_repo_writer(project: Optional[str] = None) -> RepoWriter:
    """Fábrica espejo. REUSA la misma resolución por tracker_type del Plan 65
    (get_tracker_provider) para devolver el adapter del provider activo del proyecto.
    NO inventa un mecanismo de selección propio (C8)."""
    # Importado lazy para poder parchear en tests (patrón del repo)
    from services.tracker_provider import get_tracker_provider
    provider = get_tracker_provider(project=project)
    if not isinstance(provider, RepoWriter):
        raise RuntimeError(
            f"El provider '{getattr(provider, 'name', type(provider).__name__)}' "
            f"no implementa RepoWriter (falta commit_file)."
        )
    return provider
