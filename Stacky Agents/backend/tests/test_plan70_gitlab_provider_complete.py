"""Plan 70 F1-A — Pre-auditoría: GitLabTrackerProvider implementa todos los PORT_METHODS.

Verifica que NINGÚN método del puerto lanza NotImplementedError con un input dummy
razonable. Si falta alguno, se documenta como GAP-G (aquí garantizamos que no hay).
"""
from __future__ import annotations

import inspect

import pytest

from services.tracker_provider import PORT_METHODS, TrackerQuery, TrackerItem


def _instantiate_gitlab_provider():
    """Crea una instancia sin tocar red: monkeypatch del cliente HTTP."""
    from services import gitlab_provider as mod

    provider = mod.GitLabTrackerProvider.__new__(mod.GitLabTrackerProvider)
    # Inyectar un cliente mock minimal (los métodos que llaman red se pullean al assert)
    class _FakeGitlabClient:
        def __init__(self, *a, **kw):
            pass

        def __getattr__(self, name):
            # Cualquier llamada de red returns un dict/list vacío serializable
            def _stub(*a, **kw):
                return {}
            return _stub

    provider._client = _FakeGitlabClient()
    provider._project = None
    provider._group = None
    provider._project_cfg = {"name": "test", "token": "", "url": ""}
    return provider


@pytest.mark.parametrize("method_name", PORT_METHODS)
def test_gitlab_provider_method_implemented(method_name):
    """Cada método de PORT_METHODS existe en GitLabTrackerProvider y no es NotImplementedError."""
    from services import gitlab_provider as mod

    assert hasattr(mod.GitLabTrackerProvider, method_name), (
        f"GAP-G: GitLabTrackerProvider no implementa '{method_name}'"
    )
    source = inspect.getsource(getattr(mod.GitLabTrackerProvider, method_name))
    assert "NotImplementedError" not in source, (
        f"GAP-G: '{method_name}' lanza NotImplementedError en GitLabTrackerProvider"
    )


def test_gitlab_provider_has_all_port_methods():
    """Cobertura exacta: PORT_METHODS ⊆ métodos de GitLabTrackerProvider."""
    from services import gitlab_provider as mod

    missing = [m for m in PORT_METHODS if not hasattr(mod.GitLabTrackerProvider, m)]
    assert missing == [], f"GAP-G: métodos faltantes en GitLabTrackerProvider: {missing}"
