"""Plan 72 F1 — Tests del sub-puerto CIProvider extendido con trigger_pipeline.

6 casos:
  1. CIProvider con 3 métodos satisface isinstance; stub sin trigger_pipeline NO.
  2. GitLabCIProvider.monitor_pipeline("99") llama delegate.poll_pipeline("99").
  3. AdoCIProvider.monitor_pipeline("99") lanza NotImplementedError.
  4. GitLabTrackerProvider.trigger_pipeline("develop") POST correcto y devuelve dict.
  5. [C1'] Si _request lanza TrackerApiError(403), trigger_pipeline propaga sin capturar.
  6. [C3] CI_PORT_METHODS == 3-tupla con trigger_pipeline.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.ci_provider import CI_PORT_METHODS, CIProvider, ItemRef, ItemPipelineResult
from services.tracker_provider import TrackerApiError


# ---------------------------------------------------------------------------
# Caso 1 — Protocol runtime_checkable con 3 métodos
# ---------------------------------------------------------------------------
def test_ci_provider_3_methods_isinstance():
    class FullStub:
        name = "stub"

        def infer_item_pipeline(self, item_ref):
            ...

        def monitor_pipeline(self, pipeline_id: str) -> dict:
            ...

        def trigger_pipeline(self, item_ref, ref: str) -> dict:
            ...

    assert isinstance(FullStub(), CIProvider)


def test_ci_provider_missing_trigger_not_isinstance():
    class PartialStub:
        name = "partial"

        def infer_item_pipeline(self, item_ref):
            ...

        def monitor_pipeline(self, pipeline_id: str) -> dict:
            ...

    # Sin trigger_pipeline no satisface el Protocol
    assert not isinstance(PartialStub(), CIProvider)


# ---------------------------------------------------------------------------
# Caso 2 — GitLabCIProvider.monitor_pipeline delega a delegate.poll_pipeline
# ---------------------------------------------------------------------------
def test_gitlab_ci_provider_monitor_delegates():
    from services.gitlab_ci_provider import GitLabCIProvider

    provider = GitLabCIProvider.__new__(GitLabCIProvider)
    mock_delegate = MagicMock()
    mock_delegate.poll_pipeline.return_value = {"id": "99", "status": "success"}
    provider._delegate = mock_delegate

    result = provider.monitor_pipeline("99")

    mock_delegate.poll_pipeline.assert_called_once_with("99")
    assert result["id"] == "99"
    assert result["status"] == "success"


# ---------------------------------------------------------------------------
# Caso 3 — (ELIMINADO) AdoCIProvider.monitor_pipeline lanza NotImplementedError
# ---------------------------------------------------------------------------
# NOTA: Este test se eliminó en Plan 95 F1.c porque monitor_pipeline ADO ahora está implementado.
# Originalmente verificaba NotImplementedError para v1, pero F1 lo implementó.

# ---------------------------------------------------------------------------
# Caso 4 — GitLabTrackerProvider.trigger_pipeline POST correcto
# ---------------------------------------------------------------------------
def test_gitlab_trigger_pipeline_calls_post():
    from services.gitlab_provider import GitLabTrackerProvider

    provider = GitLabTrackerProvider.__new__(GitLabTrackerProvider)
    mock_client = MagicMock()
    mock_client._project_path.return_value = "myorg%2Fmyrepo"
    mock_client._request.return_value = (
        {"id": 1, "status": "created", "ref": "develop", "sha": "abc", "web_url": "http://gl/p/1"},
        {},  # headers
    )
    provider._client = mock_client

    result = provider.trigger_pipeline("develop")

    mock_client._request.assert_called_once_with(
        "POST",
        "/projects/myorg%2Fmyrepo/pipeline",
        json_body={"ref": "develop"},
    )
    assert result["id"] == "1"
    assert result["status"] == "created"


# ---------------------------------------------------------------------------
# Caso 5 — [C1'] TrackerApiError 403 se propaga sin capturar
# ---------------------------------------------------------------------------
def test_gitlab_trigger_pipeline_propagates_tracker_error():
    from services.gitlab_provider import GitLabTrackerProvider

    provider = GitLabTrackerProvider.__new__(GitLabTrackerProvider)
    mock_client = MagicMock()
    mock_client._project_path.return_value = "org%2Frepo"
    mock_client._request.side_effect = TrackerApiError(403, "no api scope", kind="forbidden")
    provider._client = mock_client

    with pytest.raises(TrackerApiError) as exc_info:
        provider.trigger_pipeline("main")

    assert exc_info.value.status == 403
    assert exc_info.value.kind == "forbidden"


# ---------------------------------------------------------------------------
# Caso 6 — [C3] CI_PORT_METHODS es la 3-tupla con trigger_pipeline
# ---------------------------------------------------------------------------
def test_ci_port_methods_is_frozen():
    assert CI_PORT_METHODS == ("infer_item_pipeline", "monitor_pipeline", "trigger_pipeline")
