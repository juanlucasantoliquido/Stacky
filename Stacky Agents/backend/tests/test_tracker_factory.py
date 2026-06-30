"""
tests/test_tracker_factory.py -- Tests de la fábrica get_tracker_provider (Plan 65 F10).
"""
import pytest
from unittest.mock import MagicMock, patch

from services.tracker_provider import TrackerConfigError


def _make_ctx(tracker_type="azure_devops"):
    ctx = MagicMock()
    ctx.tracker_type = tracker_type
    ctx.organization = "myorg"
    ctx.tracker_project = "myproject"
    ctx.auth_path = "/fake/auth"
    ctx.stacky_project_name = "myproject"
    ctx.workspace_root = "/fake/workspace"
    return ctx


def test_factory_defaults_to_ado():
    """Sin issue_tracker.type → retorna AdoTrackerProvider."""
    from services.tracker_provider import get_tracker_provider
    from services.ado_provider import AdoTrackerProvider

    ctx = _make_ctx("azure_devops")

    with patch("services.tracker_provider.resolve_project_context", return_value=ctx), \
         patch("services.ado_provider.build_ado_client") as mock_build:
        mock_build.return_value = MagicMock()
        provider = get_tracker_provider(project="myproject")

    assert isinstance(provider, AdoTrackerProvider)


def test_factory_returns_gitlab_when_type_and_enabled():
    """issue_tracker.type=gitlab + STACKY_GITLAB_ENABLED=true → GitLabTrackerProvider."""
    from services.tracker_provider import get_tracker_provider
    from services.gitlab_provider import GitLabTrackerProvider

    ctx = _make_ctx("gitlab")

    with patch("services.tracker_provider.resolve_project_context", return_value=ctx), \
         patch("services.tracker_provider.config") as mock_cfg, \
         patch("services.gitlab_provider.GitLabClient") as mock_gl_cls, \
         patch("services.gitlab_provider.config") as mock_gl_cfg:
        mock_cfg.STACKY_GITLAB_ENABLED = True
        mock_gl_cfg.GITLAB_URL = "https://gl.example.com"
        mock_gl_cfg.GITLAB_PROJECT = "proj"
        mock_gl_cfg.STACKY_GITLAB_GROUP = ""
        mock_gl_cfg.STACKY_GITLAB_EPICS_NATIVE = False
        mock_client = MagicMock()
        mock_client._token = "tok"
        mock_gl_cls.return_value = mock_client

        provider = get_tracker_provider(project="myproject")

    assert isinstance(provider, GitLabTrackerProvider)


def test_factory_raises_when_gitlab_disabled():
    """issue_tracker.type=gitlab + STACKY_GITLAB_ENABLED=false → TrackerConfigError."""
    from services.tracker_provider import get_tracker_provider

    ctx = _make_ctx("gitlab")

    with patch("services.tracker_provider.resolve_project_context", return_value=ctx), \
         patch("services.tracker_provider.config") as mock_cfg:
        mock_cfg.STACKY_GITLAB_ENABLED = False
        with pytest.raises(TrackerConfigError, match="STACKY_GITLAB_ENABLED=false"):
            get_tracker_provider(project="myproject")


def test_factory_raises_for_jira_mantis():
    """Tipos jira/mantis no tienen puerto formal → TrackerConfigError."""
    from services.tracker_provider import get_tracker_provider

    for tracker_type in ("jira", "mantis"):
        ctx = _make_ctx(tracker_type)
        with patch("services.tracker_provider.resolve_project_context", return_value=ctx), \
             patch("services.tracker_provider.config"):
            with pytest.raises(TrackerConfigError, match="sin puerto formal"):
                get_tracker_provider()
