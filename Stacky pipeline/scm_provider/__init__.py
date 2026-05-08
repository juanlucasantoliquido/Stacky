"""
scm_provider — Abstracción de SCM para Stacky.

Proveedores actuales:
  - git_provider.GitProvider  — implementación git (subprocess), ADO-aware

Uso:

    from scm_provider import get_scm
    scm = get_scm(project_name="RSPACIFICO")
    scm.status(workspace)
    scm.commit(workspace, "Fix #1234", files=["a.cs", "b.cs"])
    scm.push(workspace)
"""

from .base import ChangedFile, CommitResult, RepoInfo, ScmProvider
from .factory import get_scm, load_scm_config

__all__ = [
    "ScmProvider",
    "ChangedFile",
    "CommitResult",
    "RepoInfo",
    "get_scm",
    "load_scm_config",
]
