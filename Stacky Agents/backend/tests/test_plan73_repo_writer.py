"""Tests F4 — RepoWriter sub-puerto + commit_file. Plan 73."""
from unittest.mock import MagicMock, patch
import pytest

from services.repo_writer import RepoWriter, REPO_WRITER_METHODS
from services.tracker_provider import TrackerApiError


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_gitlab_provider(project="proj"):
    """Devuelve GitLabTrackerProvider con cliente mockeado."""
    from services.gitlab_provider import GitLabTrackerProvider
    provider = GitLabTrackerProvider.__new__(GitLabTrackerProvider)
    mock_client = MagicMock()
    mock_client._project_path.return_value = "my%2Frepo"
    provider._client = mock_client
    provider._project = project
    provider._group = ""
    provider._epics_native = False
    return provider, mock_client


def _make_ado_provider():
    from services.ado_provider import AdoTrackerProvider
    provider = AdoTrackerProvider.__new__(AdoTrackerProvider)
    provider._client = MagicMock()
    provider._project = None
    return provider


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_f4_repo_writer_protocol_passes_with_commit_file():
    """Stub con commit_file → isinstance(stub, RepoWriter) == True."""
    class GoodStub:
        name = "test"
        def commit_file(self, path, content, branch, message):
            return {}
    assert isinstance(GoodStub(), RepoWriter)


def test_f4_repo_writer_protocol_fails_without_commit_file():
    """Stub sin commit_file → NO pasa isinstance."""
    class BadStub:
        name = "test"
    assert not isinstance(BadStub(), RepoWriter)


def test_f4_commit_file_create(tmp_path):
    """commit_file con acción "create" → POST con action=create, retorna sha/status."""
    provider, mock_client = _make_gitlab_provider()
    # _detect_commit_action → "create"
    mock_client._request.side_effect = [
        # GET file → 404
        TrackerApiError(404, "not found", kind="not_found"),
        # POST commit → ok
        ({"id": "abc123", "web_url": "https://gitlab.com/commit/abc"}, {}),
    ]
    result = provider.commit_file("ci.yml", "content", "main", "msg")
    assert result["sha"] == "abc123"
    assert result["status"] == "create"


def test_f4_c1_tracker_api_error_propagated():
    """[C1] Si _request lanza TrackerApiError(403), commit_file lo propaga sin capturar."""
    provider, mock_client = _make_gitlab_provider()
    mock_client._request.side_effect = TrackerApiError(403, "no api scope", kind="forbidden")
    with pytest.raises(TrackerApiError) as exc_info:
        provider.commit_file("ci.yml", "content", "main", "msg")
    assert exc_info.value.status == 403
    assert exc_info.value.kind == "forbidden"


def test_f4_c7_idempotence_unchanged():
    """[C7] Si el contenido es idéntico al actual, retorna 'unchanged' sin llamar al POST."""
    import base64
    provider, mock_client = _make_gitlab_provider()
    existing_content = "content"
    encoded = base64.b64encode(existing_content.encode()).decode()
    # Primera llamada → GET del archivo (devuelve contenido existente)
    mock_client._request.side_effect = [
        ({"content": encoded}, {}),  # GET file → existe, mismo contenido
    ]
    result = provider.commit_file("ci.yml", existing_content, "main", "msg")
    assert result["status"] == "unchanged"
    # El POST no se llamó después del GET inicial
    # _request fue llamado exactamente 1 vez (el GET)
    assert mock_client._request.call_count == 1


# NOTA: test_f4_ado_commit_file_raises_not_implemented se eliminó en Plan 95 F1.a porque
# commit_file ADO ahora está implementado. Originalmente verificaba NotImplementedError para v1.


def test_f4_c8_get_repo_writer_returns_gitlab_adapter():
    """[C8] get_repo_writer con proyecto GitLab devuelve adapter con name='gitlab'.
    Parcheo en el módulo origen (import lazy, patrón del repo)."""
    from services.repo_writer import get_repo_writer
    mock_provider = MagicMock()
    mock_provider.name = "gitlab"
    mock_provider.commit_file = MagicMock(
        return_value={"sha": "x", "status": "create", "branch": "b", "path": "p", "web_url": ""}
    )

    with patch("services.tracker_provider.get_tracker_provider", return_value=mock_provider):
        writer = get_repo_writer(project="test-project")
    assert writer.name == "gitlab"
