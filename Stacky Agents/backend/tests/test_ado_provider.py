"""
tests/test_ado_provider.py -- Tests del adapter AdoTrackerProvider (Plan 65 F1).
"""
import pytest
from unittest.mock import MagicMock, patch
from services.tracker_provider import TrackerItem, TrackerQuery, PORT_METHODS


def _make_provider():
    """Crea AdoTrackerProvider con AdoClient completamente mockeado."""
    from services.ado_provider import AdoTrackerProvider
    # build_ado_client se importa a nivel módulo en ado_provider → parchear ahí
    with patch("services.ado_provider.build_ado_client") as mock_build:
        mock_client = MagicMock()
        mock_client.org = "myorg"
        mock_client.project = "myproject"
        mock_build.return_value = mock_client
        provider = AdoTrackerProvider(project="myproject")
        # Asegurar que el cliente quede mockeado tras salir del context manager
        return provider, mock_client


def test_ado_provider_is_tracker_provider():
    """AdoTrackerProvider implementa todos los PORT_METHODS."""
    provider, _ = _make_provider()
    missing = [m for m in PORT_METHODS if not hasattr(provider, m)]
    assert missing == [], f"Faltan métodos: {missing}"
    assert provider.name == "azure_devops"


def test_create_item_maps_type_and_fields():
    """TrackerItem con item_type 'epic' → create_work_item con type 'Epic'."""
    provider, mock_client = _make_provider()
    mock_client.create_work_item.return_value = {"id": 100}

    item = TrackerItem(
        item_type="epic",
        title="Mi Épica",
        description_html="<p>desc</p>",
        fields={"System.Tags": "tag1"},
    )
    result = provider.create_item(item)

    mock_client.create_work_item.assert_called_once()
    call_kwargs = mock_client.create_work_item.call_args
    assert call_kwargs.kwargs.get("work_item_type") == "Epic"
    assert call_kwargs.kwargs.get("title") == "Mi Épica"
    assert result == {"id": 100}


def test_create_item_maps_story_type():
    """item_type='story' → 'User Story'."""
    provider, mock_client = _make_provider()
    mock_client.create_work_item.return_value = {"id": 200}
    item = TrackerItem(item_type="story", title="US", description_html="<p>d</p>")
    provider.create_item(item)
    call_kwargs = mock_client.create_work_item.call_args
    assert call_kwargs.kwargs.get("work_item_type") == "User Story"


def test_post_comment_delegates_unchanged():
    """post_comment pasa el body_html sin modificar."""
    provider, mock_client = _make_provider()
    mock_client.post_comment.return_value = {"id": 5}

    result = provider.post_comment("42", "<p>marker::abc</p>")

    mock_client.post_comment.assert_called_once_with(42, "<p>marker::abc</p>")
    assert result == {"id": 5}


def test_fetch_item_updates_delegates_id_as_int():
    """fetch_item_updates castea item_id str → int."""
    provider, mock_client = _make_provider()
    mock_client.fetch_work_item_updates.return_value = [
        {"revisedDate": "2026-01-01", "rev": 1},
        {"revisedDate": "2026-06-01", "rev": 2},
    ]

    result = provider.fetch_item_updates("99")

    mock_client.fetch_work_item_updates.assert_called_once_with(99)
    assert len(result) == 2


def test_fetch_item_updates_filters_by_since():
    """fetch_item_updates filtra por since cuando se provee."""
    provider, mock_client = _make_provider()
    mock_client.fetch_work_item_updates.return_value = [
        {"revisedDate": "2026-01-01", "rev": 1},
        {"revisedDate": "2026-06-15", "rev": 2},
    ]

    result = provider.fetch_item_updates("99", since="2026-06-01")

    assert len(result) == 1
    assert result[0]["rev"] == 2


def test_item_url_constructs_ado_url():
    """item_url construye la URL de ADO correctamente."""
    provider, _ = _make_provider()
    url = provider.item_url("123")
    assert "myorg" in url
    assert "myproject" in url
    assert "123" in url


def test_comment_exists_returns_bool():
    """comment_exists devuelve True cuando el cliente retorna un dict."""
    provider, mock_client = _make_provider()
    mock_client.comment_exists.return_value = {"id": 1}
    assert provider.comment_exists("10", "::marker::") is True

    mock_client.comment_exists.return_value = None
    assert provider.comment_exists("10", "::missing::") is False
