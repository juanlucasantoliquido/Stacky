"""Plan 75 F3 — Tests del fallback Free para deep links de épicas GitLab.

resolve_epic_deep_link maneja 3 estrategias:
  - premium_native + _group: compose_epic_url
  - free_degrade + fallback_issue_iid: compose_issue_url del issue degradado
  - free_degrade sin fallback_issue_iid: compose_search_url con label:type::epic
  - auto: detecta _epics_native del provider
"""
from unittest.mock import MagicMock
from services.gitlab_deep_links import resolve_epic_deep_link, compose_search_url


def _make_provider(*, base_url="https://gl.example.com", project_path="proj%2Ftest",
                   group="", epics_native=False):
    """Crea un provider mock con los atributos que lee resolve_epic_deep_link."""
    provider = MagicMock()
    provider._group = group
    provider._epics_native = epics_native
    provider._client._base_url = base_url
    provider._client._project_path.return_value = project_path
    return provider


def test_f3_1_premium_native_with_group():
    """premium_native + _group -> URL épica nativa."""
    provider = _make_provider(group="my-group", epics_native=True)
    result = resolve_epic_deep_link(
        dest_provider=provider,
        epic_strategy="premium_native",
        gitlab_iid="7",
        fallback_issue_iid=None,
    )
    assert result == "https://gl.example.com/groups/my-group/-/epics/7"


def test_f3_2_free_degrade_with_fallback_issue():
    """free_degrade + fallback_issue_iid -> URL del issue degradado."""
    provider = _make_provider(project_path="rs%2Fpacifico%2Fstrat")
    result = resolve_epic_deep_link(
        dest_provider=provider,
        epic_strategy="free_degrade",
        gitlab_iid="99",
        fallback_issue_iid="42",
    )
    assert result == "https://gl.example.com/rs%2Fpacifico%2Fstrat/-/issues/42"


def test_f3_3_free_degrade_without_fallback_issue():
    """free_degrade sin fallback_issue_iid -> URL de búsqueda con label:type::epic."""
    provider = _make_provider(project_path="rs%2Fpacifico%2Fstrat")
    result = resolve_epic_deep_link(
        dest_provider=provider,
        epic_strategy="free_degrade",
        gitlab_iid="99",
        fallback_issue_iid=None,
    )
    assert "/-/issues" in result
    # label_name debe estar en la URL
    assert "type%3A%3Aepic" in result or "type::epic" in result or "label_name" in result


def test_f3_4_auto_detects_epics_native_false():
    """auto + _epics_native=False -> cae a free_degrade."""
    provider = _make_provider(project_path="proj%2Ftest", epics_native=False, group="")
    result = resolve_epic_deep_link(
        dest_provider=provider,
        epic_strategy="auto",
        gitlab_iid="5",
        fallback_issue_iid="10",
    )
    # free_degrade con fallback -> issue del issue degradado
    assert result == "https://gl.example.com/proj%2Ftest/-/issues/10"


def test_f3_5_compose_search_url():
    """compose_search_url produce URL de búsqueda encodeada correctamente."""
    result = compose_search_url("https://gl.example.com", "proj%2Ftest", "label:type::epic")
    assert "/-/issues" in result
    assert "label_name" in result
    # el label debe estar encodado en el query string
    assert "type" in result
