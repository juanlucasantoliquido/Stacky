"""Plan 75 F2 — Tests de wiring de deep links en GitLabTrackerProvider.

Verifica:
  - item_url / mr_url / commit_url / epic_url usan compositoras de F1.
  - Todos devuelven None cuando STACKY_GITLAB_DEEP_LINKS_ENABLED=False.
  - No regresión ADO: AdoTrackerProvider.item_url sigue sin cambios.
"""
import pytest
from unittest.mock import MagicMock, patch


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_provider(flag_on: bool = True, group: str = "grp"):
    """Instancia GitLabTrackerProvider con client mockeado."""
    from services.gitlab_provider import GitLabTrackerProvider
    import services.gitlab_provider as gp_module

    provider = GitLabTrackerProvider.__new__(GitLabTrackerProvider)
    mock_client = MagicMock()
    mock_client._base_url = "https://gl.example.com"
    mock_client._project_path.return_value = "rs%2Fpacifico%2Fstrat"
    provider._client = mock_client
    provider._project = "rs/pacifico/strat"
    provider._group = group
    provider._epics_native = bool(group)

    # Parchear config en el módulo del provider
    with patch.object(gp_module.config, "STACKY_GITLAB_DEEP_LINKS_ENABLED", flag_on):
        yield provider, gp_module


# ── Tests F2 ──────────────────────────────────────────────────────────────────

def test_f2_1_item_url_flag_on_no_double_encoding():
    """Flag ON: item_url devuelve URL con encoding correcto (sin %25)."""
    from services.gitlab_provider import GitLabTrackerProvider
    import services.gitlab_provider as gp_module

    provider = GitLabTrackerProvider.__new__(GitLabTrackerProvider)
    mock_client = MagicMock()
    mock_client._base_url = "https://gl.example.com"
    mock_client._project_path.return_value = "rs%2Fpacifico%2Fstrat"
    provider._client = mock_client
    provider._project = "rs/pacifico/strat"
    provider._group = "grp"
    provider._epics_native = True

    with patch.object(gp_module.config, "STACKY_GITLAB_DEEP_LINKS_ENABLED", True):
        result = provider.item_url("42")

    assert result == "https://gl.example.com/rs%2Fpacifico%2Fstrat/-/issues/42"
    assert "%25" not in result


def test_f2_2_mr_url_flag_on():
    """Flag ON: mr_url devuelve URL MR correcta."""
    from services.gitlab_provider import GitLabTrackerProvider
    import services.gitlab_provider as gp_module

    provider = GitLabTrackerProvider.__new__(GitLabTrackerProvider)
    mock_client = MagicMock()
    mock_client._base_url = "https://gl.example.com"
    mock_client._project_path.return_value = "rs%2Fpacifico%2Fstrat"
    provider._client = mock_client
    provider._group = "grp"

    with patch.object(gp_module.config, "STACKY_GITLAB_DEEP_LINKS_ENABLED", True):
        result = provider.mr_url("7")

    assert result == "https://gl.example.com/rs%2Fpacifico%2Fstrat/-/merge_requests/7"


def test_f2_3_commit_url_flag_on():
    """Flag ON: commit_url devuelve URL commit correcta."""
    from services.gitlab_provider import GitLabTrackerProvider
    import services.gitlab_provider as gp_module

    provider = GitLabTrackerProvider.__new__(GitLabTrackerProvider)
    mock_client = MagicMock()
    mock_client._base_url = "https://gl.example.com"
    mock_client._project_path.return_value = "rs%2Fpacifico%2Fstrat"
    provider._client = mock_client
    provider._group = "grp"

    with patch.object(gp_module.config, "STACKY_GITLAB_DEEP_LINKS_ENABLED", True):
        result = provider.commit_url("abc123")

    assert result == "https://gl.example.com/rs%2Fpacifico%2Fstrat/-/commit/abc123"


def test_f2_4_epic_url_flag_on_with_group():
    """Flag ON + _group configurado: epic_url devuelve URL épica correcta."""
    from services.gitlab_provider import GitLabTrackerProvider
    import services.gitlab_provider as gp_module

    provider = GitLabTrackerProvider.__new__(GitLabTrackerProvider)
    mock_client = MagicMock()
    mock_client._base_url = "https://gl.example.com"
    mock_client._project_path.return_value = "rs%2Fpacifico%2Fstrat"
    provider._client = mock_client
    provider._group = "grp"

    with patch.object(gp_module.config, "STACKY_GITLAB_DEEP_LINKS_ENABLED", True):
        result = provider.epic_url("3")

    assert result == "https://gl.example.com/groups/grp/-/epics/3"


def test_f2_5_epic_url_no_group_raises():
    """Flag ON + sin _group → TrackerConfigError."""
    from services.gitlab_provider import GitLabTrackerProvider
    from services.tracker_provider import TrackerConfigError
    import services.gitlab_provider as gp_module

    provider = GitLabTrackerProvider.__new__(GitLabTrackerProvider)
    mock_client = MagicMock()
    mock_client._base_url = "https://gl.example.com"
    mock_client._project_path.return_value = "proj"
    provider._client = mock_client
    provider._group = ""

    with patch.object(gp_module.config, "STACKY_GITLAB_DEEP_LINKS_ENABLED", True):
        with pytest.raises(TrackerConfigError):
            provider.epic_url("3")


def test_f2_6_all_methods_return_none_when_flag_off():
    """Gate C2: flag OFF → item_url, mr_url, commit_url, epic_url devuelven None."""
    from services.gitlab_provider import GitLabTrackerProvider
    import services.gitlab_provider as gp_module

    provider = GitLabTrackerProvider.__new__(GitLabTrackerProvider)
    mock_client = MagicMock()
    mock_client._base_url = "https://gl.example.com"
    mock_client._project_path.return_value = "proj"
    provider._client = mock_client
    provider._group = "grp"

    with patch.object(gp_module.config, "STACKY_GITLAB_DEEP_LINKS_ENABLED", False):
        assert provider.item_url("1") is None
        assert provider.mr_url("1") is None
        assert provider.commit_url("abc") is None
        assert provider.epic_url("1") is None


def test_f2_7_ado_provider_item_url_no_regression():
    """No regresión ADO: AdoTrackerProvider.item_url sigue funcionando sin cambios."""
    from services.ado_provider import AdoTrackerProvider

    provider = AdoTrackerProvider.__new__(AdoTrackerProvider)
    mock_client = MagicMock()
    mock_client.org = "UbimiaPacifico"
    mock_client.project = "Strategist_Pacifico"
    provider._client = mock_client

    result = provider.item_url("42")
    assert "dev.azure.com" in result
    assert "42" in result
    assert not hasattr(provider, "STACKY_GITLAB_DEEP_LINKS_ENABLED")
