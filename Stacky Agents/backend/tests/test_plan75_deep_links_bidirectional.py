"""Plan 75 F5 - Tests de composicion bidireccional GitLab deep links.

Verifica:
  - epic_related_links compone URLs para issues hijo, MRs y pipelines de una epica.
  - pipeline_trigger_issue_link detecta rama del patron ^issue-(digit+)(?:-|$).
  - Anti-falso-positivo (C5): refs que NO siguen el patron devuelven None.
"""
from unittest.mock import MagicMock
from services.gitlab_deep_links import epic_related_links, pipeline_trigger_issue_link


def _make_provider(flag_on: bool = True):
    """Provider mock con item_url y mr_url que devuelven URLs reales."""
    provider = MagicMock()
    if flag_on:
        provider.item_url.side_effect = lambda iid: (
            f"https://gl.example.com/rs%2Fproj/-/issues/{iid}"
        )
        provider.mr_url.side_effect = lambda iid: (
            f"https://gl.example.com/rs%2Fproj/-/merge_requests/{iid}"
        )
    else:
        provider.item_url.return_value = None
        provider.mr_url.return_value = None
    return provider


def test_f5_1_epic_related_links_composes_all_types():
    """epic_related_links con 2 issues + 1 MR + 1 pipeline -> 3 listas correctas."""
    provider = _make_provider(flag_on=True)
    result = epic_related_links(
        dest_provider=provider,
        epic_iid="99",
        child_issues=[{"iid": "10"}, {"iid": "11"}],
        mrs=[{"iid": "7"}],
        pipelines=[{"web_url": "https://gl.example.com/rs%2Fproj/-/pipelines/55"}],
    )
    assert result["issue_urls"] == [
        "https://gl.example.com/rs%2Fproj/-/issues/10",
        "https://gl.example.com/rs%2Fproj/-/issues/11",
    ]
    assert result["mr_urls"] == [
        "https://gl.example.com/rs%2Fproj/-/merge_requests/7",
    ]
    assert result["pipeline_urls"] == [
        "https://gl.example.com/rs%2Fproj/-/pipelines/55",
    ]


def test_f5_2_pipeline_trigger_issue_link_exact_ref():
    """pipeline_trigger_issue_link con ref='issue-42' -> URL issue 42."""
    provider = _make_provider(flag_on=True)
    result = pipeline_trigger_issue_link({"ref": "issue-42"}, dest_provider=provider)
    assert result == "https://gl.example.com/rs%2Fproj/-/issues/42"


def test_f5_3_pipeline_trigger_issue_link_with_suffix():
    """ref='issue-42-fix-auth' -> URL issue 42 (match parcial valido)."""
    provider = _make_provider(flag_on=True)
    result = pipeline_trigger_issue_link({"ref": "issue-42-fix-auth"}, dest_provider=provider)
    assert result == "https://gl.example.com/rs%2Fproj/-/issues/42"


def test_f5_4_pipeline_trigger_main_returns_none():
    """ref='main' -> None."""
    provider = _make_provider(flag_on=True)
    result = pipeline_trigger_issue_link({"ref": "main"}, dest_provider=provider)
    assert result is None


def test_f5_5_anti_false_positive_c5(monkeypatch):
    """Gate C5: refs que NO empiezan con 'issue-' devuelven None.

    'release-42', 'feat/42-dashboard', 'my-issue-42' -> None.
    """
    provider = _make_provider(flag_on=True)
    assert pipeline_trigger_issue_link({"ref": "release-42"}, dest_provider=provider) is None
    assert pipeline_trigger_issue_link({"ref": "feat/42-dashboard"}, dest_provider=provider) is None
    assert pipeline_trigger_issue_link({"ref": "my-issue-42"}, dest_provider=provider) is None


def test_f5_6_empty_inputs_no_error():
    """Inputs vacios -> listas vacias / None sin excepciones."""
    provider = _make_provider(flag_on=True)
    result = epic_related_links(
        dest_provider=provider,
        epic_iid="1",
        child_issues=[],
        mrs=[],
        pipelines=[],
    )
    assert result == {"issue_urls": [], "mr_urls": [], "pipeline_urls": []}

    result2 = pipeline_trigger_issue_link(None, dest_provider=provider)
    assert result2 is None

    result3 = pipeline_trigger_issue_link({}, dest_provider=provider)
    assert result3 is None
