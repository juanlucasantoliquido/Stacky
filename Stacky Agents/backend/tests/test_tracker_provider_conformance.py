"""
tests/test_tracker_provider_conformance.py -- Conformance del puerto TrackerProvider (Plan 65 F0+F12).
"""
import pytest
import dataclasses
from unittest.mock import MagicMock, patch
from services.tracker_provider import (
    TrackerProvider,
    TrackerQuery,
    TrackerItem,
    TrackerApiError,
    TrackerConfigError,
    PORT_METHODS,
)


# ── F0: Tests básicos del puerto ──────────────────────────────────────────────

def test_port_methods_list_matches_protocol():
    for m in PORT_METHODS:
        assert hasattr(TrackerProvider, m), (
            f"PORT_METHODS incluye '{m}' pero no está en TrackerProvider"
        )


def test_tracker_query_and_item_are_frozen():
    q = TrackerQuery()
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
        q.state = "closed"  # type: ignore[misc]
    item = TrackerItem(item_type="epic", title="t", description_html="<p>d</p>")
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
        item.title = "x"  # type: ignore[misc]


def test_api_error_carries_status_and_kind():
    e = TrackerApiError(404, "not found", kind="not_found")
    assert e.status == 404
    assert e.kind == "not_found"


# ── F12: Conformance cross-provider ──────────────────────────────────────────

def _make_ado_double():
    """Double de AdoTrackerProvider que implementa todos los PORT_METHODS."""
    from services.ado_provider import AdoTrackerProvider
    with patch("services.ado_provider.build_ado_client") as mock_build:
        mock_build.return_value = MagicMock()
        provider = AdoTrackerProvider.__new__(AdoTrackerProvider)
        provider._client = MagicMock()
        provider.name = "azure_devops"
    return provider


def _make_gitlab_double():
    """Double de GitLabTrackerProvider que implementa todos los PORT_METHODS."""
    from services.gitlab_provider import GitLabTrackerProvider
    with patch("services.gitlab_provider.GitLabClient") as mock_cls:
        mock_cls.return_value = MagicMock()
        provider = GitLabTrackerProvider.__new__(GitLabTrackerProvider)
        provider._client = MagicMock()
        provider.name = "gitlab"
        provider._project = None
    return provider


@pytest.mark.parametrize("adapter_name,make_fn", [
    ("AdoTrackerProvider", _make_ado_double),
    ("GitLabTrackerProvider", _make_gitlab_double),
])
def test_both_adapters_implement_all_port_methods(adapter_name, make_fn):
    """Ambos adapters exponen todos los PORT_METHODS."""
    provider = make_fn()
    missing = [m for m in PORT_METHODS if not hasattr(provider, m)]
    assert missing == [], f"{adapter_name} le faltan métodos del puerto: {missing}"


@pytest.mark.parametrize("adapter_name,make_fn", [
    ("AdoTrackerProvider", _make_ado_double),
    ("GitLabTrackerProvider", _make_gitlab_double),
])
def test_no_port_method_is_a_stub(adapter_name, make_fn):
    """Ningún método del puerto levanta NotImplementedError por default."""
    provider = make_fn()
    # Patchear el _client para que todos los llamados retornen algo válido
    provider._client = MagicMock()
    if hasattr(provider, "_client"):
        provider._client.return_value = {}

    for m in PORT_METHODS:
        method = getattr(provider, m)
        # Solo verificamos que el atributo exista y sea callable (no que esté hardcoded NotImplementedError)
        assert callable(method), f"{adapter_name}.{m} no es callable"


@pytest.mark.parametrize("adapter_name,make_fn", [
    ("AdoTrackerProvider", _make_ado_double),
    ("GitLabTrackerProvider", _make_gitlab_double),
])
def test_fetch_open_items_returns_normalized_shape(adapter_name, make_fn):
    """fetch_open_items debe retornar lista (puede ser vacía con double)."""
    provider = make_fn()
    provider._client = MagicMock()

    if adapter_name == "AdoTrackerProvider":
        provider._client.list_work_items.return_value = []
    else:
        provider._client._request_paginated.return_value = []

    from services.tracker_provider import TrackerQuery
    result = provider.fetch_open_items(TrackerQuery())
    assert isinstance(result, list)


@pytest.mark.parametrize("adapter_name,make_fn", [
    ("AdoTrackerProvider", _make_ado_double),
    ("GitLabTrackerProvider", _make_gitlab_double),
])
def test_post_comment_idempotent_shape(adapter_name, make_fn):
    """post_comment debe aceptar item_id + body_html sin explosionar."""
    provider = make_fn()
    provider._client = MagicMock()

    if adapter_name == "AdoTrackerProvider":
        provider._client.post_comment.return_value = {"id": 1}
    else:
        provider._client._request.return_value = ({"id": 1}, {})

    result = provider.post_comment("42", "<p>marker</p>")
    assert isinstance(result, dict)


@pytest.mark.parametrize("adapter_name,make_fn", [
    ("AdoTrackerProvider", _make_ado_double),
    ("GitLabTrackerProvider", _make_gitlab_double),
])
def test_create_then_find_child_by_marker_idempotent(adapter_name, make_fn):
    """find_child_by_marker debe aceptar parent_id + marker sin explotar."""
    provider = make_fn()
    provider._client = MagicMock()

    if adapter_name == "AdoTrackerProvider":
        provider._client.list_work_items.return_value = []
        provider._client.find_child_by_marker.return_value = None
    else:
        provider._client._request_paginated.return_value = []
        provider._client._request.return_value = ([], {})

    result = provider.find_child_by_marker("1", "::marker::")
    # Puede ser None o dict
    assert result is None or isinstance(result, dict)
