"""Plan 75 F2 — Tests de wiring de deep links en GitLabTrackerProvider.

Verifica:
  - item_url / mr_url / commit_url / epic_url usan compositoras de F1.
  - Todos devuelven None cuando STACKY_GITLAB_DEEP_LINKS_ENABLED=False.
  - No regresión ADO: AdoTrackerProvider.item_url sigue funcionando sin cambios.

Patrón de mock (ver plan 28 + api/ci.py:82): el flag vive en config.config (instancia
singleton), no en el módulo config. Parchear con monkeypatch.setattr(config.config, ...).
"""
import pytest
from unittest.mock import MagicMock
import config as config_module


def _make_provider():
    """Instancia GitLabTrackerProvider con client mockeado (sin __init__)."""
    from services.gitlab_provider import GitLabTrackerProvider
    provider = GitLabTrackerProvider.__new__(GitLabTrackerProvider)
    mock_client = MagicMock()
    mock_client._base_url = "https://gl.example.com"
    mock_client._project_path.return_value = "rs%2Fpacifico%2Fstrat"
    provider._client = mock_client
    provider._project = "rs/pacifico/strat"
    provider._group = "grp"
    provider._epics_native = True
    return provider


# ── Tests F2 ──────────────────────────────────────────────────────────────────

def test_f2_1_item_url_flag_on_no_double_encoding(monkeypatch):
    """Flag ON: item_url devuelve URL con encoding correcto (sin %25)."""
    monkeypatch.setattr(config_module.config, "STACKY_GITLAB_DEEP_LINKS_ENABLED", True)
    provider = _make_provider()
    result = provider.item_url("42")
    assert result == "https://gl.example.com/rs%2Fpacifico%2Fstrat/-/issues/42"
    assert "%25" not in result


def test_f2_2_mr_url_flag_on(monkeypatch):
    """Flag ON: mr_url devuelve URL MR correcta."""
    monkeypatch.setattr(config_module.config, "STACKY_GITLAB_DEEP_LINKS_ENABLED", True)
    provider = _make_provider()
    result = provider.mr_url("7")
    assert result == "https://gl.example.com/rs%2Fpacifico%2Fstrat/-/merge_requests/7"


def test_f2_3_commit_url_flag_on(monkeypatch):
    """Flag ON: commit_url devuelve URL commit correcta."""
    monkeypatch.setattr(config_module.config, "STACKY_GITLAB_DEEP_LINKS_ENABLED", True)
    provider = _make_provider()
    result = provider.commit_url("abc123")
    assert result == "https://gl.example.com/rs%2Fpacifico%2Fstrat/-/commit/abc123"


def test_f2_4_epic_url_flag_on_with_group(monkeypatch):
    """Flag ON + _group configurado: epic_url devuelve URL épica correcta."""
    monkeypatch.setattr(config_module.config, "STACKY_GITLAB_DEEP_LINKS_ENABLED", True)
    provider = _make_provider()
    result = provider.epic_url("3")
    assert result == "https://gl.example.com/groups/grp/-/epics/3"


def test_f2_5_epic_url_no_group_raises(monkeypatch):
    """Flag ON + sin _group -> TrackerConfigError."""
    from services.tracker_provider import TrackerConfigError
    monkeypatch.setattr(config_module.config, "STACKY_GITLAB_DEEP_LINKS_ENABLED", True)
    provider = _make_provider()
    provider._group = ""
    with pytest.raises(TrackerConfigError):
        provider.epic_url("3")


def test_f2_6_all_methods_return_none_when_flag_off(monkeypatch):
    """Gate C2: flag OFF -> item_url, mr_url, commit_url, epic_url devuelven None."""
    monkeypatch.setattr(config_module.config, "STACKY_GITLAB_DEEP_LINKS_ENABLED", False)
    provider = _make_provider()
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
